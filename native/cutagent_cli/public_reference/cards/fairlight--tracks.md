# `fairlight tracks`

Syntax: `cutagent fairlight tracks`

## Search terms

- list Fairlight tracks
- show audio tracks
- inspect A1 A2
- count audio tracks
- list track names and formats
- find dialogue track index
- check Fairlight clip counts
- see enabled and locked tracks
- inspect audio track layout
- list audio lane heights
- preflight Fairlight track mutation
- identify target audio track

## What it does

List audio tracks.

## Do not use when

Use `fairlight items INDEX` when clip names and start/end frames on one track are needed. `fairlight tracks` returns only item counts, not clip identities or positions.
The optional fields here are best-effort enrichments.
Use `fairlight info` for broader Fairlight project/timeline context. Use bus/VCA/group commands for those objects; this list is audio tracks only.

## Preflight and readback

Run this immediately before any index-targeted Fairlight mutation and again afterward.
After the read, branch field by field.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- A scalar `pan:null` does not mean centered writable pan.
- Do not interpret a missing `format` key as stereo.

## Examples

- `cutagent fairlight tracks --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
