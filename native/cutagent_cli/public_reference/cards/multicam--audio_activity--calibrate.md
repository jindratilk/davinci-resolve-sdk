# `multicam audio-activity calibrate`

Syntax: `cutagent multicam audio-activity calibrate [--angle VALUE] [--audio-source VALUE] [--audio-angle-map VALUE] [--audio-target VALUE] [--audio-sync VALUE] [--sync-reference-audio VALUE] [--sync-reference-angle VALUE] [--sync-reference-source VALUE] [--audio-offsets-json VALUE] [--overlap-policy VALUE] [--overlap-angle VALUE] [--transcript VALUE] [--transcript-speaker-map VALUE] [--style VALUE] [--duration-limit-seconds VALUE] [--fps VALUE] [--write-analysis VALUE] [--ranked-candidates VALUE]`

## Search terms

- calibrate audio activity multicam
- recommend podcast switching thresholds
- rank audio activity candidates
- speaker audio angle map
- reactive balanced calm switching
- transcript assisted calibration
- waveform audio sync calibration

## What it does

Recommend audio-activity switching thresholds without mutating DaVinci Resolve.

## Do not use when

Do not use a recommendation as an automatic creative verdict. Review its confidence, risks, metrics, samples, source gain balance, transcript agreement, and actual edit pacing.
Do not assume this command is side-effect-free under global dry-run. `--write-analysis` still writes/overwrites a real file because that branch does not check dry-run.
Do not assume the advertised style set is enforced.
Do not use a short calibration slice as proof of whole-program behavior. Silence, overlap, speaker balance, drift, interjections, and pacing can differ later.
Apply reviewed settings later through the multicam switch workflow.

## Preflight and readback

Record source hashes.
Start with a bounded duration and a small returned ranking, but remember all candidate plans are still computed. Compare balanced/reactive/calm results on representative sections.
After output, inspect recommendation score/confidence/risks, candidate count versus returned rank count, coverage/silence/overlap/switch-rate metrics, diagnostics, and sample problem intervals. Then apply settings to a disposable edit and verify the resulting cuts in DaVinci Resolve.

## Public arguments and options

- `--angle` (optional, repeatable) — Repeatable angle spec: A=camA.mov
- `--audio-source` (optional, repeatable) — Repeatable audio activity source spec: id=/path/audio.wav
- `--audio-angle-map` (optional) — Audio activity mapping: source_id=ANGLE,source_id=ANGLE
- `--audio-target` (optional, repeatable) — Repeatable flexible target spec: source_id=ANGLE or source_id=ANGLE_A,ANGLE_B
- `--audio-sync` (optional, default: `"prealigned"`) — Audio sync mode: prealigned, waveform, offsets-json
- `--sync-reference-audio` (optional) — Reference camera/audio file for waveform audio sync
- `--sync-reference-angle` (optional) — Reference angle for waveform audio sync when --angle contains source paths
- `--sync-reference-source` (optional, repeatable) — Repeatable source-specific waveform reference: source_id=/path/reference_camera.mov
- `--audio-offsets-json` (optional) — Path to JSON offsets object for audio-activity sync
- `--overlap-policy` (optional) — Overlap handling while scoring: angle/wide, dominant, hold, mark
- `--overlap-angle/--wide-angle` (optional) — Multicam angle to use for overlap/wide moments
- `--transcript` (optional) — Optional speaker-labelled transcript JSON for transcript-assisted calibration
- `--transcript-speaker-map` (optional) — Optional transcript speaker to audio source mapping: speaker_0=speaker_1,speaker_1=speaker_2
- `--style` (optional, default: `"balanced"`) — Calibration style: balanced, reactive, calm
- `--duration-limit-seconds` (optional) — Analyze only the first N seconds for quick calibration
- `--fps` (optional, default: `24.0`) — Timeline frames per second for waveform offset conversion
- `--write-analysis` (optional) — Optional JSON path to write the full calibration result
- `--ranked-candidates` (optional, default: `8`) — Number of ranked candidates to include in the response

## Boundaries and gotchas

- At least one `--angle` is mandatory.
- At least one `--audio-source` is mandatory.
- Duplicate convenience angle labels are rejected.
- Duplicate audio-source IDs are rejected.
- Duration limit must be greater than zero and is rounded to integer milliseconds.
- `--ranked-candidates` is constrained to 1–50.
- That option truncates returned ranked candidates; it does not reduce the candidate grid computation.
- Global dry-run performs full source decoding, level analysis, candidate generation, and ranking.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent multicam audio-activity calibrate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
