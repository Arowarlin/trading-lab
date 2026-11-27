#!/usr/bin/env bash
# Lanza tl_guard.py con el Python del venv del proyecto (Linux o Windows/Git Bash)
# o, si no existe, con el del sistema. Si no hay ningún Python, no bloquea nada.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
for py in "$root/.venv/bin/python" "$root/.venv/Scripts/python.exe" python3 python; do
  if command -v "$py" >/dev/null 2>&1; then
    exec "$py" "$here/tl_guard.py" "$@"
  fi
done
exit 0
