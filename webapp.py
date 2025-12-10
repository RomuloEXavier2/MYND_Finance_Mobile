import streamlit as st
import os
import json
import pandas as pd
import tempfile
import base64
import requests
import bcrypt
import time  # <--- GARANTIDO AQUI
from datetime import datetime  # <--- GARANTIDO AQUI
import plotly.express as px
from openai import OpenAI
from audio_recorder_streamlit import audio_recorder
from streamlit_lottie import st_lottie
from streamlit_autorefresh import st_autorefresh
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="MYND Finance", page_icon="assets/logo_header.png", layout="wide")


# --- CARREGAMENTO DE ASSETS ---
def get_base64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return ""


bg_img = get_base64_of_bin_file("assets/bg_mobile.png")
carie_icon_path = "assets/carie.png"
logo_img = get_base64_of_bin_file("assets/logo_header.png")

# --- CONSTANTES ---
# URL do Firebase
FIREBASE_URL = "https://mynd-e958a-default-rtdb.firebaseio.com/MYND_Finance"

# ID DA PLANILHA MODELO (TEMPLATE)
# IMPORTANTE: Você COMPARTILHOU essa planilha com o email do robô (client_email)?
TEMPLATE_SHEET_ID = "1UyR7ng84daDRIm2pj2t_aBs62ROcypM3yP-nfz6djww"


# ==========================================
# FUNÇÕES DE BACKEND (AUTH & DATA)
# ==========================================

def get_google_creds():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    if "GOOGLE_CREDENTIALS" in st.secrets:
        creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        return ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)


def firebase_db(path, method="GET", data=None):
    url = f"{FIREBASE_URL}/{path}.json"
    try:
        if method == "GET":
            response = requests.get(url)
            return response.json() if response.status_code == 200 else None
        elif method == "PUT":
            response = requests.put(url, json=data)
            return response.json()
        elif method == "PATCH":
            requests.patch(url, json=data)
            return True
    except Exception as e:
        print(f"Erro Firebase: {e}")
        return None


def criar_planilha_usuario(username):
    """Cria uma cópia da planilha modelo para o usuário"""
    try:
        creds = get_google_creds()
        service = build('drive', 'v3', credentials=creds)

        # Copia o Template
        body = {'name': f'MYND_Finance_{username}'}

        # Tenta copiar (Aqui dava o erro 404 se não compartilhado)
        drive_response = service.files().copy(
            fileId=TEMPLATE_SHEET_ID, body=body).execute()

        new_sheet_id = drive_response.get('id')

        # Opcional: Compartilhar a nova planilha com um email real (se tivermos)
        # Para simplificar, o robô é o dono e o app usa o robô para ler/escrever.

        return new_sheet_id
    except Exception as e:
        st.error(f"Erro Drive API: {e}. Verifique se compartilhou o Template com o robô!")
        return None


def autenticar(user, password):
    user_data = firebase_db(f"users/{user}")

    if not user_data:
        return False, "Usuário não encontrado.", None

    stored_pass = user_data.get('password')
    pass_ok = False

    try:
        # Verifica se é hash bcrypt
        if bcrypt.checkpw(password.encode(), stored_pass.encode()):
            pass_ok = True
    except:
        # Fallback texto plano
        if str(password) == str(stored_pass):
            pass_ok = True

    if not pass_ok:
        return False, "Senha incorreta.", None

    if user_data.get('status') != "ATIVO":
        return False, "Conta inativa.", None

    # Verifica se tem planilha vinculada
    if not user_data.get('sheet_id'):
        with st.spinner("Primeiro acesso: Configurando banco de dados..."):
            new_id = criar_planilha_usuario(user)
            if new_id:
                user_data['sheet_id'] = new_id
                firebase_db(f"users/{user}", "PATCH", {"sheet_id": new_id})
            else:
                return False, "Falha ao criar planilha. Contate suporte.", None

    return True, "Login realizado!", user_data


def registrar(user, password, nome):
    if firebase_db(f"users/{user}"):
        return False, "Usuário já existe."

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    # CORREÇÃO DO ERRO DE TIME: Usando datetime agora
    data_hoje = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_user = {
        "password": hashed,
        "name": nome,
        "status": "ATIVO",
        "role": "user",
        "sheet_id": "",
        "created_at": data_hoje
    }

    res = firebase_db(f"users/{user}", "PUT", new_user)

    if res:
        return True, "Conta criada! Faça login."
    else:
        return False, "Erro ao conectar no banco."


# ==========================================
# INTERFACE E CSS
# ==========================================
st.markdown(f"""
    <style>
    .stApp {{ background-color: #000000 !important; color: #e0e0e0; }}

    .login-box {{
        background: rgba(10,10,10,0.95);
        border: 1px solid #333;
        border-radius: 20px;
        padding: 40px;
        box-shadow: 0 0 50px rgba(0, 229, 255, 0.1);
        text-align: center;
    }}

    .stTextInput input {{
        background-color: #111 !important; color: white !important;
        border: 1px solid #333 !important; border-radius: 10px !important;
    }}

    div[data-testid="stFormSubmitButton"] button {{
        background-color: #00E5FF !important; color: black !important;
        border-radius: 10px !important; border: none !important; font-weight: bold !important;
    }}

    .stTabs [data-baseweb="tab-list"] {{ border-bottom: 1px solid #333; }}
    .stTabs [aria-selected="true"] {{ border: 1px solid #00E5FF !important; color: #00E5FF !important; }}

    header, footer {{visibility: hidden;}}
    .block-container {{ padding-top: 10px; padding-bottom: 120px; }}
    .stChatMessage {{ background-color: rgba(20, 20, 20, 0.85); border: 1px solid #333; }}
    div[data-testid="chatAvatarIcon-user"] {{ background-color: #00E5FF !important; color: black !important; }}

    iframe[title="audio_recorder_streamlit.audio_recorder"] {{
        position: fixed !important; bottom: 30px !important; left: 50% !important;
        transform: translateX(-50%) !important; z-index: 99999 !important;
        background-color: #000000 !important; border-radius: 50%;
        border: 2px solid #00E5FF; box-shadow: 0 0 25px rgba(0, 229, 255, 0.5);
        width: 70px !important; height: 70px !important;
        padding-top: 10px !important; padding-left: 5px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# FLUXO DE LOGIN
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_data = {}

if not st.session_state.logged_in:
    st.markdown(f"""
    <div style="text-align:center; margin-top:40px; margin-bottom:20px;">
        <img src="data:image/png;base64,{logo_img}" style="height:50px;">
        <h2 style="color:white; font-family:sans-serif; margin-top:10px;">MYND FINANCE</h2>
    </div>
    """, unsafe_allow_html=True)

    tab_entrar, tab_criar = st.tabs(["ENTRAR", "CRIAR CONTA"])

    with tab_entrar:
        st.markdown('<div class="login-box">', unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Usuário")
            p = st.text_input("Senha", type="password")
            if st.form_submit_button("ACESSAR", use_container_width=True):
                ok, msg, data = autenticar(u, p)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.user_data = data
                    st.rerun()
                else:
                    st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_criar:
        st.markdown('<div class="login-box">', unsafe_allow_html=True)
        with st.form("registro"):
            new_u = st.text_input("Escolha um Usuário (Login)")
            new_n = st.text_input("Seu Nome")
            new_p = st.text_input("Sua Senha", type="password")
            if st.form_submit_button("CRIAR CONTA", use_container_width=True):
                if len(new_p) < 4:
                    st.warning("Senha muito curta.")
                else:
                    ok, msg = registrar(new_u, new_p, new_n)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)

    st.stop()

# ==========================================
# ÁREA LOGADA
# ==========================================
SHEET_ID = st.session_state.user_data.get('sheet_id')


@st.cache_data(ttl=10)
def carregar_dados():
    try:
        creds = get_google_creds()
        client_gs = gspread.authorize(creds)
        sheet = client_gs.open_by_key(SHEET_ID).get_worksheet(0)
        return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()


def salvar_na_nuvem(dados):
    try:
        creds = get_google_creds()
        client_gs = gspread.authorize(creds)
        sheet = client_gs.open_by_key(SHEET_ID).get_worksheet(0)

        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cat = dados.get("categoria")
        if cat == "Compras" and dados.get("local_compra") == "Online": cat = "Compras Online"

        row = [ts, dados.get("item"), dados.get("valor"), cat, dados.get("pagamento"),
               dados.get("local_compra", ""), dados.get("recorrencia", "Único"), "App Nuvem"]
        sheet.append_row(row)
        carregar_dados.clear()
        return True, "Salvo!"
    except Exception as e:
        return False, str(e)


# Clientes IA
api_key = st.secrets.get("OPENAI_API_KEY")
client_ai = OpenAI(api_key=api_key)
try:
    from elevenlabs.client import ElevenLabs

    eleven_key = st.secrets.get("ELEVENLABS_API_KEY")
    client_eleven = ElevenLabs(api_key=eleven_key)
    AUDIO_AVAILABLE = True
except:
    AUDIO_AVAILABLE = False


def transcrever(audio_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as fp:
        fp.write(audio_bytes)
        fp_path = fp.name
    try:
        with open(fp_path, "rb") as audio_file:
            transcript = client_ai.audio.transcriptions.create(model="whisper-1", file=audio_file, language="pt")
        return transcript.text
    except:
        return ""
    finally:
        os.remove(fp_path)


def falar(texto):
    if not AUDIO_AVAILABLE: return None
    try:
        voice_id = "EXAVITQu4vr4xnSDxMaL"
        audio = client_eleven.text_to_speech.convert(voice_id=voice_id, text=texto, model_id="eleven_multilingual_v2")
        return b"".join(chunk for chunk in audio)
    except:
        return None


def processar_gpt(texto):
    if "dados" not in st.session_state: st.session_state.dados = {}
    ctx = f"Dados parciais: {json.dumps(st.session_state.dados, ensure_ascii=False)}"
    prompt = f"""You are Carie (MYND). Extract data. {ctx}. User: "{texto}".
    JSON: {{"item":null,"valor":null,"categoria":null,"pagamento":null,"recorrencia":"Único","local_compra":null,"missing_info":null,"cancelar":false}}
    Rules: 'Compras' needs local_compra. If missing info, ASK in 'missing_info' (Portuguese)."""
    try:
        resp = client_ai.chat.completions.create(model="gpt-4-turbo", messages=[{"role": "system", "content": prompt}],
                                                 response_format={"type": "json_object"})
        return json.loads(resp.choices[0].message.content)
    except:
        return {}


def load_lottieurl(url):
    try:
        return requests.get(url).json()
    except:
        return None


def limpar_moeda(v):
    if isinstance(v, str):
        v = v.replace('R$', '').replace(' ', '')
        if '.' in v and ',' in v:
            v = v.replace('.', '').replace(',', '.')
        elif ',' in v:
            v = v.replace(',', '.')
        return v
    return v


# --- APP START ---
col_h1, col_h2 = st.columns([4, 1])
with col_h1:
    st.markdown(f"""
    <div style="display:flex; align-items:center; margin-bottom:10px;">
        <img src="data:image/png;base64,{logo_img}" style="height:35px; margin-right:10px;">
        <h3 style="color:#00E5FF; margin:0;">MYND Finance</h3>
    </div>
    """, unsafe_allow_html=True)
with col_h2:
    if st.button("SAIR"):
        st.session_state.logged_in = False
        st.session_state.user_data = {}
        st.rerun()

st.caption(f"Usuário: {st.session_state.user_data.get('name', 'Convidado')}")

if "msgs" not in st.session_state:
    st.session_state.msgs = [{"role": "assistant", "content": "Olá! Sou a Carie. Vamos lançar gastos?"}]

tab1, tab2 = st.tabs(["💬 AGENTE", "📊 DASHBOARD"])

with tab1:
    st.markdown(
        f"""<div style="position:fixed; top:0; left:0; width:100%; height:100%; background-image:url('data:image/png;base64,{bg_img}'); background-size:cover; z-index:0; pointer-events:none;"></div>""",
        unsafe_allow_html=True)

    with st.container():
        lottie_robot = load_lottieurl("https://lottie.host/020d5e2e-2e4a-4497-b67e-2f943063f282/Gef2CSQ7Qh.json")
        c1, c2 = st.columns([1, 2])
        with c1:
            if lottie_robot: st_lottie(lottie_robot, height=120, key="robot")
        with c2: st.markdown(
            '<div style="padding-top:20px; position:relative; z-index:10;"><p style="color:#00FF41;">● ONLINE</p></div>',
            unsafe_allow_html=True)

    st.markdown("---")

    with st.container():
        for msg in st.session_state.msgs:
            av = carie_icon_path if msg["role"] == "assistant" else None
            with st.chat_message(msg["role"], avatar=av): st.write(msg["content"])

    st.write("##");
    st.write("##")

    st.markdown('<div class="fixed-mic-wrapper"><div class="mic-btn-style">', unsafe_allow_html=True)
    audio_bytes = audio_recorder(text="", recording_color="#ff0055", neutral_color="#00E5FF", icon_size="2x", key="mic")
    st.markdown('</div></div>', unsafe_allow_html=True)

    if audio_bytes:
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_bytes:
            st.session_state.last_audio = audio_bytes
            with st.spinner("."):
                txt = transcrever(audio_bytes)
            if txt and len(txt) > 2:
                st.session_state.msgs.append({"role": "user", "content": txt})
                dados = processar_gpt(txt)
                if dados.get("cancelar"):
                    st.session_state.dados = {};
                    resp = "Cancelado."
                else:
                    for k, v in dados.items():
                        if v: st.session_state.dados[k] = v
                    falta = dados.get("missing_info")
                    if not falta:
                        if not st.session_state.dados.get("item"):
                            falta = "Item?"
                        elif not st.session_state.dados.get("valor"):
                            falta = "Valor?"
                    if falta:
                        resp = falta
                    else:
                        ok, m = salvar_na_nuvem(st.session_state.dados)
                        if ok:
                            resp = f"Salvo: {st.session_state.dados['item']}"
                            st.session_state.dados = {};
                            st.balloons()
                        else:
                            resp = f"Erro: {m}"
                st.session_state.msgs.append({"role": "assistant", "content": resp})
                mp3 = falar(resp)
                if mp3:
                    b64 = base64.b64encode(mp3).decode()
                    st.markdown(
                        f"""<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>""",
                        unsafe_allow_html=True)
                st.rerun()

with tab2:
    st.markdown('<div style="position:relative; z-index:10;">', unsafe_allow_html=True)
    st_autorefresh(interval=30000)
    df = carregar_dados()
    if not df.empty:
        try:
            cols = df.columns.tolist()
            col_val = next((c for c in cols if "valor" in c.lower()), None)
            col_cat = next((c for c in cols if "categoria" in c.lower()), None)
            if col_val:
                df[col_val] = df[col_val].apply(limpar_moeda)
                df[col_val] = pd.to_numeric(df[col_val], errors='coerce').fillna(0)
                total = df[col_val].sum()
                st.metric("TOTAL GASTO", f"R$ {total:,.2f}")

                if col_cat:
                    fig = px.bar(df.groupby(col_cat)[col_val].sum().reset_index(), x=col_cat, y=col_val,
                                 template="plotly_dark", color_continuous_scale=["#00E5FF", "#FF0055"], color=col_val)
                    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)

                st.dataframe(df.tail(10), use_container_width=True, hide_index=True)
        except:
            st.error("Erro dados")
    else:
        st.info("Planilha vazia.")
    st.markdown('</div>', unsafe_allow_html=True)