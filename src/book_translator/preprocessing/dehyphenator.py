"""Correção controlada de hifenização de quebra de linha."""

from __future__ import annotations

import re

from book_translator.preprocessing.config import PreprocessingConfig

# Prefixos e modificadores canônicos do inglês que preservam o hífen legítimo em palavras compostas
KNOWN_COMPOUND_PREFIXES = {
    "anti",
    "all",
    "co",
    "cross",
    "ex",
    "half",
    "mid",
    "non",
    "post",
    "pre",
    "pro",
    "quasi",
    "re",
    "self",
    "sub",
    "super",
    "ultra",
    "well",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
}

# Hífen no final de uma linha seguido por quebra de linha e continuação alfabética
LINEBREAK_HYPHEN_REGEX = re.compile(r"(\b[a-zA-ZÀ-ÿ]{2,})[-—–]\s*\n\s*([a-zA-ZÀ-ÿ]{2,}\b)")


class Dehyphenator:
    """Corrige palavras partidas por hifenização tipográfica de final de linha."""

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()

    def dehyphenate(self, text: str) -> str:
        """Processa o texto recombinando palavras quebradas por hífen no fim da linha."""
        if not text or not self.config.fix_hyphenation:
            return text

        # 1. Remove caracteres de soft-hyphen explícitos (\u00ad)
        cleaned = text.replace("\u00ad\n", "").replace("\u00ad", "")

        def replace_match(match: re.Match) -> str:
            part1 = match.group(1)
            part2 = match.group(2)

            # Verifica tamanho mínimo configurado
            if len(part1) + len(part2) < self.config.min_hyphen_word_len:
                return f"{part1}-{part2}"

            # Se preservação de compostos estiver ativada e part1 for um prefixo reconhecido
            if self.config.preserve_compounds and part1.lower() in KNOWN_COMPOUND_PREFIXES:
                return f"{part1}-{part2}"

            # Se a segunda parte começar com letra maiúscula (ex: Anglo-\nAmerican), mantém o hífen
            if part2[0].isupper() and part1[0].isupper():
                return f"{part1}-{part2}"

            # Caso padrão: une a palavra removendo o hífen
            return f"{part1}{part2}"

        return LINEBREAK_HYPHEN_REGEX.sub(replace_match, cleaned)
