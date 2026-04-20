"""
CS 527 - Fault-Tolerant System: Evaluation Simulation (Real Faults)
Group 12: David Zhao, Chelsea Sun

Extended harness: environment profiles (idle vs CPU stress), optional injected
network delay before recovery, cold vs warm trials on a long-lived system,
larger N, per-group statistics (mean, variance, P50/P95), CSV + summary CSV.

Usage:
  python run_simulation.py
  python run_simulation.py --trials 100 --output simulation_results.csv
  python run_simulation.py --quick
  python run_simulation.py --trials 50 --plots
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import statistics
import threading
import time
from dataclasses import dataclass
from typing import Any

from state_machine import FaultTolerantSystem, FaultType

# Default output files
RESULTS_FILE = "simulation_results.csv"
SUMMARY_FILE = "simulation_summary.csv"


@dataclass(frozen=True)
class EnvConfig:
    """One experimental environment (load × simulated pre-recovery delay)."""

    config_id: str
    load_profile: str  # "idle" | "stress"
    stress: bool
    net_delay_ms: int

    @staticmethod
    def default_grid() -> list["EnvConfig"]:
        return [
            EnvConfig("idle_d0", "idle", False, 0),
            EnvConfig("idle_d100", "idle", False, 100),
            EnvConfig("stress_d0", "stress", True, 0),
            EnvConfig("stress_d100", "stress", True, 100),
        ]


def _safe_print(msg: str) -> None:
    """Avoid UnicodeEncodeError on Windows consoles (e.g. GBK)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


@contextlib.contextmanager
def stress_load(num_threads: int = 8) -> Iterable[None]:
    """CPU-bound background load during the wrapped section (simulates high load)."""
    stop = threading.Event()

    def worker() -> None:
        while not stop.is_set():
            _ = sum(i * i for i in range(2500))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(num_threads)]
    for t in threads:
        t.start()
    try:
        yield
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=2.0)


def _percentile_nsorted(sorted_vals: list[float], p: float) -> float:
    """Linear interpolation percentile, p in [0,100]."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = rank - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def recovery_time_stats(times_s: list[float]) -> dict[str, float]:
    """Mean, sample variance, P50, P95 over successful recovery durations."""
    if not times_s:
        return {"n": 0, "mean_s": 0.0, "variance_s2": 0.0, "p50_s": 0.0, "p95_s": 0.0}
    xs = sorted(times_s)
    n = len(xs)
    mean = statistics.fmean(xs)
    var = statistics.variance(xs) if n >= 2 else 0.0
    return {
        "n": float(n),
        "mean_s": mean,
        "variance_s2": var,
        "p50_s": _percentile_nsorted(xs, 50.0),
        "p95_s": _percentile_nsorted(xs, 95.0),
    }


def run_trial(
    system: FaultTolerantSystem,
    fault_type: FaultType,
    *,
    stress: bool,
    net_delay_ms: int,
    trial_in_session: int,
) -> dict[str, Any] | None:
    """One fault → recovery cycle under environment knobs. trial_in_session is 1-based."""
    if system.state.value != "Operational":
        return None

    cold_start = trial_in_session == 1

    def inject_and_recover() -> tuple[bool, str]:
        system.trigger_fault(fault_type)
        # Simulated extra queuing / RTT before recovery starts (network experiments).
        if net_delay_ms > 0 and fault_type == FaultType.NETWORK_TIMEOUT:
            time.sleep(net_delay_ms / 1000.0)
        return system.attempt_recovery()

    t0 = time.perf_counter()
    if stress:
        with stress_load():
            success, message = inject_and_recover()
    else:
        success, message = inject_and_recover()
    elapsed = round(time.perf_counter() - t0, 6)

    return {
        "config_id": None,  # filled by caller
        "load_profile": None,
        "net_delay_ms": None,
        "fault_type": fault_type.value,
        "trial_in_session": trial_in_session,
        "cold_start": cold_start,
        "recovered": success,
        "time_s": elapsed,
        "message": message,
        "final_state": system.state.value,
    }


def run_block(
    env: EnvConfig,
    fault_type: FaultType,
    num_trials: int,
    trial_id_start: int,
) -> tuple[list[dict[str, Any]], int]:
    """Run num_trials on one long-lived system (warm path after first trial)."""
    system = FaultTolerantSystem()
    rows: list[dict[str, Any]] = []
    tid = trial_id_start
    for i in range(num_trials):
        row = run_trial(
            system,
            fault_type,
            stress=env.stress,
            net_delay_ms=env.net_delay_ms,
            trial_in_session=i + 1,
        )
        if row is None:
            _safe_print(f"  [SKIP] trial_id={tid} (system not operational)")
            tid += 1
            continue
        row["config_id"] = env.config_id
        row["load_profile"] = env.load_profile
        row["net_delay_ms"] = env.net_delay_ms
        row["trial_id"] = tid
        rows.append(row)
        tid += 1
        ok = "[OK]" if row["recovered"] else "[FAIL]"
        phase = "cold" if row["cold_start"] else "warm"
        _safe_print(
            f"  {ok} id={row['trial_id']} session={row['trial_in_session']} ({phase}) | "
            f"{row['time_s']}s | {str(row['message'])[:70]}"
        )
    return rows, tid


def _fixed_aggregate_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build summary rows: time stats for all / cold_only / warm_only + success_rate rows."""
    from collections import defaultdict

    time_buckets: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for r in rows:
        if not r["recovered"]:
            continue
        t = float(r["time_s"])
        cf = (r["config_id"], r["fault_type"])
        time_buckets[(*cf, "all")].append(t)
        if r["cold_start"]:
            time_buckets[(*cf, "cold_only")].append(t)
        else:
            time_buckets[(*cf, "warm_only")].append(t)

    out: list[dict[str, Any]] = []
    for (cid, ft, cohort) in sorted(time_buckets.keys()):
        times = time_buckets[(cid, ft, cohort)]
        st = recovery_time_stats(times)
        out.append(
            {
                "config_id": cid,
                "fault_type": ft,
                "cohort": cohort,
                "n": int(st["n"]),
                "mean_s": round(st["mean_s"], 6),
                "variance_s2": round(st["variance_s2"], 8),
                "p50_s": round(st["p50_s"], 6),
                "p95_s": round(st["p95_s"], 6),
            }
        )

    rate_key: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for r in rows:
        rate_key[(r["config_id"], r["fault_type"])].append(bool(r["recovered"]))

    for (cid, ft), flags in sorted(rate_key.items()):
        n = len(flags)
        succ = sum(1 for x in flags if x)
        out.append(
            {
                "config_id": cid,
                "fault_type": ft,
                "cohort": "success_rate_pct",
                "n": n,
                "mean_s": round(100.0 * succ / n, 2) if n else 0.0,
                "variance_s2": 0.0,
                "p50_s": 0.0,
                "p95_s": 0.0,
            }
        )
    return out


def print_console_summary(rows: list[dict[str, Any]]) -> None:
    """Human-readable tables for stdout."""
    from collections import defaultdict

    _safe_print("\n" + "=" * 72)
    _safe_print("DETAIL: recovery rate by config × fault type")
    _safe_print("-" * 72)
    grid: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for r in rows:
        grid[(r["config_id"], r["fault_type"])].append(bool(r["recovered"]))
    for (cid, ft) in sorted(grid.keys()):
        flags = grid[(cid, ft)]
        n = len(flags)
        succ = sum(1 for x in flags if x)
        _safe_print(f"  {cid:<14} {ft:<22}  success {succ}/{n} ({100*succ/n:.1f}%)")

    _safe_print("\n" + "=" * 72)
    _safe_print("DETAIL: time stats (successful trials), by cohort")
    _safe_print("-" * 72)
    sums = _fixed_aggregate_summaries(rows)
    for s in sums:
        if s["cohort"] == "success_rate_pct":
            continue
        _safe_print(
            f"  {s['config_id']:<14} {s['fault_type']:<20} {s['cohort']:<10} n={s['n']:<4} "
            f"mean={s['mean_s']}s  var={s['variance_s2']}  P50={s['p50_s']}s  P95={s['p95_s']}s"
        )

    _safe_print("\n" + "=" * 72)
    _safe_print("SUCCESS RATE (cohort = success_rate_pct; mean_s column = pct)")
    for s in sums:
        if s["cohort"] == "success_rate_pct":
            _safe_print(f"  {s['config_id']:<14} {s['fault_type']:<22}  {s['mean_s']}% over n={s['n']}")
    _safe_print("=" * 72)


def run_evaluation(
    *,
    trials: int,
    configs: list[EnvConfig],
    output_csv: str,
    summary_csv: str,
) -> list[dict[str, Any]]:
    _safe_print("=" * 72)
    _safe_print("CS 527 · Fault-Tolerant System Evaluation (Real Faults, extended)")
    _safe_print("Group 12: David Zhao, Chelsea Sun")
    _safe_print(f"Trials per (config × fault type): {trials}")
    _safe_print(f"Environment configs: {len(configs)}")
    _safe_print("=" * 72)

    all_rows: list[dict[str, Any]] = []
    trial_id = 1

    for env in configs:
        _safe_print(f"\n### CONFIG {env.config_id}  load={env.load_profile}  net_delay_ms={env.net_delay_ms}")
        for fault_type in FaultType:
            _safe_print(f"\n[{fault_type.value}]")
            block_rows, trial_id = run_block(env, fault_type, trials, trial_id)
            all_rows.extend(block_rows)

    if all_rows:
        fieldnames = list(all_rows[0].keys())
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(all_rows)
        _safe_print(f"\n[OK] Wrote {len(all_rows)} rows -> {output_csv}")

        summaries = _fixed_aggregate_summaries(all_rows)
        if summaries:
            with open(summary_csv, "w", newline="", encoding="utf-8") as f:
                sw = csv.DictWriter(f, fieldnames=list(summaries[0].keys()))
                sw.writeheader()
                sw.writerows(summaries)
            _safe_print(f"[OK] Wrote summary -> {summary_csv}")

        print_console_summary(all_rows)
    return all_rows


def maybe_run_plots(csv_path: str) -> None:
    import subprocess
    import sys
    from pathlib import Path

    plot_script = Path(__file__).resolve().parent / "plot_simulation.py"
    if not plot_script.is_file():
        _safe_print("[WARN] plot_simulation.py not found; skip --plots")
        return
    try:
        subprocess.run(
            [sys.executable, str(plot_script), "--input", csv_path],
            check=False,
            cwd=str(plot_script.parent),
        )
    except Exception as e:
        _safe_print(f"[WARN] Plotting failed: {e}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fault/recovery evaluation harness.")
    p.add_argument("--trials", type=int, default=50, help="Trials per (env config × fault type).")
    p.add_argument("--output", type=str, default=RESULTS_FILE, help="Main CSV path.")
    p.add_argument("--summary", type=str, default=SUMMARY_FILE, help="Summary CSV path.")
    p.add_argument(
        "--configs",
        type=str,
        default="grid",
        choices=["grid", "idle_only"],
        help="grid = 4 env combos; idle_only = single idle, 0ms delay (fast smoke).",
    )
    p.add_argument("--quick", action="store_true", help="10 trials + idle_only (smoke test).")
    p.add_argument("--plots", action="store_true", help="Run plot_simulation after CSV is written.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    trials = 10 if args.quick else max(1, args.trials)
    if args.configs == "idle_only" or args.quick:
        configs = [EnvConfig("idle_d0", "idle", False, 0)]
    else:
        configs = EnvConfig.default_grid()

    run_evaluation(trials=trials, configs=configs, output_csv=args.output, summary_csv=args.summary)
    if args.plots:
        maybe_run_plots(args.output)


if __name__ == "__main__":
    main()
