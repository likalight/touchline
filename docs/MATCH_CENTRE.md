# A coherent match centre, starting at `/`

26 October 2026. The first redesign changed `/judge` while leaving the default route in
the old green studio interface. That was a scope error: someone opening the app normally
could miss almost all of the work. This pass redesigns the default route and shares its
appearance with the guided story, phone companion and highlights player.

## Design direction

Reading this as a football product for fans, analysts and judges, with the clarity of a
professional product and the presence of a sports broadcast. The direction is plum,
off-white and lime, self-hosted Barlow typography, a prominent match score and a focused
story surface. Dials: design variance 7, motion intensity 3, visual density 4.

The taste and existing-project redesign skills inform the visual audit. This is native
CSS in the existing application, not a Fluent component implementation or an official
Premier League design. There are no league marks or claims of endorsement.

## Player experience follow-up

The visual audit found three concrete gaps: the featured player was difficult to identify,
the crowd competed with the replay, and the desktop pitch began about 606px down the page.
The compact header now brings the pitch to approximately 485px at 1440px width. Judge Mode
retains its separate introduction.

Player Spotlight adds a fictional kit illustration, all 22 players, three timestamped
match totals and up to three delivered player moments. Goal explanations take precedence
over same-minute milestones. Viewers can pin an earlier moment, inspect its receipt,
return to the latest moment, or follow the player on the pitch. The identity label tracks
the actual camera subject, including the replay scorer. Stadium colours are restrained;
the elevated replay camera shows more pitch, with a stationary orbit under reduced motion.

The profile never fetches future match history. Totals are explicitly timed separately
from a selected story, and only the current audience/language rendering supplies its
prose. An illustrated kit is not a player likeness or an official club asset.

Validation: 83 backend tests and six JavaScript tests passed. The real match-centre browser
journey checks player selection, snapshot values, earlier-moment pinning, goal/milestone
deduplication, keyboard focus, receipt access, follow camera and identity. The shared-route
checks cover both themes, all eight tools, and 320/390/768px layouts. Screenshots in the
README show the running application, not a design mockup. These checks are functional
and visual verification, not human usability evidence. Lighthouse 13.5.0's local mobile
accessibility audit scored 100 after correcting description-list markup and matching the
moment buttons' accessible names to their visible labels; automated checks do not replace
screen-reader or participant testing.

[Microsoft's Fluent principles](https://fluent2.microsoft.design/design-principles) emphasize
focus, familiar behavior and inclusion. We apply those principles through progressive
disclosure, readable controls and keyboard navigation. The [Premier League/Microsoft
partnership](https://www.premierleague.com/en/about/partners/microsoft) centers personalized
fan experiences; our design inference is that the football story should lead, with tools
and agent evidence available when the viewer wants them. These sources are design inputs,
not validation of Touchline's usability.

## What changed

- The default page opens with the match identity and a large score, followed by a compact
  audience toolbar. Player focus, metrics, audio and replay controls remain under Personalise.
- A prominent story presents the latest goal and the Analyst's linked memory. The goal
  timeline contains only delivered goals. Selecting one pins that story without rewinding
  the pitch; Follow latest resumes automatic selection.
- The live feed remains available. Raw source IDs and feedback move into native disclosures,
  while the evidence receipt remains immediately accessible.
- The default camera is the tactical event visualization for visitors without a saved
  camera preference. TV and player cameras remain available and load Three.js on demand.
- Match metrics sit beside the pitch's timeline. Highlights, Q&A, counterfactuals, players,
  production, agent operations and architecture have a separate exploration area.
- Appearance persists across `/`, `/judge`, `/phone` and `/reel`. The phone link now carries
  the current session. The reel has a direct path back to the match centre.
- Keyboard tabs support arrows, Home and End with explicit tab/panel relationships. The
  player table scrolls within a labeled region instead of overflowing the phone viewport.
- Source inspection handles a missing event outcome as “Not recorded”; previously that
  value could throw before the evidence drawer opened.
- Reconnect and seek history is batched into one feed update, reducing repeated layout
  work during the initial event burst. Seeking preserves a pinned goal; reconnecting
  rebuilds the session view and returns to the latest goal.

## Validation and limits

The main-app browser journey checks a real isolated seed-221 match: chronological goals,
pinned-versus-latest selection, audience/language changes, nullable source data, receipt
downloads and focus restoration, preferences, keyboard tabs, Q&A, all eight tool panels,
TV/player/tactical cameras, 320/390/768px layouts and theme persistence across routes.
The separate complete 90-second Judge Mode journey checks the shared UI regression.

Local Lighthouse 13.5.0, mobile simulation, default `/` route: **95 performance, 100 automated
accessibility**, FCP 1.7s, LCP 2.8s, CLS 0.05 and TBT 20ms. Before batching history, the same
redesign scored 79 performance with 180ms TBT. These are individual local lab observations,
not a controlled benchmark or field INP measurement. LCP remains above the 2.5s target.
See [machine-readable audit](centre-audit.json).

No 10× improvement, participant preference, production device frame rate, hosted Azure
reliability or accessibility certification is claimed. The remaining hosted and human
evidence gaps are listed in [the category case](WINNING_CASE.md).

## Reproduce

Run a local server on port 8765, then `node tests/centre-browser.cjs` and
`node tests/story-browser.cjs`. Both require Playwright and Chromium. `PLAYWRIGHT_MODULE`,
`CHROMIUM_EXECUTABLE`, and `TOUCHLINE_URL` can point at existing installations.
`CENTRE_SCREENSHOTS` selects the main-app screenshot directory.
