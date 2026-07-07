from gitscope.graph import layout_graph
from gitscope.models import Commit


def commit(sha: str, parents: tuple[str, ...] = ()) -> Commit:
    return Commit(
        sha=sha,
        short_sha=sha[:7],
        parents=parents,
        author_name="Ada",
        author_email="ada@example.com",
        date="2026-07-05T12:00:00+05:30",
        subject=f"commit {sha}",
    )


def assert_no_cell_collisions(rows) -> None:
    for row in rows:
        lanes = [cell.lane for cell in row.cells]
        target_lanes = [connection.to_lane for connection in row.connections]
        assert len(lanes) == len(set(lanes))
        assert len(target_lanes) == len(set(target_lanes))
        assert row.cells[row.commit_lane].kind == "commit"


def test_layout_graph_handles_empty_history() -> None:
    assert layout_graph([]) == []


def test_layout_graph_handles_root_commit() -> None:
    rows = layout_graph([commit("a1")])

    assert rows[0].commit_lane == 0
    assert rows[0].lanes_before == ("a1",)
    assert rows[0].lanes_after == ()
    assert rows[0].graph == "*"
    assert rows[0].connections == ()
    assert_no_cell_collisions(rows)


def test_layout_graph_keeps_linear_history_in_one_lane() -> None:
    rows = layout_graph(
        [
            commit("c3", ("c2",)),
            commit("c2", ("c1",)),
            commit("c1"),
        ]
    )

    assert [row.commit_lane for row in rows] == [0, 0, 0]
    assert [row.graph for row in rows] == ["*", "*", "*"]
    assert [row.lanes_after for row in rows] == [("c2",), ("c1",), ()]
    assert_no_cell_collisions(rows)


def test_layout_graph_assigns_merge_parent_lanes_without_collisions() -> None:
    rows = layout_graph(
        [
            commit("m", ("b", "a")),
            commit("b", ("c",)),
            commit("a", ("c",)),
            commit("c"),
        ]
    )

    merge_row = rows[0]
    assert merge_row.commit_lane == 0
    assert merge_row.lanes_after == ("b", "a")
    assert [(edge.parent_sha, edge.from_lane, edge.to_lane, edge.glyph) for edge in merge_row.connections] == [
        ("b", 0, 0, "|"),
        ("a", 0, 1, "\\"),
    ]
    assert rows[1].lanes_before == ("b", "a")
    assert rows[2].commit_lane == 1
    assert rows[2].lanes_after == ("c",)
    assert_no_cell_collisions(rows)


def test_layout_graph_handles_multiple_active_lanes() -> None:
    rows = layout_graph(
        [
            commit("tip", ("left", "right")),
            commit("left", ("base",)),
            commit("right", ("base",)),
            commit("base"),
        ]
    )

    assert rows[0].lanes_after == ("left", "right")
    assert rows[1].graph == "* |"
    assert rows[2].graph == "| *"
    assert rows[3].graph == "*"
    assert_no_cell_collisions(rows)


def test_layout_graph_handles_detached_style_history() -> None:
    rows = layout_graph(
        [
            commit("detached", ("parent",)),
            commit("parent"),
        ]
    )

    assert rows[0].lanes_before == ("detached",)
    assert rows[0].lanes_after == ("parent",)
    assert rows[1].lanes_before == ("parent",)
    assert rows[1].lanes_after == ()
    assert_no_cell_collisions(rows)
