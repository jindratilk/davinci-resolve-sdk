# `fusion template dir`

Syntax: `cutagent fusion template dir [--set VALUE]`

## Search terms

- resolve-templates path
- configure Fusion templates
- user template path
- CutAgent template location

## What it does

Check and set the template directory.

## Do not use when

Do not use it to install or move templates.
Do not point `--set` at an existing file, a protected location, or a broad/unreviewed path. Parent directories can be created recursively.

## Preflight and readback

Before `--set`, inspect the exact path, its parents, existing file type, permissions, and whether process-local configuration is sufficient. Prefer an absolute path.
Run a fresh `fusion template dir` process to prove whether the setting persisted.
No DaVinci Resolve cleanup is needed.

## Public arguments and options

- `--set` (optional) — Set template directory

## Boundaries and gotchas

- The only command-specific option is `--set TEXT`.
- In a normal CLI invocation, the process exits immediately and the environment change cannot affect the parent shell or next CLI process.

## Examples

- `cutagent fusion template dir --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
