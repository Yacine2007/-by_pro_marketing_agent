# ========================================================================
# B.Y PRO Marketing Agent - Render Server (with detailed logging)
# Flask + OpenRouter + MongoDB + Facebook Messenger Webhook
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
# 1. تحميل الأسرار من GitHub عند بدء التشغيل
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
    print("🔐 [STARTUP] جاري تحميل الأسرار من GitHub...")
    if not GITHUB_TOKEN:
        print("⚠️ [STARTUP] GITHUB_TOKEN غير موجود — سيتم الاعتماد على متغيرات Render فقط")
        return
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.raw',
    }
    for path in SECRET_FILES:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        try:
            r = requests.get(url, headers=headers, params={'ref': GITHUB_BRANCH}, timeout=15)
            if r.status_code != 200:
                print(f"⚠️ [STARTUP] فشل قراءة {path}: HTTP {r.status_code}")
                continue
            for line in r.text.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v:
                    os.environ[k] = v
            print(f"✅ [STARTUP] تم تحميل: {path}")
        except Exception as e:
            print(f"❌ [STARTUP] استثناء في {path}: {e}")

load_secrets_from_github()

# ========================================================================
# 2. المفاتيح
# ========================================================================
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN      = os.environ.get('VERIFY_TOKEN', 'bypro_verify_2026')
OWNER_FB_ID       = os.environ.get('OWNER_FB_ID', '122126937801008677')
PAGE_ID           = os.environ.get('PAGE_ID', '923170140890240')
PAGE_NAME         = os.environ.get('PAGE_NAME', 'B.Y PRO Marketing Agent')

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_MODEL   = os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')
OPENROUTER_URL     = 'https://openrouter.ai/api/v1/chat/completions'

MONGODB_URI        = os.environ.get('MONGODB_URI')
ORDERS_DB_NAME     = os.environ.get('ORDERS_DB_NAME', 'bypro_orders')
ORDERS_COLLECTION  = 'orders'

SELF_URL          = os.environ.get('SELF_URL', 'https://by-pro-marketing-agent-v2jk.onrender.com')
COMPANY_WEBSITE   = os.environ.get('COMPANY_WEBSITE', 'https://b.y-pro.kesug.com')

# ========================================================================
# 3. MongoDB
# ========================================================================
_mongo_client = None
_orders_col = None

def get_mongo_collection():
    global _mongo_client, _orders_col
    if _orders_col is not None:
        return _orders_col
    if not MONGODB_URI:
        print("❌ [MONGO] MONGODB_URI غير موجود")
        return None
    try:
        _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=15000, tlsAllowInvalidCertificates=True)
        _mongo_client.admin.command('ping')
        _orders_col = _mongo_client[ORDERS_DB_NAME][ORDERS_COLLECTION]
        print("✅ [MONGO] متصل بنجاح")
        return _orders_col
    except Exception as e:
        print(f"❌ [MONGO] فشل الاتصال: {e}")
        return None

# ========================================================================
# 4. التخزين المؤقت
# ========================================================================
_ram_cache = {
    'sessions': {},
    'stats': {'msgs_received': 0, 'msgs_sent': 0, 'start_time': datetime.now().isoformat()},
    'comment_replied_ids': [],
    'comment_stats': {},
    'comment_log': [],
    'publish_settings': {'enabled': False, 'interval_minutes': 60, 'post_text': '', 'add_chat_button': True, 'last_published': ''},
    'comment_settings': {'enabled': False, 'prompt': '', 'check_interval_minutes': 5},
}
logs = deque(maxlen=100)

def add_log(msg):
    entry = {'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg}
    logs.appendleft(entry)
    print(f"[{entry['time']}] {msg}")

# ========================================================================
# 5. شخصيات AI
# ========================================================================
BOT_PERSONALITY = """أنت وكيل تسويق لخدمة العملاء في شركة B.Y PRO للتكنولوجيا والبرمجيات.

شخصيتك:
- تتحدث كإنسان حقيقي، بأسلوب ودود ومريح، وليس كبوت آلي.
- مختصر ومباشر، لا تطوّل بدون داعٍ.
- تفهم احتياج العميل قبل أي شيء.

طريقة عملك مع العميل:
1. اسمع طلب العميل باختصار.
2. اسأله سؤالاً أو سؤالين بسيطين لفهم المشروع.
3. بعد الفهم، قدّم السعر التقريبي والمدة بوضوح.
4. إذا وافق، اطلب اسمه الكريم ورقم هاتفه لتسجيل الطلب.
5. لا تطلب أي بيانات شخصية قبل الاتفاق على السعر.

قواعد أساسية:
- لا تكرر نفسك.
- لا تظهر كبوت أبداً.
- أجب بنفس لغة العميل (عربي أو إنجليزي أو فرنسي).
- إذا سألك عن شيء تقني خارج نطاقك، قل له "أحوّلك للفريق التقني".

الخدمات والأسعار التقريبية:
- موقع ويب عادي: 300-800$ (5-10 أيام)
- متجر إلكتروني: 700-1800$ (15-25 يوم)
- بوت ذكاء اصطناعي: 500-2000$ (حسب التعقيد)
- تطبيق جوال: من 1500$ (30-60 يوم)
- تصميم جرافيك / شعار: 50-200$ (24-72 ساعة)
- برنامج مخصص: من 1000$ (حسب المشروع)

روابط الشركة:
- صفحة فيسبوك: https://www.facebook.com/bypro2007
- الموقع الرسمي: https://b.y-pro.kesug.com
- المتجر: https://store-pro.great-site.net
- دعم المتجر: https://t.me/STOREPROSPRT

طريقة الدفع: 30% مقدماً، 70% بعد التسليم.

مهم جداً: لا تسجّل الطلب ولا تطلب البيانات إلا بعد أن يوافق العميل صراحةً على السعر والمدة."""

OWNER_PERSONALITY = """أنت وكيل تسويق لخدمة العملاء في شركة B.Y PRO للتكنولوجيا والبرمجيات.

الشخص الذي تتحدث معه الآن هو المدير العام للشركة:
الاسم: ياسين بن مقران
الصفة: مؤسس ومدير شركة B.Y PRO — هو صاحبك ومديرك المباشر.

قواعد التعامل مع المدير ياسين:
- ناده دائماً بـ "سيدي المدير" أو "سيدي ياسين"
- تعامل معه باحترام كامل وأسلوب مهني راقٍ
- هو مديرك وليس عميلاً — لا تعرض عليه خدمات أبداً
- لا تسأله عن مشاريع أو ميزانيات أو بيانات شخصية
- ردودك معه مختصرة ومباشرة وتخص إدارة البوت والشركة فقط
- إذا سألك عن إحصائيات أو طلبات أو عملاء، قدّم المعلومات بشكل منظم وواضح
- أجبه بنفس اللغة التي يكتب بها
- لا تبدأ كل رد بـ "سيدي المدير" — استخدمها بشكل طبيعي"""

# ========================================================================
# 6. OpenRouter AI
# ========================================================================
def get_ai_response(prompt):
    if not OPENROUTER_API_KEY:
        add_log("❌ [AI] OPENROUTER_API_KEY غير موجود")
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
            'max_tokens': 1024,
        }
        add_log(f"🤖 [AI] إرسال طلب إلى {OPENROUTER_MODEL}...")
        r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=45)
        if r.status_code == 200:
            result = r.json()
            answer = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            if answer and answer.strip():
                add_log(f"✅ [AI] استجابة: {answer[:60]}...")
                return answer.strip()
            add_log("⚠️ [AI] استجابة فارغة")
            return None
        else:
            add_log(f"❌ [AI] HTTP {r.status_code}: {r.text[:150]}")
            return None
    except requests.exceptions.Timeout:
        add_log("❌ [AI] timeout بعد 45 ثانية")
        return None
    except Exception as e:
        add_log(f"❌ [AI] استثناء: {e}")
        return None

def ask_ai(user_msg, sess, extra_instruction="", personality=None):
    context = "\n".join(sess.get('conversation', [])[-12:])
    stage_hints = {
        'explore': "استمع للعميل، اسأل سؤالاً أو سؤالين، ثم قدّم السعر والمدة.",
        'price_proposed': "انتظر موافقة العميل. لا تضف معلومات جديدة.",
        'collecting_name': "اطلب من العميل اسمه الكريم فقط.",
        'collecting_phone': f"اسم العميل: {sess.get('name','')}. اطلب رقم هاتفه.",
    }
    active_personality = personality or BOT_PERSONALITY
    stage = sess.get('stage', 'explore')
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
        return response[:1800]
    return "عذراً، حدث خطأ تقني مؤقت. أعد رسالتك من فضلك."

# ========================================================================
# 7. فيسبوك
# ========================================================================
def send_fb(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        add_log("❌ [FB] PAGE_ACCESS_TOKEN غير موجود")
        return False
    try:
        add_log(f"📤 [FB] إرسال إلى {str(recipient_id)[:12]}...")
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {'recipient': {'id': recipient_id}, 'message': {'text': text}, 'messaging_type': 'RESPONSE'}
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            _ram_cache['stats']['msgs_sent'] += 1
            add_log(f"✅ [FB] تم الإرسال: {text[:50]}")
            return True
        add_log(f"❌ [FB] فشل {r.status_code}: {r.text[:150]}")
        return False
    except Exception as e:
        add_log(f"❌ [FB] استثناء: {e}")
        return False

# ========================================================================
# 8. الجلسات
# ========================================================================
def get_session(sender_id):
    sid = str(sender_id)
    if sid not in _ram_cache['sessions']:
        print(f"🆕 [SESSION] إنشاء جلسة جديدة لـ {sid[:12]}...")
        _ram_cache['sessions'][sid] = {
            'name': '', 'service': '', 'budget': 0, 'budget_range': '',
            'phone': '', 'duration': '', 'details': '', 'stage': 'explore',
            'conversation': [],
        }
    return _ram_cache['sessions'][sid]

def add_to_conversation(sender_id, role, message):
    sess = get_session(sender_id)
    sess['conversation'].append(f"{role}: {message}")
    if len(sess['conversation']) > 15:
        sess['conversation'] = sess['conversation'][-15:]

# ========================================================================
# 9. استخراج البيانات
# ========================================================================
def extract_phone(text):
    patterns = [
        r'(\+213[567][0-9]{8})', r'(0[567][0-9]{8})',
        r'(\+966[0-9]{9})', r'(05[0-9]{8})',
        r'(\+[1-9][0-9]{7,14})', r'([0-9]{10,13})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None

def extract_name_from_text(text):
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

def is_price_confirmation(text):
    confirmations = ['نعم', 'موافق', 'تمام', 'اوكي', 'اوك', 'ok', 'yes', 'موافقة', 'ماشي', 'اتفقنا', 'ممتاز']
    return any(w in text.lower() for w in confirmations)

# ========================================================================
# 10. حفظ الطلب في MongoDB
# ========================================================================
def save_order_to_mongo(order_data):
    col = get_mongo_collection()
    if col is None:
        add_log("⚠️ [MONGO] غير متاح — الطلب لن يُحفظ")
        return None
    try:
        doc = {
            'id': f"ORD-{int(time.time() * 1000)}",
            'source_page_id': PAGE_ID,
            'source_page_name': PAGE_NAME,
            'channel': 'messenger',
            'sender_id': order_data.get('sender_id', ''),
            'fullName': order_data.get('name', ''),
            'phone': order_data.get('phone', ''),
            'service': order_data.get('service', ''),
            'projectName': order_data.get('project_name', ''),
            'projectDetails': order_data.get('details', ''),
            'budget': order_data.get('budget', 0),
            'budgetRange': order_data.get('budget_range', ''),
            'duration': order_data.get('duration', ''),
            'status': 'pending',
            'isNew': True,
            'createdAt': datetime.now(timezone.utc).isoformat(),
        }
        add_log(f"💾 [MONGO] حفظ طلب جديد لـ {order_data.get('name', '?')}...")
        result = col.insert_one(doc)
        add_log(f"✅ [MONGO] طلب محفوظ: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        add_log(f"❌ [MONGO] فشل الحفظ: {e}")
        return None

# ========================================================================
# 11. معالجة الرسائل
# ========================================================================
def process_message(sender_id, text):
    sender_id = str(sender_id)
    _ram_cache['stats']['msgs_received'] += 1

    print("=" * 70)
    print(f"📨 [MSG] رسالة جديدة من {sender_id[:15]}...")
    print(f"📝 [MSG] المحتوى: {text}")
    print("=" * 70)

    sess = get_session(sender_id)
    add_to_conversation(sender_id, 'المستخدم', text)
    stage = sess.get('stage', 'explore')
    print(f"🎯 [STAGE] المرحلة الحالية: {stage}")

    # ---- المدير ----
    if sender_id == str(OWNER_FB_ID):
        print(f"👑 [OWNER] المرسل هو المدير — استخدام OWNER_PERSONALITY")
        reply = ask_ai(text, sess, personality=OWNER_PERSONALITY)
        print(f"💬 [REPLY] جاري الإرسال: {reply[:80]}...")
        send_fb(sender_id, reply)
        add_to_conversation(sender_id, 'الوكيل', reply)
        return

    # ---- كلمة السر ----
    if re.search(r'كلمة\s*[Ss]ر|password', text.lower()):
        print(f"🔐 [AUTH] طلب كلمة سر — معطلة حالياً")
        send_fb(sender_id, "هذه الخاصية معطلة. تواصل مع المدير.")
        return

    # ---- explore ----
    if stage == 'explore':
        print(f"🔍 [STAGE:explore] استشارة AI...")
        reply = ask_ai(text, sess)
        print(f"💬 [REPLY] {reply[:80]}...")

        price_match = re.search(r'(\d{2,5})\s*[-–]\s*(\d{2,5})\s*\$', reply)
        single_price = re.search(r'(\d{3,5})\s*\$', reply)
        if price_match:
            sess['budget_range'] = f"{price_match.group(1)}-{price_match.group(2)}"
            sess['budget'] = int(price_match.group(1))
            sess['stage'] = 'price_proposed'
            print(f"💰 [PRICE] تم اكتشاف سعر: {sess['budget_range']} → المرحلة: price_proposed")
        elif single_price:
            sess['budget'] = int(single_price.group(1))
            sess['stage'] = 'price_proposed'
            print(f"💰 [PRICE] تم اكتشاف سعر: {sess['budget']}$ → المرحلة: price_proposed")

        duration_match = re.search(r'(\d+[-–]\d+\s*(?:يوم|أيام|day|days|ساعة))', reply, re.I)
        if duration_match:
            sess['duration'] = duration_match.group(1)
            print(f"⏱️ [DURATION] {sess['duration']}")

        send_fb(sender_id, reply)
        add_to_conversation(sender_id, 'الوكيل', reply)
        return

    # ---- price_proposed ----
    if stage == 'price_proposed':
        if is_price_confirmation(text):
            print(f"✅ [CONFIRM] العميل وافق → المرحلة: collecting_name")
            sess['stage'] = 'collecting_name'
            send_fb(sender_id, "ممتاز! ما اسمك الكريم؟")
        else:
            print(f"💭 [STAGE:price_proposed] العميل يستفسر — استشارة AI...")
            reply = ask_ai(text, sess, extra_instruction="العميل يستفسر. أجبه باختصار.")
            send_fb(sender_id, reply)
            add_to_conversation(sender_id, 'الوكيل', reply)
        return

    # ---- collecting_name ----
    if stage == 'collecting_name':
        print(f"📛 [STAGE:collecting_name] محاولة استخراج الاسم...")
        name = extract_name_from_text(text)
        if not name and len(text.split()) <= 4 and len(text) <= 30:
            name = text.strip()
        if name:
            sess['name'] = name
            sess['stage'] = 'collecting_phone'
            print(f"✅ [NAME] تم استخراج: {name} → المرحلة: collecting_phone")
            send_fb(sender_id, f"تمام {name}، ما رقم هاتفك؟")
        else:
            print(f"⚠️ [NAME] لم يتم استخراج اسم صالح")
            send_fb(sender_id, "ما اسمك الكريم؟")
        return

    # ---- collecting_phone ----
    if stage == 'collecting_phone':
        print(f"📞 [STAGE:collecting_phone] محاولة استخراج رقم الهاتف...")
        phone = extract_phone(text)
        if phone:
            sess['phone'] = phone
            print(f"✅ [PHONE] {phone}")
            order_data = {
                'name': sess['name'], 'phone': phone,
                'service': sess.get('service', 'خدمة تقنية'),
                'budget': sess.get('budget', 0),
                'budget_range': sess.get('budget_range', ''),
                'duration': sess.get('duration', ''),
                'details': sess.get('details', ''),
                'sender_id': sender_id,
                'project_name': '',
            }
            save_order_to_mongo(order_data)
            confirm_msg = (
                f"شكراً {sess['name']}! تم تسجيل طلبك بنجاح 👌\n"
                f"سيتواصل معك فريقنا قريباً."
            )
            send_fb(sender_id, confirm_msg)
            print(f"🔄 [RESET] إعادة تعيين الجلسة")
            _ram_cache['sessions'][sender_id] = {
                'name': '', 'service': '', 'budget': 0, 'budget_range': '',
                'phone': '', 'duration': '', 'details': '', 'stage': 'explore',
                'conversation': [],
            }
        else:
            print(f"⚠️ [PHONE] لم يتم استخراج رقم صالح")
            send_fb(sender_id, "أرسل رقم هاتفك فقط (مثال: 0555123456)")
        return

    # ---- fallback ----
    print(f"🔄 [FALLBACK] مرحلة غير معروفة — استشارة AI...")
    reply = ask_ai(text, sess)
    send_fb(sender_id, reply)
    add_to_conversation(sender_id, 'الوكيل', reply)

# ========================================================================
# 12. Webhook
# ========================================================================
@app.route('/webhook', methods=['GET'])
def verify():
    print(f"🔍 [WEBHOOK GET] التحقق من webhook...")
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if token == VERIFY_TOKEN:
        print(f"✅ [WEBHOOK GET] تم التحقق بنجاح")
        return challenge
    print(f"❌ [WEBHOOK GET] فشل التحقق — token: {token}")
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    body = request.json
    print("=" * 70)
    print(f"📥 [WEBHOOK POST] استُلم حدث جديد")
    print(f"📦 [BODY] {json.dumps(body, ensure_ascii=False)[:500]}")
    print("=" * 70)

    if not body or body.get('object') != 'page':
        print(f"⚠️ [WEBHOOK] object ليس page — تم التجاهل")
        return 'OK', 200

    for entry in body.get('entry', []):
        for msg in entry.get('messaging', []):
            sender = str(msg.get('sender', {}).get('id', ''))
            message = msg.get('message', {})

            # رسالة نصية
            if 'text' in message:
                print(f"📨 [TEXT] من {sender[:12]}: {message['text'][:80]}")
                threading.Thread(
                    target=process_message,
                    args=(sender, message['text']),
                    daemon=True
                ).start()
                continue

            # postback (أزرار)
            if 'postback' in msg:
                print(f"🔘 [POSTBACK] من {sender[:12]}: {msg['postback'].get('payload', '')}")
                continue

            # echo (رسالة أرسلتها الصفحة)
            if message.get('is_echo'):
                print(f"🔁 [ECHO] رسالة صادرة — تم التجاهل")
                continue

            # delivery
            if 'delivery' in msg:
                print(f"✓ [DELIVERY] إشعار تسليم من {sender[:12]}")
                continue

            # read
            if 'read' in msg:
                print(f"👁️ [READ] إشعار قراءة من {sender[:12]}")
                continue

            # غير معروف
            print(f"❓ [UNKNOWN] نوع رسالة غير معروف: {json.dumps(msg, ensure_ascii=False)[:200]}")

    return 'OK', 200

# ========================================================================
# 13. API
# ========================================================================
@app.route('/api/orders', methods=['GET'])
def api_orders():
    col = get_mongo_collection()
    if col is None:
        return jsonify([])
    orders = list(col.find().sort('createdAt', -1).limit(100))
    for o in orders:
        o['_id'] = str(o['_id'])
    return jsonify(orders)

@app.route('/api/clients', methods=['GET'])
def api_clients():
    col = get_mongo_collection()
    if col is None:
        return jsonify([])
    orders = list(col.find().sort('createdAt', -1))
    clients_map = {}
    for o in orders:
        sid = o.get('sender_id', '')
        if not sid or sid in clients_map:
            continue
        clients_map[sid] = {
            'id': sid,
            'name': o.get('fullName', ''),
            'phone': o.get('phone', ''),
            'source': 'online',
            'status': o.get('status', 'pending'),
            'order': {
                'service': o.get('service', ''),
                'project_name': o.get('projectName', ''),
                'project_details': o.get('projectDetails', ''),
            },
        }
    return jsonify(list(clients_map.values()))

@app.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    col = get_mongo_collection()
    total = 0
    completed = 0
    pending = 0
    if col is not None:
        total = col.count_documents({})
        completed = col.count_documents({'status': 'completed'})
        pending = col.count_documents({'status': 'pending'})
    return jsonify({'total_orders': total, 'completed': completed, 'pending': pending})

@app.route('/api/logs', methods=['GET'])
def api_logs():
    return jsonify(list(logs)[:50])

@app.route('/health')
def health():
    col = get_mongo_collection()
    return jsonify({'status': 'ok', 'mongo': col is not None})

# ========================================================================
# 14. Keep-Alive
# ========================================================================
def keep_alive_loop():
    while True:
        time.sleep(300)
        try:
            requests.get(SELF_URL, timeout=8)
        except Exception as e:
            print(f"⚠️ [KEEP-ALIVE] {e}")

# ========================================================================
# 15. التشغيل
# ========================================================================
if __name__ == '__main__':
    print("=" * 70)
    print("🚀 B.Y PRO Marketing Agent - Render")
    print("=" * 70)
    print(f"👤 Owner ID: {OWNER_FB_ID}")
    print(f"📄 Page ID: {PAGE_ID}")
    print(f"🤖 AI Model: {OPENROUTER_MODEL}")
    _col = get_mongo_collection()
    print(f"🗄️ MongoDB: {'متصل' if _col is not None else 'غير متصل'}")
    print("=" * 70 + "\n")
    threading.Thread(target=keep_alive_loop, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
