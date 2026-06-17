@echo off
echo === Setting up .venv and required libraries ===
echo.

python -m venv .venv
if errorlevel 1 (
    echo ERROR: Failed to create venv. Is Python installed?
    pause
    exit /b 1
)

call .venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Some packages failed to install.
) else (
    echo.
    echo === Setup complete! ===
)

pause
