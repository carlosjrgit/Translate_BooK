"""Mecanismos especializados de resolução: referência pronominal, aliases, termos recorrentes e similaridade semântica."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from book_translator.context.models import SemanticSnippet
from book_translator.core.models import Segment
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    TranslationMemoryEntry,
)

STOPWORDS_PT = {
    "a",
    "o",
    "os",
    "as",
    "um",
    "uma",
    "uns",
    "umas",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "pelo",
    "pela",
    "pelos",
    "pelas",
    "com",
    "e",
    "ou",
    "mas",
    "que",
    "se",
    "para",
    "como",
    "ao",
    "aos",
    "à",
    "às",
    "seu",
    "sua",
    "seus",
    "suas",
    "meu",
    "minha",
    "foi",
    "era",
    "estava",
    "são",
    "ser",
    "ter",
    "havia",
}

STOPWORDS_EN = {
    "a",
    "an",
    "the",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "from",
    "about",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "and",
    "or",
    "but",
    "if",
    "while",
    "that",
    "which",
    "as",
    "is",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "of",
    "it",
    "its",
    "this",
}

PRONOUN_MAP_EN = {
    "masculine": {"he", "him", "his", "himself"},
    "feminine": {"she", "her", "hers", "herself"},
    "neutral": {"it", "its", "they", "them", "their", "theirs", "themselves"},
}

PRONOUN_MAP_PT = {
    "masculine": {"ele", "dele", "nele", "o mesmo"},
    "feminine": {"ela", "dela", "nela", "a mesma"},
    "neutral": {"eles", "elas", "deles", "delas"},
}


class PronounResolver:
    """Resolve referências pronominais em segmentos conectando-os aos antecedentes imediatos."""

    @staticmethod
    def resolve_pronominal_references(
        segment: Segment,
        preceding_segments: list[Segment],
        known_characters: list[CharacterEntry],
    ) -> list[tuple[CharacterEntry, str, float, str]]:
        """Identifica pronomes no segmento e recupera o personagem antecedente correspondente.

        Retorna lista de tuplas: (CharacterEntry, pronome, score, justificativa).
        """
        if not preceding_segments or not known_characters:
            return []

        text_lower = segment.original_text.lower()
        tokens = set(re.findall(r"\b\w+\b", text_lower))

        detected_pronouns: list[tuple[str, str]] = []  # (pronome, gênero)
        for gen, pset in PRONOUN_MAP_EN.items():
            found = tokens.intersection(pset)
            for p in found:
                detected_pronouns.append((p, gen))

        for gen, pset in PRONOUN_MAP_PT.items():
            found = tokens.intersection(pset)
            for p in found:
                detected_pronouns.append((p, gen))

        if not detected_pronouns:
            return []

        resolved: list[tuple[CharacterEntry, str, float, str]] = []
        already_resolved_cids: set[str] = set()

        # Busca personagens mencionados nos parágrafos anteriores (do mais próximo para o mais distante)
        for dist, prev_seg in enumerate(reversed(preceding_segments), start=1):
            prev_text_lower = prev_seg.original_text.lower()
            for char in known_characters:
                if char.id in already_resolved_cids:
                    continue

                # Verifica se o personagem foi mencionado no parágrafo anterior
                names_to_check = [char.name.lower()] + [a.lower() for a in char.aliases]
                mentioned = any(
                    re.search(rf"\b{re.escape(n)}\b", prev_text_lower) for n in names_to_check if n
                )

                if mentioned:
                    for pron, gen in detected_pronouns:
                        # Compatibilidade de gênero
                        char_gender = getattr(char, "gender", "unknown").lower()
                        is_compatible = (
                            char_gender == gen
                            or char_gender in ("unknown", "neutral")
                            or gen == "neutral"
                        )
                        if is_compatible:
                            # Score decai suavemente com a distância de parágrafos
                            score = max(0.65, 0.95 - (dist - 1) * 0.10)
                            justification = (
                                f"Referência pronominal '{pron}' no segmento #{segment.id} "
                                f"resolvida para '{char.name}' (gênero {char_gender}, "
                                f"mencionado a {dist} parágrafo(s) antes no segmento #{prev_seg.id})."
                            )
                            resolved.append((char, pron, score, justification))
                            already_resolved_cids.add(char.id)
                            break

        return resolved


class AliasResolver:
    """Identifica aliases, alcunhas e variantes nominais de personagens e entidades."""

    @staticmethod
    def resolve_aliases(
        segment: Segment,
        character_memory: Any,
    ) -> list[tuple[CharacterEntry, str, float, str]]:
        """Varre o texto do segmento identificando menções a aliases de personagens.

        Retorna lista de tuplas: (CharacterEntry, alias_encontrado, score, justificativa).
        """
        if not character_memory:
            return []

        text_lower = segment.original_text.lower()
        resolved: list[tuple[CharacterEntry, str, float, str]] = []
        seen_cids: set[str] = set()

        # Obtém todos os personagens
        all_chars: list[CharacterEntry] = []
        if hasattr(character_memory, "list_characters"):
            all_chars = character_memory.list_characters()
        elif hasattr(character_memory, "_characters"):
            all_chars = list(character_memory._characters.values())

        for char in all_chars:
            # 1. Menção direta pelo nome canônico
            if char.name and re.search(rf"\b{re.escape(char.name.lower())}\b", text_lower):
                if char.id not in seen_cids:
                    resolved.append(
                        (
                            char,
                            char.name,
                            0.98,
                            f"Menção nominal explícita ao personagem canônico '{char.name}'.",
                        )
                    )
                    seen_cids.add(char.id)
                continue

            # 2. Menção através de alias/alcunha
            for alias in char.aliases:
                if not alias or len(alias) < 2:
                    continue
                if re.search(rf"\b{re.escape(alias.lower())}\b", text_lower):
                    if char.id not in seen_cids:
                        resolved.append(
                            (
                                char,
                                alias,
                                0.92,
                                f"Alias '{alias}' identificado no segmento -> mapeado para o personagem '{char.name}'.",
                            )
                        )
                        seen_cids.add(char.id)
                        break

        return resolved


class RecurringTermMatcher:
    """Rastreia frequência e recorrência de termos do Glossário e TM na obra."""

    @staticmethod
    def match_glossary_terms(
        segment: Segment,
        glossary: Any,
        preceding_segments: list[Segment] | None = None,
    ) -> list[tuple[GlossaryEntry, float, str]]:
        """Localiza termos do glossário atribuindo score baseado em travamento e recorrência."""
        if not glossary:
            return []

        matched_entries: list[tuple[GlossaryEntry, int, int]] = []
        if hasattr(glossary, "find_matching_terms"):
            matched_entries = glossary.find_matching_terms(segment.original_text)

        # Contagem de recorrência nos parágrafos anteriores
        term_freqs: Counter[str] = Counter()
        if preceding_segments:
            for p in preceding_segments:
                p_lower = p.original_text.lower()
                for entry, _, _ in matched_entries:
                    if entry.source_term.lower() in p_lower:
                        term_freqs[entry.source_term.lower()] += 1

        results: list[tuple[GlossaryEntry, float, str]] = []
        seen_terms: set[str] = set()

        for entry, _, _ in matched_entries:
            key = entry.source_term.lower()
            if key in seen_terms:
                continue
            seen_terms.add(key)

            freq = term_freqs.get(key, 0)
            if entry.locked:
                score = 1.0
                just = (
                    f"Termo técnico travado (locked=True): '{entry.source_term}' -> '{entry.target_term}'. "
                    f"Tradução obrigatória (recorrência anterior: {freq} vezes)."
                )
            else:
                score = min(0.95, 0.75 + freq * 0.05)
                just = (
                    f"Termo de glossário: '{entry.source_term}' -> '{entry.target_term}' "
                    f"(recorrência anterior: {freq} vezes, score: {round(score, 2)})."
                )

            results.append((entry, score, just))

        # Ordena por score decrescente
        return sorted(results, key=lambda x: x[1], reverse=True)

    @staticmethod
    def match_tm_entries(
        segment: Segment,
        translation_memory: Any,
    ) -> list[tuple[TranslationMemoryEntry, float, str]]:
        """Busca correspondências exatas ou frasais na Translation Memory."""
        if not translation_memory or not hasattr(translation_memory, "search"):
            return []

        matches = translation_memory.search(segment.original_text, min_confidence=0.5)
        results: list[tuple[TranslationMemoryEntry, float, str]] = []

        for entry in matches:
            if entry.locked:
                score = 1.0
                just = f"Entrada travada da Translation Memory: '{entry.source_term}' -> '{entry.target_term}' (locked=True)."
            elif entry.source_term.strip().lower() == segment.original_text.strip().lower():
                score = 0.98
                just = "Correspondência exata da Translation Memory."
            else:
                score = min(0.95, 0.70 + entry.confidence * 0.25)
                just = (
                    f"Correspondência parcial da Translation Memory: '{entry.source_term}' -> '{entry.target_term}' "
                    f"(confiança TM: {entry.confidence})."
                )
            results.append((entry, score, just))

        return sorted(results, key=lambda x: x[1], reverse=True)


class LexicalSemanticMatcher:
    """Algoritmo de similaridade léxico-semântica para recuperar trechos anteriores análogos."""

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        words = re.findall(r"\b\w{3,}\b", text.lower())
        stopwords = STOPWORDS_PT.union(STOPWORDS_EN)
        return [w for w in words if w not in stopwords]

    @classmethod
    def find_similar_passages(
        cls,
        target_segment: Segment,
        all_segments: list[Segment],
        allow_future_leakage: bool = False,
        min_threshold: float = 0.15,
        top_k: int = 3,
    ) -> list[SemanticSnippet]:
        """Localiza trechos com alta densidade de vocabulário e tópicos compartilhados."""
        target_tokens = cls._tokenize(target_segment.original_text)
        if not target_tokens:
            return []

        target_counter = Counter(target_tokens)
        target_norm = math.sqrt(sum(v * v for v in target_counter.values()))
        if target_norm == 0:
            return []

        candidates: list[tuple[Segment, float, set[str]]] = []

        # Localiza o índice do segmento alvo na lista de leitura global
        target_idx = -1
        for i, s in enumerate(all_segments):
            if s.id == target_segment.id:
                target_idx = i
                break

        for i, seg in enumerate(all_segments):
            if seg.id == target_segment.id:
                continue

            # Regra anti-vazamento: trechos posteriores na ordem de leitura são rigorosamente bloqueados
            if not allow_future_leakage:
                if target_idx != -1 and i >= target_idx:
                    continue
                elif (
                    seg.chapter_id == target_segment.chapter_id
                    and seg.sequence_order >= target_segment.sequence_order
                ):
                    continue

            seg_tokens = cls._tokenize(seg.original_text)
            if not seg_tokens:
                continue

            seg_counter = Counter(seg_tokens)
            seg_norm = math.sqrt(sum(v * v for v in seg_counter.values()))
            if seg_norm == 0:
                continue

            intersection = set(target_tokens).intersection(set(seg_tokens))
            if not intersection:
                continue

            dot_product = sum(target_counter[t] * seg_counter[t] for t in intersection)
            cosine = dot_product / (target_norm * seg_norm)

            if cosine >= min_threshold:
                candidates.append((seg, cosine, intersection))

        # Ordena pelos mais similares
        candidates.sort(key=lambda x: x[1], reverse=True)

        snippets: list[SemanticSnippet] = []
        for seg, sim, common_terms in candidates[:top_k]:
            sample_terms = sorted(list(common_terms))[:4]
            just = (
                f"Similaridade léxico-semântica de {round(sim * 100)}% com o segmento #{seg.id} "
                f"(termos compartilhados: {', '.join(sample_terms)})."
            )
            snippets.append(
                SemanticSnippet(
                    segment_id=seg.id,
                    source_text=seg.original_text[:180],
                    translated_text=seg.translated_text[:180] if seg.translated_text else "",
                    similarity_score=round(sim, 3),
                    justification=just,
                )
            )

        return snippets
