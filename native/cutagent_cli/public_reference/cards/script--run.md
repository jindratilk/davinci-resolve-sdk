# `script run`

Syntax: `cutagent script run PATH [--args VALUE]`

## Search terms

- execute Python script
- execute Lua script
- repeat script arguments
- capture stdout stderr
- subprocess return code
- run script outside DaVinci Resolve
- local code execution
- script dry-run command preview

## What it does

Apply a DaVinci Resolve custom edit.

## Do not use when

Do not run untrusted or unreviewed code; this command provides no sandbox.
Do not use it to run a DaVinci Resolve in-process script that depends on embedded application objects or UI context.

## Preflight and readback

Use `--args VALUE` repeatedly; use `--args=--flag` when an argument begins with a hyphen so the CLI does not parse it as its own option.
After execution, inspect `returncode`, stdout, and stderr, then verify every intended side effect independently. Remove temporary scripts and outputs when finished.

## Public arguments and options

- `PATH` (required) — Script path
- `--args` (optional, repeatable) — Argument to pass; repeat for multiple values

## Boundaries and gotchas

- The command does not connect to DaVinci Resolve.
- Extension matching is exact and case-sensitive in code.
- A nonzero child return code does not become a CutAgent CLI error.
- The command does not parse structured child output or verify side effects.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent script run --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
