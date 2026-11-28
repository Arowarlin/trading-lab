"""Guardas de Claude Code del proyecto (`.claude/hooks/tl_guard.py`).

Cada regla de AGENTS.md que el hook convierte en bloqueo tiene aquí un caso que
se deniega y otro parecido que debe pasar.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "tl_guard.py"
RUNNER = ROOT / ".claude" / "hooks" / "run.sh"


def _git_bash() -> str | None:
    """bash que entiende rutas Windows; el de WSL (System32) no sirve para este runner."""
    if os.name != "nt":
        return shutil.which("bash")
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "bin" / "bash.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


BASH = _git_bash()

_spec = importlib.util.spec_from_file_location("tl_guard", GUARD)
guard = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(guard)

ENV = "." + "env"  # el propio comando de pytest no debe contener el nombre literal


def _work_branch(_root):
    return "claude/rama-de-trabajo"


def _master(_root):
    return "master"


DENY = [
    "lab campaign run --approved-by-operator c1",
    r".\.venv\Scripts\lab.exe research --start 2020",
    "lab research-intraday",
    "lab research-swing --x 1",
    "uv run lab discovery approve c1",
    "python -m tradinglab.cli discovery run c1",
    "lab discovery confirm c1",
    "lab discovery supersede c1",
    "lab learning record-informal --n 3 --reason x",
    "git push origin master",
    "git push origin HEAD:main",
    "git push --force origin claude/x",
    "git push origin +claude/x",
    "git add -A",
    "git add .",
    "git add -u",
    "git commit -am 'x'",
    "git commit -a -m x",
    "git commit --amend -m x",
    "git rebase -i HEAD~3",
    "git reset --hard HEAD~1",
    "git rm src/x.py",
    "git clean -fdx",
    "git branch -D vieja",
    "rm -rf data",
    "git status && rm fichero.txt",
    "echo $(rm x)",
    "cd docs\nrm viejo.md",
    "Remove-Item foo.txt",
    "find . -name '*.pyc' -delete",
    "schtasks /Create /TN x /TR y",
    "Register-ScheduledTask -TaskName x",
    f"cat {ENV}",
    f"echo x > {ENV}.local",
    "ALLOW_LIVE=YES lab ai-trader run",
]

ALLOW = [
    "lab research-trials --limit 5",
    "lab discovery preflight --spec x.yaml",
    "lab discovery results c1",
    "lab propfund verify",
    "git push -u origin claude/vibrant-mayer-r46s0o",
    "git add docs/futures/README.md README.md",
    "git commit -m 'rm x; git add -A' -- a.py",
    "git commit -F - -- a.py",
    f"cat {ENV}.example",
    "ls .venv/bin",
    "python - <<'EOF'\ndel x\nrm = 1\nEOF",
    "grep -rn 'rm ' src",
    "ruff check .",
    "pytest -q tests",
    "git log --oneline -5",
]


@pytest.mark.parametrize("command", DENY)
def test_bash_denied(command):
    assert guard.check_bash(command, ROOT, _work_branch), command


@pytest.mark.parametrize("command", ALLOW)
def test_bash_allowed(command):
    assert guard.check_bash(command, ROOT, _work_branch) is None, command


def test_plain_push_depends_on_branch():
    assert guard.check_bash("git push", ROOT, _master)
    assert guard.check_bash("git push origin", ROOT, _master)
    assert guard.check_bash("git push", ROOT, _work_branch) is None


@pytest.mark.parametrize(
    "path",
    [ENV, f"sub/{ENV}.local", "config/propfund/protected_manifest.json", "scripts/register_tasks_tz.ps1",
     "config/schedule.yaml"],
)
def test_path_denied(path):
    verdict = guard.check_path(path, ROOT)
    assert verdict and verdict[0] == "deny", path


def test_production_path_asks():
    files = guard.protected_files(ROOT)
    assert files, "el manifiesto protegido debe listar ficheros"
    path = sorted(files)[0]
    verdict = guard.check_path(path, ROOT)
    assert verdict and verdict[0] == "ask" and "CHANGELOG" in verdict[1]
    assert guard.check_path(str(ROOT / path), ROOT)[0] == "ask"


def test_normal_path_allowed():
    assert guard.check_path("docs/futures/README.md", ROOT) is None
    assert guard.check_path(f"{ENV}.example", ROOT) is None


def test_ruff_reports_only_python(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    bad = tmp_path / "bad.py"
    bad.write_text("import os\n", encoding="utf-8")
    good = tmp_path / "notes.md"
    good.write_text("# x\n", encoding="utf-8")
    assert guard.check_ruff(str(good), tmp_path) is None
    if guard._ruff(tmp_path) is None and shutil.which("ruff") is None:
        pytest.skip("ruff no disponible")
    reason = guard.check_ruff(str(bad), tmp_path)
    assert reason and "F401" in reason


@pytest.mark.skipif(BASH is None, reason="Git Bash no disponible; el bash de WSL no sirve")
def test_runner_end_to_end():
    assert BASH is not None
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git add -A"}})
    out = subprocess.run(
        [BASH, RUNNER.as_posix(), "bash"], input=payload, capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0
    decision = json.loads(out.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    ok = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    out = subprocess.run(
        [BASH, RUNNER.as_posix(), "bash"], input=ok, capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_bad_json_never_blocks():
    out = subprocess.run(
        [sys.executable, str(GUARD), "bash"], input="no es json", capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0 and out.stdout == ""
