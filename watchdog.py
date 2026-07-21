import socket
import subprocess
import time
import traceback
from datetime import datetime

import psutil
import requests

# ==========================================================
# REGIÃO: INICIALIZAÇÃO
# ==========================================================
# Constantes fixas do agente. Diferente da configuração operacional
# (sala, URL, limites de CPU etc.), estes valores identificam ONDE
# o agente busca informações e NÃO vêm do banco - são parte do
# próprio agente, assim como já eram no script original.

HOSTNAME = socket.gethostname()

# Endpoint único do Lovable, usado tanto para ler configuração
# quanto para enviar heartbeat/eventos. O que muda é o VERBO HTTP
# e a forma de envio dos dados, não a URL:
#
#   GET  ENDPOINT_URL?hostname=X   -> leitura de configuração
#                                      (idempotente, sem efeitos colaterais,
#                                      dados vão na query string)
#
#   POST ENDPOINT_URL              -> heartbeat e eventos
#                                      (envia/ingere dados, corpo em JSON)
#
ENDPOINT_URL = "https://flux-heartbeat.lovable.app/api/public/ingest/2a3c35b4-b740-4fe0-b216-c7b2c50a137e"
API_KEY = "pk_0e55c97681154727a54be6541f88db186fec32bcdb1e484e86b043913cbbe495"

# Intervalo entre tentativas de busca de configuração, caso o
# banco esteja indisponível na inicialização.
INTERVALO_RETRY_CONFIG = 15  # segundos

# Valores padrão de segurança, usados SOMENTE se o banco não
# retornar algum desses campos (mesmo comportamento defensivo que
# o carregar_config() original tinha para "url" e "chrome_path").
PADRAO_CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
PADRAO_LIMITE_CPU = 75
PADRAO_TEMPO_CRITICO = 10
PADRAO_TEMPO_PAUSADO = 30

# Configuração ativa em memória (preenchida por buscar_configuracao_remota)
CONFIG = {}

# Contador de segundos consecutivos com CPU acima do limite
segundos_cpu_alta = 0


# ==========================================================
# REGIÃO: LOG
# ==========================================================

def log_local(msg):
    """Escreve uma mensagem no console e no arquivo watchdog.log."""

    texto = f"[{datetime.now()}] {msg}"

    print(texto)

    with open("watchdog.log", "a", encoding="utf-8") as f:
        f.write(texto + "\n")


# ==========================================================
# REGIÃO: CONFIGURAÇÃO (BANCO DE DADOS - LOVABLE)
# ==========================================================
# Substitui completamente o config.json local. carregar_config() e
# criar_config_padrao() deixam de existir. Toda configuração agora
# vem do banco, identificada pelo hostname da máquina.

def buscar_configuracao_remota(hostname):
    """
    Consulta o banco de dados (Lovable) e retorna a configuração
    completa do dispositivo identificado por 'hostname'.

    Faz tentativas indefinidas em caso de falha, pois o watchdog
    não pode operar sem configuração (não há mais fallback local).
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


def normalizar_configuracao(hostname, dados):
    """
    Garante que todos os campos obrigatórios existam na configuração,
    aplicando valores padrão quando necessário (mesma postura defensiva
    do carregar_config() original).
    """

    config = {
        "hostname": hostname,
        "hospital": dados.get("hospital", ""),
        "sala": dados.get("sala", ""),
        "url": dados.get("url", ""),
        "chrome_path": dados.get("chrome_path", PADRAO_CHROME_PATH),
        "limite_cpu": dados.get("limite_cpu", PADRAO_LIMITE_CPU),
        "tempo_critico": dados.get("tempo_critico", PADRAO_TEMPO_CRITICO),
        "tempo_pausado": dados.get("tempo_pausado", PADRAO_TEMPO_PAUSADO),
    }

    return config


# ==========================================================
# REGIÃO: COMUNICAÇÃO API (EVENTOS E HEARTBEAT)
# ==========================================================
# Toda comunicação HTTP com o Lovable fica concentrada aqui.

def enviar_evento(tipo, mensagem, extra=None):
    """
    Envia um evento pontual (ex: chrome_fechado, cpu_critica, erro_watchdog).
    Mantido igual ao script original para não perder nenhum registro
    de auditoria já existente.
    """

    payload = {
        "name": CONFIG.get("hostname", HOSTNAME),
        "hostname": CONFIG.get("hostname", HOSTNAME),
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


def enviar_heartbeat(cpu, memoria_ram, chrome_aberto, capture_aberto, status="online"):
    """
    Envia o heartbeat completo do dispositivo. O Lovable deve
    atualizar apenas uma linha por dispositivo (upsert por hostname).
    """

    agora = str(datetime.now())

    payload = {
        "hostname": CONFIG.get("hostname", HOSTNAME),
        "hospital": CONFIG.get("hospital", ""),
        "sala": CONFIG.get("sala", ""),
        "cpu": cpu,
        "memoria_ram": memoria_ram,
        "status": status,
        "chrome_aberto": chrome_aberto,
        "capture_aberto": capture_aberto,
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
# REGIÃO: CHROME
# ==========================================================

def abrir_chrome():
    """
    Abre o Chrome na sala configurada. Assim como no script original,
    a configuração é recarregada antes de abrir, garantindo que a
    URL/caminho mais recentes (definidos no banco) sejam usados mesmo
    que tenham sido alterados após o início do watchdog.
    """

    global CONFIG

    try:

        CONFIG = buscar_configuracao_remota(HOSTNAME)

        url_sala = CONFIG["url"]
        chrome_path = CONFIG["chrome_path"]

        if url_sala.strip() == "":

            log_local("Nenhuma URL configurada.")

            subprocess.Popen(
                ["cmd", "/c", "start", "chrome"]
            )

            return

        log_local(f"Abrindo URL: {url_sala}")

        subprocess.Popen([
            chrome_path,
            "--new-window",
            url_sala
        ])

    except Exception as e:

        log_local(f"Erro abrindo Chrome: {e}")


# ==========================================================
# REGIÃO: PROCESSOS
# ==========================================================

def finalizar_processos():
    """Encerra Chrome e 4KCaptureUtility. Lógica idêntica ao original."""

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


def verificar_processos_ativos():
    """
    Verifica (sem encerrar) se Chrome e 4KCaptureUtility estão em
    execução. Usado apenas para compor o heartbeat.
    """

    chrome_aberto = False
    capture_aberto = False

    for proc in psutil.process_iter(["name"]):

        try:

            nome = proc.info["name"]

            if nome is None:
                continue

            nome = nome.lower()

            if nome == "chrome.exe":
                chrome_aberto = True

            elif nome == "4kcaptureutility.exe":
                capture_aberto = True

        except Exception:
            continue

    return chrome_aberto, capture_aberto


# ==========================================================
# REGIÃO: COMANDOS REMOTOS (RESERVADO - ETAPA 2)
# ==========================================================
# NÃO IMPLEMENTAR AGORA.
# Nesta etapa futura, o watchdog consultará periodicamente uma fila
# de comandos no banco (restart_chrome, restart_capture, restart_all,
# shutdown, reboot, refresh_page, kill_chrome, kill_capture, open_url),
# executará o comando recebido e enviará o resultado de volta.
# A região existe apenas para deixar clara a próxima extensão do
# código; nenhuma função é chamada no loop principal ainda.


# ==========================================================
# REGIÃO: MONITORAMENTO CPU / LOOP PRINCIPAL
# ==========================================================

def iniciar_watchdog():

    global CONFIG, segundos_cpu_alta

    # 1. Descobrir hostname (já feito na inicialização do módulo)
    # 2/3/4. Consultar banco e baixar configuração completa
    CONFIG = buscar_configuracao_remota(HOSTNAME)

    log_local("====================================")
    log_local("WATCHDOG INICIADO")
    log_local(f"Hostname: {CONFIG['hostname']}")
    log_local(f"Hospital: {CONFIG['hospital']}")
    log_local(f"Sala: {CONFIG['sala']}")
    log_local(f"URL: {CONFIG['url']}")
    log_local("====================================")

    # 5. Iniciar monitoramento
    while True:

        try:

            limite_cpu = CONFIG["limite_cpu"]
            tempo_critico = CONFIG["tempo_critico"]
            tempo_pausado = CONFIG["tempo_pausado"]

            cpu = psutil.cpu_percent(interval=1)
            memoria_ram = psutil.virtual_memory().percent

            chrome_aberto, capture_aberto = verificar_processos_ativos()

            log_local(f"CPU {cpu}% | RAM {memoria_ram}%")

            enviar_heartbeat(
                cpu=cpu,
                memoria_ram=memoria_ram,
                chrome_aberto=chrome_aberto,
                capture_aberto=capture_aberto,
                status="online"
            )

            if cpu >= limite_cpu:

                segundos_cpu_alta += 1

                log_local(f"CPU crítica por {segundos_cpu_alta}s")

            else:

                segundos_cpu_alta = 0

            if segundos_cpu_alta >= tempo_critico:

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

                log_local(f"Aguardando {tempo_pausado}s...")

                time.sleep(tempo_pausado)

                abrir_chrome()

                enviar_evento(
                    "chrome_reaberto",
                    "Chrome reaberto automaticamente",
                    {
                        "url": CONFIG["url"]
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


# ==========================================================
# PONTO DE ENTRADA
# ==========================================================

if __name__ == "__main__":
    iniciar_watchdog()