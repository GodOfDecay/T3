"""The standalone chat socket both Track 3 agents serve their own page from.

The same wire contract every Portfolio 1 agent page speaks (the chat BFF,
`frontend/app/api/chat/route.ts`, bridges to it): one `user_message_with_files` frame
per turn; `stream_chunk` frames while the agent answers; then `stream_end` and a
terminal `activity_update{type: "complete"}` on EVERY path — without the terminal the
composer stays disabled and the turn never ends.

What each turn establishes before the graph runs, and why — every line of this list
was a bug in some Portfolio 1 wrapper before it was a line somewhere:

  identity    from the redeemed single-use ticket, never from the frame.
  access      the project from the frame is RESOLVED and checked: the caller is a
              member, the agent belongs to the project's TRACK, and the caller's role
              reaches the agent (`assert_agent_access_for_chat_on_track`).
  run         the per-project chat run for this stage, so what the agent records
              (the brief, the assessment) lands on a run the project's pages read.
  connector   the project's connector for THIS stage, bound for the turn only —
              the same adapter the Orchestrator's dispatch uses, so an agent reaches
              exactly the same tools standalone as it does orchestrated.
  consent     recomputed from THIS turn's message: a "yes" authorises one
              Consequential action, never every later turn.
  model       project-scoped BYOK, resolved in the graph's agent node with the
              project id carried in state. No env-key fallback.

And two rules about turns themselves, both copied from the Track 1 Development agent,
which found them the hard way (Lessons R31, R32):

  one at a time   a second turn for a session whose turn is still running is refused,
                  visibly, and ended properly. Two turns driving one checkpoint at once
                  produced duplicate replies and interleaved tool calls.
  cancellable     each turn runs as a tracked task, cancelled when its socket goes, so
                  an orphaned turn never keeps writing to a thread a new socket drives.
  delivered       the system prompt counts as delivered when it is IN THE THREAD'S
                  CHECKPOINT, not when a set in memory says so. The set said so before
                  the turn ran, so a failed first turn left the session without its
                  instructions until a restart; and after a restart the empty set
                  re-sent the prompt into a thread that already had it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)

_MAX_MESSAGE_BYTES = 50_000

#: (agent_id, session_id) of every turn running in this process, keyed by agent too. NOTE:
#: this does NOT make one session id on two agents two threads — in enterprise mode every
#: agent's checkpointer shares one Postgres store keyed by `thread_id` alone
#: (`config/checkpoint.py`). What keeps one agent's instructions out of another's reasoning
#: is `system_prompt_delivered` matching the system message to THIS agent.
_INFLIGHT: set[tuple[str, str]] = set()

STOPPED_NOTE = chr(10) * 2 + "_(stopped before it finished)_"

BUSY_MESSAGE = ("Still working on your previous message — please wait for it to finish "
                "before sending another.")


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) and b.get("type") == "text"
            else (b if isinstance(b, str) else "")
            for b in content
        )
    return ""


async def _send(websocket: WebSocket, payload: dict) -> None:
    from config.connection_manager import manager  # noqa: PLC0415

    await manager.send_personal_message(json.dumps(payload), websocket)


async def _finish(websocket: WebSocket, session_id: str, *, error: str | None = None) -> None:
    """The end of a turn, on every path. See the module docstring."""
    try:
        if error is not None:
            await _send(websocket, {"type": "agent_completed", "session_id": session_id,
                                    "success": False, "error": error})
        await _send(websocket, {"type": "stream_end", "session_id": session_id})
        await _send(websocket, {"type": "activity_update", "activity": {
            "id": str(uuid4()), "type": "complete", "session_id": session_id,
            "message": "Processing complete", "time": "Just now",
        }})
    except Exception:  # noqa: BLE001 — the peer may already be gone
        logger.debug("could not send the end of turn for session %s", session_id)


async def _chat_run(tenant_id: str, project_id: str, agent_id: str) -> str | None:
    """The project's chat run for this stage — one per project and stage, reused."""
    from config.ws_helper import set_run_id  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.services.chat_artifacts import _get_or_create_chat_run  # noqa: PLC0415

    set_run_id(None)  # never inherit a previous turn's run
    async with get_db_session_for_tenant(tenant_id) as session:
        run_id = await _get_or_create_chat_run(session, tenant_id, project_id, agent_id)
        await session.commit()
    return run_id


async def _run_config(session_id: str, tenant_id: str, user_id: str, project_id: str,
                      agent_id: str) -> dict:
    from shared.audit import AuditCallbackHandler  # noqa: PLC0415
    from shared.audit.service import audit_service  # noqa: PLC0415
    from shared.observability.callbacks import agent_trace  # noqa: PLC0415

    # THROUGH `agent_trace`, NOT `langfuse_langchain_extras` DIRECTLY.
    #
    # The attribution this passed was complete, so the drift guard
    # (tests/observability/test_trace_attribution.py) looked pedantic here. It was not:
    # `agent_trace` also resolves the project's LANGFUSE BINDING, which is what decides
    # WHICH Langfuse project the turn writes to. Without it these agents fall back to the
    # single default client, so Track 3's traces land in a shared bucket instead of their
    # own project — losing the per-project isolation migration 0057 exists to provide, and
    # losing it silently, because traces still arrive.
    #
    # It also resolves `workspace_id` from the project (so the lookup here is redundant)
    # and binds the run's client to a contextvar for agents that do not go through
    # LangChain.
    callbacks, metadata = await agent_trace(
        session_id=session_id,
        agent_type=agent_id,
        user_id=user_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    audit = AuditCallbackHandler(audit_service, run_id=session_id, tenant_id=tenant_id)
    return {"configurable": {"thread_id": session_id}, "recursion_limit": 100,
            "callbacks": [audit, *callbacks], "metadata": metadata}


def system_message_id(agent_id: str) -> str:
    """The id this agent's system message carries in the thread (a re-sent message with the
    same id replaces itself under `add_messages` rather than stacking up)."""
    return f"system:{agent_id}"


def _is_mine(message: Any, agent_id: str, system_prompt: str) -> bool:
    """THIS agent's system message: tagged with its id, or — for a thread started before
    messages were tagged — untagged and beginning with this agent's own prompt. Another
    agent's system message in a shared thread (enterprise checkpoints are keyed by
    thread id alone) is not this agent's instructions and does not count."""
    if not isinstance(message, SystemMessage):
        return False
    if getattr(message, "id", None) == system_message_id(agent_id):
        return True
    head = (system_prompt or "")[:200]
    return not getattr(message, "id", None) and bool(head) and str(message.content).startswith(head)


async def system_prompt_delivered(graph: Any, session_id: str, initialized: set[str], *,
                                  agent_id: str = "", system_prompt: str = "") -> bool:
    """Is THIS agent's system prompt already in this session's thread? See the module docstring.

    `initialized` is only a cache of "yes" answers. A thread whose checkpoint cannot be
    read counts as not delivered: sending the prompt twice is recoverable, a turn with
    no instructions at all is not.
    """
    if session_id in initialized:
        return True
    try:
        snapshot = await graph.aget_state({"configurable": {"thread_id": session_id}})
        messages = (getattr(snapshot, "values", None) or {}).get("messages") or []
    except Exception:  # noqa: BLE001
        logger.warning("could not read the checkpoint of session %s; sending the system prompt", session_id)
        return False
    if any(_is_mine(m, agent_id, system_prompt) for m in messages):
        initialized.add(session_id)
        return True
    return False


async def run_turn(
    websocket: WebSocket,
    message: dict,
    *,
    agent_id: str,
    label: str,
    graph: Any,
    system_prompt: str,
    user_id: str,
    tenant_id: str,
    initialized: set[str],
) -> None:
    """One chat turn, or a visible refusal when this session already has one running."""
    session_id = str(message.get("session_id") or uuid4())
    message["session_id"] = session_id
    key = (agent_id, session_id)
    if key in _INFLIGHT:
        await _send(websocket, {"type": "stream_chunk", "content": BUSY_MESSAGE, "session_id": session_id})
        await _finish(websocket, session_id)
        return
    _INFLIGHT.add(key)
    try:
        await _turn(websocket, message, agent_id=agent_id, label=label, graph=graph,
                    system_prompt=system_prompt, user_id=user_id, tenant_id=tenant_id,
                    initialized=initialized)
    finally:
        _INFLIGHT.discard(key)


async def _turn(
    websocket: WebSocket,
    message: dict,
    *,
    agent_id: str,
    label: str,
    graph: Any,
    system_prompt: str,
    user_id: str,
    tenant_id: str,
    initialized: set[str],
) -> None:
    """The turn itself. Never raises into the socket loop; always ends the turn."""
    from agents_orchestrator.orchestrator2 import connectors, mcp  # noqa: PLC0415
    from config.agent_context import build_agent_input_text  # noqa: PLC0415
    from config.ws_helper import (  # noqa: PLC0415
        reset_session_id, set_consequential_approved, set_orchestrator_run,
        set_project_id, set_provider_kind, set_run_id, set_session_id, set_tenant_id,
        set_user_id,
    )
    from shared.authz.agent_access import assert_agent_access_for_chat_on_track  # noqa: PLC0415
    from shared.authz.consequential import is_approval_message  # noqa: PLC0415
    from shared.db import get_db_session_for_tenant  # noqa: PLC0415
    from shared.errors import classify_error  # noqa: PLC0415
    from shared.services.conversation_service import persist_turn  # noqa: PLC0415
    from shared.services.skill_runtime import skill_context_scope  # noqa: PLC0415
    from shared.services.standalone_prompt import (  # noqa: PLC0415
        resolve_agent_skills,
        resolve_agent_turn,
    )
    from shared.tools.document_tools import (  # noqa: PLC0415
        attachment_message_contents,
        attachment_paths_from_context,
    )

    session_id = str(message.get("session_id") or uuid4())
    context = message.get("pipeline_context") if isinstance(message.get("pipeline_context"), dict) else {}
    task_intent = str(message.get("task_intent") or message.get("text") or "")
    requested_project = str(context.get("project_id") or message.get("project_id") or "")

    # ── access: member, track, reach ─────────────────────────────────────────
    try:
        if not requested_project:
            raise HTTPException(status_code=400, detail=(
                f"Open the {label} from a project — this turn named no project."))
        async with get_db_session_for_tenant(tenant_id) as db:
            project_id = await assert_agent_access_for_chat_on_track(
                db, tenant_id=tenant_id, project_id=requested_project,
                user_id=str(user_id), agent_id=agent_id,
            )
    except HTTPException as exc:
        await _send(websocket, {"type": "agent_response", "agent_name": "Error Agent",
                                "message": str(exc.detail), "session_id": session_id})
        await _finish(websocket, session_id, error=str(exc.detail))
        return
    except Exception as exc:  # noqa: BLE001 — cannot prove access ⇒ refuse
        logger.exception("%s: access check failed", agent_id)
        await _finish(websocket, session_id, error=classify_error(exc, "access check"))
        return

    token = set_session_id(session_id)
    set_user_id(str(user_id))
    set_tenant_id(tenant_id or None)
    set_project_id(project_id)
    set_orchestrator_run(False)
    set_consequential_approved(is_approval_message(task_intent))
    reply_parts: list[str] = []
    error: str | None = None
    stopped = False
    try:
        set_run_id(await _chat_run(tenant_id, project_id, agent_id))
        try:
            set_provider_kind(await connectors.connector_kind_for(
                agent_id, tenant_id=tenant_id, project_id=project_id))
        except Exception:  # noqa: BLE001 — a refinement, never fatal
            pass

        messages: list[Any] = []
        if not await system_prompt_delivered(graph, session_id, initialized,
                                             agent_id=agent_id, system_prompt=system_prompt):
            prompt, _skills = await resolve_agent_turn(agent_id, system_prompt, tenant_id or None, project_id)
            messages.append(SystemMessage(content=prompt or system_prompt, id=system_message_id(agent_id)))
        from config.ws_helper import get_run_id  # noqa: PLC0415

        upstream = await upstream_from_pages(project_id, tenant_id, agent_id,
                                             consumer_run_id=get_run_id(), consumed_by=str(user_id),
                                             consumer_session=session_id)
        if upstream:
            messages.append(HumanMessage(content=(
                "--- WORK ALREADY ON THIS PROJECT ---\n" + upstream + "\n--- END ---")))
        messages.append(HumanMessage(content=build_agent_input_text(
            conversation_context=message.get("conversation_context"),
            task_intent=task_intent, pipeline_context=context, pipeline_sections=(),
        ) or task_intent))
        files = [f.get("path") for f in (message.get("files") or []) if isinstance(f, dict) and f.get("path")]
        for content in attachment_message_contents(attachment_paths_from_context(context) + files):
            messages.append(HumanMessage(content=content))

        await persist_turn(session_id, "user", task_intent, tenant_id=tenant_id or None,
                           author_id=str(user_id), artifact_refs=context.get("attachments") or None)

        state = {"messages": messages, "tenant_id": tenant_id, "project_id": project_id,
                 "model_id": message.get("model_id"), "offering_id": message.get("offering_id")}
        config = await _run_config(session_id, tenant_id, str(user_id), project_id, agent_id)
        skills = await resolve_agent_skills(agent_id, tenant_id or None, project_id)
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(connectors.bound_connector(
                agent_id, tenant_id=tenant_id, project_id=project_id, owner_id=str(user_id)))
            await stack.enter_async_context(mcp.bound_mcp_tools(
                agent_id, tenant_id=tenant_id, project_id=project_id, owner_id=str(user_id)))
            await stack.enter_async_context(skill_context_scope(agent_id, skills))
            async for chunk, _meta in graph.astream(state, stream_mode="messages", config=config):
                if isinstance(chunk, ToolMessage):
                    continue  # a tool's output is not the agent speaking
                text = _text(getattr(chunk, "content", None))
                if text:
                    reply_parts.append(text)
                    await _send(websocket, {"type": "stream_chunk", "content": text,
                                            "session_id": session_id})
        if reply_parts:
            initialized.add(session_id)  # delivered: the turn that carried it completed
        else:
            error = "The agent finished without producing a reply. Try again, or rephrase."
            await _send(websocket, {"type": "agent_response", "agent_name": "Error Agent",
                                    "message": error, "session_id": session_id})
    except WebSocketDisconnect:
        # The turn runs in its own task now (R31), so re-raising would only surface as
        # "Task exception was never retrieved". The socket loop cancels its turns itself.
        logger.info("%s: the socket went during a turn (session=%s)", agent_id, session_id)
    except asyncio.CancelledError:
        stopped = True
        raise
    except Exception as exc:  # noqa: BLE001 — a failed turn is shown, never silent
        logger.exception("%s turn failed (session=%s)", agent_id, session_id)
        error = classify_error(exc, "agent processing")
        await _send(websocket, {"type": "agent_response", "agent_name": "Error Agent",
                                "message": f"An error occurred: {error}", "session_id": session_id})
    finally:
        if reply_parts:
            # A reply cut off by a cancel is kept, but never passed off as a complete one.
            text = "".join(reply_parts) + (STOPPED_NOTE if stopped else "")
            await persist_turn(session_id, "agent", text,
                               tenant_id=tenant_id or None, author_id=agent_id,
                               model=message.get("model_id"))
        await _finish(websocket, session_id, error=error)
        try:
            reset_session_id(token)
        except Exception:  # noqa: BLE001
            pass
        set_user_id("")
        set_tenant_id(None)
        set_project_id(None)
        set_run_id(None)
        set_consequential_approved(False)
        set_provider_kind("")
        from agents_orchestrator.modernization_common.versions import reset_built_from  # noqa: PLC0415

        reset_built_from()


INVALID_TICKET_REASON = (
    '{"error": "invalid_or_expired_ticket", '
    '"detail": "Provide a valid single-use ticket from POST /auth/ws-ticket"}'
)


def tenant_mismatch(websocket: WebSocket, claims: dict) -> bool:
    """Enterprise mode: the socket's `tenant_id` query param must match the ticket's."""
    from config.env import AGENT_RUNTIME_MODE  # noqa: PLC0415

    if AGENT_RUNTIME_MODE != "enterprise":
        return False
    expected = websocket.query_params.get("tenant_id", "")
    return bool(expected) and claims.get("tenant_id", "") != expected


async def serve_agent_socket(
    websocket: WebSocket, claims: dict, *, agent_id: str, label: str, graph: Any,
    system_prompt: str, initialized: set[str],
) -> None:
    """The socket loop, one turn per frame, for a caller whose ticket the ENDPOINT
    has already redeemed.

    Redemption stays in each endpoint on purpose: the boot scan's audit
    (`tests/test_ws_route_coverage.py`) reads every socket handler and requires it to
    redeem its ticket before accepting, so the authentication decision is visible
    where the route is declared rather than one call away.
    """
    from config.connection_manager import manager  # noqa: PLC0415
    from config.websocket_utils import set_websocket_context  # noqa: PLC0415

    await manager.connect(websocket)
    user_id = str(claims.get("user_id", ""))
    tenant_id = str(claims.get("tenant_id", "") or "")
    # This connection's running turns, so a dropped socket cancels its orphan (R31).
    turns: set[asyncio.Task] = set()

    def _cancel_turns() -> None:
        for task in list(turns):
            if not task.done():
                task.cancel()

    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw.encode()) > _MAX_MESSAGE_BYTES:
                await _send(websocket, {"type": "error", "message": "Message too large (max 50 KB)."})
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {"type": "error", "message": "Malformed message."})
                continue
            session_id = str(message.get("session_id") or uuid4())
            message["session_id"] = session_id
            manager.register_session(websocket, session_id)
            set_websocket_context(manager, session_id)
            if message.get("type") == "user_message_with_files":
                task = asyncio.create_task(run_turn(
                    websocket, message, agent_id=agent_id, label=label, graph=graph,
                    system_prompt=system_prompt, user_id=user_id, tenant_id=tenant_id,
                    initialized=initialized))
                turns.add(task)
                task.add_done_callback(turns.discard)
            elif message.get("type") == "session_cleanup":
                initialized.discard(session_id)
            else:
                await _send(websocket, {"type": "echo"})
    except WebSocketDisconnect:
        _cancel_turns()
        manager.disconnect(websocket)
    except RuntimeError as exc:
        # The chat BFF closes its per-turn socket once the turn ends; Starlette reports
        # that as RuntimeError("WebSocket is not connected"). A normal end, not a fault.
        if "not connected" not in str(exc).lower() and "disconnect" not in str(exc).lower():
            logger.error("%s socket error: %s", agent_id, exc)
        _cancel_turns()
        manager.disconnect(websocket)
    except Exception:  # noqa: BLE001
        logger.exception("%s socket closed on an unexpected error", agent_id)
        _cancel_turns()
        manager.disconnect(websocket)


#: The page whose versions feed each Track 3 input artifact: (producing stage, noun).
_UPSTREAM_STAGE = {"migration_intent_payload": ("requirements_modernization", "Migration-intent brief"),
                   "discovery_artifacts": ("discovery", "Dependency and Risk assessment")}


#: (agent, session, producing stage) → the version this chat session already recorded
#: reading. Without it every turn wrote another `artifact_consumptions` row for the same
#: read, and "Read by" grew one line per chat message (Phase B review). Per process, and
#: bounded: a forgotten entry only means one more (correct) row.
_RECORDED: dict[tuple[str, str, str], object] = {}
_RECORDED_CAP = 10_000


async def upstream_from_pages(project_id: str, tenant_id: str, agent_id: str, *,
                              consumer_run_id: str | None = None,
                              consumed_by: str | None = None,
                              consumer_session: str | None = None) -> str:
    """The work already on the AGENT PAGES that this agent builds on — for Discovery, the
    brief on the Migration Intent page; for Target Architecture, the brief and the assessment
    (each read, pinned and recorded on its own).

    FROM THE PAGES' VERSIONS, NOT FROM RUNS. The run columns are written by Orchestrator
    conversations too, and an Orchestrator conversation is self-contained: a brief
    captured there must not turn up as the context of a page's chat. Versions are only
    frozen by the pages, so reading them keeps the two apart.

    Which version, and what is RECORDED:
      published          through `read_upstream` — the platform's one reader of approved
                         work — so the read is recorded in `artifact_consumptions`
                         (who read which version, for which run). This is the evidence
                         "what did this assessment build on" is answered from later.
      none published,    the newest draft, labelled "not yet approved" (not recorded: a
        not enforced     draft is not a version anyone signed off).
      none published,    said, not silently absent: "no approved brief yet", so the agent
        enforced         tells the user rather than acting as if the stage never ran.
    """
    from config.agent_registry import AGENT_REGISTRY  # noqa: PLC0415
    from config.context_broker import _ARTIFACT_FORMATTERS  # noqa: PLC0415

    definition = AGENT_REGISTRY.get(agent_id)
    wanted = [a for a in (definition.input_artifacts if definition else []) if a in _UPSTREAM_STAGE]
    if not (wanted and project_id and tenant_id):
        return ""
    parts: list[str] = []
    try:
        from shared.db import get_db_session_for_tenant  # noqa: PLC0415
        from shared.services import artifact_versions as svc  # noqa: PLC0415

        async with get_db_session_for_tenant(tenant_id) as db:
            enforced = await svc.enforcement_enabled(db, project_id)
            for artifact in wanted:
                stage, noun = _UPSTREAM_STAGE[artifact]
                formatter = _ARTIFACT_FORMATTERS.get(artifact)
                # Record a read once per session and version (see `_RECORDED`).
                key = (agent_id, consumer_session or "", stage)
                peek = await svc.latest_published(db, project_id, stage)
                seen = peek.version if peek is not None else "grant"
                record = consumer_session is None or _RECORDED.get(key) != seen
                read = await svc.read_upstream(
                    db, tenant_id=tenant_id, project_id=project_id, stage=stage,
                    consumer_stage=agent_id, consumer_run_id=consumer_run_id,
                    consumed_by=consumed_by, record=record,
                )
                if read.payload and record and consumer_session:
                    if len(_RECORDED) >= _RECORDED_CAP:
                        _RECORDED.clear()
                    _RECORDED[key] = seen
                if read.payload:
                    from agents_orchestrator.modernization_common.versions import note_input  # noqa: PLC0415

                    # A read by consumption grant is of an UNPUBLISHED version: say so, frozen.
                    note_input(artifact=artifact, stage=stage, version=read.version,
                               status="granted" if read.via_grant else "published")
                    state = "approved by exception (consumption grant)" if read.via_grant else "approved"
                    body = formatter(read.payload) if formatter else str(read.payload)
                    parts.append(f"{noun} v{read.version} ({state}):\n{body}")
                    continue
                if enforced:
                    parts.append(f"{noun}: none approved yet. This project only builds on approved "
                                 f"work, so say that the {noun.lower()} must be approved first; do not use a draft.")
                    continue
                row = await svc.latest_version(db, project_id, stage)
                if row is not None and row.payload:
                    from agents_orchestrator.modernization_common.versions import note_input  # noqa: PLC0415

                    note_input(artifact=artifact, stage=stage, version=row.version, status=row.status)
                    body = formatter(row.payload) if formatter else str(row.payload)
                    parts.append(f"{noun} v{row.version} ({row.status}, not yet approved):\n{body}")
            # The consumption rows are committed when this session closes cleanly
            # (`get_db_session_for_tenant` commits on exit) — verified by mutation: an
            # explicit commit here changed nothing.
    except Exception:  # noqa: BLE001 — context is a help, never a reason to fail the turn
        logger.exception("modernization: reading upstream versions failed (project %s)", project_id)
        return ("--- NOTE ---\nThe approved work this agent builds on could not be read for this "
                "turn. Say so if it matters; do not treat it as 'nothing recorded yet'.")
    return "\n\n".join(parts)
