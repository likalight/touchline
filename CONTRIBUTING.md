# Contributing to Touchline

Thanks for helping. Touchline is small enough to understand in an afternoon.

## Set up

```bash
pip install -r requirements.txt -r functions/requirements.txt pytest
uvicorn touchline.server:app --reload      # http://localhost:8000
```

Or open the repo in GitHub Codespaces: everything is preinstalled.

## Before you open a pull request

```bash
pytest -q                                   # all tests
python scripts/evaluate.py --matches 12 --gate   # 100% verified, every goal explained, latency, exactly-once ingest
```

CI runs both, plus a Bicep build and a container smoke test.

## Ground rules

* **Every number must be verifiable.** New insight types need FactChecker support (`touchline/agents/verifier.py`) and a test that a tampered value is blocked.
* **Synthetic data only.** No real match data, clubs, players, logos or footage.
* **The hot path never waits on a model.** Language-model work arrives later as an update.
* **Plain words in the UI.** Write for a fan, not for an engineer.

## Where things live

| Change | Start here |
|---|---|
| A new kind of insight | `touchline/agents/scout.py`, `touchline/agents/analyst.py`, `touchline/i18n.py` |
| A new agent in the workflow | `touchline/orchestrator.py` |
| A new language in the phrase banks | `touchline/i18n.py` |
| The 3D view | `web/tv3d.js` |
| Azure resources | `infra/resources.bicep` |
