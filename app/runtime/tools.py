import os
import re
import urllib.parse
import httpx

# Ensure a secure directory inside workspace for files created/read by agents
STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "workspace_storage")
os.makedirs(STORAGE_DIR, exist_ok=True)

# Pre-populate a mock system status and knowledge base file inside workspace_storage
KNOWLEDGE_BASE_PATH = os.path.join(STORAGE_DIR, "knowledge_base.txt")
if not os.path.exists(KNOWLEDGE_BASE_PATH):
    with open(KNOWLEDGE_BASE_PATH, "w", encoding="utf-8") as f:
        f.write("""=============================================================
AETHER ORCHESTRATION PLATFORM - TECHNICAL KNOWLEDGE BASE
=============================================================

SYSTEM CONFIGURATION:
- Service Port: 8000
- Server Bind Address: 127.0.0.1
- Database Engine: SQLite 3
- Real-time Pipeline: WebSockets (active on /ws/monitor)

KNOWN ISSUES & RESOLUTIONS:
1. Error Code: ERR_CONN_REFUSED
   - Description: The FastAPI server is not reachable on Port 8000.
   - Fix: Ensure 'python run.py' was executed and check if another process is utilizing port 8000. Use netstat to check.
   
2. Error Code: ERR_TELEGRAM_INVALID_TOKEN
   - Description: The Telegram Bot fails to connect.
   - Fix: Verify that your TELEGRAM_BOT_TOKEN environment variable in the .env file is correct and not revoked by @BotFather.

3. Workflow Loop Exceeded
   - Description: Workflow runs into an infinite feedback loop between Writer and Critic.
   - Fix: Modify the Critic agent's prompt to be more lenient or adjust the Critic's approval conditions in the workflow edges.

BILLING INFORMATION & RULES:
- Standard Plan: $29/month, includes 5 concurrent agents, 50,000 runs/month.
- Enterprise Plan: $199/month, unlimited agents, priority queue execution, dedicated webhook support.
- API Key Overrides: Customers must provide their own Gemini or OpenAI API keys to enable custom LLMs.
""")

def search_web(query: str) -> str:
    """
    Search the web for a given query.
    Attempts to scrape real search results from Wikipedia API or DuckDuckGo.
    Falls back to intelligent local keyword search if offline or error occurs.
    """
    print(f"[Tool: search_web] Querying: '{query}'")
    try:
        # 1. Attempt Wikipedia search API
        encoded_query = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&format=json&utf8="
        
        response = httpx.get(url, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            search_results = data.get("query", {}).get("search", [])
            if search_results:
                formatted_results = []
                for idx, result in enumerate(search_results[:3]):
                    title = result.get("title")
                    snippet = re.sub(r'<[^>]*>', '', result.get("snippet", "")) # Clean HTML tags
                    page_id = result.get("pageid")
                    formatted_results.append(f"[{idx+1}] Title: {title}\nSnippet: {snippet}\nURL: https://en.wikipedia.org/?curid={page_id}")
                return "\n\n".join(formatted_results)
    except Exception as e:
        print(f"[Tool: search_web] Real web search failed/offline: {e}. Using fallback retriever.")
    
    # 2. Hybrid mock search database for offline robustness
    knowledge_index = {
        "price": "Standard Subscription is $29/mo (5 agents, 50k runs). Enterprise is $199/mo (unlimited agents, priority support). Overages are charged at $0.002 per agent message.",
        "billing": "Billing issues are routed to the billing team or the Support Supervisor. We support Stripe, PayPal, and bank transfers.",
        "port": "FastAPI is bound to port 8000 by default (127.0.0.1). You can change this in the .env file under the PORT variable.",
        "telegram": "Telegram integration requires setting the TELEGRAM_BOT_TOKEN in .env. The bot uses async long polling so no webhooks/ngrok is needed.",
        "workflow": "Workflows consist of nodes (Agents) and edges (Conditions). Edges can evaluate field conditions such as 'last_response contains TECHNICAL'.",
        "loop": "If agents get stuck in loops, adjust their system prompt or loosen the validation criteria in the workflow editor."
    }
    
    # Clean and match keywords
    query_lower = query.lower()
    matches = []
    for key, value in knowledge_index.items():
        if key in query_lower:
            matches.append(f"[Mock Source: {key.capitalize()}] {value}")
            
    if matches:
        return "\n\n".join(matches)
    
    return f"[Web Search Result] Searched for '{query}'. Found no matching direct answers. The topic relates to standard AI orchestrations. (Offline simulated lookup complete)."

def fetch_url(url: str) -> str:
    """
    Downloads and fetches text from a web page.
    """
    print(f"[Tool: fetch_url] Fetching: {url}")
    try:
        response = httpx.get(url, timeout=5.0, headers={"User-Agent": "AetherBot/1.0"})
        if response.status_code == 200:
            text = response.text
            # Simple HTML text extraction (remove script, style, tags)
            text = re.sub(r'<script.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]*>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:1500] + "..." if len(text) > 1500 else text
    except Exception as e:
        return f"[Error: fetch_url] Failed to fetch URL {url}: {e}"
        
    return f"[Error: fetch_url] Failed with status code: {response.status_code if 'response' in locals() else 'Unknown'}"

def calculator(expression: str) -> str:
    """
    Safely evaluates a mathematical expression using mathematical characters only.
    """
    print(f"[Tool: calculator] Evaluating: {expression}")
    # Sanitize the expression to allow only numbers, basic operators, spaces, parentheses
    sanitized = re.sub(r'[^0-9+\-*/().\s]', '', expression)
    try:
        if not sanitized.strip():
            return "Error: Empty expression or invalid characters."
        # Use eval safely since we stripped all letters, symbols and command injectors
        result = eval(sanitized, {"__builtins__": None}, {})
        return str(result)
    except Exception as e:
        return f"Error: Failed to evaluate mathematical expression '{expression}': {e}"

def write_file(filename: str, content: str) -> str:
    """
    Writes data content to a file inside the secure workspace_storage folder.
    """
    # Sanitize filename to prevent directory traversal
    clean_name = os.path.basename(filename)
    dest_path = os.path.join(STORAGE_DIR, clean_name)
    print(f"[Tool: write_file] Writing to: {dest_path}")
    try:
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: Content written to file '{clean_name}' successfully."
    except Exception as e:
        return f"Error: Failed to write to file '{clean_name}': {e}"

def read_file(filename: str) -> str:
    """
    Reads data content from a file inside the secure workspace_storage folder.
    """
    # Sanitize filename
    clean_name = os.path.basename(filename)
    source_path = os.path.join(STORAGE_DIR, clean_name)
    print(f"[Tool: read_file] Reading from: {source_path}")
    try:
        if not os.path.exists(source_path):
            return f"Error: File '{clean_name}' does not exist inside workspace storage."
        with open(source_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: Failed to read file '{clean_name}': {e}"

# Mapping of tools
TOOL_MAPPING = {
    "search_web": search_web,
    "fetch_url": fetch_url,
    "calculator": calculator,
    "write_file": write_file,
    "read_file": read_file
}

def execute_tool(tool_name: str, argument: str) -> str:
    """
    Helper function to dispatch and run tools by name.
    """
    if tool_name not in TOOL_MAPPING:
        return f"Error: Tool '{tool_name}' is not supported or available on this platform."
    try:
        return TOOL_MAPPING[tool_name](argument)
    except Exception as e:
        return f"Error: Failed to execute tool '{tool_name}': {e}"
