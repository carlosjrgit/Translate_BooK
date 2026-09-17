"""Implementação do BookAnalyzer para análise global e extração de entidades da obra."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from book_translator.analysis.alias_resolver import AliasResolver
from book_translator.analysis.base import AnalysisReport, AnalyzerInterface
from book_translator.analysis.models import (
    AnalyzedEntity,
    EntityInference,
    EntityType,
    Relationship,
)
from book_translator.analysis.ner.factory import get_ner_engine
from book_translator.analysis.ner.interface import NERInterface, RawEntityMention
from book_translator.analysis.relation_extractor import RelationExtractor
from book_translator.core.models import Document
from book_translator.logging import get_logger
from book_translator.memory.base import CharacterEntry, StyleBible

logger = get_logger("analysis.book_analyzer")

# Stopwords comuns em inglês para filtragem de termos frequentes
ENGLISH_STOPWORDS = {
    "the",
    "be",
    "to",
    "of",
    "and",
    "a",
    "in",
    "that",
    "have",
    "i",
    "it",
    "for",
    "not",
    "on",
    "with",
    "he",
    "as",
    "you",
    "do",
    "at",
    "this",
    "but",
    "his",
    "by",
    "from",
    "they",
    "we",
    "say",
    "her",
    "she",
    "or",
    "an",
    "will",
    "my",
    "one",
    "all",
    "would",
    "there",
    "their",
    "what",
    "so",
    "up",
    "out",
    "if",
    "about",
    "who",
    "get",
    "which",
    "go",
    "me",
    "when",
    "make",
    "can",
    "like",
    "time",
    "no",
    "just",
    "him",
    "know",
    "take",
    "people",
    "into",
    "year",
    "your",
    "good",
    "some",
    "could",
    "them",
    "see",
    "other",
    "than",
    "then",
    "now",
    "look",
    "only",
    "come",
    "its",
    "over",
    "think",
    "also",
    "back",
    "after",
    "use",
    "two",
    "how",
    "our",
    "work",
    "first",
    "well",
    "way",
    "even",
    "new",
    "want",
    "because",
    "any",
    "these",
    "give",
    "day",
    "most",
    "us",
}

PRONOUN_1ST_PERSON = re.compile(
    r"\b(i|me|my|mine|myself|we|us|our|ours|ourselves)\b", re.IGNORECASE
)
PRONOUN_3RD_PERSON = re.compile(
    r"\b(he|him|his|himself|she|her|hers|herself|they|them|their|theirs)\b", re.IGNORECASE
)


class BookAnalyzer(AnalyzerInterface):
    """Analisador global da obra responsável por identificar personagens, entidades e estilo."""

    def __init__(
        self,
        ner_engine: NERInterface | None = None,
        alias_resolver: AliasResolver | None = None,
        relation_extractor: RelationExtractor | None = None,
    ) -> None:
        self.ner_engine = ner_engine or get_ner_engine("heuristic")
        self.alias_resolver = alias_resolver or AliasResolver()
        self.relation_extractor = relation_extractor or RelationExtractor()

    def _infer_character_gender(self, entity: AnalyzedEntity) -> None:
        """Infere o gênero gramatical do personagem estritamente a partir de evidências."""
        # 1. Baseado em honorífico explícito (confiança 0.95)
        for hon in entity.honorifics:
            hon_lower = hon.lower().replace(".", "")
            if hon_lower in ("mr", "sir", "lord", "king", "prince", "duke", "baron", "count"):
                entity.gender = "masculine"
                entity.inferences.append(
                    EntityInference(
                        inference_type="gender",
                        value="masculine",
                        confidence=0.95,
                        evidence=f"Título honorífico masculino explícito '{hon}'",
                    )
                )
                return
            if hon_lower in ("mrs", "miss", "ms", "lady", "queen", "princess", "duchess", "dame"):
                entity.gender = "feminine"
                entity.inferences.append(
                    EntityInference(
                        inference_type="gender",
                        value="feminine",
                        confidence=0.95,
                        evidence=f"Título honorífico feminino explícito '{hon}'",
                    )
                )
                return

        # 2. Baseado em pronomes nos snippets imediatos das ocorrências
        he_count = 0
        she_count = 0
        he_evidences: list[str] = []
        she_evidences: list[str] = []

        for occ in entity.occurrences:
            snippet = occ.surrounding_snippet
            if re.search(r"\b(he|him|his)\b", snippet, re.IGNORECASE):
                he_count += 1
                he_evidences.append(snippet)
            if re.search(r"\b(she|her|hers)\b", snippet, re.IGNORECASE):
                she_count += 1
                she_evidences.append(snippet)

        if he_count > 0 and she_count == 0:
            entity.gender = "masculine"
            entity.inferences.append(
                EntityInference(
                    inference_type="gender",
                    value="masculine",
                    confidence=0.85,
                    evidence=he_evidences[0],
                )
            )
        elif she_count > 0 and he_count == 0:
            entity.gender = "feminine"
            entity.inferences.append(
                EntityInference(
                    inference_type="gender",
                    value="feminine",
                    confidence=0.85,
                    evidence=she_evidences[0],
                )
            )
        # 3. Baseado em primeiro nome próprio inequívoco
        name_tokens = [
            w
            for w in entity.canonical_name.split()
            if w.lower().replace(".", "")
            not in (
                "dr",
                "doctor",
                "mr",
                "mrs",
                "miss",
                "ms",
                "prof",
                "professor",
                "inspector",
            )
        ]
        if name_tokens:
            first_name = name_tokens[0].lower()
            masculine_names = {
                "john",
                "sherlock",
                "arthur",
                "robert",
                "jack",
                "william",
                "james",
                "george",
                "charles",
                "thomas",
                "edward",
                "henry",
                "joão",
                "pedro",
                "lucas",
                "carlos",
            }
            feminine_names = {
                "margaret",
                "mary",
                "elizabeth",
                "sarah",
                "jane",
                "emma",
                "alice",
                "maria",
                "ana",
                "helena",
            }
            if first_name in masculine_names:
                entity.gender = "masculine"
                entity.inferences.append(
                    EntityInference(
                        inference_type="gender",
                        value="masculine",
                        confidence=0.85,
                        evidence=f"Primeiro nome tipicamente masculino '{name_tokens[0]}'",
                    )
                )
                return
            if first_name in feminine_names:
                entity.gender = "feminine"
                entity.inferences.append(
                    EntityInference(
                        inference_type="gender",
                        value="feminine",
                        confidence=0.85,
                        evidence=f"Primeiro nome tipicamente feminino '{name_tokens[0]}'",
                    )
                )
                return

        # Informação ausente ou conflitante: NÃO INVENTA DADO!
        entity.gender = "unknown"

    def analyze(self, document: Document) -> AnalysisReport:
        """Executa a varredura e extração analítica global do documento."""
        logger.info(f"Iniciando varredura analítica da obra: '{document.title}'")

        all_mentions: list[RawEntityMention] = []
        all_relationships: list[Relationship] = []
        word_counts: Counter[str] = Counter()

        count_1st_person = 0
        count_3rd_person = 0

        # 1. Varre capítulos e unidades coletando menções e dados linguísticos
        for chapter in document.chapters:
            reading_units = chapter.get_reading_sequence()

            for unit in reading_units:
                text = getattr(unit, "normalized_text", getattr(unit, "raw_text", ""))
                if not text:
                    continue

                ctx = {"chapter_id": chapter.id, "unit_id": getattr(unit, "id", "")}

                # Executa NER na unidade
                mentions = self.ner_engine.extract_entities(text, context=ctx)
                all_mentions.extend(mentions)

                # Contabilização de termos frequentes
                tokens = re.findall(r"\b[a-zA-ZÀ-ÿ]{3,}\b", text.lower())
                for t in tokens:
                    if t not in ENGLISH_STOPWORDS:
                        word_counts[t] += 1

                # Contagem de pronomes na narrativa para estimativa do narrador
                # Não conta diálogos para não confundir fala em 1ª pessoa com narrador
                if getattr(unit, "__class__", None).__name__ == "Paragraph":
                    count_1st_person += len(PRONOUN_1ST_PERSON.findall(text))
                    count_3rd_person += len(PRONOUN_3RD_PERSON.findall(text))

        # 2. Resolução de aliases e desambiguação de homônimos
        entities: list[AnalyzedEntity] = self.alias_resolver.resolve(all_mentions)

        # 3. Inferência de gênero e refinamento para cada personagem
        for ent in entities:
            if ent.entity_type == EntityType.CHARACTER:
                self._infer_character_gender(ent)

        # 4. Extração de relações com evidências a partir das entidades identificadas
        for chapter in document.chapters:
            for unit in chapter.get_reading_sequence():
                text = getattr(unit, "normalized_text", getattr(unit, "raw_text", ""))
                if text:
                    rels = self.relation_extractor.extract_relations(
                        text=text,
                        entities=entities,
                        chapter_id=chapter.id,
                        unit_id=getattr(unit, "id", ""),
                    )
                    all_relationships.extend(rels)

        # 5. Estimativa de narrador predominante
        if count_1st_person > count_3rd_person * 0.7:
            predominant_narrator = "primeira pessoa"
        else:
            predominant_narrator = "terceira pessoa"

        # 6. Identificação de conceitos recorrentes (nomes de entidades frequentes)
        recurrent_concepts = [
            ent.canonical_name
            for ent in entities
            if ent.occurrences_count >= 2
            and ent.entity_type
            in (
                EntityType.ORGANIZATION,
                EntityType.LOCATION,
                EntityType.CONCEPT,
            )
        ]

        # 7. Formata listas de retrocompatibilidade
        detected_chars: list[dict[str, Any]] = [
            {
                "name": e.canonical_name,
                "aliases": e.aliases,
                "gender": e.gender,
                "occurrences": e.occurrences_count,
                "is_ambiguous": e.is_ambiguous,
            }
            for e in entities
            if e.entity_type == EntityType.CHARACTER
        ]

        detected_locs: list[str] = [
            e.canonical_name for e in entities if e.entity_type == EntityType.LOCATION
        ]

        detected_orgs: list[str] = [
            e.canonical_name for e in entities if e.entity_type == EntityType.ORGANIZATION
        ]

        report = AnalysisReport(
            entities=entities,
            relationships=all_relationships,
            recurrent_concepts=recurrent_concepts,
            detected_characters=detected_chars,
            detected_locations=detected_locs,
            detected_organizations=detected_orgs,
            frequent_terms=word_counts.most_common(20),
            predominant_narrator=predominant_narrator,
            formality_level="literário contemporâneo",
            estimated_tone="neutro/narrativo",
            metadata={
                "total_entities_found": len(entities),
                "total_relationships_found": len(all_relationships),
            },
        )

        logger.info(
            f"Análise concluída: {len(entities)} entidades encontradas, "
            f"{len(all_relationships)} relações detectadas. Narrador: '{predominant_narrator}'"
        )
        return report

    def populate_project_memory(
        self,
        report: AnalysisReport,
        db: Any,
        project_id: str,
    ) -> None:
        """Grava as entidades e descobertas da análise diretamente no banco do projeto."""
        for ent in report.entities:
            if ent.entity_type == EntityType.CHARACTER:
                char_entry = CharacterEntry(
                    id=ent.id,
                    name=ent.canonical_name,
                    aliases=ent.aliases,
                    gender=ent.gender,
                    occurrences=ent.occurrences_count,
                    first_appearance=ent.first_appearance_chapter,
                    notes=f"Identificado automaticamente. Honoríficos: {', '.join(ent.honorifics)}",
                )
                db.save_character(project_id, char_entry)
            else:
                from book_translator.core.models import Entity

                db_entity = Entity(
                    id=ent.id,
                    project_id=project_id,
                    name=ent.canonical_name,
                    entity_type=ent.entity_type.value,
                    occurrences=ent.occurrences_count,
                    metadata={
                        **ent.metadata,
                        "aliases": ent.aliases,
                        "first_seen_chapter_id": ent.first_appearance_chapter or None,
                    },
                )
                db.save_entity(db_entity)

        # Atualiza a bíblia de estilo com o narrador detectado
        sb = StyleBible(
            narrator=report.predominant_narrator,
            register=report.formality_level,
        )
        db.save_style_bible(project_id, sb)
