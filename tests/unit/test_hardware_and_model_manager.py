"""Testes unitários para Hardware Profiler e Model Manager (Prompt 24)."""

import hashlib
from pathlib import Path

from book_translator.system import (
    SUPPORTED_MODELS_REGISTRY,
    DiskInfo,
    GpuInfo,
    HardwareProfiler,
    ModelManager,
    ModelStatus,
    RamInfo,
)


def test_hardware_profiler_real_detection(tmp_path: Path):
    """Verifica se o hardware profiler detecta as métricas reais do sistema."""
    profiler = HardwareProfiler(target_path=tmp_path)
    profile = profiler.profile()

    assert profile.cpu.logical_cores >= 1
    assert profile.ram.total_gb > 0.0
    assert profile.disk.total_gb > 0.0
    assert profile.disk.free_gb > 0.0
    assert profile.os_name != ""
    assert profile.recommended_profile in ("economy", "balanced", "quality")


def test_hardware_profiler_suitability_rules():
    """Garante que o profiler nunca finja suficiência sem evidência concreta."""
    profiler = HardwareProfiler()

    disk_ok = DiskInfo(path=".", total_gb=500.0, used_gb=200.0, free_gb=300.0)

    # 1. Hardware Insuficiente (< 8 GB RAM, sem GPU)
    ram_low = RamInfo(total_gb=4.0, available_gb=1.5, used_percent=62.5)
    gpu_none = GpuInfo(available=False)
    prof_rec, can_run, warnings = profiler._evaluate_suitability(ram_low, gpu_none, disk_ok)

    assert can_run is False
    assert prof_rec == "economy"
    assert any("Hardware insuficiente" in w for w in warnings)

    # 2. Hardware Econômico (8 GB RAM, sem GPU)
    ram_eco = RamInfo(total_gb=8.0, available_gb=4.0, used_percent=50.0)
    prof_rec2, can_run2, warnings2 = profiler._evaluate_suitability(ram_eco, gpu_none, disk_ok)
    assert can_run2 is True
    assert prof_rec2 == "economy"

    # 3. Hardware Balanceado (16 GB RAM ou GPU >= 6GB VRAM)
    ram_high = RamInfo(total_gb=16.0, available_gb=10.0, used_percent=37.5)
    prof_rec3, can_run3, _ = profiler._evaluate_suitability(ram_high, gpu_none, disk_ok)
    assert can_run3 is True
    assert prof_rec3 == "balanced"

    # 4. Hardware Alta Qualidade (GPU >= 10GB VRAM)
    gpu_high = GpuInfo(available=True, name="RTX 4080", vram_total_gb=16.0, vram_free_gb=14.0)
    prof_rec4, can_run4, _ = profiler._evaluate_suitability(ram_high, gpu_high, disk_ok)
    assert can_run4 is True
    assert prof_rec4 == "quality"


def test_model_manager_catalog():
    """Valida que todas as entradas do catálogo possuem licenças auditáveis e hashes SHA-256."""
    assert len(SUPPORTED_MODELS_REGISTRY) >= 3

    for model_id, entry in SUPPORTED_MODELS_REGISTRY.items():
        assert entry.model_id == model_id
        assert entry.license == "Apache-2.0"
        assert entry.license_terms_url != ""
        assert len(entry.files) >= 1
        for f in entry.files:
            assert len(f.sha256) == 64  # SHA-256 válido em hex
            assert f.url.startswith("https://")
            assert f.size_bytes > 0


def test_model_manager_status_and_corruption_detection(tmp_path: Path):
    """Testa detecção de status, verificação de integridade e detecção de corrupção."""
    models_dir = tmp_path / "models"
    manager = ModelManager(models_dir=models_dir)

    model_id = "madlad400-3b-mt-ct2-int8"
    entry = manager.get_model_entry(model_id)

    # 1. Inicialmente NOT_INSTALLED
    assert manager.get_model_status(model_id) == ModelStatus.NOT_INSTALLED

    # 2. Simular download corrompido (hash incorreto)
    m_dir = manager.get_model_dir(model_id)
    m_dir.mkdir(parents=True)
    for f in entry.files:
        (m_dir / f.filename).write_bytes(b"corrupted or wrong bytes")

    assert manager.get_model_status(model_id) == ModelStatus.CORRUPTED
    assert manager.verify_model_integrity(model_id) is False

    # 3. Simular arquivos íntegros com hash correto
    # Criamos um modelo fake no registro para testar integridade real
    test_content_1 = b"fake weights for testing model binary"
    test_content_2 = b'{"vocab": "test"}'
    hash_1 = hashlib.sha256(test_content_1).hexdigest()
    hash_2 = hashlib.sha256(test_content_2).hexdigest()

    entry.files[0].sha256 = hash_1
    entry.files[1].sha256 = hash_2
    (m_dir / entry.files[0].filename).write_bytes(test_content_1)
    (m_dir / entry.files[1].filename).write_bytes(test_content_2)

    assert manager.get_model_status(model_id) == ModelStatus.INSTALLED
    assert manager.verify_model_integrity(model_id) is True

    # 4. Selecionar versão ativa
    active = manager.select_active_model(model_id)
    assert active.model_id == model_id
    assert manager.get_active_model() == active

    # 5. Remover modelo
    assert manager.remove_model(model_id) is True
    assert manager.get_model_status(model_id) == ModelStatus.NOT_INSTALLED
    assert manager.get_active_model() is None
