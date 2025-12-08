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
carie_img = get_base64_of_bin_file("assets/carie.png")
logo_img = get_base64_of_bin_file("assets/logo_header.png")

# --- CSS GERAL (BLACK PIANO PADRÃO) ---
st.markdown("""
    <style>
    /* 1. Fundo Geral PRETO (Padrão para Dashboard) */
    .stApp {
        background-color: #000000 !important;
        color: #e0e0e0;
    }

    /* Remove barras */
    header, footer {visibility: hidden;}
    .block-container {
        padding-top: 10px;
        padding-bottom: 120px; /* Espaço mic */
        padding-left: 5px;
        padding-right: 5px;
    }

    /* 2. Abas Estilizadas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
        border-bottom: 1px solid #222;
        padding-bottom: 10px;
        justify-content: center;
    }
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        background-color: #111;
        border-radius: 20px;
        color: #666;
        font-size: 14px;
        border: 1px solid #333;
        padding: 0 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #000 !important;
        border: 1px solid #00E5FF !important;
        color: #00E5FF !important;
        box-shadow: 0 0 10px rgba(0, 229, 255, 0.4);
    }

    /* 3. Avatar Carie (Ajuste de Posição) */
    .chat-avatar {
        width: 55px;
        height: 55px;
        border-radius: 50%;
        margin-right: 12px;
        flex-shrink: 0;
        border: 2px solid #00E5FF;
        box-shadow: 0 0 12px rgba(0,229,255,0.4);
        /* CORREÇÃO DA IMAGEM CORTADA */
        background-image: url("data:image/png;base64,%s");
        background-size: cover; 
        background-position: center top; /* Tenta focar no rosto */
        background-repeat: no-repeat;
    }

    /* 4. Microfone Fixo (Centralização Robusta) */
    .fixed-mic-wrapper {
        position: fixed;
        bottom: 20px;
        left: 0;
        width: 100%;
        display: flex;
        justify-content: center; /* Garante centro absoluto */
        z-index: 9999;
        pointer-events: none; /* Deixa clicar atrás se não for no botão */
    }
    .mic-btn-style {
        pointer-events: auto; /* Reativa clique no botão */
        background: black;
        border-radius: 50%;
        padding: 10px;
        box-shadow: 0 0 25px #00E5FF; /* Brilho Neon */
        border: 2px solid #00E5FF;
    }

    /* Esconde background do iframe do gravador */
    iframe[title="audio_recorder_streamlit.audio_recorder"] {
        background: transparent !important;
    }
    </style>
    """ % carie_img, unsafe_allow_html=True)

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


@st.cache_data(ttl=10)
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
        # Tente usar um voice_id diferente se o atual estiver mudo
        voice_id = "EXAVITQu4vr4xnSDxMaL"
        audio = client_eleven.text_to_speech.convert(voice_id=voice_id, text=texto, model_id="eleven_multilingual_v2")
        return b"".join(chunk for chunk in audio)
    except:
        return None


def processar_gpt(texto):
    if "dados" not in st.session_state: st.session_state.dados = {}
    ctx = f"Dados parciais: {json.dumps(st.session_state.dados, ensure_ascii=False)}"
    prompt = f"""You are Carie (MYND Finance). Extract data. {ctx}. User said: "{texto}".
    JSON: {{"item":null,"valor":null,"categoria":null,"pagamento":null,"recorrencia":"Único","local_compra":null,"missing_info":null,"cancelar":false}}
    Rules: 'Compras' needs local_compra. If missing info (item/valor/pagamento), ASK in 'missing_info' (Portuguese)."""
    try:
        resp = client_ai.chat.completions.create(model="gpt-4-turbo", messages=[{"role": "system", "content": prompt}],
                                                 response_format={"type": "json_object"})
        return json.loads(resp.choices[0].message.content)
    except:
        return {}


# --- SESSÃO ---
if "msgs" not in st.session_state:
    st.session_state.msgs = [
        {"role": "carie", "content": "Olá, eu sou a Carie, tudo bem?"},
        {"role": "carie", "content": "Sou sua assistente financeira."}
    ]

# --- UI ---
# Header
st.markdown(f"""
<div style="display:flex; align-items:center; justify-content:center; margin-bottom:10px;">
    <img src="data:image/png;base64,{logo_img}" style="height:35px; margin-right:10px;">
    <h3 style="color:#00E5FF; margin:0; font-family:sans-serif;">MYND Finance</h3>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["💬 CARIE", "📊 DASHBOARD"])

# --- ABA 1: CARIE ---
with tab1:
    # 1. Background APENAS nesta aba (Injeção de Div Fixa)
    # Ajuste de tamanho: background-size: 85% (Reduzido como pediu)
    st.markdown(f"""
    <div style="
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background-image: url('data:image/png;base64,{bg_img}');
        background-size: cover; 
        background-position: center;
        background-repeat: no-repeat;
        z-index: -1;
        opacity: 1;
    "></div>
    """, unsafe_allow_html=True)

    # 2. Chat
    chat_box = st.container()
    with chat_box:
        for msg in st.session_state.msgs:
            if msg["role"] == "carie":
                st.markdown(f"""
                <div style="display:flex; align-items:flex-start; margin-bottom:15px;">
                    <div class="chat-avatar"></div>
                    <div style="
                        background: rgba(0, 50, 100, 0.7);
                        color: #fff;
                        padding: 12px 16px;
                        border-radius: 0 15px 15px 15px;
                        backdrop-filter: blur(4px);
                        border: 1px solid rgba(0, 229, 255, 0.3);
                        font-size: 14px;
                        max-width: 75%;">
                        {msg['content']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="display:flex; justify-content:flex-end; margin-bottom:15px;">
                    <div style="
                        background: rgba(20, 20, 20, 0.9);
                        color: #ddd;
                        padding: 12px 16px;
                        border-radius: 15px 0 15px 15px;
                        border: 1px solid #333;
                        font-size: 14px;
                        max-width: 75%;">
                        {msg['content']}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    st.write("##")  # Espaço

    # 3. Microfone Fixo no Rodapé (Container Flex)
    # A classe 'fixed-mic-wrapper' garante centralização
    st.markdown('<div class="fixed-mic-wrapper"><div class="mic-btn-style">', unsafe_allow_html=True)
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ff0055",
        neutral_color="#00E5FF",
        icon_size="3x",  # Tamanho do ícone
        key="mic_carie"
    )
    st.markdown('</div></div>', unsafe_allow_html=True)

    # Lógica
    if audio_bytes:
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_bytes:
            st.session_state.last_audio = audio_bytes

            with st.spinner("Ouvindo..."):
                txt = transcrever(audio_bytes)

            if txt and len(txt) > 2:
                # Adiciona User
                st.session_state.msgs.append({"role": "user", "content": txt})

                # Processa
                dados = processar_gpt(txt)

                if dados.get("cancelar"):
                    st.session_state.dados = {}
                    resp = "Operação cancelada."
                else:
                    for k, v in dados.items():
                        if v: st.session_state.dados[k] = v

                    falta = dados.get("missing_info")
                    dp = st.session_state.dados

                    if not falta:
                        if not dp.get("item"):
                            falta = "O que você comprou?"
                        elif not dp.get("valor"):
                            falta = "Qual o valor?"

                    if falta:
                        resp = falta
                    else:
                        ok, msg = salvar_na_nuvem(dp)
                        if ok:
                            resp = f"Salvo! {dp['item']} de R$ {dp['valor']}."
                            st.session_state.dados = {}
                            st.balloons()
                        else:
                            resp = f"Erro: {msg}"

                # Resposta Carie
                st.session_state.msgs.append({"role": "carie", "content": resp})

                # Áudio Resposta
                mp3 = falar(resp)
                if mp3:
                    # Autoplay via HTML oculto para garantir execução
                    b64 = base64.b64encode(mp3).decode()
                    md = f"""
                        <audio autoplay="true">
                        <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                        </audio>
                        """
                    st.markdown(md, unsafe_allow_html=True)

                st.rerun()

# --- ABA 2: DASHBOARD (Black Piano Puro) ---
with tab2:
    st_autorefresh(interval=30000, key="dash")
    # Aqui não tem a div de background, então fica preto do stApp

    df = carregar_dados()
    if not df.empty:
        try:
            if df['Valor'].dtype == object:
                df['Valor'] = df['Valor'].astype(str).str.replace('R$', '').str.replace('.', '').str.replace(',', '.')
            df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)

            total = df['Valor'].sum()

            # Card KPI
            st.markdown(f"""
            <div style="background:#080808; border:1px solid #333; padding:20px; border-radius:15px; text-align:center; margin-bottom:20px;">
                <span style="color:#888; font-size:14px;">SALDO TOTAL</span><br>
                <span style="color:#00E5FF; font-size:32px; font-family:monospace; font-weight:bold;">R$ {total:,.2f}</span>
            </div>
            """, unsafe_allow_html=True)

            # Gráficos
            c1, c2 = st.columns(2)
            with c1:
                fig = px.bar(df.groupby("Categoria")["Valor"].sum().reset_index(), x="Categoria", y="Valor",
                             color="Valor", template="plotly_dark", color_continuous_scale=["#00E5FF", "#FF0055"])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  margin=dict(t=30, l=0, r=0, b=0))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                fig = px.pie(df, names="Pagamento", values="Valor", hole=0.6, template="plotly_dark",
                             color_discrete_sequence=["#00E5FF", "#FF0055", "#00FF41"])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=30, l=0, r=0, b=0), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            st.dataframe(df.tail(10)[['Data/Hora', 'Item', 'Valor']], use_container_width=True, hide_index=True)

        except:
            st.error("Erro dados")
    else:
        st.info("Sem dados")