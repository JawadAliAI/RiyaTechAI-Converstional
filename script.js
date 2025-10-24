// API Configuration - Use current origin for deployed environment
const API_URL = window.location.origin;
let sessionId = null;
let patientData = {};
let currentPdfUrl = null;

// Voice recognition variables
let recognition = null;
let isRecording = false;
let autoSpeak = false;
let currentUtterance = null;
let isSpeaking = false;
let continuousMode = false;

// Initialize Speech Recognition
function initSpeechRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        recognition.onstart = function() {
            isRecording = true;
            document.getElementById('voiceBtn').classList.add('recording');
            document.getElementById('voiceInputBtn').classList.add('active');
            updateVoiceStatus('🎤 Listening... Speak now');
            
            // Stop any ongoing speech when user starts speaking
            if (isSpeaking) {
                stopSpeaking();
            }
        };

        recognition.onresult = function(event) {
            const transcript = event.results[0][0].transcript;
            document.getElementById('messageInput').value = transcript;
            updateVoiceStatus('✓ Voice input received: "' + transcript + '"');
            
            // In continuous mode, automatically send the message
            if (continuousMode) {
                setTimeout(() => {
                    sendMessage();
                }, 500);
            } else {
                setTimeout(() => hideVoiceStatus(), 2000);
            }
        };

        recognition.onerror = function(event) {
            console.error('Speech recognition error:', event.error);
            
            // Don't show error for 'aborted' or 'no-speech' in continuous mode
            if (continuousMode && (event.error === 'aborted' || event.error === 'no-speech')) {
                console.log('Speech recognition ended normally');
            } else {
                updateVoiceStatus('❌ Error: ' + event.error, 'error');
            }
            
            stopRecording();
            
            // Restart listening in continuous mode if it wasn't a user abort
            if (continuousMode && event.error !== 'aborted' && event.error !== 'no-speech') {
                setTimeout(() => {
                    if (continuousMode && !isSpeaking) {
                        startListening();
                    }
                }, 1000);
            }
        };

        recognition.onend = function() {
            stopRecording();
            
            // Restart listening in continuous mode after a brief pause
            if (continuousMode && !isSpeaking) {
                setTimeout(() => {
                    if (continuousMode) {
                        startListening();
                    }
                }, 500);
            }
        };
    } else {
        showNotification('Voice recognition not supported in this browser', 'error');
    }
}

function startListening() {
    if (!recognition) {
        initSpeechRecognition();
    }
    
    // Don't start listening if AI is currently speaking
    if (isSpeaking) {
        console.log('Waiting for AI to finish speaking...');
        return;
    }
    
    if (!isRecording) {
        try {
            recognition.start();
        } catch (e) {
            console.error('Error starting recognition:', e);
        }
    }
}

function toggleVoiceInput() {
    if (!recognition) {
        initSpeechRecognition();
    }

    if (isRecording) {
        recognition.stop();
    } else {
        startListening();
    }
}

function stopRecording() {
    isRecording = false;
    document.getElementById('voiceBtn').classList.remove('recording');
    document.getElementById('voiceInputBtn').classList.remove('active');
}

function updateVoiceStatus(message, type = 'info') {
    const status = document.getElementById('voiceStatus');
    status.textContent = message;
    status.className = 'voice-status active';
    if (type === 'error') {
        status.style.background = '#ffebee';
        status.style.color = '#c62828';
    } else {
        status.style.background = '#e3f2fd';
        status.style.color = '#1565c0';
    }
}

function hideVoiceStatus() {
    document.getElementById('voiceStatus').classList.remove('active');
}

// Text-to-Speech functions
function speakText(text) {
    if (!('speechSynthesis' in window)) {
        console.error('Speech synthesis not supported');
        showNotification('Text-to-speech not supported in this browser', 'error');
        return;
    }

    if (isSpeaking) {
        window.speechSynthesis.cancel();
    }
    
    // Stop voice recognition while AI is speaking to prevent feedback loop
    if (isRecording) {
        recognition.stop();
        updateVoiceStatus('🔇 Voice input paused while AI speaks...');
    }

    let cleanText = text
        .replace(/🩺|💡|💊|🥗|⚠️|⚠|📅|🎯|📊|🛡️|🏃|👤/g, '')
        .replace(/━+/g, '')
        .replace(/\*\*/g, '')
        .replace(/\n{3,}/g, '\n\n');

    currentUtterance = new SpeechSynthesisUtterance(cleanText);
    currentUtterance.rate = 0.85;
    currentUtterance.pitch = 1.1;
    currentUtterance.volume = 1;
    currentUtterance.lang = 'en-US';

    const voices = window.speechSynthesis.getVoices();
    
    if (voices.length > 0) {
        const preferredVoice = voices.find(voice => 
            (voice.lang.includes('en-US') || voice.lang.includes('en-GB')) &&
            (voice.name.includes('Female') || 
             voice.name.includes('Samantha') ||
             voice.name.includes('Victoria') ||
             voice.name.includes('Google') ||
             voice.name.includes('Microsoft'))
        ) || voices.find(voice => voice.lang.includes('en')) || voices[0];
        
        currentUtterance.voice = preferredVoice;
    }

    currentUtterance.onstart = function() {
        isSpeaking = true;
        updateVoiceStatus('🔊 AI is speaking... Voice input paused');
    };

    currentUtterance.onend = function() {
        isSpeaking = false;
        
        // In continuous mode, start listening again after doctor finishes speaking
        if (continuousMode) {
            setTimeout(() => {
                if (continuousMode && !isRecording) {
                    updateVoiceStatus('🎤 Ready to listen again...');
                    startListening();
                }
            }, 800); // Slightly longer delay to ensure clean transition
        } else {
            hideVoiceStatus();
        }
    };

    currentUtterance.onerror = function(event) {
        console.error('Speech synthesis error:', event);
        isSpeaking = false;
        if (event.error !== 'interrupted') {
            showNotification('Speech error: ' + event.error, 'error');
        }
        
        // Resume listening in continuous mode even if there was an error
        if (continuousMode && !isRecording) {
            setTimeout(() => {
                startListening();
            }, 1000);
        }
    };

    setTimeout(() => {
        window.speechSynthesis.speak(currentUtterance);
    }, 100);
}

function stopSpeaking() {
    window.speechSynthesis.cancel();
    isSpeaking = false;
}

function toggleAutoSpeak() {
    autoSpeak = !autoSpeak;
    const indicator = document.getElementById('speakIndicator');
    const text = document.getElementById('autoSpeakText');
    
    if (autoSpeak) {
        indicator.style.background = '#4CAF50';
        text.textContent = '🔊 Auto-Speak: ON';
        showNotification('Auto-speak enabled - Doctor responses will be spoken', 'success');
    } else {
        indicator.style.background = '#999';
        text.textContent = '🔊 Auto-Speak: OFF';
        stopSpeaking();
        showNotification('Auto-speak disabled', 'info');
    }
}

function toggleContinuousMode() {
    continuousMode = !continuousMode;
    const btn = document.getElementById('continuousModeBtn');
    
    if (continuousMode) {
        btn.classList.add('active');
        btn.innerHTML = '<span class="voice-indicator recording"></span><span>🔄 Continuous: ON</span>';
        
        // Enable auto-speak if not already enabled
        if (!autoSpeak) {
            autoSpeak = true;
            const indicator = document.getElementById('speakIndicator');
            const text = document.getElementById('autoSpeakText');
            indicator.style.background = '#4CAF50';
            text.textContent = '🔊 Auto-Speak: ON';
        }
        
        showNotification('Continuous conversation mode enabled! Speak naturally.', 'success');
        startListening();
    } else {
        btn.classList.remove('active');
        btn.innerHTML = '<span class="voice-indicator"></span><span>🔄 Continuous: OFF</span>';
        showNotification('Continuous mode disabled', 'info');
        if (isRecording) {
            recognition.stop();
        }
        stopSpeaking();
    }
}

window.onload = async () => {
    await startNewSession();
    initSpeechRecognition();
    
    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = function() {
            window.speechSynthesis.getVoices();
        };
    }
};

async function startNewSession() {
    try {
        const response = await fetch(`${API_URL}/start-session`, {
            method: 'POST'
        });
        const data = await response.json();
        sessionId = data.session_id;
        
        updateSessionInfo();
        addMessage('doctor', data.message);
        
        if (autoSpeak) {
            speakText(data.message);
        }
        
        showNotification('New consultation started!', 'success');
    } catch (error) {
        console.error('Error starting session:', error);
        showNotification('Failed to connect to server', 'error');
    }
}

function updateSessionInfo() {
    const info = document.getElementById('sessionInfo');
    const patientInfo = patientData.name ? `Patient: ${patientData.name}` : 'New Patient';
    info.innerHTML = `${patientInfo}`;
    
    const sessionDisplay = document.getElementById('sessionIdDisplay');
    sessionDisplay.textContent = `Session ID: ${sessionId} (Click to copy)`;
}

function copySessionId() {
    navigator.clipboard.writeText(sessionId).then(() => {
        showNotification('Session ID copied to clipboard!', 'success');
    }).catch(() => {
        showNotification('Failed to copy Session ID', 'error');
    });
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return;

    addMessage('user', message);
    input.value = '';
    showLoading(true);

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });

        const data = await response.json();
        sessionId = data.session_id;
        patientData = data.patient_data;
        updateSessionInfo();
        addMessage('doctor', data.response);
        
        if (autoSpeak || continuousMode) {
            speakText(data.response);
        }
    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('doctor', '❌ Sorry, there was an error. Please try again.');
    } finally {
        showLoading(false);
    }
}

function addMessage(type, text) {
    const container = document.getElementById('chatContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = text;
    
    if (type === 'doctor' && 'speechSynthesis' in window) {
        const speakerIcon = document.createElement('span');
        speakerIcon.className = 'speaker-icon';
        speakerIcon.innerHTML = '🔊';
        speakerIcon.title = 'Click to hear this message';
        speakerIcon.onclick = function() {
            if (isSpeaking) {
                stopSpeaking();
                speakerIcon.classList.remove('speaking');
            } else {
                speakText(text);
                speakerIcon.classList.add('speaking');
                setTimeout(() => speakerIcon.classList.remove('speaking'), 3000);
            }
        };
        contentDiv.appendChild(speakerIcon);
    }
    
    messageDiv.appendChild(contentDiv);
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
}

function showLoading(show) {
    const loading = document.getElementById('loading');
    loading.className = show ? 'loading active' : 'loading';
}

async function generateSummary() {
    if (!sessionId) {
        showNotification('No active session', 'error');
        return;
    }

    showLoading(true);
    showNotification('Generating comprehensive detailed summary and PDF... This may take 30-60 seconds', 'success');

    try {
        const response = await fetch(`${API_URL}/summary`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        });

        const data = await response.json();
        
        currentPdfUrl = `${API_URL}${data.pdf_url}`;
        document.getElementById('summaryText').textContent = data.summary;
        document.getElementById('pdfDownloadInfo').style.display = 'block';
        document.getElementById('downloadPdfBtn').style.display = 'inline-block';
        document.getElementById('viewPdfBtn').style.display = 'inline-block';
        document.getElementById('summaryModal').classList.add('active');
        
        showNotification('Comprehensive summary and professional PDF generated successfully!', 'success');
    } catch (error) {
        console.error('Error generating summary:', error);
        showNotification('Failed to generate summary. Please try again.', 'error');
    } finally {
        showLoading(false);
    }
}

function downloadPDF() {
    if (!currentPdfUrl) {
        showNotification('No PDF available', 'error');
        return;
    }

    const link = document.createElement('a');
    link.href = currentPdfUrl;
    link.download = `Consultation_Summary_${sessionId.substring(0, 8)}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showNotification('PDF download started!', 'success');
}

function togglePDFViewer() {
    const viewerContainer = document.getElementById('pdfViewerContainer');
    const viewer = document.getElementById('pdfViewer');
    const btn = document.getElementById('viewPdfBtn');
    
    if (viewerContainer.style.display === 'none') {
        viewer.src = currentPdfUrl;
        viewerContainer.style.display = 'block';
        btn.textContent = '🙈 Hide PDF';
    } else {
        viewerContainer.style.display = 'none';
        btn.textContent = '👁️ View PDF';
    }
}

function closeSummary() {
    document.getElementById('summaryModal').classList.remove('active');
    document.getElementById('pdfViewerContainer').style.display = 'none';
    document.getElementById('viewPdfBtn').textContent = '👁️ View PDF';
}

async function showHistoryModal() {
    document.getElementById('historyModal').classList.add('active');
    await loadHistoryList();
}

function closeHistory() {
    document.getElementById('historyModal').classList.remove('active');
}

async function loadHistoryList() {
    const historyList = document.getElementById('historyList');
    historyList.innerHTML = '<p style="text-align: center; color: #999;">Loading...</p>';

    try {
        const response = await fetch(`${API_URL}/all-sessions`);
        const data = await response.json();

        if (data.sessions.length === 0) {
            historyList.innerHTML = '<p style="text-align: center; color: #999;">No previous consultations found</p>';
            return;
        }

        historyList.innerHTML = '';
        data.sessions.forEach(session => {
            const item = document.createElement('div');
            item.className = 'history-item';
            item.onclick = () => loadSession(session.session_id);
            
            const date = new Date(session.last_updated).toLocaleString();
            const pdfBadge = session.has_pdf ? '<span class="pdf-badge">📄 PDF Available</span>' : '';
            
            item.innerHTML = `
                <h4>👤 ${session.patient_name} ${pdfBadge}</h4>
                <p>📅 ${date}</p>
                <p>💬 Messages: ${session.message_count}</p>
                <p style="font-family: monospace; font-size: 0.8em;">🔑 ${session.session_id.substring(0, 20)}...</p>
            `;
            historyList.appendChild(item);
        });
    } catch (error) {
        console.error('Error loading history:', error);
        historyList.innerHTML = '<p style="text-align: center; color: #dc3545;">Failed to load history</p>';
    }
}

async function loadSessionById() {
    const input = document.getElementById('sessionIdInput');
    const id = input.value.trim();
    
    if (!id) {
        showNotification('Please enter a Session ID', 'error');
        return;
    }

    await loadSession(id);
}

async function loadSession(id) {
    showLoading(true);
    closeHistory();

    try {
        const response = await fetch(`${API_URL}/load-session/${id}`);
        
        if (!response.ok) {
            throw new Error('Session not found');
        }

        const data = await response.json();
        
        stopSpeaking();
        
        document.getElementById('chatContainer').innerHTML = '';
        
        sessionId = data.session_id;
        patientData = data.patient_data;
        updateSessionInfo();

        data.history.forEach(msg => {
            addMessage(msg.role === 'user' ? 'user' : 'doctor', msg.content);
        });

        if (data.has_pdf && data.pdf_url) {
            currentPdfUrl = `${API_URL}${data.pdf_url}`;
        }

        showNotification('Consultation loaded successfully!', 'success');
    } catch (error) {
        console.error('Error loading session:', error);
        showNotification('Failed to load session. Check the ID and try again.', 'error');
    } finally {
        showLoading(false);
    }
}

async function restartSession() {
    if (!confirm('Are you sure you want to start a new consultation? Current session will be saved.')) {
        return;
    }

    // Disable continuous mode when restarting
    if (continuousMode) {
        toggleContinuousMode();
    }

    stopSpeaking();
    document.getElementById('chatContainer').innerHTML = '';
    patientData = {};
    currentPdfUrl = null;
    await startNewSession();
}

function showNotification(message, type) {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type} active`;
    
    setTimeout(() => {
        notification.classList.remove('active');
    }, 3000);
}

document.getElementById('messageInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

document.getElementById('sessionIdInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        loadSessionById();
    }
});

window.addEventListener('beforeunload', () => {
    stopSpeaking();
    if (continuousMode && recognition) {
        recognition.stop();
    }
});
