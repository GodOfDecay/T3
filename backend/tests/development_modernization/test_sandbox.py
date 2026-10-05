"""Migration Development's build sandbox, for real (R52) — Phase H.

The toolchain's commands run in the pinned image with no network, the workspace read-only for a build
(a build never edits what it checks) and writable only for a recipe; bytecode never lands in the diff.
The 2to3 recipe really converts ClaimTrack Lite's claims API — and leaves the rounding trap in place,
which is why the agent reads the code a recipe produced. Skipped where Docker is not running.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from agents_orchestrator.development_modernization_agent import sandbox
from agents_orchestrator.development_modernization_agent import toolchains as T
from tests.testing_modernization import lite

pytestmark = pytest.mark.skipif(not sandbox.available(), reason="Docker is not running")

CHAIN = T.toolchain("python")
IMAGE = T.image_for(CHAIN)


@pytest.fixture
def work(tmp_path):
    shutil.copytree(lite.SAMPLE / "claims-api", tmp_path / "claims-api")
    return tmp_path


def test_a_command_has_no_network(work):
    r = sandbox.run(IMAGE, work, ["python", "-c", "import urllib.request; urllib.request.urlopen('http://1.1.1.1', timeout=5)"])
    assert not r.ok and ("unreachable" in r.output.lower() or "urlopen error" in r.output.lower()
                         or "timed out" in r.output.lower())


def test_a_build_cannot_write_the_workspace_and_leaves_no_bytecode(work):
    before = sorted(p.relative_to(work).as_posix() for p in work.rglob("*"))
    r = sandbox.run(IMAGE, work, ["python", "-c", "open('claims-api/x.py', 'w').write('1')"])
    assert not r.ok and "Read-only file system" in r.output
    r = sandbox.run(IMAGE, work, T.argv(CHAIN.lint, "claims-api"))
    assert r.ok, r.output
    assert sorted(p.relative_to(work).as_posix() for p in work.rglob("*")) == before


def test_the_legacy_code_does_not_build_on_the_target_runtime(work):
    """server.py is valid Python 3 SYNTAX — its Python 2 imports only fail when it runs. A compile-only
    "build" called it green (found in Phase H); the build resolves every import, so it is honestly red."""
    r = sandbox.run(IMAGE, work, T.argv(CHAIN.build, "claims-api"))
    assert not r.ok
    assert "cannot import BaseHTTPServer on this runtime" in r.output and "cannot import urllib2" in r.output


def test_the_recipe_converts_the_module_and_leaves_the_rounding_trap(work):
    recipe = CHAIN.recipe("2to3")
    r = sandbox.run(IMAGE, work, T.argv(recipe.argv, "claims-api"), writable=True)
    assert r.ok, r.output
    text = (work / "claims-api" / "server.py").read_text()
    assert "import http.server" in text and "urllib.request.urlopen" in text and "BaseHTTPServer" not in text
    assert "return round(amount * rate, 2)" in text, "a recipe converts syntax; the trap is the agent's to handle"
    assert "self.wfile.write(data)" in text, "and it cannot see that the socket now needs bytes"
    built = sandbox.run(IMAGE, work, T.argv(CHAIN.build, "claims-api"))
    assert built.ok, built.output


def test_a_secret_a_command_prints_is_redacted(work):
    r = sandbox.run(IMAGE, work, ["python", "-c", "print('token ghp_' + 'a' * 36)"])
    assert "ghp_***" in r.output and "a" * 36 not in r.output


def test_nothing_is_left_running(work):
    sandbox.run(IMAGE, work, ["python", "-c", "print(1)"], label="M-77")
    left = subprocess.run(["docker", "ps", "-aq", "--filter", "label=sdlc.migration=M-77"], capture_output=True,
                          text=True).stdout.split()
    assert left == []
