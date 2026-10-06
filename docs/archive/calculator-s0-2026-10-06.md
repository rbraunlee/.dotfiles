# Calculator S0 trial — 2026-10-06

The one-slice calculator trial ran in an independent clone and was locally accepted
by the user. This is a historical outcome, not qualification of future workflow
automation or sandbox isolation. The original checkout was reported unchanged
*during* the trial; afterward the user fast-forwarded its `main` to the candidate.

| Item | Commit |
| --- | --- |
| Recorded baseline | `9c95bac6722b15b2b5f6ed06c86b9d817ba48d10` |
| `s0/display-tail` slice | `b08f8023172098a7a617caf6f1eb0ad0df9c2ad6` |
| `s0/candidate` | `12164546a97b90a8c636925bdff5c6cf0f9d485c` |

User-reported results: slice and candidate each passed 14/14 `unittest` tests
and `compileall`; Tester passed acceptance and fresh Reviewer found no blockers.
No Builder repair was needed. After the initial handoff, the user confirmed
manual TUI behavior in the clone. These checks and acceptance reports were not
rerun for this documentation update.

Read-only Git inspection for this record found the clone on `s0/candidate` at
`1216454`, with `s0/display-tail` at `b08f802`; the two commits have identical
trees. The original calculator checkout is now on `main` at `1216454` with an
untracked `docs/s0-trial.md` (the trial spec). Neither calculator location was
modified for this record. The calculator repo has no hosted remote; nothing
was pushed, published or deployed.

Friction and follow-up: the initial Builder model was unsupported (corrected
in `.dotfiles` commit `2e00158`). Reviewer initially opened in the wrong
location, then moved to the clone; lacking shell/external diff access, it used
a temporary untracked diff copy in the clone, later removed. Reviewer still
independently examined the final diff. No persistent shell approvals were
granted. The post-trial permissions/routing/diff correction in `.dotfiles`
commit `725e0aa` was verified offline on installed OpenCode v2.0.22, **not**
tested in a subsequent real trial. The trial does not prove fully automatic
routing or a sandbox boundary.
