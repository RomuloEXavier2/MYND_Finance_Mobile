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
# Não precisamos carregar carie_img em base64 para o st.chat_message, usamos o path direto ou Image object
# Mas mantemos aqui caso precise pro CSS
carie_icon_path = "assets/carie.png"
logo_img = get_base64_of_bin_file("assets/logo_header.png")

# --- CSS SUPREMO (REFATORADO PARA DESIGN LIMPO) ---
st.markdown(f"""
    <style>
    /* 1. Fundo Geral */
    .stApp {{
        background-color: #000000;
        background-image: url("data:image/png;base64,{bg_img}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    /* Remove elementos padrão */
    header, footer {{visibility: hidden;}}
    .block-container {{
        padding-top: 20px;
        padding-bottom: 150px; /* Espaço generoso para o mic */
        max-width: 800px; /* Limita largura no PC para parecer app mobile */
    }}

    /* 2. Abas Modernas (Estilo Reference) */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 10px;
        background-color: rgba(0,0,0,0.5);
        padding: 10px;
        border-radius: 15px;
        border: 1px solid #333;
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

    /* 3. Ajuste das Mensagens de Chat (Native) */
    /* Deixa o fundo das mensagens do assistente um pouco mais claro que o fundo */
    .stChatMessage {{
        background-color: rgba(20, 20, 20, 0.8);
        border: 1px solid #333;
        border-radius: 15px;
        margin-bottom: 10px;
    }}
    /* Mensagem do usuário com destaque sutil */
    div[data-testid="chatAvatarIcon-user"] {{
        background-color: #00E5FF !important;
        color: black !important;
    }}

    /* 4. Microfone Flutuante (Design Limpo) */
    .fixed-mic-wrapper {{
        position: fixed;
        bottom: 30px;
        left: 0;
        width: 100%;
        display: flex;
        justify-content: center;
        z-index: 9999;
        pointer-events: none; /* Permite clique através da área vazia */
    }}
    .mic-btn-style {{
        pointer-events: auto;
        background: rgba(0, 0, 0, 0.9); /* Fundo quase preto */
        border-radius: 50%;
        padding: 15px;
        box-shadow: 0 0 30px rgba(0, 229, 255, 0.3); /* Glow Azul Suave */
        border: 2px solid #00E5FF;
        transition: transform 0.2s;
    }}
    .mic-btn-style:active {{
        transform: scale(0.95);
        box-shadow: 0 0 50px rgba(0, 229, 255, 0.6);
    }}

    /* Esconde iframe do gravador */
    iframe[title="audio_recorder_streamlit.audio_recorder"] {{
        background: transparent !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- CLIENTES ---
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
    ctx = f"Dados atuais: {json.dumps(st.session_state.dados, ensure_ascii=False)}"
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

# --- ABA 1: CHAT LIMPO (Reference Style) ---
with tab1:
    # Container para o Robô (Topo, estilo cartão)
    with st.container():
        lottie_robot = load_lottieurl("https://lottie.host/020d5e2e-2e4a-4497-b67e-2f943063f282/Gef2CSQ7Qh.json")
        col_anim, col_info = st.columns([1, 2])
        with col_anim:
            if lottie_robot: st_lottie(lottie_robot, height=120, key="robot")
        with col_info:
            st.markdown("""
            <div style="padding-top:20px;">
                <p style="color:#888; font-size:12px; margin:0;">STATUS DO SISTEMA</p>
                <p style="color:#00FF41; font-size:14px; font-weight:bold;">● ONLINE</p>
                <p style="color:#ccc; font-size:14px;">"Estou ouvindo. Clique abaixo para registrar."</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")  # Divisor sutil

    # Container de Chat (Nativo do Streamlit)
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.msgs:
            # Define o avatar correto
            avatar_icon = carie_icon_path if msg["role"] == "assistant" else None

            with st.chat_message(msg["role"], avatar=avatar_icon):
                st.write(msg["content"])

    # Espaçador
    st.write("##")
    st.write("##")

    # MICROFONE (Fixo embaixo)
    st.markdown('<div class="fixed-mic-wrapper"><div class="mic-btn-style">', unsafe_allow_html=True)
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ff0055",
        neutral_color="#00E5FF",
        icon_size="3x",
        key="mic_main"
    )
    st.markdown('</div></div>', unsafe_allow_html=True)

    # Lógica de Processamento
    if audio_bytes:
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_bytes:
            st.session_state.last_audio = audio_bytes

            # 1. Transcreve
            with st.spinner("Ouvindo..."):
                txt = transcrever(audio_bytes)

            if txt and len(txt) > 2:
                # Adiciona mensagem do usuário na hora
                st.session_state.msgs.append({"role": "user", "content": txt})

                # Processa IA
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
                            resp = f"Salvo: {st.session_state.dados['item']} (R$ {st.session_state.dados['valor']})"
                            st.session_state.dados = {}
                            st.balloons()
                        else:
                            resp = f"Erro: {msg}"

                # Adiciona resposta e toca áudio
                st.session_state.msgs.append({"role": "assistant", "content": resp})
                mp3 = falar(resp)
                if mp3:
                    b64 = base64.b64encode(mp3).decode()
                    md = f"""<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>"""
                    st.markdown(md, unsafe_allow_html=True)

                st.rerun()

# --- ABA 2: DASHBOARD (Mantido igual) ---
with tab2:
    st_autorefresh(interval=30000, key="dash")
    df = carregar_dados()
    if not df.empty:
        try:
            df['Valor'] = df['Valor'].apply(limpar_moeda)
            df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)

            total = df['Valor'].sum()

            st.markdown(f"""
            <div style="background:rgba(20,20,20,0.8); border:1px solid #333; padding:20px; border-radius:15px; text-align:center; margin-bottom:20px;">
                <span style="color:#888; font-size:14px;">TOTAL GASTO</span><br>
                <span style="color:#00E5FF; font-size:32px; font-family:monospace; font-weight:bold;">R$ {total:,.2f}</span>
            </div>
            """, unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                fig = px.bar(df.groupby("Categoria")["Valor"].sum().reset_index(), x="Categoria", y="Valor",
                             color="Valor", template="plotly_dark", color_continuous_scale=["#00E5FF", "#FF0055"])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  margin=dict(t=30, l=0, r=0, b=0), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                fig = px.pie(df, names="Pagamento", values="Valor", hole=0.6, template="plotly_dark",
                             color_discrete_sequence=["#00E5FF", "#FF0055", "#00FF41"])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=30, l=0, r=0, b=0), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("##### Extrato")
            st.dataframe(df.tail(10)[['Data/Hora', 'Item', 'Valor']], use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Erro: {e}")
    else:
        st.info("Sem dados.")