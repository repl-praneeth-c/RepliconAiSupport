#!/usr/bin/env python3
"""
Simple script to run the Replicon AI Support System
"""

import os
import sys
from pathlib import Path

def check_setup():
    """Check if setup is complete"""
    required_files = [
        'replicon_scraper.py',
        'support_system.py',
        'templates/support_home.html',
        '.env'
    ]
    
    missing = []
    for file in required_files:
        if not Path(file).exists():
            missing.append(file)
    
    if missing:
        print("Missing required files:")
        for file in missing:
            print(f"   - {file}")
        print("\nPlease run setup.py first!")
        sys.exit(1)
    
    # Check if .env has API key
    with open('.env', 'r') as f:
        env_content = f.read()
        if 'your_claude_api_key_here' in env_content:
            print("Warning: Please set your Claude API key in .env file")
            print("   Replace 'your_claude_api_key_here' with your actual API key")

def main():
    print("Starting Replicon AI Support System...")
    
    check_setup()
    
    # Check if database exists
    if not Path('replicon_docs.db').exists():
        print("No documentation database found.")
        response = input("Do you want to scrape documentation now? (y/n): ")
        if response.lower() in ['y', 'yes']:
            print("Starting documentation scraper...")
            import replicon_scraper
            scraper = replicon_scraper.RepliconDocumentationScraper()
            try:
                scraper.scrape_all_documentation()
                stats = scraper.get_stats()
                print(f"Scraped {stats['total_documents']} documents")
                scraper.export_to_json()
            except Exception as e:
                print(f"Scraping failed: {e}")
            finally:
                scraper.close()
        else:
            print("Running without documentation database")
    
    # Start the FastAPI server
    print("Starting web server...")
    import uvicorn
    import support_system
    
    uvicorn.run(
        "support_system:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

if __name__ == "__main__":
    main()
