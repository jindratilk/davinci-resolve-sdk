# DaVinci Resolve SDK

This source preview retains the **complete existing `davinci-resolve-sdk` interface** and existing SDK HTTP/action routes. Local bootstrap and session ownership work without a CutAgent account, subscription, desktop installation, cloud issuer or development bypass. The distribution is explicitly `standalone_local`.

The native composition now reuses the existing Python runtime, bridge execution wrappers, guarded live inspection and native factories for markers, timeline edits/structure/move/blade, project/media, color, multicam, storage, render, captions, Fusion graphs and typed reads. Start it with `startNativeLocalRuntime({stateDirectory, transport})` from `runtime/index.mjs`. The original prepared-action host and production builder selections now join these owners, for 639 registered native actions; its complete Python registry initializes 502 prepared descriptors. The original workflow and checkpoint owners are composed too. Unsupported operations fail closed. This is **not a complete standalone release**, and source tests are not native DaVinci Resolve validation.

## Source verification

Use Node.js 22.12+ (22.x) or 24.x and Python 3.12 (the locked NumPy/SciPy dependencies require 3.12+):

```sh
npm ci --ignore-scripts
npm run build
python3.12 -m venv .venv
.venv/bin/python -m pip install -r native/requirements.lock.txt
npm test
npm run test:types
npm run verify:source
.venv/bin/python -m unittest discover -s test -p 'test_*.py' -v
```

The Node tests use the actual full SDK, private discovery and HTTP routes with a clearly simulated native owner. Python tests use the existing native connection/inspection logic with a simulated native adapter. Neither test suite touches a real project.

For an explicitly requested real read smoke, with DaVinci Resolve running:

```sh
node examples/local-inspect.mjs studio_external
```

`embedded_free` selects the existing embedded transport, including the newly extracted Free Lua spool implementation. The standalone broker uses its own script, auth/spool directory and port; embedded mutations use the broker’s private local capability plus an exact, expiring, one-use command/native-call context; the Free setup has source/process evidence, and real standalone Free marker acceptance has passed. The example only reads the current project and cleans up its private runtime afterwards. A real read-only Studio smoke passed through the full SDK/local HTTP/native inspection chain. That read-only smoke performed no mutation. The later full-runtime Studio marker smoke described below also passed.

## Boundaries

The original complete SDK root/action/schema/protocol/preview exports remain available. The extraction build includes their generated declarations. Existing project identity projection, session token checks, response parsing, deadlines, mutation/operation authority code and ownership invalidation remain in the route closure. The original durable operation repository and authority now start with the local runtime, retain idempotency across restarts, and reconcile interrupted records. Their ownership derives from the private installation identity, without an account or token. Native executors plug into the existing action registry; uncomposed actions fail closed. Mutation authorities are not fabricated when no native owner is supplied.

The local principal is owned by the current process/user and invalidated by generation changes. The inherited private `accountFingerprint` field holds a local ownership fingerprint; no account object or fake paid entitlement is created. Bootstrap requires a private same-user discovery file, unpredictable capability, exact route and one-use runtime bootstrap. Browser origins and non-loopback hosts are denied. Windows ACL validation remains unimplemented and startup rejects Windows explicitly.

`EXTRACTION_INVENTORY.json` and `native/SOURCE_INVENTORY.json` bind exact selected upstream files and their transformations. The extractors take a source path explicitly, so runtime/build/test execution does not depend on the monorepo. Re-extraction is maintainer work and overwrites only inventoried source files; it does not overwrite local composition code.

The source verifier checks exact paths and hashes. Defensive schema expressions containing words such as `sqlite` are valid source and do not trigger the old binary-only exporter rule. It still excludes unrelated app/cloud/private-documentation families and private keys. This source policy is local to this authorized open-source candidate; the original product's release policy was not weakened.

The ignored `rejected-sdk-export/` is evidence from the earlier failed upstream exporter and is not part of this candidate. The source preview is public at [jindratilk/davinci-resolve-sdk](https://github.com/jindratilk/davinci-resolve-sdk). No registry release or bundled installer is activated. See [PROVENANCE.md](PROVENANCE.md) for licensing scope and remaining notices, and [extraction-plan.md](extraction-plan.md) for the dependency analysis; the latter records the initial plan and its initial licensing/admission alternatives, not the implemented session authority.

Free broker setup (run only when the target Free environment is assigned):

```sh
.venv/bin/python native/free_broker.py install
.venv/bin/python native/free_broker.py serve
```

Then run `Workspace > Scripts > DaVinciResolveSDK` inside DaVinci Resolve Free. The standalone namespace does not overwrite `CutAgent.lua` or `CutAgent.scriptlib`, focus CutAgent, or use the commercial broker port/state. Process tests proved auth enforcement, spool acknowledgement before execution, stale-response rejection and bounded shutdown. Subsequent real Free source acceptance also passed; see the retained acceptance evidence.

The full native source entrypoint imports successfully and reports its version. Native factory composition and local process/argument custody have source tests; a real Studio marker create/readback/delete smoke passed on 2026-09-08 through the full SDK, local HTTP runtime and native prepared/direct owners. Both operation verifiers passed, and final track/clip/audio and original marker hashes matched the pre-test snapshot. Hosted generation/transcription services remain outside the standalone native runtime scope.

Hosted transcript creation and voice-catalog lookup are excluded from the standalone action registry, so they fail before native dispatch. Native Fairlight voice-isolation controls retain their native scope.

Prepared actions use the existing bounded protocol over private local pipes. Opaque process-owned handles and exact local policy bindings replace commercial signed receipts and redemption; the original request/target checks, native execution, verification/recovery and durable idempotency remain. The inherited private protocol retains some historical field names, but the runtime creates no account or subscription object. Source tests include stale target and local ownership rejection and one-use verified execution with an explicitly simulated descriptor. The combined composition passed the Studio marker smoke; broader native domains remain pending.

The full native implementation also requires locally available FFmpeg/FFprobe for media workflows. The candidate does not redistribute DaVinci Resolve binaries or third-party Windows LuaSocket libraries.

## Guarded native marker acceptance

Run only on an assigned project/timeline, with exclusive mutation ownership:

```sh
node examples/native-marker-smoke.mjs studio_external 'Exact project name' 'Exact timeline name'
```

For the independently running Free broker, use `embedded_free` instead. The script checks both names and native identities, creates one uniquely named marker, reads it back, deletes only that marker, and compares the original markers and all track/clip/audio state. It retains a private `smoke-report.json` in the printed temporary directory. It never switches projects or timelines. Free marker acceptance passed; the precise tested-tree boundary is recorded in docs/FREE_21_1_ACCEPTANCE_2026-09-08.json.

The package name is a candidate pending registry availability and release review. Existing exported class names remain for API compatibility; applications may import `CutAgent as DaVinciResolve` from `davinci-resolve-sdk`. Internal historical protocol fields are implementation details, not account requirements.

Clean installed-package import/type verification is available with `node scripts/smoke-packed-consumer.mjs` after the build. It packs locally, installs into a new temporary consumer directory, verifies all public subpaths and rejects unsupported deep imports. It performs no native connection. See [RELEASE_STATUS.md](RELEASE_STATUS.md) for exact acceptance and release gates.

## Run the companion runtime

After source setup, keep this process running:

```sh
node examples/start-runtime.mjs studio_external /absolute/path/to/private-state
```

The runtime creates or validates the private state directory and prints its discovery-file path. In the consuming process, set `CUTAGENT_SDK_DISCOVERY_FILE` to that path before calling the SDK connection method. This retained technical environment name is a local discovery contract and does not connect to a commercial service. Use SIGINT/SIGTERM for graceful operation drain and shutdown. For Free, start and activate the independent broker/script first, then pass `embedded_free`.

Studio and Free marker create/readback/delete have passed through the standalone runtime. This is a source preview, not blanket validation of every composed native method. The Free evidence distinguishes the live tested tree from the final committed source; later trim fixes have focused source regression coverage.

Exact public commit `fb4ad93` passed the guarded Studio marker create/readback/delete cycle, including final state restoration; see [Studio evidence](docs/STUDIO_PUBLIC_SOURCE_ACCEPTANCE_2026-09-08.json). The Free exact-public-source retry was blocked at initial snapshot before any mutation; [Free evidence](docs/FREE_21_1_ACCEPTANCE_2026-09-08.json) retains both the earlier successful tested-tree result and this later blocker.
