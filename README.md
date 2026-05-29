# WrenAI + DuckDB Gemini Agent Workspace

Welcome to the team workspace for our WrenAI-powered semantic querying project. This repository integrates a dbt project (DuckDB), Wren Engine context layers, and a FastAPI + Gemini AI dashboard.

## Repository Layout

- **[WrenAI/](file:///Users/harshit/Desktop/SN/WrenAI)**: Core repository containing the Rust-based semantic engines and Python SDK (`wren-pydantic`).
- **[jaffle_shop_duckdb/](file:///Users/harshit/Desktop/SN/jaffle_shop_duckdb)**: The underlying dbt project utilizing DuckDB. Contains the source tables, seed data, and model compilation.
- **[jaffle-wren/](file:///Users/harshit/Desktop/SN/jaffle-wren)**: The semantic modeling definitions (MDL YAML files), CLI Gemini agent, and FastAPI dashboard frontend/backend.
- **[setup/](file:///Users/harshit/Desktop/SN/setup)**: Script automation and onboarding documentation for developers.

---

## Onboarding & Setup

Please follow the onboarding guide specific to your operating system to set up your Python virtual environment, compile requirements, resolve local database connection paths, and launch the application:

- **macOS / Linux users**: Follow the **[macOS Onboarding Guide](file:///Users/harshit/Desktop/SN/setup/README_mac.md)**
- **Windows users**: Follow the **[Windows Onboarding Guide](file:///Users/harshit/Desktop/SN/setup/README_windows.md)**

### Quick Start (Automation Scripts)

- **macOS / Linux**:
  ```bash
  chmod +x setup/setup_mac.sh
  ./setup/setup_mac.sh
  ```
- **Windows (CMD)**:
  ```cmd
  setup\setup_windows.bat
  ```

These scripts will handle package compilation, update configuration file paths locally, verify dependencies, set your Gemini API key, and launch the FastAPI web server immediately.
