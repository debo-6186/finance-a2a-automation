from typing import Any
import logging
import re
import os
from reportanalyser_agent.agent import StockReportAnalyserAgent
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
import re

logger = get_logger(__name__)

class ReportAnalyserAgentExecutor(AgentExecutor):
    """Executor for StockReportAnalyserAgent that processes PDF stock reports."""

    def __init__(self):
        super().__init__()
        logger.info("Initializing ReportAnalyserAgentExecutor.")
        self.agent = StockReportAnalyserAgent()

    @override
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        # Expecting PDF file as input (either bytes or file path)
        pdf_data = context.get_user_input()  # Should be a dict with 'filename' key or a string containing a filename
        logger.info(f"execute called with pdf_data: {pdf_data}")
        filename = None
        if isinstance(pdf_data, dict) and 'filename' in pdf_data:
            filename_str = pdf_data['filename']
            match = re.search(r"([\w\-. ]+\.pdf)", filename_str)
            if match:
                filename = match.group(1).strip()
                logger.info(f"Extracted filename from input dict: {filename}")
            else:
                logger.error("No valid filename found in input dict's 'filename' value.")
                return
        elif isinstance(pdf_data, str):
            match = re.search(r"([\w\-. ]+\.pdf)", pdf_data)
            if match:
                filename = match.group(1).strip()
                logger.info(f"Extracted filename from input string: {filename}")
            else:
                logger.error("No valid filename found in input string.")
                return
        else:
            logger.error("Input must be a dict with a 'filename' key or a string containing a filename.")
            return
        
        if isinstance(filename, str) and not os.path.isabs(filename):
            # Get the directory where agent.py or agentexecutor.py resides
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filename = os.path.join(script_dir, filename)
            
        task = context.current_task

        if not context.message:
            raise Exception("No message provided")

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        # Run the agent's analysis (no streaming, just one result)
        result = await self.agent.analyze_pdf(filename, getattr(task, 'contextId', None))
        if result["is_task_complete"]:
            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    append=False,
                    contextId=task.contextId,
                    taskId=task.id,
                    lastChunk=True,
                    artifact=new_text_artifact(
                        name="current_result",
                        description="Result of PDF stock report analysis.",
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
