---
name: import-notes
description: Classify raw .md files in /imported/ into the Obsidian vault (/Journal/, /Projects/, /Ideas/) following the vault's import rules, then delete the source files. Use when the user asks to import, classify, or clear the imported folder.
---

## Context

This skill operates on an Obsidian vault using a bottom-up personal knowledge base.
Raw `.md` files land in `/imported/` and must be classified into `/Journal/`, `/Projects/`, or `/Ideas/`.

## Workflow

### Step 1: List files

List all `.md` files in `/imported/` (excluding `README.md`).

### Step 2: Read each file

Read every file. Each filename follows the pattern `e###.md` where higher numbers are newer entries.

### Step 3: Classify each file

For each file, determine:

**Date** (Priority order):
1. Explicit dates in text (`DD.MM.YY` format — convert to `YYYY-MM-DD`)
2. Date inferred from nearest adjacent numbered files
3. Undated (no date found)

**Type** (in order of specificity):

1. **Dated Journal Entry** — evening retrospective, reflective prose ("the day was okay", "what excited me"). No timestamps within the body.
   - Destination: `/Journal/YYYY-MM-DD-journal.md`
   - Merge multiple files with the same date into one file.

2. **Sitlog** — real-time in-the-moment log with multiple timestamps embedded in the body (e.g. "12:30", "16:19"). Captures triggers, urges, live reflections, not evening summaries.
   - Destination: `/Journal/YYYY-MM-DD-sitlog.md`
   - Merge multiple sitlog files for the same date.

3. **Undated Themed Reflection** — journal-like content but no date, focused on a specific theme.
   - Topics: `goals` (life direction, financial goals), `relationships` (Hannah, family, friends), `procrastination` (work struggles, youtube rabbit holes, triggers)
   - Destination: `/Journal/journal-<topic>-##.md` (01, 02, ...)
   - Check existing files in `/Journal/` to find the next sequence number.

4. **Project Note** — technical details, experiments, work tasks (e.g. "Moisture Sensor", "Pipelines", "ADF Adversity").
   - Destination: `/Projects/<Project Name>.md`
   - Merge notes about the same project.

5. **Idea** — short snippets, random ideas, venting without clear topic or project.
   - Destination: `/Ideas/<Short Title>.md`

6. **If ambiguous** — present your assumption to the user and wait for confirmation. Do NOT guess silently.

### Step 4: Present classification

Present a summary table:

| Source | Date | Type | Destination |
|--------|------|------|-------------|
| e001.md | — | Undated (goals) | `/Journal/journal-goals-01.md` |

Ask the user to confirm before proceeding.

### Step 5: Create files

For each file, write the classified note. Follow these rules:

**Frontmatter**:
- Journal/sitlog: `type: journal-entry`, `tags: [journal]`, `date: YYYY-MM-DD` (or `date: null` for undated), `source: imported/e###.md`
- Project: `type: project-note`, `tags: [project]`, `source: imported/e###.md`
- Idea: `type: idea`, `tags: [idea]`, `source: imported/e###.md`

**Content cleanup** — lightly clean up OCR/capture artifacts while preserving the writer's voice:
- Fix obvious typos
- Improve heading structure with `#` / `##` hierarchy
- Remove stray `[` and `]` brackets from OCR
- Do NOT rewrite the content — preserve stream-of-consciousness tone

**Linking** — on first mention, wrap entity names in `[[ ]]` links:
- People names (e.g. `Hannah` → `[[Hannah]]`)
- Places, companies, products, concepts

**Dates** — convert `DD.MM.YY` found in body text to `YYYY-MM-DD` in frontmatter.

**Merge** — when merging multiple files for the same destination:
- Combine content under appropriate headings
- List all sources in frontmatter as an array: `source: [imported/e001.md, imported/e002.md]`

### Step 6: Delete source files

Only after the user confirms the classification is correct, delete each source file from `/imported/`.

## Critical Rules

- **Ask before deleting.** Never delete a source file until the user has confirmed the classification.
- **Ask when ambiguous.** If a file could be Journal or Project, or if date inference is uncertain, present the assumption and pause.
- **Preserve voice.** Light cleanup only — fix typos, add headings, link entities. Do not rewrite.
- **Check existing files.** Before creating `journal-goals-02.md`, check that `journal-goals-01.md` already exists to determine the next number.
- **Read the README.** Always check `/imported/README.md` first — it may contain updated rules.
