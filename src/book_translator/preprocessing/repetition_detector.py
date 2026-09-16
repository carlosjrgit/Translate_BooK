"""Detecção e filtragem estatística de conteúdo repetido (cabeçalhos, rodapés e boilerplate)."""

from __future__ import annotations

from collections import Counter

from book_translator.preprocessing.config import PreprocessingConfig


class RepetitionDetector:
    """Identifica linhas repetidas com alta frequência (como cabeçalhos recorrentes)."""

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()

    def detect_repetitive_lines(
        self,
        groups: list[list[str]],
        threshold: float | None = None,
    ) -> set[str]:
        """Detecta linhas que ocorrem repetidamente através dos grupos (ex: páginas ou capítulos).

        Argumentos:
            groups: Lista de listas de linhas (ex: linhas por página).
            threshold: Limite de frequência (0.0 a 1.0). Se None, usa config.
        """
        if not groups or len(groups) < 2:
            return set()

        cutoff = threshold or self.config.repetition_frequency_threshold
        min_occurrences = max(2, int(len(groups) * cutoff))

        counts: Counter[str] = Counter()

        for group in groups:
            # Conjunto de linhas únicas normalizadas dentro do grupo
            unique_in_group = {
                line.strip().lower() for line in group if line.strip() and len(line.strip()) <= 100
            }
            for line in unique_in_group:
                counts[line] += 1

        repetitive: set[str] = {line for line, count in counts.items() if count >= min_occurrences}
        return repetitive

    def filter_repetitive_from_groups(
        self,
        groups: list[list[str]],
        repetitive: set[str] | None = None,
    ) -> list[list[str]]:
        """Filtra as linhas repetitivas de cada grupo mantendo a ordem das demais."""
        if not groups:
            return []

        rep_set = repetitive if repetitive is not None else self.detect_repetitive_lines(groups)
        if not rep_set:
            return groups

        filtered: list[list[str]] = []
        for group in groups:
            clean_group = [line for line in group if line.strip().lower() not in rep_set]
            filtered.append(clean_group)

        return filtered
