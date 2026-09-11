# `color group graph`

Syntax: `cutagent color group graph GROUP [--stage VALUE]`

## Search terms

- inspect Color group node graph
- count pre-clip group nodes
- count post-clip group nodes
- check shared grading graph exists
- inspect group pre clip grade
- inspect group post clip grade
- verify Color group pipeline stage

## What it does

Inspect a color group's pre and post clip node graph.

## Do not use when

This command cannot edit a group graph and cannot answer what a group grade visually does; use the appropriate Color-page group-node mutation/readback surface plus render verification. Do not confuse `--stage pre/post` with before/after command snapshots—these are two persistent processing stages surrounding each member clip's local nodes.

## Preflight and readback

Confirm the exact group and member clips, inspect both stages before changing group grading, and record each node count. After a group-node mutation, rerun the matching stage and render at least one member clip; an unchanged/increased count does not prove parameters or connections. Also render an ungrouped control clip when testing the shared scope.

## Public arguments and options

- `GROUP` (required) — Color group name
- `--stage` (optional, default: `"pre"`) — pre|post

## Boundaries and gotchas

- `--stage` accepts exactly lowercase `pre` or `post`; `middle` returned a zero-duration validation error.
- Output is only a count summary.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color group graph --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
