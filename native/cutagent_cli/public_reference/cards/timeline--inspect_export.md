# `timeline inspect-export`

Syntax: `cutagent timeline inspect-export PATH [--force]`

## Search terms

- detailed timeline inspection
- timeline inspect export
- inspect timeline properties
- export Fusion graph readback
- inspect Color and Fairlight state
- inspect retime curves and keyframes
- timeline diagnostic document

## What it does

Export an explicit detailed, inspection-only timeline document.

## Do not use when

Use the appropriate DRT, DRP, archive, render, or timeline export command instead.
Do not run it automatically at startup or before every message.

## Public arguments and options

- `PATH` (required) — Output path for the detailed inspection document
- `--force/-f` (optional, default: `false`) — Replace an existing regular file

## Boundaries and gotchas

- Exact help is `cutagent timeline inspect-export PATH [--force]`.
- It refuses to replace an existing file unless `--force` is supplied.
- The command does not render, mutate the timeline, or advertise reconstruction completeness.
- The SDK action remains subject to the existing release-admission contract; adding discovery does not activate production execution.

## Examples

- `cutagent timeline inspect-export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
