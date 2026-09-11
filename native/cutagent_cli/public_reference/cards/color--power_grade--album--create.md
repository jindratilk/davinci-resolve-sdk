# `color power-grade album create`

Syntax: `cutagent color power-grade album create NAME`

## Search terms

- create a PowerGrade album
- add a shared grade library folder
- make a new PowerGrades collection
- organize reusable grades in an album
- create empty PowerGrade bin
- new Gallery PowerGrade album
- prepare album for reusable looks
- add PowerGrade category
- create user gallery grade album
- make a PowerGrade destination before saving stills

## What it does

Create a PowerGrade album.

## Do not use when

Use `color power-grade list` to enumerate saved PowerGrade stills, not to create a container. Use `color gallery still grab` to capture a current-frame grade into the currently selected regular album, and use `color power-grade apply`/`template-apply` to apply an existing PowerGrade to a clip.

## Preflight and readback

Before creating, confirm the desired scope is a PowerGrade album rather than a normal Gallery album, inspect the Gallery UI for existing names, and normalize/reject blank or unsafe names in the agent because this command does not. Decide how the new empty album will be selected and populated afterward; the command leaves the current album unchanged.
Verify the new empty album directly in DaVinci Resolve's PowerGrade Gallery UI or through a dedicated album enumeration outside this command. Do not use `color power-grade list` as negative proof: that command emits one row per still and omits empty albums.

## Public arguments and options

- `NAME` (required) — PowerGrade album name

## Boundaries and gotchas

- A false/missing rename does not cause command failure.
- It does not return empty album rows.
- It does not set the new PowerGrade album as current.
- The CLI currently exposes only `album create` under `color power-grade album`; there is no matching list/current/switch/rename/delete surface.

## Examples

- `cutagent color power-grade album create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
