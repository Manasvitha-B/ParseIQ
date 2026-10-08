$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendRoot = Join-Path $projectRoot 'frontend'
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found at $python. Create the project's .venv first."
}
if (-not $npm) {
    throw 'npm.cmd was not found. Install Node.js and make npm available on PATH.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'))) {
    throw 'Frontend dependencies are missing. Run npm install once in the frontend folder.'
}

function Start-ParseIQBackend {
    Write-Host 'Starting ParseIQ backend at http://127.0.0.1:8000'
    Start-Process -FilePath $python -ArgumentList @('-m', 'backend.run') `
        -WorkingDirectory $projectRoot -PassThru -NoNewWindow
}

function Start-ParseIQFrontend {
    Write-Host 'Starting ParseIQ frontend at http://127.0.0.1:5173'
    Start-Process -FilePath $npm -ArgumentList @('run', 'dev', '--', '--host', '127.0.0.1') `
        -WorkingDirectory $frontendRoot -PassThru -NoNewWindow
}

function Stop-ProcessTree($process) {
    if ($process -and -not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F *> $null
    }
}

$backendProcess = $null
$frontendProcess = $null
$backendRestarts = 0
$frontendRestarts = 0
try {
    $backendProcess = Start-ParseIQBackend
    $frontendProcess = Start-ParseIQFrontend
    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
            $ui = Invoke-WebRequest -Uri 'http://127.0.0.1:5173' -TimeoutSec 2 -UseBasicParsing
            if ($health.status -eq 'ok' -and $ui.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    if ($ready) { Start-Process 'http://127.0.0.1:5173' }
    else { Write-Warning 'Services are still starting. Open http://127.0.0.1:5173 when ready.' }
    Write-Host 'Both services are running. Upload as many documents as needed; press Ctrl+C to stop.'
    Write-Host 'The launcher will restart a service if its process exits.'

    while ($true) {
        Start-Sleep -Seconds 2
        if ($backendProcess.HasExited) {
            $backendRestarts++
            if ($backendRestarts -gt 5) { throw 'Backend exited repeatedly. Check the backend error shown above.' }
            Write-Warning "Backend stopped; restarting ($backendRestarts/5)."
            $backendProcess = Start-ParseIQBackend
        }
        if ($frontendProcess.HasExited) {
            $frontendRestarts++
            if ($frontendRestarts -gt 5) { throw 'Frontend exited repeatedly. Check the frontend error shown above.' }
            Write-Warning "Frontend stopped; restarting ($frontendRestarts/5)."
            $frontendProcess = Start-ParseIQFrontend
        }
    }
}
finally {
    Stop-ProcessTree $frontendProcess
    Stop-ProcessTree $backendProcess
}
