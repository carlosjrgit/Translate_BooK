"""Motor heurístico leve para Reconhecimento de Entidades Nomeadas (NER)."""

from __future__ import annotations

import re
from typing import Any

from book_translator.analysis.models import EntityType
from book_translator.analysis.ner.interface import NERInterface, RawEntityMention

# Honoríficos e títulos que precedem nomes de personagens
HONORIFICS = (
    "Mr.",
    "Mrs.",
    "Miss",
    "Ms.",
    "Dr.",
    "Doctor",
    "Prof.",
    "Professor",
    "Lord",
    "Lady",
    "Sir",
    "Dame",
    "Count",
    "Countess",
    "Duke",
    "Duchess",
    "Baron",
    "Baroness",
    "King",
    "Queen",
    "Prince",
    "Princess",
    "Captain",
    "Colonel",
    "Major",
    "General",
    "Inspector",
    "Detective",
    "Father",
    "Brother",
    "Sister",
    "Master",
)

HONORIFIC_PATTERN = r"(?:" + "|".join(re.escape(h) for h in HONORIFICS) + r")"

# Sufixos e indicadores de locais
LOCATION_KEYWORDS = {
    "street",
    "st.",
    "avenue",
    "ave.",
    "road",
    "rd.",
    "lane",
    "square",
    "park",
    "river",
    "mountain",
    "valley",
    "city",
    "town",
    "village",
    "bay",
    "sea",
    "ocean",
    "bridge",
    "tower",
    "castle",
    "hall",
    "manor",
    "abbey",
    "palace",
    "hotel",
    "island",
    "lake",
    "forest",
    "london",
    "paris",
    "england",
    "scotland",
    "britain",
    "france",
    "america",
}

# Indicadores de organizações e coletivos
ORGANIZATION_KEYWORDS = {
    "ministry",
    "department",
    "police",
    "yard",
    "guard",
    "army",
    "navy",
    "society",
    "club",
    "company",
    "corporation",
    "association",
    "order",
    "council",
    "committee",
    "bank",
    "university",
    "college",
    "hospital",
    "guild",
    "patrol",
}

# Verbos de elocução que confirmam personagens com alta confiança
SPEECH_VERBS_SET = {
    "said",
    "asked",
    "replied",
    "whispered",
    "shouted",
    "murmured",
    "answered",
    "exclaimed",
    "remarked",
    "cried",
    "demanded",
    "disse",
    "perguntou",
    "respondeu",
    "afirmou",
}

# Expressão para título com nome (ex: "Dr. John Watson" ou "Lady Margaret")
TITLE_PERSON_REGEX = re.compile(
    rf"\b({HONORIFIC_PATTERN})\s+([A-ZÀ-Ý][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)?)\b"
)

# Expressão para nomes próprios capitalizados de duas ou três palavras
CAPITALIZED_NAME_REGEX = re.compile(
    r"\b([A-ZÀ-Ý][a-zA-ZÀ-ÿ]+(?:\s+(?:von|van|de|da|Mc|Mac|O')?[A-ZÀ-Ý][a-zA-ZÀ-ÿ]+){1,2})\b"
)

NON_PERSON_POSSESSIVES = {
    "it",
    "there",
    "that",
    "what",
    "here",
    "who",
    "let",
    "one",
    "today",
    "yesterday",
    "tomorrow",
    "world",
    "life",
    "year",
    "month",
    "day",
    "night",
    "country",
    "city",
    "government",
    "god",
    "heaven",
    "hell",
    "earth",
    "nature",
    "winter",
    "summer",
    "spring",
    "autumn",
    "fall",
    "ele",
    "ela",
    "isto",
    "isso",
    "aquilo",
    "hoje",
    "ontem",
    "amanhã",
}

POSSESSIVE_NAME_REGEX = re.compile(r"\b([A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)'s\b")
SPEECH_AFTER_REGEX = re.compile(rf"\b([A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)\s+(?:{'|'.join(SPEECH_VERBS_SET)})\b")
SPEECH_BEFORE_REGEX = re.compile(rf"\b(?:{'|'.join(SPEECH_VERBS_SET)})\s+([A-ZÀ-Ý][a-zA-ZÀ-ÿ]+)\b")


class HeuristicNER(NERInterface):
    """Implementação funcional leve e determinística de NER baseada em padrões linguísticos."""

    @property
    def engine_name(self) -> str:
        return "heuristic"

    def _extract_snippet(self, text: str, start: int, end: int, window: int = 40) -> str:
        """Gera um snippet de contexto ao redor da menção."""
        left = max(0, start - window)
        right = min(len(text), end + window)
        prefix = "..." if left > 0 else ""
        suffix = "..." if right < len(text) else ""
        return f"{prefix}{text[left:right].strip()}{suffix}"

    def extract_entities(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> list[RawEntityMention]:
        """Varre o texto e extrai menções brutas de personagens, locais e organizações."""
        if not text:
            return []

        ctx = context or {}
        chapter_id = ctx.get("chapter_id", "")
        unit_id = ctx.get("unit_id", "")

        mentions: list[RawEntityMention] = []
        spans_matched: set[tuple[int, int]] = set()

        # 1. Padrão de Título Honorífico + Nome (ex: "Dr. John Watson") -> CHARACTER
        for match in TITLE_PERSON_REGEX.finditer(text):
            full_span = match.span()
            honorific = match.group(1)
            name_part = match.group(2)
            full_mention = f"{honorific} {name_part}"
            spans_matched.add(full_span)

            mentions.append(
                RawEntityMention(
                    text=full_mention,
                    entity_type=EntityType.CHARACTER,
                    confidence=0.95,
                    start_char=full_span[0],
                    end_char=full_span[1],
                    honorific=honorific,
                    chapter_id=chapter_id,
                    unit_id=unit_id,
                    snippet=self._extract_snippet(text, full_span[0], full_span[1]),
                    metadata={"base_name": name_part, "honorific": honorific},
                )
            )

        # 2. Padrão de Nomes Próprios Multi-palavras
        for match in CAPITALIZED_NAME_REGEX.finditer(text):
            span = match.span()
            # Evita sobreposição com correspondências de título já encontradas
            if any(s[0] <= span[0] and span[1] <= s[1] for s in spans_matched):
                continue

            entity_str = match.group(1)
            words = entity_str.split()
            words_lower = [w.lower() for w in words]

            # Heurística de Organização (precedência sobre localização)
            if any(w in ORGANIZATION_KEYWORDS for w in words_lower):
                spans_matched.add(span)
                mentions.append(
                    RawEntityMention(
                        text=entity_str,
                        entity_type=EntityType.ORGANIZATION,
                        confidence=0.90,
                        start_char=span[0],
                        end_char=span[1],
                        chapter_id=chapter_id,
                        unit_id=unit_id,
                        snippet=self._extract_snippet(text, span[0], span[1]),
                    )
                )
                continue

            # Heurística de Local
            if any(w in LOCATION_KEYWORDS for w in words_lower):
                spans_matched.add(span)
                mentions.append(
                    RawEntityMention(
                        text=entity_str,
                        entity_type=EntityType.LOCATION,
                        confidence=0.90,
                        start_char=span[0],
                        end_char=span[1],
                        chapter_id=chapter_id,
                        unit_id=unit_id,
                        snippet=self._extract_snippet(text, span[0], span[1]),
                    )
                )
                continue

            # Heurística de Personagem com Verbo de Fala no entorno
            surrounding = self._extract_snippet(text, span[0], span[1], window=25).lower()
            has_speech_verb = any(v in surrounding for v in SPEECH_VERBS_SET)

            conf = 0.90 if has_speech_verb else 0.80
            spans_matched.add(span)
            mentions.append(
                RawEntityMention(
                    text=entity_str,
                    entity_type=EntityType.CHARACTER,
                    confidence=conf,
                    start_char=span[0],
                    end_char=span[1],
                    chapter_id=chapter_id,
                    unit_id=unit_id,
                    snippet=self._extract_snippet(text, span[0], span[1]),
                    metadata={"has_speech_verb": has_speech_verb},
                )
            )

        # 3. Padrão de Nomes em Possessivo Simples (ex: "Arthur's mother")
        for match in POSSESSIVE_NAME_REGEX.finditer(text):
            name_token = match.group(1)
            span = match.span(1)
            if name_token.lower() in NON_PERSON_POSSESSIVES:
                continue
            if any(s[0] <= span[0] and span[1] <= s[1] for s in spans_matched):
                continue

            spans_matched.add(span)
            mentions.append(
                RawEntityMention(
                    text=name_token,
                    entity_type=EntityType.CHARACTER,
                    confidence=0.85,
                    start_char=span[0],
                    end_char=span[1],
                    chapter_id=chapter_id,
                    unit_id=unit_id,
                    snippet=self._extract_snippet(text, span[0], span[1]),
                    metadata={"is_possessive": True},
                )
            )

        # 4. Padrão de Nome Próprio Simples com Verbo de Fala Imediato
        for regex in (SPEECH_AFTER_REGEX, SPEECH_BEFORE_REGEX):
            for match in regex.finditer(text):
                name_token = match.group(1)
                span = match.span(1)
                if name_token.lower() in NON_PERSON_POSSESSIVES:
                    continue
                if any(s[0] <= span[0] and span[1] <= s[1] for s in spans_matched):
                    continue

                spans_matched.add(span)
                mentions.append(
                    RawEntityMention(
                        text=name_token,
                        entity_type=EntityType.CHARACTER,
                        confidence=0.90,
                        start_char=span[0],
                        end_char=span[1],
                        chapter_id=chapter_id,
                        unit_id=unit_id,
                        snippet=self._extract_snippet(text, span[0], span[1]),
                        metadata={"has_speech_verb": True},
                    )
                )

        return mentions
