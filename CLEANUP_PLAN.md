# Repository cleanup plan

Audit date: 2026-10-26. Planning only; no branches deleted, configuration changed,
packages stowed into the real home, commits created, or pushes performed by this audit.

Implementation progress (2026-10-26): started phase 1. Added `tests/run.py`,
documented prerequisites and suite selection, and removed shared temporary-directory
assumptions from fixtures. All 265 existing tests pass without manually preparing `/tmp/opencode`;
three additional runner checks pass for hidden-suite discovery, process isolation,
failure continuation, empty suites and invalid selection. CI and later phases
remain pending. No branch/worktree retirement has been performed.

Phase 2 progress: removed seven broken tmux gitlinks from the index while keeping
their local directories. Git and Stow ignore legacy plugin folders. The tmux
configuration explicitly routes TPM to `~/.tmux/plugins/`, outside the Stow
checkout; installation/migration instructions now describe that single path.
Nine tmux checks pass, including native plugin-path validation and temporary-home
install/restow/unstow, conflict refusal and plugin-data preservation. Other
packages' installation coverage, inventory, dependency policy and CI remain pending.

Next phase 2 slice: added `PACKAGES.md` with all 19 tracked packages, application
prerequisites, optional integrations, reload guidance, validation and legacy status.
Root and agent installation examples use `--no-folding`; Bash and agent clients
are opt-in and Voxtype has a separate documented adoption path. Added temporary
checkout/home coverage for every package's install/restow/unstow and conflicting
files, plus combined common+Linux/common+macOS layouts, cross-package links and
runtime-state preservation. Native desktop/macOS behavior remains outside these
filesystem checks. Dependency policy, CI and branch retirement remain pending.

Dependency policy completed (2026-10-28): added lockfile v3 files for OpenCode,
Codex and Claude, retaining the existing OpenCode resolution and direct versions.
Setup uses `npm ci`; Claude registration stops on install failure. All three
temporary clean installs succeeded with unchanged locks and both executable links.
Documented maintenance and the existing Brave deprecation/draw.io runtime-cache
limitations in `DEPENDENCIES.md`. All 277 tests across 13 suites pass. CI and
branch retirement remain pending. The completed cleanup is ready for the
commit/push checkpoint; the pre-existing local Codex configuration edit is excluded.

## Baseline and scope

- GNU Stow layout (`common`, `linux`, `macos`) is worth keeping. Avoid a wholesale reorganization.
- Initial main was `306fde5`. Another actor advanced main to `9936f59` during the
  audit, incorporating Claude Code. This plan uses the latter state. Origin was
  fetched successfully; `origin/main` remained `306fde5` at the last check.
- 68 local branches: main, 62 other branches whose tips are ancestors of main,
  and five non-ancestor branches. Three worktrees including the primary checkout.
- Existing local modification: `common/codex/.codex/config.toml`. Preserve it;
  the local project entry is not part of the committed configuration.
- Review covered tracked layout, installation docs, representative configuration,
  test suites, branch ancestry, patch equivalence and worktree state. It was not
  an interactive desktop/macOS validation or a full security audit.

## 1. Make verification reproducible — highest priority

Evidence:

- `python3 -m unittest discover -s tests` discovers zero tests.
- Tests live in nested package directories without a root discovery entry point;
  OpenCode additionally keeps its suite inside its Stow package.
- Neovim, part of Zsh, Hyprland, Wofi and OpenCode assume `/tmp/opencode` exists.
  The first run failed in those suites with `FileNotFoundError`.
- With that directory temporarily supplied, all 265 tests passed: Claude 30,
  Codex 6, Neovim 43, tmux 6, Zsh 64, Hyprland 18, Voxtype 4, Waybar 35,
  Wofi 5, OpenCode 54. The temporary directory was removed afterward.

Work:

1. Add one documented test command that enumerates every suite, including
   hidden package-local suites, aggregates failures and rejects zero tests.
2. Replace assumed temporary parents with self-contained fixtures. Keep the
   narrowly scoped OpenCode runtime fixture boundary where required, but create
   and clean it explicitly; ordinary unit tests should use standard temp dirs.
3. Document binary prerequisites and distinguish static checks, native-tool
   tests and live desktop checks. Report skipped prerequisites clearly.
4. Add CI for the portable checks first, then Linux native checks. Add macOS
   coverage where supported; do not imply Linux proves desktop/macOS behavior.

Acceptance: a fresh checkout runs the documented command without manually
creating directories; every suite is accounted for and failures propagate.

## 2. Fix fresh-clone installation

Evidence:

- Seven tmux plugin paths are tracked as gitlinks (`160000`), with no
  `.gitmodules`. `git submodule status` fails with “no submodule mapping found”.
- tmux config and root README use `~/.tmux/plugins/tpm`, while the dangling
  gitlinks live under the package's `.config/tmux/plugins` directory.
- Root prerequisites list only Stow, npm and a Nerd Font. Actual packages and
  tests require additional tools; root Linux installation omits Voxtype.
- MCP package manifests pin direct versions but do not track lockfiles;
  OpenCode explicitly ignores package-manager locks.

Work:

1. Choose TPM as the single tmux plugin installation mechanism, consistent with
   existing bootstrap instructions. Remove obsolete gitlink entries from the
   index while preserving any local plugin checkout data; document one path.
2. Add a package inventory: platform, prerequisites, optional integrations,
   install flags, reload action and verification command. Mark Bash and Qtile
   legacy status explicitly rather than presenting everything as equally active.
3. Exercise Stow install/restow/unstow in an empty temporary home for each
   supported package and supported combination. Check cross-package symlinks
   (notably Claude -> OpenCode), conflicts and runtime state preservation.
4. Use `--no-folding` consistently for agent packages where fresh-home directory
   folding could otherwise place generated state inside the repository.
5. Pick a package manager/lockfile policy for MCP dependencies. If reproducible
   installs are intended, commit locks and document frozen installs; otherwise
   explicitly document that transitive versions can drift.

Acceptance: clean clone has no broken submodule metadata; documented setup works
in an empty target and refuses conflicting existing configuration without loss.

## 3. Retire Git branches and worktrees

Refresh origin and record ref SHAs immediately before execution: the repository
changed during this audit. Check for active sessions as well as dirty files;
a clean worktree alone does not mean it is unused. Save a ref manifest or Git
bundle before bulk retirement. Never force-delete all non-main branches.

### Already integrated local branches

62 non-main branches are ancestors of main. Of these, 60 are not attached to a
worktree and are straightforward retirement candidates after rechecking ancestry.
The complete candidate inventory is in the appendix.

Two integrated branches have clean worktrees and need separate session checks:

- `feature/claude`: `/home/rbl/.local/share/claude-worktrees/dotfiles/feature-claude`.
  Tip equals main, but this worktree changed during the audit. Preserve until its
  active work is finished and the intended main state is durably retained.
- `feature/common-opencode-ship-20261020-a`:
  `/home/rbl/.local/share/opencode/worktrees/dotfiles-cleanup/common-opencode-ship-20261020-a`.
  Integrated; remove the unused worktree before retiring its branch.

Prefer `git branch -d` for integrated refs. If it refuses, investigate upstream
and worktree state rather than escalating blindly. Prune worktree metadata only
after checking actual directories and registrations.

### Five branches not ancestral to main

- `feature/linux-waybar-paru-empty-20261012-a` and
  `ticket/linux-waybar-paru-empty-01-20261012-a`: both point to `1e0ac84`.
  `git cherry main <branch>` reports the commit as patch-equivalent to an
  integrated change. Current Waybar tests pass. Retire after recording that
  equivalence; normal ancestry-based deletion may refuse, so handle explicitly.
- `feature/recovery-permissions-20261010-a`: two unmatched patches (`1f0597c`,
  `ef53386`) adjusting OpenCode recovery review permissions, including a command
  containing dated Neovim branch names. Compare remaining behavior against the
  current permission tests. Preserve any still-needed general capability as a
  focused change; do not merge the historical branch wholesale.
- `ticket/common-opencode-local-dictation-memory-01-20261018-a`: unmatched
  `0917b44`, an earlier Voxtype draft. Main has later configuration/service work;
  the draft uses `backend = "local"` where main uses `mode = "local"` and lacks
  later output safeguards. Likely superseded, but reconcile its full patch before
  retiring it; patch-ID mismatch is not proof of missing functionality.
- `experiment/opencode-routine-w1-w2-checkpoint`: three commits outside main,
  one patch-equivalent and two unmatched. Adds approximately 24,795 lines across
  84 files, including an application and historical documents. Keep as an
  explicitly archived experiment or extract to a separate repository if resumed.
  Do not fold this into a dotfiles cleanup.

### Remote branches

`git ls-remote --heads origin` confirmed five branches:

- Keep `main`.
- `changes`, `mac_changes`, `maintower_branch`: all tips are ancestors of local
  main (also already ancestral to the original main before the Claude advance).
  Candidates for remote retirement after checking external references/open PRs.
- Keep `experiment/opencode-routine-w1-w2-checkpoint` until the archival decision.

Remote PR/deployment references were not inspected. No remote deletion is part
of this analysis. Remote removal and `fetch --prune` are separate operations;
pruning local tracking refs does not delete remote branches.

Acceptance: main plus intentionally active/archived branches remain, no abandoned
worktrees remain, and every unmatched commit has a recorded disposition.

## 4. Simplify configuration and documentation deliberately

1. Resolve shell leftovers: `linux/bash/.bashrc` still prepends
   `/home/rudolf/.local/bin`; common Zsh contains hardcoded macOS paths and TODOs.
   Decide whether Bash remains supported, then replace obsolete paths with
   guarded user/platform-derived values. Validate macOS package paths on macOS
   rather than accepting historical comments as current package facts.
2. Keep `common` cross-platform and isolate platform-specific behavior where it
   helps. Do not split the working Zsh configuration merely for file count.
3. Review hardcoded OpenCode home/worktree permission paths. Make supported
   host customization explicit without broadening permission boundaries or
   assuming environment interpolation is supported in every config format.
4. Audit duplicated agent skills by content and provenance. Codex intentionally
   has an adapted independent snapshot; Claude already links unchanged skills
   to OpenCode. Preserve intentional provider differences, upstream metadata
   and licenses. Add drift reporting before attempting shared generation.
5. Review `.gitignore`: root docs allowlist references absent documents;
   experimental-package bytecode rules survive archival removal. Simplify only
   after deciding which local notes and experiment residue must remain ignored.
6. Document or remove `unused/x11/qtile` after confirming it is not used. Confirm
   the root `.zprofile` symlink has a real consumer before removing it: Stow
   itself installs the package copy and does not require a root-level link.
7. Tighten setup prose: distinguish Git's global-to-this-clone `merge.ff=only`
   from a main-only enforcement rule; merge/revert messages can be edited, even
   though the hook deliberately permits their generated forms.

Acceptance: supported packages and local overrides are explicit; no unexplained
legacy paths remain; skill parity is deliberate; package regression suites pass.

## Suggested delivery order

1. Test entry point, fixture repair and prerequisite documentation.
2. tmux plugin metadata repair plus temporary-home installation checks.
3. Branch/worktree retirement as a separate maintenance operation.
4. Package inventory, shell/ignore/docs cleanup in small package-scoped changes.
5. Optional shared-skill maintenance tooling only if drift warrants it.

Keep the existing Stow architecture. Avoid bulk formatting, dependency upgrades,
agent policy rewrites and history rewriting in the same cleanup changes.

## Appendix: integrated non-main local refs

Snapshot at main `9936f59`; re-evaluate before acting.

```text
docs/workflow-end-of-life
feature/claude
feature/cleanup-common-nvim-20261009-a
feature/cleanup-common-nvim-qa-repair-20261010-a
feature/cleanup-common-tmux-20261009-a
feature/cleanup-linux-hypr-20261009-a
feature/cleanup-linux-waybar-20261009-a
feature/cleanup-linux-wofi-20261012-a
feature/codex
feature/common-nvim-agent-chat-20261013-a
feature/common-nvim-search-fallback-20261012-a
feature/common-opencode-agent-attribution-20261012-a
feature/common-opencode-feature-scoped-review-20261012-a
feature/common-opencode-local-dictation-memory-20261018-a
feature/common-opencode-mvp-focused-planning-20261013-a
feature/common-opencode-review-readiness-20261011-a
feature/common-opencode-ship-20261020-a
feature/common-zsh-bash-migration-20261009
feature/linux-hypr-automatic-locking-20261017-a
feature/linux-voxtype-dotfiles-integration-20261018-a
feature/linux-voxtype-finalize-20261018-a
feature/status-reconciliation-20261009
fix/linux-hypr-voxtype-startup-20261020-a
fix/linux-waybar-workspace-click-20261018-a
maintower_branch
repair/cleanup-common-nvim-privacy-20261010-a
repair/cleanup-common-nvim-qa-20261010-a
repair/common-opencode-agent-attribution-01-20261012-a
repair/common-opencode-review-readiness-01-20261011-a
repair/common-opencode-review-readiness-02-20261011-a
repair/common-opencode-review-readiness-03-20261011-a
repair/common-opencode-review-readiness-guidance-20261011-a
ticket/cleanup-common-nvim-01-20261009-a
ticket/cleanup-common-nvim-02-20261009-a
ticket/cleanup-common-nvim-03-20261009-a
ticket/cleanup-common-nvim-04-20261009-a
ticket/cleanup-common-tmux-01-20261009-a
ticket/cleanup-linux-hypr-01-20261009-a
ticket/cleanup-linux-waybar-01-20261009-a
ticket/cleanup-linux-waybar-02-20261009-a
ticket/cleanup-linux-waybar-03-20261009-a
ticket/cleanup-linux-wofi-01-20261012-a
ticket/common-nvim-agent-chat-01-20261013-a
ticket/common-nvim-agent-chat-double-esc-20261013-a
ticket/common-nvim-agent-chat-v3-01-20261013-a
ticket/common-nvim-agent-chat-v4-04-20261013-a
ticket/common-nvim-search-fallback-01-20261012-a
ticket/common-opencode-feature-scoped-review-01-20261012-a
ticket/common-opencode-local-dictation-memory-02-20261018-a
ticket/common-opencode-mvp-focused-planning-01-20261013-a
ticket/common-opencode-review-readiness-01-20261011-a
ticket/common-opencode-review-readiness-02-20261011-a
ticket/common-zsh-bash-migration-01-20261009
ticket/common-zsh-bash-migration-02-20261009
ticket/common-zsh-bash-migration-03-20261009
ticket/common-zsh-bash-migration-04-20261009
ticket/common-zsh-bash-migration-05-20261009
ticket/common-zsh-bash-migration-06-20261010-a
ticket/common-zsh-bash-migration-07-20261010-a
ticket/linux-hypr-automatic-locking-01-20261017-a
ticket/linux-hypr-automatic-locking-02-20261017-a
ticket/linux-voxtype-dotfiles-integration-01-20261018-a
```
