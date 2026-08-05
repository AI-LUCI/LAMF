#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

function fail(message) {
  process.stderr.write(`[LAMF Desktop] ${message}\n`);
  process.exit(1);
}

const configuredRoot = process.env.LAMF_ROOT;
if (!configuredRoot || !configuredRoot.trim()) {
  fail("No LAMF installation folder was configured. Open the extension settings and select the folder containing runtime and data.");
}

let root;
try {
  root = fs.realpathSync(configuredRoot);
} catch (error) {
  fail(`The configured LAMF folder is unavailable: ${error.message}`);
}

const runtimeDir = path.join(root, "runtime");
const server = path.join(runtimeDir, "lamf_mcp.py");
const dataDir = path.join(root, "data");
const python = process.platform === "win32"
  ? path.join(runtimeDir, ".venv", "Scripts", "python.exe")
  : path.join(runtimeDir, ".venv", "bin", "python");

for (const [label, target, kind] of [
  ["MCP server", server, "file"],
  ["Python runtime", python, "file"],
  ["LAMF data directory", dataDir, "directory"]
]) {
  let stat;
  try {
    stat = fs.statSync(target);
  } catch (error) {
    fail(`${label} was not found at ${target}. Select the LAMF installation folder, not its data subfolder.`);
  }
  if ((kind === "file" && !stat.isFile()) || (kind === "directory" && !stat.isDirectory())) {
    fail(`${label} has the wrong type at ${target}.`);
  }
}

const env = {
  ...process.env,
  LAMF_DATA_DIR: dataDir,
  LAMF_HARNESS: process.env.LAMF_HARNESS || "claude-desktop"
};
delete env.LAMF_ROOT;

const child = spawn(python, [server], {
  cwd: runtimeDir,
  env,
  shell: false,
  // Claude Desktop runs this launcher in an Electron utility process. Explicit
  // pipes are required here: inherited descriptors can be closed after launch,
  // which makes the Python MCP server see EOF and disconnect immediately.
  stdio: ["pipe", "pipe", "pipe"],
  windowsHide: true
});

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);
child.stderr.pipe(process.stderr);

for (const stream of [process.stdin, child.stdin, child.stdout, child.stderr]) {
  stream.on("error", (error) => {
    if (error.code !== "EPIPE" && error.code !== "ERR_STREAM_PREMATURE_CLOSE") {
      process.stderr.write(`[LAMF Desktop] Stream error: ${error.message}\n`);
    }
  });
}

child.on("error", (error) => {
  fail(`Unable to start the existing LAMF MCP server: ${error.message}`);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code === null ? 1 : code);
});

process.stdin.on("end", () => child.stdin.end());

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    if (!child.killed) child.kill(signal);
  });
}
