"""
CS 527 - Fault-Tolerant System: Automated Test Suite
Group 12: David Zhao, Chelsea Sun

Run with: pytest tests/test_state_machine.py -v
"""

import time
import pytest
from unittest.mock import patch
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
    s.trigger_fault(FaultType.NETWORK_TIMEOUT)
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
        sys.trigger_fault(FaultType.NETWORK_TIMEOUT)
        assert sys.state == State.ERROR

    def test_fault_increments_counter(self, sys):
        sys.trigger_fault(FaultType.NETWORK_TIMEOUT)
        assert sys.get_status()["metrics"]["total_faults"] == 1

    def test_current_fault_recorded(self, sys):
        sys.trigger_fault(FaultType.NETWORK_TIMEOUT)
        assert sys.get_status()["current_fault"] == "Network Timeout"

    def test_multiple_faults_counted(self, sys):
        for _ in range(3):
            sys.trigger_fault(FaultType.NETWORK_TIMEOUT)
            sys.attempt_recovery()  # reset back to OPERATIONAL
        assert sys.get_status()["metrics"]["total_faults"] == 3

    def test_no_fault_from_non_operational(self, sys_in_error):
        result = sys_in_error.trigger_fault(FaultType.DATABASE_FAILURE)
        assert result is False
        assert sys_in_error.state == State.ERROR

    @pytest.mark.parametrize("fault", list(FaultType))
    def test_all_fault_types_accepted(self, sys, fault):
        result = sys.trigger_fault(fault)
        assert result is True
        assert sys.state == State.ERROR


# ──────────────────────────────────────────────
# TC-3  Recovery Initiation (ERROR → OPERATIONAL)
# ──────────────────────────────────────────────

class TestRecoveryInitiation:
    def test_recovery_from_error_succeeds(self, sys_in_error):
        success, _ = sys_in_error.attempt_recovery()
        assert success is True
        assert sys_in_error.state == State.OPERATIONAL

    def test_recovery_not_from_operational(self, sys):
        success, msg = sys.attempt_recovery()
        assert success is False
        assert sys.state == State.OPERATIONAL


# ──────────────────────────────────────────────
# TC-4  Recovery Success (→ OPERATIONAL)
# ──────────────────────────────────────────────

class TestRecoverySuccess:
    def test_recovery_returns_operational(self, sys_in_error):
        sys_in_error.attempt_recovery()
        assert sys_in_error.state == State.OPERATIONAL

    def test_success_increments_counter(self, sys_in_error):
        sys_in_error.attempt_recovery()
        assert sys_in_error.get_status()["metrics"]["successful_recoveries"] == 1

    def test_fault_cleared_after_success(self, sys_in_error):
        sys_in_error.attempt_recovery()
        assert sys_in_error.get_status()["current_fault"] is None

    def test_recovery_time_recorded(self, sys_in_error):
        sys_in_error.attempt_recovery()
        assert len(sys_in_error.metrics["recovery_times"]) == 1
        assert sys_in_error.metrics["recovery_times"][0] >= 0


# ──────────────────────────────────────────────
# TC-5  Recovery Failure (→ ERROR via mock)
# ──────────────────────────────────────────────

class TestRecoveryFailure:
    def test_recovery_failure_returns_error(self, sys_in_error):
        handler = sys_in_error._current_handler
        with patch.object(handler, "try_recover", return_value=(False, "mocked failure")):
            success, _ = sys_in_error.attempt_recovery()
        assert success is False
        assert sys_in_error.state == State.ERROR

    def test_failed_recovery_increments_counter(self, sys_in_error):
        handler = sys_in_error._current_handler
        with patch.object(handler, "try_recover", return_value=(False, "mocked failure")):
            sys_in_error.attempt_recovery()
        assert sys_in_error.get_status()["metrics"]["failed_recoveries"] == 1

    def test_retry_after_failure(self, sys_in_error):
        handler = sys_in_error._current_handler
        with patch.object(handler, "try_recover", return_value=(False, "mocked failure")):
            sys_in_error.attempt_recovery()
        assert sys_in_error.state == State.ERROR
        # Now let it actually recover
        success, _ = sys_in_error.attempt_recovery()
        assert success is True
        assert sys_in_error.state == State.OPERATIONAL


# ──────────────────────────────────────────────
# TC-6  Full Lifecycle Tests
# ──────────────────────────────────────────────

class TestFullLifecycle:
    def test_full_happy_path(self, sys):
        assert sys.state == State.OPERATIONAL
        sys.trigger_fault(FaultType.NETWORK_TIMEOUT)
        assert sys.state == State.ERROR
        success, _ = sys.attempt_recovery()
        assert success is True
        assert sys.state == State.OPERATIONAL

    def test_full_failure_then_retry(self, sys):
        sys.trigger_fault(FaultType.NETWORK_TIMEOUT)
        handler = sys._current_handler
        with patch.object(handler, "try_recover", return_value=(False, "mocked failure")):
            sys.attempt_recovery()
        assert sys.state == State.ERROR
        sys.attempt_recovery()
        assert sys.state == State.OPERATIONAL

    def test_consecutive_faults(self, sys):
        for _ in range(5):
            sys.trigger_fault(FaultType.SERVER_CRASH)
            sys.attempt_recovery()
        assert sys.get_status()["metrics"]["successful_recoveries"] == 5


# ──────────────────────────────────────────────
# TC-7  Metrics Accuracy
# ──────────────────────────────────────────────

class TestMetrics:
    def test_recovery_rate_100_when_all_succeed(self, sys):
        for _ in range(5):
            sys.trigger_fault(FaultType.SERVER_CRASH)
            sys.attempt_recovery()
        rate = sys.get_status()["metrics"]["recovery_success_rate"]
        assert rate == 100.0

    def test_recovery_rate_0_when_all_fail(self, sys):
        for _ in range(3):
            sys.trigger_fault(FaultType.NETWORK_TIMEOUT)
            handler = sys._current_handler
            with patch.object(handler, "try_recover", return_value=(False, "mocked")):
                sys.attempt_recovery()
        rate = sys.get_status()["metrics"]["recovery_success_rate"]
        assert rate == 0.0

    def test_avg_recovery_time_positive(self, sys):
        sys.trigger_fault(FaultType.SERVER_CRASH)
        sys.attempt_recovery()
        avg = sys.get_status()["metrics"]["avg_recovery_time_s"]
        assert avg >= 0

    def test_log_records_events(self, sys):
        sys.trigger_fault(FaultType.DATABASE_FAILURE)
        sys.attempt_recovery()
        log = sys.get_status()["log"]
        assert len(log) >= 2  # at least fault + recovery entries


# ──────────────────────────────────────────────
# TC-8  trigger_fault() guard conditions
# ──────────────────────────────────────────────

class TestTriggerFault:
    def test_trigger_from_operational_succeeds(self, sys):
        result = sys.trigger_fault(FaultType.DATABASE_FAILURE)
        assert result is True
        assert sys.state == State.ERROR

    def test_trigger_from_error_fails(self, sys_in_error):
        result = sys_in_error.trigger_fault(FaultType.DATABASE_FAILURE)
        assert result is False
        assert sys_in_error.state == State.ERROR

    def test_all_three_fault_types(self, sys):
        for fault in FaultType:
            sys.trigger_fault(fault)
            sys.attempt_recovery()
        assert sys.get_status()["metrics"]["total_faults"] == 3