"""
CS 527 - Fault-Tolerant System: State Machine Core (Real Faults)
Group 12: David Zhao, Chelsea Sun
"""

from contextlib import contextmanager
from enum import Enum
import threading
import time

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


@contextmanager
def _stress_load(num_threads: int = 8):
    """CPU-bound background threads (aligns with run_simulation stress profile)."""
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

        # Dashboard / parity with batch harness: optional recovery-time stress & net delay
        self.web_stress_recovery = False
        self.web_net_delay_ms = 0
        self.web_recovery_cycles_completed = 0

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

    def set_recovery_env(
        self,
        *,
        stress_during_recovery: bool | None = None,
        network_recovery_delay_ms: int | None = None,
    ):
        """Update web dashboard knobs (thread-safe). None = leave unchanged."""
        with self._lock:
            if stress_during_recovery is not None:
                self.web_stress_recovery = bool(stress_during_recovery)
            if network_recovery_delay_ms is not None:
                self.web_net_delay_ms = max(0, min(int(network_recovery_delay_ms), 5000))

    def attempt_recovery(self):
        with self._lock:
            if self.state != State.ERROR:
                return False, "Not in error state"
            self.state = State.RECOVERY
            self._record(f"Recovery started for: {self._current_fault_type.value}")
            handler = self._current_handler
            ftype = self._current_fault_type
            use_stress = self.web_stress_recovery
            net_delay_ms = self.web_net_delay_ms

        if ftype == FaultType.NETWORK_TIMEOUT and net_delay_ms > 0:
            time.sleep(net_delay_ms / 1000.0)

        if use_stress:
            with _stress_load():
                success, message = handler.try_recover()
        else:
            success, message = handler.try_recover()

        with self._lock:
            if success:
                elapsed = round(time.time() - self._fault_time, 2)
                self.metrics["successful_recoveries"] += 1
                self.metrics["recovery_times"].append(elapsed)
                self.web_recovery_cycles_completed += 1
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
        """Background loop: no random fault injection—only pull ERROR → recovery."""
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
                "recovery_env": {
                    "stress_during_recovery": self.web_stress_recovery,
                    "network_recovery_delay_ms": self.web_net_delay_ms,
                },
                "recovery_cycles_completed": self.web_recovery_cycles_completed,
                "recovery_watch_active": self._running,
            }
