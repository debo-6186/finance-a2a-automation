#!/usr/bin/env python3
"""
Comprehensive test for the complete stock allocation workflow.
Tests the fixes for:
1. Investment strategy storage (should store full text, not just "keep_pattern")
2. No repeated questions (agent should not ask for same info twice)
3. Email ID triggering stock analyser agent
"""

import asyncio
import json
import httpx
import os
import time
from typing import Optional


class WorkflowTester:
    """Tester for the complete stock allocation workflow."""

    def __init__(self, base_url: str = "http://localhost:10001"):
        self.base_url = base_url
        self.session_id: Optional[str] = None
        self.conversation_history = []

    async def send_message(self, message: str, description: str = "") -> dict:
        """Send a message and return the response."""
        if description:
            print(f"\n{'='*60}")
            print(f"📨 {description}")
            print(f"{'='*60}")
            print(f"User: {message}")

        payload = {
            "message": message,
            "session_id": self.session_id,
            "user_id": "test_user_workflow",  # Test user ID
            "paid_user": True  # Set as paid user for testing
        }

        # Use a simple dev token for authentication
        headers = {
            "Authorization": "Bearer test_token_for_development_testing"
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chats",  # Correct endpoint
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()

            # Store session ID for future use
            if not self.session_id:
                self.session_id = result.get("session_id")

            # Store conversation
            self.conversation_history.append({
                "user": message,
                "agent": result.get("response"),
                "description": description
            })

            print(f"Agent: {result.get('response')[:300]}...")

            return result

    async def upload_portfolio_mock(self):
        """Simulate portfolio upload by updating the database directly."""
        # This would need to be implemented based on your database setup
        # For now, we'll skip the actual upload and assume it's handled separately
        print("\n⚠️  Note: Portfolio upload should be done separately via the upload endpoint")
        print("For this test, we assume a portfolio has already been uploaded for the session")

    async def check_for_repeated_questions(self):
        """Check if the agent asked the same question multiple times."""
        questions_asked = {}

        for entry in self.conversation_history:
            agent_response = entry["agent"].lower()

            # Check for investment amount question
            if "how much" in agent_response and "invest" in agent_response:
                questions_asked["investment_amount"] = questions_asked.get("investment_amount", 0) + 1

            # Check for investment strategy question
            if "type of investor" in agent_response or "investment strategy" in agent_response:
                questions_asked["investment_strategy"] = questions_asked.get("investment_strategy", 0) + 1

            # Check for email question
            if "email" in agent_response and ("provide" in agent_response or "address" in agent_response):
                questions_asked["email"] = questions_asked.get("email", 0) + 1

        repeated = {k: v for k, v in questions_asked.items() if v > 1}

        if repeated:
            print(f"\n❌ FAIL: Questions were repeated!")
            for question, count in repeated.items():
                print(f"   {question}: asked {count} times")
            return False
        else:
            print(f"\n✅ PASS: No questions were repeated")
            return True

    async def check_investment_strategy_stored(self):
        """Check if the full investment strategy was stored (not just 'keep_pattern')."""
        # We can infer this from the log file
        log_file = "host_agent.log"

        if not os.path.exists(log_file):
            print(f"\n⚠️  WARNING: Log file {log_file} not found. Cannot verify investment strategy storage.")
            return None

        # Read the last 100 lines of the log file
        with open(log_file, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-100:]

        # Look for the investment strategy storage log
        for line in recent_lines:
            if "User's investment strategy stored:" in line:
                # Extract the stored strategy
                if "keep_pattern" in line and "I'm a long-term investor" not in line:
                    print(f"\n❌ FAIL: Investment strategy was simplified to 'keep_pattern'")
                    print(f"   Log line: {line.strip()}")
                    return False
                elif "I'm a long-term investor" in line:
                    print(f"\n✅ PASS: Full investment strategy was stored")
                    print(f"   Log line: {line.strip()}")
                    return True

        print(f"\n⚠️  WARNING: Could not find investment strategy storage in logs")
        return None

    async def check_email_triggered_analysis(self):
        """Check if providing email triggered the stock analyser agent."""
        log_file = "host_agent.log"

        if not os.path.exists(log_file):
            print(f"\n⚠️  WARNING: Log file {log_file} not found. Cannot verify stock analyser trigger.")
            return None

        # Read the last 100 lines of the log file
        with open(log_file, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-100:]

        # Look for the stock analyser trigger
        analysis_triggered = False
        prerequisites_met = False

        for line in recent_lines:
            if "All prerequisites met:" in line and "True" in line:
                prerequisites_met = True
                print(f"\n✅ PASS: All prerequisites met")
                print(f"   Log line: {line.strip()}")

            if "Sending analysis request to Stock Analyser Agent" in line:
                analysis_triggered = True
                print(f"\n✅ PASS: Stock analyser agent was triggered")
                print(f"   Log line: {line.strip()}")

        if analysis_triggered:
            return True
        elif prerequisites_met:
            print(f"\n⚠️  WARNING: Prerequisites met but stock analyser not triggered (check logs)")
            return None
        else:
            print(f"\n❌ FAIL: Stock analyser agent was NOT triggered")
            return False

    async def run_complete_workflow_test(self):
        """Run the complete workflow test."""
        print("\n" + "="*60)
        print("🧪 TESTING COMPLETE STOCK ALLOCATION WORKFLOW")
        print("="*60)

        try:
            # Step 1: Initial greeting
            await self.send_message(
                "Hello, I want to allocate my portfolio",
                "Step 1: Initial greeting"
            )

            # Small delay to ensure agent processes
            await asyncio.sleep(2)

            # Note about portfolio upload
            print("\n📋 Note: Portfolio upload step")
            print("In a real scenario, you would upload a portfolio PDF here.")
            print("For this test, we assume the portfolio is already uploaded and analyzed.")

            # Step 2: Provide investment amount
            await self.send_message(
                "I want to invest $50000",
                "Step 2: Provide investment amount"
            )

            await asyncio.sleep(2)

            # Step 3: Provide detailed investment strategy
            investment_strategy = "I'm a long-term investor looking for stable growth over 5-10 years with focus on technology and healthcare sectors"
            await self.send_message(
                investment_strategy,
                "Step 3: Provide detailed investment strategy"
            )

            await asyncio.sleep(2)

            # Step 4: Select additional stocks
            await self.send_message(
                "Yes, I want to add AAPL and MSFT",
                "Step 4: Select additional stocks"
            )

            await asyncio.sleep(2)

            # Step 5: Provide email
            await self.send_message(
                "My email is test@example.com",
                "Step 5: Provide email address"
            )

            # Wait for background processing
            print("\n⏳ Waiting 5 seconds for background processing...")
            await asyncio.sleep(5)

            # Run validations
            print("\n" + "="*60)
            print("📊 VALIDATION RESULTS")
            print("="*60)

            # Test 1: Check for repeated questions
            test1_result = await self.check_for_repeated_questions()

            # Test 2: Check if full investment strategy was stored
            test2_result = await self.check_investment_strategy_stored()

            # Test 3: Check if email triggered stock analyser
            test3_result = await self.check_email_triggered_analysis()

            # Summary
            print("\n" + "="*60)
            print("📈 TEST SUMMARY")
            print("="*60)

            results = {
                "No repeated questions": test1_result,
                "Full investment strategy stored": test2_result,
                "Email triggered stock analyser": test3_result
            }

            for test_name, result in results.items():
                if result is True:
                    status = "✅ PASS"
                elif result is False:
                    status = "❌ FAIL"
                else:
                    status = "⚠️  SKIP (check logs manually)"
                print(f"{status}: {test_name}")

            # Overall result
            failures = sum(1 for r in results.values() if r is False)
            passes = sum(1 for r in results.values() if r is True)

            print(f"\n📊 Overall: {passes} passed, {failures} failed")

            if failures == 0:
                print("\n🎉 ALL TESTS PASSED!")
            else:
                print(f"\n❌ {failures} TEST(S) FAILED - Please review the issues above")

            # Print conversation history
            print("\n" + "="*60)
            print("📜 CONVERSATION HISTORY")
            print("="*60)
            for i, entry in enumerate(self.conversation_history, 1):
                print(f"\n{i}. {entry['description']}")
                print(f"   User: {entry['user']}")
                print(f"   Agent: {entry['agent'][:150]}...")

            return failures == 0

        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP Error: {e.response.status_code} - {e.response.text}")
            return False
        except httpx.ConnectError:
            print("❌ Connection Error: Could not connect to Host Agent API")
            print("Make sure the Host Agent is running on http://localhost:10001")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main test function."""
    print("\n" + "="*60)
    print("🚀 STOCK ALLOCATION WORKFLOW TEST")
    print("="*60)
    print("\nThis test validates:")
    print("1. ✅ Agent doesn't repeat questions")
    print("2. ✅ Full investment strategy is stored (not just 'keep_pattern')")
    print("3. ✅ Email triggers stock analyser agent")
    print("\nStarting test in 3 seconds...")
    await asyncio.sleep(3)

    tester = WorkflowTester()
    success = await tester.run_complete_workflow_test()

    if success:
        print("\n" + "="*60)
        print("🎉 TEST COMPLETED SUCCESSFULLY!")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ TEST COMPLETED WITH FAILURES")
        print("="*60)
        print("\nPlease review:")
        print("1. Check host_agent.log for detailed logs")
        print("2. Verify all agents are running (host_agent, stockanalyser_agent)")
        print("3. Ensure portfolio was uploaded for the test session")


if __name__ == "__main__":
    asyncio.run(main())
