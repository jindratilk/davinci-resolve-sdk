# `multicam convert`

Syntax: `cutagent multicam convert [--timeline VALUE] [--compound VALUE] [--media-id VALUE] [--multicam-name VALUE] [--force]`

## Search terms

- multicam convert
- Convert tracks into a multicam clip.
- multicam convert help
- multicam convert command

## What it does

Convert tracks into a multicam clip.

## Do not use when

Do not pass both `--timeline` and `--compound`. Do not use sources with fewer than two or more than six logical video tracks.

## Preflight and readback

Inspect source track contents and checkpoint the project. After conversion require the new Media Pool multicam, exact angle/item bindings, paired audio timing, source identity, and save/close/reopen visibility.

## Public arguments and options

- `--timeline` (optional)
- `--compound` (optional)
- `--media-id` (optional)
- `--multicam-name` (optional) — Optional new multicam clip name
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- Exactly one of `--timeline` or `--compound` is required.
- `--multicam-name` is required.

## Examples

- `cutagent multicam convert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
