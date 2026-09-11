# ========================================================================
# B.Y PRO Marketing Agent - Render Server (Final)
# ========================================================================
import sys
sys.stdout.reconfigure(line_buffering=True)  # ← مهم: يُظهر logs فوراً

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
OWNER_FB_ID       = os.environ.get('OWNER_FB_ID', '')
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
# 5. التصنيفات من MongoDB
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
    """عرض التصنيفات مع ID للـ AI"""
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
# 6. معرّف المدير
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
        add_log(f"❌ AI HTTP {r.status_code}: {r.text[:150]}")
        return None
    except Exception as e:
        add_log(f"❌ AI: {e}")
        return None

# ========================================================================
# 8. الشخصيات
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
6. إذا وافق، اطلب بياناته (اسم، هاتف، بريد، سوشيال).

الأسعار التقريبية الواقعية (بالدولار):
- صفحة هبوط بسيطة: 1500$-4000$ (2-4 أسابيع)
- موقع متكامل: 4000$-12000$ (6-12 أسبوع)
- متجر إلكتروني: 3500$-15000$ (10-20 أسبوع)
- تطبيق بسيط: 5000$-20000$ (2-4 أشهر)
- تطبيق معقد: 25000$-60000$ (4-8 أشهر)
- بوت AI: 300$-2000$ (1-3 أسابيع)
- شعار: 150$-500$ (3-7 أيام)
- هوية بصرية: 800$-3000$ (2-4 أسابيع)
- ريلز (مونتاج): 30$-100$
- فيديو يوتيوب: 150$-500$
- موشن جرافيك (60 ث): 500$-1500$
- نظام ERP/CRM: 8000$-40000$ (2-6 أشهر)
- سكربت مخصص: 500$-3000$

التحويل: 1$ = 240 دج (إذا طلب الدينار الجزائري).

⚠️ مهم جداً: في نهاية كل رد، أضف سطراً منفصلاً بالشكل:
[CATEGORY:id]
[SERVICE:اسم_الخدمة]

حيث id هو معرّف التصنيف من القائمة أعلاه.
مثال: [CATEGORY:web]
[SERVICE:صفحة هبوط]

هذه الوسوم تُستخدم داخلياً وسيتم حذفها قبل إرسال الرد للعميل. لا تشرحها للعميل."""

OWNER_PERSONALITY = """أنت وكيل تسويق لخدمة العملاء في شركة B.Y PRO.

المتحدث هو المدير العام: ياسين بن مقران — مؤسس الشركة.

قواعد:
- ناده "سيدي المدير" أو "سيدي ياسين"
- هو مديرك وليس عميلاً
- لا تعرض خدمات
- ردودك مختصرة
- أجبه بنفس لغته
- لا تبدأ كل رد بالتحية"""

def parse_ai_tags(text):
    """استخراج الوسوم من رد AI"""
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
        'explore': "افهم ما يريد. اسأل 1-2 سؤال. إذا سأل عن الخدمات اعرض القائمة.",
        'details': "اطلب من العميل تفاصيل مشروعه كاملة (الأهداف، المميزات، المتطلبات).",
        'model': "اسأل العميل إذا كان لديه نموذج أو تصميم جاهز.",
        'price': "قدّم السعر والمدة بوضوح. انتظر موافقته.",
        'collecting_name': "اطلب من العميل اسمه الكامل.",
        'collecting_phone': f"الاسم: {sess.get('name','')}. اطلب رقم هاتفه.",
        'collecting_email': "اطلب بريده الإلكتروني (اختياري).",
        'collecting_social': "اطلب روابط سوشيال ميديا (اختياري).",
    }
    p = personality or get_bot_personality()
    hint = hints.get(stage, "")
    full = f"""{p}

[المرحلة الحالية: {stage}]
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
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            _cache['stats']['msgs_sent'] += 1
            add_log(f"📤 {str(recipient_id)[:12]}: {text[:60]}")
            return True
        add_log(f"❌ فشل الإرسال: {r.status_code} - {r.text[:150]}")
        return False
    except Exception as e:
        add_log(f"❌ إرسال: {e}")
        return False

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
        print(f"🆕 [SESSION] جلسة جديدة لـ {sid[:15]}", flush=True)
        _cache['sessions'][sid] = new_session()
    return _cache['sessions'][sid]

def add_conv(sender_id, role, message):
    sess = get_session(sender_id)
    sess['conversation'].append(f"{role}: {message}")
    if len(sess['conversation']) > 20:
        sess['conversation'] = sess['conversation'][-20:]

# ========================================================================
# 11. استخراج
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
    for pat in [r'اسمي[:\s]*([\u0600-\u06FF\s]{3,30})', r'الاسم[:\s]*([\u0600-\u06FF\s]{3,30})',
                r'my name is[:\s]*([a-zA-Z\s]{3,30})', r'name[:\s]*([a-zA-Z\s]{3,30})']:
        m = re.search(pat, text, re.I)
        if m:
            n = m.group(1).strip()
            if 2 <= len(n.split()) <= 5 and len(n) <= 40:
                return n
    return None

def is_confirmation(text):
    words = ['نعم', 'موافق', 'تمام', 'اوكي', 'اوك', 'ok', 'yes', 'موافقة', 'ماشي', 'اتفقنا', 'ممتاز', 'أوافق', 'نبدا', 'نبدأ']
    return any(w in text.lower() for w in words)

def is_skip(text):
    return text.lower().strip() in ['تخطي', 'skip', 'لا', 'no', 'بدون', 'بلا', 'مش']

# ========================================================================
# 12. حفظ الطلب (بنية clients.html بالضبط)
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

    # المدير
    owner = get_owner_id()
    if owner and sender_id == owner:
        print(f"👑 [OWNER] المدير", flush=True)
        sess = get_session(sender_id)
        add_conv(sender_id, 'المستخدم', text)
        reply = ask_ai(text, sess, personality=OWNER_PERSONALITY)
        send_fb(sender_id, reply)
        add_conv(sender_id, 'الوكيل', reply)
        return

    sess = get_session(sender_id)
    add_conv(sender_id, 'المستخدم', text)
    stage = sess.get('stage', 'welcome')
    print(f"🎯 [STAGE] {stage}", flush=True)

    # ===== 1. welcome =====
    if stage == 'welcome':
        raw = ask_ai(text, sess, extra_instruction="رحّب بالعميل واسأل كيف يمكنك مساعدته اليوم. رد مختصر.")
        clean, cat_id, svc = parse_ai_tags(raw)
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'explore'
        return

    # ===== 2. explore =====
    if stage == 'explore':
        raw = ask_ai(text, sess, extra_instruction="افهم احتياج العميل. اسأل سؤالاً أو سؤالين. إذا سأل عن الخدمات اعرض القائمة.")
        clean, cat_id, svc = parse_ai_tags(raw)
        if cat_id:
            cat = find_category(cat_id)
            if cat:
                sess['category'] = cat_id
                sess['categoryName'] = cat.get('name', '')
                sess['categoryIcon'] = cat.get('icon', 'fa-solid fa-box')
                print(f"📂 [CATEGORY] {cat.get('name')}", flush=True)
        if svc:
            sess['service'] = svc
            print(f"🛠️ [SERVICE] {svc}", flush=True)

        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)

        # ننتقل لمرحلة التفاصيل بعد التعرف على الخدمة
        if sess.get('service'):
            sess['stage'] = 'details'
        return

    # ===== 3. details =====
    if stage == 'details':
        if not sess.get('projectDetails'):
            sess['projectDetails'] = text.strip()[:2000]
            print(f"✅ [DETAILS] {len(sess['projectDetails'])} حرف", flush=True)
        raw = ask_ai(text, sess, extra_instruction="اسأل العميل إذا كان لديه نموذج أو تصميم جاهز للمشروع.")
        clean, _, _ = parse_ai_tags(raw)
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)
        sess['stage'] = 'model'
        return

    # ===== 4. model =====
    if stage == 'model':
        tl = text.lower()
        if any(w in tl for w in ['نعم', 'yes', 'عندي', 'لدي', 'موجود', 'عندى']):
            sess['hasModel'] = True
        elif any(w in tl for w in ['لا', 'no', 'ليس', 'ماعندي', 'مش', 'بدون']):
            sess['hasModel'] = False
        print(f"🖼️ [MODEL] {sess['hasModel']}", flush=True)

        raw = ask_ai(text, sess, extra_instruction="قدّم السعر التقريبي والمدة بوضوح بالدولار (أو الدينار إذا طلب، 1$=240دج). انتظر موافقة العميل.")
        clean, cat_id, svc = parse_ai_tags(raw)
        if cat_id:
            cat = find_category(cat_id)
            if cat:
                sess['category'] = cat_id
                sess['categoryName'] = cat.get('name', '')
                sess['categoryIcon'] = cat.get('icon', 'fa-solid fa-box')
        send_fb(sender_id, clean)
        add_conv(sender_id, 'الوكيل', clean)

        # نحاول استخراج السعر
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

    # ===== 5. price =====
    if stage == 'price':
        if is_confirmation(text):
            print(f"✅ [CONFIRM] العميل وافق", flush=True)
            sess['stage'] = 'collecting_name'
            send_fb(sender_id, "ممتاز! نحتاج بعض المعلومات لتسجيل طلبك.\nما اسمك الكامل؟")
        else:
            raw = ask_ai(text, sess, extra_instruction="العميل يستفسر عن السعر. أجبه باختصار. ذكّره بالسؤال: هل توافق؟")
            clean, _, _ = parse_ai_tags(raw)
            send_fb(sender_id, clean)
            add_conv(sender_id, 'الوكيل', clean)
        return

    # ===== 6. name =====
    if stage == 'collecting_name':
        name = extract_name(text)
        if not name and len(text.split()) <= 5 and len(text) <= 40:
            if not any(w in text.lower() for w in ['نعم', 'لا', 'كيف', 'متى', 'ماذا', 'شكرا']):
                name = text.strip()
        if name:
            sess['name'] = name
            sess['stage'] = 'collecting_phone'
            print(f"✅ [NAME] {name}", flush=True)
            send_fb(sender_id, f"تمام {name}، ما رقم هاتفك؟")
        else:
            send_fb(sender_id, "ما اسمك الكامل؟")
        return

    # ===== 7. phone =====
    if stage == 'collecting_phone':
        phone = extract_phone(text)
        if phone:
            sess['phone'] = phone
            sess['stage'] = 'collecting_email'
            print(f"✅ [PHONE] {phone}", flush=True)
            send_fb(sender_id, "هل لديك بريد إلكتروني؟ (اختياري — أرسل 'تخطي' للمتابعة)")
        else:
            send_fb(sender_id, "أرسل رقم هاتفك (مثال: +213795082763 أو 0555123456)")
        return

    # ===== 8. email =====
    if stage == 'collecting_email':
        if is_skip(text):
            sess['email'] = ''
            sess['stage'] = 'collecting_social'
            send_fb(sender_id, "هل لديك روابط سوشيال ميديا؟ (اختياري — أرسل 'تخطي')")
        else:
            email = extract_email(text)
            if email:
                sess['email'] = email
                sess['stage'] = 'collecting_social'
                print(f"✅ [EMAIL] {email}", flush=True)
                send_fb(sender_id, "هل لديك روابط سوشيال ميديا؟ (اختياري — أرسل 'تخطي')")
            else:
                send_fb(sender_id, "البريد غير صالح. أرسل بريداً صحيحاً أو 'تخطي'.")
        return

    # ===== 9. social =====
    if stage == 'collecting_social':
        if not is_skip(text):
            url = re.search(r'https?://[^\s]+', text)
            if url:
                sess['social'].append({'platform': 'social', 'url': url.group(0)})
            else:
                sess['social'].append({'platform': 'social', 'url': text.strip()[:200]})
        else:
            sess['social'] = []

        print(f"💾 [SAVE] جاري حفظ الطلب...", flush=True)
        oid = save_order(sess, sender_id)
        if oid:
            print(f"✅ [SAVED] {oid}", flush=True)
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

    # fallback
    print(f"🔄 [FALLBACK] {stage}", flush=True)
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
                print(f"🔁 [ECHO]", flush=True)
                continue
            if 'delivery' in msg:
                print(f"✓ [DELIVERY]", flush=True)
                continue
            if 'read' in msg:
                print(f"👁️ [READ]", flush=True)
                continue
            print(f"❓ [UNKNOWN] {json.dumps(msg)[:200]}", flush=True)

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

@app.route('/api/reload_categories', methods=['POST'])
def api_reload_categories():
    _cache['categories'] = None
    load_categories()
    return jsonify({'success': True, 'count': len(get_categories())})

@app.route('/api/logs', methods=['GET'])
def api_logs():
    return jsonify(list(logs)[:100])

@app.route('/api/set_owner', methods=['POST'])
def api_set_owner():
    global OWNER_FB_ID
    data = request.json or {}
    oid = str(data.get('owner_id', '')).strip()
    if oid:
        OWNER_FB_ID = oid
        _cache['owner_id'] = oid
        add_log(f"👑 تم تعيين المدير: {oid}")
        return jsonify({'success': True, 'owner_id': oid})
    return jsonify({'success': False, 'error': 'owner_id required'}), 400

@app.route('/api/whoami', methods=['GET'])
def api_whoami():
    """يُظهر PSID الفعلي لآخر مرسل"""
    if _cache['sessions']:
        sids = list(_cache['sessions'].keys())
        return jsonify({'last_senders': sids[-10:]})
    return jsonify({'last_senders': []})

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

# ========================================================================
# 16. Keep-Alive
# ========================================================================
def keep_alive():
    while True:
        time.sleep(300)
        try:
            requests.get(SELF_URL, timeout=8)
        except:
            pass

# ========================================================================
# 17. التشغيل
# ========================================================================
if __name__ == '__main__':
    print("=" * 70, flush=True)
    print("🚀 B.Y PRO Marketing Agent", flush=True)
    print("=" * 70, flush=True)
    print(f"👤 Owner ID: {OWNER_FB_ID or 'غير محدد'}", flush=True)
    print(f"📄 Page ID: {PAGE_ID}", flush=True)
    print(f"🤖 AI: {OPENROUTER_MODEL}", flush=True)
    print(f"🔑 PAGE_ACCESS_TOKEN: {'موجود' if PAGE_ACCESS_TOKEN else 'مفقود!'}", flush=True)
    col, _ = get_mongo()
    print(f"🗄️ MongoDB: {'متصل' if col is not None else 'غير متصل'}", flush=True)
    load_categories()
    print("=" * 70 + "\n", flush=True)

    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
