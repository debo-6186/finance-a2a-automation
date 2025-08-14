from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
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
from logger import setup_logging, get_logger, get_log_file_path
from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

# Setup logging and get log file path
log_file_path = setup_logging()
logger = get_logger(__name__)
logger.info(f"Logging initialized. Log file: {log_file_path}")

stock_analysis_tool = MCPToolset(
    connection_params=StdioServerParameters(
        command="uv",
        args=[
            "--directory", 
            "/Users/debojyotichakraborty/codebase/finhub-mcp",
            "run", 
            "server.py"
        ]
    )
)
 

def aggregate_parallel_results(successful_analyses: str, failed_analyses: str, investment_amount: str = "", email_to: str = "") -> str:
    """
    Uses LLM to aggregate and summarize results from parallel stock analyses with comprehensive recommendations.
    
    Args:
        successful_analyses: String containing all successful stock analyses
        failed_analyses: String containing all failed stock analysis messages
        investment_amount: Total investment amount (optional)
    
    Returns:
        LLM-generated comprehensive aggregated analysis and recommendations
    """
    try:
        logger.info("Starting LLM-based aggregation of parallel stock analysis results")
        
        # Parse the input strings to understand the data
        if not successful_analyses.strip() and not failed_analyses.strip():
            return "Error: No analysis results provided for aggregation."
        
        # Count successful and failed analyses by parsing the input strings
        successful_count = successful_analyses.count("**EXPERT ANALYSIS FOR") if successful_analyses else 0
        failed_count = failed_analyses.count("could not be analysed") if failed_analyses else 0
        total_requested = successful_count + failed_count
        
        logger.info(f"Aggregating results: {successful_count} successful, {failed_count} failed")
        
        # Initialize the Google GenAI client
        api_key = os.getenv("GOOGLE_API_KEY")
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            client = genai.Client(vertexai=True)
            logger.info("Using Vertex AI for results aggregation")
        elif api_key:
            client = genai.Client(api_key=api_key)
            logger.info("Using Google GenAI API for results aggregation")
        else:
            client = genai.Client()
            logger.info("Using default GenAI client for results aggregation")
        
        # System prompt for aggregation INCLUDING INDIVIDUAL STOCK ALLOCATION FIRST
        system_prompt = """You are a senior financial analyst and portfolio manager responsible for creating comprehensive investment reports. 

Your task is to analyze multiple stock analysis results and create a professional, actionable investment report that STARTS with INDIVIDUAL STOCK ALLOCATION.

CRITICAL REQUIREMENTS:
1. BEGIN the report with a section titled: "INDIVIDUAL STOCK ALLOCATION"
   - For each BUY-recommended stock, provide:
     • Stock Ticker: SYMBOL
     • Amount to invest: $X,XXX.XX (use the provided investment amount; if not provided, recommend percentage allocations and show 0$ placeholder)
     • Allocation Percentage: XX.X% of total
   - Base allocations on the expert analyses quality, conviction, diversification, and risk balance
   - The allocation must be internally consistent and sum to 100% (when investment amount is given)
2. Synthesize individual stock analyses into portfolio-level insights
3. Provide clear investment recommendations with specific allocation guidance
4. Assess risk levels and diversification across the analyzed stocks
5. Create actionable investment strategies based on the analysis
6. Highlight key opportunities and risks
7. Provide implementation timelines and monitoring suggestions
8. Consider market conditions and sector correlations

Format your response as a professional investment report with clear sections, bullet points, and actionable recommendations. Always start with INDIVIDUAL STOCK ALLOCATION."""

        # Prepare the data for LLM analysis
        analysis_data = f"""**ANALYSIS STATISTICS:**
• Total Stocks Processed: {total_requested}
• Successfully Analyzed: {successful_count}
• Failed to Analyze: {failed_count}
• Success Rate: {(successful_count/total_requested)*100:.1f}%" if total_requested > 0 else "0%"
"""
        if investment_amount:
            analysis_data += f"• Investment Amount: {investment_amount}\n"

        if successful_analyses.strip():
            analysis_data += f"\n**SUCCESSFUL STOCK ANALYSES:**\n{successful_analyses}\n"
        
        if failed_analyses.strip():
            analysis_data += f"\n**FAILED ANALYSES:**\n{failed_analyses}\n"

        # User prompt with the analysis data
        user_prompt = f"""Please create a comprehensive investment report based on the following stock analysis results:

{analysis_data}

**REQUIRED REPORT SECTIONS (IN THIS ORDER):**

1. **INDIVIDUAL STOCK ALLOCATION** (FIRST)
   - For each BUY-recommended stock: Ticker, Amount to invest (USD), Allocation Percentage of total
   - If investment amount is not provided, provide percentage allocations and set amount to $0.00 (clearly note this)
   - Brief rationale for each allocation (one sentence)
2. **EXECUTIVE SUMMARY**: Key findings and overall investment outlook
3. **PORTFOLIO RECOMMENDATIONS**: Specific allocation strategy and stock selections
4. **RISK ASSESSMENT**: Risk analysis, diversification evaluation, and risk mitigation strategies
5. **SECTOR ANALYSIS**: Sector distribution and concentration risks/opportunities
6. **INVESTMENT STRATEGY**: Recommended approach (growth vs value, timing, etc.)
7. **IMPLEMENTATION PLAN**: Step-by-step execution guidance with timeline
8. **MONITORING & REBALANCING**: Ongoing portfolio management recommendations
9. **ALTERNATIVE SCENARIOS**: What-if analysis and contingency planning

**SPECIAL REQUIREMENTS:**
- If investment amount is provided, include specific dollar allocations and ensure totals match the investment amount
- Focus on actionable recommendations
- Use clear, professional language
- Provide specific numbers and percentages where possible
- Highlight key risks and opportunities"""

        # Generate aggregated report using LLM
        logger.info("Generating aggregated report using LLM")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=GenerateContentConfig(
                system_instruction=[system_prompt],
                temperature=0.4,  # Balanced temperature for creativity with consistency
                max_output_tokens=3000
            )
        )
        logger.info("Received LLM response for aggregated report")
        
        if response and response.text:
            aggregated_response = response.text.strip()
            logger.info(f"LLM aggregated report generated: {len(aggregated_response)} characters")
            
            # Format the response with header and statistics
            formatted_response = f"""**PARALLEL STOCK ANALYSIS - COMPREHENSIVE INVESTMENT REPORT**
{"=" * 70}

**ANALYSIS STATISTICS:**
• Total Stocks Processed: {total_requested}
• Successfully Analyzed: {successful_count}
• Failed to Analyze: {failed_count}
• Success Rate: {(successful_count/total_requested)*100:.1f}%" if total_requested > 0 else "0%"
{"• Investment Amount: " + investment_amount if investment_amount else ""}

{"=" * 70}

{aggregated_response}

{"=" * 70}
**REPORT COMPLETED**
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Method: AI-Generated Comprehensive Analysis
Analyst: Advanced Portfolio Management System"""
            
            # Log that we're sending the response back to host agent
            logger.info(f"Prepared formatted response for host agent: {len(formatted_response)} characters")
            logger.info("Response will be automatically sent back to host agent through A2A framework")
            send_analysis_to_webhook(formatted_response, email_to=email_to)
            return formatted_response
        else:
            logger.error("No response from LLM for aggregated report")
            # Fallback to basic summary if LLM fails
            basic_summary = f"""**PARALLEL STOCK ANALYSIS - BASIC SUMMARY**
{"=" * 60}

**ANALYSIS STATISTICS:**
• Total Stocks Processed: {total_requested}
• Successfully Analyzed: {successful_count}
• Failed to Analyze: {failed_count}
• Success Rate: {(successful_count/total_requested)*100:.1f}%" if total_requested > 0 else "0%"
{"• Investment Amount: " + investment_amount if investment_amount else ""}

**SUCCESSFUL ANALYSES:**
{successful_analyses if successful_analyses.strip() else "None"}

**FAILED ANALYSES:**
{failed_analyses if failed_analyses.strip() else "None"}

**Note:** Advanced LLM analysis was unavailable. Please review individual stock analyses above for investment decisions.

**ANALYSIS COMPLETED**
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            logger.info(f"Using fallback basic summary for host agent: {len(basic_summary)} characters")
            send_analysis_to_webhook(basic_summary, email_to=email_to)
            return basic_summary
            
    except Exception as e:
        error_msg = f"Error in LLM-based aggregation: {str(e)}"
        logger.error(error_msg)
        return f"**Error**: Failed to aggregate analysis results using LLM. {str(e)}"
    



def extract_stocks_from_analysis_request(analysis_request: str) -> str:
    """
    Uses LLM to extract stock tickers from a comprehensive analysis request.
    
    Args:
        analysis_request: The comprehensive analysis request containing stock lists
    
    Returns:
        A formatted string with extracted stock lists and analysis plan
    """
    try:
        # Log the analysis request for debugging
        logger.info(f"Using LLM to extract stocks from analysis request")
        
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
        system_prompt = """You are an expert financial analyst specializing in parsing investment analysis requests. Your task is to extract stock ticker symbols from analysis requests.

Extract stock tickers and classify them into two categories:
1. Existing portfolio stocks (stocks currently held)
2. New stocks to consider (stocks being suggested for analysis)

Rules:
- Extract only valid US stock ticker symbols (1-5 characters, letters only)
- Convert all tickers to uppercase
- Remove duplicates
- Look for patterns like "AAPL", "Apple Inc.", company names, etc.
- Distinguish between existing holdings vs new suggestions

Respond with ONLY comma-separated ticker lists in this format:
EXISTING: AAPL,GOOGL,MSFT
NEW: TSLA,F,GM

If no stocks found in a category, write: EXISTING: NONE or NEW: NONE"""

        # User prompt with the analysis request
        user_prompt = f"""Extract existing portfolio stocks and new stocks to consider from this analysis request:

{analysis_request}

Provide only the ticker lists in the specified format."""

        # Generate stock extraction using LLM
        logger.info("Generating stock extraction using LLM")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=GenerateContentConfig(
                system_instruction=[system_prompt]
            )
        )
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
        else:
            logger.error("No response from LLM for stock extraction")
            return "**Error**: Could not extract stocks using LLM. Please try again."
        
        # Create the result with only existing and new stocks
        result = ""
        
        result += f"**Existing Portfolio Stocks:** {len(existing_stocks)}\n"
        if existing_stocks:
            result += f"{', '.join(existing_stocks)}\n"
        else:
            result += "None\n"
        
        result += f"\n**New Stocks to Consider:** {len(new_stocks)}\n"
        if new_stocks:
            result += f"{', '.join(new_stocks)}\n"
        else:
            result += "None\n"
        
        logger.info(f"LLM-powered stock extraction complete: {len(existing_stocks)} existing, {len(new_stocks)} new stocks")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in LLM stock extraction: {str(e)}")
        return f"Error extracting stocks from analysis request: {e}"

def get_expert_stock_analysis(stock_analysis_response: str, ticker: str) -> str:
    """
    Uses LLM with expert system prompt to analyze stock technicals and other factors.
    
    Args:
        stock_analysis_response: The full stock analysis response from stock_analysis_tool
        ticker: The stock ticker symbol being analyzed
    
    Returns:
        Expert analysis of stock technicals and factors
    """
    try:
        logger.info(f"get_expert_stock_analysis called for ticker: {ticker}")
        # Create the client
        client = genai.Client()
        
        # Expert system prompt
        system_prompt = """You are an expert stock analyst with deep knowledge of technical analysis, fundamental analysis, and market psychology. You excel at:

1. **Technical Analysis**: Reading charts, identifying support/resistance levels, trend analysis, momentum indicators (RSI, MACD, Bollinger Bands), volume analysis, and pattern recognition.

2. **Fundamental Analysis**: Understanding company financials, earnings growth, revenue trends, debt levels, cash flow, and valuation metrics.

3. **Market Psychology**: Interpreting market sentiment, news impact, institutional behavior, and retail investor patterns.

4. **Risk Assessment**: Evaluating volatility, beta, correlation with market indices, sector performance, and macroeconomic factors.

5. **Portfolio Management**: Understanding diversification, sector allocation, risk-adjusted returns, and optimal position sizing.

Your analysis should be:
- **Data-driven**: Based on concrete metrics and indicators
- **Balanced**: Consider both bullish and bearish factors
- **Actionable**: Provide clear buy/sell/hold recommendations with reasoning
- **Risk-aware**: Always consider downside potential and risk factors
- **Context-aware**: Consider market conditions, sector trends, and economic environment

Analyze the provided stock data and give a comprehensive expert assessment."""

        # Create the user prompt with the stock analysis data
        user_prompt = f"""Please provide an expert analysis of {ticker} based on the following data:

{stock_analysis_response}

Provide your analysis in the following format:

**EXPERT ANALYSIS FOR {ticker}**

**Technical Assessment:**
- Key technical indicators and their interpretation
- Support/resistance levels
- Trend analysis and momentum
- Volume analysis

**Fundamental Assessment:**
- Key financial metrics
- Growth prospects
- Valuation analysis
- Competitive position

**Risk Factors:**
- Market risks
- Company-specific risks
- Sector risks
- Macroeconomic risks

**Market Sentiment:**
- Current market perception
- Institutional vs retail sentiment
- News impact assessment

**Expert Recommendation:**
- Clear buy/sell/hold recommendation
- Reasoning behind the recommendation
- Price targets (if applicable)
- Time horizon for the recommendation

**Portfolio Fit:**
- Suitable for what type of portfolio
- Position sizing recommendations
- Diversification considerations

Please be thorough but concise, focusing on the most important factors for investment decision-making."""

        # Generate the expert analysis using client API
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=GenerateContentConfig(
                system_instruction=[system_prompt]
            )
        )
        
        if response and response.text:
            # Log the expert analysis response
            logger.info(f"**EXPERT ANALYSIS FOR {ticker}**\n\n{response.text}")
            return response.text
        else:
            return f"**Error**: Could not generate expert analysis for {ticker}. Please try again."
            
    except Exception as e:
        return f"**Error generating expert analysis for {ticker}**: {str(e)}\n\n**Fallback**: Using basic summary analysis instead."



def handle_malformed_function_call_error() -> str:
    """
    Provides guidance when a malformed function call error occurs.
    
    Returns:
        A formatted string with troubleshooting steps and recovery guidance
    """
    return """
    **MALFORMED FUNCTION CALL ERROR DETECTED**

    **Common Causes:**
    - MCP connection failure (API keys missing or invalid)
    - Incorrect parameter format (missing quotes, wrong JSON structure)
    - Missing required parameters
    - Using undefined function names
    
    **IMMEDIATE RECOVERY:**
    If MCP tools are unavailable, proceed with basic analysis using available information:
    
    1. **Extract Stocks:** Use extract_stocks_from_analysis_request() to get ticker list
    2. **Provide Basic Analysis:** Create recommendations based on:
       - Known portfolio information from the request
       - General stock knowledge 
       - Risk diversification principles
    3. **Report MCP Issue:** Include message about data connectivity issues
    
    **CORRECT Function Call Examples:**
    
    1. **Extract Stocks:**
       extract_stocks_from_analysis_request(analysis_request="[FULL REQUEST TEXT]")
    
    2. **Get Stock Data:**
       Use stock_analysis_tool directly (it's an MCP toolset)
       Don't try to call it with custom parameters
    
    3. **Expert Analysis:**
       get_expert_stock_analysis(stock_analysis_response="[RAW DATA]", ticker="AAPL")

    **Recovery Steps:**
    1. Call `extract_stocks_from_analysis_request(analysis_request="[FULL REQUEST]")` first
    2. If MCP available: Use stock_analysis_tool for each stock ticker found
    3. If MCP fails: Provide general analysis with disclaimer about data availability
    4. Call `get_expert_stock_analysis(stock_analysis_response="[DATA]", ticker="TICKER")` for interpretation
    5. Use `aggregate_parallel_results` to organize results
    6. Provide final recommendations based on available information

    **Critical:** Always use proper JSON format with quotes around strings!
    **Fallback:** If MCP tools fail, still provide portfolio recommendations with data limitation disclaimers.
    """

def prepare_stock_analysis_summary(stocks_analyzed: str, total_investment: str) -> str:
    """
    Prepares a summary template for organizing stock analysis results.
    
    Args:
        stocks_analyzed: Comma-separated list of stocks that were analyzed
        total_investment: Total investment amount available
    
    Returns:
        A structured template for organizing analysis results
    """
    logger.info(f"Preparing stock analysis summary for stocks: {stocks_analyzed}, investment: {total_investment}")
    template = f"""
    **STOCK ANALYSIS SUMMARY TEMPLATE**
    
    **Investment Details:**
    - Total Investment Amount: {total_investment}
    - Stocks Analyzed: {stocks_analyzed}
    - Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    **Analysis Results Structure:**
    
    For each stock analyzed, include:
    1. **Raw Data Summary**: Key price, volume, and market cap data
    2. **Expert Analysis**: Professional interpretation and outlook
    3. **Recommendation**: Buy/Sell/Hold with confidence level
    4. **Allocation Suggestion**: Specific dollar amount or percentage
    5. **Risk Assessment**: High/Medium/Low risk classification
    
    **Portfolio Recommendations:**
    1. **Allocation Distribution**: Percentage breakdown across all stocks
    2. **Risk Diversification**: Balance across sectors and risk levels
    3. **Implementation Timeline**: Immediate vs. staged investments
    
    **Failed Analyses:**
    - List any stocks that could not be analyzed with reasons
    
    Use this structure to organize your comprehensive analysis results.
    """
    
    return template


def send_analysis_to_webhook(analysis_response: str, email_to: str, webhook_url: str = None, username: str = None, password: str = None) -> str:
    """
    Securely sends analysis response data to the Activepieces webhook endpoint.
    
    Args:
        analysis_response: The analysis data to send
        webhook_url: Webhook URL (defaults to Activepieces endpoint)
        username: Basic auth username (defaults to environment variable)
        password: Basic auth password (defaults to environment variable)
    
    Returns:
        Success/error message with details
    """
    try:
        logger.info("Preparing to send analysis response to webhook endpoint")
        # Use environment variables for sensitive data if not provided
        webhook_url = webhook_url or "https://cloud.activepieces.com/api/v1/webhooks/BzkDtbfmZODV2C3jotH94"
        username = username or os.getenv("ACTIVEPIECES_USERNAME")
        password = password or os.getenv("ACTIVEPIECES_PASSWORD")
        
        # Validate required parameters
        if not username or not password:
            logger.error("Missing Activepieces authentication credentials")
            return "Error: Missing authentication credentials. Please set ACTIVEPIECES_USERNAME and ACTIVEPIECES_PASSWORD environment variables."
        
        if not analysis_response or not analysis_response.strip():
            logger.error("Empty analysis response provided")
            return "Error: Analysis response cannot be empty."
        
        # Prepare the request data - match the working curl payload structure
        payload = {
            "analysis_response": analysis_response,
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
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        logger.info(f"Headers: {json.dumps({k: v for k, v in headers.items() if k != 'Authorization'}, indent=2)}")
        logger.info(f"Auth: Basic {encoded_credentials[:10]}...")
        
        # Make the POST request - exactly like your curl
        response = requests.post(
            webhook_url,
            json=payload,
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
    except requests.exceptions.ConnectionError:
        logger.error("Connection error - unable to reach webhook endpoint")
        return "Error: Connection error. Unable to reach the webhook endpoint."
    except requests.exceptions.SSLError:
        logger.error("SSL certificate verification failed")
        return "Error: SSL certificate verification failed. Please check the webhook endpoint."
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return f"Error: Request failed - {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error sending to webhook: {str(e)}")
        return f"Error: Unexpected error occurred - {str(e)}"


# Create function tools with basic FunctionTool (no explicit schemas)
extract_stocks_from_analysis_request_tool = FunctionTool(extract_stocks_from_analysis_request)
get_expert_stock_analysis_tool = FunctionTool(get_expert_stock_analysis)
handle_malformed_function_call_error_tool = FunctionTool(handle_malformed_function_call_error)
aggregate_parallel_results_tool = FunctionTool(aggregate_parallel_results)

def create_agent() -> LlmAgent:
    """Constructs the ADK agent for stock analysis and allocation management."""
    return LlmAgent(
        model="gemini-2.5-flash",
        name="stock_analyser_agent",
        instruction="""
            **Role:** You are a professional stock analyst. You MUST follow this EXACT workflow step by step.

            **CRITICAL WORKFLOW - FOLLOW EXACTLY:**

            **STEP 1 - Extract Stocks (REQUIRED FIRST STEP):**
            When you receive ANY analysis request, IMMEDIATELY call:
            extract_stocks_from_analysis_request(analysis_request="[COPY THE ENTIRE REQUEST TEXT HERE]")
            
            **STEP 2 - Execute Parallel Analysis:**
            After getting the stock list from STEP 1, for EACH stock ticker:
            a) Use stock_analysis_tool MCP tool to get market data for the ticker
            b) Call get_expert_stock_analysis(stock_analysis_response="[data from stock_analysis_tool]", ticker="TICKER")
            c) Collect successful analyses in a list
            d) Collect failed analyses in a list
            
            **STEP 3 - Aggregate Results (FINAL STEP):**
            After ALL individual stock analyses are complete, call:
            aggregate_parallel_results(
                successful_analyses="[ALL successful results combined]",
                failed_analyses="[ALL failed messages combined]", 
                investment_amount="[amount from request]",
                email_to="[email id from request]"
            )

            **IMPORTANT RULES:**
            - ALWAYS start with STEP 1 (extract_stocks_from_analysis_request)
            - NEVER skip any step
            - ALWAYS wait for each function call to complete before proceeding
            - Use the EXACT function names and parameters shown above
            - If any step fails, use handle_malformed_function_call_error() for guidance
            
            **EXAMPLE WORKFLOW:**
            1. Call: extract_stocks_from_analysis_request(analysis_request="[full request]")
            2. For each stock returned: get_expert_stock_analysis(...)
            3. Call: aggregate_parallel_results(...)
            
            **ERROR HANDLING:**
            - If you get MALFORMED_FUNCTION_CALL, use handle_malformed_function_call_error()
            - If individual stock analysis fails, continue with other stocks
            - Report failed stocks as: "[TICKER] stock could not be analysed (try again later)"
            
            **Professional Standards:**
            - Use precise financial terminology
            - Provide objective, data-driven analysis
            - Focus on actionable investment recommendations
            - Consider portfolio diversification and risk management
            
            **Scope:** Comprehensive portfolio analysis, stock analysis, and allocation management.
        """,
        tools=[
            stock_analysis_tool,
            extract_stocks_from_analysis_request_tool,
            get_expert_stock_analysis_tool,
            handle_malformed_function_call_error_tool,
            aggregate_parallel_results_tool,
        ],
    )
