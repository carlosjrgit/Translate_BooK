"""Gerenciador unificado de memórias da obra com persistência e verificação de conflitos."""

from __future__ import annotations

from typing import Any

from book_translator.memory.base import (
    CharacterEntry,
    ConflictReport,
    GlossaryEntry,
    LockedVerificationResult,
    MemoryManagerInterface,
    StyleBible,
    TranslationMemoryEntry,
)
from book_translator.memory.character_memory import CharacterMemory
from book_translator.memory.glossary import Glossary
from book_translator.memory.translation_memory import TranslationMemory


class MemoryManager(MemoryManagerInterface):
    """Fachada unificada para controle de Characters, TM, Glossary, StyleBible e auditoria."""

    def __init__(self, project_id: str = "default", db: Any = None) -> None:
        self.project_id = project_id
        self.db = db
        self.characters = CharacterMemory(project_id=project_id, db=db)
        self.glossary = Glossary(project_id=project_id, db=db)
        self.tm = TranslationMemory(project_id=project_id, db=db)
        self._style_bible: StyleBible = StyleBible()

        if self.db:
            sb = self.db.get_style_bible(project_id)
            if sb:
                self._style_bible = sb

    # --- Character Memory ---
    def add_character(self, character: CharacterEntry) -> None:
        self.characters.add_character(character)

    def get_character(self, character_id: str) -> CharacterEntry | None:
        return self.characters.get_character(character_id)

    # --- Translation Memory ---
    def add_tm_entry(self, entry: TranslationMemoryEntry, force: bool = False) -> None:
        self.tm.add_entry(entry, force=force)

    def get_tm_entry(self, source_term: str) -> TranslationMemoryEntry | None:
        return self.tm.get_entry(source_term)

    # --- Glossary ---
    def add_glossary_entry(self, entry: GlossaryEntry, force: bool = False) -> None:
        self.glossary.add_entry(entry, force=force)

    def get_glossary_entry(self, source_term: str) -> GlossaryEntry | None:
        return self.glossary.get_entry(source_term)

    @property
    def translation_memory(self) -> TranslationMemory:
        """Alias para o gerenciador de memória de tradução."""
        return self.tm

    # --- Style Bible ---
    @property
    def style_bible(self) -> StyleBible:
        """Acesso direto à StyleBible atual."""
        return self._style_bible

    def get_style_bible(self) -> StyleBible:
        return self._style_bible

    def save_style_bible(self, style_bible: StyleBible) -> None:
        self._style_bible = style_bible
        if self.db:
            self.db.save_style_bible(self.project_id, style_bible)

    def set_style_bible(self, style_bible: StyleBible) -> None:
        """Alias para save_style_bible."""
        self.save_style_bible(style_bible)

    # --- Verificações Cruzadas e Conformidade ---
    def verify_all_locked_terms(
        self, source_text: str, target_text: str
    ) -> LockedVerificationResult:
        """Verifica a conformidade de todos os termos travados (Glossário e TM simultaneamente)."""
        glossary_res = self.glossary.verify_locked_terms(source_text, target_text)
        tm_res = self.tm.verify_locked_terms(source_text, target_text)

        all_violations = glossary_res.violations + tm_res.violations
        total_checked = glossary_res.total_checked + tm_res.total_checked

        return LockedVerificationResult(
            is_compliant=len(all_violations) == 0,
            total_checked=total_checked,
            violations=all_violations,
        )

    def detect_all_conflicts(self) -> list[ConflictReport]:
        """Detecta conflitos internos e colisões entre o Glossário e a Translation Memory."""
        conflicts: list[ConflictReport] = []
        conflicts.extend(self.characters.detect_conflicts())
        conflicts.extend(self.glossary.detect_conflicts())
        conflicts.extend(self.tm.detect_conflicts())

        # Detecção de colisões cruzadas entre Glossário e TM:
        # Se um termo tem traduções conflitantes estabelecidas em ambas as memórias
        for source_key, gloss_entry in self.glossary._entries.items():
            tm_entry = self.tm.get_entry(source_key)
            if tm_entry and gloss_entry.target_term.lower() != tm_entry.target_term.lower():
                conflicts.append(
                    ConflictReport(
                        memory_type="cross_memory_conflict",
                        term_or_name=gloss_entry.source_term,
                        existing_value=(
                            f"Glossary: '{gloss_entry.target_term}' (locked={gloss_entry.locked})"
                        ),
                        conflicting_value=(
                            f"TM: '{tm_entry.target_term}' (locked={tm_entry.locked})"
                        ),
                        reason=(
                            f"Tradução divergente para '{gloss_entry.source_term}' "
                            f"entre Glossário e TM: '{gloss_entry.target_term}' "
                            f"vs '{tm_entry.target_term}'."
                        ),
                        severity="error" if (gloss_entry.locked or tm_entry.locked) else "warning",
                        details={
                            "glossary_locked": gloss_entry.locked,
                            "tm_locked": tm_entry.locked,
                        },
                    )
                )

        return conflicts

    def get_audit_history(
        self,
        entry_id: str | None = None,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recupera registros de auditoria persistidos no banco de dados."""
        if self.db and hasattr(self.db, "get_memory_audit_log"):
            return self.db.get_memory_audit_log(
                project_id=self.project_id,
                entry_id=entry_id,
                memory_type=memory_type,
            )
        return []
