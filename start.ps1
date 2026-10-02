$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$pythonPath = Join-Path (Split-Path $appRoot -Parent) 'nba-player-stats-mcp\.venv\Scripts\python.exe'
$healthy = $false
try { $healthy = (Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2).ok } catch {}
if (-not $healthy) {
    Start-Process -FilePath $pythonPath -ArgumentList ('"' + (Join-Path $appRoot 'server.py') + '"') -WorkingDirectory $appRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $appRoot 'data\server.log') -RedirectStandardError (Join-Path $appRoot 'data\server-error.log')
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { if ((Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 1).ok) { $healthy=$true; break } } catch {}
    }
}
if ($healthy) { Start-Process 'http://127.0.0.1:8765' } else { throw 'Courtside failed to start. See data/server-error.log.' }
