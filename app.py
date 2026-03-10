import os
import re
import json
import requests
import time
import threading
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from collections import deque

import os as _os
app = Flask(__name__, static_folder=_os.path.join(_os.path.dirname(__file__), 'static'), static_url_path='')

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

# ========== شخصية البوت - بشرية وطبيعية ==========
BOT_PERSONALITY = """أنت "أحمد"، مستشار مبيعات في شركة B.Y PRO للتكنولوجيا والبرمجيات.

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
- أجب بنفس لغة العميل (عربي أو إنجليزي).
- إذا سألك عن شيء تقني خارج نطاقك، قل له "أحوّلك للفريق التقني".

الخدمات والأسعار التقريبية (استخدمها كمرجع فقط، السعر الفعلي يتحدد حسب التفاصيل):
- موقع تعريفي: 300-800$ (5-10 أيام)
- متجر إلكتروني: 700-1800$ (15-25 يوم)
- بوت ذكاء اصطناعي: 500-2000$ (حسب التعقيد)
- تطبيق جوال: من 1500$ (30-60 يوم)
- تصميم جرافيك / شعار: 50-200$ (24-72 ساعة)
- برنامج مخصص: من 1000$ (حسب المشروع)

طريقة الدفع: 30% مقدماً، 70% بعد التسليم، عبر USDT (Binance Pay) معرف: 1074084246

مهم جداً: لا تسجّل الطلب ولا تطلب البيانات إلا بعد أن يوافق العميل صراحةً على السعر والمدة."""

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
def ask_ai(user_msg, sess, extra_instruction=""):
    context = "\n".join(sess.get('conversation', [])[-12:])
    
    stage_hints = {
        'explore': "أنت تستمع لطلب العميل وتفهم احتياجه. اسأل سؤالاً أو سؤالين بسيطين لتفهم المشروع، ثم قدّم له السعر والمدة.",
        'price_proposed': "لقد اقترحت سعراً للعميل. انتظر موافقته. لا تضيف معلومات جديدة.",
        'awaiting_confirmation': "العميل على وشك الموافقة أو الرفض. إذا وافق، اطلب اسمه الكريم فقط.",
        'collecting_name': "اطلب من العميل اسمه الكريم فقط. رسالة واحدة مختصرة.",
        'collecting_phone': f"اسم العميل هو: {sess.get('name', '')}. اطلب منه رقم هاتفه الآن. رسالة مختصرة.",
    }
    
    stage = sess.get('stage', 'explore')
    hint = stage_hints.get(stage, "")
    
    full_prompt = (
        f"{BOT_PERSONALITY}\n\n"
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
    if body and body.get('object') == 'page':
        for entry in body.get('entry', []):
            for msg in entry.get('messaging', []):
                if 'message' in msg and 'text' in msg['message']:
                    sender = str(msg['sender']['id'])
                    text = msg['message']['text']
                    threading.Thread(target=process_message, args=(sender, text), daemon=True).start()
    return 'OK', 200

# ========== لوحة التحكم (index.html) ==========
@app.route('/')
def home():
    return app.send_static_file('index.html')
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

# ========== APIs الجديدة للوحة ==========

@app.route('/api/dashboard')
def api_dashboard():
    """بيانات شاملة للوحة"""
    stats = get_live_stats()
    orders = data.get('orders', [])
    
    # تصنيف الطلبات حسب الخدمة
    service_counts = {}
    for o in orders:
        svc = o.get('service', 'أخرى')
        service_counts[svc] = service_counts.get(svc, 0) + 1
    
    # إحصائيات آخر 7 أيام
    from datetime import timedelta
    daily = {}
    for i in range(7):
        day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        daily[day] = {'orders': 0, 'msgs': 0}
    for o in orders:
        day = o.get('timestamp', '')[:10]
        if day in daily:
            daily[day]['orders'] += 1
    
    completed = len([o for o in orders if o.get('status') == 'مكتمل'])
    
    return jsonify({
        'stats': stats,
        'service_breakdown': service_counts,
        'daily': daily,
        'completed': completed,
        'pending': len(orders) - completed,
        'start_time': data['stats'].get('start_time', ''),
        'logs': list(logs)[:30]
    })

@app.route('/api/orders')
def api_orders():
    """كل الطلبات مع البحث"""
    q = request.args.get('q', '').lower()
    status = request.args.get('status', '')
    orders = data.get('orders', [])
    if q:
        orders = [o for o in orders if q in o.get('name','').lower() or q in o.get('service','').lower() or q in o.get('phone','').lower()]
    if status:
        orders = [o for o in orders if o.get('status','') == status]
    orders_with_notes = []
    for o in reversed(orders[-100:]):
        o2 = dict(o)
        o2['note'] = data.get('order_notes', {}).get(str(o.get('id','')), '')
        orders_with_notes.append(o2)
    return jsonify(orders_with_notes)

@app.route('/api/clients')
def api_clients():
    """قائمة العملاء مع محادثاتهم"""
    q = request.args.get('q', '').lower()
    sessions = data.get('sessions', {})
    orders = data.get('orders', [])
    
    clients = {}
    for o in orders:
        sid = o.get('sender_id', '')
        name = o.get('name', '')
        if not name:
            continue
        if sid not in clients:
            clients[sid] = {
                'id': sid,
                'name': name,
                'phone': o.get('phone', ''),
                'link': o.get('link', ''),
                'orders': [],
                'last_seen': o.get('timestamp', ''),
                'conversation': sessions.get(sid, {}).get('conversation', [])
            }
        clients[sid]['orders'].append({'service': o.get('service'), 'budget': o.get('budget'), 'status': o.get('status')})
        if o.get('timestamp','') > clients[sid]['last_seen']:
            clients[sid]['last_seen'] = o.get('timestamp','')
    
    result = list(clients.values())
    if q:
        result = [c for c in result if q in c['name'].lower() or q in c.get('phone','').lower()]
    result.sort(key=lambda x: x['last_seen'], reverse=True)
    return jsonify(result[:100])

@app.route('/api/admins')
def api_admins():
    """قائمة المدراء"""
    return jsonify({
        'owner': OWNER_FB_ID,
        'verified': data.get('verified', [])
    })

@app.route('/api/admin/test/<user_id>', methods=['POST'])
def api_test_admin(user_id):
    """اختبار صلاحية مدير"""
    result = send_fb(user_id, f"🔐 Admin verification test. Please reply with the admin password.")
    return jsonify({'success': result})

@app.route('/api/admin/remove/<user_id>', methods=['POST'])
def api_admin_remove(user_id):
    if user_id in data.get('verified', []):
        data['verified'].remove(user_id)
        if user_id not in data.get('blocked', []):
            data['blocked'].append(user_id)
        save_data()
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """قراءة الإعدادات"""
    return jsonify({
        'binance_id': BINANCE_ID,
        'bot_prompt': BOT_PERSONALITY,
        'owner_prompt': OWNER_PERSONALITY,
        'ai_api_url': AI_API_URL,
        'company_website': COMPANY_WEBSITE,
        'self_url': SELF_URL,
        'fb_page': 'https://www.facebook.com/bypro2007',
        'store_url': 'https://store-pro.great-site.net',
        'store_support': 'https://t.me/STOREPROSPRT'
    })

@app.route('/api/settings', methods=['POST'])
def api_save_settings():
    """حفظ الإعدادات"""
    global BOT_PERSONALITY, OWNER_PERSONALITY, BINANCE_ID, AI_API_URL
    body = request.json or {}
    if 'bot_prompt' in body:
        BOT_PERSONALITY = body['bot_prompt']
    if 'owner_prompt' in body:
        OWNER_PERSONALITY = body['owner_prompt']
    if 'binance_id' in body:
        BINANCE_ID = body['binance_id']
    if 'ai_api_url' in body:
        AI_API_URL = body['ai_api_url']
    add_log("⚙️ Settings updated from dashboard")
    return jsonify({'success': True})

@app.route('/api/logs')
def api_logs():
    return jsonify(list(logs)[:50])

@app.route('/api/reset', methods=['POST'])
def api_reset():
    """إعادة تعيين - يحذف الرسائل والإحصائيات فقط"""
    body = request.json or {}
    if body.get('password') != OWNER_PASSWORD:
        return jsonify({'success': False, 'error': 'Wrong password'}), 403
    
    owner = data.get('verified', [])[:1]  # الاحتفاظ بالمدير الأول فقط
    data['orders'] = []
    data['sessions'] = {}
    data['order_notes'] = {}
    data['blocked'] = []
    data['verified'] = owner
    data['stats'] = {
        'msgs_received': 0,
        'msgs_sent': 0,
        'start_time': datetime.now().isoformat()
    }
    save_data()
    add_log("🔄 System reset from dashboard")
    return jsonify({'success': True})

@app.route('/api/block/<user_id>', methods=['POST'])
def api_block_user(user_id):
    if 'blocked' not in data:
        data['blocked'] = []
    if user_id not in data['blocked']:
        data['blocked'].append(user_id)
        save_data()
    return jsonify({'success': True})
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
