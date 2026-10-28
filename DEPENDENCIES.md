# MCP dependency policy

The OpenCode, Codex and Claude packages use npm with committed lockfile v3 files.
Direct dependencies remain pinned at their existing versions; the initial locks
retain the existing OpenCode resolution for all three packages. Each package owns
its lockfile so it can be installed independently. `node_modules` remains ignored.
These locks cover the declared local Node MCP servers, not the clients themselves,
remote MCP services, editor plugins or transcription models.

## Install

Stow the selected package with `--no-folding` first, then run only its command:

```sh
npm ci --prefix "$HOME/.config/opencode"
npm ci --prefix "$HOME/.local/share/codex-mcp"
npm ci --prefix "$HOME/.claude/mcp"
```

For Claude, `~/.claude/mcp/install.sh` performs the same clean install and then
registers the servers. Running the npm command alone does not register servers.

Use Node.js/npm compatible with the dependencies and lockfile v3. This change was
validated with Node.js 26.12.1 and npm 12.2.1 on Linux; this is a tested combination,
not a claim that older versions are incompatible.

Validation installed 98 dependencies per package without changing the locks.
npm reported the existing Brave Search server 0.6.2 as deprecated; replacing it
is a separate integration change. npm 12 also blocked draw.io's optional
postinstall cache warmup. Its script explicitly supports skipped installation
scripts and defers caching to first use. Both executable links were installed;
authenticated requests and interactive rendering were not exercised. draw.io can
fetch assets at runtime, so locking npm dependencies does not freeze those assets.

[`npm ci`](https://docs.npmjs.com/cli/v11/commands/npm-ci/) requires matching
manifest and lockfile contents, replaces the target's `node_modules`, and leaves
the manifest/lockfile unchanged. Stop the affected MCP processes before replacing
their dependencies, then restart the client when ready. No credentials are needed
to download these public dependencies. Existing regular lockfiles in HOME may
conflict with Stow: compare and preserve local work before adopting the tracked
copy. Do not use `--adopt` to silently overwrite repository files.

## Intentional updates

1. Edit the appropriate package's direct dependency version in this checkout.
2. From that package directory, run `npm install --package-lock-only --ignore-scripts`
   to update its lockfile. This avoids populating the Stow source with dependencies.
3. Review manifest and lockfile changes together. Apply shared dependency changes
   to each client intentionally; do not assume their versions must always match.
4. Copy the manifest and lockfile into a temporary directory and run `npm ci`
   there. Verify required executable links and test the integration separately.
5. Run `python3 -B tests/run.py common/mcp common/stow common/claude common/codex`
   and commit the reviewed manifests and locks together.

Use npm for these dependency sets; the existing ignored OpenCode Bun lock is not
an alternative source of truth. Avoid running dependency updates through a live
Stow symlink unless you intend to edit the repository. Offline tests check lock
integrity and installer ordering; real clean installs require registry access
and are an additional validation step, not part of the default Python suite.
