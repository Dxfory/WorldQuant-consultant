# Run this inside F:\Image\pixel-intact
# It overlays the latest Pixel Intact files into the current folder.

$ErrorActionPreference = "Stop"
$here = Get-Location
if (-not (Test-Path (Join-Path $here "web\index.html"))) {
    throw "请先 cd 到 F:\Image\pixel-intact 再运行这个脚本。"
}

$zip = Join-Path $env:TEMP "pixel-intact-update.zip"
$tmp = Join-Path $env:TEMP "pixel-intact-update"
$branch = "cursor/pixel-intact-studio-fe20"
$uri = "https://github.com/Dxfory/WorldQuant-consultant/archive/refs/heads/$branch.zip"

Write-Host "正在下载 $branch ..."
Invoke-WebRequest -Uri $uri -OutFile $zip
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$src = Get-ChildItem $tmp -Directory | Select-Object -First 1
$payload = Join-Path $src.FullName "pixel-intact"
if (-not (Test-Path (Join-Path $payload "web\index.html"))) {
    throw "下载内容里没有 pixel-intact，请把报错发给我。"
}

Write-Host "正在写入 $here"
Copy-Item -Path (Join-Path $payload "*") -Destination $here -Recurse -Force
Write-Host "更新完成。接着执行："
Write-Host '  python -m pip install -e ".[dev,sr]"'
Write-Host "  python -m pixel_intact.cli studio"
