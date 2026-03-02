import base64
import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import ButlerAgent
from agent.network_utils import force_ipv4

# Force IPv4 to prevent timeouts on environments with broken IPv6
force_ipv4()

app = FastAPI(
    title="Butler AI REST API",
    description="REST API for interacting with the Butler Agent, supporting text and image inputs.",
    version="1.0.0"
)

# ── Models ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    image_base64: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    session_id: str

# ── Agent Instance ──────────────────────────────────────────────────────

_agent: Optional[ButlerAgent] = None

def get_agent() -> ButlerAgent:
    """Lazy-initialise the ButlerAgent."""
    global _agent
    if _agent is None:
        try:
            _agent = ButlerAgent()
        except Exception as e:
            raise RuntimeError(f"Failed to initialise ButlerAgent: {e}")
    return _agent

# ── Endpoints ──────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Primary chat endpoint.
    - message: The user's text input.
    - session_id: Optional session ID to maintain conversation state.
    - image_base64: Optional base64-encoded image string.
    """
    agent = get_agent()
    
    # 1. Handle session switching
    if request.session_id:
        try:
            # Attempt to switch to existing session
            agent.switch_session(request.session_id)
        except ValueError:
            # If session doesn't exist, we'll start using this ID
            # ButlerAgent logic will handle adding messages to this new ID
            agent.session_id = request.session_id
            
    # 2. Handle image base64
    image_bytes = None
    if request.image_base64:
        try:
            # Basic validation: remove header if present (e.g. "data:image/jpeg;base64,")
            b64_data = request.image_base64
            if "," in b64_data:
                b64_data = b64_data.split(",")[1]
            image_bytes = base64.b64decode(b64_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {e}")

    # 3. Process with Agent
    try:
        reply = agent.chat(request.message, image_bytes=image_bytes)
        return ChatResponse(
            reply=reply,
            session_id=agent.session_id
        )
    except Exception as e:
        # Log error in real application
        raise HTTPException(status_code=500, detail=f"Agent Error: {str(e)}")

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "agent_initialised": _agent is not None}

@app.get("/sessions")
async def list_sessions():
    """List all available chat sessions."""
    agent = get_agent()
    return agent.list_sessions()

if __name__ == "__main__":
    import uvicorn
    # Allow port to be set via env var for Docker
    port = int(os.getenv("API_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
