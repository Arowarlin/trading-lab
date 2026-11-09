# Reanudación tras el reinicio

Fecha: 2026-11-09.

## Estado tras el reinicio

- `Microsoft-Windows-Subsystem-Linux` y `VirtualMachinePlatform`: **Enabled**.
- `wsl --status` devuelve "no está instalado" (exit 50): falta
  `wsl --install -d Ubuntu`.
- La tarea `TradingLab-Resume` reabre Windows Terminal y la sesión exacta
  `ses_e5220563affelHrJU9DmgfjCb3` de OpenCode al iniciar sesión, como máximo
  una vez por arranque. Lanza `scripts/resume_terminal.ps1` con `-File` para
  que `wt.exe` no parta el comando por los `;`. Queda registrada: quitarla
  requiere una consola elevada
  (`Unregister-ScheduledTask -TaskName TradingLab-Resume -Confirm:$false`).
- `scripts/reboot_after_download.ps1` espera a que termine la descarga del MoE y
programa el reinicio con 120 s de aviso; si el modelo no aparece, no reinicia.
Si hay que cancelar: `shutdown /a`.

La descarga de Qwen3-30B-A3B se reanuda con:
  `lms get qwen/qwen3-30b-a3b@q4_k_m -y --gguf`.
- Los datos están en `E:\trading-lab\data\lab.db` y las cachés en
  `E:\trading-lab\data\cache`; no están en la unidad del sistema.

## Después del reinicio

```powershell
wsl --status
wsl --install -d Ubuntu
wsl --update
wsl --set-default-version 2
```

Dentro de Ubuntu:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.12 ~/.venv-r1
uv pip install --python ~/.venv-r1/bin/python trading-r1
```

Para el perfil local, apuntar Trading-R1 a LM Studio:

```bash
export TR1_VLLM_BASE_URL=http://<IP-de-Windows>:1234/v1
export TR1_VLLM_MODEL=qwen3.8-27b
~/.venv-r1/bin/trading-r1 --profile vllm
```

Si el perfil `vllm` no acepta LM Studio directamente, usar el fallback nativo:

```powershell
lab premarket --tickers SPY,QQQ,NVDA --out logs/premarket/premarket.md
```

No se deben enviar órdenes ni activar bots durante la comprobación.
