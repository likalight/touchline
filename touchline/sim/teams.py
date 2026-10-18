"""Fictional clubs and squads. No real clubs, players or Premier League data are used."""
from __future__ import annotations

import random

from touchline.schema import PITCH_L, PITCH_W, Player, Team

# 4-3-3 anchor positions for a side attacking towards x = 105 (in the "attacking frame").
FORMATION_433 = [
    ("GK", 1, (5.0, 34.0)),
    ("RB", 2, (32.0, 10.0)),
    ("RCB", 5, (26.0, 26.0)),
    ("LCB", 6, (26.0, 42.0)),
    ("LB", 3, (32.0, 58.0)),
    ("DM", 4, (42.0, 34.0)),
    ("RCM", 8, (52.0, 22.0)),
    ("LCM", 10, (52.0, 46.0)),
    ("RW", 7, (70.0, 10.0)),
    ("ST", 9, (76.0, 34.0)),
    ("LW", 11, (70.0, 58.0)),
]

FIRST = [
    "Mateo", "Kofi", "Liam", "Arjun", "Yusuf", "Theo", "Ibrahim", "Lucas", "Kenji", "Rafael",
    "Oscar", "Samir", "Elias", "Tomas", "Niko", "Jonah", "Diego", "Malik", "Felix", "Hugo",
    "Andre", "Callum", "Emeka", "Joao", "Leon", "Marco", "Owen", "Ravi", "Sven", "Tariq",
]
LAST = [
    "Okafor", "Hale", "Moreau", "Varga", "Lindqvist", "Brennan", "Achterberg", "Silva", "Navarro",
    "Mensah", "Kowalski", "Ferreira", "Adeyemi", "Calloway", "Dubois", "Rasmussen", "Petrov",
    "Quinn", "Takahashi", "Esposito", "Haddad", "Larsen", "Mbeki", "Novak", "Ortega", "Pryce",
    "Reyes", "Sato", "Thorne", "Vance", "Whitlock", "Yilmaz", "Zielinski", "Abara", "Castell",
]

CLUBS = {
    "home": dict(name="Kestrel Bay FC", short="KES", color="#1f6feb"),
    "away": dict(name="Ironmoor Athletic", short="IRM", color="#e5484d"),
}

PROFILE = {
    # position: (pace m/s, passing, finishing, defending)
    "GK": (6.5, 0.70, 0.05, 0.60),
    "RB": (8.6, 0.74, 0.20, 0.72), "LB": (8.6, 0.74, 0.20, 0.72),
    "RCB": (7.9, 0.72, 0.18, 0.82), "LCB": (7.9, 0.72, 0.18, 0.82),
    "DM": (7.8, 0.84, 0.30, 0.76),
    "RCM": (8.1, 0.83, 0.42, 0.62), "LCM": (8.1, 0.85, 0.45, 0.60),
    "RW": (9.3, 0.76, 0.58, 0.35), "LW": (9.3, 0.76, 0.58, 0.35),
    "ST": (9.0, 0.70, 0.72, 0.30),
}


def build_team(side: str, rng: random.Random, used: set[str] | None = None) -> Team:
    """`used` is shared by both squads so no two players in a match share a name."""
    club = CLUBS[side]
    used = used if used is not None else set()
    players = []
    for pos, num, _ in FORMATION_433:
        while True:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        pace, pas, fin, de = PROFILE[pos]
        jitter = lambda v, s=0.05: max(0.05, min(0.97, v + rng.uniform(-s, s)))  # noqa: E731
        players.append(Player(
            id=f"{side[0]}{num}", team=side, name=name, number=num, position=pos,
            pace=round(pace + rng.uniform(-0.4, 0.4), 2), passing=round(jitter(pas), 3),
            finishing=round(jitter(fin, 0.08), 3), defending=round(jitter(de), 3),
        ))
    return Team(side=side, formation="4-3-3", players=players, **club)


def anchor(pos_index: int, side: str) -> tuple[float, float]:
    x, y = FORMATION_433[pos_index][2]
    if side == "away":
        return PITCH_L - x, PITCH_W - y
    return x, y
