#!/usr/bin/env node
import { realpath } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import * as sdk from "./index.js";

const ACTIVITY_PREFIX = "CUTAGENT_SDK_ACTIVITY_V1\t";
const HELP = `Usage: cutagent-sdk --title "Action description" script.mjs

Run an ES module with the installed CutAgent SDK. The module must export an
async default function receiving { sdk, client, project, timeline, snapshot, progress }.
Call progress("Current step") to report real progress. Ordinary console output
and errors remain visible. The runner has no overall execution timeout.
`;

type Client = Awaited<ReturnType<typeof sdk.CutAgent.connect>>;
type Project = Awaited<ReturnType<Client["projects"]["current"]>>;
type Timeline = Awaited<ReturnType<Project["timelines"]["current"]>>;
interface ScriptContext {
  sdk: typeof sdk;
  client: Client;
  project: Project;
  timeline: Timeline;
  snapshot: Awaited<ReturnType<Timeline["snapshot"]>>;
  progress: (message: string) => void;
}
interface RunnerDependencies {
  connect?: typeof sdk.CutAgent.connect;
  load?: (url: string) => Promise<{ default?: unknown }>;
  write?: (text: string) => void;
}

// Exported for focused tests; the CLI is the supported entry point.
export async function runSdkScript(args: readonly string[], dependencies: RunnerDependencies = {}): Promise<void> {
  const write = dependencies.write ?? ((text: string) => { process.stdout.write(text); });
  if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
    write(HELP);
    return;
  }
  if (args.length !== 3 || args[0] !== "--title") throw new Error(HELP.trim());
  const title = args[1]?.trim();
  const scriptPath = args[2];
  if (!title || title.length > 200 || /[\x00-\x1f\x7f]/.test(title)) {
    throw new Error("Provide an action title of 1–200 characters without control characters.");
  }
  if (!scriptPath || !/\.mjs$/i.test(scriptPath)) throw new Error("Provide an ES module script file ending in .mjs.");
  const scriptUrl = pathToFileURL(await realpath(resolve(scriptPath))).href;
  const startedAt = performance.now();
  const emit = (event: object) => write(`${ACTIVITY_PREFIX}${JSON.stringify({ version: 1, ...event })}\n`);
  const progress = (message: string) => {
    if (typeof message !== "string" || !message.trim() || message.length > 500 || /[\x00-\x1f\x7f]/.test(message)) {
      throw new Error("Progress must be 1–500 characters without control characters.");
    }
    emit({ kind: "progress", title, message: message.trim(), elapsed_ms: Math.round(performance.now() - startedAt) });
  };
  emit({ kind: "start", title });
  progress("Checking the current project and timeline");
  const client = await (dependencies.connect ?? sdk.CutAgent.connect)();
  let failed = false;
  try {
    const project = await client.projects.current();
    const timeline = await project.timelines.current();
    await client.projects.context();
    const snapshot = await timeline.snapshot();
    // Import only after preflight: module top-level code can itself perform work.
    const script = await (dependencies.load ?? ((url: string) => import(url)))(scriptUrl);
    if (typeof script.default !== "function") throw new Error("The SDK script must export a default async function.");
    progress("Running the SDK script");
    await (script.default as (context: ScriptContext) => unknown)({ sdk, client, project, timeline, snapshot, progress });
    // Native process exit is the only completion signal. No post-script inspection.
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    try { await client.close(); }
    catch (error) { if (!failed) throw error; }
  }
}

const invokedPath = process.argv[1] ? await realpath(process.argv[1]).catch(() => resolve(process.argv[1]!)) : null;
if (invokedPath === fileURLToPath(import.meta.url)) {
  try { await runSdkScript(process.argv.slice(2)); }
  catch (error) {
    process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
