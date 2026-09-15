from abc import ABC, abstractmethod
from models import ResultadoConsulta

class BaseScraper(ABC):
    MUNICIPIO: str = ""
    NOMBRE: str = ""
    URL: str = ""

    @abstractmethod
    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        pass

    @abstractmethod
    async def consultar_por_dni(self, dni: str, tipo_doc: str = "DNI") -> ResultadoConsulta:
        pass

    @abstractmethod
    async def close(self):
        pass
