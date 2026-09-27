<#
.SYNOPSIS
  One-time setup: downloads Python's official "embeddable" distribution,
  patches it so it can use pip/site-packages, and installs GLauncher's
  dependencies into it - producing the python-embed/ folder that
  launcher.py (the frozen auto-py-to-exe stub) looks for at runtime.

  Run this ONCE per machine you build the .exe on, from the project root:

      powershell -ExecutionPolicy Bypass -File scripts\setup_python_embed.ps1

  Re-run it any time requirements.txt changes - it's safe to run again,
  it just reuses the existing download if present.

.PARAMETER PythonVersion
  Exact CPython version to embed, e.g. 3.11.9. Must be a version that has
  an "embeddable package" build published on python.org (all recent 3.9+
  releases do). Match README's "Python 3.10+" requirement.
#>
param(
    [string]$PythonVersion = "3.11.9"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$embedDir = Join-Path $root "python-embed"
$zipName = "python-$PythonVersion-embed-amd64.zip"
$zipPath = Join-Path $root $zipName
$zipUrl = "https://www.python.org/ftp/python/$PythonVersion/$zipName"

Write-Host "== GLauncher embedded Python setup ($PythonVersion) =="

if (Test-Path $embedDir) {
    Write-Host "Removing existing python-embed/ ..."
    Remove-Item -Recurse -Force $embedDir
}

if (-not (Test-Path $zipPath)) {
    Write-Host "Downloading $zipUrl ..."
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
} else {
    Write-Host "Reusing already-downloaded $zipName"
}

Write-Host "Extracting to python-embed/ ..."
Expand-Archive -Path $zipPath -DestinationPath $embedDir -Force

# The embeddable distro ships a <version>._pth file that, by default,
# restricts imports to its own stdlib zip and blocks `import site` -
# meaning no pip, no site-packages, nothing third-party works. Uncommenting
# "import site" and adding Lib\site-packages is what makes pip-installed
# packages (pywebview, requests, minecraft-launcher-lib) importable.
$pthFile = Get-ChildItem $embedDir -Filter "python*._pth" | Select-Object -First 1
if (-not $pthFile) {
    throw "Couldn't find a ._pth file inside the extracted embeddable package."
}
Write-Host "Patching $($pthFile.Name) to enable site-packages ..."
$pthContent = Get-Content $pthFile.FullName
$pthContent = $pthContent -replace '^#\s*import site', 'import site'
if ($pthContent -notcontains "Lib\site-packages") {
    $pthContent += "Lib\site-packages"
}
Set-Content -Path $pthFile.FullName -Value $pthContent

$pythonExe = Join-Path $embedDir "python.exe"

$getPipPath = Join-Path $root "get-pip.py"
if (-not (Test-Path $getPipPath)) {
    Write-Host "Downloading get-pip.py ..."
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPipPath
}

Write-Host "Installing pip into python-embed/ ..."
& $pythonExe $getPipPath --no-warn-script-location

Write-Host "Installing requirements.txt into python-embed/ ..."
& $pythonExe -m pip install -r (Join-Path $root "requirements.txt") --no-warn-script-location

Remove-Item $zipPath -ErrorAction SilentlyContinue
Remove-Item $getPipPath -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done. python-embed/ is ready next to main.py."
Write-Host "Now freeze launcher.py (not main.py) with auto-py-to-exe, and"
Write-Host "ship the resulting exe together with: main.py, api.py, core/,"
Write-Host "web/, requirements.txt, and this python-embed/ folder."
