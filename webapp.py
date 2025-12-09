import streamlit as st
import os
import json
import pandas as pd
import tempfile
import base64
import requests
import plotly.express as px
from openai import OpenAI
from pathlib import Path
from audio_recorder_streamlit import audio_recorder
from streamlit_lottie import st_lottie
from streamlit_autorefresh import st_autorefresh
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="MYND Finance", page_icon="assets/logo_header.png", layout="wide")


# --- ASSETS ---
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


# --- FUNÇÕES AUXILIARES ---
def load_lottieurl(url: str):
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200: return None
        return r.json()
    except:
        return None


# --- CSS SUPREMO (COM AJUSTE DE MICROFONE) ---
st.markdown(f"""
    <style>
    /* 1. Fundo Geral */
    .stApp {{
        background-color: #000000 !important;
        color: #e0e0e0;
    }}

    /* Remove elementos padrão */
    header, footer {{visibility: hidden;}}
    .block-container {{
        padding-top: 20px;
        padding-bottom: 150px;
        max-width: 800px;
    }}

    /* 2. Abas Modernas */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 10px;
        background-color: rgba(20,20,20,0.8);
        padding: 10px;
        border-radius: 15px;
        border: 1px solid #333;
        z-index: 10;
        position: relative;
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 40px;
        background-color: transparent;
        color: #888;
        font-weight: 600;
        border: none;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: #111 !important;
        color: #00E5FF !important;
        border-radius: 10px;
        border: 1px solid #00E5FF !important;
    }}

    /* 3. Mensagens de Chat */
    .stChatMessage {{
        background-color: rgba(20, 20, 20, 0.85);
        border: 1px solid #333;
        border-radius: 15px;
        margin-bottom: 10px;
        backdrop-filter: blur(5px);
    }}
    div[data-testid="chatAvatarIcon-user"] {{
        background-color: #00E5FF !important;
        color: black !important;
    }}

    /* 4. MICROFONE FIXO E CENTRALIZADO */
    iframe[title="audio_recorder_streamlit.audio_recorder"] {{
        position: fixed !important;
        bottom: 30px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        z-index: 99999 !important;

        /* Estilo da Bola Neon */
        background-color: #000000 !important;
        border-radius: 50%;
        border: 2px solid #00E5FF;
        box-shadow: 0 0 25px rgba(0, 229, 255, 0.5);

        /* Tamanho fixo do container */
        width: 70px !important;
        height: 70px !important;

        /* AJUSTE FINO DE POSIÇÃO DO ÍCONE */
        /* Mexa nestes valores se ainda estiver torto */
        padding-top: 15px !important;
        padding-left: 10px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- CLIENTES API ---
api_key = st.secrets.get("OPENAI_API_KEY")
client_ai = OpenAI(api_key=api_key)

try:
    from elevenlabs.client import ElevenLabs

    eleven_key = st.secrets.get("ELEVENLABS_API_KEY")
    client_eleven = ElevenLabs(api_key=eleven_key)
    AUDIO_AVAILABLE = True
except:
    AUDIO_AVAILABLE = False


@st.cache_data(ttl=60)
def carregar_dados():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "GOOGLE_CREDENTIALS" in st.secrets:
            creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client_gs = gspread.authorize(creds)
        sheet = client_gs.open("MYND_Finance_Bot").get_worksheet(0)
        return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()


def salvar_na_nuvem(dados):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "GOOGLE_CREDENTIALS" in st.secrets:
            creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client_gs = gspread.authorize(creds)
        sheet = client_gs.open("MYND_Finance_Bot").get_worksheet(0)

        from datetime import datetime
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


# --- FUNÇÕES ---
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


def limpar_moeda(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace(' ', '')
        if '.' in v and ',' in v:
            v = v.replace('.', '').replace(',', '.')
        elif ',' in v:
            v = v.replace(',', '.')
        return v
    return valor


# --- SESSÃO ---
if "msgs" not in st.session_state:
    st.session_state.msgs = [
        {"role": "assistant", "content": "Olá, sou a Carie! 🤖"},
        {"role": "assistant", "content": "Sou sua assistente financeira. Pode falar!"}
    ]

# --- UI HEADER ---
st.markdown(f"""
<div style="display:flex; align-items:center; justify-content:center; margin-bottom:20px;">
    <img src="data:image/png;base64,{logo_img}" style="height:40px; margin-right:15px;">
    <h2 style="color:#FFF; margin:0; font-family:'Roboto', sans-serif; font-weight:300; letter-spacing: 1px;">MYND <span style="color:#00E5FF; font-weight:bold;">Finance</span></h2>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["💬 AGENTE", "📊 DASHBOARD"])

# --- ABA 1: CARIE ---
with tab1:
    # Background Exclusivo
    st.markdown(f"""
    <div style="
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background-image: url('data:image/png;base64,{bg_img}');
        background-size: cover; background-position: center; background-repeat: no-repeat;
        z-index: 0; pointer-events: none;
    "></div>
    """, unsafe_allow_html=True)

    with st.container():
        lottie_robot = load_lottieurl("https://lottie.host/020d5e2e-2e4a-4497-b67e-2f943063f282/Gef2CSQ7Qh.json")
        col_anim, col_info = st.columns([1, 2])
        with col_anim:
            if lottie_robot: st_lottie(lottie_robot, height=120, key="robot")
        with col_info:
            st.markdown("""
            <div style="padding-top:20px; position: relative; z-index: 10;">
                <p style="color:#888; font-size:12px; margin:0;">STATUS DO SISTEMA</p>
                <p style="color:#00FF41; font-size:14px; font-weight:bold;">● ONLINE</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.msgs:
            avatar_icon = carie_icon_path if msg["role"] == "assistant" else None
            with st.chat_message(msg["role"], avatar=avatar_icon):
                st.write(msg["content"])

    st.write("##")
    st.write("##")

    # MICROFONE (Fixo e Centralizado)
    # Reduzi o icon_size para 2x para ele "caber" melhor dentro da bola de 70px
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ff0055",
        neutral_color="#00E5FF",
        icon_size="2x",
        key="mic_main"
    )

    if audio_bytes:
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_bytes:
            st.session_state.last_audio = audio_bytes

            with st.spinner("Ouvindo..."):
                txt = transcrever(audio_bytes)

            if txt and len(txt) > 2:
                st.session_state.msgs.append({"role": "user", "content": txt})
                dados = processar_gpt(txt)
                resp = ""

                if dados.get("cancelar"):
                    st.session_state.dados = {}
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
                        ok, msg = salvar_na_nuvem(st.session_state.dados)
                        if ok:
                            resp = f"Salvo! {st.session_state.dados['item']} de R$ {st.session_state.dados['valor']}."
                            st.session_state.dados = {}
                            st.balloons()
                        else:
                            resp = f"Erro: {msg}"

                st.session_state.msgs.append({"role": "assistant", "content": resp})
                mp3 = falar(resp)
                if mp3:
                    b64 = base64.b64encode(mp3).decode()
                    md = f"""<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>"""
                    st.markdown(md, unsafe_allow_html=True)

                st.rerun()

# --- ABA 2: DASHBOARD ---
with tab2:
    st.markdown('<div style="position:relative; z-index:10;">', unsafe_allow_html=True)
    st_autorefresh(interval=30000, key="dash")

    df = carregar_dados()
    if not df.empty:
        try:
            # Blindagem de Colunas
            cols = df.columns.tolist()
            col_valor = next((c for c in cols if "valor" in c.lower()), None)
            col_categoria = next((c for c in cols if "categoria" in c.lower()), None)
            col_pagamento = next((c for c in cols if "pagamento" in c.lower()), None)

            if col_valor:
                df[col_valor] = df[col_valor].apply(limpar_moeda)
                df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce').fillna(0)
                total = df[col_valor].sum()

                st.markdown(f"""
                <div style="background:rgba(20,20,20,0.8); border:1px solid #333; padding:20px; border-radius:15px; text-align:center; margin-bottom:20px;">
                    <span style="color:#888; font-size:14px;">TOTAL GASTO</span><br>
                    <span style="color:#00E5FF; font-size:32px; font-family:monospace; font-weight:bold;">R$ {total:,.2f}</span>
                </div>
                """, unsafe_allow_html=True)

                c1, c2 = st.columns(2)
                if col_categoria:
                    with c1:
                        fig = px.bar(df.groupby(col_categoria)[col_valor].sum().reset_index(), x=col_categoria,
                                     y=col_valor,
                                     color=col_valor, template="plotly_dark",
                                     color_continuous_scale=["#00E5FF", "#FF0055"])
                        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                          margin=dict(t=30, l=0, r=0, b=0), showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

                if col_pagamento:
                    with c2:
                        fig = px.pie(df, names=col_pagamento, values=col_valor, hole=0.6, template="plotly_dark",
                                     color_discrete_sequence=["#00E5FF", "#FF0055", "#00FF41"])
                        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=30, l=0, r=0, b=0),
                                          showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

            st.markdown("##### Extrato Recente")
            # Mostra colunas seguras
            st.dataframe(df.tail(10), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Erro: {e}")
    else:
        st.info("Sem dados.")

    st.markdown('</div>', unsafe_allow_html=True)