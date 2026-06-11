import streamlit as st
import polars as pl
import database as db
import engine
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Tenta pegar do secrets do Streamlit primeiro (Prod), senão do .env (Local)
admin_pass = st.secrets.get("ADMIN_PASS", os.getenv("ADMIN_PASS", "admin"))

st.set_page_config(page_title="Bolão Copa 2026", layout="centered", initial_sidebar_state="collapsed")

# Custom CSS for minimalist style
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚽ Bolão da Copa do Mundo 2026")

# Initialize database
try:
    db.init_db()
except Exception as e:
    st.error(f"Erro ao inicializar o banco: {e}")

# Load data
users_df = db.get_users_df()
gabarito_df = db.get_gabarito_df()
palpites_df = db.get_palpites_df()

# Auth State
if "logged_user_id" not in st.session_state:
    st.session_state.logged_user_id = None
if "logged_user_name" not in st.session_state:
    st.session_state.logged_user_name = None

def logout():
    st.session_state.logged_user_id = None
    st.session_state.logged_user_name = None

# Tabs Structure
if st.session_state.logged_user_id is None:
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Login / Cadastro", "Regras", "Classificação", "Ver Palpites", "Painel do Admin"])
else:
    st.sidebar.write(f"Logado como: **{st.session_state.logged_user_name}**")
    st.sidebar.button("Sair", on_click=logout)
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Meus Palpites", "Regras", "Classificação", "Ver Palpites", "Painel do Admin"])

# --- TAB 1: LOGIN / CADASTRO (Not Logged In) ---
if st.session_state.logged_user_id is None:
    with tab1:
        auth_mode = st.radio("Selecione:", ["Entrar", "Novo Cadastro"], horizontal=True)

        if auth_mode == "Entrar":
            st.subheader("Login")
            with st.form("login_form"):
                log_name = st.text_input("Nome")
                log_pass = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar"):
                    user = db.authenticate_user(log_name, log_pass)
                    if user:
                        st.session_state.logged_user_id = user[0]
                        st.session_state.logged_user_name = log_name
                        st.rerun()
                    else:
                        st.error("Nome ou senha incorretos.")

        elif auth_mode == "Novo Cadastro":
            st.subheader("Cadastro e Pagamento")
            st.markdown("A taxa de participação é de **R$ 30,00**. Faça o PIX e clique em 'Confirmar'.")
            
            # Simulated QR Code Block
            st.markdown("### Chave PIX (E-mail)")
            st.code("gumk123@gmail.com", language="text")
            st.caption("👆 Transfira R$ 30,00 para a chave acima em nome de Gustavo Ribeiro de Oliveira Roque.")
            
            with st.form("register_form"):
                reg_name = st.text_input("Nome")
                reg_zap = st.text_input("WhatsApp")
                reg_pass = st.text_input("Senha", type="password")
                
                check_pix = st.checkbox("Confirmo que já realizei o PIX de R$ 30,00.")
                
                if st.form_submit_button("Finalizar Cadastro"):
                    if not reg_name or not reg_zap or not reg_pass:
                        st.error("Preencha todos os campos.")
                    elif not check_pix:
                        st.error("Você precisa confirmar que realizou o pagamento.")
                    else:
                        if db.create_user(reg_name, reg_zap, reg_pass):
                            user = db.authenticate_user(reg_name, reg_pass)
                            st.session_state.logged_user_id = user[0]
                            st.session_state.logged_user_name = reg_name
                            st.success("Cadastro realizado com sucesso!")
                            st.rerun()
                        else:
                            st.error("Este nome já está cadastrado.")

# --- TAB 1: MEUS PALPITES (Logged In) ---
else:
    with tab1:
        st.header("Meus Palpites")
        st.write("Preencha seus palpites para as fases liberadas.")
        
        user_palpites = palpites_df.filter(pl.col("user_id") == st.session_state.logged_user_id) if not palpites_df.is_empty() else pl.DataFrame()
        
        open_matches = gabarito_df.filter(pl.col("is_open") == 1).sort(["fase", "data", "match_id"])
        
        if open_matches.is_empty():
            st.info("Nenhuma fase aberta para apostas no momento.")
        else:
            with st.form("palpites_form"):
                current_fase = ""
                for row in open_matches.iter_rows(named=True):
                    if row["fase"] != current_fase:
                        st.subheader(f"🏆 {row['fase']}")
                        current_fase = row["fase"]
                        
                    match_id = row["match_id"]
                    val_a = 0
                    val_b = 0
                    has_prediction = False
                    
                    if not user_palpites.is_empty():
                        p = user_palpites.filter(pl.col("match_id") == match_id)
                        if not p.is_empty() and p["gols_a"][0] is not None and p["gols_b"][0] is not None:
                            val_a = p["gols_a"][0]
                            val_b = p["gols_b"][0]
                            has_prediction = True

                    col1, col2, col3, col4, col5 = st.columns([2, 1, 0.5, 1, 2])
                    with col1:
                        st.write(f"**{row['time_a']}**")
                        st.caption(f"{row['data']}")
                    with col2:
                        st.number_input("Gols A", min_value=0, max_value=20, value=val_a, key=f"p_a_{match_id}", label_visibility="collapsed", disabled=has_prediction)
                    with col3:
                        st.write("X")
                    with col4:
                        st.number_input("Gols B", min_value=0, max_value=20, value=val_b, key=f"p_b_{match_id}", label_visibility="collapsed", disabled=has_prediction)
                    with col5:
                        st.write(f"**{row['time_b']}**")
                        
                if st.form_submit_button("Salvar Palpites"):
                    palpites_lote = []
                    for row in open_matches.iter_rows(named=True):
                        m_id = row["match_id"]
                        
                        p = user_palpites.filter(pl.col("match_id") == m_id) if not user_palpites.is_empty() else None
                        if p is not None and not p.is_empty() and p["gols_a"][0] is not None:
                            continue # já foi palpitado e travado
                            
                        a = st.session_state[f"p_a_{m_id}"]
                        b = st.session_state[f"p_b_{m_id}"]
                        palpites_lote.append({'match_id': m_id, 'gols_a': a, 'gols_b': b})
                    
                    if palpites_lote:
                        db.upsert_palpites_batch(st.session_state.logged_user_id, palpites_lote)
                        st.success("Palpites salvos com sucesso!")
                        st.rerun()
                    else:
                        st.info("Nenhum palpite novo para salvar.")

# --- TAB 2: REGRAS ---
with tab2:
    st.header("📖 Regras do Bolão")
    st.markdown("""
    **1. Inscrições e Pagamento:**
    - Taxa de inscrição: R$ 30,00 via PIX.
    - Inscrições abertas a qualquer momento.
    - Administrador confirmará o pagamento.
    
    **2. Sistema de Pontuação:**
    - **3 Pontos:** Acerto exato do placar (ex: apostou 2x1 e foi 2x1).
    - **1 Ponto:** Acerto da tendência/vencedor (ex: apostou 2x1 e foi 1x0, você acertou quem ganhou).
    - **0 Pontos:** Errou quem venceu ou apostou empate e teve vencedor.
    
    **3. Fases:**
    - Inicialmente apenas a Fase de Grupos estará disponível.
    - Durante o andamento da Copa, as fases eliminatórias (Oitavas, Quartas, etc) serão desbloqueadas.
    - Fique atento para logar e enviar os palpites das novas fases!
    
    **4. Premiação:**
    - 1º Lugar: 70% do montante arrecadado.
    - 2º Lugar: 20% do montante arrecadado.
    - 3º Lugar: 10% do montante arrecadado.
    """)

# --- TAB 3: CLASSIFICAÇÃO ---
with tab3:
    st.header("Classificação")
    ranking = engine.calculate_ranking(db.get_palpites_df(), db.get_gabarito_df(), db.get_users_df())
    st.dataframe(ranking.to_pandas(), use_container_width=True, hide_index=True)

# --- TAB 4: VER PALPITES ---
with tab4:
    st.header("Ver Palpites dos Usuários")
    current_names = users_df["name"].to_list() if not users_df.is_empty() else []
    selected_view_user = st.selectbox("Selecione um usuário para espiar:", [""] + current_names)
    
    if selected_view_user:
        user_id_view = users_df.filter(pl.col("name") == selected_view_user)["user_id"][0]
        user_palpites = palpites_df.filter(pl.col("user_id") == user_id_view) if not palpites_df.is_empty() else pl.DataFrame()
        
        if user_palpites.is_empty():
            st.warning("Este usuário ainda não palpitou.")
        else:
            st.write(f"Palpites de **{selected_view_user}**:")
            gabarito_sorted = gabarito_df.sort(["fase", "data", "match_id"])
            current_fase_view = ""
            for row in gabarito_sorted.iter_rows(named=True):
                if row["fase"] != current_fase_view:
                    st.markdown(f"#### 🏆 {row['fase']}")
                    current_fase_view = row["fase"]
                
                p = user_palpites.filter(pl.col("match_id") == row["match_id"])
                if not p.is_empty():
                    ga = p["gols_a"][0]
                    gb = p["gols_b"][0]
                    st.markdown(f"{row['data']} | **{row['time_a']}** {ga} x {gb} **{row['time_b']}**")
                else:
                    st.markdown(f"{row['data']} | **{row['time_a']}** - x - **{row['time_b']}** *(Sem palpite)*")

# --- TAB 5: PAINEL DO ADMIN ---
with tab5:
    st.header("Painel do Admin")
    senha = st.text_input("Senha Admin", type="password")
    if senha == admin_pass:
        st.success("Acesso liberado.")
        
        with st.expander("➕ Adicionar Jogo do Mata-Mata"):
            with st.form("add_match"):
                f_fase = st.selectbox("Fase", ["16-avos de Final", "Oitavas de Final", "Quartas de Final", "Semifinal", "Final"])
                f_data = st.text_input("Data (ex: 2026-06-28)")
                f_time_a = st.text_input("Time A")
                f_time_b = st.text_input("Time B")
                if st.form_submit_button("Inserir Jogo"):
                    db.insert_match(f_fase, "", f_data, f_time_a, f_time_b)
                    st.success("Jogo inserido! (Ele entra bloqueado por padrão)")
                    st.rerun()

        st.write("---")
        st.subheader("Gerenciar Jogos (Resultados e Liberação)")
        if not gabarito_df.is_empty():
            with st.form("admin_manage_form"):
                for row in gabarito_df.sort(["fase", "data", "match_id"]).iter_rows(named=True):
                    m_id = row["match_id"]
                    played = row["gols_a"] is not None
                    val_a = row["gols_a"] if played else 0
                    val_b = row["gols_b"] if played else 0
                    is_open = bool(row["is_open"])
                    
                    col1, col2, col3, col4, col5, col6, col7 = st.columns([1.5, 1, 0.3, 1, 1.5, 1, 1])
                    with col1:
                        st.write(f"**{row['time_a']}**")
                        st.caption(f"{row['fase']}")
                    with col2:
                        st.number_input("Gols A", min_value=0, max_value=20, value=val_a, key=f"adm_a_{m_id}", label_visibility="collapsed")
                    with col3:
                        st.write("X")
                    with col4:
                        st.number_input("Gols B", min_value=0, max_value=20, value=val_b, key=f"adm_b_{m_id}", label_visibility="collapsed")
                    with col5:
                        st.write(f"**{row['time_b']}**")
                    with col6:
                        st.checkbox("Apostas Abertas", value=is_open, key=f"open_{m_id}")
                    with col7:
                        st.checkbox("Jogo Encerrado", value=played, key=f"played_{m_id}")
                        
                if st.form_submit_button("Salvar Tudo"):
                    updates_lote = []
                    for row in gabarito_df.iter_rows(named=True):
                        m_id = row["match_id"]
                        a = st.session_state[f"adm_a_{m_id}"]
                        b = st.session_state[f"adm_b_{m_id}"]
                        is_open_val = 1 if st.session_state[f"open_{m_id}"] else 0
                        is_played = st.session_state[f"played_{m_id}"]
                        
                        gols_a_val = a if is_played else None
                        gols_b_val = b if is_played else None
                        
                        updates_lote.append({
                            'match_id': m_id, 
                            'is_open': is_open_val, 
                            'gols_a': gols_a_val, 
                            'gols_b': gols_b_val
                        })
                    
                    db.update_gabarito_and_status_batch(updates_lote)
                    st.success("Tudo salvo com sucesso no Google Sheets!")
                    st.rerun()
    elif senha:
        st.error("Senha incorreta.")
