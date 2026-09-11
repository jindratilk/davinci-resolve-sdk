# `fairlight dynamics enable`

Syntax: `cutagent fairlight dynamics enable [--track VALUE]`

## Search terms

- enable Fairlight dynamics
- turn on compressor gate limiter
- activate track dynamics
- enable dialogue compression
- turn on noise gate
- turn on limiter
- apply dynamics processing preset
- enable all dynamics modules
- add compressor gate limiter settings
- make dialogue dynamics active
- turn on Fairlight channel dynamics

## What it does

Enable Fairlight dynamics.

## Do not use when

Do not use this merely to turn on an existing tuned compressor/gate/limiter.
Use `fairlight dynamics set` when changing only explicitly mapped parameters or flags.
Do not use this to enable dynamics on one audio track, one bus, one clip or one named timeline. No selector exists.

## Preflight and readback

Treat any multi-timeline project as out of scope unless overwriting all sequence models is explicitly intended.
Inspect every timeline/track, routing/config-dependent behavior and actual audio. Do not accept the built-in three-boolean verification as complete project or acoustic proof.

## Public arguments and options

- `--track` (optional, default: `1`) — Audio track index (1-based)

## Boundaries and gotchas

- The source mapping notes that this scale is nonlinear (roughly 1:1.1 at 0), so “gate enabled” does not alone describe the audible gate behavior.
- Only the active timeline is restored after reopen.
- The command ran only in a separate one-timeline disposable project.

## DaVinci Resolve editions

Free was not independently exercised for this card.

## Examples

- `cutagent fairlight dynamics enable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
