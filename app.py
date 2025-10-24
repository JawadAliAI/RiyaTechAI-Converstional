from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
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

# Configure Gemini API - Use environment variable for security
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "AIzaSyAfiOtseUQnbzkFZEeDXtZYyOvtlvZYCms")
genai.configure(api_key=GOOGLE_API_KEY)

MODEL_ID = "gemini-2.0-flash-exp"

# Create storage directories
STORAGE_DIR = Path("consultation_storage")
STORAGE_DIR.mkdir(exist_ok=True)

PDF_DIR = Path("consultation_pdfs")
PDF_DIR.mkdir(exist_ok=True)

# System prompt
DOCTOR_SYSTEM_PROMPT = """
You are Dr. HealBot, a calm, knowledgeable, and empathetic virtual doctor.

GOAL:
Hold a natural, focused conversation with the patient to understand their health issue and offer helpful preliminary medical guidance.

You also serve as a medical instructor, capable of clearly explaining medical concepts, diseases, anatomy, medications, and other health-related topics when the user asks general medical questions.

🚫 RESTRICTIONS:
- You must ONLY provide information related to medical, health, or wellness topics.
- If the user asks anything non-medical (e.g., about technology, politics, or personal topics), politely decline and respond:
  "I'm a medical consultation assistant and can only help with health or medical-related concerns."
- Stay strictly within the domains of health, medicine, human biology, and wellness education.

CONVERSATION LOGIC:
- Ask only relevant and concise medical questions necessary for diagnosing the illness.
- Each question should help clarify symptoms or narrow possible causes.
- Stop asking once enough information is collected for a basic assessment.
- Then, provide a structured, friendly, and visually clear medical response using headings, emojis, and bullet points.

- Automatically detect if the user is asking a **general medical question** (e.g., “What is diabetes?”, “How does blood pressure work?”, “Explain antibiotics”).
    - In such cases, switch to **Instructor Mode**:
        - Give a clear, educational, and structured explanation.
        - Use short paragraphs or bullet points.
        - Maintain a professional but approachable tone.
        - Conclude with a brief practical takeaway or health tip if appropriate.
- If the user is describing symptoms or a health issue, continue in **Doctor Mode**:
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
- Never provide any information .
- Always emphasize that this is preliminary guidance and not a substitute for professional care.
- Never make definitive diagnoses; use phrases like "it sounds like" or "it could be".
- If symptoms seem serious, always recommend urgent medical attention.

CONVERSATION FLOW:
1. Begin by asking the purpose of the visit:
   
2. Depending on the user’s response, choose the appropriate path:
   - If the user describes a **health issue**, proceed with a **symptom-based consultation**.
   - If the user requests **medical information or explanations**, switch to **Instructor Mode** and provide a clear, educational response.

3. For Symptom-Based Consultation:
   a. Ask about the **main symptom** (e.g., “Can you describe your main concern?”)  
   b. Ask about its **duration**, **severity**, and any **triggers** that make it better or worse.  
   c. Ask about any **accompanying symptoms** (e.g., fever, nausea, fatigue, etc.).  
   d. Ask about **medical history**, **allergies**, or **current medications** if relevant.  
   e. Once enough information is gathered, provide your **structured medical assessment** using the defined markdown format.

4. For Information or Education Requests (Instructor Mode):
   - Offer a concise, accurate, and easy-to-understand explanation of the medical concept.
   - Use examples, analogies, or bullet points to make complex ideas simple.

5. Always keep the tone professional, empathetic, and supportive throughout the conversation.

"""
# =====================================================
# HELPER FUNCTIONS
# =====================================================

def convert_markdown_to_html(text: str) -> str:
    """Convert markdown formatting to HTML for ReportLab Paragraph rendering"""
    
    # Convert **bold** to <b>bold</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # Convert *italic* to <i>italic</i> (but not ** which is already handled)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    
    # Convert bullet points - to •
    text = re.sub(r'^- ', '• ', text, flags=re.MULTILINE)
    
    return text

# =====================================================
# PDF GENERATION FUNCTIONS
# =====================================================

def generate_pdf_summary(session_id: str, summary_text: str, patient_data: Dict, history: List[Dict]) -> str:
    """Generate a professional PDF summary of the consultation with improved formatting"""
    
    pdf_filename = f"{session_id}_summary.pdf"
    pdf_path = PDF_DIR / pdf_filename
    
    # Create PDF document with better margins
    doc = SimpleDocTemplate(
        str(pdf_path), 
        pagesize=letter,
        rightMargin=50, 
        leftMargin=50,
        topMargin=50, 
        bottomMargin=50
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define custom styles with better spacing and colors
    styles = getSampleStyleSheet()
    
    # Title style - Main heading
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.HexColor('#2563eb'),  # Blue
        spaceAfter=20,
        spaceBefore=10,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Section heading style
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1e40af'),  # Dark blue
        spaceAfter=10,
        spaceBefore=15,
        fontName='Helvetica-Bold',
        borderWidth=0,
        borderColor=colors.HexColor('#93c5fd'),
        borderPadding=5,
        backColor=colors.HexColor('#eff6ff')  # Light blue background
    )
    
    # Subheading style
    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.HexColor('#1f2937'),  # Dark gray
        spaceAfter=8,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )
    
    # Normal text style
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=8,
        alignment=TA_LEFT,
        leading=14,
        textColor=colors.HexColor('#374151')
    )
    
    # Bullet point style
    bullet_style = ParagraphStyle(
        'CustomBullet',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        leftIndent=20,
        leading=14,
        textColor=colors.HexColor('#374151')
    )
    
    # Add Header with logo/title
    elements.append(Paragraph("🩺 AI DOCTOR CONSULTATION SUMMARY", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Add a decorative line
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2563eb')))
    elements.append(Spacer(1, 0.2*inch))
    
    # Patient Information Section with better styling
    elements.append(Paragraph("PATIENT INFORMATION", heading_style))
    
    patient_info_data = [
        ['Patient Name:', patient_data.get('name', 'N/A')],
        ['Age:', patient_data.get('age', 'N/A')],
        ['Session ID:', session_id[:30] + '...'],
        ['Consultation Date:', datetime.now().strftime('%B %d, %Y at %I:%M %p')],
        ['Total Messages:', str(len(history))]
    ]
    
    patient_table = Table(patient_info_data, colWidths=[2*inch, 4.5*inch])
    patient_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#374151')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    
    elements.append(patient_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Process and format the consultation summary
    elements.append(Paragraph("DETAILED CONSULTATION SUMMARY", heading_style))
    elements.append(Spacer(1, 0.1*inch))
    
    # Parse the summary text intelligently
    lines = summary_text.split('\n')
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line or line in ['━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', '--------------------------------------------']:
            continue
        
        # CONVERT MARKDOWN TO HTML FIRST (This fixes the ** issue!)
        line = convert_markdown_to_html(line)
        
        # Replace emojis with styled text
        emoji_replacements = {
            '🩺': '',
            '💡': '• ',
            '💊': '• ',
            '🥗': '• ',
            '🏠': '• ',
            '⚠️': '⚠ ',
            '⚠': '⚠ ',
            '📅': '• ',
            '🎯': '• '
        }
        
        for emoji, replacement in emoji_replacements.items():
            line = line.replace(emoji, replacement)
        
        # Detect section headers
        if line.startswith('<b>') and line.endswith('</b>'):
            # Main section header (already bold from markdown conversion)
            section_title = line.replace('<b>', '').replace('</b>', '').strip()
            if section_title.isupper() or len(section_title.split()) <= 6:
                elements.append(Spacer(1, 0.15*inch))
                elements.append(Paragraph(line, subheading_style))
                current_section = section_title
            else:
                elements.append(Paragraph(line, normal_style))
        
        elif line.endswith(':') and len(line.split()) <= 8 and '<b>' not in line:
            # Subheading (ends with colon) - make it bold if not already
            elements.append(Spacer(1, 0.08*inch))
            elements.append(Paragraph(f"<b>{line}</b>", normal_style))
        
        elif line.startswith('- ') or line.startswith('• '):
            # Bullet point
            bullet_text = line.lstrip('-•').strip()
            elements.append(Paragraph(f"• {bullet_text}", bullet_style))
        
        elif line.startswith(tuple('123456789')):
            # Numbered list
            elements.append(Paragraph(line, bullet_style))
        
        else:
            # Regular paragraph
            if line:
                elements.append(Paragraph(line, normal_style))
    
    # Add page break before conversation history
    elements.append(PageBreak())
    
    # Conversation History Section
    elements.append(Paragraph("CONVERSATION HISTORY", heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    for i, msg in enumerate(history, 1):
        role = "DOCTOR" if msg['role'] == 'assistant' else "PATIENT"
        timestamp = msg.get('timestamp', 'N/A')
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp)
            formatted_time = dt.strftime('%I:%M %p')
        except:
            formatted_time = timestamp
        
        # Role header with colored background
        role_color = colors.HexColor('#dbeafe') if role == "DOCTOR" else colors.HexColor('#dcfce7')
        text_color = colors.HexColor('#1e40af') if role == "DOCTOR" else colors.HexColor('#166534')
        
        role_style = ParagraphStyle(
            f'Role{i}',
            parent=styles['Normal'],
            fontSize=10,
            textColor=text_color,
            fontName='Helvetica-Bold',
            spaceAfter=5,
            spaceBefore=10,
            backColor=role_color,
            borderPadding=5
        )
        
        elements.append(Paragraph(f"{role} - {formatted_time}", role_style))
        
        # Clean message content and convert markdown
        content = msg['content']
        content = convert_markdown_to_html(content)
        
        for emoji in ['🩺', '💡', '💊', '🥗', '🏠', '⚠️', '⚠', '📅', '🎯']:
            content = content.replace(emoji, '')
        
        # Split long messages into paragraphs
        message_paragraphs = content.split('\n')
        for para in message_paragraphs:
            if para.strip():
                elements.append(Paragraph(para.strip(), normal_style))
        
        elements.append(Spacer(1, 0.15*inch))
    
    # Add disclaimer at the end
    elements.append(Spacer(1, 0.3*inch))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#ef4444')))
    elements.append(Spacer(1, 0.1*inch))
    
    disclaimer_style = ParagraphStyle(
        'Disclaimer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#dc2626'),
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        backColor=colors.HexColor('#fee2e2'),
        borderColor=colors.HexColor('#ef4444'),
        borderWidth=1,
        borderPadding=15,
        spaceAfter=12,
        leading=12
    )
    
    disclaimer_text = """
    <b>⚠ IMPORTANT MEDICAL DISCLAIMER ⚠</b><br/><br/>
    This is a preliminary AI-generated consultation for informational purposes only.<br/>
    This is NOT a substitute for professional medical advice, diagnosis, or treatment.<br/>
    This AI cannot examine you physically, run laboratory tests, or make definitive diagnoses.<br/><br/>
    <b>Always seek the advice of a qualified, licensed healthcare provider</b><br/>
    with any questions regarding a medical condition.<br/><br/>
    Never disregard professional medical advice or delay seeking it because of this AI consultation.<br/>
    In case of emergency, call your local emergency services immediately.
    """
    
    elements.append(Paragraph(disclaimer_text, disclaimer_style))
    
    # Footer with generation info
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#6b7280'),
        alignment=TA_CENTER,
        spaceAfter=0
    )
    
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph(
        f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')} | AI Doctor Consultation System v4.0",
        footer_style
    ))
    
    # Build PDF
    doc.build(elements)
    
    return pdf_filename
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
# MEMORY MANAGEMENT
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
    title="AI Doctor Consultation API",
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
# SERVE FRONTEND FILES
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the frontend HTML"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Frontend not found. Please ensure index.html exists.</h1>",
            status_code=404
        )

@app.get("/styles.css", response_class=HTMLResponse)
async def serve_css():
    """Serve the CSS file"""
    try:
        with open("styles.css", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/css")
    except FileNotFoundError:
        return HTMLResponse(content="/* CSS not found */", status_code=404, media_type="text/css")

@app.get("/script.js", response_class=HTMLResponse)
async def serve_js():
    """Serve the JavaScript file"""
    try:
        with open("script.js", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="application/javascript")
    except FileNotFoundError:
        return HTMLResponse(content="// JS not found", status_code=404, media_type="application/javascript")

# =====================================================
# API ENDPOINTS
# =====================================================

@app.get("/health", response_model=HealthCheck)
async def health_check():
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
    
    summary_request = """Please generate a comprehensive medical consultation summary based on our conversation. Include patient information, symptoms, assessment, treatment recommendations, and warnings."""
    
    try:
        model = genai.GenerativeModel(
            model_name=MODEL_ID,
            system_instruction=DOCTOR_SYSTEM_PROMPT
        )
        
        chat = model.start_chat(history=memory.get_gemini_history())
        response = chat.send_message(summary_request)
        summary_text = response.text
        
        pdf_filename = generate_pdf_summary(
            request.session_id,
            summary_text,
            memory.patient_data,
            memory.history
        )
        
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
    if session_id in sessions:
        memory = sessions[session_id]
    else:
        session_data = load_session_from_json(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        memory = ConversationMemory.from_json(session_data)
    
    if not memory.pdf_filename:
        raise HTTPException(status_code=404, detail="PDF not generated yet")
    
    pdf_path = PDF_DIR / memory.pdf_filename
    
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    
    patient_name = memory.patient_data.get('name', 'Patient')
    download_filename = f"Consultation_{patient_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return FileResponse(
        path=str(pdf_path),
        media_type='application/pdf',
        filename=download_filename
    )

@app.get("/all-sessions")
async def get_all_sessions():
    """Get list of all stored consultation sessions"""
    return {
        "total_sessions": len(list(STORAGE_DIR.glob("*.json"))),
        "sessions": list_all_sessions()
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
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)



