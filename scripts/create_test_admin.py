from app.db_session import get_session
from app.db_models import User
import bcrypt

def create_test_admin():
    with get_session() as session:
        # Check if admin exists
        admin = session.query(User).filter_by(username="admin").first()
        
        hashed_password = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        if admin:
            print("Updating existing admin password to 'admin123'...")
            admin.password_hash = hashed_password
            admin.role = "admin"
            admin.is_admin = True
        else:
            print("Creating new admin user...")
            new_admin = User(
                username="admin",
                password_hash=hashed_password,
                role="admin",
                is_admin=True,
                company="Marcus Theatres" # Required for some logic
            )
            session.add(new_admin)
        
        session.commit()
    print("Test admin 'admin' with password 'admin123' is ready.")

if __name__ == "__main__":
    create_test_admin()
