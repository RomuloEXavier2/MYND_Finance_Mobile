import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os

# Configuração de acesso
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
CREDENTIALS_FILE = "credentials.json"
SHEET_NAME = "MYND_Finance_Bot"  # O nome exato da sua planilha no Google


def conectar_planilha():
    if not os.path.exists(CREDENTIALS_FILE):
        print("❌ Erro: credentials.json não encontrado.")
        return None

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
        client = gspread.authorize(creds)
        # Abre a planilha e seleciona a primeira aba (índice 0)
        sheet = client.open(SHEET_NAME).get_worksheet(0)
        return sheet
    except Exception as e:
        print(f"❌ Erro ao conectar no Google Sheets: {e}")
        return None


def salvar_gasto(dados_json):
    """
    Recebe o JSON: {"item": "Coxinha", "valor": 8.50, "categoria": "Lanche", ...}
    Salva na planilha.
    """
    sheet = conectar_planilha()
    if not sheet:
        return False, "Erro de conexão com a planilha."

    try:
        # Prepara a linha para salvar
        # Colunas: Data/Hora | Item | Valor | Categoria | Pagamento | Local Compra | Recorrência | Status
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # Se a categoria for "Compras" e tiver local_compra, ajusta a categoria
        categoria = dados_json.get("categoria", "Compras")
        local_compra = dados_json.get("local_compra", "")

        # Se for compra online, muda a categoria
        if categoria == "Compras" and local_compra == "Online":
            categoria_final = "Compras Online"
        elif categoria == "Compras" and local_compra == "Loja Física":
            categoria_final = "Compras"
        else:
            categoria_final = categoria

        linha = [
            timestamp,
            dados_json.get("item", ""),
            dados_json.get("valor", 0.0),
            categoria_final,
            dados_json.get("pagamento", "Débito"),
            local_compra,  # Nova coluna
            dados_json.get("recorrencia", "Único"),
            "Confirmado"
        ]

        # Adiciona a linha no final da planilha
        sheet.append_row(linha)

        print(f"✅ Salvo: {linha}")
        return True, "Gasto salvo com sucesso!"

    except Exception as e:
        print(f"❌ Erro ao salvar: {e}")
        return False, f"Erro ao salvar: {e}"