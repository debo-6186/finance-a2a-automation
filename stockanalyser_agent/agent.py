from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.tools import FunctionTool
import json
import os
from typing import List, Dict, Optional

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

def read_stock_data() -> str:
    """
    Reads the stock data from the JSON file containing categorized stock tickers.
    Returns the stock data as a formatted string for analysis.
    """
    try:
        # Construct an absolute path to the JSON file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(agent_dir, "stock_data.json")
        
        if not os.path.exists(json_path):
            return "Error: stock_data.json not found. Please ensure the stock data file exists."
        
        with open(json_path, 'r') as f:
            stock_data = json.load(f)
        
        # Format the data for better readability
        formatted_data = "Available Stock Categories:\n"
        for category, tickers in stock_data.items():
            formatted_data += f"\n{category}:\n"
            formatted_data += f"  Tickers: {', '.join(tickers)}\n"
            formatted_data += f"  Count: {len(tickers)} stocks\n"
        
        return formatted_data
        
    except json.JSONDecodeError as e:
        return f"Error reading JSON file: {e}"
    except Exception as e:
        return f"Error reading stock data: {e}"

def suggest_stocks_by_category(country: str, domain: str) -> str:
    """
    Suggests top stocks for a specific country and domain.
    
    Args:
        country: The country (e.g., 'USA', 'INDIA')
        domain: The domain/sector (e.g., 'TECHNOLOGY', 'FINANCIAL', 'AUTOMOBILE')
    
    Returns:
        A formatted string with suggested stocks for the specified category
    """
    try:
        # Construct an absolute path to the JSON file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(agent_dir, "stock_data.json")
        
        if not os.path.exists(json_path):
            return "Error: stock_data.json not found. Please ensure the stock data file exists."
        
        with open(json_path, 'r') as f:
            stock_data = json.load(f)
        
        # Create the category key
        category_key = f"{country.upper()}_TOP_{domain.upper()}_STOCKS"
        
        if category_key not in stock_data:
            available_categories = list(stock_data.keys())
            return f"Error: Category '{category_key}' not found. Available categories:\n" + "\n".join(available_categories)
        
        tickers = stock_data[category_key]
        
        result = f"Top {domain.lower()} stocks for {country}:\n"
        result += f"Category: {category_key}\n"
        result += f"Number of stocks: {len(tickers)}\n"
        result += f"Stock tickers: {', '.join(tickers)}\n\n"
        result += "These stocks represent the top performers in this category and can be considered for portfolio allocation."
        
        return result
        
    except json.JSONDecodeError as e:
        return f"Error reading JSON file: {e}"
    except Exception as e:
        return f"Error suggesting stocks: {e}"

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

def get_allocation_analysis() -> str:
    """
    Provides analysis recommendations for all stocks in the allocation list.
    Returns a formatted string with analysis suggestions for each stock.
    """
    try:
        # Construct an absolute path to the allocation file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        allocation_path = os.path.join(agent_dir, "allocation.json")
        
        if not os.path.exists(allocation_path):
            return "No allocation list found. Please add stocks to allocation first."
        
        with open(allocation_path, 'r') as f:
            allocation_data = json.load(f)
        
        if not allocation_data:
            return "Allocation list is empty. Please add stocks to allocation first."
        
        result = "📊 **Allocation Analysis Recommendations:**\n\n"
        result += f"You have {len(allocation_data)} stocks in your allocation list.\n\n"
        result += "**Recommended Analysis Actions:**\n\n"
        
        for i, stock in enumerate(allocation_data, 1):
            result += f"{i}. **{stock}** - Analyze this stock for:\n"
            result += f"   - Current price and trend analysis\n"
            result += f"   - Technical indicators (RSI, MACD, Bollinger Bands)\n"
            result += f"   - News and market sentiment\n"
            result += f"   - Buy/Sell/Hold recommendations\n"
            result += f"   - Risk assessment and price targets\n\n"
        
        result += "**Next Steps:**\n"
        result += "- Use the stock_analysis_tool to analyze each stock individually\n"
        result += "- Consider portfolio diversification across sectors\n"
        result += "- Monitor allocation performance regularly\n"
        result += "- Rebalance allocation based on analysis results\n\n"
        
        result += "**Allocation List:**\n"
        for i, stock in enumerate(allocation_data, 1):
            result += f"{i}. {stock}\n"
        
        return result
        
    except json.JSONDecodeError as e:
        return f"Error reading allocation file: {e}"
    except Exception as e:
        return f"Error getting allocation analysis: {e}"

def add_stocks_to_allocation(stocks: List[str]) -> str:
    """
    Adds stocks to the allocation list.
    
    Args:
        stocks: List of stock tickers to add to allocation
    
    Returns:
        Confirmation message with updated allocation list
    """
    try:
        # Construct an absolute path to the allocation file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        allocation_path = os.path.join(agent_dir, "allocation.json")
        
        # Load existing allocation or create new one
        current_allocation = []
        if os.path.exists(allocation_path):
            with open(allocation_path, 'r') as f:
                current_allocation = json.load(f)
        
        # Add new stocks (avoid duplicates)
        added_stocks = []
        for stock in stocks:
            stock_upper = stock.upper().strip()
            if stock_upper not in current_allocation:
                current_allocation.append(stock_upper)
                added_stocks.append(stock_upper)
        
        # Save updated allocation
        with open(allocation_path, 'w') as f:
            json.dump(current_allocation, f, indent=2)
        
        result = f"Successfully added {len(added_stocks)} stocks to allocation:\n"
        if added_stocks:
            result += f"Added: {', '.join(added_stocks)}\n"
        
        result += f"\nCurrent allocation has {len(current_allocation)} stocks total."
        
        # Add analysis recommendation
        if added_stocks:
            result += f"\n\n💡 **Analysis Recommendation:** Consider analyzing the newly added stocks: {', '.join(added_stocks)}"
        
        return result
        
    except Exception as e:
        return f"Error adding stocks to allocation: {e}"

def remove_stocks_from_allocation(stocks: List[str]) -> str:
    """
    Removes stocks from the allocation list.
    
    Args:
        stocks: List of stock tickers to remove from allocation
    
    Returns:
        Confirmation message with updated allocation list
    """
    try:
        # Construct an absolute path to the allocation file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        allocation_path = os.path.join(agent_dir, "allocation.json")
        
        if not os.path.exists(allocation_path):
            return "No allocation list found to remove stocks from."
        
        with open(allocation_path, 'r') as f:
            current_allocation = json.load(f)
        
        # Remove specified stocks
        removed_stocks = []
        for stock in stocks:
            stock_upper = stock.upper().strip()
            if stock_upper in current_allocation:
                current_allocation.remove(stock_upper)
                removed_stocks.append(stock_upper)
        
        # Save updated allocation
        with open(allocation_path, 'w') as f:
            json.dump(current_allocation, f, indent=2)
        
        result = f"Successfully removed {len(removed_stocks)} stocks from allocation:\n"
        if removed_stocks:
            result += f"Removed: {', '.join(removed_stocks)}\n"
        
        result += f"\nCurrent allocation has {len(current_allocation)} stocks total."
        return result
        
    except Exception as e:
        return f"Error removing stocks from allocation: {e}"

def clear_allocation_list() -> str:
    """
    Clears the entire allocation list.
    
    Returns:
        Confirmation message
    """
    try:
        # Construct an absolute path to the allocation file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        allocation_path = os.path.join(agent_dir, "allocation.json")
        
        # Clear the allocation
        with open(allocation_path, 'w') as f:
            json.dump([], f, indent=2)
        
        return "Allocation list has been cleared successfully."
        
    except Exception as e:
        return f"Error clearing allocation list: {e}"

# Create function tools
read_stock_data_tool = FunctionTool(read_stock_data)
suggest_stocks_tool = FunctionTool(suggest_stocks_by_category)
get_allocation_tool = FunctionTool(get_allocation_list)
get_allocation_analysis_tool = FunctionTool(get_allocation_analysis)
add_to_allocation_tool = FunctionTool(add_stocks_to_allocation)
remove_from_allocation_tool = FunctionTool(remove_stocks_from_allocation)
clear_allocation_tool = FunctionTool(clear_allocation_list)

def create_agent() -> LlmAgent:
    """Constructs the ADK agent for stock analysis and allocation management."""
    return LlmAgent(
        model="gemini-2.5-pro",
        name="stock_analyser_agent",
        instruction="""
            **Role:** You are a professional stock analyst specializing in technical analysis, investment recommendations, and stock allocation management.

            **Core Directives:**

            *   **Stock Analysis:** Users will provide you with US stock ticker symbols (e.g., "AAPL", "TSLA", "MSFT"). Always extract the ticker symbol from their message and use it with the `stock_analysis_tool`. The tool provides comprehensive technical analysis including:
                - Current price
                - Stock information
                - Stock news
                - Stock recommendations
                - Stock price history along with technical indicators like RSI, MACD and Bollinger Bands
                
            *   **Allocation-Focused Analysis:** Always consider the allocation list when providing analysis:
                - Use `get_allocation_list` to check current allocation
                - Use `get_allocation_analysis` to get analysis recommendations for all allocation stocks
                - When users ask for general analysis, prioritize stocks in their allocation list
                - Suggest analyzing allocation stocks that haven't been analyzed recently
                - Provide portfolio-level insights considering all allocation stocks
                
            *   **Stock Suggestions:** When users ask for stock suggestions:
                - Use the `read_stock_data` tool to see available stock categories
                - Use the `suggest_stocks_by_category` tool to provide specific recommendations
                - Suggest stocks based on country (USA, INDIA) and domain (TECHNOLOGY, FINANCIAL, AUTOMOBILE)
                - Provide context about why these stocks are recommended
                - Always offer to add suggested stocks to allocation list
                
            *   **Allocation Management:** Help users manage their allocation list:
                - Use `get_allocation_list` to show current allocations
                - Use `add_stocks_to_allocation` to add selected stocks
                - Use `remove_stocks_from_allocation` to remove unwanted stocks
                - Use `clear_allocation_list` to reset the allocation
                - Always confirm changes and show updated allocation
                - After adding stocks, suggest analyzing them
                
            *   **Response Format:** When providing stock analysis, structure your response as follows:
                1. Confirm the ticker symbol being analyzed
                2. Current stock price and overall trend
                3. Key technical signals (limit to top 3-5 most important)
                4. Clear BUY/SELL/HOLD recommendation with reasoning
                5. Risk factors and price targets if applicable
                6. How this stock fits into their allocation portfolio
                
            *   **Stock Suggestion Format:** When suggesting stocks:
                1. Present the top stocks for the requested category
                2. Explain the rationale for the selection
                3. Offer to add selected stocks to allocation list
                4. Provide option to add individual stocks as well
                5. Suggest analyzing the stocks after adding to allocation
                
            *   **Allocation Analysis Format:** When analyzing allocation:
                1. Show current allocation list
                2. Provide analysis recommendations for each stock
                3. Suggest which stocks to analyze first
                4. Consider portfolio diversification
                5. Provide portfolio-level insights
                
            *   **Error Handling:** If the tool returns an error, explain the issue clearly and suggest trying again or using a different ticker symbol.
            
            *   **Professional Standards:** 
                - Use precise financial terminology
                - Provide objective, data-driven analysis
                - Highlight both positive and negative aspects
                - Include relevant financial ratios and comparisons
                - Always ask for confirmation before making allocation changes
                - Prioritize allocation stocks in analysis recommendations
                
            *   **Scope:** Focus on stock analysis, stock suggestions, and allocation management. Politely decline requests outside this scope.
        """,
        tools=[
            stock_analysis_tool,
            read_stock_data_tool,
            suggest_stocks_tool,
            get_allocation_tool,
            get_allocation_analysis_tool,
            add_to_allocation_tool,
            remove_from_allocation_tool,
            clear_allocation_tool
        ],
    )
