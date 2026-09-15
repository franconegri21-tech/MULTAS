from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
import asyncio
from scrapers import get_scraper
from models import ResultadoConsulta

app = FastAPI(
    title="Consulta de Infracciones Argentina",
    description="API para consultar infracciones de tránsito en múltiples municipios",
    version="1.0.0"
)

class ConsultaRequest(BaseModel):
    municipio: str
    patente: Optional[str] = None
    dni: Optional[str] = None
    tipo_doc: Optional[str] = "DNI"

@app.get("/")
def root():
    from scrapers import SCRAPERS
    return {
        "mensaje": "API de Consulta de Infracciones",
        "municipios_disponibles": list(SCRAPERS.keys())
    }

@app.post("/consultar", response_model=ResultadoConsulta)
async def consultar(req: ConsultaRequest):
    scraper = get_scraper(req.municipio)

    if req.patente:
        return await scraper.consultar_por_patente(req.patente)
    elif req.dni:
        return await scraper.consultar_por_dni(req.dni, req.tipo_doc)
    else:
        return ResultadoConsulta(
            municipio=req.municipio,
            error="Debe proporcionar patente o DNI",
            tiene_infracciones=False
        )

@app.get("/municipios")
def listar_municipios():
    from scrapers import SCRAPERS
    return {"municipios": list(SCRAPERS.keys())}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
