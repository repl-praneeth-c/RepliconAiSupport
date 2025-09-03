#!/usr/bin/env python3
"""
Enhanced Replicon Documentation Scraper with semantic text-image linking
This replaces your existing replicon_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
from urllib.parse import urljoin, urlparse
import re
from dataclasses import dataclass
from typing import List, Dict, Optional
import logging
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from datetime import datetime
import hashlib
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ImageContext:
    """Stores semantic context around an image"""
    image_url: str
    local_filename: str
    alt_text: str
    caption: str
    surrounding_text: str
    section_heading: str
    step_number: Optional[int]
    semantic_tags: List[str]
    context_type: str

@dataclass
class DocumentSection:
    title: str
    content: str
    url: str
    category: str
    subcategory: Optional[str]
    last_updated: Optional[str]
    breadcrumbs: List[str]
    keywords: List[str]
    images: List[ImageContext] = None
    semantic_sections: List[Dict] = None

class EnhancedRepliconScraper:
    def __init__(self, base_url="https://www.replicon.com/help/", delay=1.0):
        self.base_url = base_url
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.scraped_urls = set()
        self.failed_urls = set()
        self.documents = []
        self.enable_images = True
        
        # Create directories
        self.images_dir = Path("static/images/scraped")
        self.images_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database with migration
        self.init_enhanced_database()
    
    def init_enhanced_database(self):
        """Initialize database with enhanced semantic schema"""
        self.conn = sqlite3.connect('replicon_docs.db')
        cursor = self.conn.cursor()
        
        # Create or update documents table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            category TEXT,
            subcategory TEXT,
            last_updated TEXT,
            breadcrumbs TEXT,
            keywords TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Enhanced semantic images table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS semantic_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_url TEXT,
            original_url TEXT,
            local_filename TEXT,
            alt_text TEXT,
            caption TEXT,
            surrounding_text TEXT,
            section_heading TEXT,
            step_number INTEGER,
            semantic_tags TEXT,
            context_type TEXT,
            relevance_score REAL DEFAULT 0.0,
            file_size INTEGER,
            image_type TEXT,
            width INTEGER,
            height INTEGER,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_url) REFERENCES documents (url)
        )
        ''')
        
        # Content sections for better organization
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS content_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_url TEXT,
            section_type TEXT,
            section_title TEXT,
            content TEXT,
            section_order INTEGER,
            has_images BOOLEAN DEFAULT FALSE,
            semantic_keywords TEXT,
            FOREIGN KEY (document_url) REFERENCES documents (url)
        )
        ''')
        
        # Scraping sessions tracking
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS scraping_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            total_urls INTEGER,
            successful_urls INTEGER,
            failed_urls INTEGER,
            images_found INTEGER DEFAULT 0,
            images_downloaded INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'
        )
        ''')
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_semantic_images_tags ON semantic_images(semantic_tags)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_semantic_images_context ON semantic_images(context_type, section_heading)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_content_sections_keywords ON content_sections(semantic_keywords)')
        
        self.conn.commit()
        logger.info("Enhanced database schema initialized")
    
    def discover_help_urls(self) -> List[str]:
        """Discover help documentation URLs"""
        logger.info("Discovering URLs...")
        urls_to_scrape = set()
        
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(self.base_url, href)
                
                if (self.base_url in full_url and 
                    full_url not in urls_to_scrape and
                    not self._is_excluded_url(full_url)):
                    urls_to_scrape.add(full_url)
            
            urls_list = list(urls_to_scrape)
            logger.info(f"Found {len(urls_list)} URLs to scrape")
            return urls_list
            
        except Exception as e:
            logger.error(f"Error discovering URLs: {e}")
            return []
    
    def _is_excluded_url(self, url: str) -> bool:
        """Check if URL should be excluded"""
        excluded_patterns = [
            r'/search\?', r'/login', r'/register', r'/contact',
            r'\.pdf$', r'\.jpg$', r'\.png$', r'\.gif$', r'/api/', r'#'
        ]
        return any(re.search(pattern, url) for pattern in excluded_patterns)
    
    def extract_semantic_images(self, soup: BeautifulSoup, page_url: str) -> List[ImageContext]:
        """Extract images with rich semantic context"""
        image_contexts = []
        
        # Find all images
        img_tags = soup.find_all('img')
        
        for img in img_tags:
            img_src = img.get('src')
            if not img_src or not self._is_valid_image_url(img_src):
                continue
            
            # Skip small/icon images
            if self._is_small_image(img):
                continue
            
            # Extract semantic context
            context = self._extract_image_context(img, soup, page_url)
            if context and context.semantic_tags:  # Only include if we have semantic meaning
                # Download the image
                downloaded_info = self.download_image(context.image_url, page_url)
                if downloaded_info:
                    context.local_filename = downloaded_info['local_filename']
                    image_contexts.append(context)
                    logger.info(f"Captured semantic image: {context.local_filename} - {context.semantic_tags}")
        
        return image_contexts
    
    def _extract_image_context(self, img_element, soup: BeautifulSoup, page_url: str) -> Optional[ImageContext]:
        """Extract rich semantic context around an image"""
        
        img_src = urljoin(page_url, img_element.get('src'))
        alt_text = img_element.get('alt', '').strip()
        
        # Find caption
        caption = self._find_image_caption(img_element)
        
        # Extract surrounding text (before and after the image)
        surrounding_text = self._extract_surrounding_text(img_element, 300)
        
        # Find the section heading this image belongs to
        section_heading = self._find_section_heading(img_element)
        
        # Detect if this is part of a step-by-step process
        step_number = self._detect_step_number(img_element, surrounding_text)
        
        # Generate semantic tags - this is the key improvement
        semantic_tags = self._generate_semantic_tags(
            alt_text, caption, surrounding_text, section_heading
        )
        
        # Only proceed if we have meaningful semantic tags
        if not semantic_tags:
            return None
        
        # Determine context type
        context_type = self._determine_context_type(
            img_element, surrounding_text, section_heading, step_number
        )
        
        return ImageContext(
            image_url=img_src,
            local_filename="",  # Will be filled after download
            alt_text=alt_text,
            caption=caption,
            surrounding_text=surrounding_text,
            section_heading=section_heading,
            step_number=step_number,
            semantic_tags=semantic_tags,
            context_type=context_type
        )
    
    def _find_section_heading(self, img_element) -> str:
        """Find the section heading that contains this image"""
        
        # Look for parent section headings
        current = img_element
        max_depth = 10
        depth = 0
        
        while current and depth < max_depth:
            # Check if current element is a heading
            if current.name and current.name.startswith('h') and current.name[1:].isdigit():
                return current.get_text().strip()
            
            # Look for previous headings in the document
            for sibling in current.find_all_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'], limit=5):
                return sibling.get_text().strip()
            
            current = current.parent
            depth += 1
        
        return ""
    
    def _extract_surrounding_text(self, img_element, max_chars: int = 300) -> str:
        """Extract text immediately surrounding the image"""
        
        # Get text from surrounding elements
        surrounding_elements = []
        
        # Previous siblings
        for sibling in img_element.find_all_previous(limit=5):
            if hasattr(sibling, 'get_text'):
                text = sibling.get_text().strip()
                if text and len(text) > 10:  # Meaningful text only
                    surrounding_elements.append(text)
        
        # Next siblings
        for sibling in img_element.find_all_next(limit=5):
            if hasattr(sibling, 'get_text'):
                text = sibling.get_text().strip()
                if text and len(text) > 10:
                    surrounding_elements.append(text)
        
        # Parent element text
        parent = img_element.parent
        if parent:
            parent_text = parent.get_text().strip()
            if parent_text and len(parent_text) < 500:  # Not too long
                surrounding_elements.append(parent_text)
        
        # Combine and clean
        full_text = ' '.join(surrounding_elements)
        # Remove excessive whitespace
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        return full_text[:max_chars] if len(full_text) > max_chars else full_text
    
    def _detect_step_number(self, img_element, surrounding_text: str) -> Optional[int]:
        """Detect if image is part of a numbered step process"""
        
        # Look for step indicators
        step_patterns = [
            r'step\s*(\d+)',
            r'(\d+)\.\s*(?:click|select|enter|navigate)',
            r'figure\s*(\d+)',
            r'screenshot\s*(\d+)',
        ]
        
        text_to_search = surrounding_text.lower()
        for pattern in step_patterns:
            match = re.search(pattern, text_to_search)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _generate_semantic_tags(self, alt_text: str, caption: str, 
                               surrounding_text: str, section_heading: str) -> List[str]:
        """Generate semantic tags describing what the image actually shows"""
        
        # Combine all text sources
        all_text = f"{alt_text} {caption} {surrounding_text} {section_heading}".lower()
        
        # Enhanced semantic categories with more specific indicators
        semantic_categories = {
            # Timesheet related
            'timesheet_entry': ['enter time', 'fill timesheet', 'time entry', 'add hours', 'timesheet form'],
            'timesheet_submission': ['submit timesheet', 'submit for approval', 'send timesheet'],
            'timesheet_approval': ['approve timesheet', 'timesheet approval', 'manager approval'],
            'timesheet_interface': ['timesheet screen', 'timesheet view', 'timesheet page'],
            
            # Project related
            'project_creation': ['create project', 'new project', 'add project', 'project setup'],
            'project_dashboard': ['project dashboard', 'project view', 'project list', 'projects page'],
            'project_settings': ['project settings', 'project configuration', 'project properties'],
            
            # Navigation and interface
            'navigation_menu': ['main menu', 'navigation', 'sidebar', 'menu bar', 'nav menu'],
            'dashboard_home': ['dashboard', 'home screen', 'main page', 'landing page'],
            'form_interface': ['form', 'input field', 'dropdown', 'checkbox', 'text field'],
            'button_interface': ['button', 'click here', 'press', 'submit button'],
            
            # Mobile specific
            'mobile_timesheet': ['mobile timesheet', 'app timesheet', 'phone timesheet'],
            'mobile_interface': ['mobile screen', 'app interface', 'phone app', 'mobile view'],
            'mobile_navigation': ['mobile menu', 'app menu', 'mobile nav'],
            
            # Workflows
            'approval_workflow': ['approval process', 'workflow', 'approval step'],
            'submission_process': ['submit process', 'submission workflow', 'send for approval'],
            
            # Reporting
            'report_interface': ['report screen', 'reports page', 'analytics view'],
            'chart_visualization': ['chart', 'graph', 'visualization', 'analytics chart'],
            
            # Admin/Settings
            'admin_interface': ['admin screen', 'administration', 'admin panel'],
            'user_settings': ['user settings', 'preferences', 'user profile'],
            'system_settings': ['system settings', 'configuration', 'setup page']
        }
        
        tags = []
        for category, keywords in semantic_categories.items():
            # Check for exact phrase matches first (higher confidence)
            if any(keyword in all_text for keyword in keywords):
                tags.append(category)
        
        # Add action-based tags
        action_indicators = {
            'clicking_action': ['click', 'press', 'tap', 'select'],
            'data_entry': ['enter', 'type', 'fill in', 'input', 'add data'],
            'navigation_action': ['navigate', 'go to', 'access', 'open'],
            'form_submission': ['submit', 'send', 'save', 'apply']
        }
        
        for action, keywords in action_indicators.items():
            if any(keyword in all_text for keyword in keywords):
                tags.append(action)
        
        # Filter out generic tags if we have specific ones
        if any('timesheet' in tag for tag in tags):
            tags = [tag for tag in tags if 'form_interface' not in tag or 'timesheet' in tag]
        
        return tags[:6]  # Limit to most relevant tags
    
    def _determine_context_type(self, img_element, surrounding_text: str, 
                               section_heading: str, step_number: Optional[int]) -> str:
        """Determine the type of context this image represents"""
        
        text_to_analyze = f"{surrounding_text} {section_heading}".lower()
        
        # Step-by-step process
        if step_number is not None or any(word in text_to_analyze for word in ['step', 'first', 'next', 'then', 'tutorial']):
            return 'step'
        
        # Example or demonstration
        if any(word in text_to_analyze for word in ['example', 'shows', 'displays', 'demonstrates', 'illustration']):
            return 'example'
        
        # Interface screenshot
        if any(word in text_to_analyze for word in ['screen', 'interface', 'page', 'view', 'dialog', 'window']):
            return 'interface'
        
        # Diagram or flowchart
        if any(word in text_to_analyze for word in ['diagram', 'chart', 'flow', 'process', 'workflow']):
            return 'diagram'
        
        return 'general'
    
    def _is_small_image(self, img) -> bool:
        """Check if image is too small to be useful"""
        width = img.get('width')
        height = img.get('height')
        
        if width and height:
            try:
                if int(width) < 80 or int(height) < 80:
                    return True
            except ValueError:
                pass
        
        # Check classes and alt text for icons
        img_classes = ' '.join(img.get('class', [])).lower()
        alt_text = img.get('alt', '').lower()
        
        icon_indicators = ['icon', 'logo', 'avatar', 'emoji', 'bullet', 'arrow']
        return any(indicator in img_classes or indicator in alt_text for indicator in icon_indicators)
    
    def _is_valid_image_url(self, url: str) -> bool:
        """Check if URL is a valid image"""
        if url.startswith('data:'):
            return False
        
        parsed = urlparse(url)
        path = parsed.path.lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        
        return any(path.endswith(ext) for ext in image_extensions)
    
    def download_image(self, img_url: str, document_url: str) -> Optional[Dict]:
        """Download image with error handling"""
        try:
            full_img_url = urljoin(document_url, img_url)
            
            # Generate filename
            url_hash = hashlib.md5(full_img_url.encode()).hexdigest()[:12]
            parsed_url = urlparse(full_img_url)
            file_extension = os.path.splitext(parsed_url.path)[1] or '.png'
            local_filename = f"img_{url_hash}{file_extension}"
            local_path = self.images_dir / local_filename
            
            # Skip if already exists
            if local_path.exists():
                return {'local_filename': local_filename}
            
            # Download
            logger.info(f"Downloading image: {full_img_url}")
            img_response = self.session.get(full_img_url, timeout=10)
            img_response.raise_for_status()
            
            # Validate content type
            content_type = img_response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                return None
            
            # Save image
            with open(local_path, 'wb') as f:
                f.write(img_response.content)
            
            return {
                'local_filename': local_filename,
                'file_size': len(img_response.content),
                'image_type': content_type
            }
            
        except Exception as e:
            logger.error(f"Failed to download image {img_url}: {e}")
            return None
    
    def _find_image_caption(self, img_element) -> str:
        """Find caption for image"""
        # Check figure/figcaption
        figure = img_element.find_parent('figure')
        if figure:
            figcaption = figure.find('figcaption')
            if figcaption:
                return figcaption.get_text().strip()
        
        # Check nearby text that might be captions
        for sibling in img_element.find_next_siblings(['p', 'span', 'div'], limit=2):
            text = sibling.get_text().strip()
            if text and len(text) < 200:
                # Look for caption indicators
                if any(word in text.lower() for word in ['figure', 'image', 'screenshot', 'above', 'below']):
                    return text
        
        return ""
    
    def scrape_single_page_enhanced(self, url: str) -> Optional[DocumentSection]:
        """Enhanced page scraping with semantic context"""
        if url in self.scraped_urls:
            return None
            
        try:
            logger.info(f"Enhanced scraping: {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract basic information
            title = self._extract_title(soup)
            content = self._extract_content(soup)
            
            if len(content.strip()) < 100:
                logger.warning(f"Skipping {url} - content too short")
                return None
            
            # Extract semantic images with context
            semantic_images = self.extract_semantic_images(soup, url)
            
            # Extract metadata
            category = self._categorize_content(url, title, content)
            subcategory = self._extract_subcategory(url, soup)
            breadcrumbs = self._extract_breadcrumbs(soup)
            keywords = self._extract_keywords(title, content)
            
            doc = DocumentSection(
                title=title,
                content=content,
                url=url,
                category=category,
                subcategory=subcategory,
                last_updated=None,
                breadcrumbs=breadcrumbs,
                keywords=keywords,
                images=semantic_images,
                semantic_sections=[]
            )
            
            self.scraped_urls.add(url)
            logger.info(f"Enhanced scraped: {title} ({len(semantic_images)} semantic images)")
            return doc
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            self.failed_urls.add(url)
            return None
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title"""
        for selector in ['h1', '.page-title', '.article-title', 'title']:
            title_elem = soup.select_one(selector)
            if title_elem and title_elem.get_text().strip():
                return title_elem.get_text().strip()
        return "Untitled"
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main content"""
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
        
        for selector in ['article', '.content', '.main-content', 'main']:
            content_elem = soup.select_one(selector)
            if content_elem:
                text = content_elem.get_text(separator='\n', strip=True)
                return re.sub(r'\n\s*\n', '\n\n', text)
        
        body = soup.find('body')
        if body:
            return body.get_text(separator='\n', strip=True)
        return ""
    
    def _categorize_content(self, url: str, title: str, content: str) -> str:
        """Categorize content"""
        text = f"{url} {title} {content}".lower()
        
        categories = {
            'timesheet': ['timesheet', 'time entry', 'hours', 'submit time'],
            'project_management': ['project', 'task', 'milestone'],
            'billing': ['billing', 'invoice', 'rates', 'cost'],
            'mobile': ['mobile', 'app', 'ios', 'android'],
            'reporting': ['report', 'analytics', 'dashboard']
        }
        
        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                return category
        return 'general'
    
    def _extract_subcategory(self, url: str, soup: BeautifulSoup) -> Optional[str]:
        """Extract subcategory"""
        path_parts = url.replace(self.base_url, '').split('/')
        return path_parts[0].replace('-', ' ').title() if path_parts else None
    
    def _extract_breadcrumbs(self, soup: BeautifulSoup) -> List[str]:
        """Extract breadcrumbs"""
        breadcrumbs = []
        breadcrumb = soup.select_one('.breadcrumb, .breadcrumbs')
        if breadcrumb:
            for link in breadcrumb.find_all(['a', 'span']):
                text = link.get_text().strip()
                if text:
                    breadcrumbs.append(text)
        return breadcrumbs
    
    def _extract_keywords(self, title: str, content: str) -> List[str]:
        """Extract keywords"""
        text = f"{title} {content[:500]}".lower()
        replicon_terms = ['timesheet', 'project', 'billing', 'mobile', 'report']
        return [term for term in replicon_terms if term in text]
    
    def save_semantic_data(self, doc: DocumentSection):
        """Save document with semantic image data"""
        cursor = self.conn.cursor()
        
        # Save document
        cursor.execute('''
        INSERT OR REPLACE INTO documents 
        (title, content, url, category, subcategory, last_updated, breadcrumbs, keywords)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            doc.title, doc.content, doc.url, doc.category, doc.subcategory,
            doc.last_updated, json.dumps(doc.breadcrumbs), json.dumps(doc.keywords)
        ))
        
        # Save semantic images
        if doc.images:
            for img in doc.images:
                cursor.execute('''
                INSERT OR REPLACE INTO semantic_images 
                (document_url, original_url, local_filename, alt_text, caption, 
                 surrounding_text, section_heading, step_number, semantic_tags, 
                 context_type, relevance_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    doc.url, img.image_url, img.local_filename, img.alt_text,
                    img.caption, img.surrounding_text, img.section_heading,
                    img.step_number, json.dumps(img.semantic_tags), 
                    img.context_type, len(img.semantic_tags) * 2.0
                ))
        
        self.conn.commit()
    
    def scrape_all_documentation(self, max_workers=2):
        """Main scraping method"""
        cursor = self.conn.cursor()
        
        # Create session record
        cursor.execute('INSERT INTO scraping_sessions (total_urls, images_found, images_downloaded) VALUES (0, 0, 0)')
        session_id = cursor.lastrowid
        self.conn.commit()
        
        try:
            urls = self.discover_help_urls()
            
            # Update session
            cursor.execute('UPDATE scraping_sessions SET total_urls = ? WHERE id = ?', 
                          (len(urls), session_id))
            self.conn.commit()
            
            successful = 0
            failed = 0
            total_images = 0
            
            # Scrape pages
            for url in urls:
                doc = self.scrape_single_page_enhanced(url)
                if doc:
                    self.save_semantic_data(doc)
                    successful += 1
                    if doc.images:
                        total_images += len(doc.images)
                else:
                    failed += 1
                
                time.sleep(self.delay)
            
            # Update session completion
            cursor.execute('''
            UPDATE scraping_sessions 
            SET completed_at = CURRENT_TIMESTAMP, successful_urls = ?, failed_urls = ?, 
                images_found = ?, images_downloaded = ?, status = 'completed'
            WHERE id = ?
            ''', (successful, failed, total_images, total_images, session_id))
            self.conn.commit()
            
            logger.info(f"Enhanced scraping completed! Success: {successful}, Failed: {failed}")
            logger.info(f"Semantic images captured: {total_images}")
            
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            cursor.execute('UPDATE scraping_sessions SET status = ? WHERE id = ?', 
                          ('failed', session_id))
            self.conn.commit()
    
    def get_stats(self):
        """Get enhanced scraping statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM documents')
        total_docs = cursor.fetchone()[0]
        
        cursor.execute('SELECT category, COUNT(*) FROM documents GROUP BY category')
        categories = dict(cursor.fetchall())
        
        cursor.execute('SELECT COUNT(*) FROM semantic_images')
        total_semantic_images = cursor.fetchone()[0]
        
        # Get semantic tag distribution
        cursor.execute('SELECT semantic_tags, COUNT(*) FROM semantic_images GROUP BY semantic_tags LIMIT 10')
        tag_distribution = cursor.fetchall()
        
        stats = {
            'total_documents': total_docs,
            'documents_by_category': categories,
            'semantic_images': total_semantic_images,
            'image_support_enabled': self.enable_images,
            'semantic_tag_samples': tag_distribution[:5]
        }
        
        return stats
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()

# Main execution
if __name__ == "__main__":
    scraper = EnhancedRepliconScraper()
    
    try:
        print("🚀 Starting ENHANCED documentation scraping with semantic image-text linking...")
        print(f"📸 Enhanced image processing: {'Enabled' if scraper.enable_images else 'Disabled'}")
        
        scraper.scrape_all_documentation()
        
        stats = scraper.get_stats()
        print("\n📊 Enhanced Results:")
        print(f"Documents: {stats['total_documents']}")
        print(f"Semantic Images: {stats.get('semantic_images', 0)}")
        print("Categories:", stats['documents_by_category'])
        print("\nSample semantic tags:")
        for tags, count in stats.get('semantic_tag_samples', []):
            if tags:
                tag_list = json.loads(tags) if tags.startswith('[') else [tags]
                print(f"  {tag_list[:3]} ({count} images)")
        
    except KeyboardInterrupt:
        print("\n⏸️ Scraping interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        scraper.close()