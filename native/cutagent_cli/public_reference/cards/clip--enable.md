# `clip enable`

Syntax: `cutagent clip enable [NAME]`

## Search terms

- enable one timeline clip
- turn a disabled clip back on
- reactivate timeline item
- unmute a single edit clip
- restore hidden video occurrence
- make clip active again
- re-enable selected clip
- undo clip disable

## What it does

Enable a clip.

## Do not use when

Use `timeline track enable` when the whole track is disabled. Enabling one occurrence does not enable linked counterparts or other occurrences of the same source.

## Preflight and readback

Identify the exact occurrence before mutation.

## Public arguments and options

- `NAME` (optional)

## Boundaries and gotchas

- The intended scope is one timeline object.
- Duplicate names are first-match only, with no track/time selector.
- Repeating enable is idempotent but does not distinguish already-enabled from newly enabled.

## Examples

- `cutagent clip enable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
