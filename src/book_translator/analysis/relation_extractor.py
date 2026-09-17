"""Extração heurística de relações entre personagens com base em evidências textuais."""

from __future__ import annotations

import re

from book_translator.analysis.models import AnalyzedEntity, Relationship

# Relações interpessoais e familiares suportadas
RELATION_NOUNS = (
    "mother",
    "father",
    "brother",
    "sister",
    "wife",
    "husband",
    "son",
    "daughter",
    "uncle",
    "aunt",
    "cousin",
    "friend",
    "assistant",
    "servant",
    "partner",
    "mãe",
    "pai",
    "irmão",
    "irmã",
    "esposa",
    "marido",
    "filho",
    "filha",
    "tio",
    "tia",
    "primo",
    "prima",
    "amigo",
    "amiga",
    "assistente",
    "servo",
    "serva",
    "sócio",
    "sócia",
)

REL_NOUNS_STR = "|".join(re.escape(r) for r in RELATION_NOUNS)
HONORIFIC_STR = (
    r"(?:Lady|Lord|Sir|Dame|Dr\.|Doctor|Mr\.|Mrs\.|Miss|Ms\.|Prof\.|Professor|Inspector)"
)

# Padrões com correspondência estrita de maiúsculas para nomes próprios:
# 1. Possessivo: "Arthur's mother Margaret stood..." ou "Arthur's mother Lady Margaret"
POSSESSIVE_PATTERN = (
    rf"\b([A-ZÀ-Ý][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)?)'s\s+"
    rf"(?i:({REL_NOUNS_STR}))\s*,?\s+"
    rf"((?:{HONORIFIC_STR}\s+)?[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)?)\b"
)

# 2. Inverso: "Watson, the faithful friend of Holmes, smiled..."
INVERSE_PATTERN = (
    rf"\b((?:{HONORIFIC_STR}\s+)?[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)?)\s*,?\s+"
    rf"(?i:(?:the\s+|a\s+|o\s+)?(?:[a-zà-ÿ]+\s+)?({REL_NOUNS_STR})\s+(?:of|de|da|do))\s+"
    rf"((?:{HONORIFIC_STR}\s+)?[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)?)\b"
)

RELATION_PATTERNS = [
    (POSSESSIVE_PATTERN, "possessive"),
    (INVERSE_PATTERN, "inverse"),
]


class RelationExtractor:
    """Extrai relações familiares e interpessoais com base em evidências explícitas."""

    def __init__(self) -> None:
        self._compiled_patterns = [(re.compile(p), ptype) for p, ptype in RELATION_PATTERNS]

    def _resolve_entity(
        self, raw_name: str, name_to_entity: dict[str, AnalyzedEntity]
    ) -> AnalyzedEntity | None:
        """Resolve o nome ou alias na lista de entidades conhecidas."""
        norm = raw_name.strip()
        if not norm:
            return None

        # 1. Correspondência direta pelo nome ou alias
        if norm.lower() in name_to_entity:
            return name_to_entity[norm.lower()]

        # 2. Tenta remover honorífico caso presente
        stripped = re.sub(rf"^{HONORIFIC_STR}\s+", "", norm, flags=re.IGNORECASE).strip()
        if stripped.lower() in name_to_entity:
            return name_to_entity[stripped.lower()]

        # 3. Tenta tokens individuais
        for tok in reversed(norm.split()):
            if tok.lower() in name_to_entity:
                return name_to_entity[tok.lower()]

        return None

    def extract_relations(
        self,
        text: str,
        entities: list[AnalyzedEntity],
        chapter_id: str = "",
        unit_id: str = "",
    ) -> list[Relationship]:
        """Varre o texto procurando relações entre as entidades conhecidas."""
        if not text or not entities:
            return []

        # Índice de nomes e aliases para rápida localização da entidade correspondente
        name_to_entity: dict[str, AnalyzedEntity] = {}
        for ent in entities:
            name_to_entity[ent.canonical_name.lower()] = ent
            for alias in ent.aliases:
                name_to_entity[alias.lower()] = ent

        relationships: list[Relationship] = []

        for regex, pattern_type in self._compiled_patterns:
            for match in regex.finditer(text):
                full_snippet = text[
                    max(0, match.start() - 20) : min(len(text), match.end() + 20)
                ].strip()

                if pattern_type == "possessive":
                    # Padrão: PersonA's [relation] PersonB
                    # ex: Arthur's mother Margaret -> Margaret is mother_of Arthur
                    p1_name = match.group(1).strip()
                    rel_word = match.group(2).lower().strip()
                    p2_name = match.group(3).strip()

                    ent1 = self._resolve_entity(p1_name, name_to_entity)
                    ent2 = self._resolve_entity(p2_name, name_to_entity)

                    if ent1 and ent2 and ent1.id != ent2.id:
                        relationships.append(
                            Relationship(
                                source_entity_id=ent2.id,
                                target_entity_id=ent1.id,
                                source_name=ent2.canonical_name,
                                target_name=ent1.canonical_name,
                                relation_type=f"{rel_word}_of",
                                confidence=0.90,
                                evidence=full_snippet,
                                source_unit_id=unit_id,
                                source_chapter_id=chapter_id,
                            )
                        )

                elif pattern_type == "inverse":
                    # Padrão: PersonB, [relation] of PersonA
                    # ex: Watson, friend of Holmes -> Watson is friend_of Holmes
                    p2_name = match.group(1).strip()
                    rel_word = match.group(2).lower().strip()
                    p1_name = match.group(3).strip()

                    ent2 = self._resolve_entity(p2_name, name_to_entity)
                    ent1 = self._resolve_entity(p1_name, name_to_entity)

                    if ent1 and ent2 and ent1.id != ent2.id:
                        relationships.append(
                            Relationship(
                                source_entity_id=ent2.id,
                                target_entity_id=ent1.id,
                                source_name=ent2.canonical_name,
                                target_name=ent1.canonical_name,
                                relation_type=f"{rel_word}_of",
                                confidence=0.90,
                                evidence=full_snippet,
                                source_unit_id=unit_id,
                                source_chapter_id=chapter_id,
                            )
                        )

        return relationships
