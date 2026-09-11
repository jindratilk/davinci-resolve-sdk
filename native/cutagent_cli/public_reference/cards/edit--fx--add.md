# `edit fx add`

Syntax: `cutagent edit fx add NAME [--clip VALUE] [--item-id VALUE] [--track VALUE] [--record-frame VALUE] [--template VALUE] [--params VALUE] [--verify] [--proof-dir VALUE]`

## Search terms

- add reviewed Fusion effect to clip
- apply glow blur sharpen transform
- stable effect ID
- typed effect parameters
- exact timeline item effect
- rendered effect verification

## What it does

Add an effect to a clip.

## Do not use when

Use generic Fusion graph commands for arbitrary topology. Do not use an unreviewed template, arbitrary parameter name, or `--no-verify`; these inputs fail closed.

## Preflight and readback

Run `color fx list`, choose a stable effect ID, and inspect supported parameter IDs/ranges. Prefer `--item-id`, or use `--track` with `--record-frame`, when clip names repeat. Retain `--proof-dir`.

## Public arguments and options

- `NAME` (required) — Reviewed effect ID or alias
- `--clip` (optional) — Target timeline clip (current clip if omitted)
- `--item-id` (optional)
- `--track` (optional) — Exact video track index; requires --record-frame
- `--record-frame/--at` (optional) — Record-domain position inside the target
- `--template` (optional) — Reviewed custom .setting path with sibling manifest
- `--params` (optional) — JSON object of reviewed parameter IDs and typed values
- `--verify/--no-verify` (optional, default: `true`) — Require structural and rendered verification
- `--proof-dir` (optional) — Directory for retained rendered evidence

## Boundaries and gotchas

- Built-ins take deterministic precedence and cannot be shadowed by a same-named template.
- `--no-verify` is rejected for this consequential mutation.
- Global `--dry-run` validates effect identity and parameter typing without connecting to DaVinci Resolve.

## Stable public error codes

- `AMBIGUOUS_TIMELINE_ITEM`
- `EFFECT_NOT_SUPPORTED`
- `EFFECT_PARAMETER_INVALID`
- `EFFECT_VERIFICATION_FAILED`
- `STALE_TIMELINE_ITEM`

## Examples

- `cutagent edit fx add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
