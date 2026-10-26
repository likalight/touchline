# Ten-minute user test

Use the [offline observation form](user-test-kit.html) for the current judge journey.
Download it and open it locally. It collects anonymous IDs, consent, task outcomes,
elapsed time, participant explanations and ratings, then exports JSON on this device.
No observations have been collected yet. The blank form is a preparation artifact.

Run this with 3 to 5 people: at least one casual fan, one person who follows tactics closely, and,
if you can, one person who uses a screen reader. Use the live app (deployed URL or `localhost:8000`).

## Before you start

* Open the app on the demo match. Say: "This is a fictional match with made-up clubs. Think aloud;
  there are no wrong answers. We are testing the app, not you."
* Note each person's profile: casual fan, tactics fan, or accessibility user.

## Tasks (about 90 seconds each)

| # | Task | What to watch for |
|---|---|---|
| 1 | "Make the app about your team." | Do they find My club, Follow player or the Players tab favourites without help? |
| 2 | "A goal just went in. Why did it happen?" | Do they read the card, open an evidence chip, or ask the analyst? |
| 3 | "Switch to how a TV pundit would see this." | Do they find the Analyst view, and does the copy feel different? |
| 4 | "Turn on the commentary." | Can they tell the two voices apart? Are the captions readable? |
| 5 | "Get your own highlights." | Do they reach My Match and play the 3D reel? |
| 6 | "Ask the analyst a question you care about." | Is the answer correct and specific to the match? |

During the session, ask them to press **Useful** or **Not for me** on cards as they go.

## Five questions afterwards (1 = strongly disagree, 5 = strongly agree)

1. I understood why the moments on screen mattered.
2. The app felt made for the way I follow football.
3. I trusted the numbers I saw.
4. I would use this while watching a real match.
5. It was easy to find what I wanted.

Plus one open question: "What would you change first?"

## Record the results here

| Person | Profile | Q1 | Q2 | Q3 | Q4 | Q5 | Tasks done unaided (of 6) | Change first |
|---|---|---|---|---|---|---|---|---|
| P1 | | | | | | | | |
| P2 | | | | | | | | |
| P3 | | | | | | | | |

Viewer feedback from the app: `GET /api/matches/demo/feedback` (useful rate by persona and moment type).

## Judge-journey validation (record real participants only)

Status: **not conducted for this revision**. Recruit 3–5 consenting participants; do not substitute
simulated personas or automated browser tests for human results. Use anonymous participant IDs
and record only the observations needed for the study.

For each task, record success without assistance, elapsed seconds, any assistance and the
participant's explanation in their own words:

1. Start Judge Mode and explain what happened after the first goal.
2. Find the connection between the earlier mistake and the later equalizer.
3. Compare Fan and Analyst and say how the versions differ.
4. Locate a source fact and download its receipt.
5. Use keyboard-only navigation to open and close the receipt.

Report counts as “n of N”, including failures. Distinguish software browser checks from this
study. With a small convenience sample, describe observations rather than claiming population
impact. For a broadcaster pilot, separately measure producer acceptance, editing time per cue
and correction rate in a preview-only workflow before any on-air use.
