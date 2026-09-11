# `launch`

Syntax: `cutagent launch [--headless] [--wait] [--timeout-s VALUE] [--resolve-path VALUE]`

## Search terms

- launch DaVinci Resolve
- CutAgent CLI launch
- DaVinci Resolve headless
- launch -nogui
- wait for scripting bridge
- already running DaVinci Resolve
- Resolve binary path
- launch timeout cleanup
- DaVinci Resolve startup automation

## What it does

Launch DaVinci Resolve.

## Do not use when

Do not use launch to reconnect or restart an unhealthy existing process without understanding its special branch. If the process exists but the bridge is unreachable, no second process is spawned; wait may time out.
Do not pass `--headless` assuming an already running GUI instance will become headless. The flag only alters a new spawn command.
Do not use `--no-wait` when the next operation requires scripting readiness. It can return immediately with `connected:false`.
Do not trust default dry-run as proof that the installed binary path is valid.
Do not point `--resolve-path` at an untrusted executable. The command runs the exact executable in a new session with stdio discarded.
Do not launch during unsaved/modal/shutdown-sensitive application state without an operational plan.

## Preflight and readback

Dry-run with an explicit known path when binary validation matters. Validate a finite positive timeout even with no-wait.
When wait reports connected, run `status`/`connect` and verify product/version/current page.

## Public arguments and options

- `--headless` (optional, default: `false`) — Launch DaVinci Resolve with -nogui
- `--wait/--no-wait` (optional, default: `true`) — Wait until scripting bridge is reachable
- `--timeout-s` (optional, default: `60.0`) — Wait timeout in seconds
- `--resolve-path` (optional) — Path to DaVinci Resolve binary

## Boundaries and gotchas

- Options are `--headless`, `--wait/--no-wait`, `--timeout-s FLOAT`, and `--resolve-path TEXT`.
- Timeout must be finite and greater than zero.
- Explicit/configured paths must be executable files.
- Dry-run validates timeout.
- Dry-run resolves/validates the binary only when an explicit `--resolve-path` was supplied.
- Dry-run does not inspect current process state or scripting reachability.
- `--headless` adds only `-nogui`; it does not add project/script arguments.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent launch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
