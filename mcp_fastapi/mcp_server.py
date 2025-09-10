# mcp_server.py

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import yaml
import logging
import requests

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Custom MCP Server",
    description="A custom server to expose tools from a tools.yaml file.",
)

# Load tool definitions from the tools.yaml file
def load_tool_definitions(file_path: str):
    try:
        # 파일을 'utf-8' 인코딩으로 명시적으로 읽도록 수정
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Error: The file '{file_path}' was not found.")
        raise HTTPException(status_code=404, detail="Tools file not found.")


tools_config = load_tool_definitions("tools.yaml")

# A simple in-memory session store (replace with a real DB for persistence)
session_store: Dict[str, Dict] = {}

class ToolCallRequest(BaseModel):
    tool_name: str
    params: Dict[str, Any]
    session_id: str
    user_id: str

@app.post("/call")
async def handle_tool_call(request_data: ToolCallRequest):
    """
    Handles a tool call request by routing it to the appropriate external API.
    """
    tool_name = request_data.tool_name
    params = request_data.params
    session_id = request_data.session_id
    user_id = request_data.user_id

    logging.info(f"Received call for tool '{tool_name}' from user '{user_id}'.")

    # Look up the tool definition in the loaded config
    tool_definition = tools_config.get(tool_name)
    if not tool_definition:
        logging.error(f"Error: Tool '{tool_name}' not found in tools.yaml.")
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found.")

    tool_url = tool_definition.get("url")
    http_method = tool_definition.get("http_method", "GET").upper()

    try:
        # Add session and user ID to parameters if required by the tool
        # This is a key part of maintaining context
        if 'session_id' in params:
            params['session_id'] = session_id
        if 'user_id' in params:
            params['user_id'] = user_id

        # Route the request to the external API based on the HTTP method
        if http_method == "GET":
            response = requests.get(tool_url, params=params)
        elif http_method == "POST":
            response = requests.post(tool_url, json=params)
        else:
            raise HTTPException(status_code=405, detail=f"HTTP method '{http_method}' not supported.")

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling tool '{tool_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to call external tool: {e}")

@app.get("/tools")
async def get_tools():
    """
    Returns the full set of tool definitions for discovery by the Gemini agent.
    """
    return tools_config