@echo off
title Karaoke Party - PC
cd /d "%~dp0pc"

node --version >nul 2>nul
if errorlevel 1 goto falta
python --version >nul 2>nul
if errorlevel 1 goto falta
ffmpeg -version >nul 2>nul
if errorlevel 1 goto falta

if exist ".instalado" goto drive
echo.
echo Primera vez: instalando los componentes de IA.
echo Puede tardar bastante y descarga varios GB. No cierres esta ventana.
echo.
python -m pip install -r requirements.txt
if errorlevel 1 goto pipfalla
echo instalado> .instalado

:drive
set "BASE="
for %%D in (C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
  if exist "%%D:\Mi unidad\" set "BASE=%%D:\Mi unidad"
  if exist "%%D:\My Drive\" set "BASE=%%D:\My Drive"
)
if not defined BASE goto sindrive
set "LIBRARY_DIR=%BASE%\Karaoke\canciones"
if not exist "%LIBRARY_DIR%" mkdir "%LIBRARY_DIR%"
echo.
echo Las canciones listas se guardaran en: %LIBRARY_DIR%
goto arrancar

:sindrive
echo.
echo No encontre Google Drive para escritorio. Las canciones quedaran en la carpeta "biblioteca" de este programa.
echo Instala Google Drive para escritorio y vuelve a abrir este archivo para que se suban a tu Drive.

:arrancar
echo.
echo Abriendo la pagina para agregar canciones. No cierres esta ventana mientras se procesan.
start "" http://localhost:3000/preparar
node server.js
pause
exit /b 0

:falta
echo.
echo Falta instalar Node.js, Python o ffmpeg. Abre primero "instalar.bat".
echo Si ya lo hiciste, cierra esta ventana y vuelve a abrir este archivo.
pause
exit /b 1

:pipfalla
echo.
echo Fallo la instalacion de los componentes. Revisa la conexion a internet y vuelve a abrir este archivo.
pause
exit /b 1
