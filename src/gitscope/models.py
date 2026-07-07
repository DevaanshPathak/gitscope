from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Restricting ref kinds with Literal keeps sidebar/ref handling type-safe and prevents invalid ref categories.
RefKind = Literal["head", "branch", "tag"]
DiffLineKind = Literal["file", "metadata", "hunk", "added", "removed", "context", "no_newline"]
GraphCellKind = Literal["empty", "commit", "vertical", "connector"]


@dataclass(frozen=True, slots=True)
class Commit:
    """Commit metadata loaded from git log output."""

    sha: str
    short_sha: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    date: str
    subject: str


@dataclass(frozen=True, slots=True)
class GitRef:
    """A local ref displayed by the TUI."""

    kind: RefKind
    name: str
    target: str
    current: bool = False


@dataclass(frozen=True, slots=True)
class HeadInfo:
    """Current HEAD metadata for status and sidebar display."""

    sha: str
    short_sha: str
    branch: str | None


@dataclass(frozen=True, slots=True)
class DiffLine:
    """A parsed line from git diff output."""

    kind: DiffLineKind
    text: str
    old_lineno: int | None = None
    new_lineno: int | None = None


@dataclass(frozen=True, slots=True)
class GraphConnection:
    """A parent edge from the displayed commit lane to a parent lane."""

    parent_sha: str
    from_lane: int
    to_lane: int
    glyph: str


@dataclass(frozen=True, slots=True)
class GraphCell:
    """Renderable lane cell for a graph row."""

    lane: int
    kind: GraphCellKind
    glyph: str
    sha: str | None = None


@dataclass(frozen=True, slots=True)
class GraphRow:
    """Pure graph layout output for one commit row."""

    commit: Commit
    commit_lane: int
    cells: tuple[GraphCell, ...]
    connections: tuple[GraphConnection, ...]
    lanes_before: tuple[str, ...]
    lanes_after: tuple[str, ...]

    @property
    def glyphs(self) -> tuple[str, ...]:
        """Return only the display glyphs for quick rendering."""

        return tuple(cell.glyph for cell in self.cells)

    @property
    def graph(self) -> str:
        """Return a compact text graph for table display."""

        return " ".join(self.glyphs).rstrip() or "*"
