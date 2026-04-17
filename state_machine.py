"""
CS 527 - Fault-Tolerant System: State Machine Core
Group 12: David Zhao, Chelsea Sun
"""

from enum import Enum
import time
import random
import threading


class State(Enum):
    OPERATIONAL = "Operational"
    ERROR = "Error"
    RECOVERY = "Recovery"


class FaultType(Enum):
    NETWORK_TIMEOUT = "Network Timeout"
    DATABASE_FAILURE = "Database Failure"
    SERVER_CRASH = "Server Crash"


class FaultTolerantSystem:
    def __init__(self, fault_probability=0.25, recovery_success_rate=0.85):
        self.state = State.OPERATIONAL
        self.fault_probability = fault_probability
        self.recovery_success_rate = recovery_success_rate
        self.log = []
        self.metrics = {
            "total_faults": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "recovery_times": [],
        }
        self._lock = threading.Lock()
        self._running = False
        self._current_fault = None
        self._fault_time = None

    def _record(self, message):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "state": self.state.value,
            "message": message,
        }
        self.log.append(entry)
        if len(self.log) > 100:
            self.log.pop(0)

    def transition(self, event, fault_type=None):
        with self._lock:
            prev = self.state
            if self.state == State.OPERATIONAL and event == "fault_detected":
                self.state = State.ERROR
                self._current_fault = fault_type or random.choice(list(FaultType)).value
                self._fault_time = time.time()
                self.metrics["total_faults"] += 1
                self._record(f"Fault detected: {self._current_fault}")

            elif self.state == State.ERROR and event == "recovery_triggered":
                self.state = State.RECOVERY
                self._record(f"Recovery initiated for: {self._current_fault}")

            elif self.state == State.RECOVERY and event == "recovery_success":
                elapsed = round(time.time() - self._fault_time, 2) if self._fault_time else 0
                self.metrics["successful_recoveries"] += 1
                self.metrics["recovery_times"].append(elapsed)
                self.state = State.OPERATIONAL
                self._record(f"Recovery successful in {elapsed}s")
                self._current_fault = None

            elif self.state == State.RECOVERY and event == "recovery_failed":
                self.state = State.ERROR
                self.metrics["failed_recoveries"] += 1
                self._record("Recovery failed, re-entering error state")

            return prev != self.state  # returns True if state changed

    def inject_fault(self, fault_type=None):
        """Manually inject a fault (used by frontend/tests)."""
        if self.state == State.OPERATIONAL:
            ft = fault_type or random.choice(list(FaultType))
            self.transition("fault_detected", ft.value if isinstance(ft, FaultType) else ft)
            return True
        return False

    def step(self):
        """Advance the system by one automatic step."""
        if self.state == State.OPERATIONAL:
            if random.random() < self.fault_probability:
                self.transition("fault_detected")
        elif self.state == State.ERROR:
            time.sleep(0.5)
            self.transition("recovery_triggered")
        elif self.state == State.RECOVERY:
            time.sleep(1.0)
            if random.random() < self.recovery_success_rate:
                self.transition("recovery_success")
            else:
                self.transition("recovery_failed")

    def start_auto(self, interval=2.0):
        """Run the system automatically in a background thread."""
        self._running = True

        def loop():
            while self._running:
                self.step()
                time.sleep(interval)

        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def stop_auto(self):
        self._running = False

    def get_status(self):
        with self._lock:
            total = self.metrics["total_faults"]
            success = self.metrics["successful_recoveries"]
            avg_time = (
                round(sum(self.metrics["recovery_times"]) / len(self.metrics["recovery_times"]), 2)
                if self.metrics["recovery_times"]
                else 0
            )
            return {
                "state": self.state.value,
                "current_fault": self._current_fault,
                "log": list(reversed(self.log[-10:])),
                "metrics": {
                    "total_faults": total,
                    "successful_recoveries": success,
                    "failed_recoveries": self.metrics["failed_recoveries"],
                    "recovery_success_rate": round(success / total * 100, 1) if total > 0 else 100.0,
                    "avg_recovery_time_s": avg_time,
                },
            }
