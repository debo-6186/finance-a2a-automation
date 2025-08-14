import asyncio
import json
import uuid
import os
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
from google.adk.tools import FunctionTool
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
        # New instance variables for stock management
        self.stock_report_response: str = ""
        self.existing_portfolio_stocks: List[str] = []
        self.new_stocks: List[str] = []
        self.investment_amount: float = 0.0
        self.receiver_email_id: str = ""
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
        connection_errors = []
        
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=60.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        ) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, address)
                try:
                    logger.info(f"Attempting to connect to agent at {address}")
                    card = await card_resolver.get_agent_card()
                    remote_connection = RemoteAgentConnections(
                        agent_card=card, agent_url=address
                    )
                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card
                    logger.info(f"Successfully connected to {card.name} at {address}")
                except httpx.ConnectError as e:
                    error_msg = f"ConnectError: Failed to connect to {address}: {e}"
                    logger.error(error_msg)
                    connection_errors.append(error_msg)
                except httpx.ReadTimeout as e:
                    error_msg = f"ReadTimeout: Agent at {address} is not responding: {e}"
                    logger.error(error_msg)
                    connection_errors.append(error_msg)
                except httpx.ConnectTimeout as e:
                    error_msg = f"ConnectTimeout: Agent at {address} is not reachable: {e}"
                    logger.error(error_msg)
                    connection_errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Unexpected error connecting to {address}: {e}"
                    logger.error(error_msg)
                    connection_errors.append(error_msg)

        # Log connection summary
        if self.remote_agent_connections:
            logger.info(f"Successfully connected to {len(self.remote_agent_connections)} agents: {list(self.remote_agent_connections.keys())}")
        else:
            logger.error("❌ No agents connected successfully!")
            logger.error("Connection errors:")
            for error in connection_errors:
                logger.error(f"  - {error}")
        
        if connection_errors:
            logger.warning(f"⚠️ {len(connection_errors)} connection errors occurred during initialization")

        agent_info = [
            json.dumps({"name": card.name, "description": card.description})
            for card in self.cards.values()
        ]
        logger.info(f"agent_info: {agent_info}")
        self.agents = "\n".join(agent_info) if agent_info else "No agents connected"

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
            model="gemini-2.5-flash",
            name="Host_Agent",
            instruction=self.root_instruction,
            description="This Host agent orchestrates scheduling pickleball with friends.",
            tools=[
                FunctionTool(self.send_message),
                FunctionTool(self.store_stock_report_response),
                FunctionTool(self.store_investment_amount),
                FunctionTool(self.store_receiver_email_id),
                FunctionTool(self.get_investment_amount),
                FunctionTool(self.add_existing_stocks),
                FunctionTool(self.add_new_stocks),
                FunctionTool(self.get_stock_lists),
                FunctionTool(self.analyze_all_stocks),
                FunctionTool(self.suggest_stocks_by_category),
                FunctionTool(self.get_agent_status),
                FunctionTool(self.test_agent_connection),
            ],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        return f"""
        **Role:** You are a stock list coordinator and delegation agent. Your ONLY job is to:
        1. Collect stocks from user's portfolio (via stock report analyser agent)
        2. Collect additional stocks the user wants to analyze
        3. Create a comprehensive list of "stocks to analyze"
        4. Delegate the analysis to the stock analyser agent
        5. Present the results to the user
        
        **YOU DO NOT PERFORM ANY ANALYSIS YOURSELF** - You only coordinate and delegate.

        **STRICT WORKFLOW - FOLLOW EXACTLY:**

        **STEP 1:** When user asks for stock allocation based on portfolio:
        - IMMEDIATELY use `send_message` to send portfolio statement to `stock_report_analyser_agent`
        - Tell user: "I'm analyzing your portfolio statement. This will take about a minute."
        - WAIT for response from stock report analyser agent

        **STEP 2:** After getting response from stock report analyser agent:
        - Store the response automatically
        - Extract existing stocks from the response and add them using `add_existing_stocks`
        - Show user their existing stock list (no analysis, just the list)

        **STEP 3:** Ask user: "How much do you want to invest?"

        **STEP 4:** After user provides investment amount:
        - Store the investment amount using `store_investment_amount`
        
        - Ask user: "Do you want to invest in any other stocks? You can choose from automobile, technology, or financial sectors in India or USA, or specify any other sector. 
        - Tell user that they can choose a specific stock or a sector. Tell user that you can give list of top stocks in a sector"
        - If user mentions a sector: Use `suggest_stocks_by_category` to get stocks from that sector, then add user selected stocks using `add_new_stocks`
        - ** You must show the stocks from the sector to the user, till user confirms the selection.**
        - If user mentions a specific stock: Add them using `add_new_stocks`

        **STEP 5:** Ask user the email id to send the analysis to and store it using `store_receiver_email_id`

        **STEP 6:** Prepare comprehensive analysis:
        - Use `analyze_all_stocks` to prepare the analysis request
        - IMMEDIATELY after getting the result from `analyze_all_stocks`, use `send_message(agent_name='stock_analyser_agent', task='[USE THE EXACT RESULT FROM analyze_all_stocks] Email ID: {self.receiver_email_id}')`
        - Tell user: "I'm analyzing all stocks for comprehensive recommendations. This will take about a minute."
        - WAIT for response from stock analyser agent
        - Do a stock analysis

        **CRITICAL RULES:**
        - NEVER skip any step
        - ALWAYS wait for agent responses before proceeding
        - ALWAYS use the exact tools specified
        - ALWAYS inform user about waiting times

        **AVAILABLE SECTORS:**
        * **ONLY suggest stocks from stock_data.json**: Never suggest sectors or stocks that aren't in the available data. The available categories are:
          - USA_TOP_FINANCIAL_STOCKS
          - USA_TOP_AUTOMOBILE_STOCKS  
          - USA_TOP_TECHNOLOGY_STOCKS
          - INDIA_TOP_FINANCIAL_STOCKS
          - INDIA_TOP_AUTOMOBILE_STOCKS
          - INDIA_TOP_TECHNOLOGY_STOCKS
        * **Ask for specific sectors**: When user wants to invest in other sectors, ask: "Which sector would you like to consider? Available options are: Technology, Financial, or Automobile for USA/India."
        * **Consider existing portfolio stocks**: When analyzing allocation, include stocks from the user's current portfolio if they are good candidates for the new allocation.
        * **No assumptions**: Don't suggest diversification into sectors not in stock_data.json. Only work with the available data.

        **Available Tools:**
        * `send_message`: Delegate tasks to other agents
        * `store_stock_report_response`: Manually store stock report response
        * `store_investment_amount`: Store the investment amount
        * `store_receiver_email_id`: Store the email ID to send analysis to
        * `add_existing_stocks`: Add stocks from portfolio statement
        * `add_new_stocks`: Add new stocks user wants to consider
        * `get_stock_lists`: View current state of all lists
        * `analyze_all_stocks`: Create list of stocks to analyze and prepare delegation request
        * `suggest_stocks_by_category`: Get stocks from specific categories (e.g., 'USA_TOP_TECHNOLOGY_STOCKS')
        * `get_agent_status`: Check status of connected agents (for debugging)
        * `test_agent_connection`: Test connection to a specific agent (for debugging)

        **Directives:**
        * **FOLLOW THE STRICT WORKFLOW EXACTLY** - Do not deviate from the 6 steps outlined above
        * **ALWAYS WAIT** for agent responses before proceeding to the next step
        * **ALWAYS INFORM** users about waiting times (about a minute)
        * **ONLY COORDINATE AND DELEGATE** - Do not perform any analysis yourself
        * Use the provided tools to create lists and delegate to other agents
        * Do not invent or assume any financial data
        * Your responses must be clear, concise, and easy to understand
        * When suggesting diversification, only mention sectors available in stock_data.json
        * Use the `suggest_stocks_by_category` tool directly to get stocks from specific categories

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

    async def _send_message_async(self, agent_name: str, task: str):
        """Internal async method for sending messages to remote agents."""
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        connection = self.remote_agent_connections[agent_name]

        if not connection:
            raise ValueError(f"Connection not available for {agent_name}")

        # Simplified task and context ID management
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
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
        
        try:
            logger.info(f"Sending message to {agent_name} with task length: {len(task)} characters")
            
            # Create a completely fresh httpx client and A2AClient for this request
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=60.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            ) as http_client:
                # Create a completely fresh A2AClient with the new httpx client
                from a2a.client import A2AClient
                temp_agent_client = A2AClient(http_client, connection.card, url=connection.agent_url)
                
                # Send the message using the temporary client
                send_response: SendMessageResponse = await temp_agent_client.send_message(message_request)
            
            logger.info(f"Successfully received response from {agent_name}")

            if not isinstance(
                send_response.root, SendMessageSuccessResponse
            ) or not isinstance(send_response.root.result, Task):
                logger.error("Received a non-success or non-task response. Cannot proceed.")
                return f"Error: Received invalid response from {agent_name}"

            response_content = send_response.root.model_dump_json(exclude_none=True)
            json_content = json.loads(response_content)

            resp = []
            if json_content.get("result", {}).get("artifacts"):
                for artifact in json_content["result"]["artifacts"]:
                    if artifact.get("parts"):
                        resp.extend(artifact["parts"])
            
            # Log the response details for debugging
            logger.info(f"Response from {agent_name} contains {len(resp)} parts")
            for i, part in enumerate(resp):
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        logger.info(f"Response part {i+1} (text): {len(part.get('text', ''))} characters")
                        logger.debug(f"Response part {i+1} preview: {part.get('text', '')[:200]}...")
                    else:
                        logger.info(f"Response part {i+1} (type: {part.get('type', 'unknown')})")
                elif isinstance(part, str):
                    logger.info(f"Response part {i+1} (string): {len(part)} characters")
                    logger.debug(f"Response part {i+1} preview: {part[:200]}...")
            
            # Automatically store response from stock report analyser agent
            if agent_name.lower() == "stock_report_analyser_agent" and resp:
                # Extract text content from response parts
                response_text = ""
                for part in resp:
                    if isinstance(part, dict) and part.get("type") == "text":
                        response_text += part.get("text", "")
                    elif isinstance(part, str):
                        response_text += part
                
                if response_text:
                    self.stock_report_response = response_text
                    logger.info(f"Automatically stored response from {agent_name}: {len(response_text)} characters")
            
            # Log when we're about to return the response to the host agent
            logger.info(f"Returning response from {agent_name} to host agent: {len(resp)} parts")
            return resp
            
        except httpx.ReadTimeout as e:
            error_msg = f"ReadTimeout error when communicating with {agent_name}: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}. The agent may be processing a large request. Please try again."
            
        except httpx.ConnectTimeout as e:
            error_msg = f"ConnectTimeout error when communicating with {agent_name}: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}. The agent may be unavailable. Please check if the agent is running."
            
        except httpx.RequestError as e:
            error_msg = f"RequestError when communicating with {agent_name}: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}. Please try again later."
            
        except Exception as e:
            error_msg = f"Unexpected error when communicating with {agent_name}: {e}"
            logger.error(f"{error_msg}. Full error details: {type(e).__name__}: {str(e)}")
            return f"Error: {error_msg}. Please try again or contact support."

    def send_message(self, agent_name: str, task: str):
        """Sends a task to a remote friend agent with simple retry logic."""
        try:
            # Check if any agents are connected
            if not self.remote_agent_connections:
                error_msg = "No agents are currently connected. Please check if the stock analyser and stock report analyser agents are running."
                logger.error(error_msg)
                return f"Error: {error_msg}"
            
            # Check if agent is available
            if agent_name not in self.remote_agent_connections:
                available_agents = list(self.remote_agent_connections.keys())
                error_msg = f"Agent '{agent_name}' not found. Available agents: {available_agents}"
                logger.error(error_msg)
                return f"Error: {error_msg}"
            
            # Simple synchronous execution with retry only on failure
            import asyncio
            max_retries = 3
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    # Always create a new event loop for this call
                    result = asyncio.run(self._send_message_async(agent_name, task))
                    logger.info(f"Successfully sent message to {agent_name} on attempt {attempt + 1}")
                    return result
                    
                except Exception as e:
                    last_error = e
                    error_msg = str(e).lower()
                    
                    # Only retry on specific failure types
                    is_retryable = any(keyword in error_msg for keyword in [
                        'timeout', 'connection', 'network', 'unavailable', 'server error'
                    ])
                    
                    if attempt < max_retries - 1 and is_retryable:
                        wait_time = (2 ** attempt) * 2  # 2s, 4s, 8s
                        logger.warning(f"Attempt {attempt + 1} failed for {agent_name}: {e}. Retrying in {wait_time}s...")
                        import time
                        time.sleep(wait_time)
                    else:
                        if attempt >= max_retries - 1:
                            logger.error(f"All {max_retries} attempts failed for {agent_name}. Last error: {e}")
                        else:
                            logger.error(f"Non-retryable error on attempt {attempt + 1} for {agent_name}: {e}")
                        break
            
            # If we get here, all attempts failed
            error_msg = f"Failed to send message to {agent_name} after {max_retries} attempts. Last error: {last_error}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
            
        except Exception as e:
            error_msg = f"Error sending message to {agent_name}: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

    def store_stock_report_response(self, response: str):
        """Stores the response received from the stock report analyser agent."""
        self.stock_report_response = response
        logger.info(f"Stored stock report response: {len(response)} characters")
        return f"Stock report response stored successfully. Response length: {len(response)} characters"

    def store_investment_amount(self, amount: float):
        """Stores the investment amount for stock analysis."""
        self.investment_amount = amount
        logger.info(f"Stored investment amount: ${amount:,.2f}")
        return f"Investment amount stored successfully: ${amount:,.2f}"

    def store_receiver_email_id(self, email_id: str):
        """Stores the receiver email ID for sending stock analysis."""
        self.receiver_email_id = email_id
        logger.info(f"Stored receiver email ID: {email_id}")
        return f"Receiver email ID stored successfully: {email_id}"

    def get_investment_amount(self):
        """Returns the stored investment amount."""
        if self.investment_amount > 0:
            return f"Current investment amount: ${self.investment_amount:,.2f}"
        else:
            return "No investment amount has been set yet."

    def add_existing_stocks(self, stocks: List[str]):
        """Adds existing portfolio stocks to the list."""
        for stock in stocks:
            stock_upper = stock.upper().strip()
            if stock_upper not in self.existing_portfolio_stocks:
                self.existing_portfolio_stocks.append(stock_upper)
        logger.info(f"Added {len(stocks)} existing stocks. Total: {len(self.existing_portfolio_stocks)}")
        return f"Added {len(stocks)} existing portfolio stocks. Current list: {', '.join(self.existing_portfolio_stocks)}"

    def add_new_stocks(self, stocks: List[str]):
        """Adds new stocks to the list."""
        for stock in stocks:
            stock_upper = stock.upper().strip()
            if stock_upper not in self.new_stocks:
                self.new_stocks.append(stock_upper)
        logger.info(f"Added {len(stocks)} new stocks. Total: {len(self.new_stocks)}")
        return f"Added {len(stocks)} new stocks. Current list: {', '.join(self.new_stocks)}"

    def get_stock_lists(self):
        """Returns the current stock lists, investment amount, and report response."""
        result = "**Current Investment Information:**\n\n"
        
        # Add investment amount
        result += f"**Investment Amount:**\n"
        if self.investment_amount > 0:
            result += f"${self.investment_amount:,.2f}\n\n"
        else:
            result += "Not set yet.\n\n"
        
        # Add receiver email ID
        result += f"**Receiver Email ID:**\n"
        if self.receiver_email_id:
            result += f"{self.receiver_email_id}\n\n"
        else:
            result += "Not set yet.\n\n"
        
        result += f"**Existing Portfolio Stocks ({len(self.existing_portfolio_stocks)}):**\n"
        if self.existing_portfolio_stocks:
            for i, stock in enumerate(self.existing_portfolio_stocks, 1):
                result += f"{i}. {stock}\n"
        else:
            result += "No existing portfolio stocks added yet.\n"
        
        result += f"\n**New Stocks ({len(self.new_stocks)}):**\n"
        if self.new_stocks:
            for i, stock in enumerate(self.new_stocks, 1):
                result += f"{i}. {stock}\n"
        else:
            result += "No new stocks added yet.\n"
        
        result += f"\n**Stock Report Response:**\n"
        if self.stock_report_response:
            result += f"Response stored ({len(self.stock_report_response)} characters)\n"
            result += f"Preview: {self.stock_report_response[:200]}...\n"
        else:
            result += "No stock report response stored yet.\n"
        
        return result

    def analyze_all_stocks(self):
        """Creates a comprehensive list of stocks to analyze and prepares the delegation request."""
        all_stocks = self.existing_portfolio_stocks + self.new_stocks
        
        if not all_stocks:
            return "No stocks available for analysis. Please add stocks to the lists first."
        
        if not self.stock_report_response:
            return "No stock report response available. Please store the report response first."
        
        # Create the delegation request with the list of stocks to analyze
        delegation_request = f"""
        **STOCKS TO ANALYZE - DELEGATION REQUEST**

        **PORTFOLIO REPORT (for context):**
        {self.stock_report_response}

        **COMPLETE LIST OF STOCKS TO ANALYZE:**
        - Existing Portfolio Stocks: {', '.join(self.existing_portfolio_stocks) if self.existing_portfolio_stocks else 'None'}
        - New Stocks to Consider: {', '.join(self.new_stocks) if self.new_stocks else 'None'}
        - Total Stocks for Analysis: {len(all_stocks)}

        **INVESTMENT AMOUNT:**
        {self.investment_amount}

        **RECEIVER EMAIL ID:**
        {self.receiver_email_id if self.receiver_email_id else 'Not specified'}

        **DELEGATION INSTRUCTIONS:**
        Please analyze all the stocks listed above and provide comprehensive recommendations.
        Consider the portfolio report for context and provide allocation suggestions.
        Consider the investment amount and provide allocation suggestions.
        """
        
        logger.info(f"Created list of {len(all_stocks)} stocks to analyze")
        
        # Return the delegation request that should be sent to stock analyser agent
        return delegation_request.strip()

    def get_agent_status(self):
        """Returns the status of connected agents for debugging purposes."""
        result = "**Connected Agents Status:**\n\n"
        
        if not self.remote_agent_connections:
            result += "❌ **No agents connected.**\n\n"
            result += "**Troubleshooting Steps:**\n"
            result += "1. **Check if agents are running:**\n"
            result += "   - Stock Analyser Agent should be running on port 10002\n"
            result += "   - Stock Report Analyser Agent should be running on port 10003\n"
            result += "2. **Start the agents:**\n"
            result += "   - Navigate to stockanalyser_agent directory and run: `python -m __main__`\n"
            result += "   - Navigate to stockreport_analyser_agent directory and run: `python -m __main__`\n"
            result += "3. **Check ports:** Ensure ports 10002 and 10003 are not being used by other applications\n"
            result += "4. **Restart host agent:** After starting the agents, restart this host agent\n\n"
            result += "**Expected URLs:**\n"
            result += "- http://localhost:10002 (Stock Analyser Agent)\n"
            result += "- http://localhost:10003 (Stock Report Analyser Agent)\n"
            return result
        
        for agent_name, connection in self.remote_agent_connections.items():
            result += f"✅ **{agent_name}**: Connected\n"
            result += f"   - URL: {connection.agent_url}\n"
            result += f"   - Description: {connection.agent_card.description}\n"
            result += f"   - Skills: {[skill.name for skill in connection.agent_card.skills]}\n\n"
        
        result += f"**Total Connected Agents:** {len(self.remote_agent_connections)}"
        logger.info(f"Agent status requested. Connected agents: {list(self.remote_agent_connections.keys())}")
        return result

    def test_agent_connection(self, agent_name: str):
        """Tests the connection to a specific agent."""
        if not self.remote_agent_connections:
            return "❌ No agents are connected. Use 'get_agent_status' to see troubleshooting steps."
        
        if agent_name not in self.remote_agent_connections:
            available_agents = list(self.remote_agent_connections.keys())
            return f"❌ Agent '{agent_name}' not found. Available agents: {available_agents}"
        
        connection = self.remote_agent_connections[agent_name]
        result = f"**Connection Test for {agent_name}:**\n\n"
        result += f"✅ **Status**: Connected\n"
        result += f"📡 **URL**: {connection.agent_url}\n"
        result += f"📋 **Description**: {connection.agent_card.description}\n"
        result += f"🛠️ **Skills**: {[skill.name for skill in connection.agent_card.skills]}\n"
        result += f"📊 **Version**: {connection.agent_card.version}\n\n"
        result += f"**Connection appears to be working properly.**"
        
        logger.info(f"Connection test requested for {agent_name}")
        return result

    def suggest_stocks_by_category(self, category: str):
        """
        Retrieves a list of stocks from a specified category.
        
        Args:
            category: The full category name (e.g., 'USA_TOP_AUTOMOBILE_STOCKS', 'INDIA_TOP_TECHNOLOGY_STOCKS')
        """
        stock_data_path = os.path.join(os.path.dirname(__file__), "stock_data.json")
        
        if not os.path.exists(stock_data_path):
            return "Error: stock_data.json not found. Please ensure it's in the correct directory."

        try:
            with open(stock_data_path, "r") as f:
                stock_data = json.load(f)
            
            if category not in stock_data:
                available_categories = list(stock_data.keys())
                return f"Error: Category '{category}' not found. Available categories:\n" + "\n".join(available_categories)
            
            stocks_in_category = stock_data[category]
            if not stocks_in_category:
                return f"No stocks found in category: {category}."
            
            result = f"**Top stocks for category '{category}':**\n\n"
            result += f"**Number of stocks:** {len(stocks_in_category)}\n\n"
            result += "**Stock tickers:**\n"
            for i, stock in enumerate(stocks_in_category, 1):
                result += f"{i}. {stock}\n"
            
            result += f"\n**Analysis:**\n"
            result += f"These {len(stocks_in_category)} stocks represent the top performers in this category and can be considered for portfolio allocation.\n"
            result += f"You can add selected stocks to your analysis using the `add_new_stocks` tool."
            
            logger.info(f"Retrieved {len(stocks_in_category)} stocks for category: {category}")
            return result
            
        except FileNotFoundError:
            return "Error: stock_data.json not found. Please ensure it's in the correct directory."
        except json.JSONDecodeError:
            return "Error: Failed to decode stock_data.json file."
        except Exception as e:
            logger.error(f"Error suggesting stocks by category: {e}")
            return f"Error suggesting stocks by category: {e}"


def _get_initialized_host_agent_sync():
    """Synchronously creates and initializes the HostAgent."""

    async def _async_main():
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
