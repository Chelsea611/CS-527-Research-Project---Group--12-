"""
CS 527 - Fault-Tolerant System: Evaluation Simulation (Real Faults)
Group 12: David Zhao, Chelsea Sun

Runs 60 real fault-recovery cycles across all 3 fault types.
Each trial actually breaks a subsystem and verifies real recovery.
Usage: python run_simulation.py
"""

import csv
import time
from state_machine import FaultTolerantSystem, FaultType

NUM_TRIALS_PER_FAULT = 20   # 20 trials × 3 fault types = 60 total
RESULTS_FILE = "simulation_results.csv"


def run_trial(system, trial_id, fault_type):
    """One full fault → recovery cycle. Returns result dict."""
    # Ensure system is operational before injecting
    if system.state.value != "Operational":
        return None

    start = time.time()
    system.trigger_fault(fault_type)
    success, message = system.attempt_recovery()
    elapsed = round(time.time() - start, 4)

    return {
        "trial_id": trial_id,
        "fault_type": fault_type.value,
        "recovered": success,
        "time_s": elapsed,
        "message": message,
        "final_state": system.state.value,
    }


def run_evaluation():
    print("=" * 60)
    print("CS 527 · Fault-Tolerant System Evaluation (Real Faults)")
    print("Group 12: David Zhao, Chelsea Sun")
    print("=" * 60)

    all_rows = []
    trial_id = 1

    for fault_type in FaultType:
        system = FaultTolerantSystem()
        print(f"\n[{fault_type.value}] Running {NUM_TRIALS_PER_FAULT} trials...")

        successes = 0
        times = []

        for i in range(NUM_TRIALS_PER_FAULT):
            row = run_trial(system, trial_id, fault_type)
            if row is None:
                print(f"  ⚠ Trial {trial_id} skipped (system not operational)")
                continue

            all_rows.append(row)
            trial_id += 1

            status = "✓" if row["recovered"] else "✗"
            print(f"  {status} Trial {i+1:02d} | {row['time_s']}s | {row['message']}")

            if row["recovered"]:
                successes += 1
                times.append(row["time_s"])

        rate = round(successes / NUM_TRIALS_PER_FAULT * 100, 1)
        avg  = round(sum(times) / len(times), 4) if times else 0
        print(f"\n  → Recovery rate: {rate}% | Avg time: {avg}s | {successes}/{NUM_TRIALS_PER_FAULT} succeeded")

    # Write CSV
    if all_rows:
        with open(RESULTS_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\n[✓] Results saved to {RESULTS_FILE}")

    print_summary(all_rows)


def print_summary(rows):
    from collections import defaultdict
    by_fault = defaultdict(list)
    for r in rows:
        by_fault[r["fault_type"]].append(r)

    print("\n" + "=" * 60)
    print("SUMMARY TABLE")
    print(f"{'Fault Type':<22} | {'Recovery Rate':>13} | {'Avg Time (s)':>12} | {'Trials':>6}")
    print("-" * 60)
    for fault, trials in by_fault.items():
        successes = sum(1 for t in trials if t["recovered"])
        times = [t["time_s"] for t in trials if t["recovered"]]
        rate  = round(successes / len(trials) * 100, 1)
        avg_t = round(sum(times) / len(times), 4) if times else 0
        print(f"{fault:<22} | {rate:>12}% | {avg_t:>12} | {len(trials):>6}")
    print("=" * 60)


if __name__ == "__main__":
    run_evaluation()
