---
name: ship
description: "Owner-invoked after human QA: merge one verified feature into main (local-merge) or open its PR (pr), then retire it."
---

# Ship a feature

Local skill (not from the pinned upstream snapshot; see `../../workflow/UPSTREAM.md`).
The owner runs `/ship <feature> [<sha>]` in the primary session after human QA. It
is the only agent path to `main`. Read the project profile `docs/agents/project.md`
and `../implement-spec/LOCAL-EXECUTION.md` (commit attribution) first.

## 1. Ship mode

Read the line `Ship mode: local-merge | pr` (one of the two values) in
`docs/agents/project.md`. If it is missing or has any other value, stop and ask;
do not guess a default.

## 2. Pre-flight (read-only)

Resolve the feature to exactly one feature branch, its worktree and its planning
directory (the tracker's feature root, e.g. `docs/plans/<feature>/`). Then check,
running only read-only commands:

- Run from the primary checkout: `git worktree list --porcelain` lists the worktree
  whose branch is `main` (e.g. `/home/rbl/.dotfiles`); your `git rev-parse
  --show-toplevel` must equal it. Run there, never from inside the feature worktree
  (retirement removes it).
- `main` is checked out and clean (`git status --short` empty) in that checkout.
- The tested/reviewed SHA recorded for the feature (`approval.md`, tracker
  `handoff.md`, or the `<sha>` the owner passes from the handoff report) equals the
  feature branch tip (`git rev-parse <feature-branch>`).
- The feature branch's worktree is clean.
- `main` is an ancestor of the feature tip (`git merge-base --is-ancestor main
  <feature-branch>`). If not, main moved since the feature was verified and the
  merge result would be untested yet go live via Stow; the owner can rebase and
  re-verify through the normal delivery workflow.

On any failure, ambiguity or missing record: stop and change nothing; report what
failed. Never `git switch` or `git checkout` `main`, and never fix state yourself.

## 3. QA steps and approval

Before asking, always print:

- the feature's QA checklist (from its handoff/approval record);
- the live configs the merge will change (`git diff --stat main...<feature-branch>`,
  mapped to `<group>/<package>`). In a GNU Stow repository installed configs
  symlink into the primary checkout, so merging into `main` makes changes live
  immediately; new files need re-stow (`git diff --name-only --diff-filter=A
  main...<feature-branch>`);
- the worktrees and branches retirement will remove.

Then ask with the question tool for explicit approval. Only an explicit approval
reply proceeds; anything else (silence, a question, "maybe") means stop. Invoking
`/ship` alone is not QA approval.

## 4. Merge or publish

**local-merge:** from the primary checkout, create one merge commit with a plain
Conventional Commit subject and the attribution from LOCAL-EXECUTION.md (own
actual model in the trailer). `--no-ff` on the command line overrides a configured
`merge.ff=only`:

```sh
GIT_AUTHOR_NAME='OpenCode Agent' GIT_AUTHOR_EMAIL='opencode-agent@users.invalid' \
GIT_COMMITTER_NAME='OpenCode Agent' GIT_COMMITTER_EMAIL='opencode-agent@users.invalid' \
git -c commit.gpgsign=false merge --no-ff --no-gpg-sign '<feature-branch>' -m $'feat(<package>): <subject>\n\nAgent: OpenCode / <actual model name>'
```

On conflict or any merge failure run `git merge --abort`, confirm `main` is clean
at its previous SHA and report; never resolve conflicts on `main`. Never push `main`.

**pr:** push only the feature branch and create one PR with `gh pr create`
(permission prompts still apply; a denial is a reported blocker). Stop there.
Retirement happens only after the PR is merged: a later `/ship` run detects the
merged PR (`gh pr view <feature-branch> --json state,mergeCommit`) and, after the
owner has updated local `main`, retires. The owner merges; never `gh pr merge`.

## 5. Retire (in this order)

1. Preserve the feature's `decisions.md` and `approval.md` in the primary
   checkout's `docs/plans/<feature>/` (the tracker's feature root). `docs/` is
   gitignored, so records that exist only in the feature worktree vanish with it,
   and an overwritten primary record is unrecoverable. Never overwrite. For each
   file: if the primary target is missing, copy it and verify with `sha256sum`
   (source and copy must match); if source and target are identical, do nothing;
   if the target exists and differs (it normally holds the original record with
   appended entries), stop retiring: keep the worktree and branches and report
   both paths so the owner reconciles them; do not merge their contents yourself.
   A `sha256sum` mismatch after copying also stops retiring.
2. Add or keep exactly one index line for the feature in `docs/plans/README.md`.
3. Use non-force `git worktree remove <exact-path>` for the feature worktree and any
   leftover ticket/repair/verification worktrees; never `--force`.
4. `git branch -d` the feature and ticket branches; never `-D`.

Dirty, ambiguous or in-use worktrees and branches (a live OpenCode session located
there, per `opencode session list` or the owner) are kept and reported. A refused
`git branch -d` is kept and reported. Delete other working artifacts of the feature
(scratch dirs, session dumps, manifests) only when owned and unambiguous.

## 6. Report

Always state: the merge SHA (or PR URL); "`main` is N commits ahead of `origin/main`
— you push" (`git rev-list --count origin/main..main`); live configs changed; new
files needing re-stow with the exact command (dry run `stow -n -v -R -t ~ -d <group>
<package>`, then `stow -R -t ~ -d <group> <package>`); any reload or restart needed
(e.g. `hyprctl reload`, restart Waybar, `tmux source-file ~/.config/tmux/tmux.conf`,
restart OpenCode); and anything kept and why.
