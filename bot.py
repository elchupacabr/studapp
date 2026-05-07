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
            headers = {'User-Agent': user_agent,
                       'Accept': 'text/html,application/xhtml+xml'}
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
    selections[str(user_id)] = {
        "type": selection_type, "name": name, "id": id_val}
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


def get_all_groups(year=None):
    if year is None:
        year = get_current_academic_year()
    current_time = datetime.now().timestamp()
    if groups_cache["data"] and groups_cache["year"] == year:
        if (current_time - groups_cache["timestamp"]) < 86400:
            return groups_cache["data"]
    try:
        response = requests.get(API_GROUPLIST_URL, params={
                                "year": year}, timeout=10)
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
            return auditoriums_cache["data"]
    try:
        response = requests.get(API_AUDITORIUMS_URL, params={
                                "year": year}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("data"):
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
        response = requests.get(API_TEACHERS_URL, params={
                                "year": year}, timeout=10)
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


def search_teachers_by_name(query):
    teachers = get_all_teachers()
    if not teachers:
        return []
    query_lower = query.lower().strip()
    results = []
    for teacher in teachers:
        name = teacher.get("name", "")
        if query_lower in name.lower():
            results.append(teacher)
    return results[:20]


def search_auditoriums_by_name(query):
    auditoriums = get_all_auditoriums()
    if not auditoriums:
        return []
    query_lower = query.lower().strip()
    results = []
    for aud in auditoriums:
        name = aud.get("name", "")
        if query_lower in name.lower():
            results.append(aud)
    return results[:20]

# ========== НОРМАЛИЗАЦИЯ НАЗВАНИЙ ГРУПП ==========


def normalize_group_name(name):
    name_lower = name.lower().strip()
    name_lower = name_lower.replace('t', 'т')
    name_lower = name_lower.replace('b', 'б')
    name_lower = name_lower.replace('-', '')
    name_lower = re.sub(r'\s+', '', name_lower)
    name_lower = re.sub(r'([а-яё])\1+', r'\1', name_lower)
    return name_lower

# ========== ФУНКЦИИ РАБОТЫ С РАСПИСАНИЕМ ==========


def fetch_schedule_by_group(group_id, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        response = requests.get(API_BASE_URL, params={
                                "idGroup": group_id, "sdate": date}, timeout=15)
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
        response = requests.get(API_BASE_URL, params={
                                "idTeacher": teacher_id, "sdate": date}, timeout=15)
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
        response = requests.get(API_BASE_URL, params={
                                "idAud": auditorium_id, "sdate": date}, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("state") != 1:
            return None, f"Ошибка: {data.get('msg')}"
        all_lessons = data.get("data", {}).get("rasp", [])
        filtered = [l for l in all_lessons if l.get("дата", "")[:10] == date]
        return filtered, None
    except Exception as e:
        return None, f"Ошибка: {e}"


def fetch_week_schedule_parallel(fetch_func, identifier, target_date):
    """Универсальная функция для параллельного получения расписания на неделю"""
    start_date, end_date = get_week_for_date(target_date)

    dates = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    lessons_by_date = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        future_to_date = {
            executor.submit(fetch_func, identifier, date): date
            for date in dates
        }
        for future in concurrent.futures.as_completed(future_to_date):
            date = future_to_date[future]
            try:
                lessons, error = future.result(timeout=20)
                if lessons:
                    lessons_by_date[date] = lessons
            except Exception as e:
                print(f"Ошибка при запросе {date}: {e}")

    return lessons_by_date, start_date, end_date


def get_week_for_date(date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    monday = date_obj - timedelta(days=date_obj.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_weekday_rus(weekday):
    days = ["Понедельник", "Вторник", "Среда",
            "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return days[weekday]


def format_date_compact(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%d.%m")


def parse_lesson_type(discipline):
    if discipline.startswith("лек "):
        return "📖 ЛЕКЦИЯ", discipline[4:]
    elif discipline.startswith("пр "):
        return "💻 ПРАКТИКА", discipline[3:]
    elif discipline.startswith("лаб "):
        return "🔬 ЛАБОРАТОРНАЯ", discipline[4:]
    else:
        return "", discipline


def format_lessons(lessons, title, date):
    """Расписание на один день (компактно)"""
    if not lessons:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        return f"{title}\n📅 {date_obj.strftime('%d.%m.%Y')}\n\n❌ Занятий нет"

    date_obj = datetime.strptime(date, "%Y-%m-%d")
    result = f"{title}\n📅 {date_obj.strftime('%d.%m.%Y')} ({get_weekday_rus(date_obj.weekday())})\n"
    result += "─" * 24 + "\n"  # короткая линия вместо =====

    for lesson in sorted(lessons, key=lambda x: x.get("начало", "00:00")):
        time_start = lesson.get("начало", "")
        time_end = lesson.get("конец", "")
        discipline = lesson.get("дисциплина", "")
        teacher = lesson.get("преподаватель", "")
        room = lesson.get("аудитория", "")

        lesson_type, clean_discipline = parse_lesson_type(discipline)

        result += f"⏰ {time_start}–{time_end}\n"
        if lesson_type:
            result += f"{lesson_type}\n"
        result += f"📚 {clean_discipline}\n"
        result += f"👨‍🏫 {teacher}  |  🏫 {room}\n"
        result += "•" * 42 + "\n"  # точки вместо тире

    return result


def format_week_schedule(lessons_by_date, title, start_date, end_date):
    """Расписание на неделю (аккуратно, как на один день)"""
    if not lessons_by_date:
        start_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_obj = datetime.strptime(end_date, "%Y-%m-%d")
        return f"{title}\n📆 {start_obj.strftime('%d.%m')} – {end_obj.strftime('%d.%m.%Y')}\n\n❌ Занятий нет"

    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj = datetime.strptime(end_date, "%Y-%m-%d")
    result = f"{title}\n📆 {start_obj.strftime('%d.%m')} – {end_obj.strftime('%d.%m.%Y')}\n"
    result += "─" * 24 + "\n"

    for date, lessons in sorted(lessons_by_date.items()):
        if not lessons:
            continue
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        weekday = get_weekday_rus(date_obj.weekday())
        date_short = date_obj.strftime("%d.%m")
        result += f"\n📌 {weekday.upper()} ({date_short})\n"
        result += "─" * 24 + "\n"  # Такая же линия, как в начале

        for lesson in sorted(lessons, key=lambda x: x.get("начало", "00:00")):
            time_start = lesson.get("начало", "")
            time_end = lesson.get("конец", "")
            discipline = lesson.get("дисциплина", "")
            teacher = lesson.get("преподаватель", "")
            room = lesson.get("аудитория", "")

            lesson_type, clean_discipline = parse_lesson_type(discipline)

            result += f"⏰ {time_start}–{time_end}\n"
            if lesson_type:
                result += f"{lesson_type}\n"
            result += f"📚 {clean_discipline}\n"
            result += f"👨‍🏫 {teacher}  |  🏫 {room}\n"
            result += "•" * 42 + "\n"  # Такие же точки, как в одном дне

        result += ""  # Пустая строка между днями

    return result

# ========== ОСНОВНЫЕ ФУНКЦИИ РАСПИСАНИЯ ==========


def get_schedule_for_group_day(group_id, target_date):
    lessons, error = fetch_schedule_by_group(group_id, target_date)
    if error:
        return error
    group_name = get_group_name_by_id(group_id)
    title = f"📅 РАСПИСАНИЕ ГРУППЫ {group_name}"
    return format_lessons(lessons, title, target_date)


def get_schedule_for_teacher_day(teacher_id, teacher_name, target_date):
    lessons, error = fetch_schedule_by_teacher(teacher_id, target_date)
    if error:
        return error
    title = f"👨‍🏫 РАСПИСАНИЕ ПРЕПОДАВАТЕЛЯ {teacher_name}"
    return format_lessons(lessons, title, target_date)


def get_schedule_for_auditorium_day(auditorium_id, auditorium_name, target_date):
    lessons, error = fetch_schedule_by_auditorium(auditorium_id, target_date)
    if error:
        return error
    title = f"🏫 РАСПИСАНИЕ АУДИТОРИИ {auditorium_name}"
    return format_lessons(lessons, title, target_date)


def get_schedule_for_group_week(group_id, target_date):
    lessons_by_date, start_date, end_date = fetch_week_schedule_parallel(
        fetch_schedule_by_group, group_id, target_date
    )
    group_name = get_group_name_by_id(group_id)
    title = f"📅 РАСПИСАНИЕ ГРУППЫ {group_name}"
    return format_week_schedule(lessons_by_date, title, start_date, end_date)


def get_schedule_for_teacher_week(teacher_id, teacher_name, target_date):
    lessons_by_date, start_date, end_date = fetch_week_schedule_parallel(
        fetch_schedule_by_teacher, teacher_id, target_date
    )
    title = f"👨‍🏫 РАСПИСАНИЕ ПРЕПОДАВАТЕЛЯ {teacher_name}"
    return format_week_schedule(lessons_by_date, title, start_date, end_date)


def get_schedule_for_auditorium_week(auditorium_id, auditorium_name, target_date):
    lessons_by_date, start_date, end_date = fetch_week_schedule_parallel(
        fetch_schedule_by_auditorium, auditorium_id, target_date
    )
    title = f"🏫 РАСПИСАНИЕ АУДИТОРИИ {auditorium_name}"
    return format_week_schedule(lessons_by_date, title, start_date, end_date)


def get_schedule_for_group_today(group_id):
    return get_schedule_for_group_day(group_id, datetime.now().strftime("%Y-%m-%d"))


def get_schedule_for_teacher_today(teacher_id, teacher_name):
    return get_schedule_for_teacher_day(teacher_id, teacher_name, datetime.now().strftime("%Y-%m-%d"))


def get_schedule_for_auditorium_today(auditorium_id, auditorium_name):
    return get_schedule_for_auditorium_day(auditorium_id, auditorium_name, datetime.now().strftime("%Y-%m-%d"))


def get_schedule_for_group_current_week(group_id):
    return get_schedule_for_group_week(group_id, datetime.now().strftime("%Y-%m-%d"))


def get_schedule_for_group_next_week(group_id):
    next_week_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    return get_schedule_for_group_week(group_id, next_week_date)

# ========== ФУНКЦИИ ДЛЯ ГРУПП ==========


def get_available_years():
    current_time = datetime.now().timestamp()
    if years_cache["data"] and (current_time - years_cache["timestamp"]) < 3600:
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


def find_group_by_name(search_name, year=None):
    all_groups = get_all_groups(year)
    if not all_groups:
        return None, None
    normalized_search = normalize_group_name(search_name)
    for group in all_groups:
        normalized_group = normalize_group_name(group["name"])
        if normalized_group == normalized_search:
            return group["id"], group["name"]
    return None, None


def get_group_name_by_id(group_id, year=None):
    all_groups = get_all_groups(year)
    for group in all_groups:
        if group["id"] == group_id:
            return group["name"]
    return None


def get_groups_list_message(page=1, per_page=20):
    groups = get_all_groups()
    if not groups:
        return "❌ Не удалось загрузить список групп"
    total_pages = (len(groups) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    result = f"📚 СПИСОК ГРУПП (страница {page}/{total_pages})\n"
    result += "=" * 35 + "\n\n"
    for group in groups[start:end]:
        result += f"📌 {group['name']}\n"
    result += f"\n💡 Напишите `выбрать [название группы]`"
    return result


def search_groups_message(keyword):
    all_groups = get_all_groups()
    if not all_groups:
        return "❌ Не удалось загрузить список групп"
    keyword_lower = keyword.lower().strip()
    results = []
    for group in all_groups:
        if keyword_lower in group["name"].lower():
            results.append(group)
    if not results:
        return f"❌ Группы по запросу `{keyword}` не найдены"
    result = f"🔍 РЕЗУЛЬТАТЫ ПОИСКА: `{keyword}`\n📚 Найдено: {len(results)}\n"
    result += "=" * 35 + "\n\n"
    for group in results[:20]:
        result += f"📌 {group['name']}\n"
    if len(results) > 20:
        result += f"\n... и ещё {len(results) - 20} групп"
    result += f"\n💡 Напишите `выбрать [название]` для выбора группы"
    return result

# ========== ФУНКЦИИ ДЛЯ АУДИТОРИЙ ==========


def get_auditoriums_list_message(page=1, per_page=20):
    auditoriums = get_all_auditoriums()
    if not auditoriums:
        return "❌ Не удалось загрузить список аудиторий"
    total_pages = (len(auditoriums) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    result = f"🏫 СПИСОК АУДИТОРИЙ (страница {page}/{total_pages})\n"
    result += "=" * 35 + "\n\n"
    for aud in auditoriums[start:end]:
        result += f"📌 {aud['name']}\n"
    result += f"\n💡 Напишите `аудитория [номер]` для просмотра расписания"
    return result


def search_auditoriums_message(keyword):
    results = search_auditoriums_by_name(keyword)
    if not results:
        return f"❌ Аудитории по запросу `{keyword}` не найдены"
    result = f"🔍 РЕЗУЛЬТАТЫ ПОИСКА АУДИТОРИЙ: `{keyword}`\n📚 Найдено: {len(results)}\n"
    result += "=" * 35 + "\n\n"
    for aud in results[:20]:
        result += f"📌 {aud['name']}\n"
    if len(results) > 20:
        result += f"\n... и ещё {len(results) - 20} аудиторий"
    result += f"\n💡 Напишите `аудитория [номер]` для просмотра расписания"
    return result

# ========== ФУНКЦИИ ДЛЯ ПРЕПОДАВАТЕЛЕЙ ==========


def get_teachers_list_message(page=1, per_page=20):
    teachers = get_all_teachers()
    if not teachers:
        return "❌ Не удалось загрузить список преподавателей"
    total_pages = (len(teachers) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    result = f"👨‍🏫 СПИСОК ПРЕПОДАВАТЕЛЕЙ (страница {page}/{total_pages})\n"
    result += "=" * 35 + "\n\n"
    for teacher in teachers[start:end]:
        result += f"📌 {teacher['name']}\n"
    result += f"\n💡 Напишите `преподаватель [фамилия]` для просмотра расписания"
    return result


def search_teachers_message(keyword):
    results = search_teachers_by_name(keyword)
    if not results:
        return f"❌ Преподаватели по запросу `{keyword}` не найдены"
    result = f"🔍 РЕЗУЛЬТАТЫ ПОИСКА ПРЕПОДАВАТЕЛЕЙ: `{keyword}`\n📚 Найдено: {len(results)}\n"
    result += "=" * 35 + "\n\n"
    for teacher in results[:20]:
        result += f"📌 {teacher['name']}\n"
    if len(results) > 20:
        result += f"\n... и ещё {len(results) - 20} преподавателей"
    result += f"\n💡 Напишите `преподаватель [фамилия]` для просмотра расписания"
    return result

# ========== ПАРСИНГ ДАТЫ ==========


def parse_date_from_text(text):
    """Извлекает дату из текста в форматах ДД.ММ или ДД.ММ.ГГГГ"""
    patterns = [
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
        r'(\d{1,2})\.(\d{1,2})'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                day = int(match.group(1))
                month = int(match.group(2))
                year = int(match.group(3)) if len(
                    match.groups()) >= 3 else datetime.now().year
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day).strftime("%Y-%m-%d")
            except:
                continue
    return None

# ========== ПРОВЕРКА СТАТУСА САЙТА ==========


def check_site_status():
    results = {"site_reachable": False, "api_reachable": False,
               "response_time": None, "error": None}
    try:
        start_time = datetime.now()
        response = requests.get("https://stud.sssu.ru",
                                timeout=10, allow_redirects=True)
        results["response_time"] = int(
            (datetime.now() - start_time).total_seconds() * 1000)
        if response.status_code == 200:
            results["site_reachable"] = True
        else:
            results["error"] = f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        results["error"] = "Таймаут (нет ответа 10 секунд)"
    except requests.exceptions.ConnectionError:
        results["error"] = "Ошибка соединения (сервер не отвечает)"
    except Exception as e:
        results["error"] = str(e)[:100]
    try:
        response = requests.get(API_YEARS_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("state") == 1:
                results["api_reachable"] = True
            else:
                results["api_reachable"] = False
                results["error"] = f"API вернул ошибку: {data.get('msg', 'неизвестно')}"
        else:
            results["api_reachable"] = False
    except Exception as e:
        results["api_reachable"] = False
        if not results["error"]:
            results["error"] = str(e)[:100]
    return results


def get_status_message():
    status = check_site_status()
    result = "🖥️ **СТАТУС СЕРВЕРА stud.sssu.ru**\n" + "=" * 35 + "\n\n"
    if status["site_reachable"]:
        result += "✅ **Основной сайт:** Доступен\n"
        if status["response_time"]:
            result += f"   ⏱️ Время ответа: {status['response_time']} мс\n"
    else:
        result += "❌ **Основной сайт:** НЕ ДОСТУПЕН\n"
    if status["api_reachable"]:
        result += "✅ **API расписания:** Работает\n   📡 Бот может получать расписание\n"
    else:
        result += "❌ **API расписания:** НЕ РАБОТАЕТ\n   ⚠️ Бот не может получить расписание\n"
    if status["error"]:
        result += f"\n⚠️ **Детали ошибки:**\n   {status['error']}\n"
    result += "\n💡 **Рекомендации:**\n"
    if not status["api_reachable"]:
        result += "   • Проверьте подключение к интернету\n   • Сайт может быть на техническом обслуживании\n"
    elif not status["site_reachable"] and not status["api_reachable"]:
        result += "   • Вероятно, сервер университета не работает\n"
    else:
        result += "   • Всё работает, можно пользоваться!\n"
    result += f"\n🕐 Проверено: {datetime.now().strftime('%H:%M:%S')}"
    return result

# ========== СИСТЕМА ОТСЛЕЖИВАНИЯ ИЗМЕНЕНИЙ ==========


def get_schedule_hash(group_id, date):
    lessons, error = fetch_schedule_by_group(group_id, date)
    if error or not lessons:
        return None
    hash_string = ""
    for lesson in lessons:
        hash_string += f"{lesson.get('дата')}|{lesson.get('начало')}|{lesson.get('дисциплина')}|{lesson.get('преподаватель')}|{lesson.get('аудитория')}|"
    return hashlib.md5(hash_string.encode()).hexdigest()


def check_and_notify_changes(vk):
    print("🔍 Проверка обновлений расписания...")
    users = load_user_groups()
    cache = load_json_file(SCHEDULE_CACHE_FILE)
    changes_detected = False
    notifications = {}
    today = datetime.now().strftime("%Y-%m-%d")
    dates_to_check = [
        today] + [(datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 8)]

    for user_id, user_data in users.items():
        group_id = user_data["group_id"]
        group_name = user_data["group_name"]
        user_changes = []
        for date in dates_to_check:
            cache_key = f"{group_id}_{date}"
            current_hash = get_schedule_hash(group_id, date)
            if current_hash is None:
                continue
            if cache_key in cache:
                if cache[cache_key] != current_hash:
                    user_changes.append(date)
                    cache[cache_key] = current_hash
                    changes_detected = True
            else:
                cache[cache_key] = current_hash
        if user_changes:
            notifications[user_id] = {
                "group_name": group_name, "dates": user_changes}

    if changes_detected:
        save_json_file(SCHEDULE_CACHE_FILE, cache)
        for user_id, data in notifications.items():
            dates_str = ", ".join(
                [datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m") for d in data["dates"]])
            message = (
                f"🔄 *ВНИМАНИЕ! РАСПИСАНИЕ ИЗМЕНИЛОСЬ!*\n\n"
                f"📌 Группа: `{data['group_name']}`\n"
                f"📅 Изменения затронули: {dates_str}\n\n"
                f"💡 Для получения актуального расписания нажмите:\n"
                f"   • 📅 РАСПИСАНИЕ - на сегодня\n"
                f"   • 📆 НЕДЕЛЯ - на текущую неделю"
            )
            try:
                vk.messages.send(user_id=int(user_id),
                                 message=message, random_id=0)
                print(f"✅ Уведомление отправлено пользователю {user_id}")
            except Exception as e:
                print(f"❌ Ошибка отправки уведомления {user_id}: {e}")


def schedule_checker(vk):
    while True:
        try:
            time.sleep(21600)
            check_and_notify_changes(vk)
        except Exception as e:
            print(f"❌ Ошибка в потоке проверки: {e}")


def start_schedule_checker(vk):
    checker_thread = threading.Thread(
        target=schedule_checker, args=(vk,), daemon=True)
    checker_thread.start()
    print("✅ Поток проверки расписания запущен (каждые 6 часов)")


# ========== НАСТРОЙКИ ==========
VK_TOKEN = "vk1.a.caFxSOtgxlqz1GOqzR5VUhDTxl6Yi7Nhz2-n5bJ3Za8RCAQKsweYPbQtZQRLKYlmWQhg_mPFQ9UKppanLGRKkVVEOmhXYnN9b4hpmJ3jmcrCvZhafBGhWEwR77FFR0OKR2tJi4x-AZ73hc6rr4R0N1iKkHwvqBxdoqJ3P21AHEHTT1Cf538JnbyCUcwAaH8OiIHC10p6nQRLrW6vPifD3Q"
GROUP_ID = 238232620

# ========== КЛАВИАТУРЫ ==========


def get_main_keyboard(user_has_group=False):
    keyboard = {"one_time": False, "buttons": []}
    if user_has_group:
        keyboard["buttons"] = [
            [{"action": {"type": "text", "label": "📅 РАСПИСАНИЕ"}},
                {"action": {"type": "text", "label": "📆 НЕДЕЛЯ"}}],
            [{"action": {"type": "text", "label": "⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ"}},
                {"action": {"type": "text", "label": "🎯 БЛИЖАЙШЕЕ"}}],
            [{"action": {"type": "text", "label": "🏫 МОЯ ГРУППА"}}, {
                "action": {"type": "text", "label": "📚 ВСЕ ГРУППЫ"}}],
            [{"action": {"type": "text", "label": "👨‍🏫 ПРЕПОДАВАТЕЛИ"}},
                {"action": {"type": "text", "label": "🏢 АУДИТОРИИ"}}],
            [{"action": {"type": "text", "label": "🖥️ СТАТУС САЙТА"}},
                {"action": {"type": "text", "label": "❓ ПОМОЩЬ"}}],
            [{"action": {"type": "text", "label": "🗑️ СБРОСИТЬ ВЫБОР"}}]
        ]
    else:
        keyboard["buttons"] = [
            [{"action": {"type": "text", "label": "📚 ВЫБРАТЬ ГРУППУ"}}, {
                "action": {"type": "text", "label": "🔍 ПОИСК ГРУППЫ"}}],
            [{"action": {"type": "text", "label": "👨‍🏫 ПРЕПОДАВАТЕЛИ"}},
                {"action": {"type": "text", "label": "🏢 АУДИТОРИИ"}}],
            [{"action": {"type": "text", "label": "📋 ВСЕ ГРУППЫ"}}, {
                "action": {"type": "text", "label": "🖥️ СТАТУС САЙТА"}}],
            [{"action": {"type": "text", "label": "❓ ПОМОЩЬ"}}]
        ]
    return keyboard


def get_back_keyboard():
    return {"one_time": False, "buttons": [[{"action": {"type": "text", "label": "◀️ НАЗАД"}}]]}


def get_search_keyboard():
    return {"one_time": True, "buttons": [[{"action": {"type": "text", "label": "❌ ОТМЕНА"}}]]}


def send_keyboard(vk, peer_id, message, keyboard):
    try:
        vk.messages.send(peer_id=peer_id, message=message, random_id=0,
                         keyboard=json.dumps(keyboard, ensure_ascii=False))
    except Exception as e:
        print(f"Ошибка отправки клавиатуры: {e}")
        send_message(vk, peer_id, message)


def send_message(vk, peer_id, message):
    vk.messages.send(peer_id=peer_id, message=message, random_id=0)


# ========== ОБРАБОТЧИК ==========
user_states = {}


def handle_message(text, user_id, peer_id, from_chat, vk):
    text_lower = text.lower().strip()
    user_id_str = str(user_id)
    current_selection = get_user_selection(user_id)

    # Парсим дату из текста
    target_date = parse_date_from_text(text)

    # ===== КОМАНДА "неделя на ДД.ММ" или "неделя на ДД.ММ.ГГГГ" =====
    if target_date and ("неделя" in text_lower or "week" in text_lower):
        if current_selection["type"] == "teacher":
            answer = get_schedule_for_teacher_week(
                current_selection["id"], current_selection["name"], target_date)
        elif current_selection["type"] == "auditorium":
            answer = get_schedule_for_auditorium_week(
                current_selection["id"], current_selection["name"], target_date)
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_schedule_for_group_week(
                    user_group["group_id"], target_date)
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!",
                              get_main_keyboard(user_has_group=False))
                return
        send_keyboard(vk, peer_id, answer, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    # ===== КОМАНДА "расписание на ДД.ММ" или "расписание на ДД.ММ.ГГГГ" =====
    if target_date and ("расписание" in text_lower or "schedule" in text_lower):
        if current_selection["type"] == "teacher":
            answer = get_schedule_for_teacher_day(
                current_selection["id"], current_selection["name"], target_date)
        elif current_selection["type"] == "auditorium":
            answer = get_schedule_for_auditorium_day(
                current_selection["id"], current_selection["name"], target_date)
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_schedule_for_group_day(
                    user_group["group_id"], target_date)
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!",
                              get_main_keyboard(user_has_group=False))
                return
        send_keyboard(vk, peer_id, answer, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    # Кнопка НАЗАД
    if text == "◀️ НАЗАД":
        if user_id_str in user_states:
            del user_states[user_id_str]
        clear_user_selection(user_id)
        user_group = get_user_group(user_id)
        send_keyboard(vk, peer_id, "🔙 Вы вернулись в главное меню",
                      get_main_keyboard(user_has_group=bool(user_group)))
        return

    # Кнопка СБРОСИТЬ ВЫБОР
    if text == "🗑️ СБРОСИТЬ ВЫБОР":
        if user_id_str in user_states:
            del user_states[user_id_str]
        clear_user_selection(user_id)
        user_group = get_user_group(user_id)
        send_keyboard(vk, peer_id, "🗑️ Выбор сброшен. Теперь кнопки показывают расписание вашей группы.",
                      get_main_keyboard(user_has_group=bool(user_group)))
        return

    # Кнопка ОТМЕНА
    if text == "❌ ОТМЕНА":
        if user_id_str in user_states:
            del user_states[user_id_str]
        user_group = get_user_group(user_id)
        send_keyboard(vk, peer_id, "✅ Действие отменено",
                      get_main_keyboard(user_has_group=bool(user_group)))
        return

    # Состояния
    if user_id_str in user_states:
        state = user_states[user_id_str]

        if state.get("mode") == "waiting_for_group":
            group_name = text.strip()
            group_id, found_name = find_group_by_name(group_name)
            if group_id:
                set_user_group(user_id, group_id, found_name)
                clear_user_selection(user_id)
                del user_states[user_id_str]
                send_keyboard(vk, peer_id, f"✅ Группа `{found_name}` сохранена!", get_main_keyboard(
                    user_has_group=True))
            else:
                send_keyboard(
                    vk, peer_id, f"❌ Группа `{group_name}` не найдена.\nПопробуйте `📚 ВСЕ ГРУППЫ`", get_search_keyboard())
            return

        elif state.get("mode") == "waiting_for_teacher":
            teacher_query = text.strip()
            if teacher_query:
                results = search_teachers_by_name(teacher_query)
                if len(results) == 1:
                    teacher = results[0]
                    set_user_selection(user_id, "teacher",
                                       teacher["name"], teacher["id"])
                    del user_states[user_id_str]
                    answer = get_schedule_for_teacher_today(
                        teacher["id"], teacher["name"])
                    send_keyboard(vk, peer_id, answer, get_main_keyboard(
                        user_has_group=bool(get_user_group(user_id))))
                elif len(results) > 1:
                    message = f"🔍 Найдено преподавателей по запросу `{teacher_query}`:\n\n"
                    for t in results[:10]:
                        message += f"📌 {t['name']}\n"
                    message += f"\n💡 Уточните запрос (например, `преподаватель {results[0]['name']}`)"
                    send_keyboard(vk, peer_id, message, get_search_keyboard())
                else:
                    send_keyboard(
                        vk, peer_id, f"❌ Преподаватель `{teacher_query}` не найден", get_search_keyboard())
            else:
                send_keyboard(
                    vk, peer_id, "❓ Введите фамилию преподавателя", get_search_keyboard())
            return

        elif state.get("mode") == "waiting_for_auditorium":
            auditorium_query = text.strip()
            if auditorium_query:
                aud_number_match = re.match(
                    r'^(\d{2,5}[а-я]?)$', auditorium_query.lower())
                if aud_number_match:
                    aud_number = aud_number_match.group(1)
                    results = search_auditoriums_by_name(aud_number)
                else:
                    results = search_auditoriums_by_name(auditorium_query)

                if len(results) == 1:
                    aud = results[0]
                    set_user_selection(user_id, "auditorium",
                                       aud["name"], aud["id"])
                    del user_states[user_id_str]
                    answer = get_schedule_for_auditorium_today(
                        aud["id"], aud["name"])
                    send_keyboard(vk, peer_id, answer, get_main_keyboard(
                        user_has_group=bool(get_user_group(user_id))))
                elif len(results) > 1:
                    message = f"🔍 Найдено аудиторий по запросу `{auditorium_query}`:\n\n"
                    for a in results[:10]:
                        message += f"📌 {a['name']}\n"
                    message += f"\n💡 Уточните запрос (например, `аудитория {results[0]['name']}`)"
                    send_keyboard(vk, peer_id, message, get_search_keyboard())
                else:
                    send_keyboard(
                        vk, peer_id, f"❌ Аудитория `{auditorium_query}` не найдена", get_search_keyboard())
            else:
                send_keyboard(
                    vk, peer_id, "❓ Введите номер аудитории", get_search_keyboard())
            return

    # ===== ПРОВЕРКА НА ПРОСТОЙ НОМЕР АУДИТОРИИ =====
    aud_pattern = re.match(r'^(\d{2,5}[а-я]?)$', text_lower)
    if aud_pattern:
        aud_number = aud_pattern.group(1)
        results = search_auditoriums_by_name(aud_number)
        if len(results) == 1:
            aud = results[0]
            set_user_selection(user_id, "auditorium", aud["name"], aud["id"])
            answer = get_schedule_for_auditorium_today(aud["id"], aud["name"])
            send_keyboard(vk, peer_id, answer, get_main_keyboard(
                user_has_group=bool(get_user_group(user_id))))
            return
        elif len(results) > 1:
            message = f"🔍 Найдено аудиторий по запросу `{aud_number}`:\n\n"
            for a in results[:10]:
                message += f"📌 {a['name']}\n"
            message += f"\n💡 Уточните запрос (например, `аудитория {results[0]['name']}`)"
            send_keyboard(vk, peer_id, message, get_main_keyboard(
                user_has_group=bool(get_user_group(user_id))))
            return
        else:
            send_keyboard(vk, peer_id, f"❌ Аудитория `{aud_number}` не найдена", get_main_keyboard(
                user_has_group=bool(get_user_group(user_id))))
            return

    # Обработка кнопок
    if text == "📚 ВЫБРАТЬ ГРУППУ":
        user_states[user_id_str] = {"mode": "waiting_for_group"}
        send_keyboard(
            vk, peer_id, "📝 Напишите название группы (например: `иктс тб31`)", get_search_keyboard())
        return

    if text == "🔍 ПОИСК ГРУППЫ":
        send_keyboard(
            vk, peer_id, "🔍 Введите ключевое слово для поиска группы", get_search_keyboard())
        return

    if text == "📚 ВСЕ ГРУППЫ" or text == "📋 ВСЕ ГРУППЫ":
        message = get_groups_list_message(1)
        send_keyboard(vk, peer_id, message, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    if text == "👨‍🏫 ПРЕПОДАВАТЕЛИ":
        message = get_teachers_list_message(1)
        user_states[user_id_str] = {"mode": "waiting_for_teacher"}
        send_keyboard(vk, peer_id, message, get_search_keyboard())
        return

    if text == "🏢 АУДИТОРИИ":
        message = get_auditoriums_list_message(1)
        user_states[user_id_str] = {"mode": "waiting_for_auditorium"}
        send_keyboard(vk, peer_id, message, get_search_keyboard())
        return

    if text == "📅 РАСПИСАНИЕ":
        if current_selection["type"] == "teacher":
            answer = get_schedule_for_teacher_today(
                current_selection["id"], current_selection["name"])
        elif current_selection["type"] == "auditorium":
            answer = get_schedule_for_auditorium_today(
                current_selection["id"], current_selection["name"])
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_schedule_for_group_today(user_group["group_id"])
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!",
                              get_main_keyboard(user_has_group=False))
                return
        send_keyboard(vk, peer_id, answer, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    if text == "📆 НЕДЕЛЯ":
        today = datetime.now().strftime("%Y-%m-%d")
        if current_selection["type"] == "teacher":
            answer = get_schedule_for_teacher_week(
                current_selection["id"], current_selection["name"], today)
        elif current_selection["type"] == "auditorium":
            answer = get_schedule_for_auditorium_week(
                current_selection["id"], current_selection["name"], today)
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_schedule_for_group_week(
                    user_group["group_id"], today)
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!",
                              get_main_keyboard(user_has_group=False))
                return
        send_keyboard(vk, peer_id, answer, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    if text == "⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ":
        next_week_date = (datetime.now() + timedelta(days=7)
                          ).strftime("%Y-%m-%d")
        if current_selection["type"] == "teacher":
            answer = get_schedule_for_teacher_week(
                current_selection["id"], current_selection["name"], next_week_date)
        elif current_selection["type"] == "auditorium":
            answer = get_schedule_for_auditorium_week(
                current_selection["id"], current_selection["name"], next_week_date)
        else:
            user_group = get_user_group(user_id)
            if user_group:
                answer = get_schedule_for_group_week(
                    user_group["group_id"], next_week_date)
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!",
                              get_main_keyboard(user_has_group=False))
                return
        send_keyboard(vk, peer_id, answer, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    if text == "🎯 БЛИЖАЙШЕЕ":
        if current_selection["type"] in ["teacher", "auditorium"]:
            send_keyboard(vk, peer_id, "🎯 Ближайшее занятие доступно только для групп",
                          get_main_keyboard(user_has_group=bool(get_user_group(user_id))))
        else:
            user_group = get_user_group(user_id)
            if user_group:
                today = datetime.now().strftime("%Y-%m-%d")
                lessons, _ = fetch_schedule_by_group(
                    user_group["group_id"], today)
                if lessons:
                    answer = get_schedule_for_group_today(
                        user_group["group_id"])
                else:
                    found = False
                    for i in range(1, 30):
                        next_date = (datetime.now() +
                                     timedelta(days=i)).strftime("%Y-%m-%d")
                        lessons, _ = fetch_schedule_by_group(
                            user_group["group_id"], next_date)
                        if lessons:
                            group_name = get_group_name_by_id(
                                user_group["group_id"])
                            answer = format_lessons(
                                lessons, f"📅 РАСПИСАНИЕ ГРУППЫ {group_name}", next_date)
                            answer += f"\n\n📆 Следующее занятие: {datetime.strptime(next_date, '%Y-%m-%d').strftime('%d.%m.%Y')}"
                            found = True
                            break
                    if not found:
                        answer = "📭 Ближайших занятий не найдено"
                send_keyboard(vk, peer_id, answer,
                              get_main_keyboard(user_has_group=True))
            else:
                send_keyboard(vk, peer_id, "❓ Сначала выберите группу!",
                              get_main_keyboard(user_has_group=False))
        return

    if text == "🏫 МОЯ ГРУППА":
        user_group = get_user_group(user_id)
        if user_group:
            send_keyboard(vk, peer_id, f"📌 Ваша группа: `{user_group['group_name']}`", get_main_keyboard(
                user_has_group=True))
        else:
            send_keyboard(vk, peer_id, "❓ Группа не выбрана. Нажмите `📚 ВЫБРАТЬ ГРУППУ`",
                          get_main_keyboard(user_has_group=False))
        return

    if text == "🖥️ СТАТУС САЙТА":
        answer = get_status_message()
        send_keyboard(vk, peer_id, answer, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    if text == "❓ ПОМОЩЬ":
        user_group = get_user_group(user_id)
        selection = get_user_selection(user_id)
        selection_text = ""
        if selection["type"] == "teacher":
            selection_text = f"\n🎯 Текущий выбор: преподаватель `{selection['name']}`"
        elif selection["type"] == "auditorium":
            selection_text = f"\n🎯 Текущий выбор: аудитория `{selection['name']}`"

        if user_group:
            group_text = f"📌 Ваша группа: `{user_group['group_name']}`"
        else:
            group_text = "❓ Группа не выбрана"

        help_text = (
            "🤖 *Тони Диспетчер - Бот с расписанием СГУ*\n\n"
            f"{group_text}"
            f"{selection_text}\n\n"
            "✨ *Что умеет бот:*\n\n"
            "**По группам:**\n"
            "• 📅 РАСПИСАНИЕ - сегодня\n"
            "• 📆 НЕДЕЛЯ - текущая неделя\n"
            "• ⏩ СЛЕДУЮЩАЯ НЕДЕЛЯ\n"
            "• 🎯 БЛИЖАЙШЕЕ - следующее занятие\n\n"
            "**По преподавателям:**\n"
            "• 👨‍🏫 ПРЕПОДАВАТЕЛИ - список\n"
            "• Напишите фамилию для выбора\n\n"
            "**По аудиториям:**\n"
            "• 🏢 АУДИТОРИИ - список\n"
            "• Напишите номер для выбора (можно просто цифрами)\n\n"
            "**Поиск по дате:**\n"
            "• `расписание на 21.05` - на конкретный день\n"
            "• `неделя на 21.05` - на неделю (с 18 по 24 мая)\n\n"
            "**Управление:**\n"
            "• 📚 ВЫБРАТЬ ГРУППУ - задать группу\n"
            "• 🗑️ СБРОСИТЬ ВЫБОР - вернуться к группе\n"
            "• ◀️ НАЗАД - из любого меню\n"
            "• ❌ ОТМЕНА - отменить поиск\n\n"
            "**Текстовые команды:**\n"
            "• `расписание иктс тб31` - расписание группы\n"
            "• `преподаватель Иванов` - выбрать преподавателя\n"
            "• `аудитория 2349` - выбрать аудиторию\n"
            "• `1301` - быстрый поиск аудитории\n\n"
            "💡 *Совет:* Используйте кнопки для быстрого доступа!"
        )
        send_keyboard(vk, peer_id, help_text, get_main_keyboard(
            user_has_group=bool(user_group)))
        return

    # ===== ТЕКСТОВЫЕ КОМАНДЫ =====
    if text_lower.startswith("преподаватель "):
        teacher_name = text_lower.replace("преподаватель ", "").strip()
        if teacher_name:
            results = search_teachers_by_name(teacher_name)
            if len(results) == 1:
                teacher = results[0]
                set_user_selection(user_id, "teacher",
                                   teacher["name"], teacher["id"])
                answer = get_schedule_for_teacher_today(
                    teacher["id"], teacher["name"])
                send_keyboard(vk, peer_id, answer, get_main_keyboard(
                    user_has_group=bool(get_user_group(user_id))))
            elif len(results) > 1:
                message = f"🔍 Найдено преподавателей по запросу `{teacher_name}`:\n\n"
                for t in results[:10]:
                    message += f"📌 {t['name']}\n"
                message += f"\n💡 Уточните запрос (например, `преподаватель {results[0]['name']}`)"
                send_keyboard(vk, peer_id, message, get_main_keyboard(
                    user_has_group=bool(get_user_group(user_id))))
            else:
                send_keyboard(vk, peer_id, f"❌ Преподаватель `{teacher_name}` не найден", get_main_keyboard(
                    user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите фамилию преподавателя", get_main_keyboard(
                user_has_group=bool(get_user_group(user_id))))
        return

    if text_lower.startswith("аудитория "):
        aud_name = text_lower.replace("аудитория ", "").strip()
        if aud_name:
            results = search_auditoriums_by_name(aud_name)
            if len(results) == 1:
                aud = results[0]
                set_user_selection(user_id, "auditorium",
                                   aud["name"], aud["id"])
                answer = get_schedule_for_auditorium_today(
                    aud["id"], aud["name"])
                send_keyboard(vk, peer_id, answer, get_main_keyboard(
                    user_has_group=bool(get_user_group(user_id))))
            elif len(results) > 1:
                message = f"🔍 Найдено аудиторий по запросу `{aud_name}`:\n\n"
                for a in results[:10]:
                    message += f"📌 {a['name']}\n"
                message += f"\n💡 Уточните запрос (например, `аудитория {results[0]['name']}`)"
                send_keyboard(vk, peer_id, message, get_main_keyboard(
                    user_has_group=bool(get_user_group(user_id))))
            else:
                send_keyboard(vk, peer_id, f"❌ Аудитория `{aud_name}` не найдена", get_main_keyboard(
                    user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите номер аудитории", get_main_keyboard(
                user_has_group=bool(get_user_group(user_id))))
        return

    if text_lower.startswith("выбрать "):
        group_name = text_lower.replace("выбрать ", "").strip()
        if group_name:
            group_id, found_name = find_group_by_name(group_name)
            if group_id:
                set_user_group(user_id, group_id, found_name)
                clear_user_selection(user_id)
                send_keyboard(vk, peer_id, f"✅ Группа `{found_name}` сохранена!", get_main_keyboard(
                    user_has_group=True))
            else:
                send_keyboard(vk, peer_id, f"❌ Группа `{group_name}` не найдена", get_main_keyboard(
                    user_has_group=False))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите название группы",
                          get_main_keyboard(user_has_group=False))
        return

    if text_lower == "группы" or text_lower == "список групп":
        answer = get_groups_list_message(1)
        send_keyboard(vk, peer_id, answer, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    if text_lower.startswith("найди ") or text_lower.startswith("поиск "):
        keyword = text_lower.replace(
            "найди ", "").replace("поиск ", "").strip()
        if keyword:
            answer = search_groups_message(keyword)
            send_keyboard(vk, peer_id, answer, get_main_keyboard(
                user_has_group=bool(get_user_group(user_id))))
        else:
            send_keyboard(vk, peer_id, "❓ Напишите, что искать", get_main_keyboard(
                user_has_group=bool(get_user_group(user_id))))
        return

    if text_lower == "моя группа" or text_lower == "моя группа?":
        user_group = get_user_group(user_id)
        if user_group:
            send_keyboard(vk, peer_id, f"📌 Ваша группа: `{user_group['group_name']}`", get_main_keyboard(
                user_has_group=True))
        else:
            send_keyboard(vk, peer_id, "❓ Группа не выбрана",
                          get_main_keyboard(user_has_group=False))
        return

    if text_lower == "статус" or text_lower == "статус сайта":
        answer = get_status_message()
        send_keyboard(vk, peer_id, answer, get_main_keyboard(
            user_has_group=bool(get_user_group(user_id))))
        return

    if text_lower in ["/start", "/help", "начать", "помощь", "start", "help"]:
        user_group = get_user_group(user_id)
        selection = get_user_selection(user_id)
        selection_text = ""
        if selection["type"] == "teacher":
            selection_text = f"\n🎯 Выбран преподаватель: `{selection['name']}`"
        elif selection["type"] == "auditorium":
            selection_text = f"\n🎯 Выбрана аудитория: `{selection['name']}`"

        if user_group:
            group_text = f"📌 Группа: `{user_group['group_name']}`"
        else:
            group_text = "❓ Группа не выбрана"

        help_text = (
            f"🤖 *Тони Диспетчер - Бот с расписанием СГУ*\n\n"
            f"{group_text}"
            f"{selection_text}\n\n"
            "✨ *Как пользоваться:*\n\n"
            "**Выбор группы:**\n• `выбрать иктс тб31` - сохранить группу\n• `группы` - список всех групп\n• `найди иктс` - поиск группы\n\n"
            "**Преподаватели:**\n• `преподаватель Иванов` - выбрать преподавателя\n\n"
            "**Аудитории:**\n• `аудитория 2349` - выбрать аудиторию\n• `1301` - быстрый поиск (просто цифры)\n\n"
            "**Поиск по дате:**\n• `расписание на 21.05` - на конкретный день\n"
            "• `неделя на 21.05` - на неделю (с 18 по 24 мая)\n\n"
            "**Команды после выбора:**\n• `расписание` - на сегодня\n• `неделя` - на текущую неделю\n"
            "• `следующая неделя` - на следующую неделю\n\n"
            "💡 *Совет:* Используйте кнопки для быстрого доступа!\n"
            "🔙 Кнопка НАЗАД - сбросить выбор преподавателя/аудитории\n"
            "❌ ОТМЕНА - отменить поиск"
        )
        send_keyboard(vk, peer_id, help_text, get_main_keyboard(
            user_has_group=bool(user_group)))
        return

    # Если просто написали название группы
    group_id, group_name = find_group_by_name(text_lower)
    if group_id:
        set_user_group(user_id, group_id, group_name)
        clear_user_selection(user_id)
        answer = get_schedule_for_group_today(group_id)
        send_keyboard(vk, peer_id, answer,
                      get_main_keyboard(user_has_group=True))
        return

    # Если ничего не подошло
    user_group = get_user_group(user_id)
    if user_group:
        send_keyboard(vk, peer_id, "❓ Неизвестная команда. Напишите `помощь` для списка команд",
                      get_main_keyboard(user_has_group=True))
    else:
        send_keyboard(vk, peer_id, "❓ Неизвестная команда. Напишите `помощь` для списка команд",
                      get_main_keyboard(user_has_group=False))

# ========== ЗАПУСК ==========


def main():
    print("🚀 Запуск Тони Диспетчер - Бот с расписанием СГУ")
    print("=" * 40)

    start_self_ping()
    get_available_years()
    get_current_academic_year()
    get_all_groups()
    get_all_teachers()
    get_all_auditoriums()

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)

    start_schedule_checker(vk)

    print("🤖 Бот готов к работе!")
    print("📡 Функции: группы, преподаватели, аудитории")
    print("⚡ Параллельные запросы для быстрого расписания на неделю")
    print("📅 Поиск по дате: `расписание на 21.05` или `неделя на 21.05`")
    print("🕐 Автоматическая проверка обновлений: каждые 6 часов")
    print("=" * 40)

    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            user_message = event.obj.message['text']
            user_id = event.obj.message['from_id']

            if event.from_chat:
                peer_id = 2000000000 + event.chat_id
                from_chat = True
                if user_id < 0:
                    continue
                print(
                    f"📨 Чат {event.chat_id} от {user_id}: {user_message[:50]}...")
            else:
                peer_id = user_id
                from_chat = False
                print(f"📨 ЛС от {user_id}: {user_message[:50]}...")

            handle_message(user_message, user_id, peer_id, from_chat, vk)


if __name__ == "__main__":
    main()
