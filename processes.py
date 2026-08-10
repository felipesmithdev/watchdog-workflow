"""Encerramento e verificação de processos monitorados pelo watchdog."""

import psutil

from api_client import enviar_evento
from logger import log_local


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
