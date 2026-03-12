import os
import re
import json
import requests
import time
import threading
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from datetime import datetime
from collections import deque

app = Flask(__name__)

# ========== المتغيرات البيئية ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN      = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_ID       = os.environ.get('OWNER_FB_ID', '61580260328404')
OWNER_THREAD_ID   = os.environ.get('OWNER_THREAD_ID', '1319343656265410')
OWNER_PASSWORD    = os.environ.get('OWNER_PASSWORD', '20070909')
BIN_ID            = os.environ.get('BIN_ID')
X_MASTER_KEY      = os.environ.get('X_MASTER_KEY')
X_ACCESS_KEY      = os.environ.get('X_ACCESS_KEY')
BINANCE_ID        = os.environ.get('BINANCE_ID', '1074084246')
AI_API_URL        = os.environ.get('AI_API_URL', 'http://fi8.bot-hosting.net:20163/elos-gemina')
COMPANY_WEBSITE   = os.environ.get('COMPANY_WEBSITE', 'https://b.y-pro.kesug.com')
FB_PAGE_URL       = os.environ.get('FB_PAGE_URL', 'https://www.facebook.com/bypro2007')
STORE_URL         = os.environ.get('STORE_URL', 'https://store-pro.great-site.net')
STORE_SUPPORT     = os.environ.get('STORE_SUPPORT', 'https://t.me/STOREPROSPRT')
SELF_URL          = os.environ.get('SELF_URL', 'https://by-pro-marketing-agent.onrender.com')

# ========== شخصية البوت - للعملاء ==========
BOT_PERSONALITY = """أنت "أحمد"، وكيل تسويق خدمات شركة B.Y PRO للتكنولوجيا والبرمجيات.

شخصيتك:
- تتحدث كإنسان حقيقي، بأسلوب ودود ومريح، وليس كبوت آلي.
- مختصر ومباشر، لا تطوّل بدون داعٍ.
- تفهم احتياج العميل قبل أي شيء.
- لا تبدأ ردودك بـ "أهلاً وسهلاً" في كل رسالة، تكلّم بشكل طبيعي.

طريقة عملك مع العميل:
1. اسمع طلبه باختصار.
2. اسأله أسئلة بسيطة تساعدك تفهم المشروع (1-2 سؤال فقط، مش أكثر).
3. بعد ما فهمت المشروع، قدّم له السعر التقريبي والمدة مباشرة وبوضوح.
4. إذا وافق، اطلب منه اسمه الكريم ورقم هاتفه لتسجيل الطلب.
5. لا تطلب أي بيانات شخصية قبل الاتفاق على السعر.

قواعد أساسية:
- لا تكرر نفسك.
- لا تظهر كبوت أبداً.
- أجب بنفس لغة العميل (عربي أو إنجليزي أو فرنسي).
- إذا سألك عن شيء تقني خارج نطاقك، قل له "أحوّلك للفريق التقني".

الخدمات والأسعار التقريبية (استخدمها كمرجع فقط، السعر الفعلي يتحدد حسب التفاصيل):
- موقع ويب عادي: 300-800$ (5-10 أيام)
- متجر إلكتروني: 700-1800$ (15-25 يوم)
- بوت ذكاء اصطناعي: 500-2000$ (حسب التعقيد)
- تطبيق جوال: من 1500$ (30-60 يوم)
- تصميم جرافيك / شعار: 50-200$ (24-72 ساعة)
- برنامج مخصص: من 1000$ (حسب المشروع)
- متجر برامج ومشاريع: من 1$ للمشروع المجاني / 3$ للمشروع المدفوع — رابط المتجر: https://store-pro.great-site.net

روابط الشركة:
- صفحة فيسبوك: https://www.facebook.com/bypro2007
- الموقع الرسمي: https://b.y-pro.kesug.com
- المتجر: https://store-pro.great-site.net
- دعم المتجر: https://t.me/STOREPROSPRT

طريقة الدفع: 30% مقدماً، 70% بعد التسليم، عبر USDT (Binance Pay) معرف: 1074084246

مهم جداً: لا تسجّل الطلب ولا تطلب البيانات إلا بعد أن يوافق العميل صراحةً على السعر والمدة."""

# ========== برومبت المدير ==========
OWNER_PERSONALITY = """أنت "أحمد"، وكيل تسويق خدمات شركة B.Y PRO للتكنولوجيا والبرمجيات.

الشخص الذي تتحدث معه الآن هو المدير العام للشركة:
الاسم: ياسين بن مقران (Yacine Ben Mokrane)
معرف فيسبوك: 61580260328404
رابط الصفحة الشخصية: https://www.facebook.com/profile.php?id=61580260328404
الصفة: مؤسس ومدير شركة B.Y PRO — هو صاحبك ومديرك المباشر.

قواعد التعامل مع المدير ياسين:
- ناده دائماً بـ "سيدي المدير" أو "سيدي ياسين"
- تعامل معه باحترام كامل وأسلوب مهني راقٍ
- هو مديرك وليس عميلاً — لا تعرض عليه خدمات أبداً
- لا تسأله عن مشاريع أو ميزانيات أو بيانات شخصية
- لا تطلب منه اسمه أو هاتفه — أنت تعرفه مسبقاً
- ردودك معه مختصرة ومباشرة وتخص إدارة البوت والشركة فقط
- إذا سألك عن إحصائيات أو طلبات أو عملاء، قدّم المعلومات بشكل منظم وواضح
- أجبه بنفس اللغة التي يكتب بها (عربي أو إنجليزي أو فرنسي)
- لا تبدأ كل رد بـ "سيدي المدير" — استخدمها بشكل طبيعي وليس في كل جملة"""


# ========== برومبت الردود على التعليقات ==========
COMMENT_PERSONALITY = """أنت "أحمد"، وكيل تسويق شركة B.Y PRO للتكنولوجيا والبرمجيات.

مهمتك: الرد على تعليقات المتابعين على منشورات الصفحة.

قواعد الرد:
- خاطب المعلق باسمه دائماً في بداية الرد
- ردودك قصيرة ومشجعة (2-4 أسطر فقط)
- إذا كان التعليق سؤالاً تقنياً أو طلب خدمة → اقترح عليه التواصل عبر الماسنجر
- إذا كان إطراءً أو تشجيعاً → اشكره وأضف جملة تسويقية خفيفة
- إذا كان استفساراً عن أسعار → أعطه نطاق سعري مختصر وادعه للماسنجر
- لا تبدو كبوت — تكلم بشكل طبيعي وودي
- أجب بنفس لغة التعليق (عربي أو إنجليزي أو فرنسي)
- لا تضع هاشتاقات في الردود"""

# ========== نص المنشور الافتراضي ==========
DEFAULT_POST_TEXT = """🚀 B.Y PRO | حلول تقنية متكاملة تقود أعمالك نحو الريادة

✨ نحن لا نبني مجرد برمجيات، بل نصمم أدوات ذكية تضاعف نمو أعمالك وتضمن تفوقك المستمر.

━━━━━━━━━━━━━━━━━━━━━━
💼 حلولنا الاحترافية (جودة عالمية وتنفيذ متقن):
━━━━━━━━━━━━━━━━━━━━━━

🌐 المنصات الرقمية
تطوير مواقع إلكترونية فائقة السرعة، متجاوبة، ومجهزة تقنياً لتصدر نتائج البحث (SEO).

📱 تطبيقات الجوال
تجربة مستخدم (UX) استثنائية على iOS وAndroid تجمع بين الأناقة وسلاسة الأداء.

☁️ الأنظمة السحابية المخصصة
تطوير أنظمة (ERP - CRM) وأتمتة العمليات لرفع كفاءة فريقك بنسبة 100%.

🤖 تقنيات الذكاء الاصطناعي
دمج Chatbots ذكية، تحليل بيانات تنبؤي، وصناعة محتوى آلي متقدم.

🎨 الهوية البصرية
صياغة بصمة بصرية فريدة (Logo & Branding) تعكس قيم مشروعك وتجذب عملاءك.

🎬 المحتوى المرئي
مونتاج فيديو تسويقي وصناعة محتوى يروي قصة نجاحك بأسلوب احترافي.

📈 استراتيجيات النمو الرقمي
بناء مجتمعات حقيقية وتفاعل مستهدف يحوّل المتابعين إلى عملاء.

🛡️ الاستشارات والدعم
مرافقة تقنية مستمرة 24/7 لضمان استقرار وتطور أعمالك دون توقف.

━━━━━━━━━━━━━━━━━━━━━━
🏆 لماذا يثق رواد الأعمال في B.Y PRO؟
━━━━━━━━━━━━━━━━━━━━━━

1️⃣ الابتكار المستدام — أحدث التقنيات لضمان بقاء مشروعك في الصدارة دائماً
2️⃣ الالتزام المطلق — التسليم في الموعد المحدد هو ميثاقنا
3️⃣ عائد الاستثمار (ROI) — حلولنا مصممة لزيادة المبيعات وتقليل التكاليف
4️⃣ مرونة فائقة — خطط دفع ميسرة تناسب الشركات الناشئة والمؤسسات الكبرى

━━━━━━━━━━━━━━━━━━━━━━
⚡ مستقبل أعمالك يبدأ بقرار الآن!
━━━━━━━━━━━━━━━━━━━━━━

لا تترك المنافس يسبقك 👇
📩 راسلنا الآن ونبدأ فوراً!

#BY_PRO #تحول_رقمي #ذكاء_اصطناعي #برمجة #تسويق_رقمي #ريادة_الأعمال #تطوير_مواقع"""
def jsonbin_read():
    if not BIN_ID or not X_MASTER_KEY:
        return {}
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {'X-Master-Key': X_MASTER_KEY}
    if X_ACCESS_KEY:
        headers['X-Access-Key'] = X_ACCESS_KEY
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            record = resp.json().get('record', {})
            if not isinstance(record, dict):
                return {}
            return record
        else:
            print(f"JSONBin read error: {resp.status_code} - {resp.text[:200]}")
            return {}
    except Exception as e:
        print(f"JSONBin read exception: {e}")
        return {}

def jsonbin_write(d):
    if not BIN_ID or not X_MASTER_KEY:
        return False
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': X_MASTER_KEY
    }
    if X_ACCESS_KEY:
        headers['X-Access-Key'] = X_ACCESS_KEY
    try:
        resp = requests.put(url, json=d, headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"JSONBin write exception: {e}")
        return False

# ========== هيكل البيانات الأساسي ==========
DEFAULT_DATA = {
    'orders': [],
    'blocked': [],
    'verified': [],
    'sessions': {},
    'order_notes': {},
    'stats': {
        'msgs_received': 0,
        'msgs_sent': 0,
        'start_time': datetime.now().isoformat()
    },
    # إعدادات التعليقات والنشر
    'comment_replied_ids': [],      # IDs التعليقات التي تم الرد عليها
    'comment_stats': {},            # إحصائيات التعليقات اليومية
    'comment_log': [],              # سجل التعليقات والردود
    'publish_settings': {
        'enabled': False,
        'interval_minutes': 60,
        'post_text': '',
        'add_chat_button': True,
        'last_published': ''
    },
    'comment_settings': {
        'enabled': False,
        'prompt': '',
        'check_interval_minutes': 5
    }
}

# تحميل البيانات
loaded_data = jsonbin_read()
if loaded_data:
    data = DEFAULT_DATA.copy()
    for key in DEFAULT_DATA:
        if key in loaded_data:
            data[key] = loaded_data[key]
        else:
            data[key] = DEFAULT_DATA[key]
else:
    data = {k: v.copy() if isinstance(v, (dict, list)) else v for k, v in DEFAULT_DATA.items()}
    jsonbin_write(data)

# ========== سجل الأحداث المحلي ==========
logs = deque(maxlen=100)

def add_log(msg):
    logs.appendleft({'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg})
    print(f"[{logs[0]['time']}] {msg}")

# ========== دوال فيسبوك ==========
def send_fb(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        add_log("❌ PAGE_ACCESS_TOKEN غير موجود")
        return False
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            data['stats']['msgs_sent'] += 1
            add_log(f"📤 إلى {str(recipient_id)[:10]}...: {text[:50]}")
            return True
        else:
            add_log(f"❌ فشل الإرسال: {r.status_code} - {r.text[:100]}")
            return False
    except Exception as e:
        add_log(f"❌ خطأ في الإرسال: {e}")
        return False

# ========== حفظ البيانات ==========
_save_lock = threading.Lock()

def save_data():
    with _save_lock:
        success = jsonbin_write(data)
        if success:
            add_log("💾 تم الحفظ")
        else:
            add_log("⚠️ فشل الحفظ في JSONBin")
        return success

# ========== التحقق من المدير ==========
def is_owner(sender_id):
    """المدير الحقيقي هو صاحب الـ OWNER_FB_ID فقط - لا أحد غيره"""
    return str(sender_id) == str(OWNER_FB_ID)

def is_verified_admin(sender_id):
    """المدراء المضافون بكلمة المرور"""
    return str(sender_id) in [str(v) for v in data.get('verified', [])]

# ========== دوال الإحصائيات ==========
def get_live_stats():
    today = datetime.now().strftime('%Y-%m-%d')
    orders_list = data.get('orders', [])
    today_orders = [o for o in orders_list if o.get('timestamp', '').startswith(today)]
    unique_clients = len(set(o.get('sender_id', '') for o in orders_list if o.get('sender_id')))
    return {
        'unique_clients': unique_clients,
        'total_orders': len(orders_list),
        'today_orders': len(today_orders),
        'today_orders_list': today_orders[-10:],
        'blocked': len(data.get('blocked', [])),
        'verified': len(data.get('verified', [])),
        'msgs_received': data['stats']['msgs_received'],
        'msgs_sent': data['stats']['msgs_sent']
    }

# ========== إدارة الطلبات ==========
def add_order(order_dict):
    if 'orders' not in data:
        data['orders'] = []
    order_dict['id'] = len(data['orders']) + 1
    data['orders'].append(order_dict)
    save_data()
    add_log(f"✅ طلب جديد #{order_dict['id']} - {order_dict['name']} - {order_dict['service']} - {order_dict.get('budget','؟')}$")

    stats = get_live_stats()
    notify_msg = (
        f"🔔 طلب جديد #{order_dict['id']}\n"
        f"الاسم: {order_dict['name']}\n"
        f"الخدمة: {order_dict['service']}\n"
        f"الميزانية المتفق عليها: {order_dict.get('budget','؟')}$\n"
        f"رقم الجوال: {order_dict.get('phone', 'غير متوفر')}\n"
        f"المدة: {order_dict.get('duration', 'غير محددة')}\n"
        f"التفاصيل: {order_dict.get('details', '')[:150]}\n"
        f"إجمالي الطلبات: {stats['total_orders']} | اليوم: {stats['today_orders']}\n"
        f"محادثة: {order_dict['link']}"
    )
    send_fb(OWNER_FB_ID, notify_msg)
    return order_dict['id']

def get_order(order_id):
    for o in data.get('orders', []):
        if o['id'] == order_id:
            return o
    return None

def update_order(order_id, updates):
    for o in data.get('orders', []):
        if o['id'] == order_id:
            o.update(updates)
            save_data()
            return True
    return False

def delete_order(order_id):
    if 'orders' in data:
        data['orders'] = [o for o in data['orders'] if o['id'] != order_id]
        save_data()
        add_log(f"🗑️ حذف طلب #{order_id}")

def add_note_to_order(order_id, note):
    if 'order_notes' not in data:
        data['order_notes'] = {}
    data['order_notes'][str(order_id)] = note
    save_data()

# ========== إدارة الجلسات ==========
def get_session(sender_id):
    sid = str(sender_id)
    if 'sessions' not in data:
        data['sessions'] = {}
    if sid not in data['sessions']:
        data['sessions'][sid] = {
            'name': '',
            'service': '',
            'budget': 0,
            'budget_range': '',
            'phone': '',
            'duration': '',
            'details': '',
            'stage': 'explore',  # explore -> price_proposed -> awaiting_confirmation -> collecting_data -> done
            'conversation': [],
            'awaiting_password': False,
        }
    return data['sessions'][sid]

def update_session(sender_id, updates):
    sid = str(sender_id)
    if 'sessions' in data and sid in data['sessions']:
        data['sessions'][sid].update(updates)

def add_to_conversation(sender_id, role, message):
    sid = str(sender_id)
    sess = get_session(sid)
    sess['conversation'].append(f"{role}: {message}")
    if len(sess['conversation']) > 15:
        sess['conversation'] = sess['conversation'][-15:]

def reset_session(sender_id):
    sid = str(sender_id)
    if 'sessions' in data and sid in data['sessions']:
        old_conv = data['sessions'][sid].get('conversation', [])[-3:]
        data['sessions'][sid] = {
            'name': '',
            'service': '',
            'budget': 0,
            'budget_range': '',
            'phone': '',
            'duration': '',
            'details': '',
            'stage': 'explore',
            'conversation': old_conv,
            'awaiting_password': False,
        }

# ========== استخراج البيانات من النص ==========
def extract_phone(text):
    """استخراج رقم الهاتف من النص"""
    patterns = [
        r'(\+213[567][0-9]{8})',      # جزائر +213
        r'(00213[567][0-9]{8})',       # جزائر 00213
        r'(0[567][0-9]{8})',           # جزائر محلي
        r'(\+966[0-9]{9})',            # سعودية
        r'(05[0-9]{8})',               # سعودية محلي
        r'(\+212[0-9]{9})',            # مغرب
        r'(\+216[0-9]{8})',            # تونس
        r'(\+20[0-9]{10})',            # مصر
        r'(\+[1-9][0-9]{7,14})',       # أي رقم دولي
        r'([0-9]{10,13})',             # أي رقم طويل
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None

def extract_name_from_text(text):
    """استخراج الاسم من النص"""
    patterns = [
        r'اسمي[:\s]*([\u0600-\u06FF\s]{3,30})',
        r'الاسم[:\s]*([\u0600-\u06FF\s]{3,30})',
        r'انا[:\s]*([\u0600-\u06FF]{3,20})',
        r'my name is[:\s]*([a-zA-Z\s]{3,30})',
        r'i\'?m[:\s]*([a-zA-Z\s]{3,25})',
        r'name[:\s]*([a-zA-Z\s]{3,30})',
        r'يسمونني[:\s]*([\u0600-\u06FF\s]{3,20})',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            name = m.group(1).strip()
            # تأكد أنه اسم وليس جملة طويلة
            if 2 <= len(name.split()) <= 4 and len(name) <= 30:
                return name
    return None

def is_price_confirmation(text):
    """هل وافق العميل على السعر؟"""
    confirmations = [
        'نعم', 'موافق', 'موافقة', 'تمام', 'تمام شكراً', 'اوكي', 'اوك', 'ok', 'yes', 
        'okay', 'agreed', 'deal', 'ماشي', 'راني موافق', 'حسنا', 'يلا نبدأ', 
        'نبدو', 'نبدأ', 'جيد', 'سنبدأ', 'اتفقنا', 'ممتاز', 'بالتوفيق', 'شكراً',
        'اشتري', 'مشينا'
    ]
    text_clean = text.lower().strip()
    return any(w in text_clean for w in confirmations)

def is_price_rejection(text):
    """هل رفض العميل السعر؟"""
    rejections = ['لا', 'غالي', 'كثير', 'خصم', 'أرخص', 'يخفض', 'مو مناسب', 'no', 'too much', 'expensive']
    text_clean = text.lower().strip()
    return any(w in text_clean for w in rejections)

# ========== الذكاء الاصطناعي ==========
def ask_ai(user_msg, sess, extra_instruction="", personality=None):
    context = "\n".join(sess.get('conversation', [])[-12:])
    
    stage_hints = {
        'explore': "أنت تستمع لطلب العميل وتفهم احتياجه. اسأل سؤالاً أو سؤالين بسيطين لتفهم المشروع، ثم قدّم له السعر والمدة.",
        'price_proposed': "لقد اقترحت سعراً للعميل. انتظر موافقته. لا تضيف معلومات جديدة.",
        'awaiting_confirmation': "العميل على وشك الموافقة أو الرفض. إذا وافق، اطلب اسمه الكريم فقط.",
        'collecting_name': "اطلب من العميل اسمه الكريم فقط. رسالة واحدة مختصرة.",
        'collecting_phone': f"اسم العميل هو: {sess.get('name', '')}. اطلب منه رقم هاتفه الآن. رسالة مختصرة.",
    }
    
    # اختر الشخصية المناسبة
    active_personality = personality or BOT_PERSONALITY
    
    stage = sess.get('stage', 'explore')
    hint = stage_hints.get(stage, "")
    
    full_prompt = (
        f"{active_personality}\n\n"
        f"[حالة المحادثة الحالية: {hint}]\n"
        f"{extra_instruction}\n\n"
        f"سجل المحادثة:\n{context}\n\n"
        f"المستخدم: {user_msg}\n"
        f"أحمد:"
    )
    
    try:
        url = f'{AI_API_URL}?text={requests.utils.quote(full_prompt)}'
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            resp = r.json()
            answer = resp.get('response', '').strip()
            if answer:
                return answer[:1800]
    except Exception as e:
        add_log(f"❌ خطأ AI: {e}")
    
    return "عذراً، حدث خطأ تقني مؤقت. حاول مرة أخرى."

# ========== معالجة أوامر المدير ==========
def handle_owner_command(sender_id, text):
    """معالجة أوامر المدير — يتعرف على اللغة الطبيعية ويمنع الـ AI من اختراع بيانات"""
    t = text.lower().strip()
    stats = get_live_stats()

    # ====== إحصائيات (يتعرف على أي صياغة) ======
    if any(k in t for k in [
        'احصائيات', 'إحصائيات', 'statistics', 'stats',
        'احصاء', 'الأرقام', 'الارقام', 'ارقام', 'نظرة عامة',
        'اليوم كيف', 'كيف اليوم', 'ما الجديد', 'ما جديد',
        'وضع', 'الوضع', 'ايش صاير', 'شو صاير', 'كيف الامور',
        'كيف الأمور', 'اعطني احصائيات', 'اعطني الاحصائيات',
        'اعطني إحصائيات', 'احصائيات اليوم', 'تقرير'
    ]):
        completed = len([o for o in data.get('orders', []) if o.get('status') == 'مكتمل'])
        pending = stats['total_orders'] - completed
        msg = (
            f"📊 إحصائيات B.Y PRO\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📦 إجمالي الطلبات: {stats['total_orders']}\n"
            f"📅 طلبات اليوم: {stats['today_orders']}\n"
            f"✅ مكتملة: {completed}\n"
            f"⏳ معلقة: {pending}\n"
            f"👥 عملاء فريدون: {stats['unique_clients']}\n"
            f"🚫 محظورون: {stats['blocked']}\n"
            f"🔐 مدراء: {stats['verified']}\n"
            f"📨 رسائل واردة: {stats['msgs_received']}\n"
            f"📤 رسائل صادرة: {stats['msgs_sent']}"
        )
        send_fb(sender_id, msg)
        return True

    # ====== طلبات اليوم ======
    if any(k in t for k in ['اي جديد', 'طلبات اليوم', 'الجديد', 'جديد اليوم']):
        if stats['today_orders'] > 0:
            lines = [
                f"#{o['id']} {o['name']} — {o['service']} — {o.get('budget','؟')}$"
                for o in stats['today_orders_list']
            ]
            send_fb(sender_id, f"📦 {stats['today_orders']} طلب اليوم:\n" + "\n".join(lines))
        else:
            send_fb(sender_id, "لا توجد طلبات اليوم.")
        return True

    # ====== كل الطلبات / عرض الطلبات ======
    if any(k in t for k in [
        'كل الطلبات', 'جميع الطلبات', 'all orders', 'الطلبات الموجودة',
        'الطلبات', 'اعرض الطلبات', 'عرض الطلبات', 'كا الطلبات',
        'كل الطلبات', 'قائمة الطلبات', 'اظهر الطلبات', 'شوف الطلبات',
        'طلبات موجودة', 'كم طلب', 'عدد الطلبات'
    ]):
        orders = data.get('orders', [])
        if not orders:
            send_fb(sender_id, "لا توجد طلبات بعد.")
        else:
            show = list(reversed(orders[-15:]))
            lines = [
                f"#{o['id']} {o.get('name','؟')} — {o.get('service','؟')} — "
                f"{o.get('budget','؟')}$ [{o.get('status','جديد')}]"
                for o in show
            ]
            send_fb(sender_id,
                f"📋 الطلبات ({len(orders)} إجمالاً)، آخر {len(show)}:\n" + "\n".join(lines))
        return True

    # ====== تفاصيل طلب بالرقم ======
    m = re.search(r'(?:تفاصيل|تفصيل|طلب)\s*#?\s*(\d+)', text)
    if m:
        oid = int(m.group(1))
        o = get_order(oid)
        if o:
            note = data.get('order_notes', {}).get(str(oid), 'لا يوجد')
            msg = (
                f"📋 تفاصيل الطلب #{oid}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 الاسم: {o['name']}\n"
                f"🛠 الخدمة: {o['service']}\n"
                f"💰 الميزانية: {o.get('budget','؟')}$\n"
                f"📞 الهاتف: {o.get('phone','غير متوفر')}\n"
                f"⏱ المدة: {o.get('duration','غير محددة')}\n"
                f"📝 ملاحظات: {note}\n"
                f"🔖 الحالة: {o.get('status','جديد')}\n"
                f"📅 التاريخ: {o.get('timestamp','')[:16]}\n"
                f"🔗 رابط: {o.get('link','')}"
            )
        else:
            msg = f"❌ لم يُعثر على طلب #{oid}"
        send_fb(sender_id, msg)
        return True

    # ====== حظر مستخدم ======
    m = re.search(r'حظر\s+(\d+)', text)
    if m:
        uid = m.group(1)
        data.setdefault('blocked', [])
        if uid not in data['blocked']:
            data['blocked'].append(uid)
            save_data()
            send_fb(sender_id, f"✅ تم حظر المستخدم {uid}")
        else:
            send_fb(sender_id, "المستخدم محظور مسبقاً.")
        return True

    # ====== إلغاء الحظر ======
    m = re.search(r'(?:الغاء حظر|رفع حظر|فك حظر)\s+(\d+)', text)
    if m:
        uid = m.group(1)
        if uid in data.get('blocked', []):
            data['blocked'].remove(uid)
            save_data()
            send_fb(sender_id, f"✅ تم رفع الحظر عن {uid}")
        else:
            send_fb(sender_id, "المستخدم غير محظور.")
        return True

    # ====== تحديث طلب مكتمل ======
    m = re.search(r'(?:مكتمل|اكتمل|انجز|انتهى)\s+#?(\d+)', text)
    if m:
        oid = int(m.group(1))
        if update_order(oid, {'status': 'مكتمل'}):
            send_fb(sender_id, f"✅ تم تحديث طلب #{oid} إلى مكتمل")
        else:
            send_fb(sender_id, f"❌ لم يُعثر على طلب #{oid}")
        return True

    # ====== حذف طلب ======
    m = re.search(r'حذف\s+#?(\d+)', text)
    if m:
        oid = int(m.group(1))
        delete_order(oid)
        send_fb(sender_id, f"🗑️ تم حذف طلب #{oid}")
        return True

    # ====== ملاحظة على طلب ======
    m = re.search(r'ملاحظة\s+#?(\d+)\s+(.+)', text)
    if m:
        oid = int(m.group(1))
        note = m.group(2).strip()
        add_note_to_order(oid, note)
        send_fb(sender_id, f"📝 تمت إضافة الملاحظة لطلب #{oid}")
        return True

    # ====== قائمة المحظورين ======
    if any(k in t for k in ['المحظورين', 'محظورين', 'المحظورون', 'blocked']):
        blocked = data.get('blocked', [])
        if blocked:
            send_fb(sender_id, f"🚫 المحظورون ({len(blocked)}):\n" + "\n".join(blocked[-15:]))
        else:
            send_fb(sender_id, "لا يوجد مستخدمون محظورون.")
        return True

    # ====== قائمة العملاء ======
    if any(k in t for k in ['العملاء', 'اعرض العملاء', 'clients', 'قائمة العملاء', 'الزبائن']):
        orders = data.get('orders', [])
        clients = {}
        for o in orders:
            name = o.get('name', '')
            if name and name not in clients:
                clients[name] = o.get('phone', '')
        if clients:
            lines = [f"• {n} — {p}" for n, p in list(clients.items())[-15:]]
            send_fb(sender_id, f"👥 العملاء ({len(clients)}):\n" + "\n".join(lines))
        else:
            send_fb(sender_id, "لا يوجد عملاء مسجلون بعد.")
        return True

    # ====== أي سؤال عن أرقام / بيانات = لا يخترع ======
    if any(k in t for k in [
        'طلب', 'order', 'عميل', 'client', 'كم', 'عدد',
        'مبيعات', 'دخل', 'ربح', 'revenue', 'sales'
    ]):
        # أرجع إحصائيات مباشرة بدل تمريرها للـ AI
        completed = len([o for o in data.get('orders', []) if o.get('status') == 'مكتمل'])
        send_fb(sender_id,
            f"📊 ملخص سريع:\n"
            f"الطلبات: {stats['total_orders']} (اليوم: {stats['today_orders']})\n"
            f"مكتملة: {completed} | معلقة: {stats['total_orders']-completed}\n"
            f"عملاء: {stats['unique_clients']}\n"
            f"اكتب 'كل الطلبات' لعرض القائمة الكاملة."
        )
        return True

    return False

# ========== المعالجة الرئيسية للرسائل ==========
def process_message(sender_id, text):
    sender_id = str(sender_id)
    data['stats']['msgs_received'] += 1
    add_log(f"📨 من {sender_id[:12]}: {text[:50]}")

    # تحقق الحظر
    if sender_id in [str(b) for b in data.get('blocked', [])]:
        add_log(f"🚫 محظور: {sender_id[:12]}")
        return

    sess = get_session(sender_id)
    add_to_conversation(sender_id, 'المستخدم', text)

    # ====== المدير الحقيقي (بالـ ID الثابت فقط) ======
    if is_owner(sender_id):
        handled = handle_owner_command(sender_id, text)
        if not handled:
            stats = get_live_stats()
            # استخدم owner_prompt المحفوظ إن وجد، وإلا استخدم OWNER_PERSONALITY الافتراضي
            active_owner_prompt = data.get('owner_prompt') or OWNER_PERSONALITY
            extra = (
                f"\n[إحصائيات سريعة: {stats['today_orders']} طلب اليوم، "
                f"{stats['total_orders']} إجمالاً، {stats['unique_clients']} عميل]"
            )
            reply = ask_ai(text, sess, extra_instruction=extra, personality=active_owner_prompt)
            send_fb(sender_id, reply)
            add_to_conversation(sender_id, 'أحمد', reply)
        save_data()
        return

    # ====== المدراء الموثقون (بكلمة المرور) ======
    if is_verified_admin(sender_id):
        handled = handle_owner_command(sender_id, text)
        if not handled:
            active_owner_prompt = data.get('owner_prompt') or OWNER_PERSONALITY
            reply = ask_ai(text, sess, personality=active_owner_prompt)
            send_fb(sender_id, reply)
            add_to_conversation(sender_id, 'أحمد', reply)
        save_data()
        return

    # ====== انتظار كلمة المرور ======
    if sess.get('awaiting_password'):
        if text.strip() == OWNER_PASSWORD:
            if 'verified' not in data:
                data['verified'] = []
            if sender_id not in data['verified']:
                data['verified'].append(sender_id)
            sess['awaiting_password'] = False
            update_session(sender_id, {'awaiting_password': False})
            save_data()
            add_log(f"🔐 مدير جديد موثق: {sender_id[:12]}")
            send_fb(sender_id, "✅ تم التحقق. أهلاً بك.")
        else:
            send_fb(sender_id, "❌ كلمة المرور غير صحيحة.")
        return

    # ====== طلب كلمة المرور - يُعرض فقط عند الكلمات المحددة ======
    # لا نقبل ادعاءات المدير من مجرد كلام - يجب كلمة السر
    if re.search(r'\bكلمة\s*[Ss]ر\b|password|رمز\s*السر|رمز\s*الدخول', text.lower()):
        sess['awaiting_password'] = True
        update_session(sender_id, {'awaiting_password': True})
        save_data()
        send_fb(sender_id, "أدخل كلمة المرور:")
        return

    # ====== معالجة العميل العادي حسب مرحلة المحادثة ======
    stage = sess.get('stage', 'explore')

    # --- مرحلة: استكشاف / عرض السعر ---
    if stage == 'explore':
        reply = ask_ai(text, sess)
        
        # هل اقترح الذكاء الاصطناعي سعراً؟
        price_match = re.search(r'(\d{2,5})\s*[-–]\s*(\d{2,5})\s*\$', reply)
        single_price = re.search(r'(\d{3,5})\s*\$', reply)
        
        if price_match:
            low = int(price_match.group(1))
            high = int(price_match.group(2))
            sess['budget_range'] = f"{low}-{high}"
            sess['budget'] = low
            
            # استخراج الخدمة من السياق
            if not sess.get('service'):
                service_patterns = [
                    (r'موقع|website|web', 'موقع إلكتروني'),
                    (r'متجر|store|ecommerce', 'متجر إلكتروني'),
                    (r'تطبيق|app|mobile', 'تطبيق جوال'),
                    (r'بوت|bot|chatbot|ذكاء', 'بوت ذكاء اصطناعي'),
                    (r'تصميم|design|شعار|logo', 'تصميم'),
                    (r'برنامج|software|نظام', 'برنامج مخصص'),
                ]
                for pat, svc in service_patterns:
                    if re.search(pat, text + reply, re.I):
                        sess['service'] = svc
                        break
                if not sess.get('service'):
                    sess['service'] = 'خدمة تقنية'
            
            sess['stage'] = 'price_proposed'
            update_session(sender_id, {
                'budget_range': sess['budget_range'],
                'budget': sess['budget'],
                'service': sess['service'],
                'stage': 'price_proposed'
            })
        elif single_price and not sess.get('budget'):
            price = int(single_price.group(1))
            sess['budget'] = price
            sess['stage'] = 'price_proposed'
            update_session(sender_id, {'budget': price, 'stage': 'price_proposed'})
        
        # استخراج مدة من الرد
        duration_match = re.search(r'(\d+[-–]\d+\s*(?:يوم|أيام|يوماً|day|days|ساعة|hours?))', reply, re.I)
        if duration_match and not sess.get('duration'):
            sess['duration'] = duration_match.group(1)
            update_session(sender_id, {'duration': sess['duration']})
        
        send_fb(sender_id, reply)
        add_to_conversation(sender_id, 'أحمد', reply)
        save_data()
        return

    # --- مرحلة: تم اقتراح السعر، ننتظر الموافقة ---
    if stage == 'price_proposed':
        if is_price_confirmation(text):
            # وافق! انتقل لجمع البيانات
            sess['stage'] = 'collecting_name'
            update_session(sender_id, {'stage': 'collecting_name'})
            save_data()
            send_fb(sender_id, "ممتاز! ما اسمك الكريم؟")
            return
        elif is_price_rejection(text):
            # رفض أو طلب تعديل
            sess['stage'] = 'explore'
            update_session(sender_id, {'stage': 'explore', 'budget': 0, 'budget_range': ''})
            reply = ask_ai(text, sess, extra_instruction="\nالعميل يريد تعديلاً في السعر أو لديه استفسار. ناقشه بمرونة.")
            send_fb(sender_id, reply)
            add_to_conversation(sender_id, 'أحمد', reply)
            save_data()
            return
        else:
            # سؤال إضافي قبل الموافقة
            reply = ask_ai(text, sess, extra_instruction="\nالعميل يستفسر. أجبه باختصار ثم ذكّره بالسؤال: هل يوافق على السعر والمدة؟")
            send_fb(sender_id, reply)
            add_to_conversation(sender_id, 'أحمد', reply)
            save_data()
            return

    # --- مرحلة: جمع الاسم ---
    if stage == 'collecting_name':
        # استخراج الاسم من النص
        name = extract_name_from_text(text)
        
        # إذا لم يُستخرج بالنمط، افترض أن النص كله هو الاسم إذا كان قصيراً
        if not name and len(text.split()) <= 4 and len(text) <= 30:
            # تحقق أنه ليس كلمة موافقة أو سؤال
            if not any(w in text.lower() for w in ['نعم', 'لا', 'كيف', 'ماذا', 'متى', 'أين']):
                name = text.strip()
        
        if name:
            sess['name'] = name
            sess['stage'] = 'collecting_phone'
            update_session(sender_id, {'name': name, 'stage': 'collecting_phone'})
            save_data()
            send_fb(sender_id, f"تمام {name}، ما هو رقم هاتفك للتواصل؟")
            return
        else:
            send_fb(sender_id, "ما اسمك الكريم؟ (الاسم فقط من فضلك)")
            return

    # --- مرحلة: جمع رقم الهاتف ---
    if stage == 'collecting_phone':
        phone = extract_phone(text)
        if phone:
            sess['phone'] = phone
            update_session(sender_id, {'phone': phone})
            
            # هل هناك تفاصيل إضافية في النص؟
            # لا، نسجّل الطلب مباشرة
            sess['stage'] = 'done'
            update_session(sender_id, {'stage': 'done'})
            
            # === تسجيل الطلب ===
            order = {
                'name': sess['name'],
                'service': sess.get('service', 'خدمة تقنية'),
                'budget': sess.get('budget', 0),
                'budget_range': sess.get('budget_range', ''),
                'phone': sess['phone'],
                'duration': sess.get('duration', ''),
                'details': sess.get('details', ''),
                'timestamp': datetime.now().isoformat(),
                'sender_id': sender_id,
                'link': f"https://www.facebook.com/messages/t/{sender_id}",
                'status': 'جديد'
            }
            order_id = add_order(order)
            
            # رسالة للعميل طبيعية
            confirm_msg = (
                f"شكراً {sess['name']}! تم تسجيل طلبك بنجاح 👌\n"
                f"سيتواصل معك فريقنا على رقمك قريباً لبدء العمل على {sess.get('service', 'مشروعك')}.\n"
                f"إذا كان لديك أي سؤال في الوقت الحالي، تواصل معنا على: {COMPANY_WEBSITE}"
            )
            send_fb(sender_id, confirm_msg)
            add_log(f"✅ طلب #{order_id} مسجّل كامل لـ {sess['name']}")
            
            # إعادة تعيين الجلسة للطلبات المستقبلية
            reset_session(sender_id)
            save_data()
            return
        else:
            send_fb(sender_id, "أرسل لي رقم هاتفك فقط من فضلك (مثال: 0555123456)")
            return

    # --- أي مرحلة أخرى - إعادة تشغيل ---
    sess['stage'] = 'explore'
    update_session(sender_id, {'stage': 'explore'})
    reply = ask_ai(text, sess)
    send_fb(sender_id, reply)
    add_to_conversation(sender_id, 'أحمد', reply)
    save_data()


# ========== مسارات Flask ==========
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

        # ===== أحداث Feed (تعليقات على المنشورات) =====
        for change in entry.get('changes', []):
            val = change.get('value', {})
            item = val.get('item', '')
            verb = val.get('verb', '')
            # تعليق جديد على منشور الصفحة
            if item == 'comment' and verb == 'add':
                comment_id = val.get('comment_id', '')
                from_info = val.get('from', {})
                commenter_name = from_info.get('name', '')
                commenter_id = from_info.get('id', '')
                comment_text = val.get('message', '')
                post_id = val.get('post_id', '')
                add_log(f"💬 تعليق جديد من {commenter_name or commenter_id}: {comment_text[:50]}")
                if comment_id and comment_text:
                    threading.Thread(
                        target=handle_new_comment,
                        args=(comment_id, commenter_name, commenter_id, comment_text, post_id),
                        daemon=True
                    ).start()

        # ===== رسائل Messenger =====
        for msg in entry.get('messaging', []):
            sender = str(msg['sender']['id'])
            message = msg.get('message', {})

            if message.get('quick_reply'):
                payload = message['quick_reply'].get('payload', '')
                if is_owner(sender) or is_verified_admin(sender):
                    threading.Thread(
                        target=handle_quick_reply_payload,
                        args=(sender, payload), daemon=True
                    ).start()
                continue

            if 'text' in message:
                text = message['text']
                if (is_owner(sender) or is_verified_admin(sender)) and \
                   text.strip().lower() in ['menu', 'قائمة', 'مساعدة', 'help', 'القائمة']:
                    threading.Thread(target=send_owner_menu, args=(sender,), daemon=True).start()
                else:
                    threading.Thread(target=process_message, args=(sender, text), daemon=True).start()

    return 'OK', 200


def handle_new_comment(comment_id, commenter_name, commenter_id, comment_text, post_id):
    """معالجة تعليق جديد فور وصوله عبر Webhook"""
    # تحقق مزدوج — الأول هنا، الثاني داخل reply_to_comment
    replied_ids = set(data.get('comment_replied_ids', []))
    if comment_id in replied_ids:
        add_log(f"⏭️ تعليق مكرر تجاهله: {comment_id[:10]}")
        return

    # جلب نص المنشور
    post_text = ''
    try:
        r = requests.get(
            f'https://graph.facebook.com/v18.0/{post_id}',
            params={'access_token': PAGE_ACCESS_TOKEN, 'fields': 'message'},
            timeout=8
        )
        if r.status_code == 200:
            post_text = r.json().get('message', '')
    except:
        pass

    display_name = commenter_name or 'صديق'
    reply_text = generate_comment_reply(display_name, comment_text, post_text)
    if not reply_text:
        return

    # إضافة @tag إذا كان لدينا ID المعلق
    if commenter_id:
        final_reply = f"@[{commenter_id}] {reply_text}"
    else:
        final_reply = reply_text

    ok = reply_to_comment(comment_id, final_reply)
    if ok:
        replied_ids.add(comment_id)
        data['comment_replied_ids'] = list(replied_ids)[-1000:]
        today = datetime.now().strftime('%Y-%m-%d')
        data.setdefault('comment_stats', {})[today] = data['comment_stats'].get(today, 0) + 1
        data.setdefault('comment_log', []).insert(0, {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'post_id': post_id,
            'post_text': post_text[:100],
            'commenter': display_name,
            'comment': comment_text[:200],
            'reply': final_reply[:200]
        })
        data['comment_log'] = data['comment_log'][:200]
        save_data()
        add_log(f"✅ رد على {display_name}: {comment_text[:30]}")

# ========== لوحة التحكم ==========
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

# ========== API: Dashboard ==========
@app.route('/api/dashboard')
def api_dashboard():
    from datetime import timedelta
    stats = get_live_stats()
    orders = data.get('orders', [])
    daily = {}
    for i in range(13, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        daily[day] = 0
    for o in orders:
        ts = o.get('timestamp', '')[:10]
        if ts in daily:
            daily[ts] += 1
    cats = {'Web': 0, 'Store': 0, 'Apps': 0, 'Bots': 0, 'Design': 0, 'Software': 0, 'Other': 0}
    for o in orders:
        svc = o.get('service', '').lower()
        if any(k in svc for k in ['موقع', 'web', 'site']): cats['Web'] += 1
        elif any(k in svc for k in ['متجر', 'store', 'ecommerce']): cats['Store'] += 1
        elif any(k in svc for k in ['تطبيق', 'app', 'mobile']): cats['Apps'] += 1
        elif any(k in svc for k in ['بوت', 'bot', 'ذكاء']): cats['Bots'] += 1
        elif any(k in svc for k in ['تصميم', 'design', 'شعار', 'logo']): cats['Design'] += 1
        elif any(k in svc for k in ['برنامج', 'software', 'نظام']): cats['Software'] += 1
        else: cats['Other'] += 1
    completed = len([o for o in orders if o.get('status') == 'مكتمل'])
    pending = len([o for o in orders if o.get('status') != 'مكتمل'])
    return jsonify({
        'stats': stats,
        'daily': daily,
        'categories': cats,
        'completed': completed,
        'pending': pending,
        'start_time': data['stats'].get('start_time', '')
    })

# ========== API: Orders ==========
@app.route('/api/orders')
def api_orders():
    orders = sorted(data.get('orders', []), key=lambda x: x.get('id', 0), reverse=True)
    notes = data.get('order_notes', {})
    result = []
    for o in orders:
        item = dict(o)
        item['note'] = notes.get(str(o.get('id', '')), '')
        item['fb_link'] = o.get('link', '')
        result.append(item)
    return jsonify(result)

@app.route('/api/order/<int:oid>/complete', methods=['POST'])
def api_complete(oid):
    update_order(oid, {'status': 'مكتمل'})
    add_log(f"✅ طلب #{oid} → مكتمل")
    save_data()
    return jsonify({'success': True})

@app.route('/api/order/<int:oid>/delete', methods=['POST'])
def api_delete_order(oid):
    delete_order(oid)
    return jsonify({'success': True})

@app.route('/api/order/<int:oid>/note', methods=['POST'])
def api_add_note(oid):
    note = request.json.get('note', '')
    add_note_to_order(oid, note)
    add_log(f"📝 ملاحظة على طلب #{oid}")
    return jsonify({'success': True})

@app.route('/api/new_orders_check')
def api_new_orders_check():
    since = request.args.get('since', '')
    orders = data.get('orders', [])
    new_orders = [o for o in orders if o.get('timestamp', '') > since and o.get('status') == 'جديد']
    return jsonify({'count': len(new_orders), 'orders': new_orders[-5:]})

# ========== API: Clients ==========
@app.route('/api/clients')
def api_clients():
    sessions = data.get('sessions', {})
    orders = data.get('orders', [])
    clients_map = {}
    for o in orders:
        sid = o.get('sender_id', '')
        if not sid:
            continue
        name = o.get('name', '') or sid
        if sid not in clients_map:
            clients_map[sid] = {
                'id': sid,
                'name': name,
                'phone': o.get('phone', ''),
                'link': o.get('link', ''),
                'orders': [],
                'last_seen': o.get('timestamp', '')
            }
        clients_map[sid]['orders'].append({
            'id': o.get('id'),
            'service': o.get('service', ''),
            'budget': o.get('budget', 0),
            'status': o.get('status', 'جديد')
        })
        if o.get('timestamp', '') > clients_map[sid]['last_seen']:
            clients_map[sid]['last_seen'] = o['timestamp']
            clients_map[sid]['phone'] = o.get('phone', '') or clients_map[sid]['phone']
    for sid, c in clients_map.items():
        sess = sessions.get(sid, {})
        c['conversation'] = sess.get('conversation', [])
    result = sorted(clients_map.values(), key=lambda x: x['last_seen'], reverse=True)
    return jsonify(result)

# ========== API: Admins ==========
@app.route('/api/admins')
def api_admins():
    second = os.environ.get('SECOND_OWNER_FB_ID', '')
    return jsonify({
        'owner': OWNER_FB_ID,
        'second': second,
        'verified': data.get('verified', [])
    })

@app.route('/api/admin/test/<uid>', methods=['POST'])
def api_admin_test(uid):
    ok = send_fb(uid, '✅ Test message from B.Y PRO dashboard. You are verified.')
    return jsonify({'success': ok})

@app.route('/api/admin/remove/<uid>', methods=['POST'])
def api_admin_remove(uid):
    verified = data.get('verified', [])
    if uid in verified:
        verified.remove(uid)
        data['verified'] = verified
    data.setdefault('blocked', [])
    if uid not in data['blocked']:
        data['blocked'].append(uid)
    save_data()
    add_log(f"🚫 تم إزالة المدير وحظره: {uid[:12]}")
    return jsonify({'success': True})

@app.route('/api/unblock/<uid>', methods=['POST'])
def api_unblock(uid):
    blocked = data.get('blocked', [])
    if uid in blocked:
        blocked.remove(uid)
        data['blocked'] = blocked
        save_data()
        add_log(f"✅ رُفع الحظر عن: {uid[:12]}")
    return jsonify({'success': True})

@app.route('/api/remove_admin/<uid>', methods=['POST'])
def api_remove_admin(uid):
    verified = data.get('verified', [])
    if uid in verified:
        verified.remove(uid)
        data['verified'] = verified
        save_data()
    return jsonify({'success': True})

# ========== API: Settings ==========
@app.route('/api/settings', methods=['GET'])
def api_settings_get():
    return jsonify({
        'binance_id': BINANCE_ID,
        'ai_api_url': AI_API_URL,
        'fb_page': FB_PAGE_URL,
        'company_website': COMPANY_WEBSITE,
        'store_url': STORE_URL,
        'store_support': STORE_SUPPORT,
        'bot_prompt': BOT_PERSONALITY,
        'owner_prompt': data.get('owner_prompt', OWNER_PERSONALITY)
    })

@app.route('/api/settings', methods=['POST'])
def api_settings_save():
    global BOT_PERSONALITY, BINANCE_ID, AI_API_URL
    body = request.json or {}
    if body.get('bot_prompt'):
        BOT_PERSONALITY = body['bot_prompt']
    if body.get('binance_id'):
        BINANCE_ID = body['binance_id']
    if body.get('ai_api_url'):
        AI_API_URL = body['ai_api_url']
    if 'owner_prompt' in body:
        data['owner_prompt'] = body['owner_prompt']
    save_data()
    add_log("⚙️ تم تحديث الإعدادات من لوحة التحكم")
    return jsonify({'success': True})

# ========== API: Logs ==========
@app.route('/api/logs')
def api_logs():
    return jsonify(list(logs)[:50])

# ========== API: Reset ==========
@app.route('/api/reset', methods=['POST'])
def api_reset():
    body = request.json or {}
    if body.get('password') != OWNER_PASSWORD:
        return jsonify({'success': False, 'error': 'Wrong password'})
    keep_verified = data.get('verified', [])[:1]
    keep_owner_prompt = data.get('owner_prompt', '')
    data['orders'] = []
    data['sessions'] = {}
    data['blocked'] = []
    data['order_notes'] = {}
    data['stats'] = {
        'msgs_received': 0,
        'msgs_sent': 0,
        'start_time': datetime.now().isoformat()
    }
    data['verified'] = keep_verified
    data['owner_prompt'] = keep_owner_prompt
    save_data()
    add_log("🔄 تم إعادة تعيين البيانات من لوحة التحكم")
    return jsonify({'success': True})


# ========== ردود فيسبوك على التعليقات ==========

def get_page_id():
    """جلب Page ID من API"""
    try:
        r = requests.get(
            f'https://graph.facebook.com/v18.0/me',
            params={'access_token': PAGE_ACCESS_TOKEN, 'fields': 'id,name'},
            timeout=8
        )
        if r.status_code == 200:
            return r.json().get('id')
    except:
        pass
    return None

def get_recent_posts(page_id, limit=10):
    """جلب آخر منشورات الصفحة"""
    try:
        r = requests.get(
            f'https://graph.facebook.com/v18.0/{page_id}/posts',
            params={
                'access_token': PAGE_ACCESS_TOKEN,
                'fields': 'id,message,created_time',
                'limit': limit
            },
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get('data', [])
    except Exception as e:
        add_log(f"❌ خطأ جلب المنشورات: {e}")
    return []

def get_post_comments(post_id):
    """جلب تعليقات منشور مع pagination"""
    comments = []
    try:
        url = f'https://graph.facebook.com/v18.0/{post_id}/comments'
        params = {
            'access_token': PAGE_ACCESS_TOKEN,
            'fields': 'id,message,from{id,name},created_time',
            'limit': 100,
            'filter': 'stream'
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data_r = r.json()
            comments = data_r.get('data', [])
            add_log(f"💬 جلب {len(comments)} تعليق من منشور {post_id[:15]}")
        else:
            add_log(f"⚠️ خطأ جلب تعليقات {post_id[:10]}: {r.status_code} {r.text[:80]}")
    except Exception as e:
        add_log(f"❌ خطأ جلب التعليقات: {e}")
    return comments

def reply_to_comment(comment_id, reply_text):
    """الرد على تعليق — مع تسجيل فوري قبل الإرسال لمنع التكرار"""
    replied_ids = set(data.get('comment_replied_ids', []))
    if comment_id in replied_ids:
        add_log(f"⏭️ تخطي تعليق مكرر: {comment_id[:10]}")
        return False
    # تسجيل فوري لمنع أي إعادة محاولة متوازية
    replied_ids.add(comment_id)
    data['comment_replied_ids'] = list(replied_ids)[-2000:]

    try:
        r = requests.post(
            f'https://graph.facebook.com/v18.0/{comment_id}/comments',
            params={'access_token': PAGE_ACCESS_TOKEN},
            json={'message': reply_text},
            timeout=10
        )
        if r.status_code == 200:
            return True
        else:
            err_data = r.json().get('error', {})
            err_msg = err_data.get('message', r.text[:100])
            err_code = err_data.get('code', 0)
            # كود 100 أو 400 = تعليق لا يمكن الرد عليه (محذوف/قديم/من الصفحة)
            # نبقيه في replied_ids لتجنب إعادة المحاولة
            if r.status_code == 400 or err_code in [100, 200, 10]:
                add_log(f"⏭️ تعليق غير قابل للرد (سيُتجاهل): {err_msg[:60]}")
                # يبقى في replied_ids — لا نُزيله
                return False
            # أخطاء أخرى مؤقتة — نُزيل من replied_ids للمحاولة لاحقاً
            replied_ids.discard(comment_id)
            data['comment_replied_ids'] = list(replied_ids)
            add_log(f"⚠️ خطأ مؤقت في الرد: {r.status_code} {err_msg[:60]}")
            return False
    except Exception as e:
        replied_ids.discard(comment_id)
        data['comment_replied_ids'] = list(replied_ids)
        add_log(f"❌ خطأ الرد على تعليق: {e}")
        return False

def generate_comment_reply(commenter_name, comment_text, post_text):
    """توليد رد على تعليق بالـ AI"""
    comment_prompt = data.get('comment_settings', {}).get('prompt') or COMMENT_PERSONALITY
    full_prompt = (
        f"{comment_prompt}\n\n"
        f"المنشور الأصلي: {post_text[:300]}\n\n"
        f"اسم المعلق: {commenter_name}\n"
        f"التعليق: {comment_text}\n\n"
        f"اكتب رداً مناسباً يخاطبه باسمه:"
    )
    try:
        url = f'{AI_API_URL}?text={requests.utils.quote(full_prompt)}'
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            answer = r.json().get('response', '').strip()
            if answer:
                return answer[:500]
    except Exception as e:
        add_log(f"❌ خطأ AI للتعليق: {e}")
    return None

def process_comments_once():
    """فحص التعليقات — يرد فقط على الجديدة ولا يعدّ القديمة"""
    try:
        settings = data.get('comment_settings', {})
        if not settings.get('enabled') or not PAGE_ACCESS_TOKEN:
            return

        page_id = get_page_id()
        if not page_id:
            add_log("⚠️ لم يتم جلب Page ID للتعليقات")
            return

        posts = get_recent_posts(page_id, limit=20)
        # نسخة محلية من replied_ids — لا نُعدّل الـ global هنا
        replied_ids = set(data.get('comment_replied_ids', []))
        today = datetime.now().strftime('%Y-%m-%d')
        new_replies = 0
        from datetime import timezone

        for post in posts:
            post_id = post.get('id', '')
            post_text = post.get('message', '')
            comments = get_post_comments(post_id)

            for comment in comments:
                cid = comment.get('id', '')
                if not cid or cid in replied_ids:
                    continue  # مكرر — تجاهل بدون عداد

                from_data = comment.get('from') or {}
                commenter_name = (from_data.get('name') or '').strip()
                commenter_id = (from_data.get('id') or '').strip()
                comment_text = (comment.get('message') or '').strip()

                # تجاهل التعليقات الفارغة
                if not comment_text:
                    replied_ids.add(cid)  # علّمه لتجنب إعادة فحصه
                    continue

                # تجاهل التعليقات الأقدم من 24 ساعة وعلّمها
                created = comment.get('created_time', '')
                if created:
                    try:
                        ct = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        age_hours = (datetime.now(timezone.utc) - ct).total_seconds() / 3600
                        if age_hours > 24:
                            replied_ids.add(cid)
                            continue
                    except:
                        pass

                # توليد الرد
                display_name = commenter_name or 'صديق'
                reply = generate_comment_reply(display_name, comment_text, post_text)
                if not reply:
                    continue

                final_reply = f"@[{commenter_id}] {reply}" if commenter_id else reply

                # reply_to_comment تُضيف cid لـ replied_ids داخلياً
                ok = reply_to_comment(cid, final_reply)
                if ok:
                    replied_ids.add(cid)
                    new_replies += 1
                    # العداد يزيد فقط عند النجاح الفعلي
                    data.setdefault('comment_stats', {})[today] = \
                        data['comment_stats'].get(today, 0) + 1
                    data.setdefault('comment_log', []).insert(0, {
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
                        'post_id': post_id,
                        'post_text': post_text[:100],
                        'commenter': display_name,
                        'commenter_id': commenter_id,
                        'comment': comment_text[:200],
                        'reply': final_reply[:200]
                    })
                    data['comment_log'] = data['comment_log'][:200]
                    add_log(f"💬 رد على {display_name}: {comment_text[:40]}")
                    time.sleep(4)

        # تحديث replied_ids المجمّعة مرة واحدة
        data['comment_replied_ids'] = list(replied_ids)[-2000:]

        if new_replies > 0:
            save_data()
            add_log(f"✅ {new_replies} رد جديد على التعليقات")
        else:
            # احفظ replied_ids المحدّثة حتى لو لم يكن هناك ردود جديدة
            save_data()

    except Exception as e:
        add_log(f"⚠️ خطأ فحص التعليقات: {e}")

def comments_loop():
    """حلقة مراقبة التعليقات — يفحص فوراً ثم كل X دقائق"""
    time.sleep(10)  # انتظر 10 ثوان بعد بدء السيرفر فقط
    while True:
        process_comments_once()
        settings = data.get('comment_settings', {})
        interval = int(settings.get('check_interval_minutes', 5)) * 60
        time.sleep(interval)

# ========== نشر المنشورات التلقائي ==========

def publish_post(text, add_chat_button=True):
    """نشر منشور على الصفحة"""
    if not PAGE_ACCESS_TOKEN:
        return False, "PAGE_ACCESS_TOKEN غير موجود"
    try:
        page_id = get_page_id()
        if not page_id:
            return False, "لم يتم جلب Page ID"

        payload = {'message': text, 'access_token': PAGE_ACCESS_TOKEN}

        if add_chat_button:
            payload['call_to_action'] = {
                'type': 'MESSAGE_PAGE',
                'value': {'app_destination': 'MESSENGER'}
            }

        r = requests.post(
            f'https://graph.facebook.com/v18.0/{page_id}/feed',
            json=payload,
            timeout=15
        )
        if r.status_code == 200:
            post_id = r.json().get('id', '')
            add_log(f"📢 تم نشر منشور: {post_id}")
            data.setdefault('publish_settings', {})['last_published'] = datetime.now().isoformat()
            save_data()
            return True, post_id
        else:
            err = r.json().get('error', {}).get('message', r.text[:100])
            add_log(f"❌ فشل النشر: {err}")
            return False, err
    except Exception as e:
        add_log(f"❌ خطأ النشر: {e}")
        return False, str(e)

def publish_loop():
    """حلقة النشر التلقائي"""
    while True:
        try:
            time.sleep(60)
            settings = data.get('publish_settings', {})
            if not settings.get('enabled') or not settings.get('post_text'):
                continue
            interval = int(settings.get('interval_minutes', 60)) * 60
            last = settings.get('last_published', '')
            if last:
                elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
                if elapsed < interval:
                    continue
            text = settings.get('post_text', '')
            add_btn = settings.get('add_chat_button', True)
            publish_post(text, add_btn)
        except Exception as e:
            add_log(f"⚠️ خطأ حلقة النشر: {e}")

# ========== أزرار سريعة للمدير عبر الماسنجر ==========

def send_quick_replies(sender_id, text, buttons):
    """إرسال رسالة مع أزرار سريعة"""
    if not PAGE_ACCESS_TOKEN:
        return False
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {
            'recipient': {'id': sender_id},
            'message': {
                'text': text,
                'quick_replies': [
                    {'content_type': 'text', 'title': b['title'], 'payload': b['payload']}
                    for b in buttons[:11]
                ]
            },
            'messaging_type': 'RESPONSE'
        }
        r = requests.post(url, json=payload, timeout=8)
        return r.status_code == 200
    except:
        return False

def send_owner_menu(sender_id):
    """إرسال القائمة الرئيسية للمدير"""
    send_quick_replies(sender_id,
        "🎛️ لوحة تحكم B.Y PRO — اختر:",
        [
            {'title': '📊 الإحصائيات',    'payload': 'STATS'},
            {'title': '📋 كل الطلبات',    'payload': 'ALL_ORDERS'},
            {'title': '📅 طلبات اليوم',   'payload': 'TODAY_ORDERS'},
            {'title': '👥 العملاء',        'payload': 'CLIENTS'},
            {'title': '🚫 المحظورون',      'payload': 'BLOCKED'},
            {'title': '💬 التعليقات',      'payload': 'COMMENT_STATS'},
            {'title': '📢 نشر الآن',       'payload': 'PUBLISH_NOW'},
            {'title': '🔐 المدراء',        'payload': 'ADMINS'},
        ]
    )

def handle_quick_reply_payload(sender_id, payload):
    """معالجة الضغط على زر سريع"""
    stats = get_live_stats()

    if payload == 'STATS':
        completed = len([o for o in data.get('orders', []) if o.get('status') == 'مكتمل'])
        msg = (
            f"📊 إحصائيات B.Y PRO\n━━━━━━━━━━━━━━━\n"
            f"📦 إجمالي الطلبات: {stats['total_orders']}\n"
            f"📅 اليوم: {stats['today_orders']}\n"
            f"✅ مكتملة: {completed}\n"
            f"⏳ معلقة: {stats['total_orders']-completed}\n"
            f"👥 عملاء: {stats['unique_clients']}\n"
            f"🚫 محظورون: {stats['blocked']}\n"
            f"📨 واردة: {stats['msgs_received']} | 📤 صادرة: {stats['msgs_sent']}"
        )
        send_fb(sender_id, msg)
        send_quick_replies(sender_id, "ماذا تريد؟", [
            {'title': '📋 كل الطلبات', 'payload': 'ALL_ORDERS'},
            {'title': '🏠 القائمة الرئيسية', 'payload': 'MAIN_MENU'}
        ])

    elif payload == 'ALL_ORDERS':
        orders = list(reversed(data.get('orders', [])[-15:]))
        if not orders:
            send_fb(sender_id, "لا توجد طلبات بعد.")
        else:
            lines = [f"#{o['id']} {o.get('name','؟')} — {o.get('service','؟')} — {o.get('budget','؟')}$ [{o.get('status','جديد')}]" for o in orders]
            send_fb(sender_id, f"📋 الطلبات ({len(data.get('orders',[]))} إجمالاً):\n" + "\n".join(lines))
        send_quick_replies(sender_id, "إجراء على طلب؟", [
            {'title': '✅ تحديد مكتمل', 'payload': 'COMPLETE_ORDER'},
            {'title': '🗑️ حذف طلب',    'payload': 'DELETE_ORDER'},
            {'title': '📝 ملاحظة',      'payload': 'NOTE_ORDER'},
            {'title': '🏠 رئيسية',      'payload': 'MAIN_MENU'}
        ])

    elif payload == 'TODAY_ORDERS':
        if stats['today_orders'] > 0:
            lines = [f"#{o['id']} {o['name']} — {o['service']} — {o.get('budget','؟')}$" for o in stats['today_orders_list']]
            send_fb(sender_id, f"📅 طلبات اليوم ({stats['today_orders']}):\n" + "\n".join(lines))
        else:
            send_fb(sender_id, "لا توجد طلبات اليوم.")
        send_quick_replies(sender_id, "؟", [{'title': '🏠 رئيسية', 'payload': 'MAIN_MENU'}])

    elif payload == 'CLIENTS':
        orders = data.get('orders', [])
        clients = {}
        for o in orders:
            n = o.get('name', '')
            if n and n not in clients:
                clients[n] = o.get('phone', '')
        if clients:
            lines = [f"• {n} — {p}" for n, p in list(clients.items())[-15:]]
            send_fb(sender_id, f"👥 العملاء ({len(clients)}):\n" + "\n".join(lines))
        else:
            send_fb(sender_id, "لا يوجد عملاء بعد.")
        send_quick_replies(sender_id, "؟", [{'title': '🏠 رئيسية', 'payload': 'MAIN_MENU'}])

    elif payload == 'BLOCKED':
        blocked = data.get('blocked', [])
        if blocked:
            send_fb(sender_id, f"🚫 المحظورون ({len(blocked)}):\n" + "\n".join(blocked[-15:]))
        else:
            send_fb(sender_id, "لا يوجد محظورون.")
        send_quick_replies(sender_id, "؟", [{'title': '🏠 رئيسية', 'payload': 'MAIN_MENU'}])

    elif payload == 'COMMENT_STATS':
        today = datetime.now().strftime('%Y-%m-%d')
        today_count = data.get('comment_stats', {}).get(today, 0)
        total = sum(data.get('comment_stats', {}).values())
        status = "🟢 مفعّل" if data.get('comment_settings', {}).get('enabled') else "🔴 موقوف"
        send_fb(sender_id,
            f"💬 إحصائيات التعليقات\n━━━━━━━━━━━━━━━\n"
            f"الحالة: {status}\n"
            f"ردود اليوم: {today_count}\n"
            f"إجمالي الردود: {total}"
        )
        send_quick_replies(sender_id, "؟", [
            {'title': '🟢 تفعيل الردود',  'payload': 'COMMENTS_ON'},
            {'title': '🔴 إيقاف الردود',  'payload': 'COMMENTS_OFF'},
            {'title': '🏠 رئيسية',         'payload': 'MAIN_MENU'}
        ])

    elif payload == 'COMMENTS_ON':
        data.setdefault('comment_settings', {})['enabled'] = True
        save_data()
        send_fb(sender_id, "🟢 تم تفعيل الرد التلقائي على التعليقات.")
        send_quick_replies(sender_id, "؟", [{'title': '🏠 رئيسية', 'payload': 'MAIN_MENU'}])

    elif payload == 'COMMENTS_OFF':
        data.setdefault('comment_settings', {})['enabled'] = False
        save_data()
        send_fb(sender_id, "🔴 تم إيقاف الرد التلقائي على التعليقات.")
        send_quick_replies(sender_id, "؟", [{'title': '🏠 رئيسية', 'payload': 'MAIN_MENU'}])

    elif payload == 'PUBLISH_NOW':
        text = data.get('publish_settings', {}).get('post_text', '')
        if not text:
            send_fb(sender_id, "❌ لم يتم تعيين نص المنشور بعد. اذهب للوحة التحكم > Publishing.")
        else:
            add_btn = data.get('publish_settings', {}).get('add_chat_button', True)
            ok, result = publish_post(text, add_btn)
            if ok:
                send_fb(sender_id, f"✅ تم النشر بنجاح! ID: {result}")
            else:
                send_fb(sender_id, f"❌ فشل النشر: {result}")
        send_quick_replies(sender_id, "؟", [{'title': '🏠 رئيسية', 'payload': 'MAIN_MENU'}])

    elif payload == 'ADMINS':
        verified = data.get('verified', [])
        msg = f"🔐 المدراء ({len(verified)}):\n" + "\n".join(verified[-10:]) if verified else "لا يوجد مدراء مضافون."
        send_fb(sender_id, msg)
        send_quick_replies(sender_id, "؟", [{'title': '🏠 رئيسية', 'payload': 'MAIN_MENU'}])

    elif payload == 'COMPLETE_ORDER':
        send_fb(sender_id, "أرسل: مكتمل [رقم الطلب]\nمثال: مكتمل 5")

    elif payload == 'DELETE_ORDER':
        send_fb(sender_id, "أرسل: حذف [رقم الطلب]\nمثال: حذف 3")

    elif payload == 'NOTE_ORDER':
        send_fb(sender_id, "أرسل: ملاحظة [رقم] [النص]\nمثال: ملاحظة 2 العميل طلب تعديل")

    elif payload == 'MAIN_MENU':
        send_owner_menu(sender_id)

# ========== API: Comments ==========
@app.route('/api/comments/log')
def api_comments_log():
    return jsonify(data.get('comment_log', [])[:100])

@app.route('/api/comments/stats')
def api_comments_stats():
    stats_raw = data.get('comment_stats', {})
    today = datetime.now().strftime('%Y-%m-%d')
    return jsonify({
        'today': stats_raw.get(today, 0),
        'total': sum(stats_raw.values()),
        'daily': dict(sorted(stats_raw.items())[-14:]),
        'enabled': data.get('comment_settings', {}).get('enabled', False)
    })

@app.route('/api/comments/settings', methods=['GET'])
def api_comments_settings_get():
    s = data.get('comment_settings', {})
    return jsonify({
        'enabled': s.get('enabled', False),
        'prompt': s.get('prompt', COMMENT_PERSONALITY),
        'check_interval_minutes': s.get('check_interval_minutes', 5)
    })

@app.route('/api/comments/settings', methods=['POST'])
def api_comments_settings_save():
    body = request.json or {}
    data.setdefault('comment_settings', {}).update({
        k: body[k] for k in ['enabled', 'prompt', 'check_interval_minutes'] if k in body
    })
    save_data()
    add_log("⚙️ تم تحديث إعدادات التعليقات")
    return jsonify({'success': True})

# ========== API: Publishing ==========
@app.route('/api/publish/now', methods=['POST'])
def api_publish_now():
    body = request.json or {}
    text = body.get('text') or data.get('publish_settings', {}).get('post_text', '')
    add_btn = body.get('add_chat_button', data.get('publish_settings', {}).get('add_chat_button', True))
    if not text:
        return jsonify({'success': False, 'error': 'لا يوجد نص للنشر'})
    ok, result = publish_post(text, add_btn)
    return jsonify({'success': ok, 'result': result})

@app.route('/api/publish/settings', methods=['GET'])
def api_publish_settings_get():
    s = data.get('publish_settings', {})
    return jsonify({
        'enabled': s.get('enabled', False),
        'interval_minutes': s.get('interval_minutes', 60),
        'post_text': s.get('post_text', DEFAULT_POST_TEXT),
        'add_chat_button': s.get('add_chat_button', True),
        'last_published': s.get('last_published', '')
    })

@app.route('/api/publish/settings', methods=['POST'])
def api_publish_settings_save():
    body = request.json or {}
    data.setdefault('publish_settings', {}).update({
        k: body[k] for k in ['enabled', 'interval_minutes', 'post_text', 'add_chat_button'] if k in body
    })
    save_data()
    add_log("⚙️ تم تحديث إعدادات النشر")
    return jsonify({'success': True})

# ========== API: Clear Message Counters ==========
@app.route('/api/clear_msgs', methods=['POST'])
def api_clear_msgs():
    body = request.json or {}
    if body.get('password') != OWNER_PASSWORD:
        return jsonify({'success': False, 'error': 'Wrong password'})
    data['stats']['msgs_received'] = 0
    data['stats']['msgs_sent'] = 0
    save_data()
    add_log("🗑️ تم مسح عدادات الرسائل")
    return jsonify({'success': True})

# ========== API: Comment Log Management ==========
@app.route('/api/comments/log/delete', methods=['POST'])
def api_comment_log_delete():
    body = request.json or {}
    idx = body.get('index')
    if idx is None:
        return jsonify({'success': False, 'error': 'index required'})
    log = data.get('comment_log', [])
    if 0 <= idx < len(log):
        removed = log.pop(idx)
        data['comment_log'] = log
        save_data()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid index'})

@app.route('/api/comments/log/clear', methods=['POST'])
def api_comment_log_clear():
    body = request.json or {}
    if body.get('password') != OWNER_PASSWORD:
        return jsonify({'success': False, 'error': 'Wrong password'})
    data['comment_log'] = []
    data['comment_stats'] = {}
    save_data()
    add_log("🗑️ تم مسح سجل التعليقات والإحصائيات")
    return jsonify({'success': True})

@app.route('/api/comments/log/edit', methods=['POST'])
def api_comment_log_edit():
    body = request.json or {}
    idx = body.get('index')
    new_reply = body.get('reply', '')
    if idx is None or not new_reply:
        return jsonify({'success': False, 'error': 'index and reply required'})
    log = data.get('comment_log', [])
    if 0 <= idx < len(log):
        log[idx]['reply'] = new_reply
        log[idx]['edited'] = True
        data['comment_log'] = log
        save_data()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid index'})

# ========== API: Manual Comments Check ==========
@app.route('/api/comments/check_now', methods=['POST'])
def api_comments_check_now():
    threading.Thread(target=process_comments_once, daemon=True).start()
    return jsonify({'success': True, 'message': 'Comment check started'})

# ========== Keep-Alive كل 30 ثانية ==========
def keep_alive_loop():
    while True:
        time.sleep(30)
        try:
            requests.get(SELF_URL, timeout=8)
            add_log("💓 Keep-alive ping")
        except Exception as e:
            add_log(f"⚠️ Keep-alive failed: {e}")

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 B.Y PRO Agent - النسخة النهائية الشاملة")
    print("="*70)
    print(f"👤 Owner ID: {OWNER_FB_ID}")
    print(f"🔑 Password: {OWNER_PASSWORD}")
    print(f"💰 Binance: {BINANCE_ID}")
    print(f"📦 Orders: {len(data.get('orders', []))}")
    print(f"💬 Comments replied: {len(data.get('comment_replied_ids', []))}")
    print(f"📢 Auto-publish: {data.get('publish_settings', {}).get('enabled', False)}")
    print("="*70 + "\n")

    threading.Thread(target=keep_alive_loop, daemon=True).start()
    threading.Thread(target=comments_loop, daemon=True).start()
    threading.Thread(target=publish_loop, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
