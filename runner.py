import asyncio
import os
from datetime import datetime
from typing import List
from scrapers import get_scraper
from models import ResultadoConsulta

# ReportLab imports
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


class ConsolidadorInfracciones:
    MUNICIPIOS_DISPONIBLES = ["caba", "pba", "lanus", "avellaneda"]

    def __init__(self, municipios: List[str] = None):
        self.municipios = municipios or self.MUNICIPIOS_DISPONIBLES

    async def consultar_municipio(self, municipio: str, patente: str) -> ResultadoConsulta:
        try:
            scraper = get_scraper(municipio)
            if not scraper:
                return ResultadoConsulta(
                    municipio=municipio,
                    patente=patente.upper(),
                    error=f"Scraper no implementado para {municipio}",
                    tiene_infracciones=False
                )
            resultado = await scraper.consultar_por_patente(patente)
            return resultado
        except Exception as e:
            return ResultadoConsulta(
                municipio=municipio,
                patente=patente.upper(),
                error=str(e),
                tiene_infracciones=False
            )

    async def consultar_todas(self, patente: str) -> List[ResultadoConsulta]:
        print(f"\n============================================================")
        print(f"INICIANDO BÚSQUEDA MULTI-JURISDICCIÓN | PATENTE: {patente.upper()}")
        print(f"Jurisdicciones activas: {', '.join(self.municipios)}")
        print(f"============================================================\n")

        tareas = [self.consultar_municipio(m, patente) for m in self.municipios]
        resultados = await asyncio.gather(*tareas)
        return resultados

    def generar_reporte_pdf(self, patente: str, resultados: List[ResultadoConsulta], ruta_destino: str = None) -> str:
        if not ruta_destino:
            os.makedirs("reportes", exist_ok=True)
            fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta_destino = f"reportes/informe_{patente.upper()}_{fecha_str}.pdf"

        doc = SimpleDocTemplate(
            ruta_destino,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        story = []
        styles = getSampleStyleSheet()

        # Estilos personalizados
        title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1A365D'), alignment=1)
        subtitle_style = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.HexColor('#718096'), alignment=1)
        section_style = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=12, leading=15, textColor=colors.HexColor('#1A365D'), spaceBefore=8, spaceAfter=4)
        body_style = ParagraphStyle('BodyTextCustom', parent=styles['Normal'], fontSize=8, leading=11, textColor=colors.HexColor('#2D3748'))
        header_table_style = ParagraphStyle('HeaderTable', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.white, fontName='Helvetica-Bold')

        # Cabecera Documento
        story.append(Paragraph("ESTADO DE DEUDA E INFRACCIONES DE TRÁNSITO", title_style))
        story.append(Paragraph("INFORME CONSOLIDADO MULTI-JURISDICCIONAL", subtitle_style))
        story.append(Spacer(1, 10))

        # Cuadro de Membrete/Metadatos
        meta_data = [
            [
                Paragraph("<b>Dominio / Patente:</b>", body_style),
                Paragraph(f"<b>{patente.upper()}</b>", body_style),
                Paragraph("<b>Fecha de Emisión:</b>", body_style),
                Paragraph(datetime.now().strftime('%d/%m/%Y %H:%M:%S'), body_style)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[110, 150, 110, 170])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F7FAFC')),
            ('BORDER', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 12))

        total_actas_global = 0

        # Iterar Jurisdicciones
        for r in resultados:
            story.append(Paragraph(f"JURISDICCIÓN: {r.municipio.upper()}", section_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E0'), spaceAfter=6))

            if r.error:
                story.append(Paragraph(f"<b>Error al consultar jurisdicción:</b> {r.error}", body_style))
                story.append(Spacer(1, 8))
                continue

            if not r.tiene_infracciones or not r.infracciones:
                no_fine_data = [[Paragraph("✓ No registra infracciones de tránsito pendientes de pago.", body_style)]]
                no_fine_table = Table(no_fine_data, colWidths=[540])
                no_fine_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F0FFF4')),
                    ('BORDER', (0,0), (-1,-1), 1, colors.HexColor('#C6F6D5')),
                    ('PADDING', (0,0), (-1,-1), 6),
                ]))
                story.append(no_fine_table)
                story.append(Spacer(1, 8))
            else:
                table_data = [
                    [
                        Paragraph("Acta / ID", header_table_style),
                        Paragraph("Fecha", header_table_style),
                        Paragraph("Motivo / Concepto", header_table_style),
                        Paragraph("Importe", header_table_style)
                    ]
                ]

                for inf in r.infracciones:
                    total_actas_global += 1
                    acta_txt = getattr(inf, 'acta', 'S/N')
                    fecha_txt = getattr(inf, 'fecha', 'S/D')
                    motivo_txt = getattr(inf, 'motivo', 'Sin descripción')
                    importe_txt = getattr(inf, 'importe', '$0,00')

                    table_data.append([
                        Paragraph(acta_txt, body_style),
                        Paragraph(fecha_txt, body_style),
                        Paragraph(motivo_txt, body_style),
                        Paragraph(f"<b>{importe_txt}</b>", body_style)
                    ])

                fines_table = Table(table_data, colWidths=[90, 80, 230, 140])
                fines_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2B6CB0')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('BORDER', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('PADDING', (0,0), (-1,-1), 5),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')])
                ]))
                story.append(fines_table)
                story.append(Spacer(1, 8))

        # Resumen Final
        story.append(Spacer(1, 10))
        resumen_data = [
            [
                Paragraph("<b>TOTAL DE ACTAS DETECTADAS:</b>", body_style),
                Paragraph(f"<b>{total_actas_global}</b>", body_style)
            ]
        ]
        resumen_table = Table(resumen_data, colWidths=[380, 160])
        resumen_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#EDF2F7')),
            ('BORDER', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E0')),
            ('PADDING', (0,0), (-1,-1), 8),
            ('ALIGN', (1,0), (1,0), 'RIGHT')
        ]))
        story.append(resumen_table)

        doc.build(story)
        print(f"\n📄 Reporte PDF generado exitosamente en: {ruta_destino}")
        return ruta_destino


async def main():
    import sys
    patente = sys.argv[1] if len(sys.argv) > 1 else "AD307EC"

    consolidador = ConsolidadorInfracciones()
    resultados = await consolidador.consultar_todas(patente)
    consolidador.generar_reporte_pdf(patente, resultados)

if __name__ == "__main__":
    asyncio.run(main())