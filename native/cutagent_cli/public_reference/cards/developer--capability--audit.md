# `developer capability audit`

Syntax: `cutagent developer capability audit`

## Search terms

- developer capability audit
- Check feature coverage.
- developer capability audit help
- developer capability audit command

## What it does

Check feature coverage.

## Do not use when

Use catalog-generation/tests to enforce a release gate, because audit reports gaps with exit success.
Do not use this command to verify documentation-card coverage, command-index parity, aliases, cloud authorization, bridge inference or actual DaVinci Resolve support.

## Preflight and readback

Run from the exact build/artifact being audited, since source parsing and packaged snapshots can contain different command counts.
Fix source command annotations or catalog generation, then rerun in a fresh process/build and add contract tests.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- This audit does not compare those collections and cannot explain or flag that documentation mismatch.

## Examples

- `cutagent developer capability audit --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
