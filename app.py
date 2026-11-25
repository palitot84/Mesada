"""Aplicativo Streamlit de controle de mesada."""
from datetime import date

import pandas as pd
import streamlit as st

import database as db

st.set_page_config(page_title="Controle de Mesada", page_icon="💰", layout="centered")

db.init_db()

ROLE_LABELS = {"admin": "Administrador", "responsavel": "Responsável"}

if "user" not in st.session_state:
    st.title("💰 Controle de Mesada")
    with st.form("form_login"):
        username = st.text_input("Login")
        password = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            user = db.authenticate(username.strip(), password)
            if user is None:
                st.error("Login ou senha inválidos.")
            else:
                st.session_state["user"] = user
                st.rerun()
    st.stop()

current_user = db.get_user(st.session_state["user"]["id"])
if current_user is None:
    del st.session_state["user"]
    st.rerun()
st.session_state["user"] = current_user
owner_id = current_user["id"]
is_admin = current_user["role"] == "admin"

MENU_OPTIONS = [
    "Gestão de Famílias",
    "Gestão de Crianças",
    "Gestão de Categorias",
    "Crédito de Mesada",
    "Débito de Mesada",
    "Extrato e Saldos",
]
if is_admin:
    MENU_OPTIONS.append("Gestão de Usuários")

st.sidebar.title("💰 Menu")
st.sidebar.caption(f"👤 {current_user['username']} ({ROLE_LABELS.get(current_user['role'], current_user['role'])})")
if st.sidebar.button("Sair"):
    del st.session_state["user"]
    st.rerun()
choice = st.sidebar.radio("Navegação", MENU_OPTIONS)

TX_TYPE_LABELS = {"credito": "Crédito", "debito": "Débito"}


def format_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def category_label(row) -> str:
    if row.is_default:
        return f"{row.name} (valor livre)"
    return f"{row.name} ({format_brl(float(row.value))})"


def render_transaction_screen(tx_type: str) -> None:
    label = TX_TYPE_LABELS[tx_type].lower()
    family_id = select_family()
    if family_id is None:
        return
    child_id = select_child(family_id)
    if child_id is None:
        return
    categories = db.get_categories(owner_id, family_id, tx_type)
    if categories.empty:
        st.warning(f"Esta família não possui categorias de {label}. Cadastre em Gestão de Categorias.")
        return
    options = {category_label(row): row for row in categories.itertuples()}
    category = options[st.selectbox("Categoria", options.keys(), key=f"categoria_{tx_type}")]
    with st.form(f"form_{tx_type}"):
        if category.is_default:
            value = st.number_input("Valor", min_value=0.01, step=1.0, format="%.2f")
            reason = st.text_input(f"Motivo do {label}")
        else:
            value = float(category.value)
            reason = category.name
            st.write(f"Valor: {format_brl(value)}")
        if st.form_submit_button(f"Registrar {label}"):
            if not reason.strip():
                st.error(f"Informe o motivo do {label}.")
            else:
                try:
                    db.add_transaction(owner_id, child_id, tx_type, value, date.today(), reason.strip())
                    st.success(f"{TX_TYPE_LABELS[tx_type]} registrado com sucesso!")
                except Exception as exc:
                    st.error(f"Erro ao registrar {label}: {exc}")


def select_family() -> int | None:
    families = db.get_families(owner_id)
    if families.empty:
        st.warning("Nenhuma família cadastrada ainda. Cadastre uma família primeiro.")
        return None
    options = dict(zip(families["name"], families["id"]))
    chosen_name = st.selectbox("Família", options.keys())
    return options[chosen_name]


def select_child(family_id: int) -> int | None:
    children = db.get_children(owner_id, family_id)
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
                        db.add_family(owner_id, family_name.strip())
                        st.success(f"Família '{family_name}' cadastrada com sucesso!")
                    except Exception as exc:
                        st.error(f"Erro ao cadastrar família: {exc}")

    with tab_alterar:
        families = db.get_families(owner_id)
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
                            db.update_family(owner_id, family_id, new_name.strip())
                            st.success("Família atualizada com sucesso!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro ao atualizar família: {exc}")

    with tab_remover:
        families = db.get_families(owner_id)
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
                    db.delete_family(owner_id, family_id)
                    st.success(f"Família '{chosen_name}' removida com sucesso!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao remover família: {exc}")

    st.subheader("Famílias cadastradas")
    st.dataframe(db.get_families(owner_id), width="stretch", hide_index=True)

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
                            db.add_child(owner_id, family_id, child_name.strip(), birth_date)
                            st.success(f"Criança '{child_name}' cadastrada com sucesso!")
                        except Exception as exc:
                            st.error(f"Erro ao cadastrar criança: {exc}")

    with tab_alterar:
        children = db.get_children(owner_id)
        if children.empty:
            st.warning("Nenhuma criança cadastrada ainda.")
        else:
            labels = {
                f"{row.name} ({row.family_name})": row.id for row in children.itertuples()
            }
            chosen_label = st.selectbox("Criança", labels.keys(), key="alterar_crianca_select")
            child = children.loc[children["id"] == labels[chosen_label]].iloc[0]
            families = db.get_families(owner_id)
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
                                owner_id,
                                int(child["id"]), family_options[new_family_name], new_name.strip(), new_birth_date
                            )
                            st.success("Criança atualizada com sucesso!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro ao atualizar criança: {exc}")

    with tab_remover:
        children = db.get_children(owner_id)
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
                    db.delete_child(owner_id, child_id)
                    st.success(f"Criança '{chosen_label}' removida com sucesso!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao remover criança: {exc}")

    st.subheader("Crianças cadastradas")
    st.dataframe(db.get_children(owner_id), width="stretch", hide_index=True)

elif choice == "Gestão de Categorias":
    st.header("🏷️ Gestão de Categorias")
    st.caption('A categoria "Outros" é criada automaticamente em cada família, tem valor livre e não pode ser alterada.')
    type_options = {v: k for k, v in TX_TYPE_LABELS.items()}
    tab_criar, tab_alterar, tab_remover = st.tabs(["Criar", "Alterar", "Remover"])

    with tab_criar:
        family_id = select_family()
        if family_id is not None:
            with st.form("form_categoria_criar", clear_on_submit=True):
                cat_name = st.text_input("Nome da categoria")
                cat_type = st.radio("Tipo", type_options.keys(), horizontal=True)
                cat_value = st.number_input("Valor", min_value=0.01, step=1.0, format="%.2f")
                if st.form_submit_button("Cadastrar"):
                    if not cat_name.strip():
                        st.error("Informe o nome da categoria.")
                    else:
                        try:
                            db.add_category(owner_id, family_id, cat_name.strip(), type_options[cat_type], cat_value)
                            st.success(f"Categoria '{cat_name.strip()}' cadastrada com sucesso!")
                        except Exception as exc:
                            st.error(f"Erro ao cadastrar categoria: {exc}")

    editable = db.get_categories(owner_id)
    editable = editable.loc[~editable["is_default"].astype(bool)]
    labels = {
        f"{row.name} - {TX_TYPE_LABELS[row.type]} ({row.family_name})": row.id for row in editable.itertuples()
    }

    with tab_alterar:
        if editable.empty:
            st.warning("Nenhuma categoria personalizada cadastrada ainda.")
        else:
            chosen_label = st.selectbox("Categoria", labels.keys(), key="alterar_categoria_select")
            cat = editable.loc[editable["id"] == labels[chosen_label]].iloc[0]
            families = db.get_families(owner_id)
            family_options = dict(zip(families["name"], families["id"]))
            with st.form("form_categoria_alterar"):
                new_name = st.text_input("Nome da categoria", value=cat["name"])
                new_type = st.radio(
                    "Tipo", type_options.keys(), horizontal=True,
                    index=list(type_options.values()).index(cat["type"]),
                )
                new_value = st.number_input("Valor", min_value=0.01, step=1.0, format="%.2f", value=float(cat["value"]))
                new_family = st.selectbox(
                    "Família", family_options.keys(),
                    index=list(family_options.keys()).index(cat["family_name"]),
                )
                if st.form_submit_button("Salvar alterações"):
                    if not new_name.strip():
                        st.error("Informe o nome da categoria.")
                    else:
                        try:
                            db.update_category(
                                owner_id, int(cat["id"]), family_options[new_family],
                                new_name.strip(), type_options[new_type], new_value,
                            )
                            st.success("Categoria atualizada com sucesso!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro ao atualizar categoria: {exc}")

    with tab_remover:
        if editable.empty:
            st.warning("Nenhuma categoria personalizada cadastrada ainda.")
        else:
            chosen_label = st.selectbox("Categoria", labels.keys(), key="remover_categoria_select")
            st.info("Os lançamentos já registrados com esta categoria são mantidos no extrato.")
            confirm = st.checkbox("Confirmo a remoção desta categoria", key="confirm_remover_categoria")
            if st.button("Remover categoria", disabled=not confirm):
                try:
                    db.delete_category(owner_id, labels[chosen_label])
                    st.success(f"Categoria '{chosen_label}' removida com sucesso!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao remover categoria: {exc}")

    st.subheader("Categorias cadastradas")
    display = db.get_categories(owner_id).rename(columns={
        "name": "categoria", "type": "tipo", "value": "valor", "family_name": "família",
    })
    display["tipo"] = display["tipo"].map(TX_TYPE_LABELS)
    display["valor"] = [
        "Livre" if is_default else format_brl(float(value))
        for is_default, value in zip(display["is_default"], display["valor"])
    ]
    st.dataframe(display[["família", "categoria", "tipo", "valor"]], width="stretch", hide_index=True)

elif choice == "Crédito de Mesada":
    st.header("➕ Crédito de Mesada")
    render_transaction_screen("credito")

elif choice == "Débito de Mesada":
    st.header("➖ Débito de Mesada")
    render_transaction_screen("debito")

elif choice == "Extrato e Saldos":
    st.header("📊 Extrato e Saldos")

    st.subheader("Saldos atuais")
    st.dataframe(db.get_balances(owner_id), width="stretch", hide_index=True)

    st.subheader("Extrato detalhado")
    families = db.get_families(owner_id)
    filter_option = st.selectbox("Filtrar por família (opcional)", ["Todas"] + families["name"].tolist())
    if filter_option == "Todas":
        st.dataframe(db.get_transactions(owner_id), width="stretch", hide_index=True)
    else:
        family_id = int(families.loc[families["name"] == filter_option, "id"].iloc[0])
        children = db.get_children(owner_id, family_id)
        tx_frames = [db.get_transactions(owner_id, int(cid)) for cid in children["id"]]
        combined = pd.concat(tx_frames) if tx_frames else db.get_transactions(owner_id).iloc[0:0]
        st.dataframe(combined, width="stretch", hide_index=True)

elif choice == "Gestão de Usuários" and is_admin:
    st.header("🔐 Gestão de Usuários")
    role_options = {ROLE_LABELS[r]: r for r in db.ROLES}
    tab_criar, tab_alterar, tab_remover = st.tabs(["Criar", "Alterar", "Remover"])

    with tab_criar:
        with st.form("form_usuario_criar", clear_on_submit=True):
            new_username = st.text_input("Login")
            new_password = st.text_input("Senha", type="password")
            new_role_label = st.selectbox("Perfil", role_options.keys(), index=1)
            if st.form_submit_button("Cadastrar"):
                if not new_username.strip() or not new_password:
                    st.error("Informe login e senha.")
                else:
                    try:
                        db.add_user(new_username.strip(), new_password, role_options[new_role_label])
                        st.success(f"Usuário '{new_username.strip()}' cadastrado com sucesso!")
                    except Exception as exc:
                        st.error(f"Erro ao cadastrar usuário: {exc}")

    users = db.get_users()

    with tab_alterar:
        user_options = dict(zip(users["username"], users["id"]))
        chosen_username = st.selectbox("Usuário", user_options.keys(), key="alterar_usuario_select")
        user = users.loc[users["id"] == user_options[chosen_username]].iloc[0]
        is_self = int(user["id"]) == owner_id
        with st.form("form_usuario_alterar"):
            edit_username = st.text_input("Login", value=user["username"])
            edit_role_label = st.selectbox(
                "Perfil", role_options.keys(),
                index=list(role_options.values()).index(user["role"]),
                disabled=is_self,
                help="Você não pode alterar o seu próprio perfil." if is_self else None,
            )
            edit_password = st.text_input("Nova senha (deixe em branco para manter)", type="password")
            if st.form_submit_button("Salvar alterações"):
                if not edit_username.strip():
                    st.error("Informe o login.")
                else:
                    try:
                        db.update_user(
                            int(user["id"]),
                            edit_username.strip(),
                            user["role"] if is_self else role_options[edit_role_label],
                            edit_password or None,
                        )
                        st.success("Usuário atualizado com sucesso!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Erro ao atualizar usuário: {exc}")

    with tab_remover:
        removable = users.loc[users["id"] != owner_id]
        if removable.empty:
            st.warning("Não há outros usuários para remover.")
        else:
            remove_options = dict(zip(removable["username"], removable["id"]))
            chosen_username = st.selectbox("Usuário", remove_options.keys(), key="remover_usuario_select")
            st.warning("Remover o usuário também remove todas as famílias, crianças e transações criadas por ele.")
            confirm = st.checkbox("Confirmo a remoção deste usuário", key="confirm_remover_usuario")
            if st.button("Remover usuário", disabled=not confirm):
                try:
                    db.delete_user(remove_options[chosen_username])
                    st.success(f"Usuário '{chosen_username}' removido com sucesso!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao remover usuário: {exc}")

    st.subheader("Usuários cadastrados")
    display = db.get_users().rename(columns={"username": "login", "role": "perfil", "families": "famílias"})
    display["perfil"] = display["perfil"].map(ROLE_LABELS)
    st.dataframe(display, width="stretch", hide_index=True)
