> **Historical copy (2026-10-06)** of root `docs/review-findings-2026-10-05.md`. Dated review, not live tree status; permission regression now fixed on main, and historical test counts are not current verification.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# Review findings — 2026-10-05

Analysis of `docs/implementation-plan.md` (W1–W9), the `linux/opencode-routine/`
launcher package, and the uncommitted agent edits. Written while the W2 session was
paused on OpenCode usage limits, so the W2 session can finish without re-deriving
this.

**Nothing here was changed.** Every claim marked *verified* was checked against the
working tree and the installed release (OpenCode `2.0.22`, `opencode-1`).

## State of the tree

| Item | State |
|---|---|
| Branch | `main`, clean against `origin/main` (0 ahead) — all remediation work unpushed |
| Uncommitted | 10 modified agent files; `linux/opencode-routine/` untracked (71 files) |
| Untracked docs | `docs/` is gitignored — `git ls-files docs` → **0** |
| Tests | **601 collected, 583 passed, 18 skipped** (*verified*) |

Test breakdown (*verified*): `test_w1` 114 · `test_w2` 141 · `test_m1` 25 ·
`test_m2` 321. Total 601.

## Summary of findings

| # | Finding | Severity | Needs |
|---|---|---|---|
| 1 | `planner` and `tutor` agent permission blocks are silently ignored — both are unrestricted | **High** | Fix now; independent of W2 |
| 2 | Plan has no W2 evidence section; recorded counts are stale (460 vs 601) | **High** | Add before presenting W2 |
| 3 | `linux/opencode-routine/README.md` contradicts the plan (M1/M2 sandbox narrative) | Medium | Reconcile |
| 4 | 71 new files untracked; entire `docs/` tree untracked | Medium | Land; revisit D4 |
| 5 | Agent model changes reverse settled decision #14, unbudgeted and unrecorded | Medium | User decision |
| 6 | Plan structure: documentation lags code; altitude mismatch in one file | Low | Structural |

---

## 1. `planner` and `tutor` permission blocks are silently ignored

**This is a live hole, not a documentation issue.** It predates the current session
and is unrelated to W1/W2.

### What is wrong

Five agents carry a permission block. Two spell the key `permissions:` (array); three
spell it `permission:` (map). Only the map form works.

*Verified* with `opencode debug agents` on 2.0.22 — resolved `permissions` per agent:

| Agent | Frontmatter key | Agent-level deny resolves? |
|---|---|---|
| `aligner` | `permission:` (map) | **yes** — `shell\|*\|deny`, `edit\|*\|deny`, `edit\|docs/**\|allow` |
| `brainstomer` | `permission:` (map) | **yes** — same shape |
| `orchestrator` | `permission:` (map) | **yes** — `shell\|*\|ask` (correct by design) |
| **`planner`** | `permissions:` (array) | **NO — block ignored entirely** |
| **`tutor`** | `permissions:` (array) | **NO — block ignored entirely** |

`planner` and `tutor` each resolve to 34 rules with **no agent-level deny at all**.
Rule 0 is `*|*|allow`. Their only shell gating is the global `ask` list
(`git push`, `rm -rf *`, `dd *`, …) from `opencode.jsonc`.

Consequence: `tutor` — whose prompt states it "produces nothing — it provokes
thought" — currently has full shell and full edit. `planner` — "strictly forbidden
from touching application source code" — likewise. Neither restriction is enforced.

### How it happened

The uncommitted agent edits already migrated `aligner`, `brainstomer` and
`orchestrator` to the working map form. `planner` and `tutor` were left on the array
form, so the migration is half-done.

The array form was introduced by `249b9fa` (*fix(opencode): translate V1 agent
permission blocks to V2 rules*). Comparing against `1dbddf1`, the commit before it:

| Agent | `1dbddf1` (before O10) | Now | Effect |
|---|---|---|---|
| `planner` | `edit: allow`, **`bash: deny`** | ignored | **widened** |
| `tutor` | **`edit: deny`, `bash: deny`** | ignored | **widened** |
| `builder`, `cleaner`, `recaper`, `refactorer`, `tester` | `edit: allow`, `bash: allow` | block deleted | neutral — no restriction lost |

So O10's deletion of those five blocks is harmless (they granted everything), but
its *translation* of `planner` and `tutor` silently granted shell to both. Only two
agents regressed — not four, not ten.

### The trap

`permissions:` (array) **is** honoured in the root `opencode.jsonc`: all of its
global rules appear in every agent's resolved list. The same key in agent
frontmatter does nothing. A key that works in one file and silently fails in
another is the exact footgun already recorded in `~/.opencode/plan/README.md`
("An unrecognised config key produces no error at all").

Note the irony: O1 correctly warned that *deleting* the V1 blocks "would have
granted shell to 4 agents". O10's translation granted shell to 2 agents, by changing
the key rather than the values.

### Schema corroboration

`https://opencode.ai/config.json` (*verified* by fetch):

- `AgentConfig` properties: `color, description, disable, hidden, maxSteps, mode,
  model, options, permission, prompt, steps, temperature, tools, top_p, variant`.
  There is **no `permissions` key**. `permission` is the supported spelling.
- `PermissionConfig` is `anyOf[ PermissionActionConfig, {map: action → rule} ]`,
  where `PermissionActionConfig` is the string enum `ask|allow|deny`.

The map form the three working agents use is the schema-valid one.

Caveat: the schema is not authoritative for every key — `reasoningEffort` is absent
from `AgentConfig` yet *is* parsed (see §5). So treat the schema as corroboration
and `opencode debug agents` as the proof.

### Fix

Change `permissions:` → `permission:` in `planner.md` and `tutor.md`, using the map
form to match the three working agents:

```yaml
permission:
  shell: deny
  edit:
    "*": deny
    "docs/**": allow
```

For `tutor`, the pre-O10 intent was `edit: deny` with no `docs/**` exception, and
`bash: deny`; decide whether tutor should keep read-only browsing intent. `planner`
should keep `docs/**` as its only writable path.

### Verify

Reports the agent-level rule for every configured agent, for both `deny` and `ask`
(orchestrator uses `shell: ask`, so a deny-only filter wrongly shows it as `NONE`):

```sh
opencode debug agents 2>/dev/null | python3 -c "
import json,sys
for a in json.load(sys.stdin):
    ag=[f\"{p['action']}={p['effect']}\" for p in a['permissions']
        if p['resource']=='*' and p['effect'] in ('deny','ask')
        and p['action'] in ('shell','edit','write','skill','subagent')]
    print(f\"{a['id']:<14}{len(a['permissions']):>4}  \"
          f\"{','.join(ag) if ag else 'NONE'}\")"
```

Expected after the fix — all five permission-bearing agents resolved from their own
frontmatter:

```
aligner         44  shell=deny,edit=deny
brainstomer     44  shell=deny,edit=deny
orchestrator    41  shell=ask
planner         ..  shell=deny,edit=deny
tutor           ..  shell=deny,edit=deny
```

`planner` and `tutor` currently report `NONE` and must stop doing so. The remaining
agents have no frontmatter and are expected to be unchanged: built-ins `build`,
`compaction`, `summary`, `title` report `NONE`; `explore`, `general` and `plan`
carry their own built-in rules.

### Also correct the O-series record

`~/.opencode/plan/README.md` records under "O-series: implemented 2026-10-03":

> `tutor` shell → tool **absent from the catalog**, not refused at call time

That check cannot be reproduced against the current tree and is therefore not sound
evidence. It should be marked unverified rather than left as a passing result.

---

## 2. The plan has no W2 evidence section and its counts are stale

**This is the main thing the finishing W2 session needs to address.**

The plan's §5 ("Next approval boundary") still reads:

> Present assembled W2 deterministic evidence, independent verification/fresh
> review, remaining gates and the concrete joined qualification proposal.

But W2 is already assembled and wired. *Verified* present state:

- `cli.py` exposes `authorize_local`, `authorize_local_dispatch`, `local-stop`, and
  the Coordinator operations `local-prepare`, `local-fixture-check`, `local-stop`.
- `launcher.py` has `Launcher.local_stop`, `authorize_local`,
  `authorize_local_dispatch`, and `Coordinator.claim_local`, `local_prepare`,
  `local_fixture_check`, `local_stop`, wiring `LocalLifecycle`.
- New modules: `local_contracts.py`, `local_bundle.py`, `local_baseline.py`,
  `local_run.py`, `local_lifecycle.py`, `opencode_local.py`.
- New tests: `test_w1*.py` (114), `test_w2.py`, `test_w2_adapter.py`,
  `test_w2_assembly.py`, `test_w2_clone.py`, `w2_fixture.py` (141).

The plan's only evidence section is `#### W1 implementation evidence`, which records
the W1-era figure:

> final full discovery without `-p` collected **460 tests, 442 passed, 18 skipped**

That is arithmetically the W1-era tree: 114 W1 + 328 historical + 18 skipped = 460.
The 141-test delta is exactly W2. So the recorded number is not wrong for its moment —
it is simply the last W1 snapshot, and **W2 was never recorded**.

### What to add

A `#### W2 implementation evidence` section mirroring the W1 one, recording:

- Adapted/added files, relative to `linux/opencode-routine/`.
- Assembled counts: **601 collected, 583 passed, 18 live skipped**; breakdown
  114 W1 / 141 W2 / 25 M1 / 321 M2.
- The exact command, with the three live opt-ins explicitly unset:
  ```sh
  env -u OPENCODE_ROUTINE_TEST_IMAGE -u OPENCODE_ROUTINE_COMPONENT_IMAGE \
      -u OPENCODE_ROUTINE_STORAGE_IMAGE \
      TMPDIR=/tmp/opencode PYTHONDONTWRITEBYTECODE=1 \
    python3 -B -m unittest discover -s linux/opencode-routine/tests -v
  ```
- A code/test fingerprint in the same shape W1 used (canonical JSON of the sorted
  `{path, sha256}` list). W1's ten-file identity was
  `3967eb57714b43c126321125e4a57f69873f93c28869cd7d04d9a284a5da940f`; W2 adds
  files, so the set identity changes and must be recomputed.
- Confirmation that no real session/command launch, sandbox opt-in, GitHub write,
  host install or production mutation occurred.
- Independent verification and fresh read-only review results, or an explicit
  statement that they are still outstanding.
- The separate approval still required before the joined real W2 qualification
  exercise (plan §"Separately approved real W2 qualification").

Until that exists, the plan cannot support its own claim that evidence is bound to
tested source identities.

---

## 3. `linux/opencode-routine/README.md` contradicts the plan

The package README still presents the **archived** path as current. Its opening
line:

> **M1 done; M2 partially implemented, not qualified.** … Normal suite:
> **192 passed, 18 live tests skipped**; all opt-ins: **210 passed**

The plan superseded that: sandboxing is deferred to a separate project, and W1–W9
replace M3+. The README never mentions W1–W9 at all. A reader landing on the package
learns a project the plan has archived, with counts that disagree with both the plan
and the tree.

Two options; either is fine, but they cannot both stand:

- **Retitle as history.** Add a header banner: superseded for planning purposes by
  `docs/implementation-plan.md`; this file records the M1/M2 sandbox line. Relabel
  the test counts as "at the documented revision" for M2 only.
- **Rewrite the header** to describe the workflow-first package and move the M2
  sandbox detail to an appendix or archive.

Note `.stow-local-ignore` excludes `^/README\.md$`, so it is not stowed to a new
machine — but it is the first file a reader opens in the repo.

---

## 4. Untracked work, and `docs/` ignored at the wrong scale

*Verified*: `git ls-files linux/opencode-routine` → 0. `git add -An
linux/opencode-routine` → 71 files. `git ls-files docs` → 0.

Two separate problems:

- **The launcher package is unlanded.** This is D3 recurring — the "dirty working
  tree" problem that was previously marked `IMPLEMENTED`. Two days of W1/W2 work,
  601 passing tests, nothing committed.
- **`docs/` is now much larger than the decision that ignored it.** D4 / decision #8
  accepted keeping `docs/` ignored when it held `CONTEXT.md`. It now holds ~300 KB:
  `implementation-plan.md` (1093 lines), `alignment.md` (397), `brainstorming.md`
  (~80 KB decision record), `CONTEXT.md`, `loop-logic.md`, `m2-qualification.md`
  (54 KB of evidence), `m2-{interface-checkpoint,network,services,storage}-proposal.md`,
  `sandcastle-investigation.md`, `skills-ranking.md`, and `archive/`. None of it is
  tracked, none travels to another machine, and it is all one `rm` from gone.

The D4 rationale — "`docs/CONTEXT.md` does not travel between machines — accepted
knowingly" — was reasonable for one file and is no longer reasonable at this scale.
Recommend revisiting, with `plan.md` still excluded per the original intent.

---

## 5. Agent model changes reverse a settled decision, unbudgeted

The uncommitted edits change all seven agents that had a `#TODO` model marker, and
drop the marker:

```
-#TODO opencode/big-pickle was a temporary swap from tencent/hy3:free — revisit cost and quality
-model: opencode/big-pickle
+model: openai/gpt-6.1-sol
+reasoningEffort: high
```

*Verified* against the model catalogue: `opencode/big-pickle` is **free**
(input/output/cache all 0). The replacements are on the `openai` provider
(`gpt-6.1-sol`, `gpt-5.3-codex-spark`) — both are valid IDs, so this is not another
O3-style bad-model-ID bug.

But it does three things without a record:

1. **Reverses settled decision #14** in `~/.opencode/plan/README.md`, which reads
   "Which agents move to `big-pickle`? **All four**". The TODO said "revisit cost and
   quality"; this answers it, in the expensive direction, for seven agents.
2. **Is unbudgeted.** Moving the loop owner and four other agents off a free model
   onto paid ones is a recurring-cost change.
3. **Is not in the decision record.** `docs/brainstorming.md` contains no mention of
   `big-pickle`, `gpt-6.1-sol`, `gpt-5.3-codex-spark` or `reasoningEffort`
   (*verified* by grep). The plan's §2 says "Preserve existing agent edits", but
   nothing records what they decided.

This needs a user decision, not an implementation guess. Either update decision #14
and add the reasoning to `docs/brainstorming.md`, or revert.

### `reasoningEffort` may be inert

*Verified*: it is absent from `AgentConfig` in the schema, yet OpenCode parses it
into `request.body.reasoningEffort` (seen in `opencode debug agents` output). That
is the same destination as the `temperature` key the O-series established is
"preserved but not sent". Confirm it actually reaches the provider before relying on
it — the failure mode is silent, exactly as `temperature` was.

---

## 6. Assessment of the plan itself

### What it gets right

1. **The scope cut is honest.** §1 states that clones are not containment, that "role
   tool permissions are workflow controls, not adversarial host containment", and
   that "ambient host access cannot be claimed absent". This is the right framing and
   it avoids the creeping overclaim the M2 documents were drifting toward.
2. **The reuse map is code-specific** (§2) — names files and exact reuse boundaries,
   including traps: `bundle-id` fingerprints worker-image assets, not the local
   agent/skill bundle; M1 validates baseline *syntax* and hashes but does not
   establish that the baseline exists; the prompts are "adaptation inputs, not a
   usable local execution bundle".
3. **Gates are falsifiable.** "Any uncertain gate holds W3"; "a mocked pass is not
   real runtime qualification"; evidence bound to source/profile/bundle/runtime/commit
   identities. Legacy findings S1–S14 each map to a specific milestone proof (§4).
   This is the document's real strength.
4. **Build order is decoupled from runtime scheduling** (§3), which prevents the
   common misread of milestones as a runtime queue.
5. **The advisory discipline is good.** W1's open items — the missing metadata-cap
   advisory, the absent dedicated deadline/packed-ref-race tests — are recorded as
   visible limitations rather than reported as passes.

### Structural problems

- **Documentation lags code** (§2 above). For a document whose value proposition is
  evidence-bound identity, this is the most damaging possible gap.
- **One file does two jobs.** W1/W2 are exact Python signatures and status reports;
  W3–W9 are ~20 lines of outcome-level acceptance each. The split is intentional and
  correct, but combining design, status and evidence in one file is why it went
  stale. Consider moving per-milestone evidence into `docs/` siblings
  (`w1-evidence.md`, `w2-evidence.md`) with the plan holding only scope, contracts
  and acceptance.
- **§2's "Preserve existing agent edits" was applied as "do not touch"**, which is
  how §1's regression passed through unexamined. "Preserve" needs a qualifier:
  preserve *unless verified broken*.

---

## Recommended order

1. **Fix `planner` and `tutor`** (§1). Two files; closes a live hole. Verify with
   `opencode debug agents`. Independent of W2 — do not let it wait on the plan.
2. **Mark the `tutor` row in `~/.opencode/plan/README.md` unverified** (§1).
3. **Add the W2 evidence section** (§2) so the plan matches the tree before W2 is
   presented.
4. **Reconcile the package README** (§3).
5. **Land the 71 files**; revisit `docs/`/D4 (§4).
6. **User decision on the model change** (§5), then record it in
   `docs/brainstorming.md` and the decision register.

Items 1 and 2 are quick and reduce live risk. Items 3–5 are hygiene before W2 is
presented. Item 6 needs the user.

## Reproducing this analysis

```sh
# 1. agent permission state
opencode debug agents > /tmp/opencode-agents.json

# 2. full suite, live opt-ins explicitly unset
cd /home/rbl/.dotfiles
env -u OPENCODE_ROUTINE_TEST_IMAGE -u OPENCODE_ROUTINE_COMPONENT_IMAGE \
    -u OPENCODE_ROUTINE_STORAGE_IMAGE \
    TMPDIR=/tmp/opencode PYTHONDONTWRITEBYTECODE=1 \
  python3 -B -m unittest discover -s linux/opencode-routine/tests

# 3. per-group counts
for p in test_w1 test_w2 test_m1 test_m2; do
  env -u OPENCODE_ROUTINE_TEST_IMAGE -u OPENCODE_ROUTINE_COMPONENT_IMAGE \
      -u OPENCODE_ROUTINE_STORAGE_IMAGE TMPDIR=/tmp/opencode \
      PYTHONDONTWRITEBYTECODE=1 \
    python3 -B -m unittest discover -s linux/opencode-routine/tests -p "$p*.py" 2>&1 \
    | grep -E '^Ran ' | sed "s/^/$p -> /"
done

# 4. tracking status
git ls-files linux/opencode-routine docs | wc -l
git add -An --dry-run linux/opencode-routine | wc -l

# 5. the config schema
curl -sS https://opencode.ai/config.json | python3 -c "
import json,sys
print(sorted(json.load(sys.stdin)['\$defs']['AgentConfig']['properties']))"

# 6. permission-block spelling per agent
cd common/opencode/.config/opencode/agents
for f in *.md; do
  printf '%-14s %s\n' \"\${f%.md}\" \
    \"\$(awk '/^---\$/{n++; next} n==1 && /^(permission|permissions):/{print \$1; exit}' \$f)\"
done
```