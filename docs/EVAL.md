# Evaluation

`python scripts/evaluate.py --matches 12 --gate` on 12 unseen synthetic matches
(seeds 5000+, half of them through a 10% faulty feed), deterministic path. Runs in CI on every push.

| Metric | Result | Gate |
|---|---|---|
| Insights verified by the FactChecker | 100.0% | 100% |
| Goals explained | 100.0% (31 goals) | 100% |
| Citations resolving to a real, non-future event | 0 errors | 0 |
| Renders per insight (4 personas x 4 languages) | 16, 0 template leaks | 0 leaks |
| Moments explained per match | 55.9 | - |
| Agent pipeline latency per moment, p50 / p95 | 8.21 / 12.3 ms | p95 < 250 ms |
| Event -> state update, p50 / p95 | 0.14 / 0.24 ms | p95 < 5 ms |
| Faulty feed recovered exactly-once, in order | 100% of matches | 100% |


Moment kinds explained across the run:

| Kind | Count |
|---|---|
| line_break | 111 |
| momentum | 85 |
| sprint | 74 |
| hard_pass | 73 |
| phase | 56 |
| long_carry | 37 |
| standout | 36 |
| press | 32 |
| goal | 31 |
| saves | 28 |
| rhythm | 24 |
| card_yellow | 23 |
| half_time | 12 |
| full_time | 12 |
| chance_saved | 11 |
| chance_missed | 10 |
| brace | 9 |
| wp_swing | 4 |
| hat_trick | 2 |
| card_red | 1 |

Gate: PASSED. Wall time 10.7 s.

## Auto-eventing from video

`python -m touchline.vision.autoevent --seed 7 --from-min 0 --minutes 45` renders the first half as a noisy
420x272 top-down feed at 10 fps (27,001 frames). The tracker only sees the pixels. It segments the ball and
both kits by colour, tracks 22 players with nearest-neighbour association (seeded once from the kick-off line-up),
assigns ball ownership, and emits passes and shots. The results are matched against the simulator's ground truth:

| Metric | Result |
|---|---|
| Passes: precision / recall | 0.879 / 0.747 (328 of 439 matched) |
| Passer and receiver both identified correctly | 89% |
| Ball-speed error (mean absolute) | 2.14 km/h |
| Pass-distance error (mean absolute) | 2.11 m |
| Shots: recall | 0.8 (8 of 10) |
