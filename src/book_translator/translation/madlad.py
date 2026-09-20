"""Implementação desacoplada do motor de tradução MADLAD-400-10B-MT com suporte a múltiplos runtimes e quantizações."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from book_translator.context.base import TranslationContext
from book_translator.core.models import Segment
from book_translator.errors import TranslationEngineError
from book_translator.logging import get_logger
from book_translator.memory.style_bible import StyleBible
from book_translator.translation.base import (
    CandidateRankerInterface,
    TranslationCandidate,
    TranslationDraft,
    TranslationEngine,
)

logger = get_logger("translation.madlad")


class QuantizationType(str, Enum):
    """Níveis de quantização suportados para o modelo MADLAD-400-10B-MT."""

    Q4 = "int4"  # ~5.5 GB em disco / VRAM
    Q6 = "int8_float16"  # ~7.5 GB - Pesos em INT8, ativações em FP16 (equilíbrio ideal)
    Q8 = "int8"  # ~10.5 GB - INT8 puro
    FP16 = "float16"  # ~20.5 GB - Precisão de meia flutuação
    BF16 = "bfloat16"  # ~20.5 GB - Bfloat16 para hardware moderno


class DeviceType(str, Enum):
    """Dispositivos de computação para inferência local."""

    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
    DIRECTML = "directml"


class RuntimeType(str, Enum):
    """Runtimes de inferência suportados."""

    CTRANSLATE2 = "ctranslate2"
    TRANSFORMERS = "transformers"
    MOCK = "mock"


class MissingModelWeightsError(TranslationEngineError):
    """Lançado quando os pesos do modelo não foram encontrados localmente e download não foi autorizado."""

    pass


@runtime_checkable
class BackendProtocol(Protocol):
    """Protocolo formal para runtimes de inferência sob o MADLAD Engine."""

    @property
    def runtime_name(self) -> str: ...

    def is_ready(self) -> bool: ...

    def translate(
        self,
        prompt: str,
        target_lang: str = "pt",
        max_tokens: int = 512,
        temperature: float = 0.0,
        n_best: int = 1,
    ) -> tuple[list[str], float, dict[str, Any]]: ...


class MockMadladBackend:
    """Backend simulado de alta fidelidade e determinístico para testes unitários, CI e benchmarks offline."""

    def __init__(self, latency_per_token_ms: float = 1.2) -> None:
        self.latency_per_token_ms = latency_per_token_ms
        self._ready = True

        # Mapeamento léxico de teste EN -> PT-BR para frases e termos literários clássicos
        self._lexicon: dict[str, str] = {
            "dr. john watson sat near the fireplace at 221b baker street, listening carefully.": (
                "O Dr. John Watson sentou-se perto da lareira na Baker Street, 221B, ouvindo atentamente."
            ),
            "sherlock holmes examined the footprint with his magnifying glass.": (
                "Sherlock Holmes examinou a pegada com sua lente de aumento."
            ),
            "'the thief was hasty,' said holmes.": ("— O ladrão foi precipitado — disse Holmes."),
            "suddenly watson stood up.": ("Subitamente Watson levantou-se."),
            "'do you believe scotland yard will arrive in time, holmes?' asked watson.": (
                "— Você acredita que a Scotland Yard chegará a tempo, Holmes? — perguntou Watson."
            ),
            "inspector lestrade had sent an urgent telegram regarding the blackwood sapphire.": (
                "O Inspetor Lestrade havia enviado um telegrama urgente a respeito da safira de Blackwood."
            ),
            "the train arrived at dartmoor under heavy rain and ominous thunder.": (
                "O trem chegou a Dartmoor sob forte chuva e trovões sinistros."
            ),
            "sherlock holmes and watson met lady margaret at the grand entrance.": (
                "Sherlock Holmes e Watson encontraram Lady Margaret na grande entrada."
            ),
            "she was trembling.": ("Ela estava tremendo."),
            "'the sapphire vanished at midnight from the safe,' whispered lady margaret.": (
                "— A safira desapareceu à meia-noite do cofre — sussurrou Lady Margaret."
            ),
            "meanwhile holmes inspected the lock.": (
                "Enquanto isso, Holmes inspecionava a fechadura."
            ),
        }

        # Mapeamento reverso automático para retrotradução PT-BR -> EN
        self._reverse_lexicon: dict[str, str] = {
            v.strip().lower(): k for k, v in self._lexicon.items()
        }
        # Adiciona formas normalizadas sem travessão editorial
        for k, v in list(self._lexicon.items()):
            clean_pt = re.sub(r"^[—–-]\s*", "", v).strip().lower()
            clean_pt = re.sub(r"\s*[—–-]\s*disse\s+holmes\.?", ", said holmes.", clean_pt)
            self._reverse_lexicon[clean_pt] = k

        # Mapeamento de palavras comuns para fallback de tradução reversa PT -> EN
        self._pt_to_en_words: dict[str, str] = {
            "o": "the",
            "a": "the",
            "os": "the",
            "as": "the",
            "um": "a",
            "uma": "a",
            "e": "and",
            "disse": "said",
            "perguntou": "asked",
            "respondeu": "replied",
            "safira": "sapphire",
            "detetive": "detective",
            "mansão": "manor",
            "castelo": "castle",
            "holmes": "Holmes",
            "watson": "Watson",
            "em": "in",
            "na": "at",
            "no": "at",
            "sobre": "on",
            "ele": "he",
            "ela": "she",
            "estava": "was",
            "estavam": "were",
            "não": "not",
            "nunca": "never",
            "com": "with",
            "de": "of",
            "do": "of the",
            "da": "of the",
            "para": "to",
            "por": "for",
        }

    @property
    def runtime_name(self) -> str:
        return "mock"

    def is_ready(self) -> bool:
        return self._ready

    def translate(
        self,
        prompt: str,
        target_lang: str = "pt",
        max_tokens: int = 512,
        temperature: float = 0.0,
        n_best: int = 1,
    ) -> tuple[list[str], float, dict[str, Any]]:
        # Remove o prefixo de idioma MADLAD (<2pt> ou <2en>) para normalização do prompt
        clean_text = re.sub(r"^<2[a-z]{2,5}>\s*", "", prompt).strip()
        clean_lower = clean_text.lower()

        t0 = time.perf_counter()

        # Rota de retrotradução: PT-BR -> EN
        if target_lang.startswith("en"):
            if clean_lower in self._reverse_lexicon:
                base_output = self._reverse_lexicon[clean_lower]
                # Preserva maiúsculas iniciais
                if clean_text and clean_text[0].isupper() and base_output:
                    base_output = base_output[0].upper() + base_output[1:]
            else:
                words = clean_text.split()
                en_words = []
                for w in words:
                    clean_w = re.sub(r"[^\w]", "", w.lower())
                    tr_w = self._pt_to_en_words.get(clean_w, w)
                    en_words.append(tr_w)
                base_output = " ".join(en_words)
                if clean_text.endswith("."):
                    base_output = base_output.rstrip(".") + "."

            hypotheses = [base_output]
            while len(hypotheses) < n_best:
                hypotheses.append(f"{base_output} [var_{len(hypotheses) + 1}]")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return hypotheses, elapsed_ms, {"runtime": "mock", "tokens_generated": len(base_output.split())}

        # Rota primária: EN -> PT-BR
        if clean_lower in self._lexicon:
            base_output = self._lexicon[clean_lower]
        else:
            # Fallback heurístico: substitui palavras comuns e prefixa marcação
            words = clean_text.split()
            tr_words = []
            word_map = {
                "the": "o",
                "a": "um",
                "an": "um",
                "and": "e",
                "said": "disse",
                "asked": "perguntou",
                "replied": "respondeu",
                "sapphire": "safira",
                "detective": "detetive",
                "manor": "mansão",
                "castle": "castelo",
                "holmes": "Holmes",
                "watson": "Watson",
                "at": "em",
                "in": "em",
                "on": "sobre",
                "he": "ele",
                "she": "ela",
                "was": "estava",
                "were": "estavam",
            }
            for w in words:
                clean_w = re.sub(r"[^\w]", "", w.lower())
                tr_w = word_map.get(clean_w, w)
                tr_words.append(tr_w)
            base_output = " ".join(tr_words)

        hypotheses = [base_output]

        # Gera hipóteses alternativas para N-best
        if n_best > 1:
            # Hipótese 2: variação estilística (diálogo em aspas ou sinônimo léxico)
            v2 = base_output
            if v2.startswith("— "):
                v2 = f'"{v2[2:].strip()}"'
            elif "ouvindo atentamente" in v2:
                v2 = v2.replace("ouvindo atentamente", "escutando com atenção")
            elif "disse Holmes" in v2:
                v2 = v2.replace("disse Holmes", "afirmou Holmes")
            elif "perguntou Watson" in v2:
                v2 = v2.replace("perguntou Watson", "indagou Watson")
            elif "examinou" in v2:
                v2 = v2.replace("examinou", "analisou")
            else:
                v2 = f"{v2} (alt)"
            hypotheses.append(v2)

        if n_best > 2:
            # Hipótese 3: variação de vocabulário formal
            v3 = base_output
            if "perto da lareira" in v3:
                v3 = v3.replace("perto da lareira", "junto à lareira")
            elif "com sua lente de aumento" in v3:
                v3 = v3.replace("com sua lente de aumento", "através de sua lupa")
            elif "precipitado" in v3:
                v3 = v3.replace("precipitado", "apressado")
            else:
                v3 = f"{base_output}."
            hypotheses.append(v3)

        while len(hypotheses) < n_best:
            hypotheses.append(f"{base_output} [var_{len(hypotheses) + 1}]")

        hypotheses = hypotheses[:n_best]

        # Simula latência computacional proporcional ao comprimento em tokens
        token_count = max(1, len(clean_text.split())) * n_best
        simulated_duration = (token_count * self.latency_per_token_ms) / 1000.0
        time.sleep(min(simulated_duration, 0.02))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        metadata = {
            "tokens_generated": sum(len(h.split()) for h in hypotheses),
            "runtime": "mock",
            "quantization": "simulated",
            "simulated_latency_ms": elapsed_ms,
            "n_best": len(hypotheses),
        }
        return hypotheses, elapsed_ms, metadata


class CTranslate2Backend:
    """Backend CTranslate2 de alto desempenho para modelos seq2seq/encoder-decoder em C++."""

    def __init__(
        self,
        model_path: str | Path,
        device: DeviceType = DeviceType.CPU,
        quantization: QuantizationType = QuantizationType.Q6,
        allow_download: bool = False,
    ) -> None:
        self.model_path = Path(model_path)
        self.device = device
        self.quantization = quantization
        self.allow_download = allow_download
        self._translator: Any = None
        self._tokenizer: Any = None
        self._ready = False

    @property
    def runtime_name(self) -> str:
        return "ctranslate2"

    def is_ready(self) -> bool:
        return self._ready

    def load(self) -> None:
        """Carrega o modelo CTranslate2 e o tokenizer associado."""
        if not self.model_path.exists():
            if not self.allow_download:
                raise MissingModelWeightsError(
                    f"Diretório de pesos não encontrado em '{self.model_path}'. "
                    f"Por segurança arquitetural (Prompt 14), o download automático de modelos "
                    f"pesados está DESATIVADO por padrão. Forneça o caminho local dos pesos "
                    f"ou habilite explicitamente 'allow_download=True'."
                )
            raise NotImplementedError(
                "Download automático de pesos não implementado sem aprovação."
            )

        try:
            import ctranslate2
            from transformers import AutoTokenizer  # type: ignore
        except ImportError as err:
            raise TranslationEngineError(
                f"Dependência CTranslate2 ou Transformers ausente no ambiente: {err}. "
                f"Instale com 'pip install ctranslate2 transformers'."
            ) from err

        compute_type = self.quantization.value
        dev = "cuda" if self.device == DeviceType.CUDA else "cpu"

        logger.info(
            f"Carregando CTranslate2: modelo='{self.model_path}', device='{dev}', compute_type='{compute_type}'"
        )
        self._translator = ctranslate2.Translator(
            str(self.model_path),
            device=dev,
            compute_type=compute_type,
        )
        self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))
        self._ready = True

    def translate(
        self,
        prompt: str,
        target_lang: str = "pt",
        max_tokens: int = 512,
        temperature: float = 0.0,
        n_best: int = 1,
    ) -> tuple[list[str], float, dict[str, Any]]:
        if not self._ready or self._translator is None:
            self.load()

        t0 = time.perf_counter()
        # MADLAD-400 utiliza token de destino <2pt> no início da entrada
        lang_prefix = f"<2{target_lang}>"
        input_text = f"{lang_prefix} {prompt}" if not prompt.startswith("<2") else prompt

        tokens = self._tokenizer.convert_ids_to_tokens(self._tokenizer.encode(input_text))
        beam_size = max(n_best, 4)
        results = self._translator.translate_batch(
            [tokens],
            max_decoding_length=max_tokens,
            sampling_temperature=temperature,
            num_hypotheses=n_best,
            beam_size=beam_size,
        )

        hypotheses = []
        total_tokens = 0
        for hyp_tokens in results[0].hypotheses:
            decoded = self._tokenizer.decode(
                self._tokenizer.convert_tokens_to_ids(hyp_tokens)
            ).strip()
            hypotheses.append(decoded)
            total_tokens += len(hyp_tokens)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        meta = {
            "tokens_generated": total_tokens,
            "runtime": "ctranslate2",
            "compute_type": self.quantization.value,
            "device": self.device.value,
            "n_best": len(hypotheses),
        }
        return hypotheses, elapsed_ms, meta


class TransformersBackend:
    """Backend alternativo HuggingFace Transformers / PyTorch (usado para referência e fallback)."""

    def __init__(
        self,
        model_name_or_path: str = "google/madlad400-10b-mt",
        device: DeviceType = DeviceType.CPU,
        allow_download: bool = False,
    ) -> None:
        self.model_path = model_name_or_path
        self.device = device
        self.allow_download = allow_download
        self._ready = False
        self._model: Any = None
        self._tokenizer: Any = None

    @property
    def runtime_name(self) -> str:
        return "transformers"

    def is_ready(self) -> bool:
        return self._ready

    def load(self) -> None:
        if not Path(self.model_path).exists() and not self.allow_download:
            raise MissingModelWeightsError(
                f"Pesos de Transformers não encontrados em '{self.model_path}' e download automático não autorizado."
            )
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # type: ignore
        except ImportError as err:
            raise TranslationEngineError(
                f"Dependências PyTorch / Transformers ausentes: {err}"
            ) from err

        logger.info(f"Carregando HuggingFace Transformers: '{self.model_path}'")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_path)
        self._ready = True

    def translate(
        self,
        prompt: str,
        target_lang: str = "pt",
        max_tokens: int = 512,
        temperature: float = 0.0,
        n_best: int = 1,
    ) -> tuple[list[str], float, dict[str, Any]]:
        if not self._ready:
            self.load()

        t0 = time.perf_counter()
        lang_prefix = f"<2{target_lang}>"
        input_text = f"{lang_prefix} {prompt}" if not prompt.startswith("<2") else prompt

        inputs = self._tokenizer(input_text, return_tensors="pt")
        beam_size = max(n_best, 4)
        outputs = self._model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=temperature if temperature > 0 else None,
            do_sample=temperature > 0,
            num_return_sequences=n_best,
            num_beams=beam_size,
        )
        hypotheses = [
            self._tokenizer.decode(out, skip_special_tokens=True).strip() for out in outputs
        ]
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        meta = {
            "tokens_generated": sum(len(o) for o in outputs),
            "runtime": "transformers",
            "device": self.device.value,
            "n_best": len(hypotheses),
        }
        return hypotheses, elapsed_ms, meta


class MadladTranslationEngine(TranslationEngine):
    """Motor de tradução desacoplado compatível com MADLAD-400-10B-MT e o protocolo TranslationEngine.

    Recursos essenciais:
    - Desacoplamento estrito de runtime (Mock, CTranslate2, Transformers).
    - Suporte a prefixos linguísticos de destino (<2pt> para PT-BR).
    - Aplicação e preservação determinística de termos travados de Glossário e TM.
    - Salvaguarda rígida contra download automático de modelos gigantes sem consentimento.
    """

    def __init__(
        self,
        backend: BackendProtocol | None = None,
        runtime_type: RuntimeType = RuntimeType.MOCK,
        quantization: QuantizationType = QuantizationType.Q6,
        device: DeviceType = DeviceType.CPU,
        model_path: str | Path | None = None,
        allow_download: bool = False,
    ) -> None:
        self.quantization = quantization
        self.device = device
        self.allow_download = allow_download
        self._engine_name = f"madlad-400-10b-mt-{quantization.name.lower()}"

        if backend is not None:
            self.backend = backend
        elif runtime_type == RuntimeType.CTRANSLATE2:
            self.backend = CTranslate2Backend(
                model_path=model_path or "models/madlad-400-10b-mt-ct2",
                device=device,
                quantization=quantization,
                allow_download=allow_download,
            )
        elif runtime_type == RuntimeType.TRANSFORMERS:
            self.backend = TransformersBackend(
                model_name_or_path=str(model_path or "google/madlad400-10b-mt"),
                device=device,
                allow_download=allow_download,
            )
        else:
            self.backend = MockMadladBackend()

    @property
    def engine_name(self) -> str:
        return self._engine_name

    def is_ready(self) -> bool:
        return self.backend.is_ready()

    def translate_segment(
        self,
        segment: Segment,
        context: TranslationContext | None = None,
        n_best: int = 1,
        ranker: CandidateRankerInterface | None = None,
        style_bible: StyleBible | None = None,
    ) -> TranslationDraft:
        """Traduz um segmento textual aplicando as salvaguardas contextuais, termos travados e N-best."""
        input_text = segment.original_text.strip()
        timestamp_now = datetime.now(timezone.utc).isoformat()

        if not input_text:
            return TranslationDraft(
                segment_id=segment.id,
                selected_text="",
                candidates=[TranslationCandidate(text="", score=1.0, rank=1)],
                engine_name=self.engine_name,
                execution_time_ms=0.0,
                metadata={
                    "source_text": input_text,
                    "model_name": self.engine_name,
                    "runtime": self.backend.runtime_name,
                    "parameters": {
                        "quantization": self.quantization.value,
                        "device": self.device.value,
                        "n_best": n_best,
                    },
                    "context_used": context.reproducibility_hash if context else None,
                    "timestamp": timestamp_now,
                    "version": "1.0.0",
                },
            )

        # 1. Verificação prioritária de correspondência exata na Translation Memory (locked)
        if context and context.established_translations:
            for tm in context.established_translations:
                if tm.locked and tm.source_term.strip().lower() == input_text.lower():
                    logger.debug(f"Tradução resolvida via TM travada para segmento #{segment.id}")
                    cand = TranslationCandidate(
                        text=tm.target_term,
                        score=1.0,
                        rank=1,
                        metadata={
                            "origin": "translation_memory",
                            "locked": True,
                            "source_text": input_text,
                            "runtime": self.backend.runtime_name,
                            "model_name": self.engine_name,
                        },
                    )
                    return TranslationDraft(
                        segment_id=segment.id,
                        selected_text=tm.target_term,
                        candidates=[cand],
                        engine_name=self.engine_name,
                        execution_time_ms=0.0,
                        metadata={
                            "source": "tm_locked_match",
                            "source_text": input_text,
                            "model_name": self.engine_name,
                            "runtime": self.backend.runtime_name,
                            "parameters": {
                                "quantization": self.quantization.value,
                                "device": self.device.value,
                                "n_best": n_best,
                            },
                            "context_used": context.reproducibility_hash if context else None,
                            "timestamp": timestamp_now,
                            "version": "1.0.0",
                        },
                    )

        # 2. Execução da inferência linguística com o backend ativo
        raw_output, elapsed_ms, meta = self.backend.translate(
            prompt=input_text,
            target_lang="pt",
            n_best=n_best,
        )

        hypotheses: list[str] = raw_output if isinstance(raw_output, list) else [raw_output]

        # 3. Pós-processamento e preservação de termos de glossário travados para cada hipótese
        candidates: list[TranslationCandidate] = []
        for idx, hyp_text in enumerate(hypotheses, start=1):
            final_text = hyp_text
            glossary_enforcements: list[str] = []

            if context and context.relevant_glossary:
                for g in context.relevant_glossary:
                    if g.locked and g.source_term and g.target_term:
                        pattern = re.compile(rf"\b{re.escape(g.source_term)}\b", re.IGNORECASE)
                        if pattern.search(final_text):
                            final_text = pattern.sub(g.target_term, final_text)
                            glossary_enforcements.append(g.source_term)

            candidate = TranslationCandidate(
                text=final_text,
                score=0.95,
                rank=idx,
                metadata={
                    **meta,
                    "source_text": input_text,
                    "model_name": self.engine_name,
                    "runtime": self.backend.runtime_name,
                    "glossary_enforcements": glossary_enforcements,
                },
            )
            candidates.append(candidate)

        # 4. Ranqueamento com CandidateRanker se n_best > 1
        if ranker and len(candidates) > 1:
            if hasattr(ranker, "rank_candidates"):
                candidates = ranker.rank_candidates(
                    candidates,
                    context=context,
                    style_bible=style_bible,
                    source_text=input_text,
                )
            else:
                top = ranker.rank(candidates, context=context)
                if candidates and candidates[0] != top:
                    if top in candidates:
                        candidates.remove(top)
                    candidates.insert(0, top)
                for r_idx, c in enumerate(candidates, start=1):
                    c.rank = r_idx

        selected_text = candidates[0].text if candidates else ""

        draft = TranslationDraft(
            segment_id=segment.id,
            selected_text=selected_text,
            candidates=candidates,
            engine_name=self.engine_name,
            execution_time_ms=elapsed_ms,
            metadata={
                "source_text": input_text,
                "model_name": self.engine_name,
                "runtime": self.backend.runtime_name,
                "parameters": {
                    "quantization": self.quantization.value,
                    "device": self.device.value,
                    "n_best": n_best,
                },
                "context_used": context.reproducibility_hash if context else None,
                "tokens_generated": meta.get("tokens_generated", len(selected_text.split())),
                "timestamp": timestamp_now,
                "version": "1.0.0",
            },
        )
        return draft

    def translate_text(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "pt",
    ) -> str:
        """Traduz um texto isolado diretamente para o idioma alvo (usado para retrotradução e testes)."""
        clean = text.strip()
        if not clean:
            return ""
        raw_output, _, _ = self.backend.translate(
            prompt=clean,
            target_lang=target_lang,
            n_best=1,
        )
        if isinstance(raw_output, list):
            return raw_output[0] if raw_output else ""
        return str(raw_output)
