from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import fitz  # PyMuPDF
import io
import os
import re
from google import genai
from google.genai.types import GenerateContentConfig

def read_portfolio_statement() -> str:
    """
    Reads portfolio statement PDF and returns text content.
    """
    try:
        # Construct an absolute path to the PDF file
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        pdf_path = os.path.join(agent_dir, "portfolio_statement.pdf")
        
        print(f"Attempting to read PDF from: {pdf_path}")
        
        if not os.path.exists(pdf_path):
            return f"Error: portfolio_statement.pdf not found at {pdf_path}"
        
        with open(pdf_path, "rb") as f:
            file_bytes = f.read()
        
        print(f"Successfully read {len(file_bytes)} bytes from PDF")
        
    except FileNotFoundError:
        return f"Error: portfolio_statement.pdf not found. Looked in: {os.path.abspath(os.path.join(os.path.dirname(__file__)))}"
    except Exception as e:
        return f"Error reading PDF file: {e}"
    
    try:
        print("Opening PDF with PyMuPDF...")
        pdf_document = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        print(f"PDF opened successfully. Number of pages: {len(pdf_document)}")
        
        text = ""
        for page_num in range(len(pdf_document)):
            print(f"Processing page {page_num + 1}/{len(pdf_document)}")
            page = pdf_document.load_page(page_num)
            page_text = page.get_text()
            text += page_text
            print(f"Page {page_num + 1} text length: {len(page_text)} characters")
        
        print(f"Total text extracted: {len(text)} characters")
        return text
        
    except Exception as e:
        return f"Error processing PDF: {e}"

def extract_stock_tickers_from_portfolio(portfolio_text: str) -> str:
    """
    Extracts stock tickers from portfolio text.
    
    Args:
        portfolio_text: The portfolio statement text
        
    Returns:
        List of stock tickers found
    """
    try:
        print(f"Starting LLM-based stock ticker extraction from {len(portfolio_text)} characters of text")
        
        # Create the client with proper configuration
        # Check if we should use Vertex AI or API key
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            client = genai.Client(vertexai=True)
            print("Using Vertex AI for ticker extraction")
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                print("No GOOGLE_API_KEY found for ticker extraction")
                return "**Error**: Google API key not configured for ticker extraction. Please set GOOGLE_API_KEY environment variable."
            client = genai.Client(api_key=api_key)
            print("Using Google AI API for ticker extraction")
        
        # System prompt for stock ticker extraction
        system_prompt = """You are an expert financial analyst specializing in analyzing portfolio statements and identifying stock ticker symbols.

Your task is to carefully analyze portfolio text and extract ALL stock ticker symbols mentioned.

Rules for extraction:
1. Extract only valid stock ticker symbols (typically 1-5 characters, letters only)
2. Look for company names and convert them to their ticker symbols (e.g., "Apple Inc." → "AAPL")
3. Include both individual stocks and ETFs 
4. Convert all tickers to uppercase
5. Remove duplicates
6. Do NOT include common words, currency codes, or non-stock identifiers
7. Include tickers that appear in any context within the portfolio (holdings, transactions, etc.)

Common patterns to look for:
- Direct ticker mentions: "AAPL", "GOOGL", "TSLA"
- Company names: "Apple Inc.", "Microsoft Corporation", "Tesla Inc."
- ETF names: "Vanguard S&P 500 ETF" → "VOO"
- Holdings tables with ticker columns
- Transaction records

Respond with ONLY a comma-separated list of ticker symbols in this format:
AAPL,GOOGL,MSFT,TSLA,VOO

If no tickers are found, respond with: NONE"""

        # User prompt with the portfolio text
        user_prompt = f"""Analyze this portfolio statement text and extract ALL stock ticker symbols:

{portfolio_text}

Provide only the comma-separated ticker list as specified."""

        # Generate ticker extraction using LLM
        print("Generating ticker extraction using LLM...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=GenerateContentConfig(
                system_instruction=[system_prompt]
            )
        )
        print("Received LLM response for ticker extraction")
        
        found_tickers = []
        
        if response and response.text:
            # Parse the LLM response
            response_text = response.text.strip()
            print(f"LLM ticker extraction response: {response_text}")
            
            # Parse the response
            if response_text.upper() != "NONE":
                # Split by commas and clean up
                ticker_list = response_text.split(',')
                for ticker in ticker_list:
                    ticker = ticker.strip().upper()
                    # Validate ticker format (1-5 characters, letters only)
                    if ticker and len(ticker) >= 1 and len(ticker) <= 5 and ticker.isalpha():
                        found_tickers.append(ticker)
                
                # Remove duplicates while preserving order
                found_tickers = list(dict.fromkeys(found_tickers))
        else:
            print("No response from LLM for ticker extraction")
            return "**Error**: Could not extract tickers using LLM. Please try again."
        
        if not found_tickers:
            print("No stock tickers found by LLM")
            return "No stock tickers found in the portfolio text. Please check if the portfolio statement contains stock symbols."
        
        print(f"LLM found {len(found_tickers)} tickers: {found_tickers}")
        
        # Format the result
        result = f"**Stock Tickers Found in Portfolio:**\n\n"
        result += f"Total stocks identified: {len(found_tickers)}\n\n"
        result += "**Individual Stocks:**\n"
        for i, ticker in enumerate(found_tickers, 1):
            result += f"{i}. {ticker}\n"
        
        result += f"\n**Analysis Recommendation:**\n"
        result += f"These {len(found_tickers)} stocks should be analyzed for:\n"
        result += f"- Current performance and trends\n"
        result += f"- Risk assessment\n"
        result += f"- Portfolio diversification analysis\n"
        result += f"- Investment recommendations\n"
        
        return result
        
    except Exception as e:
        print(f"Error in extract_stock_tickers_from_portfolio: {e}")
        return f"Error extracting stock tickers: {e}"


def handle_portfolio_analysis_error() -> str:
    """
    Provides guidance when portfolio analysis encounters errors.
    
    Returns:
        Error handling instructions
    """
    return """
    **PORTFOLIO ANALYSIS ERROR GUIDANCE**
    
    **If you get malformed function call errors:**
    
    1. **Correct Function Calls:**
       ✅ read_portfolio_statement()
       ✅ extract_stock_tickers_from_portfolio(portfolio_text="[text content]")
    
    2. **Simple Workflow:**
       - Step 1: Call read_portfolio_statement() first
       - Step 2: Use the text result in extract_stock_tickers_from_portfolio()
       - Step 3: Analyze the results
    
    3. **Parameter Rules:**
       - read_portfolio_statement() takes NO parameters
       - extract_stock_tickers_from_portfolio() takes portfolio_text as a string
       - Always use quotes around string parameters
    
    **Recovery Steps:**
    1. Call read_portfolio_statement() to get portfolio text
    2. Call extract_stock_tickers_from_portfolio(portfolio_text="[paste the text here]")
    3. Provide analysis based on the extracted tickers
    """


read_portfolio_statement_tool = FunctionTool(read_portfolio_statement)
extract_stock_tickers_from_portfolio_tool = FunctionTool(extract_stock_tickers_from_portfolio)
handle_portfolio_analysis_error_tool = FunctionTool(handle_portfolio_analysis_error)

def create_agent() -> LlmAgent:
    """Constructs the ADK agent for stock report analysis."""
    return LlmAgent(
        model="gemini-2.5-flash",
        name="stock_report_analyser_agent",
        instruction="""
            **Role:** Analyze portfolio statements and extract stock information.

            **Workflow:**
            
            1. Call: read_portfolio_statement()
            2. Call: extract_stock_tickers_from_portfolio(portfolio_text="[result from step 1]")
            3. Analyze and provide recommendations
            
            **Function Call Rules:**
            - read_portfolio_statement() - NO parameters
            - extract_stock_tickers_from_portfolio(portfolio_text="text") - ONE string parameter
            - Use exact parameter names with quotes
            - If errors occur, use handle_portfolio_analysis_error()
        """,
        tools=[read_portfolio_statement_tool, extract_stock_tickers_from_portfolio_tool, handle_portfolio_analysis_error_tool],
    )
