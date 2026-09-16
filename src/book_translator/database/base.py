"""Contratos para persistência do projeto e memória incremental (SQLite + JSON)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_translator.context.base import TranslationContext
from book_translator.core.models import (
    Chapter,
    Checkpoint,
    Document,
    Entity,
    EventLog,
    Paragraph,
    Project,
    Section,
    Segment,
)
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    StyleBible,
    TranslationMemoryEntry,
)
from book_translator.qa.base import QAReport
from book_translator.translation.base import TranslationDraft


@runtime_checkable
class DatabaseInterface(Protocol):
    """Protocolo formal de persistência transacional e incremental do livro."""

    def initialize(self) -> None:
        """Inicializa a base de dados e executa migrations pendentes."""
        ...

    # Projetos e Documentos
    def save_project(self, project: Project) -> None:
        """Salva ou atualiza os metadados do projeto."""
        ...

    def load_project(self, project_id: str) -> Project | None:
        """Carrega um projeto existente a partir de seu identificador."""
        ...

    def save_document(self, document: Document, project_id: str) -> None:
        """Salva a estrutura intermediária de um documento."""
        ...

    def load_document(self, project_id: str) -> Document | None:
        """Carrega o documento completo e seus capítulos."""
        ...

    # Estrutura do Documento
    def save_chapter(self, chapter: Chapter, document_id: str) -> None:
        """Salva um capítulo no banco."""
        ...

    def save_section(self, section: Section) -> None:
        """Salva uma seção ou subseção."""
        ...

    def save_paragraph(self, paragraph: Paragraph) -> None:
        """Salva um parágrafo original."""
        ...

    def save_segment(self, segment: Segment) -> None:
        """Persiste um segmento individual imediatamente (checkpointing)."""
        ...

    def get_segment(self, segment_id: str) -> Segment | None:
        """Recupera um segmento salvo pelo seu identificador permanente."""
        ...

    def get_segments_by_chapter(self, chapter_id: str) -> list[Segment]:
        """Retorna todos os segmentos pertencentes a um capítulo."""
        ...

    def get_pending_segments(self, project_id: str) -> list[Segment]:
        """Retorna todos os segmentos pendentes de tradução."""
        ...

    def count_translated_segments(self, project_id: str) -> int:
        """Retorna o número de segmentos já concluídos."""
        ...

    def count_total_segments(self, project_id: str) -> int:
        """Retorna a quantidade total de segmentos da obra."""
        ...

    # Entidades e Memórias
    def save_entity(self, entity: Entity) -> None:
        """Salva uma entidade identificada na obra."""
        ...

    def get_entities(self, project_id: str) -> list[Entity]:
        """Recupera entidades do projeto."""
        ...

    def save_character(self, project_id: str, character: CharacterEntry) -> None:
        """Salva ou atualiza um personagem na Character Memory."""
        ...

    def get_characters(self, project_id: str) -> list[CharacterEntry]:
        """Retorna todos os personagens cadastrados."""
        ...

    def save_glossary_entry(self, project_id: str, entry: GlossaryEntry) -> None:
        """Salva ou atualiza uma entrada de Glossário."""
        ...

    def get_glossary(self, project_id: str) -> list[GlossaryEntry]:
        """Retorna todos os termos do glossário do projeto."""
        ...

    def save_tm_entry(self, project_id: str, entry: TranslationMemoryEntry) -> None:
        """Salva ou atualiza um termo na Translation Memory."""
        ...

    def get_tm(self, project_id: str) -> list[TranslationMemoryEntry]:
        """Retorna todas as entradas da Translation Memory."""
        ...

    def save_style_bible(self, project_id: str, style_bible: StyleBible) -> None:
        """Salva as diretrizes de estilo do projeto."""
        ...

    def get_style_bible(self, project_id: str) -> StyleBible | None:
        """Recupera a Style Bible do projeto."""
        ...

    # Contexto e Traduções
    def save_context(self, context: TranslationContext) -> None:
        """Armazena o contexto gerado para um segmento."""
        ...

    def get_context(self, segment_id: str) -> TranslationContext | None:
        """Recupera o contexto associado a um segmento."""
        ...

    def save_translation_draft(self, draft: TranslationDraft) -> None:
        """Salva rascunho de tradução e suas hipóteses candidatas."""
        ...

    def save_revision(
        self,
        segment_id: str,
        old_text: str,
        new_text: str,
        revised_by: str,
        reason: str = "",
    ) -> None:
        """Registra uma revisão/edição de segmento no histórico."""
        ...

    # QA e Validação
    def save_qa_report(self, report: QAReport) -> None:
        """Salva as anomalias e o relatório de QA de um segmento."""
        ...

    # Checkpoints e Eventos
    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Grava ponto de restauração do projeto."""
        ...

    def get_latest_checkpoint(self, project_id: str) -> Checkpoint | None:
        """Recupera o ponto de restauração mais recente do projeto."""
        ...

    def log_event(self, event: EventLog) -> None:
        """Registra um evento ou erro no log persistente do projeto."""
        ...

    def close(self) -> None:
        """Encerra com segurança a conexão com a base de dados."""
        ...
