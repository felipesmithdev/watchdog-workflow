"""
Diagnóstico de qualidade de conexão (latência e perda de pacotes).

Mede sem depender de ICMP (o comando 'ping' do Windows tem parsing
frágil dependendo do idioma do SO, e ICMP costuma ser bloqueado em
redes hospitalares). Em vez disso, medimos o tempo de uma conexão TCP
direta - mais confiável e testa exatamente a rota que importa: até o
servidor da sala OneConnect.
"""

import socket
import time
import urllib.parse

from config_manager import get_config
from logger import log_local
from settings import INTERVALO_CHECAGEM_REDE

_ultima_checagem_rede = 0.0
_ultimo_resultado_rede = {
    "ping_host": None,
    "ping_ms": None,
    "perda_pacotes_pct": None
}


def obter_host_para_ping():
    """
    Determina qual host testar. Prioriza o domínio da própria URL da
    sala (mede a rota real que importa); usa um host público
    confiável como fallback caso a URL não esteja configurada.
    """

    url_sala = get_config().get("url", "")

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
