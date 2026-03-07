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
OWNER_FB_ID = os.environ.get('OWNER_FB_ID', '2592319994')
OWNER_PASSWORD = os.environ.get('OWNER_PASSWORD', '20070909')
BIN_ID = os.environ.get('BIN_ID')
X_MASTER_KEY = os.environ.get('X_MASTER_KEY')
X_ACCESS_KEY = os.environ.get('X_ACCESS_KEY')
BINANCE_ID = os.environ.get('BINANCE_ID', '1074084246')
AI_API_URL = os.environ.get('AI_API_URL', 'http://fi8.bot-hosting.net:20163/elos-gemina')
COMPANY_WEBSITE = os.environ.get('COMPANY_WEBSITE', 'https://b.y-pro.kesug.com')

# ========== البرومبت الكامل ==========
BOT_PERSONALITY = """أنت مساعد مبيعات B.Y PRO الرسمي.

هويتك المهنية: أنت وكيل مبيعات بشري محنك، تعمل لصالح شركة B.Y PRO للتكنولوجيا والبرمجيات. أنت هادئ، واثق، ومختصر جداً في حديثك. لا تتصرف كآلة، لا تستخدم الرموز التعبيرية بكثرة، ولا تكرر الجمل الترحيبية المملة.

مبادئ التواصل البشري المحترف:
1. الاختصار الذكي: أجب على قدر السؤال بدقة. الزبون يقدر وقته، وأنت تقدر وقتك. لا تشرح أساسيات التقنية إلا إذا طلب الزبون ذلك.
2. التكيف اللغوي: ابدأ الحوار فوراً بنفس لغة المستخدم (عربية، إنجليزية، فرنسية، إلخ). استخدم لغة بيضاء احترافية وراقية.
3. عدم الإلحاح: إذا قدمت العرض ولم يرد الزبون، لا تلاحقه بالرسائل. نحن شركة تطلبها النخبة، وقطار B.Y PRO لا يتوقف لانتظار أحد.
4. السرية المطلقة: يمنع ذكر اسم المدير (السيد ياسين)، عدد الموظفين، أسماء الأعضاء، أو تفاصيل الوكلاء في الدول. إذا سُئلت عن المقر، قل: "نحن كيان رقمي دولي بمركز عمليات في شمال أفريقيا (الجزائر)، ولدينا انتشار عالمي مدروس".

قائمة الخدمات والأسعار المتوسطة (سوق 2026):
- المواقع التعريفية (Portfolio/Business): بين 300$ إلى 800$. (المدة: 5-10 أيام).
- المتاجر الإلكترونية (E-commerce): بين 700$ إلى 1800$. (المدة: 15-25 يوماً).
- أنظمة الأتمتة وبوتات الذكاء الاصطناعي: تبدأ من 300$. (المدة: 7-14 يوماً).
- تطبيقات الموبايل (Android/iOS): تبدأ من 1500$. (المدة: 30-60 يوماً).
- التصميم الجرافيكي والمونتاج الاحترافي: 50$ - 200$. (المدة: 24-72 ساعة).

بروتوكول التعامل المالي:
- القاعدة الثابتة: نظام (30% عربون مقدم) لبدء التنفيذ، و (70% عند التسليم النهائي).
- وسيلة الدفع: USDT (Binance Pay) حصراً لضمان سرعة التعامل الدولي. معرف بينانس: 1074084246.
- التفاوض: إذا حاول الزبون خفض السعر بشكل مبالغ، قل بلباقة: "أسعارنا تعكس معايير الجودة والالتزام الصارم بالمواعيد في B.Y PRO، نعتذر عن عدم تقديم خصومات إضافية حالياً".

الهدف النهائي: تحويل الاستفسار إلى "مشروع قائم" وإرسال تفاصيل الدفع للزبون الجاد فقط."""

# ========== تخزين JSONBin.io مع تحميل آمن ==========
def jsonbin_read():
    """قراءة جميع البيانات من JSONBin.io مع التحقق من وجود المفاتيح"""
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {
        'X-Master-Key': X_MASTER_KEY,
        'X-Access-Key': X_ACCESS_KEY
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            record = resp.json().get('record', {})
            # التأكد من وجود جميع المفاتيح الأساسية
            if not isinstance(record, dict):
                record = {}
            return record
        else:
            print(f"JSONBin read error: {resp.status_code}")
            return {}
    except Exception as e:
        print(f"JSONBin read exception: {e}")
        return {}

def jsonbin_write(data):
    """كتابة جميع البيانات إلى JSONBin.io"""
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': X_MASTER_KEY,
        'X-Access-Key': X_ACCESS_KEY
    }
    try:
        resp = requests.put(url, json=data, headers=headers, timeout=10)
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

# تحميل البيانات مع التأكد من وجود جميع المفاتيح
loaded_data = jsonbin_read()
if loaded_data:
    # دمج البيانات المحملة مع الهيكل الافتراضي (للتأكد من وجود كل المفاتيح)
    data = DEFAULT_DATA.copy()
    for key in data:
        if key in loaded_data:
            data[key] = loaded_data[key]
else:
    data = DEFAULT_DATA.copy()
    # حفظ الهيكل الافتراضي في JSONBin
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
            save_data()
            add_log(f"📤 إلى {recipient_id[:10]}...: {text[:40]}")
            return True
        else:
            add_log(f"❌ فشل الإرسال: {r.status_code}")
            return False
    except Exception as e:
        add_log(f"❌ خطأ في الإرسال: {e}")
        return False

# ========== حفظ البيانات ==========
def save_data():
    """حفظ البيانات إلى JSONBin.io مع التحقق من النجاح"""
    success = jsonbin_write(data)
    if success:
        add_log("💾 تم حفظ البيانات في JSONBin")
    else:
        add_log("⚠️ فشل حفظ البيانات في JSONBin")
    return success

# ========== التحقق من المدير ==========
def is_owner(sender_id):
    return sender_id == OWNER_FB_ID or sender_id in data.get('verified', [])

# ========== دوال الطلبات ==========
def add_order(order_dict):
    if 'orders' not in data:
        data['orders'] = []
    order_dict['id'] = len(data['orders']) + 1
    data['orders'].append(order_dict)
    save_data()
    add_log(f"✅ طلب جديد #{order_dict['id']} - {order_dict['name']}")
    # إشعار المدير على ماسنجر
    notify_msg = f"🔔 طلب جديد #{order_dict['id']}\n{order_dict['name']} - {order_dict['service']} - {order_dict['budget']}$\nhttps://www.facebook.com/messages/t/{order_dict['sender_id']}"
    send_fb(OWNER_FB_ID, notify_msg)
    return order_dict['id']

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

def get_order(order_id):
    for o in data.get('orders', []):
        if o['id'] == order_id:
            return o
    return None

def add_note(order_id, note):
    if 'order_notes' not in data:
        data['order_notes'] = {}
    data['order_notes'][str(order_id)] = note
    save_data()

def get_today_orders():
    if 'orders' not in data:
        return []
    today = datetime.now().strftime('%Y-%m-%d')
    return [o for o in data['orders'] if o.get('timestamp', '').startswith(today)]

def get_unique_clients_count():
    if 'orders' not in data:
        return 0
    return len(set(o.get('sender_id', '') for o in data['orders'] if o.get('sender_id')))

# ========== إدارة الجلسات ==========
def get_session(sender_id):
    """استرجاع جلسة المستخدم مع التأكد من وجودها"""
    if 'sessions' not in data:
        data['sessions'] = {}
    if sender_id not in data['sessions']:
        data['sessions'][sender_id] = {
            'name': '',
            'service': '',
            'budget': 0,
            'phone': '',
            'confirmed': False,
            'conversation': [],
            'awaiting_password': False,
            'lang': 'ar'
        }
        save_data()
    return data['sessions'][sender_id]

def update_session(sender_id, updates):
    if 'sessions' not in data:
        data['sessions'] = {}
    if sender_id in data['sessions']:
        data['sessions'][sender_id].update(updates)
        save_data()

def add_to_conversation(sender_id, role, message):
    """إضافة رسالة إلى سجل المحادثة مع الحفاظ على آخر 10 رسائل"""
    sess = get_session(sender_id)
    sess['conversation'].append(f"{role}: {message}")
    if len(sess['conversation']) > 10:
        sess['conversation'] = sess['conversation'][-10:]
    save_data()

# ========== استخراج بيانات العميل ==========
def extract_client_data(text, sess):
    updated = False
    # الاسم
    if not sess.get('name'):
        patterns = [
            r'(?:اسمي|الاسم)[:\s]*([\w\s]{2,30})',
            r'my name is[:\s]*([a-zA-Z\s]{2,30})',
            r'انا\s+([\w\s]{2,20})'
        ]
        for p in patterns:
            m = re.search(p, text, re.I)
            if m:
                sess['name'] = m.group(1).strip()
                add_log(f"📝 الاسم: {sess['name']}")
                updated = True
                break
    # الخدمة
    if not sess.get('service'):
        services = {
            'شعار|logo|لوجو': 'تصميم شعار',
            'موقع|website|web': 'تصميم موقع',
            'متجر|ecommerce|store': 'متجر إلكتروني',
            'تطبيق|app|mobile': 'تطبيق جوال',
            'بوت|bot|chatbot': 'بوت ذكاء اصطناعي',
            'تصميم|design|graphic': 'تصميم جرافيك'
        }
        for kw, svc in services.items():
            if re.search(kw, text, re.I):
                sess['service'] = svc
                add_log(f"🛠 الخدمة: {svc}")
                updated = True
                break
    # الميزانية
    if sess.get('budget', 0) == 0:
        m = re.search(r'(\d+)[\s-]*(?:usdt|\$|دولار)', text, re.I)
        if m:
            sess['budget'] = int(m.group(1))
            add_log(f"💰 الميزانية: {sess['budget']}$")
            updated = True
    # رقم الجوال
    if not sess.get('phone'):
        m = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9}|00966[0-9]{9})', text)
        if m:
            sess['phone'] = m.group(1)
            add_log(f"📱 الجوال: {sess['phone']}")
            updated = True
    return updated

# ========== الذكاء الاصطناعي ==========
def ask_ai(user_msg, sess, is_owner=False):
    # بناء السياق من آخر 8 رسائل
    context = "\n".join(sess.get('conversation', [])[-8:])
    system = BOT_PERSONALITY
    if is_owner:
        system += "\n\nالمستخدم هو المدير. أجب باختصار شديد وباحترام."
    prompt = f"{system}\n\nسجل المحادثة:\n{context}\n\nالمستخدم: {user_msg}\nالرد:"
    try:
        url = f'{AI_API_URL}?text={requests.utils.quote(prompt)}'
        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            answer = r.json().get('response', '').strip()
            return answer[:1800]
        else:
            add_log(f"⚠️ الذكاء الاصطناعي رد بـ {r.status_code}")
    except Exception as e:
        add_log(f"❌ خطأ في الذكاء الاصطناعي: {e}")
    return "عذراً، حدث خطأ تقني. حاول مرة أخرى."

# ========== أوامر المدير ==========
def handle_owner_command(text, sender_id):
    cmd = text.strip().lower()
    parts = cmd.split()

    # إحصائيات
    if any(k in cmd for k in ['احصائيات', 'stats', 'احصاء']):
        today_ords = len(get_today_orders())
        unique_clients = get_unique_clients_count()
        msg = f"""📊 إحصائيات:
• العملاء الفريدون: {unique_clients}
• إجمالي الطلبات: {len(data.get('orders', []))}
• طلبات اليوم: {today_ords}
• المحظورون: {len(data.get('blocked', []))}
• الموثوقون: {len(data.get('verified', []))}
• الرسائل المستلمة: {data['stats']['msgs_received']}
• الرسائل المرسلة: {data['stats']['msgs_sent']}"""
        send_fb(sender_id, msg)
        return True

    # طلبات اليوم
    if any(k in cmd for k in ['طلبات اليوم', 'اليوم']):
        today_ords = get_today_orders()
        if not today_ords:
            send_fb(sender_id, "لا توجد طلبات اليوم.")
        else:
            msg = f"طلبات اليوم ({len(today_ords)}):\n"
            for o in today_ords[-10:]:
                msg += f"#{o['id']} {o['name']} - {o['service']} - {o['budget']}$\n"
            send_fb(sender_id, msg)
        return True

    # كل الطلبات
    if any(k in cmd for k in ['كل الطلبات', 'جميع الطلبات']):
        orders_list = data.get('orders', [])
        if not orders_list:
            send_fb(sender_id, "لا توجد طلبات.")
        else:
            msg = f"آخر 10 طلبات من أصل {len(orders_list)}:\n"
            for o in orders_list[-10:]:
                msg += f"#{o['id']} {o['name']} - {o['service']} - {o['budget']}$\n"
            send_fb(sender_id, msg)
        return True

    # تفاصيل طلب
    if 'تفاصيل' in cmd:
        nums = [int(p) for p in parts if p.isdigit()]
        if nums:
            o = get_order(nums[0])
            if o:
                note = data.get('order_notes', {}).get(str(o['id']), '')
                msg = f"""📋 الطلب #{o['id']}
الاسم: {o['name']}
الخدمة: {o['service']}
الميزانية: {o['budget']}$
الجوال: {o.get('phone', 'غير متوفر')}
التاريخ: {o['timestamp'][:10]}
الحالة: {o.get('status', 'جديد')}
ملاحظات: {note}
رابط: {o['link']}"""
                send_fb(sender_id, msg)
            else:
                send_fb(sender_id, f"الطلب {nums[0]} غير موجود.")
        return True

    # اعرض العملاء
    if any(k in cmd for k in ['اعرض العملاء', 'اسمائهم']):
        orders_list = data.get('orders', [])
        if not orders_list:
            send_fb(sender_id, "لا يوجد عملاء.")
        else:
            names = list(set(o.get('name', '') for o in orders_list if o.get('name')))
            msg = f"العملاء المسجلون ({len(names)}):\n" + "\n".join([f"• {n}" for n in names[-15:]])
            send_fb(sender_id, msg)
        return True

    # المحظورون
    if any(k in cmd for k in ['المحظورين', 'blocked']):
        blocked = data.get('blocked', [])
        if not blocked:
            send_fb(sender_id, "لا يوجد محظورون.")
        else:
            bl = "\n".join([f"• {uid[:15]}..." for uid in blocked[-15:]])
            send_fb(sender_id, f"المحظورون ({len(blocked)}):\n{bl}")
        return True

    # حظر مستخدم
    if cmd.startswith('حظر ') or cmd.startswith('block '):
        if len(parts) >= 2 and parts[1].isdigit():
            target = parts[1]
            if 'blocked' not in data:
                data['blocked'] = []
            if target not in data['blocked']:
                data['blocked'].append(target)
                save_data()
                send_fb(sender_id, f"✅ تم حظر {target[:15]}...")
                add_log(f"🔨 حظر {target[:15]}...")
            else:
                send_fb(sender_id, "المستخدم محظور بالفعل.")
        return True

    # إلغاء حظر
    if cmd.startswith('الغاء حظر ') or cmd.startswith('unblock '):
        if len(parts) >= 2:
            target = parts[1]
            blocked = data.get('blocked', [])
            if target in blocked:
                data['blocked'].remove(target)
                save_data()
                send_fb(sender_id, f"✅ تم إلغاء حظر {target[:15]}...")
            else:
                send_fb(sender_id, "المستخدم غير موجود في قائمة المحظورين.")
        return True

    # إضافة ملاحظة
    if 'ملاحظة' in cmd:
        nums = [int(p) for p in parts if p.isdigit()]
        if nums:
            order_id = nums[0]
            note_text = ' '.join(parts[parts.index(str(order_id)) + 1:])
            if note_text:
                if 'order_notes' not in data:
                    data['order_notes'] = {}
                data['order_notes'][str(order_id)] = note_text
                save_data()
                send_fb(sender_id, f"✅ تم إضافة ملاحظة للطلب #{order_id}")
            else:
                send_fb(sender_id, "يرجى كتابة الملاحظة بعد رقم الطلب.")
        return True

    # تغيير حالة الطلب
    if any(k in cmd for k in ['مكتمل', 'complete']) and any(p.isdigit() for p in parts):
        nums = [int(p) for p in parts if p.isdigit()]
        if nums:
            order_id = nums[0]
            if update_order(order_id, {'status': 'مكتمل'}):
                send_fb(sender_id, f"✅ تم تحديث الطلب #{order_id} إلى مكتمل")
            else:
                send_fb(sender_id, f"الطلب {order_id} غير موجود.")
        return True

    # حذف طلب
    if 'حذف' in cmd and any(p.isdigit() for p in parts):
        nums = [int(p) for p in parts if p.isdigit()]
        if nums:
            order_id = nums[0]
            delete_order(order_id)
            send_fb(sender_id, f"✅ تم حذف الطلب #{order_id}")
        return True

    # عدد الرسائل
    if 'كم رسالة' in cmd:
        send_fb(sender_id, f"إجمالي الرسائل المستلمة: {data['stats']['msgs_received']}, المرسلة: {data['stats']['msgs_sent']}")
        return True

    # عدد العملاء
    if 'كم عميل' in cmd:
        send_fb(sender_id, f"عدد العملاء الفريدين: {get_unique_clients_count()}")
        return True

    return False

# ========== المعالجة الرئيسية ==========
def process_message(sender_id, text):
    # تحديث الإحصائيات
    data['stats']['msgs_received'] += 1
    save_data()
    add_log(f"📨 من {sender_id[:10]}...: {text[:40]}")

    # التحقق من الحظر
    if sender_id in data.get('blocked', []):
        add_log(f"🚫 مستخدم محظور {sender_id[:10]}... تم تجاهل الرسالة")
        return

    # استرجاع جلسة المستخدم
    sess = get_session(sender_id)

    # إضافة الرسالة إلى سجل المحادثة
    add_to_conversation(sender_id, 'المستخدم', text)

    # 1. إذا كان المرسل هو المدير
    if is_owner(sender_id):
        if handle_owner_command(text, sender_id):
            return
        reply = ask_ai(text, sess, is_owner=True)
        send_fb(sender_id, reply)
        add_to_conversation(sender_id, 'النظام', reply)
        return

    # 2. إذا كان المستخدم في مرحلة إدخال كلمة المرور
    if sess.get('awaiting_password'):
        if text.strip() == OWNER_PASSWORD:
            if sender_id not in data.get('verified', []):
                if 'verified' not in data:
                    data['verified'] = []
                data['verified'].append(sender_id)
                save_data()
            sess['awaiting_password'] = False
            update_session(sender_id, {'awaiting_password': False})
            send_fb(sender_id, "أهلاً بك يا مدير.")
            add_log(f"🔐 مدير جديد: {sender_id[:10]}...")
        else:
            send_fb(sender_id, "❌ كلمة المرور غير صحيحة.")
        return

    # 3. كشف محاولة انتحال المدير
    if any(k in text.lower() for k in ['مدير', 'owner', 'المالك', 'ياسين']):
        sess['awaiting_password'] = True
        update_session(sender_id, {'awaiting_password': True})
        send_fb(sender_id, "🔐 الرجاء إدخال الرقم السري:")
        return

    # 4. استخراج بيانات العميل
    extract_client_data(text, sess)
    update_session(sender_id, sess)

    # 5. التحقق من اكتمال البيانات
    if sess.get('name') and sess.get('service') and sess.get('budget', 0) > 0 and not sess.get('confirmed', False):
        sess['confirmed'] = True
        update_session(sender_id, {'confirmed': True})

        order = {
            'name': sess['name'],
            'service': sess['service'],
            'budget': sess['budget'],
            'phone': sess.get('phone', ''),
            'timestamp': datetime.now().isoformat(),
            'sender_id': sender_id,
            'link': f"https://www.facebook.com/messages/t/{sender_id}",
            'status': 'جديد'
        }
        order_id = add_order(order)

        deposit = int(sess['budget'] * 0.3)
        pay_msg = f"""تم تأكيد طلبك {sess['name']}.

الخدمة: {sess['service']}
المبلغ: {sess['budget']}$ (المقدم {deposit}$)

للدفع عبر USDT (Binance):
المعرف: {BINANCE_ID}

بعد الدفع نبدأ التنفيذ فوراً.
للاستفسار: {COMPANY_WEBSITE}"""
        send_fb(sender_id, pay_msg)
        return

    # 6. رد عادي من الذكاء الاصطناعي
    reply = ask_ai(text, sess, is_owner=False)
    send_fb(sender_id, reply)
    add_to_conversation(sender_id, 'النظام', reply)

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data_json = request.json
    if data_json.get('object') == 'page':
        for entry in data_json.get('entry', []):
            for msg in entry.get('messaging', []):
                if 'message' in msg and 'text' in msg['message']:
                    sender = msg['sender']['id']
                    text = msg['message']['text']
                    threading.Thread(target=process_message, args=(sender, text)).start()
    return 'OK', 200

@app.route('/')
def home():
    today_ords = len(get_today_orders())
    unique_clients = get_unique_clients_count()
    
    html = """
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>B.Y PRO - لوحة التحكم</title>
        <style>
            * { box-sizing: border-box; font-family: system-ui, 'Segoe UI', Tahoma, sans-serif; }
            body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); margin: 0; padding: 20px; min-height: 100vh; }
            .container { max-width: 1400px; margin: 0 auto; }
            .header { background: white; border-radius: 20px; padding: 30px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
            h1 { color: #333; margin: 0 0 10px; font-size: 2em; }
            .badge { background: #4ade80; color: #166534; padding: 5px 15px; border-radius: 25px; display: inline-block; font-weight: bold; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
            .card { background: white; border-radius: 15px; padding: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            .card h3 { margin: 0 0 10px; color: #64748b; font-size: 1em; }
            .card .value { font-size: 2.5em; font-weight: bold; color: #2563eb; }
            .logs { background: white; border-radius: 15px; padding: 20px; margin-bottom: 20px; max-height: 250px; overflow-y: auto; }
            .log-item { padding: 5px; border-bottom: 1px solid #e2e8f0; font-family: monospace; }
            .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
            .tab-btn { background: white; border: none; padding: 12px 25px; border-radius: 30px; font-size: 1em; cursor: pointer; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            .tab-btn.active { background: #2563eb; color: white; }
            .tab-content { background: white; border-radius: 15px; padding: 20px; display: none; }
            .tab-content.active { display: block; }
            table { width: 100%; border-collapse: collapse; }
            th { text-align: right; padding: 12px; background: #f8fafc; color: #475569; font-weight: 600; }
            td { padding: 12px; border-bottom: 1px solid #e2e8f0; }
            .btn { background: #2563eb; color: white; border: none; padding: 5px 15px; border-radius: 20px; cursor: pointer; font-size: 0.9em; margin: 2px; }
            .btn-danger { background: #dc2626; }
            .btn-success { background: #16a34a; }
            .btn-warning { background: #d97706; }
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); justify-content: center; align-items: center; }
            .modal-content { background: white; padding: 30px; border-radius: 15px; max-width: 500px; width: 90%; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤵 B.Y PRO - مساعد المبيعات الرسمي</h1>
                <div class="badge">✅ النظام يعمل</div>
                <p style="margin-top: 10px;">⏱ بدء التشغيل: {{ start_time }} | 💰 بينانس: <code style="background:#f1f5f9;padding:3px 8px;border-radius:5px;">{{ binance_id }}</code></p>
            </div>

            <div class="stats-grid">
                <div class="card"><h3>العملاء الفريدون</h3><div class="value">{{ unique_clients }}</div></div>
                <div class="card"><h3>إجمالي الطلبات</h3><div class="value">{{ orders_count }}</div></div>
                <div class="card"><h3>طلبات اليوم</h3><div class="value">{{ today_orders }}</div></div>
                <div class="card"><h3>المحظورون</h3><div class="value">{{ blocked_count }}</div></div>
                <div class="card"><h3>الموثوقون</h3><div class="value">{{ verified_count }}</div></div>
                <div class="card"><h3>الرسائل المستلمة</h3><div class="value">{{ msgs_received }}</div></div>
            </div>

            <div class="logs">
                <h3>📋 آخر الأحداث</h3>
                {% for log in logs %}
                <div class="log-item">[{{ log.time }}] {{ log.msg }}</div>
                {% endfor %}
            </div>

            <div class="tabs">
                <button class="tab-btn active" onclick="showTab('orders')">📦 الطلبات</button>
                <button class="tab-btn" onclick="showTab('clients')">👥 العملاء</button>
                <button class="tab-btn" onclick="showTab('blocked')">🔨 المحظورون</button>
                <button class="tab-btn" onclick="showTab('verified')">🔐 الموثوقون</button>
                <button class="tab-btn" onclick="showTab('commands')">⚙️ الأوامر</button>
            </div>

            <div id="orders" class="tab-content active">
                <h3>📦 جميع الطلبات ({{ orders_count }})</h3>
                <table>
                    <tr><th>#</th><th>الاسم</th><th>الخدمة</th><th>الميزانية</th><th>الحالة</th><th>ملاحظات</th><th>الإجراءات</th></tr>
                    {% for o in orders %}
                    <tr>
                        <td>{{ o.id }}</td>
                        <td>{{ o.name }}</td>
                        <td>{{ o.service }}</td>
                        <td>{{ o.budget }}$</td>
                        <td><span class="badge" style="background: {% if o.status == 'مكتمل' %}#16a34a{% else %}#d97706{% endif %}; color: white;">{{ o.status }}</span></td>
                        <td>{{ order_notes.get(o.id|string, '') }}</td>
                        <td>
                            <button class="btn btn-success" onclick="markComplete({{ o.id }})">✔️ مكتمل</button>
                            <button class="btn btn-warning" onclick="addNote({{ o.id }})">📝 ملاحظة</button>
                            <button class="btn btn-danger" onclick="deleteOrder({{ o.id }})">🗑️ حذف</button>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div id="clients" class="tab-content">
                <h3>👥 العملاء المسجلون</h3>
                <table>
                    <tr><th>الاسم</th><th>عدد الطلبات</th><th>آخر طلب</th><th>رابط</th></tr>
                    {% for client in clients %}
                    <tr>
                        <td>{{ client.name }}</td>
                        <td>{{ client.order_count }}</td>
                        <td>{{ client.last_date[:10] }}</td>
                        <td><a href="{{ client.link }}" target="_blank">محادثة</a></td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div id="blocked" class="tab-content">
                <h3>🔨 المستخدمون المحظورون ({{ blocked_count }})</h3>
                <table>
                    <tr><th>معرف المستخدم</th><th>الإجراء</th></tr>
                    {% for uid in blocked_list %}
                    <tr>
                        <td>{{ uid[:15] }}...</td>
                        <td><button class="btn btn-success" onclick="unblockUser('{{ uid }}')">إلغاء الحظر</button></td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div id="verified" class="tab-content">
                <h3>🔐 المستخدمون الموثوقون ({{ verified_count }})</h3>
                <table>
                    <tr><th>معرف المستخدم</th></tr>
                    {% for uid in verified_list %}
                    <tr><td>{{ uid[:15] }}...</td></tr>
                    {% endfor %}
                </table>
            </div>

            <div id="commands" class="tab-content">
                <h3>⚙️ أوامر المدير (يمكن إرسالها عبر المحادثة)</h3>
                <ul style="line-height: 2;">
                    <li><code>احصائيات</code> - عرض إحصائيات عامة</li>
                    <li><code>طلبات اليوم</code> - عرض طلبات اليوم</li>
                    <li><code>كل الطلبات</code> - عرض آخر 10 طلبات</li>
                    <li><code>تفاصيل [رقم]</code> - عرض تفاصيل طلب محدد</li>
                    <li><code>اعرض العملاء</code> - عرض أسماء العملاء المسجلين</li>
                    <li><code>المحظورين</code> - عرض قائمة المحظورين</li>
                    <li><code>حظر [معرف]</code> - حظر مستخدم</li>
                    <li><code>الغاء حظر [معرف]</code> - إلغاء حظر مستخدم</li>
                    <li><code>ملاحظة [رقم] [نص]</code> - إضافة ملاحظة لطلب</li>
                    <li><code>مكتمل [رقم]</code> - تغيير حالة الطلب إلى مكتمل</li>
                    <li><code>حذف [رقم]</code> - حذف طلب</li>
                    <li><code>كم رسالة</code> - عدد الرسائل المستلمة والمرسلة</li>
                    <li><code>كم عميل</code> - عدد العملاء الفريدين</li>
                </ul>
            </div>
        </div>

        <div id="noteModal" class="modal">
            <div class="modal-content">
                <h3>📝 إضافة ملاحظة للطلب #<span id="noteOrderId"></span></h3>
                <textarea id="noteText" rows="4" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #ccc;"></textarea>
                <div style="margin-top: 15px; text-align: left;">
                    <button class="btn" onclick="submitNote()">حفظ</button>
                    <button class="btn btn-danger" onclick="closeModal()">إلغاء</button>
                </div>
            </div>
        </div>

        <script>
            function showTab(tabId) {
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.getElementById(tabId).classList.add('active');
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');
            }

            function markComplete(orderId) {
                if (confirm(`تأكيد إكمال الطلب #${orderId}؟`)) {
                    fetch(`/api/order/${orderId}/complete`, { method: 'POST' })
                        .then(res => res.json())
                        .then(data => { if(data.success) location.reload(); });
                }
            }

            function deleteOrder(orderId) {
                if (confirm(`هل أنت متأكد من حذف الطلب #${orderId}؟`)) {
                    fetch(`/api/order/${orderId}/delete`, { method: 'POST' })
                        .then(res => res.json())
                        .then(data => { if(data.success) location.reload(); });
                }
            }

            function addNote(orderId) {
                document.getElementById('noteOrderId').innerText = orderId;
                document.getElementById('noteModal').style.display = 'flex';
            }

            function submitNote() {
                const orderId = document.getElementById('noteOrderId').innerText;
                const note = document.getElementById('noteText').value;
                fetch(`/api/order/${orderId}/note`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ note: note })
                }).then(res => res.json()).then(data => {
                    if(data.success) location.reload();
                });
            }

            function closeModal() {
                document.getElementById('noteModal').style.display = 'none';
                document.getElementById('noteText').value = '';
            }

            function unblockUser(uid) {
                if (confirm(`إلغاء حظر ${uid.slice(0,15)}...؟`)) {
                    fetch(`/api/unblock/${uid}`, { method: 'POST' })
                        .then(res => res.json())
                        .then(data => { if(data.success) location.reload(); });
                }
            }

            window.onclick = function(event) {
                if (event.target == document.getElementById('noteModal')) {
                    closeModal();
                }
            }
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
                clients_dict[name] = {'name': name, 'order_count': 0, 'last_date': o.get('timestamp', ''), 'link': o.get('link', '')}
            clients_dict[name]['order_count'] += 1
            if o.get('timestamp', '') > clients_dict[name]['last_date']:
                clients_dict[name]['last_date'] = o['timestamp']
    clients_list = list(clients_dict.values())
    clients_list.sort(key=lambda x: x['last_date'], reverse=True)

    return render_template_string(html,
        start_time=data['stats']['start_time'][:16].replace('T', ' '),
        binance_id=BINANCE_ID,
        unique_clients=unique_clients,
        orders_count=len(data.get('orders', [])),
        today_orders=today_ords,
        blocked_count=len(data.get('blocked', [])),
        verified_count=len(data.get('verified', [])),
        msgs_received=data['stats']['msgs_received'],
        logs=list(logs)[:20],
        orders=orders_list,
        order_notes=data.get('order_notes', {}),
        clients=clients_list[:50],
        blocked_list=data.get('blocked', [])[-50:],
        verified_list=data.get('verified', [])[-50:]
    )

# ========== واجهات برمجية للوحة التحكم ==========
@app.route('/api/order/<int:order_id>/complete', methods=['POST'])
def api_complete_order(order_id):
    if update_order(order_id, {'status': 'مكتمل'}):
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/order/<int:order_id>/delete', methods=['POST'])
def api_delete_order(order_id):
    delete_order(order_id)
    return jsonify({'success': True})

@app.route('/api/order/<int:order_id>/note', methods=['POST'])
def api_add_note(order_id):
    note = request.json.get('note', '')
    add_note(order_id, note)
    return jsonify({'success': True})

@app.route('/api/unblock/<user_id>', methods=['POST'])
def api_unblock(user_id):
    blocked = data.get('blocked', [])
    if user_id in blocked:
        data['blocked'].remove(user_id)
        save_data()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

# ========== Keep alive ==========
def keep_alive():
    while True:
        time.sleep(600)
        try:
            requests.get(f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/", timeout=5)
            add_log("💓 Keep-alive ping")
        except:
            pass

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 B.Y PRO Agent - النسخة الآمنة مع التحقق من البيانات")
    print("="*70)
    print(f"👤 Owner ID: {OWNER_FB_ID}")
    print(f"🔑 Password: {OWNER_PASSWORD}")
    print(f"💰 Binance: {BINANCE_ID}")
    print(f"📦 Orders in DB: {len(data.get('orders', []))}")
    print(f"📊 JSONBin ID: {BIN_ID}")
    print("="*70 + "\n")

    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
