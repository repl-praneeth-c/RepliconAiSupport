#!/usr/bin/env python3
"""
Debug script to identify and fix image search issues
"""

import sqlite3
import json
from pathlib import Path

def debug_image_database():
    """Debug the image database to understand what's available"""
    
    if not Path('replicon_docs.db').exists():
        print("❌ Database not found")
        return
    
    conn = sqlite3.connect('replicon_docs.db')
    cursor = conn.cursor()
    
    print("=== DATABASE ANALYSIS ===")
    
    # Check if images table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images'")
    if not cursor.fetchone():
        print("❌ Images table doesn't exist - run enhanced scraper first")
        return
    
    # Total images
    cursor.execute('SELECT COUNT(*) FROM images')
    total_images = cursor.fetchone()[0]
    print(f"📸 Total images in database: {total_images}")
    
    # Images by document category
    cursor.execute('''
    SELECT d.category, COUNT(i.id) as image_count
    FROM documents d
    LEFT JOIN images i ON d.url = i.document_url
    WHERE i.id IS NOT NULL
    GROUP BY d.category
    ORDER BY image_count DESC
    ''')
    
    print("\n📊 Images by category:")
    for category, count in cursor.fetchall():
        print(f"  {category}: {count} images")
    
    # Sample image data
    cursor.execute('''
    SELECT i.local_filename, i.alt_text, i.caption, d.title, d.category, d.url
    FROM images i
    JOIN documents d ON i.document_url = d.url
    LIMIT 10
    ''')
    
    print(f"\n🔍 Sample images:")
    for filename, alt_text, caption, doc_title, category, url in cursor.fetchall():
        print(f"  📁 {filename}")
        print(f"     Alt: {alt_text or 'None'}")
        print(f"     Caption: {caption or 'None'}")
        print(f"     From: {doc_title} ({category})")
        print(f"     URL: {url}")
        print()
    
    conn.close()

def test_project_search():
    """Test project-specific search"""
    
    conn = sqlite3.connect('replicon_docs.db')
    cursor = conn.cursor()
    
    print("\n=== PROJECT SETUP SEARCH TEST ===")
    
    # Test the fixed search query for project setup
    sql = '''
    SELECT DISTINCT 
        i.local_filename, i.alt_text, i.caption,
        d.title, d.category, d.content
    FROM images i
    JOIN documents d ON i.document_url = d.url
    WHERE (
        (LOWER(d.title) LIKE '%project%' AND (
            LOWER(d.title) LIKE '%setup%' OR 
            LOWER(d.title) LIKE '%create%' OR 
            LOWER(d.title) LIKE '%new%' OR
            LOWER(d.content) LIKE '%project setup%' OR
            LOWER(d.content) LIKE '%new project%'
        ))
        OR 
        (LOWER(i.alt_text) LIKE '%project%' AND LOWER(i.alt_text) LIKE '%create%')
        OR
        (LOWER(i.caption) LIKE '%project%' AND LOWER(i.caption) LIKE '%setup%')
    )
    AND LOWER(d.title) NOT LIKE '%login%'
    AND LOWER(d.title) NOT LIKE '%password%'
    AND LOWER(d.title) NOT LIKE '%email%'
    ORDER BY 
        CASE WHEN LOWER(d.title) LIKE '%project%' THEN 1 ELSE 2 END,
        d.title
    LIMIT 10
    '''
    
    try:
        cursor.execute(sql)
        results = cursor.fetchall()
        
        print(f"🔍 Found {len(results)} project-related images:")
        
        for i, (filename, alt_text, caption, doc_title, category, content) in enumerate(results, 1):
            print(f"\n{i}. 📁 {filename}")
            print(f"   Document: {doc_title} ({category})")
            print(f"   Alt text: {alt_text or 'None'}")
            print(f"   Caption: {caption or 'None'}")
            print(f"   Content preview: {content[:100] if content else 'None'}...")
            
            # Check if file exists
            file_path = Path(f"static/images/scraped/{filename}")
            print(f"   File exists: {file_path.exists()}")
            
    except Exception as e:
        print(f"❌ Query failed: {e}")
    
    conn.close()

def check_irrelevant_images():
    """Check for the irrelevant images that were showing up"""
    
    conn = sqlite3.connect('replicon_docs.db')
    cursor = conn.cursor()
    
    print("\n=== CHECKING FOR IRRELEVANT IMAGES ===")
    
    # Look for login/formula related images
    cursor.execute('''
    SELECT i.local_filename, i.alt_text, d.title, d.category
    FROM images i
    JOIN documents d ON i.document_url = d.url
    WHERE LOWER(d.title) LIKE '%login%' OR LOWER(d.title) LIKE '%email%' OR LOWER(d.title) LIKE '%formula%'
    ORDER BY d.title
    ''')
    
    results = cursor.fetchall()
    print(f"📋 Found {len(results)} potentially irrelevant images:")
    
    for filename, alt_text, doc_title, category in results:
        print(f"  📁 {filename}")
        print(f"     Document: {doc_title} ({category})")
        print(f"     Alt: {alt_text or 'None'}")
        print()
    
    conn.close()

def test_fixed_search(query="project setup"):
    """Test the fixed search logic"""
    
    print(f"\n=== TESTING FIXED SEARCH: '{query}' ===")
    
    # Simulate the fixed search logic
    query_lower = query.lower()
    
    if 'project' in query_lower and ('setup' in query_lower or 'new' in query_lower or 'create' in query_lower):
        print("✅ Detected as PROJECT SETUP query")
        print("   Will use project-specific search with filters")
        test_project_search()
    else:
        print("ℹ️ General search logic would be used")

def main():
    """Run full debugging analysis"""
    print("🔍 REPLICON IMAGE SEARCH DEBUG TOOL")
    print("=" * 50)
    
    # Basic database analysis
    debug_image_database()
    
    # Test project search
    test_fixed_search("project setup")
    
    # Check for irrelevant images
    check_irrelevant_images()
    
    print("\n" + "=" * 50)
    print("🎯 DEBUG COMPLETE")
    print("   Replace support_system.py with the fixed version")
    print("   The new system filters out irrelevant login/formula images")
    print("   Test with: 'Visual guide for setting up a new project'")

if __name__ == "__main__":
    main()