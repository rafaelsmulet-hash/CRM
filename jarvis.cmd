@echo off
REM Wrapper para rodar o Jarvis como `jarvis <comando>` no Windows.
python "%~dp0cli\main.py" %*
