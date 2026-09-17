"""Implementação do Glossário de conceitos, termos e organizações."""

from __future__ import annotations

import re
from typing import Any

from book_translator.errors import LockedTermError, MemoryError
from book_translator.logging import get_logger
from book_translator.memory.models import (
    ConflictReport,
    GlossaryEntry,
    LockedVerificationResult,
)

logger = get_logger("memory.glossary")


def build_word_boundary_pattern(term: str) -> str:
    """Gera padrão regex com fronteira léxica adequada mesmo para termos com pontuação."""
    escaped = re.escape(term)
    prefix = r"\b" if term and term[0].isalnum() else r"(?<!\w)"
    suffix = r"\b" if term and term[-1].isalnum() else r"(?!\w)"
    return f"{prefix}{escaped}{suffix}"


class Glossary:
    """Gerenciador de termos técnicos, conceitos e entidades da obra com controle de travamento."""

    def __init__(self, project_id: str = "default", db: Any = None) -> None:
        self.project_id = str(project_id)
        self.db = db
        self._entries: dict[str, GlossaryEntry] = {}
        self._alias_to_term: dict[str, str] = {}

        if self.db:
            self.load_from_db()

    def load_from_db(self) -> None:
        """Carrega os termos do glossário persistidos no SQLite."""
        if not self.db:
            return
        entries = self.db.get_glossary(self.project_id)
        for entry in entries:
            key = entry.source_term.lower()
            self._entries[key] = entry
            for alias in entry.aliases:
                self._alias_to_term[alias.lower()] = key

    def add_entry(
        self,
        entry: GlossaryEntry,
        auto_save: bool = True,
        force: bool = False,
        changed_by: str = "user",
    ) -> None:
        """Adiciona ou atualiza uma entrada com verificação estrita de termos travados."""
        key = entry.source_term.lower()

        if key in self._entries:
            existing = self._entries[key]
            # Verifica se o termo está travado e tenta mudar a tradução
            if existing.locked and existing.target_term != entry.target_term and not force:
                raise LockedTermError(
                    f"O termo '{existing.source_term}' está travado (locked=True) com a tradução "
                    f"'{existing.target_term}'. Para alterar para '{entry.target_term}', "
                    f"utilize 'force=True' ou destrave o termo previamente."
                )

            # Se não estiver travado ou force=True, registra auditoria de alteração
            if existing.target_term != entry.target_term:
                existing.add_revision(
                    field_name="target_term",
                    old_val=existing.target_term,
                    new_val=entry.target_term,
                    author=changed_by,
                    reason="Atualização de tradução no glossário",
                )
                existing.target_term = entry.target_term

            # Mescla aliases
            for al in entry.aliases:
                if al not in existing.aliases:
                    existing.aliases.append(al)

            entry_to_save = existing
        else:
            self._entries[key] = entry
            entry_to_save = entry

        # Atualiza índice de aliases
        for alias in entry_to_save.aliases:
            alias_lower = alias.lower()
            # Detecta se o alias já está vinculado a outro termo diferente
            existing_term = self._alias_to_term.get(alias_lower)
            if existing_term and existing_term != key:
                logger.warning(
                    f"Colisão de alias no Glossário: '{alias}' já mapeava para '{existing_term}'."
                )
            self._alias_to_term[alias_lower] = key

        if auto_save and self.db:
            self.db.save_glossary_entry(self.project_id, entry_to_save)
            if changed_by:
                self.db.record_memory_audit(
                    project_id=self.project_id,
                    memory_type="glossary",
                    entry_id=entry_to_save.source_term,
                    term_or_name=entry_to_save.source_term,
                    field_changed="created",
                    old_value="",
                    new_value=entry_to_save.target_term,
                    changed_by=changed_by,
                    reason="Registro de termo no glossário",
                )
            logger.info(
                f"Termo '{entry_to_save.source_term}' -> '{entry_to_save.target_term}' "
                f"(locked={entry_to_save.locked}) salvo no Glossário."
            )

    def get_entry(self, term: str) -> GlossaryEntry | None:
        """Busca entrada pelo termo original ou alias."""
        term_lower = term.lower()
        if term_lower in self._entries:
            return self._entries[term_lower]

        canonical_key = self._alias_to_term.get(term_lower)
        if canonical_key and canonical_key in self._entries:
            return self._entries[canonical_key]

        return None

    def update_entry(
        self,
        source_term: str,
        target_term: str | None = None,
        locked: bool | None = None,
        author: str = "user",
        reason: str = "",
        force: bool = False,
        auto_save: bool = True,
        **other_fields: Any,
    ) -> GlossaryEntry:
        """Atualiza campos de uma entrada, exigindo force para alterar termos travados."""
        entry = self.get_entry(source_term)
        if not entry:
            raise MemoryError(f"Termo '{source_term}' não encontrado no Glossário.")

        if target_term is not None and target_term != entry.target_term:
            if entry.locked and not force:
                raise LockedTermError(
                    f"Tentativa de alteração não autorizada no termo travado "
                    f"'{entry.source_term}'. Tradução atual: '{entry.target_term}'. "
                    f"Para forçar a alteração, informe force=True."
                )
            entry.add_revision("target_term", entry.target_term, target_term, author, reason)
            entry.target_term = target_term

        if locked is not None and locked != entry.locked:
            entry.add_revision("locked", entry.locked, locked, author, reason)
            entry.locked = locked

        for f_name, f_val in other_fields.items():
            if hasattr(entry, f_name):
                old_val = getattr(entry, f_name)
                if old_val != f_val:
                    entry.add_revision(f_name, old_val, f_val, author, reason)
                    setattr(entry, f_name, f_val)

        if auto_save and self.db:
            self.db.save_glossary_entry(self.project_id, entry)
            self.db.record_memory_audit(
                project_id=self.project_id,
                memory_type="glossary",
                entry_id=entry.source_term,
                term_or_name=entry.source_term,
                field_changed="multiple" if len(other_fields) > 1 else "update",
                old_value="",
                new_value=entry.target_term,
                changed_by=author,
                reason=reason,
            )

        return entry

    def find_matching_terms(self, text: str) -> list[tuple[GlossaryEntry, int, int]]:
        """Identifica ocorrências de termos do glossário sem substituição cega.

        Utiliza fronteiras léxicas de palavras e respeita estritamente case_sensitive.
        Retorna tuplas (GlossaryEntry, start_char, end_char).
        """
        if not text:
            return []

        matches: list[tuple[GlossaryEntry, int, int]] = []

        for entry in self._entries.values():
            terms_to_search = [entry.source_term] + entry.aliases
            for term in terms_to_search:
                flags = 0 if entry.case_sensitive else re.IGNORECASE
                pattern = build_word_boundary_pattern(term)
                for match in re.finditer(pattern, text, flags):
                    matches.append((entry, match.start(), match.end()))

        # Ordena pelo offset inicial no texto
        return sorted(matches, key=lambda m: m[1])

    def verify_locked_terms(self, source_text: str, target_text: str) -> LockedVerificationResult:
        """Valida se termos travados presentes no original foram preservados na tradução."""
        matches = self.find_matching_terms(source_text)
        locked_matches = [m for m in matches if m[0].locked]

        violations: list[dict[str, Any]] = []

        for entry, start, end in locked_matches:
            target_pattern = build_word_boundary_pattern(entry.target_term)
            flags = 0 if entry.case_sensitive else re.IGNORECASE
            if not re.search(target_pattern, target_text, flags):
                violations.append(
                    {
                        "source_term": entry.source_term,
                        "expected_target": entry.target_term,
                        "source_snippet": source_text[
                            max(0, start - 20) : min(len(source_text), end + 20)
                        ],
                        "message": (
                            f"Termo travado '{entry.source_term}' requer a tradução "
                            f"'{entry.target_term}', mas ela não foi encontrada no texto traduzido."
                        ),
                    }
                )

        return LockedVerificationResult(
            is_compliant=len(violations) == 0,
            total_checked=len(locked_matches),
            violations=violations,
        )

    def detect_conflicts(self) -> list[ConflictReport]:
        """Detecta termos com traduções divergentes ou aliases colidentes."""
        conflicts: list[ConflictReport] = []

        # Verifica aliases que colidem com termos canônicos distintos
        for alias, canonical_key in self._alias_to_term.items():
            if alias in self._entries and alias != canonical_key:
                conflicts.append(
                    ConflictReport(
                        memory_type="glossary",
                        term_or_name=alias,
                        existing_value=canonical_key,
                        conflicting_value=self._entries[alias].target_term,
                        reason=f"O alias '{alias}' coincide com o termo canônico '{alias}'.",
                        severity="warning",
                    )
                )

        return conflicts

    def list_entries(self) -> list[GlossaryEntry]:
        """Retorna todas as entradas do glossário ordenadas alfabeticamente."""
        return sorted(self._entries.values(), key=lambda e: e.source_term.lower())
