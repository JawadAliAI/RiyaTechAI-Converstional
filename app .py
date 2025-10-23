from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import google.generativeai as genai
import os
from datetime import datetime
import uuid
import json
from pathlib import Path

# Configure Gemini API
os.environ["GOOGLE_API_KEY"] = "AIzaSyDYeLGYWP9Blu56tWP9V8kN9XFRxEpobEE"
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

MODEL_ID = "gemini-2.0-flash-exp"

# Create storage directory
STORAGE_DIR = Path("consultation_storage")
STORAGE_DIR.mkdir(exist_ok=True)


# IMPROVED System prompt
DOCTOR_SYSTEM_PROMPT = """You are Dr. Alex, a real human doctor having a natural conversation with a patient.

🎯 CORE PRINCIPLE: Talk like a real doctor, not a chatbot. Real doctors don't use the same phrases repeatedly or follow rigid scripts.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ BANNED PHRASES (Never use these):
- "Thank you for sharing that with me"
- "I appreciate you telling me that"
- "Thanks for providing that information"
- Any repetitive acknowledgment phrase

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ NATURAL ACKNOWLEDGMENTS (Rotate these):
- "I see"
- "Got it"
- "Okay"
- "Alright"
- "That helps"
- "Makes sense"
- "Understood"
- "Right"
- "Mm-hmm"
- "Fair enough"
- Just move to the next question without acknowledgment

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 CONVERSATION STRUCTURE:

OPENING (1st message):
- Start with empathy if appropriate: "I'm sorry to hear that" / "That sounds uncomfortable"
- Ask ONE specific, focused question
- Include 2-3 options if helpful: "Is it sharp, dull, or burning?"

FOLLOW-UP (2nd-3rd messages):
- Ask about: timing, location, severity, triggers, or related symptoms
- Keep questions SHORT and direct
- If they give a short answer ("no" / "yesterday"), acknowledge briefly and move on
- Don't over-explain why you're asking

RECOMMENDATION (After 3-4 exchanges):
- Stop asking questions - start helping
- Give clear, actionable advice
- Structure your response naturally, not as a rigid list

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 EXAMPLE - NATURAL FLOW:

Patient: "I have lower back pain"
You: "I'm sorry to hear that. Is it more on one side or centered? And is it sharp, dull, or aching?"

Patient: "left side, sharp"
You: "Okay. When did this start?"

Patient: "yesterday after lifting boxes"
You: "Got it. Does the pain shoot down your leg at all, or stay in your back?"

Patient: "just my back"
You: "Alright. Based on what you're describing, this sounds like a muscle strain from the lifting. Here's what I'd recommend:

First, ice the area for 15-20 minutes every few hours today and tomorrow. After that, switch to heat. Ibuprofen or naproxen will help with both pain and inflammation - follow the bottle instructions.

Avoid heavy lifting for the next few days, but gentle movement is actually better than complete rest. Light walking is good.

You should feel improvement in 2-3 days. See a doctor if the pain shoots down your leg, you develop numbness or tingling, or it's not better in a week."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 RECOMMENDATION FORMAT:

After gathering key information (3-4 questions max), provide:

1. **What it likely is**: "This sounds like [condition]" or "This could be [X or Y]"

2. **Immediate actions**: What to do in the next 24-48 hours

3. **Medications** (if appropriate): OTC options with brief guidance

4. **Lifestyle advice**: Specific, practical tips

5. **Red flags**: "See a doctor if [specific warning signs]" or "This should improve in [timeframe]"

Write this naturally - don't number it unless listing items.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ DO:
- Vary your sentence structure constantly
- Mix short and longer responses
- Show empathy when appropriate (not robotically)
- Get to recommendations quickly (3-4 questions max)
- Be direct and confident
- Use contractions (I'm, you're, it's)

❌ DON'T:
- Repeat the same acknowledgment phrase
- Ask obvious or redundant questions
- Use template language
- Over-apologize or over-thank
- Ask 10 questions before helping
- Use formal medical jargon unless necessary
- End every message with a question

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚨 HANDLING SHORT ANSWERS:

If patient says just "no" or "yes":
- Brief acknowledgment: "Okay" / "Got it"
- Move immediately to next question or recommendation
- Don't make them feel bad for short answers

Example:
Patient: "no"
You: "Okay, no problem. How about..." [next question]

NOT: "Thank you for clarifying that. I appreciate you answering. Now, how about..."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Remember: You're a knowledgeable, efficient doctor who respects the patient's time. Ask what you need to know, then help them. That's it."""

# =====================================================
# STORAGE FUNCTIONS
# =====================================================

def save_session_to_json(session_id: str, memory: 'ConversationMemory'):
    """Save session data to JSON file"""
    file_path = STORAGE_DIR / f"{session_id}.json"
    
    session_data = {
        "session_id": session_id,
        "created_at": memory.created_at.isoformat(),
        "last_updated": datetime.now().isoformat(),
        "patient_data": memory.patient_data,
        "questions_asked": memory.questions_asked,
        "history": memory.history,
        "message_count": len(memory.history)
    }
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)

def load_session_from_json(session_id: str) -> Optional[Dict]:
    """Load session data from JSON file"""
    file_path = STORAGE_DIR / f"{session_id}.json"
    
    if not file_path.exists():
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def list_all_sessions() -> List[Dict]:
    """List all stored sessions"""
    sessions_list = []
    
    for file_path in STORAGE_DIR.glob("*.json"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                sessions_list.append({
                    "session_id": data["session_id"],
                    "created_at": data["created_at"],
                    "last_updated": data.get("last_updated", data["created_at"]),
                    "patient_name": data["patient_data"].get("name", "Unknown"),
                    "message_count": data["message_count"]
                })
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    
    return sorted(sessions_list, key=lambda x: x["last_updated"], reverse=True)

# =====================================================
# SHORT-TERM MEMORY MANAGEMENT
# =====================================================

class ConversationMemory:
    """Manages short-term memory for each session"""
    def __init__(self, max_messages: int = 20, session_id: str = None):
        self.max_messages = max_messages
        self.history = []
        self.patient_data = {}
        self.created_at = datetime.now()
        self.questions_asked = 0
        self.session_id = session_id
        
    def add_message(self, role: str, content: str):
        """Add message to history with memory management"""
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        if role == "assistant" and "?" in content:
            self.questions_asked += 1
        
        if len(self.history) > self.max_messages:
            self.history = [self.history[0]] + self.history[-(self.max_messages-1):]
        
        # Auto-save to JSON after each message
        if self.session_id:
            save_session_to_json(self.session_id, self)
    
    def extract_patient_info(self, message: str):
        """Extract and store patient information from conversation"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["name is", "i'm", "i am", "im"]):
            words = message.split()
            for i, word in enumerate(words):
                if word.lower() in ["is", "i'm", "am", "im"] and i + 1 < len(words):
                    self.patient_data["name"] = words[i + 1].strip(".,!?")
        
        if "year" in message_lower or "age" in message_lower:
            import re
            age_match = re.search(r'\b(\d{1,3})\b', message)
            if age_match:
                self.patient_data["age"] = age_match.group(1)
        
        if "fever" in message_lower or "pain" in message_lower or "sick" in message_lower:
            self.patient_data["has_symptoms"] = True
    
    def should_give_recommendations(self) -> bool:
        """Check if we should provide recommendations now"""
        return (
            self.questions_asked >= 7 or 
            self.patient_data.get("has_symptoms", False)
        )
    
    def get_context_summary(self) -> str:
        """Generate a brief context summary for the AI"""
        summary = "\n[Session Context: "
        if "name" in self.patient_data:
            summary += f"Name: {self.patient_data['name']}, "
        if "age" in self.patient_data:
            summary += f"Age: {self.patient_data['age']}, "
        summary += f"Questions asked: {self.questions_asked}/7, "
        
        if self.questions_asked >= 5:
            summary += "⚠️ IMPORTANT: You've asked enough questions. After the next 1-2 answers, IMMEDIATELY provide comprehensive medical recommendations.]"
        elif self.questions_asked >= 7:
            summary += "⚠️ CRITICAL: You MUST provide comprehensive medical recommendations NOW. Do not ask more questions!]"
        else:
            summary += f"Ask {7 - self.questions_asked} more essential questions then give recommendations.]"
        
        return summary
    
    def get_gemini_history(self) -> List[Dict]:
        """Convert history to Gemini format"""
        gemini_history = []
        for msg in self.history:
            gemini_history.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [msg["content"]]
            })
        return gemini_history
    
    @classmethod
    def from_json(cls, session_data: Dict) -> 'ConversationMemory':
        """Create ConversationMemory from JSON data"""
        memory = cls(session_id=session_data["session_id"])
        memory.history = session_data["history"]
        memory.patient_data = session_data["patient_data"]
        memory.questions_asked = session_data["questions_asked"]
        memory.created_at = datetime.fromisoformat(session_data["created_at"])
        return memory

# Global session storage (in-memory cache)
sessions: Dict[str, ConversationMemory] = {}

def cleanup_old_sessions():
    """Remove sessions older than 1 hour from memory (JSON persists)"""
    current_time = datetime.now()
    expired_sessions = []
    
    for session_id, memory in sessions.items():
        age = (current_time - memory.created_at).total_seconds()
        if age > 3600:
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        del sessions[session_id]

# =====================================================
# FASTAPI APPLICATION
# =====================================================

app = FastAPI(
    title="AI Doctor Consultation API",
    description="Professional medical consultation API with persistent JSON storage",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    timestamp: str
    patient_data: Dict

class SessionRequest(BaseModel):
    session_id: str

class SummaryResponse(BaseModel):
    summary: str
    session_id: str

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    active_sessions: int
    stored_sessions: int

# =====================================================
# API ENDPOINTS
# =====================================================

@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint"""
    cleanup_old_sessions()
    stored_count = len(list(STORAGE_DIR.glob("*.json")))
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(sessions),
        "stored_sessions": stored_count
    }


@app.post("/start-session")
async def start_session():
    """Start a new consultation session"""
    session_id = str(uuid.uuid4())
    sessions[session_id] = ConversationMemory(max_messages=20, session_id=session_id)
    
    initial_message = "Hello! I'm Dr. AI Assistant. I'm here to help you today.\n\n👤 May I have your name, please?"
    
    sessions[session_id].add_message("assistant", initial_message)
    
    return {
        "session_id": session_id,
        "message": initial_message,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and get doctor's response"""
    try:
        # Get or create session
        if not request.session_id or request.session_id not in sessions:
            session_id = str(uuid.uuid4())
            sessions[session_id] = ConversationMemory(max_messages=20, session_id=session_id)
        else:
            session_id = request.session_id
        
        memory = sessions[session_id]
        
        # Extract patient information
        memory.extract_patient_info(request.message)
        
        # Add user message to memory
        memory.add_message("user", request.message)
        
        # Create model with system instruction + context
        context = memory.get_context_summary()
        system_prompt = DOCTOR_SYSTEM_PROMPT + context
        
        model = genai.GenerativeModel(
            model_name=MODEL_ID,
            system_instruction=system_prompt
        )
        
        # Start chat with history
        chat = model.start_chat(history=memory.get_gemini_history()[:-1])
        
        # Get response
        response = chat.send_message(request.message)
        doctor_response = response.text
        
        # Add assistant response to memory
        memory.add_message("assistant", doctor_response)
        
        return {
            "session_id": session_id,
            "response": doctor_response,
            "timestamp": datetime.now().isoformat(),
            "patient_data": memory.patient_data
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/load-session/{session_id}")
async def load_session(session_id: str):
    """Load a previous consultation session by ID"""
    # Check if already in memory
    if session_id in sessions:
        memory = sessions[session_id]
        return {
            "session_id": session_id,
            "loaded": True,
            "from_cache": True,
            "history": memory.history,
            "patient_data": memory.patient_data,
            "created_at": memory.created_at.isoformat(),
            "questions_asked": memory.questions_asked
        }
    
    # Try to load from JSON
    session_data = load_session_from_json(session_id)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    # Restore to memory
    memory = ConversationMemory.from_json(session_data)
    sessions[session_id] = memory
    
    return {
        "session_id": session_id,
        "loaded": True,
        "from_cache": False,
        "history": memory.history,
        "patient_data": memory.patient_data,
        "created_at": memory.created_at.isoformat(),
        "questions_asked": memory.questions_asked,
        "message": "Session loaded successfully. You can continue the conversation."
    }

@app.get("/all-sessions")
async def get_all_sessions():
    """Get list of all stored consultation sessions"""
    return {
        "total_sessions": len(list(STORAGE_DIR.glob("*.json"))),
        "sessions": list_all_sessions()
    }

@app.post("/summary", response_model=SummaryResponse)
async def generate_summary(request: SessionRequest):
    """Generate consultation summary for a session"""
    # Try memory first
    if request.session_id not in sessions:
        # Try loading from JSON
        session_data = load_session_from_json(request.session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        memory = ConversationMemory.from_json(session_data)
        sessions[request.session_id] = memory
    else:
        memory = sessions[request.session_id]
    
    summary_request = """Please generate a comprehensive consultation summary based on our conversation:

📋 **MEDICAL CONSULTATION SUMMARY**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Patient Information:**
[Include name, age, gender, date]

**Chief Complaints:**
[Main symptoms]

**Medical History:**
[Relevant history]

**Assessment:**
[Your preliminary assessment]

**Recommendations:**

1. **Dietary Recommendations:**
   [Specific advice]

2. **Lifestyle Modifications:**
   [Changes needed]

3. **Exercise & Physical Activity:**
   [Recommendations]

4. **Medication Suggestions:**
   [With disclaimer]

5. **Follow-up Care:**
   [When to seek attention]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ This is a preliminary AI consultation. Please consult a licensed medical doctor for accurate diagnosis and treatment.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    
    try:
        model = genai.GenerativeModel(
            model_name=MODEL_ID,
            system_instruction=DOCTOR_SYSTEM_PROMPT
        )
        
        chat = model.start_chat(history=memory.get_gemini_history())
        response = chat.send_message(summary_request)
        
        return {
            "summary": response.text,
            "session_id": request.session_id
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")

@app.post("/restart-session")
async def restart_session(request: SessionRequest):
    """Restart a consultation session"""
    if request.session_id in sessions:
        del sessions[request.session_id]
    
    sessions[request.session_id] = ConversationMemory(max_messages=20, session_id=request.session_id)
    
    initial_message = "Consultation restarted. Hello! I'm Dr. AI Assistant. May I have your name please?"
    sessions[request.session_id].add_message("assistant", initial_message)
    
    return {
        "session_id": request.session_id,
        "message": initial_message,
        "timestamp": datetime.now().isoformat()
    }

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a consultation session (from memory and JSON)"""
    # Remove from memory
    if session_id in sessions:
        del sessions[session_id]
    
    # Remove JSON file
    file_path = STORAGE_DIR / f"{session_id}.json"
    if file_path.exists():
        file_path.unlink()
        return {"message": "Session deleted successfully from both memory and storage"}
    
    raise HTTPException(status_code=404, detail="Session not found")

@app.get("/session/{session_id}/history")
async def get_session_history(session_id: str):
    """Get conversation history for a session"""
    # Try memory first
    if session_id in sessions:
        memory = sessions[session_id]
    else:
        # Try loading from JSON
        session_data = load_session_from_json(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        memory = ConversationMemory.from_json(session_data)
    
    return {
        "session_id": session_id,
        "history": memory.history,
        "patient_data": memory.patient_data,
        "created_at": memory.created_at.isoformat(),
        "questions_asked": memory.questions_asked
    }

from fastapi.responses import FileResponse, HTMLResponse

@app.get("/", response_class=HTMLResponse)
def serve_index():
    return FileResponse("index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
