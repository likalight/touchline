"""Canonical data contracts shared by every agent.

Coordinates: metres on a 105 x 68 pitch, origin at the home team's left corner flag.
The home side always attacks towards x = 105 (the feed is pre-normalised, like most
commercial event feeds).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

PITCH_L = 105.0
PITCH_W = 68.0

EventType = Literal[
    "kickoff", "pass", "carry", "dribble", "pressure", "tackle", "interception",
    "shot", "save", "goal", "foul", "card", "corner", "out", "half_time", "full_time",
]


class Player(BaseModel):
    id: str
    team: Literal["home", "away"]
    name: str
    number: int
    position: str
    pace: float  # top speed m/s
    passing: float  # 0..1
    finishing: float  # 0..1
    defending: float  # 0..1


class Team(BaseModel):
    side: Literal["home", "away"]
    name: str
    short: str
    color: str
    formation: str
    players: list[Player]


class Event(BaseModel):
    """One synthetic, football-realistic match event (the ingest contract)."""

    id: str
    seq: int
    match_id: str
    t: float = Field(description="seconds since kick-off of the match clock")
    period: Literal[1, 2]
    minute: int
    type: EventType
    team: Optional[Literal["home", "away"]] = None
    player_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    outcome: Optional[str] = None
    target_id: Optional[str] = None
    qualifiers: dict = Field(default_factory=dict)
    # Lightweight tracking snapshot at the moment of the event: player_id -> [x, y]
    frame: Optional[dict[str, list[float]]] = None


class MatchMeta(BaseModel):
    match_id: str
    competition: str
    venue: str
    home: Team
    away: Team
    seed: int
    synthetic: bool = True
