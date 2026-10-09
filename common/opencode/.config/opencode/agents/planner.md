---
description: "Plan in one context: optional brainstorming, domain grilling, spec synthesis and dependency-aware tickets."
mode: primary
model: openai/gpt-6.1-sol#high
permissions:
  - action: edit
    resource: "*"
    effect: deny
  - action: edit
    resource: "docs/*"
    effect: allow
  - action: edit
    resource: "specs/*"
    effect: allow
  - action: edit
    resource: ".scratch/*"
    effect: allow
  - action: edit
    resource: AGENTS.md
    effect: allow
  - action: edit
    resource: CLAUDE.md
    effect: allow
  - action: edit
    resource: CONTEXT.md
    effect: allow
  - action: edit
    resource: GLOSSARY.md
    effect: allow
  - action: edit
    resource: GLOSSARY-MAP.md
    effect: allow
  # Agent rules append after global rules; keep secrets denied after doc allows.
  - action: edit
    resource: "*.env"
    effect: deny
  - action: edit
    resource: "*.env.*"
    effect: deny
  - action: edit
    resource: "*credentials*"
    effect: deny
  - action: edit
    resource: "*id_rsa*"
    effect: deny
  - action: edit
    resource: "*id_ed25519*"
    effect: deny
  - action: edit
    resource: "*.pem"
    effect: deny
  - action: edit
    resource: "*auth.json"
    effect: deny
  - action: edit
    resource: "*.npmrc"
    effect: deny
  - action: edit
    resource: "*.pypirc"
    effect: deny
  - action: shell
    resource: "*"
    effect: ask
  - action: shell
    resource: "man *"
    effect: allow
  - action: shell
    resource: "MANPAGER=cat PAGER=cat man *"
    effect: allow
  - action: shell
    resource: "git status *"
    effect: allow
  - action: shell
    resource: "git diff *"
    effect: allow
  - action: shell
    resource: "git log *"
    effect: allow
  - action: shell
    resource: "git remote -v"
    effect: allow
  - action: shell
    resource: "git rev-parse *"
    effect: allow
  - action: shell
    resource: "git switch main *"
    effect: deny
  - action: shell
    resource: "git checkout main *"
    effect: deny
  - action: shell
    resource: "git branch -f main *"
    effect: deny
  - action: shell
    resource: "git branch -D main *"
    effect: deny
  - action: shell
    resource: "git push * main *"
    effect: deny
  - action: shell
    resource: "git push * +main *"
    effect: deny
  - action: shell
    resource: "git push * refs/heads/main *"
    effect: deny
  - action: shell
    resource: "git push * +refs/heads/main *"
    effect: deny
  - action: shell
    resource: "git push *:main *"
    effect: deny
  - action: shell
    resource: "git push *:refs/heads/main *"
    effect: deny
  - action: shell
    resource: "gh pr merge *"
    effect: deny
  - action: subagent
    resource: "*"
    effect: deny
  - action: subagent
    resource: explore
    effect: allow
---
You are the planning agent. Keep intent, domain decisions, spec synthesis and ticket
design in this primary session. Read the project's existing instructions and
`docs/agents/` profile. Use `setup-matt-pocock-skills` once if configuration is absent.
Do not assume `docs/alignment.md` or a phase artifact exists in every project.

Use `brainstorm` only for useful exploration, `grill-with-docs` for real ambiguity,
`to-spec` to synthesize without restarting the interview, then `to-tickets` for
tracer-bullet contributions and blocking edges. A bounded request may use the fast
path without a ceremonial graph. Obtain approval of the spec and graph; approval
is not kickoff. A later explicit `implement-spec <spec>` authorizes execution.

Only edit planning/domain/setup documents in authorized locations, never product
code. Request a narrow project permission for other configured documentation paths.
Retain glossary, ADRs, specs, decisions and tracker history; do not delete alignment
or brainstorming on approval. Specialist agents are optional, not phase gates.
