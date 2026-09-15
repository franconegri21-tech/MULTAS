from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Any


class EstadoActa(Enum):
    PENDIENTE = "PENDIENTE"
    PAGADA = "PAGADA"
    VENCIDA = "VENCIDA"
    PUNTO_ROJO = "PUNTO ROJO"
    PAGO_VOLUNTARIO = "PAGO VOLUNTARIO"
    RESOLVER_UACF = "RESOLVER UACF"
    NO_DISPONIBLE = "NO DISPONIBLE"
    # Estados de PBA
    CON_DEUDA = "CON DEUDA"
    SENTENCIA = "SENTENCIA"
    EN_FECHA = "EN FECHA"


@dataclass
class Infraccion:
    acta: str
    motivo: str
    importe: Optional[str] = None
    importe_descuento: Optional[str] = None
    descuento_porcentaje: Optional[int] = None
    lugar: Optional[str] = None
    fecha: Optional[str] = None
    hora: Optional[str] = None
    estado: EstadoActa = EstadoActa.PENDIENTE
    punto_rojo: bool = False
    observaciones: Optional[str] = None


@dataclass
class ResultadoConsulta:
    municipio: str
    patente: Optional[str] = None
    dni: Optional[str] = None
    tiene_infracciones: bool = False
    cantidad: int = 0
    monto_total: Optional[str] = None
    infracciones: List[Infraccion] = field(default_factory=list)
    error: Optional[str] = None
    observaciones: Optional[str] = None
    raw_data: Any = None
