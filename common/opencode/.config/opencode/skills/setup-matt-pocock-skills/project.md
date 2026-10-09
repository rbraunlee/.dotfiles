# Project delivery profile (template)

Replace placeholders with discovered and confirmed project values. Do not leave
required checks as TODO and call setup ready. Never record secret values.

## Status and domain

- Setup: ready / blocked (reason)
- Domain/ADR layout: see `domain.md`
- Tracker/operations/completion vocabulary: see `issue-tracker.md`
- Branch/commit conventions: <existing conventions>

## Feedback loops

| Purpose | Exact command | Working directory | Baseline result |
| --- | --- | --- | --- |
| Setup | <command> | <relative path> | <result> |
| Tests | <command> | <relative path> | <result> |
| Lint | <command or N/A with rationale> | <path> | <result> |
| Type-check | <command or N/A with rationale> | <path> | <result> |
| Build | <command or N/A with rationale> | <path> | <result> |

- Integration checks: <commands per merged ticket>
- Final checks: <full required commands and acceptance verification>
- Agreed test seams: <interfaces; ticket/spec may specialize>
- Baseline commit/date: <SHA/date>

## Runtime and authorization

- Access: trusted local development only; no production or deployment
- Worktree root: `/tmp/opencode/<project>/<feature>` or approved project root
- Maximum active Implementers: 2 (adjust for host/project capacity)
- Shared services/ports/databases/generated paths: <namespacing or serialization>
- Dependencies/provisioning: <development instructions, no secrets>
- Publication: local-only; hosted issue writes/pushes/one feature PR require explicit
  setup authorization, including host/repository and permitted operations
- Protected branch: `main`; final merge belongs to the user
- Persistent preview: off unless requested

## Human QA

- Inspect/run: <project-specific commands>
- QA checklist: <smoke scenarios>
- Feature worktree retained until human acceptance; uncertain work is preserved
