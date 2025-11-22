import requests
import base64
import logging
import PyPDF2
from io import BytesIO
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

class BrowserHandler:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        # Create a session for HTTP requests (connection pooling)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def _ensure_browser(self):
        """Initialize browser lazily when needed (thread-safe)"""
        if self.playwright is None:
            try:
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security'
                    ]
                )
                self.context = self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    java_script_enabled=True,
                    bypass_csp=True,
                    ignore_https_errors=True
                )
                # Set longer default timeout
                self.context.set_default_timeout(45000)
                self.page = self.context.new_page()
                logger.info("Browser initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize browser: {str(e)}")
                raise
    
    def fetch_page(self, url):
        """Fetch and render a JavaScript page, return the HTML content"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self._ensure_browser()
                
                # Navigate to the page with increased timeout
                logger.info(f"Navigating to {url} (attempt {retry_count + 1}/{max_retries})")
                
                # Try different wait strategies
                try:
                    # First try: wait for network to be idle
                    self.page.goto(url, wait_until='networkidle', timeout=45000)
                except Exception as e:
                    logger.warning(f"NetworkIdle failed, trying domcontentloaded: {e}")
                    # Fallback: just wait for DOM
                    self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
                
                # Give a moment for any final scripts
                self.page.wait_for_timeout(1000)
                
                # Get the rendered HTML content
                content = self.page.content()
                
                # Also get visible text for easier parsing
                body_text = self.page.evaluate("() => document.body.innerText")
                
                # If we got content, return it
                if content and len(content) > 100:
                    logger.info(f"Successfully fetched page (size: {len(content)} bytes)")
                    return {
                        'html': content,
                        'text': body_text,
                        'url': url
                    }
                else:
                    logger.warning("Page content seems too short, retrying...")
                    retry_count += 1
                    continue
                    
            except Exception as e:
                retry_count += 1
                logger.error(f"Error fetching page {url} (attempt {retry_count}/{max_retries}): {str(e)}")
                
                if retry_count < max_retries:
                    # Close and reinitialize browser on error
                    try:
                        if self.browser:
                            self.browser.close()
                        if self.playwright:
                            self.playwright.stop()
                    except:
                        pass
                    
                    self.playwright = None
                    self.browser = None
                    self.context = None
                    self.page = None
                    
                    # Wait a bit before retry
                    import time
                    time.sleep(2)
                else:
                    # Last resort: try with requests (no JS rendering)
                    logger.warning("All browser attempts failed, falling back to simple HTTP request")
                    try:
                        response = requests.get(url, timeout=15)
                        return {
                            'html': response.text,
                            'text': response.text,
                            'url': url
                        }
                    except Exception as req_error:
                        logger.error(f"HTTP fallback also failed: {req_error}")
                        return None
        
        return None
    
    def fetch_file(self, url):
        """Download a text-based file (CSV, JSON, TXT)"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            logger.info(f"Downloaded file: {url}, size: {len(response.text)} bytes")
            return response.text
        except Exception as e:
            logger.error(f"Error fetching file {url}: {str(e)}")
            return None
    
    def fetch_binary(self, url):
        """Download a binary file and return as base64"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Return both raw bytes and base64
            return {
                'base64': base64.b64encode(response.content).decode('utf-8'),
                'bytes': response.content,
                'size': len(response.content)
            }
        except Exception as e:
            logger.error(f"Error fetching binary {url}: {str(e)}")
            return None
    
    def fetch_audio(self, url):
        """Download an audio file"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Detect content type
            content_type = response.headers.get('content-type', 'audio/mpeg')
            
            # Handle opus/ogg files
            if url.endswith('.opus') or 'opus' in url:
                content_type = 'audio/ogg'
            elif url.endswith('.mp3'):
                content_type = 'audio/mpeg'
            elif url.endswith('.wav'):
                content_type = 'audio/wav'
            
            logger.info(f"Downloaded audio file: {url}, type: {content_type}, size: {len(response.content)} bytes")
            
            return {
                'base64': base64.b64encode(response.content).decode('utf-8'),
                'bytes': response.content,
                'size': len(response.content),
                'content_type': content_type
            }
        except Exception as e:
            logger.error(f"Error fetching audio {url}: {str(e)}")
            return None
    
    def fetch_pdf(self, url):
        """Download and extract text from PDF"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Parse PDF
            pdf_file = BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Extract text from all pages
            text_by_page = {}
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text_by_page[page_num + 1] = page.extract_text()
            
            logger.info(f"Downloaded PDF: {url}, {len(pdf_reader.pages)} pages")
            
            return {
                'num_pages': len(pdf_reader.pages),
                'pages': text_by_page,
                'full_text': '\n\n'.join(text_by_page.values())
            }
            
        except Exception as e:
            logger.error(f"Error fetching PDF {url}: {str(e)}")
            return None
    
    def screenshot(self, selector=None):
        """Take a screenshot of the page or a specific element"""
        try:
            self._ensure_browser()
            
            if selector:
                element = self.page.query_selector(selector)
                if element:
                    screenshot_bytes = element.screenshot()
                else:
                    screenshot_bytes = self.page.screenshot()
            else:
                screenshot_bytes = self.page.screenshot()
            
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Error taking screenshot: {str(e)}")
            return None
    
    def execute_script(self, script):
        """Execute JavaScript on the page"""
        try:
            self._ensure_browser()
            return self.page.evaluate(script)
        except Exception as e:
            logger.error(f"Error executing script: {str(e)}")
            return None
    
    def close(self):
        """Clean up browser resources"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")