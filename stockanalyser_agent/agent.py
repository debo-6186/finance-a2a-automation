from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.tools import FunctionTool
import json
import os
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import concurrent.futures
import traceback
from logger import setup_logging, get_logger, get_log_file_path
from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

# Setup logging and get log file path
log_file_path = setup_logging()
logger = get_logger(__name__)
logger.info(f"Logging initialized. Log file: {log_file_path}")

# stock_analysis_tool = MCPToolset(
#     connection_params=StdioServerParameters(
#         command="uv",
#         args=[
#             "--directory", 
#             "/Users/debojyotichakraborty/codebase/mcp-yfinance-server",
#             "run", 
#             "source/yf_server.py"
#         ]
#     )
# )

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

# stock_analysis_tool = MCPToolset(
#     connection_params=StdioServerParameters(
#         command="uv",
#         args=[
#             "--directory", 
#             "/Users/debojyotichakraborty/codebase/mcp-yfinance",
#             "run", 
#             "mcp_yfinance/server.py"
#         ]
#     )
# )

# stock_analysis_tool = MCPToolset(
#     connection_params=StdioServerParameters(
#         command="/Users/debojyotichakraborty/.pyenv/shims/python",
#         args=[
#             "/Users/debojyotichakraborty/codebase/mcp-yfinance/server.py",
#         ]
#     )
# )

def analyze_single_stock_parallel(ticker: str, stock_analysis_tool) -> Dict[str, str]:
    """
    Analyzes a single stock by getting market data and expert analysis.
    
    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        stock_analysis_tool: The MCP toolset for stock analysis
    
    Returns:
        Dictionary with ticker, raw_data, expert_analysis, and status
    """
    try:
        logger.info(f"Starting parallel analysis for {ticker}")
        
        # Step 2: Get stock market data using MCP tool
        # Note: The actual MCP tool call will be handled by the LLM
        # This function serves as a template for the parallel structure
        
        result = {
            'ticker': ticker,
            'raw_data': '',
            'expert_analysis': '',
            'status': 'pending',
            'error_message': ''
        }
        
        # The actual implementation will be handled by the LLM calling MCP tools
        # This is a structural template for parallel processing
        logger.info(f"Parallel analysis template ready for {ticker}")
        return result
        
    except Exception as e:
        logger.error(f"Error in parallel analysis for {ticker}: {str(e)}")
        return {
            'ticker': ticker,
            'raw_data': '',
            'expert_analysis': '',
            'status': 'failed',
            'error_message': f"{ticker} stock could not be analysed (error: {str(e)} - try again later)"
        }


def execute_parallel_stock_analysis(tickers: str) -> str:
    """
    Provides detailed instructions for executing parallel stock analysis.
    
    Args:
        tickers: Comma-separated string of stock tickers
    
    Returns:
        Detailed parallel execution instructions for the LLM
    """
    try:
        ticker_list = [ticker.strip().upper() for ticker in tickers.split(',') if ticker.strip()]
        
        if not ticker_list:
            return "Error: No valid tickers provided for parallel analysis."
        
        logger.info(f"Generating parallel execution instructions for {len(ticker_list)} stocks")
        
        instructions = f"""
        **PARALLEL STOCK ANALYSIS EXECUTION PLAN**
        
        **Stocks for Parallel Processing:** {', '.join(ticker_list)}
        **Total Stocks:** {len(ticker_list)}
        
        **EXECUTE THESE SIMULTANEOUSLY (IN PARALLEL):**
        
        For EACH ticker below, perform BOTH steps at the same time:
        
        """
        
        for i, ticker in enumerate(ticker_list, 1):
            instructions += f"""
        **PARALLEL TASK {i} - {ticker}:**
        Step A: Call stock_analysis_tool for {ticker} to get market data
        Step B: When data received, immediately call get_expert_stock_analysis(stock_analysis_response="[{ticker} data]", ticker="{ticker}")
        
        """
        
        instructions += f"""
        **PARALLEL EXECUTION REQUIREMENTS:**
        
        1. **Simultaneous Processing:** Start analysis for ALL {len(ticker_list)} stocks at the same time
        2. **Independent Results:** Keep each stock's analysis completely separate
        3. **Error Isolation:** If one stock fails, continue with others
        4. **Data Integrity:** Never mix data between different stocks
        
        **EXPECTED PARALLEL OUTPUTS:**
        
        For each successful stock, collect:
        - Ticker symbol
        - Raw market data from stock_analysis_tool
        - Expert analysis and recommendation
        - Buy/Sell/Hold recommendation
        - Suggested allocation percentage
        
        For each failed stock, collect:
        - Error message: "[TICKER] stock could not be analysed (try again later)"
        
        **NEXT STEP AFTER PARALLEL COMPLETION:**
        Use aggregate_parallel_results() to combine all results into final recommendations.
        
        **START PARALLEL EXECUTION NOW FOR:** {', '.join(ticker_list)}
        """
        
        return instructions
        
    except Exception as e:
        logger.error(f"Error generating parallel execution instructions: {str(e)}")
        return f"Error: Failed to generate parallel execution plan. {str(e)}"


def calculate_investment_allocation(analysis_results: str, investment_amount: str) -> str:
    """
    Calculates specific dollar amounts for each BUY recommendation based on investment amount.
    
    Args:
        analysis_results: String containing all stock analysis results
        investment_amount: Total amount available for investment
    
    Returns:
        Formatted investment allocation with specific dollar amounts
    """
    try:
        # Parse the investment amount to get numeric value
        investment_amount_numeric = 0
        import re
        amount_match = re.search(r'[\d,]+\.?\d*', investment_amount.replace(',', ''))
        if amount_match:
            investment_amount_numeric = float(amount_match.group().replace(',', ''))
        
        if investment_amount_numeric <= 0:
            return "Error: Invalid investment amount provided. Please provide a valid dollar amount."
        
        # Parse analysis results to extract BUY recommendations
        buy_stocks = []
        hold_stocks = []
        sell_stocks = []
        
        if analysis_results:
            # Split analyses by stock sections
            stock_sections = analysis_results.split("**EXPERT ANALYSIS FOR")
            
            for section in stock_sections[1:]:  # Skip first empty section
                try:
                    # Extract ticker from section
                    lines = section.split('\n')
                    ticker_line = lines[0] if lines else ""
                    ticker = ticker_line.strip().replace('**', '').strip()
                    
                    # Look for recommendations in the section
                    section_text = section.upper()
                    
                    if 'BUY' in section_text and ('RECOMMENDATION' in section_text or 'EXPERT RECOMMENDATION' in section_text):
                        # Check if it's actually a BUY recommendation
                        if 'BUY' in section_text and 'SELL' not in section_text.replace('BUY', ''):
                            buy_stocks.append(ticker)
                    elif 'HOLD' in section_text and ('RECOMMENDATION' in section_text or 'EXPERT RECOMMENDATION' in section_text):
                        hold_stocks.append(ticker)
                    elif 'SELL' in section_text and ('RECOMMENDATION' in section_text or 'EXPERT RECOMMENDATION' in section_text):
                        sell_stocks.append(ticker)
                except:
                    continue
        
        # Format the results
        result_parts = []
        result_parts.append("**INVESTMENT ALLOCATION BASED ON EXPERT RECOMMENDATIONS**")
        result_parts.append("=" * 60)
        result_parts.append("")
        result_parts.append(f"Total Investment Amount: {investment_amount}")
        result_parts.append("")
        
        if buy_stocks:
            # Calculate equal allocation among BUY stocks
            amount_per_stock = investment_amount_numeric / len(buy_stocks)
            
            result_parts.append("**1) STOCK ALLOCATION:**")
            for stock in buy_stocks:
                result_parts.append(f"Stock Ticker: {stock}, Amount to invest: ${amount_per_stock:,.2f}")
            result_parts.append("")
            
            result_parts.append("**2) RATIONALE / DETAILS:**")
            result_parts.append(f"• BUY Recommendations: {len(buy_stocks)} stocks")
            result_parts.append(f"• HOLD Recommendations: {len(hold_stocks)} stocks")
            result_parts.append(f"• SELL Recommendations: {len(sell_stocks)} stocks")
            result_parts.append(f"• Equal allocation strategy: ${amount_per_stock:,.2f} per BUY stock")
            result_parts.append(f"• Total allocation: ${investment_amount_numeric:,.2f} (100% of available funds)")
            result_parts.append("• Diversification across multiple BUY recommendations")
            result_parts.append("• Based on comprehensive expert analysis and market assessment")
            
            if hold_stocks:
                result_parts.append(f"• HOLD stocks ({', '.join(hold_stocks)}): No new investment recommended")
            if sell_stocks:
                result_parts.append(f"• SELL stocks ({', '.join(sell_stocks)}): Consider exiting positions")
        else:
            result_parts.append("**1) STOCK ALLOCATION:**")
            result_parts.append("No BUY recommendations found in the analysis results.")
            result_parts.append("")
            result_parts.append("**2) RATIONALE / DETAILS:**")
            result_parts.append(f"• BUY Recommendations: 0 stocks")
            result_parts.append(f"• HOLD Recommendations: {len(hold_stocks)} stocks")
            result_parts.append(f"• SELL Recommendations: {len(sell_stocks)} stocks")
            result_parts.append("• No new investments recommended at this time")
            result_parts.append("• Consider holding cash or reviewing alternative investment options")
            
            if hold_stocks:
                result_parts.append(f"• HOLD stocks ({', '.join(hold_stocks)}): Maintain current positions")
            if sell_stocks:
                result_parts.append(f"• SELL stocks ({', '.join(sell_stocks)}): Consider reducing positions")
        
        return "\n".join(result_parts)
        
    except Exception as e:
        logger.error(f"Error calculating investment allocation: {str(e)}")
        return f"Error calculating investment allocation: {str(e)}"


def aggregate_parallel_results(successful_analyses: str, failed_analyses: str, investment_amount: str = "") -> str:
    """
    Aggregates results from parallel stock analyses and provides comprehensive recommendations.
    
    Args:
        successful_analyses: String containing all successful stock analyses
        failed_analyses: String containing all failed stock analysis messages
        investment_amount: Total investment amount (optional)
    
    Returns:
        Comprehensive aggregated analysis and recommendations
    """
    try:
        # Parse the input strings to understand the data
        if not successful_analyses.strip() and not failed_analyses.strip():
            return "Error: No analysis results provided for aggregation."
        
        # Count successful and failed analyses by parsing the input strings
        successful_count = successful_analyses.count("**") if successful_analyses else 0
        failed_count = failed_analyses.count("could not be analysed") if failed_analyses else 0
        total_requested = successful_count + failed_count
        
        logger.info(f"Aggregating results: {successful_count} successful, {failed_count} failed")
        
        report_parts = []
        
        # Header
        report_parts.append("**PARALLEL STOCK ANALYSIS - AGGREGATED RESULTS**")
        report_parts.append("=" * 60)
        report_parts.append("")
        
        # Summary Statistics
        report_parts.append("**ANALYSIS SUMMARY:**")
        report_parts.append(f"• Total Stocks Processed: {total_requested}")
        report_parts.append(f"• Successfully Analyzed: {successful_count}")
        report_parts.append(f"• Failed to Analyze: {failed_count}")
        if investment_amount:
            report_parts.append(f"• Investment Amount: {investment_amount}")
        report_parts.append(f"• Success Rate: {(successful_count/total_requested)*100:.1f}%" if total_requested > 0 else "• Success Rate: 0%")
        report_parts.append("")
        
        # Successful Analyses
        if successful_analyses.strip():
            report_parts.append("**SUCCESSFUL STOCK ANALYSES:**")
            report_parts.append("-" * 40)
            report_parts.append("")
            report_parts.append(successful_analyses)
            report_parts.append("")
            report_parts.append("-" * 40)
            report_parts.append("")
        
        # Failed Analyses
        if failed_analyses.strip():
            report_parts.append("**FAILED ANALYSES:**")
            report_parts.append("-" * 20)
            report_parts.append(failed_analyses)
            report_parts.append("")
        
        # Portfolio Recommendations
        if successful_analyses.strip():
            report_parts.append("**AGGREGATED PORTFOLIO RECOMMENDATIONS:**")
            report_parts.append("=" * 50)
            report_parts.append("")
            
            report_parts.append("**ALLOCATION STRATEGY:**")
            report_parts.append(f"Based on {successful_count} successfully analyzed stocks")
            report_parts.append("Review individual expert recommendations above for specific allocation guidance")
            report_parts.append("")
            
            if investment_amount:
                # Parse the investment amount to get numeric value
                investment_amount_numeric = 0
                try:
                    # Extract numeric value from investment amount string
                    import re
                    amount_match = re.search(r'[\d,]+\.?\d*', investment_amount.replace(',', ''))
                    if amount_match:
                        investment_amount_numeric = float(amount_match.group().replace(',', ''))
                except:
                    investment_amount_numeric = 0
                
                # Parse successful analyses to extract BUY recommendations
                buy_stocks = []
                if successful_analyses and investment_amount_numeric > 0:
                    # Split analyses by stock sections
                    stock_sections = successful_analyses.split("**EXPERT ANALYSIS FOR")
                    
                    for section in stock_sections[1:]:  # Skip first empty section
                        try:
                            # Extract ticker from section
                            lines = section.split('\n')
                            ticker_line = lines[0] if lines else ""
                            ticker = ticker_line.strip().replace('**', '').strip()
                            
                            # Look for BUY recommendation in the section
                            section_text = section.upper()
                            if 'BUY' in section_text and ('RECOMMENDATION' in section_text or 'EXPERT RECOMMENDATION' in section_text):
                                # Check if it's actually a BUY recommendation (not SELL or HOLD)
                                if 'BUY' in section_text and 'SELL' not in section_text.replace('BUY', ''):
                                    buy_stocks.append(ticker)
                        except:
                            continue
                
                report_parts.append(f"**INVESTMENT ALLOCATION RECOMMENDATIONS:**")
                report_parts.append(f"Total Investment Amount: {investment_amount}")
                report_parts.append("")
                
                if buy_stocks and investment_amount_numeric > 0:
                    # Calculate equal allocation among BUY stocks (can be modified for weighted allocation)
                    amount_per_stock = investment_amount_numeric / len(buy_stocks)
                    
                    report_parts.append("**1) STOCK ALLOCATION:**")
                    for stock in buy_stocks:
                        report_parts.append(f"Stock Ticker: {stock}, Amount to invest: ${amount_per_stock:,.2f}")
                    report_parts.append("")
                    
                    report_parts.append("**2) RATIONALE / DETAILS:**")
                    report_parts.append(f"• Total stocks recommended for BUY: {len(buy_stocks)}")
                    report_parts.append(f"• Equal allocation strategy: ${amount_per_stock:,.2f} per stock")
                    report_parts.append(f"• Based on expert analysis showing BUY recommendations")
                    report_parts.append(f"• Diversification across {len(buy_stocks)} different stocks")
                    report_parts.append("• Review individual expert analysis above for detailed reasoning")
                    report_parts.append("• Consider adjusting amounts based on risk tolerance and conviction levels")
                    report_parts.append("")
                    
                    report_parts.append("**IMPLEMENTATION NOTES:**")
                    report_parts.append("• Execute BUY orders for the recommended amounts")
                    report_parts.append("• Consider dollar-cost averaging for large positions")
                    report_parts.append("• Set appropriate stop-loss levels based on expert analysis")
                    report_parts.append("• Monitor performance and rebalance as needed")
                else:
                    report_parts.append("**1) STOCK ALLOCATION:**")
                    report_parts.append("No BUY recommendations found in the analysis results.")
                    report_parts.append("")
                    report_parts.append("**2) RATIONALE / DETAILS:**")
                    report_parts.append("• No stocks received BUY recommendations from expert analysis")
                    report_parts.append("• Consider holding cash or reviewing other investment options")
                    report_parts.append("• Check individual stock analyses above for HOLD or SELL recommendations")
                
                report_parts.append("")
            
            report_parts.append("**PORTFOLIO DIVERSIFICATION:**")
            report_parts.append("• Review sector distribution across analyzed stocks")
            report_parts.append("• Consider risk levels of individual recommendations")
            report_parts.append("• Monitor correlation between selected stocks")
            report_parts.append("• Balance growth vs. value stocks based on expert analysis")
            report_parts.append("")
            
            report_parts.append("**IMPLEMENTATION RECOMMENDATIONS:**")
            report_parts.append("• Prioritize stocks with 'BUY' recommendations")
            report_parts.append("• Consider position sizing based on confidence levels")
            report_parts.append("• Implement dollar-cost averaging for large investments")
            report_parts.append("• Set stop-loss levels based on expert analysis")
            report_parts.append("• Review and rebalance portfolio quarterly")
            
        else:
            report_parts.append("**NO SUCCESSFUL ANALYSES AVAILABLE**")
            report_parts.append("Unable to provide portfolio recommendations due to analysis failures.")
            report_parts.append("Please retry with different stocks or check data availability.")
        
        report_parts.append("")
        report_parts.append("**ANALYSIS COMPLETED**")
        report_parts.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        final_report = "\n".join(report_parts)
        logger.info(f"Aggregated report generated: {len(final_report)} characters")
        
        return final_report
        
    except Exception as e:
        error_msg = f"Error aggregating parallel results: {str(e)}"
        logger.error(error_msg)
        return f"**Error**: Failed to aggregate analysis results. {str(e)}"


def get_allocation_list() -> str:
    """
    Reads the current allocation list from the allocation.json file.
    Returns the current allocation as a formatted string.
    """
    try:
        # Construct an absolute path to the allocation file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        allocation_path = os.path.join(agent_dir, "allocation.json")
        
        if not os.path.exists(allocation_path):
            return "No allocation list found. The allocation list is empty."
        
        with open(allocation_path, 'r') as f:
            allocation_data = json.load(f)
        
        if not allocation_data:
            return "Allocation list is empty."
        
        result = "Current Allocation List:\n"
        for i, stock in enumerate(allocation_data, 1):
            result += f"{i}. {stock}\n"
        
        result += f"\nTotal stocks in allocation: {len(allocation_data)}"
        return result
        
    except json.JSONDecodeError as e:
        return f"Error reading allocation file: {e}"
    except Exception as e:
        return f"Error reading allocation list: {e}"


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
            return f"**EXPERT ANALYSIS FOR {ticker}**\n\n{response.text}"
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
       ✅ extract_stocks_from_analysis_request(analysis_request="[FULL REQUEST TEXT]")
       ❌ extract_stocks_from_analysis_request([FULL REQUEST TEXT])
    
    2. **Get Stock Data:**
       ✅ Use stock_analysis_tool directly (it's an MCP toolset)
       ❌ Don't try to call it with custom parameters
    
    3. **Expert Analysis:**
       ✅ get_expert_stock_analysis(stock_analysis_response="[RAW DATA]", ticker="AAPL")
       ❌ get_expert_stock_analysis([RAW DATA], AAPL)

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


# Create function tools
extract_stocks_from_analysis_request_tool = FunctionTool(extract_stocks_from_analysis_request)
get_expert_stock_analysis_tool = FunctionTool(get_expert_stock_analysis)
get_log_file_path_tool = FunctionTool(get_log_file_path)
handle_malformed_function_call_error_tool = FunctionTool(handle_malformed_function_call_error)
prepare_stock_analysis_summary_tool = FunctionTool(prepare_stock_analysis_summary)
execute_parallel_stock_analysis_tool = FunctionTool(execute_parallel_stock_analysis)
calculate_investment_allocation_tool = FunctionTool(calculate_investment_allocation)
aggregate_parallel_results_tool = FunctionTool(aggregate_parallel_results)

def create_agent() -> LlmAgent:
    """Constructs the ADK agent for stock analysis and allocation management."""
    return LlmAgent(
        model="gemini-2.5-flash",
        name="stock_analyser_agent",
        instruction="""
            **Role:** You are a professional stock analyst. Analyze stocks in parallel and send incremental updates to prevent timeouts.

            **TIMEOUT PREVENTION WORKFLOW:**
            
            **STEP 1 - Extract Stocks:**
            Call: extract_stocks_from_analysis_request(analysis_request="[full request text]")
            
            **STEP 2 - Get Parallel Execution Plan:**
            Call: execute_parallel_stock_analysis(tickers="TICKER1,TICKER2,TICKER3")
            
            **STEP 3 - Execute Parallel Analysis WITH PROGRESS UPDATES:**
            For EACH stock ticker simultaneously (in parallel):
            a) Use stock_analysis_tool to get market data for the ticker
            b) If expert analysis takes time: prevent_timeout_with_keepalive(operation_name="Expert analysis for TICKER")
            c) Call get_expert_stock_analysis(stock_analysis_response="[data]", ticker="TICKER")
            
            **ERROR HANDLING:**
            - If MCP connection fails, use handle_malformed_function_call_error() for guidance
            - If individual stock analysis fails, continue with other stocks
            - Report failed stocks as: "[TICKER] stock could not be analysed (try again later)"
            
            **STEP 4 - Send Final Summary:**
            After all individual stock updates are sent, call:
            Then call: aggregate_parallel_results(
                successful_analyses="[all successful results]",
                failed_analyses="[all failed messages]", 
                investment_amount="[amount]"
            )
            
            **OPTIONAL - Specific Investment Allocation:**
            For detailed dollar amount breakdown, you can also use:
            calculate_investment_allocation(
                analysis_results="[all successful analyses]",
                investment_amount="[dollar amount]"
            )
            This provides the exact format: "Stock Ticker: XYZ, Amount to invest: $123"
            
            **Key Principles:**
            - Analyze each stock individually using available MCP tools
            - Don't repeat function calls for the same stock
            - Continue processing other stocks if one fails
            - Focus recommendations on successfully analyzed stocks only
            
            **Response Format:**
            1. **Portfolio Recommendations**: 
                - Recommended allocation percentages based on successful analyses and investment amount (which is inside analysis request)
                - Suggest Diversification improvements if required
                - Risk management suggestions
            2. **Portfolio Overview**: Summary of existing portfolio distribution
            3. **Stock-by-Stock Analysis**: For each successfully analyzed stock:
                - Raw data from MCP tools
                - Expert analysis and recommendations
                - Buy/sell/hold recommendations with reasoning
            4. **Failed Stocks**: List any stocks that could not be analyzed with error messages
            5. **Final Summary**: Updated allocation recommendations
            6. **Send the message to host agent.**
            
            **Error Handling:**
            - If individual stock analysis fails, report "XXX stock could not be analysed (try again later)"
            - Continue with other stocks
            - If you encounter errors, use `handle_malformed_function_call_error` for guidance
            - Make recommendations only based on successfully analyzed stocks
            
            **Professional Standards:**
            - Use precise financial terminology
            - Provide objective, data-driven analysis
            - Highlight both positive and negative aspects
            - Include relevant financial ratios and comparisons
            - Always consider the existing portfolio distribution
            - Prioritize diversification and risk management
            - Be transparent about data limitations
            
            **Scope:** Focus on comprehensive portfolio analysis, stock analysis, and allocation management. Provide thorough, actionable investment recommendations based on available data.
        """,
        tools=[
            stock_analysis_tool,
            extract_stocks_from_analysis_request_tool,
            get_expert_stock_analysis_tool,
            handle_malformed_function_call_error_tool,
            execute_parallel_stock_analysis_tool,
            calculate_investment_allocation_tool,
            aggregate_parallel_results_tool
        ],
    )
