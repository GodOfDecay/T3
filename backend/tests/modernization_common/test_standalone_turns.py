"""The Track 3 chat shell's turn rules (R31, R32): one turn per session at a time, turns
cancelled with their socket, and the system prompt delivered exactly when it is in the
thread's checkpoint.

The real `run_turn`/`_turn` code runs; only its collaborators (access check, DB run, connector,
persistence, prompt resolution) and the model graph are replaced. No database, no network.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents_orchestrator.modernization_common import standalone

pytestmark = pytest.mark.unit

AGENT = "requirements_modernization"


class _Socket:
    def __init__(self, inbound=(), hold=True):
        self._inbound = [json.dumps(m) for m in inbound]
        self.hold = hold
        self.sent: list[dict] = []

    async def accept(self):
        pass

    async def receive_text(self):
        if self._inbound:
            return self._inbound.pop(0)
        if self.hold:  # like the chat BFF: stay until the turn has ended
            for _ in range(400):
                if any(m.get("type") == "activity_update" for m in self.sent):
                    break
                await asyncio.sleep(0.005)
        raise WebSocketDisconnect()

    async def send_text(self, raw):
        self.sent.append(json.loads(raw))


class _Graph:
    """Scripted graph: records the state each turn was given; replies or raises."""

    def __init__(self, *, reply="Hello.", fail=False, checkpoint=()):
        self.reply, self.fail, self.checkpoint = reply, fail, list(checkpoint)
        self.states: list[dict] = []

    async def aget_state(self, config):
        return SimpleNamespace(values={"messages": self.checkpoint})

    async def astream(self, state, stream_mode, config):
        self.states.append(state)
        if self.fail:
            raise RuntimeError("model endpoint down")
        self.checkpoint.extend(state["messages"])
        yield AIMessage(content=self.reply), {}


@asynccontextmanager
async def _nothing(*_a, **_k):
    yield None


@pytest.fixture
def shell(monkeypatch):
    """Replace every collaborator of `_turn` except the logic under test."""
    from agents_orchestrator.orchestrator2 import connectors, mcp
    import shared.authz.agent_access as access
    import shared.db as db
    import shared.services.conversation_service as conv
    import shared.services.skill_runtime as skills
    import shared.services.standalone_prompt as sp

    async def allow(_db, *, tenant_id, project_id, user_id, agent_id):
        return project_id

    async def run_id(*_a):
        return "run-1"

    async def kind(*_a, **_k):
        return "azure_devops"

    async def noop(*_a, **_k):
        return None

    async def prompt(agent_id, system_prompt, tenant, project):
        return system_prompt, []

    async def no_skills(*_a):
        return []

    async def config(session_id, *_a):
        return {"configurable": {"thread_id": session_id}}

    async def no_upstream(*_a, **_k):
        return ""

    monkeypatch.setattr(access, "assert_agent_access_for_chat_on_track", allow)
    monkeypatch.setattr(db, "get_db_session_for_tenant", _nothing)
    monkeypatch.setattr(standalone, "_chat_run", run_id)
    monkeypatch.setattr(standalone, "_run_config", config)
    monkeypatch.setattr(standalone, "upstream_from_pages", no_upstream)
    monkeypatch.setattr(connectors, "connector_kind_for", kind)
    monkeypatch.setattr(connectors, "bound_connector", _nothing)
    monkeypatch.setattr(mcp, "bound_mcp_tools", _nothing)
    monkeypatch.setattr(conv, "persist_turn", noop)
    monkeypatch.setattr(sp, "resolve_agent_turn", prompt)
    monkeypatch.setattr(sp, "resolve_agent_skills", no_skills)
    monkeypatch.setattr(skills, "skill_context_scope", _nothing)
    standalone._INFLIGHT.clear()
    yield
    standalone._INFLIGHT.clear()


def _frame(session="s1"):
    return {"type": "user_message_with_files", "session_id": session, "task_intent": "hi",
            "pipeline_context": {"project_id": "p1"}}


async def _turn(graph, initialized, session="s1"):
    sock = _Socket()
    await standalone.run_turn(sock, _frame(session), agent_id=AGENT, label="Migration Intent agent",
                              graph=graph, system_prompt="SYSTEM", user_id="u1", tenant_id="t1",
                              initialized=initialized)
    return sock


def _systems(state):
    return [m for m in state["messages"] if isinstance(m, SystemMessage)]


# ── R32: delivered means "in the thread" ─────────────────────────────────────

async def test_first_turn_sends_the_prompt_and_marks_it_only_after_success(shell):
    graph, initialized = _Graph(), set()
    sock = await _turn(graph, initialized)
    assert [m.content for m in _systems(graph.states[0])] == ["SYSTEM"]
    assert initialized == {"s1"}
    assert [m["type"] for m in sock.sent[-2:]] == ["stream_end", "activity_update"]


async def test_a_failed_first_turn_does_not_count_as_delivered(shell):
    initialized = set()
    await _turn(_Graph(fail=True), initialized)
    assert initialized == set()
    retry = _Graph()  # a fresh, empty thread: the failed turn persisted nothing
    await _turn(retry, initialized)
    assert len(_systems(retry.states[0])) == 1


async def test_a_turn_that_ends_without_a_reply_does_not_count_as_delivered(shell):
    initialized = set()
    sock = await _turn(_Graph(reply=""), initialized)
    assert initialized == set()
    assert any("without producing a reply" in (m.get("message") or "") for m in sock.sent)


async def test_after_a_restart_the_prompt_already_in_the_checkpoint_is_not_resent(shell):
    graph = _Graph(checkpoint=[SystemMessage(content="SYSTEM"), HumanMessage(content="earlier")])
    initialized: set[str] = set()  # a new process: the in-memory cache is empty
    await _turn(graph, initialized)
    assert _systems(graph.states[0]) == []
    assert initialized == {"s1"}


async def test_an_unreadable_checkpoint_counts_as_not_delivered():
    class Broken:
        async def aget_state(self, config):
            raise RuntimeError("checkpointer offline")

    assert await standalone.system_prompt_delivered(Broken(), "s1", set()) is False


# ── R31: one turn per session, cancelled with its socket ─────────────────────

async def test_a_second_turn_for_a_busy_session_is_refused_and_ended(shell):
    standalone._INFLIGHT.add((AGENT, "s1"))
    graph = _Graph()
    sock = await _turn(graph, set())
    assert graph.states == []  # the graph was never driven
    assert sock.sent[0] == {"type": "stream_chunk", "content": standalone.BUSY_MESSAGE, "session_id": "s1"}
    assert [m["type"] for m in sock.sent[-2:]] == ["stream_end", "activity_update"]
    assert (AGENT, "s1") in standalone._INFLIGHT  # the running turn still owns it


async def test_the_same_session_on_another_agent_is_not_busy(shell):
    standalone._INFLIGHT.add(("discovery", "s1"))
    graph = _Graph()
    await _turn(graph, set())
    assert len(graph.states) == 1


async def test_the_marker_is_released_when_the_turn_is_cancelled(shell, monkeypatch):
    started = asyncio.Event()

    async def slow(*_a, **_k):
        started.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(standalone, "_turn", slow)
    task = asyncio.create_task(standalone.run_turn(
        _Socket(), _frame(), agent_id=AGENT, label="x", graph=None, system_prompt="",
        user_id="u1", tenant_id="t1", initialized=set()))
    await started.wait()
    assert (AGENT, "s1") in standalone._INFLIGHT
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (AGENT, "s1") not in standalone._INFLIGHT


async def test_a_dropped_socket_cancels_its_running_turn(shell, monkeypatch):
    cancelled = asyncio.Event()
    started = asyncio.Event()

    async def slow(*_a, **_k):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(standalone, "run_turn", slow)

    class Dropping(_Socket):
        async def receive_text(self):
            if self._inbound:
                return self._inbound.pop(0)
            await started.wait()  # the turn is running when the socket goes
            raise WebSocketDisconnect()

    await standalone.serve_agent_socket(
        Dropping([_frame()]), {"user_id": "u1", "tenant_id": "t1"}, agent_id=AGENT, label="x",
        graph=None, system_prompt="", initialized=set())
    await asyncio.wait_for(cancelled.wait(), timeout=2)


# ── Phase B review fixes ─────────────────────────────────────────────────────

async def test_another_agents_system_message_in_a_shared_thread_is_not_mine(shell):
    """Enterprise checkpoints are one store keyed by thread id: a session id that names
    another agent's thread must not make this agent skip its own instructions."""
    other = SystemMessage(content="You are the Dependency and Risk agent…", id="system:discovery")
    graph = _Graph(checkpoint=[other, HumanMessage(content="earlier")])
    await _turn(graph, set())
    mine = _systems(graph.states[0])
    assert [m.id for m in mine] == [standalone.system_message_id(AGENT)]


async def test_the_system_message_sent_carries_this_agents_id(shell):
    graph = _Graph()
    await _turn(graph, set())
    assert _systems(graph.states[0])[0].id == "system:requirements_modernization"


async def test_a_turn_stopped_mid_reply_is_saved_as_stopped(shell, monkeypatch):
    import shared.services.conversation_service as conv

    saved: list[str] = []

    async def persist(session_id, role, text, **_k):
        if role == "agent":
            saved.append(text)

    monkeypatch.setattr(conv, "persist_turn", persist)
    started = asyncio.Event()

    class Slow(_Graph):
        async def astream(self, state, stream_mode, config):
            yield AIMessage(content="Half a reply"), {}
            started.set()
            await asyncio.sleep(30)

    task = asyncio.create_task(standalone.run_turn(
        _Socket(), _frame(), agent_id=AGENT, label="x", graph=Slow(), system_prompt="SYSTEM",
        user_id="u1", tenant_id="t1", initialized=set()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert saved == ["Half a reply" + standalone.STOPPED_NOTE]
