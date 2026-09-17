"""Consolidação e resolução determinística de aliases e homônimos."""

from __future__ import annotations

from collections import defaultdict

from book_translator.analysis.models import (
    AnalyzedEntity,
    EntityInference,
    EntityOccurrence,
    EntityType,
)
from book_translator.analysis.ner.interface import RawEntityMention


class AliasResolver:
    """Consolida menções variantes em entidades canônicas ou as marca como ambíguas."""

    def __init__(self) -> None:
        self._entity_counter = 1

    def _generate_entity_id(self, entity_type: EntityType) -> str:
        prefix = {
            EntityType.CHARACTER: "char",
            EntityType.LOCATION: "loc",
            EntityType.ORGANIZATION: "org",
        }.get(entity_type, "ent")
        eid = f"{prefix}_{self._entity_counter:04d}"
        self._entity_counter += 1
        return eid

    def resolve(
        self,
        mentions: list[RawEntityMention],
        full_text: str = "",
    ) -> list[AnalyzedEntity]:
        """Agrupa menções brutas, consolida aliases unívocos e sinaliza homônimos ambíguos."""
        if not mentions:
            return []

        # 1. Agrupa menções multi-palavras / completas primeiro como candidatas canônicas
        # Mapeia canonical_name -> AnalyzedEntity
        canonical_entities: dict[str, AnalyzedEntity] = {}

        # Mapeia token/sobrenome -> lista de canonical_names candidatos
        name_part_to_canonical: dict[str, set[str]] = defaultdict(set)

        # Filtra e organiza menções completas
        for m in mentions:
            text = m.text.strip()
            # Se tem honorífico ("Dr. John Watson"), o nome base é "John Watson"
            base_name = m.metadata.get("base_name", text)

            # Considera candidato canônico se tiver 2+ palavras, honorífico ou for local/organização
            words = base_name.split()
            if (
                len(words) >= 2
                or bool(m.honorific)
                or m.entity_type
                in (
                    EntityType.LOCATION,
                    EntityType.ORGANIZATION,
                )
            ):
                if base_name not in canonical_entities:
                    eid = self._generate_entity_id(m.entity_type)
                    canonical_entities[base_name] = AnalyzedEntity(
                        id=eid,
                        canonical_name=base_name,
                        entity_type=m.entity_type,
                        honorifics=[m.honorific] if m.honorific else [],
                    )
                else:
                    if m.honorific and m.honorific not in canonical_entities[base_name].honorifics:
                        canonical_entities[base_name].honorifics.append(m.honorific)

                # Mapeia partes do nome (ex: "Watson" e "John" para "John Watson")
                for w in words:
                    if len(w) > 2 and w[0].isupper():
                        name_part_to_canonical[w].add(base_name)

        # 2. Processa cada menção associando a ocorrência à entidade correspondente
        ambiguous_mentions: list[RawEntityMention] = []

        for m in mentions:
            text = m.text.strip()
            base_name = m.metadata.get("base_name", text)

            occ = EntityOccurrence(
                chapter_id=m.chapter_id,
                unit_id=m.unit_id,
                text=text,
                char_offset=m.start_char,
                surrounding_snippet=m.snippet,
                metadata=m.metadata,
            )

            # Caso A: Correspondência exata com entidade canônica existente
            if base_name in canonical_entities:
                canonical_entities[base_name].occurrences.append(occ)
                if text != base_name and text not in canonical_entities[base_name].aliases:
                    canonical_entities[base_name].aliases.append(text)
                continue

            # Caso B: Menção de uma palavra só (ex: "Watson" ou "Henderson")
            candidates = list(name_part_to_canonical.get(text, set()))

            if len(candidates) == 1:
                # Unívoco: consolida com a única entidade canônica existente
                c_name = candidates[0]
                ent = canonical_entities[c_name]
                ent.occurrences.append(occ)
                if text not in ent.aliases:
                    ent.aliases.append(text)
                ent.inferences.append(
                    EntityInference(
                        inference_type="alias_resolution",
                        value=f"Refere-se a {c_name}",
                        confidence=0.85,
                        evidence=m.snippet,
                        source_unit_id=m.unit_id,
                        source_chapter_id=m.chapter_id,
                    )
                )
            elif len(candidates) > 1:
                # Homônimo ambíguo: NÃO consolida cegamente
                ambiguous_mentions.append(m)
            else:
                # Não é candidato a alias de ninguém; cria entidade autônoma
                eid = self._generate_entity_id(m.entity_type)
                new_ent = AnalyzedEntity(
                    id=eid,
                    canonical_name=text,
                    entity_type=m.entity_type,
                    occurrences=[occ],
                )
                canonical_entities[text] = new_ent

        # 3. Trata as menções ambíguas criando registros sinalizados com is_ambiguous=True
        # Agrupa por texto ambíguo (ex: todas as menções de "Henderson")
        ambiguous_grouped: dict[str, list[RawEntityMention]] = defaultdict(list)
        for am in ambiguous_mentions:
            ambiguous_grouped[am.text.strip()].append(am)

        result_entities = list(canonical_entities.values())

        for amb_text, am_list in ambiguous_grouped.items():
            candidate_names = list(name_part_to_canonical.get(amb_text, set()))
            candidate_ids = [
                canonical_entities[c].id for c in candidate_names if c in canonical_entities
            ]

            amb_eid = self._generate_entity_id(EntityType.CHARACTER)
            amb_occurrences = [
                EntityOccurrence(
                    chapter_id=m.chapter_id,
                    unit_id=m.unit_id,
                    text=m.text,
                    char_offset=m.start_char,
                    surrounding_snippet=m.snippet,
                    metadata=m.metadata,
                )
                for m in am_list
            ]

            amb_inferences = [
                EntityInference(
                    inference_type="alias_ambiguity",
                    value=f"Ambiguidade detectada entre: {', '.join(candidate_names)}",
                    confidence=0.50,
                    evidence=m.snippet,
                    source_unit_id=m.unit_id,
                    source_chapter_id=m.chapter_id,
                )
                for m in am_list
            ]

            result_entities.append(
                AnalyzedEntity(
                    id=amb_eid,
                    canonical_name=amb_text,
                    entity_type=EntityType.CHARACTER,
                    occurrences=amb_occurrences,
                    inferences=amb_inferences,
                    is_ambiguous=True,
                    candidate_entity_ids=candidate_ids,
                    metadata={"ambiguity_note": "Homônimo com múltiplos candidatos."},
                )
            )

        return result_entities
