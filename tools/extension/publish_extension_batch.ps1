<#
.SYNOPSIS
  Drain Chrome-extension approvals into local CSVs and push to git.

.DESCRIPTION
  Safe end-to-end runner. Pulls the latest CSVs from GitHub first so the
  daily price-update automation's CSV writes are never clobbered, then runs
  the two publishers, then commits and pushes if anything changed.

  Order of operations (matches what `automated_cigar_price_system.py` does
  for git, applied to the extension-specific publishers):

    1. git pull --rebase            (abort on conflict)
    2. publish_extension_approvals.py  -> master CSV+DB and per-retailer CSVs
    3. sync_new_retailer_queue.py      -> tools/ai/new_retailer_queue.txt
    4. git add ... (only files touched by the publishers)
    5. git commit + git push

  Env:
    ADMIN_SECRET_KEY (required)  - same key the website uses
    EXTENSION_API_BASE           - optional override; defaults to
                                   https://cigarpricescout.com

.PARAMETER DryRun
  Run both publishers in --dry-run mode (no writes, no commit/push).

.PARAMETER SkipPush
  Run the publishers and commit, but do not push to origin.

.EXAMPLE
  pwsh tools/extension/publish_extension_batch.ps1
  pwsh tools/extension/publish_extension_batch.ps1 -DryRun
#>
param(
    [switch]$DryRun,
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..\..")
Set-Location $projectRoot

function Write-Step {
    param([string]$msg)
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}

function Fail {
    param([string]$msg)
    Write-Host "FATAL: $msg" -ForegroundColor Red
    exit 1
}

if (-not $env:ADMIN_SECRET_KEY) {
    Fail "ADMIN_SECRET_KEY is not set. Set it before running."
}

# ── 1. git pull --rebase ──────────────────────────────────────────────
Write-Step "git pull --rebase"
$pullOutput = git pull --rebase 2>&1
Write-Host $pullOutput
if ($LASTEXITCODE -ne 0) {
    # Try to detect a rebase-in-progress and abort cleanly.
    if (Test-Path ".git/rebase-merge" -or Test-Path ".git/rebase-apply") {
        Write-Host "Rebase appears to be in progress; aborting." -ForegroundColor Yellow
        git rebase --abort | Out-Null
    }
    Fail "git pull --rebase failed. Resolve manually, then re-run."
}

# Sanity: ensure we're on a tracked branch (so push won't surprise us later).
$branch = git rev-parse --abbrev-ref HEAD
Write-Host "On branch: $branch"

# ── 2. publish_extension_approvals.py ─────────────────────────────────
Write-Step "publish_extension_approvals.py"
$publisherArgs = @()
if ($DryRun) { $publisherArgs += "--dry-run" }
python tools/extension/publish_extension_approvals.py @publisherArgs
if ($LASTEXITCODE -ne 0) {
    Fail "publish_extension_approvals.py exited with code $LASTEXITCODE"
}

# ── 3. sync_new_retailer_queue.py ─────────────────────────────────────
Write-Step "sync_new_retailer_queue.py"
python tools/extension/sync_new_retailer_queue.py @publisherArgs
if ($LASTEXITCODE -ne 0) {
    Fail "sync_new_retailer_queue.py exited with code $LASTEXITCODE"
}

if ($DryRun) {
    Write-Step "Dry-run complete; not committing or pushing"
    exit 0
}

# ── 4. git commit (only the files our publishers can touch) ───────────
Write-Step "git status (publisher-touched files)"
$paths = @(
    "data/master_cigars.csv",
    "data/master_cigars.db",
    "static/data",
    "tools/ai/new_retailer_queue.txt"
)
git add -- @paths

$dirty = git status --porcelain -- @paths
if (-not $dirty) {
    Write-Host "Nothing to commit; publishers produced no changes." -ForegroundColor Green
    exit 0
}

Write-Host $dirty
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$commitMessage = "Extension: publish approvals + new-retailer queue ($timestamp)"

git commit -m $commitMessage
if ($LASTEXITCODE -ne 0) {
    Fail "git commit failed"
}

# ── 5. git push ───────────────────────────────────────────────────────
if ($SkipPush) {
    Write-Host "`n-SkipPush set; commit made but not pushed." -ForegroundColor Yellow
    exit 0
}

Write-Step "git push"
git push
if ($LASTEXITCODE -ne 0) {
    Fail "git push failed. The commit is local; push manually when ready."
}

Write-Host "`nDone." -ForegroundColor Green
