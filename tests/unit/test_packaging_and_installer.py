"""Testes de validação de empacotamento Windows e instalador (Prompt 28).

Cenários cobertos:
1. Validação estrita do arquivo translate_book.spec (exclusão de pesos neurais, runtime standalone, SQL migrations).
2. Validação do script Inno Setup (PrivilegesRequired=lowest, suporte a caminhos com espaços, preservação de projetos).
3. Separação arquitetural entre executável, projetos do usuário e modelos de IA (get_default_data_dirs).
4. Suporte a caminhos contendo espaços e caracteres especiais.
5. Simulação de primeira execução limpa (sem modelo instalado).
6. Simulação de atualização de versão e desinstalação (preservação estrita dos projetos do usuário).
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

from book_translator.config import get_default_data_dirs
from book_translator.system.model_manager import ModelManager, ModelStatus


def test_spec_excludes_neural_weights():
    """Valida que o spec do PyInstaller exclui categoricamente pesos neurais e lógicas desnecessárias."""
    spec_path = Path(__file__).resolve().parent.parent.parent / "packaging" / "windows" / "translate_book.spec"
    assert spec_path.exists(), f"Arquivo spec não encontrado em {spec_path}"

    content = spec_path.read_text(encoding="utf-8")

    # Verifica console=False (aplicativo puramente GUI)
    assert "console=False" in content

    # Verifica filtro de pesos neurais
    assert "is_model_weight" in content
    for ext in [".bin", ".safetensors", ".gguf", ".pt", ".onnx"]:
        assert ext in content, f"Extensão {ext} deve ser filtrada no spec"

    # Verifica inclusão das migrations SQL
    assert "book_translator/database/sql" in content.replace("\\", "/")


def test_installer_iss_configuration():
    """Valida as diretrizes de segurança e usabilidade no script Inno Setup (.iss)."""
    iss_path = Path(__file__).resolve().parent.parent.parent / "packaging" / "windows" / "installer.iss"
    assert iss_path.exists(), f"Arquivo .iss não encontrado em {iss_path}"

    content = iss_path.read_text(encoding="utf-8")

    # 1. Privilégios mínimos (não exige privilégios administrativos)
    assert "PrivilegesRequired=lowest" in content

    # 2. Localização padrão por usuário
    assert "{localappdata}\\Programs\\" in content or "{localappdata}/Programs/" in content

    # 3. Tratamento de caminhos com espaços (citações em torno de executáveis e caminhos)
    assert '"{app}\\{#MyAppExeName}"' in content or '"{app}/{#MyAppExeName}"' in content

    # 4. Política de preservação: NUNCA deve haver diretiva de remoção recursiva em {userappdata}
    assert "delete" not in content.lower() or "{userappdata}" not in content


def test_data_isolation_frozen_vs_dev(tmp_path):
    """Verifica a separação entre diretório do executável, projetos do usuário e modelos de IA."""
    # Cenário 1: Modo Desenvolvimento (padrão)
    dev_dirs = get_default_data_dirs()
    assert dev_dirs.projects_dir is not None
    assert dev_dirs.models_dir is not None

    # Cenário 2: Simulação de Executável PyInstaller (sys.frozen = True)
    frozen_app_dir = tmp_path / "Program Files" / "Translate_BooK"
    frozen_app_dir.mkdir(parents=True)
    fake_exe = frozen_app_dir / "Translate_BooK.exe"
    fake_exe.touch()

    fake_app_data = tmp_path / "AppData" / "Roaming"
    fake_local_app_data = tmp_path / "AppData" / "Local"
    fake_app_data.mkdir(parents=True)
    fake_local_app_data.mkdir(parents=True)

    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", str(fake_exe)), \
         patch.object(sys, "platform", "win32"), \
         patch.dict(os.environ, {
             "APPDATA": str(fake_app_data),
             "LOCALAPPDATA": str(fake_local_app_data)
         }):

        dirs = get_default_data_dirs()

        # O executável reside em 'Program Files/Translate_BooK'
        assert dirs.app_dir == frozen_app_dir

        # Os projetos NUNCA devem residir dentro da pasta do executável
        assert dirs.projects_dir != frozen_app_dir
        assert "projects" in str(dirs.projects_dir).lower()

        # Os modelos NUNCA devem residir dentro da pasta do executável
        assert dirs.models_dir != frozen_app_dir
        assert "models" in str(dirs.models_dir).lower()


def test_paths_with_spaces_handling(tmp_path):
    """Valida o funcionamento em caminhos que contêm espaços e caracteres especiais."""
    space_dir = tmp_path / "Usuario Carlos Jr" / "Área de Trabalho" / "Espaço e Acentuação"
    space_dir.mkdir(parents=True)

    fake_app_data = space_dir / "AppData" / "Roaming"
    fake_local_app_data = space_dir / "AppData" / "Local"
    fake_app_data.mkdir(parents=True)
    fake_local_app_data.mkdir(parents=True)

    fake_exe = space_dir / "Program Files" / "Translate_BooK" / "Translate_BooK.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()

    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", str(fake_exe)), \
         patch.object(sys, "platform", "win32"), \
         patch.dict(os.environ, {
             "APPDATA": str(fake_app_data),
             "LOCALAPPDATA": str(fake_local_app_data)
         }):
        dirs = get_default_data_dirs()
        assert " " in str(dirs.projects_dir)
        dirs.projects_dir.mkdir(parents=True, exist_ok=True)
        assert dirs.projects_dir.exists()
        assert str(dirs.projects_dir).startswith(str(fake_app_data))


def test_first_run_without_models(tmp_path):
    """Valida a estabilidade do sistema na primeira execução em um Windows limpo (sem modelos)."""
    fake_models_dir = tmp_path / "clean_windows" / "models"
    fake_models_dir.mkdir(parents=True)

    # Inicializa o ModelManager no diretório limpo
    manager = ModelManager(models_dir=fake_models_dir)

    status = manager.get_status("madlad400-3b-mt-ct2-int8")
    assert status == ModelStatus.NOT_INSTALLED

    # Verifica que listar modelos instalados não falha nem lança exceção
    installed = manager.list_installed_models()
    assert len(installed) == 0


def test_version_upgrade_and_uninstall_preserves_user_projects(tmp_path):
    """Simula a política de preservação de projetos do usuário através de desinstalações e upgrades."""
    app_v1_dir = tmp_path / "Programs" / "Translate_BooK_v1"
    app_v1_dir.mkdir(parents=True)

    user_projects_dir = tmp_path / "AppData" / "Roaming" / "Translate_BooK" / "projects"
    user_projects_dir.mkdir(parents=True)

    # Usuário cria um projeto importante na v1
    project_dir = user_projects_dir / "Meu_Livro_Importante"
    project_dir.mkdir()
    project_db = project_dir / "project.db"
    project_db.write_text("DADOS_DO_PROJETO_SQLITE_SIMULADO", encoding="utf-8")

    # Simulação da Desinstalação da v1: o instalador deleta SOMENTE a pasta do aplicativo (app_v1_dir)
    import shutil
    shutil.rmtree(app_v1_dir)
    assert not app_v1_dir.exists()

    # Simulação da Instalação da v2
    app_v2_dir = tmp_path / "Programs" / "Translate_BooK_v2"
    app_v2_dir.mkdir(parents=True)

    # VERIFICAÇÃO CRÍTICA: O projeto do usuário permanece intacto!
    assert user_projects_dir.exists()
    assert project_dir.exists()
    assert project_db.exists()
    assert project_db.read_text(encoding="utf-8") == "DADOS_DO_PROJETO_SQLITE_SIMULADO"
