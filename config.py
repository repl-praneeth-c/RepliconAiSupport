# Replicon AI Support System Configuration

SCRAPING_CONFIG = {
    'base_url': 'https://www.replicon.com/help/',
    'delay': 1.0,  # Seconds between requests
    'max_workers': 3,  # Concurrent scraping threads
    'timeout': 10,  # Request timeout in seconds
    'retry_attempts': 3,
    'excluded_patterns': [
        r'/search\?',
        r'/login',
        r'/register',
        r'/contact',
        r'\.pdf$',
        r'\.jpg$',
        r'\.png$',
        r'\.gif$',
        r'/api/',
        r'#'
    ]
}

CLAUDE_CONFIG = {
    'model': 'claude-3-5-sonnet-20241022',
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

# Image processing settings
IMAGE_CONFIG = {
    'enable_images': True,
    'max_image_size_mb': 5,
    'supported_formats': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
    'thumbnail_size': (300, 300),
    'storage_path': 'static/images/scraped'
}

# API response settings
API_CONFIG = {
    'max_response_length': 3000,
    'include_confidence_score': True,
    'include_suggested_actions': True,
    'max_relevant_docs': 3,
    'max_conversation_history': 10
}