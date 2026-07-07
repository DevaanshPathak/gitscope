from gitscope.diff_parser import parse_diff


def test_parse_diff_classifies_line_level_output_with_line_numbers() -> None:
    diff = "\n".join(
        [
            "diff --git a/example.py b/example.py",
            "index 1111111..2222222 100644",
            "--- a/example.py",
            "+++ b/example.py",
            "@@ -10,3 +10,4 @@ def demo():",
            " unchanged",
            "-old",
            "+new",
            "+extra",
            r"\ No newline at end of file",
        ]
    )

    lines = parse_diff(diff)

    assert [line.kind for line in lines] == [
        "file",
        "metadata",
        "metadata",
        "metadata",
        "hunk",
        "context",
        "removed",
        "added",
        "added",
        "no_newline",
    ]
    assert lines[5].old_lineno == 10
    assert lines[5].new_lineno == 10
    assert lines[6].old_lineno == 11
    assert lines[6].new_lineno is None
    assert lines[7].old_lineno is None
    assert lines[7].new_lineno == 11
    assert lines[8].new_lineno == 12


def test_parse_diff_handles_empty_diff() -> None:
    assert parse_diff("") == []


def test_parse_diff_handles_single_line_hunk_ranges() -> None:
    lines = parse_diff(
        "\n".join(
            [
                "@@ -1 +1 @@",
                "-old",
                "+new",
            ]
        )
    )

    assert lines[1].old_lineno == 1
    assert lines[2].new_lineno == 1
