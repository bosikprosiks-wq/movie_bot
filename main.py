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

user_last_genre = {}
user_last_rating = {}
user_last_year = {}
user_last_country = {}
user_last_filter_key = {}
last_movies = {}


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎬 Подобрать фильм")],
        [
            KeyboardButton(text="⭐ Избранное"),
            KeyboardButton(text="ℹ️ Помощь"),
        ],
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
        [KeyboardButton(text="⬅️ Назад")],
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

    connection.commit()
    connection.close()


def add_favorite(user_id: int, movie: dict):
    title = movie.get("title") or movie.get("original_title") or "Без названия"
    original_title = movie.get("original_title") or title
    release_date = movie.get("release_date") or "Неизвестно"
    year = release_date[:4] if release_date != "Неизвестно" else "Неизвестно"
    rating = str(movie.get("vote_average", "Нет рейтинга"))

    kinopoisk_url, tmdb_url = get_movie_links(movie)

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
            kinopoisk_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            movie.get("id"),
            title,
            original_title,
            year,
            rating,
            tmdb_url,
            kinopoisk_url,
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
        SELECT movie_id, title, original_title, year, rating, tmdb_url, kinopoisk_url
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


def remember_seen_movie(user_id: int, filter_key: str, movie_id: int):
    if not movie_id:
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
        (user_id, filter_key, movie_id)
    )

    connection.commit()
    connection.close()


def get_seen_movie_ids(user_id: int, filter_key: str):
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


def reset_seen_movies_for_user(user_id: int, filter_key: str | None = None):
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


def get_genre_id(genre_text: str) -> str:
    genres = {
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

    return genres.get(genre_text, "")


def get_rating_settings(rating_text: str) -> dict:
    settings = {
        "⭐ 1–4": {
            "min_rating": 1.0,
            "max_rating": 4.99,
            "min_votes": 20,
            "sort_by": "popularity.desc",
            "allow_soft_search": True,
            "name": "1-4",
        },
        "⭐ 5–6": {
            "min_rating": 5.0,
            "max_rating": 6.99,
            "min_votes": 50,
            "sort_by": "popularity.desc",
            "allow_soft_search": True,
            "name": "5-6",
        },
        "⭐ 7–8": {
            "min_rating": 7.0,
            "max_rating": 8.99,
            "min_votes": 150,
            "sort_by": "popularity.desc",
            "allow_soft_search": True,
            "name": "7-8",
        },
        "⭐ 8+": {
            "min_rating": 8.0,
            "max_rating": 10.0,
            "min_votes": 300,
            "sort_by": "popularity.desc",
            "allow_soft_search": False,
            "name": "8plus",
        },
        "🎲 Любой рейтинг": {
            "min_rating": 0.0,
            "max_rating": 10.0,
            "min_votes": 50,
            "sort_by": "popularity.desc",
            "allow_soft_search": True,
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
            "allow_soft_search": True,
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
    genre_text: str,
    rating_settings: dict,
    year_settings: dict,
    country_settings: dict
) -> str:
    genre_id = get_genre_id(genre_text) or "any"
    rating_name = rating_settings.get("name", "any")
    year_name = year_settings.get("name", "any")
    country_name = country_settings.get("name", "any")

    return f"genre={genre_id}|rating={rating_name}|year={year_name}|country={country_name}"


def build_tmdb_params(
    genre_text: str,
    rating_settings: dict,
    year_settings: dict,
    country_settings: dict,
    min_votes_override: int | None = None
):
    genre_id = get_genre_id(genre_text)
    country_code = country_settings.get("country_code")

    params = {
        "api_key": TMDB_API_KEY,
        "language": "ru-RU",
        "sort_by": rating_settings["sort_by"],
        "vote_average.gte": rating_settings["min_rating"],
        "vote_average.lte": rating_settings["max_rating"],
        "vote_count.gte": min_votes_override
        if min_votes_override is not None
        else rating_settings["min_votes"],
        "include_adult": "false",
        "page": 1,
    }

    if genre_id:
        params["with_genres"] = genre_id

    if year_settings["from_date"]:
        params["primary_release_date.gte"] = year_settings["from_date"]

    if year_settings["to_date"]:
        params["primary_release_date.lte"] = year_settings["to_date"]

    if country_code:
        params["with_origin_country"] = country_code

    return params


async def fetch_movies_from_tmdb(session: aiohttp.ClientSession, params: dict):
    url = "https://api.themoviedb.org/3/discover/movie"

    async with session.get(url, params=params) as response:
        if response.status != 200:
            return [], 0

        data = await response.json()
        movies = data.get("results", [])
        total_pages = data.get("total_pages", 0)

        return movies, total_pages


async def collect_movies_from_pages(session: aiohttp.ClientSession, params: dict):
    first_page_params = params.copy()
    first_page_params["page"] = 1

    movies, total_pages = await fetch_movies_from_tmdb(session, first_page_params)

    if total_pages <= 1:
        return movies

    max_page = min(total_pages, 20)

    pages = list(range(2, max_page + 1))
    random.shuffle(pages)

    selected_pages = pages[:5]

    for page in selected_pages:
        page_params = params.copy()
        page_params["page"] = page

        page_movies, _ = await fetch_movies_from_tmdb(session, page_params)
        movies.extend(page_movies)

    return movies


async def get_movie_by_filters(
    user_id: int,
    genre_text: str,
    rating_settings: dict,
    year_settings: dict,
    country_settings: dict
):
    filter_key = build_filter_key(
        genre_text,
        rating_settings,
        year_settings,
        country_settings
    )

    seen_movies = get_seen_movie_ids(user_id, filter_key)

    async with aiohttp.ClientSession() as session:
        params = build_tmdb_params(
            genre_text,
            rating_settings,
            year_settings,
            country_settings
        )

        movies = await collect_movies_from_pages(session, params)

        if (
            not movies
            and rating_settings["min_votes"] > 0
            and rating_settings.get("allow_soft_search", True)
        ):
            soft_params = build_tmdb_params(
                genre_text,
                rating_settings,
                year_settings,
                country_settings,
                min_votes_override=0
            )

            movies = await collect_movies_from_pages(session, soft_params)

    if not movies:
        return {
            "status": "not_found",
            "movie": None,
            "filter_key": filter_key,
        }

    unique_movies = {}
    for movie in movies:
        movie_id = movie.get("id")
        if movie_id:
            unique_movies[movie_id] = movie

    movies = list(unique_movies.values())

    unseen_movies = [
        movie for movie in movies
        if movie.get("id") not in seen_movies
    ]

    if unseen_movies:
        return {
            "status": "ok",
            "movie": random.choice(unseen_movies),
            "filter_key": filter_key,
        }

    return {
        "status": "exhausted",
        "movie": None,
        "filter_key": filter_key,
    }


def get_movie_links(movie: dict):
    title = movie.get("title") or movie.get("original_title") or "Без названия"
    release_date = movie.get("release_date") or "Неизвестно"
    year = release_date[:4] if release_date != "Неизвестно" else ""

    kinopoisk_query = quote_plus(f"{title} {year}")
    kinopoisk_url = f"https://www.kinopoisk.ru/index.php?kp_query={kinopoisk_query}"

    tmdb_url = f"https://www.themoviedb.org/movie/{movie.get('id')}"

    return kinopoisk_url, tmdb_url


def get_poster_url(movie: dict):
    poster_path = movie.get("poster_path")

    if not poster_path:
        return None

    return f"https://image.tmdb.org/t/p/w500{poster_path}"


def build_movie_keyboard(movie: dict) -> InlineKeyboardMarkup:
    kinopoisk_url, tmdb_url = get_movie_links(movie)
    movie_id = movie.get("id")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔎 КиноПоиск", url=kinopoisk_url),
                InlineKeyboardButton(text="🌐 TMDB", url=tmdb_url),
            ],
            [
                InlineKeyboardButton(text="⭐ В избранное", callback_data=f"favorite:{movie_id}"),
            ],
            [
                InlineKeyboardButton(text="🔁 Другой фильм", callback_data="another_movie"),
            ],
        ]
    )


def build_no_more_movies_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Сбросить повторы",
                    callback_data="reset_seen_movies"
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


def build_movie_text(movie: dict) -> str:
    title = movie.get("title") or movie.get("original_title") or "Без названия"
    original_title = movie.get("original_title") or title
    release_date = movie.get("release_date") or "Неизвестно"
    year = release_date[:4] if release_date != "Неизвестно" else "Неизвестно"
    rating = movie.get("vote_average", "Нет рейтинга")
    description = movie.get("overview") or "Описание отсутствует."

    return (
        f"🎬 <b>{title}</b>\n"
        f"🌍 Оригинальное название: {original_title}\n"
        f"📅 Год: {year}\n"
        f"⭐ Рейтинг TMDB: {rating}/10\n\n"
        f"📝 {description}"
    )


def build_favorite_text(title: str, original_title: str, year: str, rating: str) -> str:
    return (
        f"🎬 <b>{title}</b>\n"
        f"🌍 Оригинальное название: {original_title}\n"
        f"📅 Год: {year}\n"
        f"⭐ Рейтинг TMDB: {rating}/10"
    )


async def send_movie_card(message: Message, movie: dict):
    movie_text = build_movie_text(movie)
    movie_keyboard = build_movie_keyboard(movie)
    poster_url = get_poster_url(movie)

    if poster_url:
        await message.answer_photo(
            photo=poster_url,
            caption=movie_text,
            parse_mode="HTML",
            reply_markup=movie_keyboard
        )
    else:
        await message.answer(
            movie_text,
            parse_mode="HTML",
            reply_markup=movie_keyboard
        )


async def send_no_movies_message(message: Message, exhausted: bool):
    if exhausted:
        await message.answer(
            "По этому запросу больше нет новых фильмов 😢\n\n"
            "Попробуй изменить фильтры:\n"
            "• выбрать другой рейтинг;\n"
            "• выбрать другой год;\n"
            "• выбрать другую страну;\n"
            "• выбрать «Любая страна» или «Любой год».\n\n"
            "Либо можешь сбросить повторы и начать показывать фильмы заново.",
            reply_markup=build_no_more_movies_keyboard()
        )
    else:
        await message.answer(
            "Не смог найти фильм по таким фильтрам 😢\n\n"
            "Попробуй выбрать более широкий фильтр: "
            "например «Любой год», «Любая страна» или другой рейтинг."
        )


async def send_movie(
    message: Message,
    genre_text: str,
    rating_settings: dict,
    year_settings: dict,
    country_settings: dict
):
    await message.answer("Ищу фильм... 🎬")

    user_id = message.from_user.id

    result = await get_movie_by_filters(
        user_id,
        genre_text,
        rating_settings,
        year_settings,
        country_settings
    )

    user_last_filter_key[user_id] = result["filter_key"]

    if result["status"] == "not_found":
        await send_no_movies_message(message, exhausted=False)
        return

    if result["status"] == "exhausted":
        await send_no_movies_message(message, exhausted=True)
        return

    movie = result["movie"]
    movie_id = movie.get("id")

    last_movies[user_id] = movie

    if movie_id:
        remember_seen_movie(user_id, result["filter_key"], movie_id)

    await send_movie_card(message, movie)


@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer(
        "Привет! 🎬\n\n"
        "Я бот «Что посмотреть вечером».\n"
        "Помогу подобрать фильм по жанру, рейтингу, году и стране 😎\n\n"
        "Выбери действие на клавиатуре ниже:",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "🎬 Подобрать фильм")
async def choose_movie(message: Message):
    await message.answer(
        "Выбери жанр фильма:",
        reply_markup=genre_keyboard
    )


@dp.message(F.text == "⭐ Избранное")
async def favorites(message: Message):
    rows = get_favorites(message.from_user.id)

    if not rows:
        await message.answer(
            "У тебя пока нет избранных фильмов ⭐\n\n"
            "Выбери фильм и нажми кнопку «⭐ В избранное»."
        )
        return

    await message.answer("⭐ <b>Твоё избранное:</b>", parse_mode="HTML")

    for row in rows:
        movie_id, title, original_title, year, rating, tmdb_url, kinopoisk_url = row

        await message.answer(
            build_favorite_text(title, original_title, year, rating),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=build_favorite_keyboard(movie_id, kinopoisk_url, tmdb_url)
        )


@dp.message(F.text == "ℹ️ Помощь")
async def help_message(message: Message):
    await message.answer(
        "Я помогу подобрать фильм по жанру, рейтингу, году и стране.\n\n"
        "Нажми «🎬 Подобрать фильм», выбери жанр, "
        "потом диапазон рейтинга, год и страну, "
        "и я найду фильм через TMDB API.\n\n"
        "Если бот ничего не нашёл, попробуй выбрать более широкий фильтр: "
        "например «Любой год» или «Любая страна».\n\n"
        "Понравился фильм? Нажми «⭐ В избранное», "
        "и он сохранится в твоём списке."
    )


@dp.message(F.text == "⬅️ Назад")
async def back_to_menu(message: Message):
    await message.answer(
        "Вернул тебя в главное меню.",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "⬅️ Назад к жанрам")
async def back_to_genres(message: Message):
    await message.answer(
        "Выбери жанр фильма:",
        reply_markup=genre_keyboard
    )


@dp.message(F.text == "⬅️ Назад к рейтингу")
async def back_to_rating(message: Message):
    await message.answer(
        "Выбери диапазон рейтинга фильма:",
        reply_markup=rating_keyboard
    )


@dp.message(F.text == "⬅️ Назад к году")
async def back_to_year(message: Message):
    await message.answer(
        "Выбери год выпуска:",
        reply_markup=year_keyboard
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
    user_last_genre[user_id] = message.text

    await message.answer(
        "Теперь выбери диапазон рейтинга фильма:",
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
        "Теперь выбери год выпуска:",
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

    genre_text = user_last_genre.get(user_id)
    rating_settings = user_last_rating.get(user_id)
    year_settings = user_last_year.get(user_id)

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

    await send_movie(
        message,
        genre_text,
        rating_settings,
        year_settings,
        country_settings
    )


@dp.callback_query(F.data == "another_movie")
async def another_movie(callback: CallbackQuery):
    user_id = callback.from_user.id

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

    if not genre_text:
        await callback.answer("Сначала выбери жанр 🎬", show_alert=True)
        return

    if not rating_settings:
        await callback.answer("Сначала выбери рейтинг ⭐", show_alert=True)
        return

    await callback.answer("Ищу другой фильм...")

    result = await get_movie_by_filters(
        user_id,
        genre_text,
        rating_settings,
        year_settings,
        country_settings
    )

    user_last_filter_key[user_id] = result["filter_key"]

    if result["status"] == "not_found":
        await callback.message.answer(
            "Не смог найти новый фильм по таким фильтрам 😢\n\n"
            "Попробуй выбрать более широкий фильтр: "
            "например «Любой год», «Любая страна» или другой рейтинг."
        )
        return

    if result["status"] == "exhausted":
        await callback.message.answer(
            "По этому запросу больше нет новых фильмов 😢\n\n"
            "Попробуй поменять жанр, рейтинг, год или страну.\n"
            "Либо сбрось повторы и начни показ заново.",
            reply_markup=build_no_more_movies_keyboard()
        )
        return

    movie = result["movie"]
    movie_id = movie.get("id")

    last_movies[user_id] = movie

    if movie_id:
        remember_seen_movie(user_id, result["filter_key"], movie_id)

    await send_movie_card(callback.message, movie)


@dp.callback_query(F.data == "reset_seen_movies")
async def reset_seen_movies(callback: CallbackQuery):
    user_id = callback.from_user.id
    filter_key = user_last_filter_key.get(user_id)

    reset_seen_movies_for_user(user_id, filter_key)

    await callback.answer("Повторы сброшены 🔄")
    await callback.message.answer(
        "Готово! Теперь можно снова получать фильмы по этим же фильтрам."
    )


@dp.callback_query(F.data.startswith("favorite:"))
async def add_movie_to_favorites(callback: CallbackQuery):
    user_id = callback.from_user.id
    movie = last_movies.get(user_id)

    if not movie:
        await callback.answer("Сначала получи фильм 🎬", show_alert=True)
        return

    added = add_favorite(user_id, movie)

    if added:
        await callback.answer("Фильм добавлен в избранное ⭐")
    else:
        await callback.answer("Этот фильм уже есть в избранном ⭐", show_alert=True)


@dp.callback_query(F.data.startswith("delete_favorite:"))
async def delete_movie_from_favorites(callback: CallbackQuery):
    user_id = callback.from_user.id
    movie_id_text = callback.data.split(":")[1]

    try:
        movie_id = int(movie_id_text)
    except ValueError:
        await callback.answer("Ошибка удаления 😢", show_alert=True)
        return

    deleted = delete_favorite(user_id, movie_id)

    if deleted:
        await callback.answer("Фильм удалён из избранного 🗑")
        await callback.message.edit_text(
            "🗑 Фильм удалён из избранного.",
            reply_markup=None
        )
    else:
        await callback.answer("Фильм уже удалён или не найден.", show_alert=True)


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