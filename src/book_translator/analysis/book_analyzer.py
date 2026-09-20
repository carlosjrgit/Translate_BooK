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
from book_translator.memory.base import CharacterEntry, StoryMemory, StyleBible, StyleEvidence

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
        evidences_1st_person: list[str] = []
        evidences_3rd_person: list[str] = []

        count_past_tense = 0
        count_present_tense = 0
        evidences_past: list[str] = []
        evidences_present: list[str] = []

        count_em_dash = 0
        count_quotes = 0
        evidences_dialogue: list[str] = []

        evidences_profanity: list[str] = []
        evidences_titles: list[str] = []
        evidences_treatment: list[str] = []

        re_past = re.compile(
            r"\b(was|were|had|said|looked|went|walked|came|saw|thought|asked|replied|took|felt)\b",
            re.IGNORECASE,
        )
        re_present = re.compile(
            r"\b(is|are|has|says|looks|goes|walks|comes|sees|thinks|asks|replies|takes|feels)\b",
            re.IGNORECASE,
        )
        re_titles = re.compile(
            r"\b(Lord|Lady|Sir|Count|Countess|Duke|Duchess|Baron|Baroness|King|Queen|Prince|Princess|Captain|Doctor|Professor)\b",
            re.IGNORECASE,
        )
        re_profanity = re.compile(
            r"\b(fuck|shit|damn|bastard|bitch|asshole)\b",
            re.IGNORECASE,
        )
        re_treatment = re.compile(
            r"\b(Mr\.|Mrs\.|Miss|Ms\.|Sir|Lord|Lady|you|thou|thee)\b",
            re.IGNORECASE,
        )

        chapters_meta: list[dict[str, Any]] = []

        # 1. Varre capítulos e unidades coletando menções e dados linguísticos
        for chapter in document.chapters:
            reading_units = chapter.get_reading_sequence()
            chapters_meta.append(
                {
                    "chapter_id": chapter.id,
                    "title": chapter.title or chapter.id,
                    "order_index": getattr(chapter, "order", getattr(chapter, "order_index", 0)),
                    "units_count": len(reading_units),
                }
            )

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

                # Contagem de pronomes e tempos na narrativa para estimativa de narrador/estilo
                if getattr(unit, "__class__", None).__name__ == "Paragraph":
                    m1 = PRONOUN_1ST_PERSON.findall(text)
                    m3 = PRONOUN_3RD_PERSON.findall(text)
                    count_1st_person += len(m1)
                    count_3rd_person += len(m3)
                    if m1 and len(evidences_1st_person) < 5:
                        evidences_1st_person.append(text[:120])
                    if m3 and len(evidences_3rd_person) < 5:
                        evidences_3rd_person.append(text[:120])

                    past_m = re_past.findall(text)
                    pres_m = re_present.findall(text)
                    count_past_tense += len(past_m)
                    count_present_tense += len(pres_m)
                    if past_m and len(evidences_past) < 5:
                        evidences_past.append(text[:120])
                    if pres_m and len(evidences_present) < 5:
                        evidences_present.append(text[:120])

                # Padrão de diálogo
                trimmed = text.strip()
                if trimmed.startswith(("—", "–", "- ")):
                    count_em_dash += 1
                    if len(evidences_dialogue) < 5:
                        evidences_dialogue.append(trimmed[:120])
                elif trimmed.startswith('"'):
                    count_quotes += 1
                    if len(evidences_dialogue) < 5:
                        evidences_dialogue.append(trimmed[:120])

                prof_m = re_profanity.findall(text)
                if prof_m and len(evidences_profanity) < 5:
                    evidences_profanity.append(text[:120])

                title_m = re_titles.findall(text)
                if title_m and len(evidences_titles) < 5:
                    evidences_titles.append(text[:120])

                treat_m = re_treatment.findall(text)
                if treat_m and len(evidences_treatment) < 5:
                    evidences_treatment.append(text[:120])

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

        # 5. Estimativa de narrador predominante e pessoa narrativa
        if count_1st_person > count_3rd_person * 0.7:
            predominant_narrator = "primeira pessoa"
            narrative_person = "1ª pessoa"
            narrator_evidences = evidences_1st_person or evidences_3rd_person
            narrator_conf = min(
                0.95, 0.6 + (count_1st_person / (count_1st_person + count_3rd_person + 1)) * 0.35
            )
        else:
            predominant_narrator = "terceira pessoa"
            narrative_person = "3ª pessoa"
            narrator_evidences = evidences_3rd_person or evidences_1st_person
            narrator_conf = min(
                0.95, 0.6 + (count_3rd_person / (count_1st_person + count_3rd_person + 1)) * 0.35
            )

        # Tempo predominante
        if count_past_tense >= count_present_tense:
            predominant_tense = "passado"
            tense_evidences = evidences_past
            tense_conf = min(
                0.95, 0.6 + (count_past_tense / (count_past_tense + count_present_tense + 1)) * 0.35
            )
        else:
            predominant_tense = "presente"
            tense_evidences = evidences_present
            tense_conf = min(
                0.95,
                0.6 + (count_present_tense / (count_past_tense + count_present_tense + 1)) * 0.35,
            )

        # Padrão de diálogo
        dialogue_style = "travessão"  # Padrão editorial brasileiro
        dialogue_evs = evidences_dialogue or ["Convenção editorial padrão PT-BR com travessão"]

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
                "chapters_meta": chapters_meta,
                "style_dimensions": {
                    "narrator": predominant_narrator,
                    "narrator_conf": narrator_conf,
                    "narrator_evidences": narrator_evidences,
                    "narrative_person": narrative_person,
                    "predominant_tense": predominant_tense,
                    "tense_conf": tense_conf,
                    "tense_evidences": tense_evidences,
                    "dialogue_style": dialogue_style,
                    "dialogue_evidences": dialogue_evs,
                    "profanity_evidences": evidences_profanity,
                    "titles_evidences": evidences_titles,
                    "treatment_evidences": evidences_treatment,
                },
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
        document: Document | None = None,
    ) -> None:
        """Grava as entidades, StyleBible e StoryMemory diretamente no banco do projeto."""
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

        # 1. Popula StyleBible estruturada com evidências
        style_dims = report.metadata.get("style_dimensions", {})
        sb = StyleBible(
            narrator=report.predominant_narrator,
            narrative_person=style_dims.get("narrative_person", "terceira pessoa"),
            predominant_tense=style_dims.get("predominant_tense", "passado"),
            formality_level=report.formality_level,
            dialogue_style=style_dims.get("dialogue_style", "travessão"),
            profanity_handling="preservar intensidade do original",
            treatment_forms="você",
            editorial_punctuation="editorial brasileiro",
            title_treatment="traduzir",
            internal_conventions=[
                "diálogos com travessão editorial",
                "preservação de itálicos de ênfase",
            ],
            register=report.formality_level,
            project_id=str(project_id),
        )

        # Registra regras com suas respectivas evidências textuais
        if "narrator_evidences" in style_dims and style_dims["narrator_evidences"]:
            sb.set_rule(
                "narrator",
                report.predominant_narrator,
                confidence=style_dims.get("narrator_conf", 0.9),
                evidences=[StyleEvidence(snippet=s) for s in style_dims["narrator_evidences"]],
            )
            sb.set_rule(
                "narrative_person",
                style_dims.get("narrative_person", "3ª pessoa"),
                confidence=style_dims.get("narrator_conf", 0.9),
                evidences=[StyleEvidence(snippet=s) for s in style_dims["narrator_evidences"]],
            )

        if "tense_evidences" in style_dims and style_dims["tense_evidences"]:
            sb.set_rule(
                "predominant_tense",
                style_dims.get("predominant_tense", "passado"),
                confidence=style_dims.get("tense_conf", 0.9),
                evidences=[StyleEvidence(snippet=s) for s in style_dims["tense_evidences"]],
            )

        if "dialogue_evidences" in style_dims and style_dims["dialogue_evidences"]:
            sb.set_rule(
                "dialogue_style",
                style_dims.get("dialogue_style", "travessão"),
                confidence=0.9,
                evidences=[StyleEvidence(snippet=s) for s in style_dims["dialogue_evidences"]],
            )

        if "profanity_evidences" in style_dims and style_dims["profanity_evidences"]:
            sb.set_rule(
                "profanity_handling",
                "preservar intensidade do original",
                confidence=1.0,
                evidences=[StyleEvidence(snippet=s) for s in style_dims["profanity_evidences"]],
            )

        if "treatment_evidences" in style_dims and style_dims["treatment_evidences"]:
            sb.set_rule(
                "treatment_forms",
                "você",
                confidence=0.85,
                evidences=[StyleEvidence(snippet=s) for s in style_dims["treatment_evidences"]],
            )

        if "titles_evidences" in style_dims and style_dims["titles_evidences"]:
            sb.set_rule(
                "title_treatment",
                "traduzir",
                confidence=0.9,
                evidences=[StyleEvidence(snippet=s) for s in style_dims["titles_evidences"]],
            )

        db.save_style_bible(project_id, sb)

        # 2. Popula StoryMemory com resumos, estados e fatos
        sm = StoryMemory(project_id=str(project_id))

        # Cria resumos preliminares por capítulo
        chapters_info = report.metadata.get("chapters_meta", [])
        if document and document.chapters:
            for ch in document.chapters:
                units = ch.get_reading_sequence()
                chars_here = [
                    e.canonical_name
                    for e in report.entities
                    if e.entity_type == EntityType.CHARACTER
                    and any(occ.chapter_id == ch.id for occ in e.occurrences)
                ]
                sm.record_summary(
                    unit_id=ch.id,
                    summary_text=f"Capítulo '{ch.title or ch.id}' ({len(units)} unidades de leitura).",
                    title=ch.title or ch.id,
                    unit_type="chapter",
                    characters_present=chars_here,
                    order_index=getattr(ch, "order", getattr(ch, "order_index", 0)),
                )
        elif chapters_info:
            for cm in chapters_info:
                cid = cm["chapter_id"]
                sm.record_summary(
                    unit_id=cid,
                    summary_text=f"Capítulo '{cm['title']}' ({cm['units_count']} unidades de leitura).",
                    title=cm["title"],
                    unit_type="chapter",
                    order_index=cm["order_index"],
                )

        # Registra estados iniciais dos personagens identificados
        for ent in report.entities:
            if ent.entity_type == EntityType.CHARACTER:
                first_ch = ent.first_appearance_chapter or (
                    chapters_info[0]["chapter_id"] if chapters_info else "ch_001"
                )
                sm.record_character_state(
                    character_id=ent.id,
                    chapter_id=first_ch,
                    alive_status="alive",
                    role_or_title=", ".join(ent.honorifics) if ent.honorifics else "",
                    metadata={"canonical_name": ent.canonical_name, "gender": ent.gender},
                )

        # Registra relações extraídas
        for rel in report.relationships:
            sm.record_relationship(
                source_character_id=rel.source_entity_id,
                target_character_id=rel.target_entity_id,
                relation_type=rel.relation_type,
                description=rel.evidence,
                chapter_id=rel.chapter_id,
                evidence=rel.evidence,
                confidence=rel.confidence,
            )

        # Registra conceitos recorrentes como fatos persistentes
        for concept in report.recurrent_concepts:
            sm.record_fact(
                statement=f"Conceito ou elemento recorrente no universo da obra: '{concept}'.",
                category="lore",
                confidence=0.9,
            )

        if hasattr(db, "save_story_memory"):
            db.save_story_memory(project_id, sm)
