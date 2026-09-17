"""Implementação da Character Memory para rastreamento de personagens e relações."""

from __future__ import annotations

from typing import Any

from book_translator.errors import MemoryConflictError, MemoryError
from book_translator.logging import get_logger
from book_translator.memory.models import CharacterEntry, ConflictReport

logger = get_logger("memory.character_memory")


class CharacterMemory:
    """Gerenciador de perfis de personagens, aliases, traços e auditoria de alterações."""

    def __init__(self, project_id: str = "default", db: Any = None) -> None:
        self.project_id = project_id
        self.db = db
        self._characters: dict[str, CharacterEntry] = {}
        self._name_to_id: dict[str, str] = {}
        self._alias_to_id: dict[str, set[str]] = {}

        if self.db:
            self.load_from_db()

    def load_from_db(self) -> None:
        """Carrega os personagens persistidos no banco de dados SQLite."""
        if not self.db:
            return
        entries = self.db.get_characters(self.project_id)
        for char in entries:
            self._characters[char.id] = char
            self._name_to_id[char.name.lower()] = char.id
            for alias in char.aliases:
                self._alias_to_id.setdefault(alias.lower(), set()).add(char.id)

    def add_character(
        self,
        character: CharacterEntry,
        auto_save: bool = True,
        changed_by: str = "user",
    ) -> None:
        """Adiciona ou atualiza um personagem com detecção rigorosa de conflitos."""
        name_lower = character.name.lower()

        # Verifica se outro personagem com ID diferente já possui este nome canônico
        existing_id = self._name_to_id.get(name_lower)
        if existing_id and existing_id != character.id:
            raise MemoryConflictError(
                f"Conflito na Character Memory: O nome canônico '{character.name}' "
                f"já pertence ao personagem '{existing_id}'."
            )

        # Adiciona e indexa
        self._characters[character.id] = character
        self._name_to_id[name_lower] = character.id

        for alias in character.aliases:
            self._alias_to_id.setdefault(alias.lower(), set()).add(character.id)

        if auto_save and self.db:
            self.db.save_character(self.project_id, character)
            self.db.record_memory_audit(
                project_id=self.project_id,
                memory_type="character",
                entry_id=character.id,
                term_or_name=character.name,
                field_changed="created",
                old_value="",
                new_value=character.name,
                changed_by=changed_by,
                reason="Criação de personagem",
            )
            logger.info(
                f"Personagem '{character.name}' ({character.id}) salvo na Character Memory."
            )

    def get_character(self, character_id: str) -> CharacterEntry | None:
        """Busca personagem pelo identificador permanente."""
        return self._characters.get(character_id)

    def get_by_name(self, name: str) -> CharacterEntry | None:
        """Busca personagem pelo nome canônico (case-insensitive)."""
        char_id = self._name_to_id.get(name.lower())
        return self._characters.get(char_id) if char_id else None

    def find_by_alias(self, alias: str) -> list[CharacterEntry]:
        """Localiza personagens que possuem o alias especificado."""
        matching_ids = self._alias_to_id.get(alias.lower(), set())
        # Também verifica correspondência com nome canônico
        canonical_id = self._name_to_id.get(alias.lower())
        if canonical_id:
            matching_ids = matching_ids | {canonical_id}

        return [self._characters[cid] for cid in matching_ids if cid in self._characters]

    def update_character(
        self,
        character_id: str,
        changes: dict[str, Any] | None = None,
        author: str = "user",
        changed_by: str | None = None,
        reason: str = "",
        auto_save: bool = True,
        **kwargs: Any,
    ) -> CharacterEntry:
        """Atualiza atributos do personagem registrando cada alteração no histórico de auditoria."""
        if changed_by is not None and author == "user":
            author = changed_by

        char = self._characters.get(character_id)
        if not char:
            char = self.get_by_name(character_id)
        if not char:
            raise MemoryError(f"Personagem '{character_id}' não encontrado na Character Memory.")

        all_changes = dict(changes or {})
        all_changes.update(kwargs)

        for field_name, new_value in all_changes.items():
            if not hasattr(char, field_name):
                continue
            old_value = getattr(char, field_name)
            if old_value != new_value:
                char.add_revision(
                    field_name=field_name,
                    old_val=old_value,
                    new_val=new_value,
                    author=author,
                    reason=reason,
                )
                setattr(char, field_name, new_value)

                if self.db:
                    self.db.record_memory_audit(
                        project_id=self.project_id,
                        memory_type="character",
                        entry_id=char.id,
                        term_or_name=char.name,
                        field_changed=field_name,
                        old_value=old_value,
                        new_value=new_value,
                        changed_by=author,
                        reason=reason,
                    )

        # Reindexa se nome ou aliases mudaram
        if "name" in all_changes or "aliases" in all_changes:
            self._reindex()

        if auto_save and self.db:
            self.db.save_character(self.project_id, char)

        return char

    def _reindex(self) -> None:
        """Reconstrói os índices de busca por nome e alias."""
        self._name_to_id.clear()
        self._alias_to_id.clear()
        for char in self._characters.values():
            self._name_to_id[char.name.lower()] = char.id
            for alias in char.aliases:
                self._alias_to_id.setdefault(alias.lower(), set()).add(char.id)

    def detect_conflicts(self) -> list[ConflictReport]:
        """Detecta homônimos ambíguos ou colisões de aliases entre personagens distintos."""
        conflicts: list[ConflictReport] = []

        for alias_lower, char_ids in self._alias_to_id.items():
            if len(char_ids) > 1:
                names = [self._characters[cid].name for cid in char_ids if cid in self._characters]
                conflicts.append(
                    ConflictReport(
                        memory_type="character",
                        term_or_name=alias_lower,
                        existing_value=names[0],
                        conflicting_value=names[1:],
                        reason=(
                            f"Alias ambíguo compartilhado por {len(char_ids)} personagens: "
                            f"{', '.join(names)}"
                        ),
                        severity="warning",
                        details={"character_ids": list(char_ids)},
                    )
                )

        return conflicts

    def list_characters(self) -> list[CharacterEntry]:
        """Retorna todos os personagens ordenados por número de ocorrências."""
        return sorted(self._characters.values(), key=lambda c: c.occurrences, reverse=True)
