"""Konstanten für Home Rhythm."""

DOMAIN = "home_rhythm"
VERSION = "0.9.14"

CONF_SEASON_ENTITY = "season_entity"
CONF_WINTER_VALUES = "winter_values"
CONF_VACATION_ENTITY = "vacation_entity"
CONF_AWAY_VALUE = "away_value"
CONF_HOME_VALUE = "home_value"
CONF_WORKDAY_ENTITY = "workday_entity"
CONF_AWAY_TEMP = "away_temp"
CONF_COOL_VALUES = "cool_values"  # Jahreszeiten, in denen gekühlt wird
CONF_PRESENCE_ENTITY = "presence_entity"  # z. B. zone.home: 0 = niemand zu Hause
CONF_SUMMER_VALUE = "summer_value"  # Wert der Jahreszeit-Auswahl für "Sommer"
CONF_WINTER_BELOW = "winter_below"  # Ø 3 Tage darunter → Winter
CONF_HOT_ABOVE = "hot_above"  # Ø 3 Tage darüber → Heißphase
# Energie: Klimaanlage oder Gas?
CONF_OUTDOOR_ENTITIES = "outdoor_entities"
CONF_OUTDOOR_AGG = "outdoor_aggregate"  # "mean" oder "min"
CONF_OUTDOOR_MINUTES = "outdoor_minutes"
CONF_GAS_PRICE = "gas_price"  # ct/kWh
CONF_GAS_PRICE_ENTITY = "gas_price_entity"
CONF_BOILER_EFF = "boiler_efficiency"  # %
CONF_POWER_PRICE = "power_price"  # ct/kWh
CONF_POWER_PRICE_ENTITY = "power_price_entity"
CONF_HYSTERESIS = "hysteresis"  # K
# Heizung: welcher Wochenplan gilt an Feiertagen bzw. bei „Urlaub zu Hause“? "wd" = Mo–Fr, "sa", "so"
CONF_HOLIDAY_AS = "holiday_as"
CONF_VACATION_AS = "vacation_as"

DEFAULTS = {
    CONF_SEASON_ENTITY: "",
    CONF_WINTER_VALUES: "Winter",
    CONF_VACATION_ENTITY: "",
    CONF_AWAY_VALUE: "Urlaub unterwegs",
    CONF_HOME_VALUE: "Urlaub zu Hause",
    CONF_WORKDAY_ENTITY: "",
    CONF_AWAY_TEMP: 16.0,
    CONF_COOL_VALUES: "Heißphase",
    CONF_PRESENCE_ENTITY: "zone.home",
    CONF_SUMMER_VALUE: "Sommer",
    CONF_WINTER_BELOW: 15.0,
    CONF_HOT_ABOVE: 26.0,
    CONF_OUTDOOR_ENTITIES: [],
    CONF_OUTDOOR_AGG: "mean",
    CONF_OUTDOOR_MINUTES: 60,
    CONF_GAS_PRICE: 12.0,
    CONF_GAS_PRICE_ENTITY: "",
    CONF_BOILER_EFF: 90,
    CONF_POWER_PRICE: 35.0,
    CONF_POWER_PRICE_ENTITY: "",
    CONF_HYSTERESIS: 1.0,
    CONF_HOLIDAY_AS: "so",
    CONF_VACATION_AS: "so",
}

STORAGE_KEY = f"{DOMAIN}.data"
STORAGE_VERSION = 1

EVENT_UPDATED = f"{DOMAIN}_updated"
SIGNAL_UPDATED = f"{DOMAIN}_updated_signal"
SIGNAL_FLOWS = f"{DOMAIN}_flows_changed"  # Abläufe gespeichert/gelöscht → HA-Schalter der Zeitpläne abgleichen

CARD_URL = f"/{DOMAIN}/home-rhythm-card.js"

# Nach eigenem Befehl so lange keine Hand-Änderung erkennen (träge Geräte wie Fritz!DECT).
GRACE_SECONDS = 180
# Weicht ein Gerät trotz Befehl ab, nach dieser Zeit erneut senden.
RESYNC_SECONDS = 600
# Meldet ein Gerät nach einem eigenen Befehl noch den ALTEN Wert, gilt das so lange als Echo (Fritz!DECT
# übernimmt Befehle teils erst beim nächsten Aufwachen, bis ca. 15 min).
SLOW_ECHO_SECONDS = 900
TICK_SECONDS = 60

# Reiter, mit denen die Karte öffnen kann
START_TABS = ("overview", "heat", "flows", "devices", "setup")
# Ausnahme („Heute“) höchstens so weit im Voraus
MAX_EXCEPTION_DAYS = 14
