# What Microsoft Foundry does for Touchline

Touchline uses Agent Framework orchestration and published Foundry agents for optional model
language work and tool-using analyst Q&A. Deterministic analytics and phrase banks keep the
core synthetic broadcast independent of model latency.

| Capability | Implemented | Evidence boundary |
|---|---|---|
| Versioned hosted agents | Publication and pinned runtime versions | Version 4 observed on the current Azure image, selecting exact source statements without fallback |
| Q&A tools | Scoreboard, player, event and team context | Source binding and fallback require application tests, not just portal publication |
| Additional languages | Optional generated rewrites | No fluent-speaker quality score is claimed |
| Quality evaluation | Version-4 bounded application run: six of six hosted cases passed | [Raw results and limits](FOUNDRY_EVAL.md); full portal and broader semantic/language evaluation remain |
| Content controls | Policy configuration, Content Safety and Prompt Shields integration | Offline screening is not equivalent moderation; service failure must remain explicit |
| Service authentication | Managed identity | Separate from human producer identity |
| Observability | Tracing integration and request-level execution metadata | Do not infer that every trace has been inspected in the portal |

[Current hosted request proof](evidence/final-hosted-answer.json) records an actual invocation,
model, duration and fallback status. [Deployment proof](DEPLOYMENT_PROOF.md) records its revision
and the wider cloud chain. GitHub Actions provides CI; it is not GitHub Copilot Agent Mode.

The useful lifecycle story is publish → invoke with tools → evaluate → inspect failures →
pin a tested version. Rollback support in code is not an observed rollback experiment.
