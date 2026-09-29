"""Target Architecture — standalone chat socket (Track 3 — Code Modernization, Phase E).

Mounted at `/sdlc/agent/design-modernization`. The ticket is redeemed HERE, before the
handshake is accepted; the turn contract, access (member, track, reach), run, connector and
upstream reads after that are shared with Track 3's other agents:
`modernization_common/standalone.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket

from config.auth.ws_ticket import redeem_ws_ticket as _redeem_ws_ticket

design_modernization_router = APIRouter()

#: Sessions whose system message has been sent (a cache; the checkpoint is the truth).
_initialized_sessions: set[str] = set()


@design_modernization_router.websocket("/ws")
async def design_modernization_ws(websocket: WebSocket) -> None:
    from agents_orchestrator.design_modernization_agent.agents.architect import (  # noqa: PLC0415
        AGENT_ID,
        DESIGN_MODERNIZATION_SYS_MESSAGE,
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
        websocket, claims, agent_id=AGENT_ID, label="Target Architecture agent", graph=app,
        system_prompt=DESIGN_MODERNIZATION_SYS_MESSAGE, initialized=_initialized_sessions,
    )
