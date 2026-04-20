"""
CS 527 - Real Fault Tests
Group 12: David Zhao, Chelsea Sun

These tests verify REAL fault injection and REAL recovery.
No random numbers — each test actually breaks and fixes a subsystem.
"""

import pytest
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_machine import FaultTolerantSystem, FaultType, State
from faults.network_fault import NetworkFaultHandler
from faults.database_fault import DatabaseFaultHandler
from faults.server_fault import ServerCrashFaultHandler


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def sys_clean():
    return FaultTolerantSystem()


# ── TC-1  Initial State ───────────────────────────────────────

class TestInitialState:
    def test_starts_operational(self, sys_clean):
        assert sys_clean.state == State.OPERATIONAL

    def test_metrics_zeroed(self, sys_clean):
        m = sys_clean.get_status()["metrics"]
        assert m["total_faults"] == 0
        assert m["successful_recoveries"] == 0

    def test_all_subsystems_healthy_at_start(self, sys_clean):
        health = sys_clean.get_status()["subsystem_health"]
        assert all(health.values()), f"Unhealthy at start: {health}"


# ── TC-2  Network Fault ───────────────────────────────────────

class TestNetworkFault:
    def test_server_starts_healthy(self):
        h = NetworkFaultHandler()
        assert h.is_healthy()

    def test_fault_kills_server(self):
        h = NetworkFaultHandler()
        h.trigger_fault()
        assert not h.is_healthy()

    def test_recovery_restarts_server(self):
        h = NetworkFaultHandler()
        h.trigger_fault()
        assert not h.is_healthy()
        success, msg = h.try_recover()
        assert success, f"Network recovery failed: {msg}"
        assert h.is_healthy()

    def test_recovery_message_contains_verified(self):
        h = NetworkFaultHandler()
        h.trigger_fault()
        success, msg = h.try_recover()
        assert success
        assert "verified" in msg.lower()

    def test_full_cycle_via_state_machine(self, sys_clean):
        sys_clean.trigger_fault(FaultType.NETWORK_TIMEOUT)
        assert sys_clean.state == State.ERROR
        success, _ = sys_clean.attempt_recovery()
        assert success
        assert sys_clean.state == State.OPERATIONAL


# ── TC-3  Database Fault ──────────────────────────────────────

class TestDatabaseFault:
    def test_db_starts_healthy(self):
        h = DatabaseFaultHandler()
        assert h.is_healthy()

    def test_fault_deletes_db_file(self):
        import os
        h = DatabaseFaultHandler()
        h.trigger_fault()
        assert not os.path.exists(h.db_path)
        assert not h.is_healthy()

    def test_recovery_recreates_db(self):
        import os
        h = DatabaseFaultHandler()
        h.trigger_fault()
        success, msg = h.try_recover()
        assert success, f"DB recovery failed: {msg}"
        assert os.path.exists(h.db_path)
        assert h.is_healthy()

    def test_recovery_verifies_write(self):
        h = DatabaseFaultHandler()
        h.trigger_fault()
        success, msg = h.try_recover()
        assert "write test passed" in msg

    def test_full_cycle_via_state_machine(self, sys_clean):
        sys_clean.trigger_fault(FaultType.DATABASE_FAILURE)
        assert sys_clean.state == State.ERROR
        success, _ = sys_clean.attempt_recovery()
        assert success
        assert sys_clean.state == State.OPERATIONAL


# ── TC-4  Server Crash Fault ──────────────────────────────────

class TestServerCrashFault:
    def test_worker_starts_alive(self):
        h = ServerCrashFaultHandler()
        assert h.is_healthy()

    def test_fault_kills_worker_thread(self):
        h = ServerCrashFaultHandler()
        h.trigger_fault()
        time.sleep(0.3)
        assert not h.is_healthy()

    def test_recovery_restarts_worker(self):
        h = ServerCrashFaultHandler()
        h.trigger_fault()
        time.sleep(0.3)
        success, msg = h.try_recover()
        assert success, f"Worker recovery failed: {msg}"
        assert h.is_healthy()

    def test_recovery_verifies_task_processing(self):
        h = ServerCrashFaultHandler()
        h.trigger_fault()
        time.sleep(0.3)
        success, msg = h.try_recover()
        assert "21" in msg or "42" in msg  # 21*2=42 is the verification task

    def test_full_cycle_via_state_machine(self, sys_clean):
        sys_clean.trigger_fault(FaultType.SERVER_CRASH)
        assert sys_clean.state == State.ERROR
        success, _ = sys_clean.attempt_recovery()
        assert success
        assert sys_clean.state == State.OPERATIONAL


# ── TC-5  State Machine Logic ─────────────────────────────────

class TestStateMachineLogic:
    def test_fault_rejected_when_not_operational(self, sys_clean):
        sys_clean.trigger_fault(FaultType.NETWORK_TIMEOUT)
        result = sys_clean.trigger_fault(FaultType.DATABASE_FAILURE)
        assert result is False   # already in Error, second fault rejected

    def test_recovery_rejected_when_operational(self, sys_clean):
        success, msg = sys_clean.attempt_recovery()
        assert success is False
        assert sys_clean.state == State.OPERATIONAL

    def test_fault_increments_counter(self, sys_clean):
        sys_clean.trigger_fault(FaultType.SERVER_CRASH)
        assert sys_clean.get_status()["metrics"]["total_faults"] == 1

    def test_successful_recovery_increments_counter(self, sys_clean):
        sys_clean.trigger_fault(FaultType.DATABASE_FAILURE)
        sys_clean.attempt_recovery()
        assert sys_clean.get_status()["metrics"]["successful_recoveries"] == 1

    def test_recovery_time_is_positive(self, sys_clean):
        sys_clean.trigger_fault(FaultType.NETWORK_TIMEOUT)
        sys_clean.attempt_recovery()
        avg = sys_clean.get_status()["metrics"]["avg_recovery_time_s"]
        assert avg > 0

    def test_log_records_all_transitions(self, sys_clean):
        sys_clean.trigger_fault(FaultType.SERVER_CRASH)
        sys_clean.attempt_recovery()
        log = sys_clean.get_status()["log"]
        assert len(log) >= 3   # fault injected, recovery started, recovery successful

    def test_consecutive_different_faults(self, sys_clean):
        for fault in FaultType:
            sys_clean.trigger_fault(fault)
            success, _ = sys_clean.attempt_recovery()
            assert success, f"Recovery failed for {fault.value}"
            assert sys_clean.state == State.OPERATIONAL

    def test_recovery_rate_100_after_all_succeed(self, sys_clean):
        for fault in FaultType:
            sys_clean.trigger_fault(fault)
            sys_clean.attempt_recovery()
        rate = sys_clean.get_status()["metrics"]["recovery_success_rate"]
        assert rate == 100.0
