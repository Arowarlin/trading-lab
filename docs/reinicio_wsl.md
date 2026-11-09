# Reanudación tras el reinicio

Fecha: 2026-11-09.

## Estado

- WSL2: WSL 3.0.3, kernel 6.18.54.1, Ubuntu 24.04.5 LTS, usuario `pc`
  (UID 1000, sudo), versión predeterminada 2.
- `C:\Users\PC\.wslconfig` activa `networkingMode=mirrored`; LM Studio está en
  `http://127.0.0.1:1234/v1` con `qwen3.8-27b`.
- Trading-R1 0.1.1 en `/home/pc/.venv-r1`; `TR1_VLLM_*`, `~/.venv-r1/bin` y
  `~/.bun/bin` (bun 1.4.4 nativo) quedan en `~/.bashrc` y `~/.profile`. TUI
  verificada.
- La tarea `TradingLab-Resume` reabre Windows Terminal y la sesión exacta
  `ses_e5220563affelHrJU9DmgfjCb3` de OpenCode al iniciar sesión, como máximo
  una vez por arranque. Lanza `scripts/resume_terminal.ps1` con `-File` para
  que `wt.exe` no parta el comando por los `;`. Queda registrada: quitarla
  requiere una consola elevada
  (`Unregister-ScheduledTask -TaskName TradingLab-Resume -Confirm:$false`).
- `scripts/reboot_after_download.ps1` espera a que termine la descarga del MoE y
  programa el reinicio con 120 s de aviso; si el modelo no aparece, no reinicia.
  Si hay que cancelar: `shutdown /a`.
- Los datos están en `E:\trading-lab\data\lab.db` y las cachés en
  `E:\trading-lab\data\cache`; no están en la unidad del sistema.

## Instalación realizada

```powershell
wsl --install -d Ubuntu-24.04 --no-launch --web-download
```

El OOBE de Ubuntu creó el usuario `pc`. Después, dentro de Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y unzip
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://bun.sh/install | bash
uv venv --python 3.12 ~/.venv-r1
uv pip install --python ~/.venv-r1/bin/python trading-r1
```

Configuración del perfil local contra LM Studio:

```bash
export TR1_PROFILE=vllm
export TR1_VLLM_BASE_URL=http://127.0.0.1:1234/v1
export TR1_VLLM_MODEL=qwen3.8-27b
trading-r1 --profile vllm
```

Verificación: `/v1/models` y una inferencia real devolvieron HTTP 200; la TUI
quedó corriendo en una pestaña de Windows Terminal. No se configuró ninguna
clave Tauric ni se enviaron órdenes.

Para entrar manualmente: `wsl -d Ubuntu-24.04`.

## Runner pre-market

Con el backend de Trading-R1 vivo (TUI abierta o `trading-r1 serve`):

```powershell
.\scripts\trading_r1_premarket.ps1 -PreflightOnly
.\scripts\trading_r1_premarket.ps1 -Send
```

El runner genera los datos con `lab premarket --no-llm`, pide a Trading-R1
solo la redacción (sin web ni herramientas), guarda Markdown y JSON en
`reports/premarket/` y, con `-Send`, envía el Markdown con
`lab telegram send`. No envía órdenes.
