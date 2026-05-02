import requests
from datetime import datetime, timedelta
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from functools import lru_cache
import difflib
import socket
import os
import json
import re
import threading
import time
import random
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========== ПРОСТОЙ НАДЕЖНЫЙ HEALTH-CHECK СЕРВЕР ==========
class SimpleHTTPHandler(BaseHTTPRequestHandler):
    """Минимальный обработчик для health-check"""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def log_message(self, format, *args):
        pass

def start_web_server():
    """Запускает веб-сервер на порту 10000"""
    port = int(os.environ.get('PORT', 10000))
    for attempt in range(5):
        try:
            server = HTTPServer(('0.0.0.0', port), SimpleHTTPHandler)
            print(f"✅ ВЕБ-СЕРВЕР ЗАПУЩЕН на порту {port}")
            server.serve_forever()
            break
        except Exception as e:
            print(f"⚠️ Попытка {attempt+1}: Не удалось запустить сервер: {e}")
            time.sleep(2)
    else:
        print("❌ НЕ УДАЛОСЬ ЗАПУСТИТЬ ВЕБ-СЕРВЕР")

# Запускаем веб-сервер в фоновом потоке
web_thread = threading.Thread(target=start_web_server, daemon=True)
web_thread.start()
time.sleep(3)

# ========== ПРОДВИНУТЫЙ SELF-PING ==========
def self_ping_advanced():
    """Продвинутый self-ping с эмуляцией браузера"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0",
    ]
    
    while True:
        try:
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if not render_url:
                time.sleep(60)
                continue
            
            user_agent = random.choice(user_agents)
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            urls_to_visit = [f"{render_url}/", f"{render_url}/health", f"{render_url}/status"]
            
            for url in urls_to_visit:
                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    if response.status_code == 200:
                        print(f"   ✅ {url} → {response.status_code}")
                except Exception as e:
                    print(f"   ❌ {url} → {str(e)[:30]}")
                time.sleep(random.uniform(1, 3))
            
            wait_time = random.randint(600, 900)
            print(f"💤 Следующий обход через {wait_time // 60} минут")
            time.sleep(wait_time)
        except Exception as e:
            print(f"⚠️ Self-ping ошибка: {e}")
            time.sleep(300)

def start_self_ping():
    ping_thread = threading.Thread(target=self_ping_advanced, daemon=True)
    ping_thread.start()
    print("✅ Self-ping активирован")

# ========== FIX ДЛЯ DNS ПРОБЛЕМ ==========
STUD_SSSU_IP = "89.16.96.207"

def force_stud_ip():
    original_getaddrinfo = socket.getaddrinfo
    def patched_getaddrinfo(host, port, *args, **kwargs):
        if host == "stud.sssu.ru":
            print(f"🔧 DNS патч: {host} -> {STUD_SSSU_IP}")
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (STUD_SSSU_IP, port))]
        return original_getaddrinfo(host, port, *args, **kwargs)
    socket.getaddrinfo = patched_getaddrinfo
    print("✅ DNS патч активирован")

force_stud_ip()

# ========== ХРАНЕНИЕ ГРУПП ПОЛЬЗОВАТЕЛЕЙ ==========
USER_GROUPS_FILE = "user_groups.json"

def load_user_groups():
    try:
        if os.path.exists(USER_GROUPS_FILE):
            with open(USER_GROUPS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return {}

def save_user_groups(groups):
    try:
        with open(USER_GROUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(groups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

def get_user_group(user_id):
    groups = load_user_groups()
    return groups.get(str(user_id))

def set_user_group(user_id, group_id, group_name):
    groups = load_user_groups()
    groups[str(user_id)] = {"group_id": group_id, "group_name": group_name}
    save_user_groups(groups)

# ========== НАСТРОЙКИ ==========
VK_TOKEN = "vk1.a.caFxSOtgxlqz1GOqzR5VUhDTxl6Yi7Nhz2-n5bJ3Za8RCAQKsweYPbQtZQRLKYlmWQhg_mPFQ9UKppanLGRKkVVEOmhXYnN9b4hpmJ3jmcrCvZhafBGhWEwR77FFR0OKR2tJi4x-AZ73hc6rr4R0N1iKkHwvqBxdoqJ3P21AHEHTT1Cf538JnbyCUcwAaH8OiIHC10p6nQRLrW6vPifD3Q"
GROUP_ID = 238232620

API_BASE_URL = "https://stud.sssu.ru/api/Rasp"
API_DATES_URL = "https://stud.sssu.ru/api/GetRaspDates"
API_GROUPLIST_URL = "https://stud.sssu.ru/api/raspGrouplist"
API_YEARS_URL = "https://stud.sssu.ru/api/Rasp/ListYears"

CACHE_TIMEOUT = 3600

groups_cache = {"data": None, "timestamp": 0}
years_cache = {"data": None, "timestamp": 0}
current_year = None

# ========== РАБОТА С УЧЕБНЫМИ ГОДАМИ ==========
def get_available_years():
    current_time = datetime.now().timestamp()
    if years_cache["data"] and (current_time - years_cache["timestamp"]) < CACHE_TIMEOUT:
        return years_cache["data"]
    try:
        response = requests.get(API_YEARS_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("state") == 1 and data.get("data", {}).get("years"):
            years = data["data"]["years"]
            years_cache["data"] = years
            years_cache["timestamp"] = current_time
            print(f"✅ Список годов: {years}")
            return years
        return []
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []

def get_current_academic_year():
    global current_year
    if current_year:
        return current_year
    years = get_available_years()
    if not years:
        return "2025-2026"
    now = datetime.now()
    current_year_num = now.year
    current_month = now.month
    if current_month >= 9:
        academic_year = f"{current_year_num}-{current_year_num + 1}"
    else:
        academic_year = f"{current_year_num - 1}-{current_year_num}"
    if academic_year in years:
        current_year = academic_year
    else:
        current_year = years[-1]
    print(f"📅 Текущий год: {current_year}")
    return current_year

# ========== РАБОТА СО СПИСКОМ ГРУПП ==========
def get_all_groups(year=None):
    if year is None:
        year = get_current_academic_year()
    current_time = datetime.now().timestamp()
    if groups_cache["data"] and groups_cache.get("year") == year:
        if (current_time - groups_cache["timestamp"]) < CACHE_TIMEOUT:
            return groups_cache["data"]
    try:
        response = requests.get(API_GROUPLIST_URL, params={"year": year}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("data"):
            groups_cache["data"] = data["data"]
            groups_cache["timestamp"] = current_time
            groups_cache["year"] = year
            print(f"✅ Список групп: {len(data['data'])}")
            return groups_cache["data"]
        return []
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []

def find_group_by_name(search_name, year=None):
    all_groups = get_all_groups(year)
    if not all_groups:
        return None, None, []
    search_name_lower = search_name.lower().strip()
    for group in all_groups:
        if group["name"].lower() == search_name_lower:
            return group["id"], group["name"], []
    for group in all_groups:
        if group["name"].lower().startswith(search_name_lower):
            return group["id"], group["name"], []
    all_names_lower = [g["name"].lower() for g in all_groups]
    all_names_original = [g["name"] for g in all_groups]
    matches = difflib.get_close_matches(search_name_lower, all_names_lower, n=5, cutoff=0.6)
    original_matches = []
    for match_lower in matches:
        try:
            index = all_names_lower.index(match_lower)
            original_matches.append(all_names_original[index])
        except ValueError:
            continue
    return None, None, original_matches

def get_group_name_by_id(group_id, year=None):
    all_groups = get_all_groups(year)
    for group in all_groups:
        if group["id"] == group_id:
            return group["name"]
    return None

def get_all_groups_list(page=1, per_page=20):
    all_groups = get_all_groups()
    if not all_groups:
        return []
    sorted_groups = sorted(all_groups, key=lambda x: x["name"])
    start = (page - 1) * per_page
    end = start + per_page
    return sorted_groups[start:end]

def search_groups_by_keyword(keyword):
    all_groups = get_all_groups()
    if not all_groups:
        return []
    keyword_lower = keyword.lower()
    results = []
    for group in all_groups:
        if keyword_lower in group["name"].lower():
            results.append(group)
    return sorted(results, key=lambda x: x["name"])

def get_groups_list_message(page=1):
    groups = get_all_groups_list(page=page, per_page=20)
    if not groups:
        return "❌ Не удалось загрузить список групп"
    total_groups = len(get_all_groups())
    total_pages = (total_groups + 19) // 20
    result = f"📚 СПИСОК ГРУПП (страница {page}/{total_pages})\n"
    result += "=" * 35 + "\n\n"
    for group in groups:
        result += f"📌 {group['name']}\n"
        result += f"   🏫 {group.get('facul', '?')} | 📚 {group.get('kurs', '?')} курс\n\n"
    return result

def search_groups_message(keyword):
    results = search_groups_by_keyword(keyword)
    if not results:
        return f"❌ Группы по запросу `{keyword}` не найдены"
    result = f"🔍 РЕЗУЛЬТАТЫ ПОИСКА: `{keyword}`\n"
    result += f"📚 Найдено: {len(results)}\n"
    result += "=" * 35 + "\n\n"
    for group in results[:20]:
        result += f"📌 {group['name']} | 🏫 {group.get('facul', '?')}\n"
    return result

# ========== РАБОТА С РАСПИСАНИЕМ ==========
def fetch_available_dates(group_id):
    try:
        response = requests.get(API_DATES_URL, params={"idGroup": group_id}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("state") == 1:
            return data.get("data", {}).get("dates", [])
        return []
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

def has_lessons_on_date(group_id, date):
    dates = fetch_available_dates(group_id)
    return date in dates

def fetch_schedule(group_id, date):
    try:
        response = requests.get(API_BASE_URL, params={"idGroup": group_id, "sdate": date}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("state") != 1:
            return None, f"Ошибка: {data.get('msg')}"
        all_lessons = data.get("data", {}).get("rasp", [])
        filtered = [l for l in all_lessons if l.get("дата", "")[:10] == date]
        return {"data": {"rasp": filtered}}, None
    except Exception as e:
        return None, f"Ошибка: {e}"

def get_weekday_rus(weekday):
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return days[weekday]

def parse_lesson_type(discipline):
    if discipline.startswith("лек "):
        return "ЛЕК", discipline[4:]
    elif discipline.startswith("пр "):
        return "ПРАК", discipline[3:]
    elif discipline.startswith("лаб "):
        return "ЛАБ", discipline[4:]
    else:
        return "", discipline

def get_schedule_for_today(group_id):
    data, error = fetch_schedule(group_id, datetime.now().strftime("%Y-%m-%d"))
    if error:
        return error
    lessons = data.get("data", {}).get("rasp", [])
    if not lessons:
        return "📭 На сегодня занятий нет"
    result = "📅 РАСПИСАНИЕ НА СЕГОДНЯ\n" + "=" * 30 + "\n\n"
    for l in lessons:
        t_start = l.get("начало", "")
        t_end = l.get("конец", "")
        disc = l.get("дисциплина", "")
        teacher = l.get("преподаватель", "")
        room = l.get("аудитория", "")
        ltype, clean = parse_lesson_type(disc)
        result += f"⏰ {t_start}–{t_end}\n"
        if ltype:
            result += f"[{ltype}] "
        result += f"{clean}\n👨‍🏫 {teacher} | 🏫 {room}\n\n"
    return result

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(user_has_group=False):
    keyboard = {"one_time": False, "buttons": []}
    if user_has_group:
        keyboard["buttons"] = [
            [{"action": {"type": "text", "label": "📅 РАСПИСАНИЕ"}}, {"action": {"type": "text", "label": "🏫 МОЯ ГРУППА"}}],
            [{"action": {"type": "text", "label": "❓ ПОМОЩЬ"}}]
        ]
    else:
        keyboard["buttons"] = [
            [{"action": {"type": "text", "label": "📚 ВЫБРАТЬ ГРУППУ"}}],
            [{"action": {"type": "text", "label": "❓ ПОМОЩЬ"}}]
        ]
    return keyboard

def send_keyboard(vk, peer_id, message, keyboard):
    vk.messages.send(peer_id=peer_id, message=message, random_id=0, keyboard=json.dumps(keyboard, ensure_ascii=False))

# ========== ОБРАБОТЧИК ==========
user_states = {}

def handle_message(text, user_id, peer_id, from_chat, vk):
    text_lower = text.lower().strip()
    uid = str(user_id)
    
    if uid in user_states and user_states[uid].get("mode") == "waiting_for_group":
        group_id, group_name, _ = find_group_by_name(text.strip())
        if group_id:
            set_user_group(user_id, group_id, group_name)
            del user_states[uid]
            send_keyboard(vk, peer_id, f"✅ Группа {group_name} сохранена!", get_main_keyboard(True))
        else:
            send_keyboard(vk, peer_id, "❌ Группа не найдена", get_main_keyboard(False))
        return
    
    if text == "📚 ВЫБРАТЬ ГРУППУ":
        user_states[uid] = {"mode": "waiting_for_group"}
        send_keyboard(vk, peer_id, "📝 Введите название группы", get_main_keyboard(False))
        return
    
    if text == "📅 РАСПИСАНИЕ":
        ug = get_user_group(user_id)
        if ug:
            answer = get_schedule_for_today(ug['group_id'])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(True))
        else:
            send_keyboard(vk, peer_id, "❓ Сначала выберите группу", get_main_keyboard(False))
        return
    
    if text == "🏫 МОЯ ГРУППА":
        ug = get_user_group(user_id)
        if ug:
            send_keyboard(vk, peer_id, f"📌 Ваша группа: {ug['group_name']}", get_main_keyboard(True))
        else:
            send_keyboard(vk, peer_id, "❓ Группа не выбрана", get_main_keyboard(False))
        return
    
    if text == "❓ ПОМОЩЬ":
        help_text = "🤖 Бот расписания СГУ\n\n📌 Команды:\n• выбрать [группа]\n• расписание\n• моя группа"
        send_keyboard(vk, peer_id, help_text, get_main_keyboard(bool(get_user_group(user_id))))
        return
    
    # Обычный текст — пробуем найти группу
    if text_lower.startswith("выбрать "):
        group_name = text_lower.replace("выбрать ", "").strip()
        gid, gname, _ = find_group_by_name(group_name)
        if gid:
            set_user_group(user_id, gid, gname)
            send_keyboard(vk, peer_id, f"✅ Группа {gname} сохранена!", get_main_keyboard(True))
        else:
            send_keyboard(vk, peer_id, "❌ Группа не найдена", get_main_keyboard(False))
        return
    
    ug = get_user_group(user_id)
    if ug:
        answer = get_schedule_for_today(ug['group_id'])
        send_keyboard(vk, peer_id, answer, get_main_keyboard(True))
    else:
        send_keyboard(vk, peer_id, "❓ Группа не выбрана. Напишите: выбрать ИКТС-Тb31", get_main_keyboard(False))

# ========== ЗАПУСК ==========
def main():
    print("🚀 Запуск бота")
    start_self_ping()
    get_available_years()
    get_current_academic_year()
    get_all_groups()
    
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    
    print("🤖 Бот готов")
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            msg = event.obj.message['text']
            uid = event.obj.message['from_id']
            
            if event.from_chat:
                peer_id = 2000000000 + event.chat_id
            else:
                peer_id = uid
            
            handle_message(msg, uid, peer_id, event.from_chat, vk)

if __name__ == "__main__":
    main()
