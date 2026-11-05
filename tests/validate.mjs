import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Script } from "node:vm";
import test from "node:test";

const html = readFileSync(new URL("../uebersichtsseite.html", import.meta.url), "utf8");
const scriptStart = html.indexOf("<script>");
const scriptEnd = html.indexOf("</script>", scriptStart);
const script = scriptStart >= 0 && scriptEnd > scriptStart
  ? html.slice(scriptStart + "<script>".length, scriptEnd)
  : "";

test("dashboard document has a valid HTML shell and one application script", () => {
  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /<html lang="de">/i);
  assert.ok(script, "Expected one embedded application script");
  assert.equal(html.split("<script>").length - 1, 1);
});

test("embedded dashboard JavaScript parses", () => {
  assert.doesNotThrow(() => new Script(script, { filename: "uebersichtsseite.html" }));
});

test("dashboard keeps the Claude database contract", () => {
  for (const contract of [
    'claude.use("db")',
    'db.collection("jobs")',
    'db.collection("laeufe")',
    'db.doc("profil/aktuell")',
  ]) {
    assert.ok(script.includes(contract), `Missing database contract: ${contract}`);
  }
  for (const status of ["neu", "merken", "beworben", "absage", "verworfen"]) {
    assert.ok(script.includes(status), `Missing status: ${status}`);
  }
});

test("external job links are restricted to HTTP or HTTPS", () => {
  assert.ok(script.includes('url.protocol === "https:" || url.protocol === "http:"'));
  assert.ok(script.includes('rel: "noopener"'));
});
