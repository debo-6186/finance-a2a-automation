#!/usr/bin/env python3
"""
Test script to verify the updated /chats endpoint functionality.
This script tests both JSON and multipart form data requests.
"""

import requests
import json

# Test configuration
HOST = "localhost"
PORT = 10001
BASE_URL = f"http://{HOST}:{PORT}"

# Test Firebase token (should be replaced with a real token)
TEST_TOKEN = "test_firebase_token_123456"

# Test headers
headers_json = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TEST_TOKEN}"
}

headers_form = {
    "Authorization": f"Bearer {TEST_TOKEN}"
}

def test_json_request():
    """Test JSON request format."""
    print("Testing JSON request...")
    
    payload = {
        "message": "Hello, what is my portfolio performance?",
        "user_id": "user123",
        "paid_user": True,
        "session_id": "session456"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/chats",
            headers=headers_json,
            json=payload,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:200]}...")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Session ID: {data.get('session_id')}")
            print(f"Is Complete: {data.get('is_complete')}")
            print(f"Is File Uploaded: {data.get('is_file_uploaded')}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception during JSON test: {e}")
        return False

def test_form_request():
    """Test form data request format."""
    print("\nTesting form data request...")
    
    data = {
        "message": "Please analyze this portfolio statement",
        "user_id": "user123",
        "paid_user": "true",
        "session_id": "session456"
    }
    
    # Create a dummy PDF file for testing
    files = {
        "file": ("test_portfolio.pdf", b"dummy pdf content", "application/pdf")
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/chats",
            headers=headers_form,
            data=data,
            files=files,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:200]}...")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Session ID: {data.get('session_id')}")
            print(f"Is Complete: {data.get('is_complete')}")
            print(f"Is File Uploaded: {data.get('is_file_uploaded')}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception during form test: {e}")
        return False

def test_health_check():
    """Test health check endpoint."""
    print("\nTesting health check...")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        print(f"Health Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Connected Agents: {data.get('connected_agents')}")
            return True
        else:
            print(f"Health check failed: {response.text}")
            return False
    except Exception as e:
        print(f"Exception during health check: {e}")
        return False

def main():
    """Run all tests."""
    print("=== Testing Updated /chats Endpoint ===\n")
    
    # Test health check first
    health_ok = test_health_check()
    if not health_ok:
        print("Health check failed, server might not be running")
        return
    
    # Test JSON format
    json_ok = test_json_request()
    
    # Test form data format
    form_ok = test_form_request()
    
    print("\n=== Test Results ===")
    print(f"Health Check: {'PASS' if health_ok else 'FAIL'}")
    print(f"JSON Request: {'PASS' if json_ok else 'FAIL'}")
    print(f"Form Request: {'PASS' if form_ok else 'FAIL'}")
    
    if json_ok and form_ok:
        print("\n✅ All tests passed! The endpoint supports both formats correctly.")
    else:
        print("\n❌ Some tests failed. Check the server logs for details.")

if __name__ == "__main__":
    main()