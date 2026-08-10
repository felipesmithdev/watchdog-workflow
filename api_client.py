"""
Toda comunicação HTTP com o Lovable fica concentrada neste módulo.

Um único ENDPOINT_URL é usado para tudo - o que muda é o VERBO HTTP e
a forma de envio dos dados, não a URL:

    GET  ENDPOINT_URL?hostname=X                  -> leitura de configuração
    GET  ENDPOINT_URL?hostname=X&tipo=comandos     -> leitura de comandos pendentes
    POST ENDPOINT_URL                              -> heartbeat, eventos e resultado de comandos
"""

import time
from datetime import datetime

import requests

from config_manager import get_config, normalizar_configuracao
from logger import log_local
from settings import API_KEY, ENDPOINT_URL, HOSTNAME, INTERVALO_RETRY_CONFIG

# ==========================================================
# CONFIGURAÇÃO (leitura)
# ==========================================================

def buscar_configuracao_remota(hostname):
    """
    Consulta o banco de dados (Lovable) e retorna a configuração
    completa do dispositivo identificado por 'hostname'.

    Faz tentativas indefinidas em caso de falha, pois o watchdog não
    pode operar sem configuração (não há mais fallback local).
    """

    while True:

        try:

            headers = {
                "Authorization": f"Bearer {API_KEY}"
            }

            params = {
                "hostname": hostname
            }

            log_local(f"Consultando configuração remota (GET) para '{hostname}'...")

            # GET: leitura de dados, parâmetros na query string,
            # sem body e sem efeitos colaterais no servidor.
            resposta = requests.get(
                ENDPOINT_URL,
                headers=headers,
                params=params,
                timeout=10
            )

            resposta.raise_for_status()

            dados = resposta.json()

            config = normalizar_configuracao(hostname, dados)

            log_local("Configuração remota carregada com sucesso.")

            return config

        except Exception as e:

            log_local(f"Erro ao buscar configuração remota: {e}")
            log_local(f"Nova tentativa em {INTERVALO_RETRY_CONFIG}s...")

            time.sleep(INTERVALO_RETRY_CONFIG)


# ==========================================================
# EVENTOS E HEARTBEAT (escrita)
# ==========================================================

def enviar_evento(tipo, mensagem, extra=None):
    """
    Envia um evento pontual (ex: chrome_fechado, cpu_critica, erro_watchdog).
    Mantido igual ao script original para não perder nenhum registro
    de auditoria já existente.
    """

    config = get_config()

    payload = {
        "name": config.get("hostname", HOSTNAME),
        "hostname": config.get("hostname", HOSTNAME),
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

        # POST: envio/ingestão de dados, corpo em JSON.
        requests.post(
            ENDPOINT_URL,
            json=payload,
            headers=headers,
            timeout=5
        )

    except Exception as e:

        log_local(f"Erro endpoint (evento): {e}")


def enviar_heartbeat(cpu, memoria_ram, chrome_aberto, capture_aberto, status="online",
                      ping_ms=None, perda_pacotes_pct=None, ping_host=None):
    """
    Envia o heartbeat completo do dispositivo. O Lovable deve
    atualizar apenas uma linha por dispositivo (upsert por hostname).
    """

    config = get_config()
    agora = str(datetime.now())

    payload = {
        "hostname": config.get("hostname", HOSTNAME),
        "hospital": config.get("hospital", ""),
        "sala": config.get("sala", ""),
        "cpu": cpu,
        "memoria_ram": memoria_ram,
        "status": status,
        "chrome_aberto": chrome_aberto,
        "capture_aberto": capture_aberto,
        "ping_ms": ping_ms,
        "perda_pacotes_pct": perda_pacotes_pct,
        "ping_host": ping_host,
        "timestamp": agora,
        "last_seen": agora
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:

        # POST: envio/ingestão de dados, corpo em JSON.
        requests.post(
            ENDPOINT_URL,
            json=payload,
            headers=headers,
            timeout=5
        )

    except Exception as e:

        log_local(f"Erro endpoint (heartbeat): {e}")


# ==========================================================
# COMANDOS REMOTOS (leitura)
# ==========================================================
#
# ATENÇÃO - CONTRATO ASSUMIDO COM O LOVABLE (confirmar/ajustar):
#
#   GET  ENDPOINT_URL?hostname=X&tipo=comandos
#   Resposta esperada:
#   {
#     "comandos": [
#       {"id": "abc123", "comando": "restart_chrome"},
#       {"id": "def456", "comando": "shutdown"}
#     ]
#   }
#
# Se o Lovable expuser isso de forma diferente (outro endpoint,
# outros nomes de campo), é só ajustar esta função.

def buscar_comandos_pendentes(hostname):
    """Consulta o banco por comandos pendentes para este dispositivo."""

    try:

        headers = {
            "Authorization": f"Bearer {API_KEY}"
        }

        params = {
            "hostname": hostname,
            "tipo": "comandos"
        }

        resposta = requests.get(
            ENDPOINT_URL,
            headers=headers,
            params=params,
            timeout=10
        )

        resposta.raise_for_status()

        dados = resposta.json()

        return dados.get("comandos") or []

    except Exception as e:

        log_local(f"Erro ao buscar comandos pendentes: {e}")

        return []
