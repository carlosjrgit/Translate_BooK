"""Motor de Auditoria Global de Consistência da Obra (Global Consistency Pass).

Executa auditoria holística pós-tradução cobrindo 15 dimensões:
- personagens, aliases, nomes, pronomes, tratamentos, locais, organizações,
  terminologia, títulos, cronologia, estilo, diálogos, Glossary, TM e Style Bible.

Classifica os achados rigorosamente em:
- SAFE FIX: correções determinísticas e seguras (ex: termo travado com variante não autorizada, espaçamento de travessão)
- SUGGESTED FIX: padronizações prováveis que demandam confirmação
- REVIEW REQUIRED: diferenças potencialmente intencionais (ex: alteração de tratamento, nuances dramáticas)
  que NUNCA devem ser uniformizadas automaticamente.
"""

from __future__ import annotations

import re

from book_translator.consistency.base import (
    ConsistencyCheckerInterface,
    ConsistencyConflict,
    ConsistencyFixAuditRecord,
    GlobalConsistencyReport,
    OccurrenceLocation,
)
from book_translator.core.models import Chapter, Document, Segment
from book_translator.logging import get_logger
from book_translator.memory.base import MemoryManagerInterface
from book_translator.memory.style_bible import NOBILITY_TITLES
from book_translator.qa.base import IssueSeverity

logger = get_logger("consistency.checker")

# Padrões comuns para formas de tratamento em português
TREATMENT_PATTERNS = {
    "você": re.compile(r"\b(você|vocês|voce|voces)\b", re.IGNORECASE),
    "tu": re.compile(r"\b(tu|te|ti|contigo)\b", re.IGNORECASE),
    "o senhor/a senhora": re.compile(
        r"\b(o\s+senhor|a\s+senhora|ao\s+senhor|à\s+senhora|do\s+senhor|da\s+senhora|os\s+senhores|as\s+senhoras)\b",
        re.IGNORECASE,
    ),
    "vossa excelência/senhoria": re.compile(
        r"\b(vossa\s+excelência|vossa\s+senhoria|vossa\s+alteza|vossa\s+majestade)\b",
        re.IGNORECASE,
    ),
}

# Pronomes em português por gênero
PRONOUNS_MASCULINE = re.compile(r"\b(ele|eles|dele|deles|nele|neles|o\s+mesmo)\b", re.IGNORECASE)
PRONOUNS_FEMININE = re.compile(r"\b(ela|elas|dela|delas|nela|nelas|a\s+mesma)\b", re.IGNORECASE)


class GlobalConsistencyChecker(ConsistencyCheckerInterface):
    """Auditor global de consistência para a obra traduzida completa."""

    def __init__(self) -> None:
        pass

    def audit(
        self,
        document: Document,
        memory_manager: MemoryManagerInterface,
    ) -> GlobalConsistencyReport:
        """Examina toda a obra traduzida buscando divergências nas 15 dimensões."""
        conflicts: list[ConsistencyConflict] = []
        all_segments = self._collect_all_segments(document)
        total_segments = len(all_segments)
        total_chapters = len(document.chapters)

        logger.info(
            f"Iniciando Consistency Pass Global: {total_chapters} capítulos, {total_segments} segmentos"
        )

        # 1. Terminologia & Glossário (Dimensões: terminologia, Glossary)
        conflicts.extend(self._audit_terminology_and_glossary(all_segments, memory_manager))

        # 2. Translation Memory (Dimensão: Translation Memory)
        conflicts.extend(self._audit_translation_memory(all_segments, memory_manager))

        # 3. Personagens, Aliases e Nomes (Dimensões: personagens, aliases, nomes)
        conflicts.extend(self._audit_characters_and_aliases(all_segments, memory_manager))

        # 4. Tratamentos (Dimensão: tratamentos)
        conflicts.extend(self._audit_treatment_forms(all_segments, memory_manager))

        # 5. Pronomes e Gênero (Dimensão: pronomes)
        conflicts.extend(self._audit_pronouns_and_gender(all_segments, memory_manager))

        # 6. Locais e Organizações (Dimensões: locais, organizações)
        conflicts.extend(self._audit_locations_and_organizations(all_segments, memory_manager))

        # 7. Títulos e Honoríficos (Dimensão: títulos)
        conflicts.extend(self._audit_titles(all_segments, memory_manager))

        # 8. Cronologia e Fatos da História (Dimensão: cronologia)
        conflicts.extend(self._audit_chronology_and_story(all_segments, memory_manager))

        # 9. Estilo e Diálogos (Dimensões: estilo, diálogos, Style Bible)
        conflicts.extend(self._audit_style_and_dialogues(all_segments, memory_manager))

        report = GlobalConsistencyReport(
            total_segments_audited=total_segments,
            total_chapters_audited=total_chapters,
            conflicts=conflicts,
            metadata={
                "project_id": getattr(memory_manager, "project_id", "default"),
                "total_conflicts": len(conflicts),
            },
        )

        logger.info(
            f"Consistency Pass Global concluído: {len(conflicts)} conflitos "
            f"({len(report.safe_fixes)} SAFE FIX, {len(report.suggested_fixes)} SUGGESTED FIX, "
            f"{len(report.review_required)} REVIEW REQUIRED)"
        )

        return report

    def apply_safe_fixes(
        self,
        document: Document,
        report: GlobalConsistencyReport,
    ) -> list[ConsistencyFixAuditRecord]:
        """Aplica apenas correções categorizadas como SAFE FIX de forma auditável e reversível.

        NUNCA altera conflitos marcados como REVIEW_REQUIRED ou SUGGESTED_FIX.
        """
        applied_records: list[ConsistencyFixAuditRecord] = []

        for conflict in report.safe_fixes:
            std_target = conflict.suggested_standardization
            if not std_target:
                continue

            # Itera sobre variantes que diferem da padronização sugerida
            for variant_text, occurrences in conflict.variants.items():
                if variant_text.strip().lower() == std_target.strip().lower():
                    continue

                for loc in occurrences:
                    segment = self._find_segment(document, loc.segment_id)
                    if not segment or not segment.translated_text:
                        continue

                    old_text = segment.translated_text
                    new_text = self._replace_variant_safely(
                        old_text, variant_text, std_target, conflict.category
                    )

                    if new_text != old_text:
                        segment.translated_text = new_text
                        segment.revisions.append(
                            f"ConsistencyPass [SAFE FIX]: {conflict.category} '{variant_text}' -> '{std_target}'"
                        )

                        record = ConsistencyFixAuditRecord(
                            conflict_id=conflict.id,
                            category=conflict.category,
                            chapter_id=loc.chapter_id,
                            segment_id=loc.segment_id,
                            original_target_text=old_text,
                            modified_target_text=new_text,
                            applied_rule=conflict.message,
                            reversible=True,
                            undone=False,
                            details={
                                "term_or_entity": conflict.term_or_entity,
                                "old_variant": variant_text,
                                "standardized": std_target,
                            },
                        )
                        applied_records.append(record)
                        report.audit_trail.append(record)

        logger.info(f"SAFE FIXES aplicados com sucesso: {len(applied_records)} correções registradas")
        return applied_records

    def rollback_fix(
        self,
        document: Document,
        audit_record_or_fix_id: ConsistencyFixAuditRecord | str,
    ) -> bool:
        """Reverte cirurgicamente uma correção automática aplicada anteriormente."""
        record: ConsistencyFixAuditRecord | None = None
        if isinstance(audit_record_or_fix_id, ConsistencyFixAuditRecord):
            record = audit_record_or_fix_id
        else:
            return False

        if record.undone:
            logger.warning(f"Fix {record.fix_id} já foi revertido anteriormente")
            return True

        segment = self._find_segment(document, record.segment_id)
        if not segment:
            logger.error(f"Segmento {record.segment_id} não encontrado para rollback")
            return False

        segment.translated_text = record.original_target_text
        segment.revisions.append(f"ConsistencyPass [ROLLBACK]: Reversão do fix {record.fix_id}")
        record.undone = True
        logger.info(f"Rollback do fix {record.fix_id} no segmento {record.segment_id} concluído")
        return True

    def rollback_all_fixes(
        self,
        document: Document,
        report: GlobalConsistencyReport,
    ) -> int:
        """Reverte todas as correções automáticas ativas no relatório."""
        undone_count = 0
        for record in reversed(report.audit_trail):
            if not record.undone:
                if self.rollback_fix(document, record):
                    undone_count += 1
        logger.info(f"Rollback completo executado: {undone_count} correções revertidas")
        return undone_count

    # -------------------------------------------------------------------------
    # Métodos Internos de Auditoria
    # -------------------------------------------------------------------------

    def _collect_all_segments(
        self, document: Document
    ) -> list[tuple[Chapter, Segment]]:
        """Recupera todos os pares (Chapter, Segment) da obra."""
        result: list[tuple[Chapter, Segment]] = []
        for chapter in document.chapters:
            for seg in chapter.segments:
                result.append((chapter, seg))
        return result

    def _find_segment(self, document: Document, segment_id: str) -> Segment | None:
        """Localiza um segmento específico na árvore do documento."""
        for ch in document.chapters:
            for s in ch.segments:
                if s.id == segment_id:
                    return s
        return None

    def _audit_terminology_and_glossary(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita termos recorrentes e entradas do glossário buscando variantes divergentes."""
        conflicts: list[ConsistencyConflict] = []
        glossary = getattr(memory_manager, "glossary", None)
        glossary_entries = getattr(glossary, "_entries", {}) if glossary else {}

        # 1. Checagem direta de termos do Glossário
        for source_key, entry in glossary_entries.items():
            source_term = entry.source_term
            target_term = entry.target_term
            is_locked = bool(entry.locked)
            aliases = getattr(entry, "aliases", [])

            # Mapeia onde o termo fonte ocorre
            term_occurrences: list[tuple[Chapter, Segment]] = []
            pattern = rf"\b{re.escape(source_term)}\b"
            for ch, seg in all_segments:
                if not seg.translated_text:
                    continue
                if re.search(pattern, seg.original_text, re.IGNORECASE):
                    term_occurrences.append((ch, seg))

            if not term_occurrences:
                continue

            # Mapeia as variantes de tradução observadas no target
            variant_map: dict[str, list[OccurrenceLocation]] = {}
            target_pattern = rf"\b{re.escape(target_term)}\b"

            for ch, seg in term_occurrences:
                target_text = seg.translated_text
                loc = OccurrenceLocation(
                    chapter_id=ch.id,
                    segment_id=seg.id,
                    source_snippet=seg.original_text[:100],
                    translated_snippet=target_text[:100],
                    order_index=seg.sequence_order,
                )

                if re.search(target_pattern, target_text, re.IGNORECASE):
                    # Encontrou a forma canônica do glossário
                    variant_map.setdefault(target_term, []).append(loc)
                else:
                    # Encontrou tradução divergente ou não padronizada
                    divergent_variant = self._extract_relevant_target_phrase(
                        target_text, source_term, target_term, aliases
                    )
                    variant_map.setdefault(divergent_variant, []).append(loc)

            # Se houver mais de uma variante
            if len(variant_map) > 1:
                severity = IssueSeverity.SAFE_FIX if is_locked else IssueSeverity.SUGGESTED_FIX
                message = (
                    f"Termo do glossário '{source_term}' traduzido de forma divergente em múltiplos capítulos ({', '.join(list(variant_map.keys()))}). "
                    f"Tradução canônica esperada: '{target_term}' (locked={is_locked})."
                )
                conflicts.append(
                    ConsistencyConflict(
                        term_or_entity=source_term,
                        category="glossary" if is_locked else "terminology",
                        variants=variant_map,
                        severity=severity,
                        message=message,
                        suggested_standardization=target_term,
                        is_potential_intentional_variation=not is_locked,
                        evidence=f"Glossary target: '{target_term}'",
                        details={"is_locked": is_locked, "glossary_id": getattr(entry, "id", "")},
                    )
                )

        # 2. Detecção empírica de termos recorrentes (fora do glossário formal)
        recurrent_terms_found = self._detect_recurrent_term_divergences(all_segments)
        for term, v_map in recurrent_terms_found.items():
            if term.lower() in [k.lower() for k in glossary_entries.keys()]:
                continue

            # Escolhe a variante mais frequente como sugestão
            most_frequent = max(v_map.items(), key=lambda x: len(x[1]))[0]
            conflicts.append(
                ConsistencyConflict(
                    term_or_entity=term,
                    category="terminology",
                    variants=v_map,
                    severity=IssueSeverity.SUGGESTED_FIX,
                    message=(
                        f"Termo recorrente '{term}' traduzido com {len(v_map)} variantes distintas na obra "
                        f"({', '.join(list(v_map.keys())[:3])})."
                    ),
                    suggested_standardization=most_frequent,
                    is_potential_intentional_variation=True,
                    evidence=f"Variantes: {list(v_map.keys())}",
                )
            )

        return conflicts

    def _detect_recurrent_term_divergences(
        self, all_segments: list[tuple[Chapter, Segment]]
    ) -> dict[str, dict[str, list[OccurrenceLocation]]]:
        """Detecta termos compostos em inglês com traduções divergentes entre capítulos."""
        recurrent_candidates: dict[str, dict[str, list[OccurrenceLocation]]] = {}

        candidate_phrases = set()
        for _, seg in all_segments:
            matches = re.findall(
                r"\b(?!(?:the|and|for|with|from|this|that|some|each|every|our|his|her|its|their)\b)[A-Za-z]{3,}\s+(?:drive|generator|chamber|device|system|protocol|shield|cannon|array|core|engine|portal|gate|vessel)\b",
                seg.original_text,
                re.IGNORECASE,
            )
            for m in matches:
                candidate_phrases.add(m.lower())

        for phrase in candidate_phrases:
            phrase_locs: list[tuple[Chapter, Segment]] = []
            for ch, seg in all_segments:
                if re.search(rf"\b{re.escape(phrase)}\b", seg.original_text, re.IGNORECASE):
                    phrase_locs.append((ch, seg))

            if len(phrase_locs) < 2:
                continue

            v_map: dict[str, list[OccurrenceLocation]] = {}
            for ch, seg in phrase_locs:
                target_text = seg.translated_text
                snippet = self._extract_phrase_translation(seg.original_text, target_text, phrase)
                if not snippet:
                    snippet = target_text[:30]
                loc = OccurrenceLocation(
                    chapter_id=ch.id,
                    segment_id=seg.id,
                    source_snippet=seg.original_text[:100],
                    translated_snippet=target_text[:100],
                    order_index=seg.sequence_order,
                )
                v_map.setdefault(snippet, []).append(loc)

            if len(v_map) > 1:
                recurrent_candidates[phrase] = v_map

        return recurrent_candidates

    def _audit_translation_memory(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita conformidade contra unidades da Translation Memory."""
        conflicts: list[ConsistencyConflict] = []
        tm = getattr(memory_manager, "tm", None)
        tm_entries = getattr(tm, "_entries", {}) if tm else {}

        for source_key, entry in tm_entries.items():
            source_term = entry.source_term
            target_term = entry.target_term
            is_locked = bool(getattr(entry, "locked", False))

            variant_map: dict[str, list[OccurrenceLocation]] = {}
            target_pattern = rf"\b{re.escape(target_term)}\b"

            for ch, seg in all_segments:
                if not seg.translated_text:
                    continue
                if source_term.lower() in seg.original_text.lower():
                    loc = OccurrenceLocation(
                        chapter_id=ch.id,
                        segment_id=seg.id,
                        source_snippet=seg.original_text[:100],
                        translated_snippet=seg.translated_text[:100],
                        order_index=seg.sequence_order,
                    )
                    if re.search(target_pattern, seg.translated_text, re.IGNORECASE):
                        variant_map.setdefault(target_term, []).append(loc)
                    else:
                        divergent_snippet = self._extract_relevant_target_phrase(
                            seg.translated_text, source_term, target_term
                        )
                        variant_map.setdefault(divergent_snippet, []).append(loc)

            if len(variant_map) > 1:
                severity = IssueSeverity.SAFE_FIX if is_locked else IssueSeverity.SUGGESTED_FIX
                conflicts.append(
                    ConsistencyConflict(
                        term_or_entity=source_term,
                        category="translation_memory",
                        variants=variant_map,
                        severity=severity,
                        message=(
                            f"Expressão da TM '{source_term}' traduzida de forma divergente entre capítulos. "
                            f"Tradução esperada: '{target_term}'."
                        ),
                        suggested_standardization=target_term,
                        is_potential_intentional_variation=not is_locked,
                        evidence=f"TM target: '{target_term}'",
                    )
                )

        return conflicts

    def _audit_characters_and_aliases(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita consistência de nomes de personagens e seus aliases."""
        conflicts: list[ConsistencyConflict] = []
        char_mem = getattr(memory_manager, "characters", None)
        characters = getattr(char_mem, "_characters", {}) if char_mem else {}

        for char_id, character in characters.items():
            canonical_name = character.canonical_name or character.name
            aliases = character.aliases or []

            names_to_check = [canonical_name] + aliases
            for name in names_to_check:
                if not name or len(name) < 3:
                    continue

                occurrences: list[tuple[Chapter, Segment]] = []
                name_pattern = rf"\b{re.escape(name)}\b"
                for ch, seg in all_segments:
                    if not seg.translated_text:
                        continue
                    if re.search(name_pattern, seg.original_text, re.IGNORECASE):
                        occurrences.append((ch, seg))

                if len(occurrences) < 2:
                    continue

                variant_map: dict[str, list[OccurrenceLocation]] = {}
                for ch, seg in occurrences:
                    target_text = seg.translated_text
                    matched_variant = self._find_name_in_target(name, target_text)
                    loc = OccurrenceLocation(
                        chapter_id=ch.id,
                        segment_id=seg.id,
                        source_snippet=seg.original_text[:100],
                        translated_snippet=target_text[:100],
                        order_index=seg.sequence_order,
                        character_id=char_id,
                    )
                    variant_map.setdefault(matched_variant, []).append(loc)

                if len(variant_map) > 1:
                    is_alias = name in aliases
                    category = "alias" if is_alias else "character"
                    most_common = max(variant_map.items(), key=lambda x: len(x[1]))[0]

                    conflicts.append(
                        ConsistencyConflict(
                            term_or_entity=f"{name} ({canonical_name})" if is_alias else name,
                            category=category,
                            variants=variant_map,
                            severity=IssueSeverity.SUGGESTED_FIX,
                            message=(
                                f"Nome/alias '{name}' do personagem '{canonical_name}' traduzido com variantes "
                                f"inconsistentes entre capítulos: {list(variant_map.keys())}."
                            ),
                            suggested_standardization=most_common,
                            is_potential_intentional_variation=False,
                            evidence=f"Character ID: {char_id}",
                        )
                    )

        return conflicts

    def _audit_treatment_forms(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita variações e alterações de formas de tratamento (você vs tu vs o senhor).

        CRUCIAL: Não uniformiza automaticamente diferenças intencionais. Marca como REVIEW_REQUIRED.
        """
        conflicts: list[ConsistencyConflict] = []
        chapter_treatments: dict[str, dict[str, list[OccurrenceLocation]]] = {}

        for ch, seg in all_segments:
            text = seg.translated_text
            if not text:
                continue

            for t_name, pattern in TREATMENT_PATTERNS.items():
                if pattern.search(text):
                    loc = OccurrenceLocation(
                        chapter_id=ch.id,
                        segment_id=seg.id,
                        source_snippet=seg.original_text[:100],
                        translated_snippet=text[:100],
                        order_index=seg.sequence_order,
                    )
                    if ch.id not in chapter_treatments:
                        chapter_treatments[ch.id] = {}
                    chapter_treatments[ch.id].setdefault(t_name, []).append(loc)

        if len(chapter_treatments) < 2:
            return conflicts

        # Identifica a forma predominante em cada capítulo
        chapter_predominant: dict[str, str] = {}
        for ch_id, t_counts in chapter_treatments.items():
            if t_counts:
                pred = max(t_counts.items(), key=lambda x: len(x[1]))[0]
                chapter_predominant[ch_id] = pred

        distinct_treatments = set(chapter_predominant.values())
        if len(distinct_treatments) > 1:
            variants: dict[str, list[OccurrenceLocation]] = {}
            for ch_id, pred_t in chapter_predominant.items():
                locs = chapter_treatments[ch_id].get(pred_t, [])
                variants.setdefault(pred_t, []).extend(locs)

            ch_details = [f"{ch_id}: '{pred}'" for ch_id, pred in chapter_predominant.items()]
            conflicts.append(
                ConsistencyConflict(
                    term_or_entity="Forma de Tratamento (Tratamento Global)",
                    category="treatment",
                    variants=variants,
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    message=(
                        f"Alteração na forma de tratamento detectada entre capítulos ({', '.join(ch_details)}). "
                        "ATENÇÃO: Não uniformizado automaticamente. Mudanças de tratamento frequentemente "
                        "refletem nuances intencionais (evolução da intimidade, conflito dramático, "
                        "afastamento ou quebra hierárquica) e exigem revisão humana obrigatória."
                    ),
                    suggested_standardization="",
                    is_potential_intentional_variation=True,
                    evidence=f"Capítulos: {ch_details}",
                    details={"chapter_predominant": chapter_predominant},
                )
            )

        return conflicts

    def _audit_pronouns_and_gender(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita concordância pronominal com o gênero estabelecido dos personagens."""
        conflicts: list[ConsistencyConflict] = []
        char_mem = getattr(memory_manager, "characters", None)
        characters = getattr(char_mem, "_characters", {}) if char_mem else {}

        for char_id, character in characters.items():
            gender = (character.gender or "").lower()
            if gender not in ("feminine", "masculine"):
                continue

            canonical_name = character.canonical_name or character.name
            name_pattern = rf"\b{re.escape(canonical_name)}\b"

            wrong_pronoun_locs: list[OccurrenceLocation] = []
            for ch, seg in all_segments:
                if not seg.translated_text:
                    continue
                if re.search(name_pattern, seg.original_text, re.IGNORECASE):
                    target_text = seg.translated_text
                    if gender == "feminine" and PRONOUNS_MASCULINE.search(target_text):
                        loc = OccurrenceLocation(
                            chapter_id=ch.id,
                            segment_id=seg.id,
                            source_snippet=seg.original_text[:100],
                            translated_snippet=target_text[:100],
                            order_index=seg.sequence_order,
                            character_id=char_id,
                        )
                        wrong_pronoun_locs.append(loc)
                    elif gender == "masculine" and PRONOUNS_FEMININE.search(target_text):
                        loc = OccurrenceLocation(
                            chapter_id=ch.id,
                            segment_id=seg.id,
                            source_snippet=seg.original_text[:100],
                            translated_snippet=target_text[:100],
                            order_index=seg.sequence_order,
                            character_id=char_id,
                        )
                        wrong_pronoun_locs.append(loc)

            if wrong_pronoun_locs:
                expected_pronoun = "feminino (ela/dela)" if gender == "feminine" else "masculino (ele/dele)"
                conflicts.append(
                    ConsistencyConflict(
                        term_or_entity=f"Pronome ({canonical_name})",
                        category="pronoun",
                        variants={"pronome_incongruente": wrong_pronoun_locs},
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        message=(
                            f"Possível desacordo pronominal de gênero para o personagem '{canonical_name}' "
                            f"(gênero estabelecido: {gender}). Esperado: {expected_pronoun}."
                        ),
                        suggested_standardization=expected_pronoun,
                        is_potential_intentional_variation=False,
                        evidence=f"Gênero registrado: {gender}",
                    )
                )

        return conflicts

    def _audit_locations_and_organizations(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita consistência na tradução de nomes de locais e organizações."""
        conflicts: list[ConsistencyConflict] = []
        glossary = getattr(memory_manager, "glossary", None)
        glossary_entries = getattr(glossary, "_entries", {}) if glossary else {}

        for source_key, entry in glossary_entries.items():
            entry_type = (entry.entry_type or "").lower()
            if entry_type not in ("place", "location", "organization"):
                continue

            source_term = entry.source_term
            target_term = entry.target_term
            aliases = getattr(entry, "aliases", [])
            category = "location" if entry_type in ("place", "location") else "organization"

            variant_map: dict[str, list[OccurrenceLocation]] = {}
            target_pat = rf"\b{re.escape(target_term)}\b"

            for ch, seg in all_segments:
                if not seg.translated_text:
                    continue
                if re.search(rf"\b{re.escape(source_term)}\b", seg.original_text, re.IGNORECASE):
                    loc = OccurrenceLocation(
                        chapter_id=ch.id,
                        segment_id=seg.id,
                        source_snippet=seg.original_text[:100],
                        translated_snippet=seg.translated_text[:100],
                        order_index=seg.sequence_order,
                    )
                    if re.search(target_pat, seg.translated_text, re.IGNORECASE):
                        variant_map.setdefault(target_term, []).append(loc)
                    else:
                        phrase = self._extract_relevant_target_phrase(
                            seg.translated_text, source_term, target_term, aliases
                        )
                        variant_map.setdefault(phrase, []).append(loc)

            if len(variant_map) > 1:
                conflicts.append(
                    ConsistencyConflict(
                        term_or_entity=source_term,
                        category=category,
                        variants=variant_map,
                        severity=IssueSeverity.SUGGESTED_FIX,
                        message=(
                            f"{category.capitalize()} '{source_term}' traduzido com variações entre capítulos: "
                            f"{list(variant_map.keys())}. Canônico: '{target_term}'."
                        ),
                        suggested_standardization=target_term,
                        is_potential_intentional_variation=False,
                        evidence=f"Tipo de entidade: {entry_type}",
                    )
                )

        return conflicts

    def _audit_titles(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita consistência de títulos de nobreza e cargos (Lord, Sir, Captain, Doctor, etc.)."""
        conflicts: list[ConsistencyConflict] = []
        style_bible = getattr(memory_manager, "style_bible", None)
        title_policy = getattr(style_bible, "title_treatment", "traduzir").lower() if style_bible else "traduzir"

        for en_title, expected_pt in NOBILITY_TITLES.items():
            occurrences: list[tuple[Chapter, Segment]] = []
            pat = rf"\b{re.escape(en_title)}\b"

            for ch, seg in all_segments:
                if not seg.translated_text:
                    continue
                if re.search(pat, seg.original_text, re.IGNORECASE):
                    occurrences.append((ch, seg))

            if len(occurrences) < 2:
                continue

            variant_map: dict[str, list[OccurrenceLocation]] = {}
            for ch, seg in occurrences:
                target_text = seg.translated_text
                loc = OccurrenceLocation(
                    chapter_id=ch.id,
                    segment_id=seg.id,
                    source_snippet=seg.original_text[:100],
                    translated_snippet=target_text[:100],
                    order_index=seg.sequence_order,
                )

                if re.search(rf"\b{re.escape(expected_pt)}\b", target_text, re.IGNORECASE):
                    variant_map.setdefault(expected_pt.capitalize(), []).append(loc)
                elif re.search(rf"\b{re.escape(en_title)}\b", target_text, re.IGNORECASE):
                    variant_map.setdefault(en_title.capitalize(), []).append(loc)
                else:
                    variant_map.setdefault(self._extract_phrase_translation(seg.original_text, target_text, en_title), []).append(loc)

            if len(variant_map) > 1:
                suggested = expected_pt.capitalize() if "traduzir" in title_policy else en_title.capitalize()
                conflicts.append(
                    ConsistencyConflict(
                        term_or_entity=f"Título '{en_title.capitalize()}'",
                        category="title",
                        variants=variant_map,
                        severity=IssueSeverity.SUGGESTED_FIX,
                        message=(
                            f"Título '{en_title.capitalize()}' traduzido com variações ({list(variant_map.keys())}). "
                            f"Diretriz editorial: '{title_policy}' (esperado: '{suggested}')."
                        ),
                        suggested_standardization=suggested,
                        is_potential_intentional_variation=False,
                        evidence=f"Diretriz de estilo: {title_policy}",
                    )
                )

        return conflicts

    def _audit_chronology_and_story(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita cronologia e fatos persistentes integrando anomalias do StoryMemory."""
        conflicts: list[ConsistencyConflict] = []
        story = getattr(memory_manager, "story", None)
        if not story:
            return conflicts

        anomalies = []
        if hasattr(story, "detect_contradictions"):
            anomalies.extend(story.detect_contradictions())
        if hasattr(story, "detect_timeline_inconsistencies"):
            anomalies.extend(story.detect_timeline_inconsistencies())

        for anomaly in anomalies:
            ch_id = getattr(anomaly, "chapter_id", "global")
            conflicts.append(
                ConsistencyConflict(
                    term_or_entity=getattr(anomaly, "entity_id", "") or anomaly.anomaly_type,
                    category="chronology",
                    variants={
                        "anomalia_narrativa": [
                            OccurrenceLocation(
                                chapter_id=ch_id,
                                segment_id=ch_id,
                                source_snippet="",
                                translated_snippet=getattr(anomaly, "snippet", ""),
                            )
                        ]
                    },
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    message=anomaly.message,
                    suggested_standardization="",
                    is_potential_intentional_variation=True,
                    evidence=getattr(anomaly, "evidence", "") or getattr(anomaly, "conflicting_with", ""),
                    details={"anomaly_type": anomaly.anomaly_type},
                )
            )

        return conflicts

    def _audit_style_and_dialogues(
        self,
        all_segments: list[tuple[Chapter, Segment]],
        memory_manager: MemoryManagerInterface,
    ) -> list[ConsistencyConflict]:
        """Audita estilo editorial, pontuação de diálogos e diretrizes da Style Bible."""
        conflicts: list[ConsistencyConflict] = []
        style_bible = getattr(memory_manager, "style_bible", None)
        if not style_bible:
            return conflicts

        dialogue_convention = getattr(style_bible, "dialogue_style", "travessão").lower()

        # Checagem de travessão vs aspas em diálogos
        quote_dialogues: list[OccurrenceLocation] = []
        emdash_no_space: list[OccurrenceLocation] = []

        for ch, seg in all_segments:
            text = seg.translated_text
            if not text:
                continue

            # Diálogos com aspas quando a regra é travessão
            if "travessão" in dialogue_convention:
                if re.search(r'(^|\n)["“][^"”]+["”]', text):
                    quote_dialogues.append(
                        OccurrenceLocation(
                            chapter_id=ch.id,
                            segment_id=seg.id,
                            source_snippet=seg.original_text[:80],
                            translated_snippet=text[:80],
                            order_index=seg.sequence_order,
                        )
                    )

                # Travessão sem espaço: '—Texto'
                if re.search(r"(^|\n)—[^\s\d—]", text):
                    emdash_no_space.append(
                        OccurrenceLocation(
                            chapter_id=ch.id,
                            segment_id=seg.id,
                            source_snippet=seg.original_text[:80],
                            translated_snippet=text[:80],
                            order_index=seg.sequence_order,
                        )
                    )

        if quote_dialogues:
            conflicts.append(
                ConsistencyConflict(
                    term_or_entity="Pontuação de Diálogo (Aspas vs Travessão)",
                    category="dialogue",
                    variants={"aspas": quote_dialogues},
                    severity=IssueSeverity.SUGGESTED_FIX,
                    message="Diálogo formatado com aspas quando a diretriz editorial da obra exige travessão (—).",
                    suggested_standardization="—",
                    is_potential_intentional_variation=False,
                    evidence=f"StyleBible: {dialogue_convention}",
                )
            )

        if emdash_no_space:
            conflicts.append(
                ConsistencyConflict(
                    term_or_entity="Espaçamento de Travessão de Diálogo",
                    category="dialogue",
                    variants={"emdash_sem_espaco": emdash_no_space},
                    severity=IssueSeverity.SAFE_FIX,
                    message="Travessão de diálogo sem espaço após o travessão ('—Texto' em vez de '— Texto').",
                    suggested_standardization="— ",
                    is_potential_intentional_variation=False,
                    evidence="Editorial brasileiro padrão: '— '",
                )
            )

        return conflicts

    # -------------------------------------------------------------------------
    # Métodos Auxiliares de Extração e Substituição
    # -------------------------------------------------------------------------

    def _extract_relevant_target_phrase(
        self,
        target_text: str,
        source_term: str,
        target_term: str,
        aliases: list[str] | None = None,
    ) -> str:
        """Extrai a variante ou trecho representativo da tradução divergente encontrada no segmento."""
        # 1. Checa aliases conhecidos registrados na memória
        if aliases:
            for alias in aliases:
                if re.search(rf"\b{re.escape(alias)}\b", target_text, re.IGNORECASE):
                    m = re.search(rf"\b{re.escape(alias)}\b", target_text, re.IGNORECASE)
                    if m:
                        return m.group(0)

        # 2. Checa palavras de conteúdo compartilhadas ou estruturas afins
        target_words = target_term.split()
        if len(target_words) >= 2:
            suffix = " ".join(target_words[1:])
            m = re.search(rf"\b\w+\s+{re.escape(suffix)}\b", target_text, re.IGNORECASE)
            if m:
                return m.group(0)
            prefix = target_words[0]
            m2 = re.search(rf"\b{re.escape(prefix)}\s+\w+\b", target_text, re.IGNORECASE)
            if m2:
                return m2.group(0)

        # 3. Dicionário de equivalentes comuns
        common_alternatives = {
            "watch": ["o relógio", "relógio", "vigília", "guarda"],
            "drive": ["propulsor de dobra", "propulsor", "propulsão", "motor"],
            "shield": ["campo de força", "blindagem", "escudo"],
            "shadow": ["o vulto", "vulto", "sombra"],
            "citadel": ["fortaleza", "cidadela"],
        }
        source_lower = source_term.lower()
        for key, alts in common_alternatives.items():
            if key in source_lower:
                for alt in alts:
                    m = re.search(rf"\b{re.escape(alt)}(\s+de\s+\w+|\s+\w+)?\b", target_text, re.IGNORECASE)
                    if m:
                        return m.group(0)

        # 4. Fallback: extrai frase curta limpa
        clean = re.sub(r'^[—"“\s]+', "", target_text)
        words = clean.split()
        return " ".join(words[:min(4, len(words))])

    def _extract_phrase_translation(
        self, source_text: str, target_text: str, phrase: str
    ) -> str:
        """Extrai a correspondência aproximada de um termo composto no texto traduzido."""
        # Busca padrões de termos compostos: "gerador de escudo", "motor de dobra", etc.
        m = re.search(
            r"\b(gerador|motor|propulsor|sistema|dispositivo|canhão|campo|câmara|núcleo)\s+de\s+\w+\b",
            target_text,
            re.IGNORECASE,
        )
        if m:
            return m.group(0)

        m2 = re.search(
            r"\b\w+\s+de\s+(escudo|blindagem|dobra|força|energia|hiperespaço)\b",
            target_text,
            re.IGNORECASE,
        )
        if m2:
            return m2.group(0)

        words = target_text.split()
        return " ".join(words[:min(3, len(words))])

    def _find_name_in_target(self, name: str, target_text: str) -> str:
        """Localiza a forma como um nome próprio foi renderizado no texto traduzido."""
        if re.search(rf"\b{re.escape(name)}\b", target_text, re.IGNORECASE):
            match = re.search(rf"\b{re.escape(name)}\b", target_text, re.IGNORECASE)
            return match.group(0) if match else name

        if name.startswith("Dr. "):
            alt = name.replace("Dr. ", "Doutor ")
            if alt.lower() in target_text.lower():
                return alt
        if name.startswith("Mr. "):
            alt = name.replace("Mr. ", "Sr. ")
            if alt.lower() in target_text.lower():
                return alt

        # Detecta tradução de nomes (ex: John -> João)
        if "john" in name.lower() and "joão" in target_text.lower():
            return name.replace("John", "João").replace("john", "joão")

        return name

    def _replace_variant_safely(
        self, text: str, old_variant: str, new_variant: str, category: str
    ) -> str:
        """Executa substituição segura de uma variante sem efeitos colaterais indesejados."""
        if category == "dialogue" and new_variant == "— ":
            # Correção de espaçamento após travessão: '—Texto' -> '— Texto'
            return re.sub(r"(^|\n)—([^\s\d—])", r"\1— \2", text)

        pattern = rf"\b{re.escape(old_variant)}\b"
        if re.search(pattern, text, re.IGNORECASE):
            return re.sub(pattern, new_variant, text, count=1, flags=re.IGNORECASE)

        if old_variant.lower() in text.lower():
            idx = text.lower().find(old_variant.lower())
            return text[:idx] + new_variant + text[idx + len(old_variant):]

        return text
