# ========================================================================
# B.Y PRO Marketing Agent - Render Server
# Owner messages → Dashboard Executive Assistant
# v3: Stable long conversations + Messenger-friendly formatting
# ========================================================================
import sys
sys.stdout.reconfigure(line_buffering=True)

import os
import re
import json
import requests
import time
import threading
from flask import Flask, request, jsonify
from datetime import datetime, timezone
from collections import deque
from pymongo import MongoClient

app = Flask(__name__)

# ========================================================================
# 0. CORS
# ========================================================================
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.route('/api/<path:_any>', methods=['OPTIONS'])
@app.route('/<path:_any>', methods=['OPTIONS'])
def cors_preflight(_any=None):
    return '', 204

# ========================================================================
# 1. تحميل الأسرار من GitHub
# ========================================================================
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO  = os.environ.get('GITHUB_REPO', 'Yacine2007/APIs-B.YPRO-Managment')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

SECRET_FILES = [
    'Marketer/FACEBOOK_PAGE_TOKEN.env',
    'Marketer/User_Token.env',
    'AI/key.env',
    'DB/mongodb_params.env',
]

def load_secrets_from_github():
    print("🔐 [STARTUP] تحميل الأسرار من GitHub...", flush=True)
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN غير موجود", flush=True)
        return
    headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github.raw'}
    for path in SECRET_FILES:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        try:
            r = requests.get(url, headers=headers, params={'ref': GITHUB_BRANCH}, timeout=15)
            if r.status_code != 200:
                print(f"⚠️ فشل {path}: {r.status_code}", flush=True)
                continue
            for line in r.text.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v:
                    os.environ[k] = v
            print(f"✅ تم: {path}", flush=True)
        except Exception as e:
            print(f"❌ {path}: {e}", flush=True)

load_secrets_from_github()

# ========================================================================
# 2. المفاتيح
# ========================================================================
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN      = os.environ.get('VERIFY_TOKEN', 'bypro_verify_2026')
OWNER_FB_ID       = os.environ.get('OWNER_FB_ID', '25923199944038952')
PAGE_ID           = os.environ.get('PAGE_ID', '923170140890240')
PAGE_NAME         = os.environ.get('PAGE_NAME', 'B.Y PRO Marketing Agent')

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_MODEL   = os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')
OPENROUTER_URL     = 'https://openrouter.ai/api/v1/chat/completions'

MONGODB_URI        = os.environ.get('MONGODB_URI')
ORDERS_DB_NAME     = os.environ.get('ORDERS_DB_NAME', 'bypro_orders')
ORDERS_COLLECTION  = 'orders'
SETTINGS_DB_NAME   = os.environ.get('SETTINGS_DB_NAME', 'DashboardDB')
SETTINGS_COLLECTION = 'settings'
SETTINGS_KEY       = 'service_settings'

# Dashboard shared collections
DASHBOARD_DB_NAME     = 'DashboardDB'
CHAT_COLLECTION       = 'chat_history'
CLIENTS_COLLECTION    = 'clients'
PROJECTS_COLLECTION   = 'projects_registry'
DASH_SETTINGS_COLL    = 'settings'

SELF_URL = os.environ.get('SELF_URL', 'https://by-pro-marketing-agent-v2jk.onrender.com')

# ========================================================================
# 3. MongoDB
# ========================================================================
_mongo_client = None
_orders_col = None
_settings_col = None

def get_mongo():
    global _mongo_client, _orders_col, _settings_col
    if _orders_col is not None:
        return _orders_col, _settings_col
    if not MONGODB_URI:
        print("❌ MONGODB_URI غير موجود", flush=True)
        return None, None
    try:
        _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=15000, tlsAllowInvalidCertificates=True)
        _mongo_client.admin.command('ping')
        _orders_col = _mongo_client[ORDERS_DB_NAME][ORDERS_COLLECTION]
        _settings_col = _mongo_client[SETTINGS_DB_NAME][SETTINGS_COLLECTION]
        print("✅ MongoDB متصل", flush=True)
        return _orders_col, _settings_col
    except Exception as e:
        print(f"❌ MongoDB: {e}", flush=True)
        return None, None

def _ensure_mongo():
    global _mongo_client
    if _mongo_client is None:
        get_mongo()
    return _mongo_client

# ========================================================================
# 4. التخزين المؤقت
# ========================================================================
_cache = {
    'sessions': {},
    'stats': {'msgs_received': 0, 'msgs_sent': 0, 'start_time': datetime.now().isoformat()},
    'categories': None,
    'owner_id': None,
}
logs = deque(maxlen=200)

def add_log(msg):
    entry = {'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg}
    logs.appendleft(entry)
    print(f"[{entry['time']}] {msg}", flush=True)

# ========================================================================
# 5. التصنيفات (للعملاء فقط)
# ========================================================================
DEFAULT_CATEGORIES = [
    {"id": "design", "enabled": True, "name": "التصميم البصري", "icon": "fa-solid fa-palette", "services": ["شعارات","هوية بصرية","تعديل صور","سوشيال ميديا","بطاقات","منشورات","أغلفة"]},
    {"id": "web", "enabled": True, "name": "مواقع الويب", "icon": "fa-solid fa-globe", "services": ["صفحة هبوط","متجر إلكتروني","موقع ثابت","موقع ديناميكي","مدونة","لوحة تحكم"]},
    {"id": "apps", "enabled": True, "name": "التطبيقات", "icon": "fa-solid fa-mobile-screen", "services": ["أندرويد","iOS","ويب App","Flutter","React Native"]},
    {"id": "desktop", "enabled": True, "name": "ديسكتوب", "icon": "fa-solid fa-desktop", "services": ["ويندوز","ماك","لينكس","إدارة","POS"]},
    {"id": "systems", "enabled": True, "name": "الأنظمة", "icon": "fa-solid fa-gears", "services": ["CMS","سكربت مخصص","بايثون ولغات أخرى","ERP","CRM","فوترة","حجوزات","بوتات","أتمتة"]},
    {"id": "editing", "enabled": True, "name": "المونتاج", "icon": "fa-solid fa-film", "services": ["مونتاج فيديو","تعليق صوتي","موشن جرافيك","إعلانات","يوتيوب","ريلز","AI فيديو"]},
    {"id": "security", "enabled": True, "name": "الأمن السيبراني", "icon": "fa-solid fa-shield-halved", "services": ["اختبار اختراق","حماية مواقع","تحليل ثغرات","استشارات","تدقيق","تقارير"]},
    {"id": "marketing", "enabled": True, "name": "تسويق", "icon": "fa-solid fa-chart-line", "services": ["تسويق رقمي","إعلانات","SEO","محتوى","حملات","سوشيال ميديا"]},
    {"id": "other", "enabled": True, "name": "أخرى", "icon": "fa-solid fa-box", "services": ["خدمة مخصصة"]},
]

def load_categories():
    _, settings_col = get_mongo()
    if settings_col is None:
        return None
    try:
        doc = settings_col.find_one({'key': SETTINGS_KEY})
        if doc and doc.get('value') and doc['value'].get('categories'):
            cats = doc['value']['categories']
            _cache['categories'] = cats
            add_log(f"✅ تم تحميل {len(cats)} تصنيف من MongoDB")
            return cats
    except Exception as e:
        add_log(f"❌ فشل تحميل التصنيفات: {e}")
    return None

def get_categories():
    if _cache['categories'] is None:
        load_categories()
    if _cache['categories'] is None:
        _cache['categories'] = DEFAULT_CATEGORIES
    return _cache['categories']

def format_categories_for_ai():
    cats = get_categories()
    lines = []
    for c in cats:
        if not c.get('enabled', True):
            continue
        cat_id = c.get('id', '')
        name = c.get('name', cat_id)
        services = c.get('services', [])
        svc_labels = []
        for s in services:
            if isinstance(s, dict):
                if s.get('enabled', True):
                    lbl = s.get('label_ar') or s.get('label_en') or s.get('id', '')
                    svc_labels.append(lbl)
            elif isinstance(s, str):
                svc_labels.append(s)
        lines.append(f"[{cat_id}] {name}: {', '.join(svc_labels)}")
    return "\n".join(lines)

def find_category(cat_id):
    for c in get_categories():
        if c.get('id') == cat_id:
            return c
    return None

# ========================================================================
# 6. المدير
# ========================================================================
def get_owner_id():
    if _cache['owner_id']:
        return _cache['owner_id']
    if OWNER_FB_ID:
        _cache['owner_id'] = str(OWNER_FB_ID)
        return _cache['owner_id']
    return None

# ========================================================================
# 7. OpenRouter AI
# ========================================================================
def get_ai_response(prompt):
    if not OPENROUTER_API_KEY:
        add_log("❌ OPENROUTER_API_KEY غير موجود")
        return None
    try:
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
            'HTTP-Referer': SELF_URL,
            'X-Title': 'B.Y PRO Marketing Agent',
        }
        payload = {
            'model': OPENROUTER_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'max_tokens': 2048,
        }
        r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        if r.status_code == 200:
            result = r.json()
            answer = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            if answer and answer.strip():
                return answer.strip()
            return None
        add_log(f"❌ AI HTTP {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        add_log(f"❌ AI: {e}")
        return None

def call_ai_with_messages(messages, max_tokens=2500, retries=2):
    """Call OpenRouter with automatic retry on transient failures."""
    if not OPENROUTER_API_KEY:
        add_log("❌ OPENROUTER_API_KEY غير موجود")
        return None, "AI key missing"

    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': SELF_URL,
        'X-Title': 'B.Y PRO Executive Assistant',
    }
    payload = {
        'model': OPENROUTER_MODEL,
        'messages': messages,
        'temperature': 0.7,
        'max_tokens': max_tokens,
    }

    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)

            if r.status_code == 200:
                result = r.json()
                choices = result.get('choices') or []
                if not choices:
                    last_err = "empty choices"
                    time.sleep(1.5)
                    continue
                answer = choices[0].get('message', {}).get('content', '')
                if answer and answer.strip():
                    return answer.strip(), None
                last_err = "empty content"
                time.sleep(1.5)
                continue

            # Client errors (bad request, context too long) — do not retry with same payload
            if r.status_code in (400, 413, 422):
                err_body = r.text[:300]
                add_log(f"❌ AI client error {r.status_code}: {err_body}")
                return None, f"HTTP {r.status_code}: {err_body}"

            # Auth errors — do not retry
            if r.status_code in (401, 403):
                add_log(f"❌ AI auth error {r.status_code}")
                return None, f"HTTP {r.status_code}"

            # Rate limit or server error — retry with backoff
            last_err = f"HTTP {r.status_code}: {r.text[:150]}"
            add_log(f"⚠️ AI transient {r.status_code} (attempt {attempt+1}/{retries+1})")
            time.sleep(2 * (attempt + 1))
            continue

        except requests.exceptions.Timeout:
            last_err = "timeout"
            add_log(f"⚠️ AI timeout (attempt {attempt+1}/{retries+1})")
            time.sleep(2 * (attempt + 1))
            continue
        except Exception as e:
            last_err = str(e)
            add_log(f"⚠️ AI exception: {e}")
            time.sleep(2 * (attempt + 1))
            continue

    return None, last_err or "AI call failed after retries"

# ========================================================================
# 7b. Executive Assistant Bridge
# ========================================================================
def get_dashboard_settings():
    client = _ensure_mongo()
    if client is None:
        return {}
    out = {}
    try:
        col = client[DASHBOARD_DB_NAME][DASH_SETTINGS_COLL]
        for doc in col.find({}):
            k = doc.get('key')
            if k:
                out[k] = doc.get('value')
    except Exception as e:
        add_log(f"⚠️ settings load: {e}")
    return out

def get_chat_history():
    client = _ensure_mongo()
    if client is None:
        return []
    try:
        col = client[DASHBOARD_DB_NAME][CHAT_COLLECTION]
        out = []
        for d in col.find({}).sort('_id', 1):
            out.append({
                'role': d.get('role'),
                'content': d.get('content', ''),
                'meta': d.get('meta') or {},
            })
        return out
    except Exception as e:
        add_log(f"⚠️ chat load: {e}")
        return []

def get_conversation_history():
    """
    Return ONLY the meaningful user/assistant dialogue — exclude auto alerts,
    welcome greetings, and system notifications that pollute the context.
    """
    raw = get_chat_history()
    clean = []
    for m in raw:
        meta = m.get('meta') or {}
        # Skip automatic/system messages entirely
        if meta.get('auto') or meta.get('welcome') or meta.get('alert'):
            continue
        role = m.get('role')
        if role not in ('user', 'assistant'):
            continue
        content = (m.get('content') or '').strip()
        if not content:
            continue
        clean.append({'role': role, 'content': content})
    return clean

def save_chat_message(role, content, meta=None):
    client = _ensure_mongo()
    if client is None:
        return False
    try:
        col = client[DASHBOARD_DB_NAME][CHAT_COLLECTION]
        doc = {
            'role': role,
            'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        if meta:
            doc['meta'] = meta
        col.insert_one(doc)
        return True
    except Exception as e:
        add_log(f"⚠️ chat save: {e}")
        return False

def get_clients_for_ai(limit=80):
    client = _ensure_mongo()
    if client is None:
        return []
    try:
        col = client[DASHBOARD_DB_NAME][CLIENTS_COLLECTION]
        out = []
        for d in col.find({}).sort('_id', -1).limit(limit):
            order = d.get('order') or {}
            out.append({
                'name': d.get('name', ''),
                'email': d.get('email', ''),
                'phone': d.get('phone', ''),
                'source': d.get('source', ''),
                'status': d.get('status', ''),
                'service': order.get('service', ''),
                'project': order.get('project_name', '') or d.get('project_name', ''),
            })
        return out
    except Exception as e:
        add_log(f"⚠️ clients load: {e}")
        return []

def get_pending_orders_for_ai(limit=30):
    col, _ = get_mongo()
    if col is None:
        return []
    try:
        query = {'$or': [
            {'status': 'new'},
            {'status': {'$exists': False}},
            {'status': None},
            {'status': 'pending'},
        ]}
        out = []
        for d in col.find(query).sort([('createdAt', -1), ('_id', -1)]).limit(limit):
            out.append({
                'name': d.get('fullName') or d.get('name', ''),
                'phone': d.get('phone', ''),
                'service': d.get('service', ''),
                'project': d.get('projectName', ''),
            })
        return out
    except Exception as e:
        add_log(f"⚠️ orders load: {e}")
        return []

def get_company_summary():
    client = _ensure_mongo()
    if client is None:
        return ''
    try:
        db = client[DASHBOARD_DB_NAME]
        col = db[PROJECTS_COLLECTION]
        clients_count = db[CLIENTS_COLLECTION].count_documents({})
        projects_count = col.count_documents({'kind': 'project'})
        completed = col.count_documents({'kind': 'project', 'progress': {'$gte': 100}})
        return (
            "=== Company Summary ===\n"
            f"Customers: {clients_count}\n"
            f"Projects: {projects_count}\n"
            f"Completed: {completed}\n"
        )
    except Exception as e:
        add_log(f"⚠️ summary: {e}")
        return ''

DEFAULT_SYSTEM_PROMPT_FALLBACK = (
    'You are the executive assistant managing B.Y PRO Technologie, a multinational digital software company. '
    'Your director is Yacine, the founder and owner of B.Y PRO. '
    'Address him ONLY as "Sir" or "Director Yacine". '
    'Speak professionally and formally, in the language he uses. '
    'You have full read access to the business data: clients, pending orders, projects, transactions, service settings, and system health. '
    'You can answer questions about any client, help him search for them by name, email, phone, project, service, or source, and report on pending orders. '
    'You always know the current date and time. '
    'Company details: Technology, Software Services, Development & AI. '
    'Website: https://by-pro.kesug.com/ (backup: http://bypro.great-site.net/).'
)

# Instructions added ONLY for Messenger delivery
MESSENGER_FORMAT_RULE = (
    "\n\n=== MESSENGER FORMAT RULES (CRITICAL) ===\n"
    "Your reply will be delivered through Facebook Messenger, which does NOT render Markdown.\n"
    "STRICT RULES:\n"
    "1) NEVER use Markdown tables (no | ... | ... |). Instead, list items as bullet lines.\n"
    "2) NEVER use triple backticks (```). Use plain text or simple indentation.\n"
    "3) NEVER use # headers. Use a plain uppercase label on its own line if needed.\n"
    "4) For lists, use one of: • , -, or 1. 2. 3.\n"
    "5) For each item with fields, use this pattern:\n"
    "   • Name: Ahmad\n"
    "     Phone: 0555...\n"
    "     Service: Website\n"
    "   • Name: Sara\n"
    "     Phone: 0666...\n"
    "     Service: Logo\n"
    "6) Keep replies focused. If a list has many entries, show the first 5-10 and offer to show more.\n"
    "7) Bold and italic markers (** **) do not render — do not use them.\n"
)

def sanitize_for_messenger(text):
    """
    Convert any Markdown leftovers into Messenger-friendly plain text.
    Handles: tables, code fences, headers, bold/italic markers.
    """
    if not text:
        return text

    # 1. Strip code fences (keep inner content)
    text = re.sub(r'```[a-zA-Z0-9_+\-]*\n?', '', text)
    text = text.replace('```', '')

    # 2. Convert Markdown tables into bullet lists
    lines = text.split('\n')
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect table header + separator
        if ('|' in line) and (i + 1 < len(lines)) and re.match(r'^\s*\|?[\s\-:|]+\|?\s*$', lines[i + 1]):
            header_line = line
            i += 2  # skip header + separator
            body = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                body.append(lines[i])
                i += 1

            headers = [c.strip() for c in header_line.strip().strip('|').split('|')]

            if headers:
                out.append('')
                for row in body:
                    cells = [c.strip() for c in row.strip().strip('|').split('|')]
                    # First field as bullet, rest as indented key: value
                    first_written = False
                    for idx, (h, c) in enumerate(zip(headers, cells)):
                        if not c:
                            continue
                        if not first_written:
                            out.append(f"• {h}: {c}")
                            first_written = True
                        else:
                            out.append(f"     {h}: {c}")
                    if first_written:
                        out.append('')
                # Remove trailing extra blank line if any
                if out and out[-1] == '':
                    out.pop()
                out.append('')
            continue

        out.append(line)
        i += 1

    text = '\n'.join(out)

    # 3. Convert headers to plain uppercase
    def _hdr(m):
        return m.group(1).strip().upper()
    text = re.sub(r'^#{1,6}\s*(.+)$', _hdr, text, flags=re.MULTILINE)

    # 4. Remove bold / italic markers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)', r'\1', text)

    # 5. Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()

def build_executive_context(clients_limit=80, orders_limit=30):
    settings = get_dashboard_settings()
    now = datetime.now()
    weekday = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][now.weekday()]

    clients = get_clients_for_ai(clients_limit)
    pending = get_pending_orders_for_ai(orders_limit)
    summary = get_company_summary()

    company_info = {
        'website': settings.get('company_website', ''),
        'tagline': settings.get('company_tagline', ''),
    }

    return (
        "=== CURRENT DATE & TIME ===\n"
        f"Today is {weekday}, {now.strftime('%Y-%m-%d')} — local time {now.strftime('%H:%M:%S')}.\n\n"
        "=== LIVE BUSINESS CONTEXT ===\n"
        f"Clients count: {len(clients)}\n"
        f"Pending orders count: {len(pending)}\n\n"
        f"Clients list (most recent {len(clients)}):\n{json.dumps(clients, ensure_ascii=False)}\n\n"
        f"Pending orders:\n{json.dumps(pending, ensure_ascii=False)}\n\n"
        f"Company summary:\n{summary}\n\n"
        f"Company info:\n{json.dumps(company_info, ensure_ascii=False)}\n"
    )

def ask_executive_assistant(user_msg, attempt=1):
    """
    Route owner's message through the Executive Assistant with retry +
    progressive context reduction so long conversations never break.
    """
    MAX_ATTEMPTS = 3

    # Progressive downsizing on retry
    if attempt == 1:
        clients_limit, orders_limit, history_limit, max_tokens = 80, 30, 20, 2000
    elif attempt == 2:
        clients_limit, orders_limit, history_limit, max_tokens = 30, 15, 10, 1500
    else:
        clients_limit, orders_limit, history_limit, max_tokens = 10, 5, 6, 1200

    settings = get_dashboard_settings()
    system_prompt = (settings.get('system_prompt') or '').strip() or DEFAULT_SYSTEM_PROMPT_FALLBACK
    system_context = build_executive_context(clients_limit, orders_limit)

    # Save user message once, on first attempt
    if attempt == 1:
        save_chat_message('user', user_msg, meta={'source': 'messenger'})

    # Clean conversation (no auto alerts)
    history = get_conversation_history()
    # Exclude current user message (already appended)
    if history and history[-1]['role'] == 'user' and history[-1]['content'].strip() == user_msg.strip():
        history = history[:-1]

    if len(history) > history_limit:
        history = history[-history_limit:]

    system_block = system_prompt + "\n\n" + system_context + MESSENGER_FORMAT_RULE
    messages = [{'role': 'system', 'content': system_block}]
    for m in history:
        messages.append({'role': m['role'], 'content': m['content']})

    total_chars = sum(len(m.get('content', '')) for m in messages)
    add_log(f"📏 [EA] attempt={attempt} size={total_chars} chars, msgs={len(messages)}")

    reply, err = call_ai_with_messages(messages, max_tokens=max_tokens)

    if reply is None:
        add_log(f"❌ [EA] attempt {attempt} failed: {err}")
        if attempt < MAX_ATTEMPTS:
            time.sleep(1.5)
            return ask_executive_assistant(user_msg, attempt=attempt + 1)
        return None

    # Convert any leftover Markdown to Messenger-friendly text
    reply = sanitize_for_messenger(reply)

    save_chat_message('assistant', reply, meta={'source': 'messenger'})
    return reply

# ========================================================================
# 8. شخصيات العملاء
# ========================================================================
def get_bot_personality():
    cats_text = format_categories_for_ai()
    return f"""أنت وكيل تسويق لخدمة العملاء في شركة B.Y PRO للتكنولوجيا والبرمجيات.

شخصيتك:
- تتحدث كإنسان حقيقي، ودود ومريح، وليس كبوت.
- مختصر ومباشر، لا تطوّل بدون داعٍ.
- تفهم احتياج العميل قبل أي شيء.
- أجب بنفس لغة العميل (عربي، إنجليزي، فرنسي).

الخدمات المتاحة (استخدم الـ ID بين الأقواس):
{cats_text}

طريقة عملك:
1. رحّب واسأل كيف يمكنك المساعدة.
2. إذا سأل عن الخدمات، اعرض القائمة.
3. افهم تفاصيل المشروع (اسأل 1-2 سؤال في كل مرة).
4. اسأل إذا كان لديه نموذج/تصميم جاهز.
5. قدّم السعر التقريبي والمدة بوضوح.
6. إذا وافق، اطلب بياناته.

الأسعار التقريبية (بالدولار):
- صفحة هبوط: 1500$-4000$ | موقع: 4000$-12000$ | متجر: 3500$-15000$
- تطبيق بسيط: 5000$-20000$ | تطبيق معقد: 25000$-60000$
- بوت AI: 300$-2000$ | شعار: 150$-500$ | هوية: 800$-3000$
- ريلز: 30$-100$ | فيديو: 150$-500$ | موشن: 500$-1500$
- ERP/CRM: 8000$-40000$ | سكربت: 500$-3000$
التحويل: 1$ = 240 دج.

⚠️ أضف في نهاية كل رد سطرين منفصلين:
[CATEGORY:id]
[SERVICE:اسم_الخدمة]"""

DATA_COLLECTION_PERSONALITY = """أنت وكيل تسويق في B.Y PRO.
مهمتك: جمع بيانات العميل فقط.
قواعد: قصير جداً، سؤال واحد، لا أسعار، لا خدمات، لا تحيات مكررة."""

def parse_ai_tags(text):
    cat = re.search(r'\[CATEGORY:([a-zA-Z0-9_\-]+)\]', text)
    svc = re.search(r'\[SERVICE:([^\]]+)\]', text)
    clean = re.sub(r'\[CATEGORY:[^\]]+\]', '', text)
    clean = re.sub(r'\[SERVICE:[^\]]+\]', '', clean)
    return clean.strip(), (cat.group(1) if cat else None), (svc.group(1).strip() if svc else None)

def ask_ai(user_msg, sess, extra_instruction="", personality=None):
    context = "\n".join(sess.get('conversation', [])[-14:])
    stage = sess.get('stage', 'welcome')
    hints = {
        'welcome': "رحّب بالعميل واسأل كيف يمكنك مساعدته.",
        'explore': "افهم ما يريد. اسأل 1-2 سؤال.",
        'details': "اطلب تفاصيل المشروع.",
        'model': "اسأل إذا كان لديه نموذج جاهز.",
        'price': "قدّم السعر والمدة.",
    }
    p = personality or get_bot_personality()
    hint = hints.get(stage, "")
    full = f"""{p}

[المرحلة: {stage}]
[توجيه: {hint}]
{extra_instruction}

سجل المحادثة:
{context}

العميل: {user_msg}
الوكيل:"""
    res = get_ai_response(full)
    if res:
        return res[:2500]
    return "عذراً، حدث خطأ تقني. أعد رسالتك من فضلك."

# ========================================================================
# 9. فيسبوك
# ========================================================================
def send_fb(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        add_log("❌ PAGE_ACCESS_TOKEN مفقود")
        return False
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {'recipient': {'id': recipient_id}, 'message': {'text': text}, 'messaging_type': 'RESPONSE'}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            _cache['stats']['msgs_sent'] += 1
            add_log(f"📤 {str(recipient_id)[:12]}: {text[:60]}")
            return True
        add_log(f"❌ فشل الإرسال: {r.status_code} - {r.text[:150]}")
        return False
    except Exception as e:
        add_log(f"❌ إرسال: {e}")
        return False

def send_fb_long(recipient_id, text, max_len=1800):
    """Split long replies to respect Messenger's limit."""
    if text is None:
        return False
    text = str(text)
    if len(text) <= max_len:
        return send_fb(recipient_id, text)

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        split_at = remaining.rfind('\n', 0, max_len)
        if split_at < max_len // 2:
            split_at = remaining.rfind(' ', 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()

    ok = True
    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(0.4)
        if not send_fb(recipient_id, chunk):
            ok = False
    return ok

# ========================================================================
# 10. الجلسات
# ========================================================================
def new_session():
    return {
        'name': '', 'service': '', 'category': '', 'categoryName': '', 'categoryIcon': '',
        'projectName': '', 'projectDetails': '', 'hasModel': None,
        'budget': 0, 'duration': '',
        'phone': '', 'email': '', 'social': [],
        'stage': 'welcome', 'conversation': [],
    }

def get_session(sender_id):
    sid = str(sender_id)
    if sid not in _cache['sessions']:
        print(f"🆕 [SESSION] {sid}", flush=True)
        _cache['sessions'][sid] = new_session()
    return _cache['sessions'][sid]

def add_conv(sender_id, role, message):
    sess = get_session(sender_id)
    sess['conversation'].append(f"{role}: {message}")
    if len(sess['conversation']) > 20:
        sess['conversation'] = sess['conversation'][-20:]

# ========================================================================
# 11. الاستخراج
# ========================================================================
def extract_phone(text):
    for pat in [r'(\+213[567][0-9]{8})', r'(0[567][0-9]{8})', r'(\+[1-9][0-9]{7,14})', r'([0-9]{10,13})']:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None

def extract_email(text):
    m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return m.group(0) if m else None

def extract_name(text):
    t = text.strip()
    t = re.sub(r'^(مرحبا|أهلا|السلام عليكم|hi|hello)\s*', '', t, flags=re.I)
    patterns = [
        r'اسمي\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
        r'الاسم\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
        r'انا\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
        r'أنا\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
        r'my name is\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
        r"i'm\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.I)
        if m:
            name = m.group(1).strip()
            name = re.sub(r'\s+(و|ثم|بعدها)$', '', name)
            if 1 <= len(name.split()) <= 4 and 2 <= len(name) <= 40:
                return name
    words = t.split()
    if 1 <= len(words) <= 3 and len(t) <= 30:
        if not any(w in t.lower() for w in ['نعم', 'لا', 'كيف', 'متى', 'ماذا', 'شكرا', 'مرحبا', 'اهلا', 'السلام']):
            return t
    return None

def is_confirmation(text):
    words = ['نعم', 'موافق', 'تمام', 'اوكي', 'اوك', 'ok', 'yes', 'موافقة', 'ماشي', 'اتفقنا', 'ممتاز', 'أوافق', 'نبدا', 'نبدأ', 'يلا']
    return any(w in text.lower() for w in words)

def is_skip(text):
    tl = text.lower().strip()
    skip_words = [
        'تخطي', 'skip', 'بدون', 'بلا', 'مش',
        'لا املك', 'لا أملك', 'لااملك', 'لا امتلك',
        'ليس لدي', 'ليس عندي', 'ليست لدي',
        'ما عندي', 'ماعندي', 'ما لدي', 'مالدي',
        'لا يوجد', 'لايوجد', 'بدون بريد', 'بدون ايميل',
        'تجاوز', 'تجاوزها', 'مو موجود', 'غير موجود',
        'ما عنديش', 'ماعنديش',
        'no email', 'no social', 'none', 'nothing', 'nope'
    ]
    if tl in ['لا', 'no', 'nope']:
        return True
    return any(w in tl for w in skip_words)

# ========================================================================
# 12. حفظ الطلب
# ========================================================================
def save_order(sess, sender_id):
    col, _ = get_mongo()
    if col is None:
        add_log("⚠️ MongoDB غير متاح")
        return None
    try:
        cat = find_category(sess.get('category', ''))
        cat_name = cat.get('name', sess.get('categoryName', 'أخرى')) if cat else sess.get('categoryName', 'أخرى')
        cat_icon = cat.get('icon', 'fa-solid fa-box') if cat else sess.get('categoryIcon', 'fa-solid fa-box')

        details = sess.get('projectDetails', '')
        proj_name = details[:80] if details else sess.get('service', '')

        doc = {
            'id': f"ORD-{int(time.time() * 1000)}",
            'category': sess.get('category', 'other'),
            'categoryName': cat_name,
            'categoryIcon': cat_icon,
            'service': sess.get('service', ''),
            'projectName': proj_name,
            'projectDetails': details,
            'hasModel': sess.get('hasModel', False) if sess.get('hasModel') is not None else False,
            'modelFiles': [],
            'modelUrls': [],
            'modelDescription': '',
            'fullName': sess.get('name', ''),
            'phone': sess.get('phone', ''),
            'email': sess.get('email', ''),
            'socialAccounts': sess.get('social', []),
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'status': 'pending',
            'isNew': True,
        }
        result = col.insert_one(doc)
        add_log(f"✅ طلب محفوظ: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        add_log(f"❌ فشل الحفظ: {e}")
        return None

# ========================================================================
# 13. معالجة الرسائل
# ========================================================================
def process_message(sender_id, text):
    sender_id = str(sender_id)
    _cache['stats']['msgs_received'] += 1

    print("=" * 70, flush=True)
    print(f"📨 [MSG] من {sender_id}", flush=True)
    print(f"📝 [MSG] النص: {text}", flush=True)

    owner = get_owner_id()
    if owner and sender_id == owner:
        print(f"👑 [OWNER] → Executive Assistant", flush=True)
        try:
            reply = ask_executive_assistant(text)
        except Exception as e:
            add_log(f"❌ EA bridge: {e}")
            reply = None

        if not reply:
            reply = (
                "عذراً سيدي، تعذّر الوصول إلى المساعد التنفيذي حالياً.\n"
                "أعد إرسال رسالتك بعد لحظات من فضلك."
            )

        send_fb_long(sender_id, reply)
        return

    # ============ CUSTOMER PATH ============
    sess = get_session(sender_id)
    add_conv(sender_id, 'المستخدم', text)
    stage = sess.get('stage', 'welcome')
    print(f"🎯 [STAGE] {stage}", flush=True)

    if stage == 'welcome':
        raw = ask_ai(text, sess, extra_instruction="رحّب بالعميل واسأل كيف يمكنك مساعدته اليوم. رد مختصر.")
        clean, _, _ = parse_ai_tags(raw)
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'explore'
        return

    if stage == 'explore':
        raw = ask_ai(text, sess, extra_instruction="افهم احتياج العميل. اسأل سؤالاً أو سؤالين.")
        clean, cat_id, svc = parse_ai_tags(raw)
        if cat_id:
            cat = find_category(cat_id)
            if cat:
                sess['category'] = cat_id
                sess['categoryName'] = cat.get('name', '')
                sess['categoryIcon'] = cat.get('icon', 'fa-solid fa-box')
        if svc:
            sess['service'] = svc
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        if sess.get('service'):
            sess['stage'] = 'details'
        return

    if stage == 'details':
        if not sess.get('projectDetails'):
            sess['projectDetails'] = text.strip()[:2000]
        raw = ask_ai(text, sess, extra_instruction="اسأل العميل إذا كان لديه نموذج أو تصميم جاهز. سؤال واحد فقط.")
        clean, _, _ = parse_ai_tags(raw)
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'model'
        return

    if stage == 'model':
        tl = text.lower()
        if any(w in tl for w in ['نعم', 'yes', 'عندي', 'لدي', 'موجود', 'عندى']):
            sess['hasModel'] = True
        elif any(w in tl for w in ['لا', 'no', 'ليس', 'ماعندي', 'مش', 'بدون']):
            sess['hasModel'] = False
        raw = ask_ai(text, sess, extra_instruction="قدّم السعر التقريبي والمدة بوضوح بالدولار. انتظر موافقة العميل.")
        clean, cat_id, svc = parse_ai_tags(raw)
        if cat_id:
            cat = find_category(cat_id)
            if cat:
                sess['category'] = cat_id
                sess['categoryName'] = cat.get('name', '')
                sess['categoryIcon'] = cat.get('icon', 'fa-solid fa-box')
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)

        pm = re.search(r'(\d{2,6})\s*[-–]\s*(\d{2,6})\s*\$', clean)
        sp = re.search(r'(\d{3,6})\s*\$', clean)
        if pm:
            sess['budget'] = int(pm.group(1))
        elif sp:
            sess['budget'] = int(sp.group(1))
        dm = re.search(r'(\d+[-–]\d+\s*(?:يوم|أيام|أسبوع|أسابيع|شهر|أشهر|day|days|week|weeks|month|months))', clean, re.I)
        if dm:
            sess['duration'] = dm.group(1)
        sess['stage'] = 'price'
        return

    if stage == 'price':
        if is_confirmation(text):
            sess['stage'] = 'collecting_name'
            send_fb(sender_id, "ممتاز! نحتاج بعض المعلومات لتسجيل طلبك.\nما اسمك الكامل؟")
        else:
            raw = ask_ai(text, sess, extra_instruction="العميل يستفسر. أجبه باختصار. ذكّره بالسؤال: هل توافق؟")
            clean, _, _ = parse_ai_tags(raw)
            send_fb(sender_id, clean)
            add_conv(sender_id, 'الوكيل', clean)
        return

    if stage == 'collecting_name':
        name = extract_name(text)
        if name:
            sess['name'] = name
            sess['stage'] = 'collecting_phone'
            send_fb(sender_id, f"تمام {name}، ما رقم هاتفك؟")
        else:
            send_fb(sender_id, "ما اسمك الكامل؟")
        return

    if stage == 'collecting_phone':
        phone = extract_phone(text)
        if phone:
            sess['phone'] = phone
            sess['stage'] = 'collecting_email'
            send_fb(sender_id, "هل لديك بريد إلكتروني؟ (اختياري — أرسل 'تخطي')")
        else:
            send_fb(sender_id, "أرسل رقم هاتفك (مثال: +213795082763)")
        return

    if stage == 'collecting_email':
        if is_skip(text):
            sess['email'] = ''
            sess['stage'] = 'collecting_social'
            send_fb(sender_id, "حسناً. هل لديك روابط سوشيال ميديا؟ (اختياري — أرسل 'تخطي')")
        else:
            email = extract_email(text)
            if email:
                sess['email'] = email
                sess['stage'] = 'collecting_social'
                send_fb(sender_id, "هل لديك روابط سوشيال ميديا؟ (اختياري — أرسل 'تخطي')")
            else:
                send_fb(sender_id, "البريد غير صالح. أرسل بريداً صحيحاً أو 'تخطي'.")
        return

    if stage == 'collecting_social':
        if not is_skip(text):
            url = re.search(r'https?://[^\s]+', text)
            if url:
                sess['social'].append({'platform': 'social', 'url': url.group(0)})
            else:
                sess['social'].append({'platform': 'social', 'url': text.strip()[:200]})
        else:
            sess['social'] = []

        oid = save_order(sess, sender_id)
        if oid:
            msg = (
                f"شكراً {sess.get('name', '')} على ثقتك بنا 🌟\n\n"
                f"تم تسجيل طلبك بنجاح.\n"
                f"سنتواصل معك مجدداً لمناقشة التفاصيل والبدء في مشروعك.\n\n"
                f"فريق B.Y PRO"
            )
            send_fb(sender_id, msg)
        else:
            send_fb(sender_id, "حدث خطأ تقني أثناء حفظ الطلب. سنتواصل معك قريباً.")
        _cache['sessions'][sender_id] = new_session()
        return

    raw = ask_ai(text, sess)
    clean, _, _ = parse_ai_tags(raw)
    send_fb(sender_id, clean)
    add_conv(sender_id, 'الوكيل', clean)

# ========================================================================
# 14. Webhook
# ========================================================================
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        print(f"✅ Webhook verified", flush=True)
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    body = request.json
    print("=" * 70, flush=True)
    print(f"📥 [WEBHOOK] حدث جديد", flush=True)

    if not body or body.get('object') != 'page':
        return 'OK', 200

    for entry in body.get('entry', []):
        for msg in entry.get('messaging', []):
            sender = str(msg.get('sender', {}).get('id', ''))
            message = msg.get('message', {})

            if 'text' in message:
                print(f"📨 [TEXT] من {sender}: {message['text'][:80]}", flush=True)
                threading.Thread(target=process_message, args=(sender, message['text']), daemon=True).start()
                continue
            if 'postback' in msg:
                print(f"🔘 [POSTBACK] من {sender}", flush=True)
                continue
            if message.get('is_echo'):
                continue
            if 'delivery' in msg:
                continue
            if 'read' in msg:
                continue

    return 'OK', 200

# ========================================================================
# 15. API
# ========================================================================
@app.route('/api/orders', methods=['GET'])
def api_orders():
    col, _ = get_mongo()
    if col is None:
        return jsonify([])
    orders = list(col.find().sort('createdAt', -1).limit(100))
    for o in orders:
        o['_id'] = str(o['_id'])
    return jsonify(orders)

@app.route('/api/categories', methods=['GET'])
def api_categories():
    return jsonify(get_categories())

@app.route('/api/reload_categories', methods=['GET', 'POST'])
def api_reload_categories():
    _cache['categories'] = None
    load_categories()
    return jsonify({'success': True, 'count': len(get_categories())})

@app.route('/api/logs', methods=['GET'])
def api_logs():
    return jsonify(list(logs)[:100])

@app.route('/api/set_owner', methods=['GET', 'POST'])
def api_set_owner():
    global OWNER_FB_ID
    if request.method == 'GET':
        oid = request.args.get('owner_id', '').strip()
    else:
        data = request.json or {}
        oid = str(data.get('owner_id', '')).strip()
    if oid:
        OWNER_FB_ID = oid
        _cache['owner_id'] = oid
        add_log(f"👑 تم تعيين المدير: {oid}")
        return jsonify({'success': True, 'owner_id': oid})
    return jsonify({'success': False, 'error': 'owner_id required'}), 400

@app.route('/api/set_owner_direct/<owner_id>', methods=['GET'])
def api_set_owner_direct(owner_id):
    global OWNER_FB_ID
    oid = str(owner_id).strip()
    if oid:
        OWNER_FB_ID = oid
        _cache['owner_id'] = oid
        add_log(f"👑 تم تعيين المدير: {oid}")
        return jsonify({'success': True, 'owner_id': oid})
    return jsonify({'success': False, 'error': 'invalid'}), 400

@app.route('/api/whoami', methods=['GET'])
def api_whoami():
    return jsonify({
        'owner_id': _cache.get('owner_id'),
        'sessions': list(_cache['sessions'].keys())[-10:]
    })

@app.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    col, _ = get_mongo()
    total = completed = pending = 0
    if col is not None:
        total = col.count_documents({})
        completed = col.count_documents({'status': 'completed'})
        pending = col.count_documents({'status': 'pending'})
    return jsonify({'total_orders': total, 'completed': completed, 'pending': pending})

@app.route('/health')
def health():
    col, _ = get_mongo()
    return jsonify({
        'status': 'ok',
        'mongo': col is not None,
        'owner_id': _cache.get('owner_id'),
        'categories_loaded': len(get_categories()),
    })

@app.route('/api/test_owner_ai', methods=['GET', 'POST'])
def api_test_owner_ai():
    """Diagnostic endpoint — simulates an owner message and returns the reply."""
    if request.method == 'GET':
        msg = request.args.get('msg', 'مرحبا')
    else:
        data = request.json or {}
        msg = data.get('msg', 'مرحبا')
    reply = ask_executive_assistant(msg)
    return jsonify({'input': msg, 'reply': reply})

# ========================================================================
# 16. Keep-Alive
# ========================================================================
def keep_alive():
    while True:
        time.sleep(240)
        try:
            requests.get(SELF_URL + '/health', timeout=10)
        except:
            pass

# ========================================================================
# 17. التشغيل
# ========================================================================
if __name__ == '__main__':
    print("=" * 70, flush=True)
    print("🚀 B.Y PRO Marketing Agent v3", flush=True)
    print("=" * 70, flush=True)
    print(f"👤 Owner ID: {OWNER_FB_ID or 'غير محدد'}", flush=True)
    print(f"📄 Page ID: {PAGE_ID}", flush=True)
    print(f"🤖 AI: {OPENROUTER_MODEL}", flush=True)
    print(f"🔑 PAGE_ACCESS_TOKEN: {'موجود' if PAGE_ACCESS_TOKEN else 'مفقود!'}", flush=True)
    col, _ = get_mongo()
    print(f"🗄️ MongoDB: {'متصل' if col is not None else 'غير متصل'}", flush=True)
    print(f"👑 Owner → Executive Assistant (Dashboard AI)", flush=True)
    print(f"📱 Formatting: Messenger-friendly (no Markdown tables/code)", flush=True)
    load_categories()
    print("=" * 70 + "\n", flush=True)

    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
