<div align="center">

# 🎬 CutAgent SDK

### Give your AI agent the keys to DaVinci Resolve.

An open-source connection between your agent and your editing timeline.<br>
**Works with DaVinci Resolve 21.1+ Free and Studio.**

[![AGPL-3.0 License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![DaVinci Resolve Free](https://img.shields.io/badge/DaVinci_Resolve-Free_%26_Studio-ff5a2b)](#-yes-it-works-with-davinci-resolve-free)
[![TypeScript](https://img.shields.io/badge/TypeScript-SDK-3178C6)](docs/package/README.md)

[Get started](#-get-started) · [Examples](examples/) · [Documentation](docs/GETTING_STARTED.md) · [CutAgent desktop app](https://cutagent.ai)

</div>

---

## From an idea to an editable timeline

Your agent can write code. Now give it a way to work with your footage.

CutAgent SDK lets agents and scripts organize media, build timelines, edit clips, work with audio, create Fusion graphics, and export videos in DaVinci Resolve. The work stays in your project, where you can inspect it, change it, and keep editing.

Use the TypeScript SDK for editing scripts, or CutAgent CLI when your agent works through a terminal. Bring an agent that can run local code and give it the SDK documentation and examples to work from.

## ✨ What you can build

| Your next project | What the SDK brings |
| --- | --- |
| A real estate reel | Arrange shots, adjust framing, shape the pacing, and add titles. |
| A podcast edit | Organize cameras and audio, work with multicam cuts, and add captions. |
| A repeatable content workflow | Import files, organize bins, apply edits to multiple clips, and export. |
| Your own motion graphics | Build editable Fusion text, node graphs, and keyframe animations. |
| A custom editing assistant | Read the current timeline and let your agent make changes through code. |

These are workflows you can build with the SDK, not one-prompt presets. The agent supplies the editing decisions and script; the SDK connects them to DaVinci Resolve.

## 🆓 Yes, it works with DaVinci Resolve Free

You don't need to buy DaVinci Resolve Studio to get started.

CutAgent SDK includes a local script that connects to the free edition. Install it, open it from **Workspace → Scripts → CutAgentSDK**, and your agent can work with your project.

Studio is supported too. Features that require Studio inside DaVinci Resolve still require Studio; the SDK doesn't unlock paid effects.

**Current platform: macOS.** Windows setup is not available yet. Free and Studio have passed native marker tests on earlier releases; the latest Studio source has also passed a marker create/read/delete test. See [current verification and limitations](RELEASE_STATUS.md) for what has been tested.

## 🤖 Built for agents. Useful for people.

- **Bring your own agent.** Use a coding agent that can run local commands and TypeScript scripts.
- **Keep editing in DaVinci Resolve.** Work with timelines, clips, audio, and Fusion compositions in the editor you already use.
- **Work locally.** Run editing scripts on your computer, directly in DaVinci Resolve.
- **Make it yours.** AGPL-3.0 licensed, so you can inspect, modify, and build on the source under the license terms.

Your agent provider has its own data handling and billing. CutAgent SDK supplies the local editing connection, not an AI model or a library of creative skills.

## 🚀 Get started

You'll need macOS, DaVinci Resolve, Node.js 22.12+ or 24.x, and Python 3.12. Install FFmpeg and FFprobe for media inspection and export workflows.

The SDK is currently installed from source, not npm:

```sh
git clone https://github.com/jindratilk/davinci-resolve-sdk.git
cd davinci-resolve-sdk
npm ci --ignore-scripts
npm run build
npm pack
mkdir ../my-video-project
cd ../my-video-project
npm init -y
npm install ../davinci-resolve-sdk/cutagent-3.0.0.tgz
```

**Using DaVinci Resolve Free?**

```sh
npx cutagent setup --free
```

Open **Workspace → Scripts → CutAgentSDK** in DaVinci Resolve, then start the connection:

```sh
cutagent runtime start --transport embedded_free
```

**Using DaVinci Resolve Studio?** Set external scripting to **Local**, then run:

```sh
npx cutagent setup
cutagent runtime start --transport studio_external
```

Keep that terminal running. It prints the connection-file path; set `CUTAGENT_SDK_DISCOVERY_FILE` to that path in the terminal where your agent or script runs.

[Full setup guide →](docs/GETTING_STARTED.md)

## Your first connection

```ts
import { CutAgent } from "cutagent";

const client = await CutAgent.connect();

try {
  const project = await client.projects.current();
  const timeline = await project.timelines.current();

  console.log(`Ready to edit ${timeline.name} in ${project.name}`);
  console.log(await timeline.snapshot());
} finally {
  await client.close();
}
```

Start with the [examples](examples/), including a marker workflow that creates a temporary marker, reads it back, and removes it again.

## Want the full editing app?

[CutAgent](https://cutagent.ai) brings the editing experience into a desktop app, including its AI transcription, voice generation, and video generation services. The open-source SDK is for building your own local tools and agent workflows.

## Help make it better

Found a bug? [Open an issue](https://github.com/jindratilk/davinci-resolve-sdk/issues) with your operating system, DaVinci Resolve version and edition, and a small script that reproduces it. Leave out credentials and private footage.

Pull requests are welcome. Run the build, tests, and source checks before submitting a change. If this project is useful to you, a star helps other editors and builders find it. ⭐

## License

[GNU AGPL-3.0](LICENSE). Third-party components keep their [own licenses](THIRD_PARTY_NOTICES/README.md).

DaVinci Resolve is a product of Blackmagic Design Pty Ltd. This project is independent and is not affiliated with or endorsed by Blackmagic Design.
