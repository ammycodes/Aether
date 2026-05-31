// ==========================================================================
// AETHER SVG CANVAS EDITOR - DRAG & BUILD ORCHESTRATION GRAPH
// ==========================================================================

class WorkflowCanvas {
    constructor() {
        this.nodes = {}; // Mapping of node_id -> nodeObject
        this.edges = []; // List of edgeObjects { id, source, target, condition }
        this.selectedPort = null; // Track clicked port for drawing a line { node_id, type }
        this.draggedNode = null; // Active dragged node ID
        this.dragOffset = { x: 0, y: 0 };
        
        // DOM refs
        this.canvasWrapper = document.getElementById("svg-canvas-wrapper");
        this.svg = document.getElementById("workflow-svg");
        this.overlay = document.getElementById("nodes-overlay");
        
        this.tempLine = null; // Temporary line SVG element when dragging link
        
        this.initializeEvents();
    }

    initializeEvents() {
        // Drag and drop from toolbox
        this.canvasWrapper.addEventListener("dragover", (e) => e.preventDefault());
        this.canvasWrapper.addEventListener("drop", (e) => this.handleToolboxDrop(e));

        // SVG Canvas click to clear selected port/link drawing
        this.svg.addEventListener("click", (e) => {
            if (e.target === this.svg) {
                this.cancelLinkDrawing();
            }
        });

        // Mousemove on canvas to draw active link line
        this.svg.addEventListener("mousemove", (e) => {
            if (this.selectedPort) {
                this.drawTempLine(e);
            }
        });

        // Global mouse move and mouse up for dragging node elements
        document.addEventListener("mousemove", (e) => this.handleNodeDrag(e));
        document.addEventListener("mouseup", () => this.stopNodeDrag());
    }

    handleToolboxDrop(e) {
        e.preventDefault();
        const agentDataJson = e.dataTransfer.getData("application/json");
        if (!agentDataJson) return;

        try {
            const agent = JSON.parse(agentDataJson);
            
            // Calculate absolute coordinate over canvas wrapper
            const rect = this.canvasWrapper.getBoundingClientRect();
            const posX = e.clientX - rect.left - 110; // Offset node half width
            const posY = e.clientY - rect.top - 40;

            const nodeId = `node_${Date.now()}`;
            this.addNode({
                id: nodeId,
                agent_id: agent.id,
                label: agent.name,
                pos_x: posX,
                pos_y: posY,
                config: {}
            });
        } catch (err) {
            console.error("[Canvas] Drop processing failed:", err);
        }
    }

    addNode(config) {
        const node = {
            id: config.id,
            agent_id: config.agent_id,
            label: config.label,
            x: config.pos_x,
            y: config.pos_y,
            config: config.config || {}
        };

        // Create DOM element overlay card
        const card = document.createElement("div");
        card.id = node.id;
        card.className = "workflow-node glass";
        card.style.left = `${node.x}px`;
        card.style.top = `${node.y}px`;

        card.innerHTML = `
            <div class="node-header">
                <h4>${node.label}</h4>
                <span class="node-remove" title="Delete Node">×</span>
            </div>
            <div class="node-body">
                <span class="role-badge">Agent: ${node.agent_id}</span>
            </div>
            <!-- Ports for connection links -->
            <div class="node-port port-input" data-port="input"></div>
            <div class="node-port port-output" data-port="output"></div>
        `;

        // Attach event listeners
        card.addEventListener("mousedown", (e) => this.startNodeDrag(node.id, e));
        
        // Port connect event
        const inputPort = card.querySelector(".port-input");
        const outputPort = card.querySelector(".port-output");
        
        outputPort.addEventListener("click", (e) => {
            e.stopPropagation();
            this.startLinkDrawing(node.id);
        });

        inputPort.addEventListener("click", (e) => {
            e.stopPropagation();
            this.completeLinkDrawing(node.id);
        });

        // Delete button event
        card.querySelector(".node-remove").addEventListener("click", (e) => {
            e.stopPropagation();
            this.deleteNode(node.id);
        });

        this.overlay.appendChild(card);
        node.element = card;
        
        this.nodes[node.id] = node;
        console.log(`[Canvas] Added node: ${node.id}`);
    }

    startNodeDrag(nodeId, e) {
        // Prevent drag on ports or delete button
        if (e.target.classList.contains("node-port") || e.target.classList.contains("node-remove")) {
            return;
        }
        this.draggedNode = nodeId;
        const node = this.nodes[nodeId];
        
        // Calculate click offset inside card
        this.dragOffset.x = e.clientX - node.x;
        this.dragOffset.y = e.clientY - node.y;
    }

    handleNodeDrag(e) {
        if (!this.draggedNode) return;
        
        const node = this.nodes[this.draggedNode];
        const rect = this.canvasWrapper.getBoundingClientRect();
        
        // Calculate new boundary positions
        let newX = e.clientX - this.dragOffset.x;
        let newY = e.clientY - this.dragOffset.y;
        
        // Boundary bounds clamp
        newX = Math.max(0, Math.min(rect.width - 220, newX));
        newY = Math.max(0, Math.min(rect.height - 100, newY));

        node.x = newX;
        node.y = newY;
        
        node.element.style.left = `${newX}px`;
        node.element.style.top = `${newY}px`;
        
        // Update connection paths
        this.redrawEdges();
    }

    stopNodeDrag() {
        this.draggedNode = null;
    }

    deleteNode(nodeId) {
        // 1. Remove DOM element
        const node = this.nodes[nodeId];
        if (node && node.element) {
            this.overlay.removeChild(node.element);
        }
        
        // 2. Clear from dictionary
        delete this.nodes[nodeId];

        // 3. Clear linked edges
        this.edges = this.edges.filter(edge => {
            if (edge.source === nodeId || edge.target === nodeId) {
                // Delete path element
                if (edge.pathElement && edge.pathElement.parentNode) {
                    this.svg.removeChild(edge.pathElement);
                }
                return false;
            }
            return true;
        });

        this.redrawEdges();
    }

    // ==========================================================================
    // PATH CONNECTION COORDINATION METHODS
    // ==========================================================================

    startLinkDrawing(nodeId) {
        this.selectedPort = { node_id: nodeId, type: "output" };
        
        // Spawn temporary line
        this.tempLine = document.createElementNS("http://www.w3.org/2000/svg", "path");
        this.tempLine.setAttribute("class", "connection-path");
        this.tempLine.setAttribute("stroke-dasharray", "4 4");
        this.svg.appendChild(this.tempLine);
    }

    drawTempLine(e) {
        if (!this.tempLine) return;
        
        const rect = this.canvasWrapper.getBoundingClientRect();
        const mX = e.clientX - rect.left;
        const mY = e.clientY - rect.top;
        
        // Origin port coordinates
        const sourceNode = this.nodes[this.selectedPort.node_id];
        const startX = sourceNode.x + 220; // Output port position (right edge)
        const startY = sourceNode.y + 50;  // Centered vertically

        // Draw bezier path curves to mouse
        const dx = Math.abs(startX - mX) * 0.4;
        const dStr = `M ${startX} ${startY} C ${startX + dx} ${startY}, ${mX - dx} ${mY}, ${mX} ${mY}`;
        
        this.tempLine.setAttribute("d", dStr);
    }

    completeLinkDrawing(targetNodeId) {
        if (!this.selectedPort || this.selectedPort.node_id === targetNodeId) {
            this.cancelLinkDrawing();
            return;
        }

        const edgeId = `edge_${Date.now()}`;
        const sourceNodeId = this.selectedPort.node_id;

        // Check if edge already exists to prevent duplicate lines
        const duplicate = this.edges.find(e => e.source === sourceNodeId && e.target === targetNodeId);
        if (duplicate) {
            this.cancelLinkDrawing();
            return;
        }

        // Create permanent SVG path
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("class", "connection-path");
        path.setAttribute("id", edgeId);
        path.setAttribute("marker-end", "url(#arrow)");
        
        this.svg.appendChild(path);

        this.edges.push({
            id: edgeId,
            source: sourceNodeId,
            target: targetNodeId,
            condition: { type: "always" },
            pathElement: path
        });

        this.cancelLinkDrawing();
        this.redrawEdges();
    }

    cancelLinkDrawing() {
        if (this.tempLine) {
            this.svg.removeChild(this.tempLine);
            this.tempLine = null;
        }
        this.selectedPort = null;
    }

    redrawEdges() {
        this.edges.forEach(edge => {
            const source = this.nodes[edge.source];
            const target = this.nodes[edge.target];
            
            if (!source || !target) return;

            // Output port coordinates (right side of source)
            const sX = source.x + 220;
            const sY = source.y + 50;

            // Input port coordinates (left side of target)
            const tX = target.x;
            const tY = target.y + 50;

            // Draw clean cubic bezier path
            const dx = Math.abs(sX - tX) * 0.4;
            const dStr = `M ${sX} ${sY} C ${sX + dx} ${sY}, ${tX - dx} ${tY}, ${tX} ${tY}`;
            
            edge.pathElement.setAttribute("d", dStr);
        });
    }

    // ==========================================================================
    // REAL-TIME ANIMATED EXECUTIONS & HIGHLIGHTS
    // ==========================================================================

    highlightNode(nodeId) {
        this.clearHighlights();
        const node = this.nodes[nodeId];
        if (node && node.element) {
            node.element.classList.add("active-run");
            
            // Auto scroll container center to focus active node
            this.canvasWrapper.scrollTo({
                left: node.x - this.canvasWrapper.clientWidth / 2 + 110,
                top: node.y - this.canvasWrapper.clientHeight / 2 + 50,
                behavior: "smooth"
            });
        }
    }

    clearHighlights() {
        Object.values(this.nodes).forEach(node => {
            if (node.element) {
                node.element.classList.remove("active-run");
            }
        });
    }

    animateTransition(sourceId, targetId) {
        // Locate edge
        const edge = this.edges.find(e => e.source === sourceId && e.target === targetId);
        if (!edge) return;

        const pathData = edge.pathElement.getAttribute("d");
        if (!pathData) return;

        // Spawn a glowing message orb circle
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("r", "6");
        circle.setAttribute("class", "message-packet");

        // Motion element
        const motion = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
        motion.setAttribute("dur", "2.2s");
        motion.setAttribute("repeatCount", "1");
        motion.setAttribute("fill", "freeze");
        motion.setAttribute("path", pathData);

        circle.appendChild(motion);
        this.svg.appendChild(circle);

        // Delete from DOM after animation completes
        setTimeout(() => {
            if (circle.parentNode) {
                this.svg.removeChild(circle);
            }
        }, 2250);
    }

    // Load structured workflow layout from DB JSON
    loadWorkflowGraph(workflowData) {
        this.clearCanvas();

        const nodes = workflowData.nodes || [];
        const edges = workflowData.edges || [];

        // 1. Spawning nodes
        nodes.forEach(node => {
            this.addNode(node);
        });

        // 2. Spawning edges
        edges.forEach(edge => {
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("class", "connection-path");
            path.setAttribute("id", edge.id);
            path.setAttribute("marker-end", "url(#arrow)");
            this.svg.appendChild(path);

            this.edges.push({
                id: edge.id,
                source: edge.source_node_id,
                target: edge.target_node_id,
                condition: edge.condition || { type: "always" },
                pathElement: path
            });
        });

        this.redrawEdges();
        console.log(`[Canvas] Loaded workflow graph: ${workflowData.name}`);
    }

    clearCanvas() {
        // 1. Delete node DOM overlays
        this.overlay.innerHTML = "";
        this.nodes = {};

        // 2. Delete SVG edge paths
        this.edges.forEach(edge => {
            if (edge.pathElement && edge.pathElement.parentNode) {
                this.svg.removeChild(edge.pathElement);
            }
        });
        this.edges = [];
        
        // Remove trailing animated orbs
        const packets = this.svg.querySelectorAll(".message-packet");
        packets.forEach(p => this.svg.removeChild(p));
    }

    exportWorkflowData() {
        const nodesData = Object.values(this.nodes).map(n => ({
            id: n.id,
            agent_id: n.agent_id,
            label: n.label,
            pos_x: n.x,
            pos_y: n.y,
            config: n.config
        }));

        const edgesData = this.edges.map(e => ({
            id: e.id,
            source_node_id: e.source,
            target_node_id: e.target,
            condition: e.condition
        }));

        return {
            nodes: nodesData,
            edges: edgesData
        };
    }
}

// Instantiate on startup
window.addEventListener("DOMContentLoaded", () => {
    window.aetherCanvas = new WorkflowCanvas();
});
