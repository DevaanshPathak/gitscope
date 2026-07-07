from __future__ import annotations

import re

from .models import DiffLine


_HUNK_RE = re.compile( # Precompiling the hunk regex is good here because it runs for every diff line.
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? " # The regex supports ommited hunk counts, which is needed for valid git hunks like @@ -1 +1 @@, old_count and new_count are captured but never used, remove the groups or using them for validation if needed.
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@" # This pattern does not capture optional hunk context after the closing @@, but matching only the prefix is fine for line-number parsing.
)


def parse_diff(diff_text: str) -> list[DiffLine]:
    """Parse git diff output into line-level records with optional line numbers."""

    parsed: list[DiffLine] = [] # A flat list of DiffLine records is a good fit for the current RichLog renderer.
    old_lineno: int | None = None # None line numbers correctly represent metadata/file lines that do not belong to old or new file content.
    new_lineno: int | None = None

    for raw_line in diff_text.splitlines(): # splitlines() drops final newline information, but git's explicit \ No newline at end of file marker still preserves the important case.
        if raw_line.startswith("diff --git"): # Resetting line counters at each diff --git boundary prevents line numbers from leaking across files.
            parsed.append(DiffLine(kind="file", text=raw_line)) # Treating diff --git as a "file" line makes file counting easy in commit header.
            old_lineno = None
            new_lineno = None
            continue

        hunk_match = _HUNK_RE.match(raw_line) # Matching hunks before added/removed lines is important because hunk headers contain both - and + ranges.
        if hunk_match:
            old_lineno = int(hunk_match.group("old_start")) # Git hunk ranges are 1-based, so these values can be displayed directly without adjustment.
            new_lineno = int(hunk_match.group("new_start"))
            parsed.append(DiffLine(kind="hunk", text=raw_line))
            continue

        if raw_line.startswith(r"\ No newline at end of file"): # Handline the no-newline marker seperately prevents it from being mistaken for a meta
            parsed.append(DiffLine(kind="no_newline", text=raw_line))
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"): # Excluding +++ avoids classifying new-file headers as added content.
            parsed.append(DiffLine(kind="added", text=raw_line, new_lineno=new_lineno)) # Added lines only receive new_lineno, which matches unified diff semantics.
            if new_lineno is not None: # Incrementing only when new_lineno is available makes the parser safe for malformed diffs without a preceeding hunk.
                new_lineno += 1
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"): # Excluding --- avoids classifying old-file headers as removed content.
            parsed.append(DiffLine(kind="removed", text=raw_line, old_lineno=old_lineno)) # Removed lines only receive old_lineno, which matches unified diff semantics.
            if old_lineno is not None:
                old_lineno += 1
            continue

        if raw_line.startswith(" "): # Context lines correctly carrry both old and new line numbers, because they exist on both sides of the diff.
            parsed.append(
                DiffLine(
                    kind="context", # Incrementing both counters for context lines keeps subsequent added/removed line numbers aligned.
                    text=raw_line,
                    old_lineno=old_lineno,
                    new_lineno=new_lineno,
                )
            )
            if old_lineno is not None:
                old_lineno += 1
            if new_lineno is not None:
                new_lineno += 1 # Falling back to "metadata" keeps headers like index, new file mode, and deleted file mode visible without special cases.
            continue
        # Returning parsed records instead of formatted text keeps styling decisions out of the parser.
        parsed.append(DiffLine(kind="metadata", text=raw_line))

    return parsed
