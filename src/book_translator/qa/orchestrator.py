"""Orquestrador Unificado de Controle de Qualidade (Deterministic + Semantic + Backtranslation).

Integra os três níveis de garantia editorial:
- QA Determinístico (regras estritas, números, datas, termos locked);
- Semantic QA (multi-sinal: embeddings, inversão, intensidade, falsos amigos, sujeitos);
- Backtranslation (evidência auxiliar de corroboração).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from book_translator.core.models import Segment
from book_translator.logging import get_logger
from book_translator.qa.backtranslation import BacktranslationVerifier
from book_translator.qa.base import (
    QAReport,
    UnifiedQAReport,
)
from book_translator.qa.deterministic import DeterministicQAEngine
from book_translator.qa.semantic import SemanticQAEngine

if TYPE_CHECKING:
    from book_translator.database.base import DatabaseInterface

logger = get_logger("qa.orchestrator")


class UnifiedQAOrchestrator:
    """Orquestra a validação holística cruzando sinais determinísticos e semânticos com retrotradução."""

    def __init__(
        self,
        deterministic_engine: DeterministicQAEngine | None = None,
        semantic_engine: SemanticQAEngine | None = None,
        backtranslation_verifier: BacktranslationVerifier | None = None,
        db: DatabaseInterface | None = None,
    ) -> None:
        self.deterministic_engine = deterministic_engine or DeterministicQAEngine()
        self.semantic_engine = semantic_engine or SemanticQAEngine()
        self.backtranslation_verifier = backtranslation_verifier or BacktranslationVerifier()
        self.db = db

    def evaluate(
        self,
        segment: Segment,
        original_text: str,
        translated_text: str,
        context: Any = None,
        glossary: list[Any] | None = None,
        characters: list[Any] | None = None,
        fast_mode: bool = False,
    ) -> UnifiedQAReport:
        """Executa a bateria integrada de validação de qualidade."""
        src = original_text.strip()
        tgt = translated_text.strip()

        # 1. QA Determinístico (Prompt 17)
        det_report: QAReport = self.deterministic_engine.evaluate(
            segment=segment,
            original_text=src,
            translated_text=tgt,
            context=context,
            glossary=glossary,
            characters=characters,
        )

        # 2. Semantic QA Multi-Sinal (Prompt 18)
        sem_result = self.semantic_engine.evaluate_semantic(
            segment=segment,
            original_text=src,
            translated_text=tgt,
            context=context,
        )

        # 3. Retrotradução como Evidência Auxiliar (Prompt 19)
        bt_evidence = self.backtranslation_verifier.verify(
            original_en=src,
            translated_pt=tgt,
            fast_mode=fast_mode,
        )

        # 4. Cruzamento de Sinais e Corroboração
        semantic_issues = list(sem_result.issues)

        # Se houver alerta de retrotradução confirmando problema semântico, anota corroboração
        if bt_evidence and bt_evidence.has_potential_issue:
            for issue in semantic_issues:
                if issue.check_type in ("polarity_inversion", "meaning_reversal") and not bt_evidence.negation_preserved:
                    issue.description += " [Confirmado por retrotradução auxiliar: negação perdida na volta]"
                elif issue.check_type == "subject_shift" and not bt_evidence.subject_preserved:
                    issue.description += " [Confirmado por retrotradução auxiliar: sujeito alterado na volta]"
                elif issue.check_type == "semantic_omission":
                    issue.description += " [Corroborado por encurtamento na retrotradução]"

        # Determina aprovação consolidada
        passed = det_report.passed and sem_result.passed

        unified_report = UnifiedQAReport(
            segment_id=segment.id,
            passed=passed,
            deterministic_issues=det_report.issues,
            semantic_issues=semantic_issues,
            backtranslation_evidence=bt_evidence,
            semantic_result=sem_result,
        )

        # Persistência opcional se houver banco ativo
        if self.db:
            try:
                # Salva todas as issues unificadas
                db_report = QAReport(
                    segment_id=segment.id,
                    passed=passed,
                    issues=unified_report.issues,
                )
                self.db.save_qa_report(db_report)
            except Exception as exc:
                logger.error(f"Falha ao persistir relatório unificado de QA para segmento #{segment.id}: {exc}")

        return unified_report
