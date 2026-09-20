"""Sanitizador de logs e auditoria de privacidade."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

# Padrões para mascaramento de tokens e caminhos de usuário
API_KEY_REGEX = re.compile(r"(?:api[_-]?key|token|bearer|secret)[\s:=]+([a-zA-Z0-9_\-\.]{8,})", re.IGNORECASE)


class PrivacySanitizingFilter(logging.Filter):
    """Filtro de logging que anonimiza caminhos locais e mascara eventuais tokens ou segredos."""

    def __init__(self) -> None:
        super().__init__()
        self.user_home = str(Path.home())
        self.user_name = os.getenv("USERNAME") or os.getenv("USER") or ""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.sanitize_message(record.msg)
        return True

    def sanitize_message(self, message: str) -> str:
        clean = message
        # 1. Mascara segredos/tokens
        clean = API_KEY_REGEX.sub(r"***REDACTED_SECRET***", clean)
        # 2. Mascara caminhos pessoais do usuário para evitar vazamento em logs compartilhados
        if self.user_home and len(self.user_home) > 3:
            clean = clean.replace(self.user_home, "[HOME_DIR]")
        # Padrões genéricos de caminhos de usuário no Windows (C:\Users\<user>) e Linux (/home/<user>)
        clean = re.sub(r"[a-zA-Z]:\\Users\\[^\\]+", "[HOME_DIR]", clean)
        clean = re.sub(r"/home/[^/]+", "[HOME_DIR]", clean)
        if self.user_name and len(self.user_name) > 2:
            clean = re.sub(rf"\b{re.escape(self.user_name)}\b", "[USER]", clean)
        return clean
