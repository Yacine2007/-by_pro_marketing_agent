# ========================================================================
# B.Y PRO — Executive Bridge (Arabic-enforced, low-credit optimized)
# ========================================================================

import json
import time
import threading
from datetime import datetime, timezone

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

try:
    import requests
except ImportError:
    requests = None


class ExecutiveBridge:

    DASHBOARD_DB     = 'DashboardDB'
    ORDERS_DB        = 'bypro_orders'
    CHAT_COL         = 'chat_history'
    OWNER_CHAT_COL   = 'owner_messenger_chat'
    SETTINGS_COL     = 'settings'
    CLIENTS_COL      = 'clients'
    PROJECTS_COL     = 'projects_registry'
    ORDERS_COL       = 'orders'

    MAX_HISTORY_TURNS   = 10
    MAX_CLIENTS         = 40
    MAX_PENDING_ORDERS  = 20
    MAX_PROJECTS        = 20

    def __init__(self, mongo_uri, logger=None):
        self.mongo_uri = mongo_uri
        self.log = logger or (lambda m: print(m, flush=True))
        self._client = None
        self._lock = threading.Lock()

    # ====================================================================
    # MongoDB
    # ====================================================================
    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if MongoClient is None:
            self.log("❌ pymongo not installed")
            return None
        if not self.mongo_uri:
            self.log("❌ Bridge: no mongo uri")
            return None
        try:
            client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=15000,
                tlsAllowInvalidCertificates=True,
            )
            client.admin.command('ping')
            self._client = client
            self.log("✅ Bridge connected")
            return self._client
        except Exception as e:
            self.log(f"❌ Bridge MongoDB: {e}")
            self._client = None
            return None

    def _db(self):
        c = self._ensure_client()
        if c is None:
            return None
        return c[self.DASHBOARD_DB]

    # ====================================================================
    # Data loaders
    # ====================================================================
    def _load_settings(self):
        db = self._db()
        if db is None:
            return {}
        out = {}
        try:
            for doc in db[self.SETTINGS_COL].find({}):
                k = doc.get('key')
                if k:
                    out[k] = doc.get('value')
        except Exception as e:
            self.log(f"⚠️ settings: {e}")
        return out

    def _load_stats(self):
        db = self._db()
        c = self._ensure_client()
        if db is None or c is None:
            return {}
        try:
            return {
                'clients':            db[self.CLIENTS_COL].count_documents({}),
                'projects':           db[self.PROJECTS_COL].count_documents({'kind': 'project'}),
                'projects_completed': db[self.PROJECTS_COL].count_documents({
                    'kind': 'project', 'progress': {'$gte': 100}
                }),
                'orders_total':       c[self.ORDERS_DB][self.ORDERS_COL].count_documents({}),
                'orders_pending':     c[self.ORDERS_DB][self.ORDERS_COL].count_documents({
                    '$or': [
                        {'status': 'new'},
                        {'status': {'$exists': False}},
                        {'status': None},
                        {'status': 'pending'},
                    ]
                }),
            }
        except Exception as e:
            self.log(f"⚠️ stats: {e}")
            return {}

    def _load_clients(self, limit=None):
        db = self._db()
        if db is None:
            return []
        limit = limit or self.MAX_CLIENTS
        try:
            out = []
            for d in db[self.CLIENTS_COL].find({}).sort('_id', -1).limit(limit):
                order = d.get('order') or {}
                item = {
                    'name':    d.get('name', ''),
                    'phone':   d.get('phone', ''),
                    'email':   d.get('email', ''),
                    'status':  d.get('status', ''),
                    'service': order.get('service', ''),
                    'project': order.get('project_name', '') or d.get('project_name', ''),
                }
                out.append({k: v for k, v in item.items() if v})
            return out
        except Exception as e:
            self.log(f"⚠️ clients: {e}")
            return []

    def _load_pending_orders(self):
        c = self._ensure_client()
        if c is None:
            return []
        try:
            col = c[self.ORDERS_DB][self.ORDERS_COL]
            query = {'$or': [
                {'status': 'new'},
                {'status': {'$exists': False}},
                {'status': None},
                {'status': 'pending'},
            ]}
            out = []
            for d in col.find(query).sort([('createdAt', -1), ('_id', -1)]).limit(self.MAX_PENDING_ORDERS):
                out.append({
                    'name':    d.get('fullName') or d.get('name', ''),
                    'phone':   d.get('phone', ''),
                    'service': d.get('service', ''),
                    'project': d.get('projectName', ''),
                })
            return out
        except Exception as e:
            self.log(f"⚠️ pending orders: {e}")
            return []

    def _load_projects(self):
        db = self._db()
        if db is None:
            return []
        try:
            out = []
            for d in db[self.PROJECTS_COL].find({'kind': 'project'}).sort('_id', -1).limit(self.MAX_PROJECTS):
                out.append({
                    'title':    d.get('title') or d.get('name') or '',
                    'progress': d.get('progress', 0),
                    'status':   d.get('status', ''),
                })
            return out
        except Exception as e:
            self.log(f"⚠️ projects: {e}")
            return []

    def _load_finances(self):
        db = self._db()
        if db is None:
            return {}
        try:
            col = db[self.PROJECTS_COL]

            def _sum(t_type):
                out = {}
                for row in col.aggregate([
                    {'$match': {'kind': 'transaction', 'type': t_type}},
                    {'$group': {'_id': '$currency', 'total': {'$sum': '$amount'}}},
                ]):
                    out[row['_id'] or 'DZD'] = row['total']
                return out

            income  = _sum('income')
            expense = _sum('expense')
            rate = 245
            income_dzd  = income.get('DZD', 0)  + income.get('USD', 0)  * rate
            expense_dzd = expense.get('DZD', 0) + expense.get('USD', 0) * rate
            return {
                'income_dzd':  round(income_dzd),
                'expense_dzd': round(expense_dzd),
                'net_dzd':     round(income_dzd - expense_dzd),
            }
        except Exception as e:
            self.log(f"⚠️ finances: {e}")
            return {}

    def _load_services_summary(self):
        db = self._db()
        if db is None:
            return []
        try:
            doc = db[self.SETTINGS_COL].find_one({'key': 'service_settings'})
            if not doc or not doc.get('value'):
                return []
            out = []
            for c in (doc['value'].get('categories') or []):
                if not c.get('enabled', True):
                    continue
                on = [s.get('id') for s in c.get('services', []) if s.get('enabled', True)]
                out.append({'id': c.get('id'), 'on': on})
            return out
        except Exception as e:
            self.log(f"⚠️ services: {e}")
            return []

    def _load_health(self, ai_cfg_getter, img_cfg_getter, marketer_cfg_getter):
        out = {
            'db': False, 'ai': False, 'img': False, 'marketer': False,
            'db_size_mb': None,
        }
        db = self._db()
        if db is not None:
            try:
                stats = db.command('dbStats')
                total = (stats.get('dataSize', 0) or 0) + (stats.get('indexSize', 0) or 0)
                out['db'] = True
                out['db_size_mb'] = round(total / (1024 * 1024), 2)
            except Exception:
                pass
        try: out['ai'] = ai_cfg_getter() is not None
        except Exception: pass
        try: out['img'] = img_cfg_getter() is not None
        except Exception: pass
        try: out['marketer'] = marketer_cfg_getter() is not None
        except Exception: pass
        return out

    # ====================================================================
    # Conversation
    # ====================================================================
    def _load_history(self, limit=None):
        db = self._db()
        if db is None:
            return []
        limit = limit or self.MAX_HISTORY_TURNS
        try:
            docs = list(db[self.OWNER_CHAT_COL].find({}).sort('_id', -1).limit(limit))
            docs.reverse()
            return [{'role': d.get('role', 'user'), 'content': d.get('content', '')} for d in docs]
        except Exception as e:
            self.log(f"⚠️ history: {e}")
            return []

    def _save_msg(self, role, content, mirror=True):
        db = self._db()
        if db is None:
            return
        ts = datetime.now(timezone.utc).isoformat()
        try:
            db[self.OWNER_CHAT_COL].insert_one({
                'role': role, 'content': content, 'timestamp': ts,
            })
        except Exception as e:
            self.log(f"⚠️ save own: {e}")
        if mirror:
            try:
                db[self.CHAT_COL].insert_one({
                    'role': role, 'content': content, 'timestamp': ts,
                    'meta': {'source': 'messenger'},
                })
            except Exception:
                pass

    def reset_conversation(self):
        db = self._db()
        if db is None:
            return False
        try:
            db[self.OWNER_CHAT_COL].delete_many({})
            return True
        except Exception:
            return False

    # ====================================================================
    # AI — Cascade starting at 1200 to save credits
    # ====================================================================
    def _call_ai(self, messages, cfg, max_tokens=1200):
        if requests is None:
            return None, "requests missing"
        if not cfg:
            return None, "AI key missing"

        headers = {
            'Authorization': f"Bearer {cfg['api_key']}",
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://bypro-marketing-agent.onrender.com',
            'X-Title': 'B.Y PRO Executive Bridge',
        }

        budgets = sorted({b for b in (max_tokens, 1000, 800, 600, 400, 250) if b <= max_tokens},
                         reverse=True)

        last_err = None
        for mt in budgets:
            try:
                payload = {
                    'model': cfg['model'],
                    'messages': messages,
                    'temperature': 0.75,
                    'max_tokens': mt,
                }
                t0 = time.time()
                r = requests.post(cfg['api_url'], headers=headers, json=payload, timeout=90)
                dt = round(time.time() - t0, 1)

                if r.status_code == 200:
                    data = r.json()
                    choices = data.get('choices') or []
                    if not choices:
                        last_err = "empty choices"
                        continue
                    content = choices[0].get('message', {}).get('content', '')
                    if content and content.strip():
                        self.log(f"✅ AI ({dt}s, {len(content)}c, mt={mt})")
                        return content.strip(), None
                    last_err = "empty content"
                    continue

                if r.status_code == 402:
                    self.log(f"⚠️ AI 402 (mt={mt}) — reducing")
                    last_err = f"402 at mt={mt}"
                    continue

                if r.status_code in (401, 403):
                    return None, f"auth {r.status_code}"

                if r.status_code in (400, 413, 422):
                    self.log(f"⚠️ AI {r.status_code}: {r.text[:150]}")
                    last_err = f"{r.status_code}"
                    continue

                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5)
                    last_err = f"{r.status_code}"
                    continue

                return None, f"HTTP {r.status_code}"
            except Exception as e:
                last_err = str(e)
                self.log(f"⚠️ AI exception: {e}")
                continue

        return None, last_err or "all budgets failed"

    # ====================================================================
    # ARABIC-ENFORCED system prompt
    # ====================================================================
    def _build_system_prompt(self, base_prompt, ctx, size='full'):
        now = datetime.now()
        weekday_ar = ['الإثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد'][now.weekday()]

        if size == 'full':
            c_lim, o_lim, p_lim = 30, 15, 15
        elif size == 'medium':
            c_lim, o_lim, p_lim = 15, 8, 8
        else:
            c_lim, o_lim, p_lim = 8, 5, 5

        clients  = ctx['clients'][:c_lim]
        pending  = ctx['pending_orders'][:o_lim]
        projects = ctx['projects'][:p_lim]

        # Arabic enforcement goes LAST so it overrides English base_prompt
        arabic_override = (
            "\n\n═══ قواعد صارمة ═══\n"
            "🔴 اللغة: أجب دائماً بالعربية الفصحى الواضحة، مهما كانت لغة الرسالة السابقة.\n"
            "🔴 المخاطبة: نادِ المدير: \"سيدي\" أو \"سيدي ياسين\" فقط.\n"
            "🔴 لا تستخدم كلمات إنجليزية أو فرنسية إلا للأسماء التقنية.\n"
            "🔴 التنسيق: نقاط (•) — لا جداول، لا ```، لا ###، لا **.\n"
            "🔴 لا تكرر ردك السابق. كل رسالة تستحق إجابة جديدة ومختلفة.\n"
            "🔴 كن موجزاً (2-5 أسطر عادة). لا تسأل أسئلة عامة.\n"
            "🔴 استخدم فقط الأرقام من البيانات أعلاه، لا تخترع.\n"
        )

        parts = [
            "=== الوقت الحالي ===",
            f"{weekday_ar}، {now.strftime('%Y-%m-%d %H:%M')}",
            "",
            "=== الشركة ===",
            json.dumps(ctx['settings'], ensure_ascii=False),
            "",
            "=== إحصائيات ===",
            json.dumps(ctx['stats'], ensure_ascii=False),
            "",
            "=== المالية (دج، دولار@245) ===",
            json.dumps(ctx['finances'], ensure_ascii=False),
            "",
            "=== الحالة والمفاتيح ===",
            json.dumps(ctx['health'], ensure_ascii=False),
            "",
            "=== الخدمات المفعّلة ===",
            json.dumps(ctx['services'], ensure_ascii=False),
            "",
            f"=== العملاء ({len(clients)}) ===",
            json.dumps(clients, ensure_ascii=False),
            "",
            f"=== الطلبات المعلقة ({len(pending)}) ===",
            json.dumps(pending, ensure_ascii=False),
            "",
            f"=== المشاريع ({len(projects)}) ===",
            json.dumps(projects, ensure_ascii=False),
        ]

        return base_prompt + "\n\n" + "\n".join(parts) + arabic_override

    # ====================================================================
    # PUBLIC API
    # ====================================================================
    def get_owner_reply(
        self,
        user_msg,
        ai_cfg_getter,
        img_cfg_getter,
        marketer_cfg_getter,
        base_prompt_getter=None,
    ):
        user_msg = (user_msg or '').strip()
        if not user_msg:
            return None, "empty"

        self.log(f"👑 Bridge ({len(user_msg)}c)")

        # 1. Persist user message
        self._save_msg('user', user_msg)

        # 2. Load prior history (excluding just-saved)
        history = self._load_history()
        if history and history[-1]['role'] == 'user' \
                and history[-1]['content'].strip() == user_msg:
            history = history[:-1]

        # 3. Load context
        raw_settings = self._load_settings()
        ctx = {
            'settings': {
                'admin_name':          raw_settings.get('admin_name', 'ياسين'),
                'company_website':     raw_settings.get('company_website', ''),
                'company_tagline':     raw_settings.get('company_tagline', ''),
                'company_description': (raw_settings.get('company_description') or '')[:200],
            },
            'stats':          self._load_stats(),
            'finances':       self._load_finances(),
            'health':         self._load_health(ai_cfg_getter, img_cfg_getter, marketer_cfg_getter),
            'services':       self._load_services_summary(),
            'clients':        self._load_clients(),
            'pending_orders': self._load_pending_orders(),
            'projects':       self._load_projects(),
        }

        # 4. Base prompt — Arabic-first (overrides Dashboard's English prompt)
        base = (
            "أنت المساعد التنفيذي لشركة B.Y PRO للتكنولوجيا والبرمجيات.\n"
            "مديرك هو ياسين بن مقران — مؤسس الشركة.\n"
            "تتحدث معه بالعربية دائماً.\n"
            "لديك وصول كامل للبيانات الحية أدناه.\n"
            "استخدم فقط هذه البيانات، لا تخترع أرقاماً."
        )
        # The Dashboard prompt is deliberately NOT used — it was forcing English.
        # If you want to combine, uncomment the line below:
        # if base_prompt_getter:
        #     try: base = (base_prompt_getter() or '') + "\n\n" + base
        #     except Exception: pass

        # 5. AI config
        cfg = ai_cfg_getter()
        if not cfg:
            err = "عذراً سيدي، مفتاح AI غير متوفر حالياً. راجع إعدادات API-AI."
            self._save_msg('assistant', err)
            return err, "no ai config"

        # 6. Attempts with decreasing size (starts at 1200, not 1600)
        attempts = [('full', 1200), ('medium', 1000), ('small', 800)]
        last_err = None

        for i, (size, budget) in enumerate(attempts):
            system_prompt = self._build_system_prompt(base, ctx, size=size)
            messages = [{'role': 'system', 'content': system_prompt}]

            hist_turns = 8 if size == 'full' else (5 if size == 'medium' else 3)
            for h in history[-hist_turns:]:
                if h['content']:
                    messages.append({'role': h['role'], 'content': h['content']})

            total_chars = sum(len(m['content']) for m in messages)
            self.log(f"📏 attempt {i+1} ({size}): {len(messages)} msgs, {total_chars}c")

            reply, err = self._call_ai(messages, cfg, max_tokens=budget)

            if reply:
                self._save_msg('assistant', reply)
                return reply, None

            last_err = err
            self.log(f"⚠️ attempt {i+1} failed: {err}")

        err_reply = (
            "عذراً سيدي، تعذّر إكمال الرد.\n\n"
            "الأسباب المحتملة:\n"
            "• نفاد رصيد OpenRouter (اشحن الرصيد — 5$ تكفي لشهور)\n"
            "• تعطّل مؤقت في الخدمة\n\n"
            "أعد إرسال رسالتك بعد قليل."
        )
        self.log(f"❌ Bridge final error: {last_err}")
        self._save_msg('assistant', err_reply)
        return err_reply, last_err or "unknown"

    # ====================================================================
    # Helpers
    # ====================================================================
    def get_conversation(self, limit=50):
        return self._load_history(limit=limit)

    def get_full_report(self, ai_cfg_getter, img_cfg_getter, marketer_cfg_getter):
        return {
            'settings':             self._load_settings(),
            'stats':                self._load_stats(),
            'finances':             self._load_finances(),
            'health':               self._load_health(ai_cfg_getter, img_cfg_getter, marketer_cfg_getter),
            'clients_count':        len(self._load_clients()),
            'pending_orders_count': len(self._load_pending_orders()),
            'projects_count':       len(self._load_projects()),
        }
