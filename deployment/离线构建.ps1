param([Parameter(Mandatory=$true)][string]$BuildDirectory,
      [string]$PythonExecutable = 'python')
$ErrorActionPreference = 'Stop'
$releaseSource = Join-Path $PSScriptRoot '源码'
$releaseWheels = Join-Path (Split-Path $PSScriptRoot -Parent) '04_离线依赖_Windows64位'
$releaseBuild = [System.IO.Path]::GetFullPath($BuildDirectory)
if($releaseBuild -eq [System.IO.Path]::GetPathRoot($releaseBuild)) { throw '请选择具体构建文件夹，不能使用磁盘根目录。' }
& $PythonExecutable -c 'import sys,struct; raise SystemExit(0 if sys.version_info >= (3,10) and struct.calcsize("P")==8 else 1)'
if($LASTEXITCODE -ne 0) { throw '需要可运行的 Windows 64 位 Python 3.10+；推荐 3.12。' }
New-Item -ItemType Directory -Path $releaseBuild -Force | Out-Null
$releaseEnvironment = Join-Path $releaseBuild '.venv-build'
& $PythonExecutable -m venv $releaseEnvironment
if($LASTEXITCODE -ne 0) { throw '创建构建环境失败。' }
$releasePython = Join-Path $releaseEnvironment 'Scripts/python.exe'
& $releasePython -m pip install --no-cache-dir --no-index --find-links $releaseWheels --require-hashes -r (Join-Path $releaseSource 'requirements-build.txt')
if($LASTEXITCODE -ne 0) { throw '离线构建依赖安装失败。' }
& $releasePython (Join-Path $releaseSource 'gui.py') --self-test --result (Join-Path $releaseBuild '源码验收.json')
if($LASTEXITCODE -ne 0) { throw '源码验收失败，停止构建。' }
& $releasePython (Join-Path $releaseSource 'build_exe.py') --mode both --output (Join-Path $releaseBuild '产物')
if($LASTEXITCODE -ne 0) { throw '构建失败。' }
Write-Output ('两种免安装形态已生成：' + (Join-Path $releaseBuild '产物'))
