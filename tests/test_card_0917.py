"""0.9.17: Karte – Funk-Zuverlässigkeit (gelbes ⚠, Reiter „Funk“, Fenster je Thermostat, Zähler in der Übersicht)."""
import json
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.core import Context
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.helpers.json import JSONEncoder
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm.const import DOMAIN, STUCK_SECONDS

pw = pytest.importorskip("playwright.async_api")

_src = (Path(__file__).parent / "test_card_0913.py").read_text(encoding="utf-8")
_ns: dict = {}
exec(compile(_src[_src.index("CARD = "):_src.index("@pytest.fixture")], "test_card_0913", "exec"), {"Path": Path, "__file__": __file__}, _ns)
CARD, PAGE = _ns["CARD"], _ns["PAGE"]

NACHT = {"wd": [["00:00", "24:00", "nacht"]], "sa": [["00:00", "24:00", "nacht"]], "so": [["00:00", "24:00", "nacht"]]}
ATTRS = {"hvac_modes": ["off", "heat"], "target_temp_step": 0.5, "min_temp": 5, "max_temp": 30, "current_temperature": 19.5, "hvac_action": "idle"}


@pytest.fixture
async def state(hass, enable_custom_integrations, freezer):
    """Wohnzimmer hängt (rot), Esszimmer kam zu spät an (gelb), Küche sofort (ok)."""
    await async_setup_component(hass, "homeassistant", {})

    async def ignore(call):
        return None

    for svc in ("set_temperature", "set_hvac_mode", "set_preset_mode"):
        hass.services.async_register("climate", svc, ignore)
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    areas, reg = ar.async_get(hass), er.async_get(hass)
    names = {"wz": "Wohnzimmer", "ez": "Esszimmer", "ku": "Küche"}
    for oid in names:
        reg.async_get_or_create("climate", "test", oid, suggested_object_id=f"heizung_{oid}")
        hass.states.async_set(f"climate.heizung_{oid}", "heat", {**ATTRS, "temperature": 21})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN]["controller"]
    for oid, n in names.items():
        await ctrl.async_save_room({"name": n, "area_id": areas.async_create(n).id, "climate_entities": [f"climate.heizung_{oid}"], "schedule": NACHT})
    await hass.async_block_till_done()
    await ctrl.async_update(apply=True)
    ctx = next(iter(ctrl._own_contexts))
    hass.states.async_set("climate.heizung_ku", "heat", {**ATTRS, "temperature": 17.0}, context=Context(id=ctx))
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 120))
    hass.states.async_set("climate.heizung_ez", "heat", {**ATTRS, "temperature": 17.0}, context=Context(id=ctx))
    await hass.async_block_till_done()
    await ctrl.async_update(apply=True)
    snap = json.loads(json.dumps(ctrl.snapshot(), cls=JSONEncoder))
    return snap


@pytest.fixture
async def page(tmp_path):
    html = tmp_path / "page.html"
    html.write_text(PAGE.replace("%CARD%", CARD.read_text(encoding="utf-8")), encoding="utf-8")
    async with pw.async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception as err:  # noqa: BLE001
            pytest.skip(f"Chromium nicht verfügbar: {err}")
        pg = await browser.new_page(viewport={"width": 1000, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(f"{e} @ {str(e.stack)[:300]}"))
        await pg.goto(html.as_uri())
        pg.errors = errors
        yield pg
        await browser.close()


def _lv(snap):
    return {r["name"]: r["climates"][0]["radio"]["level"] for r in snap["rooms"]}


async def test_data(state):
    assert _lv(state) == {"Wohnzimmer": "r", "Esszimmer": "y", "Küche": ""}


async def test_heat_list_marks_and_window(state, page):
    await page.evaluate("([s, c]) => addCards(s, c)", [state, [{"view": "heat"}]])
    await page.wait_for_timeout(300)
    rows = await page.evaluate("""() => [...document.getElementById('c0').shadowRoot.querySelectorAll('.room')].map((x) => ({
        name: x.querySelector('.name').textContent.trim().split(' ')[0], radio: !!x.querySelector('.warnmark.radio'), stuck: !!x.querySelector('.warnmark.stuck') }))""")
    by = {x["name"]: x for x in rows}
    assert by["Esszimmer"]["radio"] and not by["Esszimmer"]["stuck"]
    assert by["Wohnzimmer"]["stuck"] and not by["Wohnzimmer"]["radio"]  # rot hat Vorrang
    assert not by["Küche"]["radio"] and not by["Küche"]["stuck"]
    await page.evaluate("() => document.getElementById('c0').shadowRoot.querySelector('.warnmark.radio').click()")
    await page.wait_for_timeout(200)
    dlg = await page.evaluate("() => document.getElementById('c0').shadowRoot.getElementById('fdlg').innerText")
    assert "Auffällig" in dlg and "Befehle rechtzeitig übernommen" in dlg and "0 von 1" in dlg and "Warum gelb?" in dlg
    assert "17 °C erst nach" in dlg.replace("17,0", "17") or "erst nach" in dlg
    open_ = await page.evaluate("() => document.getElementById('c0').shadowRoot.getElementById('fdlg').open")
    assert open_ is True
    await page.evaluate("() => document.getElementById('c0').shadowRoot.querySelector('[data-a=\"rdper\"][data-v=\"7\"]').click()")
    await page.wait_for_timeout(100)
    assert await page.evaluate("() => document.getElementById('c0').shadowRoot.querySelectorAll('.rdday').length") == 7
    await page.evaluate("() => document.getElementById('c0').shadowRoot.querySelector('[data-a=\"rdclose\"]').click()")
    await page.wait_for_timeout(100)
    assert await page.evaluate("() => document.getElementById('c0').shadowRoot.getElementById('fdlg').innerHTML") == ""
    assert page.errors == []


async def test_radio_tab_and_overview_chip(state, page):
    await page.evaluate("([s, c]) => addCards(s, c)", [state, [{}]])
    await page.wait_for_timeout(300)
    chip = await page.evaluate("() => [...document.getElementById('c0').shadowRoot.querySelectorAll('.hcnt')].map((x) => x.textContent).find((t) => t.includes('📶'))")
    assert chip == "📶 1/3"
    await page.evaluate("() => document.getElementById('c0').shadowRoot.querySelector('[data-a=\"tab\"][data-v=\"radio\"]').click()")
    await page.wait_for_timeout(200)
    rows = await page.evaluate("() => [...document.getElementById('c0').shadowRoot.querySelectorAll('.rdt tbody tr')].map((x) => x.innerText.replace(/\\s+/g, ' ').trim())")
    assert "Wohnzimmer" in rows[0] and "Esszimmer" in rows[1] and "Küche" in rows[2]  # rot, gelb, ok
    assert "0/1" in rows[1] and "1/1" in rows[2]
    assert await page.evaluate("() => !document.getElementById('c0').shadowRoot.querySelector('[data-a=\"rdreset\"]')")  # kein Admin
    await page.evaluate("() => document.getElementById('c0').shadowRoot.querySelectorAll('.rdt tbody tr')[2].click()")
    await page.wait_for_timeout(200)
    dlg = await page.evaluate("() => document.getElementById('c0').shadowRoot.getElementById('fdlg').innerText")
    assert "Zuverlässig" in dlg and "1 von 1" in dlg
    # Die Testseite beantwortet „day_states“ (Übersicht rechts) nur mit {} – Fehler daraus gehören zur Testseite.
    assert [e for e in page.errors if "_loadDay" not in e and "_atFromDay" not in e] == []


async def test_phone_width_no_overflow(state, page):
    await page.set_viewport_size({"width": 390, "height": 800})
    await page.evaluate("([s, c]) => addCards(s, c)", [state, [{"view": "radio"}]])
    await page.wait_for_timeout(300)
    await page.evaluate("() => document.getElementById('c0').shadowRoot.querySelectorAll('.rdt tbody tr')[0].click()")
    await page.wait_for_timeout(200)
    w = await page.evaluate("() => { const d = document.getElementById('c0').shadowRoot.querySelector('.rddlg'); return [d.scrollWidth, d.clientWidth]; }")
    assert w[0] <= w[1] + 1
    dlg = await page.evaluate("() => document.getElementById('c0').shadowRoot.getElementById('fdlg').innerText")
    assert "Hängt gerade" in dlg and "übernimmt den Sollwert nicht" in dlg
    assert page.errors == []
