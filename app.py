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
# الرابط الجديد للـ API - يحتوي على ?text= بالفعل
AI_API_URL        = os.environ.get('AI_API_URL', 'http://de3.bot-hosting.net:21007/kilwa-chat?text=')
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
    'comment_replied_ids': [],
    'comment_stats': {},
    'comment_log': [],
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
    return str(sender_id) == str(OWNER_FB_ID)

def is_verified_admin(sender_id):
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
            'stage': 'explore',
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
    patterns = [
        r'(\+213[567][0-9]{8})',
        r'(00213[567][0-9]{8})',
        r'(0[567][0-9]{8})',
        r'(\+966[0-9]{9})',
        r'(05[0-9]{8})',
        r'(\+212[0-9]{9})',
        r'(\+216[0-9]{8})',
        r'(\+20[0-9]{10})',
        r'(\+[1-9][0-9]{7,14})',
        r'([0-9]{10,13})',
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
            if 2 <= len(name.split()) <= 4 and len(name) <= 30:
                return name
    return None

def is_price_confirmation(text):
    confirmations = [
        'نعم', 'موافق', 'موافقة', 'تمام', 'تمام شكراً', 'اوكي', 'اوك', 'ok', 'yes',
        'okay', 'agreed', 'deal', 'ماشي', 'راني موافق', 'حسنا', 'يلا نبدأ',
        'نبدو', 'نبدأ', 'جيد', 'سنبدأ', 'اتفقنا', 'ممتاز', 'بالتوفيق', 'شكراً',
        'اشتري', 'مشينا'
    ]
    text_clean = text.lower().strip()
    return any(w in text_clean for w in confirmations)

def is_price_rejection(text):
    rejections = ['لا', 'غالي', 'كثير', 'خصم', 'أرخص', 'يخفض', 'مو مناسب', 'no', 'too much', 'expensive']
    text_clean = text.lower().strip()
    return any(w in text_clean for w in rejections)

# ========== الذكاء الاصطناعي - متوافق مع API الجديد ==========
def get_ai_response(prompt):
    """دالة مركزية للاتصال بـ API الذكاء الاصطناعي الجديد"""
    if not AI_API_URL:
        add_log("❌ AI_API_URL غير محدد")
        return None
    
    try:
        # الرابط الجديد يحتوي بالفعل على ?text=
        url = f"{AI_API_URL}{requests.utils.quote(prompt)}"
        add_log(f"🤖 إرسال طلب إلى AI: {url[:100]}...")
        
        response = requests.get(url, timeout=25)
        
        if response.status_code == 200:
            try:
                result = response.json()
                # النموذج الجديد يعيد response في حقل 'response'
                answer = result.get('response', '')
                if answer and answer.strip():
                    add_log(f"✅ استجابة AI: {answer[:50]}...")
                    return answer.strip()
                else:
                    add_log(f"⚠️ استجابة AI فارغة")
                    return None
            except json.JSONDecodeError:
                # إذا لم تكن استجابة JSON، جرب النص العادي
                text_response = response.text.strip()
                if text_response:
                    add_log(f"✅ استجابة AI (نص): {text_response[:50]}...")
                    return text_response
                else:
                    add_log(f"⚠️ استجابة AI نص فارغ")
                    return None
        else:
            add_log(f"❌ خطأ AI: HTTP {response.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        add_log(f"❌ AI: timeout بعد 25 ثانية")
        return None
    except Exception as e:
        add_log(f"❌ AI: استثناء - {str(e)}")
        return None

def ask_ai(user_msg, sess, extra_instruction="", personality=None):
    """سؤال الذكاء الاصطناعي باستخدام API الجديد"""
    context = "\n".join(sess.get('conversation', [])[-12:])
    
    stage_hints = {
        'explore': "أنت تستمع لطلب العميل وتفهم احتياجه. اسأل سؤالاً أو سؤالين بسيطين لتفهم المشروع، ثم قدّم له السعر والمدة.",
        'price_proposed': "لقد اقترحت سعراً للعميل. انتظر موافقته. لا تضيف معلومات جديدة.",
        'awaiting_confirmation': "العميل على وشك الموافقة أو الرفض. إذا وافق، اطلب اسمه الكريم فقط.",
        'collecting_name': "اطلب من العميل اسمه الكريم فقط. رسالة واحدة مختصرة.",
        'collecting_phone': f"اسم العميل هو: {sess.get('name', '')}. اطلب منه رقم هاتفه الآن. رسالة مختصرة.",
    }
    
    active_personality = personality or BOT_PERSONALITY
    stage = sess.get('stage', 'explore')
    hint = stage_hints.get(stage, "")
    
    full_prompt = f"""{active_personality}

[حالة المحادثة الحالية: {hint}]
{extra_instruction}

سجل المحادثة:
{context}

المستخدم: {user_msg}
أحمد:"""
    
    # محاولة الحصول على رد من AI
    response = get_ai_response(full_prompt)
    
    if response:
        return response[:1800]
    
    # رد احتياطي في حال فشل AI
    fallback_responses = [
        "عذراً، النظام التقني مؤقت. أعد كتابة رسالتك من فضلك.",
        "حدث خطأ تقني. حاول مرة أخرى بعد لحظة.",
        "نأسف للخلل التقني. تفضل بكتابة طلبك مرة أخرى."
    ]
    import random
    return random.choice(fallback_responses)

# ========== معالجة أوامر المدير ==========
def handle_owner_command(sender_id, text):
    t = text.lower().strip()
    stats = get_live_stats()

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

    m = re.search(r'(?:مكتمل|اكتمل|انجز|انتهى)\s+#?(\d+)', text)
    if m:
        oid = int(m.group(1))
        if update_order(oid, {'status': 'مكتمل'}):
            send_fb(sender_id, f"✅ تم تحديث طلب #{oid} إلى مكتمل")
        else:
            send_fb(sender_id, f"❌ لم يُعثر على طلب #{oid}")
        return True

    m = re.search(r'حذف\s+#?(\d+)', text)
    if m:
        oid = int(m.group(1))
        delete_order(oid)
        send_fb(sender_id, f"🗑️ تم حذف طلب #{oid}")
        return True

    m = re.search(r'ملاحظة\s+#?(\d+)\s+(.+)', text)
    if m:
        oid = int(m.group(1))
        note = m.group(2).strip()
        add_note_to_order(oid, note)
        send_fb(sender_id, f"📝 تمت إضافة الملاحظة لطلب #{oid}")
        return True

    if any(k in t for k in ['المحظورين', 'محظورين', 'المحظورون', 'blocked']):
        blocked = data.get('blocked', [])
        if blocked:
            send_fb(sender_id, f"🚫 المحظورون ({len(blocked)}):\n" + "\n".join(blocked[-15:]))
        else:
            send_fb(sender_id, "لا يوجد مستخدمون محظورون.")
