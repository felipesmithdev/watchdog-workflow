"""
Abertura de navegadores (Chrome / Edge) na sala configurada.

Ambas as funções reaproveitam o mesmo campo 'url' (a URL da sala)
vindo do banco - o operador escolhe em qual navegador abrir, não em
qual sala. Nenhuma delas fecha nada antes de abrir; quem quiser
"reiniciar" (fechar + abrir) usa os comandos remotos combinados
(ex: restart_chrome, em commands.py).
"""

import subprocess

from api_client import buscar_configuracao_remota
from config_manager import get_config, set_config
from logger import log_local
from settings import HOSTNAME


def abrir_chrome():
    """
    Abre o Chrome na sala configurada. Assim como no script original,
    a configuração é recarregada antes de abrir, garantindo que a
    URL/caminho mais recentes (definidos no banco) sejam usados mesmo
    que tenham sido alterados após o início do watchdog.
    """

    try:

        set_config(buscar_configuracao_remota(HOSTNAME))
        config = get_config()

        url_sala = config["url"]
        chrome_path = config["chrome_path"]

        if url_sala.strip() == "":

            log_local("Nenhuma URL configurada.")

            subprocess.Popen(
                ["cmd", "/c", "start", "chrome"]
            )

            return

        log_local(f"Abrindo URL no Chrome: {url_sala}")

        subprocess.Popen([
            chrome_path,
            "--new-window",
            url_sala
        ])

    except Exception as e:

        log_local(f"Erro abrindo Chrome: {e}")


def abrir_edge():
    """
    Abre o Edge na mesma URL da sala. Diferente do Chrome, não
    dependemos de um caminho de executável configurado - o Edge é
    componente nativo do Windows 10/11 e sempre pode ser chamado por
    'start msedge', mesmo sem saber onde exatamente ele está
    instalado (o caminho varia entre Program Files e
    Program Files (x86) dependendo da versão/instalação).
    """

    try:

        set_config(buscar_configuracao_remota(HOSTNAME))
        config = get_config()

        url_sala = config["url"]

        if url_sala.strip() == "":

            log_local("Nenhuma URL configurada.")

            subprocess.Popen(
                ["cmd", "/c", "start", "msedge"]
            )

            return

        log_local(f"Abrindo URL no Edge: {url_sala}")

        subprocess.Popen([
            "cmd", "/c", "start", "msedge", url_sala
        ])

    except Exception as e:

        log_local(f"Erro abrindo Edge: {e}")
