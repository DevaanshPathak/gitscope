## gitscope TUI Design Doc

The TUI in the banner is designed as a **read-only Git history explorer** inside a polished terminal-style window. The whole UI communicates: “local, safe, developer-focused, no destructive actions.”

---

# 1. Overall Window

The app appears inside a large dark terminal window on the right side of the banner.

**Window shape**

* Rounded rectangle container.
* Thin purple-gray border.
* Slight glow around the outer edge.
* Dark navy/black background.
* Looks like a modern terminal app, not a browser dashboard.

**Approx colors**

```text
Outer background:        #020813 / #050B14
Main app background:     #06101A
Panel background:        #08111D
Border:                 #3E4567
Purple glow/border:      #6F4DFF
Text primary:            #E6EDF3
Text muted:              #A5ADBA
Text dim:                #5F6B7A
```

---

# 2. Top Title Bar

At the top of the app window there is a slim title bar.

```text
gitscope                                      —   □   ×
```

**Left side**

* App title: `gitscope`
* Color: purple
* Approx: `#9A6CFF`

**Right side**

* Window control icons:

  * minimize
  * maximize
  * close
* Color: muted lavender-gray
* Approx: `#AAB2D5`

The title bar makes the TUI feel like a desktop terminal window while still keeping the app itself fully terminal-based.

---

# 3. Main Layout Structure

The TUI is split into four major zones:

```text
┌─────────────────────────────────────────────────────────────┐
│ Title bar: gitscope                                         │
├───────────────┬─────────────────────────────────────────────┤
│ Refs sidebar  │ Commit log + graph table                    │
│               │                                             │
│               │                                             │
├───────────────┴─────────────────────────────────────────────┤
│ Selected commit details + line-level diff viewer            │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Status bar: path, HEAD, key hints                           │
└─────────────────────────────────────────────────────────────┘
```

The UI is built around a **sidebar + main content** layout. The top half is for scanning commit history. The bottom half is for inspecting the selected commit.

---

# 4. Refs Sidebar

The left sidebar is labeled:

```text
REFS
```

**Header color**

* Bright cyan-blue.
* Approx: `#56C7FF`

The sidebar contains three groups:

## 4.1 HEAD Section

```text
* HEAD (main)
```

**Design**

* `HEAD` is white.
* `(main)` is green.
* The star/marker shows the current checked-out ref.

**Colors**

```text
HEAD text:       #E6EDF3
Current branch:  #6DD17A
Marker:          #C7F0D2
```

---

## 4.2 Local Branches Section

```text
Local Branches
  main
7F0D2
```

---

dev
feature/ui
feature/diff-view
bugfix/scroll
chore/deps

````

This section lists local branches.

**Header**

- Cyan-blue.
- Approx: `#56C7FF`

**Branch icons**

- Small green branch-like symbols.
- Approx: `#6DD17A`

**Branch text**

- Light gray.
- Approx: `#D8DEE9`

**Selected branch**

The `main` branch is selected.

```text
main
````

It has a purple rounded highlight bar.

```text
Selection background: #3D2178 / #4A2A92
Selection text:       #FFFFFF
```

This shows the active branch/ref context without implying checkout or branch switching action.

---

## 4.3 Tags Section

```text
Tags
  v1.0.0
  v0.9.0
  v0.8.0
  v0.7.0
```

**Tag icons**

* Yellow/orange tag glyphs.
* Approx: `#FFD44D`

**Tag text**

* Light gray.
* Approx: `#D8DEE9`

The tags are visually different from branches so users can quickly separate release refs from branch refs.

---

# 5. Commit Log + Graph Table

The top-right main pane is the commit history table.

It has these columns:

```text
GRAPH    SHA      AUTHOR            DATE              SUBJECT
```

## 5.1 Table Header

Headers are uppercase and bright cyan.

```text
GRAPH
SHA
AUTHOR
DATE
SUBJECT
```

**Header color**

```text
#56C7FF
```

The uppercase style makes it feel like a real terminal table while keeping it scannable.

---

## 5.2 Graph Column

The `GRAPH` column contains a visual branch topology gutter.

It uses colored vertical lines, diagonal merge lines, and circular commit nodes.

**Graph colors**

```text
Green lane:       #6DD17A
Purple lane:      #8A63FF
Blue lane:        #7EB6FF
Red/orange lane:  #FF6B57
Yellow node:      #D9D94A
Muted line:       #596579
```

**Purpose**

The graph shows:

* branch lanes
* merges
* diverging history
* commit relationships
* selected commit position

The graph is intentionally narrow so it does not dominate the commit list.

---

## 5.3 SHA Column

Example SHAs shown:

```text
e3b1c4a
7f9a2d1
2c4d8e7
9a1b6c3
d4e5f12
b7c8a90
8e3d1f4
```

**Color**

* Mostly green/cyan-tinted for SHAs.
* Approx: `#8BE28B` or `#9FEA9F`

The selected SHA is shown inside the selected row and becomes high contrast.

---

## 5.4 Author Column

Example authors:

```text
Devaansh Pathak
Alice Johnson
Bob Smith
Charlie Lee
```

**Color**

* Primary light gray/white.
* Approx: `#E6EDF3`

The author column is aligned so names are easy to scan vertically.

---

## 5.5 Date Column

Example dates:

```text
2025-06-01 18:45
2025-05-31 22:11
2025-05-30 20:33
2025-05-27 21:07
```

**Color**

* Primary light gray.
* Approx: `#D8DEE9`

The date column uses fixed-width alignment so the commit list feels structured.

---

## 5.6 Subject Column

Example subjects:

```text
feat: add ref sidebar
ui: improve graph connectors
feat: diff viewer scroll sync
fix: handle empty commits
perf: cache git log output
chore: bump dependencies
feat: add diff syntax colors
docs: update README
```

**Color**

* Primary light gray.
* Approx: `#E6EDF3`

The subject column is the widest column because it carries the most meaningful information.

---

# 6. Selected Commit Row

The selected commit is:

```text
8e3d1f4  Devaansh Pathak  2025-05-27 21:07  feat: add diff syntax colors
```

It is highlighted with a horizontal purple bar.

**Selection style**

```text
Background: #3D2178 / #4B2AA0
Text:       #FFFFFF
Accent:     #9A6CFF
```

The selection spans across the commit table, including graph, SHA, author, date, and subject.

**Design intent**

The selected row drives the lower diff pane. When the user moves up/down in the log, this selected row changes and the diff below updates.

---

# 7. Diff Pane

The bottom half of the TUI is the selected commit inspector and diff viewer.

It starts with metadata:

```text
commit  8e3d1f4e6c0b2a7d9f1a7e2b6c3d4e5f7a8b9c0d    (1 of 3 files)
Author: Devaansh Pathak <devaansh@example.com>       Date: Tue May 27 21:07:14 2025 +0530
        feat: add diff syntax colors
```

## 7.1 Metadata Colors

```text
Labels like commit/Author/Date:  #56C7FF
Commit hash:                     #BFD7FF
Author value:                    #E6EDF3
Date value:                      #E6EDF3
Selected SHA:                    #9A6CFF
```

The metadata is compact but readable. It gives the user enough context before the actual diff begins.

---

## 7.2 File Diff Header

Example:

```text
diff --git a/gitscope/ui/diff_view.py b/gitscope/ui/diff_view.py
index 91b4c2f..d7a9e31 100644
--- a/gitscope/ui/diff_view.py
+++ b/gitscope/ui/diff_view.py
```

**Colors**

```text
Normal diff header: #E6EDF3
Deleted file path:  #FF6B57
Added file path:    #6DD17A
Index line:         #A5ADBA
```

---

## 7.3 Hunk Header

Example:

```text
@@ -23,7 +23,11 @@ class DiffView(Static):
```

**Color**

* Cyan/blue.
* Approx: `#5FD7FF`

This makes hunk boundaries very easy to spot.

---

## 7.4 Line Numbers

Line numbers appear on the left of the code area.

```text
23
24
25
26
27
```

**Color**

* Muted gray.
* Approx: `#687487`

They are intentionally dim so they do not compete with the code.

---

## 7.5 Added Lines

Added lines are shown with:

```text
+
```

and green highlighting.

Example:

```text
+    return f"[bold green]{line}[/]"
```

**Colors**

```text
Added line text:       #7CFF88
Added line background: #11351D / #143D22
Plus marker:           #6DD17A
```

---

## 7.6 Removed Lines

Removed lines are shown with:

```text
-
```

and red highlighting.

Example:

```text
-    return f"[green]{line}[/]"
```

**Colors**

```text
Removed line text:       #FF7A6E
Removed line background: #3A171A / #421B1F
Minus marker:            #FF6B57
```

---

## 7.7 Normal Code Lines

Normal unchanged lines appear in light gray/white.

```text
if line.startswith('+'):
if line.startswith('-'):
return line
```

**Colors**

```text
Normal code: #E6EDF3
Strings:     #B8E986 / greenish
Keywords:    #C792EA / purple-blue
Function names / symbols: #D6E2FF
```

The syntax highlighting is subtle. The main priority is diff readability, not heavy IDE-style coloring.

---

# 8. Diff Minimap / File Overview

On the far right of the diff pane there is a small vertical overview strip.

It shows colored bars representing the diff content.

**Colors**

```text
Green bars:  added sections
Red bars:    deleted sections
Gray bars:   unchanged/context sections
Blue-gray:   inactive lines
```

**Purpose**

This gives the user a quick idea of where changes exist in the selected commit. It also visually suggests that the diff pane is scrollable.

---

# 9. Bottom Status Bar

At the bottom of the TUI, there is a single-line status bar.

Example:

```text
~/projects/gitscope    HEAD: main @ 8e3d1f4    ↑/↓ Move   j/k Move   PgUp/PgDn Scroll   Tab Focus   q Quit   ? Help
```

## 9.1 Left Side

Shows current repository path:

```text
~/projects/gitscope
```

**Colors**

```text
Folder icon: #9A6CFF
Path text:   #AAB2D5
```

## 9.2 Center

Shows current HEAD:

```text
HEAD: main @ 8e3d1f4
```

**Colors**

```text
HEAD label:  #AAB2D5
main:        #6DD17A
SHA:         #9A6CFF
```

## 9.3 Right Side

Shows key hints:

```text
↑/↓ Move
j/k Move
PgUp/PgDn Scroll
Tab Focus
q Quit
? Help
```

**Colors**

```text
Keys:        #E6EDF3
Hint labels: #A5ADBA
```

This reinforces that the app is keyboard-first and read-only.

---

# 10. Pane Borders and Separators

The panes are divided by thin lines.

**Separator color**

```text
#263246 / #303A55
```

The borders are subtle, not bright. They help separate areas without making the UI feel boxed-in or noisy.

Important separators:

* Between refs sidebar and commit table.
* Between commit table and diff pane.
* Between diff pane and status bar.
* Around the full app window.

---

# 11. Typography

The TUI uses a clean monospaced font style.

Recommended fonts:

```text
JetBrains Mono
Fira Code
Cascadia Mono
IBM Plex Mono
```

**Font behavior**

* Commit table uses fixed-width alignment.
* SHAs, dates, paths, and key hints use monospace.
* Headers are uppercase.
* Selected row uses stronger contrast.
* No decorative font inside the TUI.

---

# 12. Interaction Model Implied by the Design

The TUI is designed around keyboard navigation.

Expected behavior:

```text
↑ / ↓       Move selected commit
j / k       Vim-style movement
PgUp/PgDn   Scroll diff or log
Tab         Switch focus between panes
q           Quit
?           Help
```

There are no buttons for destructive Git actions.

Not present by design:

```text
No commit button
No checkout button
No push/pull/fetch
No rebase
No staging area
No branch creation
No file editing
```

This visually supports the product’s read-only philosophy.

---

# 13. Final Visual Personality

The TUI has a **dark cyber-terminal aesthetic** with:

* navy-black base
* purple primary accent
* cyan section headers
* green Git branch/status accents
* yellow tag accents
* red/green diff highlighting
* soft glowing borders
* structured grid layout
* keyboard-first footer

The result is a Git history viewer that feels like a mix of:

```text
git log --graph
lazygit-style pane layout
modern Textual terminal app
read-only commit explorer
```

It should feel powerful, safe, local, and portfolio-worthy.
