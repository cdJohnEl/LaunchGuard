"""Eval harness for the scam engine: scam recall and false positive rate on the labeled dataset."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _path in (str(_BACKEND), str(_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

os.environ.setdefault("LAUNCHGUARD_LLM_PROVIDER", "mock")

from scam_engine import evaluate

SCAM_RECALL_MIN = 0.85
FPR_MAX = 0.15
DATASET_PATH = Path(__file__).resolve().parent / "dataset.jsonl"


def load_rows(path: Path = DATASET_PATH) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("label") not in ("scam", "ham") or not row.get("text"):
            raise ValueError(f"bad dataset row: {line!r}")
        rows.append({"text": row["text"], "label": row["label"]})
    return rows


async def _predict_all(rows: list[dict]) -> list[bool]:
    flagged = []
    for row in rows:
        decision = await evaluate(row["text"])
        flagged.append(bool(decision.delete))
    return flagged


def predict(rows: list[dict]) -> list[bool]:
    return asyncio.run(_predict_all(rows))


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def compute_metrics(rows: list[dict], preds: list[bool]) -> dict:
    tp = fp = tn = fn = 0
    for row, pred in zip(rows, preds):
        actual_scam = row["label"] == "scam"
        if actual_scam and pred:
            tp += 1
        elif actual_scam and not pred:
            fn += 1
        elif not actual_scam and pred:
            fp += 1
        else:
            tn += 1
    return {
        "scam": _prf(tp, fp, fn),
        "ham": _prf(tn, fn, fp),
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
        "counts": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "failures": [
            {"text": row["text"], "label": row["label"]}
            for row, pred in zip(rows, preds)
            if (row["label"] == "scam") != pred
        ],
    }


def format_table(rows: list[dict], metrics: dict) -> str:
    counts = metrics["counts"]
    total = len(rows)
    scam_total = counts["tp"] + counts["fn"]
    ham_total = counts["tn"] + counts["fp"]
    lines = [
        f"scam engine eval — {total} rows ({scam_total} scam / {ham_total} ham)",
        "",
        "label   tp  fp  fn  tn  precision  recall  f1",
        f"scam    {counts['tp']:>3}  {counts['fp']:>3}  {counts['fn']:>3}  {'-':>3}  "
        f"{metrics['scam']['precision']:>9.3f}  {metrics['scam']['recall']:>6.3f}  {metrics['scam']['f1']:>5.3f}",
        f"ham     {'-':>3}  {counts['fn']:>3}  {counts['fp']:>3}  {counts['tn']:>3}  "
        f"{metrics['ham']['precision']:>9.3f}  {metrics['ham']['recall']:>6.3f}  {metrics['ham']['f1']:>5.3f}",
        "",
        f"overall FPR {metrics['fpr']:.3f} (max {FPR_MAX:.3f})",
        f"scam recall {metrics['scam']['recall']:.3f} (min {SCAM_RECALL_MIN:.3f})",
    ]
    if metrics["failures"]:
        lines.append("")
        lines.append(f"failures ({len(metrics['failures'])}):")
        for fail in metrics["failures"][:15]:
            lines.append(f"  [{fail['label']}] {fail['text']}")
    return "\n".join(lines)


def main() -> int:
    rows = load_rows()
    metrics = compute_metrics(rows, predict(rows))
    print(format_table(rows, metrics))
    passed = metrics["scam"]["recall"] >= SCAM_RECALL_MIN and metrics["fpr"] <= FPR_MAX
    print(f"\n{'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
