# AutoCheck 打包脚本
# 用法: 在 D:\trae\autocheck 目录执行

$python = "C:/Users/jh832/.workbuddy/binaries/python/envs/autocheck/Scripts/python.exe"
$src = "D:/trae/autocheck/src"
$web = "D:/trae/autocheck/src/auto_check/web"
$resources = "D:/trae/autocheck/src/auto_check/resources"
$entry = "D:/trae/autocheck/src/auto_check/__main__.py"
$dist = "D:/trae/autocheck/dist"
$build = "D:/trae/autocheck/build"

# Kill existing process
taskkill /f /im auto-check.exe 2>$null
Start-Sleep 1

# Build
& $python -m PyInstaller --noconfirm --onefile --name auto-check `
  --paths $src --add-data "${web};auto_check/web" --add-data "${resources};auto_check/resources" `
  --collect-submodules auto_check.modules --collect-data auto_check.modules `
  --distpath $dist --workpath $build --specpath $build `
  --clean $entry

if ($LASTEXITCODE -eq 0) {
    $exe = Join-Path $dist "auto-check.exe"
    $size = (Get-Item $exe).Length / 1MB
    Write-Host "Done: $exe ($([math]::Round($size)) MB)" -ForegroundColor Green
}
