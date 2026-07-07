from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from gitscope.git_backend import GitBackend, GitBackendError


class RecordingRunner:
    def __init__(self, responses: dict[tuple[str, ...], str]) -> None:
        self.responses = responses
        self.calls: list[tuple[Path, tuple[str, ...], int]] = []

    def __call__(self, cwd: Path, args: Sequence[str], timeout: int) -> str:
        key = tuple(args)
        self.calls.append((cwd, key, timeout))
        if key not in self.responses:
            raise AssertionError(f"Unexpected git command: {key}")
        return self.responses[key]


def test_discover_validates_repository_root() -> None:
    runner = RecordingRunner(
        {
            ("rev-parse", "--show-toplevel"): "D:/repo\n",
            ("rev-parse", "--is-inside-work-tree"): "true\n",
        }
    )

    backend = GitBackend.discover(Path("D:/repo/subdir"), runner=runner)

    assert backend.repository_path() == Path("D:/repo")
    assert [call[1] for call in runner.calls] == [
        ("rev-parse", "--show-toplevel"),
        ("rev-parse", "--is-inside-work-tree"),
        ("rev-parse", "--show-toplevel"),
    ]


def test_current_head_reads_sha_short_sha_and_branch() -> None:
    runner = RecordingRunner(
        {
            ("rev-parse", "HEAD"): "abc123def456\n",
            ("rev-parse", "--short", "HEAD"): "abc123d\n",
            ("branch", "--show-current"): "main\n",
        }
    )

    head = GitBackend(Path("repo"), runner=runner).current_head()

    assert head.sha == "abc123def456"
    assert head.short_sha == "abc123d"
    assert head.branch == "main"


def test_list_refs_returns_head_branches_and_tags() -> None:
    runner = RecordingRunner(
        {
            ("rev-parse", "HEAD"): "abc123def456\n",
            ("rev-parse", "--short", "HEAD"): "abc123d\n",
            ("branch", "--show-current"): "main\n",
            (
                "for-each-ref",
                "--format=%(refname:short)%09%(objectname:short)%09%(HEAD)",
                "refs/heads",
            ): "main\tabc123d\t*\ndev\tdef456a\t\n",
            (
                "for-each-ref",
                "--format=%(refname:short)%09%(objectname:short)%09%(HEAD)",
                "refs/tags",
            ): "v1.0\taaa111b\t\n",
        }
    )

    refs = GitBackend(Path("repo"), runner=runner).list_refs()

    assert [(ref.kind, ref.name, ref.target, ref.current) for ref in refs] == [
        ("head", "HEAD", "abc123d", True),
        ("branch", "main", "abc123d", True),
        ("branch", "dev", "def456a", False),
        ("tag", "v1.0", "aaa111b", False),
    ]


def test_load_commits_parses_current_ref_log_page() -> None:
    runner = RecordingRunner(
        {
            (
                "log",
                "--topo-order",
                "--date=iso-strict",
                "--format=%H%x1f%h%x1f%P%x1f%an%x1f%ae%x1f%ad%x1f%s%x1e",
                "--skip=10",
                "-n20",
                "HEAD",
            ): (
                "abc123def456\x1fabc123d\x1fparent1 parent2\x1fAda Lovelace\x1f"
                "ada@example.com\x1f2026-07-05T12:00:00+05:30\x1ffeat: backend\x1e"
            ),
        }
    )

    commits = GitBackend(Path("repo"), runner=runner).load_commits(skip=10, limit=20)

    assert len(commits) == 1
    assert commits[0].sha == "abc123def456"
    assert commits[0].short_sha == "abc123d"
    assert commits[0].parents == ("parent1", "parent2")
    assert commits[0].author_name == "Ada Lovelace"
    assert commits[0].author_email == "ada@example.com"
    assert commits[0].subject == "feat: backend"


def test_load_commits_can_request_all_branches() -> None:
    runner = RecordingRunner(
        {
            (
                "log",
                "--topo-order",
                "--date=iso-strict",
                "--format=%H%x1f%h%x1f%P%x1f%an%x1f%ae%x1f%ad%x1f%s%x1e",
                "--skip=0",
                "-n5",
                "--branches",
            ): "",
        }
    )

    commits = GitBackend(Path("repo"), runner=runner).load_all_branch_commits(limit=5)

    assert commits == []
    assert runner.calls[0][1][-1] == "--branches"


def test_load_all_branch_commits_uses_requested_page_window() -> None:
    runner = RecordingRunner(
        {
            (
                "log",
                "--topo-order",
                "--date=iso-strict",
                "--format=%H%x1f%h%x1f%P%x1f%an%x1f%ae%x1f%ad%x1f%s%x1e",
                "--skip=25",
                "-n50",
                "--branches",
            ): "",
        }
    )

    GitBackend(Path("repo"), runner=runner).load_all_branch_commits(skip=25, limit=50)

    assert runner.calls[0][1][-3:] == ("--skip=25", "-n50", "--branches")


def test_load_commits_rejects_invalid_page_windows() -> None:
    backend = GitBackend(Path("repo"), runner=RecordingRunner({}))

    with pytest.raises(ValueError):
        backend.load_commits(skip=-1)

    with pytest.raises(ValueError):
        backend.load_commits(limit=0)


def test_diff_for_commit_uses_git_diff_without_external_diff_or_color() -> None:
    runner = RecordingRunner(
        {
            (
                "diff",
                "--no-ext-diff",
                "--no-color",
                "--find-renames",
                "--patch",
                "abc123d^!",
            ): "diff --git a/a.txt b/a.txt\n",
        }
    )

    diff = GitBackend(Path("repo"), runner=runner).diff_for_commit("abc123d")

    assert diff.startswith("diff --git")
    assert runner.calls[0][1][0] == "diff"


def test_backend_rejects_unsafe_refs_and_shas() -> None:
    backend = GitBackend(Path("repo"), runner=RecordingRunner({}))

    with pytest.raises(ValueError):
        backend.load_commits(ref="--all")

    with pytest.raises(ValueError):
        backend.diff_for_commit("HEAD")


def test_backend_rejects_unsupported_git_command_shapes() -> None:
    backend = GitBackend(Path("repo"), runner=RecordingRunner({}))

    with pytest.raises(GitBackendError):
        backend._git(["checkout", "main"])

    with pytest.raises(GitBackendError):
        backend._git(["branch", "-D", "main"])


def test_validate_repository_rejects_non_work_tree() -> None:
    runner = RecordingRunner({("rev-parse", "--is-inside-work-tree"): "false\n"})

    with pytest.raises(GitBackendError):
        GitBackend(Path("repo"), runner=runner).validate_repository()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_backend_reads_real_temporary_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "config", "user.email", "test@example.com")

    (repo / "example.txt").write_text("one\n", encoding="utf-8")
    _run_git(repo, "add", "example.txt")
    _run_git(repo, "commit", "-m", "initial commit")

    (repo / "example.txt").write_text("one\ntwo\n", encoding="utf-8")
    _run_git(repo, "add", "example.txt")
    _run_git(repo, "commit", "-m", "update example")
    _run_git(repo, "branch", "dev")
    _run_git(repo, "tag", "v1.0")

    backend = GitBackend.discover(repo)
    head = backend.current_head()
    refs = backend.list_refs()
    commits = backend.load_commits(limit=10)
    all_commits = backend.load_all_branch_commits(limit=10)
    diff = backend.diff_for_commit(head.short_sha)

    assert backend.validate_repository() == repo
    assert backend.repository_path() == repo
    assert head.branch == "main"
    assert {ref.name for ref in refs} >= {"HEAD", "main", "dev", "v1.0"}
    assert commits[0].subject == "update example"
    assert len(all_commits) >= len(commits)
    assert "diff --git" in diff
    assert "+two" in diff


def _run_git(cwd: Path, *args: str) -> None:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test User",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test User",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
