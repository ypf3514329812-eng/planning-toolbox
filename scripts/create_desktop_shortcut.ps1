param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$exePath = Join-Path $ProjectRoot "dist\PlanningToolbox\PlanningToolbox.exe"
$iconPath = Join-Path $ProjectRoot "assets\planning_toolbox.ico"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Planning Toolbox executable not found: $exePath"
}
if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Planning Toolbox icon not found: $iconPath"
}

$desktopPath = [Environment]::GetFolderPath("Desktop")
$existingShortcut = Get-ChildItem -LiteralPath $desktopPath -Filter "Planning Toolbox*.lnk" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$shortcutPath = if ($existingShortcut) {
    $existingShortcut.FullName
} else {
    Join-Path $desktopPath "Planning Toolbox.lnk"
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "Planning Toolbox v0.30.0 GIS-CAD-SU Workbench"
$shortcut.Save()

Write-Output $shortcutPath
