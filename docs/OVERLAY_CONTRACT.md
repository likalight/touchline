# Overlay contract: `touchline.overlay/1`

Touchline does not draw on the broadcast itself. The Producer agent emits **cues**: small,
timed, machine-readable JSON documents keyed to the match clock. Any rendering partner can
play them in sync with the live feed. They can use their own templates, consume the SSE stream
or poll `GET /api/matches/{session}/cues`. The `/overlay` page in this repo is a
reference renderer. It shows the same cues on a transparent (keyable) background.

```json
{
  "schema": "touchline.overlay/1",
  "cue_id": "SYN-00007-I0021-C21",
  "insight_id": "SYN-00007-I0021",
  "match_id": "SYN-00007",
  "kind": "goal",
  "clock": { "match_t": 2271.4, "minute": 38 },
  "in_at_t": 2271.9,
  "duration_s": 9.0,
  "out_at_t": 2280.9,
  "layer": "lower_third",
  "template": "full_banner",
  "priority": 100,
  "anchor": { "x": 101.2, "y": 33.1, "units": "pitch_m" },
  "data": { "type": "shot", "x": 94.7, "y": 30.8, "end_x": 105, "end_y": 33.1, "xg": 0.38,
            "wp_before": 0.43, "wp_after": 0.75, "team": "home" },
  "copy": {
    "en": { "title": "GOAL! Niko Takahashi scores for Kestrel Bay FC", "line": "Chance quality: 0.38 xG" },
    "es": { "title": "¡GOL! Niko Takahashi marca para Kestrel Bay FC", "line": "Calidad de la ocasión: 0.38 xG" }
  },
  "evidence": ["E00803", "E00804", "E00805"],
  "verification": "verified",
  "approval": "auto"
}
```

| Field | Meaning |
|---|---|
| `clock.match_t`, `in_at_t`, `out_at_t` | Seconds on the **match clock**, not wall time. A renderer aligns the cue to its own feed timecode, so the cue survives replays, delays and highlights packages. |
| `layer` | `lower_third`, `side_panel`, `player_tag`, `full_screen`. Only one cue per layer is on air at a time. A higher `priority` pre-empts a lower one. Lower-priority cues are marked `skipped` rather than queued, so stale graphics never air late. |
| `template` | `full_banner`, `shot_card`, `pass_card`, `player_tag`, `momentum_bar`, `phase_meter`, `press_card`, `card`, `wp_chart`, `player_card`, `rhythm_meter`, `summary`. |
| `anchor` | Pitch coordinates in metres (105 x 68, home attacks towards x = 105), for AR or tracking-linked graphics such as player tags. |
| `data` | The structured numbers behind the graphic, so partners can build their own visuals. |
| `copy` | Studio-ready text in every rendered language. Viewer apps can request any persona from `/api/matches/{s}/insights?persona=&lang=`. |
| `evidence` | Event IDs the claim is derived from. `GET /api/matches/{s}/events/{id}` returns the facts, model drivers and pitch control. |
| `verification` | Only `verified` cues are ever emitted on air. |
| `approval` | `auto`, `pending` (review mode: waiting in the producer console), `approved`, `rejected`, `expired`, `skipped`. Updates arrive as `cue_update` events. |

Stream events on `GET /api/matches/{session}/stream` (Server-Sent Events): `hello`, `state`,
`event`, `insight` (contains `cue`), `cue_update`, `trace`, `control`, `done`.
