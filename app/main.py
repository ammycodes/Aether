import os
import json
import asyncio
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.config import settings
from app.database import (
    init_db, get_db, AgentModel, WorkflowModel, WorkflowNodeModel, 
    WorkflowEdgeModel, LogModel, MessageModel, CostTrackerModel
)
from app.runtime.agent import AgentRunner
from app.runtime.workflow import WorkflowRunner, WEBSOCKET_BROADCASTERS, broadcast_ws
from app.runtime.telegram_bot import telegram_worker

# Create FastAPI app
app = FastAPI(title="Aether Agent Orchestration Platform")

# Mount Static Files (Frontend UI files served from app/static)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)

# ----------------- FastAPI Lifecycle Events -----------------

@app.on_event("startup")
async def startup_event():
    # Initialize SQLite Database & populate templates
    init_db()
    
    # Register WebSocket broadcast sender
    WEBSOCKET_BROADCASTERS.append(broadcast_payload)
    
    # Start Telegram Listener bot in background thread/task
    telegram_worker.start()

@app.on_event("shutdown")
def shutdown_event():
    # Stop Telegram Listener bot
    telegram_worker.stop()
    if broadcast_payload in WEBSOCKET_BROADCASTERS:
        WEBSOCKET_BROADCASTERS.remove(broadcast_payload)

# ----------------- WebSocket Live Stream Coordinator -----------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS Manager] Browser client connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"[WS Manager] Browser client disconnected. Active: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection might be stale
                pass

manager = ConnectionManager()

async def broadcast_payload(payload: dict):
    """Callback passed to Aether Runtime to transmit logs/transitions live to the UI."""
    await manager.broadcast(payload)

@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Keep connection open, wait for client signals
        while True:
            data = await websocket.receive_text()
            # Handle client ping/pongs or manual commands if needed
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ----------------- API Pydantic Schemas -----------------

class AgentCreate(BaseModel):
    id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    name: str
    role: str
    system_prompt: str
    model: str = "gemini-2.5-flash"
    tools: list[str] = []
    memory_type: str = "buffer"
    schedules: list[dict] = []
    rules: list[str] = []

class WorkflowNodeCreate(BaseModel):
    id: str
    agent_id: str | None = None
    label: str | None = None
    pos_x: float
    pos_y: float
    config: dict = {}

class WorkflowEdgeCreate(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    condition: dict = {}

class WorkflowCreate(BaseModel):
    id: str
    name: str
    description: str | None = None
    nodes: list[WorkflowNodeCreate] = []
    edges: list[WorkflowEdgeCreate] = []

class WorkflowRunRequest(BaseModel):
    input: str

# ----------------- REST API Endpoints -----------------

# 1. Agent CRUD
@app.get("/api/agents")
def get_agents(db: Session = Depends(get_db)):
    agents = db.query(AgentModel).all()
    # Decode stringified fields
    results = []
    for a in agents:
        results.append({
            "id": a.id,
            "name": a.name,
            "role": a.role,
            "system_prompt": a.system_prompt,
            "model": a.model,
            "tools": json.loads(a.tools),
            "memory_type": a.memory_type,
            "schedules": json.loads(a.schedules),
            "rules": json.loads(a.rules),
            "created_at": a.created_at.isoformat()
        })
    return results

@app.post("/api/agents")
def create_agent(agent: AgentCreate, db: Session = Depends(get_db)):
    existing = db.query(AgentModel).filter(AgentModel.id == agent.id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Agent with ID '{agent.id}' already exists.")
    
    new_agent = AgentModel(
        id=agent.id,
        name=agent.name,
        role=agent.role,
        system_prompt=agent.system_prompt,
        model=agent.model,
        tools=json.dumps(agent.tools),
        memory_type=agent.memory_type,
        schedules=json.dumps(agent.schedules),
        rules=json.dumps(agent.rules)
    )
    db.add(new_agent)
    db.commit()
    return {"status": "success", "agent_id": agent.id}

@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: str, agent: AgentCreate, db: Session = Depends(get_db)):
    db_agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    db_agent.name = agent.name
    db_agent.role = agent.role
    db_agent.system_prompt = agent.system_prompt
    db_agent.model = agent.model
    db_agent.tools = json.dumps(agent.tools)
    db_agent.memory_type = agent.memory_type
    db_agent.schedules = json.dumps(agent.schedules)
    db_agent.rules = json.dumps(agent.rules)
    
    db.commit()
    return {"status": "success"}

@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    db_agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    db.delete(db_agent)
    db.commit()
    return {"status": "success"}

# 2. Workflow CRUD
@app.get("/api/workflows")
def get_workflows(db: Session = Depends(get_db)):
    workflows = db.query(WorkflowModel).all()
    results = []
    for w in workflows:
        nodes = []
        for n in w.nodes:
            nodes.append({
                "id": n.id,
                "agent_id": n.agent_id,
                "label": n.label,
                "pos_x": n.pos_x,
                "pos_y": n.pos_y,
                "config": json.loads(n.config) if n.config else {}
            })
            
        edges = []
        for e in w.edges:
            edges.append({
                "id": e.id,
                "source_node_id": e.source_node_id,
                "target_node_id": e.target_node_id,
                "condition": json.loads(e.condition) if e.condition else {}
            })
            
        results.append({
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "is_template": w.is_template,
            "created_at": w.created_at.isoformat(),
            "nodes": nodes,
            "edges": edges
        })
    return results

@app.post("/api/workflows")
def create_workflow(wf: WorkflowCreate, db: Session = Depends(get_db)):
    # Delete existing workflow with same ID to overwrite cleanly
    existing = db.query(WorkflowModel).filter(WorkflowModel.id == wf.id).first()
    if existing:
        db.delete(existing)
        db.commit()
        
    new_wf = WorkflowModel(
        id=wf.id,
        name=wf.name,
        description=wf.description,
        is_template=False
    )
    db.add(new_wf)
    db.commit()
    
    for n in wf.nodes:
        db_node = WorkflowNodeModel(
            id=n.id,
            workflow_id=wf.id,
            agent_id=n.agent_id,
            label=n.label,
            pos_x=n.pos_x,
            pos_y=n.pos_y,
            config=json.dumps(n.config)
        )
        db.add(db_node)
        
    for e in wf.edges:
        db_edge = WorkflowEdgeModel(
            id=e.id,
            workflow_id=wf.id,
            source_node_id=e.source_node_id,
            target_node_id=e.target_node_id,
            condition=json.dumps(e.condition)
        )
        db.add(db_edge)
        
    db.commit()
    return {"status": "success", "workflow_id": wf.id}

@app.delete("/api/workflows/{workflow_id}")
def delete_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    db.delete(wf)
    db.commit()
    return {"status": "success"}

# 3. Trigger Workflow Execution
@app.post("/api/workflows/{workflow_id}/run")
def run_workflow(workflow_id: str, req: WorkflowRunRequest, bg_tasks: BackgroundTasks):
    async def async_run():
        try:
            runner = WorkflowRunner(workflow_id)
            await runner.execute(req.input)
            runner.close()
        except Exception as e:
            print(f"[Workflow Exec Error] Running workflow {workflow_id} failed: {e}")
            
    # Fire off in background immediately
    bg_tasks.add_task(async_run)
    return {"status": "queued", "workflow_id": workflow_id}

# 4. Logs and Monitoring analytics
@app.get("/api/logs")
def get_logs(limit: int = 100, db: Session = Depends(get_db)):
    logs = db.query(LogModel).order_by(LogModel.timestamp.desc()).limit(limit).all()
    return [{
        "id": l.id,
        "level": l.level,
        "message": l.message,
        "component": l.component,
        "workflow_id": l.workflow_id,
        "timestamp": l.timestamp.isoformat()
    } for l in logs]

@app.get("/api/messages")
def get_messages(limit: int = 50, db: Session = Depends(get_db)):
    messages = db.query(MessageModel).order_by(MessageModel.timestamp.desc()).limit(limit).all()
    # Reverse to read chronologically
    messages.reverse()
    return [{
        "id": m.id,
        "sender_type": m.sender_type,
        "sender_id": m.sender_id,
        "recipient_type": m.recipient_type,
        "recipient_id": m.recipient_id,
        "content": m.content,
        "status": m.status,
        "timestamp": m.timestamp.isoformat()
    } for m in messages]

@app.get("/api/costs")
def get_costs(db: Session = Depends(get_db)):
    costs = db.query(CostTrackerModel).all()
    total_cost = sum(c.cost_usd for c in costs)
    total_tokens = sum(c.prompt_tokens + c.completion_tokens for c in costs)
    
    # Calculate costs per agent
    agent_costs = {}
    for c in costs:
        if c.agent_id not in agent_costs:
            agent_costs[c.agent_id] = {"cost": 0.0, "tokens": 0}
        agent_costs[c.agent_id]["cost"] += c.cost_usd
        agent_costs[c.agent_id]["tokens"] += (c.prompt_tokens + c.completion_tokens)
        
    return {
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
        "breakdown": agent_costs
    }

# ----------------- Serves Static Web Dashboard -----------------

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# Fallback mounts for static folder serving
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
