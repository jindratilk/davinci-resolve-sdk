# `color page param-delete`

Syntax: `cutagent color page param-delete [CLIP_NAME] --param VALUE`

## Search terms

- delete Color parameter
- remove explicit grade value
- fall back to default parameter
- unset saturation value
- delete qualifier parameter
- clear key output override
- reset one raw Color field

## What it does

Runs the public `color page param-delete` CutAgent command.

## Do not use when

Use semantic setters such as `primary-set`, `wheel-set`, `key-output-set`, qualifier commands, curve commands or Power Window commands when you know the desired state and need their companion fields plus domain validation. Use node cleanup/delete for topology, `dctl-remove`/LUT clearing for node LUT slots, and Fusion input/tool commands for Fusion state.

## Preflight and readback

Include all coupled fields required to reset a structured feature, not just the most obvious key.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--param` (required, repeatable) — Color Page param name to delete; repeatable

## Boundaries and gotchas

- There is no `--node` option.
- It validates neither registry membership nor current presence and does not echo which names it received.
- Absence verification can still succeed; do not interpret success as evidence a visible adjustment was reset.

## Examples

- `cutagent color page param-delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
