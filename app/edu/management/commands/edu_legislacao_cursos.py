from io import BytesIO

import pandas as pd
from django.core.files.storage import default_storage

from djtools.management.commands import BaseCommandPlus
from edu.models import Autorizacao, MatrizCurso, Reconhecimento


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # RECONHECIMENTOS
        rows = []
        headers = [
            'COD CURSO',
            'NOME DO CURSO',
            'MODALIDADE',
            'COD MATRIZ',
            'NOME DA MATRIZ',
            'DIRETORIA',
            'CAMPUS',
            'TIPO',
            'DATA',
            'NUMERO',
            'RENOVACAO',
            'VALIDADE',
            'NUM PUBLICACAO',
            'DT PUBLICACAO',
            'VEICULO',
            'SECAO',
            'PAGINA',
            'REFERENCIA',
        ]

        reconhecimentos = Reconhecimento.objects.filter(matriz_curso__curso_campus__modalidade__nivel_ensino__id=3).order_by(
            'matriz_curso__curso_campus__diretoria'
        )
        for r in reconhecimentos:
            rows.append(
                [
                    r.matriz_curso.curso_campus.codigo,
                    r.matriz_curso.curso_campus.descricao_historico,
                    r.matriz_curso.curso_campus.modalidade,
                    r.matriz_curso.matriz_id,
                    r.matriz_curso.matriz.descricao,
                    r.matriz_curso.curso_campus.diretoria,
                    r.matriz_curso.curso_campus.diretoria.setor.uo,
                    r.tipo,
                    r.data.strftime('%d/%m/%Y'),
                    r.numero,
                    r.renovacao and 'S' or 'N',
                    r.validade and r.validade.strftime('%d/%m/%Y') or '',
                    r.numero_publicao or '',
                    r.data_publicacao and r.data_publicacao.strftime('%d/%m/%Y') or '',
                    r.veiculo_publicacao or '',
                    r.secao_publicao or '',
                    r.pagina_publicao or '',
                    '',  # REFERENCIA
                ]
            )

        mcs = MatrizCurso.objects.filter(curso_campus__modalidade__nivel_ensino__id=3).order_by('curso_campus__diretoria')

        for r in mcs.filter(reconhecimento__isnull=True):
            rows.append(
                [
                    r.curso_campus.codigo,
                    r.curso_campus.descricao_historico,
                    r.curso_campus.modalidade,
                    r.matriz_id,
                    r.matriz.descricao,
                    r.curso_campus.diretoria,
                    r.curso_campus.diretoria.setor.uo,
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '{} {}'.format(r.reconhecimento_texto or '', r.reconhecimento_data and r.reconhecimento_data.strftime('%d/%m/%Y') or ''),
                ]
            )

        df_reconhecimentos = pd.DataFrame(rows, columns=headers)

        # AUTORIZACOES
        rows = []
        headers = [
            'COD CURSO',
            'NOME DO CURSO',
            'MODALIDADE',
            'COD MATRIZ',
            'NOME DA MATRIZ',
            'DIRETORIA',
            'CAMPUS',
            'TIPO',
            'DATA',
            'NUMERO',
            'ADEQUACAO',
            'NUM PUBLICACAO',
            'DT PUBLICACAO',
            'VEICULO',
            'SECAO',
            'PAGINA',
            'REFERENCIA',
        ]

        autorizacoes = Autorizacao.objects.filter(matriz_curso__curso_campus__modalidade__nivel_ensino__id=3).order_by(
            'matriz_curso__curso_campus__diretoria'
        )
        for r in autorizacoes:
            rows.append(
                [
                    r.matriz_curso.curso_campus.codigo,
                    r.matriz_curso.curso_campus.descricao_historico,
                    r.matriz_curso.curso_campus.modalidade,
                    r.matriz_curso.matriz_id,
                    r.matriz_curso.matriz.descricao,
                    r.matriz_curso.curso_campus.diretoria,
                    r.matriz_curso.curso_campus.diretoria.setor.uo,
                    r.tipo,
                    r.data.strftime('%d/%m/%Y'),
                    r.numero,
                    r.adequacao and 'S' or 'N',
                    r.numero_publicacao or '',
                    r.data_publicacao and r.data_publicacao.strftime('%d/%m/%Y') or '',
                    r.veiculo_publicacao or '',
                    r.secao_publicacao or '',
                    r.pagina_publicacao or '',
                    '',  # REFERENCIA
                ]
            )
        for r in mcs.filter(autorizacao__isnull=True):
            rows.append(
                [
                    r.curso_campus.codigo,
                    r.curso_campus.descricao_historico,
                    r.curso_campus.modalidade,
                    r.matriz_id,
                    r.matriz.descricao,
                    r.curso_campus.diretoria,
                    r.curso_campus.diretoria.setor.uo,
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '{} {}'.format(r.resolucao_criacao or '', r.resolucao_data and r.resolucao_data.strftime('%d/%m/%Y') or ''),
                ]
            )

        df_autorizacoes = pd.DataFrame(rows, columns=headers)

        stream = BytesIO()
        with pd.ExcelWriter(stream, engine='openpyxl') as writer:
            df_reconhecimentos.to_excel(writer, sheet_name='RECONHECIMENTOS', index=False)
            df_autorizacoes.to_excel(writer, sheet_name='AUTORIZACOES', index=False)

            # Auto-fit columns
            for sheet_name in ['RECONHECIMENTOS', 'AUTORIZACOES']:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column = list(column)
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except Exception:
                            pass
                    adjusted_width = max_length + 2
                    worksheet.column_dimensions[column[0].column_letter].width = adjusted_width

        stream.seek(0)
        content = stream.read()
        file = default_storage.save('CursosSuperiores.xlsx', BytesIO(content))
        self.stdout.write(file)
