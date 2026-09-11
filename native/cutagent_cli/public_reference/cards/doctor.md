# `doctor`

Syntax: `cutagent doctor [--full]`

## Search terms

- diagnose CutAgent setup
- DaVinci Resolve automation readiness
- ffmpeg ffprobe availability
- embedded bridge health
- why CutAgent cannot connect
- preflight editing environment
- CutAgent installation diagnostics

## What it does

Check DaVinci Resolve readiness.

## Do not use when

Do not use `doctor` as a project-state or editing-target readback; use `status` or `context`. Do not run it after every edit as verification: it proves environment readiness, not that a clip, grade, render, or Fairlight parameter changed. Use `embedded status` when the only question is the installed/running/authenticated state of the embedded Free bridge.

## Preflight and readback

Follow a successful result with `status` to capture the exact open project/timeline, then use `capabilities` for the intended feature.

## Public arguments and options

- `--full` (optional, default: `false`) — Include full external tool version details

## Boundaries and gotchas

- Without `--full`, external-tool results contain resolved path and health but omit their full version banner.

## DaVinci Resolve editions

Use `embedded status` when the only question is the installed/running/authenticated state of the embedded Free bridge.

## Examples

- `cutagent doctor --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
