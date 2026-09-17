"""Testes unitários do Glossário, termos locked e verificação sem substituição cega."""

from __future__ import annotations

import pytest

from book_translator.errors import LockedTermError
from book_translator.memory.glossary import Glossary
from book_translator.memory.models import GlossaryEntry


def test_glossary_add_and_retrieve() -> None:
    gloss = Glossary(project_id="p1")

    entry = GlossaryEntry(
        source_term="The Watch",
        target_term="A Patrulha",
        entry_type="organization",
        locked=True,
        aliases=["Night Watch", "The Night's Watch"],
        context="Força militar defensora da fronteira",
    )
    gloss.add_entry(entry)

    # Busca por termo original
    retrieved = gloss.get_entry("The Watch")
    assert retrieved is not None
    assert retrieved.target_term == "A Patrulha"
    assert retrieved.locked is True

    # Busca por alias
    by_alias = gloss.get_entry("Night Watch")
    assert by_alias is not None
    assert by_alias.source_term == "The Watch"


def test_glossary_locked_term_prevents_unauthorized_overwrite() -> None:
    gloss = Glossary(project_id="p1")

    entry = GlossaryEntry(
        source_term="The Watch",
        target_term="A Patrulha",
        locked=True,
    )
    gloss.add_entry(entry)

    # Tentativa de sobrescrever o termo travado com tradução diferente sem force
    attempt = GlossaryEntry(
        source_term="The Watch",
        target_term="O Relógio",
    )
    with pytest.raises(LockedTermError, match="está travado"):
        gloss.add_entry(attempt, force=False)

    # Tentativa via update_entry sem force
    with pytest.raises(LockedTermError, match="não autorizada"):
        gloss.update_entry("The Watch", target_term="O Relógio", force=False)

    # Termo continua íntegro
    assert gloss.get_entry("The Watch").target_term == "A Patrulha"


def test_glossary_locked_term_override_with_force_records_audit() -> None:
    gloss = Glossary(project_id="p1")

    entry = GlossaryEntry(
        source_term="The Watch",
        target_term="A Patrulha",
        locked=True,
    )
    gloss.add_entry(entry)

    # Atualização forçada pelo editor
    updated = gloss.update_entry(
        source_term="The Watch",
        target_term="A Guarda da Noite",
        force=True,
        author="editor_chefe",
        reason="Decisão editorial conjunta com o autor",
    )

    assert updated.target_term == "A Guarda da Noite"
    assert len(updated.history) == 1
    rev = updated.history[0]
    assert rev.old_value == "A Patrulha"
    assert rev.new_value == "A Guarda da Noite"
    assert rev.changed_by == "editor_chefe"


def test_glossary_find_matching_terms_no_blind_replace() -> None:
    gloss = Glossary(project_id="p1")

    gloss.add_entry(
        GlossaryEntry(
            source_term="art",
            target_term="arte",
            case_sensitive=True,
        )
    )
    gloss.add_entry(
        GlossaryEntry(
            source_term="The Watch",
            target_term="A Patrulha",
            case_sensitive=False,
        )
    )

    # Texto com 'part' (não pode dar match com 'art' por substituição cega)
    # e 'The Watch' e 'the watch'
    text = "He took part in the watch tower. Modern art was his passion."

    matches = gloss.find_matching_terms(text)

    matched_sources = [m[0].source_term for m in matches]
    # 'art' deve ser encontrado em 'Modern art', mas NÃO em 'part'
    assert "art" in matched_sources
    assert "The Watch" in matched_sources

    art_match = next(m for m in matches if m[0].source_term == "art")
    assert text[art_match[1] : art_match[2]] == "art"


def test_glossary_verify_locked_terms_compliance() -> None:
    gloss = Glossary(project_id="p1")

    gloss.add_entry(
        GlossaryEntry(
            source_term="The Watch",
            target_term="A Patrulha",
            locked=True,
        )
    )
    gloss.add_entry(
        GlossaryEntry(
            source_term="The Citadel",
            target_term="A Cidadela",
            locked=True,
        )
    )

    source_text = "The Watch guarded the borders near The Citadel."

    # Cenário 1: Tradução em total conformidade
    target_compliant = "A Patrulha guardava as fronteiras perto de A Cidadela."
    res1 = gloss.verify_locked_terms(source_text, target_compliant)
    assert res1.is_compliant is True
    assert len(res1.violations) == 0
    assert res1.total_checked == 2

    # Cenário 2: Tradução que violou um termo travado ("O Relógio" em vez de "A Patrulha")
    target_violated = "O Relógio guardava as fronteiras perto de A Cidadela."
    res2 = gloss.verify_locked_terms(source_text, target_violated)
    assert res2.is_compliant is False
    assert len(res2.violations) == 1
    v = res2.violations[0]
    assert v["source_term"] == "The Watch"
    assert v["expected_target"] == "A Patrulha"
