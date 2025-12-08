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


# --- FUNÇÕES DE IMAGEM ---
def get_base64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return ""


# Carrega Imagens (Cache simples para não recarregar disco toda vez)
bg_img = get_base64_of_bin_file("assets/bg_mobile.png")
carie_img = get_base64_of_bin_file("assets/carie.png")
logo_img = get_base64_of_bin_file("assets/logo_header.png")

# --- CSS SUPREMO (CORRIGIDO E ESTABILIZADO) ---
st.markdown(f"""
    <style>
    /* 1. Fundo Geral Estabilizado (Aplica na raiz do App para não piscar) */
    .stApp {{
        background-color: #000000;
        background-image: url("data:image/png;base64,{bg_img}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}

    /* Remove barras */
    header, footer {{visibility: hidden;}}
    .block-container {{
        padding-top: 10px;
        padding-bottom: 120px;
        padding-left: 5px;
        padding-right: 5px;
    }}

    /* 2. Abas Estilizadas */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        background-color: rgba(0,0,0,0.8); /* Fundo semi-transparente nas abas */
        border-bottom: 1px solid #222;
        padding-bottom: 10px;
        justify-content: center;
        border-radius: 15px;
        margin-bottom: 20px;
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 40px;
        background-color: #111;
        border-radius: 20px;
        color: #666;
        font-size: 14px;
        border: 1px solid #333;
        padding: 0 20px;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: #000 !important;
        border: 1px solid #00E5FF !important;
        color: #00E5FF !important;
        box-shadow: 0 0 10px rgba(0, 229, 255, 0.4);
    }}

    /* 3. Avatar Carie */
    .chat-avatar {{
        width: 55px;
        height: 55px;
        border-radius: 50%;
        margin-right: 12px;
        flex-shrink: 0;
        border: 2px solid #00E5FF;
        box-shadow: 0 0 12px rgba(0,229,255,0.4);
        background-image: url("data:image/png;base64,{carie_img}");
        background-size: cover; 
        background-position: center top; 
        background-repeat: no-repeat;
    }}

    /* 4. Microfone Fixo */
    .fixed-mic-wrapper {{
        position: fixed;
        bottom: 20px;
        left: 0;
        width: 100%;
        display: flex;
        justify-content: center;
        z-index: 9999;
        pointer-events: none;
    }}
    .mic-btn-style {{
        pointer-events: auto;
        background: black;
        border-radius: 50%;
        padding: 10px;
        box-shadow: 0 0 25px #00E5FF;
        border: 2px solid #00E5FF;
    }}

    iframe[title="audio_recorder_streamlit.audio_recorder"] {{
        background: transparent !important;
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


@st.cache_data(ttl=60)  # Aumentei TTL para performance
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
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Erro ao carregar dados: {e}")  # Log no terminal
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


# --- FUNÇÕES AUXILIARES ---
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


def limpar_moeda(valor):
    """Função robusta para limpar formatos de moeda"""
    if isinstance(valor, str):
        # Remove R$, espaços e converte , para .
        v = valor.replace('R$', '').replace(' ', '')
        # Se tiver ponto como milhar (ex: 1.000,00), remove o ponto
        if '.' in v and ',' in v:
            v = v.replace('.', '').replace(',', '.')
        elif ',' in v:
            v = v.replace(',', '.')
        return v
    return valor


def processar_gpt(texto):
    if "dados" not in st.session_state: st.session_state.dados = {}

    # Contexto atual para o GPT saber o que já tem
    ctx = json.dumps(st.session_state.dados, ensure_ascii=False)

    prompt = f"""
    You are Carie, a financial assistant.
    Current Data Context: {ctx}
    User Input: "{texto}"

    Task: Extract financial data. Update the context.
    JSON Output Format:
    {{
        "item": "string or null",
        "valor": "float or null (format as number)",
        "categoria": "string or null",
        "pagamento": "string or null",
        "recorrencia": "Único (default) or Mensal",
        "local_compra": "string or null",
        "missing_info": "string (Question in Portuguese if item, valor or pagamento are missing) or null",
        "cancelar": boolean
    }}
    Rules: 
    1. If user says 'cancelar', set "cancelar": true.
    2. Check 'item', 'valor', 'pagamento'. If any is missing, set 'missing_info' to a polite question asking for it.
    """

    try:
        resp = client_ai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "system", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except:
        return {}


# --- SESSÃO ---
if "msgs" not in st.session_state:
    st.session_state.msgs = [
        {"role": "carie", "content": "Olá, eu sou a Carie! Sou sua assistente financeira."},
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
    # (Removida a div de background que causava flickering - agora está no CSS global)

    # Chat
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

    st.write("##")

    # Microfone
    st.markdown('<div class="fixed-mic-wrapper"><div class="mic-btn-style">', unsafe_allow_html=True)
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ff0055",
        neutral_color="#00E5FF",
        icon_size="3x",
        key="mic_carie"
    )
    st.markdown('</div></div>', unsafe_allow_html=True)

    # Lógica Principal
    if audio_bytes:
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_bytes:
            st.session_state.last_audio = audio_bytes

            with st.spinner("Carie ouvindo..."):
                txt = transcrever(audio_bytes)

            if txt and len(txt) > 2:
                # 1. Registra fala do usuário
                st.session_state.msgs.append({"role": "user", "content": txt})

                # 2. Processa intenção
                dados_gpt = processar_gpt(txt)

                resposta_carie = ""

                if dados_gpt.get("cancelar"):
                    st.session_state.dados = {}
                    resposta_carie = "Tudo bem, cancelei a operação."
                else:
                    # Atualiza estado parcial
                    for k, v in dados_gpt.items():
                        if v and k != "missing_info":
                            st.session_state.dados[k] = v

                    falta = dados_gpt.get("missing_info")

                    if falta:
                        # Se faltar info, a resposta é a pergunta do GPT
                        resposta_carie = falta
                    else:
                        # Se tiver tudo, tenta salvar
                        ok, msg_salvo = salvar_na_nuvem(st.session_state.dados)
                        if ok:
                            item_nome = st.session_state.dados.get('item', 'Item')
                            val_nome = st.session_state.dados.get('valor', '0')
                            resposta_carie = f"Certo! Salvei {item_nome} no valor de {val_nome} reais."
                            st.session_state.dados = {}  # Limpa para próxima
                            st.balloons()
                        else:
                            resposta_carie = f"Houve um erro ao salvar: {msg_salvo}"

                # 3. Adiciona resposta ao chat
                st.session_state.msgs.append({"role": "carie", "content": resposta_carie})

                # 4. GERA AUDIO (Correção Crítica: Ocorre SEMPRE que há resposta)
                mp3 = falar(resposta_carie)
                if mp3:
                    b64 = base64.b64encode(mp3).decode()
                    md = f"""<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>"""
                    st.markdown(md, unsafe_allow_html=True)

                st.rerun()

# --- ABA 2: DASHBOARD ---
with tab2:
    st_autorefresh(interval=30000, key="dash")  # Refresh a cada 30s

    df = carregar_dados()

    # Verificação defensiva de dados
    if not df.empty and 'Valor' in df.columns and 'Categoria' in df.columns:
        try:
            # Limpeza robusta
            df['Valor'] = df['Valor'].apply(limpar_moeda)
            df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)

            total = df['Valor'].sum()

            st.markdown(f"""
            <div style="background:rgba(0,0,0,0.6); border:1px solid #333; padding:20px; border-radius:15px; text-align:center; margin-bottom:20px; backdrop-filter: blur(5px);">
                <span style="color:#888; font-size:14px;">SALDO GASTO TOTAL</span><br>
                <span style="color:#00E5FF; font-size:32px; font-family:monospace; font-weight:bold;">R$ {total:,.2f}</span>
            </div>
            """, unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                # Agrupamento seguro
                df_cat = df.groupby("Categoria")["Valor"].sum().reset_index()
                fig = px.bar(df_cat, x="Categoria", y="Valor",
                             color="Valor", template="plotly_dark", color_continuous_scale=["#00E5FF", "#FF0055"])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  margin=dict(t=30, l=0, r=0, b=0), font=dict(color="#ddd"))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                fig = px.pie(df, names="Pagamento", values="Valor", hole=0.6, template="plotly_dark",
                             color_discrete_sequence=["#00E5FF", "#FF0055", "#00FF41"])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=30, l=0, r=0, b=0), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            # Tabela Recente
            st.markdown("##### Extrato Recente")
            st.dataframe(df.tail(10)[['Data/Hora', 'Item', 'Valor']], use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Erro ao processar gráfico: {e}")
    else:
        st.info("Nenhum dado encontrado ou planilha vazia.")