from db_manager import DatabaseManager

def create_all_tables(db_manager):
    """
    Create all necessary tables for the application using DatabaseManager instance.
    Uses the new AI-related schema (clients, Model_Versions, Inference_Requests).
    """
    # === CLIENTS TABLE ===
    db_manager.create_table(
        "clients",
        """(
            id UUID PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            api_key_hash TEXT,
            role SMALLINT DEFAULT 1,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP NULL,
            mfa_enabled BOOLEAN DEFAULT FALSE
        )"""
    )

    # === MODEL_VERSIONS TABLE ===
    db_manager.create_table(
        "Model_Versions",
        """(
            id UUID PRIMARY KEY,
            model_name TEXT NOT NULL,
            version_tag TEXT NOT NULL,
            storage_tag TEXT,
            framework TEXT,
            max_tokens INTEGER,
            quantized BOOLEAN DEFAULT FALSE,
            parameters_count BIGINT,
            owner_user_id UUID,
            is_deployed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_user_id) REFERENCES clients(id)
        )"""
    )

    # === INFERENCE_REQUESTS TABLE ===
    db_manager.create_table(
        "Inference_Requests",
        """(
            id UUID PRIMARY KEY,
            request_uuid TEXT UNIQUE NOT NULL,
            user_id UUID,
            model_version_id UUID,
            input_hash TEXT,
            input_size INTEGER,
            prompt_tokens INTEGER,
            response_tokens INTEGER,
            latency_ms INTEGER,
            status SMALLINT,
            cost_estimate_cents DECIMAL(10,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            FOREIGN KEY (user_id) REFERENCES clients(id),
            FOREIGN KEY (model_version_id) REFERENCES Model_Versions(id)
        )"""
    )

    print("All tables created successfully (clients, Model_Versions, Inference_Requests).")


def populate_media_menu(db_manager):
    """
    (Unused in new schema)
    Keeping for compatibility — does nothing.
    """
    print("populate_media_menu() skipped: media_menu table not part of new schema.")
