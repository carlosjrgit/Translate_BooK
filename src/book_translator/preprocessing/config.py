"""Configurações e parâmetros do pipeline de pré-processamento editorial."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PreprocessingConfig:
    """Configuração completa das etapas de normalização, estruturação e segmentação."""

    # 1. Normalização Unicode e Caracteres
    normalize_unicode: bool = True
    unicode_form: str = "NFKC"
    clean_control_chars: bool = True
    standardize_whitespace: bool = True
    standardize_quotes: bool = False  # se True, padroniza aspas curvas em editoriais

    # 2. Des-hifenização controlada
    fix_hyphenation: bool = True
    preserve_compounds: bool = True
    min_hyphen_word_len: int = 4

    # 3. Reconstrução de Parágrafos
    reconstruct_paragraphs: bool = True
    detect_scene_breaks: bool = True
    scene_break_symbols: list[str] = field(
        default_factory=lambda: ["* * *", "***", "---", "###", "§ § §", "§§§", "• • •"]
    )

    # 4. Estrutura e Títulos
    detect_headings: bool = True
    max_heading_length: int = 120
    chapter_regex_patterns: list[str] = field(
        default_factory=lambda: [
            r"^(?:CHAPTER|CAPÍTULO)\s+([0-9IVXLCDM]+)(?:\s*[:.-]\s*(.*))?$",
            r"^(?:PROLOGUE|EPILOGUE|PRÓLOGO|EPÍLOGO)(?:\s*[:.-]\s*(.*))?$",
            r"^(?:PART|PARTE|BOOK|LIVRO)\s+([0-9IVXLCDM]+)(?:\s*[:.-]\s*(.*))?$",
        ]
    )

    # 5. Diálogos
    detect_dialogues: bool = True
    extract_speaker_hints: bool = True

    # 6. Repetição e Cabeçalhos/Rodapés
    filter_repetitions: bool = True
    repetition_frequency_threshold: float = 0.6

    # 7. Segmentação Inicial
    group_short_paragraphs: bool = True
    max_group_words: int = 120  # Agrupa parágrafos muito curtos contíguos até esse limite
    split_long_paragraphs: bool = True
    max_segment_words: int = 100  # Parágrafos longos (>100 palavras) são divididos em sentenças
    max_dialogue_exchange_words: int = 250  # Trocas rápidas de fala
    detect_small_scenes: bool = True
    max_scene_words: int = 350

