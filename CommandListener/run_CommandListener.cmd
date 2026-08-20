@echo off
setlocal

set "PYTHON_EXE=C:\Users\zhv85164\AppData\Local\Programs\Python\Python311\python.exe"

if not exist "%PYTHON_EXE%" (
    echo Error: Expected interpreter not found: %PYTHON_EXE%
    exit /b 1
)

"%PYTHON_EXE%" "%~dp0CommandListener.py" %*
