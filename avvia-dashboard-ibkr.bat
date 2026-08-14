@echo off
cd /d "%~dp0"
title Portfolio Operations - IBKR Dashboard Bridge
echo Avvio del collegamento locale IBKR in sola lettura...
echo TWS Live: porta 7496 - TWS Paper: porta 7497.
echo Puoi tenere aperta una sola sessione oppure entrambe.
echo.
python ibkr_paper_bridge.py
if errorlevel 1 (
  echo.
  echo Il collegamento non e' stato avviato. Controlla TWS e riprova.
  pause
)
