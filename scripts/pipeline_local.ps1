# Pipeline diario en local: ingesta -> (los lunes) entrenar -> predecir -> commit y push.
#
# Se ejecuta con el Programador de tareas de Windows (ver README, sección Automatización).
# Corre en local porque la API del Ministerio rechaza las conexiones desde GitHub Actions.
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
git pull --rebase --autostash

# 2. Ingesta: si falla, seguimos con el histórico que haya
& $uv run python -m pipeline_dsia.ingesta
if ($LASTEXITCODE -ne 0) { Write-Warning "Ingesta fallida (código $LASTEXITCODE): se usa el último histórico" }

# 3. Entrenar los lunes o si todavía no hay modelo
if ((Get-Date).DayOfWeek -eq "Monday" -or -not (Test-Path "models\modelo.joblib")) {
    & $uv run python -m pipeline_dsia.entrenar
} else {
    Write-Output "Hoy no toca reentrenar"
}

# 4. Predecir mañana
& $uv run python -m pipeline_dsia.predecir

# 5. Guardar el histórico y el modelo en el repositorio
git add historico/ models/
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "datos: pipeline diario $(Get-Date -Format 'yyyy-MM-dd')"
    git push
} else {
    Write-Output "Sin cambios que subir"
}

Stop-Transcript | Out-Null
