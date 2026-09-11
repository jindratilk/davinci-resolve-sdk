# `dctl apply`

Syntax: `cutagent dctl apply CLIP NAME [--node VALUE]`

## Search terms

- apply DCTL to clip
- put DCTL on color node
- use DaVinci CTL transform
- add custom color transform to shot
- apply .dctl file
- load DCTL as node LUT
- make clip grayscale with DCTL
- assign LUT to named timeline clip
- apply SDK DCTL
- set node LUT from DCTL path
- use installed DCTL on grade node

## What it does

Apply a DCTL as a node LUT to a timeline clip.

## Do not use when

Use `color page dctl-apply` when the current Color-page clip may be implicit or when the workflow needs the newer before/after Deliver render proof. Use `dctl install` to install without assigning a clip, `dctl validate` for the source's lightweight syntax check, and `dctl list` to discover SDK/user DCTL files.
Do not use this command for transition DCTLs, ACES IDT/ODT registration or a DCTL OpenFX plugin with exposed controls; a Color-node LUT slot is the wrong host. Resolve the exact instance/version first or use a command with track/record-frame targeting.

## Preflight and readback

Use a separate Color version/checkpoint for the test because applying replaces any LUT already assigned to that node.
Export or Deliver-render a representative frame and inspect the intended transform; this command does not supply pixel proof. Save the project only after the image is accepted.

## Public arguments and options

- `CLIP` (required) — Timeline clip name
- `NAME` (required) — DCTL/LUT name or path
- `--node` (optional, default: `1`) — Color node index

## Boundaries and gotchas

- The assignment applies only to the currently active Color version.
- It does not say which local/remote version was active in its output.
- `--node` below 1 is rejected locally, but a positive index is not prevalidated against node count.
- It does not create a missing node.
- A valid DCTL and valid clip can still fail solely because the node index does not exist.
- It does not resolve the clip, active version, node count, source file, install root, candidate key or DaVinci Resolve support.

## DaVinci Resolve editions

There is no explicit Studio-versus-Free branch. - The project is not automatically saved.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent dctl apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
