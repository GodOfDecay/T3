"""REQ-M8-05 — Dead-letter stream unit tests.

Asserts the failed-emit → Redis dead-letter → retry worker pipeline:
  - When AuditEventService._write() raises, _send_to_dead_letter() is called with XADD
  - The dead-letter Redis stream receives the payload JSON
  - A retry worker reads the stream and re-emits the event via emit_blocking(),
    deletes the entry on success, and leaves it in place on failure

D-M8-05 locked decision: Failed non-blocking emits → Redis dead-letter stream
(reuse existing Redis infra). Background retry worker picks them up.

These were xfail(strict=False) while Wave-2 was outstanding. Both modules now exist and
all of these pass, so the marker is gone — left in place it accepted a silent regression,
which is how the retry worker shipped re-reading the stream from "0-0" forever without
ever deleting an entry.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
async def test_failed_write_sends_to_dead_letter(mock_audit_service, mock_redis_client):
    """When _write() raises, _send_to_dead_letter() must XADD to audit:dead_letter."""
    from shared.audit.service import AuditEventService
    from shared.audit.models import AuditEventPayload

    svc = AuditEventService()

    # Force _write to raise a DB error
    svc._write = AsyncMock(side_effect=Exception("DB connection refused"))
    svc._send_to_dead_letter = AsyncMock(wraps=svc._send_to_dead_letter)

    payload = AuditEventPayload(
        tenant_id="00000000-0000-0000-0000-000000000001",
        run_id="run-dlq-001",
        event_type="tool_call_start",
        agent_type="requirements",
        actor_id="system:requirements",
        payload={"tool_name": "fetch_work_items"},
    )

    with patch("shared.audit.service.redis_from_url", return_value=mock_redis_client):
        await svc.emit(payload)

    # Give the background task a chance to run
    import asyncio
    await asyncio.sleep(0)

    mock_redis_client.xadd.assert_called_once()
    stream_name, fields = mock_redis_client.xadd.call_args[0]
    assert stream_name == "audit:dead_letter"
    assert "payload" in fields


@pytest.mark.unit
async def test_failed_write_does_not_raise(mock_audit_service, mock_redis_client):
    """emit() must never raise even when both _write() and dead-letter fail.

    fire-and-forget contract: failures are swallowed; the caller is never blocked.
    """
    from shared.audit.service import AuditEventService
    from shared.audit.models import AuditEventPayload

    svc = AuditEventService()
    svc._write = AsyncMock(side_effect=Exception("DB down"))

    payload = AuditEventPayload(
        tenant_id="00000000-0000-0000-0000-000000000001",
        run_id="run-dlq-002",
        event_type="model_call",
        agent_type="design",
        actor_id="system:design",
        payload={},
    )

    with patch("shared.audit.service.redis_from_url", return_value=mock_redis_client):
        # Must not raise
        await svc.emit(payload)

    import asyncio
    await asyncio.sleep(0)


@pytest.mark.unit
async def test_dead_letter_xadd_contains_payload_json(mock_redis_client):
    """The XADD message must include serialized AuditEventPayload JSON."""
    from shared.audit.service import AuditEventService
    from shared.audit.models import AuditEventPayload

    svc = AuditEventService()
    svc._write = AsyncMock(side_effect=RuntimeError("write error"))

    payload = AuditEventPayload(
        tenant_id="00000000-0000-0000-0000-000000000001",
        run_id="run-dlq-003",
        event_type="tool_call_end",
        agent_type="testing",
        actor_id="system:testing",
        payload={"output": "pass"},
    )

    with patch("shared.audit.service.redis_from_url", return_value=mock_redis_client):
        await svc.emit(payload)

    import asyncio
    await asyncio.sleep(0)

    mock_redis_client.xadd.assert_called_once()
    _, fields = mock_redis_client.xadd.call_args[0]
    import json
    recovered = json.loads(fields["payload"])
    assert recovered["run_id"] == "run-dlq-003"
    assert recovered["event_type"] == "tool_call_end"


@pytest.mark.unit
async def test_retry_worker_reemits_from_dead_letter(mock_audit_service, mock_redis_client):
    """Round-trip: XADD payload → worker reads → emit_blocking() → entry deleted."""
    import json
    from shared.audit.models import AuditEventPayload

    test_payload = AuditEventPayload(
        tenant_id="00000000-0000-0000-0000-000000000001",
        run_id="run-retry-001",
        event_type="tool_call_start",
        agent_type="development",
        actor_id="system:development",
        payload={"tool_name": "write_code"},
    )

    # Simulate XREADGROUP returning one message from the dead-letter stream
    stream_entry = [
        [
            b"audit:dead_letter",
            [(b"1-0", {b"payload": test_payload.model_dump_json().encode()})],
        ]
    ]
    mock_redis_client.xread = AsyncMock(return_value=stream_entry)

    from workers.audit_retry_worker import AuditRetryWorker

    worker = AuditRetryWorker(audit_service=mock_audit_service, redis_client=mock_redis_client)
    await worker.process_one()

    # emit_blocking, not emit: the retry path must AWAIT the write. emit() is
    # fire-and-forget, so it reports no success and applies no backpressure — the worker
    # could neither know when to XDEL nor stop spawning writes, which is what let the
    # stream grow into a permanent backlog the loop re-read forever.
    mock_audit_service.emit_blocking.assert_called_once()
    emitted = mock_audit_service.emit_blocking.call_args[0][0]
    assert emitted.run_id == "run-retry-001"
    assert emitted.event_type == "tool_call_start"

    # A successfully re-emitted entry must be removed, or it is replayed forever.
    mock_redis_client.xdel.assert_called_once_with("audit:dead_letter", b"1-0")


@pytest.mark.unit
async def test_retry_worker_keeps_entry_when_reemit_fails(mock_audit_service, mock_redis_client):
    """A failed re-emit must NOT delete the entry — it is retried by a later run."""
    from shared.audit.models import AuditEventPayload

    test_payload = AuditEventPayload(
        tenant_id="00000000-0000-0000-0000-000000000001",
        run_id="run-retry-002",
        event_type="tool_call_start",
        agent_type="development",
        actor_id="system:development",
        payload={},
    )
    mock_redis_client.xread = AsyncMock(
        return_value=[[b"audit:dead_letter", [(b"2-0", {b"payload": test_payload.model_dump_json().encode()})]]]
    )
    mock_audit_service.emit_blocking = AsyncMock(side_effect=RuntimeError("DB down"))

    from workers.audit_retry_worker import AuditRetryWorker

    worker = AuditRetryWorker(audit_service=mock_audit_service, redis_client=mock_redis_client)
    await worker.process_one()

    mock_redis_client.xdel.assert_not_called()


# ── the worker survives an idle wait (the 2 s socket timeout vs the 5 s block) ──

async def test_the_retry_worker_reads_longer_than_it_blocks():
    """Its own client may wait out the whole xread block. With the shared 2 s socket
    timeout under a 5 s block, every idle read timed out and the worker died at startup."""
    from workers import audit_retry_worker as w

    assert w._READ_TIMEOUT_S > w._BLOCK_MS / 1000
    made = {}

    class Client:
        async def xread(self, **_kw):
            raise asyncio.CancelledError

        async def aclose(self):
            pass

    def fake_from_url(**kw):
        made.update(kw)
        return Client()

    with patch.object(w, "redis_from_url", fake_from_url):
        await w.AuditRetryWorker(audit_service=AsyncMock()).run()
    assert made["socket_timeout"] == w._READ_TIMEOUT_S


async def test_a_timed_out_idle_read_does_not_end_the_worker(mock_audit_service, mock_redis_client):
    import redis.asyncio as aioredis

    from workers.audit_retry_worker import AuditRetryWorker

    calls = []

    async def xread(**_kw):
        calls.append(1)
        if len(calls) < 3:
            raise aioredis.TimeoutError("Timeout reading from socket")
        raise asyncio.CancelledError

    mock_redis_client.xread = xread
    await AuditRetryWorker(audit_service=mock_audit_service, redis_client=mock_redis_client).run()
    assert len(calls) == 3


def test_every_long_lived_redis_reader_outlasts_its_wait():
    """The 2 s operation timeout is for commands. A reader that waits on purpose must not
    time out while waiting (audit retry worker, pipeline workers, artifact listener)."""
    import inspect

    import process_api
    from shared.redis_client import OPERATION_TIMEOUT_S, blocking_read_timeout
    from workers import audit_retry_worker, base_worker

    assert blocking_read_timeout(5) == 5 + OPERATION_TIMEOUT_S
    assert audit_retry_worker._READ_TIMEOUT_S > audit_retry_worker._BLOCK_MS / 1000
    assert "socket_timeout=blocking_read_timeout(_BLOCK_MS / 1000)" in inspect.getsource(base_worker)
    assert "redis_pubsub_from_url(socket_timeout=None)" in inspect.getsource(process_api._artifact_event_listener)
