$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ProjectRoot "scripts\create_island_scene.py"
$OutputDir = Join-Path $ProjectRoot "output"
$BlendPath = Join-Path $OutputDir "island_two_villages.blend"
$GlbPath = Join-Path $OutputDir "island_two_villages.glb"

function Resolve-Blender {
    $Command = Get-Command blender -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $CommonPaths = @(
        "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
        "C:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
        "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
        "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
    )

    foreach ($Path in $CommonPaths) {
        if (Test-Path -LiteralPath $Path) {
            return $Path
        }
    }

    return $null
}

$BlenderExe = Resolve-Blender

if (-not $BlenderExe) {
    Write-Host "Blender was not found. Installing Blender with winget..."
    winget install BlenderFoundation.Blender --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Automatic Blender installation failed with exit code $LASTEXITCODE."
    }

    $BlenderExe = Resolve-Blender
}

if (-not $BlenderExe) {
    throw "Blender installation completed, but no usable blender executable was found on PATH or in common install paths."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "Using Blender: $BlenderExe"
& $BlenderExe --background --python $PythonScript
if ($LASTEXITCODE -ne 0) {
    throw "Blender scene generation failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path -LiteralPath $BlendPath)) {
    throw "Expected Blender file was not created: $BlendPath"
}

if (-not (Test-Path -LiteralPath $GlbPath)) {
    throw "Expected GLB preview was not created: $GlbPath"
}

Write-Host ""
Write-Host "Generated files:"
Write-Host "  $BlendPath"
Write-Host "  $GlbPath"
