from backend.database.db import SessionLocal
from backend.database.models import User
from backend.auth.auth import get_password_hash

db = SessionLocal()

try:
    # Check if user already exists
    existing_user = db.query(User).filter(User.username == "alikaka").first()
    if existing_user:
        print(f"User 'alikaka' already exists (ID: {existing_user.id})")
        print(f"Delete it first or use a different username")
        db.close()
        exit()
    
    # Create user
    user = User(
        username="alikaka",
        email="alikaka@example.com",
        hashed_password=get_password_hash("1234")
    )
    db.add(user)
    db.commit()
    print(f"✅ User created successfully!")
    print(f"   Username: {user.username}")
    print(f"   Email: {user.email}")
    print(f"   User ID: {user.id}")
    print(f"   Password hash: {user.hashed_password[:20]}...")
    
except Exception as e:
    print(f"❌ Error: {e}")
    db.rollback()
finally:
    db.close()