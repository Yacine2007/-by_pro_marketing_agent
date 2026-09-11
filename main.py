# ========================================================================
# B.Y PRO Marketing Agent - Render Server
# v4 — Minimal & Safe: Owner ↔ Executive Assistant via isolated collection
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
# 1. تحميل الأسرار
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

MONGODB_URI         = os.environ.get('MONGODB_URI')
ORDERS_DB_NAME      = os.environ.get('ORDERS_DB_NAME', 'bypro_orders')
ORDERS_COLLECTION   = 'orders'
SETTINGS_DB_NAME    = os.environ.get('SETTINGS_DB_NAME', 'DashboardDB')
SETTINGS_COLLECTION = 'settings'
SETTINGS_KEY        = 'service_settings'

# Shared with Dashboard
DASHBOARD_DB_NAME     = 'DashboardDB'
CHAT_COLLECTION       = 'chat_history'          # write-only mirror (so Dashboard shows it)
CLIENTS_COLLECTION    = 'clients'
PROJECTS_COLLECTION   = 'projects_registry'
DASH_SETTINGS_COLL    = 'settings'

# Owner ↔ Messenger isolated collection (read + write source of truth)
OWNER_CHAT_COLLECTION = 'messenger_owner_chat'

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
        _mongo_client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=15000,
            tlsAllowInvalidCertificates=True,
        )
        _mongo_client.admin.command('ping')
        _orders_col = _mongo_client[ORDERS_DB_NAME][ORDERS_COLLECTION]
        _settings_col = _mongo_client[SETTINGS_DB_NAME][SETTINGS_COLLECTION]
        print("✅ MongoDB متصل", flush=True)
        return _orders_col, _settings_col
    except Exception as e:
        print(f"❌ MongoDB: {e}", flush=True)
        return None, None

def _db():
    if _mongo_client is None:
        get_mongo()
    return _mongo_client

# ========================================================================
# 4. أدوات مساعدة
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
    {"id": "desktop", "enabled": True, "name": "ديسك توب", "icon": "fa-solid fa-desktop", "services": ["ويندوز","ماك","لينكس","إدارة","POS"]},
    {"id": "systems", "enabled": True, "name": "الأنظمة", "icon": "fa-solid fa-gears", "services": ["CMS","سكربت مخصص","ERP","CRM","فوترة","حجوزات","بوتات","أتمتة"]},
    {"id": "editing", "enabled": True, "name": "المونتاج", "icon": "fa-solid fa-film", "services": ["مونتاج فيديو","تعليق صوتي","موشن جرافيك","إعلانات","يوتيوب","ريلز"]},
    {"id": "security", "enabled": True, "name": "الأمن السيبراني", "icon": "fa-solid fa-shield-halved", "services": ["اختبار اختراق","حماية مواقع","تحليل ثغرات","استشارات"]},
    {"id": "marketing", "enabled": True, "name": "تسويق", "icon": "fa-solid fa-chart-line", "services": ["تسويق رقمي","إعلانات","SEO","محتوى","حملات"]},
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
            add_log(f"✅ تحميل {len(cats)} تصنيف")
            return cats
    except Exception as e:
        add_log(f"❌ تحميل التصنيفات: {e}")
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
        name = c.get('name', c.get('id', ''))
        services = c.get('services', [])
        svc_labels = []
        for s in services:
            if isinstance(s, dict):
                if s.get('enabled', True):
                    svc_labels.append(s.get('label_ar') or s.get('label_en') or s.get('id', ''))
            elif isinstance(s, str):
                svc_labels.append(s)
        lines.append(f"[{c.get('id','')}] {name}: {', '.join(svc_labels)}")
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
# 7. AI Calls (simple, single retry)
# ========================================================================
def _ai_headers(title):
    return {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': SELF_URL,
        'X-Title': title,
    }

def get_ai_response(prompt):
    """Single-turn AI call (used by customer flow)."""
    if not OPENROUTER_API_KEY:
        add_log("❌ OPENROUTER_API_KEY غير موجود")
        return None
    try:
        payload = {
            'model': OPENROUTER_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'max_tokens': 2048,
        }
        r = requests.post(OPENROUTER_URL, headers=_ai_headers('B.Y PRO Marketing Agent'),
                          json=payload, timeout=90)
        if r.status_code == 200:
            data = r.json()
            answer = (data.get('choices') or [{}])[0].get('message', {}).get('content', '')
            if answer and answer.strip():
                return answer.strip()
        add_log(f"❌ AI {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        add_log(f"❌ AI: {e}")
        return None

def call_ai_messages(messages, max_tokens=2000):
    """Multi-turn AI call (used by Executive Assistant). Returns (reply, err)."""
    if not OPENROUTER_API_KEY:
        return None, "missing key"
    try:
        payload = {
            'model': OPENROUTER_MODEL,
            'messages': messages,
            'temperature': 0.7,
            'max_tokens': max_tokens,
        }
        r = requests.post(OPENROUTER_URL, headers=_ai_headers('B.Y PRO Executive Assistant'),
                          json=payload, timeout=120)
        if r.status_code == 200:
            data = r.json()
            choices = data.get('choices') or []
            if not choices:
                return None, "empty choices"
            answer = choices[0].get('message', {}).get('content', '')
            if answer and answer.strip():
                return answer.strip(), None
            return None, "empty content"
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, str(e)

# ========================================================================
# 7b. Owner isolated conversation (v4 — SIMPLE)
# ========================================================================
def owner_read_history(limit=15):
    """Read owner's Messenger conversation from the isolated collection."""
    db = _db()
    if db is None:
        return []
    try:
        col = db[OWNER_CHAT_COLLECTION]
        docs = list(col.find({}).sort('_id', -1).limit(limit))
        docs.reverse()  # chronological
        return [{'role': d.get('role', 'user'), 'content': d.get('content', '')} for d in docs]
    except Exception as e:
        add_log(f"⚠️ owner_read_history: {e}")
        return []

def owner_save_message(role, content):
    """Save into owner collection (source of truth) + mirror into Dashboard chat."""
    db = _db()
    if db is None:
        return
    ts = datetime.now(timezone.utc).isoformat()
    try:
        db[OWNER_CHAT_COLLECTION].insert_one({
            'role': role, 'content': content, 'timestamp': ts,
        })
    except Exception as e:
        add_log(f"⚠️ owner_save (own): {e}")
    try:
        # mirror for Dashboard visibility (write-only)
        db[CHAT_COLLECTION].insert_one({
            'role': role, 'content': content, 'timestamp': ts,
            'meta': {'source': 'messenger'},
        })
    except Exception as e:
        add_log(f"⚠️ owner_save (mirror): {e}")

def owner_reset_history():
    """Clear the owner conversation (can be called manually via API)."""
    db = _db()
    if db is None:
        return False
    try:
        db[OWNER_CHAT_COLLECTION].delete_many({})
        return True
    except Exception as e:
        add_log(f"⚠️ owner_reset: {e}")
        return False

def get_dashboard_settings():
    db = _db()
    if db is None:
        return {}
    out = {}
    try:
        for doc in db[DASH_SETTINGS_COLL].find({}):
            k = doc.get('key')
            if k:
                out[k] = doc.get('value')
    except Exception as e:
        add_log(f"⚠️ settings: {e}")
    return out

def get_clients_compact(limit=60):
    """Compact client list — only the fields the AI really needs."""
    db = _db()
    if db is None:
        return []
    try:
        out = []
        for d in db[CLIENTS_COLLECTION].find({}).sort('_id', -1).limit(limit):
            order = d.get('order') or {}
            item = {
                'name': d.get('name', ''),
                'phone': d.get('phone', ''),
                'email': d.get('email', ''),
                'service': order.get('service', ''),
                'project': order.get('project_name', '') or d.get('project_name', ''),
                'status': d.get('status', ''),
                'source': d.get('source', ''),
            }
            # Remove empty fields to shrink payload
            out.append({k: v for k, v in item.items() if v})
        return out
    except Exception as e:
        add_log(f"⚠️ clients: {e}")
        return []

def get_pending_orders_compact(limit=20):
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
        add_log(f"⚠️ orders: {e}")
        return []

def get_company_stats():
    db = _db()
    if db is None:
        return {}
    try:
        col = db[PROJECTS_COLLECTION]
        return {
            'clients_count': db[CLIENTS_COLLECTION].count_documents({}),
            'projects_count': col.count_documents({'kind': 'project'}),
            'completed_projects': col.count_documents({'kind': 'project', 'progress': {'$gte': 100}}),
        }
    except Exception as e:
        add_log(f"⚠️ stats: {e}")
        return {}

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

# Small addition that does NOT fight the main system prompt:
MESSENGER_NOTE = (
    "\n\n[Note: your reply will be shown in Facebook Messenger, which is plain text. "
    "Prefer bullet lists (• item) over tables. Avoid ### headers. "
    "Keep it readable as plain text.]"
)

def build_executive_context():
    """Compact, bounded context — never explodes the payload."""
    settings = get_dashboard_settings()
    now = datetime.now()
    weekday = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][now.weekday()]

    stats = get_company_stats()
    clients = get_clients_compact(60)
    pending = get_pending_orders_compact(20)

    lines = [
        "=== CURRENT DATE & TIME ===",
        f"Today is {weekday}, {now.strftime('%Y-%m-%d %H:%M')}.",
        "",
        "=== LIVE BUSINESS DATA ===",
        f"Clients total: {stats.get('clients_count', 0)}",
        f"Projects total: {stats.get('projects_count', 0)}",
        f"Completed projects: {stats.get('completed_projects', 0)}",
        f"Pending orders: {len(pending)}",
        "",
        f"Clients (latest {len(clients)}):",
        json.dumps(clients, ensure_ascii=False),
        "",
        f"Pending orders:",
        json.dumps(pending, ensure_ascii=False),
        "",
        f"Company website: {settings.get('company_website','')}",
    ]
    return "\n".join(lines)

def ask_executive_assistant(user_msg):
    """Simple, isolated pipeline for the owner's Messenger messages."""
    # 1) Persist user message into owner collection + mirror
    owner_save_message('user', user_msg)

    # 2) Build context
    settings = get_dashboard_settings()
    base_prompt = (settings.get('system_prompt') or '').strip() or DEFAULT_SYSTEM_PROMPT_FALLBACK
    system_content = base_prompt + "\n\n" + build_executive_context() + MESSENGER_NOTE

    # 3) Build messages: 1 system + last 15 from owner's own history
    history = owner_read_history(limit=15)
    # Drop the just-saved user message (we'll re-add nothing — it's the last)
    # Actually keep it: history already includes it as the last item.
    messages = [{'role': 'system', 'content': system_content}]
    for h in history:
        if h['content']:
            messages.append({'role': h['role'], 'content': h['content']})

    # Safety: cap total payload size
    total_chars = sum(len(m.get('content', '')) for m in messages)
    if total_chars > 60000:
        # Trim history to last 6 turns and re-build system context smaller
        history = owner_read_history(limit=6)
        clients = get_clients_compact(15)
        pending = get_pending_orders_compact(5)
        now = datetime.now()
        compact_ctx = (
            f"Today: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"Clients count: {len(clients)}\n"
            f"Pending orders: {len(pending)}\n"
            f"Clients sample: {json.dumps(clients[:10], ensure_ascii=False)}\n"
            f"Orders: {json.dumps(pending, ensure_ascii=False)}"
        )
        system_content = base_prompt + "\n\n" + compact_ctx + MESSENGER_NOTE
        messages = [{'role': 'system', 'content': system_content}]
        for h in history:
            if h['content']:
                messages.append({'role': h['role'], 'content': h['content']})

    add_log(f"📏 EA payload: {len(messages)} msgs, ~{sum(len(m['content']) for m in messages)} chars")

    # 4) Call AI (single attempt — no cascading retries)
    reply, err = call_ai_messages(messages, max_tokens=1800)

    if reply is None:
        add_log(f"❌ EA AI failed: {err}")
        return None

    # 5) Persist assistant reply
    owner_save_message('assistant', reply)
    return reply

# ========================================================================
# 8. شخصيات العملاء
# ========================================================================
def get_bot_personality():
    cats_text = format_categories_for_ai()
    return f"""أنت وكيل تسويق لخدمة العملاء في شركة B.Y PRO للتكنولوجيا والبرمجيات.

شخصيتك:
- تتحدث كإنسان حقيقي، ودود ومريح، وليس كبوت.
- مختصر ومباشر.
- تفهم احتياج العميل قبل أي شيء.
- أجب بنفس لغة العميل.

الخدمات المتاحة:
{cats_text}

طريقة عملك:
1. رحّب واسأل كيف يمكنك المساعدة.
2. افهم تفاصيل المشروع.
3. اسأل إذا كان لديه نموذج جاهز.
4. قدّم السعر التقريبي والمدة.
5. إذا وافق، اطلب بياناته.

الأسعار التقريبية (بالدولار):
- صفحة هبوط: 1500-4000 | موقع: 4000-12000 | متجر: 3500-15000
- تطبيق بسيط: 5000-20000 | تطبيق معقد: 25000-60000
- بوت AI: 300-2000 | شعار: 150-500 | هوية: 800-3000
- ريلز: 30-100 | فيديو: 150-500 | موشن: 500-1500
- ERP/CRM: 8000-40000 | سكربت: 500-3000

⚠️ في نهاية كل رد أضف:
[CATEGORY:id]
[SERVICE:اسم_الخدمة]"""

def parse_ai_tags(text):
    cat = re.search(r'\[CATEGORY:([a-zA-Z0-9_\-]+)\]', text)
    svc = re.search(r'\[SERVICE:([^\]]+)\]', text)
    clean = re.sub(r'\[CATEGORY:[^\]]+\]', '', text)
    clean = re.sub(r'\[SERVICE:[^\]]+\]', '', clean)
    return clean.strip(), (cat.group(1) if cat else None), (svc.group(1).strip() if svc else None)

def ask_ai(user_msg, sess, extra_instruction="", personality=None):
    context = "\n".join(sess.get('conversation', [])[-12:])
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
    return res[:2500] if res else "عذراً، حدث خطأ تقني. أعد رسالتك من فضلك."

# ========================================================================
# 9. فيسبوك
# ========================================================================
def send_fb(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        add_log("❌ PAGE_ACCESS_TOKEN مفقود")
        return False
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE',
        }
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            _cache['stats']['msgs_sent'] += 1
            add_log(f"📤 {str(recipient_id)[:12]}: {text[:60]}")
            return True
        add_log(f"❌ إرسال {r.status_code}: {r.text[:150]}")
        return False
    except Exception as e:
        add_log(f"❌ إرسال: {e}")
        return False

def send_fb_long(recipient_id, text, max_len=1800):
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
# 10. الجلسات (للعملاء)
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
    for pat in [
        r'اسمي\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
        r'الاسم\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
        r'أنا\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
        r'my name is\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
    ]:
        m = re.search(pat, t, re.I)
        if m:
            name = m.group(1).strip()
            if 1 <= len(name.split()) <= 4 and 2 <= len(name) <= 40:
                return name
    words = t.split()
    if 1 <= len(words) <= 3 and len(t) <= 30:
        if not any(w in t.lower() for w in ['نعم','لا','كيف','متى','ماذا','شكرا','مرحبا']):
            return t
    return None

def is_confirmation(text):
    return any(w in text.lower() for w in ['نعم','موافق','تمام','اوكي','اوك','ok','yes','ماشي','اتفقنا','أوافق'])

def is_skip(text):
    tl = text.lower().strip()
    if tl in ['لا','no','nope']:
        return True
    return any(w in tl for w in ['تخطي','skip','بدون','مش','لا املك','ليس لدي','ماعندي','تجاوز','no email'])

# ========================================================================
# 12. حفظ الطلب
# ========================================================================
def save_order(sess, sender_id):
    col, _ = get_mongo()
    if col is None:
        return None
    try:
        cat = find_category(sess.get('category', ''))
        cat_name = cat.get('name', 'أخرى') if cat else 'أخرى'
        cat_icon = cat.get('icon', 'fa-solid fa-box') if cat else 'fa-solid fa-box'
        details = sess.get('projectDetails', '')
        doc = {
            'id': f"ORD-{int(time.time() * 1000)}",
            'category': sess.get('category', 'other'),
            'categoryName': cat_name,
            'categoryIcon': cat_icon,
            'service': sess.get('service', ''),
            'projectName': details[:80] if details else sess.get('service', ''),
            'projectDetails': details,
            'hasModel': bool(sess.get('hasModel')),
            'modelFiles': [], 'modelUrls': [], 'modelDescription': '',
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
        add_log(f"❌ حفظ: {e}")
        return None

# ========================================================================
# 13. معالجة الرسائل
# ========================================================================
def process_message(sender_id, text):
    sender_id = str(sender_id)
    _cache['stats']['msgs_received'] += 1
    print("=" * 70, flush=True)
    print(f"📨 من {sender_id}: {text[:100]}", flush=True)

    owner = get_owner_id()
    if owner and sender_id == owner:
        print(f"👑 [OWNER] → Executive Assistant", flush=True)
        try:
            reply = ask_executive_assistant(text)
        except Exception as e:
            add_log(f"❌ EA: {e}")
            reply = None
        if not reply:
            reply = "عذراً سيدي، حدث خطأ مؤقت. أعد المحاولة بعد لحظات."
        send_fb_long(sender_id, reply)
        return

    # ============ CUSTOMER PATH ============
    sess = get_session(sender_id)
    add_conv(sender_id, 'المستخدم', text)
    stage = sess.get('stage', 'welcome')

    if stage == 'welcome':
        raw = ask_ai(text, sess, extra_instruction="رحّب بالعميل واسأل كيف يمكنك مساعدته. رد مختصر.")
        clean, _, _ = parse_ai_tags(raw)
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'explore'
        return

    if stage == 'explore':
        raw = ask_ai(text, sess)
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
        raw = ask_ai(text, sess, extra_instruction="اسأل إذا كان لديه نموذج جاهز. سؤال واحد.")
        clean, _, _ = parse_ai_tags(raw)
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'model'
        return

    if stage == 'model':
        tl = text.lower()
        sess['hasModel'] = any(w in tl for w in ['نعم','yes','عندي','لدي'])
        raw = ask_ai(text, sess, extra_instruction="قدّم السعر والمدة. انتظر الموافقة.")
        clean, cat_id, _ = parse_ai_tags(raw)
        if cat_id:
            cat = find_category(cat_id)
            if cat:
                sess['category'] = cat_id
                sess['categoryName'] = cat.get('name', '')
                sess['categoryIcon'] = cat.get('icon', 'fa-solid fa-box')
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'price'
        return

    if stage == 'price':
        if is_confirmation(text):
            sess['stage'] = 'collecting_name'
            send_fb(sender_id, "ممتاز! ما اسمك الكامل؟")
        else:
            raw = ask_ai(text, sess, extra_instruction="العميل يستفسر. ذكّره بالسؤال: هل توافق؟")
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
            send_fb(sender_id, "هل لديك بريد إلكتروني؟ (اختياري — 'تخطي')")
        else:
            send_fb(sender_id, "أرسل رقم هاتفك")
        return

    if stage == 'collecting_email':
        if is_skip(text):
            sess['email'] = ''
            sess['stage'] = 'collecting_social'
            send_fb(sender_id, "هل لديك روابط سوشيال ميديا؟ (اختياري — 'تخطي')")
        else:
            email = extract_email(text)
            if email:
                sess['email'] = email
                sess['stage'] = 'collecting_social'
                send_fb(sender_id, "هل لديك روابط سوشيال ميديا؟ (اختياري — 'تخطي')")
            else:
                send_fb(sender_id, "البريد غير صالح أو 'تخطي'")
        return

    if stage == 'collecting_social':
        if not is_skip(text):
            url = re.search(r'https?://[^\s]+', text)
            sess['social'].append({'platform': 'social', 'url': url.group(0) if url else text.strip()[:200]})
        oid = save_order(sess, sender_id)
        if oid:
            send_fb(sender_id, f"شكراً {sess.get('name','')} 🌟\nتم تسجيل طلبك بنجاح.\nفريق B.Y PRO")
        else:
            send_fb(sender_id, "حدث خطأ أثناء حفظ الطلب.")
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
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    body = request.json
    if not body or body.get('object') != 'page':
        return 'OK', 200
    for entry in body.get('entry', []):
        for msg in entry.get('messaging', []):
            sender = str(msg.get('sender', {}).get('id', ''))
            message = msg.get('message', {})
            if 'text' in message:
                print(f"📨 {sender}: {message['text'][:80]}", flush=True)
                threading.Thread(target=process_message,
                                 args=(sender, message['text']), daemon=True).start()
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
        oid = str((request.json or {}).get('owner_id', '')).strip()
    if oid:
        OWNER_FB_ID = oid
        _cache['owner_id'] = oid
        add_log(f"👑 تم تعيين المدير: {oid}")
        return jsonify({'success': True, 'owner_id': oid})
    return jsonify({'success': False, 'error': 'required'}), 400

@app.route('/api/set_owner_direct/<owner_id>', methods=['GET'])
def api_set_owner_direct(owner_id):
    global OWNER_FB_ID
    oid = str(owner_id).strip()
    if oid:
        OWNER_FB_ID = oid
        _cache['owner_id'] = oid
        return jsonify({'success': True, 'owner_id': oid})
    return jsonify({'success': False}), 400

@app.route('/api/whoami', methods=['GET'])
def api_whoami():
    return jsonify({'owner_id': _cache.get('owner_id'), 'sessions': list(_cache['sessions'].keys())[-10:]})

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
        'version': 'v4',
    })

# ========================================================================
# Diagnostics & manual controls
# ========================================================================
@app.route('/api/test_owner_ai', methods=['GET', 'POST'])
def api_test_owner_ai():
    """Test the owner→EA pipeline without going through Messenger."""
    if request.method == 'GET':
        msg = request.args.get('msg', 'مرحبا')
    else:
        msg = (request.json or {}).get('msg', 'مرحبا')
    reply = ask_executive_assistant(msg)
    return jsonify({'input': msg, 'reply': reply})

@app.route('/api/owner_history', methods=['GET'])
def api_owner_history():
    """Inspect the owner's isolated conversation."""
    limit = int(request.args.get('limit', 30))
    return jsonify(owner_read_history(limit=limit))

@app.route('/api/owner_reset', methods=['POST', 'GET'])
def api_owner_reset():
    """Reset the owner's isolated conversation (safe — does NOT touch Dashboard chat)."""
    ok = owner_reset_history()
    return jsonify({'success': ok})

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
    print("🚀 B.Y PRO Marketing Agent v4", flush=True)
    print("=" * 70, flush=True)
    print(f"👤 Owner ID: {OWNER_FB_ID or 'غير محدد'}", flush=True)
    print(f"📄 Page ID: {PAGE_ID}", flush=True)
    print(f"🤖 AI: {OPENROUTER_MODEL}", flush=True)
    print(f"🔑 PAGE_ACCESS_TOKEN: {'موجود' if PAGE_ACCESS_TOKEN else 'مفقود!'}", flush=True)
    col, _ = get_mongo()
    print(f"🗄️ MongoDB: {'متصل' if col is not None else 'غير متصل'}", flush=True)
    print(f"👑 Owner → Executive Assistant (isolated collection)", flush=True)
    load_categories()
    print("=" * 70 + "\n", flush=True)
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
