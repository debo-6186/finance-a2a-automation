import os
import sys
from typing import Dict, Any
import asyncio
from contextlib import asynccontextmanager

import click
import uvicorn

from stockprice_agent.agent import StockPriceAgent  # You need to implement this
from stockprice_agent.agentexecutor import StockPriceAgentExecutor  # You need to implement this
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from a2a.server.tasks import InMemoryTaskStore

load_dotenv(override=True)

app_context: Dict[str, Any] = {}

@asynccontextmanager
async def app_lifespan(context: Dict[str, Any]):
    """Manages the lifecycle of shared resources (none needed for this agent)."""
    print("Lifespan: No special resources to initialize for StockPriceAgent.")
    try:
        yield
    finally:
        print("Lifespan: No special resources to clean up for StockPriceAgent.")
        context.clear()

@click.command()
@click.option(
    "--host", "host", default="localhost", help="Hostname to bind the server to."
)
@click.option(
    "--port", "port", default=10004, type=int, help="Port to bind the server to."
)
@click.option("--log-level", "log_level", default="info", help="Uvicorn log level.")
def cli_main(host: str, port: int, log_level: str):
    """Command Line Interface to start the Stock Price Agent server."""
    # If you need an API key for a stock price provider, check for it here
    # if not os.getenv("STOCK_API_KEY"):
    #     print("STOCK_API_KEY environment variable not set.", file=sys.stderr)
    #     sys.exit(1)

    async def run_server_async():
        async with app_lifespan(app_context):
            # Initialize StockPriceAgentExecutor (no tools needed)
            stock_agent_executor = StockPriceAgentExecutor()

            request_handler = DefaultRequestHandler(
                agent_executor=stock_agent_executor,
                task_store=InMemoryTaskStore(),
            )

            # Create the A2AServer instance
            a2a_server = A2AStarletteApplication(
                agent_card=get_agent_card(host, port), http_handler=request_handler
            )

            # Get the ASGI app from the A2AServer instance
            asgi_app = a2a_server.build()

            config = uvicorn.Config(
                app=asgi_app,
                host=host,
                port=port,
                log_level=log_level.lower(),
                lifespan="auto",
            )

            uvicorn_server = uvicorn.Server(config)

            print(
                f"Starting Uvicorn server at http://{host}:{port} with log-level {log_level}..."
            )
            try:
                await uvicorn_server.serve()
            except KeyboardInterrupt:
                print("Server shutdown requested (KeyboardInterrupt).")
            finally:
                print("Uvicorn server has stopped.")

    try:
        asyncio.run(run_server_async())
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            print(
                "Critical Error: Attempted to nest asyncio.run(). This should have been prevented.",
                file=sys.stderr,
            )
        else:
            print(f"RuntimeError in cli_main: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred in cli_main: {e}", file=sys.stderr)
        sys.exit(1)

def get_agent_card(host: str, port: int):
    """Returns the Agent Card for the Stock Price Agent."""
    capabilities = AgentCapabilities(streaming=False, pushNotifications=True)
    skill = AgentSkill(
        id="stock_price_lookup",
        name="Fetch Real-Time Stock Price",
        description="Fetches the real-time price of a US stock based on its ticker symbol.",
        tags=["stock price", "realtime", "finance", "US market"],
        examples=[
            "Get the current price for AAPL",
            "Fetch the latest price for TSLA",
        ],
    )
    return AgentCard(
        name="Stock Price Agent",
        description="Fetches real-time prices for US stocks based on ticker symbols.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text", "text/plain"],
        defaultOutputModes=["text", "text/plain"],
        capabilities=capabilities,
        skills=[skill],
    )

if __name__ == "__main__":
    cli_main()
