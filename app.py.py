from flask import Flask, request
import requests
import json

app = Flask(__name__)

PAGE_ACCESS_TOKEN = "التوكن_هنا"
VERIFY_TOKEN = "by_pro_verify"

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
                    sender = msg['sender']['id']
                    text = msg['message']['text']
                    
                    # رد بسيط (بدون ذكاء اصطناعي للسرعة)
                    reply = f"شكراً لرسالتك: {text}\nسيتواصل معك فريق B.Y PRO قريباً."
                    
                    # إرسال الرد
                    url = f'https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
                    requests.post(url, json={
                        'recipient': {'id': sender},
                        'message': {'text': reply}
                    })
    return 'OK', 200

@app.route('/')
def home():
    return "B.Y PRO Bot is Running!"

if __name__ == '__main__':
    app.run()