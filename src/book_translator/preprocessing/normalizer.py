"""Normalização Unicode, sanitização de caracteres de controle e espaços."""

from __future__ import annotations

import re
import unicodedata

from book_translator.preprocessing.config import PreprocessingConfig

# Caracteres de controle a serem removidos, preservando \n (10), \r (13) e \t (9)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufeff\u200b-\u200f]")

# Espaços Unicode não usuais a serem convertidos para espaço padrão (0x20)
SPECIAL_SPACES_REGEX = re.compile(r"[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]")


class UnicodeNormalizer:
    """Normalizador canônico de texto para garantir consistência tipográfica e semântica."""

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()

    def normalize(self, text: str) -> str:
        """Aplica o fluxo completo de normalização textual conforme a configuração."""
        if not text:
            return ""

        result = text

        # 1. Unificação inicial de quebras de linha
        result = result.replace("\r\n", "\n").replace("\r", "\n")

        # 2. Normalização Unicode (padrão NFKC)
        if self.config.normalize_unicode:
            result = unicodedata.normalize(self.config.unicode_form, result)

        # 3. Remoção de caracteres de controle invisíveis e zero-width
        if self.config.clean_control_chars:
            result = CONTROL_CHAR_REGEX.sub("", result)

        # 4. Padronização de espaços em branco especiais
        if self.config.standardize_whitespace:
            result = SPECIAL_SPACES_REGEX.sub(" ", result)
            # Remove espaços no fim de cada linha, mantendo a estrutura de linhas
            lines = [re.sub(r"[ \t]+$", "", line) for line in result.split("\n")]
            result = "\n".join(lines)

        # 5. Padronização opcional de aspas tipográficas
        if self.config.standardize_quotes:
            result = result.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

        return result

    def normalize_with_offsets(self, text: str) -> tuple[str, list[dict[str, int]]]:
        """Normaliza o texto retornando também um mapa de correspondência de offsets.

        Retorna:
            (texto_normalizado, lista contendo {raw_start, raw_end, norm_start, norm_end})
        """
        normalized = self.normalize(text)
        # Para strings onde houve substituição 1-a-1 ou limpeza de controle,
        # geramos mapeamentos lineares de bloco
        mapping: list[dict[str, int]] = [
            {
                "raw_start": 0,
                "raw_end": len(text),
                "norm_start": 0,
                "norm_end": len(normalized),
            }
        ]
        return normalized, mapping
