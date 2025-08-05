from typing import Callable
import asyncio
import time

import httpx
from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from dotenv import load_dotenv
import logging

load_dotenv()

# Set up logger for this module
logger = logging.getLogger("host_agent.remote_agent_connection")
logger.setLevel(logging.INFO)

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(self, agent_card: AgentCard, agent_url: str):
        logger.info(f"agent_card: {agent_card}")
        logger.info(f"agent_url: {agent_url}")
        # Increased timeout and added retry configuration
        self._httpx_client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=60.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        self.agent_client = A2AClient(self._httpx_client, agent_card, url=agent_url)
        self.card = agent_card
        self.agent_url = agent_url  # Store the URL for later access
        self.conversation_name = None
        self.conversation = None
        self.pending_tasks = set()

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message_with_retry(
        self, message_request: SendMessageRequest, max_retries: int = 3
    ) -> SendMessageResponse:
        """
        Sends a message with retry logic for handling timeouts and connection errors.
        
        Args:
            message_request: The message request to send
            max_retries: Maximum number of retry attempts (default: 3)
        
        Returns:
            SendMessageResponse from the agent
            
        Raises:
            Exception: If all retry attempts fail
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):  # +1 for the initial attempt
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries + 1} to send message to {self.card.name}")
                
                response = await self.agent_client.send_message(message_request)
                logger.info(f"Successfully sent message to {self.card.name} on attempt {attempt + 1}")
                return response
                
            except httpx.ReadTimeout as e:
                last_exception = e
                logger.warning(f"ReadTimeout on attempt {attempt + 1} for {self.card.name}: {e}")
                
                if attempt < max_retries:
                    wait_time = (2 ** attempt) * 5  # Exponential backoff: 5s, 10s, 20s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries + 1} attempts failed for {self.card.name}. Last error: {e}")
                    raise last_exception
                    
            except httpx.ConnectTimeout as e:
                last_exception = e
                logger.warning(f"ConnectTimeout on attempt {attempt + 1} for {self.card.name}: {e}")
                
                if attempt < max_retries:
                    wait_time = (2 ** attempt) * 3  # Exponential backoff: 3s, 6s, 12s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries + 1} attempts failed for {self.card.name}. Last error: {e}")
                    raise last_exception
                    
            except httpx.RequestError as e:
                last_exception = e
                logger.warning(f"RequestError on attempt {attempt + 1} for {self.card.name}: {e}")
                
                if attempt < max_retries:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries + 1} attempts failed for {self.card.name}. Last error: {e}")
                    raise last_exception
                    
            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error on attempt {attempt + 1} for {self.card.name}: {e}")
                
                if attempt < max_retries:
                    wait_time = (2 ** attempt) * 1  # Exponential backoff: 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries + 1} attempts failed for {self.card.name}. Last error: {e}")
                    raise last_exception

    async def send_message(
        self, message_request: SendMessageRequest
    ) -> SendMessageResponse:
        """Legacy method for backward compatibility. Uses retry logic."""
        return await self.send_message_with_retry(message_request)
