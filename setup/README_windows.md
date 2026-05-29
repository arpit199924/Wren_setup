# Windows Setup & Onboarding Guide

This guide helps team members set up the WrenAI + DuckDB + FastAPI dashboard workspace on Windows systems using the Command Prompt (CMD).

## Prerequisites

Before running the setup, ensure your system has the following:
1. **Python 3.11 or later**: Verify via `python --version`. If not installed, you can download the installer from [python.org](https://www.python.org/downloads/). During installation, **make sure to check "Add Python to PATH"**.
2. **Git**: Verify via `git --version`. Ensure it is added to your environment variables.
3. **Google Gemini API Key**: Needed to run the Gemini LLM agent.

### How to Get a Google Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click the **Get API key** button on the top-left sidebar.
4. Click **Create API key**. You can create a key in a new project or an existing one.
5. Copy the generated key and save it securely. You will need to export this key in your command prompt:
   ```cmd
   set GEMINI_API_KEY=your_actual_api_key_here
   ```

---

## Automated Setup

We have provided a batch script [setup_windows.bat](file:///Users/harshit/Desktop/SN/setup/setup_windows.bat) to fully automate the installation and configuration of the environment on Windows.

To run it, open your Command Prompt (CMD) in the project root directory and execute:
```cmd
setup\setup_windows.bat
```

### What the Setup Script Does

The setup script performs the following actions automatically:
1. **Checks Python version**: Ensures your active Python version is 3.11+.
2. **Creates a virtual environment**: Sets up a local `.venv` environment at the root of the project to isolate dependencies.
3. **Upgrades pip**: Installs the latest version of pip inside the virtual environment.
4. **Installs dbt-duckdb dependencies**: Installs all required python packages for the local DuckDB dataset located under [jaffle_shop_duckdb](file:///Users/harshit/Desktop/SN/jaffle_shop_duckdb) using its `requirements.txt`.
5. **Installs wren-pydantic**: Installs the local `wren-pydantic` package from [WrenAI/sdk/wren-pydantic](file:///Users/harshit/Desktop/SN/WrenAI/sdk/wren-pydantic) in **editable mode** (`pip install -e`). This compiles the Rust-based Wren core engine.
6. **Installs dashboard dependencies**: Installs `fastapi`, `uvicorn`, `loguru`, and `pydantic-ai` for running the dashboard.
7. **Resolves database paths**: Runs [update_profile.py](file:///Users/harshit/Desktop/SN/setup/update_profile.py) to dynamically update the absolute folder path of your DuckDB database in [jaffle-profile.json](file:///Users/harshit/Desktop/SN/jaffle-wren/jaffle-profile.json).
8. **Asks to start the dashboard**: If `GEMINI_API_KEY` is not present, it prompts you to enter it, exports it, and automatically spins up the FastAPI app.

---

## Manual Step-by-Step Installation (Alternative)

If you prefer to set up the environment manually instead of running the script, execute these commands from the root directory:

```cmd
:: 1. Create virtual environment
python -m venv .venv
call .venv\Scripts\activate

:: 2. Upgrade pip
python -m pip install --upgrade pip

:: 3. Install dbt-duckdb project dependencies
pip install -r jaffle_shop_duckdb\requirements.txt

:: 4. Install local wren-pydantic package in editable mode
pip install -e WrenAI\sdk\wren-pydantic

:: 5. Install dashboard packages
pip install fastapi uvicorn loguru pydantic-ai

:: 6. Dynamically update DuckDB path in config
python setup\update_profile.py
```

---

## Running the Application

### 1. Launching the Web Dashboard (FastAPI + HTML)

The web dashboard provides an interactive chat interface to ask questions about your DuckDB database models.

Ensure your virtual environment is active and run:
```cmd
:: Set your API key
set GEMINI_API_KEY=your_api_key

:: Run the FastAPI server
cd jaffle-wren
python -m uvicorn server:app --reload --port 8000
```
Open your browser and navigate to: [http://localhost:8000](http://localhost:8000)

### 2. Running the Command-Line Agent

To run a quick search query from the terminal:
```cmd
:: Run CLI agent with a sample query
python jaffle-wren\gemini_agent.py "How many customers do we have, and who has the highest lifetime value?"
```

---

## Modifying schemas & dbt rebuilds
- **Rebuilding DuckDB**: The database file `jaffle_shop.duckdb` is already pre-built in the repo. If you need to rebuild or refresh it, run:
  ```cmd
  cd jaffle_shop_duckdb
  dbt build
  ```
- **Updating Wren schemas**: If you update the models (YAML files under `jaffle-wren\models\`), you can compile them to the engine target:
  ```cmd
  cd jaffle-wren
  wren context build && wren memory index
  ```
