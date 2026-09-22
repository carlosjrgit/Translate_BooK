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


def clean_repetition_loops(text: str) -> str:
    """Remove loops de alucinação, repetições degeneradas e vazamentos de corpus de treino."""
    if not text:
        return ""

    # 1. Identifica frases de vazamento originadas em model_input=
    model_input_matches = re.findall(r"(?i)\bmodel_input\s*=\s*(.*?)(?:-|\n|$)", text)
    leak_phrases = set()
    for m in model_input_matches:
        phrase = m.strip().lower()
        if phrase:
            leak_phrases.add(phrase)

    meta_patterns = [
        re.compile(r"(?i)\bmodel_input\b"),
        re.compile(r"(?i)\bwikisource\b"),
        re.compile(r"(?i)\bwikipedia\b"),
        re.compile(r"(?i)\bwikiquote\b"),
    ]

    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            cleaned_lines.append("")
            continue
        if any(pat.search(line) for pat in meta_patterns):
            continue
        if line.lower() in leak_phrases:
            continue
        cleaned_lines.append(raw_line)

    cleaned = "\n".join(cleaned_lines)

    # 2. Desduplicação de linhas consecutivas; se uma linha repetir 3+ vezes, trata como loop degenerado e remove
    raw_lines = cleaned.splitlines()
    deduped_lines = []
    idx = 0
    while idx < len(raw_lines):
        line = raw_lines[idx]
        stripped = line.strip().lower()
        if not stripped:
            deduped_lines.append("")
            idx += 1
            continue

        repeat_count = 1
        while (idx + repeat_count < len(raw_lines)) and (raw_lines[idx + repeat_count].strip().lower() == stripped):
            repeat_count += 1

        if repeat_count >= 3:
            idx += repeat_count
            continue
        else:
            deduped_lines.append(line)
            idx += repeat_count

    cleaned = "\n".join(deduped_lines)


    # 3. Desduplicação de orações/frases repetidas em sequência
    def dedup_consecutive_sentences(paragraph: str) -> str:
        tokens = re.split(r'([.!?]+(?:\s+|$))', paragraph)
        reconstructed = []
        prev_sent = None
        i = 0
        while i < len(tokens):
            chunk = tokens[i]
            delim = tokens[i + 1] if i + 1 < len(tokens) else ""
            sent_norm = chunk.strip().lower()
            if sent_norm and sent_norm == prev_sent:
                i += 2
                continue
            if sent_norm:
                prev_sent = sent_norm
            reconstructed.append(chunk + delim)
            i += 2
        return "".join(reconstructed)

    para_chunks = [dedup_consecutive_sentences(p) for p in cleaned.split("\n\n")]
    cleaned = "\n\n".join(para_chunks)

    # 4. Remove repetições consecutivas de n-gramas (>= 3 palavras repetidas 2+ vezes)
    cleaned = re.sub(
        r'\b((?:[\wÀ-ÿ]+\s+){2,}[\wÀ-ÿ]+)(?:\s+\1)+\b',
        r'\1',
        cleaned,
        flags=re.IGNORECASE,
    )

    # 5. Normaliza quebras de linha excessivas
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()

    return cleaned


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


class _SentencePieceTokenizerAdapter:
    """Adaptador de tokenizer SentencePiece nativo com suporte a caminhos Windows com acentuação."""

    def __init__(self, model_file: Path | str) -> None:
        import sentencepiece as spm

        model_path = Path(model_file)
        with open(model_path, "rb") as f:
            proto_data = f.read()
        self._sp = spm.SentencePieceProcessor()
        self._sp.load_from_serialized_proto(proto_data)

    def encode(self, text: str) -> list[int]:
        return self._sp.encode(text, out_type=int)

    def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
        return [self._sp.id_to_piece(i) for i in ids]

    def convert_tokens_to_ids(self, tokens: list[str]) -> list[int]:
        return [self._sp.piece_to_id(t) for t in tokens]

    def decode(self, tokens_or_ids: list[Any]) -> str:
        if not tokens_or_ids:
            return ""
        if isinstance(tokens_or_ids[0], str):
            return self._sp.decode(tokens_or_ids)
        return self._sp.decode([int(x) for x in tokens_or_ids])


class CTranslate2Backend:
    """Backend CTranslate2 de alto desempenho para modelos seq2seq/encoder-decoder em C++."""

    def __init__(
        self,
        model_path: str | Path,
        device: DeviceType = DeviceType.CPU,
        quantization: QuantizationType = QuantizationType.Q8,
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
        except ImportError as err:
            raise TranslationEngineError(
                f"Dependência CTranslate2 ausente no ambiente: {err}. "
                f"Instale com 'pip install ctranslate2'."
            ) from err

        compute_type = self.quantization.value
        dev = "cuda" if self.device == DeviceType.CUDA else "cpu"

        # Adapta compute_type dinamicamente caso o dispositivo não suporte o tipo solicitado
        try:
            supported = ctranslate2.get_supported_compute_types(dev)
        except Exception:
            supported = set()

        if supported and compute_type not in supported:
            logger.warning(
                f"Tipo de computação '{compute_type}' não suportado pelo dispositivo '{dev}'. "
                f"Tipos suportados: {supported}. Adaptando para tipo compatível."
            )
            if "int8" in supported:
                compute_type = "int8"
            elif "int8_float32" in supported:
                compute_type = "int8_float32"
            elif "float32" in supported:
                compute_type = "float32"
            else:
                compute_type = "auto"

        logger.info(
            f"Carregando CTranslate2: modelo='{self.model_path}', device='{dev}', compute_type='{compute_type}'"
        )
        try:
            self._translator = ctranslate2.Translator(
                str(self.model_path),
                device=dev,
                compute_type=compute_type,
            )
        except Exception as load_err:
            if dev == "cuda":
                logger.warning(
                    f"Falha ao carregar modelo em CUDA ({load_err}). "
                    f"Ativando fallback de segurança automático para CPU com INT8."
                )
                dev = "cpu"
                self.device = DeviceType.CPU
                cpu_supported = ctranslate2.get_supported_compute_types("cpu")
                compute_type = "int8" if "int8" in cpu_supported else "auto"
                self._translator = ctranslate2.Translator(
                    str(self.model_path),
                    device="cpu",
                    compute_type=compute_type,
                )
            else:
                raise

        # Carregamento do tokenizer com suporte a caminhos Windows com acentuação
        sp_model_file = self.model_path / "spiece.model"
        tokenizer_loaded = False

        if sp_model_file.exists():
            try:
                self._tokenizer = _SentencePieceTokenizerAdapter(sp_model_file)
                tokenizer_loaded = True
            except Exception as sp_err:
                logger.warning(
                    f"Não foi possível carregar via SentencePieceAdapter ({sp_err}). Tentando AutoTokenizer..."
                )

        if not tokenizer_loaded:
            try:
                from transformers import AutoTokenizer  # type: ignore

                self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), use_fast=False)
            except Exception as tok_err:
                raise TranslationEngineError(
                    f"Falha ao inicializar o tokenizer para o modelo em '{self.model_path}': {tok_err}"
                ) from tok_err

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
        if "</s>" not in tokens:
            tokens.append("</s>")

        beam_size = max(n_best, 4)
        decoding_len = max(max_tokens, len(tokens) * 3)
        results = self._translator.translate_batch(
            [tokens],
            max_decoding_length=decoding_len,
            sampling_temperature=temperature,
            num_hypotheses=n_best,
            beam_size=beam_size,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
        )

        hypotheses = []
        total_tokens = 0
        for hyp_tokens in results[0].hypotheses:
            clean_hyp = [t for t in hyp_tokens if t != "</s>"]
            decoded = self._tokenizer.decode(
                self._tokenizer.convert_tokens_to_ids(clean_hyp)
            ).strip()
            decoded = clean_repetition_loops(decoded)
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
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
        )
        hypotheses = [
            clean_repetition_loops(
                self._tokenizer.decode(out, skip_special_tokens=True).strip()
            )
            for out in outputs
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

        # 3. Pós-processamento, preservação de glossário e diretrizes de estilo
        candidates: list[TranslationCandidate] = []
        for idx, hyp_text in enumerate(hypotheses, start=1):
            final_text = clean_repetition_loops(hyp_text)
            glossary_enforcements: list[str] = []

            # Aplicação prioritária de termos de glossário
            if context and context.relevant_glossary:
                for g in context.relevant_glossary:
                    if g.source_term and g.target_term:
                        src_pattern = re.compile(rf"\b{re.escape(g.source_term)}\b", re.IGNORECASE)
                        # Se o termo original em inglês estava no texto do segmento
                        if src_pattern.search(input_text):
                            # Se o modelo manteve o termo em inglês ou calque na tradução
                            if src_pattern.search(final_text):
                                final_text = src_pattern.sub(g.target_term, final_text)
                                glossary_enforcements.append(g.source_term)
                            # Se houver aliases cadastrados para o termo
                            for alias in getattr(g, "aliases", []) or []:
                                a_pat = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
                                if a_pat.search(final_text):
                                    final_text = a_pat.sub(g.target_term, final_text)
                                    glossary_enforcements.append(alias)

            # Aplicação de estilo editorial da obra
            if style_bible:
                is_dialogue = (
                    segment.metadata.get("segment_type") == "dialogue"
                    or getattr(style_bible, "editorial_punctuation", "") in ("dialogue_dash", "travessao")
                    or getattr(style_bible, "dialogue_style", "") in ("dash", "travessao")
                )
                if is_dialogue and final_text:
                    if final_text.startswith('"') and final_text.endswith('"') and len(final_text) > 2:
                        final_text = f"— {final_text[1:-1].strip()}"
                    elif final_text.startswith('"') and not final_text.startswith("—"):
                        final_text = re.sub(r'^"\s*', "— ", final_text)

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
