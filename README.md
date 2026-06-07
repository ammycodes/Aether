# Aether - AI Agent Orchestration Platform

A state-of-the-art **AI Agent Orchestration Platform** built for the  AI Engineer Hiring Challenge. Aether enables users to visually design collaborative multi-agent workflows, configures their personalities, authorized tools, and memory parameters, and triggers them via manual triggers or **live Telegram messaging channels**.

Aether runs **completely locally** out-of-the-box using a single setup command, and features an **intelligent Offline/Hybrid Mode** that allows full testing of the visual transitions, feedback loops, tool actions, and Telegram bots without requiring API keys.

---

## 🏛️ System Architecture

Aether is designed with clear boundary separation between the **Web UI Presentation Layer**, **FastAPI Backend Server & Pipeline coordinator**, and **SQLite Database relational engine**.

```mermaid
graph TD
    subgraph Frontend [Presentation Layer (Web UI - Glassmorphic SPA)]
        A[Dashboard & Metrics Ticker]
        B[SVG Workflow Canvas Editor]
        C[Live Console Chat & scrolling Terminal]
    end

    subgraph Backend [FastAPI Application Engine]
        D[FastAPI REST API Routes]
        E[WebSockets Broadcaster]
        F[Telegram Long Polling Worker]
        G[Workflow Graph Parser]
    end

    subgraph Runtime [Aether Agent Engine]
        H[Agent ReAct Executor]
        I[Real Tools: search_web, fetch_url, calculator, write_file, read_file]
    end

    subgraph Persistence [Relational Persistence Layer]
        J[(SQLite Database - agents.db)]
    end

    %% Communications
    A & B & C <-->|REST / WebSockets| D & E
    F -->|Triggers Async Workflow| G
    G -->|Activates Nodes| H
    H -->|Executes ReAct Loops| I
    H & G -->|Persists logs, costs & history| J
    D -->|Queries / Mutations| J
    E <-->|Broadcasts system logs & node orbs| B & C
```

---

## ⚡ Architectural Decisions & Justifications

### 1. Unified Backend Runtimes (Python 3.12 + FastAPI)
- **Justification**: Python has rich libraries for LLM integration (`google-generativeai`, `openai`). FastAPI provides outstanding speed, native async integration (ideal for long polling and asynchronous graph orchestration), and built-in support for **WebSockets** to stream live console events instantly.

### 2. Aether Custom Agent Engine ("Aether Runtime")
- **Justification**: Rather than importing heavy external frameworks like LangGraph or CrewAI which add dependency bloat, a custom **ReAct (Reasoning and Action)** execution loop was written from scratch in `app/runtime/agent.py`. It manages:
  - Iterative tool parsing using robust regex pattern matchers.
  - Safe mathematical evaluation, Wikipedia text scraping, and isolated file reads/writes in a secure `workspace_storage` subdirectory.
  - Persistent SQLite-backed memory buffers per dialogue thread.
  - **Intelligent Offline Fallback**: A rule-based LLM simulator that parses tool requests, feeds back observations, and constructs logical outputs so the hiring panel can run and audit the platform immediately with *zero setup configuration or credentials*.

### 3. SVG Drag-and-Drop Node Builder (Vanilla JS)
- **Justification**: To present a stunning dashboard without Node.js/npm on the evaluator's system, a customized, high-fidelity SVG editor was coded in pure JavaScript. It supports:
  - Dragging agents from a sidebar toolbox onto a grid coordinate.
  - Clicking-and-dragging ports to draw **cubic bezier curve connections**.
  - **Micro-Animations**: Real-time WebSocket transition signals trigger glowing circular "message packets" that glide smoothly along the bezier lines via native SVG `<animateMotion>` before landing on target nodes!

### 4. Zero-Tunnel Telegram Integration (Long Polling)
- **Justification**: Telegram bots typically require webhooks and public HTTPS tunnels (like `ngrok`), which are tedious to run and configure. Aether utilizes an asynchronous **Long Polling loop** running inside a FastAPI background task. This allows the local server to receive messages directly from Telegram from anywhere in the world with **zero public webhook setup**.

---

## 🚀 One-Command Quickstart

Aether is designed to run locally using a single startup script:

### Step 1: Clone and launch
Open a terminal in the root workspace directory and run:
```bash
python run.py
```
This utility will automatically:
1. Scan and install all package requirements via `pip install -r requirements.txt`.
2. Bootstrap the database and populate default agent profiles and visual templates.
3. Launch the `uvicorn` development server on `http://127.0.0.1:8000`.

### Step 2: Open Dashboard
Open your web browser and navigate to:
```
http://127.0.0.1:8000
```
Interactions on the SVG Canvas, triggering content templates, and editing agent specifications will immediately begin logging raw threads in the scrolling terminal simulator and streaming chat dialogues.

---

## 🤖 Live Messaging Channel Configuration (Optional)

To connect an agent to a real conversational messaging thread:

1. Open your Telegram application, search for `@BotFather`, and create a new bot by sending `/newbot`.
2. Copy the **HTTP API Token** provided.
3. Open the `.env` file in the project folder and paste the token:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   ```
4. Restart the server (`python run.py`). You will see a log line: `[Telegram Bot] Telegram long polling worker started successfully. Bot is ONLINE.`
5. Send a message to your bot handle on Telegram (e.g. *"What is the standard plan billing structure?"*).
6. Watch the Aether Web UI instantly switch to the console tab, animate the classification node transitions, execute tools, and reply back to your phone chat!

---

## 🎨 Creative Customizations

### 1. Adding a new Pre-Built Workflow Template
Workflow templates are seeded in `app/database.py` inside the `init_db()` method:
1. Instantiate a new `WorkflowModel(id="template_key", name="Display Name", description="...")`.
2. Add node cards as `WorkflowNodeModel` (assign agent IDs and visual grid coordinates).
3. Connect them via `WorkflowEdgeModel`, declaring trigger conditions. E.g.:
   ```python
   WorkflowEdgeModel(
       id="edge_id",
       workflow_id="template_key",
       source_node_id="node_a",
       target_node_id="node_b",
       condition=json.dumps({
           "type": "operator",
           "field": "last_response",
           "operator": "contains",
           "value": "CRITICAL"
       })
   )
   ```

### 2. Adding a New External Messaging Channel (e.g. Slack Bot)
To integrate an additional external messaging pipeline:
1. Create a worker file in `app/runtime/slack_bot.py`.
2. Implement a standard polling handler using Slack's `socket_mode` or a background listener loop.
3. When a message is received, save it to `MessageModel` and invoke `WorkflowRunner`:
   ```python
   runner = WorkflowRunner("template_support_gateway")
   response = await runner.execute(slack_message_text, session_id=f"slack_{channel_id}")
   # Reply response back to Slack
   ```
4. Hook the startup and shutdown lifecycles inside `app/main.py`.
