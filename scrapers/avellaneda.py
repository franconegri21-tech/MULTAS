import os
import requests
import urllib3
from datetime import datetime
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class AvellanedaScraper(BaseScraper):
    MUNICIPIO = "avellaneda"
    NOMBRE = "Municipio de Avellaneda"
    API_URL = "https://siac.mda.gob.ar/api/externo/consultar"

    def __init__(self):
        self.debug_dir = "debug_avellaneda"
        os.makedirs(self.debug_dir, exist_ok=True)

    def _parsear_multas(self, multas_raw):
        infracciones = []
        monto_total_acumulado = 0.0
        hoy = datetime.now()

        for m in multas_raw:
            importe_actual = float(m.get("importe", 0.0))
            monto_total_acumulado += importe_actual
            
            es_interna = m.get("interna", False)
            fecha_vto_desc_str = m.get("FECHA_VTO_DESC")
            motivo_texto = str(m.get("DESCRIPCION", ""))
            
            tiene_descuento_activo = False
            fecha_desc_fmt = None

            # 1. Caso Actas Internas (Traen objeto estructurado con fechas)
            if es_interna and fecha_vto_desc_str:
                try:
                    fecha_desc_dt = datetime.strptime(str(fecha_vto_desc_str).split(" ")[0], "%d/%m/%Y")
                    fecha_desc_fmt = fecha_desc_dt.strftime("%d/%m/%Y")
                    if fecha_desc_dt >= hoy:
                        tiene_descuento_activo = True
                except Exception:
                    pass

            # 2. Caso Actas Externas (API SIAC devuelve importe con 50% ya aplicado para actas en pago voluntario)
            elif not es_interna:
                # Si el importe no es tarifa plena de senda o semáforo sin desc, tiene pago voluntario activo
                # Exceso de velocidad (150 UF desc = $170.325)
                if "velocidad" in motivo_texto.lower() or importe_actual == 170325.0:
                    tiene_descuento_activo = True

            monto_str = f"${importe_actual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            if tiene_descuento_activo:
                monto_str = f"{monto_str} (50% Descuento Aplicado)"
                if fecha_desc_fmt:
                    motivo_texto += f" [PAGO VOLUNTARIO VIGENTE hasta {fecha_desc_fmt}]"
                else:
                    motivo_texto += " [PAGO VOLUNTARIO VIGENTE]"
            else:
                monto_str = f"{monto_str} (Monto Pleno)"
                if fecha_desc_fmt:
                    motivo_texto += f" [PAGO VOLUNTARIO VENCIDO el {fecha_desc_fmt}]"
                else:
                    motivo_texto += " [SIN DESCUENTO VIGENTE]"

            infracciones.append(Infraccion(
                acta=str(m.get("NRO_ACTA", "S/N")),
                fecha=str(m.get("FECHA", "")),
                motivo=motivo_texto,
                importe=monto_str,
                estado=EstadoActa.PENDIENTE,
                juzgado=str(m.get("juzgadoNombre", ""))
            ))

        return infracciones, monto_total_acumulado

    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        try:
            print(f"\nMunicipio: {self.MUNICIPIO}")
            print(f"Patente: {patente.upper()}")
            print("=" * 60)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Origin": "https://multas.mda.gob.ar",
                "Referer": "https://multas.mda.gob.ar/"
            }

            payload = {
                "buscarPor": "PATENTE",
                "parametroBusqueda": patente.upper()
            }

            res = requests.post(self.API_URL, json=payload, headers=headers, timeout=15, verify=False)
            if res.status_code != 200:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    error=f"Respuesta API inválida (Status {res.status_code})",
                    tiene_infracciones=False
                )

            data = res.json()
            multas_raw = data.get("multas", [])
            infracciones, monto_total_acumulado = self._parsear_multas(multas_raw)

            tiene = len(infracciones) > 0
            monto_str = f"${monto_total_acumulado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if tiene else "$0,00"

            return ResultadoConsulta(
                municipio=self.MUNICIPIO,
                patente=patente.upper(),
                tiene_infracciones=tiene,
                cantidad=len(infracciones),
                monto_total=monto_str,
                infracciones=infracciones
            )

        except Exception as e:
            return ResultadoConsulta(
                municipio=self.MUNICIPIO,
                patente=patente.upper(),
                error=str(e),
                tiene_infracciones=False
            )

    async def consultar_por_dni(self, dni: str, tipo_doc: str = "DNI") -> ResultadoConsulta:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Origin": "https://multas.mda.gob.ar",
                "Referer": "https://multas.mda.gob.ar/"
            }

            payload = {
                "buscarPor": "DNI",
                "parametroBusqueda": str(dni).strip()
            }

            res = requests.post(self.API_URL, json=payload, headers=headers, timeout=15, verify=False)
            if res.status_code != 200:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    dni=dni,
                    error=f"Respuesta API inválida (Status {res.status_code})",
                    tiene_infracciones=False
                )

            data = res.json()
            multas_raw = data.get("multas", [])
            infracciones, monto_total_acumulado = self._parsear_multas(multas_raw)

            tiene = len(infracciones) > 0
            monto_str = f"${monto_total_acumulado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if tiene else "$0,00"

            return ResultadoConsulta(
                municipio=self.MUNICIPIO,
                dni=dni,
                tiene_infracciones=tiene,
                cantidad=len(infracciones),
                monto_total=monto_str,
                infracciones=infracciones
            )
        except Exception as e:
            return ResultadoConsulta(
                municipio=self.MUNICIPIO,
                dni=dni,
                error=str(e),
                tiene_infracciones=False
            )

    async def close(self):
        pass