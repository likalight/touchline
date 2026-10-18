# Ten-minute user test

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
