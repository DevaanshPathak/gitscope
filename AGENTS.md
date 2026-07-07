# AGENTS.md

Guidance for AI coding agents working on gitscope. Follow these rules unless the user explicitly overrides them.

## Project Boundary

gitscope is a read-only Python 3.12+ Textual TUI for visualizing git commit history. It must operate only on repositories already present on disk. It must not make network calls or perform mutating git operations.

## Architecture

- `DESIGN.md` is compulsory for all TUI work. Read it before changing Textual layout, colors, widgets, pane structure, key hints, or visual styling, and keep UI implementation aligned with it.
- Keep git data access behind a `GitBackend` abstraction.
- `GitBackend` shells out to the local `git` binary with subprocess and parses git output.
- Do not use libgit2, pygit2, Dulwich, or hand-rolled packfile/object parsing.
- Keep Textual UI code separate from git access, graph layout, and diff parsing.
- Implement graph layout as pure data transformation: input commit metadata and parent SHAs; output rows containing lane/connector metadata for rendering.
- Keep diff parsing separate from Textual so it can be unit-tested without a terminal.
- Use Textual reactive state with one source of truth for the selected commit. Panes should observe shared state rather than reaching into each other.
- Design log loading for pagination or lazy loading. Do not shell out for the entire history up front in large repositories.

## Coding Conventions

- Use type hints for application code.
- Prefer dataclasses, typed dictionaries, or explicit model objects for structured git/graph/diff data.
- Keep public API surfaces documented with concise docstrings or comments where intent is not obvious.
- Prefer pure functions for graph layout and diff parsing.
- Keep subprocess command construction centralized in the git data layer.
- Treat git command output as an external interface: parse deliberately and add tests for edge cases.
- Do not add implementation code without matching the existing project structure once one exists.
- Do not introduce broad abstractions until repeated code or testability requires them.

## Testing Approach

- Unit-test graph layout independently of Textual.
- Unit-test diff parsing independently of Textual.
- Test git backend behavior with controlled fixtures or mocked subprocess calls where practical.
- Keep UI tests lighter, but verify key flows that connect selection state, log rendering, graph rendering, and diff updates.
- Include cases for merge commits, multiple branch lanes, root commits, empty diffs, tags, detached HEAD, and large-history pagination when those features are implemented.

## Verification Before Done

- Run the test suite before considering a coding task complete.
- Run any configured formatter, linter, or type checker once those tools exist.
- Manually run the Textual app in a real git repository for UI-affecting changes.
- Do not assume Textual rendering works without checking it.
- Confirm changes do not add network access or mutating git commands.
- Confirm documentation stays aligned with actual behavior.

## What Not To Do

- Do not add staging, committing, checkout, reset, merge, rebase, stash, branch creation, tag creation, push, pull, fetch, clone, or other mutating/remote git operations.
- Do not add network calls.
- Do not add config file support for v1 unless the user changes scope.
- Do not add a plugin system for v1 unless the user changes scope.
- Do not add word-level intraline diff highlighting for v1.
- Do not bypass `GitBackend` from UI code.
- Do not couple graph layout to Textual widgets.
- Do not parse git object databases directly.

## Git and Devlog Rules

- Do not push to GitHub unless and until the user asks.
- If the user asks to push, push to `main`. Do not create pull requests or different branches unless the user explicitly overrides this rule.
- When asked to write a devlog, create a folder named `devlog`, add it to `.gitignore`, and write numbered Markdown entries there.
- The first devlog is `devlog/1.md`, the second is `devlog/2.md`, and so on.
- Keep every devlog entry under 4000 characters.

## Agent Workflow

- Read the relevant docs before editing: `README.md`, `PRD.md`, `DESIGN.md`, `roadmap.md`, and this file.
- Keep changes tightly scoped to the user's request.
- Preserve read-only/local-only behavior as a hard product constraint.
- Ask only when a decision cannot be inferred from local context or these docs.
- If scope is ambiguous, add a TODO comment in documentation or ask the user rather than silently expanding v1.
- Never revert user changes unless the user explicitly asks.
