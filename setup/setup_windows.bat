@echo off
echo ==========================================================
echo          WrenAI + DuckDB Workspace Setup (Windows)        
echo ==========================================================
echo.

:: Ensure we are in the root directory (parent of setup)
cd /d "%~dp0.."

:: 1. Validate Python version
echo Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: python command not found. Please install Python 3.11 or later and add it to your PATH.
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo Error: Python 3.11 or later is required.
    exit /b 1
)
echo Python is installed.
echo.

:: 2. Setup Virtual Environment
if not exist .venv (
    echo Creating virtual environment in .venv...
    python -m venv .venv
) else (
    echo Existing virtual environment .venv found.
)

echo Activating virtual environment...
call .venv\Scripts\activate
echo.

:: 3. Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip
echo.

:: 4. Install dbt-duckdb requirements
echo Installing dbt and DuckDB requirements...
pip install -r jaffle_shop_duckdb\requirements.txt
echo.

:: 5. Install wren-pydantic SDK (Editable mode)
echo Installing local Wren-Pydantic SDK (with Wren core engine dependencies)...
pip install -e WrenAI\sdk\wren-pydantic
echo.

:: 6. Install FastAPI dashboard requirements
echo Installing FastAPI dashboard packages...
pip install fastapi uvicorn loguru pydantic-ai
echo.

:: 7. Update profile paths dynamically
echo Configuring database connection profile...
python setup\update_profile.py
echo.

:: 8. Manage API Key
if "%GEMINI_API_KEY%"=="" if "%GOOGLE_API_KEY%"=="" goto ASK_KEY
goto START_SERVER

:ASK_KEY
echo ==========================================================
echo           Gemini API Key Setup Required                   
echo ==========================================================
echo To run the Gemini model, an API key is required.
echo Get a key for free from Google AI Studio:
echo   https://aistudio.google.com/
echo ----------------------------------------------------------
echo.
set /p GEMINI_API_KEY="Please enter your GEMINI_API_KEY (or press Enter to skip): "
echo.
if "%GEMINI_API_KEY%"=="" goto NO_KEY
set GOOGLE_API_KEY=%GEMINI_API_KEY%
goto START_SERVER

:NO_KEY
echo Warning: No API Key was set. Skipping automatic server startup.
echo To run the application manually later:
echo   1. Activate virtual environment: call .venv\Scripts\activate
echo   2. Set key: set GEMINI_API_KEY="your_key"
echo   3. Start server: cd jaffle-wren ^& python -m uvicorn server:app --port 8000
echo ==========================================================
exit /b 0

:START_SERVER
:: Ensure GOOGLE_API_KEY is populated if GEMINI_API_KEY is set
if not "%GEMINI_API_KEY%"=="" if "%GOOGLE_API_KEY%"=="" set GOOGLE_API_KEY=%GEMINI_API_KEY%

:: 9. Startup FastAPI application
echo ==========================================================
echo Setup completed successfully! Starting the dashboard...
echo Open the UI at: http://localhost:8000
echo Press Ctrl+C to stop the server.
echo ==========================================================
echo.

cd jaffle-wren
python -m uvicorn server:app --port 8000
