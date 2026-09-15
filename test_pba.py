import asyncio
import os
import sys

# Asegurar la ruta raíz en sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scrapers.pba import PbaScraper
import config

async def main():
    print(f"API Key detectada en config: '{config.TWOCAPTCHA_API_KEY}'")
    scraper = PbaScraper()
    resultado = await scraper.consultar_por_patente("AB958NA")
    
    print("\n--- RESULTADO PBA ---")
    print(f"Tiene infracciones: {resultado.tiene_infracciones}")
    print(f"Error: {resultado.error}")
    print(f"Cantidad: {resultado.cantidad}")
    print(f"Monto total: {resultado.monto_total}")

if __name__ == "__main__":
    asyncio.run(main())