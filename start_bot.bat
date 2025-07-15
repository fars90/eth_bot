@echo off
echo Ativando ambiente virtual...
call d:\bot\venv\Scripts\activate.bat

echo Iniciando bot...
python d:\bot\bot.py

echo ------------------------------
echo Bot terminou de correr.
pause
