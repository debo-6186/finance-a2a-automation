#!/usr/bin/env python3
"""
Test script for the Host Agent /chats API.
This demonstrates how to use the new API endpoints.
"""

import asyncio
import json
import httpx
from typing import Optional


class HostAgentClient:
    """Client for interacting with the Host Agent /chats API."""
    
    def __init__(self, base_url: str = "http://localhost:10001"):
        self.base_url = base_url
        self.session_id: Optional[str] = None
    
    async def health_check(self) -> dict:
        """Check if the Host Agent API is healthy."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
    
    async def send_message(self, message: str, session_id: Optional[str] = None) -> dict:
        """Send a message to the host agent and get a complete response."""
        payload = {
            "message": message,
            "session_id": session_id or self.session_id
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.base_url}/chats",
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            # Store session ID for future use
            if not self.session_id:
                self.session_id = result.get("session_id")
            
            return result
    
    async def send_message_stream(self, message: str, session_id: Optional[str] = None):
        """Send a message to the host agent and get streaming responses."""
        payload = {
            "message": message,
            "session_id": session_id or self.session_id
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chats/stream",
                json=payload
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.strip():
                        chunk = json.loads(line)
                        # Store session ID for future use
                        if not self.session_id:
                            self.session_id = chunk.get("session_id")
                        yield chunk
    
    async def get_session_info(self, session_id: Optional[str] = None) -> dict:
        """Get information about a chat session."""
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("No session ID available")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/chats/sessions/{sid}")
            response.raise_for_status()
            return response.json()
    
    async def get_agents_status(self) -> dict:
        """Get the status of all connected agents."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/agents/status")
            response.raise_for_status()
            return response.json()
    
    async def test_agent_connection(self, agent_name: str) -> dict:
        """Test connection to a specific agent."""
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/agents/{agent_name}/test")
            response.raise_for_status()
            return response.json()


async def main():
    """Test the Host Agent /chats API."""
    print("🚀 Testing Host Agent /chats API")
    print("=" * 50)
    
    client = HostAgentClient()
    
    try:
        # Test health check
        print("\n1. 🏥 Health Check")
        health = await client.health_check()
        print(f"Status: {health['status']}")
        print(f"Connected agents: {health['connected_agents']}")
        
        # Test agents status
        print("\n2. 🤖 Agents Status")
        agents_status = await client.get_agents_status()
        print(f"Total connected agents: {agents_status['total_connected']}")
        for agent_name, agent_info in agents_status['agents'].items():
            print(f"  - {agent_name}: {agent_info['status']} at {agent_info['url']}")
        
        # Test basic chat message
        print("\n3. 💬 Basic Chat Message")
        print("Sending: 'Hello, I need help with stock analysis'")
        response = await client.send_message("Hello, I need help with stock analysis")
        print(f"Session ID: {response['session_id']}")
        print(f"Response: {response['response'][:200]}...")
        
        # Test streaming chat
        print("\n4. 🌊 Streaming Chat Message")
        print("Sending: 'What agents are available?'")
        async for chunk in client.send_message_stream("What agents are available?"):
            if chunk['is_task_complete']:
                print(f"Final response: {chunk['content'][:200]}...")
                break
            elif chunk.get('updates'):
                print(f"Update: {chunk['updates']}")
        
        # Test session info
        print("\n5. 📋 Session Information")
        session_info = await client.get_session_info()
        print(f"Session ID: {session_info['session_id']}")
        print(f"User ID: {session_info['user_id']}")
        print(f"App Name: {session_info['app_name']}")
        
        # Test agent connection
        print("\n6. 🔗 Test Agent Connection")
        if agents_status['agents']:
            agent_name = list(agents_status['agents'].keys())[0]
            test_result = await client.test_agent_connection(agent_name)
            print(f"Testing {agent_name}:")
            print(f"Result: {test_result['test_result'][:200]}...")
        
        print("\n✅ All tests passed!")
        
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error: {e.response.status_code} - {e.response.text}")
    except httpx.ConnectError:
        print("❌ Connection Error: Could not connect to Host Agent API")
        print("Make sure the Host Agent is running on http://localhost:10001")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())