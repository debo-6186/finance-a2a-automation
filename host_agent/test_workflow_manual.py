#!/usr/bin/env python3
"""
Manual/Interactive test for the stock allocation workflow.
Run this to manually test the complete flow step by step.
"""

import asyncio
import httpx
import json


async def send_message(message: str, session_id: str = None) -> dict:
    """Send a message to the host agent."""
    payload = {
        "message": message,
        "session_id": session_id,
        "user_id": "test_user_manual",  # Test user ID
        "paid_user": True  # Set as paid user for testing
    }

    # Use a simple dev token for authentication
    headers = {
        "Authorization": "Bearer test_token_for_development_testing"
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            "http://localhost:10001/api/chats",  # Correct endpoint
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()


async def main():
    """Interactive test."""
    print("\n" + "="*70)
    print("🧪 MANUAL WORKFLOW TEST")
    print("="*70)
    print("\nThis script will walk you through the complete workflow step by step.")
    print("Press Enter after each step to continue...\n")

    session_id = None

    # Step 1: Initial greeting
    input("Step 1: Press Enter to send initial greeting...")
    print("\n📨 Sending: 'Hello, I want to allocate my portfolio'")
    result = await send_message("Hello, I want to allocate my portfolio", session_id)
    session_id = result.get("session_id")
    print(f"✅ Session ID: {session_id}")
    print(f"📩 Response:\n{result.get('response')}\n")

    # Step 2: Portfolio upload note
    input("\nStep 2: Press Enter to continue (Portfolio upload happens separately)...")
    print("\n📋 Note: In production, portfolio PDF would be uploaded here.")
    print("For testing, ensure a portfolio has been uploaded for this session.\n")

    # Step 3: Investment amount
    input("\nStep 3: Press Enter to provide investment amount...")
    print("\n📨 Sending: 'I want to invest $50000'")
    result = await send_message("I want to invest $50000", session_id)
    print(f"📩 Response:\n{result.get('response')}\n")

    # Check if agent is asking for the same thing again
    if "how much" in result.get('response', '').lower() and "invest" in result.get('response', '').lower():
        print("⚠️  WARNING: Agent is asking for investment amount again!")
    else:
        print("✅ Good: Agent moved to next step")

    # Step 4: Investment strategy
    input("\nStep 4: Press Enter to provide investment strategy...")
    strategy = "I'm a long-term investor looking for stable growth over 5-10 years with focus on technology and healthcare sectors"
    print(f"\n📨 Sending: '{strategy}'")
    result = await send_message(strategy, session_id)
    print(f"📩 Response:\n{result.get('response')}\n")

    # Check if agent is asking for investment strategy again
    if "type of investor" in result.get('response', '').lower() or "investment strategy" in result.get('response', '').lower():
        print("⚠️  WARNING: Agent is asking for investment strategy again!")
    else:
        print("✅ Good: Agent moved to next step")

    # Step 5: Additional stocks
    input("\nStep 5: Press Enter to select additional stocks...")
    print("\n📨 Sending: 'Yes, I want to add AAPL and MSFT'")
    result = await send_message("Yes, I want to add AAPL and MSFT", session_id)
    print(f"📩 Response:\n{result.get('response')}\n")

    # Step 6: Email address
    input("\nStep 6: Press Enter to provide email address...")
    print("\n📨 Sending: 'My email is test@example.com'")
    result = await send_message("My email is test@example.com", session_id)
    print(f"📩 Response:\n{result.get('response')}\n")

    # Check if session ended
    response_lower = result.get('response', '').lower()
    if "stock analysis in progress" in response_lower or "email you" in response_lower:
        print("✅ SUCCESS: Email triggered stock analysis!")
        print("✅ Session should end here")
    else:
        print("⚠️  WARNING: Email did not trigger stock analysis")
        print("Expected response about 'stock analysis in progress'")

    # Summary
    print("\n" + "="*70)
    print("📊 TEST SUMMARY")
    print("="*70)
    print("\nThings to verify:")
    print("1. ✓ Agent should NOT ask for investment amount twice")
    print("2. ✓ Agent should NOT ask for investment strategy twice")
    print("3. ✓ After providing email, session should end with analysis message")
    print("\nCheck the logs for:")
    print("  - Look for: 'User's investment strategy stored: I'm a long-term investor...'")
    print("  - NOT: 'User's investment strategy stored: keep_pattern'")
    print("  - Look for: 'All prerequisites met: True'")
    print("  - Look for: 'Sending analysis request to Stock Analyser Agent'")
    print("\nLog file: host_agent.log")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.ConnectError:
        print("\n❌ ERROR: Could not connect to Host Agent")
        print("Make sure the Host Agent is running:")
        print("  cd host_agent")
        print("  uv run --active .")
    except KeyboardInterrupt:
        print("\n\n👋 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
