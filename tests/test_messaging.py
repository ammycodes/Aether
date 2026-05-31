import pytest
from app.database import SessionLocal, MessageModel, init_db

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()
    yield

def test_message_persistence():
    db = SessionLocal()
    try:
        # Create mock message exchange trace
        msg = MessageModel(
            sender_type="agent",
            sender_id="writer",
            recipient_type="agent",
            recipient_id="critic",
            content="Standard mock body report draft for revision.",
            status="delivered"
        )
        db.add(msg)
        db.commit()
        
        # Verify persistence and retrieval
        db_msg = db.query(MessageModel).filter(
            MessageModel.sender_id == "writer",
            MessageModel.recipient_id == "critic"
        ).order_by(MessageModel.timestamp.desc()).first()
        
        assert db_msg is not None
        assert db_msg.content == "Standard mock body report draft for revision."
        assert db_msg.status == "delivered"
        
    finally:
        db.close()
