// The web tests' fixtures (ruling R17): the public cut of the four saved real runs, committed, so every lane's node test pins its
// values on the same files on any clone. Written by scripts/web_fixtures.py; frozen (refresh only with the tests that pin them).
//   import { load, NAMES } from "./web_fixtures.mjs";   const robert = load("robert");
import { readFileSync } from "node:fs";

export const NAMES = ["robert", "mateo", "amira", "canadian"];

const cache = new Map();

export function load(name) {
  if (!NAMES.includes(name)) throw new Error(`no web fixture named ${name} (one of ${NAMES.join(", ")})`);
  if (!cache.has(name)) cache.set(name, readFileSync(new URL(`./fixtures/web/${name}.json`, import.meta.url), "utf8"));
  return JSON.parse(cache.get(name));          // a fresh copy each time: a test may change its Result freely
}
