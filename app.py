import requests
from bs4 import BeautifulSoup, Comment
from urllib.parse import urljoin, urlparse
import time
import re
import json
import os # For environment variables
import uuid
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify, request as flask_request 
from flask_cors import CORS
from duckduckgo_search import DDGS
from tavily import TavilyClient
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from io import BytesIO

# Load environment variables from .env file
load_dotenv()

# For Gemini API
from google.generativeai import GenerativeModel, configure

# For Langchain (with fallback to simple memory)
try:
    from langchain.memory import ConversationBufferMemory
    from langchain.schema import HumanMessage, AIMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    print("Warning: Langchain not available, using simple memory management")
    LANGCHAIN_AVAILABLE = False

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# NOTE: Global Gemini API configuration is removed from here.
# It will be done within each route that uses the API.

# --- Chat Session Management ---
chat_sessions = {}  # {session_id: {"messages": list, "article_content": str, "article_url": str, "last_activity": datetime, "status": str, "progress_message": str}}
session_lock = threading.Lock()
SESSION_TIMEOUT_MINUTES = 10

def cleanup_expired_sessions():
    """Remove sessions that have been inactive for more than SESSION_TIMEOUT_MINUTES"""
    with session_lock:
        current_time = datetime.now()
        expired_sessions = []
        for session_id, session_data in chat_sessions.items():
            if current_time - session_data["last_activity"] > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del chat_sessions[session_id]
            print(f"  Cleaned up expired chat session: {session_id}")
        
        if expired_sessions:
            print(f"  Cleaned up {len(expired_sessions)} expired chat sessions")

def update_session_activity(session_id):
    """Update the last activity time for a session"""
    if session_id in chat_sessions:
        chat_sessions[session_id]["last_activity"] = datetime.now()

# --- Helper Functions (Scraping Logic - largely unchanged) ---

def extract_article_details(article_url, headers):
    print(f"    Extracting details from: {article_url}")
    details = {
        "Article Heading": "Not found",
        "Article Date": "Not found",
        "Article first few lines": "Not found",
        "Article Link": article_url
    }
    max_summary_length = 300
    try:
        response = requests.get(article_url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        title_tag = soup.select_one('h1#page-title') or \
                    soup.select_one('h1.ds-text-heading--2xl span') or \
                    soup.select_one('article h1') or \
                    soup.select_one('h1')
        if title_tag: details["Article Heading"] = title_tag.get_text(strip=True)

        specific_date_span = soup.select_one('span.create-date')
        if specific_date_span:
            date_text = specific_date_span.get_text(strip=True)
            if date_text: details["Article Date"] = date_text
        
        if details["Article Date"] == "Not found":
            date_tag = soup.find('time', attrs={'datetime': True})
            if date_tag and date_tag.get('datetime'):
                details["Article Date"] = date_tag['datetime'].split('T')[0]
            else:
                date_div_selectors = [
                    'div.ds-text-body--sm.ds-u-color--gray', 
                    'p.ds-text-body--xs.ds-u-color--gray',
                    'div.date-display-single', 'p.published-date'
                ]
                for selector in date_div_selectors:
                    date_element = soup.select_one(selector)
                    if date_element:
                        date_text_fallback = date_element.get_text(strip=True)
                        match = re.search(r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}', date_text_fallback)
                        if match: details["Article Date"] = match.group(0); break 
                        elif "Published on" in date_text_fallback: details["Article Date"] = date_text_fallback.replace("Published on", "").strip(); break
                        elif any(month in date_text_fallback for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]): details["Article Date"] = date_text_fallback; break
            if details["Article Date"] == "Not found" and soup.select_one('meta[property="article:published_time"]'):
                details["Article Date"] = soup.select_one('meta[property="article:published_time"]')['content'].split('T')[0]
        
        content_area_selectors = ['article', 'div[role="main"]', 'div.field--name-body', 'div.content', 'div.entry-content', 'div.post-content', 'div.article-body', 'div.story-body', 'div.article-content', 'section.article-content']
        content_element = next((soup.select_one(s) for s in content_area_selectors if soup.select_one(s)), None) or soup.body

        if content_element:
            paragraphs = content_element.find_all('p', recursive=True)
            summary_text = ""
            for p_tag in paragraphs:
                skip = any(p.name in ['nav', 'header', 'footer', 'aside', 'form', 'figure'] or (p.has_attr('class') and any(ci in p['class'] for ci in ['menu', 'button', 'link', 'meta'])) for p in p_tag.parents if p != content_element)
                if skip: continue
                p_text = p_tag.get_text(strip=True)
                if p_text:
                    if len(summary_text) + len(p_text) + 1 < max_summary_length: summary_text += p_text + " "
                    else:
                        remaining_len = max_summary_length - len(summary_text) -1
                        if remaining_len > 20: summary_text += p_text[:remaining_len] + "..."
                        break 
            details["Article first few lines"] = summary_text.strip()
        
        if len(details["Article first few lines"]) < 50:
            meta_desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
            if meta_desc_tag and meta_desc_tag.get('content'):
                 details["Article first few lines"] = meta_desc_tag['content'][:max_summary_length].strip()
        # Fetch full content for sentiment and impact analysis
        full_content = fetch_article_main_content(article_url, headers)
        sentiment = analyze_sentiment_with_llm(full_content)
        impact_analysis = analyze_impact_with_llm(details["Article Heading"], article_url, full_content)
        
        details["Sentiment"] = sentiment
        details["Impact_score"] = impact_analysis["Impact_score"]
        details["Impact_score_reason"] = impact_analysis["Impact_score_reason"]
        details["Impact"] = impact_analysis["Impact"]

    except Exception as e: print(f"      ERROR processing {article_url} for details: {e}")
    time.sleep(0.5) 
    return details

def scrape_cms_newsroom_with_specific_link_selector(start_url, max_link_pages=None, headers=None):
    if headers is None: headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'}
    all_article_urls, current_page_url, pages_scraped_count, visited_page_urls = set(), start_url, 0, set()
    while current_page_url and (max_link_pages is None or pages_scraped_count < max_link_pages):
        if current_page_url in visited_page_urls: break
        print(f"Gathering links from page ({pages_scraped_count + 1}" + (f"/{max_link_pages}" if max_link_pages else "") + f"): {current_page_url}")
        visited_page_urls.add(current_page_url)
        try:
            response = requests.get(current_page_url, headers=headers, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            pages_scraped_count += 1
            links_found_on_this_page = 0
            for row_container in soup.select('div.views-row'):
                link_tag = row_container.select_one('a.ds-c-button.newsroom-main-view-link[href]')
                if link_tag and link_tag.get('href'):
                    abs_url = urljoin(current_page_url, link_tag['href'])
                    if urlparse(abs_url).netloc == urlparse(start_url).netloc:
                        cleaned_url = urlparse(abs_url)._replace(query="", fragment="").geturl()
                        if cleaned_url not in all_article_urls:
                            all_article_urls.add(cleaned_url)
                            links_found_on_this_page +=1
            print(f"  Found {links_found_on_this_page} new unique links on this page. Total unique links so far: {len(all_article_urls)}")
            see_more_button = soup.select_one('a.button.vis-show-more-button[rel="next"][href]')
            if see_more_button and see_more_button.get('href'):
                next_url = urljoin(start_url, see_more_button['href'])
                current_page_url = next_url if next_url != current_page_url and next_url not in visited_page_urls else None
            else: current_page_url = None
            if current_page_url: time.sleep(1)
        except Exception as e: print(f"ERROR link gathering from {current_page_url}: {e}"); current_page_url = None
    return sorted(list(all_article_urls))

def fetch_article_main_content(article_url, headers):
    print(f"    Fetching main content from: {article_url}")
    try:
        response = requests.get(article_url, headers=headers, timeout=20)
        print(f"    HTTP Status: {response.status_code}")
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        for element_type in ['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'button', 'input', 'select', 'textarea', 'noscript', 'img', 'figure', 'iframe', 'svg']:
            for element in soup.find_all(element_type): element.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)): comment.extract()
        main_content_selectors = ['article', 'main', 'div[role="main"]', 'div.content', 'div.entry-content', 'div.post-content', 'div.article-body', 'div.story-body', 'div.article-content', 'section.article-content']
        content_element = next((soup.select_one(s) for s in main_content_selectors if soup.select_one(s)), None)
        if not content_element: content_element = soup.body
        if content_element:
            text_parts = [el.get_text(separator=' ', strip=True) for el in content_element.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'span', 'td', 'th'], recursive=True) if el.get_text(strip=True) and len(el.get_text(strip=True).split()) > 2 and not any(p.name in ['nav', 'header', 'footer', 'aside', 'form', 'figure'] or (p.has_attr('class') and any(ci in p['class'] for ci in ['menu', 'button', 'link', 'meta'])) for p in el.parents if p != content_element)]
            full_text = "\n".join(text_parts)
            full_text = re.sub(r'\s*\n\s*', '\n', full_text).strip()
            full_text = re.sub(r'[ \t]{2,}', ' ', full_text)
            if not full_text: full_text = content_element.get_text(separator='\n', strip=True)
            print(f"      Extracted content length: {len(full_text)} characters.")
            return full_text if len(full_text) > 50 else "Error: Fetched content was too short after cleaning."
        return "Error: Could not extract main content."
    except requests.exceptions.HTTPError as e:
        print(f"      HTTP Error: {e}")
        return f"Error: HTTP {e.response.status_code} - {e}"
    except Exception as e: 
        print(f"      General Error: {e}")
        return f"Error during content extraction for {article_url}: {e}"

@app.route('/api/cms-articles', methods=['GET'])
def get_cms_articles_api():
    target_newsroom_url = "https://www.cms.gov/about-cms/contact/newsroom"
    max_link_pages = None 
    
    # Get max_articles parameter from query string
    max_articles_param = flask_request.args.get('max_articles', '6')
    if max_articles_param.upper() == 'NA':
        max_detail_articles = None
    else:
        try:
            max_detail_articles = int(max_articles_param)
        except ValueError:
            max_detail_articles = 6  # Default fallback
    
    start_time = time.time()
    print(f"API call: /api/cms-articles. Max articles: {max_detail_articles or 'All'}. Stage 1: Gathering links...")
    headers = {'User-Agent': 'Mozilla/5.0 (Amgen Scraper - Article List)'}
    all_links = scrape_cms_newsroom_with_specific_link_selector(target_newsroom_url, max_link_pages=max_link_pages, headers=headers)
    if not all_links: return jsonify({"error": "No article links found.", "articles": []}), 500
    
    print(f"Stage 1 Complete: Found {len(all_links)} links. Stage 2: Extracting details...")
    articles_data = [extract_article_details(link, headers) for i, link in enumerate(all_links) if max_detail_articles is None or i < max_detail_articles]
    
    print(f"Stage 2 Complete. Scraped details for {len(articles_data)} articles. Total time: {time.time() - start_time:.2f}s.")
    return jsonify(articles_data)

# ... (imports and other functions in app.py remain the same) ...

@app.route('/api/analyze-article', methods=['GET'])
def analyze_article_api():
    # Fetch API_KEY from environment for this specific invocation
    api_key_for_request = os.environ.get("GOOGLE_API_KEY")
    if not api_key_for_request:
        print("ERROR: /api/analyze-article - API_KEY environment variable not found for this request.")
        return jsonify({"error": "Gemini API key not configured on the server for this request."}), 503
    
    try:
        configure(api_key=api_key_for_request) # Configure Gemini for this request
        print("  Gemini API configured for /api/analyze-article request.")
    except Exception as e:
        print(f"  ERROR: Failed to configure Gemini API for /api/analyze-article: {e}")
        return jsonify({"error": f"Failed to configure Gemini API: {str(e)}"}), 500

    article_url = flask_request.args.get('url')
    if not article_url: return jsonify({"error": "Missing 'url' query parameter."}), 400
    
    print(f"API call: /api/analyze-article for URL: {article_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Amgen Scraper - Analyze Content)'}
    content = fetch_article_main_content(article_url, headers)
    if content.startswith("Error:") or len(content) < 100:
        return jsonify({"error": f"Content issue: {content}", "preview": content[:200]}), 400

    # Get article data from JSON to extract existing analysis
    article_data = None
    try:
        with open('cms_articles_details.json', 'r') as f:
            articles = json.load(f)
            article_data = next((a for a in articles if a.get('Article Link') == article_url), None)
    except:
        pass
    
    existing_sentiment = article_data.get('Sentiment', 'Neutral') if article_data else 'Neutral'
    existing_impact = article_data.get('Impact', 'Moderate') if article_data else 'Moderate'
    existing_impact_reason = article_data.get('Impact_score_reason', 'No analysis available') if article_data else 'No analysis available'
    
    prompt_template = f"""You are the CEO of Amgen, a large-scale life sciences company. Provide a comprehensive impact analysis for this article.
    
    The article sentiment is: {existing_sentiment}
    The article impact level is: {existing_impact}
    
    Based on the article content below, provide:
    1. Sentiment Justification: Maximum 3 bullet points in HTML format explaining why the sentiment is {existing_sentiment}
    2. Plan of Action: Structured action items in HTML format (use <ul><li> or <ol><li> tags)
    
    Article Content: {content}
    
    Return as JSON with keys: "sentiment", "sentiment_justification", "impact_level", "impact_reason", "plan_of_action"
    - sentiment: "{existing_sentiment}"
    - sentiment_justification: HTML formatted bullet points (max 3)
    - impact_level: "{existing_impact}"
    - impact_reason: "{existing_impact_reason}"
    - plan_of_action: HTML formatted action items"""
    # MODIFIED PROMPT: Explicitly ask for JSON output
    formatted_prompt = prompt_template

    try:
        print("  Sending analysis prompt to Gemini...")
        model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
        # Request JSON output from the model
        generation_config_for_json = {"response_mime_type": "application/json"}
        response = model.generate_content(
            formatted_prompt,
            generation_config=generation_config_for_json # Add this
        )
        
        raw_analysis_text = ""
        if hasattr(response, 'text') and response.text:
            raw_analysis_text = response.text
        elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            raw_analysis_text = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text'))
        
        if not raw_analysis_text:
            print(f"  Gemini analysis response was empty. Full response: {response}")
            return jsonify({"error": "Received an empty analysis from the AI."}), 500
        
        print(f"  Received raw analysis text from Gemini: {raw_analysis_text[:500]}...") # Log snippet

        # Attempt to parse the text as JSON, after stripping potential markdown fences
        json_str_to_parse = raw_analysis_text.strip()
        if json_str_to_parse.startswith("```json"):
            json_str_to_parse = json_str_to_parse[7:] # Remove ```json\n
        if json_str_to_parse.startswith("```"): # More generic fence removal
             json_str_to_parse = json_str_to_parse[3:]
        if json_str_to_parse.endswith("```"):
            json_str_to_parse = json_str_to_parse[:-3]
        json_str_to_parse = json_str_to_parse.strip()

        try:
            parsed_json_response = json.loads(json_str_to_parse)
            # Validate expected keys for new format
            sentiment = parsed_json_response.get("sentiment", existing_sentiment)
            sentiment_justification = parsed_json_response.get("sentiment_justification", "Could not determine from JSON")
            impact_level = parsed_json_response.get("impact_level", existing_impact)
            impact_reason = parsed_json_response.get("impact_reason", existing_impact_reason)
            plan_of_action = parsed_json_response.get("plan_of_action", "Could not determine from JSON")

            analysis_parts = {
                "sentiment": sentiment,
                "sentiment_justification": sentiment_justification,
                "impact_level": impact_level,
                "impact_reason": impact_reason,
                "plan_of_action": plan_of_action,
                "full_text": raw_analysis_text
            }
            print(f"  Successfully parsed JSON analysis: {analysis_parts}")
            return jsonify(analysis_parts)

        except json.JSONDecodeError as e:
            print(f"  JSONDecodeError parsing Gemini response. String was: '{json_str_to_parse}'. Error: {e}")
            print(f"  Original full_text from Gemini for context: {raw_analysis_text}")
            # Fallback to trying to parse the previous numbered list format if JSON parsing fails badly
            # This is less ideal as the model was asked for JSON.
            print("  Falling back to regex parsing due to JSONDecodeError...")
            fallback_parts = {"sentiment": "Fallback: Could not determine", "justification": "Fallback: Could not determine", "plan_of_action": "Fallback: Could not determine", "full_text": raw_analysis_text}
            lines = raw_analysis_text.split('\n')
            current_key = None
            header_patterns = {
                "sentiment": re.compile(r"^\s*1\.\s*(?:\*\*)?Sentiment(?:\*\*)?\s*[:\-\s]?(.*)", re.IGNORECASE),
                "justification": re.compile(r"^\s*2\.\s*(?:\*\*)?(?:Justify|Justification)(?:\*\*)?\s*[:\-\s]?(.*)", re.IGNORECASE),
                "plan_of_action": re.compile(r"^\s*3\.\s*(?:\*\*)?Possible plan of action(?:\*\*)?\s*[:\-\s]?(.*)", re.IGNORECASE)
            }
            temp_buffers = {"sentiment": [], "justification": [], "plan_of_action": []}

            for line_content in lines:
                matched_new_section = False
                for key, pattern in header_patterns.items():
                    match = pattern.match(line_content.strip())
                    if match:
                        current_key = key
                        content_on_header_line = match.group(1).strip()
                        if content_on_header_line: temp_buffers[current_key].append(content_on_header_line)
                        matched_new_section = True
                        break
                if not matched_new_section and current_key:
                    if line_content.strip(): temp_buffers[current_key].append(line_content.strip())
                    elif temp_buffers[current_key]: temp_buffers[current_key].append("")
            
            for key in temp_buffers: fallback_parts[key] = "\n".join(temp_buffers[key]).strip() or f"Fallback: Could not determine {key}"
            return jsonify(fallback_parts)

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"AI analysis failed: {str(e)}"}), 500

# ... (rest of app.py including summarize_article_api and other functions remains the same)
@app.route('/api/summarize-article', methods=['GET'])
def summarize_article_api():
    # Fetch API_KEY from environment for this specific invocation
    api_key_for_request = os.environ.get("GOOGLE_API_KEY")
    if not api_key_for_request:
        print("ERROR: /api/summarize-article - API_KEY environment variable not found for this request.")
        return jsonify({"error": "Gemini API key not configured on the server for this request."}), 503

    try:
        configure(api_key=api_key_for_request) # Configure Gemini for this request
        print("  Gemini API configured for /api/summarize-article request.")
    except Exception as e:
        print(f"  ERROR: Failed to configure Gemini API for /api/summarize-article: {e}")
        return jsonify({"error": f"Failed to configure Gemini API: {str(e)}"}), 500

    article_url = flask_request.args.get('url')
    if not article_url: return jsonify({"error": "Missing 'url' query parameter."}), 400

    print(f"API call: /api/summarize-article for URL: {article_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Amgen Scraper - Summarize Content)'}
    content = fetch_article_main_content(article_url, headers)
    if content.startswith("Error:") or len(content) < 50:
        return jsonify({"error": f"Content issue: {content}", "preview": content[:200]}), 400

    prompt = f"Please provide a concise, neutral summary of the following article content, capturing the main points. The summary should be approximately 10 sentences long. Bullet points are appreciated\n\nArticle Content:\n{content}\n\nSummary:"
    try:
        print("  Sending summarization prompt to Gemini...")
        model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
        response = model.generate_content(prompt)
        summary = response.text if hasattr(response, 'text') and response.text else "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text')) if response.candidates else ""

        if not summary: return jsonify({"error": "Empty summary from AI."}), 500
        print("  Received summary from Gemini.")
        return jsonify({"summary": summary.strip()})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"AI summarization failed: {str(e)}"}), 500

@app.route('/api/chat-with-article', methods=['POST'])
def chat_with_article():
    # Fetch API_KEY from environment
    api_key_for_request = os.environ.get("GOOGLE_API_KEY")
    if not api_key_for_request:
        print("ERROR: /api/chat-with-article - API_KEY environment variable not found.")
        return jsonify({"error": "Gemini API key not configured on the server."}), 503

    try:
        configure(api_key=api_key_for_request)
        print("  Gemini API configured for /api/chat-with-article request.")
    except Exception as e:
        print(f"  ERROR: Failed to configure Gemini API for /api/chat-with-article: {e}")
        return jsonify({"error": f"Failed to configure Gemini API: {str(e)}"}), 500

    # Clean up expired sessions
    cleanup_expired_sessions()
    
    data = flask_request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    
    action = data.get('action')
    
    if action == 'start':
        # Start new chat session
        article_url = data.get('url')
        additional_context = data.get('additional_context', '')
        context_type = data.get('context_type', 'article')
        
        if not article_url:
            return jsonify({"error": "Missing 'url' in request body for start action."}), 400
        
        print(f"API call: /api/chat-with-article - Starting chat for URL: {article_url}")
        
        # Fetch article content
        headers = {'User-Agent': 'Mozilla/5.0 (Amgen Scraper - Chat Content)'}
        content = fetch_article_main_content(article_url, headers)
        
        # Create session regardless, but handle invalid content
        session_id = str(uuid.uuid4())
        
        print(f"  Content received: {content[:200]}...")  # Debug log
        
        # Check for various error conditions
        is_error = (
            content.startswith("Error:") or 
            len(content) < 100 or  # Increased threshold
            "404" in content or 
            "Not Found" in content or
            "Page not found" in content.lower() or
            "could not extract main content" in content.lower()
        )
        
        if is_error:
            # Create session with error state
            with session_lock:
                chat_sessions[session_id] = {
                    "messages": [],
                    "article_content": None,
                    "article_url": article_url,
                    "last_activity": datetime.now(),
                    "status": "error",
                    "progress_message": "Article could not be loaded"
                }
            
            print(f"  Created chat session with error: {session_id} - Content issue: {content[:100]}")
            
            return jsonify({
                "session_id": session_id,
                "message": "Hello! I tried to read the article at the link you provided. But it seems that this link is not valid anymore. Please close this session and try another article link.",
                "status": "error"
            })
        
        # Create session with loading state and start background processing
        with session_lock:
            chat_sessions[session_id] = {
                "messages": [],
                "article_content": content,
                "additional_context": additional_context,
                "context_type": context_type,
                "article_url": article_url,
                "last_activity": datetime.now(),
                "status": "loading",
                "progress_message": "Loading article content..."
            }
        
        print(f"  Created new chat session: {session_id} - Starting background processing")
        
        # Start background processing
        def process_article_async():
            try:
                # Update status: Analyzing
                with session_lock:
                    if session_id in chat_sessions:
                        chat_sessions[session_id]["status"] = "analyzing"
                        chat_sessions[session_id]["progress_message"] = "Analyzing article content..."
                
                # Generate article summary with additional context if provided
                print("  Generating article summary...")
                with session_lock:
                    if session_id in chat_sessions:
                        chat_sessions[session_id]["progress_message"] = "Generating response..."
                
                if context_type == 'strategic_report' and additional_context:
                    summary_prompt = f"""You have access to both an original article and a comprehensive strategic report based on that article and related sources.

Original Article Content:
{content[:1000]}...

Strategic Report:
{additional_context[:2000]}...

Provide a concise 2-line summary focusing on the strategic implications and key findings from both the article and the comprehensive analysis.

Summary (2 lines maximum):"""
                else:
                    summary_prompt = f"""Provide a concise 2-line summary of the following article content. Focus on the main topic and key points.

Article Content:
{content[:2000]}...

Summary (2 lines maximum):"""
                
                model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
                summary_response = model.generate_content(summary_prompt)
                
                article_summary = ""
                if hasattr(summary_response, 'text') and summary_response.text:
                    article_summary = summary_response.text.strip()
                else:
                    if context_type == 'strategic_report':
                        article_summary = "This discussion covers strategic analysis of healthcare policy developments and their business implications."
                    else:
                        article_summary = "This article discusses important healthcare policy updates and regulatory changes."
                
                print(f"  Generated summary: {article_summary[:100]}...")
                
                # Update status: Questions
                with session_lock:
                    if session_id in chat_sessions:
                        chat_sessions[session_id]["progress_message"] = "Preparing suggested questions..."
                
                # Generate suggested questions based on context type
                print("  Generating suggested questions...")
                if context_type == 'strategic_report' and additional_context:
                    questions_prompt = f"""Based on the following strategic report and original article, generate exactly 3 relevant questions that a user might want to ask. The questions should focus on strategic implications, business impact, and actionable insights.

Original Article:
{content[:1000]}...

Strategic Report:
{additional_context[:2000]}...

Return only the 3 questions as a JSON array with no additional text:
["Question 1?", "Question 2?", "Question 3?"]"""  
                else:
                    questions_prompt = f"""Based on the following article content, generate exactly 3 relevant questions that a user might want to ask about this article. The questions should be:
1. Specific to the article content
2. Helpful for understanding key points
3. Encourage deeper discussion

Article Content:
{content[:2000]}...

Return only the 3 questions as a JSON array with no additional text:
["Question 1?", "Question 2?", "Question 3?"]"""
                
                generation_config = {"response_mime_type": "application/json"}
                questions_response = model.generate_content(questions_prompt, generation_config=generation_config)
                
                suggested_questions = []
                if hasattr(questions_response, 'text') and questions_response.text:
                    try:
                        parsed_questions = json.loads(questions_response.text.strip())
                        if isinstance(parsed_questions, list) and len(parsed_questions) == 3:
                            suggested_questions = parsed_questions
                        else:
                            raise ValueError("Invalid questions format")
                    except (json.JSONDecodeError, ValueError):
                        print("  Could not load follow up questions.")
                        suggested_questions = [
                            "What is the main topic of this article?",
                            "What are the key points discussed?",
                            "How might this impact the healthcare industry?"
                        ]
                else:
                    print("  Could not load follow up questions.")
                    suggested_questions = [
                        "What is the main topic of this article?",
                        "What are the key points discussed?", 
                        "How might this impact the healthcare industry?"
                    ]
                
                print(f"  Generated {len(suggested_questions)} suggested questions")
                
                # Create final message
                first_message = f"Hello! I have read the article. It talks about {article_summary} Please ask your question, or you may choose from the options below."
                
                # Update session to ready state
                with session_lock:
                    if session_id in chat_sessions:
                        chat_sessions[session_id]["status"] = "ready"
                        chat_sessions[session_id]["progress_message"] = "Ready to chat!"
                        chat_sessions[session_id]["message"] = first_message
                        chat_sessions[session_id]["suggested_questions"] = suggested_questions
                
                print(f"  Background processing completed for session: {session_id}")
                
            except Exception as e:
                print(f"  Error in background processing: {e}")
                with session_lock:
                    if session_id in chat_sessions:
                        chat_sessions[session_id]["status"] = "error"
                        chat_sessions[session_id]["progress_message"] = "Processing failed"
        
        # Start background thread
        thread = threading.Thread(target=process_article_async)
        thread.daemon = True
        thread.start()
        
        # Return immediate response with loading status
        return jsonify({
            "session_id": session_id,
            "status": "loading",
            "progress_message": "Loading article content..."
        })
    
    elif action == 'close':
        # Close and invalidate session
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({"error": "Missing 'session_id' in request body."}), 400
        
        with session_lock:
            if session_id in chat_sessions:
                del chat_sessions[session_id]
                print(f"  Closed and invalidated chat session: {session_id}")
                return jsonify({"message": "Session closed successfully.", "status": "closed"})
            else:
                return jsonify({"error": "Session not found or already closed."}), 404
    
    elif action == 'message':
        # Handle chat message
        session_id = data.get('session_id')
        user_message = data.get('message')
        
        if not session_id or not user_message:
            return jsonify({"error": "Missing 'session_id' or 'message' in request body."}), 400
        
        with session_lock:
            if session_id not in chat_sessions:
                return jsonify({"error": "Invalid or expired session ID."}), 404
            
            session_data = chat_sessions[session_id]
            
            # Check if session is in error state
            if session_data.get("status") == "error":
                return jsonify({"error": "This session has an invalid article. Please close this session and try another article link."}), 400
            
            update_session_activity(session_id)
        
        print(f"API call: /api/chat-with-article - Message for session: {session_id}")
        
        try:
            # Get conversation history and content
            messages = session_data["messages"]
            article_content = session_data["article_content"]
            additional_context = session_data.get("additional_context", "")
            context_type = session_data.get("context_type", "article")
            
            # Build conversation history string
            conversation_history = ""
            for msg in messages:
                conversation_history += f"{msg['role']}: {msg['content']}\n"
            
            # Create enhanced prompt based on context type
            if context_type == 'strategic_report' and additional_context:
                prompt = f"""You are an AI assistant helping to discuss and analyze a strategic report and its underlying article. You have access to both the original article and a comprehensive strategic analysis.

Original Article Content:
{article_content[:2000]}

Strategic Report:
{additional_context[:3000]}

Conversation History:
{conversation_history}

Current Question: {user_message}

Please provide a helpful response based on both the article content and strategic analysis. Focus on strategic implications, business impact, and actionable insights. Be concise and informative.

After your response, suggest 3 new relevant questions focusing on strategic aspects, competitive implications, or actionable recommendations.

Return your response as a JSON object with this exact format:
{{
  "response": "Your detailed answer here",
  "suggested_questions": ["Question 1?", "Question 2?", "Question 3?"]
}}"""
            else:
                prompt = f"""You are an AI assistant helping to discuss and analyze an article. 

Article Content:
{article_content}

Conversation History:
{conversation_history}

Current Question: {user_message}

Please provide a helpful response based on the article content and conversation context. Be concise and informative.

After your response, you must also suggest 3 new relevant questions that the user might want to ask next, based on:
1. The current conversation context
2. Unexplored aspects of the article
3. Natural follow-up questions to your response

Return your response as a JSON object with this exact format:
{{
  "response": "Your detailed answer here",
  "suggested_questions": ["Question 1?", "Question 2?", "Question 3?"]
}}"""
            
            # Get response from Gemini with JSON format
            model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
            generation_config = {"response_mime_type": "application/json"}
            response = model.generate_content(prompt, generation_config=generation_config)
            
            raw_response = ""
            if hasattr(response, 'text') and response.text:
                raw_response = response.text
            elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                raw_response = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text'))
            
            if not raw_response:
                return jsonify({"error": "Empty response from AI."}), 500
            
            # Parse JSON response
            try:
                parsed_response = json.loads(raw_response.strip())
                ai_message = parsed_response.get("response", "")
                suggested_questions = parsed_response.get("suggested_questions", [])
                
                # Validate suggested questions
                if not isinstance(suggested_questions, list) or len(suggested_questions) != 3:
                    print("  Could not load follow up questions.")
                    suggested_questions = [
                        "Can you elaborate on this topic?",
                        "What are the implications of this?",
                        "How does this relate to other aspects of the article?"
                    ]
                    
            except json.JSONDecodeError as e:
                print(f"  Could not load follow up questions.")
                # Fallback to treating entire response as message
                ai_message = raw_response
                suggested_questions = [
                    "Can you elaborate on this topic?",
                    "What are the implications of this?", 
                    "How does this relate to other aspects of the article?"
                ]
            
            # Add both messages to session history
            with session_lock:
                session_data["messages"].append({"role": "Human", "content": user_message})
                session_data["messages"].append({"role": "Assistant", "content": ai_message})
            
            print(f"  Generated response with {len(suggested_questions)} suggested questions for session: {session_id}")
            
            return jsonify({
                "message": ai_message.strip(),
                "session_id": session_id,
                "suggested_questions": suggested_questions
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Chat failed: {str(e)}"}), 500
    
    else:
        return jsonify({"error": "Invalid action. Use 'start', 'message', or 'close'."}), 400

@app.route('/api/generate-report', methods=['POST'])
def generate_report_api():
    """Generate comprehensive Amgen-focused report from expanded context"""
    api_key_for_request = os.environ.get("GOOGLE_API_KEY")
    if not api_key_for_request:
        return jsonify({"error": "Gemini API key not configured."}), 503
    
    try:
        configure(api_key=api_key_for_request)
        
        data = flask_request.get_json()
        if not data or 'expanded_context' not in data:
            return jsonify({"error": "Missing 'expanded_context' in request body."}), 400
        
        expanded_context = data['expanded_context']
        original_article = data.get('original_article', {})
        
        # Build context summary for the prompt
        context_summary = ""
        for i, ctx in enumerate(expanded_context, 1):
            context_summary += f"\n\n**Source {i}: {ctx.get('source', 'Unknown')}**\n"
            context_summary += f"Title: {ctx.get('title', 'N/A')}\n"
            context_summary += f"Date: {ctx.get('date', 'N/A')}\n"
            context_summary += f"URL: {ctx.get('url', 'N/A')}\n"
            context_summary += f"Summary: {ctx.get('summary', 'N/A')}\n"
            context_summary += f"Key Insights: {ctx.get('insights', 'N/A')}\n"
        
        # Add original article context if provided
        original_context = ""
        if original_article:
            original_context = f"\n\n**ORIGINAL ARTICLE CONTEXT:**\n"
            original_context += f"Title: {original_article.get('title', 'N/A')}\n"
            original_context += f"Impact Level: {original_article.get('impact', 'N/A')}\n"
            original_context += f"Impact Score: {original_article.get('impact_score', 'N/A')}/10\n"
            original_context += f"Impact Reasoning: {original_article.get('impact_reason', 'N/A')}\n"
            original_context += f"Sentiment: {original_article.get('sentiment', 'N/A')}\n"
        
        prompt = f"""You are the Chief Strategy Officer of Amgen, a leading biotechnology company. Analyze the following healthcare policy and industry developments to create a comprehensive strategic report with detailed regulatory change analysis and cross-functional impact assessment.

**EXPANDED CONTEXT FROM MULTIPLE SOURCES:**{context_summary}{original_context}

**INSTRUCTIONS:**
As Amgen's Chief Strategy Officer, provide a comprehensive analysis structured as follows:

## EXECUTIVE SUMMARY
- Brief overview of key developments and their strategic significance to Amgen
- Primary opportunities and threats identified
- Recommended strategic priorities and timeline
- Critical regulatory change classification summary

## REGULATORY CHANGE CLASSIFICATION & ANALYSIS
### Change Type Identification:
**Clearly classify each development as:**
- **Regulation Change**: New or modified FDA/CMS regulations with legal binding requirements
- **Guidance Change**: Updated FDA guidance documents, Q&A, or interpretive policies
- **Standards Change**: Modified industry standards, quality requirements, or technical specifications
- **Policy Change**: Shifts in reimbursement policies, coverage decisions, or administrative procedures
- **Other**: Legislative changes, court decisions, or international regulatory harmonization

### Regulatory Impact Severity:
- **Critical**: Immediate compliance required, significant business impact
- **Major**: Compliance required within 12-24 months, moderate business impact
- **Minor**: Guidance updates, minimal immediate impact
- **Monitoring**: Proposed changes requiring ongoing assessment

## CROSS-FUNCTIONAL IMPACT ASSESSMENT
### Affected Business Functions:
**Regulatory Affairs:**
- Submission strategy modifications required
- New compliance obligations and timelines
- Regulatory pathway implications

**Clinical Development:**
- Protocol modifications needed
- New endpoint requirements or study designs
- Patient safety and monitoring changes

**Manufacturing & Quality:**
- CMC (Chemistry, Manufacturing, Controls) updates
- Quality system modifications
- Supply chain and vendor qualification impacts

**Commercial Operations:**
- Marketing and promotional claim adjustments
- Sales force training requirements
- Market access and reimbursement strategy changes

**Medical Affairs:**
- Medical information updates
- Healthcare provider communication needs
- Post-market surveillance modifications

**Legal & Compliance:**
- Contract modifications with partners/vendors
- Compliance program updates
- Risk assessment and mitigation strategies

## SCOPE DETERMINATION ANALYSIS
### Product Scope Assessment:
**Marketed Products:**
- Which Amgen products are directly affected
- Required labeling or indication changes
- Post-market commitment modifications

**Pipeline Products:**
- Development program adjustments needed
- Regulatory submission timeline impacts
- Clinical trial protocol modifications

**Biosimilar Portfolio:**
- Reference product comparability implications
- Interchangeability pathway effects
- Market entry strategy adjustments

### Process Scope Assessment:
**Manufacturing Processes:**
- Process validation requirements
- Analytical method updates
- Facility compliance modifications

**Quality Systems:**
- QMS (Quality Management System) updates
- Documentation and training requirements
- Audit and inspection preparedness

**Business Processes:**
- Standard Operating Procedure updates
- Cross-functional workflow modifications
- Technology system adaptations

## REMEDIATION LIFECYCLE MANAGEMENT
### Phase 1: Assessment & Planning (0-3 months)
**Gap Analysis:**
- Current state vs. new requirements assessment
- Resource requirement identification
- Timeline and milestone development

**Cross-Functional Team Formation:**
- Regulatory lead assignment
- Subject matter expert identification
- Steering committee establishment

### Phase 2: Implementation & Testing (3-12 months)
**Remediation Activities:**
- Process modifications and validations
- System updates and testing
- Documentation updates and reviews

**Remediation Testing:**
- Analytical method validation
- Process performance qualification
- System integration testing
- User acceptance testing

### Phase 3: Regulatory Submissions (6-18 months)
**Submission Strategy:**
- Prior Approval Supplement (PAS) requirements
- Changes Being Effected (CBE) submissions
- Annual report updates
- International regulatory alignment

**Submission Preparation:**
- CMC section updates
- Clinical data package assembly
- Risk assessment documentation
- Regulatory justification development

### Phase 4: Implementation & Monitoring (12-24 months)
**Go-Live Activities:**
- Change implementation across sites
- Training completion verification
- Process monitoring initiation

**Post-Implementation Monitoring:**
- Effectiveness assessment
- Continuous improvement identification
- Regulatory inspection readiness

## AMGEN BUSINESS IMPACT ASSESSMENT
### Direct Impact on Amgen:
- Core therapeutic area implications (oncology, inflammation, cardiovascular, nephrology, neuroscience)
- Biosimilar business and pipeline effects
- Manufacturing and supply chain considerations
- Financial impact estimation (costs, revenue, timeline)

### Subsidiary and Partnership Impact:
- Joint venture and collaboration effects
- Licensing agreement modifications
- Vendor and supplier requirements

## COMPETITIVE LANDSCAPE ANALYSIS
### Competitor Impact Assessment:
- How developments affect key competitors (Roche, Novartis, Bristol Myers Squibb, Gilead, etc.)
- Competitive advantage/disadvantage analysis
- Market positioning implications

## STRATEGIC RECOMMENDATIONS
### Immediate Actions (0-6 months):
- Critical compliance activities
- Resource allocation and team formation
- Stakeholder communication plan

### Medium-term Strategy (6-18 months):
- Remediation implementation
- Regulatory submission execution
- Market positioning adjustments

### Long-term Vision (18+ months):
- Portfolio strategy optimization
- Innovation pipeline adjustments
- Competitive positioning enhancement

## RISK ASSESSMENT & MITIGATION
### Regulatory Risks:
- Non-compliance penalties and consequences
- Submission delays and rejections
- Inspection findings and remediation

### Business Risks:
- Revenue impact and market share loss
- Competitive disadvantage scenarios
- Resource constraint implications

### Mitigation Strategies:
- Contingency planning
- Risk monitoring indicators
- Escalation procedures

## CONCLUSION & NEXT STEPS
- Strategic priority summary
- Key success metrics and KPIs
- Executive team action items
- Board reporting recommendations

**FORMATTING REQUIREMENTS:**
- Use professional pharmaceutical industry language
- Cite specific sources using [Source X: domain.com] format
- Include specific regulatory timelines and requirements
- Provide actionable recommendations with clear rationale and timelines
- Maintain objective, analytical tone throughout
- Include cost-benefit analysis where applicable

Generate a comprehensive strategic report following this enhanced structure."""
        
        print(f"Generating comprehensive report with {len(expanded_context)} sources...")
        
        model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
        response = model.generate_content(prompt)
        
        report_content = ""
        if hasattr(response, 'text') and response.text:
            report_content = response.text
        elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            report_content = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text'))
        
        if not report_content:
            return jsonify({"error": "Failed to generate report content"}), 500
        
        # Generate PDF
        pdf_buffer = generate_pdf_report(report_content, len(expanded_context), original_article.get('title', 'Strategic Analysis'))
        
        return jsonify({
            "report": report_content,
            "pdf_base64": pdf_buffer,
            "sources_analyzed": len(expanded_context),
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error generating report: {e}")
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500

@app.route('/api/generate-insights', methods=['GET'])
def generate_insights_api():
    """Generate top insights for an article"""
    api_key_for_request = os.environ.get("GOOGLE_API_KEY")
    if not api_key_for_request:
        return jsonify({"error": "Gemini API key not configured."}), 503
    
    article_url = flask_request.args.get('url')
    if not article_url:
        return jsonify({"error": "Missing 'url' query parameter."}), 400
    
    try:
        configure(api_key=api_key_for_request)
        headers = {'User-Agent': 'Mozilla/5.0 (Amgen Scraper - Insights)'}
        content = fetch_article_main_content(article_url, headers)
        
        if content.startswith("Error:") or len(content) < 100:
            return jsonify({"error": "Content issue", "insights": "Unable to generate insights"}), 400
        
        prompt = f"""Analyze the following article and provide the top 3 key insights that would be most relevant for healthcare industry stakeholders. Focus on actionable insights, policy implications, and strategic considerations.

Article Content:
{content[:2000]}

Provide exactly 3 bullet points as insights:"""
        
        model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
        response = model.generate_content(prompt)
        
        insights = response.text.strip() if hasattr(response, 'text') and response.text else "Unable to generate insights"
        return jsonify({"insights": insights})
        
    except Exception as e:
        print(f"Error generating insights: {e}")
        return jsonify({"error": f"Insights generation failed: {str(e)}"}), 500

@app.route('/api/expanded-search', methods=['GET'])
def expanded_search_articles_api():
    article_title = flask_request.args.get('title')
    if not article_title:
        return jsonify({"error": "Missing 'title' query parameter."}), 400
    
    max_results = int(flask_request.args.get('max_results', 5))
    
    print(f"API call: /api/expanded-search for title: {article_title}")
    
    try:
        related_articles = search_related_articles(article_title, max_results)
        return jsonify({
            "query": article_title,
            "results": related_articles,
            "count": len(related_articles)
        })
    except Exception as e:
        print(f"Error in expanded search API: {e}")
        return jsonify({"error": f"Expanded search failed: {str(e)}"}), 500

@app.route('/api/chat-status', methods=['GET'])
def get_chat_status():
    session_id = flask_request.args.get('session_id')
    if not session_id:
        return jsonify({"error": "Missing 'session_id' query parameter."}), 400
    
    with session_lock:
        if session_id not in chat_sessions:
            return jsonify({"error": "Session not found."}), 404
        
        session_data = chat_sessions[session_id]
        update_session_activity(session_id)
        
        response_data = {
            "session_id": session_id,
            "status": session_data["status"],
            "progress_message": session_data.get("progress_message", "")
        }
        
        # If ready, include the final message and questions
        if session_data["status"] == "ready" and "message" in session_data:
            response_data["message"] = session_data["message"]
            response_data["suggested_questions"] = session_data.get("suggested_questions", [])
        
        return jsonify(response_data)

def analyze_sentiment_with_llm(article_content):
    """Analyze sentiment using Gemini LLM"""
    api_key_for_request = os.environ.get("GOOGLE_API_KEY")
    if not api_key_for_request:
        return "Neutral"
    
    try:
        configure(api_key=api_key_for_request)
        
        prompt = f"""You are an expert sentiment analyst. Your task is to determine the overall sentiment of the provided article content and provide a concise justification. The sentiment should be 'positive', 'negative', or 'neutral'.

Analyze the sentiment of the following article content:

Article Content:
{article_content[:2000]}

Return only one word: positive, negative, or neutral"""

        model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
        response = model.generate_content(prompt)
        
        sentiment = response.text.strip().lower()
        if sentiment in ['positive', 'negative', 'neutral']:
            return sentiment.capitalize()
        return "Neutral"
        
    except Exception as e:
        print(f"Error in sentiment analysis: {e}")
        return "Neutral"

def get_impact_text(score):
    """Convert impact score to text description based on comprehensive regulatory analysis"""
    if 0 <= score <= 2:
        return "Low"
    elif 3 <= score <= 4:
        return "Moderate"
    elif 5 <= score <= 6:
        return "Significant"
    elif 7 <= score <= 8:
        return "High"
    elif score == 9:
        return "Very High"
    elif score == 10:
        return "Extremely High"
    else:
        return "Moderate"  # fallback

def load_credible_sources():
    """Load credible sources from config file"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            return config.get('credible_sources', [])
    except:
        return ['fiercepharma.com', 'fiercehealthcare.com', 'fiercebiotech.com', 'kff.org', 'fda.gov', 'economictimes.indiatimes.com']

def extract_date_from_result(result):
    """Extract date from search result (works for both DuckDuckGo and Tavily)"""
    print(f"Extracting date from result: {result.keys()}")
    
    # Try different date fields that might be present
    date_fields = ['published', 'published_date', 'date', 'timestamp']
    for field in date_fields:
        if field in result and result[field]:
            print(f"Found date in field '{field}': {result[field]}")
            return result[field]
    
    # Try to extract date from URL pattern
    url = result.get('href', '') or result.get('url', '')
    print(f"Checking URL for date: {url}")
    
    date_patterns = [
        r'/(\d{4})/(\d{2})/(\d{2})/',  # /2025/01/15/
        r'/(\d{4})-(\d{2})-(\d{2})',   # /2025-01-15
        r'/(\d{4})/(\d{1,2})/',        # /2025/1/
        r'/(\d{4})/(\d{1,2})/(\d{1,2})', # /2025/1/15
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, url)
        if match:
            if len(match.groups()) == 3:
                year, month, day = match.groups()
                extracted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                print(f"Extracted date from URL: {extracted_date}")
                return extracted_date
            elif len(match.groups()) == 2:
                year, month = match.groups()
                extracted_date = f"{year}-{month.zfill(2)}"
                print(f"Extracted partial date from URL: {extracted_date}")
                return extracted_date
    
    # Try to extract from snippet text
    snippet = result.get('body', '') or result.get('content', '') or result.get('snippet', '')
    if snippet:
        print(f"Checking snippet for date: {snippet[:100]}...")
        date_match = re.search(r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),?\s+(\d{4})', snippet)
        if date_match:
            extracted_date = f"{date_match.group(1)} {date_match.group(2)}, {date_match.group(3)}"
            print(f"Extracted date from snippet: {extracted_date}")
            return extracted_date
    
    print("No date found")
    return "Date not available"

def search_with_tavily(article_title, credible_sources, max_results=5):
    """Search using Tavily as backup"""
    try:
        tavily_api_key = os.environ.get("TAVILY_API_KEY")
        print(f"Tavily API key present: {bool(tavily_api_key)}")
        if not tavily_api_key:
            print("No Tavily API key found")
            return []
        
        client = TavilyClient(api_key=tavily_api_key)
        
        # Create search query with site restrictions like DuckDuckGo
        site_query = ' OR '.join([f'site:{source}' for source in credible_sources])
        search_query = f'{article_title} ({site_query})'
        print(f"Tavily search query: {search_query}")
        
        response = client.search(query=search_query, max_results=max_results*2)  # Get more results to filter
        print(f"Tavily returned {len(response.get('results', []))} results")
        
        filtered_results = []
        for result in response.get('results', []):
            url = result.get('url', '')
            print(f"Checking URL: {url}")
            if any(source in url for source in credible_sources):
                print(f"Found credible source: {url}")
                # Extract date from Tavily result
                article_date = extract_date_from_result(result)
                
                filtered_results.append({
                    'title': result.get('title', ''),
                    'url': url,
                    'snippet': result.get('content', ''),
                    'source': next((source for source in credible_sources if source in url), 'unknown'),
                    'date': article_date
                })
        
        print(f"Tavily filtered results: {len(filtered_results)}")
        return filtered_results[:max_results]
        
    except Exception as e:
        print(f"Error in Tavily search: {e}")
        return []

def search_related_articles(article_title, max_results=5):
    """Expanded search combining DuckDuckGo and Tavily results"""
    credible_sources = load_credible_sources()
    combined_results = []
    
    # Search with DuckDuckGo
    try:
        # Try simpler query first
        search_query = f'{article_title} healthcare'
        print(f"DuckDuckGo search query: {search_query}")
        
        time.sleep(2)
        
        with DDGS() as ddgs:
            ddg_results = list(ddgs.text(search_query, max_results=max_results*3, backend='lite'))
        
        print(f"DuckDuckGo returned {len(ddg_results)} results")
        
        # Debug: show first few results
        for i, result in enumerate(ddg_results[:3]):
            print(f"DDG Result {i+1}: {result.get('href', 'No URL')} - {result.get('title', 'No title')[:50]}...")
        
        for result in ddg_results:
            url = result.get('href', '')
            if any(source in url for source in credible_sources):
                article_date = extract_date_from_result(result)
                
                combined_results.append({
                    'title': result.get('title', ''),
                    'url': url,
                    'snippet': result.get('body', ''),
                    'source': next((source for source in credible_sources if source in url), 'unknown'),
                    'date': article_date,
                    'search_tool': 'DuckDuckGo'
                })
        
    except Exception as e:
        print(f"Error in DuckDuckGo search: {e}")
    
    # Search with Tavily
    try:
        tavily_api_key = os.environ.get("TAVILY_API_KEY")
        print(f"Tavily API key available: {bool(tavily_api_key)}")
        if tavily_api_key:
            client = TavilyClient(api_key=tavily_api_key)
            # Try simpler query first
            search_query = f'{article_title} healthcare'
            print(f"Tavily search query: {search_query}")
            
            response = client.search(query=search_query, max_results=max_results*3)
            tavily_results = response.get('results', [])
            print(f"Tavily returned {len(tavily_results)} results")
            
            # Debug: show first few results
            for i, result in enumerate(tavily_results[:3]):
                print(f"Tavily Result {i+1}: {result.get('url', 'No URL')} - {result.get('title', 'No title')[:50]}...")
            
            for result in tavily_results:
                url = result.get('url', '')
                if any(source in url for source in credible_sources):
                    # Check for duplicates
                    if not any(existing['url'] == url for existing in combined_results):
                        article_date = extract_date_from_result(result)
                        
                        combined_results.append({
                            'title': result.get('title', ''),
                            'url': url,
                            'snippet': result.get('content', ''),
                            'source': next((source for source in credible_sources if source in url), 'unknown'),
                            'date': article_date,
                            'search_tool': 'Tavily'
                        })
    
    except Exception as e:
        print(f"Error in Tavily search: {e}")
    
    # Return combined results or fallback
    if combined_results:
        return combined_results[:max_results]
    else:
        return [
            {
                'title': f'Related article about {article_title}',
                'url': 'https://fiercepharma.com/demo-article',
                'snippet': 'Expanded search services temporarily unavailable. Please try again later.',
                'source': 'fiercepharma.com',
                'date': 'Date not available',
                'search_tool': 'Fallback'
            }
        ]

def generate_pdf_report(report_content, sources_count, title):
    """Generate a professionally formatted PDF report"""
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        
        # Define styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            textColor=HexColor('#000048'),
            alignment=1  # Center alignment
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=HexColor('#000048')
        )
        
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=12,
            spaceBefore=15,
            spaceAfter=8,
            textColor=HexColor('#000048')
        )
        
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            leading=12
        )
        
        # Build PDF content
        story = []
        
        # Title page
        story.append(Paragraph("Amgen Strategic Analysis Report", title_style))
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"<b>Report Title:</b> {title}", body_style))
        story.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", body_style))
        story.append(Paragraph(f"<b>Sources Analyzed:</b> {sources_count}", body_style))
        story.append(Spacer(1, 30))
        
        # Process report content
        lines = report_content.split('\n')
        current_section = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                story.append(Spacer(1, 6))
                continue
                
            # Main headings (##)
            if line.startswith('## '):
                story.append(Spacer(1, 15))
                story.append(Paragraph(line[3:], heading_style))
            # Sub headings (###)
            elif line.startswith('### '):
                story.append(Paragraph(line[4:], subheading_style))
            # Bold text (**text**)
            elif line.startswith('**') and line.endswith('**'):
                story.append(Paragraph(f"<b>{line[2:-2]}</b>", body_style))
            # Bullet points
            elif line.startswith('- '):
                story.append(Paragraph(f"• {line[2:]}", body_style))
            # Regular text
            else:
                # Handle bold text within paragraphs
                formatted_line = line.replace('**', '<b>', 1).replace('**', '</b>', 1)
                story.append(Paragraph(formatted_line, body_style))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF data and encode as base64
        pdf_data = buffer.getvalue()
        buffer.close()
        
        import base64
        return base64.b64encode(pdf_data).decode('utf-8')
        
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return None

def analyze_impact_with_llm(article_title, article_url, article_content):
    """Analyze impact score using Gemini LLM"""
    api_key_for_request = os.environ.get("GOOGLE_API_KEY")
    if not api_key_for_request:
        return {"Impact_score": 5, "Impact_score_reason": "Unable to analyze - API key not available", "Impact": "Moderate"}
    
    try:
        configure(api_key=api_key_for_request)
        
        prompt = f"""You are an expert pharmaceutical regulatory and business impact analyst. Evaluate the potential impact of this article on pharmaceutical companies, focusing on regulatory changes, cross-functional implications, scope determination, and remediation requirements. Assign an impact score from 0 to 10.

Article Title: {article_title}
Article Source URL: {article_url}
Article Content:
{article_content[:2000]}

**COMPREHENSIVE IMPACT SCORING CRITERIA (0-10):**

**REGULATORY CHANGE CLASSIFICATION WEIGHT:**
- **Regulation Changes** (FDA/CMS binding requirements): +3-4 points
- **Guidance Changes** (FDA interpretive policies): +2-3 points  
- **Standards Changes** (Quality/technical specs): +1-2 points
- **Policy Changes** (Reimbursement/coverage): +2-3 points
- **Other** (Legislative/court decisions): +1-4 points

**CROSS-FUNCTIONAL IMPACT ASSESSMENT:**
- **Single Function Impact**: +1 point
- **2-3 Functions Affected**: +2 points
- **4-5 Functions Affected**: +3 points
- **Enterprise-wide Impact**: +4 points

**SCOPE DETERMINATION MULTIPLIER:**
- **Process Only**: Base score
- **Single Product Line**: +1 point
- **Multiple Product Lines**: +2 points
- **Entire Portfolio**: +3 points
- **Industry-wide**: +4 points

**REMEDIATION COMPLEXITY FACTOR:**
- **Documentation Updates Only**: +0 points
- **Process Modifications**: +1 point
- **System Changes + Testing**: +2 points
- **Regulatory Submissions Required**: +3 points
- **Multi-year Implementation**: +4 points

**FINAL IMPACT SCORE MAPPING:**

* **0-2 (Low Impact):** 
  - Minor guidance clarifications or administrative updates
  - Single function impact with documentation changes only
  - No regulatory submissions required
  - Minimal business disruption

* **3-4 (Moderate Impact):**
  - Routine policy updates or minor guidance changes
  - 2-3 functions affected with process modifications
  - Single product line scope
  - Standard regulatory submissions (CBE-30, Annual Reports)
  - 6-12 month implementation timeline

* **5-6 (Significant Impact):**
  - Important regulatory changes or new guidance
  - 4-5 functions affected requiring system changes
  - Multiple product lines or therapeutic areas
  - Prior Approval Supplements or new submissions required
  - 12-18 month implementation with testing/validation

* **7-8 (High Impact):**
  - Major regulatory changes with binding requirements
  - Enterprise-wide cross-functional impact
  - Portfolio-wide scope affecting multiple products
  - Complex regulatory submissions with clinical data
  - 18-24 month multi-phase implementation
  - Significant financial and operational implications

* **9 (Very High Impact):**
  - Critical regulatory changes with immediate compliance requirements
  - Industry-wide implications affecting all major players
  - Complete portfolio review and potential restructuring
  - Multiple complex regulatory submissions across regions
  - Multi-year remediation with substantial resource allocation
  - Market access and competitive positioning implications

* **10 (Extremely High Impact):**
  - Transformational regulatory changes reshaping industry
  - All business functions requiring fundamental restructuring
  - Industry-wide scope with potential market disruption
  - Comprehensive regulatory strategy overhaul required
  - Multi-year, multi-billion dollar remediation efforts
  - Potential product withdrawals or market exits
  - AMGEN specifically mentioned or directly targeted

**EVALUATION FRAMEWORK:**
1. Identify the regulatory change type and classification
2. Assess cross-functional impact across all business areas
3. Determine scope (process vs. product, single vs. multiple)
4. Evaluate remediation complexity and timeline requirements
5. Calculate cumulative impact score using the criteria above
6. Provide comprehensive justification covering all four dimensions

Provide your analysis as a JSON object with exactly these fields:
{{
  "Impact_score": <integer from 0 to 10>,
  "Impact_score_reason": "<comprehensive justification covering regulatory change type, cross-functional impact, scope determination, and remediation requirements>",
  "Impact": "<one of: Low, Moderate, Significant, High, Very High, Extremely High>"
}}"""

        model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
        generation_config = {"response_mime_type": "application/json"}
        response = model.generate_content(prompt, generation_config=generation_config)
        
        try:
            result = json.loads(response.text.strip())
            # Validate the response structure
            if "Impact_score" in result and "Impact_score_reason" in result:
                # Ensure score is within valid range
                score = int(result["Impact_score"])
                if 0 <= score <= 10:
                    # Add Impact text if not provided or validate if provided
                    if "Impact" not in result or result["Impact"] not in ["Low", "Moderate", "Significant", "Very High", "Extremely High"]:
                        result["Impact"] = get_impact_text(score)
                    return result
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        
        # Fallback if parsing fails
        return {"Impact_score": 5, "Impact_score_reason": "Unable to parse impact analysis", "Impact": "Moderate"}
        
    except Exception as e:
        print(f"Error in impact analysis: {e}")
        return {"Impact_score": 5, "Impact_score_reason": f"Analysis error: {str(e)}", "Impact": "Moderate"}

if __name__ == '__main__':
    print("Starting Amgen Article Analyzer Flask App...")
    # print(f"Flask version: {flask.__version__}") # Requires: import flask
    # print(f"Requests version: {requests.__version__}")
    # from bs4 import __version__ as bs4_version # To get bs4 version
    # print(f"BeautifulSoup version: {bs4_version}")
    
    # Check if API_KEY is generally available for logging purposes, but routes will check again
    if os.environ.get("GOOGLE_API_KEY"): 
        print("Note: An API_KEY environment variable is present.")
    else: 
        print("WARNING: API_KEY environment variable does NOT seem to be set. Analyze/Summarize will fail if not available to routes.")
    
    print("\nEndpoints: /api/cms-articles, /api/analyze-article?url=<URL>, /api/summarize-article?url=<URL>, /api/chat-with-article, /api/chat-status, /api/expanded-search?title=<TITLE>, /api/generate-insights?url=<URL>, /api/generate-report (POST)")
    app.run(debug=True, port=5001, use_reloader=False)

def analyze_sentiment_with_llm(article_content):
    """Analyze sentiment using Gemini LLM"""
    api_key_for_request = os.environ.get("GOOGLE_API_KEY")
    if not api_key_for_request:
        return "Neutral"
    
    try:
        configure(api_key=api_key_for_request)
        
        prompt = f"""You are an expert sentiment analyst. Your task is to determine the overall sentiment of the provided article content and provide a concise justification. The sentiment should be 'positive', 'negative', or 'neutral'.

Analyze the sentiment of the following article content:

Article Content:
{article_content[:2000]}

Return only one word: positive, negative, or neutral"""

        model = GenerativeModel(model_name="gemini-2.5-flash-preview-04-17")
        response = model.generate_content(prompt)
        
        sentiment = response.text.strip().lower()
        if sentiment in ['positive', 'negative', 'neutral']:
            return sentiment.capitalize()
        return "Neutral"
        
    except Exception as e:
        print(f"Error in sentiment analysis: {e}")
        return "Neutral"