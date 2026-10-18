"""A2A (Agent2Agent) interop: exposes AskTheAnalyst to other agents.

Any A2A client - another studio's agent, a Copilot agent, Agent Framework's
`A2AAgent` - can discover the card at /.well-known/agent-card.json and send a
message to /a2a. Questions are answered from the live demo session, with cited
event IDs, by the same tool-grounded agent the UI uses.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

log = logging.getLogger("touchline.a2a")


def mount_a2a(app, get_session: Callable, base_url: str) -> bool:
    try:
        from a2a.helpers.proto_helpers import new_text_message
        from a2a.server.agent_execution import AgentExecutor, RequestContext
        from a2a.server.events import EventQueue
        from a2a.server.request_handlers import DefaultRequestHandler
        from a2a.server.routes.agent_card_routes import create_agent_card_routes
        from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
        from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
        from a2a.server.tasks import InMemoryTaskStore
        from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
    except Exception as exc:  # pragma: no cover - optional dependency
        log.warning("A2A disabled: %s", exc)
        return False

    class AnalystExecutor(AgentExecutor):
        async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
            question = context.get_user_input() or "What's happening in the match?"
            session = get_session()
            if session is None:
                answer = "No live match is running."
            else:
                from touchline.safety import safety

                refused = await safety.screen_question(question)  # same Prompt Shields as fan questions
                res = ({"answer": "I can only help with questions about this match.", "citations": []} if refused
                       else await session.ask_agent.ask(question))
                cites = f" Evidence: {', '.join(res['citations'][:6])}." if res.get("citations") else ""
                answer = f"[{session.meta.match_id} {session.state.minute}'] {res['answer']}{cites}"
            await event_queue.enqueue_event(new_text_message(answer, context_id=context.context_id, task_id=context.task_id))

        async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
            return None

    card = AgentCard(
        name="Touchline Match Analyst",
        description=("Explainable match intelligence for a live synthetic football match: scores, xG, win probability, "
                     "momentum, control-vs-chaos, player performance and why key moments mattered, with event-ID citations."),
        version=os.getenv("TOUCHLINE_VERSION", "1.0.0"),
        supported_interfaces=[AgentInterface(url=f"{base_url.rstrip('/')}/a2a", protocol_binding="JSONRPC")],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(id="match-qa", name="Live match Q&A", description="Answer questions about the live match with cited evidence.",
                       tags=["football", "analytics", "explainability"],
                       examples=["Why did Kestrel Bay score?", "Who is the standout player?", "What is the win probability?"]),
            AgentSkill(id="player-lookup", name="Player performance", description="Per-player passing difficulty, xG, xT, speed and rating.",
                       tags=["player", "stats"], examples=["How is the number 9 playing?"]),
        ],
    )
    handler = DefaultRequestHandler(agent_executor=AnalystExecutor(), task_store=InMemoryTaskStore(), agent_card=card)
    add_a2a_routes_to_fastapi(app, agent_card_routes=create_agent_card_routes(card),
                              jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/a2a", enable_v0_3_compat=True))
    return True
