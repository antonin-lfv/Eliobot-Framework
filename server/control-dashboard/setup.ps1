$ErrorActionPreference = "Stop"
# Le lanceur Python vérifie Docker Desktop et enregistre le vrai système hôte.
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 "$PSScriptRoot/setup.py" @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$PSScriptRoot/setup.py" @args
} else {
    Write-Error "Installer Python 3.11 ou plus récent, puis relancer ce script."
    exit 1
}
exit $LASTEXITCODE
