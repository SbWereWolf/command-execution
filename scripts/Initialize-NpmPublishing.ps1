[CmdletBinding()]
param(
    [string]$Tarball = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist/npm/command-execution-2.0.6.tgz'),
    [switch]$Apply,
    [switch]$PushRelease
)

$ErrorActionPreference = 'Stop'
$Registry = 'https://registry.npmjs.org/'
$Package = 'command-execution'
$BootstrapVersion = '2.0.6'
$BootstrapSha512 = 'efc59e72316f54410c324e0fc3bbe4de5e4df1a68c0508ce90a053e5845a0928837f10c4565e3f3c0658d2abb6a688f27c5bfccd35601850f68633bd81623b23'
$Repository = 'SbWereWolf/command-execution'
$WslRepository = '/home/sbwerewolf/workdata/command-execution'
$ReleaseTag = 'v2.0.7'

function Get-PublishedBootstrap {
    try {
        Invoke-RestMethod -Uri "$Registry$Package/$BootstrapVersion" -Headers @{'Cache-Control' = 'no-cache'}
    }
    catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) { return }
        throw
    }
}

function Assert-SameBootstrap($Release, [string]$Integrity) {
    if ($Release.dist.integrity -cne $Integrity) {
        throw "$Package@$BootstrapVersion already exists with different bytes."
    }
}

if ($PushRelease -and -not $Apply) { throw '-PushRelease requires -Apply.' }
$Archive = (Resolve-Path -LiteralPath $Tarball).ProviderPath
if ((Get-FileHash -Algorithm SHA512 -LiteralPath $Archive).Hash -ine $BootstrapSha512) {
    throw 'The archive does not match the verified bootstrap tarball.'
}
$Hasher = [Security.Cryptography.SHA512]::Create()
$Stream = [IO.File]::OpenRead($Archive)
try { $Integrity = 'sha512-' + [Convert]::ToBase64String($Hasher.ComputeHash($Stream)) }
finally { $Stream.Dispose(); $Hasher.Dispose() }

$Published = Get-PublishedBootstrap
if ($Published) { Assert-SameBootstrap $Published $Integrity }
Write-Host "Verified local archive for $Package@$BootstrapVersion."
Write-Host "Registry: $Registry"
Write-Host "Trusted publisher: $Repository / publish.yml / npm publish"
if (-not $Apply) { return }

$Npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$Node = (Get-Command node.exe -ErrorAction Stop).Source
& $Node -e 'const [major,minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || major === 22 && minor >= 14 ? 0 : 1)'
if ($LASTEXITCODE -ne 0) { throw 'Node.js 22.14 or later is required.' }

$Local = Join-Path ([IO.Path]::GetTempPath()) ('command-execution-npm-' + [guid]::NewGuid())
[void](New-Item -ItemType Directory -Path $Local)
$LocalArchive = Join-Path $Local "$Package-$BootstrapVersion.tgz"
Copy-Item -LiteralPath $Archive -Destination $LocalArchive
Push-Location -LiteralPath $Local
try {
    $Npm11 = @('exec', '--yes', "--registry=$Registry", '--package=npm@11.21.3', '--', 'npm')
    & $Npm @Npm11 whoami "--registry=$Registry"
    if ($LASTEXITCODE -ne 0) {
        & $Npm @Npm11 login --auth-type=web "--registry=$Registry"
        if ($LASTEXITCODE -ne 0) { throw 'npm login failed.' }
    }
    if (-not $Published) {
        & $Npm @Npm11 publish $LocalArchive --access=public "--registry=$Registry"
        if ($LASTEXITCODE -ne 0) { throw 'npm bootstrap publication failed.' }
        foreach ($Delay in @(0, 2, 4, 8, 16, 30)) {
            if ($Delay) { Start-Sleep -Seconds $Delay }
            $Published = Get-PublishedBootstrap
            if ($Published) { break }
        }
        if (-not $Published) { throw 'The bootstrap version is not visible in npm yet.' }
        Assert-SameBootstrap $Published $Integrity
    }
    & $Npm @Npm11 trust github $Package --repo $Repository --file publish.yml --allow-publish "--registry=$Registry"
    if ($LASTEXITCODE -ne 0) { throw 'npm trust failed. Inspect the existing publisher settings on npmjs.com.' }
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $LocalArchive) { Remove-Item -LiteralPath $LocalArchive }
    Remove-Item -LiteralPath $Local
}

if ($PushRelease) {
    $Url = & wsl.exe -d Ubuntu --exec git -C $WslRepository remote get-url --push origin
    if ($LASTEXITCODE -ne 0 -or $Url -cne "https://github.com/$Repository.git") { throw 'Unexpected origin push URL.' }
    $TaggedCommit = & wsl.exe -d Ubuntu --exec git -C $WslRepository rev-parse --verify "$ReleaseTag^{commit}"
    if ($LASTEXITCODE -ne 0) { throw "Missing $ReleaseTag." }
    $MasterCommit = & wsl.exe -d Ubuntu --exec git -C $WslRepository rev-parse --verify refs/heads/master
    if ($LASTEXITCODE -ne 0 -or $MasterCommit -ne $TaggedCommit) { throw "master does not point to $ReleaseTag." }
    & wsl.exe -d Ubuntu --exec git -C $WslRepository push --atomic origin refs/heads/master "refs/tags/$ReleaseTag"
    if ($LASTEXITCODE -ne 0) { throw 'Git push failed.' }
}
