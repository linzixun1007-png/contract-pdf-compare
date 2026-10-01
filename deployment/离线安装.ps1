param([Parameter(Mandatory=$true)][string]$InstallDirectory,
      [string]$PythonExecutable = 'python')
$ErrorActionPreference = 'Stop'
$releaseSource = Join-Path $PSScriptRoot '源码'
$releaseWheels = Join-Path (Split-Path $PSScriptRoot -Parent) '04_离线依赖_Windows64位'
$releaseTarget = [System.IO.Path]::GetFullPath($InstallDirectory)
if($releaseTarget -eq [System.IO.Path]::GetPathRoot($releaseTarget)) { throw '请选择具体安装文件夹，不能使用磁盘根目录。' }
& $PythonExecutable -c 'import sys,struct; raise SystemExit(0 if sys.version_info >= (3,10) and struct.calcsize("P")==8 else 1)'
if($LASTEXITCODE -ne 0) { throw '需要可运行的 Windows 64 位 Python 3.10+；推荐 3.12。' }
if((Test-Path -LiteralPath $releaseTarget) -and @(Get-ChildItem -LiteralPath $releaseTarget -Force).Count -gt 0) { throw '安装目录已有内容，请选择新建或空目录。' }
New-Item -ItemType Directory -Path $releaseTarget -Force | Out-Null
Get-ChildItem -LiteralPath $releaseSource -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $releaseTarget -Recurse }
$releaseEnvironment = Join-Path $releaseTarget '.venv'
& $PythonExecutable -m venv $releaseEnvironment
if($LASTEXITCODE -ne 0) { throw '创建独立 Python 环境失败。' }
$releasePython = Join-Path $releaseEnvironment 'Scripts/python.exe'
& $releasePython -m pip install --no-cache-dir --no-index --find-links $releaseWheels --require-hashes -r (Join-Path $releaseTarget 'requirements-runtime.txt')
if($LASTEXITCODE -ne 0) { throw '离线依赖安装失败。' }
& $releasePython (Join-Path $releaseTarget 'gui.py') --self-test --result (Join-Path $releaseTarget '安装验收.json')
if($LASTEXITCODE -ne 0) { throw '安装后功能验收未通过。' }
$releaseLauncher = @'
@echo off
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0gui.py"
'@
[System.IO.File]::WriteAllText((Join-Path $releaseTarget '启动合同对比.bat'), $releaseLauncher, [System.Text.Encoding]::ASCII)
Write-Output ('安装和验收完成：' + $releaseTarget)
