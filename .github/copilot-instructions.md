# Working on Touchline with GitHub Copilot

Touchline is a multi-agent system (Microsoft Agent Framework) that explains a live, synthetic football match.

* **Ask the match, don't guess.** With the app running (`uvicorn touchline.server:app`), Copilot agent mode can use the `touchline` MCP server from `.vscode/mcp.json`: `list_matches`, `get_scoreboard`, `get_key_moments`, `explain_event`, `get_player`, `get_team_report`, `get_recap`, `ask_analyst`. Quote numbers exactly and cite event IDs (E01837).
* **Every number must be verifiable.** New insight types need FactChecker support in `touchline/agents/verifier.py` and a test that a tampered value is blocked.
* **Synthetic data only.** Never add real clubs, players, logos or match data.
* **Keep the hot path model-free.** Language-model work arrives later as an update.
* Run `pytest -q` and `python scripts/evaluate.py --gate` before proposing a change.
