# `audio beat-detect`

Syntax: `cutagent audio beat-detect INPUT [--fps VALUE] [--min-bpm VALUE] [--max-bpm VALUE] [--beats-per-bar VALUE] [--bars-per-phrase VALUE] [--beat-offset VALUE]`

## Search terms

- detect music beats
- find tempo from song
- edit video to beat
- music phrase boundaries
- frame snapped beat markers
- find downbeats for montage
- plan cuts to music
- bpm analysis

## What it does

Detect musical beats and phrase candidates.

## Do not use when

Do not use this as unquestioned ground truth on rubato music, weak or ambiguous percussion, changing meter, swing, pickup measures, long ambient passages, or tempo changes. Do not treat every beat as a required cut. Use dialogue/transcript or silence analysis when speech meaning, rather than musical pulse, owns the edit.

## Preflight and readback

Run `audio info` first when stream selection or duration is uncertain. Pass the actual timeline fps so frame snapping matches the destination timeline. Adjust `--beat-offset` only after identifying the real downbeat.

## Public arguments and options

- `INPUT` (required) — Input music or media file
- `--fps` (optional, default: `24.0`) — Timeline frame rate used for frame-snapped beat positions
- `--min-bpm` (optional, default: `60.0`) — Minimum tempo to consider
- `--max-bpm` (optional, default: `200.0`) — Maximum tempo to consider
- `--beats-per-bar` (optional, default: `4`) — Meter used to infer downbeats
- `--bars-per-phrase` (optional, default: `8`) — Bars used to infer phrase starts
- `--beat-offset` (optional, default: `0`) — Shift the inferred downbeat/phrase grid by this many beats

## Boundaries and gotchas

- Narrow `--min-bpm` and `--max-bpm` to the musically plausible range.
- Pickup notes require `--beat-offset` or manual interpretation.
- It does not verify DaVinci Resolve state or editorial quality.

## Examples

- `cutagent audio beat-detect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
