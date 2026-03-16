"""
db.py
-----
Модуль, отвечающий за работу с базой данных SQLite в проекте CREDDIT.

Основные задачи этого файла:
- создать (инициализировать) структуру базы данных: таблицы users, posts,
  comments, votes;
- предоставить удобные функции для:
  - получения подключения к базе в рамках одного HTTP‑запроса;
  - выполнения SQL‑запросов;
  - закрытия соединения после обработки запроса.

Важно понять общую идею:
- Flask обрабатывает каждый HTTP‑запрос отдельно.
- Нам нужно, чтобы во время обработки запроса у нас было *одно* соединение
  с БД (а не создавать/закрывать его руками в каждой функции).
- Для этого Flask предоставляет объект `g` — \"глобальное\" хранилище для
  данных, живущих только в рамках одного запроса.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Optional

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    """
    Получить объект подключения к базе данных для текущего запроса.

    Как это работает:
    - `g` — это специальный объект Flask, который существует только во
      время обработки одного HTTP‑запроса.
    - Мы сохраняем соединение с БД в `g.db`, чтобы:
      - не создавать новое соединение при каждом обращении к БД внутри
        одного запроса;
      - автоматически закрыть его после завершения запроса.
    """

    if "db" not in g:
        # Создаём новое подключение к SQLite.
        # Путь к файлу базы данных мы берём из конфигурации приложения.
        db_path = current_app.config["DATABASE_PATH"]

        # Параметр check_same_thread=False позволяет использовать одно и то же
        # соединение в разных частях кода внутри одного потока (запроса).
        conn = sqlite3.connect(db_path, check_same_thread=False)

        # Указываем, что результаты запросов будут возвращаться в виде
        # "словари‑подобных" объектов, где можно обращаться к полям по имени
        # колонки (row["username"]), а не только по индексу.
        conn.row_factory = sqlite3.Row

        g.db = conn

    return g.db  # type: ignore[return-value]


def close_db(e: Optional[BaseException] = None) -> None:
    """
    Закрыть подключение к базе данных, если оно было открыто.

    Flask сам вызовет эту функцию в конце обработки запроса, если
    мы зарегистрируем её через `app.teardown_appcontext(close_db)`.
    """

    db: Optional[sqlite3.Connection] = g.pop("db", None)  # type: ignore[assignment]

    if db is not None:
        db.close()


def execute(
    query: str,
    params: Iterable[Any] | None = None,
    *,
    commit: bool = False,
) -> sqlite3.Cursor:
    """
    Удобная обёртка для выполнения SQL‑запроса.

    Параметры:
    - query: текст SQL‑запроса, например
      \"INSERT INTO users (username, password_hash) VALUES (?, ?)\".
    - params: значения для подстановки вместо знаков вопроса (?).
      Мы всегда используем параметризованные запросы, чтобы защититься
      от SQL‑инъекций.
    - commit: если True, то после выполнения запроса будет вызван
      commit() — это необходимо для запросов, изменяющих данные
      (INSERT, UPDATE, DELETE).

    Возвращаемое значение:
    - объект Cursor, через который можно получить результаты запроса
      (для SELECT) или, например, lastrowid.
    """

    if params is None:
        params = ()

    db = get_db()
    cursor = db.execute(query, tuple(params))

    if commit:
        db.commit()

    return cursor


def init_db() -> None:
    """
    Инициализация структуры базы данных.

    Эта функция:
    - создаёт файл БД (если его ещё нет);
    - создаёт все необходимые таблицы, если они ещё не существуют.

    Её можно вызывать:
    - вручную из Python‑консоли;
    - через специальную CLI‑команду Flask (мы добавим её в app.py);
    - потенциально из небольшого скрипта инициализации.
    """

    db = get_db()

    # Важно: мы используем IF NOT EXISTS, чтобы не пытаться создать
    # таблицу повторно, если она уже есть.
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            value INTEGER NOT NULL CHECK (value IN (-1, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (post_id, user_id),
            FOREIGN KEY (post_id) REFERENCES posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )

    db.commit()

