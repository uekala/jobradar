from __future__ import annotations

from pathlib import Path
import re
import shutil

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "index.html"

STUB = r"""
(() => {
  const jobs = {
    cloud: { titel: "Senior Cloud & Infrastructure Engineer", arbeitgeber: "Beispiel AG", ort: "Krefeld", homeoffice: true, quelle: "Karriereseite", url: "https://example.org/cloud", gefunden: "2026-11-04T06:38:00Z", punkte: 93, warum: "VMware und Windows Server passen.", bedenken: "Frist offen.", gehalt: "70.000–78.000 €", status: "neu", notiz: "" },
    platform: { titel: "Senior Platform Engineer", arbeitgeber: "Beispiel GmbH", ort: "Düsseldorf", homeoffice: false, quelle: "Indeed", url: "https://example.org/platform", gefunden: "2026-11-03T08:00:00Z", punkte: 83, warum: "Linux und Container passen.", bedenken: "Noch zu prüfen.", gehalt: "", status: "merken", notiz: "Kontakt aufnehmen" }
  };
  const profile = { ort: "Krefeld", umkreis_km: 50, rollen: "Systemadministrator", faehigkeiten: "VMware, Linux", wuensche: "Homeoffice", gehalt_wunsch: 70000, min_entgeltgruppe: 11, ausschliessen_arbeitgeber: "Stadt Krefeld", homeoffice: true };
  const calls = []; let jobsListener;
  const snapshot = () => ({ docs: Object.entries(jobs).map(([id, data]) => ({ id, data: () => ({ ...data }) })), metadata: { fromCache: false } });
  const db = {
    collection(name) {
      if (name === "jobs") return { onSnapshot(cb) { jobsListener = cb; cb(snapshot()); return () => {}; } };
      if (name === "laeufe") return { orderBy() { return this; }, limit() { return this; }, onSnapshot(cb) { cb({ empty: false, docs: [{ data: () => ({ datum: "2026-11-04T06:38:00Z", neu: 14, quellen: "Indeed, StepStone" }) }] }); return () => {}; } };
    },
    doc(path) {
      if (path === "profil/aktuell") return { onSnapshot(cb) { cb({ exists: true, data: () => ({ ...profile }) }); return () => {}; }, async set(value) { calls.push({ op: "set", path, value }); Object.assign(profile, value); } };
      const id = path.split("/")[1];
      return { async update(value) { calls.push({ op: "update", path, value }); Object.assign(jobs[id], value); jobsListener?.(snapshot()); } };
    }
  };
  window.__jobradarTest = { calls, jobs, profile };
  window.claude = { async use(key) { if (key !== "db") throw new Error("Unbekannter Dienst"); return db; } };
})();
"""


def page_with_stub(browser, width: int = 1280, height: int = 900, dark: bool = False):
    page = browser.new_page(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light")
    content = HTML.read_text(encoding="utf-8")
    content = re.sub(r'<link[^>]+fonts\.googleapis\.com[^>]*>', "", content)
    content = content.replace("<script>", f"<script>{STUB}</script>\n<script>", 1)
    page.set_content(content, wait_until="domcontentloaded")
    page.locator(".job").first.wait_for()
    return page


def main() -> None:
    if not HTML.exists():
        raise SystemExit(f"HTML nicht gefunden: {HTML}")
    with sync_playwright() as p:
        browser_path = shutil.which("chromium") or shutil.which("chromium-browser")
        browser = p.chromium.launch(headless=True, executable_path=browser_path, args=["--no-sandbox"] if browser_path else [])
        try:
            page = page_with_stub(browser)
            assert page.locator(".job").count() == 1
            page.locator('[data-filter="alle"]').click()
            assert page.locator(".job").count() == 2
            card = page.locator(".job").filter(has_text="Senior Cloud")
            score = card.locator(".score").bounding_box()
            body = card.locator(".job-content").bounding_box()
            assert score and body and body["x"] >= score["x"] + score["width"]
            card.get_by_role("button", name="Beworben", exact=False).click()
            page.wait_for_function("window.__jobradarTest.calls.some(c => c.op === 'update' && c.value.status === 'beworben')")
            card = page.locator(".job").filter(has_text="Senior Cloud")
            note = card.locator("textarea.notiz")
            note.fill("Bewerbung am 04.11.")
            note.evaluate("el => el.blur()")
            page.wait_for_function("window.__jobradarTest.calls.some(c => c.op === 'update' && c.value.notiz === 'Bewerbung am 04.11.')")
            page.locator("#profile summary").click()
            page.locator("#p-gehalt").fill("72000")
            page.get_by_role("button", name="Profil speichern").click()
            page.wait_for_function("window.__jobradarTest.calls.some(c => c.op === 'set' && c.path === 'profil/aktuell' && c.value.gehalt_wunsch === 72000)")
            print("PASS: Datenbank-Laden, Filter, Kartenlayout, Status, Notiz und Suchprofil")
            page.close()

            mobile = page_with_stub(browser, 390, 844, True)
            dims = mobile.evaluate("({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth })")
            assert dims["scroll"] <= dims["width"], dims
            mobile.locator('[data-filter="alle"]').click()
            assert mobile.locator(".job").count() == 2
            print("PASS: 390-px-Mobile-Ansicht und Dark Mode ohne horizontalen Überlauf")
            mobile.close()

            local = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            local.on("pageerror", lambda error: errors.append(str(error)))
            local.set_content(HTML.read_text(encoding="utf-8"), wait_until="domcontentloaded")
            local.locator("#alert").wait_for(state="visible")
            assert "Claude" in local.locator("#alert").inner_text()
            assert not errors, errors
            print("PASS: Lokaler Modus ohne Claude und ohne JavaScript-Laufzeitfehler")
            local.close()

            failing = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            failing.on("pageerror", lambda error: errors.append(str(error)))
            content = HTML.read_text(encoding="utf-8")
            failing_stub = '<script>window.claude = { use: async () => { throw new Error("DB Testfehler") } };</script>\\n<script>'
            content = content.replace("<script>", failing_stub, 1)
            failing.set_content(content, wait_until="domcontentloaded")
            failing.locator("#alert").wait_for(state="visible")
            assert "DB Testfehler" in failing.locator("#alert").inner_text()
            assert not errors, errors
            print("PASS: Datenbank-Initialisierungsfehler wird abgefangen")
            failing.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
