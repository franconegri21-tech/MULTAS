import os
import sys
import asyncio
from concurrent.futures import ProcessPoolExecutor
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse
from runner import ConsolidadorInfracciones

# Fijar EventLoopPolicy para Windows para permitir Subprocesses de Playwright
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="Gestor de Infracciones Multi-Jurisdicción")

# Executor de procesos aislado para Playwright
executor = ProcessPoolExecutor(max_workers=2)


def _ejecutar_consulta_sync(patente: str):
    """Función síncrona contenedora que se ejecuta en un proceso independiente."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    consolidador = ConsolidadorInfracciones()
    resultados = asyncio.run(consolidador.consultar_todas(patente))
    ruta_pdf = consolidador.generar_reporte_pdf(patente, resultados)
    return ruta_pdf


HTML_CONTENT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Consulta de Infracciones</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: white; padding: 35px; border-radius: 12px; box-shadow: 0 8px 16px rgba(0,0,0,0.1); width: 100%; max-width: 420px; text-align: center; }
        h2 { color: #1a365d; margin-bottom: 20px; font-size: 22px; }
        input[type="text"] { width: 100%; padding: 12px; margin-bottom: 20px; border: 2px solid #cbd5e0; border-radius: 6px; box-sizing: border-box; font-size: 18px; text-transform: uppercase; text-align: center; font-weight: bold; letter-spacing: 2px; }
        input[type="text"]:focus { border-color: #2b6cb0; outline: none; }
        button { background-color: #2b6cb0; color: white; border: none; padding: 14px 20px; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; font-weight: bold; transition: background 0.3s; }
        button:hover { background-color: #1a365d; }
        
        .loading-container { display: none; margin-top: 20px; }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #2b6cb0; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 10px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .loading-text { font-size: 14px; color: #4a5568; }
    </style>
    <script>
        function mostrarCarga() {
            document.getElementById('btn-submit').style.display = 'none';
            document.getElementById('loading').style.display = 'block';
        }
    </script>
</head>
<body>
    <div class="card">
        <h2>Consulta de Infracciones</h2>
        <form action="/consultar" method="post" onsubmit="mostrarCarga()">
            <input type="text" name="patente" placeholder="AD307EC" required maxlength="9">
            <button id="btn-submit" type="submit">Generar Informe PDF</button>
        </form>
        
        <div id="loading" class="loading-container">
            <div class="spinner"></div>
            <div class="loading-text">Consultando jurisdicciones y resolviendo captchas...<br><small>(Esto puede demorar hasta 1 minuto)</small></div>
        </div>
    </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML_CONTENT


@app.post("/consultar")
async def consultar_patente(patente: str = Form(...)):
    patente_clean = patente.strip().upper()
    loop = asyncio.get_running_loop()

    # Ejecutar en el ProcessPoolExecutor aislado
    ruta_pdf = await loop.run_in_executor(
        executor, 
        _ejecutar_consulta_sync, 
        patente_clean
    )

    return FileResponse(
        path=ruta_pdf,
        filename=os.path.basename(ruta_pdf),
        media_type="application/pdf"
    )