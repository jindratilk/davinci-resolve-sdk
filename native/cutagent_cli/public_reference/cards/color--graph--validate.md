# `color graph validate`

Syntax: `cutagent color graph validate [--clip VALUE] [--comp VALUE] [--strict]`

## Search terms

- validate Fusion color graph
- check grading graph invariants
- detect disconnected MediaOut
- verify primary ColorCorrector chain
- check qualifier tracker MediaIn feeds
- fail on orphaned color tools
- preflight Fusion grading composition

## What it does

Validate the Fusion grading graph checks.

## Preflight and readback

After mutation, validate normally to catch structural errors, then with `--strict` when no known orphan may remain.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index
- `--strict` (optional, default: `false`) — Treat orphaned grading tools as errors

## Boundaries and gotchas

- `--strict` only promotes known orphan rows from warnings to errors.
- It does not tighten main-chain traversal, validate arbitrary tools, or change state.
- A primary-less chain containing only ChromaticAdaptation tools is also accepted if it is linear and reaches MediaIn; other intermediate tool types cause an error.
- Qualifiers and trackers are checked for MediaIn only when they are in the active mask chain.

## Examples

- `cutagent color graph validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
