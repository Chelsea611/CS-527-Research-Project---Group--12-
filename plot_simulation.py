"""
Plot recovery-time distributions from simulation_results.csv (extended schema).

Requires: pip install matplotlib

Usage:
  python plot_simulation.py --input simulation_results.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def _recovered_ok(val: object) -> bool:
    return val is True or str(val).lower() == "true"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def generate_plots(csv_path: str | Path, out_dir: str | Path | None = None) -> list[Path]:
    csv_path = Path(csv_path)
    out_dir = Path(out_dir) if out_dir else csv_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise SystemExit(
            "matplotlib is required for plotting. Install with: pip install matplotlib"
        ) from e

    rows = load_rows(csv_path)
    if not rows:
        raise SystemExit("No rows in CSV")

    # (fault_type, config_id) -> list of times (successful only)
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if not _recovered_ok(r.get("recovered")):
            continue
        ft = r.get("fault_type") or "unknown"
        cid = r.get("config_id") or "default"
        buckets[(ft, cid)].append(float(r["time_s"]))

    fault_types = sorted({ft for ft, _ in buckets.keys()})
    config_ids = sorted({cid for _, cid in buckets.keys()})

    # --- Figure 1: boxplot per fault type, grouped by config ---
    fig1, axes = plt.subplots(1, len(fault_types), figsize=(5 * len(fault_types), 4.5), squeeze=False)
    for ax, ft in zip(axes[0], fault_types):
        data = [buckets.get((ft, cid), []) for cid in config_ids]
        labels = config_ids
        ax.boxplot(data, labels=labels, showfliers=True)
        ax.set_title(ft)
        ax.set_ylabel("Recovery time (s)")
        ax.tick_params(axis="x", labelrotation=35)
        ax.grid(True, axis="y", linestyle=":", alpha=0.6)
    fig1.suptitle("Recovery time by fault type and environment config")
    fig1.tight_layout()
    p1 = out_dir / "plot_recovery_box_by_fault.png"
    fig1.savefig(p1, dpi=150)
    plt.close(fig1)

    # --- Figure 2: cold vs warm (all configs flattened per fault) ---
    cold_warm: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if not _recovered_ok(r.get("recovered")):
            continue
        ft = r.get("fault_type") or "unknown"
        cohort = "cold" if str(r.get("cold_start", "")).lower() == "true" else "warm"
        cold_warm[(ft, cohort)].append(float(r["time_s"]))

    fig2, axes2 = plt.subplots(1, len(fault_types), figsize=(5 * len(fault_types), 4.5), squeeze=False)
    for ax, ft in zip(axes2[0], fault_types):
        d_cold = cold_warm.get((ft, "cold"), [])
        d_warm = cold_warm.get((ft, "warm"), [])
        ax.boxplot([d_cold, d_warm], labels=["cold", "warm"], showfliers=True)
        ax.set_title(ft)
        ax.set_ylabel("Recovery time (s)")
        ax.grid(True, axis="y", linestyle=":", alpha=0.6)
    fig2.suptitle("Cold (first trial on fresh system) vs warm (subsequent trials)")
    fig2.tight_layout()
    p2 = out_dir / "plot_recovery_cold_vs_warm.png"
    fig2.savefig(p2, dpi=150)
    plt.close(fig2)

    print(f"[plot_simulation] Wrote {p1.name}, {p2.name} -> {out_dir.resolve()}")
    return [p1, p2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=str, default="simulation_results.csv")
    ap.add_argument("--out-dir", type=str, default=".")
    args = ap.parse_args()
    generate_plots(args.input, args.out_dir)


if __name__ == "__main__":
    main()
