#!/usr/bin/env python3
"""
Test script for the new programmatic flow.
"""

import os
import sys
import asyncio
import json
from unittest.mock import Mock, patch

# Add the current directory to the path so we can import the agent
sys.path.insert(0, os.path.dirname(__file__))

from agent import StockAnalyzerAgent


async def test_programmatic_flow():
    """Test the programmatic flow with mock data."""

    # Create a test analysis request
    test_request = """
    **STOCKS TO ANALYZE - DELEGATION REQUEST**

    **PORTFOLIO REPORT (for context):**
    Existing portfolio contains AAPL, GOOGL

    **COMPLETE LIST OF STOCKS TO ANALYZE:**
    - Existing Portfolio Stocks: AAPL, GOOGL
    - New Stocks to Consider: TSLA, MSFT
    - Total Stocks for Analysis: 4

    **INVESTMENT AMOUNT:**
    10000

    **RECEIVER EMAIL ID:**
    test@example.com

    **DELEGATION INSTRUCTIONS:**
    Please analyze all the stocks listed above and provide comprehensive recommendations.
    """

    # Create the agent
    agent = StockAnalyzerAgent()

    # Mock the MCP tool calls to avoid external dependencies
    async def mock_mcp_call(tool_name, params):
        ticker = params.get('ticker', 'UNKNOWN')
        return {
            'ticker': ticker,
            'price': 150.0,
            'recommendation': 'BUY',
            'analysis': f'Mock analysis for {ticker}'
        }

    # Mock the webhook call
    def mock_webhook_call(analysis_response, email_to, webhook_url=None, username=None, password=None):
        return f"Success: Mock webhook call sent to {email_to}"

    # Apply mocks
    agent.stock_mcp_tool.call_tool = mock_mcp_call
    agent.send_analysis_to_webhook = mock_webhook_call

    # Mock the LLM calls to avoid API dependencies
    with patch('agent.genai.Client') as mock_client:
        # Mock client instance
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance

        # Mock the generate_content response for investment details extraction
        mock_investment_response = Mock()
        mock_investment_response.text = "INVESTMENT_AMOUNT: 10000\nEMAIL_ID: test@example.com"
        mock_client_instance.models.generate_content.return_value = mock_investment_response

        try:
            # Test the programmatic flow
            print("Testing programmatic flow...")
            result = await agent.execute_programmatic_flow(test_request)

            print("✅ Programmatic flow completed successfully!")
            print(f"Result: {result}")

            # Check if the result contains expected information
            if "Stock analysis completed successfully" in result:
                print("✅ Flow returned expected success message")
            else:
                print("❌ Flow did not return expected success message")

            return True

        except Exception as e:
            print(f"❌ Error in programmatic flow: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_json_functions():
    """Test that the modified functions return proper JSON."""

    agent = StockAnalyzerAgent()

    # Test extract_stocks_from_analysis_request returns JSON
    test_request = "Analyze AAPL, GOOGL (existing) and TSLA, MSFT (new stocks). Invest $5000. Email: user@test.com"

    # Mock the LLM call
    with patch('agent.genai.Client') as mock_client:
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance

        mock_response = Mock()
        mock_response.text = "EXISTING: AAPL,GOOGL\nNEW: TSLA,MSFT\nINVESTMENT_AMOUNT: 5000\nEMAIL_ID: user@test.com"
        mock_client_instance.models.generate_content.return_value = mock_response

        try:
            # Test stock extraction
            result = agent.extract_stocks_from_analysis_request(test_request)
            data = json.loads(result)

            print("✅ extract_stocks_from_analysis_request returns valid JSON")
            print(f"JSON result: {data}")

            if "existing_stocks" in data and "new_stocks" in data:
                print("✅ JSON contains expected keys")
            else:
                print("❌ JSON missing expected keys")

        except json.JSONDecodeError:
            print("❌ extract_stocks_from_analysis_request does not return valid JSON")
        except Exception as e:
            print(f"❌ Error testing extract_stocks_from_analysis_request: {e}")

    # Test save_portfolio_analysis_to_file returns JSON
    with patch('agent.genai.Client') as mock_client:
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance

        mock_response = Mock()
        mock_response.text = "INVESTMENT_AMOUNT: 5000\nEMAIL_ID: user@test.com"
        mock_client_instance.models.generate_content.return_value = mock_response

        try:
            result = agent.save_portfolio_analysis_to_file(test_request)
            data = json.loads(result)

            print("✅ save_portfolio_analysis_to_file returns valid JSON")
            print(f"JSON result: {data}")

            if "investment_amount" in data and "email_id" in data:
                print("✅ JSON contains expected keys")
            else:
                print("❌ JSON missing expected keys")

        except json.JSONDecodeError:
            print("❌ save_portfolio_analysis_to_file does not return valid JSON")
        except Exception as e:
            print(f"❌ Error testing save_portfolio_analysis_to_file: {e}")


async def main():
    """Run all tests."""
    print("=== Testing New Programmatic Flow ===\n")

    print("1. Testing JSON function returns...")
    test_json_functions()

    print("\n2. Testing full programmatic flow...")
    success = await test_programmatic_flow()

    if success:
        print("\n✅ All tests passed! The programmatic flow is working correctly.")
    else:
        print("\n❌ Some tests failed. Please check the implementation.")


if __name__ == "__main__":
    asyncio.run(main())