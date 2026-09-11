# `fusion template validate`

Syntax: `cutagent fusion template validate PATH`

## Search terms

- validate Fusion template
- check .setting extension
- template Tools check
- shallow template validation
- Fusion template validity
- template file exists
- validate generated scaffold
- template suffix validation
- compare setting validation

## What it does

Validate a Fusion template file.

## Do not use when

Do not use it instead of `fusion setting inspect` or `fusion setting validate`.
Do not expect dry-run to avoid file access.

## Preflight and readback

Prefer an explicit path rather than assuming template search rules.
Treat `valid:false` as a completed negative check, not a command failure.
For any file that may be imported or shipped, run `fusion setting inspect` and strict `fusion setting validate`; inspect MediaOut, connections, warnings, errors, and layout.
No cleanup is needed because the command is read-only.

## Public arguments and options

- `PATH` (required) — .setting path

## Boundaries and gotchas

- Content comparison is the raw case-sensitive substring `"Tools" in text`.
- It does not report why an existing file returned `valid:false`.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
