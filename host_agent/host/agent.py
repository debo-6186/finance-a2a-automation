import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, AsyncIterable, List

import httpx
import nest_asyncio
from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
)
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from .remote_agent_connection import RemoteAgentConnections
import logging
from logging.handlers import RotatingFileHandler

load_dotenv()
nest_asyncio.apply()

# Set up rotating file logger
logger = logging.getLogger("host_agent")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler("host_agent.log", maxBytes=5*1024*1024, backupCount=3)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class HostAgent:
    """The Host agent."""

    def __init__(
        self,
    ):
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ""
        self._agent = self.create_agent()
        self._user_id = "host_agent"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    async def _async_init_components(self, remote_agent_addresses: List[str]):
        async with httpx.AsyncClient(timeout=300) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, address)
                try:
                    card = await card_resolver.get_agent_card()
                    remote_connection = RemoteAgentConnections(
                        agent_card=card, agent_url=address
                    )
                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card
                except httpx.ConnectError as e:
                    logger.error(f"ERROR: Failed to get agent card from {address}: {e}")
                except Exception as e:
                    logger.error(f"ERROR: Failed to initialize connection for {address}: {e}")

        agent_info = [
            json.dumps({"name": card.name, "description": card.description})
            for card in self.cards.values()
        ]
        logger.info(f"agent_info: {agent_info}")
        self.agents = "\n".join(agent_info) if agent_info else "No friends found"

    @classmethod
    async def create(
        cls,
        remote_agent_addresses: List[str],
    ):
        instance = cls()
        await instance._async_init_components(remote_agent_addresses)
        return instance

    def create_agent(self) -> Agent:
        return Agent(
            model="gemini-2.5-pro",
            name="Host_Agent",
            instruction=self.root_instruction,
            description="This Host agent orchestrates scheduling pickleball with friends.",
            tools=[
                self.send_message,
            ],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        return f"""
        **Role:** You are a stock analysis and suggestion host agent. You orchestrate the entire user interaction, including stock selection, consent, and allocation analysis, by delegating to specialized agents as needed.

        **Conversational Flow for Allocation Analysis:**

        1. **Before suggesting the final allocation:**
            - Always ask the user: "Are you interested in any other stocks outside your current portfolio or allocation?"
            - If the user provides a stock name, add it to the analysis list.
            - If the user says something like "also show me top stocks in finance or banking in USA", delegate to the stock analyser agent using the `suggest_stocks_by_category` tool to show the relevant list from `stock_data.json`.
            - Wait for the user to select stocks from this list, then add the selected stocks to the analysis list.
            - Repeat this process until the user is done adding stocks.

        2. **Before starting the allocation analysis:**
            - Always get final consent: "Are you thinking of any other stocks or sectors to invest in?"
            - If the user says yes, repeat step 1.
            - If the user says no, proceed with the allocation analysis for the selected + portfolio stocks.

        **CRITICAL RULES:**
        * **ONLY suggest stocks from stock_data.json**: Never suggest sectors or stocks that aren't in the available data. The available categories are:
          - USA_TOP_FINANCIAL_STOCKS
          - USA_TOP_AUTOMOBILE_STOCKS  
          - USA_TOP_TECHNOLOGY_STOCKS
          - INDIA_TOP_FINANCIAL_STOCKS
          - INDIA_TOP_AUTOMOBILE_STOCKS
          - INDIA_TOP_TECHNOLOGY_STOCKS
        * **Ask for specific sectors**: Instead of assuming sectors like "Healthcare" or "Financials", ask the user: "Which sector would you like to consider? Available options are: Technology, Financial, or Automobile for USA/India."
        * **Consider existing portfolio stocks**: When analyzing allocation, include stocks from the user's current portfolio if they are good candidates for the new allocation.
        * **No assumptions**: Don't suggest diversification into sectors not in stock_data.json. Only work with the available data.
        * **Use correct tool names**: When delegating to the stock analyser agent, use `suggest_stocks_by_category` tool, not `show_stock_list`.

        **Workflow:**
        1. **Ask for Investment Amount:** Only, ask the user for the amount they want to invest.
        2. **Report Analysis:** Perform an analysis of the provided stock report. The stock report is already provided so no need to ask for it again. Check all the stocks in the report.
        3. **Stock Analysis:** For each ticker found in the report, perform a detailed stock analysis.
        4. **Investment Suggestion:** Based on the stock analysis, and the current allocation from the report analysis, suggest:
            - The allocation of new stocks (ONLY from stock_data.json categories)
            - The amount to buy for each stock
            - The number of stocks to buy (either in full or fractional shares), ensuring the total does not exceed the user's specified amount

        **Directives:**
        * Use the provided tools and delegate to other agents as needed (e.g., for report, stock, or company analysis).
        * Do not invent or assume any financial data.
        * Your responses must be clear, concise, and easy to understand. Use bullet points or tables where appropriate.
        * Use the `send_message` tool to delegate tasks to other agents.
        * When suggesting diversification, only mention sectors available in stock_data.json.
        * When delegating stock suggestions, use the `suggest_stocks_by_category` tool in the stock analyser agent.

        **Today's Date (YYYY-MM-DD):** {datetime.now().strftime("%Y-%m-%d")}

        <Available Agents>
        {self.agents}
        </Available Agents>
        """

    async def stream(
        self, query: str, session_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        """
        Streams the agent's response to a given query.
        """
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )
        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session.id, new_message=content
        ):
            if event.is_final_response():
                response = ""
                if (
                    event.content
                    and event.content.parts
                    and event.content.parts[0].text
                ):
                    response = "\n".join(
                        [p.text for p in event.content.parts if p.text]
                    )
                yield {
                    "is_task_complete": True,
                    "content": response,
                }
            else:
                yield {
                    "is_task_complete": False,
                    "updates": "The host agent is thinking...",
                }

    async def send_message(self, agent_name: str, task: str, tool_context: ToolContext):
        """Sends a task to a remote friend agent."""
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        client = self.remote_agent_connections[agent_name]

        if not client:
            raise ValueError(f"Client not available for {agent_name}")

        # Simplified task and context ID management
        state = tool_context.state
        task_id = state.get("task_id", str(uuid.uuid4()))
        context_id = state.get("context_id", str(uuid.uuid4()))
        message_id = str(uuid.uuid4())

        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": task}],
                "messageId": message_id,
                "taskId": task_id,
                "contextId": context_id,
            },
        }

        message_request = SendMessageRequest(
            id=message_id, params=MessageSendParams.model_validate(payload)
        )
        send_response: SendMessageResponse = await client.send_message(message_request)
        logger.info(f"send_response {send_response}")

        if not isinstance(
            send_response.root, SendMessageSuccessResponse
        ) or not isinstance(send_response.root.result, Task):
            logger.error("Received a non-success or non-task response. Cannot proceed.")
            return

        response_content = send_response.root.model_dump_json(exclude_none=True)
        json_content = json.loads(response_content)

        resp = []
        if json_content.get("result", {}).get("artifacts"):
            for artifact in json_content["result"]["artifacts"]:
                if artifact.get("parts"):
                    resp.extend(artifact["parts"])
        return resp


def _get_initialized_host_agent_sync():
    """Synchronously creates and initializes the HostAgent."""

    async def _async_main():
        # Hardcoded URLs for the friend agents
        agent_urls = [
            "http://localhost:10002",  # Stock Analyser Agent
            "http://localhost:10003",  # Stock Report Analyser Agent
        ]

        logger.info("initializing host agent")
        hosting_agent_instance = await HostAgent.create(
            remote_agent_addresses=agent_urls
        )
        logger.info("HostAgent initialized")
        return hosting_agent_instance.create_agent()

    try:
        return asyncio.run(_async_main())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.warning(
                f"Warning: Could not initialize HostAgent with asyncio.run(): {e}. "
                "This can happen if an event loop is already running (e.g., in Jupyter). "
                "Consider initializing HostAgent within an async function in your application."
            )
        else:
            raise


root_agent = _get_initialized_host_agent_sync()
