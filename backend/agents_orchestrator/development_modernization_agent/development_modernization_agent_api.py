"""Migration Development — standalone chat socket (Track 3 — Code Modernization, Phase H).

Mounted at `/sdlc/agent/development-modernization`. The ticket is redeemed HERE, before the handshake is
accepted; the turn contract, access (member, track, reach), run, connector and upstream reads after
that are shared with Track 3's other agents: `modernization_common/standalone.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket

from config.auth.ws_ticket import redeem_ws_ticket as _redeem_ws_ticket

development_modernization_router = APIRouter()

#: Sessions whose system message has been sent (a cache; the checkpoint is the truth).
_initialized_sessions: set[str] = set()


@development_modernization_router.websocket("/ws")
async def development_modernization_ws(websocket: WebSocket) -> None:
    from agents_orchestrator.development_modernization_agent.agents.developer import (  # noqa: PLC0415
        AGENT_ID,
        MIGRATION_DEVELOPMENT_SYS_MESSAGE,
        app,
    )
    from agents_orchestrator.modernization_common.standalone import (  # noqa: PLC0415
        INVALID_TICKET_REASON,
        serve_agent_socket,
        tenant_mismatch,
    )

    ticket = websocket.query_params.get("ticket", "")
    claims = await _redeem_ws_ticket(ticket) if ticket else None
    if claims is None:
        await websocket.close(code=4401, reason=INVALID_TICKET_REASON)
        return
    if tenant_mismatch(websocket, claims):
        await websocket.close(code=4403, reason='{"error": "tenant_mismatch"}')
        return

    await serve_agent_socket(
        websocket, claims, agent_id=AGENT_ID, label="Migration Development agent", graph=app,
        system_prompt=MIGRATION_DEVELOPMENT_SYS_MESSAGE, initialized=_initialized_sessions,
    )
