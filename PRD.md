# Product Requirements Document: gitscope

## Problem Statement

Git history is powerful but often awkward to inspect in a terminal. `git log --graph` is available everywhere, but it is static, dense, and hard to navigate when moving between commits and diffs. Tools like `tig` and `lazygit` are mature and capable, but they either expose broader git workflows or do not match the specific goal of building a focused, read-only history visualizer as a personal/portfolio project.

gitscope is not intended to replace every existing git UI. Its purpose is to provide a small, local-only TUI that makes commit history, branch topology, refs, and selected-commit diffs easy to inspect without adding mutating git operations.

## Goals

- Provide a read-only terminal UI for visualizing git commit history.
- Show commit metadata, branch/merge topology, refs, and selected-commit diffs in coordinated panes.
- Keep all git data access local by shelling out to the installed `git` binary.
- Keep data access, graph layout, diff parsing, and Textual UI concerns decoupled.
- Support large repositories by paginating or lazy-loading commit history instead of loading the full history up front.
- Produce a project suitable for public viewing on GitHub or in a portfolio.

## Non-Goals

- No write or mutating git operations, including staging, committing, rebasing, checkout, branch creation, reset, merge, or stash changes.
- No remote or network operations, including fetch, pull, push, clone, or API calls.
- No config file support in v1.
- No plugin system in v1.
- No word-level intraline diff highlighting in v1; diffs are line-level only.
- No libgit2, pygit2, Dulwich, or hand-rolled packfile/object parsing.
- No independent diff algorithm for v1; the app consumes `git diff` output.

## Target User

The primary user is the solo developer building gitscope: a freelance full-stack/systems developer using the project for personal productivity, learning, and portfolio presentation. Documentation and implementation quality should still be professional because the repository may be public.

## Product Scope

### 1. Commit Log Pane

Description: A scrollable list of commits for the current branch/HEAD, with an option to view all branches.

Acceptance criteria:

- Displays commit SHA, author, date, and subject for each row.
- Supports moving the selected commit through the visible log.
- Can show commits for the current branch/HEAD.
- Can show commits across all branches.
- Uses pagination or lazy loading so large repositories are not loaded entirely at startup.

### 2. Branch Graph Pane

Description: An ASCII/Unicode graph gutter aligned with the commit log, similar in spirit to `git log --graph`.

Acceptance criteria:

- Renders graph lanes next to the corresponding commit rows.
- Represents branch continuation, branching, and merge relationships.
- Handles multiple branch lanes without visual collisions.
- Handles merge commits without connectors overlapping ambiguously.
- Is implemented as a pure data transformation from commits and parent SHAs to graph row metadata, independent of Textual.

### 3. Diff Pane

Description: A scrollable pane showing the line-level diff for the selected commit.

Acceptance criteria:

- Updates reactively when the selected commit changes.
- Displays added, removed, and context lines from `git diff` output.
- Supports scrolling independently from the commit log.
- Does not implement word-level intraline highlighting in v1.
- Relies on parsed git output rather than an independent diff algorithm.

### 4. Branch/Ref Sidebar

Description: A sidebar listing local branches, tags, and HEAD.

Acceptance criteria:

- Displays local branches.
- Displays tags.
- Displays HEAD.
- Allows selecting a ref to filter or jump the log.
- Does not perform checkout or any other ref-mutating operation.

### 5. Status Bar

Description: A persistent status area for repository and navigation context.

Acceptance criteria:

- Shows the current repository path.
- Shows the current HEAD.
- Shows key hint reminders for the active UI state.
- Updates when the viewed ref or selected commit changes where applicable.

## Technical Requirements

- Runtime: Python 3.12+.
- UI framework: Textual.
- Git access: a `GitBackend` abstraction that shells out to the local `git` binary through subprocess calls.
- Git command scope: use porcelain/plumbing output such as `git log --format=...`, `git branch -v`, and `git diff`.
- State management: selected commit should be a single reactive source of truth observed by the graph/log and diff panes.
- Local-only execution: no network calls of any kind.

## Future Considerations

- Word-level intraline diff highlighting.
- Blame view.
- Config file support.
- Theme customization.
- Plugin system.

## Success Criteria for v1

- A user can install the project from source and run `gitscope` inside an existing git repository.
- The UI shows commit log, graph, diff, refs, and status information in a coordinated read-only interface.
- Selecting a commit updates the diff pane without panes reaching into each other directly.
- Large repositories are handled through lazy loading or pagination.
- Graph layout and diff parsing have unit tests independent of Textual.
- The app performs no mutating git operations and makes no network calls.
- Textual rendering is manually verified before v1 is considered done.
