import streamlit as st
import gspread
import polars as pl
import pandas as pd
import os
import hashlib

CSV_PATH = "planilha/bolao_copa_2026 - bolao_copa_2026.csv"

# Conexão com Google Sheets usando Streamlit Secrets
@st.cache_resource
def get_client():
    if "gcp_service_account" not in st.secrets:
        raise ValueError("Credenciais 'gcp_service_account' não encontradas no secrets.toml.")
    creds_dict = dict(st.secrets["gcp_service_account"])
    return gspread.service_account_from_dict(creds_dict)

@st.cache_resource
def get_spreadsheet():
    if "spreadsheet_id" not in st.secrets:
        raise ValueError("ID da planilha 'spreadsheet_id' não encontrado no secrets.toml.")
    client = get_client()
    return client.open_by_key(st.secrets["spreadsheet_id"])

def _ensure_worksheet(sheet, title, headers):
    try:
        ws = sheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.append_row(headers)
    return ws

def init_db():
    try:
        sheet = get_spreadsheet()
    except Exception as e:
        raise e

    # Garante que as 3 abas existam com os devidos cabeçalhos
    ws_users = _ensure_worksheet(sheet, "users", ['user_id', 'name', 'whatsapp', 'password', 'payment_status'])
    ws_gabarito = _ensure_worksheet(sheet, "gabarito", ['match_id', 'fase', 'is_open', 'grupo', 'data', 'horario', 'time_a', 'gols_a', 'time_b', 'gols_b'])
    ws_palpites = _ensure_worksheet(sheet, "palpites", ['palpite_id', 'user_id', 'match_id', 'gols_a', 'gols_b'])

    # Carregar jogos da fase de grupos iniciais se gabarito estiver vazio (apenas cabeçalho)
    if len(ws_gabarito.get_all_values()) <= 1 and os.path.exists(CSV_PATH):
        df = pl.read_csv(CSV_PATH)
        rows_to_insert = []
        for i, row in enumerate(df.iter_rows(named=True)):
            match_id = i + 1
            rows_to_insert.append([
                match_id, 'Fase de Grupos', 1, row['Grupo'], row['Data'], 
                row['Time A'], "", row['Time B'], ""
            ])
        ws_gabarito.append_rows(rows_to_insert)

# --- Funções de Leitura (com TTL curto caso outras pessoas atualizem) ---
@st.cache_data(ttl=10)
def get_users_df() -> pl.DataFrame:
    try:
        ws = get_spreadsheet().worksheet("users")
        data = ws.get_all_records()
        return pl.DataFrame(data, schema_overrides={'user_id': pl.Int64}) if data else pl.DataFrame(schema={'user_id': pl.Int64, 'name': pl.Utf8, 'whatsapp': pl.Utf8, 'password': pl.Utf8, 'payment_status': pl.Utf8})
    except Exception:
        return pl.DataFrame()

@st.cache_data(ttl=10)
def get_gabarito_df() -> pl.DataFrame:
    try:
        ws = get_spreadsheet().worksheet("gabarito")
        data = ws.get_all_records()
        df = pl.DataFrame(data, schema_overrides={'match_id': pl.Int64, 'gols_a': pl.Utf8, 'gols_b': pl.Utf8}) if data else pl.DataFrame(schema={'match_id': pl.Int64, 'fase': pl.Utf8, 'is_open': pl.Int64, 'grupo': pl.Utf8, 'data': pl.Utf8, 'horario': pl.Utf8, 'time_a': pl.Utf8, 'gols_a': pl.Int64, 'time_b': pl.Utf8, 'gols_b': pl.Int64})
        
        # Converte string vazia para nulo
        df = df.with_columns([
            pl.when(pl.col("gols_a").cast(pl.Utf8) == "").then(None).otherwise(pl.col("gols_a")).cast(pl.Int64).alias("gols_a"),
            pl.when(pl.col("gols_b").cast(pl.Utf8) == "").then(None).otherwise(pl.col("gols_b")).cast(pl.Int64).alias("gols_b")
        ])
        return df
    except Exception:
        return pl.DataFrame()

@st.cache_data(ttl=10)
def get_palpites_df() -> pl.DataFrame:
    try:
        ws = get_spreadsheet().worksheet("palpites")
        data = ws.get_all_records()
        df = pl.DataFrame(data, schema_overrides={'match_id': pl.Int64, 'user_id': pl.Int64, 'gols_a': pl.Utf8, 'gols_b': pl.Utf8}) if data else pl.DataFrame(schema={'palpite_id': pl.Int64, 'user_id': pl.Int64, 'match_id': pl.Int64, 'gols_a': pl.Int64, 'gols_b': pl.Int64})
        
        # Converte string vazia para nulo
        df = df.with_columns([
            pl.when(pl.col("gols_a").cast(pl.Utf8) == "").then(None).otherwise(pl.col("gols_a")).cast(pl.Int64).alias("gols_a"),
            pl.when(pl.col("gols_b").cast(pl.Utf8) == "").then(None).otherwise(pl.col("gols_b")).cast(pl.Int64).alias("gols_b")
        ])
        return df
    except Exception:
        return pl.DataFrame()

def clear_cache():
    st.cache_data.clear()

# --- Funções de Escrita ---
def create_user(name: str, whatsapp: str, password: str) -> bool:
    users_df = get_users_df()
    if not users_df.is_empty() and name in users_df["name"].to_list():
        return False
        
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
    ws = get_spreadsheet().worksheet("users")
    new_id = int(users_df["user_id"].max()) + 1 if not users_df.is_empty() and users_df["user_id"].max() is not None else 1
    
    ws.append_row([new_id, name, str(whatsapp), hashed_password, 'approved'])
    clear_cache()
    return True

def authenticate_user(name: str, password: str):
    users_df = get_users_df()
    if users_df.is_empty(): return None
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    match = users_df.filter((pl.col("name") == name) & (pl.col("password").cast(pl.Utf8) == str(hashed_password)))
    if match.height > 0:
        return (match["user_id"][0], match["payment_status"][0])
    return None

def insert_match(fase: str, grupo: str, data: str, horario: str, time_a: str, time_b: str):
    gabarito_df = get_gabarito_df()
    new_id = int(gabarito_df["match_id"].max()) + 1 if not gabarito_df.is_empty() and gabarito_df["match_id"].max() is not None else 1
    
    ws = get_spreadsheet().worksheet("gabarito")
    headers = ws.row_values(1)
    row_to_insert = [""] * len(headers)
    
    col_map = {
        'match_id': new_id, 'fase': fase, 'is_open': 0, 'grupo': grupo, 
        'data': data, 'horario': horario, 'time_a': time_a, 'time_b': time_b
    }
    
    for col_name, value in col_map.items():
        if col_name in headers:
            row_to_insert[headers.index(col_name)] = value
            
    ws.append_row(row_to_insert)
    clear_cache()

# Lote de atualização (BATCH) para o Admin
def update_gabarito_and_status_batch(updates_list):
    """
    updates_list é uma lista de dicionários: 
    [{'match_id': int, 'is_open': int, 'gols_a': int|None, 'gols_b': int|None}, ...]
    """
    ws = get_spreadsheet().worksheet("gabarito")
    all_rows = ws.get_all_values()
    headers = all_rows[0]
    
    idx_is_open = headers.index('is_open')
    idx_gols_a = headers.index('gols_a')
    idx_gols_b = headers.index('gols_b')
    
    cells_to_update = []
    
    for update in updates_list:
        m_id = update['match_id']
        # Encontra a linha onde match_id está (linha_num = idx + 1 por causa do 0-index)
        # O match_id na planilha é a coluna 0
        for i, row in enumerate(all_rows[1:], start=2):
            if str(row[0]) == str(m_id):
                cells_to_update.append(gspread.Cell(row=i, col=idx_is_open+1, value=update['is_open']))
                
                ga = update['gols_a'] if update['gols_a'] is not None else ""
                gb = update['gols_b'] if update['gols_b'] is not None else ""
                
                cells_to_update.append(gspread.Cell(row=i, col=idx_gols_a+1, value=ga))
                cells_to_update.append(gspread.Cell(row=i, col=idx_gols_b+1, value=gb))
                break
                
    if cells_to_update:
        ws.update_cells(cells_to_update)
        clear_cache()

# Lote de atualização de palpites
def upsert_palpites_batch(user_id: int, palpites_list):
    """
    palpites_list: [{'match_id': int, 'gols_a': int, 'gols_b': int}, ...]
    """
    ws = get_spreadsheet().worksheet("palpites")
    all_rows = ws.get_all_values()
    
    if len(all_rows) > 1:
        headers = all_rows[0]
        # mapear quais já existem
        existing_rows = {}
        for i, row in enumerate(all_rows[1:], start=2):
            # row[1] = user_id, row[2] = match_id
            if str(row[1]) == str(user_id):
                existing_rows[str(row[2])] = i
    else:
        existing_rows = {}
        headers = ['palpite_id', 'user_id', 'match_id', 'gols_a', 'gols_b']
        
    # Achar o último ID
    if len(all_rows) > 1:
        last_id = max([int(r[0]) for r in all_rows[1:] if r[0].isdigit()] + [0])
    else:
        last_id = 0
        
    cells_to_update = []
    rows_to_append = []
    
    for p in palpites_list:
        m_id = str(p['match_id'])
        if m_id in existing_rows:
            # Update
            r_idx = existing_rows[m_id]
            cells_to_update.append(gspread.Cell(row=r_idx, col=4, value=p['gols_a']))
            cells_to_update.append(gspread.Cell(row=r_idx, col=5, value=p['gols_b']))
        else:
            # Append
            last_id += 1
            rows_to_append.append([last_id, user_id, m_id, p['gols_a'], p['gols_b']])
            
    if cells_to_update:
        ws.update_cells(cells_to_update)
    if rows_to_append:
        ws.append_rows(rows_to_append)
        
    clear_cache()

# Manter as antigas como fallback, chamando o batch para um só
def upsert_palpite(user_id: int, match_id: int, gols_a: int, gols_b: int):
    upsert_palpites_batch(user_id, [{'match_id': match_id, 'gols_a': gols_a, 'gols_b': gols_b}])
    
def update_gabarito(match_id: int, gols_a: int, gols_b: int):
    update_gabarito_and_status_batch([{'match_id': match_id, 'is_open': 0, 'gols_a': gols_a, 'gols_b': gols_b}])
