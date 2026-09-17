"""Implementação da Translation Memory (TM) para frases e termos recorrentes."""

from __future__ import annotations

import re
from typing import Any

from book_translator.errors import LockedTermError, MemoryError
from book_translator.logging import get_logger
from book_translator.memory.models import (
    ConflictReport,
    LockedVerificationResult,
    TranslationMemoryEntry,
)

logger = get_logger("memory.translation_memory")


def build_word_boundary_pattern(term: str) -> str:
    """Gera padrão regex com fronteira léxica adequada mesmo para termos com pontuação."""
    escaped = re.escape(term)
    prefix = r"\b" if term and term[0].isalnum() else r"(?<!\w)"
    suffix = r"\b" if term and term[-1].isalnum() else r"(?!\w)"
    return f"{prefix}{escaped}{suffix}"


class TranslationMemory:
    """Gerenciador de memórias de tradução com rastreabilidade, controle de status e travamento."""

    def __init__(self, project_id: str = "default", db: Any = None) -> None:
        self.project_id = str(project_id)
        self.db = db
        self._entries: dict[str, TranslationMemoryEntry] = {}

        if self.db:
            self.load_from_db()

    def load_from_db(self) -> None:
        """Carrega as entradas de TM persistidas no banco SQLite."""
        if not self.db:
            return
        entries = self.db.get_tm(self.project_id)
        for entry in entries:
            self._entries[entry.source_term.lower()] = entry

    def add_entry(
        self,
        entry: TranslationMemoryEntry,
        auto_save: bool = True,
        force: bool = False,
        changed_by: str = "user",
    ) -> None:
        """Registra uma tradução prévia com controle de termos travados e versionamento."""
        key = entry.source_term.lower()

        if not entry.history:
            entry.add_revision(
                field_name="created",
                old_val=None,
                new_val=entry.target_term,
                author=changed_by,
                reason="Entrada registrada na Translation Memory",
            )

        if key in self._entries:
            existing = self._entries[key]
            # Se estiver travado e tentar atribuir tradução divergente
            if existing.locked and existing.target_term != entry.target_term and not force:
                raise LockedTermError(
                    f"A tradução para '{existing.source_term}' está travada (locked=True) como "
                    f"'{existing.target_term}'. Para sobrescrever com '{entry.target_term}', "
                    f"informe force=True ou destrave a entrada previamente."
                )

            if existing.target_term != entry.target_term:
                existing.add_revision(
                    field_name="target_term",
                    old_val=existing.target_term,
                    new_val=entry.target_term,
                    author=changed_by,
                    reason=f"Atualização via TM (origem: {entry.origin})",
                )
                existing.target_term = entry.target_term
                existing.status = entry.status
                existing.confidence = entry.confidence
                existing.context = entry.context or existing.context

            existing.occurrences += 1
            entry_to_save = existing
        else:
            self._entries[key] = entry
            entry_to_save = entry

        if auto_save and self.db:
            self.db.save_tm_entry(self.project_id, entry_to_save)
            logger.info(
                f"TM: '{entry_to_save.source_term}' -> '{entry_to_save.target_term}' "
                f"(status={entry_to_save.status}, locked={entry_to_save.locked}) gravado."
            )

    def get_entry(self, source_term: str) -> TranslationMemoryEntry | None:
        """Recupera entrada da TM pelo termo/frase original."""
        return self._entries.get(source_term.lower())

    def update_entry(
        self,
        source_term: str,
        target_term: str | None = None,
        target: str | None = None,
        locked: bool | None = None,
        status: str | None = None,
        confidence: float | None = None,
        author: str = "user",
        changed_by: str | None = None,
        reason: str = "",
        force: bool = False,
        auto_save: bool = True,
    ) -> TranslationMemoryEntry:
        """Atualiza a entrada de TM registrando histórico de auditoria para cada alteração."""
        if target is not None and target_term is None:
            target_term = target
        if changed_by is not None and author == "user":
            author = changed_by

        entry = self.get_entry(source_term)
        if not entry:
            raise MemoryError(f"Entrada '{source_term}' não encontrada na Translation Memory.")

        if target_term is not None and target_term != entry.target_term:
            if entry.locked and not force:
                raise LockedTermError(
                    f"Alteração bloqueada no termo travado '{entry.source_term}'. "
                    f"Tradução atual: '{entry.target_term}'. Utilize force=True para sobrescrever."
                )
            entry.add_revision("target_term", entry.target_term, target_term, author, reason)
            entry.target_term = target_term

        if locked is not None and locked != entry.locked:
            entry.add_revision("locked", entry.locked, locked, author, reason)
            entry.locked = locked

        if status is not None and status != entry.status:
            entry.add_revision("status", entry.status, status, author, reason)
            entry.status = status

        if confidence is not None and confidence != entry.confidence:
            entry.add_revision("confidence", entry.confidence, confidence, author, reason)
            entry.confidence = confidence

        if auto_save and self.db:
            self.db.save_tm_entry(self.project_id, entry)
            self.db.record_memory_audit(
                project_id=self.project_id,
                memory_type="translation_memory",
                entry_id=entry.source_term,
                term_or_name=entry.source_term,
                field_changed="update",
                old_value="",
                new_value=entry.target_term,
                changed_by=author,
                reason=reason,
            )

        return entry

    def search(
        self,
        query: str,
        exact: bool = False,
        min_confidence: float = 0.0,
    ) -> list[TranslationMemoryEntry]:
        """Localiza entradas por correspondência exata ou parcial com filtros."""
        query_lower = query.lower().strip()
        if exact:
            entry = self.get_entry(query_lower)
            if entry and entry.confidence >= min_confidence:
                return [entry]
            return []

        results: list[TranslationMemoryEntry] = []
        for entry in self._entries.values():
            if entry.confidence < min_confidence:
                continue
            if query_lower in entry.source_term.lower() or entry.source_term.lower() in query_lower:
                results.append(entry)

        return results

    def verify_locked_terms(self, source_text: str, target_text: str) -> LockedVerificationResult:
        """Verifica se termos travados da TM presentes no original foram mantidos na tradução."""
        violations: list[dict[str, Any]] = []
        total_checked = 0

        for entry in self._entries.values():
            if not entry.locked:
                continue

            # Busca com limites de palavra inteligentes
            pattern = build_word_boundary_pattern(entry.source_term)
            for match in re.finditer(pattern, source_text, re.IGNORECASE):
                total_checked += 1
                target_pattern = build_word_boundary_pattern(entry.target_term)
                if not re.search(target_pattern, target_text, re.IGNORECASE):
                    violations.append(
                        {
                            "source_term": entry.source_term,
                            "expected_target": entry.target_term,
                            "source_snippet": source_text[
                                max(0, match.start() - 20) : min(len(source_text), match.end() + 20)
                            ],
                            "message": (
                                f"Termo travado de TM '{entry.source_term}' requer a tradução "
                                f"'{entry.target_term}', mas ela não foi encontrada no destino."
                            ),
                        }
                    )

        return LockedVerificationResult(
            is_compliant=len(violations) == 0,
            total_checked=total_checked,
            violations=violations,
        )

    def detect_conflicts(self) -> list[ConflictReport]:
        """Detecta entradas da TM com status conflitante ou traduções depreciadas."""
        conflicts: list[ConflictReport] = []
        # No nível individual de chave, cada chave tem uma entrada canônica.
        # Conflitos podem existir se houver termos idênticos com status rejeitado
        for entry in self._entries.values():
            if entry.status == "rejected" and entry.locked:
                conflicts.append(
                    ConflictReport(
                        memory_type="translation_memory",
                        term_or_name=entry.source_term,
                        existing_value=entry.target_term,
                        conflicting_value="rejected",
                        reason=(
                            f"Termo '{entry.source_term}' está marcado como "
                            f"'locked=True', mas status é 'rejected'."
                        ),
                        severity="error",
                    )
                )
        return conflicts

    def list_entries(self) -> list[TranslationMemoryEntry]:
        """Retorna todas as entradas da TM ordenadas por frequência de ocorrências."""
        return sorted(self._entries.values(), key=lambda e: e.occurrences, reverse=True)
