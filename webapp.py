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
from streamlit_autorefresh import st_autorefresh
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="MYND Finance", page_icon="assets/logo_header.png", layout="wide")


# --- FUNÇÕES DE IMAGEM (BASE64) ---
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()


def get_img_tag(png_file, width, height):
    bin_str = get_base64_of_bin_file(png_file)
    return f'<img src="data:image/png;base64,{bin_str}" width="{width}" height="{height}" style="border-radius:50%">'


# Carrega Assets (Verificação de segurança)
try:
    bg_img = get_base64_of_bin_file("assets/bg_mobile.png")
    carie_img = get_base64_of_bin_file("assets/carie.png")
    logo_img = get_base64_of_bin_file("assets/logo_header.png")
except:
    st.error("⚠️ ERRO: Imagens não encontradas na pasta 'assets'. Verifique os nomes.")
    st.stop()

# --- CSS PRO (INTERFACE IDÊNTICA À IMAGEM) ---
st.markdown(f"""
    <style>
    /* 1. FUNDO DA TELA COM LOGO DA MYND */
    .stApp {{
        background-image: url("data:image/png;base64,{bg_img}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    /* Remove elementos padrão do Streamlit */
    header, footer {{visibility: hidden;}}
    .block-container {{
        padding-top: 10px;
        padding-bottom: 150px; /* Espaço para o mic no fim */
        padding-left: 10px;
        padding-right: 10px;
    }}

    /* 2. CABEÇALHO MYND */
    .mynd-header {{
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 20px;
        padding-top: 20px;
    }}
    .mynd-header img {{
        height: 40px;
        margin-right: 10px;
    }}
    .mynd-header h1 {{
        color: #00E5FF; /* Azul MYND */
        font-family: 'Arial', sans-serif;
        font-weight: bold;
        font-size: 24px;
        margin: 0;
        text-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
    }}

    /* 3. CHAT BUBBLES (Personalizados) */
    .chat-row {{
        display: flex;
        align-items: flex-start; /* Alinha no topo */
        margin-bottom: 15px;
        width: 100%;
    }}

    .chat-avatar {{
        width: 50px;
        height: 50px;
        border-radius: 50%;
        margin-right: 10px;
        flex-shrink: 0;
        border: 2px solid #00E5FF;
        box-shadow: 0 0 10px rgba(0,229,255,0.3);
        background-image: url("data:image/png;base64,{carie_img}");
        background-size: cover;
    }}

    .bubble {{
        padding: 15px;
        border-radius: 20px;
        font-family: 'Verdana', sans-serif;
        font-size: 14px;
        line-height: 1.4;
        max-width: 80%;
        position: relative;
    }}

    /* Estilo da Carie (Azul Transparente 70%) */
    .bubble-carie {{
        background-color: rgba(30, 144, 255, 0.7); /* Azul com transparencia */
        color: #000000; /* Texto Preto para contraste */
        border-top-left-radius: 0; /* Ponta do balão */
        border: 1px solid rgba(255,255,255,0.2);
        font-weight: 600;
        backdrop-filter: blur(5px);
    }}

    /* Estilo do Usuário (Minimalista Escuro) */
    .bubble-user {{
        background-color: rgba(20, 20, 20, 0.8);
        color: #ffffff;
        border-top-right-radius: 0;
        margin-left: auto; /* Joga para a direita */
        border: 1px solid #333;
    }}

    /* 4. MICROFONE FIXO NO RODAPÉ */
    .mic-container {{
        position: fixed;
        bottom: 30px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 999;
        background: transparent;
    }}

    /* Ajuste para o componente de áudio ficar transparente */
    iframe[title="audio_recorder_streamlit.audio_recorder"] {{
        background-color: transparent !important;
        border: none !important;
    }}

    </style>
    """, unsafe_allow_html=True)


# --- CACHE E DADOS ---
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
        return True, "Salvo com sucesso!"
    except Exception as e:
        return False, str(e)


# --- INTELIGÊNCIA ---
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
client_ai = OpenAI(api_key=api_key)

try:
    from elevenlabs.client import ElevenLabs

    eleven_key = st.secrets.get("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS_API_KEY")
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
    ctx = f"Dados atuais: {json.dumps(st.session_state.dados, ensure_ascii=False)}"
    prompt = f"""You are Carie, from MYND Finance. Extract data. {ctx}. Phrase: "{texto}".
    JSON: {{"item":null,"valor":null,"categoria":null,"pagamento":null,"recorrencia":"Único","local_compra":null,"missing_info":null,"cancelar":false}}
    Rules: 'Compras' needs local_compra. If missing info, ask in Portuguese inside 'missing_info'."""
    try:
        resp = client_ai.chat.completions.create(model="gpt-4-turbo", messages=[{"role": "system", "content": prompt}],
                                                 response_format={"type": "json_object"})
        return json.loads(resp.choices[0].message.content)
    except:
        return {}


# --- LÓGICA DE SESSÃO ---
if "mensagens" not in st.session_state:
    st.session_state.mensagens = [
        {"role": "carie", "content": "Olá, eu sou a Carie, tudo bem?"},
        {"role": "carie", "content": "Sou sua assistente financeira."}
    ]
if "dados" not in st.session_state:
    st.session_state.dados = {}

# --- RENDERIZAÇÃO DA INTERFACE ---

# 1. Cabeçalho Personalizado
st.markdown(f"""
<div class="mynd-header">
    <img src="data:image/png;base64,{logo_img}">
    <h1>MYND Finance</h1>
</div>
""", unsafe_allow_html=True)

# Abas (Invisíveis visualmente, controlam o conteúdo)
tab1, tab2 = st.tabs(["💬 CARIE", "📊 DASHBOARD"])

with tab1:
    # 2. Renderiza Chat (Loop de Mensagens)
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.mensagens:
            if msg["role"] == "carie":
                # Layout Carie (Avatar Esquerda + Balão Azul)
                st.markdown(f"""
                <div class="chat-row">
                    <div class="chat-avatar"></div>
                    <div class="bubble bubble-carie">{msg['content']}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                # Layout Usuário (Balão Escuro Direita)
                st.markdown(f"""
                <div class="chat-row">
                    <div class="bubble bubble-user">{msg['content']}</div>
                </div>
                """, unsafe_allow_html=True)

    # Espaçador para o conteúdo não ficar atrás do microfone
    st.write("##")
    st.write("##")

    # 3. Microfone Fixo no Rodapé
    st.markdown('<div class="mic-container">', unsafe_allow_html=True)
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ff0055",
        neutral_color="#00E5FF",  # Azul Neon da Imagem
        icon_size="4x",  # Tamanho grande como na imagem
        key="mic_carie"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # 4. Processamento Lógico (Invisível)
    if audio_bytes:
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_bytes:
            st.session_state.last_audio = audio_bytes

            # Adiciona mensagem do usuário na hora
            texto_user = transcrever(audio_bytes)
            if texto_user and len(texto_user) > 2:
                st.session_state.mensagens.append({"role": "user", "content": texto_user})
                st.rerun()  # Recarrega para mostrar a fala do usuário

            if texto_user:
                # Processa IA
                dados = processar_gpt(texto_user)

                if dados.get("cancelar"):
                    st.session_state.dados = {}
                    resp_carie = "Tudo bem, cancelei a operação."
                else:
                    # Atualiza dados parciais
                    for k, v in dados.items():
                        if v: st.session_state.dados[k] = v

                    falta = dados.get("missing_info")
                    dp = st.session_state.dados

                    # Validacao Local
                    if not falta:
                        if not dp.get("item"):
                            falta = "O que você comprou?"
                        elif not dp.get("valor"):
                            falta = "Qual foi o valor?"

                    if falta:
                        resp_carie = falta
                    else:
                        sucesso, status = salvar_na_nuvem(dp)
                        if sucesso:
                            resp_carie = f"Pronto! Lancei {dp['item']} de R$ {dp['valor']}."
                            st.session_state.dados = {}  # Limpa para o próximo
                        else:
                            resp_carie = f"Tive um erro: {status}"

                # Adiciona resposta da Carie e Toca Áudio
                st.session_state.mensagens.append({"role": "carie", "content": resp_carie})
                audio_resp = falar(resp_carie)
                if audio_resp:
                    st.audio(audio_resp, format="audio/mp3", autoplay=True)

                st.rerun()

# --- ABA DASHBOARD (Mantive o Plotly Neon que ficou bom) ---
with tab2:
    st_autorefresh(interval=30000, key="dash_refresh")
    df = carregar_dados()
    if not df.empty:
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)
        total = df['Valor'].sum()

        st.markdown(f"<h1 style='text-align:center; color:#00E5FF'>R$ {total:,.2f}</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#888'>Gasto Total Acumulado</p>", unsafe_allow_html=True)

        fig = px.bar(df.groupby("Categoria")["Valor"].sum().reset_index(), x="Categoria", y="Valor",
                     color="Valor", template="plotly_dark", color_continuous_scale=["#00E5FF", "#FF0055"])
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Ainda não tenho dados para mostrar.")