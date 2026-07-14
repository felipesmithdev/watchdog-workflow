import json
import os
import socket
import subprocess
import time
import traceback
from datetime import datetime

import psutil
import requests

# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

LIMITE_CPU = 75
TEMPO_CRITICO = 10
TEMPO_PAUSADO = 30

ENDPOINT_URL = "https://flux-heartbeat.lovable.app/api/public/ingest/2a3c35b4-b740-4fe0-b216-c7b2c50a137e"

API_KEY = "pk_0e55c97681154727a54be6541f88db186fec32bcdb1e484e86b043913cbbe495"

HOSTNAME = socket.gethostname()

CONFIG_FILE = "config.json"

segundos_cpu_alta = 0


# ==========================================================
# LOG
# ==========================================================

def log_local(msg):

    texto = f"[{datetime.now()}] {msg}"

    print(texto)

    with open("watchdog.log", "a", encoding="utf-8") as f:
        f.write(texto + "\n")


# ==========================================================
# CONFIG
# ==========================================================

def criar_config_padrao():

    config = {
        "hostname": HOSTNAME,
        "url": "",
        "chrome_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    log_local("config.json criado. Configure a URL da sala.")

    return config


def carregar_config():

    if not os.path.exists(CONFIG_FILE):
        return criar_config_padrao()

    try:

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:

            config = json.load(f)

            if "url" not in config:
                config["url"] = ""

            if "chrome_path" not in config:
                config["chrome_path"] = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

            return config

    except Exception as e:

        log_local(f"Erro lendo config.json: {e}")

        return criar_config_padrao()


CONFIG = carregar_config()

URL_ONECONNECT = CONFIG["url"]

CHROME_PATH = CONFIG["chrome_path"]


# ==========================================================
# ENDPOINT
# ==========================================================

def enviar_evento(tipo, mensagem, extra=None):

    payload = {

        "name": HOSTNAME,
        "hostname": HOSTNAME,
        "status": "online",
        "tipo": tipo,
        "mensagem": mensagem,
        "timestamp": str(datetime.now())
    }

    if extra:
        payload.update(extra)

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:

        requests.post(
            ENDPOINT_URL,
            json=payload,
            headers=headers,
            timeout=5
        )

    except Exception as e:

        log_local(f"Erro endpoint: {e}")


# ==========================================================
# CHROME
# ==========================================================

def abrir_chrome():

    global URL_ONECONNECT

    try:

        CONFIG = carregar_config()

        URL_ONECONNECT = CONFIG["url"]

        CHROME_PATH = CONFIG["chrome_path"]

        if URL_ONECONNECT.strip() == "":

            log_local("Nenhuma URL configurada.")

            subprocess.Popen(
                ["cmd", "/c", "start", "chrome"]
            )

            return

        log_local(f"Abrindo URL: {URL_ONECONNECT}")

        subprocess.Popen([
            CHROME_PATH,
            "--new-window",
            URL_ONECONNECT
        ])

    except Exception as e:

        log_local(f"Erro abrindo Chrome: {e}")


# ==========================================================
# PROCESSOS
# ==========================================================

def finalizar_processos():

    chrome = False
    capture = False

    for proc in psutil.process_iter(["pid", "name"]):

        try:

            nome = proc.info["name"]

            if nome is None:
                continue

            nome = nome.lower()

            if nome == "chrome.exe":

                chrome = True

                log_local(f"Matando Chrome PID {proc.pid}")

                enviar_evento(
                    "chrome_fechado",
                    "Chrome encerrado",
                    {
                        "pid": proc.pid
                    }
                )

                proc.kill()

            elif nome == "4kcaptureutility.exe":

                capture = True

                log_local(f"Matando 4K PID {proc.pid}")

                enviar_evento(
                    "4k_fechado",
                    "4K encerrado",
                    {
                        "pid": proc.pid
                    }
                )

                proc.kill()

        except Exception as e:

            log_local(f"Erro processo: {e}")

    return chrome, capture


# ==========================================================
# INÍCIO
# ==========================================================

log_local("====================================")
log_local("WATCHDOG INICIADO")
log_local(f"Hostname: {HOSTNAME}")
log_local(f"URL: {URL_ONECONNECT}")
log_local("====================================")


# ==========================================================
# LOOP
# ==========================================================

while True:

    try:

        cpu = psutil.cpu_percent(interval=1)

        log_local(f"CPU {cpu}%")

        enviar_evento(
            "heartbeat",
            "Monitorando",
            {
                "cpu": cpu
            }
        )

        if cpu >= LIMITE_CPU:

            segundos_cpu_alta += 1

            log_local(
                f"CPU crítica por {segundos_cpu_alta}s"
            )

        else:

            segundos_cpu_alta = 0

        if segundos_cpu_alta >= TEMPO_CRITICO:

            enviar_evento(
                "cpu_critica",
                "CPU acima do limite",
                {
                    "cpu": cpu
                }
            )

            chrome, capture = finalizar_processos()

            if not chrome:

                enviar_evento(
                    "chrome_nao_encontrado",
                    "Chrome não estava em execução"
                )

            if not capture:

                enviar_evento(
                    "4k_nao_encontrado",
                    "4KCaptureUtility não estava em execução"
                )

            log_local(
                f"Aguardando {TEMPO_PAUSADO}s..."
            )

            time.sleep(TEMPO_PAUSADO)

            abrir_chrome()

            enviar_evento(
                "chrome_reaberto",
                "Chrome reaberto automaticamente",
                {
                    "url": URL_ONECONNECT
                }
            )

            segundos_cpu_alta = 0

        time.sleep(1)

    except Exception as e:

        log_local(f"ERRO WATCHDOG: {e}")

        traceback.print_exc()

        enviar_evento(
            "erro_watchdog",
            str(e)
        )

        time.sleep(5)