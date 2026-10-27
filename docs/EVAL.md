# Evaluation

`python scripts/evaluate.py --matches 12 --gate` on 12 unseen synthetic matches
(seeds 5000+, half of them through a 10% faulty feed), deterministic path. The CI workflow runs it on every push.

Observed 2026-10-27T17:15:29.642437+00:00. Git HEAD `103713674de92570c613e9a07460d34d3c101c4a`; dirty working tree: `True`.
Simulator SHA-256: `b7570cd0c19b2b462d85e23a113bcbb31b96d976da8e76ae4d16448967d27695`. Frozen model artifact SHA-256: `e2f64797a51e6362240ea1846a907b97eb16bc0a2d9e82b0bf31077af5eed142`.
This reruns the pipeline with the frozen models; it does not refit or independently recalibrate them. A verified rate measures the implemented checks, not universal semantic correctness.

| Metric | Result | Gate |
|---|---|---|
| Insights verified by the FactChecker | 100.0% | 100% |
| Goals explained | 100.0% (28 goals) | 100% |
| Citations resolving to a real, non-future event | 0 errors | 0 |
| Renders per insight (4 personas x 4 languages) | 16, 0 template leaks | 0 leaks |
| Moments explained per match | 60.8 | - |
| Agent pipeline latency per moment, p50 / p95 | 5.82 / 8.56 ms | p95 < 250 ms |
| Event -> state update, p50 / p95 | 0.37 / 1.41 ms | p95 < 5 ms |
| Faulty feed recovered exactly-once, in order | 100% of matches | 100% |


Moment kinds explained across the run:

| Kind | Count |
|---|---|
| line_break | 116 |
| momentum | 87 |
| sprint | 71 |
| hard_pass | 67 |
| phase | 62 |
| long_carry | 38 |
| standout | 36 |
| goal | 28 |
| press | 28 |
| saves | 28 |
| story_duel | 25 |
| card_yellow | 24 |
| rhythm | 23 |
| story_channel | 14 |
| chance_missed | 14 |
| story_fatigue | 13 |
| half_time | 12 |
| full_time | 12 |
| chance_saved | 10 |
| brace | 8 |
| story_waste | 6 |
| wp_swing | 3 |
| hat_trick | 2 |
| story_keeper | 2 |
| card_red | 1 |

Storyline callbacks woven into live insights (match-long memory): s.error 11, s.comeback 11, s.run_of_play 2.

Gate: PASSED. Wall time 31.0 s.

## Auto-eventing from video (top-down feed)

`python -m touchline.vision.autoevent --seed 7 --from-min 0 --minutes 45`
renders the match as a noisy 420x272 feed at 10 fps (27,001 frames). The detector sees only pixels.

| Metric | Result |
|---|---|
| Passes: precision / recall | 0.879 / 0.747 (328 of 439) |
| Passer and receiver both identified | 89% |
| Ball-speed error (mean absolute) | 2.14 km/h |
| Pass-distance error (mean absolute) | 2.11 m |
| Shots: recall | 0.8 (8 of 10) |

## Computer vision from the broadcast camera (experimental)

`python -m touchline.vision.broadcast_cv` renders the angled TV view (960x540, 1,185 frames) and maps
pixels back to the pitch through the calibrated camera (pan telemetry only).

| Metric | Result |
|---|---|
| Player localisation error, p50 / p90 | **0.43 m / 1.09 m** over 17,194 detections |
| Ball on the ground located within 1 m | 46% of frames |
| Passes detected: precision / recall (recall on passes fully in shot) | 1.0 / 0.174 (0.235) |

Player positions from the angled camera are reliable. Ball tracking from that angle (small, fast, often
airborne or occluded) is the open problem, so pass detection from the broadcast view is experimental; the
top-down detector above is the one we rely on.
