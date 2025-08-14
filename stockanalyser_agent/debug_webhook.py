#!/usr/bin/env python3
"""
Debug script to test webhook function and compare with working curl command.
"""
import os
import sys
import base64
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_webhook_debug():
    """Test webhook function with detailed debugging."""
    
    # Test data
    analysis_response = "Test response from Python script"
    webhook_url = "https://cloud.activepieces.com/api/v1/webhooks/BzkDtbfmZODV2C3jotH94"
    
    # Get credentials from environment
    username = os.getenv("ACTIVEPIECES_USERNAME")
    password = os.getenv("ACTIVEPIECES_PASSWORD")
    
    print("🔍 Debugging webhook function...")
    print(f"URL: {webhook_url}")
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password) if password else 'None'}")
    
    if not username or not password:
        print("❌ Missing credentials in environment variables")
        return False
    
    # Create payload exactly like your working curl
    payload = {
        "analysis_response": analysis_response,
        "email_to": "dev.061086@gmail.com"
    }
    
    # Create basic auth header exactly like your curl
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json"
    }
    
    print(f"\n📤 Payload: {json.dumps(payload, indent=2)}")
    print(f"🔑 Auth Header: Basic {encoded_credentials[:20]}...")
    print(f"📋 Headers: {json.dumps({k: v for k, v in headers.items() if k != 'Authorization'}, indent=2)}")
    
    try:
        print(f"\n🚀 Making POST request...")
        
        # Make the request
        response = requests.post(
            webhook_url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"✅ Request completed")
        print(f"📊 Status Code: {response.status_code}")
        print(f"📋 Response Headers: {dict(response.headers)}")
        print(f"📄 Response Text: {response.text[:500]}")
        
        if response.status_code == 200:
            print("🎉 SUCCESS! Webhook call worked!")
            return True
        else:
            print(f"❌ FAILED! Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def compare_with_curl():
    """Show the equivalent curl command."""
    print("\n" + "="*60)
    print("🔗 EQUIVALENT CURL COMMAND:")
    print("="*60)
    
    username = os.getenv("ACTIVEPIECES_USERNAME")
    password = os.getenv("ACTIVEPIECES_PASSWORD")
    
    if username and password:
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        curl_cmd = f"""curl --location '{webhook_url}' \\
--header 'Content-Type: application/json' \\
--header 'Authorization: Basic {encoded_credentials}' \\
--data-raw '{{
    "analysis_response": "Test response from Python script",
    "email_to": "dev.061086@gmail.com"
}}'"""
        
        print(curl_cmd)
    else:
        print("❌ Cannot generate curl command - missing credentials")

if __name__ == "__main__":
    print("🐍 Python Webhook Debug Script")
    print("="*40)
    
    # Test the webhook function
    success = test_webhook_debug()
    
    # Show equivalent curl command
    compare_with_curl()
    
    if success:
        print("\n🎉 Debug completed successfully!")
    else:
        print("\n❌ Debug found issues!")
    
    sys.exit(0 if success else 1)
