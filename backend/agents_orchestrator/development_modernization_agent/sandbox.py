"""Run a toolchain command on a migration workspace, in a container (Phase H decision H5).

Builds, tests, lints and upgrade recipes are the TARGET's and the LEGACY's own code being executed:
somebody else's program. So never on the server: each command runs in a fresh container of the
toolchain's digest-pinned image, with

  --network none          no internet, no host, no other container
  runner.limits()         no Linux capabilities, no privilege escalation, bounded memory/CPU/processes
  --read-only             the image's own filesystem is not writable; /tmp is a tmpfs
  /sdlc                   the platform's own checks (`checks/`), read-only
  the workspace           mounted READ-ONLY for build, test and lint (a build never edits the code it
                          checks); writable only for an upgrade recipe, whose job is to edit it
  PYTHONPYCACHEPREFIX     bytecode caches go to /tmp, never into the workspace's diff

argv only — no shell. Output is redacted and capped (Track 1's `sandbox_policy`), so a credential a
build prints never reaches the model.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import time
from dataclasses import dataclass

from agents_orchestrator.development_agent.tools.sandbox_policy import sanitize_output
from agents_orchestrator.testing_modernization_agent.sandbox.runner import CaptureFailed, docker, limits

COMMAND_SECONDS = 600


class SandboxUnavailable(Exception):
    """Docker could not run the command at all (not the command failing). For people."""


@dataclass
class CommandResult:
    exit_code: int
    output: str
    seconds: float

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _user() -> list[str]:
    """Run as the server's own user on POSIX, so files a recipe writes are not root-owned."""
    if hasattr(os, "getuid"):
        return ["--user", f"{os.getuid()}:{os.getgid()}"]
    return []


def run(image: str, workspace: pathlib.Path, argv: list[str], *, writable: bool = False,
        label: str = "", timeout: int = COMMAND_SECONDS) -> CommandResult:
    """Run `argv` in `image` with the workspace at /work. Raises SandboxUnavailable when Docker itself
    fails; a command that runs and fails is a CommandResult with a non-zero exit code."""
    from agents_orchestrator.development_modernization_agent.toolchains import CHECKS_DIR  # noqa: PLC0415

    mount = f"type=bind,src={workspace.resolve()},dst=/work" + ("" if writable else ",readonly")
    args = ["run", "--rm", "--network", "none", *limits(), "--read-only", "--tmpfs", "/tmp:rw,exec",
            "--mount", mount, "--mount", f"type=bind,src={CHECKS_DIR},dst=/sdlc,readonly",
            "-w", "/work", "-e", "HOME=/tmp", "-e", "PYTHONPYCACHEPREFIX=/tmp/pycache",
            "-e", "PYTHONDONTWRITEBYTECODE=1", *_user()]
    if label:
        args += ["--label", f"sdlc.migration={label}"]
    started = time.monotonic()
    try:
        proc = docker(*args, image, *argv, check=False, timeout=timeout)
    except CaptureFailed as exc:  # Docker missing, or the command outlived its time
        raise SandboxUnavailable(str(exc)) from exc
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    if proc.returncode == 125:  # Docker's own error (bad image, bad mount): not the command
        raise SandboxUnavailable(f"Docker could not start the toolchain container: {sanitize_output(out)[-400:]}")
    return CommandResult(exit_code=proc.returncode, output=sanitize_output(out.strip()),
                         seconds=round(time.monotonic() - started, 1))


def tail(text: str, lines: int = 40) -> str:
    """The end of a command's output — where a build says what failed."""
    rows = (text or "").splitlines()
    return "\n".join(rows[-lines:])


def available() -> bool:
    try:
        return subprocess.run([os.environ.get("SDLC_DOCKER", "docker"), "info"], capture_output=True,
                              timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
