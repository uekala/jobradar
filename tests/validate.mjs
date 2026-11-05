import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Script } from "node:vm";
import test from "node:test";

const html = readFileSync(new URL("../uebersichtsseite.html", import.meta.url), "utf8");
const scripts = [...html.matchAll(/<script\\b[^>]*>([\\s\\S]*?)<\\/script>/gi)];

test("dashboard document has a valid HTML shell and one application script", () => {
  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /<html lang="de">/i);
  assert.equal(scripts.length, 1, "Expected exactly one embedded application script");
});

test("embedded dashboard JavaScript parses", () => {
  assert.doesNotThrow(() => new Script(scripts[0][1], { filename: "uebersichtsseite.html" }));
});

test("dashboard keeps the Claude database contract", () => {
  const script = scripts[0][1];
  assert.match(script, /claude\\.use\\(["']db["']\\)/);
  assert.match(script, /collection\\(["']jobs["']\\)/);
  assert.match(script, /collection\\(["']laeufe["']\\)/);
  assert.match(script, /doc\\(["']profil\\/aktuell["']\\)/);
  for (const status of ["neu", "merken", "beworben", "absage", "verworfen"]) {
    assert.ok(script.includes(status), `Missing status: ${status}`);
  }
});

test("external job links are restricted to HTTP or HTTPS", () => {
  assert.match(scripts[0][1], /url\\.protocol === ["']https:["'] \\|\\| url\\.protocol === ["']http:["']/);
  assert.match(scripts[0][1], /rel: ["']noopener["']/);
});
