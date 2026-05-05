"""
Plot recovery-time distributions and environment/load effects from simulation_results.csv.

Requires: pip install matplotlib

Usage:
  python plot_simulation.py --input simulation_results.csv
  python plot_simulation.py --input simulation_results.csv --out-dir figures
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def _recovered_ok(val: object) -> bool:
    return val is True or str(val).lower() == "true"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# Stable ordering for axes (matches run_simulation.EnvConfig.default_grid)
CONFIG_ORDER = ["idle_d0", "idle_d100", "stress_d0", "stress_d100"]
FAULT_ORDER = ["Network Timeout", "Database Failure", "Server Crash"]


def _fault_types_present(rows: list[dict[str, str]]) -> list[str]:
    seen = {r.get("fault_type") or "" for r in rows}
    ordered = [f for f in FAULT_ORDER if f in seen]
    rest = sorted(f for f in seen if f and f not in ordered)
    return ordered + rest


def _config_ids_present(rows: list[dict[str, str]]) -> list[str]:
    seen = {r.get("config_id") or "" for r in rows}
    ordered = [c for c in CONFIG_ORDER if c in seen]
    rest = sorted(c for c in seen if c and c not in ordered)
    return ordered + rest


def _boxplot(ax, data: list[list[float]], labels: list[str]) -> None:
    try:
        ax.boxplot(data, tick_labels=labels, showfliers=True)
    except TypeError:
        ax.boxplot(data, labels=labels, showfliers=True)


def _stats_matrix(
    rows: list[dict[str, str]], fault_types: list[str], config_ids: list[str]
) -> tuple[list[list[float]], list[list[float]]]:
    """Per (fault, config): list of times, then mean/std matrices (fault x config)."""
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if not _recovered_ok(r.get("recovered")):
            continue
        ft = r.get("fault_type") or "unknown"
        cid = r.get("config_id") or "default"
        buckets[(ft, cid)].append(float(r["time_s"]))

    means: list[list[float]] = []
    stds: list[list[float]] = []
    for ft in fault_types:
        row_m: list[float] = []
        row_s: list[float] = []
        for cid in config_ids:
            xs = buckets.get((ft, cid), [])
            if xs:
                row_m.append(statistics.fmean(xs))
                row_s.append(statistics.stdev(xs) if len(xs) > 1 else 0.0)
            else:
                row_m.append(float("nan"))
                row_s.append(0.0)
        means.append(row_m)
        stds.append(row_s)
    return means, stds


def generate_plots(csv_path: str | Path, out_dir: str | Path | None = None) -> list[Path]:
    csv_path = Path(csv_path)
    out_dir = Path(out_dir) if out_dir else csv_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as e:
        raise SystemExit(
            "matplotlib (and numpy, usually bundled with mpl stacks) is required. "
            "Install with: pip install matplotlib"
        ) from e

    rows = load_rows(csv_path)
    if not rows:
        raise SystemExit("No rows in CSV")

    fault_types = _fault_types_present(rows)
    config_ids = _config_ids_present(rows)
    means, stds = _stats_matrix(rows, fault_types, config_ids)

    written: list[Path] = []

    # --- Figure 1: boxplot per fault type, grouped by config ---
    fig1, axes = plt.subplots(1, len(fault_types), figsize=(4.2 * len(fault_types), 4.2), squeeze=False)
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if not _recovered_ok(r.get("recovered")):
            continue
        ft = r.get("fault_type") or "unknown"
        cid = r.get("config_id") or "default"
        buckets[(ft, cid)].append(float(r["time_s"]))

    for ax, ft in zip(axes[0], fault_types):
        data = [buckets.get((ft, cid), []) for cid in config_ids]
        _boxplot(ax, data, config_ids)
        ax.set_title(ft, fontsize=11)
        ax.set_ylabel("Recovery time (s)")
        ax.tick_params(axis="x", labelrotation=30)
        ax.grid(True, axis="y", linestyle=":", alpha=0.6)
    fig1.suptitle("Recovery time distributions by environment (boxplot)")
    fig1.tight_layout()
    p1 = out_dir / "plot_recovery_box_by_fault.png"
    fig1.savefig(p1, dpi=150, bbox_inches="tight")
    plt.close(fig1)
    written.append(p1)

    # --- Figure 2: cold vs warm ---
    cold_warm: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if not _recovered_ok(r.get("recovered")):
            continue
        ft = r.get("fault_type") or "unknown"
        cohort = "cold" if str(r.get("cold_start", "")).lower() == "true" else "warm"
        cold_warm[(ft, cohort)].append(float(r["time_s"]))

    fig2, axes2 = plt.subplots(1, len(fault_types), figsize=(4.2 * len(fault_types), 4.2), squeeze=False)
    for ax, ft in zip(axes2[0], fault_types):
        d_cold = cold_warm.get((ft, "cold"), [])
        d_warm = cold_warm.get((ft, "warm"), [])
        _boxplot(ax, [d_cold, d_warm], ["cold", "warm"])
        ax.set_title(ft, fontsize=11)
        ax.set_ylabel("Recovery time (s)")
        ax.grid(True, axis="y", linestyle=":", alpha=0.6)
    fig2.suptitle("Cold (first trial) vs warm (later trials), all configs pooled")
    fig2.tight_layout()
    p2 = out_dir / "plot_recovery_cold_vs_warm.png"
    fig2.savefig(p2, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    written.append(p2)

    # --- Figure 3: heatmap of mean recovery time (fault x config) ---
    M = np.array(means, dtype=float)
    fig3, ax3 = plt.subplots(figsize=(6.5, 3.8))
    im = ax3.imshow(M, aspect="auto", cmap="viridis")
    cbar = fig3.colorbar(im, ax=ax3)
    cbar.set_label("Mean time (s)")
    ax3.set_xticks(range(len(config_ids)))
    ax3.set_xticklabels(config_ids, rotation=25, ha="right")
    ax3.set_yticks(range(len(fault_types)))
    ax3.set_yticklabels(fault_types)
    ax3.set_xlabel("Environment config")
    ax3.set_ylabel("Fault type")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if not np.isnan(M[i, j]):
                ax3.text(
                    j,
                    i,
                    f"{M[i, j]:.2f}",
                    ha="center",
                    va="center",
                    color="white" if M[i, j] < np.nanmedian(M) else "black",
                    fontsize=8,
                )
    fig3.suptitle("Mean recovery time: environment × fault type")
    fig3.tight_layout()
    p3 = out_dir / "plot_mean_heatmap.png"
    fig3.savefig(p3, dpi=150, bbox_inches="tight")
    plt.close(fig3)
    written.append(p3)

    # --- Figure 4: grouped mean ± std bars (one panel per fault) ---
    x = np.arange(len(config_ids))
    w = 0.72
    fig4, axes4 = plt.subplots(1, len(fault_types), figsize=(4.0 * len(fault_types), 4.0), squeeze=False)
    for ax, ft, mrow, srow in zip(axes4[0], fault_types, means, stds):
        ax.bar(x, mrow, width=w, yerr=srow, capsize=3, color="steelblue", ecolor="dimgray", alpha=0.88)
        ax.set_xticks(x)
        ax.set_xticklabels(config_ids, rotation=28, ha="right", fontsize=8)
        ax.set_title(ft, fontsize=11)
        ax.set_ylabel("Mean ± stdev (s)")
        ax.grid(True, axis="y", linestyle=":", alpha=0.6)
    fig4.suptitle("Mean recovery time by environment (error bars = sample stdev)")
    fig4.tight_layout()
    p4 = out_dir / "plot_mean_bar_by_fault.png"
    fig4.savefig(p4, dpi=150, bbox_inches="tight")
    plt.close(fig4)
    written.append(p4)

    # --- Figure 5: line plot — sweep configs for each fault ---
    fig5, ax5 = plt.subplots(figsize=(7.0, 4.2))
    xi = list(range(len(config_ids)))
    for ft, mrow in zip(fault_types, means):
        ax5.plot(xi, mrow, marker="o", linewidth=2, label=ft)
    ax5.set_xticks(xi)
    ax5.set_xticklabels(config_ids, rotation=22, ha="right")
    ax5.set_ylabel("Mean recovery time (s)")
    ax5.set_xlabel("Environment (idle/stress × net delay knob)")
    ax5.legend(loc="best", fontsize=9)
    ax5.grid(True, linestyle=":", alpha=0.6)
    ax5.set_title("How mean recovery time changes across environment cells")
    fig5.tight_layout()
    p5 = out_dir / "plot_mean_line_by_env.png"
    fig5.savefig(p5, dpi=150, bbox_inches="tight")
    plt.close(fig5)
    written.append(p5)

    # --- Figure 6: stress uplift (stress - idle) at d0 and d100 per fault ---
    def mean_for(ft: str, cid: str) -> float | None:
        key = (ft, cid)
        xs = buckets.get(key, [])
        return statistics.fmean(xs) if xs else None

    pairs = [("d0", "idle_d0", "stress_d0"), ("d100", "idle_d100", "stress_d100")]
    fig6, ax6 = plt.subplots(figsize=(7.0, 4.0))
    n_ft = len(fault_types)
    group_w = 0.35
    gap = 0.08
    base = np.arange(n_ft, dtype=float)
    for gi, (label, idle_c, stress_c) in enumerate(pairs):
        offsets = base + (gi - 0.5) * (group_w + gap)
        deltas: list[float] = []
        for ft in fault_types:
            mi, ms = mean_for(ft, idle_c), mean_for(ft, stress_c)
            deltas.append((ms - mi) if mi is not None and ms is not None else float("nan"))
        ax6.bar(
            offsets,
            deltas,
            width=group_w,
            label=f"stress − idle ({label})",
        )
    ax6.set_xticks(base)
    ax6.set_xticklabels(fault_types, rotation=12, ha="right")
    ax6.axhline(0, color="gray", linewidth=0.8)
    ax6.set_ylabel("Δ mean time (s)")
    ax6.set_title("CPU stress penalty: mean(stress) − mean(idle) at same delay knob")
    ax6.legend()
    ax6.grid(True, axis="y", linestyle=":", alpha=0.6)
    fig6.tight_layout()
    p6 = out_dir / "plot_stress_uplift.png"
    fig6.savefig(p6, dpi=150, bbox_inches="tight")
    plt.close(fig6)
    written.append(p6)

    # --- Figure 7: injected delay effect (idle_d100 − idle_d0) per fault ---
    fig7, ax7 = plt.subplots(figsize=(6.0, 3.8))
    deltas_idle: list[float] = []
    deltas_stress: list[float] = []
    for ft in fault_types:
        a, b = mean_for(ft, "idle_d0"), mean_for(ft, "idle_d100")
        deltas_idle.append((b - a) if a is not None and b is not None else float("nan"))
        c, d = mean_for(ft, "stress_d0"), mean_for(ft, "stress_d100")
        deltas_stress.append((d - c) if c is not None and d is not None else float("nan"))
    xb = np.arange(len(fault_types))
    ax7.bar(xb - 0.2, deltas_idle, width=0.38, label="idle: d100 − d0")
    ax7.bar(xb + 0.2, deltas_stress, width=0.38, label="stress: d100 − d0")
    ax7.set_xticks(xb)
    ax7.set_xticklabels(fault_types, rotation=12, ha="right")
    ax7.axhline(0.1, color="crimson", linestyle="--", linewidth=1, alpha=0.7, label="0.10 s (injected sleep, network only)")
    ax7.set_ylabel("Δ mean time (s)")
    ax7.set_title("Effect of +100 ms pre-recovery sleep (harness applies to network fault only)")
    ax7.legend(fontsize=8, loc="upper left")
    ax7.grid(True, axis="y", linestyle=":", alpha=0.6)
    fig7.tight_layout()
    p7 = out_dir / "plot_delay_knob_delta.png"
    fig7.savefig(p7, dpi=150, bbox_inches="tight")
    plt.close(fig7)
    written.append(p7)

    names = ", ".join(p.name for p in written)
    print(f"[plot_simulation] Wrote {len(written)} files -> {out_dir.resolve()}\n  {names}")
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=str, default="simulation_results.csv")
    ap.add_argument("--out-dir", type=str, default=".")
    args = ap.parse_args()
    generate_plots(args.input, args.out_dir)


if __name__ == "__main__":
    main()
