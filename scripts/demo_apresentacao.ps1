param(
    [ValidateRange(1024, 65535)][int]$Port = 55452
)

$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
$demoContainer = 'automatize-demo-henrique-20261110'
$demoDatabase = 'automatize_demo_presentation_test'
$demoLabel = 'presentation-demo-20261110'
$demoPython = Join-Path $demoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    $demoCommonGit = (& git -C $demoRoot rev-parse --path-format=absolute --git-common-dir).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Repositorio Git indisponivel.' }
    $demoPython = Join-Path (Split-Path -Parent $demoCommonGit) '.venv/Scripts/python.exe'
}
if (-not (Test-Path -LiteralPath $demoPython)) { throw 'Prepare a venv do projeto antes da demonstracao.' }

$demoCreated = $false
$demoSaved = @{}
foreach ($demoName in @('TEST_DATABASE_URL','DATABASE_URL','SUPABASE_URL','SUPABASE_KEY','CORS_ORIGINS')) {
    $demoSaved[$demoName] = [Environment]::GetEnvironmentVariable($demoName, 'Process')
}
try {
    $demoExisting = & docker ps -aq --filter "name=^/$demoContainer$"
    if ($LASTEXITCODE -ne 0) { throw 'Inicie o Docker Desktop antes da demonstracao.' }
    if ($demoExisting) {
        $demoActualLabel = (& docker inspect --format '{{index .Config.Labels "automatize.audit"}}' $demoContainer).Trim()
        $demoActualPort = (& docker port $demoContainer 5432/tcp).Trim()
        if ($demoActualLabel -ne $demoLabel -or $demoActualPort -ne "127.0.0.1:$Port") {
            throw 'O container existente nao corresponde ao ambiente de demonstracao.'
        }
    } else {
        & docker run --detach --rm --name $demoContainer --label "automatize.audit=$demoLabel" `
            --publish "127.0.0.1:${Port}:5432" --env "POSTGRES_DB=$demoDatabase" `
            --env POSTGRES_HOST_AUTH_METHOD=trust postgres:17 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel iniciar PostgreSQL descartavel.' }
        $demoCreated = $true
    }
    $demoReady = $false
    $demoDeadline = [DateTime]::UtcNow.AddSeconds(30)
    $demoProbeCode = -1
    while ([DateTime]::UtcNow -lt $demoDeadline) {
        $demoProbe = & docker exec $demoContainer pg_isready -U postgres -d $demoDatabase 2>&1
        $demoProbeCode = $LASTEXITCODE
        if ($demoProbeCode -eq 0) { $demoReady = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $demoReady) { throw "PostgreSQL local indisponivel; codigo de prontidao $demoProbeCode." }

    # Only a disposable IPv4 loopback database. Never load a shared .env target.
    $env:TEST_DATABASE_URL = "postgresql+psycopg2://postgres@127.0.0.1:${Port}/$demoDatabase"
    $env:DATABASE_URL = $env:TEST_DATABASE_URL
    $env:SUPABASE_URL = ''
    $env:SUPABASE_KEY = ''
    $env:CORS_ORIGINS = '[]'
    Push-Location -LiteralPath $demoRoot
    try {
        Write-Output 'DEMONSTRACAO LOCAL: PostgreSQL real, Storage simulado, nenhum Supabase compartilhado.'
        & $demoPython -m pytest tests/integration/test_apresentacao_demo.py -q -s --tb=short -p no:cacheprovider
        if ($LASTEXITCODE -ne 0) { throw 'O ensaio falhou; nao declarar aprovacao.' }
    } finally { Pop-Location }
} finally {
    foreach ($demoName in $demoSaved.Keys) {
        [Environment]::SetEnvironmentVariable($demoName, $demoSaved[$demoName], 'Process')
    }
    if ($demoCreated) {
        & docker stop $demoContainer | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Encerre manualmente apenas o container local desta demonstracao.' }
    }
}
