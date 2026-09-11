# `dctl install`

Syntax: `cutagent dctl install PATH [--kind VALUE] [--overwrite]`

## Search terms

- install DCTL
- copy .dctl into DaVinci Resolve
- add user DCTL
- install custom color transform
- put DCTL in LUT folder
- register ACES IDT DCTL
- install ACES ODT
- make DCTL available in DaVinci Resolve
- copy DCTL to user support folder
- replace installed DCTL
- deploy DaVinci CTL file

## What it does

Install a DCTL into a user DaVinci Resolve support folder.

## Do not use when

Use `dctl apply` to assign a transform to a specific timeline clip/node, or `color page dctl-apply` when assignment also needs rendered before/after proof. Use `dctl validate` before installation to reject obvious non-DCTL input, because install does not validate it. Use `dctl scaffold` to create source rather than copying an existing file.
Do not use the default `lut` kind for an ACES input/output transform, and do not use ACES destinations for an ordinary node transform. Do not rely on `dctl list` to verify ACES installs: it scans the user LUT root and SDK tree, but not the user ACES IDT/ODT roots.

## Preflight and readback

Before installation, run `dctl validate`, determine whether the source is a node transform, ACES IDT or ACES ODT, and run a dry-run to inspect the exact destination.
For LUT-kind installs, confirm it appears in `dctl list`; inspect ACES destinations directly. Restart DaVinci Resolve or use an explicit refresh-capable LUT/ACES workflow before assuming the application has discovered the file. Apply it to a disposable Color version and render-test it separately.

## Public arguments and options

- `PATH` (required) — .dctl path
- `--kind` (optional, default: `"lut"`) — lut|aces-idt|aces-odt
- `--overwrite` (optional, default: `false`) — Replace an existing installed DCTL

## Boundaries and gotchas

- `--kind` is not validated.
- The ACES kind does not prove ACES semantics.
- `dctl list` sees the user LUT install but omits user ACES IDT/ODT installs, so an empty list result cannot disprove an ACES installation.
- Dry-run still checks source existence and destination conflict before returning.
- `--overwrite` removes the old destination before copying the new one.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent dctl install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
