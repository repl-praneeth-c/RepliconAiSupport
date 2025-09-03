#!/usr/bin/env python3
"""
Complete debugging script to identify why images aren't showing up
"""

import sqlite3
import json
from pathlib import Path

def debug_complete_system():
    """Complete system debugging"""
    
    print("🔍 COMPLETE IMAGE SYSTEM DEBUG")
    print("=" * 60)
    
    # 1. Check database existence and structure
    print("\n1. DATABASE CHECK:")
    db_path = Path('replicon_docs.db')
    if not db_path.exists():
        print("❌ Database not found: replicon_docs.db")
        return False
    
    print("✅ Database found")
    
    try:
        conn = sqlite3.connect('replicon_docs.db')
        cursor = conn.cursor()
        
        # Check if images table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images'")
        if not cursor.fetchone():
            print("❌ Images table doesn't exist")
            print("   Run: python database_migration.py")
            return False
        
        print("✅ Images table exists")
        
        # Check total images in database
        cursor.execute('SELECT COUNT(*) FROM images')
        total_images = cursor.fetchone()[0]
        print(f"📊 Total images in database: {total_images}")
        
        if total_images == 0:
            print("❌ No images in database")
            print("   Run: python replicon_scraper.py (with image support)")
            return False
        
        # Check images by category
        cursor.execute('''
        SELECT d.category, COUNT(i.id) as image_count
        FROM documents d
        LEFT JOIN images i ON d.url = i.document_url
        WHERE i.id IS NOT NULL
        GROUP BY d.category
        ORDER BY image_count DESC
        ''')
        
        print("\n📋 Images by category:")
        categories = cursor.fetchall()
        for category, count in categories:
            print(f"   {category}: {count} images")
        
        # 2. Check physical image files
        print("\n2. PHYSICAL FILES CHECK:")
        images_dir = Path("static/images/scraped")
        if not images_dir.exists():
            print("❌ Images directory doesn't exist: static/images/scraped")
            print("   Create it or run enhanced scraper")
            return False
        
        print("✅ Images directory exists")
        
        # Count actual files
        image_files = list(images_dir.glob("*.*"))
        print(f"📁 Physical image files: {len(image_files)}")
        
        if len(image_files) == 0:
            print("❌ No physical image files found")
            print("   Run enhanced scraper to download images")
            return False
        
        # Show some sample files
        print("📄 Sample files:")
        for i, file in enumerate(image_files[:5]):
            size_kb = file.stat().st_size // 1024
            print(f"   {file.name} ({size_kb} KB)")
        
        # 3. Test specific query searches
        print("\n3. QUERY SEARCH TESTS:")
        
        test_queries = [
            "project setup",
            "timesheet",
            "visual guide for setting up a new project",
            "how to create project"
        ]
        
        for query in test_queries:
            print(f"\n🔍 Testing query: '{query}'")
            
            # Test the exact search logic from FixedImageManager
            query_lower = query.lower()
            
            if 'project' in query_lower and ('setup' in query_lower or 'new' in query_lower or 'create' in query_lower):
                print("   Detected as PROJECT SETUP query")
                
                sql = '''
                SELECT DISTINCT 
                    i.local_filename, i.alt_text, i.caption,
                    d.title, d.category, d.url
                FROM images i
                JOIN documents d ON i.document_url = d.url
                WHERE (
                    (LOWER(d.title) LIKE '%project%' AND (
                        LOWER(d.title) LIKE '%setup%' OR 
                        LOWER(d.title) LIKE '%create%' OR 
                        LOWER(d.title) LIKE '%new%'
                    ))
                    OR 
                    (LOWER(i.alt_text) LIKE '%project%' AND LOWER(i.alt_text) LIKE '%create%')
                )
                AND LOWER(d.title) NOT LIKE '%login%'
                AND LOWER(d.title) NOT LIKE '%password%'
                LIMIT 5
                '''
                
                cursor.execute(sql)
                results = cursor.fetchall()
                print(f"   Found {len(results)} matching images")
                
                for filename, alt_text, caption, doc_title, category, url in results:
                    file_path = images_dir / filename
                    exists = "✅" if file_path.exists() else "❌"
                    print(f"   {exists} {filename} - {doc_title} ({category})")
            
            elif 'timesheet' in query_lower:
                print("   Detected as TIMESHEET query")
                
                sql = '''
                SELECT DISTINCT 
                    i.local_filename, i.alt_text, d.title, d.category
                FROM images i
                JOIN documents d ON i.document_url = d.url
                WHERE (
                    LOWER(d.title) LIKE '%timesheet%' OR 
                    LOWER(i.alt_text) LIKE '%timesheet%'
                )
                AND LOWER(d.title) NOT LIKE '%login%'
                LIMIT 5
                '''
                
                cursor.execute(sql)
                results = cursor.fetchall()
                print(f"   Found {len(results)} matching images")
                
                for filename, alt_text, doc_title, category in results:
                    file_path = images_dir / filename
                    exists = "✅" if file_path.exists() else "❌"
                    print(f"   {exists} {filename} - {doc_title} ({category})")
            
            else:
                print("   General search logic would be used")
        
        # 4. Check for problematic data
        print("\n4. DATA QUALITY CHECK:")
        
        # Check for images with missing files
        cursor.execute('SELECT local_filename FROM images LIMIT 10')
        db_files = [row[0] for row in cursor.fetchall()]
        
        missing_files = []
        for filename in db_files:
            if filename and not (images_dir / filename).exists():
                missing_files.append(filename)
        
        if missing_files:
            print(f"⚠️  {len(missing_files)} images in DB but files missing:")
            for filename in missing_files[:3]:
                print(f"   {filename}")
        else:
            print("✅ All database images have corresponding files")
        
        # 5. Test the actual image manager
        print("\n5. IMAGE MANAGER TEST:")
        
        try:
            # Import and test the actual image manager
            import sys
            sys.path.append('.')
            
            # Test the image manager directly
            from support_system import FixedImageManager
            
            image_manager = FixedImageManager()
            if image_manager.conn:
                test_images = image_manager.get_images_for_query("visual guide for setting up a new project", "project_management", limit=3)
                print(f"   Image manager returned: {len(test_images)} images")
                
                for img in test_images:
                    print(f"   📸 {img.get('local_filename')} - Score: {img.get('relevance_score', 0):.1f}")
                    print(f"      From: {img.get('document_title', 'Unknown')}")
                    file_exists = Path(img.get('local_path', '').replace('/static/', 'static/')).exists()
                    print(f"      File exists: {'✅' if file_exists else '❌'}")
            else:
                print("❌ Image manager has no database connection")
                
        except ImportError as e:
            print(f"❌ Cannot import image manager: {e}")
        except Exception as e:
            print(f"❌ Image manager error: {e}")
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("🎯 DIAGNOSIS COMPLETE")
        
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def fix_common_issues():
    """Suggest fixes for common issues"""
    
    print("\n🔧 COMMON FIXES:")
    print("1. If no images in database:")
    print("   python replicon_scraper.py  # Run enhanced scraper")
    
    print("\n2. If images table missing:")
    print("   python database_migration.py  # Migrate database")
    
    print("\n3. If image files missing:")
    print("   Check static/images/scraped/ directory permissions")
    print("   Re-run scraper to download images")
    
    print("\n4. If images not showing in UI:")
    print("   Check browser console for 404 errors on image URLs")
    print("   Verify FastAPI static file mounting")
    
    print("\n5. Test image serving:")
    print("   Visit: http://localhost:8000/static/images/scraped/")
    print("   Should show directory listing or specific image")

def test_api_endpoint():
    """Test the debug API endpoint"""
    
    print("\n🌐 API ENDPOINT TEST:")
    print("Visit these URLs while your app is running:")
    print("   http://localhost:8000/debug/images?query=project%20setup")
    print("   http://localhost:8000/stats")
    print("   http://localhost:8000/health")

if __name__ == "__main__":
    success = debug_complete_system()
    
    if not success:
        fix_common_issues()
    
    test_api_endpoint()
    
    print("\n🚀 NEXT STEPS:")
    print("1. Fix any issues identified above")
    print("2. Test with: python support_system.py")
    print("3. Try query: 'Visual guide for setting up a new project'")
    print("4. Check browser network tab for image loading errors")