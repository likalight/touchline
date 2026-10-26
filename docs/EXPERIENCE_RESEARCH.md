# A match you can investigate across time

Research and implementation review: 26 October 2026.

The strongest product direction is an inspectable match story. A viewer sees a goal,
understands its connection to an earlier event, checks the original source, switches
perspective and explores a clearly labeled alternate ending. This is our design hypothesis;
we have not measured a 10× improvement, user preference or commercial novelty.

## What the sources change about our design

| Primary source | Finding relevant to Touchline | Design decision |
|---|---|---|
| [Premier League / Microsoft partnership](https://www.premierleague.com/en/about/partners/microsoft) | The Companion already centers personalized football experiences | Lead with inspectable memory, not generic AI chat or personalization |
| [WSC Sports Arena](https://wsc-sports.com/platform/) | Automated event analysis and personalized sports content are established product capabilities | Do not claim automatic highlights alone are a new category |
| [Sportify, research paper](https://arxiv.org/abs/2408.05123) | Basketball research combines action visualizations with narrative explanations; different narrative perspectives serve different viewer needs | Keep the selected explanation and evidence together; offer a direct perspective switch |
| [SportsBuddy, research paper](https://arxiv.org/abs/2502.08621) | Its authoring tool combines tracking, contextual interaction and timelines; the authors report real deployments | Make the timeline navigable and attach sources to moments; avoid a disconnected statistics wall |
| [NISTIR 8312](https://nvlpubs.nist.gov/nistpubs/ir/2021/nist.ir.8312.pdf) | Explanations should suit their audience, reflect the actual process and expose knowledge limits | Preserve original receipts; separate event positions from inferred trajectories and simulations from facts |
| [Official judging rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) | Implementation, innovation, impact, presentation and category fit have equal weight | Pair the visual story with working proof and the deployment/user evidence still needed |

These sources inform the design. Their results do not establish Touchline's usability,
accuracy or comparative advantage, and they do not imply competitor products lack receipts.

## Gaps addressed in this pass

The previous screen gave most space to a broadcast simulation and put story details in a
scrolling feed. Redemption could disappear from the shorter Fan render. Evidence meant
opening raw IDs in a drawer. Important controls competed with the core demo.

The revised `/judge` experience has:

- An editorial opening that contracts when playback starts, giving space back to the pitch.
- Three chapter markers that unlock only when their goals are delivered. Selecting an earlier
  chapter pins its explanation and evidence; the live pitch remains labeled separately.
- A persistent match-memory explanation from the Analyst render, with its actual language
  identified. Changing the audience changes the moment's explanation without hiding memory.
- Human-readable links from redemption back to the earlier possession loss. The source event
  map uses original coordinates and endpoints. Missing coordinates stay missing.
- A selected-goal alternate ending using the existing paired simulation engine. Both branches,
  source ID, simulation count and model limitations are visible.
- Original receipt access, comparison and JSON export. Slow replies cannot overwrite a newer
  selection or a restarted session. Failed requests can be retried.
- Responsive layouts, keyboard focus, reduced-motion-aware navigation and clearer mobile
  pitch visibility. These are implementation checks, not an accessibility certification.
- A [taste-guided visual overhaul](TASTE_REVIEW.md): original atmosphere image, two themes,
  quieter editorial layouts and a deferred 3D load on the entrance.

## Remaining gaps, ranked by evidence value

| Priority | Gap | Concrete next evidence | Why it matters |
|---|---|---|---|
| 1 | No verified public Azure deployment | Subscription/region/budget, then deploy and save live Foundry execution and downstream package results | Baseline viability, Foundry and cloud-native category credibility |
| 2 | No observed first-time user outcomes | Run the existing protocol with 3–5 consenting participants; record completion, explanation accuracy and time to locate a source | Impact and intuitive UX need human evidence |
| 3 | No final demonstration video | Record the deployed journey in under two minutes, including actual cloud proof | Judges need the central value quickly |
| 4 | Model usefulness and semantic quality are not established | Run the hosted narration comparison, retain failures, review translations with fluent speakers | Numeric checks are narrower than explanation quality |
| 5 | Enterprise recovery is not fully durable | Transactional outbound outbox, durable editorial audit, authenticated operator and process-kill drills | Needed before production claims or broadcaster adoption |
| 6 | Multi-match scale and match-length capacity are unproven | Partition ownership, session routing and an external full-match soak with delivery measurements | One warm replica and a short local load experiment are not scale proof |
| 7 | The visual simulation is not match footage | Validate comprehension of the current schematic view before investing in more realism | A costly stadium redesign may add less value than a clearer explanation |

The rules permit at most one Grand Prize and one Category Prize for a project. We should
make every applicable category case credible, while choosing the strongest evidence for the
submission. No presentation change can substitute for the missing hosted and human results.

## Reproducing the experience checks

Run `node --test tests/story.test.cjs` and `pytest tests/test_judge_receipts.py -q`.
The full browser journey is `node tests/story-browser.cjs`, against a running server on
`http://127.0.0.1:8765` (override with `TOUCHLINE_URL`). It requires Playwright and Chromium;
`PLAYWRIGHT_MODULE` and `CHROMIUM_EXECUTABLE` can point at existing installations.
It uses a real 90-second replay and saves screenshots under `work/story` by default
(`STORY_SCREENSHOTS` overrides this). The Node contract tests run in CI; the browser journey
is also run locally and is not represented as a hosted Azure test.
