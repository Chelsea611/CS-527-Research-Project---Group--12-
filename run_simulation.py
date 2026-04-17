"""
CS 527 - Fault-Tolerant System: Evaluation Simulation
Group 12: David Zhao, Chelsea Sun

Runs 100 fault scenarios and outputs results.csv for the report.
Usage: python run_simulation.py
"""

import csv
import time
import random
from state_machine import FaultTolerantSystem, FaultType

NUM_TRIALS = 100
RECOVERY_RATES = [0.7, 0.80, 0.85, 0.90, 0.95]   # test multiple recovery rates
RESULTS_FILE = "simulation_results.csv"


def run_single_trial(system, trial_id, fault_type):
    """Simulate one fault-to-recovery cycle. Returns a result dict."""
    start = time.time()

    system.state_override = None   # reset via public method
    system.state.__class__  # just touch it

    # inject fault
    from state_machine import State
    system.state = State.OPERATIONAL
    system.transition("fault_detected", fault_type.value)
    system.transition("recovery_triggered")

    attempts = 0
    max_attempts = 5
    recovered = False

    while attempts < max_attempts:
        attempts += 1
        time.sleep(0.01)   # simulate processing time
        if random.random() < system.recovery_success_rate:
            system.transition("recovery_success")
            recovered = True
            break
        else:
            system.transition("recovery_failed")
            system.transition("recovery_triggered")

    elapsed = round(time.time() - start, 4)

    return {
        "trial_id": trial_id,
        "fault_type": fault_type.value,
        "recovered": recovered,
        "attempts": attempts,
        "time_s": elapsed,
        "final_state": system.state.value,
    }


def run_evaluation():
    print("=" * 60)
    print("CS 527 · Fault-Tolerant System Evaluation")
    print("Group 12: David Zhao, Chelsea Sun")
    print("=" * 60)

    all_rows = []

    for rate in RECOVERY_RATES:
        system = FaultTolerantSystem(recovery_success_rate=rate)
        print(f"\n[Recovery Rate: {int(rate*100)}%] Running {NUM_TRIALS} trials...")

        successes = 0
        times = []

        for i in range(NUM_TRIALS):
            fault = random.choice(list(FaultType))
            row = run_single_trial(system, trial_id=i + 1, fault_type=fault)
            row["configured_rate"] = rate
            all_rows.append(row)
            if row["recovered"]:
                successes += 1
                times.append(row["time_s"])

        actual_rate = round(successes / NUM_TRIALS * 100, 1)
        avg_time = round(sum(times) / len(times), 4) if times else 0
        print(f"  ✓ Actual recovery rate : {actual_rate}%")
        print(f"  ✓ Avg recovery time    : {avg_time}s")
        print(f"  ✓ Successful trials    : {successes}/{NUM_TRIALS}")

    # Write CSV
    with open(RESULTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n[✓] Results saved to {RESULTS_FILE}")
    print_summary(all_rows)


def print_summary(rows):
    from collections import defaultdict
    by_rate = defaultdict(list)
    for r in rows:
        by_rate[r["configured_rate"]].append(r)

    print("\n" + "=" * 60)
    print("SUMMARY TABLE")
    print(f"{'Config Rate':>12} | {'Actual Rate':>11} | {'Avg Time (s)':>12} | {'Trials':>6}")
    print("-" * 60)
    for rate, trials in sorted(by_rate.items()):
        successes = sum(1 for t in trials if t["recovered"])
        times = [t["time_s"] for t in trials if t["recovered"]]
        actual = round(successes / len(trials) * 100, 1)
        avg_t = round(sum(times) / len(times), 4) if times else 0
        print(f"{int(rate*100):>11}% | {actual:>10}% | {avg_t:>12} | {len(trials):>6}")
    print("=" * 60)


if __name__ == "__main__":
    run_evaluation()
