"""Utilitários de detecção de encoding e normalização Unicode."""

from __future__ import annotations

import unicodedata

from book_translator.logging import get_logger

logger = get_logger("parsers.normalization")

# Caracteres de controle ou invisíveis indesejados
DISALLOWED_CONTROL_CHARS = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
    "\ufeff",  # zero-width no-break space (BOM)
}


def detect_encoding(raw_bytes: bytes) -> str:
    """Detecta o encoding de bytes brutos com fallback seguro e resiliente."""
    if not raw_bytes:
        return "utf-8"

    # 1. Detecção por BOM
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw_bytes.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw_bytes.startswith(b"\xfe\xff"):
        return "utf-16-be"

    # 2. Testa UTF-8 estrito
    try:
        raw_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # 3. Biblioteca charset_normalizer se disponível
    try:
        import charset_normalizer

        matches = charset_normalizer.from_bytes(raw_bytes)
        best = matches.best()
        if best and best.encoding:
            enc = best.encoding.lower()
            if enc in ("cp1250", "iso-8859-2"):
                try:
                    decoded = raw_bytes.decode("cp1252")
                    if any(c in decoded for c in "ãõçéáíóúêâôÃÕÇÉÁÍÓÚÊÂÔ"):
                        return "cp1252"
                except UnicodeDecodeError:
                    pass
            logger.debug(f"Encoding detectado via charset_normalizer: {best.encoding}")
            return best.encoding
    except Exception as e:
        logger.debug(f"Falha na detecção por charset_normalizer: {e}")

    # 4. Fallbacks comuns para textos ocidentais
    for enc in ("cp1252", "iso-8859-1", "latin-1"):
        try:
            raw_bytes.decode(enc)
            logger.debug(f"Encoding fallback selecionado: {enc}")
            return enc
        except UnicodeDecodeError:
            continue

    return "utf-8"


def normalize_unicode(text: str, form: str = "NFC") -> str:
    """Normaliza o texto para forma Unicode canônica e remove caracteres invisíveis."""
    if not text:
        return ""

    # Remove BOM se presente
    text = text.lstrip("\ufeff")

    # Normaliza quebras de linha para \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Normalização Unicode canônica (NFC)
    text = unicodedata.normalize(form, text)

    # Remove caracteres de controle invisíveis ou disfuncionais
    cleaned_chars = [
        c
        for c in text
        if c not in DISALLOWED_CONTROL_CHARS
        and (unicodedata.category(c) != "Cc" or c in ("\n", "\t"))
    ]
    return "".join(cleaned_chars)
