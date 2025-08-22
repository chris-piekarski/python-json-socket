Python 3 BDD tests use Behave instead of Lettuce.

Setup
- Install dependencies: `python -m pip install behave`

Run
- From repo root: `PYTHONPATH=. behave -f progress2`

Notes
- Feature files live under `features/*.feature` (unchanged from Lettuce).
- Step definitions are in `features/steps/steps.py`.
- Behave will launch a simple server and client to validate JSON message flow.
