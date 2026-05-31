// ==========================================================================
// AETHER DASHBOARD COORDINATOR - METRICS & TEMPLATES MANAGER
// ==========================================================================

class DashboardManager {
    constructor() {
        this.initializeEvents();
        this.loadDashboardData();
    }

    initializeEvents() {
        // Trigger run template button bindings
        document.querySelectorAll(".run-template-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const wfId = e.target.getAttribute("data-wf");
                this.loadTemplateToCanvas(wfId);
            });
        });
    }

    async loadDashboardData() {
        await this.loadCosts();
        await this.loadStats();
    }

    async loadCosts() {
        try {
            const response = await fetch("/api/costs");
            if (!response.ok) throw new Error("Failed to load cost logs");
            
            const data = await response.json();
            
            // Update displays
            document.getElementById("total-cost-display").textContent = `$${data.total_cost_usd.toFixed(6)}`;
            document.getElementById("metric-cost").textContent = `$${data.total_cost_usd.toFixed(5)}`;
            document.getElementById("metric-tokens").textContent = data.total_tokens.toLocaleString();

            // Populate Resource breakdown table
            const tableBody = document.getElementById("cost-table-body");
            if (tableBody) {
                tableBody.innerHTML = "";
                
                const breakdown = data.breakdown || {};
                
                if (Object.keys(breakdown).length === 0) {
                    tableBody.innerHTML = `<tr><td colspan="3" class="text-muted text-center">No token consumption logged yet.</td></tr>`;
                    return;
                }

                for (const [agentId, stats] of Object.entries(breakdown)) {
                    const tr = document.createElement("tr");
                    
                    const nameTd = document.createElement("td");
                    nameTd.className = "text-indigo font-bold";
                    nameTd.textContent = agentId.toUpperCase();
                    
                    const tokensTd = document.createElement("td");
                    tokensTd.textContent = stats.tokens.toLocaleString();
                    
                    const costTd = document.createElement("td");
                    costTd.className = "green-text font-bold";
                    costTd.textContent = `$${stats.cost.toFixed(6)}`;
                    
                    tr.appendChild(nameTd);
                    tr.appendChild(tokensTd);
                    tr.appendChild(costTd);
                    tableBody.appendChild(tr);
                }
            }
        } catch (err) {
            console.error("[Dashboard] Error fetching cost logs:", err);
        }
    }

    async loadStats() {
        try {
            // Load agents count
            const agResponse = await fetch("/api/agents");
            if (agResponse.ok) {
                const agents = await agResponse.json();
                document.getElementById("metric-agents").textContent = agents.length;
            }

            // Load message metrics
            const msgResponse = await fetch("/api/messages");
            if (msgResponse.ok) {
                const messages = await msgResponse.json();
                document.getElementById("metric-messages").textContent = messages.length;
            }

            // Load API configuration keys and check bot status
            // If Bot token is filled, we update status badges
            const logsResponse = await fetch("/api/logs");
            if (logsResponse.ok) {
                const logs = await logsResponse.json();
                
                let telegramOnline = false;
                
                // Read through logs to detect bot status
                for (const log of logs) {
                    if (log.message.includes("Telegram long polling worker started")) {
                        telegramOnline = true;
                        break;
                    }
                }
                
                const tgBadge = document.getElementById("tg-status-badge");
                const tgDot = document.getElementById("tg-dot");
                const tgText = document.getElementById("tg-status-text");

                if (telegramOnline) {
                    tgBadge.classList.add("cost-badge"); // Add neon glow
                    tgDot.className = "status-dot green-dot";
                    tgText.textContent = "ONLINE";
                } else {
                    tgBadge.classList.remove("cost-badge");
                    tgDot.className = "status-dot red-dot";
                    tgText.textContent = "OFFLINE";
                }
            }
        } catch (err) {
            console.error("[Dashboard] Error loading system stats:", err);
        }
    }

    async loadTemplateToCanvas(workflowId) {
        try {
            const response = await fetch("/api/workflows");
            if (!response.ok) throw new Error("Failed to load workflows");
            
            const workflows = await response.json();
            const selectedWf = workflows.find(w => w.id === workflowId);
            
            if (!selectedWf) {
                alert(`Template '${workflowId}' not found.`);
                return;
            }

            // Load onto Canvas
            if (window.aetherCanvas) {
                window.aetherCanvas.loadWorkflowGraph(selectedWf);
            }

            // Update loading selectors
            const selectDropdown = document.getElementById("wf-load-dropdown");
            if (selectDropdown) {
                selectDropdown.value = workflowId;
            }

            // Smooth navigate to Orchestrator tab
            const orchestratorTabBtn = document.querySelector('a[data-tab="canvas"]');
            if (orchestratorTabBtn) {
                orchestratorTabBtn.click();
            }
            
            console.log(`[Dashboard] Loaded template into active canvas: ${workflowId}`);
        } catch (err) {
            console.error("[Dashboard] Template loading failed:", err);
        }
    }
}

// Hook startup
window.addEventListener("DOMContentLoaded", () => {
    window.aetherDashboard = new DashboardManager();
});
