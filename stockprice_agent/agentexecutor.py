from typing import Any
import logging
from stockprice_agent.agent import StockPriceAgent
from typing_extensions import override
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact
from logger import get_logger

logger = get_logger(__name__)

class StockPriceAgentExecutor(AgentExecutor):
    """Executor for StockPriceAgent that fetches real-time stock prices."""

    def __init__(self):
        super().__init__()
        logger.info("Initializing StockPriceAgentExecutor.")
        self.agent = StockPriceAgent()

    @override
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        # Expecting ticker symbol as input (string)
        user_input = context.get_user_input()
        logger.info(f"execute called with user_input: {user_input}")
        ticker = None
        if isinstance(user_input, dict) and 'ticker' in user_input:
            ticker = user_input['ticker']
        elif isinstance(user_input, str):
            ticker = user_input.strip().replace('"', '').upper()
        else:
            logger.error("Input must be a dict with a 'ticker' key or a string containing a ticker symbol.")
            return

        task = context.current_task
        if not context.message:
            raise Exception("No message provided")
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        # Run the agent's price fetch
        result = await self.agent.get_stock_price(ticker)
        if result["is_task_complete"]:
            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    append=False,
                    contextId=task.contextId,
                    taskId=task.id,
                    lastChunk=True,
                    artifact=new_text_artifact(
                        name="current_result",
                        description="Result of stock price lookup.",
                        text=result["content"],
                    ),
                )
            )
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(state=TaskState.completed),
                    final=True,
                    contextId=task.contextId,
                    taskId=task.id,
                )
            )
        elif result["require_user_input"]:
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.input_required,
                        message=new_agent_text_message(
                            result["content"],
                            task.contextId,
                            task.id,
                        ),
                    ),
                    final=True,
                    contextId=task.contextId,
                    taskId=task.id,
                )
            )
        else:
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.working,
                        message=new_agent_text_message(
                            result["content"],
                            task.contextId,
                            task.id,
                        ),
                    ),
                    final=False,
                    contextId=task.contextId,
                    taskId=task.id,
                )
            )

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception("cancel not supported")
