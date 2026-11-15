<p align="center"><img src="custom_components/home_rhythm/brand/logo.png" alt="Home Rhythm" width="420"></p>

# Home Rhythm

**Der Wochenrhythmus deines Zuhauses – Heizung, Klima, Rollläden, Licht und Steckdosen in einer Karte, mit Begründung.**

Home Rhythm ist eine Integration für [Home Assistant](https://www.home-assistant.io/) mit eigener Dashboard-Karte.
Sie steuert alle Thermostate und Klimaanlagen nach Wochenplänen und Hausmodi (Jahreszeit, Urlaub, Feiertag,
Anwesenheit …), schaltet Rollläden, Licht und Steckdosen nach frei zusammengestellten Zeitplänen und reagiert auf
Ereignisse wie Bewegung oder einen Knopfdruck. Für jeden Raum und jeden Ablauf siehst du, **was gerade gilt und warum**.

> Sprache der Oberfläche: Deutsch. Läuft komplett lokal – keine Cloud, kein Konto, keine Daten nach außen.

---

## Was Home Rhythm besonders macht

Die meisten Heizungs- und Zeitplan-Lösungen beantworten nur „was soll passieren?“. Home Rhythm beantwortet auch
**„warum passiert gerade das – und was passiert als Nächstes?“**: Jede Raumzeile sagt dir „Komfort 21 °C · Wochenplan
· bis 22:00“, „Hand-Änderung (Automation ‚Gute Nacht‘) · bis morgen“ oder „Feiertag → Sonntagsplan“, und die
Übersicht zeigt als Zeitleiste alles, was heute im Haus noch geschaltet wird – auch für ein beliebiges Datum, etwa
Heiligabend. Statt vieler einzelner Automationen gibt es **einen Ort** für Hausmodi, Wochenpläne, Rollläden, Licht und
Reaktionen, mit **verständlichen Sätzen statt YAML** („Wenn Bewegung am Hoftor und Sonne ist dunkel → Licht an,
nach 3 Minuten ohne Bewegung aus“). Home Rhythm respektiert, was Menschen von Hand ändern (es schaltet nur zu
Schaltpunkten und erkennt Hand-Änderungen am Thermostat), es erkennt **fremde Steuerung** (Automationen, Fritz!Box-
Zeitpläne), die gegen den Plan arbeiten, und es rechnet bei Klimaanlagen aus, **ob gerade Gas oder Strom billiger heizt**.
Und wer lieber bei klassischen HA-Automationen bleibt, kann jeden Ablauf mit einem Schalter **auch als echte
Home-Assistant-Automation** anlegen lassen.

---

## Funktionen im Überblick

| Bereich | Was es kann |
|---|---|
| **Heizung & Klima** | Räume aus HA-Bereichen, mehrere Thermostate pro Raum (gemeinsam oder einzeln, mit Abweichung ± °C), Stufen (Komfort, Absenkung, Nacht, Booster + bis zu 4 eigene), Wochenplan Mo–Fr / Sa / So+Feiertag, Hand-Änderungen mit Ablaufzeit und ✕ zum Zurücksetzen, Better Thermostat und Versatile Thermostat werden erkannt, Verlauf, Luftfeuchte. |
| **Hausmodi** | Jahreszeit (auch automatisch nach Außentemperatur), Urlaub zu Hause / unterwegs, Feiertag (Workday), Anwesenheit, Ereignis (Party, Gäste), Anlass Weihnachten, „Heute anders“ pro Raum, Raumregeln. |
| **Klimaanlage** | Heizt mit, wenn sie billiger ist als Gas (COP-Kurve, Gas- und Strompreis, Wirkungsgrad), Heizkörper als Reserve, Kühlen in der Heißphase mit Vorkühlen. |
| **Abläufe – Zeitpläne** | Rollläden oder Licht/Steckdosen frei gruppieren (einzeln oder per Bereich, Etage, Label), Schaltpunkte nach Uhrzeit oder Sonne ± Minuten mit „frühestens/spätestens“, Arbeitstag/freier Tag/Wochentage, Bedingungen mit UND/ODER-Gruppen, „nur falls nötig“, „nachprüfen & wiederholen“, Urlaubssimulation, „Nächsten Schaltpunkt überspringen“. |
| **Abläufe – Reaktionen** | Wenn → Dann: Bewegung, Knopf, Schalter, Leistung über/unter X … → einschalten, warten, „warten bis …“ mit Nachlauf, Warnblinken, Rollladen-Position, Nachricht. |
| **Übersicht** | Was gerade gilt, Hinweise mit direktem Sprung, Zeitleiste für heute oder ein gewähltes Datum. |
| **Geräte** | Batterie und Erreichbarkeit aller Thermostate, Sensoren, Rollläden, Lampen und Melder. |
| **Sicherheit** | Fremde Steuerung erkennen, nach Neustart nichts nachholen, nichts schalten, solange Hausmodi „nicht verfügbar“ sind. |

---

## Voraussetzungen

- Home Assistant **2026.3** oder neuer (getestet mit 2026.10).
- Alles Weitere ist optional. Die Kachel **Einrichtung → Voraussetzungen** zeigt, was da ist und was fehlt, legt
  fehlende Helfer auf Klick an (ganz normale HA-Helfer) oder merkt sich „ohne“:

| Voraussetzung | Wofür | Was passiert ohne? |
|---|---|---|
| `input_select` **Jahreszeit** (z. B. Winter / Sommer / Heißphase) | Heizen, Kühlen, „Jahreszeit ist …“ | Es wird immer geheizt und nie gekühlt. |
| `input_select` **Urlaub** (z. B. kein Urlaub / Urlaub zu Hause / Urlaub unterwegs) | Urlaubstemperatur, „Urlaub zu Hause“, Urlaubssimulation | Kein Urlaub, keine Urlaubsabsenkung. |
| Integration **Workday** | Arbeitstage und Feiertage nach Bundesland | Mo–Fr gilt als Arbeitstag, Feiertage werden nicht erkannt. |
| **Anwesenheit** (`zone.home` + Personen mit Standort) | „niemand zu Hause“ (Licht aus, Klima aus) | „niemand zu Hause“ wird nie erkannt. |
| **Außentemperatur** (Sensor oder Wetter) | Jahreszeit automatisch, Klima oder Gas | Keine automatische Jahreszeit, immer Heizkörper. |

- Optional: [Better Thermostat](https://github.com/KartoffelToby/better_thermostat) für Heizkörper,
  [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) für Klimaanlagen.

## Installation

### Über HACS (empfohlen)

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → URL dieses Repositorys, Typ **Integration** → Hinzufügen.
2. „Home Rhythm“ suchen → **Herunterladen**.
3. Home Assistant neu starten.

Updates erscheinen danach automatisch in HACS.

### Von Hand

1. Den Ordner `custom_components/home_rhythm` nach `/config/custom_components/home_rhythm` kopieren
   (z. B. mit „Studio Code Server“ oder „Samba share“).
2. Home Assistant neu starten.

### Einrichten

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Home Rhythm.**
2. Schritt 1 **Hausmodi**: Helfer für Jahreszeit, Urlaub, Arbeitstag, Anwesenheit; Urlaubstemperatur; welche
   Jahreszeiten gekühlt werden.
3. Schritt 2 **Energie**: Außentemperatur-Sensoren (einer oder mehrere, Mittel oder kältester), Gas- und Strompreis
   (fest oder aus einer Entität), Wirkungsgrad der Therme, Grenzen für die automatische Jahreszeit.
4. Ein Dashboard öffnen → Bearbeiten → **Karte hinzufügen → „Home Rhythm“** oder als YAML:

   ```yaml
   type: custom:home-rhythm-card
   ```

   Am besten in einer eigenen Ansicht vom Typ **Panel (eine Karte)**. Eine Ressource muss nicht angelegt werden.
5. Browser einmal neu laden (in der App: Einstellungen → Companion App → Debugging → Frontend-Cache leeren).

Später änderst du alles unter **Einstellungen → Geräte & Dienste → Home Rhythm → Konfigurieren** oder über ⚙️ in der Karte.

---

## Die Karte

| Reiter | Inhalt |
|---|---|
| **Übersicht** | Kopf in einer Zeile: was heute gilt, Hausmodi (Pillen, „mehr ⌄“), Zähler 🔥 ✋ ★ 🔋 📡 ⚠ – antippen zeigt die Liste mit Sprung zum Raum/Gerät; ⚙ wählt, welche Hinweise erscheinen. **🕐 Vorschau** klappt Tag, Uhrzeit-Regler und „Angenommen“ auf (was wäre wenn). Links Räume und Abläufe wie in den Reitern, rechts die **Zeitleiste** des Tages. Zeile antippen öffnet sie im Reiter, Symbol antippen öffnet das Bedien-Fenster. |
| **Heizung & Klima** | Räume nach Etagen: Ist, Soll, Stufe, Grund, „bis wann“. Aufgeklappt: Geräte, „Heute anders“, Woche, Verlauf, fremde Steuerung. Das Symbol vorne öffnet das **Bedien-Fenster** (Temperatur, Stufe, „gilt bis“, Zurück zum Plan, Links „Gerät ⤴“ zum HA-Dialog). |
| **Abläufe** | Zeitpläne (Rollläden, Licht & Steckdosen) und Reaktionen. Jeder Ablauf zeigt Zustand, nächsten Schaltpunkt und den heutigen Verlauf; aufgeklappt Woche, Protokoll und Aktionen. Das Symbol vorne öffnet das Bedien-Fenster (alle oder einzelne Geräte schalten, nächsten Schaltpunkt überspringen). „Was wäre wenn“ steht in der Übersicht unter 🕐 Vorschau. |
| **Geräte** | Batterie und Erreichbarkeit – Filter „Batterie schwach“ und „Nicht erreichbar“. |
| **Einrichtung** | Räume, Stufen, Hausmodi/Energie (öffnet HA), Sicherung (Export/Import). Nur für Administratoren. |

---

## Heizung

**Räume** entstehen aus Home-Assistant-Bereichen: Einrichtung → Bereich → **Hinzufügen**. Alle Thermostate des
Bereichs sind vorausgewählt. Ein Thermostat gehört immer nur zu einem Raum.

- **Stufen** mit Temperatur pro Raum, **Zeiten** für Mo–Fr, Samstag und Sonntag/Feiertag (`6:30`, `0630` oder `6`).
- **Hand-Änderung:** Stellt jemand am Thermostat, in der App oder per Sprache um, gilt das bis zum nächsten Wechsel
  im Plan (oder 30 min … 4 h, einstellbar). **✕** am Schild oder „Zurück zum Plan“ beendet sie sofort.
- **Mehrere Thermostate:** *gemeinsam* (eine Hand-Änderung gilt für alle) oder *einzeln*; jedes mit Abweichung ± °C.
- **Better Thermostat / Versatile Thermostat** werden erkannt: Gesteuert wird der Regler, das Gerät darunter wird
  ausgeblendet, damit nicht zwei Stellen dasselbe Ventil stellen.
- **Luftfeuchte** automatisch: Sensor aus BT/VT, sonst am Thermostat (z. B. FRITZ!DECT 440), sonst Raumsensor im Bereich.

### Klimaanlage, die mitheizt

Im Raum-Editor beim Gerät die Rolle **Klimaanlage** wählen. Home Rhythm vergleicht laufend:
*Gaspreis ÷ Wirkungsgrad* gegen *Strompreis ÷ COP bei aktueller Außentemperatur* (COP-Werte aus dem Datenblatt,
mindestens zwei Punkte). Die Karte zeigt, ab welcher Außentemperatur das Klima billiger ist. Dazu: Heizkörper als
Reserve, „Heizkörper helfen mit“, Einsatzgrenze, nachts kein Klima, Kühlen in der Heißphase mit optionalem Vorkühlen.

### So entscheidet Home Rhythm (erste zutreffende Regel gewinnt)

1. Jahreszeit ist keine Heiz-Jahreszeit → aus
2. Raumregel, die sich auf den Urlaub bezieht
3. Urlaub unterwegs → Urlaubstemperatur
4. Hand-Änderung
5. „Heute“ / Ausnahme (Stufe von … bis …, wie Mo–Fr / Sonntag, niemand im Raum) / Party (Party-Räume)
6. übrige Raumregeln
7. Feiertag oder Urlaub zu Hause → Sonntagsplan (wählbar: wie Mo–Fr, Samstag oder Sonntag – Einstellungen → Hausmodi)
8. Wochenplan

---

## Abläufe: Zeitpläne und Reaktionen

### Zeitpläne

Ein Zeitplan schaltet eine **frei zusammengestellte Gruppe** – z. B. „alle Rollläden im OG“, „Weihnachtsbeleuchtung“.

**Einfach (Standard)** – wie bei der Heizung, Zeiten je Tagesart:

| Tagesart | Auswahl |
|---|---|
| Mo–Fr | eigene Zeiten |
| Samstag | wie Mo–Fr / eigene |
| Sonntag | wie Mo–Fr / wie Samstag / eigene |
| Feiertag | wie Mo–Fr / wie Samstag / wie Sonntag / eigene |
| Urlaub zu Hause an Werktagen | eigene / wie Samstag / wie Sonntag |
| Urlaub zu Hause am Wochenende | unverändert / eigene / wie Samstag / wie Sonntag / wie Urlaub-Werktage |

Vorrang: Feiertag vor Urlaub zu Hause vor Wochentag. Je Tagesart **Öffnen** (Uhrzeit oder Sonne ± mit „frühestens“;
ganz auf oder Position %) bzw. **Einschalten**; **Schließen** eine Zeit für alle oder je Tagesart – eine Schließzeit
vor der Öffnungszeit (z. B. 00:30) gehört zum Vorabend. Dazu Absicherung („um 23:00 nochmal schließen“) und
„**Zeitplan gilt**“: immer, nicht bei „Urlaub unterwegs“, nur in einer Jahreszeit, **nur von … bis …** (jedes Jahr,
z. B. 28.11.–6.1., auch über den Jahreswechsel) oder eigene Bedingungen (auch „Datum zwischen …“).
Was von einem Sensor abhängt (z. B. Hitzeschutz ab 25 °C), ist eine **Reaktion**, kein Zeitplan.

**Übersicht:** Tag wählen und mit dem Uhrzeit-Regler „vorspulen“ – Räume (nach Etagen) und Abläufe zeigen, was zu
dieser Zeit gilt; rechts der Tagesablauf. Unter „Angenommen“ lassen sich Jahreszeit, Urlaub, Anwesenheit, Ereignis,
Weihnachten und Feiertag frei kombinieren (es wird nichts geschaltet). **Geräte:** Suche, Filter und „wofür verwendet“.

Im Editor lassen sich die Abschnitte (Geräte, Zeiten, Bestimmte Tage, Zeitplan gilt, Taster) **zuklappen** – zugeklappt
steht eine Zeile Zusammenfassung. Die **Wochenvorschau** lässt sich wochenweise blättern oder springt direkt zu Beginn/Ende
des Zeitraums und zu den bestimmten Tagen.

**Bestimmte Tage** (z. B. Heiligabend, Silvester): jedes Jahr am selben Datum eigene Zeiten – Ein-/Ausschalten
„wie sonst“, zu einer Uhrzeit, nach der Sonne oder gar nicht. Sie gehen allen Tagesarten vor; ein Ausschalten vor
12:00 (z. B. 02:00) zählt noch zu diesem Tag.

**Taster:** Ein Zigbee-Taster (oder jedes Gerät, das Tastendrücke meldet) schaltet **alle Geräte des Zeitplans
gemeinsam** – wie von Hand; der Plan läuft danach normal weiter. Gerät aus der Liste wählen oder „Taste drücken zum
Erkennen“. Eine Taste (mindestens eins an → alle aus, sonst alle an) oder eigene Tasten für an/aus; optional
„nach 1/2/3 Std. wieder aus“ und „nur wenn der Zeitplan gilt“. Wahlweise zusätzlich als **Schalter in Home Assistant**
(`switch.home_rhythm_<name>`) – für Sprache, Dashboard und andere Automationen.

**Erweitert** – beliebige **Schaltpunkte**:

- **Tage:** täglich, Arbeitstag, freier Tag (Wochenende, Feiertag, Urlaub zu Hause), Mo–Fr, Sa+So, eigene Wochentage
  oder Tagesarten (wie im einfachen Modus, auch „zählt zum Vorabend“).
- **Zeitpunkt:** Uhrzeit oder Sonnenauf-/-untergang ± Minuten, optional *frühestens* / *spätestens*.
- **Aktion:** öffnen, schließen, Position (auch pro Gerät abweichend) bzw. ein/aus mit Helligkeit.
- **nur falls nötig:** schaltet nur Geräte, die noch nicht so stehen – ideal für eine Absicherung („23:00 nochmal zu“).
- **nachprüfen & wiederholen:** nach 5 Minuten prüfen, bei Bedarf bis zu 2× erneut; Probleme stehen im Protokoll und in der Übersicht.
- **Schnellbedienung:** Ein Klick auf das Symbol vorne in der Zeile öffnet ein Fenster: alle Geräte auf einmal oder
  einzeln schalten – wie von Hand, bis zum nächsten Schaltpunkt. Erst „Übernehmen“ schaltet, ✕ verwirft.
- **Bedingungen** für den ganzen Zeitplan oder einzelne Schaltpunkte, mit Gruppen:
  `(Urlaub ist unterwegs) oder (Anwesenheit ist niemand da und Jahreszeit ist Winter)`.
  Verfügbar: Jahreszeit, Urlaub, Ereignis, Anlass, Anwesenheit, Arbeitstag, Sonne, beliebige Entität (Zustand oder
  Zahl über/unter) und der Zustand eines anderen Zeitplans.
- **Urlaubssimulation:** Zeiten jeden Tag zufällig um ± x Minuten verschieben.

Ein Schaltpunkt ist ein **Befehl zu dieser Zeit**. Was du zwischendurch von Hand änderst, bleibt bis zum nächsten
Schaltpunkt. Nach einem Neustart wird nichts nachgeholt. Stehen zwei Zeitpläne zur selben Minute auf demselben Gerät,
gilt der obere (Reihenfolge mit ↑ ↓). Ein Gerät darf in mehreren Zeitplänen stehen – die Karte zeigt das dezent an.

### Reaktionen

**Wenn** (Auslöser: Zustand wird …, Wert steigt über / fällt unter, Knopf gedrückt) **und nur wenn** (Bedingungen)
**dann** der Reihe nach: einschalten, ausschalten, umschalten, öffnen/schließen/Position, warten (Sekunden oder Minuten),
*warten bis …* mit Nachlauf, Warnblinken (Anzahl und Tempo einstellbar: je Durchgang alle aus – Pause – alle an – Pause,
endet an), Nachricht. Wird eine Reaktion erneut ausgelöst, während sie läuft: *Zeit beginnt neu* oder *ignorieren*.
Beispiele: Bewegungslicht mit Warnblinken, Timer-Knopf für die Bewässerung, Sauger mit dem Werkzeug.

### Auch als Home-Assistant-Automation

Pro Ablauf gibt es den Schalter **„Auch als Automation in Home Assistant anlegen“** (Standard: aus). Dann schreibt
Home Rhythm eine Automation mit der ID `home_rhythm_…` in `automations.yaml`, und **Home Assistant** führt sie aus –
auch wenn Home Rhythm deaktiviert ist; sie erscheint in den Ablaufverfolgungen. Bearbeitet wird weiterhin in der Karte.
Andere Automationen bleiben unangetastet; vor jedem Schreiben legt Home Rhythm `automations.yaml.home_rhythm.bak`
an. Nutzt deine `automations.yaml` `!include` oder `!secret`, schreibt Home Rhythm dort nichts hinein. Nicht übertragbar sind „nachprüfen & wiederholen“, Zufall und Überspringen – die Karte weist darauf hin.
Bedingungen, die sich in HA nicht abbilden lassen (z. B. „Zeitplan ist …“), verhindern das Anlegen, statt die
Automation stillschweigend anders laufen zu lassen.

---

## Entitäten in Home Assistant

| Entität | Bedeutung |
|---|---|
| `sensor.home_rhythm_<raum>` | Stufe des Raums, Attribute: Solltemperatur, Grund, bis wann, Wärmequelle |
| `sensor.home_rhythm_status` | was heute gilt, Räume mit Hand-Änderung |
| `select.home_rhythm_ereignis` | keins / Party / Gäste |
| `select.home_rhythm_<raum>_heute` | „Heute anders“ pro Raum (bei einer Ausnahme „Stufe“ ohne Option, Details in den Attributen) |
| `switch.home_rhythm_jahreszeit_automatisch` | Jahreszeit nach Außentemperatur |

Alle lassen sich in eigenen Automationen, per Sprache und in anderen Karten verwenden.

### Raumtemperatur: Art, Sensoren, Korrektur (ab 0.9.5)

Raum bearbeiten → Schritt 1–3. Ohne Einstellung bleibt alles wie bisher.

| Art | Sensoren | Korrektur |
|---|---|---|
| FRITZ!DECT | Fühler am Thermostat · Sensoren im Raum · in der Fritz!Box eingestellt (z. B. FRITZ!DECT 440) | keine · fest · beobachten (nur mit Sensoren im Raum) |
| Better Thermostat / andere Regel-Integration | stellt die Integration ein – Home Rhythm zeigt und prüft ihn | macht die Integration |
| Thermostat direkt (Sonoff & Co.) | Fühler am Thermostat · Sensoren im Raum | mit Sensoren: Raumwert wird ans Thermostat gesendet; sonst keine · fest |

- **Fest:** misst der Fühler 1,5 °C zu viel, −1,5 eintragen. Das Thermostat bekommt dann Soll + 1,5 (Display zeigt
  z. B. 22,5 bei 21). Für FRITZ!DECT ist der Versatz in der Fritz!Box oder ein FRITZ!DECT 440 meist angenehmer.
- **Beobachten:** misst nur (Ventil seit 1 Std. zu, höchstens alle 10 min), Export im Raum als CSV.
- **Senden (Thermostat direkt):** braucht am Gerät eine Zahl-Entität „external temperature input“ und am besten eine
  Auswahl „temperature sensor“ (Zigbee2MQTT). `system_mode` sollte `heat` sein, nicht `auto`.

### Raumkarte fürs Dashboard (ab 0.9.8)

Dashboard bearbeiten → Karte hinzufügen → „Home Rhythm“ → Raum wählen. Oder YAML:

```yaml
type: custom:home-rhythm-card
room: arbeitszimmer_og   # ohne room: ganze Home-Rhythm-Ansicht wie bisher
layout: standard       # compact | standard | tablet
step: 0.5              # + / − in 0,5 oder 1 °C
quick: [komfort, boost, today, off]   # Stufen-Schlüssel (komfort, absenkung, nacht, bad, extra1 …), boost, today, off
title: Arbeitszimmer OG   # optional
```

Statt `room:` geht auch `area:` mit der ID des Home-Assistant-Bereichs (ab 0.9.13). Die Karte nimmt dann den
Home-Rhythm-Raum mit diesem Bereich, bei mehreren den ersten; `room:` hat Vorrang. Gibt es zu dem Bereich keinen
Raum, zeigt die Karte nur eine kleine Zeile „kein Home-Rhythm-Raum“. Im grafischen Editor: „Raum wählen über“ Raum
oder Bereich.

**Raumknopf für Etagenseiten (ab 0.9.13)** – eine Zeile wie eine HA-Kachel:

```yaml
type: custom:home-rhythm-card
area: kueche
layout: knopf
navigation_path: /homecockpit-v1/kueche   # optional
name: Küche                               # optional, statt Raumname
icon: mdi:stove                           # optional, mdi-Symbol statt Emoji
```

Links das runde Raumsymbol, eingefärbt nach Zustand (🔥 heizt · 💤 Leerlauf · ⏻ aus · ✋ Hand · ⚠ nicht erreichbar),
rechts Name mit ★ ⚠ 🔋 und darunter „Ist · Soll“ (bzw. „· aus“, bei Hand „· ✋ bis 18:30“). Ist ein Thermostat nicht
erreichbar, bleiben Ist und Soll sichtbar, dazu ⚠. Das Symbol öffnet das Bedien-Fenster; die übrige Fläche wechselt zu
`navigation_path` oder öffnet ohne Pfad ebenfalls das Bedien-Fenster. In Abschnitts-Ansichten ist der Knopf 6 von
12 Spalten breit und eine Reihe hoch (mindestens 3 Spalten).

Viele Karten auf einer Seite laden die Daten nur einmal und teilen sich ein Abo. Für andere Karten gibt es die
leichte Abfrage `home_rhythm/rooms` (auch ohne Admin): je Raum `id`, `name`, `area_id`, `enabled`,
`climate_entities`, `ac_entities`, `room_temp_entities` (die Raumfühler) mit `room_temp_source`
(`sensors` · `box` · `integration` · `device`), `ist`, `soll`, `hvac_mode`, `level`, `level_name`, `manual_until`,
`unavailable`. Mit `home_rhythm/subscribe` meldet Home Rhythm jede Änderung (ohne Daten), danach neu abfragen.

+ / − und die Schnellwahl lösen eine Hand-Änderung für den Raum aus (mit „Zurück zum Plan“). Stufen und „Aus“ fragen
„bis wann?“. Das Symbol öffnet das Bedien-Fenster (ein Entwurf, bis du „Übernehmen“ tippst), der Name klappt den Raum auf. Bedienen dürfen alle Benutzer,
Einstellungen nur Administratoren.

### Bedienteile (ab 0.9.6, Anlernen ab 0.9.7)

Raum bearbeiten → Schritt 4. Ein Bedienteil löst eine Hand-Änderung für den ganzen Raum aus (mit ✋, „gilt bis …“ und
„Zurück zum Plan“) – unabhängig davon, welche Art von Thermostat der Raum hat.

1. **Gerät wählen** (Taster oder Bedienteil mit Anzeige, z. B. SONOFF SNZB-01M, Hue Dimmer, IKEA, Aqara W100).
2. Je Funktion **„anlernen“** antippen und am Gerät die Taste drücken: wärmer · kälter · zurück zum Plan ·
   Booster 1 Std. · Komfort bis zum nächsten Wechsel · aus bis zum nächsten Wechsel. Home Rhythm merkt sich genau,
   was das Gerät dabei meldet (Ereignis, Aktion, Sollwert hoch/runter, Ein/Aus oder – beim W100 – die Mitteltaste
   als Meldung ohne Wert). Nicht belegte Tasten bleiben frei für eigene Automationen.
3. Geräte mit Anzeige: Häkchen **„Sollwert des Raums auf dem Display zeigen“**. Nach jedem erkannten Tastendruck
   schreibt Home Rhythm den Sollwert sofort zurück – das W100 aktualisiert sein Display erst dann.

Tipp W100: `temp_threshold` auf 0,1–0,2 stellen, wenn es auch Raumsensor ist.

### Ausnahme „Heute“

Je Raum gibt es höchstens **eine** Ausnahme; eine neue ersetzt die alte. In der Karte: Raum aufklappen → „Heute: … ▾“.

- **Stufe von … bis …** – jede wählbare Stufe (auch eigene wie „Homeoffice“), Beginn jetzt / Uhrzeit / anderer Tag,
  Ende Tagesende / Uhrzeit / späterer Tag (höchstens 14 Tage voraus). Außerhalb gilt der Plan. Eine geplante Ausnahme
  steht bis zum Beginn mit ⏱ in der Raumzeile; mit ihrem Beginn endet eine laufende Hand-Änderung.
  Eine Hand-Änderung während der Ausnahme gilt bis zu deren Ende (bei „bis zum nächsten Wechsel“).
  Klimaanlagen kühlen, wenn die Stufe „Raum belegt“ ist.
- **Wie Mo–Fr / wie Sonntag / niemand im Raum** – ganze Tage: nur heute, heute und morgen oder bis einschließlich Datum.
- **Party bis 1 Uhr.**

Dienste für Automationen, Sprache oder Kalender:

```yaml
action: home_rhythm.set_exception
data:
  room: Arbeitszimmer EG   # Name oder ID
  level: Homeoffice        # Name der Stufe
  start: "2026-11-09 14:00:00"   # optional, sonst sofort
  end: "2026-11-09 21:30:00"
---
action: home_rhythm.clear_exception
data:
  room: Arbeitszimmer EG
```

---

## Umstieg von anderen Lösungen

Erst wenn alle Räume und Abläufe angelegt sind:

1. Bisherige Heizungs-Automationen und Zeitplan-Integrationen (z. B. Scheduler, Thermostat-Timeline) deaktivieren.
2. Zeitpläne in der Fritz!Box bzw. am Thermostat ausschalten – sonst meldet Home Rhythm sie als fremde Steuerung.
3. In Better Thermostat / Versatile Thermostat keine Presets oder Zeitpläne nutzen – das übernimmt Home Rhythm.
4. Better Thermostat mit Fritz!DECT: Kalibrierungsmodus nicht „KI zeitbasiert“ (dreht bis 28 °C auf), sondern mit externem Sensor „Nur externer Sensorversatz“, ohne externen Sensor „Keine Kalibrierung“.
5. Für Rollläden und Licht: die alten Automationen der Geräte deaktivieren, die jetzt ein Ablauf schaltet.

---

## Datenschutz und Sicherheit

- **Alles lokal.** Home Rhythm stellt keine Verbindung ins Internet her, nutzt keine Cloud, sammelt keine Telemetrie.
- **Gespeichert** wird in `/config/.storage/home_rhythm.data`: Räume, Stufen, Abläufe, laufende Hand-Änderungen, die
  letzten fremden Änderungen je Thermostat (mit Name und ID des HA-Benutzers bzw. der Automation, die geändert hat) und
  ein kurzes Protokoll je Ablauf (höchstens 30 Einträge). Tagesmittel der Außentemperatur für die Jahreszeit-Automatik.
- **Beim Löschen der Integration** werden diese Daten und alle von Home Rhythm angelegten Automationen entfernt.
- **Sicherung (Export)** enthält nur die Einrichtung – keine Protokolle, Hand-Änderungen oder Benutzernamen. Die Datei
  enthält aber die Namen deiner Geräte und Räume; teile sie entsprechend vorsichtig.
- **Rechte:** Einrichtung ändern (Räume, Stufen, Abläufe, Import/Export, Test) dürfen nur **Administratoren**.
  Alltägliches (Zurück zum Plan, Heute anders, Ereignis, „Jetzt auf Plan setzen“, Überspringen) dürfen alle Nutzer –
  sie könnten die Geräte in HA ohnehin selbst schalten.
- **Eingaben werden geprüft:** erlaubte Gerätearten, gültige Entitäten, Zeiten, Größenbegrenzungen. Es gibt bewusst
  **keine Templates und keine frei wählbaren Dienste** – ein Ablauf kann nichts anderes tun, als die gewählten Geräte
  zu schalten oder eine Nachricht über `notify.*` zu senden.
- **Schreiben in `automations.yaml`** nur bei eingeschaltetem Schalter, nur für eigene Einträge, mit Sicherung,
  Sperre gegen gleichzeitiges Schreiben und atomarem Schreiben; ist die Datei unlesbar oder nutzt sie `!include`/`!secret`,
  wird nichts geschrieben. Nachrichtentexte dürfen keine Template-Klammern enthalten.
- **Zirkelbezüge** („Zeitplan A gilt, wenn Zeitplan B …, und B, wenn A …“) werden beim Speichern abgelehnt.
- **Sommer-/Winterzeit:** Schaltpunkte in der doppelten Stunde laufen nur einmal, in der übersprungenen Stunde werden sie nachgeholt.
- Die Karte zeigt alle Texte maskiert an (kein HTML aus Namen oder Werten).

Sicherheitslücke gefunden? Bitte nicht als öffentliches Issue, sondern über „Security → Report a vulnerability“ melden.

---

## Fehlersuche

- **Karte erscheint nicht / alte Version:** Browser-Cache leeren bzw. in der App den Frontend-Cache leeren.
- **„Hand-Änderung“, die keine war:** Funk-Thermostate übernehmen Werte oft erst nach Minuten. Home Rhythm wartet
  3 Minuten und sendet nach 10 Minuten erneut. Unter „Zuletzt von außen geändert“ steht, wer geändert hat.
  ✕ am Schild setzt zurück.
- **Ein Ablauf schaltet nicht:** Protokoll im aufgeklappten Ablauf ansehen; Bedingung erfüllt? Geräte erreichbar?
  Hausmodi-Helfer verfügbar? (Ist einer „nicht verfügbar“, schaltet Home Rhythm sicherheitshalber nichts.)
- **Protokoll für Entwickler:** in `configuration.yaml`

  ```yaml
  logger:
    logs:
      custom_components.home_rhythm: debug
  ```

## Entfernen

Einstellungen → Geräte & Dienste → Home Rhythm → Löschen, dann den Ordner `custom_components/home_rhythm` entfernen
(bzw. in HACS deinstallieren) und neu starten. Die Geräte bleiben auf dem letzten Wert.

---

## Entwicklung

```
custom_components/home_rhythm/
  engine.py       Regeln für Heizen/Kühlen (reine Logik, ohne HA)
  flows.py        Zeitpläne und Reaktionen (reine Logik, Prüfung aller Eingaben)
  controller.py   Räume, Thermostate, Hand-Änderungen, Energie, Daten für die Karte
  runner.py       führt Zeitpläne und Reaktionen aus, Zeitleiste, Vorschau
  native.py       optionale Übersetzung in HA-Automationen
  websocket_api.py  Befehle der Karte (mit Rechteprüfung)
  www/home-rhythm-card.js  die Karte (ohne Build-Schritt)
tests/            pytest mit pytest-homeassistant-custom-component
```

Tests: `pip install pytest-homeassistant-custom-component && pytest -q`. Die Kartentests (`tests/test_card_*.py`)
brauchen zusätzlich `pip install playwright && playwright install chromium`, sonst werden sie übersprungen.

## Lizenz

[MIT](LICENSE)

---

## English summary

**Home Rhythm** is a local-only Home Assistant integration with its own dashboard card (German UI). It controls all
thermostats and AC units by weekly schedules and house modes (season, vacation, holidays, presence, events), explains
for every room *why* a temperature applies and until when, detects manual changes and foreign control, and decides
whether gas or the heat pump/AC is cheaper. Its *Abläufe* (flows) switch freely grouped covers, lights and plugs at
time/sun-based points with AND/OR conditions, and *reactions* handle triggers like motion or buttons. Every flow can
optionally be written as a native Home Assistant automation. Install via HACS (custom repository) and add
`type: custom:home-rhythm-card` to a dashboard.
