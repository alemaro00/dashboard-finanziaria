@echo off
cd /d "%~dp0"
title Portfolio Operations - IBKR Dashboard Bridge
echo Avvio locale offline. Nessuna connessione broker automatica.
if not exist web-build\dashboard.html (
  node scripts\build-web.cjs
  if errorlevel 1 (
    echo Installa Node.js e compila il frontend. Vedi README.
    pause
    exit /b 1
  )
)
echo.
python ibkr_paper_bridge.py
if errorlevel 1 (
  echo.
  echo Il collegamento non e' stato avviato. Controlla il messaggio di errore e il README.
  pause
)
