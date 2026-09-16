"""Geração determinística de IDs estáveis para as unidades estruturais do livro."""

from __future__ import annotations

import hashlib
import re
import unicodedata


def slugify(text: str) -> str:
    """Converte um texto em slug alfanumérico seguro para diretórios e identificadores.

    Remove acentos, converte para minúsculas e substitui caracteres não-alfanuméricos
    por underscores.
    """
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    slug = re.sub(r"[-\s]+", "_", slug)
    return slug or "untitled"


def compute_content_hash(text: str) -> str:
    """Gera um hash SHA-256 estável e determinístico de 16 caracteres a partir do texto."""
    normalized_text = " ".join(text.strip().split())
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]


def generate_project_id(book_title: str) -> str:
    """Gera o identificador canônico de projeto a partir do título da obra."""
    return slugify(book_title)


def generate_document_id(project_id: str) -> str:
    """Gera o identificador canônico do documento intermediário."""
    return f"doc_{project_id}"


def generate_chapter_id(order_index: int) -> str:
    """Gera identificador canônico de capítulo ordenado (ex: ch_0001)."""
    return f"ch_{order_index:04d}"


def generate_section_id(chapter_id: str, order_index: int) -> str:
    """Gera identificador canônico de seção/subseção (ex: ch_0001_sec_0001)."""
    return f"{chapter_id}_sec_{order_index:04d}"


def generate_paragraph_id(chapter_id: str, order_index: int) -> str:
    """Gera identificador canônico de parágrafo (ex: ch_0001_p_00001)."""
    return f"{chapter_id}_p_{order_index:05d}"


def generate_segment_id(chapter_id: str, order_index: int) -> str:
    """Gera identificador estável e permanente de segmento (ex: ch_0001_seg_00001)."""
    return f"{chapter_id}_seg_{order_index:05d}"
