import os
import sys
from pathlib import Path
from pydantic_ai import Agent
from wren_pydantic import WrenToolkit

def main():
    # Resolve API Key
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required to run the Gemini model.", file=sys.stderr)
        print("Please export it in your terminal first:", file=sys.stderr)
        print("  export GEMINI_API_KEY=your_gemini_api_key", file=sys.stderr)
        sys.exit(1)

    project_path = Path(__file__).parent.resolve()
    print(f"Loading Wren project from: {project_path}")
    
    # Initialize the Wren toolkit from current project directory
    toolkit = WrenToolkit.from_project(project_path)
    
    # Initialize the Pydantic AI agent with Gemini
    # We use 'google:gemini-flash-lite-latest' which matches Google's Gemini API
    model_name = "google:gemini-flash-lite-latest"
    print(f"Initializing Pydantic AI Agent with model: {model_name}")
    
    agent = Agent(
        model_name,
        instructions=toolkit.instructions(),
        toolsets=[toolkit.toolset()],
    )

    # Accept a question from command line arguments or use a default one
    question = sys.argv[1] if len(sys.argv) > 1 else "How many customers do we have, and who has the highest lifetime value?"
    print(f"\nAsking Agent: '{question}'")
    print("-" * 50)
    
    # Run the agent synchronously
    result = agent.run_sync(question)
    print("\nAgent Response:")
    print(result.output)

if __name__ == "__main__":
    main()
