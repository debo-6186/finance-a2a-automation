#!/usr/bin/env python3
"""
Simple script to check environment variables for webhook configuration.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_environment():
    """Check and display environment variables."""
    print("🔍 Environment Variables Check")
    print("="*40)
    
    # Check required variables
    username = os.getenv("ACTIVEPIECES_USERNAME")
    password = os.getenv("ACTIVEPIECES_PASSWORD")
    
    print(f"ACTIVEPIECES_USERNAME: {username}")
    print(f"ACTIVEPIECES_PASSWORD: {'*' * len(password) if password else 'None'}")
    
    # Check if .env file exists
    env_file = ".env"
    if os.path.exists(env_file):
        print(f"✅ .env file exists: {env_file}")
        
        # Read and show .env contents (without passwords)
        try:
            with open(env_file, 'r') as f:
                lines = f.readlines()
                print(f"\n📄 .env file contents:")
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if 'PASSWORD' in line:
                            # Hide password values
                            key, value = line.split('=', 1)
                            print(f"  {key}=***hidden***")
                        else:
                            print(f"  {line}")
        except Exception as e:
            print(f"❌ Error reading .env file: {e}")
    else:
        print(f"❌ .env file not found: {env_file}")
    
    # Check current working directory
    print(f"\n📁 Current working directory: {os.getcwd()}")
    
    # Check if we're in the right place
    if "stockanalyser_agent" in os.getcwd():
        print("✅ In stockanalyser_agent directory")
    else:
        print("⚠️ Not in stockanalyser_agent directory")
    
    # Summary
    print(f"\n📊 Summary:")
    if username and password:
        print("✅ Credentials are set")
        print(f"   Username length: {len(username)}")
        print(f"   Password length: {len(password)}")
    else:
        print("❌ Missing credentials")
        if not username:
            print("   - ACTIVEPIECES_USERNAME not set")
        if not password:
            print("   - ACTIVEPIECES_PASSWORD not set")

if __name__ == "__main__":
    check_environment()
