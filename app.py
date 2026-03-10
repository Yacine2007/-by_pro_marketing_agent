import os
import re
import json
import requests
import time
import threading
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from collections import deque

app = Flask(__name__)

# ========== المتغيرات البيئية ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '61580260328404')  # معرف المدير الحقيقي
OWNER_PASSWORD = os.environ.get('OWNER_PASSWORD', '20070909')
BIN_ID = os.environ.get('BIN_ID')
X_MASTER_KEY = os.environ.get('X_MASTER_KEY')
X_ACCESS_KEY = os.environ.get('X_ACCESS_KEY')
BINANCE_ID = os.environ.get('BINANCE_ID', '1074084246')
AI_API_URL = os.environ.get('AI_API_URL', 'http://fi8.bot-hosting.net:20163/elos-gemina')
COMPANY_WEBSITE = os.environ.get('COMPANY_WEBSITE', 'https://b.y-pro.kesug.com')
SELF_URL = os.environ.get('SELF_URL', 'https://by-pro-marketing-agent.onrender.com')

# ========== شخصية البوت ==========
BOT_PERSONALITY = """أنت "أحمد"، وكيل تسويق ومبيعات في شركة B.Y PRO للتكنولوجيا والبرمجيات.

=== قاعدة اللغة - الأهم ===
تحدّث دائماً بنفس لغة العميل التي بدأ بها المحادثة. إذا بدأ بالعربية فأنت عربي طوال المحادثة. إذا بدأ بالإنجليزية فأنت إنجليزي طوال المحادثة. لا تخلط اللغتين أبداً.

=== هويتك ===
أنت تمثّل شركة B.Y PRO بالكامل: تصميم، برمجة، تطبيقات، ذكاء اصطناعي، جرافيك.
عندما يسألك عميل "هل تقدر تبرمج؟" أو "هل تصمم؟" الجواب دائماً بإيجاب: "نعم، هذا تخصصنا".
لا تقل "سأحوّلك للفريق التقني" أبداً. أنت من يغلق الصفقة مباشرة.
لا تكشف أنك بوت أو ذكاء اصطناعي.

=== أسلوبك ===
تكلّم بطبيعية كإنسان، ودود ومختصر. لا تبدأ كل رسالة بـ "أهلاً". ردود قصيرة ومباشرة.

=== مسار البيع (اتبعه بدقة) ===
1. اسمع العميل واسأل سؤالاً أو اثنين لفهم المشروع.
2. قدّم السعر والمدة بوضوح (مثال: "120$ وتاخذ 24 ساعة").
3. انتظر موافقته فقط. النظام يجمع بياناته تلقائياً بعد موافقته.

=== ممنوع منعاً باتاً ===
لا تطلب اسم العميل أو رقمه - النظام يفعل ذلك تلقائياً.
لا تقل "تم تسجيل طلبك" - النظام هو من يسجّل.
لا تعطِ وعوداً بالتسجيل قبل إعطاء البيانات.

=== خدمات B.Y PRO والأسعار ===
- شعار / لوجو بسيط: 80-180$ (24-48 ساعة)
- هوية بصرية كاملة: 200-450$ (3-5 أيام)
- تصميم جرافيك / مواد تسويقية: 100-350$ (1-3 أيام)
- موقع تعريفي بسيط: 250-500$ (5-10 أيام)
- موقع تعريفي متقدم: 500-950$ (10-20 يوم)
- متجر إلكتروني أساسي: 650-1100$ (15-25 يوم)
- متجر إلكتروني متكامل: 1100-2400$ (25-45 يوم)
- تطبيق جوال بسيط MVP: 1400-2400$ (30-50 يوم)
- تطبيق جوال متكامل: 2400-7500$ (50-90 يوم)
- بوت ذكاء اصطناعي بسيط: 450-900$ (7-15 يوم)
- بوت ذكاء اصطناعي متقدم: 900-2900$ (15-40 يوم)
- برنامج / نظام مخصص: 950-4900$ (حسب المشروع)
طريقة الدفع: 30% مقدماً، 70% بعد التسليم، عبر USDT (Binance Pay) معرف: 1074084246

=== متجر STORE PRO (ميزة إضافية) ===
نمتلك متجراً لبيع المشاريع والبرامج الجاهزة: https://store-pro.great-site.net/
يمكن لأي شخص رفع مشروعه أو برنامجه على المتجر للبيع:
- المشاريع المجانية: تبدأ من 1$ فقط
- المشاريع المدفوعة: تبدأ من 3$
- باقي التسعيرات والميزات موجودة في المتجر
- للدعم والتواصل: https://t.me/STOREPROSPRT
لا تُعرض هذه الخدمة من تلقاء نفسك، فقط أجب عنها إذا سأل العميل."""

# ========== برومبت المدير ==========
OWNER_PERSONALITY = """أنت "أحمد"، مساعد ذكي لصاحب شركة B.Y PRO.
المدير هو صاحب الشركة - صلاحياته مطلقة. أجبه مباشرة وبدون تحفظات.
لا تقل له "هذا حساس" أو "ثواني" أو "سأتحقق" - أعطه المعلومة فوراً.
مختصر وجاد معه دائماً. تحدث معه بالعربية دائماً."""

# ========== تخزين JSONBin.io ==========
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
            'stage': 'explore',
            'lang': 'ar',  # لغة العميل المكتشفة
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

def is_valid_phone(phone):
    """التحقق من صحة رقم الهاتف - يرفض الأرقام العشوائية"""
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 8 or len(digits) > 15:
        return False
    # رفض الأرقام المتكررة (0000000, 1111111, 1234567890)
    if len(set(digits)) <= 2:
        return False
    if digits in ['1234567890', '0123456789', '9876543210']:
        return False
    # تحقق من بادئات معقولة
    if digits.startswith('0') and len(digits) < 9:
        return False
    return True

def extract_phone(text):
    """استخراج رقم الهاتف من النص مع التحقق من الصحة"""
    patterns = [
        r'(\+213[5-7][0-9]{8})',      # جزائر +213
        r'(00213[5-7][0-9]{8})',       # جزائر 00213
        r'(0[5-7][0-9]{8})',           # جزائر/مغرب محلي
        r'(\+966[5][0-9]{8})',         # سعودية +966
        r'(05[0-9]{8})',               # خليجي محلي
        r'(\+971[5][0-9]{8})',         # إمارات
        r'(\+212[5-7][0-9]{8})',       # مغرب
        r'(\+216[2-9][0-9]{7})',       # تونس
        r'(\+20[0-9]{10})',            # مصر
        r'(\+962[7][0-9]{8})',         # أردن
        r'(\+[1-9][0-9]{7,13})',       # أي رقم دولي
        r'(07[0-9]{8,9})',             # العراق/الأردن
        r'([0-9]{10,13})',             # أي رقم طويل
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            phone = m.group(1)
            if is_valid_phone(phone):
                return phone
    return None

def is_valid_name(name):
    """التحقق من صحة الاسم"""
    name = name.strip()
    if len(name) < 2 or len(name) > 40:
        return False
    # يجب أن يحتوي على حروف فعلية (عربية أو لاتينية)
    if not re.search(r'[\u0600-\u06FFa-zA-Z]', name):
        return False
    # رفض الأرقام فقط
    if re.match(r'^[\d\s]+$', name):
        return False
    # رفض الرموز العشوائية
    if re.match(r'^[^a-zA-Z\u0600-\u06FF]+$', name):
        return False
    # رفض الكلمات العشوائية (حروف مكررة جداً)
    if len(name) > 3 and len(set(name.replace(' ', ''))) <= 2:
        return False
    # رفض الكلمات الشائعة التي ليست أسماء
    non_names = ['نعم', 'لا', 'اوكي', 'تمام', 'كيف', 'ماذا', 'متى', 'yes', 'no', 'ok', 'okay', 'hello', 'مرحبا', 'هلا']
    if name.lower() in non_names:
        return False
    return True

def extract_name_from_text(text):
    """استخراج الاسم من النص"""
    patterns = [
        r'(?:اسمي|الاسم|أنا|انا)[:\s]+([\u0600-\u06FF\w]{2,25}(?:\s[\u0600-\u06FF\w]{2,20}){0,3})',
        r'(?:my name is|name is|im called|i am)[:\s]+([\w]{2,25}(?:\s[\w]{2,20}){0,2})',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            candidate = m.group(1).strip()
            if is_valid_name(candidate):
                return candidate
    return None

def detect_language(text):
    """كشف لغة النص الأساسية"""
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    latin_chars = len(re.findall(r'[a-zA-Z]', text))
    if arabic_chars > latin_chars:
        return 'ar'
    elif latin_chars > arabic_chars:
        return 'en'
    return 'ar'  # افتراضي

def is_price_confirmation(text):
    """هل وافق العميل على السعر؟"""
    confirmations = [
        'نعم', 'موافق', 'موافقة', 'تمام', 'اوكي', 'اوك', 'ok', 'yes', 'okay',
        'agreed', 'deal', 'ماشي', 'حسنا', 'يلا', 'نبدأ', 'جيد', 'اتفقنا',
        'ممتاز', 'مشينا', 'بالطبع', 'طيب', 'خلاص', 'ايه', 'آه', 'يس',
        'ان شاء الله نبدأ', 'حسناً', 'مو مشكلة', 'لا مشكلة', 'نعم موافق',
        'sure', 'let\'s go', 'proceed', 'sounds good', 'perfect', 'great'
    ]
    text_clean = text.lower().strip()
    if any(w in text_clean for w in confirmations):
        return True
    if len(text_clean) <= 3 and text_clean not in ['لا', 'لأ', 'no', 'la', 'لو', 'لن']:
        return True
    return False

def is_price_rejection(text):
    """هل رفض العميل السعر؟"""
    rejections = ['غالي', 'كثير', 'خصم', 'أرخص', 'يخفض', 'مو مناسب',
                  'too much', 'expensive', 'reduce', 'discount', 'cheaper']
    text_clean = text.lower().strip()
    if text_clean in ['لا', 'لأ', 'no', 'nope']:
        return True
    return any(w in text_clean for w in rejections)

# ========== الذكاء الاصطناعي ==========
def ask_ai(user_msg, sess, extra_instruction="", is_owner_mode=False):
    context = "\n".join(sess.get('conversation', [])[-12:])
    lang = sess.get('lang', 'ar')
    lang_hint = "تحدث بالعربية فقط." if lang == 'ar' else "Respond in English only."

    if is_owner_mode:
        full_prompt = (
            f"{OWNER_PERSONALITY}\n\n"
            f"{extra_instruction}\n\n"
            f"سجل المحادثة:\n{context}\n\n"
            f"المدير: {user_msg}\n"
            f"أحمد:"
        )
    else:
        stage_hints = {
            'explore': "استمع للعميل، اسأل سؤالاً واحداً أو اثنين لفهم المشروع، ثم قدّم السعر والمدة مباشرة.",
            'price_proposed': "اقترحت سعراً. فقط انتظر موافقته. لا تضيف جديداً. لا تطلب اسمه أو رقمه.",
        }
        stage = sess.get('stage', 'explore')
        hint = stage_hints.get(stage, "")

        full_prompt = (
            f"{BOT_PERSONALITY}\n\n"
            f"[{lang_hint}]\n"
            f"[التعليمة الحالية: {hint}]\n"
            f"{extra_instruction}\n\n"
            f"سجل المحادثة:\n{context}\n\n"
            f"العميل: {user_msg}\n"
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

    if lang == 'en':
        return "Sorry, a temporary technical error occurred. Please try again."
    return "عذراً، حدث خطأ تقني مؤقت. حاول مرة أخرى."

# ========== معالجة أوامر المدير ==========
def handle_owner_command(sender_id, text):
    """معالجة أوامر المدير الحقيقي أو المدير الموثق"""
    text_lower = text.lower().strip()
    stats = get_live_stats()
    
    # إحصائيات
    if any(k in text_lower for k in ['احصائيات', 'إحصائيات', 'statistics', 'stats']):
        msg = (
            f"📊 إحصائيات B.Y PRO\n"
            f"العملاء الفريدون: {stats['unique_clients']}\n"
            f"إجمالي الطلبات: {stats['total_orders']}\n"
            f"طلبات اليوم: {stats['today_orders']}\n"
            f"المحظورون: {stats['blocked']}\n"
            f"المدراء: {stats['verified']}\n"
            f"رسائل واردة: {stats['msgs_received']}\n"
            f"رسائل صادرة: {stats['msgs_sent']}"
        )
        send_fb(sender_id, msg)
        return True
    
    # الطلبات الجديدة
    if any(k in text_lower for k in ['اي جديد', 'طلبات اليوم', 'الجديد']):
        if stats['today_orders'] > 0:
            lines = [f"#{o['id']} {o['name']} - {o['service']} - {o.get('budget','؟')}$" 
                     for o in stats['today_orders_list']]
            send_fb(sender_id, f"📦 {stats['today_orders']} طلب اليوم:\n" + "\n".join(lines))
        else:
            send_fb(sender_id, "لا توجد طلبات اليوم.")
        return True
    
    # كل الطلبات
    if any(k in text_lower for k in ['كل الطلبات', 'جميع الطلبات', 'all orders']):
        orders = data.get('orders', [])[-10:]
        if orders:
            lines = [f"#{o['id']} {o['name']} - {o['service']} - {o.get('budget','؟')}$ [{o.get('status','جديد')}]"
                     for o in reversed(orders)]
            send_fb(sender_id, "📋 آخر الطلبات:\n" + "\n".join(lines))
        else:
            send_fb(sender_id, "لا توجد طلبات بعد.")
        return True
    
    # تفاصيل طلب
    m = re.search(r'تفاصيل\s+(\d+)', text)
    if m:
        oid = int(m.group(1))
        o = get_order(oid)
        if o:
            note = data.get('order_notes', {}).get(str(oid), 'لا يوجد')
            msg = (
                f"📋 تفاصيل الطلب #{oid}\n"
                f"الاسم: {o['name']}\n"
                f"الخدمة: {o['service']}\n"
                f"الميزانية: {o.get('budget','؟')}$\n"
                f"الهاتف: {o.get('phone','غير متوفر')}\n"
                f"المدة: {o.get('duration','غير محددة')}\n"
                f"التفاصيل: {o.get('details','')}\n"
                f"الحالة: {o.get('status','جديد')}\n"
                f"ملاحظات: {note}\n"
                f"التاريخ: {o.get('timestamp','')[:16]}\n"
                f"رابط: {o.get('link','')}"
            )
        else:
            msg = f"❌ لم يُعثر على طلب #{oid}"
        send_fb(sender_id, msg)
        return True
    
    # حظر مستخدم
    m = re.search(r'حظر\s+(\d+)', text)
    if m:
        uid = m.group(1)
        if 'blocked' not in data:
            data['blocked'] = []
        if uid not in data['blocked']:
            data['blocked'].append(uid)
            save_data()
            send_fb(sender_id, f"✅ تم حظر المستخدم {uid}")
        else:
            send_fb(sender_id, "المستخدم محظور مسبقاً.")
        return True
    
    # إلغاء الحظر
    m = re.search(r'(الغاء حظر|رفع حظر)\s+(\d+)', text)
    if m:
        uid = m.group(2)
        if uid in data.get('blocked', []):
            data['blocked'].remove(uid)
            save_data()
            send_fb(sender_id, f"✅ تم رفع الحظر عن {uid}")
        else:
            send_fb(sender_id, "المستخدم غير محظور.")
        return True
    
    # مكتمل
    m = re.search(r'مكتمل\s+(\d+)', text)
    if m:
        oid = int(m.group(1))
        if update_order(oid, {'status': 'مكتمل'}):
            send_fb(sender_id, f"✅ تم تحديث طلب #{oid} إلى مكتمل")
        else:
            send_fb(sender_id, f"❌ لم يُعثر على طلب #{oid}")
        return True
    
    # حذف طلب
    m = re.search(r'حذف\s+(\d+)', text)
    if m:
        oid = int(m.group(1))
        delete_order(oid)
        send_fb(sender_id, f"🗑️ تم حذف طلب #{oid}")
        return True
    
    # ملاحظة
    m = re.search(r'ملاحظة\s+(\d+)\s+(.+)', text)
    if m:
        oid = int(m.group(1))
        note = m.group(2).strip()
        add_note_to_order(oid, note)
        send_fb(sender_id, f"📝 تمت إضافة الملاحظة لطلب #{oid}")
        return True
    
    # المحظورين
    if 'المحظورين' in text_lower:
        blocked = data.get('blocked', [])
        if blocked:
            send_fb(sender_id, f"🚫 المحظورون ({len(blocked)}):\n" + "\n".join(blocked[-15:]))
        else:
            send_fb(sender_id, "لا يوجد مستخدمون محظورون.")
        return True
    
    # العملاء
    if any(k in text_lower for k in ['العملاء', 'اعرض العملاء', 'clients']):
        orders = data.get('orders', [])
        clients = {}
        for o in orders:
            name = o.get('name', '')
            if name and name not in clients:
                clients[name] = o.get('phone', '')
        if clients:
            lines = [f"• {n} - {p}" for n, p in list(clients.items())[-15:]]
            send_fb(sender_id, "👥 العملاء المسجلون:\n" + "\n".join(lines))
        else:
            send_fb(sender_id, "لا يوجد عملاء مسجلون بعد.")
        return True
    
    return False  # لم يُعثر على أمر مطابق

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

    # كشف لغة العميل عند أول رسالة حقيقية (غير المدير)
    if not is_owner(sender_id) and not is_verified_admin(sender_id):
        if not sess.get('lang') or sess.get('lang') == 'ar':
            detected = detect_language(text)
            if detected != sess.get('lang', 'ar'):
                update_session(sender_id, {'lang': detected})
                sess['lang'] = detected

    add_to_conversation(sender_id, 'المستخدم', text)

    # ====== المدير الحقيقي (بالـ ID الثابت فقط) ======
    if is_owner(sender_id):
        # المدير الحقيقي لا يحتاج كلمة مرور
        handled = handle_owner_command(sender_id, text)
        if not handled:
            # رد ذكي للمدير
            stats = get_live_stats()
            extra = (
                f"\n[أنت تتحدث مع المدير مباشرة. إحصائيات سريعة: "
                f"{stats['today_orders']} طلب اليوم، {stats['total_orders']} إجمالاً]"
            )
            reply = ask_ai(text, sess, extra_instruction=extra)
            send_fb(sender_id, reply)
            add_to_conversation(sender_id, 'أحمد', reply)
        save_data()
        return

    # ====== المدراء الموثقون (بكلمة المرور) ======
    if is_verified_admin(sender_id):
        handled = handle_owner_command(sender_id, text)
        if not handled:
            reply = ask_ai(text, sess)
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
            sess['stage'] = 'collecting_name'
            update_session(sender_id, {'stage': 'collecting_name'})
            save_data()
            msg = "Great! What's your name?" if sess.get('lang') == 'en' else "ممتاز! ما اسمك الكريم؟"
            send_fb(sender_id, msg)
            add_to_conversation(sender_id, 'أحمد', msg)
            return
        elif is_price_rejection(text):
            sess['stage'] = 'explore'
            update_session(sender_id, {'stage': 'explore', 'budget': 0, 'budget_range': ''})
            reply = ask_ai(text, sess, extra_instruction="العميل يريد تعديل السعر. ناقشه بمرونة وقدّم بديلاً.")
            send_fb(sender_id, reply)
            add_to_conversation(sender_id, 'أحمد', reply)
            save_data()
            return
        else:
            reply = ask_ai(text, sess, extra_instruction="أجب باختصار ثم اسأله: هل يوافق على السعر؟ لا تطلب اسمه أو رقمه.")
            send_fb(sender_id, reply)
            add_to_conversation(sender_id, 'أحمد', reply)
            save_data()
            return

    # --- مرحلة: جمع الاسم ---
    if stage == 'collecting_name':
        lang = sess.get('lang', 'ar')
        # محاولة استخراج الاسم بالأنماط أولاً
        name = extract_name_from_text(text)

        # إذا لم يُستخرج، افترض أن النص كله هو الاسم إذا كان قصيراً وصالحاً
        if not name:
            candidate = text.strip()
            words = candidate.split()
            if 1 <= len(words) <= 4 and 2 <= len(candidate) <= 40:
                if is_valid_name(candidate):
                    name = candidate

        if name:
            update_session(sender_id, {'name': name, 'stage': 'collecting_phone'})
            sess.update({'name': name, 'stage': 'collecting_phone'})
            save_data()
            msg = f"Got it {name}! Please send your phone number." if lang == 'en' else f"تمام {name}، أرسل رقم هاتفك للتواصل."
            send_fb(sender_id, msg)
            add_to_conversation(sender_id, 'أحمد', msg)
        else:
            msg = "Please enter your name only." if lang == 'en' else "أدخل اسمك فقط من فضلك."
            send_fb(sender_id, msg)
        return

    # --- مرحلة: جمع رقم الهاتف ---
    if stage == 'collecting_phone':
        lang = sess.get('lang', 'ar')
        phone = extract_phone(text)

        if phone:
            update_session(sender_id, {'phone': phone, 'stage': 'done'})
            sess.update({'phone': phone, 'stage': 'done'})

            # === تسجيل الطلب الفعلي ===
            order = {
                'name': sess.get('name', ''),
                'service': sess.get('service', 'خدمة تقنية'),
                'budget': sess.get('budget', 0),
                'budget_range': sess.get('budget_range', ''),
                'phone': phone,
                'duration': sess.get('duration', ''),
                'details': sess.get('details', ''),
                'timestamp': datetime.now().isoformat(),
                'sender_id': sender_id,
                'link': f"https://www.facebook.com/messages/t/{sender_id}",
                'status': 'جديد'
            }
            order_id = add_order(order)

            if lang == 'en':
                confirm_msg = (
                    f"Your order has been registered successfully {sess.get('name','')} 👌\n"
                    f"Our team will contact you shortly to start working on your {sess.get('service','project')}.\n"
                    f"Any questions: {COMPANY_WEBSITE}"
                )
            else:
                confirm_msg = (
                    f"تم تسجيل طلبك بنجاح يا {sess.get('name','')} 👌\n"
                    f"فريقنا سيتواصل معك قريباً على رقمك لبدء العمل على {sess.get('service','مشروعك')}.\n"
                    f"أي سؤال: {COMPANY_WEBSITE}"
                )
            send_fb(sender_id, confirm_msg)
            add_log(f"✅ طلب #{order_id} مسجّل لـ {sess.get('name','')}")
            reset_session(sender_id)
            save_data()
        else:
            # رقم غير صالح - أخبره بالسبب
            msg = "That doesn't look like a valid phone number. Please send your real phone number (e.g. +1234567890)." if lang == 'en' else "هذا لا يبدو رقم هاتف صحيح. أرسل رقمك الحقيقي (مثال: 0555123456)."
            send_fb(sender_id, msg)
        return

    # --- أي مرحلة أخرى - إعادة تشغيل ---
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
    if body and body.get('object') == 'page':
        for entry in body.get('entry', []):
            for msg in entry.get('messaging', []):
                if 'message' in msg and 'text' in msg['message']:
                    sender = str(msg['sender']['id'])
                    text = msg['message']['text']
                    threading.Thread(target=process_message, args=(sender, text), daemon=True).start()
    return 'OK', 200

# ========== لوحة التحكم ==========
@app.route('/')
def home():
    stats = get_live_stats()
    html = """
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>B.Y PRO - لوحة التحكم</title>
        <style>
            * { box-sizing: border-box; font-family: system-ui, 'Segoe UI', Tahoma, sans-serif; }
            body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); margin: 0; padding: 20px; min-height: 100vh; }
            .container { max-width: 1400px; margin: 0 auto; }
            .header { background: rgba(255,255,255,0.95); border-radius: 20px; padding: 25px 30px; margin-bottom: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }
            h1 { color: #1a1a2e; margin: 0 0 8px; font-size: 1.8em; }
            .badge { background: #4ade80; color: #166534; padding: 4px 14px; border-radius: 20px; display: inline-block; font-weight: bold; font-size: 0.9em; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 15px; margin-bottom: 20px; }
            .card { background: rgba(255,255,255,0.95); border-radius: 15px; padding: 18px; box-shadow: 0 5px 15px rgba(0,0,0,0.15); text-align: center; }
            .card h3 { margin: 0 0 8px; color: #64748b; font-size: 0.85em; }
            .card .value { font-size: 2.2em; font-weight: bold; color: #2563eb; }
            .logs { background: rgba(255,255,255,0.95); border-radius: 15px; padding: 20px; margin-bottom: 20px; max-height: 200px; overflow-y: auto; }
            .log-item { padding: 4px 0; border-bottom: 1px solid #e2e8f0; font-family: monospace; font-size: 0.85em; }
            .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
            .tab-btn { background: rgba(255,255,255,0.85); border: none; padding: 10px 22px; border-radius: 30px; font-size: 0.95em; cursor: pointer; transition: all 0.2s; }
            .tab-btn:hover { background: white; }
            .tab-btn.active { background: #2563eb; color: white; }
            .tab-content { background: rgba(255,255,255,0.95); border-radius: 15px; padding: 20px; display: none; }
            .tab-content.active { display: block; }
            table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
            th { text-align: right; padding: 10px 12px; background: #f8fafc; color: #475569; font-weight: 600; }
            td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: middle; }
            .btn { background: #2563eb; color: white; border: none; padding: 5px 14px; border-radius: 15px; cursor: pointer; font-size: 0.85em; margin: 2px; transition: opacity 0.2s; }
            .btn:hover { opacity: 0.85; }
            .btn-danger { background: #dc2626; }
            .btn-success { background: #16a34a; }
            .btn-warning { background: #d97706; }
            .status-badge { padding: 3px 10px; border-radius: 12px; font-size: 0.8em; font-weight: bold; color: white; }
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); justify-content: center; align-items: center; z-index: 1000; }
            .modal-content { background: white; padding: 30px; border-radius: 15px; max-width: 500px; width: 90%; }
            .refresh-note { color: rgba(255,255,255,0.6); font-size: 0.8em; text-align: center; margin-top: 15px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤵 B.Y PRO - مساعد المبيعات التقني</h1>
                <div class="badge">✅ النظام يعمل</div>
                <p style="margin: 8px 0 0; color: #64748b; font-size: 0.9em;">
                    ⏱ بدء: {{ start_time }} &nbsp;|&nbsp; 💰 Binance: <code style="background:#f1f5f9;padding:2px 8px;border-radius:5px;">{{ binance_id }}</code>
                </p>
            </div>

            <div class="stats-grid">
                <div class="card"><h3>العملاء الفريدون</h3><div class="value">{{ unique_clients }}</div></div>
                <div class="card"><h3>إجمالي الطلبات</h3><div class="value">{{ orders_count }}</div></div>
                <div class="card"><h3>طلبات اليوم</h3><div class="value">{{ today_orders }}</div></div>
                <div class="card"><h3>المحظورون</h3><div class="value">{{ blocked_count }}</div></div>
                <div class="card"><h3>المدراء</h3><div class="value">{{ verified_count }}</div></div>
                <div class="card"><h3>رسائل واردة</h3><div class="value">{{ msgs_received }}</div></div>
            </div>

            <div class="logs">
                <h3 style="margin: 0 0 10px; color: #1a1a2e;">📋 آخر الأحداث</h3>
                {% for log in logs %}
                <div class="log-item">[{{ log.time }}] {{ log.msg }}</div>
                {% endfor %}
            </div>

            <div class="tabs">
                <button class="tab-btn active" onclick="showTab('orders', event)">📦 الطلبات ({{ orders_count }})</button>
                <button class="tab-btn" onclick="showTab('clients', event)">👥 العملاء</button>
                <button class="tab-btn" onclick="showTab('blocked', event)">🚫 المحظورون ({{ blocked_count }})</button>
                <button class="tab-btn" onclick="showTab('verified', event)">🔐 المدراء ({{ verified_count }})</button>
                <button class="tab-btn" onclick="showTab('commands', event)">⚙️ الأوامر</button>
            </div>

            <div id="orders" class="tab-content active">
                <h3>📦 جميع الطلبات</h3>
                <table>
                    <tr><th>#</th><th>الاسم</th><th>الخدمة</th><th>الميزانية</th><th>الهاتف</th><th>المدة</th><th>الحالة</th><th>ملاحظات</th><th>التاريخ</th><th>الإجراءات</th></tr>
                    {% for o in orders %}
                    <tr>
                        <td>{{ o.id }}</td>
                        <td><a href="{{ o.link }}" target="_blank">{{ o.name }}</a></td>
                        <td>{{ o.service }}</td>
                        <td>{{ o.get('budget_range', '') or (o.budget|string + '$') }}</td>
                        <td>{{ o.get('phone', '-') }}</td>
                        <td>{{ o.get('duration', '-') }}</td>
                        <td>
                            <span class="status-badge" style="background: {% if o.status == 'مكتمل' %}#16a34a{% else %}#d97706{% endif %}">
                                {{ o.status }}
                            </span>
                        </td>
                        <td>{{ order_notes.get(o.id|string, '') }}</td>
                        <td style="font-size:0.8em;">{{ o.get('timestamp','')[:16] }}</td>
                        <td>
                            <button class="btn btn-success" onclick="markComplete({{ o.id }})">✔️</button>
                            <button class="btn btn-warning" onclick="addNote({{ o.id }})">📝</button>
                            <button class="btn btn-danger" onclick="deleteOrder({{ o.id }})">🗑️</button>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div id="clients" class="tab-content">
                <h3>👥 العملاء المسجلون</h3>
                <table>
                    <tr><th>الاسم</th><th>الهاتف</th><th>عدد الطلبات</th><th>آخر طلب</th><th>محادثة</th></tr>
                    {% for client in clients %}
                    <tr>
                        <td>{{ client.name }}</td>
                        <td>{{ client.phone }}</td>
                        <td>{{ client.order_count }}</td>
                        <td>{{ client.last_date[:10] }}</td>
                        <td><a href="{{ client.link }}" target="_blank">🔗 فتح</a></td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div id="blocked" class="tab-content">
                <h3>🚫 المستخدمون المحظورون</h3>
                <table>
                    <tr><th>معرف المستخدم</th><th>الإجراء</th></tr>
                    {% for uid in blocked_list %}
                    <tr>
                        <td>{{ uid }}</td>
                        <td><button class="btn btn-success" onclick="unblockUser('{{ uid }}')">رفع الحظر</button></td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div id="verified" class="tab-content">
                <h3>🔐 المدراء الموثقون</h3>
                <table>
                    <tr><th>معرف المستخدم</th><th>الإجراء</th></tr>
                    {% for uid in verified_list %}
                    <tr>
                        <td>{{ uid }}</td>
                        <td><button class="btn btn-danger" onclick="removeAdmin('{{ uid }}')">إزالة</button></td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div id="commands" class="tab-content">
                <h3>⚙️ أوامر المدير (عبر الماسنجر)</h3>
                <table>
                    <tr><th>الأمر</th><th>الوظيفة</th></tr>
                    <tr><td><code>احصائيات</code></td><td>عرض الإحصائيات الكاملة</td></tr>
                    <tr><td><code>اي جديد</code></td><td>طلبات اليوم</td></tr>
                    <tr><td><code>كل الطلبات</code></td><td>آخر 10 طلبات</td></tr>
                    <tr><td><code>تفاصيل [رقم]</code></td><td>تفاصيل طلب محدد</td></tr>
                    <tr><td><code>مكتمل [رقم]</code></td><td>تحديث حالة الطلب</td></tr>
                    <tr><td><code>حذف [رقم]</code></td><td>حذف طلب</td></tr>
                    <tr><td><code>ملاحظة [رقم] [نص]</code></td><td>إضافة ملاحظة</td></tr>
                    <tr><td><code>حظر [معرف]</code></td><td>حظر مستخدم</td></tr>
                    <tr><td><code>الغاء حظر [معرف]</code></td><td>رفع الحظر</td></tr>
                    <tr><td><code>المحظورين</code></td><td>قائمة المحظورين</td></tr>
                    <tr><td><code>العملاء</code></td><td>قائمة العملاء</td></tr>
                </table>
            </div>
        </div>

        <div id="noteModal" class="modal">
            <div class="modal-content">
                <h3>📝 إضافة ملاحظة للطلب #<span id="noteOrderId"></span></h3>
                <textarea id="noteText" rows="4" style="width:100%;padding:10px;border-radius:8px;border:1px solid #ccc;margin-top:10px;"></textarea>
                <div style="margin-top:15px;text-align:left;">
                    <button class="btn" onclick="submitNote()">حفظ</button>
                    <button class="btn btn-danger" onclick="closeModal()">إلغاء</button>
                </div>
            </div>
        </div>

        <p class="refresh-note">⟳ تحديث تلقائي كل 30 ثانية</p>

        <script>
            function showTab(tabId, event) {
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.getElementById(tabId).classList.add('active');
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                if (event && event.target) event.target.classList.add('active');
            }
            function markComplete(id) {
                if (confirm('تأكيد إكمال الطلب #' + id + '؟')) {
                    fetch('/api/order/' + id + '/complete', {method:'POST'})
                        .then(r => r.json()).then(d => { if(d.success) location.reload(); });
                }
            }
            function deleteOrder(id) {
                if (confirm('حذف الطلب #' + id + '؟ لا يمكن التراجع.')) {
                    fetch('/api/order/' + id + '/delete', {method:'POST'})
                        .then(r => r.json()).then(d => { if(d.success) location.reload(); });
                }
            }
            function addNote(id) {
                document.getElementById('noteOrderId').innerText = id;
                document.getElementById('noteModal').style.display = 'flex';
            }
            function submitNote() {
                const id = document.getElementById('noteOrderId').innerText;
                const note = document.getElementById('noteText').value;
                fetch('/api/order/' + id + '/note', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({note:note})
                }).then(r => r.json()).then(d => { if(d.success) location.reload(); });
            }
            function closeModal() {
                document.getElementById('noteModal').style.display = 'none';
                document.getElementById('noteText').value = '';
            }
            function unblockUser(uid) {
                if (confirm('رفع الحظر عن ' + uid + '؟')) {
                    fetch('/api/unblock/' + uid, {method:'POST'})
                        .then(r => r.json()).then(d => { if(d.success) location.reload(); });
                }
            }
            function removeAdmin(uid) {
                if (confirm('إزالة المدير ' + uid + '؟')) {
                    fetch('/api/remove_admin/' + uid, {method:'POST'})
                        .then(r => r.json()).then(d => { if(d.success) location.reload(); });
                }
            }
            window.onclick = function(e) {
                if (e.target == document.getElementById('noteModal')) closeModal();
            }
            // تحديث تلقائي كل 30 ثانية
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """
    
    orders_list = sorted(data.get('orders', []), key=lambda x: x.get('id', 0), reverse=True)[:50]
    
    clients_dict = {}
    for o in data.get('orders', []):
        name = o.get('name', '')
        if name:
            if name not in clients_dict:
                clients_dict[name] = {
                    'name': name,
                    'phone': o.get('phone', '-'),
                    'order_count': 0,
                    'last_date': o.get('timestamp', ''),
                    'link': o.get('link', '')
                }
            clients_dict[name]['order_count'] += 1
            if o.get('timestamp', '') > clients_dict[name]['last_date']:
                clients_dict[name]['last_date'] = o['timestamp']
                clients_dict[name]['phone'] = o.get('phone', '-')
    
    clients_list = sorted(clients_dict.values(), key=lambda x: x['last_date'], reverse=True)

    return render_template_string(html,
        start_time=data['stats'].get('start_time', '')[:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        unique_clients=stats['unique_clients'],
        orders_count=stats['total_orders'],
        today_orders=stats['today_orders'],
        blocked_count=stats['blocked'],
        verified_count=stats['verified'],
        msgs_received=stats['msgs_received'],
        logs=list(logs)[:20],
        orders=orders_list,
        order_notes=data.get('order_notes', {}),
        clients=clients_list[:50],
        blocked_list=data.get('blocked', [])[-50:],
        verified_list=data.get('verified', [])[-50:]
    )

# ========== APIs اللوحة ==========
@app.route('/api/order/<int:order_id>/complete', methods=['POST'])
def api_complete(order_id):
    return jsonify({'success': update_order(order_id, {'status': 'مكتمل'})})

@app.route('/api/order/<int:order_id>/delete', methods=['POST'])
def api_delete(order_id):
    delete_order(order_id)
    return jsonify({'success': True})

@app.route('/api/order/<int:order_id>/note', methods=['POST'])
def api_note(order_id):
    note = request.json.get('note', '')
    add_note_to_order(order_id, note)
    return jsonify({'success': True})

@app.route('/api/unblock/<user_id>', methods=['POST'])
def api_unblock(user_id):
    if user_id in data.get('blocked', []):
        data['blocked'].remove(user_id)
        save_data()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/remove_admin/<user_id>', methods=['POST'])
def api_remove_admin(user_id):
    if user_id in data.get('verified', []):
        data['verified'].remove(user_id)
        save_data()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/stats')
def api_stats():
    return jsonify(get_live_stats())

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
    print("🚀 B.Y PRO Agent - النسخة المُصلحة الكاملة")
    print("="*70)
    print(f"👤 Owner ID: {OWNER_FB_ID}")
    print(f"🔑 Password: {OWNER_PASSWORD}")
    print(f"💰 Binance: {BINANCE_ID}")
    print(f"📦 Orders in DB: {len(data.get('orders', []))}")
    print(f"📊 JSONBin ID: {BIN_ID}")
    print(f"🌐 Self URL: {SELF_URL}")
    print("="*70 + "\n")

    threading.Thread(target=keep_alive_loop, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
