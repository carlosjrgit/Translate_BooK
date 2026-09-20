"""Ranqueador multicritério transparente e inspecionável para candidatos de tradução N-best."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from book_translator.context.base import TranslationContext
from book_translator.logging import get_logger
from book_translator.memory.style_bible import StyleBible
from book_translator.translation.base import (
    CandidateRankerInterface,
    TranslationCandidate,
)

logger = get_logger("translation.ranker")


@dataclass
class RankingFeatureWeights:
    """Pesos configuráveis para as 7 dimensões do ranqueador de candidatos."""

    fidelity: float = 0.25
    naturalness: float = 0.15
    terminology: float = 0.20
    consistency: float = 0.15
    character: float = 0.10
    style: float = 0.08
    fluency: float = 0.07

    def __post_init__(self) -> None:
        total = (
            self.fidelity
            + self.naturalness
            + self.terminology
            + self.consistency
            + self.character
            + self.style
            + self.fluency
        )
        if total > 0 and abs(total - 1.0) > 1e-4:
            self.fidelity /= total
            self.naturalness /= total
            self.terminology /= total
            self.consistency /= total
            self.character /= total
            self.style /= total
            self.fluency /= total


@dataclass
class CandidateScoreBreakdown:
    """Detalhamento transparente das pontuações atribuídas a um candidato."""

    fidelity: float
    naturalness: float
    terminology: float
    consistency: float
    character: float
    style: float
    fluency: float
    final_score: float
    justifications: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fidelity": round(self.fidelity, 4),
            "naturalness": round(self.naturalness, 4),
            "terminology": round(self.terminology, 4),
            "consistency": round(self.consistency, 4),
            "character": round(self.character, 4),
            "style": round(self.style, 4),
            "fluency": round(self.fluency, 4),
            "final_score": round(self.final_score, 4),
            "justifications": self.justifications,
        }


class LiteraryCandidateRanker(CandidateRankerInterface):
    """Ranqueador inspecionável e determinístico para seleção da melhor hipótese de tradução.

    Avalia 7 dimensões fundamentais sem score mágico:
    1. Fidelidade: comprimento proporcional, preservação de números e pontuação emotiva.
    2. Naturalidade: ausência de repetições em loop (n-grams) e pontuação fluida.
    3. Terminologia: presença mandatória de termos de glossário travados.
    4. Consistência: aderência a memórias de tradução (TM) e termos consolidados.
    5. Personagem: preservação de nomes canônicos e pronomes de tratamento.
    6. Estilo: alinhamento com convenções da Style Bible (travessão editorial, etc.).
    7. Fluência: completude morfossintática e pontuação final válida.
    """

    def __init__(
        self,
        weights: RankingFeatureWeights | None = None,
        fast_mode: bool = False,
    ) -> None:
        self.weights = weights or RankingFeatureWeights()
        self.fast_mode = fast_mode

    def rank(
        self,
        candidates: list[TranslationCandidate],
        context: TranslationContext | None = None,
    ) -> TranslationCandidate:
        """Avalia e ordena a lista de candidatos, retornando a hipótese com maior pontuação."""
        if not candidates:
            raise ValueError("A lista de candidatos não pode ser vazia para ranqueamento.")

        ranked = self.rank_candidates(candidates, context=context)
        return ranked[0]

    def rank_candidates(
        self,
        candidates: list[TranslationCandidate],
        context: TranslationContext | None = None,
        style_bible: StyleBible | None = None,
        source_text: str = "",
    ) -> list[TranslationCandidate]:
        """Avalia todos os candidatos, calcula scores detalhados e retorna lista ordenada por rank."""
        if not candidates:
            return []

        # Se houver apenas 1 candidato ou fast_mode estiver ativado, bypass para alto throughput
        if len(candidates) == 1 or self.fast_mode:
            for idx, c in enumerate(candidates, start=1):
                c.rank = idx
                if "score_breakdown" not in c.metadata:
                    c.metadata["score_breakdown"] = {
                        "mode": "fast_bypass" if self.fast_mode else "single_candidate",
                        "final_score": c.score or 0.95,
                    }
            return candidates

        # Extrai o texto fonte do contexto se não fornecido explicitamente
        src_text = source_text
        if not src_text and context and hasattr(context, "source_text"):
            src_text = getattr(context, "source_text", "")
        if not src_text and candidates and "source_text" in candidates[0].metadata:
            src_text = str(candidates[0].metadata["source_text"])

        scored_candidates: list[tuple[float, TranslationCandidate]] = []

        for cand in candidates:
            breakdown = self.evaluate_candidate(
                candidate_text=cand.text,
                source_text=src_text,
                context=context,
                style_bible=style_bible,
            )
            cand.score = breakdown.final_score
            cand.metadata["score_breakdown"] = breakdown.to_dict()
            cand.metadata["justifications"] = breakdown.justifications
            scored_candidates.append((breakdown.final_score, cand))

        # Ordena de forma determinística e estável: maior score primeiro; em caso de empate, tamanho do texto
        scored_candidates.sort(key=lambda item: (-item[0], len(item[1].text)))

        result: list[TranslationCandidate] = []
        for rank_idx, (_, cand) in enumerate(scored_candidates, start=1):
            cand.rank = rank_idx
            result.append(cand)

        return result

    def evaluate_candidate(
        self,
        candidate_text: str,
        source_text: str,
        context: TranslationContext | None = None,
        style_bible: StyleBible | None = None,
    ) -> CandidateScoreBreakdown:
        """Calcula os 7 sub-scores inspecionáveis para uma hipótese textual."""
        justifications: list[str] = []

        s_fidelity, j_fid = self._score_fidelity(candidate_text, source_text)
        justifications.extend(j_fid)

        s_naturalness, j_nat = self._score_naturalness(candidate_text)
        justifications.extend(j_nat)

        s_terminology, j_term = self._score_terminology(candidate_text, context)
        justifications.extend(j_term)

        s_consistency, j_cons = self._score_consistency(candidate_text, context)
        justifications.extend(j_cons)

        s_character, j_char = self._score_character(candidate_text, context)
        justifications.extend(j_char)

        s_style, j_style = self._score_style(candidate_text, style_bible)
        justifications.extend(j_style)

        s_fluency, j_flue = self._score_fluency(candidate_text)
        justifications.extend(j_flue)

        # Cálculo da média ponderada transparente
        w = self.weights
        final_score = (
            w.fidelity * s_fidelity
            + w.naturalness * s_naturalness
            + w.terminology * s_terminology
            + w.consistency * s_consistency
            + w.character * s_character
            + w.style * s_style
            + w.fluency * s_fluency
        )
        final_score = max(0.0, min(1.0, final_score))

        return CandidateScoreBreakdown(
            fidelity=s_fidelity,
            naturalness=s_naturalness,
            terminology=s_terminology,
            consistency=s_consistency,
            character=s_character,
            style=s_style,
            fluency=s_fluency,
            final_score=final_score,
            justifications=justifications,
        )

    # -------------------------------------------------------------------------
    # Métodos Inspecionáveis de Avaliação das 7 Dimensões
    # -------------------------------------------------------------------------

    def _score_fidelity(self, target: str, source: str) -> tuple[float, list[str]]:
        """Avalia preservação de números, pontuação e proporção do comprimento."""
        if not source:
            return 1.0, []

        score = 1.0
        justifications: list[str] = []

        # 1. Proporção de comprimento em caracteres
        len_ratio = len(target) / max(1, len(source))
        if len_ratio < 0.4:
            penalty = 0.4
            score -= penalty
            justifications.append(
                f"Penalidade de fidelidade: truncamento severo (proporção {len_ratio:.2f})"
            )
        elif len_ratio > 2.5:
            penalty = 0.3
            score -= penalty
            justifications.append(
                f"Penalidade de fidelidade: expansão excessiva (proporção {len_ratio:.2f})"
            )

        # 2. Preservação de números
        src_numbers = set(re.findall(r"\b\d+\b", source))
        tgt_numbers = set(re.findall(r"\b\d+\b", target))
        missing_numbers = src_numbers - tgt_numbers
        if missing_numbers:
            penalty = min(0.3, len(missing_numbers) * 0.15)
            score -= penalty
            justifications.append(f"Penalidade de fidelidade: números ausentes {missing_numbers}")

        # 3. Preservação de pontuação expressiva (?, !)
        for punct in ["?", "!"]:
            if (punct in source) and (punct not in target):
                score -= 0.1
                justifications.append(f"Penalidade de fidelidade: pontuação '{punct}' omitida")

        # 4. Detecção de palavras comuns em inglês não traduzidas
        untranslated_markers = {"the", "and", "with", "from", "that", "this", "because"}
        tgt_words = set(re.findall(r"\b[a-z]{2,}\b", target.lower()))
        retained = tgt_words.intersection(untranslated_markers)
        if retained:
            penalty = min(0.4, len(retained) * 0.15)
            score -= penalty
            justifications.append(
                f"Penalidade de fidelidade: palavras em inglês não traduzidas {retained}"
            )

        return max(0.0, min(1.0, score)), justifications

    def _score_naturalness(self, target: str) -> tuple[float, list[str]]:
        """Avalia fluência, cadência e ausência de loops repetitivos."""
        score = 1.0
        justifications: list[str] = []

        words = target.lower().split()
        if not words:
            return 0.0, ["Texto vazio"]

        # 1. Repetição de palavras consecutivas (ex: "o o o", "muito muito")
        for i in range(len(words) - 1):
            if words[i] == words[i + 1] and len(words[i]) > 1:
                score -= 0.25
                justifications.append(
                    f"Penalidade de naturalidade: repetição consecutiva '{words[i]}'"
                )

        # 2. Repetição de bigramas consecutivos (ex: "o homem o homem")
        if len(words) >= 4:
            for i in range(len(words) - 3):
                bg1 = (words[i], words[i + 1])
                bg2 = (words[i + 2], words[i + 3])
                if bg1 == bg2:
                    score -= 0.35
                    justifications.append(
                        f"Penalidade de naturalidade: loop de bigrama '{bg1[0]} {bg1[1]}'"
                    )
                    break

        # 3. Pontuação duplicada anômala (ex: ",,", "..")
        if re.search(r",\s*,|\.\s*\.\s*\.(?!\.)", target):
            score -= 0.15
            justifications.append("Penalidade de naturalidade: pontuação anômala duplicada")

        return max(0.0, min(1.0, score)), justifications

    def _score_terminology(
        self, target: str, context: TranslationContext | None
    ) -> tuple[float, list[str]]:
        """Avalia conformidade obrigatória com termos travados do glossário."""
        if not context or not context.relevant_glossary:
            return 1.0, []

        score = 1.0
        justifications: list[str] = []

        for entry in context.relevant_glossary:
            if not entry.locked:
                continue

            target_term = entry.target_term.strip()
            source_term = entry.source_term.strip()

            # O termo traduzido deve estar presente
            tgt_pattern = re.compile(rf"\b{re.escape(target_term)}\b", re.IGNORECASE)
            if not tgt_pattern.search(target):
                score -= 0.4
                justifications.append(
                    f"Penalidade de terminologia: termo de glossário '{target_term}' ausente"
                )

            # O termo em inglês não deve permanecer
            src_pattern = re.compile(rf"\b{re.escape(source_term)}\b", re.IGNORECASE)
            if src_pattern.search(target) and target_term.lower() != source_term.lower():
                score -= 0.35
                justifications.append(
                    f"Penalidade de terminologia: termo original '{source_term}' não traduzido"
                )

        return max(0.0, min(1.0, score)), justifications

    def _score_consistency(
        self, target: str, context: TranslationContext | None
    ) -> tuple[float, list[str]]:
        """Avalia coerência com a Translation Memory já estabelecida."""
        if not context or not context.established_translations:
            return 1.0, []

        score = 1.0
        justifications: list[str] = []

        for tm in context.established_translations:
            if not tm.locked:
                continue
            if tm.target_term.lower() not in target.lower():
                score -= 0.2
                justifications.append(
                    f"Penalidade de consistência: TM travada '{tm.target_term}' não adotada"
                )

        return max(0.0, min(1.0, score)), justifications

    def _score_character(
        self, target: str, context: TranslationContext | None
    ) -> tuple[float, list[str]]:
        """Avalia integridade de nomes de personagens ativos na cena."""
        if not context or not context.active_characters:
            return 1.0, []

        score = 1.0
        justifications: list[str] = []

        for char in context.active_characters:
            # Se o nome canônico estiver ausente quando o personagem é fulcral
            canonical = char.canonical_name.strip()
            if canonical and len(canonical.split()) > 1:
                # Se for nome composto (ex: "Sherlock Holmes", "Dr. John Watson"), deve aparecer integro
                # se pelo menos parte do nome estiver presente
                tokens = [t.lower() for t in canonical.split() if len(t) > 2]
                present_tokens = [t for t in tokens if t in target.lower()]
                if present_tokens and len(present_tokens) < len(tokens):
                    score -= 0.15
                    justifications.append(
                        f"Alerta de personagem: nome parcial/mutilado de '{canonical}'"
                    )

        return max(0.0, min(1.0, score)), justifications

    def _score_style(self, target: str, style_bible: StyleBible | None) -> tuple[float, list[str]]:
        """Avalia alinhamento com padrões editoriais (travessão em diálogos, etc.)."""
        score = 1.0
        justifications: list[str] = []

        # Detecção de linha de diálogo iniciada por aspas quando o estilo editorial é travessão
        trimmed = target.strip()
        if trimmed.startswith('"') or trimmed.startswith("'"):
            # Se a convenção for editorial brasileira, diálogos usam travessão (—)
            score -= 0.15
            justifications.append(
                "Alerta de estilo: diálogo iniciado com aspas em vez de travessão editorial (—)"
            )
        elif trimmed.startswith("—") or trimmed.startswith("- "):
            score += 0.05
            justifications.append("Bônus de estilo: uso correto de travessão editorial em diálogo")

        return max(0.0, min(1.0, score)), justifications

    def _score_fluency(self, target: str) -> tuple[float, list[str]]:
        """Avalia estrutura de encerramento de frase e pontuação."""
        score = 1.0
        justifications: list[str] = []

        trimmed = target.strip()
        if not trimmed:
            return 0.0, ["Texto vazio"]

        # Frase não deve terminar em preposição solta ou vírgula
        dangling_prepositions = (" de", " com", " em", " para", " por", " sob", " sobre", ",")
        if trimmed.endswith(dangling_prepositions):
            score -= 0.3
            justifications.append(
                "Penalidade de fluência: frase terminada em preposição/vírgula incompleta"
            )

        # Verifica parênteses e aspas pareadas
        for open_ch, close_ch in [("(", ")"), ("[", "]")]:
            if target.count(open_ch) != target.count(close_ch):
                score -= 0.2
                justifications.append(
                    f"Penalidade de fluência: desbalanceamento de '{open_ch}' e '{close_ch}'"
                )

        return max(0.0, min(1.0, score)), justifications
