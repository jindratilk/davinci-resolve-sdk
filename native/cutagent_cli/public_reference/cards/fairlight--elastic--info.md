# `fairlight elastic info`

Syntax: `cutagent fairlight elastic info [--limit VALUE]`

## Search terms

- inspect Elastic Wave state
- list audio clips with retiming
- find stretched Fairlight clips
- verify Elastic timing points
- check Voice General Purpose Varispeed state
- audit audio retime storage
- see clip stretch duration and keyframes

## What it does

Read stored speed and retime profile candidates for Fairlight Elastic Wave research.

## Do not use when

Do not use this command to turn Elastic Wave on/off; use `fairlight elastic enable`. Do not use it to change duration or timing points; use `fairlight elastic keyframe`.

## Preflight and readback

Confirm the intended project and active timeline, save recent GUI changes, and start with enough limit to avoid truncating the clip of interest. After `elastic enable` or `elastic keyframe`, rerun the command and compare the same stable ID, not array position or display name.

## Public arguments and options

- `--limit` (optional, default: `20`)

## Examples

- `cutagent fairlight elastic info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
