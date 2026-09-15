from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class EstadoActa(str, Enum):
    PENDIENTE = "pendiente"
    PAGO_VOLUNTARIO = "pago_voluntario"
    RESOLVER_UACF = "resolver_uacf"
    PUNTO_ROJO = "punto_rojo"
    PAGADA = "pagada"
    NO_DISPONIBLE = "no_disponible"
    VENCIDA = "vencida"
    CON_DEUDA = "con_deuda"
    SENTENCIA = "sentencia"
    EN_FECHA = "en_fecha"

class Infraccion(BaseModel):
    acta: str
    fecha: Optional[str] = None
    hora: Optional[str] = None
    motivo: str
    importe: Optional[str] = None
    importe_descuento: Optional[str] = None
    descuento_porcentaje: Optional[int] = None
    estado: EstadoActa = EstadoActa.PENDIENTE
    punto_rojo: bool = False
    lugar: Optional[str] = None
    observaciones: Optional[str] = None

class ResultadoConsulta(BaseModel):
    municipio: str
    patente: Optional[str] = None
    dni: Optional[str] = None
    tiene_infracciones: bool = False
    cantidad: int = 0
    monto_total: Optional[str] = None
    infracciones: List[Infraccion] = []
    error: Optional[str] = None
    observaciones: Optional[str] = None
