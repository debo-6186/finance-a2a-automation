from dotenv.main import logger
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
import fitz  # PyMuPDF
import io
import os
import re
import sys
from google import genai
from google.genai.types import GenerateContentConfig

# Add the host_agent directory to the path to import database functions
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "host_agent"))

try:
    from database import get_db, mark_portfolio_statement_uploaded
except ImportError as e:
    print(f"Warning: Could not import database functions: {e}")
    print("Portfolio upload status will not be tracked in the database")


def read_portfolio_statement(session_id: str = "") -> str:
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
        
        # Mark portfolio statement as uploaded in the database if session_id is provided
        if session_id and text:
            try:
                db = next(get_db())
                success = mark_portfolio_statement_uploaded(db, session_id)
                if success:
                    print(f"Successfully marked portfolio statement as uploaded for session {session_id}")
                else:
                    print(f"Failed to mark portfolio statement as uploaded for session {session_id}")
            except Exception as e:
                print(f"Error updating database for session {session_id}: {e}")
        
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
8. Calculate and include percentage allocation for each ticker based on portfolio value

Common patterns to look for:
- Direct ticker mentions: "AAPL", "GOOGL", "TSLA"
- Company names: "Apple Inc.", "Microsoft Corporation", "Tesla Inc."
- ETF names: "Vanguard S&P 500 ETF" → "VOO"
- Holdings tables with ticker columns
- Transaction records
- Position values and total portfolio value for percentage calculations

Respond with ONLY ticker symbols and their percentage allocations in this format:
AAPL (3.02%), GOOGL (9.66%), MSFT (3.95%), TSLA (0.61%), VOO (37.14%)

If no tickers are found, respond with: NONE"""

        # User prompt with the portfolio text
        user_prompt = f"""Analyze this portfolio statement text and extract ALL stock ticker symbols:

{portfolio_text}

Provide only the comma-separated ticker list as specified."""

        # Generate ticker extraction using LLM with retry logic
        print("Generating ticker extraction using LLM...")
        max_retries = 3
        base_delay = 2.0
        response = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    import random
                    import time
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"Retrying ticker extraction after {delay:.2f}s delay (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=user_prompt,
                    config=GenerateContentConfig(
                        system_instruction=[system_prompt]
                    )
                )

                # If we get here, the call was successful
                print(f"Successfully generated ticker extraction (attempt {attempt + 1})")
                break

            except Exception as e:
                error_message = str(e)
                is_api_error = any(code in error_message for code in ["500", "503", "INTERNAL", "UNAVAILABLE"])

                if attempt == max_retries - 1:
                    # Last attempt failed, re-raise the exception
                    print(f"Failed to generate ticker extraction after {max_retries} attempts: {e}")
                    raise

                if is_api_error:
                    print(f"Google AI API error on attempt {attempt + 1}: {e}")
                else:
                    print(f"Non-API error on attempt {attempt + 1}: {e}")
                    # For non-API errors, fail immediately
                    raise
        
        found_tickers = []
        allocation_percentage = ""
        
        if response and response.text:
            # Parse the LLM response
            response_text = response.text.strip()
            print(f"LLM ticker extraction response: {response_text}")
            
            # Store the raw LLM response for allocation percentage
            allocation_percentage = response_text
            
            # Parse the response
            if response_text.upper() != "NONE":
                # Split by commas and clean up
                ticker_list = response_text.split(',')
                for ticker_entry in ticker_list:
                    ticker_entry = ticker_entry.strip()
                    # Extract ticker symbol (before the parentheses if present)
                    if '(' in ticker_entry:
                        ticker = ticker_entry.split('(')[0].strip().upper()
                    else:
                        ticker = ticker_entry.strip().upper()
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
        
        result += f"\n**Allocation Percentage:**\n"
        result += f"{allocation_percentage}\n"
        
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
       ✅ read_portfolio_statement(session_id="session_id")
       ✅ extract_stock_tickers_from_portfolio(portfolio_text="[text content]")
    
    2. **Simple Workflow:**
       - Step 1: Call read_portfolio_statement(session_id="session_id") first
       - Step 2: Use the text result in extract_stock_tickers_from_portfolio()
       - Step 3: Analyze the results
    
    3. **Parameter Rules:**
       - read_portfolio_statement() takes one optional string parameter: session_id
       - extract_stock_tickers_from_portfolio() takes portfolio_text as a string
       - Always use quotes around string parameters
    
    **Recovery Steps:**
    1. Call read_portfolio_statement(session_id="session_id") to get portfolio text
    2. Call extract_stock_tickers_from_portfolio(portfolio_text="[paste the text here]")
    3. Provide analysis based on the extracted tickers
    """


read_portfolio_statement_tool = FunctionTool(read_portfolio_statement)
extract_stock_tickers_from_portfolio_tool = FunctionTool(extract_stock_tickers_from_portfolio)
handle_portfolio_analysis_error_tool = FunctionTool(handle_portfolio_analysis_error)

def create_agent() -> Agent:
    """Constructs the ADK agent for stock report analysis."""
    return Agent(
        model="gemini-2.5-flash",
        name="stock_report_analyser_agent",
        instruction="""
            **Role:** Analyze portfolio statements and extract stock information.

            **Session ID Extraction:**
            - Look for "Session ID: " followed by the actual session ID in the user message
            - Extract this session ID to pass to the read_portfolio_statement function
            - If no session ID is found in the message, use empty string

            **Workflow:**
            
            1. Extract session ID from user message (look for "Session ID: [id]")
            2. Call: read_portfolio_statement(session_id="extracted_session_id")
            3. Call: extract_stock_tickers_from_portfolio(portfolio_text="[result from step 2]")
            4. Analyze and provide recommendations
            
            **Function Call Rules:**
            - read_portfolio_statement(session_id="session_id") - ONE optional string parameter
            - extract_stock_tickers_from_portfolio(portfolio_text="text") - ONE string parameter
            - Use exact parameter names with quotes
            - If errors occur, use handle_portfolio_analysis_error()
        """,
        tools=[read_portfolio_statement_tool, extract_stock_tickers_from_portfolio_tool, handle_portfolio_analysis_error_tool],
    )
