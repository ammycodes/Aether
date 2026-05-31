// ==========================================================================
// AETHER PIPELINE MONITOR - WEBSOCKETS COORDINATOR
// ==========================================================================

class SystemMonitor {
    constructor() {
        this.ws = null;
        this.wsUrl = `ws://${window.location.host}/ws/monitor`;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 3000;
        
        this.initializeConnection();
    }

    initializeConnection() {
        console.log(`[Monitor] Opening real-time pipeline on: ${this.wsUrl}`);
        this.ws = new WebSocket(this.wsUrl);

        this.ws.onopen = () => {
            console.log("[Monitor] Real-time WebSocket connection established.");
            this.reconnectAttempts = 0;
            this.appendTerminalLine("runtime", "CONNECTED", "Real-time visual monitoring pipeline established successfully.");
        };

        this.ws.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                this.routeEvent(payload);
            } catch (err) {
                console.error("[Monitor] Failed to parse WebSocket payload:", err);
            }
        };

        this.ws.onclose = () => {
            console.warn("[Monitor] WebSocket connection dropped.");
            this.appendTerminalLine("runtime", "DISCONNECTED", "Connection dropped. Attempting pipeline re-establishment...", true);
            this.attemptReconnect();
        };

        this.ws.onerror = (err) => {
            console.error("[Monitor] Pipeline WebSocket error:", err);
        };
    }

    attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error("[Monitor] Maximum WebSocket reconnect attempts exceeded. Please refresh page.");
            this.appendTerminalLine("runtime", "ERROR", "Connection failure. Max reconnection threshold reached. Manual reload required.", true);
            return;
        }

        this.reconnectAttempts++;
        setTimeout(() => {
            this.initializeConnection();
        }, this.reconnectDelay);
    }

    routeEvent(payload) {
        // Log raw payloads to terminal simulator
        if (payload.type === "log") {
            this.appendTerminalLine(payload.component, payload.level, payload.message, payload.level === "ERROR" || payload.level === "WARNING");
            // Pull new costs on logs to update display instantly
            if (window.aetherDashboard) {
                window.aetherDashboard.loadCosts();
            }
        } 
        
        // Agent Whisper Chat Message
        else if (payload.type === "active_node") {
            this.appendTerminalLine("workflow", "INFO", `Active Agent transition: activating node '${payload.label}' [${payload.agent_id}]`);
            // Highlight node in Canvas
            if (window.aetherCanvas) {
                window.aetherCanvas.highlightNode(payload.node_id);
            }
        } 
        
        // Visual messaging orb sliding animation trigger
        else if (payload.type === "transition") {
            this.appendTerminalLine("workflow", "INFO", `Message packet dispatched: Node '${payload.source_id}' ➔ Node '${payload.target_id}'`);
            
            // Trigger animating orb on SVG path
            if (window.aetherCanvas) {
                window.aetherCanvas.animateTransition(payload.source_id, payload.target_id);
            }
        } 
        
        // Chat events inside monitor view tabs
        else if (payload.type === "channel_message") {
            this.appendChatBubble(payload.channel, payload.sender, payload.content, payload.direction === "out");
        } 
        
        // General workflow execution status
        else if (payload.type === "workflow_status") {
            if (payload.status === "idle" && window.aetherCanvas) {
                window.aetherCanvas.clearHighlights();
            }
        }
    }

    appendTerminalLine(component, level, message, isError = false) {
        const terminal = document.getElementById("terminal-log-stream");
        if (!terminal) return;

        const timestamp = new Date().toLocaleTimeString();
        
        const line = document.createElement("div");
        line.className = "term-line";
        
        const timeSpan = document.createElement("span");
        timeSpan.className = "term-time";
        timeSpan.textContent = `[${timestamp}]`;
        
        const compSpan = document.createElement("span");
        compSpan.className = "term-comp";
        compSpan.textContent = `[${component.toUpperCase()}:${level}]`;
        
        const msgSpan = document.createElement("span");
        msgSpan.className = isError ? "term-msg term-err" : "term-msg";
        msgSpan.textContent = message;
        
        line.appendChild(timeSpan);
        line.appendChild(compSpan);
        line.appendChild(msgSpan);
        
        terminal.appendChild(line);
        
        // Auto scroll
        terminal.scrollTop = terminal.scrollHeight;
        
        // Cap lines at 200 to protect page memory
        while (terminal.children.length > 200) {
            terminal.removeChild(terminal.firstChild);
        }
    }

    appendChatBubble(channel, sender, content, isRight = false) {
        const whispersStream = document.getElementById("whispers-bubbles-stream");
        const telegramStream = document.getElementById("telegram-bubbles-stream");
        
        const stream = channel === "telegram" ? telegramStream : whispersStream;
        if (!stream) return;

        // Clear placeholder if first message
        const placeholder = stream.querySelector(".chat-placeholder");
        if (placeholder) {
            placeholder.style.display = "none";
        }

        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        const bubble = document.createElement("div");
        bubble.className = isRight ? "bubble right" : "bubble left";
        
        const meta = document.createElement("div");
        meta.className = "bubble-meta";
        meta.innerHTML = `<span>${sender}</span><span>${timestamp}</span>`;
        
        const body = document.createElement("div");
        body.className = "bubble-content";
        
        // Strip markdown stars/formatting if clean display is preferred, or display text
        body.textContent = content;
        
        bubble.appendChild(meta);
        bubble.appendChild(body);
        stream.appendChild(bubble);
        
        // Auto scroll
        const container = stream.parentElement;
        container.scrollTop = container.scrollHeight;
    }

    clearChatHistory() {
        const streams = ["whispers-bubbles-stream", "telegram-bubbles-stream"];
        streams.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.innerHTML = `<div class="chat-placeholder"><p>Messages cleared. Launch a workflow to re-initialize logs.</p></div>`;
            }
        });
    }
}

// Hook onto window so it's access-ready
window.addEventListener("DOMContentLoaded", () => {
    window.aetherMonitor = new SystemMonitor();
});
