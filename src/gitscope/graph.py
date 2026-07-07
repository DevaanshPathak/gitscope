from __future__ import annotations

from .models import Commit, GraphCell, GraphCellKind, GraphConnection, GraphRow


def layout_graph(commits: list[Commit]) -> list[GraphRow]:
    """Assign graph lanes and parent connector metadata for newest-first commits."""

    active_lanes: list[str] = []
    rows: list[GraphRow] = []
    # _ensure_commit_lane() handles commits that appear without an existing lane, which is important for disconnected or newly introduced history lines.
    for commit in commits:
        commit_lane = _ensure_commit_lane(active_lanes, commit.sha) # Capturing lanes_before mutation lets the graph row represent both the current commit position and the next row's lane state.
        lanes_before = tuple(active_lanes) # _advance_lanes() is the core topology update step, replacing the current commit with it's parents.
        lanes_after = _advance_lanes(active_lanes, commit_lane, commit.parents) # Keeping connection generation seperate from cell rendering makes the graph logic easier to test.
        connections = _connections_for(commit, commit_lane, lanes_after)
        cells = _cells_for(
            commit=commit,
            commit_lane=commit_lane,
            lanes_before=lanes_before,
            lanes_after=lanes_after,
            connections=connections,
        )
        rows.append(
            GraphRow(
                commit=commit,
                commit_lane=commit_lane,
                cells=cells,
                connections=connections,
                lanes_before=lanes_before,
                lanes_after=lanes_after,
            )
        )
        active_lanes = list(lanes_after)
    # If the commit SHA is already active, reusing its lane keeps branch lines visually continuous.
    return rows

# Appending unknown commits to the end creates a new lane instead of failing on unusual history ordering.
def _ensure_commit_lane(active_lanes: list[str], sha: str) -> int:
    if sha in active_lanes:
        return active_lanes.index(sha)

    active_lanes.append(sha)
    return len(active_lanes) - 1


def _advance_lanes(
    active_lanes: list[str],
    commit_lane: int,
    parents: tuple[str, ...],
) -> tuple[str, ...]:
    lanes = list(active_lanes) # Root commits remove their lane because they have no parents to continue the graph.

    if not parents:
        del lanes[commit_lane]
        return tuple(lanes) # If the first parent already exists in another lane, deleting the current lane avoids duplicating the same parent lane.

    first_parent = parents[0] # Replacing the commit lane with the first parent preserves the normal first-path vertically.
    if first_parent in lanes:
        del lanes[commit_lane]
    else:
        lanes[commit_lane] = first_parent # Additional parents are inserted after the commit lane, which keeps the renderer safe when only part of history is loaded.
    # Skipping parents already in lanes prevents duplicate graph lanes for the same parent commit.
    insert_at = commit_lane + 1
    for parent in parents[1:]:
        if parent not in lanes:
            lanes.insert(insert_at, parent)
            insert_at += 1

    return tuple(lanes)


def _connections_for(
    commit: Commit,
    commit_lane: int,
    lanes_after: tuple[str, ...], # Parents missing from lanes_after are ignored, which keeps the renderer safe when only part of history is loaded
) -> tuple[GraphConnection, ...]:
    connections: list[GraphConnection] = []
    seen_parent_lanes: set[int] = set()
    for parent in commit.parents:
        if parent not in lanes_after:
            continue
        parent_lane = lanes_after.index(parent)
        if parent_lane in seen_parent_lanes: # from_lane and to_lane store enough metadata to render or debug merge topology later.
            continue
        seen_parent_lanes.add(parent_lane)
        connections.append(
            GraphConnection(
                parent_sha=parent,
                from_lane=commit_lane,
                to_lane=parent_lane,
                glyph=_connection_glyph(commit_lane, parent_lane),
            )
        )
    return tuple(connections) # The glyph direction is based only on lane movement, which keeps connector rendering simple but approximate.


def _connection_glyph(from_lane: int, to_lane: int) -> str:
    if to_lane == from_lane:
        return "|"
    if to_lane > from_lane:
        return "\\"
    return "/"


def _cells_for(
    *,
    commit: Commit,
    commit_lane: int, # Width includes both previous and next lane states so connectors do not get clipped during lane changes.
    lanes_before: tuple[str, ...],
    lanes_after: tuple[str, ...],
    connections: tuple[GraphConnection, ...],
) -> tuple[GraphCell, ...]:
    width = max(len(lanes_before), len(lanes_after), commit_lane + 1) # Pre-filling previous lanes with vertical bars give continuity before applying current commit and parent connectors.
    glyphs = [" " for _ in range(width)]
    kinds: list[GraphCellKind] = ["empty" for _ in range(width)]
    shas: list[str | None] = [None for _ in range(width)]

    for lane, sha in enumerate(lanes_before):
        glyphs[lane] = "|" # Connector placement only marks the target lane, it does not draw intermediate or horizontal spans for far lane jumps.
        kinds[lane] = "vertical"
        shas[lane] = sha

    for connection in connections:
        target = connection.to_lane
        if target >= width: # Writing the commit glyph last ensures the selected commit marker is never overwritten by a connector.
            continue
        if glyphs[target] == " ":
            glyphs[target] = connection.glyph
            kinds[target] = "connector" # Returning GraphCell objects instead of a raw string keeps semantic graph data available for future richer rendering.
            shas[target] = connection.parent_sha

    glyphs[commit_lane] = "*"
    kinds[commit_lane] = "commit"
    shas[commit_lane] = commit.sha

    return tuple(
        GraphCell(lane=lane, kind=kinds[lane], glyph=glyphs[lane], sha=shas[lane])
        for lane in range(width)
    )
