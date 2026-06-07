from backend.database.db import engine, Base
from backend.database.models import User, Document, ChatHistory

def init_database():
    """Create all database tables"""
    print("Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully!")
        print("   - users table")
        print("   - documents table")
        print("   - chat_history table")
    except Exception as e:
        print(f"❌ Error creating tables: {e}")

if __name__ == "__main__":
    init_database()