"""Ponto de entrada ASGI: ``uvicorn sistemacampero.interfaces.api.main:app``."""

from dotenv import load_dotenv

from sistemacampero.interfaces.api.app import create_app

load_dotenv()  # lê o .env local (em produção use variáveis de ambiente do provedor)
app = create_app()
