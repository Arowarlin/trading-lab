# Retención de los JSONL diarios de Vector: borra all-*.jsonl de más de N días.
# No toca alerts.jsonl (el relevo guarda su offset). Lo llama heartbeat_pc.ps1.
param(
    [string]$Root = "E:\trading-lab",
    [int]$Days = 14
)

$ErrorActionPreference = "Continue"
$dir = Join-Path $Root "logs\vector"
if (-not (Test-Path $dir)) { return }

$limit = (Get-Date).AddDays(-[Math]::Max(1, $Days))
Get-ChildItem $dir -Filter "all-*.jsonl" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $limit } |
    Remove-Item -Force -ErrorAction SilentlyContinue
