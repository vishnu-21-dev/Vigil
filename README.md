# Vigil
Vigil monitors IoT devices in real time, detecting behavioral anomalies via a Random Forest model trained on N-BaIoT. Operators get 120s to respond — if they don't, an AI failsafe auto-quarantines the device. Built with FastAPI, scikit-learn, and Groq.

## Run it

Requires Python 3.14 (what the pinned versions were tested on).

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then put your Groq key in .env (never commit it)
uvicorn api.main:app --port 8000 --workers 1
```

- UI: <http://localhost:8000/app/> (dashboard, alerts, quarantine, reports)
- API docs: <http://localhost:8000/docs>
- Inject a demo anomaly: `POST /demo/trigger-anomaly`, then leave the alert alone for 120s to watch the failsafe fire.

### Configuration (`.env`)

| Variable | Default | Notes |
| --- | --- | --- |
| `GROQ_API_KEY` | empty | Empty means incident reports use the built-in template (`source: fallback`). |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Must be a model your key can access. |
| `MODEL_DIR` | `ml/models` | Where `model.pkl` and `scaler.pkl` live. |
| `DB_PATH` | `data/app_state.sqlite3` | SQLite file. |

`scikit-learn` is pinned to 1.8.0 because that is the version the saved model was pickled with. Change it only together with retraining.

### Always run with `--workers 1`

The failsafe loop and the device/zone seeding run once per worker process. With more than one worker you get duplicate seed devices and several loops contending to contain the same alert.

## Tests

```bash
python -m pytest                       # backend (42 tests)
node tests/js/failsafe_state.test.js   # frontend failsafe-state logic
```

## Model accuracy

On a random row split the model scores 99.99%, but that split shares duplicate and time-adjacent rows between train and test. With whole devices or whole attack types held out, it scores about 99.9% F1. It does **not** generalize to an unseen botnet family: trained without BASHLITE, it catches 60% of BASHLITE traffic and 0% of its TCP/UDP floods. On some unseen devices, up to ~4.7% of benign rows are flagged. Full method and numbers: [`ml/audit/RESULTS.md`](ml/audit/RESULTS.md).

## Known limitations

- **Check-then-act race.** `auto_quarantine` re-reads the alert and device, then writes, without a single transaction. An operator approving or dismissing at the same instant as the failsafe can still produce a conflicting result.
- **About 15s of UI lag.** The failsafe checks once every 10s and the UI polls every 5s, so an alert can sit past 120s for up to ~10s before it is contained, and up to ~5s more before the UI shows it.
- **SQLite on deploy.** State is a local SQLite file. It needs a persistent disk, a single worker, and a host that does not spin down (a free-tier spin-down pauses the failsafe loop and, on an ephemeral disk, loses state).
