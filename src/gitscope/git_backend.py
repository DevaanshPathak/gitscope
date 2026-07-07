from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from .models import Commit, GitRef, HeadInfo


GitRunner = Callable[[Path, Sequence[str], int], str] # GitRunner injection makes the backend easy to test without spawning real git subprocesses.

_LOG_FORMAT = "%H%x1f%h%x1f%P%x1f%an%x1f%ae%x1f%ad%x1f%s%x1e" # The custom log format uses seperators that are unlikely to appear in a normal commit field, making parsing more reliable.
_REF_FORMAT = "%(refname:short)%09%(objectname:short)%09%(HEAD)"
_SAFE_REVISION = re.compile(r"^[A-Za-z0-9._/\-]+$") # _SAFE_REVISION prevents obvious option injection before user-selectable refs are passed to git.
_SAFE_SHA = re.compile(r"^[0-9A-Fa-f]{4,40}$") # _SAFE_SHA accepts short SHAs, but very short SHAs can be ambiguous in large repositories.


class GitBackendError(RuntimeError):
    """Raised when read-only git data cannot be loaded."""


class GitBackend:
    """Read-only data-access layer around the local git CLI."""

    def __init__(
        self,
        repo_path: Path,
        *,
        runner: GitRunner | None = None,
        timeout: int = 10, # A timeout is important because git commands can otherwise hang the TUI.
    ) -> None:
        self.repo_path = Path(repo_path)
        self._runner = runner
        self._timeout = timeout

    @classmethod
    def discover(
        cls,
        start: Path | None = None,
        *,
        runner: GitRunner | None = None,
        timeout: int = 10,
    ) -> GitBackend:
        """Discover and validate the containing git repository."""

        start_path = Path.cwd() if start is None else Path(start)
        root = _run_git(start_path, ["rev-parse", "--show-toplevel"], timeout, runner).strip() # rev-parse --show-toplevel is the right source of truth for finding the repository root.
        if not root:
            raise GitBackendError("Unable to locate git repository root.")

        backend = cls(Path(root), runner=runner, timeout=timeout)
        backend.validate_repository()
        return backend

    def validate_repository(self) -> Path:
        """Validate that the backend points at a git work tree and return its root."""

        inside = self._git(["rev-parse", "--is-inside-work-tree"]).strip() # This rejects bare repositories, which is reasonable because the app is designed around a local work tree.
        if inside != "true":
            raise GitBackendError(f"{self.repo_path} is not inside a git work tree.")

        root = self._git(["rev-parse", "--show-toplevel"]).strip()
        if not root:
            raise GitBackendError("Unable to resolve git repository root.")

        return Path(root)

    def repository_path(self) -> Path:
        """Return the repository root path used by this backend."""

        return self.repo_path

    def current_head(self) -> HeadInfo:
        """Return current HEAD commit and checked-out branch, if any."""

        sha = self._git(["rev-parse", "HEAD"]).strip() # rev-parse HEAD will fail in an empty repository, so the UI should handle that error cleanly.
        short_sha = self._git(["rev-parse", "--short", "HEAD"]).strip()
        branch = self._git(["branch", "--show-current"]).strip() or None # Treating an empty branch name as None correctly handles detached HEAD state.
        return HeadInfo(sha=sha, short_sha=short_sha, branch=branch)

    def list_refs(self) -> list[GitRef]:
        """Return HEAD, local branches, and local tags."""

        head = self.current_head()
        refs = [
            GitRef(
                kind="head",
                name="HEAD",
                target=head.short_sha,
                current=True,
            )
        ]
        refs.extend(self._list_namespace_refs("branch", "refs/heads"))
        refs.extend(self._list_namespace_refs("tag", "refs/tags"))
        return refs

    def load_commits( # Pagination validation here prevents invalid skip/limit values from reaching git.
        self,
        *,
        ref: str = "HEAD",
        all_branches: bool = False,
        skip: int = 0,
        limit: int = 200,
    ) -> list[Commit]:
        """Load a page of commits for one ref or all branches."""

        if skip < 0:
            raise ValueError("skip must be non-negative")
        if limit <= 0:
            raise ValueError("limit must be positive")

        args = [
            "log",
            "--topo-order", # --topo-order is important because the graph view depends on meaningful commit topology.
            "--date=iso-strict",
            f"--format={_LOG_FORMAT}",
            f"--skip={skip}", # --skip pagination is simple, but it can become unstable if refs move while the app is open.
            f"-n{limit}",
        ]

        if all_branches: # --branches correctly keeps all branches mode local-only.
            args.append("--branches")
        else:
            _validate_revision(ref) # Ref validation is important because selected refs eventually become git command arguments.
            args.append(ref)

        return _parse_log(self._git(args))

    def load_all_branch_commits(self, *, skip: int = 0, limit: int = 200) -> list[Commit]:
        """Load a page of commits reachable from local branches."""

        return self.load_commits(all_branches=True, skip=skip, limit=limit)

    def diff_for_commit(self, sha: str) -> str:
        """Return the selected commit patch using git diff."""

        _validate_sha(sha) # SHA validation before building sha^! prevents arbitrary revision syntax from reaching git diff.
        return self._git(
            [
                "diff", # sha^! correctly limits the diff only to the selected commit.
                "--no-ext-diff", # --no-ext-diff prevents external diff tools from running inside a read-only viewer.
                "--no-color", # --no-color keeps parser input free of ANSI escape codes.
                "--find-renames",
                "--patch",
                f"{sha}^!",
            ]
        )

    def _list_namespace_refs(self, kind: Literal["branch", "tag"], namespace: str) -> list[GitRef]:
        output = self._git(
            [
                "for-each-ref",
                f"--format={_REF_FORMAT}",
                namespace,
            ]
        )
        refs: list[GitRef] = []
        for line in output.splitlines():
            if not line:
                continue
            name, target, current = line.split("\t", maxsplit=2) # This split assumes exactly three tab-seperated fields, malformed git output would currently raise a raw ValueError.
            refs.append(
                GitRef(
                    kind=kind,
                    name=name,
                    target=target,
                    current=current == "*",
                )
            )
        return refs

    def _git(self, args: Sequence[str]) -> str: # Centralizing git execution keeps timeout, cwd, runner injection, and read only checks consistent.
        return _run_git(self.repo_path, args, self._timeout, self._runner)


def _run_git(
    cwd: Path,
    args: Sequence[str],
    timeout: int,
    runner: GitRunner | None = None,
) -> str:
    _ensure_read_only_args(args) # Read-only validation happens before runner injection, so tests still pass through the safety layer.

    if runner is not None:
        return runner(cwd, args, timeout)

    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0" # GIT_TERMINAL_PROMPT=0 prevents git from blocking the app on credential prompts.

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace", # errors = "replace" avoids crashes on unusual commit metadata, but may display replacement characters.
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise GitBackendError("git executable was not found on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitBackendError(f"git {' '.join(args)} timed out.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise GitBackendError(f"git {' '.join(args)} failed: {detail}") from exc

    return result.stdout


def _ensure_read_only_args(args: Sequence[str]) -> None: # _ensure_read_only_args() is the main gaurdrail enforcing the project's read only promise.
    if not args:
        raise GitBackendError("Missing git command.")

    command = args[0]
    if command == "rev-parse":
        allowed = {
            ("rev-parse", "--show-toplevel"),
            ("rev-parse", "--is-inside-work-tree"),
            ("rev-parse", "HEAD"),
            ("rev-parse", "--short", "HEAD"),
        }
        if tuple(args) in allowed:
            return
    elif command == "branch":
        if tuple(args) == ("branch", "--show-current"):
            return
    elif command == "for-each-ref":
        if (
            len(args) == 3
            and args[1] == f"--format={_REF_FORMAT}"
            and args[2] in {"refs/heads", "refs/tags"}
        ):
            return
    elif command == "log": # The strict log command allowlist is safe, but future harmless flags will need to be added here.
        if len(args) == 7 and list(args[1:4]) == [
            "--topo-order",
            "--date=iso-strict",
            f"--format={_LOG_FORMAT}",
        ]:
            _validate_log_page_args(args[4], args[5])
            if args[6] != "--branches":
                _validate_revision(args[6])
            return
    elif command == "diff":
        if len(args) == 6 and list(args[1:5]) == [
            "--no-ext-diff",
            "--no-color",
            "--find-renames",
            "--patch",
        ]:
            if not args[5].endswith("^!"): # Requiring ^! ensures diffs are only generated for one selected commit range.
                raise GitBackendError("git diff target must be a selected commit range.")
            _validate_sha(args[5][:-2])
            return

    raise GitBackendError(f"Unsupported git command shape: git {' '.join(args)}") # Including the unsupported git command shape in the error will make backend changes easier to debug.


def _parse_log(output: str) -> list[Commit]:
    commits: list[Commit] = []
    for raw_record in output.split("\x1e"): # Record-seperator parsing matches _LOG_FORMAT and avoids newline based parsing issues.
        record = raw_record.strip("\n")
        if not record:
            continue

        parts = record.split("\x1f", maxsplit=6) # maxsplit=6 keeps commit subjects intact, even when they contain normal spaces or punctuation.
        if len(parts) != 7: # Raising on unexpected log output is better than silently rendering incorrect commits.
            raise GitBackendError("Unexpected git log output.")

        sha, short_sha, parents, author_name, author_email, date, subject = parts
        commits.append(
            Commit(
                sha=sha,
                short_sha=short_sha,
                parents=tuple(parent for parent in parents.split() if parent), # Parent SHAs are preserved for graph layout.
                author_name=author_name,
                author_email=author_email,
                date=date,
                subject=subject,
            )
        )

    return commits


def _validate_revision(ref: str) -> None: # _validate_revision() blocks empty refs and option-like refs before they reach git.
    if not ref or ref.startswith("-") or not _SAFE_REVISION.fullmatch(ref):
        raise ValueError(f"Unsafe git revision: {ref!r}")


def _validate_sha(sha: str) -> None:
    if not _SAFE_SHA.fullmatch(sha): # Using full SHAs internally would be safer than accepting 4-character abbreviations.
        raise ValueError(f"Expected a commit SHA, got {sha!r}")


def _validate_log_page_args(skip_arg: str, limit_arg: str) -> None:
    if not skip_arg.startswith("--skip="):
        raise GitBackendError("git log skip argument is required.")
    if not limit_arg.startswith("-n"):
        raise GitBackendError("git log limit argument is required.")

    try:
        skip = int(skip_arg.removeprefix("--skip="))
        limit = int(limit_arg.removeprefix("-n"))
    except ValueError as exc:
        raise GitBackendError("git log pagination arguments must be numeric.") from exc

    if skip < 0 or limit <= 0: # Final pagination range checks prevent expensive or nonsensical git log calls.
        raise GitBackendError("git log pagination arguments are out of range.")
