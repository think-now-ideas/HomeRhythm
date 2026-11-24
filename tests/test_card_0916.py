"""0.9.16: Karte – rotes ⚠ „übernimmt den Sollwert nicht“, Raumsymbol zeigt bei Hand-Änderung den Heizzustand."""
import json
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.helpers.json import JSONEncoder
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm.const import DOMAIN, STUCK_SECONDS


pw = pytest.importorskip("playwright.async_api")

# Testseite und Karte wie in test_card_0913 (ohne Paket-Import, tests/ ist kein Paket)
_src = (Path(__file__).parent / "test_card_0913.py").read_text(encoding="utf-8")
_ns: dict = {}
exec(compile(_src[_src.index("CARD = "):_src.index("@pytest.fixture")], "test_card_0913", "exec"), {"Path": Path, "__file__": __file__}, _ns)
CARD, PAGE = _ns["CARD"], _ns["PAGE"]

NACHT = {"wd": [["00:00", "24:00", "nacht"]], "sa": [["00:00", "24:00", "nacht"]], "so": [["00:00", "24:00", "nacht"]]}
ATTRS = {"hvac_modes": ["off", "heat"], "target_temp_step": 0.5, "min_temp": 5, "max_temp": 30}


@pytest.fixture
async def state(hass, enable_custom_integrations, freezer):
    await async_setup_component(hass, "homeassistant", {})

    async def ignore(call):  # Gerät reagiert nicht
        return None

    for svc in ("set_temperature", "set_hvac_mode", "set_preset_mode"):
        hass.services.async_register("climate", svc, ignore)
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    areas = ar.async_get(hass)
    wz, ez = areas.async_create("Wohnzimmer"), areas.async_create("Esszimmer")
    reg = er.async_get(hass)
    for oid in ("wz", "ez"):
        reg.async_get_or_create("climate", "test", oid, suggested_object_id=f"heizung_{oid}")
    hass.states.async_set("climate.heizung_wz", "heat", {**ATTRS, "temperature": 21, "current_temperature": 20.7, "hvac_action": "heating"})
    hass.states.async_set("climate.heizung_ez", "heat", {**ATTRS, "temperature": 17, "current_temperature": 19.0, "hvac_action": "idle"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN]["controller"]
    await ctrl.async_save_room({"name": "Wohnzimmer", "area_id": wz.id, "climate_entities": ["climate.heizung_wz"], "schedule": NACHT})
    await ctrl.async_save_room({"name": "Esszimmer", "area_id": ez.id, "climate_entities": ["climate.heizung_ez"], "schedule": NACHT})
    await hass.async_block_till_done()
    await ctrl.async_update(apply=True)
    ids = {r["name"]: r["id"] for r in ctrl.snapshot()["rooms"]}
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 60))
    # Esszimmer: Hand-Änderung am Gerät (nach der Karenzzeit), Ventil heizt
    hass.states.async_set("climate.heizung_ez", "heat", {**ATTRS, "temperature": 22, "current_temperature": 19.0, "hvac_action": "heating"})
    await hass.async_block_till_done()
    await ctrl.async_update(apply=True)
    snap = json.loads(json.dumps(ctrl.snapshot(), cls=JSONEncoder))
    return snap, ids


@pytest.fixture
async def page(tmp_path):
    html = tmp_path / "page.html"
    html.write_text(PAGE.replace("%CARD%", CARD.read_text(encoding="utf-8")), encoding="utf-8")
    async with pw.async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception as err:  # noqa: BLE001 – Browser nicht installiert
            pytest.skip(f"Chromium nicht verfügbar: {err}")
        pg = await browser.new_page(viewport={"width": 1000, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        await pg.goto(html.as_uri())
        pg.errors = errors
        yield pg
        await browser.close()


async def test_data(state):
    snap, ids = state
    rooms = {r["name"]: r for r in snap["rooms"]}
    assert rooms["Wohnzimmer"]["climates"][0]["not_taken"]["want_temp"] == 17.0
    assert rooms["Esszimmer"]["manual"] is not None and rooms["Esszimmer"]["climates"][0]["not_taken"] is None


async def test_heat_list_red_mark_and_detail(state, page):
    snap, ids = state
    await page.evaluate("([s, c]) => addCards(s, c)", [snap, [{"view": "heat"}]])
    await page.wait_for_timeout(300)
    r = await page.evaluate("""() => { const root = document.getElementById('c0').shadowRoot;
        const rows = [...root.querySelectorAll('.room')].map((x) => ({ name: x.querySelector('.name').textContent,
          ico: x.querySelector('.ico').textContent.trim(), stuck: !!x.querySelector('.warnmark.stuck') }));
        return rows; }""")
    by = {x["name"].split(" ")[0].strip(): x for x in r}
    assert by["Wohnzimmer"]["stuck"] is True
    assert by["Esszimmer"]["stuck"] is False
    assert by["Esszimmer"]["ico"] == "🔥"  # Variante A: Hand-Änderung verdeckt das Heizen nicht mehr
    color = await page.evaluate("() => getComputedStyle(document.getElementById('c0').shadowRoot.querySelector('.warnmark.stuck')).color")
    assert color != "rgb(255, 152, 0)"  # nicht das orange ⚠
    # antippen klappt den Raum auf (das ⚠ liegt in der Zeile; die Zeile öffnet den Raum)
    await page.evaluate("() => document.getElementById('c0').shadowRoot.querySelector('.warnmark.stuck').click()")
    await page.wait_for_timeout(200)
    box = await page.evaluate("() => (document.getElementById('c0').shadowRoot.querySelector('.stuckbox') || {}).textContent || ''")
    assert "übernimmt den Sollwert nicht" in box and "Gesendet: 17" in box and "21" in box
    assert page.errors == []


async def test_room_card_and_knopf(state, page):
    snap, ids = state
    await page.evaluate("([s, c]) => addCards(s, c)", [snap, [{"room": ids["Wohnzimmer"]}, {"room": ids["Wohnzimmer"], "layout": "knopf"},
                                                             {"room": ids["Esszimmer"], "layout": "knopf"}]])
    await page.wait_for_timeout(300)
    res = await page.evaluate("""() => [0, 1, 2].map((i) => { const r = document.getElementById('c' + i).shadowRoot;
        return { stuck: !!r.querySelector('.warnmark.stuck'), kn: (r.querySelector('.kn') || {}).className || '' }; })""")
    assert res[0]["stuck"] and res[1]["stuck"] and not res[2]["stuck"]
    assert "k-heat" in res[2]["kn"]  # Raumknopf Esszimmer: heizt, obwohl Hand-Änderung
    assert page.errors == []
