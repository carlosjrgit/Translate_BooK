"""Testes unitários para o Consistency Pass Global (Prompt 20).

Valida:
1. Detecção de termo traduzido de duas formas.
2. Detecção de alteração na forma de tratamento (sem uniformização cega).
3. Relatório global navegável por capítulo e segmento (árvore, markdown, dict).
4. Correções automáticas restritas a SAFE FIX com trilha de auditoria e reversibilidade total (rollback).
5. Auditoria de personagens, aliases, pronomes, títulos, diálogos e cronologia.
"""

from __future__ import annotations

from typing import Any

from book_translator.consistency.checker import GlobalConsistencyChecker
from book_translator.core.models import Chapter, Document, DocumentMetadata, Segment
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    StyleBible,
)
from book_translator.memory.manager import MemoryManager
from book_translator.qa.base import IssueSeverity


def build_synthetic_document(chapters_data: list[dict[str, Any]]) -> Document:
    """Cria um documento com múltiplos capítulos e segmentos para teste."""
    chapters: list[Chapter] = []
    for ch_idx, ch_info in enumerate(chapters_data, start=1):
        ch_id = ch_info.get("id", f"chapter_{ch_idx:02d}")
        title = ch_info.get("title", f"Capítulo {ch_idx}")
        segments: list[Segment] = []

        for seg_idx, seg_info in enumerate(ch_info.get("segments", []), start=1):
            seg_id = seg_info.get("id", f"{ch_id}_seg_{seg_idx:02d}")
            segments.append(
                Segment(
                    id=seg_id,
                    chapter_id=ch_id,
                    original_text=seg_info.get("original", ""),
                    translated_text=seg_info.get("translated", ""),
                    sequence_order=seg_idx,
                    status="translated",
                )
            )

        chapter = Chapter(
            id=ch_id,
            title=title,
            order=ch_idx,
            segments=segments,
        )
        chapters.append(chapter)

    meta = DocumentMetadata(title="Test Saga", author="Author Test", language="en")
    return Document(id="doc_test", metadata=meta, chapters=chapters)


# =============================================================================
# 1. CRITÉRIO DE ACEITE: Consegue detectar termo traduzido de duas formas
# =============================================================================

def test_detects_term_translated_in_two_different_ways() -> None:
    """Verifica se o auditor detecta quando um mesmo termo técnico/específico foi

    traduzido de duas formas distintas entre capítulos.
    """
    doc = build_synthetic_document([
        {
            "id": "ch_01",
            "title": "Partida",
            "segments": [
                {
                    "id": "ch_01_s01",
                    "original": "The warp drive was fully online and humming.",
                    "translated": "O motor de dobra estava totalmente ligado e zumbindo.",
                }
            ],
        },
        {
            "id": "ch_02",
            "title": "A Batalha",
            "segments": [
                {
                    "id": "ch_02_s01",
                    "original": "Captain, engage the warp drive right now!",
                    "translated": "Capitão, acione o propulsor de dobra agora mesmo!",
                }
            ],
        },
    ])

    mem = MemoryManager(project_id="test_proj")
    mem.add_glossary_entry(
        GlossaryEntry(
            source_term="warp drive",
            target_term="motor de dobra",
            locked=True,
            aliases=["propulsor de dobra"],
        )
    )

    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)

    assert report.has_conflicts is True
    term_conflicts = [c for c in report.conflicts if "warp drive" in c.term_or_entity.lower()]
    assert len(term_conflicts) == 1

    conflict = term_conflicts[0]
    assert conflict.term_or_entity == "warp drive"
    assert "motor de dobra" in conflict.variants
    assert "propulsor de dobra" in conflict.variants
    assert len(conflict.variants["motor de dobra"]) == 1
    assert len(conflict.variants["propulsor de dobra"]) == 1
    assert conflict.suggested_standardization == "motor de dobra"
    assert conflict.severity == IssueSeverity.SAFE_FIX  # locked glossary term


def test_detects_unlocked_recurrent_term_divergence() -> None:
    """Detecta termos recorrentes não registrados formalmente no glossário que

    divergem na tradução.
    """
    doc = build_synthetic_document([
        {
            "id": "ch_01",
            "title": "Espaço Profundo",
            "segments": [
                {
                    "id": "ch_01_s01",
                    "original": "The shield generator absorbed the blast.",
                    "translated": "O gerador de escudo absorveu a explosão.",
                }
            ],
        },
        {
            "id": "ch_02",
            "title": "Contra-ataque",
            "segments": [
                {
                    "id": "ch_02_s01",
                    "original": "The shield generator failed under pressure.",
                    "translated": "O gerador de blindagem falhou sob pressão.",
                }
            ],
        },
    ])

    mem = MemoryManager(project_id="test_proj")
    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)

    shield_conflicts = [c for c in report.conflicts if "shield generator" in c.term_or_entity.lower()]
    assert len(shield_conflicts) >= 1
    sc = shield_conflicts[0]
    assert sc.severity == IssueSeverity.SUGGESTED_FIX
    assert sc.is_potential_intentional_variation is True


# =============================================================================
# 2. CRITÉRIO DE ACEITE: Detecta alteração de tratamento (sem uniformização cega)
# =============================================================================

def test_detects_treatment_alteration_as_review_required() -> None:
    """Verifica se alteração de tratamento ('o senhor' no Cap 1 vs 'você' no Cap 2)

    é detectada e classificada estritamente como REVIEW_REQUIRED sem uniformização automática.
    """
    doc = build_synthetic_document([
        {
            "id": "ch_01",
            "title": "Encontro Formal",
            "segments": [
                {
                    "id": "ch_01_s01",
                    "original": "You should consider the consequences, sir.",
                    "translated": "O senhor deve considerar as consequências, senhor.",
                },
                {
                    "id": "ch_01_s02",
                    "original": "Will you attend the ceremony?",
                    "translated": "O senhor comparecerá à cerimônia?",
                },
            ],
        },
        {
            "id": "ch_02",
            "title": "Conversa Íntima",
            "segments": [
                {
                    "id": "ch_02_s01",
                    "original": "You know I cannot do that.",
                    "translated": "Você sabe que eu não posso fazer isso.",
                },
                {
                    "id": "ch_02_s02",
                    "original": "Why are you looking at me like that?",
                    "translated": "Por que você está me olhando desse jeito?",
                },
            ],
        },
    ])

    mem = MemoryManager(project_id="test_proj")
    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)

    treatment_conflicts = report.get_conflicts_by_category("treatment")
    assert len(treatment_conflicts) == 1

    tc = treatment_conflicts[0]
    assert tc.severity == IssueSeverity.REVIEW_REQUIRED
    assert tc.is_potential_intentional_variation is True
    # Garante que NÃO há sugestão cega que forçaria uniformização
    assert tc.suggested_standardization == ""
    assert "Não uniformizado automaticamente" in tc.message
    assert "ch_01" in tc.get_chapters_involved()
    assert "ch_02" in tc.get_chapters_involved()


# =============================================================================
# 3. CRITÉRIO DE ACEITE: Relatório global navegável por capítulo/segmento
# =============================================================================

def test_global_report_navigation_and_export() -> None:
    """Verifica que o relatório é navegável por capítulo e segmento e pode ser exportado."""
    doc = build_synthetic_document([
        {
            "id": "ch_01",
            "title": "Cap 1",
            "segments": [
                {
                    "id": "ch_01_s01",
                    "original": "Lord Harrington entered.",
                    "translated": "Lorde Harrington entrou.",
                }
            ],
        },
        {
            "id": "ch_02",
            "title": "Cap 2",
            "segments": [
                {
                    "id": "ch_02_s01",
                    "original": "Lord Harrington called out.",
                    "translated": "Senhor Harrington chamou em voz alta.",
                }
            ],
        },
    ])

    mem = MemoryManager(project_id="test_proj")
    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)

    # 1. Navegação por capítulo
    ch1_conflicts = report.get_conflicts_by_chapter("ch_01")
    ch2_conflicts = report.get_conflicts_by_chapter("ch_02")
    assert len(ch1_conflicts) >= 1
    assert len(ch2_conflicts) >= 1

    # 2. Navegação por segmento
    seg_conflicts = report.get_conflicts_by_segment("ch_02_s01")
    assert len(seg_conflicts) >= 1

    # 3. Árvore navegável
    tree = report.get_navigation_tree()
    assert "ch_01" in tree
    assert "ch_02" in tree
    assert "ch_02_s01" in tree["ch_02"]
    assert len(tree["ch_02"]["ch_02_s01"]) >= 1

    # 4. Formato Markdown
    md = report.to_markdown()
    assert "# Relatório Global de Consistência" in md
    assert "ch_02_s01" in md
    assert "Capítulo: `ch_01`" in md

    # 5. Formato Dicionário / JSON
    data = report.to_dict()
    assert data["total_chapters_audited"] == 2
    assert data["total_segments_audited"] == 2
    assert len(data["conflicts"]) >= 1


# =============================================================================
# 4. CRITÉRIO DE ACEITE: Correções automáticas reversíveis e auditáveis
# =============================================================================

def test_safe_fixes_application_and_rollback() -> None:
    """Verifica que apenas SAFE FIX é aplicado, gera trilha de auditoria e permite

    reversão exata (rollback_fix e rollback_all_fixes).
    """
    doc = build_synthetic_document([
        {
            "id": "ch_01",
            "title": "Cap 1",
            "segments": [
                {
                    "id": "ch_01_s01",
                    "original": "The Watch was on the wall.",
                    "translated": "A Patrulha estava na muralha.",
                },
                {
                    "id": "ch_01_s02",
                    "original": "Speak clearly.",
                    "translated": "—Não temos tempo para hesitar.",  # Travessão sem espaço
                },
            ],
        },
        {
            "id": "ch_02",
            "title": "Cap 2",
            "segments": [
                {
                    "id": "ch_02_s01",
                    "original": "The Watch sounded the horn.",
                    "translated": "O Relógio tocou a trombeta.",  # Violação de termo locked
                },
                {
                    "id": "ch_02_s02",
                    "original": "You must listen to me.",
                    "translated": "Você deve me ouvir.",  # Tratamento (REVIEW_REQUIRED)
                },
            ],
        },
    ])

    mem = MemoryManager(project_id="test_proj")
    mem.add_glossary_entry(
        GlossaryEntry(
            source_term="The Watch",
            target_term="A Patrulha",
            locked=True,
            aliases=["O Relógio"],
        )
    )
    # Style Bible com travessão
    sb = StyleBible(dialogue_style="travessão")
    mem.save_style_bible(sb)

    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)

    # Identifica tipos de anomalias
    safe_fixes = report.safe_fixes
    _review_req = report.review_required
    assert len(safe_fixes) >= 1

    seg_watch = doc.chapters[1].segments[0]
    seg_dialogue = doc.chapters[0].segments[1]
    original_watch_text = seg_watch.translated_text
    original_dialogue_text = seg_dialogue.translated_text

    # Aplica as correções seguras
    audit_records = checker.apply_safe_fixes(doc, report)
    assert len(audit_records) >= 1

    # Verifica se os textos foram atualizados
    assert seg_watch.translated_text == "A Patrulha tocou a trombeta."
    assert "A Patrulha" in seg_watch.translated_text
    assert seg_dialogue.translated_text.startswith("— Não temos tempo")
    assert len(seg_watch.revisions) >= 1
    assert "ConsistencyPass [SAFE FIX]" in seg_watch.revisions[-1]

    # Garante que o segmento com 'Você deve me ouvir' (REVIEW_REQUIRED) NÃO foi modificado
    seg_treatment = doc.chapters[1].segments[1]
    assert seg_treatment.translated_text == "Você deve me ouvir."

    # Teste de Rollback Cirúrgico de 1 fix
    watch_record = [r for r in audit_records if r.segment_id == "ch_02_s01"][0]
    success = checker.rollback_fix(doc, watch_record)
    assert success is True
    assert watch_record.undone is True
    # Texto do relógio restaurado com precisão
    assert seg_watch.translated_text == original_watch_text
    assert "ConsistencyPass [ROLLBACK]" in seg_watch.revisions[-1]

    # Teste de Rollback Geral (reverte as correções restantes)
    undone_count = checker.rollback_all_fixes(doc, report)
    assert undone_count >= 1
    assert seg_dialogue.translated_text == original_dialogue_text


# =============================================================================
# 5. Auditorias Adicionais: Personagens, Aliases, Locais e Cronologia
# =============================================================================

def test_audit_characters_and_aliases_consistency() -> None:
    """Verifica auditoria de personagens com nomes divergentes."""
    doc = build_synthetic_document([
        {
            "id": "ch_01",
            "title": "Cap 1",
            "segments": [
                {
                    "id": "ch_01_s01",
                    "original": "John Watson looked around.",
                    "translated": "John Watson olhou ao redor.",
                }
            ],
        },
        {
            "id": "ch_02",
            "title": "Cap 2",
            "segments": [
                {
                    "id": "ch_02_s01",
                    "original": "John Watson agreed with him.",
                    "translated": "João Watson concordou com ele.",
                }
            ],
        },
    ])

    mem = MemoryManager(project_id="test_proj")
    mem.add_character(
        CharacterEntry(
            id="char_watson",
            name="John Watson",
            canonical_name="John Watson",
        )
    )

    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)

    char_conflicts = report.get_conflicts_by_category("character")
    assert len(char_conflicts) == 1
    assert "John Watson" in char_conflicts[0].term_or_entity
    assert "João Watson" in char_conflicts[0].variants


def test_audit_pronoun_gender_mismatch() -> None:
    """Verifica detecção de inconsistência pronominal com gênero de personagem."""
    doc = build_synthetic_document([
        {
            "id": "ch_01",
            "title": "Cap 1",
            "segments": [
                {
                    "id": "ch_01_s01",
                    "original": "Lady Beatrice walked in, and he looked very stern.",
                    "translated": "Lady Beatrice entrou, e ele parecia muito severo.",
                }
            ],
        }
    ])

    mem = MemoryManager(project_id="test_proj")
    mem.add_character(
        CharacterEntry(
            id="char_beatrice",
            name="Lady Beatrice",
            gender="feminine",
        )
    )

    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)

    pronoun_conflicts = report.get_conflicts_by_category("pronoun")
    assert len(pronoun_conflicts) >= 1
    pc = pronoun_conflicts[0]
    assert pc.severity == IssueSeverity.REVIEW_REQUIRED
    assert "feminino" in pc.message


def test_audit_chronology_and_story_memory() -> None:
    """Verifica integração com contradições narrativas do StoryMemory."""
    doc = build_synthetic_document([
        {
            "id": "ch_01",
            "title": "Cap 1",
            "segments": [
                {
                    "id": "ch_01_s01",
                    "original": "The ancient rule was sacred.",
                    "translated": "A regra antiga era sagrada.",
                }
            ],
        }
    ])

    mem = MemoryManager(project_id="test_proj")
    # Adiciona fato persistente com negação
    mem.story.record_fact(
        entity_id="planeta",
        fact="Teletransporte é impossível de realizar no planeta.",
        chapter_id="ch_01",
        confidence=1.0,
    )

    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)
    # Não há contradição com o segmento acima
    assert len(report.get_conflicts_by_category("chronology")) == 0

    # Cria contradição de estado de personagem (falecido no cap 1, vivo no cap 2 sem flashback)
    mem.story.record_character_state(
        character_id="char_arthur",
        chapter_id="ch_01",
        alive_status="deceased",
        order_index=1,
    )
    mem.story.record_character_state(
        character_id="char_arthur",
        chapter_id="ch_02",
        alive_status="alive",
        order_index=2,
    )

    report2 = checker.audit(doc, mem)
    chrono_conflicts = report2.get_conflicts_by_category("chronology")
    assert len(chrono_conflicts) >= 1
    assert chrono_conflicts[0].severity == IssueSeverity.REVIEW_REQUIRED
