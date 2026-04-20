"""
Real Server Crash Fault Handler
- Fault:    Sets a stop event on the worker thread so it dies
- Recovery: Spawns a fresh worker thread and verifies it's processing tasks
"""

import threading
import queue
import time


class ServerCrashFaultHandler:
    def __init__(self):
        self._task_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._tasks_processed = 0
        self._start_worker()  # start healthy

    # ── Worker Thread ────────────────────────────────────────

    def _start_worker(self):
        """Spawn a worker thread that processes tasks from the queue."""
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True
        )
        self._worker_thread.start()

    def _worker_loop(self):
        """Worker: pulls tasks off queue, processes them, puts results back."""
        while not self._stop_event.is_set():
            try:
                task = self._task_queue.get(timeout=0.5)
                # Simulate doing real work: compute task value
                result = {"task_id": task["id"], "result": task["value"] * 2}
                self._result_queue.put(result)
                self._tasks_processed += 1
                self._task_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                break

    # ── Fault & Recovery ────────────────────────────────────

    def trigger_fault(self):
        """
        Actually crash the worker: set the stop event so the
        thread exits its loop and dies.
        """
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
        self._worker_thread = None

    def try_recover(self):
        """
        Actually fix it: spawn a new worker thread, submit a
        test task, and verify it gets processed correctly.
        """
        try:
            self._start_worker()
            time.sleep(0.2)  # give thread time to start

            if not self._worker_thread or not self._worker_thread.is_alive():
                return False, "Worker thread failed to start"

            return self._verify_worker()
        except Exception as e:
            return False, f"Worker restart failed: {e}"

    def _verify_worker(self):
        """Submit a real task and verify the worker returns the right result."""
        # Clear any old results
        while not self._result_queue.empty():
            self._result_queue.get()

        test_task = {"id": "recovery_test", "value": 21}
        self._task_queue.put(test_task)

        try:
            result = self._result_queue.get(timeout=3.0)
            if result["task_id"] == "recovery_test" and result["result"] == 42:
                return True, f"Worker verified — processed task correctly (21×2=42), total tasks: {self._tasks_processed}"
            return False, f"Worker returned wrong result: {result}"
        except queue.Empty:
            return False, "Worker did not process test task within timeout"

    def is_healthy(self):
        return (
            self._worker_thread is not None
            and self._worker_thread.is_alive()
            and not self._stop_event.is_set()
        )

    def submit_task(self, value):
        """Used by external code to submit real tasks to the worker."""
        task_id = f"task_{int(time.time()*1000)}"
        self._task_queue.put({"id": task_id, "value": value})
        return task_id
