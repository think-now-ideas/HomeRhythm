# Änderungen

## 0.9.16 – Thermostat übernimmt nicht
- **Rotes ⚠ am Raum, wenn ein Thermostat den gesendeten Sollwert nicht übernimmt** – erst nach 5 Minuten
  (FRITZ!DECT: 20 Minuten, die wachen nur alle paar Minuten auf), sonst ist nichts zu sehen. Typische Ursache ist
  Funk: Reichweite zum nächsten Zigbee-Router, Batterie, überlastetes Netz. Bisher zeigte die Karte in diesem Fall
  einfach den Plan-Wert, und man merkte nicht, dass das Gerät weiter mit dem alten Wert heizte.
- Antippen klappt den Raum auf: „… übernimmt den Sollwert nicht – seit 23:01, 3 Versuche. Gesendet 19,0 °C, das
  Gerät meldet 21,0 °C.“ Das ⚠ steht in der Heizungsliste, in der Raumkarte und im Raumknopf; die Kopfzeile zählt
  den Raum unter „auffällig“ (dann rot). Wechselt der Plan, während das Gerät noch nicht reagiert, zählt „seit“ weiter.
- Einmal pro Vorfall eine Warnung im Home-Assistant-Protokoll, eine Info, sobald das Gerät den Wert übernommen hat.
- `home_rhythm/rooms` (leichte Raumliste, z. B. für HomeCockpit) liefert dazu `not_taken`.
- **Raumsymbol zeigt immer den Heizzustand** (🔥 heizt, 💤 Leerlauf, ⏻ aus) – auch bei einer Hand-Änderung. Die Hand
  steht weiter im Text daneben („Hand ✕“, „✋ bis …“). Bisher verdeckte ✋ das 🔥.

## 0.9.15 – Grenzen an Sonnenzeiten
- **„frühestens“ und „spätestens“ an jeder Sonnenzeit** im einfachen Zeitplan – beim Öffnen/Einschalten und beim
  Schließen/Ausschalten, für Rollläden, Licht und Steckdosen und an bestimmten Tagen. Beispiel: „Sonnenuntergang
  + 1 Std., nicht vor 18:00, spätestens 23:00“. Liegt die Sonnenzeit vor „frühestens“, wird zu dieser Uhrzeit
  geschaltet (nicht gar nicht). Bisher bot der Editor beim Öffnen nur „frühestens“ und beim Schließen nur
  „spätestens“; die Ausführung konnte beides schon.
- Knopf **„+ Grenzen“** neben dem Versatz; sind Grenzen gesetzt, zeigt er sie („18:00 – 23:00 ✎“). „heute ≈ …“
  nennt, welche Grenze heute greift.
- **Jahresband** unter einer Sonnenzeit mit Grenzen: an welchen Tagen welche Grenze greift („frühestens 18:00 greift
  ca. 27.10.–27.1.“, „spätestens 23:00 greift nie“), aufklappbar zum Jahresverlauf. Die Sonnenzeiten fürs ganze Jahr
  kommen mit der Editor-Vorschau (`sun_year`, Standort von Home Assistant).
- Zusammenfassung des Zeitplans nennt die Grenzen („zu: Sonnenuntergang +1 Std. (18:00–23:00)“).
- **Absicherung** sagt, ob sie gilt – und wenn nicht, warum (z. B. „ohne ‚spätestens‘ kann die Sonnenzeit später sein“).
- **Hinweis „Art passt nicht zu den Thermostaten“** – z. B. Art „FRITZ!DECT“, aber das Thermostat ist ein
  Zigbee-Gerät (typisch nach einem Tausch). Im Raum mit Knopf „Auf … umstellen“ und „ist gewollt“; im Raum-Editor
  als Hinweis. Neuer WebSocket `home_rhythm/room/kind` (nur Admins). Nur eindeutige Fälle, „andere
  Regel-Integration“ wird nicht beanstandet.
- Anzeigename **HomeRhythm** (Integration, HACS, Karte, Texte). Domain `home_rhythm`, Entitäts-IDs, Gerätename
  und die Namen bereits angelegter HA-Automationen bleiben. Links in `manifest.json` auf `think-now-ideas/HomeRhythm`.
- Prüf-Action „Prüfen“ führt jetzt auch alle Tests aus (pytest, Karte in Chromium).

## 0.9.14 – neutraler Beispielpfad
- README und Test nennen als Beispiel für `navigation_path` den neutralen Pfad `/mein-dashboard/kueche`. Keine Funktionsänderung.

## 0.9.13 – Raumkarte für HomeCockpit
- **`area:` statt `room:`** – die Karte sucht den Home-Rhythm-Raum mit diesem Bereich (bei mehreren den ersten);
  `room:` hat Vorrang. Ohne passenden Raum nur eine kleine Zeile „kein Home-Rhythm-Raum“ statt Fehlerkasten.
  Grafischer Editor: „Raum wählen über“ Raum oder Bereich (beim Umschalten wird umgerechnet).
- **`layout: knopf`** – Raumknopf für Etagenseiten, eine Zeile wie eine HA-Kachel: rundes Symbol, eingefärbt nach
  Zustand (gleiche Logik wie in der Übersicht), Name mit ★ ⚠ 🔋, darunter „Ist · Soll“ / „· aus“ / „· ✋ bis …“.
  Symbol → Bedien-Fenster; Fläche → `navigation_path` (pushState + `location-changed`), ohne Pfad ebenfalls das
  Fenster. Optionen `name:`, `icon:` (mdi). Nicht erreichbar: Ist/Soll bleiben, dazu ⚠. Im Fenster entfällt
  „Raum öffnen ›“ beim Knopf ohne Pfad (mit Pfad führt es dorthin).
- **Größen für Abschnitts-Ansichten:** `getGridOptions()` – Knopf 6×1 (min. 3 Spalten); Kompakt, Standard und
  Tablet 12 Spalten (wie bisher, min. 6) mit automatischer Höhe; ganze Ansicht volle Breite.
- **Fenster liegen sicher oben:** Bedien-Fenster, „Heute anders“ und die Editoren sind jetzt `<dialog>` mit
  `showModal()` (Browser-„Top Layer“) – über der HA-Kopfleiste, nicht mehr von Abschnitten oder dem Bearbeiten-Modus
  abgeschnitten. Inhalt unverändert. Esc schließt das Bedien-Fenster (verwirft wie ✕), die Editoren nicht.
  „Gerät ⤴“ schließt das Bedien-Fenster, bevor sich das HA-Fenster öffnet (es läge sonst dahinter).
- **Ein gemeinsamer Speicher je Seite:** alle Karten teilen eine Abfrage `home_rhythm/state` und ein Abo; mehrere
  Meldungen kurz hintereinander lösen eine Abfrage aus. Die letzte Karte, die verschwindet, beendet das Abo.
- **Neu: `home_rhythm/subscribe`** (auch ohne Admin) – Nicht-Admins sehen Änderungen jetzt sofort statt erst nach
  30 Sekunden.
- **Neu: `home_rhythm/rooms`** (auch ohne Admin) – leichte Raumliste für andere Karten: id, name, area_id, enabled,
  climate_entities, ac_entities, room_temp_entities + room_temp_source, ist, soll, hvac_mode, level, level_name,
  manual_until, unavailable.
- Erste Veröffentlichung auf GitHub: Beispielnamen neutral; die feste Vorgabe alter Helfer-Entitäten für Einrichtungen
  bis 0.8.2 ist entfernt (bestehende Einrichtungen haben die Werte längst gespeichert).
- Unverändert: Übersicht, Heizung & Klima, Abläufe, Inhalt des Bedien-Fensters, Heizungslogik (engine.py).
- Tests: `test_rooms_0913.py` (Abfrage, Hand, Nicht-Admin, Abo), `test_card_0913.py` (area-Auflösung, Knopf,
  Klicks, Fenster über der Kopfleiste, gemeinsamer Speicher – mit Playwright).

## 0.9.12 – Kompakter Kopf, Bedien-Fenster
- **Übersicht, Kopf in einer Zeile:** Plan, Hausmodi als Pillen (brechen nicht um, „mehr ⌄“ wie bisher) und rechts
  Zähler 🔥 heizen · ❄ Klima · ✋ Hand · ★ Sondertag · 🔋 · 📡 · ⚠. Antippen öffnet eine kleine Liste darunter; jede
  Zeile führt zum Raum, Ablauf oder Gerät, oben „In Geräte zeigen“ bzw. „Zur Heizung“. ⚙ sammelt die Schalter, welche
  Hinweise angezeigt werden.
- **„🕐 Vorschau“** klappt Tag, Uhrzeit und „Angenommen“ auf und zu. Ob sie offen ist, wird gemerkt; die Zeit startet
  immer bei „jetzt“, Zuklappen setzt alles auf jetzt zurück.
- **Zeilen wie in den Reitern:** Räume mit Symbol · Name (★ ⚠ 🔋) · Ist · Soll · Stufe + Grund; Abläufe mit Symbol ·
  Name + Geräte · Zustand · nächster Schaltpunkt + Tagesbalken mit Markierung. Zeile antippen öffnet den Raum bzw.
  Ablauf im passenden Reiter und klappt ihn auf.
- **Bedien-Fenster** über das Symbol am Zeilenanfang – gleich in Übersicht, Heizung & Klima und Abläufe:
  - Raum: Temperatur −/+ (0,5°), Stufen inkl. Booster und aus, „gilt bis“ (nächster Wechsel, 1 Std., 2 Std., heute
    ganztägig, morgen 06:00), „Zurück zum Plan“, „Raum öffnen ›“. Links „Gerät ⤴“ öffnen das Fenster von Home
    Assistant; nicht erreichbare Geräte stehen oben. Läuft über dieselbe Funktion wie die Raumkarte, geht also auch
    ohne Admin-Rechte.
  - Ablauf: alle an/aus bzw. öffnen/schließen oder jedes Gerät einzeln, Gerätenamen öffnen das HA-Fenster,
    „nächsten Schaltpunkt überspringen“, „Jetzt wie geplant setzen“. Ersetzt die Leiste unter der Zeile.
  - **Alles im Fenster ist ein Entwurf:** „Übernehmen“ schaltet, ✕, „Abbrechen“ oder ein Tipp daneben verwirft.
  - Auf dem Handy bildschirmfüllend.
- Alle Einstellungen in Heizung & Klima und Abläufe bleiben unverändert; nur das Symbol öffnet jetzt das neue Fenster.

## 0.9.11.1 – Regler reagiert sofort, Symbole
- Übersicht: Der ganze Tag wird einmal in Viertelstunden geladen (`home_rhythm/day_states`) – beim Ziehen des Reglers
  ändern sich Räume, Abläufe und die Linie „gewählt“ sofort, ohne Rückfrage an Home Assistant.
- Symbole je Raum wie früher: jetzt 🔥 heizt · 💤 Leerlauf · ⏻ aus · ✋ Hand · ⚠ nicht erreichbar; zu anderen Zeiten
  laut Plan 🔥 warm · 💤 Absenkung · 🌙 Nacht · 🧳 Urlaub. Abläufe: 💡 an, 🔼 offen, 🔽 zu. Kurze Legende darunter.

## 0.9.11 – Übersicht mit Zeitregler, Geräteliste
- **Übersicht:** Tag wählen (wie bisher) und neu einen **Uhrzeit-Regler** (Viertelstunden, ±1 Std., „jetzt“). Links stehen die
  Räume nach Etagen (zuklappbar, gemerkt) mit Stufe, Soll und „bis … dann …“ zu dieser Zeit sowie die Abläufe
  („inaktive zeigen“ an/aus, gemerkt). Rechts der Tagesablauf wie bisher (erledigt ✓, „jetzt“) plus gestrichelte
  Linie „gewählt“; antippen stellt den Regler.
- **„Angenommen“** für Heizung und Abläufe zusammen, frei kombinierbar: Jahreszeit, Urlaub, Anwesenheit, Ereignis,
  Weihnachten, Feiertag. Die Tagesart ergibt sich aus dem gewählten Tag. Gelber Rahmen + „Vorschau – es wird nichts
  geschaltet“. Ersetzt die Leiste „Simulieren“ im Reiter Abläufe.
- Kopfzeile: Hinweise „🔋 Batterie schwach“ und neu „📡 nicht erreichbar“ einzeln abschaltbar; Antippen öffnet die
  Geräteliste schon gefiltert.
- **Geräte:** Suche; Filter nach Zustand (Probleme, Batterie, nicht erreichbar), Art (Thermostate, Sensoren,
  Bedienteile & Taster, Geräte der Abläufe) und Verwendung; unter jedem Gerät Schilder, **wofür** Home Rhythm es
  benutzt (Heizung: Raum + Rolle wie Thermostat, Raumsensor, Bedienteil; Abläufe inkl. Taster und Reaktionen;
  Außentemperatur) – antippen öffnet die Stelle. Etagen und Räume zuklappbar (zugeklappt mit Zählern und ⚠),
  Spalten Batterie / Erreichbarkeit / Luftfeuchte an/aus, **„nicht verwendete ausblenden“**. Alles wird gemerkt.
  Gewählte Raumsensoren aus anderen Bereichen und Taster der Zeitpläne erscheinen jetzt auch in der Liste.
- Korrektur: „von Hand … – bis 23:00 (nächster Schaltpunkt)“ erschien auch, wenn der Zeitplan gerade nicht gilt.
  „Nächster Schaltpunkt“ berücksichtigt jetzt überall „Zeitplan gilt“.

## 0.9.10 – Editor aufklappbar, Wochenwahl
- **Abschnitte zum Aufklappen** im Zeitplan-Editor: Geräte, Zeiten je Tagesart (bzw. Schaltpunkte), Bestimmte Tage,
  Zeitplan gilt, Taster & HA-Schalter. Zugeklappt zeigt jeder Abschnitt eine Zeile Zusammenfassung; „alle auf-/zuklappen“.
  Der Browser merkt sich, was zugeklappt ist (gilt für alle Zeitpläne).
- **Wochenvorschau mit Wochenwahl:** ‹ › wochenweise, „diese Woche“, Datum wählen; „Springen zu“ Beginn/Ende des
  Zeitraums und die bestimmten Tage (z. B. Heiligabend). Der rote „jetzt“-Strich nur in der aktuellen Woche.

## 0.9.9.1 – Darstellung
- Editor in zwei Spalten wie im Entwurf: rechts Taster, „In HA anlegen“ und die Wochenvorschau.
- Ausgeschaltete Abläufe (Haken „aktiv“ weg) sind in der Liste deutlich zurückgenommen (blass, grau, „· aus“).

## 0.9.9 – Zeitraum, bestimmte Tage, Taster
- **Zeitplan gilt: „nur von … bis …“** – jedes Jahr, von 0:00 am ersten bis 23:59 am letzten Tag, auch über den
  Jahreswechsel (z. B. 28.11.–6.1.). Dasselbe als Bedingung **„Datum zwischen …“** in eigenen Bedingungen.
- **Schaltzeiten nach Mitternacht** zählen jetzt auch bei „Zeitplan gilt“ zum Vortag: „aus um 01:00“ läuft nach dem
  letzten Tag eines Zeitraums noch (gilt auch für Jahreszeit, Weihnachten usw.).
- **Bestimmte Tage** im einfachen Modus: jedes Jahr am selben Datum eigene Zeiten (Ein-/Ausschalten „wie sonst“,
  Uhrzeit, Sonne, gar nicht), z. B. Heiligabend 15:00–02:00, Silvester bis 03:00. Gehen allen Tagesarten vor;
  die normale Zeit und die Absicherung fallen an diesen Tagen weg. Warnung, wenn ein Tag außerhalb des Zeitraums liegt.
  Im erweiterten Modus: Tage „bestimmte Tage“ (TT.MM.) und „außer …“.
- **Taster je Zeitplan:** Gerät wählen oder „Taste drücken zum Erkennen“ (20 s auf alle Taster hören), eine Taste
  (mind. eins an → alle aus, sonst alle an) oder eigene Tasten für an/aus. Schaltet alle Geräte gemeinsam wie von
  Hand; der Plan läuft danach weiter. Optional „nach 30 min … 4 Std. wieder aus“ (übersteht einen Neustart; entfällt,
  wenn der Plan vorher selbst schaltet) und „nur wenn der Zeitplan gilt“.
- **Schalter in Home Assistant je Zeitplan** (optional): `switch.home_rhythm_<name>`, an = mindestens ein Gerät an;
  Schalten wirkt wie der Taster.
- In der Liste: Chip „✋ Taster … – bis …“, solange von Hand geschaltet ist (auch nach der Schnellbedienung).
- „In HA anlegen“: Zeitraum und bestimmte Tage werden als Template-Bedingung übertragen.

## 0.9.8.1 – gelöschte Thermostate
- Fehler: Ein in Home Assistant gelöschtes Thermostat (z. B. Better Thermostat nach dem Umstieg auf Sonoff) blieb im
  Raum eingetragen und war im Raum-Editor unsichtbar – man konnte es nicht abwählen. Jetzt steht es dort als
  „… (in Home Assistant gelöscht)“ und lässt sich abhaken. Hinweis im Raum: „gibt es nicht mehr – Haken entfernen“;
  keine irreführende Meldung „kein Eingang für externe Temperatur“ und kein veralteter Ventil-Zustand mehr.

## 0.9.8 – Raumkarte fürs Dashboard
- Die Karte kann jetzt **einen einzelnen Raum** zeigen: `room: <raum-id>` (oder im visuellen Editor „Raum“ wählen).
  Ohne `room` bleibt alles wie bisher.
- Drei Größen (`layout`): **Kompakt** (eine Zeile), **Standard**, **Groß (Tablet)** mit großen Tasten und Tagesverlauf.
- **+ / −** (0,5 oder 1 °C, `step`): Hand-Änderung für den Raum; mehrere Tipper hintereinander werden zu einem Befehl.
- **Symbol antippen** öffnet wie bisher die Thermostat-Steuerung (Auswahl bei mehreren Thermostaten),
  **Name antippen** klappt den Raum wie in der vollen Ansicht auf.
- **Schnellwahl einstellbar** (`quick`, Reihenfolge im Editor): jede Stufe „… bis wann?“ (nächster Wechsel, 1 / 2 Std.,
  heute ganztägig, morgen früh, Uhrzeit), Booster 1 Std., Heute … (Ausnahme-Fenster), Aus … bis wann.
- **Bedienen dürfen alle Benutzer** (neuer Websocket `home_rhythm/room/manual`, nur Hand-Änderungen eines Raums);
  Einstellungen bleiben Administratoren vorbehalten.
- **Visueller Karten-Editor**: Raum, Titel, Größe, Schritt, Schnellwahl – bzw. Start-Reiter für die ganze Ansicht.

## 0.9.7 – Bedienteile anlernen, W100 schneller
- **Bedienteile = Gerät + angelernte Tasten** (für alle Taster und Bedienteile gleich): Gerät wählen, je Funktion
  „anlernen“ und die Taste drücken. Erkannt wird genau das, was das Gerät dabei meldet (Ereignis, Aktion,
  Sollwert + / −, Ein/Aus, Meldung ohne Wert). Eine Taste gehört immer nur zu einer Funktion.
- **W100 Mitteltaste** funktioniert: Sie meldet nur einen Zeitstempel ohne Anhang – das lässt sich jetzt anlernen
  (z. B. „zurück zum Plan“). Antworten auf eigene Befehle (bis 5 s danach) zählen nicht.
- **W100 +/− nicht mehr träge:** Nach jedem erkannten Tastendruck wird der Sollwert sofort ans Gerät zurückgeschrieben,
  auch wenn Home Assistant den Wert schon hat – erst dann aktualisiert das W100 sein Display.
- Vorhandene Bedienteile werden übernommen: W100 + / − bleiben wärmer / kälter, Taster behalten ihre Zuordnung.
  **Die Mitteltaste des W100 bitte einmal neu anlernen.**
- Websocket `home_rhythm/control/learn` (start / result / cancel, nur Admins) ersetzt `control/last_action`.

## 0.9.6.2 – W100: Tastendrücke zuverlässig und sofort
- Fehler 0.9.6: Ein Tastendruck um 0,5 °C kurz nach einem eigenen Befehl galt als „gerundete Rückmeldung“ und wurde
  ignoriert (Anzeige sprang zurück). Jetzt ist nur der exakt gleiche Wert ein Echo.
- Geräte mit Tastendruck-Meldung (Aqara W100 `PMTSD_from_W100_Data`): Tastendruck nur, wenn die Meldung einen Anhang
  mit dem neuen Wert hat (`…_TW21`); dann wird er sofort übernommen, ohne 3 s Wartezeit. Meldungen ohne Anhang zählen nicht.

## 0.9.6.1 – W100 als Bedienteil und Raumsensor
- Bedienteile wie das Aqara W100 (Thermostat-Entität mit „thermostat_mode“ am Gerät oder als Bedienteil eingetragen)
  erscheinen nicht mehr in der Thermostat-Liste des Raums, stehen bei „+ Bedienteil mit Anzeige“ oben, und ihre
  Temperatur ist wieder als Raumsensor wählbar (wurde in 0.9.5.1 versehentlich mit ausgefiltert).

## 0.9.6 – Bedienteile und Ventil-Zustand
- **Bedienteile je Raum** (Raum bearbeiten → Schritt 4, mehrere möglich). Sie lösen eine Hand-Änderung für den Raum
  aus – Home Rhythm gibt sie an jede Art von Thermostat weiter (FRITZ!DECT, Better Thermostat, Integration, direkt).
  - **Mit Anzeige** (Thermostat-Entität ohne Ventil, z. B. Aqara W100 im Thermostat-Modus): zeigt den Sollwert des
    Raums (Schrittweite vom Gerät). Sollwert am Gerät geändert = Hand-Änderung. Kein Tastendruck sind: nur neue
    Messwerte, eigene Befehle, gerundete Rückmeldungen (60 s), Werte beim Wiedererreichen des Geräts; meldet das Gerät
    einen Tastendruck-Zeitpunkt (W100: PMTSD), muss der sich mit ändern. Ein/Aus am Gerät = Mitteltaste: zurück zum
    Plan · aus bis zum nächsten Wechsel · nichts.
  - **Taster** (Ereignis-Entität, z. B. SNZB-01/01M, Hue Dimmer, IKEA): Zuordnung Tastendruck → wärmer · kälter (0,5/1 °C)
    · zurück zum Plan · Booster 1 Std. · Komfort · aus bis zum nächsten Wechsel. „Taste drücken zum Zuordnen“ im Editor.
- **Ventil-Zustand** in der Thermostat-Zeile: „heizt – Ventil auf“ / „Ventil zu“, seit wann, Anteil der letzten
  Stunde (vom Gerät, z. B. Sonoff `heat_percentage_hour`, sonst selbst gezählt). Hinweis, wenn über 1 Std. geheizt wird
  und der Raum kaum wärmer wird.
- Dienst: neue Websocket-Funktion `home_rhythm/control/last_action` (nur Admins).

## 0.9.5.1 – Raumsensor nicht mehr fälschlich „ohne Wert“
- Sensoren, die sich nur bei Änderungen melden, galten nach 2 Std. gleicher Temperatur als ausgefallen – dann wurde
  nichts mehr ans Thermostat gesendet. Jetzt zählt ein Sensor nur nicht, wenn er „nicht verfügbar“ ist oder seit
  12 Std. nichts gemeldet hat. Neu nur als Hinweis: „seit über 3 Std. derselbe Wert, obwohl geheizt wird“.
- Sensorauswahl im Raum zeigt nur noch echte Raumsensoren: keine Werte von Thermostat-Geräten (Fühler, Komfort-/
  Eco-/nächste geplante Temperatur) und keine Rechenwerte von Better/Versatile Thermostat.

## 0.9.5 – Raum einrichten Schritt für Schritt: Art, Raumsensoren, Korrektur
Bestehende Räume verhalten sich unverändert: Sie bekommen automatisch ihre Art (Better Thermostat, Versatile
Thermostat → andere Regel-Integration, FRITZ!DECT, sonst Thermostat direkt), „Fühler am Thermostat“ und keine Korrektur.
- **1 · Art je Raum:** FRITZ!DECT · Better Thermostat · andere Regel-Integration · Thermostat direkt (Sonoff & Co.).
  Die Liste zeigt die Thermostate dieser Art im Bereich (Klimaanlagen immer).
- **2 · Sensoren:** Fühler am Thermostat · Sensoren im Raum (mehrere = Durchschnitt; ohne Meldung seit 2 Std. zählen
  sie nicht) · bei FRITZ!DECT „in der Fritz!Box eingestellt“ (z. B. FRITZ!DECT 440, nur Anzeige). Bei BT/Integration
  zeigt Home Rhythm den dort eingetragenen Sensor.
- **3 · Korrektur:** keine · fest ± °C (wie der Versatz in der Fritz!Box; Hand-Änderung am Gerät wird zurückgerechnet)
  · beobachten (FRITZ!DECT mit Raumsensor: misst die Abweichung Fühler ↔ Raum bei geschlossenem Ventil, ändert nichts;
  Export als CSV). **Thermostat direkt mit Raumsensor:** Home Rhythm schickt den Raumwert an den Eingang für externe
  Temperatur (z. B. Sonoff TRVZB / TRV Gen2 über Zigbee2MQTT, bei Änderung und spätestens alle 10 min) und stellt die
  Quelle auf „remote“.
- **Raumansicht:** Art / misst mit / Korrektur und Hinweise ⚠: Sensor aus anderem Bereich (auch der Sensor von BT),
  Sensoren liegen > 2 °C auseinander, Sensor meldet nichts, Thermostat auf eigenen Fühler zurückgefallen, steht auf „auto“.
- Ist-Temperatur des Raums = Raumsensor(en) bzw. Fritz!Box-Sensor, wenn eingestellt.

## 0.9.4 – „Heute“ als Auswahlfenster, Ausnahme mit Beginn und Ende
- **„Heute: … ▾“** öffnet ein Fenster statt fünf Knöpfen: alle wählbaren Stufen (auch eigene, z. B. Homeoffice) mit
  Zeitraum **von** jetzt / Uhrzeit / anderer Tag **bis** Tagesende / Uhrzeit / späterer Tag – z. B. Homeoffice 14:00–21:23.
  Außerhalb gilt der Plan. Balken und Satz zeigen sofort, wie der Tag aussieht.
- Neu „wie Mo–Fr“; „wie Sonntag“, „wie Mo–Fr“ und „niemand im Raum“ gelten nur heute, heute und morgen oder bis
  einschließlich Datum. „Komfort den ganzen Tag“ ist jetzt die Stufe Komfort (Auswahl-Entität kennt ihn weiter).
- Je Raum genau eine Ausnahme. Geplante Ausnahmen: ⏱ in der Raumzeile, Woche zeigt sie schon; mit ihrem Beginn endet
  eine laufende Hand-Änderung. Hand-Änderung während der Ausnahme gilt bis zu deren Ende. Kühlen nach „Raum belegt“.
- Dienste `home_rhythm.set_exception` (Raum, Stufe, Beginn, Ende – Namen genügen) und `home_rhythm.clear_exception`.
- Enthält alles aus 0.9.3.

## 0.9.3 – Fritz!DECT: keine 28 °C mehr durch Werte von außen, Start-Reiter
- **Höchstwert ohne HA-Ursache wird nicht mehr als Hand-Änderung übernommen**: Meldet ein Thermostat von sich aus
  seinen Höchstwert oder „dauerhaft an“ (HA zeigt bei Fritz!DECT dann 30 °C), wird das weder als Hand-Änderung
  gemerkt noch an die anderen Thermostate des Raums weitergegeben (vorher: alle auf 28 °C). Nach 10 min setzt
  Home Rhythm den Plan wieder. Wer den Wert in HA bewusst einstellt, bekommt weiterhin eine Hand-Änderung.
- **Träge Fritz!DECT**: Meldet ein Gerät bis zu 15 min nach einem Befehl noch einmal den alten Wert, gilt das als
  Rückmeldung, nicht als Hand-Änderung „am Gerät / extern“ (vorher nur 3 min).
- Liste „Zuletzt von außen geändert“: „dauerhaft an“ statt „30 °C“, Vermerk „nicht übernommen (Höchstwert)“.
- **Start-Reiter** einstellbar (Einrichtung → Weiteres): Übersicht, Heizung & Klima, Abläufe, Geräte oder Einrichtung.
  `view:` in der Kartenkonfiguration hat weiterhin Vorrang.
- Hinweis Better Thermostat mit Fritz!DECT: Kalibrierungsmodus „KI zeitbasiert“ dreht das Thermostat bis 28 °C auf.
  Mit externem Sensor „Nur externer Sensorversatz“, ohne externen Sensor „Keine Kalibrierung“ wählen.

## 0.9.2 – Zeitplan-Editor wie im Entwurf
- **Tage, an denen „Zeitplan gilt“ nicht zutrifft, sind in der Woche schraffiert** und mit „ruht“ beschriftet
  (vorher zeigten die Balken z. B. bei Weihnachten im November trotzdem Schaltzeiten).
- Farbpunkte je Tagesart in den Zeilen und neben jedem Tag der Woche (wie im Entwurf).
- „▲ Öffnen“ / „▼ Schließen“ in einer Zeile mit den Feldern; bei „alle Tage“ keine doppelte Beschriftung mehr;
  Absicherung sauber in einer Zeile.
- „Zeitplan gilt“: neue Kurzauswahl „nur zu Weihnachten (1. Advent – 6. Januar)“.
- Hinweis bei Rollläden: Hitzeschutz nach Temperatur ist eine Reaktion, zeitgesteuerter Hitzeschutz ein eigener Zeitplan.
- Gleich benannte Geräte im Editor zeigen zusätzlich ihre Entitäts-ID.

## 0.9.1
- **Behoben:** In 0.9.0 fehlten die Wochenbalken der Heizung (Raum-Editor und Raumdetails). Ursache: eine neue Funktion
  für die Ablauf-Vorschau hatte denselben Namen wie die der Heizung und hat sie überschrieben. Die Heizungsregeln selbst
  waren nicht betroffen. Ein Test prüft jetzt, dass es keine doppelten Funktionsnamen in der Karte gibt.
- Legende der Heizungswoche: „*“ = anderer Plan als sonst (Feiertag, Urlaub zu Hause, „wie Sonntag“).

## 0.9.0 – Zeitpläne „Einfach“ und Voraussetzungen
- **Zeitpläne im einfachen Modus (Standard), wie bei der Heizung:** Zeiten je Tagesart – Mo–Fr, Samstag
  (wie Mo–Fr / eigene), Sonntag (wie Mo–Fr / wie Samstag / eigene), Feiertag (wie Mo–Fr / Sa / So / eigene),
  Urlaub zu Hause an Werktagen und am Wochenende (je mit „wie …“), mit Erklärsatz. Vorrang fest:
  Feiertag vor Urlaub zu Hause vor Wochentag.
  - Öffnen: Uhrzeit oder Sonne ± (mit „frühestens“), ganz auf oder auf Position %; Licht: einschalten (mit Helligkeit).
  - Schließen: eine Zeit für alle Tage oder je Tagesart; eine Schließzeit vor der Öffnungszeit (z. B. 00:30)
    gilt als „nach Mitternacht“ und gehört zum Vorabend.
  - Absicherung („um 23:00 nochmal schließen, falls nötig“), „nur falls nötig“, „nachprüfen“ für den ganzen Plan.
  - „Zeitplan gilt“: immer / nicht bei „Urlaub unterwegs“ / nur in Jahreszeit … / eigene Bedingungen, mit Anzeige
    „gilt gerade / ruht gerade“.
- **Erweitert** = der bisherige Schaltpunkt-Editor. Umschalten übernimmt die Schaltpunkte; zurück zu „Einfach“ geht,
  solange sie nicht verändert wurden. Bestehende Zeitpläne bleiben im erweiterten Modus.
  Neu dort: Tage „Tagesarten“ (auch „zählt zum Vorabend“).
- **Wochenvorschau richtig:** Die Woche wird als Kreis gerechnet (Montag früh beginnt mit dem letzten Befehl, nicht
  mit „offen“); bei jedem Tag steht, was gilt („Feiertag → wie Sonntag“); Uhrzeiten ▲/▼ unter jedem Balken;
  ☀ = nach Sonne, grauer Strich = Absicherung, roter Strich = jetzt; „schaltet nie“ schraffiert.
  Woche simulieren: Feiertag am Mittwoch, Urlaub zu Hause, Urlaub unterwegs, Heißphase.
- **Versatz immer mit Einheit** (min / Std.) und „heute ≈ 18:32“ daneben – „+1“ heißt nicht mehr heimlich 1 Minute.
- **Heizung:** Feiertag und „Urlaub zu Hause“ heizen wählbar wie Mo–Fr, Samstag oder Sonntag
  (Einstellungen → Hausmodi; Standard wie bisher Sonntag).
- **Neue Kachel „Voraussetzungen“** (Einrichtung): Jahreszeit, Urlaub, Workday, Anwesenheit, Außentemperatur –
  vorhanden / fehlt / bewusst ohne. Helfer per Klick anlegen (normaler HA-Helfer), Vorhandenes übernehmen,
  Workday über den HA-Dialog einrichten (wird danach automatisch übernommen) oder „ohne“. Fehlt etwas, steht oben in
  der Übersicht ein Hinweis. „Jahreszeit automatisch“ ist dort mit erklärt.
- **Neuinstallation ohne fest eingebaute Entitätsnamen:** Die Einrichtung schlägt nur vor, was es wirklich gibt.
- Doppelte Gerätenamen („Rollladen Arbeitszimmer EG Arbeitszimmer EG Rollladen“) werden gekürzt; Schaltpunkt-Zeilen überlappen auf
  dem Tablet nicht mehr.

## 0.8.2
- **Schnellbedienung in der Ablauf-Liste:** Klick auf das Symbol am Zeilenanfang – bei einem Gerät öffnet sich der
  Gerätedialog, bei mehreren eine Leiste mit „alle öffnen/schließen“ bzw. „alle an/aus“ und den einzelnen Geräten.
  Gilt wie eine Hand-Änderung bis zum nächsten Schaltpunkt; steht im Protokoll. Auch für Nicht-Admins.
- **Neuer Schritt „umschalten“** in Reaktionen (an↔aus bzw. Rollladen auf↔zu).
- **Warnblinken einstellbar:** 1–10 Durchgänge, Tempo 0,3 / 0,5 / 1 / 2 s; jetzt auch in der HA-Automation identisch.
- **Warten in Sekunden oder Minuten** (z. B. 0,3 min = 18 s).
- **Suche nach Geräteart:** „Bewegung“ findet auch Melder mit englischem Namen („… occupancy“); auch Tür/Fenster,
  Leistung, Helligkeit u. a. Entitäten ohne Registry-Eintrag werden angeboten.
- Feld „Hell. %“ nur noch, wenn Lampen im Zeitplan sind; Aktion bleibt lesbar. „nur falls nötig“ und
  „nachprüfen & wiederholen“ mit Erklärung direkt im Editor (auch auf dem Handy).

## 0.8.1
- **Gerätesuche im Ablauf-Editor:** Statt exakter Entitäts-IDs reicht ein Teil von Name, Raum oder Art
  (z. B. „bad roll“). Die Trefferliste zeigt Symbol, Name, Raum und ID; Pfeiltasten + Enter oder Klick übernehmen.
  Gilt für Geräte, Auslöser, Bedingungen und „warten bis …“. Für Zustände gibt es Vorschläge (an/aus, offen/zu …).

## 0.8.0 – Abläufe
- **Neu: Abläufe.** Zeitpläne für frei zusammengestellte Rollläden, Lampen und Steckdosen (Uhrzeit oder Sonne ± Minuten,
  frühestens/spätestens, Arbeitstag/freier Tag/Wochentage, „nur falls nötig“, „nachprüfen & wiederholen“,
  Urlaubssimulation, Überspringen) und Reaktionen (Wenn → Dann mit Warten, Nachlauf, Warnblinken, Nachricht).
- Bedingungen mit **UND/ODER-Gruppen**, auch mit beliebigen Entitäten und dem Zustand anderer Zeitpläne.
- Optional **als Home-Assistant-Automation** anlegen (automations.yaml, mit Sicherung).
- **Neue Aufteilung der Karte:** Übersicht mit Zeitleiste und Vorschau auf ein Datum, Heizung & Klima, Abläufe,
  Geräte, Einrichtung; ⚙️ öffnet die Integration; Kacheldarstellung.
- ✕ am „Hand“-Schild setzt eine Hand-Änderung sofort zurück.
- Simulation der Hausmodi für Zeitpläne; Sicherung (Export/Import).
- Datenschutz: Beim Löschen der Integration werden gespeicherte Daten und angelegte Automationen entfernt.
- Die Rollläden-/Licht-Einstellungen in Räumen aus 0.7.0 entfallen (jetzt als Abläufe).

## 0.7.0
- Rollläden, Licht und Steckdosen pro Raum (ersetzt durch Abläufe in 0.8.0), Ansicht „Bereiche“.
- Luftfeuchte: BT/VT-Sensor → Thermostat (FRITZ!DECT) → Raumsensor. Großes Logo.

## 0.6.x
- Logo, Thermostat-Dialog aus der Raumzeile, Verlauf, eigene Stufen, „Booster“, Luftfeuchte, Reiter „Geräte“,
  zusammenklappbare Hausmodi.

## 0.5.0 / 0.6.0
- Kühlen, fremde Steuerung erkennen, Hausmodi automatisch (Jahreszeit), Ereignis, Anlass, „Heute anders“, Raumregeln.

## 0.4.x
- Klimaanlage als zweite Wärmequelle (Gas oder Strom – was ist billiger?), Versatile Thermostat.

## 0.1.0 – 0.3.0
- Heizung nach Hausmodi und Wochenplan, mehrere Thermostate pro Raum, Better Thermostat.
