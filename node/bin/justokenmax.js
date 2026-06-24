#!/usr/bin/env node
/**
 * Thin Node wrapper over the jusTokenMax Python core — designed so a Claude Code
 * (or any) user who has Node but NOT Python still works out of the box.
 *
 * It does no PDF/image work itself; it forwards all arguments to the Python CLI
 * and resolves a runtime in this order:
 *   1. Repo checkout  — sibling `python/` dir (dev), run with `python3`.
 *   2. Installed pkg  — `python3 -m justokenmax` when the module is importable.
 *   3. No Python      — auto-provision via uv: `uvx justokenmax …` (uv fetches an
 *                       ephemeral Python + the published package; nothing to
 *                       pre-install). Tries to bootstrap uv if missing.
 *
 * Examples:
 *   npx -y @kalmantic/justokenmax mcp        # run the MCP server (stdio)
 *   npx -y @kalmantic/justokenmax optimize x.pdf
 */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const REPO_PY_DIR = path.resolve(__dirname, "..", "..", "python");
const PKG = "justokenmax";
const args = process.argv.slice(2);

function ok(cmd, probeArgs) {
  const r = spawnSync(cmd, probeArgs, { stdio: "ignore" });
  return !r.error && r.status === 0;
}

function findPython() {
  for (const cmd of ["python3", "python"]) {
    if (ok(cmd, ["--version"])) return cmd;
  }
  return null;
}

function run(cmd, cmdArgs, env) {
  const res = spawnSync(cmd, cmdArgs, { stdio: "inherit", env: env || process.env });
  if (res.error) {
    console.error(`justokenmax: failed to run ${cmd}: ${res.error.message}`);
    process.exit(1);
  }
  process.exit(res.status === null ? 1 : res.status);
}

function tryPython() {
  const python = findPython();
  if (!python) return false;

  const env = { ...process.env };
  const repoPkg = path.join(REPO_PY_DIR, PKG);
  if (fs.existsSync(repoPkg)) {
    // Dev checkout: make the local package importable, then it's always present.
    env.PYTHONPATH = env.PYTHONPATH
      ? `${REPO_PY_DIR}${path.delimiter}${env.PYTHONPATH}`
      : REPO_PY_DIR;
    run(python, ["-m", PKG, ...args], env);
  }
  // Installed: only use it if the module actually imports.
  if (ok(python, ["-c", "import justokenmax"])) {
    run(python, ["-m", PKG, ...args], env);
  }
  return false; // python exists but package not installed — fall through to uv
}

function tryUv() {
  // uvx == `uv tool run`: fetches an ephemeral Python + the PyPI package.
  if (ok("uvx", ["--version"])) run("uvx", [PKG, ...args]);
  if (ok("uv", ["--version"])) run("uv", ["tool", "run", PKG, ...args]);
  return false;
}

function bootstrapUv() {
  // Best-effort: install uv via its official installer if a shell is available.
  const isWin = process.platform === "win32";
  const installer = isWin
    ? ["powershell", ["-NoProfile", "-Command",
        "irm https://astral.sh/uv/install.ps1 | iex"]]
    : ["sh", ["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]];
  console.error("justokenmax: no Python found — provisioning via uv …");
  const r = spawnSync(installer[0], installer[1], { stdio: "inherit" });
  return !r.error && r.status === 0;
}

function main() {
  if (tryPython()) return;
  if (tryUv()) return;
  if (bootstrapUv()) {
    // uv installs to ~/.local/bin (unix) / %USERPROFILE%\.local\bin (win); add it.
    const home = process.env.HOME || process.env.USERPROFILE || "";
    process.env.PATH =
      `${path.join(home, ".local", "bin")}${path.delimiter}${process.env.PATH}`;
    if (tryUv()) return;
  }
  console.error(
    "justokenmax: could not find or provision a runtime.\n" +
      "  Install Python 3.9+ (`pip install justokenmax`), or install uv\n" +
      "  (https://astral.sh/uv) and re-run."
  );
  process.exit(127);
}

main();
