import asyncio
import sys
from scrapers.caba import CabaScraper

async def main():
    if len(sys.argv) < 2:
        print("Uso: python test_caba.py <PATENTE>")
        print("Ejemplo: python test_caba.py OHC092")
        sys.exit(1)

    patente = sys.argv[1]
    scraper = CabaScraper()

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

        if resultado.infracciones:
            print(f"\nDetalle de infracciones:")
            print("-"*60)
            for i, inf in enumerate(resultado.infracciones, 1):
                print(f"\n{i}. ACTA: {inf.acta}")
                print(f"   Fecha: {inf.fecha or 'No disponible'} {inf.hora or ''}")
                print(f"   Motivo: {inf.motivo}")
                print(f"   Importe: {inf.importe or 'No disponible'}")
                if inf.importe_descuento:
                    print(f"   DESCUENTO PAGO VOLUNTARIO: {inf.descuento_porcentaje}% OFF")
                    print(f"   Importe con descuento: {inf.importe_descuento}")
                if inf.punto_rojo:
                    print(f"   ⚠️ ESTADO: Punto Rojo - Debe resolverse con un controlador de faltas")
                print(f"   Estado: {inf.estado.value}")

        print("\n" + "="*60)
        print("Consulta finalizada")

    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
