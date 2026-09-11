# `fuse scaffold`

Syntax: `cutagent fuse scaffold NAME [--output VALUE] [--overwrite]`

## Search terms

- scaffold Fusion Fuse
- create minimal Fuse file
- generate .fuse source
- Fuse SDK starter
- FuRegisterClass generator
- Fuse scaffold dry-run
- overwrite Fuse source
- invalid Fuse name quoting
- CutAgent Fuse developer workflow

## What it does

Prepare a Fuse file.

## Do not use when

Do not treat the generated file as a complete working Fuse.
Do not pass untrusted or unvalidated names. The name is interpolated twice into double-quoted Fuse/Lua source without escaping; quotes, newlines, backslashes, or code fragments can produce malformed or injected source.
Do not rely on `fuse validate` to catch malformed generated source. Its lightweight check can report `valid:true` for syntactically broken content.
Do not overwrite an existing source without preserving it first.
Do not expect the command to install, load, compile, execute, or refresh the Fuse in DaVinci Resolve.

## Preflight and readback

`fuse validate` is only a shallow preflight.

## Public arguments and options

- `NAME` (required) — Fuse name
- `--output` (optional) — Output .fuse path
- `--overwrite` (optional, default: `false`) — Replace an existing Fuse file

## Boundaries and gotchas

- `--output TEXT` and `--overwrite` are optional.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fuse scaffold --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
