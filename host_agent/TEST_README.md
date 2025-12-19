# Workflow Testing Guide

This directory contains comprehensive tests for the stock allocation workflow.

## Test Files

### 1. `test_workflow.py` - Automated Workflow Test
Runs the complete workflow automatically and validates:
- ✅ Agent doesn't repeat questions
- ✅ Full investment strategy is stored (not simplified to "keep_pattern")
- ✅ Email triggers stock analyser agent

**Usage:**
```bash
cd host_agent
python test_workflow.py
```

**What it tests:**
1. Sends a series of messages simulating the complete user flow
2. Checks conversation history for repeated questions
3. Parses logs to verify investment strategy storage
4. Verifies that email triggers the stock analyser agent

### 2. `test_workflow_manual.py` - Interactive Manual Test
Step-by-step interactive test where you press Enter to advance through each step.

**Usage:**
```bash
cd host_agent
python test_workflow_manual.py
```

**What it does:**
1. Guides you through each step of the workflow
2. Shows you the agent's responses at each step
3. Highlights potential issues (e.g., repeated questions)
4. Provides guidance on what to check in logs

### 3. `test_chats_api.py` - API Endpoint Test
Tests the basic API functionality (health check, chat, streaming).

**Usage:**
```bash
cd host_agent
python test_chats_api.py
```

## Prerequisites

Before running tests:

1. **Start the Host Agent:**
   ```bash
   cd host_agent
   uv run --active .
   ```
   The agent should be running on `http://localhost:10001`

2. **Start the Stock Analyser Agent:**
   ```bash
   cd stockanalyser_agent
   uv run --active .
   ```
   The agent should be running on `http://localhost:10002`

3. **Ensure database is configured:**
   - PostgreSQL should be running
   - Database schema should be created
   - Connection string in environment variables

## Expected Flow

The complete workflow should follow these steps:

1. **Initial Greeting**
   - User: "Hello, I want to allocate my portfolio"
   - Agent: Asks for portfolio upload

2. **Portfolio Upload** (handled separately via upload endpoint)
   - Upload PDF via the upload endpoint
   - Agent analyzes portfolio and shows stocks

3. **Investment Amount**
   - User: "I want to invest $50000"
   - Agent: Asks for investment strategy
   - ⚠️ Should NOT ask for amount again

4. **Investment Strategy**
   - User: "I'm a long-term investor looking for stable growth..."
   - Agent: Asks about additional stocks
   - ✅ Should store the FULL strategy text, not "keep_pattern"
   - ⚠️ Should NOT ask for strategy again

5. **Additional Stocks**
   - User: "Yes, I want to add AAPL and MSFT"
   - Agent: Asks for email address

6. **Email Address (Final Step)**
   - User: "My email is test@example.com"
   - Agent: Returns "Stock analysis in progress, we will email you..."
   - ✅ Should trigger stock analyser agent in background
   - ✅ Session should END

## Validation Points

### 1. No Repeated Questions ✅
**Check:** Agent should ask each question only ONCE
- Investment amount: asked once
- Investment strategy: asked once
- Email address: asked once

**How to verify:**
- Run `test_workflow.py` - it will check conversation history
- Or run `test_workflow_manual.py` and watch for repeated questions

### 2. Full Investment Strategy Stored ✅
**Check:** The complete investment strategy should be stored, not simplified

**Bad (old behavior):**
```
User's investment strategy stored: keep_pattern
```

**Good (new behavior):**
```
User's investment strategy stored: I'm a long-term investor looking for stable growth over 5-10 years...
```

**How to verify:**
```bash
# Check the log file
tail -100 host_agent.log | grep "investment strategy stored"
```

### 3. Email Triggers Stock Analyser ✅
**Check:** When email is provided, stock analyser should be triggered

**Look for in logs:**
```
========== PREREQUISITES CHECK ==========
Investment amount: $50000.0 (valid: True)
Existing stocks count: X
New stocks count: Y
Has stocks: True
Diversification preference: 'I'm a long-term investor...' (valid: True)
Portfolio uploaded (from DB): True for session XXX
All prerequisites met: True
Sending analysis request to Stock Analyser Agent
```

**How to verify:**
```bash
# Check the log file
tail -100 host_agent.log | grep -A 10 "PREREQUISITES CHECK"
```

## Common Issues

### Issue 1: Connection Error
```
❌ Connection Error: Could not connect to Host Agent API
```

**Solution:**
- Make sure Host Agent is running: `cd host_agent && uv run --active .`
- Check if port 10001 is available: `lsof -i :10001`

### Issue 2: Agent Repeats Questions
```
❌ FAIL: Questions were repeated!
   investment_amount: asked 2 times
```

**Solution:**
- This was the original bug - check that you have the latest code
- Verify the fixes in `host_agent/host/agent.py`:
  - Line 225-229: "ONLY IF investment_amount is NOT set"
  - Line 231-241: "ONLY IF diversification_preference is NOT set"

### Issue 3: Investment Strategy Simplified
```
❌ FAIL: Investment strategy was simplified to 'keep_pattern'
```

**Solution:**
- Check `store_diversification_preference` function (line 689-698)
- Should store the full text, not convert to "keep_pattern"

### Issue 4: Email Doesn't Trigger Analysis
```
❌ FAIL: Stock analyser agent was NOT triggered
```

**Solution:**
- Check if all prerequisites are met in logs
- Verify Stock Analyser Agent is running on port 10002
- Check `store_receiver_email_id` function (line 700-793)

## Running All Tests

To run all tests in sequence:

```bash
cd host_agent

# 1. Test basic API functionality
echo "Testing API endpoints..."
python test_chats_api.py

# 2. Run automated workflow test
echo "Testing complete workflow..."
python test_workflow.py

# 3. (Optional) Run manual interactive test
echo "Running manual test..."
python test_workflow_manual.py
```

## Interpreting Results

### ✅ All Tests Pass
```
✅ PASS: No repeated questions
✅ PASS: Full investment strategy stored
✅ PASS: Email triggered stock analyser

📊 Overall: 3 passed, 0 failed
🎉 ALL TESTS PASSED!
```

### ❌ Some Tests Fail
```
❌ FAIL: Questions were repeated!
   investment_amount: asked 2 times
✅ PASS: Full investment strategy stored
⚠️  SKIP: Email triggered stock analyser (check logs manually)

📊 Overall: 1 passed, 1 failed
❌ 1 TEST(S) FAILED - Please review the issues above
```

When tests fail:
1. Check the detailed output for which specific test failed
2. Review the relevant section in the code
3. Check `host_agent.log` for detailed logs
4. Verify all agents are running

## Logs

Main log file: `host_agent/host_agent.log`

Useful log searches:
```bash
# Check investment strategy storage
grep "investment strategy stored" host_agent.log

# Check prerequisites check
grep -A 10 "PREREQUISITES CHECK" host_agent.log

# Check stock analyser trigger
grep "Sending analysis request to Stock Analyser" host_agent.log

# Check for errors
grep "ERROR" host_agent.log

# See recent activity
tail -100 host_agent.log
```

## Contributing

When adding new features to the workflow:
1. Update the test scripts to cover new steps
2. Add validation for new functionality
3. Update this README with new test cases
4. Ensure all existing tests still pass
