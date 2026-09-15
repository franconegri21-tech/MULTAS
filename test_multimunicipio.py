import asyncio
import sys
from scrapers import get_scraper

async def main():
    if len(sys.argv) < 3:
        print("Uso: python test_multimunicipio.py <MUNICIPIO> <PATENTE>")
        print("Ejemplo: python test_multimunicipio.py caba OHC092")
        print("Ejemplo: python test_multimunicipio.py lanus ABC123")
        print("\nMunicipios disponibles:")
        from scrapers import SCRAPERS
        for k in SCRAPERS:
            print(f"  - {k}")
        sys.exit(1)

    municipio = sys.argv[1].lower()
    patente = sys.argv[2]

    try:
        scraper = get_scraper(municipio)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    try:
        resultado = await scraper.consultar_por_patente(patente)

        print("\n" + "="*60)
        print("RESULTADO DE LA CONSULTA")
        print("="*60)
        print(f"Municipio: {resultado.municipio}")
        print(f"Patente: {resultado.patente}")
        print(f"Tiene infracciones: {resultado.tiene_infracciones}")
        print(f"Cantidad: {resultado.cantidad}")
        print(f"Monto total: {resultado.monto_total}")

        if resultado.error:
            print(f"\n❌ Error: {resultado.error}")

        if resultado.observaciones:
            print(f"\n📝 {resultado.observaciones}")

        if resultado.infracciones:
            print(f"\nDetalle de infracciones:")
            print("-"*60)
            for i, inf in enumerate(resultado.infracciones, 1):
                print(f"\n{i}. ACTA: {inf.acta}")
                print(f"   Fecha: {inf.fecha or 'No disponible'} {inf.hora or ''}")
                print(f"   Motivo: {inf.motivo}")
                print(f"   Importe: {inf.importe or 'No disponible'}")
                if inf.importe_descuento:
                    print(f"   DESCUENTO: {inf.descuento_porcentaje}% OFF -> {inf.importe_descuento}")
                if inf.punto_rojo:
                    print(f"   ⚠️ PUNTO ROJO")
                print(f"   Estado: {inf.estado.value}")

        print("\n" + "="*60)
        print("Consulta finalizada")

    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
