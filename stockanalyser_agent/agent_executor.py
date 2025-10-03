import asyncio
import time
from collections.abc import AsyncGenerator
from logger import setup_logging, get_logger

# Ensure logging is set up
setup_logging()

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    FilePart,
    FileWithBytes,
    FileWithUri,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils.errors import ServerError
from google.adk import Runner
from google.adk.events import Event
from google.genai import types

logger = get_logger(__name__)
logger.info("StockAnalyserAgentExecutor initialized with centralized logging")


class StockAnalyserAgentExecutor(AgentExecutor):
    """An AgentExecutor that runs Stock Analyser's ADK-based Agent."""

    def __init__(self, runner: Runner):
        self.runner = runner
        self._running_sessions = {}

    def _run_agent(
        self, session_id, new_message: types.Content
    ) -> AsyncGenerator[Event, None]:
        return self.runner.run_async(
            session_id=session_id, user_id="stock_analyser_agent", new_message=new_message
        )

    async def _run_agent_with_retry(
        self, session_id: str, new_message: types.Content, max_retries: int = 1
    ) -> AsyncGenerator[Event, None]:
        """
        Runs the agent with retry logic for handling rate limits and other errors.
        
        Args:
            session_id: The session ID
            new_message: The message to process
            max_retries: Maximum number of retry attempts (default: 3)
        
        Yields:
            Events from the agent execution
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):  # +1 for the initial attempt
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries + 1} for session {session_id}")
                
                event_count = 0
                async for event in self._run_agent(session_id, new_message):
                    event_count += 1
                    if event_count % 10 == 0:  # Log every 10th event to track progress
                        logger.debug(f"Processed {event_count} events for session {session_id}")
                    yield event
                
                # If we reach here, the execution was successful
                logger.info(f"Successfully completed execution for session {session_id} on attempt {attempt + 1}")
                return
                
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()
                
                # Check if this is a retryable error
                is_retryable = any(keyword in error_msg for keyword in [
                    'rate limit', 'quota exceeded', 'too many requests', 
                    'service unavailable', 'internal server error', 'timeout',
                    'connection error', 'network error', 'cancel scope',
                    'mcp', 'generatorexit', 'runtime'
                ])
                
                if attempt < max_retries and is_retryable:
                    wait_time = (2 ** attempt) * 1  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"Attempt {attempt + 1} failed for session {session_id} with retryable error: {e}. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    if attempt >= max_retries:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for session {session_id}. "
                            f"Last error: {e}"
                        )
                    else:
                        logger.error(
                            f"Non-retryable error on attempt {attempt + 1} for session {session_id}: {e}"
                        )
                    raise last_exception

    async def _process_request(
        self,
        new_message: types.Content,
        session_id: str,
        task_updater: TaskUpdater,
    ) -> None:
        
        session_obj = await self._upsert_session(session_id)
        session_id = session_obj.id

        try:
            async for event in self._run_agent_with_retry(session_id, new_message):
                if event.is_final_response():
                    # Log raw event content for debugging
                    if event.content and event.content.parts:
                        logger.info(f"Raw event parts for session {session_id}: {len(event.content.parts)} parts")
                        for i, raw_part in enumerate(event.content.parts):
                            logger.info(f"Raw part {i+1}: text={bool(raw_part.text)}, file_data={bool(raw_part.file_data)}, inline_data={bool(raw_part.inline_data)}")
                            if raw_part.text:
                                logger.info(f"Raw part {i+1} text preview: {raw_part.text[:100]}...")

                    parts = convert_genai_parts_to_a2a(
                        event.content.parts if event.content and event.content.parts else []
                    )
                    logger.info(f"Final response received from agent for session {session_id}: {len(parts)} parts")

                    # If no parts were converted, create a default completion message
                    if not parts:
                        logger.warning(f"No parts converted for session {session_id}, creating default completion message")
                        parts = [Part(root=TextPart(text="Analysis completed successfully. Results have been saved to the system."))]

                    # Log the response content for debugging
                    for i, part in enumerate(parts):
                        if hasattr(part.root, 'text'):
                            logger.info(f"Response part {i+1}: {len(part.root.text)} characters")
                            logger.debug(f"Response part {i+1} preview: {part.root.text[:200]}...")

                    # Send the response back to the host agent through the task updater
                    try:
                        logger.info(f"About to call task_updater.add_artifact for session {session_id} with {len(parts)} parts")
                        await task_updater.add_artifact(parts)
                        logger.info(f"Successfully called task_updater.add_artifact for session {session_id}")

                        logger.info(f"About to call task_updater.complete() for session {session_id}")
                        await task_updater.complete()
                        logger.info(f"Successfully called task_updater.complete() for session {session_id}")
                    except Exception as task_error:
                        logger.error(f"Error completing task for session {session_id}: {task_error}")
                        logger.error(f"Task error type: {type(task_error)}")
                        logger.error(f"Task error details: {str(task_error)}")
                        # Don't raise the error as the analysis was successful, just log it
                    break
                if not event.get_function_calls():
                    logger.debug("Yielding update response")
                    await task_updater.update_status(
                        TaskState.working,
                        message=task_updater.new_agent_message(
                            convert_genai_parts_to_a2a(
                                event.content.parts
                                if event.content and event.content.parts
                                else []
                            ),
                        ),
                    )
                else:
                    logger.debug("Skipping event")
        except Exception as e:
            logger.error(f"Failed to process request for session {session_id} after all retries: {e}")
            # Update task status to indicate failure
            try:
                await task_updater.update_status(
                    TaskState.failed,
                    message=task_updater.new_agent_message(
                        [TextPart(text=f"Error: Failed to process request after multiple attempts. Error: {str(e)}")]
                    ),
                )
                await task_updater.complete()
                logger.info(f"Task marked as failed and completed for session {session_id}")
            except Exception as cleanup_error:
                logger.warning(f"Error during cleanup after failure for session {session_id}: {cleanup_error}")
                # Don't re-raise cleanup errors as they're not critical

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        if not context.task_id or not context.context_id:
            raise ValueError("RequestContext must have task_id and context_id")
        if not context.message:
            raise ValueError("RequestContext must have a message")

        logger.info(f"Execute: Initial context.task_id={context.task_id}, context.context_id={context.context_id}")
        logger.info(f"Execute: context.current_task={context.current_task}")

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        logger.info(f"Execute: Created TaskUpdater with task_id={context.task_id}")

        if not context.current_task:
            logger.info("Execute: No current_task, calling await updater.submit()")
            await updater.submit()
            logger.info("Execute: Called await updater.submit()")
        else:
            logger.info("Execute: current_task exists, skipping updater.submit()")

        logger.info("Execute: Calling await updater.start_work()")
        await updater.start_work()
        logger.info("Execute: Called await updater.start_work()")

        await self._process_request(
            types.UserContent(
                parts=convert_a2a_parts_to_genai(context.message.parts),
            ),
            context.context_id,
            updater,
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        raise ServerError(error=UnsupportedOperationError())

    async def _upsert_session(self, session_id: str):
        session = await self.runner.session_service.get_session(
            app_name=self.runner.app_name, user_id="stock_analyser_agent", session_id=session_id
        )
        if session is None:
            session = await self.runner.session_service.create_session(
                app_name=self.runner.app_name,
                user_id="stock_analyser_agent",
                session_id=session_id,
            )
        if session is None:
            raise RuntimeError(f"Failed to get or create session: {session_id}")
        return session


def convert_a2a_parts_to_genai(parts: list[Part]) -> list[types.Part]:
    """Convert a list of A2A Part types into a list of Google Gen AI Part types."""
    return [convert_a2a_part_to_genai(part) for part in parts]


def convert_a2a_part_to_genai(part: Part) -> types.Part:
    """Convert a single A2A Part type into a Google Gen AI Part type."""
    root = part.root
    if isinstance(root, TextPart):
        return types.Part(text=root.text)
    if isinstance(root, FilePart):
        if isinstance(root.file, FileWithUri):
            return types.Part(
                file_data=types.FileData(
                    file_uri=root.file.uri, mime_type=root.file.mimeType
                )
            )
        if isinstance(root.file, FileWithBytes):
            return types.Part(
                inline_data=types.Blob(
                    data=root.file.bytes.encode("utf-8"),
                    mime_type=root.file.mimeType or "application/octet-stream",
                )
            )
        raise ValueError(f"Unsupported file type: {type(root.file)}")
    raise ValueError(f"Unsupported part type: {type(part)}")


def convert_genai_parts_to_a2a(parts: list[types.Part]) -> list[Part]:
    """Convert a list of Google Gen AI Part types into a list of A2A Part types."""
    return [
        convert_genai_part_to_a2a(part)
        for part in parts
        if (part.text or part.file_data or part.inline_data)
    ]


def convert_genai_part_to_a2a(part: types.Part) -> Part:
    """Convert a single Google Gen AI Part type into an A2A Part type."""
    if part.text:
        return Part(root=TextPart(text=part.text))
    if part.file_data:
        if not part.file_data.file_uri:
            raise ValueError("File URI is missing")
        return Part(
            root=FilePart(
                file=FileWithUri(
                    uri=part.file_data.file_uri,
                    mimeType=part.file_data.mime_type,
                )
            )
        )
    if part.inline_data:
        if not part.inline_data.data:
            raise ValueError("Inline data is missing")
        return Part(
            root=FilePart(
                file=FileWithBytes(
                    bytes=part.inline_data.data.decode("utf-8"),
                    mimeType=part.inline_data.mime_type,
                )
            )
        )
    raise ValueError(f"Unsupported part type: {part}")
