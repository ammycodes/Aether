import pytest
from app.database import init_db
from app.runtime.workflow import WorkflowRunner

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()
    yield

@pytest.mark.asyncio
async def test_workflow_runner():
    # Load support gateway workflow template
    runner = WorkflowRunner("template_support_gateway")
    
    # Run support workflow with a Technical query
    # Classifier should tag it as TECHNICAL and transition to tech_support specialist!
    final_output = await runner.execute("My server is throwing a port 8000 error, please check technical docs.")
    
    # Assertions
    assert final_output is not None
    assert len(final_output) > 0
    # Specialist should have resolved utilizing the knowledge base file
    assert "port" in final_output.lower() or "resolution" in final_output.lower() or "knowledge" in final_output.lower()
    
    runner.close()
