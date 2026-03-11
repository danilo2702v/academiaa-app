from __future__ import annotations

import importlib
import os
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
try:
    psycopg = importlib.import_module("psycopg")
    dict_row = importlib.import_module("psycopg.rows").dict_row
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "academia.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith(
    "postgresql://"
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-key")

WEEKDAYS = [
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
    "sabado",
    "domingo",
]
WEEKDAY_LABELS = {
    "segunda": "Segunda-feira",
    "terca": "Terca-feira",
    "quarta": "Quarta-feira",
    "quinta": "Quinta-feira",
    "sexta": "Sexta-feira",
    "sabado": "Sabado",
    "domingo": "Domingo",
}


DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError,)
if USE_POSTGRES and psycopg is not None:
    DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)


class CompatDB:
    def __init__(self, conn: Any, is_postgres: bool) -> None:
        self.conn = conn
        self.is_postgres = is_postgres

    def _sql(self, query: str) -> str:
        if not self.is_postgres:
            return query
        return query.replace("?", "%s")

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        return self.conn.execute(self._sql(query), params)

    def executemany(self, query: str, seq: list[tuple[Any, ...]]) -> Any:
        if not self.is_postgres:
            return self.conn.executemany(query, seq)
        with self.conn.cursor() as cur:
            cur.executemany(self._sql(query), seq)
            return cur

    def executescript(self, script: str) -> None:
        if not self.is_postgres:
            self.conn.executescript(script)
            return
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for stmt in statements:
            self.conn.execute(stmt)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def get_db() -> CompatDB:
    if "db" not in g:
        if USE_POSTGRES:
            if psycopg is None:
                raise RuntimeError("psycopg nao instalado para usar PostgreSQL.")
            conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
            g.db = CompatDB(conn, True)
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            g.db = CompatDB(conn, False)
    return g.db


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    if USE_POSTGRES:
        if psycopg is None:
            raise RuntimeError("psycopg nao instalado para usar PostgreSQL.")
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        db = CompatDB(raw, True)
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','user')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS workout_plans (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                weekday TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id SERIAL PRIMARY KEY,
                plan_id INTEGER NOT NULL REFERENCES workout_plans(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS workout_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                workout_date DATE NOT NULL,
                set_number INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight_kg DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS supplements (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                stock_grams DOUBLE PRECISION NOT NULL,
                dose_grams DOUBLE PRECISION NOT NULL,
                intakes_per_day INTEGER NOT NULL,
                usage_mode TEXT NOT NULL CHECK(usage_mode IN ('daily','training_days')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS supplement_usage_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                supplement_id INTEGER NOT NULL REFERENCES supplements(id) ON DELETE CASCADE,
                use_date DATE NOT NULL,
                grams_used DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, supplement_id, use_date)
            );

            CREATE TABLE IF NOT EXISTS measurements (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                body_part TEXT NOT NULL,
                value_cm DOUBLE PRECISION NOT NULL,
                measure_date DATE NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    else:
        raw = sqlite3.connect(DB_PATH)
        raw.execute("PRAGMA foreign_keys = ON")
        db = CompatDB(raw, False)
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','user')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS workout_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                weekday TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plan_id) REFERENCES workout_plans(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS workout_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                exercise_id INTEGER NOT NULL,
                workout_date TEXT NOT NULL,
                set_number INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight_kg REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS supplements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                stock_grams REAL NOT NULL,
                dose_grams REAL NOT NULL,
                intakes_per_day INTEGER NOT NULL,
                usage_mode TEXT NOT NULL CHECK(usage_mode IN ('daily','training_days')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS supplement_usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                supplement_id INTEGER NOT NULL,
                use_date TEXT NOT NULL,
                grams_used REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (supplement_id) REFERENCES supplements(id) ON DELETE CASCADE,
                UNIQUE (user_id, supplement_id, use_date)
            );

            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                body_part TEXT NOT NULL,
                value_cm REAL NOT NULL,
                measure_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )

    admin_exists = db.execute(
        "SELECT id FROM users WHERE username = ?", ("admin",)
    ).fetchone()
    if not admin_exists:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "admin"),
        )
    db.commit()
    db.close()


init_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Acesso apenas para admin.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def load_logged_user() -> None:
    g.user = None
    uid = session.get("user_id")
    if uid:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


@app.route("/")
def root():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Usuario ou senha invalidos.", "error")
            return render_template("login.html")
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    uid = session["user_id"]
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    def is_valid_iso_date(value: str) -> bool:
        if not value:
            return True
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    if not is_valid_iso_date(date_from) or not is_valid_iso_date(date_to):
        flash("Filtro de data invalido. Use o formato YYYY-MM-DD.", "error")
        return redirect(url_for("dashboard"))

    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    workout_filters = ["user_id = ?"]
    workout_params: list[Any] = [uid]
    if date_from:
        workout_filters.append("workout_date >= ?")
        workout_params.append(date_from)
    if date_to:
        workout_filters.append("workout_date <= ?")
        workout_params.append(date_to)
    workout_where_sql = " AND ".join(workout_filters)

    workouts = db.execute(
        "SELECT COUNT(*) AS total FROM workout_plans WHERE user_id = ?", (uid,)
    ).fetchone()["total"]
    logs = db.execute(
        f"SELECT COUNT(*) AS total FROM workout_logs WHERE {workout_where_sql}",
        tuple(workout_params),
    ).fetchone()["total"]
    supplements = db.execute(
        "SELECT COUNT(*) AS total FROM supplements WHERE user_id = ?", (uid,)
    ).fetchone()["total"]
    measures = db.execute(
        "SELECT COUNT(*) AS total FROM measurements WHERE user_id = ?", (uid,)
    ).fetchone()["total"]

    if USE_POSTGRES:
        year_expr = "EXTRACT(ISOYEAR FROM workout_date)::int"
        week_expr = "EXTRACT(WEEK FROM workout_date)::int"
        month_expr = "TO_CHAR(workout_date, 'YYYY-MM')"
        weekday_expr = "EXTRACT(DOW FROM workout_date)::int"
    else:
        year_expr = "strftime('%Y', workout_date)"
        week_expr = "strftime('%W', workout_date)"
        month_expr = "strftime('%Y-%m', workout_date)"
        weekday_expr = "CAST(strftime('%w', workout_date) AS INTEGER)"

    week_rows = db.execute(
        f"""
        SELECT
            {year_expr} AS year,
            {week_expr} AS week,
            COALESCE(SUM(reps * weight_kg), 0) AS volume
        FROM workout_logs
        WHERE {workout_where_sql}
        GROUP BY year, week
        ORDER BY year DESC, week DESC
        LIMIT 2
        """,
        tuple(workout_params),
    ).fetchall()

    week_workload = float(week_rows[0]["volume"]) if week_rows else 0.0
    prev_week_workload = float(week_rows[1]["volume"]) if len(week_rows) > 1 else 0.0
    week_progress = calc_progress(week_workload, prev_week_workload)
    def format_week_label(year_value: Any, week_value: Any) -> str:
        week_int = int(week_value)
        if not USE_POSTGRES:
            week_int += 1
        return f"{int(year_value)}-S{week_int:02d}"

    week_label = format_week_label(week_rows[0]["year"], week_rows[0]["week"]) if week_rows else "-"
    prev_week_label = (
        format_week_label(week_rows[1]["year"], week_rows[1]["week"])
        if len(week_rows) > 1
        else "-"
    )

    weekly_rows = db.execute(
        f"""
        SELECT
            {year_expr} AS year,
            {week_expr} AS week,
            COALESCE(SUM(reps * weight_kg), 0) AS volume
        FROM workout_logs
        WHERE {workout_where_sql}
        GROUP BY year, week
        ORDER BY year DESC, week DESC
        LIMIT 8
        """,
        tuple(workout_params),
    ).fetchall()
    weekly_rows = list(reversed(weekly_rows))
    weekly_labels = [format_week_label(r["year"], r["week"]) for r in weekly_rows]
    weekly_values = [round(float(r["volume"]), 1) for r in weekly_rows]

    monthly_rows = db.execute(
        f"""
        SELECT
            {month_expr} AS ym,
            COALESCE(SUM(reps * weight_kg), 0) AS volume
        FROM workout_logs
        WHERE {workout_where_sql}
        GROUP BY ym
        ORDER BY ym DESC
        LIMIT 6
        """,
        tuple(workout_params),
    ).fetchall()
    monthly_rows = list(reversed(monthly_rows))
    monthly_labels = [r["ym"] for r in monthly_rows]
    monthly_values = [round(float(r["volume"]), 1) for r in monthly_rows]

    weekday_rows = db.execute(
        f"""
        SELECT
            {weekday_expr} AS weekday_num,
            COUNT(*) AS logs_count
        FROM workout_logs
        WHERE {workout_where_sql}
        GROUP BY weekday_num
        """,
        tuple(workout_params),
    ).fetchall()
    weekday_counts = {int(r["weekday_num"]): int(r["logs_count"]) for r in weekday_rows}
    weekday_order = [1, 2, 3, 4, 5, 6, 0]
    weekday_chart_labels = [WEEKDAY_LABELS[WEEKDAYS[i - 1]] if i != 0 else WEEKDAY_LABELS["domingo"] for i in weekday_order]
    weekday_chart_values = [weekday_counts.get(i, 0) for i in weekday_order]

    return render_template(
        "dashboard.html",
        workouts=workouts,
        logs=logs,
        supplements=supplements,
        measures=measures,
        week_workload=round(week_workload, 1),
        week_progress=week_progress,
        week_label=week_label,
        prev_week_label=prev_week_label,
        weekly_labels=weekly_labels,
        weekly_values=weekly_values,
        monthly_labels=monthly_labels,
        monthly_values=monthly_values,
        weekday_chart_labels=weekday_chart_labels,
        weekday_chart_values=weekday_chart_values,
        date_from=date_from,
        date_to=date_to,
    )


@app.route("/admin/users", methods=["GET", "POST"])
@login_required
@admin_required
def admin_users():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        if not username or not password:
            flash("Preencha usuario e senha.", "error")
        elif role not in {"admin", "user"}:
            flash("Perfil invalido.", "error")
        else:
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), role),
                )
                db.commit()
                flash("Usuario criado com sucesso.", "success")
                return redirect(url_for("admin_users"))
            except DB_INTEGRITY_ERRORS:
                flash("Usuario ja existe.", "error")

    users = db.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    return render_template("admin_users.html", users=users)


@app.route("/treinos", methods=["GET", "POST"])
@login_required
def treinos():
    db = get_db()
    uid = session["user_id"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        weekday = request.form.get("weekday", "").strip()
        exercise_names = request.form.getlist("exercise_name")
        exercise_names = [e.strip() for e in exercise_names if e.strip()]
        if not name or weekday not in WEEKDAYS or not exercise_names:
            flash("Preencha nome, dia da semana e pelo menos um exercicio.", "error")
        else:
            if USE_POSTGRES:
                cur = db.execute(
                    "INSERT INTO workout_plans (user_id, name, weekday) VALUES (?, ?, ?) RETURNING id",
                    (uid, name, weekday),
                )
                plan_id = cur.fetchone()["id"]
            else:
                cur = db.execute(
                    "INSERT INTO workout_plans (user_id, name, weekday) VALUES (?, ?, ?)",
                    (uid, name, weekday),
                )
                plan_id = cur.lastrowid
            db.executemany(
                "INSERT INTO exercises (plan_id, name) VALUES (?, ?)",
                [(plan_id, ex) for ex in exercise_names],
            )
            db.commit()
            flash("Treino criado.", "success")
            return redirect(url_for("treinos"))

    plans = db.execute(
        """
        SELECT wp.id, wp.name, wp.weekday, COUNT(e.id) AS exercise_count
        FROM workout_plans wp
        LEFT JOIN exercises e ON e.plan_id = wp.id
        WHERE wp.user_id = ?
        GROUP BY wp.id, wp.name, wp.weekday
        ORDER BY CASE wp.weekday
            WHEN 'segunda' THEN 1
            WHEN 'terca' THEN 2
            WHEN 'quarta' THEN 3
            WHEN 'quinta' THEN 4
            WHEN 'sexta' THEN 5
            WHEN 'sabado' THEN 6
            ELSE 7 END, wp.name
        """,
        (uid,),
    ).fetchall()
    return render_template("treinos.html", plans=plans, weekday_labels=WEEKDAY_LABELS)


def calc_progress(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round(((current - previous) / previous) * 100.0, 2)


@app.route("/treinos/<int:plan_id>", methods=["GET", "POST"])
@login_required
def treino_detail(plan_id: int):
    db = get_db()
    uid = session["user_id"]
    plan = db.execute(
        "SELECT * FROM workout_plans WHERE id = ? AND user_id = ?", (plan_id, uid)
    ).fetchone()
    if not plan:
        flash("Treino nao encontrado.", "error")
        return redirect(url_for("treinos"))

    exercises = db.execute(
        "SELECT id, name FROM exercises WHERE plan_id = ? ORDER BY id", (plan_id,)
    ).fetchall()

    if request.method == "POST":
        action = request.form.get("action", "save_log")
        if action == "add_exercise":
            exercise_name = request.form.get("exercise_name", "").strip()
            selected_date = request.form.get("selected_date", date.today().isoformat())
            if not exercise_name:
                flash("Informe o nome do exercicio.", "error")
            else:
                db.execute(
                    "INSERT INTO exercises (plan_id, name) VALUES (?, ?)",
                    (plan_id, exercise_name),
                )
                db.commit()
                flash("Exercicio adicionado ao treino.", "success")
            return redirect(url_for("treino_detail", plan_id=plan_id, d=selected_date))

        exercise_id = int(request.form.get("exercise_id", "0"))
        workout_date = request.form.get("workout_date", "")
        reps_list = request.form.getlist("reps")
        weight_list = request.form.getlist("weight")

        selected = [e for e in exercises if e["id"] == exercise_id]
        if not selected:
            flash("Exercicio invalido.", "error")
            return redirect(url_for("treino_detail", plan_id=plan_id))

        valid_sets = []
        for idx, (reps, weight) in enumerate(zip(reps_list, weight_list), start=1):
            reps = reps.strip()
            weight = weight.strip()
            if not reps and not weight:
                continue
            try:
                reps_int = int(reps)
                weight_f = float(weight)
                if reps_int <= 0 or weight_f < 0:
                    raise ValueError
                valid_sets.append((uid, exercise_id, workout_date, idx, reps_int, weight_f))
            except ValueError:
                flash("Serie invalida. Use repeticoes inteiras e peso numerico.", "error")
                return redirect(url_for("treino_detail", plan_id=plan_id))

        if not workout_date or not valid_sets:
            flash("Informe data e ao menos uma serie.", "error")
            return redirect(url_for("treino_detail", plan_id=plan_id))

        db.execute(
            "DELETE FROM workout_logs WHERE user_id = ? AND exercise_id = ? AND workout_date = ?",
            (uid, exercise_id, workout_date),
        )
        db.executemany(
            """
            INSERT INTO workout_logs (user_id, exercise_id, workout_date, set_number, reps, weight_kg)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            valid_sets,
        )
        db.commit()
        flash("Registro de treino salvo.", "success")
        return redirect(url_for("treino_detail", plan_id=plan_id, d=workout_date))

    selected_date = request.args.get("d", date.today().isoformat())
    exercise_cards = []
    for ex in exercises:
        current_sets = db.execute(
            """
            SELECT set_number, reps, weight_kg
            FROM workout_logs
            WHERE user_id = ? AND exercise_id = ? AND workout_date = ?
            ORDER BY set_number
            """,
            (uid, ex["id"], selected_date),
        ).fetchall()
        previous_day = db.execute(
            """
            SELECT MAX(workout_date) AS d
            FROM workout_logs
            WHERE user_id = ? AND exercise_id = ? AND workout_date < ?
            """,
            (uid, ex["id"], selected_date),
        ).fetchone()["d"]

        previous_sets = []
        progress = None
        if previous_day:
            previous_sets = db.execute(
                """
                SELECT reps, weight_kg FROM workout_logs
                WHERE user_id = ? AND exercise_id = ? AND workout_date = ?
                """,
                (uid, ex["id"], previous_day),
            ).fetchall()
            current_load = sum(s["reps"] * s["weight_kg"] for s in current_sets)
            prev_load = sum(s["reps"] * s["weight_kg"] for s in previous_sets)
            progress = calc_progress(current_load, prev_load)

        exercise_cards.append(
            {
                "id": ex["id"],
                "name": ex["name"],
                "current_sets": current_sets,
                "previous_day": previous_day,
                "previous_sets": previous_sets,
                "progress": progress,
            }
        )

    history = db.execute(
        """
        SELECT wl.workout_date, e.name AS exercise_name, SUM(wl.reps * wl.weight_kg) AS volume
        FROM workout_logs wl
        JOIN exercises e ON e.id = wl.exercise_id
        JOIN workout_plans wp ON wp.id = e.plan_id
        WHERE wl.user_id = ? AND wp.id = ?
        GROUP BY wl.workout_date, e.name
        ORDER BY wl.workout_date DESC, e.name
        LIMIT 60
        """,
        (uid, plan_id),
    ).fetchall()

    return render_template(
        "treino_detail.html",
        plan=plan,
        weekday_labels=WEEKDAY_LABELS,
        selected_date=selected_date,
        exercise_cards=exercise_cards,
        history=history,
    )


@app.route("/suplementos", methods=["GET", "POST"])
@login_required
def suplementos():
    db = get_db()
    uid = session["user_id"]

    if request.method == "POST":
        action = request.form.get("action", "add_supplement")
        if action == "add_supplement":
            name = request.form.get("name", "").strip()
            stock_grams = request.form.get("stock_grams", "").strip()
            dose_grams = request.form.get("dose_grams", "").strip()
            intakes_per_day = request.form.get("intakes_per_day", "").strip()
            usage_mode = request.form.get("usage_mode", "daily")
            try:
                stock_f = float(stock_grams)
                dose_f = float(dose_grams)
                intakes_i = int(intakes_per_day)
                if stock_f <= 0 or dose_f <= 0 or intakes_i <= 0:
                    raise ValueError
                if usage_mode not in {"daily", "training_days"}:
                    raise ValueError
                db.execute(
                    """
                    INSERT INTO supplements (user_id, name, stock_grams, dose_grams, intakes_per_day, usage_mode)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (uid, name, stock_f, dose_f, intakes_i, usage_mode),
                )
                db.commit()
                flash("Suplemento salvo.", "success")
                return redirect(url_for("suplementos"))
            except ValueError:
                flash("Valores invalidos no cadastro de suplemento.", "error")
        elif action == "log_usage":
            supplement_id = request.form.get("supplement_id", "").strip()
            use_date = request.form.get("use_date", "").strip()
            grams_used = request.form.get("grams_used", "").strip()
            try:
                supplement_id_i = int(supplement_id)
                grams_used_f = float(grams_used)
                datetime.strptime(use_date, "%Y-%m-%d")
                if grams_used_f < 0:
                    raise ValueError

                supplement = db.execute(
                    "SELECT id FROM supplements WHERE id = ? AND user_id = ?",
                    (supplement_id_i, uid),
                ).fetchone()
                if not supplement:
                    flash("Suplemento invalido para lancamento.", "error")
                    return redirect(url_for("suplementos"))

                db.execute(
                    """
                    INSERT INTO supplement_usage_logs (user_id, supplement_id, use_date, grams_used)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, supplement_id, use_date)
                    DO UPDATE SET grams_used = excluded.grams_used, created_at = CURRENT_TIMESTAMP
                    """,
                    (uid, supplement_id_i, use_date, grams_used_f),
                )
                db.commit()
                flash("Uso diario registrado.", "success")
                return redirect(url_for("suplementos"))
            except ValueError:
                flash("Lancamento invalido. Informe data valida e gramas >= 0.", "error")

    training_days_count = db.execute(
        "SELECT COUNT(DISTINCT weekday) AS c FROM workout_plans WHERE user_id = ?", (uid,)
    ).fetchone()["c"]
    training_days_count = max(1, int(training_days_count))
    today_weekday = WEEKDAYS[date.today().weekday()]
    has_training_today = (
        db.execute(
            "SELECT 1 FROM workout_plans WHERE user_id = ? AND weekday = ? LIMIT 1",
            (uid, today_weekday),
        ).fetchone()
        is not None
    )

    rows = db.execute(
        """
        SELECT id, name, stock_grams, dose_grams, intakes_per_day, usage_mode
        FROM supplements
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (uid,),
    ).fetchall()

    usage_totals = db.execute(
        """
        SELECT supplement_id, COALESCE(SUM(grams_used), 0) AS total_used
        FROM supplement_usage_logs
        WHERE user_id = ?
        GROUP BY supplement_id
        """,
        (uid,),
    ).fetchall()
    usage_totals_map = {int(r["supplement_id"]): float(r["total_used"]) for r in usage_totals}

    today_str = date.today().isoformat()
    today_usage_rows = db.execute(
        """
        SELECT supplement_id, grams_used
        FROM supplement_usage_logs
        WHERE user_id = ? AND use_date = ?
        """,
        (uid, today_str),
    ).fetchall()
    today_usage_map = {int(r["supplement_id"]): float(r["grams_used"]) for r in today_usage_rows}

    recent_usage = db.execute(
        """
        SELECT sul.use_date, s.name AS supplement_name, sul.grams_used
        FROM supplement_usage_logs sul
        JOIN supplements s ON s.id = sul.supplement_id
        WHERE sul.user_id = ?
        ORDER BY sul.use_date DESC, sul.created_at DESC
        LIMIT 40
        """,
        (uid,),
    ).fetchall()

    supplements_view = []
    for s in rows:
        grams_per_day = s["dose_grams"] * s["intakes_per_day"]
        usage_days_per_week = 7 if s["usage_mode"] == "daily" else training_days_count
        expected_today = (
            grams_per_day if s["usage_mode"] == "daily" or has_training_today else 0.0
        )
        grams_per_calendar_day = grams_per_day * (usage_days_per_week / 7.0)
        total_used = usage_totals_map.get(int(s["id"]), 0.0)
        remaining_real = max(float(s["stock_grams"]) - total_used, 0.0)
        days_left = remaining_real / grams_per_calendar_day if grams_per_calendar_day > 0 else 0
        remind_today = s["usage_mode"] == "daily" or has_training_today
        used_today = today_usage_map.get(int(s["id"]), 0.0)
        today_diff = round(used_today - expected_today, 2)
        supplements_view.append(
            {
                **dict(s),
                "grams_per_day": round(grams_per_day, 2),
                "expected_today": round(expected_today, 2),
                "used_today": round(used_today, 2),
                "today_diff": today_diff,
                "total_used": round(total_used, 2),
                "remaining_real": round(remaining_real, 2),
                "days_left": round(days_left, 1),
                "low_stock": days_left <= 7,
                "remind_today": remind_today,
            }
        )
    return render_template(
        "suplementos.html",
        supplements=supplements_view,
        has_training_today=has_training_today,
        weekday_label=WEEKDAY_LABELS[today_weekday],
        today_str=today_str,
        recent_usage=recent_usage,
    )


@app.route("/medidas", methods=["GET", "POST"])
@login_required
def medidas():
    db = get_db()
    uid = session["user_id"]

    if request.method == "POST":
        body_part = request.form.get("body_part", "").strip()
        value_cm = request.form.get("value_cm", "").strip()
        measure_date = request.form.get("measure_date", "").strip()
        try:
            value_f = float(value_cm)
            if value_f <= 0 or not body_part or not measure_date:
                raise ValueError
            db.execute(
                """
                INSERT INTO measurements (user_id, body_part, value_cm, measure_date)
                VALUES (?, ?, ?, ?)
                """,
                (uid, body_part, value_f, measure_date),
            )
            db.commit()
            flash("Medida registrada.", "success")
            return redirect(url_for("medidas"))
        except ValueError:
            flash("Dados invalidos para medida.", "error")

    rows = db.execute(
        """
        SELECT body_part, measure_date, value_cm
        FROM measurements
        WHERE user_id = ?
        ORDER BY body_part, measure_date DESC
        """,
        (uid,),
    ).fetchall()
    by_part: dict[str, list[Any]] = {}
    for r in rows:
        by_part.setdefault(r["body_part"], []).append(r)

    comparison = []
    for part, items in by_part.items():
        latest = items[0]
        previous = items[1] if len(items) > 1 else None
        delta = None
        pct = None
        if previous:
            delta = round(latest["value_cm"] - previous["value_cm"], 2)
            if previous["value_cm"] > 0:
                pct = round((delta / previous["value_cm"]) * 100.0, 2)
        comparison.append(
            {
                "part": part,
                "latest_date": latest["measure_date"],
                "latest_value": latest["value_cm"],
                "previous_date": previous["measure_date"] if previous else None,
                "previous_value": previous["value_cm"] if previous else None,
                "delta": delta,
                "pct": pct,
            }
        )
    comparison.sort(key=lambda x: x["part"].lower())

    recent = db.execute(
        """
        SELECT body_part, value_cm, measure_date
        FROM measurements
        WHERE user_id = ?
        ORDER BY measure_date DESC, body_part
        LIMIT 80
        """,
        (uid,),
    ).fetchall()
    return render_template("medidas.html", comparison=comparison, recent=recent)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
