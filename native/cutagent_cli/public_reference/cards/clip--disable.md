# `clip disable`

Syntax: `cutagent clip disable [NAME]`

## Search terms

- disable one timeline clip
- turn off a clip without deleting it
- bypass video occurrence
- mute a single edit item
- temporarily hide timeline clip
- deactivate clip in DaVinci Resolve
- compare edit with clip off
- disable selected timeline item

## What it does

Disable a clip.

## Do not use when

Use `timeline track disable` when the intended scope is an entire video/audio track. Use Fairlight mute/automation for attenuation or a mix decision, and deletion commands only when removal/ripple semantics are explicitly wanted. This command targets one occurrence and does not automatically disable linked audio/video partners.

## Preflight and readback

Identify the exact occurrence before mutation. For delivery-critical work, also inspect program output or a short render. Restore with `clip enable` and require its true readback.

## Public arguments and options

- `NAME` (optional)

## Boundaries and gotchas

- It does not automatically disable a linked counterpart, every source occurrence, or the whole track.
- Repeating disable is idempotent but does not distinguish already-disabled from newly disabled.

## Examples

- `cutagent clip disable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
