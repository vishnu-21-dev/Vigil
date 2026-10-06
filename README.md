# Vigil

**Live demo:** https://vigil-i41b.onrender.com/app/ (free tier: the first load after idle takes about a minute, and demo state resets on restart)

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
- The failsafe auto-quarantines only alerts with model confidence **≥ 0.95**. Lower-confidence alerts still appear with a pending request for a human, but are never contained automatically (why: [`ml/audit/RESULTS.md`](ml/audit/RESULTS.md), section 4).

### Configuration (`.env`)

| Variable | Default | Notes |
| --- | --- | --- |
| `GROQ_API_KEY` | empty | Empty means incident reports use the built-in template (`source: fallback`). |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Must be a model your key can access. |
| `MODEL_DIR` | `ml/models` | Where `model.pkl` and `scaler.pkl` live. |
| `DB_PATH` | `data/app_state.sqlite3` | SQLite file. |

`scikit-learn` is pinned to 1.8.0 because that is the version the saved model was pickled with. Change it only together with retraining.

### Always run with `--workers 1`

The failsafe loop and the device/zone seeding run once per worker process. With more than one worker you get duplicate seed devices and one failsafe loop per worker (containment is transactional, so they cannot double-contain an alert, but it is wasted work).

## Deploy on Render

`render.yaml` is a Blueprint for one web service on the **free** plan (demo setup).

1. Push the repo to GitHub.
2. Render dashboard: **New > Blueprint**, pick this repo, and apply it.
3. When asked, enter `GROQ_API_KEY` (it is `sync: false`, so it never lives in git).
4. Open `https://<your-service>.onrender.com/app/`.

Free-tier caveats: the service sleeps after ~15 minutes idle, so the failsafe loop pauses until the next request wakes it, and there is no persistent disk, so SQLite state (`/tmp`) resets on every deploy or restart. For real use, change `plan` to `starter`, add a 1 GB `disk` mounted at `/var/data`, and set `DB_PATH=/var/data/app_state.sqlite3`. Keep one instance. Check `PYTHON_VERSION` in `render.yaml` against what Render supports if the build fails.

## Tests

```bash
python -m pytest                       # backend (70 tests)
node tests/js/failsafe_state.test.js   # frontend failsafe-state logic
```

## Model accuracy

On a random row split the model scores 99.99%, but that split shares duplicate and time-adjacent rows between train and test. With whole devices or whole attack types held out, it scores about 99.9% F1. It does **not** generalize to an unseen botnet family: trained without BASHLITE, it catches 60% of BASHLITE traffic and 0% of its TCP/UDP floods. On some unseen devices, up to ~4.7% of benign rows are flagged. Full method and numbers: [`ml/audit/RESULTS.md`](ml/audit/RESULTS.md).

## Known limitations

- **After a restart**, alerts that went overdue while the server was down get one fresh 120s window (logged as `Restart: N overdue alert(s) ...`), so operators can review them before the failsafe acts. This is granted once per alert, so a crash loop can't postpone containment forever. A report lost to a crash after containment is regenerated at startup.
- **Up to ~5s of UI lag.** The failsafe checks once every 2s and the UI polls every 3s, so an alert can sit past 120s for up to ~2s before it is contained, and up to ~3s more before the UI shows it.
- **SQLite on deploy.** State is a local SQLite file. It needs a persistent disk, a single worker, and a host that does not spin down (a free-tier spin-down pauses the failsafe loop and, on an ephemeral disk, loses state).
