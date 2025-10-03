import asyncio
import logging
import time
from collections.abc import AsyncGenerator

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

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class StockReportAnalyserAgentExecutor(AgentExecutor):
    """An AgentExecutor that runs Stock Report Analyser's ADK-based Agent."""

    def __init__(self, runner: Runner):
        self.runner = runner
        self._running_sessions = {}

    def _run_agent(
        self, session_id, new_message: types.Content
    ) -> AsyncGenerator[Event, None]:
        return self.runner.run_async(
            session_id=session_id, user_id="stock_report_analyser_agent", new_message=new_message
        )

    async def _run_agent_with_retry(
        self, session_id: str, new_message: types.Content, max_retries: int = 3
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
                
                async for event in self._run_agent(session_id, new_message):
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
                    'connection error', 'network error'
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
                    parts = convert_genai_parts_to_a2a(
                        event.content.parts if event.content and event.content.parts else []
                    )
                    logger.debug("Yielding final response: %s", parts)
                    await task_updater.add_artifact(parts)
                    await task_updater.complete()
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
            except Exception as cleanup_error:
                logger.warning(f"Error during cleanup after failure: {cleanup_error}")
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

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        try:
            if not context.current_task:
                await updater.submit()
            await updater.start_work()
            await self._process_request(
                types.UserContent(
                    parts=convert_a2a_parts_to_genai(context.message.parts),
                ),
                context.context_id,
                updater,
            )
        except Exception as e:
            logger.error(f"Error in execute method: {e}")
            # Try to update task status to failed, but don't fail if cleanup fails
            try:
                await updater.update_status(
                    TaskState.failed,
                    message=updater.new_agent_message(
                        [TextPart(text=f"Error during execution: {str(e)}")]
                    ),
                )
                await updater.complete()
            except Exception as cleanup_error:
                logger.warning(f"Error during cleanup in execute: {cleanup_error}")
            # Re-raise the original error
            raise

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        raise ServerError(error=UnsupportedOperationError())

    async def _upsert_session(self, session_id: str):
        session = await self.runner.session_service.get_session(
            app_name=self.runner.app_name, user_id="stock_report_analyser_agent", session_id=session_id
        )
        if session is None:
            session = await self.runner.session_service.create_session(
                app_name=self.runner.app_name,
                user_id="stock_report_analyser_agent",
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
            # Only pass supported parameters - exclude display_name and other unsupported fields
            return types.Part(
                file_data=types.FileData(
                    file_uri=root.file.uri, 
                    mime_type=root.file.mimeType
                    # Note: display_name is intentionally excluded as it's not supported by Gemini API
                )
            )
        if isinstance(root.file, FileWithBytes):
            # Handle file bytes data properly - decode if it's already bytes, encode if it's string
            file_data = root.file.bytes
            if isinstance(file_data, str):
                # If it's a string, encode it to bytes
                file_data = file_data.encode("utf-8")
            elif isinstance(file_data, bytes):
                # If it's already bytes, use it as is
                pass
            else:
                # For other types, try to convert to string first then encode
                file_data = str(file_data).encode("utf-8")
            
            # Only pass supported parameters - exclude display_name and other unsupported fields
            return types.Part(
                inline_data=types.Blob(
                    data=file_data,
                    mime_type=root.file.mimeType or "application/octet-stream",
                    # Note: display_name is intentionally excluded as it's not supported by Gemini API
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
        
        # Handle inline data properly - decode to string if it's bytes
        inline_data = part.inline_data.data
        if isinstance(inline_data, bytes):
            try:
                inline_data = inline_data.decode("utf-8")
            except UnicodeDecodeError:
                # If it's not valid UTF-8, convert to base64 string
                import base64
                inline_data = base64.b64encode(inline_data).decode("utf-8")
        
        return Part(
            root=FilePart(
                file=FileWithBytes(
                    bytes=inline_data,
                    mimeType=part.inline_data.mime_type,
                )
            )
        )
    raise ValueError(f"Unsupported part type: {part}")
