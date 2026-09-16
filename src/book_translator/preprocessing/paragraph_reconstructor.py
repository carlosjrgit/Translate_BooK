"""Reconstrução de parágrafos e identificação de quebras estruturais e de cena."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from book_translator.preprocessing.config import PreprocessingConfig

# Padrões comuns de marcadores de diálogo no início da linha
DIALOGUE_START_REGEX = re.compile(r"^[\s]*[—–―\"“«\-]")

# Padrões de listas numeradas ou marcadores
LIST_ITEM_REGEX = re.compile(r"^[\s]*(\d+[\.\)]|[-*•])\s+")


@dataclass
class ReconstructedBlock:
    """Bloco textual reconstruído com metadados de quebra e rastreabilidade."""

    text: str
    is_scene_break: bool = False
    scene_marker: str | None = None
    is_dialogue_candidate: bool = False
    is_heading_candidate: bool = False
    original_line_start: int = 1
    original_line_end: int = 1
    metadata: dict[str, str] = field(default_factory=dict)


class ParagraphReconstructor:
    """Reconstrói parágrafos a partir de linhas com quebras suaves, preservando quebras duras."""

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()

    def is_scene_break_line(self, line: str) -> tuple[bool, str | None]:
        """Verifica se uma linha isolada é um separador de cena (ex: * * * ou ---)."""
        trimmed = line.strip()
        if not trimmed:
            return False, None

        for symbol in self.config.scene_break_symbols:
            if trimmed == symbol:
                return True, symbol

        # Verifica variações com espaços (ex: *  *  *)
        if re.fullmatch(r"^(\*\s*){3,}$", trimmed):
            return True, "* * *"
        if re.fullmatch(r"^(-{3,}|_{3,}|#{3,})$", trimmed):
            return True, trimmed

        return False, None

    def reconstruct(self, raw_text: str) -> list[ReconstructedBlock]:
        """Processa texto contendo quebras de linha e retorna blocos lógicos reconstruídos."""
        if not raw_text.strip():
            return []

        lines = raw_text.split("\n")
        blocks: list[ReconstructedBlock] = []

        current_lines: list[str] = []
        current_start_line = 1

        def flush_current(end_line: int) -> None:
            nonlocal current_lines, current_start_line
            if not current_lines:
                return

            joined_text = " ".join(part.strip() for part in current_lines if part.strip())
            if joined_text:
                is_diag = bool(DIALOGUE_START_REGEX.match(joined_text))
                blocks.append(
                    ReconstructedBlock(
                        text=joined_text,
                        is_scene_break=False,
                        is_dialogue_candidate=is_diag,
                        original_line_start=current_start_line,
                        original_line_end=end_line,
                    )
                )
            current_lines = []

        for idx, line in enumerate(lines, start=1):
            trimmed = line.strip()

            # 1. Linha em branco -> quebra dura de parágrafo
            if not trimmed:
                flush_current(idx - 1)
                current_start_line = idx + 1
                continue

            # 2. Separador de cena
            if self.config.detect_scene_breaks:
                is_scene, marker = self.is_scene_break_line(trimmed)
                if is_scene:
                    flush_current(idx - 1)
                    blocks.append(
                        ReconstructedBlock(
                            text=trimmed,
                            is_scene_break=True,
                            scene_marker=marker,
                            original_line_start=idx,
                            original_line_end=idx,
                        )
                    )
                    current_start_line = idx + 1
                    continue

            # 3. Se a linha iniciar um novo diálogo ou item de lista, quebra o parágrafo anterior
            if DIALOGUE_START_REGEX.match(line) or LIST_ITEM_REGEX.match(line):
                if current_lines:
                    flush_current(idx - 1)
                    current_start_line = idx

            # Se não estivermos acumulando ainda, define a linha inicial
            if not current_lines:
                current_start_line = idx

            current_lines.append(trimmed)

        flush_current(len(lines))
        return blocks
