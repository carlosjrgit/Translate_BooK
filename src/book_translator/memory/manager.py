"""Gerenciador unificado de memórias da obra com persistência e verificação de conflitos."""

from __future__ import annotations

from typing import Any

from book_translator.memory.base import (
    CharacterEntry,
    ConflictReport,
    GlossaryEntry,
    LockedVerificationResult,
    MemoryManagerInterface,
    StoryContextSnapshot,
    StoryMemory,
    StyleBible,
    StyleViolation,
    TranslationMemoryEntry,
)
from book_translator.memory.character_memory import CharacterMemory
from book_translator.memory.glossary import Glossary
from book_translator.memory.translation_memory import TranslationMemory


class MemoryManager(MemoryManagerInterface):
    """Fachada unificada para controle de Characters, TM, Glossary, StyleBible, StoryMemory e auditoria."""

    def __init__(self, project_id: str = "default", db: Any = None) -> None:
        self.project_id = project_id
        self.db = db
        self.characters = CharacterMemory(project_id=project_id, db=db)
        self.glossary = Glossary(project_id=project_id, db=db)
        self.tm = TranslationMemory(project_id=project_id, db=db)
        self._style_bible: StyleBible = StyleBible()
        self.story: StoryMemory = StoryMemory(project_id=project_id)

        if self.db:
            sb = self.db.get_style_bible(project_id)
            if sb:
                self._style_bible = sb
            if hasattr(self.db, "get_story_memory"):
                loaded_story = self.db.get_story_memory(project_id)
                if loaded_story:
                    self.story = loaded_story

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

    # --- Story / Context Memory ---
    @property
    def story_memory(self) -> StoryMemory:
        """Acesso direto à StoryMemory atual."""
        return self.story

    def get_story_memory(self) -> StoryMemory:
        """Recupera a StoryMemory gerenciada."""
        return self.story

    def save_story_memory(self, story_memory: StoryMemory | None = None) -> None:
        """Salva a StoryMemory no banco do projeto."""
        if story_memory is not None:
            self.story = story_memory
        if self.db and hasattr(self.db, "save_story_memory"):
            self.db.save_story_memory(self.project_id, self.story)

    def get_story_context(
        self,
        chapter_id: str,
        unit_id: str,
        character_ids: list[str] | None = None,
        max_facts: int = 5,
        max_events: int = 3,
    ) -> StoryContextSnapshot:
        """Recupera o recorte cirúrgico de contexto da história para o segmento atual."""
        return self.story.get_scene_context_snapshot(
            chapter_id=chapter_id,
            unit_id=unit_id,
            character_ids=character_ids,
            max_facts=max_facts,
            max_events=max_events,
        )

    # --- QA de Estilo e Continuidade ---
    def validate_style(self, target_text: str, source_text: str = "") -> list[StyleViolation]:
        """Executa validação programática de aderência à Style Bible."""
        return self._style_bible.validate_text(target_text, source_text=source_text)

    def validate_character_continuity(
        self, character_id: str, chapter_id: str, text: str, order_index: int = 0
    ) -> list[Any]:
        """Valida continuidade de ações do personagem contra seu estado prévio."""
        return self.story.validate_character_continuity(
            character_id=character_id,
            chapter_id=chapter_id,
            text=text,
            order_index=order_index,
        )

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
        """Detecta conflitos internos e colisões entre o Glossário, TM, Style Bible e Story Memory."""
        conflicts: list[ConflictReport] = []
        conflicts.extend(self.characters.detect_conflicts())
        conflicts.extend(self.glossary.detect_conflicts())
        conflicts.extend(self.tm.detect_conflicts())
        conflicts.extend(self._style_bible.detect_contradictions())

        for anomaly in self.story.detect_contradictions():
            conflicts.append(
                ConflictReport(
                    memory_type="story_memory",
                    term_or_name=anomaly.entity_id or anomaly.anomaly_type,
                    existing_value=anomaly.conflicting_with or "",
                    conflicting_value=anomaly.evidence or "",
                    reason=anomaly.description,
                    severity=anomaly.severity,
                    details={
                        "anomaly_type": anomaly.anomaly_type,
                        "chapter_id": anomaly.chapter_id,
                        "order_index": anomaly.order_index,
                    },
                )
            )

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
