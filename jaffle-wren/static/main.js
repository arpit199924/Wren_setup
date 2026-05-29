// --- DOM Elements ---
const queryForm = document.getElementById('query-form');
const queryInput = document.getElementById('query-input');
const submitBtn = document.getElementById('submit-btn');
const chatContainer = document.getElementById('chat-container');
const consoleOutput = document.getElementById('console-output');
const clearConsoleBtn = document.getElementById('clear-console-btn');
const autoscrollChk = document.getElementById('autoscroll-chk');
const filterBtns = document.querySelectorAll('.control-btn[data-filter]');

// --- State Variables ---
let allLogs = [
    { text: "System initialized. Local DuckDB database is active.", level: "system" },
    { text: "Ready to process natural language questions using Gemini.", level: "system" }
];
let activeFilter = 'all';

// --- Initialize Console ---
renderLogs();

// --- Event Listeners ---
queryForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const question = queryInput.value.trim();
    if (!question) return;

    // 1. Add User Message to Chat
    appendMessage(question, 'user');
    queryInput.value = '';
    
    // 2. Add System Log
    addLog(`Initiated agent run for question: "${question}"`, 'system');
    
    // 3. Set UI to Loading State
    setLoading(true);
    const thinkingMessage = appendMessage('Gemini is planning & executing queries', 'agent thinking');

    try {
        // 4. Send API Request
        const response = await fetch('/api/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question })
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Failed to get response from Gemini agent.');
        }

        const data = await response.json();

        // 5. Remove Thinking Placeholder & Render Agent Markdown Response
        thinkingMessage.remove();
        appendMessage(data.output, 'agent');

        // 6. Process and Append Backend Logs
        if (data.logs) {
            parseAndAppendLogs(data.logs);
        }
    } catch (error) {
        thinkingMessage.remove();
        appendMessage(`Failed to execute query: ${error.message}`, 'error');
        addLog(`ERROR: ${error.message}`, 'error');
    } finally {
        setLoading(false);
    }
});

// Clear Console Logs
clearConsoleBtn.addEventListener('click', () => {
    allLogs = [{ text: "Console logs cleared.", level: "system" }];
    renderLogs();
});

// Filter Console Logs
filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.getAttribute('data-filter');
        renderLogs();
    });
});

// --- Helper Functions ---

// Render chat messages
function appendMessage(content, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    if (sender === 'agent thinking') {
        contentDiv.innerHTML = `${content} <span class="loading-dots"><span></span><span></span><span></span></span>`;
    } else if (sender === 'agent') {
        if (typeof marked !== 'undefined') {
            contentDiv.innerHTML = marked.parse(content);
        } else {
            contentDiv.innerHTML = content
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/\n/g, "<br>");
        }
    } else {
        contentDiv.textContent = content;
    }
    
    msgDiv.appendChild(contentDiv);
    chatContainer.appendChild(msgDiv);
    scrollContainer(chatContainer);
    return msgDiv;
}

// Add a single custom system log
function addLog(text, level) {
    const timestamp = new Date().toLocaleTimeString();
    allLogs.push({ text: `${timestamp} | ${level.toUpperCase()} | ${text}`, level });
    renderLogs();
}

// Parse logs block returned from FastAPI backend
function parseAndAppendLogs(logsText) {
    const lines = logsText.split('\n');
    lines.forEach(line => {
        if (!line.trim()) return;
        
        let level = 'info';
        const upperLine = line.toUpperCase();
        
        if (upperLine.includes('| DEBUG |') || upperLine.includes(' DEBUG ') || upperLine.includes('| DEBUG:')) {
            level = 'debug';
        } else if (upperLine.includes('| ERROR |') || upperLine.includes(' ERROR ') || upperLine.includes('ERROR:')) {
            level = 'error';
        } else if (upperLine.includes('| WARNING |') || upperLine.includes(' WARNING ') || upperLine.includes('WARNING:')) {
            level = 'warning';
        }
        
        allLogs.push({ text: line, level });
    });
    renderLogs();
}

// Render the logs according to active filter
function renderLogs() {
    consoleOutput.innerHTML = '';
    
    const filteredLogs = allLogs.filter(log => {
        if (activeFilter === 'all') return true;
        return log.level === activeFilter;
    });
    
    filteredLogs.forEach(log => {
        const span = document.createElement('span');
        span.className = `log-line ${log.level}`;
        span.textContent = log.text;
        consoleOutput.appendChild(span);
    });
    
    scrollContainer(consoleOutput);
}

// Scroll console and chat containers
function scrollContainer(container) {
    if (autoscrollChk.checked) {
        container.scrollTop = container.scrollHeight;
    }
}

// Handle loading state in form elements
function setLoading(isLoading) {
    queryInput.disabled = isLoading;
    submitBtn.disabled = isLoading;
    if (isLoading) {
        submitBtn.style.opacity = '0.6';
        submitBtn.style.cursor = 'not-allowed';
    } else {
        submitBtn.style.opacity = '1';
        submitBtn.style.cursor = 'pointer';
    }
}
