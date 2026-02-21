"""
Create tables WITHOUT dropping existing data
"""
from db_manager import DatabaseManager
from constants import DB_CONFIG
import uuid

def create_all_tables(db_manager):
    """Create tables only if they don't exist. NEVER drop data."""
    
    # === CLIENTS TABLE ===
    db_manager.conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id            CHAR(36)     PRIMARY KEY,
            username_hash VARCHAR(255) UNIQUE NOT NULL,
            display_name  VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role          SMALLINT     DEFAULT 1,
            is_active     BOOLEAN      DEFAULT TRUE,
            created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP    NULL,
            encryption_key VARCHAR(64) NULL
        )
    """)

    # === MODEL_VERSIONS TABLE ===
    db_manager.conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS Model_Versions (
            id            CHAR(36)     PRIMARY KEY,
            model_key     VARCHAR(100) UNIQUE NOT NULL,
            display_name  VARCHAR(255) NOT NULL,
            gguf_filename VARCHAR(255) NOT NULL,
            description   TEXT,
            max_new_tokens INT         DEFAULT 256,
            is_active     BOOLEAN      DEFAULT TRUE,
            created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === CHAT_SESSIONS TABLE ===
    db_manager.conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS Chat_Sessions (
            id               CHAR(36)     PRIMARY KEY,
            user_id          CHAR(36)     NOT NULL,
            model_version_id CHAR(36)     NOT NULL,
            title            VARCHAR(255) DEFAULT 'New Chat',
            created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)          REFERENCES clients(id) ON DELETE CASCADE,
            FOREIGN KEY (model_version_id) REFERENCES Model_Versions(id)
        )
    """)

    # === CHAT_MESSAGES TABLE (with encryption) ===
    db_manager.conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS Chat_Messages (
            id         CHAR(36)                     PRIMARY KEY,
            session_id CHAR(36)                     NOT NULL,
            role       ENUM('user','assistant')      NOT NULL,
            content    TEXT                          NOT NULL,
            encrypted  BOOLEAN                       DEFAULT FALSE,
            latency_ms INT                           DEFAULT NULL,
            created_at TIMESTAMP                     DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES Chat_Sessions(id) ON DELETE CASCADE
        )
    """)

    # === FAILED_LOGINS TABLE (security) ===
    db_manager.conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS failed_logins (
            id            INT          PRIMARY KEY AUTO_INCREMENT,
            username_hash VARCHAR(255) NOT NULL,
            ip_address    VARCHAR(45)  NOT NULL,
            attempt_time  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_username (username_hash),
            INDEX idx_time (attempt_time)
        )
    """)

    # === AUDIT_LOG TABLE ===
    db_manager.conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id         INT          PRIMARY KEY AUTO_INCREMENT,
            user_id    CHAR(36)     NULL,
            action     VARCHAR(100) NOT NULL,
            details    TEXT         NULL,
            ip_address VARCHAR(45)  NULL,
            timestamp  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user (user_id),
            INDEX idx_action (action),
            INDEX idx_time (timestamp)
        )
    """)

    db_manager.conn.commit()
    print("[INFO] All tables created (existing data preserved)")


def seed_models(db_manager):
    """Add models only if they don't exist"""
    cursor = db_manager.conn.cursor()
    cursor.execute("SELECT model_key FROM Model_Versions")
    existing = {row[0] for row in cursor.fetchall()}
    
    models = [
        {
            "id": str(uuid.uuid4()),
            "model_key": "tinyllama",
            "display_name": "TinyLlama 1.1B",
            "gguf_filename": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
            "description": "Fast 1.1B model for quick responses",
            "max_new_tokens": 256,
        },
        {
            "id": str(uuid.uuid4()),
            "model_key": "mistral-7b",
            "display_name": "Mistral 7B",
            "gguf_filename": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
            "description": "High-quality 7B model with better reasoning",
            "max_new_tokens": 512,
        },
        {
            "id": str(uuid.uuid4()),
            "model_key": "phi2",
            "display_name": "Phi-2",
            "gguf_filename": "phi-2.Q4_K_M.gguf",
            "description": "Strong 2.7B reasoning model",
            "max_new_tokens": 256,
        },
    ]
    
    for m in models:
        if m["model_key"] not in existing:
            db_manager.insert_row(
                "Model_Versions",
                ["id","model_key","display_name","gguf_filename","description","max_new_tokens"],
                [m["id"], m["model_key"], m["display_name"],
                 m["gguf_filename"], m["description"], m["max_new_tokens"]],
            )
            print(f"[INFO] Seeded model: {m['display_name']}")
        else:
            print(f"[INFO] Model exists: {m['model_key']}")


if __name__ == "__main__":
    db = DatabaseManager(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )
    db.create_database(DB_CONFIG["database"])
    db.reconnect(DB_CONFIG["database"])
    create_all_tables(db)
    seed_models(db)
    db.close()
    print("[INFO] Database setup complete. Data preserved.")