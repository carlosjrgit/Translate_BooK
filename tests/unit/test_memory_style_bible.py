"""Testes unitários completos para StyleBible (Prompt 11)."""

from __future__ import annotations

from book_translator.memory.base import StyleBible, StyleRule


def test_style_bible_all_ten_dimensions_with_evidence() -> None:
    """Verifica registro das 10 dimensões exigidas pelo Prompt 11 com evidência."""
    sb = StyleBible()
    dimensions = [
        ("narrator", "terceira pessoa onisciente", "O narrador sabe os pensamentos de todos."),
        ("narrative_person", "3a pessoa", "Uso predominante de 'ele', 'eles'."),
        ("predominant_tense", "pretérito perfeito", "Verbos no passado: 'chegou', 'disse'."),
        ("formality", "formal culto", "Vocabulário erudito e sintaxe clássica."),
        ("dialogue_style", "travessão", "Diálogos abertos com '— '."),
        ("profanity_policy", "atenuar", "Substituição de termos ofensivos por brandos."),
        ("treatment_forms", "você", "Personagens tratam-se por 'você'."),
        ("punctuation_policy", "aspas curvas e elipse sem espaço", "Uso de '…' e aspas inglesas."),
        ("title_treatment", "manter títulos em inglês", "Ex: 'Lord', 'Sir' não traduzidos."),
        ("internal_conventions", "manter termos mágicos em maiúsculo", "Ex: 'A Força'."),
    ]

    for dim, rule, evidence in dimensions:
        sb.set_rule(
            StyleRule(
                dimension=dim,
                rule=rule,
                evidence=evidence,
                confidence=0.9,
                is_inferred=False,
                source_type="explicit",
            )
        )

    for dim, rule, evidence in dimensions:
        r = sb.get_rule(dim)
        assert r is not None
        assert r.rule == rule
        assert r.evidence == evidence
        assert r.is_inferred is False
        assert r.source_type == "explicit"
        assert r.confidence == 0.9


def test_style_bible_explicit_vs_inferred_differentiation() -> None:
    """Garante diferenciação estrita entre regras explícitas e inferências."""
    sb = StyleBible()
    sb.set_rule(
        StyleRule(
            dimension="narrator",
            rule="primeira pessoa",
            evidence="Prefácio do autor: 'Escrevi esta memória em primeira pessoa'",
            is_inferred=False,
            source_type="explicit",
            confidence=1.0,
        )
    )
    sb.set_rule(
        StyleRule(
            dimension="formality",
            rule="coloquial",
            evidence="Frequência alta de contrações no capítulo 1",
            is_inferred=True,
            source_type="inference",
            confidence=0.7,
        )
    )

    explicit_rules = sb.get_explicit_rules()
    inferred_rules = sb.get_inferred_rules()

    assert "narrator" in explicit_rules
    assert "formality" not in explicit_rules

    assert "formality" in inferred_rules
    assert "narrator" not in inferred_rules


def test_style_bible_locked_rules_prevent_unauthorized_override() -> None:
    """Verifica que regras travadas (locked) não são sobrescritas sem autorização explícita."""
    sb = StyleBible()
    sb.set_rule(
        StyleRule(
            dimension="dialogue_style",
            rule="travessão",
            evidence="Manual da editora",
            locked=True,
        )
    )

    # Tentativa de sobrescrever com inferência deve falhar
    ok_inferred = sb.set_rule(
        StyleRule(
            dimension="dialogue_style",
            rule="aspas",
            evidence="Trecho pontual com aspas",
            is_inferred=True,
        )
    )
    assert ok_inferred is False
    assert sb.get_rule("dialogue_style").rule == "travessão"

    # Tentativa de sobrescrever sem force=True deve falhar
    ok_normal = sb.set_rule(
        StyleRule(
            dimension="dialogue_style",
            rule="aspas",
            evidence="Outra evidência",
            locked=False,
        ),
        force=False,
    )
    assert ok_normal is False
    assert sb.get_rule("dialogue_style").rule == "travessão"

    # Com force=True, sobrescreve
    ok_force = sb.set_rule(
        StyleRule(
            dimension="dialogue_style",
            rule="aspas",
            evidence="Autorização do editor-chefe",
            locked=True,
        ),
        force=True,
    )
    assert ok_force is True
    assert sb.get_rule("dialogue_style").rule == "aspas"


def test_style_bible_contradiction_detection() -> None:
    """Testa detecção programática de contradições internas na Style Bible."""
    # 1. Narrador vs pessoa narrativa
    sb1 = StyleBible()
    sb1.narrator = "primeira pessoa (protagonista)"
    sb1.narrative_person = "3a"
    conflicts1 = sb1.detect_contradictions()
    assert any(c.term_or_name == "narrator_vs_person" for c in conflicts1)

    # 2. Formalidade vs tom incompatíveis
    sb2 = StyleBible()
    sb2.formality = "muito formal e solene"
    sb2.tone = "coloquial com gírias e humor chulo"
    conflicts2 = sb2.detect_contradictions()
    assert any(c.term_or_name == "formality_vs_tone" for c in conflicts2)

    # 3. Padrão de diálogo contradizendo convenções internas
    sb3 = StyleBible()
    sb3.dialogue_style = "travessão"
    sb3.internal_conventions = "todos os diálogos devem utilizar aspas inglesas obrigatoriamente"
    conflicts3 = sb3.detect_contradictions()
    assert any(c.term_or_name == "dialogue_convention_conflict" for c in conflicts3)

    # 4. Regra travada explícita colidindo com inferência
    sb4 = StyleBible()
    sb4.set_rule(
        StyleRule(
            dimension="treatment_forms",
            rule="você",
            evidence="Diretriz editorial expressa",
            locked=True,
            is_inferred=False,
        )
    )
    # Tentativa rejeitada mas registrada ou detectada
    sb4.rules["treatment_forms_candidate"] = StyleRule(
        dimension="treatment_forms",
        rule="tu",
        evidence="Inferido do capítulo 2",
        is_inferred=True,
    )
    conflicts4 = sb4.detect_contradictions()
    assert any("treatment_forms" in c.term_or_name for c in conflicts4)


def test_style_bible_qa_validation_rules() -> None:
    """Testa validação de texto de tradução contra regras da Style Bible."""
    sb = StyleBible()
    sb.dialogue_style = "travessão"
    sb.treatment_forms = "você"
    sb.profanity_policy = "censurar"
    sb.title_treatment = "manter original"

    # Violação de diálogo: uso de aspas quando o estilo exige travessão
    violations1 = sb.validate_text('"Olá, como vai você?", perguntou ele.')
    assert any(v.dimension == "dialogue_style" for v in violations1)

    # Violação de tratamento: uso de 'tu' quando a regra é 'você'
    violations2 = sb.validate_text("— Tu disseste a verdade?")
    assert any(v.dimension == "treatment_forms" for v in violations2)

    # Violação de palavrão quando a política é censurar
    violations3 = sb.validate_text("— Que porra é essa?")
    assert any(v.dimension == "profanity" for v in violations3)

    # Violação de títulos quando a regra é manter original e foi traduzido
    violations4 = sb.validate_text(
        "O senhor Blackwood e o conde de Essex.", source_text="Sir Blackwood and Earl of Essex."
    )
    assert any(v.dimension == "title_treatment" for v in violations4)
