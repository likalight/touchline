# What Microsoft Foundry does for Touchline

The Foundry prize asks how Foundry speeds up building, orchestrating and managing AI. Here is the honest
before-and-after for this project. The line counts are from this repository.

| Job | Without Foundry | With Foundry | In this repo |
|---|---|---|---|
| **A new language** | Hand-write and test about 130 verified phrases per language. That is what we did for English, Spanish, French and Portuguese (`touchline/i18n.py`, 485 lines). | One model deployment writes graphics copy in any other language; the FactChecker binds every number to the verified line, then Content Safety checks it. No new code per language. | `touchline/agents/narrator.py` (`render_llm`) |
| **Shipping an agent change** | Prompts live in code; every change is a redeploy, with no record of which prompt was live. | Agents are published to **Foundry Agent Service** as versions tagged with the git commit, each with a content policy attached. Runtime binds to the published version; rollback is choosing a version. | `touchline/foundry_agents.py` (90 lines), `scripts/foundry_publish.py` (37 lines), run by `azd up` |
| **Knowing whether the agent is good** | Write and maintain your own judges for relevance, coherence, tool use and safety. | Eight built-in Foundry evaluators (quality, intent, tool-call accuracy, tool-output use, hate and violence) run next to Touchline's three domain checks, with results in the portal. | `scripts/foundry_eval.py` (127 lines, most of it the domain checks) |
| **Seeing what agents did** | Build a trace store and viewer. | One Bicep resource connects the project to Application Insights; every agent run and workflow superstep appears in Foundry's tracing view. | `infra/resources.bicep` (`tracing` connection) |
| **Safety** | Wire a moderation service, prompt-injection detection and policies separately. | The same Foundry (AI Services) account serves the model, Content Safety (Prompt Shields and moderation) and Speech; the agents carry a Responsible-AI policy. | `touchline/safety.py`, `touchline/speech.py` |
| **Security** | API keys per service, rotated by hand. | One managed identity, local auth disabled, four least-privilege roles on the one AI account (OpenAI User, Azure AI User, Speech User, Cognitive Services User for Content Safety), plus AcrPull on the registry. No keys. | `infra/resources.bicep` |

## Intended value for a broadcaster (requires live validation)

* **A route to additional languages.** Turning on Tamil, Japanese or Swahili graphics is a setting, with numeric/name checks before display; semantic equivalence and language quality require human review.
* **Agents are managed like software.** Each version is tied to a commit, carries its safety policy, and can be evaluated and rolled back from the portal.
* **One place to look.** Model, agents, evaluations, traces and safety live in one Foundry project per broadcaster.

## Graceful without it

Foundry is the production path, not a single point of failure. If the hosted agent is unreachable the same
agent runs locally on the Foundry model, and if the model is down the verified phrase banks take over: see the
resilience drills in the app and [GOVERNANCE.md](GOVERNANCE.md).

## Evidence status

The integration is implemented. A live hosted run, Foundry evaluation and observed rollback
have not yet been recorded for this revision. Follow [DEPLOYMENT_PROOF.md](DEPLOYMENT_PROOF.md).
Analyst answers now expose per-request execution provenance; aggregate backend configuration
is not treated as proof that an individual answer ran in Foundry. The local evaluation trusts
tool outputs only and validates cited event IDs. These checks do not prove semantic entailment.
