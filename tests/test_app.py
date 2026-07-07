from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import DataTable, Static

from gitscope.app import GitscopeApp, RefFilter
from gitscope.models import Commit, GitRef, HeadInfo


def commit(sha: str, subject: str, parents: tuple[str, ...] = ()) -> Commit:
    return Commit(
        sha=sha,
        short_sha=sha[:7],
        parents=parents,
        author_name="Ada Lovelace",
        author_email="ada@example.com",
        date="2026-07-05T12:00:00+05:30",
        subject=subject,
    )


class FakeBackend:
    def __init__(self) -> None:
        self.head = HeadInfo(
            sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            short_sha="aaaaaaa",
            branch="main",
        )
        self.main_commits = [
            commit("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "main tip", ("bbbbbbbb",)),
            commit("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "main base"),
        ]
        self.dev_commits = [
            commit("cccccccccccccccccccccccccccccccccccccccc", "dev tip", ("bbbbbbbb",)),
        ]
        self.load_calls: list[dict[str, object]] = []
        self.all_branch_calls: list[dict[str, int]] = []
        self.diff_calls: list[str] = []

    def repository_path(self) -> Path:
        return Path("C:/repo")

    def current_head(self) -> HeadInfo:
        return self.head

    def list_refs(self) -> list[GitRef]:
        return [
            GitRef(kind="head", name="HEAD", target="aaaaaaa", current=True),
            GitRef(kind="branch", name="main", target="aaaaaaa", current=True),
            GitRef(kind="branch", name="dev", target="ccccccc", current=False),
            GitRef(kind="tag", name="v1.0", target="bbbbbbb", current=False),
        ]

    def load_commits(
        self,
        *,
        ref: str = "HEAD",
        all_branches: bool = False,
        skip: int = 0,
        limit: int = 200,
    ) -> list[Commit]:
        self.load_calls.append(
            {"ref": ref, "all_branches": all_branches, "skip": skip, "limit": limit}
        )
        commits = self.dev_commits if ref == "dev" else self.main_commits
        return commits[skip : skip + limit]

    def load_all_branch_commits(self, *, skip: int = 0, limit: int = 200) -> list[Commit]:
        self.all_branch_calls.append({"skip": skip, "limit": limit})
        commits = [self.main_commits[0], self.dev_commits[0], self.main_commits[1]]
        return commits[skip : skip + limit]

    def diff_for_commit(self, sha: str) -> str:
        self.diff_calls.append(sha)
        return "\n".join(
            [
                "diff --git a/example.txt b/example.txt",
                "@@ -1 +1 @@",
                "-old",
                "+new",
            ]
        )


def make_commits(count: int) -> list[Commit]:
    commits: list[Commit] = []
    for index in range(count):
        sha = f"{index + 1:040x}"
        parent = f"{index + 2:040x}" if index + 1 < count else ""
        commits.append(commit(sha, f"commit {index + 1}", (parent,) if parent else ()))
    return commits


def status_text(app: GitscopeApp) -> str:
    return str(app.query_one("#status", Static).content)


def test_app_mounts_log_graph_refs_diff_and_status() -> None:
    async def run() -> None:
        backend = FakeBackend()
        app = GitscopeApp(backend=backend, page_size=20)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            table = app.query_one("#history", DataTable)

            assert table.row_count == 2
            assert app.selected_commit == backend.main_commits[0].sha
            assert backend.diff_calls[-1] == backend.main_commits[0].sha
            assert app.query_one("#refs") is not None
            assert app.query_one("#diff") is not None
            assert app.query_one("#status") is not None

    asyncio.run(run())


def test_moving_commit_selection_updates_diff_pane() -> None:
    async def run() -> None:
        backend = FakeBackend()
        app = GitscopeApp(backend=backend, page_size=20)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()

            assert app.selected_commit == backend.main_commits[1].sha
            assert backend.diff_calls[-1] == backend.main_commits[1].sha

    asyncio.run(run())


def test_ref_selection_reloads_log_without_mutating_git_state() -> None:
    async def run() -> None:
        backend = FakeBackend()
        app = GitscopeApp(backend=backend, page_size=20)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            await app._select_ref(RefFilter("dev", "branch", "dev"))
            await pilot.pause()
            table = app.query_one("#history", DataTable)

            assert table.row_count == 1
            assert app.selected_commit == backend.dev_commits[0].sha
            assert backend.load_calls[-1]["ref"] == "dev"
            assert backend.head.branch == "main"

    asyncio.run(run())


def test_all_branches_action_uses_all_branch_backend_path() -> None:
    async def run() -> None:
        backend = FakeBackend()
        app = GitscopeApp(backend=backend, page_size=20)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            await app.action_show_all()
            await pilot.pause()
            table = app.query_one("#history", DataTable)

            assert table.row_count == 3
            assert backend.all_branch_calls[-1] == {"skip": 0, "limit": 21}
            assert backend.load_calls[-1]["ref"] == "HEAD"

    asyncio.run(run())


def test_initial_log_load_is_bounded_by_page_size() -> None:
    async def run() -> None:
        backend = FakeBackend()
        backend.main_commits = make_commits(5)
        app = GitscopeApp(backend=backend, page_size=2)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            table = app.query_one("#history", DataTable)

            assert table.row_count == 2
            assert backend.load_calls[0]["skip"] == 0
            assert backend.load_calls[0]["limit"] == 3
            assert "more commits available" in status_text(app)

    asyncio.run(run())


def test_manual_load_more_appends_pages_and_stops_at_end() -> None:
    async def run() -> None:
        backend = FakeBackend()
        backend.main_commits = make_commits(5)
        app = GitscopeApp(backend=backend, page_size=2)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            table = app.query_one("#history", DataTable)
            assert table.row_count == 2

            app.action_load_more()
            await pilot.pause()
            assert table.row_count == 4
            assert backend.load_calls[-1]["skip"] == 2
            assert backend.load_calls[-1]["limit"] == 3

            app.action_load_more()
            await pilot.pause()
            assert table.row_count == 5
            assert backend.load_calls[-1]["skip"] == 4
            assert "end of history" in status_text(app)

            call_count = len(backend.load_calls)
            app.action_load_more()
            await pilot.pause()
            assert len(backend.load_calls) == call_count
            assert "end of history" in status_text(app)

    asyncio.run(run())


def test_navigation_near_loaded_boundary_requests_next_page() -> None:
    async def run() -> None:
        backend = FakeBackend()
        backend.main_commits = make_commits(5)
        app = GitscopeApp(backend=backend, page_size=2, auto_load_margin=0)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            table = app.query_one("#history", DataTable)
            assert table.row_count == 2

            await pilot.press("down")
            await pilot.pause()
            assert table.row_count == 4
            assert backend.load_calls[-1]["skip"] == 2

    asyncio.run(run())
