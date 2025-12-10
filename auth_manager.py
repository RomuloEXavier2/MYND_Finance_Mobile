import requests
import streamlit as st
import uuid


# Pega URL do Firebase dos Secrets
# No secrets.toml deve ter: [FIREBASE] url = "https://SEU-PROJETO.firebaseio.com/"
def get_firebase_url():
    if "FIREBASE" in st.secrets and "url" in st.secrets["FIREBASE"]:
        url = st.secrets["FIREBASE"]["url"]
        if not url.endswith("/"): url += "/"
        return url
    return None


def autenticar_usuario(usuario, senha):
    url_base = get_firebase_url()
    if not url_base:
        return False, "Erro: URL Firebase não configurada.", None

    try:
        # Busca usuário no nó 'usuarios' (Reaproveitando sua estrutura)
        # Nota: Ajuste o caminho se no banco for diferente.
        # Seu código antigo usava: f"{url_base}Academic_Assistant/usuarios/{usuario}.json"
        # Para o Finance, talvez queira separar ou usar o mesmo.
        # Vou assumir que queremos UNIFICAR, então vou buscar na raiz de usuários.

        # Tenta buscar na raiz de usuários (caso você mude a estrutura)
        # Ou ajuste aqui para f"{url_base}Academic_Assistant/usuarios/{usuario}.json" se quiser manter isolado
        endpoint = f"{url_base}usuarios/{usuario}.json"

        response = requests.get(endpoint, timeout=10)

        if response.status_code != 200:
            return False, "Erro de conexão com servidor.", None

        dados = response.json()

        if not dados:
            return False, "Usuário não encontrado.", None

        # Validação
        senha_real = dados.get("senha")
        status = str(dados.get("status", "BLOQUEADO")).upper()

        # Verifica Senha
        if str(senha) != str(senha_real):
            return False, "Senha incorreta.", None

        # Verifica Status
        if status != "ATIVO":
            return False, f"Conta bloqueada (Status: {status}).", None

        # Recupera (ou cria) o ID da Planilha Financeira
        sheet_id = dados.get("finance_sheet_id")

        return True, "Login realizado!", {"sheet_id": sheet_id, "dados": dados}

    except Exception as e:
        return False, f"Erro crítico: {e}", None


def registrar_planilha_usuario(usuario, sheet_id):
    """Salva o ID da planilha criada no perfil do usuário no Firebase"""
    url_base = get_firebase_url()
    if not url_base: return False

    try:
        endpoint = f"{url_base}usuarios/{usuario}.json"
        # Patch atualiza apenas o campo enviado
        requests.patch(endpoint, json={"finance_sheet_id": sheet_id})
        return True
    except:
        return False