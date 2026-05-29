import os
import sys
import io
import contextlib
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pydantic_ai import Agent
from wren_pydantic import WrenToolkit
from loguru import logger

# Initialize FastAPI app
app = FastAPI(title="Wren AI Gemini Dashboard")

# Resolve API Key early
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("Warning: GEMINI_API_KEY / GOOGLE_API_KEY environment variable is not set. The server will start, but queries will fail until the key is set.", file=sys.stderr)

# Initialize Wren Toolkit
project_path = Path(__file__).parent.resolve()
toolkit = WrenToolkit.from_project(project_path)

# Initialize Pydantic AI Agent
model_name = "google:gemini-flash-lite-latest"
agent = Agent(
    model_name,
    instructions=toolkit.instructions(),
)

from typing import Any
from wren_pydantic._tools import _run_query, _run_dry_plan, _run_list_models

@agent.tool_plain(retries=2)
def wren_list_models() -> list[Any]:
    """List all models in this Wren project with column counts."""
    print(">>> Agent is calling wren_list_models() to retrieve schema metadata...")
    res = _run_list_models(toolkit)
    print(f"    [Success] {len(res)} models retrieved from metadata.")
    return res

@agent.tool_plain(retries=2)
def wren_dry_plan(sql: str) -> str:
    """Plan SQL through MDL and return the target-dialect SQL.

    Cheap (no DB round-trip). Use this to verify your SQL
    targets Wren models correctly before running wren_query.
    """
    print(f">>> Agent is calling wren_dry_plan(sql={sql!r}) to validate/expand target SQL...")
    res = _run_dry_plan(toolkit, sql)
    print(">>> Target-dialect SQL planned successfully:")
    print(f"    {res.strip()}")
    return res

@agent.tool_plain(retries=2)
def wren_query(sql: str, limit: int = 100) -> Any:
    """Execute SQL through the Wren semantic layer and return rows.

    Use after wren_dry_plan looks correct. Default limit is 100;
    increase only when needed. Hard cap is 1000 rows — beyond
    that, aggregate in SQL.
    """
    print(f">>> Agent is calling wren_query(sql={sql!r}, limit={limit}) to fetch data...")
    res = _run_query(toolkit, sql, limit)
    print(f"    [Success] Query completed. Retrieved {res.row_count} rows.")
    return res


class QueryRequest(BaseModel):
    question: str

class DualStringIO(io.StringIO):
    """StringIO wrapper that also writes to the true system stdout so terminal output remains visible."""
    def write(self, s):
        sys.__stdout__.write(s)
        return super().write(s)

@contextlib.contextmanager
def capture_all_logs():
    buffer = DualStringIO()
    
    # Intercept loguru (used by wren-engine)
    loguru_sink_id = logger.add(buffer, format="{time:HH:mm:ss} | {level} | {message}", level="DEBUG")
    
    # Intercept standard logging
    std_handler = logging.StreamHandler(buffer)
    std_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    root_logger = logging.getLogger()
    root_logger.addHandler(std_handler)
    
    # Intercept sys.stdout and sys.stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = buffer
    sys.stderr = buffer
    
    try:
        yield buffer
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        root_logger.removeHandler(std_handler)
        logger.remove(loguru_sink_id)

@app.get("/api/env")
def get_env():
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    google_key = os.environ.get("GOOGLE_API_KEY", "")
    return {
        "GEMINI_API_KEY": gemini_key[:8] + "..." if gemini_key else "Not Set",
        "GOOGLE_API_KEY": google_key[:8] + "..." if google_key else "Not Set"
    }

@app.post("/api/ask")
async def ask_agent(req: QueryRequest):
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise HTTPException(
            status_code=400,
            detail="GEMINI_API_KEY / GOOGLE_API_KEY is not set. Please set it in your environment."
        )
    
    print(f"Received question: {req.question}")
    
    # Execute the agent and capture all generated logs
    with capture_all_logs() as log_buffer:
        try:
            print(">>> Starting Gemini Agent execution loop...")
            result = await agent.run(req.question)
            print(">>> Execution completed successfully.")
            output_text = result.output
        except Exception as e:
            print(f">>> ERROR during execution: {str(e)}")
            output_text = f"An error occurred: {str(e)}"
            
    captured_logs = log_buffer.getvalue()
    return {
        "output": output_text,
        "logs": captured_logs
    }

# Serve the static files
static_dir = project_path / "static"
static_dir.mkdir(exist_ok=True)

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
