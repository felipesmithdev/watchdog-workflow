"""
Watchdog OneConnect - ponto de entrada.

Monitora CPU/RAM, mantém Chrome e 4KCaptureUtility saudáveis, reporta
heartbeat + qualidade de rede, e executa comandos remotos vindos do
Lovable. Toda a configuração operacional (sala, URL, limites) vem do
banco - nada fica em arquivo local.
"""

import time
import traceback

import psutil

from api_client import buscar_configuracao_remota, enviar_evento, enviar_heartbeat
from browsers import abrir_chrome
from commands import verificar_comandos_pendentes
from config_manager import get_config, set_config
from logger import log_local
from network import obter_qualidade_rede_atual
from processes import finalizar_processos, verificar_processos_ativos
from settings import HOSTNAME


def iniciar_watchdog():

    # 1. Descobrir hostname (já feito na inicialização de settings.py)
    # 2/3/4. Consultar banco e baixar configuração completa
    set_config(buscar_configuracao_remota(HOSTNAME))
    config = get_config()

    log_local("====================================")
    log_local("WATCHDOG INICIADO")
    log_local(f"Hostname: {config['hostname']}")
    log_local(f"Hospital: {config['hospital']}")
    log_local(f"Sala: {config['sala']}")
    log_local(f"URL: {config['url']}")
    log_local("====================================")

    segundos_cpu_alta = 0

    # 5. Iniciar monitoramento
    while True:

        try:

            config = get_config()

            limite_cpu = config["limite_cpu"]
            tempo_critico = config["tempo_critico"]
            tempo_pausado = config["tempo_pausado"]

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
            # kill_edge, shutdown, etc.). Throttled internamente - não
            # consulta o banco a cada ciclo.
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
                        "url": get_config()["url"]
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


if __name__ == "__main__":
    iniciar_watchdog()
