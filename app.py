"""
CS 527 - Fault-Tolerant System: Flask Backend
Group 12: David Zhao, Chelsea Sun
"""

import random

from flask import Flask, jsonify, request, render_template
from state_machine import FaultTolerantSystem, FaultType

app = Flask(__name__)
AUTO_INTERVAL_S = 3.0

system = FaultTolerantSystem()
system.start_auto(interval=AUTO_INTERVAL_S)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    return jsonify(system.get_status())


@app.route("/api/inject_fault", methods=["POST"])
def inject_fault():
    """Maps to FaultTolerantSystem.trigger_fault (real subsystem fault)."""
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
    success = system.trigger_fault(fault_type)
    return jsonify({"success": success, "state": system.state.value})


@app.route("/api/reset", methods=["POST"])
def reset():
    global system
    system.stop_auto()
    system = FaultTolerantSystem()
    system.start_auto(interval=AUTO_INTERVAL_S)
    return jsonify({"success": True})


@app.route("/api/fault_types")
def fault_types():
    return jsonify([f.value for f in FaultType])


if __name__ == "__main__":
    app.run(debug=True, port=5000)
