"""Módulo de Retrotradução (Backtranslation) como Evidência Auxiliar (Prompt 19).

Pipeline:
    EN original -> PT-BR traduzido -> EN reconstruído.

Compara EN original x EN reconstruído para coletar evidências auxiliares sobre:
- Omissões conceituais;
- Inversão de negações;
- Mudanças de sujeito gramatical.

Regras Fundamentais:
- A retrotradução NÃO é autoridade isolada (variações léxicas legítimas são documentadas como seguras).
- Não substitui automaticamente a tradução quando a volta diverge.
- Pode ser desativada em modo rápido (fast_mode=True).
"""

from __future__ import annotations

import re
from collections import Counter

from book_translator.logging import get_logger
from book_translator.qa.base import BacktranslationEvidence
from book_translator.translation.madlad import MadladTranslationEngine

logger = get_logger("qa.backtranslation")


def compute_token_f1(text_a: str, text_b: str) -> float:
    """Calcula a pontuação F1 de sobreposição de tokens entre dois textos."""
    tokens_a = re.findall(r"\b\w+\b", text_a.lower())
    tokens_b = re.findall(r"\b\w+\b", text_b.lower())

    if not tokens_a or not tokens_b:
        return 0.0

    counts_a = Counter(tokens_a)
    counts_b = Counter(tokens_b)

    common = sum((counts_a & counts_b).values())
    if common == 0:
        return 0.0

    precision = common / len(tokens_b)
    recall = common / len(tokens_a)
    return (2 * precision * recall) / (precision + recall)


def compute_char_chrf(reference: str, hypothesis: str, n: int = 4, beta: float = 2.0) -> float:
    """Calcula chrF aproximado (F-score de n-gramas de caracteres) entre dois textos."""
    ref = reference.strip().lower()
    hyp = hypothesis.strip().lower()

    if not ref or not hyp:
        return 0.0
    if ref == hyp:
        return 1.0

    ref_len = len(ref)
    hyp_len = len(hyp)

    ref_ngrams: Counter[str] = Counter()
    hyp_ngrams: Counter[str] = Counter()

    for i in range(1, n + 1):
        for j in range(ref_len - i + 1):
            ref_ngrams[ref[j : j + i]] += 1
        for j in range(hyp_len - i + 1):
            hyp_ngrams[hyp[j : j + i]] += 1

    common = sum((ref_ngrams & hyp_ngrams).values())
    total_hyp = sum(hyp_ngrams.values())
    total_ref = sum(ref_ngrams.values())

    if total_hyp == 0 or total_ref == 0 or common == 0:
        return 0.0

    precision = common / total_hyp
    recall = common / total_ref
    b2 = beta * beta
    return (1 + b2) * (precision * recall) / (b2 * precision + recall)


class BacktranslationVerifier:
    """Verificador de evidências auxiliares baseado em retrotradução EN -> PT-BR -> EN."""

    def __init__(
        self,
        engine: MadladTranslationEngine | None = None,
        enabled: bool = True,
    ) -> None:
        self.engine = engine or MadladTranslationEngine()
        self.enabled = enabled

    def verify(
        self,
        original_en: str,
        translated_pt: str,
        fast_mode: bool = False,
    ) -> BacktranslationEvidence:
        """Executa a retrotradução e analisa semelhanças e discrepâncias críticas."""
        orig = original_en.strip()
        trans = translated_pt.strip()

        # Bypass imediato em modo rápido ou quando explicitamente desativado
        if fast_mode or not self.enabled or not orig or not trans:
            return BacktranslationEvidence(
                reconstructed_en="",
                lexical_chrf=1.0,
                token_similarity=1.0,
                negation_preserved=True,
                subject_preserved=True,
                divergence_notes=["Retrotradução desativada ou ignorada em modo rápido."],
                has_potential_issue=False,
                metadata={"bypassed": True, "fast_mode": fast_mode},
            )

        # 1. Executa o ciclo de retrotradução: PT-BR -> EN
        reconstructed_en = self.engine.translate_text(
            trans,
            source_lang="pt",
            target_lang="en",
        )

        # 2. Métricas de similaridade textual e n-gramas
        token_f1 = compute_token_f1(orig, reconstructed_en)
        chrf = compute_char_chrf(orig, reconstructed_en)

        divergence_notes: list[str] = []
        has_potential_issue = False

        # 3. Análise de preservação de Negação
        orig_has_neg = bool(re.search(r"\b(not|never|neither|no\s+one|nobody|nothing|refused)\b", orig, re.I))
        recon_has_neg = bool(re.search(r"\b(not|never|neither|no\s+one|nobody|nothing|refused)\b", reconstructed_en, re.I))
        negation_preserved = (orig_has_neg == recon_has_neg)

        if not negation_preserved:
            has_potential_issue = True
            if orig_has_neg and not recon_has_neg:
                divergence_notes.append(
                    "Alerta de retrotradução: oração original continha negação, mas o texto reconstruído em inglês é afirmativo."
                )
            else:
                divergence_notes.append(
                    "Alerta de retrotradução: oração original era afirmativa, mas o texto reconstruído adquiriu negação espúria."
                )

        # 4. Análise de preservação de Sujeito Gramatical / Agente
        subject_preserved = True
        orig_words = orig.split()
        recon_words = reconstructed_en.split()

        if orig_words and recon_words:
            first_orig = orig_words[0].lower().strip(",.")
            first_recon = recon_words[0].lower().strip(",.")

            # Verifica pronomes de terceira pessoa he vs she
            if (first_orig == "he" and first_recon == "she") or (first_orig == "she" and first_recon == "he"):
                subject_preserved = False
                has_potential_issue = True
                divergence_notes.append(
                    f"Alerta de retrotradução: sujeito pronominal alternado de '{first_orig}' para '{first_recon}'."
                )

            # Verifica nomes próprios de agentes conhecidos
            agents = ["holmes", "watson", "lestrade", "margaret"]
            orig_agent = next((a for a in agents if a in orig.lower()), None)
            recon_agent = next((a for a in agents if a in reconstructed_en.lower()), None)

            if orig_agent and recon_agent and orig_agent != recon_agent:
                subject_preserved = False
                has_potential_issue = True
                divergence_notes.append(
                    f"Alerta de retrotradução: agente identificado '{orig_agent}' diverge do reconstruído '{recon_agent}'."
                )

        # 5. Análise de Omissão Severa
        if len(orig.split()) >= 6 and len(recon_words) < 0.45 * len(orig_words):
            has_potential_issue = True
            divergence_notes.append(
                f"Alerta de retrotradução: texto reconstruído perdeu mais de 50% do tamanho ({len(recon_words)} vs {len(orig_words)} palavras)."
            )

        # 6. Documentação de Falsos Positivos Comuns (Variações Léxicas Aceitáveis)
        if not has_potential_issue and token_f1 < 0.70:
            divergence_notes.append(
                "Nota: divergência léxica de superfície detectada na volta (sinônimos legítimos ou variação sintática permitida). Nenhuma anomalia crítica confirmada."
            )

        return BacktranslationEvidence(
            reconstructed_en=reconstructed_en,
            lexical_chrf=round(chrf, 4),
            token_similarity=round(token_f1, 4),
            negation_preserved=negation_preserved,
            subject_preserved=subject_preserved,
            divergence_notes=divergence_notes,
            has_potential_issue=has_potential_issue,
            metadata={
                "original_en": orig,
                "translated_pt": trans,
                "reconstructed_en": reconstructed_en,
            },
        )
