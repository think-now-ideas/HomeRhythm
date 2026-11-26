"""Websocket-Befehle für die Karte.

Rechte: Alles, was die Einrichtung ändert (Räume, Stufen, Abläufe anlegen/ändern/löschen,
Export/Import), verlangt einen Administrator (``require_admin``). Alltägliches wie
„Zurück zum Plan“, „Heute anders“, „Jetzt auf Plan setzen“ oder „überspringen“ dürfen
alle angemeldeten Nutzer – sie könnten die Geräte in HA ohnehin selbst schalten.
Alle Eingaben werden im Controller bzw. in ``flows.normalize_*`` geprüft.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, EVENT_UPDATED, START_TABS


def _controller(hass: HomeAssistant, connection, msg) -> Any:
    ctrl = hass.data.get(DOMAIN, {}).get("controller")
    if ctrl is None:
        connection.send_error(msg["id"], "not_loaded", "HomeRhythm ist nicht eingerichtet")
    return ctrl


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    for handler in (ws_state, ws_room_save, ws_room_delete, ws_manual_clear, ws_preview, ws_hint_dismiss, ws_room_kind, ws_hint_reset, ws_today_set, ws_event_set, ws_season_auto_set, ws_levels_save,
                    ws_flow_save, ws_flow_delete, ws_flow_order, ws_flow_enabled, ws_flow_apply, ws_flow_skip, ws_flow_test,
                    ws_flow_stop, ws_flow_switch, ws_flow_preview, ws_flow_sim, ws_timeline, ws_at, ws_day_states, ws_export, ws_import, ws_requirement_set, ws_flow_expand, ws_start_tab_set, ws_observe_export, ws_control_learn, ws_room_manual,
                    ws_rooms, ws_subscribe, ws_radio_reset):
        websocket_api.async_register_command(hass, handler)


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/state"})
@callback
def ws_state(hass: HomeAssistant, connection, msg) -> None:
    if ctrl := _controller(hass, connection, msg):
        connection.send_result(msg["id"], ctrl.snapshot())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/room/save", vol.Required("room"): dict})
@websocket_api.async_response
async def ws_room_save(hass: HomeAssistant, connection, msg) -> None:
    if not (ctrl := _controller(hass, connection, msg)):
        return
    try:
        room_id = await ctrl.async_save_room(msg["room"])
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {"id": room_id})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/room/delete", vol.Required("room_id"): str})
@websocket_api.async_response
async def ws_room_delete(hass: HomeAssistant, connection, msg) -> None:
    if ctrl := _controller(hass, connection, msg):
        await ctrl.async_delete_room(msg["room_id"])
        connection.send_result(msg["id"], {})


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/manual/clear", vol.Required("room_id"): str})
@websocket_api.async_response
async def ws_manual_clear(hass: HomeAssistant, connection, msg) -> None:
    if ctrl := _controller(hass, connection, msg):
        await ctrl.async_clear_manual(msg["room_id"])
        connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {vol.Required("type"): "home_rhythm/preview", vol.Required("room"): dict, vol.Optional("room_id"): vol.Any(str, None)}
)
@callback
def ws_preview(hass: HomeAssistant, connection, msg) -> None:
    if not (ctrl := _controller(hass, connection, msg)):
        return
    try:
        days = ctrl.preview(msg["room"], msg.get("room_id"))
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {"days": days})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/hint/dismiss", vol.Required("hint_id"): str})
@websocket_api.async_response
async def ws_hint_dismiss(hass: HomeAssistant, connection, msg) -> None:
    if ctrl := _controller(hass, connection, msg):
        await ctrl.async_dismiss_hint(msg["hint_id"])
        connection.send_result(msg["id"], {})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/room/kind", vol.Required("room_id"): str, vol.Required("kind"): str})
@websocket_api.async_response
async def ws_room_kind(hass: HomeAssistant, connection, msg) -> None:
    """0.9.15: Art des Raums umstellen (Knopf am Hinweis „Art passt nicht zu den Thermostaten“)."""
    if ctrl := _controller(hass, connection, msg):
        try:
            await ctrl.async_set_kind(msg["room_id"], msg["kind"])
        except ValueError as err:
            connection.send_error(msg["id"], "invalid", str(err))
            return
        connection.send_result(msg["id"], {})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/hint/reset", vol.Required("room_id"): str})
@websocket_api.async_response
async def ws_hint_reset(hass: HomeAssistant, connection, msg) -> None:
    if ctrl := _controller(hass, connection, msg):
        await ctrl.async_reset_hints(msg["room_id"])
        connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "home_rhythm/today/set",
        vol.Required("room_id"): str,
        vol.Required("kind"): str,
        vol.Optional("level"): vol.Any(str, None),
        vol.Optional("start"): vol.Any(str, None),  # ISO-Zeitpunkt, None = jetzt
        vol.Optional("end"): vol.Any(str, None),  # ISO-Zeitpunkt (Ausnahme „Stufe“)
        vol.Optional("until_day"): vol.Any(str, None),  # ISO-Datum, ganze Tage bis einschließlich
    }
)
@websocket_api.async_response
async def ws_today_set(hass: HomeAssistant, connection, msg) -> None:
    from homeassistant.util import dt as dt_util  # noqa: PLC0415

    if not (ctrl := _controller(hass, connection, msg)):
        return
    try:
        start = dt_util.parse_datetime(msg["start"]) if msg.get("start") else None
        end = dt_util.parse_datetime(msg["end"]) if msg.get("end") else None
        day = dt_util.parse_date(msg["until_day"]) if msg.get("until_day") else None
        if (msg.get("start") and start is None) or (msg.get("end") and end is None) or (msg.get("until_day") and day is None):
            raise ValueError("Ungültige Zeitangabe")
        await ctrl.async_set_today(msg["room_id"], msg["kind"], level=msg.get("level"), start=start, end=end, until_day=day)
    except ValueError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/event/set", vol.Required("event"): str})
@websocket_api.async_response
async def ws_event_set(hass: HomeAssistant, connection, msg) -> None:
    if not (ctrl := _controller(hass, connection, msg)):
        return
    try:
        await ctrl.async_set_event(msg["event"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/season_auto/set", vol.Required("enabled"): bool})
@websocket_api.async_response
async def ws_season_auto_set(hass: HomeAssistant, connection, msg) -> None:
    if ctrl := _controller(hass, connection, msg):
        await ctrl.async_set_season_auto(msg["enabled"])
        connection.send_result(msg["id"], {})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/levels/save", vol.Required("levels"): dict})
@websocket_api.async_response
async def ws_levels_save(hass: HomeAssistant, connection, msg) -> None:
    if not (ctrl := _controller(hass, connection, msg)):
        return
    try:
        await ctrl.async_save_levels(msg["levels"])
    except (ValueError, TypeError, AttributeError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {})


ERRORS = (ValueError, KeyError, IndexError, TypeError, AttributeError)


def _runner(hass: HomeAssistant, connection, msg) -> Any:
    ctrl = _controller(hass, connection, msg)
    return ctrl.runner if ctrl else None


async def _run(connection, msg, coro) -> None:
    """Befehl ausführen, Eingabefehler als lesbare Meldung zurückgeben."""
    try:
        result = await coro
    except ERRORS as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], result if isinstance(result, dict) else {"result": result})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/save", vol.Required("flow"): dict})
@websocket_api.async_response
async def ws_flow_save(hass: HomeAssistant, connection, msg) -> None:
    if r := _runner(hass, connection, msg):
        async def go():
            return {"id": await r.async_save_flow(msg["flow"]), "native_error": r.native_error}
        await _run(connection, msg, go())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/delete", vol.Required("flow_id"): str})
@websocket_api.async_response
async def ws_flow_delete(hass: HomeAssistant, connection, msg) -> None:
    if r := _runner(hass, connection, msg):
        await _run(connection, msg, r.async_delete_flow(msg["flow_id"]))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/order", vol.Required("order"): [str]})
@websocket_api.async_response
async def ws_flow_order(hass: HomeAssistant, connection, msg) -> None:
    if r := _runner(hass, connection, msg):
        await _run(connection, msg, r.async_order(msg["order"]))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/enabled", vol.Required("flow_id"): str, vol.Required("enabled"): bool})
@websocket_api.async_response
async def ws_flow_enabled(hass: HomeAssistant, connection, msg) -> None:
    if r := _runner(hass, connection, msg):
        await _run(connection, msg, r.async_set_enabled(msg["flow_id"], msg["enabled"]))


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/apply", vol.Required("flow_id"): str})
@websocket_api.async_response
async def ws_flow_apply(hass: HomeAssistant, connection, msg) -> None:
    if r := _runner(hass, connection, msg):
        await _run(connection, msg, r.async_apply_now(msg["flow_id"]))


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/skip", vol.Required("flow_id"): str})
@websocket_api.async_response
async def ws_flow_skip(hass: HomeAssistant, connection, msg) -> None:
    if r := _runner(hass, connection, msg):
        async def go():
            return {"skip": await r.async_toggle_skip(msg["flow_id"])}
        await _run(connection, msg, go())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/test", vol.Required("flow_id"): str})
@websocket_api.async_response
async def ws_flow_test(hass: HomeAssistant, connection, msg) -> None:
    if r := _runner(hass, connection, msg):
        async def go():
            flow = r.flows[msg["flow_id"]]
            if flow["type"] == "react":
                r.start_reaction(msg["flow_id"], why="Test")
            else:
                await r.async_apply_now(msg["flow_id"])
            return {}
        await _run(connection, msg, go())


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/stop", vol.Required("flow_id"): str})
@websocket_api.async_response
async def ws_flow_stop(hass: HomeAssistant, connection, msg) -> None:
    if r := _runner(hass, connection, msg):
        await _run(connection, msg, r.async_stop_reaction(msg["flow_id"]))


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/switch", vol.Required("flow_id"): str,
                                  vol.Required("action"): vol.In(["open", "close", "on", "off"])})
@websocket_api.async_response
async def ws_flow_switch(hass: HomeAssistant, connection, msg) -> None:
    """Schnellbedienung: alle Geräte eines Ablaufs schalten (wie von Hand, bis zum nächsten Schaltpunkt)."""
    if r := _runner(hass, connection, msg):
        async def go():
            return {"switched": await r.async_switch_all(msg["flow_id"], msg["action"])}
        await _run(connection, msg, go())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/preview", vol.Required("flow"): dict})
@callback
def ws_flow_preview(hass: HomeAssistant, connection, msg) -> None:
    """Wochenvorschau eines noch nicht gespeicherten Zeitplans (für den Editor)."""
    if not (r := _runner(hass, connection, msg)):
        return
    try:
        connection.send_result(msg["id"], r.preview(msg["flow"]))
    except ERRORS as err:
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flows/sim", vol.Required("sim"): dict})
@callback
def ws_flow_sim(hass: HomeAssistant, connection, msg) -> None:
    """Abläufe „so tun als ob“ (Jahreszeit, Urlaub, Weihnachten, Anwesenheit) – schaltet nichts."""
    if r := _runner(hass, connection, msg):
        connection.send_result(msg["id"], r.simulate(msg["sim"]))


# „Angenommen“ in der Übersicht: nur diese Schlüssel, kurze Texte (es wird nichts geschaltet)
ASSUME_SCHEMA = vol.Schema({vol.Optional(k): vol.Any(None, vol.All(str, vol.Length(max=60)))
                            for k in ("season", "vacation", "presence", "event", "christmas", "holiday")})


def _day(msg):
    from datetime import date  # noqa: PLC0415

    from homeassistant.util import dt as dt_util  # noqa: PLC0415

    day = date.fromisoformat(msg["date"])
    if abs((day - dt_util.now().date()).days) > 400:
        raise ValueError("Datum zu weit entfernt")
    return day


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/timeline", vol.Required("date"): str, vol.Optional("assume"): ASSUME_SCHEMA})
@callback
def ws_timeline(hass: HomeAssistant, connection, msg) -> None:
    if not (r := _runner(hass, connection, msg)):
        return
    try:
        connection.send_result(msg["id"], r.timeline(_day(msg), msg.get("assume")))
    except ERRORS as err:
        connection.send_error(msg["id"], "invalid", str(err))


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/day_states", vol.Required("date"): str, vol.Optional("assume"): ASSUME_SCHEMA})
@callback
def ws_day_states(hass: HomeAssistant, connection, msg) -> None:
    """Übersicht/Zeitregler: ganzer Tag in Viertelstunden (Soll je Raum, Zustand je Zeitplan) – nur Anzeige."""
    if not (r := _runner(hass, connection, msg)):
        return
    try:
        connection.send_result(msg["id"], r.day_states(_day(msg), msg.get("assume")))
    except ERRORS as err:
        connection.send_error(msg["id"], "invalid", str(err))


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/at", vol.Required("date"): str,
                                  vol.Required("minute"): vol.All(int, vol.Range(min=0, max=1439)), vol.Optional("assume"): ASSUME_SCHEMA})
@callback
def ws_at(hass: HomeAssistant, connection, msg) -> None:
    """Übersicht/Zeitregler: Soll je Raum und Zustand je Zeitplan zu einem Zeitpunkt (nur Anzeige)."""
    if not (r := _runner(hass, connection, msg)):
        return
    try:
        connection.send_result(msg["id"], r.at(_day(msg), msg["minute"], msg.get("assume")))
    except ERRORS as err:
        connection.send_error(msg["id"], "invalid", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/export"})
@callback
def ws_export(hass: HomeAssistant, connection, msg) -> None:
    """Sicherung: Räume, Stufen und Abläufe (ohne Protokolle und Hand-Änderungen)."""
    if ctrl := _controller(hass, connection, msg):
        connection.send_result(msg["id"], ctrl.export_config())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/import", vol.Required("data"): dict})
@websocket_api.async_response
async def ws_import(hass: HomeAssistant, connection, msg) -> None:
    if ctrl := _controller(hass, connection, msg):
        await _run(connection, msg, ctrl.async_import_config(msg["data"]))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "home_rhythm/requirement/set",
    vol.Required("key"): vol.In(["season", "vacation", "workday", "outdoor"]),
    vol.Optional("entity"): vol.Any(str, None),
    vol.Optional("none", default=False): bool,
})
@websocket_api.async_response
async def ws_requirement_set(hass: HomeAssistant, connection, msg) -> None:
    """Voraussetzung übernehmen (vorhandene Entität) oder bewusst „ohne“ – nur Admins."""
    from . import requirements as R  # noqa: PLC0415

    if not (ctrl := _controller(hass, connection, msg)):
        return
    try:
        await R.async_set(ctrl, msg["key"], msg.get("entity"), msg["none"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/flow/expand", vol.Required("kind"): str, vol.Required("simple"): dict})
@callback
def ws_flow_expand(hass: HomeAssistant, connection, msg) -> None:
    """Einfachen Zeitplan in Schaltpunkte umrechnen (für „Erweitert“) – ändert nichts, braucht weder Namen noch Geräte."""
    from . import flows as F  # noqa: PLC0415

    if msg["kind"] not in F.KINDS:
        connection.send_error(msg["id"], "invalid", "Unbekannte Art")
        return
    try:
        simple = F.normalize_simple(msg["simple"], msg["kind"])
        connection.send_result(msg["id"], {"points": F.simple_points(simple, msg["kind"])})
    except ValueError as err:
        connection.send_error(msg["id"], "invalid", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/start_tab/set", vol.Required("tab"): vol.In(list(START_TABS))})
@websocket_api.async_response
async def ws_start_tab_set(hass: HomeAssistant, connection, msg) -> None:
    """Reiter, mit dem die Karte öffnet – gilt für alle Nutzer, nur Admins dürfen ihn ändern."""
    if not (ctrl := _controller(hass, connection, msg)):
        return
    await ctrl.async_set_start_tab(msg["tab"])
    connection.send_result(msg["id"], {})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/observe/export", vol.Required("room_id"): str})
@websocket_api.async_response
async def ws_observe_export(hass: HomeAssistant, connection, msg) -> None:
    """Beobachtung Fühler ↔ Raum als CSV (Semikolon, deutsches Komma) – nur Admins."""
    if not (ctrl := _controller(hass, connection, msg)):
        return
    try:
        csv_text = ctrl.observations_csv(msg["room_id"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {"csv": csv_text, "filename": f"home_rhythm_beobachtung_{msg['room_id']}.csv"})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/control/learn",
                                  vol.Required("device_id"): vol.All(str, vol.Length(min=1, max=128)),
                                  vol.Required("step"): vol.In(["start", "result", "cancel"])})
@websocket_api.async_response
async def ws_control_learn(hass: HomeAssistant, connection, msg) -> None:
    """Taste anlernen: „start“, dann „result“ abfragen, bis eine Taste gedrückt wurde (oder „cancel“)."""
    if not (ctrl := _controller(hass, connection, msg)):
        return
    dev = msg["device_id"]
    if msg["step"] == "start":
        ctrl.controls.learn_start(dev)
        connection.send_result(msg["id"], {"state": "waiting"})
    elif msg["step"] == "cancel":
        ctrl.controls.learn_cancel(dev)
        connection.send_result(msg["id"], {"state": "idle"})
    else:
        connection.send_result(msg["id"], ctrl.controls.learn_result(dev))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "home_rhythm/room/manual",
        vol.Required("room_id"): str,
        vol.Optional("temperature"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=5, max=30))),
        vol.Optional("level"): vol.Any(None, str),
        vol.Optional("off"): bool,
        vol.Optional("until"): vol.Any(None, str),  # None/„default“ = wie beim Raum eingestellt · „next“ · ISO-Zeitpunkt
        vol.Optional("minutes"): vol.Any(None, vol.All(int, vol.Range(min=1, max=1440))),
    }
)
@websocket_api.async_response
async def ws_room_manual(hass: HomeAssistant, connection, msg) -> None:
    """Raumkarte (0.9.8): Hand-Änderung für einen Raum – für alle Benutzer (nur Raum-Aktionen, keine Einstellungen)."""
    if not (ctrl := _controller(hass, connection, msg)):
        return
    try:
        await ctrl.async_card_manual(msg["room_id"], temperature=msg.get("temperature"), level=msg.get("level"), off=msg.get("off", False),
                                     until=msg.get("until"), minutes=msg.get("minutes"))
    except ValueError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/rooms"})
@callback
def ws_rooms(hass: HomeAssistant, connection, msg) -> None:
    """0.9.13: leichte Raumliste für andere Karten (z. B. HomeCockpit) – für alle Benutzer, ändert nichts."""
    if ctrl := _controller(hass, connection, msg):
        connection.send_result(msg["id"], {"rooms": ctrl.rooms_light()})


@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/subscribe"})
@callback
def ws_subscribe(hass: HomeAssistant, connection, msg) -> None:
    """0.9.13: Abo „es hat sich etwas geändert“ – auch für Nicht-Admins (die eigene HA-Ereignisse nicht abonnieren dürfen).

    Die Nachricht enthält keine Daten; die Karte lädt danach einmal ``home_rhythm/state`` bzw. ``home_rhythm/rooms``.
    """
    if not _controller(hass, connection, msg):
        return

    @callback
    def forward(_event) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], {"updated": True}))

    connection.subscriptions[msg["id"]] = hass.bus.async_listen(EVENT_UPDATED, forward)
    connection.send_result(msg["id"])


# 0.9.17: Funk-Zählung neu beginnen (z. B. nach Wechsel des Zigbee-Sticks) bzw. wieder alles zeigen.
# Ändert nur die Anzeige, nicht die Steuerung – trotzdem nur für Administratoren (betrifft alle Nutzer).
@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "home_rhythm/radio/reset", vol.Required("on"): bool})
@websocket_api.async_response
async def ws_radio_reset(hass: HomeAssistant, connection, msg) -> None:
    if not (ctrl := _controller(hass, connection, msg)):
        return
    await ctrl.async_radio_reset(msg["on"])
    connection.send_result(msg["id"], {"reset_at": ctrl.radio.reset_at.isoformat() if ctrl.radio.reset_at else None})
