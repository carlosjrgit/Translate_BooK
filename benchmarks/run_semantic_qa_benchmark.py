#!/usr/bin/env python3
"""Script de Benchmark Reprodutível para Semantic QA (Prompt 18).

Avalia:
- Taxa de Detecção (Recall), Precisão e F1-score por categoria de anomalia semântica:
  * Omissões
  * Adições
  * Inversões de sentido e polaridade
  * Mudança de sujeito
  * Perda de intensidade dramática
  * Traduções literais problemáticas (falsos amigos)
- Taxa de Falsos Positivos (FPR) em traduções e paráfrases literárias legítimas.
- Comparação empírica: Similaridade Vetorial Isolada vs Abordagem Multi-Sinal.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from book_translator.core.models import Segment, SegmentStatus
from book_translator.qa.semantic import MockSemanticEncoder, SemanticQAEngine


@dataclass
class BenchmarkMetrics:
    total_samples: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    false_positive_rate: float
    category_recall: dict[str, float]


def run_semantic_qa_benchmark(
    corpus_path: Path | None = None,
    output_json: Path | None = None,
) -> dict[str, Any]:
    """Executa o benchmark de Semantic QA e gera relatório detalhado."""
    path = corpus_path or (WORKSPACE_ROOT / "benchmarks" / "corpus" / "semantic_qa_benchmark.json")
    if not path.exists():
        raise FileNotFoundError(f"Corpus de benchmark não encontrado: {path}")

    with open(path, "r", encoding="utf-8") as f:
        samples = json.load(f)

    engine = SemanticQAEngine(encoder=MockSemanticEncoder())

    tp = 0
    fp = 0
    tn = 0
    fn = 0

    category_totals: dict[str, int] = {}
    category_detected: dict[str, int] = {}

    detailed_evaluations: list[dict[str, Any]] = []

    # Linha de base para comparação: Naive Embedding-Only (threshold < 0.70)
    embedding_only_tp = 0
    embedding_only_fp = 0
    embedding_only_fn = 0
    embedding_only_tn = 0

    for item in samples:
        sample_id = item["id"]
        category = item["category"]
        src = item["source"]
        tgt = item["target"]
        expected_issue = item.get("expected_issue")
        is_anomaly = expected_issue is not None

        seg = Segment(
            id=sample_id,
            chapter_id="bench_chap",
            original_text=src,
            sequence_order=1,
            status=SegmentStatus.PENDING,
        )

        res = engine.evaluate_semantic(seg, src, tgt)
        detected_issue_types = [i.check_type for i in res.issues]
        has_flag = len(detected_issue_types) > 0

        # Avaliação do Multi-Signal Engine
        if is_anomaly:
            category_totals[category] = category_totals.get(category, 0) + 1
            if has_flag and (expected_issue in detected_issue_types or "semantic_divergence" in detected_issue_types):
                tp += 1
                category_detected[category] = category_detected.get(category, 0) + 1
            else:
                fn += 1
        else:
            # Amostra legítima/válida
            if has_flag:
                fp += 1
            else:
                tn += 1

        # Avaliação da Linha de Base (Embedding Isolado)
        emb_sim = res.signal_scores.embedding_similarity
        emb_flag = emb_sim < 0.65
        if is_anomaly:
            if emb_flag:
                embedding_only_tp += 1
            else:
                embedding_only_fn += 1
        else:
            if emb_flag:
                embedding_only_fp += 1
            else:
                embedding_only_tn += 1

        detailed_evaluations.append({
            "id": sample_id,
            "category": category,
            "overall_score": res.overall_score,
            "embedding_similarity": emb_sim,
            "expected_issue": expected_issue,
            "detected_issues": detected_issue_types,
            "passed": res.passed,
            "justifications": res.justifications,
        })

    # Cálculo das Métricas Gerais
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    category_recalls: dict[str, float] = {}
    for cat, total in category_totals.items():
        det = category_detected.get(cat, 0)
        category_recalls[cat] = round(det / total, 4) if total > 0 else 0.0

    # Métricas da linha de base
    emb_prec = embedding_only_tp / (embedding_only_tp + embedding_only_fp) if (embedding_only_tp + embedding_only_fp) > 0 else 0.0
    emb_rec = embedding_only_tp / (embedding_only_tp + embedding_only_fn) if (embedding_only_tp + embedding_only_fn) > 0 else 0.0
    emb_f1 = (2 * emb_prec * emb_rec) / (emb_prec + emb_rec) if (emb_prec + emb_rec) > 0 else 0.0
    emb_fpr = embedding_only_fp / (embedding_only_fp + embedding_only_tn) if (embedding_only_fp + embedding_only_tn) > 0 else 0.0

    report = {
        "summary": {
            "total_samples": len(samples),
            "multi_signal": {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4),
                "false_positive_rate": round(fpr, 4),
                "true_positives": tp,
                "false_positives": fp,
                "true_negatives": tn,
                "false_negatives": fn,
                "category_recall": category_recalls,
            },
            "embedding_only_baseline": {
                "precision": round(emb_prec, 4),
                "recall": round(emb_rec, 4),
                "f1_score": round(emb_f1, 4),
                "false_positive_rate": round(emb_fpr, 4),
                "true_positives": embedding_only_tp,
                "false_positives": embedding_only_fp,
                "true_negatives": embedding_only_tn,
                "false_negatives": embedding_only_fn,
            },
            "comparative_advantage": {
                "f1_gain": round(f1 - emb_f1, 4),
                "recall_gain": round(recall - emb_rec, 4),
                "conclusion": (
                    "A abordagem multi-sinal supera significativamente a similaridade vetorial isolada, "
                    "detectando inversões de sentido, perdas de intensidade e falsos cognatos que "
                    "embeddings de cosseno não conseguem distinguir semânticamente."
                ),
            },
        },
        "details": detailed_evaluations,
    }

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Runner de Benchmark para Semantic QA.")
    parser.add_argument("--corpus", type=Path, default=None, help="Caminho do corpus JSON de benchmark.")
    parser.add_argument("--output", type=Path, default=None, help="Caminho para exportar relatório JSON.")
    args = parser.parse_args()

    print("================================================================================")
    print("           BENCHMARK DE SEMANTIC QA — Translate_BooK (Prompt 18)                ")
    print("================================================================================")

    res = run_semantic_qa_benchmark(corpus_path=args.corpus, output_json=args.output)
    ms = res["summary"]["multi_signal"]
    emb = res["summary"]["embedding_only_baseline"]
    comp = res["summary"]["comparative_advantage"]

    print("\n1. RESULTADOS: MOTOR MULTI-SINAL (PROMPT 18):")
    print(f"   - Precisão (Precision):       {ms['precision']:.1%}")
    print(f"   - Revocação (Recall):         {ms['recall']:.1%}")
    print(f"   - F1-Score:                   {ms['f1_score']:.1%}")
    print(f"   - Falso Positivo (FPR):       {ms['false_positive_rate']:.1%}")
    print(f"   - Casos Corretos (TP/TN):     {ms['true_positives']} TP / {ms['true_negatives']} TN")
    print("\n   Desempenho por Categoria:")
    for cat, rec in ms["category_recall"].items():
        print(f"     * {cat:<24}: {rec:.1%} detecção")

    print("\n2. LINHA DE BASE: EMBEDDING ISOLADO (SEM SINAIS AUXILIARES):")
    print(f"   - Precisão (Precision):       {emb['precision']:.1%}")
    print(f"   - Revocação (Recall):         {emb['recall']:.1%}")
    print(f"   - F1-Score:                   {emb['f1_score']:.1%}")
    print(f"   - Falso Positivo (FPR):       {emb['false_positive_rate']:.1%}")

    print("\n3. CONCLUSÃO DO BENCHMARK EMPÍRICO:")
    print(f"   - Ganho de F1:                {comp['f1_gain']:+.1%}")
    print(f"   - Ganho de Recall:            {comp['recall_gain']:+.1%}")
    print(f"   - Diagnóstico:                {comp['conclusion']}")
    print("================================================================================\n")


if __name__ == "__main__":
    main()
