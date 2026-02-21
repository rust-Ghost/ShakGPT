# run_once_seed_stress_users.py
import bcrypt, uuid
from db_manager import DatabaseManager
from constants import DB_CONFIG
import hashlib

db = DatabaseManager(**DB_CONFIG)
users = [
    ("alice","Pass123!"),("bob","Pass456!"),("charlie","Pass789!"),
    ("dave","Pass000!"),("eve","Pass111!"),("frank","Pass222!"),
]
for username, password in users:
    uh = hashlib.sha256(username.lower().encode()).hexdigest()
    ph = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        db.insert_row("clients",
            ["id","username_hash","display_name","password_hash"],
            [str(uuid.uuid4()), uh, username, ph])
        print(f"Added {username}")
    except Exception as e:
        print(f"Skipped {username}: {e}")
db.close()