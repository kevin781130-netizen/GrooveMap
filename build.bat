@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  GrooveMap - Windows 打包 + 压缩
echo ============================================

echo [0/5] 检查 Python 版本...
python -c "import sys; assert sys.version_info[:2] in [(3,10),(3,11)], 'need Python 3.10 or 3.11'; print('OK:', sys.version)"
if errorlevel 1 ( echo [错误] 请安装 Python 3.10 或 3.11 & pause & exit /b 1 )

echo [1/5] 建立 / 启用虚拟环境...
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate

echo [2/5] 安装依赖...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo [3/5] 清理旧输出...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/5] PyInstaller 打包...
python -m PyInstaller --clean --noconfirm build_exe.spec

if not exist "dist\GrooveMap\GrooveMap.exe" (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo [5/5] 压缩成 zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\GrooveMap\*' -DestinationPath 'dist\GrooveMap-Windows.zip' -Force"

echo.
echo ============================================
echo  完成！
echo  EXE : dist\GrooveMap\GrooveMap.exe
echo  ZIP : dist\GrooveMap-Windows.zip
echo ============================================
pause
