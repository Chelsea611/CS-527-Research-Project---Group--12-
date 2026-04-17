"""
CS 527 - Fault-Tolerant System: Automated Test Suite
Group 12: David Zhao, Chelsea Sun

Run with: pytest tests/test_state_machine.py -v
"""

import pytest
from state_machine import FaultTolerantSystem, State, FaultType


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def sys():
    return FaultTolerantSystem()


@pytest.fixture
def sys_in_error():
    s = FaultTolerantSystem()
    s.transition("fault_detected")
    return s


@pytest.fixture
def sys_in_recovery():
    s = FaultTolerantSystem()
    s.transition("fault_detected")
    s.transition("recovery_triggered")
    return s


# ──────────────────────────────────────────────
# TC-1  Initial State
# ──────────────────────────────────────────────

class TestInitialState:
    def test_starts_operational(self, sys):
        assert sys.state == State.OPERATIONAL

    def test_metrics_zeroed(self, sys):
        status = sys.get_status()
        assert status["metrics"]["total_faults"] == 0
        assert status["metrics"]["successful_recoveries"] == 0

    def test_no_current_fault(self, sys):
        assert sys.get_status()["current_fault"] is None


# ──────────────────────────────────────────────
# TC-2  Fault Detection (OPERATIONAL → ERROR)
# ──────────────────────────────────────────────

class TestFaultDetection:
    def test_operational_to_error(self, sys):
        sys.transition("fault_detected")
        assert sys.state == State.ERROR

    def test_fault_increments_counter(self, sys):
        sys.transition("fault_detected")
        assert sys.get_status()["metrics"]["total_faults"] == 1

    def test_current_fault_recorded(self, sys):
        sys.transition("fault_detected", "Network Timeout")
        assert sys.get_status()["current_fault"] == "Network Timeout"

    def test_multiple_faults_counted(self, sys):
        for _ in range(3):
            sys.state = State.OPERATIONAL
            sys.transition("fault_detected")
        assert sys.get_status()["metrics"]["total_faults"] == 3

    def test_no_fault_from_non_operational(self, sys_in_error):
        sys_in_error.transition("fault_detected")   # should be ignored
        assert sys_in_error.state == State.ERROR

    @pytest.mark.parametrize("fault", list(FaultType))
    def test_all_fault_types_accepted(self, sys, fault):
        result = sys.inject_fault(fault)
        assert result is True
        assert sys.state == State.ERROR


# ──────────────────────────────────────────────
# TC-3  Recovery Initiation (ERROR → RECOVERY)
# ──────────────────────────────────────────────

class TestRecoveryInitiation:
    def test_error_to_recovery(self, sys_in_error):
        sys_in_error.transition("recovery_triggered")
        assert sys_in_error.state == State.RECOVERY

    def test_recovery_not_from_operational(self, sys):
        sys.transition("recovery_triggered")
        assert sys.state == State.OPERATIONAL   # unchanged


# ──────────────────────────────────────────────
# TC-4  Recovery Success (RECOVERY → OPERATIONAL)
# ──────────────────────────────────────────────

class TestRecoverySuccess:
    def test_recovery_success_returns_operational(self, sys_in_recovery):
        sys_in_recovery.transition("recovery_success")
        assert sys_in_recovery.state == State.OPERATIONAL

    def test_success_increments_counter(self, sys_in_recovery):
        sys_in_recovery.transition("recovery_success")
        assert sys_in_recovery.get_status()["metrics"]["successful_recoveries"] == 1

    def test_fault_cleared_after_success(self, sys_in_recovery):
        sys_in_recovery.transition("recovery_success")
        assert sys_in_recovery.get_status()["current_fault"] is None

    def test_recovery_time_recorded(self, sys_in_recovery):
        sys_in_recovery.transition("recovery_success")
        assert len(sys_in_recovery.metrics["recovery_times"]) == 1
        assert sys_in_recovery.metrics["recovery_times"][0] >= 0


# ──────────────────────────────────────────────
# TC-5  Recovery Failure (RECOVERY → ERROR)
# ──────────────────────────────────────────────

class TestRecoveryFailure:
    def test_recovery_failure_returns_error(self, sys_in_recovery):
        sys_in_recovery.transition("recovery_failed")
        assert sys_in_recovery.state == State.ERROR

    def test_failed_recovery_increments_counter(self, sys_in_recovery):
        sys_in_recovery.transition("recovery_failed")
        assert sys_in_recovery.get_status()["metrics"]["failed_recoveries"] == 1

    def test_retry_after_failure(self, sys_in_recovery):
        sys_in_recovery.transition("recovery_failed")
        sys_in_recovery.transition("recovery_triggered")
        sys_in_recovery.transition("recovery_success")
        assert sys_in_recovery.state == State.OPERATIONAL


# ──────────────────────────────────────────────
# TC-6  Full Lifecycle Tests
# ──────────────────────────────────────────────

class TestFullLifecycle:
    def test_full_happy_path(self, sys):
        assert sys.state == State.OPERATIONAL
        sys.transition("fault_detected")
        assert sys.state == State.ERROR
        sys.transition("recovery_triggered")
        assert sys.state == State.RECOVERY
        sys.transition("recovery_success")
        assert sys.state == State.OPERATIONAL

    def test_full_failure_then_retry(self, sys):
        sys.transition("fault_detected")
        sys.transition("recovery_triggered")
        sys.transition("recovery_failed")
        sys.transition("recovery_triggered")
        sys.transition("recovery_success")
        assert sys.state == State.OPERATIONAL

    def test_consecutive_faults(self, sys):
        for i in range(5):
            sys.state = State.OPERATIONAL
            sys.transition("fault_detected")
            sys.transition("recovery_triggered")
            sys.transition("recovery_success")
        assert sys.get_status()["metrics"]["successful_recoveries"] == 5


# ──────────────────────────────────────────────
# TC-7  Metrics Accuracy
# ──────────────────────────────────────────────

class TestMetrics:
    def test_recovery_rate_100_when_all_succeed(self, sys):
        for _ in range(5):
            sys.state = State.OPERATIONAL
            sys.transition("fault_detected")
            sys.transition("recovery_triggered")
            sys.transition("recovery_success")
        rate = sys.get_status()["metrics"]["recovery_success_rate"]
        assert rate == 100.0

    def test_recovery_rate_0_when_all_fail(self, sys):
        for _ in range(3):
            sys.state = State.OPERATIONAL
            sys.transition("fault_detected")
            sys.transition("recovery_triggered")
            sys.transition("recovery_failed")
        rate = sys.get_status()["metrics"]["recovery_success_rate"]
        assert rate == 0.0

    def test_avg_recovery_time_positive(self, sys):
        import time
        sys.transition("fault_detected")
        time.sleep(0.05)
        sys.transition("recovery_triggered")
        sys.transition("recovery_success")
        avg = sys.get_status()["metrics"]["avg_recovery_time_s"]
        assert avg >= 0.05

    def test_log_records_transitions(self, sys):
        sys.transition("fault_detected")
        sys.transition("recovery_triggered")
        sys.transition("recovery_success")
        log = sys.get_status()["log"]
        assert len(log) == 3


# ──────────────────────────────────────────────
# TC-8  inject_fault() convenience method
# ──────────────────────────────────────────────

class TestInjectFault:
    def test_inject_from_operational_succeeds(self, sys):
        result = sys.inject_fault()
        assert result is True
        assert sys.state == State.ERROR

    def test_inject_from_error_fails(self, sys_in_error):
        result = sys_in_error.inject_fault()
        assert result is False
        assert sys_in_error.state == State.ERROR

    def test_inject_from_recovery_fails(self, sys_in_recovery):
        result = sys_in_recovery.inject_fault()
        assert result is False
