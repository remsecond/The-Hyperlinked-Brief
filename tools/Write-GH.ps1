function Write-GitHubFile {
    [CmdletBinding()]
    param(
        [string] $Owner,
        [string] $Repo,
        [Parameter(Mandatory=$true)] [string] $Branch,
        [Parameter(Mandatory=$true)] [string] $Path,
        [Parameter(Mandatory=$true)] [string] $Content,
        [string] $CommitMessage = "Update $Path"
    )

    if (-not $env:GH_TOKEN) { throw "GH_TOKEN environment variable is not set." }

    # Auto-detect owner/repo from current git origin if not supplied
    if (-not $Owner -or -not $Repo) {
        $url = git config --get remote.origin.url 2>$null
        if ($url -match "github\.com[:/](?<owner>[^/]+)/(?<repo>[^\.]+)(\.git)?$") {
            $Owner = $Matches['owner']; $Repo = $Matches['repo']
        } else {
            throw "Owner/Repo not provided and could not be auto-detected (are you in a git repo?)."
        }
    }

    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Content))

    # Get SHA if file exists (required for updates)
    $sha = $null
    $getUrl = "https://api.github.com/repos/$Owner/$Repo/contents/$($Path -replace '\\','/')?ref=$Branch"
    try {
        $resp = Invoke-RestMethod -Headers @{ Authorization = "Bearer $($env:GH_TOKEN)"; "User-Agent"="eai-writer"; "Accept"="application/vnd.github+json" } `
                                  -Uri $getUrl -Method GET -ErrorAction Stop
        $sha = $resp.sha
    } catch { } # ok if it doesn't exist yet

    $body = @{
        message = $CommitMessage
        content = $b64
        branch  = $Branch
    }
    if ($sha) { $body.sha = $sha }

    $putUrl = "https://api.github.com/repos/$Owner/$Repo/contents/$($Path -replace '\\','/')"

    try {
        $resp = Invoke-RestMethod -Headers @{ Authorization = "Bearer $($env:GH_TOKEN)"; "User-Agent"="eai-writer"; "Accept"="application/vnd.github+json" } `
                                  -Uri $putUrl -Method PUT -Body ($body | ConvertTo-Json -Depth 5) -ErrorAction Stop

        # Success only if API returned a commit SHA
        if ($resp.commit.sha) {
            Write-Host "Committed $Path to $Owner/$Repo@$Branch (`$($resp.commit.sha.Substring(0,7))`)"
        } else {
            throw "Unexpected API response; commit missing."
        }
    } catch {
        $msg = $_.Exception.Response.GetResponseStream() | % { New-Object IO.StreamReader($_) } | % { $_.ReadToEnd() }
        if (-not $msg) { $msg = $_.Exception.Message }
        throw "GitHub write failed: $msg"
    }
}
