#!/usr/bin/env python3
"""
Replicon AI Support System Setup Script
This script sets up the complete end-to-end documentation system.
"""

import os
import sys
from pathlib import Path
import subprocess

def create_directory_structure():
    """Create necessary directories"""
    directories = [
        'templates',
        'static',
        'static/css',
        'static/js',
        'docs',
        'logs'
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"Created directory: {directory}")

def create_requirements_file():
    """Create requirements.txt file"""
    requirements = """
# Core dependencies
fastapi==0.104.1
uvicorn[standard]==0.24.0
anthropic==0.7.8
requests==2.31.0
beautifulsoup4==4.12.2

# HTML templating
jinja2==3.1.2

# Data processing
pandas==2.1.4

# Async support
aiofiles==23.2.0

# Optional: For better text processing
nltk==3.8.1
spacy==3.7.2

# Development
python-multipart==0.0.6
python-dotenv==1.0.0
    """.strip()
    
    with open('requirements.txt', 'w', encoding='utf-8') as f:
        f.write(requirements)
    print("Created requirements.txt")

def create_env_file():
    """Create .env file template"""
    env_content = """
# Replicon AI Support System Configuration

# Claude API Key (Required)
CLAUDE_API_KEY=your_claude_api_key_here

# Application Settings
DEBUG=True
HOST=0.0.0.0
PORT=8000

# Database
DATABASE_PATH=replicon_docs.db

# Scraping Settings
SCRAPE_DELAY=1.0
MAX_WORKERS=3
BASE_URL=https://www.replicon.com/help/

# Logging
LOG_LEVEL=INFO
    """.strip()
    
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)
    print("Created .env file template")

def save_html_template():
    """Save the HTML template to templates directory"""
    # The HTML content from the previous artifact
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Replicon AI Support Assistant</title>
    <!-- CSS content would go here - same as the previous artifact -->
</head>
<body>
    <!-- HTML body content would go here - same as the previous artifact -->
</body>
</html>"""
    
    # Since we already created the full HTML template in the artifact above,
    # we'll reference that users should copy it to templates/support_home.html
    print("Note: Copy the HTML template from the artifact above to templates/support_home.html")

def create_run_script():
    """Create a simple run script"""
    run_script = """#!/usr/bin/env python3
\"\"\"
Simple script to run the Replicon AI Support System
\"\"\"

import os
import sys
from pathlib import Path

def check_setup():
    \"\"\"Check if setup is complete\"\"\"
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
        print("\\nPlease run setup.py first!")
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
"""
    
    with open('run.py', 'w', encoding='utf-8') as f:
        f.write(run_script)
    os.chmod('run.py', 0o755)  # Make executable
    print("Created run.py script")

def create_config_file():
    """Create configuration file"""
    config = """
# Replicon AI Support System Configuration

SCRAPING_CONFIG = {
    'base_url': 'https://www.replicon.com/help/',
    'delay': 1.0,  # Seconds between requests
    'max_workers': 3,  # Concurrent scraping threads
    'timeout': 10,  # Request timeout in seconds
    'retry_attempts': 3,
    'excluded_patterns': [
        r'/search\\?',
        r'/login',
        r'/register',
        r'/contact',
        r'\\.pdf,
        r'\\.jpg,
        r'\\.png,
        r'\\.gif,
        r'/api/',
        r'#'
    ]
}

CLAUDE_CONFIG = {
    'model': 'claude-3-sonnet-20240229',
    'max_tokens': 2000,
    'temperature': 0.1  # Low temperature for consistent responses
}

SUPPORT_CATEGORIES = {
    'timesheet': {
        'keywords': ['timesheet', 'time entry', 'submit time', 'hours', 'clock in', 'clock out'],
        'priority': 1
    },
    'project_management': {
        'keywords': ['project', 'task', 'milestone', 'deadline', 'project setup'],
        'priority': 2
    },
    'billing': {
        'keywords': ['billing', 'invoice', 'rates', 'cost', 'expense', 'charge'],
        'priority': 2
    },
    'compliance': {
        'keywords': ['compliance', 'overtime', 'labor law', 'regulation', 'policy'],
        'priority': 3
    },
    'workforce_management': {
        'keywords': ['schedule', 'shift', 'employee', 'workforce', 'attendance'],
        'priority': 2
    },
    'integration': {
        'keywords': ['integration', 'api', 'sync', 'import', 'export', 'connect'],
        'priority': 3
    },
    'reporting': {
        'keywords': ['report', 'analytics', 'dashboard', 'metrics', 'data'],
        'priority': 2
    },
    'mobile': {
        'keywords': ['mobile', 'app', 'phone', 'ios', 'android'],
        'priority': 2
    },
    'troubleshooting': {
        'keywords': ['error', 'issue', 'problem', 'fix', 'not working', 'broken'],
        'priority': 1
    }
}
    """.strip()
    
    with open('config.py', 'w', encoding='utf-8') as f:
        f.write(config)
    print("Created config.py")

def install_dependencies():
    """Install Python dependencies"""
    print("Installing Python dependencies...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        print("Please install manually: pip install -r requirements.txt")

def create_readme():
    """Create README.md with instructions"""
    readme_content = """# Replicon AI Support System

An AI-powered support system that scrapes Replicon's documentation and provides intelligent responses using Claude AI.

## 🚀 Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up your Claude API Key**
   - Edit `.env` file
   - Replace `your_claude_api_key_here` with your actual Claude API key

3. **Copy HTML Template**
   - Copy the HTML template from the artifacts to `templates/support_home.html`

4. **Run the System**
   ```bash
   python run.py
   ```

## 📁 Project Structure

```
replicon-ai-support/
├── replicon_scraper.py      # Documentation scraper
├── support_system.py        # Main FastAPI application
├── run.py                   # Easy run script
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables
├── templates/
│   └── support_home.html   # Web interface template
├── static/                 # Static files (CSS, JS)
├── docs/                   # Scraped documentation (JSON)
└── replicon_docs.db       # SQLite database
```

## 🛠️ Components

### 1. Documentation Scraper (`replicon_scraper.py`)
- Automatically discovers and scrapes Replicon help documentation
- Categorizes content intelligently
- Stores in SQLite database for fast searching
- Respects rate limits and robots.txt

### 2. AI Support System (`support_system.py`)
- FastAPI web application
- Claude AI integration for intelligent responses
- Context-aware responses based on user role and module
- Confidence scoring and escalation detection

### 3. Web Interface
- Clean, modern UI
- Real-time AI responses
- Suggested actions and relevant documentation
- Mobile-friendly design

## 📊 Features

- **Smart Documentation Scraping**: Automatically builds knowledge base
- **Context-Aware AI**: Responses tailored to user role and Replicon module
- **Confidence Scoring**: AI assesses its own response quality
- **Escalation Detection**: Identifies when human support is needed
- **Relevant Documentation**: Shows related help articles
- **Suggested Actions**: Provides actionable next steps
- **Search Functionality**: Direct documentation search
- **Analytics**: Track common issues and response quality

## 🔧 Configuration

Edit `config.py` to customize:
- Scraping behavior
- Claude AI settings
- Category definitions
- Response thresholds

## 🚦 Usage

1. **First Run**: The system will offer to scrape documentation
2. **Web Interface**: Visit http://localhost:8000
3. **Ask Questions**: Type natural language questions about Replicon
4. **Get AI Responses**: Receive intelligent, contextual answers

## 📈 Monitoring

- Check scraping statistics at `/stats` endpoint
- Monitor response quality and user satisfaction
- Track common issues for documentation improvements

## 🔐 Security

- API keys stored in environment variables
- Rate limiting on scraping
- Input validation and sanitization
- HTTPS ready for production

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📝 License

MIT License - see LICENSE file for details

## 💡 Tips

- **Better Responses**: Include your role and specific Replicon module
- **Complex Issues**: Provide detailed context and steps already tried
- **Documentation**: Check the suggested documentation links for deeper info
- **Feedback**: Use confidence scores to gauge response reliability

## 🆘 Support

- Check the `/stats` endpoint for system health
- Review logs in the `logs/` directory
- For Claude API issues, check your API key and usage limits
- For scraping issues, verify the target website is accessible

---

Built with ❤️ using FastAPI, Claude AI, and modern web technologies.
"""
    
    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print("Created README.md")

def main():
    """Main setup function"""
    print("Setting up Replicon AI Support System...")
    print("=" * 50)
    
    # Create directory structure
    create_directory_structure()
    
    # Create configuration files
    create_requirements_file()
    create_env_file()
    create_config_file()
    
    # Create scripts
    create_run_script()
    
    # Create documentation
    create_readme()
    
    # Install dependencies
    install_dependencies()
    
    print("\n" + "=" * 50)
    print("Setup completed successfully!")
    print("\nNext Steps:")
    print("1. Copy the HTML template from the artifacts to templates/support_home.html")
    print("2. Copy the scraper code to replicon_scraper.py")
    print("3. Copy the support system code to support_system.py")
    print("4. Edit .env file and add your Claude API key")
    print("5. Run: python run.py")
    print("\nThe system will be available at http://localhost:8000")
    print("\nRead README.md for detailed instructions")

if __name__ == "__main__":
    main()