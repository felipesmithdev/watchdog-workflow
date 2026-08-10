"""
Normalização e estado em memória da configuração do dispositivo.

Este módulo é o "dono" do dicionário CONFIG. Nenhum outro módulo deve
guardar sua própria cópia dele - todos leem via get_config() e
atualizam via set_config(), o que evita um problema clássico do
Python: reatribuir uma variável importada de outro módulo
(`outro_modulo.CONFIG = {...}`) não propaga como se espera. Usando
funções em vez de uma variável importada diretamente, o estado fica
sempre consistente entre módulos.
"""

from logger import log_local
from settings import (
    PADRAO_CHROME_PATH,
    PADRAO_LIMITE_CPU,
    PADRAO_TEMPO_CRITICO,
    PADRAO_TEMPO_PAUSADO,
)

# Configuração ativa em memória (preenchida por api_client.buscar_configuracao_remota
# e armazenada aqui via set_config).
_config = {}


def get_config():
    """Retorna a configuração ativa em memória."""
    return _config


def set_config(nova_config):
    """Substitui a configuração ativa em memória."""

    global _config
    _config = nova_config


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
