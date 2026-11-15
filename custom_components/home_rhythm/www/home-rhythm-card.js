/* Home Rhythm – Karte für Home Assistant (ohne Build-Schritt, ohne Abhängigkeiten). */
(() => {
  const VERSION = "0.9.14";
  const DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  const DAY_TYPES = [["wd", "Mo–Fr"], ["sa", "Samstag"], ["so", "So / Feiertag"]];
  const COLORS = {
    komfort: "#e8833a", absenkung: "#6fa3c9", nacht: "#4b5d8f", bad: "#d4505e",
    extra1: "#2bb3a3", extra2: "#c4a21a", extra3: "#d26fa8", extra4: "#8d6e63",
    urlaub: "#7fb563", hand: "#a77bd6", aus: "#9e9e9e", kuehlen: "#2f8fd6", vorkuehlen: "#8cc8ef",
  };
  const RT_KINDS = [["fritz", "FRITZ!DECT"], ["bt", "Better Thermostat"], ["integration", "andere Regel-Integration"], ["direct", "Thermostat direkt (Sonoff & Co.)"]];
  const RT_KIND_HINT = {
    fritz: "Fritz-Thermostate, die Home Rhythm direkt steuert.",
    bt: "Better Thermostat regelt; Home Rhythm setzt nur den Sollwert.",
    integration: "z. B. Versatile Thermostat – die Integration regelt; Home Rhythm setzt nur den Sollwert.",
    direct: "Zigbee- und andere Thermostate, die Home Rhythm direkt steuert – auch mit Raumsensor.",
  };
  const MANUAL_MODES = [["next", "bis zum nächsten Wechsel im Plan"], ["30", "30 Minuten"], ["60", "1 Stunde"], ["120", "2 Stunden"], ["240", "4 Stunden"]];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  /** Angelernte Taste lesbar (Signatur aus der Integration, siehe controls.py). */
  const sigLabel = (sig) => {
    const [kind, ent, ...rest] = String(sig).split(":"); const val = rest.join(":");
    const pretty = (a) => String(a).replace(/_/g, " ").replace(/\bbutton (\d)/, "Taste $1").replace(/^single /, "1× · ").replace(/^double /, "2× · ").replace(/^triple /, "3× · ").replace(/^(long|hold) /, "halten · ");
    return ({ event: pretty(val), action: pretty(val), up: "Sollwert + (hoch)", down: "Sollwert − (runter)", mode: `Ein/Aus → ${val}`, plain: "Taste ohne Wert (Mitteltaste)" })[kind] || sig;
  };
  const fmtTemp = (t) => (t === null || t === undefined || t === "" ? "–" : `${Number(t).toLocaleString("de-DE", { maximumFractionDigits: 1 })} °`);
  let NOW_REF = null; // Zeit von Home Assistant (für „heute/morgen“)
  const fmtTime = (iso) => {
    if (!iso) return "";
    const d = new Date(iso), now = NOW_REF ? new Date(NOW_REF) : new Date();
    const hm = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    const days = Math.round((new Date(d.toDateString()) - new Date(now.toDateString())) / 864e5);
    if (days === 0) return hm;
    if (days === 1) return `morgen ${hm}`;
    if (days === -1) return `gestern ${hm}`;
    return `${d.toLocaleDateString("de-DE", { weekday: "short" })} ${hm}`;
  };
  const normTime = (v) => {
    const s = String(v || "").trim().replace(/[.,h ]/g, ":");
    let h, m;
    if (s.includes(":")) [h, m] = s.split(":");
    else if (/^\d{1,2}$/.test(s)) [h, m] = [s, "0"];
    else if (/^\d{3,4}$/.test(s)) [h, m] = [s.slice(0, -2), s.slice(-2)];
    else return null;
    h = Number(h); m = Number(m || 0);
    if (!Number.isInteger(h) || !Number.isInteger(m) || m < 0 || m > 59 || h < 0 || h > 24 || (h === 24 && m)) return null;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  };
  const copAt = (pts, t) => {
    const p = [...pts].sort((a, b) => a[0] - b[0]);
    let a, b;
    if (t <= p[0][0]) [a, b] = [p[0], p[1]];
    else if (t >= p[p.length - 1][0]) [a, b] = [p[p.length - 2], p[p.length - 1]];
    else for (let i = 0; i < p.length - 1; i++) if (p[i][0] <= t && t <= p[i + 1][0]) { [a, b] = [p[i], p[i + 1]]; break; }
    return Math.max(a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0]), 0.5);
  };
  const acThreshold = (pts, be) => {
    if (copAt(pts, 30) < be) return null;
    if (copAt(pts, -30) >= be) return -30;
    let lo = -30, hi = 30;
    for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; if (copAt(pts, m) >= be) hi = m; else lo = m; }
    return Math.round(hi * 10) / 10;
  };
  const fmtNum = (v, d = 1) => (v == null ? "–" : Number(v).toLocaleString("de-DE", { maximumFractionDigits: d }));
  const AC_MODES = [["auto", "automatisch – billigere Quelle"], ["ac", "Klima bevorzugt"], ["radiator", "immer Heizkörper (Klima aus)"]];
  const WORDMARK = `<svg class="hrword" viewBox="14 22 2812 754" fill="currentColor" role="img" aria-label="Home Rhythm"><path fill="#faaf40" d="M932.36,383.13L476.11,27.59,19.86,383.13l131.46,3.42,5.88,315.73c42.41-131.84,166.07-227.25,312-227.25s262.05,89.69,307.9,215.32l-4.59-309.63,159.85,2.41ZM469.2,409.08h-92.66v-92.66h92.66v92.66ZM469.2,302.61h-92.66v-92.64h92.66v92.64ZM575.67,409.08h-92.66v-92.66h92.66v92.66ZM575.67,302.61h-92.66v-92.64h92.66v92.64Z"/><g><path fill="#faaf40" fill-rule="evenodd" d="M313.83,524.54h0c3.62-2.09,8.29-.83,10.38,2.79l37.06,64.19c2.1,3.63.84,8.29-2.78,10.39-3.63,2.09-8.29.84-10.39-2.79l-37.06-64.19c-2.09-3.62-.84-8.29,2.79-10.39"/><path fill="#faaf40" fill-rule="evenodd" d="M205.64,632.73h0c2.1-3.63,6.77-4.88,10.39-2.79l64.19,37.06c3.63,2.1,4.88,6.77,2.79,10.39-2.09,3.63-6.76,4.88-10.39,2.78l-64.2-37.06c-3.62-2.09-4.87-6.76-2.78-10.38Z"/><path fill="#faaf40" fill-rule="evenodd" d="M717.57,632.73h0c2.09,3.62.84,8.29-2.78,10.38l-64.2,37.06c-3.62,2.1-8.29.85-10.39-2.78-2.09-3.63-.84-8.29,2.79-10.38l64.19-37.07c3.63-2.09,8.3-.84,10.39,2.79Z"/><path fill="#faaf40" fill-rule="evenodd" d="M609.38,524.54h0c3.62,2.1,4.87,6.77,2.79,10.39l-37.06,64.19c-2.09,3.63-6.77,4.88-10.39,2.79-3.62-2.09-4.88-6.76-2.78-10.39l37.06-64.19c2.1-3.62,6.76-4.88,10.38-2.79Z"/><path fill="#faaf40" fill-rule="evenodd" d="M461.6,484.94h0c4.18,0,7.6,3.42,7.61,7.6v74.14c0,4.18-3.43,7.6-7.61,7.6s-7.6-3.42-7.6-7.6v-74.14c0-4.18,3.42-7.6,7.6-7.6Z"/><path fill="#faaf40" fill-rule="evenodd" d="M386.34,499.6c-1.51.4-2.42,1.99-2.02,3.5l10.97,40.91c1.82-.51,3.67-1,5.51-1.47l-10.96-40.92c-.4-1.51-1.99-2.42-3.5-2.02Z"/><path fill="#faaf40" fill-rule="evenodd" d="M255.97,574.87c-1.11,1.11-1.11,2.93,0,4.04l30.01,30c1.33-1.36,2.68-2.71,4.04-4.04l-30-30c-1.11-1.11-2.93-1.11-4.04,0Z"/><path fill="#faaf40" fill-rule="evenodd" d="M742.51,705.24c-.41-1.5-2-2.42-3.5-2.02l-40.92,10.96c.51,1.83,1.01,3.67,1.48,5.51l40.92-10.96c1.5-.4,2.42-1.99,2.02-3.5Z"/><path fill="#faaf40" fill-rule="evenodd" d="M667.24,574.87c-1.11-1.11-2.93-1.11-4.04,0l-30,30c1.35,1.33,2.7,2.68,4.03,4.04l30-30c1.11-1.11,1.11-2.94,0-4.04Z"/><path fill="#faaf40" fill-rule="evenodd" d="M225.12,714.19l-40.92-10.97c-1.51-.4-3.1.52-3.5,2.02-.41,1.5.51,3.1,2.02,3.5l40.92,10.96c.47-1.85.96-3.69,1.48-5.51Z"/><path fill="#faaf40" fill-rule="evenodd" d="M536.87,499.6c-1.51-.41-3.09.51-3.5,2.02l-10.96,40.92c1.85.47,3.69.96,5.52,1.48l10.96-40.92c.4-1.51-.52-3.1-2.02-3.5Z"/></g><g><path d="M859.31,442.82v108.35h135.71v-108.35h17.51v245.88h-17.51v-122.94h-135.71v122.94h-17.51v-245.88h17.51Z"/><path d="M1114.31,692.72c-45.24,0-80.26-35.39-80.26-90.11,0-59.83,39.4-93.03,82.81-93.03,48.52,0,81.35,36.48,81.35,90.11,0,64.94-44.87,93.03-83.54,93.03h-.36ZM1115.4,678.12c36.48,0,65.3-32.83,65.3-77.7,0-32.1-17.88-76.25-64.21-76.25s-64.94,39.76-64.94,77.34c0,43.78,27.73,76.61,63.48,76.61h.37Z"/><path d="M1218.65,555.55c0-16.05-.37-28.09-1.46-41.95h16.42l1.09,30.64h.73c11.31-20.06,28.09-34.66,56.91-34.66,24.08,0,42.68,16.05,50.34,37.94h.73c4.74-10.21,11.31-18.24,17.88-23.71,11.31-9.12,22.98-14.23,41.59-14.23,17.15,0,57.27,9.48,57.27,75.88v103.24h-17.51v-101.78c0-39.4-15.32-62.75-45.6-62.75-21.89,0-39.04,16.42-45.97,34.66-1.46,5.11-2.92,10.94-2.92,17.51v112.36h-17.51v-109.81c0-31.37-14.96-54.72-43.41-54.72-23.35,0-41.95,18.97-48.52,39.4-1.46,5.11-2.55,10.94-2.55,17.15v107.98h-17.51v-133.15Z"/><path d="M1496.99,599.33c0,55.82,30.64,78.07,66.76,78.07,25.54,0,38.67-5.11,48.52-9.85l4.38,13.5c-6.57,3.65-24.44,11.31-55.09,11.31-50.34,0-81.72-36.48-81.72-87.92,0-58.37,33.56-94.85,78.8-94.85,57.27,0,68.22,53.99,68.22,79.16,0,4.74,0,7.3-.73,10.58h-129.14ZM1608.62,585.46c.36-24.44-9.85-61.29-52.17-61.29-38.67,0-55.09,34.29-58.37,61.29h110.54Z"/><path d="M1659.51,446.47c17.15-3.28,41.95-5.47,67.85-5.47,35.39,0,59.1,5.84,75.88,19.7,13.5,11.31,21.16,28.46,21.16,49.61,0,31.74-21.52,53.26-44.87,61.29v1.09c17.88,6.57,28.46,23.71,34.29,47.42,8.03,30.64,14.59,59.1,19.33,68.58h-45.97c-3.65-7.3-9.85-27.36-16.42-58-7.3-32.1-18.6-42.32-44.14-43.05h-22.62v101.05h-44.51v-242.23ZM1704.02,554.82h26.63c30.28,0,48.88-16.05,48.88-40.49,0-26.63-18.61-39.4-47.79-39.4-14.23,0-23.35,1.09-27.72,2.19v77.7Z"/><path d="M1859.39,429.33h44.87v105.79h.73c5.47-8.39,13.13-15.32,22.25-20.06,9.12-5.11,19.7-8.03,31.01-8.03,30.28,0,62.02,20.06,62.02,76.97v104.7h-44.87v-99.96c0-25.54-9.49-45.24-34.29-45.24-17.51,0-29.91,11.67-35.02,25.17-1.46,4.01-1.82,8.75-1.82,13.5v106.52h-44.87v-259.38Z"/><path d="M2080.64,511.04l31.74,95.21c3.65,10.94,7.66,24.44,10.21,34.29h1.09c2.55-9.85,5.84-23.35,9.49-34.66l27.73-94.85h47.79l-44.51,121.12c-24.44,66.39-40.86,95.94-61.65,114.18-17.88,15.32-36.12,21.16-47.06,22.62l-10.21-37.58c7.66-1.82,16.78-5.84,25.9-12.4,8.39-5.47,18.61-16.05,24.81-28.09,1.46-3.28,2.55-5.84,2.55-8.03,0-1.82-.37-4.38-2.19-8.75l-65.3-163.07h49.61Z"/><path d="M2289.79,465.44v45.6h42.68v33.56h-42.68v78.07c0,21.89,5.84,32.83,22.98,32.83,8.03,0,12.4-.37,17.51-1.82l.73,33.93c-6.57,2.55-18.61,4.74-32.47,4.74-16.78,0-30.28-5.47-38.67-14.59-9.85-10.21-14.23-26.63-14.23-49.98v-83.18h-25.17v-33.56h25.17v-33.2l44.14-12.4Z"/><path d="M2357.39,429.33h44.87v105.79h.73c5.47-8.39,13.13-15.32,22.25-20.06,9.12-5.11,19.7-8.03,31.01-8.03,30.28,0,62.02,20.06,62.02,76.97v104.7h-44.87v-99.96c0-25.54-9.49-45.24-34.29-45.24-17.51,0-29.91,11.67-35.02,25.17-1.46,4.01-1.82,8.75-1.82,13.5v106.52h-44.87v-259.38Z"/><path d="M2556.87,563.94c0-20.43-.73-37.58-1.46-52.9h38.3l2.19,26.27h1.09c8.39-13.86,24.44-30.28,54.72-30.28,23.35,0,41.59,13.13,49.25,32.83h.73c6.2-9.85,13.5-17.15,21.52-22.25,10.21-6.93,21.52-10.58,36.48-10.58,29.18,0,59.1,20.06,59.1,76.97v104.7h-43.78v-98.13c0-29.55-10.21-47.06-31.74-47.06-15.32,0-26.63,10.94-31.37,23.71-1.46,4.01-2.19,9.85-2.19,14.96v106.52h-43.78v-102.88c0-24.81-9.85-42.32-30.64-42.32-16.78,0-28.09,13.13-32.47,25.17-1.46,4.74-2.19,9.85-2.19,14.96v105.06h-43.78v-124.76Z"/></g></svg>`;
  const LOGO = `<svg class="hrlogo" viewBox="12 118 928 706" aria-hidden="true"><path fill="#faaf40" d="M932.36,482.22L476.11,126.67,19.86,482.22l131.46,3.42,5.88,315.73c42.41-131.84,166.07-227.25,312-227.25s262.05,89.69,307.9,215.32l-4.59-309.63,159.85,2.41ZM469.2,508.17h-92.66v-92.66h92.66v92.66ZM469.2,401.69h-92.66v-92.64h92.66v92.64ZM575.67,508.17h-92.66v-92.66h92.66v92.66ZM575.67,401.69h-92.66v-92.64h92.66v92.64Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M319.37,626.54h0c3.49-2.01,7.98-.8,9.99,2.68l35.67,61.79c2.02,3.49.81,7.98-2.68,10-3.49,2.01-7.98.81-10-2.68l-35.67-61.78c-2.01-3.48-.81-7.98,2.68-10"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M215.24,730.67h0c2.02-3.49,6.51-4.69,10-2.68l61.79,35.67c3.49,2.02,4.69,6.51,2.68,10-2.02,3.49-6.51,4.69-10,2.68l-61.79-35.67c-3.48-2.01-4.69-6.51-2.68-9.99Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M707.97,730.67h0c2.01,3.48.81,7.98-2.68,9.99l-61.79,35.67c-3.49,2.02-7.98.81-10-2.68-2.01-3.49-.81-7.98,2.68-9.99l61.79-35.68c3.49-2.01,7.99-.81,10,2.68Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M603.84,626.54h0c3.49,2.02,4.69,6.52,2.68,10l-35.67,61.78c-2.02,3.49-6.51,4.69-10,2.68-3.48-2.02-4.69-6.51-2.68-10l35.67-61.79c2.02-3.49,6.5-4.69,9.99-2.68Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M461.6,588.43h0c4.03,0,7.32,3.29,7.32,7.32v71.36c0,4.03-3.3,7.32-7.32,7.32s-7.32-3.29-7.32-7.32v-71.36c0-4.03,3.29-7.32,7.32-7.32Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M389.16,602.54c-1.45.38-2.33,1.92-1.95,3.37l10.56,39.38c1.76-.49,3.53-.97,5.31-1.42l-10.55-39.39c-.39-1.45-1.92-2.33-3.37-1.94Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M263.68,674.99c-1.07,1.07-1.07,2.82,0,3.89l28.88,28.88c1.28-1.31,2.58-2.61,3.89-3.89l-28.88-28.88c-1.07-1.07-2.82-1.07-3.89,0Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M731.98,800.46c-.39-1.44-1.93-2.33-3.37-1.94l-39.39,10.55c.49,1.76.97,3.53,1.42,5.31l39.39-10.55c1.45-.39,2.33-1.92,1.95-3.37Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M659.53,674.99c-1.07-1.07-2.82-1.07-3.89,0l-28.87,28.88c1.3,1.28,2.6,2.58,3.88,3.89l28.88-28.88c1.07-1.07,1.07-2.83,0-3.89Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M233.99,809.08l-39.39-10.56c-1.45-.38-2.98.5-3.37,1.95-.39,1.44.49,2.98,1.94,3.37l39.38,10.55c.45-1.78.93-3.55,1.43-5.31Z"/><path fill="#faaf40" stroke="#faaf40" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" d="M534.05,602.54c-1.45-.39-2.98.49-3.37,1.94l-10.55,39.39c1.78.45,3.55.93,5.31,1.43l10.55-39.39c.39-1.45-.5-2.98-1.95-3.37Z"/></svg>`;
  const SCOL = { open: "#f2c94c", closed: "#4b5d8f", pos: "#8fb3cf", on: "#faaf40", off: "var(--divider-color)",
    none: "repeating-linear-gradient(135deg,#b8bcc4 0 4px,#e3e5e9 4px 8px)" };
  const DT_COLOR = { mf: "#0277bd", sa: "#6a4fb3", so: "#8e5a00", hol: "#b3261e", vacwd: "#2e7d32", vacwe: "#2e7d32" };
  const dtColorOf = (label) => /^ruht/.test(label) ? "#9aa0a6" : /^Mo–Fr|^Arbeitstag/.test(label) ? DT_COLOR.mf : /^Samstag/.test(label) ? DT_COLOR.sa
    : /^Sonntag/.test(label) ? DT_COLOR.so : /^Feiertag/.test(label) ? DT_COLOR.hol : /^Urlaub/.test(label) ? DT_COLOR.vacwd : "";
  const ACT_ICON = { open: "▲", on: "▲", close: "▼", off: "▼", position: "◆" };
  const CATCOL = { heat: "#e8833a", cover: "#4b5d8f", switch: "#faaf40", react: "#7fb563" };
  const DOMICON = { cover: "🪟", light: "💡", switch: "🔌", input_boolean: "🔘", fan: "🌀", binary_sensor: "📡", sensor: "📈", input_button: "🔘", button: "🔘", event: "⚡", input_select: "📋", lock: "🔒", person: "👤", device_tracker: "📍" };
  const DOMNAME = { cover: "Rollladen", light: "Licht", switch: "Schalter", input_boolean: "Helfer", fan: "Ventilator", binary_sensor: "Melder", sensor: "Messwert", input_button: "Knopf", button: "Knopf", event: "Ereignis", input_select: "Auswahl", lock: "Schloss", person: "Person", device_tracker: "Ortung" };
  const CATNAME = { heat: "Heizung", cover: "Rollläden", switch: "Licht & Steckdosen", react: "Reaktionen" };
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const pad = (n) => String(n).padStart(2, "0");
  const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const minHm = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  // Datum ohne Jahr („MM-TT“, wie gespeichert) – für Zeitraum und bestimmte Tage (0.9.9)
  const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
  const MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const mdParts = (md) => { const x = /^(\d{2})-(\d{2})$/.exec(md || ""); return x ? [Number(x[1]), Number(x[2])] : [1, 1]; };
  const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const mdText = (md) => { const [m, d] = mdParts(md); return `${d}.${m}.`; };
  const mdOk = (md) => { const [m, d] = mdParts(md); return d <= MONTH_DAYS[m - 1]; };
  const mdParse = (txt) => { const x = /^(\d{1,2})\.(\d{1,2})\.?$/.exec(String(txt).trim()); return x ? `${pad(Number(x[2]))}-${pad(Number(x[1]))}` : String(txt).trim(); };
  const mdIn = (md, a, b) => (a <= b ? md >= a && md <= b : md >= a || md <= b);
  const mdSet = (md, part, v) => { let [m, d] = mdParts(md); if (part === "d") d = Number(v); else m = Number(v); return `${pad(m)}-${pad(d)}`; };
  const mdSel = (attrs, md, aria) => {
    const [m, d] = mdParts(md);
    return `<select class="inp md" ${attrs} data-part="d" aria-label="${aria} – Tag">${[...Array(31)].map((_, i) => `<option value="${i + 1}" ${i + 1 === d ? "selected" : ""}>${i + 1}.</option>`).join("")}</select><select class="inp md" ${attrs} data-part="m" aria-label="${aria} – Monat">${MONTHS.map((n, i) => `<option value="${i + 1}" ${i + 1 === m ? "selected" : ""}>${n}</option>`).join("")}</select>`;
  };
  const hhmm = (iso) => new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });

  const STYLE = `
    :host { display:block; --hr-gap:12px; }
    * { box-sizing:border-box; }
    ha-card { overflow:hidden; background:none; box-shadow:none; border:none; }
    ha-card.rcmode { display:block; background:var(--ha-card-background, var(--card-background-color, #fff)); box-shadow:var(--ha-card-box-shadow, none); border:var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0)); border-radius:var(--ha-card-border-radius, 12px); }
    ha-card.rcmode .wrap { padding:14px 16px; }
    /* 0.9.13: Raumknopf – eine Zeile wie eine HA-Kachel (tile) */
    :host([knopf]) { height:100%; }
    ha-card.knopf { height:100%; box-sizing:border-box; display:flex; align-items:center; min-height:56px; }
    ha-card.knopf .wrap { padding:0; width:100%; height:100%; }
    .kn { display:flex; align-items:center; gap:10px; height:100%; min-height:56px; box-sizing:border-box; padding:0 10px; cursor:pointer; -webkit-tap-highlight-color:transparent; outline:none; border-radius:inherit; }
    .kn:focus-visible { box-shadow:inset 0 0 0 2px var(--primary-color); }
    .kico { --kc:#8a8a8a; flex:none; width:36px; height:36px; border-radius:50%; border:none; padding:0; margin:0; display:flex; align-items:center; justify-content:center; cursor:pointer;
      background:color-mix(in srgb, var(--kc) 20%, transparent); color:var(--kc); font-size:18px; line-height:1; transition:transform .1s; }
    span.kico { cursor:default; }
    button.kico:active { transform:scale(.92); }
    .kico ha-icon { --mdc-icon-size:22px; color:var(--kc); }
    .kemo { font-size:18px; line-height:1; }
    .ktx { min-width:0; flex:1; display:flex; flex-direction:column; justify-content:center; }
    .kname { display:flex; align-items:center; gap:4px; min-width:0; font-size:14px; font-weight:500; line-height:20px; color:var(--primary-text-color); }
    .kname .kn1 { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }
    .kname > span:not(.kn1) { flex:none; font-size:12px; }
    .kline { font-size:12px; line-height:16px; color:var(--secondary-text-color); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .kmiss { font-size:12px; color:var(--secondary-text-color); padding:4px 10px; display:flex; align-items:center; min-height:inherit; height:100%; box-sizing:border-box; }
    ha-card.rcmode:not(.knopf) .kmiss { padding:0; height:auto; }
    /* 0.9.13: Fenster-Hosts als <dialog> (Top Layer) – das eigentliche Fenster ist weiterhin .ov > .dlg */
    dialog.hrdlg { padding:0; margin:0; border:none; background:transparent; color:inherit; max-width:none; max-height:none; width:100%; height:100%; inset:0; overflow:visible; }
    dialog.hrdlg:not([open]) { display:none; }
    dialog.hrdlg::backdrop { background:transparent; }
    .rc { display:flex; flex-direction:column; gap:12px; }
    .rcc { flex-direction:row; align-items:center; gap:10px; }
    .rchead { display:flex; align-items:center; gap:10px; }
    .rcico { font-size:22px; background:none; border:none; cursor:pointer; padding:0; line-height:1; }
    .rct .rcico { font-size:28px; }
    .rcname { font:inherit; font-size:18px; font-weight:500; background:none; border:none; padding:0; cursor:pointer; color:var(--primary-text-color); text-align:left; }
    .rct .rcname { font-size:24px; }
    .rcc .rcname { font-size:16px; }
    .rcmid { flex:1; display:flex; flex-direction:column; gap:2px; min-width:0; }
    .rcline { font-size:14px; color:var(--secondary-text-color); }
    .rcc .rcline { font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .rcline.c, .rcrow.c { text-align:center; justify-content:center; }
    .rcist { font-size:14px; color:var(--secondary-text-color); white-space:nowrap; }
    .rcsoll { font-size:20px; font-weight:700; min-width:52px; text-align:center; white-space:nowrap; }
    .rcpm { width:44px; height:44px; flex:none; border-radius:50%; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); font-size:24px; cursor:pointer; }
    .rcpm:disabled { opacity:.4; cursor:default; }
    .rcc .rcpm { width:36px; height:36px; font-size:20px; }
    .rct .rcpm { width:72px; height:72px; font-size:34px; }
    .rcnums { display:flex; align-items:center; justify-content:space-between; }
    .rcv { display:flex; flex-direction:column; gap:2px; }
    .rcv.c { align-items:center; min-width:76px; }
    .rcv small, .rcval small, .rcday small { font-size:13px; color:var(--secondary-text-color); }
    .rcv b { font-size:26px; font-weight:500; }
    .rcv b.big { font-size:30px; font-weight:700; }
    .rcset { display:flex; align-items:center; gap:12px; }
    .rcbig { display:flex; align-items:center; justify-content:center; gap:28px; }
    .rcval { display:flex; flex-direction:column; align-items:center; gap:4px; }
    .rcval b { font-size:56px; font-weight:700; line-height:1; }
    .rcrow { display:flex; }
    .rcback { min-height:36px; padding:0 14px; border-radius:18px; font:inherit; font-size:14px; cursor:pointer; background:var(--secondary-background-color); color:var(--primary-color); border:1px solid var(--divider-color); }
    .rcquick { display:flex; gap:8px; flex-wrap:wrap; }
    .rcquick button, .rcask button { min-height:36px; padding:0 12px; border-radius:18px; font:inherit; font-size:14px; cursor:pointer; background:var(--secondary-background-color); border:1px solid var(--divider-color); color:var(--primary-text-color); }
    .rcquick button.on { border-color:var(--primary-color); color:var(--primary-color); }
    .rct .rcquick { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .rct .rcquick button { min-height:52px; border-radius:12px; font-size:16px; }
    .rcask { display:flex; flex-direction:column; gap:6px; border:1px solid var(--divider-color); border-radius:12px; padding:10px 12px; }
    .rcask > button { text-align:left; border-radius:8px; }
    .rcclock { display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:14px; }
    .rcclock input { width:auto; }
    .rcclock button.pri { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
    .rcday .bar { position:relative; display:flex; height:14px; border-radius:7px; overflow:hidden; }
    .rcday .bar i { flex:1; }
    .rcday .now { position:absolute; top:0; bottom:0; width:2px; background:var(--primary-text-color); }
    .rcday .axis { display:flex; justify-content:space-between; font-size:11px; color:var(--secondary-text-color); }
    .rcvalve { font-size:12px; color:var(--secondary-text-color); }
    .rcmenu { padding:0; }
    .rcdetail { margin-top:10px; border-top:1px solid var(--divider-color); }
    /* Kacheln: alles Zusammengehörige steht auf einer Kachel mit Rand – wie im Entwurf */
    .tile { background:var(--ha-card-background, var(--card-background-color)); border:1px solid var(--divider-color);
      border-radius:var(--ha-card-border-radius, 12px); }
    .list > :last-child, .list > .room:last-child { border-bottom:0; }
    .sech { display:flex; justify-content:space-between; align-items:center; gap:8px; margin:18px 4px 8px; flex-wrap:wrap; }
    .sech h2 { font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--secondary-text-color); margin:0; font-weight:600; }
    .gear { border:1px solid var(--divider-color); background:var(--ha-card-background, var(--card-background-color)); border-radius:10px; width:38px; height:38px; font-size:17px; cursor:pointer; flex:none; }
    .tabs .s { display:none; }
    @media (max-width:640px) { .tabs .l { display:none; } .tabs .s { display:inline; } .title { width:100%; justify-content:space-between; } }
    .wrap { padding:12px 16px 16px; }
    .top { display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; }
    .title { font-size:20px; font-weight:500; display:flex; gap:8px; align-items:center; }
    .tabs { display:flex; gap:4px; background:var(--secondary-background-color); border-radius:10px; padding:3px; }
    .tabs button { border:0; background:none; padding:6px 12px; border-radius:8px; cursor:pointer; color:var(--secondary-text-color); font:inherit; }
    .tabs button.on { background:var(--card-background-color); color:var(--primary-text-color); box-shadow:0 1px 2px rgba(0,0,0,.15); }
    @media (max-width:500px) { .tabs { width:100%; gap:2px; } .tabs button { flex:1; padding:6px 4px; font-size:13px; min-width:0; } }
    .modes { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:8px; margin:12px 0; }
    .mode { background:var(--ha-card-background, var(--card-background-color)); border:1px solid var(--divider-color); border-radius:var(--ha-card-border-radius, 12px); padding:8px 12px; min-width:0; }
    .mode label { display:block; font-size:12px; color:var(--secondary-text-color); margin-bottom:2px; }
    .mode select { width:100%; border:0; background:transparent; font:inherit; color:var(--primary-text-color); padding:2px 0; cursor:pointer; }
    .mode .val { font-weight:500; }
    .filters { display:flex; gap:6px; flex-wrap:wrap; margin:4px 0 8px; }
    .chip { border:1px solid var(--divider-color); background:none; border-radius:16px; padding:4px 12px; font:inherit; font-size:13px; cursor:pointer; color:var(--primary-text-color); }
    .chip.on { background:var(--primary-color); border-color:var(--primary-color); color:var(--text-primary-color,#fff); }
    .floor { font-size:13px; font-weight:600; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.04em; margin:18px 4px 8px; }
    .room { border-bottom:1px solid var(--divider-color); }
    .row { display:grid; grid-template-columns:34px minmax(0,1.4fr) 64px 64px minmax(0,2fr) 20px; gap:8px; align-items:center; padding:10px 12px; cursor:pointer; }
    .row:hover { background:var(--secondary-background-color); }
    .ico { font-size:18px; text-align:center; }
    .name { font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .num { text-align:right; font-variant-numeric:tabular-nums; }
    .num small { display:block; font-size:11px; color:var(--secondary-text-color); }
    .why { display:flex; gap:6px; align-items:center; min-width:0; }
    .why span.txt { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--secondary-text-color); font-size:13px; }
    .lvl { display:inline-block; border-radius:6px; padding:1px 8px; font-size:12px; color:#fff; white-space:nowrap; flex:none; }
    .chev { color:var(--secondary-text-color); transition:transform .15s; }
    .open .chev { transform:rotate(90deg); }
    .detail { padding:4px 14px 14px 54px; }
    .facts { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:6px 16px; font-size:13px; margin-bottom:10px; }
    .facts b { font-weight:500; }
    .facts .dev { grid-column:1 / -1; }
    .facts div span { color:var(--secondary-text-color); }
    .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
    .btn { border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); border-radius:8px; padding:6px 12px; font:inherit; font-size:14px; cursor:pointer; }
    .btn.pri { background:var(--primary-color); color:var(--text-primary-color,#fff); border-color:var(--primary-color); }
    .btn.warn { color:var(--error-color); }
    .btn:disabled { opacity:.5; cursor:default; }
    .week { display:grid; grid-template-columns:28px minmax(0,1fr); gap:3px 6px; font-size:12px; }
    .week .d { color:var(--secondary-text-color); align-self:center; }
    .week .d.today { color:var(--primary-color); font-weight:600; }
    .bar { position:relative; display:flex; height:16px; border-radius:4px; overflow:hidden; background:var(--divider-color); }
    .bar i { flex:1; }
    .bar .now { position:absolute; top:-2px; bottom:-2px; width:2px; background:var(--primary-text-color); }
    .axis { display:flex; justify-content:space-between; font-size:10px; color:var(--secondary-text-color); grid-column:2; }
    .legend { display:flex; flex-wrap:wrap; gap:4px 12px; font-size:12px; color:var(--secondary-text-color); margin-top:6px; }
    .legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:-1px; }
    .empty { padding:24px; text-align:center; color:var(--secondary-text-color); }
    .hint { font-size:13px; color:var(--secondary-text-color); margin:6px 0; }
    .reqban { display:flex; flex-wrap:wrap; align-items:center; gap:8px 12px; justify-content:space-between; }
    .rq .rqrow { display:grid; grid-template-columns:30px minmax(0,1fr) auto; gap:10px; align-items:start; padding:10px 14px; border-bottom:1px solid var(--divider-color); }
    .rq .rqrow:last-child { border-bottom:0; }
    .rqs { width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:14px; }
    .rqs.rok { background:rgba(61,154,91,.15); color:#1b5e30; } .rqs.rwarn { background:rgba(255,152,0,.18); color:#7a4a00; }
    .rqs.rnone { background:var(--secondary-background-color); color:var(--secondary-text-color); } .rqs.rinfo { background:rgba(3,169,244,.12); color:var(--primary-color); }
    .rqt { min-width:0; display:grid; gap:2px; font-size:13.5px; } .rqt small { font-size:12px; }
    .rq .btnrow { justify-content:flex-end; max-width:360px; } .rq select { max-width:300px; }
    @media (max-width:720px) { .rq .rqrow { grid-template-columns:30px minmax(0,1fr); } .rq .btnrow { grid-column:2; justify-content:flex-start; } }
    .bad { color:var(--error-color); }
    .warnbox { background:rgba(255,152,0,.12); border-left:3px solid var(--warning-color,#ff9800); padding:8px 10px; border-radius:6px; font-size:13px; margin:8px 0; }
    input[type=search], input[type=text], input[type=number], input[type=time], input[type=date], select.inp, input.inp {
      font:inherit; color:var(--primary-text-color); background:var(--card-background-color);
      border:1px solid var(--divider-color); border-radius:8px; padding:6px 8px; min-width:0; }
    input[type=search] { width:100%; margin:8px 0; }
    .area { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px; align-items:center; padding:10px 14px; border-bottom:1px solid var(--divider-color); }
    .area .sub { font-size:12px; color:var(--secondary-text-color); overflow:hidden; text-overflow:ellipsis; }
    .badge { font-size:11px; border-radius:4px; padding:0 5px; background:var(--secondary-background-color); color:var(--secondary-text-color); margin-left:4px; }
    /* Editor */
    .ov { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:9; display:flex; align-items:center; justify-content:center; padding:16px; }
    .dlg { background:var(--card-background-color); color:var(--primary-text-color); border-radius:14px; width:min(980px,100%); max-height:calc(100vh - 32px); overflow:auto; box-shadow:0 10px 40px rgba(0,0,0,.35); }
    .dlg header { position:sticky; top:0; background:var(--card-background-color); z-index:1; display:flex; justify-content:space-between; align-items:center; padding:14px 18px; border-bottom:1px solid var(--divider-color); }
    .dlg header h2 { margin:0; font-size:18px; font-weight:500; }
    .dlg footer { position:sticky; bottom:0; background:var(--card-background-color); display:flex; gap:8px; justify-content:flex-end; flex-wrap:wrap; padding:12px 18px; border-top:1px solid var(--divider-color); }
    .dlg footer .sp { flex:1; }
    .cols { display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,1fr); gap:18px; padding:16px 18px; }
    .cols > div { min-width:0; }
    .sec { margin-bottom:16px; }
    .sec h3 { font-size:14px; font-weight:600; margin:0 0 8px; }
    .grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; }
    .grid2 label, .lvls label { font-size:12px; color:var(--secondary-text-color); display:flex; flex-direction:column; gap:3px; }
    .lvls { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; }
    .lvls input { width:100%; }
    .dt { border:1px solid var(--divider-color); border-radius:10px; padding:10px; margin-bottom:10px; }
    .dt .hd { display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; gap:6px; flex-wrap:wrap; }
    .blk { display:grid; grid-template-columns:72px auto 72px minmax(0,1fr) 32px; gap:6px; align-items:center; margin-bottom:6px; }
    .blk input, .blk select { width:100%; } .blk input { text-align:center; font-variant-numeric:tabular-nums; }
    .x { border:0; background:none; cursor:pointer; color:var(--secondary-text-color); font-size:18px; }
    .ths { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:6px; }
    .th { display:flex; gap:8px; align-items:flex-start; padding:6px 8px; border:1px solid var(--divider-color); border-radius:8px; cursor:pointer; min-width:0; }
    .th span { min-width:0; overflow:hidden; } .th small { display:block; font-size:11px; color:var(--secondary-text-color); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .th .off { margin-left:auto; flex:none; font-size:12px; color:var(--secondary-text-color); white-space:nowrap; }
    .th .off input { width:58px; padding:3px 4px; }
    .th.dis { opacity:.55; cursor:default; }
    .acbox { border:1px solid var(--divider-color); border-radius:10px; padding:10px; margin-top:12px; background:var(--secondary-background-color); }
    .acbox h3 { margin:0 0 8px; font-size:14px; }
    .inl { display:flex; align-items:center; gap:4px; color:var(--secondary-text-color); }
    .inl input { width:80px; } .inl input[type=checkbox] { width:auto; }
    .cops { display:grid; grid-template-columns:90px 90px 28px; gap:4px 6px; align-items:center; margin:8px 0; }
    .cops .h { font-size:12px; color:var(--secondary-text-color); }
    .verdict { margin:8px 0; font-size:14px; }
    .src { font-size:11px; border-radius:6px; padding:1px 6px; border:1px solid var(--divider-color); white-space:nowrap; flex:none; }
    .src.ac { border-color:#3aa0d8; color:#3aa0d8; }
    .src.radiator { border-color:#e8833a; color:#e8833a; }
    .sub2 { font-size:12px; font-weight:400; color:var(--secondary-text-color); }
    .th .off select { padding:2px 4px; font-size:12px; }
    .warnmark { color:var(--warning-color,#ff9800); font-size:14px; }
    .foreign { margin:8px 0 10px; font-size:13px; }
    .foreign .fh { font-weight:600; margin-bottom:4px; }
    .hintrow { display:flex; gap:8px; align-items:center; justify-content:space-between; padding:6px 8px; border-radius:8px; background:rgba(255,152,0,.10); margin-bottom:4px; flex-wrap:wrap; }
    .hintrow small { color:var(--secondary-text-color); }
    .hbtns { display:flex; gap:6px; flex:none; }
    .btn.sm { padding:3px 8px; font-size:12px; }
    .linkbtn { border:0; background:none; color:var(--primary-color); cursor:pointer; padding:2px 0; font:inherit; font-size:12px; }
    .foreign details { margin-top:6px; }
    .foreign summary { cursor:pointer; color:var(--secondary-text-color); }
    .logrow { display:grid; grid-template-columns:90px minmax(0,1fr) 70px minmax(0,1.2fr); gap:6px; padding:3px 0; border-bottom:1px solid var(--divider-color); }
    .logrow span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--secondary-text-color); }
    @media (max-width:720px) { .logrow { grid-template-columns:70px minmax(0,1fr) 60px; } .logrow span:last-child { grid-column:1 / -1; } }
    .hero { display:flex; gap:14px; align-items:flex-start; border:1px solid var(--divider-color); border-radius:var(--ha-card-border-radius, 12px); padding:14px; margin:12px 0 4px;
      background:var(--ha-card-background, var(--card-background-color)); }
    .hico { font-size:28px; width:52px; height:52px; border-radius:12px; background:var(--secondary-background-color); display:flex; align-items:center; justify-content:center; flex:none; }
    .htxt { min-width:0; }
    .htitle { font-size:20px; font-weight:600; }
    .hsub { color:var(--secondary-text-color); font-size:14px; margin:2px 0 8px; }
    .hchips { display:flex; flex-wrap:wrap; gap:6px; }
    .hchip { background:var(--secondary-background-color); border:0; border-radius:14px; padding:3px 10px; font:inherit; font-size:13px; color:var(--primary-text-color); cursor:pointer; display:inline-flex; gap:6px; align-items:center; max-width:100%; text-align:left; }
    .hchip.hand { background:rgba(167,123,214,.18); cursor:default; }
    .hchip.warnc { background:rgba(255,152,0,.14); color:var(--warning-color,#b7791f); }
    .lx { border:0; background:rgba(0,0,0,.12); color:inherit; border-radius:5px; padding:0 5px; margin-left:4px; cursor:pointer; font:inherit; font-size:12px; line-height:16px; }
    .mrow { display:flex; gap:6px; align-items:center; margin-top:4px; flex-wrap:wrap; }
    .mrow small { color:var(--secondary-text-color); font-size:12px; }
    .mini { border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--secondary-text-color); border-radius:10px; padding:1px 8px; font:inherit; font-size:12px; cursor:pointer; }
    .mini.on { border-color:var(--primary-color); color:var(--primary-color); }
    .mode select[data-a=event] { width:100%; border:0; background:transparent; font:inherit; color:var(--primary-text-color); padding:2px 0; cursor:pointer; }
    .floor.fl { display:flex; justify-content:space-between; align-items:baseline; cursor:pointer; gap:8px; }
    .floor.fl small { text-transform:none; letter-spacing:0; font-weight:400; font-size:12px; }
    .star { color:#c99a06; font-size:14px; }
    .todaybar { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin:8px 0; }
    .todaybar .tl { font-size:13px; color:var(--secondary-text-color); }
    .todaybar small { color:var(--secondary-text-color); font-size:12px; }
    .seg { border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); border-radius:14px; padding:3px 10px; font:inherit; font-size:12px; cursor:pointer; }
    .seg.on { background:var(--primary-color); border-color:var(--primary-color); color:var(--text-primary-color,#fff); }
    .seg.big { font-size:14px; padding:8px 14px; border-radius:18px; min-height:38px; display:inline-flex; align-items:center; gap:6px; }
    .seg.big small { color:inherit; opacity:.75; }
    .seg .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
    .seg.on .dot { box-shadow:0 0 0 2px var(--card-background-color); }
    .tddlg { width:min(620px,100%); }
    h3.step { margin:16px 0 6px; font-size:15px; font-weight:500; }
    h3.step b { color:var(--primary-color); }
    .pills { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
    .rtopt { display:flex; align-items:center; gap:8px; min-height:34px; font-size:14px; }
    .rtopt small, .rtsub small { color:var(--secondary-text-color); }
    .rtgroup { padding-left:26px; display:flex; flex-direction:column; gap:4px; font-size:14px; }
    .rtsub { display:flex; align-items:center; gap:8px; min-height:30px; font-size:14px; }
    small.warnt { color:var(--warning-color,#b26a00) !important; }
    .rtinfo { background:var(--secondary-background-color); border-radius:10px; padding:10px 12px; font-size:14px; }
    .badge.warnb { background:#fff4e5; color:#6b3d00; } .badge.okb { background:#e6f4ea; color:#1e6b34; }
    .rtval { display:inline-flex; align-items:center; gap:6px; font-size:14px; }
    .rtval input { width:70px; }
    .rtlines { font-size:13px; line-height:1.6; margin:6px 0; }
    .ctl { border:1px solid var(--divider-color); border-radius:10px; padding:10px 12px; margin:6px 0; display:flex; flex-direction:column; gap:6px; }
    .ctlhd { display:flex; align-items:center; gap:8px; }
    .ctlhd .sp, .ctlhd .sp { flex:1; }
    .ctlrow { display:flex; align-items:center; gap:8px; font-size:14px; }
    .ctlrow > span:first-child { width:140px; }
    .keytag { font-size:13px; padding:2px 8px; border-radius:6px; background:var(--secondary-background-color); }
    .learnwait { font-size:13px; color:var(--primary-color); font-weight:600; }
    .chip.hand { color:#5b2a86; }
    select.inp.md { width:auto; min-width:0; }
    .srow.sday { border:1px solid var(--divider-color,#e0e0e0); border-radius:10px; padding:8px 10px; margin-top:6px; }
    .srow.sday .srh { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
    .ctlrow select { flex:1; }
    .heatln { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:4px; font-size:13px; }
    .hchip { padding:2px 9px; border-radius:12px; background:#e8f0f7; color:#1d4f7a; font-weight:500; }
    .hchip.on { background:#fde7d9; color:#8a3b0a; }
    .hbar { width:110px; height:8px; border-radius:4px; background:var(--divider-color); overflow:hidden; display:inline-block; }
    .hbar i { display:block; height:100%; background:#e0874a; }
    .rtwarn { background:#fff4e5; border:1px solid #f5c27a; color:#6b3d00; border-radius:8px; padding:6px 10px; font-size:13px; margin:4px 0; }
    .tdbody { padding:14px 18px; display:flex; flex-direction:column; gap:14px; }
    .tdsec h3 { margin:0 0 8px; font-size:12px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--secondary-text-color); }
    .tdrow { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
    .tdrow + .tdrow { margin-top:8px; }
    .tdl { width:30px; font-size:14px; color:var(--secondary-text-color); }
    .tdprev { background:var(--secondary-background-color); border-radius:10px; padding:10px 12px; font-size:14px; display:flex; flex-direction:column; gap:6px; }
    .tdbar { display:flex; height:20px; border-radius:6px; overflow:hidden; }
    .tdbar i { flex:1; }
    .tdax { display:flex; justify-content:space-between; font-size:11px; color:var(--secondary-text-color); }
    .tdprev .err { color:var(--error-color,#db4437); }
    .rules { display:flex; flex-direction:column; gap:3px; font-size:12px; color:var(--secondary-text-color); margin-bottom:8px; }
    .rules .act { color:var(--primary-text-color); font-weight:500; }
    .rule { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:6px; font-size:13px; }
    .rule select { max-width:100%; }
    @media (max-width:720px) { .hero { padding:10px 12px; } .htitle { font-size:17px; } .hico { display:none; } }
    .icob { border:0; background:none; cursor:pointer; padding:4px; border-radius:50%; font:inherit; font-size:18px; line-height:1; width:32px; height:32px; }
    .icob:hover, .icob:focus-visible { background:var(--secondary-background-color); outline:2px solid var(--primary-color); outline-offset:-2px; }
    .ctlmenu { display:flex; flex-wrap:wrap; gap:6px; padding:0 4px 10px 40px; }
    .histhd { display:flex; gap:6px; align-items:center; margin:14px 0 4px; font-size:13px; }
    .histhd b { margin-right:4px; }
    .hist { min-height:40px; }
    .hsvg { width:100%; height:180px; display:block; }
    .hsvg .g { stroke:var(--divider-color); stroke-width:1; }
    .hsvg .ax { fill:var(--secondary-text-color); font-size:10px; }
    .hum { margin-left:8px; font-size:12px; font-weight:400; color:var(--secondary-text-color); white-space:nowrap; }
    .batmark { font-size:13px; }
    .lvlbox { border:1px solid var(--divider-color); border-radius:var(--ha-card-border-radius, 12px); padding:2px 12px 10px; margin:10px 0 14px; background:var(--ha-card-background, var(--card-background-color)); }
    .lvlgrid { display:grid; grid-template-columns:14px minmax(0,1fr) 110px 64px 50px; gap:6px 10px; align-items:center; margin:8px 0; }
    .lvlgrid i { width:12px; height:12px; border-radius:3px; display:inline-block; }
    .lvlgrid .h { font-size:12px; color:var(--secondary-text-color); }
    .lvlgrid input[type=text] { width:100%; }
    .lvlgrid .inl input { width:70px; }
    .devroom { font-weight:600; padding:10px 14px 2px; font-size:14px; }
    .devrow { display:grid; grid-template-columns:minmax(0,1.5fr) minmax(120px,1fr) minmax(0,1fr); gap:10px; align-items:center; padding:9px 14px; border-bottom:1px solid var(--divider-color); cursor:pointer; font-size:14px; }
    .devrow:hover { background:var(--secondary-background-color); }
    .devrow small { display:block; font-size:12px; color:var(--secondary-text-color); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .devrow .dn { min-width:0; overflow:hidden; text-overflow:ellipsis; }
    .db { display:flex; align-items:center; gap:8px; }
    .batt { width:60px; height:10px; border-radius:3px; border:1px solid var(--divider-color); overflow:hidden; display:inline-block; }
    .batt i { display:block; height:100%; background:#57a55a; }
    .batt.low i { background:var(--error-color); }
    .bad { color:var(--error-color); }
    .ok { color:#57a55a; }
    @media (max-width:720px) { .devrow { grid-template-columns:minmax(0,1fr) 110px; } .devrow .da { grid-column:1 / -1; display:flex; gap:8px; } .devrow .da small { display:inline; }
      .lvlgrid { grid-template-columns:14px minmax(0,1fr) 92px 44px 36px; gap:6px; } }
    .hmodes { display:flex; flex-wrap:wrap; gap:4px 0; align-items:center; margin:0 0 8px; cursor:pointer; font-size:14px; }
    .hmodes span { color:var(--primary-text-color); }
    .hmodes span + span::before { content:"·"; margin:0 6px; color:var(--secondary-text-color); }
    .hmodes .mini { margin-left:10px; }
    .title .hrlogo { width:34px; height:26px; flex:none; }
    .title .hrword { height:56px; width:auto; max-width:100%; flex:none; display:block; }
    @media (max-width:500px) { .title .hrword { height:42px; } }
    .hrw { font-size:21px; letter-spacing:-.2px; }
    .hrw .h1 { font-weight:300; }
    .hrw .h2 { font-weight:700; }
    .setg { display:grid; gap:10px; }
    .setc { display:grid; grid-template-columns:36px minmax(0,1fr) auto; gap:12px; align-items:center; padding:12px 14px; }
    .setc .sico { font-size:22px; text-align:center; }
    .btnrow { display:flex; gap:6px; flex-wrap:wrap; }
    @media (max-width:560px) { .setc { grid-template-columns:30px minmax(0,1fr); } .setc > :last-child { grid-column:2; } }
    /* Übersicht: Zeitleiste */
    .dpick { display:flex; gap:6px; flex-wrap:wrap; align-items:center; justify-content:flex-end; }
    .dpick .chip, .tfil .chip { padding:2px 10px; font-size:12px; }
    .dpick input { padding:3px 6px; font-size:12px; }
    .tline { padding:4px 0 10px; }
    .tfil { display:flex; gap:6px; flex-wrap:wrap; align-items:center; padding:8px 14px 10px; border-bottom:1px solid var(--divider-color); margin-bottom:6px; }
    .tinfo { margin:0 0 0 auto; }
    .cdot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:4px; }
    .tpast { margin:2px 0 4px 72px; }
    .tev { display:grid; grid-template-columns:52px 14px minmax(0,1fr); gap:10px; align-items:center; padding:3px 14px; cursor:pointer; position:relative; }
    .tev::before { content:""; position:absolute; left:80px; top:0; bottom:0; width:2px; background:var(--divider-color); }
    .tev .tt { text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }
    .tdot { width:12px; height:12px; border-radius:50%; position:relative; z-index:1; box-shadow:0 0 0 3px var(--ha-card-background, var(--card-background-color)); }
    .tc { display:flex; gap:10px; align-items:center; background:var(--secondary-background-color); border-radius:10px; padding:7px 10px; min-width:0; }
    .tc:hover { outline:1px solid var(--primary-color); }
    .tc.run { outline:2px solid #7fb563; }
    .tc .ti { font-size:20px; flex:none; }
    .tc > div { min-width:0; flex:1; }
    .tc b { display:block; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .tc small { display:block; color:var(--secondary-text-color); font-size:12.5px; }
    .tev.past { opacity:.5; }
    .tnow { display:grid; grid-template-columns:52px 1fr auto; gap:10px; align-items:center; padding:4px 14px; color:var(--error-color); font-size:12px; font-weight:600; }
    .tnow span { text-align:right; } .tnow i { height:2px; background:var(--error-color); display:block; }
    .chip.skipc { border:0; background:rgba(167,123,214,.18); color:#7d55b0; font-size:11px; padding:1px 8px; cursor:default; }
    @media (max-width:560px) { .tev { grid-template-columns:42px 12px minmax(0,1fr); gap:8px; padding:3px 10px; } .tev::before { left:63px; } .tnow { grid-template-columns:42px 1fr auto; } .tinfo { width:100%; margin:0; } .tpast { margin-left:50px; } }
    /* Abläufe */
    .sim { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; padding:10px 14px; font-size:13px; margin-top:12px; }
    .segs { display:inline-flex; flex-wrap:wrap; gap:3px; margin-left:4px; }
    .frow { display:grid; grid-template-columns:36px minmax(0,1.35fr) minmax(0,.9fr) minmax(0,1.6fr) 18px; gap:10px; align-items:center; padding:10px 12px; border-bottom:1px solid var(--divider-color); cursor:pointer; }
    .frow.r { grid-template-columns:36px minmax(0,2.4fr) minmax(0,1fr) 18px; }
    .frow:hover { background:var(--secondary-background-color); }
    .frow.dim .fn b, .frow.dim .fs, .frow.dim .fbar { opacity:.5; }
    /* ausgeschaltet (Haken „aktiv“ weg): ganze Zeile deutlich zurückgenommen, beim Zeigen etwas kräftiger */
    .frow.off { opacity:.35; filter:grayscale(1); transition:opacity .15s; }
    .frow.off:hover, .frow.off:focus-within { opacity:.6; }
    .frow.off .fn b::after { content:" · aus"; font-weight:400; }
    .rcol { display:flex; flex-direction:column; gap:14px; min-width:0; }
    /* Übersicht: Tag, Uhrzeit-Regler, angenommen (0.9.11) */
    .ovtime { padding:14px 16px; display:flex; flex-direction:column; gap:10px; margin-bottom:14px; border:1px solid var(--divider-color,#e0e0e0); }
    .ovtime.sim { border:2px solid #f0c36d; }
    .ovrow { display:flex; align-items:center; gap:8px; flex-wrap:wrap; justify-content:flex-start; text-align:left; }
    .ovrow .dpick { justify-content:flex-start; }
    .ovtime { text-align:left; align-items:stretch; }
    .ovl { font-size:12px; color:var(--secondary-text-color); letter-spacing:.04em; text-transform:uppercase; width:64px; }
    .ovtm { font-family:ui-monospace,Menlo,monospace; font-size:22px; font-weight:500; width:70px; }
    .ovrange { flex:1; min-width:160px; display:flex; flex-direction:column; }
    .ovrange input { width:100%; accent-color:var(--primary-color); height:28px; }
    .ovax { display:flex; justify-content:space-between; font-size:11px; color:var(--secondary-text-color); }
    .chip.okc { background:#e3f1e6; color:#1e5b2b; } .chip.simc { background:#fff4d6; color:#6b4500; }
    .ovass summary { cursor:pointer; min-height:32px; display:flex; align-items:center; gap:8px; }
    .ovsegs { display:flex; flex-wrap:wrap; gap:10px 18px; align-items:center; margin:8px 0 4px; font-size:13px; }
    .ovsegs > span { display:flex; align-items:center; gap:6px; }
    .simnote { font-size:13px; background:#fff4d6; color:#4a3b00; border-radius:10px; padding:8px 12px; }
    .ovgrid { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:16px; align-items:start; }
    @media (max-width: 900px) { .ovgrid { grid-template-columns:1fr; } }
    .ovfloor { padding:0; overflow:hidden; margin-bottom:12px; }
    .ovfh { display:flex; align-items:center; gap:10px; width:100%; min-height:46px; padding:6px 14px; border:0; background:var(--secondary-background-color,#f5f5f5); text-align:left; cursor:pointer; color:inherit; font:inherit; }
    .ovfh.static { cursor:default; }
    .ovfh small { font-size:12.5px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .ovfh .chev { display:inline-block; width:12px; color:var(--secondary-text-color); transition:transform .15s; }
    .ovfh .chev.open { transform:rotate(90deg); }
    .ovr { display:grid; grid-template-columns:minmax(0,150px) 96px 56px minmax(0,1fr); gap:10px; align-items:center; min-height:46px; padding:4px 14px; border-top:1px solid var(--divider-color,#eee); cursor:pointer; }
    .ovr.off { opacity:.4; filter:grayscale(1); }
    .ovn { display:flex; flex-direction:column; min-width:0; } .ovn b { font-weight:500; font-size:14px; } .ovn small { font-size:12px; color:var(--secondary-text-color); }
    .ovt { font-family:ui-monospace,Menlo,monospace; font-size:16px; font-weight:500; }
    .ovx { font-size:12.5px; color:var(--secondary-text-color); }
    .lvl { justify-self:start; font-size:12px; padding:3px 10px; border-radius:12px; background:#eceef1; color:#3c4043; white-space:nowrap; }
    .lvl.lk { background:#fde7d9; color:#8a3b0a; } .lvl.ln { background:#e6e8f7; color:#2f3a8f; } .lvl.lb { background:#fbd9d0; color:#8a2a0a; }
    .lvl.lu { background:#e3f1e6; color:#1e5b2b; } .lvl.lo, .lvl.lx { background:#f1f3f4; color:#80868b; }
    .stale { opacity:.6; }
    /* 0.9.12 Kopf der Übersicht */
    .ovhead { padding:0; margin-bottom:12px; overflow:hidden; }
    .ovhrow { display:flex; align-items:center; gap:10px; padding:8px 12px; min-height:48px; }
    .hico2 { font-size:20px; } .htx { display:flex; flex-direction:column; flex:none; } .htx b { font-size:14.5px; font-weight:600; } .htx small { font-size:12px; color:var(--secondary-text-color); }
    .hpills { display:flex; gap:6px; flex:1; min-width:0; overflow-x:auto; white-space:nowrap; scrollbar-width:none; padding:2px 0; }
    .hpills::-webkit-scrollbar { display:none; }
    .hpills > span { flex:none; font-size:12.5px; padding:4px 10px; border-radius:12px; background:var(--secondary-background-color,#eef1f5); }
    .hpills .mini { flex:none; }
    .hcnts { display:flex; gap:5px; flex:none; }
    .hcnt { font:inherit; font-size:12.5px; padding:4px 9px; border-radius:12px; border:1px solid transparent; background:#fde7d9; color:#8a3b0a; cursor:pointer; white-space:nowrap; }
    .hcnt.w { background:#fff4d6; color:#6b4500; } .hcnt.bad { background:#fdeaea; color:#8c1d18; } .hcnt.on { border-color:currentColor; }
    .ovtbtn { flex:none; white-space:nowrap; } .ovtbtn.simb { background:#fff4d6; border-color:#f0c36d; color:#6b4500; }
    .gearb { flex:none; width:36px; height:36px; border-radius:18px; border:1px solid var(--divider-color); background:none; cursor:pointer; color:inherit; }
    .ovsub { border-top:1px solid var(--divider-color); padding:8px 14px; display:flex; gap:16px; flex-wrap:wrap; align-items:center; font-size:13px; background:var(--secondary-background-color,#fafbfc); }
    .ovsub label { display:flex; align-items:center; gap:6px; } .ovsub.modes { display:block; } .ovsub.pop { display:block; }
    .ovhead .ovtime { border:0; border-top:1px solid var(--divider-color); border-radius:0; margin:0; background:var(--secondary-background-color,#fafbfc); }
    .ovhead .ovtime.sim { background:#fffbf0; }
    .poph { display:flex; align-items:center; gap:8px; margin-bottom:4px; }
    .popr { display:grid; grid-template-columns:24px minmax(0,1fr) minmax(0,1.4fr) auto; gap:8px; align-items:center; min-height:34px; border-top:1px solid var(--divider-color,#eee); cursor:pointer; }
    .popr .pv { text-align:right; white-space:nowrap; }
    @media (max-width: 900px) { .ovhrow { flex-wrap:wrap; } .hpills { order:5; flex-basis:100%; } }
    /* Zeilen der Übersicht wie in „Heizung & Klima“ / „Abläufe“ */
    .ovgrp { margin-bottom:12px; } .ovgh { display:flex; align-items:baseline; gap:10px; border:0; background:none; padding:4px 6px; cursor:pointer; color:inherit; font:inherit; width:100%; text-align:left; }
    .ovgh b { font-size:12.5px; letter-spacing:.06em; } .ovgh small { font-size:12px; color:var(--secondary-text-color); } .ovgh.static { cursor:default; align-items:center; } .ovgh .inl { font-size:12.5px; color:var(--secondary-text-color); display:flex; gap:5px; align-items:center; } .ovgh .sp { flex:1; }
    .ovr2 { display:grid; grid-template-columns:40px minmax(0,1fr) 60px 60px minmax(0,1.6fr) 14px; gap:8px; align-items:center; min-height:50px; padding:4px 12px; border-bottom:1px solid var(--divider-color); cursor:pointer; }
    .ovr2.fl { grid-template-columns:40px minmax(0,1fr) 110px minmax(0,1.4fr) 14px; }
    .ovr2.off { opacity:.4; filter:grayscale(1); }
    .ovr2 .ico { font-size:20px; text-align:center; } .ovr2 .nm { font-weight:500; font-size:14.5px; display:flex; flex-direction:column; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .ovr2 .nm small { font-weight:400; font-size:12px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .ovr2 .num { display:flex; flex-direction:column; align-items:flex-end; font-weight:500; } .ovr2 .num small { font-size:11px; color:var(--secondary-text-color); font-weight:400; }
    .ovr2 .why { display:flex; align-items:center; gap:8px; min-width:0; } .ovr2 .why .lvl { flex:none; color:#fff; font-size:12px; padding:2px 9px; border-radius:11px; }
    .ovr2 .why .txt { font-size:12.5px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .ovr2 .fs2 { display:flex; flex-direction:column; } .ovr2 .fs2 small, .ovr2 .fx2 small { font-size:12px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .ovr2 .fx2 { display:flex; flex-direction:column; gap:3px; min-width:0; }
    .mbar { position:relative; display:block; height:8px; border-radius:4px; overflow:visible; } .mbar.off { background:repeating-linear-gradient(135deg,#eceef1 0 5px,#dfe2e6 5px 10px); }
    .mbar i { position:absolute; top:-2px; bottom:-2px; width:2px; background:var(--error-color,#d93025); }
    .ovr2 .chev { color:var(--secondary-text-color); }
    @media (max-width: 700px) { .ovr2 { grid-template-columns:36px minmax(0,1fr) 52px 52px 10px; } .ovr2 .why { grid-column:2 / -1; } .ovr2.fl { grid-template-columns:36px minmax(0,1fr) 90px 10px; } .ovr2.fl .fx2 { grid-column:2 / -1; } }
    /* Bedien-Fenster */
    .qdlg { width:min(560px,100%); }
    .qhd { display:flex; align-items:center; gap:8px; padding:12px 14px; border-bottom:1px solid var(--divider-color); flex-wrap:wrap; }
    .qhd b { font-size:18px; font-weight:500; } .qico { font-size:22px; }
    .qbody { padding:14px 16px; display:flex; flex-direction:column; gap:12px; }
    .qinfo { display:flex; gap:16px; flex-wrap:wrap; font-size:13px; color:var(--secondary-text-color); } .qinfo b { color:var(--primary-text-color); font-size:15px; }
    .qtemp { display:flex; align-items:center; justify-content:center; gap:22px; }
    .qtemp b { font-size:44px; font-weight:500; min-width:150px; text-align:center; font-variant-numeric:tabular-nums; } .qtemp b.back { color:var(--secondary-text-color); }
    .qpm { width:56px; height:56px; border-radius:28px; border:1px solid var(--divider-color); background:none; font-size:26px; cursor:pointer; color:inherit; }
    .qsegs { display:flex; gap:6px; flex-wrap:wrap; justify-content:center; } .qlab { font-size:11.5px; letter-spacing:.05em; color:var(--secondary-text-color); }
    .qft { display:flex; gap:8px; align-items:center; padding:10px 14px; border-top:1px solid var(--divider-color); flex-wrap:wrap; }
    .qbigs { display:flex; gap:8px; } .qbig { flex:1; min-height:46px; border-radius:12px; border:1px solid var(--primary-color); background:none; color:var(--primary-color); font:inherit; font-size:15px; cursor:pointer; }
    .qbig.on { background:var(--primary-color); color:var(--text-primary-color,#fff); }
    .qdevs { border:1px solid var(--divider-color); border-radius:12px; overflow:hidden; }
    .qdev { display:grid; grid-template-columns:24px minmax(0,1fr) auto auto auto; gap:8px; align-items:center; min-height:46px; padding:4px 10px; border-top:1px solid var(--divider-color); }
    .qdev:first-child { border-top:0; } .qdev small { font-size:12px; color:var(--secondary-text-color); white-space:nowrap; } .qdn { text-align:left; }
    .qnote { background:var(--secondary-background-color); border-radius:8px; padding:6px 10px; }
    @media (max-width: 600px) { .qdlg { width:100%; } .qtemp b { font-size:38px; min-width:120px; } }
    .ovico { display:inline-block; width:22px; text-align:center; } .ovleg { margin:-4px 6px 12px; font-size:12px; }
    .devbar { padding:12px 14px; display:flex; flex-direction:column; gap:8px; margin-bottom:6px; }
    .devbar .filters { display:flex; gap:6px; flex-wrap:wrap; align-items:center; margin:0; }
    .flab { font-size:12px; color:var(--secondary-text-color); width:76px; }
    .devopts label { display:flex; align-items:center; gap:6px; font-size:13px; margin-right:10px; }
    .floorh { background:#eef1f5; min-height:50px; } .floorh b { font-size:15px; }
    .devroom2 { border-top:1px solid var(--divider-color,#e0e0e0); } .devroom2 > .ovfh { background:none; padding-left:26px; }
    .devrow2 { display:grid; gap:12px; align-items:center; min-height:50px; padding:6px 14px 6px 50px; border-top:1px solid var(--divider-color,#f0f0f0); }
    .devrow2 .dn { display:flex; flex-direction:column; gap:2px; min-width:0; } .devrow2 .dnn { cursor:pointer; font-size:14px; }
    .devrow2 .dn small { font-size:12px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .devrow2 .db { display:flex; align-items:center; gap:8px; } .devrow2 .da { display:flex; flex-direction:column; font-size:13px; }
    .utags { display:flex; gap:6px; flex-wrap:wrap; margin-top:3px; }
    .utag { font:inherit; font-size:12px; padding:3px 9px; border-radius:11px; border:0; cursor:pointer; }
    .utag.heat { background:#fde7d9; color:#8a3b0a; } .utag.flow { background:#efe3fa; color:#4a1d70; } .utag.off { opacity:.55; }
    .utag.none { border:1px dashed var(--divider-color,#c4c8ce); background:none; color:var(--secondary-text-color); cursor:default; }
    @media (max-width: 700px) { .devrow2 { padding-left:20px; grid-template-columns:minmax(0,1fr) !important; } }
    .tnow.tsel { color:var(--primary-color); } .tnow.tsel i { background:none; border-top:2px dashed var(--primary-color); height:0; }
    .hero { position:relative; } .hopts { display:flex; flex-direction:column; gap:4px; font-size:12.5px; margin-left:auto; align-self:flex-start; }
    .hopts label { display:flex; align-items:center; gap:6px; white-space:nowrap; }
    @media (max-width: 700px) { .hopts { display:none; } .ovr { grid-template-columns:minmax(0,1fr) 86px 50px; } .ovr .ovx { grid-column:1 / -1; } }
    .fold { border:1px solid var(--divider-color,#e0e0e0); border-radius:12px; margin-bottom:10px; background:var(--card-background-color,#fff); }
    .foldh { display:flex; align-items:center; gap:8px; padding-right:10px; }
    .foldb { display:flex; align-items:center; gap:10px; flex:1; min-width:0; min-height:48px; padding:8px 12px; border:0; background:none; text-align:left; cursor:pointer; color:inherit; font:inherit; }
    .foldb .chev { display:inline-block; width:14px; color:var(--secondary-text-color); transition:transform .15s; transform:rotate(90deg); }
    .fold.closed .foldb .chev { transform:rotate(0deg); }
    .foldt { display:flex; flex-direction:column; gap:2px; min-width:0; }
    .foldt b { font-size:14px; font-weight:600; }
    .foldt small { font-size:12.5px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .foldc { padding:0 14px 14px; }
    .foldall { display:flex; gap:14px; justify-content:flex-end; margin:-4px 0 6px; }
    .rcard > .fold { margin:0; }
    .weeknav { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin:4px 0 6px; }
    .weeknav b { min-width:130px; text-align:center; font-size:14px; font-weight:500; }
    .weeknav .wdate { display:flex; align-items:center; gap:4px; }
    .weeknav .wdate input { width:auto; }
    .weekjump { display:flex; gap:6px; flex-wrap:wrap; align-items:center; margin-bottom:6px; }
    .chip.jump { cursor:pointer; border:1px solid var(--divider-color,#e0e0e0); background:none; font:inherit; font-size:12px; color:#5b2a86; }
    .rcol > .rcard { margin:0; }
    .rcol > .acbox.native { margin:0; }
    .frow .ico { font-size:22px; }
    .frow .icob.big { font-size:22px; width:36px; height:36px; }
    .fctl { padding:8px 12px 10px 58px; border-bottom:1px solid var(--divider-color); background:var(--secondary-background-color); }
    .fctl .actions { margin:0 0 6px; }
    .fctl .devs { margin:4px 0; }
    .fn b { font-size:15px; font-weight:500; }
    .fn small, .fs small, .fx small { display:block; color:var(--secondary-text-color); font-size:12px; }
    .fn .sent { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
    .fs b { font-weight:500; } .runc { color:#3d9a5b; }
    .fn, .fs, .fx { min-width:0; overflow-wrap:anywhere; }
    .tags { display:flex; gap:4px; flex-wrap:wrap; margin-top:3px; }
    .tags .chip, .fn .chip { border:0; padding:1px 8px; font-size:11.5px; cursor:default; background:var(--secondary-background-color); color:var(--secondary-text-color); }
    .chip.cond { background:rgba(3,169,244,.12) !important; color:var(--primary-color) !important; }
    .chip.olap { background:rgba(232,163,61,.15) !important; color:#b7791f !important; }
    .fbar, .bar { position:relative; display:flex; height:10px; border-radius:4px; overflow:hidden; background:var(--divider-color); margin-top:4px; }
    .bar { height:14px; margin-top:0; }
    .fbar i, .bar i { flex:1; display:block; }
    .tick { position:absolute; top:0; bottom:0; width:2px; background:var(--primary-text-color); opacity:.55; }
    .barw { position:relative; }
    .barw .tick { top:-2px; bottom:-2px; margin-left:-1px; opacity:.8; }
    .barw .tick.guard { background:var(--secondary-text-color); opacity:.6; }
    .barw .tick.sun::after { content:"☀"; position:absolute; top:-12px; left:-4px; font-size:10px; line-height:1; color:#b36b00; }
    .barw .now, .fbar .now, .bar .now { position:absolute; top:-3px; bottom:-3px; width:3px; margin-left:-1px; border-radius:2px; background:#e53935; }
    .wk2 { display:grid; grid-template-columns:118px minmax(0,1fr); gap:16px 8px; font-size:12px; margin-top:16px; }
    .wk2 .d { color:var(--primary-text-color); font-weight:500; align-self:start; line-height:1.2; }
    .wk2 .d small { display:block; font-weight:400; color:var(--secondary-text-color); font-size:11px; }
    .wk2 .d.today { color:var(--primary-color); }
    .wk2 .bar { height:18px; }
    .wk2 .ml { font-size:11.5px; color:var(--secondary-text-color); margin-top:3px; font-variant-numeric:tabular-nums; }
    .simbar { display:flex; flex-wrap:wrap; gap:4px; margin:6px 0; }
    .modebar { display:inline-flex; border:1px solid var(--divider-color); border-radius:10px; overflow:hidden; }
    .modebar button { border:0; background:none; padding:6px 14px; font:inherit; font-size:13px; cursor:pointer; color:var(--primary-text-color); }
    .modebar button.on { background:var(--primary-color); color:var(--text-primary-color, #fff); }
    .modebar button:disabled { opacity:.45; cursor:not-allowed; }
    .srow { border:1px solid var(--divider-color); border-radius:10px; padding:8px 10px; margin-bottom:8px; display:grid; gap:6px; }
    .srow.sp { background:var(--secondary-background-color); }
    .srh { display:flex; flex-wrap:wrap; gap:6px 10px; align-items:center; }
    .srh b { min-width:150px; font-weight:600; }
    .srh small { color:var(--secondary-text-color); }
    .srl { display:flex; flex-wrap:wrap; gap:6px; align-items:center; padding-left:10px; font-size:13px; }
    .srl > .lb { min-width:104px; font-weight:500; white-space:nowrap; }
    .dtdot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; vertical-align:1px; }
    .guardl { padding-left:0; margin-top:6px; } .guardl .chk { display:inline-flex; gap:6px; align-items:center; font-weight:500; }
    .guardl small { flex:1 1 220px; }
    .reacthint { margin-top:10px; border:1px dashed var(--divider-color); border-radius:10px; padding:8px 10px; font-size:12.5px; color:var(--secondary-text-color); }
    .srl .inp { width:auto; flex:0 1 auto; } .srl input[type=number], .srl input.off { width:64px; } .srl input.tm { width:66px; }
    .srl .calc { color:var(--secondary-text-color); font-size:12px; }
    .sent { font-size:12.5px; color:#2e5d3a; background:rgba(61,154,91,.12); border-radius:8px; padding:4px 8px; justify-self:start; }
    .unit { font-size:12.5px; color:var(--secondary-text-color); }
    .empty-bar { opacity:.4; }
    .fdetail { padding:6px 14px 14px 58px; border-bottom:1px solid var(--divider-color); }
    .devs { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 10px; }
    .dev { border:1px solid var(--divider-color); border-radius:8px; padding:4px 9px; font:inherit; font-size:13px; background:var(--ha-card-background, var(--card-background-color)); cursor:pointer; color:var(--primary-text-color); }
    .dev small { color:var(--secondary-text-color); }
    .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; vertical-align:1px; }
    .pts { display:grid; gap:3px; margin:6px 0 10px; font-size:13px; }
    .flog { margin-top:10px; border-top:1px dashed var(--divider-color); padding-top:8px; display:grid; gap:2px; font-size:12.5px; }
    .swl { display:inline-flex; gap:6px; align-items:center; margin-left:auto; }
    .recipe { display:grid; gap:6px; margin:6px 0; }
    .blk2 { border-radius:10px; padding:8px 10px; margin-bottom:8px; }
    .blk2 .lbl { font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:var(--secondary-text-color); margin-bottom:4px; }
    .blk2.when { background:rgba(3,169,244,.10); } .blk2.cnd { background:rgba(167,123,214,.12); } .blk2.then { background:rgba(250,175,64,.14); }
    .step { display:flex; gap:8px; align-items:flex-start; font-size:13px; margin:2px 0; }
    .step .n { flex:none; width:20px; height:20px; border-radius:50%; border:1px solid var(--divider-color); background:var(--ha-card-background, var(--card-background-color)); font-size:11px; display:flex; align-items:center; justify-content:center; }
    .tplh { padding:12px 18px 0; font-size:12px; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.06em; font-weight:600; }
    .tpl { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:10px; padding:10px 18px 16px; }
    .tpl button { text-align:left; border:1px solid var(--divider-color); background:var(--ha-card-background, var(--card-background-color)); border-radius:12px; padding:12px; cursor:pointer; font:inherit; color:var(--primary-text-color); }
    .tpl button:hover { border-color:var(--primary-color); }
    .tpl span { font-size:22px; } .tpl b { display:block; margin:4px 0 2px; } .tpl small { color:var(--secondary-text-color); font-size:12px; }
    .grid3 { display:grid; grid-template-columns:70px minmax(0,1fr) 170px; gap:8px; margin-bottom:12px; }
    .grid3 label { font-size:12px; color:var(--secondary-text-color); display:flex; flex-direction:column; gap:3px; }
    .grid3 .inp { width:100%; font-size:14px; }
    .spc { border:1px solid var(--divider-color); border-radius:10px; padding:8px; margin-bottom:8px; }
    .spl { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
    .spl > select { flex:1 1 120px; min-width:110px; } .spl > input { width:70px; } .spl > .x { margin-left:auto; }
    .spl .offw { display:inline-flex; gap:4px; align-items:center; }
    .spa { display:flex; flex-wrap:wrap; gap:6px; min-width:0; } .spa select { flex:1 1 110px; min-width:110px; } .spa input { width:70px; flex:0 0 70px; }
    .daychips { display:flex; gap:3px; margin-top:6px; flex-wrap:wrap; }
    .spo { display:flex; flex-wrap:wrap; gap:4px 14px; margin-top:6px; font-size:12.5px; color:var(--secondary-text-color); align-items:center; }
    .spo .inp { width:66px; padding:2px 5px; } .spo .note { width:140px; }
    .spo label { display:inline-flex; gap:5px; align-items:center; }
    .spc details { margin-top:6px; } .spc summary { cursor:pointer; }
    .condl { display:grid; grid-template-columns:minmax(0,1fr) 90px minmax(0,1.3fr) 26px; gap:6px; align-items:center; margin:4px 0; }
    .condl .inp { width:100%; }
    .cvv { display:flex; gap:4px; min-width:0; } .cvv .inp { flex:1; min-width:0; }
    .grp { border:1px dashed var(--divider-color); border-radius:10px; padding:8px; margin:6px 0; }
    .grph { display:flex; gap:8px; align-items:center; justify-content:space-between; margin-bottom:4px; font-size:13px; flex-wrap:wrap; }
    .grph.root { justify-content:flex-start; }
    .tagrow { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
    .tag { display:inline-flex; align-items:center; gap:6px; background:var(--ha-card-background, var(--card-background-color)); border:1px solid var(--divider-color); border-radius:8px; padding:3px 4px 3px 9px; font-size:13px; }
    .tag small { color:var(--secondary-text-color); } .tag.dyn { border-style:dashed; }
    .tag button { border:0; background:none; color:var(--secondary-text-color); cursor:pointer; font-size:15px; padding:0 4px; }
    .tagin { width:170px; } .mini-in { width:52px; padding:1px 4px; font-size:12px; } .grow { flex:1; min-width:150px; }
    .rstep { display:grid; grid-template-columns:24px minmax(0,1fr) 26px; gap:6px; align-items:start; margin-bottom:6px; }
    .rbody { display:flex; flex-wrap:wrap; gap:6px; align-items:center; font-size:13px; }
    .rbody > .inp { min-width:120px; }
    .epick { position:relative; min-width:0; flex:1; }
    .epick input { width:100%; }
    .pklist { position:absolute; z-index:5; left:0; right:0; top:calc(100% + 4px); max-height:280px; overflow:auto; background:var(--ha-card-background, var(--card-background-color));
      border:1px solid var(--divider-color); border-radius:10px; box-shadow:0 8px 24px rgba(0,0,0,.18); padding:4px; min-width:260px; }
    .pkitem { display:flex; gap:10px; align-items:center; width:100%; text-align:left; border:0; background:none; padding:6px 8px; border-radius:8px; cursor:pointer; font:inherit; color:var(--primary-text-color); }
    .pkitem:hover, .pkitem.on { background:var(--secondary-background-color); }
    .pki { font-size:18px; flex:none; width:24px; text-align:center; }
    .pkt { min-width:0; } .pkt b { display:block; font-weight:500; } .pkt small { display:block; color:var(--secondary-text-color); font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .pkempty { padding:8px; font-size:12.5px; color:var(--secondary-text-color); }
    .pkcur { cursor:pointer; } .pkcur small { margin-left:4px; }
    .rstep .tagrow + .epick { margin-top:6px; }
    .rbody .epick { flex:1 1 220px; } .rbody .tagrow { flex:1 1 100%; }
    .cvv { flex-wrap:wrap; } .cvv .epick { flex:2 1 200px; } .cvv > .inp { flex:1 1 90px; }
    .native { margin-top:14px; } .nat { display:flex; gap:8px; align-items:center; cursor:pointer; }
    .wdk { display:block; font-size:9px; line-height:1; }
    @media (max-width:720px) {
      .frow, .frow.r { grid-template-columns:34px minmax(0,1fr) minmax(0,40%); } .frow .fx { grid-column:2 / -1; } .frow .chev { display:none; }
      .fdetail { padding:6px 12px 14px; }
      .grid3 { grid-template-columns:60px minmax(0,1fr); } .grid3 > :nth-child(3) { grid-column:1 / -1; }
      .condl { grid-template-columns:1fr 1fr 26px; } .condl > :nth-child(3) { grid-column:1 / 3; }
    }
    .err { color:var(--error-color); font-size:13px; margin:6px 0; }
    .sticky { position:sticky; top:70px; }
    @media (max-width: 720px) {
      .wrap { padding:10px 10px 14px; }
      .row { grid-template-columns:34px minmax(0,1fr) 52px 52px 16px; }
      .row .why { grid-column:2 / 5; grid-row:2; }
      .row .chev { grid-row:1; grid-column:5; }
      .detail { padding-left:4px; }
      .cols { grid-template-columns:1fr; padding:12px; }
      .sticky { position:static; }
      .lvls { grid-template-columns:repeat(2,minmax(0,1fr)); }
      .ov { padding:0; align-items:stretch; }
      .dlg { border-radius:0; max-height:100vh; height:100vh; }
      .blk { grid-template-columns:64px auto 64px minmax(0,1fr) 28px; gap:4px; }
    }
  `;


  /**
   * 0.9.13: gemeinsamer Speicher je Home-Assistant-Verbindung. Alle Karten einer Seite (z. B. 15 Raumknöpfe) teilen
   * eine Abfrage `home_rhythm/state` und ein Abo `home_rhythm/subscribe`. Karten melden sich an/ab; die letzte, die
   * verschwindet, beendet das Abo (mit kurzer Verzögerung, damit ein Seitenwechsel nicht neu abonniert).
   */
  class HrStore {
    constructor(conn) { this.conn = conn; this.cards = new Set(); this.data = null; this.error = null; this.at = 0; this._p = null; this._next = null; this._unsub = null; this._subbing = false; }
    add(card) {
      this.cards.add(card); clearTimeout(this._drop);
      if (!this._unsub && !this._subbing) this._subscribe();
    }
    remove(card) {
      this.cards.delete(card);
      if (!this.cards.size) { clearTimeout(this._drop); this._drop = setTimeout(() => this._unsubscribe(), 5000); }
    }
    async _subscribe() {
      this._subbing = true;
      const cb = () => this._soon();
      try { this._unsub = await this.conn.subscribeMessage(cb, { type: "home_rhythm/subscribe" }); }
      catch (e) {  // ältere Integration: HA-Ereignis (nur Admins dürfen es abonnieren)
        try { this._unsub = await this.conn.subscribeEvents(cb, "home_rhythm_updated"); } catch (e2) { this._unsub = null; }
      }
      this._subbing = false;
      if (!this.cards.size) this._unsubscribe();
    }
    _unsubscribe() {
      if (this.cards.size || !this._unsub) return;
      const u = this._unsub; this._unsub = null;
      try { const r = u(); if (r && r.catch) r.catch(() => {}); } catch (e) { /* Verbindung schon zu */ }
    }
    /** Mehrere Meldungen kurz hintereinander = eine Abfrage. */
    _soon() { clearTimeout(this._t); this._t = setTimeout(() => this.fetch(), 250); }
    /** Neu laden; läuft schon eine Abfrage, folgt genau eine weitere (damit Änderungen danach sicher drin sind). */
    fetch() {
      if (!this._p) return this._start();
      if (!this._next) this._next = this._p.then(() => { this._next = null; return this._start(); });
      return this._next;
    }
    _start() {
      this.at = Date.now();
      const p = this._p = this.conn.sendMessagePromise({ type: "home_rhythm/state" })
        .then((d) => { this.data = d; this.error = null; }, (e) => { this.error = e || new Error("Fehler"); })
        .then(() => { if (this._p === p) this._p = null; for (const c of [...this.cards]) { try { c._onStore(this); } catch (e) { console.error(e); } } });
      return p;
    }
    /** Daten für eine neue Karte: vorhandene nehmen, sonst laden (läuft schon eine Abfrage: mitbenutzen). */
    ensure(maxAge = 30000) {
      if (this._p) return this._p;
      if (this.data && Date.now() - this.at < maxAge) return Promise.resolve();
      return this._start();
    }
    /** Gedrosseltes Nachladen (Ist-Werte ändern sich laufend) – egal wie viele Karten fragen. */
    refreshIfOlder(ms) { if (!this._p && Date.now() - this.at > ms) this.fetch(); }
  }
  const HR_STORES = new WeakMap();
  const hrStore = (hass) => {
    const conn = hass.connection;
    let st = HR_STORES.get(conn);
    if (!st) { st = new HrStore(conn); HR_STORES.set(conn, st); }
    return st;
  };
  window.__homeRhythmStore = hrStore;  // für Tests und andere Karten

  class HomeRhythmCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._tab = "overview"; // Startreiter
      this._tlDate = null;      // Übersicht: gewähltes Datum (null = heute)
      this._tlCache = {};       // Datum → Zeitleiste
      this._tlFilter = "all";
      this._tlPast = false;
      this._flowOpen = new Set();
      this._fctlOpen = null;
      this._filter = "all";
      this._open = new Set();
      this._previews = {};
      this._search = "";
      this._data = null;
      this._error = null;
      this._editor = null;
      this._openLogs = new Set();
      this._closedFloors = new Set();
      this._histCache = {};
      this._histHours = 24;
      this._ctlMenu = null;
    }

    setConfig(config) { this._config = config || {}; if (config && config.view) this._tab = config.view; if (this._data) this._render(); }
    getCardSize() { return this._roomMode ? ({ compact: 1, knopf: 1, tablet: 7 }[this._config.layout] || 4) : 8; }
    /** Größe in Abschnitts-Ansichten (sections): 12 Spalten = volle Breite. */
    getGridOptions() {
      if (!this._roomMode) return { columns: "full" };
      return ({
        knopf: { columns: 6, rows: 1, min_columns: 3, min_rows: 1, max_rows: 1 },
        // übrige Formen: volle Breite wie bisher (Standard ohne Angabe), Höhe automatisch – bestehende Dashboards
        // sehen unverändert aus; schmaler ziehen geht bis 6 Spalten
        compact: { columns: 12, min_columns: 6 },
        tablet: { columns: 12, min_columns: 6 },
      })[this._config.layout] || { columns: 12, min_columns: 6 };
    }

    /** Raumkarte? (`room:` oder `area:`) */
    get _roomMode() { const c = this._config || {}; return !!(c.room || c.area); }
    /** Raum der Karte: `room:` hat Vorrang, sonst der erste Home-Rhythm-Raum mit `area:` als Bereich. */
    get _rid() {
      const c = this._config || {};
      if (c.room) return c.room;
      if (!c.area || !this._data) return null;
      const r = (this._data.rooms || []).find((x) => x.area_id === c.area);
      return r ? r.id : null;
    }
    get _knopf() { return this._roomMode && (this._config || {}).layout === "knopf"; }
    static getStubConfig() { return {}; }
    static getConfigElement() { return document.createElement("home-rhythm-card-editor"); }

    set hass(hass) {
      const first = !this._hass;
      this._hass = hass;
      if (first) { this._init(); return; }
      for (const el of Object.values(this._histCache || {})) if (!el._svg) el.hass = hass;
      // Ist-Werte der Thermostate ändern sich laufend → gedrosselt neu laden (einmal für alle Karten der Seite).
      if (!this._editor && !this._fedit) hrStore(hass).refreshIfOlder(30000);
    }

    async _init() {
      // 0.9.13: Fenster als <dialog> mit showModal() – liegen im „Top Layer“ des Browsers, also sicher über der
      // HA-Kopfleiste und werden von Abschnitten / Bearbeiten-Modus (transform, overflow) nicht abgeschnitten.
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="wrap" id="main"></div></ha-card><dialog id="dlg" class="hrdlg"></dialog><dialog id="tdlg" class="hrdlg"></dialog><dialog id="qdlg" class="hrdlg"></dialog>`;
      this._watchDialogs();
      this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
      this.shadowRoot.addEventListener("change", (e) => this._onChange(e));
      this.shadowRoot.addEventListener("input", (e) => this._onInput(e));
      this.shadowRoot.addEventListener("keydown", (e) => {
        if ((e.key === "Enter" || e.key === " ") && e.target.dataset && e.target.dataset.a === "knav") { e.preventDefault(); this._knopfNav(); return; }
        this._pickKey(e);
      });
      this.shadowRoot.addEventListener("focusin", (e) => { const t = e.target; if (t.dataset && t.dataset.a === "pkq" && (!this._pick || this._pick.tgt !== t.dataset.t)) this._openPick(t.dataset.t, t.value); });
      this.shadowRoot.addEventListener("toggle", (e) => {
        const d = e.target;
        if (d && d.dataset && d.dataset.room) (d.open ? this._openLogs.add(d.dataset.room) : this._openLogs.delete(d.dataset.room));
        if (d && d.dataset && d.dataset.ass) this._assOpen = d.open;
      }, true);
      this._join();
    }

    /** Beim gemeinsamen Speicher anmelden; vorhandene Daten sofort zeigen. */
    _join() {
      const st = hrStore(this._hass);
      st.add(this);
      if (st.data || st.error) this._onStore(st);
      st.ensure(30000);
    }

    disconnectedCallback() { if (this._hass) { hrStore(this._hass).remove(this); this._reconnect = true; } }
    connectedCallback() {
      if (this._reconnect && this._hass) { this._reconnect = false; this._join(); }
      this._resyncDialogs();
    }

    /** Fenster-Hosts: Inhalt da → showModal(), leer → schließen. Esc schließt nur das Bedien-Fenster (wie ✕). */
    _watchDialogs() {
      for (const d of this.shadowRoot.querySelectorAll("dialog.hrdlg")) {
        const sync = () => {
          const has = !!d.firstElementChild;
          if (has && !d.open) { try { d.showModal(); } catch (e) { d.setAttribute("open", ""); } }
          else if (!has && d.open) { try { d.close(); } catch (e) { d.removeAttribute("open"); } }
        };
        new MutationObserver(sync).observe(d, { childList: true });
        d.addEventListener("cancel", (e) => {
          e.preventDefault();  // Esc: Editor-Fenster nicht versehentlich verlieren
          if (d.id === "qdlg" && this._q) { this._q = null; this._renderQ(); }
        });
      }
    }

    /** Karte wurde im DOM verschoben (z. B. Bearbeiten-Modus): offenes Fenster fällt aus dem Top Layer → neu öffnen. */
    _resyncDialogs() {
      if (!this.shadowRoot) return;
      for (const d of this.shadowRoot.querySelectorAll("dialog.hrdlg")) {
        if (!d.firstElementChild || (d.open && d.matches(":modal"))) continue;
        try { if (d.open) d.close(); d.showModal(); } catch (e) { /* nicht verbunden */ }
      }
    }

    _ws(msg) { return this._hass.connection.sendMessagePromise(msg); }

    /** Neu laden – für alle Karten der Seite (gemeinsamer Speicher); jede bekommt danach _onStore(). */
    async _fetch() {
      this._lastFetch = Date.now();
      if (this._hass) await hrStore(this._hass).fetch();
    }

    async _onStore(st) {
      this._lastFetch = st.at;
      try {
        if (st.error) throw st.error;
        this._data = st.data;
        this._error = null;
        // Start-Reiter aus der Einrichtung – nur beim ersten Laden und nicht, wenn die Karte „view:“ vorgibt
        if (!this._startTabSet) { this._startTabSet = true; if (!(this._config && this._config.view) && this._data.start_tab) this._tab = this._data.start_tab; }
        NOW_REF = this._data.now;
        for (const k of Object.keys(this._tlCache)) if (k.startsWith(this._data.now.slice(0, 10))) delete this._tlCache[k];  // „Heute“ neu laden (Erledigtes, laufende Reaktionen)
        this._dayCache = {};  // Stand je Viertelstunde neu (Hand-Änderungen, Pläne)
        if (this._q) this._renderQ();
        if (this._sim) this._loadSim();
        for (const id of this._open) this._loadPreview(id);
        if (this._rid && this._config.layout === "tablet" && Date.now() - (this._rcPrevAt || 0) > 600000) { this._rcPrevAt = Date.now(); this._loadPreview(this._rid).then(() => this._render()); }
        // Nach „Workday einrichten“: sobald der Sensor da ist, ohne weiteren Klick übernehmen
        const wd = this._data.requirements && this._data.requirements.items.workday;
        if (this._reqWdWait && this._admin && wd && wd.suggestion && wd.suggestion !== this._reqWdBefore) {
          this._reqWdWait = false;
          await this._ws({ type: "home_rhythm/requirement/set", key: "workday", entity: wd.suggestion });
          this._fetch();
        }
      } catch (e) {
        this._error = e && e.code === "unknown_command"
          ? "Home Rhythm ist noch nicht eingerichtet (Einstellungen → Geräte & Dienste → Integration hinzufügen → Home Rhythm)."
          : (e && e.message) || String(e);
      }
      this._render();
    }

    async _loadPreview(roomId) {
      const room = this._room(roomId);
      if (!room || !(room.climates || []).length) return;
      try {
        const r = await this._ws({ type: "home_rhythm/preview", room: { schedule: room.schedule, levels: room.levels, default_level: room.default_level, manual_mode: room.manual_mode, ac_entities: room.ac_entities || [], ac: room.ac, rules: room.rules || [], party_room: !!room.party_room }, room_id: roomId });
        this._previews[roomId] = r.days;
        const el = this.shadowRoot.getElementById(`wk-${roomId}`);
        if (el) el.innerHTML = this._weekHtml(r.days);
      } catch (e) { /* Vorschau ist optional */ }
    }

    _room(id) { return this._data && this._data.rooms.find((r) => r.id === id); }

    // Thermostat-Dialog von Home Assistant (z. B. Better Thermostat) öffnen
    _moreInfo(entityId) {
      this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
    }

    // ------------------------------------------------------------ Verlauf
    // In Home Assistant: die eingebaute Verlaufskarte (Ist, Soll, Heizen). Ohne sie: eigenes Diagramm aus der History.
    async _mountHistories() {
      for (const box of this.shadowRoot.querySelectorAll(".hist[data-room]")) {
        const room = this._room(box.dataset.room);
        if (!room) continue;
        const ents = (room.climates || []).map((c) => c.entity_id);
        const key = `${room.id}|${this._histHours}|${ents.join(",")}`;
        let el = this._histCache[key];
        if (!el || (el._svg && Date.now() - el._at > 300000)) {
          el = await this._createHistory(ents, this._histHours, room);
          if (!el) continue;
          this._histCache[key] = el;
        }
        if (el.parentNode !== box) { box.innerHTML = ""; box.appendChild(el); }
        if (!el._svg) el.hass = this._hass;
      }
    }

    async _createHistory(ents, hours, room) {
      try {
        if (window.loadCardHelpers) {
          const helpers = await window.loadCardHelpers();
          const card = await helpers.createCardElement({ type: "history-graph", hours_to_show: hours, entities: ents });
          card.hass = this._hass;
          return card;
        }
      } catch (e) { /* weiter mit eigenem Diagramm */ }
      try {
        const start = new Date(Date.now() - hours * 3600e3).toISOString();
        const data = await this._ws({ type: "history/history_during_period", start_time: start, entity_ids: ents, minimal_response: false, no_attributes: false, significant_changes_only: false });
        const div = document.createElement("div");
        div._svg = true; div._at = Date.now();
        div.innerHTML = this._historySvg(data, ents, hours, room);
        return div;
      } catch (e) {
        const div = document.createElement("div");
        div._svg = true; div._at = Date.now();
        div.innerHTML = `<div class="hint">Verlauf nicht verfügbar.</div>`;
        return div;
      }
    }

    _historySvg(data, ents, hours, room) {
      const W = Math.round(Math.max(300, Math.min(1100, (this.getBoundingClientRect().width || 720) - 40))), H = 180, L = 34, R = 8, T = 10, B = 22;
      const end = Date.now(), start = end - hours * 3600e3;
      const x = (t) => L + ((t - start) / (end - start)) * (W - L - R);
      const series = ents.map((e) => (data[e] || []).map((p) => ({ t: (p.lu || p.lc || 0) * 1000, s: p.s, cur: Number(p.a && p.a.current_temperature), set: Number(p.a && p.a.temperature), act: p.a && p.a.hvac_action })).filter((p) => p.t));
      const vals = series.flat().flatMap((p) => [p.cur, p.set]).filter((v) => Number.isFinite(v));
      if (!vals.length) return `<div class="hint">Noch kein Verlauf aufgezeichnet.</div>`;
      const lo = Math.floor(Math.min(...vals) - 0.5), hi = Math.ceil(Math.max(...vals) + 0.5);
      const y = (v) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
      const colors = ["#e8833a", "#2f8fd6", "#7fb563", "#a77bd6"];
      let out = "";
      for (let v = lo; v <= hi; v++) out += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="g"/><text x="${L - 4}" y="${y(v) + 3}" class="ax" text-anchor="end">${v}°</text>`;
      const step = (hours <= 24 ? 6 : hours <= 72 ? 12 : 24) * (W < 500 ? 2 : 1);
      for (let t = Math.ceil(start / (step * 3600e3)) * step * 3600e3; t < end; t += step * 3600e3) {
        const d = new Date(t);
        out += `<text x="${x(t)}" y="${H - 6}" class="ax" text-anchor="middle">${hours > 24 ? d.toLocaleDateString("de-DE", { weekday: "short" }) + " " : ""}${String(d.getHours()).padStart(2, "0")}:00</text>`;
      }
      series.forEach((pts, i) => {
        if (!pts.length) return;
        const col = colors[i % colors.length];
        const seg = (k) => pts.map((p, j) => (Number.isFinite(p[k]) ? `${j && Number.isFinite(pts[j - 1][k]) ? "L" : "M"}${x(p.t).toFixed(1)},${y(p[k]).toFixed(1)}` : "")).join("");
        // Heizen/Kühlen als Fläche
        pts.forEach((p, j) => {
          if (p.act === "heating" || p.act === "cooling") {
            const t2 = j + 1 < pts.length ? pts[j + 1].t : end;
            out += `<rect x="${x(p.t)}" y="${T}" width="${Math.max(1, x(t2) - x(p.t))}" height="${H - T - B}" fill="${p.act === "heating" ? "rgba(232,131,58,.12)" : "rgba(47,143,214,.12)"}"/>`;
          }
        });
        const stepSet = pts.map((p, j) => (Number.isFinite(p.set) ? `${j ? `H${x(p.t).toFixed(1)}V` : `M${x(p.t).toFixed(1)},`}${y(p.set).toFixed(1)}` : "")).join("") + (Number.isFinite(pts[pts.length - 1].set) ? `H${x(end)}` : "");
        out += `<path d="${stepSet}" fill="none" stroke="${col}" stroke-width="1.5" stroke-dasharray="4 3"/>`;
        out += `<path d="${seg("cur")}" fill="none" stroke="${col}" stroke-width="2"/>`;
      });
      const legend = ents.map((e, i) => {
        const c = (room.climates || []).find((x) => x.entity_id === e);
        return `<span><i style="background:${colors[i % colors.length]}"></i>${esc(c ? c.name : e)}</span>`;
      }).join("");
      return `<svg viewBox="0 0 ${W} ${H}" class="hsvg" preserveAspectRatio="none">${out}</svg>
        <div class="legend">${legend}<span>— Ist</span><span>- - Soll</span><span><i style="background:rgba(232,131,58,.35)"></i>heizt</span></div>`;
    }
    get _admin() { return !!(this._hass && this._hass.user && this._hass.user.is_admin); }

    // ------------------------------------------------------------ Rendern
    _render() {
      const main = this.shadowRoot.getElementById("main");
      if (!main) return;
      const card = main.parentElement;
      if (card) { card.classList.toggle("rcmode", this._roomMode); card.classList.toggle("knopf", this._knopf); }
      this.toggleAttribute("knopf", this._knopf);
      if (this._error) { main.innerHTML = `<div class="${this._knopf ? "kmiss" : "empty"}">${esc(this._error)}</div>`; return; }
      if (!this._data) { main.innerHTML = this._knopf ? `<div class="kmiss">Lade …</div>` : `<div class="empty">Lade …</div>`; return; }
      if (this._roomMode) {
        // `area:` ohne passenden Raum: kleine, unauffällige Zeile statt Fehlerkasten
        if (!this._config.room && !this._rid) { main.innerHTML = `<div class="kmiss">kein Home-Rhythm-Raum</div>`; return; }
        main.innerHTML = this._knopf ? this._knopfHtml() : this._roomCardHtml();
        return;
      }
      const tabs = [["overview", "Übersicht", "Übersicht"], ["heat", "Heizung & Klima", "Heizung"], ["flows", "Abläufe", "Abläufe"], ["devices", "Geräte", "Geräte"], ["setup", "Einrichtung", "Setup"]];
      const views = { overview: () => this._reqBanner() + this._headerHtml()
          + `<div class="ovgrid"><div class="ovleft" id="ovleft">${this._ovStateHtml()}</div><div class="ovright" id="ovright">${this._timelineHtml()}</div></div>`, heat: () => this._overviewHtml(),
        flows: () => this._flowsHtml(), devices: () => this._devicesHtml(), setup: () => this._setupHtml() };
      main.innerHTML = `
        <div class="top">
          <div class="title">${this._config.title ? `${LOGO}${esc(this._config.title)}` : WORDMARK}
            ${this._admin ? `<button class="gear" data-a="nav" data-v="/config/integrations/integration/home_rhythm" title="Home Rhythm in Home Assistant konfigurieren (Hausmodi, Energie)">⚙️</button>` : ""}</div>
          <div class="tabs">${tabs.map(([k, n, sh]) => `<button data-a="tab" data-v="${k}" class="${this._tab === k ? "on" : ""}"><span class="l">${n}</span><span class="s">${sh}</span></button>`).join("")}</div>
        </div>
        ${(views[this._tab] || views.overview)()}`;
      this._mountHistories();
    }

    _headerHtml() {
      // 0.9.12: Kopf in einer Zeile – Plan, Hausmodi (ohne Umbruch), Zähler (antippen = Liste), 🕐 Vorschau, ⚙
      const d = this._data, m = d.modes, rooms = d.rooms;
      let icon = "📅", title = "Normaler Wochenplan";
      if (!m.heating_season && !m.cooling_season) [icon, title] = ["☀️", `Heizung aus (${m.season})`];
      else if (m.cooling_season) [icon, title] = m.away ? ["🧳", "Urlaub – Klima aus"] : m.nobody_home ? ["🚪", "Niemand zu Hause – Klima aus"] : ["❄️", "Kühlen nach Plan"];
      else if (m.away) [icon, title] = ["🧳", m.vacation || "Urlaub unterwegs"];
      else if (m.event === "Party") [icon, title] = ["🎉", "Party"];
      else if (m.home_vacation) [icon, title] = ["🏡", "Urlaub zu Hause – Sonntagsplan"];
      else if (m.holiday_today) [icon, title] = ["🎈", "Feiertag – Sonntagsplan"];
      const now = new Date(d.now);
      const sub = `${now.toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "numeric" })} · ${now.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })} Uhr${m.nobody_home ? " · niemand zu Hause" : ""}`;
      const e = d.energy || {};
      const modeChips = [`${m.season}${m.season_auto_possible ? (m.season_auto ? " · automatisch" : " · fest") : ""}`, m.vacation || "kein Urlaub", `Ereignis: ${m.event || "keins"}`];
      if (m.occasion) modeChips.push(m.occasion);
      if (e.outdoor != null) modeChips.push(`außen ${fmtNum(e.outdoor)} °C`);
      const P = this._ovPopData();
      const cnt = Object.entries(P).filter(([, x]) => x.show).map(([k, x]) => `<button class="hcnt ${x.cls || ""} ${this._ovPop === k ? "on" : ""}" data-a="ovpop" data-v="${k}" title="${esc(x.title)} – antippen für die Liste">${esc(x.label)}</button>`).join("");
      const timeOpen = this._pref("ovTimeOpen", false), sim = timeOpen && !this._atNow();
      const pop = this._ovPop && P[this._ovPop] && P[this._ovPop].show ? this._ovPopHtml(this._ovPop, P[this._ovPop]) : "";
      const gear = this._ovGear ? `<div class="ovsub"><b class="hint">Hinweise oben zeigen</b>
          <label><input type="checkbox" data-a="ovopt" data-k="ovBatt" ${this._pref("ovBatt", true) ? "checked" : ""}> 🔋 Batterie</label>
          <label><input type="checkbox" data-a="ovopt" data-k="ovReach" ${this._pref("ovReach", true) ? "checked" : ""}> 📡 Erreichbarkeit</label>
          <label><input type="checkbox" data-a="ovopt" data-k="ovOdd" ${this._pref("ovOdd", true) ? "checked" : ""}> ⚠ auffällige Räume</label></div>` : "";
      return `<div class="tile ovhead"><div class="ovhrow">
          <span class="hico2">${icon}</span><span class="htx"><b>${esc(title)}</b><small>${esc(sub)}</small></span>
          <span class="hpills">${modeChips.map((c) => `<span>${esc(c)}</span>`).join("")}<button class="mini ${this._modesOpen ? "on" : ""}" data-a="modes">${this._modesOpen ? "weniger ⌃" : "mehr ⌄"}</button></span>
          <span class="hcnts">${cnt}</span>
          <button class="btn sm ovtbtn ${sim ? "simb" : ""}" data-a="ovtime" aria-expanded="${timeOpen}">🕐 Vorschau${timeOpen ? " ⌃" : ""}</button>
          <button class="gearb" data-a="ovgear" aria-label="Anzeige-Einstellungen" title="Anzeige-Einstellungen">⚙</button>
        </div>${pop}${gear}${this._modesOpen ? `<div class="ovsub modes">${this._modesHtml()}</div>` : ""}${timeOpen ? this._ovTimeHtml() : ""}</div>`;
    }

    /** Zähler oben rechts und was beim Antippen aufklappt. */
    _ovPopData() {
      const d = this._data, rooms = d.rooms;
      const heatRooms = rooms.filter((x) => (x.climates || []).length);
      const heating = heatRooms.filter((r) => (r.climates || []).some((c) => c.hvac_action === "heating" && c.role !== "ac"));
      const acOn = rooms.filter((r) => (r.climates || []).some((c) => c.role === "ac" && c.state !== "off" && c.state !== "unavailable"));
      const manual = rooms.filter((r) => r.manual), special = rooms.filter((r) => r.today || r.active_rule);
      const allDev = rooms.flatMap((r) => (r.devices || []).map((x) => ({ ...x, roomName: r.name }))).concat((d.flow_devices || []).map((x) => ({ ...x, roomName: "" })));
      const seen = new Set(), uniq = allDev.filter((x) => { const k = x.device_id || x.entity_id; if (seen.has(k)) return false; seen.add(k); return true; });
      const low = uniq.filter((x) => x.battery_low), off = uniq.filter((x) => !x.available);
      const odd = rooms.filter((r) => this._attention(r) && !r.manual);
      const today = d.now.slice(0, 10), yest = isoDate(new Date(Date.parse(today) - 864e5));
      const ferr = ((d.flows && d.flows.items) || []).filter((it) => { const l = (it.log || [])[0]; return l && l.kind === "bad" && l.at.slice(0, 10) >= yest; });
      const use = (x) => (x.uses || []).map((u) => u.text).join(", ") || "nirgends verwendet";
      return {
        heat: { show: true, label: `🔥 ${heating.length}/${heatRooms.length}`, title: "Räume heizen gerade", go: ["tab", "heat"], goLabel: "Zu „Heizung & Klima“",
          items: heating.map((r) => ({ ico: "🔥", name: r.name, info: `${(r.result || {}).level_name || ""} ${fmtTemp((r.result || {}).temperature)}`, val: `Ist ${fmtTemp((r.climate || {}).current_temperature)}`, act: ["goroom", r.id] })) },
        ac: { show: acOn.length > 0, label: `❄️ ${acOn.length}`, title: "Klimaanlagen an", go: ["tab", "heat"], goLabel: "Zu „Heizung & Klima“",
          items: acOn.map((r) => ({ ico: "❄️", name: r.name, info: (r.result || {}).reason || "", val: "", act: ["goroom", r.id] })) },
        hand: { show: manual.length > 0, label: `✋ ${manual.length}`, title: "Hand-Änderungen", go: ["tab", "heat"], goLabel: "Zu „Heizung & Klima“",
          items: manual.map((r) => ({ ico: "✋", name: r.name, info: `${r.manual.hvac_mode === "off" ? "aus" : fmtTemp(r.manual.temperature)} · ${r.manual.source || "von Hand"}`, val: `bis ${fmtTime(r.manual.until)}`, act: ["goroom", r.id], clear: r.id })) },
        special: { show: special.length > 0, label: `★ ${special.length}`, title: "heute anders / Raumregel", go: ["tab", "heat"], goLabel: "Zu „Heizung & Klima“",
          items: special.map((r) => ({ ico: "★", name: r.name, info: r.today ? r.today.label || "heute anders" : r.active_rule || "", val: "", act: ["goroom", r.id] })) },
        batt: { show: low.length > 0 && this._pref("ovBatt", true), label: `🔋 ${low.length}`, title: "Batterien schwach", cls: "w", go: ["devgo", "low"], goLabel: "In Geräte zeigen",
          items: low.map((x) => ({ ico: "🔋", name: x.name, info: `${x.roomName ? x.roomName + " · " : ""}${use(x)}`, val: x.battery != null ? `${fmtNum(x.battery, 0)} %` : "schwach", act: ["more", x.battery_entity || x.entity_id] })) },
        reach: { show: off.length > 0 && this._pref("ovReach", true), label: `📡 ${off.length}`, title: "Geräte nicht erreichbar", cls: "bad", go: ["devgo", "off"], goLabel: "In Geräte zeigen",
          items: off.map((x) => ({ ico: "📡", name: x.name, info: `${x.roomName ? x.roomName + " · " : ""}${use(x)}`, val: x.last_changed ? `seit ${fmtTime(x.last_changed)}` : "", act: ["more", x.entity_id] })) },
        odd: { show: odd.length > 0 && this._pref("ovOdd", true), label: `⚠ ${odd.length}`, title: "Räume auffällig", cls: "w", go: ["tab", "heat"], goLabel: "Zu „Heizung & Klima“",
          items: odd.map((r) => ({ ico: "⚠", name: r.name, info: this._attentionWhy(r), val: "", act: ["goroom", r.id] })) },
        ferr: { show: ferr.length > 0, label: `⚠ ${ferr.length} Ablauf`, title: "Abläufe mit Fehler", cls: "bad", go: ["tab", "flows"], goLabel: "Zu „Abläufe“",
          items: ferr.map((it) => ({ ico: it.icon || "⚠", name: it.name, info: it.log[0].text, val: fmtTime(it.log[0].at), act: ["goflow", it.id] })) },
      };
    }

    _attentionWhy(r) {
      const c = r.climate || {};
      if (!r.enabled) return "pausiert – Home Rhythm steuert nicht";
      if (c.state === "unavailable" || c.state === "unknown" || c.some_unavailable) return "Thermostat nicht erreichbar";
      if ((r.hints || []).length) return "wird auch von anderer Stelle gesteuert";
      const bad = (r.devices || []).filter((x) => x.battery_low || !x.available);
      if (bad.length) return bad.map((x) => `${x.name}: ${x.available ? "Batterie schwach" : "nicht erreichbar"}`).join(" · ");
      if (this._mismatch(r)) return "Thermostat steht anders als geplant";
      return "";
    }

    _ovPopHtml(k, x) {
      return `<div class="ovsub pop"><div class="poph"><b>${esc(x.title)}</b><span class="sp"></span>
          <button class="btn sm" data-a="${x.go[0]}" data-v="${esc(x.go[1])}">${esc(x.goLabel)}</button><button class="x" data-a="ovpop" data-v="${k}" aria-label="Schließen">✕</button></div>
        ${x.items.map((i) => `<div class="popr" data-a="${i.act[0]}" data-v="${esc(i.act[1])}"><span>${esc(i.ico)}</span><b>${esc(i.name)}</b><span class="hint">${esc(i.info)}</span><span class="pv">${esc(i.val)}${i.clear ? ` <button class="lx" data-a="clear" data-v="${esc(i.clear)}" title="Zurück zum Plan">✕</button>` : ""}</span></div>`).join("")}</div>`;
    }

    _modesHtml() {
      const d = this._data, m = d.modes;
      const sel = (label, entity, value, extra = "") => {
        const st = entity && this._hass.states[entity];
        const opts = st && st.attributes.options;
        if (!opts) return `<div class="mode"><label>${label}</label><div class="val">${esc(value || "–")}</div>${extra}</div>`;
        return `<div class="mode"><label>${label}</label><select data-a="mode" data-entity="${esc(entity)}">
          ${opts.map((o) => `<option ${o === st.state ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>${extra}</div>`;
      };
      const avg = m.season_average != null && m.season_average_days >= 2
        ? `Ø ${m.season_average_days} Tage ${fmtNum(m.season_average)} °C → ${esc(m.season_suggestion || "–")}`
        : `sammelt Außentemperatur (${m.season_average_days || 0} von 2 vollen Tagen)`;
      const seasonTile = sel("Jahreszeit", d.entities.season, m.season,
        !m.season_auto_possible ? "" : `<div class="mrow"><button class="mini ${m.season_auto ? "on" : ""}" data-a="seasonauto" data-v="${m.season_auto ? "0" : "1"}" title="Automatisch nach Ø Außentemperatur (unter ${fmtNum(m.winter_below)} °C Winter, über ${fmtNum(m.hot_above)} °C Heißphase); von Hand wählen hält fest">${m.season_auto ? "automatisch" : "festgehalten"}</button><small>${avg}</small></div>`);
      const ev = `<div class="mode"><label>Ereignis</label><select data-a="event">${d.events.map((e) => `<option ${e === m.event ? "selected" : ""}>${esc(e)}</option>`).join("")}</select>
        ${m.event === "Party" && m.party_until ? `<div class="mrow"><small>Party-Räume Komfort bis ${esc(fmtTime(m.party_until))}</small></div>` : m.event === "Gäste" ? `<div class="mrow"><small>Raumregeln mit „Gäste“ aktiv</small></div>` : ""}</div>`;
      const occ = `<div class="mode"><label>Anlass</label><div class="val">${esc(m.occasion || "keiner")}</div><div class="mrow"><small>Weihnachten: 1. Advent bis 6. Januar</small></div></div>`;
      return `<div class="modes">
        ${seasonTile}
        ${sel("Urlaub", d.entities.vacation, m.vacation)}
        ${ev}
        ${occ}
        ${this._energyTile()}
      </div>`;
    }

    _energyTile() {
      const e = this._data.energy;
      if (!e || (!e.outdoor_entities.length && !this._data.rooms.some((r) => (r.ac_entities || []).length))) return "";
      return `<div class="mode" title="Gas ${fmtNum(e.gas_ct, 2)} ct/kWh ÷ ${fmtNum(e.boiler_efficiency * 100, 0)} % = ${fmtNum(e.heat_cost_gas, 1)} ct pro kWh Wärme · Strom ${fmtNum(e.power_ct, 2)} ct/kWh">
        <label>${this._data.modes.cooling_season || !this._data.modes.heating_season ? "Außentemperatur" : `Außen · Klima lohnt ab COP ${fmtNum(e.break_even_cop, 2)}`}</label>
        <div class="val">${e.outdoor == null ? "keine Außentemperatur" : `${fmtNum(e.outdoor)} °C`}${this._data.modes.heating_season ? `<small class="sub2"> · Wärme Gas ${fmtNum(e.heat_cost_gas)} ct</small>` : ""}</div></div>`;
    }

    // ------------------------------------------------------------ Raumkarte (0.9.8): ein Raum fürs Dashboard
    _rcQuick() {
      const d = this._data, q = Array.isArray(this._config.quick) ? this._config.quick : ["komfort", "boost", "today", "off"];
      return q.filter((k) => ["boost", "today", "off"].includes(k) || d.plan_levels.includes(k)).slice(0, 8);
    }

    _rcQuickName(k) {
      return { boost: "Booster 1 Std.", today: "Heute …", off: "Aus …" }[k] || `${this._data.level_names[k] || k} …`;
    }

    _roomCardHtml() {
      const d = this._data, id = this._rid, room = this._room(id);
      const layout = ["compact", "tablet"].includes(this._config.layout) ? this._config.layout : "standard";
      if (!room) return `<div class="empty">Raum „${esc(id)}“ nicht gefunden – Karte bearbeiten und Raum wählen.</div>`;
      const r = room.result || {}, c = room.climate || {};
      const [ico, icoTitle] = this._icon(room);
      const noHeat = !(room.climates || []).length;
      const ist = room.room_temp && room.room_temp.value != null ? room.room_temp.value : c.current_temperature;
      const pend = this._rcPend && this._rcPend.room === id ? this._rcPend.temp : null;
      const off = r.hvac_mode === "off" && pend == null;
      const soll = off ? "aus" : fmtTemp(pend != null ? pend : r.temperature);
      const lvl = room.manual ? "hand" : (r.level || "aus");
      const m = room.manual;
      const line = !room.enabled ? "pausiert – Home Rhythm steuert nicht" : noHeat ? "keine Heizung"
        : m ? `✋ ${m.source && m.source !== "Raumkarte" ? esc(m.source.replace(/^Raumkarte: /, "")) : "Hand-Änderung"} · gilt bis ${fmtTime(m.until)}`
        : `${esc(r.reason || "")}${r.until ? ` · bis ${fmtTime(r.until)}` : ""}${r.next_level_name ? ` → ${esc(r.next_level_name)}` : ""}`;
      const lvlChip = noHeat ? "" : `<span class="lvl" style="background:${COLORS[lvl] || "#888"}">${esc(m ? "Hand" : (r.level_name || lvl))}</span>`;
      const icoBtn = noHeat ? `<span class="rcico">${ico}</span>` : `<button class="rcico icob" data-a="ctl" data-v="${esc(id)}" title="${esc(icoTitle)} – Thermostat einstellen">${ico}</button>`;
      const pm = (sign) => `<button class="rcpm" data-a="rcstep" data-v="${sign}" ${noHeat || !room.enabled ? "disabled" : ""} aria-label="${sign > 0 ? "wärmer" : "kälter"}">${sign > 0 ? "+" : "−"}</button>`;
      const back = m ? `<button class="rcback" data-a="clear" data-v="${esc(id)}">↩ Zurück zum Plan</button>` : "";
      const quick = noHeat || !room.enabled ? "" : `<div class="rcquick">${this._rcQuick().map((k) => `<button data-a="rcq" data-v="${k}" class="${this._rcAsk === k ? "on" : ""}">${esc(this._rcQuickName(k))}</button>`).join("")}</div>`;
      const ask = this._rcAsk ? this._rcAskHtml() : "";
      const menu = this._ctlMenu === id ? `<div class="ctlmenu rcmenu">${(room.climates || []).map((t) => `<button class="btn sm" data-a="more" data-v="${esc(t.entity_id)}">${esc(t.name)}${t.role === "ac" ? " (Klima)" : ""}</button>`).join("")}</div>` : "";
      const valve = (room.climates || []).filter((x) => x.heat && x.heat.heating != null).map((x) => `${esc(x.name)}: ${x.heat.heating ? "heizt – Ventil auf" : "Ventil zu"}${x.heat.pct != null ? ` · ${x.heat.pct} % der letzten Stunde` : ""}`).join(" · ");
      const name = `<button class="rcname" data-a="rcopen" title="Raum aufklappen">${esc(this._config.title || room.name)}</button>`;
      const detail = this._open.has(id) ? `<div class="rcdetail">${this._detailHtml(room)}</div>` : "";
      if (layout === "compact") {
        return `<div class="rc rcc">${icoBtn}<div class="rcmid">${name}<span class="rcline">${line}</span></div>
          <span class="rcist">${fmtTemp(ist)}</span>${pm(-1)}<span class="rcsoll">${soll}</span>${pm(1)}</div>${menu}${back ? `<div class="rcrow">${back}</div>` : ""}
          ${this._open.has(id) || this._rcAsk ? `<div class="rc" style="margin-top:10px">${quick}${ask}</div>` : ""}${detail}`;
      }
      if (layout === "tablet") {
        const today = ((this._previews[id] || []).find((x) => x.today) || null);
        const nowPct = ((new Date().getHours() * 60 + new Date().getMinutes()) / 1440) * 100;
        const bar = today ? `<div class="rcday"><small>Heute</small><div class="bar">${today.slots.map((l) => `<i style="background:${COLORS[l] || "#888"}"></i>`).join("")}<span class="now" style="left:${nowPct}%"></span></div>
          <div class="axis"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div></div>` : "";
        return `<div class="rc rct"><div class="rchead">${icoBtn}${name}<span class="sp"></span>${lvlChip}</div>${menu}
          <div class="rcbig">${pm(-1)}<div class="rcval"><b>${soll}</b><small>im Raum ${fmtTemp(ist)}</small></div>${pm(1)}</div>
          <div class="rcline c">${line}</div>${back ? `<div class="rcrow c">${back}</div>` : ""}${quick}${ask}${bar}
          ${valve ? `<div class="rcvalve">${valve}</div>` : ""}</div>${detail}`;
      }
      return `<div class="rc rcs"><div class="rchead">${icoBtn}${name}<span class="sp"></span>${lvlChip}</div>${menu}
        <div class="rcnums"><div class="rcv"><small>Ist</small><b>${fmtTemp(ist)}</b></div><div class="rcset">${pm(-1)}<div class="rcv c"><small>Soll</small><b class="big">${soll}</b></div>${pm(1)}</div></div>
        <div class="rcline">${line}</div>${back ? `<div class="rcrow">${back}</div>` : ""}${quick}${ask}
        ${valve ? `<div class="rcvalve">${valve}</div>` : ""}</div>${detail}`;
    }


    // ------------------------------------------------------------ Raumknopf (0.9.13): eine Zeile wie eine HA-Kachel
    /** Zustand fürs Symbol – dieselbe Logik wie _icon() in der Übersicht, dazu Farbe. */
    _knopfState(room) {
      const [ico, title] = this._icon(room);
      const col = { "🔥": "var(--state-climate-heat-color, #ff8100)", "💤": "var(--state-climate-idle-color, #8a8a8a)", "⏻": "var(--state-climate-off-color, #8a8a8a)",
        "✋": COLORS.hand, "⚠": "var(--warning-color, #ffa600)", "❄️": "var(--state-climate-cool-color, #2b9af9)", "🏠": "var(--state-inactive-color, #8a8a8a)" }[ico] || "#8a8a8a";
      const key = { "🔥": "heat", "💤": "idle", "⏻": "off", "✋": "hand", "⚠": "unavail", "❄️": "cool", "🏠": "none" }[ico] || "idle";
      return { ico, title, col, key };
    }

    _knopfHtml() {
      const id = this._rid, room = this._room(id), c = this._config;
      if (!room) return `<div class="kmiss">kein Home-Rhythm-Raum</div>`;
      const r = room.result || {}, cl = room.climate || {};
      const st = this._knopfState(room);
      const noHeat = !(room.climates || []).length;
      const ist = room.room_temp && room.room_temp.value != null ? room.room_temp.value : cl.current_temperature;
      const flags = [
        room.today || room.active_rule ? `<span class="star" title="${esc(room.today ? room.today.label || "heute anders" : room.active_rule)}">★</span>` : "",
        (room.hints || []).length || cl.state === "unavailable" || cl.state === "unknown" || cl.some_unavailable ? `<span class="warnmark" title="${esc(this._attentionWhy(room) || "auffällig")}">⚠</span>` : "",
        (room.devices || []).some((x) => x.battery_low) ? `<span class="batmark" title="Batterie schwach">🔋</span>` : "",
      ].join("");
      const soll = r.hvac_mode === "off" ? "aus" : fmtTemp(r.temperature);
      const line = !room.enabled ? `${fmtTemp(ist)} · pausiert` : noHeat ? `${fmtTemp(ist)}`
        : `${fmtTemp(ist)} · ${soll}${room.manual ? ` · ✋ bis ${fmtTime(room.manual.until)}` : ""}`;
      const name = c.name || c.title || room.name;
      const icon = c.icon ? `<ha-icon icon="${esc(c.icon)}"></ha-icon>` : `<span class="kemo">${st.ico}</span>`;
      const icoEl = noHeat
        ? `<span class="kico" style="--kc:${st.col}" title="${esc(st.title)}">${icon}</span>`
        : `<button class="kico" style="--kc:${st.col}" data-a="ctl" data-v="${esc(id)}" title="${esc(st.title)} – Raum bedienen" aria-label="${esc(name)}: ${esc(st.title)} – bedienen">${icon}</button>`;
      return `<div class="kn k-${st.key}" data-a="knav" role="button" tabindex="0" aria-label="${esc(name)}${c.navigation_path ? " – öffnen" : " – bedienen"}">
          ${icoEl}<div class="ktx"><div class="kname"><span class="kn1">${esc(name)}</span>${flags}</div><div class="kline">${line}</div></div></div>`;
    }

    /** Fläche des Knopfs: zu `navigation_path` navigieren, sonst Bedien-Fenster. */
    _knopfNav() {
      const p = this._config.navigation_path;
      if (p) { history.pushState(null, "", p); window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } })); return; }
      const room = this._room(this._rid);
      if (room && (room.climates || []).length) this._qOpenRoom(room.id);
    }

    _rcAskHtml() {
      const k = this._rcAsk, room = this._room(this._rid), r = (room && room.result) || {};
      const next = r.until ? ` (${fmtTime(r.until)})` : "";
      const opts = [["next", `bis zum nächsten Wechsel${next}`], ["m60", "1 Stunde"], ["m120", "2 Stunden"], ["eod", "heute ganztägig"], ["morning", "bis morgen früh (06:00)"]];
      const clock = this._rcClock || (() => { const t = new Date(Date.now() + 2 * 3600e3); return `${String(t.getHours()).padStart(2, "0")}:00`; })();
      return `<div class="rcask"><b>${esc(k === "off" ? "Aus" : this._data.level_names[k] || k)} – bis wann?</b>
        ${opts.map(([v, n]) => `<button data-a="rcuntil" data-v="${v}">${esc(n)}</button>`).join("")}
        <div class="rcclock"><span>bis Uhrzeit</span><input type="time" class="inp" data-a="rcclock" value="${clock}"><button class="pri" data-a="rcuntil" data-v="clock">OK</button>
        <button data-a="rcq" data-v="${k}">abbrechen</button></div>${this._rcErr ? `<div class="hint warn">${esc(this._rcErr)}</div>` : ""}</div>`;
    }

    async _rcClick(a, v, t) {
      const id = this._rid;
      if (a === "rcopen") { if (this._open.has(id)) this._open.delete(id); else { this._open.add(id); this._loadPreview(id); } this._render(); return true; }
      if (a === "rcclock") return true;
      if (a === "rcstep") {
        const room = this._room(id), r = (room && room.result) || {};
        const base = this._rcPend && this._rcPend.room === id ? this._rcPend.temp : (r.hvac_mode === "off" || r.temperature == null ? 20 : r.temperature);
        const step = Number(this._config.step) === 1 ? 1 : 0.5;
        const temp = Math.max(5, Math.min(30, Math.round((base + Number(v) * step) * 2) / 2));
        this._rcPend = { room: id, temp };
        clearTimeout(this._rcTimer);
        this._rcTimer = setTimeout(async () => {  // mehrere Tipper hintereinander = ein Befehl
          const p = this._rcPend; this._rcPend = null;
          try { await this._ws({ type: "home_rhythm/room/manual", room_id: id, temperature: p.temp }); } catch (e) { this._error = null; }
          this._fetch();
        }, 900);
        this._render();
        return true;
      }
      if (a === "rcq") {
        this._rcErr = null;
        if (v === "today") { this._rcAsk = null; this._tdOpen(id); return true; }
        if (v === "boost") { await this._rcSend({ level: "bad", minutes: 60 }); return true; }
        this._rcAsk = this._rcAsk === v ? null : v; this._rcClock = null; this._render();
        return true;
      }
      if (a === "rcuntil") {
        const k = this._rcAsk, msg = k === "off" ? { off: true } : { level: k };
        const pad = (n) => String(n).padStart(2, "0"), now = new Date();
        const at = (d, hm) => { const [h, mi] = hm.split(":").map(Number); const x = new Date(d); x.setHours(h, mi, 0, 0); return x; };
        if (v === "next") msg.until = "next";
        else if (v === "m60") msg.minutes = 60;
        else if (v === "m120") msg.minutes = 120;
        else if (v === "eod") msg.until = at(now, "23:59").toISOString();
        else if (v === "morning") msg.until = at(new Date(now.getTime() + 864e5), "06:00").toISOString();
        else {
          const inp = this.shadowRoot.querySelector('[data-a="rcclock"]'), hm = (inp && inp.value) || "18:00";
          let x = at(now, hm); if (x <= now) x = new Date(x.getTime() + 864e5);  // Uhrzeit schon vorbei → morgen
          msg.until = x.toISOString(); this._rcClock = `${pad(x.getHours())}:${pad(x.getMinutes())}`;
        }
        await this._rcSend(msg);
        return true;
      }
      return false;
    }

    async _rcSend(msg) {
      try {
        await this._ws({ type: "home_rhythm/room/manual", room_id: this._rid, ...msg });
        this._rcAsk = null; this._rcErr = null;
      } catch (e) { this._rcErr = (e && e.message) || String(e); }
      await this._fetch();
    }

    _icon(room) {
      const r = room.result || {}, c = room.climate || {};
      if (!(room.climates || []).length) return ["🏠", "ohne Heizung"];
      if (c.state === "unavailable" || c.state === "unknown" || c.some_unavailable) return ["⚠", "Thermostat nicht erreichbar"];
      if (r.rule === "man" || room.manual) return ["✋", "Hand-Änderung"];
      if ((room.climates || []).some((d) => d.hvac_action === "cooling")) return ["❄️", "kühlt"];
      if (c.state === "off" || r.hvac_mode === "off") return ["⏻", "aus"];
      if (c.hvac_action === "heating") return ["🔥", "heizt"];
      return ["💤", "Leerlauf"];
    }

    _attention(room) {
      const c = room.climate || {}, r = room.result || {};
      if (!(room.climates || []).length) return (room.devices || []).some((x) => x.battery_low || !x.available);
      if (!room.enabled) return true;
      if (c.state === "unavailable" || c.state === "unknown" || c.some_unavailable) return true;
      if (r.rule === "man" || room.manual || (room.hints || []).length) return true;
      if ((room.devices || []).some((x) => x.battery_low || !x.available)) return true;
      return this._mismatch(room);
    }

    _mismatch(room) {
      const r = room.result || {};
      if (r.hvac_mode === "off" || r.temperature == null) return false;
      return (room.climates || []).some((d) => {
        const want = d.result && d.result.temperature != null ? d.result.temperature : r.temperature;
        if (d.state === "unavailable" || d.state === "unknown" || (d.result && (d.result.rule === "man" || d.result.hvac_mode === "off"))) return false;
        return d.state === "off" || (d.temperature != null && Math.abs(d.temperature - want) > 0.25);
      });
    }

    _grouped(rooms) {
      const d = this._data;
      const areaFloor = Object.fromEntries(d.areas.map((a) => [a.id, a.floor_id]));
      const floors = [...d.floors].sort((a, b) => (b.level ?? 0) - (a.level ?? 0));
      const groups = floors.map((f) => ({ name: f.name, rooms: rooms.filter((r) => areaFloor[r.area_id] === f.id) }));
      const rest = rooms.filter((r) => !areaFloor[r.area_id] || !floors.some((f) => f.id === areaFloor[r.area_id]));
      if (rest.length) groups.push({ name: floors.length ? "Ohne Etage" : "", rooms: rest });
      return groups.filter((g) => g.rooms.length);
    }

    _overviewHtml() {
      const all = this._data.rooms;
      if (!all.length) {
        return `<div class="empty">Noch keine Räume.<br><br>${this._admin ? `<button class="btn pri" data-a="tab" data-v="setup">Räume einrichten</button>` : "Ein Administrator kann Räume unter „Einrichtung“ anlegen."}</div>`;
      }
      const f = this._filter;
      const rooms = all.filter((r) => f === "all" || (f === "att" && this._attention(r)) || (f === "heat" && (r.climate || {}).hvac_action === "heating"));
      const n = (fn) => all.filter(fn).length;
      const chips = [["all", `Alle ${all.length}`], ["att", `Auffällig ${n((r) => this._attention(r))}`], ["heat", `Heizt ${n((r) => (r.climate || {}).hvac_action === "heating")}`]];
      return `<div class="filters">${chips.map(([k, l]) => `<button class="chip ${f === k ? "on" : ""}" data-a="filter" data-v="${k}">${l}</button>`).join("")}</div>
        ${rooms.length ? this._grouped(rooms).map((g) => {
          const closed = this._closedFloors.has(g.name);
          const heat = g.rooms.filter((r) => (r.climate || {}).hvac_action === "heating").length;
          const att = g.rooms.filter((r) => this._attention(r)).length;
          const sum = `${g.rooms.length} ${g.rooms.length === 1 ? "Raum" : "Räume"} · ${heat} heizen${att ? ` · ${att} auffällig` : ""}`;
          return `${g.name ? `<div class="floor fl" data-a="floor" data-v="${esc(g.name)}"><span>${closed ? "›" : "⌄"} ${esc(g.name)}</span><small>${sum}</small></div>` : ""}${closed ? "" : `<div class="tile list">${g.rooms.map((r) => this._roomHtml(r)).join("")}</div>`}`;
        }).join("") : `<div class="empty">Nichts auffällig.</div>`}
        <div class="legend">${this._data.plan_levels.concat(["urlaub", "hand", "aus"]).concat(this._data.modes.cooling_season ? ["kuehlen", "vorkuehlen"] : []).map((l) => `<span><i style="background:${COLORS[l]}"></i>${esc(this._data.level_names[l])}</span>`).join("")}</div>`;
    }

    _roomHtml(room) {
      const r = room.result || {}, c = room.climate || {};
      const [ico, icoTitle] = this._icon(room);
      const open = this._open.has(room.id);
      const soll = r.hvac_mode === "off" ? "aus" : fmtTemp(r.temperature);
      const until = r.until ? ` · bis ${fmtTime(r.until)}` : "";
      const lvl = r.level || "aus";
      const noHeat = !(room.climates || []).length;
      const planned = room.today && room.today.planned ? ` · ⏱ ab ${fmtTime(room.today.start)}: ${room.today.label}` : "";
      const reason = !room.enabled ? "pausiert – Home Rhythm steuert nicht" : noHeat ? "keine Heizung" : `${r.reason || ""}${until}${planned}`;
      return `<div class="room ${open ? "open" : ""}">
        <div class="row" data-a="toggle" data-v="${esc(room.id)}">
          ${noHeat ? `<span class="ico" title="${esc(icoTitle)}">${ico}</span>` : `<button class="ico icob" data-a="ctl" data-v="${esc(room.id)}" title="${esc(icoTitle)} – Thermostat einstellen">${ico}</button>`}
          <div class="name">${esc(room.name)}${room.today || room.active_rule ? ` <span class="star" title="${esc(room.today ? (room.today.planned ? "Ausnahme geplant" : "Heute anders / Ausnahme") : room.active_rule)}">★</span>` : ""}${(room.hints || []).length ? ` <span class="warnmark" title="Wird auch von anderer Stelle gesteuert">⚠</span>` : ""}${(room.devices || []).some((x) => x.battery_low) ? ` <span class="batmark" title="Batterie schwach">🔋</span>` : ""}${room.humidity && room.humidity.value != null ? `<small class="hum" title="Luftfeuchte">💧 ${fmtNum(room.humidity.value, 0)} %</small>` : ""}</div>
          <div class="num">${fmtTemp(c.current_temperature)}<small>Ist</small></div>
          <div class="num">${noHeat ? "–" : soll}<small>Soll</small></div>
          <div class="why">${noHeat ? "" : `<span class="lvl" style="background:${COLORS[lvl] || "#888"}">${esc(r.level_name || lvl)}${room.manual ? ` <button class="lx" data-a="clear" data-v="${esc(room.id)}" title="Hand-Änderung verwerfen – zurück zum Plan" aria-label="Zurück zum Plan">✕</button>` : ""}</span>`}${room.energy && r.hvac_mode !== "off" && ["plan", "hol", "man", "today", "party", "room"].includes(r.rule) ? `<span class="src ${room.energy.source}" title="${esc(room.energy.reason)}">${room.energy.source === "ac" ? (room.energy.boost ? "Klima + Gas" : "Klima") : "Gas"}</span>` : ""}<span class="txt">${esc(reason)}</span></div>
          <div class="chev">›</div>
        </div>
        ${this._ctlMenu === room.id ? `<div class="ctlmenu">${(room.climates || []).map((t) => `<button class="btn sm" data-a="more" data-v="${esc(t.entity_id)}">${esc(t.name)}${t.role === "ac" ? " (Klima)" : ""}</button>`).join("")}</div>` : ""}
        ${open ? this._detailHtml(room) : ""}
      </div>`;
    }

    /** Art / misst mit / Korrektur + Hinweise (0.9.5) – nur, wenn etwas Neues eingestellt ist oder es Hinweise gibt. */
    _rtHtml(room) {
      const rt = room.room_temp;
      if (!rt) return "";
      const plain = rt.source === "device" && rt.correction === "none" && !rt.integration_sensor && !(rt.checks || []).length;
      if (plain) return "";
      const kindName = (RT_KINDS.find(([k]) => k === rt.kind) || [, rt.kind])[1];
      const intName = rt.kind === "bt" ? "Better Thermostat" : "der Regel-Integration";
      let measure;
      if (rt.integration_sensor) measure = `${esc(rt.integration_sensor.name)}, ${fmtTemp(rt.integration_sensor.value)} (aus ${intName})`;
      else if (rt.source === "sensors") measure = rt.value == null ? "Raumsensoren – kein aktueller Wert" : (rt.sensors.filter((x) => !x.stale).length > 1 ? `Durchschnitt aus ${rt.sensors.filter((x) => !x.stale).length} Sensoren, ${fmtTemp(rt.value)}` : `${esc((rt.sensors.find((x) => !x.stale) || {}).name || "")}, ${fmtTemp(rt.value)}`);
      else if (rt.source === "box") measure = `${esc((rt.sensors[0] || {}).name || "")}, ${fmtTemp(rt.value)} (in der Fritz!Box eingestellt)`;
      else measure = "Fühler am Thermostat";
      let corr;
      if (rt.kind === "bt" || rt.kind === "integration") corr = `macht ${intName}`;
      else if (rt.source === "box") corr = "macht die Fritz!Box";
      else if (rt.push && rt.push.length) corr = rt.push.map((x) => x.value != null ? `Raumwert ${fmtTemp(x.value)} an ${esc(x.name)} gesendet (${esc(fmtTime(x.at))})` : `Raumwert wird an ${esc(x.name)} gesendet`).join(" · ");
      else if (rt.correction === "fixed") corr = `${rt.correction_value > 0 ? "+" : ""}${fmtNum(rt.correction_value, 1)} °C fest`;
      else if (rt.correction === "observe") corr = rt.observe && rt.observe.n ? `beobachtet: Fühler bei geschlossenem Ventil im Schnitt ${rt.observe.mean > 0 ? "+" : ""}${fmtNum(rt.observe.mean, 1)} °C gegenüber dem Raum (${rt.observe.n} Messungen, 7 Tage)` : "beobachten – noch keine Messung (Ventil muss 1 Std. zu sein)";
      else corr = "keine";
      return `<div class="rtlines"><div><span>Art:</span> <b>${esc(kindName)}</b></div><div><span>Misst mit:</span> <b>${measure}</b></div><div><span>Korrektur:</span> <b>${corr}</b></div>
        ${rt.correction === "observe" && this._admin ? `<button class="btn" data-a="rtexport" data-v="${esc(room.id)}">Beobachtung exportieren (CSV)</button>` : ""}</div>
        ${(rt.checks || []).map((x) => `<div class="rtwarn">⚠ ${esc(x)}</div>`).join("")}`;
    }

    async _rtExport(roomId) {
      try {
        const r = await this._ws({ type: "home_rhythm/observe/export", room_id: roomId });
        const blob = new Blob(["\ufeff" + r.csv], { type: "text/csv;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = r.filename;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      } catch (e) { /* Export ist optional */ }
    }

    /** Ventil-Zustand (0.9.6): heizt / zu, seit wann, Anteil der letzten Stunde. */
    _heatHtml(h) {
      if (!h) return "";
      const pct = h.pct != null ? Math.max(0, Math.min(100, Math.round(h.pct))) : null;
      return `<div class="heatln"><span class="hchip ${h.heating ? "on" : ""}">${h.heating ? "🔥 heizt – Ventil auf" : "💤 Ventil zu"}</span>
        ${pct != null ? `<span class="hbar"><i style="width:${pct}%"></i></span><span>${pct} % der letzten Stunde geheizt</span>` : ""}
        <small>seit ${esc(fmtTime(h.since))}</small></div>`;
    }

    _detailHtml(room) {
      const r = room.result || {}, c = room.climate || {}, m = room.manual;
      const mismatch = this._mismatch(room);
      return `<div class="detail">
        <div class="facts">
          ${room.energy ? `<div class="dev"><span>Wärmequelle:</span> <b>${esc(room.energy.source === "ac" ? "Klimaanlage" : "Heizkörper (Gas)")}</b> <span>– ${esc(room.energy.reason)}</span></div>
          <div class="dev"><span>Kosten pro kWh Wärme:</span> <b>Gas ${fmtNum(room.energy.cost_gas)} ct</b>${room.energy.cost_ac != null ? ` · <b>Klima ${fmtNum(room.energy.cost_ac)} ct</b> <span>(COP ${fmtNum(room.energy.cop_now, 2)} bei ${fmtNum(room.energy.outdoor)} °C)</span>` : ""}</div>` : ""}
          <div><span>Grund:</span> <b>${esc(r.reason || "–")}</b></div>
          <div><span>Gilt bis:</span> <b>${r.until ? esc(fmtTime(r.until)) : "–"}</b>${r.next_level_name ? ` <span>→ ${esc(r.next_level_name)}</span>` : ""}</div>
          ${(room.climates || []).map((t) => `<div class="dev"><span>${t.result && t.result.rule === "man" ? "✋ " : ""}${esc(t.name)}${t.role === "ac" ? '<span class="badge">Klima</span>' : ""}:</span> ${(room.climates || []).length > 1 && t.result ? t.result.hvac_mode === "off" ? `<span>Soll aus ·</span> ` :  `<span>Soll ${fmtTemp(t.result.temperature)}${t.result.rule === "man" && t.result.until ? ` bis ${esc(fmtTime(t.result.until))}` : ""} ·</span> ` : ""}<b>${t.state === "unavailable" || t.state === "unknown" ? "nicht erreichbar" : t.state === "off" ? "aus" : `${fmtTemp(t.temperature)} eingestellt`}</b>${t.current_temperature != null ? ` <span>· Ist ${fmtTemp(t.current_temperature)}</span>` : ""}${t.hvac_action === "heating" ? " 🔥" : ""}${this._heatHtml(t.heat)}</div>`).join("")}
          ${m ? `<div><span>Hand-Änderung:</span> <b>${esc(m.source || "")}</b></div>` : ""}
        </div>
        ${this._rtHtml(room)}
        ${this._todayHtml(room)}
        ${this._foreignHtml(room)}
        ${mismatch ? `<div class="warnbox">Das Thermostat steht noch nicht auf dem Sollwert. Funk-Thermostate übernehmen Werte oft erst nach einigen Minuten; Home Rhythm sendet nach 10 Minuten erneut.</div>` : ""}
        <div class="week" id="wk-${esc(room.id)}">${this._previews[room.id] ? this._weekHtml(this._previews[room.id]) : `<span></span><span class="hint">Woche wird geladen …</span>`}</div>
        <div class="histhd"><b>Verlauf</b>${[[24, "24 h"], [72, "3 Tage"], [168, "7 Tage"]].map(([h, n]) => `<button class="seg ${this._histHours === h ? "on" : ""}" data-a="histh" data-v="${h}">${n}</button>`).join("")}</div>
        <div class="hist" data-room="${esc(room.id)}"></div>
        <div class="actions">
          ${m ? `<button class="btn pri" data-a="clear" data-v="${esc(room.id)}">Zurück zum Plan</button>` : ""}
          ${this._admin ? `<button class="btn" data-a="edit" data-v="${esc(room.id)}">Zeiten bearbeiten</button>` : ""}
          ${(room.climates || []).map((t) => `<button class="btn" data-a="more" data-v="${esc(t.entity_id)}">${(room.climates || []).length > 1 ? esc(t.name) : "Thermostat öffnen"}</button>`).join("")}
        </div>
      </div>`;
    }

    _todayHtml(room) {
      const t = room.today;
      const label = !t ? "normal" : t.label;
      const info = !t ? "" : t.planned ? `geplant ab ${fmtTime(t.start)}` : t.kind === "stufe" ? "" : `bis ${fmtTime(t.until)}`;
      return `<div class="todaybar"><span class="tl">Heute:</span>
        <button class="seg ${t ? "on" : ""}" data-a="tdopen" data-v="${esc(room.id)}">${t && t.planned ? "⏱ " : ""}${esc(label)} ▾</button>
        ${info ? `<small>${esc(info)}</small>` : ""}
        ${t ? `<button class="linkbtn" data-a="tdreset" data-v="${esc(room.id)}">zurück zu normal</button>` : ""}</div>
        ${room.rule_texts && room.rule_texts.length ? `<div class="rules">${room.rule_texts.map((x) => `<span class="${x === room.active_rule ? "act" : ""}">${x === room.active_rule ? "★ " : ""}${esc(x)}</span>`).join("")}</div>` : ""}`;
    }

    // ------------------------------------------------------------ „Heute“ / Ausnahme (Fenster)
    _tdOpen(roomId) {
      const room = this._room(roomId), t = room && room.today;
      const now = new Date(), pad = (n) => String(n).padStart(2, "0");
      const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, hm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
      const tomorrow = new Date(now.getTime() + 864e5);
      const draft = { room: roomId, kind: "normal", level: null, start: "now", from: hm(new Date(Math.ceil(now.getTime() / 9e5) * 9e5)), startDate: iso(tomorrow),
        end: "eod", to: "17:00", endDate: iso(tomorrow), dur: "today", durDate: iso(new Date(now.getTime() + 2 * 864e5)), error: null };
      if (t) {
        draft.kind = t.kind === "komfort" ? "stufe" : t.kind;
        if (t.kind === "komfort") draft.level = "komfort";
        if (t.kind === "stufe") {
          draft.level = t.level;
          const st = new Date(t.start), en = new Date(t.until);
          if (t.planned) { draft.start = iso(st) === iso(now) ? "time" : "date"; draft.from = hm(st); draft.startDate = iso(st); }
          const endDay = new Date(en.getTime() - 6e4);
          if (hm(en) === "00:00" && iso(endDay) === iso(st)) draft.end = "eod";
          else if (iso(en) === iso(st)) { draft.end = "time"; draft.to = hm(en); }
          else { draft.end = "date"; draft.to = hm(en); draft.endDate = iso(en); }
        } else if (t.kind !== "party") {
          const last = iso(new Date(new Date(t.until).getTime() - 6e4));
          draft.dur = last === iso(now) ? "today" : last === iso(tomorrow) ? "tomorrow" : "date";
          draft.durDate = last;
        }
      }
      this._td = draft;
      this._renderToday();
    }

    _tdClose() { this._td = null; this._renderToday(); }

    /** Beginn/Ende der Ausnahme als Date (lokale Zeit des Browsers). */
    _tdTimes(d) {
      const now = new Date(), at = (day, hm) => { const [h, m] = String(hm || "0:0").split(":").map(Number); const x = new Date(day + "T00:00:00"); x.setHours(h, m || 0, 0, 0); return x; };
      const pad = (n) => String(n).padStart(2, "0"), today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
      let start = d.start === "now" ? null : d.start === "time" ? at(today, d.from) : at(d.startDate, d.from);
      if (start && start <= now) start = null;
      const ref = start || now, refDay = `${ref.getFullYear()}-${pad(ref.getMonth() + 1)}-${pad(ref.getDate())}`;
      let end;
      if (d.end === "eod") { end = at(refDay, "00:00"); end.setDate(end.getDate() + 1); }
      else if (d.end === "time") { end = at(refDay, d.to); if (end <= ref) end.setDate(end.getDate() + 1); }
      else end = at(d.endDate, d.to);
      return { start, end };
    }

    _tdSummary(d) {
      const n = this._data.level_names;
      if (d.kind === "normal") return "Normaler Plan.";
      if (d.kind === "stufe") {
        if (!d.level) return "Bitte eine Stufe wählen.";
        const { start, end } = this._tdTimes(d), f = (x) => fmtTime(x.toISOString());
        const temp = (this._room(d.room) || {}).levels ? (this._room(d.room).levels[d.level] ?? this._data.level_defs[d.level].temp) : "";
        return `${n[d.level]}${temp !== "" ? ` (${fmtTemp(temp)})` : ""} ${start ? "ab " + f(start) : "ab jetzt"} bis ${f(end)}. Außerhalb läuft der Plan.`;
      }
      if (d.kind === "party") return "Komfort bis 1 Uhr nachts, danach Plan.";
      const what = { sonntag: "Sonntagsplan", werktag: "Plan Mo–Fr", leer: "niemand im Raum (Absenkung, nachts nicht wärmer als der Plan)" }[d.kind];
      const day = new Date(d.durDate + "T12:00:00"), dayTxt = `${["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"][day.getDay()]} ${day.getDate()}.${day.getMonth() + 1}.`;
      const until = d.dur === "today" ? "heute" : d.dur === "tomorrow" ? "heute und morgen" : `bis einschließlich ${dayTxt}`;
      return `${what} – ${until}. Danach wieder Plan.`;
    }

    /** Heutiger Balken mit der Ausnahme (nur für „Stufe“ – die übrigen Arten zeigt die Wochenansicht nach dem Übernehmen). */
    _tdBar(d) {
      const days = this._previews[d.room];
      if (!days || d.kind !== "stufe" || !d.level) return "";
      const today = days.find((x) => x.today);
      if (!today) return "";
      const { start, end } = this._tdTimes(d), now = new Date(), base = new Date(now); base.setHours(0, 0, 0, 0);
      const slots = today.slots.map((l, i) => { const t = new Date(base.getTime() + (i * 30 + 15) * 6e4); return t >= (start || now) && t < end ? d.level : l; });
      return `<div class="tdbar">${slots.map((l) => `<i style="background:${COLORS[l] || "#888"}" title="${esc(this._data.level_names[l] || l)}"></i>`).join("")}</div>
        <div class="tdax"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>`;
    }

    _renderToday() {
      const host = this.shadowRoot.getElementById("tdlg");
      if (!host) return;
      const d = this._td;
      if (!d) { host.innerHTML = ""; return; }
      const room = this._room(d.room);
      if (!room) { this._td = null; host.innerHTML = ""; return; }
      if (!this._previews[d.room] && !d.previewTried) {  // Wochenvorschau für den Balken einmal nachladen
        d.previewTried = true;
        this._loadPreview(d.room).finally(() => { if (this._td === d) this._renderToday(); });
      }
      const pill = (on, a, v, label, extra = "") => `<button class="seg big ${on ? "on" : ""}" data-a="${a}" data-v="${esc(v)}"${extra}>${label}</button>`;
      const names = this._data.level_names, levels = this._data.plan_levels;
      const temp = (l) => (room.levels && room.levels[l] != null ? room.levels[l] : (this._data.level_defs[l] || {}).temp);
      const lvl = levels.map((l) => pill(d.kind === "stufe" && d.level === l, "tdlevel", l, `<span class="dot" style="background:${COLORS[l] || "#888"}"></span>${esc(names[l])} <small>${fmtTemp(temp(l))}</small>`)).join("");
      const timeIn = (f, v, lab) => `<input class="inp" type="time" aria-label="${lab}" data-a="tdin" data-f="${f}" value="${esc(v)}">`;
      const dateIn = (f, v, lab) => `<input class="inp" type="date" aria-label="${lab}" data-a="tdin" data-f="${f}" value="${esc(v)}">`;
      const span = d.kind === "stufe" && d.level ? `<div class="tdsec"><h3>Zeitraum</h3>
          <div class="tdrow"><span class="tdl">von</span>${pill(d.start === "now", "tdset", "start:now", "jetzt")}${pill(d.start === "time", "tdset", "start:time", "Uhrzeit")}${pill(d.start === "date", "tdset", "start:date", "anderer Tag")}
            ${d.start === "date" ? dateIn("startDate", d.startDate, "Beginn Tag") : ""}${d.start !== "now" ? timeIn("from", d.from, "Beginn") : ""}</div>
          <div class="tdrow"><span class="tdl">bis</span>${pill(d.end === "eod", "tdset", "end:eod", "Tagesende")}${pill(d.end === "time", "tdset", "end:time", "Uhrzeit")}${pill(d.end === "date", "tdset", "end:date", "späterer Tag")}
            ${d.end === "date" ? dateIn("endDate", d.endDate, "Ende Tag") : ""}${d.end !== "eod" ? timeIn("to", d.to, "Ende") : ""}</div></div>` : "";
      const whole = ["sonntag", "werktag", "leer"].includes(d.kind) ? `<div class="tdsec"><h3>Gilt</h3><div class="tdrow">
          ${pill(d.dur === "today", "tdset", "dur:today", "nur heute")}${pill(d.dur === "tomorrow", "tdset", "dur:tomorrow", "heute und morgen")}${pill(d.dur === "date", "tdset", "dur:date", "bis einschließlich")}
          ${d.dur === "date" ? dateIn("durDate", d.durDate, "letzter Tag") : ""}</div></div>` : "";
      host.innerHTML = `<div class="ov" data-a="tdov"><div class="dlg tddlg" role="dialog" aria-modal="true" aria-label="Heute für ${esc(room.name)}">
        <header><h2>Heute für ${esc(room.name)}</h2><button class="x" data-a="tdclose" aria-label="Schließen">✕</button></header>
        <div class="tdbody">
          <div class="tdsec"><h3>Stufe</h3><div class="tdrow">${lvl}</div></div>
          ${span}
          <div class="tdsec"><h3>Wie ein anderer Tag</h3><div class="tdrow">${pill(d.kind === "normal", "tdkind", "normal", "normal (Plan)")}${pill(d.kind === "werktag", "tdkind", "werktag", "wie Mo–Fr")}${pill(d.kind === "sonntag", "tdkind", "sonntag", "wie Sonntag")}</div></div>
          <div class="tdsec"><h3>Besonderes</h3><div class="tdrow">${pill(d.kind === "party", "tdkind", "party", "Party bis 1 Uhr")}${pill(d.kind === "leer", "tdkind", "leer", "niemand im Raum")}</div></div>
          ${whole}
          <div class="tdprev">${this._tdBar(d)}<div>${esc(this._tdSummary(d))}</div>${d.error ? `<div class="err">${esc(d.error)}</div>` : ""}</div>
        </div>
        <footer><span class="sp"></span><button class="btn" data-a="tdclose">Abbrechen</button><button class="btn pri" data-a="tdapply" ${d.kind === "stufe" && !d.level ? "disabled" : ""}>Übernehmen</button></footer>
      </div></div>`;
    }

    async _tdApply() {
      const d = this._td;
      if (!d) return;
      const msg = { type: "home_rhythm/today/set", room_id: d.room, kind: d.kind };
      if (d.kind === "stufe") {
        const { start, end } = this._tdTimes(d);
        Object.assign(msg, { level: d.level, start: start ? start.toISOString() : null, end: end.toISOString() });
      } else if (["sonntag", "werktag", "leer"].includes(d.kind) && d.dur !== "today") {
        const t = new Date(Date.now() + 864e5), pad = (n) => String(n).padStart(2, "0");
        msg.until_day = d.dur === "tomorrow" ? `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}` : d.durDate;
      }
      try {
        await this._ws(msg);
        delete this._previews[d.room];
        this._tdClose();
        await this._fetch();
        if (this._open.has(d.room)) this._loadPreview(d.room);
      } catch (e) {
        d.error = (e && e.message) || String(e);
        this._renderToday();
      }
    }

    /** Klicks im Fenster „Heute“. */
    async _tdClick(a, v, t, e) {
      if (!a.startsWith("td")) return false;
      const d = this._td;
      if (a === "tdopen") this._tdOpen(v);
      else if (a === "tdreset") { await this._ws({ type: "home_rhythm/today/set", room_id: v, kind: "normal" }); delete this._previews[v]; await this._fetch(); if (this._open.has(v)) this._loadPreview(v); }
      else if (a === "tdov") { if (e.target === t) this._tdClose(); }
      else if (a === "tdclose") this._tdClose();
      else if (a === "tdapply") await this._tdApply();
      else if (!d) return true;
      else if (a === "tdlevel") { d.kind = "stufe"; d.level = v; d.error = null; this._renderToday(); }
      else if (a === "tdkind") { d.kind = v; d.error = null; this._renderToday(); }
      else if (a === "tdset") { const [k, val] = v.split(":"); d[k] = val; d.error = null; this._renderToday(); }
      return true;
    }

    _foreignHtml(room) {
      const hints = room.hints || [], log = room.foreign || [];
      if (!hints.length && !log.length && !room.dismissed_count) return "";
      const devName = (eid) => this._climateName(eid);
      const hintRow = (h) => `<div class="hintrow"><span>⚠ ${esc(h.text)}${(room.climates || []).length > 1 ? ` <small>(${esc(devName(h.entity_id))})</small>` : ""}</span>
        <span class="hbtns">${h.config_id && h.source && h.source.startsWith("automation.") ? `<button class="btn sm" data-a="nav" data-v="/config/automation/edit/${esc(h.config_id)}">Öffnen</button>` : h.source && h.source.startsWith("script.") ? `<button class="btn sm" data-a="nav" data-v="/config/script/edit/${esc(h.source.split(".")[1])}">Öffnen</button>` : ""}
        ${this._admin ? `<button class="btn sm" data-a="dismiss" data-v="${esc(h.id)}">ist gewollt</button>` : ""}</span></div>`;
      return `<div class="foreign">
        ${hints.length ? `<div class="fh">Wird auch von anderer Stelle gesteuert</div>${hints.map(hintRow).join("")}` : ""}
        ${room.dismissed_count && this._admin ? `<button class="linkbtn" data-a="resethints" data-v="${esc(room.id)}">${room.dismissed_count} ausgeblendete${room.dismissed_count > 1 ? "" : "n"} Hinweis${room.dismissed_count > 1 ? "e" : ""} wieder zeigen</button>` : ""}
        ${log.length ? `<details data-room="${esc(room.id)}" ${this._openLogs.has(room.id) ? "open" : ""}><summary>Zuletzt von außen geändert (${log.length})</summary>${log.map((e) => `<div class="logrow"><span>${esc(fmtTime(e.at))}</span><span>${esc(devName(e.entity_id))}</span><b>${esc(e.value)}</b><span>${esc(e.name)}${e.note ? ` · <i>${esc(e.note)}</i>` : ""}</span></div>`).join("")}</details>` : ""}
      </div>`;
    }

    _weekHtml(days) {
      const now = new Date();
      const nowPct = ((now.getHours() * 60 + now.getMinutes()) / 1440) * 100;
      const typeName = { wd: "", sa: "", so: "" };
      return days.map((d, i) => {
        const cells = d.slots.map((l) => `<i style="background:${COLORS[l] || "#888"}" title="${esc(this._data.level_names[l] || l)}"></i>`).join("");
        const normal = i < 5 ? "wd" : i === 5 ? "sa" : "so";
        const special = d.day_type !== normal;  // Feiertag / Urlaub zu Hause / „wie Sonntag“ → anderer Plan
        const planName = { wd: "Werktagsplan", sa: "Samstagsplan", so: "Sonntagsplan" }[d.day_type];
        const hol = special ? ` title="${planName}"` : "";
        return `<div class="d ${d.today ? "today" : ""}"${hol}>${DAYS[i]}${special ? "*" : ""}${typeName[d.day_type]}</div>
          <div class="bar">${cells}${d.today ? `<span class="now" style="left:${nowPct}%"></span>` : ""}</div>`;
      }).join("") + `<div class="axis"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>`;
    }

    _setupHtml() {
      if (!this._admin) return `<div class="empty">Die Einrichtung ist nur für Administratoren.</div>`;
      const d = this._data;
      const q = this._search.trim().toLowerCase();
      const roomsByEntity = Object.fromEntries(d.rooms.flatMap((r) => [...r.climate_entities, ...(r.ac_entities || [])].map((e) => [e, r])));
      const areaName = Object.fromEntries(d.areas.map((a) => [a.id, a.name]));
      const floors = [...d.floors].sort((a, b) => (b.level ?? 0) - (a.level ?? 0));
      const areasOf = (fid) => d.areas.filter((a) => a.floor_id === fid);
      const noFloor = d.areas.filter((a) => !a.floor_id || !floors.some((f) => f.id === a.floor_id));
      const groups = floors.map((f) => [f.name, areasOf(f.id)]);
      if (noFloor.length) groups.push([floors.length ? "Ohne Etage" : "Bereiche", noFloor]);
      const unassigned = d.climates.filter((c) => !c.area_id || !areaName[c.area_id]);
      const wrappedCount = d.climates.filter((c) => c.wrapped_by).length;

      const areaRow = (area) => {
        const climates = d.climates.filter((c) => c.area_id === area.id);
        const rooms = d.rooms.filter((r) => r.area_id === area.id || climates.some((c) => r.climate_entities.includes(c.entity_id) || (r.ac_entities || []).includes(c.entity_id)));
        const free = climates.filter((c) => !roomsByEntity[c.entity_id] && !c.wrapped_by);
        if (q && !area.name.toLowerCase().includes(q) && !climates.some((c) => c.name.toLowerCase().includes(q))) return "";
        if (!climates.length && !rooms.length && !q) return "";
        const sub = rooms.length
          ? rooms.map((r) => `${rooms.length > 1 || r.name !== area.name ? esc(r.name) + ": " : ""}${[...r.climate_entities, ...(r.ac_entities || [])].map((e) => esc(this._climateName(e)) + (this._wrapper(e) ? `<span class="badge">${this._wrapper(e)}</span>` : "") + ((r.ac_entities || []).includes(e) ? '<span class="badge">Klima</span>' : "")).join(", ")}${r.enabled ? "" : " (pausiert)"}`).join(" · ")
          + (rooms.length && free.length ? ` · <b>nicht gesteuert:</b> ${free.map((c) => esc(c.name)).join(", ")}` : "")
          : free.length ? `Vorschlag: ${free.map((c) => esc(c.name) + (c.wrapper ? `<span class="badge">${c.wrapper}</span>` : "")).join(", ")}` : "Kein Thermostat in diesem Bereich";
        const btns = rooms.map((r) => `<button class="btn" data-a="edit" data-v="${esc(r.id)}">${rooms.length > 1 ? esc(r.name) : "Bearbeiten"}</button>`).join(" ")
          + (free.length ? ` <button class="btn ${rooms.length ? "" : "pri"}" data-a="add" data-v="${esc(area.id)}">Hinzufügen</button>` : "");
        return `<div class="area"><div><div class="name">${esc(area.name)}</div><div class="sub">${sub}</div></div><div>${btns}</div></div>`;
      };
      const html = groups.map(([name, areas]) => {
        const rows = areas.map(areaRow).join("");
        return rows ? `<div class="floor">${esc(name)}</div><div class="tile list">${rows}</div>` : "";
      }).join("");
      return `
        ${this._reqHtml()}
        ${this._levelsHtml()}
        <div class="hint">Räume sind Bereiche aus Home Assistant. Ein Raum kann mehrere Thermostate haben (Fritz!DECT, Better Thermostat, Zigbee, Klimaanlage …), alle folgen demselben Plan. Rollläden, Licht und Steckdosen richtest du unter „Abläufe“ ein.</div>
        ${wrappedCount ? `<div class="hint">${wrappedCount} Thermostat${wrappedCount > 1 ? "e stecken" : " steckt"} in Better Thermostat (BT) oder Versatile Thermostat (VT) und ${wrappedCount > 1 ? "werden" : "wird"} nur darüber gesteuert – sie erscheinen hier nicht einzeln.</div>` : ""}
        <input type="search" placeholder="Bereich oder Thermostat suchen" data-a="search" value="${esc(this._search)}">
        ${html || `<div class="empty">Keine Bereiche mit Thermostat gefunden.</div>`}
        ${unassigned.some((c) => !roomsByEntity[c.entity_id] && !c.wrapped_by) ? `<div class="floor">Thermostate ohne Bereich</div><div class="tile list">${unassigned.filter((c) => !roomsByEntity[c.entity_id] && !c.wrapped_by).map((c) => `<div class="area"><div><div class="name">${esc(c.name)}${c.wrapper ? `<span class="badge">${c.wrapper}</span>` : ""}</div><div class="sub">${esc(c.entity_id)}</div></div><div><button class="btn" data-a="add-entity" data-v="${esc(c.entity_id)}">Hinzufügen</button></div></div>`).join("")}</div>` : ""}
        <div class="actions"><button class="btn" data-a="add" data-v="">Raum ohne Vorschlag anlegen</button></div>
        <div class="sech"><h2>Weiteres</h2></div>
        <div class="setg">
          <div class="tile setc"><span class="sico">🧭</span><div><b>Hausmodi, Helfer &amp; Energie</b><div class="hint">Jahreszeit, Urlaub, Arbeitstag, Anwesenheit, Außensensoren, Gas- und Strompreis</div></div>
            <button class="btn" data-a="nav" data-v="/config/integrations/integration/home_rhythm">In HA öffnen</button></div>
          <div class="tile setc"><span class="sico">🗂️</span><div><b>Start-Reiter</b><div class="hint">Mit welchem Reiter Home Rhythm öffnet (für alle Nutzer).</div></div>
            <select data-a="starttab">${[["overview", "Übersicht"], ["heat", "Heizung & Klima"], ["flows", "Abläufe"], ["devices", "Geräte"], ["setup", "Einrichtung"]].map(([k, n]) => `<option value="${k}" ${(d.start_tab || "overview") === k ? "selected" : ""}>${n}</option>`).join("")}</select></div>
          <div class="tile setc"><span class="sico">💾</span><div><b>Sicherung</b><div class="hint">Räume, Stufen und Abläufe als Datei. Protokolle, Hand-Änderungen und Benutzernamen sind nicht enthalten.</div>${this._importMsg ? `<div class="hint"><b>${esc(this._importMsg)}</b></div>` : ""}</div>
            <span class="btnrow"><button class="btn" data-a="export">Export</button><label class="btn">Import<input type="file" accept=".json,application/json" data-a="import" hidden></label></span></div>
          <div class="tile setc"><span class="sico">ℹ️</span><div><b>Home Rhythm ${esc(VERSION)}</b><div class="hint">Läuft komplett lokal in Home Assistant – keine Cloud, keine Daten nach außen.</div></div>
            <button class="btn" data-a="nav" data-v="/config/integrations/integration/home_rhythm">Integration</button></div>
        </div>`;
    }

    // ------------------------------------------------------------ Voraussetzungen (Einrichtung)
    _reqBanner() {
      const R = this._data.requirements;
      if (!R || !R.missing.length) return "";
      const names = { season: "Jahreszeit", vacation: "Urlaub", workday: "Workday (Feiertage)" };
      const what = R.missing.includes("season") ? "Bis dahin wird immer geheizt." : R.missing.includes("vacation") ? "Urlaub wird nicht erkannt." : "Feiertage werden nicht erkannt.";
      return `<div class="warnbox reqban"><span>${R.missing.length === 1 ? "Es fehlt" : "Es fehlen"}: <b>${esc(R.missing.map((k) => names[k]).join(", "))}</b>. ${esc(what)}</span>
        ${this._admin ? `<button class="btn sm" data-a="reqgo">Zu den Voraussetzungen</button>` : `<span class="hint">Ein Administrator kann das unter „Einrichtung“ beheben.</span>`}</div>`;
    }

    _reqHtml() {
      const R = this._data.requirements;
      if (!R) return "";
      const I = R.items, st = (this._hass && this._hass.states) || {};
      const SYM = { ok: ["✓", "rok", "vorhanden"], missing: ["!", "rwarn", "fehlt"], unset: ["!", "rwarn", "fehlt"], none: ["–", "rnone", "bewusst ohne"], info: ["i", "rinfo", "Info"] };
      const nm = (e) => (st[e] && st[e].attributes.friendly_name) || e;
      const pickList = (key) => {
        const doms = { season: ["input_select", "select"], vacation: ["input_select", "select"], workday: ["binary_sensor"], outdoor: ["sensor", "weather"] }[key];
        return Object.keys(st).filter((e) => doms.includes(e.split(".")[0])).filter((e) => {
          const a = st[e].attributes || {};
          if (key === "workday") return /workday|arbeitstag|feiertag/i.test(e + " " + (a.friendly_name || ""));
          if (key === "outdoor") return e.startsWith("weather.") || a.device_class === "temperature";
          return (a.options || []).length > 0;
        }).sort((a, b) => nm(a).localeCompare(nm(b)));
      };
      const why = { season: "Steuert Heizen, Kühlen und alles mit „Jahreszeit ist …“.", vacation: "Urlaub unterwegs → Absenkung; Urlaub zu Hause → wie eingestellt (z. B. wie Wochenende).",
        workday: "Für Feiertage nach Bundesland. Eingerichtet wird Workday über den normalen Dialog von Home Assistant.", outdoor: "Optional: für die automatische Jahreszeit und die Wahl zwischen Klimaanlage und Heizkörper." };
      const title = { season: "Jahreszeit", vacation: "Urlaub", workday: "Arbeitstag und Feiertage (Workday)", outdoor: "Außentemperatur" };
      const row = (key) => {
        const it = I[key], [sym, cls, lab] = SYM[it.status];
        let text;
        if (it.status === "ok") text = it.entities.map((e, j) => `${esc(it.names[j])}${it.names[j] !== e ? ` <small>${esc(e)}</small>` : ""}`).join(", ")
          + (it.options ? ` · ${esc(it.options.join(" / "))}` : "") + (it.detail ? ` · ${esc(it.detail)}` : "")
          + (it.states[0] != null ? ` · gerade: <b>${esc(key === "workday" ? (it.states[0] === "on" ? "Arbeitstag" : "frei") : it.states[0])}</b>` : "");
        else if (it.status === "missing") text = `„${esc(it.entities.join(", "))}“ ist eingestellt, gibt es aber nicht (mehr).`;
        else if (it.status === "none") text = esc(it.without);
        else text = key === "outdoor" ? "Kein Sensor gewählt (optional)." : "Nicht eingestellt.";
        if (this._reqWdWait && key === "workday" && it.status !== "ok") text = "Der Dialog von Home Assistant ist offen. Home Rhythm übernimmt den Sensor, sobald er fertig ist.";
        const btn = (a, label, pri, extra = "") => `<button class="btn sm ${pri ? "pri" : ""}" data-a="${a}" data-v="${key}" ${extra}>${label}</button>`;
        let btns = "";
        if (this._admin) {
          if (it.suggestion) btns += btn("reqset", `Übernehmen: ${esc(nm(it.suggestion))}`, true, `data-e="${esc(it.suggestion)}"`);
          if (it.status !== "ok" && R.new_helpers[key]) btns += btn("reqnew", "Anlegen", !it.suggestion);
          if (it.status !== "ok" && key === "workday") btns += btn("reqwd", "Workday einrichten", !it.suggestion);
          btns += btn("reqpick", it.status === "ok" ? "Ändern" : "Vorhandenen wählen");
          if (it.status !== "none" && it.status !== "ok") btns += btn("reqnone", "Ohne");
          if (this._reqPick === key) btns += `<select class="inp" data-a="reqsel" data-v="${key}" aria-label="${esc(title[key])} wählen"><option value="">– wählen –</option>${pickList(key).map((e) => `<option value="${esc(e)}">${esc(nm(e))} (${esc(e)})</option>`).join("")}</select>`;
        }
        return `<div class="rqrow"><span class="rqs ${cls}" title="${lab}" aria-label="${lab}">${sym}</span>
          <div class="rqt"><b>${title[key]}</b><div>${text}</div><small class="hint">${esc(why[key])}</small></div><div class="btnrow">${btns}</div></div>`;
      };
      const p = I.presence;
      const pres = `<div class="rqrow"><span class="rqs ${p.persons ? "rok" : "rinfo"}">${p.persons ? "✓" : "i"}</span>
        <div class="rqt"><b>Anwesenheit</b><div>${p.entities.length ? `${esc(nm(p.entities[0]))}${nm(p.entities[0]) !== p.entities[0] ? ` <small>${esc(p.entities[0])}</small>` : ""} · ` : "nicht eingestellt · "}${p.persons} ${p.persons === 1 ? "Person" : "Personen"} mit Standort${p.persons ? ` · gerade: <b>${p.nobody_home ? "niemand zu Hause" : "jemand zu Hause"}</b>` : ""}</div>
        <small class="hint">${p.persons ? "Für „niemand zu Hause“ (Licht aus, Klima aus)." : "Ohne Personen mit Standort (Companion-App) wird „niemand zu Hause“ nie erkannt – kein Fehler, nur eine Info."}</small></div>
        <div class="btnrow">${this._admin ? `<button class="btn sm" data-a="nav" data-v="/config/integrations/integration/home_rhythm">Einstellungen</button>` : ""}</div></div>`;
      const m = this._data.modes;
      const auto = `<div class="rqrow"><span class="rqs ${R.season_auto ? "rok" : "rnone"}">${R.season_auto ? "✓" : "–"}</span>
        <div class="rqt"><label class="inl" style="color:inherit"><input type="checkbox" data-a="reqauto" ${R.season_auto ? "checked" : ""} ${R.season_auto_possible && this._admin ? "" : "disabled"}> <b>Jahreszeit automatisch umstellen</b></label>
        <small class="hint">${!R.season_auto_possible ? "Braucht den Jahreszeit-Helfer und einen Außentemperatur-Sensor."
          : `Einmal täglich nach 4 Uhr nach Ø der letzten 3 Tage (unter ${fmtNum(m.winter_below)} °C Winter, über ${fmtNum(m.hot_above)} °C Heißphase). Wer die Jahreszeit von Hand wählt, hält sie fest.${m.season_average != null ? ` Ø gerade ${fmtNum(m.season_average)} °C.` : ""}`}</small></div><div></div></div>`;
      const open = this._reqOpen ?? R.missing.length > 0;
      const okCount = ["season", "vacation", "workday", "outdoor"].filter((k) => I[k].status === "ok").length;
      return `<div class="lvlbox" id="reqbox">
        <div class="floor fl" data-a="reqopen"><span>${open ? "⌄" : "›"} Voraussetzungen</span><small>${R.missing.length ? `<b class="bad">${R.missing.length} fehlt</b> · ` : ""}${okCount} von 4 vorhanden</small></div>
        ${open ? `<div class="tile list rq">${row("season")}${row("vacation")}${row("workday")}${pres}${row("outdoor")}${auto}</div>
          <div class="hint">Angelegt wird nur nach Klick und nur von einem Admin – als ganz normaler Helfer in Home Assistant (Einstellungen → Helfer).</div>` : ""}</div>`;
    }

    async _reqCall(msg) {
      try { await this._ws(msg); } catch (e) { alert((e && e.message) || String(e)); }
      await this._fetch();
    }

    async _reqClick(a, v, t) {
      if (a === "reqgo") { this._tab = "setup"; this._reqOpen = true; this._render(); const el = this.shadowRoot.getElementById("reqbox"); if (el) el.scrollIntoView({ behavior: "smooth" }); return; }
      if (a === "reqopen") { this._reqOpen = !(this._reqOpen ?? this._data.requirements.missing.length > 0); this._render(); return; }
      if (a === "reqpick") { this._reqPick = this._reqPick === v ? null : v; this._render(); return; }
      if (a === "reqset") return this._reqCall({ type: "home_rhythm/requirement/set", key: v, entity: t.dataset.e });
      if (a === "reqnone") return this._reqCall({ type: "home_rhythm/requirement/set", key: v, none: true });
      if (a === "reqwd") {
        this._reqWdWait = true;
        this._reqWdBefore = this._data.requirements.items.workday.suggestion || null;  // nur einen neu angelegten Sensor übernehmen
        this._render();
        history.pushState(null, "", "/config/integrations/dashboard/add?domain=workday");
        window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
        return;
      }
      if (a === "reqnew") {
        try { await this._reqNew(v); } catch (e) { alert((e && e.message) || String(e)); }
        await this._fetch();
      }
    }

    async _reqNew(key) {
      const h = this._data.requirements.new_helpers[key];
      if (!confirm(`Helfer „${h.name}“ mit ${h.options.join(" / ")} in Home Assistant anlegen und hier eintragen?`)) return;
      const res = await this._ws({ type: "input_select/create", name: h.name, options: h.options, icon: h.icon });
      const eid = `input_select.${res.id}`;
      for (let i = 0; i < 10; i++) {  // der Helfer erscheint kurz nach dem Anlegen
        try { await this._ws({ type: "home_rhythm/requirement/set", key, entity: eid }); return; }
        catch (e) { if (i === 9) throw e; await new Promise((r) => setTimeout(r, 300)); }
      }
    }

    _levelsHtml() {
      const d = this._data;
      const defs = this._levelDraft || clone(d.level_defs);
      const keys = Object.keys(defs);
      const open = this._levelsOpen;
      return `<div class="lvlbox">
        <div class="floor fl" data-a="levelsopen"><span>${open ? "⌄" : "›"} Stufen</span><small>${esc(d.plan_levels.map((l) => d.level_names[l]).join(" · "))}</small></div>
        ${open ? `<div class="hint">Namen gelten für alle Räume, die Temperaturen hier sind die Vorgabe für neue Räume (pro Raum im Raum-Editor änderbar). <br><b>Raum belegt</b>: In dieser Stufe ist jemand im Raum – im Sommer kühlt die Klimaanlage dann (bei den anderen Stufen nicht). <b>Wählbar</b>: Die Stufe erscheint im Zeitplan und in den Regeln; die vier Grundstufen sind immer wählbar, eigene Stufen kannst du ausblenden.</div>
        <div class="lvlgrid"><span></span><span class="h">Name</span><span class="h">Vorgabe</span><span class="h" title="Jemand ist im Raum – im Sommer wird gekühlt">Raum belegt</span><span class="h" title="Im Zeitplan und in Regeln auswählbar">wählbar</span>
        ${keys.map((k) => { const v = defs[k], base = ["komfort", "absenkung", "nacht", "bad"].includes(k); return `
          <i style="background:${COLORS[k]}"></i>
          <input type="text" maxlength="24" value="${esc(v.name)}" data-a="lvldef" data-k="${k}" data-f="name" ${!base && !v.enabled ? "disabled" : ""}>
          <span class="inl"><input type="number" step="0.5" min="5" max="30" value="${v.temp}" data-a="lvldef" data-k="${k}" data-f="temp" ${!base && !v.enabled ? "disabled" : ""}> °C</span>
          <input type="checkbox" data-a="lvldef" data-k="${k}" data-f="use" ${v.use ? "checked" : ""} ${!base && !v.enabled ? "disabled" : ""}>
          ${base ? `<span class="hint" title="Grundstufen sind immer wählbar">✓ fest</span>` : `<input type="checkbox" data-a="lvldef" data-k="${k}" data-f="enabled" ${v.enabled ? "checked" : ""}>`}`; }).join("")}
        </div>
        ${this._levelErr ? `<div class="err">${esc(this._levelErr)}</div>` : ""}
        <div class="actions"><button class="btn pri" data-a="lvlsave" ${this._levelDraft ? "" : "disabled"}>Stufen speichern</button>${this._levelDraft ? `<button class="btn" data-a="lvlcancel">Verwerfen</button>` : ""}</div>` : ""}
      </div>`;
    }

    _devicesHtml() {
      // 0.9.11: Suche, Filter (Zustand / Art / Verwendung), Etagen und Räume zuklappbar, Spalten an/aus – alles gemerkt
      const d = this._data, st = this._devFilter || "all", ty = this._pref("devType", "all"), use = this._pref("devUse", "all");
      const hideUnused = this._pref("devHideUnused", false), colB = this._pref("devColBatt", true), colR = this._pref("devColReach", true), colH = this._pref("devColHum", true);
      const closed = new Set(this._pref("devClosed", []));
      const q = (this._devQ || "").toLowerCase().split(/\s+/).filter(Boolean);
      const typeOf = (x) => /Thermostat|Regler|Klimaanlage/.test(x.role) ? "thermo" : x.role === "Bedienteil" || x.role === "Taster" ? "control" : x.role === "Sensor" && !x.flowOnly ? "sensor" : x.flowOnly ? "flow" : "sensor";
      const roomDevs = d.rooms.flatMap((r) => (r.devices || []).map((x) => ({ ...x, room: r })));
      const known = new Set(roomDevs.map((x) => x.device_id || x.entity_id));
      const flowDevs = (d.flow_devices || []).filter((x) => !known.has(x.device_id || x.entity_id)).map((x) => ({ ...x, flowOnly: true }));
      const all = roomDevs.concat(flowDevs);
      const uses = (x) => x.uses || (x.flows || []).map((n) => ({ kind: "flow", text: `Zeitplan ${n}` }));
      const used = (x) => uses(x).length > 0;
      const bad = (x) => x.battery_low || !x.available;
      const pass = (x) => (st === "all" || (st === "prob" && bad(x)) || (st === "low" && x.battery_low) || (st === "off" && !x.available))
        && (ty === "all" || typeOf(x) === ty)
        && (use === "all" || (use === "none" ? !used(x) : uses(x).some((u) => u.kind === use)))
        && (!hideUnused || used(x) || st !== "all")
        && q.every((w) => `${x.name} ${x.model || ""} ${x.role} ${x.room ? x.room.name : ""} ${uses(x).map((u) => u.text).join(" ")}`.toLowerCase().includes(w));
      const filtering = st !== "all" || ty !== "all" || use !== "all" || q.length > 0;
      const n = (fn) => all.filter(fn).length;
      const chip = (act, k, cur, label) => `<button class="chip ${cur === k ? "on" : ""}" data-a="${act}" data-v="${k}">${esc(label)}</button>`;
      const bar = (x) => x.battery == null ? (x.battery_low == null || !x.battery_entity ? `<span class="hint">–</span>` : `<span class="${x.battery_low ? "bad" : ""}">${x.battery_low ? "schwach" : "ok"}</span>`)
        : `<span class="batt ${x.battery_low ? "low" : ""}"><i style="width:${Math.max(4, Math.min(100, x.battery))}%"></i></span><b class="${x.battery_low ? "bad" : ""}">${fmtNum(x.battery, 0)} %</b>`;
      const useTags = (x) => {
        const u = uses(x);
        if (!u.length) return `<span class="utag none">– nirgends verwendet (nur zur Info)</span>`;
        return u.map((t) => {
          const act = t.flow ? `data-a="goflow" data-v="${esc(t.flow)}"` : t.room ? `data-a="tab" data-v="heat"` : "";
          return `<button class="utag ${t.kind === "heat" ? "heat" : "flow"} ${t.off ? "off" : ""}" ${act}>${t.kind === "heat" ? "🔥" : esc(t.icon || "⏱")} ${esc(t.text)}${t.off ? " (aus)" : ""}</button>`;
        }).join("");
      };
      const cols = ["minmax(0,1fr)", colB ? "150px" : "", colR ? "150px" : ""].filter(Boolean).join(" ");
      const row = (x) => `<div class="devrow2" style="grid-template-columns:${cols}">
          <span class="dn"><span data-a="more" data-v="${esc(x.battery_entity || x.entity_id)}" class="dnn">${esc(x.name)}</span><small>${esc(x.role)}${x.model ? " · " + esc(x.model) : ""}</small><span class="utags">${useTags(x)}</span></span>
          ${colB ? `<span class="db">${bar(x)}</span>` : ""}
          ${colR ? `<span class="da">${x.available ? `<span class="ok">● erreichbar</span>` : `<span class="bad">● nicht erreichbar</span>`}${!x.available && x.last_changed ? `<small>seit ${esc(fmtTime(x.last_changed))}</small>` : ""}</span>` : ""}
        </div>`;
      const badChip = (list) => { const k = list.filter(bad).length; return k ? `<span class="chip warnc">⚠ ${k}</span>` : ""; };
      let shown = 0;
      const groups = this._grouped(d.rooms).map((g, gi) => {
        const fk = `f:${g.name || gi}`, fClosed = !filtering && closed.has(fk);
        const roomsHtml = g.rooms.map((r) => {
          const devs = (r.devices || []).map((x) => ({ ...x, room: r })), hit = devs.filter(pass);
          shown += hit.length;
          if (!hit.length) return "";
          const rk = `r:${r.id}`, rClosed = !filtering && closed.has(rk);
          return `<div class="devroom2"><button class="ovfh" data-a="devfold" data-v="${esc(rk)}" aria-expanded="${!rClosed}"><span class="chev ${rClosed ? "" : "open"}">▸</span><b>${esc(r.name)}</b>
              ${colH && r.humidity && r.humidity.value != null ? `<small class="hum">💧 ${fmtNum(r.humidity.value, 0)} %</small>` : ""}<small>${devs.length} Gerät${devs.length === 1 ? "" : "e"}${filtering ? ` · ${hit.length} passend` : ""}</small><span class="sp"></span>${badChip(devs)}</button>
            ${rClosed ? "" : hit.map(row).join("")}</div>`;
        }).join("");
        if (!roomsHtml) return "";
        const devsAll = g.rooms.flatMap((r) => r.devices || []);
        return `<div class="tile ovfloor"><button class="ovfh floorh" data-a="devfold" data-v="${esc(fk)}" aria-expanded="${!fClosed}"><span class="chev ${fClosed ? "" : "open"}">▸</span><b>${esc(g.name || "Räume")}</b>
            <small>${g.rooms.length} ${g.rooms.length === 1 ? "Raum" : "Räume"} · ${devsAll.length} Gerät${devsAll.length === 1 ? "" : "e"}</small><span class="sp"></span>${devsAll.some(bad) ? badChip(devsAll) : `<span class="chip okc">✓ alles ok</span>`}</button>
          ${fClosed ? "" : roomsHtml}</div>`;
      }).join("");
      const fHit = flowDevs.filter(pass);
      shown += fHit.length;
      const fk = "f:abl", fClosed = !filtering && closed.has(fk);
      const flowGroup = fHit.length ? `<div class="tile ovfloor"><button class="ovfh floorh" data-a="devfold" data-v="${fk}" aria-expanded="${!fClosed}"><span class="chev ${fClosed ? "" : "open"}">▸</span><b>Geräte der Abläufe</b>
          <small>ohne Heizungs-Raum · ${flowDevs.length} Geräte</small><span class="sp"></span>${flowDevs.some(bad) ? badChip(flowDevs) : `<span class="chip okc">✓ alles ok</span>`}</button>
          ${fClosed ? "" : fHit.map(row).join("")}</div>` : "";
      return `<div class="tile devbar">
          <div class="btnrow"><input class="inp" type="search" data-a="devq" value="${esc(this._devQ || "")}" placeholder="🔍 Gerät, Raum, Modell oder Verwendung suchen" aria-label="Geräte suchen" style="flex:1;min-width:200px">
            <button class="btn sm" data-a="devfoldall" data-v="open">alle aufklappen</button><button class="btn sm" data-a="devfoldall" data-v="close">alle zuklappen</button></div>
          <div class="filters"><span class="flab">Zustand</span>${[["all", `Alle ${all.length}`], ["prob", `⚠ Probleme ${n(bad)}`], ["low", `🔋 Batterie schwach ${n((x) => x.battery_low)}`], ["off", `📡 nicht erreichbar ${n((x) => !x.available)}`]].map(([k, l]) => chip("devfilter", k, st, l)).join("")}</div>
          <div class="filters"><span class="flab">Art</span>${[["all", "Alle"], ["thermo", "Thermostate"], ["sensor", "Sensoren"], ["control", "Bedienteile & Taster"], ["flow", "Geräte der Abläufe"]].map(([k, l]) => chip("devtype", k, ty, l)).join("")}</div>
          <div class="filters"><span class="flab">Verwendet</span>${[["all", "überall"], ["heat", `🔥 in der Heizung ${n((x) => uses(x).some((u) => u.kind === "heat"))}`], ["flow", `⏱ in Abläufen ${n((x) => uses(x).some((u) => u.kind === "flow"))}`], ["none", `nirgends ${n((x) => !used(x))}`]].map(([k, l]) => chip("devuse", k, use, l)).join("")}</div>
          <div class="filters devopts"><span class="flab">Anzeigen</span>
            <label><input type="checkbox" data-a="devpref" data-k="devHideUnused" ${hideUnused ? "checked" : ""}> nicht verwendete ausblenden</label>
            <label><input type="checkbox" data-a="devpref" data-k="devColBatt" ${colB ? "checked" : ""}> Batterie</label>
            <label><input type="checkbox" data-a="devpref" data-k="devColReach" ${colR ? "checked" : ""}> Erreichbarkeit</label>
            <label><input type="checkbox" data-a="devpref" data-k="devColHum" ${colH ? "checked" : ""}> Luftfeuchte</label></div>
        </div>
        <div class="hint" style="margin:6px 4px 10px">${filtering ? `${shown} von ${all.length} Geräten passen – Etagen und Räume sind dafür aufgeklappt.` : `${all.length} Geräte.`} Schilder: wofür Home Rhythm das Gerät benutzt (🔥 Heizung, ⏱ Abläufe) – antippen öffnet die Stelle, der Name öffnet das Gerät in Home Assistant. Schwach heißt: ${d.battery_low} % oder weniger bzw. Batterie-Warnung des Geräts.</div>
        ${groups + flowGroup || `<div class="empty">${filtering ? "✓ Nichts gefunden – mit diesem Filter ist alles in Ordnung." : "Noch keine Räume eingerichtet."}</div>`}`;
    }

    _wrapper(eid) { const c = this._data.climates.find((x) => x.entity_id === eid); return c && c.wrapper; }

    _climateName(eid) {
      const c = this._data.climates.find((x) => x.entity_id === eid);
      return c ? c.name : eid;
    }

    // ------------------------------------------------------------ Übersicht: Zeitleiste
    // Alles, was an einem Tag passiert: Heizung, Zeitpläne, (heute) ausgelöste Reaktionen.
    _tlKey() { return this._tlDay() + "|" + JSON.stringify(this._assumeReq()); }
    _tlDay() { return this._tlDate || this._data.now.slice(0, 10); }

    async _loadTimeline(key) {
      if (this._tlLoading === key) return;
      this._tlLoading = key;
      const [day] = key.split("|");
      try { this._tlCache[key] = await this._ws({ type: "home_rhythm/timeline", date: day, assume: this._assumeReq() }); }
      catch (e) { this._tlCache[key] = { error: (e && e.message) || String(e), events: [] }; }
      this._tlLoading = null;
      if (this._tab === "overview") this._render();
    }

    _timelineHtml() {
      const today = this._data.now.slice(0, 10), day = this._tlDay(), key = this._tlKey(), tl = this._tlCache[key];
      const head = `<div class="sech"><h2>${day === today ? "Heute" : esc(new Date(day + "T12:00").toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "numeric" }))}</h2></div>`;
      if (!tl) { this._loadTimeline(key); return head + `<div class="tile"><div class="hint" style="padding:14px">Lade …</div></div>`; }
      if (tl.error) return head + `<div class="tile"><div class="err" style="padding:14px">${esc(tl.error)}</div></div>`;
      const isToday = tl.today, cats = Object.keys(CATNAME).filter((c) => tl.events.some((e) => e.cat === c));
      const f = this._tlFilter, list = tl.events.filter((e) => f === "all" || e.cat === f);
      const past = isToday ? list.filter((e) => e.minute <= tl.now && !e.running) : [];
      const shown = isToday && !this._tlPast ? list.filter((e) => e.minute > tl.now || e.running) : list;
      const info = [tl.holiday ? `Feiertag: ${tl.holiday}` : tl.workday ? "Arbeitstag" : "freier Tag", tl.christmas ? "Weihnachtszeit" : "",
        `Sonne ${hhmm(tl.sunrise)}–${hhmm(tl.sunset)}`].filter(Boolean).join(" · ");
      let nowShown = !isToday;
      const nowLine = () => { nowShown = true; return `<div class="tnow"><span>${minHm(tl.now)}</span><i></i><b>jetzt</b></div>`; };
      const sel = this._selMin(), atNow = this._atNow();
      let selShown = atNow;
      const selLine = () => { selShown = true; return `<div class="tnow tsel"><span>${minHm(sel)}</span><i></i><b>gewählt</b></div>`; };
      const rows = shown.map((e) => {
        const pre = (!nowShown && e.minute > tl.now ? nowLine() : "") + (!selShown && e.minute > sel ? selLine() : "");
        const done = isToday && e.minute <= tl.now && !e.running;
        const target = `data-a="tlset" data-v="${e.minute}" title="Regler auf ${minHm(e.minute)} stellen"`;
        return `${pre}<div class="tev ${done ? "past" : ""}" ${target}>
          <span class="tt">${minHm(e.minute)}</span><span class="tdot" style="background:${CATCOL[e.cat] || "#999"}"></span>
          <div class="tc ${e.running ? "run" : ""}"><span class="ti">${esc(e.icon)}</span><div><b>${esc(e.title)}</b><small>${esc(e.text)}</small></div>
            ${e.skip && !done ? `<span class="chip skipc">wird übersprungen</span>` : ""}${e.kind === "bad" ? `<span class="bad">⚠</span>` : done ? `<span class="ok">✓</span>` : ""}</div></div>`;
      }).join("") + (nowShown ? "" : nowLine()) + (selShown || !shown.length ? "" : selLine());
      return head + `<div class="tile tline">
        <div class="tfil">${[["all", `Alle ${tl.events.length}`], ...cats.map((c) => [c, `${CATNAME[c]} ${tl.events.filter((e) => e.cat === c).length}`])]
          .map(([k, n]) => `<button class="chip ${f === k ? "on" : ""}" data-a="tlfilter" data-v="${k}">${k !== "all" ? `<i class="cdot" style="background:${CATCOL[k]}"></i>` : ""}${esc(n)}</button>`).join("")}
          <span class="hint tinfo">${esc(info)}</span></div>
        ${past.length ? `<button class="linkbtn tpast" data-a="tlpast">${this._tlPast ? "▾ Erledigtes ausblenden" : `▸ ${past.length} heute schon erledigt`}</button>` : ""}
        ${rows || `<div class="hint" style="padding:12px 14px">${isToday ? "Heute ist nichts mehr geplant." : "An diesem Tag ist nichts geplant."}</div>`}
      </div>
      <div class="hint" style="margin:8px 4px">Antippen stellt den Regler auf diese Zeit.${isToday ? "" : " Vorschau mit den Plänen, Feiertagen und Sonnenzeiten dieses Tages und den Hausmodi von heute bzw. „angenommen“. Reaktionen erscheinen erst, wenn sie ausgelöst werden."}</div>`;
    }

    // ------------------------------------------------------------ Übersicht: Tag, Uhrzeit-Regler, „angenommen“ (0.9.11)
    // Zeigt, was zu einem Zeitpunkt gilt – Heizung und Abläufe zusammen. Es wird nichts geschaltet.
    _pref(key, def) {
      if (!this._prefs) { try { this._prefs = JSON.parse(window.localStorage.getItem("home_rhythm_prefs") || "{}") || {}; } catch (e) { this._prefs = {}; } }
      return this._prefs[key] === undefined ? def : this._prefs[key];
    }

    _setPref(key, val) {
      this._pref(key);
      this._prefs[key] = val;
      try { window.localStorage.setItem("home_rhythm_prefs", JSON.stringify(this._prefs)); } catch (e) { /* nur für diese Sitzung */ }
    }

    _assumeReq() {
      const a = this._assume || {};
      return Object.fromEntries(Object.entries(a).filter(([, v]) => v !== "" && v != null));
    }

    _selMin() {
      if (this._tlMin != null) return this._tlMin;
      return Math.floor(this._nowMin() / 15) * 15;
    }

    _atNow() { return this._tlMin == null && this._tlDay() === this._data.now.slice(0, 10) && !Object.keys(this._assumeReq()).length; }

    _ovTimeHtml() {
      const today = this._data.now.slice(0, 10), day = this._tlDay(), cv = (this._data.flows || { meta: { cond_values: {} } }).meta.cond_values || {};
      const shift = (n) => { const d = new Date(today + "T12:00"); d.setDate(d.getDate() + n); return isoDate(d); };
      const year = Number(today.slice(0, 4)), fixed = (m, d) => { const x = `${year}-${m}-${d}`; return x >= today ? x : `${year + 1}-${m}-${d}`; };
      const sat = (() => { const d = new Date(today + "T12:00"); d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7 || 7)); return isoDate(d); })();
      const sun = (() => { const d = new Date(today + "T12:00"); d.setDate(d.getDate() + ((7 - d.getDay()) % 7 || 7)); return isoDate(d); })();
      const quick = [[today, "Heute"], [shift(1), "Morgen"], [sat, "Samstag"], [sun, "Sonntag"], [fixed("12", "24"), "24.12."], [fixed("12", "25"), "25.12."], [fixed("12", "31"), "31.12."]];
      const sel = this._selMin(), atNow = this._atNow(), a = this._assume || {};
      const rel = this._relText();
      const seg = (key, vals) => `<span class="segs">${vals.map(([v, n]) => `<button class="seg ${String(a[key] ?? "") === String(v) ? "on" : ""}" data-a="assume" data-k="${key}" data-v="${esc(v)}">${esc(n)}</button>`).join("")}</span>`;
      const sims = Object.keys(this._assumeReq());
      const simTxt = [!atNow && (this._tlMin != null || day !== today) ? `${new Date(day + "T12:00").toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "numeric" })} ${minHm(sel)}` : "",
        a.season ? `Jahreszeit ${a.season}` : "", a.vacation ? a.vacation : "", a.presence ? (a.presence === "away" ? "niemand da" : "jemand da") : "",
        a.event ? `Ereignis ${a.event}` : "", a.christmas ? (a.christmas === "1" ? "Weihnachten" : "nicht Weihnachten") : "", a.holiday ? "Feiertag" : ""].filter(Boolean).join(" · ");
      return `<div class="ovtime ${atNow ? "" : "sim"}">
        <div class="ovrow"><b class="ovl">Tag</b><div class="dpick">${quick.map(([d, n]) => `<button class="chip ${d === day ? "on" : ""}" data-a="tldate" data-v="${d}">${n}</button>`).join("")}
          <input type="date" class="inp" data-a="tlpick" value="${esc(day)}" aria-label="Datum wählen"></div><span class="sp"></span>
          <button class="btn sm ${atNow ? "" : "pri"}" data-a="tlnow">jetzt</button></div>
        <div class="ovrow"><b class="ovl">Uhrzeit</b><b class="ovtm" id="ovtm">${minHm(sel)}</b>
          <button class="btn sm" data-a="tlstep" data-v="-60" aria-label="1 Stunde zurück">−1h</button>
          <span class="ovrange"><input type="range" min="0" max="95" step="1" value="${sel / 15}" data-a="tlrange" aria-label="Uhrzeit am gewählten Tag"><span class="ovax"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></span></span>
          <button class="btn sm" data-a="tlstep" data-v="60" aria-label="1 Stunde vor">+1h</button><span id="ovrel" class="chip ${rel.now ? "okc" : "simc"}">${esc(rel.text)}</span></div>
        <details class="ovass" ${sims.length || this._assOpen ? "open" : ""} data-ass="1"><summary><b>Angenommen</b> <span class="hint">${sims.length ? `${sims.length} geändert` : "Hausmodi wie jetzt – antippen, um „was wäre wenn“ zu probieren"}</span></summary>
          <div class="ovsegs">
            <span>Jahreszeit ${seg("season", [["", "wie jetzt"], ...(cv.season || []).map((x) => [x, x])])}</span>
            <span>Urlaub ${seg("vacation", [["", "wie jetzt"], ...(cv.vacation || []).map((x) => [x, x])])}</span>
            <span>Anwesenheit ${seg("presence", [["", "wie jetzt"], ["home", "jemand da"], ["away", "niemand da"]])}</span>
            <span>Ereignis ${seg("event", [["", "wie jetzt"], ["keins", "keins"], ["Party", "Party"], ["Gäste", "Gäste"]])}</span>
            <span>Weihnachten ${seg("christmas", [["", "wie Kalender"], ["1", "ja"], ["0", "nein"]])}</span>
            <span>Feiertag ${seg("holiday", [["", "wie Kalender"], ["1", "ja"]])}</span>
            ${sims.length ? `<button class="linkbtn" data-a="assreset">alles wie jetzt</button>` : ""}
          </div>
          <div class="hint">Alles frei kombinierbar. Die Tagesart ergibt sich aus dem Tag – z. B. Sonntag wählen, dazu Winter und Urlaub zu Hause.</div></details>
        ${atNow ? "" : `<div class="simnote">🔮 Vorschau – es wird nichts geschaltet. ${esc(simTxt)}</div>`}
      </div>`;
    }

    // Ganzer Tag auf einmal (96 Viertelstunden) – der Regler reagiert beim Ziehen sofort, ohne Rückfrage.
    _dayKey() { return `${this._tlDay()}|${JSON.stringify(this._assumeReq())}`; }

    async _loadDay(key) {
      if (this._dayLoading === key) return;
      this._dayLoading = key;
      const [day] = key.split("|");
      try { this._dayCache[key] = await this._ws({ type: "home_rhythm/day_states", date: day, assume: this._assumeReq() }); }
      catch (e) { this._dayCache[key] = { error: (e && e.message) || String(e) }; }
      this._dayLoading = null;
      if (this._tab === "overview") this._render();
    }

    _atFromDay(ds, minute) {
      const slot = ds.slots[Math.max(0, Math.min(95, Math.floor(minute / 15)))], names = ds.level_names || {};
      let ri = 0;
      const rooms = ds.rooms.map((r) => {
        if (r.paused) return r;
        const [level, temperature, hvac, next_at, next_level, next_temp, manual, reason] = slot.r[ri++];
        return { ...r, level, level_name: names[level] || level, temperature, hvac, next_at, next_level, next_level_name: next_level ? names[next_level] || next_level : null, next_temp, manual, reason };
      });
      const flows = ds.flows.map((f, i) => { const [state, nm, nt] = slot.f[i]; return { ...f, state, next: nm != null ? { minute: nm, text: nt } : null, strip: ds.slots.map((x) => x.f[i][0]) }; });
      return { date: ds.date, rooms, flows };
    }

    _ovStateHtml() {
      this._dayCache = this._dayCache || {};
      const key = this._dayKey(), ds = this._dayCache[key];
      if (!ds) { this._loadDay(key); return this._dayLast ? this._ovStateBody(this._atFromDay(this._dayLast, this._selMin()), true) : `<div class="tile"><div class="hint" style="padding:14px">Lade …</div></div>`; }
      if (ds.error) return `<div class="tile"><div class="err" style="padding:14px">${esc(ds.error)}</div></div>`;
      this._dayLast = ds;
      return this._ovStateBody(this._atFromDay(ds, this._selMin()), false);
    }

    /** Beim Ziehen: nur die betroffenen Teile neu zeichnen (der Regler selbst bleibt unberührt). */
    _ovLive() {
      const root = this.shadowRoot, sel = this._selMin();
      const tm = root.getElementById("ovtm"); if (tm) tm.textContent = minHm(sel);
      const left = root.getElementById("ovleft"); if (left) left.innerHTML = this._ovStateHtml();
      const right = root.getElementById("ovright"); if (right) right.innerHTML = this._timelineHtml();
      const rel = root.getElementById("ovrel"); if (rel) { const r = this._relText(); rel.textContent = r.text; rel.className = `chip ${r.now ? "okc" : "simc"}`; }
      const card = root.querySelector(".ovtime"); if (card) card.classList.toggle("sim", !this._atNow());
    }

    _relText() {
      const day = this._tlDay(), sel = this._selMin(), atNow = this._atNow();
      const diff = Math.round((new Date(`${day}T${minHm(sel)}:00`) - new Date(this._data.now)) / 60000), ad = Math.abs(diff);
      if (atNow || ad < 8) return { text: "jetzt", now: atNow };
      return { now: false, text: `${diff > 0 ? "in" : "vor"} ${ad >= 1440 ? `${Math.round(ad / 1440)} Tag${Math.round(ad / 1440) > 1 ? "en" : ""}` : ad >= 60 ? `${(Math.round(ad / 15) / 4).toString().replace(".", ",")} Std.` : `${ad} min`}` };
    }

    _ovStateBody(at, stale) {
      // 0.9.12: Zeilen wie in „Heizung & Klima“ bzw. „Abläufe“ – Symbol (antippen = Bedienen) · Name · Ist · Soll · Stufe + Grund
      if (at.error) return `<div class="tile"><div class="err" style="padding:14px">${esc(at.error)}</div></div>`;
      const d = this._data, meta = (d.flows || {}).meta || {}, atNow = this._atNow(), closed = new Set(this._pref("ovClosed", []));
      const live = Object.fromEntries((d.rooms || []).map((r) => [r.id, r]));
      const rooms = (at.rooms || []).map((r) => ({ ...r, area_id: r.area_id || (live[r.id] || {}).area_id }));
      const sel = this._selMin();
      const roomRow = (r) => {
        const lr = live[r.id] || {};
        if (r.paused) return `<div class="ovr2 off" data-a="goroom" data-v="${esc(r.id)}"><span class="ico">⏸</span><span class="nm">${esc(r.name)}</span><span class="num">${fmtTemp((lr.climate || {}).current_temperature)}<small>Ist</small></span><span class="num">–<small>Soll</small></span><span class="why"><span class="txt">pausiert – Home Rhythm steuert nicht</span></span><span class="chev">›</span></div>`;
        const off = r.hvac === "off";
        let ico, icoT;
        if (atNow) [ico, icoT] = this._icon(lr);
        else [ico, icoT] = r.manual ? ["✋", "Hand-Änderung"] : off ? ["⏻", "aus"] : r.level === "nacht" ? ["🌙", "Nacht"] : r.level === "absenkung" ? ["💤", "Absenkung"] : r.level === "urlaub" ? ["🧳", "Urlaub"] : ["🔥", "warm (Komfort o. ä.)"];
        const marks = `${lr.today || lr.active_rule ? ` <span class="star">★</span>` : ""}${(lr.hints || []).length ? ` <span class="warnmark">⚠</span>` : ""}${(lr.devices || []).some((x) => x.battery_low) ? ` <span class="batmark">🔋</span>` : ""}`;
        const next = r.next_at ? ` · bis ${r.next_at.slice(0, 10) !== at.date ? "morgen " : ""}${r.next_at.slice(11, 16)}, dann ${r.next_level_name || ""}${r.next_temp != null ? ` ${fmtNum(r.next_temp)} °C` : ""}` : "";
        const why = atNow && lr.manual ? `✋ von Hand bis ${fmtTime(lr.manual.until)}` : `${r.reason || ""}${next}`;
        const lvl = off ? "aus" : r.level;
        return `<div class="ovr2" data-a="goroom" data-v="${esc(r.id)}">
          <button class="ico icob" data-a="qroom" data-v="${esc(r.id)}" title="${esc(icoT)} – antippen: bedienen">${ico}</button>
          <span class="nm">${esc(r.name)}${marks}</span>
          <span class="num">${atNow ? fmtTemp((lr.climate || {}).current_temperature) : "–"}<small>Ist</small></span>
          <span class="num">${off ? "aus" : fmtTemp(r.temperature)}<small>Soll</small></span>
          <span class="why"><span class="lvl" style="background:${COLORS[lvl] || "#888"}">${esc(off ? "aus" : r.level_name || r.level)}</span><span class="txt">${esc(why)}</span></span>
          <span class="chev">›</span></div>`;
      };
      const floors = this._grouped(rooms).map((g, gi) => {
        const k = g.name || `g${gi}`, isClosed = closed.has(k);
        const warm = g.rooms.filter((r) => !r.paused && r.hvac !== "off" && (atNow ? (this._icon(live[r.id] || {})[0] === "🔥") : r.level !== "absenkung" && r.level !== "nacht")).length;
        const sum = `${g.rooms.length} ${g.rooms.length === 1 ? "Raum" : "Räume"} · ${warm} ${atNow ? "heizen" : "warm"}`;
        return `<div class="ovgrp"><button class="ovgh" data-a="ovfold" data-v="${esc(k)}" aria-expanded="${!isClosed}"><b>${isClosed ? "▸" : "▾"} ${esc((g.name || "Räume").toUpperCase())}</b><small>${esc(sum)}</small></button>
          ${isClosed ? "" : `<div class="tile list">${g.rooms.map(roomRow).join("")}</div>`}</div>`;
      }).join("");
      const showOff = this._pref("ovInactive", false);
      const items = Object.fromEntries(((d.flows && d.flows.items) || []).map((x) => [x.id, x]));
      const fl = (at.flows || []).filter((f) => showOff || f.enabled);
      const hidden = (at.flows || []).length - fl.length;
      const SC = { on: "#f5a623", off: "#d5d9de", open: "#f0c36d", closed: "#2a3a7a", pos: "#7fa7d9" };
      const bar = (strip) => {
        if (!strip || !strip.length) return "";
        const stops = []; let i = 0;
        while (i < strip.length) { let j = i; while (j < strip.length && strip[j] === strip[i]) j++; const c = strip[i] ? SC[strip[i]] || "#bbb" : "#eceef1"; stops.push(`${c} ${(i / 96 * 100).toFixed(2)}% ${(j / 96 * 100).toFixed(2)}%`); i = j; }
        return `<span class="mbar" style="background:linear-gradient(to right, ${stops.join(", ")})"><i style="left:${(sel / 1440 * 100).toFixed(2)}%"></i></span>`;
      };
      const flowRow = (f) => {
        const it = items[f.id] || {}, n = (it.resolved || []).length;
        const unit = f.kind === "cover" ? (n === 1 ? "Rollladen" : "Rollläden") : (n === 1 ? "Gerät" : "Geräte");
        const hand = atNow && it.hand ? ` · ✋ ${it.hand.src || "von Hand"}` : "";
        return `<div class="ovr2 fl ${f.enabled ? "" : "off"}" data-a="goflow" data-v="${esc(f.id)}">
          <button class="ico icob" data-a="qflow" data-v="${esc(f.id)}" title="antippen: Geräte von Hand schalten">${esc(f.icon || "⏱")}</button>
          <span class="nm">${esc(f.name)}<small>${n} ${unit}${it.conds && it.conds.items && it.conds.items.length ? ` · nur wenn ${esc(it.cond_text || "")}` : ""}${esc(hand)}</small></span>
          <span class="fs2"><b>${esc(f.enabled ? (f.state ? meta.state_names[f.state] || f.state : "ruht") : "aus")}</b><small>${esc(f.enabled ? f.why || "" : "ausgeschaltet")}</small></span>
          <span class="fx2"><small>${f.next ? `nächster: ${esc(minHm(f.next.minute))} → ${esc(f.next.text)}` : "nächster: –"}</small>${f.enabled ? bar(f.strip) : `<span class="mbar off"></span>`}</span>
          <span class="chev">›</span></div>`;
      };
      const flows = (at.flows || []).length ? `<div class="ovgrp"><div class="ovgh static"><b>ABLÄUFE</b><small>${fl.filter((f) => f.enabled).length} aktiv${!showOff && hidden ? ` · ${hidden} aus ausgeblendet` : ""}</small><span class="sp"></span>
          <label class="inl"><input type="checkbox" data-a="ovinactive" ${showOff ? "checked" : ""}> inaktive zeigen</label></div>
          <div class="tile list">${fl.map(flowRow).join("") || `<div class="hint" style="padding:10px 14px">Keine aktiven Zeitpläne.</div>`}</div></div>` : "";
      return `<div class="${stale ? "stale" : ""}">${floors}${flows}</div>`;
    }

    // ------------------------------------------------------------ Bedien-Fenster (0.9.12)
    // Symbol am Zeilenanfang → Fenster. Alles darin ist ein Entwurf: „Übernehmen“ schaltet, ✕ verwirft.
    _qOpenRoom(id) {
      const room = this._room(id); if (!room) return;
      const r = room.result || {}, man = room.manual;
      const t = man && man.temperature != null ? man.temperature : r.temperature != null ? r.temperature : 20;
      this._q = { type: "room", id, temp: t, level: man ? null : (r.level || null), off: man ? man.hvac_mode === "off" : r.hvac_mode === "off", until: "next", back: false, dirty: false, err: null };
      this._renderQ();
    }

    _qOpenFlow(id) {
      const it = ((this._data.flows && this._data.flows.items) || []).find((x) => x.id === id); if (!it) return;
      this._q = { type: "flow", id, all: null, devs: {}, skip: !!it.skip, dirty: false, err: null };
      this._renderQ();
    }

    _renderQ() {
      const host = this.shadowRoot.getElementById("qdlg");
      if (!host) return;
      const q = this._q;
      if (!q) { host.innerHTML = ""; return; }
      const body = q.type === "room" ? this._qRoomHtml(q) : this._qFlowHtml(q);
      host.innerHTML = `<div class="ov" data-a="qcancel"><div class="dlg qdlg" role="dialog" aria-modal="true">${body}</div></div>`;
    }

    _qRoomHtml(q) {
      const room = this._room(q.id); if (!room) return "";
      const r = room.result || {}, c = room.climate || {}, d = this._data;
      const [ico, icoT] = this._icon(room);
      const links = [...(room.climates || []).map((x) => [x.name || this._entName(x.entity_id), x.entity_id, x.state === "unavailable"]),
        ...((room.room_temp && room.room_temp.sensors) || []).map((x) => [x.name, x.entity_id, x.stale])].filter((x) => x[1]);
      const bad = [...(room.climates || []).filter((x) => x.state === "unavailable").map((x) => `${x.name}: nicht erreichbar`),
        ...(room.devices || []).filter((x) => !x.available).map((x) => `${x.name}: nicht erreichbar${x.last_changed ? ` seit ${fmtTime(x.last_changed)}` : ""}`)];
      const levels = (d.plan_levels || ["komfort", "absenkung", "nacht", "bad"]).filter((k) => (room.levels || {})[k] != null);
      const lvName = (k) => ((d.level_defs || {})[k] || {}).name || k;
      const shown = q.back ? (r.hvac_mode === "off" ? "aus" : fmtTemp(r.temperature)) : q.off ? "aus" : `${fmtNum(q.temp, 1)}°`;
      const untilOpts = [["next", "nächster Wechsel"], ["m60", "1 Std."], ["m120", "2 Std."], ["eod", "heute ganztägig"], ["morning", "morgen 06:00"]];
      const plan = `${r.level_name || ""} ${r.hvac_mode === "off" ? "aus" : fmtTemp(r.temperature)}${r.until ? ` · bis ${fmtTime(r.until)}` : ""}`;
      return `<div class="qhd"><span class="qico" title="${esc(icoT)}">${ico}</span><b>${esc(room.name)}</b><span class="sp"></span>
          ${links.map(([n, eid]) => `<button class="btn sm" data-a="more" data-v="${esc(eid)}" title="${esc(eid)} in Home Assistant öffnen (Verlauf, Einstellungen)">${esc(n)} ⤴</button>`).join("")}
          <button class="x" data-a="qcancel" aria-label="Schließen (verwirft Änderungen)">✕</button></div>
        <div class="qbody">
          ${bad.length ? `<div class="warnbox">${bad.map(esc).join("<br>")}</div>` : ""}
          <div class="qinfo"><span>Ist <b>${fmtTemp(c.current_temperature)}</b></span><span>Soll jetzt <b>${r.hvac_mode === "off" ? "aus" : fmtTemp(r.temperature)}</b></span><span>${c.hvac_action === "heating" ? "🔥 heizt" : c.state === "off" ? "⏻ aus" : "💤 Leerlauf"}</span>${room.manual ? `<span>✋ von Hand bis ${esc(fmtTime(room.manual.until))}</span>` : ""}</div>
          <div class="qtemp"><button class="qpm" data-a="qt" data-v="-0.5" aria-label="kälter">−</button><b class="${q.back ? "back" : ""}">${shown}</b><button class="qpm" data-a="qt" data-v="0.5" aria-label="wärmer">+</button></div>
          <div class="qsegs">${levels.map((k) => `<button class="seg ${!q.back && !q.off && q.level === k ? "on" : ""}" data-a="qlvl" data-v="${k}">${esc(lvName(k))} ${fmtNum(room.levels[k])}°</button>`).join("")}
            <button class="seg ${!q.back && q.off ? "on" : ""}" data-a="qlvl" data-v="off">aus</button></div>
          ${q.back ? `<div class="hint">„Übernehmen“ beendet die Hand-Änderung – der Raum folgt wieder dem Plan.</div>` : `<div class="qlab">GILT BIS</div>
          <div class="qsegs">${untilOpts.map(([k, n]) => `<button class="seg ${q.until === k ? "on" : ""}" data-a="quntil" data-v="${k}">${esc(n)}</button>`).join("")}</div>`}
          <div class="hint">Plan jetzt: ${esc(plan)}. ${room.temp_source === "sensors" || (room.room_temp && room.room_temp.value != null) ? "Du stellst die Raumtemperatur ein – Home Rhythm rechnet sie für das Thermostat um." : ""}</div>
          ${q.err ? `<div class="err">${esc(q.err)}</div>` : ""}
        </div>
        <div class="qft"><button class="btn" data-a="qback" ${room.manual || q.dirty ? "" : "disabled"}>Zurück zum Plan</button>${this._knopf && !this._config.navigation_path ? "" : `<button class="linkbtn" data-a="qgo">Raum öffnen ›</button>`}<span class="sp"></span>
          <button class="btn" data-a="qcancel">Abbrechen</button><button class="btn pri" data-a="qapply" ${q.dirty ? "" : "disabled"}>Übernehmen</button></div>`;
    }

    _qFlowHtml(q) {
      const it = ((this._data.flows && this._data.flows.items) || []).find((x) => x.id === q.id); if (!it) return "";
      const ents = this._fctlEnts(it), states = (this._hass && this._hass.states) || {};
      const isCover = (e) => e.startsWith("cover.");
      const covers = ents.filter(isCover), others = ents.filter((e) => !isCover(e));
      const cur = (e) => { const st = states[e]; return !st ? "?" : st.state; };
      const want = (e) => q.devs[e] || (q.all ? (isCover(e) ? ({ on: "open", off: "closed", open: "open", close: "closed" })[q.all] : ({ open: "on", close: "off", on: "on", off: "off" })[q.all]) : null);
      const name = (v) => ({ on: "an", off: "aus", open: "offen", closed: "zu", opening: "öffnet", closing: "schließt", unavailable: "nicht erreichbar", unknown: "?" })[v] || v;
      const big = (a, label) => `<button class="qbig ${q.all === a ? "on" : ""}" data-a="qall" data-v="${a}">${label}</button>`;
      const allBtns = [covers.length ? big("open", "▲ alle öffnen") + big("close", "▼ alle schließen") : "", others.length ? big("on", "💡 alle an") + big("off", "⚫ alle aus") : ""].join("");
      const rows = ents.map((e) => {
        const w = want(e), c = cur(e), opts = isCover(e) ? [["open", "▲"], ["closed", "▼"]] : [["on", "an"], ["off", "aus"]];
        return `<div class="qdev"><span>${isCover(e) ? "🪟" : (w || c) === "on" ? "💡" : "⚫"}</span><button class="linkbtn qdn" data-a="more" data-v="${esc(e)}" title="In Home Assistant öffnen">${esc(this._entName(e))} ⤴</button>
          <small>${esc(name(c))}${w && w !== c ? ` → <b>${esc(name(w))}</b>` : ""}</small>
          ${opts.map(([v, l]) => `<button class="seg ${w === v ? "on" : ""}" data-a="qdev" data-v="${esc(e)}" data-s="${v}">${l}</button>`).join("")}</div>`;
      }).join("");
      const nxt = it.next ? `${fmtTime(it.next.at)} → ${it.next.text}` : "kein weiterer Schaltpunkt";
      return `<div class="qhd"><span class="qico">${esc(it.icon || "⏱")}</span><b>${esc(it.name)}</b><span class="sp"></span><button class="x" data-a="qcancel" aria-label="Schließen (verwirft Änderungen)">✕</button></div>
        <div class="qbody">
          ${it.enabled ? "" : `<div class="hint qnote">Der Zeitplan ist ausgeschaltet – von Hand schalten geht trotzdem.</div>`}
          ${it.type === "plan" ? `<div class="qbigs">${allBtns}</div>` : ""}
          <div class="qdevs">${rows}</div>
          ${it.type === "plan" ? `<label class="inl"><input type="checkbox" data-a="qskip" ${q.skip ? "checked" : ""}> nächsten Schaltpunkt überspringen (${esc(nxt)})</label>
          <div class="hint">Von Hand geschaltet gilt bis zum nächsten Schaltpunkt (${esc(nxt)}). Der Zeitplan selbst bleibt unverändert.</div>` : `<div class="hint">Schaltet nur die Geräte – die Reaktion selbst wird nicht ausgelöst.</div>`}
          ${q.err ? `<div class="err">${esc(q.err)}</div>` : ""}
        </div>
        <div class="qft">${it.type === "plan" ? `<button class="btn" data-a="qplan">Jetzt wie geplant setzen</button>` : ""}<button class="linkbtn" data-a="qgo">Ablauf öffnen ›</button><span class="sp"></span>
          <button class="btn" data-a="qcancel">Abbrechen</button><button class="btn pri" data-a="qapply" ${q.dirty ? "" : "disabled"}>Übernehmen</button></div>`;
    }

    async _qApply() {
      const q = this._q; if (!q) return;
      try {
        if (q.type === "room") {
          if (q.back) await this._ws({ type: "home_rhythm/manual/clear", room_id: q.id });
          else {
            const room = this._room(q.id) || {};
            const msg = q.off ? { off: true } : q.level && (room.levels || {})[q.level] === q.temp ? { level: q.level } : { temperature: q.temp };
            const at = (dd, hm) => { const [h, mi] = hm.split(":").map(Number); const x = new Date(dd); x.setHours(h, mi, 0, 0); return x; };
            const now = new Date();
            if (q.until === "next") msg.until = "next";
            else if (q.until === "m60") msg.minutes = 60;
            else if (q.until === "m120") msg.minutes = 120;
            else if (q.until === "eod") msg.until = at(now, "23:59").toISOString();
            else if (q.until === "morning") msg.until = at(new Date(now.getTime() + 864e5), "06:00").toISOString();
            await this._ws({ type: "home_rhythm/room/manual", room_id: q.id, ...msg });
          }
        } else {
          const it = ((this._data.flows && this._data.flows.items) || []).find((x) => x.id === q.id);
          if (q.all && it && it.type === "plan") {
            const ents = this._fctlEnts(it), hasCover = ents.some((e) => e.startsWith("cover.")), hasOther = ents.some((e) => !e.startsWith("cover."));
            const acts = q.all === "open" || q.all === "close" ? [hasCover ? q.all : null, hasOther ? (q.all === "open" ? "on" : "off") : null] : [hasOther ? q.all : null, hasCover ? (q.all === "on" ? "open" : "close") : null];
            for (const a of [...new Set(acts.filter(Boolean))]) await this._ws({ type: "home_rhythm/flow/switch", flow_id: q.id, action: a });
          }
          for (const [e, v] of Object.entries(q.devs)) {
            const dom = e.split(".")[0];
            if (dom === "cover") await this._hass.callService("cover", v === "open" ? "open_cover" : "close_cover", { entity_id: e });
            else await this._hass.callService("homeassistant", v === "on" ? "turn_on" : "turn_off", { entity_id: e });
          }
          if (it && it.type === "plan" && !!it.skip !== q.skip) await this._ws({ type: "home_rhythm/flow/skip", flow_id: q.id });
        }
        this._q = null; this._renderQ(); this._dayCache = {}; await this._fetch();
      } catch (e) { q.err = (e && e.message) || String(e); this._renderQ(); }
    }

    /** Klicks im Bedien-Fenster. */
    async _qClick(a, v, t, e) {
      const q = this._q;
      switch (a) {
        case "qroom": this._qOpenRoom(v); return true;
        case "qflow": this._qOpenFlow(v); return true;
        case "goroom": if (e.target.closest("button, input, label, select") && e.target.closest("button, input, label, select") !== t) return true; this._tab = "heat"; this._open.add(v); this._loadPreview(v); this._render(); return true;
        case "ovpop": this._ovPop = this._ovPop === v ? null : v; this._ovGear = false; this._render(); return true;
        case "ovgear": this._ovGear = !this._ovGear; this._ovPop = null; this._render(); return true;
        case "ovtime": {
          const open = !this._pref("ovTimeOpen", false);
          this._setPref("ovTimeOpen", open);
          if (!open) { this._tlDate = null; this._tlMin = null; this._assume = {}; }  // zu = wieder „jetzt“
          this._render(); return true;
        }
      }
      if (!q) return false;
      switch (a) {
        case "qcancel": if (a === "qcancel" && t.classList.contains("ov") && e.target !== t) return true; this._q = null; this._renderQ(); return true;
        case "qt": q.temp = Math.max(5, Math.min(30, Math.round((q.temp + Number(v)) * 2) / 2)); q.level = null; q.off = false; q.back = false; q.dirty = true; this._renderQ(); return true;
        case "qlvl": { const room = this._room(q.id) || {}; if (v === "off") { q.off = true; } else { q.off = false; q.level = v; q.temp = (room.levels || {})[v] ?? q.temp; } q.back = false; q.dirty = true; this._renderQ(); return true; }
        case "quntil": q.until = v; q.dirty = true; this._renderQ(); return true;
        case "qback": q.back = true; q.dirty = true; this._renderQ(); return true;
        case "qall": q.all = q.all === v ? null : v; q.devs = {}; q.dirty = true; this._renderQ(); return true;
        case "qdev": q.devs[v] = t.dataset.s; q.dirty = true; this._renderQ(); return true;
        case "qplan": await this._ws({ type: "home_rhythm/flow/apply", flow_id: q.id }); this._q = null; this._renderQ(); await this._fetch(); return true;
        case "qgo": { const id = q.id, type = q.type; this._q = null; this._renderQ(); if (this._knopf) { if (this._config.navigation_path) this._knopfNav(); return true; } if (type === "room") { this._tab = "heat"; this._open.add(id); this._loadPreview(id); } else { this._tab = "flows"; this._flowOpen.add(id); } this._render(); return true; }
        case "qapply": await this._qApply(); return true;
      }
      return false;
    }

    // ------------------------------------------------------------ Abläufe
    _flowData() {
      const base = this._data.flows;
      if (!base || !this._sim || !this._simData) return base;
      const byId = Object.fromEntries(this._simData.items.map((i) => [i.id, i]));
      return { ...base, items: base.items.map((i) => byId[i.id] ? { ...i, week: byId[i.id].week, week_ticks: byId[i.id].week_ticks, week_marks: byId[i.id].week_marks, day_labels: byId[i.id].day_labels, wait: byId[i.id].wait, next: byId[i.id].next, state: byId[i.id].state } : i) };
    }

    _simHtml() {
      const F = this._data.flows, s = this._sim || {}, cv = F.meta.cond_values;
      const seg = (key, vals) => `<span class="segs">${vals.map(([v, n]) => `<button class="seg ${String(s[key] ?? "") === String(v) ? "on" : ""}" data-a="sim" data-k="${key}" data-v="${esc(v)}">${esc(n)}</button>`).join("")}</span>`;
      return `<div class="tile sim"><b>Simulieren</b>
        <span>Jahreszeit ${seg("season", [["", "wie jetzt"], ...cv.season.map((x) => [x, x])])}</span>
        <span>Urlaub ${seg("vacation", [["", "wie jetzt"], ...cv.vacation.map((x) => [x, x])])}</span>
        <span>Weihnachten ${seg("christmas", [["", "wie jetzt"], ["1", "ja"], ["0", "nein"]])}</span>
        <span>Anwesenheit ${seg("presence", [["", "wie jetzt"], ["home", "jemand da"], ["away", "niemand da"]])}</span></div>`;
    }

    async _loadSim() {
      const s = this._sim || {};
      if (!Object.values(s).some((v) => v !== "" && v != null)) { this._sim = null; this._simData = null; this._render(); return; }
      try { this._simData = await this._ws({ type: "home_rhythm/flows/sim", sim: s }); } catch (e) { this._simData = null; }
      this._render();
    }

    _flowsHtml() {
      const F = this._flowData();
      if (!F) return `<div class="empty">Abläufe werden geladen …</div>`;
      const items = F.items, adm = this._admin;
      const section = (title, list, empty, add) => `<div class="sech"><h2>${title}</h2>${add && adm ? `<button class="btn sm pri" data-a="fnew">+ Neu</button>` : ""}</div>
        <div class="tile list">${list.length ? list.map((i) => i.type === "plan" ? this._planRow(i) : this._reactRow(i)).join("") : `<div class="hint" style="padding:12px 14px">${empty}</div>`}</div>`;
      return `${F.native_error ? `<div class="warnbox">Automationen konnten nicht in automations.yaml geschrieben werden: ${esc(F.native_error)}</div>` : ""}
        ${items.some((i) => i.type === "plan") ? `<div class="hint" style="margin:0 4px 10px">Was wäre wenn (Jahreszeit, Urlaub, Weihnachten …)? → Übersicht, „Angenommen“ – zusammen mit der Heizung.</div>` : ""}
        ${section("Rollläden", items.filter((i) => i.type === "plan" && i.kind === "cover"), "Noch keine Zeitpläne für Rollläden.", true)}
        ${section("Licht &amp; Steckdosen", items.filter((i) => i.type === "plan" && i.kind === "switch"), "Noch keine Zeitpläne für Licht oder Steckdosen.")}
        ${section("Reaktionen", items.filter((i) => i.type === "react"), "Noch keine Reaktionen – z. B. Licht bei Bewegung, Timer-Knopf.")}
        <div class="legend" style="margin:10px 4px">${[["open", "offen"], ["pos", "Position"], ["closed", "zu"], ["on", "an"], ["off", "aus"]].map(([k, n]) => `<span><i style="background:${SCOL[k]}"></i>${n}</span>`).join("")}<span>│ Schaltpunkt</span></div>
        <div class="hint" style="margin:6px 4px">Ein Schaltpunkt ist ein Befehl zu dieser Zeit. Was du zwischendurch von Hand änderst, bleibt bis zum nächsten Schaltpunkt. „falls nötig“ schaltet nur Geräte, die noch nicht so stehen. Stehen zwei Zeitpläne zur selben Minute auf einem Gerät, gilt der obere.</div>`;
    }

    _todayIdx() { return (new Date(this._data.now).getDay() + 6) % 7; }
    _nowMin() { const d = new Date(this._data.now); return d.getHours() * 60 + d.getMinutes(); }

    // Wochen-/Tagesbalken: Farbflächen + Schaltpunkte (☀ = nach Sonne, grau = Absicherung) + orange „jetzt“.
    _strip(it, day, cls) {
      const week = it.week || [];
      if (!week[day]) return `<div class="${cls} empty-bar"></div>`;
      const marks = (it.week_marks || [])[day] || ((it.week_ticks || [])[day] || []).map((m) => ({ m }));
      const pct = (m) => (m / 14.4).toFixed(2);
      const ticks = marks.map((k) => `<span class="tick${k.sun ? " sun" : ""}${k.guard ? " guard" : ""}" style="left:${pct(k.m)}%" title="${esc(minHm(k.m))}${k.guard ? " Absicherung" : ""}"></span>`).join("");
      const now = day === (it.today ?? this._todayIdx()) ? `<span class="now" style="left:${pct(this._nowMin())}%" title="jetzt"></span>` : "";
      return `<div class="barw"><div class="${cls}">${week[day].map((s) => `<i style="background:${SCOL[s] || "#999"}"></i>`).join("")}</div>${ticks}${now}</div>`;
    }

    // Uhrzeiten unter einem Balken: „▲ 07:00 · ▼ 16:56 · ▼ 23:00“
    _marksLine(marks) {
      return (marks || []).map((k) => `${ACT_ICON[k.a] || "│"} ${minHm(k.m)}${k.guard ? " (Absicherung)" : ""}${k.prev ? " (vom Vorabend)" : ""}`).join(" · ") || "kein Schaltpunkt";
    }

    _flowWeekHtml(it, labels, dates) {
      const today = it.today ?? this._todayIdx();
      return `<div class="wk2">${DAYS.map((d, i) => { const lab = (labels || [])[i] || "", col = dtColorOf(lab), rests = /^ruht/.test(lab); return `<div class="d ${i === today ? "today" : ""}">${d}${dates ? ` ${esc(dates[i].slice(8, 10))}.${esc(dates[i].slice(5, 7))}.` : ""}<small>${col ? `<i class="dtdot" style="background:${col}"></i>` : ""}${esc(lab)}</small></div>
        <div>${this._strip(it, i, "bar")}<div class="ml">${rests ? "" : esc(this._marksLine((it.week_marks || [])[i]))}</div></div>`; }).join("")}
        <span></span><div class="axis"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div></div>`;
    }

    _planRow(it) {
      const meta = this._data.flows.meta, open = this._flowOpen.has(it.id), n = it.resolved.length;
      const matches = (x) => it.state === "on" ? x.state === "on" : it.state === "off" ? x.state === "off" : it.state === "closed" ? x.state === "closed" : x.state === "open";
      const off = it.state && !it.wait ? it.resolved.filter((x) => !matches(x)).length : 0;
      const tags = [
        it.conds.items.length ? `<span class="chip cond">nur wenn ${esc(it.cond_text)}</span>` : "",
        ...(it.overlaps || []).map((o) => `<span class="chip olap" title="Fallen zwei Schaltpunkte auf dieselbe Minute, gilt der Ablauf, der weiter oben steht">⧉ ${o.n} auch in ${esc(o.name)}</span>`),
        it.native ? `<span class="chip" title="Läuft als Automation in Home Assistant">🏠 in HA</span>` : "",
        it.skip ? `<span class="chip skipc">nächster Schaltpunkt wird übersprungen</span>` : "",
        it.hand ? `<span class="chip hand" title="${esc(it.hand.src || "")}">✋ ${esc(it.hand.src || "von Hand")} ${esc(fmtTime(it.hand.at))}: ${esc(meta.action_names[it.hand.action] || it.hand.action)}${it.hand.until ? ` – bis ${esc(fmtTime(it.hand.until))}${it.hand.auto ? "" : " (nächster Schaltpunkt)"}` : ""}</span>` : "",
        it.button ? `<span class="chip" title="Taster: schaltet alle Geräte gemeinsam">🔘 Taster</span>` : "",
        it.switch ? `<span class="chip" title="Auch als Schalter in Home Assistant">🔌 HA-Schalter</span>` : "",
      ].join("");
      const unit = it.kind === "cover" ? (n === 1 ? "Rollladen" : "Rollläden") : (n === 1 ? "Gerät" : "Geräte");
      return `<div class="frow ${!it.enabled ? "off" : it.wait ? "dim" : ""}" data-a="ftoggle" data-v="${esc(it.id)}">
        ${this._fctlIcon(it)}
        <div class="fn"><b>${esc(it.name)}</b><small>${n} ${unit}${it.random ? ` · Zeiten täglich ±${it.random} min` : ""}</small>${tags ? `<div class="tags">${tags}</div>` : ""}</div>
        <div class="fs">${it.wait ? `<b>–</b><small>${esc(it.wait)}</small>` : `<b>${esc(meta.state_names[it.state] || "–")}</b><small>${off ? `${off} von ${n} von Hand anders` : "alle wie geplant"}</small>`}</div>
        <div class="fx"><small>${it.next ? `nächster: ${esc(fmtTime(it.next.at))} → ${esc(it.next.text)}` : "nächster: –"}</small>${this._strip(it, this._todayIdx(), "fbar")}</div>
        <span class="chev">${open ? "⌄" : "›"}</span></div>${this._fctlBar(it)}${open ? this._planDetail(it) : ""}`;
    }

    // Schnellbedienung: Klick auf das Symbol am Zeilenanfang (wie bei der Heizung)
    _fctlEnts(it) {
      if (it.type === "plan") return it.resolved.map((x) => x.entity_id);
      return [...new Set((it.steps || []).flatMap((s) => s.entities || []))];
    }

    _fctlIcon(it) {
      const n = this._fctlEnts(it).length;
      if (!n) return `<span class="ico">${esc(it.icon)}</span>`;
      const title = n === 1 ? "Gerät öffnen und schalten" : `Alle ${n} Geräte schalten`;
      return `<button class="ico icob big" data-a="fctl" data-v="${esc(it.id)}" title="${esc(title)}" aria-label="${esc(title)}">${esc(it.icon)}</button>`;
    }

    _fctlBar(it) {
      if (this._fctlOpen !== it.id) return "";
      const ents = this._fctlEnts(it), states = (this._hass && this._hass.states) || {};
      const covers = ents.filter((e) => e.startsWith("cover.")), others = ents.filter((e) => !e.startsWith("cover."));
      const btn = (d, label) => `<button class="btn sm" data-a="fsw" data-v="${esc(it.id)}" data-d="${d}">${label}</button>`;
      const acts = [
        covers.length ? btn("open", covers.length > 1 ? "▲ alle öffnen" : "▲ öffnen") + btn("close", covers.length > 1 ? "▼ alle schließen" : "▼ schließen") : "",
        others.length ? btn("on", others.length > 1 ? "● alle an" : "● an") + btn("off", others.length > 1 ? "○ alle aus" : "○ aus") : "",
        it.run ? `<button class="btn sm warn" data-a="fstop" data-v="${esc(it.id)}">Reaktion abbrechen</button>` : "",
      ].join("");
      const chips = ents.map((e) => {
        const st = states[e], on = st && ["on", "open", "opening"].includes(st.state);
        return `<button class="dev" data-a="more" data-v="${esc(e)}" title="Einzeln öffnen und schalten"><span class="dot" style="background:${!st || st.state === "unavailable" ? "#999" : on ? "#f5a623" : "#7a8899"}"></span>${esc(this._entName(e))}</button>`;
      }).join("");
      return `<div class="fctl"><div class="actions">${acts}</div><div class="devs">${chips}</div>
        <div class="hint">${it.type === "plan" ? "Gilt wie eine Änderung von Hand – bis zum nächsten Schaltpunkt." : "Schaltet nur die Geräte – die Reaktion selbst wird nicht ausgelöst."}</div></div>`;
    }

    _logHtml(it) {
      if (!(it.log || []).length) return `<div class="flog hint">Noch nichts geschaltet.</div>`;
      return `<div class="flog">${it.log.map((l) => `<div><span class="${l.kind === "bad" ? "bad" : l.kind === "ok" ? "ok" : "hint"}">${l.kind === "bad" ? "⚠" : l.kind === "ok" ? "✓" : "·"}</span> <b>${esc(fmtTime(l.at))}</b> ${esc(l.text)}</div>`).join("")}</div>`;
    }

    _flowActions(it) {
      const adm = this._admin, items = this._data.flows.items, idx = items.findIndex((x) => x.id === it.id);
      return `<div class="actions">
        ${it.type === "plan" ? `<button class="btn sm pri" data-a="fapply" data-v="${esc(it.id)}">Jetzt auf Plan setzen</button>
          <button class="btn sm" data-a="fskip" data-v="${esc(it.id)}">${it.skip ? "Überspringen aufheben" : "Nächsten Schaltpunkt überspringen"}</button>`
          : `${adm ? `<button class="btn sm pri" data-a="ftest" data-v="${esc(it.id)}">Jetzt testen</button>` : ""}${it.run ? `<button class="btn sm warn" data-a="fstop" data-v="${esc(it.id)}">Abbrechen</button>` : ""}`}
        ${adm ? `<button class="btn sm" data-a="fedit" data-v="${esc(it.id)}">Bearbeiten</button>
          <button class="btn sm" data-a="fcopy" data-v="${esc(it.id)}">Kopieren</button>
          <button class="btn sm" data-a="fmove" data-v="${esc(it.id)}" data-d="-1" ${idx <= 0 ? "disabled" : ""} title="nach oben (hat Vorrang)">↑</button>
          <button class="btn sm" data-a="fmove" data-v="${esc(it.id)}" data-d="1" ${idx >= items.length - 1 ? "disabled" : ""} title="nach unten">↓</button>
          <label class="hint swl">aktiv <input type="checkbox" data-a="fenabled" data-v="${esc(it.id)}" ${it.enabled ? "checked" : ""}></label>` : ""}
      </div>`;
    }

    _planDetail(it) {
      const meta = this._data.flows.meta;
      const devs = it.resolved.map((x) => `<button class="dev" data-a="more" data-v="${esc(x.entity_id)}"><span class="dot" style="background:${SCOL[x.state === "closed" ? "closed" : x.state] || "#999"}"></span>${esc(x.name)} <small>${esc(x.state === "unavailable" ? "nicht erreichbar" : meta.state_names[x.state] || x.state)}${x.position != null && it.kind === "cover" ? ` ${esc(x.position)} %` : ""}${x.brightness != null && x.state === "on" ? ` ${esc(x.brightness)} %` : ""}</small></button>`).join("");
      const sels = (it.selectors || []).map((s) => this._selectorName(s)).join(", ");
      return `<div class="fdetail">
        <div class="devs">${devs || `<span class="hint">Keine Geräte gefunden.</span>`}</div>
        ${sels ? `<div class="hint">Automatisch dabei: alle Geräte aus ${esc(sels)}</div>` : ""}
        <div class="pts">${it.point_texts.map((t, i) => `<div>${esc(t)}${it.points[i].only_needed ? ` <small class="hint">· falls nötig</small>` : ""}${it.points[i].verify ? ` <small class="hint">· nachprüfen</small>` : ""}${it.points[i].note ? ` <small class="hint">· ${esc(it.points[i].note)}</small>` : ""}</div>`).join("")}</div>
        ${it.week && it.week.length ? this._flowWeekHtml(it, it.day_labels) : ""}
        ${(it.unsupported || []).length ? `<div class="hint">In HA nicht verfügbar: ${esc(it.unsupported.join(", "))}</div>` : ""}
        ${this._logHtml(it)}
        ${this._flowActions(it)}
      </div>`;
    }

    _reactRow(it) {
      const open = this._flowOpen.has(it.id);
      const sentence = `Wenn ${it.trigger_texts.join(" oder ")}${it.conds.items.length ? ` und ${it.cond_text}` : ""} → ${it.step_texts.join(", ")}`;
      const run = it.run, last = (it.log || [])[0];
      const state = !it.enabled ? "aus" : run ? `läuft – Schritt ${run.step + 1}${run.until ? ` bis ${fmtTime(run.until)}` : ""}` : "bereit";
      return `<div class="frow r ${!it.enabled ? "off" : ""}" data-a="ftoggle" data-v="${esc(it.id)}">
        ${this._fctlIcon(it)}
        <div class="fn"><b>${esc(it.name)}</b>${it.native ? ` <span class="chip">🏠 in HA</span>` : ""}<small class="sent">${esc(sentence)}</small></div>
        <div class="fs"><b class="${run ? "runc" : ""}">${esc(state)}</b><small>${last ? `zuletzt ${esc(fmtTime(last.at))}` : "noch nie ausgelöst"}</small></div>
        <span class="chev">${open ? "⌄" : "›"}</span></div>${this._fctlBar(it)}${open ? this._reactDetail(it) : ""}`;
    }

    _recipeHtml(trig, cond, steps, mode) {
      return `<div class="recipe">
        <div class="blk2 when"><div class="lbl">Wenn</div>${trig.map((t) => `<div>${esc(t)}</div>`).join("") || `<div class="hint">–</div>`}</div>
        ${cond ? `<div class="blk2 cnd"><div class="lbl">Und nur wenn</div><div>${esc(cond)}</div></div>` : ""}
        <div class="blk2 then"><div class="lbl">Dann</div>${steps.map((s, i) => `<div class="step"><span class="n">${i + 1}</span><span>${esc(s)}</span></div>`).join("") || `<div class="hint">–</div>`}
          ${mode ? `<div class="hint" style="margin-top:6px">Erneut ausgelöst, während es läuft: <b>${esc(mode)}</b></div>` : ""}</div></div>`;
    }

    _reactDetail(it) {
      return `<div class="fdetail">${this._recipeHtml(it.trigger_texts, it.conds.items.length ? it.cond_text : "", it.step_texts, this._data.flows.meta.react_modes[it.mode])}
        ${(it.unsupported || []).length ? `<div class="hint">In HA nicht verfügbar: ${esc(it.unsupported.join(", "))}</div>` : ""}
        ${this._logHtml(it)}${this._flowActions(it)}</div>`;
    }

    _selectorName(s) {
      const list = (this._data.flows.selectors || {})[s.by] || [];
      const hit = list.find((x) => x.id === s.id);
      return `${{ area: "Bereich", floor: "Etage", label: "Label" }[s.by]} „${hit ? hit.name : s.id}“`;
    }

    _entName(eid) {
      const c = (this._data.flows.candidates || []).find((x) => x.entity_id === eid);
      return c ? c.name : eid;
    }

    // ------------------------------------------------------------ Abläufe: Editor
    _flowTemplates() {
      const cv = this._data.flows.meta.cond_values;
      const away = cv.vacation.find((v) => /unterwegs/i.test(v)) || cv.vacation[cv.vacation.length - 1];
      const hot = cv.season.find((v) => /hei/i.test(v)) || cv.season[cv.season.length - 1];
      const P = (days, ref, x, action, extra = {}) => ({ days, ref, ...(ref === "time" ? { time: x } : { offset: x }), action, conds: { op: "and", items: [] }, ...extra });
      const G = (items = [], op = "and") => ({ op, items });
      const S = this._simpleNew.bind(this);
      return {
        cover: ["🪟", "Rollläden nach Zeit und Sonne", "morgens auf, abends zu, mit Absicherung", { type: "plan", kind: "cover", icon: "🪟", name: "Rollläden", devices: [], selectors: [], conds: G(), mode: "simple", points: [],
          simple: S({ ref: "time", time: "07:00" }, { ref: "sunset", offset: 60, unit: "min", latest: "23:00" }, "23:00", { sa: { like: "own", open: { ref: "time", time: "08:30" } }, so: { like: "sa" } }) }],
        hitze: ["☀️", "Hitzeschutz", "nur in der Heißphase auf Position", { type: "plan", kind: "cover", icon: "☀️", name: "Hitzeschutz", devices: [], selectors: [], mode: "advanced",
          conds: G([{ key: "season", op: "is", value: [hot] }]), points: [P("daily", "time", "11:00", "position", { position: 10 }), P("daily", "time", "18:00", "open", { only_needed: true })] }],
        light: ["💡", "Licht nach Sonne", "an vor Sonnenuntergang, aus um 23:00", { type: "plan", kind: "switch", icon: "💡", name: "Licht am Abend", devices: [], selectors: [], conds: G(), mode: "simple", points: [],
          simple: S({ ref: "sunset", offset: -15, unit: "min" }, { ref: "time", time: "23:00" }, "", { sa: { like: "mf" }, so: { like: "mf" }, hol: { like: "mf" }, vacwd: { like: "sa" } }) }],
        xmas: ["🎄", "Weihnachten", "nur im Advent bis 6. Januar", { type: "plan", kind: "switch", icon: "🎄", name: "Weihnachten", devices: [], selectors: [], mode: "simple", points: [],
          conds: G([{ key: "occasion", op: "is", value: "christmas" }]), simple: S({ ref: "sunset", offset: -30, unit: "min" }, { ref: "time", time: "23:00" }, "", { sa: { like: "mf" }, so: { like: "mf" }, hol: { like: "mf" }, vacwd: { like: "sa" } }) }],
        urlaub: ["🧳", "Urlaubssimulation", "abends an, jeden Tag etwas andere Zeiten", { type: "plan", kind: "switch", icon: "🧳", name: "Urlaubssimulation", random: 20, devices: [], selectors: [], mode: "simple", points: [],
          conds: G([{ key: "vacation", op: "is", value: [away] }]), simple: S({ ref: "sunset", offset: 20, unit: "min" }, { ref: "time", time: "22:45" }, "", { sa: { like: "mf" }, so: { like: "mf" }, hol: { like: "mf" }, vacwd: { like: "sa" } }) }],
        empty: ["⏰", "Leerer Zeitplan", "alles selbst festlegen", { type: "plan", kind: "switch", icon: "⏰", name: "", devices: [], selectors: [], conds: G(), mode: "simple", points: [],
          simple: S({ ref: "time", time: "07:00" }, { ref: "time", time: "22:00" }, "", { sa: { like: "mf" }, so: { like: "mf" }, hol: { like: "mf" }, vacwd: { like: "sa" } }) }],
        motion: ["🚶", "Bewegungslicht", "an bei Bewegung, aus nach Nachlauf, Warnblinken", { type: "react", icon: "🚶", name: "Bewegungslicht", mode: "restart", conds: G([{ key: "sun", op: "is", value: "down" }]),
          triggers: [{ kind: "state", entity: "", to: "on" }], steps: [{ do: "on", entities: [] }, { do: "wait_until", until: { key: "entity", entity: "", op: "is", value: "off" }, after: 180 }, { do: "blink", entities: [], times: 2 }, { do: "off", entities: [] }] }],
        timer: ["⏲️", "Timer-Knopf", "Knopf → an, nach 30 min aus", { type: "react", icon: "⏲️", name: "Timer", mode: "restart", conds: G(),
          triggers: [{ kind: "state", entity: "", to: null }], steps: [{ do: "on", entities: [] }, { do: "wait", seconds: 1800 }, { do: "off", entities: [] }] }],
        power: ["🔌", "Bei Leistung schalten", "z. B. Sauger mit dem Werkzeug", { type: "react", icon: "🔌", name: "Bei Leistung schalten", mode: "restart", conds: G(),
          triggers: [{ kind: "above", entity: "", value: 2 }], steps: [{ do: "on", entities: [] }, { do: "wait_until", until: { key: "entity", entity: "", op: "below", value: 2 }, after: 10 }, { do: "off", entities: [] }] }],
      };
    }

    _pickerHtml() {
      const T = this._flowTemplates();
      const grp = (title, keys) => `<div class="tplh">${title}</div><div class="tpl">${keys.map((k) => `<button data-a="ftpl" data-v="${k}"><span>${T[k][0]}</span><b>${esc(T[k][1])}</b><small>${esc(T[k][2])}</small></button>`).join("")}</div>`;
      return `<div class="ov" data-a="fovclick"><div class="dlg" role="dialog" aria-modal="true">
        <header><h2>Neuer Ablauf</h2><button class="x" data-a="fclose" aria-label="Schließen">✕</button></header>
        ${grp("Zeitplan – schaltet zu festen Zeiten", ["cover", "hitze", "light", "xmas", "urlaub", "empty"])}
        ${grp("Reaktion – wenn etwas passiert", ["motion", "timer", "power"])}
      </div></div>`;
    }

    _openFlowEditor(flow, isNew) {
      this._pick = null;
      const f = clone(flow);
      f.conds = f.conds && f.conds.items ? f.conds : { op: "and", items: [] };
      if (f.type === "plan") (f.points || []).forEach((p) => { p.conds = p.conds && p.conds.items ? p.conds : { op: "and", items: [] }; });
      ["state", "next", "week", "week_ticks", "week_marks", "day_labels", "wait", "cond_text", "log", "resolved", "unsupported", "point_texts", "overlaps", "skip", "trigger_texts", "step_texts", "run"].forEach((k) => delete f[k]);
      this._fpick = false;
      if (f.type === "plan") {
        f.mode = f.mode === "simple" ? "simple" : "advanced";
        if (f.mode === "simple") this._ensureSimple(f);
      }
      // Erweitert, aber aus „Einfach“ unverändert → Weg zurück offen (der Server hat das beim Speichern geprüft)
      this._fedit = { flow: f, isNew, preview: null, error: null, sim: "now", backPts: f.type === "plan" && f.mode === "advanced" && f.simple ? JSON.stringify(f.points) : null };
      this._renderFlowEditor();
      this._flowPreview();
    }

    _flowPreview() {
      clearTimeout(this._fpTimer);
      this._fpTimer = setTimeout(async () => {
        if (!this._fedit) return;
        const seq = (this._fpSeq = (this._fpSeq || 0) + 1);
        try {
          const res = await this._ws({ type: "home_rhythm/flow/preview", flow: { ...this._fedit.flow, sim: this._simReq(), week: this._fedit.week || null } });
          if (!this._fedit || seq !== this._fpSeq) return; // veraltete Antwort
          this._fedit.preview = res.error ? null : res;
          this._fedit.error = res.error || null;
        } catch (e) { if (this._fedit) this._fedit.error = (e && e.message) || String(e); }
        const pane = this.shadowRoot.getElementById("fprev");
        if (pane) pane.innerHTML = this._flowPreviewHtml();
        // „heute ≈ …“ hängt an den Sonnenzeiten der Vorschau
        this.shadowRoot.querySelectorAll("[data-calc]").forEach((el) => { el.textContent = this._sunCalc(this._calcSpec(el.dataset.calc)); });
      }, 250);
    }

    _calcSpec(key) {
      const f = this._fedit.flow;
      if (key.startsWith("pt")) return f.points[Number(key.slice(2))];
      return this._simObj(key);
    }

    // Woche simulieren (nur Vorschau): Feiertag am Mittwoch, Urlaub zu Hause / unterwegs, Heißphase
    _sims() {
      const meta = this._data.flows.meta, cv = meta.cond_values;
      const hot = cv.season.find((v) => /hei/i.test(v));
      return [["now", "Diese Woche"], ["hol", "Feiertag am Mi"], meta.home_value ? ["vachome", meta.home_value] : null,
        meta.away_value ? ["away", meta.away_value] : null, hot ? ["hot", hot] : null].filter(Boolean);
    }

    _simReq() {
      const meta = this._data.flows.meta, k = (this._fedit && this._fedit.sim) || "now";
      if (k === "hol") { const p = this._fedit && this._fedit.preview; return { holidays: [(p && p.dates ? p.dates : this._weekDates())[2]] }; }
      if (k === "vachome") return { vacation: meta.home_value };
      if (k === "away") return { vacation: meta.away_value };
      if (k === "hot") return { season: meta.cond_values.season.find((v) => /hei/i.test(v)) };
      return {};
    }

    _flowPreviewHtml() {
      const ed = this._fedit, f = ed.flow, p = ed.preview, meta = this._data.flows.meta;
      let out = "";
      if (f.type === "plan") {
        const sims = this._sims(), simName = (sims.find(([k]) => k === ed.sim) || sims[0])[1];
        const dates = p && p.dates ? p.dates : null, todayIso = String(this._data.now || "").slice(0, 10);
        const isNow = !ed.week || (dates && dates.includes(todayIso));
        const dm = (iso) => `${Number(iso.slice(8, 10))}.${Number(iso.slice(5, 7))}.`;
        const label = dates ? `${dm(dates[0])} – ${dm(dates[6])}${dates[6].slice(0, 4)}` : "";
        // „Springen zu“: Beginn/Ende des Zeitraums und die bestimmten Tage (nächstes Vorkommen)
        const next = (md) => { const y = Number(todayIso.slice(0, 4)), cand = `${y}-${md}`; return cand >= todayIso ? cand : `${y + 1}-${md}`; };
        const c0 = this._giltKey(f) === "range" ? (f.conds.items || [])[0] : null;
        const jumps = [...(c0 && mdOk(c0.from) ? [[`Beginn ${mdText(c0.from)}`, next(c0.from)]] : []),
          ...(((f.simple || {}).days || []).filter((d) => mdOk(d.date)).map((d) => [d.name || mdText(d.date), next(d.date)])),
          ...(c0 && mdOk(c0.to) ? [[`Ende ${mdText(c0.to)}`, next(c0.to)]] : [])].slice(0, 8);
        out += `<h3>So läuft die Woche</h3>
          <div class="weeknav"><button class="btn sm" data-a="fweek" data-v="prev" aria-label="Woche zurück">‹</button><b>${esc(label)}</b><button class="btn sm" data-a="fweek" data-v="next" aria-label="Woche vor">›</button>
            <button class="btn sm ${isNow ? "pri" : ""}" data-a="fweek" data-v="now">diese Woche</button>
            <label class="hint wdate">📅 <input class="inp" type="date" data-a="fweekdate" value="${esc(dates ? dates[0] : "")}" aria-label="Woche mit diesem Datum zeigen"></label></div>
          ${jumps.length ? `<div class="weekjump"><span class="hint">Springen zu:</span>${jumps.map(([n, d]) => `<button class="chip jump" data-a="fweek" data-v="${esc(d)}">${esc(n)}</button>`).join("")}</div>` : ""}
          <div class="simbar">${sims.map(([k, n]) => `<button class="seg ${ed.sim === k ? "on" : ""}" data-a="fsim" data-v="${k}">${esc(n)}</button>`).join("")}</div>
          <div class="hint">${ed.sim === "now" ? "Mit den Hausmodi von jetzt" : `Angenommen: ${esc(simName)}`}${p && !p.active ? " – <b>der Zeitplan ruht dann</b> („Zeitplan gilt“ trifft nicht zu)" : ""}.</div>`;
        if (p) {
          const it = { week: p.week, week_marks: p.week_marks, today: (p.dates || []).indexOf(String(this._data.now || "").slice(0, 10)) };
          out += this._flowWeekHtml(it, p.day_labels, p.dates)
            + `<div class="legend">${(f.kind === "cover" ? ["open", "pos", "closed"] : ["on", "off"]).map((k) => `<span><i style="background:${SCOL[k]}"></i>${meta.state_names[k]}</span>`).join("")}
              <span><i style="background:${SCOL.none}"></i>schaltet nie / ruht</span><span>☀ nach Sonne</span><span><i style="background:#e53935;width:3px"></i>jetzt</span></div>
            ${f.mode === "simple" ? `<details><summary class="hint">So wird es gespeichert (${p.point_texts.length} Schaltpunkte)</summary><div class="pts">${p.point_texts.map((t) => `<div>${esc(t)}</div>`).join("")}</div></details>`
              : `<div class="pts">${p.point_texts.map((t) => `<div>${esc(t)}</div>`).join("")}</div>`}
            <div class="hint">${p.devices} Gerät${p.devices === 1 ? "" : "e"} werden geschaltet.</div>`;
        }
      } else if (p) {
        out += `<h3>So liest es sich</h3>${this._recipeHtml(p.trigger_texts, f.conds.items.length ? p.cond_text : "", p.step_texts, meta.react_modes[f.mode])}`;
      }
      if (p && f.conds.items.length && f.type === "plan") out += `<div class="hint">Zeitplan gilt nur, wenn: <b>${esc(p.cond_text)}</b></div>`;
      if (p && (p.unsupported || []).length) out += `<div class="warnbox">Als HA-Automation nicht möglich: ${esc(p.unsupported.join(", "))}</div>`;
      if (ed.inputError) out += `<div class="err">${esc(ed.inputError)}</div>`;
      if (ed.error) out += `<div class="err">${esc(ed.error)}</div>`;
      return out;
    }

    // ------------------------------------------------------------ Gerätesuche
    // Statt exakter Entitäts-IDs: Teil von Name, Raum oder ID tippen und den Treffer anklicken.
    // Ziele: "dev" (Geräte eines Zeitplans), "step|i" (Geräte eines Schritts), "trig|i", "cond|<pfad>|i", "wu|i" (warten bis …).
    _pickDomains(tgt) {
      const meta = this._data.flows.meta, f = this._fedit.flow, [kind, a] = tgt.split("|");
      if (kind === "dev") return meta.kind_domains[f.kind];
      if (kind === "step") { const d = f.steps[Number(a)].do; return d === "toggle" ? [...meta.kind_domains.switch, ...meta.kind_domains.cover] : ["open", "close", "position"].includes(d) ? meta.kind_domains.cover : meta.kind_domains.switch; }
      if (kind === "trig") return meta.trigger_domains;
      return null;
    }

    _pickTaken(tgt) {
      const f = this._fedit.flow, [kind, a] = tgt.split("|");
      if (kind === "dev") return f.devices || [];
      if (kind === "step") return f.steps[Number(a)].entities || [];
      return [];
    }

    _pickMatches(tgt) {
      const C = this._data.flows.candidates || [], doms = this._pickDomains(tgt), taken = new Set(this._pickTaken(tgt));
      const areas = Object.fromEntries(((this._data.flows.selectors || {}).area || []).map((a) => [a.id, a.name]));
      const norm = (x) => String(x || "").toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss").replace(/[_.]/g, " ");
      const words = norm(this._pick.q).split(/\s+/).filter(Boolean);
      const all = C.filter((c) => (!doms || doms.includes(c.domain)) && !taken.has(c.entity_id))
        .map((c) => ({ ...c, area: areas[c.area_id] || "" }))
        .filter((c) => { const hay = norm(`${c.name} ${c.area} ${c.entity_id} ${DOMNAME[c.domain] || ""} ${c.kind || ""} ${c.device_class || ""}`); return words.every((w) => hay.includes(w)); });
      return { list: all.slice(0, 40), more: Math.max(0, all.length - 40) };
    }

    _pickListHtml(tgt) {
      const { list, more } = this._pickMatches(tgt);
      if (!list.length) return `<div class="pkempty">Nichts gefunden – anderes Wort versuchen (Name, Raum oder Art, z. B. „Rollladen Bad“).</div>`;
      this._pick.list = list.map((c) => c.entity_id);
      return list.map((c, k) => `<button class="pkitem ${k === this._pick.idx ? "on" : ""}" data-a="pkpick" data-t="${esc(tgt)}" data-v="${esc(c.entity_id)}" tabindex="-1">
          <span class="pki">${DOMICON[c.domain] || "•"}</span><span class="pkt"><b>${esc(c.name)}</b><small>${esc([c.area, (c.kind || "").split(" ")[0] || DOMNAME[c.domain], c.entity_id].filter(Boolean).join(" · "))}</small></span></button>`).join("")
        + (more ? `<div class="pkempty">… und ${more} weitere – weiter tippen, um einzugrenzen.</div>` : "");
    }

    _entPickHtml(tgt, placeholder) {
      const open = this._pick && this._pick.tgt === tgt;
      return `<div class="epick"><input class="inp" type="search" data-a="pkq" data-t="${esc(tgt)}" placeholder="🔍 ${esc(placeholder)}" value="${open ? esc(this._pick.q) : ""}" autocomplete="off" aria-label="${esc(placeholder)}">
        ${open ? `<div class="pklist" data-t="${esc(tgt)}">${this._pickListHtml(tgt)}</div>` : ""}</div>`;
    }

    _entSingleHtml(tgt, eid, placeholder) {
      if (eid && !(this._pick && this._pick.tgt === tgt)) {
        const c = (this._data.flows.candidates || []).find((x) => x.entity_id === eid);
        return `<button class="tag pkcur" data-a="pkopen" data-t="${esc(tgt)}" title="${esc(eid)}">${c ? DOMICON[c.domain] || "" : ""} ${esc(this._entName(eid))} <small>ändern</small></button>`;
      }
      return this._entPickHtml(tgt, placeholder);
    }

    _pickApply(tgt, eid) {
      const f = this._fedit.flow, parts = tgt.split("|"), kind = parts[0];
      if (kind === "dev") { f.devices = f.devices || []; if (!f.devices.includes(eid)) f.devices.push(eid); }
      else if (kind === "step") { const st = f.steps[Number(parts[1])]; st.entities = st.entities || []; if (!st.entities.includes(eid)) st.entities.push(eid); }
      else if (kind === "trig") f.triggers[Number(parts[1])].entity = eid;
      else if (kind === "cond") this._resolveGroup(parts[1]).items[Number(parts[2])].entity = eid;
      else if (kind === "wu") { const st = f.steps[Number(parts[1])]; st.until = { ...(st.until || { key: "entity", op: "is", value: "off" }), entity: eid }; }
      const multi = kind === "dev" || kind === "step";
      this._pick = multi ? { tgt, q: "", idx: 0 } : null;
      this._renderFlowEditor();
      this._flowPreview();
      if (multi) this._focusPick(tgt);
    }

    _focusPick(tgt) {
      const inp = [...this.shadowRoot.querySelectorAll('input[data-a="pkq"]')].find((x) => x.dataset.t === tgt);
      if (inp) { inp.focus(); const n = inp.value.length; inp.setSelectionRange(n, n); }
    }

    _openPick(tgt, q = "") {
      this._pick = { tgt, q, idx: 0 };
      const inp = [...this.shadowRoot.querySelectorAll('input[data-a="pkq"]')].find((x) => x.dataset.t === tgt);
      const box = inp && inp.parentElement;
      if (!box) return;
      let list = box.querySelector(".pklist");
      if (!list) { list = document.createElement("div"); list.className = "pklist"; list.dataset.t = tgt; box.appendChild(list); }
      list.innerHTML = this._pickListHtml(tgt);
    }

    _closePick() {
      if (!this._pick) return;
      const single = !["dev", "step"].includes(this._pick.tgt.split("|")[0]);
      this._pick = null;
      if (single) this._renderFlowEditor();
      else this.shadowRoot.querySelectorAll(".pklist").forEach((x) => x.remove());
    }

    _pickKey(e) {
      const t = e.target;
      if (!t.dataset || t.dataset.a !== "pkq" || !this._pick) return;
      const n = (this._pick.list || []).length;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        this._pick.idx = n ? (this._pick.idx + (e.key === "ArrowDown" ? 1 : -1) + n) % n : 0;
        this._openPick(this._pick.tgt, this._pick.q);
        const on = this.shadowRoot.querySelector(".pkitem.on"); if (on) on.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (n) this._pickApply(this._pick.tgt, this._pick.list[this._pick.idx] || this._pick.list[0]);
      } else if (e.key === "Escape") { e.stopPropagation(); this._closePick(); }
    }

    _datalists() {
      const dl = (id, doms) => `<datalist id="${id}">${C.filter((c) => !doms || doms.includes(c.domain)).map((c) => `<option value="${esc(c.entity_id)}">${esc(c.name)}</option>`).join("")}</datalist>`;
      return `<datalist id="hr-dl-states">${[["on", "an"], ["off", "aus"], ["open", "offen"], ["closed", "zu"], ["home", "zu Hause"], ["not_home", "weg"], ["playing", "spielt"], ["unlocked", "aufgeschlossen"]].map(([v, n]) => `<option value="${v}">${n}</option>`).join("")}</datalist>`;
    }

    _condRowHtml(c, path, i) {
      const meta = this._data.flows.meta, cv = meta.cond_values;
      const keyOpts = Object.entries(meta.cond_keys).map(([k, n]) => `<option value="${k}" ${k === c.key ? "selected" : ""}>${esc(n)}</option>`).join("");
      const ops = c.key === "entity" ? ["is", "not", "above", "below"] : ["is", "not"];
      const opNames = c.key === "date" ? (meta.date_ops || { is: "zwischen", not: "nicht zwischen" }) : meta.cond_ops;
      const opOpts = ops.map((o) => `<option value="${o}" ${o === c.op ? "selected" : ""}>${esc(opNames[o])}</option>`).join("");
      const one = Array.isArray(c.value) ? c.value[0] : c.value;
      let val;
      if (c.key === "date") {
        const at = (f) => `data-a="fcond" data-p="${path}" data-i="${i}" data-f="${f}"`;
        val = `<span class="cvv">${mdSel(at("from"), c.from, "von")}<span class="unit">und</span>${mdSel(at("to"), c.to, "bis")}</span>`;
      } else if (c.key === "entity") {
        val = `<span class="cvv">${this._entSingleHtml(`cond|${path}|${i}`, c.entity, "Gerät suchen")}
          <input class="inp" list="hr-dl-states" placeholder="${c.op === "above" || c.op === "below" ? "Zahl" : "Zustand, z. B. on"}" value="${esc(c.value ?? "")}" data-a="fcond" data-p="${path}" data-i="${i}" data-f="value"></span>`;
      } else if (c.key === "flow") {
        const plans = this._data.flows.items.filter((x) => x.type === "plan" && x.id !== this._fedit.flow.id);
        val = `<span class="cvv"><select class="inp" data-a="fcond" data-p="${path}" data-i="${i}" data-f="flow">${plans.map((x) => `<option value="${esc(x.id)}" ${x.id === c.flow ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
          <select class="inp" data-a="fcond" data-p="${path}" data-i="${i}" data-f="value">${["open", "closed", "pos", "on", "off"].map((s) => `<option value="${s}" ${s === c.value ? "selected" : ""}>${meta.state_names[s]}</option>`).join("")}</select></span>`;
      } else {
        const vals = meta.cond_fixed[c.key] ? Object.entries(meta.cond_fixed[c.key]) : (cv[c.key] || []).map((x) => [x, x]);
        val = `<select class="inp" data-a="fcond" data-p="${path}" data-i="${i}" data-f="value">${vals.map(([v, n]) => `<option value="${esc(v)}" ${v === one ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`;
      }
      return `<div class="condl"><select class="inp" data-a="fcond" data-p="${path}" data-i="${i}" data-f="key">${keyOpts}</select>
        <select class="inp" data-a="fcond" data-p="${path}" data-i="${i}" data-f="op">${opOpts}</select>${val}
        <button class="x" data-a="fconddel" data-p="${path}" data-i="${i}" aria-label="Bedingung entfernen">×</button></div>`;
    }

    _groupHtml(g, path, depth) {
      const rows = g.items.map((c, i) => c.items ? `<div class="grp"><div class="grph"><select class="inp" data-a="fgrpop" data-p="${path}.${i}"><option value="and" ${c.op !== "or" ? "selected" : ""}>Alle davon</option><option value="or" ${c.op === "or" ? "selected" : ""}>Eine davon</option></select>
          <button class="x" data-a="fconddel" data-p="${path}" data-i="${i}" aria-label="Gruppe entfernen">×</button></div>${this._groupHtml(c, `${path}.${i}`, depth + 1)}</div>` : this._condRowHtml(c, path, i)).join("");
      return `${depth === 0 && g.items.length ? `<div class="grph root">Gilt, wenn <select class="inp" data-a="fgrpop" data-p="${path}"><option value="and" ${g.op !== "or" ? "selected" : ""}>alle</option><option value="or" ${g.op === "or" ? "selected" : ""}>eine</option></select> dieser Bedingungen zutreffen:</div>` : ""}
        ${rows || (depth === 0 ? `<div class="hint">Keine – gilt immer.</div>` : "")}
        <div class="btnrow" style="margin-top:4px"><button class="btn sm" data-a="fcondadd" data-p="${path}">+ Bedingung</button>${depth < 2 ? `<button class="btn sm" data-a="fgrpadd" data-p="${path}">+ Gruppe (und / oder)</button>` : ""}</div>`;
    }

    _resolveGroup(path) {
      const f = this._fedit.flow, parts = path.split(".");
      let g = parts[0] === "c" ? f.conds : f.points[Number(parts[0].slice(1))].conds;
      for (const i of parts.slice(1)) g = g.items[Number(i)];
      return g;
    }

    _entityTags(list, field, idx) {
      return `<div class="tagrow">${list.map((e, j) => `<span class="tag">${esc(this._entName(e))}<button data-a="fentdel" data-f="${field}" data-i="${idx}" data-j="${j}" aria-label="entfernen">×</button></span>`).join("")}</div>
        ${this._entPickHtml(`step|${idx}`, "+ Gerät suchen")}`;
    }

    _pointHtml(p, i, kind) {
      const meta = this._data.flows.meta;
      const days = Object.entries(meta.days).map(([k, n]) => `<option value="${k}" ${p.days === k ? "selected" : ""}>${esc(n)}</option>`).join("");
      const refs = Object.entries(meta.refs).map(([k, n]) => `<option value="${k}" ${p.ref === k ? "selected" : ""}>${esc(n)}</option>`).join("");
      const acts = meta.actions[kind].map((k) => `<option value="${k}" ${p.action === k ? "selected" : ""}>${esc(meta.action_names[k])}</option>`).join("");
      return `<div class="spc">
        <div class="spl">
          <select class="inp" data-a="fpt" data-i="${i}" data-f="days">${days}</select>
          <select class="inp" data-a="fpt" data-i="${i}" data-f="ref">${refs}</select>
          ${p.ref === "time" ? `<input class="inp" data-a="fpt" data-i="${i}" data-f="time" value="${esc(p.time || "")}" maxlength="5" aria-label="Uhrzeit">`
            : `<span class="offw"><input class="inp" type="number" step="5" data-a="fpt" data-i="${i}" data-f="offset" value="${esc(p.offset || 0)}" title="+ danach, − davor" aria-label="Versatz in Minuten" style="width:64px"><span class="unit">min</span><span class="unit" data-calc="pt${i}">${esc(this._sunCalc(p))}</span></span>`}
          <span class="spa"><select class="inp" data-a="fpt" data-i="${i}" data-f="action">${acts}</select>
            ${p.action === "position" ? `<input class="inp" type="number" min="0" max="100" data-a="fpt" data-i="${i}" data-f="position" value="${esc(p.position ?? 30)}" title="Position %">` : ""}
            ${p.action === "on" && this._editHasLights() ? `<input class="inp hell" type="number" min="1" max="100" step="5" data-a="fpt" data-i="${i}" data-f="brightness" value="${esc(p.brightness ?? "")}" placeholder="Hell. %" title="Helligkeit % – nur für Lampen, Steckdosen ignorieren den Wert">` : ""}</span>
          <button class="x" data-a="fptdel" data-i="${i}" aria-label="Schaltpunkt entfernen">×</button>
        </div>
        ${p.days === "custom" ? `<div class="daychips">${meta.weekdays.map((d, j) => `<button class="seg ${(p.weekdays || []).includes(j) ? "on" : ""}" data-a="fwday" data-i="${i}" data-v="${j}">${d}</button>`).join("")}</div>` : ""}
        ${p.days === "dates" ? `<div class="daychips"><input class="inp" data-a="fpt" data-i="${i}" data-f="dates" value="${esc((p.dates || []).map(mdText).join(", "))}" placeholder="z. B. 24.12., 31.12." aria-label="Bestimmte Tage" style="min-width:200px">
          <label class="inl" style="margin-left:6px"><input type="checkbox" data-a="fptc" data-i="${i}" data-f="prev" ${p.prev ? "checked" : ""}> zählt zum Vorabend (nach Mitternacht)</label></div>` : ""}
        ${(p.except || []).length ? `<div class="hint">außer ${esc(p.except.map(mdText).join(", "))} (dort gelten eigene Zeiten)</div>` : ""}
        ${p.days === "type" ? `<div class="daychips">${Object.entries(meta.day_types || {}).map(([k, n]) => `<button class="seg ${(p.types || []).includes(k) ? "on" : ""}" data-a="ftype" data-i="${i}" data-v="${k}">${esc(n)}</button>`).join("")}
          <label class="inl" style="margin-left:6px"><input type="checkbox" data-a="fptc" data-i="${i}" data-f="prev" ${p.prev ? "checked" : ""}> zählt zum Vorabend (nach Mitternacht)</label></div>` : ""}
        <div class="spo">
          ${p.ref !== "time" ? `<span>frühestens <input class="inp" data-a="fpt" data-i="${i}" data-f="earliest" value="${esc(p.earliest || "")}" placeholder="–" maxlength="5"> spätestens <input class="inp" data-a="fpt" data-i="${i}" data-f="latest" value="${esc(p.latest || "")}" placeholder="–" maxlength="5"></span>` : ""}
          <label><input type="checkbox" data-a="fptc" data-i="${i}" data-f="only_needed" ${p.only_needed ? "checked" : ""}> nur falls nötig <small class="hint">(nur Geräte, die noch nicht so stehen)</small></label>
          <label><input type="checkbox" data-a="fptc" data-i="${i}" data-f="verify" ${p.verify ? "checked" : ""}> nachprüfen &amp; wiederholen <small class="hint">(nach 5 min prüfen, bis zu 2× erneut)</small></label>
          <input class="inp note" data-a="fpt" data-i="${i}" data-f="note" value="${esc(p.note || "")}" placeholder="Notiz" maxlength="40">
        </div>
        <details ${p.conds.items.length ? "open" : ""}><summary class="hint">nur wenn … ${p.conds.items.length ? `(${p.conds.items.length})` : ""}</summary>${this._groupHtml(p.conds, `p${i}`, 1)}</details>
      </div>`;
    }

    // ------------------------------------------------------------ Zeitplan: einfacher Modus (Tagesarten wie bei der Heizung)
    // Eingabe pro Tagesart; der Server rechnet daraus Schaltpunkte. Zeilen ohne eigene Zeiten folgen „wie …“.
    _simpleNew(open, close, guard, rows = {}) {
      const like = { mf: "own", sa: "own", so: "own", hol: "so", vacwd: "so", vacwe: "keep" };
      const out = { rows: {}, close_per_row: false, close: clone(close), guard: guard || "", only_needed: false, verify: true };
      for (const k of ["mf", "sa", "so", "hol", "vacwd", "vacwe"]) {
        const r = rows[k] || {};
        out.rows[k] = { like: r.like || like[k], open: clone(r.open || open), close: clone(r.close || close) };
      }
      return out;
    }

    _ensureSimple(f) {
      if (!f.simple) f.simple = this._simpleNew({ ref: "time", time: "07:00" }, { ref: "sunset", offset: 30, unit: "min", latest: "23:00" }, f.kind === "cover" ? "23:00" : "");
      const s = f.simple, def = s.rows.mf || {};
      for (const k of ["mf", "sa", "so", "hol", "vacwd", "vacwe"]) {
        s.rows[k] = s.rows[k] || { like: k === "vacwe" ? "keep" : k === "mf" ? "own" : "mf" };
        s.rows[k].open = s.rows[k].open || clone(def.open || { ref: "time", time: "07:00" });
        s.rows[k].close = s.rows[k].close || clone(s.close || { ref: "sunset", offset: 0 });
      }
      s.close = s.close || { ref: "sunset", offset: 0 };
      s.days = Array.isArray(s.days) ? s.days : [];
      return s;
    }

    _simObj(path) {
      const s = this._fedit.flow.simple, parts = path.split(".");
      let o = s;
      for (const k of parts) o = o[k];
      return o;
    }

    _weekDates() {
      const d = new Date(this._data.now), monday = new Date(d.getFullYear(), d.getMonth(), d.getDate() - ((d.getDay() + 6) % 7));
      return [...Array(7)].map((_, i) => { const x = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i); return `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}`; });
    }

    // „heute ≈ 08:22“ für Zeiten nach der Sonne (Sonnenzeiten kommen mit der Vorschau)
    _sunCalc(spec) {
      const p = this._fedit && this._fedit.preview;
      if (!p || !p.sun || !spec || !["sunrise", "sunset"].includes(spec.ref)) return "";
      const sun = p.sun[this._todayIdx()];
      let m = (spec.ref === "sunrise" ? sun.rise : sun.set) + (Number(spec.offset) || 0);
      const e = spec.earliest ? normTime(spec.earliest) : null, l = spec.latest ? normTime(spec.latest) : null;
      const toM = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
      if (e) m = Math.max(m, toM(e));
      if (l) m = Math.min(m, toM(l));
      return `heute ≈ ${minHm(Math.max(0, Math.min(1439, Math.round(m))))}`;
    }

    _specHtml(path, spec, which, kind, noLabel = false, withNormal = false) {
      const cover = kind === "cover", open = which === "open";
      const label = open ? (cover ? "Öffnen" : "Einschalten") : (cover ? "Schließen" : "Ausschalten");
      const refs = (open ? [["time", "Uhrzeit"], ["sunrise", "Sonnenaufgang"], ["sunset", "Sonnenuntergang"], ["none", cover ? "nicht öffnen" : "nicht einschalten"]]
        : [["time", "Uhrzeit"], ["sunset", "Sonnenuntergang"], ["sunrise", "Sonnenaufgang"], ["none", cover ? "nicht schließen" : "nicht ausschalten"]]);
      if (withNormal) refs.unshift(["normal", "wie sonst"]);
      const sel = (f, opts, val, aria) => `<select class="inp" data-a="fsp" data-p="${path}" data-f="${f}" aria-label="${esc(aria)}">${opts.map(([v, n]) => `<option value="${v}" ${v === val ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`;
      const ref = spec.ref || "time", unit = spec.unit === "h" ? "h" : "min";
      let body = sel("ref", refs, ref, `${label} – wann`);
      if (ref === "time") body += `<input class="inp tm" data-a="fsp" data-p="${path}" data-f="time" value="${esc(spec.time || "")}" maxlength="5" aria-label="${label} Uhrzeit" placeholder="hh:mm">`;
      else if (ref !== "none" && ref !== "normal") {
        const shown = unit === "h" ? String(Math.round(((spec.offset || 0) / 60) * 100) / 100).replace(".", ",") : (spec.offset || 0);
        body += `<input class="inp off" type="text" inputmode="decimal" data-a="fsp" data-p="${path}" data-f="offset" value="${esc(shown)}" aria-label="Versatz" title="+ danach, − davor">
          ${sel("unit", [["min", "min"], ["h", "Std."]], unit, "Einheit")}
          <span class="unit">${open ? "frühestens" : "spätestens"}</span><input class="inp tm" data-a="fsp" data-p="${path}" data-f="${open ? "earliest" : "latest"}" value="${esc((open ? spec.earliest : spec.latest) || "")}" maxlength="5" placeholder="–" aria-label="${open ? "frühestens" : "spätestens"}">
          <span class="calc" data-calc="${path}">${esc(this._sunCalc(spec))}</span>`;
      }
      if (open && ref !== "none" && ref !== "normal" && cover) {
        const pos = spec.position !== undefined && spec.position !== null && spec.position !== "";
        body += sel("target", [["open", "ganz auf"], ["pos", "auf Position"]], pos ? "pos" : "open", "Ziel");
        if (pos) body += `<input class="inp" type="number" min="0" max="100" data-a="fsp" data-p="${path}" data-f="position" value="${esc(spec.position)}" aria-label="Position in Prozent"><span class="unit">%</span>`;
      }
      if (open && ref !== "none" && ref !== "normal" && !cover && this._editHasLights()) body += `<input class="inp" type="number" min="1" max="100" step="5" data-a="fsp" data-p="${path}" data-f="brightness" value="${esc(spec.brightness ?? "")}" placeholder="Hell. %" title="Helligkeit % – nur für Lampen">`;
      return `<div class="srl">${noLabel ? "" : `<span class="lb">${open ? "▲" : "▼"}&nbsp;${label}</span>`}${body}</div>`;
    }

    _simpleHtml(f) {
      const meta = this._data.flows.meta, s = this._ensureSimple(f), cover = f.kind === "cover";
      const likeOpts = meta.simple_like || {}, likeNames = meta.simple_like_names || {}, rowNames = meta.simple_rows || {};
      const subs = { mf: "Werktage", sa: "", so: "", hol: "laut Workday-Sensor", vacwd: "Hausmodus", vacwe: "Hausmodus" };
      const likeTxt = (k) => { const l = s.rows[k].like; return l === "own" ? "eigene Zeiten" : l === "keep" ? "unverändert" : likeNames[l] || l; };
      const closeWord = cover ? "Schließen" : "Ausschalten";
      const rows = ["mf", "sa", "so", "hol", "vacwd", "vacwe"].map((k) => {
        const r = s.rows[k], opts = likeOpts[k] || ["own"];
        const sel = opts.length > 1 ? `<select class="inp" data-a="fsl" data-v="${k}" aria-label="${esc(rowNames[k])}">${opts.map((o) => `<option value="${o}" ${o === r.like ? "selected" : ""}>${esc(likeNames[o] || o)}</option>`).join("")}</select>` : "";
        const sent = k === "vacwe" ? `<div class="sent">Im Urlaub zu Hause: Mo–Fr ${esc(likeTxt("vacwd"))}, Sa/So ${esc(likeTxt("vacwe"))}.</div>` : "";
        const own = r.like === "own" ? this._specHtml(`rows.${k}.open`, r.open, "open", f.kind) + (s.close_per_row ? this._specHtml(`rows.${k}.close`, r.close, "close", f.kind) : "") : "";
        return `<div class="srow ${["hol", "vacwd", "vacwe"].includes(k) ? "sp" : ""}"><div class="srh"><b><i class="dtdot" style="background:${DT_COLOR[k]}"></i>${esc(rowNames[k] || k)}</b>${subs[k] ? `<small>${esc(subs[k])}</small>` : ""}${sel}</div>${sent}${own}</div>`;
      }).join("");
      return `<label class="inl" style="margin-bottom:8px"><input type="checkbox" data-a="fsc" data-f="close_per_row" ${s.close_per_row ? "checked" : ""}> ${closeWord} je Tagesart unterschiedlich</label>
        ${s.close_per_row ? "" : `<div class="srow sp"><div class="srh"><b>▼&nbsp;${closeWord}</b><small>alle Tage</small></div>${this._specHtml("close", s.close, "close", f.kind, true)}</div>`}
        ${rows}
        <div class="hint" style="margin:4px 0 8px">Vorrang wie bei der Heizung: bestimmter Tag vor Feiertag vor Urlaub zu Hause vor Wochentag. Eine Uhrzeit zum ${closeWord} vor 12:00 (z. B. 00:30) gilt als „nach Mitternacht“ und gehört zum Vorabend.</div>
        <div class="srl guardl"><label class="chk"><input type="checkbox" data-a="fsc" data-f="guard_on" ${s.guard ? "checked" : ""}> Absicherung: um</label>
          <input class="inp tm" data-a="fsg" value="${esc(s.guard || "23:00")}" maxlength="5" ${s.guard ? "" : "disabled"} aria-label="Absicherung Uhrzeit"><span>nochmal ${cover ? "schließen" : "ausschalten"}</span>
          <small class="hint">(nur Geräte, die noch nicht so stehen; nicht an Tagen, die später ${cover ? "schließen" : "ausschalten"})</small></div>
        <div class="spo"><label><input type="checkbox" data-a="fsc" data-f="only_needed" ${s.only_needed ? "checked" : ""}> nur falls nötig <small class="hint">(nur Geräte, die noch nicht so stehen)</small></label>
          <label><input type="checkbox" data-a="fsc" data-f="verify" ${s.verify ? "checked" : ""}> nachprüfen &amp; wiederholen <small class="hint">(nach 5 min, bis zu 2×)</small></label></div>
        ${cover ? `<div class="reacthint">⚡ <b>Hitzeschutz nach Temperatur?</b> Das ist eine <b>Reaktion</b>, kein Zeitplan: „Wenn Außentemperatur über 25 °C → auf Position“. Zeitgesteuerter Hitzeschutz (z. B. 08:31 auf 1 %) geht als eigener Zeitplan mit „Zeitplan gilt: nur in Jahreszeit Heißphase“ und Öffnen „auf Position“.</div>` : ""}`;
    }

    /** Bestimmte Tage (0.9.9): jedes Jahr am selben Datum eigene Zeiten, z. B. Heiligabend, Silvester. */
    _specialDaysHtml(f, s) {
      const cover = f.kind === "cover", days = s.days || [];
      const c = (f.conds.items || [])[0], range = this._giltKey(f) === "range" && c ? c : null;
      const items = days.map((d, i) => {
        let warn = "";
        if (!mdOk(d.date)) warn = `Den ${mdText(d.date)} gibt es nicht.`;
        else if (days.findIndex((x) => x.date === d.date) !== i) warn = "Dieses Datum gibt es doppelt.";
        else if (range && mdOk(range.from) && mdOk(range.to) && !mdIn(d.date, range.from, range.to)) warn = `Liegt außerhalb des Zeitraums ${mdText(range.from)}–${mdText(range.to)} – wird nie verwendet.`;
        return `<div class="srow sday"><div class="srh"><b>📅</b>${mdSel(`data-a="fsday" data-i="${i}" data-f="date"`, d.date, "Datum")}
            <input class="inp" data-a="fsday" data-i="${i}" data-f="name" value="${esc(d.name || "")}" placeholder="Name (optional)" maxlength="30" style="max-width:170px">
            <span class="sp"></span><button class="x" data-a="fsdaydel" data-i="${i}" aria-label="Tag entfernen">×</button></div>
          ${this._specHtml(`days.${i}.open`, d.open || { ref: "normal" }, "open", f.kind, false, true)}
          ${this._specHtml(`days.${i}.close`, d.close || { ref: "normal" }, "close", f.kind, false, true)}
          ${warn ? `<div class="hint warn">${esc(warn)}</div>` : ""}</div>`;
      }).join("");
      return `${items}<button class="btn sm" data-a="fsdayadd" style="margin-top:6px">+ bestimmter Tag</button>
        <div class="hint">Jedes Jahr am selben Datum, z. B. Heiligabend, Silvester. Geht allen Tagesarten vor. „wie sonst“ = die Zeit der Tagesart bleibt. ${cover ? "Schließen" : "Ausschalten"} vor 12:00 (z. B. 02:00) = nach Mitternacht, zählt noch zu diesem Tag.</div>`;
    }

    // „Zeitplan gilt“: Kurzauswahl, sonst eigene Bedingungen (dieselben Bedingungen wie bisher)
    _giltKey(f) {
      const it = f.conds.items;
      if (this._fedit.giltCustom) return "custom";
      if (!it.length) return "always";
      if (it.length === 1 && !it[0].items) {
        const c = it[0], v = Array.isArray(c.value) ? c.value : [c.value];
        if (c.key === "vacation" && c.op === "not" && v.length === 1) return `vac:${v[0]}`;
        if (c.key === "season" && c.op === "is" && v.length === 1) return `season:${v[0]}`;
        if (c.key === "occasion" && c.op === "is" && v[0] === "christmas") return "xmas";
        if (c.key === "date" && c.op === "is") return "range";
      }
      return "custom";
    }

    _giltHtml(f) {
      const cv = this._data.flows.meta.cond_values, key = this._giltKey(f), p = this._fedit.preview;
      const opts = [["always", "immer"], ...cv.vacation.slice(1).map((v) => [`vac:${v}`, `nicht bei „${v}“`]), ...cv.season.map((v) => [`season:${v}`, `nur in Jahreszeit „${v}“`]), ["xmas", "nur zu Weihnachten (1. Advent – 6. Januar)"], ["range", "nur von … bis … (jedes Jahr)"], ["custom", "wenn … (eigene Bedingungen)"]];
      if (!opts.some(([v]) => v === key)) opts.splice(opts.length - 1, 0, [key, key.split(":").slice(1).join(":")]);
      const state = p ? (p.active ? `<span class="chip" style="color:#1b5e30">gilt gerade</span>` : `<span class="chip" style="color:#8c1d18">ruht gerade</span>`) : "";
      const c0 = (f.conds.items || [])[0];
      const sum = (key === "range" && c0 ? `nur vom ${mdText(c0.from)} bis ${mdText(c0.to)} (jedes Jahr)` : key === "custom" ? `wenn ${p && p.cond_text ? p.cond_text : "… (eigene Bedingungen)"}` : (opts.find(([v]) => v === key) || [0, key])[1])
        + (p ? (p.active ? " · gilt gerade" : " · ruht gerade") : "");
      return this._fold("gilt", "Zeitplan gilt", "wie bei der Heizung einmal für den ganzen Zeitplan", sum, `
        <div class="btnrow"><select class="inp" data-a="fgilt" aria-label="Zeitplan gilt">${opts.map(([v, n]) => `<option value="${esc(v)}" ${v === key ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>${state}</div>
        ${key === "custom" ? `<div class="acbox" style="margin-top:8px">${this._groupHtml(f.conds, "c", 0)}</div>` : ""}
        ${key === "range" ? this._rangeHtml(f.conds.items[0]) : ""}`);
    }

    // ------------------------------------------------------------ Abschnitte zum Aufklappen (0.9.10)
    // Zugeklappt: eine Zeile Zusammenfassung. Was zugeklappt ist, merkt sich der Browser (gilt für alle Zeitpläne).
    _foldsClosed() {
      if (!this._folds) {
        let saved = [];
        try { saved = JSON.parse(window.localStorage.getItem("home_rhythm_folds") || "[]"); } catch (e) { saved = []; }
        this._folds = new Set(Array.isArray(saved) ? saved.filter((x) => typeof x === "string").slice(0, 20) : []);
      }
      return this._folds;
    }

    _foldToggle(key, open) {
      const set = this._foldsClosed();
      if (open === undefined) open = set.has(key);
      if (open) set.delete(key); else set.add(key);
      try { window.localStorage.setItem("home_rhythm_folds", JSON.stringify([...set])); } catch (e) { /* privat/gesperrt: nur für diese Sitzung */ }
    }

    _fold(key, title, sub, summary, body, extra = "") {
      const closed = this._foldsClosed().has(key);
      return `<div class="fold ${closed ? "closed" : ""}">
        <div class="foldh"><button class="foldb" data-a="ffold" data-k="${key}" aria-expanded="${closed ? "false" : "true"}"><span class="chev">▸</span>
          <span class="foldt"><b>${esc(title)}</b>${closed ? `<small>${esc(summary || "")}</small>` : sub ? `<small class="sub2">${esc(sub)}</small>` : ""}</span></button>${closed ? "" : extra}</div>
        ${closed ? "" : `<div class="foldc">${body}</div>`}</div>`;
    }

    _specTxt(spec, cover, open) {
      if (!spec) return "–";
      const ref = spec.ref || "time";
      if (ref === "normal") return "wie sonst";
      if (ref === "none") return open ? (cover ? "nicht öffnen" : "nicht einschalten") : (cover ? "nicht schließen" : "nicht ausschalten");
      if (ref === "time") return spec.time || "–";
      const off = Number(spec.offset || 0), unit = spec.unit === "h" ? "Std." : "min", n = spec.unit === "h" ? off / 60 : off;
      return `${ref === "sunrise" ? "Sonnenaufgang" : "Sonnenuntergang"}${off ? ` ${off > 0 ? "+" : "−"}${Math.abs(n).toString().replace(".", ",")} ${unit}` : ""}`;
    }

    _foldSummaries(f) {
      const cover = f.kind === "cover", n = (f.devices || []).length, sels = (f.selectors || []).map((x) => this._selectorName(x));
      const names = (f.devices || []).slice(0, 3).map((e) => this._entName(e));
      const dev = [n ? `${n} Gerät${n === 1 ? "" : "e"}: ${names.join(", ")}${n > 3 ? " …" : ""}` : "", ...sels.map((x) => `🏷️ ${x}`)].filter(Boolean).join(" · ") || "noch keine Geräte";
      let times;
      if (f.mode === "simple" && f.simple) {
        const sm = f.simple, rows = sm.rows || {}, mf = rows.mf || {};
        const same = ["sa", "so"].every((k) => !rows[k] || rows[k].like === "mf");
        times = `${cover ? "auf" : "an"}: ${this._specTxt(mf.open, cover, true)} · ${cover ? "zu" : "aus"}: ${sm.close_per_row ? "je Tagesart" : this._specTxt(sm.close, cover, false)}${same ? " · alle Tage gleich" : " · Wochenende eigene Zeiten"}`;
      } else times = `${(f.points || []).length} Schaltpunkte`;
      const days = ((f.simple || {}).days || []);
      const special = days.length ? days.map((d) => `${d.name || "📅"} ${mdText(d.date)} (${this._specTxt(d.open, cover, true)} – ${this._specTxt(d.close, cover, false)})`).join(" · ") : "keine";
      return { dev, times, special };
    }

    _rangeHtml(c) {
      const at = (fld) => `data-a="fgdate" data-f="${fld}"`;
      const bad = [c.from, c.to].find((x) => !mdOk(x));
      const txt = bad ? `Den ${mdText(bad)} gibt es nicht – bitte anderes Datum wählen.`
        : `Jedes Jahr vom ${mdText(c.from)}, 0:00 Uhr, bis ${mdText(c.to)}, 23:59 Uhr${c.from > c.to ? " – über den Jahreswechsel" : ""}. Schaltzeiten nach Mitternacht (z. B. aus um 01:00) zählen noch zum letzten Tag.`;
      return `<div class="acbox" style="margin-top:8px"><div class="btnrow"><span>vom</span>${mdSel(at("from"), c.from, "Start")}<span>bis</span>${mdSel(at("to"), c.to, "Ende")}</div>
        <div class="hint ${bad ? "warn" : ""}" style="margin-top:6px">${esc(txt)}</div></div>`;
    }

    // ------------------------------------------------------------ Taster je Zeitplan (0.9.9)
    _buttonHtml(f) {
      const ed = this._fedit, b = f.button, cover = f.kind === "cover";
      const cand = Array.isArray(this._data.control_candidates) ? this._data.control_candidates : [], areas = this._data.areas || [];
      const areaName = (id) => ((areas.find((a) => a.id === id) || {}).name || "");
      const split = ed.bsplit ?? !!(b && Object.values(b.map || {}).some((v) => v !== "toggle"));
      const L = ed.blearn || {};
      const sorted = [...cand].sort((x, y) => (areaName(x.area_id) || "~").localeCompare(areaName(y.area_id) || "~") || x.name.localeCompare(y.name));
      let opts = sorted.map((x) => `<option value="${esc(x.device_id)}" ${b && b.device_id === x.device_id ? "selected" : ""}>${esc((areaName(x.area_id) ? `${areaName(x.area_id)} · ` : "") + x.name)}</option>`).join("");
      if (b && !cand.some((x) => x.device_id === b.device_id)) opts += `<option value="${esc(b.device_id)}" selected>${esc(b.name || b.device_id)}</option>`;
      const detecting = L.token && L.detect;
      const word = (on) => (cover ? (on ? "auf" : "zu") : on ? "an" : "aus");
      const acts = split ? [["on", `Taste „${word(true)}“`], ["off", `Taste „${word(false)}“`]] : [["toggle", "Taste"]];
      const rows = b ? acts.map(([act, name]) => {
        const map = b.map || {}, sig = Object.keys(map).find((k) => map[k] === act);
        const learning = L.token && !L.detect && L.act === act;
        const key = learning ? `<span class="learnwait">Jetzt die Taste drücken …</span>` : sig ? `<span class="keytag" title="${esc(sig)}">${esc(sigLabel(sig))}</span>` : `<span class="hint">nicht belegt</span>`;
        return `<div class="ctlrow"><span>${name}</span>${key}<span class="sp"></span>
          <button class="linkbtn" data-a="fblearn" data-v="${act}">${learning ? "abbrechen" : sig ? "neu anlernen" : "anlernen"}</button>
          ${sig && !learning ? `<button class="x" data-a="fbunmap" data-k="${esc(sig)}" aria-label="Belegung entfernen">✕</button>` : ""}</div>`;
      }).join("") : "";
      const auto = b ? Number(b.auto_off || 0) : 0;
      const autoOpts = [[0, `beim nächsten ${cover ? "Schließen" : "Ausschalten"} laut Plan`], [30, "nach 30 min"], [60, "nach 1 Std."], [120, "nach 2 Std."], [180, "nach 3 Std."], [240, "nach 4 Std."]];
      if (!autoOpts.some(([v]) => v === auto)) autoOpts.push([auto, `nach ${auto} min`]);
      const slug = String(f.name || "zeitplan").toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
      const bdev = b ? ((cand.find((x) => x.device_id === b.device_id) || {}).name || b.name || "Taster") : "";
      const bsum = (b ? [bdev, split ? "Tasten an/aus" : "eine Taste", auto ? `wieder ${word(false)} nach ${auto >= 60 ? `${(auto / 60).toString().replace(".", ",")} Std.` : `${auto} min`}` : ""] : ["kein Taster"])
        .concat(f.switch ? ["HA-Schalter"] : []).filter(Boolean).join(" · ");
      return `<div class="rcard">${this._fold("button", "Taster & HA-Schalter", "schaltet alle Geräte gemeinsam – wie von Hand; der Zeitplan läuft danach normal weiter", bsum, `<div class="acbox">
        <div class="btnrow"><select class="inp" data-a="fbdev" aria-label="Taster-Gerät" style="flex:1;min-width:0"><option value="">${b ? "– kein Taster –" : "+ Taster wählen (Gerät) …"}</option>${opts}</select>
          <button class="btn sm ${detecting ? "pri" : ""}" data-a="fbdetect">${detecting ? "Warte auf Tastendruck … (abbrechen)" : "Taste drücken zum Erkennen"}</button></div>
        <div class="hint">Liste: Geräte, die Tastendrücke melden (z. B. SONOFF SNZB-01M, Hue Dimmer, IKEA, Aqara W100), nach Raum sortiert. „Erkennen“: 20 s lang auf jeden Taster im Haus hören – der erste Druck legt Gerät und Taste fest.</div>
        ${L.msg ? `<div class="hint ${L.ok ? "" : "warn"}">${esc(L.msg)}</div>` : ""}
        ${b ? `${rows}
          <label class="chk" style="margin-top:8px;display:flex;gap:8px;align-items:center"><input type="checkbox" data-a="fbsplit" ${split ? "checked" : ""}> Eigene Tasten für „${word(true)}“ und „${word(false)}“</label>
          <div class="hint">${split ? "" : `Eine Taste: ist mindestens ein Gerät ${word(true)}, gehen alle ${word(false)}, sonst alle ${word(true)}.`}</div>
          <div class="btnrow" style="margin-top:6px"><span>Von Hand ${cover ? "geöffnet" : "eingeschaltet"} – wieder ${word(false)}:</span><select class="inp" data-a="fbopt" data-f="auto_off">${autoOpts.map(([v, n]) => `<option value="${v}" ${v === auto ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>
          <div class="btnrow" style="margin-top:6px"><span>Taster wirkt:</span><select class="inp" data-a="fbopt" data-f="scope">${[["always", "immer"], ["active", "nur wenn der Zeitplan gilt"]].map(([v, n]) => `<option value="${v}" ${(b.scope || "always") === v ? "selected" : ""}>${n}</option>`).join("")}</select></div>` : ""}
        <div style="margin-top:10px;border-top:1px solid var(--divider-color,#e0e0e0);padding-top:8px">
          <label class="chk" style="display:flex;gap:8px;align-items:center"><input type="checkbox" data-a="ffield" data-f="switch" ${f.switch ? "checked" : ""}> Auch als Schalter in Home Assistant</label>
          <div class="hint">switch.home_rhythm_${esc(slug)} – an = mindestens ein Gerät ${word(true)}. Schalten wirkt wie der Taster, z. B. für Sprache, Dashboard oder andere Automationen.</div></div>
      </div>`)}</div>`;
    }

    async _fbLearn(act, detect = false) {
      const ed = this._fedit, f = ed && ed.flow;
      if (!f) return;
      const dev = detect ? "*" : f.button && f.button.device_id;
      if (!dev) return;
      const token = {};
      ed.blearn = { act, detect, token, dev };
      this._renderFlowEditor();
      const alive = () => this._fedit === ed && ed.blearn && ed.blearn.token === token;
      try {
        await this._ws({ type: "home_rhythm/control/learn", device_id: dev, step: "start" });
        while (alive()) {
          await new Promise((r) => setTimeout(r, 700));
          if (!alive()) break;
          const r = await this._ws({ type: "home_rhythm/control/learn", device_id: dev, step: "result" });
          if (r.state === "done") {
            if (detect) {
              const old = f.button || {};
              f.button = { device_id: r.device_id, map: {}, auto_off: old.auto_off || 0, scope: old.scope || "always", name: r.name };
              ed.bsplit = false;
            }
            const a = detect ? "toggle" : act;
            f.button.map = f.button.map || {};
            for (const k of Object.keys(f.button.map)) if (f.button.map[k] === a || k === r.signature) delete f.button.map[k];
            f.button.map[r.signature] = a;
            ed.blearn = { ok: true, msg: detect ? `Erkannt: ${r.name} – ${r.label}` : null };
            break;
          }
          if (r.state !== "waiting") { ed.blearn = { msg: "Kein Tastendruck erkannt – bitte noch einmal." }; break; }
        }
      } catch (e) { if (alive()) ed.blearn = { msg: (e && e.message) || "Anlernen nicht möglich" }; }
      if (this._fedit === ed) { this._renderFlowEditor(); this._flowPreview(); }
    }

    _fbCancel() {
      const ed = this._fedit, L = ed && ed.blearn;
      if (L && L.token) this._ws({ type: "home_rhythm/control/learn", device_id: L.dev, step: "cancel" }).catch(() => {});
      if (ed) ed.blearn = null;
    }

    _canBackToSimple() {
      const ed = this._fedit, f = ed.flow;
      return !!(f.simple && ed.backPts && JSON.stringify(f.points) === ed.backPts);
    }

    _modeBarHtml(f) {
      const simple = f.mode === "simple", back = this._canBackToSimple();
      const why = simple ? "" : back ? "Zurück zur einfachen Eingabe" : f.simple ? "Schaltpunkte wurden geändert – zurück zu „Einfach“ verwirft diese Änderungen" : "Neu im einfachen Modus beginnen";
      return `<span class="modebar" role="group" aria-label="Eingabe"><button class="${simple ? "on" : ""}" data-a="fmode" data-v="simple" title="${esc(why)}">Einfach</button><button class="${simple ? "" : "on"}" data-a="fmode" data-v="advanced" title="Beliebige Schaltpunkte, Bedingungen je Schaltpunkt">Erweitert</button></span>`;
    }

    _editHasLights() {
      const f = this._fedit && this._fedit.flow;
      if (!f) return false;
      return (f.selectors || []).length > 0 || (f.devices || []).some((e) => e.startsWith("light."));
    }

    _stepHtml(s, i) {
      const meta = this._data.flows.meta;
      const kinds = Object.entries(meta.step_kinds).map(([k, n]) => `<option value="${k}" ${s.do === k ? "selected" : ""}>${esc(n)}</option>`).join("");
      let body = "";
      if (["on", "off", "blink", "toggle", "open", "close", "position"].includes(s.do)) body = this._entityTags(s.entities || [], "step", i);
      if (s.do === "position") body += `<label class="inl">Position <input class="inp" type="number" min="0" max="100" data-a="fstep" data-i="${i}" data-f="position" value="${esc(s.position ?? 50)}"> %</label>`;
      if (s.do === "on") body += `<label class="inl">Helligkeit <input class="inp" type="number" min="1" max="100" step="5" data-a="fstep" data-i="${i}" data-f="brightness" value="${esc(s.brightness ?? "")}" placeholder="–"> %</label>`;
      if (s.do === "blink") body += `<label class="inl"><input class="inp" type="number" min="1" max="10" data-a="fstep" data-i="${i}" data-f="times" value="${esc(s.times ?? 2)}">× blinken</label>
        <label class="inl">Tempo <select class="inp" data-a="fstep" data-i="${i}" data-f="pause">${[[3, "schnell (0,3 s)"], [5, "normal (0,5 s)"], [10, "langsam (1 s)"], [20, "sehr langsam (2 s)"]].map(([v, n]) => `<option value="${v}" ${(s.pause ?? 5) === v ? "selected" : ""}>${n}</option>`).join("")}</select></label>
        <div class="hint">Je Durchgang: alle aus – Pause – alle an – Pause. Am Ende sind die Geräte an.</div>`;
      if (s.do === "wait") {
        const secs = s.seconds ?? 60, unit = s._unit || (secs % 60 ? "s" : "min");
        const val = unit === "s" ? secs : String(Math.round(secs / 6) / 10).replace(".", ",");
        body = `<label class="inl"><input class="inp" type="text" inputmode="decimal" data-a="fstep" data-i="${i}" data-f="wait_val" value="${esc(val)}" aria-label="Dauer">
          <select class="inp" data-a="fstep" data-i="${i}" data-f="_unit"><option value="s" ${unit === "s" ? "selected" : ""}>Sekunden</option><option value="min" ${unit === "min" ? "selected" : ""}>Minuten</option></select></label>
          ${unit === "min" && secs % 60 ? `<span class="hint">= ${secs} s</span>` : ""}`;
      }
      if (s.do === "wait_until") {
        const u = s.until || { key: "entity", entity: "", op: "is", value: "off" };
        body = `<span class="cvv">${this._entSingleHtml(`wu|${i}`, u.entity, "Gerät suchen, z. B. Bewegungsmelder")}
          <select class="inp" data-a="fstep" data-i="${i}" data-f="u_op">${["is", "not", "above", "below"].map((o) => `<option value="${o}" ${o === u.op ? "selected" : ""}>${esc(meta.cond_ops[o])}</option>`).join("")}</select>
          <input class="inp" list="hr-dl-states" value="${esc(u.value ?? "")}" data-a="fstep" data-i="${i}" data-f="u_value" placeholder="off / Zahl"></span>
          <label class="inl">dann Nachlauf <input class="inp" type="number" min="0" data-a="fstep" data-i="${i}" data-f="after" value="${esc(s.after ?? 0)}"> s</label>`;
      }
      if (s.do === "notify") body = `<select class="inp" data-a="fstep" data-i="${i}" data-f="target"><option value="persistent">Benachrichtigung in HA</option>${(meta.notify_services || []).map((n) => `<option value="${esc(n)}" ${s.target === n ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
        <input class="inp" maxlength="200" data-a="fstep" data-i="${i}" data-f="message" value="${esc(s.message || "")}" placeholder="Text">`;
      return `<div class="rstep"><span class="hint">${i + 1}.</span><div class="rbody"><select class="inp" data-a="fstep" data-i="${i}" data-f="do">${kinds}</select>${body}</div>
        <button class="x" data-a="fstepdel" data-i="${i}" aria-label="Schritt entfernen">×</button></div>`;
    }

    _triggerHtml(t, i) {
      const meta = this._data.flows.meta;
      return `<div class="rstep"><span>⚡</span><div class="rbody">
        ${this._entSingleHtml(`trig|${i}`, t.entity, "Auslöser suchen, z. B. Bewegung Hoftor")}
        <select class="inp" data-a="ftrig" data-i="${i}" data-f="kind">${Object.entries(meta.trigger_kinds).map(([k, n]) => `<option value="${k}" ${t.kind === k ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
        ${t.kind === "state" ? `<input class="inp" list="hr-dl-states" value="${esc(t.to ?? "")}" data-a="ftrig" data-i="${i}" data-f="to" placeholder="Zustand (leer = jede Änderung, z. B. Knopf)">` : `<input class="inp" type="number" step="any" value="${esc(t.value ?? "")}" data-a="ftrig" data-i="${i}" data-f="value" placeholder="Schwelle">`}
        </div><button class="x" data-a="ftrigdel" data-i="${i}" aria-label="Auslöser entfernen">×</button></div>`;
    }

    _renderFlowEditor() {
      // Beim Ersetzen des Inhalts kann der Browser für das gerade verlassene Feld noch ein „change“ nachschieben –
      // das würde sonst mitten im Neuaufbau erneut zeichnen.
      if (this._fRendering) return;
      this._fRendering = true;
      try { this._renderFlowEditorInner(); } finally { this._fRendering = false; }
    }

    _renderFlowEditorInner() {
      const host = this.shadowRoot.getElementById("dlg");
      if (this._fpick) { host.innerHTML = this._pickerHtml(); return; }
      if (!this._fedit) { host.innerHTML = ""; return; }
      const f = this._fedit.flow, meta = this._data.flows.meta, plan = f.type === "plan";
      const sel = this._data.flows.selectors || {};
      const usesPos = plan && (f.mode === "simple" ? Object.values((f.simple || {}).rows || {}).some((r) => r.like === "own" && r.open && r.open.position != null && r.open.position !== "") : f.points.some((p) => p.action === "position"));
      const devTags = plan ? `<div class="tagrow">${(f.selectors || []).map((s, j) => `<span class="tag dyn">🏷️ ${esc(this._selectorName(s))}<button data-a="fseldel" data-j="${j}" aria-label="entfernen">×</button></span>`).join("")}
          ${(f.devices || []).map((e, j) => `<span class="tag">${esc(this._entName(e))}${(f.devices || []).filter((x) => this._entName(x) === this._entName(e)).length > 1 ? ` <small>${esc(e)}</small>` : ""}${usesPos ? ` <small>eigene Pos.</small><input class="inp mini-in" type="number" min="0" max="100" data-a="fovr" data-v="${esc(e)}" value="${esc(((f.overrides || {})[e] || {}).position ?? "")}" placeholder="–">` : ""}<button data-a="fentdel" data-f="devices" data-j="${j}" aria-label="entfernen">×</button></span>`).join("")}</div>
        <div class="btnrow" style="margin-top:8px"><div class="grow">${this._entPickHtml("dev", f.kind === "cover" ? "Rollladen suchen – Name oder Raum" : "Licht, Steckdose, Schalter suchen – Name oder Raum")}</div>
          <select class="inp" data-a="fseladd"><option value="">+ Bereich / Etage / Label …</option>
            ${[["area", "Bereich"], ["floor", "Etage"], ["label", "Label"]].map(([by, n]) => (sel[by] || []).length ? `<optgroup label="${n}">${sel[by].map((x) => `<option value="${by}|${esc(x.id)}">${esc(x.name)}</option>`).join("")}</optgroup>` : "").join("")}</select></div>` : "";
      const fsum = plan ? this._foldSummaries(f) : {};
      const nativeBox = `<div class="acbox native"><label class="nat"><input type="checkbox" data-a="ffield" data-f="native" ${f.native ? "checked" : ""}> <b>Auch als Automation in Home Assistant anlegen</b></label>
            <div class="hint">${f.native ? "Home Assistant führt den Ablauf aus (automations.yaml, ID home_rhythm_…) – er läuft auch, wenn Home Rhythm aus ist, und erscheint in den HA-Ablaufverfolgungen. Bitte nur hier bearbeiten. Vor dem ersten Schreiben legt Home Rhythm eine Sicherung der Datei an."
              : "Aus (Standard): Home Rhythm führt den Ablauf selbst aus – mit Protokoll, Überspringen, Nachprüfen und Vorschau."}</div></div>`;
      host.innerHTML = `<div class="ov" data-a="fovclick"><div class="dlg" role="dialog" aria-modal="true">
        <header><h2>${this._fedit.isNew ? (plan ? "Neuer Zeitplan" : "Neue Reaktion") : esc(f.name)}</h2><button class="x" data-a="fclose" aria-label="Schließen">✕</button></header>
        ${this._datalists()}
        <div class="cols"><div>
          <div class="grid3">
            <label>Symbol<input class="inp" value="${esc(f.icon || "")}" data-a="ffield" data-f="icon" maxlength="4"></label>
            <label>Name<input class="inp" value="${esc(f.name || "")}" data-a="ffield" data-f="name" maxlength="60" placeholder="z. B. Rollläden OG"></label>
            ${plan ? `<label>Art<select class="inp" data-a="ffield" data-f="kind">${Object.entries(meta.kinds).map(([k, n]) => `<option value="${k}" ${f.kind === k ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>` : `<span></span>`}
          </div>
          ${plan ? `<div class="foldall"><button class="linkbtn" data-a="ffoldall" data-v="open">alle aufklappen</button><button class="linkbtn" data-a="ffoldall" data-v="close">alle zuklappen</button></div>
            ${this._fold("dev", "Geräte", "einzeln oder automatisch über Bereich / Etage / Label", fsum.dev, `<div class="acbox">${devTags}</div>`)}
            ${this._fold("times", f.mode === "simple" ? "Zeiten je Tagesart" : "Schaltpunkte", "", fsum.times + (f.random ? ` · zufällig ±${f.random} min` : ""), `
              ${f.mode === "simple" ? this._simpleHtml(f) : `<div class="hint" style="margin-bottom:6px">Arbeitstag = Workday-Sensor; Feiertag und „Urlaub zu Hause“ = freier Tag</div>
              ${f.points.map((p, i) => this._pointHtml(p, i, f.kind)).join("")}
              <button class="btn sm" data-a="fptadd">+ Schaltpunkt</button>`}
              ${f.kind === "switch" ? `<label class="inl" style="margin-top:10px">Zeiten täglich zufällig verschieben um ± <input class="inp" type="number" min="0" max="60" step="5" data-a="ffield" data-f="random" value="${esc(f.random || 0)}"> min (Urlaubssimulation)</label>` : ""}`, this._modeBarHtml(f))}
            ${f.mode === "simple" ? this._fold("special", "Bestimmte Tage", "jedes Jahr am selben Datum eigene Zeiten", fsum.special, this._specialDaysHtml(f, this._ensureSimple(f))) : ""}`
          : `<div class="blk2 when"><div class="lbl">Wenn – eins davon</div>${f.triggers.map((t, i) => this._triggerHtml(t, i)).join("")}<button class="btn sm" data-a="ftrigadd">+ Auslöser</button></div>`}
          ${plan && f.mode === "simple" ? this._giltHtml(f)
            : plan ? this._fold("gilt", "Gilt nur wenn", "für den ganzen Ablauf – auch (a und b) oder (c und d)", f.conds.items.length ? `wenn ${(this._fedit.preview || {}).cond_text || "…"}` : "immer", `<div class="acbox">${this._groupHtml(f.conds, "c", 0)}</div>`)
            : `<div class="blk2 cnd"><div class="lbl">Und nur wenn</div>${this._groupHtml(f.conds, "c", 0)}</div>`}
          ${plan ? "" : `<div class="blk2 then"><div class="lbl">Dann – der Reihe nach</div>${f.steps.map((s, i) => this._stepHtml(s, i)).join("")}
            <button class="btn sm" data-a="fstepadd">+ Schritt</button>
            <label class="inl" style="margin-top:8px">Erneut ausgelöst, während es läuft: <select class="inp" data-a="ffield" data-f="mode">${Object.entries(meta.react_modes).map(([k, n]) => `<option value="${k}" ${f.mode === k ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label></div>`}
          ${plan ? "" : nativeBox}
        </div>
        <div class="rcol">${plan ? `${this._buttonHtml(f)}${nativeBox}` : ""}<div class="sticky" id="fprev">${this._flowPreviewHtml()}</div></div></div>
        <footer>${this._fedit.isNew ? "" : `<button class="btn warn" data-a="fdel">Löschen</button>`}<span class="sp"></span>
          <button class="btn" data-a="fclose">Abbrechen</button><button class="btn pri" data-a="fsave">Speichern</button></footer>
      </div></div>`;
    }

    async _saveFlow() {
      const ed = this._fedit;
      try {
        const res = await this._ws({ type: "home_rhythm/flow/save", flow: ed.flow });
        this._fedit = null;
        this._flowOpen.add(res.id);
        this._tab = "flows";
        this.shadowRoot.getElementById("dlg").innerHTML = "";
        this._tlCache = {};
        await this._fetch();
        if (res.native_error) alert(`Gespeichert, aber automations.yaml konnte nicht geschrieben werden: ${res.native_error}`);
      } catch (e) {
        ed.error = (e && e.message) || String(e);
        const pane = this.shadowRoot.getElementById("fprev");
        if (pane) pane.innerHTML = this._flowPreviewHtml();
      }
    }

    // Klicks im Bereich Übersicht/Abläufe. true = erledigt.
    async _flowClick(a, v, t, e) {
      if (a === "pkpick") { this._pickApply(t.dataset.t, v); return true; }
      if (a === "pkopen") { this._pick = { tgt: t.dataset.t, q: "", idx: 0 }; this._renderFlowEditor(); this._focusPick(t.dataset.t); this._openPick(t.dataset.t); return true; }
      if (a === "pkq") return true;
      if (this._pick && !e.target.closest(".epick")) this._closePick();
      const items = (this._data && this._data.flows && this._data.flows.items) || [];
      const ws = async (msg) => { try { await this._ws(msg); } catch (err) { alert((err && err.message) || String(err)); } this._tlCache = {}; await this._fetch(); };
      const f = this._fedit && this._fedit.flow;
      const rerender = () => { this._renderFlowEditor(); this._flowPreview(); };
      switch (a) {
        case "tldate": this._tlDate = v; this._render(); return true;
        case "tlnow": this._tlDate = null; this._tlMin = null; this._assume = {}; this._render(); return true;
        case "tlset": this._tlMin = Number(v); this._render(); return true;
        case "tlstep": this._tlMin = Math.max(0, Math.min(23 * 60 + 45, this._selMin() + Number(v))); this._render(); return true;
        case "assume": this._assume = { ...(this._assume || {}), [t.dataset.k]: v }; this._assOpen = true; this._render(); return true;
        case "assreset": this._assume = {}; this._render(); return true;
        case "ovfold": { const set = new Set(this._pref("ovClosed", [])); if (set.has(v)) set.delete(v); else set.add(v); this._setPref("ovClosed", [...set]); this._render(); return true; }
        case "devgo": this._devFilter = v; this._tab = "devices"; this._render(); return true;
        case "devtype": this._setPref("devType", v); this._render(); return true;
        case "devuse": this._setPref("devUse", v); this._render(); return true;
        case "devfold": { const set = new Set(this._pref("devClosed", [])); if (set.has(v)) set.delete(v); else set.add(v); this._setPref("devClosed", [...set]); this._render(); return true; }
        case "devfoldall": {
          const keys = v === "open" ? [] : [...this._grouped(this._data.rooms).map((g, gi) => `f:${g.name || gi}`), "f:abl"];
          this._setPref("devClosed", keys); this._render(); return true;
        }
        case "tlfilter": this._tlFilter = v; this._render(); return true;
        case "tlpast": this._tlPast = !this._tlPast; this._render(); return true;
        case "goflow": this._tab = "flows"; this._flowOpen.add(v); this._render(); return true;
        case "ftoggle": if (e.target.closest("button, input, label, select")) return true; this._flowOpen.has(v) ? this._flowOpen.delete(v) : this._flowOpen.add(v); this._render(); return true;
        case "sim": this._sim = { ...(this._sim || {}), [t.dataset.k]: v }; await this._loadSim(); return true;
        case "fapply": await ws({ type: "home_rhythm/flow/apply", flow_id: v }); return true;
        case "fskip": await ws({ type: "home_rhythm/flow/skip", flow_id: v }); return true;
        case "ftest": await ws({ type: "home_rhythm/flow/test", flow_id: v }); return true;
        case "fstop": await ws({ type: "home_rhythm/flow/stop", flow_id: v }); return true;
        case "fctl": this._qOpenFlow(v); return true;  // 0.9.12: Bedien-Fenster statt Leiste
        case "fsw": await ws({ type: "home_rhythm/flow/switch", flow_id: v, action: t.dataset.d }); return true;
        case "fmove": {
          const order = items.map((x) => x.id), i = order.indexOf(v), j = i + Number(t.dataset.d);
          if (j < 0 || j >= order.length) return true;
          [order[i], order[j]] = [order[j], order[i]];
          await ws({ type: "home_rhythm/flow/order", order });
          return true;
        }
        case "fnew": this._fpick = true; this._renderFlowEditor(); return true;
        case "ftpl": this._openFlowEditor(this._flowTemplates()[v][3], true); return true;
        case "fedit": this._openFlowEditor(items.find((x) => x.id === v), false); return true;
        case "fcopy": { const src = items.find((x) => x.id === v); this._openFlowEditor({ ...src, id: undefined, name: `${src.name} (Kopie)`, native: false }, true); return true; }
        case "fovclick": if (e.target === t) { this._fedit = null; this._fpick = false; this._renderFlowEditor(); } return true;
        case "fclose": this._fedit = null; this._fpick = false; this._renderFlowEditor(); return true;
        case "fsave": await this._saveFlow(); return true;
        case "fdel":
          if (!confirm(`„${f.name}“ wirklich löschen?`)) return true;
          await ws({ type: "home_rhythm/flow/delete", flow_id: f.id }); this._fedit = null; this._renderFlowEditor(); return true;
        case "fptadd": f.points.push({ days: "daily", ref: "time", time: "12:00", action: f.kind === "cover" ? "open" : "on", conds: { op: "and", items: [] } }); rerender(); return true;
        case "fptdel": f.points.splice(Number(t.dataset.i), 1); rerender(); return true;
        case "ftype": { const p = f.points[Number(t.dataset.i)]; p.types = (p.types || []).includes(v) ? p.types.filter((x) => x !== v) : [...(p.types || []), v]; rerender(); return true; }
        case "fsim": this._fedit.sim = v; this._renderFlowEditor(); this._flowPreview(); return true;
        case "ffold": this._foldToggle(t.dataset.k); this._renderFlowEditor(); return true;
        case "ffoldall": for (const k of ["dev", "times", "special", "gilt", "button"]) this._foldToggle(k, v === "open"); this._renderFlowEditor(); return true;
        case "fweek": {
          const ed = this._fedit, base = ed.week || (ed.preview && ed.preview.dates ? ed.preview.dates[0] : null);
          if (v === "now") ed.week = null;
          else if (v === "prev" || v === "next") { const d = base ? new Date(`${base}T12:00:00`) : new Date(); d.setDate(d.getDate() + (v === "next" ? 7 : -7)); ed.week = isoDay(d); }
          else ed.week = v;  // Datum (JJJJ-MM-TT) – das Backend nimmt die Woche, in der es liegt
          this._flowPreview(); return true;
        }
        case "fmode": {
          if (v === f.mode) return true;
          if (v === "advanced") {
            // frisch umrechnen (die Vorschau kann ein paar Millisekunden hinterherhinken)
            let pts;
            try { pts = (await this._ws({ type: "home_rhythm/flow/expand", kind: f.kind, simple: f.simple })).points; }
            catch (err) { alert(`Umschalten nicht möglich: ${(err && err.message) || err}`); return true; }
            f.points = clone(pts).map((p) => ({ ...p, conds: p.conds && p.conds.items ? p.conds : { op: "and", items: [] } }));
            f.mode = "advanced";
            this._fedit.backPts = JSON.stringify(f.points);
          } else {
            if (!this._canBackToSimple()) {
              const msg = f.simple ? "Die Schaltpunkte wurden im erweiterten Modus geändert. Zurück zu „Einfach“ verwirft diese Änderungen. Fortfahren?"
                : "Dieser Zeitplan wurde im erweiterten Modus angelegt. Im einfachen Modus mit neuen Zeiten beginnen? Die bisherigen Schaltpunkte werden ersetzt.";
              if (!confirm(msg)) return true;
            }
            f.mode = "simple";
            this._ensureSimple(f);
          }
          rerender(); return true;
        }
        case "fwday": { const p = f.points[Number(t.dataset.i)], j = Number(v); p.weekdays = (p.weekdays || []).includes(j) ? p.weekdays.filter((x) => x !== j) : [...(p.weekdays || []), j].sort(); rerender(); return true; }
        case "fsdayadd": this._ensureSimple(f).days.push({ date: "12-24", name: "", open: { ref: "normal" }, close: { ref: "time", time: "01:00" } }); rerender(); return true;
        case "fsdaydel": f.simple.days.splice(Number(t.dataset.i), 1); rerender(); return true;
        case "fblearn": { const L = this._fedit.blearn; if (L && L.token && !L.detect && L.act === v) { this._fbCancel(); rerender(); } else { this._fbCancel(); this._fbLearn(v); } return true; }
        case "fbdetect": { const L = this._fedit.blearn; this._fbCancel(); if (L && L.token && L.detect) rerender(); else this._fbLearn(null, true); return true; }
        case "fbunmap": if (f.button) delete f.button.map[t.dataset.k]; rerender(); return true;
        case "fcondadd": this._resolveGroup(t.dataset.p).items.push({ key: "season", op: "is", value: [this._data.flows.meta.cond_values.season[0]] }); rerender(); return true;
        case "fgrpadd": this._resolveGroup(t.dataset.p).items.push({ op: "or", items: [{ key: "vacation", op: "is", value: [this._data.flows.meta.cond_values.vacation[0]] }] }); rerender(); return true;
        case "fconddel": this._resolveGroup(t.dataset.p).items.splice(Number(t.dataset.i), 1); rerender(); return true;
        case "fentdel":
          if (t.dataset.f === "devices") { const e2 = f.devices.splice(Number(t.dataset.j), 1)[0]; if (f.overrides) delete f.overrides[e2]; }
          else f.steps[Number(t.dataset.i)].entities.splice(Number(t.dataset.j), 1);
          rerender(); return true;
        case "fseldel": f.selectors.splice(Number(t.dataset.j), 1); rerender(); return true;
        case "ftrigadd": f.triggers.push({ kind: "state", entity: "", to: "on" }); rerender(); return true;
        case "ftrigdel": f.triggers.splice(Number(t.dataset.i), 1); rerender(); return true;
        case "fstepadd": f.steps.push({ do: "off", entities: [] }); rerender(); return true;
        case "fstepdel": f.steps.splice(Number(t.dataset.i), 1); rerender(); return true;
        case "export": {
          try {
            const data = await this._ws({ type: "home_rhythm/export" });
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = `home-rhythm-sicherung-${this._data.now.slice(0, 10)}.json`;
            document.body.appendChild(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(link.href), 5000);
          } catch (err) { alert((err && err.message) || String(err)); }
          return true;
        }
        default: return false;
      }
    }

    // Änderungen in Formularfeldern der Abläufe. true = erledigt.
    _flowChange(a, t) {
      if (a === "tlpick") { if (t.value) { this._tlDate = t.value; this._render(); } return true; }
      if (a === "tlrange") { this._tlMin = Number(t.value) * 15; this._render(); return true; }
      if (a === "ovopt") { this._setPref(t.dataset.k, t.checked); this._render(); return true; }
      if (a === "ovinactive") { this._setPref("ovInactive", t.checked); this._render(); return true; }
      if (a === "qskip" && this._q) { this._q.skip = t.checked; this._q.dirty = true; this._renderQ(); return true; }
      if (a === "devpref") { this._setPref(t.dataset.k, t.checked); this._render(); return true; }
      if (a === "fenabled") { this._ws({ type: "home_rhythm/flow/enabled", flow_id: t.dataset.v, enabled: t.checked }).then(() => this._fetch()).catch((e) => alert(e.message)); return true; }
      if (a === "import") {
        const file = t.files && t.files[0];
        if (!file) return true;
        if (file.size > 2_000_000) { alert("Die Datei ist zu groß."); return true; }
        t.value = ""; // dieselbe Datei später erneut wählbar
        file.text().then((txt) => this._ws({ type: "home_rhythm/import", data: JSON.parse(txt) }))
          .then((res) => { this._importMsg = `Eingelesen: ${res.rooms} Räume, ${res.flows} Abläufe${res.errors.length ? ` – Probleme: ${res.errors.join("; ")}` : ""}`; this._fetch(); })
          .catch((e) => { this._importMsg = `Import fehlgeschlagen: ${(e && e.message) || e}`; this._render(); });
        return true;
      }
      if (!this._fedit) return false;
      const f = this._fedit.flow, i = Number(t.dataset.i), fld = t.dataset.f;
      this._fedit.inputError = null;  // neue Eingabe – alter Hinweis verschwindet
      const num = (x) => (x === "" || x == null ? undefined : Number(String(x).replace(",", ".")));
      switch (a) {
        case "fweekdate": if (t.value) { this._fedit.week = t.value; this._flowPreview(); } return;
        case "fgdate": { const c = f.conds.items[0]; if (c) c[fld] = mdSet(c[fld], t.dataset.part, t.value); break; }
        case "fsday": { const d = f.simple.days[i]; if (fld === "name") d.name = t.value.slice(0, 30); else d.date = mdSet(d.date, t.dataset.part, t.value); break; }
        case "fbdev": {
          this._fbCancel();
          const old = f.button || {};
          f.button = t.value ? { device_id: t.value, map: {}, auto_off: old.auto_off || 0, scope: old.scope || "always" } : null;
          this._fedit.bsplit = false;
          break;
        }
        case "fbopt": if (f.button) f.button[fld] = fld === "auto_off" ? Number(t.value) || 0 : t.value; break;
        case "fbsplit": this._fbCancel(); this._fedit.bsplit = t.checked; if (f.button) f.button.map = {}; break;
        case "ffield":
          if (fld === "native") f.native = t.checked;
          else if (fld === "switch") f.switch = t.checked;
          else if (fld === "random") f.random = Number(t.value) || 0;
          else if (fld === "kind") {
            f.kind = t.value; f.devices = []; f.overrides = {};
            f.points.forEach((p) => { p.action = this._data.flows.meta.actions[f.kind][0]; });
            if (f.simple) Object.values(f.simple.rows).forEach((r) => { delete r.open.position; delete r.open.brightness; });
          }
          else f[fld] = t.value;
          break;
        case "fpt": {
          const p = f.points[i];
          if (["time", "earliest", "latest"].includes(fld)) { const n = t.value.trim() ? normTime(t.value) : ""; if (n === null) { this._fedit.error = `„${t.value}“ ist keine Uhrzeit`; break; } p[fld] = n || undefined; }
          else if (["offset", "position", "brightness"].includes(fld)) p[fld] = num(t.value);
          else p[fld] = t.value;
          if (fld === "ref" && t.value === "time" && !p.time) p.time = "07:00";
          if (fld === "days" && t.value === "custom" && !(p.weekdays || []).length) p.weekdays = [0, 1, 2, 3, 4];
          if (fld === "days" && t.value === "type" && !(p.types || []).length) p.types = ["mf"];
          if (fld === "days" && t.value === "dates" && !(p.dates || []).length) p.dates = ["12-24"];
          if (fld === "dates") p.dates = t.value.split(/[,;\s]+/).filter(Boolean).map(mdParse);
          break;
        }
        case "fptc": f.points[i][fld] = t.checked; break;
        case "fsp": {
          const o = this._simObj(t.dataset.p);
          if (fld === "ref") {
            o.ref = t.value;
            if (t.value === "time" && !o.time) o.time = t.dataset.p.endsWith("open") ? "07:00" : "22:00";
            if (["sunrise", "sunset"].includes(t.value) && o.offset == null) { o.offset = 0; o.unit = "min"; }
          } else if (["time", "earliest", "latest"].includes(fld)) {
            const n = t.value.trim() ? normTime(t.value) : "";
            if (n === null) { this._fedit.inputError = `„${t.value}“ ist keine Uhrzeit (hh:mm) – nicht übernommen.`; break; }
            if (n) o[fld] = n; else delete o[fld];
          } else if (fld === "offset") {
            const x = parseFloat(String(t.value).replace(",", ".")) || 0;
            const m = Math.round(o.unit === "h" ? x * 60 : x);
            o.offset = Math.max(-300, Math.min(300, m));
            if (m !== o.offset) this._fedit.inputError = "Versatz höchstens ± 5 Std. (300 min).";
          } else if (fld === "unit") o.unit = t.value;
          else if (fld === "target") { if (t.value === "pos") o.position = o.position ?? 30; else delete o.position; }
          else if (fld === "position" || fld === "brightness") { const n2 = num(t.value); if (n2 === undefined) delete o[fld]; else o[fld] = n2; }
          break;
        }
        case "fsl": f.simple.rows[t.dataset.v].like = t.value; break;
        case "fsc":
          if (fld === "guard_on") f.simple.guard = t.checked ? (f.simple.guard || "23:00") : "";
          else f.simple[fld] = t.checked;
          break;
        case "fsg": { const n = normTime(t.value); if (n) f.simple.guard = n; else this._fedit.inputError = `„${t.value}“ ist keine Uhrzeit (hh:mm) – nicht übernommen.`; break; }
        case "fgilt": {
          const cv = this._data.flows.meta.cond_values;
          this._fedit.giltCustom = t.value === "custom";
          if (t.value === "always") f.conds = { op: "and", items: [] };
          else if (t.value.startsWith("vac:")) f.conds = { op: "and", items: [{ key: "vacation", op: "not", value: [t.value.slice(4)] }] };
          else if (t.value.startsWith("season:")) f.conds = { op: "and", items: [{ key: "season", op: "is", value: [t.value.slice(7)] }] };
          else if (t.value === "xmas") f.conds = { op: "and", items: [{ key: "occasion", op: "is", value: "christmas" }] };
          else if (t.value === "range") f.conds = { op: "and", items: [{ key: "date", op: "is", from: "11-28", to: "01-06" }] };
          else if (!f.conds.items.length) f.conds = { op: "and", items: [{ key: "vacation", op: "not", value: [cv.vacation[cv.vacation.length - 1]] }] };
          break;
        }
        case "fcond": {
          const c = this._resolveGroup(t.dataset.p).items[i];
          if (fld === "key") {
            const cv = this._data.flows.meta.cond_values, fixed = this._data.flows.meta.cond_fixed[t.value];
            c.key = t.value; c.op = "is"; delete c.entity; delete c.flow; delete c.from; delete c.to;
            c.value = fixed ? Object.keys(fixed)[0] : t.value === "entity" ? "on" : t.value === "flow" ? "closed" : [(cv[t.value] || [""])[0]];
            if (t.value === "flow") c.flow = (this._data.flows.items.find((x) => x.type === "plan") || {}).id || "";
            if (t.value === "date") { delete c.value; c.from = "11-28"; c.to = "01-06"; }
          } else if (fld === "from" || fld === "to") c[fld] = mdSet(c[fld], t.dataset.part, t.value);
          else if (fld === "value") c.value = ["season", "vacation", "event"].includes(c.key) ? [t.value] : t.value;
          else c[fld] = t.value;
          break;
        }
        case "fgrpop": { const p = t.dataset.p; (p.includes(".") || p.startsWith("p") ? this._resolveGroup(p) : f.conds).op = t.value; break; }
        case "fovr": { f.overrides = f.overrides || {}; const val = num(t.value); if (val === undefined) delete f.overrides[t.dataset.v]; else f.overrides[t.dataset.v] = { position: val }; break; }
        case "fseladd": { if (!t.value) return true; const [by, id] = t.value.split("|"); f.selectors = f.selectors || []; if (!f.selectors.some((s) => s.by === by && s.id === id)) f.selectors.push({ by, id }); break; }
        case "ftrig": {
          const tr = f.triggers[i];
          if (fld === "kind") { tr.kind = t.value; if (t.value === "state") { tr.to = "on"; delete tr.value; } else { tr.value = tr.value ?? 0; delete tr.to; } }
          else if (fld === "to") tr.to = t.value.trim() || null;
          else if (fld === "value") tr.value = num(t.value);
          else tr[fld] = t.value.trim();
          break;
        }
        case "fstep": {
          const s = f.steps[i];
          if (fld === "do") {
            const keep = s.entities || [];
            Object.keys(s).forEach((k) => delete s[k]);
            s.do = t.value;
            if (t.value === "toggle") s.entities = keep;
            else if (["on", "off", "blink", "open", "close", "position"].includes(t.value)) s.entities = ["open", "close", "position"].includes(t.value) ? keep.filter((x) => x.startsWith("cover.")) : keep.filter((x) => !x.startsWith("cover."));
            if (t.value === "wait") s.seconds = 60;
            if (t.value === "wait_until") { s.until = { key: "entity", entity: "", op: "is", value: "off" }; s.after = 0; }
            if (t.value === "blink") s.times = 2;
            if (t.value === "notify") { s.target = "persistent"; s.message = ""; }
          } else if (fld === "wait_val") {
            const x = parseFloat(String(t.value).replace(",", ".")) || 0, unit = s._unit || (s.seconds % 60 ? "s" : "min");
            s.seconds = Math.max(1, Math.round(unit === "s" ? x : x * 60));
            s._unit = unit;
          } else if (fld === "_unit") s._unit = t.value;
          else if (fld === "pause") s.pause = Number(t.value);
          else if (fld.startsWith("u_")) { s.until = s.until || { key: "entity", op: "is" }; s.until[fld.slice(2)] = fld === "u_value" && ["above", "below"].includes(s.until.op) ? num(t.value) : t.value.trim(); }
          else if (["position", "brightness", "times", "after"].includes(fld)) s[fld] = num(t.value);
          else s[fld] = t.value;
          break;
        }
        default: return false;
      }
      this._renderFlowEditor();
      this._flowPreview();
      return true;
    }

    // ------------------------------------------------------------ Editor
    _openEditor(roomId, areaId, entityId) {
      const d = this._data;
      let room;
      if (roomId) room = clone(this._room(roomId));
      else {
        const area = d.areas.find((a) => a.id === areaId);
        const cands = areaId ? d.climates.filter((c) => c.area_id === areaId && !c.wrapped_by && !d.rooms.some((r) => r.climate_entities.includes(c.entity_id) || (r.ac_entities || []).includes(c.entity_id))) : [];
        const picks = entityId ? [entityId] : cands.map((c) => c.entity_id);
        const pick = picks[0] || "";
        const pickArea = areaId || (d.climates.find((c) => c.entity_id === pick) || {}).area_id || null;
        room = {
          id: null, name: area ? area.name : (d.climates.find((c) => c.entity_id === pick) || {}).name || "", area_id: pickArea,
          climate_entities: picks, levels: clone(d.default_temps), default_level: "absenkung", manual_mode: "next", enabled: true,
          schedule: { wd: [["00:00", "05:30", "nacht"], ["06:00", "08:00", "komfort"], ["17:00", "22:00", "komfort"]], sa: [["07:30", "22:30", "komfort"]], so: [["07:30", "22:30", "komfort"]] },
        };
      }
      for (const [k] of DAY_TYPES) room.schedule[k] = room.schedule[k] || [];
      room.ac_entities = room.ac_entities || [];
      room.ac = clone(room.ac || d.energy.default_ac);
      // Neue Räume: Geräte mit Kühlfunktion sind Klimaanlagen
      if (!roomId) {
        const cool = new Set(d.climates.filter((c) => c.can_cool).map((c) => c.entity_id));
        room.ac_entities = room.climate_entities.filter((e) => cool.has(e));
        room.climate_entities = room.climate_entities.filter((e) => !cool.has(e));
      }
      // 0.9.5: Art, Temperaturquelle, Korrektur (fehlt → wie bisher)
      if (!room.kind) {
        const kinds = room.climate_entities.map((e) => (d.climates.find((c) => c.entity_id === e) || {}).kind).filter(Boolean);
        room.kind = kinds.includes("bt") ? "bt" : kinds.includes("integration") ? "integration" : kinds.includes("fritz") ? "fritz" : kinds[0] || "direct";
      }
      room.temp_source = room.temp_source || "device";
      room.temp_sensors = room.temp_sensors || [];
      room.box_sensor = room.box_sensor || "";
      room.correction = room.correction || "none";
      room.correction_value = room.correction_value || 0;
      room.controls = clone(room.controls || []);
      this._editor = { room, error: null, preview: null };
      this._renderEditor();
      this._editorPreview();
    }

    _closeEditor() { this._editor = null; this.shadowRoot.getElementById("dlg").innerHTML = ""; this._fetch(); }

    /** Schritt 4: Bedienteile (0.9.7) – Gerät wählen, je Funktion einmal die Taste drücken („anlernen“). */
    _ctlEditorHtml(room) {
      const d = this._data, cand = Array.isArray(d.control_candidates) ? d.control_candidates : [];
      const ctls = room.controls || [];
      const ACT = [["warmer", "Wärmer"], ["colder", "Kälter"], ["back", "Zurück zum Plan"], ["boost", "Booster 1 Std."], ["comfort", "Komfort bis Wechsel"], ["off", "Aus bis Wechsel"]];
      const devName = (c) => ((cand.find((x) => x.device_id === c.device_id) || {}).name || c.name || (c.device_id.startsWith("entity:") ? c.device_id.slice(7) : c.device_id));
      const items = ctls.map((c, i) => {
        const map = c.map || {};
        const info = cand.find((x) => x.device_id === c.device_id) || {};
        const disp = c.display || info.display;
        const rows = ACT.map(([act, name]) => {
          const sig = Object.keys(map).find((k) => map[k] === act);
          const learning = this._editor.learn && this._editor.learn.i === i && this._editor.learn.act === act;
          const key = learning ? `<span class="learnwait">Jetzt die Taste drücken …</span>` : sig ? `<span class="keytag" title="${esc(sig)}">${esc(sigLabel(sig))}</span>` : `<span class="hint">nicht belegt</span>`;
          return `<div class="ctlrow"><span>${name}</span>${key}<span class="sp"></span>
            <button class="linkbtn" data-a="ctllearn" data-i="${i}" data-v="${act}">${learning ? "abbrechen" : sig ? "neu anlernen" : "anlernen"}</button>
            ${sig && !learning ? `<button class="x" data-a="ctlunmap" data-i="${i}" data-k="${esc(sig)}" aria-label="Belegung entfernen">✕</button>` : ""}</div>`;
        }).join("");
        const err = this._editor.learn && this._editor.learn.i === i && this._editor.learn.msg;
        return `<div class="ctl"><div class="ctlhd"><b>${esc(devName(c))}</b>${disp ? `<span class="badge">mit Anzeige</span>` : ""}<span class="sp"></span><button class="linkbtn" data-a="ctldel" data-i="${i}">entfernen</button></div>
          ${disp ? `<label class="rtopt"><input type="checkbox" data-a="ctldisp" data-i="${i}" data-v="${esc(disp)}" ${c.display ? "checked" : ""}> Sollwert des Raums auf dem Display zeigen</label>` : ""}
          <div class="hint">„anlernen“ antippen, dann am Gerät die Taste drücken. Nicht belegte Tasten bleiben frei für andere Automationen.</div>
          ${rows}${err ? `<div class="hint warn">${esc(err)}</div>` : ""}
          <div class="pills"><span class="hint">Schritt für wärmer / kälter (Tasten ohne eigenen Wert):</span>${[[0.5, "0,5 °C"], [1, "1 °C"]].map(([v, n]) => `<button class="seg ${(c.step || 0.5) === v ? "on" : ""}" data-a="ctlstep" data-i="${i}" data-v="${v}">${n}</button>`).join("")}</div></div>`;
      }).join("");
      const used = new Set(d.rooms.flatMap((r) => (r.id === room.id ? [] : (r.controls || []).map((c) => c.device_id))).concat(ctls.map((c) => c.device_id)));
      const inRoom = (x) => !room.area_id || !x.area_id || x.area_id === room.area_id || this._editor.ctlAll;
      const opts = cand.filter((x) => !used.has(x.device_id) && inRoom(x));
      return `<h3 class="step"><b>4</b> · Bedienteile <small>(optional, mehrere möglich)</small></h3><div class="rtsec">${items}
        <div class="pills"><select class="inp" data-a="ctladd"><option value="">+ Bedienteil (Gerät) …</option>${opts.map((x) => `<option value="${esc(x.device_id)}">${esc(x.name)}${x.display ? " · mit Anzeige" : ""}</option>`).join("")}</select>
          <button class="linkbtn" data-a="ctlall">${this._editor.ctlAll ? "nur Geräte aus diesem Bereich" : "Geräte aus anderen Bereichen zeigen"}</button></div>
        <div class="hint">Taster und Bedienteile mit Anzeige, z. B. SONOFF SNZB-01M, Hue Dimmer, IKEA, Aqara W100. Sie bedienen den Raum – gleich welche Thermostate er hat.</div></div>`;
    }

    async _ctlLearn(i, act) {
      const ed = this._editor, c = ed && ed.room.controls[i];
      if (!c) return;
      const token = {};
      ed.learn = { i, act, token };
      this._renderEditor();
      const alive = () => this._editor === ed && ed.learn && ed.learn.token === token;
      try {
        await this._ws({ type: "home_rhythm/control/learn", device_id: c.device_id, step: "start" });
        while (alive()) {
          await new Promise((r) => setTimeout(r, 700));
          if (!alive()) break;
          const r = await this._ws({ type: "home_rhythm/control/learn", device_id: c.device_id, step: "result" });
          if (r.state === "done") {
            c.map = c.map || {};
            for (const k of Object.keys(c.map)) if (c.map[k] === act || k === r.signature) delete c.map[k];
            c.map[r.signature] = act;
            ed.learn = null;
            break;
          }
          if (r.state !== "waiting") { ed.learn = { i, msg: "Kein Tastendruck erkannt – bitte noch einmal." }; break; }
        }
      } catch (e) { if (alive()) ed.learn = { i, msg: (e && e.message) || "Anlernen nicht möglich" }; }
      if (this._editor === ed) this._renderEditor();
    }

    /** Schritte 2 und 3 der Raum-Einrichtung: Sensoren und Korrektur (0.9.5). */
    _rtEditorHtml(room) {
      const d = this._data, integ = room.kind === "bt" || room.kind === "integration";
      const intName = room.kind === "bt" ? "Better Thermostat" : "die Regel-Integration";
      const all = d.temperature_sensors || [];
      const radio = (v, label, sub) => `<label class="rtopt"><input type="radio" name="rtsrc" data-a="rtsrc" value="${v}" ${room.temp_source === v ? "checked" : ""}> ${label}${sub ? ` <small>${sub}</small>` : ""}</label>`;
      const val = (x) => (x.value != null ? `${fmtNum(x.value, 1)} °C` : "–");
      const areaName = (id) => ((d.areas.find((a) => a.id === id) || {}).name || "");
      let step2;
      if (integ) {
        const live = room.id && this._room(room.id) && this._room(room.id).room_temp;
        const s = live && live.integration_sensor;
        const other = s && room.area_id && s.area_id && s.area_id !== room.area_id;
        step2 = `<div class="rtinfo">${room.kind === "bt" ? "Better Thermostat" : "Die Regel-Integration"} misst mit: <b>${s ? `${esc(s.name)}, ${val(s)}` : "– (nach dem Speichern sichtbar)"}</b>
          ${s ? `<span class="badge ${other ? "warnb" : "okb"}">${other ? `⚠ Bereich ${esc(areaName(s.area_id))}` : "✓"}</span>` : ""}
          <div class="hint">Einstellen in ${room.kind === "bt" ? "Better Thermostat" : "der Integration"}. Mehrere Sensoren dort: als HA-Helfer „Gruppe → Sensor (Mittelwert)“ zusammenfassen und diesen eintragen.</div></div>`;
      } else {
        const here = all.filter((x) => room.area_id && x.area_id === room.area_id);
        const rest = all.filter((x) => !here.includes(x));
        const chosen = new Set(room.temp_sensors);
        const list = [...here, ...rest.filter((x) => this._editor.rtMore || chosen.has(x.entity_id))];
        const sens = list.map((x) => `<label class="rtsub"><input type="checkbox" data-a="rtsens" data-v="${esc(x.entity_id)}" ${chosen.has(x.entity_id) ? "checked" : ""}> ${esc(x.name)} <small class="${room.area_id && x.area_id && x.area_id !== room.area_id ? "warnt" : ""}">${val(x)}${x.area_id && x.area_id !== room.area_id ? ` · Bereich ${esc(areaName(x.area_id))}` : ""}</small></label>`).join("") || `<div class="hint rtsub">Im Bereich ist kein Temperatursensor.</div>`;
        const vals = all.filter((x) => chosen.has(x.entity_id) && x.value != null).map((x) => x.value);
        const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
        const boxOpts = all.filter((x) => x.platform === "fritzbox" || x.entity_id === room.box_sensor || (room.area_id && x.area_id === room.area_id));
        step2 = radio("device", "Fühler am Thermostat", "(wie bisher)")
          + radio("sensors", "Sensoren im Raum", "– bei mehreren der Durchschnitt")
          + (room.temp_source === "sensors" ? `<div class="rtgroup">${sens}
              <button class="linkbtn" data-a="rtmore">${this._editor.rtMore ? "nur Sensoren aus diesem Bereich zeigen" : "Sensoren aus anderen Bereichen zeigen"}</button>
              <div>${!chosen.size ? "Bitte mindestens einen Sensor wählen." : vals.length > 1 ? `Durchschnitt aus ${vals.length}: <b>${fmtNum(avg, 1)} °C</b>` : avg != null ? `Gemessen: <b>${fmtNum(avg, 1)} °C</b>` : ""}</div>
              <div class="hint">Sensoren, die nicht verfügbar sind oder seit 12 Std. nichts melden, zählen nicht mit. Liegen die Werte mehr als 2 °C auseinander, gibt es einen Hinweis.</div></div>` : "")
          + (room.kind === "fritz" ? radio("box", "In der Fritz!Box eingestellt", "– z. B. FRITZ!DECT 440 als Raumsensor")
            + (room.temp_source === "box" ? `<div class="rtgroup"><label>Anzeigen in Home Rhythm von<select class="inp" data-a="rtbox"><option value="">– bitte wählen –</option>
                ${boxOpts.map((x) => `<option value="${esc(x.entity_id)}" ${x.entity_id === room.box_sensor ? "selected" : ""}>${esc(x.name)} · ${val(x)}</option>`).join("")}</select></label>
                <div class="hint">Das Thermostat regelt in der Fritz!Box nach diesem Sensor – Home Rhythm schickt den Sollwert unverändert und zeigt den Wert als Ist. Einstellen: Fritz!Box → Smart Home → Thermostat → Temperatur (ab FRITZ!OS 7.20).</div></div>` : "") : "");
      }
      let step3;
      if (integ) step3 = `<div class="hint">Macht ${intName} selbst – hier nichts einzustellen.</div>`;
      else if (room.temp_source === "box") step3 = `<div class="hint">Macht die Fritz!Box – hier nichts einzustellen. Misst der Sensor zu viel oder zu wenig, dort einen Temperatur-Versatz einstellen.</div>`;
      else if (room.kind === "direct" && room.temp_source === "sensors") step3 = `<div class="hint">Home Rhythm schickt den Raumwert ans Thermostat (bei jeder Änderung, spätestens alle 10 min) und stellt es auf externe Temperatur. Das Thermostat regelt dann selbst nach dem Raum – keine Korrektur nötig.</div>`;
      else {
        const opts = [["none", "keine"], ["fixed", "fest"], ...(room.kind === "fritz" && room.temp_source === "sensors" ? [["observe", "beobachten"]] : [])];
        const cur = opts.some(([k]) => k === room.correction) ? room.correction : "none";
        step3 = `<div class="pills">${opts.map(([k, n]) => `<button class="seg big ${cur === k ? "on" : ""}" data-a="rtcorr" data-v="${k}">${n}</button>`).join("")}
          ${cur === "fixed" ? `<label class="rtval">± <input class="inp" type="number" step="0.5" min="-5" max="5" data-a="rtcval" value="${esc(room.correction_value || 0)}" aria-label="Korrektur in Grad"> °C</label>` : ""}</div>
          <div class="hint">${{ none: "Das Thermostat regelt nach seinem Fühler, wie er misst.",
            fixed: "Fester Wert wie der Versatz in der Fritz!Box: misst der Fühler 1,5 °C zu viel, −1,5 eintragen. Das Display am Thermostat zeigt dann den umgerechneten Wert (z. B. 22,5 statt 21).",
            observe: "Ändert nichts an der Regelung. Home Rhythm misst, um wie viel der Fühler bei geschlossenem Ventil vom Raumwert abweicht – zum Exportieren und später für „lernen“." }[cur]}</div>`;
      }
      return `<h3 class="step"><b>2</b> · Welche Sensoren messen die Raumtemperatur?</h3><div class="rtsec">${step2}</div>
        <h3 class="step"><b>3</b> · Korrektur der Temperatur</h3><div class="rtsec">${step3}</div>`;
    }

    _renderEditor() {
      const host = this.shadowRoot.getElementById("dlg");
      if (!this._editor) { host.innerHTML = ""; return; }
      const { room, error, preview } = this._editor;
      const d = this._data;
      const lvOpts = (sel) => d.plan_levels.map((l) => `<option value="${l}" ${l === sel ? "selected" : ""}>${esc(d.level_names[l])}</option>`).join("");
      const inOther = (c) => d.rooms.find((r) => r.id !== room.id && (r.climate_entities.includes(c.entity_id) || (r.ac_entities || []).includes(c.entity_id)));
      const acSet = new Set(room.ac_entities);
      const sel = new Set([...room.climate_entities, ...room.ac_entities]);
      const show = d.climates.filter((c) => sel.has(c.entity_id) || this._editor.all || (room.area_id && c.area_id === room.area_id && !c.panel && !(room.controls || []).some((x) => x.display === c.entity_id) && (c.kind === room.kind || c.can_cool)))
        .sort((a, b) => (sel.has(b.entity_id) - sel.has(a.entity_id)) || a.name.localeCompare(b.name));
      const thermoHtml = show.map((c) => {
        const other = inOther(c);
        const why = c.wrapped_by ? `wird geregelt von „${this._climateName(c.wrapped_by)}“ (${this._wrapper(c.wrapped_by) || ""})` : other ? `gehört zu ${other.name}` : "";
        const dis = !sel.has(c.entity_id) && why;
        return `<label class="th ${dis ? "dis" : ""}"><input type="checkbox" data-a="thermo" data-v="${esc(c.entity_id)}" ${sel.has(c.entity_id) ? "checked" : ""} ${dis ? "disabled" : ""}>
          <span>${esc(c.name)}${c.wrapper ? `<span class="badge">${c.wrapper}</span>` : ""}<small>${esc(why || c.entity_id)}</small></span>
          ${sel.has(c.entity_id) ? `<span class="off"><select class="inp" data-a="role" data-v="${esc(c.entity_id)}" title="Rolle"><option value="radiator">Heizkörper</option><option value="ac" ${acSet.has(c.entity_id) ? "selected" : ""}>Klimaanlage</option></select>
            <span title="Abweichung zu den Stufen-Temperaturen">± <input type="number" step="0.5" min="-5" max="5" value="${(room.offsets || {})[c.entity_id] || 0}" data-a="offset" data-v="${esc(c.entity_id)}"> °</span></span>` : ""}</label>`;
      }).join("") || `<div class="hint">Im Bereich ist kein Thermostat.</div>`;
      const areaOpts = `<option value="">– kein Bereich –</option>` + d.areas.map((a) => `<option value="${esc(a.id)}" ${a.id === room.area_id ? "selected" : ""}>${esc(a.name)}</option>`).join("");
      const dayHtml = DAY_TYPES.map(([k, name]) => `
        <div class="dt">
          <div class="hd"><b>${name}</b>
            <span>${k !== "wd" ? `<button class="btn" data-a="copy" data-v="${k}">wie Mo–Fr</button> ` : ""}<button class="btn" data-a="addblk" data-v="${k}">+ Zeit</button></span></div>
          ${room.schedule[k].length ? room.schedule[k].map((b, i) => `
            <div class="blk">
              <input type="text" inputmode="numeric" maxlength="5" placeholder="hh:mm" value="${esc(b[0])}" data-a="blk" data-k="${k}" data-i="${i}" data-f="0">
              <span>–</span>
              <input type="text" inputmode="numeric" maxlength="5" placeholder="hh:mm" value="${esc(b[1])}" data-a="blk" data-k="${k}" data-i="${i}" data-f="1">
              <select class="inp" data-a="blk" data-k="${k}" data-i="${i}" data-f="2">${lvOpts(b[2])}</select>
              <button class="x" title="Entfernen" data-a="delblk" data-k="${k}" data-i="${i}">×</button>
            </div>`).join("") : `<div class="hint">Ganzer Tag ${esc(d.level_names[room.default_level])}</div>`}
        </div>`).join("");
      host.innerHTML = `<div class="ov" data-a="ovclick"><div class="dlg" role="dialog" aria-modal="true">
        <header><h2>${room.id ? esc(room.name) : "Neuer Raum"}</h2><button class="x" data-a="close" title="Schließen">×</button></header>
        <div class="cols">
          <div>
            <div class="sec"><div class="grid2">
              <label>Name<input type="text" value="${esc(room.name)}" data-a="field" data-f="name"></label>
              <label>Bereich<select class="inp" data-a="field" data-f="area_id">${areaOpts}</select></label>
            </div>
            <h3 class="step"><b>1</b> · Welche Art von Thermostat?</h3>
            <div class="pills">${RT_KINDS.map(([k, n]) => `<button class="seg big ${room.kind === k ? "on" : ""}" data-a="rtkind" data-v="${k}">${n}</button>`).join("")}</div>
            <div class="hint">${RT_KIND_HINT[room.kind] || ""}</div>
            <div class="ths">${thermoHtml}</div>
            ${room.ac_entities.length ? this._acHtml(room) : ""}
            ${room.climate_entities.length > 1 ? `<div class="grid2" style="margin-top:8px"><label>Mehrere Thermostate<select class="inp" data-a="field" data-f="linked">
              <option value="1" ${room.linked !== false ? "selected" : ""}>gemeinsam – Hand-Änderung gilt für alle</option>
              <option value="0" ${room.linked === false ? "selected" : ""}>einzeln – jedes eigene Hand-Änderung</option></select></label></div>
              <div class="hint">Gleiche Zeiten für alle. ± verschiebt die Temperaturen einzelner Thermostate (z. B. Eingang +1 °C). Ganz andere Zeiten? Zweiten Raum im selben Bereich anlegen.</div>` : ""}
            <button class="btn" style="margin-top:6px" data-a="allthermo">${this._editor.all ? "Nur Thermostate dieser Art im Bereich zeigen" : "Alle Thermostate zeigen"}</button>
            ${this._rtEditorHtml(room)}
            ${this._ctlEditorHtml(room)}
            <h3 class="step"><b>5</b> · Weiteres</h3>
            <div class="grid2"><label>Hand-Änderung gilt<select class="inp" data-a="field" data-f="manual_mode">
                ${MANUAL_MODES.map(([v, n]) => `<option value="${v}" ${v === String(room.manual_mode) ? "selected" : ""}>${n}</option>`).join("")}</select></label></div>
            <label class="hint" style="display:flex;gap:6px;align-items:center;margin-top:8px"><input type="checkbox" data-a="field" data-f="enabled" ${room.enabled ? "checked" : ""}> Home Rhythm steuert diesen Raum</label>
            <label class="hint" style="display:flex;gap:6px;align-items:center;margin-top:4px"><input type="checkbox" data-a="field" data-f="party_room" ${room.party_room ? "checked" : ""}> Party-Raum (bei Ereignis „Party“ Komfort bis 1 Uhr)</label>
            <div class="grid2" style="margin-top:8px"><label>Luftfeuchte anzeigen von<select class="inp" data-a="field" data-f="humidity_entity">
              <option value="" ${!room.humidity_entity ? "selected" : ""}>automatisch${(() => { const o = room.id && this._room(room.id); const h = o && o.humidity && o.humidity.auto ? o.humidity : null; return h ? ` – jetzt: ${esc(h.name)} (${esc(h.source || "")})` : " (BT/VT, Thermostat, dann Raumsensor)"; })()}</option>
              <option value="none" ${room.humidity_entity === "none" ? "selected" : ""}>nicht anzeigen</option>
              ${(() => {
                const all = d.humidity_sensors || [], opt = (h) => `<option value="${esc(h.entity_id)}" ${h.entity_id === room.humidity_entity ? "selected" : ""}>${esc(h.name)}${h.value != null ? ` · ${fmtNum(h.value, 0)} %` : " · –"}</option>`;
                const here = all.filter((h) => room.area_id && h.area_id === room.area_id), rest = all.filter((h) => !here.includes(h));
                return (here.length ? `<optgroup label="In diesem Bereich">${here.map(opt).join("")}</optgroup>` : "") + `<optgroup label="${here.length ? "Andere" : "Alle Feuchtesensoren"}">${rest.map(opt).join("")}</optgroup>`;
              })()}</select></label></div>
            ${this._rulesHtml(room)}
            </div>
            ${room.climate_entities.length || room.ac_entities.length ? `<div class="sec"><h3>Stufen</h3><div class="lvls">
              ${d.plan_levels.map((l) => `<label><span><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${COLORS[l]}"></i> ${esc(d.level_names[l])}</span>
                <input type="number" min="5" max="30" step="0.5" value="${room.levels[l] ?? d.default_temps[l]}" data-a="lvl" data-v="${l}"></label>`).join("")}
            </div>
            <div class="grid2" style="margin-top:8px"><label>Außerhalb der Zeiten<select class="inp" data-a="field" data-f="default_level">${lvOpts(room.default_level)}</select></label></div></div>
            <div class="sec"><h3>Zeiten</h3>${dayHtml}</div>` : `<div class="hint" style="margin-top:12px">Ohne Thermostat: Zeiten und Stufen entfallen – hier gelten nur Rollläden, Licht und Steckdosen.</div>`}
          </div>
          <div><div class="sticky">
            ${!room.climate_entities.length && !room.ac_entities.length ? `<div class="sec"><h3>Ohne Heizung</h3><div class="hint">Dieser Raum hat kein Thermostat. Rollläden, Licht und Steckdosen stellst du links ein; ihren Wochenverlauf siehst du in der Übersicht unter „Woche“.</div></div>` : ""}
            <div class="sec" style="${!room.climate_entities.length && !room.ac_entities.length ? "display:none" : ""}"><h3>So läuft die Woche</h3>
              <div class="hint">Ergebnis aller Regeln mit den aktuellen Hausmodi. * = anderer Plan als sonst (Feiertag, Urlaub zu Hause, „wie Sonntag“).</div>
              <div class="week">${preview ? this._weekHtml(preview) : `<span></span><span class="hint">…</span>`}</div>
              <div class="legend">${d.plan_levels.concat(["urlaub", "hand", "aus"], room.ac_entities && room.ac_entities.length ? ["kuehlen", "vorkuehlen"] : []).map((l) => `<span><i style="background:${COLORS[l]}"></i>${esc(d.level_names[l])}</span>`).join("")}</div>
            </div>
            <div class="hint">Vorrang: Jahreszeit (außer Winter → aus) · Raumregel zum Urlaub · Urlaub unterwegs (${fmtTemp(d.modes.away_temp)}) · Hand-Änderung · Heute anders / Party · übrige Raumregeln · Feiertag / Urlaub zu Hause → Sonntagsplan · Wochenplan</div>
            ${error ? `<div class="err">${esc(error)}</div>` : ""}
          </div></div>
        </div>
        <footer>
          ${room.id ? `<button class="btn warn" data-a="delete">Raum entfernen</button>` : ""}
          <span class="sp"></span>
          <button class="btn" data-a="close">Abbrechen</button>
          <button class="btn pri" data-a="save">Speichern</button>
        </footer>
      </div></div>`;
    }

    _rulesHtml(room) {
      const d = this._data, rules = room.rules || [];
      const opt = (list, cur) => list.map(([k, n]) => `<option value="${esc(k)}" ${k === cur ? "selected" : ""}>${esc(n)}</option>`).join("");
      return `<div class="sec" style="margin-top:12px"><h3>Raumregeln <small class="sub2">bei bestimmten Hausmodi anders – erste zutreffende gilt; Urlaub, Hand-Änderung und „Heute anders“ gehen vor (außer Regeln zum Urlaub)</small></h3>
        ${rules.map((r, i) => {
          const vals = d.rule_values[r.if.mode] || [];
          const valList = vals.includes(r.if.value) ? vals : [r.if.value, ...vals];
          return `<div class="rule">
            <span>Wenn</span>
            <select class="inp" data-a="rule" data-i="${i}" data-f="mode">${opt(Object.entries(d.rule_modes), r.if.mode)}</select>
            <select class="inp" data-a="rule" data-i="${i}" data-f="op">${opt([["is", "ist"], ["not", "ist nicht"]], r.if.op)}</select>
            <select class="inp" data-a="rule" data-i="${i}" data-f="value">${opt(valList.map((v) => [v, v]), r.if.value)}</select>
            <span>dann</span>
            <select class="inp" data-a="rule" data-i="${i}" data-f="then">${opt(Object.entries(d.rule_actions), r.then)}</select>
            <button class="x" data-a="delrule" data-i="${i}" title="Entfernen">×</button></div>`;
        }).join("") || `<div class="hint">Keine. Beispiel: Gästezimmer – „Wenn Ereignis ist nicht Gäste, dann Absenkung“.</div>`}
        <button class="btn" data-a="addrule">+ Regel</button></div>`;
    }

    _acHtml(room) {
      const e = this._data.energy, ac = room.ac;
      let thr = null, err = "";
      try {
        if (ac.cop.length < 2) throw new Error("Mindestens zwei COP-Werte eintragen");
        thr = acThreshold(ac.cop.map((p) => [Number(p[0]), Number(p[1])]), e.break_even_cop);
      } catch (x) { err = x.message; }
      const verdict = err ? err
        : thr == null ? "Mit deinen Preisen ist Gas bei jeder Außentemperatur billiger."
        : `Mit deinen Preisen heizt die Klimaanlage ab <b>${fmtNum(thr)} °C</b> draußen billiger als Gas${e.outdoor != null ? ` – jetzt ${fmtNum(e.outdoor)} °C: <b>${e.outdoor >= thr ? "Klima" : "Gas"}</b>` : ""}.`;
      return `<div class="acbox">
        <h3>Klimaanlage heizt mit</h3>
        <div class="grid2">
          <label>Wärmequelle<select class="inp" data-a="ac" data-f="mode">${AC_MODES.map(([v, n]) => `<option value="${v}" ${v === ac.mode ? "selected" : ""}>${n}</option>`).join("")}</select></label>
          <label>Heizkörper als Reserve<span class="inl"><input type="number" step="0.5" min="0" max="10" value="${ac.reserve}" data-a="ac" data-f="reserve"> K unter Soll</span></label>
          <label>Einsatzgrenze Klima<span class="inl"><input type="number" step="1" min="-30" max="10" value="${ac.min_outdoor ?? ""}" placeholder="keine" data-a="ac" data-f="min_outdoor"> °C außen</span></label>
          <label>Heizkörper helfen, wenn zu kalt nach<span class="inl"><input type="number" step="5" min="5" max="240" value="${ac.boost_after}" data-a="ac" data-f="boost_after"> min</span></label>
        </div>
        <label class="hint" style="display:flex;gap:6px;align-items:center;margin:8px 0"><input type="checkbox" data-a="ac" data-f="night_off" ${ac.night_off ? "checked" : ""}> Bei Stufe „Nacht“ kein Klima (Geräusch, Luftzug)</label>
        <div class="hint">COP aus dem Datenblatt: Heizleistung ÷ Leistungsaufnahme bei der jeweiligen Außentemperatur (meist für +7 °C und −7 °C, manchmal +2 °C und −15 °C angegeben). Bei mehreren Innengeräten an einer Multisplit-Außeneinheit die Werte der Kombination nehmen.</div>
        <div class="cops">
          <span class="h">Außen °C</span><span class="h">COP</span><span></span>
          ${ac.cop.map((p, i) => `<input type="number" step="1" min="-30" max="30" value="${p[0]}" data-a="cop" data-i="${i}" data-f="0">
            <input type="number" step="0.05" min="0.5" max="10" value="${p[1]}" data-a="cop" data-i="${i}" data-f="1">
            <button class="x" data-a="delcop" data-i="${i}" title="Entfernen">×</button>`).join("")}
        </div>
        <button class="btn" data-a="addcop">+ COP-Wert</button>
        <div class="verdict">${verdict}</div>
        ${this._coolHtml(room)}
        <div class="hint">Wärme aus Gas: ${fmtNum(e.gas_ct, 2)} ct ÷ ${fmtNum(e.boiler_efficiency * 100, 0)} % = ${fmtNum(e.heat_cost_gas)} ct/kWh · Strom ${fmtNum(e.power_ct, 2)} ct/kWh → Klima lohnt ab COP ${fmtNum(e.break_even_cop, 2)}. Preise und Außensensoren: Einstellungen → Home Rhythm → Konfigurieren → Energie.</div>
      </div>`;
    }

    _editorPreview() {
      clearTimeout(this._pvTimer);
      this._pvTimer = setTimeout(async () => {
        if (!this._editor) return;
        const room = this._editor.room;
        try {
          const r = await this._ws({ type: "home_rhythm/preview", room: { schedule: room.schedule, levels: room.levels, default_level: room.default_level, manual_mode: room.manual_mode, ac_entities: room.ac_entities || [], ac: room.ac, rules: room.rules || [], party_room: !!room.party_room }, room_id: room.id });
          if (!this._editor) return;
          this._editor.preview = r.days;
          this._editor.error = null;
        } catch (e) { if (this._editor) this._editor.error = e.message || String(e); }
        this._renderPreviewOnly();
      }, 250);
    }

    _coolHtml(room) {
      const c = room.ac.cooling || (room.ac.cooling = { enabled: true, temp: 25, other: null, precool: null });
      const seasons = this._data.modes.cooling_season ? "jetzt aktiv" : "in den eingestellten Kühl-Jahreszeiten (Standard: Heißphase)";
      return `<h3 style="margin-top:14px">Kühlen</h3>
        <label class="hint" style="display:flex;gap:6px;align-items:center;margin:4px 0 8px"><input type="checkbox" data-a="cool" data-f="enabled" ${c.enabled ? "checked" : ""}> Klimaanlage kühlt ${seasons}</label>
        ${c.enabled ? `<div class="grid2">
          <label>Bei genutzten Stufen (${esc(this._data.plan_levels.filter((l) => this._data.level_defs[l] && this._data.level_defs[l].use).map((l) => this._data.level_names[l]).join(", "))})<span class="inl">kühlen auf <input type="number" step="0.5" min="16" max="30" value="${c.temp}" data-a="cool" data-f="temp"> °C</span></label>
          <label>Sonst<span class="inl"><input type="number" step="0.5" min="16" max="32" value="${c.other ?? ""}" placeholder="aus" data-a="cool" data-f="other"> °C (leer = aus)</span></label>
        </div>
        <label class="hint" style="display:flex;gap:6px;align-items:center;margin:10px 0 4px"><input type="checkbox" data-a="cool" data-f="precool_on" ${c.precool ? "checked" : ""}> Vorkühlen (z. B. mittags mit Solarstrom, bevor der Raum aufheizt)</label>
        ${c.precool ? `<div class="blk" style="grid-template-columns:72px auto 72px auto 80px auto">
          <input type="text" inputmode="numeric" maxlength="5" value="${esc(c.precool[0])}" data-a="cool" data-f="pre0"><span>–</span>
          <input type="text" inputmode="numeric" maxlength="5" value="${esc(c.precool[1])}" data-a="cool" data-f="pre1"><span>auf</span>
          <input type="number" step="0.5" min="16" max="30" value="${c.precool[2]}" data-a="cool" data-f="pre2"><span>°C</span></div>` : ""}
        <div class="hint">Kühlt nicht bei Urlaub unterwegs und wenn niemand zu Hause ist (Anwesenheit in den Einstellungen). Heizkörper sind in der Zeit aus.</div>` : ""}`;
    }

    _refreshAc() {
      const box = this.shadowRoot.querySelector("#dlg .acbox .verdict");
      if (!box) return;
      const tmp = document.createElement("div");
      tmp.innerHTML = this._acHtml(this._editor.room);
      box.innerHTML = tmp.querySelector(".verdict").innerHTML;
    }

    _renderPreviewOnly() {
      const host = this.shadowRoot.getElementById("dlg");
      const wk = host.querySelector(".sticky .week");
      if (wk && this._editor.preview) wk.innerHTML = this._weekHtml(this._editor.preview);
      const sticky = host.querySelector(".sticky");
      let err = sticky && sticky.querySelector(".err");
      if (this._editor.error) {
        if (!err && sticky) { err = document.createElement("div"); err.className = "err"; sticky.appendChild(err); }
        if (err) err.textContent = this._editor.error;
      } else if (err) err.remove();
    }

    async _saveEditor() {
      const room = clone(this._editor.room);
      room.levels = Object.fromEntries(Object.entries(room.levels).map(([k, v]) => [k, Number(v)]));
      if (!room.id) delete room.id;
      try {
        const r = await this._ws({ type: "home_rhythm/room/save", room });
        this._open.add(r.id);
        this._tab = "heat";
        this._closeEditor();
      } catch (e) {
        this._editor.error = e.message || String(e);
        this._renderEditor();
      }
    }

    // ------------------------------------------------------------ Ereignisse
    async _onClick(e) {
      const t = e.target.closest("[data-a]");
      if (!t) { if (this._pick && !e.target.closest(".epick")) this._closePick(); return; }
      const a = t.dataset.a, v = t.dataset.v;
      if (await this._qClick(a, v, t, e)) return;
      if (await this._tdClick(a, v, t, e)) return;
      if (await this._flowClick(a, v, t, e)) return;
      if (a === "ovclick") { if (e.target === t) this._closeEditor(); return; }
      if (a === "knav") { this._knopfNav(); return; }
      if (a.startsWith("rc") && await this._rcClick(a, v, t)) return;
      if (["mode", "field", "lvl", "blk", "search", "thermo", "offset", "role", "ac", "cop", "cool", "event", "rule", "lvldef", "rtsrc", "rtsens", "rtbox", "rtcval", "ctladd", "ctlmap"].includes(a)) return;
      if (a === "tab") { this._tab = v; this._render(); }
      else if (a === "filter") { this._filter = v; this._render(); }
      else if (a === "toggle") {
        if (this._open.has(v)) this._open.delete(v); else { this._open.add(v); this._loadPreview(v); }
        this._render();
      } else if (a === "clear") { await this._ws({ type: "home_rhythm/manual/clear", room_id: v }); this._fetch(); }
      else if (a === "modes") { this._modesOpen = !this._modesOpen; this._render(); }
      else if (a === "devfilter") { this._devFilter = v; this._render(); }
      else if (a === "levelsopen") { this._levelsOpen = !this._levelsOpen; this._render(); }
      else if (a === "lvlcancel") { this._levelDraft = null; this._levelErr = null; this._levelsDirtyShown = false; this._render(); }
      else if (a === "lvlsave") {
        try { await this._ws({ type: "home_rhythm/levels/save", levels: this._levelDraft }); this._levelDraft = null; this._levelErr = null; this._levelsDirtyShown = false; await this._fetch(); }
        catch (e) { this._levelErr = e.message || String(e); this._render(); }
      }
      else if (a === "seasonauto") { await this._ws({ type: "home_rhythm/season_auto/set", enabled: v === "1" }); this._fetch(); }
      else if (["reqgo", "reqopen", "reqset", "reqnone", "reqnew", "reqwd", "reqpick"].includes(a)) await this._reqClick(a, v, t);
      else if (a === "floor") { this._closedFloors.has(v) ? this._closedFloors.delete(v) : this._closedFloors.add(v); this._render(); }
      else if (a === "addrule") { (this._editor.room.rules = this._editor.room.rules || []).push({ if: { mode: "event", op: "is", value: "Gäste" }, then: "komfort" }); this._renderEditor(); this._editorPreview(); }
      else if (a === "delrule") { this._editor.room.rules.splice(Number(t.dataset.i), 1); this._renderEditor(); this._editorPreview(); }
      else if (a === "dismiss") { await this._ws({ type: "home_rhythm/hint/dismiss", hint_id: v }); this._fetch(); }
      else if (a === "resethints") { await this._ws({ type: "home_rhythm/hint/reset", room_id: v }); this._fetch(); }
      else if (a === "nav") { history.pushState(null, "", v); window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } })); }
      else if (a === "ctl") this._qOpenRoom(v);  // 0.9.12: eigenes Fenster (Gerät ⤴ darin öffnet das HA-Fenster)
      else if (a === "histh") { this._histHours = Number(v); this._render(); }
      else if (a === "more") {
        this._ctlMenu = null;
        // Unser Fenster ist modal (Top Layer); das HA-Fenster läge sonst dahinter und wäre gesperrt → Bedien-Fenster schließen.
        if (this._q) { this._q = null; this._renderQ(); }
        this._moreInfo(v);
      }
      else if (a === "edit") this._openEditor(v);
      else if (a === "add") this._openEditor(null, v || null);
      else if (a === "add-entity") this._openEditor(null, null, v);
      else if (a === "close") this._closeEditor();
      else if (a === "addcop") {
        const pts = this._editor.room.ac.cop;
        pts.push([pts.length ? Math.min(pts[pts.length - 1][0] + 5, 30) : 7, pts.length ? pts[pts.length - 1][1] : 3.5]);
        this._renderEditor();
      } else if (a === "delcop") { this._editor.room.ac.cop.splice(Number(t.dataset.i), 1); this._renderEditor(); }
      else if (a === "allthermo") { this._editor.all = !this._editor.all; this._renderEditor(); }
      else if (a === "rtexport") { this._rtExport(v); }
      else if (a === "ctldel") { this._editor.room.controls.splice(Number(t.dataset.i), 1); this._editor.learn = null; this._renderEditor(); }
      else if (a === "ctlstep") { this._editor.room.controls[Number(t.dataset.i)].step = Number(v); this._renderEditor(); }
      else if (a === "ctlunmap") { delete this._editor.room.controls[Number(t.dataset.i)].map[t.dataset.k]; this._renderEditor(); }
      else if (a === "ctllearn") { const L = this._editor.learn, i = Number(t.dataset.i); if (L && L.i === i && L.act === v) { this._editor.learn = null; this._ws({ type: "home_rhythm/control/learn", device_id: this._editor.room.controls[i].device_id, step: "cancel" }).catch(() => {}); this._renderEditor(); } else this._ctlLearn(i, v); }
      else if (a === "ctlall") { this._editor.ctlAll = !this._editor.ctlAll; this._renderEditor(); }
      else if (a === "rtkind") { this._editor.room.kind = v; this._renderEditor(); }
      else if (a === "rtcorr") { this._editor.room.correction = v; this._renderEditor(); }
      else if (a === "rtmore") { this._editor.rtMore = !this._editor.rtMore; this._renderEditor(); }
      else if (a === "save") this._saveEditor();
      else if (a === "delete") {
        if (!confirm(`Raum „${this._editor.room.name}“ aus Home Rhythm entfernen? Das Thermostat bleibt auf dem letzten Wert.`)) return;
        await this._ws({ type: "home_rhythm/room/delete", room_id: this._editor.room.id });
        this._open.delete(this._editor.room.id);
        this._closeEditor();
      } else if (a === "addblk") {
        const list = this._editor.room.schedule[v];
        const last = list[list.length - 1];
        const start = last ? last[1] : "07:00";
        const [h, m] = start.split(":").map(Number);
        const end = h + 2 >= 24 ? "24:00" : `${String(h + 2).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
        list.push([start, end > start ? end : "24:00", "komfort"]);
        this._renderEditor(); this._editorPreview();
      } else if (a === "delblk") {
        this._editor.room.schedule[t.dataset.k].splice(Number(t.dataset.i), 1);
        this._renderEditor(); this._editorPreview();
      } else if (a === "copy") {
        this._editor.room.schedule[v] = clone(this._editor.room.schedule.wd);
        this._renderEditor(); this._editorPreview();
      }
    }

    _onChange(e) {
      const t = e.target, a = t.dataset && t.dataset.a;
      if (!a) return;
      if (this._flowChange(a, t)) return;
      if (a === "lvldef") {
        const defs = this._levelDraft || (this._levelDraft = clone(this._data.level_defs)), def = defs[t.dataset.k], f = t.dataset.f;
        def[f] = t.type === "checkbox" ? t.checked : f === "temp" ? Number(t.value) : t.value;
        if (f === "enabled" || !this._levelsDirtyShown) { this._levelsDirtyShown = true; this._render(); }
        return;
      }
      if (a === "event") { this._ws({ type: "home_rhythm/event/set", event: t.value }).then(() => this._fetch()); return; }
      if (a === "tdin") { if (this._td) { this._td[t.dataset.f] = t.value; this._td.error = null; this._renderToday(); } return; }
      if (a === "starttab") { this._ws({ type: "home_rhythm/start_tab/set", tab: t.value }).then(() => this._fetch()); return; }
      if (a === "reqsel") { if (t.value) { this._reqPick = null; this._reqCall({ type: "home_rhythm/requirement/set", key: t.dataset.v, entity: t.value }); } return; }
      if (a === "reqauto") { this._reqCall({ type: "home_rhythm/season_auto/set", enabled: t.checked }); return; }
      if (a === "mode") {
        this._hass.callService(t.dataset.entity.split(".")[0], "select_option", { entity_id: t.dataset.entity, option: t.value });
        return;
      }
      if (!this._editor) return;
      const room = this._editor.room;
      if (a === "rtsrc") { room.temp_source = t.value; this._renderEditor(); return; }
      if (a === "ctladd") { if (t.value) { const x = (this._data.control_candidates || []).find((y) => y.device_id === t.value) || {}; room.controls.push({ device_id: t.value, display: x.display || null, map: {}, step: 0.5 }); } this._renderEditor(); return; }
      if (a === "ctldisp") { room.controls[Number(t.dataset.i)].display = t.checked ? t.dataset.v : null; this._renderEditor(); return; }
      if (a === "rtsens") { room.temp_sensors = room.temp_sensors.filter((e) => e !== t.dataset.v); if (t.checked) room.temp_sensors.push(t.dataset.v); this._renderEditor(); return; }
      if (a === "rtbox") { room.box_sensor = t.value; return; }
      if (a === "rtcval") { room.correction_value = Number(t.value) || 0; return; }
      if (a === "field") {
        const f = t.dataset.f;
        room[f] = f === "linked" ? t.value === "1" : t.type === "checkbox" ? t.checked : t.value || (f === "area_id" ? null : t.value);
        if (f === "area_id" || f === "default_level") this._renderEditor();
      } else if (a === "thermo") {
        const id = t.dataset.v;
        const c = this._data.climates.find((x) => x.entity_id === id);
        room.climate_entities = room.climate_entities.filter((e) => e !== id);
        room.ac_entities = room.ac_entities.filter((e) => e !== id);
        if (t.checked) (c && c.can_cool ? room.ac_entities : room.climate_entities).push(id);
        this._renderEditor();
        return;
      } else if (a === "role") {
        const id = t.dataset.v;
        room.climate_entities = room.climate_entities.filter((e) => e !== id);
        room.ac_entities = room.ac_entities.filter((e) => e !== id);
        (t.value === "ac" ? room.ac_entities : room.climate_entities).push(id);
        this._renderEditor();
        return;
      } else if (a === "ac") {
        const f = t.dataset.f;
        room.ac[f] = f === "night_off" ? t.checked : f === "mode" ? t.value : t.value === "" ? null : Number(t.value);
        if (f === "mode") this._renderEditor();
        return;
      } else if (a === "rule") {
        const rule = room.rules[Number(t.dataset.i)], f = t.dataset.f;
        if (f === "then") rule.then = t.value;
        else rule.if[f] = t.value;
        if (f === "mode") { rule.if.value = (this._data.rule_values[t.value] || [""])[0]; this._renderEditor(); }
        this._editorPreview();
        return;
      } else if (a === "cool") {
        const c = room.ac.cooling, f = t.dataset.f;
        if (f === "enabled") { c.enabled = t.checked; this._renderEditor(); }
        else if (f === "precool_on") { c.precool = t.checked ? ["11:00", "14:00", Math.max(16, (c.temp || 25) - 1)] : null; this._renderEditor(); }
        else if (f === "pre0" || f === "pre1") {
          const v = normTime(t.value);
          if (!v) { this._editor.error = `„${t.value}“ ist keine Uhrzeit`; this._renderPreviewOnly(); return; }
          t.value = v; c.precool[f === "pre0" ? 0 : 1] = v;
        } else if (f === "pre2") c.precool[2] = Number(t.value);
        else if (f === "other") c.other = t.value === "" ? null : Number(t.value);
        else if (t.value !== "") c[f] = Number(t.value);
        this._editorPreview();
        return;
      } else if (a === "cop") {
        room.ac.cop[Number(t.dataset.i)][Number(t.dataset.f)] = Number(t.value);
        this._refreshAc();
        return;
      } else if (a === "offset") {
        room.offsets = { ...(room.offsets || {}), [t.dataset.v]: Number(t.value) || 0 };
        return;
      } else if (a === "lvl") {
        if (t.value === "" || Number.isNaN(Number(t.value))) delete room.levels[t.dataset.v];
        else room.levels[t.dataset.v] = Number(t.value);
      }
      else if (a === "blk") {
        let val = t.value;
        if (t.dataset.f !== "2") {
          val = normTime(val);
          if (!val) { this._editor.error = `„${t.value}“ ist keine Uhrzeit (z. B. 6:30 oder 0630)`; this._renderPreviewOnly(); return; }
          t.value = val;
        }
        room.schedule[t.dataset.k][Number(t.dataset.i)][Number(t.dataset.f)] = val;
        if (t.dataset.f === "0") { room.schedule[t.dataset.k].sort((x, y) => x[0].localeCompare(y[0])); this._renderEditor(); }
      }
      this._editorPreview();
    }

    _onInput(e) {
      const t = e.target, a = t.dataset && t.dataset.a;
      if (a === "pkq") { this._openPick(t.dataset.t, t.value); return; }
      if (a === "tlrange") { this._tlMin = Number(t.value) * 15; this._ovLive(); return; }
      if (a === "devq") {
        this._devQ = t.value;
        const pos = t.selectionStart;
        this._render();
        const inp = this.shadowRoot.querySelector('input[data-a="devq"]');
        if (inp) { inp.focus(); inp.setSelectionRange(pos, pos); }
        return;
      }
      if (a === "search") {
        this._search = t.value;
        const pos = t.selectionStart;
        this._render();
        const inp = this.shadowRoot.querySelector('input[data-a="search"]');
        if (inp) { inp.focus(); inp.setSelectionRange(pos, pos); }
      } else if (a === "field" && t.dataset.f === "name" && this._editor) this._editor.room.name = t.value;
    }
  }

  /** Visueller Editor der Karte (0.9.8): ganze Ansicht oder ein Raum mit Größe und Schnellwahl. */
  class HomeRhythmCardEditor extends HTMLElement {
    constructor() { super(); this.attachShadow({ mode: "open" }); this._config = {}; this._data = null; }
    setConfig(config) { this._config = { ...(config || {}) }; this._render(); }
    set hass(hass) {
      const first = !this._hass; this._hass = hass;
      if (first) {
        const st = hrStore(hass);  // gemeinsamer Speicher – meist schon geladen
        st.ensure(60000).then(() => { if (st.error) throw st.error; this._data = st.data; this._render(); }).catch((e) => { this._err = (e && e.message) || String(e); this._render(); });
      }
    }
    _set(patch) {
      const c = { ...this._config, ...patch };
      for (const k of Object.keys(c)) if (c[k] === undefined || c[k] === "" || c[k] === null) delete c[k];
      if (!c.room && !c.area) { delete c.layout; delete c.quick; delete c.step; }
      if (c.layout !== "knopf") { delete c.navigation_path; delete c.icon; delete c.name; }
      this._config = c;
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: c }, bubbles: true, composed: true }));
      this._render();
    }
    _render() {
      const c = this._config, d = this._data;
      if (!d) { this.shadowRoot.innerHTML = `<div style="padding:8px">${this._err ? esc(this._err) : "Lade Räume …"}</div>`; return; }
      const quick = Array.isArray(c.quick) ? c.quick : ["komfort", "boost", "today", "off"];
      const qAll = [...d.plan_levels.map((l) => [l, `${d.level_names[l] || l} … (bis wann?)`]), ["boost", "Booster 1 Std."], ["today", "Heute … (Ausnahme-Fenster)"], ["off", "Aus … (bis wann?)"]];
      const layout = c.layout || "standard";
      const by = this._by || (c.area && !c.room ? "area" : "room");
      const one = !!(c.room || c.area);
      const areaRoom = c.area ? d.rooms.find((r) => r.area_id === c.area) : null;
      const roomAreas = new Set(d.rooms.map((r) => r.area_id).filter(Boolean));
      const areas = [...(d.areas || [])].sort((a, b) => a.name.localeCompare(b.name, "de"));
      const seg = (key, val, label, cur) => `<button class="seg ${cur === val ? "on" : ""}" data-k="${key}" data-v="${val}">${label}</button>`;
      this.shadowRoot.innerHTML = `<style>
          :host { display:block; font-family:var(--paper-font-body1_-_font-family, inherit); }
          .f { display:flex; flex-direction:column; gap:6px; margin-bottom:16px; }
          label.t { font-weight:500; }
          select, input[type=text] { font:inherit; padding:8px; border-radius:6px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); }
          .segs { display:flex; gap:6px; flex-wrap:wrap; }
          .seg { font:inherit; padding:6px 12px; border-radius:16px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); cursor:pointer; }
          .seg.on { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
          .q { display:flex; align-items:center; gap:8px; }
          .q button { font:inherit; border:none; background:none; cursor:pointer; color:var(--secondary-text-color); padding:0 4px; }
          small { color:var(--secondary-text-color); }
        </style>
        <div class="f"><label class="t">Raum wählen über</label><div class="segs"><button class="seg ${by === "room" ? "on" : ""}" data-by="room">Raum</button><button class="seg ${by === "area" ? "on" : ""}" data-by="area">Bereich</button></div></div>
        ${by === "room" ? `<div class="f"><label class="t">Raum</label>
          <select data-k="room"><option value="">– ganze Home-Rhythm-Ansicht –</option>${d.rooms.map((r) => `<option value="${esc(r.id)}" ${c.room === r.id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select>
          <small>Mit Raum: kleine Karte für ein Dashboard. Bedienen dürfen alle Benutzer, Einstellungen nur Administratoren.</small></div>` : `<div class="f"><label class="t">Bereich</label>
          <select data-k="area"><option value="">– ganze Home-Rhythm-Ansicht –</option>${areas.map((a) => `<option value="${esc(a.id)}" ${c.area === a.id ? "selected" : ""}>${esc(a.name)}${roomAreas.has(a.id) ? "" : " (kein Home-Rhythm-Raum)"}</option>`).join("")}</select>
          <small>${c.area ? (areaRoom ? `Zeigt den Home-Rhythm-Raum „${esc(areaRoom.name)}“.` : "Zu diesem Bereich gibt es keinen Home-Rhythm-Raum – die Karte zeigt nur eine kleine Zeile.") : "Die Karte sucht den Home-Rhythm-Raum mit diesem Bereich (bei mehreren den ersten)."}</small></div>`}
        <div class="f"><label class="t">${c.layout === "knopf" ? "Name" : "Titel"} <small>(optional)</small></label><input type="text" data-k="${c.layout === "knopf" ? "name" : "title"}" value="${esc((c.layout === "knopf" ? c.name || c.title : c.title) || "")}" placeholder="${one ? "Name des Raums" : "Home Rhythm"}"></div>
        ${one ? `
        <div class="f"><label class="t">Größe</label><div class="segs">${seg("layout", "knopf", "Knopf (Kachel)", layout)}${seg("layout", "compact", "Kompakt (eine Zeile)", layout)}${seg("layout", "standard", "Standard", layout)}${seg("layout", "tablet", "Groß (Tablet)", layout)}</div></div>
        ${layout === "knopf" ? `
        <div class="f"><label class="t">Symbol <small>(optional, mdi-Symbol statt Emoji)</small></label><input type="text" data-k="icon" value="${esc(c.icon || "")}" placeholder="z. B. mdi:sofa"></div>
        <div class="f"><label class="t">Antippen öffnet <small>(optional)</small></label><input type="text" data-k="navigation_path" value="${esc(c.navigation_path || "")}" placeholder="z. B. /dashboard-haus/kueche">
          <small>Mit Pfad: Fläche antippen wechselt dorthin, das Symbol öffnet das Bedien-Fenster. Ohne Pfad öffnet beides das Bedien-Fenster.</small></div>` : `
        <div class="f"><label class="t">+ / − Schritt</label><div class="segs">${seg("step", "0.5", "0,5 °C", String(c.step || 0.5))}${seg("step", "1", "1 °C", String(c.step || 0.5))}</div></div>
        <div class="f"><label class="t">Schnellwahl <small>(Reihenfolge mit ▲▼; bei „Kompakt“ nach Antippen des Namens)</small></label>
          ${quick.filter((k) => qAll.some(([x]) => x === k)).map((k, i, arr) => `<div class="q"><input type="checkbox" checked data-q="${k}"> ${esc(qAll.find(([x]) => x === k)[1])}
            <button data-up="${i}" ${i ? "" : "disabled"} title="nach oben">▲</button><button data-down="${i}" ${i < arr.length - 1 ? "" : "disabled"} title="nach unten">▼</button></div>`).join("")}
          ${qAll.filter(([k]) => !quick.includes(k)).map(([k, n]) => `<div class="q"><input type="checkbox" data-q="${k}"> ${esc(n)}</div>`).join("")}</div>`}` : `
        <div class="f"><label class="t">Start-Reiter</label><select data-k="view"><option value="">wie in der Einrichtung</option>${[["overview", "Übersicht"], ["heat", "Heizung & Klima"], ["flows", "Abläufe"], ["devices", "Geräte"]].map(([v, n]) => `<option value="${v}" ${c.view === v ? "selected" : ""}>${n}</option>`).join("")}</select></div>`}`;
      const root = this.shadowRoot;
      root.querySelectorAll("select[data-k]").forEach((el) => el.addEventListener("change", () => this._set({ [el.dataset.k]: el.value })));
      root.querySelectorAll("button[data-by]").forEach((el) => el.addEventListener("click", () => {
        const to = el.dataset.by; if (to === by) return;
        this._by = to;
        // Raum ↔ Bereich umrechnen, damit die Karte nicht leer wird
        if (to === "area") { const r = d.rooms.find((x) => x.id === c.room); this._set({ room: undefined, area: r && r.area_id ? r.area_id : undefined }); }
        else { const r = c.area ? d.rooms.find((x) => x.area_id === c.area) : null; this._set({ area: undefined, room: r ? r.id : undefined }); }
      }));
      root.querySelectorAll("input[type=text][data-k]").forEach((el) => el.addEventListener("change", () => this._set({ [el.dataset.k]: el.value })));
      root.querySelectorAll("button.seg").forEach((el) => el.addEventListener("click", () => this._set({ [el.dataset.k]: el.dataset.k === "step" ? (el.dataset.v === "1" ? 1 : undefined) : (el.dataset.v === "standard" ? undefined : el.dataset.v) })));
      const cur = quick.filter((k) => qAll.some(([x]) => x === k));
      root.querySelectorAll("input[data-q]").forEach((el) => el.addEventListener("change", () => {
        const k = el.dataset.q, next = el.checked ? [...cur, k] : cur.filter((x) => x !== k);
        this._set({ quick: next });
      }));
      const move = (i, j) => { const n = [...cur]; [n[i], n[j]] = [n[j], n[i]]; this._set({ quick: n }); };
      root.querySelectorAll("button[data-up]").forEach((el) => el.addEventListener("click", () => move(Number(el.dataset.up), Number(el.dataset.up) - 1)));
      root.querySelectorAll("button[data-down]").forEach((el) => el.addEventListener("click", () => move(Number(el.dataset.down), Number(el.dataset.down) + 1)));
    }
  }

  if (!customElements.get("home-rhythm-card")) {
    customElements.define("home-rhythm-card", HomeRhythmCard);
    if (!customElements.get("home-rhythm-card-editor")) customElements.define("home-rhythm-card-editor", HomeRhythmCardEditor);
    window.customCards = window.customCards || [];
    window.customCards.push({ type: "home-rhythm-card", name: "Home Rhythm", description: "Hausmodi, Wochenpläne und Begründung je Raum – oder ein einzelner Raum zum Bedienen", preview: false });
    console.info(`%c HOME-RHYTHM %c ${VERSION} `, "background:#e8833a;color:#fff", "");
  }
})();
