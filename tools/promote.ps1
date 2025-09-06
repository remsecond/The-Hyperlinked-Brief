param(
  [Parameter(Mandatory)][string]$Path,
  [string]$Repo = "C:\Repos\The-Hyperlinked-Brief"
)

Set-StrictMode -Version Latest
Set-Location -LiteralPath $Repo
if (!(Test-Path .git)) { throw "Not a git repo: $Repo" }

git fetch origin | Out-Null

# If there are no differences, exit politely
git diff --quiet origin/prod..origin/dev -- $Path
if ($LASTEXITCODE -eq 0) {
  Write-Host "No changes on origin/dev for '$Path'. Nothing to promote."
  exit 0
}

# Switch to prod and copy the exact file bytes from origin/dev
git switch prod | Out-Null
git restore --source origin/dev -- $Path
git add $Path
git commit -m "Promote: $Path from dev to prod" | Out-Null
git push origin prod | Out-Null

# Verify via orchestrator if present
$orch = Join-Path $Repo 'Scripts\orchestrator.py'
if (Test-Path $orch) {
  python $orch --branch origin/prod --prompt $Path
} else {
  Write-Host "Promoted. (orchestrator not found to verify)"
}
