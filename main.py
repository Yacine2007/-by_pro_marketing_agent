# ========================================================================
# B.Y PRO Marketing Agent - Render Server
# v5.1 — Owner → Executive Assistant + Full Diagnostics
# Fixes: MongoDB _db() returning Database + Facebook send fallback
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
# CORS
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
# تحميل الأسرار من GitHub
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
    print("🔐 تحميل الأسرار من GitHub...", flush=True)
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN غير موجود", flush=True)
        return
    headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github.raw'}
    for path in SECRET_FILES:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        try:
            r = requests.get(url, headers=headers, params={'ref': GITHUB_BRANCH}, timeout=15)
            if r.status_code != 200:
                print(f"⚠️ {path}: {r.status_code}", flush=True)
                continue
            for line in r.text.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v:
                    os.environ[k] = v
            print(f"✅ {path}", flush=True)
        except Exception as e:
            print(f"❌ {path}: {e}", flush=True)

load_secrets_from_github()

# ========================================================================
# المفاتيح
# ========================================================================
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN      = os.environ.get('VERIFY_TOKEN', 'bypro_verify_2026')
OWNER_FB_ID       = os.environ.get('OWNER_FB_ID', '25923199944038952')
PAGE_ID           = os.environ.get('PAGE_ID', '923170140890240')

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_MODEL   = os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')
OPENROUTER_URL     = 'https://openrouter.ai/api/v1/chat/completions'

MONGODB_URI         = os.environ.get('MONGODB_URI')
ORDERS_DB_NAME      = os.environ.get('ORDERS_DB_NAME', 'bypro_orders')
ORDERS_COLLECTION   = 'orders'
SETTINGS_DB_NAME    = os.environ.get('SETTINGS_DB_NAME', 'DashboardDB')
SETTINGS_COLLECTION = 'settings'
SETTINGS_KEY        = 'service_settings'

# Dashboard shared collections
DASHBOARD_DB_NAME     = 'DashboardDB'
CHAT_COLLECTION       = 'chat_history'
CLIENTS_COLLECTION    = 'clients'
PROJECTS_COLLECTION   = 'projects_registry'
DASH_SETTINGS_COLL    = 'settings'

# Owner's isolated conversation (source of truth for Messenger)
OWNER_CHAT_COLLECTION = 'messenger_owner_chat'

SELF_URL = os.environ.get('SELF_URL', 'https://by-pro-marketing-agent-v2jk.onrender.com')

# ========================================================================
# MongoDB
# ========================================================================
_mongo_client = None
_orders_col = None
_settings_col = None

def get_mongo():
    """Initialize MongoDB connection and return (orders_col, settings_col)."""
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
    """Return the Dashboard DATABASE object (not the client)."""
    if _mongo_client is None:
        get_mongo()
    if _mongo_client is None:
        return None
    return _mongo_client[DASHBOARD_DB_NAME]

# ========================================================================
# Utilities
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
# Categories
# ========================================================================
DEFAULT_CATEGORIES = [
    {"id": "design", "enabled": True, "name": "التصميم", "services": ["شعارات","هوية بصرية","سوشيال ميديا"]},
    {"id": "web", "enabled": True, "name": "مواقع", "services": ["صفحة هبوط","متجر","موقع"]},
    {"id": "apps", "enabled": True, "name": "تطبيقات", "services": ["أندرويد","iOS","Web App"]},
    {"id": "systems", "enabled": True, "name": "أنظمة", "services": ["ERP","CRM","بوتات"]},
    {"id": "marketing", "enabled": True, "name": "تسويق", "services": ["تسويق رقمي","SEO"]},
    {"id": "other", "enabled": True, "name": "أخرى", "services": ["خدمة مخصصة"]},
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
            add_log(f"✅ {len(cats)} تصنيف محمّل")
            return cats
    except Exception as e:
        add_log(f"❌ categories: {e}")
    return None

def get_categories():
    if _cache['categories'] is None:
        load_categories()
    if _cache['categories'] is None:
        _cache['categories'] = DEFAULT_CATEGORIES
    return _cache['categories']

def format_categories_for_ai():
    out = []
    for c in get_categories():
        if not c.get('enabled', True):
            continue
        svc = []
        for s in c.get('services', []):
            if isinstance(s, dict):
                if s.get('enabled', True):
                    svc.append(s.get('label_ar') or s.get('label_en') or s.get('id', ''))
            elif isinstance(s, str):
                svc.append(s)
        out.append(f"[{c.get('id','')}] {c.get('name','')}: {', '.join(svc)}")
    return "\n".join(out)

def find_category(cat_id):
    for c in get_categories():
        if c.get('id') == cat_id:
            return c
    return None

def get_owner_id():
    if _cache['owner_id']:
        return _cache['owner_id']
    if OWNER_FB_ID:
        _cache['owner_id'] = str(OWNER_FB_ID)
        return _cache['owner_id']
    return None

# ========================================================================
# AI — single function used everywhere
# ========================================================================
def ask_ai_raw(prompt, max_tokens=2000):
    """Single-turn AI call — used by both customer flow and owner flow."""
    if not OPENROUTER_API_KEY:
        add_log("❌ OPENROUTER_API_KEY غير موجود")
        return None
    try:
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
            'HTTP-Referer': SELF_URL,
            'X-Title': 'B.Y PRO Agent',
        }
        payload = {
            'model': OPENROUTER_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'max_tokens': max_tokens,
        }
        t0 = time.time()
        r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
        dt = round(time.time() - t0, 1)
        if r.status_code == 200:
            data = r.json()
            answer = (data.get('choices') or [{}])[0].get('message', {}).get('content', '')
            if answer and answer.strip():
                add_log(f"✅ AI ({dt}s, {len(answer)} chars)")
                return answer.strip()
            add_log(f"⚠️ AI empty ({dt}s)")
            return None
        add_log(f"❌ AI {r.status_code} ({dt}s): {r.text[:200]}")
        return None
    except Exception as e:
        add_log(f"❌ AI exception: {e}")
        return None

# ========================================================================
# OWNER — isolated conversation + context
# ========================================================================
def owner_history_load(limit=12):
    """Load owner's recent messages from the isolated collection."""
    db = _db()
    if db is None:
        return []
    try:
        docs = list(db[OWNER_CHAT_COLLECTION].find({}).sort('_id', -1).limit(limit))
        docs.reverse()
        return [{'role': d.get('role', 'user'), 'content': d.get('content', '')} for d in docs]
    except Exception as e:
        add_log(f"⚠️ owner_history_load: {e}")
        return []

def owner_history_save(role, content):
    """Save to owner collection + mirror into Dashboard chat_history."""
    db = _db()
    if db is None:
        return
    ts = datetime.now(timezone.utc).isoformat()
    try:
        db[OWNER_CHAT_COLLECTION].insert_one({'role': role, 'content': content, 'timestamp': ts})
    except Exception as e:
        add_log(f"⚠️ owner_save (own): {e}")
    try:
        db[CHAT_COLLECTION].insert_one({
            'role': role, 'content': content, 'timestamp': ts,
            'meta': {'source': 'messenger'},
        })
    except Exception as e:
        add_log(f"⚠️ owner_save (mirror): {e}")

def owner_history_reset():
    db = _db()
    if db is None:
        return False
    try:
        db[OWNER_CHAT_COLLECTION].delete_many({})
        return True
    except Exception:
        return False

def get_clients(limit=40):
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
            }
            out.append({k: v for k, v in item.items() if v})
        return out
    except Exception as e:
        add_log(f"⚠️ clients: {e}")
        return []

def get_pending_orders(limit=15):
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

def get_stats():
    db = _db()
    if db is None:
        return {}
    try:
        col = db[PROJECTS_COLLECTION]
        return {
            'clients': db[CLIENTS_COLLECTION].count_documents({}),
            'projects': col.count_documents({'kind': 'project'}),
            'completed': col.count_documents({'kind': 'project', 'progress': {'$gte': 100}}),
        }
    except Exception as e:
        add_log(f"⚠️ stats: {e}")
        return {}

def ask_ea(user_msg):
    """Owner path — single-turn, isolated history, full business context."""
    add_log(f"👑 [EA] معالجة رسالة المدير ({len(user_msg)} حرف)")

    # Save user message
    owner_history_save('user', user_msg)

    # Load previous conversation (without the just-saved message)
    history = owner_history_load(limit=13)
    if history and history[-1]['role'] == 'user' and history[-1]['content'].strip() == user_msg.strip():
        history = history[:-1]

    history_text = ""
    for h in history[-10:]:
        role_ar = "المدير" if h['role'] == 'user' else "المساعد"
        history_text += f"{role_ar}: {h['content']}\n"

    # Business context
    stats = get_stats()
    clients = get_clients(40)
    pending = get_pending_orders(15)
    now = datetime.now()

    prompt = f"""أنت المساعد التنفيذي لشركة B.Y PRO للتكنولوجيا والبرمجيات.
اسم المدير: ياسين بن مقران. نادِه "سيدي" أو "سيدي ياسين".
أجب بنفس لغة المدير.

=== الوقت الحالي ===
{now.strftime('%A, %Y-%m-%d %H:%M')}

=== إحصائيات ===
- العملاء: {stats.get('clients', 0)}
- المشاريع: {stats.get('projects', 0)}
- المشاريع المكتملة: {stats.get('completed', 0)}
- الطلبات المعلقة: {len(pending)}

=== قائمة العملاء (آخر {len(clients)}) ===
{json.dumps(clients, ensure_ascii=False)}

=== الطلبات المعلقة ===
{json.dumps(pending, ensure_ascii=False)}

=== قواعد الرد ===
- مختصر ومهني.
- استخدم النقاط (•) وليس الجداول.
- لا تستخدم ``` أو ### أو **.
- استخدم البيانات أعلاه فقط، لا تخترع أرقاماً.

=== سجل المحادثة ===
{history_text if history_text else '(محادثة جديدة)'}

المدير: {user_msg}
المساعد:"""

    reply = ask_ai_raw(prompt, max_tokens=1800)

    if reply:
        owner_history_save('assistant', reply)
        return reply

    return None

# ========================================================================
# CUSTOMER path
# ========================================================================
def get_bot_personality():
    return f"""أنت وكيل تسويق لخدمة العملاء في B.Y PRO.

الخدمات:
{format_categories_for_ai()}

أجب بنفس لغة العميل. مختصر وودود.

الأسعار التقريبية (دولار):
- صفحة هبوط: 1500-4000 | موقع: 4000-12000 | متجر: 3500-15000
- تطبيق: 5000-20000 | بوت: 300-2000 | شعار: 150-500

أضف في نهاية كل رد:
[CATEGORY:id]
[SERVICE:اسم_الخدمة]"""

def parse_ai_tags(text):
    cat = re.search(r'\[CATEGORY:([a-zA-Z0-9_\-]+)\]', text)
    svc = re.search(r'\[SERVICE:([^\]]+)\]', text)
    clean = re.sub(r'\[CATEGORY:[^\]]+\]', '', text)
    clean = re.sub(r'\[SERVICE:[^\]]+\]', '', clean)
    return clean.strip(), (cat.group(1) if cat else None), (svc.group(1).strip() if svc else None)

def ask_ai_customer(user_msg, sess, extra=""):
    context = "\n".join(sess.get('conversation', [])[-12:])
    stage = sess.get('stage', 'welcome')
    hints = {
        'welcome': "رحّب واسأل كيف يمكنك المساعدة.",
        'explore': "افهم ما يريد. اسأل 1-2 سؤال.",
        'details': "اطلب تفاصيل المشروع.",
        'model': "اسأل إذا كان لديه نموذج.",
        'price': "قدّم السعر والمدة.",
    }
    full = f"""{get_bot_personality()}

[المرحلة: {stage}] {hints.get(stage, '')}
{extra}

سجل:
{context}

العميل: {user_msg}
الوكيل:"""
    res = ask_ai_raw(full, max_tokens=1500)
    return res[:2500] if res else "عذراً، حدث خطأ. أعد رسالتك."

# ========================================================================
# Facebook Send — with 3-strategy fallback
# ========================================================================
def send_fb(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        add_log("❌ PAGE_ACCESS_TOKEN مفقود")
        return False

    url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
    text = (text or '')[:2000]

    strategies = [
        # 1) Standard reply within 24h window
        {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE',
        },
        # 2) Update type (used for non-reply messages)
        {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'UPDATE',
        },
        # 3) Human agent tag (bypasses window restrictions)
        {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'MESSAGE_TAG',
            'tag': 'HUMAN_AGENT',
        },
    ]

    last_err = None
    for i, payload in enumerate(strategies):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                _cache['stats']['msgs_sent'] += 1
                add_log(f"📤 → {str(recipient_id)[:12]} ({len(text)} chars) [strategy {i+1}]")
                return True
            last_err = f"{r.status_code}: {r.text[:180]}"
            add_log(f"⚠️ send_fb attempt {i+1} failed: {last_err}")
        except Exception as e:
            last_err = str(e)
            add_log(f"⚠️ send_fb attempt {i+1} exception: {e}")

    add_log(f"❌ send_fb all strategies failed: {last_err}")
    return False

# ========================================================================
# Sessions (customers)
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
# Extraction helpers
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
            'fullName': sess.get('name', ''),
            'phone': sess.get('phone', ''),
            'email': sess.get('email', ''),
            'socialAccounts': sess.get('social', []),
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'status': 'pending',
            'isNew': True,
        }
        r = col.insert_one(doc)
        add_log(f"✅ order saved: {r.inserted_id}")
        return str(r.inserted_id)
    except Exception as e:
        add_log(f"❌ save_order: {e}")
        return None

# ========================================================================
# Message processing
# ========================================================================
def process_message(sender_id, text):
    sender_id = str(sender_id)
    _cache['stats']['msgs_received'] += 1
    print("=" * 70, flush=True)
    print(f"📨 [{sender_id}] {text[:120]}", flush=True)

    owner = get_owner_id()
    is_owner = (owner and sender_id == owner)
    print(f"👤 owner_id={owner} | sender={sender_id} | is_owner={is_owner}", flush=True)

    # ==========================================================
    # OWNER PATH
    # ==========================================================
    if is_owner:
        print("👑 OWNER PATH", flush=True)
        reply = None
        try:
            reply = ask_ea(text)
        except Exception as e:
            add_log(f"❌ EA exception: {e}")
            import traceback
            traceback.print_exc()

        if not reply:
            reply = "عذراً سيدي، تعذّر الوصول إلى المساعد التنفيذي. أعد المحاولة من فضلك."

        ok = send_fb(sender_id, reply)
        print(f"📤 owner reply sent={ok}, length={len(reply)}", flush=True)
        return

    # ==========================================================
    # CUSTOMER PATH
    # ==========================================================
    sess = get_session(sender_id)
    add_conv(sender_id, 'المستخدم', text)
    stage = sess.get('stage', 'welcome')
    print(f"🎯 CUSTOMER stage={stage}", flush=True)

    if stage == 'welcome':
        raw = ask_ai_customer(text, sess, "رحّب واسأل كيف يمكنك المساعدة.")
        clean, _, _ = parse_ai_tags(raw)
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'explore'
        return

    if stage == 'explore':
        raw = ask_ai_customer(text, sess)
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
        raw = ask_ai_customer(text, sess, "اسأل إذا كان لديه نموذج. سؤال واحد.")
        clean, _, _ = parse_ai_tags(raw)
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'model'
        return

    if stage == 'model':
        sess['hasModel'] = any(w in text.lower() for w in ['نعم','yes','عندي','لدي'])
        raw = ask_ai_customer(text, sess, "قدّم السعر والمدة. انتظر الموافقة.")
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
            raw = ask_ai_customer(text, sess, "ذكّره بالسؤال: هل توافق؟")
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
            send_fb(sender_id, "هل لديك بريد إلكتروني؟ ('تخطي' للمتابعة)")
        else:
            send_fb(sender_id, "أرسل رقم هاتفك")
        return

    if stage == 'collecting_email':
        if is_skip(text):
            sess['email'] = ''
            sess['stage'] = 'collecting_social'
            send_fb(sender_id, "هل لديك روابط سوشيال؟ ('تخطي')")
        else:
            email = extract_email(text)
            if email:
                sess['email'] = email
                sess['stage'] = 'collecting_social'
                send_fb(sender_id, "هل لديك روابط سوشيال؟ ('تخطي')")
            else:
                send_fb(sender_id, "البريد غير صالح أو 'تخطي'")
        return

    if stage == 'collecting_social':
        if not is_skip(text):
            url = re.search(r'https?://[^\s]+', text)
            sess['social'].append({'platform': 'social', 'url': url.group(0) if url else text.strip()[:200]})
        oid = save_order(sess, sender_id)
        if oid:
            send_fb(sender_id, f"شكراً {sess.get('name','')} 🌟\nتم تسجيل طلبك.\nفريق B.Y PRO")
        else:
            send_fb(sender_id, "حدث خطأ أثناء حفظ الطلب.")
        _cache['sessions'][sender_id] = new_session()
        return

    raw = ask_ai_customer(text, sess)
    clean, _, _ = parse_ai_tags(raw)
    send_fb(sender_id, clean)
    add_conv(sender_id, 'الوكيل', clean)

# ========================================================================
# Webhook
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
                print(f"📥 webhook text from {sender}", flush=True)
                threading.Thread(
                    target=process_message,
                    args=(sender, message['text']),
                    daemon=True,
                ).start()
    return 'OK', 200

# ========================================================================
# API endpoints
# ========================================================================
@app.route('/health')
def health():
    col, _ = get_mongo()
    return jsonify({
        'status': 'ok',
        'version': 'v5.1',
        'mongo': col is not None,
        'owner_id': _cache.get('owner_id'),
        'owner_fb_id_env': OWNER_FB_ID,
        'ai_key_set': bool(OPENROUTER_API_KEY),
        'fb_token_set': bool(PAGE_ACCESS_TOKEN),
        'categories_loaded': len(get_categories()),
        'stats': _cache['stats'],
    })

@app.route('/api/logs', methods=['GET'])
def api_logs():
    return jsonify(list(logs)[:100])

@app.route('/api/whoami', methods=['GET'])
def api_whoami():
    return jsonify({
        'owner_id': _cache.get('owner_id'),
        'owner_fb_id_env': OWNER_FB_ID,
        'sessions': list(_cache['sessions'].keys())[-10:],
    })

@app.route('/api/set_owner_direct/<owner_id>', methods=['GET'])
def api_set_owner_direct(owner_id):
    global OWNER_FB_ID
    OWNER_FB_ID = str(owner_id).strip()
    _cache['owner_id'] = OWNER_FB_ID
    add_log(f"👑 owner set: {OWNER_FB_ID}")
    return jsonify({'success': True, 'owner_id': OWNER_FB_ID})

@app.route('/api/test_owner_ai', methods=['GET', 'POST'])
def api_test_owner_ai():
    """Test EA pipeline without Messenger."""
    if request.method == 'GET':
        msg = request.args.get('msg', 'مرحبا، كم عدد العملاء؟')
    else:
        msg = (request.json or {}).get('msg', 'مرحبا')
    reply = ask_ea(msg)
    return jsonify({
        'input': msg,
        'reply': reply,
        'ai_key_set': bool(OPENROUTER_API_KEY),
        'mongo_connected': _db() is not None,
    })

@app.route('/api/test_send_fb', methods=['GET', 'POST'])
def api_test_send_fb():
    """Test send_fb to owner without going through AI."""
    if request.method == 'GET':
        msg = request.args.get('msg', '🧪 اختبار الإرسال من السيرفر')
    else:
        msg = (request.json or {}).get('msg', '🧪 اختبار الإرسال من السيرفر')
    owner = get_owner_id()
    if not owner:
        return jsonify({'error': 'owner not set'}), 400
    ok = send_fb(owner, msg)
    return jsonify({'owner': owner, 'sent': ok, 'fb_token_set': bool(PAGE_ACCESS_TOKEN)})

@app.route('/api/owner_history', methods=['GET'])
def api_owner_history():
    return jsonify(owner_history_load(limit=int(request.args.get('limit', 30))))

@app.route('/api/owner_reset', methods=['POST', 'GET'])
def api_owner_reset():
    return jsonify({'success': owner_history_reset()})

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

@app.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    col, _ = get_mongo()
    total = completed = pending = 0
    if col is not None:
        total = col.count_documents({})
        completed = col.count_documents({'status': 'completed'})
        pending = col.count_documents({'status': 'pending'})
    return jsonify({'total_orders': total, 'completed': completed, 'pending': pending})

# ========================================================================
# Keep alive
# ========================================================================
def keep_alive():
    while True:
        time.sleep(240)
        try:
            requests.get(SELF_URL + '/health', timeout=10)
        except Exception:
            pass

# ========================================================================
# Run
# ========================================================================
if __name__ == '__main__':
    print("=" * 70, flush=True)
    print("🚀 B.Y PRO Marketing Agent v5.1", flush=True)
    print("=" * 70, flush=True)
    print(f"👤 OWNER_FB_ID: {OWNER_FB_ID or 'غير محدد'}", flush=True)
    print(f"📄 PAGE_ID: {PAGE_ID}", flush=True)
    print(f"🤖 Model: {OPENROUTER_MODEL}", flush=True)
    print(f"🔑 PAGE_ACCESS_TOKEN: {'موجود' if PAGE_ACCESS_TOKEN else 'مفقود!'}", flush=True)
    print(f"🔑 OPENROUTER_API_KEY: {'موجود' if OPENROUTER_API_KEY else 'مفقود!'}", flush=True)
    col, _ = get_mongo()
    print(f"🗄️ MongoDB: {'متصل' if col is not None else 'غير متصل'}", flush=True)
    load_categories()
    print("=" * 70 + "\n", flush=True)

    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
