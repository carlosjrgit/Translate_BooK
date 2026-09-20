"""Motor de Controle de Qualidade Semântico Multi-Sinal (Prompt 18).

Implementa validação semântica profunda sem tratar similaridade vetorial isolada como autoridade,
combinando 6 sinais ortogonais: alinhamento vetorial, consistência de sujeito, análise de polaridade,
gradiente de intensidade, densidade de conteúdo e detecção de falsos amigos (tradução literal problemática).
"""

from __future__ import annotations

import math
import re
from typing import Any

from book_translator.core.models import Segment
from book_translator.logging import get_logger
from book_translator.qa.base import (
    IssueSeverity,
    QAIssue,
    SemanticEncoderProtocol,
    SemanticEvaluationResult,
    SemanticQAInterface,
    SemanticSignalScores,
)

logger = get_logger("qa.semantic")


# -----------------------------------------------------------------------------
# Encoders Semânticos Multilíngues (Interface Substituível)
# -----------------------------------------------------------------------------
class MockSemanticEncoder:
    """Encoder determinístico e leve para testes unitários, CI e benchmarks offline.

    Utiliza representação de n-gramas de caracteres e alinhamento de vocabulário
    cruzado para estimar similaridade semântica de forma reprodutível sem dependência de GPU.
    """

    def __init__(self) -> None:
        # Mini-léxico cruzado EN <-> PT para pesos semânticos no encoder mock
        self._cross_lingual_anchors: dict[str, set[str]] = {
            "doctor": {"doutor", "médico", "dr"},
            "sat": {"sentou", "sentado"},
            "fireplace": {"lareira"},
            "listening": {"ouvindo", "escutando"},
            "carefully": {"atentamente", "cuidado"},
            "detective": {"detetive", "investigador"},
            "examined": {"examinou", "analisou", "inspecionou"},
            "footprint": {"pegada", "rastro"},
            "glass": {"lente", "vidro", "lupa"},
            "thief": {"ladrão", "gatuno"},
            "hasty": {"precipitado", "apressado"},
            "said": {"disse", "afirmou", "falou"},
            "asked": {"perguntou", "indagou"},
            "telegram": {"telegrama", "mensagem"},
            "urgent": {"urgente"},
            "sapphire": {"safira", "joia"},
            "train": {"trem", "comboio"},
            "arrived": {"chegou"},
            "rain": {"chuva"},
            "thunder": {"trovão", "trovões"},
            "trembling": {"tremendo", "trêmula"},
            "vanished": {"desapareceu", "sumiu"},
            "midnight": {"meia-noite"},
            "safe": {"cofre", "seguro"},
            "lock": {"fechadura", "tranca"},
            "witness": {"testemunha"},
            "confirmed": {"confirmou"},
            "statement": {"declaração", "depoimento"},
            "furious": {"furioso", "enfurecido"},
            "terrified": {"aterrorizado", "apavorado"},
            "excruciating": {"excruciante", "insuportável"},
            "overjoyed": {"radiante", "em êxtase", "alegre"},
            "devastated": {"devastado", "arrasado"},
        }

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Gera pseudo-embeddings normalizados baseados em n-gramas e âncoras semânticas."""
        embeddings: list[list[float]] = []
        for text in texts:
            vec = [0.0] * 64
            clean = text.lower()
            words = set(re.findall(r"\b\w+\b", clean))

            # Frequência de caracteres em bins
            for ch in clean:
                idx = ord(ch) % 32
                vec[idx] += 1.0

            # Ativação de âncoras semânticas
            anchor_idx = 32
            for en_key, pt_set in self._cross_lingual_anchors.items():
                if anchor_idx >= 64:
                    break
                if en_key in words or any(pt_w in words for pt_w in pt_set):
                    vec[anchor_idx] += 3.0
                anchor_idx += 1

            # Normalização L2
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            embeddings.append([x / norm for x in vec])
        return embeddings

    def similarity(self, text_a: str, text_b: str) -> float:
        """Calcula similaridade por cosseno com bônus de âncoras semânticas compartilhadas."""
        if not text_a.strip() or not text_b.strip():
            return 0.0

        vecs = self.encode([text_a, text_b])
        dot = sum(a * b for a, b in zip(vecs[0], vecs[1]))
        return max(0.0, min(1.0, dot))


class SentenceTransformerSemanticEncoder:
    """Encoder neural multilíngue baseado em Sentence-Transformers (ex: LaBSE ou MiniLM)."""

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._fallback_encoder = MockSemanticEncoder()

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            self._model = SentenceTransformer(self.model_name)
            return True
        except Exception as exc:
            logger.warning(
                f"SentenceTransformer '{self.model_name}' indisponível ({exc}). Usando fallback mock."
            )
            return False

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self._ensure_loaded():
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        return self._fallback_encoder.encode(texts)

    def similarity(self, text_a: str, text_b: str) -> float:
        if self._ensure_loaded():
            vecs = self.encode([text_a, text_b])
            return float(sum(a * b for a, b in zip(vecs[0], vecs[1])))
        return self._fallback_encoder.similarity(text_a, text_b)


# -----------------------------------------------------------------------------
# Motor de Semantic QA Multi-Sinal
# -----------------------------------------------------------------------------
class SemanticQAEngine(SemanticQAInterface):
    """Validador de qualidade semântica multilíngue combinando 6 sinais analíticos."""

    # Dicionário curado de falsos amigos críticos EN -> PT
    FALSE_COGNATES: dict[str, tuple[str, str]] = {
        # trigger_en: (wrong_pt_regex, correct_suggestion)
        "actually": (r"atualmente", "na verdade / realmente"),
        "eventually": (r"eventualmente", "com o tempo / no final das contas / por fim"),
        "parents": (r"parentes", "pais"),
        "realize": (r"realiz(?:ar|ou|aram|am|o|ava|avam)", "perceber / dar-se conta"),
        "realized": (r"realiz(?:ou|ara|ara|aram|ava)", "percebeu / deu-se conta"),
        "push": (r"pux(?:ar|ou|aram|a|am|ava)", "empurrar"),
        "pushed": (r"pux(?:ou|ara|aram|ava)", "empurrou"),
        "compromise": (r"compromet(?:er|eu|eram|e|em|ia)", "entrar em acordo / transigir"),
        "prejudice": (r"prejuízo", "preconceito"),
        "fabric": (r"fábrica", "tecido"),
        "novel": (r"novela", "romance"),
        "legend": (r"legenda", "lenda"),
        "exquisite": (r"esquisit[ao]s?", "refinado / primoroso / sublime"),
        "pretend": (r"pretend(?:er|eu|eram|e|em|ia)", "fingir"),
        "pretended": (r"pretend(?:eu|era|eram|ia)", "fingiu"),
        "intend": (r"entend(?:er|eu|eram|e|em|ia)", "pretender / tencionar"),
        "collar": (r"colar", "colarinho / coleira"),
    }

    # Tabela de atenuação de intensidade dramática / emocional
    INTENSITY_ATTENUATIONS: dict[str, tuple[list[str], str]] = {
        # en_strong: (pt_weak_regex_list, suggested_pt_strong)
        "furious": ([r"chatead[ao]s?", r"aborrecid[ao]s?", r"irritad[ao]s?", r"pouco contente"], "furioso / enfurecido"),
        "enraged": ([r"chatead[ao]s?", r"aborrecid[ao]s?", r"descontente"], "enfurecido / colérico"),
        "terrified": ([r"preocupad[ao]s?", r"receos[ao]s?", r"com um pouco de medo", r"tímid[ao]s?"], "aterrorizado / apavorado"),
        "petrified": ([r"preocupad[ao]s?", r"inquiet[ao]s?"], "petrificado / paralisado de terror"),
        "excruciating": ([r"desconfortáve(?:l|is)", r"incômod[ao]s?", r"chat[ao]s?", r"leve dor"], "excruciante / insuportável / atroz"),
        "unbearable": ([r"desagradáve(?:l|is)", r"incômod[ao]s?"], "insuportável / intolerável"),
        "overjoyed": ([r"satisfeit[ao]s?", r"contente", r"ok"], "radiante / em êxtase / jubiloso"),
        "devastated": ([r"triste", r"chatead[ao]s?"], "devastado / desolado"),
        "ecstatic": ([r"alegre", r"contente"], "em êxtase / extasiado"),
        "masterpiece": ([r"bom trabalho", r"trabalho legal", r"peça boa"], "obra-prima"),
        "horrific": ([r"ruim", r"desagradáve(?:l|is)"], "horripilante / terrível"),
    }

    # Antônimos para detecção de inversão semântica e contradição
    ANTONYM_PAIRS: list[tuple[set[str], set[str]]] = [
        ({"alive", "living"}, {"morto", "faleceu", "morreu", "sem vida"}),
        ({"dead", "deceased"}, {"vivo", "sobreviveu", "com vida"}),
        ({"accepted", "agreed", "approved"}, {"recusou", "rejeitou", "negou", "desaprovou"}),
        ({"rejected", "refused", "denied"}, {"aceitou", "concordou", "aprovou"}),
        ({"guilty"}, {"inocente", "sem culpa"}),
        ({"innocent"}, {"culpado"}),
        ({"open", "opened"}, {"fechado", "fechou", "trancou"}),
        ({"closed", "locked"}, {"aberto", "abriu"}),
        ({"friend", "ally"}, {"inimigo", "adversário"}),
        ({"enemy", "foe"}, {"amigo", "aliado"}),
        ({"love", "loved"}, {"odiou", "odeia", "detestou"}),
        ({"hate", "hated"}, {"amou", "ama", "adorou"}),
        ({"success", "victory"}, {"fracasso", "derrota", "perda"}),
        ({"failure", "defeat"}, {"sucesso", "vitória"}),
    ]

    def __init__(self, encoder: SemanticEncoderProtocol | None = None) -> None:
        self.encoder: SemanticEncoderProtocol = encoder or MockSemanticEncoder()

    def evaluate_semantic(
        self,
        segment: Segment,
        original_text: str,
        translated_text: str,
        context: Any = None,
    ) -> SemanticEvaluationResult:
        """Executa a bateria completa de validação semântica multi-sinal."""
        src = original_text.strip()
        tgt = translated_text.strip()

        if not src:
            return SemanticEvaluationResult(
                overall_score=1.0,
                signal_scores=SemanticSignalScores(),
                issues=[],
                justifications=["Segmento de origem vazio."],
                passed=True,
            )

        issues: list[QAIssue] = []
        justifications: list[str] = []

        # ---------------------------------------------------------------------
        # 1. Sinal Vetorial: Similaridade de Embedding Cross-Lingual
        # ---------------------------------------------------------------------
        emb_sim = self.encoder.similarity(src, tgt)
        if emb_sim < 0.55 and len(src.split()) > 3:
            issues.append(
                QAIssue(
                    check_type="semantic_divergence",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description=f"Similaridade semântica global baixa ({emb_sim:.2f}). Possível distorção de significado.",
                    original_snippet=src[:60] + "..." if len(src) > 60 else src,
                    translated_snippet=tgt[:60] + "..." if len(tgt) > 60 else tgt,
                )
            )
            justifications.append(f"Similaridade de embedding abaixo do limiar (score={emb_sim:.2f}).")
        else:
            justifications.append(f"Similaridade de embedding satisfatória (score={emb_sim:.2f}).")

        # ---------------------------------------------------------------------
        # 2. Sinal: Omissão e Adição de Conceitos Relevantes
        # ---------------------------------------------------------------------
        content_score, content_issues = self._check_content_omissions_and_additions(src, tgt)
        issues.extend(content_issues)

        # ---------------------------------------------------------------------
        # 3. Sinal: Inversão de Sentido, Polaridade e Contradição
        # ---------------------------------------------------------------------
        polarity_score, polarity_issues = self._check_meaning_reversal_and_polarity(src, tgt)
        issues.extend(polarity_issues)

        # ---------------------------------------------------------------------
        # 4. Sinal: Mudança de Sujeito Gramatical / Agente da Ação
        # ---------------------------------------------------------------------
        subject_score, subject_issues = self._check_subject_shift(src, tgt, context)
        issues.extend(subject_issues)

        # ---------------------------------------------------------------------
        # 5. Sinal: Perda de Intensidade Emocional e Dramática
        # ---------------------------------------------------------------------
        intensity_score, intensity_issues = self._check_intensity_loss(src, tgt)
        issues.extend(intensity_issues)

        # ---------------------------------------------------------------------
        # 6. Sinal: Tradução Literal Problemática e Falsos Cognatos
        # ---------------------------------------------------------------------
        literal_score, literal_issues = self._check_problematic_literal(src, tgt)
        issues.extend(literal_issues)

        # ---------------------------------------------------------------------
        # 7. Sinal: Mudança de Relações entre Personagens
        # ---------------------------------------------------------------------
        rel_issues = self._check_relationship_shift(src, tgt, context)
        issues.extend(rel_issues)

        # ---------------------------------------------------------------------
        # Consolidação Ponderada dos Sinais
        # ---------------------------------------------------------------------
        signal_scores = SemanticSignalScores(
            embedding_similarity=emb_sim,
            subject_consistency=subject_score,
            polarity_consistency=polarity_score,
            intensity_preservation=intensity_score,
            content_preservation=content_score,
            literal_correctness=literal_score,
        )

        overall_score = (
            0.25 * emb_sim
            + 0.20 * subject_score
            + 0.20 * polarity_score
            + 0.15 * content_score
            + 0.10 * intensity_score
            + 0.10 * literal_score
        )
        overall_score = round(max(0.0, min(1.0, overall_score)), 4)

        has_blocking_issue = any(i.severity == IssueSeverity.REVIEW_REQUIRED for i in issues)
        passed = overall_score >= 0.70 and not has_blocking_issue

        return SemanticEvaluationResult(
            overall_score=overall_score,
            signal_scores=signal_scores,
            issues=issues,
            justifications=justifications,
            passed=passed,
        )

    # -------------------------------------------------------------------------
    # Métodos Analíticos Privados
    # -------------------------------------------------------------------------
    def _check_content_omissions_and_additions(
        self, source: str, target: str
    ) -> tuple[float, list[QAIssue]]:
        """Identifica omissões conceituais ou alucinações de conteúdo aditivo."""
        issues: list[QAIssue] = []
        src_words = [w.lower() for w in re.findall(r"\b\w{3,}\b", source)]
        tgt_words = [w.lower() for w in re.findall(r"\b\w{3,}\b", target)]

        if not src_words:
            return 1.0, issues

        # Relação de comprimento de palavras de conteúdo
        ratio = len(tgt_words) / len(src_words)

        # Omissão semântica (corte excessivo de vocabulário de conteúdo)
        if len(src_words) >= 6 and ratio < 0.40:
            issues.append(
                QAIssue(
                    check_type="semantic_omission",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description=f"Possível omissão semântica: a tradução preserva apenas {ratio:.1%} das palavras de conteúdo.",
                    original_snippet=source,
                    translated_snippet=target,
                )
            )
            return 0.4, issues

        # Adição espúria / alucinação de conteúdo
        if len(src_words) >= 4 and ratio > 2.2:
            issues.append(
                QAIssue(
                    check_type="semantic_addition",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description=f"Possível adição semântica não fundamentada: tradução tem {ratio:.1%} do volume original.",
                    original_snippet=source,
                    translated_snippet=target,
                )
            )
            return 0.5, issues

        return 1.0, issues

    def _check_meaning_reversal_and_polarity(
        self, source: str, target: str
    ) -> tuple[float, list[QAIssue]]:
        """Detecta contradições lógicas e inversões de sentido entre original e destino."""
        issues: list[QAIssue] = []
        src_lower = source.lower()
        tgt_lower = target.lower()

        # 1. Antônimos diretos
        for en_set, pt_set in self.ANTONYM_PAIRS:
            en_found = [w for w in en_set if re.search(rf"\b{re.escape(w)}\b", src_lower)]
            pt_found = [w for w in pt_set if re.search(rf"\b{re.escape(w)}\b", tgt_lower)]

            if en_found and pt_found:
                issues.append(
                    QAIssue(
                        check_type="meaning_reversal",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description=f"Inversão de sentido: termo '{en_found[0]}' traduzido com significado antagônico '{pt_found[0]}'.",
                        original_snippet=en_found[0],
                        translated_snippet=pt_found[0],
                    )
                )
                return 0.2, issues

        # 2. Polaridade negativa vs afirmativa
        en_neg = bool(re.search(r"\b(not|never|neither|no\s+one|nobody|nothing)\b", src_lower))
        pt_neg = bool(re.search(r"\b(não|nunca|jamais|ninguém|nada|nem)\b", tgt_lower))

        if en_neg != pt_neg and len(src_lower.split()) <= 15:
            desc = (
                "Oração negativa no original traduzida como afirmativa."
                if en_neg
                else "Oração afirmativa no original traduzida com negação espúria."
            )
            issues.append(
                QAIssue(
                    check_type="polarity_inversion",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description=desc,
                    original_snippet=source[:50],
                    translated_snippet=target[:50],
                )
            )
            return 0.3, issues

        return 1.0, issues

    def _check_subject_shift(
        self, source: str, target: str, context: Any = None
    ) -> tuple[float, list[QAIssue]]:
        """Detecta troca de sujeito ou inversão de agentes de diálogo e ações."""
        issues: list[QAIssue] = []

        # Padrão clássico: "X asked Y" vs "Y perguntou a X" ou "disse Y"
        dialogue_pattern_en = re.compile(
            r"\b([A-Z][a-z]+)\s+(?:said|asked|replied|demanded|whispered)\b", re.UNICODE
        )
        dialogue_pattern_pt_before = re.compile(
            r"\b([A-Z][a-z]+)\s+(?:disse|perguntou|respondeu|indagou|sussurrou)\b", re.UNICODE
        )
        dialogue_pattern_pt_after = re.compile(
            r"\b(?:disse|perguntou|respondeu|indagou|sussurrou)\s+([A-Z][a-z]+)\b", re.UNICODE
        )

        match_en = dialogue_pattern_en.search(source)
        match_pt = dialogue_pattern_pt_before.search(target) or dialogue_pattern_pt_after.search(target)

        if match_en and match_pt:
            agent_en = match_en.group(1).lower()
            agent_pt = match_pt.group(1).lower()

            # Mapeia nomes equivalentes comuns
            if agent_en != agent_pt and not (agent_en.startswith(agent_pt) or agent_pt.startswith(agent_en)):
                issues.append(
                    QAIssue(
                        check_type="subject_shift",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description=f"Mudança de sujeito: o agente da fala no original era '{match_en.group(1)}', mas na tradução foi atribuído a '{match_pt.group(1)}'.",
                        original_snippet=match_en.group(0),
                        translated_snippet=match_pt.group(0),
                        suggested_fix=match_en.group(1),
                    )
                )
                return 0.3, issues

        # Detecção de troca de sujeito pronominal (He vs Ela / She vs Ele)
        if re.search(r"^\s*he\b", source, re.IGNORECASE) and re.search(r"^\s*ela\b", target, re.IGNORECASE):
            issues.append(
                QAIssue(
                    check_type="subject_shift",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description="Mudança de sujeito: pronome masculino 'He' traduzido como pronome feminino 'Ela'.",
                    original_snippet="He",
                    translated_snippet="Ela",
                    suggested_fix="Ele",
                )
            )
            return 0.4, issues

        if re.search(r"^\s*she\b", source, re.IGNORECASE) and re.search(r"^\s*ele\b", target, re.IGNORECASE):
            issues.append(
                QAIssue(
                    check_type="subject_shift",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description="Mudança de sujeito: pronome feminino 'She' traduzido como pronome masculino 'Ele'.",
                    original_snippet="She",
                    translated_snippet="Ele",
                    suggested_fix="Ela",
                )
            )
            return 0.4, issues

        return 1.0, issues

    def _check_intensity_loss(self, source: str, target: str) -> tuple[float, list[QAIssue]]:
        """Detecta atenuação excessiva de termos de alta intensidade emocional ou dramática."""
        issues: list[QAIssue] = []
        src_lower = source.lower()
        tgt_lower = target.lower()

        for strong_en, (weak_pt_list, suggested_pt) in self.INTENSITY_ATTENUATIONS.items():
            if re.search(rf"\b{re.escape(strong_en)}\b", src_lower):
                for weak_pt in weak_pt_list:
                    match = re.search(rf"\b(?:{weak_pt})\b", tgt_lower)
                    if match:
                        matched_snippet = match.group(0)
                        issues.append(
                            QAIssue(
                                check_type="intensity_loss",
                                severity=IssueSeverity.SUGGESTED_FIX,
                                description=f"Perda de intensidade dramática: '{strong_en}' atenuado para '{matched_snippet}'. Sugestão: '{suggested_pt}'.",
                                original_snippet=strong_en,
                                translated_snippet=matched_snippet,
                                suggested_fix=suggested_pt,
                            )
                        )
                        return 0.6, issues

        return 1.0, issues

    def _check_problematic_literal(self, source: str, target: str) -> tuple[float, list[QAIssue]]:
        """Detecta traduções literais impróprias e falsos cognatos clássicos."""
        issues: list[QAIssue] = []
        src_lower = source.lower()
        tgt_lower = target.lower()

        for en_trigger, (wrong_pt, correct_sugg) in self.FALSE_COGNATES.items():
            if re.search(rf"\b{re.escape(en_trigger)}\b", src_lower):
                match = re.search(rf"\b(?:{wrong_pt})\b", tgt_lower)
                if match:
                    matched_snippet = match.group(0)
                    issues.append(
                        QAIssue(
                            check_type="problematic_literal_translation",
                            severity=IssueSeverity.SUGGESTED_FIX,
                            description=f"Falso amigo/tradução literal detectada: '{en_trigger}' traduzido como '{matched_snippet}'. Esperado: '{correct_sugg}'.",
                            original_snippet=en_trigger,
                            translated_snippet=matched_snippet,
                            suggested_fix=correct_sugg,
                        )
                    )
                    return 0.5, issues

        return 1.0, issues

    def _check_relationship_shift(
        self, source: str, target: str, context: Any = None
    ) -> list[QAIssue]:
        """Verifica consistência de registro interpessoal com a memória de relacionamentos."""
        issues: list[QAIssue] = []
        if context is None:
            return issues

        # Checagem de quebra de formalidade quando o contexto exige reverência
        # Ex: "você/cara" em diálogo com nobres ou autoridades quando StyleBible define 'formal'
        tgt_lower = target.lower()
        style_bible = getattr(context, "style_bible", None)
        if style_bible:
            formality = getattr(style_bible, "formality_level", "").lower()
            if "formal" in formality or "muito formal" in formality:
                informal_markers = ["cara", "mano", "tipo assim", "né"]
                for marker in informal_markers:
                    if re.search(rf"\b{re.escape(marker)}\b", tgt_lower):
                        issues.append(
                            QAIssue(
                                check_type="relationship_shift",
                                severity=IssueSeverity.REVIEW_REQUIRED,
                                description=f"Inconsistência de registro: termo informal '{marker}' incompatível com o nível formal exigido na obra.",
                                original_snippet=source[:50],
                                translated_snippet=marker,
                            )
                        )
                        break

        return issues
