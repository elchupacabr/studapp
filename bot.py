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
import hashlib
import concurrent.futures
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========== ОТКЛЮЧАЕМ SSL ДЛЯ ЗАПРОСОВ К API СГУ ==========
# Это подавляет предупреждение о небезопасном подключении из-за verify=False
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== ПРОСТОЙ НАДЕЖНЫЙ HEALTH-CHECK СЕРВЕР ==========
class SimpleHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def start_web_server():
    port = int(os.environ.get('PORT', 10000))
    for attempt in range(5):
        try:
            server = HTTPServer(('0.0.0.0', port), SimpleHTTPHandler)
            print(f"✅ ВЕБ-СЕРВЕР ЗАПУЩЕН на порту {port}")
            server.serve_forever()
            break
        except Exception as e:
            print(f"⚠️ Попытка {attempt+1}: {e}")
            time.sleep(2)
    else:
        print("❌ НЕ УДАЛОСЬ ЗАПУСТИТЬ ВЕБ-СЕРВЕР")

web_thread = threading.Thread(target=start_web_server, daemon=True)
web_thread.start()
time.sleep(3)

# ========== SELF-PING ==========
def self_ping_advanced():
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
            headers = {'User-Agent': user_agent, 'Accept': 'text/html,application/xhtml+xml'}
            for url in [f"{render_url}/", f"{render_url}/health", f"{render_url}/status"]:
                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    if response.status_code == 200:
                        print(f"   ✅ {url}")
                except Exception as e:
                    print(f"   ❌ {url}: {str(e)[:30]}")
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

# ========== DNS FIX ==========
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

# ========== ХРАНЕНИЕ ДАННЫХ ==========
USER_GROUPS_FILE = "user_groups.json"
USER_SELECTIONS_FILE = "user_selections.json"
SCHEDULE_CACHE_FILE = "schedule_cache.json"

def load_json_file(filepath):
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Ошибка загрузки {filepath}: {e}")
        return {}

def save_json_file(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения {filepath}: {e}")
        return

def load_user_groups():
    return load_json_file(USER_GROUPS_FILE)

def save_user_groups(groups):
    save_json_file(USER_GROUPS_FILE, groups)

def get_user_group(user_id):
    groups = load_user_groups()
    return groups.get(str(user_id))

def set_user_group(user_id, group_id, group_name):
    groups = load_user_groups()
    groups[str(user_id)] = {"group_id": group_id, "group_name": group_name}
    save_user_groups(groups)

def load_user_selections():
    return load_json_file(USER_SELECTIONS_FILE)

def save_user_selections(selections):
    save_json_file(USER_SELECTIONS_FILE, selections)

def get_user_selection(user_id):
    selections = load_user_selections()
    return selections.get(str(user_id), {"type": None, "name": None, "id": None})

def set_user_selection(user_id, selection_type, name, id_val=None):
    selections = load_user_selections()
    selections[str(user_id)] = {"type": selection_type, "name": name, "id": id_val}
    save_user_selections(selections)

def clear_user_selection(user_id):
    selections = load_user_selections()
    if str(user_id) in selections:
        del selections[str(user_id)]
        save_user_selections(selections)

# ========== РАБОТА С API СПИСКОВ ==========
API_BASE_URL = "https://stud.sssu.ru/api/Rasp"
API_DATES_URL = "https://stud.sssu.ru/api/GetRaspDates"
API_GROUPLIST_URL = "https://stud.sssu.ru/api/raspGrouplist"
API_AUDITORIUMS_URL = "https://stud.sssu.ru/api/raspAudlist"
API_TEACHERS_URL = "https://stud.sssu.ru/api/raspTeacherlist"
API_YEARS_URL = "https://stud.sssu.ru/api/Rasp/ListYears"

# Кэш для списков
groups_cache = {"data": None, "timestamp": 0, "year": None}
auditoriums_cache = {"data": None, "timestamp": 0, "year": None}
teachers_cache = {"data": None, "timestamp": 0, "year": None}
years_cache = {"data": None, "timestamp": 0}
current_year = None

# ========== ОБНОВЛЕННЫЕ ФУНКЦИИ С verify=False ==========
def get_all_groups(year=None):
    if year is None:
        year = get_current_academic_year()
    current_time = datetime.now().timestamp()
    if groups_cache["data"] and groups_cache["year"] == year:
        if (current_time - groups_cache["timestamp"]) < 86400:
            return groups_cache["data"]
    try:
        # Добавлен verify=False
        response = requests.get(API_GROUPLIST_URL, params={"year": year}, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        if data.get("data"):
            groups_cache["data"] = data["data"]
            groups_cache["timestamp"] = current_time
            groups_cache["year"] = year
            print(f"✅ Загружены группы: {len(data['data'])} шт.")
            return groups_cache["data"]
        return []
    except Exception as e:
        print(f"❌ Ошибка загрузки групп: {e}")
        return []

def get_all_auditoriums(year=None):
    if year is None:
        year = get_current_academic_year()
    current_time = datetime.now().timestamp()
    if auditoriums_cache["data"] and auditoriums_cache["year"] == year:
        if (current_time - auditoriums_cache["timestamp"]) < 86400:
            print(f"📦 Аудитории из кэша: {len(auditoriums_cache['data'])} шт.")
            return auditoriums_cache["data"]
    try:
        print(f"🔄 Загрузка аудиторий за {year}...")
        # Добавлен verify=False
        response = requests.get(API_AUDITORIUMS_URL, params={"year": year}, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        if data.get("state") == 1 and data.get("data"):
            auditoriums_cache["data"] = data["data"]
            auditoriums_cache["timestamp"] = current_time
            auditoriums_cache["year"] = year
            print(f"✅ Загружены аудитории: {len(data['data'])} шт.")
            return auditoriums_cache["data"]
        return []
    except Exception as e:
        print(f"❌ Ошибка загрузки аудиторий: {e}")
        return []

def get_all_teachers(year=None):
    if year is None:
        year = get_current_academic_year()
    current_time = datetime.now().timestamp()
    if teachers_cache["data"] and teachers_cache["year"] == year:
        if (current_time - teachers_cache["timestamp"]) < 86400:
            return teachers_cache["data"]
    try:
        # Добавлен verify=False
        response = requests.get(API_TEACHERS_URL, params={"year": year}, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        if data.get("data"):
            teachers_cache["data"] = data["data"]
            teachers_cache["timestamp"] = current_time
            teachers_cache["year"] = year
            print(f"✅ Загружены преподаватели: {len(data['data'])} шт.")
            return teachers_cache["data"]
        return []
    except Exception as e:
        print(f"❌ Ошибка загрузки преподавателей: {e}")
        return []

def get_available_years():
    current_time = datetime.now().timestamp()
    if years_cache["data"] and (current_time - years_cache["timestamp"]) < 3600:
        return years_cache["data"]
    try:
        # Добавлен verify=False
        response = requests.get(API_YEARS_URL, timeout=10, verify=False)
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

def fetch_schedule_by_group(group_id, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        # Добавлен verify=False
        response = requests.get(API_BASE_URL, params={"idGroup": group_id, "sdate": date}, timeout=15, verify=False)
        response.raise_for_status()
        data = response.json()
        if data.get("state") != 1:
            return None, f"Ошибка: {data.get('msg')}"
        all_lessons = data.get("data", {}).get("rasp", [])
        filtered = [l for l in all_lessons if l.get("дата", "")[:10] == date]
        return filtered, None
    except Exception as e:
        return None, f"Ошибка: {e}"

def fetch_schedule_by_teacher(teacher_id, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        # Добавлен verify=False
        response = requests.get(API_BASE_URL, params={"idTeacher": teacher_id, "sdate": date}, timeout=15, verify=False)
        response.raise_for_status()
        data = response.json()
        if data.get("state") != 1:
            return None, f"Ошибка: {data.get('msg')}"
        all_lessons = data.get("data", {}).get("rasp", [])
        filtered = [l for l in all_lessons if l.get("дата", "")[:10] == date]
        return filtered, None
    except Exception as e:
        return None, f"Ошибка: {e}"

def fetch_schedule_by_auditorium(auditorium_id, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        aud_id = int(auditorium_id)
        # Добавлен verify=False
        response = requests.get(API_BASE_URL, params={"idAud": aud_id, "sdate": date}, timeout=15, verify=False)
        response.raise_for_status()
        data = response.json()
        if data.get("state") != 1:
            return None, f"Ошибка API: {data.get('msg', 'Неизвестная ошибка')}"
        all_lessons = data.get("data", {}).get("rasp", [])
        filtered = [l for l in all_lessons if l.get("дата", "")[:10] == date]
        return filtered, None
    except ValueError:
        return None, f"Ошибка: неверный ID аудитории {auditorium_id}"
    except Exception as e:
        return None, f"Ошибка: {e}"

# ... (остальные функции остаются без изменений: normalize_group_name, parse_lesson_type, format_lessons, format_week_schedule, get_schedule_for_* и т.д.) ...

# ========== ЗАПУСК БОТА (С ОБРАБОТКОЙ ReadTimeout) ==========
def main():
    print("🚀 Запуск Тони Диспетчер - Бот с расписанием СГУ")
    print("=" * 40)

    start_self_ping()
    get_available_years()
    get_current_academic_year()
    get_all_groups()

    # Принудительная загрузка списков
    print("🔄 Принудительная загрузка списков...")
    aud = get_all_auditoriums()
    print(f"📊 Аудитории загружены: {len(aud)} шт.")
    teach = get_all_teachers()
    print(f"📊 Преподаватели загружены: {len(teach)} шт.")

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    
    # Запускаем поток проверки расписания
    start_schedule_checker(vk)

    print("🤖 Бот готов к работе!")
    print("=" * 40)
    
    # ===== УЛУЧШЕННЫЙ ЦИКЛ С ОБРАБОТКОЙ ОШИБОК =====
    while True:
        try:
            longpoll = VkBotLongPoll(vk_session, GROUP_ID)
            print("✅ LongPoll подключен, слушаю события...")
            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    user_message = event.obj.message['text']
                    user_id = event.obj.message['from_id']

                    if event.from_chat:
                        peer_id = 2000000000 + event.chat_id
                        from_chat = True
                        if user_id < 0:
                            continue
                        print(f"📨 Чат {event.chat_id} от {user_id}: {user_message[:50]}...")
                    else:
                        peer_id = user_id
                        from_chat = False
                        print(f"📨 ЛС от {user_id}: {user_message[:50]}...")

                    handle_message(user_message, user_id, peer_id, from_chat, vk)

        except requests.exceptions.ReadTimeout:
            print("⚠️ Ошибка ReadTimeout от серверов VK. Переподключение через 15 секунд...")
            time.sleep(15)
            continue
        except requests.exceptions.ConnectionError as e:
            print(f"⚠️ Ошибка соединения с VK: {e}. Переподключение через 30 секунд...")
            time.sleep(30)
            continue
        except Exception as e:
            print(f"❌ Неожиданная ошибка в основном цикле: {e}")
            print("Перезапуск через 1 минуту...")
            time.sleep(60)
            continue

if __name__ == "__main__":
    main()
