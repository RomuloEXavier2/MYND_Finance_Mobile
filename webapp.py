import streamlit as st
import os
import json
import pandas as pd
import tempfile
import requests
import plotly.express as px
import plotly.graph_objects as go
from openai import OpenAI
from pathlib import Path
from audio_recorder_streamlit import audio_recorder
from streamlit_lottie import st_lottie
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="MYND Finance", page_icon="🤖", layout="wide")

# --- CSS AVANÇADO (ESTÉTICA BLACK PIANO & NEON) ---
st.markdown("""
    <style>
    /* Fundo Geral */
    .stApp {
        background-color: #000000;
        color: #e0e0e0;
    }

    /* Remove barras do Streamlit */
    header {visibility: hidden;}
    footer {visibility: hidden;}

    /* Estilização das Abas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #111111;
        border-radius: 4px 4px 0px 0px;
        color: #ffffff;
        font-weight: bold;
    }
    .stTabs [aria-selected="true"] {
        background-color: #000000;
        border-bottom: 2px solid #00E5FF;
        color: #00E5FF;
    }

    /* Cards de Métricas */
    div[data-testid="stMetric"] {
        background-color: #0a0a0a;
        border: 1px solid #333;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 229, 255, 0.05);
    }
    div[data-testid="stMetricLabel"] {
        color: #888;
    }
    div[data-testid="stMetricValue"] {
        color: #00E5FF;
        font-family: 'Courier New', monospace;
    }

    /* Centralizar Gravador */
    .audio-rec-wrapper {
        display: flex;
        justify_content: center;
        margin-top: 20px;
    }
    </style>
    """, unsafe_allow_html=True)


# --- FUNÇÕES AUXILIARES ---
def load_lottieurl(url: str):
    r = requests.get(url)
    if r.status_code != 200: return None
    return r.json()


# Cache do Google Sheets
@st.cache_resource
def get_google_sheet_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # Tenta Secrets (Nuvem) ou Local
    if "GOOGLE_CREDENTIALS" in st.secrets:
        creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)


def salvar_na_nuvem(dados):
    try:
        client_gs = get_google_sheet_client()
        sheet = client_gs.open("MYND_Finance_Bot").get_worksheet(0)
        from datetime import datetime
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        linha = [
            timestamp,
            dados.get("item"),
            dados.get("valor"),
            dados.get("categoria"),
            dados.get("pagamento"),
            dados.get("local_compra", ""),
            dados.get("recorrencia", "Único"),
            "App Nuvem"
        ]
        sheet.append_row(linha)
        return True, "Salvo!"
    except Exception as e:
        return False, str(e)


def carregar_dados():
    try:
        client_gs = get_google_sheet_client()
        sheet = client_gs.open("MYND_Finance_Bot").get_worksheet(0)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()


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


# --- PROCESSO DE ÁUDIO ---
def transcrever_audio(audio_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as fp:
        fp.write(audio_bytes)
        fp_path = fp.name
    try:
        with open(fp_path, "rb") as audio_file:
            transcript = client_ai.audio.transcriptions.create(model="whisper-1", file=audio_file, language="pt")
        return transcript.text
    except Exception as e:
        st.error(f"Erro OpenAI: {e}")
        return ""
    finally:
        os.remove(fp_path)


def falar_texto(texto):
    if not AUDIO_AVAILABLE: return None
    try:
        # Voice ID padrão (Rachel)
        voice_id = "EXAVITQu4vr4xnSDxMaL"
        audio_gen = client_eleven.text_to_speech.convert(
            voice_id=voice_id,
            text=texto,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        return b"".join(chunk for chunk in audio_gen)
    except Exception as e:
        st.error(f"Erro ElevenLabs: {e}")
        return None


def processar_intencao_gpt(texto):
    if "dados_parciais" not in st.session_state:
        st.session_state.dados_parciais = {}

    contexto = f"Dados atuais: {json.dumps(st.session_state.dados_parciais, ensure_ascii=False)}"

    prompt = f"""
    Você é o MYND CFO. Extraia dados. {contexto}. Frase: "{texto}"
    JSON OBRIGATÓRIO: {{"item": null, "valor": null, "categoria": null, "pagamento": null, "recorrencia": "Único", "local_compra": null, "missing_info": null, "cancelar": false}}
    Regras: Categoria 'Compras' exige local_compra. Se faltar item, valor ou pagamento -> preencher missing_info com a pergunta para o usuário.
    """

    try:
        response = client_ai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "system", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        st.error(f"Erro GPT: {e}")
        return {}


# --- INTERFACE ---
tab1, tab2 = st.tabs(["🎙️ AGENTE", "📊 DASHBOARD"])

# --- ABA AGENTE (Minimalista Black Piano) ---
with tab1:
    # Animação do Robô (Lottie)
    # URL de um robô futurista azul/neon
    lottie_robot = load_lottieurl("https://lottie.host/020d5e2e-2e4a-4497-b67e-2f943063f282/Gef2CSQ7Qh.json")

    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        if lottie_robot:
            st_lottie(lottie_robot, height=250, key="robot")

        # Histórico de mensagem rápida (Só a última)
        if "last_response" in st.session_state:
            st.markdown(
                f"<div style='text-align:center; color:#00E5FF; font-size:18px;'>{st.session_state.last_response}</div>",
                unsafe_allow_html=True)

    st.write("---")

    # Área do Microfone (Centralizada e Neon)
    col_mic1, col_mic2, col_mic3 = st.columns([1, 1, 1])
    with col_mic2:
        audio_bytes = audio_recorder(
            text="",
            recording_color="#ff0055",  # Vermelho gravando
            neutral_color="#00E5FF",  # Azul Neon parado
            icon_size="4x",  # Grande destaque
        )

    # Processamento Lógico
    if audio_bytes:
        if "last_audio_processed" not in st.session_state or st.session_state.last_audio_processed != audio_bytes:
            st.session_state.last_audio_processed = audio_bytes

            with st.spinner("Processando..."):
                texto_usuario = transcrever_audio(audio_bytes)

                if texto_usuario:
                    dados = processar_intencao_gpt(texto_usuario)

                    if dados.get("cancelar"):
                        st.session_state.dados_parciais = {}
                        msg_final = "Operação cancelada."
                        st.session_state.last_response = msg_final
                    else:
                        # Atualiza memória
                        for k, v in dados.items():
                            if v: st.session_state.dados_parciais[k] = v

                        # Verifica se FALTA algo
                        falta = dados.get("missing_info")

                        # Validação local extra
                        dp = st.session_state.dados_parciais
                        if not falta:
                            if not dp.get("item"):
                                falta = "O que você comprou?"
                            elif not dp.get("valor"):
                                falta = "Qual o valor?"

                        if falta:
                            # FALTA INFO: Tocar áudio perguntando
                            msg_final = falta
                            st.session_state.last_response = f"⚠️ {falta}"
                            audio_resp = falar_texto(falta)
                            if audio_resp:
                                st.audio(audio_resp, format="audio/mp3", autoplay=True)
                        else:
                            # TUDO CERTO: Salvar
                            sucesso, status = salvar_na_nuvem(dp)
                            if sucesso:
                                msg_final = f"Feito! {dp['item']} de R$ {dp['valor']} salvo."
                                st.session_state.dados_parciais = {}
                                st.balloons()

                                # Tocar áudio de sucesso
                                audio_resp = falar_texto(msg_final)
                                if audio_resp:
                                    st.audio(audio_resp, format="audio/mp3", autoplay=True)

                                st.session_state.last_response = f"✅ {msg_final}"
                            else:
                                st.error(status)

# --- ABA DASHBOARD (Estilo da Imagem Black) ---
with tab2:
    if st.button("🔄 Atualizar"): st.cache_data.clear()

    df = carregar_dados()
    if not df.empty:
        try:
            # Tratamento de dados
            df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)

            # --- Métrica de Topo ---
            total = df['Valor'].sum()
            col_m1, col_m2 = st.columns(2)
            col_m1.metric("Saldo Total", f"R$ {total:,.2f}", "+2%")
            col_m2.metric("Transações", len(df))

            st.write("---")

            # --- Layout de Gráficos (Plotly Black Piano) ---
            col_g1, col_g2 = st.columns(2)

            with col_g1:
                st.caption("GASTOS POR CATEGORIA")
                fig_cat = px.bar(
                    df.groupby("Categoria")["Valor"].sum().reset_index(),
                    x="Categoria", y="Valor",
                    color="Valor",
                    color_continuous_scale=["#00E5FF", "#00FF41", "#FF0055"],  # Neon Colors
                    template="plotly_dark"
                )
                fig_cat.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_cat, use_container_width=True)

            with col_g2:
                st.caption("FORMAS DE PAGAMENTO")
                fig_pag = px.pie(
                    df, names="Pagamento", values="Valor",
                    hole=0.5,  # Donut
                    color_discrete_sequence=["#00E5FF", "#FF0055", "#FF9100", "#00FF41"],
                    template="plotly_dark"
                )
                fig_pag.update_layout(paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_pag, use_container_width=True)

            # Tabela
            st.caption("HISTÓRICO RECENTE")
            st.dataframe(
                df.tail(5).sort_index(ascending=False),
                use_container_width=True,
                hide_index=True
            )

        except Exception as e:
            st.error(f"Erro ao gerar gráficos: {e}")
    else:
        st.info("Sem dados.")