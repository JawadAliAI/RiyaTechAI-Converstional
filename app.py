from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import google.generativeai as genai
import os
from datetime import datetime
import uuid
import json
from pathlib import Path
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas

# Configure Gemini API
os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

MODEL_ID = "gemini-2.0-flash-exp"

# Create storage directories
STORAGE_DIR = Path("consultation_storage")
STORAGE_DIR.mkdir(exist_ok=True)

PDF_DIR = Path("consultation_pdfs")
PDF_DIR.mkdir(exist_ok=True)

# System prompt (same as before)
DOCTOR_SYSTEM_PROMPT = """
You are Dr. HealBot, a calm, knowledgeable, and empathetic virtual doctor.

GOAL:
Hold a natural, focused conversation with the patient to understand their health issue and offer helpful preliminary medical guidance.

CONVERSATION LOGIC:
- Ask only relevant and concise medical questions necessary for diagnosing the illness.
- Each question should help clarify symptoms or narrow possible causes.
- Stop asking once enough information is collected for a basic assessment.
- Then, provide a structured, friendly, and visually clear medical response using headings, emojis, and bullet points.

FINAL RESPONSE FORMAT:
When giving your full assessment, use this markdown-styled format:

🩺 Based on what you've told me...
Brief summary of what the patient described.

💡 Possible Causes (Preliminary)
- List 1–2 possible conditions using phrases like "It could be" or "This sounds like".
- Include a disclaimer that this is not a confirmed diagnosis.

💊 Suggested Over-the-Counter Medicines
- Generic medicine names only (e.g., "Paracetamol 500mg every 6 hours if fever or pain")
- Mention to check packaging or consult a pharmacist for dosage confirmation.

🥗 Lifestyle & Home Care Tips
- 2–3 practical suggestions (rest, hydration, warm compress, balanced diet, etc.)

⚠ When to See a Real Doctor
- 2–3 warning signs or conditions when urgent medical care is needed.

📅 Follow-Up Advice
- Brief recommendation for self-care or follow-up timing (e.g., "If not improving in 3 days, visit a clinic.")

TONE & STYLE:
- Speak like a real, caring doctor — short, clear, and empathetic (1–2 sentences per reply).
- Use plain language, no jargon.
- Only one question per turn unless clarification is essential.
- Keep tone warm, calm, and professional.
- Early messages: short questions only.
- Final message: structured output with emojis and headings.

IMPORTANT:
- Always emphasize that this is preliminary guidance and not a substitute for professional care.
- Never make definitive diagnoses; use phrases like "it sounds like" or "it could be".
- If symptoms seem serious, always recommend urgent medical attention.

CONVERSATION FLOW:
1. Ask about the main symptom.
2. Ask about its duration, severity, and any triggers.
3. Ask about accompanying symptoms.
4. Ask about medical history, allergies, or medications.
5. Then, provide your structured assessment as described above.
"""

# =====================================================
# PDF GENERATION FUNCTIONS
# =====================================================

def generate_pdf_summary(session_id: str, summary_text: str, patient_data: Dict, history: List[Dict]) -> str:
    """Generate a professional PDF summary of the consultation"""
    
    pdf_filename = f"{session_id}_summary.pdf"
    pdf_path = PDF_DIR / pdf_filename
    
    # Create PDF document
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=12,
        alignment=TA_JUSTIFY,
        leading=14
    )
    
    # Add Title
    elements.append(Paragraph("🩺 AI DOCTOR CONSULTATION SUMMARY", title_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Add horizontal line
    elements.append(Spacer(1, 0.1*inch))
    
    # Patient Information Table
    patient_info_data = [
        ['Patient Name:', patient_data.get('name', 'N/A')],
        ['Age:', patient_data.get('age', 'N/A')],
        ['Session ID:', session_id[:20] + '...'],
        ['Consultation Date:', datetime.now().strftime('%B %d, %Y at %I:%M %p')],
        ['Total Messages:', str(len(history))]
    ]
    
    patient_table = Table(patient_info_data, colWidths=[2*inch, 4*inch])
    patient_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    
    elements.append(patient_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Add Consultation Summary
    elements.append(Paragraph("CONSULTATION SUMMARY", heading_style))
    
    # Process summary text - split by lines and convert to paragraphs
    summary_lines = summary_text.split('\n')
    for line in summary_lines:
        if line.strip():
            # Replace emojis with text equivalents for PDF compatibility
            line = line.replace('🩺', '[Medical] ')
            line = line.replace('💡', '[Insight] ')
            line = line.replace('💊', '[Medicine] ')
            line = line.replace('🥗', '[Lifestyle] ')
            line = line.replace('⚠️', '[Warning] ')
            line = line.replace('⚠', '[Warning] ')
            line = line.replace('📅', '[Follow-up] ')
            line = line.replace('━', '-')
            
            # Check if it's a heading (starts with **)
            if line.strip().startswith('**') and line.strip().endswith('**'):
                elements.append(Paragraph(line.strip('*'), heading_style))
            else:
                elements.append(Paragraph(line, normal_style))
    
    elements.append(Spacer(1, 0.3*inch))
    
    # Add Conversation History
    elements.append(PageBreak())
    elements.append(Paragraph("CONVERSATION HISTORY", heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    for i, msg in enumerate(history, 1):
        role = "DOCTOR" if msg['role'] == 'assistant' else "PATIENT"
        timestamp = msg.get('timestamp', 'N/A')
        
        role_style = ParagraphStyle(
            f'Role{i}',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#667eea') if role == "DOCTOR" else colors.HexColor('#28a745'),
            fontName='Helvetica-Bold',
            spaceAfter=4
        )
        
        elements.append(Paragraph(f"{role} ({timestamp}):", role_style))
        
        content = msg['content'].replace('🩺', '').replace('💡', '').replace('💊', '')
        content = content.replace('🥗', '').replace('⚠️', '').replace('⚠', '').replace('📅', '')
        elements.append(Paragraph(content, normal_style))
        elements.append(Spacer(1, 0.15*inch))
    
    # Add disclaimer at the end
    elements.append(Spacer(1, 0.3*inch))
    
    disclaimer_style = ParagraphStyle(
        'Disclaimer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.red,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        borderColor=colors.red,
        borderWidth=1,
        borderPadding=10,
        spaceAfter=12
    )
    
    elements.append(Paragraph(
        "⚠ IMPORTANT DISCLAIMER ⚠<br/>" +
        "This is a preliminary AI-generated consultation for informational purposes only.<br/>" +
        "It is NOT a substitute for professional medical advice, diagnosis, or treatment.<br/>" +
        "Always seek the advice of a qualified healthcare provider with any questions regarding a medical condition.",
        disclaimer_style
    ))
    
    # Build PDF
    doc.build(elements)
    
    return pdf_filename

# =====================================================
# STORAGE FUNCTIONS (same as before)
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
        "message_count": len(memory.history),
        "pdf_filename": getattr(memory, 'pdf_filename', None)
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
                    "message_count": data["message_count"],
                    "has_pdf": data.get("pdf_filename") is not None
                })
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    
    return sorted(sessions_list, key=lambda x: x["last_updated"], reverse=True)

# =====================================================
# MEMORY MANAGEMENT (same as before)
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
        self.pdf_filename = None
        
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
        memory.pdf_filename = session_data.get("pdf_filename")
        return memory

sessions: Dict[str, ConversationMemory] = {}

def cleanup_old_sessions():
    """Remove sessions older than 1 hour from memory"""
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
    title="AI Doctor Consultation API with PDF Generation",
    description="Professional medical consultation API with PDF summary generation",
    version="3.0.0"
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
    pdf_filename: str
    pdf_url: str

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    active_sessions: int
    stored_sessions: int
    stored_pdfs: int

# =====================================================
# API ENDPOINTS
# =====================================================

@app.get("/", response_model=HealthCheck)
async def root():
    """Health check endpoint"""
    cleanup_old_sessions()
    stored_count = len(list(STORAGE_DIR.glob("*.json")))
    pdf_count = len(list(PDF_DIR.glob("*.pdf")))
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(sessions),
        "stored_sessions": stored_count,
        "stored_pdfs": pdf_count
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
        if not request.session_id or request.session_id not in sessions:
            session_id = str(uuid.uuid4())
            sessions[session_id] = ConversationMemory(max_messages=20, session_id=session_id)
        else:
            session_id = request.session_id
        
        memory = sessions[session_id]
        memory.extract_patient_info(request.message)
        memory.add_message("user", request.message)
        
        context = memory.get_context_summary()
        system_prompt = DOCTOR_SYSTEM_PROMPT + context
        
        model = genai.GenerativeModel(
            model_name=MODEL_ID,
            system_instruction=system_prompt
        )
        
        chat = model.start_chat(history=memory.get_gemini_history()[:-1])
        response = chat.send_message(request.message)
        doctor_response = response.text
        
        memory.add_message("assistant", doctor_response)
        
        return {
            "session_id": session_id,
            "response": doctor_response,
            "timestamp": datetime.now().isoformat(),
            "patient_data": memory.patient_data
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/summary", response_model=SummaryResponse)
async def generate_summary(request: SessionRequest):
    """Generate consultation summary and PDF"""
    if request.session_id not in sessions:
        session_data = load_session_from_json(request.session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        memory = ConversationMemory.from_json(session_data)
        sessions[request.session_id] = memory
    else:
        memory = sessions[request.session_id]
    
    summary_request = """Please generate a COMPREHENSIVE and DETAILED medical consultation summary based on our entire conversation. Make it thorough and professional:

📋 **COMPREHENSIVE MEDICAL CONSULTATION SUMMARY**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**PATIENT INFORMATION:**
- Full Name: [Patient's name]
- Age: [Patient's age if mentioned]
- Gender: [If mentioned]
- Consultation Date: [Current date and time]
- Session Duration: [Approximate]
- Current Medications: [List all mentioned]
- Known Allergies: [If mentioned]

**CHIEF COMPLAINTS & SYMPTOMS:**
[Provide a detailed description of ALL symptoms mentioned, including:]
- Primary symptom and severity
- Duration of each symptom
- Onset and progression
- Associated symptoms
- Aggravating and relieving factors
- Impact on daily activities

**DETAILED MEDICAL HISTORY:**
[Include everything discussed:]
- Current medications and dosages
- Past medical conditions
- Recent illnesses or infections
- Family medical history (if mentioned)
- Lifestyle factors (sleep, stress, diet)
- Recent travel or exposures

**CLINICAL ASSESSMENT:**
[Provide detailed analysis:]
- Most likely diagnosis with explanation
- Differential diagnoses (2-3 possibilities)
- Reasoning behind each possibility
- Risk factors present
- Severity assessment

**COMPREHENSIVE TREATMENT PLAN:**

1. **IMMEDIATE CARE RECOMMENDATIONS:**
   - What to do in the next 24-48 hours
   - Symptom management strategies
   - Warning signs to watch for

2. **MEDICATION RECOMMENDATIONS:**
   - Primary medications (generic names, dosages, frequency, duration)
   - Alternative options if first choice unavailable
   - Potential side effects to monitor
   - Drug interactions to avoid
   - When to take each medication (with/without food)
   - Important: Check with pharmacist for exact dosing

3. **DETAILED DIETARY RECOMMENDATIONS:**
   - Foods to eat (specific examples and portions)
   - Foods to avoid completely
   - Meal timing and frequency
   - Hydration guidelines (specific amounts)
   - Nutritional supplements if needed
   - Sample meal plan for recovery

4. **LIFESTYLE MODIFICATIONS:**
   - Sleep recommendations (hours, timing, environment)
   - Rest and activity balance
   - Stress management techniques
   - Environmental modifications
   - Work/school attendance guidance
   - Specific activities to avoid

5. **HOME CARE REMEDIES:**
   - Natural remedies that may help
   - Temperature management techniques
   - Pain relief methods
   - Steam inhalation or other therapies
   - Specific home treatments for symptoms

6. **EXERCISE & PHYSICAL ACTIVITY:**
   - Current activity restrictions
   - Safe exercises during recovery
   - When to resume normal activities
   - Gradual activity progression plan
   - Post-recovery exercise recommendations

7. **PREVENTIVE MEASURES:**
   - How to prevent recurrence
   - Hygiene practices
   - Vaccination recommendations
   - Family/household precautions
   - Long-term health maintenance

8. **MONITORING PLAN:**
   - Symptoms to track daily
   - How to measure improvement
   - When improvement should be expected
   - What to document for doctor visit

**CRITICAL WARNING SIGNS - SEEK IMMEDIATE MEDICAL ATTENTION IF:**
[List 5-7 specific warning signs that require emergency care:]
- [Specific symptom with threshold]
- [Specific symptom with threshold]
- [Continue with detailed warnings]

**FOLLOW-UP CARE PLAN:**
- Timeline for self-care (e.g., "Monitor for 48 hours")
- When to schedule doctor appointment (specific timeframe)
- What information to bring to doctor
- Specialist referral recommendations if needed
- Follow-up testing that may be needed

**PROGNOSIS & EXPECTED RECOVERY:**
- Expected recovery timeline
- What to expect during recovery process
- Signs of improvement to look for
- Long-term outlook

**ADDITIONAL RESOURCES:**
- Reputable health information sources
- Support resources if applicable
- Emergency contact information reminder

**PATIENT EDUCATION:**
- Understanding your condition
- How the body fights this illness
- Why specific recommendations are important
- Common misconceptions about this condition

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ **CRITICAL DISCLAIMER** ⚠️
This is a preliminary AI-generated consultation for informational and educational purposes ONLY. 
This is NOT a substitute for professional medical advice, diagnosis, or treatment.
This AI cannot examine you physically, run laboratory tests, or make definitive diagnoses.
ALWAYS seek the advice of a qualified, licensed healthcare provider with any questions regarding a medical condition.
Never disregard professional medical advice or delay seeking it because of this AI consultation.
In case of emergency, call your local emergency services immediately.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Please make this summary as detailed, professional, and helpful as possible. Include specific, actionable advice."""
    
    try:
        model = genai.GenerativeModel(
            model_name=MODEL_ID,
            system_instruction=DOCTOR_SYSTEM_PROMPT
        )
        
        chat = model.start_chat(history=memory.get_gemini_history())
        response = chat.send_message(summary_request)
        summary_text = response.text
        
        # Generate PDF
        pdf_filename = generate_pdf_summary(
            request.session_id,
            summary_text,
            memory.patient_data,
            memory.history
        )
        
        # Save PDF filename to memory
        memory.pdf_filename = pdf_filename
        save_session_to_json(request.session_id, memory)
        
        return {
            "summary": summary_text,
            "session_id": request.session_id,
            "pdf_filename": pdf_filename,
            "pdf_url": f"/download-pdf/{request.session_id}"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")

@app.get("/download-pdf/{session_id}")
async def download_pdf(session_id: str):
    """Download PDF summary for a session"""
    # Check if session exists
    if session_id in sessions:
        memory = sessions[session_id]
    else:
        session_data = load_session_from_json(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        memory = ConversationMemory.from_json(session_data)
    
    if not memory.pdf_filename:
        raise HTTPException(status_code=404, detail="PDF not generated yet. Please generate summary first.")
    
    pdf_path = PDF_DIR / memory.pdf_filename
    
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    
    patient_name = memory.patient_data.get('name', 'Patient')
    download_filename = f"Consultation_Summary_{patient_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return FileResponse(
        path=str(pdf_path),
        media_type='application/pdf',
        filename=download_filename
    )

@app.get("/load-session/{session_id}")
async def load_session(session_id: str):
    """Load a previous consultation session by ID"""
    if session_id in sessions:
        memory = sessions[session_id]
        return {
            "session_id": session_id,
            "loaded": True,
            "from_cache": True,
            "history": memory.history,
            "patient_data": memory.patient_data,
            "created_at": memory.created_at.isoformat(),
            "questions_asked": memory.questions_asked,
            "has_pdf": memory.pdf_filename is not None,
            "pdf_url": f"/download-pdf/{session_id}" if memory.pdf_filename else None
        }
    
    session_data = load_session_from_json(session_id)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
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
        "has_pdf": memory.pdf_filename is not None,
        "pdf_url": f"/download-pdf/{session_id}" if memory.pdf_filename else None,
        "message": "Session loaded successfully. You can continue the conversation."
    }

@app.get("/all-sessions")
async def get_all_sessions():
    """Get list of all stored consultation sessions"""
    return {
        "total_sessions": len(list(STORAGE_DIR.glob("*.json"))),
        "sessions": list_all_sessions()
    }

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
    """Delete a consultation session (from memory, JSON, and PDF)"""
    if session_id in sessions:
        memory = sessions[session_id]
        pdf_filename = memory.pdf_filename
        del sessions[session_id]
    else:
        session_data = load_session_from_json(session_id)
        pdf_filename = session_data.get('pdf_filename') if session_data else None
    
    # Remove JSON file
    file_path = STORAGE_DIR / f"{session_id}.json"
    if file_path.exists():
        file_path.unlink()
    
    # Remove PDF file if exists
    if pdf_filename:
        pdf_path = PDF_DIR / pdf_filename
        if pdf_path.exists():
            pdf_path.unlink()
    
    return {"message": "Session and associated files deleted successfully"}

@app.get("/session/{session_id}/history")
async def get_session_history(session_id: str):
    """Get conversation history for a session"""
    if session_id in sessions:
        memory = sessions[session_id]
    else:
        session_data = load_session_from_json(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        memory = ConversationMemory.from_json(session_data)
    
    return {
        "session_id": session_id,
        "history": memory.history,
        "patient_data": memory.patient_data,
        "created_at": memory.created_at.isoformat(),
        "questions_asked": memory.questions_asked,
        "has_pdf": memory.pdf_filename is not None
    }

@app.get("/active-sessions")
async def get_active_sessions():
    """Get list of all active sessions in memory"""
    cleanup_old_sessions()
    return {
        "active_sessions": len(sessions),
        "sessions": [
            {
                "session_id": sid,
                "created_at": mem.created_at.isoformat(),
                "message_count": len(mem.history),
                "questions_asked": mem.questions_asked,
                "patient_data": mem.patient_data,
                "has_pdf": mem.pdf_filename is not None
            }
            for sid, mem in sessions.items()
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
