# `fusion comp rename`

Syntax: `cutagent fusion comp rename NEW_NAME [--index VALUE] [--clip VALUE]`

## Search terms

- rename Fusion composition
- change comp label on clip
- name a Fusion comp
- rename Composition1
- organize multiple clip Fusion comps
- set Fusion composition name
- rename comp tab
- change clip Fusion comp label
- label alternate Fusion version
- give Fusion graph a descriptive name
- rename current clip composition

## What it does

Rename a Fusion composition on the current and named timeline clip.

## Do not use when

Use `media rename` or the appropriate clip/timeline naming command when the desired visible name is the media-pool asset or timeline item. This command targets the attached Fusion composition label only.
Use `fusion tool rename` when a node inside the graph needs a new tool name. Comp rename does not change tool IDs or expressions referencing nodes.
Use `fusion comp delete` to remove an unwanted comp rather than renaming it to hide/reuse a label.
Do not target by `--clip` when duplicate clip names make the standard clip resolver ambiguous. This command has no track/frame selector.

## Preflight and readback

Before renaming, list the exact timeline items and run `clip fusion list` on the intended clip.
Choose a unique, nonempty descriptive label. A successful plan does not prove the clip exists or the index is in range.
Treat disagreement as two distinct naming surfaces, not automatic evidence that no rename occurred.
If downstream commands address comps by name, test those exact commands with the new clip-level label before relying on it.

## Public arguments and options

- `NEW_NAME` (required) — New composition name
- `--index/-i` (optional, default: `1`) — Composition index
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- The command can rename only by current/named clip plus 1-based comp index.
- Dry-run does not resolve the target.
- It does not lock the clip/comp during name resolution and mutation, so concurrent UI changes can invalidate index/name candidates.
- Renaming does not alter graph content or solve duplicate tool names; it is metadata at the timeline-item comp layer.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion comp rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
