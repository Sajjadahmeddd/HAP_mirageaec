@echo off
rem Double-click launcher for the HAP PDF-to-CSV Converter (development mode).
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m hap_converter.main
