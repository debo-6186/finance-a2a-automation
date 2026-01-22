import asyncio
import json
import uuid
import os
import time
import threading
import shutil
from datetime import datetime
from typing import Any, AsyncIterable, List, Tuple

import boto3
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
from .document_analyzer import read_portfolio_document, extract_stock_tickers_from_text, verify_portfolio_document, verify_text_portfolio
import logging

# Import database functions and models at the top
try:
    from database import get_db, get_session, mark_portfolio_statement_uploaded, get_agent_state, update_agent_state, get_conversation_history, User
    from config import current_config
except ImportError:
    # Handle case where database module is in parent directory
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import get_db, get_session, mark_portfolio_statement_uploaded, get_agent_state, update_agent_state, get_conversation_history, User
    from config import current_config

load_dotenv()
nest_asyncio.apply()

# Set up logger - will use parent logger's handlers (host_agent_api)
logger = logging.getLogger("host_agent_api.host_agent")
logger.setLevel(logging.INFO)


class HostAgent:
    """The Host agent."""

    def __init__(
        self,
    ):
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ""
        # Keep only session tracking in memory - all other state goes to database
        self.current_session_id = {"id": "", "user_id": "", "is_file_uploaded": False}  # Store current session info
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

    def _load_state(self) -> dict:
        """Load conversation state from database for current session."""
        session_id = self.current_session_id.get("id")
        if not session_id:
            logger.warning("⚠️ No session_id available in current_session_id, returning empty state")
            logger.warning(f"   current_session_id = {self.current_session_id}")
            return {
                "stock_report_response": "",
                "existing_portfolio_stocks": [],
                "new_stocks": [],
                "investment_amount": 0.0,
                "receiver_email_id": "",
                "diversification_preference": "",
                "share_counts": {}
            }

        try:
            logger.info(f"📖 Loading state for session {session_id}...")
            db = next(get_db())
            agent_state = get_agent_state(db, session_id, "host_agent")
            db.close()

            if agent_state and agent_state.state_data:
                state = json.loads(agent_state.state_data)
                logger.info(f"✓ Loaded existing state for session {session_id}")
                logger.info(f"   State keys: {list(state.keys())}")
                logger.info(f"   investment_amount: {state.get('investment_amount', 0)}")
                logger.info(f"   diversification_preference: {state.get('diversification_preference', 'NOT SET')[:50]}...")
                logger.info(f"   existing_portfolio_stocks count: {len(state.get('existing_portfolio_stocks', []))}")
                logger.info(f"   new_stocks count: {len(state.get('new_stocks', []))}")
                return state
            else:
                logger.info(f"ℹ️ No existing state found in database for session {session_id}, returning defaults")
                return {
                    "stock_report_response": "",
                    "existing_portfolio_stocks": [],
                    "new_stocks": [],
                    "investment_amount": 0.0,
                    "receiver_email_id": "",
                    "diversification_preference": "",
                    "share_counts": {}
                }
        except Exception as e:
            logger.error(f"✗ Error loading state for session {session_id}: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            return {
                "stock_report_response": "",
                "existing_portfolio_stocks": [],
                "new_stocks": [],
                "investment_amount": 0.0,
                "receiver_email_id": "",
                "diversification_preference": "",
                "share_counts": {}
            }

    def _save_state(self, state: dict):
        """Save conversation state to database for current session."""
        session_id = self.current_session_id.get("id")
        if not session_id:
            logger.warning("⚠️ No session_id available in current_session_id, cannot save state")
            logger.warning(f"   current_session_id = {self.current_session_id}")
            return

        try:
            logger.info(f"💾 Saving state for session {session_id}...")
            logger.info(f"   State keys: {list(state.keys())}")
            logger.info(f"   investment_amount: {state.get('investment_amount', 0)}")
            logger.info(f"   diversification_preference: {state.get('diversification_preference', 'NOT SET')[:50]}...")
            logger.info(f"   existing_portfolio_stocks count: {len(state.get('existing_portfolio_stocks', []))}")
            logger.info(f"   new_stocks count: {len(state.get('new_stocks', []))}")

            db = next(get_db())
            update_agent_state(db, session_id, "host_agent", json.dumps(state))
            db.close()
            logger.info(f"✓ Successfully saved state for session {session_id}")
        except Exception as e:
            logger.error(f"✗ Error saving state for session {session_id}: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")

    def create_agent(self) -> Agent:
        max_retries = 5  # Increased retries for API reliability
        base_delay = 2   # Base delay in seconds

        for attempt in range(max_retries):
            try:
                return Agent(
                    model="gemini-2.5-flash",
                    name="Host_Agent",
                    instruction=self.root_instruction,
                    description="This Host agent orchestrates stock allocation logic.",
                    tools=[
                        FunctionTool(self.send_message),
                        FunctionTool(self.store_portfolio_file),
                        FunctionTool(self.check_file_upload_status),
                        FunctionTool(self.read_and_analyze_portfolio),
                        FunctionTool(self.analyze_text_portfolio),
                        FunctionTool(self.store_stock_report_response),
                        FunctionTool(self.store_market_preference),
                        FunctionTool(self.get_market_preference),
                        FunctionTool(self.store_investment_amount),
                        FunctionTool(self.store_diversification_preference),
                        FunctionTool(self.store_receiver_email_id),
                        FunctionTool(self.get_investment_amount),
                        FunctionTool(self.add_existing_stocks),
                        FunctionTool(self.add_new_stocks),
                        FunctionTool(self.store_share_count),
                        FunctionTool(self.get_share_counts),
                        FunctionTool(self.get_stock_lists),
                        FunctionTool(self.answer_general_stock_question),
                        FunctionTool(self.analyze_all_stocks),
                        FunctionTool(self.suggest_stocks_by_category),
                        FunctionTool(self.get_agent_status),
                        FunctionTool(self.test_agent_connection),
                    ],
                )
            except Exception as e:
                error_message = str(e)
                is_api_error = any(code in error_message for code in ["500", "503", "INTERNAL", "UNAVAILABLE"])

                logger.warning(f"Agent creation attempt {attempt + 1} failed: {e}")

                if attempt == max_retries - 1:
                    logger.error(f"Failed to create agent after {max_retries} attempts")
                    raise

                if is_api_error:
                    # Exponential backoff for API errors with jitter
                    import random
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.info(f"Google AI API error detected, retrying in {delay:.2f}s...")
                    time.sleep(delay)
                else:
                    # Linear backoff for other errors
                    time.sleep(base_delay * (attempt + 1))

    def root_instruction(self, context: ReadonlyContext) -> str:
        # Access context to satisfy linter requirement
        _ = context
        return f"""
        **SCOPE RESTRICTION - READ THIS FIRST:**
        You are a specialized portfolio analyzer and stock recommender bot. You can ONLY answer questions related to:
        - Stock portfolio analysis and management
        - Stock recommendations and investment strategies
        - Portfolio diversification and allocation
        - Stock market data and analysis
        - Investment preferences and amounts

        **HANDLING OFF-TOPIC QUESTIONS:**
        1. **If a question is outside your portfolio analysis workflow BUT still related to stocks/stock market:**
           - Examples: "What is a stock split?", "How does the stock market work?", "What's the current price of AAPL?", "What is P/E ratio?"
           - Use the `answer_general_stock_question` tool with the user's question
           - Return the answer from the tool to the user
           - After answering, gently guide them back to the portfolio analysis workflow if they haven't completed it yet

        2. **If a question is completely unrelated to stocks, markets, or finance:**
           - Examples: "What's the weather?", "How do I cook pasta?", "Tell me a joke"
           - Respond with: "I am a portfolio analyzer and stock recommender bot. I can only assist with questions related to stocks, portfolios, and investment strategies. Please ask me about your portfolio analysis, stock recommendations, or investment planning."

        **How to determine if a question is stock-related:**
        - Does it mention stocks, shares, companies, market, trading, investing, or financial terms?
        - Is it asking about stock market concepts, mechanisms, or data?
        - If YES to any of these, use `answer_general_stock_question` tool
        - If NO to all, give the rejection message above

        **Role:** You are a stock portfolio coordinator agent. Your job is to:
        1. Analyze the user's portfolio
        2. Collect investment preferences
        3. Coordinate stock analysis
        4. Send results to the user via email

        **YOU DO NOT PERFORM ANY FINANCIAL ANALYSIS YOURSELF** - You only coordinate and delegate to the Stock Analyser Agent.

        **CRITICAL FIRST MESSAGE REQUIREMENT:**
        - **ALWAYS START** by checking if market preference has been set using `get_market_preference`
        - If NO market preference exists yet, your **FIRST MESSAGE MUST BE** the greeting and asking about market preference
        - Use this EXACT greeting for first-time users: "Hello! Welcome to the portfolio analysis service. Before we begin, I need to know which market you'd like to invest in.

        Are you interested in:
        1. US Market (stocks like AAPL, GOOGL, MSFT, etc.)
        2. Indian Market (stocks like RELIANCE.NS, TCS.BO, INFY.NS, etc.)

        Please specify 'US' or 'India'."

        **WORKFLOW - FOLLOW THESE STEPS IN ORDER:**

        **STEP 0: Get Market Preference**
        - FIRST, use `get_market_preference` to check if market preference has been set
        - If NOT set, show the greeting message above and wait for user response
        - WAIT for user to specify 'US' or 'India' (or variations like 'USA', 'United States', 'Indian', etc.)
        - Store using `store_market_preference` with value "US" or "INDIA" (normalized)
        - Proceed immediately to STEP 1

        **STEP 1: Analyze Portfolio**
        - FIRST, use `check_file_upload_status` to check if portfolio data has been provided (via file or text)
        - If NO portfolio data, ask user: "Please provide your portfolio details using any of these methods:
          1. Upload a PDF portfolio statement
          2. Upload a screenshot/snapshot of your portfolio
          3. Type your stock holdings directly in the chat (e.g., 'AAPL 30%, GOOGL 20%, MSFT 50%')

        How would you like to share your portfolio?"
        - If portfolio data exists, proceed with analysis

        **If file is uploaded (PDF or image):**
        - Inform user: "Your portfolio has been uploaded. I'm analyzing it now. This will take about a minute."
        - Use `read_and_analyze_portfolio` tool with current session ID to analyze the portfolio
        - WAIT for the response from the tool
        - Extract existing stocks from the response and add them using `add_existing_stocks`
        - Show user their existing stock list from the portfolio

        **If user provides portfolio as text:**
        - Identify when user types portfolio data (stock tickers with/without percentages)
        - Use `analyze_text_portfolio` tool with the user's text input
        - WAIT for the response from the tool
        - Extract existing stocks from the response and add them using `add_existing_stocks`
        - Show user their existing stock list from the portfolio

        - Once portfolio is analyzed (regardless of format), proceed to STEP 1.5

        **STEP 1.5: Collect Missing Share Counts (CRITICAL FOR SELL RECOMMENDATIONS)**
        - After portfolio analysis, check the portfolio response for "**Holdings Missing Share Counts**" section
        - If ANY stocks are missing share counts, you MUST ask for them BEFORE proceeding
        - For EACH stock missing share counts:
          1. Ask: "How many shares of [TICKER] do you currently own? (Approximate is fine, but needed for SELL recommendations)"
          2. WAIT for user response
          3. If user provides a number (exact or approximate), use `store_share_count(ticker="[TICKER]", shares=[NUMBER])`
          4. If user says "I don't know" or "I don't remember", respond: "Please provide at least an estimate. Knowing approximately how many shares you own is critical for determining if we should recommend selling any positions. Even a rough number helps."
          5. If user still cannot provide an estimate after reminder, acknowledge and note that SELL recommendations cannot be made for that stock
        - Repeat for ALL stocks missing share counts
        - Once all share counts are collected (or acknowledged as unavailable), proceed to STEP 2

        **STEP 2: Get Investment Amount**
        - BEFORE asking, check if investment amount is already set using `get_investment_amount`
        - If NOT set, ask: "How much do you want to invest?"
        - WAIT for user response
        - Store the amount using `store_investment_amount`
        - Proceed immediately to STEP 3

        **STEP 3: Get Investment Preference**
        - BEFORE asking, check `get_stock_lists` to see if diversification_preference is already set
        - If NOT set, ask: "What type of investor are you? Please describe your investment strategy. For example:
          • 'Long-term investor looking for stable growth over 5-10 years'
          • 'Short-term trader looking for quick gains in 3-6 months'
          • 'Only interested in technology and healthcare stocks'
          • 'High-risk, high-reward investments'
          • 'Dividend-paying stocks for passive income'
          • Or describe your own strategy"
        - WAIT for user response
        - Store the COMPLETE response using `store_diversification_preference`
        - Proceed immediately to STEP 4

        **STEP 4: Check for Additional Stocks**
        - BEFORE asking, check `get_stock_lists` to see if new stocks have been discussed
        - If NOT discussed yet, ask: "Do you want to invest in any other stocks besides your existing portfolio?
          • Say 'yes' to add more stocks from specific sectors (Technology, Financial, or Automobile)
          • Specify stock tickers directly (e.g., 'AAPL', 'TSLA' for US or 'RELIANCE.NS', 'TCS.BO' for India)
          • Say 'no' if you only want to analyze your existing portfolio"
        - WAIT for user response

        **If user wants to add more stocks:**
        - If user mentions a sector: Use `suggest_stocks_by_category` with the appropriate category name:
          * **For US Market users:** USA_TOP_TECHNOLOGY_STOCKS, USA_TOP_FINANCIAL_STOCKS, USA_TOP_AUTOMOBILE_STOCKS
          * **For India Market users:** INDIA_TOP_TECHNOLOGY_STOCKS, INDIA_TOP_FINANCIAL_STOCKS, INDIA_TOP_AUTOMOBILE_STOCKS
          * **IMPORTANT:** Only use categories matching the user's market preference (check with `get_market_preference`)
        - Show the stocks from that category
        - Ask user to select specific tickers from the list
        - WAIT for user to select tickers
        - Add selected stocks using `add_new_stocks` (will auto-validate against market preference)
        - Ask: "Would you like to add stocks from another sector?" and repeat if yes

        **If user mentions specific stock tickers:**
        - Add them directly using `add_new_stocks` (will auto-validate against market preference)
        - The tool will reject stocks that don't match the user's selected market
        - Ask: "Would you like to add any more stocks?" and repeat if yes

        **If user says 'no':**
        - Proceed immediately to STEP 5

        - After all stocks are added, proceed immediately to STEP 5

        **STEP 5: Get Email and Trigger Analysis**
        - BEFORE asking, check `get_stock_lists` to see if receiver_email_id is already set
        - If NOT set, ask: "Please provide your email address so we can send you the detailed stock allocation report."
        - WAIT for user response
        - When user provides email, IMMEDIATELY EXECUTE: `store_receiver_email_id(email_id="<user's email>")`
        - This is a FUNCTION CALL that MUST be EXECUTED
        - Return EXACTLY what the tool returns without any modification
        - The tool will automatically trigger stock analysis and send it in the background
        - After calling this tool, the conversation ENDS (tool returns end_session signal)

        **CRITICAL REQUIREMENTS:**
        - ALWAYS check if information is already stored before asking (use `get_investment_amount` and `get_stock_lists`)
        - NEVER ask the same question twice
        - Each step executes ONCE per session
        - ALWAYS wait for user responses and tool responses
        - In STEP 5, you MUST call `store_receiver_email_id` tool - do NOT generate the response yourself
        - The `store_receiver_email_id` tool automatically triggers the analysis and returns the completion message

        **AVAILABLE SECTORS:**
        Only suggest stocks from these categories in stock_data.json:
        - USA_TOP_FINANCIAL_STOCKS
        - USA_TOP_AUTOMOBILE_STOCKS
        - USA_TOP_TECHNOLOGY_STOCKS
        - INDIA_TOP_FINANCIAL_STOCKS
        - INDIA_TOP_AUTOMOBILE_STOCKS
        - INDIA_TOP_TECHNOLOGY_STOCKS

        **Available Tools:**
        * `check_file_upload_status`: Check if portfolio file has been uploaded
        * `read_and_analyze_portfolio`: Analyze portfolio document (PDF or image) and extract stock tickers
        * `analyze_text_portfolio`: Analyze portfolio data provided as text input
        * `add_existing_stocks`: Add stocks from portfolio statement
        * `store_market_preference`: Store user's market preference (US or INDIA)
        * `get_market_preference`: Check user's market preference
        * `add_new_stocks`: Add new stocks user wants to consider (auto-validates against market preference)
        * `store_share_count`: Store share count for a stock ticker (critical for SELL recommendations)
        * `get_share_counts`: View all stored share counts
        * `store_investment_amount`: Store the investment amount
        * `store_diversification_preference`: Store user's investment strategy
        * `store_receiver_email_id`: Store email ID and trigger stock analysis
        * `get_investment_amount`: Check if investment amount is set
        * `get_stock_lists`: View current state of all stored information
        * `answer_general_stock_question`: Answer general stock market questions using external knowledge (use for stock-related questions outside the workflow)
        * `suggest_stocks_by_category`: Get stocks from categories matching user's market preference
        * `analyze_all_stocks`: Create comprehensive analysis request
        * `send_message`: Delegate to Stock Analyser Agent

        **Key Points:**
        * Be clear and concise in your responses
        * Only coordinate and delegate - do not perform financial analysis
        * Follow the workflow strictly in the order specified
        * Check what information is already stored before asking questions
        * The stock analysis happens in the background after you call `store_receiver_email_id`

        **Today's Date (YYYY-MM-DD):** {datetime.now().strftime("%Y-%m-%d")}

        <Available Agents>
        {self.agents}
        </Available Agents>
        """

    async def stream(
        self, query: str, session_id: str, user_id: str = ""
    ) -> AsyncIterable[dict[str, Any]]:
        """
        Streams the agent's response to a given query.
        """
        # Store the current session ID and user ID for use in tool functions
        self.current_session_id = {"id": session_id, "user_id": user_id, "is_file_uploaded": False}

        # Load existing state at the start of each conversation turn
        # This ensures the agent has access to previously saved data
        logger.info(f"🔄 Starting conversation turn for session {session_id}")
        existing_state = self._load_state()
        logger.info(f"   Loaded state has {len(existing_state.get('existing_portfolio_stocks', []))} existing stocks, "
                   f"{len(existing_state.get('new_stocks', []))} new stocks, "
                   f"investment amount: {existing_state.get('investment_amount', 0)}")

        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )

        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )

        # Load conversation history from database on EVERY request
        # This ensures the agent always has the full conversation context
        # Add it as context to the current message instead of trying to modify the session
        conversation_context = ""
        try:
            logger.info(f"📚 Loading conversation history from database for session {session_id}")
            db = next(get_db())
            history_messages = get_conversation_history(db, session_id, limit=50)
            db.close()

            if history_messages:
                logger.info(f"   Found {len(history_messages)} historical messages")

                # Build conversation history as a text summary
                history_lines = []
                for msg in history_messages:
                    role = "User" if msg.message_type == "user" else "Assistant"
                    history_lines.append(f"{role}: {msg.content}")

                conversation_context = "\n".join(history_lines)
                logger.info(f"✓ Loaded {len(history_messages)} messages as conversation context")
            else:
                logger.info(f"   No historical messages found for session {session_id}")

        except Exception as e:
            logger.error(f"✗ Error loading conversation history: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")

        # Prepend conversation history to the current query if we have it
        if conversation_context:
            original_query = query
            query = f"[Previous conversation context - DO NOT repeat these questions, continue from where we left off]:\n{conversation_context}\n\n[Current user message]:\n{original_query}"
            logger.info(f"   Added conversation context to query ({len(history_messages)} previous messages)")

        # Create content AFTER modifying query with conversation history
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        try:
            async for event in self._runner.run_async(
                user_id=self._user_id, session_id=session.id, new_message=content
            ):
                if event.is_final_response():
                    response = ""
                    if event.content and event.content.parts:
                        # Filter out non-text parts and handle structured responses
                        text_parts = []
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                text_parts.append(part.text)
                            elif hasattr(part, 'function_call'):
                                # Log function calls but don't include in response
                                logger.info(f"Function call detected in response: {part.function_call}")
                            elif hasattr(part, 'thought_signature'):
                                # Log thought signatures but don't include in response
                                logger.info(f"Thought signature detected in response: {part.thought_signature}")

                        if text_parts:
                            response = "\n".join(text_parts)
                        else:
                            logger.warning("No text parts found in final response, using fallback")
                            response = "Task completed successfully."

                    yield {
                        "is_task_complete": True,
                        "content": response,
                    }
                else:
                    yield {
                        "is_task_complete": False,
                        "updates": "The host agent is thinking...",
                    }
        except Exception as e:
            error_message = str(e)
            if "500 INTERNAL" in error_message or "503 UNAVAILABLE" in error_message:
                logger.error(f"Google AI API error in stream: {error_message}")
                yield {
                    "is_task_complete": True,
                    "content": "I'm experiencing temporary connectivity issues with the AI service. Please try again in a moment.",
                }
            else:
                logger.error(f"Unexpected error in stream: {error_message}")
                yield {
                    "is_task_complete": True,
                    "content": "An unexpected error occurred. Please try again.",
                }

    async def _send_message_async(self, agent_name: str, task: str):
        """Internal async method for sending messages to remote agents."""
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        connection = self.remote_agent_connections[agent_name]

        if not connection:
            raise ValueError(f"Connection not available for {agent_name}")

        # Simplified task and context ID management - let the remote agent create the task
        context_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())

        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": task}],
                "messageId": message_id,
                "contextId": context_id,
            },
        }

        message_request = SendMessageRequest(
            id=message_id, params=MessageSendParams.model_validate(payload)
        )
        
        try:
            logger.info(f"========== ASYNC MESSAGE SEND STARTING ==========")
            logger.info(f"Agent: {agent_name}, Task length: {len(task)} characters")
            logger.info(f"Context ID: {context_id}, Message ID: {message_id}")
            logger.info(f"Connection URL: {connection}")

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
            
            # Debug logging to understand response structure
            logger.info(f"Response type: {type(send_response)}")
            logger.info(f"Response root type: {type(send_response.root)}")
            if hasattr(send_response.root, 'result'):
                logger.info(f"Response root result type: {type(send_response.root.result)}")
            else:
                logger.info("Response root has no 'result' attribute")
            logger.info(f"Response root content: {send_response.root}")

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
                    state = self._load_state()
                    state["stock_report_response"] = response_text
                    self._save_state(state)
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
            # Replace placeholder with actual session ID if present
            if "[current_session_id]" in task and self.current_session_id["id"]:
                task = task.replace("[current_session_id]", self.current_session_id["id"])
                logger.info(f"Replaced session ID placeholder. Task now: {task}")
            
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

    def send_message_background(self, agent_name: str, task: str):
        """Send message in background without blocking."""
        import threading
        import asyncio

        logger.info(f"========== SEND_MESSAGE_BACKGROUND CALLED ==========")
        logger.info(f"========== AGENT: {agent_name} ==========")
        logger.info(f"========== TASK LENGTH: {len(task)} characters ==========")

        def run_in_background():
            try:
                logger.info(f"Background thread started for {agent_name}")
                asyncio.run(self._send_message_async(agent_name, task))
                logger.info(f"Background thread completed successfully for {agent_name}")
            except Exception as e:
                logger.error(f"Background send_message failed for {agent_name}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")

        thread = threading.Thread(target=run_in_background, daemon=True)
        thread.start()
        logger.info(f"Started background task to send message to {agent_name} (thread: {thread.name})")

    def store_portfolio_file(self, user_name: str, file_path: str, session_id: str):
        """Stores the uploaded portfolio file to local storage or AWS S3 bucket depending on environment.
        Supports PDF and image file formats.
        """
        try:
            # Use provided session_id
            target_session_id = session_id

            # Get file extension from source file
            file_ext = os.path.splitext(file_path)[1]

            # Determine input format type
            if file_ext.lower() == '.pdf':
                input_format = 'pdf'
            elif file_ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                input_format = 'image'
            else:
                input_format = 'unknown'

            # Generate filename using the specified format with correct extension
            filename = f"{user_name}_{target_session_id}_portfolio_statement{file_ext}"

            logger.info(f"Portfolio file upload requested for user: {user_name}")
            logger.info(f"Source file path: {file_path}")
            logger.info(f"Target filename: {filename}")
            logger.info(f"File format: {input_format}")
            logger.info(f"Session ID: {target_session_id}")
            logger.info(f"Environment: {current_config.ENVIRONMENT}")

            # Check if local or production environment
            if current_config.is_local():
                # LOCAL STORAGE
                storage_path = current_config.LOCAL_STORAGE_PATH
                logger.info(f"Using local storage: {storage_path}")

                # Create directory if it doesn't exist
                os.makedirs(storage_path, exist_ok=True)

                # Copy file to local storage
                target_file_path = os.path.join(storage_path, filename)
                shutil.copy2(file_path, target_file_path)

                logger.info(f"File uploaded to local storage: {target_file_path}")
                storage_location = target_file_path

            else:
                # S3 STORAGE (Production)
                bucket_name = current_config.S3_BUCKET_NAME
                logger.info(f"Using S3 bucket: {bucket_name}")

                # Initialize S3 client
                s3_client = boto3.client('s3')

                # Upload file to S3
                s3_client.upload_file(file_path, bucket_name, filename)

                logger.info(f"File uploaded to S3: s3://{bucket_name}/{filename}")
                storage_location = f"s3://{bucket_name}/{filename}"

            # Update database to mark portfolio statement as uploaded with format type
            if target_session_id:
                try:
                    db = next(get_db())
                    success = mark_portfolio_statement_uploaded(db, target_session_id, input_format=input_format)
                    if success:
                        logger.info(f"Database updated: portfolio_statement_uploaded = True ({input_format}) for session {target_session_id}")
                    else:
                        logger.warning(f"Failed to update database for session {target_session_id}")
                    db.close()
                except Exception as db_error:
                    logger.error(f"Error updating database for session {target_session_id}: {db_error}")
                    # Don't fail the upload if database update fails

            return f"Portfolio file stored successfully at: {storage_location}"

        except Exception as e:
            error_msg = f"Error storing portfolio file: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

    def check_file_upload_status(self):
        """Check if a file has been uploaded for the current session."""
        try:
            session_id = self.current_session_id["id"]
            if not session_id:
                logger.warning("No session ID available for file upload status check")
                return "File upload status: NO SESSION ID - cannot check status"
            
            # Check database for actual upload status
            try:
                db = next(get_db())
                session = get_session(db, session_id)
                db.close()
                
                if session and session.portfolio_statement_uploaded:
                    # Update in-memory flag to match database
                    self.current_session_id["is_file_uploaded"] = True
                    logger.info(f"File upload status check: File HAS been uploaded for session {session_id} (verified from database)")
                    return f"File upload status: UPLOADED for session {session_id}"
                else:
                    logger.info(f"File upload status check: File NOT yet uploaded for session {session_id} (verified from database)")
                    return f"File upload status: NOT UPLOADED for session {session_id}"
                    
            except Exception as db_error:
                logger.error(f"Database error checking file upload status: {db_error}")
                # Fall back to in-memory check
                is_uploaded = self.current_session_id["is_file_uploaded"]
                if is_uploaded:
                    logger.info(f"File upload status check (fallback): File HAS been uploaded for session {session_id}")
                    return f"File upload status: UPLOADED for session {session_id} (fallback check)"
                else:
                    logger.info(f"File upload status check (fallback): File NOT yet uploaded for session {session_id}")
                    return f"File upload status: NOT UPLOADED for session {session_id} (fallback check)"
                    
        except Exception as e:
            error_msg = f"Error checking file upload status: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

    def store_stock_report_response(self, response: str):
        """Stores the response received from the stock report analyser agent."""
        state = self._load_state()
        state["stock_report_response"] = response
        self._save_state(state)
        logger.info(f"Stored stock report response: {len(response)} characters")
        return f"Stock report response stored successfully. Response length: {len(response)} characters"

    def store_investment_amount(self, amount: float):
        """Stores the investment amount for stock analysis."""
        logger.info(f"🔧 TOOL CALLED: store_investment_amount(amount={amount})")
        state = self._load_state()
        state["investment_amount"] = amount
        self._save_state(state)
        logger.info(f"✓ Stored investment amount: ${amount:,.2f}")
        return f"Investment amount stored successfully: ${amount:,.2f}"

    def store_market_preference(self, market: str):
        """Stores the user's market preference (US or INDIA).

        Args:
            market: The market preference - should be "US" or "INDIA"
        """
        logger.info(f"🔧 TOOL CALLED: store_market_preference(market='{market}')")

        # Normalize the market value
        market_normalized = market.upper().strip()
        if market_normalized in ["USA", "UNITED STATES", "AMERICA"]:
            market_normalized = "US"
        elif market_normalized in ["IND", "INDIAN", "BHARAT"]:
            market_normalized = "INDIA"

        if market_normalized not in ["US", "INDIA"]:
            logger.warning(f"Invalid market preference: {market}. Expected 'US' or 'INDIA'")
            return f"Error: Invalid market preference '{market}'. Please specify 'US' or 'India'."

        # Store in agent state
        state = self._load_state()
        state["market_preference"] = market_normalized
        self._save_state(state)

        # Also update the database session
        try:
            session_id = self.current_session_id["id"]
            db = next(get_db())
            session = get_session(db, session_id)
            if session:
                session.market_preference = market_normalized
                db.commit()
                logger.info(f"✓ Updated market_preference in database session: {market_normalized}")
            db.close()
        except Exception as db_error:
            logger.error(f"Error updating market_preference in database: {db_error}")

        logger.info(f"✓ Stored market preference: {market_normalized}")
        return f"Market preference stored successfully: {market_normalized} Market"

    def get_market_preference(self):
        """Gets the user's market preference.

        Returns:
            String indicating the market preference status
        """
        logger.info(f"🔧 TOOL CALLED: get_market_preference()")

        # First check agent state
        state = self._load_state()
        market_pref = state.get("market_preference")

        # If not in state, check database
        if not market_pref:
            try:
                session_id = self.current_session_id["id"]
                db = next(get_db())
                session = get_session(db, session_id)
                if session and session.market_preference:
                    market_pref = session.market_preference
                    # Sync to state
                    state["market_preference"] = market_pref
                    self._save_state(state)
                    logger.info(f"✓ Loaded market preference from database: {market_pref}")
                db.close()
            except Exception as db_error:
                logger.error(f"Error loading market_preference from database: {db_error}")

        if market_pref:
            logger.info(f"✓ Market preference is set: {market_pref}")
            return f"Market preference: {market_pref} Market"
        else:
            logger.info(f"✓ Market preference NOT set yet")
            return "Market preference: NOT SET"

    def store_diversification_preference(self, preference: str):
        """Stores the user's complete investment strategy.

        Args:
            preference: The user's detailed investment strategy description
        """
        logger.info(f"🔧 TOOL CALLED: store_diversification_preference(preference='{preference[:100]}...')")
        # Store the FULL preference text, not a simplified version
        state = self._load_state()
        state["diversification_preference"] = preference.strip()
        self._save_state(state)
        logger.info(f"✓ User's investment strategy stored: {state['diversification_preference'][:100]}...")
        return f"Investment strategy stored successfully: {preference[:100]}..."

    def store_receiver_email_id(self, email_id: str):
        """Stores the receiver email ID for sending stock analysis."""
        logger.info(f"========== STORE_RECEIVER_EMAIL_ID FUNCTION CALLED ==========")
        logger.info(f"========== EMAIL ID PARAMETER: {email_id} ==========")

        # Load state and update email
        state = self._load_state()
        state["receiver_email_id"] = email_id
        self._save_state(state)
        logger.info(f"Stored receiver email ID: {email_id}")

        # Check if all prerequisites are met for ending the session
        has_portfolio = False
        has_investment_amount = state["investment_amount"] > 0
        has_stocks = len(state["existing_portfolio_stocks"]) > 0 or len(state["new_stocks"]) > 0
        has_diversification_pref = bool(state["diversification_preference"])

        logger.info(f"========== PREREQUISITES CHECK ==========")
        logger.info(f"Investment amount: ${state['investment_amount']} (valid: {has_investment_amount})")
        logger.info(f"Existing stocks count: {len(state['existing_portfolio_stocks'])}")
        logger.info(f"New stocks count: {len(state['new_stocks'])}")
        logger.info(f"Has stocks: {has_stocks}")
        logger.info(f"Diversification preference: '{state['diversification_preference']}' (valid: {has_diversification_pref})")

        # Check if portfolio statement is uploaded
        try:
            session_id = self.current_session_id["id"]
            if session_id:
                db = next(get_db())
                session = get_session(db, session_id)
                db.close()
                has_portfolio = session and session.portfolio_statement_uploaded
                logger.info(f"Portfolio uploaded (from DB): {has_portfolio} for session {session_id}")
        except Exception as e:
            logger.warning(f"Could not check portfolio upload status: {e}")
            has_portfolio = self.current_session_id.get("is_file_uploaded", False)
            logger.info(f"Portfolio uploaded (fallback): {has_portfolio}")

        logger.info(f"All prerequisites met: {has_portfolio and has_investment_amount and has_stocks and has_diversification_pref}")

        # If all conditions are met, trigger stock analysis and return end session message
        if has_portfolio and has_investment_amount and has_stocks and has_diversification_pref:
            logger.info(f"All prerequisites met for email {email_id}. Triggering stock analysis.")
            
            # Execute STEP 6: Prepare comprehensive analysis
            try:
                # Get analysis request from analyze_all_stocks
                analysis_request = self.analyze_all_stocks()
                logger.info(f"Analysis request: {analysis_request}")
                
                if analysis_request and not analysis_request.startswith("No stocks") and not analysis_request.startswith("Error"):
                    # Send message to stock_analyser_agent
                    task_with_email = f"{analysis_request} Email ID: {email_id}"
                    logger.info(f"Sending analysis request to stock_analyser_agent for email {email_id}")
                    
                    # Send the message asynchronously (don't wait for response)
                    logger.info(f"Sending analysis request to Stock Analyser Agent with task: {task_with_email}")
                    self.send_message_background(agent_name='Stock Analyser Agent', task=task_with_email)
                    logger.info(f"Analysis request sent to Stock Analyser Agent. Ending session.")
                else:
                    logger.error(f"Failed to prepare analysis request: {analysis_request}")
                    
            except Exception as e:
                logger.error(f"Error triggering stock analysis for {email_id}: {e}")
            
            # Return a special JSON string that the API can parse
            import json
            return json.dumps({
                "message": "Stock analysis in progress, we will email you the stock allocation report",
                "end_session": True
            })
        else:
            # Log what's missing for debugging
            missing = []
            if not has_portfolio:
                missing.append("portfolio statement")
            if not has_investment_amount:
                missing.append("investment amount")
            if not has_stocks:
                missing.append("stocks selection")
            if not has_diversification_pref:
                missing.append("diversification preference")
            logger.info(f"Prerequisites not met for {email_id}. Missing: {', '.join(missing)}")

            return f"Receiver email ID stored successfully: {email_id}"

    def get_investment_amount(self):
        """Returns the stored investment amount."""
        state = self._load_state()
        if state["investment_amount"] > 0:
            return f"Current investment amount: ${state['investment_amount']:,.2f}"
        else:
            return "No investment amount has been set yet."

    def add_existing_stocks(self, stocks: List[str]):
        """Adds existing portfolio stocks to the list."""
        logger.info(f"🔧 TOOL CALLED: add_existing_stocks(stocks={stocks})")
        state = self._load_state()
        for stock in stocks:
            stock_upper = stock.upper().strip()
            if stock_upper not in state["existing_portfolio_stocks"]:
                state["existing_portfolio_stocks"].append(stock_upper)
        self._save_state(state)
        logger.info(f"✓ Added {len(stocks)} existing stocks. Total: {len(state['existing_portfolio_stocks'])}")
        return f"Added {len(stocks)} existing portfolio stocks. Current list: {', '.join(state['existing_portfolio_stocks'])}"

    def add_new_stocks(self, stocks: List[str]):
        """Adds new stocks to the list, converting stock names to tickers using LLM."""
        logger.info(f"🔧 TOOL CALLED: add_new_stocks(stocks={stocks})")
        from google import genai
        from google.genai.types import GenerateContentConfig

        state = self._load_state()
        logger.info(f"Using LLM to find stock tickers for: {stocks}")

        # Create the client with proper configuration
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            client = genai.Client(vertexai=True)
            logger.info("Using Vertex AI for ticker lookup")
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("No GOOGLE_API_KEY found for ticker lookup")
                # Fallback to original behavior
                for stock in stocks:
                    stock_upper = stock.upper().strip()
                    if stock_upper not in state["new_stocks"]:
                        state["new_stocks"].append(stock_upper)
                self._save_state(state)
                logger.info(f"Added {len(stocks)} new stocks (fallback mode). Total: {len(state['new_stocks'])}")
                return f"Added {len(stocks)} new stocks (API key missing). Current list: {', '.join(state['new_stocks'])}"
            client = genai.Client(api_key=api_key)
            logger.info("Using Google AI API for ticker lookup")

        # System prompt for ticker lookup
        system_prompt = """You are a financial data expert. Your job is to convert stock names or company names to their correct stock ticker symbols.

For US stocks: Return the ticker symbol (e.g., "AAPL" for Apple)
For Indian stocks: Return the ticker with exchange suffix (e.g., "RELIANCE.NS" for Reliance on NSE, or "RELIANCE.BO" for BSE)

Return ONLY a JSON array of ticker symbols, nothing else. Example: ["AAPL", "MSFT", "RELIANCE.NS"]"""

        # Prepare the ticker lookup request
        stocks_input = ', '.join(stocks)
        ticker_request = f"""Convert the following stock names to their ticker symbols: {stocks_input}

Return ONLY a JSON array of uppercase ticker symbols. If a name is already a ticker, keep it as is."""

        try:
            # Make the LLM call with retry logic
            max_retries = 3
            base_delay = 2
            response = None

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        import random
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.info(f"Retrying ticker lookup after {delay:.2f}s delay (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)

                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=ticker_request,
                        config=GenerateContentConfig(
                            system_instruction=[system_prompt]
                        )
                    )

                    logger.info(f"Successfully generated ticker lookup (attempt {attempt + 1})")
                    break

                except Exception as e:
                    error_message = str(e)
                    is_api_error = any(code in error_message for code in ["500", "503", "INTERNAL", "UNAVAILABLE"])

                    if attempt == max_retries - 1:
                        logger.error(f"Failed to generate ticker lookup after {max_retries} attempts: {e}")
                        raise

                    if is_api_error:
                        logger.warning(f"Google AI API error on attempt {attempt + 1}: {e}")
                    else:
                        logger.warning(f"Unexpected error on attempt {attempt + 1}: {e}")

            # Extract the response text
            response_text = response.text.strip()
            logger.info(f"LLM response for stock tickers: {response_text}")

            # Parse the JSON response
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            tickers = json.loads(response_text)

            # VALIDATE STOCKS AGAINST MARKET PREFERENCE
            market_preference = state.get("market_preference")
            if market_preference:
                logger.info(f"Validating {len(tickers)} new stocks against market preference: {market_preference}")
                is_valid, error_message, valid_tickers, invalid_tickers = self._validate_stocks_against_market_preference(
                    tickers, market_preference
                )

                if not is_valid:
                    logger.warning(f"Stock validation failed: {len(invalid_tickers)} invalid stocks")
                    return error_message

                # Use only valid tickers
                tickers = valid_tickers
                logger.info(f"All {len(tickers)} stocks validated successfully")
            else:
                logger.warning("Market preference not set - skipping stock validation")

            # Add tickers to the list
            added_count = 0
            for ticker in tickers:
                ticker_upper = ticker.upper().strip()
                if ticker_upper not in state["new_stocks"]:
                    state["new_stocks"].append(ticker_upper)
                    added_count += 1

            self._save_state(state)
            logger.info(f"Added {added_count} new stocks. Total: {len(state['new_stocks'])}")
            return f"Added {added_count} new stocks (tickers: {', '.join(tickers)}). Current list: {', '.join(state['new_stocks'])}"

        except Exception as e:
            logger.error(f"Error in LLM ticker lookup: {e}")
            # Fallback to original behavior if LLM call fails
            for stock in stocks:
                stock_upper = stock.upper().strip()
                if stock_upper not in state["new_stocks"]:
                    state["new_stocks"].append(stock_upper)
            self._save_state(state)
            logger.info(f"Added {len(stocks)} new stocks (fallback mode). Total: {len(state['new_stocks'])}")
            return f"Added {len(stocks)} new stocks (using input as-is due to error: {str(e)}). Current list: {', '.join(state['new_stocks'])}"

    def store_share_count(self, ticker: str, shares: float):
        """
        Stores the number of shares for a specific stock ticker.
        This is critical for SELL recommendations.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            shares: Number of shares owned (can be approximate)

        Returns:
            Confirmation message
        """
        logger.info(f"🔧 TOOL CALLED: store_share_count(ticker={ticker}, shares={shares})")
        state = self._load_state()

        # Initialize share_counts dict if it doesn't exist
        if "share_counts" not in state:
            state["share_counts"] = {}

        # Store the share count
        ticker_upper = ticker.upper().strip()
        state["share_counts"][ticker_upper] = float(shares)

        self._save_state(state)
        logger.info(f"✓ Stored {shares} shares for {ticker_upper}")

        return f"Stored {shares} shares for {ticker_upper}. This will be used for portfolio analysis and SELL recommendations."

    def get_share_counts(self):
        """
        Returns all stored share counts.

        Returns:
            Formatted string showing share counts for all stocks
        """
        state = self._load_state()
        share_counts = state.get("share_counts", {})

        if not share_counts:
            return "No share counts have been stored yet."

        result = "**Stored Share Counts:**\n\n"
        for ticker, shares in share_counts.items():
            result += f"• {ticker}: {shares} shares\n"

        return result

    def get_stock_lists(self):
        """Returns the current stock lists, investment amount, and report response."""
        state = self._load_state()
        result = "**Current Investment Information:**\n\n"

        # Add investment amount
        result += f"**Investment Amount:**\n"
        if state["investment_amount"] > 0:
            result += f"${state['investment_amount']:,.2f}\n\n"
        else:
            result += "Not set yet.\n\n"

        # Add receiver email ID
        result += f"**Receiver Email ID:**\n"
        if state["receiver_email_id"]:
            result += f"{state['receiver_email_id']}\n\n"
        else:
            result += "Not set yet.\n\n"

        result += f"**Existing Portfolio Stocks ({len(state['existing_portfolio_stocks'])}):**\n"
        if state["existing_portfolio_stocks"]:
            for i, stock in enumerate(state["existing_portfolio_stocks"], 1):
                result += f"{i}. {stock}\n"
        else:
            result += "No existing portfolio stocks added yet.\n"

        result += f"\n**New Stocks ({len(state['new_stocks'])}):**\n"
        if state["new_stocks"]:
            for i, stock in enumerate(state["new_stocks"], 1):
                result += f"{i}. {stock}\n"
        else:
            result += "No new stocks added yet.\n"

        result += f"\n**Stock Report Response:**\n"
        if state["stock_report_response"]:
            result += f"Response stored ({len(state['stock_report_response'])} characters)\n"
            result += f"Preview: {state['stock_report_response'][:200]}...\n"
        else:
            result += "No stock report response stored yet.\n"

        return result

    def answer_general_stock_question(self, question: str):
        """
        Answers general stock market questions using Perplexity API.

        This function is used for questions that are related to stocks/stock market
        but are outside the current portfolio analysis workflow.

        Args:
            question: The user's question about stocks or the stock market

        Returns:
            Answer from Perplexity API or error message
        """
        try:
            logger.info(f"🔧 TOOL CALLED: answer_general_stock_question(question='{question[:100]}...')")

            # Get Perplexity API key from environment
            perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
            if not perplexity_api_key:
                logger.error("PERPLEXITY_API_KEY not found in environment variables")
                return "I apologize, but I'm unable to answer general stock market questions at the moment due to a configuration issue. Please try asking about your portfolio analysis instead."

            # Use OpenAI client with Perplexity base URL
            from openai import OpenAI

            client = OpenAI(
                api_key=perplexity_api_key,
                base_url="https://api.perplexity.ai"
            )

            # Make the API call to Perplexity
            response = client.chat.completions.create(
                model="sonar",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a knowledgeable stock market expert assistant.
                        Provide accurate, helpful, and concise answers to stock market related questions.
                        Focus on factual information and include relevant data when available.
                        If you mention stock prices or market data, clarify the timeframe.
                        Keep responses clear and user-friendly."""
                    },
                    {
                        "role": "user",
                        "content": question
                    }
                ]
            )

            # Extract the answer
            if response.choices and len(response.choices) > 0:
                answer = response.choices[0].message.content.strip()
                logger.info(f"✓ Successfully answered general stock question using Perplexity API")
                return answer
            else:
                logger.error("No response from Perplexity API")
                return "I apologize, but I couldn't get an answer at the moment. Please try again or ask about your portfolio analysis."

        except Exception as e:
            error_msg = f"Error querying Perplexity API: {e}"
            logger.error(error_msg)
            return f"I apologize, but I encountered an error while trying to answer your question. Please try asking about your portfolio analysis instead, or rephrase your question."

    def analyze_all_stocks(self):
        """Creates a comprehensive list of stocks to analyze and prepares the delegation request."""
        state = self._load_state()
        all_stocks = state["existing_portfolio_stocks"] + state["new_stocks"]

        if not all_stocks:
            return "No stocks available for analysis. Please add stocks to the lists first."

        # Create the delegation request with the list of stocks to analyze
        # Include portfolio report if available, otherwise proceed without it
        portfolio_section = ""
        if state["stock_report_response"]:
            portfolio_section = f"""
        **PORTFOLIO REPORT (for context):**
        {state['stock_report_response']}
        """
        else:
            portfolio_section = """
        **PORTFOLIO REPORT:**
        No existing portfolio report available. Proceeding with analysis based on selected stocks only.
        """

        # Add user's investment strategy to the delegation request
        strategy_instruction = ""
        if state["diversification_preference"] and state["diversification_preference"].strip():
            strategy_instruction = f"""
        **USER'S INVESTMENT STRATEGY:**
        {state['diversification_preference']}

        **CRITICAL REQUIREMENT:**
        - The stock allocation and recommendations MUST align with the user's investment strategy described above
        - Highlight in your analysis how each recommendation fits the user's stated investment goals
        - Tailor risk levels, time horizons, and sector preferences according to the user's strategy
        - If the user specified sector preferences, prioritize those sectors
        - If the user specified risk appetite (high/low risk), adjust recommendations accordingly
        - If the user specified time horizon (long-term/short-term), factor that into your analysis
        """
        else:
            # Default behavior if strategy not set
            strategy_instruction = """
        **INVESTMENT APPROACH:**
        Provide balanced recommendations considering both growth and risk management.
        """

        # Include user ID and session ID in the delegation request
        session_id = self.current_session_id.get("id", "unknown")
        user_id = self.current_session_id.get("user_id", "unknown")

        # Format share counts for delegation
        share_counts = state.get("share_counts", {})
        share_counts_section = ""
        if share_counts:
            share_counts_section = "\n**SHARE COUNTS (for SELL recommendations):**\n"
            for ticker, shares in share_counts.items():
                share_counts_section += f"- {ticker}: {shares} shares\n"
            share_counts_section += "\n**CRITICAL:** Only stocks with known share counts above can have SELL recommendations. Stocks without share counts should be marked HOLD instead of SELL.\n"
        else:
            share_counts_section = "\n**SHARE COUNTS:** Not provided. SELL recommendations cannot be made without share counts.\n"

        delegation_request = f"""
        **STOCKS TO ANALYZE - DELEGATION REQUEST**
        {portfolio_section}
        **COMPLETE LIST OF STOCKS TO ANALYZE:**
        - Existing Portfolio Stocks: {', '.join(state['existing_portfolio_stocks']) if state['existing_portfolio_stocks'] else 'None'}
        - New Stocks to Consider: {', '.join(state['new_stocks']) if state['new_stocks'] else 'None'}
        - Total Stocks for Analysis: {len(all_stocks)}

        **USER ID:**
        {user_id}

        **SESSION ID:**
        {session_id}

        **INVESTMENT AMOUNT:**
        {state['investment_amount']}

        **RECEIVER EMAIL ID:**
        {state['receiver_email_id'] if state['receiver_email_id'] else 'Not specified'}
        {share_counts_section}
        {strategy_instruction}
        **DELEGATION INSTRUCTIONS:**
        Please analyze all the stocks listed above and provide comprehensive recommendations.
        Consider the portfolio report for context and provide allocation suggestions.
        Consider the investment amount and provide allocation suggestions.
        IMPORTANT: Follow the user's investment strategy requirements specified above and ensure your recommendations clearly demonstrate alignment with their stated goals.
        """

        logger.info(f"Created list of {len(all_stocks)} stocks to analyze with diversification preference: {state['diversification_preference']}")

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

    def read_and_analyze_portfolio(self, session_id: str = "") -> str:
        """
        Reads portfolio document (PDF or image) and extracts stock tickers locally.
        Supports multiple document formats.

        Args:
            session_id: The current session ID for tracking (optional, will use current session if not provided)

        Returns:
            Formatted string with stock tickers and allocation percentages
        """
        # Always use the stored current_session_id if available (prevents LLM from using extracted filenames)
        current_id = self.current_session_id.get("id", "")
        if current_id:
            logger.info(f"Using stored current session ID: {current_id} (ignoring parameter: {session_id})")
            session_id = current_id
        elif not session_id or session_id.endswith('.pdf'):
            logger.error(f"No valid session ID available. Provided: {session_id}")
            return "Error: No valid session ID available to retrieve portfolio file."

        logger.info(f"Reading and analyzing portfolio locally for session {session_id}")

        try:
            # Use stored user_id from current_session_id if available
            user_id = self.current_session_id.get("user_id", "")

            if not user_id:
                # Fallback to database query if user_id is not stored
                logger.warning(f"User ID not found in current_session_id, falling back to database query")
                db = next(get_db())
                session = get_session(db, session_id)

                if not session:
                    db.close()
                    return "Error: Session not found. Cannot retrieve portfolio file."

                # Get user info - use user.id (not user.name) as it's what was used during upload
                user = db.query(User).filter(User.id == session.user_id).first()

                # Get the input format from session
                input_format = session.input_format if session.input_format else 'pdf'

                db.close()

                if not user:
                    return "Error: User information not found. Cannot retrieve portfolio file."

                user_id = user.id
            else:
                # Try to get input format from database
                db = next(get_db())
                session = get_session(db, session_id)
                input_format = session.input_format if session and session.input_format else 'pdf'
                db.close()

            logger.info(f"Retrieved user_id: {user_id}, format: {input_format} for session {session_id}")

            # Step 1: Read the document (PDF or image) from storage
            portfolio_text, actual_format = read_portfolio_document(session_id, user_id, input_format)

            if portfolio_text.startswith("Error"):
                logger.error(f"Error reading portfolio: {portfolio_text}")
                return portfolio_text

            logger.info(f"Successfully read portfolio text ({actual_format}): {len(portfolio_text)} characters")

            # Step 2: VERIFY the document is a valid portfolio statement
            logger.info(f"Verifying document is a valid portfolio statement...")

            # Need to re-read the file bytes for verification
            try:
                if current_config.is_local():
                    storage_path = current_config.LOCAL_STORAGE_PATH
                    base_filename = f"{user_id}_{session_id}_portfolio_statement"

                    # Determine file extension
                    if actual_format == 'pdf':
                        file_path = os.path.join(storage_path, base_filename + '.pdf')
                    else:
                        # Try to find image file
                        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
                        file_path = None
                        for ext in image_extensions:
                            test_path = os.path.join(storage_path, base_filename + ext)
                            if os.path.exists(test_path):
                                file_path = test_path
                                break

                    if not file_path or not os.path.exists(file_path):
                        logger.error(f"Could not find file for verification: {file_path}")
                        return "Error: Could not locate file for verification."

                    with open(file_path, 'rb') as f:
                        file_bytes = f.read()
                else:
                    # S3 storage
                    import io
                    bucket_name = current_config.S3_BUCKET_NAME
                    s3_client = boto3.client('s3')
                    base_filename = f"{user_id}_{session_id}_portfolio_statement"

                    if actual_format == 'pdf':
                        filename = base_filename + '.pdf'
                    else:
                        # Try to find image file
                        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
                        filename = None
                        for ext in image_extensions:
                            test_filename = base_filename + ext
                            try:
                                s3_client.head_object(Bucket=bucket_name, Key=test_filename)
                                filename = test_filename
                                break
                            except:
                                continue

                    if not filename:
                        logger.error(f"Could not find file in S3 for verification")
                        return "Error: Could not locate file in S3 for verification."

                    file_obj = io.BytesIO()
                    s3_client.download_fileobj(bucket_name, filename, file_obj)
                    file_obj.seek(0)
                    file_bytes = file_obj.read()

                # Verify the document
                is_valid, verification_message = verify_portfolio_document(file_bytes, actual_format)

                if not is_valid:
                    logger.warning(f"Document verification failed: {verification_message}")
                    return verification_message

                logger.info(f"Document verification passed: {verification_message}")

            except Exception as verify_error:
                logger.error(f"Error during document verification: {verify_error}")
                # Continue with analysis if verification fails due to technical error
                logger.warning("Continuing with analysis despite verification error")

            # Step 3: Extract tickers from the text
            # Get market preference to validate portfolio against it
            state = self._load_state()
            market_preference = state.get("market_preference")
            result = extract_stock_tickers_from_text(portfolio_text, market_preference)

            # Step 4: CRITICAL - Automatically store extracted share counts
            if result and not result.startswith("Error"):
                # Parse the HOLDINGS_DATA_JSON section from the result
                try:
                    if "**HOLDINGS_DATA_JSON:**" in result:
                        json_start = result.find("**HOLDINGS_DATA_JSON:**") + len("**HOLDINGS_DATA_JSON:**")
                        json_str = result[json_start:].strip()

                        # Parse the JSON
                        holdings_data = json.loads(json_str)

                        # Store share counts for each holding that has shares
                        shares_stored_count = 0
                        for holding in holdings_data:
                            ticker = holding.get("ticker")
                            shares = holding.get("shares", 0)

                            if ticker and shares > 0:
                                # Call store_share_count to save to database
                                self.store_share_count(ticker, shares)
                                shares_stored_count += 1
                                logger.info(f"Auto-stored share count: {ticker} = {shares} shares")

                        logger.info(f"Automatically stored share counts for {shares_stored_count} stocks from portfolio")
                except Exception as parse_error:
                    logger.warning(f"Could not parse holdings JSON for auto-storage: {parse_error}")
                    # Continue anyway - the response is still valid

                # Store the response automatically (same as before with remote agent)
                state = self._load_state()
                state["stock_report_response"] = result
                self._save_state(state)
                logger.info(f"Automatically stored portfolio analysis result: {len(result)} characters")

            return result

        except Exception as e:
            error_msg = f"Error in read_and_analyze_portfolio: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

    def analyze_text_portfolio(self, portfolio_text: str) -> str:
        """
        Analyzes portfolio data provided as text input by the user.
        Supports formats like:
        - "AAPL 30%, GOOGL 20%, MSFT 50%"
        - "Apple 30%, Google 20%, Microsoft 50%"
        - "My portfolio: AAPL, GOOGL, MSFT"

        Args:
            portfolio_text: The portfolio data as text

        Returns:
            Formatted string with stock tickers and allocation percentages
        """
        try:
            logger.info(f"Analyzing text-based portfolio input: {len(portfolio_text)} characters")

            if not portfolio_text or len(portfolio_text.strip()) < 3:
                return "Error: Please provide portfolio data in text format."

            # Step 1: VERIFY the text contains valid portfolio information
            logger.info(f"Verifying text contains valid portfolio information...")
            is_valid, verification_message = verify_text_portfolio(portfolio_text)

            if not is_valid:
                logger.warning(f"Text verification failed: {verification_message}")
                return verification_message

            logger.info(f"Text verification passed: {verification_message}")

            # Step 2: Extract tickers from the text using LLM
            # Get market preference to validate portfolio against it
            state = self._load_state()
            market_preference = state.get("market_preference")
            result = extract_stock_tickers_from_text(portfolio_text, market_preference)

            # Store the response automatically if successful
            if result and not result.startswith("Error") and not result.startswith("No stock"):
                # CRITICAL - Automatically store extracted share counts
                try:
                    if "**HOLDINGS_DATA_JSON:**" in result:
                        json_start = result.find("**HOLDINGS_DATA_JSON:**") + len("**HOLDINGS_DATA_JSON:**")
                        json_str = result[json_start:].strip()

                        # Parse the JSON
                        holdings_data = json.loads(json_str)

                        # Store share counts for each holding that has shares
                        shares_stored_count = 0
                        for holding in holdings_data:
                            ticker = holding.get("ticker")
                            shares = holding.get("shares", 0)

                            if ticker and shares > 0:
                                # Call store_share_count to save to database
                                self.store_share_count(ticker, shares)
                                shares_stored_count += 1
                                logger.info(f"Auto-stored share count from text: {ticker} = {shares} shares")

                        logger.info(f"Automatically stored share counts for {shares_stored_count} stocks from text portfolio")
                except Exception as parse_error:
                    logger.warning(f"Could not parse holdings JSON for auto-storage: {parse_error}")
                    # Continue anyway - the response is still valid

                state = self._load_state()
                state["stock_report_response"] = result

                # Mark portfolio statement as uploaded in text format
                current_id = self.current_session_id.get("id", "")
                if current_id:
                    try:
                        db = next(get_db())
                        success = mark_portfolio_statement_uploaded(db, current_id, input_format='text')
                        if success:
                            logger.info(f"Marked portfolio as uploaded (text format) for session {current_id}")
                        db.close()
                    except Exception as db_error:
                        logger.error(f"Error updating database: {db_error}")

                self._save_state(state)
                logger.info(f"Automatically stored text portfolio analysis result: {len(result)} characters")

            return result

        except Exception as e:
            error_msg = f"Error in analyze_text_portfolio: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

    def _validate_stocks_against_market_preference(self, tickers: List[str], market_preference: str) -> Tuple[bool, str, List[str], List[str]]:
        """
        Validates that stock tickers match the user's market preference using LLM.

        Args:
            tickers: List of stock ticker symbols to validate
            market_preference: User's market preference ("US" or "INDIA")

        Returns:
            Tuple of (is_valid, error_message, valid_tickers, invalid_tickers)
        """
        from google import genai
        from google.genai.types import GenerateContentConfig

        try:
            logger.info(f"Validating {len(tickers)} tickers against market preference: {market_preference}")

            # Create the client with proper configuration
            if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
                client = genai.Client(vertexai=True)
            else:
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    logger.error("No GOOGLE_API_KEY found for stock validation")
                    # If no API key, skip validation (lenient fallback)
                    return True, "", tickers, []
                client = genai.Client(api_key=api_key)

            tickers_str = ", ".join(tickers)
            expected_market = "US" if market_preference == "US" else "India"

            # System prompt for stock validation
            system_prompt = f"""You are a financial expert who validates stock tickers against specific stock exchanges.

Your task is to validate whether stock tickers belong to the {expected_market} market/exchange.

VALIDATION RULES:
- **US Market Stocks**: Tickers WITHOUT country suffixes (e.g., AAPL, GOOGL, MSFT, TSLA, JPM, VOO, SPY)
  - Listed on US exchanges (NYSE, NASDAQ, etc.)
  - Usually 1-5 uppercase letters
  - ETFs like VOO, SPY, QQQ are also US market

- **Indian Market Stocks**: Tickers WITH .NS (NSE) or .BO (BSE) suffixes OR Indian company names
  - Listed on Indian exchanges (NSE, BSE)
  - Examples: RELIANCE.NS, TCS.BO, INFY.NS, HDFCBANK, SBIN
  - If ticker lacks suffix but is clearly an Indian company (like RELIANCE, TCS, INFY), classify as Indian

RESPONSE FORMAT - Return ONLY valid JSON:
{{
  "valid_tickers": ["list of tickers matching {expected_market} market"],
  "invalid_tickers": [
    {{"ticker": "ticker_symbol", "actual_market": "US/India/Unknown", "reason": "explanation"}}
  ],
  "all_valid": true/false
}}"""

            user_prompt = f"""Validate these tickers for {expected_market} market:

Tickers: {tickers_str}

Check if ALL tickers belong to {expected_market} market. Return valid and invalid tickers."""

            # Make the LLM call
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=GenerateContentConfig(system_instruction=[system_prompt])
            )

            response_text = response.text.strip()

            # Parse JSON response
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            validation_result = json.loads(response_text)
            all_valid = validation_result.get("all_valid", False)
            valid_tickers = validation_result.get("valid_tickers", [])
            invalid_tickers_data = validation_result.get("invalid_tickers", [])
            invalid_tickers = [item.get("ticker") for item in invalid_tickers_data]

            if all_valid:
                logger.info(f"✓ All {len(tickers)} tickers are valid for {expected_market} market")
                return True, "", valid_tickers, []
            else:
                # Build error message
                error_msg = f"**Invalid Stocks: Market Preference Mismatch**\n\n"
                error_msg += f"You selected **{market_preference} Market**, but some stocks don't match:\n\n"

                for invalid_item in invalid_tickers_data:
                    ticker = invalid_item.get("ticker")
                    actual_market = invalid_item.get("actual_market", "Unknown")
                    reason = invalid_item.get("reason", "Does not match selected market")
                    error_msg += f"• **{ticker}**: {reason} (Appears to be {actual_market} market)\n"

                error_msg += f"\n**Requirement:** All stocks must be from the {expected_market} market.\n"
                if expected_market == "US":
                    error_msg += "Please provide only US stocks (e.g., AAPL, GOOGL, MSFT, JPM, VOO).\n"
                else:
                    error_msg += "Please provide only Indian stocks (e.g., RELIANCE.NS, TCS.BO, INFY.NS, HDFCBANK).\n"

                logger.warning(f"Validation failed: {len(invalid_tickers)} invalid tickers for {expected_market} market")
                return False, error_msg, valid_tickers, invalid_tickers

        except Exception as e:
            logger.error(f"Error validating stocks against market preference: {e}")
            # On error, be lenient and allow through
            return True, "", tickers, []

    def suggest_stocks_by_category(self, category: str):
        """
        Retrieves a list of stocks from a specified category.
        Validates that the category matches the user's market preference.

        Args:
            category: The full category name (e.g., 'USA_TOP_AUTOMOBILE_STOCKS', 'INDIA_TOP_TECHNOLOGY_STOCKS')
        """
        logger.info(f"🔧 TOOL CALLED: suggest_stocks_by_category(category='{category}')")

        # Check market preference
        state = self._load_state()
        market_preference = state.get("market_preference")

        if not market_preference:
            return "Error: Market preference not set. Please specify if you want to invest in US or Indian market first."

        # Validate category matches market preference
        category_upper = category.upper()
        if market_preference == "US":
            if not category_upper.startswith("USA_"):
                error_msg = f"**Market Preference Mismatch**\n\n"
                error_msg += f"You selected **US Market**, but requested category '{category}' is for Indian stocks.\n\n"
                error_msg += "**Available US Categories:**\n"
                error_msg += "• USA_TOP_TECHNOLOGY_STOCKS\n"
                error_msg += "• USA_TOP_FINANCIAL_STOCKS\n"
                error_msg += "• USA_TOP_AUTOMOBILE_STOCKS\n"
                logger.warning(f"Category '{category}' doesn't match US market preference")
                return error_msg
        elif market_preference == "INDIA":
            if not category_upper.startswith("INDIA_"):
                error_msg = f"**Market Preference Mismatch**\n\n"
                error_msg += f"You selected **Indian Market**, but requested category '{category}' is for US stocks.\n\n"
                error_msg += "**Available Indian Categories:**\n"
                error_msg += "• INDIA_TOP_TECHNOLOGY_STOCKS\n"
                error_msg += "• INDIA_TOP_FINANCIAL_STOCKS\n"
                error_msg += "• INDIA_TOP_AUTOMOBILE_STOCKS\n"
                logger.warning(f"Category '{category}' doesn't match INDIA market preference")
                return error_msg

        stock_data_path = os.path.join(os.path.dirname(__file__), "stock_data.json")

        if not os.path.exists(stock_data_path):
            return "Error: stock_data.json not found. Please ensure it's in the correct directory."

        try:
            with open(stock_data_path, "r") as f:
                stock_data = json.load(f)

            if category not in stock_data:
                # Show only categories matching the user's market preference
                all_categories = list(stock_data.keys())
                if market_preference == "US":
                    available_categories = [cat for cat in all_categories if cat.startswith("USA_")]
                    market_name = "US"
                else:
                    available_categories = [cat for cat in all_categories if cat.startswith("INDIA_")]
                    market_name = "Indian"

                return f"Error: Category '{category}' not found. Available {market_name} categories:\n" + "\n".join(available_categories)
            
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
            # Stock Report Analyser Agent removed - now integrated locally as a sub-agent
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
