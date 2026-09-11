# `timeline mark clear`

Syntax: `cutagent timeline mark clear [--type VALUE]`

## Search terms

- clear timeline in and out
- remove timeline range marks
- reset render range
- clear video in out points
- clear audio in out points
- unmark timeline section
- clear both timeline ranges

## What it does

Clear timeline mark in and out points.

## Do not use when

Do not use this to delete named/colored timeline markers; use the timeline marker-delete command.

## Preflight and readback

Run `timeline mark get` first and retain both categories when undo or restoration may be needed. Choose `--type video` or `--type audio` when the other category must survive; omit `--type` only when both should be removed. Rerun `timeline mark get` afterward and require the targeted category to be `{}` while checking that any untargeted category still has its original bounds.

## Public arguments and options

- `--type` (optional, default: `"all"`) — all|video|audio

## Boundaries and gotchas

- The default is `--type all`; omitting the option can erase a separately configured audio range along with the video range.
- Clearing `video` does not clear `audio`, and vice versa.
- Clearing a range does not remove point markers, marker metadata, render jobs, or content.

## Examples

- `cutagent timeline mark clear --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
