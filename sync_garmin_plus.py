#!/usr/bin/env python3
"""
Sincronizador Continuo e Híbrido Garmin Connect+
1. Extrae métricas frescas de Garmin Connect hacia Obsidian.
2. Regenera data.json con el motor de fusión (Fénix 7 + Amazfit Helio).
3. Publica automáticamente los cambios a GitHub Pages (git push).
4. Diseñado para ejecutarse en segundo plano sin consumo innecesario de recursos.
"""

import os
import sys
import subprocess
import datetime

GARMIN_FETCH_SCRIPT = "/home/luis/OBSIDIAN/Mi Cerebro Digital/000 NEXUS/HABILIDADES/captura/garmin-sync/garmin_fetch.py"
GENERATE_DATA_SCRIPT = "/home/luis/garmin-plus/generate_data.py"
GARMIN_PLUS_DIR = "/home/luis/garmin-plus"
LOG_FILE = "/home/luis/garmin-plus/sync.log"

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    # Solo escrita directa al fichero: el cron redirige stdout al mismo sync.log,
    # imprimir aquí duplicaba cada línea.
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def run_sync():
    log("🚀 Iniciando ciclo de sincronización Garmin Connect+...")

    # 1. Ejecutar garmin_fetch.py para actualizar Obsidian con Garmin Connect
    try:
        log("1/3 Sincronizando con Garmin Connect API...")
        res_fetch = subprocess.run(
            ["/usr/bin/python3", GARMIN_FETCH_SCRIPT],
            capture_output=True,
            text=True,
            timeout=180
        )
        if res_fetch.returncode == 0:
            log("✓ Garmin Connect sincronizado.")
        else:
            log(f"Aviso en garmin_fetch: {res_fetch.stderr.strip()[:200]}")
    except Exception as e:
        log(f"Error ejecutando garmin_fetch: {e}")

    # 2. Regenerar data.json en el repositorio garmin-plus
    try:
        log("2/4 Procesando motor de fusión y generando data.json...")
        res_data = subprocess.run(
            ["/usr/bin/python3", GENERATE_DATA_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60
        )
        if res_data.returncode == 0:
            log("✓ data.json actualizado con éxito.")
        else:
            log(f"Error en generate_data: {res_data.stderr.strip()}")
            return
    except Exception as e:
        log(f"Error generando data.json: {e}")
        return

    # 2b. Calcular y escribir métricas de carga aguda/crónica (ACWR)
    try:
        log("3/4 Calculando ratio ACWR anti-lesión (stamina_ratio)...")
        stamina_script = os.path.join(GARMIN_PLUS_DIR, "stamina_ratio.py")
        if os.path.exists(stamina_script):
            res_acwr = subprocess.run(
                ["/usr/bin/python3", stamina_script, "--write"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if res_acwr.returncode == 0:
                log("✓ Carga aguda/crónica (ACWR) calculada y guardada.")
            else:
                log(f"Aviso en stamina_ratio: {res_acwr.stderr.strip()[:200]}")
    except Exception as e:
        log(f"Error calculando ACWR: {e}")

    # 3. Comprobar si hay cambios y hacer git push a GitHub Pages
    try:
        log("3/3 Comprobando cambios para GitHub Pages...")
        # Red de seguridad: no publicar data.json roto
        smoke = subprocess.run(
            ["/usr/bin/python3", os.path.join(GARMIN_PLUS_DIR, "smoke_test.py")],
            capture_output=True, text=True, timeout=30)
        if smoke.returncode != 0:
            log(f"⛔ smoke_test falló: {smoke.stdout.strip()[:200]} — push cancelado")
            return
        status = subprocess.run(
            ["git", "-C", GARMIN_PLUS_DIR, "status", "--porcelain"],
            capture_output=True,
            text=True
        ).stdout.strip()

        if status:
            subprocess.run(["git", "-C", GARMIN_PLUS_DIR, "add", "data.json", "index.html"], check=True)
            commit_msg = f"sync: auto-sync metrics {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
            subprocess.run(["git", "-C", GARMIN_PLUS_DIR, "commit", "-m", commit_msg], check=True)
            res_push = subprocess.run(["git", "-C", GARMIN_PLUS_DIR, "push", "origin", "main"], capture_output=True, text=True)
            if res_push.returncode == 0:
                log("✅ GitHub Pages actualizado con éxito vía git push.")
            else:
                log(f"Aviso en git push: {res_push.stderr.strip()[:200]}")
        else:
            log("ℹ️ No hay cambios pendientes, data.json ya estaba actualizado.")
    except Exception as e:
        log(f"Error al publicar en GitHub: {e}")

if __name__ == "__main__":
    run_sync()
