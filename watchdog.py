import socket
import subprocess
import time
import traceback
import urllib.parse
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
PADRAO_TEMPO_PAUSADO = 10

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


def _valor_texto(dados, campo, padrao=""):
    """
    Lê um campo de texto do JSON, tratando tanto ausência da chave
    quanto valor explicitamente 'null' (dict.get sozinho só cobre o
    primeiro caso - foi exatamente isso que causou o bug do
    'NoneType' em produção).
    """

    valor = dados.get(campo)

    if valor is None:
        return padrao

    return str(valor)


def _valor_numerico(dados, campo, padrao):
    """
    Lê um campo numérico do JSON (limite_cpu, tempo_critico, tempo_pausado).
    Trata: chave ausente, valor null, string vazia, e valores vindos
    como texto (ex: formulário do Lovable enviando "90" em vez de 90).
    """

    valor = dados.get(campo)

    if valor is None or valor == "":
        return padrao

    try:
        return int(valor)
    except (TypeError, ValueError):
        try:
            return float(valor)
        except (TypeError, ValueError):
            log_local(f"Valor inválido para '{campo}': {valor!r}. Usando padrão {padrao}.")
            return padrao


def normalizar_configuracao(hostname, dados):
    """
    Garante que todos os campos obrigatórios existam na configuração,
    aplicando valores padrão quando necessário (mesma postura defensiva
    do carregar_config() original, agora também à prova de valores
    'null' vindos do banco).
    """

    config = {
        "hostname": hostname,
        "hospital": _valor_texto(dados, "hospital"),
        "sala": _valor_texto(dados, "sala"),
        "url": _valor_texto(dados, "url"),
        "chrome_path": _valor_texto(dados, "chrome_path", PADRAO_CHROME_PATH) or PADRAO_CHROME_PATH,
        "limite_cpu": _valor_numerico(dados, "limite_cpu", PADRAO_LIMITE_CPU),
        "tempo_critico": _valor_numerico(dados, "tempo_critico", PADRAO_TEMPO_CRITICO),
        "tempo_pausado": _valor_numerico(dados, "tempo_pausado", PADRAO_TEMPO_PAUSADO),
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


def enviar_heartbeat(cpu, memoria_ram, chrome_aberto, capture_aberto, status="online",
                      ping_ms=None, perda_pacotes_pct=None, ping_host=None):
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

def finalizar_processo_por_nome(nome_processo, tipo_evento, mensagem_evento):
    """
    Encerra todos os processos com o nome informado (ex: 'chrome.exe').
    Retorna True se ao menos um processo foi encontrado e encerrado.
    Usado tanto pelo monitoramento automático de CPU quanto pelos
    comandos remotos (ex: restart_chrome isolado, sem mexer no 4K).
    """

    encontrado = False

    for proc in psutil.process_iter(["pid", "name"]):

        try:

            nome = proc.info["name"]

            if nome is None:
                continue

            if nome.lower() == nome_processo:

                encontrado = True

                log_local(f"Matando {nome_processo} PID {proc.pid}")

                enviar_evento(
                    tipo_evento,
                    mensagem_evento,
                    {
                        "pid": proc.pid
                    }
                )

                proc.kill()

        except Exception as e:

            log_local(f"Erro processo: {e}")

    return encontrado


def finalizar_processos():
    """Encerra Chrome e 4KCaptureUtility. Lógica idêntica ao original."""

    chrome = finalizar_processo_por_nome("chrome.exe", "chrome_fechado", "Chrome encerrado")
    capture = finalizar_processo_por_nome("4kcaptureutility.exe", "4k_fechado", "4K encerrado")

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
# REGIÃO: REDE (DIAGNÓSTICO DE QUALIDADE DE CONEXÃO)
# ==========================================================
# Mede latência e perda de pacotes sem depender de ICMP (o comando
# 'ping' do Windows tem parsing frágil dependendo do idioma do SO,
# e ICMP costuma ser bloqueado em redes hospitalares). Em vez disso,
# medimos o tempo de uma conexão TCP direta - mais confiável e testa
# exatamente a rota que importa: até o servidor da sala OneConnect.

INTERVALO_CHECAGEM_REDE = 10  # segundos entre medições (não medir a cada ciclo do loop)

_ultima_checagem_rede = 0.0
_ultimo_resultado_rede = {
    "ping_host": None,
    "ping_ms": None,
    "perda_pacotes_pct": None
}


def obter_host_para_ping():
    """
    Determina qual host testar. Prioriza o domínio da própria URL
    da sala (mede a rota real que importa); usa um host público
    confiável como fallback caso a URL não esteja configurada.
    """

    url_sala = CONFIG.get("url", "")

    try:

        if url_sala:

            url_completa = url_sala if "://" in url_sala else f"https://{url_sala}"

            partes = urllib.parse.urlparse(url_completa)

            if partes.hostname:
                return partes.hostname

    except Exception:
        pass

    return "8.8.8.8"


def medir_qualidade_rede(host=None, porta=443, tentativas=3, timeout=2):
    """
    Mede latência média (ms) e perda de pacotes (%) abrindo conexões
    TCP diretas ao host informado. Não trava o watchdog por muito
    tempo: no pior caso (rede totalmente fora), o tempo máximo é
    tentativas * timeout segundos.
    """

    if host is None:
        host = obter_host_para_ping()

    latencias = []
    falhas = 0

    for _ in range(tentativas):

        inicio = time.perf_counter()

        try:

            with socket.create_connection((host, porta), timeout=timeout):
                pass

            latencias.append((time.perf_counter() - inicio) * 1000)

        except Exception:

            falhas += 1

    perda_pct = round((falhas / tentativas) * 100, 1)
    latencia_media = round(sum(latencias) / len(latencias), 1) if latencias else None

    return {
        "ping_host": host,
        "ping_ms": latencia_media,
        "perda_pacotes_pct": perda_pct
    }


def obter_qualidade_rede_atual():
    """
    Retorna a última medição de rede feita, atualizando-a a cada
    INTERVALO_CHECAGEM_REDE segundos. Evita testar a rede a cada
    ciclo do loop principal (o que atrasaria o monitoramento de CPU
    justamente quando a rede está ruim).
    """

    global _ultima_checagem_rede, _ultimo_resultado_rede

    agora = time.time()

    if agora - _ultima_checagem_rede >= INTERVALO_CHECAGEM_REDE:

        _ultima_checagem_rede = agora
        _ultimo_resultado_rede = medir_qualidade_rede()

        log_local(
            f"Rede: {_ultimo_resultado_rede['ping_ms']}ms "
            f"| perda {_ultimo_resultado_rede['perda_pacotes_pct']}% "
            f"(host: {_ultimo_resultado_rede['ping_host']})"
        )

    return _ultimo_resultado_rede


# ==========================================================
# REGIÃO: COMANDOS REMOTOS
# ==========================================================
# O watchdog consulta periodicamente o banco por comandos pendentes
# para este hostname, executa e envia o resultado de volta.
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
#   POST ENDPOINT_URL  (resultado, reaproveitando enviar_evento)
#   {
#     "tipo": "resultado_comando",
#     "comando_id": "abc123",
#     "comando": "restart_chrome",
#     "status": "sucesso" | "erro",
#     "mensagem": "..."
#   }
#
# Se o Lovable expuser isso de forma diferente (outro endpoint,
# outros nomes de campo), é só ajustar buscar_comandos_pendentes().

INTERVALO_CHECAGEM_COMANDOS = 5  # segundos entre verificações de comandos pendentes

_ultima_checagem_comandos = 0.0


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


def enviar_resultado_comando(comando_id, comando, status, mensagem):
    """Reaproveita enviar_evento para reportar o resultado da execução."""

    enviar_evento(
        "resultado_comando",
        mensagem,
        {
            "comando_id": comando_id,
            "comando": comando,
            "status": status
        }
    )


def comando_restart_chrome():
    """Reinicia apenas o Chrome (mantém o 4KCaptureUtility rodando)."""

    finalizar_processo_por_nome("chrome.exe", "chrome_fechado", "Chrome encerrado (comando remoto)")

    tempo_pausado = CONFIG.get("tempo_pausado", PADRAO_TEMPO_PAUSADO)

    log_local(f"Aguardando {tempo_pausado}s antes de reabrir (comando remoto)...")

    time.sleep(tempo_pausado)

    abrir_chrome()

    return "Chrome reiniciado com sucesso via comando remoto."


def comando_shutdown():
    """Desliga a máquina Windows. Dá 5s de margem para o resultado ser enviado antes."""

    subprocess.Popen(["shutdown", "/s", "/t", "5"])

    return "Comando de desligamento enviado. A máquina será desligada em 5 segundos."


# Tabela de comandos suportados -> função executora.
# Adicionar novos comandos aqui é o único passo necessário para expandir.
COMANDOS_DISPONIVEIS = {
    "restart_chrome": comando_restart_chrome,
    "shutdown": comando_shutdown,
    "desligar_maquina": comando_shutdown,  # alias em português
}


def executar_comando(comando_item):
    """Executa um único comando recebido do banco e reporta o resultado."""

    comando_id = comando_item.get("id")
    comando = comando_item.get("comando")

    log_local(f"Comando recebido: '{comando}' (id={comando_id})")

    funcao = COMANDOS_DISPONIVEIS.get(comando)

    if funcao is None:

        log_local(f"Comando desconhecido: '{comando}'")

        enviar_resultado_comando(
            comando_id, comando, "erro",
            f"Comando '{comando}' não reconhecido pelo agente."
        )

        return

    try:

        mensagem = funcao()

        enviar_resultado_comando(comando_id, comando, "sucesso", mensagem)

    except Exception as e:

        log_local(f"Erro executando comando '{comando}': {e}")

        enviar_resultado_comando(comando_id, comando, "erro", str(e))


def verificar_comandos_pendentes():
    """
    Verifica se há comandos pendentes, respeitando o intervalo mínimo
    entre checagens (não consulta o banco a cada ciclo do loop).
    """

    global _ultima_checagem_comandos

    agora = time.time()

    if agora - _ultima_checagem_comandos < INTERVALO_CHECAGEM_COMANDOS:
        return

    _ultima_checagem_comandos = agora

    comandos = buscar_comandos_pendentes(CONFIG.get("hostname", HOSTNAME))

    for comando_item in comandos:
        executar_comando(comando_item)


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

            rede = obter_qualidade_rede_atual()

            log_local(f"CPU {cpu}% | RAM {memoria_ram}%")

            enviar_heartbeat(
                cpu=cpu,
                memoria_ram=memoria_ram,
                chrome_aberto=chrome_aberto,
                capture_aberto=capture_aberto,
                status="online",
                ping_ms=rede["ping_ms"],
                perda_pacotes_pct=rede["perda_pacotes_pct"],
                ping_host=rede["ping_host"]
            )

            # Verifica se há comandos remotos pendentes (restart_chrome,
            # shutdown, etc.). Throttled internamente - não consulta
            # o banco a cada ciclo.
            verificar_comandos_pendentes()

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