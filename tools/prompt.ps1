param(
  [Parameter(Mandatory)][ValidateSet('list','get','set','promote')]$Cmd,
  [string]$Target,                               # index like "3" or name like "Prompt_I"
  [string]$Repo = "C:\Repos\The-Hyperlinked-Brief",
  [switch]$ToClipboard,                          # for: get
  [switch]$FromClipboard,                        # for: set
  [string]$File,                                 # for: set (alternative to -FromClipboard)
  [switch]$Full                                  # for: get (print full file instead of header)
)

$ErrorActionPreference = 'Stop'
function Use-Repo {
  param([string]$Path)
  if (!(Test-Path $Path)) { throw "Repo not found: $Path" }
  Set-Location -LiteralPath $Path
  if (!(Test-Path .git)) { throw "Not a git repo: $Path" }
  git fetch origin | Out-Null
}

function Get-PromptList {
  # Discover all prompt files on origin/dev
  $names = git ls-tree -r --name-only origin/dev -- 'Prompts' |
           Where-Object { $_ -like 'Prompts/*.md' } |
           Sort-Object
  $i = 0
  $names | ForEach-Object {
    $i++
    [PSCustomObject]@{
      Index = $i
      Name  = [IO.Path]::GetFileNameWithoutExtension($_)   # e.g. Prompt_I
      Path  = $_                                           # e.g. Prompts/Prompt_I.md
    }
  }
}

function Resolve-Target {
  param($List, [string]$Target)
  if (-not $Target) { return $null }
  if ($Target -match '^\d+$') {
    $idx = [int]$Target
    $item = $List | Where-Object { $_.Index -eq $idx }
    if (!$item) { throw "No prompt with index $idx" }
    return $item
  } else {
    $item = $List | Where-Object { $_.Name -eq $Target -or $_.Path -eq $Target }
    if (!$item) { throw "No prompt named '$Target'" }
    return $item
  }
}

function Show-Header {
  param([string]$Text,[int]$Lines=14)
  $i = 0
  "----- FILE HEADER -----"
  foreach ($ln in ($Text -split "`r?`n")[0..([Math]::Min($Lines-1, (($Text -split "`r?`n").Count-1)))]) {
    $i++
    "{0:D2}: {1}" -f $i, $ln
  }
  "-----------------------"
}

Use-Repo $Repo
$prompts = Get-PromptList

switch ($Cmd) {
  'list' {
    if (!$prompts) { Write-Host "No prompt files found under Prompts/ on origin/dev."; break }
    $prompts | Format-Table Index,Name,Path -AutoSize
  }

  'get' {
    if (!$prompts) { throw "No prompt files found." }
    $sel = Resolve-Target $prompts $Target
    if (-not $sel) {
      $prompts | Format-Table Index,Name,Path -AutoSize
      $choice = Read-Host "Enter index to GET"
      $sel = Resolve-Target $prompts $choice
    }
    $text = git show ("origin/dev:{0}" -f $sel.Path)
    if ($ToClipboard) { $text | Set-Clipboard }
    if ($Full) { $text } else { Show-Header $text }
  }

  'set' {
    if (!$prompts) { throw "No prompt files found." }
    $sel = Resolve-Target $prompts $Target
    if (-not $sel) {
      $prompts | Format-Table Index,Name,Path -AutoSize
      $choice = Read-Host "Enter index to SET"
      $sel = Resolve-Target $prompts $choice
    }
    if ($FromClipboard) {
      $text = Get-Clipboard -Raw
      if (-not $text) { throw "Clipboard is empty." }
    } elseif ($File) {
      if (!(Test-Path $File)) { throw "File not found: $File" }
      $text = Get-Content -Raw -Encoding UTF8 $File
    } else {
      throw "Provide -FromClipboard OR -File <path>."
    }

    git switch dev | Out-Null
    $dest = Join-Path $Repo ($sel.Path -replace '/','\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    [IO.File]::WriteAllText($dest, $text, [Text.UTF8Encoding]::new($false))
    git add -- $sel.Path
    git commit -m ("chore(dev): update {0}" -f $sel.Path) | Out-Null
    git push origin dev | Out-Null
    Write-Host ("Updated dev: {0}" -f $sel.Path)
  }

  'promote' {
    if (!$prompts) { throw "No prompt files found." }
    $sel = Resolve-Target $prompts $Target
    if (-not $sel) {
      $prompts | Format-Table Index,Name,Path -AutoSize
      $choice = Read-Host "Enter index to PROMOTE"
      $sel = Resolve-Target $prompts $choice
    }
    # Only promote if remote dev differs from remote prod
    git diff --quiet origin/prod..origin/dev -- $sel.Path
    if ($LASTEXITCODE -eq 0) {
      Write-Host ("No diff for {0}; nothing to promote." -f $sel.Path)
      break
    }
    git switch prod | Out-Null
    git restore --source origin/dev -- $sel.Path
    git add -- $sel.Path
    git commit -m ("Promote: {0} from dev to prod" -f $sel.Path) | Out-Null
    git push origin prod | Out-Null
    # Verify (print header from prod)
    $text = git show ("origin/prod:{0}" -f $sel.Path)
    Show-Header $text
  }
}
