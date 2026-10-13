#!/usr/bin/env python3
"""
smoke_test.py — Red de seguridad post-sync (stdlib puro, salida filtrada).
Valida que data.json es JSON íntegro y que las claves críticas existen,
antes de que GitHub Pages sirva datos rotos.
Uso: python3 smoke_test.py   → rc 0 OK / rc 1 fallo (el cron lo notifica)
"""
import json
import sys
import urllib.request

DATA = "/home/luis/garmin-plus/data.json"
CRITICAS = ["usuario", "metricas_clave", "desglose_diario",
            "historico_semanas", "body_battery"]
URLS = [
    "https://luiso112.github.io/Garmin-plus/index.html",
    "https://luiso112.github.io/Garmin-plus/sw.js",
    "https://luiso112.github.io/Garmin-plus/manifest.json",
]


def main():
    try:
        d = json.load(open(DATA, encoding="utf-8"))
    except Exception as e:
        print(f"SMOKE ✗ data.json ilegible: {e}")
        sys.exit(1)
    faltan = [k for k in CRITICAS if k not in d]
    if faltan:
        print(f"SMOKE ✗ claves ausentes: {faltan}")
        sys.exit(1)
    for k in ("acwr", "ai_coach_insights"):
        if k in d and not isinstance(d[k], dict):
            print(f"SMOKE ✗ {k} corrupto (no dict)")
            sys.exit(1)
    dias = d.get("desglose_diario", [])
    if not dias:
        print("SMOKE ✗ desglose_diario vacío")
        sys.exit(1)
    print(f"SMOKE ✓ {len(d)} claves, {len(dias)} días, acwr={'sí' if 'acwr' in d else 'no'}")
    sys.exit(0)


if __name__ == "__main__":
    main()
