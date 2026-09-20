#!/usr/bin/env python3
"""Script de benchmark reprodutível para avaliação de runtimes e quantizações do MADLAD-400-10B-MT.

Avalia:
- Latência por segmento (média, p95) e Throughput (tokens/s).
- Consumo de memória RAM (Peak RSS) e VRAM (quando disponível).
- Qualidade de tradução EN -> PT-BR vs referências humanas (chrF e F1 léxico).
- Tamanho estimado em disco por quantização (Q4, Q6, Q8, FP16).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

# Adiciona o diretório raiz ao PYTHONPATH se necessário
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from book_translator.core.models import Segment
from book_translator.translation.madlad import (
    DeviceType,
    MadladTranslationEngine,
    QuantizationType,
    RuntimeType,
)


def get_current_rss_mb() -> float:
    """Retorna o consumo atual de RAM do processo em Megabytes (cross-platform)."""
    try:
        import psutil  # type: ignore
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        pass

    # Fallback nativo para Windows via ctypes
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)

            class PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return pmc.WorkingSetSize / (1024 * 1024)
        except Exception:
            pass

    # Fallback para Unix via resource
    try:
        import resource  # type: ignore
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return (usage / 1024) if sys.platform == "darwin" else (usage / 1024 / 1024)
    except Exception:
        pass

    return 0.0


def get_vram_mb() -> float:
    """Retorna o uso de VRAM em MB caso PyTorch CUDA esteja disponível."""
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            return torch.cuda.max_memory_allocated() / (1024 * 1024)
    except Exception:
        pass
    return 0.0


def calculate_token_f1(hypothesis: str, reference: str) -> float:
    """Calcula o F1-Score léxico baseado em unigramas normalizados."""
    hyp_tokens = hypothesis.lower().split()
    ref_tokens = reference.lower().split()
    if not hyp_tokens or not ref_tokens:
        return 0.0

    hyp_counts = Counter(hyp_tokens)
    ref_counts = Counter(ref_tokens)
    overlap = sum((hyp_counts & ref_counts).values())

    precision = overlap / len(hyp_tokens) if hyp_tokens else 0.0
    recall = overlap / len(ref_tokens) if ref_tokens else 0.0
    if precision + recall == 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def calculate_chrf(hypothesis: str, reference: str, n: int = 6, beta: float = 2.0) -> float:
    """Calcula aproximação da métrica chrF (F-score de n-gramas de caracteres)."""
    def get_char_ngrams(s: str, order: int) -> Counter[str]:
        s_clean = "".join(s.lower().split())
        if len(s_clean) < order:
            return Counter()
        return Counter(s_clean[i : i + order] for i in range(len(s_clean) - order + 1))

    f_scores = []
    for order in range(1, n + 1):
        hyp_ngrams = get_char_ngrams(hypothesis, order)
        ref_ngrams = get_char_ngrams(reference, order)
        if not hyp_ngrams or not ref_ngrams:
            continue
        overlap = sum((hyp_ngrams & ref_ngrams).values())
        prec = overlap / sum(hyp_ngrams.values()) if hyp_ngrams else 0.0
        rec = overlap / sum(ref_ngrams.values()) if ref_ngrams else 0.0
        if prec + rec > 0:
            f = ((1 + beta**2) * prec * rec) / ((beta**2 * prec) + rec)
            f_scores.append(f)

    return sum(f_scores) / len(f_scores) if f_scores else 0.0


# Estimativa de tamanho em disco por quantização (base: modelo 10.7B parâmetros)
DISK_SIZE_ESTIMATES_GB: dict[QuantizationType, float] = {
    QuantizationType.Q4: 5.6,
    QuantizationType.Q6: 7.6,
    QuantizationType.Q8: 10.8,
    QuantizationType.FP16: 20.9,
    QuantizationType.BF16: 20.9,
}


@dataclass
class SegmentBenchmarkResult:
    item_id: str
    category: str
    source_text: str
    reference_text: str
    hypothesis_text: str
    latency_ms: float
    token_count: int
    token_f1: float
    chrf_score: float


@dataclass
class BenchmarkSummary:
    runtime: str
    quantization: str
    device: str
    total_segments: int
    total_time_s: float
    avg_latency_ms: float
    p95_latency_ms: float
    total_tokens: int
    throughput_tokens_per_sec: float
    avg_token_f1: float
    avg_chrf_score: float
    peak_ram_mb: float
    peak_vram_mb: float
    estimated_disk_gb: float
    segment_results: list[SegmentBenchmarkResult]


def run_benchmark(
    runtime_type: RuntimeType = RuntimeType.MOCK,
    quantization: QuantizationType = QuantizationType.Q6,
    device: DeviceType = DeviceType.CPU,
    corpus_path: Path | None = None,
    model_path: Path | None = None,
    allow_download: bool = False,
) -> BenchmarkSummary:
    """Executa a bateria de benchmarks sobre o corpus especificado."""
    path = corpus_path or (WORKSPACE_ROOT / "benchmarks" / "corpus" / "literary_en_pt.json")
    if not path.exists():
        raise FileNotFoundError(f"Corpus de benchmark não encontrado: {path}")

    corpus_data = json.loads(path.read_text(encoding="utf-8"))

    # Instancia o motor com o runtime e quantização requisitados
    engine = MadladTranslationEngine(
        runtime_type=runtime_type,
        quantization=quantization,
        device=device,
        model_path=model_path,
        allow_download=allow_download,
    )

    initial_ram = get_current_rss_mb()
    results: list[SegmentBenchmarkResult] = []
    latencies: list[float] = []
    total_tokens = 0

    t_start = time.perf_counter()

    for item in corpus_data:
        seg = Segment(
            id=item["id"],
            chapter_id="benchmark_chap",
            original_text=item["source"],
            sequence_order=1,
        )

        t0 = time.perf_counter()
        draft = engine.translate_segment(seg)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        latencies.append(elapsed_ms)
        hyp_text = draft.selected_text
        ref_text = item["reference"]
        tokens_gen = draft.metadata.get("tokens_generated", len(hyp_text.split()))
        total_tokens += tokens_gen

        f1 = calculate_token_f1(hyp_text, ref_text)
        chrf = calculate_chrf(hyp_text, ref_text)

        results.append(
            SegmentBenchmarkResult(
                item_id=item["id"],
                category=item.get("category", "general"),
                source_text=item["source"],
                reference_text=ref_text,
                hypothesis_text=hyp_text,
                latency_ms=elapsed_ms,
                token_count=tokens_gen,
                token_f1=round(f1, 4),
                chrf_score=round(chrf, 4),
            )
        )

    total_time = time.perf_counter() - t_start
    final_ram = get_current_rss_mb()
    peak_vram = get_vram_mb()

    latencies_sorted = sorted(latencies)
    p95_idx = int(len(latencies_sorted) * 0.95)
    p95_latency = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)]

    summary = BenchmarkSummary(
        runtime=runtime_type.value,
        quantization=quantization.value,
        device=device.value,
        total_segments=len(results),
        total_time_s=round(total_time, 3),
        avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        p95_latency_ms=round(p95_latency, 2),
        total_tokens=total_tokens,
        throughput_tokens_per_sec=round(total_tokens / total_time, 2) if total_time > 0 else 0.0,
        avg_token_f1=round(sum(r.token_f1 for r in results) / len(results), 4) if results else 0.0,
        avg_chrf_score=round(sum(r.chrf_score for r in results) / len(results), 4) if results else 0.0,
        peak_ram_mb=round(final_ram or initial_ram, 1),
        peak_vram_mb=round(peak_vram, 1),
        estimated_disk_gb=DISK_SIZE_ESTIMATES_GB.get(quantization, 10.0),
        segment_results=results,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MADLAD-400-10B-MT Controlled Benchmark Runner (Prompt 14)"
    )
    parser.add_argument(
        "--runtime",
        type=str,
        choices=["mock", "ctranslate2", "transformers"],
        default="mock",
        help="Runtime de inferência (padrão: mock para CI e benchmarks reprodutíveis)",
    )
    parser.add_argument(
        "--quantization",
        type=str,
        choices=["q4", "q6", "q8", "fp16", "bf16"],
        default="q6",
        help="Nível de quantização (padrão: q6)",
    )
    parser.add_argument(
        "--device",
        type=str,
        choices=["cpu", "cuda", "directml", "auto"],
        default="cpu",
        help="Dispositivo de computação (padrão: cpu)",
    )
    parser.add_argument(
        "--corpus",
        type=str,
        default="",
        help="Caminho para arquivo JSON de corpus",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default="",
        help="Caminho local dos pesos do modelo (caso use ctranslate2 ou transformers)",
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Permite download de pesos (DESATIVADO por padrão por segurança)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="",
        help="Caminho para salvar relatório JSON bruto",
    )

    args = parser.parse_args()

    rt_map = {
        "mock": RuntimeType.MOCK,
        "ctranslate2": RuntimeType.CTRANSLATE2,
        "transformers": RuntimeType.TRANSFORMERS,
    }
    quant_map = {
        "q4": QuantizationType.Q4,
        "q6": QuantizationType.Q6,
        "q8": QuantizationType.Q8,
        "fp16": QuantizationType.FP16,
        "bf16": QuantizationType.BF16,
    }
    dev_map = {
        "cpu": DeviceType.CPU,
        "cuda": DeviceType.CUDA,
        "directml": DeviceType.DIRECTML,
        "auto": DeviceType.AUTO,
    }

    corpus_p = Path(args.corpus) if args.corpus else None
    model_p = Path(args.model_path) if args.model_path else None

    print("\n" + "=" * 70)
    print("MADLAD-400-10B-MT RUNTIME & QUANTIZATION BENCHMARK")
    print(f"Runtime:      {args.runtime.upper()}")
    print(f"Quantização:  {args.quantization.upper()} ({quant_map[args.quantization].value})")
    print(f"Dispositivo:  {args.device.upper()}")
    print("=" * 70)

    summary = run_benchmark(
        runtime_type=rt_map[args.runtime],
        quantization=quant_map[args.quantization],
        device=dev_map[args.device],
        corpus_path=corpus_p,
        model_path=model_p,
        allow_download=args.allow_download,
    )

    print("\n--- RESULTADOS GERAIS ---")
    print(f"Segmentos processados:       {summary.total_segments}")
    print(f"Tempo total de inferência:   {summary.total_time_s} s")
    print(f"Latência média por segmento: {summary.avg_latency_ms} ms")
    print(f"Latência p95 por segmento:   {summary.p95_latency_ms} ms")
    print(f"Throughput de geração:       {summary.throughput_tokens_per_sec} tokens/s")
    print(f"Qualidade léxica (Token F1): {summary.avg_token_f1 * 100:.2f}%")
    print(f"Qualidade morfológica (chrF):{summary.avg_chrf_score * 100:.2f}%")
    print(f"Consumo de RAM (RSS):        {summary.peak_ram_mb} MB")
    print(f"Consumo de VRAM:             {summary.peak_vram_mb} MB")
    print(f"Tamanho estimado em disco:   {summary.estimated_disk_gb} GB")
    print("=" * 70 + "\n")

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(asdict(summary), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Relatório exportado para: {out_path}")


if __name__ == "__main__":
    main()
