# `ofx build`

Syntax: `cutagent ofx build PATH [--backend VALUE]`

## Search terms

- build OpenFX plugin
- run make for OFX project
- OpenFX backend build
- build OFX with Metal
- make OpenFX project
- OpenFX build dry-run
- OFX Makefile stdout stderr
- OpenFX build failure
- BACKEND environment for OFX

## What it does

Build an OpenFX effect project.

## Do not use when

Do not run this command on an untrusted project or Makefile.
Do not assume `--backend` validates `cpu`, `cuda`, `opencl`, or `metal`.
Do not expect the generated `ofx scaffold` result to build.
Do not use this command when a specific make target, parallelism flag, toolchain option, clean build, timeout, streaming log, or controlled environment is required.

## Preflight and readback

Pin and independently verify the intended `make` executable and toolchain.
Run global dry-run and confirm the resolved make path, project path, backend, and absence of build artifacts afterward. Remember that dry-run does not inspect or display Makefile recipes.
Installation and real DaVinci Resolve discovery/render proof are distinct steps. Clean up only isolated test build outputs or use the project's reviewed cleanup procedure.

## Public arguments and options

- `PATH` (required) — Project folder
- `--backend` (optional) — cpu|cuda|opencl|metal

## Boundaries and gotchas

- `--backend TEXT` is optional; help suggests `cpu|cuda|opencl|metal`.
- It does not run `make -n`.
- Although subprocess invocation does not use a shell directly, Make recipes normally do.

## Examples

- `cutagent ofx build --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
