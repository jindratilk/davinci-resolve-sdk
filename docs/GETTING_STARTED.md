# Get started with CutAgent SDK

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

Package dependency installation may contact the configured npm and Python package indexes.

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
npm install /absolute/path/to/new-cutagent-package.tgz
npx cutagent setup
```

`cutagent update` prints this instruction and performs no network request or automatic replacement.

Remove managed executable and versioned runtime files:

```sh
cutagent uninstall
```

Uninstall removes only files recorded as belonging to this standalone setup. Runtime state is retained for recovery. The command does not remove DaVinci Resolve, user projects, media, FFmpeg, Python, Node.js, or CutAgent app files.


For current platform verification, see [release status](../RELEASE_STATUS.md).
