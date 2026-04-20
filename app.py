"""
CS 527 - Fault-Tolerant System: Flask Backend
Group 12: David Zhao, Chelsea Sun
"""

import random

from flask import Flask, jsonify, request, render_template
from state_machine import FaultTolerantSystem, FaultType

app = Flask(__name__)
# Background thread only retries recovery when in ERROR (no random fault injection).
RECOVERY_WATCH_INTERVAL_S = 2.0

system = FaultTolerantSystem()
system.start_auto(interval=RECOVERY_WATCH_INTERVAL_S)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    return jsonify(system.get_status())


@app.route("/api/inject_fault", methods=["POST"])
def inject_fault():
    """Inject fault then immediately attempt recovery (fault → recover chain)."""
    data = request.get_json(silent=True) or {}
    fault_name = data.get("fault_type")
    fault_type = None
    if fault_name:
        fault_type = next((f for f in FaultType if f.value == fault_name), None)
        if fault_type is None:
            return jsonify(
                {
                    "success": False,
                    "state": system.state.value,
                    "message": "Unknown fault_type",
                }
            )
    if fault_type is None:
        fault_type = random.choice(list(FaultType))
    injected = system.trigger_fault(fault_type)
    rec_ok, rec_msg = (None, None)
    if injected:
        rec_ok, rec_msg = system.attempt_recovery()
    return jsonify(
        {
            "success": injected,
            "state": system.state.value,
            "recovery_attempted": injected,
            "recovery_success": rec_ok,
            "recovery_message": rec_msg,
        }
    )


@app.route("/api/reset", methods=["POST"])
def reset():
    global system
    system.stop_auto()
    system = FaultTolerantSystem()
    system.start_auto(interval=RECOVERY_WATCH_INTERVAL_S)
    return jsonify({"success": True})


@app.route("/api/recovery_env", methods=["GET", "POST"])
def recovery_env():
    """Match batch harness knobs: CPU stress during try_recover, extra delay before network recover."""
    global system
    if request.method == "GET":
        return jsonify(
            {
                "stress_during_recovery": system.web_stress_recovery,
                "network_recovery_delay_ms": system.web_net_delay_ms,
            }
        )
    data = request.get_json(silent=True) or {}
    kw = {}
    if isinstance(data.get("stress_during_recovery"), bool):
        kw["stress_during_recovery"] = data["stress_during_recovery"]
    if "network_recovery_delay_ms" in data:
        kw["network_recovery_delay_ms"] = int(data["network_recovery_delay_ms"])
    system.set_recovery_env(**kw)
    return jsonify(
        {
            "success": True,
            "stress_during_recovery": system.web_stress_recovery,
            "network_recovery_delay_ms": system.web_net_delay_ms,
        }
    )


@app.route("/api/fault_types")
def fault_types():
    return jsonify([f.value for f in FaultType])


if __name__ == "__main__":
    # threaded=True: long-running POST /api/inject_fault must not block GET /api/status
    # so the UI can poll Error/Recovery while try_recover runs.
    app.run(debug=True, port=5000, threaded=True)
