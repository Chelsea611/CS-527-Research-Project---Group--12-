"""
CS 527 - Fault-Tolerant System: Flask Backend
Group 12: David Zhao, Chelsea Sun
"""

from flask import Flask, jsonify, request, render_template
from state_machine import FaultTolerantSystem, FaultType

app = Flask(__name__)
system = FaultTolerantSystem(fault_probability=0.2, recovery_success_rate=0.85)
system.start_auto(interval=3.0)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    return jsonify(system.get_status())


@app.route("/api/inject_fault", methods=["POST"])
def inject_fault():
    data = request.get_json(silent=True) or {}
    fault_name = data.get("fault_type")
    fault_type = None
    if fault_name:
        fault_type = next((f for f in FaultType if f.value == fault_name), None)
    success = system.inject_fault(fault_type)
    return jsonify({"success": success, "state": system.state.value})


@app.route("/api/reset", methods=["POST"])
def reset():
    global system
    system.stop_auto()
    system = FaultTolerantSystem(fault_probability=0.2, recovery_success_rate=0.85)
    system.start_auto(interval=3.0)
    return jsonify({"success": True})


@app.route("/api/fault_types")
def fault_types():
    return jsonify([f.value for f in FaultType])


if __name__ == "__main__":
    app.run(debug=True, port=5000)
