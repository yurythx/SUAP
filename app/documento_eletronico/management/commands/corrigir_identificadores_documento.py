from datetime import datetime

from django.apps import apps
from django.core.management import CommandError
from tqdm import tqdm

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.generators import montar_identificador_sigla


class Command(BaseCommandPlus):
    """
    Command criado para corrigir documentos assinados com identificadores incorretos
    Será feita checagem do identificador e correção caso necessário
    Ex: python manage.py corrigir_identificadores_documento --dt_inicio_processamento="01/01/2023"
    """

    def add_arguments(self, parser):
        parser.add_argument('--dt_inicio_processamento', type=str, help='Data e hora de início do processamento no formato DD/MM/YYYY')

    def handle(self, *args, **options):
        DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
        Setor = apps.get_model('rh', 'Setor')

        dt_inicio_processamento = datetime(2022, 1, 1)
        if options['dt_inicio_processamento']:
            try:
                dt_inicio_processamento = datetime.strptime(options['dt_inicio_processamento'], '%d/%m/%Y')
            except ValueError:
                raise CommandError('Formato de data e hora inválido. Use o formato DD/MM/YYYY')

        title = 'Doc. Eletrônico - Command para Corrigir Identificadores de Documentos'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        setores_com_documentos_assinados = (
            Setor.objects.suap_ativos()
            .filter(documentotexto__data_criacao__gte=dt_inicio_processamento, documentotexto__assinatura_balizadora__isnull=False)
            .distinct()
        )
        print(f'{setores_com_documentos_assinados.count()} setores a serem analisado com documentos assinados apos {dt_inicio_processamento}')
        total_corrigidos_setor = 0
        total_corrigidos_tipo = 0
        documentos_corrigidos_ids = []
        for setor in tqdm(setores_com_documentos_assinados):
            print(f'Setor {setor.sigla}')
            identificador_sigla_correto = montar_identificador_sigla(setor)
            docs_assinados = DocumentoTexto.objects.filter(
                setor_dono=setor, data_criacao__gte=dt_inicio_processamento, assinatura_balizadora__isnull=False
            )

            qtd_docs = docs_assinados.count()
            qtd_corrigidos_setor = 0
            qtd_corrigidos_tipo_sigla = 0
            if qtd_docs:
                print(f'Foram encontrados {qtd_docs} documentos neste setor. Agora o atributo identificador_setor_sigla será corrigido.')
            for doc in docs_assinados:
                if doc.setor_dono and (doc.identificador_setor_sigla != identificador_sigla_correto):
                    doc.identificador_setor_sigla = identificador_sigla_correto
                    doc.save()
                    qtd_corrigidos_setor += 1
                    documentos_corrigidos_ids.append(doc.id)
                    print(
                        f'Documento Texto id {doc.id} teve o identificador_sigla_setor corrigido de {doc.identificador_setor_sigla} para {identificador_sigla_correto}'
                    )

                if doc.identificador_tipo_documento_sigla != doc.modelo.get_tipo_sigla():
                    doc.identificador_tipo_documento_sigla = doc.modelo.get_tipo_sigla()
                    doc.save()
                    qtd_corrigidos_tipo_sigla += 1
                    documentos_corrigidos_ids.append(doc.id)
                    print(
                        f'Documento Texto id {doc.id} teve o identificador_tipo_sigla corrigido de {doc.identificador_tipo_documento_sigla} para {doc.modelo.get_tipo_sigla()}'
                    )
            print(f'Foram corrigidos {qtd_corrigidos_setor} siglas do setor de documentos neste setor.')
            print(f'Foram corrigidos {qtd_corrigidos_tipo_sigla} identificador de tipos de documentos neste setor.')
            total_corrigidos_setor += qtd_corrigidos_setor
            total_corrigidos_tipo += qtd_corrigidos_tipo_sigla

        print()
        print(f'O atributo identificador_sigla_setor foi corrigido em  {total_corrigidos_setor} documentos.')
        print(f'O atributo identificador_tipo_documento_sigla foi corrigido em  {total_corrigidos_tipo} documentos.')
        print('Lista com Ids de Documentos Corrigidos')
        print(f'{documentos_corrigidos_ids}')
        print('Fim do processamento.')
