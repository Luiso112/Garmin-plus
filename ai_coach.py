#!/usr/bin/env python3
"""
ai_coach.py — Informe semanal Garmin-plus con IA (OpenRouter, modelo gratuito).
Zero-Waste: Python stdlib. Cero Ollama local (política anti-saturación CPU).
Lee data.json + métricas del diario (si existen), genera análisis con LLM
gratuito y lo envía por Telegram. Opcional: --write → data.json[ai_coach_insights].

Uso: python3 ai_coach.py [--write] [--no-telegram]
"""
import json
import os
import re
import sys
import glob
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stamina_ratio

DATA = stamina_ratio.DATA
VAULT = "/home/luis/OBSIDIAN/Mi Cerebro Digital"
FREE_MODELS = [
    # Orden: gratuitos $0 primero; pago barato solo como última red.
    "inclusionai/ling-3.1-flash",          # $0 en catálogo
    "deepseek/deepseek-v4-flash-0731",     # $0 en catálogo
    "deepseek/deepseek-chat-v3-0324",      # ~$0.11/$0.27 por 1M — fiable, última red
    # Nota: los :free clásicos (gemma/nemotron/llama) están en pool saturado (429)
    # y devuelven solo "reasoning" sin content. openrouter/free devuelve metadados
    # de seguridad, no informes. No usarlos aquí.
]
MAX_TOKENS = 1500


def load_key(var="OPENROUTER_API_KEY"):
    """Cascada de claves: ~/.privada → env → ~/.hermes/.env. Nunca imprime valores."""
    for p in (os.path.expanduser("~/.privada/personal/.env"),
              os.path.expanduser("~/.hermes/.env")):
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.startswith(var + "="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            pass
    return os.getenv(var)


def call_agy(prompt):
    """Motor 1: CLI agy (Antigravity → Gemini plan Pro de Luis, coste cero)."""
    import subprocess
    agy = os.path.expanduser("~/.local/bin/agy")
    if not os.path.exists(agy):
        raise RuntimeError("sin CLI agy")
    r = subprocess.run([agy, "-p", prompt], capture_output=True, text=True,
                       timeout=420, cwd="/tmp")
    if r.returncode != 0:
        raise RuntimeError(f"agy rc={r.returncode}")
    txt = r.stdout.strip()
    return txt, "agy → Gemini Pro (plan)"


def call_gemini(prompt):
    """Motor 2 (opcional): API Gemini directa — solo si GEMINI_API_KEY es válida."""
    key = load_key("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("sin GEMINI_API_KEY")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": MAX_TOKENS, "temperature": 0.4},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=***)",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        out = json.load(r)
    txt = out["candidates"][0]["content"]["parts"][0]["text"].strip()
    return txt, "gemini-2.5-flash (plan Pro)"


def diary_week(days=14):
    """Extrae métricas YAML del diario más reciente (sin leer contenido íntimo)."""
    out = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        path = f"{VAULT}/900 DIARIO/{d}.md"
        if not os.path.exists(path):
            continue
        try:
            head = open(path, encoding="utf-8").read(1200)
        except OSError:
            continue
        m = re.match(r"^---\n(.*?)\n---", head, re.S)
        if not m:
            continue
        y = m.group(1)
        def g(k):
            mm = re.search(rf"^{k}:\s*([\d.]+)", y, re.M)
            return mm.group(1) if mm else None
        row = {k: g(k) for k in ("meditacion", "conocimiento", "fuerza", "andar",
                                 "control", "nutricion", "espiritualidad")}
        if any(v for v in row.values()):
            out.append({"fecha": d, **row})
    return out


def build_context():
    d = json.load(open(DATA, encoding="utf-8"))
    days = stamina_ratio.load_days(d)
    acwr = stamina_ratio.compute(days) or {}
    mc = d.get("metricas_clave", {})
    ar = d.get("active_intelligence", {})
    bb = d.get("body_battery", {})
    ctx = {
        "resumen_semanal": {k: mc.get(k) for k in
                            ("rhr", "hrv", "sueno_score", "pasos_semana",
                             "estres", "vo2max", "min_intensidad")},
        "carga_acwr": {k: acwr.get(k) for k in
                       ("carga_aguda_min_dia", "carga_cronica_min_dia",
                        "ratio_acwr", "semaforo", "fatiga")},
        "readiness": ar.get("nivel") if isinstance(ar, dict) else None,
        "body_battery": {"actual": bb.get("actual"), "min": bb.get("min")},
        "ultimas_actividades": [a.get("nombre") for a in d.get("actividades", [])[:5]],
        "diario_personal": diary_week(),
    }
    return ctx


def _usable(text):
    """Criterio de calidad: descarta respuestas vacías o metadados del router."""
    if not text:
        return False
    t = text.strip()
    junk = ("user safety", "safe\n", "no content", "hello!")
    return len(t) >= 150 and not t.lower().startswith(junk)


def call_llm(ctx):
    prompt = (
        "Eres un coach de running y montaña experto en HRV, carga aguda/crónica (ACWR) "
        "y sueño. Luis (61 años, Fenix 7) te da sus datos de la semana en JSON. "
        "IMPORTANTE: no muestres análisis ni razonamiento previo; tu respuesta debe ser "
        "ÚNICAMENTE el informe final. Redáctalo en español, máximo 160 palabras, formato "
        "Telegram (Markdown, sin tablas): 1) Una línea de veredicto (emoji + estado). "
        "2) Qué dicen carga/HRV/sueño y si las sensaciones del diario coinciden con los "
        "datos (si el diario está vacío, dilo en una línea). 3) UNA recomendación concreta "
        "para los próximos 7 días (sesiones, intensidades). "
        "Sé directo, cero relleno, cero advertencias médicas genéricas.\n\n"
        + json.dumps(ctx, ensure_ascii=False)
    )
    # Motor 1: agy → Gemini plan Pro de Luis (coste cero, orden directa).
    for motor in (call_agy, call_gemini):
        try:
            txt, model = motor(prompt)
            if _usable(txt):
                return txt, model
        except Exception:
            continue
    # Motor 2 (red): OpenRouter gratuito/barato — requiere OPENROUTER_API_KEY.
    key = load_key()
    if not key:
        raise RuntimeError("Gemini falló y no hay OPENROUTER_API_KEY para la red")
    payload_models = {
        "model": None,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.4,
    }
    last_err = None
    for model in FREE_MODELS:
        body = dict(payload_models, model=model)
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                out = json.load(r)
            msg = out["choices"][0]["message"]
            txt = (msg.get("content") or "").strip()
            if not txt:  # algunos routers ponen el texto en reasoning
                txt = (msg.get("reasoning") or "").strip()
            if _usable(txt):
                return txt, model
            last_err = RuntimeError(f"{model}: respuesta vacía/no útil")
            continue
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Todos los modelos gratuitos fallaron: {last_err}")


def main():
    write = "--write" in sys.argv
    no_tg = "--no-telegram" in sys.argv
    ctx = build_context()
    txt, model = call_llm(ctx)
    # filtrado estricto de salida (zero-waste)
    print(f"[modelo: {model}]")
    print(txt)
    if write:
        d = json.load(open(DATA, encoding="utf-8"))
        insight = {"fecha": date.today().isoformat(), "modelo": model, "texto": txt}
        d["ai_coach_insights"] = insight
        tmp = DATA + ".tmp"
        json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, DATA)
        # Fichero propio e inmortales: generate_data.py NO lo toca → el informe
        # sobrevive a los syncs entre semana (la UI puede fetch'earlo también).
        json.dump(insight, open("/home/luis/garmin-plus/coach_insights.json", "w",
                                encoding="utf-8"), ensure_ascii=False, indent=2)
        print("✓ data.json + coach_insights.json actualizados", file=sys.stderr)
    if not no_tg:
        sys.path.insert(0, f"{VAULT}/000 NEXUS/_SCRIPTS")
        from notify_telegram import send_telegram
        ok = send_telegram("🏃 *Informe semanal Garmin-plus*\n\n" + txt)
        print("✓ Telegram enviado" if ok else "⚠ Telegram falló", file=sys.stderr)


if __name__ == "__main__":
    main()
