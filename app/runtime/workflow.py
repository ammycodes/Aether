import json
import asyncio
from sqlalchemy.orm import Session
from app.database import SessionLocal, WorkflowModel, WorkflowNodeModel, WorkflowEdgeModel, LogModel, MessageModel
from app.runtime.agent import AgentRunner

# Global registry for active websocket connections to broadcast real-time runs
# We will append connection handlers here from main.py
WEBSOCKET_BROADCASTERS = []

async def broadcast_ws(payload: dict):
    """Utility to safely broadcast real-time events to all connected UI clients."""
    for broadcaster in WEBSOCKET_BROADCASTERS:
        try:
            await broadcaster(payload)
        except Exception as e:
            print(f"[WS Broadcast Error] Failed to send update: {e}")

class NodeData:
    def __init__(self, id, agent_id, label, pos_x, pos_y, config):
        self.id = id
        self.agent_id = agent_id
        self.label = label
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.config = config

class EdgeData:
    def __init__(self, id, source_node_id, target_node_id, condition):
        self.id = id
        self.source_node_id = source_node_id
        self.target_node_id = target_node_id
        self.condition = condition

class WorkflowRunner:
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.db = SessionLocal()
        
        self.workflow = self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id).first()
        if not self.workflow:
            raise ValueError(f"Workflow with ID '{workflow_id}' does not exist.")
            
        # Load all nodes and edges eagerly into detached memory objects
        # This completely avoids SQLAlchemy Session DetachedInstance errors during DB commits!
        db_nodes = self.db.query(WorkflowNodeModel).filter(WorkflowNodeModel.workflow_id == workflow_id).all()
        self.nodes = {
            n.id: NodeData(n.id, n.agent_id, n.label, n.pos_x, n.pos_y, n.config)
            for n in db_nodes
        }
        
        db_edges = self.db.query(WorkflowEdgeModel).filter(WorkflowEdgeModel.workflow_id == workflow_id).all()
        self.edges = [
            EdgeData(e.id, e.source_node_id, e.target_node_id, e.condition)
            for e in db_edges
        ]


    def log(self, level: str, message: str):
        """Append a log event to database and console."""
        log_entry = LogModel(
            level=level,
            message=message,
            component="workflow",
            workflow_id=self.workflow_id
        )
        self.db.add(log_entry)
        self.db.commit()
        print(f"[{level}] [Workflow:{self.workflow_id}] {message}")
        
        # Broadcast via WebSockets
        asyncio.create_task(broadcast_ws({
            "type": "log",
            "level": level,
            "message": message,
            "workflow_id": self.workflow_id,
            "timestamp": str(datetime.datetime.utcnow())
        }))

    async def execute(self, start_input: str, session_id: str = "workflow_session") -> str:
        """
        Executes the workflow graph starting from the trigger/starter node.
        Traverses nodes, runs agents, evaluates edge conditions, and loops until done.
        """
        self.log("INFO", f"Starting workflow '{self.workflow.name}' with input: '{start_input}'")
        
        # 1. Find trigger node
        start_node = None
        for node in self.nodes.values():
            config = json.loads(node.config) if node.config else {}
            if config.get("trigger") in ["start", "telegram"]:
                start_node = node
                break
                
        # Fallback to the first node if no trigger tag
        if not start_node and self.nodes:
            start_node = list(self.nodes.values())[0]

        if not start_node:
            self.log("ERROR", "No starter node found in workflow definition.")
            return "Error: No starter node configured."

        # Broadcast workflow started state
        await broadcast_ws({
            "type": "workflow_status",
            "workflow_id": self.workflow_id,
            "status": "running",
            "active_node_id": start_node.id
        })

        current_node = start_node
        current_input = start_input
        step_count = 0
        max_steps = 10 # Prevent infinite loops
        last_response = ""

        # Map to track values for evaluation
        variables = {"last_response": ""}

        while current_node and step_count < max_steps:
            step_count += 1
            node_label = current_node.label or f"Node {current_node.id}"
            agent_id = current_node.agent_id
            
            self.log("INFO", f"Step {step_count}: Activating node '{node_label}' (Agent: {agent_id})")
            
            # Highlight current active node on the visual UI
            await broadcast_ws({
                "type": "active_node",
                "workflow_id": self.workflow_id,
                "node_id": current_node.id,
                "agent_id": agent_id,
                "label": node_label
            })
            
            if not agent_id:
                self.log("WARNING", f"Node '{node_label}' has no agent attached. Skipping execution.")
                last_response = current_input
            else:
                # Initialize Agent and run
                agent = AgentRunner(agent_id, db_session=self.db)
                try:
                    # Run the agent ReAct loop
                    last_response = await agent.execute(current_input, session_id=session_id, workflow_id=self.workflow_id)
                    variables["last_response"] = last_response
                except Exception as e:
                    self.log("ERROR", f"Agent execution failed on '{node_label}': {e}")
                    last_response = f"Error: {e}"
                    variables["last_response"] = last_response
                    
            # Log message between agents visually
            self.log("INFO", f"Node '{node_label}' output: '{last_response[:100]}...'")
            
            # Find next target nodes by checking edge triggers
            next_node = await self._find_next_node(current_node.id, variables)
            
            if next_node:
                # Visual transition orb sliding animation trigger
                await broadcast_ws({
                    "type": "transition",
                    "workflow_id": self.workflow_id,
                    "source_id": current_node.id,
                    "target_id": next_node.id,
                    "message": last_response[:120] + "..." if len(last_response) > 120 else last_response
                })
                
                # Dynamic feedback logic: next node takes the last output as its new input
                current_input = last_response
                current_node = next_node
                # Add delay to make visual flows highly readable and pleasing to watch
                await asyncio.sleep(2.5)
            else:
                # No more edges match, workflow complete!
                current_node = None

        if step_count >= max_steps:
            self.log("WARNING", "Workflow execution halted. Maximum execution step limit exceeded.")
            
        self.log("INFO", "Workflow execution successfully completed.")
        
        # Reset state on client visualizers
        await broadcast_ws({
            "type": "workflow_status",
            "workflow_id": self.workflow_id,
            "status": "idle",
            "active_node_id": None
        })
        
        return last_response

    async def _find_next_node(self, current_node_id: str, variables: dict) -> WorkflowNodeModel | None:
        """
        Scans outgoing edges from the current node and evaluates conditional triggers.
        Supports operator expressions e.g. 'not_contains APPROVED' or 'contains TECHNICAL'.
        """
        outgoing_edges = [edge for edge in self.edges if edge.source_node_id == current_node_id]
        
        self.log("INFO", f"Evaluating {len(outgoing_edges)} outgoing edge conditions from node '{current_node_id}'...")

        # Search for a conditional match
        for edge in outgoing_edges:
            condition = json.loads(edge.condition) if edge.condition else {}
            cond_type = condition.get("type", "always")
            
            if cond_type == "always":
                self.log("INFO", f"Edge condition MATCHED: 'Always follow' ➔ Node '{edge.target_node_id}'")
                return self.nodes.get(edge.target_node_id)
                
            elif cond_type == "operator":
                field = condition.get("field", "last_response")
                operator = condition.get("operator", "contains")
                value = condition.get("value", "")
                
                # Fetch target variable
                field_val = str(variables.get(field, ""))
                
                matched = False
                if operator == "contains":
                    matched = value.lower() in field_val.lower()
                elif operator == "not_contains":
                    matched = value.lower() not in field_val.lower()
                elif operator == "equals":
                    matched = value.lower() == field_val.strip().lower()
                
                if matched:
                    self.log("INFO", f"Edge condition MATCHED: '{field} {operator} \"{value}\"' ➔ Node '{edge.target_node_id}'")
                    return self.nodes.get(edge.target_node_id)
                else:
                    self.log("INFO", f"Edge condition failed: '{field} {operator} \"{value}\"' (Value was: '{field_val[:40]}...')")

        return None

    def close(self):
        if self.db:
            self.db.close()
            
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

import datetime # Used for log records
