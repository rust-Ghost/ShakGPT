from db_manager import DatabaseManager

def create_all_tables(db_manager):
    """
    Create all necessary tables for the application using DatabaseManager instance.
    
    Args:
        db_manager: An initialized DatabaseManager instance
    """
    db_manager.create_table(
        "clients",
        "(client_id INT PRIMARY KEY, client_ip VARCHAR(255), client_port INT, last_seen DATETIME, ddos_status BOOLEAN, total_sent_media INT)"
    )
    
    db_manager.create_table(
        "decrypted_media",
        "(user_id VARCHAR(255), media_type_id INT, path_to_decrypted_media VARCHAR(255))"
    )
    
    db_manager.create_table(
        "media_menu",
        "(id_media INT PRIMARY KEY, image_path VARCHAR(255), audio_path VARCHAR(255), video_path VARCHAR(255))"
    )

def populate_media_menu(db_manager):
    """
    Populate the media_menu table with predefined data if it's empty.
    
    Args:
        db_manager: An initialized DatabaseManager instance
    """
    predefined_media = [
        (1, r"C:\Users\Mamriot_User\Desktop\secret_service_project\JPG\Ransom.jpg", None, None),
        (2, r"C:\Users\Mamriot_User\Desktop\secret_service_project\JPG\cover1_image.jpg", None, None),
        (3, None, None, r"C:\Users\Mamriot_User\Desktop\secret_service_project\MP4\video.mp4")
    ]

    existing_rows = db_manager.get_all_rows("media_menu")
    if not existing_rows:
        for media in predefined_media:
            db_manager.insert_row(
                "media_menu",
                "(id_media, image_path, audio_path, video_path)",
                "(%s, %s, %s, %s)",
                media
            )