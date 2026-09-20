"""Guarda de segurança contra ataques de XXE (XML External Entity) e Billion Laughs."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from book_translator.security.path_guard import SecurityError

MAX_XML_TEXT_BYTES = 50 * 1024 * 1024  # 50 MB

# Padrões regex para detecção de injeções de DTD e entidades externas / recursivas
DOCTYPE_REGEX = re.compile(r"<!DOCTYPE\s+[^>]+>", re.IGNORECASE | re.DOTALL)
ENTITY_REGEX = re.compile(r"<!ENTITY\s+[^>]+>", re.IGNORECASE)
SYSTEM_PUBLIC_REGEX = re.compile(r"(?:SYSTEM|PUBLIC)\s+[\"'][^\"']+[\"']", re.IGNORECASE)
SCRIPT_TAG_REGEX = re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
JAVASCRIPT_URI_REGEX = re.compile(r"href\s*=\s*[\"']\s*javascript:", re.IGNORECASE)


def validate_xml_security(xml_content: str | bytes) -> None:
    """Inspeciona o payload XML antes do parsing para bloquear XXE e injeções de DTD."""
    if isinstance(xml_content, bytes):
        if len(xml_content) > MAX_XML_TEXT_BYTES:
            raise SecurityError(
                f"Payload XML excede o tamanho máximo de segurança ({len(xml_content)} bytes)."
            )
        try:
            text = xml_content.decode("utf-8", errors="replace")
        except Exception as e:
            raise SecurityError(f"Codificação inválida no XML: {e}") from e
    else:
        if len(xml_content.encode("utf-8", errors="replace")) > MAX_XML_TEXT_BYTES:
            raise SecurityError("Payload XML excede o tamanho máximo de segurança.")
        text = xml_content

    # 1. Bloqueio de DTDs com entidades externas (XXE)
    if SYSTEM_PUBLIC_REGEX.search(text):
        raise SecurityError(
            "Vulnerabilidade de XXE bloqueada: O XML contém referências SYSTEM ou PUBLIC DTD externas."
        )

    # 2. Bloqueio de declaração de entidades internas arbitrárias (Billion Laughs / Entity Expansion)
    if ENTITY_REGEX.search(text):
        raise SecurityError(
            "Vulnerabilidade de expansão de entidades bloqueada: Declaração de <!ENTITY> não é permitida."
        )


def safe_parse_xml(xml_content: str | bytes) -> ET.Element:
    """Executa o parsing de XML de forma segura com inspeção prévia rigorosa contra XXE."""
    validate_xml_security(xml_content)

    try:
        # No Python 3.8+, o parser nativo com resolve_entities=False impede expansão perigosa
        parser = ET.XMLParser()
        if isinstance(xml_content, str):
            return ET.fromstring(xml_content, parser=parser)
        return ET.fromstring(xml_content.decode("utf-8", errors="replace"), parser=parser)
    except ET.ParseError as e:
        raise SecurityError(f"Erro de sintaxe ao processar XML seguro: {e}") from e


def sanitize_html_content(raw_html: str) -> str:
    """Remove scripts, tags perigosas e protocolos javascript: de conteúdo HTML/XHTML."""
    clean = SCRIPT_TAG_REGEX.sub("", raw_html)
    clean = JAVASCRIPT_URI_REGEX.sub("href=\"#blocked-js\"", clean)
    clean = re.sub(r"\bon\w+\s*=\s*[\"'][^\"']*[\"']", "", clean, flags=re.IGNORECASE)
    return clean
