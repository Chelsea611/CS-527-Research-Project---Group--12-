# CS 527 · Fault-Tolerant System · Group 12
**David Zhao, Chelsea Sun · UIUC**

## Project Structure
```
project/
├── state_machine.py          # Core state machine logic
├── app.py                    # Flask web backend
├── run_simulation.py         # Evaluation simulation (generates CSV)
├── simulation_results.csv    # Evaluation data for the report
├── templates/
│   └── index.html            # Live monitoring dashboard
└── tests/
    └── test_state_machine.py # 30 automated test cases
```

## Setup & Run

### Install dependencies
```bash
pip install flask pytest
```

### Run automated tests
```bash
pytest tests/test_state_machine.py -v
# → 30 tests, all pass
```

### Run evaluation simulation
```bash
python run_simulation.py
# → generates simulation_results.csv
```

### Start web dashboard
```bash
python app.py
# → open http://localhost:5000
```

## State Machine

```
OPERATIONAL ──(fault detected)──▶ ERROR ──(recovery triggered)──▶ RECOVERY
     ▲                                                                  │
     └──────────(recovery success)──────────────────────────────────────┘
                                          └──(recovery failed)──▶ ERROR
```

### States
| State | Description |
|---|---|
| Operational | System running normally |
| Error | Fault detected, awaiting recovery |
| Recovery | Attempting to restore normal operation |

### Fault Types
- Network Timeout
- Database Failure
- Server Crash

## Evaluation Results (500 trials across 5 configurations)

| Config Recovery Rate | Actual Recovery Rate | Avg Time (s) |
|---|---|---|
| 70% | 98.0% | 0.0139 |
| 80% | 100.0% | 0.0133 |
| 85% | 100.0% | 0.0127 |
| 90% | 100.0% | 0.0120 |
| 95% | 100.0% | 0.0112 |

High actual recovery rates (98–100%) are achieved even at low per-attempt
probabilities due to the retry mechanism (up to 5 attempts per fault).
