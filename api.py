import base64
import os
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
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

class AudioResponse(BaseModel):
    transcription: str
    reply: str
    audio_base64: str
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

@app.post("/audio", response_model=AudioResponse)
async def audio_endpoint(
    file: UploadFile = File(...), 
    session_id: Optional[str] = None,
    instruction: Optional[str] = None
):
    """
    Audio interaction endpoint.
    - file: The user's voice input (wav/mp3/etc).
    - session_id: Optional session ID.
    - instruction: Optional instruction to prepend/append to the transcription.
    """
    agent = get_agent()
    
    if session_id:
        try:
            agent.switch_session(session_id)
        except ValueError:
            agent.session_id = session_id

    try:
        audio_bytes = await file.read()
        
        # 1. Transcribe (includes noise reduction by default)
        user_text = agent.voice.transcribe(audio_bytes)
        if user_text.startswith("Error:"):
             return AudioResponse(transcription="", reply=user_text, audio_base64="", session_id=agent.session_id)

        # 2. Append instruction if provided
        chat_prompt = user_text
        if instruction:
            chat_prompt += instruction

        # 3. Regular Chat
        assistant_reply = agent.chat(chat_prompt)

        # 4. Synthesize Speech
        audio_reply = agent.voice.generate_speech(assistant_reply)
        
        audio_b64 = ""
        if audio_reply:
            audio_b64 = base64.b64encode(audio_reply).decode("utf-8")

        return AudioResponse(
            transcription=user_text,
            reply=assistant_reply,
            audio_base64=audio_b64,
            session_id=agent.session_id
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Voice Agent Error: {str(e)}")

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
