#!/usr/bin/env python3
"""
Test script to verify the MCP agent can be created and the MCP tool is properly configured.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_mcp_agent_creation():
    """Test that the MCP agent can be created without errors."""
    try:
        from agent import create_agent
        print("✅ Import successful")
        
        agent = create_agent()
        print("✅ Agent created successfully")
        print(f"✅ Agent name: {agent.name}")
        print(f"✅ Agent model: {agent.model}")
        print(f"✅ Number of tools: {len(agent.tools)}")
        
        # Check each tool
        for i, tool in enumerate(agent.tools):
            tool_type = type(tool).__name__
            print(f"✅ Tool {i+1}: {tool_type}")
            
            if tool_type == "MCPToolset":
                print(f"   - MCP Tool found and configured")
                print(f"   - Connection params: {tool.connection_params}")
            elif tool_type == "FunctionTool":
                print(f"   - Function Tool: {tool.name if hasattr(tool, 'name') else 'Unnamed'}")
        
        print("\n🎉 MCP Agent test passed! The agent is ready to use.")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error creating agent: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing MCP agent creation...")
    success = test_mcp_agent_creation()
    sys.exit(0 if success else 1)
