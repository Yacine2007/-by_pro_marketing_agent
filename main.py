# ========================================================================
# B.Y PRO Marketing Agent - Render Server
# ========================================================================
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
    print("🔐 [STARTUP] تحميل الأسرار...")
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN غير موجود")
        return
    headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github.raw'}
    for path in SECRET_FILES:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        try:
            r = requests.get(url, headers=headers, params={'ref': GITHUB_BRANCH}, timeout=15)
            if r.status_code != 200:
                print(f"⚠️ فشل {path}: {r.status_code}")
                continue
            for line in r.text.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v:
                    os.environ[k] = v
            print(f"✅ تم: {path}")
        except Exception as e:
            print(f"❌ {path}: {e}")

load_secrets_from_github()

# ========================================================================
# 2. المفاتيح
# ========================================================================
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN      = os.environ.get('VERIFY_TOKEN', 'bypro_verify_2026')
OWNER_FB_ID       = os.environ.get('OWNER_FB_ID', '')
PAGE_ID           = os.environ.get('PAGE_ID', '923170140890240')
PAGE_NAME         = os.environ.get('PAGE_NAME', 'B.Y PRO Marketing Agent')
USER_TOKEN        = os.environ.get('USER_TOKEN', '')

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
        print("❌ MONGODB_URI غير موجود")
        return None, None
    try:
        _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=15000, tlsAllowInvalidCertificates=True)
        _mongo_client.admin.command('ping')
        _orders_col = _mongo_client[ORDERS_DB_NAME][ORDERS_COLLECTION]
        _settings_col = _mongo_client[SETTINGS_DB_NAME][SETTINGS_COLLECTION]
        print("✅ MongoDB متصل")
        return _orders_col, _settings_col
    except Exception as e:
        print(f"❌ MongoDB: {e}")
        return None, None

# ========================================================================
# 4. التخزين المؤقت
# ========================================================================
_cache = {
    'sessions': {},
    'stats': {'msgs_received': 0, 'msgs_sent': 0, 'start_time': datetime.now().isoformat()},
    'categories': None,  # تُحمّل من MongoDB
    'owner_id': None,    # يُكتشف تلقائياً
}
logs = deque(maxlen=200)

def add_log(msg):
    entry = {'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg}
    logs.appendleft(entry)
    print(f"[{entry['time']}] {msg}")

# ========================================================================
# 5. تحميل التصنيفات من MongoDB
# ========================================================================
def load_categories():
    """تحميل التصنيفات من DashboardDB.settings (نفس مصدر clients.html)"""
    _, settings_col = get_mongo()
    if settings_col is None:
        return None
    try:
        doc = settings_col.find_one({'key': SETTINGS_KEY})
        if doc and doc.get('value') and doc['value'].get('categories'):
            cats = doc['value']['categories']
            _cache['categories'] = cats
            print(f"✅ تم تحميل {len(cats)} تصنيف من MongoDB")
            return cats
        print("⚠️ لا توجد إعدادات في MongoDB — استخدام الافتراضي")
    except Exception as e:
        print(f"❌ فشل تحميل التصنيفات: {e}")
    return None

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

def get_categories():
    if _cache['categories'] is None:
        load_categories()
    if _cache['categories'] is None:
        _cache['categories'] = DEFAULT_CATEGORIES
    return _cache['categories']

def format_categories_for_ai():
    """تنسيق التصنيفات لتمريرها للـ AI"""
    cats = get_categories()
    lines = []
    for c in cats:
        if not c.get('enabled', True):
            continue
        name = c.get('name', c.get('id', ''))
        services = c.get('services', [])
        svc_labels = [s.get('label_ar') or s.get('label_en') or s.get('id') for s in services if (isinstance(s, dict) and s.get('enabled', True)) or isinstance(s, str)]
        lines.append(f"- {name}: {', '.join(svc_labels)}")
    return "\n".join(lines)

# ========================================================================
# 6. اكتشاف معرّف المدير
# ========================================================================
def get_owner_id():
    if _cache['owner_id']:
        return _cache['owner_id']
    if OWNER_FB_ID:
        _cache['owner_id'] = str(OWNER_FB_ID)
        return _cache['owner_id']
    return None

# ========================================================================
# 7. OpenRouter AI مع أسعار واقعية
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
# 8. شخصيات AI
# ========================================================================
def get_bot_personality():
    """شخصية البوت مع الأسعار الواقعية والتصنيفات"""
    cats_text = format_categories_for_ai()
    return f"""أنت وكيل تسويق لخدمة العملاء في شركة B.Y PRO للتكنولوجيا والبرمجيات.

شخصيتك:
- تتحدث كإنسان حقيقي، ودود ومريح، وليس كبوت.
- مختصر ومباشر، لا تطوّل بدون داعٍ.
- تفهم احتياج العميل قبل أي شيء.
- أجب بنفس لغة العميل (عربي، إنجليزي، فرنسي).

طريقة عملك:
1. رحّب بالعميل وافهم ما يريده.
2. إذا سأل عن الخدمات، اعرض عليه القائمة التالية:
{cats_text}
3. اسأل أسئلة لفهم المشروع (1-2 سؤال في كل مرة).
4. بعد الفهم، قدّم السعر التقريبي والمدة.
5. إذا وافق العميل، اطلب منه بياناته.

الخدمات والأسعار التقريبية (بالدولار الأمريكي):
- موقع ويب بسيط (صفحة هبوط): 1500$-4000$ (2-4 أسابيع)
- موقع ويب متكامل: 4000$-12000$ (6-12 أسبوع)
- متجر إلكتروني: 3500$-15000$ (10-20 أسبوع)
- تطبيق جوال بسيط: 5000$-20000$ (2-4 أشهر)
- تطبيق جوال معقد: 25000$-60000$ (4-8 أشهر)
- بوت ذكاء اصطناعي: 300$-2000$ (1-3 أسابيع)
- تصميم شعار: 150$-500$ (3-7 أيام)
- هوية بصرية كاملة: 800$-3000$ (2-4 أسابيع)
- مونتاج فيديو قصير (ريلز): 30$-100$
- مونتاج فيديو يوتيوب (5-10 دقائق): 150$-500$
- موشن جرافيك (60 ثانية): 500$-1500$
- برنامج مخصص/نظام (ERP/CRM): 8000$-40000$ (2-6 أشهر)
- سكربت مخصص: 500$-3000$

طريقة التحويل: إذا طلب العميل بالدينار الجزائري، استخدم: 1$ = 240 دج.

قواعد أساسية:
- لا تكرر نفسك.
- لا تظهر كبوت أبداً.
- لا تطلب بيانات شخصية قبل الاتفاق على السعر.
- كن واقعياً في الأسعار — لا تبالغ ولا تقلل.

مهم جداً: لا تسجّل الطلب ولا تطلب البيانات إلا بعد موافقة العميل صراحةً على السعر والمدة."""

OWNER_PERSONALITY = """أنت وكيل تسويق لخدمة العملاء في شركة B.Y PRO للتكنولوجيا والبرمجيات.

الشخص الذي تتحدث معه الآن هو المدير العام للشركة:
الاسم: ياسين بن مقران
الصفة: مؤسس ومدير شركة B.Y PRO.

قواعد:
- ناده "سيدي المدير" أو "سيدي ياسين"
- هو مديرك وليس عميلاً — لا تعرض عليه خدمات
- لا تسأله عن بيانات شخصية
- ردودك مختصرة وتخص إدارة البوت فقط
- أجبه بنفس اللغة التي يكتب بها
- لا تبدأ كل رد بـ "سيدي المدير" """

def ask_ai(user_msg, sess, extra_instruction="", personality=None):
    context = "\n".join(sess.get('conversation', [])[-12:])
    stage_hints = {
        'welcome': "رحّب بالعميل واسأل كيف يمكنك مساعدته.",
        'explore': "افهم احتياج العميل. اسأل سؤالاً أو سؤالين. إذا سأل عن الخدمات، اعرض القائمة.",
        'service_selected': "العميل اختار خدمة. اسأله عن اسم مشروعه.",
        'project_named': "العميل ذكر اسم المشروع. اطلب منه وصف المشروع بالتفصيل.",
        'details_collected': "العميل شرح مشروعه. اسأله إذا كان لديه نموذج أو تصميم جاهز.",
        'model_collected': "قدّم السعر التقريبي والمدة بوضوح. انتظر موافقته.",
        'price_proposed': "انتظر موافقة العميل على السعر.",
        'collecting_name': "اطلب من العميل اسمه الكامل.",
        'collecting_phone': f"اسم العميل: {sess.get('name','')}. اطلب رقم هاتفه.",
        'collecting_email': f"اسم العميل: {sess.get('name','')}. اطلب بريده الإلكتروني (اختياري).",
        'collecting_social': "اطلب روابط تواصله (سوشيال ميديا) إن وجدت.",
        'done': "الطلب مكتمل. اشكر العميل.",
    }
    active_personality = personality or get_bot_personality()
    stage = sess.get('stage', 'welcome')
    hint = stage_hints.get(stage, "")
    full_prompt = f"""{active_personality}

[حالة المحادثة: {hint}]
{extra_instruction}

سجل المحادثة:
{context}

المستخدم: {user_msg}
الوكيل:"""
    response = get_ai_response(full_prompt)
    if response:
        return response[:2000]
    return "عذراً، حدث خطأ تقني مؤقت. أعد رسالتك من فضلك."

# ========================================================================
# 9. فيسبوك
# ========================================================================
def send_fb(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        add_log("❌ PAGE_ACCESS_TOKEN غير موجود")
        return False
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {'recipient': {'id': recipient_id}, 'message': {'text': text}, 'messaging_type': 'RESPONSE'}
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            _cache['stats']['msgs_sent'] += 1
            add_log(f"📤 {str(recipient_id)[:10]}: {text[:50]}")
            return True
        add_log(f"❌ فشل: {r.status_code} - {r.text[:150]}")
        return False
    except Exception as e:
        add_log(f"❌ إرسال: {e}")
        return False

# ========================================================================
# 10. الجلسات
# ========================================================================
def get_session(sender_id):
    sid = str(sender_id)
    if sid not in _cache['sessions']:
        _cache['sessions'][sid] = {
            'name': '', 'service': '', 'category': '', 'categoryName': '', 'categoryIcon': '',
            'projectName': '', 'projectDetails': '', 'hasModel': None,
            'budget': 0, 'duration': '',
            'phone': '', 'email': '', 'social': [],
            'stage': 'welcome', 'conversation': [],
            'price_offered': False,
        }
    return _cache['sessions'][sid]

def add_conv(sender_id, role, message):
    sess = get_session(sender_id)
    sess['conversation'].append(f"{role}: {message}")
    if len(sess['conversation']) > 20:
        sess['conversation'] = sess['conversation'][-20:]

# ========================================================================
# 11. استخراج البيانات
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
    patterns = [
        r'اسمي[:\s]*([\u0600-\u06FF\s]{3,30})',
        r'الاسم[:\s]*([\u0600-\u06FF\s]{3,30})',
        r'my name is[:\s]*([a-zA-Z\s]{3,30})',
        r'name[:\s]*([a-zA-Z\s]{3,30})',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            name = m.group(1).strip()
            if 2 <= len(name.split()) <= 4 and len(name) <= 30:
                return name
    return None

def is_confirmation(text):
    words = ['نعم', 'موافق', 'تمام', 'اوكي', 'اوك', 'ok', 'yes', 'موافقة', 'ماشي', 'اتفقنا', 'ممتاز', 'أوافق']
    return any(w in text.lower() for w in words)

# ========================================================================
# 12. حفظ الطلب في MongoDB (بنية clients.html)
# ========================================================================
def save_order(sess, sender_id):
    col, _ = get_mongo()
    if col is None:
        add_log("⚠️ MongoDB غير متاح")
        return None
    try:
        # إيجاد التصنيف
        cat = None
        for c in get_categories():
            if c.get('id') == sess.get('category') or c.get('name') == sess.get('categoryName'):
                cat = c
                break

        doc = {
            'id': f"ORD-{int(time.time() * 1000)}",
            'category': sess.get('category', 'other'),
            'categoryName': sess.get('categoryName', 'أخرى'),
            'categoryIcon': sess.get('categoryIcon', 'fa-solid fa-box'),
            'service': sess.get('service', ''),
            'projectName': sess.get('projectName', ''),
            'projectDetails': sess.get('projectDetails', ''),
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
            # حقول إضافية للتمييز
            'source': 'messenger',
            'source_page_id': PAGE_ID,
            'sender_id': sender_id,
        }
        result = col.insert_one(doc)
        add_log(f"✅ طلب محفوظ: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        add_log(f"❌ فشل الحفظ: {e}")
        return None

# ========================================================================
# 13. معالجة الرسائل — التسلسل الجديد
# ========================================================================
def process_message(sender_id, text):
    sender_id = str(sender_id)
    _cache['stats']['msgs_received'] += 1

    print("=" * 70)
    print(f"📨 من {sender_id[:15]}: {text[:100]}")
    print("=" * 70)

    # اكتشاف المدير تلقائياً
    owner_id = get_owner_id()
    if owner_id and sender_id == owner_id:
        print(f"👑 [OWNER] المدير — استخدام OWNER_PERSONALITY")
        sess = get_session(sender_id)
        add_conv(sender_id, 'المستخدم', text)
        reply = ask_ai(text, sess, personality=OWNER_PERSONALITY)
        send_fb(sender_id, reply)
        add_conv(sender_id, 'الوكيل', reply)
        return

    sess = get_session(sender_id)
    add_conv(sender_id, 'المستخدم', text)
    stage = sess.get('stage', 'welcome')
    print(f"🎯 المرحلة: {stage}")

    # ====== 1. الترحيب ======
    if stage == 'welcome':
        print(f"👋 ترحيب")
        reply = ask_ai(text, sess, extra_instruction="رحّب بالعميل واسأل كيف يمكنك مساعدته. لا تطوّل.")
        send_fb(sender_id, reply)
        add_conv(sender_id, 'الوكيل', reply)
        sess['stage'] = 'explore'
        return

    # ====== 2. الاستكشاف ======
    if stage == 'explore':
        print(f"🔍 استكشاف")
        # نتحقق أولاً: هل اختار خدمة محددة؟
        reply = ask_ai(text, sess, extra_instruction="افهم ما يريده العميل. إذا سأل عن الخدمات، اعرض القائمة. اسأل سؤالاً أو سؤالين.")
        send_fb(sender_id, reply)
        add_conv(sender_id, 'الوكيل', reply)

        # نحاول استخراج التصنيف/الخدمة من رد العميل
        text_lower = (text + ' ' + reply).lower()
        for cat in get_categories():
            cat_name = cat.get('name', '').lower()
            cat_id = cat.get('id', '').lower()
            if cat_name in text_lower or cat_id in text_lower:
                sess['category'] = cat.get('id', '')
                sess['categoryName'] = cat.get('name', '')
                sess['categoryIcon'] = cat.get('icon', 'fa-solid fa-box')
                print(f"📂 تصنيف: {sess['categoryName']}")
                break

        # ننتقل لاختيار الخدمة
        sess['stage'] = 'service_selected'
        return

    # ====== 3. اختيار الخدمة ======
    if stage == 'service_selected':
        print(f"🛠️ خدمة")
        if not sess.get('service'):
            reply = ask_ai(text, sess, extra_instruction="العميل يحدد الخدمة. اسأله عن اسم مشروعه.")
            send_fb(sender_id, reply)
            add_conv(sender_id, 'الوكيل', reply)
            # نحاول استخراج اسم الخدمة من النص
            sess['service'] = text.strip()[:100]
            sess['stage'] = 'project_named'
        else:
            sess['stage'] = 'project_named'
            reply = ask_ai(text, sess, extra_instruction="اسأل العميل عن اسم مشروعه.")
            send_fb(sender_id, reply)
            add_conv(sender_id, 'الوكيل', reply)
        return

    # ====== 4. اسم المشروع ======
    if stage == 'project_named':
        print(f"📝 اسم المشروع")
        if not sess.get('projectName'):
            sess['projectName'] = text.strip()[:200]
            print(f"✅ المشروع: {sess['projectName'][:50]}")
        reply = ask_ai(text, sess, extra_instruction="اطلب من العميل وصف المشروع بالتفصيل (الأهداف، المميزات، المتطلبات).")
        send_fb(sender_id, reply)
        add_conv(sender_id, 'الوكيل', reply)
        sess['stage'] = 'details_collected'
        return

    # ====== 5. تفاصيل المشروع ======
    if stage == 'details_collected':
        print(f"📋 التفاصيل")
        if not sess.get('projectDetails'):
            sess['projectDetails'] = text.strip()[:2000]
            print(f"✅ التفاصيل: {len(sess['projectDetails'])} حرف")
        reply = ask_ai(text, sess, extra_instruction="اسأل العميل إذا كان لديه نموذج أو تصميم جاهز.")
        send_fb(sender_id, reply)
        add_conv(sender_id, 'الوكيل', reply)
        sess['stage'] = 'model_collected'
        return

    # ====== 6. النموذج/التصميم ======
    if stage == 'model_collected':
        print(f"🖼️ النموذج")
        text_lower = text.lower()
        if any(w in text_lower for w in ['نعم', 'yes', 'عندي', 'لدي', 'موجود']):
            sess['hasModel'] = True
        elif any(w in text_lower for w in ['لا', 'no', 'ليس', 'ماعندي', 'مش']):
            sess['hasModel'] = False
        else:
            sess['hasModel'] = None

        # نقدّم السعر
        reply = ask_ai(text, sess, extra_instruction="قدّم السعر التقريبي والمدة بوضوح. استخدم أسعاراً واقعية بالدولار. إذا طلب الدينار الجزائري، استخدم 1$=240 دج. انتظر موافقة العميل.")
        send_fb(sender_id, reply)
        add_conv(sender_id, 'الوكيل', reply)
        sess['stage'] = 'price_proposed'
        sess['price_offered'] = True

        # نحاول استخراج السعر من الرد
        price_match = re.search(r'(\d{2,6})\s*[-–]\s*(\d{2,6})\s*\$', reply)
        single = re.search(r'(\d{3,6})\s*\$', reply)
        if price_match:
            sess['budget'] = int(price_match.group(1))
        elif single:
            sess['budget'] = int(single.group(1))
        dur = re.search(r'(\d+[-–]\d+\s*(?:يوم|أيام|أسبوع|أسابيع|شهر|أشهر|day|days|week|weeks|month|months))', reply, re.I)
        if dur:
            sess['duration'] = dur.group(1)
        return

    # ====== 7. السعر (انتظار الموافقة) ======
    if stage == 'price_proposed':
        print(f"💰 السعر")
        if is_confirmation(text):
            print(f"✅ العميل وافق → جمع البيانات")
            sess['stage'] = 'collecting_name'
            send_fb(sender_id, "ممتاز! نحتاج بعض المعلومات لتسجيل طلبك.\nما اسمك الكامل؟")
        else:
            reply = ask_ai(text, sess, extra_instruction="العميل يستفسر أو يريد تعديلاً. أجبه باختصار.")
            send_fb(sender_id, reply)
            add_conv(sender_id, 'الوكيل', reply)
        return

    # ====== 8. جمع الاسم ======
    if stage == 'collecting_name':
        print(f"📛 الاسم")
        name = extract_name(text)
        if not name and len(text.split()) <= 5 and len(text) <= 40:
            name = text.strip()
        if name:
            sess['name'] = name
            sess['stage'] = 'collecting_phone'
            print(f"✅ {name}")
            send_fb(sender_id, f"تمام {name}، ما رقم هاتفك؟")
        else:
            send_fb(sender_id, "ما اسمك الكامل؟")
        return

    # ====== 9. جمع الهاتف ======
    if stage == 'collecting_phone':
        print(f"📞 الهاتف")
        phone = extract_phone(text)
        if phone:
            sess['phone'] = phone
            sess['stage'] = 'collecting_email'
            print(f"✅ {phone}")
            send_fb(sender_id, "هل لديك بريد إلكتروني؟ (اختياري — أرسل 'تخطي' للمتابعة)")
        else:
            send_fb(sender_id, "أرسل رقم هاتفك فقط (مثال: +213795082763 أو 0555123456)")
        return

    # ====== 10. جمع البريد ======
    if stage == 'collecting_email':
        print(f"📧 البريد")
        text_lower = text.lower().strip()
        if text_lower in ['تخطي', 'skip', 'لا', 'no', 'بدون']:
            sess['email'] = ''
            sess['stage'] = 'collecting_social'
            send_fb(sender_id, "هل لديك روابط سوشيال ميديا (فيسبوك، إنستغرام...)؟ (اختياري — أرسل 'تخطي')")
        else:
            email = extract_email(text)
            if email:
                sess['email'] = email
                sess['stage'] = 'collecting_social'
                print(f"✅ {email}")
                send_fb(sender_id, "هل لديك روابط سوشيال ميديا؟ (اختياري — أرسل 'تخطي')")
            else:
                send_fb(sender_id, "البريد غير صالح. أرسل بريداً صحيحاً أو 'تخطي'.")
        return

    # ====== 11. جمع السوشيال ======
    if stage == 'collecting_social':
        print(f"🔗 السوشيال")
        text_lower = text.lower().strip()
        if text_lower in ['تخطي', 'skip', 'لا', 'no', 'بدون']:
            sess['social'] = []
        else:
            # نحاول استخراج رابط
            url_match = re.search(r'https?://[^\s]+', text)
            if url_match:
                sess['social'].append({'platform': 'social', 'url': url_match.group(0)})
            else:
                sess['social'].append({'platform': 'social', 'url': text.strip()[:200]})

        # حفظ الطلب
        print(f"💾 حفظ الطلب...")
        order_id = save_order(sess, sender_id)
        if order_id:
            print(f"✅ تم حفظ الطلب")
            send_fb(sender_id, f"شكراً {sess['name']}! تم تسجيل طلبك بنجاح ✅\n\nسنتواصل معك قريباً لمناقشة التفاصيل والبدء في مشروعك.\n\nفريق B.Y PRO")
        else:
            send_fb(sender_id, "حدث خطأ تقني أثناء حفظ الطلب. سنتواصل معك قريباً.")
            add_log("❌ فشل حفظ الطلب")

        # إعادة تعيين الجلسة
        _cache['sessions'][sender_id] = {
            'name': '', 'service': '', 'category': '', 'categoryName': '', 'categoryIcon': '',
            'projectName': '', 'projectDetails': '', 'hasModel': None,
            'budget': 0, 'duration': '', 'phone': '', 'email': '', 'social': [],
            'stage': 'welcome', 'conversation': [], 'price_offered': False,
        }
        return

    # fallback
    print(f"🔄 fallback")
    reply = ask_ai(text, sess)
    send_fb(sender_id, reply)
    add_conv(sender_id, 'الوكيل', reply)

# ========================================================================
# 14. Webhook
# ========================================================================
@app.route('/webhook', methods=['GET'])
def verify():
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if token == VERIFY_TOKEN:
        print(f"✅ Webhook verified")
        return challenge
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    body = request.json
    print("=" * 70)
    print(f"📥 Webhook")
    print("=" * 70)

    if not body or body.get('object') != 'page':
        return 'OK', 200

    for entry in body.get('entry', []):
        for msg in entry.get('messaging', []):
            sender = str(msg.get('sender', {}).get('id', ''))
            message = msg.get('message', {})

            if 'text' in message:
                print(f"📨 نص من {sender[:12]}: {message['text'][:80]}")
                threading.Thread(target=process_message, args=(sender, message['text']), daemon=True).start()
                continue

            if 'postback' in msg:
                print(f"🔘 postback")
                continue
            if message.get('is_echo'):
                print(f"🔁 echo")
                continue
            if 'delivery' in msg:
                print(f"✓ delivery")
                continue
            if 'read' in msg:
                print(f"👁️ read")
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

@app.route('/api/clients', methods=['GET'])
def api_clients():
    col, _ = get_mongo()
    if col is None:
        return jsonify([])
    orders = list(col.find().sort('createdAt', -1))
    clients = {}
    for o in orders:
        sid = o.get('sender_id', '')
        if not sid or sid in clients:
            continue
        clients[sid] = {
            'id': sid,
            'name': o.get('fullName', ''),
            'phone': o.get('phone', ''),
            'source': 'messenger',
            'status': o.get('status', 'pending'),
            'order': {
                'service': o.get('service', ''),
                'project_name': o.get('projectName', ''),
                'project_details': o.get('projectDetails', ''),
            },
        }
    return jsonify(list(clients.values()))

@app.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    col, _ = get_mongo()
    total = completed = pending = 0
    if col is not None:
        total = col.count_documents({})
        completed = col.count_documents({'status': 'completed'})
        pending = col.count_documents({'status': 'pending'})
    return jsonify({'total_orders': total, 'completed': completed, 'pending': pending})

@app.route('/api/logs', methods=['GET'])
def api_logs():
    return jsonify(list(logs)[:100])

@app.route('/api/categories', methods=['GET'])
def api_categories():
    return jsonify(get_categories())

@app.route('/api/reload_categories', methods=['POST'])
def api_reload_categories():
    _cache['categories'] = None
    load_categories()
    return jsonify({'success': True, 'count': len(get_categories())})

@app.route('/api/set_owner', methods=['POST'])
def api_set_owner():
    """لتعيين معرّف المدير يدوياً"""
    global OWNER_FB_ID
    data = request.json or {}
    owner_id = str(data.get('owner_id', '')).strip()
    if owner_id:
        OWNER_FB_ID = owner_id
        _cache['owner_id'] = owner_id
        return jsonify({'success': True, 'owner_id': owner_id})
    return jsonify({'success': False, 'error': 'owner_id required'}), 400

@app.route('/health')
def health():
    col, _ = get_mongo()
    return jsonify({'status': 'ok', 'mongo': col is not None, 'owner_id': _cache.get('owner_id')})

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
    print("=" * 70)
    print("🚀 B.Y PRO Marketing Agent")
    print("=" * 70)
    print(f"👤 Owner ID: {OWNER_FB_ID or 'غير محدد'}")
    print(f"📄 Page ID: {PAGE_ID}")
    print(f"🤖 AI: {OPENROUTER_MODEL}")
    print(f"🔑 PAGE_ACCESS_TOKEN: {'موجود' if PAGE_ACCESS_TOKEN else 'مفقود!'}")
    print(f"🔑 USER_TOKEN: {'موجود' if USER_TOKEN else 'مفقود!'}")
    col, _ = get_mongo()
    print(f"🗄️ MongoDB: {'متصل' if col is not None else 'غير متصل'}")
    # تحميل التصنيفات
    load_categories()
    print("=" * 70 + "\n")

    threading.Thread(target=keep_alive, daemon=True).start()

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
