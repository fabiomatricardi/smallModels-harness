# Launch llama-server for the LFM3-1.7B distill benchmark.
#
# Notes:
#   -np 1          one slot: the whole -c context goes to the single request
#                  (auto/4 would silently split 16384 into 4096-token slots)
#   -ctk/-ctv q8_0 quantized KV cache: ~half the memory, negligible quality loss
#   --reasoning-budget  thinking tokens are capped so they cannot eat the context
#                  or the answer budget (0 = no thinking, 512 = thinking sweep)
param(
    [int]$Port = 8080,
    [int]$Ctx = 16384,
    [int]$Ngl = 999,
    [int]$Np = 1,
    [string]$Ctk = "q8_0",
    [string]$Ctv = "q8_0",
    [int]$ReasoningBudget = 0,
    [string]$Fa = "on",
    [string]$ModelFile = "LFM-3-Coder-Claude-Distill.Q5_K_M.gguf"
)

$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "llamaCPP\llama-server.exe"
$model = Join-Path $root "llamaCPP\models\$ModelFile"
$log = Join-Path $PSScriptRoot "server.log"

if (-not (Test-Path $exe)) { throw "llama-server.exe not found at $exe" }
if (-not (Test-Path $model)) { throw "model not found at $model" }

$srvArgs = @('-m', $model, '-c', $Ctx, '--host', '127.0.0.1', '--port', $Port,
          '-ngl', $Ngl, '-np', $Np, '--jinja', '--no-webui',
          '-ctk', $Ctk, '-ctv', $Ctv, '-fa', $Fa,
          '--reasoning-budget', $ReasoningBudget)

Write-Host "starting llama-server on :$Port  ctx=$Ctx  np=$Np  kv=$Ctk/$Ctv  fa=$Fa  thinking_budget=$ReasoningBudget"
$p = Start-Process -FilePath $exe -ArgumentList $srvArgs `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru -WindowStyle Hidden

$p.Id | Set-Content (Join-Path $PSScriptRoot "server.pid")
Write-Host "pid $($p.Id)  log $log"

for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $h = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($h.status -eq "ok") {
            Write-Host "server ready ($([math]::Round($i/2,1))s)"
            exit 0
        }
    } catch { }
}
throw "server did not become ready - see $log"