"""Testes integrados do BookAnalyzer e persistência em memórias do projeto."""

from __future__ import annotations

from pathlib import Path

from book_translator.analysis.book_analyzer import BookAnalyzer
from book_translator.core.document import Document, DocumentMetadata
from book_translator.core.models import Chapter, Heading, Paragraph, Project, ProjectMetadata
from book_translator.database.sqlite import SQLiteDatabase


def test_book_analyzer_full_document_scan() -> None:
    analyzer = BookAnalyzer()

    doc = Document(id="doc_test_1", metadata=DocumentMetadata(title="A Study in Analysis"))

    # Capítulo 1
    ch1 = Chapter(id="ch_0001", title="Chapter 1", order=1)
    ch1.headings.append(
        Heading(id="h1", chapter_id="ch_0001", level=1, raw_text="Chapter 1", reading_order=1)
    )
    ch1.paragraphs.append(
        Paragraph(
            id="p1",
            chapter_id="ch_0001",
            raw_text="Dr. John Watson resided in Baker Street for several years.",
            reading_order=2,
        )
    )
    ch1.paragraphs.append(
        Paragraph(
            id="p2",
            chapter_id="ch_0001",
            raw_text="Sherlock Holmes observed Watson with quiet amusement.",
            reading_order=3,
        )
    )
    doc.chapters.append(ch1)

    # Capítulo 2
    ch2 = Chapter(id="ch_0002", title="Chapter 2", order=2)
    ch2.headings.append(
        Heading(id="h2", chapter_id="ch_0002", level=1, raw_text="Chapter 2", reading_order=1)
    )
    ch2.paragraphs.append(
        Paragraph(
            id="p3",
            chapter_id="ch_0002",
            raw_text="Inspector Lestrade from Scotland Yard requested their assistance.",
            reading_order=2,
        )
    )
    ch2.paragraphs.append(
        Paragraph(
            id="p4",
            chapter_id="ch_0002",
            raw_text="Arthur's mother Lady Margaret waited outside the room.",
            reading_order=3,
        )
    )
    doc.chapters.append(ch2)

    report = analyzer.analyze(doc)

    assert len(report.entities) >= 4

    names = [e.canonical_name for e in report.entities]
    assert any("Watson" in n for n in names)
    assert any("Holmes" in n for n in names)
    assert "Baker Street" in report.detected_locations
    assert "Scotland Yard" in report.detected_organizations

    # Valida gênero inferido para os personagens principais
    watson_ent = next(e for e in report.entities if "Watson" in e.canonical_name)
    assert watson_ent.gender == "masculine"
    assert "Dr." in watson_ent.honorifics

    margaret_ent = next((e for e in report.entities if "Margaret" in e.canonical_name), None)
    if margaret_ent:
        assert margaret_ent.gender == "feminine"
        assert "Lady" in margaret_ent.honorifics

    # Valida relações encontradas
    rel_types = [r.relation_type for r in report.relationships]
    assert "mother_of" in rel_types

    # Narrador em terceira pessoa
    assert report.predominant_narrator == "terceira pessoa"


def test_book_analyzer_first_person_narrator() -> None:
    analyzer = BookAnalyzer()

    doc = Document(id="doc_1st", metadata=DocumentMetadata(title="My Memoirs"))
    ch = Chapter(id="ch_0001", title="Chapter 1", order=1)
    ch.paragraphs.append(
        Paragraph(
            id="p1",
            chapter_id="ch_0001",
            raw_text="I walked through the empty city, wondering what my future held for me.",
            reading_order=1,
        )
    )
    ch.paragraphs.append(
        Paragraph(
            id="p2",
            chapter_id="ch_0001",
            raw_text="We decided that our only hope was to pack our bags and leave.",
            reading_order=2,
        )
    )
    doc.chapters.append(ch)

    report = analyzer.analyze(doc)
    assert report.predominant_narrator == "primeira pessoa"


def test_populate_project_memory(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "analyzer_mem_test.db")
    db.initialize()

    proj_meta = ProjectMetadata(
        project_id="test_analysis_proj",
        book_title="Analysis Project",
        source_file_path="book.txt",
    )
    db.save_project(Project(metadata=proj_meta, project_dir=tmp_path, db_path=db.db_path))

    doc = Document(id="doc_mem", metadata=DocumentMetadata(title="Memory Book"))
    ch = Chapter(id="ch_0001", title="Ch 1", order=1)
    ch.paragraphs.append(
        Paragraph(
            id="p1",
            chapter_id="ch_0001",
            raw_text="Dr. John Watson visited Baker Street.",
            reading_order=1,
        )
    )
    doc.chapters.append(ch)

    analyzer = BookAnalyzer()
    report = analyzer.analyze(doc)

    # Injeta no banco do projeto
    analyzer.populate_project_memory(report, db, "test_analysis_proj")

    # Verifica persistência de Character e Entity
    chars = db.get_characters("test_analysis_proj")
    assert len(chars) >= 1
    assert any("Watson" in c.name for c in chars)

    entities = db.get_entities("test_analysis_proj")
    assert len(entities) >= 1
    assert any(e.name == "Baker Street" for e in entities)

    # Verifica persistência da Style Bible
    sb = db.get_style_bible("test_analysis_proj")
    assert sb is not None
    assert sb.narrator != ""

    db.close()
