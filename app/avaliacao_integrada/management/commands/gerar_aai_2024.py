import os
from datetime import date

import pandas as pd
from django.db import transaction
from django.utils.text import slugify

from avaliacao_integrada.models import Avaliacao, Dimensao, Eixo, Indicador, Macroprocesso, Segmento
from comum.models import Ano
from djtools.management.commands import BaseCommandPlus
from edu.models import Modalidade

# gerar_aai_2024 /opt/suap/avaliacao_integrada/management/commands/Instrumento_AAI_2024_EIXO3_17092024.CSV


class Command(BaseCommandPlus):
    def __init__(self, stdout=None, stderr=None, no_color=False, force_color=False):
        super().__init__(stdout, stderr, no_color, force_color)
        self.novo_indicador = None
        self.ano = Ano.objects.get(ano='2024')
        self.modalidades_fic_ids = Modalidade.objects.filter(descricao__icontains='FIC').values_list('id', flat=True)

    def add_arguments(self, parser):
        # Define um argumento posicional obrigatório chamado "arquivo"
        parser.add_argument(
            'path_filename',
            type=str,
            help='Especifique o caminho da planilha a ser importada ',
            nargs='?',  # Permite que o argumento seja opcional
            default=None,  # Define o valor padrão se não for passado
        )

    @transaction.atomic
    def criar_avaliacao(self, id_avaliacao_ref: int):
        self.stdout.write(f'Criando nova avaliação a partir da avaliação de id: {id_avaliacao_ref} ...')
        avaliacao = Avaliacao.objects.get(id=id_avaliacao_ref)

        # Criando uma nova instância da avaliação
        nova_avaliacao = Avaliacao.objects.get(id=id_avaliacao_ref)
        nova_avaliacao.pk = None
        nova_avaliacao.nome = '[FASE DE VALIDAÇÃO] - AUTOAVALIAÇÃO INSTITUCIONAL 2024.1'
        nova_avaliacao.periodo = 1
        nova_avaliacao.ano = self.ano
        nova_avaliacao.data_inicio = date(2024, 10, 7)
        nova_avaliacao.data_termino = date(2024, 10, 31)
        nova_avaliacao.save()

        self.stdout.write(f'Avaliação criada, id {nova_avaliacao.pk}')
        self.stdout.write(f'\tNome: {nova_avaliacao.nome}')
        self.stdout.write(f'\tData Início: {nova_avaliacao.data_inicio}')
        self.stdout.write(f'\tData Término: {nova_avaliacao.data_termino}')

        # Copia as relações ManyToMany
        nova_avaliacao.tipos.set(avaliacao.tipos.all())
        nova_avaliacao.areas_vinculacao.set(avaliacao.areas_vinculacao.all())
        nova_avaliacao.segmentos.set(avaliacao.segmentos.all())
        nova_avaliacao.modalidades.set(avaliacao.modalidades.exclude(id__in=self.modalidades_fic_ids).all())
        nova_avaliacao.uos.set(avaliacao.uos.all())

        return nova_avaliacao

    def get_indicador(self, id: int) -> Indicador:
        if self.novo_indicador is None:
            self.novo_indicador = Indicador.objects.get(id=id)
        return self.novo_indicador

    @transaction.atomic
    def criar_indicador(self, indicador_ref: Indicador, macroprocesso: Macroprocesso, nome: str, aspecto: str) -> Indicador:
        self.stdout.write(f'\tCriando indicador a partir do indicador de id: {indicador_ref.pk}')

        novo_indicador = self.get_indicador(indicador_ref.pk)
        novo_indicador.pk = None
        novo_indicador.ordem = None
        novo_indicador.macroprocesso = macroprocesso
        novo_indicador.nome = nome
        novo_indicador.aspecto = aspecto
        novo_indicador.save()

        self.stdout.write(f'\tIndicador crido, id: {novo_indicador.pk} ')
        self.stdout.write(f'\t\tMacroprocesso: {macroprocesso.descricao}')
        self.stdout.write(f'\t\tDenominação: {nome}')
        self.stdout.write(f'\t\tAspecto: {aspecto}')
        self.stdout.write(f'\t\tAno de referência: {self.ano}')

        # Copia as relações ManyToMany
        novo_indicador.anos_referencia.add(self.ano)
        novo_indicador.subsidio_para.set(indicador_ref.subsidio_para.all())
        novo_indicador.areas_vinculacao.set(indicador_ref.areas_vinculacao.all())
        novo_indicador.modalidades.set(indicador_ref.modalidades.all())
        novo_indicador.uos.set(indicador_ref.uos.all())
        novo_indicador.modalidades.set(indicador_ref.modalidades.exclude(id__in=self.modalidades_fic_ids).all())

        return novo_indicador

    def processar_csv_indicadores(self, path_filename):
        if path_filename and not os.path.exists(path_filename):
            raise FileNotFoundError(f'Arquivo {path_filename} não encontrado.')

        self.stdout.write(f'Processando arquivo csv {path_filename} ...')
        df = pd.read_csv(path_filename, sep=';')

        # Aplicar slugify a todos os nomes de colunas e renomear
        df.rename(columns=slugify, inplace=True)

        # self.stdout.write(df.to_dict(orient='index'))

        indicador_ref = Indicador.objects.get(id=951)
        segmentos_servidores = Segmento.objects.filter(id__in=Segmento.SERVIDORES)
        segmento_aluno = Segmento.objects.get(id=Segmento.ESTUDANTE)
        segmentos_sociedade_civil = Segmento.objects.filter(id__in=Segmento.SOCIEDADE_CIVIL).exclude(
            id__in=(Segmento.DESLIGADO, Segmento.OUTRO_SOCIEDADE_CIVIL)
        )

        for index, row in df.iterrows():
            self.stdout.write(f'\nProcessando linha {index + 1} ...')

            nome_denominador = row['meta-pdi-macroprocesso']

            eixo, _ = Eixo.objects.get_or_create(descricao=row['eixo-sinaes'])
            dimensao, _ = Dimensao.objects.get_or_create(descricao=row['dimensao-sinaes'], eixo=eixo)
            macroprocesso, _ = Macroprocesso.objects.get_or_create(descricao=nome_denominador[5:], dimensao=dimensao)
            self.stdout.write(f'\tEixo: {eixo.pk} - {eixo.descricao}.')
            self.stdout.write(f'\tDimensão: {dimensao.pk} - {dimensao.descricao}.')
            self.stdout.write(f'\tMacroprocesso: {macroprocesso.pk} - {macroprocesso.descricao}.')

            self.stdout.write('\n\tCriando indicar para segmento servidores...')
            aspecto = row['servidores']
            novo_indicador = self.criar_indicador(indicador_ref, macroprocesso, nome_denominador, aspecto)
            novo_indicador.segmentos.set(segmentos_servidores)

            if row['estudantes'] != 'Não se aplica':
                self.stdout.write('\n\tCriando indicar para segmento estudantes...')
                if row['estudantes'] != 'idem':
                    aspecto = row['estudantes']
                    novo_indicador = self.criar_indicador(indicador_ref, macroprocesso, nome_denominador, aspecto)
                self.stdout.write(f'\tIncluindo segmento {segmento_aluno}')
                novo_indicador.segmentos.add(segmento_aluno)

            if row['sociedade-civil'] != 'Não se aplica':
                self.stdout.write('\n\tCriando indicar para segmento sociedade civil...')
                if row['sociedade-civil'] != 'idem':
                    aspecto = row['sociedade-civil']
                    novo_indicador = self.criar_indicador(indicador_ref, macroprocesso, nome_denominador, aspecto)
                for segmento in segmentos_sociedade_civil:
                    self.stdout.write(f'\tIncluindo segmento {segmento}')
                    novo_indicador.segmentos.add(segmento)

    def handle(self, **options):
        # Avaliacao.objects.filter(ano__ano='2024').delete()
        self.criar_avaliacao(20)
        path_filename = options.get('path_filename')

        Indicador.objects.filter(anos_referencia__ano='2024').delete()
        self.processar_csv_indicadores(path_filename)
