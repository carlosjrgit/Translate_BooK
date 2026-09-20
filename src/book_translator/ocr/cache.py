"""Sistema de cache e revisão por página para resultados de OCR."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from book_translator.logging import get_logger
from book_translator.ocr.base import OcrPageResult

logger = get_logger("ocr.cache")


class OcrCache:
    """Cache persistente em disco para resultados de OCR por página."""

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        if cache_dir is None:
            # Diretório padrão no diretório de dados da aplicação ou temp do projeto
            self.cache_dir = Path(".cache/ocr").resolve()
        else:
            self.cache_dir = Path(cache_dir).resolve()

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, OcrPageResult] = {}

    @staticmethod
    def calculate_file_hash(file_path: Path | str) -> str:
        """Gera o hash SHA-256 do arquivo fonte para indexação de cache imutável."""
        p = Path(file_path)
        sha = hashlib.sha256()
        with p.open("rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    def _make_key(
        self,
        file_hash: str,
        page_number: int,
        engine_name: str,
        language: str = "eng",
    ) -> str:
        return f"{file_hash[:16]}_p{page_number:04d}_{engine_name}_{language}"

    def get(
        self,
        file_hash: str,
        page_number: int,
        engine_name: str,
        language: str = "eng",
    ) -> OcrPageResult | None:
        """Recupera resultado de OCR em cache da memória ou do disco."""
        cache_key = self._make_key(file_hash, page_number, engine_name, language)

        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        disk_path = self.cache_dir / f"{cache_key}.json"
        if disk_path.exists():
            try:
                data = json.loads(disk_path.read_text(encoding="utf-8"))
                result = OcrPageResult(
                    page_number=data["page_number"],
                    text=data["text"],
                    confidence=data.get("confidence"),
                    is_ocr=data.get("is_ocr", True),
                    char_count=data.get("char_count", len(data["text"])),
                    words_count=data.get("words_count", len(data["text"].split())),
                    engine_name=data.get("engine_name", engine_name),
                    needs_review=data.get("needs_review", False),
                    metadata=data.get("metadata", {}),
                )
                self._memory_cache[cache_key] = result
                logger.debug(f"Cache OCR HIT: página {page_number} ({cache_key})")
                return result
            except Exception as e:
                logger.warning(f"Erro ao ler cache OCR '{disk_path.name}': {e}")

        return None

    def put(
        self,
        file_hash: str,
        page_number: int,
        engine_name: str,
        result: OcrPageResult,
        language: str = "eng",
    ) -> None:
        """Armazena resultado de OCR na memória e em arquivo JSON no disco."""
        cache_key = self._make_key(file_hash, page_number, engine_name, language)
        self._memory_cache[cache_key] = result

        disk_path = self.cache_dir / f"{cache_key}.json"
        try:
            payload = {
                "page_number": result.page_number,
                "text": result.text,
                "confidence": result.confidence,
                "is_ocr": result.is_ocr,
                "char_count": result.char_count,
                "words_count": result.words_count,
                "engine_name": result.engine_name,
                "needs_review": result.needs_review,
                "metadata": result.metadata,
            }
            disk_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Falha ao salvar cache OCR em '{disk_path.name}': {e}")

    def update_review(
        self,
        file_hash: str,
        page_number: int,
        engine_name: str,
        reviewed_text: str,
        language: str = "eng",
        reviewer: str = "user",
    ) -> OcrPageResult:
        """Permite a revisão humana do texto extraído por OCR preservando histórico."""
        existing = self.get(file_hash, page_number, engine_name, language)
        if not existing:
            existing = OcrPageResult(
                page_number=page_number,
                text=reviewed_text,
                confidence=1.0,
                engine_name=engine_name,
            )

        # Atualiza metadados de revisão
        existing.metadata["original_ocr_text"] = existing.text
        existing.metadata["reviewed_by"] = reviewer
        existing.metadata["was_reviewed"] = True
        existing.text = reviewed_text
        existing.char_count = len(reviewed_text)
        existing.words_count = len(reviewed_text.split())
        existing.needs_review = False
        existing.confidence = 1.0  # Texto validado manualmente

        self.put(file_hash, page_number, engine_name, existing, language)
        logger.info(f"Página {page_number} revisada com sucesso por '{reviewer}'")
        return existing
