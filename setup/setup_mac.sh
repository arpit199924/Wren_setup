#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=========================================================="
echo "          WrenAI + DuckDB Workspace Setup (macOS/Linux)   "
echo "=========================================================="
echo ""

# Ensure we are in the root directory (parent of setup/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

# 1. Validate Python version (requires >= 3.11)
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 command not found. Please install Python 3.11 or later."
    exit 1
fi

python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || {
    echo "Error: Python 3.11 or later is required. Current version is $(python3 -V)"
    exit 1
}
echo "Python $(python3 -V) found."
echo ""

# 2. Setup Virtual Environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv..."
    python3 -m venv .venv
else
    echo "Existing virtual environment .venv found."
fi

echo "Activating virtual environment..."
source .venv/bin/activate
echo ""

# 3. Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip
echo ""

# 4. Install dbt-duckdb requirements
echo "Installing dbt and DuckDB requirements..."
pip install -r jaffle_shop_duckdb/requirements.txt
echo ""

# 5. Install wren-pydantic SDK (Editable mode)
echo "Installing local Wren-Pydantic SDK (with Wren core engine dependencies)..."
pip install -e WrenAI/sdk/wren-pydantic
echo ""

# 6. Install FastAPI dashboard requirements
echo "Installing FastAPI dashboard packages..."
pip install fastapi uvicorn loguru pydantic-ai
echo ""

# 7. Update profile paths dynamically
echo "Configuring database connection profile..."
python setup/update_profile.py
echo ""

# 8. Manage API Key
if [ -z "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
    echo "=========================================================="
    echo "          Gemini API Key Setup Required                   "
    echo "=========================================================="
    echo "To run the Gemini model, an API key is required."
    echo "Get a key for free from Google AI Studio:"
    echo "  https://aistudio.google.com/"
    echo "----------------------------------------------------------"
    echo ""
    read -p "Please enter your GEMINI_API_KEY (or press Enter to skip): " user_key
    if [ -n "$user_key" ]; then
        export GEMINI_API_KEY="$user_key"
        export GOOGLE_API_KEY="$user_key"
        echo "API Key temporarily set in current session."
    fi
    echo ""
fi

# Double check if we have a key now
if [ -z "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
    echo "Warning: No API Key was set. Skipping automatic server startup."
    echo "To run the application manually later:"
    echo "  1. Activate virtual environment: source .venv/bin/activate"
    echo "  2. Export key: export GEMINI_API_KEY=\"your_key\""
    echo "  3. Start server: cd jaffle-wren && python -m uvicorn server:app --port 8000"
    echo "=========================================================="
    exit 0
fi

# Ensure GOOGLE_API_KEY is populated if GEMINI_API_KEY is set (pydantic-ai uses GOOGLE_API_KEY)
if [ -n "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
    export GOOGLE_API_KEY="$GEMINI_API_KEY"
fi

# 9. Startup FastAPI application
echo "=========================================================="
echo "Setup completed successfully! Starting the dashboard..."
echo "Open the UI at: http://localhost:8000"
echo "Press Ctrl+C to stop the server."
echo "=========================================================="
echo ""

cd jaffle-wren
python -m uvicorn server:app --port 8000
