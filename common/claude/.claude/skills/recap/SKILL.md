---
name: recap
description: "Interactive walkthrough of a verified feature's behavior and structure, from its exact baseline-to-final range."
argument-hint: "<feature handoff or spec> <baseline> <final>"
disable-model-invocation: true
---

# Recap a feature

Local skill (see `../../workflow/CLAUDE-ADAPTATION.md`). A walkthrough is a
conversation with the owner, which a subagent cannot hold, so it runs in the session. Run it when the owner asks for one; it
is not a delivery gate. Inputs: `$ARGUMENTS`.

1. Read the explicitly supplied feature handoff/spec and exact baseline/final range.
   Ask for any that are missing; do not guess context from the latest archive or commit.
2. Inspect the full `git diff <baseline> <final>` and `git log <baseline>..<final>`.
3. Produce a Mermaid diagram of the new behavior.
4. Walk the owner through exactly how the new code execution path flows, pausing for
   questions.

Stay read-only: do not edit files, commit, or run project checks. This keeps the
owner's structural overview and decision-making authority over the system.
