import flet as ft
import os
import tempfile
import time
import threading
import json
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

# --- CONFIGURAÇÃO DE AMBIENTE ---
try:
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)
except:
    pass

# Importa o gerenciador de planilha
try:
    from core.sheets_manager import salvar_gasto
except ImportError:
    def salvar_gasto(d):
        return False, "Erro: core/sheets_manager.py não encontrado"

# Configurações de API
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# ElevenLabs (Audio)
AUDIO_AVAILABLE = False
try:
    from elevenlabs.client import ElevenLabs

    eleven_key = os.getenv("ELEVENLABS_API_KEY")
    if eleven_key:
        client_eleven = ElevenLabs(api_key=eleven_key)
        AUDIO_AVAILABLE = True
except:
    pass

# --- CONFIGURAÇÃO DE REDE ---
# URL limpa e direta para evitar erros de sintaxe
DASHBOARD_URL = "http://192.168.15.37:1880/dashboard"


class FinanceApp(ft.Column):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.expand = True
        self.dados_parciais = {}
        self.audio_path = ""

        # --- COMPONENTES NATIVOS ---
        # Definimos aqui para garantir que o Flet detecte o uso
        self.audio_recorder = ft.AudioRecorder(
            audio_encoder=ft.AudioEncoder.WAV,
            on_state_changed=self.handle_audio_state
        )
        self.audio_player = ft.Audio(src="silence.mp3", autoplay=False)

        self.page.overlay.append(self.audio_recorder)
        self.page.overlay.append(self.audio_player)

        # --- UI ---
        self.status_text = ft.Text("Toque para falar", size=16, color="white54", text_align=ft.TextAlign.CENTER)
        self.chat_view = ft.ListView(expand=True, spacing=10, padding=20, auto_scroll=True)

        self.btn_record = ft.Container(
            content=ft.Icon(ft.Icons.MIC, size=40, color="white"),
            width=80, height=80,
            bgcolor=ft.Colors.BLUE_ACCENT,
            border_radius=40,
            alignment=ft.alignment.center,
            on_click=self.toggle_recording,
            shadow=ft.BoxShadow(blur_radius=15, color=ft.Colors.BLUE_ACCENT),
            animate=ft.Animation(200, "easeOut")
        )

        self.controls = [
            ft.Container(
                content=ft.Column([
                    ft.Text("MYND FINANCE", size=26, weight="bold"),
                    ft.Text("Seu CFO Pessoal", size=12, color="white54")
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.only(top=20, bottom=10),
                alignment=ft.alignment.center
            ),
            ft.Divider(color="white10", height=1),
            self.chat_view,
            ft.Container(
                content=ft.Column([
                    self.btn_record,
                    ft.Container(height=15),
                    self.status_text
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.alignment.center,
                padding=20
            )
        ]

    def toggle_recording(self, e):
        if self.audio_recorder.is_recording():
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        self.status_text.value = "Ouvindo..."
        self.status_text.color = "red"
        self.btn_record.bgcolor = "red"
        self.btn_record.scale = 1.1
        self.btn_record.update()
        self.status_text.update()
        self.audio_path = os.path.join(tempfile.gettempdir(), "mynd_rec.wav")
        self.audio_recorder.start_recording(self.audio_path)

    def stop_recording(self):
        self.audio_recorder.stop_recording()
        self.btn_record.bgcolor = ft.Colors.BLUE_ACCENT
        self.btn_record.scale = 1.0
        self.status_text.value = "Processando..."
        self.status_text.color = "yellow"
        self.update()

    def handle_audio_state(self, e):
        if e.data == "stopped":
            time.sleep(0.5)
            self.processar_audio()

    def processar_audio(self):
        try:
            if not os.path.exists(self.audio_path) or os.path.getsize(self.audio_path) < 1000:
                self.falar_resposta("Não ouvi nada.")
                return

            with open(self.audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file, language="pt"
                )
            texto = transcript.text.strip()

            alucinacoes = ["Eaí?", "E aí?", "Amara.org", "Sous-titres", "MBC"]
            if texto in alucinacoes or len(texto) < 2:
                self.falar_resposta("Não entendi. Pode repetir?")
                return

            self.add_message("Você", texto, align="right")
            threading.Thread(target=self.extrair_dados, args=(texto,), daemon=True).start()
        except Exception as e:
            self.falar_resposta("Erro de conexão.")

    def extrair_dados(self, texto):
        contexto_str = ""
        if self.dados_parciais:
            contexto_str = f"Dados parciais: {json.dumps(self.dados_parciais, ensure_ascii=False)}"

        prompt = f"""
        Você é o MYND CFO. Extraia dados financeiros.
        {contexto_str}
        Frase: "{texto}"
        JSON OBRIGATÓRIO: {{"item": null, "valor": null, "categoria": null, "pagamento": null, "recorrencia": "Único", "local_compra": null, "missing_info": null, "cancelar": false}}
        Regras: Categoria "Compras" exige local_compra. Se faltar item, valor ou pagamento -> preencher missing_info.
        """
        try:
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "system", "content": prompt}],
                response_format={"type": "json_object"}
            )
            dados_json = json.loads(response.choices[0].message.content)

            if dados_json.get("cancelar"):
                self.dados_parciais = {}
                self.falar_resposta("Cancelado.")
                return

            for k, v in dados_json.items():
                if v is not None: self.dados_parciais[k] = v

            if not self.dados_parciais.get("categoria"): self.dados_parciais["categoria"] = "Compras"
            if not self.dados_parciais.get("recorrencia"): self.dados_parciais["recorrencia"] = "Único"

            falta = dados_json.get("missing_info")
            if not falta:
                if not self.dados_parciais.get("item"):
                    falta = "O que você comprou?"
                elif not self.dados_parciais.get("valor"):
                    falta = "Qual o valor?"
                elif not self.dados_parciais.get("pagamento"):
                    falta = "Qual o pagamento?"
                elif self.dados_parciais.get("categoria") == "Compras" and not self.dados_parciais.get("local_compra"):
                    falta = "Foi online ou loja física?"

            if falta:
                self.falar_resposta(falta)
            else:
                self.page.run_task(self.update_status, "Salvando...", "yellow")
                sucesso, msg = salvar_gasto(self.dados_parciais)
                if sucesso:
                    self.falar_resposta(f"Salvo! {self.dados_parciais['item']} de {self.dados_parciais['valor']}.")
                    self.dados_parciais = {}
                else:
                    self.falar_resposta(f"Erro ao salvar: {msg}")
        except Exception as e:
            self.falar_resposta("Erro na inteligência.")

    def falar_resposta(self, texto):
        self.add_message("MYND", texto, align="left")
        self.page.run_task(self.update_status, "Toque para falar", "white54")
        if AUDIO_AVAILABLE:
            try:
                audio_gen = client_eleven.text_to_speech.convert(
                    voice_id=os.getenv("VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
                    text=texto,
                    model_id="eleven_multilingual_v2",
                    output_format="mp3_44100_128"
                )
                temp = os.path.join(tempfile.gettempdir(), "resp.mp3")
                with open(temp, "wb") as f:
                    for chunk in audio_gen: f.write(chunk)
                self.audio_player.src = temp
                self.audio_player.update()
                self.audio_player.play()
            except:
                pass

    def add_message(self, user, text, align):
        bg = "#333333" if align == "left" else ft.Colors.BLUE_ACCENT
        self.page.run_task(lambda: self.chat_view.controls.append(
            ft.Row([ft.Container(content=ft.Text(text, color="white"), padding=10, border_radius=10, bgcolor=bg,
                                 width=280)],
                   alignment=ft.MainAxisAlignment.END if align == "right" else ft.MainAxisAlignment.START)
        ))
        self.page.run_task(lambda: self.chat_view.update())
        self.page.run_task(lambda: self.chat_view.scroll_to(offset=-1, duration=300))

    def update_status(self, msg, color):
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.update()


def main(page: ft.Page):
    page.title = "MYND Finance"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.bgcolor = ft.Colors.BLACK

    finance_app = FinanceApp(page)

    # --- DASHBOARD NATIVO ---
    # Se der Unknown Control, o problema é o requirements.txt, não aqui.
    dashboard_webview = ft.WebView(
        url=DASHBOARD_URL,
        expand=True,
        on_web_resource_error=lambda e: print("Erro WebView:", e.description)
    )

    t = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(text="Agente IA", icon=ft.Icons.MIC, content=finance_app),
            ft.Tab(text="Dashboard", icon=ft.Icons.BAR_CHART, content=dashboard_webview),
        ],
        expand=True,
    )
    page.add(t)


if __name__ == "__main__":
    ft.app(target=main)