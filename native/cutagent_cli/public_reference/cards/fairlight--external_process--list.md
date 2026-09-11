# `fairlight external-process list`

Syntax: `cutagent fairlight external-process list [--limit VALUE]`

## Search terms

- list Fairlight external processes
- show configured audio editors
- find iZotope RX round-trip entry
- inspect ExternalFXConfiguration.xml
- external audio process configuration
- configured waveform editor path
- check external process executable
- see DaVinci Resolve external audio apps
- discover audio round-trip tools

## What it does

List configured Fairlight external audio processes from DaVinci Resolve Fairlight XML config.

## Do not use when

Do not use this command to list installed Audio Unit, VST3, or Fairlight FX plugins; use `fairlight effect plugin-catalog` for plugin registries. Do not use a returned entry as proof that `fairlight external-process run` can launch it—the run route is explicitly unsupported. Do not use it to discover an arbitrary system audio editor outside DaVinci Resolve's configuration.

## Preflight and readback

Before reading, identify the host operating system and DaVinci Resolve user/preferences location; the current default path is macOS-specific and global to the user, not the open project. Treat `name`, `executable`, and `arguments` as configuration strings only: verify the executable exists and inspect the tool manually before proposing a workflow.

## Public arguments and options

- `--limit` (optional, default: `100`) — Maximum configured external processes to read

## Boundaries and gotchas

- Only direct leaf children become `fields`; nested XML structures are omitted from normalized fields.
- The reader does not check that `executable` exists, is executable, is compatible with the OS, or matches `name`.
- `--limit` controls only the returned prefix.
- Do not quote or surface them to users unless needed and safe.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight external-process list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
