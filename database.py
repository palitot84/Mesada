"""Camada de acesso ao banco de dados (PostgreSQL/Neon)."""
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# Usuários iniciais (senhas armazenadas em texto simples, por decisão do administrador).
INITIAL_USERS = [
    ("aabp", "admin", "aabp1301"),
    ("bonitao", "responsavel", "alicedede"),
    ("daniela", "responsavel", "jose"),
]
ROLES = ("admin", "responsavel")
TX_TYPES = ("credito", "debito")
DEFAULT_CATEGORY = "Outros"
# Categorias que existiam fixas no código; migradas apenas para a família Tavares Palitot.
LEGACY_FAMILY_PATTERN = "%Tavares Palitot%"
LEGACY_DEBIT_CATEGORIES = [
    ("Falar palavrão", 2.00),
    ("Bater em papai e mamãe", 10.00),
    ("Arrastar meia no chão", 5.00),
    ("Perturbar o irmão", 2.00),
    ("Bater no irmão", 5.00),
    ("Não se comportar", 1.00),
]
ADMIN_USERNAME = "aabp"


@st.cache_resource
def get_engine() -> Engine:
    database_url = st.secrets["database_url"]
    # força o driver psycopg2, já que o sqlalchemy 2.x usa psycopg (v3) por padrão
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(database_url, pool_pre_ping=True)


def init_db() -> None:
    """Cria as tabelas necessárias caso ainda não existam."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'responsavel'))
            )
        """))
        # Migração da versão anterior, que guardava hash em "password_hash".
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password TEXT"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS password_hash"))
        for username, role, password in INITIAL_USERS:
            conn.execute(
                text("""
                    INSERT INTO users (username, password, role)
                    VALUES (:username, :password, :role)
                    ON CONFLICT (username) DO UPDATE SET password = COALESCE(users.password, EXCLUDED.password)
                """),
                {"username": username, "password": password, "role": role},
            )
        conn.execute(text("ALTER TABLE users ALTER COLUMN password SET NOT NULL"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS families (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS children (
                id SERIAL PRIMARY KEY,
                family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                birth_date DATE NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
                type TEXT NOT NULL CHECK (type IN ('credito', 'debito')),
                value NUMERIC(10, 2) NOT NULL CHECK (value > 0),
                transaction_date DATE NOT NULL,
                reason TEXT NOT NULL
            )
        """))
        conn.execute(text(
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
        ))
        # Famílias criadas antes do controle de acesso passam a pertencer ao administrador.
        conn.execute(
            text("UPDATE families SET owner_id = (SELECT id FROM users WHERE username = :admin) WHERE owner_id IS NULL"),
            {"admin": ADMIN_USERNAME},
        )
        # O nome da família passa a ser único por responsável, e não globalmente.
        conn.execute(text("ALTER TABLE families DROP CONSTRAINT IF EXISTS families_name_key"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS families_owner_name_idx ON families (owner_id, name)"))

        categories_existed = conn.execute(text("SELECT to_regclass('categories') IS NOT NULL")).scalar()
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('credito', 'debito')),
                value NUMERIC(10, 2) CHECK (value > 0),
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                UNIQUE (family_id, type, name),
                CHECK (is_default OR value IS NOT NULL)
            )
        """))
        _ensure_default_categories(conn)
        if not categories_existed:
            for name, value in LEGACY_DEBIT_CATEGORIES:
                conn.execute(
                    text("""
                        INSERT INTO categories (family_id, name, type, value)
                        SELECT id, :name, 'debito', :value FROM families WHERE name ILIKE :pattern
                        ON CONFLICT DO NOTHING
                    """),
                    {"name": name, "value": value, "pattern": LEGACY_FAMILY_PATTERN},
                )


def _ensure_default_categories(conn, family_id: int | None = None) -> None:
    """Garante a categoria padrão "Outros" (crédito e débito) na família informada ou em todas."""
    conn.execute(
        text("""
            INSERT INTO categories (family_id, name, type, value, is_default)
            SELECT f.id, :name, t.type, NULL, TRUE
            FROM families f CROSS JOIN (VALUES ('credito'), ('debito')) AS t(type)
            WHERE (CAST(:family_id AS INTEGER) IS NULL OR f.id = :family_id)
            ON CONFLICT (family_id, type, name) DO NOTHING
        """),
        {"name": DEFAULT_CATEGORY, "family_id": family_id},
    )


# ---------- Usuários / autenticação ----------

def authenticate(username: str, password: str) -> dict | None:
    """Retorna {id, username, role} se as credenciais forem válidas, senão None."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, role FROM users WHERE username = :username AND password = :password"),
            {"username": username, "password": password},
        ).mappings().first()
    return dict(row) if row else None


def get_user(user_id: int) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, role FROM users WHERE id = :user_id"), {"user_id": user_id}
        ).mappings().first()
    return dict(row) if row else None


def get_users() -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT u.id, u.username, u.role, COUNT(f.id) AS families
        FROM users u
        LEFT JOIN families f ON f.owner_id = u.id
        GROUP BY u.id, u.username, u.role
        ORDER BY u.username
    """
    return pd.read_sql(text(query), engine)


def add_user(username: str, password: str, role: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (username, password, role) VALUES (:username, :password, :role)"),
            {"username": username, "password": password, "role": role},
        )


def update_user(user_id: int, username: str, role: str, password: str | None = None) -> None:
    """Atualiza login e perfil; a senha só é trocada se informada."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE users
                SET username = :username, role = :role, password = COALESCE(:password, password)
                WHERE id = :user_id
            """),
            {"user_id": user_id, "username": username, "role": role, "password": password},
        )
        _check_rowcount(result)


def delete_user(user_id: int) -> None:
    """Remove o usuário e, em cascata, suas famílias, crianças e transações."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
        _check_rowcount(result)


# ---------- Famílias ----------

def add_family(owner_id: int, name: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        family_id = conn.execute(
            text("INSERT INTO families (name, owner_id) VALUES (:name, :owner_id) RETURNING id"),
            {"name": name, "owner_id": owner_id},
        ).scalar_one()
        _ensure_default_categories(conn, family_id)


def get_families(owner_id: int) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(
        text("SELECT id, name FROM families WHERE owner_id = :owner_id ORDER BY name"),
        engine,
        params={"owner_id": owner_id},
    )


def _check_rowcount(result) -> None:
    if result.rowcount == 0:
        raise PermissionError("Registro não encontrado ou sem permissão de acesso.")


def update_family(owner_id: int, family_id: int, name: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE families SET name = :name WHERE id = :family_id AND owner_id = :owner_id"),
            {"name": name, "family_id": family_id, "owner_id": owner_id},
        )
        _check_rowcount(result)


def delete_family(owner_id: int, family_id: int) -> None:
    """Remove a família e, em cascata, suas crianças e transações."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM families WHERE id = :family_id AND owner_id = :owner_id"),
            {"family_id": family_id, "owner_id": owner_id},
        )
        _check_rowcount(result)


# ---------- Crianças ----------

def add_child(owner_id: int, family_id: int, name: str, birth_date: date) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO children (family_id, name, birth_date)
                SELECT f.id, :name, :birth_date FROM families f
                WHERE f.id = :family_id AND f.owner_id = :owner_id
            """),
            {"family_id": family_id, "name": name, "birth_date": birth_date, "owner_id": owner_id},
        )
        _check_rowcount(result)


def get_children(owner_id: int, family_id: int | None = None) -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT c.id, c.name, c.birth_date, c.family_id, f.name AS family_name
        FROM children c
        JOIN families f ON f.id = c.family_id
        WHERE f.owner_id = :owner_id
    """
    params = {"owner_id": owner_id}
    if family_id is not None:
        query += " AND c.family_id = :family_id"
        params["family_id"] = family_id
    query += " ORDER BY f.name, c.name"
    return pd.read_sql(text(query), engine, params=params)


def update_child(owner_id: int, child_id: int, family_id: int, name: str, birth_date: date) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE children c
                SET family_id = :family_id, name = :name, birth_date = :birth_date
                FROM families cur, families dest
                WHERE c.id = :child_id
                  AND cur.id = c.family_id AND cur.owner_id = :owner_id
                  AND dest.id = :family_id AND dest.owner_id = :owner_id
            """),
            {"family_id": family_id, "name": name, "birth_date": birth_date, "child_id": child_id, "owner_id": owner_id},
        )
        _check_rowcount(result)


def delete_child(owner_id: int, child_id: int) -> None:
    """Remove a criança e, em cascata, suas transações."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM children c USING families f
                WHERE c.id = :child_id AND f.id = c.family_id AND f.owner_id = :owner_id
            """),
            {"child_id": child_id, "owner_id": owner_id},
        )
        _check_rowcount(result)


# ---------- Categorias ----------

def get_categories(owner_id: int, family_id: int | None = None, tx_type: str | None = None) -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT c.id, c.name, c.type, c.value, c.is_default, c.family_id, f.name AS family_name
        FROM categories c
        JOIN families f ON f.id = c.family_id
        WHERE f.owner_id = :owner_id
    """
    params = {"owner_id": owner_id}
    if family_id is not None:
        query += " AND c.family_id = :family_id"
        params["family_id"] = family_id
    if tx_type is not None:
        query += " AND c.type = :tx_type"
        params["tx_type"] = tx_type
    # "Outros" sempre por último na lista.
    query += " ORDER BY f.name, c.type, c.is_default, c.name"
    return pd.read_sql(text(query), engine, params=params)


def add_category(owner_id: int, family_id: int, name: str, tx_type: str, value: float) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO categories (family_id, name, type, value)
                SELECT f.id, :name, :tx_type, :value FROM families f
                WHERE f.id = :family_id AND f.owner_id = :owner_id
            """),
            {"family_id": family_id, "name": name, "tx_type": tx_type, "value": value, "owner_id": owner_id},
        )
        _check_rowcount(result)


def update_category(owner_id: int, category_id: int, family_id: int, name: str, tx_type: str, value: float) -> None:
    """Atualiza uma categoria criada pelo usuário (a categoria padrão "Outros" não pode ser alterada)."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE categories c
                SET family_id = :family_id, name = :name, type = :tx_type, value = :value
                FROM families cur, families dest
                WHERE c.id = :category_id AND NOT c.is_default
                  AND cur.id = c.family_id AND cur.owner_id = :owner_id
                  AND dest.id = :family_id AND dest.owner_id = :owner_id
            """),
            {"category_id": category_id, "family_id": family_id, "name": name, "tx_type": tx_type,
             "value": value, "owner_id": owner_id},
        )
        _check_rowcount(result)


def delete_category(owner_id: int, category_id: int) -> None:
    """Remove uma categoria criada pelo usuário; os lançamentos já feitos são mantidos."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM categories c USING families f
                WHERE c.id = :category_id AND NOT c.is_default
                  AND f.id = c.family_id AND f.owner_id = :owner_id
            """),
            {"category_id": category_id, "owner_id": owner_id},
        )
        _check_rowcount(result)


# ---------- Transações (crédito/débito) ----------

def add_transaction(owner_id: int, child_id: int, tx_type: str, value: float, tx_date: date, reason: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO transactions (child_id, type, value, transaction_date, reason)
                SELECT c.id, :tx_type, :value, :tx_date, :reason
                FROM children c JOIN families f ON f.id = c.family_id
                WHERE c.id = :child_id AND f.owner_id = :owner_id
            """),
            {"child_id": child_id, "tx_type": tx_type, "value": value, "tx_date": tx_date,
             "reason": reason, "owner_id": owner_id},
        )
        _check_rowcount(result)


def get_transactions(owner_id: int, child_id: int | None = None) -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT t.id, t.type, t.value, t.transaction_date, t.reason, c.name AS child_name, f.name AS family_name
        FROM transactions t
        JOIN children c ON c.id = t.child_id
        JOIN families f ON f.id = c.family_id
        WHERE f.owner_id = :owner_id
    """
    params = {"owner_id": owner_id}
    if child_id is not None:
        query += " AND t.child_id = :child_id"
        params["child_id"] = child_id
    query += " ORDER BY t.transaction_date DESC, t.id DESC"
    return pd.read_sql(text(query), engine, params=params)


def get_balances(owner_id: int) -> pd.DataFrame:
    """Retorna o saldo atual de cada criança (créditos - débitos)."""
    engine = get_engine()
    query = """
        SELECT
            c.id AS child_id,
            c.name AS child_name,
            f.name AS family_name,
            COALESCE(SUM(CASE WHEN t.type = 'credito' THEN t.value ELSE 0 END), 0)
                - COALESCE(SUM(CASE WHEN t.type = 'debito' THEN t.value ELSE 0 END), 0) AS balance
        FROM children c
        JOIN families f ON f.id = c.family_id
        LEFT JOIN transactions t ON t.child_id = c.id
        WHERE f.owner_id = :owner_id
        GROUP BY c.id, c.name, f.name
        ORDER BY f.name, c.name
    """
    return pd.read_sql(text(query), engine, params={"owner_id": owner_id})
