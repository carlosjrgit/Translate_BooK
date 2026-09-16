"""Detecção refinada de diálogos e extração de pistas de interlocutor."""

from __future__ import annotations

import re

from book_translator.preprocessing.config import PreprocessingConfig

DASH_MARKERS = ("—", "–", "―", "-")
QUOTE_PAIRS = [('"', '"'), ("“", "”"), ("«", "»")]

DASH_REGEX = re.compile(r"^[\s]*([—–―\-])\s*(.*)$")
QUOTE_START_REGEX = re.compile(r"^[\s]*[\"“«]")

# Verbos comuns de elocução para extração heurística de pistas de interlocutor
SPEECH_VERBS = (
    r"(?i:said|asked|replied|whispered|shouted|murmured|answered|exclaimed|remarked|"
    r"cried|demanded|growled|snapped|laughed|sighed|disse|perguntou|respondeu|sussurrou|"
    r"gritou|afirmou|comentou)"
)

# Padrão 1: ", said John." ou "— disse Maria."
SPEAKER_AFTER_VERB_REGEX = re.compile(
    rf"[,—–\-]?\s*{SPEECH_VERBS}\s+([A-ZÀ-Ý][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)?)"
)

# Padrão 2: ", John said." ou "— Maria perguntou."
SPEAKER_BEFORE_VERB_REGEX = re.compile(
    rf"[,—–\-]?\s*([A-ZÀ-Ý][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)?)\s+{SPEECH_VERBS}"
)


class DialogueDetector:
    """Identifica falas, marcadores de diálogo e possíveis pistas de interlocutores."""

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()

    def extract_speaker_hint(self, text: str) -> str | None:
        """Tenta extrair o nome do interlocutor a partir de incisos de fala na frase."""
        if not self.config.extract_speaker_hints:
            return None

        # Procura ", said Holmes"
        match = SPEAKER_AFTER_VERB_REGEX.search(text)
        if match:
            speaker = match.group(1).strip()
            if speaker.lower() not in {"he", "she", "they", "it", "ele", "ela", "eles"}:
                return speaker

        # Procura ", Holmes said"
        match2 = SPEAKER_BEFORE_VERB_REGEX.search(text)
        if match2:
            speaker = match2.group(1).strip()
            if speaker.lower() not in {"he", "she", "they", "it", "ele", "ela", "eles"}:
                return speaker

        return None

    def analyze_dialogue(self, text: str) -> tuple[bool, str, str, str | None]:
        """Analisa o texto e identifica se constitui um bloco de diálogo.

        Retorna:
            (is_dialogue, marker, clean_text, speaker_hint)
        """
        trimmed = text.strip()
        if not trimmed:
            return False, "", "", None

        # 1. Diálogo por travessão (padrão editorial latino/europeu)
        dash_match = DASH_REGEX.match(trimmed)
        if dash_match:
            marker = dash_match.group(1)
            clean = dash_match.group(2).strip()
            speaker = self.extract_speaker_hint(trimmed)
            return True, marker, clean, speaker

        # 2. Diálogo por aspas (padrão editorial anglo-saxão)
        if QUOTE_START_REGEX.match(trimmed):
            # Verifica se fecha aspas
            marker = trimmed[0]
            speaker = self.extract_speaker_hint(trimmed)
            return True, marker, trimmed, speaker

        # 3. Frase contendo citações internas amplas (ex: He looked at me and said, "Run!")
        if ('"' in trimmed and trimmed.count('"') >= 2) or ("“" in trimmed and "”" in trimmed):
            speaker = self.extract_speaker_hint(trimmed)
            return True, "“" if "“" in trimmed else '"', trimmed, speaker

        return False, "", trimmed, None
