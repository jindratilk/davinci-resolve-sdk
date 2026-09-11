# `fairlight track hide`

Syntax: `cutagent fairlight track hide INDEX`

## Search terms

- hide Fairlight track
- conceal audio track
- remove A1 from timeline view
- hide audio lane without muting
- make Fairlight track invisible
- declutter Fairlight timeline
- hide waveform track
- collapse one audio track from view
- track visibility off
- keep audio playing but hide track
- persist hidden audio track
- hide mixer timeline lane

## What it does

Hide a Fairlight audio track.

## Do not use when

Use `fairlight mute` when the user means “make this track inaudible.” Mute changes audio output but does not hide the timeline row.
Use the track enable/disable command when the user means disabling the track's processing/playback state.
Use `fairlight track folder` only when the user wants DaVinci Resolve 21 folder-track grouping/collapse; that is a different GUI feature and is also explicitly unsupported through the CLI.
Height and visibility are separate: a default or small height does not mean hidden.
For a real hide/show change, perform it manually in DaVinci Resolve.
Do not substitute track deletion for hiding. `fairlight delete` removes the audio track and its timeline items; hide is supposed to be a reversible display-only action.

## Preflight and readback

Before invoking, disambiguate “hide” from mute, disable, lock, folder collapse and delete. If the user truly means layout visibility, inspect the active track list only to identify the intended manual target; this command itself will not validate it.
After a manual GUI hide, verify visually that the track row is absent while its intended audible state is unchanged. There is no CLI visibility getter, so `fairlight tracks` can confirm enabled/mute-related properties but cannot prove hidden-versus-shown layout state.

## Public arguments and options

- `INDEX` (required) — Audio track index to hide

## Boundaries and gotchas

- It does not connect to DaVinci Resolve.
- Do not infer visibility from them.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight track hide --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
