import asyncio
import logging
import os
import random
import sqlite3
from urllib.parse import quote_plus

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

WEBHOOK_PATH = "/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8000))

if not BOT_TOKEN:
    raise ValueError("Не найден BOT_TOKEN. Проверь файл .env")

if not TMDB_API_KEY:
    raise ValueError("Не найден TMDB_API_KEY. Проверь файл .env")


dp = Dispatcher()

user_last_media = {}
user_last_genre = {}
user_last_rating = {}
user_last_year = {}
user_last_country = {}
user_last_filter_key = {}
last_items = {}


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎬 Подобрать")],
        [
            KeyboardButton(text="⭐ Избранное"),
            KeyboardButton(text="ℹ️ Помощь"),
        ],
    ],
    resize_keyboard=True
)


media_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🎬 Фильмы"),
            KeyboardButton(text="📺 Сериалы"),
        ],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True
)


genre_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🎭 Любой жанр"),
            KeyboardButton(text="😂 Комедия"),
        ],
        [
            KeyboardButton(text="🚀 Фантастика"),
            KeyboardButton(text="😱 Ужасы"),
        ],
        [
            KeyboardButton(text="🔫 Боевик"),
            KeyboardButton(text="🧨 Триллер"),
        ],
        [
            KeyboardButton(text="🕵️ Детектив"),
            KeyboardButton(text="🧟 Криминал"),
        ],
        [
            KeyboardButton(text="❤️ Романтика"),
            KeyboardButton(text="🐉 Фэнтези"),
        ],
        [
            KeyboardButton(text="🎬 Драма"),
            KeyboardButton(text="🗺 Приключения"),
        ],
        [
            KeyboardButton(text="🧒 Семейный"),
            KeyboardButton(text="🎞 Мультфильм"),
        ],
        [
            KeyboardButton(text="📚 История"),
            KeyboardButton(text="⚔️ Военный"),
        ],
        [
            KeyboardButton(text="🎵 Музыка"),
            KeyboardButton(text="📺 Документальный"),
        ],
        [
            KeyboardButton(text="🤠 Вестерн"),
            KeyboardButton(text="📺 ТВ-фильм"),
        ],
        [KeyboardButton(text="⬅️ Назад к типу")],
    ],
    resize_keyboard=True
)


rating_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="⭐ 1–4"),
            KeyboardButton(text="⭐ 5–6"),
        ],
        [
            KeyboardButton(text="⭐ 7–8"),
            KeyboardButton(text="⭐ 8+"),
        ],
        [KeyboardButton(text="🎲 Любой рейтинг")],
        [KeyboardButton(text="⬅️ Назад к жанрам")],
    ],
    resize_keyboard=True
)


year_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🆕 Новые 2020+"),
            KeyboardButton(text="🎞 2010–2019"),
        ],
        [
            KeyboardButton(text="📼 2000–2009"),
            KeyboardButton(text="📺 До 2000"),
        ],
        [KeyboardButton(text="🎲 Любой год")],
        [KeyboardButton(text="⬅️ Назад к рейтингу")],
    ],
    resize_keyboard=True
)


country_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🌍 Любая страна"),
            KeyboardButton(text="🇰🇿 Казахстан"),
        ],
        [
            KeyboardButton(text="🇷🇺 Россия"),
            KeyboardButton(text="🇺🇸 США"),
        ],
        [
            KeyboardButton(text="🇬🇧 Великобритания"),
            KeyboardButton(text="🇫🇷 Франция"),
        ],
        [
            KeyboardButton(text="🇯🇵 Япония"),
            KeyboardButton(text="🇰🇷 Корея"),
        ],
        [
            KeyboardButton(text="🇮🇳 Индия"),
            KeyboardButton(text="🇩🇪 Германия"),
        ],
        [KeyboardButton(text="⬅️ Назад к году")],
    ],
    resize_keyboard=True
)


def get_connection():
    return sqlite3.connect("movies.db")


def init_db():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            original_title TEXT,
            year TEXT,
            rating TEXT,
            tmdb_url TEXT,
            kinopoisk_url TEXT,
            UNIQUE(user_id, movie_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filter_key TEXT NOT NULL,
            movie_id INTEGER NOT NULL,
            UNIQUE(user_id, filter_key, movie_id)
        )
        """
    )

    try:
        cursor.execute("ALTER TABLE favorites ADD COLUMN media_type TEXT DEFAULT 'movie'")
    except sqlite3.OperationalError:
        pass

    connection.commit()
    connection.close()


def get_media_type_from_text(text: str) -> str:
    if text == "📺 Сериалы":
        return "tv"

    return "movie"


def get_media_label(media_type: str) -> str:
    if media_type == "tv":
        return "Сериал"

    return "Фильм"


def get_title(item: dict) -> str:
    return (
        item.get("title")
        or item.get("name")
        or item.get("original_title")
        or item.get("original_name")
        or "Без названия"
    )


def get_original_title(item: dict) -> str:
    return (
        item.get("original_title")
        or item.get("original_name")
        or get_title(item)
    )


def get_release_date(item: dict) -> str:
    return (
        item.get("release_date")
        or item.get("first_air_date")
        or "Неизвестно"
    )


def get_release_year(item: dict) -> str:
    release_date = get_release_date(item)

    if release_date and release_date != "Неизвестно":
        return release_date[:4]

    return "Неизвестно"


def add_favorite(user_id: int, item: dict):
    media_type = item.get("_media_type", "movie")
    title = get_title(item)
    original_title = get_original_title(item)
    year = get_release_year(item)
    rating = str(item.get("vote_average", "Нет рейтинга"))

    kinopoisk_url, tmdb_url = get_item_links(item)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO favorites (
            user_id,
            movie_id,
            title,
            original_title,
            year,
            rating,
            tmdb_url,
            kinopoisk_url,
            media_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            item.get("id"),
            title,
            original_title,
            year,
            rating,
            tmdb_url,
            kinopoisk_url,
            media_type,
        )
    )

    connection.commit()
    added = cursor.rowcount > 0
    connection.close()

    return added


def get_favorites(user_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT movie_id, title, original_title, year, rating, tmdb_url, kinopoisk_url, media_type
        FROM favorites
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (user_id,)
    )

    rows = cursor.fetchall()
    connection.close()

    return rows


def delete_favorite(user_id: int, movie_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM favorites
        WHERE user_id = ? AND movie_id = ?
        """,
        (user_id, movie_id)
    )

    connection.commit()
    deleted = cursor.rowcount > 0
    connection.close()

    return deleted


def remember_seen_item(user_id: int, filter_key: str, item_id: int):
    if not item_id:
        return

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO seen_movies (
            user_id,
            filter_key,
            movie_id
        )
        VALUES (?, ?, ?)
        """,
        (user_id, filter_key, item_id)
    )

    connection.commit()
    connection.close()


def get_seen_item_ids(user_id: int, filter_key: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT movie_id
        FROM seen_movies
        WHERE user_id = ? AND filter_key = ?
        """,
        (user_id, filter_key)
    )

    rows = cursor.fetchall()
    connection.close()

    return {row[0] for row in rows}


def reset_seen_items_for_user(user_id: int, filter_key: str | None = None):
    connection = get_connection()
    cursor = connection.cursor()

    if filter_key:
        cursor.execute(
            """
            DELETE FROM seen_movies
            WHERE user_id = ? AND filter_key = ?
            """,
            (user_id, filter_key)
        )
    else:
        cursor.execute(
            """
            DELETE FROM seen_movies
            WHERE user_id = ?
            """,
            (user_id,)
        )

    connection.commit()
    connection.close()


def get_genre_id(genre_text: str, media_type: str) -> str:
    movie_genres = {
        "🎭 Любой жанр": "",
        "😂 Комедия": "35",
        "🚀 Фантастика": "878",
        "😱 Ужасы": "27",
        "🔫 Боевик": "28",
        "🧨 Триллер": "53",
        "🕵️ Детектив": "9648",
        "🧟 Криминал": "80",
        "❤️ Романтика": "10749",
        "🐉 Фэнтези": "14",
        "🎬 Драма": "18",
        "🗺 Приключения": "12",
        "🧒 Семейный": "10751",
        "🎞 Мультфильм": "16",
        "📚 История": "36",
        "⚔️ Военный": "10752",
        "🎵 Музыка": "10402",
        "📺 Документальный": "99",
        "🤠 Вестерн": "37",
        "📺 ТВ-фильм": "10770",
    }

    tv_genres = {
        "🎭 Любой жанр": "",
        "😂 Комедия": "35",
        "🚀 Фантастика": "10765",
        "😱 Ужасы": "9648",
        "🔫 Боевик": "10759",
        "🧨 Триллер": "9648",
        "🕵️ Детектив": "9648",
        "🧟 Криминал": "80",
        "❤️ Романтика": "18",
        "🐉 Фэнтези": "10765",
        "🎬 Драма": "18",
        "🗺 Приключения": "10759",
        "🧒 Семейный": "10751",
        "🎞 Мультфильм": "16",
        "📚 История": "10768",
        "⚔️ Военный": "10768",
        "🎵 Музыка": "",
        "📺 Документальный": "99",
        "🤠 Вестерн": "37",
        "📺 ТВ-фильм": "",
    }

    if media_type == "tv":
        return tv_genres.get(genre_text, "")

    return movie_genres.get(genre_text, "")


def get_rating_settings(rating_text: str) -> dict:
    settings = {
        "⭐ 1–4": {
            "min_rating": 1.0,
            "max_rating": 4.99,
            "min_votes": 20,
            "sort_by": "popularity.desc",
            "name": "1-4",
        },
        "⭐ 5–6": {
            "min_rating": 5.0,
            "max_rating": 6.99,
            "min_votes": 50,
            "sort_by": "popularity.desc",
            "name": "5-6",
        },
        "⭐ 7–8": {
            "min_rating": 7.0,
            "max_rating": 8.99,
            "min_votes": 150,
            "sort_by": "popularity.desc",
            "name": "7-8",
        },
        "⭐ 8+": {
            "min_rating": 8.0,
            "max_rating": 10.0,
            "min_votes": 300,
            "sort_by": "popularity.desc",
            "name": "8plus",
        },
        "🎲 Любой рейтинг": {
            "min_rating": 0.0,
            "max_rating": 10.0,
            "min_votes": 50,
            "sort_by": "popularity.desc",
            "name": "any",
        },
    }

    return settings.get(
        rating_text,
        {
            "min_rating": 0.0,
            "max_rating": 10.0,
            "min_votes": 50,
            "sort_by": "popularity.desc",
            "name": "any",
        }
    )


def get_year_settings(year_text: str) -> dict:
    settings = {
        "🆕 Новые 2020+": {
            "from_date": "2020-01-01",
            "to_date": "2030-12-31",
            "name": "2020plus",
        },
        "🎞 2010–2019": {
            "from_date": "2010-01-01",
            "to_date": "2019-12-31",
            "name": "2010-2019",
        },
        "📼 2000–2009": {
            "from_date": "2000-01-01",
            "to_date": "2009-12-31",
            "name": "2000-2009",
        },
        "📺 До 2000": {
            "from_date": "1900-01-01",
            "to_date": "1999-12-31",
            "name": "before2000",
        },
        "🎲 Любой год": {
            "from_date": None,
            "to_date": None,
            "name": "any",
        },
    }

    return settings.get(
        year_text,
        {
            "from_date": None,
            "to_date": None,
            "name": "any",
        }
    )


def get_country_settings(country_text: str) -> dict:
    countries = {
        "🌍 Любая страна": None,
        "🇰🇿 Казахстан": "KZ",
        "🇷🇺 Россия": "RU",
        "🇺🇸 США": "US",
        "🇬🇧 Великобритания": "GB",
        "🇫🇷 Франция": "FR",
        "🇯🇵 Япония": "JP",
        "🇰🇷 Корея": "KR",
        "🇮🇳 Индия": "IN",
        "🇩🇪 Германия": "DE",
    }

    country_code = countries.get(country_text)

    return {
        "country_code": country_code,
        "name": country_code or "any",
    }


def build_filter_key(
    media_type: str,
    genre_text: str,
    rating_settings: dict,
    year_settings: dict,
    country_settings: dict
) -> str:
    genre_id = get_genre_id(genre_text, media_type) or "any"
    rating_name = rating_settings.get("name", "any")
    year_name = year_settings.get("name", "any")
    country_name = country_settings.get("name", "any")

    return (
        f"media={media_type}|genre={genre_id}|"
        f"rating={rating_name}|year={year_name}|country={country_name}"
    )


def get_min_votes_steps(rating_settings: dict, country_settings: dict) -> list[int]:
    base_votes = rating_settings["min_votes"]
    country_code = country_settings.get("country_code")
    rating_name = rating_settings.get("name", "any")

    if country_code == "KZ":
        if rating_name == "8plus":
            steps = [base_votes, 50, 20, 10, 5, 0]
        else:
            steps = [base_votes, 20, 10, 5, 0]
    elif country_code and country_code != "US":
        if rating_name == "8plus":
            steps = [base_votes, 100, 50, 20, 10, 0]
        else:
            steps = [base_votes, 50, 20, 10, 0]
    elif country_code == "US":
        if rating_name == "8plus":
            steps = [base_votes, 150, 100, 50, 20]
        else:
            steps = [base_votes, 100, 50, 20, 0]
    else:
        if rating_name == "8plus":
            steps = [base_votes, 150, 100, 50, 20]
        else:
            steps = [base_votes, 100, 50, 20, 0]

    clean_steps = []
    for step in steps:
        if step not in clean_steps and step <= base_votes:
            clean_steps.append(step)

    return clean_steps


def build_tmdb_params(
    media_type: str,
    genre_text: str,
    rating_settings: dict,
    year_settings: dict,
    country_settings: dict,
    min_votes: int
):
    genre_id = get_genre_id(genre_text, media_type)
    country_code = country_settings.get("country_code")

    params = {
        "api_key": TMDB_API_KEY,
        "language": "ru-RU",
        "sort_by": rating_settings["sort_by"],
        "vote_average.gte": rating_settings["min_rating"],
        "vote_average.lte": rating_settings["max_rating"],
        "vote_count.gte": min_votes,
        "include_adult": "false",
        "page": 1,
    }

    if genre_id:
        params["with_genres"] = genre_id

    if media_type == "tv":
        if year_settings["from_date"]:
            params["first_air_date.gte"] = year_settings["from_date"]

        if year_settings["to_date"]:
            params["first_air_date.lte"] = year_settings["to_date"]
    else:
        if year_settings["from_date"]:
            params["primary_release_date.gte"] = year_settings["from_date"]

        if year_settings["to_date"]:
            params["primary_release_date.lte"] = year_settings["to_date"]

    if country_code:
        params["with_origin_country"] = country_code

    return params


async def fetch_items_from_tmdb(
    session: aiohttp.ClientSession,
    media_type: str,
    params: dict
):
    if media_type == "tv":
        url = "https://api.themoviedb.org/3/discover/tv"
    else:
        url = "https://api.themoviedb.org/3/discover/movie"

    async with session.get(url, params=params) as response:
        if response.status != 200:
            return [], 0

        data = await response.json()
        items = data.get("results", [])
        total_pages = data.get("total_pages", 0)

        return items, total_pages


async def collect_items_from_pages(
    session: aiohttp.ClientSession,
    media_type: str,
    params: dict
):
    first_page_params = params.copy()
    first_page_params["page"] = 1

    items, total_pages = await fetch_items_from_tmdb(
        session,
        media_type,
        first_page_params
    )

    if total_pages <= 1:
        return items

    max_page = min(total_pages, 30)

    pages = list(range(2, max_page + 1))
    random.shuffle(pages)

    selected_pages = pages[:8]

    for page in selected_pages:
        page_params = params.copy()
        page_params["page"] = page

        page_items, _ = await fetch_items_from_tmdb(
            session,
            media_type,
            page_params
        )
        items.extend(page_items)

    return items


async def get_item_by_filters(
    user_id: int,
    media_type: str,
    genre_text: str,
    rating_settings: dict,
    year_settings: dict,
    country_settings: dict
):
    filter_key = build_filter_key(
        media_type,
        genre_text,
        rating_settings,
        year_settings,
        country_settings
    )

    seen_items = get_seen_item_ids(user_id, filter_key)
    min_votes_steps = get_min_votes_steps(rating_settings, country_settings)

    all_items_found = []

    async with aiohttp.ClientSession() as session:
        for min_votes in min_votes_steps:
            params = build_tmdb_params(
                media_type,
                genre_text,
                rating_settings,
                year_settings,
                country_settings,
                min_votes
            )

            items = await collect_items_from_pages(session, media_type, params)

            if not items:
                continue

            unique_items = {}
            for item in items:
                item_id = item.get("id")
                if item_id:
                    unique_items[item_id] = item

            items = list(unique_items.values())
            all_items_found.extend(items)

            unseen_items = [
                item for item in items
                if item.get("id") not in seen_items
            ]

            if unseen_items:
                selected_item = random.choice(unseen_items)
                selected_item["_media_type"] = media_type

                return {
                    "status": "ok",
                    "item": selected_item,
                    "filter_key": filter_key,
                    "used_min_votes": min_votes,
                }

    if not all_items_found:
        return {
            "status": "not_found",
            "item": None,
            "filter_key": filter_key,
            "used_min_votes": None,
        }

    return {
        "status": "exhausted",
        "item": None,
        "filter_key": filter_key,
        "used_min_votes": None,
    }


def get_item_links(item: dict):
    media_type = item.get("_media_type", "movie")
    title = get_title(item)
    year = get_release_year(item)

    kinopoisk_query = quote_plus(f"{title} {year}")
    kinopoisk_url = f"https://www.kinopoisk.ru/index.php?kp_query={kinopoisk_query}"

    if media_type == "tv":
        tmdb_url = f"https://www.themoviedb.org/tv/{item.get('id')}"
    else:
        tmdb_url = f"https://www.themoviedb.org/movie/{item.get('id')}"

    return kinopoisk_url, tmdb_url


def get_poster_url(item: dict):
    poster_path = item.get("poster_path")

    if not poster_path:
        return None

    return f"https://image.tmdb.org/t/p/w500{poster_path}"


def build_item_keyboard(item: dict) -> InlineKeyboardMarkup:
    kinopoisk_url, tmdb_url = get_item_links(item)
    item_id = item.get("id")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔎 КиноПоиск", url=kinopoisk_url),
                InlineKeyboardButton(text="🌐 TMDB", url=tmdb_url),
            ],
            [
                InlineKeyboardButton(text="⭐ В избранное", callback_data=f"favorite:{item_id}"),
            ],
            [
                InlineKeyboardButton(text="🔁 Другой вариант", callback_data="another_item"),
            ],
        ]
    )


def build_no_more_items_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Сбросить повторы",
                    callback_data="reset_seen_items"
                ),
            ],
        ]
    )


def build_favorite_keyboard(movie_id: int, kinopoisk_url: str, tmdb_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔎 КиноПоиск", url=kinopoisk_url),
                InlineKeyboardButton(text="🌐 TMDB", url=tmdb_url),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить из избранного",
                    callback_data=f"delete_favorite:{movie_id}"
                ),
            ],
        ]
    )


def build_item_text(item: dict) -> str:
    media_type = item.get("_media_type", "movie")
    media_label = get_media_label(media_type)

    title = get_title(item)
    original_title = get_original_title(item)
    year = get_release_year(item)
    rating = item.get("vote_average", "Нет рейтинга")
    votes = item.get("vote_count", 0)
    description = item.get("overview") or "Описание отсутствует."

    return (
        f"🎬 <b>{title}</b>\n"
        f"📌 Тип: {media_label}\n"
        f"🌍 Оригинальное название: {original_title}\n"
        f"📅 Год: {year}\n"
        f"⭐ Рейтинг TMDB: {rating}/10\n"
        f"👥 Голосов: {votes}\n\n"
        f"📝 {description}"
    )


def build_favorite_text(
    title: str,
    original_title: str,
    year: str,
    rating: str,
    media_type: str
) -> str:
    return (
        f"🎬 <b>{title}</b>\n"
        f"📌 Тип: {get_media_label(media_type)}\n"
        f"🌍 Оригинальное название: {original_title}\n"
        f"📅 Год: {year}\n"
        f"⭐ Рейтинг TMDB: {rating}/10"
    )


async def send_item_card(message: Message, item: dict):
    item_text = build_item_text(item)
    item_keyboard = build_item_keyboard(item)
    poster_url = get_poster_url(item)

    if poster_url:
        await message.answer_photo(
            photo=poster_url,
            caption=item_text,
            parse_mode="HTML",
            reply_markup=item_keyboard
        )
    else:
        await message.answer(
            item_text,
            parse_mode="HTML",
            reply_markup=item_keyboard
        )


async def send_no_items_message(message: Message, exhausted: bool):
    if exhausted:
        await message.answer(
            "По этому запросу больше нет новых вариантов 😢\n\n"
            "Попробуй изменить фильтры:\n"
            "• выбрать другой рейтинг;\n"
            "• выбрать другой год;\n"
            "• выбрать другую страну;\n"
            "• выбрать «Любая страна» или «Любой год».\n\n"
            "Либо можешь сбросить повторы и начать показывать варианты заново.",
            reply_markup=build_no_more_items_keyboard()
        )
    else:
        await message.answer(
            "Не смог найти вариант по таким фильтрам 😢\n\n"
            "Попробуй выбрать более широкий фильтр: "
            "например «Любой год», «Любая страна» или другой рейтинг."
        )


async def send_item(
    message: Message,
    media_type: str,
    genre_text: str,
    rating_settings: dict,
    year_settings: dict,
    country_settings: dict
):
    await message.answer("Ищу вариант... 🎬")

    user_id = message.from_user.id

    result = await get_item_by_filters(
        user_id,
        media_type,
        genre_text,
        rating_settings,
        year_settings,
        country_settings
    )

    user_last_filter_key[user_id] = result["filter_key"]

    if result["status"] == "not_found":
        await send_no_items_message(message, exhausted=False)
        return

    if result["status"] == "exhausted":
        await send_no_items_message(message, exhausted=True)
        return

    item = result["item"]
    item_id = item.get("id")

    last_items[user_id] = item

    if item_id:
        remember_seen_item(user_id, result["filter_key"], item_id)

    await send_item_card(message, item)


@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer(
        "Привет! 🎬\n\n"
        "Я бот «Что посмотреть вечером».\n"
        "Помогу подобрать фильм или сериал по жанру, рейтингу, году и стране 😎\n\n"
        "Выбери действие на клавиатуре ниже:",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "🎬 Подобрать")
async def choose_media(message: Message):
    await message.answer(
        "Что будем искать?",
        reply_markup=media_keyboard
    )


@dp.message(F.text == "⭐ Избранное")
async def favorites(message: Message):
    rows = get_favorites(message.from_user.id)

    if not rows:
        await message.answer(
            "У тебя пока нет избранного ⭐\n\n"
            "Выбери фильм или сериал и нажми кнопку «⭐ В избранное»."
        )
        return

    await message.answer("⭐ <b>Твоё избранное:</b>", parse_mode="HTML")

    for row in rows:
        movie_id, title, original_title, year, rating, tmdb_url, kinopoisk_url, media_type = row

        await message.answer(
            build_favorite_text(title, original_title, year, rating, media_type or "movie"),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=build_favorite_keyboard(movie_id, kinopoisk_url, tmdb_url)
        )


@dp.message(F.text == "ℹ️ Помощь")
async def help_message(message: Message):
    await message.answer(
        "Я помогу подобрать фильм или сериал по жанру, рейтингу, году и стране.\n\n"
        "Нажми «🎬 Подобрать», выбери тип, жанр, "
        "потом диапазон рейтинга, год и страну, "
        "и я найду вариант через TMDB API.\n\n"
        "Если бот ничего не нашёл, попробуй выбрать более широкий фильтр: "
        "например «Любой год» или «Любая страна».\n\n"
        "Понравился вариант? Нажми «⭐ В избранное», "
        "и он сохранится в твоём списке."
    )


@dp.message(F.text == "⬅️ Назад")
async def back_to_menu(message: Message):
    await message.answer(
        "Вернул тебя в главное меню.",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "⬅️ Назад к типу")
async def back_to_media(message: Message):
    await message.answer(
        "Что будем искать?",
        reply_markup=media_keyboard
    )


@dp.message(F.text == "⬅️ Назад к жанрам")
async def back_to_genres(message: Message):
    await message.answer(
        "Выбери жанр:",
        reply_markup=genre_keyboard
    )


@dp.message(F.text == "⬅️ Назад к рейтингу")
async def back_to_rating(message: Message):
    await message.answer(
        "Выбери диапазон рейтинга:",
        reply_markup=rating_keyboard
    )


@dp.message(F.text == "⬅️ Назад к году")
async def back_to_year(message: Message):
    await message.answer(
        "Выбери год:",
        reply_markup=year_keyboard
    )


@dp.message(F.text.in_([
    "🎬 Фильмы",
    "📺 Сериалы",
]))
async def media_selected(message: Message):
    user_id = message.from_user.id
    media_type = get_media_type_from_text(message.text)

    user_last_media[user_id] = media_type

    await message.answer(
        "Выбери жанр:",
        reply_markup=genre_keyboard
    )


@dp.message(F.text.in_([
    "🎭 Любой жанр",
    "😂 Комедия",
    "🚀 Фантастика",
    "😱 Ужасы",
    "🔫 Боевик",
    "🧨 Триллер",
    "🕵️ Детектив",
    "🧟 Криминал",
    "❤️ Романтика",
    "🐉 Фэнтези",
    "🎬 Драма",
    "🗺 Приключения",
    "🧒 Семейный",
    "🎞 Мультфильм",
    "📚 История",
    "⚔️ Военный",
    "🎵 Музыка",
    "📺 Документальный",
    "🤠 Вестерн",
    "📺 ТВ-фильм",
]))
async def genre_selected(message: Message):
    user_id = message.from_user.id

    if user_id not in user_last_media:
        await message.answer(
            "Сначала выбери, что искать: фильм или сериал.",
            reply_markup=media_keyboard
        )
        return

    user_last_genre[user_id] = message.text

    await message.answer(
        "Теперь выбери диапазон рейтинга:",
        reply_markup=rating_keyboard
    )


@dp.message(F.text.in_([
    "⭐ 1–4",
    "⭐ 5–6",
    "⭐ 7–8",
    "⭐ 8+",
    "🎲 Любой рейтинг",
]))
async def rating_selected(message: Message):
    user_id = message.from_user.id
    genre_text = user_last_genre.get(user_id)

    if not genre_text:
        await message.answer(
            "Сначала выбери жанр 🎬",
            reply_markup=genre_keyboard
        )
        return

    rating_settings = get_rating_settings(message.text)
    user_last_rating[user_id] = rating_settings

    await message.answer(
        "Теперь выбери год:",
        reply_markup=year_keyboard
    )


@dp.message(F.text.in_([
    "🆕 Новые 2020+",
    "🎞 2010–2019",
    "📼 2000–2009",
    "📺 До 2000",
    "🎲 Любой год",
]))
async def year_selected(message: Message):
    user_id = message.from_user.id

    genre_text = user_last_genre.get(user_id)
    rating_settings = user_last_rating.get(user_id)

    if not genre_text:
        await message.answer(
            "Сначала выбери жанр 🎬",
            reply_markup=genre_keyboard
        )
        return

    if not rating_settings:
        await message.answer(
            "Сначала выбери рейтинг ⭐",
            reply_markup=rating_keyboard
        )
        return

    year_settings = get_year_settings(message.text)
    user_last_year[user_id] = year_settings

    await message.answer(
        "Теперь выбери страну производства:",
        reply_markup=country_keyboard
    )


@dp.message(F.text.in_([
    "🌍 Любая страна",
    "🇰🇿 Казахстан",
    "🇷🇺 Россия",
    "🇺🇸 США",
    "🇬🇧 Великобритания",
    "🇫🇷 Франция",
    "🇯🇵 Япония",
    "🇰🇷 Корея",
    "🇮🇳 Индия",
    "🇩🇪 Германия",
]))
async def country_selected(message: Message):
    user_id = message.from_user.id

    media_type = user_last_media.get(user_id)
    genre_text = user_last_genre.get(user_id)
    rating_settings = user_last_rating.get(user_id)
    year_settings = user_last_year.get(user_id)

    if not media_type:
        await message.answer(
            "Сначала выбери, что искать: фильм или сериал.",
            reply_markup=media_keyboard
        )
        return

    if not genre_text:
        await message.answer(
            "Сначала выбери жанр 🎬",
            reply_markup=genre_keyboard
        )
        return

    if not rating_settings:
        await message.answer(
            "Сначала выбери рейтинг ⭐",
            reply_markup=rating_keyboard
        )
        return

    if not year_settings:
        await message.answer(
            "Сначала выбери год 📅",
            reply_markup=year_keyboard
        )
        return

    country_settings = get_country_settings(message.text)
    user_last_country[user_id] = country_settings

    await send_item(
        message,
        media_type,
        genre_text,
        rating_settings,
        year_settings,
        country_settings
    )


@dp.callback_query(F.data == "another_item")
async def another_item(callback: CallbackQuery):
    user_id = callback.from_user.id

    media_type = user_last_media.get(user_id)
    genre_text = user_last_genre.get(user_id)
    rating_settings = user_last_rating.get(user_id)
    year_settings = user_last_year.get(
        user_id,
        {
            "from_date": None,
            "to_date": None,
            "name": "any",
        }
    )
    country_settings = user_last_country.get(
        user_id,
        {
            "country_code": None,
            "name": "any",
        }
    )

    if not media_type:
        await callback.answer("Сначала выбери фильм или сериал 🎬", show_alert=True)
        return

    if not genre_text:
        await callback.answer("Сначала выбери жанр 🎬", show_alert=True)
        return

    if not rating_settings:
        await callback.answer("Сначала выбери рейтинг ⭐", show_alert=True)
        return

    await callback.answer("Ищу другой вариант...")

    result = await get_item_by_filters(
        user_id,
        media_type,
        genre_text,
        rating_settings,
        year_settings,
        country_settings
    )

    user_last_filter_key[user_id] = result["filter_key"]

    if result["status"] == "not_found":
        await callback.message.answer(
            "Не смог найти новый вариант по таким фильтрам 😢\n\n"
            "Попробуй выбрать более широкий фильтр: "
            "например «Любой год», «Любая страна» или другой рейтинг."
        )
        return

    if result["status"] == "exhausted":
        await callback.message.answer(
            "По этому запросу больше нет новых вариантов 😢\n\n"
            "Попробуй поменять жанр, рейтинг, год или страну.\n"
            "Либо сбрось повторы и начни показ заново.",
            reply_markup=build_no_more_items_keyboard()
        )
        return

    item = result["item"]
    item_id = item.get("id")

    last_items[user_id] = item

    if item_id:
        remember_seen_item(user_id, result["filter_key"], item_id)

    await send_item_card(callback.message, item)


@dp.callback_query(F.data == "reset_seen_items")
async def reset_seen_items(callback: CallbackQuery):
    user_id = callback.from_user.id
    filter_key = user_last_filter_key.get(user_id)

    reset_seen_items_for_user(user_id, filter_key)

    await callback.answer("Повторы сброшены 🔄")
    await callback.message.answer(
        "Готово! Теперь можно снова получать варианты по этим же фильтрам."
    )


@dp.callback_query(F.data.startswith("favorite:"))
async def add_item_to_favorites(callback: CallbackQuery):
    user_id = callback.from_user.id
    item = last_items.get(user_id)

    if not item:
        await callback.answer("Сначала получи вариант 🎬", show_alert=True)
        return

    added = add_favorite(user_id, item)

    if added:
        await callback.answer("Добавлено в избранное ⭐")
    else:
        await callback.answer("Уже есть в избранном ⭐", show_alert=True)


@dp.callback_query(F.data.startswith("delete_favorite:"))
async def delete_item_from_favorites(callback: CallbackQuery):
    user_id = callback.from_user.id
    movie_id_text = callback.data.split(":")[1]

    try:
        movie_id = int(movie_id_text)
    except ValueError:
        await callback.answer("Ошибка удаления 😢", show_alert=True)
        return

    deleted = delete_favorite(user_id, movie_id)

    if deleted:
        await callback.answer("Удалено из избранного 🗑")
        await callback.message.edit_text(
            "🗑 Удалено из избранного.",
            reply_markup=None
        )
    else:
        await callback.answer("Уже удалено или не найдено.", show_alert=True)


async def main_page(request):
    return web.Response(text="Movie bot is running")


async def on_startup(bot: Bot):
    webhook_full_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_full_url)
    logging.info(f"Webhook установлен: {webhook_full_url}")


async def start_polling_mode():
    logging.basicConfig(level=logging.INFO)

    init_db()

    bot = Bot(token=BOT_TOKEN)

    logging.info("Запуск в режиме polling")
    await dp.start_polling(bot)


def start_webhook_mode():
    logging.basicConfig(level=logging.INFO)

    init_db()

    bot = Bot(token=BOT_TOKEN)

    dp.startup.register(on_startup)

    app = web.Application()

    app.router.add_get("/", main_page)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)

    logging.info("Запуск в режиме webhook")
    logging.info(f"Сервер запущен на порту {WEB_SERVER_PORT}")

    web.run_app(
        app,
        host=WEB_SERVER_HOST,
        port=WEB_SERVER_PORT
    )


if __name__ == "__main__":
    if WEBHOOK_URL:
        start_webhook_mode()
    else:
        asyncio.run(start_polling_mode())