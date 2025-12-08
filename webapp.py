import streamlit as st
import os
import json
import pandas as pd
import tempfile
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from audio_recorder_streamlit import audio_recorder
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="MYND Finance", page_icon="💰", layout="wide")

# CSS para visual "Black Piano" Mobile
st.markdown("""
    <style>
    .stApp {
        background-color: #000000;
        color: #ffffff;
    }
    /* Cards de métricas */
    div[data-testid="stMetric"] {
        background-color: #111;
        border: 1px solid #333;
        padding: 10px;
        border-radius: 10px;
        color: #00e5ff;
    }
    label { color: #fff !important; }
    </style>
    """, unsafe_allow_html=True)


# --- FUNÇÕES DE CONEXÃO ---
# Cache para não conectar toda hora
@st.cache_resource
def get_google_sheet_client():
    # Tenta pegar credenciais dos Secrets (Nuvem) ou Arquivo (Local)
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

    if "GOOGLE_CREDENTIALS" in st.secrets:
        # Modo Nuvem (Streamlit Cloud)
        creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        # Modo Local (PC)
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

    return gspread.authorize(creds)


def carregar_dados():
    try:
        client_gs = get_google_sheet_client()
        sheet = client_gs.open("MYND_Finance_Bot").get_worksheet(0)
        data = sheet.get_all_records()
        df = pd.DataFrame(data)

        # Limpeza básica de dados
        if not df.empty:
            # Converte valor para numérico
            # Remove R$, pontos e troca vírgula por ponto se necessário
            # (Assumindo que já salvamos limpo, mas garantindo)
            pass
        return df
    except Exception as e:
        st.error(f"Erro ao ler planilha: {e}")
        return pd.DataFrame()


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
        return True, "Salvo com sucesso!"
    except Exception as e:
        return False, str(e)


# --- CONFIGURAÇÃO OPENAI ---
# Pega API Key dos Secrets ou Ambiente
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)


# --- PROCESSAMENTO DE ÁUDIO ---
def transcrever_audio(audio_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as fp:
        fp.write(audio_bytes)
        fp_path = fp.name

    try:
        with open(fp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, language="pt"
            )
        return transcript.text
    finally:
        os.remove(fp_path)


def processar_intencao_gpt(texto):
    if "dados_parciais" not in st.session_state:
        st.session_state.dados_parciais = {}

    contexto = f"Dados atuais: {json.dumps(st.session_state.dados_parciais, ensure_ascii=False)}"

    prompt = f"""
    Você é o MYND CFO. Extraia dados. {contexto}. Frase: "{texto}"
    JSON OBRIGATÓRIO: {{"item": null, "valor": null, "categoria": null, "pagamento": null, "recorrencia": "Único", "local_compra": null, "missing_info": null, "cancelar": false}}
    Regras: Categoria 'Compras' exige local_compra. Se faltar item, valor ou pagamento -> missing_info.
    """

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "system", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


# --- UI PRINCIPAL ---
st.title("MYND Finance Mobile")

tab1, tab2 = st.tabs(["🎙️ Inserir Gasto", "📊 Dashboard"])

# --- ABA 1: AGENTE ---
with tab1:
    st.write("### Fale seu gasto:")

    # Gravador (Funciona no Mobile via HTTPS)
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ff0000",
        neutral_color="#00e5ff",
        icon_size="3x",
    )

    if audio_bytes:
        # Check para não reprocessar o mesmo audio
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_bytes:
            st.session_state.last_audio = audio_bytes

            with st.spinner("Ouvindo..."):
                texto = transcrever_audio(audio_bytes)
                st.info(f"Você disse: '{texto}'")

                # Lógica GPT
                dados = processar_intencao_gpt(texto)

                if dados.get("cancelar"):
                    st.session_state.dados_parciais = {}
                    st.warning("Cancelado.")
                else:
                    # Atualiza memória
                    for k, v in dados.items():
                        if v: st.session_state.dados_parciais[k] = v

                    # Verifica falta
                    falta = dados.get("missing_info")

                    # Validação local extra
                    dp = st.session_state.dados_parciais
                    if not falta:
                        if not dp.get("item"):
                            falta = "O que você comprou?"
                        elif not dp.get("valor"):
                            falta = "Qual o valor?"

                    if falta:
                        st.warning(f"⚠️ {falta} (Grave novamente)")
                    else:
                        st.success("Tudo certo! Salvando...")
                        sucesso, msg = salvar_na_nuvem(dp)
                        if sucesso:
                            st.balloons()
                            st.toast(f"Salvo: {dp['item']} - R$ {dp['valor']}")
                            st.session_state.dados_parciais = {}  # Limpa
                        else:
                            st.error(f"Erro: {msg}")

# --- ABA 2: DASHBOARD NATIVO ---
with tab2:
    if st.button("🔄 Atualizar Dados"):
        st.cache_data.clear()  # Limpa cache para pegar dados novos

    df = carregar_dados()

    if not df.empty:
        # Tratamento de dados para gráfico
        # Garante que a coluna Valor seja float
        try:
            # Remove simbolo se houver
            # df['Valor'] = df['Valor'].astype(str).str.replace('R$', '').str.replace(',', '.')
            df['Valor'] = pd.to_numeric(df['Valor'])

            total_gasto = df['Valor'].sum()

            # Card de Resumo
            st.metric("Total Gasto", f"R$ {total_gasto:,.2f}")

            # Gráfico de Barras por Categoria
            st.subheader("Gastos por Categoria")
            chart_data = df.groupby("Categoria")["Valor"].sum()
            st.bar_chart(chart_data, color="#ff0055")

            # Tabela Recente
            st.subheader("Últimos Lançamentos")
            st.dataframe(df.tail(5), use_container_width=True)

        except Exception as e:
            st.warning(f"Erro ao processar gráfico: {e}. Verifique se a coluna 'Valor' na planilha tem apenas números.")
    else:
        st.info("Nenhum dado encontrado na planilha.")