from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import fitz  # PyMuPDF
import io
import os
import re

def read_portfolio_statement() -> str:
    """
    Reads text from the local 'portfolio_statement.pdf' file and returns the text content.
    Use this tool to get the content of the stock portfolio for analysis.
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
    Extracts and identifies all stock tickers from the portfolio text.
    This tool helps identify all stocks mentioned in the portfolio for analysis.
    
    Args:
        portfolio_text: The text content from the portfolio statement
        
    Returns:
        A formatted string with all identified stock tickers
    """
    try:
        print(f"Starting stock ticker extraction from {len(portfolio_text)} characters of text")
        
        # Common patterns for stock tickers (1-5 letters, often in caps)
        ticker_patterns = [
            r'\b[A-Z]{1,5}\b',  # 1-5 letter tickers in caps
            r'\b[A-Z]{1,5}\.[A-Z]{1,2}\b',  # Tickers with dots (e.g., BRK.A)
            r'\b[A-Z]{1,5}-[A-Z]{1,2}\b',  # Tickers with hyphens
            r'\b[A-Z]{1,5}\s+',  # Tickers followed by space
            r'\s+[A-Z]{1,5}\b',  # Tickers preceded by space
        ]
        
        found_tickers = set()
        all_matches = []
        
        # Extract tickers using patterns
        for pattern in ticker_patterns:
            matches = re.findall(pattern, portfolio_text)
            all_matches.extend(matches)
            for match in matches:
                # Clean the match
                clean_match = re.sub(r'[^\w]', '', match.upper())
                if clean_match:
                    # Filter out common words that might match the pattern
                    common_words = {
                        'THE', 'AND', 'FOR', 'WITH', 'FROM', 'THIS', 'THAT', 'HAVE', 'WILL', 'YOUR', 
                        'PORTFOLIO', 'STOCK', 'SHARES', 'TOTAL', 'VALUE', 'PRICE', 'DATE', 'TIME', 
                        'PAGE', 'REPORT', 'STATEMENT', 'ANALYSIS', 'INVESTMENT', 'FUND', 'ETF', 
                        'MUTUAL', 'BOND', 'CASH', 'USD', 'DOL', 'PER', 'ALL', 'NEW', 'OLD', 'BIG', 
                        'SMALL', 'HIGH', 'LOW', 'GOOD', 'BAD', 'YES', 'NO', 'ONE', 'TWO', 'THREE', 
                        'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'TEN', 'INC', 'CORP', 
                        'LTD', 'LLC', 'CO', 'COMPANY', 'SHARE', 'SHARES', 'STOCK', 'STOCKS',
                        'HOLDINGS', 'HOLDING', 'POSITION', 'POSITIONS', 'ACCOUNT', 'ACCOUNTS',
                        'BALANCE', 'BALANCES', 'AMOUNT', 'AMOUNTS', 'QUANTITY', 'QUANTITIES',
                        'NUMBER', 'NUMBERS', 'COUNT', 'COUNTS', 'EACH', 'EVERY', 'SOME', 'MANY',
                        'FEW', 'SEVERAL', 'MULTIPLE', 'SINGLE', 'DOUBLE', 'TRIPLE', 'QUAD',
                        'FIRST', 'SECOND', 'THIRD', 'FOURTH', 'FIFTH', 'SIXTH', 'SEVENTH',
                        'EIGHTH', 'NINTH', 'TENTH', 'LAST', 'NEXT', 'PREVIOUS', 'CURRENT',
                        'FORMER', 'LATTER', 'EARLY', 'LATE', 'SOON', 'LATER', 'AGAIN',
                        'ALSO', 'TOO', 'ASWELL', 'BESIDES', 'MOREOVER', 'FURTHERMORE',
                        'ADDITIONALLY', 'FURTHER', 'BESIDES', 'EXCEPT', 'UNLESS', 'UNTIL',
                        'SINCE', 'BEFORE', 'AFTER', 'DURING', 'WHILE', 'WHEN', 'WHERE',
                        'WHY', 'HOW', 'WHAT', 'WHICH', 'WHO', 'WHOSE', 'WHOM', 'THERE',
                        'HERE', 'THERE', 'WHERE', 'EVERYWHERE', 'NOWHERE', 'SOMEWHERE',
                        'ANYWHERE', 'INSIDE', 'OUTSIDE', 'ABOVE', 'BELOW', 'UNDER', 'OVER',
                        'BETWEEN', 'AMONG', 'AMONGST', 'BENEATH', 'BEHIND', 'BEFORE',
                        'AFTER', 'DURING', 'SINCE', 'UNTIL', 'WHILE', 'ALTHOUGH', 'THOUGH',
                        'UNLESS', 'EXCEPT', 'BESIDES', 'BEYOND', 'WITHIN', 'WITHOUT',
                        'AGAINST', 'TOWARD', 'TOWARDS', 'UPON', 'ABOUT', 'AROUND', 'ACROSS',
                        'THROUGH', 'THROUGHOUT', 'ALONG', 'ALONGSIDE', 'NEAR', 'NEARBY',
                        'FAR', 'AWAY', 'CLOSE', 'DISTANT', 'REMOTE', 'LOCAL', 'GLOBAL',
                        'WORLDWIDE', 'INTERNATIONAL', 'NATIONAL', 'REGIONAL', 'LOCAL',
                        'PRIVATE', 'PUBLIC', 'COMMON', 'SPECIAL', 'UNIQUE', 'RARE',
                        'USUAL', 'NORMAL', 'STANDARD', 'TYPICAL', 'AVERAGE', 'MEDIUM',
                        'LARGE', 'SMALL', 'BIG', 'LITTLE', 'HUGE', 'TINY', 'MASSIVE',
                        'MINI', 'MICRO', 'MACRO', 'MEGA', 'GIGA', 'TERA', 'PETA',
                        'EXA', 'ZETTA', 'YOTTA', 'KILO', 'MILLI', 'MICRO', 'NANO',
                        'PICO', 'FEMTO', 'ATTO', 'ZEPTO', 'YOCTO', 'CENTI', 'DECI',
                        'DECA', 'HECTO', 'MEGA', 'GIGA', 'TERA', 'PETA', 'EXA',
                        'ZETTA', 'YOTTA', 'KILO', 'MILLI', 'MICRO', 'NANO', 'PICO',
                        'FEMTO', 'ATTO', 'ZEPTO', 'YOCTO', 'CENTI', 'DECI', 'DECA',
                        'HECTO', 'MEGA', 'GIGA', 'TERA', 'PETA', 'EXA', 'ZETTA',
                        'YOTTA', 'KILO', 'MILLI', 'MICRO', 'NANO', 'PICO', 'FEMTO',
                        'ATTO', 'ZEPTO', 'YOCTO', 'CENTI', 'DECI', 'DECA', 'HECTO'
                    }
                    if clean_match not in common_words and len(clean_match) >= 1:
                        found_tickers.add(clean_match)
        
        print(f"Found {len(found_tickers)} potential tickers using regex patterns")
        
        # Also look for specific stock names that might be mentioned
        stock_keywords = ['stock', 'shares', 'ticker', 'symbol', 'company', 'holding', 'position']
        lines = portfolio_text.split('\n')
        for line_num, line in enumerate(lines):
            line_upper = line.upper()
            for keyword in stock_keywords:
                if keyword in line_upper:
                    print(f"Found stock keyword '{keyword}' in line {line_num + 1}: {line[:100]}...")
                    # Look for potential tickers in this line
                    words = line.split()
                    for word in words:
                        word_clean = re.sub(r'[^\w]', '', word.upper())
                        if len(word_clean) >= 1 and len(word_clean) <= 5 and word_clean not in common_words:
                            found_tickers.add(word_clean)
                            print(f"  Added ticker: {word_clean}")
        
        # Look for patterns like "X shares of Y" or "Y (Company Name)"
        share_patterns = [
            r'(\d+)\s+shares?\s+of\s+([A-Z]{1,5})',
            r'([A-Z]{1,5})\s*\([^)]+\)',
            r'([A-Z]{1,5})\s+Inc\.',
            r'([A-Z]{1,5})\s+Corp\.',
            r'([A-Z]{1,5})\s+Ltd\.',
            r'([A-Z]{1,5})\s+LLC',
        ]
        
        for pattern in share_patterns:
            matches = re.findall(pattern, portfolio_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    for item in match:
                        if len(item) >= 1 and len(item) <= 5 and item.isalpha():
                            found_tickers.add(item.upper())
                elif isinstance(match, str) and len(match) >= 1 and len(match) <= 5 and match.isalpha():
                    found_tickers.add(match.upper())
        
        print(f"After share pattern matching, found {len(found_tickers)} tickers")
        
        if not found_tickers:
            print("No stock tickers found. Here's a sample of the text:")
            print(portfolio_text[:500] + "..." if len(portfolio_text) > 500 else portfolio_text)
            return "No stock tickers found in the portfolio text. Please check if the portfolio statement contains stock symbols."
        
        # Sort tickers for better readability
        sorted_tickers = sorted(list(found_tickers))
        
        print(f"Final tickers found: {sorted_tickers}")
        
        result = f"**Stock Tickers Found in Portfolio:**\n\n"
        result += f"Total stocks identified: {len(sorted_tickers)}\n\n"
        result += "**Individual Stocks:**\n"
        for i, ticker in enumerate(sorted_tickers, 1):
            result += f"{i}. {ticker}\n"
        
        result += f"\n**Analysis Recommendation:**\n"
        result += f"These {len(sorted_tickers)} stocks should be analyzed for:\n"
        result += f"- Current performance and trends\n"
        result += f"- Risk assessment\n"
        result += f"- Portfolio diversification analysis\n"
        result += f"- Investment recommendations\n"
        
        return result
        
    except Exception as e:
        print(f"Error in extract_stock_tickers_from_portfolio: {e}")
        return f"Error extracting stock tickers: {e}"

read_portfolio_tool = FunctionTool(read_portfolio_statement)
extract_tickers_tool = FunctionTool(extract_stock_tickers_from_portfolio)

def create_agent() -> LlmAgent:
    """Constructs the ADK agent for stock report analysis."""
    return LlmAgent(
        model="gemini-2.5-pro",
        name="stock_report_analyser_agent",
        instruction="""
            **Role:** You are a professional financial analyst specializing in analyzing stock reports and portfolio statements.

            **Core Directives:**

            *   **Portfolio Analysis:** To analyze the user's stock portfolio, you MUST use the `read_portfolio_statement` tool to read and process the portfolio statement. Then use the `extract_stock_tickers_from_portfolio` tool to identify ALL stocks in the portfolio. Focus on:
                - Identifying ALL stock tickers in the portfolio
                - Key financial metrics and performance indicators
                - Revenue and profit trends
                - Management commentary and guidance
                - Risk factors and competitive positioning
                - Comparison with previous periods and industry benchmarks
                
            *   **Stock Identification:** 
                - Use the `extract_stock_tickers_from_portfolio` tool to systematically identify ALL stocks in the portfolio
                - Ensure no stocks are missed in the analysis
                - Provide a complete list of all identified stocks
                - Analyze each identified stock thoroughly
                
            *   **Response Format:** When analyzing reports, structure your response as follows:
                1. **Portfolio Summary**: Complete list of all stocks found in the portfolio
                2. **Executive Summary** of key findings
                3. **Financial Performance Analysis** (revenue, profit, margins)
                4. **Key Highlights and Concerns**
                5. **Management Outlook and Guidance**
                6. **Investment Implications and Recommendations**
                7. **Portfolio Diversification Analysis**
                
            *   **Analysis Depth:** Provide thorough analysis including:
                - Complete identification of all portfolio stocks
                - Quantitative metrics analysis for each stock
                - Qualitative assessment of business performance
                - Industry context and competitive positioning
                - Forward-looking insights based on the report data
                - Portfolio-level analysis and recommendations
                
            *   **Professional Standards:** 
                - Use precise financial terminology
                - Provide objective, data-driven analysis
                - Highlight both positive and negative aspects
                - Include relevant financial ratios and comparisons
                - Ensure comprehensive coverage of ALL stocks in the portfolio
                
            *   **Scope:** Focus on comprehensive portfolio analysis and investment research based on the provided portfolio statement. Ensure ALL stocks are identified and analyzed.
        """,
        tools=[read_portfolio_tool, extract_tickers_tool],
    )
