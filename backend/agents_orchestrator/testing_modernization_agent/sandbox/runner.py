"""The legacy sandbox — runs a legacy system and records what it does (Phase G decision G2).

ISOLATION. Each run gets its own Docker network created `--internal`: the containers on it reach
each other and NOTHING else (no internet, no host). On it: the legacy app (built from the checkout's
own Dockerfile, root filesystem read-only, only the profile's `writable` directories as tmpfs, no
Linux capabilities, bounded memory/CPU/processes: `limits()`), one
stub server per external service, and a short-lived request driver. Everything carries the label
`sdlc.capture=<id>` and is removed in `finally`, whether the capture worked or not.

TWO RUNS, each on a FRESH app container seeded again: whatever still differs between them is the
system's own nondeterminism (the noise report), not leftover state.

ALL SCENARIOS, IN PROFILE ORDER, EVERY RUN. Scenarios share the system's state (a settlement changes
what the bank file contains), so a capture always runs the whole profile; the plan decides which
recordings become which baseline.

Nothing here decides anything about equivalence; it runs and records. Recordings are written under
`out_dir/run<n>/<scenario>/`.
"""
from __future__ import annotations

import io
import json
import logging
import os
import pathlib
import shlex
import subprocess
import tarfile
import threading
from dataclasses import dataclass, field
from typing import Optional

from agents_orchestrator.testing_modernization_agent.sandbox.images import harness_image
from agents_orchestrator.testing_modernization_agent.sandbox.profile import output_dir_and_pattern

logger = logging.getLogger(__name__)

HARNESS_DIR = pathlib.Path(__file__).resolve().parent / "harness"


def health_seconds() -> int:
    """How long a legacy service may take to answer its health check (SDLC_SANDBOX_HEALTH_SECONDS)."""
    try:
        return max(5, int(os.environ.get("SDLC_SANDBOX_HEALTH_SECONDS", "60")))
    except ValueError:
        return 60

BATCH_SECONDS = 300
BUILD_SECONDS = 900


def limits() -> list[str]:
    """What every sandbox container runs under. The legacy code is somebody else's program, run
    as it is: no Linux capabilities, no privilege escalation, and bounded memory, CPU and process
    count, so a runaway legacy job cannot starve the server (SDLC_SANDBOX_MEMORY, _CPUS, _PIDS)."""
    memory = os.environ.get("SDLC_SANDBOX_MEMORY", "").strip() or "1g"
    cpus = os.environ.get("SDLC_SANDBOX_CPUS", "").strip() or "1"
    pids = os.environ.get("SDLC_SANDBOX_PIDS", "").strip() or "256"
    return ["--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", memory,
            "--cpus", cpus, "--pids-limit", pids]


class CaptureFailed(Exception):
    """A capture that could not complete. The message is for people: no recorded data in it."""


class CaptureCancelled(CaptureFailed):
    """The user stopped the turn: the capture stops at the next step and removes its sandbox."""


def _docker_bin() -> str:
    return os.environ.get("SDLC_DOCKER", "docker")


def docker(*args: str, timeout: int = 120, check: bool = True, binary: bool = False) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run([_docker_bin(), *args], capture_output=True, timeout=timeout,
                              text=not binary, **({} if binary else {"encoding": "utf-8", "errors": "replace"}))
    except FileNotFoundError as exc:
        raise CaptureFailed("Docker is not available on this server.") from exc
    except subprocess.TimeoutExpired as exc:
        raise CaptureFailed(f"docker {args[0]} did not finish within {timeout} seconds.") from exc
    if check and proc.returncode != 0:
        err = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode("utf-8", "replace")
        raise CaptureFailed(f"docker {args[0]} failed: {err.strip()[-400:]}")
    return proc


def _mount(src: pathlib.Path, dst: str, readonly: bool = True) -> list[str]:
    spec = f"type=bind,src={src},dst={dst}" + (",readonly" if readonly else "")
    return ["--mount", spec]


def cleanup(capture_id: str) -> None:
    """Remove every container and network of this capture. Never raises."""
    label = f"label=sdlc.capture={capture_id}"
    try:
        ids = docker("ps", "-aq", "--filter", label, check=False).stdout.split()
        if ids:
            docker("rm", "-f", *ids, check=False, timeout=120)
        nets = docker("network", "ls", "-q", "--filter", label, check=False).stdout.split()
        for net in nets:
            docker("network", "rm", net, check=False)
    except CaptureFailed:
        logger.warning("sandbox: cleanup of %s could not reach Docker", capture_id)


def leftovers(capture_id: str) -> list[str]:
    """Containers and networks still carrying this capture's label (should be none)."""
    label = f"label=sdlc.capture={capture_id}"
    return (docker("ps", "-aq", "--filter", label, check=False).stdout.split()
            + docker("network", "ls", "-q", "--filter", label, check=False).stdout.split())


def measure(checkout: pathlib.Path, profile: dict, scenarios: list[dict], capture_id: str, repeat: int,
            out_dir: pathlib.Path) -> dict[str, dict]:
    """Phase J: build and start the system once and time each HTTP scenario `repeat` times, under the same
    container limits as every run. {scenario: {"ms": [...], "errors": n}}. Leaves nothing behind."""
    tag = f"sdlc-legacy:{capture_id.lower()}"
    try:
        tag, _image = build_image(checkout, profile, capture_id)
        run = Run(checkout, profile, tag, capture_id, 1)
        try:
            run.start()
            return {sc["id"]: run.perf(sc, out_dir / sc["id"], repeat) for sc in scenarios}
        finally:
            run.stop()
    finally:
        cleanup(capture_id)
        docker("rmi", "-f", tag, check=False)


def build_image(checkout: pathlib.Path, profile: dict, capture_id: str) -> tuple[str, str]:
    """(tag, image id). Built from the checkout's own Dockerfile; base images are digest-pinned
    (checked by the profile), so the same checkout builds the same runtime."""
    tag = f"sdlc-legacy:{capture_id.lower()}"
    dockerfile = (checkout / profile["build"]["dockerfile"]).resolve()
    docker("build", "--label", f"sdlc.capture={capture_id}", "-t", tag, "-f", str(dockerfile), str(checkout),
           timeout=BUILD_SECONDS)
    image_id = docker("image", "inspect", tag, "--format", "{{.Id}}").stdout.strip()
    return tag, image_id


@dataclass
class Run:
    """One run: a network, the stubs, the app. `start()`, then `scenario()` for each, then `stop()`."""

    checkout: pathlib.Path
    profile: dict
    image: str
    capture_id: str
    number: int
    net: str = field(init=False)

    def __post_init__(self) -> None:
        self.net = f"sdlc-cap-{self.capture_id}-r{self.number}".lower()

    @property
    def app(self) -> str:
        return f"{self.net}-app"

    def _labels(self) -> list[str]:
        return ["--label", f"sdlc.capture={self.capture_id}"]

    def _driver(self, *args: str, extra: Optional[list[str]] = None, timeout: int = 120) -> subprocess.CompletedProcess:
        return docker("run", "--rm", "--network", self.net, *self._labels(), *limits(), "--read-only",
                      *_mount(HARNESS_DIR, "/harness"), *(extra or []), harness_image(),
                      "python", "/harness/driver.py", *args, check=False, timeout=timeout)

    def start(self) -> None:
        docker("network", "create", "--internal", *self._labels(), self.net)
        env = []
        for s in self.profile.get("stubs") or []:
            docker("run", "-d", "--name", f"{self.net}-{s['name']}", "--network", self.net,
                   "--network-alias", s["name"], *self._labels(), *limits(), "--read-only",
                   *_mount(HARNESS_DIR, "/harness"),
                   *_mount((self.checkout / s["responses"]).resolve(), "/stub/responses.json"),
                   harness_image(), "python", "/harness/stub_server.py", "/stub/responses.json", str(s["port"]))
            env += ["-e", f"{s['env']}=http://{s['name']}:{s['port']}"]
        seed = (self.profile.get("seed") or "").strip()
        service = self.profile.get("service")
        main = f"exec {service['command']}" if service else "while :; do sleep 3600; done"
        script = f"set -e\n{seed}\n{main}" if seed else main
        tmpfs = [x for w in self.profile.get("writable") or [] for x in ("--tmpfs", f"{w}:rw")]
        docker("run", "-d", "--name", self.app, "--network", self.net, "--network-alias", "app",
               *self._labels(), *limits(), "--read-only", "--tmpfs", "/tmp:rw", *tmpfs, *env, self.image, "sh", "-c", script)
        for s in self.profile.get("stubs") or []:
            if self._driver("wait", f"http://{s['name']}:{s['port']}/", str(health_seconds())).returncode != 0:
                raise CaptureFailed(f"The stub for {s['name']} did not start.")
        if service:
            url = f"http://app:{service['port']}{service['health']}"
            if self._driver("wait", url, str(health_seconds()), timeout=health_seconds() + 30).returncode != 0:
                state = docker("inspect", self.app, "--format", "{{.State.Status}} (exit {{.State.ExitCode}})",
                               check=False).stdout.strip()
                raise CaptureFailed(f"The legacy service did not answer on {service['health']} within "
                                    f"{health_seconds()} seconds; its container is {state or 'gone'}.")

    def scenario(self, sc: dict, out: pathlib.Path) -> dict:
        out.mkdir(parents=True, exist_ok=True)
        if sc["kind"] == "http":
            requests = (self.checkout / sc["requests"]).resolve()
            port = self.profile["service"]["port"]
            proc = self._driver("http", f"http://app:{port}", "/in/requests.jsonl", "/out/responses.jsonl",
                                extra=[*_mount(requests, "/in/requests.jsonl"), *_mount(out.resolve(), "/out", False)],
                                timeout=60 + 30 * int(sc.get("cases") or 1))
            if proc.returncode != 0 or not (out / "responses.jsonl").is_file():
                raise CaptureFailed(f"Scenario {sc['id']}: the request driver failed.")
            return {"id": sc["id"], "kind": "http", "cases": sum(1 for _ in (out / "responses.jsonl").open(encoding="utf-8"))}
        proc = docker("exec", self.app, "sh", "-c", sc["command"], check=False, timeout=BATCH_SECONDS)
        record = {"exit": proc.returncode, "stdout": proc.stdout, "missing": []}
        files = out / "files"
        files.mkdir(exist_ok=True)
        for glob in sc["outputs"]:
            directory, pattern = output_dir_and_pattern(glob)
            tar = docker("exec", self.app, "sh", "-c", f"cd {shlex.quote(directory)} && tar -cf - {pattern}",
                         check=False, binary=True, timeout=BATCH_SECONDS)
            if tar.returncode != 0 or not tar.stdout:
                record["missing"].append(glob)
                continue
            with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as archive:
                for member in archive.getmembers():
                    name = pathlib.PurePosixPath(member.name).name
                    if member.isfile() and name and name not in (".", ".."):
                        data = archive.extractfile(member).read()
                        (files / name).write_bytes(data)
        (out / "exec.json").write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        return {"id": sc["id"], "kind": "batch", "cases": 1, "exit": proc.returncode, "missing": record["missing"]}

    def perf(self, sc: dict, out: pathlib.Path, repeat: int) -> dict:
        """Phase J: the scenario's requests `repeat` times; latencies only ({"ms": [...], "errors": n})."""
        if sc["kind"] != "http":
            raise CaptureFailed(f"Scenario {sc['id']} is not HTTP: performance is measured on HTTP scenarios.")
        out.mkdir(parents=True, exist_ok=True)
        requests = (self.checkout / sc["requests"]).resolve()
        port = self.profile["service"]["port"]
        proc = self._driver("perf", f"http://app:{port}", "/in/requests.jsonl", str(int(repeat)), "/out/latencies.json",
                            extra=[*_mount(requests, "/in/requests.jsonl"), *_mount(out.resolve(), "/out", False)],
                            timeout=60 + 30 * int(repeat) * int(sc.get("cases") or 1))
        if proc.returncode != 0 or not (out / "latencies.json").is_file():
            raise CaptureFailed(f"Scenario {sc['id']}: the performance driver failed.")
        return json.loads((out / "latencies.json").read_text(encoding="utf-8"))

    def stop(self) -> None:
        cleanup_run = [f"{self.net}-{s['name']}" for s in self.profile.get("stubs") or []] + [self.app]
        docker("rm", "-f", *cleanup_run, check=False)
        docker("network", "rm", self.net, check=False)


def capture(checkout: pathlib.Path, profile: dict, out_dir: pathlib.Path, capture_id: str, runs: int = 2,
            cancelled: Optional[threading.Event] = None) -> dict:
    """Build, run the whole profile `runs` times, record. Raises CaptureFailed (CaptureCancelled once
    `cancelled` is set, checked between steps); leaves nothing behind either way."""
    tag = f"sdlc-legacy:{capture_id.lower()}"

    def _check() -> None:
        if cancelled is not None and cancelled.is_set():
            raise CaptureCancelled("The capture was stopped before it finished.")

    try:
        tag, image_id = build_image(checkout, profile, capture_id)
        results = []
        for n in range(1, runs + 1):
            _check()
            run = Run(checkout, profile, tag, capture_id, n)
            try:
                run.start()
                recorded = []
                for sc in profile["scenarios"]:
                    _check()
                    recorded.append(run.scenario(sc, out_dir / f"run{n}" / sc["id"]))
                results.append(recorded)
            finally:
                run.stop()
        return {"image_id": image_id, "runs": runs, "scenarios": results[0]}
    finally:
        cleanup(capture_id)
        docker("rmi", "-f", tag, check=False)
