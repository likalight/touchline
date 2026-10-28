"""Small, local provenance records; no credentials or environment values are exported."""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(paths):
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def provenance():
    def git(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                           stderr=subprocess.DEVNULL, timeout=5).strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return "unavailable"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_head": git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(git("status", "--porcelain")),
        "python_source_sha256": fingerprint([*ROOT.glob("touchline/**/*.py"), *ROOT.glob("scripts/*.py")]),
        "simulator_sha256": fingerprint(ROOT.glob("touchline/sim/*.py")),
        "model_artifact_sha256": fingerprint(ROOT.glob("touchline/analytics/params.json")),
        "scope": "Hashes bind the files actually read, including uncommitted changes. A Git HEAD alone does not identify a dirty working tree.",
    }
