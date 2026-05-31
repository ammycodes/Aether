import json
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from app.config import settings

# Create engine and session maker
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ----------------- Database Models -----------------

class AgentModel(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=False)
    model = Column(String, default="gemini-2.5-flash")
    tools = Column(Text, default="[]")       # JSON array of tools e.g., ["search_web"]
    memory_type = Column(String, default="buffer") # "buffer" or "none"
    schedules = Column(Text, default="[]")   # JSON array of scheduling configurations
    rules = Column(Text, default="[]")       # JSON array of interaction rules
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class WorkflowModel(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_template = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    nodes = relationship("WorkflowNodeModel", back_populates="workflow", cascade="all, delete-orphan")
    edges = relationship("WorkflowEdgeModel", back_populates="workflow", cascade="all, delete-orphan")

class WorkflowNodeModel(Base):
    __tablename__ = "workflow_nodes"

    id = Column(String, primary_key=True, index=True)
    workflow_id = Column(String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id", ondelete="CASCADE"), nullable=True)  # Can be empty for custom logic nodes
    label = Column(String, nullable=True)
    pos_x = Column(Float, nullable=False, default=0.0)
    pos_y = Column(Float, nullable=False, default=0.0)
    config = Column(Text, default="{}")  # Extra JSON config

    workflow = relationship("WorkflowModel", back_populates="nodes")
    agent = relationship("AgentModel")

class WorkflowEdgeModel(Base):
    __tablename__ = "workflow_edges"

    id = Column(String, primary_key=True, index=True)
    workflow_id = Column(String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    source_node_id = Column(String, nullable=False)
    target_node_id = Column(String, nullable=False)
    condition = Column(Text, default="{}")  # JSON representation of trigger conditions

    workflow = relationship("WorkflowModel", back_populates="edges")

class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_type = Column(String, nullable=False)  # "agent", "user", "system", "channel"
    sender_id = Column(String, nullable=False)    # Agent ID, User ID or Bot name
    recipient_type = Column(String, nullable=False) # "agent", "user", "channel"
    recipient_id = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String, default="delivered")  # "pending", "delivered", "processed"
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class LogModel(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String, default="INFO")        # "INFO", "WARNING", "ERROR", "TRACE"
    message = Column(Text, nullable=False)
    component = Column(String, nullable=False)    # "runtime", "api", "telegram", "workflow"
    workflow_id = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class CostTrackerModel(Base):
    __tablename__ = "costs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# ----------------- DB Initialization & Seeding -----------------

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Check if we already have data seeded
    db = SessionLocal()
    try:
        if db.query(AgentModel).count() > 0:
            return # DB already initialized and seeded
            
        print("Database is empty. Seeding initial Agent templates and Workflow templates...")

        # 1. Seed Pre-built Agents
        agents = [
            AgentModel(
                id="researcher",
                name="Researcher",
                role="Research Expert",
                system_prompt="You are an expert researcher. Your goal is to gather detailed information, look up facts, perform web searches, and compile comprehensive notes on any given topic. Always provide factual summaries, structural bullet points, and cite your sources. Be concise but extremely thorough.",
                model="gemini-2.5-flash",
                tools=json.dumps(["search_web", "fetch_url"]),
                memory_type="buffer",
                schedules=json.dumps([]),
                rules=json.dumps([])
            ),
            AgentModel(
                id="writer",
                name="Writer",
                role="Creative Copywriter",
                system_prompt="You are a professional copywriter and technical content generator. Your goal is to take research notes, outlines, or structural data and draft high-quality articles, essays, technical summaries, or reports. Write beautifully, ensure proper flow, maintain tone consistency, and make it engaging.",
                model="gemini-2.5-flash",
                tools=json.dumps(["calculator"]),
                memory_type="buffer",
                schedules=json.dumps([]),
                rules=json.dumps([])
            ),
            AgentModel(
                id="critic",
                name="Critic",
                role="Meticulous Editor",
                system_prompt="You are a strict editorial critic. Your job is to inspect and evaluate written articles or reports. You check for structural clarity, factual accuracy, spelling, grammar, and completeness. You MUST provide feedback. If the report is excellent, end your output EXACTLY with the text 'APPROVED'. Otherwise, suggest specific changes that need to be made.",
                model="gemini-2.5-flash",
                tools=json.dumps([]),
                memory_type="buffer",
                schedules=json.dumps([]),
                rules=json.dumps([])
            ),
            AgentModel(
                id="triage",
                name="Triage Bot",
                role="Customer Success Router",
                system_prompt="You are the gatekeeper agent for the customer support stream. Your job is to analyze queries received from external users (via Telegram or manual inputs), classify them into 'TECHNICAL', 'BILLING', or 'GENERAL', and delegate them. You are polite, welcoming, and keep responses direct.",
                model="gemini-2.5-flash",
                tools=json.dumps([]),
                memory_type="buffer",
                schedules=json.dumps([]),
                rules=json.dumps([])
            ),
            AgentModel(
                id="tech_support",
                name="Tech Specialist",
                role="Advanced Support Engineer",
                system_prompt="You are a senior tech specialist. You have access to the system's files containing local logs and mock knowledge bases. You use 'read_file' to search through knowledge bases and resolve queries. You explain steps in a clear, easy-to-understand format.",
                model="gemini-2.5-flash",
                tools=json.dumps(["read_file"]),
                memory_type="buffer",
                schedules=json.dumps([]),
                rules=json.dumps([])
            ),
            AgentModel(
                id="supervisor",
                name="Supervisor",
                role="Executive Approver",
                system_prompt="You are the customer support supervisor. You oversee responses to billing and high-priority questions. You ensure the company's guidelines are met. Review answers and approve them before sending them out to customers.",
                model="gemini-2.5-flash",
                tools=json.dumps(["calculator"]),
                memory_type="buffer",
                schedules=json.dumps([]),
                rules=json.dumps([])
            )
        ]

        for agent in agents:
            db.add(agent)
        db.commit()

        # 2. Seed Workflow 1: Research & Content Generator Template
        w1 = WorkflowModel(
            id="template_content_gen",
            name="Research & Write Flow",
            description="Collaborative writing workflow. The Researcher gathers information, the Writer drafts the piece, and the Critic reviews it. Loops back to the Writer if revisions are required.",
            is_template=True
        )
        db.add(w1)
        db.commit()

        w1_nodes = [
            WorkflowNodeModel(
                id="w1_node_researcher",
                workflow_id="template_content_gen",
                agent_id="researcher",
                label="Gather Research",
                pos_x=150.0,
                pos_y=200.0,
                config=json.dumps({"trigger": "start"})
            ),
            WorkflowNodeModel(
                id="w1_node_writer",
                workflow_id="template_content_gen",
                agent_id="writer",
                label="Draft Article",
                pos_x=450.0,
                pos_y=200.0,
                config=json.dumps({})
            ),
            WorkflowNodeModel(
                id="w1_node_critic",
                workflow_id="template_content_gen",
                agent_id="critic",
                label="Review & Approve",
                pos_x=750.0,
                pos_y=200.0,
                config=json.dumps({})
            )
        ]
        
        w1_edges = [
            WorkflowEdgeModel(
                id="w1_edge_1",
                workflow_id="template_content_gen",
                source_node_id="w1_node_researcher",
                target_node_id="w1_node_writer",
                condition=json.dumps({"type": "always"})
            ),
            # Forward to Editor
            WorkflowEdgeModel(
                id="w1_edge_2",
                workflow_id="template_content_gen",
                source_node_id="w1_node_writer",
                target_node_id="w1_node_critic",
                condition=json.dumps({"type": "always"})
            ),
            # Loopback if criticized
            WorkflowEdgeModel(
                id="w1_edge_loopback",
                workflow_id="template_content_gen",
                source_node_id="w1_node_critic",
                target_node_id="w1_node_writer",
                condition=json.dumps({
                    "type": "operator", 
                    "field": "last_response", 
                    "operator": "not_contains", 
                    "value": "APPROVED"
                })
            )
        ]

        for node in w1_nodes:
            db.add(node)
        for edge in w1_edges:
            db.add(edge)
        db.commit()

        # 3. Seed Workflow 2: Customer Support & Triage Template
        w2 = WorkflowModel(
            id="template_support_gateway",
            name="Smart Support Gateway",
            description="Receives external inputs (e.g. Telegram), classifies queries. Route technical issues to Technical Specialist, and billing/general queries to a Supervisor.",
            is_template=True
        )
        db.add(w2)
        db.commit()

        w2_nodes = [
            WorkflowNodeModel(
                id="w2_node_triage",
                workflow_id="template_support_gateway",
                agent_id="triage",
                label="Telegram Gateway (Triage)",
                pos_x=150.0,
                pos_y=250.0,
                config=json.dumps({"trigger": "telegram"})
            ),
            WorkflowNodeModel(
                id="w2_node_tech",
                workflow_id="template_support_gateway",
                agent_id="tech_support",
                label="Resolve Tech Query",
                pos_x=500.0,
                pos_y=120.0,
                config=json.dumps({})
            ),
            WorkflowNodeModel(
                id="w2_node_supervisor",
                workflow_id="template_support_gateway",
                agent_id="supervisor",
                label="Supervisor Approval",
                pos_x=500.0,
                pos_y=380.0,
                config=json.dumps({})
            )
        ]
        
        w2_edges = [
            WorkflowEdgeModel(
                id="w2_edge_tech",
                workflow_id="template_support_gateway",
                source_node_id="w2_node_triage",
                target_node_id="w2_node_tech",
                condition=json.dumps({
                    "type": "operator",
                    "field": "last_response",
                    "operator": "contains",
                    "value": "TECHNICAL"
                })
            ),
            WorkflowEdgeModel(
                id="w2_edge_billing",
                workflow_id="template_support_gateway",
                source_node_id="w2_node_triage",
                target_node_id="w2_node_supervisor",
                condition=json.dumps({
                    "type": "operator",
                    "field": "last_response",
                    "operator": "not_contains",
                    "value": "TECHNICAL"
                })
            )
        ]

        for node in w2_nodes:
            db.add(node)
        for edge in w2_edges:
            db.add(edge)
        db.commit()

        # Seed pre-populated logs and cost history to show in Dashboard at first start
        db.add(LogModel(level="INFO", message="Aether Runtime Core engine booted successfully.", component="runtime"))
        db.add(LogModel(level="INFO", message="Telegram gateway listening worker spawned.", component="telegram"))
        db.add(LogModel(level="INFO", message="Visual builder template: 'Research & Write Flow' loaded.", component="workflow"))
        db.add(LogModel(level="INFO", message="Visual builder template: 'Smart Support Gateway' loaded.", component="workflow"))
        
        # Add some costs to show on starting
        db.add(CostTrackerModel(agent_id="researcher", prompt_tokens=420, completion_tokens=180, cost_usd=0.0009))
        db.add(CostTrackerModel(agent_id="writer", prompt_tokens=650, completion_tokens=450, cost_usd=0.0021))
        db.add(CostTrackerModel(agent_id="critic", prompt_tokens=300, completion_tokens=90, cost_usd=0.0006))
        
        db.commit()
        print("Database seeding completed successfully.")

    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

# Session helper dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
