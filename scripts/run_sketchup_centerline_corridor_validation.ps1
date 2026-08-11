$ErrorActionPreference = 'Stop'

$projectRoot = if ($env:PLANNING_TOOLBOX_ROOT) { [IO.Path]::GetFullPath($env:PLANNING_TOOLBOX_ROOT) } else { Split-Path -Parent $PSScriptRoot }
$sketchup = $env:SKETCHUP_EXE
if ([string]::IsNullOrWhiteSpace($sketchup)) {
    $command = Get-Command SketchUp.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $sketchup = if ($command) { $command.Source } else {
        $candidate = Get-ChildItem -LiteralPath (Join-Path $env:ProgramFiles 'SketchUp') -Recurse -Filter 'SketchUp.exe' -File -ErrorAction SilentlyContinue | Sort-Object FullName | Select-Object -First 1
        if ($candidate) { $candidate.FullName } else { 'SketchUp.exe' }
    }
}
$runner = Join-Path $projectRoot 'scripts\sketchup_validation_runner.rb'
$bootstrap = Join-Path $projectRoot 'output\sketchup_validation_v025_final10\planning_toolbox_su_validation.skp'
$handoff = Join-Path $projectRoot 'output\sketchup_validation_v030_centerline_corridor\centerline_corridor_validation.ptsu.json'
$pluginMain = Join-Path $projectRoot 'test_artifacts\sketchup_runtime_v030_centerline_corridor\plugin\planning_toolbox_sketchup\main.rb'
$baseValidationDir = Join-Path $projectRoot 'test_artifacts\sketchup_runtime_v030_centerline_corridor'
$validationDir = $baseValidationDir
$report = Join-Path $validationDir 'sketchup_runtime_report.json'

foreach ($requiredPath in @($sketchup, $runner, $bootstrap, $handoff, $pluginMain)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Missing SketchUp centerline-corridor validation file: $requiredPath"
    }
}

if (Test-Path -LiteralPath $report -PathType Leaf) {
    $runStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $validationDir = Join-Path $projectRoot "test_artifacts\sketchup_runtime_v030_centerline_corridor_rerun_$runStamp"
    New-Item -ItemType Directory -Path $validationDir -Force | Out-Null
    $report = Join-Path $validationDir 'sketchup_runtime_report.json'
}

$env:PT_SKETCHUP_HANDOFF = $handoff
$env:PT_SKETCHUP_VALIDATION_DIR = $validationDir
$env:PT_SKETCHUP_PLUGIN_MAIN = $pluginMain
$env:PT_EXPECT_CENTERLINE_CORRIDOR = '1'
$env:PT_SKETCHUP_AUTO_QUIT = '1'

$startedAt = Get-Date
$process = Start-Process -FilePath $sketchup -ArgumentList @('-RubyStartup', $runner, $bootstrap) -PassThru
for ($index = 0; $index -lt 120; $index++) {
    Start-Sleep -Seconds 1
    if ((Test-Path -LiteralPath $report -PathType Leaf) -and
        ((Get-Item -LiteralPath $report).LastWriteTime -gt $startedAt)) {
        break
    }
    if ($process.HasExited -and $index -gt 5) {
        break
    }
}

if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw "SketchUp centerline-corridor validation report was not written in time. PID=$($process.Id)"
}

Get-Content -LiteralPath $report -Raw -Encoding UTF8
