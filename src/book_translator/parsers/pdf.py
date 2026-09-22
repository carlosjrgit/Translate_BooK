"""Analisador de documentos PDF com detecção de camada textual e heurísticas de limpeza."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pypdf

from book_translator.core.document import (
    Chapter,
    DialogueBlock,
    Document,
    Heading,
    Paragraph,
    SourceLocation,
)
from book_translator.core.ids import (
    generate_chapter_id,
    generate_dialogue_id,
    generate_heading_id,
    generate_paragraph_id,
)
from book_translator.errors import NeedsOcrError, ParsingError
from book_translator.logging import get_logger
from book_translator.parsers.base import BaseParser
from book_translator.parsers.normalization import normalize_unicode

logger = get_logger("parsers.pdf")


class PdfClassification(str, Enum):
    """Classificação da qualidade da camada textual de um PDF."""

    TEXTUAL = "TEXTUAL"
    MIXED = "MIXED"
    SCANNED_NEEDS_OCR = "SCANNED_NEEDS_OCR"


@dataclass
class PdfParserConfig:
    """Configurações e parâmetros de heurísticas para extração e limpeza de PDF."""

    # Heurísticas de limpeza
    fix_hyphenation: bool = True
    remove_headers_footers: bool = True
    remove_page_numbers: bool = True

    # Limiares de detecção de Headers/Footers recorrentes
    header_footer_frequency_threshold: float = 0.35
    header_margin_lines: int = 2
    footer_margin_lines: int = 2

    # Limiares de qualidade textual
    min_page_char_count: int = 40
    min_printable_ratio: float = 0.75
    scanned_page_threshold: float = 0.80
    textual_page_threshold: float = 0.85

    # Detecção de títulos e capítulos
    detect_headings: bool = True


# Padrões regex para limpeza e detecção
PAGE_NUMBER_REGEX = re.compile(
    r"^\s*(?:page|página|p\.)?\s*(\d+|[ivxlcdm]+)\s*(?:(?:of|de|/)\s*\d+)?\s*$",
    re.IGNORECASE,
)
PAGE_NUMBER_DASH_REGEX = re.compile(r"^\s*[-—–]\s*(\d+|[ivxlcdm]+)\s*[-—–]\s*$", re.IGNORECASE)

CHAPTER_HEADING_REGEX = re.compile(
    r"^\s*(?:CHAPTER|CAPÍTULO|ACT|SCENE|PART|PARTE|BOOK|LIVRO)\s+([0-9IVXLCDM]+[\.\:]?.*|[A-ZÀ-ÿ\s]+)\s*$",
    re.IGNORECASE,
)

DEHYPHENATION_REGEX = re.compile(r"(\b[a-zA-ZÀ-ÿ]+)[-\xad]\s*\n\s*([a-zà-ÿ]+)")


class PdfParser(BaseParser):
    """Parser para arquivos PDF com camada textual e detecção de documentos escaneados."""

    def __init__(
        self,
        config: PdfParserConfig | None = None,
        ocr_service: Any | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.config = config or PdfParserConfig()
        self.ocr_service = ocr_service

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return (".pdf",)

    def parse(self, file_path: Path | str, title: str | None = None) -> Document:
        """Executa a extração estruturada de um PDF com camada textual ou OCR opcional.

        Lança NeedsOcrError caso o PDF seja classificado como SCANNED_NEEDS_OCR e nenhum
        serviço de OCR tenha sido fornecido.
        """
        path = self.validate_source_file(file_path)
        logger.info(f"Iniciando análise de PDF: '{path.name}'")

        try:
            with path.open("rb") as f:
                reader = pypdf.PdfReader(f)
                num_pages = len(reader.pages)

                if num_pages == 0:
                    raise NeedsOcrError(
                        f"PDF vazio ou sem páginas: '{path.name}' "
                        "(classificação: SCANNED_NEEDS_OCR)"
                    )

                # 1. Avaliação de qualidade e classificação do documento
                classification, diagnostics = self.classify_pdf(reader)
                logger.info(
                    f"Classificação do PDF '{path.name}': {classification.value} "
                    f"({diagnostics['good_pages']}/{num_pages} páginas textuais)"
                )

                pages_ocr_info: dict[int, dict[str, Any]] = {}
                raw_pages: list[list[str]] = []

                if classification == PdfClassification.TEXTUAL:
                    # REGRA: Nunca rodar OCR em PDF textual válido
                    logger.debug("PDF 100% textual. Extração direta sem OCR.")
                    for p_idx, page in enumerate(reader.pages):
                        page_num = p_idx + 1
                        try:
                            p_text = page.extract_text() or ""
                        except Exception as e:
                            logger.warning(f"Erro ao extrair texto da página {page_num}: {e}")
                            p_text = ""
                        p_text = normalize_unicode(p_text)
                        lines = [line.strip() for line in p_text.splitlines() if line.strip()]
                        raw_pages.append(lines)
                        pages_ocr_info[page_num] = {"is_ocr": False}

                elif classification == PdfClassification.SCANNED_NEEDS_OCR:
                    if self.ocr_service is None:
                        raise NeedsOcrError(
                            f"O arquivo PDF '{path.name}' não possui camada de texto utilizável "
                            f"(classificação: {classification.value}). Requer OCR para processamento."
                        )
                    logger.info(f"Acionando OCR para PDF escaneado '{path.name}' ({num_pages} páginas)...")
                    ocr_doc = self.ocr_service.process_scanned_pdf(
                        path, page_numbers=list(range(1, num_pages + 1))
                    )
                    for page_res in ocr_doc.pages:
                        p_num = page_res.page_number
                        p_text = normalize_unicode(page_res.text)
                        lines = [line.strip() for line in p_text.splitlines() if line.strip()]
                        raw_pages.append(lines)
                        pages_ocr_info[p_num] = {
                            "is_ocr": True,
                            "ocr_confidence": page_res.confidence,
                            "ocr_engine": page_res.engine_name,
                            "needs_review": page_res.needs_review,
                            "page_number": p_num,
                        }

                elif classification == PdfClassification.MIXED:
                    logger.info(f"Processando PDF misto '{path.name}'...")
                    for p_idx, page in enumerate(reader.pages):
                        page_num = p_idx + 1
                        try:
                            p_text = page.extract_text() or ""
                        except Exception:
                            p_text = ""
                        p_text_norm = normalize_unicode(p_text).strip()

                        # Verifica se esta página específica necessita de OCR
                        char_count = len(p_text_norm)
                        printable_count = sum(
                            1 for c in p_text_norm
                            if not unicodedata.category(c).startswith("C") and c != "\ufffd"
                        )
                        ratio = printable_count / char_count if char_count > 0 else 0.0

                        is_page_scanned = (
                            char_count < self.config.min_page_char_count
                            or ratio < self.config.min_printable_ratio
                        )

                        if is_page_scanned and self.ocr_service is not None:
                            logger.info(f"Página {page_num} com baixa qualidade textual. Aplicando OCR...")
                            ocr_res, _ = self.ocr_service.process_page_with_cache(path, page_num)
                            p_text_norm = normalize_unicode(ocr_res.text).strip()
                            pages_ocr_info[page_num] = {
                                "is_ocr": True,
                                "ocr_confidence": ocr_res.confidence,
                                "ocr_engine": ocr_res.engine_name,
                                "needs_review": ocr_res.needs_review,
                                "page_number": page_num,
                            }
                        else:
                            pages_ocr_info[page_num] = {"is_ocr": False, "page_number": page_num}

                        lines = [line.strip() for line in p_text_norm.splitlines() if line.strip()]
                        raw_pages.append(lines)

                # 3. Aplicação de heurísticas de limpeza (cabeçalhos, rodapés, paginação)
                cleaned_pages = self._clean_pages(raw_pages)

                # 4. Obtenção de metadados do documento
                doc_title = title
                doc_author = "Desconhecido"
                if reader.metadata:
                    if not doc_title and reader.metadata.title:
                        doc_title = normalize_unicode(str(reader.metadata.title)).strip()
                    if reader.metadata.author:
                        doc_author = normalize_unicode(str(reader.metadata.author)).strip()

                doc = self.create_base_document(
                    file_path=path,
                    source_format="pdf",
                    title=doc_title,
                    author=doc_author,
                )
                doc.metadata.extra["pdf_classification"] = classification.value
                doc.metadata.extra["pdf_diagnostics"] = diagnostics
                doc.metadata.extra["is_ocr"] = any(info.get("is_ocr") for info in pages_ocr_info.values())
                ocr_scores = [
                    info["ocr_confidence"]
                    for info in pages_ocr_info.values()
                    if info.get("ocr_confidence") is not None
                ]
                if ocr_scores:
                    doc.metadata.extra["ocr_mean_confidence"] = round(sum(ocr_scores) / len(ocr_scores), 4)

                # 5. Reconstrução de blocos, headings e capítulos
                chapters = self._reconstruct_document_structure(
                    cleaned_pages, doc.id, path, pages_ocr_info=pages_ocr_info
                )
                if not chapters:
                    raise ParsingError(
                        f"Não foi possível extrair nenhum bloco de leitura do PDF '{path.name}'."
                    )

                doc.chapters = chapters
                logger.info(
                    f"PDF '{path.name}' processado com sucesso: {len(chapters)} capítulos, "
                    f"{sum(len(c.paragraphs) for c in chapters)} parágrafos."
                )
                return doc


        except NeedsOcrError:
            raise
        except pypdf.errors.PdfStreamError as e:
            raise ParsingError(f"Arquivo PDF corrompido ou stream inválido: '{path.name}'") from e
        except ParsingError:
            raise
        except Exception as e:
            raise ParsingError(f"Falha inesperada ao processar PDF '{path.name}': {e}") from e

    def classify_pdf(self, reader: pypdf.PdfReader) -> tuple[PdfClassification, dict]:
        """Avalia cada página do PDF e classifica o documento como TEXTUAL, MIXED ou SCANNED."""
        num_pages = len(reader.pages)
        if num_pages == 0:
            return PdfClassification.SCANNED_NEEDS_OCR, {
                "total_pages": 0,
                "good_pages": 0,
                "scanned_pages": 0,
                "good_ratio": 0.0,
            }

        good_pages = 0
        scanned_pages = 0

        for p_idx, page in enumerate(reader.pages):
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""

            txt_norm = unicodedata.normalize("NFC", txt).strip()
            char_count = len(txt_norm)

            if char_count < self.config.min_page_char_count:
                scanned_pages += 1
                continue

            # Avalia proporção de caracteres imprimíveis normais
            printable_count = sum(
                1 for c in txt_norm if not unicodedata.category(c).startswith("C") and c != "\ufffd"
            )
            ratio = printable_count / char_count if char_count > 0 else 0.0

            if ratio < self.config.min_printable_ratio:
                scanned_pages += 1
            else:
                good_pages += 1

        good_ratio = good_pages / num_pages
        scanned_ratio = scanned_pages / num_pages

        diagnostics = {
            "total_pages": num_pages,
            "good_pages": good_pages,
            "scanned_pages": scanned_pages,
            "good_ratio": round(good_ratio, 4),
        }

        if scanned_ratio >= self.config.scanned_page_threshold or good_pages == 0:
            classification = PdfClassification.SCANNED_NEEDS_OCR
        elif good_ratio >= self.config.textual_page_threshold:
            classification = PdfClassification.TEXTUAL
        else:
            classification = PdfClassification.MIXED

        return classification, diagnostics

    def _clean_pages(self, raw_pages: list[list[str]]) -> list[list[str]]:
        """Aplica heurísticas de eliminação de cabeçalhos/rodapés repetidos e números de página."""
        total_pages = len(raw_pages)
        if total_pages == 0:
            return []

        # 1. Identificação de cabeçalhos e rodapés recorrentes entre páginas distintas
        recurring_headers: set[str] = set()
        recurring_footers: set[str] = set()

        if self.config.remove_headers_footers and total_pages >= 2:
            header_page_counts: dict[str, int] = {}
            footer_page_counts: dict[str, int] = {}

            for lines in raw_pages:
                num_l = len(lines)
                if num_l == 0:
                    continue

                top_limit = (
                    min(self.config.header_margin_lines, num_l // 2)
                    if num_l >= 3
                    else 1
                    if num_l == 2
                    else 0
                )
                bottom_limit = (
                    min(self.config.footer_margin_lines, num_l // 2)
                    if num_l >= 3
                    else 1
                    if num_l == 2
                    else 0
                )

                top_candidates = {
                    line.lower().strip() for line in lines[:top_limit] if line.strip()
                }
                bottom_candidates = (
                    {line.lower().strip() for line in lines[num_l - bottom_limit :] if line.strip()}
                    if bottom_limit > 0
                    else set()
                )

                for h in top_candidates:
                    header_page_counts[h] = header_page_counts.get(h, 0) + 1
                for f in bottom_candidates:
                    footer_page_counts[f] = footer_page_counts.get(f, 0) + 1

            threshold = max(2, int(total_pages * self.config.header_footer_frequency_threshold))
            recurring_headers = {h for h, count in header_page_counts.items() if count >= threshold}
            recurring_footers = {f for f, count in footer_page_counts.items() if count >= threshold}

        # 2. Filtragem de cada página
        cleaned_pages: list[list[str]] = []
        for lines in raw_pages:
            num_l = len(lines)
            top_limit = (
                min(self.config.header_margin_lines, num_l // 2)
                if num_l >= 3
                else 1
                if num_l == 2
                else 0
            )
            bottom_limit = (
                min(self.config.footer_margin_lines, num_l // 2)
                if num_l >= 3
                else 1
                if num_l == 2
                else 0
            )

            filtered_lines: list[str] = []
            for idx, line in enumerate(lines):
                norm = line.lower().strip()

                if idx < top_limit:
                    if self.config.remove_headers_footers and norm in recurring_headers:
                        continue
                    if self.config.remove_page_numbers and (
                        PAGE_NUMBER_REGEX.match(line) or PAGE_NUMBER_DASH_REGEX.match(line)
                    ):
                        continue
                elif idx >= num_l - bottom_limit:
                    if self.config.remove_headers_footers and norm in recurring_footers:
                        continue
                    if self.config.remove_page_numbers and (
                        PAGE_NUMBER_REGEX.match(line) or PAGE_NUMBER_DASH_REGEX.match(line)
                    ):
                        continue

                filtered_lines.append(line)

            cleaned_pages.append(filtered_lines)

        return cleaned_pages

    def _reconstruct_document_structure(
        self,
        cleaned_pages: list[list[str]],
        doc_id: str,
        file_path: Path,
        pages_ocr_info: dict[int, dict[str, Any]] | None = None,
    ) -> list[Chapter]:
        """Reconstrói blocos de leitura, headings e capítulos a partir das páginas limpas."""
        chapters: list[Chapter] = []
        ch_counter = 1
        reading_order = 1
        ocr_info_map = pages_ocr_info or {}

        curr_ch_id = generate_chapter_id(doc_id, ch_counter)
        curr_chapter = Chapter(
            id=curr_ch_id,
            title="Início",
            order=ch_counter,
            reading_order=ch_counter,
            metadata={"source_file_path": str(file_path)},
        )

        pending_para_lines: list[str] = []
        pending_line_num: int = 1
        pending_page_num: int = 1
        pending_ocr_meta: dict[str, Any] = {}

        def flush_paragraph() -> None:
            nonlocal reading_order, curr_chapter, pending_line_num, pending_page_num, pending_ocr_meta
            if not pending_para_lines:
                return
            para_text = " ".join(pending_para_lines).strip()
            pending_para_lines.clear()
            if not para_text:
                return

            p_id = generate_paragraph_id(curr_chapter.id, len(curr_chapter.paragraphs) + 1)
            curr_chapter.paragraphs.append(
                Paragraph(
                    id=p_id,
                    chapter_id=curr_chapter.id,
                    raw_text=para_text,
                    normalized_text=para_text,
                    order_index=len(curr_chapter.paragraphs) + 1,
                    reading_order=reading_order,
                    source_location=SourceLocation(
                        file_path=str(file_path),
                        page_number=pending_page_num,
                        line_number=pending_line_num,
                    ),
                    metadata=dict(pending_ocr_meta),
                )
            )
            reading_order += 1

        for p_idx, raw_lines in enumerate(cleaned_pages):
            page_num = p_idx + 1
            if not raw_lines:
                continue

            page_ocr_meta = dict(ocr_info_map.get(page_num, {"is_ocr": False, "page_number": page_num}))

            # Heurística: Desifenização entre linhas consecutivas
            lines: list[str] = []
            if self.config.fix_hyphenation and len(raw_lines) >= 2:
                idx = 0
                while idx < len(raw_lines):
                    curr = raw_lines[idx]
                    if idx + 1 < len(raw_lines) and re.search(r"[a-zA-ZÀ-ÿ]+[-\xad]\s*$", curr):
                        next_l = raw_lines[idx + 1]
                        m = re.match(r"^\s*([a-zà-ÿ]+)(.*)", next_l)
                        if m:
                            base_word = re.sub(r"[-\xad]\s*$", "", curr)
                            joined_word = base_word + m.group(1)
                            rest = m.group(2).strip()
                            if rest:
                                lines.append(joined_word)
                                raw_lines[idx + 1] = rest
                            else:
                                lines.append(joined_word)
                                idx += 1
                            idx += 1
                            continue
                    lines.append(curr)
                    idx += 1
            else:
                lines = list(raw_lines)

            # Desifenização entre o fim da página anterior e o início da página atual
            if self.config.fix_hyphenation and pending_para_lines and lines:
                last_p_line = pending_para_lines[-1]
                if re.search(r"[a-zA-ZÀ-ÿ]+[-\xad]\s*$", last_p_line):
                    first_l = lines[0]
                    m = re.match(r"^\s*([a-zà-ÿ]+)(.*)", first_l)
                    if m:
                        base_word = re.sub(r"[-\xad]\s*$", "", last_p_line)
                        pending_para_lines[-1] = base_word + m.group(1)
                        rest = m.group(2).strip()
                        if rest:
                            lines[0] = rest
                        else:
                            lines.pop(0)

            line_lens = [len(line_item.strip()) for line_item in lines if line_item.strip()]
            max_line_len = max(line_lens) if line_lens else 80

            for line_idx, line in enumerate(lines):
                line_str = line.strip()
                if not line_str:
                    flush_paragraph()
                    continue

                # 1. Verifica se a linha é um Heading de capítulo
                is_ch_heading = False
                if self.config.detect_headings:
                    if CHAPTER_HEADING_REGEX.match(line_str):
                        is_ch_heading = True
                    elif (
                        len(line_str) < 50
                        and line_str.isupper()
                        and len(line_str.split()) <= 6
                        and not line_str.endswith(('"', "'", "”", "’", ",", ";", "-", "—"))
                        and not (pending_para_lines and not re.search(r'[.?!:]["\'”’)]?$', pending_para_lines[-1].strip()))
                    ):
                        is_ch_heading = True

                if is_ch_heading:
                    flush_paragraph()
                    # Se o capítulo atual já possui conteúdo, abre novo capítulo
                    if (
                        curr_chapter.paragraphs
                        or curr_chapter.headings
                        or curr_chapter.dialogue_blocks
                    ):
                        chapters.append(curr_chapter)
                        ch_counter += 1
                        curr_ch_id = generate_chapter_id(doc_id, ch_counter)
                        curr_chapter = Chapter(
                            id=curr_ch_id,
                            title=line_str,
                            order=ch_counter,
                            reading_order=ch_counter,
                            metadata={"source_file_path": str(file_path)},
                        )
                    else:
                        curr_chapter.title = line_str

                    h_id = generate_heading_id(curr_chapter.id, len(curr_chapter.headings) + 1)
                    curr_chapter.headings.append(
                        Heading(
                            id=h_id,
                            chapter_id=curr_chapter.id,
                            level=1,
                            raw_text=line_str,
                            normalized_text=line_str,
                            reading_order=reading_order,
                            source_location=SourceLocation(
                                file_path=str(file_path),
                                page_number=page_num,
                                line_number=line_idx + 1,
                            ),
                            metadata=dict(page_ocr_meta),
                        )
                    )
                    reading_order += 1
                    continue

                # 2. Verifica se a linha é um Bloco de Diálogo
                is_diag, marker, clean_text = self.identify_dialogue(line_str)
                # Se estamos no meio de um parágrafo cuja oração não foi concluída,
                # um travessão inicial é parentético/intrafrasal, e NÃO um novo diálogo.
                if is_diag and marker in ("—", "–", "―", "-"):
                    if pending_para_lines and not re.search(r'[.?!:]["\'”’)]?$', pending_para_lines[-1].strip()):
                        is_diag = False

                if is_diag:
                    flush_paragraph()
                    d_id = generate_dialogue_id(
                        curr_chapter.id, len(curr_chapter.dialogue_blocks) + 1
                    )
                    curr_chapter.dialogue_blocks.append(
                        DialogueBlock(
                            id=d_id,
                            chapter_id=curr_chapter.id,
                            dialogue_marker=marker,
                            raw_text=line_str,
                            normalized_text=clean_text,
                            reading_order=reading_order,
                            source_location=SourceLocation(
                                file_path=str(file_path),
                                page_number=page_num,
                                line_number=line_idx + 1,
                            ),
                            metadata=dict(page_ocr_meta),
                        )
                    )
                    reading_order += 1
                    continue

                # 3. Linha de parágrafo comum
                if not pending_para_lines:
                    pending_page_num = page_num
                    pending_line_num = line_idx + 1
                    pending_ocr_meta = dict(page_ocr_meta)
                pending_para_lines.append(line_str)

                # Heurística de final de parágrafo para páginas sem linhas em branco
                has_terminal = bool(re.search(r'[.?!]["\'”’)]?$', line_str))
                if has_terminal and len(line_str) < max_line_len * 0.72:
                    next_is_lower = False
                    if line_idx + 1 < len(lines):
                        next_str = lines[line_idx + 1].strip()
                        if next_str and next_str[0].islower():
                            next_is_lower = True
                    if not next_is_lower:
                        flush_paragraph()

            # Fim da página: se terminar com pontuação terminal e for página curta ou linha curta
            if pending_para_lines and lines:
                last_l = pending_para_lines[-1].strip()
                has_terminal = bool(re.search(r'[.?!]["\'”’)]?$', last_l))
                if has_terminal:
                    if len(lines) <= 3 or len(last_l) < max_line_len * 0.72:
                        flush_paragraph()

        flush_paragraph()

        if curr_chapter.paragraphs or curr_chapter.headings or curr_chapter.dialogue_blocks:
            chapters.append(curr_chapter)

        return chapters


