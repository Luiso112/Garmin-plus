#!/usr/bin/env python3
"""
stamina_ratio.py — Carga aguda vs crónica (ACWR) + semáforo anti-lesión.
Zero-Waste: solo Python stdlib. Lee data.json de Garmin-plus y escribe
resultados en campos limpios (acwr, fatigue_alert) sin tocar la UI.
Uso: python3 stamina_ratio.py [--write]  (--write actualiza data.json)
"""
import json
import sys
import os
from datetime import date

DATA = "/home/luis/garmin-plus/data.json"


def _min(dias):
    return min(d["min_intensidad"] for d in dias) if dias else 0


def _avg(dias, k):
    vals = [d[k] for d in dias if k in d]
    return round(sum(vals) / len(vals), 1) if vals else 0


def compute(days):
    """days: lista cronológica de desglose_diario (7 días/semana)."""
    if len(days) < 14:
        return None
    # carga aguda = media intensidad de últimos 7 días
    # carga crónica = media intensidad de últimos 28 días (máx 4 semanas)
    last7 = days[-7:]
    last28 = days[-28:] if len(days) >= 28 else days
    aguda = _avg(last7, "min_intensidad")
    cronica = _avg(last28, "min_intensidad") or 1
    ratio = round(aguda / cronica, 2) if cronica else 0

    # semáforo clásico ACWR: <0.8 zona de desentrenamiento,
    # 0.8-1.3 óptima, 1.3-1.5 precaución, >1.5 alto riesgo de lesión
    if ratio < 0.8:
        semaforo, emoji = "Desentrenamiento (baja carga)", "🟦"
    elif ratio <= 1.3:
        semaforo, emoji = "Zona óptima", "🟩"
    elif ratio <= 1.5:
        semaforo, emoji = "Precaución — subir carga despacio", "🟨"
    else:
        semaforo, emoji = "ALTO RIESGO de lesión — sesión de descarga recomendada", "🟥"

    # alerta de fatiga/enfermedad: HRV cae >20% vs media 28d y RHR sube >7 lpm vs base
    base = last28
    hrv_base = _avg(base, "hrv")
    rhr_base = _avg(base, "rhr")
    hrv_7 = _avg(last7, "hrv")
    rhr_7 = _avg(last7, "rhr")
    estres_7 = _avg(last7, "estres")

    flags = []
    if hrv_base and hrv_7 < hrv_base * 0.80:
        flags.append(f"HRV {hrv_7} vs base {hrv_base} (-20%)")
    if rhr_base and rhr_7 > rhr_base + 7:
        flags.append(f"RHR +{round(rhr_7 - rhr_base)} lpm sobre base")
    if estres_7 >= 45:
        flags.append(f"Estrés medio alto ({estres_7})")

    fatiga = {
        "nivel": "ALTA" if len(flags) >= 2 else ("MEDIA" if flags else "BAJA"),
        "motivos": flags,
        "mensaje": ("Posible fatiga no recuperada o inicio de proceso. "
                    "Prioriza descanso y vigila sueño." if len(flags) >= 2 else
                    "Todo en verde. Sin señales de alarma."),
    }

    return {
        "fecha": date.today().isoformat(),
        "carga_aguda_min_dia": aguda,
        "carga_cronica_min_dia": cronica,
        "ratio_acwr": ratio,
        "semaforo": semaforo,
        "emoji": emoji,
        "fatiga": fatiga,
        "dias_usados": len(days),
    }


def load_days(d):
    """Une desglose_diario + dias de historico_semanas, únicos y ordenados."""
    dias = {}
    for x in d.get("desglose_diario", []) + [dd for s in d.get("historico_semanas", []) for dd in s.get("dias", [])]:
        if x.get("fecha"):
            dias[x["fecha"]] = x
    return [dias[k] for k in sorted(dias)]


def main():
    write = "--write" in sys.argv
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    days = load_days(d)
    res = compute(days)
    if not res:
        print(json.dumps({"error": "Se necesitan >=14 días de desglose_diario"}))
        sys.exit(2)
    if write:
        d["acwr"] = res
    out = json.dumps(res, ensure_ascii=False, indent=None)
    # output filtrado (regla zero-waste): resumen mínimo
    print(out)
    if write:
        tmp = DATA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA)
        print("✓ data.json actualizado (campo acwr)", file=sys.stderr)


if __name__ == "__main__":
    main()
