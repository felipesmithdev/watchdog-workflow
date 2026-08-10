"""Log simples em console + arquivo, usado por todos os outros módulos."""

from datetime import datetime

ARQUIVO_LOG = "watchdog.log"


def log_local(msg):
    """Escreve uma mensagem no console e no arquivo watchdog.log."""

    texto = f"[{datetime.now()}] {msg}"

    print(texto)

    with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
        f.write(texto + "\n")
