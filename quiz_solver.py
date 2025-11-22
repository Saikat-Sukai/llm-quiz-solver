import time
import requests
import json
import base64
from datetime import datetime, timedelta
from browser_handler import BrowserHandler
from llm_handler import LLMHandler
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QuizSolver:
    def __init__(self, email, secret, initial_url):
        self.email = email
        self.secret = secret
        self.start_time = datetime.now()
        self.timeout = timedelta(minutes=3)
        self.browser = BrowserHandler()
        self.llm = LLMHandler()
        self.initial_url = initial_url
        
    def is_timeout(self):
        """Check if 3 minutes have elapsed"""
        return datetime.now() - self.start_time > self.timeout
    
    def solve_quiz_chain(self):
        """Solve a chain of quizzes until completion or timeout"""
        current_url = self.initial_url
        attempt = 0
        max_attempts = 5  # Safety limit
        
        logger.info(f"Starting quiz chain at {current_url}")
        
        try:
            while current_url and attempt < max_attempts and not self.is_timeout():
                attempt += 1
                logger.info(f"Attempt {attempt}: Solving {current_url}")
                
                # Solve the current quiz
                result = self.solve_single_quiz(current_url)
                
                if result and isinstance(result, dict) and result.get('correct'):
                    logger.info(f"✓ Correct answer for {current_url}")
                    # Move to next quiz if provided
                    current_url = result.get('url')
                    if current_url:
                        logger.info(f"→ Next quiz: {current_url}")
                    else:
                        logger.info("✓ Quiz chain completed!")
                        break
                else:
                    reason = result.get('reason', 'Unknown') if result and isinstance(result, dict) else 'Failed to solve'
                    logger.warning(f"✗ Incorrect answer: {reason}")
                    # Check if we can retry or skip to next
                    next_url = result.get('url') if result and isinstance(result, dict) else None
                    if next_url and next_url != current_url:
                        logger.info(f"→ Skipping to next quiz: {next_url}")
                        current_url = next_url
                    elif not self.is_timeout():
                        logger.info(f"↻ Retrying {current_url}")
                        time.sleep(1)  # Brief pause before retry
                    else:
                        break
                        
        except Exception as e:
            logger.error(f"Error in quiz chain: {str(e)}", exc_info=True)
        finally:
            self.browser.close()
    
    def solve_single_quiz(self, quiz_url):
        """Solve a single quiz task"""
        from urllib.parse import urljoin
        
        max_fetch_attempts = 2
        fetch_attempt = 0
        quiz_content = None
        
        # Try to fetch quiz content with retries
        while fetch_attempt < max_fetch_attempts and quiz_content is None:
            try:
                fetch_attempt += 1
                logger.info(f"Fetching quiz from {quiz_url} (attempt {fetch_attempt}/{max_fetch_attempts})")
                quiz_content = self.browser.fetch_page(quiz_url)
                
                if not quiz_content:
                    logger.warning(f"Failed to fetch quiz content on attempt {fetch_attempt}")
                    if fetch_attempt < max_fetch_attempts:
                        import time
                        time.sleep(2)
                        continue
                    else:
                        logger.error("Failed to fetch quiz content after all attempts")
                        return None
                        
            except Exception as e:
                logger.error(f"Exception while fetching: {str(e)}")
                if fetch_attempt >= max_fetch_attempts:
                    return None
        
        try:
            logger.info(f"Quiz content length: {len(quiz_content.get('text', ''))} chars")
            
            # Step 2: Extract the question using LLM
            question_data = self.llm.extract_question(quiz_content)
            
            if not question_data:
                logger.error("Failed to extract question")
                return None
            
            # Add current URL to question data for relative URL resolution
            question_data['current_url'] = quiz_url
            
            logger.info(f"Question: {question_data.get('question', 'N/A')[:200]}")
            
            # Make submit URL absolute if it's relative
            submit_url = question_data.get('submit_url', '')
            if submit_url:
                absolute_submit_url = urljoin(quiz_url, submit_url)
                question_data['submit_url'] = absolute_submit_url
                logger.info(f"Submit URL: {absolute_submit_url}")
            
            # Step 3: Gather any required resources (files, APIs, etc.)
            resources = self.gather_resources(question_data)
            
            # Step 4: Solve the question using LLM
            answer = self.llm.solve_question(question_data, resources)
            
            if answer is None:
                logger.error("Failed to generate answer")
                return None
            
            logger.info(f"Generated answer: {str(answer)[:200]}")
            
            # Step 5: Submit the answer
            submit_url = question_data.get('submit_url')
            if not submit_url:
                logger.error("No submit URL found")
                return None
            
            result = self.submit_answer(submit_url, quiz_url, answer)
            return result
            
        except Exception as e:
            logger.error(f"Error solving quiz: {str(e)}", exc_info=True)
            return None
    
    def gather_resources(self, question_data):
        """Download files, fetch API data, or scrape websites as needed"""
        from urllib.parse import urljoin
        
        resources = {}
        
        # Get the base URL for resolving relative URLs
        current_url = question_data.get('current_url', '')
        
        try:
            # Check if question mentions files to download
            file_urls = question_data.get('file_urls', [])
            for file_url in file_urls:
                # Make absolute URL
                absolute_url = urljoin(current_url, file_url)
                logger.info(f"Downloading resource: {absolute_url} (original: {file_url})")
                try:
                    if absolute_url.endswith('.pdf'):
                        content = self.browser.fetch_pdf(absolute_url)
                        resources[file_url] = {'type': 'pdf', 'content': content}
                    elif absolute_url.endswith(('.csv', '.txt', '.json')):
                        content = self.browser.fetch_file(absolute_url)
                        resources[file_url] = {'type': 'text', 'content': content}
                    elif absolute_url.endswith(('.mp3', '.wav', '.m4a', '.ogg', '.opus', '.flac')):
                        content = self.browser.fetch_audio(absolute_url)
                        resources[file_url] = {'type': 'audio', 'content': content}
                    else:
                        # For images or other files
                        content = self.browser.fetch_binary(absolute_url)
                        resources[file_url] = {'type': 'binary', 'content': content}
                except Exception as e:
                    logger.error(f"Failed to fetch {absolute_url}: {str(e)}")
            
            # Check if question mentions APIs or websites to scrape
            scrape_urls = question_data.get('scrape_urls', [])
            for url in scrape_urls:
                # Make absolute URL
                absolute_url = urljoin(current_url, url)
                logger.info(f"Scraping: {absolute_url} (original: {url})")
                try:
                    content = self.browser.fetch_page(absolute_url)
                    resources[url] = {'type': 'html', 'content': content}
                except Exception as e:
                    logger.error(f"Failed to scrape {absolute_url}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error gathering resources: {str(e)}")
        
        return resources
    
    def submit_answer(self, submit_url, quiz_url, answer):
        """Submit the answer to the specified endpoint"""
        payload = {
            "email": self.email,
            "secret": self.secret,
            "url": quiz_url,
            "answer": answer
        }
        
        try:
            # Check payload size
            payload_json = json.dumps(payload)
            payload_size = len(payload_json)
            if payload_size > 1_000_000:  # 1MB limit
                logger.warning(f"Payload size {payload_size} bytes exceeds 1MB")
                return None
            
            logger.info(f"Submitting to {submit_url}")
            logger.info(f"Payload: email={self.email}, url={quiz_url}, answer={str(answer)[:100]}")
            
            response = requests.post(
                submit_url,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Response: {json.dumps(result, indent=2)}")
                return result
            else:
                logger.error(f"Submit failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error submitting answer: {str(e)}")
            return None