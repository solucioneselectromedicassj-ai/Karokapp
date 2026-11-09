@echo off
title Instalar Karaoke Party
echo.
echo ===== Karaoke Party: instalacion (una sola vez) =====
echo.
where winget >nul 2>nul
if errorlevel 1 goto sinwinget

node --version >nul 2>nul
if errorlevel 1 (echo Instalando Node.js... & winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements) else echo [ok] Node.js ya esta instalado

python --version >nul 2>nul
if errorlevel 1 (echo Instalando Python... & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements) else echo [ok] Python ya esta instalado

ffmpeg -version >nul 2>nul
if errorlevel 1 (echo Instalando ffmpeg... & winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements) else echo [ok] ffmpeg ya esta instalado

echo.
echo Falta Google Drive para escritorio (si aun no lo tienes):
echo   https://www.google.com/drive/download/
echo Instalalo, inicia sesion con tu cuenta y espera a que aparezca la unidad "Mi unidad".
echo.
echo LISTO. Cierra esta ventana y abre "iniciar.bat".
pause
exit /b 0

:sinwinget
echo No encuentro "winget". Actualiza Windows o instala "Instalador de aplicacion" desde Microsoft Store.
echo Tambien puedes instalar a mano: Node.js (nodejs.org), Python 3.12 (python.org, marcando "Add to PATH") y ffmpeg.
pause
exit /b 1
