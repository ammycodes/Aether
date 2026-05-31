// ==========================================================================
// AETHER MAIN APPLICATION CONTROLLER - HUB & FORMS BINDER
// ==========================================================================

class AppController {
    constructor() {
        this.activeTab = "dashboard";
        
        // Modal refs
        this.runModal = document.getElementById("run-wf-modal");
        
        this.initializeNavigation();
        this.initializeAgentHub();
        this.initializeWorkflowActions();
        
        // Initial loaders
        this.loadAgents();
        this.loadWorkflowsList();
    }

    initializeNavigation() {
        const navItems = document.querySelectorAll(".nav-item");
        
        navItems.forEach(item => {
            item.addEventListener("click", (e) => {
                e.preventDefault();
                
                // Remove active classes
                navItems.forEach(n => n.classList.remove("active"));
                
                // Add active to current
                const link = e.currentTarget;
                link.classList.add("active");
                
                const targetTab = link.getAttribute("data-tab");
                this.switchTab(targetTab);
            });
        });
    }

    switchTab(tabId) {
        this.activeTab = tabId;
        
        // Hide all contents
        document.querySelectorAll(".tab-content").forEach(content => {
            content.classList.remove("active");
        });
        
        // Show target
        const activeContent = document.getElementById(`tab-${tabId}`);
        if (activeContent) activeContent.classList.add("active");

        // Update headers dynamically
        const pageTitle = document.getElementById("page-title");
        const pageSubtitle = document.getElementById("page-subtitle");

        if (tabId === "dashboard") {
            pageTitle.textContent = "Dashboard Overview";
            pageSubtitle.textContent = "Real-time metrics and overall runtime statistics.";
            if (window.aetherDashboard) window.aetherDashboard.loadDashboardData();
        } else if (tabId === "agents") {
            pageTitle.textContent = "Agent Configuration Hub";
            pageSubtitle.textContent = "Assemble custom agents, adjust system instructions, and assign tools.";
            this.loadAgents();
        } else if (tabId === "canvas") {
            pageTitle.textContent = "Visual Graph Orchestrator";
            pageSubtitle.textContent = "Design visual graphs, specify conditions, and monitor inter-agent message packages.";
            this.loadAgents(); // Reload agents list in toolbox
            this.loadWorkflowsList();
        } else if (tabId === "console") {
            pageTitle.textContent = "Live Console Streaming";
            pageSubtitle.textContent = "Real-time system events, log sequences, and inter-agent dialogues.";
            this.loadHistoricalLogs();
        }
    }

    // ==========================================================================
    // AGENT HUB CRUD CONTROLLERS
    // ==========================================================================

    initializeAgentHub() {
        const form = document.getElementById("agent-form");
        const resetBtn = document.getElementById("btn-reset-agent-form");

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await this.saveAgent();
        });

        resetBtn.addEventListener("click", () => {
            this.resetAgentForm();
        });
    }

    async loadAgents() {
        try {
            const response = await fetch("/api/agents");
            if (!response.ok) throw new Error("Failed to load active agents registry.");
            
            const agents = await response.json();
            
            // 1. Populate Agents Registry Hub list
            const registry = document.getElementById("agents-registry-list");
            if (registry) {
                registry.innerHTML = "";
                
                if (agents.length === 0) {
                    registry.innerHTML = `<div class="chat-placeholder"><p>No agents currently registered. Populate the form to create your first autonomous unit.</p></div>`;
                }

                agents.forEach(agent => {
                    const card = document.createElement("div");
                    card.className = "agent-card glass-interactive";
                    
                    const toolsBadges = agent.tools.map(t => `<span class="tool-tag">${t}</span>`).join(" ");
                    
                    card.innerHTML = `
                        <div class="agent-card-header">
                            <h3>${agent.name}</h3>
                            <span class="model-badge">${agent.model}</span>
                        </div>
                        <div class="role">${agent.role}</div>
                        <div class="system-prompt-excerpt" title="${agent.system_prompt}">${agent.system_prompt}</div>
                        <div class="agent-card-tools">
                            ${toolsBadges || '<span class="tool-tag text-muted">No Tools</span>'}
                        </div>
                        <div class="agent-card-actions">
                            <button class="btn btn-sm btn-secondary btn-edit-agent" data-id="${agent.id}">Configure</button>
                            <button class="btn btn-sm btn-secondary btn-delete-agent text-red" data-id="${agent.id}">Decommission</button>
                        </div>
                    `;

                    // Action buttons
                    card.querySelector(".btn-edit-agent").addEventListener("click", () => this.editAgent(agent));
                    card.querySelector(".btn-delete-agent").addEventListener("click", () => this.deleteAgent(agent.id));
                    
                    registry.appendChild(card);
                });
            }

            // 2. Populate drag and drop Toolbox in canvas
            const toolboxList = document.getElementById("toolbox-agents-list");
            if (toolboxList) {
                toolboxList.innerHTML = "";
                
                agents.forEach(agent => {
                    const badge = document.createElement("div");
                    badge.className = "toolbox-item";
                    badge.setAttribute("draggable", "true");
                    
                    badge.innerHTML = `
                        <h5>${agent.name}</h5>
                        <span>${agent.role.slice(0, 20)}...</span>
                    `;

                    badge.addEventListener("dragstart", (e) => {
                        e.dataTransfer.setData("application/json", JSON.stringify(agent));
                    });

                    toolboxList.appendChild(badge);
                });
            }
        } catch (err) {
            console.error("[App] Loading agents registry failed:", err);
        }
    }

    async saveAgent() {
        const agentId = document.getElementById("agent-id").value.trim();
        const name = document.getElementById("agent-name").value.trim();
        const role = document.getElementById("agent-role").value.trim();
        const systemPrompt = document.getElementById("agent-prompt").value.trim();
        const model = document.getElementById("agent-model").value;
        const memoryType = document.getElementById("agent-memory").value;

        // Extract checked tools
        const tools = [];
        document.querySelectorAll('input[name="agent-tools"]:checked').forEach(cb => {
            tools.push(cb.value);
        });

        const payload = {
            id: agentId,
            name: name,
            role: role,
            system_prompt: systemPrompt,
            model: model,
            tools: tools,
            memory_type: memoryType,
            schedules: [],
            rules: []
        };

        const isEdit = document.getElementById("agent-id").disabled;
        const url = isEdit ? `/api/agents/${agentId}` : "/api/agents";
        const method = isEdit ? "PUT" : "POST";

        try {
            const response = await fetch(url, {
                method: method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || "Database save error.");
            }

            this.resetAgentForm();
            await this.loadAgents();
            
            console.log(`[App] Agent '${name}' saved successfully.`);
        } catch (err) {
            alert(`Error saving agent: ${err.message}`);
        }
    }

    editAgent(agent) {
        document.getElementById("agent-form-title").textContent = `Configure: ${agent.name}`;
        
        const idInput = document.getElementById("agent-id");
        idInput.value = agent.id;
        idInput.disabled = true; // Lock key during edit

        document.getElementById("agent-name").value = agent.name;
        document.getElementById("agent-role").value = agent.role;
        document.getElementById("agent-prompt").value = agent.system_prompt;
        document.getElementById("agent-model").value = agent.model;
        document.getElementById("agent-memory").value = agent.memory_type;

        // Uncheck all first
        document.querySelectorAll('input[name="agent-tools"]').forEach(cb => {
            cb.checked = agent.tools.includes(cb.value);
        });

        // Focus form tab panel scroll
        document.querySelector(".form-panel").scrollTop = 0;
    }

    async deleteAgent(agentId) {
        if (!confirm("Decommissioning this agent removes them permanently from the server registry. Proceed?")) return;

        try {
            const response = await fetch(`/api/agents/${agentId}`, { method: "DELETE" });
            if (!response.ok) throw new Error("Decommissioning failed.");
            
            await this.loadAgents();
            console.log(`[App] Decommissioned agent ID: ${agentId}`);
        } catch (err) {
            alert(err.message);
        }
    }

    resetAgentForm() {
        document.getElementById("agent-form-title").textContent = "Create New Agent";
        
        const idInput = document.getElementById("agent-id");
        idInput.value = "";
        idInput.disabled = false;

        document.getElementById("agent-name").value = "";
        document.getElementById("agent-role").value = "";
        document.getElementById("agent-prompt").value = "";
        document.getElementById("agent-model").value = "gemini-2.5-flash";
        document.getElementById("agent-memory").value = "buffer";

        document.querySelectorAll('input[name="agent-tools"]').forEach(cb => {
            cb.checked = false;
        });
    }

    // ==========================================================================
    // ORCHESTRATOR WORKFLOW BINDINGS
    // ==========================================================================

    initializeWorkflowActions() {
        // Clear canvas
        document.getElementById("btn-clear-canvas").addEventListener("click", () => {
            if (window.aetherCanvas && confirm("Wipe workspace design canvas?")) {
                window.aetherCanvas.clearCanvas();
            }
        });

        // Trigger Run modal openers
        document.getElementById("btn-open-run-wf-modal").addEventListener("click", () => {
            const selectWf = document.getElementById("wf-load-dropdown").value;
            if (!selectWf) {
                alert("Please build or select an active workflow from dropdown first.");
                return;
            }
            this.runModal.classList.add("active");
        });

        document.getElementById("btn-close-run-wf-modal").addEventListener("click", () => {
            this.runModal.classList.remove("active");
        });

        // Save customized layout
        document.getElementById("btn-save-workflow").addEventListener("click", async () => {
            if (!window.aetherCanvas) return;

            const graph = window.aetherCanvas.exportWorkflowData();
            if (graph.nodes.length === 0) {
                alert("Canvas is empty. Drag agents from toolbox to assemble.");
                return;
            }

            const name = prompt("Enter a name for this custom workflow:", "My Custom Orchestration");
            if (!name) return;

            const id = prompt("Enter a unique URL slug for this workflow (alphanumeric):", "custom_run_" + Date.now().toString().slice(-6));
            if (!id) return;

            const payload = {
                id: id.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
                name: name,
                description: "User assembled workflow network.",
                nodes: graph.nodes,
                edges: graph.edges
            };

            try {
                const response = await fetch("/api/workflows", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error("Saving custom graph failed.");
                
                await this.loadWorkflowsList();
                alert("Workflow graph assembled and saved in SQLite catalog successfully!");
            } catch (err) {
                alert(err.message);
            }
        });

        // Trigger action run
        document.getElementById("btn-execute-wf").addEventListener("click", async () => {
            const wfId = document.getElementById("wf-load-dropdown").value;
            const inputVal = document.getElementById("wf-run-input").value.trim();

            if (!inputVal) {
                alert("Instruction body cannot be empty.");
                return;
            }

            // Close modal
            this.runModal.classList.remove("active");

            // Redirect UI view to Scrolling console panel immediately!
            const consoleTabBtn = document.querySelector('a[data-tab="console"]');
            if (consoleTabBtn) {
                consoleTabBtn.click();
            }

            // Trigger API
            try {
                if (window.aetherMonitor) {
                    window.aetherMonitor.clearChatHistory();
                    window.aetherMonitor.appendTerminalLine("workflow", "INFO", `Triggering API execution on workflow: ${wfId}`);
                }

                const response = await fetch(`/api/workflows/${wfId}/run`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ input: inputVal })
                });

                if (!response.ok) throw new Error("Execution pipeline launch failed.");
                
                console.log(`[App] Workflow execute successfully sent to API.`);
            } catch (err) {
                alert(err.message);
            }
        });

        // Load dropdown change bindings
        const selectDropdown = document.getElementById("wf-load-dropdown");
        selectDropdown.addEventListener("change", async (e) => {
            const wfId = e.target.value;
            if (!wfId) return;

            try {
                const response = await fetch("/api/workflows");
                const wfs = await response.json();
                const selected = wfs.find(w => w.id === wfId);
                
                if (selected && window.aetherCanvas) {
                    window.aetherCanvas.loadWorkflowGraph(selected);
                }
            } catch (err) {
                console.error("[App] Dropping active workflow graph fail:", err);
            }
        });
    }

    async loadWorkflowsList() {
        try {
            const response = await fetch("/api/workflows");
            if (!response.ok) throw new Error("Failed to load workflows.");
            
            const wfs = await response.json();
            const selectDropdown = document.getElementById("wf-load-dropdown");
            
            if (selectDropdown) {
                const currentVal = selectDropdown.value;
                selectDropdown.innerHTML = "";
                
                wfs.forEach(wf => {
                    const opt = document.createElement("option");
                    opt.value = wf.id;
                    opt.textContent = `${wf.name} (${wf.nodes.length} Nodes)`;
                    selectDropdown.appendChild(opt);
                });

                // Restore focus selection if exists
                if (currentVal && wfs.find(w => w.id === currentVal)) {
                    selectDropdown.value = currentVal;
                } else if (wfs.length > 0) {
                    // Set default to first workflow template and draw it
                    selectDropdown.value = wfs[0].id;
                    if (window.aetherCanvas && Object.keys(window.aetherCanvas.nodes).length === 0) {
                        window.aetherCanvas.loadWorkflowGraph(wfs[0]);
                    }
                }
            }
        } catch (err) {
            console.error("[App] Error loading workflow catalog list:", err);
        }
    }

    // ==========================================================================
    // CONSOLE EVENTS LOGGER PULLER
    // ==========================================================================

    async loadHistoricalLogs() {
        try {
            // Load logs in terminal simulator
            const logsResponse = await fetch("/api/logs");
            if (logsResponse.ok && window.aetherMonitor) {
                const logs = await logsResponse.json();
                // Clear and print back chronologically
                const terminal = document.getElementById("terminal-log-stream");
                if (terminal) terminal.innerHTML = "";
                
                logs.reverse().forEach(log => {
                    // Approximate formatted time
                    const t = new Date(log.timestamp).toLocaleTimeString();
                    window.aetherMonitor.appendTerminalLine(log.component, log.level, log.message, log.level === "ERROR" || log.level === "WARNING");
                });
            }

            // Load historical chat bubbles
            const msgResponse = await fetch("/api/messages");
            if (msgResponse.ok && window.aetherMonitor) {
                const messages = await msgResponse.json();
                
                const whispersStream = document.getElementById("whispers-bubbles-stream");
                const telegramStream = document.getElementById("telegram-bubbles-stream");
                
                if (whispersStream) whispersStream.innerHTML = "";
                if (telegramStream) telegramStream.innerHTML = "";

                messages.forEach(msg => {
                    const directionOut = msg.sender_type === "agent";
                    if (msg.sender_type === "channel" || msg.recipient_type === "channel") {
                        const sender = msg.sender_type === "channel" ? "Telegram User" : "Supervisor Approved";
                        window.aetherMonitor.appendChatBubble("telegram", sender, msg.content, directionOut);
                    } else {
                        const sender = msg.sender_type === "agent" ? msg.sender_id.toUpperCase() : "CLIENT QUERY";
                        window.aetherMonitor.appendChatBubble("whispers", sender, msg.content, directionOut);
                    }
                });
            }
        } catch (err) {
            console.error("[App] Historical pull failed:", err);
        }
    }

    // Clear dev logs terminal
    initializeTerminalActions() {
        document.getElementById("btn-clear-terminal").addEventListener("click", () => {
            const terminal = document.getElementById("terminal-log-stream");
            if (terminal) terminal.innerHTML = `<div class="term-line"><span class="term-time">[System]</span><span class="term-comp">[CONSOLE]</span><span class="term-msg">Workspace logger terminal buffer cleared.</span></div>`;
        });
    }
}

// Instantiate
window.addEventListener("DOMContentLoaded", () => {
    window.aetherApp = new AppController();
    window.aetherApp.initializeTerminalActions();
});
