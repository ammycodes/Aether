import os
import pytest
import json
from app.database import SessionLocal, AgentModel, init_db
from app.runtime.agent import AgentRunner

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    # Make sure DB is initialized
    init_db()
    yield

def test_agent_creation():
    db = SessionLocal()
    try:
        # Create a new testing agent
        test_id = "test_assistant"
        
        # Cleanup if exists
        existing = db.query(AgentModel).filter(AgentModel.id == test_id).first()
        if existing:
            db.delete(existing)
            db.commit()
            
        agent = AgentModel(
            id=test_id,
            name="Test Assistant",
            role="Testing Agent",
            system_prompt="You are a unit testing assistant. Keep replies short.",
            model="gemini-2.5-flash",
            tools=json.dumps(["calculator"]),
            memory_type="buffer"
        )
        db.add(agent)
        db.commit()
        
        # Verify persistence
        db_agent = db.query(AgentModel).filter(AgentModel.id == test_id).first()
        assert db_agent is not None
        assert db_agent.name == "Test Assistant"
        assert db_agent.role == "Testing Agent"
        assert "calculator" in json.loads(db_agent.tools)
        
    finally:
        db.close()

@pytest.mark.asyncio
async def test_agent_execution_loop():
    # Load testing runner
    runner = AgentRunner("researcher")
    
    # Trigger offline run
    # Researcher should see 'price' and invoke search_web("price") ReAct loop!
    response = await runner.execute("What is the price of the Standard Plan?")
    
    # Assertions
    assert response is not None
    assert len(response) > 0
    # Offline mode should have processed query facts
    assert "29" in response or "standard" in response.lower() or "price" in response.lower()
    
    runner.close()
