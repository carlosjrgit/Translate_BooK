"""Módulo de segurança, privacidade e hardening do Translate_BooK."""

from book_translator.security.audit import PrivacySanitizingFilter
from book_translator.security.path_guard import (
    SecurityError,
    sanitize_filename_strict,
    validate_safe_path,
)
from book_translator.security.resource_guard import (
    MAX_INPUT_FILE_SIZE_BYTES,
    MAX_SEGMENT_CHARACTERS,
    validate_disk_space,
    validate_file_size_limit,
    validate_https_download_url,
    validate_segment_size,
)
from book_translator.security.xml_guard import (
    safe_parse_xml,
    sanitize_html_content,
    validate_xml_security,
)
from book_translator.security.zip_guard import (
    is_safe_zip_entry_path,
    validate_zip_archive,
)

__all__ = [
    "SecurityError",
    "sanitize_filename_strict",
    "validate_safe_path",
    "is_safe_zip_entry_path",
    "validate_zip_archive",
    "validate_xml_security",
    "safe_parse_xml",
    "sanitize_html_content",
    "MAX_INPUT_FILE_SIZE_BYTES",
    "MAX_SEGMENT_CHARACTERS",
    "validate_file_size_limit",
    "validate_segment_size",
    "validate_https_download_url",
    "validate_disk_space",
    "PrivacySanitizingFilter",
]
