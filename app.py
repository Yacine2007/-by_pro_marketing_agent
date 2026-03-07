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
1. الاختصار الذكي: أجب على قدر السؤال بدقة. الزبون يقدر وقته، وأنت تقدر وقتك.
2. التكيف اللغوي: تحدث بنفس لغة المستخدم.
3. عدم الإلحاح: إذا قدمت العرض ولم يرد الزبون، لا تلاحقه.

قائمة الخدمات والأسعار:
- المواقع التعريفية: 300-800$ (5-10 أيام)
- المتاجر الإلكترونية: 700-1800$ (15-25 يوماً)
- بوتات الذكاء الاصطناعي: من 300$ (7-14 يوماً)
- تطبيقات الموبايل: من 1500$ (30-60 يوماً)
- التصميم الجرافيكي: 50-200$ (24-72 ساعة)

بروتوكول التعامل المالي:
- 30% عربون مقدم، 70% عند التسليم النهائي
- وسيلة الدفع: USDT (Binance Pay) حصراً. معرف بينانس: 1074084246

تعليمات خاصة لجمع بيانات العميل:
- مهمتك الأساسية مع العميل هي جمع: الاسم الكامل، الخدمة المطلوبة بالتفصيل، الميزانية التقريبية، رقم الجوال (اختياري).
- اسأل عن هذه البيانات بطريقة طبيعية خلال المحادثة.
- عندما يكتمل الاسم والخدمة والميزانية، سيقوم النظام تلقائياً بحفظ الطلب وإرسال تفاصيل الدفع.
- إذا لم يقدم العميل رقماً للجوال، يمكن للطلب أن يُحفظ بدونه.

تعليمات خاصة للمدير:
- أنت موظف والمستخدم هو مديرك.
- أجب بكل احترام وشفافية.
- إذا سأل عن إحصائيات أو طلبات، استخدم الأرقام الحقيقية المقدمة لك."""

# ========== تخزين JSONBin.io مع تحميل آمن ==========
def jsonbin_read():
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {
        'X-Master-Key': X_MASTER_KEY,
        'X-Access-Key': X_ACCESS_KEY
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            record = resp.json().get('record', {})
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

loaded_data = jsonbin_read()
if loaded_data:
    data = DEFAULT_DATA.copy()
    for key in data:
        if key in loaded_data:
            data[key] = loaded_data[key]
        else:
            data[key] = DEFAULT_DATA[key]
else:
    data = DEFAULT_DATA.copy()
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
    success = jsonbin_write(data)
    if success:
        add_log("💾 تم حفظ البيانات في JSONBin")
    else:
        add_log("⚠️ فشل حفظ البيانات في JSONBin")
    return success

# ========== التحقق من المدير ==========
def is_owner(sender_id):
    sender_str = str(sender_id)
    if sender_str == str(OWNER_FB_ID):
        return True
    verified_list = [str(v) for v in data.get('verified', [])]
    return sender_str in verified_list

# ========== دوال الطلبات والإحصائيات الحية ==========
def get_live_stats():
    """إحصائيات حية من البيانات الحالية"""
    today = datetime.now().strftime('%Y-%m-%d')
    today_orders = [o for o in data.get('orders', []) if o.get('timestamp', '').startswith(today)]
    unique_clients = len(set(o.get('sender_id', '') for o in data.get('orders', []) if o.get('sender_id')))
    
    return {
        'unique_clients': unique_clients,
        'total_orders': len(data.get('orders', [])),
        'today_orders': len(today_orders),
        'blocked': len(data.get('blocked', [])),
        'verified': len(data.get('verified', [])),
        'msgs_received': data['stats']['msgs_received'],
        'msgs_sent': data['stats']['msgs_sent'],
        'today_orders_list': today_orders[-5:]  # آخر 5 طلبات اليوم
    }

def add_order(order_dict):
    if 'orders' not in data:
        data['orders'] = []
    order_dict['id'] = len(data['orders']) + 1
    data['orders'].append(order_dict)
    save_data()
    add_log(f"✅ طلب جديد #{order_dict['id']} - {order_dict['name']}")
    # إشعار المدير
    stats = get_live_stats()
    notify_msg = f"""🔔 طلب جديد #{order_dict['id']}
الاسم: {order_dict['name']}
الخدمة: {order_dict['service']}
الميزانية: {order_dict['budget']}$
إجمالي الطلبات الآن: {stats['total_orders']}
طلبات اليوم: {stats['today_orders']}
{order_dict['link']}"""
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

def add_note(order_id, note):
    if 'order_notes' not in data:
        data['order_notes'] = {}
    data['order_notes'][str(order_id)] = note
    save_data()

# ========== إدارة الجلسات ==========
def get_session(sender_id):
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
            'lang': 'ar',
            'pending_details': {}  # لتخزين التفاصيل المؤقتة
        }
        save_data()
    return data['sessions'][sender_id]

def update_session(sender_id, updates):
    if 'sessions' in data and sender_id in data['sessions']:
        data['sessions'][sender_id].update(updates)
        save_data()

def add_to_conversation(sender_id, role, message):
    sess = get_session(sender_id)
    sess['conversation'].append(f"{role}: {message}")
    if len(sess['conversation']) > 15:  # زيادة الذاكرة إلى 15 رسالة
        sess['conversation'] = sess['conversation'][-15:]
    save_data()

# ========== معالجة كلمة المرور ==========
def handle_password(sender_id, text, sess):
    if text.strip() == OWNER_PASSWORD:
        sender_str = str(sender_id)
        if 'verified' not in data:
            data['verified'] = []
        if sender_str not in data['verified']:
            data['verified'].append(sender_str)
            save_data()
            add_log(f"🔐 مدير جديد: {sender_str[:10]}...")
        sess['awaiting_password'] = False
        update_session(sender_id, {'awaiting_password': False})
        send_fb(sender_id, "أهلاً بك يا مدير.")
    else:
        send_fb(sender_id, "❌ كلمة المرور غير صحيحة.")

# ========== استخراج بيانات العميل (محسّن) ==========
def extract_client_data(text, sess):
    """استخراج الاسم، الخدمة، الميزانية، رقم الجوال من النص"""
    updated = False
    text_lower = text.lower()
    
    # 1. استخراج الاسم (الأولوية: "اسمي ..." أو "الاسم ..." أو "انا ...")
    if not sess.get('name'):
        # البحث عن "اسمي"
        name_match = re.search(r'(?:اسمي|الاسم)[:\s]*([\u0600-\u06FF\s]{2,30})', text)
        if not name_match:
            name_match = re.search(r'my name is[:\s]*([a-zA-Z\s]{2,30})', text, re.I)
        if not name_match:
            # إذا لم نجد، ربما يقول "أنا [الاسم]" ولكن قد يكون وصفاً وليس اسماً حقيقياً
            # سنترك هذا للذكاء الاصطناعي
            pass
        if name_match:
            sess['name'] = name_match.group(1).strip()
            add_log(f"📝 الاسم: {sess['name']}")
            updated = True
    
    # 2. استخراج الخدمة (أكثر دقة)
    if not sess.get('service'):
        # قائمة الخدمات مع كلمات مفتاحية موسعة
        service_patterns = [
            (r'(?:موقع|website|web)(?:\s+تعريفي|\s+شخصي)?', 'موقع تعريفي'),
            (r'(?:متجر|ecommerce|store)(?:\s+إلكتروني)?', 'متجر إلكتروني'),
            (r'(?:تطبيق|app|mobile)(?:\s+جوال)?', 'تطبيق جوال'),
            (r'(?:بوت|bot|chatbot)(?:\s+ذكاء\s+اصطناعي)?', 'بوت ذكاء اصطناعي'),
            (r'(?:شعار|logo|لوجو)(?:\s+تصميم)?', 'تصميم شعار'),
            (r'(?:تصميم|design|graphic)(?:\s+جرافيكي)?', 'تصميم جرافيكي'),
            (r'فيسبوك|facebook|منصة|social media|شبكة اجتماعية', 'منصة تواصل اجتماعي (مشروع معقد)')
        ]
        for pattern, service_name in service_patterns:
            if re.search(pattern, text_lower):
                sess['service'] = service_name
                add_log(f"🛠 الخدمة: {service_name}")
                updated = True
                break
    
    # 3. استخراج الميزانية
    if sess.get('budget', 0) == 0:
        # البحث عن أرقام متبوعة بعملة
        budget_match = re.search(r'(\d+)[\s-]*(?:usdt|\$|دولار|dollar)', text, re.I)
        if budget_match:
            sess['budget'] = int(budget_match.group(1))
            add_log(f"💰 الميزانية: {sess['budget']}$")
            updated = True
        else:
            # إذا ذكر "لا توجد محدودية" أو "unlimited" اعتبر ميزانية كبيرة (10000$ افتراضياً)
            if re.search(r'(لا توجد محدودية|unlimited|ميزانية كبيرة)', text_lower):
                sess['budget'] = 10000  # قيمة افتراضية للمشاريع الكبيرة
                add_log(f"💰 الميزانية: غير محدودة (تقدير 10000$)")
                updated = True
    
    # 4. استخراج رقم الجوال
    if not sess.get('phone'):
        phone_match = re.search(r'(05[0-9]{8}|5[0-9]{8}|\+966[0-9]{9}|00966[0-9]{9})', text)
        if phone_match:
            sess['phone'] = phone_match.group(1)
            add_log(f"📱 الجوال: {sess['phone']}")
            updated = True
    
    return updated

# ========== الذكاء الاصطناعي الموحد ==========
def ask_ai(user_msg, sess, is_owner_mode=False, live_stats=None):
    # بناء السياق من آخر 12 رسالة
    context = "\n".join(sess.get('conversation', [])[-12:])
    
    system = BOT_PERSONALITY
    
    # إذا كان مديراً، نضيف الإحصائيات الحية
    if is_owner_mode and live_stats:
        stats_text = f"""
الإحصائيات الحالية:
- العملاء الفريدون: {live_stats['unique_clients']}
- إجمالي الطلبات: {live_stats['total_orders']}
- طلبات اليوم: {live_stats['today_orders']}
- المحظورون: {live_stats['blocked']}
- الموثوقون: {live_stats['verified']}
- الرسائل المستلمة: {live_stats['msgs_received']}
- الرسائل المرسلة: {live_stats['msgs_sent']}

إذا سأل المدير عن أي جديد أو طلبات، استخدم هذه الأرقام للإجابة.
"""
        system += stats_text
    
    # إضافة معلومات عن البيانات الحالية للعميل
    if sess.get('name') or sess.get('service') or sess.get('budget'):
        client_data_text = f"\nبيانات العميل المستخلصة حتى الآن:\n- الاسم: {sess.get('name', 'غير معروف')}\n- الخدمة: {sess.get('service', 'غير محددة')}\n- الميزانية: {sess.get('budget', 0)}$\n- رقم الجوال: {sess.get('phone', 'غير متوفر')}"
        system += client_data_text
    
    prompt = f"{system}\n\nسجل المحادثة:\n{context}\n\nالمستخدم: {user_msg}\nالرد:"
    
    try:
        url = f'{AI_API_URL}?text={requests.utils.quote(prompt)}'
        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            answer = r.json().get('response', '').strip()
            return answer[:1800]
    except Exception as e:
        add_log(f"❌ خطأ في الذكاء الاصطناعي: {e}")
    
    return "عذراً، حدث خطأ تقني. حاول مرة أخرى."

# ========== المعالجة الرئيسية ==========
def process_message(sender_id, text):
    data['stats']['msgs_received'] += 1
    save_data()
    add_log(f"📨 من {sender_id[:10]}...: {text[:40]}")

    # التحقق من الحظر
    if sender_id in data.get('blocked', []):
        add_log(f"🚫 مستخدم محظور {sender_id[:10]}... تم تجاهل الرسالة")
        return

    # استرجاع جلسة المستخدم
    sess = get_session(sender_id)
    add_to_conversation(sender_id, 'المستخدم', text)

    # 1. إذا كان المدير
    if is_owner(sender_id):
        live_stats = get_live_stats()
        # إذا سأل عن أي جديد أو طلبات، نعطيه رداً مختصراً أولاً ثم نمرره للذكاء
        if any(k in text.lower() for k in ['اي جديد', 'what\'s new', 'الطلبات', 'orders']):
            if live_stats['today_orders'] > 0:
                orders_summary = "\n".join([f"#{o['id']} {o['name']} - {o['service']} - {o['budget']}$" for o in live_stats['today_orders_list']])
                quick_reply = f"لدينا {live_stats['today_orders']} طلب/طلبات جديدة اليوم:\n{orders_summary}"
                send_fb(sender_id, quick_reply)
            else:
                send_fb(sender_id, "لا توجد طلبات جديدة اليوم.")
            # نمرر للذكاء أيضاً للرد الطبيعي
        reply = ask_ai(text, sess, is_owner_mode=True, live_stats=live_stats)
        send_fb(sender_id, reply)
        add_to_conversation(sender_id, 'النظام', reply)
        return

    # 2. إذا كان في مرحلة إدخال كلمة المرور
    if sess.get('awaiting_password'):
        handle_password(sender_id, text, sess)
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

    # 5. التحقق من اكتمال البيانات الأساسية (الاسم، الخدمة، الميزانية)
    if sess.get('name') and sess.get('service') and sess.get('budget', 0) > 0 and not sess.get('confirmed', False):
        # نطلب رقم الجوال إذا لم يقدمه
        if not sess.get('phone'):
            # نرسل رسالة لطلب رقم الجوال (مرة واحدة فقط)
            if not sess.get('asked_for_phone'):
                send_fb(sender_id, "شكراً لك. هل يمكنك تزويدي برقم جوالك للتواصل؟ (اختياري)")
                sess['asked_for_phone'] = True
                update_session(sender_id, {'asked_for_phone': True})
                return
        # إذا قدم رقم الجوال أو طلبنا مرة واحدة، نكمل
        if sess.get('phone') or sess.get('asked_for_phone'):
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

    # 6. رد عادي من الذكاء الاصطناعي للعميل
    reply = ask_ai(text, sess, is_owner_mode=False)
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
                <h3>⚙️ الأوامر المتاحة (يمكن استخدامها في المحادثة)</h3>
                <ul style="line-height: 2;">
                    <li><code>اي جديد</code> - عرض الطلبات الجديدة</li>
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
    print("🚀 B.Y PRO Agent - النسخة النهائية مع الإحصائيات الحية")
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
