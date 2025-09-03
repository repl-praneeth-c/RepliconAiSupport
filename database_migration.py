#!/usr/bin/env python3
"""
Database migration script to add image support to existing Replicon documentation database
"""

import sqlite3
import os
from pathlib import Path

def migrate_database(db_path='replicon_docs.db'):
    """Migrate existing database to support images"""
    
    if not Path(db_path).exists():
        print(f"Database {db_path} doesn't exist. Will be created when scraper runs.")
        return True
    
    print(f"Migrating database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check current schema
        cursor.execute("PRAGMA table_info(documents)")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"Current documents table columns: {columns}")
        
        # Add images column to documents table if it doesn't exist
        if 'images' not in columns:
            print("Adding 'images' column to documents table...")
            cursor.execute('ALTER TABLE documents ADD COLUMN images TEXT')
            print("✅ Added images column to documents table")
        else:
            print("✅ Images column already exists in documents table")
        
        # Create images table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_url TEXT,
                original_url TEXT,
                local_filename TEXT,
                alt_text TEXT,
                caption TEXT,
                file_size INTEGER,
                image_type TEXT,
                width INTEGER,
                height INTEGER,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_url) REFERENCES documents (url)
            )
        """)
        print("✅ Images table created/verified")
        
        # Check scraping_sessions table
        cursor.execute("PRAGMA table_info(scraping_sessions)")
        session_columns = [col[1] for col in cursor.fetchall()]
        print(f"Current scraping_sessions columns: {session_columns}")
        
        # Add image-related columns to scraping_sessions table
        if 'images_found' not in session_columns:
            print("Adding image columns to scraping_sessions table...")
            cursor.execute('ALTER TABLE scraping_sessions ADD COLUMN images_found INTEGER DEFAULT 0')
            cursor.execute('ALTER TABLE scraping_sessions ADD COLUMN images_downloaded INTEGER DEFAULT 0')
            print("✅ Added image columns to scraping_sessions table")
        else:
            print("✅ Image columns already exist in scraping_sessions table")
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_document_url ON images(document_url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_alt_text ON images(alt_text)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category)')
        print("✅ Created database indexes")
        
        conn.commit()
        conn.close()
        
        print("✅ Database migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

def backup_database(db_path='replicon_docs.db'):
    """Create a backup of the existing database"""
    if not Path(db_path).exists():
        print("No existing database to backup")
        return True
    
    backup_path = f"{db_path}.backup"
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"✅ Database backed up to: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False

def create_images_directory():
    """Create the images directory structure"""
    directories = [
        "static/images",
        "static/images/scraped"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: {directory}")

def verify_migration(db_path='replicon_docs.db'):
    """Verify the migration was successful"""
    if not Path(db_path).exists():
        print("Database doesn't exist yet - will be created on first scrape")
        return True
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check documents table
        cursor.execute("PRAGMA table_info(documents)")
        doc_columns = [col[1] for col in cursor.fetchall()]
        
        # Check images table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images'")
        images_table_exists = cursor.fetchone() is not None
        
        # Check scraping_sessions table
        cursor.execute("PRAGMA table_info(scraping_sessions)")
        session_columns = [col[1] for col in cursor.fetchall()]
        
        conn.close()
        
        # Verify all required columns exist
        required_doc_columns = ['images']
        required_session_columns = ['images_found', 'images_downloaded']
        
        missing_doc_columns = [col for col in required_doc_columns if col not in doc_columns]
        missing_session_columns = [col for col in required_session_columns if col not in session_columns]
        
        if missing_doc_columns:
            print(f"❌ Missing document columns: {missing_doc_columns}")
            return False
        
        if missing_session_columns:
            print(f"❌ Missing session columns: {missing_session_columns}")
            return False
            
        if not images_table_exists:
            print("❌ Images table doesn't exist")
            return False
        
        print("✅ Migration verification successful!")
        print("✅ Database is ready for image-enhanced scraping")
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Main migration function"""
    print("🔄 Replicon Database Migration for Image Support")
    print("=" * 50)
    
    db_path = 'replicon_docs.db'
    
    # Step 1: Backup existing database
    print("\n1. Backing up existing database...")
    backup_database(db_path)
    
    # Step 2: Create directories
    print("\n2. Creating image directories...")
    create_images_directory()
    
    # Step 3: Migrate database
    print("\n3. Migrating database schema...")
    if migrate_database(db_path):
        print("✅ Database migration successful")
    else:
        print("❌ Database migration failed")
        return False
    
    # Step 4: Verify migration
    print("\n4. Verifying migration...")
    if verify_migration(db_path):
        print("✅ Migration verification successful")
    else:
        print("❌ Migration verification failed")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 Migration completed successfully!")
    print("\nNext steps:")
    print("1. Run: python replicon_scraper.py")
    print("2. The scraper will now extract and download images")
    print("3. Images will be saved to: static/images/scraped/")
    print("4. Test with visual queries in your chat system")
    
    return True

if __name__ == "__main__":
    main()