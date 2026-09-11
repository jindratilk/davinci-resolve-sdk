# `fusion template scaffold`

Syntax: `cutagent fusion template scaffold KIND NAME [--output VALUE] [--overwrite]`

## Search terms

- scaffold Fusion template
- create minimal .setting
- generate title template
- generate effect template
- generate transition template
- generate generator template
- Fusion template starter
- TextPlus scaffold
- overwrite template scaffold
- template scaffold dry-run
- minimal Fusion setting

## What it does

Prepare a Fusion template.

## Do not use when

Do not use the generated file as a production-ready template. It has no MediaOut, no ViewInfo, no inputs/controls metadata, and no kind-specific structure.
Do not trust `fusion template validate` alone.
Do not import the scaffold over a valuable clip. Test in an isolated timeline or export the original graph and frame first.

## Preflight and readback

Check whether the destination and parent directories already exist.
If the destination exists, decide deliberately whether `--overwrite` is authorized.
Run both the shallow `fusion template validate` and the stricter `fusion setting inspect`/`fusion setting validate`.

## Public arguments and options

- `KIND` (required) — title|generator|effect|transition
- `NAME` (required) — Template name
- `--output` (optional) — Output .setting path
- `--overwrite` (optional, default: `false`) — Replace an existing template file

## Boundaries and gotchas

- Options are `--output TEXT` and `--overwrite`.
- Allowed kinds are case-sensitive: `title`, `generator`, `effect`, `transition`.
- Kind does not change output folder, file contents, tool class, or metadata.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template scaffold --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
