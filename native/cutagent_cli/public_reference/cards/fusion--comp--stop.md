# `fusion comp stop`

Syntax: `cutagent fusion comp stop`

## Search terms

- stop Fusion composition playback
- pause Fusion preview
- halt comp playback
- stop animated Fusion graph
- stop current Fusion comp
- freeze Fusion CurrentTime
- end Fusion viewer playback
- cancel running Fusion preview
- stop asynchronous Fusion render
- halt comp Render
- stop looping Fusion animation
- clean up after fusion comp play

## What it does

Stop playback.

## Do not use when

This command targets Fusion comp state and provides no timeline record-frame readback.
Use `fusion comp play` to start an interactive comp preview. Stop has no toggle behavior and never starts playback.
A later Stop is not a substitute for waiting and does not prove that rendering completed successfully.
Use the owning Deliver render-job cancellation/status commands for a Deliver-page render. `fusion comp stop` has no job ID and does not address the Deliver queue.
Use `fusion comp current` before and after Stop when comp identity and numeric local time need to be established. Stop's success message contains neither.
Use clip/page positioning or a clip-scoped Fusion command when more than one composition could be current.

## Preflight and readback

Before Stop, determine whether the running operation is comp playback, a direct asynchronous comp Render, timeline playback, or a Deliver render. Establish the intended project, timeline item, and comp; when reconnecting through separate CLI processes, run `fusion comp current` and verify the returned name/range rather than assuming the UI context stayed fixed.
For an asynchronous Render, inspect graph/Saver outputs and the Fusion UI before deciding that stopping is safe; Stop provides no partial-output cleanup.
Equal values support that local comp time is no longer advancing. Also inspect the Fusion viewer for visible motion and, if the operation was a Render, independently verify render/cache/Saver state.
Comp-local time and timeline record time are different domains and may not move or stop in lockstep.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- When Stop is issued after `fusion comp render` without `--wait`, it still gives no render-specific cancellation status.
- A single current-time sample cannot prove Stop worked.
- Global `--dry-run` is unsafe here.
- Stop does not rewind, restore the prior frame, restore page/viewer selection, switch to Fusion, or bring DaVinci Resolve to the foreground.
- The command is protected as a Fusion mutation even though it does not edit node topology.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion comp stop --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
