from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
)
from mcp import StdioServerParameters
from google.adk.tools import FunctionTool
# Schema imports removed - using basic FunctionTool without explicit schemas
import json
import os
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import concurrent.futures
import traceback
import requests
import base64
import re
import time
import random
from logger import setup_logging, get_logger
import asyncio
from functools import wraps
from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions
from database import get_db, save_stock_recommendation
from openai import OpenAI
from config import current_config

# Setup logging and get log file path
log_file_path = setup_logging()
logger = get_logger(__name__)
logger.info(f"Logging initialized. Log file: {log_file_path}")


class StockAnalyzerAgent:
    """Stock analyzer agent that handles portfolio analysis and stock recommendations."""
    
    def __init__(self):
        """Initialize the stock analyzer agent with instance variables and tools."""
        # Instance variables instead of global variables
        self.investment_amount = ""
        self.email_id = ""
        self.portfolio_analysis = ""
        self.user_id = ""
        self.session_id = ""
        self.stock_analysis_data = {}  # Store stock analysis data in memory
        
        # Initialize MCP tool
        # Get MCP directory from config (environment-aware)
        mcp_directory = current_config.MCP_DIRECTORY
        logger.info(f"Using MCP directory: {mcp_directory}")

        # Prepare environment variables for MCP server (no longer needs FINNHUB_API_KEY)
        mcp_env = {**os.environ}
        mcp_env["MCP_TIMEOUT"] = os.getenv("MCP_TIMEOUT", "30")  # Default 30 seconds

        # Use current Python interpreter (dependencies are now installed in stockanalyser_agent venv)
        # This avoids the uv run overhead and virtual environment resolution issues
        import sys
        server_script = os.path.join(mcp_directory, "server.py")
        command = sys.executable  # Use the current Python interpreter
        args = [server_script]

        connection_params = StdioConnectionParams(
            server_params=StdioServerParameters(
                command=command,
                args=args,
                env=mcp_env,
            )
        )
        self.stock_mcp_tool = MCPToolset(
            connection_params=connection_params,
        )
        
        # Create function tools with instance methods
        self.execute_programmatic_flow_tool = FunctionTool(self.execute_programmatic_flow)
        self.extract_stocks_from_analysis_request_tool = FunctionTool(self.extract_stocks_from_analysis_request)
        self.get_expert_portfolio_recommendations_tool = FunctionTool(self.get_expert_portfolio_recommendations)
        self.save_stock_analysis_to_memory_tool = FunctionTool(self.save_stock_analysis_to_memory)
        self.save_portfolio_analysis_to_file_tool = FunctionTool(self.save_portfolio_analysis_to_file)
        self.save_investment_details_to_file_tool = FunctionTool(self.save_investment_details_to_file)
        self.send_analysis_to_webhook_tool = FunctionTool(self.send_analysis_to_webhook)

    def extract_stocks_from_analysis_request(self, analysis_request: str) -> str:
        """
        Uses LLM to extract stock tickers from a comprehensive analysis request.

        Args:
            analysis_request (str): The comprehensive analysis request containing stock lists and investment details

        Returns:
            str: JSON string with extracted stock lists in format {"existing_stocks": [], "new_stocks": []}
        """
        try:
            logger.info(f"extract_stocks_from_analysis_request called with analysis request: {analysis_request}")
            # Validate input parameter
            if not analysis_request or not isinstance(analysis_request, str):
                logger.error(f"Invalid analysis_request parameter: {analysis_request}")
                return "**Error**: analysis_request must be a non-empty string"
            
            # Log the analysis request for debugging
            logger.info(f"Using LLM to extract stocks from analysis request: {len(analysis_request)} characters")
            
            # Create the client with proper configuration
            import os
            
            # Check if we should use Vertex AI or API key
            if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
                client = genai.Client(vertexai=True)
                logger.info("Using Vertex AI for stock extraction")
            else:
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    logger.error("No GOOGLE_API_KEY found for stock extraction")
                    return "**Error**: Google API key not configured for stock extraction"
                client = genai.Client(api_key=api_key)
                logger.info("Using Google AI API for stock extraction")
            
            # System prompt for stock extraction
            system_prompt = """You are a stock ticker extraction specialist. Your sole task is to extract stock ticker symbols from analysis requests.

TASK:
Extract stock tickers from the analysis request and categorize them as existing portfolio stocks or new stocks to analyze.
If stock names (not tickers) are provided, identify and convert them to their corresponding ticker symbols.

RULES:
- Extract ONLY valid stock ticker symbols (e.g., AAPL, GOOGL, TSLA)
- If a company name is provided (e.g., "Apple", "Microsoft"), convert it to the ticker (AAPL, MSFT)
- Categorize stocks as "existing" if they are mentioned as part of current portfolio
- Categorize stocks as "new" if they are mentioned for potential investment or analysis
- Also extract the investment amount, email ID, user ID, and session ID if present

OUTPUT FORMAT (respond with ONLY these lines):
EXISTING: TICKER1, TICKER2, TICKER3 (or NONE if no existing stocks)
NEW: TICKER1, TICKER2, TICKER3 (or NONE if no new stocks)
INVESTMENT_AMOUNT: amount (numeric value only, or 0 if not found)
EMAIL_ID: email@example.com (or not_found if not present)
USER_ID: user_id (or not_found if not present)
SESSION_ID: session_id (or not_found if not present)

EXAMPLES:
Input: "I have Apple and Microsoft in my portfolio. I want to invest $5000 in Tesla and Amazon. Email: john@example.com"
Output:
EXISTING: AAPL, MSFT
NEW: TSLA, AMZN
INVESTMENT_AMOUNT: 5000
EMAIL_ID: john@example.com
USER_ID: not_found
SESSION_ID: not_found

Input: "Analyze NVDA, VOO and suggest new stocks PLTR, GOOGL for $10000. USER ID: user123 SESSION ID: sess456"
Output:
EXISTING: NVDA, VOO
NEW: PLTR, GOOGL
INVESTMENT_AMOUNT: 10000
EMAIL_ID: not_found
USER_ID: user123
SESSION_ID: sess456"""

            # Generate stock extraction using LLM with retry logic
            logger.info("Generating stock extraction using LLM")
            max_retries = 3
            base_delay = 2.0
            response = None

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        import random
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.info(f"Retrying stock extraction after {delay:.2f}s delay (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)

                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=analysis_request,
                        config=GenerateContentConfig(
                            system_instruction=[system_prompt]
                        )
                    )

                    # If we get here, the call was successful
                    logger.info(f"Successfully generated stock extraction {response.text})")
                    break

                except Exception as e:
                    error_message = str(e)
                    is_api_error = any(code in error_message for code in ["500", "503", "INTERNAL", "UNAVAILABLE"])

                    if attempt == max_retries - 1:
                        # Last attempt failed, re-raise the exception
                        logger.error(f"Failed to generate stock extraction after {max_retries} attempts: {e}")
                        raise

                    if is_api_error:
                        logger.warning(f"Google AI API error on attempt {attempt + 1}: {e}")
                    else:
                        logger.warning(f"Non-API error on attempt {attempt + 1}: {e}")
                        # For non-API errors, fail immediately
                        raise

            logger.info("Received LLM response for stock extraction")
            
            existing_stocks = []
            new_stocks = []

            if response and response.text:
                # Parse the LLM response
                response_text = response.text.strip()
                logger.info(f"LLM stock extraction response: {response_text}")

                # Parse the response lines
                lines = response_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith("EXISTING:"):
                        stocks_text = line.replace("EXISTING:", "").strip()
                        if stocks_text and stocks_text.upper() != "NONE":
                            existing_stocks = [s.strip().upper() for s in stocks_text.split(',') if s.strip()]
                    elif line.startswith("NEW:"):
                        stocks_text = line.replace("NEW:", "").strip()
                        if stocks_text and stocks_text.upper() != "NONE":
                            new_stocks = [s.strip().upper() for s in stocks_text.split(',') if s.strip()]
                    elif line.startswith("INVESTMENT_AMOUNT:"):
                        self.investment_amount = line.replace("INVESTMENT_AMOUNT:", "").strip()
                    elif line.startswith("EMAIL_ID:"):
                        self.email_id = line.replace("EMAIL_ID:", "").strip()
                    elif line.startswith("USER_ID:"):
                        self.user_id = line.replace("USER_ID:", "").strip()
                    elif line.startswith("SESSION_ID:"):
                        self.session_id = line.replace("SESSION_ID:", "").strip()
                
            else:
                logger.error("No response from LLM for stock extraction")
                return "**Error**: Could not extract stocks using LLM. Please try again."
            
            # Create JSON result
            result = {
                "existing_stocks": existing_stocks,
                "new_stocks": new_stocks
            }

            logger.info(f"LLM-powered stock extraction complete: {len(existing_stocks)} existing, {len(new_stocks)} new stocks")
            logger.info(f"Investment amount: {self.investment_amount}")
            logger.info(f"Email id: {self.email_id}")
            logger.info(f"User ID: {self.user_id}")
            logger.info(f"Session ID: {self.session_id}")

            return json.dumps(result)
            
        except Exception as e:
            logger.error(f"Error in LLM stock extraction: {str(e)}")
            return f"Error extracting stocks from analysis request: {e}"

    def get_expert_portfolio_recommendations(self) -> str:
        """
        Analyzes portfolio data from memory and provides comprehensive investment recommendations.
        Reads both portfolio analysis and individual stock data to make buy/sell/hold decisions.
        Uses Perplexity's sonar-pro model for analysis.

        Returns:
            JSON string with comprehensive portfolio analysis with specific investment recommendations and amounts
        """
        try:
            logger.info(f"get_expert_portfolio_recommendations called with investment amount: ${self.investment_amount}")

            if not self.stock_analysis_data:
                logger.error("No stock analysis data available in memory")
                return json.dumps({"error": "No stock analysis data available. Please ensure stocks have been analyzed first."})

            # Build text content from in-memory data
            text_content_parts = []
            for ticker, data in self.stock_analysis_data.items():
                text_content_parts.append(f"\n{'='*50}\nTicker: {ticker}\nTimestamp: {data['timestamp']}\n{'='*50}\n{data['data']}\n")

            text_content = "\n".join(text_content_parts)

            logger.info(f"Successfully loaded portfolio data from memory")
            logger.info(f"Found text content with {len(text_content)} characters for {len(self.stock_analysis_data)} stocks")

            # Initialize Perplexity client using OpenAI-compatible format
            perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
            if not perplexity_api_key:
                logger.error("PERPLEXITY_API_KEY not found in environment variables")
                return json.dumps({"error": "PERPLEXITY_API_KEY not configured. Please set the environment variable."})

            client = OpenAI(
                api_key=perplexity_api_key,
                base_url="https://api.perplexity.ai"
            )
            logger.info("Using Perplexity API with sonar-pro model for portfolio analysis")

            # Expert system prompt for portfolio recommendations
            system_prompt = f"""You are a senior portfolio manager with 20+ years of experience in equity analysis and portfolio construction. Your role is to provide data-driven stock allocation recommendations with specific buy/sell/hold decisions and INTELLIGENT WEIGHTED ALLOCATION.

ANALYTICAL FRAMEWORK:
1. Fundamental Analysis: Evaluate valuation metrics (P/E, P/B, PEG ratio), financial health (debt ratios, cash flow), growth metrics (revenue/earnings growth), and profitability margins
2. Technical Analysis: Assess price momentum, trend strength (50-day vs 200-day MA), and proximity to 52-week highs/lows
3. Analyst Consensus: Consider analyst ratings and price target upside/downside
4. Portfolio Context: Evaluate sector concentration, risk diversification, and position sizing
5. Risk Assessment: Analyze beta, volatility, and company-specific risks from recent news

DECISION CRITERIA:
BUY: Must meet ALL of the following:
- Current price offers ≥10% upside to analyst mean target OR strong fundamental growth (>20% revenue/earnings growth) with reasonable valuation
- Positive technical momentum (price above 50-day MA or strong recent trend)
- Analyst recommendation of "buy" or "strong buy"
- Fits portfolio diversification needs (not overweighting existing sector concentration)

HOLD: Meets ANY of the following:
- Current price within ±10% of fair value estimate
- Mixed signals (strong fundamentals but negative momentum, or vice versa)
- Already appropriately weighted in portfolio
- Neutral analyst consensus or significant uncertainty

SELL: Meets ANY of the following:
- Current price ≥15% above analyst mean target with deteriorating fundamentals
- Declining revenue/earnings with high valuation (P/E >30 AND negative growth)
- Significant negative news or fundamental deterioration
- Overweight position that increases portfolio concentration risk above 25% in any stock

PORTFOLIO CONSTRAINTS:
- Total investment budget: ${self.investment_amount}
- Maximum single stock allocation: 25% of total budget
- Minimum single stock allocation: 5% of total budget (to ensure meaningful positions)
- Ensure sector diversification: No more than 40% in any single sector

INTELLIGENT ALLOCATION METHODOLOGY (CRITICAL - MUST FOLLOW):
For each BUY recommendation, assign a CONVICTION LEVEL and allocate accordingly:

HIGH CONVICTION (20-25% of budget): Stock meets ALL criteria:
- Analyst consensus "Strong Buy" OR price target upside >25%
- Strong fundamentals (P/E <20, revenue growth >20%, healthy margins >15%)
- Positive technical momentum (price above both 50-day and 200-day MA)
- Low risk (beta <1.2, strong balance sheet)

MEDIUM CONVICTION (10-15% of budget): Stock meets MOST criteria:
- Analyst consensus "Buy" OR price target upside 10-25%
- Solid fundamentals (reasonable P/E, positive growth)
- Neutral to positive technical signals
- Moderate risk (beta 1.0-1.5)

LOW CONVICTION (5-10% of budget): Stock meets MINIMUM criteria:
- Analyst consensus "Hold/Buy" OR price target upside 10-15%
- Acceptable fundamentals
- Mixed technical signals
- Higher risk (beta >1.5) OR smaller cap OR sector concerns

ALLOCATION RULES:
1. NEVER allocate $0 to a BUY recommendation - minimum is 5% of total budget
2. Total BUY allocations MUST sum exactly to ${self.investment_amount}
3. If fewer BUY opportunities, increase allocation to higher conviction stocks (up to 25% max)
4. Distribute remaining budget across BUY recommendations proportionally by conviction
5. For HOLD and SELL: investment_amount is always "$0"

OUTPUT FORMAT (** STRICTLY FOLLOW THE BELOW JSON FORMAT **):
You must return ONLY a valid JSON object with the following structure:
{{
    "allocation_breakdown": [
        {{
            "ticker": "string",
            "percentage": "string (e.g., '25%')",
            "investment_amount": "string (e.g., '$2500')"
        }}
    ],
    "individual_stock_recommendations": [
        {{
            "ticker": "string",
            "recommendation": "string (BUY/HOLD/SELL)",
            "conviction_level": "string (HIGH/MEDIUM/LOW for BUY, N/A for HOLD/SELL)",
            "investment_amount": "string (NEVER $0 for BUY, always $0 for HOLD/SELL)",
            "key_metrics": "string (Current P/E [X], Target Upside [X%], Analyst Rating [X], Revenue Growth [X%])",
            "reasoning": "string (2-3 sentences explaining the decision and conviction level)"
        }}
    ],
    "risk_warnings": [
        "string (risk warning point 1)",
        "string (risk warning point 2)"
    ]
}}

CRITICAL RULES:
- Return ONLY valid JSON - no markdown, no extra text, no code blocks, no ```json wrapper
- Base ALL decisions on the quantitative data provided, not general market knowledge
- NEVER return $0 for BUY recommendations - minimum 5% of budget
- Always assign conviction_level to BUY recommendations
- Ensure total BUY allocations sum EXACTLY to ${self.investment_amount}
- Use weighted allocation based on conviction, NOT equal distribution
- Reference specific metrics that justify the conviction level and allocation
- IMPORTANT: If the request includes specific DIVERSIFICATION REQUIREMENTS or INVESTMENT PATTERN preferences, prioritize following those instructions
- If user wants to DIVERSIFY: Focus heavily on sector diversification and risk minimization, potentially recommending lower allocation percentages to existing concentrated sectors
- If user wants to MAINTAIN EXISTING PATTERN: Analyze and replicate the sector distribution from their existing portfolio"""

            # Prepare comprehensive data for analysis
            portfolio_summary = f"""
INVESTMENT PORTFOLIO ANALYSIS REQUEST:
Total Investment Budget: {self.investment_amount}

STOCK ANALYSIS DATA:
{text_content}
"""

            # Create user prompt
            user_prompt = f"""Please analyze this complete investment portfolio and provide specific recommendations:

            {portfolio_summary}

            Provide actionable investment decisions with exact dollar amounts for each BUY recommendation, ensuring the total does not exceed ${self.investment_amount}."""

            # Generate portfolio recommendations using LLM
            logger.info(f"Generating comprehensive portfolio recommendations")

            max_retries = 5  # Increased retries to account for JSON validation retries
            base_delay = 1.0

            for attempt in range(max_retries):
                try:
                    # Add small random delay to prevent hitting rate limits
                    if attempt > 0:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.info(f"Retrying portfolio analysis after {delay:.2f}s delay (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)

                    # Call Perplexity API with sonar-pro model
                    completion = client.chat.completions.create(
                        messages=[
                            {
                                "role": "system",
                                "content": system_prompt
                            },
                            {
                                "role": "user",
                                "content": user_prompt
                            }
                        ],
                        model="sonar-pro"
                    )

                    response_text = completion.choices[0].message.content if completion and completion.choices else None

                    if response_text:
                        # Log successful generation
                        logger.info(f"Successfully generated portfolio recommendations: {len(response_text)} characters (attempt {attempt + 1})")

                        # Clean the response text (remove markdown code blocks if present)
                        cleaned_text = response_text.strip()
                        if cleaned_text.startswith("```json"):
                            cleaned_text = cleaned_text[7:]  # Remove ```json
                        if cleaned_text.startswith("```"):
                            cleaned_text = cleaned_text[3:]  # Remove ```
                        if cleaned_text.endswith("```"):
                            cleaned_text = cleaned_text[:-3]  # Remove trailing ```
                        cleaned_text = cleaned_text.strip()

                        # Validate JSON
                        try:
                            parsed_json = json.loads(cleaned_text)

                            # Validate required fields
                            required_fields = ["allocation_breakdown", "individual_stock_recommendations", "risk_warnings"]
                            missing_fields = [field for field in required_fields if field not in parsed_json]

                            if missing_fields:
                                logger.warning(f"JSON missing required fields: {missing_fields} (attempt {attempt + 1})")
                                if attempt == max_retries - 1:
                                    return json.dumps({"error": f"Invalid JSON response: missing fields {missing_fields}"})
                                continue  # Retry

                            # Return the validated JSON string
                            logger.info(f"Successfully validated JSON response")
                            return json.dumps(parsed_json)

                        except json.JSONDecodeError as json_err:
                            logger.warning(f"Invalid JSON response from LLM (attempt {attempt + 1}): {str(json_err)}")
                            logger.warning(f"Response text (first 500 chars): {cleaned_text[:500]}")

                            if attempt == max_retries - 1:
                                # Last attempt - return error with partial response
                                return json.dumps({
                                    "error": f"Failed to parse JSON after {max_retries} attempts",
                                    "raw_response": cleaned_text[:1000],
                                    "parse_error": str(json_err)
                                })
                            continue  # Retry

                    else:
                        logger.warning(f"Empty response from LLM for portfolio analysis (attempt {attempt + 1})")
                        if attempt == max_retries - 1:
                            return json.dumps({"error": f"Empty response from LLM after {max_retries} attempts"})

                except json.JSONDecodeError as json_err:
                    logger.error(f"JSON parsing error (attempt {attempt + 1}): {str(json_err)}")
                    if attempt == max_retries - 1:
                        return json.dumps({"error": f"JSON parsing failed: {str(json_err)}"})
                    continue  # Retry

                except Exception as llm_error:
                    logger.error(f"LLM API error for portfolio analysis (attempt {attempt + 1}): {str(llm_error)}")
                    if attempt == max_retries - 1:
                        return json.dumps({"error": f"LLM API error: {str(llm_error)}"})

                    # Check if it's a quota/rate limit error
                    error_str = str(llm_error).lower()
                    if "quota" in error_str or "rate" in error_str or "limit" in error_str:
                        logger.warning(f"Rate limit detected for portfolio analysis, increasing delay")
                        base_delay = min(base_delay * 2, 10.0)  # Cap at 10 seconds

        except Exception as e:
            error_msg = f"Error generating portfolio recommendations: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})

    def save_stock_analysis_to_memory(self, ticker: str, analysis_data: str) -> str:
        """
        Save stock analysis data to memory.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            analysis_data: The analysis data to store

        Returns:
            Success/error message
        """
        try:
            logger.info(f"Saving stock analysis for {ticker} to memory")

            # Store in memory dictionary
            timestamp = datetime.now().isoformat()
            self.stock_analysis_data[ticker] = {
                "ticker": ticker,
                "timestamp": timestamp,
                "data": analysis_data
            }

            logger.info(f"Successfully saved analysis for {ticker} to memory")
            return f"Successfully saved analysis for {ticker} to memory"

        except Exception as e:
            error_msg = f"Error saving analysis for {ticker}: {e}"
            logger.error(error_msg)
            return error_msg

    def save_portfolio_analysis_to_file(self, portfolio_analysis: str) -> str:
        """
        Save portfolio analysis data to text file and extract investment_amount and email_id.

        Args:
            portfolio_analysis (str): The portfolio analysis request containing investment amount and email

        Returns:
            JSON string with extracted investment_amount and email_id
        """
        logger.info(f"Portfolio analysis before compression: {portfolio_analysis}")
        # portfolio_analysis = self._compress_response(portfolio_analysis)
        logger.info(f"Portfolio analysis after compression: {portfolio_analysis}")
        try:
            logger.info("Saving portfolio analysis to file and extracting investment details")
            file_path = "stock_analysis_results.txt"

            if not portfolio_analysis.strip():
                logger.warning("Portfolio analysis is empty, skipping save")
                return json.dumps({"error": "Portfolio analysis is empty, nothing to save"})

            # Extract investment amount and email using LLM (similar to stock extraction)
            api_key = os.getenv("GOOGLE_API_KEY")
            if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
                client = genai.Client(vertexai=True)
                logger.info("Using Vertex AI for investment details extraction")
            elif api_key:
                client = genai.Client(api_key=api_key)
                logger.info("Using Google GenAI API for investment details extraction")
            else:
                client = genai.Client()
                logger.info("Using default GenAI client for investment details extraction")

            # System prompt for extracting investment details
            system_prompt = """Extract the investment amount and email ID from the analysis request.

            Rules:
            - Look for investment amount patterns like "$1000", "1000$", "invest 1000", etc.
            - Look for email patterns like "email@domain.com", "send to user@email.com", etc.
            - Extract only the numeric value for investment amount (remove $ symbols)
            - Extract only the email address

            Respond with ONLY these two lines in this exact format:
            INVESTMENT_AMOUNT: 1000
            EMAIL_ID: user@example.com

            If not found, write: INVESTMENT_AMOUNT: 0 or EMAIL_ID: not_found"""

            # Retry logic for Google AI API calls
            max_retries = 3
            base_delay = 2.0
            response = None

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        import random
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.info(f"Retrying investment details extraction after {delay:.2f}s delay (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)

                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=portfolio_analysis,
                        config=GenerateContentConfig(
                            system_instruction=[system_prompt]
                        )
                    )

                    # If we get here, the call was successful
                    logger.info(f"Successfully extracted investment details (attempt {attempt + 1})")
                    break

                except Exception as e:
                    error_message = str(e)
                    is_api_error = any(code in error_message for code in ["500", "503", "INTERNAL", "UNAVAILABLE"])

                    if attempt == max_retries - 1:
                        # Last attempt failed, re-raise the exception
                        logger.error(f"Failed to extract investment details after {max_retries} attempts: {e}")
                        raise

                    if is_api_error:
                        logger.warning(f"Google AI API error on attempt {attempt + 1}: {e}")
                    else:
                        logger.warning(f"Non-API error on attempt {attempt + 1}: {e}")
                        # For non-API errors, fail immediately
                        raise

            investment_amount = "0"
            email_id = "not_found"

            if response and response.text:
                response_text = response.text.strip()
                lines = response_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith("INVESTMENT_AMOUNT:"):
                        investment_amount = line.replace("INVESTMENT_AMOUNT:", "").strip()
                    elif line.startswith("EMAIL_ID:"):
                        email_id = line.replace("EMAIL_ID:", "").strip()

            # Store in instance variables for later use
            self.investment_amount = investment_amount
            self.email_id = email_id

            # Prepare the portfolio analysis entry
            timestamp = datetime.now().isoformat()
            entry = f"\n{'='*50}\nPortfolio Analysis\nTimestamp: {timestamp}\n{'='*50}\n{portfolio_analysis}\n"

            # Append to file
            with open(file_path, 'a') as f:
                f.write(entry)

            logger.info(f"Successfully saved portfolio analysis to {file_path}")
            logger.info(f"Extracted investment amount: {investment_amount}, email: {email_id}")

            return json.dumps({
                "investment_amount": investment_amount,
                "email_id": email_id,
                "status": "success"
            })

        except Exception as e:
            error_msg = f"Error saving portfolio analysis: {e}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})

    def save_investment_details_to_file(self) -> str:
        """
        Save investment amount and email ID from instance variables to text file.

        Returns:
            Success/error message
        """
        try:
            logger.info("Saving investment details to file")
            file_path = "stock_analysis_results.txt"

            # Prepare the investment details entry
            timestamp = datetime.now().isoformat()
            entry = f"\n{'='*50}\nInvestment Details\nTimestamp: {timestamp}\n{'='*50}\nInvestment Amount: {self.investment_amount}\nEmail ID: {self.email_id}\n"

            # Append to file
            with open(file_path, 'a') as f:
                f.write(entry)

            logger.info(f"Successfully saved investment details to {file_path}")
            logger.info(f"Investment amount: {self.investment_amount}, Email ID: {self.email_id}")
            return f"Successfully saved investment details to {file_path} - Amount: {self.investment_amount}, Email: {self.email_id}"

        except Exception as e:
            error_msg = f"Error saving investment details: {e}"
            logger.error(error_msg)
            return error_msg

    def convert_portfolio_analysis_to_html(self, text: str) -> str:
        """
        Converts portfolio analysis JSON to HTML email-friendly format.
        Parses JSON format and applies proper HTML styling with color coding.

        Args:
            text: The portfolio analysis in JSON format

        Returns:
            HTML formatted string suitable for email body
        """
        try:
            # Parse JSON input
            data = json.loads(text)

            html_parts = []

            # Start HTML with basic styling
            html_parts.append('''<html>
<head>
<style>
body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }
h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; font-size: 24px; margin-top: 25px; }
h2 { color: #34495e; margin-top: 30px; font-size: 20px; }
h3 { color: #7f8c8d; margin-top: 20px; font-size: 16px; font-weight: bold; }
.allocation { background-color: #ecf0f1; padding: 15px; border-radius: 5px; margin: 15px 0; }
.stock-card { background-color: #ffffff; border-left: 6px solid #3498db; padding: 15px 20px; margin: 15px 0; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.stock-card p { margin: 8px 0; line-height: 1.5; }
.buy { border-left-color: #27ae60; background-color: #f0fcf4; }
.hold { border-left-color: #f39c12; background-color: #fef9f0; }
.sell { border-left-color: #e74c3c; background-color: #fef5f5; }
.ticker { font-weight: bold; font-size: 18px; color: #2c3e50; }
.recommendation { font-weight: bold; padding: 5px 12px; border-radius: 4px; display: inline-block; font-size: 14px; letter-spacing: 0.5px; }
.rec-buy { background-color: #27ae60; color: white; }
.rec-hold { background-color: #f39c12; color: white; }
.rec-sell { background-color: #e74c3c; color: white; }
ul { margin: 10px 0; }
li { margin: 8px 0; }
.warning { background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 15px 0; }
strong { color: #2c3e50; }
</style>
</head>
<body>''')

            # Add Allocation Breakdown section
            if 'allocation_breakdown' in data and data['allocation_breakdown']:
                html_parts.append('<h1>ALLOCATION BREAKDOWN</h1>')
                html_parts.append('<ul class="allocation">')

                for allocation in data['allocation_breakdown']:
                    ticker = allocation.get('ticker', 'N/A')
                    percentage = allocation.get('percentage', 'N/A')
                    investment_amount = allocation.get('investment_amount', 'N/A')
                    html_parts.append(f'<li><strong>{ticker}:</strong> {percentage} - {investment_amount}</li>')

                html_parts.append('</ul>')

            # Add Individual Stock Recommendations section
            if 'individual_stock_recommendations' in data and data['individual_stock_recommendations']:
                html_parts.append('<h1>INDIVIDUAL STOCK RECOMMENDATIONS</h1>')

                for stock in data['individual_stock_recommendations']:
                    ticker = stock.get('ticker', 'N/A')
                    recommendation = stock.get('recommendation', 'HOLD').upper()
                    investment_amount = stock.get('investment_amount', '$0')
                    key_metrics = stock.get('key_metrics', 'N/A')
                    reasoning = stock.get('reasoning', 'No reasoning provided')

                    # Determine card styling based on recommendation
                    rec_type = 'hold'
                    rec_class = 'rec-hold'
                    if recommendation == 'BUY':
                        rec_type = 'buy'
                        rec_class = 'rec-buy'
                    elif recommendation == 'SELL':
                        rec_type = 'sell'
                        rec_class = 'rec-sell'

                    html_parts.append(f'<div class="stock-card {rec_type}">')
                    html_parts.append(f'<span class="ticker">{ticker}</span> - <span class="recommendation {rec_class}">{recommendation}</span>')

                    if recommendation == 'BUY':
                        html_parts.append(f'<p><strong>Investment Amount: {investment_amount}</strong></p>')

                    html_parts.append(f'<p><strong>Key Metrics:</strong> {key_metrics}</p>')
                    html_parts.append(f'<p><strong>Reasoning:</strong> {reasoning}</p>')
                    html_parts.append('</div>')

            # Add Risk Warnings section
            if 'risk_warnings' in data and data['risk_warnings']:
                html_parts.append('<h1>RISK WARNINGS</h1>')
                html_parts.append('<ul>')

                for warning in data['risk_warnings']:
                    html_parts.append(f'<li>{warning}</li>')

                html_parts.append('</ul>')

            # Close HTML
            html_parts.append('</body></html>')

            return ''.join(html_parts)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON in convert_portfolio_analysis_to_html: {e}")
            # Fallback to simple HTML with error message
            return f'''<html>
<head>
<style>
body {{ font-family: Arial, sans-serif; padding: 20px; }}
.error {{ color: #e74c3c; background-color: #fef5f5; padding: 15px; border-left: 4px solid #e74c3c; }}
</style>
</head>
<body>
<div class="error">
<h2>Error Processing Portfolio Analysis</h2>
<p>Failed to parse the portfolio analysis data. Please check the format.</p>
<p>Error: {str(e)}</p>
</div>
<pre>{text}</pre>
</body>
</html>'''
        except Exception as e:
            logger.error(f"Unexpected error in convert_portfolio_analysis_to_html: {e}")
            return f'''<html>
<head>
<style>
body {{ font-family: Arial, sans-serif; padding: 20px; }}
.error {{ color: #e74c3c; background-color: #fef5f5; padding: 15px; border-left: 4px solid #e74c3c; }}
</style>
</head>
<body>
<div class="error">
<h2>Unexpected Error</h2>
<p>An unexpected error occurred while processing the analysis.</p>
<p>Error: {str(e)}</p>
</div>
</body>
</html>'''

    def send_analysis_to_webhook(self, analysis_response: str, email_to: str, webhook_url: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None) -> str:
        """
        Securely sends analysis response data to the Activepieces webhook endpoint.
        
        Args:
            analysis_response: The analysis data to send
            email_to: Email address to send the analysis to
            webhook_url: Webhook URL (defaults to Activepieces endpoint)
            username: Basic auth username (defaults to environment variable)
            password: Basic auth password (defaults to environment variable)
        
        Returns:
            Success/error message with details
        """
        try:
            logger.info("Preparing to send analysis response to webhook endpoint")
            # Use environment variables for sensitive data if not provided
            webhook_url = webhook_url or "https://cloud.activepieces.com/api/v1/webhooks/a3jeiaYrX1ZqVdSAye25A"
            username = username or os.getenv("ACTIVEPIECES_USERNAME")
            password = password or os.getenv("ACTIVEPIECES_PASSWORD")
            
            # Validate required parameters
            if not username or not password:
                logger.error("Missing Activepieces authentication credentials")
                return "Error: Missing authentication credentials. Please set ACTIVEPIECES_USERNAME and ACTIVEPIECES_PASSWORD environment variables."
            
            if not analysis_response or not analysis_response.strip():
                logger.error("Empty analysis response provided")
                return "Error: Analysis response cannot be empty."
            
            # Get current date for email body
            current_date = datetime.now().strftime("%B %d, %Y")
            
            # Add date to the beginning of HTML content
            response_with_date = analysis_response.replace(
                'ALLOCATION BREAKDOWN',
                f'ALLOCATION BREAKDOWN - {current_date}'
            )
            
            # Prepare the request data - include both plain text and HTML versions
            payload = {
                "analysis_response": response_with_date,  # Add HTML version for email with date
                "email_to": email_to
            }
            
            # Create basic auth header - exactly like your working curl
            credentials = f"{username}:{password}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/json"
                # Removed User-Agent to match your curl exactly
            }
            
            logger.info(f"Sending analysis data to webhook: {webhook_url}")
            logger.info(f"Payload: {payload}")
            html_content = self.convert_portfolio_analysis_to_html(response_with_date)
            html_payload = {
                "analysis_response": html_content,
                "email_to": email_to
            }
            logger.info(f"html_payload: {html_payload}")
            logger.info(f"Headers: {json.dumps({k: v for k, v in headers.items() if k != 'Authorization'}, indent=2)}")
            logger.info(f"Auth: Basic {encoded_credentials[:10]}...")
            
            # Make the POST request - exactly like your curl
            response = requests.post(
                webhook_url,
                json=html_payload,
                headers=headers,
                timeout=30
            )
            
            # Log the full response for debugging
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            logger.info(f"Response text: {response.text[:500]}")
            
            # Check response status
            if response.status_code == 200:
                logger.info("Successfully sent analysis data to webhook")
                return f"Success: Analysis data sent to webhook. Response: {response.status_code} - {response.text[:100]}..."
            elif response.status_code == 401:
                logger.error("Authentication failed - check username/password")
                return f"Error: Authentication failed. Please verify your Activepieces credentials. Response: {response.text[:200]}"
            elif response.status_code == 404:
                logger.error("Webhook endpoint not found")
                return f"Error: Webhook endpoint not found. Please verify the URL. Response: {response.text[:200]}"
            elif response.status_code >= 500:
                logger.error(f"Server error from webhook: {response.status_code}")
                return f"Error: Server error from webhook ({response.status_code}). Response: {response.text[:200]}"
            else:
                logger.warning(f"Unexpected response from webhook: {response.status_code}")
                return f"Warning: Unexpected response from webhook ({response.status_code}): {response.text[:200]}"
                
        except requests.exceptions.Timeout:
            logger.error("Request timeout - webhook endpoint took too long to respond")
            return "Error: Request timeout. The webhook endpoint took too long to respond."
        except requests.exceptions.SSLError:
            logger.error("SSL certificate verification failed")
            return "Error: SSL certificate verification failed. Please check the webhook endpoint."
        except requests.exceptions.ConnectionError:
            logger.error("Connection error - unable to reach webhook endpoint")
            return "Error: Connection error. Unable to reach the webhook endpoint."
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            return f"Error: Request failed - {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error sending to webhook: {str(e)}")
            return f"Error: Unexpected error occurred - {str(e)}"

    async def execute_programmatic_flow(self, analysis_request: str) -> str:
        """
        Execute the programmatic stock analysis flow.

        Args:
            analysis_request: The complete analysis request from host agent

        Returns:
            Final response from the analysis flow
        """
        try:
            logger.info("Starting programmatic stock analysis flow")
            logger.info(f"Analysis request received from user_id: {self.user_id if hasattr(self, 'user_id') else 'unknown'}, session_id: {self.session_id if hasattr(self, 'session_id') else 'unknown'}")

            # Step 1: Save portfolio analysis and extract investment details
            logger.info("Step 1: Saving portfolio analysis and extracting investment details")
            portfolio_result = self.save_portfolio_analysis_to_file(analysis_request)
            portfolio_data = json.loads(portfolio_result)

            if "error" in portfolio_data:
                return f"Error in step 1: {portfolio_data['error']}"

            logger.info(f"Extracted investment amount: {portfolio_data['investment_amount']}, email: {portfolio_data['email_id']}")

            # Step 2: Extract stocks from analysis request
            logger.info("Step 2: Extracting stocks from analysis request")
            stocks_result = self.extract_stocks_from_analysis_request(analysis_request)
            stocks_data = json.loads(stocks_result)
            logger.info(f"stocks_data: {stocks_data}")

            existing_stocks = stocks_data.get("existing_stocks", [])
            new_stocks = stocks_data.get("new_stocks", [])
            all_stocks = existing_stocks + new_stocks

            logger.info(f"Extracted {len(existing_stocks)} existing stocks and {len(new_stocks)} new stocks")
            logger.info(f"Context for analysis - User ID: {self.user_id}, Session ID: {self.session_id}, Email: {self.email_id}, Investment Amount: {self.investment_amount}")

            # Step 3: Save investment details to file
            logger.info("Step 3: Saving investment details to file")
            investment_save_result = self.save_investment_details_to_file()
            logger.info(f"Investment details saved: {investment_save_result}")

            # Step 4: Analyze each stock using MCP tool
            logger.info(f"Step 4: Analyzing {len(all_stocks)} stocks")
            for stock in all_stocks:
                try:
                    logger.info(f"Analyzing stock: {stock}")

                    # Call MCP tool through session manager
                    session = await self.stock_mcp_tool._mcp_session_manager.create_session()
                    stock_data = await session.call_tool("get_stock_info", arguments={"symbol": stock})

                    # Save stock analysis result to memory
                    save_result = self.save_stock_analysis_to_memory(stock, str(stock_data))
                    logger.info(f"Saved analysis for {stock}: {save_result}")

                except Exception as stock_error:
                    logger.error(f"Error analyzing stock {stock}: {stock_error}")
                    # Continue with other stocks even if one fails
                    error_message = f"Error analyzing {stock}: {str(stock_error)}"
                    self.save_stock_analysis_to_memory(stock, error_message)

            # Step 5: Get expert portfolio recommendations
            logger.info("Step 5: Generating expert portfolio recommendations")
            recommendations = self.get_expert_portfolio_recommendations()

            # Step 6: Save recommendations to database
            logger.info("Step 6: Saving recommendations to database")
            try:
                # Parse the recommendations JSON
                recommendations_dict = json.loads(recommendations)

                # Get database session and save
                db = next(get_db())
                try:
                    saved_recommendation = save_stock_recommendation(
                        db=db,
                        session_id=self.session_id,
                        user_id=self.user_id,
                        recommendation=recommendations_dict
                    )
                    if saved_recommendation:
                        logger.info(f"Successfully saved recommendations to database for session {self.session_id}")
                    else:
                        logger.error("Failed to save recommendations to database")
                finally:
                    db.close()
            except Exception as db_error:
                logger.error(f"Error saving recommendations to database: {db_error}")
                # Continue with webhook even if database save fails

            # Step 7: Send analysis to webhook
            logger.info("Step 7: Sending analysis to webhook")
            webhook_result = self.send_analysis_to_webhook(
                analysis_response=recommendations,
                email_to=self.email_id
            )

            logger.info(f"Webhook result: {webhook_result}")

            # Return final response
            final_response = f"""Stock analysis completed successfully!

Analysis Summary:
- Portfolio analysis saved and investment details extracted
- Analyzed {len(all_stocks)} stocks ({len(existing_stocks)} existing, {len(new_stocks)} new)
- Generated expert recommendations
- Sent analysis to email: {self.email_id}

Webhook Status: {webhook_result}

The detailed analysis has been emailed to you."""

            logger.info("Programmatic flow completed successfully")
            return final_response

        except Exception as e:
            logger.error(f"Error in programmatic flow: {str(e)}")
            return f"Error in programmatic stock analysis flow: {str(e)}"

    def create_agent(self) -> Agent:
        """Constructs the ADK agent for stock analysis and allocation management."""
        return Agent(
            model="gemini-2.5-flash",
            name="stock_analyser_agent",
            instruction="""**Role:** You are a professional stock analyst using a programmatic workflow.

**WORKFLOW:**
When you receive any analysis request, you simply need to call the `execute_programmatic_flow` function with the entire analysis request as a parameter. This function will handle all the steps programmatically:

Just call: execute_programmatic_flow(analysis_request)

The function will return a complete summary of the analysis that was performed.""",
            tools=[
                self.execute_programmatic_flow_tool,
                self.stock_mcp_tool,
                self.extract_stocks_from_analysis_request_tool,
                self.save_stock_analysis_to_memory_tool,
                self.save_portfolio_analysis_to_file_tool,
                self.save_investment_details_to_file_tool,
                self.get_expert_portfolio_recommendations_tool,
                self.send_analysis_to_webhook_tool,
            ],
        )


# Create a global instance of the StockAnalyzerAgent for compatibility
_stock_analyzer_agent = None

def create_agent() -> Agent:
    """Global function to create agent for compatibility with existing host agent calls."""
    global _stock_analyzer_agent
    if _stock_analyzer_agent is None:
        _stock_analyzer_agent = StockAnalyzerAgent()
    return _stock_analyzer_agent.create_agent()