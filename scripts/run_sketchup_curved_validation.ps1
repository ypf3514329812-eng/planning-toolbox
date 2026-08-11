$ErrorActionPreference = 'Stop'

# SketchUp only evaluates -RubyStartup after a model is opened.  The bootstrap
# model is an existing validation artifact and is never edited by the runner;
# the runner immediately switches to a fresh model before importing the new
# handoff file.
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
$handoff = Join-Path $projectRoot 'output\sketchup_validation_v028_curved_lights\curved_road_validation.ptsu.json'
$pluginMain = Join-Path $projectRoot 'test_artifacts\sketchup_runtime_v028_curved_lights\plugin\planning_toolbox_sketchup\main.rb'
$baseValidationDir = Join-Path $projectRoot 'test_artifacts\sketchup_runtime_v028_curved_lights'
$validationDir = $baseValidationDir
$report = Join-Path $validationDir 'sketchup_runtime_report.json'

foreach ($requiredPath in @($sketchup, $runner, $bootstrap, $handoff, $pluginMain)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Missing SketchUp validation file: $requiredPath"
    }
}

# Never overwrite an earlier evidence run.  A rerun receives a new project
# scoped directory while reusing the immutable handoff and plugin inputs.
if (Test-Path -LiteralPath $report -PathType Leaf) {
    $runStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $validationDir = Join-Path $projectRoot "test_artifacts\sketchup_runtime_v027_curved_rerun_$runStamp"
    New-Item -ItemType Directory -Path $validationDir -Force | Out-Null
    $report = Join-Path $validationDir 'sketchup_runtime_report.json'
}

$env:PT_SKETCHUP_HANDOFF = $handoff
$env:PT_SKETCHUP_VALIDATION_DIR = $validationDir
$env:PT_SKETCHUP_PLUGIN_MAIN = $pluginMain
$env:PT_EXPECT_CURVED_ROAD = '1'
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
    throw "SketchUp validation report was not written in time. PID=$($process.Id)"
}

Get-Content -LiteralPath $report -Raw -Encoding UTF8
