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
    /* Tenta forçar transparência no iframe do componente */
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
        if r.status_code != 200: return None
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
        sheet = client_gs.open("MYND_Finance_Bot").get