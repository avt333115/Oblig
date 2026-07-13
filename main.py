
import asyncio
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Template

TELEGRAM_BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"
TELEGRAM_CHAT_ID = "ID_ВАШЕГО_ЧАТА"

DB_NAME = "nsd_mobile_tracker.db"
NSD_URL = "https://nsddata.ru/ru/disc/ca"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>NSD Мониторинг</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding-bottom: 40px; }
        .app-header { background: linear-gradient(135deg, #1e293b, #0f172a); color: white; padding: 20px 0; border-bottom-left-radius: 20px; border-bottom-right-radius: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .nav-pills .nav-link { border-radius: 12px; padding: 12px 20px; font-weight: 600; color: #64748b; background-color: #fff; border: 1px solid #e2e8f0; }
        .nav-pills .nav-link.active { background-color: #3b82f6; color: white; border-color: #3b82f6; }
        .card-custom { background: white; border: none; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 12px; padding: 16px; }
        .isin-badge { font-family: monospace; font-weight: 700; font-size: 1rem; color: #1e293b; background-color: #f1f5f9; padding: 6px 12px; border-radius: 8px; border: 1px solid #cbd5e1; display: inline-block; }
        .status-badge { font-size: 0.8rem; font-weight: 700; padding: 6px 10px; border-radius: 20px; }
        .btn-lg-custom { padding: 14px; border-radius: 12px; font-weight: 600; }
        .form-control-lg-custom { padding: 14px; border-radius: 12px; border: 2px solid #e2e8f0; font-size: 1.1rem; }
        .pulse-online { width: 10px; height: 10px; background-color: #10b981; border-radius: 50%; display: inline-block; animation: pulse 1.5s infinite; }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }
    </style>
</head>
<body>
    <div class="app-header mb-4"><div class="container text-center"><h4 class="mb-1 fw-bold"><i class="fa-solid fa-building-columns text-info me-2"></i> НРД Монитор</h4><p class="text-white-50 small mb-0"><span class="pulse-online me-1"></span> Радар активен</p></div></div>
    <div class="container">
        <ul class="nav nav-pills nav-fill gap-2 mb-4" id="pills-tab" role="tablist">
            <li class="nav-item"><button class="nav-link active" id="pills-history-tab" data-bs-toggle="pill" data-bs-target="#pills-history" type="button" role="tab"><i class="fa-solid fa-sack-dollar me-2"></i>Платежи ({{ history|length }})</button></li>
            <li class="nav-item"><button class="nav-link" id="pills-portfolio-tab" data-bs-toggle="pill" data-bs-target="#pills-portfolio" type="button" role="tab"><i class="fa-solid fa-folder-open me-2"></i>Портфель ({{ portfolio|length }})</button></li>
        </ul>
        <div class="tab-content" id="pills-tabContent">
            <div class="tab-pane fade show active" id="pills-history" role="tabpanel">
                <h5 class="fw-bold mb-3 px-1"><i class="fa-solid fa-receipt text-success me-2"></i>Поступления в НРД</h5>
                {% if not history %}
                    <div class="card-custom text-center py-5 text-muted"><i class="fa-solid fa-clock fa-fade fa-3x mb-3 text-warning"></i><p class="fw-bold mb-1">Деньги еще в пути</p><small class="d-block px-3">Как только эмитенты переведут рубли, карточки появятся здесь.</small></div>
                {% else %}
                    {% for payment in history %}<div class="card-custom"><div class="d-flex justify-content-between align-items-start mb-2"><span class="isin-badge">{{ payment.isin }}</span><span class="badge bg-success-subtle text-success status-badge"><i class="fa-solid fa-check me-1"></i> {{ payment.status }}</span></div><div class="pt-2 border-top mt-2" style="font-size: 0.9rem;"><div class="d-flex justify-content-between mb-1"><span class="text-muted">ID КД в НРД:</span><code class="text-dark fw-bold">{{ payment.ca_id }}</code></div><div class="d-flex justify-content-between"><span class="text-muted">Зачислено:</span><span class="text-dark fw-semibold">{{ payment.date }}</span></div></div><div class="mt-3"><a href="https://nsddata.ru/ru/disc/ca/card/{{ payment.ca_id }}" target="_blank" class="btn btn-sm btn-light w-100 py-2 border text-muted" style="border-radius: 8px;"><i class="fa-solid fa-arrow-up-right-from-square me-1"></i> Карточка НРД</a></div></div>{% endfor %}
                {% endif %}
            </div>
            <div class="tab-pane fade" id="pills-portfolio" role="tabpanel">
                <div class="card-custom mb-4"><h5 class="fw-bold mb-3"><i class="fa-solid fa-plus text-primary me-2"></i>Добавить бумагу</h5><form action="/add" method="post"><div class="mb-3"><input type="text" name="isin" class="form-control form-control-lg-custom text-uppercase text-center" placeholder="ВВЕДИТЕ ISIN КОД" required minlength="12" maxlength="12"></div><button type="submit" class="btn btn-primary btn-lg-custom w-100">Добавить в радар</button></form></div>
                <h5 class="fw-bold mb-3 px-1"><i class="fa-solid fa-eye text-secondary me-2"></i>Ваш список наблюдения</h5>
                {% if not portfolio %}
                    <div class="card-custom text-center py-4 text-muted"><i class="fa-solid fa-ghost fa-2x mb-2 text-secondary opacity-50"></i><p class="mb-0">Список пуст. Добавьте облигации.</p></div>
                {% else %}
                    {% for item in portfolio %}<div class="card-custom d-flex justify-content-between align-items-center py-3"><div><span class="isin-badge">{{ item.isin }}</span><div class="text-muted mt-1" style="font-size: 0.75rem;">Добавлен: {{ item.added_at }}</div></div><a href="/delete/{{ item.isin }}" class="btn btn-danger d-flex align-items-center justify-content-center" style="border-radius: 12px; width: 45px; height: 45px;"><i class="fa-solid fa-trash-can"></i></a></div>{% endfor %}
                {% endif %}
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS tracked_isins (isin TEXT PRIMARY KEY, added_at TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS completed_payments (ca_id TEXT PRIMARY KEY, isin TEXT, status TEXT, notify_date TEXT)")
    conn.commit()
    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    monitor_task = asyncio.create_task(background_nrd_worker())
    yield
    monitor_task.cancel()

app = FastAPI(lifespan=lifespan)

async def send_telegram_notification(text: str):
    if TELEGRAM_BOT_TOKEN == "ВАШ_ТОКЕН_БОТА": return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    async with httpx.AsyncClient() as client:
        try: await client.post(url, json=payload, timeout=10)
        except: pass

async def background_nrd_worker():
    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT isin FROM tracked_isins")
            watched_isins = [row[0] for row in cursor.fetchall()]
            conn.close()
            if watched_isins:
                async with httpx.AsyncClient(headers=HEADERS, timeout=20.0) as client:
                    response = await client.get(NSD_URL)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    table = soup.find("table")
                    if table:
                        for row in table.find_all("tr")[1:]:
                            cells = row.find_all("td")
                            if len(cells) < 6 or "INTR" not in cells[0].text: continue
                            href = cells[0].find("a")["href"] if cells[0].find("a") else ""
                            ca_id = re.search(r"card/(\d+)", href).group(1)
                            isin = re.search(r"\b(RU000[A-Z0-9]{7})\b", row.text).group(1)
                            if isin in watched_isins:
                                status = cells[-1].text.strip().lower()
                                if "исполнен" in status or "выплачен" in status:
                                    conn = sqlite3.connect(DB_NAME)
                                    cursor = conn.cursor()
                                    cursor.execute("SELECT 1 FROM completed_payments WHERE ca_id = ?", (ca_id,))
                                    if not cursor.fetchone():
                                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        cursor.execute("INSERT INTO completed_payments VALUES (?, ?, ?, ?)", (ca_id, isin, "Исполнено", now_str))
                                        conn.commit()
                                        conn.close()
                                        msg = f"💰 *ДЕНЬГИ В НРД!* 💰\n\n🆔 *ISIN:* `{isin}`\n⚙️ *Статус:* `Исполнено` (Отправлено брокерам)\n🔗 [Карточка]({f'https://nsddata.ru{href}'})"
                                        await send_telegram_notification(msg)
                                    else: conn.close()
        except: pass
        await asyncio.sleep(900)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT isin, added_at FROM tracked_isins ORDER BY added_at DESC")
    portfolio = [{"isin": row[0], "added_at": row[1]} for row in cursor.fetchall()]
    cursor.execute("SELECT ca_id, isin, status, notify_date FROM completed_payments ORDER BY notify_date DESC LIMIT 30")
    history = [{"ca_id": row[0], "isin": row[1], "status": row[2], "date": row[3]} for row in cursor.fetchall()]
    conn.close()
    return HTMLResponse(content=Template(HTML_TEMPLATE).render(portfolio=portfolio, history=history))

@app.post("/add")
async def add_isin(isin: str = Form(...)):
    isin = isin.strip().upper()
    if re.match(r"^RU000[A-Z0-9]{7}$", isin):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try: cursor.execute("INSERT INTO tracked_isins VALUES (?, ?)", (isin, datetime.now().strftime("%Y-%m-%d %H:%M"))); conn.commit()
        except: pass
        conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/delete/{isin}")
async def delete_isin(isin: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tracked_isins WHERE isin = ?", (isin,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)
