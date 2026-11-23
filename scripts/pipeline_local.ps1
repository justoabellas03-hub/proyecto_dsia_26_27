# Pipeline diario en local: python -m pipeline_dsia todo -> commit y push.
#
# Se ejecuta con el Programador de tareas de Windows (ver README, sección Automatización).
# Corre en local porque en GitHub Actions fallaba la descarga de los datos de mercado (Brent, EUR/USD).
#
# Prueba manual:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\pipeline_local.ps1

$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force -Path logs | Out-Null
Start-Transcript -Path "logs\pipeline_local.log" -Append | Out-Null

# uv: el del PATH o, si la tarea no lo encuentra, el de la instalación por defecto
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }

Write-Output "=== Pipeline local $(Get-Date -Format 'yyyy-MM-dd HH:mm') ==="

# 1. Traer lo último de GitHub (por si se ha subido algo desde otro sitio)
git pull --no-rebase --autostash

# 2. Todo el flujo: ingesta -> entrenar (los lunes) -> predecir -> métricas.
#    Si un paso falla, el programa sigue con el siguiente y al final muestra un resumen.
& $uv run python -m pipeline_dsia todo
if ($LASTEXITCODE -ne 0) { Write-Warning "Algún paso ha fallado (código $LASTEXITCODE): revisa el resumen" }

# 3. Guardar el histórico y el modelo en el repositorio
git add historico/ models/
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "datos: pipeline diario $(Get-Date -Format 'yyyy-MM-dd')"
    git push
} else {
    Write-Output "Sin cambios que subir"
}

Stop-Transcript | Out-Null
