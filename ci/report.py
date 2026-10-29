"""Trusted baseline CI helper; standard library only, no merge credentials."""
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import uuid

TRUSTED = Path(__file__).resolve().parents[1]
SOURCES = (".github/workflows/verify.yml", "ci/report.py")
IMAGE = "docker.io/library/python@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args]).strip()


def isolated_checks(candidate, tested):
    """Export Git blobs only. Candidate code never runs on the reporting host."""
    runner = '''import json,sys,unittest
sys.path.insert(0,sys.argv[1])
r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(sys.argv[1]+"/tests"))
print(json.dumps(dict(name="api",kind="tests",tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),expected_failures=len(r.expectedFailures),unexpected_successes=len(r.unexpectedSuccesses))))
'''
    with tempfile.TemporaryDirectory(prefix="fde-ci-export-") as temporary:
        snapshot = Path(temporary)
        snapshot.chmod(0o755)
        for entry in git(candidate, "ls-tree", "-r", "-z", tested).split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            name = raw_name.decode()
            parts = PurePosixPath(name).parts
            assert mode == "100644" and kind == "blob", "only ordinary non-executable product files"
            assert parts and not name.startswith("/") and all(p not in (".", "..", ".git") for p in parts)
            path = snapshot.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(["git", "-C", str(candidate), "cat-file", "blob", oid]))
            path.chmod(0o644)
        name = "fde-ci-" + uuid.uuid4().hex
        argv = ["docker", "run", "--pull", "never", "--rm", "--name", name,
            "--read-only", "--network", "none", "--user", "65534:65534",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "256m", "--cpus", "1",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16777216",
            "--mount", "type=bind,source=" + str(snapshot) + ",target=/product,readonly",
            "--workdir", "/product", IMAGE, "python3", "-I", "-B", "-c", runner, "/product"]
        # No env forwarding, host network/PID namespace, home, .git or Docker socket mount.
        # The isolation boundary is the existing container runtime, not filesystem owners.
        print("CI_CONTAINER_POLICY " + json.dumps(dict(image=IMAGE, read_only=True, network="none",
            uid=65534, capabilities=[], mounted_snapshot="/product", credentials_forwarded=False)))
        try:
            return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=120)
        finally:
            # Only this randomly named owned container; timeout must not leave tests running.
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)


def main():
    mode, candidate_path, result_path = sys.argv[1:]
    candidate, result = Path(candidate_path).resolve(), Path(result_path)
    source = git(TRUSTED, "rev-parse", "HEAD").decode()
    tested = git(candidate, "rev-parse", "HEAD").decode()
    assert tested == os.environ["FDE_EXPECTED_SHA"], "candidate SHA mismatch"
    sources = []
    for name in SOURCES:
        entry = git(TRUSTED, "ls-tree", source, "--", name).split(b"\t")[0].decode().split()
        file_mode, kind, oid = entry
        assert kind == "blob" and file_mode == "100644"
        raw = subprocess.check_output(["git", "-C", str(TRUSTED), "cat-file", "blob", oid])
        for repo in (TRUSTED, candidate):
            path = repo
            for part in name.split("/"):
                path = path / part
                assert not path.is_symlink(), "symlink source"
            assert path.read_bytes() == raw and not path.stat().st_mode & 0o111, "CI source drift"
        sources.append(dict(path=name, mode=file_mode, oid=oid, sha256=hashlib.sha256(raw).hexdigest()))
    identity = dict(schema_version=1, run_id=int(os.environ["GITHUB_RUN_ID"]),
        run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]), job_name="Ticket API tests",
        tested_sha=tested, source_sha=source, workflow_sha=os.environ["GITHUB_WORKFLOW_SHA"], sources=sources)
    if mode == "checks":
        unit = isolated_checks(candidate, tested)
        # Candidate output is data; it cannot add trusted report lines to the host log.
        print("UNTRUSTED_TEST_STDERR " + json.dumps(unit.stderr))
        tests = json.loads(unit.stdout)
        lint = "success"
        try:
            for path in [candidate / "tickets.py", *sorted((candidate / "tests").glob("test_*.py"))]:
                ast.parse(path.read_text())
        except (SyntaxError, UnicodeError):
            lint = "failure"
        result.write_text(json.dumps(dict(identity, checks=[tests, dict(name="syntax", kind="check", conclusion=lint)])) + "\n")
        return int(lint != "success" or tests["tests"] < 6 or any(tests[k] for k in
            ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")))
    assert mode == "report", "unknown report mode"
    report = json.loads(result.read_text())
    assert {key: report[key] for key in identity} == identity, "report identity drift"
    print("FDE_CI_REPORT_V1 " + json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
