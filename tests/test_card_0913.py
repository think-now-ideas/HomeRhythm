"""0.9.13: Karte – `area:`-Auflösung, `layout: knopf`, gemeinsamer Speicher, Bedien-Fenster als <dialog>.

Läuft die Karte in Chromium (Playwright) mit einem nachgebauten `hass` – Daten kommen aus einer echten
Home-Rhythm-Instanz (``ctrl.snapshot()``). Ohne Playwright werden die Tests übersprungen.
"""
import json
from pathlib import Path

import pytest
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.helpers.json import JSONEncoder
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm.const import DOMAIN

pw = pytest.importorskip("playwright.async_api")

CARD = Path(__file__).parent.parent / "custom_components" / "home_rhythm" / "www" / "home-rhythm-card.js"
SCHED = {"wd": [["00:00", "24:00", "komfort"]], "sa": [["00:00", "24:00", "komfort"]], "so": [["00:00", "24:00", "komfort"]]}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html { --primary-color:#03a9f4; --card-background-color:#fff; --primary-text-color:#212121; --secondary-text-color:#727272; --divider-color:#e0e0e0; }
body { margin:0; }
.hdr { position:fixed; top:0; left:0; right:0; height:56px; background:#03a9f4; z-index:100; }
.section { margin-top:64px; transform:translateZ(0); overflow:hidden; display:grid; grid-template-columns:repeat(12,1fr); grid-auto-rows:56px; gap:8px; width:520px; }
.section > * { grid-column: span 6; }
</style><script>customElements.define("ha-icon", class extends HTMLElement {});</script>
<script>%CARD%</script></head><body><div class="hdr"></div><div class="section" id="sec"></div>
<script>
window.CALLS = {}; window.SUBS = 0; window.NAV = [];
history.pushState = (st, t, url) => { window.LAST_URL = url; };  // file:// erlaubt keinen Pfadwechsel
window.addEventListener("location-changed", () => NAV.push(window.LAST_URL));
window.makeHass = (state) => ({ user: { is_admin: false }, states: {}, callService: async () => {},
  connection: {
    sendMessagePromise: async (m) => { CALLS[m.type] = (CALLS[m.type] || 0) + 1; return m.type === "home_rhythm/state" ? JSON.parse(JSON.stringify(state)) : {}; },
    subscribeMessage: async (cb) => { SUBS++; window.PUSH = cb; return () => { SUBS--; }; },
    subscribeEvents: async () => () => {} } });
window.addCards = (state, cfgs) => { const hass = window.HASS || (window.HASS = makeHass(state)); const sec = document.getElementById("sec");
  cfgs.forEach((c, i) => { const el = document.createElement("home-rhythm-card"); el.setConfig(c); el.id = "c" + sec.children.length; sec.appendChild(el); el.hass = hass; }); };
window.txt = (id) => document.getElementById(id).shadowRoot.getElementById("main").innerText.replace(/\\s+/g, " ").trim();
</script></body></html>"""


@pytest.fixture
async def state(hass, enable_custom_integrations):
    await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    areas = ar.async_get(hass)
    kueche, bad, keller = areas.async_create("Küche"), areas.async_create("Bad"), areas.async_create("Keller")
    reg = er.async_get(hass)
    for oid in ("kueche", "bad", "bad2", "bad3"):
        reg.async_get_or_create("climate", "test", oid, suggested_object_id=f"heizung_{oid}")
    hass.states.async_set("climate.heizung_kueche", "heat", {"temperature": 21, "current_temperature": 19.4, "hvac_action": "heating"})
    hass.states.async_set("climate.heizung_bad", "heat", {"temperature": 21, "current_temperature": 22.5, "hvac_action": "idle"})
    hass.states.async_set("climate.heizung_bad2", "unavailable", {})
    hass.states.async_set("climate.heizung_bad3", "heat", {"temperature": 21, "current_temperature": 20})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN]["controller"]
    await ctrl.async_save_room({"name": "Küche", "area_id": kueche.id, "climate_entities": ["climate.heizung_kueche"], "schedule": SCHED})
    await ctrl.async_save_room({"name": "Bad", "area_id": bad.id, "climate_entities": ["climate.heizung_bad", "climate.heizung_bad2"], "schedule": SCHED})
    await ctrl.async_save_room({"name": "Bad 2", "area_id": bad.id, "climate_entities": ["climate.heizung_bad3"], "schedule": SCHED})
    await hass.async_block_till_done()
    snap = json.loads(json.dumps(ctrl.snapshot(), cls=JSONEncoder))
    return snap, {"kueche": kueche.id, "bad": bad.id, "keller": keller.id}


@pytest.fixture
async def page(tmp_path):
    html = tmp_path / "page.html"
    html.write_text(PAGE.replace("%CARD%", CARD.read_text(encoding="utf-8")), encoding="utf-8")
    async with pw.async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception as err:  # noqa: BLE001 – Browser nicht installiert
            pytest.skip(f"Chromium nicht verfügbar: {err}")
        pg = await browser.new_page(viewport={"width": 1000, "height": 700})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        await pg.goto(html.as_uri())
        pg.errors = errors
        yield pg
        await browser.close()


async def test_area_resolution(state, page):
    snap, a = state
    rooms = {r["area_id"]: r for r in reversed(snap["rooms"])}  # bei mehreren: der erste
    await page.evaluate("([s, c]) => addCards(s, c)", [snap, [
        {"area": a["kueche"], "layout": "knopf"},
        {"area": a["bad"], "layout": "knopf"},                       # zwei Räume im Bereich → der erste („Bad“)
        {"area": a["keller"], "layout": "knopf"},                    # kein Raum
        {"room": rooms[a["kueche"]]["id"], "area": a["bad"], "layout": "knopf"},  # room hat Vorrang
        {"area": a["keller"]},                                       # Standard-Form ohne Raum: auch nur die kleine Zeile
    ]])
    await page.wait_for_timeout(200)
    texts = [await page.evaluate("(id) => txt(id)", f"c{i}") for i in range(5)]
    assert texts[0].startswith("Küche") or "Küche" in texts[0]
    assert "Bad" in texts[1] and "Bad 2" not in texts[1]
    assert texts[2] == "kein Home-Rhythm-Raum"
    assert "Küche" in texts[3]
    assert texts[4] == "kein Home-Rhythm-Raum"
    assert not await page.evaluate("() => !!document.getElementById('c2').shadowRoot.querySelector('.empty')")  # kein großer Fehlerkasten
    assert page.errors == []


async def test_knopf_render_and_grid(state, page):
    snap, a = state
    await page.evaluate("([s, c]) => addCards(s, c)", [snap, [
        {"area": a["kueche"], "layout": "knopf", "navigation_path": "/mein-dashboard/kueche"},
        {"area": a["bad"], "layout": "knopf", "name": "Badezimmer", "icon": "mdi:shower"},
        {"area": a["kueche"]},
    ]])
    await page.wait_for_timeout(200)
    k = await page.evaluate("() => { const r = document.getElementById('c0').shadowRoot; return { name: r.querySelector('.kn1').textContent, line: r.querySelector('.kline').textContent, cls: r.querySelector('.kn').className, ico: r.querySelector('button.kico').dataset.a }; }")
    assert k["name"] == "Küche" and k["ico"] == "ctl"
    assert "19,4" in k["line"] and "21" in k["line"]  # Ist · Soll
    assert "k-heat" in k["cls"]
    b = await page.evaluate("() => { const r = document.getElementById('c1').shadowRoot; return { name: r.querySelector('.kn1').textContent, line: r.querySelector('.kline').textContent, warn: !!r.querySelector('.kname .warnmark'), icon: r.querySelector('.kico ha-icon').getAttribute('icon'), cls: r.querySelector('.kn').className }; }")
    assert b["name"] == "Badezimmer" and b["icon"] == "mdi:shower"
    assert b["warn"] and "k-unavail" in b["cls"]
    assert "22,5" in b["line"] and "Nicht verfügbar" not in b["line"]  # trotzdem Ist/Soll
    grid = await page.evaluate("() => [document.getElementById('c0').getGridOptions(), document.getElementById('c2').getGridOptions(), document.getElementById('c0').getCardSize()]")
    assert grid[0] == {"columns": 6, "rows": 1, "min_columns": 3, "min_rows": 1, "max_rows": 1}
    assert grid[1] == {"columns": 12, "min_columns": 6} and grid[2] == 1
    assert page.errors == []


async def test_knopf_clicks_and_dialog_on_top(state, page):
    snap, a = state
    await page.evaluate("([s, c]) => addCards(s, c)", [snap, [
        {"area": a["kueche"], "layout": "knopf", "navigation_path": "/mein-dashboard/kueche"},
        {"area": a["bad"], "layout": "knopf"},
    ]])
    await page.wait_for_timeout(200)
    await page.click("#c0 >> .ktx")
    assert await page.evaluate("() => NAV") == ["/mein-dashboard/kueche"]
    await page.click("#c0 >> button.kico")
    await page.wait_for_timeout(100)
    d = await page.evaluate("""() => { const dl = document.getElementById('c0').shadowRoot.getElementById('qdlg');
        const b = dl.querySelector('.dlg').getBoundingClientRect();
        return { modal: dl.matches(':modal'), w: b.width, top: document.elementFromPoint(b.left + 20, b.top + 10).tagName }; }""")
    assert d["modal"] and d["w"] > 300 and d["top"] == "HOME-RHYTHM-CARD"  # über der Kopfleiste (z-index 100) und nicht abgeschnitten
    await page.keyboard.press("Escape")
    assert not await page.evaluate("() => document.getElementById('c0').shadowRoot.getElementById('qdlg').open")
    await page.click("#c1 >> .ktx")  # ohne navigation_path → Bedien-Fenster
    await page.wait_for_timeout(100)
    assert await page.evaluate("() => document.getElementById('c1').shadowRoot.getElementById('qdlg').open")
    assert page.errors == []


async def test_shared_store(state, page):
    snap, a = state
    await page.evaluate("([s, c]) => addCards(s, c)", [snap, [{"area": a["kueche"], "layout": "knopf"}] * 12])
    await page.wait_for_timeout(200)
    assert await page.evaluate("() => [CALLS['home_rhythm/state'], SUBS]") == [1, 1]
    await page.evaluate("() => { for (const c of document.querySelectorAll('home-rhythm-card')) c.hass = HASS; PUSH(); PUSH(); PUSH(); }")
    await page.wait_for_timeout(500)
    assert await page.evaluate("() => CALLS['home_rhythm/state']") == 2  # drei Meldungen = eine Abfrage für alle
    await page.evaluate("() => document.getElementById('sec').replaceChildren()")
    await page.wait_for_timeout(5300)
    assert await page.evaluate("() => SUBS") == 0
    assert page.errors == []
