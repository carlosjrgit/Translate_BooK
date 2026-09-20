"""Subsistema de diagnóstico de hardware, gerenciamento de modelos e recursos do sistema."""

from book_translator.system.hardware import (
    CpuInfo,
    DiskInfo,
    GpuInfo,
    HardwareProfile,
    HardwareProfiler,
    RamInfo,
)
from book_translator.system.model_manager import (
    SUPPORTED_MODELS_REGISTRY,
    ModelCatalogEntry,
    ModelFileMetadata,
    ModelManager,
    ModelStatus,
)

__all__ = [
    "CpuInfo",
    "DiskInfo",
    "GpuInfo",
    "HardwareProfile",
    "HardwareProfiler",
    "RamInfo",
    "ModelCatalogEntry",
    "ModelFileMetadata",
    "ModelManager",
    "ModelStatus",
    "SUPPORTED_MODELS_REGISTRY",
]
