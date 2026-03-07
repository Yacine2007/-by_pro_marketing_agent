import os
import json
import requests
import time
import threading
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# ========== المتغيرات ==========
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'by_pro_verify')
OWNER_ID = '2592319994'  # معرف المدير
BINANCE_ID = "1074084246"
AI_URL = "http://fi8.bot-hosting.net:20163/elos-gemina"

# ========== الملفات ==========
try:
    with open('orders.json', 'r') as f:
        orders = json.load(f)
except:
    orders = []

def save_orders():
    with open('orders.json', 'w') as f:
        json.dump(orders, f, indent=2)

# ========== جلسات المحادثة ==========
sessions = {}

# ========== إرسال رسالة ==========
def send(recipient, text):
    try:
        url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
        payload = {'recipient': {'id': recipient}, 'message': {'text': text}}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

# ========== الذكاء الاصطناعي مع البرومبت الكامل ==========
def ask_ai(user_msg, is_owner=False):
    system = """أنت مساعد مبيعات B.Y PRO الرسمي.

شخصيتك: وكيل مبيعات بشري محنك، هادئ، واثق، ومختصر جداً. لا تتصرف كآلة، لا تستخدم الرموز التعبيرية.

مبادئك:
1. الاختصار الذكي: أجب بدقة على قدر السؤال.
2. التكيف اللغوي: تحدث بنفس لغة المستخدم.
3. عدم الإلحاح: إذا قدمت العرض ولم يرد، لا تلاحقه.
4. السرية: لا تذكر أسماء موظفين أو تفاصيل داخلية.

الخدمات والأسعار:
- المواقع التعريفية: 300-800$ (5-10 أيام)
- المتاجر الإلكترونية: 700-1800$ (15-25 يوماً)
- بوتات الذكاء الاصطناعي: من 300$ (7-14 يوماً)
- تطبيقات الموبايل: من 1500$ (30-60 يوماً)
- التصميم الجرافيكي: 50-200$ (24-72 ساعة)

طريقة الدفع: 30% عربون، 70% عند التسليم عبر USDT (Binance Pay)
معرف بينانس: 1074084246

الهدف: تحويل الاستفسار إلى مشروع قائم."""

    if is_owner:
        system += "\n\nالمستخدم هو المدير. أجب باختصار وباحترام."

    try:
        prompt = f"{system}\n\nالمستخدم: {user_msg}\nالرد:"
        r = requests.get(f'{AI_URL}?text={requests.utils.quote(prompt)}', timeout=10)
        return r.json().get('response', 'كيف يمكنني مساعدتك؟')
    except:
        return "عذراً، حدث خطأ. حاول مرة أخرى."

# ========== أوامر المدير (بسيطة) ==========
def handle_owner(msg, sender):
    msg = msg.lower()
    
    if 'احصائيات' in msg or 'stats' in msg:
        clients = len(set(o.get('sender', '') for o in orders))
        text = f"📊 الطلبات: {len(orders)}\nالعملاء: {clients}"
        send(sender, text)
        return True
        
    if 'طلبات اليوم' in msg:
        today = datetime.now().strftime('%Y-%m-%d')
        count = len([o for o in orders if o.get('date', '').startswith(today)])
        send(sender, f"طلبات اليوم: {count}")
        return True
        
    if 'كل الطلبات' in msg:
        if not orders:
            send(sender, "لا توجد طلبات")
        else:
            text = "آخر الطلبات:\n"
            for o in orders[-5:]:
                text += f"- {o.get('name','')}: {o.get('service','')} {o.get('budget','')}$\n"
            send(sender, text)
        return True
        
    return False

# ========== استخراج بيانات العميل ==========
def extract_info(msg, session):
    # اسم
    if not session.get('name'):
        import re
        match = re.search(r'اسمي[:\s]*([\w\s]{2,20})', msg, re.I)
        if match:
            session['name'] = match.group(1).strip()
    
    # خدمة
    if not session.get('service'):
        if any(k in msg.lower() for k in ['موقع', 'website']):
            session['service'] = 'موقع تعريفي'
        elif any(k in msg.lower() for k in ['متجر', 'ecommerce']):
            session['service'] = 'متجر إلكتروني'
        elif any(k in msg.lower() for k in ['تطبيق', 'app']):
            session['service'] = 'تطبيق جوال'
        elif any(k in msg.lower() for k in ['بوت', 'bot']):
            session['service'] = 'بوت ذكاء اصطناعي'
    
    # ميزانية
    if not session.get('budget'):
        match = re.search(r'(\d+)[\s-]*(usdt|\$|دولار)', msg, re.I)
        if match:
            session['budget'] = int(match.group(1))

# ========== معالجة الرسائل ==========
def process(sender, msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] من {sender[:10]}: {msg[:30]}")
    
    # مدير
    if sender == OWNER_ID:
        if not handle_owner(msg, sender):
            reply = ask_ai(msg, is_owner=True)
            send(sender, reply)
        return
    
    # جلسة جديدة
    if sender not in sessions:
        sessions[sender] = {'msgs': [], 'name': '', 'service': '', 'budget': 0, 'confirmed': False}
    
    session = sessions[sender]
    session['msgs'].append(msg)
    
    # استخراج البيانات
    extract_info(msg, session)
    
    # هل اكتملت البيانات؟
    if session.get('name') and session.get('service') and session.get('budget', 0) > 0 and not session['confirmed']:
        session['confirmed'] = True
        
        # حفظ الطلب
        order = {
            'id': len(orders) + 1,
            'name': session['name'],
            'service': session['service'],
            'budget': session['budget'],
            'sender': sender,
            'date': datetime.now().isoformat()
        }
        orders.append(order)
        save_orders()
        
        # رسالة الدفع
        deposit = int(session['budget'] * 0.3)
        pay_msg = f"""تم تأكيد طلبك {session['name']}.

الخدمة: {session['service']}
المبلغ: {session['budget']}$ (المقدم {deposit}$)

للدفع عبر USDT (Binance):
المعرف: {BINANCE_ID}

بعد الدفع نبدأ التنفيذ فوراً."""
        send(sender, pay_msg)
        
        # إشعار المدير
        notify = f"🔔 طلب جديد #{order['id']}\n{order['name']} - {order['service']} - {order['budget']}$"
        send(OWNER_ID, notify)
        return
    
    # رد عادي من الذكاء
    reply = ask_ai(msg)
    send(sender, reply)

# ========== مسارات Flask ==========
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            for msg in entry.get('messaging', []):
                if 'message' in msg and 'text' in msg['message']:
                    threading.Thread(target=process, args=(msg['sender']['id'], msg['message']['text'])).start()
    return 'OK', 200

@app.route('/')
def home():
    return f"✅ البوت يعمل - الطلبات: {len(orders)}"

# ========== Keep alive ==========
def keep_alive():
    while True:
        time.sleep(600)
        try:
            requests.get("https://your-app.onrender.com")
        except:
            pass

if __name__ == '__main__':
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
