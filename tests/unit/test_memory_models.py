"""Testes unitários dos modelos e estruturas de dados de memória e auditoria."""

from __future__ import annotations

from book_translator.memory.models import (
    CharacterEntry,
    ConflictReport,
    GlossaryEntry,
    LockedVerificationResult,
    MemoryRevision,
    TranslationMemoryEntry,
)


def test_memory_revision_creation_and_dict_roundtrip() -> None:
    rev = MemoryRevision(
        changed_by="editor_1",
        field_name="target_term",
        old_value="Guarda do Reino",
        new_value="Guarda Real",
        reason="Padronização com o glossário canônico",
    )
    assert rev.revision_id != ""
    assert rev.timestamp != ""
    assert rev.changed_by == "editor_1"

    data = rev.to_dict()
    assert data["field_name"] == "target_term"
    assert data["old_value"] == "Guarda do Reino"
    assert data["new_value"] == "Guarda Real"

    rebuilt = MemoryRevision.from_dict(data)
    assert rebuilt.revision_id == rev.revision_id
    assert rebuilt.field_name == rev.field_name
    assert rebuilt.old_value == rev.old_value
    assert rebuilt.new_value == rev.new_value


def test_character_entry_attributes_and_revisions() -> None:
    char = CharacterEntry(
        id="char_0042",
        name="Margaret Henderson",
        aliases=["Margaret", "Mrs. Henderson", "Maggie"],
        gender="feminine",
        relations=["mãe de Jack", "ex-esposa de Robert"],
        treatment="Lady",
        speech_style="formal moderado",
        linguistic_traits=["sarcasmo frequente"],
        evidences=["Snippet do capítulo 2"],
        confidence=0.95,
        first_appearance="ch_0002",
        occurrences=137,
    )
    assert char.name == "Margaret Henderson"
    assert len(char.aliases) == 3
    assert char.confidence == 0.95
    assert len(char.history) == 0

    rev = char.add_revision(
        field_name="speech_style",
        old_val="formal moderado",
        new_val="formal cortante",
        author="reviewer",
        reason="Evolução do tom no capítulo 5",
    )
    assert len(char.history) == 1
    assert char.history[0] is rev
    assert rev.field_name == "speech_style"
    assert rev.new_value == "formal cortante"


def test_glossary_entry_and_tm_entry_models() -> None:
    gloss = GlossaryEntry(
        source_term="The Watch",
        target_term="A Patrulha",
        entry_type="organization",
        locked=True,
        aliases=["Night Watch"],
        context="Força militar de fronteira",
    )
    assert gloss.source_term == "The Watch"
    assert gloss.locked is True
    assert "Night Watch" in gloss.aliases

    tm = TranslationMemoryEntry(
        source_term="The Royal Guard",
        target_term="Guarda Real",
        origin="review",
        status="approved",
        locked=True,
        confidence=0.98,
        context="Capítulo 3",
    )
    assert tm.source == "The Royal Guard"
    assert tm.target == "Guarda Real"
    assert tm.status == "approved"
    assert tm.confidence == 0.98

    rev = tm.add_revision("status", "pending", "approved", "admin", "Aprovado pelo líder editorial")
    assert len(tm.history) == 1
    assert rev.new_value == "approved"


def test_conflict_report_and_locked_verification_models() -> None:
    conflict = ConflictReport(
        memory_type="glossary",
        term_or_name="Watch",
        existing_value="A Patrulha",
        conflicting_value="O Relógio",
        reason="Tradução literal em contexto militar",
        severity="error",
    )
    assert conflict.severity == "error"
    assert conflict.term_or_name == "Watch"

    res = LockedVerificationResult(
        is_compliant=False,
        total_checked=2,
        violations=[{"term": "The Watch", "expected": "A Patrulha"}],
    )
    assert not res.is_compliant
    assert res.total_checked == 2
    assert len(res.violations) == 1
