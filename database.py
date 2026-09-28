"""Camada de acesso ao banco de dados (PostgreSQL/Neon)."""
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


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


# ---------- Famílias ----------

def add_family(name: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO families (name) VALUES (:name)"), {"name": name})


def get_families() -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(text("SELECT id, name FROM families ORDER BY name"), engine)


def update_family(family_id: int, name: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE families SET name = :name WHERE id = :family_id"), {"name": name, "family_id": family_id})


def delete_family(family_id: int) -> None:
    """Remove a família e, em cascata, suas crianças e transações."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM families WHERE id = :family_id"), {"family_id": family_id})


# ---------- Crianças ----------

def add_child(family_id: int, name: str, birth_date: date) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO children (family_id, name, birth_date) VALUES (:family_id, :name, :birth_date)"),
            {"family_id": family_id, "name": name, "birth_date": birth_date},
        )


def get_children(family_id: int | None = None) -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT c.id, c.name, c.birth_date, c.family_id, f.name AS family_name
        FROM children c
        JOIN families f ON f.id = c.family_id
    """
    params = {}
    if family_id is not None:
        query += " WHERE c.family_id = :family_id"
        params["family_id"] = family_id
    query += " ORDER BY f.name, c.name"
    return pd.read_sql(text(query), engine, params=params)


def update_child(child_id: int, family_id: int, name: str, birth_date: date) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE children
                SET family_id = :family_id, name = :name, birth_date = :birth_date
                WHERE id = :child_id
            """),
            {"family_id": family_id, "name": name, "birth_date": birth_date, "child_id": child_id},
        )


def delete_child(child_id: int) -> None:
    """Remove a criança e, em cascata, suas transações."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM children WHERE id = :child_id"), {"child_id": child_id})


# ---------- Transações (crédito/débito) ----------

def add_transaction(child_id: int, tx_type: str, value: float, tx_date: date, reason: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO transactions (child_id, type, value, transaction_date, reason)
                VALUES (:child_id, :tx_type, :value, :tx_date, :reason)
            """),
            {"child_id": child_id, "tx_type": tx_type, "value": value, "tx_date": tx_date, "reason": reason},
        )


def get_transactions(child_id: int | None = None) -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT t.id, t.type, t.value, t.transaction_date, t.reason, c.name AS child_name, f.name AS family_name
        FROM transactions t
        JOIN children c ON c.id = t.child_id
        JOIN families f ON f.id = c.family_id
    """
    params = {}
    if child_id is not None:
        query += " WHERE t.child_id = :child_id"
        params["child_id"] = child_id
    query += " ORDER BY t.transaction_date DESC, t.id DESC"
    return pd.read_sql(text(query), engine, params=params)


def get_balances() -> pd.DataFrame:
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
        GROUP BY c.id, c.name, f.name
        ORDER BY f.name, c.name
    """
    return pd.read_sql(text(query), engine)
