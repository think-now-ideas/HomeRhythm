"""0.9.15: „frühestens“ und „spätestens“ an jeder Sonnenzeit im einfachen Zeitplan, Jahresband, Hinweis „Art passt nicht“."""
from datetime import date
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm import flows as F
from custom_components.home_rhythm import roomtemp as RT
from custom_components.home_rhythm.const import DOMAIN

SCHED = {"wd": [["00:00", "24:00", "komfort"]], "sa": [["00:00", "24:00", "komfort"]], "so": [["00:00", "24:00", "komfort"]]}


def cover_plan(close):
    simple = {"rows": {"mf": {"like": "own", "open": {"ref": "sunrise", "offset": 30, "earliest": "06:45", "latest": "08:00"}},
                       "sa": {"like": "mf"}, "so": {"like": "mf"}},
              "close": close, "guard": "23:00"}
    return F.normalize_plan({"kind": "cover", "name": "Rollläden", "devices": ["cover.a"], "mode": "simple", "simple": simple,
                             "conds": {"op": "and", "items": []}})


# ------------------------------------------------------------------ Ausführung (unverändert seit 0.9.0, jetzt abgesichert)
def test_close_both_limits_kept_and_applied():
    p = cover_plan({"ref": "sunset", "offset": 60, "unit": "h", "earliest": "18:00", "latest": "23:00"})
    assert p["simple"]["close"] == {"ref": "sunset", "offset": 60, "unit": "h", "earliest": "18:00", "latest": "23:00"}
    close = next(x for x in p["points"] if x["action"] == "close" and not x.get("guard"))
    assert close["earliest"] == "18:00" and close["latest"] == "23:00"
    winter, mid, summer = F.Sun(495, 975), F.Sun(400, 1200), F.Sun(300, 1330)  # Sonnenuntergang 16:15 / 20:00 / 22:10
    assert F.hm(F.point_minute(close, winter)) == "18:00"   # 17:15 → nicht vor 18:00: schließt um 18:00, nicht gar nicht
    assert F.hm(F.point_minute(close, mid)) == "21:00"      # dazwischen: Sonne + 1 Std.
    assert F.hm(F.point_minute(close, summer)) == "23:00"   # 23:10 → spätestens 23:00


def test_open_both_limits():
    p = cover_plan({"ref": "time", "time": "22:00"})
    op = next(x for x in p["points"] if x["action"] == "open")
    assert F.hm(F.point_minute(op, F.Sun(495, 975))) == "08:00"  # 08:45 → spätestens 08:00
    assert F.hm(F.point_minute(op, F.Sun(300, 1330))) == "06:45"  # 05:30 → frühestens 06:45


def test_limits_wrong_order():
    with pytest.raises(ValueError, match="frühestens"):
        cover_plan({"ref": "sunset", "offset": 0, "earliest": "23:00", "latest": "18:00"})


def test_guard_needs_latest():
    with_latest = cover_plan({"ref": "sunset", "offset": 60, "earliest": "18:00", "latest": "23:00"})
    without = cover_plan({"ref": "sunset", "offset": 60, "earliest": "18:00"})
    assert any(x.get("guard") for x in with_latest["points"])
    assert not any(x.get("guard") for x in without["points"])  # ohne „spätestens“ kann es später werden


# ------------------------------------------------------------------ Hinweis „Art passt nicht“
@pytest.mark.parametrize("kind,plats,want", [
    ("fritz", ["zha"], "direct"),                      # FRITZ!DECT gegen Zigbee getauscht
    ("fritz", ["mqtt", None], "direct"),
    ("bt", ["mqtt"], "direct"),
    ("direct", ["fritzbox"], "fritz"),
    ("integration", ["fritzbox", "fritzbox"], "fritz"),
    ("direct", ["better_thermostat"], "bt"),
    ("fritz", ["versatile_thermostat"], "integration"),
    ("fritz", ["fritzbox"], None),
    ("direct", ["zha"], None),
    ("integration", ["generic_thermostat"], None),     # andere Regel-Integration: nicht beanstanden
    ("fritz", ["fritzbox", "zha"], None),              # gemischt: nicht raten
    ("fritz", [None], None),                           # unbekannt: schweigen
    ("fritz", [], None),
])
def test_kind_mismatch(kind, plats, want):
    assert RT.kind_mismatch(kind, plats) == want


@pytest.fixture
async def ctrl(hass, enable_custom_integrations):
    await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create("climate", "zha", "trv1", suggested_object_id="heizung_bad")
    hass.states.async_set("climate.heizung_bad", "heat", {"temperature": 21, "current_temperature": 20})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN]["controller"]


async def test_kind_hint_and_switch(hass, ctrl, hass_ws_client):
    rid = await ctrl.async_save_room({"name": "Bad", "climate_entities": ["climate.heizung_bad"], "schedule": SCHED,
                                      "kind": "fritz", "temp_source": "device"})
    room = next(r for r in ctrl.snapshot()["rooms"] if r["id"] == rid)
    assert room["kind_hint"] == {"id": f"kind:{rid}:fritz:direct", "kind": "fritz", "suggest": "direct"}
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "home_rhythm/room/kind", "room_id": rid, "kind": "direct"})
    assert (await client.receive_json())["success"]
    assert ctrl.rooms[rid]["kind"] == "direct"
    assert next(r for r in ctrl.snapshot()["rooms"] if r["id"] == rid)["kind_hint"] is None
    await client.send_json({"id": 2, "type": "home_rhythm/room/kind", "room_id": rid, "kind": "quatsch"})
    assert not (await client.receive_json())["success"]


async def test_kind_hint_dismiss_and_reset(hass, ctrl):
    rid = await ctrl.async_save_room({"name": "Bad", "climate_entities": ["climate.heizung_bad"], "schedule": SCHED, "kind": "fritz"})
    await ctrl.async_dismiss_hint(f"kind:{rid}:fritz:direct")
    room = next(r for r in ctrl.snapshot()["rooms"] if r["id"] == rid)
    assert room["kind_hint"] is None and room["dismissed_count"] == 1
    await ctrl.async_reset_hints(rid)
    assert next(r for r in ctrl.snapshot()["rooms"] if r["id"] == rid)["kind_hint"]


async def test_preview_has_sun_year(hass, ctrl):
    p = ctrl.runner.preview({"type": "plan", "kind": "cover", "name": "R", "devices": ["cover.a"], "mode": "simple",
                             "simple": {"rows": {"mf": {"like": "own", "open": {"ref": "time", "time": "07:00"}}},
                                        "close": {"ref": "sunset", "offset": 60, "earliest": "18:00", "latest": "23:00"}},
                             "conds": {"op": "and", "items": []}})
    sy = p["sun_year"]
    n = (date(sy["year"] + 1, 1, 1) - date(sy["year"], 1, 1)).days
    assert len(sy["rise"]) == len(sy["set"]) == n
    assert all(0 <= r < s < 1440 for r, s in zip(sy["rise"], sy["set"]))


# ------------------------------------------------------------------ Karte: Knopf „+ Grenzen“, Jahresband, Absicherung
pw = pytest.importorskip("playwright.async_api")
CARD = Path(__file__).parent.parent / "custom_components" / "home_rhythm" / "www" / "home-rhythm-card.js"


@pytest.fixture
async def card(tmp_path):
    html = tmp_path / "p.html"
    html.write_text("<!doctype html><meta charset='utf-8'><script>customElements.define('ha-icon', class extends HTMLElement {});</script><script>"
                    + CARD.read_text(encoding="utf-8") + "</script><body><home-rhythm-card id='c'></home-rhythm-card></body>", encoding="utf-8")
    async with pw.async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception as err:  # noqa: BLE001 – Browser nicht installiert
            pytest.skip(f"Chromium nicht verfügbar: {err}")
        pg = await browser.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        await pg.goto(html.as_uri())
        pg.errors = errors
        yield pg
        await browser.close()


# Sonnenuntergang: Jan–Feb und Nov–Dez 16:30, sonst 21:00 (grob, reicht für die Abschnitte)
SET = "Array.from({length: 365}, (_, i) => (i < 59 || i >= 304) ? 990 : 1260)"


async def test_card_limits(card):
    r = await card.evaluate(f"""() => {{
      const el = document.getElementById('c');
      el._data = {{ now: '2026-11-20T21:00:00+01:00' }};
      const spec = {{ ref: 'sunset', offset: 60, unit: 'h', earliest: '18:00', latest: '23:00' }};
      el._fedit = {{ flow: {{ simple: {{ close: spec }} }}, preview: {{ sun_year: {{ year: 2026, rise: Array(365).fill(480), set: {SET} }} }} }};
      el._simObj = (p) => el._fedit.flow.simple[p];
      const chip = el._limChipHtml('close', spec), chip0 = el._limChipHtml('close', {{ ref: 'sunset', offset: 0 }});
      const lim = el._limHtml('close', spec), year = el._yearHtml('close');
      el._fedit.limOpen = {{ close: true }}; el._fedit.yearOpen = {{ close: true }};
      const open = el._limHtml('close', spec), yearOpen = el._yearHtml('close');
      const bad = el._limHtml('close', {{ ref: 'sunset', offset: 0, earliest: '23:00', latest: '18:00' }});
      const sumTxt = el._specTxt(spec, true, false);
      const calc = (el._fedit.preview.sun = [{{ rise: 480, set: 975 }}], el._todayIdx = () => 0, el._sunCalc(spec));
      return {{ chip, chip0, lim, year, open, yearOpen, bad, sumTxt, calc }};
    }}""")
    assert "18:00 – 23:00 ✎" in r["chip"] and 'class="limchip set"' in r["chip"]
    assert "+ Grenzen" in r["chip0"]
    assert 'data-a="fsp"' not in r["lim"] and 'data-year="close"' in r["lim"]           # zugeklappt: keine Felder
    assert 'data-f="earliest"' in r["open"] and 'data-f="latest"' in r["open"]        # aufgeklappt: beide Felder
    assert "frühestens 18:00</span> greift ca. 1.11.–28.2. (120 Tage)" in r["year"]  # über den Jahreswechsel
    assert "spätestens 23:00</span> greift nie" in r["year"] and "<svg" not in r["year"]
    assert "<svg" in r["yearOpen"]
    assert "„frühestens“ liegt nach „spätestens“" in r["bad"] and "data-year" not in r["bad"]
    assert r["sumTxt"] == "Sonnenuntergang +1 Std. (18:00–23:00)"
    assert r["calc"] == "heute ≈ 18:00 · frühestens greift"
    assert card.errors == []


async def test_card_guard_and_kind_hint(card):
    r = await card.evaluate("""() => {
      const el = document.getElementById('c'); el._hass = { user: { is_admin: true } };
      const names = { mf: 'Mo–Fr', sa: 'Samstag' };
      const s = (close) => ({ guard: '23:00', close_per_row: false, close, rows: {} });
      return {
        ok: el._guardNoteHtml(s({ ref: 'sunset', offset: 60, latest: '23:00' }), true, names),
        nolat: el._guardNoteHtml(s({ ref: 'sunset', offset: 60, earliest: '18:00' }), true, names),
        late: el._guardNoteHtml(s({ ref: 'time', time: '23:30' }), true, names),
        kind: el._kindHintHtml({ id: 'bad', kind_hint: { id: 'kind:bad:fritz:direct', kind: 'fritz', suggest: 'direct' } }),
        none: el._kindHintHtml({ id: 'bad', kind_hint: null }),
      };
    }""")
    assert "gilt an allen Tagen" in r["ok"]
    assert "gilt nicht" in r["nolat"] and "ohne „spätestens“" in r["nolat"]
    assert "23:30 liegt danach" in r["late"]
    assert "FRITZ!DECT" in r["kind"] and 'data-a="kindset"' in r["kind"] and 'data-k="direct"' in r["kind"]
    assert r["none"] == ""
    assert card.errors == []
