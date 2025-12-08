import streamlit as st
import os
import json
import pandas as pd
import tempfile
import requests
import plotly.express as px
from openai import OpenAI
from audio_recorder_streamlit import audio_recorder
from streamlit_lottie import st_lottie
from streamlit_autorefresh import st_autorefresh
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="MYND Finance", page_icon="🤖", layout="wide")

# --- CSS SUPREMO (BLACK PIANO & NEON FIX) ---
st.markdown("""
    <style>
    /* Fundo Geral Totalmente Preto */
    .stApp, .stApp > header, .stApp > footer {
        background-color: #000000 !important;
        color: #e0e0e0;
    }

    /* Remove barras e paddings desnecessários */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }

    /* --- ESTILIZAÇÃO DAS ABAS --- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
        border-bottom: 1px solid #333;
        padding-bottom: 5px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        background-color: #111111;
        border-radius: 8px;
        color: #666;
        font-weight: 600;
        border: 1px solid #222;
        flex-grow: 1; /* Abas ocupam largura total */
        justify-content: center;
    }
    .stTabs [aria-selected="true"] {
        background-color: #000000 !important;
        border: 1px solid #00E5FF !important;
        color: #00E5FF !important;
        box-shadow: 0 0 15px rgba(0, 229, 255, 0.3);
    }

    /* --- CARDS DE MÉTRICAS --- */
    div[data-testid="stMetric"] {
        background-color: #080808;
        border: 1px solid #333;
        padding: 15px;
        border-radius: 16px;
    }
    div[data-testid="stMetricLabel"] { color: #888; font-size: 14px; }
    div[data-testid="stMetricValue"] { color: #00E5FF; font-family: monospace; font-size: 26px; }

    /* --- CORREÇÃO E ESTILO DO GRAVADOR --- */
    iframe[title="audio_recorder_streamlit.audio_recorder"] {
        background-color: transparent !important;
    }
    /* Container do gravador com efeito Neon */
    .mic-container {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 20px;
        border-radius: 50%;
        background: #000;
        box-shadow: 0 0 20px #00E5FF, inset 0 0 20px #00E5FF; /* Brilho Neon Interno e Externo */
        width: fit-content;
        margin: auto;
    }
    </style>
    """, unsafe_allow_html=True)


# --- FUNÇÕES AUXILIARES ---
def load_lottieurl(url: str):
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return None
        return r.json()
    except:
        return None


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
        data = sheet.get_all_records()
        return pd.DataFrame(data)
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
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cat_final = dados.get("categoria")
        if cat_final == "Compras" and dados.get("local_compra") == "Online":
            cat_final = "Compras Online"

        linha = [
            timestamp, dados.get("item"), dados.get("valor"), cat_final,
            dados.get("pagamento"), dados.get("local_compra", ""),
            dados.get("recorrencia", "Único"), "App Nuvem"
        ]
        sheet.append_row(linha)
        carregar_dados.clear()
        return True, "Salvo!"
    except Exception as e:
        return False, str(e)


# --- CLIENTES IA ---
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
client_ai = OpenAI(api_key=api_key)

try:
    from elevenlabs.client import ElevenLabs

    eleven_key = st.secrets.get("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS_API_KEY")
    client_eleven = ElevenLabs(api_key=eleven_key)
    AUDIO_AVAILABLE = True
except:
    AUDIO_AVAILABLE = False


# --- PROCESSAMENTO ---
def transcrever_audio(audio_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as fp:
        fp.write(audio_bytes)
        fp_path = fp.name
    try:
        with open(fp_path, "rb") as audio_file:
            transcript = client_ai.audio.transcriptions.create(model="whisper-1", file=audio_file, language="pt")
        return transcript.text
    except Exception as e:
        return ""
    finally:
        os.remove(fp_path)


def falar_texto(texto):
    if not AUDIO_AVAILABLE: return None
    try:
        voice_id = "EXAVITQu4vr4xnSDxMaL"
        audio_gen = client_eleven.text_to_speech.convert(
            voice_id=voice_id, text=texto, model_id="eleven_multilingual_v2", output_format="mp3_44100_128"
        )
        return b"".join(chunk for chunk in audio_gen)
    except:
        return None


def processar_intencao_gpt(texto):
    if "dados_parciais" not in st.session_state: st.session_state.dados_parciais = {}
    contexto = f"Dados atuais: {json.dumps(st.session_state.dados_parciais, ensure_ascii=False)}"
    prompt = f"""You are MYND CFO. Extract finance data. {contexto}. Phrase: "{texto}".
    JSON REQUIRED: {{"item": null, "valor": null, "categoria": null, "pagamento": null, "recorrencia": "Único", "local_compra": null, "missing_info": null, "cancelar": false}}
    Rules: 'Compras' category needs local_compra. If item, valor or pagamento is missing -> fill missing_info with question in Portuguese."""
    try:
        response = client_ai.chat.completions.create(
            model="gpt-4-turbo", messages=[{"role": "system", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {}


# --- UI PRINCIPAL ---
tab1, tab2 = st.tabs(["🎙️ AGENTE IA", "📊 DASHBOARD"])

with tab1:
    lottie_robot = load_lottieurl("https://lottie.host/020d5e2e-2e4a-4497-b67e-2f943063f282/Gef2CSQ7Qh.json")
    col_a, col_b, col_c = st.columns([1, 3, 1])
    with col_b:
        if lottie_robot: st_lottie(lottie_robot, height=180, key="robot")
        if "last_response" in st.session_state:
            st.markdown(
                f"<div style='text-align:center; color:#00E5FF; margin-bottom:20px;'>{st.session_state.last_response}</div>",
                unsafe_allow_html=True)

    # --- ÁREA DO MICROFONE NEON ---
    st.markdown('<div class="mic-container">', unsafe_allow_html=True)
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ff0055",
        neutral_color="#00E5FF",
        icon_size="5x",
        key="recorder_neon"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if audio_bytes:
        # CORREÇÃO 1: Verifica tamanho do áudio para evitar erro da OpenAI
        if len(audio_bytes) < 8000:
            if "last_response" not in st.session_state or "Segure" not in st.session_state.last_response:
                st.toast("⚠️ Clique rápido demais. Segure para falar.", icon="👆")
        else:
            if "last_audio_processed" not in st.session_state or st.session_state.last_audio_processed != audio_bytes:
                st.session_state.last_audio_processed = audio_bytes

                with st.spinner("Analisando..."):
                    texto_usuario = transcrever_audio(audio_bytes)
                    if texto_usuario and len(texto_usuario) > 2:
                        dados = processar_intencao_gpt(texto_usuario)

                        if dados.get("cancelar"):
                            st.session_state.dados_parciais = {}
                            st.session_state.last_response = "🚫 Operação cancelada."
                        else:
                            for k, v in dados.items():
                                if v: st.session_state.dados_parciais[k] = v

                            falta = dados.get("missing_info")
                            dp = st.session_state.dados_parciais

                            if not falta:
                                if not dp.get("item"):
                                    falta = "O que você comprou?"
                                elif not dp.get("valor"):
                                    falta = "Qual o valor?"

                            if falta:
                                st.session_state.last_response = f"🗣️ {falta}"
                                audio_resp = falar_texto(falta)
                                if audio_resp: st.audio(audio_resp, format="audio/mp3", autoplay=True)
                            else:
                                sucesso, status = salvar_na_nuvem(dp)
                                if sucesso:
                                    msg_final = f"Feito! {dp['item']} de R$ {dp['valor']} salvo."
                                    st.session_state.dados_parciais = {}
                                    st.balloons()
                                    audio_resp = falar_texto(msg_final)
                                    if audio_resp: st.audio(audio_resp, format="audio/mp3", autoplay=True)
                                    st.session_state.last_response = f"✅ {msg_final}"
                                else:
                                    st.error(status)

with tab2:
    count = st_autorefresh(interval=30000, limit=None, key="dashboard_refresh")
    df = carregar_dados()
    if not df.empty:
        try:
            if df['Valor'].dtype == object:
                df['Valor'] = df['Valor'].astype(str).str.replace('R$', '', regex=False).str.replace('.', '',
                                                                                                     regex=False).str.replace(
                    ',', '.', regex=False)
            df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)

            total = df['Valor'].sum()
            col_m1, col_m2 = st.columns(2)
            col_m1.metric("Gasto Total", f"R$ {total:,.2f}")
            col_m2.metric("Lançamentos", len(df))

            st.write("---")
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.caption("POR CATEGORIA")
                fig_cat = px.bar(df.groupby("Categoria")["Valor"].sum().reset_index(), x="Categoria", y="Valor",
                                 color="Valor", color_continuous_scale=["#00E5FF", "#FF0055"], template="plotly_dark")
                fig_cat.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      margin=dict(t=0, b=0, l=0, r=0), coloraxis_showscale=False)
                st.plotly_chart(fig_cat, use_container_width=True)
            with col_g2:
                st.caption("POR PAGAMENTO")
                fig_pag = px.pie(df, names="Pagamento", values="Valor", hole=0.7,
                                 color_discrete_sequence=["#00E5FF", "#FF0055", "#00FF41", "#FF9100"],
                                 template="plotly_dark")
                fig_pag.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
                fig_pag.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pag, use_container_width=True)

            st.caption("EXTRATO RECENTE")
            st.dataframe(df.tail(10).sort_index(ascending=False), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Erro dados: {e}")
    else:
        st.info("Sem dados na planilha.")