"""Knipt de drie plattegronden (origineel, optie 1, optie 2) uit de Floorplanner-export
en zet ze als JSON in index.html (tussen /*PLANS*/ en /*END*/) en in data/plans.json.

Gebruik:  python3 scripts/extract.py ["pad/naar/export.fml"]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FML = next(ROOT.glob("*.fml"), None)

# Per variant: x-bereik in de export en verschuiving naar de coördinaten van het origineel.
VARIANTS = [
    {"id": "origineel", "title": "Huidige situatie", "x": (-900, 500), "dx": 0, "dy": 0},
    {"id": "optie1", "title": "Optie 1 · Bijkeuken blijft", "x": (880, 2100), "dx": 1775, "dy": 6},
    {"id": "optie2", "title": "Optie 2 · Bijkeuken naar garage", "x": (2560, 3750), "dx": 3448, "dy": 7},
]

# Ruimtes die in de export geen (bruikbare) naam hebben. Sleutel: (variant, naam, afgeronde min-x, min-y)
RENAME = {
    ("optie1", "Other"): "Hal",
    ("optie2", "Other"): "Hal",
    ("optie2", None): "Woonkeuken",
}


def shoelace(poly):
    s = 0.0
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        s += p["x"] * q["y"] - q["x"] * p["y"]
    return abs(s) / 2 / 10000  # cm² → m²


def pt(p, v):
    return {"x": round(p["x"] - v["dx"], 1), "y": round(p["y"] - v["dy"], 1)}


def inside(x, v):
    return v["x"][0] <= x <= v["x"][1]


def build(fml):
    design = fml["floors"][0]["designs"][0]
    out = []
    for v in VARIANTS:
        walls = []
        for w in design["walls"]:
            if not inside(w["a"]["x"], v):
                continue
            a, b = pt(w["a"], v), pt(w["b"], v)
            walls.append({
                "a": a, "b": b,
                "t": w["thickness"],
                "h": w["az"]["h"],
                "openings": [
                    {"type": o["type"], "t": round(o["t"], 4), "w": o["width"],
                     "z": o.get("z", 0), "zh": o.get("z_height", 0)}
                    for o in w["openings"]
                ],
            })

        areas = []
        for ar in design["areas"]:
            poly = ar["poly"]
            if not inside(min(p["x"] for p in poly), v):
                continue
            name = ar.get("name")
            name = RENAME.get((v["id"], name), name)
            m2 = shoelace(poly)
            # Optie 2: noordelijk garagedeel wordt de nieuwe bijkeuken
            if v["id"] == "optie2" and name == "Garage" and max(p["y"] for p in poly) - v["dy"] < -100:
                name = "Bijkeuken (nieuw)"
            # Origineel: het grote "Column"-vlak naast het toilet is de trap
            if v["id"] == "origineel" and name == "Column" and m2 > 1.5:
                name = "Trap"
            # Optie 1: smalle strook tussen bijkeuken en woonkamer is de oude kast
            if v["id"] == "optie1" and name == "Woonkamer" and m2 < 2:
                name = "Kast"
            area = {
                "name": name,
                "color": ar.get("color", "#eeeeee"),
                "m2": round(m2, 2),
                "poly": [pt(p, v) for p in poly],
            }
            # Label van de hal in de gang, anders valt het over het toilet
            if name == "Hal":
                area["label"] = {"x": 78, "y": 440}
            areas.append(area)

        # Meubilair (design["items"]) wordt bewust genegeerd
        surfaces = [
            {"name": s.get("customName") or s.get("name"), "color": s.get("color"),
             "poly": [pt(p, v) for p in s["poly"]]}
            for s in design["surfaces"] if inside(s["poly"][0]["x"], v)
        ]
        dims = [
            {"a": pt(d["a"], v), "b": pt(d["b"], v)}
            for d in design["dimensions"]
            if inside(d["a"]["x"], v) and inside(d["b"]["x"], v)
        ]
        labels = [
            {**pt(l, v), "text": l["text"]}
            for l in design["labels"] if inside(l["x"], v) and l["text"].startswith("H =")
        ]
        out.append({"id": v["id"], "title": v["title"], "walls": walls, "areas": areas,
                    "surfaces": surfaces, "dims": dims, "labels": labels})
        print(f"{v['id']:10} muren {len(walls):3}  ruimtes {len(areas):2}  maatlijnen {len(dims):3}")
    return out


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FML
    plans = build(json.loads(src.read_text()))
    payload = json.dumps(plans, separators=(",", ":"), ensure_ascii=False)

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "plans.json").write_text(json.dumps(plans, indent=1, ensure_ascii=False))

    html_path = ROOT / "index.html"
    if html_path.exists():
        html = html_path.read_text()
        html, n = re.subn(r"/\*PLANS\*/.*?/\*END\*/", lambda _: f"/*PLANS*/{payload}/*END*/", html, flags=re.S)
        if n != 1:
            sys.exit("index.html mist de /*PLANS*/…/*END*/ markering")
        html_path.write_text(html)
        print("index.html bijgewerkt")


if __name__ == "__main__":
    main()
