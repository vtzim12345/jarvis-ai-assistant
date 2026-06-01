@echo off
title JARVIS v5
color 0F
echo.
echo  ============================================================
echo   J . A . R . V . I . S   v5   -   Criado por Senhor Victor
echo  ============================================================
echo.

python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado. Instale Python 3.10+
    pause & exit /b
)

IF NOT EXIST ".deps_ok" (
    echo Instalando dependencias...
    pip install -r requirements.txt
    IF %ERRORLEVEL% EQU 0 (
        echo ok > .deps_ok
    ) ELSE (
        echo [AVISO] Algumas dependencias podem falhar, continuando...
    )
)

echo Abrindo interface...
start "" cmd /c "timeout /t 3 >nul && start http://localhost:5000"

echo.
echo  Acesse:     http://localhost:5000
echo  Ative:      2 palmas na frente do microfone
echo  Wake word:  diga JARVIS a qualquer momento
echo.
python backend\jarvis_core.py
pause
