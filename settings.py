"""
Constantes fixas do agente.

Diferente da configuração operacional (sala, URL, limites de CPU etc.,
que vêm do banco), estes valores identificam ONDE o agente busca
informações e como ele se comporta por padrão - são parte do próprio
agente, não do dispositivo monitorado.
"""

import socket

HOSTNAME = socket.gethostname()

# Endpoint único do Lovable, usado tanto para ler configuração quanto
# para enviar heartbeat/eventos/comandos. O que muda é o VERBO HTTP e
# a forma de envio dos dados, não a URL:
#
#   GET  ENDPOINT_URL?hostname=X            -> leitura de configuração
#   GET  ENDPOINT_URL?hostname=X&tipo=comandos -> leitura de comandos pendentes
#   POST ENDPOINT_URL                        -> heartbeat, eventos e resultado de comandos
#
ENDPOINT_URL = "https://flux-heartbeat.lovable.app/api/public/ingest/2a3c35b4-b740-4fe0-b216-c7b2c50a137e"
API_KEY = "pk_0e55c97681154727a54be6541f88db186fec32bcdb1e484e86b043913cbbe495"

# Intervalo entre tentativas de busca de configuração, caso o banco
# esteja indisponível na inicialização.
INTERVALO_RETRY_CONFIG = 15  # segundos

# Intervalo entre medições de qualidade de rede (não medir a cada
# ciclo do loop principal).
INTERVALO_CHECAGEM_REDE = 10  # segundos

# Intervalo entre verificações de comandos remotos pendentes.
INTERVALO_CHECAGEM_COMANDOS = 5  # segundos

# Valores padrão de segurança, usados SOMENTE se o banco não retornar
# algum desses campos (mesmo comportamento defensivo que o
# carregar_config() original tinha para "url" e "chrome_path").
PADRAO_CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
PADRAO_LIMITE_CPU = 75
PADRAO_TEMPO_CRITICO = 10
PADRAO_TEMPO_PAUSADO = 30
