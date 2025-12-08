import flet as ft

def main(page: ft.Page):
    page.title = "MYND Finance - Teste"
    page.add(
        ft.Text("✅ App funcionando!", size=30, weight="bold")
    )

ft.app(target=main)