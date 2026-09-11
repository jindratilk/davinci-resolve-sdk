# `timeline create`

Syntax: `cutagent timeline create NAME [--width VALUE] [--height VALUE] [--fps VALUE]`

## Search terms

- create empty timeline
- make new sequence
- start a 1080p timeline
- new timeline at 24 fps
- create timeline with custom resolution
- add blank timeline to project
- initialize editing sequence
- new vertical timeline

## What it does

Create a new empty timeline.

## Do not use when

Do not use `timeline create` to build a timeline from selected Media Pool clips; use the media/timeline creation route that accepts clip inputs. Do not use it to duplicate an existing edit; use `timeline duplicate`. Do not use it to import an XML/AAF/EDL/OTIO timeline; use `timeline import`. Do not use it to change the current timeline's dimensions or fps; use `timeline settings-set` after checking whether that setting is mutable. Do not pass only a width and assume height/fps are derived as a coherent preset; specify every setting that must be guaranteed.

## Preflight and readback

When creating the project's first timeline with custom settings, capture project settings because this command temporarily/ultimately establishes project defaults. After success, run `timeline list` to prove the new timeline is current and `timeline info` to verify resolution, fps, baseline tracks, start timecode, and empty duration before importing or appending media.

## Public arguments and options

- `NAME` (required) — Timeline name
- `--width` (optional) — Resolution width
- `--height` (optional) — Resolution height
- `--fps` (optional) — Frame rate

## Boundaries and gotchas

- Any workflow that expected to keep editing the previous timeline must switch back explicitly.
- First-timeline custom settings are written at project scope before creation.
- Dry-run does not query those defaults.

## Examples

- `cutagent timeline create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
