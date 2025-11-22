import os
import json
import re
from anthropic import Anthropic
from data_analyzer import DataAnalyzer
import logging

logger = logging.getLogger(__name__)

class LLMHandler:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-5-20250929"
        self.analyzer = DataAnalyzer()
    
    def transcribe_audio(self, audio_content):
        """Transcribe audio file using Claude"""
        try:
            if not audio_content or not isinstance(audio_content, dict):
                return None
            
            base64_audio = audio_content.get('base64')
            content_type = audio_content.get('content_type', 'audio/mpeg')
            
            # Map content type to media type
            media_type_map = {
                'audio/mpeg': 'audio/mpeg',
                'audio/mp3': 'audio/mpeg',
                'audio/wav': 'audio/wav',
                'audio/x-wav': 'audio/wav',
                'audio/ogg': 'audio/ogg',
                'audio/opus': 'audio/ogg',
            }
            media_type = media_type_map.get(content_type, 'audio/mpeg')
            
            logger.info(f"Transcribing audio (type: {media_type}, size: {audio_content.get('size', 0)} bytes)")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_audio
                            }
                        },
                        {
                            "type": "text",
                            "text": "Please transcribe this audio file. Provide the exact text spoken in the audio."
                        }
                    ]
                }]
            )
            
            transcription = response.content[0].text.strip()
            logger.info(f"Audio transcription: {transcription[:200]}")
            return transcription
            
        except Exception as e:
            logger.error(f"Error transcribing audio: {str(e)}")
            return None
    
    def extract_question(self, page_content):
        """Extract the question, submit URL, and required resources from page content"""
        
        # Get text content
        if isinstance(page_content, dict):
            text = page_content.get('text', '')
            html = page_content.get('html', '')
            current_url = page_content.get('url', '')
        else:
            text = page_content
            html = ''
            current_url = ''
        
        # Extract file URLs from HTML using regex
        file_urls = []
        
        if html:
            # Extract audio sources (audio tag)
            audio_srcs = re.findall(r'<audio[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
            file_urls.extend(audio_srcs)
            
            # Extract source tags (inside audio/video)
            source_tags = re.findall(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
            file_urls.extend(source_tags)
            
            # Extract href links to files
            file_links = re.findall(
                r'href=["\']([^"\']+\.(?:mp3|wav|m4a|ogg|opus|flac|csv|json|pdf|xlsx|xls|txt|zip))["\']',
                html,
                re.IGNORECASE
            )
            file_urls.extend(file_links)
            
            # Remove duplicates while preserving order
            seen = set()
            file_urls = [x for x in file_urls if not (x in seen or seen.add(x))]
        
        logger.info(f"Detected file URLs from HTML: {file_urls}")
        
        # Extract any important numbers from the page (like cutoff values)
        context_numbers = re.findall(r'Cutoff[:\s]*(\d+)', text, re.IGNORECASE)
        context_info = f"Cutoff values found: {context_numbers}" if context_numbers else ""
        
        prompt = f"""You are analyzing a data analysis quiz page. Extract all relevant information.

Page Content:
{text[:5000]}

DETECTED FILE URLs: {file_urls}
CONTEXT: {context_info}

Your task:
1. Identify the EXACT question or task being asked
2. Find the submission URL (look for "POST to", "submit", URLs with "/submit")
3. MUST include ALL detected file URLs in file_urls (audio, CSV, PDF, etc.)
4. Look for any scrape URLs mentioned
5. Determine expected answer type

Common patterns:
- If audio file + CSV file detected → likely "listen to audio for instructions, analyze CSV"
- If "Cutoff: NUMBER" found → that number is important for analysis
- "What is the sum..." → number
- "How many..." → number
- "Get the secret code" → string or number

Return JSON:
{{
  "question": "Listen to audio file and analyze CSV data" (or actual question if visible),
  "submit_url": "submission endpoint URL",
  "file_urls": {json.dumps(file_urls)},
  "scrape_urls": [],
  "answer_format": "number",
  "task_type": "transcription",
  "context": "{context_info}"
}}

CRITICAL: Include ALL file URLs from DETECTED FILE URLs list above!"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            
            # Extract JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                
                # Force include detected files if LLM missed them
                if file_urls:
                    result['file_urls'] = file_urls
                
                # Add context info
                if context_numbers:
                    result['context'] = f"Cutoff: {context_numbers[0]}"
                
                logger.info(f"Question: {result.get('question', 'N/A')[:150]}")
                logger.info(f"Task type: {result.get('task_type', 'unknown')}")
                logger.info(f"File URLs: {result.get('file_urls', [])}")
                logger.info(f"Context: {result.get('context', 'N/A')}")
                return result
            else:
                logger.error("Could not extract JSON from LLM response")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting question: {str(e)}")
            return None
    
    def solve_question(self, question_data, resources):
        """Use LLM to solve the question with provided resources"""
        
        question = question_data.get('question', '')
        answer_format = question_data.get('answer_format', 'string')
        task_type = question_data.get('task_type', 'unknown')
        context = question_data.get('context', '')
        
        # Pre-process data resources with data analyzer (including audio transcription)
        processed_resources = self._preprocess_resources(resources, question, context)
        
        # Build context from resources
        resource_context = self._build_resource_context(processed_resources)
        
        prompt = f"""You are a professional data analyst solving a quiz question. You have various resources available.

QUESTION: {question}
CONTEXT: {context}
EXPECTED ANSWER FORMAT: {answer_format}

{resource_context}

YOUR TASK:
Analyze all available resources and answer the question precisely.

RESOURCE TYPES YOU MAY ENCOUNTER:
- 🎵 AUDIO FILES: May contain spoken questions or instructions (check transcription)
- 📊 CSV/Excel FILES: Tabular data for analysis (filtering, aggregation, statistics)
- 📄 PDF FILES: Text documents with data or information
- 🌐 WEB PAGES: Scraped content with specific data points
- 📋 JSON FILES: Structured data for extraction or analysis
- 🖼️ IMAGES: May need OCR or visual analysis
- 📈 DATA: Numbers, codes, values mentioned in text

COMMON QUESTION PATTERNS:

1. **Data Extraction:**
   - "Get the secret code" → Extract specific value from page/file
   - "What is the value of X" → Find and return specific data point
   - "Find the URL/email/phone" → Extract pattern from text

2. **Calculations:**
   - "What is the sum/mean/count" → Aggregate numeric data
   - "How many rows/items" → Count records
   - "Calculate the total" → Sum values
   - "What percentage" → Compute ratio

3. **Filtering & Analysis:**
   - "Sum values greater than X" → Filter then aggregate
   - "Count items where condition" → Conditional counting
   - "Find records that match" → Query and extract
   - "Group by X and sum Y" → Aggregation by category

4. **Web Scraping:**
   - "Scrape URL and get" → Extract from web page
   - "What does the page say" → Read scraped content

5. **Multi-step Tasks:**
   - "Listen to audio AND analyze CSV" → Use audio for instructions, apply to CSV
   - "Use cutoff value to filter data" → Apply threshold from one source to another
   - "Download file and find X" → Retrieve then analyze

CRITICAL RULES:
✓ If AUDIO TRANSCRIPTION exists, it likely contains the actual question/instructions
✓ If CUTOFF/THRESHOLD values mentioned, apply them to filter data
✓ Look at ALL resources provided - combine info from multiple sources if needed
✓ Return ONLY the final answer value - NO explanations or reasoning
✓ Match the expected format: number → number, string → string, boolean → true/false
✓ Extract numbers from text when answer should be numeric
✓ Be precise - if asked for sum, return exact calculated sum

EXAMPLES ACROSS DIFFERENT SCENARIOS:

Example 1 - Simple Extraction:
Question: "Get the secret code"
Resource: Web page text: "Secret code is 46970"
Answer: 46970

Example 2 - Audio + CSV Analysis:
Question: "Listen to audio and analyze CSV"
Audio transcription: "Sum all values in column 'amount' that exceed the cutoff"
CSV: column 'amount' = [10000, 50000, 60000, 30000]
Context: Cutoff = 46970
Answer: 110000

Example 3 - PDF Data Extraction:
Question: "What is the total on page 2"
PDF page 2: "Sales: $50,000  Expenses: $30,000  Total: $80,000"
Answer: 80000

Example 4 - Conditional Counting:
Question: "How many products cost more than $50"
CSV: 25 products, 12 have price > 50
Answer: 12

Example 5 - JSON Parsing:
Question: "Get the user count from API response"
JSON: {{"data": {{"users": 1250, "active": 800}}}}
Answer: 1250

Example 6 - Multi-source:
Question: "Use the code from page A to filter data in file B"
Page A: "Code: ABC123"
File B CSV: 5 rows have code ABC123
Answer: 5

NOW SOLVE THE ACTUAL QUESTION:
- Read question carefully
- Check ALL resources (audio transcription, CSV data, web pages, etc.)
- Apply any filtering/calculations needed
- Return ONLY the final answer value in the expected format
- NO explanations, NO markdown, JUST the answer

Final Answer:"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            
            answer_text = response.content[0].text.strip()
            logger.info(f"Raw LLM answer: {answer_text[:200]}")
            
            # Parse answer based on expected format
            answer = self._parse_answer(answer_text, answer_format)
            
            return answer
            
        except Exception as e:
            logger.error(f"Error solving question: {str(e)}")
            return None
    
    def _preprocess_resources(self, resources, question, context=""):
        """Pre-process resources using data analyzer"""
        processed = {}
        question_lower = question.lower()
        
        # Extract cutoff value if present
        cutoff_value = None
        if context:
            cutoff_match = re.search(r'(\d+)', context)
            if cutoff_match:
                cutoff_value = int(cutoff_match.group(1))
                logger.info(f"Found cutoff value: {cutoff_value}")
        
        for url, resource in resources.items():
            if not resource or not isinstance(resource, dict):
                processed[url] = resource
                continue
                
            resource_type = resource.get('type')
            content = resource.get('content')
            
            if content is None:
                processed[url] = resource
                continue
            
            # Handle audio files - transcribe them
            if resource_type == 'audio':
                transcription = self.transcribe_audio(content)
                processed[url] = {
                    'type': 'audio_transcribed',
                    'content': content,
                    'transcription': transcription
                }
                continue
            
            # Try to parse CSV/JSON and perform initial analysis
            if resource_type == 'text' and content:
                # Check if it's CSV
                if ',' in content and '\n' in content:
                    df = self.analyzer.parse_csv(content)
                    if df is not None:
                        # Perform relevant analysis based on question keywords
                        analysis = self.analyzer.analyze_dataframe(df, question)
                        
                        # If cutoff value exists, add filtered analysis
                        if cutoff_value:
                            numeric_cols = df.select_dtypes(include=['number']).columns
                            for col in numeric_cols:
                                try:
                                    filtered = df[df[col] > cutoff_value]
                                    analysis['filtered_count'] = len(filtered)
                                    analysis[f'filtered_sum_{col}'] = float(filtered[col].sum())
                                    logger.info(f"Filtered {col} > {cutoff_value}: sum={filtered[col].sum()}, count={len(filtered)}")
                                except:
                                    pass
                        
                        processed[url] = {
                            'type': 'dataframe',
                            'content': content,
                            'dataframe': df,
                            'analysis': analysis,
                            'cutoff': cutoff_value
                        }
                        continue
                
                # Check if it's JSON
                try:
                    data = self.analyzer.parse_json(content)
                    if data is not None:
                        processed[url] = {
                            'type': 'json_data',
                            'content': content,
                            'parsed': data
                        }
                        continue
                except:
                    pass
            
            # For HTML content, extract key information
            if resource_type == 'html' and isinstance(content, dict):
                text = content.get('text', '')
                # Look for numbers, codes, or specific patterns
                numbers = re.findall(r'\b\d{4,}\b', text)
                codes = re.findall(r'\b[A-Z0-9]{5,}\b', text)
                
                processed[url] = {
                    'type': 'html',
                    'content': content,
                    'extracted_numbers': numbers,
                    'extracted_codes': codes
                }
                continue
            
            # Keep original if no special processing
            processed[url] = resource
        
        return processed
    
    def _build_resource_context(self, resources):
        """Build context string from gathered resources"""
        if not resources:
            return "No additional resources provided."
        
        context_parts = ["=== AVAILABLE RESOURCES ===\n"]
        
        for url, resource in resources.items():
            if not resource or not isinstance(resource, dict):
                continue
                
            resource_type = resource.get('type')
            content = resource.get('content')
            
            if content is None:
                logger.warning(f"Resource {url} has no content")
                continue
            
            if resource_type == 'audio_transcribed':
                context_parts.append(f"\n🎵 Audio file from {url}:")
                transcription = resource.get('transcription')
                if transcription:
                    context_parts.append(f"TRANSCRIPTION (THIS IS THE ACTUAL QUESTION): {transcription}")
                else:
                    context_parts.append("(Transcription failed)")
            
            elif resource_type == 'pdf':
                context_parts.append(f"\n📄 PDF from {url}:")
                context_parts.append(f"Pages: {content.get('num_pages')}")
                for page_num, page_text in content.get('pages', {}).items():
                    context_parts.append(f"\n--- Page {page_num} ---")
                    context_parts.append(page_text[:3000])
            
            elif resource_type == 'dataframe':
                context_parts.append(f"\n📊 CSV/DataFrame from {url}:")
                analysis = resource.get('analysis', {})
                cutoff = resource.get('cutoff')
                
                context_parts.append(f"Rows: {analysis.get('shape', [0])[0]}, Columns: {analysis.get('shape', [0, 0])[1]}")
                context_parts.append(f"Columns: {', '.join(analysis.get('columns', []))}")
                
                # Show analysis results prominently
                summary = analysis.get('summary', {})
                if summary:
                    context_parts.append("\n📈 Analysis Results:")
                    for key, value in summary.items():
                        context_parts.append(f"  {key}: {value}")
                
                if cutoff:
                    context_parts.append(f"\n🔍 FILTERED ANALYSIS (values > {cutoff}):")
                    for key in analysis.keys():
                        if 'filtered' in key:
                            context_parts.append(f"  {key}: {analysis[key]}")
                
                # Include sample data
                df = resource.get('dataframe')
                if df is not None:
                    context_parts.append("\n📋 Sample Data (first 10 rows):")
                    context_parts.append(df.head(10).to_string())
            
            elif resource_type == 'json_data':
                context_parts.append(f"\n📋 JSON from {url}:")
                parsed = resource.get('parsed')
                context_parts.append(json.dumps(parsed, indent=2)[:3000])
                    
            elif resource_type == 'text':
                context_parts.append(f"\n📄 Text file from {url}:")
                context_parts.append(str(content)[:5000])
                
            elif resource_type == 'html':
                context_parts.append(f"\n🌐 Web page from {url}:")
                
                numbers = resource.get('extracted_numbers', [])
                codes = resource.get('extracted_codes', [])
                if numbers:
                    context_parts.append(f"Found numbers: {', '.join(numbers)}")
                if codes:
                    context_parts.append(f"Found codes: {', '.join(codes)}")
                
                if isinstance(content, dict):
                    text = content.get('text', '')
                    context_parts.append(f"\nPage text:\n{text[:3000]}")
                else:
                    context_parts.append(str(content)[:3000])
                
            elif resource_type == 'binary':
                if isinstance(content, dict):
                    size = content.get('size', 0)
                    context_parts.append(f"\n📦 Binary file from {url} (size: {size} bytes)")
                else:
                    context_parts.append(f"\n📦 Binary file from {url}")
        
        return '\n'.join(context_parts)
    
    def _parse_answer(self, answer_text, answer_format):
        """Parse the LLM's answer into the correct format"""
        
        # Clean up the answer
        answer_text = answer_text.strip()
        
        # Remove quotes if present
        if answer_text.startswith('"') and answer_text.endswith('"'):
            answer_text = answer_text[1:-1]
        if answer_text.startswith("'") and answer_text.endswith("'"):
            answer_text = answer_text[1:-1]
        
        try:
            if answer_format == 'number':
                # Extract number from text
                match = re.search(r'-?\d+\.?\d*', answer_text)
                if match:
                    num = float(match.group())
                    return int(num) if num.is_integer() else num
                return None
                
            elif answer_format == 'boolean':
                answer_lower = answer_text.lower()
                if 'true' in answer_lower or answer_lower == 'yes':
                    return True
                elif 'false' in answer_lower or answer_lower == 'no':
                    return False
                return None
                
            elif answer_format == 'json':
                # Try to extract JSON object
                json_match = re.search(r'\{.*\}', answer_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                # Try array format
                json_match = re.search(r'\[.*\]', answer_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                return None
                
            elif answer_format == 'base64':
                # Return as-is, assuming it's a base64 string
                return answer_text
                
            else:  # string (default)
                # For strings, just return the cleaned text
                # But if it looks like a number, try to parse it
                if answer_text.isdigit():
                    return int(answer_text)
                try:
                    num = float(answer_text)
                    return int(num) if num.is_integer() else num
                except:
                    pass
                
                return answer_text
                
        except Exception as e:
            logger.error(f"Error parsing answer: {str(e)}")
            # Return raw text as fallback
            return answer_text