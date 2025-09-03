#!/usr/bin/env python3
"""
Fixed Replicon Documentation Scraper with automatic database migration
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
class DocumentSection:
    title: str
    content: str
    url: str
    category: str
    subcategory: Optional[str]
    last_updated: Optional[str]
    breadcrumbs: List[str]
    keywords: List[str]
    images: List[Dict] = None

class RepliconDocumentationScraper:
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
        self.enable_images = True  # Flag to enable/disable image downloading
        
        # Create directories for images
        self.images_dir = Path("static/images/scraped")
        self.images_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database with migration
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with automatic migration"""
        self.conn = sqlite3.connect('replicon_docs.db')
        cursor = self.conn.cursor()
        
        # Create basic tables
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
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS scraping_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            total_urls INTEGER,
            successful_urls INTEGER,
            failed_urls INTEGER,
            status TEXT DEFAULT 'running'
        )
        ''')
        
        # Check if we need to add image support
        self._migrate_for_images(cursor)
        
        self.conn.commit()
    
    def _migrate_for_images(self, cursor):
        """Add image support to existing database"""
        try:
            # Check if images column exists in documents table
            cursor.execute("PRAGMA table_info(documents)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'images' not in columns:
                logger.info("Adding images column to documents table...")
                cursor.execute('ALTER TABLE documents ADD COLUMN images TEXT')
            
            # Check if images table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images'")
            if not cursor.fetchone():
                logger.info("Creating images table...")
                cursor.execute('''
                CREATE TABLE images (
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
                ''')
            
            # Check if scraping_sessions has image columns
            cursor.execute("PRAGMA table_info(scraping_sessions)")
            session_columns = [col[1] for col in cursor.fetchall()]
            
            if 'images_found' not in session_columns:
                logger.info("Adding image columns to scraping_sessions...")
                cursor.execute('ALTER TABLE scraping_sessions ADD COLUMN images_found INTEGER DEFAULT 0')
                cursor.execute('ALTER TABLE scraping_sessions ADD COLUMN images_downloaded INTEGER DEFAULT 0')
            
            logger.info("✅ Database migration for images completed")
            
        except Exception as e:
            logger.error(f"Migration error: {e}")
            # If migration fails, disable image features
            self.enable_images = False
            logger.warning("⚠️ Image features disabled due to migration issues")
    
    def download_image(self, img_url: str, document_url: str, alt_text: str = "", caption: str = "") -> Optional[Dict]:
        """Download an image and return its metadata"""
        if not self.enable_images:
            return None
            
        try:
            # Make the URL absolute
            full_img_url = urljoin(document_url, img_url)
            
            # Skip if not a valid image URL
            if not self._is_valid_image_url(full_img_url):
                return None
            
            # Generate filename based on URL hash
            url_hash = hashlib.md5(full_img_url.encode()).hexdigest()[:12]
            parsed_url = urlparse(full_img_url)
            file_extension = os.path.splitext(parsed_url.path)[1] or '.png'
            local_filename = f"img_{url_hash}{file_extension}"
            local_path = self.images_dir / local_filename
            
            # Skip if already downloaded
            if local_path.exists():
                return {
                    'original_url': full_img_url,
                    'local_filename': local_filename,
                    'alt_text': alt_text,
                    'caption': caption,
                    'already_exists': True
                }
            
            # Download the image
            logger.info(f"Downloading image: {full_img_url}")
            img_response = self.session.get(full_img_url, timeout=10)
            img_response.raise_for_status()
            
            # Check if it's actually an image
            content_type = img_response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                return None
            
            # Save the image
            with open(local_path, 'wb') as f:
                f.write(img_response.content)
            
            # Try to get image dimensions
            width, height = self._get_image_dimensions(local_path)
            
            image_info = {
                'original_url': full_img_url,
                'local_filename': local_filename,
                'alt_text': alt_text,
                'caption': caption,
                'file_size': len(img_response.content),
                'image_type': content_type,
                'width': width,
                'height': height
            }
            
            logger.info(f"Downloaded: {local_filename} ({len(img_response.content)} bytes)")
            return image_info
            
        except Exception as e:
            logger.error(f"Failed to download image {img_url}: {e}")
            return None
    
    def _is_valid_image_url(self, url: str) -> bool:
        """Check if URL is likely an image"""
        if url.startswith('data:'):
            return False
        
        parsed = urlparse(url)
        path = parsed.path.lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        
        return any(path.endswith(ext) for ext in image_extensions)
    
    def _get_image_dimensions(self, image_path: Path) -> tuple:
        """Get image dimensions if possible"""
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return img.size
        except:
            return (None, None)
    
    def extract_images_from_page(self, soup: BeautifulSoup, page_url: str) -> List[Dict]:
        """Extract relevant images from a page"""
        if not self.enable_images:
            return []
            
        images = []
        img_tags = soup.find_all('img')
        
        for img in img_tags:
            img_src = img.get('src')
            if not img_src:
                continue
            
            # Skip very small images (likely icons)
            width = img.get('width')
            height = img.get('height')
            if width and height:
                try:
                    if int(width) < 50 or int(height) < 50:
                        continue
                except ValueError:
                    pass
            
            # Skip common icon/decoration classes
            img_classes = img.get('class', [])
            skip_classes = ['icon', 'logo', 'avatar', 'emoji']
            if any(skip_class in ' '.join(img_classes).lower() for skip_class in skip_classes):
                continue
            
            alt_text = img.get('alt', '').strip()
            caption = self._find_image_caption(img)
            
            # Download the image
            image_info = self.download_image(img_src, page_url, alt_text, caption)
            if image_info:
                images.append(image_info)
        
        return images
    
    def _find_image_caption(self, img_element) -> str:
        """Try to find a caption for an image"""
        # Check if image is inside a figure with figcaption
        figure = img_element.find_parent('figure')
        if figure:
            figcaption = figure.find('figcaption')
            if figcaption:
                return figcaption.get_text().strip()
        
        # Look for nearby text that might be a caption
        for sibling in img_element.find_next_siblings(['p', 'span', 'div'], limit=2):
            text = sibling.get_text().strip()
            if text and len(text) < 200:
                return text
        
        return ""
    
    def scrape_single_page(self, url: str) -> Optional[DocumentSection]:
        """Scrape a single documentation page"""
        if url in self.scraped_urls:
            return None
            
        try:
            logger.info(f"Scraping: {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract basic information
            title = self._extract_title(soup)
            content = self._extract_content(soup)
            
            if len(content.strip()) < 100:
                logger.warning(f"Skipping {url} - content too short")
                return None
            
            # Extract images if enabled
            images = self.extract_images_from_page(soup, url) if self.enable_images else []
            
            # Extract metadata
            category = self._categorize_content(url, title, content)
            subcategory = self._extract_subcategory(url, soup)
            breadcrumbs = self._extract_breadcrumbs(soup)
            keywords = self._extract_keywords(title, content)
            last_updated = self._extract_last_updated(soup)
            
            doc = DocumentSection(
                title=title,
                content=content,
                url=url,
                category=category,
                subcategory=subcategory,
                last_updated=last_updated,
                breadcrumbs=breadcrumbs,
                keywords=keywords,
                images=images
            )
            
            # Store images in database
            if self.enable_images:
                for image in images:
                    self._store_image_in_db(url, image)
            
            self.scraped_urls.add(url)
            logger.info(f"✅ Scraped: {title} ({len(images)} images)")
            return doc
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            self.failed_urls.add(url)
            return None
    
    def _store_image_in_db(self, document_url: str, image_info: Dict):
        """Store image information in database"""
        if not self.enable_images:
            return
            
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO images 
            (document_url, original_url, local_filename, alt_text, caption, 
             file_size, image_type, width, height)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                document_url,
                image_info.get('original_url'),
                image_info.get('local_filename'),
                image_info.get('alt_text', ''),
                image_info.get('caption', ''),
                image_info.get('file_size', 0),
                image_info.get('image_type', ''),
                image_info.get('width'),
                image_info.get('height')
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error storing image in DB: {e}")
    
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
            
            # Limit URLs for testing
            urls_list = list(urls_to_scrape)[:20]  # Start with just 20 URLs
            logger.info(f"Found {len(urls_list)} URLs to scrape (limited for testing)")
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
        
        # Fallback
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
    
    def _extract_last_updated(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract last updated date"""
        for selector in ['.last-updated', 'time[datetime]']:
            elem = soup.select_one(selector)
            if elem:
                return elem.get('datetime') or elem.get_text().strip()
        return None
    
    def save_to_database(self, doc: DocumentSection):
        """Save document to database"""
        cursor = self.conn.cursor()
        
        # Convert images to JSON if they exist
        images_json = json.dumps([
            {
                'local_filename': img.get('local_filename'),
                'alt_text': img.get('alt_text', ''),
                'caption': img.get('caption', '')
            }
            for img in (doc.images or [])
        ]) if self.enable_images else '[]'
        
        cursor.execute('''
        INSERT OR REPLACE INTO documents 
        (title, content, url, category, subcategory, last_updated, breadcrumbs, keywords, images)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            doc.title, doc.content, doc.url, doc.category, doc.subcategory,
            doc.last_updated, json.dumps(doc.breadcrumbs), 
            json.dumps(doc.keywords), images_json
        ))
        self.conn.commit()
    
    def scrape_all_documentation(self, max_workers=2):
        """Scrape all documentation"""
        cursor = self.conn.cursor()
        
        # Create session record
        if self.enable_images:
            cursor.execute('INSERT INTO scraping_sessions (total_urls, images_found, images_downloaded) VALUES (0, 0, 0)')
        else:
            cursor.execute('INSERT INTO scraping_sessions (total_urls) VALUES (0)')
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
                doc = self.scrape_single_page(url)
                if doc:
                    self.save_to_database(doc)
                    successful += 1
                    if doc.images:
                        total_images += len(doc.images)
                else:
                    failed += 1
                
                time.sleep(self.delay)
            
            # Update session completion
            if self.enable_images:
                cursor.execute('''
                UPDATE scraping_sessions 
                SET completed_at = CURRENT_TIMESTAMP, successful_urls = ?, failed_urls = ?, 
                    images_found = ?, images_downloaded = ?, status = 'completed'
                WHERE id = ?
                ''', (successful, failed, total_images, total_images, session_id))
            else:
                cursor.execute('''
                UPDATE scraping_sessions 
                SET completed_at = CURRENT_TIMESTAMP, successful_urls = ?, failed_urls = ?, status = 'completed'
                WHERE id = ?
                ''', (successful, failed, session_id))
            self.conn.commit()
            
            logger.info(f"✅ Completed! Success: {successful}, Failed: {failed}")
            if self.enable_images:
                logger.info(f"📸 Images downloaded: {total_images}")
            
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            cursor.execute('UPDATE scraping_sessions SET status = ? WHERE id = ?', 
                          ('failed', session_id))
            self.conn.commit()
    
    def get_stats(self):
        """Get scraping statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM documents')
        total_docs = cursor.fetchone()[0]
        
        cursor.execute('SELECT category, COUNT(*) FROM documents GROUP BY category')
        categories = dict(cursor.fetchall())
        
        stats = {
            'total_documents': total_docs,
            'documents_by_category': categories,
            'image_support_enabled': self.enable_images
        }
        
        if self.enable_images:
            cursor.execute('SELECT COUNT(*) FROM images')
            total_images = cursor.fetchone()[0]
            stats['total_images'] = total_images
            stats['images_directory'] = str(self.images_dir)
        
        return stats
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()


# Main execution
if __name__ == "__main__":
    scraper = RepliconDocumentationScraper()
    
    try:
        print("🚀 Starting documentation scraping with image extraction...")
        print(f"📸 Image support: {'Enabled' if scraper.enable_images else 'Disabled'}")
        
        scraper.scrape_all_documentation()
        
        stats = scraper.get_stats()
        print("\n📊 Results:")
        print(f"Documents: {stats['total_documents']}")
        if scraper.enable_images:
            print(f"Images: {stats.get('total_images', 0)}")
        print("Categories:", stats['documents_by_category'])
        
    except KeyboardInterrupt:
        print("\n⏸️ Scraping interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        scraper.close()