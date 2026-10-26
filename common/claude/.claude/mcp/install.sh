#!/bin/sh
# Register the Obsidian, Brave Search and draw.io MCP servers at Claude Code
# user scope. User-scope servers live in ~/.claude.json, which Claude Code owns
# and rewrites, so they are installed by this script instead of being stowed.
#
# Tokens stay in the environment: the ${VAR} references are written literally
# and expanded by Claude Code at start-up (OBS_MCP_TOKEN, BRAVE_SEARCH_TOKEN).
# Safe to re-run: each server is removed and added again.
set -eu

dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

command -v claude >/dev/null || { echo "claude CLI not found" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm not found" >&2; exit 1; }

npm install --prefix "$dir" --no-audit --no-fund

add() {
    name=$1 json=$2
    claude mcp remove --scope user "$name" >/dev/null 2>&1 || true
    claude mcp add-json --scope user "$name" "$json"
}

# shellcheck disable=SC2016  # ${...} must reach Claude Code unexpanded.
add obsidian '{"type":"http","url":"https://127.0.0.1:27124/mcp/","headers":{"Authorization":"Bearer ${OBS_MCP_TOKEN}"}}'
# shellcheck disable=SC2016
add brave-search '{"type":"stdio","command":"sh","args":["-c","exec \"$HOME/.claude/mcp/node_modules/.bin/mcp-server-brave-search\" \"$@\"","--"],"env":{"BRAVE_API_KEY":"${BRAVE_SEARCH_TOKEN}"}}'
# shellcheck disable=SC2016
add drawio '{"type":"stdio","command":"sh","args":["-c","exec \"$HOME/.claude/mcp/node_modules/.bin/drawio-mcp\" \"$@\"","--"]}'

claude mcp list
