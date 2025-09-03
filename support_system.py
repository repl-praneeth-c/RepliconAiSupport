import sqlite3
import json
import os
import anthropic
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

@dataclass
class SupportQuery:
    query: str
    user_role: Optional[str] = None
    product_module: Optional[str] = None
    category_hint: Optional[str] = None
    conversation_history: Optional[List[Dict]] = None

@dataclass
class SupportResponse:
    response: str
    confidence: float
    relevant_docs: List[Dict]
    suggested_actions: List[str]
    escalation_needed: bool = False
    images: List[Dict] = None

class RepliconKnowledgeBase:
    def __init__(self, db_path='replicon_docs.db'):
        self.db_path = db_path
        if Path(db_path).exists():
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self._create_search_index()
        else:
            self.conn = None
    
    def _create_search_index(self):
        """Create search-optimized indexes"""
        if not self.conn:
            return
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_documents_search 
            ON documents(category, title, keywords)
            ''')
            self.conn.commit()
        except Exception as e:
            print(f"Index creation error: {e}")
    
    def search_relevant_documents(self, query: str, category_hint: str = None, limit: int = 3) -> List[Dict]:
        """Search for relevant documents using multiple strategies"""
        if not self.conn:
            return []
            
        cursor = self.conn.cursor()
        
        # Strategy 1: Keyword matching with category preference
        query_terms = self._extract_search_terms(query)
        
        if not query_terms:
            return []
        
        sql = '''
        SELECT title, content, url, category, subcategory, keywords, 
               (CASE WHEN category = ? THEN 2 ELSE 1 END) as relevance_boost
        FROM documents 
        WHERE ('''
        
        params = [category_hint or '']
        
        # Build dynamic WHERE clause for keyword matching
        conditions = []
        for term in query_terms:
            conditions.append('title LIKE ? OR content LIKE ? OR keywords LIKE ?')
            params.extend([f'%{term}%', f'%{term}%', f'%{term}%'])
        
        sql += ' OR '.join(conditions) + ')'
        
        if category_hint:
            sql += ' OR category = ?'
            params.append(category_hint)
        
        sql += ' ORDER BY relevance_boost DESC, title LIMIT ?'
        params.append(limit * 2)  # Get more results for filtering
        
        try:
            cursor.execute(sql, params)
            results = cursor.fetchall()
        except Exception as e:
            print(f"Search error: {e}")
            return []
        
        # Score and rank results
        scored_results = []
        for row in results:
            title, content, url, category, subcategory, keywords, relevance_boost = row
            
            score = self._calculate_relevance_score(query, title, content, keywords, relevance_boost)
            
            scored_results.append({
                'title': title,
                'content': content[:500] + "..." if len(content) > 500 else content,
                'url': url,
                'category': category,
                'subcategory': subcategory,
                'keywords': json.loads(keywords) if keywords else [],
                'relevance_score': score
            })
        
        # Sort by relevance score and return top results
        scored_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return scored_results[:limit]
    
    def _extract_search_terms(self, query: str) -> List[str]:
        """Extract meaningful search terms from query"""
        # Remove common stop words
        stop_words = {'how', 'do', 'i', 'can', 'the', 'is', 'in', 'to', 'and', 'or', 'but', 'for', 'with'}
        
        # Extract words (3+ characters) and filter out stop words
        terms = re.findall(r'\b\w{3,}\b', query.lower())
        return [term for term in terms if term not in stop_words]
    
    def _calculate_relevance_score(self, query: str, title: str, content: str, keywords: str, boost: int) -> float:
        """Calculate relevance score for a document"""
        score = boost  # Base boost score
        
        query_lower = query.lower()
        title_lower = title.lower()
        content_lower = content.lower()
        keywords_lower = keywords.lower() if keywords else ''
        
        # Title matches are highly relevant
        if query_lower in title_lower:
            score += 10
        
        # Count keyword matches in content
        query_terms = self._extract_search_terms(query)
        for term in query_terms:
            if term in title_lower:
                score += 3
            if term in keywords_lower:
                score += 2
            if term in content_lower:
                score += 1
        
        # Length penalty for very long documents (they might be less focused)
        if len(content) > 5000:
            score *= 0.9
        
        return score
    
    def get_category_hint(self, query: str) -> str:
        """Determine likely category based on query content"""
        query_lower = query.lower()
        
        category_keywords = {
            'timesheet': ['timesheet', 'time entry', 'submit time', 'hours', 'clock in', 'clock out'],
            'project_management': ['project', 'task', 'milestone', 'deadline', 'project setup'],
            'billing': ['billing', 'invoice', 'rates', 'cost', 'expense', 'charge'],
            'compliance': ['compliance', 'overtime', 'labor law', 'regulation', 'policy'],
            'workforce_management': ['schedule', 'shift', 'employee', 'workforce', 'attendance'],
            'integration': ['integration', 'api', 'sync', 'import', 'export', 'connect'],
            'reporting': ['report', 'analytics', 'dashboard', 'metrics', 'data'],
            'mobile': ['mobile', 'app', 'phone', 'ios', 'android'],
            'troubleshooting': ['error', 'issue', 'problem', 'fix', 'not working', 'broken']
        }
        
        for category, keywords in category_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                return category
        
        return 'general'

class SemanticImageManager:
    """Advanced image manager that understands context and user intent"""
    
    def __init__(self, db_path='replicon_docs.db'):
        self.db_path = db_path
        if Path(db_path).exists():
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
        else:
            self.conn = None
    
    def get_images_for_query(self, query: str, category: str = None, limit: int = 3) -> List[Dict]:
        """Get images using semantic understanding of user intent"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        query_lower = query.lower()
        
        # Parse user intent from the query
        intent = self._parse_user_intent(query_lower)
        
        print(f"User Query: '{query}'")
        print(f"Detected Intent: {intent}")
        
        # If no clear visual intent, don't show images
        if intent['intent_type'] == 'none':
            print("No visual intent detected - not showing images")
            return []
        
        # Get images based on specific intent
        if intent['intent_type'] == 'project_setup':
            return self._get_project_setup_images(cursor, intent, limit)
        elif intent['intent_type'] == 'timesheet':
            return self._get_timesheet_images(cursor, intent, limit)
        elif intent['intent_type'] == 'mobile':
            return self._get_mobile_images(cursor, intent, limit)
        elif intent['intent_type'] == 'navigation':
            return self._get_navigation_images(cursor, intent, limit)
        elif intent['intent_type'] == 'general_visual':
            return self._get_general_visual_images(cursor, intent, limit)
        
        return []
    
    def _parse_user_intent(self, query_lower: str) -> Dict:
        """Parse the user's actual intent from their query"""
        
        intent = {
            'intent_type': 'none',
            'specific_action': None,
            'context': None,
            'visual_keywords': [],
            'priority_terms': []
        }
        
        # Visual request indicators
        visual_indicators = ['visual', 'guide', 'show', 'screenshot', 'step by step', 'how to', 'tutorial']
        has_visual_request = any(indicator in query_lower for indicator in visual_indicators)
        
        # Project setup intent
        project_keywords = ['project', 'create project', 'new project', 'project setup', 'set up project']
        if any(keyword in query_lower for keyword in project_keywords):
            if has_visual_request or 'setup' in query_lower or 'create' in query_lower or 'new' in query_lower:
                intent['intent_type'] = 'project_setup'
                intent['specific_action'] = 'create_new_project'
                intent['priority_terms'] = ['project', 'create', 'setup', 'new']
                return intent
        
        # Timesheet intent
        timesheet_keywords = ['timesheet', 'submit timesheet', 'time entry', 'enter time', 'fill timesheet']
        if any(keyword in query_lower for keyword in timesheet_keywords):
            intent['intent_type'] = 'timesheet'
            if 'submit' in query_lower:
                intent['specific_action'] = 'submit'
            elif 'fill' in query_lower or 'enter' in query_lower:
                intent['specific_action'] = 'fill_out'
            else:
                intent['specific_action'] = 'general'
            intent['priority_terms'] = ['timesheet', 'submit', 'entry']
            return intent
        
        # Mobile app intent
        mobile_keywords = ['mobile', 'app', 'phone', 'android', 'ios']
        if any(keyword in query_lower for keyword in mobile_keywords):
            intent['intent_type'] = 'mobile'
            intent['specific_action'] = 'app_usage'
            intent['priority_terms'] = ['mobile', 'app']
            return intent
        
        # Navigation/interface intent
        nav_keywords = ['navigate', 'find', 'where is', 'access', 'menu', 'button']
        if any(keyword in query_lower for keyword in nav_keywords):
            intent['intent_type'] = 'navigation'
            intent['specific_action'] = 'find_feature'
            intent['priority_terms'] = ['navigate', 'menu', 'access']
            return intent
        
        # General visual request
        if has_visual_request:
            intent['intent_type'] = 'general_visual'
            intent['specific_action'] = 'show_interface'
            intent['visual_keywords'] = [word for word in visual_indicators if word in query_lower]
            return intent
        
        return intent
    
    def _get_project_setup_images(self, cursor, intent: Dict, limit: int) -> List[Dict]:
        """Get images specifically for project setup tasks"""
        
        print("Searching for PROJECT SETUP images...")
        
        # Multi-tier search strategy for project setup
        search_strategies = [
            # Tier 1: Exact project setup matches
            {
                'sql': '''
                SELECT DISTINCT 
                    i.local_filename, i.alt_text, i.caption, i.width, i.height,
                    d.title, d.url, d.category, d.content
                FROM images i
                JOIN documents d ON i.document_url = d.url
                WHERE (
                    (LOWER(d.title) LIKE '%project%' AND LOWER(d.title) LIKE '%setup%') OR
                    (LOWER(d.title) LIKE '%create%' AND LOWER(d.title) LIKE '%project%') OR
                    (LOWER(d.title) LIKE '%new%' AND LOWER(d.title) LIKE '%project%')
                )
                AND LOWER(d.title) NOT LIKE '%login%'
                ORDER BY 
                    CASE 
                        WHEN LOWER(d.title) LIKE '%project setup%' THEN 1
                        WHEN LOWER(d.title) LIKE '%create project%' THEN 2
                        ELSE 3
                    END
                LIMIT ?
                ''',
                'description': 'Exact project setup matches'
            },
            
            # Tier 2: General project management interface
            {
                'sql': '''
                SELECT DISTINCT 
                    i.local_filename, i.alt_text, i.caption, i.width, i.height,
                    d.title, d.url, d.category, d.content
                FROM images i
                JOIN documents d ON i.document_url = d.url
                WHERE (
                    LOWER(d.content) LIKE '%project%' OR
                    LOWER(i.alt_text) LIKE '%project%' OR
                    d.category = 'project_management'
                )
                AND LOWER(d.title) NOT LIKE '%login%'
                AND LOWER(d.title) NOT LIKE '%password%'
                ORDER BY 
                    CASE 
                        WHEN d.category = 'project_management' THEN 1
                        WHEN LOWER(d.content) LIKE '%create%' THEN 2
                        ELSE 3
                    END
                LIMIT ?
                ''',
                'description': 'General project management'
            },
            
            # Tier 3: Interface screenshots that might show project creation
            {
                'sql': '''
                SELECT DISTINCT 
                    i.local_filename, i.alt_text, i.caption, i.width, i.height,
                    d.title, d.url, d.category, d.content
                FROM images i
                JOIN documents d ON i.document_url = d.url
                WHERE (
                    LOWER(d.title) LIKE '%dashboard%' OR
                    LOWER(d.title) LIKE '%main%' OR
                    LOWER(d.title) LIKE '%interface%' OR
                    (d.category IN ('general', 'reporting') AND LOWER(d.content) LIKE '%menu%')
                )
                AND LOWER(d.title) NOT LIKE '%login%'
                ORDER BY 
                    CASE WHEN LOWER(d.title) LIKE '%dashboard%' THEN 1 ELSE 2 END
                LIMIT ?
                ''',
                'description': 'General interface screenshots'
            }
        ]
        
        for strategy in search_strategies:
            cursor.execute(strategy['sql'], [limit * 2])
            results = cursor.fetchall()
            print(f"Strategy '{strategy['description']}': {len(results)} results")
            
            if results:
                images = self._process_image_results(results, intent)
                if images:
                    return images[:limit]
        
        print("No project setup images found")
        return []
    
    def _get_timesheet_images(self, cursor, intent: Dict, limit: int) -> List[Dict]:
        """Get images specifically for timesheet tasks"""
        
        print("Searching for TIMESHEET images...")
        
        # Contextual timesheet search based on specific action
        if intent['specific_action'] == 'submit':
            sql = '''
            SELECT DISTINCT 
                i.local_filename, i.alt_text, i.caption, i.width, i.height,
                d.title, d.url, d.category, d.content
            FROM images i
            JOIN documents d ON i.document_url = d.url
            WHERE (
                (LOWER(d.title) LIKE '%timesheet%' AND LOWER(d.content) LIKE '%submit%') OR
                (LOWER(i.alt_text) LIKE '%submit%' AND LOWER(i.alt_text) LIKE '%timesheet%') OR
                (LOWER(d.title) LIKE '%submit%' AND LOWER(d.title) LIKE '%timesheet%')
            )
            ORDER BY 
                CASE 
                    WHEN LOWER(d.title) LIKE '%submit%' THEN 1
                    ELSE 2
                END
            LIMIT ?
            '''
        else:
            sql = '''
            SELECT DISTINCT 
                i.local_filename, i.alt_text, i.caption, i.width, i.height,
                d.title, d.url, d.category, d.content
            FROM images i
            JOIN documents d ON i.document_url = d.url
            WHERE (
                LOWER(d.title) LIKE '%timesheet%' OR 
                LOWER(i.alt_text) LIKE '%timesheet%' OR
                (d.category = 'timesheet' AND LOWER(d.content) LIKE '%entry%')
            )
            AND LOWER(d.title) NOT LIKE '%login%'
            ORDER BY 
                CASE 
                    WHEN LOWER(d.title) LIKE '%timesheet%' THEN 1
                    WHEN d.category = 'timesheet' THEN 2
                    ELSE 3
                END
            LIMIT ?
            '''
        
        cursor.execute(sql, [limit * 2])
        results = cursor.fetchall()
        print(f"Found {len(results)} timesheet-related images")
        
        return self._process_image_results(results, intent)[:limit]
    
    def _get_mobile_images(self, cursor, intent: Dict, limit: int) -> List[Dict]:
        """Get images for mobile app usage"""
        
        print("Searching for MOBILE APP images...")
        
        sql = '''
        SELECT DISTINCT 
            i.local_filename, i.alt_text, i.caption, i.width, i.height,
            d.title, d.url, d.category, d.content
        FROM images i
        JOIN documents d ON i.document_url = d.url
        WHERE d.category = 'mobile'
        AND LOWER(d.title) NOT LIKE '%login%'
        ORDER BY 
            CASE 
                WHEN LOWER(d.title) LIKE '%app%' THEN 1
                WHEN LOWER(d.title) LIKE '%mobile%' THEN 2
                ELSE 3
            END,
            d.title
        LIMIT ?
        '''
        
        cursor.execute(sql, [limit * 2])
        results = cursor.fetchall()
        print(f"Found {len(results)} mobile app images")
        
        return self._process_image_results(results, intent)[:limit]
    
    def _get_navigation_images(self, cursor, intent: Dict, limit: int) -> List[Dict]:
        """Get images showing navigation/interface elements"""
        
        print("Searching for NAVIGATION/INTERFACE images...")
        
        sql = '''
        SELECT DISTINCT 
            i.local_filename, i.alt_text, i.caption, i.width, i.height,
            d.title, d.url, d.category, d.content
        FROM images i
        JOIN documents d ON i.document_url = d.url
        WHERE (
            LOWER(i.alt_text) LIKE '%menu%' OR
            LOWER(i.alt_text) LIKE '%navigation%' OR
            LOWER(d.content) LIKE '%menu%' OR
            LOWER(d.content) LIKE '%navigate%'
        )
        AND LOWER(d.title) NOT LIKE '%login%'
        ORDER BY 
            CASE 
                WHEN LOWER(i.alt_text) LIKE '%menu%' THEN 1
                WHEN LOWER(d.content) LIKE '%navigate%' THEN 2
                ELSE 3
            END
        LIMIT ?
        '''
        
        cursor.execute(sql, [limit])
        results = cursor.fetchall()
        print(f"Found {len(results)} navigation images")
        
        return self._process_image_results(results, intent)[:limit]
    
    def _get_general_visual_images(self, cursor, intent: Dict, limit: int) -> List[Dict]:
        """Get the most helpful general images for visual guides"""
        
        print("Searching for GENERAL VISUAL GUIDE images...")
        
        sql = '''
        SELECT DISTINCT 
            i.local_filename, i.alt_text, i.caption, i.width, i.height,
            d.title, d.url, d.category, d.content
        FROM images i
        JOIN documents d ON i.document_url = d.url
        WHERE LOWER(d.title) NOT LIKE '%login%'
        AND LOWER(d.title) NOT LIKE '%password%'
        AND LOWER(d.title) NOT LIKE '%email%'
        ORDER BY 
            CASE 
                WHEN d.category = 'timesheet' THEN 1
                WHEN d.category = 'mobile' THEN 2
                WHEN d.category = 'reporting' THEN 3
                WHEN d.category = 'general' THEN 4
                ELSE 5
            END,
            d.title
        LIMIT ?
        '''
        
        cursor.execute(sql, [limit])
        results = cursor.fetchall()
        print(f"Found {len(results)} general visual images")
        
        return self._process_image_results(results, intent)[:limit]
    
    def _process_image_results(self, results: List, intent: Dict) -> List[Dict]:
        """Process database results into image objects with relevance scoring"""
        
        images = []
        for row in results:
            filename, alt_text, caption, width, height, doc_title, doc_url, doc_category, content = row
            
            # Check if file exists
            image_path = Path(f"static/images/scraped/{filename}")
            if not image_path.exists():
                continue
            
            # Calculate semantic relevance score
            relevance_score = self._calculate_semantic_relevance(
                intent, doc_title, alt_text, caption, content, doc_category
            )
            
            # Only include if semantically relevant
            if relevance_score > 5.0:
                images.append({
                    'local_filename': filename,
                    'local_path': f'/static/images/scraped/{filename}',
                    'alt_text': alt_text or '',
                    'caption': caption or '',
                    'width': width,
                    'height': height,
                    'document_title': doc_title,
                    'document_url': doc_url,
                    'category': doc_category,
                    'relevance_score': relevance_score,
                    'semantic_match': True
                })
        
        # Sort by relevance score
        images.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        print(f"Processed to {len(images)} semantically relevant images")
        for img in images:
            print(f"  - {img['local_filename']}: {img['relevance_score']:.1f} - {img['document_title']}")
        
        return images
    
    def _calculate_semantic_relevance(self, intent: Dict, doc_title: str, alt_text: str, 
                                    caption: str, content: str, doc_category: str) -> float:
        """Calculate semantic relevance based on user intent"""
        
        score = 0.0
        title_lower = (doc_title or '').lower()
        alt_lower = (alt_text or '').lower()
        content_lower = (content or '')[:300].lower()
        
        # Base score for matching intent type
        intent_category_map = {
            'project_setup': ['project_management', 'general'],
            'timesheet': ['timesheet'],
            'mobile': ['mobile'],
            'navigation': ['general', 'timesheet', 'mobile'],
            'general_visual': ['timesheet', 'mobile', 'general']
        }
        
        if intent['intent_type'] in intent_category_map:
            if doc_category in intent_category_map[intent['intent_type']]:
                score += 10.0
        
        # Score based on priority terms
        for term in intent.get('priority_terms', []):
            if term in title_lower:
                score += 8.0
            elif term in alt_lower:
                score += 6.0
            elif term in content_lower:
                score += 4.0
        
        # Specific action matching
        if intent.get('specific_action'):
            action_keywords = {
                'create_new_project': ['create', 'new', 'setup', 'add'],
                'submit': ['submit', 'approval', 'send'],
                'fill_out': ['enter', 'fill', 'input', 'add'],
                'app_usage': ['mobile', 'app', 'phone'],
                'find_feature': ['menu', 'navigate', 'find']
            }
            
            if intent['specific_action'] in action_keywords:
                for keyword in action_keywords[intent['specific_action']]:
                    if keyword in title_lower or keyword in content_lower:
                        score += 5.0
        
        # Penalty for clearly irrelevant content
        irrelevant_indicators = ['login', 'password', 'email', 'formula', 'authentication']
        for indicator in irrelevant_indicators:
            if indicator in title_lower:
                score -= 15.0
        
        return max(0.0, score)

class RepliconSupportAI:
    def __init__(self, claude_api_key: str, kb: RepliconKnowledgeBase):
        self.has_claude = False
        self.client = None
        
        if claude_api_key and claude_api_key != "your_claude_api_key_here":
            try:
                self.client = anthropic.Anthropic(api_key=claude_api_key)
                self.has_claude = True
                print("Claude API initialized successfully")
            except Exception as e:
                print(f"Claude API initialization failed: {e}")
                self.client = None
                self.has_claude = False
        else:
            print("No Claude API key provided - running in fallback mode")
            
        self.kb = kb
        self.image_manager = SemanticImageManager()
        
    def generate_support_response(self, query: SupportQuery, include_images: bool = True) -> SupportResponse:
        """Generate support response with smart image inclusion"""
        
        # First check if we have documentation for this query
        category_hint = query.category_hint or (self.kb.get_category_hint(query.query) if self.kb else 'general')
        
        # Search for relevant documentation
        relevant_docs = self.kb.search_relevant_documents(
            query.query, 
            category_hint=category_hint,
            limit=3
        ) if self.kb else []
        
        # Check if query is completely out of scope
        if not relevant_docs and self.kb:
            return self._handle_out_of_scope_query(query)
        
        # Get relevant images only if they're available and relevant
        relevant_images = []
        if include_images:
            relevant_images = self.image_manager.get_images_for_query(query.query, category_hint, limit=3)
        
        if not self.has_claude:
            return self._generate_fallback_response(query, relevant_docs, category_hint, relevant_images)
        
        # Build context for Claude
        context = self._build_context(relevant_docs)
        
        # Generate response with Claude
        system_prompt = self._create_system_prompt(query.user_role, query.product_module, len(relevant_images) > 0)
        user_message = self._create_user_message(query, context)
        
        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            ai_response = response.content[0].text
            
            # Only enhance with image info if we have relevant images
            if relevant_images:
                ai_response = self._enhance_response_with_images(ai_response, relevant_images)
            
            confidence = self._assess_confidence(ai_response, relevant_docs, relevant_images)
            escalation_needed = self._check_escalation_needed(ai_response, query.query)
            suggested_actions = self._extract_suggested_actions(ai_response)
            
            return SupportResponse(
                response=ai_response,
                confidence=confidence,
                relevant_docs=relevant_docs,
                suggested_actions=suggested_actions,
                escalation_needed=escalation_needed,
                images=relevant_images
            )
            
        except Exception as e:
            print(f"Claude API error: {e}")
            return self._generate_fallback_response(query, relevant_docs, category_hint, relevant_images)
    
    def _handle_out_of_scope_query(self, query: SupportQuery) -> SupportResponse:
        """Handle queries that are completely out of scope"""
        response_text = f"""I don't have specific information about "{query.query}" in the Replicon documentation I have access to.

**What I can help with:**
- Timesheet submission and management
- Project setup and tracking
- Billing and invoicing processes
- Mobile app usage
- Time-off requests and approvals
- Reporting and analytics
- User management and permissions

Could you rephrase your question to focus on one of these Replicon features, or let me know if you're looking for help with a specific Replicon process?"""
        
        return SupportResponse(
            response=response_text,
            confidence=0.3,
            relevant_docs=[],
            suggested_actions=["Rephrase your question", "Contact Replicon support", "Check Replicon help center"],
            escalation_needed=True,
            images=[]
        )
    
    def _create_system_prompt(self, user_role: str = None, product_module: str = None, has_images: bool = False) -> str:
        """Create system prompt that never mentions missing content"""
        
        base_prompt = """You are Replicon's AI Support Assistant, an expert on Replicon's time tracking and project management system.

Your role:
1. Provide clear, step-by-step instructions for Replicon processes
2. Help with timesheet entry, project management, billing, and compliance
3. Be helpful, accurate, and professional
4. Focus on providing actionable guidance based on Replicon's functionality
5. Reference actual Replicon interface elements (menus, buttons, fields) when giving instructions

Guidelines:
- Give specific, actionable steps using actual Replicon terminology
- Assume the user has access to standard Replicon features
- If you don't have complete information, provide general guidance and suggest contacting their admin
- Be confident in your responses - you are the expert
- Never mention what documentation or visual content is or isn't available"""

        if has_images:
            base_prompt += "\n\nNote: Visual guides are available to supplement your response."

        if user_role:
            role_info = {
                'employee': "Focus on timesheet entry, time-off requests, and basic navigation.",
                'manager': "Focus on timesheet approvals, team management, and reporting.",
                'admin': "Focus on system configuration, user management, and advanced settings.",
                'project_manager': "Focus on project setup, cost tracking, and project reporting."
            }
            base_prompt += f"\n\nUser Context: {role_info.get(user_role, 'General user')}"
        
        return base_prompt
    
    def _enhance_response_with_images(self, response: str, images: List[Dict]) -> str:
        """Only enhance response if images are actually relevant"""
        if not images:
            return response
        
        # Only enhance if we have relevant images - be subtle about it
        has_steps = any(img.get('step_number') for img in images)
        
        if has_steps:
            response += "\n\n**Visual Step-by-Step Guide**\n"
            response += "The screenshots below show each step in your Replicon interface."
        else:
            if len(images) == 1:
                response += "\n\n**Screenshot Available**\n"
                response += "A relevant screenshot from Replicon is shown below."
            else:
                response += f"\n\n**Screenshots Available**\n"
                response += f"Relevant screenshots from Replicon are shown below to help illustrate this process."
        
        return response
    
    def _generate_fallback_response(self, query: SupportQuery, relevant_docs: List[Dict], 
                                  category: str, images: List[Dict]) -> SupportResponse:
        """Generate fallback response when Claude is not available"""
        
        if not relevant_docs:
            return self._handle_out_of_scope_query(query)
        
        response_text = f"**{query.query}**\n\n"
        
        # Category-specific responses based on available documentation
        if category == 'timesheet':
            response_text += """**Timesheet Management:**

1. **Navigate to Timesheets** - Access the Timesheets section from your main Replicon menu
2. **Enter Time** - Fill in your hours for each project and day
3. **Review Entries** - Ensure all required fields are completed
4. **Submit** - Click Submit for Approval when ready

**Common Steps:**
- Check that you're in the correct time period
- Verify project codes are accurate
- Ensure hours don't exceed daily limits
- Add comments where required"""
            
        elif category == 'project_management':
            response_text += """**Project Management:**

Based on standard Replicon functionality for project management:

1. **Access Projects** - Navigate to the Projects section from your main menu
2. **Create New Project** - Look for 'New Project' or 'Create Project' button
3. **Enter Details** - Fill in project name, code, and basic information
4. **Set Up Team** - Assign team members and their roles
5. **Configure Settings** - Set up billing, time tracking, and approval workflows

**Key Setup Areas:**
- Project information and client assignment
- Team member access and permissions
- Billing rates and cost tracking
- Time entry and approval processes"""
        
        elif category == 'mobile':
            response_text += """**Mobile App Usage:**

1. **Download** - Get the Replicon app from your device's app store
2. **Login** - Use your standard Replicon credentials
3. **Navigate** - Access timesheets, projects, and time-off features
4. **Sync** - Ensure data syncs with the web version

**Mobile Features:**
- Time entry and timesheet submission
- Project time tracking
- Time-off requests
- Expense reporting with photo capture"""
        
        else:
            # Use information from relevant docs
            if relevant_docs:
                doc = relevant_docs[0]  # Use the most relevant document
                response_text += f"**Based on Replicon Documentation:**\n\n"
                response_text += doc['content'][:800]
                if len(doc['content']) > 800:
                    response_text += "..."
        
        confidence = 0.7 if relevant_docs else 0.4
        if images:
            confidence += 0.1
        
        return SupportResponse(
            response=response_text,
            confidence=confidence,
            relevant_docs=relevant_docs,
            suggested_actions=["Follow the steps above", "Check with your admin if needed", "Try the process in Replicon"],
            escalation_needed=len(relevant_docs) == 0,
            images=images
        )
    
    def _build_context(self, docs: List[Dict]) -> str:
        """Build context string from relevant documents"""
        if not docs:
            return "No relevant documentation found."
        
        context_parts = []
        for i, doc in enumerate(docs, 1):
            context_parts.append(f"""
=== Document {i}: {doc['title']} ===
Category: {doc['category']}
Content: {doc['content'][:1000]}{'...' if len(doc['content']) > 1000 else ''}
            """.strip())
        
        return '\n\n'.join(context_parts)
    
    def _create_user_message(self, query: SupportQuery, context: str) -> str:
        """Create user message for Claude"""
        
        conversation_context = ""
        if query.conversation_history:
            recent_history = query.conversation_history[-4:]
            if recent_history:
                conversation_context = "\n\nRecent Conversation:\n"
                for msg in recent_history:
                    role = "User" if msg.get('role') == 'user' else "Assistant"
                    content = msg.get('content', '')[:150] + ("..." if len(msg.get('content', '')) > 150 else "")
                    conversation_context += f"{role}: {content}\n"
        
        return f"""
User Question: {query.query}

User Role: {query.user_role or 'Not specified'}
Product Module: {query.product_module or 'Not specified'}
{conversation_context}

Available Documentation:
{context}

Please provide a helpful, specific answer based on Replicon's functionality. Include step-by-step instructions when appropriate and reference the documentation provided above. Be confident and professional in your response.
        """.strip()
    
    def _assess_confidence(self, response: str, docs: List[Dict], images: List[Dict]) -> float:
        """Assess confidence in the response"""
        confidence = 0.6  # Higher base confidence
        
        # Higher confidence if we found relevant docs
        if docs:
            confidence += 0.2
            if len(docs) >= 2:
                confidence += 0.1
        
        # Bonus for having relevant images
        if images:
            confidence += 0.1
        
        # Check for uncertainty indicators in response
        uncertainty_indicators = ['not sure', 'might be', 'contact support', 'unclear']
        response_lower = response.lower()
        uncertainty_count = sum(1 for indicator in uncertainty_indicators if indicator in response_lower)
        confidence -= uncertainty_count * 0.1
        
        # Check for specific instructions (higher confidence)
        if any(word in response_lower for word in ['click', 'navigate', 'go to', 'select', 'enter']):
            confidence += 0.1
        
        return max(0.0, min(1.0, confidence))
    
    def _check_escalation_needed(self, response: str, query: str) -> bool:
        """Check if the query needs human escalation"""
        escalation_indicators = [
            'contact support', 'speak with', 'technical issue', 'system administrator'
        ]
        
        response_lower = response.lower()
        return any(indicator in response_lower for indicator in escalation_indicators)
    
    def _extract_suggested_actions(self, response: str) -> List[str]:
        """Extract suggested actions from the response"""
        actions = []
        
        # Look for numbered steps
        step_pattern = r'\d+\.\s*\*\*([^*]+)\*\*|^\d+\.\s*([^\n]+)'
        steps = re.findall(step_pattern, response, re.MULTILINE)
        for step in steps:
            action = step[0] or step[1]
            if action.strip():
                actions.append(action.strip()[:100])
        
        # Look for action phrases if no numbered steps
        if not actions:
            action_phrases = [
                r'navigate to ([^\n.]+)',
                r'click (?:on )?([^\n.]+)',
                r'access ([^\n.]+)'
            ]
            
            for pattern in action_phrases:
                matches = re.findall(pattern, response, re.IGNORECASE)
                for match in matches[:3]:
                    if match.strip() and len(match) < 80:
                        actions.append(f"Go to: {match.strip()}")
        
        return actions[:5]

# Create FastAPI app
app = FastAPI(title="Replicon AI Support System", version="1.0.0")

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount the scraped images directory
if Path("static/images/scraped").exists():
    app.mount("/static/images/scraped", StaticFiles(directory="static/images/scraped"), name="scraped_images")

# Initialize services
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
kb = RepliconKnowledgeBase()
support_ai = RepliconSupportAI(CLAUDE_API_KEY, kb)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with support form"""
    try:
        return templates.TemplateResponse("support_home.html", {"request": request})
    except Exception as e:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Replicon AI Support Assistant</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                .form-group {{ margin-bottom: 15px; }}
                label {{ display: block; margin-bottom: 5px; font-weight: bold; }}
                input, select, textarea {{ width: 100%; padding: 8px; border: 1px solid #ddd; }}
                button {{ background: #007bff; color: white; padding: 10px 20px; border: none; cursor: pointer; }}
                .error {{ background: #f8d7da; color: #721c24; padding: 10px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h1>Replicon AI Support Assistant</h1>
            <div class="error">Template not found: {str(e)}</div>
            <form method="post" action="/ask">
                <div class="form-group">
                    <label>What can I help you with?</label>
                    <textarea name="query" rows="4" placeholder="e.g., How do I submit my timesheet?" required></textarea>
                </div>
                <button type="submit">Get Help</button>
            </form>
        </body>
        </html>
        """)

@app.post("/ask")
async def ask_support(
    query: str = Form(...),
    user_role: str = Form(None),
    product_module: str = Form(None),
    conversation_history: str = Form("[]"),
    include_images: str = Form("true")
):
    """Process support query with improved logic"""
    try:
        # Parse conversation history
        try:
            history = json.loads(conversation_history) if conversation_history else []
        except json.JSONDecodeError:
            history = []
        
        include_images_bool = include_images.lower() == "true"
        
        support_query = SupportQuery(
            query=query,
            user_role=user_role if user_role else None,
            product_module=product_module if product_module else None,
            conversation_history=history
        )
        
        response = support_ai.generate_support_response(support_query, include_images_bool)
        
        return {
            "success": True,
            "response": response.response,
            "confidence": response.confidence,
            "relevant_docs": [
                {
                    "title": doc["title"],
                    "url": doc["url"],
                    "category": doc["category"]
                }
                for doc in response.relevant_docs
            ],
            "suggested_actions": response.suggested_actions,
            "escalation_needed": response.escalation_needed,
            "images": response.images or [],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error in ask_support: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

@app.get("/debug/images")
async def debug_images(query: str = "timesheet"):
    """Debug endpoint to check image retrieval"""
    try:
        if hasattr(support_ai, 'image_manager') and support_ai.image_manager.conn:
            images = support_ai.image_manager.get_images_for_query(query, limit=5)
            
            # Check if image files actually exist
            for img in images:
                img_path = Path(img['local_path'].replace('/static/', 'static/'))
                img['file_exists'] = img_path.exists()
                img['file_size'] = img_path.stat().st_size if img_path.exists() else 0
            
            return {
                "success": True,
                "query": query,
                "images_found": len(images),
                "images": images,
                "scraped_dir_exists": Path("static/images/scraped").exists(),
                "scraped_files_count": len(list(Path("static/images/scraped").glob("*"))) if Path("static/images/scraped").exists() else 0
            }
        else:
            return {
                "success": False,
                "error": "No image manager or database connection",
                "scraped_dir_exists": Path("static/images/scraped").exists()
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/search")
async def search_docs(q: str, category: str = None, limit: int = 5):
    """Search documentation directly"""
    try:
        if not kb or not kb.conn:
            return {"success": False, "error": "No documentation database available"}
            
        results = kb.search_relevant_documents(q, category, limit)
        return {
            "success": True,
            "results": results,
            "total": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

@app.get("/stats")
async def get_stats():
    """Get knowledge base statistics"""
    try:
        if not kb or not kb.conn:
            return {
                "total_documents": 0,
                "categories": {},
                "database_exists": False,
                "message": "No documentation database found. Run scraper first.",
                "last_updated": datetime.now().isoformat()
            }
        
        cursor = kb.conn.cursor()
        
        # Total documents
        cursor.execute('SELECT COUNT(*) FROM documents')
        total_docs = cursor.fetchone()[0]
        
        # Documents by category
        cursor.execute('SELECT category, COUNT(*) FROM documents GROUP BY category ORDER BY COUNT(*) DESC')
        categories = dict(cursor.fetchall())
        
        # Image stats if available
        image_stats = {}
        try:
            cursor.execute('SELECT COUNT(*) FROM images')
            image_stats['total_images'] = cursor.fetchone()[0]
        except:
            image_stats['total_images'] = 0
        
        return {
            "total_documents": total_docs,
            "categories": categories,
            "database_exists": True,
            "claude_configured": support_ai.has_claude,
            **image_stats,
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "total_documents": 0,
            "categories": {},
            "database_exists": False,
            "last_updated": datetime.now().isoformat()
        }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "database_connected": kb.conn is not None if kb else False,
        "claude_configured": support_ai.has_claude if support_ai else False,
        "images_available": Path("static/images/scraped").exists(),
        "timestamp": datetime.now().isoformat()
    }

# RENDER COMPATIBILITY MODIFICATIONS
if __name__ == "__main__":
    print("Starting Replicon AI Support System...")
    
    # Use environment variable for port (Render provides this)
    port = int(os.environ.get("PORT", 8000))
    
    # Use 0.0.0.0 to bind to all interfaces (required for Render)
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        # Disable reload for production
        reload=False
    )