import json
import uuid
from typing import List, Any
import httpx
import asyncio
import os

from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from host_agent.remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback
from a2a.client import A2ACardResolver
from a2a.types import (
    SendMessageResponse,
    SendMessageRequest,
    MessageSendParams,
    SendMessageSuccessResponse,
    Task,
    Part,
    AgentCard,
)
from dotenv import load_dotenv

load_dotenv()

def convert_part(part: Part, tool_context: ToolContext):
    if part.type == "text":
        return part.text
    return f"Unknown type: {part.type}"

def convert_parts(parts: list[Part], tool_context: ToolContext):
    return [convert_part(p, tool_context) for p in parts]

def create_send_message_payload(
    text: str, task_id: str | None = None, context_id: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": text}],
            "messageId": uuid.uuid4().hex,
        },
    }
    if task_id:
        payload["message"]["taskId"] = task_id
    if context_id:
        payload["message"]["contextId"] = context_id
    return payload

class HostAgent:
    """The Host agent for orchestrating stock/finance analysis tasks."""
    def __init__(self, task_callback: TaskUpdateCallback | None = None):
        self.task_callback = task_callback
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ""

    async def _async_init_components(self, remote_agent_addresses: List[str]):
        async with httpx.AsyncClient(timeout=30) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, address)
                try:
                    card = await card_resolver.get_agent_card()
                    remote_connection = RemoteAgentConnections(
                        agent_card=card, agent_url=address
                    )
                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card
                except httpx.ConnectError as e:
                    print(f"ERROR: Failed to get agent card from {address}: {e}")
                except Exception as e:
                    print(f"ERROR: Failed to initialize connection for {address}: {e}")
        agent_info = []
        for agent_detail_dict in self.list_remote_agents():
            agent_info.append(json.dumps(agent_detail_dict))
        self.agents = "\n".join(agent_info)

    @classmethod
    async def create(
        cls,
        remote_agent_addresses: List[str],
        task_callback: TaskUpdateCallback | None = None,
    ):
        instance = cls(task_callback)
        await instance._async_init_components(remote_agent_addresses)
        return instance

    def create_agent(self) -> Agent:
        return Agent(
            model="gemini-2.5-flash-preview-04-17",
            name="HostAgent",
            instruction=self.root_instruction,
            before_model_callback=self.before_model_callback,
            description=(
                "This Host agent orchestrates the decomposition and delegation of user requests for stock or financial report analysis."
            ),
            tools=[self.send_message],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        current_agent = self.check_active_agent(context)
        return f"""
        **Role:** You are an expert Host Delegator. Your primary function is to accurately delegate user inquiries regarding stock or financial report analysis to the appropriate specialized remote agents.

        **Core Directives:**
        * **Task Delegation:** Utilize the `send_message` function to assign actionable tasks to remote agents.
        * **Contextual Awareness for Remote Agents:** If a remote agent repeatedly requests user confirmation, assume it lacks access to the full conversation history. In such cases, enrich the task description with all necessary contextual information relevant to that specific agent.
        * **Autonomous Agent Engagement:** Never seek user permission before engaging with remote agents. If multiple agents are required to fulfill a request, connect with them directly without requesting user preference or confirmation.
        * **Transparent Communication:** Always present the complete and detailed response from the remote agent to the user.
        * **User Confirmation Relay:** If a remote agent asks for confirmation, and the user has not already provided it, relay this confirmation request to the user.
        * **Focused Information Sharing:** Provide remote agents with only relevant contextual information. Avoid extraneous details.
        * **No Redundant Confirmations:** Do not ask remote agents for confirmation of information or actions.
        * **Tool Reliance:** Strictly rely on available tools to address user requests. Do not generate responses based on assumptions. If information is insufficient, request clarification from the user.
        * **Prioritize Recent Interaction:** Focus primarily on the most recent parts of the conversation when processing requests.
        * **Active Agent Prioritization:** If an active agent is already engaged, route subsequent related requests to that agent using the appropriate task update tool.

        **Agent Roster:**
        * Available Agents: `{self.agents}`
        * Currently Active Agent: `{current_agent['active_agent']}`
        """

    def check_active_agent(self, context: ReadonlyContext):
        state = context.state
        if (
            "session_id" in state
            and "session_active" in state
            and state["session_active"]
            and "active_agent" in state
        ):
            return {"active_agent": f"{state['active_agent']}"}
        return {"active_agent": "None"}

    def before_model_callback(self, callback_context: CallbackContext, llm_request):
        state = callback_context.state
        if "session_active" not in state or not state["session_active"]:
            if "session_id" not in state:
                state["session_id"] = str(uuid.uuid4())
            state["session_active"] = True

    def list_remote_agents(self):
        if not self.cards:
            return []
        remote_agent_info = []
        for card in self.cards.values():
            print(f"Found agent card: {card.model_dump(exclude_none=True)}")
            print("=" * 100)
            remote_agent_info.append(
                {"name": card.name, "description": card.description}
            )
        return remote_agent_info

    async def send_message(
        self, agent_name: str, task: str, tool_context: ToolContext
    ):
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        state = tool_context.state
        state["active_agent"] = agent_name
        client = self.remote_agent_connections[agent_name]
        if not client:
            raise ValueError(f"Client not available for {agent_name}")
        if "task_id" in state:
            taskId = state["task_id"]
        else:
            taskId = str(uuid.uuid4())
        task_id = taskId
        sessionId = state["session_id"]
        if "context_id" in state:
            context_id = state["context_id"]
        else:
            context_id = str(uuid.uuid4())
        messageId = ""
        metadata = {}
        if "input_message_metadata" in state:
            metadata.update(**state["input_message_metadata"])
            if "message_id" in state["input_message_metadata"]:
                messageId = state["input_message_metadata"]["message_id"]
        if not messageId:
            messageId = str(uuid.uuid4())
        # If the task is a filename string, wrap it in a dict with key 'filename'
        message_content = task
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": json.dumps(message_content)}],
                "messageId": messageId,
            },
        }
        if task_id:
            payload["message"]["taskId"] = task_id
        if context_id:
            payload["message"]["contextId"] = context_id
        message_request = SendMessageRequest(
            id=messageId, params=MessageSendParams.model_validate(payload)
        )
        send_response: SendMessageResponse = await client.send_message(message_request=message_request)
        print("send_response", send_response)
        if not isinstance(send_response.root, SendMessageSuccessResponse):
            print("received non-success response. Aborting get task ")
            return
        if not isinstance(send_response.root.result, Task):
            print("received non-task response. Aborting get task ")
            return
        response = send_response
        if hasattr(response, "root"):
            content = response.root.model_dump_json(exclude_none=True)
        else:
            content = response.model_dump(mode="json", exclude_none=True)
        resp = []
        json_content = json.loads(content)
        print(json_content)
        if json_content.get("result") and json_content["result"].get("artifacts"):
            for artifact in json_content["result"]["artifacts"]:
                if artifact.get("parts"):
                    resp.extend(artifact["parts"])
        return resp

def _get_initialized_host_agent_sync():
    async def _async_main():
        host_agent_instance = await HostAgent.create(
            remote_agent_addresses=[
                os.getenv("REPORT_AGENT_URL", "http://localhost:10003"),
                os.getenv("STOCK_AGENT_URL", "http://localhost:10004"),
            ]
        )
        return host_agent_instance.create_agent()
    try:
        return asyncio.run(_async_main())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            print(f"Warning: Could not initialize HostAgent with asyncio.run(): {e}. "
                  "This can happen if an event loop is already running (e.g., in Jupyter). "
                  "Consider initializing HostAgent within an async function in your application.")
        raise

host_agent = _get_initialized_host_agent_sync()
