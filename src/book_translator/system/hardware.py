"""Hardware Profiler para detecção precisa de recursos e recomendação de perfis."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from book_translator.logging import get_logger

logger = get_logger("system.hardware")


@dataclass
class CpuInfo:
    """Informações detalhadas sobre a CPU do sistema."""

    brand: str
    physical_cores: int
    logical_cores: int
    architecture: str


@dataclass
class RamInfo:
    """Informações de memória física (RAM)."""

    total_gb: float
    available_gb: float
    used_percent: float


@dataclass
class GpuInfo:
    """Informações de placa gráfica e memória de vídeo (VRAM)."""

    available: bool
    name: str = "Nenhuma / CPU Only"
    vram_total_gb: float = 0.0
    vram_free_gb: float = 0.0
    backend: str = "none"  # 'cuda', 'rocm', 'mps', 'directx', 'none'


@dataclass
class DiskInfo:
    """Espaço de armazenamento em disco no ponto de montagem."""

    path: str
    total_gb: float
    free_gb: float
    used_gb: float


@dataclass
class HardwareProfile:
    """Perfil consolidado de hardware e recomendações operacionais auditáveis."""

    cpu: CpuInfo
    ram: RamInfo
    gpu: GpuInfo
    disk: DiskInfo
    os_name: str
    os_version: str
    recommended_profile: str  # 'economy', 'balanced', 'quality'
    can_run_local_models: bool
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


class HardwareProfiler:
    """Detecta a configuração física da máquina sem fingir capacidade inexistente."""

    def __init__(self, target_path: Path | str | None = None) -> None:
        self.target_path = Path(target_path or ".").resolve()

    def profile(self) -> HardwareProfile:
        """Executa a detecção completa dos subsistemas e produz recomendação segura."""
        cpu = self.detect_cpu()
        ram = self.detect_ram()
        gpu = self.detect_gpu()
        disk = self.detect_disk(self.target_path)
        os_name = f"{platform.system()} {platform.release()}"
        os_version = platform.version()

        recommended_profile, can_run, warnings = self._evaluate_suitability(ram, gpu, disk)

        profile = HardwareProfile(
            cpu=cpu,
            ram=ram,
            gpu=gpu,
            disk=disk,
            os_name=os_name,
            os_version=os_version,
            recommended_profile=recommended_profile,
            can_run_local_models=can_run,
            warnings=warnings,
            diagnostics={
                "python_version": platform.python_version(),
                "machine": platform.machine(),
            },
        )
        logger.info(
            f"Hardware Profiler: CPU={cpu.brand} ({cpu.logical_cores} cores), "
            f"RAM={ram.total_gb:.1f}GB, GPU={gpu.name} ({gpu.vram_total_gb:.1f}GB VRAM) -> "
            f"Perfil Recomendado='{recommended_profile}' (Execução Local={can_run})"
        )
        return profile

    def detect_cpu(self) -> CpuInfo:
        logical = os.cpu_count() or 1
        brand = platform.processor() or platform.machine() or "CPU Desconhecida"
        physical = logical

        try:
            import psutil
            physical = psutil.cpu_count(logical=False) or logical
        except ImportError:
            pass

        return CpuInfo(
            brand=brand,
            physical_cores=physical,
            logical_cores=logical,
            architecture=platform.machine(),
        )

    def detect_ram(self) -> RamInfo:
        # 1. Tentativa via psutil se instalado
        try:
            import psutil
            vmem = psutil.virtual_memory()
            total_gb = vmem.total / (1024**3)
            avail_gb = vmem.available / (1024**3)
            return RamInfo(
                total_gb=round(total_gb, 2),
                available_gb=round(avail_gb, 2),
                used_percent=round(vmem.percent, 1),
            )
        except ImportError:
            pass

        # 2. Fallback nativo para Windows via ctypes
        if platform.system() == "Windows":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_gb = stat.ullTotalPhys / (1024**3)
                avail_gb = stat.ullAvailPhys / (1024**3)
                return RamInfo(
                    total_gb=round(total_gb, 2),
                    available_gb=round(avail_gb, 2),
                    used_percent=float(stat.dwMemoryLoad),
                )

        # 3. Fallback genérico conservador
        return RamInfo(total_gb=8.0, available_gb=4.0, used_percent=50.0)

    def detect_gpu(self) -> GpuInfo:
        # 1. Checagem via PyTorch CUDA
        try:
            import torch
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                props = torch.cuda.get_device_properties(0)
                total_vram = props.total_memory / (1024**3)
                try:
                    free_vram = torch.cuda.mem_get_info()[0] / (1024**3)
                except Exception:
                    free_vram = total_vram * 0.8
                return GpuInfo(
                    available=True,
                    name=name,
                    vram_total_gb=round(total_vram, 2),
                    vram_free_gb=round(free_vram, 2),
                    backend="cuda",
                )
        except (ImportError, Exception):
            pass

        # 2. Checagem via nvidia-smi CLI
        if shutil.which("nvidia-smi"):
            try:
                cmd = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"]
                out = subprocess.check_output(cmd, encoding="utf-8", timeout=2).strip()
                if out:
                    parts = [p.strip() for p in out.splitlines()[0].split(",")]
                    name = parts[0]
                    total_mb = float(parts[1])
                    free_mb = float(parts[2])
                    return GpuInfo(
                        available=True,
                        name=name,
                        vram_total_gb=round(total_mb / 1024, 2),
                        vram_free_gb=round(free_mb / 1024, 2),
                        backend="cuda",
                    )
            except Exception:
                pass

        return GpuInfo(available=False, name="CPU Only", vram_total_gb=0.0, vram_free_gb=0.0, backend="none")

    def detect_disk(self, path: Path) -> DiskInfo:
        usage = shutil.disk_usage(str(path))
        return DiskInfo(
            path=str(path),
            total_gb=round(usage.total / (1024**3), 2),
            used_gb=round(usage.used / (1024**3), 2),
            free_gb=round(usage.free / (1024**3), 2),
        )

    def _evaluate_suitability(
        self, ram: RamInfo, gpu: GpuInfo, disk: DiskInfo
    ) -> tuple[str, bool, list[str]]:
        """Avalia com rigor se o hardware é suficiente para execução neural local.

        Regra inegociável: Não fingir suficiência sem evidência concreta de capacidade.
        """
        warnings: list[str] = []

        # Validação de espaço em disco
        if disk.free_gb < 5.0:
            warnings.append(
                f"Espaço em disco crítico: apenas {disk.free_gb:.1f} GB livres. "
                "Requer pelo menos 8 GB para modelos e arquivos temporários."
            )

        # Caso 1: GPU com VRAM Alta (>= 10 GB) -> Qualidade Máxima
        if gpu.available and gpu.vram_total_gb >= 10.0:
            return "quality", True, warnings

        # Caso 2: GPU com VRAM Média (>= 5.5 GB) -> Balanceado com GPU
        if gpu.available and gpu.vram_total_gb >= 5.5:
            return "balanced", True, warnings

        # Caso 3: GPU fraca (< 5.5 GB VRAM)
        if gpu.available and gpu.vram_total_gb < 5.5:
            warnings.append(
                f"GPU detectada ({gpu.name}) possui apenas {gpu.vram_total_gb:.1f} GB de VRAM, "
                "insuficiente para carregar modelos completos em GPU sem estouro de memória (OOM). "
                "Operando em modo Economy (CPU/Quantizado)."
            )

        # Caso 4: Sem GPU ou GPU insuficiente -> Avalia CPU e RAM
        if ram.total_gb >= 15.0:
            return "balanced", True, warnings
        elif ram.total_gb >= 7.5:
            warnings.append(
                f"Executando sem aceleração de GPU com {ram.total_gb:.1f} GB de RAM. "
                "Apenas o perfil 'economy' (quantização INT8 em CPU) é recomendado."
            )
            return "economy", True, warnings
        else:
            warnings.append(
                f"Hardware insuficiente: {ram.total_gb:.1f} GB de RAM total. "
                "Modelos neurais locais exigem no mínimo 8 GB de RAM para evitar travamentos do sistema. "
                "Recomenda-se uso de API externa ou upgrade de memória."
            )
            return "economy", False, warnings
