"""Aplicativo Streamlit de controle de mesada."""
from datetime import date

import pandas as pd
import streamlit as st

import database as db

st.set_page_config(page_title="Controle de Mesada", page_icon="💰", layout="centered")

db.init_db()

MENU_OPTIONS = [
    "Gestão de Famílias",
    "Gestão de Crianças",
    "Crédito de Mesada",
    "Débito de Mesada",
    "Extrato e Saldos",
]

st.sidebar.title("💰 Menu")
choice = st.sidebar.radio("Navegação", MENU_OPTIONS)

OUTROS_CATEGORY = "Outros"
DEBIT_CATEGORIES = {
    "Falar palavrão": 2.00,
    "Bater em papai e mamãe": 10.00,
    "Arrastar meia no chão": 5.00,
    "Perturbar o irmão": 2.00,
    "Bater no irmão": 5.00,
    "Não se comportar" : 1.00,
    OUTROS_CATEGORY: None,
}


def select_family() -> int | None:
    families = db.get_families()
    if families.empty:
        st.warning("Nenhuma família cadastrada ainda. Cadastre uma família primeiro.")
        return None
    options = dict(zip(families["name"], families["id"]))
    chosen_name = st.selectbox("Família", options.keys())
    return options[chosen_name]


def select_child(family_id: int) -> int | None:
    children = db.get_children(family_id)
    if children.empty:
        st.warning("Esta família ainda não possui crianças cadastradas.")
        return None
    options = dict(zip(children["name"], children["id"]))
    chosen_name = st.selectbox("Criança", options.keys())
    return options[chosen_name]


if choice == "Gestão de Famílias":
    st.header("👨‍👩‍👧 Gestão de Famílias")
    tab_criar, tab_alterar, tab_remover = st.tabs(["Criar", "Alterar", "Remover"])

    with tab_criar:
        with st.form("form_familia_criar"):
            family_name = st.text_input("Nome da família")
            submitted = st.form_submit_button("Cadastrar")
            if submitted:
                if not family_name.strip():
                    st.error("Informe o nome da família.")
                else:
                    try:
                        db.add_family(family_name.strip())
                        st.success(f"Família '{family_name}' cadastrada com sucesso!")
                    except Exception as exc:
                        st.error(f"Erro ao cadastrar família: {exc}")

    with tab_alterar:
        families = db.get_families()
        if families.empty:
            st.warning("Nenhuma família cadastrada ainda.")
        else:
            options = dict(zip(families["name"], families["id"]))
            chosen_name = st.selectbox("Família", options.keys(), key="alterar_familia_select")
            family_id = options[chosen_name]
            with st.form("form_familia_alterar"):
                new_name = st.text_input("Novo nome da família", value=chosen_name)
                submitted = st.form_submit_button("Salvar alterações")
                if submitted:
                    if not new_name.strip():
                        st.error("Informe o nome da família.")
                    else:
                        try:
                            db.update_family(family_id, new_name.strip())
                            st.success("Família atualizada com sucesso!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro ao atualizar família: {exc}")

    with tab_remover:
        families = db.get_families()
        if families.empty:
            st.warning("Nenhuma família cadastrada ainda.")
        else:
            options = dict(zip(families["name"], families["id"]))
            chosen_name = st.selectbox("Família", options.keys(), key="remover_familia_select")
            family_id = options[chosen_name]
            st.warning("Remover a família também remove todas as suas crianças e transações.")
            confirm = st.checkbox("Confirmo a remoção desta família", key="confirm_remover_familia")
            if st.button("Remover família", disabled=not confirm):
                try:
                    db.delete_family(family_id)
                    st.success(f"Família '{chosen_name}' removida com sucesso!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao remover família: {exc}")

    st.subheader("Famílias cadastradas")
    st.dataframe(db.get_families(), width="stretch", hide_index=True)

elif choice == "Gestão de Crianças":
    st.header("🧒 Gestão de Crianças")
    tab_criar, tab_alterar, tab_remover = st.tabs(["Criar", "Alterar", "Remover"])

    with tab_criar:
        family_id = select_family()
        if family_id is not None:
            with st.form("form_crianca_criar"):
                child_name = st.text_input("Nome da criança")
                birth_date = st.date_input(
                    "Data de nascimento", value=date(2015, 1, 1), min_value=date(1990, 1, 1), max_value=date.today()
                )
                submitted = st.form_submit_button("Cadastrar")
                if submitted:
                    if not child_name.strip():
                        st.error("Informe o nome da criança.")
                    else:
                        try:
                            db.add_child(family_id, child_name.strip(), birth_date)
                            st.success(f"Criança '{child_name}' cadastrada com sucesso!")
                        except Exception as exc:
                            st.error(f"Erro ao cadastrar criança: {exc}")

    with tab_alterar:
        children = db.get_children()
        if children.empty:
            st.warning("Nenhuma criança cadastrada ainda.")
        else:
            labels = {
                f"{row.name} ({row.family_name})": row.id for row in children.itertuples()
            }
            chosen_label = st.selectbox("Criança", labels.keys(), key="alterar_crianca_select")
            child = children.loc[children["id"] == labels[chosen_label]].iloc[0]
            families = db.get_families()
            family_options = dict(zip(families["name"], families["id"]))
            with st.form("form_crianca_alterar"):
                new_name = st.text_input("Nome da criança", value=child["name"])
                new_family_name = st.selectbox(
                    "Família", family_options.keys(),
                    index=list(family_options.keys()).index(child["family_name"]),
                )
                new_birth_date = st.date_input(
                    "Data de nascimento", value=child["birth_date"], min_value=date(1990, 1, 1), max_value=date.today()
                )
                submitted = st.form_submit_button("Salvar alterações")
                if submitted:
                    if not new_name.strip():
                        st.error("Informe o nome da criança.")
                    else:
                        try:
                            db.update_child(
                                int(child["id"]), family_options[new_family_name], new_name.strip(), new_birth_date
                            )
                            st.success("Criança atualizada com sucesso!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro ao atualizar criança: {exc}")

    with tab_remover:
        children = db.get_children()
        if children.empty:
            st.warning("Nenhuma criança cadastrada ainda.")
        else:
            labels = {
                f"{row.name} ({row.family_name})": row.id for row in children.itertuples()
            }
            chosen_label = st.selectbox("Criança", labels.keys(), key="remover_crianca_select")
            child_id = labels[chosen_label]
            st.warning("Remover a criança também remove todas as suas transações de mesada.")
            confirm = st.checkbox("Confirmo a remoção desta criança", key="confirm_remover_crianca")
            if st.button("Remover criança", disabled=not confirm):
                try:
                    db.delete_child(child_id)
                    st.success(f"Criança '{chosen_label}' removida com sucesso!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao remover criança: {exc}")

    st.subheader("Crianças cadastradas")
    st.dataframe(db.get_children(), width="stretch", hide_index=True)

elif choice == "Crédito de Mesada":
    st.header("➕ Crédito de Mesada")
    family_id = select_family()
    if family_id is not None:
        child_id = select_child(family_id)
        if child_id is not None:
            with st.form("form_credito"):
                value = st.number_input("Valor", min_value=0.01, step=1.0, format="%.2f")
                reason = st.text_input("Motivo do crédito")
                submitted = st.form_submit_button("Registrar crédito")
                if submitted:
                    if not reason.strip():
                        st.error("Informe o motivo do crédito.")
                    else:
                        try:
                            db.add_transaction(child_id, "credito", value, date.today(), reason.strip())
                            st.success("Crédito registrado com sucesso!")
                        except Exception as exc:
                            st.error(f"Erro ao registrar crédito: {exc}")

elif choice == "Débito de Mesada":
    st.header("➖ Débito de Mesada")
    family_id = select_family()
    if family_id is not None:
        child_id = select_child(family_id)
        if child_id is not None:
            category = st.selectbox("Categoria", DEBIT_CATEGORIES.keys())
            with st.form("form_debito"):
                if category == OUTROS_CATEGORY:
                    value = st.number_input("Valor", min_value=0.01, step=1.0, format="%.2f")
                    reason = st.text_input("Motivo do débito")
                else:
                    value = DEBIT_CATEGORIES[category]
                    reason = category
                    st.write(f"Valor: R$ {value:.2f}".replace(".", ","))
                submitted = st.form_submit_button("Registrar débito")
                if submitted:
                    if not reason.strip():
                        st.error("Informe o motivo do débito.")
                    else:
                        try:
                            db.add_transaction(child_id, "debito", value, date.today(), reason.strip())
                            st.success("Débito registrado com sucesso!")
                        except Exception as exc:
                            st.error(f"Erro ao registrar débito: {exc}")

elif choice == "Extrato e Saldos":
    st.header("📊 Extrato e Saldos")

    st.subheader("Saldos atuais")
    st.dataframe(db.get_balances(), width="stretch", hide_index=True)

    st.subheader("Extrato detalhado")
    families = db.get_families()
    filter_option = st.selectbox("Filtrar por família (opcional)", ["Todas"] + families["name"].tolist())
    if filter_option == "Todas":
        st.dataframe(db.get_transactions(), width="stretch", hide_index=True)
    else:
        family_id = int(families.loc[families["name"] == filter_option, "id"].iloc[0])
        children = db.get_children(family_id)
        tx_frames = [db.get_transactions(int(cid)) for cid in children["id"]]
        combined = pd.concat(tx_frames) if tx_frames else db.get_transactions().iloc[0:0]
        st.dataframe(combined, width="stretch", hide_index=True)
