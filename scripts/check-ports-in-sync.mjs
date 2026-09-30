#!/usr/bin/env node
/**
 * Port-sync guard. Fails (exit 1) if the backend and frontend disagree on the
 * dev ports / origins declared in their .env.example files.
 *
 * Copy into each repo as scripts/check-ports-in-sync.mjs and run in CI.
 * Usage: node check-ports-in-sync.mjs <backend/.env.example> <frontend/.env.example>
 */
import { readFileSync } from "node:fs";

const [beFile, feFile] = process.argv.slice(2);
if (!beFile || !feFile) {
  console.error("usage: check-ports-in-sync.mjs <backend .env.example> <frontend .env.example>");
  process.exit(2);
}

const parse = (p) =>
  Object.fromEntries(
    readFileSync(p, "utf8")
      .split(/\r?\n/)
      .filter((l) => l && !l.trimStart().startsWith("#") && l.includes("="))
      .map((l) => {
        const i = l.indexOf("=");
        return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
      })
  );

const be = parse(beFile);
const fe = parse(feFile);

const bePort = be.PORT;                                   // e.g. 8000
const feApi = fe.VITE_API_BASE || "";                     // e.g. http://localhost:8000
let feApiUrl;
try {
  feApiUrl = new URL(feApi);
} catch {
  feApiUrl = null;
}
const feApiPort = feApiUrl?.port || (feApiUrl?.protocol === "https:" ? "443" : "80");
const corsOrigins = (be.CORS_ORIGINS || "").split(",").map((s) => s.trim());

const errors = [];
if (!bePort) errors.push("backend PORT missing");
if (!feApi) errors.push("frontend VITE_API_BASE missing");
if (feApi && !feApiUrl) errors.push("frontend VITE_API_BASE must be a complete URL");
if (bePort && feApiPort && bePort !== feApiPort)
  errors.push(`port mismatch: backend PORT=${bePort} but frontend targets :${feApiPort}`);
if (!corsOrigins.includes("*") && !corsOrigins.includes("http://localhost:5173"))
  errors.push("backend CORS_ORIGINS must include the frontend dev origin http://localhost:5173");

if (errors.length) {
  console.error("✗ ports out of sync:\n  - " + errors.join("\n  - "));
  process.exit(1);
}
console.log(`✓ ports in sync — backend :${bePort} ⇄ frontend VITE_API_BASE ${feApi}, CORS ok`);
