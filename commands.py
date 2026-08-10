"""
Comandos remotos: o watchdog consulta periodicamente o banco por
comandos pendentes para este hostname, executa e envia o resultado
de volta.

NOTA: controle de dispositivo COM ("bridge...") fica para uma próxima
etapa - combinado, não implementado agora.
"""

import subprocess
import time

from api_client import buscar_comandos_pendentes, enviar_evento
from browsers import abrir_chrome, abrir_edge
from config_manager import get_config
from logger import log_local
from processes import finalizar_processo_por_nome
from settings import HOSTNAME, INTERVALO_CHECAGEM_COMANDOS, PADRAO_TEMPO_PAUSADO

_ultima_checagem_comandos = 0.0


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


# ----------------------------------------------------------
# Comandos: CHROME
# ----------------------------------------------------------

def comando_kill_chrome():
    """Fecha apenas o Chrome, sem reabrir."""

    encontrado = finalizar_processo_por_nome(
        "chrome.exe", "chrome_fechado", "Chrome encerrado (comando remoto)"
    )

    if encontrado:
        return "Chrome encerrado."

    return "Chrome não estava em execução."


def comando_open_chrome():
    """Abre o Chrome na URL configurada, sem fechar nada antes."""

    abrir_chrome()

    return "Chrome aberto na URL configurada."


def comando_restart_chrome():
    """Reinicia apenas o Chrome (mantém o 4KCaptureUtility rodando)."""

    finalizar_processo_por_nome("chrome.exe", "chrome_fechado", "Chrome encerrado (comando remoto)")

    tempo_pausado = get_config().get("tempo_pausado", PADRAO_TEMPO_PAUSADO)

    log_local(f"Aguardando {tempo_pausado}s antes de reabrir (comando remoto)...")

    time.sleep(tempo_pausado)

    abrir_chrome()

    return "Chrome reiniciado com sucesso via comando remoto."


# ----------------------------------------------------------
# Comandos: EDGE
# ----------------------------------------------------------

def comando_kill_edge():
    """Fecha apenas o Edge, sem reabrir."""

    encontrado = finalizar_processo_por_nome(
        "msedge.exe", "edge_fechado", "Edge encerrado (comando remoto)"
    )

    if encontrado:
        return "Edge encerrado."

    return "Edge não estava em execução."


def comando_open_edge():
    """Abre o Edge na URL configurada, sem fechar nada antes."""

    abrir_edge()

    return "Edge aberto na URL configurada."


# ----------------------------------------------------------
# Comandos: SISTEMA (WINDOWS)
# ----------------------------------------------------------

def comando_shutdown():
    """Desliga a máquina Windows. Dá 5s de margem para o resultado ser enviado antes."""

    subprocess.Popen(["shutdown", "/s", "/t", "5"])

    return "Comando de desligamento enviado. A máquina será desligada em 5 segundos."


def comando_reboot():
    """Reinicia a máquina Windows. Dá 5s de margem para o resultado ser enviado antes."""

    subprocess.Popen(["shutdown", "/r", "/t", "5"])

    return "Comando de reinicialização enviado. A máquina será reiniciada em 5 segundos."


# Tabela de comandos suportados -> função executora.
# Adicionar novos comandos aqui é o único passo necessário para expandir.
COMANDOS_DISPONIVEIS = {

    # Chrome
    "kill_chrome": comando_kill_chrome,
    "open_chrome": comando_open_chrome,
    "restart_chrome": comando_restart_chrome,

    # Edge
    "kill_edge": comando_kill_edge,
    "open_edge": comando_open_edge,

    # Sistema
    "shutdown": comando_shutdown,
    "desligar_maquina": comando_shutdown,  # alias em português
    "reboot": comando_reboot,
    "reiniciar_maquina": comando_reboot,  # alias em português
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

    hostname = get_config().get("hostname", HOSTNAME)
    comandos = buscar_comandos_pendentes(hostname)

    for comando_item in comandos:
        executar_comando(comando_item)
