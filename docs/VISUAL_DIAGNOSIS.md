# Visual and readiness diagnosis — 27 October 2026

This is an assessment of the current implementation, not a prediction of judges' scores.
The local interface was captured and exercised during this audit. Public cloud operation,
human benefit and competitor reliability are not established by those local screenshots.

## What changed

- Replaced the anonymous ball-on-grass judge cover with an original generated illustration
  of the fictional protagonist, Ravi Varga. Responsive WebP versions are 12.6 / 36.1 / 98.0 kB.
- Made the opening one photographic composition with readable HTML text, one main action,
  three numbered chapters, and a visible fictional-image disclosure.
- Compressed the main scoreboard and replay controls. Kept the player's earlier connection
  ahead of the chance-quality statistic in both visual and DOM reading order.
- Replaced the flat shirt cutout in Player Spotlight with Ravi's illustration for Ravi only.
  Other players use their own squad number. Selection, camera follow and receipts are unchanged.
- Increased profile annotations and receipt readability; retained light/dark themes,
  reduced-motion support and keyboard focus behavior.
- Added versioned references to changed assets after observing stale CSS in a returning browser.
- Changed the receipt's success label to “Source checks passed”; exported verification data
  remains unchanged. This deliberately describes the scope of the check.

## Observed flow

1. **Match centre:** functional but too many introductory rows before the pitch. Header and
   scoreboard now consume less space. The full-app eight-tool workspace still needs further
   progressive disclosure; it is a secondary path, not the first judge demonstration.
2. **Judge entry:** worked but its generic cover conveyed neither a player nor a distinctive
   story. New opening gives the demonstration a recognisable protagonist and direct promise.
3. **Replay:** three chapters, source links and perspective switching worked. Previously the
   stat arrived before the explanation connecting the moments. The connection now comes first.
   Chapter selection still does not rewind the animated pitch; that limitation is disclosed.
4. **Receipt:** source facts, checks, editorial decision and handoffs were accessible, but dense
   IDs and small text felt technical. Typography and spacing are improved. A human-readable
   claim-by-claim verdict with source excerpts remains a useful next improvement.
5. **Player:** selection and current totals worked; the CSS shirt illustration looked basic.
   The new portrait creates identity, and captions stay truthful about synthetic content.
   The other 21 players do not yet have individual artwork.

## Critical source-data finding

Reproduction: `from touchline.sim.engine import simulate; meta, events = simulate(221)`.
The simulator emits a second yellow for `h8` (Tariq Calloway) in minute 29, then emits
**91 later events whose `player_id` is `h8`**, including passes in minute 93.
The winner's receipt cites that player in the build-up while the narrative says Kestrel
Bay have ten men. `MatchSimulator.foul()` emits the dismissal but `squad()` continues
returning the full original roster.

This is a source-validity defect, not a translation or screenshot issue. Numeric/source checks
can pass over an internally inconsistent synthetic world. Do not hide the offending event,
change the card label, or suppress the ten-player explanation as a workaround.

Required correction: track dismissals, exclude dismissed players from action selection,
pass targets and tracking frames, preserve formation-role anchors, and define short-handed
goalkeeper/restart behavior. Add full-match roster-consistency checks across multiple seeds.
Then reselect or regenerate a valid story and rerun the affected tests, evaluations, receipts
and recording. Existing passing tests do not cover this invariant. **Not fixed in this revision.**

## Prize assessment

The official rules cap each entrant at one Grand Prize and one Category Prize. The practical
objective is strong overall judging performance and one particularly well-supported specialty.

| Prize | Current assessment | Evidence needed |
|---|---|---|
| Grand Prize, first or second | Plausible concept; incomplete submission case | Valid synthetic story, reliable public access, clear final video, credible benefit |
| Best Multi-Agent System | Strongest relative fit within this project; not a proven leader | Explain distinct responsibilities and handoffs; show recovery; complete a fair baseline comparison |
| Best Use of Microsoft Foundry | Provisioning is progress, but hosted effectiveness is under-evidenced | Actual tool-grounded call, trace, evaluation results, configuration/version proof and timing/cost |
| Best Azure Cloud Native Integration | Relevant architecture; operation still unproven end to end | Working public app, observed Event Hubs → app → Event Hubs → Functions → Blob delivery and restart drill |
| Best Enterprise Solution | Weakest current case | Durable editorial records/outbox, authenticated producer exercise, tenant/concurrency limits, operator evidence |

Across the five equally weighted judging criteria, adherence has broad implemented coverage;
technical implementation has meaningful tests but the roster defect and cloud gaps; innovation
needs measured specialist value; impact lacks participants/operator evidence; presentation
has improved locally but lacks the final public narrated video. None is a verified winning score.

## Remaining visual direction

The next major gain is synchronizing a selected chapter's recorded action with its explanation,
with unmistakable “live” versus “reviewing 76′” state. A dramatic portrait alone cannot make a
low-detail 3D simulation look like television. Improve camera framing, player identity, ball
legibility and event-linked emphasis before adding cinematic effects. Keep the tactical map
as a clear evidence view.

Longer-term: bring audience changes into a compact comparison, name source events in plain
language, make operator controls a distinct workflow, and explain empty states accurately
after full time. Prioritize football validity and the final demonstration over more features.

## Validation and limits

- Existing `tests/story-browser.cjs`: passed full replay, chapter locking/pinning, evidence
  geometry, perspective/translation changes, checker, downloads, stale-response isolation,
  retry, pause/refresh/restart, keyboard focus and 320/390/768 px layout checks.
- Existing `tests/centre-browser.cjs`: passed player selection/totals/moment receipts,
  camera identity, eight tools, keyboard navigation, both themes, responsive widths,
  route isolation, phone and reel checks.
- Manual browser check: selecting Lucas Sato hides Ravi's image and restores number-only
  identity. AI illustration is explicitly labeled.
- Existing backend suite earlier passed 83 tests; deployment/Foundry changes passed 14 focused
  tests. Those are prior results, not evidence that the newly found roster invariant holds.
- Public `/api/ready` check during this audit timed out after 20 seconds. Infrastructure and
  Functions provisioning do not establish that the web application is serving judges.
- No participant research, screen-reader audit, complete contrast audit, production latency
  measurement or comprehensive competitor demo comparison was completed in this revision.

Source: [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md).
The submission deadline is 28 October 2026, 14:59 Singapore time. Protect time for a valid
functioning build, a public video under two minutes, and actual submission confirmation.

## Follow-up: active-roster fix

PR #7 resolves the dismissed-player blocker. The corrected simulator removes dismissed players from actions, targets, restarts and tracking; the pitch removes absent players. Seed 221 is a regression case. Judge Mode was regenerated from seed 87: Kofi Varga, mistake at 28 minutes, redemption at 44, winner at 90 (3–2). All 92 Python tests, six JavaScript tests and both full browser journeys passed. A targeted browser check also confirmed h8 disappears from the pitch interpolation state after his second yellow. The findings above describe the earlier audited revision.
