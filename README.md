# Turn code into DaVinci Resolve timelines.

CutAgent SDK is a TypeScript SDK and local CutAgent CLI for DaVinci Resolve 20+ Studio and DaVinci Resolve 20+ Free. This source preview runs local editing workflows without a CutAgent account, subscription, or desktop app.

Source: https://github.com/jindratilk/davinci-resolve-sdk. The local package is named `cutagent`; it is not published to npm. Build and install it from this repository.

## What is included

- The complete extracted TypeScript authoring surface, including root, actions, schemas, protocol, and preview entry points.
- Local editing with durable operations, exact project and timeline checks, verification, and recovery.
- CutAgent CLI source for the extracted DaVinci Resolve command surface.
- The Studio external scripting transport.
- The independent Free embedded Lua/file-spool transport.
- Locked Node.js and Python dependency inputs and an inventoried third-party notice set.

Agent skills and creative knowledge are outside this candidate. Setup does not install or rewrite agent skill content.

## Requirements

- macOS 13 or later for the currently qualified local setup.
- Node.js 22.12+ on the Node 22 line, or Node.js 24.x.
- Python 3.12.
- DaVinci Resolve 20+ Studio or DaVinci Resolve 20+ Free.
- DaVinci Resolve Studio: external scripting set to Local.
- DaVinci Resolve Free: the included script installed and activated from `Workspace > Scripts > CutAgentSDK`.
- FFmpeg and FFprobe on `PATH` for workflows that inspect or render media.

Windows source is present, but this candidate rejects Windows setup until same-user ACL validation and live Windows qualification are complete.

## Build and install from source

Build and pack locally:

```sh
npm ci --ignore-scripts
npm run build
npm test
npm run test:types
npm run verify:source
npm pack --json
```

Install the resulting tarball in a clean consumer project:

```sh
npm install /absolute/path/to/cutagent-3.0.0.tgz
npx cutagent setup
```

`setup` installs CutAgent SDK under `~/.local/share/cutagent-sdk` and creates `~/.local/bin/cutagent`. It preserves an existing command from the CutAgent desktop app or another installation. Choose a separate folder when both are installed:

```sh
npx cutagent setup --bin-dir "$HOME/.local/cutagent-sdk-bin"
```

For DaVinci Resolve Free, install the independent embedded script during setup:

```sh
npx cutagent setup --free
```

No setup command opens a browser, signs in, uploads media, or contacts CutAgent Cloud. Package dependency installation may contact the configured npm and Python package indexes.

## Import the SDK

```ts
import {
  CutAgent,
  frames,
  idempotencyKey,
} from "cutagent";
import { ActionIds } from "cutagent/actions";
import { ProjectIdSchema } from "cutagent/schemas";
```

Start the local runtime in a separate terminal:

```sh
cutagent runtime start --transport studio_external
```

For DaVinci Resolve Free:

```sh
cutagent runtime start --transport embedded_free
```

The command prints the connection file used by `CutAgent.connect()`. If the client runs outside the same shell environment, set `CUTAGENT_SDK_DISCOVERY_FILE` to that absolute path.

```ts
import { CutAgent } from "cutagent";

const client = await CutAgent.connect();
const project = await client.projects.current();
const timeline = await project.timelines.current();

console.log({
  project: project.name,
  timeline: timeline.name,
  revision: timeline.revision,
});

await client.close();
```

Direct CutAgent CLI commands use the same canonical executable:

```sh
cutagent --json status
cutagent --json timeline list
cutagent --json capabilities
```

Read each JSON envelope through `ok`, `data`, `error`, and `meta`. For mutations, preserve exact project/timeline identity, use the inspected revision, and verify the returned terminal operation.

## Features in the CutAgent desktop app

AI transcription, AI voice selection/generation, and `video generate` are available in the CutAgent desktop app. In CutAgent SDK, these commands return `HOSTED_SERVICE_REQUIRES_CUTAGENT_APP` with the link `https://cutagent.ai`. They do not connect to a service, upload files, check an account, start billing, or open a browser.

Native transcription and transcription reads exposed by the installed DaVinci Resolve edition remain local capabilities. Native Fairlight voice isolation also remains available where DaVinci Resolve reports it.

The CutAgent desktop app continues to provide these features. This candidate does not change them.

## Update, status, and uninstall

Inspect the managed installation:

```sh
cutagent status --json
```

Updates are deliberate. Install the reviewed newer npm artifact, then rerun setup:

```sh
npm install cutagent@<reviewed-version>
npx cutagent setup
```

`cutagent update` prints this instruction and performs no network request or automatic replacement.

Remove managed executable and versioned runtime files:

```sh
cutagent uninstall
```

Uninstall removes only files recorded as belonging to this standalone setup. Runtime state is retained for recovery. The command does not remove DaVinci Resolve, user projects, media, FFmpeg, Python, Node.js, or CutAgent app files.

## Supported and qualified combinations

| Platform | Edition | Source/runtime state | Native evidence |
| --- | --- | --- | --- |
| macOS arm64 | DaVinci Resolve Studio 21.1 | Enabled | Historical marker baseline passed at commit fb4ad93; current candidate native revalidation awaits the exclusive native lane |
| macOS arm64 | DaVinci Resolve Free 21.1 | Enabled through independent embedded broker | Historical marker baseline passed at commit 172232a; current candidate remote revalidation is pending |
| macOS arm64 | DaVinci Resolve 20+ | Intended by compatibility contract | Full domain matrix remains pending |
| Windows x64 | DaVinci Resolve Studio / Free | Setup blocked | ACL, packaging, and live native qualification remain pending |

The retained Studio and Free records are historical marker baselines from the exact commits named above. They do not qualify the current candidate head, broader native domains, every DaVinci Resolve 20/21 point release, signed installers, notarization, or Windows.

## Security and project safety

CutAgent keeps local connection state private to your OS account, accepts each setup connection once, checks the exact project and timeline before editing, and verifies native changes. The package contains no development bypass and local editing does not require an account or subscription.

DaVinci Resolve database mutations still require native reopen and GUI/render truth. A matching SQLite readback alone is not accepted as success.

## License and provenance

First-party source in this candidate is offered under GNU AGPL v3 only. No custom script exception is included. Third-party components keep their own licenses and notices under [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES/README.md).

Earlier published SDK source was offered under MIT. This candidate preserves that historical grant and does not claim to revoke or retroactively replace rights already received under MIT. [PROVENANCE.md](PROVENANCE.md) records the extraction boundary and license history.

DaVinci Resolve is a product of Blackmagic Design Pty Ltd. CutAgent SDK is independent software and does not include or redistribute DaVinci Resolve.
