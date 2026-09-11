# `fusion tool copy`

Syntax: `cutagent fusion tool copy TOOL_NAMES...`

## Search terms

- copy Fusion tools
- Fusion composition clipboard
- copy multiple Fusion nodes
- comp Copy tools
- prepare Fusion paste
- verify Fusion clipboard
- missing tool copy failure
- copy orphan Background
- clipboard side effect

## What it does

Copy Fusion nodes.

## Do not use when

Do not copy guessed names. List the active composition and preserve exact unique tool names first.
Do not assume the clipboard contains what the success message claims.
Do not use it when overwriting the user's current Fusion clipboard would be unacceptable. The command returns no prior clipboard content or restoration token.
Do not assume copying one orphan guarantees a harmless paste.
Do not execute in an ambiguous composition. There is no clip, track, timeline-item, or comp-index selector.
External media, plugins, Fuses, fonts, expression dependencies, and connections outside the copied selection may not be self-contained.

## Preflight and readback

Before execution, identify the active composition, list tools, capture graph topology, and record the active tool/selection. Understand that copy changes clipboard state even though the graph remains unchanged.
Dry-run the exact ordered tool list. It validates only that at least one nonblank name remains; it does not resolve names or inspect copy support.
If testing paste in the same comp, capture the full original graph and frame first. Clean up every newly created node—including selection-dependent auto-created helpers—and restore the original connections and active tool.

## Public arguments and options

- `TOOL_NAMES` (required, repeatable) — Tool names to copy

## Boundaries and gotchas

- Whitespace-only names are silently removed when at least one valid name remains.
- Duplicate normalized names are not deduplicated.
- Copy itself does not list inputs/outputs or prove that later paste will preserve names/connections.
- The paste changed the representative frame to black and required explicit graph restoration/three-node cleanup.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion tool copy --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
