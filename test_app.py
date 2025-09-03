#!/usr/bin/env python3
"""
Minimal test version of Replicon AI Support System
Use this to test if the basic setup works
"""

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sqlite3
import json
from datetime import datetime

# Create FastAPI app
app = FastAPI(title="Replicon AI Support System", version="1.0.0")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Mount static files if directory exists
if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with support form"""
    try:
        return templates.TemplateResponse("support_home.html", {"request": request})
    except Exception as e:
        return HTMLResponse(f"""
        <html>
            <head><title>Replicon AI Support</title></head>
            <body>
                <h1>Replicon AI Support System</h1>
                <p>Template error: {str(e)}</p>
                <p>Please ensure templates/support_home.html exists</p>
                <form method="post" action="/ask">
                    <textarea name="query" placeholder="Ask your question here..." rows="4" cols="50"></textarea><br><br>
                    <button type="submit">Ask AI</button>
                </form>
            </body>
        </html>
        """)

@app.post("/ask")
async def ask_support(query: str = Form(...)):
    """Process support query - minimal version"""
    try:
        # Simple response without Claude for testing
        response_text = f"""
        Thank you for your question: "{query}"
        
        This is a test response. The system is working!
        
        To enable AI responses:
        1. Make sure your Claude API key is set in .env
        2. Ensure the full support_system.py is working
        3. Check that the documentation database exists
        
        Common Replicon help topics:
        - Timesheet submission
        - Project management
        - Billing and rates
        - Mobile app usage
        - Time-off requests
        """
        
        return {
            "success": True,
            "response": response_text,
            "confidence": 0.5,
            "relevant_docs": [],
            "suggested_actions": ["Check the full system setup"],
            "escalation_needed": False,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/test")
async def test_endpoint():
    """Test endpoint to verify the server is working"""
    return {
        "status": "working",
        "message": "Replicon AI Support System is running!",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/stats")
async def get_stats():
    """Get basic statistics"""
    try:
        # Check if database exists
        db_path = Path("replicon_docs.db")
        if db_path.exists():
            conn = sqlite3.connect("replicon_docs.db")
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM documents')
            total_docs = cursor.fetchone()[0]
            
            cursor.execute('SELECT category, COUNT(*) FROM documents GROUP BY category ORDER BY COUNT(*) DESC')
            categories = dict(cursor.fetchall())
            
            conn.close()
            
            return {
                "total_documents": total_docs,
                "categories": categories,
                "database_exists": True,
                "last_updated": datetime.now().isoformat()
            }
        else:
            return {
                "total_documents": 0,
                "categories": {},
                "database_exists": False,
                "message": "No documentation database found. Run scraper first.",
                "last_updated": datetime.now().isoformat()
            }
            
    except Exception as e:
        return {
            "error": str(e),
            "database_exists": False,
            "last_updated": datetime.now().isoformat()
        }

# Run with: uvicorn test_app:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    print("Starting Replicon AI Support System (Test Mode)...")
    print("Visit http://localhost:8000 in your browser")
    uvicorn.run(app, host="0.0.0.0", port=8000)