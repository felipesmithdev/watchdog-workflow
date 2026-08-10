# Watchdog OneConnect

Agente de monitoramento e gerenciamento remoto para os PCs KVM da
OneConnect. Monitora CPU/RAM, mantém Chrome e 4KCaptureUtility
saudáveis, mede qualidade de rede, e executa comandos remotos vindos
do painel Lovable. Toda configuração operacional (sala, URL, limites)
vem do banco - nada fica em arquivo local.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Ponto de entrada e loop principal |
| `settings.py` | Constantes (endpoint, API key, padrões, intervalos) |
| `logger.py` | Log em console + arquivo |
| `config_manager.py` | Normalização e estado em memória da configuração |
| `api_client.py` | Toda comunicação HTTP com o Lovable |
| `browsers.py` | Abrir Chrome / Edge |
| `processes.py` | Encerrar/verificar processos (Chrome, Edge, 4K) |
| `network.py` | Diagnóstico de latência e perda de pacotes |
| `commands.py` | Comandos remotos e tabela de despacho |

## Rodando localmente

```bash
pip install -r requirements.txt
python main.py
```

## Gerando o .exe

```
build.bat
```

Gera `dist\watchdog.exe` - um único executável, mesmo com o projeto
dividido em vários arquivos (o PyInstaller segue os imports
automaticamente).

## Comandos remotos disponíveis

| Comando | Ação |
|---|---|
| `kill_chrome` | Fecha o Chrome |
| `open_chrome` | Abre o Chrome na URL configurada |
| `restart_chrome` | Fecha + espera + reabre o Chrome |
| `kill_edge` | Fecha o Edge |
| `open_edge` | Abre o Edge na URL configurada |
| `shutdown` / `desligar_maquina` | Desliga o Windows |
| `reboot` / `reiniciar_maquina` | Reinicia o Windows |

Contrato assumido com o Lovable para comandos (documentado em
`api_client.py` e `commands.py` - ajustar se o backend expuser
diferente):

```
GET  ENDPOINT_URL?hostname=X&tipo=comandos
-> {"comandos": [{"id": "abc123", "comando": "restart_chrome"}]}

POST ENDPOINT_URL  (resultado)
-> {"tipo": "resultado_comando", "comando_id": ..., "comando": ...,
    "status": "sucesso"|"erro", "mensagem": ...}
```

## Próxima etapa (combinada, não implementada)

Controle de dispositivo COM ("bridge...") - habilitar/desabilitar via
PowerShell (`Get-PnpDevice` / `Enable-PnpDevice` / `Disable-PnpDevice`),
exige o agente rodando como Administrador.
