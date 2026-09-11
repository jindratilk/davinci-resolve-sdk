# `transcript create`

Syntax: `cutagent transcript create OUTPUT_PATH [--language-code VALUE] [--diarize] [--num-speakers VALUE] [--keyterm VALUE] [--no-verbatim] [--resume-job VALUE] [--new-job] [--force]`

## Search terms

- transcribe active timeline
- create transcript json
- speech to text timeline
- speaker diarization
- transcript for captions
- transcript for podcast edit
- account hosted transcription
- ElevenLabs transcript

## What it does

Transcribe the active timeline through the signed-in CutAgent account.

## Do not use when

Do not use this when an existing current transcript already matches the active timeline, when the user has not authorized a billable hosted transcription, or when the active project and timeline are uncertain. Do not use it as a generic local audio-file transcription command: its source is the active timeline. Use timeline or media inspection instead when the task needs clip identity or audio metadata rather than speech recognition.

## Preflight and readback

Run CutAgent authorization preflight, confirm DaVinci Resolve is connected, and inspect the active project and timeline before starting. Recheck the active timeline if it may have changed during the request.

## Public arguments and options

- `OUTPUT_PATH` (required) — Output path for the hosted transcript JSON
- `--language-code` (optional) — Optional BCP-47 transcript language code
- `--diarize/--no-diarize` (optional, default: `true`) — Identify and label different speakers
- `--num-speakers` (optional) — Expected number of speakers
- `--keyterm` (optional, repeatable) — Important term to bias transcription; repeat as needed
- `--no-verbatim` (optional, default: `false`) — Allow provider-side removal of verbal disfluencies
- `--resume-job` (optional) — Resume a pending hosted transcript job without rendering or uploading again
- `--new-job` (optional, default: `false`) — Intentionally render and start a separate billed transcript job
- `--force` (optional, default: `false`) — Replace an existing output file

## Boundaries and gotchas

- The CutAgent desktop authorization broker must remain reachable for the command; never synthesize or persist its short-lived credentials.
- Use `--no-diarize` only when speaker labels are unnecessary.
- `--num-speakers` accepts 1 through 32 and is meaningful only as guidance for diarization.
- `--keyterm` is repeatable, duplicate values are removed, and at most 1000 unique values are accepted.
- Without `--force`, an existing destination fails closed.
- With `--force`, the existing file is replaced after a successful response.
- Do not retry implicitly; ask before using `--new-job` because it may create separate billed usage.
- Use `--new-job` only when the user intentionally wants a separate billed transcript from a newly rendered timeline; the earlier pending job remains resumable by its job ID.
- A different timeline or transcript profile does not bypass that billing gate.
- If the response or acknowledgement is lost, rerun the same command (using `--force` only when the already-written destination must be replaced); CutAgent replays the completed result without another render, upload, or billed job.
- After delivery acknowledgement, CutAgent keeps only a compact billing tombstone.
- Do not use it as proof that the active timeline has remained unchanged since the original render.

## Stable public error codes

- `AUTHORIZATION_ACCOUNT_MISMATCH`
- `HOSTED_TRANSCRIPT_ATTEMPT_UNCERTAIN`
- `HOSTED_TRANSCRIPT_NEW_JOB_REQUIRED`
- `HOSTED_TRANSCRIPT_PENDING`
- `HOSTED_TRANSCRIPT_RESUME_REQUIRED`
- `TRANSCRIPT_ATTEMPT_AUDIO_UNAVAILABLE`

## Examples

- `cutagent transcript create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
