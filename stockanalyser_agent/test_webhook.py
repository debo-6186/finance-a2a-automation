#!/usr/bin/env python3
"""
Test script to verify the webhook function works correctly.
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_webhook_function():
    """Test the webhook function with sample data."""
    try:
        from agent import send_analysis_to_webhook
        
        print("✅ Import successful")
        
        # Test data
        test_analysis = "Sample stock analysis: AAPL - Buy recommendation with 85% confidence"
        
        print(f"📤 Testing webhook function with data: {test_analysis[:50]}...")
        
        # Test the function
        result = send_analysis_to_webhook(test_analysis)
        
        print(f"📋 Result: {result}")
        
        if result.startswith("Success:"):
            print("🎉 Webhook test successful!")
            return True
        elif result.startswith("Error:"):
            print("❌ Webhook test failed with error")
            return False
        else:
            print("⚠️ Webhook test completed with warning")
            return True
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing webhook: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_environment():
    """Check if required environment variables are set."""
    print("🔍 Checking environment variables...")
    
    required_vars = ["ACTIVEPIECES_USERNAME", "ACTIVEPIECES_PASSWORD"]
    missing_vars = []
    
    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var}: Set")
        else:
            print(f"❌ {var}: Not set")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n⚠️ Missing environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file or environment")
        return False
    
    print("✅ All required environment variables are set")
    return True

if __name__ == "__main__":
    print("Testing webhook functionality...")
    
    # Check environment first
    env_ok = check_environment()
    
    if env_ok:
        # Test the webhook function
        success = test_webhook_function()
        sys.exit(0 if success else 1)
    else:
        print("\n❌ Environment not properly configured. Please fix and try again.")
        sys.exit(1)
