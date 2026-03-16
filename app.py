"""
app.py
------
Главная точка входа в приложение CREDDIT.

Здесь мы:
- создаём объект Flask-приложения;
- настраиваем конфигурацию (секретный ключ, путь к БД и т.п.);
- определяем основные маршруты (routes) — URL-адреса, на которые
  может заходить пользователь;
- связываем Python-код с HTML-шаблонами (Jinja2);
- подключаем работу с базой данных (SQLite) и CLI-команды;
- реализуем базовую аутентификацию (регистрация, вход, выход).

Структура файла:
- функция create_app() — точка сборки приложения;
- регистрация CLI-команды init-db;
- описание маршрутов:
  - главная страница (список постов — позже);
  - регистрация /register;
  - вход /login;
  - выход /logout.
"""

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import config
from db import close_db, execute, init_db


def create_app() -> Flask:
    """
    Функция-фабрика приложения.

    Почему мы выносим создание приложения в отдельную функцию, а не пишем
    просто `app = Flask(__name__)` на уровне модуля?

    - Так проще тестировать приложение (можно создавать несколько
      независимых экземпляров с разной конфигурацией).
    - Так принято во многих примерах и реальных проектах Flask, и
      полезно привыкнуть к этому шаблону.
    """

    app = Flask(__name__)

    # Подключаем конфигурацию из файла config.py.
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DATABASE_PATH"] = config.DATABASE_PATH

    # === Подключение обработки базы данных ===
    # Регистрируем функцию close_db, чтобы Flask вызывал её автоматически
    # после каждого запроса и закрывал соединение с БД, если оно было
    # открыто.
    app.teardown_appcontext(close_db)

    # === CLI-команда для инициализации базы данных ===
    # Flask позволяет добавлять собственные команды для терминала.
    # После регистрации этой функции мы сможем выполнить:
    #
    #   flask --app app.py init-db
    #
    # и база данных будет создана/обновлена.

    @app.cli.command("init-db")
    def init_db_command() -> None:  # pragma: no cover - CLI команда
        """
        Инициализировать базу данных.

        Команда создаёт все таблицы, если они ещё не существуют.
        Это удобный способ один раз подготовить БД перед запуском
        приложения.
        """

        init_db()
        print("База данных инициализирована.")

    @app.route("/")
    def index():
        """
        Главная страница CREDDIT.

        Теперь это настоящая лента постов:
        - мы запрашиваем список постов из таблицы posts;
        - одновременно достаём имя автора из таблицы users через JOIN;
        - сортируем по дате создания (новые сверху).
        """
        posts = execute(
            """
            SELECT
              posts.id,
              posts.title,
              posts.content,
              posts.created_at,
              users.username,
              COALESCE(SUM(votes.value), 0) AS score
            FROM posts
            JOIN users ON users.id = posts.user_id
            LEFT JOIN votes ON votes.post_id = posts.id
            GROUP BY posts.id
            ORDER BY posts.created_at DESC
            """
        ).fetchall()

        return render_template("index.html", posts=posts)

    # === АУТЕНТИФИКАЦИЯ (регистрация, вход, выход) ===

    @app.route("/register", methods=["GET", "POST"])
    def register():
        """
        Страница регистрации нового пользователя.

        - При GET-запросе просто показываем HTML-форму.
        - При POST-запросе:
          - забираем данные из формы (username и password);
          - проверяем, что имя не пустое и пароль достаточно длинный;
          - проверяем, что такого пользователя ещё нет в БД;
          - сохраняем в таблицу users хэшированный пароль;
          - перенаправляем пользователя на страницу входа.

        Важно: мы НИКОГДА не храним пароль в открытом виде — только
        безопасный хэш с помощью функций из werkzeug.security.
        """

        error: str | None = None

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            # Базовые проверки на стороне сервера (даже если в HTML уже
            # есть атрибуты required, minlength и т.п., мы не можем
            # полагаться только на них).
            if not username:
                error = "Имя пользователя не может быть пустым."
            elif not password or len(password) < 6:
                error = "Пароль должен содержать минимум 6 символов."
            else:
                # Проверяем, не занят ли уже такой username.
                existing = execute(
                    "SELECT id FROM users WHERE username = ?",
                    (username,),
                ).fetchone()

                if existing is not None:
                    error = "Пользователь с таким именем уже существует."
                else:
                    password_hash = generate_password_hash(password)
                    execute(
                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (username, password_hash),
                        commit=True,
                    )
                    # После успешной регистрации перенаправляем на страницу входа.
                    return redirect(url_for("login"))

        return render_template("register.html", error=error)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """
        Страница входа (логина) пользователя.

        Логика:
        - При GET-запросе показываем форму.
        - При POST-запросе:
          - находим пользователя по имени;
          - сравниваем хэш пароля с помощью check_password_hash;
          - если всё ок, сохраняем информацию о пользователе в сессии.

        Что такое сессия во Flask?
        - Это способ \"запомнить\" пользователя между запросами.
        - Flask хранит небольшой зашифрованный словарь в cookie браузера.
        - Мы можем записать туда user_id и username, чтобы в других
          маршрутах понимать, какой пользователь залогинен.
        """

        error: str | None = None

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()

            if user is None:
                error = "Пользователь с таким именем не найден."
            elif not check_password_hash(user["password_hash"], password):
                error = "Неверный пароль."
            else:
                # Сбрасываем сессию и записываем туда идентификатор и имя.
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                # После входа отправляем пользователя на главную.
                return redirect(url_for("index"))

        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        """
        Выход пользователя из системы.

        Реализуется очень просто:
        - очищаем сессию (session.clear());
        - перенаправляем на главную страницу.
        """

        session.clear()
        return redirect(url_for("index"))

    # === ПОСТЫ (создание и просмотр) ===

    @app.route("/post/create", methods=["GET", "POST"])
    def create_post():
        """
        Создание нового поста.

        Доступно только авторизованным пользователям:
        - если в сессии нет user_id, перенаправляем на страницу входа;
        - если метод GET — показываем форму;
        - если метод POST — валидируем данные и сохраняем пост.
        """

        if not session.get("user_id"):
            # Пользователь не залогинен — отправляем его на страницу входа.
            return redirect(url_for("login"))

        error: str | None = None

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()

            if not title:
                error = "Заголовок не может быть пустым."
            elif not content:
                error = "Текст поста не может быть пустым."
            else:
                execute(
                    "INSERT INTO posts (user_id, title, content) VALUES (?, ?, ?)",
                    (session["user_id"], title, content),
                    commit=True,
                )
                return redirect(url_for("index"))

        return render_template("create_post.html", error=error)

    @app.route("/post/<int:post_id>")
    def post_detail(post_id: int):
        """
        Детальный просмотр одного поста.

        Здесь мы получаем:
        - сам пост;
        - имя автора;
        - список комментариев к посту (с именами авторов).
        Позже добавим сюда ещё и рейтинг (голоса).
        """

        post = execute(
            """
            SELECT
              posts.id,
              posts.title,
              posts.content,
              posts.created_at,
              users.username,
              COALESCE(SUM(votes.value), 0) AS score
            FROM posts
            JOIN users ON users.id = posts.user_id
            LEFT JOIN votes ON votes.post_id = posts.id
            WHERE posts.id = ?
            GROUP BY posts.id
            """,
            (post_id,),
        ).fetchone()

        if post is None:
            # Для простоты вернём стандартную 404-страницу Flask.
            # В реальном приложении можно сделать свой красивый шаблон.
            return "Пост не найден", 404

        comments = execute(
            """
            SELECT
              comments.id,
              comments.content,
              comments.created_at,
              users.username
            FROM comments
            JOIN users ON users.id = comments.user_id
            WHERE comments.post_id = ?
            ORDER BY comments.created_at ASC
            """,
            (post_id,),
        ).fetchall()

        # Обратите внимание: мы пока не передаём переменную error.
        # Она появится, когда мы добавим обработчик POST-запроса для
        # добавления комментария.
        return render_template(
            "post_detail.html",
            post=post,
            comments=comments,
            error=None,
        )

    @app.route("/post/<int:post_id>/vote", methods=["POST"])
    def vote(post_id: int):
        """
        Обработчик голосования за пост.

        Ожидает JSON-тело вида {"value": 1} или {"value": -1}.
        Логика:
        - пользователь должен быть залогинен;
        - value может быть только 1 (лайк) или -1 (дизлайк);
        - если пользователь уже голосовал за этот пост:
          - при повторном голосе с тем же значением — ничего не меняем;
          - при голосе с противоположным значением — обновляем запись;
        - если голосует впервые — создаём новую запись в votes.

        В ответ возвращаем JSON с новым значением рейтинга.
        """

        from flask import jsonify

        if not session.get("user_id"):
            return jsonify({"ok": False, "error": "auth_required"}), 401

        data = request.get_json(silent=True) or {}
        value = data.get("value")

        if value not in (-1, 1):
            return jsonify({"ok": False, "error": "invalid_value"}), 400

        existing = execute(
            "SELECT id, value FROM votes WHERE post_id = ? AND user_id = ?",
            (post_id, session["user_id"]),
        ).fetchone()

        if existing is None:
            # Первый голос этого пользователя за пост.
            execute(
                "INSERT INTO votes (post_id, user_id, value) VALUES (?, ?, ?)",
                (post_id, session["user_id"], value),
                commit=True,
            )
        elif existing["value"] != value:
            # Пользователь меняет мнение: обновляем значение голоса.
            execute(
                "UPDATE votes SET value = ? WHERE id = ?",
                (value, existing["id"]),
                commit=True,
            )
        # Если existing["value"] == value, ничего не делаем — повторный
        # одинаковый голос не должен менять рейтинг.

        # Пересчитываем текущий рейтинг поста.
        row = execute(
            "SELECT COALESCE(SUM(value), 0) AS score FROM votes WHERE post_id = ?",
            (post_id,),
        ).fetchone()

        return jsonify({"ok": True, "score": row["score"]})

    @app.route("/post/<int:post_id>/comment", methods=["POST"])
    def add_comment(post_id: int):
        """
        Обработчик добавления нового комментария к посту.

        - Требует, чтобы пользователь был авторизован.
        - Получает текст комментария из формы.
        - Проверяет, что текст не пустой.
        - Сохраняет комментарий в таблицу comments.
        - После этого перенаправляет пользователя обратно к посту.
        """

        if not session.get("user_id"):
            # Если пользователь не залогинен, сначала отправляем его
            # на страницу входа.
            return redirect(url_for("login"))

        content = request.form.get("content", "").strip()

        if not content:
            # Если комментарий пустой, мы могли бы показать ошибку.
            # Для простоты сейчас просто возвращаем пользователя к
            # странице поста. Можно улучшить это поведение позже.
            return redirect(url_for("post_detail", post_id=post_id))

        execute(
            "INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)",
            (post_id, session["user_id"], content),
            commit=True,
        )

        return redirect(url_for("post_detail", post_id=post_id))

    return app


if __name__ == "__main__":
    # Этот блок выполняется только когда мы запускаем файл напрямую:
    # python app.py
    #
    # В режиме разработки удобно включить debug=True:
    # - сервер автоматически перезапускается при изменении кода;
    # - при возникновении ошибки мы видим подробный отладочный экран.
    app = create_app()
    app.run(debug=True)

