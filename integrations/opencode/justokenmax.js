/**
 * jusTokenMax — OpenCode plugin.
 *
 * Transparently compresses heavy file reads the way the Claude Code hook does:
 * when OpenCode is about to `read` a PDF / log / JSON / notebook / CSV / diff,
 * this rewrites the path to jusTokenMax's cheap artifact, so the model gets the
 * Markdown / digest instead of the raw file — at a fraction of the tokens.
 *
 * Install:
 *   - project:  copy to  .opencode/plugins/justokenmax.js
 *   - global:   copy to  ~/.config/opencode/plugins/justokenmax.js
 *
 * Requires the `justokenmax` CLI on PATH (`pip install justokenmax`); it falls
 * back to `npx -y @kalmantic/justokenmax` (which itself bootstraps Python via uv
 * if needed). It NEVER blocks a read — any problem leaves the original read
 * untouched (fail open).
 *
 * For the full tool set (query/outline/diff/etc.) also register the MCP server:
 *   justokenmax install opencode
 */

const HEAVY = /\.(pdf|log|json|ndjson|ipynb|csv|tsv|diff|patch)$/i;
const ARG_KEYS = ["filePath", "path", "file"];

export const justokenmax = async ({ $ }) => {
  async function optimize(filePath) {
    for (const launcher of [["justokenmax"], ["npx", "-y", "@kalmantic/justokenmax"]]) {
      try {
        const out = await $`${launcher} optimize --json ${filePath}`.quiet().text();
        const r = JSON.parse(out);
        if (r && r.ok && r.output) return r.output;
        return null; // ran fine but nothing to optimize (e.g. unsupported/small)
      } catch {
        // launcher missing or failed — try the next one, else give up
      }
    }
    return null;
  }

  return {
    "tool.execute.before": async (input, output) => {
      try {
        if (input.tool !== "read") return;
        const args = (output && output.args) || {};
        const key = ARG_KEYS.find((k) => typeof args[k] === "string");
        if (!key || !HEAVY.test(args[key])) return;
        const cheap = await optimize(args[key]);
        if (cheap) args[key] = cheap;
      } catch {
        // fail open: never block a read
      }
    },
  };
};
