#!/usr/bin/env python3

"""
Test script for the investment details storage functionality in StockAnalyzerAgent.
"""

import os
import json
from stockanalyser_agent.agent import StockAnalyzerAgent

def test_investment_details_storage():
    """Test the save_investment_details_to_file functionality."""
    print("Testing investment details storage functionality...")
    
    # Create an instance of the StockAnalyzerAgent
    agent = StockAnalyzerAgent()
    
    # Set some test values
    agent.investment_amount = "10000$"
    agent.email_id = "test@example.com"
    
    print(f"Set investment_amount: {agent.investment_amount}")
    print(f"Set email_id: {agent.email_id}")
    
    # Test saving investment details
    result = agent.save_investment_details_to_file()
    print(f"Save result: {result}")
    
    # Verify the data was saved correctly
    if os.path.exists("stock_analysis_results.txt"):
        with open("stock_analysis_results.txt", 'r') as f:
            data = json.load(f)
        
        print("\nSaved data:")
        print(json.dumps(data, indent=2))
        
        # Check if INVESTMENT_DETAILS exists
        if "INVESTMENT_DETAILS" in data:
            investment_details = data["INVESTMENT_DETAILS"]
            print("\nInvestment details from file:")
            print(f"  investment_amount: {investment_details.get('investment_amount')}")
            print(f"  email_id: {investment_details.get('email_id')}")
            print(f"  timestamp: {investment_details.get('timestamp')}")
            
            # Verify the values match
            if (investment_details.get('investment_amount') == agent.investment_amount and 
                investment_details.get('email_id') == agent.email_id):
                print("\n✅ Test PASSED: Investment details saved correctly!")
            else:
                print("\n❌ Test FAILED: Investment details don't match!")
        else:
            print("\n❌ Test FAILED: INVESTMENT_DETAILS not found in JSON!")
    else:
        print("\n❌ Test FAILED: JSON file was not created!")

if __name__ == "__main__":
    test_investment_details_storage()