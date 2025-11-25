import uuid

def create_all_tables(db_manager):
    """
    Create all necessary tables for the private AI application.
    Drops existing tables first to avoid foreign key issues.
    """

    # Drop tables in reverse order to avoid FK conflicts
    for table in ["Inference_Requests", "Model_Versions", "clients"]:
        try:
            db_manager.delete_table(table)
        except Exception as e:
            print(f"Warning: Could not drop table {table}: {e}")

    # === CLIENTS TABLE ===
    db_manager.create_table(
        "clients",
        """(
            id CHAR(36) PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            display_name VARCHAR(255),
            email VARCHAR(255) UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            api_key_hash VARCHAR(255),
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
            id CHAR(36) PRIMARY KEY,
            model_name VARCHAR(255) NOT NULL,
            version_tag VARCHAR(50) NOT NULL,
            storage_tag VARCHAR(255),
            framework VARCHAR(50),
            max_tokens INT,
            quantized BOOLEAN DEFAULT FALSE,
            parameters_count BIGINT,
            owner_user_id CHAR(36),
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
            id CHAR(36) PRIMARY KEY,
            request_uuid VARCHAR(255) UNIQUE NOT NULL,
            user_id CHAR(36),
            model_version_id CHAR(36),
            input_hash VARCHAR(255),
            input_size INT,
            prompt_tokens INT,
            response_tokens INT,
            latency_ms INT,
            status SMALLINT,
            cost_estimate_cents DECIMAL(10,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            FOREIGN KEY (user_id) REFERENCES clients(id),
            FOREIGN KEY (model_version_id) REFERENCES Model_Versions(id)
        )"""
    )

    print("All tables created successfully.")
