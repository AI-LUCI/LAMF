"use strict";

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const extensionRoot = path.resolve(__dirname, "..");
const manifest = JSON.parse(fs.readFileSync(path.join(extensionRoot, "manifest.json"), "utf8"));

assert.equal(manifest.manifest_version, "0.4");
assert.equal(manifest.name, "lamf-memory-desktop");
assert.equal(manifest.version, "0.1.1");
assert.equal(manifest.server.type, "node");
assert.equal(manifest.server.entry_point, "server/index.js");
assert.equal(manifest.server.mcp_config.env.LAMF_ROOT, "${user_config.lamf_root}");
assert.equal(manifest.server.mcp_config.env.LAMF_HARNESS, "claude-desktop");
assert.equal(manifest.user_config.lamf_root.type, "directory");
assert.equal(manifest.user_config.lamf_root.required, true);

const wrapper = fs.readFileSync(path.join(extensionRoot, "server", "index.js"), "utf8");
assert(wrapper.includes('stdio: ["pipe", "pipe", "pipe"]'));
assert(wrapper.includes("process.stdin.pipe(child.stdin)"));
assert(wrapper.includes("child.stdout.pipe(process.stdout)"));

for (const forbidden of ["lamf.db", "instance.key", "operator.token", "payload_store"]){
  assert(!JSON.stringify(manifest).includes(forbidden), `manifest includes forbidden authority material: ${forbidden}`);
}

console.log("PASS manifest boundary and launcher configuration");
