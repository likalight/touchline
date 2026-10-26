# Touchline design system: Floodlit

The studio, on-air graphics and highlight reels use Floodlit below. Judge Mode uses the
new **Matchday** presentation: graphite/off-white, citron, self-hosted Barlow, system-aware
light/dark themes and an original generated atmosphere image. The [taste review](TASTE_REVIEW.md)
records its audit, tokens, scope and verification. No league or club marks are used.

## Principles

1. **The pitch is the hero.** Graphics frame the game; they never cover the ball's
   likely path. Lower-thirds sit bottom-left in the title-safe area, panels top-right.
2. **Evidence is a colour.** Floodlight amber means "checked against the match data":
   the verified tick, evidence chips, the accent bar on graphics. It is used for nothing else.
3. **Clubs own their colour, nothing else does.** The only saturated hues are the two kit
   colours, and they only ever mark a team: card edges, scorebug pips, the strap on a
   lower-third, players.
4. **Data in condensed type, reasons in a serif.** Numbers and headlines are set in
   Barlow Condensed like a scorebug; the *why* is set in Source Serif like a match report,
   so explanation reads differently from statistics.
5. **Motion says what changed, once.** Graphics wipe in on a bar, the headline follows,
   the reason last. Nothing loops, bounces or pulses.

## Tokens

| Token | Value | Role |
|---|---|---|
| `--turf` | `#0f2b20` | Ground of the app and dark graphics |
| `--turf-2` / `--turf-3` | `#123426` / `#184232` | Raised surfaces (tone steps, never borders) |
| `--panel` | `#0c241b` | Cards and panels |
| `--chalk` | `#eef0e8` | Text on dark; light graphic ground |
| `--chalk-dim` | `#a6b3a9` | Secondary text (still AA on `--turf`) |
| `--sodium` | `#f2c14e` | Evidence and the single primary action |
| `--home` / `--away` | from the club kit | Team marks only |

Contrast (computed, WCAG 2.x): chalk on turf 13.2:1; chalk-dim on turf 7.0:1; turf on sodium 9.0:1. All pass AAA for body text.

## Type

| Use | Face | Size |
|---|---|---|
| Scorebug, headlines, minute marks | Barlow Condensed 700 | 17 to 26 px in the app, 66 to 86 px on air |
| Interface | Barlow 400/500/600 | 14 to 15 px |
| Reasons and recaps | Source Serif 4 | 15 to 16 px in the app, 34 px on air |

All three are SIL Open Font License, self-hosted and subset to Latin.

## Broadcast rules (on-air template, reels and in-app TV view)

- **Canvas** 1920 x 1080, transparent; graphics stay inside the 90% title-safe area
  (96 px left/right, 54 px top/bottom).
- **Lower-third anatomy**: floodlight bar (14 px) + panel + team strap (8 px) + "checked"
  kicker + headline + one reason. Goal banners invert to chalk ground.
- **Timing**: bar 220 ms, panel wipe 420 ms, strap 500 ms, kicker / headline / reason
  staggered at 320 / 380 / 500 ms; out in 300 ms. Easing in `cubic-bezier(.16,.84,.24,1)`,
  out `cubic-bezier(.6,0,.84,.24)`. Hold 5 to 12 s from the cue's `duration_s`.
- **One graphic per layer.** Higher priority pre-empts; stale graphics are skipped,
  never queued.
- **Reduced motion** removes all travel and keeps the content.

## Components

Judge Mode adds an editorial introduction that contracts during playback, a three-chapter
story rail, a persistent match-memory panel and a source-event pitch diagram. A selected
chapter controls its explanation and evidence; it does not rewind the live pitch. Future
chapters stay unavailable until delivered. Alternate endings use separate, labeled model
comparison bars. The evidence map joins recorded endpoints only and never invents missing
locations. On small screens the explanation sits below a clear pitch, replacing duplicate
lower-third copy. See [experience research](EXPERIENCE_RESEARCH.md) for the rationale.

Scorebug (two pips in kit colours, score on chalk, clock on amber); lower-third; side
panel with an inline chart; player tag that follows the player; story card; evidence
chip; producer cue row; insight card (team edge, minute, kind, verified tick, headline,
reasons, evidence).

## References we used

- **taste-skill** (Leonxlnx/taste-skill): house rules applied to the app (no gradients, no hairline
  dividers, tone steps instead of borders, no eyebrow labels) and its full process,
  lint and browser inspector for the story page (0 FAIL).
- **CasparCG** HTML producer conventions (`play`, `stop`, `next`, `update`) and **SPX
  Graphics Controller** template definitions, so the on-air template loads in open
  broadcast playout tools.
- Broadcast safe-area practice (title-safe 90%, action-safe 93%).
