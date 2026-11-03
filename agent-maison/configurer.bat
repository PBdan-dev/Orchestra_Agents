@echo off
chcp 65001 >nul
echo Configuration de l agent Maison connectee (Python), a faire une fois.
echo Les cles Hue et TV vont dans le coffre-fort Windows, les adresses dans memoire\appareils.json.
echo.
python "%~dp0agent.py" configurer %1
echo.
pause
