# L0 · Estado (solo lectura)

Fecha de ejecución: 2026-11-26

## Paso 1

Comando:

```
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "lab|pytest|discovery" } | Select-Object ProcessId, CommandLine
```

Salida:

```
ProcessId CommandLine
--------- -----------
    24856 "C:\Program Files\WindowsApps\Claude_6.28899.6.0_x64__pzs8sxrjxfjjc\app\Claude.exe" --type=renderer --user...
      712 "C:\Program Files\WindowsApps\Claude_6.28899.6.0_x64__pzs8sxrjxfjjc\app\Claude.exe" --type=renderer --user...
     3772 "E:\trading-lab\.venv\Scripts\lab.exe" web --no-open --port 8420
     9060 "E:\trading-lab\.venv\Scripts\python.exe" "E:\trading-lab\.venv\Scripts\lab.exe" web --no-open --port 8420
    26304 "E:\trading-lab\.venv\Scripts\python.exe" "E:\trading-lab\.venv\Scripts\lab.exe" web --no-open --port 8420
     3732 "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.EXE" -NoLogo -NoProfile -NonInteractive -Command "G...
```

Nota: en las entradas largas la consola trunca la columna CommandLine con `...`.

## Paso 2

Comando:

```
Get-ChildItem E:\trading-lab\.orquestador\locks -ErrorAction SilentlyContinue | Select-Object Name, LastWriteTime
```

Salida:

```
Name     LastWriteTime
----     -------------
released 26/11/2026 1:47:52 p. m.
```

## Paso 3

Comando:

```
git -C E:\trading-lab log --oneline -5 ; git -C E:\trading-lab tag --list "edge*" "robust*" "motor*"
```

Salida:

```
b88b737 motor-flat: M3/M4b - avisos y estado
19b32c0 motor-flat: M5 - cierre y documentacion
e55392a wf-tf: W5 - aviso
c581d1f wf-tf: W4 - cierre
82f1fb2 motor-flat: M4b - H-2026-013 v2 para verificar
edge1
edge2
motor-flat
motor-flat-pre
robust-1
robust-pre
```
