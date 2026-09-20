"""Gerenciamento do ciclo de vida, persistência e integridade de projetos de livros."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from book_translator.config import get_config
from book_translator.core.ids import generate_project_id
from book_translator.core.models import Checkpoint, Project, ProjectMetadata
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.errors import ConfigurationError, DatabaseError, IngestionError
from book_translator.logging import get_logger

logger = get_logger("projects.manager")


def compute_file_sha256(file_path: Path | str) -> str:
    """Calcula o hash SHA-256 de um arquivo abrindo-o estritamente em modo read-only."""
    path = Path(file_path)
    if not path.is_file():
        raise IngestionError(f"Arquivo não encontrado para cálculo de hash: {path}")

    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class ProjectManager:
    """Orquestrador do ciclo de vida de projetos de tradução."""

    def __init__(self, base_projects_dir: Path | str | None = None) -> None:
        self.base_projects_dir = (
            Path(base_projects_dir) if base_projects_dir else get_config().projects_dir
        )

    def create_project(
        self,
        book_title: str,
        source_file_path: Path | str,
        target_dir: Path | str | None = None,
        config: dict[str, Any] | None = None,
        source_language: str = "en",
        target_language: str = "pt-BR",
    ) -> tuple[Project, SQLiteDatabase]:
        """Cria um novo projeto de livro com persistência isolada e cópia imutável da fonte."""
        source_path = Path(source_file_path)
        if not source_path.exists() or not source_path.is_file():
            raise IngestionError(f"Arquivo fonte inválido ou não encontrado: {source_path}")

        # Calcula o hash SHA-256 do arquivo original intocado
        original_hash = compute_file_sha256(source_path)

        project_id = generate_project_id(book_title)
        if target_dir:
            project_dir = Path(target_dir) / project_id
        else:
            project_dir = self.base_projects_dir / project_id

        # Cria estrutura de pastas do projeto
        source_dir = project_dir / "source"
        cache_dir = project_dir / "cache"
        translations_dir = project_dir / "translations"
        output_dir = project_dir / "output"

        for d in [source_dir, cache_dir, translations_dir, output_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Copia o arquivo fonte para dentro do projeto (mantendo o original do usuário estritamente intocado)
        internal_source_copy = source_dir / f"original_{source_path.name}"
        shutil.copy2(source_path, internal_source_copy)

        # Inicializa a base de dados SQLite
        db_path = project_dir / "project.db"
        db = SQLiteDatabase(db_path)
        db.initialize()

        meta = ProjectMetadata(
            project_id=project_id,
            book_title=book_title,
            source_file_path=str(source_path.resolve()),
            source_file_sha256=original_hash,
            source_language=source_language,
            target_language=target_language,
            status="active",
        )
        project = Project(
            metadata=meta,
            project_dir=project_dir,
            db_path=db_path,
            config=config or {},
        )

        db.save_project(project)

        # Cria checkpoint inicial
        initial_checkpoint = Checkpoint(
            id=f"chk_{project_id}_init",
            project_id=project_id,
            status="initialized",
        )
        db.save_checkpoint(initial_checkpoint)

        logger.info(f"Projeto criado com sucesso: {project_id} ({project_dir})")
        return project, db

    def open_project(self, project_dir: Path | str) -> tuple[Project, SQLiteDatabase]:
        """Abre e valida um projeto existente, aplicando migrations se necessário."""
        p_dir = Path(project_dir)
        if not p_dir.exists() or not p_dir.is_dir():
            raise ConfigurationError(f"Diretório de projeto não encontrado: {p_dir}")

        db_path = p_dir / "project.db"
        if not db_path.exists() or not db_path.is_file():
            raise DatabaseError(f"Arquivo de banco de dados 'project.db' ausente em: {p_dir}")

        # Tenta inicializar/migrar banco SQLite
        db = SQLiteDatabase(db_path)
        db.initialize()

        # Infere o id do projeto pelo nome do diretório
        project_id = p_dir.name
        project = db.load_project(project_id)
        if not project:
            # Fallback buscando pelo primeiro projeto cadastrado no banco
            cur = db.conn.cursor()
            try:
                cur.execute("SELECT id FROM projects LIMIT 1;")
                row = cur.fetchone()
                if row:
                    project = db.load_project(row["id"])
            finally:
                cur.close()

        if not project:
            db.close()
            raise DatabaseError(f"Nenhum metadado de projeto encontrado em: {db_path}")

        logger.info(f"Projeto aberto com sucesso: {project.metadata.project_id}")
        return project, db

    def close_project(self, project: Project, db: SQLiteDatabase | None = None) -> None:
        """Fecha com segurança as conexões ativas do projeto e efetua flush do WAL."""
        if db:
            db.close()
        logger.info(f"Projeto fechado com segurança: {project.metadata.project_id}")

    def resume_project(self, project_dir: Path | str) -> dict[str, Any]:
        """Verifica o estado atual do projeto para planejamento de retomada."""
        project, db = self.open_project(project_dir)
        try:
            pid = project.metadata.project_id
            latest_chk = db.get_latest_checkpoint(pid)
            total_segments = db.count_total_segments(pid)
            completed_segments = db.count_translated_segments(pid)
            pending_segments = db.get_pending_segments(pid)

            return {
                "project_id": pid,
                "book_title": project.metadata.book_title,
                "status": project.metadata.status,
                "total_segments": total_segments,
                "completed_segments": completed_segments,
                "pending_segments_count": len(pending_segments),
                "latest_checkpoint": latest_chk.__dict__ if latest_chk else None,
            }
        finally:
            db.close()

    def verify_source_integrity(self, project: Project) -> bool:
        """Confirma se a cópia interna do arquivo fonte preserva exatamente o hash inicial."""
        p_dir = project.project_dir
        source_dir = p_dir / "source"
        internal_files = list(source_dir.glob("original_*"))
        if not internal_files:
            return False

        current_hash = compute_file_sha256(internal_files[0])
        return current_hash == project.metadata.source_file_sha256
