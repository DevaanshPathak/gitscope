from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import DataTable, Label, ListItem, ListView, RichLog, Static

from .diff_parser import parse_diff
from .git_backend import GitBackend, GitBackendError
from .graph import layout_graph
from .models import Commit, DiffLine, GitRef, HeadInfo


RefFilterKind = Literal["all", "head", "branch", "tag"]


class BackendProtocol(Protocol):
    """Read-only backend surface used by the Textual UI."""

    def repository_path(self) -> Path: ...

    def current_head(self) -> HeadInfo: ...

    def list_refs(self) -> list[GitRef]: ...

    def load_commits(
        self,
        *,
        ref: str = "HEAD",
        all_branches: bool = False,
        skip: int = 0,
        limit: int = 200,
    ) -> list[Commit]: ...

    def load_all_branch_commits(self, *, skip: int = 0, limit: int = 200) -> list[Commit]: ...

    def diff_for_commit(self, sha: str) -> str: ...


@dataclass(frozen=True, slots=True) # RefFilter is immutable because selected refs should behave like stable UI state, not mutable display data.
class RefFilter:
    label: str
    kind: RefFilterKind
    value: str | None


class RefListItem(ListItem):
    """Selectable list item carrying a ref filter."""

    def __init__(self, ref_filter: RefFilter, label: Text) -> None:
        self.ref_filter = ref_filter # Storing the RefFilter is directly on ListItem avoids fragile parsing of label text when a ref is selected.
        super().__init__(Label(label))


class SectionListItem(ListItem):
    """Non-actionable visual section label in the refs list."""


class GitscopeApp(App[None]):
    """Textual application for read-only git history exploration."""

    TITLE = "gitscope"
    # Keeping the full textual CSS here makes the UI self-contained, but this may become worth moving to a .tcss file if the theme grows in later versions.
    CSS = """
    Screen {
        background: #020813;
        color: #E6EDF3;
        layout: vertical;
    }

    #window {
        height: 1fr;
        layout: vertical;
        background: #06101A;
        border: round #3E4567;
    }

    #main {
        height: 1fr;
        layout: vertical;
        background: #06101A;
    }

    #title-bar {
        height: 1;
        layout: horizontal;
        padding: 0 1;
        background: #06101A;
    }

    #title-name {
        width: 1fr;
        color: #9A6CFF;
        text-style: bold;
    }

    #title-controls {
        width: 13;
        color: #AAB2D5;
        text-align: right;
    }

    #top {
        height: 3fr;
    }

    #refs {
        width: 30;
        min-width: 24;
        background: #08111D;
        border-right: solid #263246;
    }

    RefListItem {
        padding: 0 1;
        color: #D8DEE9;
    }

    SectionListItem {
        padding: 1 1 0 1;
        color: #56C7FF;
    }

    #history {
        width: 1fr;
        background: #08111D;
        color: #E6EDF3;
    }

    ListView > ListItem.-highlight {
        background: #3D2178;
        color: #FFFFFF;
        text-style: bold;
    }

    ListView:focus > ListItem.-highlight {
        background: #4A2A92;
        color: #FFFFFF;
        text-style: bold;
    }

    DataTable > .datatable--header {
        background: #06101A;
        color: #56C7FF;
        text-style: bold;
    }

    DataTable > .datatable--cursor {
        background: #3D2178;
        color: #FFFFFF;
        text-style: bold;
    }

    DataTable:focus > .datatable--cursor {
        background: #4B2AA0;
        color: #FFFFFF;
        text-style: bold;
    }

    DataTable > .datatable--even-row {
        background: #06101A 45%;
    }

    DataTable > .datatable--hover {
        background: #263246;
    }

    #diff-pane {
        height: 2fr;
        background: #08111D;
        border-top: solid #263246;
    }

    #diff {
        width: 1fr;
        background: #08111D;
    }

    #diff-map {
        width: 12;
        padding: 1;
        background: #06101A;
        border-left: solid #263246;
        color: #687487;
    }

    #status {
        height: 1;
        padding: 0 1;
        background: #06101A;
        border-top: solid #263246;
        color: #AAB2D5;
    }
    """

    BINDINGS = [ # Keyboard shortcuts binding for TUI actions
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("m", "load_more", "More"),
        ("a", "show_all", "All"),
        ("h", "show_head", "HEAD"),
        ("down", "cursor_down", "Move"),
        ("up", "cursor_up", "Move"),
        ("j", "cursor_down", "Move"),
        ("k", "cursor_up", "Move"),
        ("?", "help", "Help"),
    ]

    selected_commit: reactive[str | None] = reactive(None) # selected_commit is reactive so changing the selected SHA automatically refreshes the diff plane.

    def __init__(
        self,
        *,
        backend: BackendProtocol | None = None,
        repo_start: Path | None = None,
        page_size: int = 200,
        auto_load_margin: int = 3,
    ) -> None:
        super().__init__()
        if page_size <= 0: # Validating page_size prevents invalid pagination states before any git calls are made.
            raise ValueError("page_size must be positive")
        if auto_load_margin < 0: # Validating auto_load_margin keeps cursor based incremental loading predictible.
            raise ValueError("auto_load_margin must be non-negative")

        self._backend = backend
        self._repo_start = repo_start
        self._page_size = page_size
        self._auto_load_margin = auto_load_margin
        self._head: HeadInfo | None = None # _head is cached seperately because the status bar and refs list both need current HEAD metadata.
        self._current_ref = RefFilter("HEAD", "head", "HEAD")
        self._commits: list[Commit] = []
        self._commits_by_sha: dict[str, Commit] = {}
        self._has_more = False # _has_more tracks whether the backend returned one extra commit beyond the visible page
        self._loading = False
        self._suppress_next_auto_load = False # _supress_next_auto_load prevents programmatic cursor movement from accidently triggering another page load.

    def compose(self) -> ComposeResult:
        with Container(id="window"):
            with Horizontal(id="title-bar"):
                yield Static("gitscope", id="title-name")
                yield Static("\u2014   \u25a1   \u00d7", id="title-controls")
            with Container(id="main"):
                with Horizontal(id="top"):
                    yield ListView(id="refs")
                    yield DataTable(id="history")
                with Horizontal(id="diff-pane"):
                    yield RichLog(id="diff", wrap=False, markup=False, highlight=False)
                    yield Static("", id="diff-map")
                yield Static("", id="status")

    async def on_mount(self) -> None:
        self._setup_history_table()

        if self._backend is None: # Backend discovery is delayed until mount so tests can inject a fake backend through the constructor.
            try:
                self._backend = GitBackend.discover(self._repo_start)
            except GitBackendError as exc:
                self._show_error(str(exc))
                return

        try:
            self._head = self._backend.current_head() # HEAD is loaded before refs sidebar can label the current branch beside HEAD.
            await self._render_refs()
            self._load_commits(reset=True) # Initial history loading is bounded by page_size, which keeps startup fast on large repositories.
            self.query_one("#history", DataTable).focus()
        except GitBackendError as exc:
            self._show_error(str(exc))

    def watch_selected_commit(self, selected_commit: str | None) -> None:
        if selected_commit is None:
            self._render_empty_diff("No commit selected.")
            return
        self._render_diff(selected_commit)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None: # Filtering row highlight events by table id prevents unrelated DataTable widgets from changing the selected commit.
        if event.data_table.id != "history":
            return

        sha = str(event.row_key.value) # The row key is the full commit SHA, so the displayed short SHA can stay compact without losing lookup accuracy.
        if sha in self._commits_by_sha:
            self.selected_commit = sha
            if self._suppress_next_auto_load: # This guard prevents auto-loading when the cursor was moved by code instead of direct user navigation.
                self._suppress_next_auto_load = False
                return
            self._load_more_if_cursor_near_end()

    async def on_list_view_selected(self, event: ListView.Selected) -> None: # Only ListItem selections are actionable, SectionListItem headings stay visual only.
        if event.list_view.id != "refs" or not isinstance(event.item, RefListItem):
            return

        await self._select_ref(event.item.ref_filter)

    def action_cursor_down(self) -> None: # Cursor down manually checks for pagination because moving near the bottom should load more history smoothly.
        table = self.query_one("#history", DataTable)
        table.action_cursor_down()
        self._load_more_if_cursor_near_end()

    def action_cursor_up(self) -> None:
        self.query_one("#history", DataTable).action_cursor_up()

    async def action_refresh(self) -> None: # Refresh loads HEAD, refs, and commits together so branch changes are reflected consistently.
        if self._backend is None:
            return
        try:
            self._head = self._backend.current_head()
            await self._render_refs()
            self._load_commits(reset=True)
        except GitBackendError as exc:
            self._show_error(str(exc))

    def action_load_more(self) -> None: # Manual load more is useful when the user wants the next page without navigating to the bottom.
        self._load_commits(reset=False)

    async def action_show_all(self) -> None:
        await self._select_ref(RefFilter("All branches", "all", None))

    async def action_show_head(self) -> None:
        await self._select_ref(RefFilter("HEAD", "head", "HEAD"))

    def action_help(self) -> None: # Help is rendered into the diff pane so it does not require an extra modal or screen.
        diff = self.query_one("#diff", RichLog)
        diff.clear()
        diff.write(Text("gitscope keys", style="bold #56C7FF"))
        diff.write("\u2191/\u2193 or j/k: move selected commit")
        diff.write("PgUp/PgDn: scroll focused pane")
        diff.write("Tab: switch focus")
        diff.write("a: all local branches")
        diff.write("h: HEAD")
        diff.write("m: load more")
        diff.write("r: refresh")
        diff.write("q: quit")

    def _setup_history_table(self) -> None: # The history table is configured once and later cleared with columns preserved.
        history = self.query_one("#history", DataTable)
        history.cursor_type = "row"
        history.zebra_stripes = True
        history.add_column("GRAPH", width=14) # The graph column gets a fixed width to keep branch topology aligned with commit rows.
        history.add_column("SHA", width=9)
        history.add_column("AUTHOR", width=22)
        history.add_column("DATE", width=17)
        history.add_column("SUBJECT")

    async def _render_refs(self) -> None:
        assert self._backend is not None

        refs = self._backend.list_refs() # Refs are fetched fresh whenever the sidebar is rebuilt, which keeps branch/tag display current after refresh.
        ref_view = self.query_one("#refs", ListView)
        await ref_view.clear()

        items: list[ListItem] = [SectionListItem(Label(Text("REFS", style="bold #56C7FF")))]

        head_ref = next((ref for ref in refs if ref.kind == "head"), None) # HEAD is shown only if backend reports it, avoiding a misleading sidebar item in broken repo states.
        if head_ref is not None:
            branch_label = ""
            if self._head and self._head.branch:
                branch_label = f" ({self._head.branch})"
            items.append(
                RefListItem(
                    RefFilter("HEAD", "head", "HEAD"),
                    Text.assemble(
                        ("\u2731 ", "#C7F0D2"),
                        ("HEAD", "#E6EDF3"),
                        (branch_label, "#6DD17A"),
                    ),
                )
            )

        branches = [ref for ref in refs if ref.kind == "branch"] # Branches are grouped seperately from tags so local navigation stays clear.
        if branches:
            items.append(SectionListItem(Label(Text("Local Branches", style="bold #56C7FF"))))
            for ref in branches:
                style = "#FFFFFF bold" if ref.current else "#D8DEE9" # The current branch is visually emphasized without changing its behaviour.
                marker = "* " if ref.current else "  "
                items.append(
                    RefListItem(
                        RefFilter(ref.name, "branch", ref.name),
                        Text.assemble((marker, "#6DD17A"), ("\u2387 ", "#6DD17A"), (ref.name, style)),
                    )
                )

        tags = [ref for ref in refs if ref.kind == "tag"]
        if tags:
            items.append(SectionListItem(Label(Text("Tags", style="bold #56C7FF"))))
            for ref in tags:
                items.append(
                    RefListItem(
                        RefFilter(ref.name, "tag", ref.name),
                        Text.assemble(("  \u25c7 ", "#FFD44D"), (ref.name, "#D8DEE9")),
                    )
                )

        selected_index = _active_ref_index(items, self._current_ref, self._head) # _active_ref_index keeps the sidebar section synced with the current logical filter.
        for item in items:
            await ref_view.append(item)
        if selected_index is not None:
            ref_view.index = selected_index

    async def _select_ref(self, ref_filter: RefFilter) -> None: # Ref section currently reloads commits but does not re-render refs, so shortcut selections like a and h may not visually move the sidebar highlight. 
        self._current_ref = ref_filter
        self._load_commits(reset=True)

    def _load_commits(self, *, reset: bool) -> None: # Commit loading is synchronous here as on very large repositories this could block the TUI and may deserve a worker later.
        if self._backend is None or self._loading:
            return
        if not reset and not self._has_more:
            self._render_status("end of history")
            return

        self._loading = True
        status_note: str | None = None
        try:
            skip = 0 if reset else len(self._commits)
            self._render_status(f"loading commits from {skip}")
            loaded = self._load_commit_page(skip=skip, limit=self._page_size + 1) # Requesting page_size+1 is a clean way to detect whether another page exists without a seperate count query.
            self._has_more = len(loaded) > self._page_size
            page = loaded[: self._page_size]
            self._commits = page if reset else [*self._commits, *page] # Appending pages assumes history order is stable; if refs move during refresh/load-more, duplicate SHAs could appear. 
            self._commits_by_sha = {commit.sha: commit for commit in self._commits} # The SHA lookup map keeps diff rendering fast even as the visible commit list grows.
            self._render_history_table()
            self._select_first_available_commit(reset=reset)
            status_note = "more commits available" if self._has_more else "end of history" # Status text is delayed until the page load succeeds so that footer does not claim an success after an exception.
        except (GitBackendError, ValueError) as exc:
            self._show_error(str(exc))
        finally:
            self._loading = False
            if status_note is not None:
                self._render_status(status_note)

    def _load_more_if_cursor_near_end(self) -> None: # Auto-loading is based on cursor position rather than scroll position, matching keyboard first navigation.
        if not self._has_more or self._loading or not self._commits:
            return

        table = self.query_one("#history", DataTable)
        cursor_row = table.cursor_coordinate.row
        threshold = max(0, len(self._commits) - 1 - self._auto_load_margin) # The threshold uses auto_load_margin so the next page starts loading before the user fully reaches the end.
        if cursor_row >= threshold:
            self._load_commits(reset=False)

    def _load_commit_page(self, *, skip: int, limit: int) -> list[Commit]: # This method centralizes the difference between HEAD/branch/tag loading and all-branches loading.
        assert self._backend is not None

        if self._current_ref.kind == "all": # All-branches history needs a seperate backend path because it changes the git log query shape.
            return self._backend.load_all_branch_commits(skip=skip, limit=limit)

        return self._backend.load_commits(
            ref=self._current_ref.value or "HEAD",
            skip=skip,
            limit=limit,
        )

    def _render_history_table(self) -> None: # Re-rendering the full table is simple and safe for paged data, but may become expensive if page_size grows significantly.
        table = self.query_one("#history", DataTable)
        table.clear(columns=False)

        for row in layout_graph(self._commits): # Graph layout is computed from the currently loaded commits only, so topology may become more complete after loading more pages.
            commit = row.commit
            table.add_row(
                _graph_text(row.graph),
                Text(commit.short_sha, style="#8BE28B"),
                Text(commit.author_name, style="#E6EDF3"),
                Text(_compact_date(commit.date), style="#D8DEE9"),
                Text(commit.subject, style="#E6EDF3"),
                key=commit.sha, # The full SHA is used as row key so selection remains stable even if short SHAs collide.
            )

    def _select_first_available_commit(self, *, reset: bool) -> None: # Selection recovery keeps the same commit selected after loading more, instead of jumping back to the first row.
        table = self.query_one("#history", DataTable)
        if not self._commits:
            self.selected_commit = None
            self._render_empty_diff("No commits found.")
            return

        if reset or self.selected_commit not in self._commits_by_sha: # Resetting selection on ref changes avoids showing a commit that does not belong to the new filter.
            next_selected = self._commits[0].sha
        else:
            next_selected = self.selected_commit

        selected_index = next(
            index for index, commit in enumerate(self._commits) if commit.sha == next_selected
        )
        self._suppress_next_auto_load = True # Suppressing the next auto-load is necessary because move_cursor() triggers the same highlight path as user movement.
        table.move_cursor(row=selected_index, column=0, animate=False)
        if self.selected_commit == next_selected: # If the selected SHA did not change, the diff is manually re-rendered because the reactive watcher will not fire.
            self._render_diff(next_selected)
        else:
            self.selected_commit = next_selected

    def _render_diff(self, sha: str) -> None:
        if self._backend is None:
            return

        commit = self._commits_by_sha.get(sha) # The commit lookup protects against stale selection values after reloads or backend changes.
        if commit is None:
            self._render_empty_diff("Selected commit is not loaded.")
            return

        try: # Diff loading is wrapped seperately so a broken commit diff does not crash the whole app.
            diff_text = self._backend.diff_for_commit(sha)
        except GitBackendError as exc:
            self._show_error(str(exc))
            return

        diff_lines = parse_diff(diff_text) # Parsing diff text into structured lines keep formatting logic seperate from git output retrieval.
        diff = self.query_one("#diff", RichLog)
        diff.clear()
        diff.write(_commit_header(commit, diff_lines))
        diff.write("")

        if not diff_lines: # Empty diffs are handled explicitly, which is useful for merge commits or metadata only commits.
            diff.write(Text("No file changes in this commit.", style="#5F6B7A"))
        else:
            for line in diff_lines:
                diff.write(_format_diff_line(line))

        self.query_one("#diff-map", Static).update(_diff_map(diff_lines)) # The diff map is updated from the same parsed lines as the diff pane, keeping both views consistent.
        self._render_status()

    def _render_empty_diff(self, message: str) -> None: # Avoid chaining clear().write(...) unless the Textual version guarantees clear() returns the widget.
        self.query_one("#diff", RichLog).clear().write(Text(message, style="#5F6B7A"))
        self.query_one("#diff-map", Static).update("")

    def _render_status(self, note: str | None = None) -> None:
        if self._backend is None:
            return

        selected = self._commits_by_sha.get(self.selected_commit or "") # Selected commit status is derived from _commits_by_sha, so stale selected SHAs safely display as -.
        selected_label = selected.short_sha if selected else "-"
        head_label = "unknown" # head_label is computed but never used, so this block can be removed or used in the status output.
        if self._head is not None:
            branch = self._head.branch or "detached"
            head_label = f"{branch} @ {self._head.short_sha}"

        more_label = "loading" if self._loading else ("more" if self._has_more else "end") # The footer shows whether history is loading, explandable, or exhausted, which makes pagination state visible.
        status = Text.assemble( # Status assembly uses styled text so repository state, selected ref, controls, and pagination hints stay readable in one line.
            ("> ", "#9A6CFF"),
            (_display_path(self._backend.repository_path()), "#AAB2D5"),
            ("    HEAD: ", "#AAB2D5"),
            ((self._head.branch if self._head and self._head.branch else "detached"), "#6DD17A"),
            (" @ ", "#AAB2D5"),
            ((self._head.short_sha if self._head else "unknown"), "#9A6CFF"),
            ("    ref: ", "#AAB2D5"),
            (self._current_ref.label, "#E6EDF3"),
            ("    selected: ", "#AAB2D5"),
            (selected_label, "#9A6CFF"),
            ("    ", "#AAB2D5"),
            (f"{len(self._commits)} loaded/{more_label}", "#A5ADBA"),
            ("    \u2191/\u2193 ", "#E6EDF3"),
            ("Move", "#A5ADBA"),
            ("   j/k ", "#E6EDF3"),
            ("Move", "#A5ADBA"),
            ("   PgUp/PgDn ", "#E6EDF3"),
            ("Scroll", "#A5ADBA"),
            ("   Tab ", "#E6EDF3"),
            ("Focus", "#A5ADBA"),
            ("   q ", "#E6EDF3"),
            ("Quit", "#A5ADBA"),
            ("   ? ", "#E6EDF3"),
            ("Help", "#A5ADBA"),
        )
        if note:
            status.append(f"    {note}", style="#A5ADBA")
        self.query_one("#status", Static).update(status)

    def _show_error(self, message: str) -> None: # Errors are surfaced in both the diff pane and footer, making failures visible even if the user's focus is elsewhere.
        self.query_one("#diff", RichLog).clear().write(Text(message, style="bold #FF6B57"))
        self.query_one("#diff-map", Static).update("")
        self.query_one("#status", Static).update(f"Error: {message}")


def _compact_date(value: str) -> str: # _compact_date assumes ISO-like date strings, unusual git date formats may be truncated incorrectly.
    if not value:
        return ""
    return value[:16].replace("T", " ")


def _active_ref_index(
    items: Sequence[ListItem],
    current_ref: RefFilter,
    head: HeadInfo | None,
) -> int | None:
    for index, item in enumerate(items):
        if not isinstance(item, RefListItem):
            continue
        if _ref_matches_current(item.ref_filter, current_ref, head):
            return index
    return None


def _ref_matches_current(
    candidate: RefFilter,
    current_ref: RefFilter,
    head: HeadInfo | None,
) -> bool:
    if candidate.kind == current_ref.kind and candidate.value == current_ref.value:
        return True
    if (
        current_ref.kind == "head"
        and candidate.kind == "branch"
        and head is not None
        and candidate.value == head.branch
    ):
        return True
    return False


def _display_path(path: Path) -> str: # _display_path shortens paths under the home directory, keeping the footer compact.
    try:
        resolved = path.resolve()
        home = Path.home().resolve()
        relative = resolved.relative_to(home)
    except (OSError, ValueError): # Falling back to the raw path is safer for repositories outside the home directory or paths that fail to resolve.
        return str(path)

    if str(relative) == ".":
        return "~"
    return "~/" + str(relative).replace("\\", "/")


def _graph_text(graph: str) -> Text: # _graph_text converts ASCII graph characters into a cleaner Unicode symbols for a more polished TUI.
    lane_styles = ["#6DD17A", "#8A63FF", "#7EB6FF", "#FF6B57", "#D9D94A"]
    replacements = {
        "*": "\u25cf",
        "|": "\u2502",
        "\\": "\u2572",
        "/": "\u2571",
    }
    text = Text()
    lane = 0 # Lane coloring is based on visible non-space characters, so colors may shift across complex graph rows instead of tracking stable branch lanes.
    for char in graph:
        if char == " ":
            text.append(" ")
            continue
        style = lane_styles[lane % len(lane_styles)]
        text.append(replacements.get(char, char), style=style)
        lane += 1
    return text


def _commit_header(commit: Commit, lines: Sequence[DiffLine]) -> Text: # The commit header summarizes file count before showing author/date/subject, giving the diff pane useful context.
    file_count = sum(1 for line in lines if line.kind == "file") # File count depends on the parsed "file" lines, so parser accuracy directly affects this summary.
    file_label = "file" if file_count == 1 else "files"
    return Text.assemble(
        ("commit  ", "#56C7FF"),
        (commit.sha, "#BFD7FF"),
        (f"    ({file_count} {file_label})\n", "#AAB2D5"),
        ("Author: ", "#56C7FF"),
        (f"{commit.author_name} <{commit.author_email}>", "#E6EDF3"),
        ("    Date: ", "#56C7FF"),
        (commit.date, "#E6EDF3"),
        ("\n        ", "#E6EDF3"),
        (commit.subject, "#E6EDF3"),
    )


def _format_diff_line(line: DiffLine) -> Text: # Diff formatting keeps old and new line numbers aligned, making additions and removals easier to scan.
    style_by_kind = {
        "file": "#E6EDF3 bold",
        "metadata": "#A5ADBA",
        "hunk": "#5FD7FF",
        "added": "#7CFF88 on #11351D",
        "removed": "#FF7A6E on #3A171A",
        "context": "#E6EDF3",
        "no_newline": "#A5ADBA italic",
    }
    old_number = "" if line.old_lineno is None else str(line.old_lineno)
    new_number = "" if line.new_lineno is None else str(line.new_lineno)
    return Text.assemble(
        (old_number.rjust(4), "#687487"),
        (" ", "#687487"),
        (new_number.rjust(4), "#687487"),
        ("  ", "#687487"),
        (line.text, _diff_line_style(line, style_by_kind)),
    )


def _diff_line_style(line: DiffLine, style_by_kind: dict[str, str]) -> str: # _diff_line_style should use a fallback style because an unexpected DiffLine kind would currently raise a KeyError.
    if line.kind == "metadata": # Metadata lines are further specialized so --- and +++ file headers match removed/added colors.
        if line.text.startswith("--- "):
            return "#FF6B57"
        if line.text.startswith("+++ "):
            return "#6DD17A"
        return "#A5ADBA"
    return style_by_kind[line.kind]


def _diff_map(lines: Sequence[DiffLine]) -> Text: # _diff_map compresses long diffs into a small color bar, giving users a quick sense of change distribution.
    if not lines:
        return Text("")

    bars = Text()
    max_lines = 18
    stride = max(1, len(lines) // max_lines) # The stride calculation limits the map to roughly 18 rows regardless of diff length.
    for index in range(0, len(lines), stride):
        group = lines[index : index + stride]
        style = _dominant_diff_style(group)
        bars.append("====\n", style=style)
        if len(bars.plain.splitlines()) >= max_lines:
            break
    return bars


def _dominant_diff_style(lines: Sequence[DiffLine]) -> str: # Added lines currently take priority over removed lines in mixed groups, which can hide removals in the diff map.
    kinds = [line.kind for line in lines]
    if "added" in kinds:
        return "#6DD17A"
    if "removed" in kinds:
        return "#FF6B57"
    if "hunk" in kinds:
        return "#5FD7FF"
    return "#687487"
