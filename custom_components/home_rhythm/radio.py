"""0.9.17: Funk-Zuverlässigkeit je Thermostat.

HomeRhythm merkt sich, ob seine eigenen Befehle an einem Thermostat ankommen:
- Befehle (Sollwert/Modus): rechtzeitig übernommen, verspätet übernommen, nie übernommen; längste Verzögerung
- Raumwert (an Thermostate mit externem Fühler-Eingang gesendete Raumtemperatur): angekommen oder nicht
- wie oft und wie lange das Thermostat in HA „nicht erreichbar“ war

Gespeichert wird je Thermostat und Stunde nur eine kleine Zählung (7 Tage), dazu die Ereignisse der letzten
gut 24 Stunden für Band und Liste in der Karte. Keine Messwerte, keine Namen – nur Zeiten und Zahlen.
Gezählt wird nur, was HomeRhythm selbst sendet; Störungen anderer Geräte sieht HomeRhythm nicht.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

KEEP_DAYS = 8  # Stundenzählung (7 Tage Anzeige + heute)
KEEP_EVENTS = timedelta(hours=26)
MAX_EVENTS = 60  # je Thermostat
RV_LIMIT = timedelta(minutes=5)  # so lange darf ein Raumwert bis zur Rückmeldung brauchen
# Grenzen für das gelbe ⚠ (letzte 24 h, abgestimmt am 26.11.2026 mit Entwurf 1)
YELLOW_OFF_COUNT = 3
YELLOW_RV_SHARE = 0.8
RV_MIN_SAMPLES = 5  # bei weniger gesendeten Raumwerten keine Quote bewerten
COUNTERS = ("ok", "late", "lost", "dmax", "off", "offs", "rv", "rvok")


def _hour_key(when: datetime) -> str:
    return dt_util.as_local(when).strftime("%Y-%m-%dT%H")


def _parse(v: Any) -> datetime | None:
    try:
        return dt_util.parse_datetime(v) if v else None
    except (TypeError, ValueError):
        return None


class RadioLog:
    """Zählung und Ereignisse je Thermostat (entity_id)."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}
        self.reset_at: datetime | None = None  # „Zählung neu beginnen“ (volle Stunde)
        self._rv_pending: dict[str, dict[str, Any]] = {}
        self._off_since: dict[str, datetime] = {}

    # ------------------------------------------------------------------ Speichern
    def load(self, raw: Any) -> None:
        self.data, self.reset_at = {}, None
        if not isinstance(raw, dict):
            return
        self.reset_at = _parse(raw.get("reset_at"))
        for eid, d in (raw.get("ents") or {}).items():
            if not isinstance(d, dict):
                continue
            buckets = {k: {c: v.get(c, 0) for c in COUNTERS} for k, v in (d.get("b") or {}).items() if isinstance(v, dict)}
            events = [e for e in (d.get("ev") or []) if isinstance(e, dict) and _parse(e.get("s"))]
            self.data[eid] = {"b": buckets, "ev": events}

    def dump(self) -> dict[str, Any]:
        return {"reset_at": self.reset_at.isoformat() if self.reset_at else None, "ents": self.data}

    def forget(self, entity_id: str) -> None:
        self.data.pop(entity_id, None)
        self._rv_pending.pop(entity_id, None)
        self._off_since.pop(entity_id, None)

    def prune(self, now: datetime) -> None:
        cut_key = _hour_key(now - timedelta(days=KEEP_DAYS))
        cut_ev = now - KEEP_EVENTS
        for d in self.data.values():
            for k in [k for k in d["b"] if k < cut_key]:
                d["b"].pop(k)
            d["ev"] = [e for e in d["ev"] if (_parse(e.get("e")) or now) >= cut_ev][-MAX_EVENTS:]

    # ------------------------------------------------------------------ Erfassen
    def _ent(self, entity_id: str) -> dict[str, Any]:
        return self.data.setdefault(entity_id, {"b": {}, "ev": []})

    def _bucket(self, entity_id: str, when: datetime) -> dict[str, Any]:
        return self._ent(entity_id)["b"].setdefault(_hour_key(when), {c: 0 for c in COUNTERS})

    def _event(self, entity_id: str, kind: str, start: datetime, end: datetime | None, **extra: Any) -> None:
        ev = self._ent(entity_id)["ev"]
        ev.append({"k": kind, "s": start.isoformat(), "e": end.isoformat() if end else None, **extra})
        del ev[:-MAX_EVENTS]

    def command_done(self, entity_id: str, since: datetime, done: datetime, tries: int, limit: float, want: str) -> None:
        """Ein gesendeter Wert ist angekommen (gezählt in der Stunde, in der er gesendet wurde)."""
        delay = max(0.0, (done - since).total_seconds())
        b = self._bucket(entity_id, since)
        if delay <= limit:
            b["ok"] += 1
        else:
            b["late"] += 1
            self._event(entity_id, "late", since, done, tries=tries, want=want)
        b["dmax"] = max(b["dmax"], round(delay))

    def command_lost(self, entity_id: str, since: datetime, end: datetime, tries: int, want: str, why: str) -> None:
        """Ein gesendeter Wert kam nie an (z. B. vom nächsten Plan-Wechsel oder einer Hand-Änderung abgelöst)."""
        b = self._bucket(entity_id, since)
        b["lost"] += 1
        b["dmax"] = max(b["dmax"], round((end - since).total_seconds()))
        self._event(entity_id, "lost", since, end, tries=tries, want=want, why=why)

    def old_value_late(self, entity_id: str, at: datetime, value: str) -> None:
        """Ein alter, schon überholter Befehl kam verspätet an – als Hinweis in der Liste."""
        self._event(entity_id, "old", at, at, want=value)

    def went_offline(self, entity_id: str, at: datetime) -> None:
        if entity_id not in self._off_since:
            self._off_since[entity_id] = at
            self._bucket(entity_id, at)["off"] += 1

    def back_online(self, entity_id: str, at: datetime) -> None:
        start = self._off_since.pop(entity_id, None)
        if start is None:
            return
        self._bucket(entity_id, start)["offs"] += round((at - start).total_seconds())
        self._event(entity_id, "off", start, at)

    def offline_since(self, entity_id: str) -> datetime | None:
        return self._off_since.get(entity_id)

    def rv_sent(self, entity_id: str, number_entity: str, value: float, at: datetime) -> None:
        """Raumwert gesendet. Gezählt wird beim nächsten Prüfen (angekommen oder nach 5 Min. nicht)."""
        self._rv_pending[entity_id] = {"num": number_entity, "value": value, "at": at}

    def rv_check(self, entity_id: str, current: float | None, now: datetime) -> None:
        p = self._rv_pending.get(entity_id)
        if not p:
            return
        if current is not None and abs(current - p["value"]) < 0.05:
            b = self._bucket(entity_id, p["at"])
            b["rv"] += 1
            b["rvok"] += 1
            self._rv_pending.pop(entity_id)
        elif now - p["at"] >= RV_LIMIT:
            b = self._bucket(entity_id, p["at"])
            b["rv"] += 1
            self._rv_pending.pop(entity_id)
            # aufeinanderfolgende Ausfälle zu einem Ereignis zusammenfassen (sonst alle paar Minuten eine Zeile)
            ev = self._ent(entity_id)["ev"]
            last = next((e for e in reversed(ev) if e["k"] == "rv"), None)
            if last and (e_at := _parse(last["e"])) and p["at"] - e_at <= timedelta(minutes=30):
                last["e"], last["n"] = now.isoformat(), int(last.get("n", 1)) + 1
            else:
                self._event(entity_id, "rv", p["at"], now, n=1)

    def rv_pending(self, entity_id: str) -> dict[str, Any] | None:
        return self._rv_pending.get(entity_id)

    # ------------------------------------------------------------------ Auswerten
    def counting_from(self, now: datetime, hours: int = 24) -> datetime:
        start = now - timedelta(hours=hours)
        if self.reset_at and self.reset_at > start:
            return self.reset_at
        return start

    def summary(self, entity_id: str, now: datetime, limit: float, pending: dict[str, Any] | None = None,
                last_seen: datetime | None = None) -> dict[str, Any]:
        """Zahlen der letzten 24 h (bzw. seit „Zählung neu beginnen“) und das daraus folgende Zeichen.

        pending: laufender, noch nicht übernommener Befehl ({since, tries, want}) – zählt ab der Grenze als
        „nicht übernommen“, damit Zahlen und rotes ⚠ zusammenpassen.
        """
        start = self.counting_from(now)
        first = _hour_key(start)
        # Stunde des Neubeginns: nur, wenn die Zählung zur vollen Stunde beginnt (reset_at ist abgerundet)
        d = self.data.get(entity_id) or {"b": {}, "ev": []}
        tot = {c: 0 for c in COUNTERS}
        for k, b in d["b"].items():
            if k >= first:
                for c in COUNTERS:
                    tot[c] = max(tot[c], b[c]) if c == "dmax" else tot[c] + b[c]
        hang = None
        if pending and pending.get("since") and (now - pending["since"]).total_seconds() >= limit:
            tot["lost"] += 1
            tot["dmax"] = max(tot["dmax"], round((now - pending["since"]).total_seconds()))
            hang = pending
        off_now = self._off_since.get(entity_id)
        if off_now:
            tot["offs"] += round((now - max(off_now, start)).total_seconds())
        cmds = tot["ok"] + tot["late"] + tot["lost"]
        why = []
        if tot["late"] + tot["lost"]:
            bad = tot["late"] + tot["lost"]
            verb = "kam" if bad == 1 else "kamen"
            why.append(f"{bad} von {cmds} Befehlen {verb} nicht rechtzeitig an (längstens {max(1, round(tot['dmax'] / 60))} Min.)")
        if tot["off"] >= YELLOW_OFF_COUNT:
            why.append(f"{tot['off']}× nicht erreichbar (zusammen {round(tot['offs'] / 60)} Min.)")
        share = tot["rvok"] / tot["rv"] if tot["rv"] else None
        if share is not None and tot["rv"] >= RV_MIN_SAMPLES and share < YELLOW_RV_SHARE:
            why.append(f"nur {round(share * 100)} % der Raumwerte kamen an")
        events = []
        for e in d["ev"]:
            s, en = _parse(e["s"]), _parse(e.get("e"))
            if (en or now) < start:
                continue
            events.append({**e, "s": max(s, start).isoformat() if s else e["s"]})
        if hang:
            events.append({"k": "hang", "s": hang["since"].isoformat(), "e": None, "tries": hang.get("tries", 1), "want": hang.get("want", "")})
        if off_now:
            events.append({"k": "off", "s": max(off_now, start).isoformat(), "e": None})
        events.sort(key=lambda e: e["s"], reverse=True)
        return {
            "level": "r" if hang else ("y" if why else ""),
            "why": why,
            "from": start.isoformat(),
            "cmd_ok": tot["ok"],
            "cmd_total": cmds,
            "delay_max": tot["dmax"],
            "off_count": tot["off"],
            "off_seconds": tot["offs"],
            "rv_ok": tot["rvok"],
            "rv_total": tot["rv"],
            "last_seen": last_seen.isoformat() if last_seen else None,
            "events": events[:30],
            "days": self.days(entity_id, now, hanging=bool(hang)),
        }

    def days(self, entity_id: str, now: datetime, hanging: bool = False) -> list[dict[str, Any]]:
        """Anteil rechtzeitig angekommener Befehle und Raumwerte je Tag (7 Tage, ältester zuerst).

        hanging: ein gerade hängender Befehl zählt heute schon als „nicht angekommen“ (wie in den 24 h).
        """
        d = self.data.get(entity_id) or {"b": {}}
        today = dt_util.as_local(now).date()
        out = []
        for i in range(6, -1, -1):
            day = (today - timedelta(days=i)).isoformat()
            good = total = off = 0
            for k, b in d["b"].items():
                if k.startswith(day):
                    good += b["ok"] + b["rvok"]
                    total += b["ok"] + b["late"] + b["lost"] + b["rv"]
                    off += b["off"]
            if hanging and i == 0:
                total += 1
            out.append({"date": day, "share": round(good / total * 100) if total else None, "off": off})
        return out
