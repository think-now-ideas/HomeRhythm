"""Version steht in manifest.json (maßgeblich), const.py und der Karte gleich; CHANGELOG hat den Abschnitt."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
D = ROOT / "custom_components" / "home_rhythm"


def test_version_consistent():
    v = json.loads((D / "manifest.json").read_text(encoding="utf-8"))["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.\d+)?", v)
    assert re.search(rf'^VERSION = "{re.escape(v)}"', (D / "const.py").read_text(encoding="utf-8"), re.M)
    assert f'const VERSION = "{v}"' in (D / "www" / "home-rhythm-card.js").read_text(encoding="utf-8")
    assert re.search(rf"^## {re.escape(v)}( |$)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
