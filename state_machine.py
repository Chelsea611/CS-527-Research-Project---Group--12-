"""
CS 527 - Fault-Tolerant System: State Machine Core (Real Faults)
Group 12: David Zhao, Chelsea Sun
"""

from enum import Enum
import time
import threading

from faults.network_fault import NetworkFaultHandler
from faults.database_fault import DatabaseFaultHandler
from faults.server_fault import ServerCrashFaultHandler


class State(Enum):
    OPERATIONAL = "Operational"
    ERROR = "Error"
    RECOVERY = "Recovery"


class FaultType(Enum):
    NETWORK_TIMEOUT = "Network Timeout"
    DATABASE_FAILURE = "Database Failure"
    SERVER_CRASH = "Server Crash"


class FaultTolerantSystem:
    def __init__(self):
        self.state = State.OPERATIONAL
        self.log = []
        self.metrics = {
            "total_faults": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "recovery_times": [],
        }
        self._lock = threading.Lock()
        self._running = False
        self._current_fault_type = None
        self._current_handler = None
        self._fault_time = None

        # Pre-initialize all handlers so they start healthy
        self._handlers = {
            FaultType.NETWORK_TIMEOUT:  NetworkFaultHandler(),
            FaultType.DATABASE_FAILURE: DatabaseFaultHandler(),
            FaultType.SERVER_CRASH:     ServerCrashFaultHandler(),
        }

    def _record(self, message):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "state": self.state.value,
            "message": message,
        }
        self.log.append(entry)
        if len(self.log) > 100:
            self.log.pop(0)

    def trigger_fault(self, fault_type):
        with self._lock:
            if self.state != State.OPERATIONAL:
                return False
            handler = self._handlers[fault_type]
            handler.trigger_fault()
            self.state = State.ERROR
            self._current_fault_type = fault_type
            self._current_handler = handler
            self._fault_time = time.time()
            self.metrics["total_faults"] += 1
            self._record(f"Fault injected: {fault_type.value} — subsystem is now broken")
            return True

    def attempt_recovery(self):
        with self._lock:
            if self.state != State.ERROR:
                return False, "Not in error state"
            self.state = State.RECOVERY
            self._record(f"Recovery started for: {self._current_fault_type.value}")

        success, message = self._current_handler.try_recover()

        with self._lock:
            if success:
                elapsed = round(time.time() - self._fault_time, 2)
                self.metrics["successful_recoveries"] += 1
                self.metrics["recovery_times"].append(elapsed)
                self.state = State.OPERATIONAL
                self._record(f"Recovery successful in {elapsed}s — {message}")
                self._current_fault_type = None
                self._current_handler = None
            else:
                self.metrics["failed_recoveries"] += 1
                self.state = State.ERROR
                self._record(f"Recovery failed — {message}")

        return success, message

    def _auto_step(self):
        import random
        if self.state == State.OPERATIONAL:
            if random.random() < 0.25:
                fault = random.choice(list(FaultType))
                self.trigger_fault(fault)
        # Not elif: if we just left OPERATIONAL via trigger_fault above, we must
        # still recover in this same tick; elif would skip until after sleep(interval).
        if self.state == State.ERROR:
            time.sleep(0.5)
            self.attempt_recovery()

    def start_auto(self, interval=4.0):
        self._running = True
        def loop():
            while self._running:
                self._auto_step()
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
                if self.metrics["recovery_times"] else 0
            )
            return {
                "state": self.state.value,
                "current_fault": self._current_fault_type.value if self._current_fault_type else None,
                "log": list(reversed(self.log[-10:])),
                "metrics": {
                    "total_faults": total,
                    "successful_recoveries": success,
                    "failed_recoveries": self.metrics["failed_recoveries"],
                    "recovery_success_rate": round(success / total * 100, 1) if total > 0 else 100.0,
                    "avg_recovery_time_s": avg_time,
                },
                "subsystem_health": {
                    ft.value: self._handlers[ft].is_healthy()
                    for ft in FaultType
                },
            }
