import math
import os
from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.db import transaction

from calculos_pagamentos.models.calculos import TIPO_CALCULO_CHOICES, Calculo
from tinymce.models import HTMLField
from comum.models import Configuracao, User
from comum.utils import get_sigla_reitoria, tl
from djtools.db import models
from djtools.db.models import ModelPlus
from rh.models import UnidadeOrganizacional


class Sequencia(ModelPlus):
    numero = models.PositiveIntegerField('Número da Sequência', unique=True)

    class Meta:
        verbose_name = 'Sequência'
        verbose_name_plural = 'Sequências'
        ordering = ('id',)

    def __str__(self):
        return f'{self.numero}'


class Rubrica(ModelPlus):
    codigo = models.CharFieldPlus('Código da Rubrica', validators=[MaxLengthValidator(5), MinLengthValidator(5)], unique=True)
    sequencias = models.ManyToManyFieldPlus(Sequencia, verbose_name='Sequências', related_name='rubricas')
    teto_seq = models.DecimalField('Teto de cada sequência', max_digits=12, decimal_places=2)
    descricao = models.CharFieldPlus('Descrição')
    # Nome do método do Cálculo que retorna o valor dessa rubrica para aquele cálculo
    metodo_get_valor = models.CharFieldPlus('Método_Get_Valor', null=True, blank=True)  # EX.: get_valor_substituicao, get_valor_gratificacao

    class Meta:
        verbose_name = 'Rubrica'
        verbose_name_plural = 'Rubricas'
        ordering = ('codigo',)

    def __str__(self):
        return f'{self.codigo} - {self.descricao}'


class ConfigPagamento(ModelPlus):
    tipo_calculo = models.PositiveIntegerField('Tipo do Cálculo', choices=TIPO_CALCULO_CHOICES, unique=True)
    rubricas = models.ManyToManyFieldPlus(Rubrica, verbose_name='Rubricas', related_name='configuracoes')

    class Meta:
        verbose_name = 'Configuração de Pagamento'
        verbose_name_plural = 'Configurações de Pagamento'
        ordering = ('id',)

    def __str__(self):
        return f'Configuração de Pagamento de {self.get_tipo_calculo_display()}'


class ArquivoPagamento(ModelPlus):
    # Campos referentes ao arquivo de pagamento. São preenchidos a partir da situação "Processado"
    mes = models.CharFieldPlus(validators=[MaxLengthValidator(2), MinLengthValidator(2)])
    ano = models.CharFieldPlus(validators=[MaxLengthValidator(4), MinLengthValidator(4)])
    quant_registros_1 = models.CharFieldPlus(validators=[MaxLengthValidator(7), MinLengthValidator(7)])
    data_criacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário criador', on_delete=models.PROTECT)
    texto_arquivo = HTMLField('Conteúdo do Arquivo')
    file_path = models.CharFieldPlus('Caminho do arquivo gerado')

    """
    Dados do arquivo de movimentação financeira
    tipo0 = '0'
    codigo_orgao = UnidadeOrganizacional.objects.filter(nome=Reitoria)[0].codigo_protocolo
    zero16 = '0000000000000000'
    nome_fantasia = 'IFMA  '
    branco29 = '                             '
    movi-financ = 'MOVI-FINANC'
    branco1 = ' '
    codigo_rubrica_linha_1 = '     '
    branco120 = '                                                                                                                        '

    tipo1 = '1'
    matricula = calculo.servidor.matricula
    dv = calculo.servidor.identificacao_unica_siape[-1:]
    tipo_comando = '4'  # Inclusão
    Dados da rubrica: matricula, dv, rend_desc, codigo, sequencia, valor, mes, ano
    prazo = '000'
    matricula_ant = '        '
    branco38 = '                                      '
    branco5 = '     '
    branco4 = '    '
    branco2 = '  '
    branco3 = '   '
    branco9 = '         '
    branco6 = '      '
    branco14 = '              '
    branco13 = '             '

    tipo9 = '9'
    nove16 = '9999999999999999'
    branco171 = '                                                                                                                                                                           '
    """

    class Meta:
        verbose_name = 'Arquivo de Pagamento'
        verbose_name_plural = 'Arquivos de Pagamento'
        ordering = ['-data_criacao']

    def __str__(self):
        return '{}/{} - Gerado em {}'.format(self.mes, self.ano, self.data_criacao.strftime('%d/%m/%Y, %H:%Mh'))

    def save(self):
        self.usuario = tl.get_user()
        super().save()

    @transaction.atomic
    def gerar_arquivo(self, mes, ano, pagamentos):
        quant_registros_1 = 0
        texto_arquivo = ''
        sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        # Dados do início (header)
        tipo_registro_0 = '0'
        orgao_siape = UnidadeOrganizacional.objects.filter(sigla=get_sigla_reitoria())[0].codigo_ugr
        constante_zero_16 = 16 * '0'
        constante_nome_fantasia = f'{sigla_instituicao}  '
        constante_branco_29 = 29 * ' '
        constante_movi_financ = 'MOVI-FINANC'
        filler_branco_1 = ' '
        codigo_rubrica_header = '00001'
        filler_branco_120 = 120 * ' '

        # Dados do meio
        tipo_registro_1 = '1'
        comando_inclusao = '4'  # Inclusão
        prazo = '001'
        numero_origem = 8 * ' '
        rubrica_calculo = 5 * ' '
        parametrizacao_rubrica_calculo = '44'
        constante_branco_3 = 3 * ' '
        constante_branco_4 = 4 * ' '
        constante_branco_5 = 5 * ' '
        constante_branco_6 = 6 * ' '
        constante_branco_9 = 9 * ' '
        constante_branco_13 = 13 * ' '
        constante_branco_14 = 14 * ' '
        constante_branco_38 = 38 * ' '

        # Dados do fim (trailler)
        tipo_registro_9 = '9'
        constante_9_16 = 16 * '9'
        filler_branco_171 = 171 * ' '

        # INÍCIO (HEADER)
        texto_arquivo += tipo_registro_0
        texto_arquivo += orgao_siape
        texto_arquivo += constante_zero_16
        texto_arquivo += str(mes).zfill(2)
        texto_arquivo += str(ano).zfill(4)
        texto_arquivo += constante_nome_fantasia
        texto_arquivo += constante_branco_29
        texto_arquivo += constante_movi_financ
        texto_arquivo += filler_branco_1
        texto_arquivo += codigo_rubrica_header
        texto_arquivo += filler_branco_120
        texto_arquivo += '\n'

        # MEIO
        data_pagamento = date(int(ano), int(mes), 1)
        pagamentos = pagamentos.filter(mes_fim__lt=data_pagamento)
        for linha in self.gerar_linhas_de_pagamento(pagamentos=pagamentos):
            texto_arquivo += tipo_registro_1
            texto_arquivo += orgao_siape
            texto_arquivo += linha.pagamentos.first().calculo.servidor.matricula.zfill(7)
            texto_arquivo += linha.pagamentos.first().calculo.servidor.identificacao_unica_siape[-1:]
            texto_arquivo += comando_inclusao
            texto_arquivo += linha.rend_desc
            texto_arquivo += linha.rubrica
            texto_arquivo += linha.sequencia
            texto_arquivo += linha.valor
            texto_arquivo += prazo
            texto_arquivo += numero_origem
            texto_arquivo += constante_branco_38  # nome beneficiario se rubrica 97XXX
            texto_arquivo += rubrica_calculo
            texto_arquivo += rubrica_calculo
            texto_arquivo += rubrica_calculo
            texto_arquivo += constante_branco_4
            texto_arquivo += parametrizacao_rubrica_calculo
            texto_arquivo += constante_branco_3
            texto_arquivo += constante_branco_3
            texto_arquivo += constante_branco_5
            texto_arquivo += filler_branco_1
            texto_arquivo += constante_branco_9
            texto_arquivo += constante_branco_6
            texto_arquivo += constante_branco_5
            texto_arquivo += constante_branco_5
            texto_arquivo += constante_branco_4
            texto_arquivo += constante_branco_5
            texto_arquivo += linha.mes
            texto_arquivo += linha.ano
            texto_arquivo += constante_branco_5
            texto_arquivo += constante_branco_14
            texto_arquivo += constante_branco_3
            texto_arquivo += constante_branco_6
            texto_arquivo += constante_branco_13
            texto_arquivo += constante_branco_4
            texto_arquivo += '\n'

            quant_registros_1 += 1

        # FIM (TRAILLER)
        if quant_registros_1 > 0:
            texto_arquivo += tipo_registro_9
            texto_arquivo += orgao_siape
            texto_arquivo += constante_9_16
            texto_arquivo += str(quant_registros_1).zfill(7)
            texto_arquivo += filler_branco_171

            self.mes = str(mes).zfill(2)
            self.ano = str(ano).zfill(4)
            self.quant_registros_1 = str(quant_registros_1).zfill(7)
            self.texto_arquivo = texto_arquivo

            datahora = datetime.now()
            file_path = os.path.join(settings.MEDIA_ROOT, f'calculos_pagamentos/arquivos_de_pagamento/MOVI-FINANC-{datahora}.txt')
            if not os.path.exists(os.path.dirname(os.path.dirname(file_path))):
                os.mkdir(os.path.dirname(os.path.dirname(file_path)))
            if not os.path.exists(os.path.dirname(file_path)):
                os.mkdir(os.path.dirname(file_path))
            arq = open(file_path, 'w')
            arq.write(texto_arquivo)
            arq.close()
            self.file_path = file_path

        return pagamentos

    def gerar_linhas_de_pagamento(self, pagamentos):
        linhas = []
        servidores_ids = set(pagamentos.values_list('calculo__servidor__pk', flat=True))
        tipos = set(pagamentos.values_list('calculo__tipo', flat=True))
        for servidor_id in servidores_ids:
            pagamentos_do_servidor = pagamentos.filter(calculo__servidor__pk=servidor_id)
            for tipo in tipos:
                pagamentos_do_servidor_do_tipo = pagamentos_do_servidor.filter(calculo__tipo=tipo)
                if pagamentos_do_servidor_do_tipo.exists():
                    for rubrica in pagamentos_do_servidor_do_tipo[0].configuracao.rubricas.all():
                        valor = 0
                        data_maxima = date(year=2000, month=1, day=1)
                        for pagamento in pagamentos_do_servidor_do_tipo:
                            calculo = pagamento.calculo.get_calculo_espeficico()
                            inicio_mes = pagamento.mes_inicio.replace(day=1)
                            fim_mes = pagamento.mes_fim.replace(day=1) + relativedelta(months=+1) + relativedelta(days=-1)
                            valor += getattr(calculo, rubrica.metodo_get_valor)(inicio_mes, fim_mes)
                            data_maxima = max(data_maxima, pagamento.mes_fim)

                        rend_desc = '1' if valor > 0 else '2'
                        mes = str(data_maxima.month).zfill(2)
                        ano = str(data_maxima.year).zfill(4)
                        quant_parcelas = math.ceil(valor / rubrica.teto_seq)
                        sequencias = [x.numero for x in rubrica.sequencias.all().order_by('numero')]
                        while quant_parcelas > 0:
                            seq = sequencias.pop(0)
                            parcela = min(rubrica.teto_seq, valor)
                            linhapagamento = LinhaPagamento(
                                rend_desc=rend_desc,
                                rubrica=rubrica.codigo,
                                sequencia=str(seq),
                                valor=str(parcela).replace('.', '').zfill(11),
                                mes=mes,
                                ano=ano,
                            )
                            linhapagamento.save()
                            for pagamento in pagamentos_do_servidor_do_tipo:
                                pagamento.linhas.add(linhapagamento)
                            linhas.append(linhapagamento)
                            quant_parcelas -= 1
                            valor -= rubrica.teto_seq

        return linhas


SITUACAO_LINHA_CHOICES = [
    [1, 'Aceita'],
    [2, 'Rejeitada'],
]


# LinhaPagamento guarda informações de uma determinada linha de movimentação financeira de um arquivo de pagamento.
class LinhaPagamento(ModelPlus):
    # Transferido campo abaixo para Pagamento, pois agora cardinalidade é N:N
    # pagamento = models.ForeignKeyPlus(Pagamento, verbose_name="Pagamento", related_name="linhas")
    # Dados da linha: rend_desc, codigo, sequencia, valor, mes, ano
    rend_desc = models.CharFieldPlus('Rendimento (1) ou Desconto (2)', validators=[MaxLengthValidator(1), MinLengthValidator(1)])
    rubrica = models.CharFieldPlus('Código da Rubrica', validators=[MaxLengthValidator(5), MinLengthValidator(5)])
    sequencia = models.CharFieldPlus('Sequência', validators=[MaxLengthValidator(1), MinLengthValidator(1)])
    valor = models.CharFieldPlus('Valor', validators=[MaxLengthValidator(11), MinLengthValidator(11)])
    mes = models.CharFieldPlus('Mês', validators=[MaxLengthValidator(2), MinLengthValidator(2)])
    ano = models.CharFieldPlus('Ano', validators=[MaxLengthValidator(4), MinLengthValidator(4)])
    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_LINHA_CHOICES, null=True, blank=True)

    class Meta:
        verbose_name = 'Linha de Pagamento'
        verbose_name_plural = 'Linhas de Pagamentos'

    def get_linha(self):
        str = '1'
        str += UnidadeOrganizacional.objects.filter(sigla=get_sigla_reitoria())[0].codigo_ugr
        str += self.pagamentos.first().calculo.servidor.matricula
        str += self.pagamentos.first().calculo.servidor.identificacao_unica_siape[-1:]
        str += '4'
        str += self.rend_desc
        str += self.rubrica
        str += self.sequencia
        str += self.valor
        str += '000'
        str += '                                                                                                                 '
        str += self.mes
        str += self.ano
        str += '                                             '
        return str

    def __str__(self):
        # return 'ID {}: {}'.format(self.pk, self.get_linha())
        return f'ID {self.pk}'


SITUACAO_PAGAMENTO_CHOICES = [
    [1, 'Não processado'],
    [2, 'Gerado'],
    [3, 'Aceito'],
    [4, 'Rejeitado'],
    [5, 'Lançado Manualmente'],
    [6, 'Aceito Parcialmente'],
]


class Pagamento(ModelPlus):
    calculo = models.ForeignKeyPlus(Calculo, verbose_name='Cálculo', related_name='pagamentos', on_delete=models.CASCADE)
    # Meses a serem considerados do cálculo neste pagamento
    mes_inicio = models.DateFieldPlus('Data com o Mês Inicial', null=False)
    mes_fim = models.DateFieldPlus('Data com o Mês Final', null=False)

    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_PAGAMENTO_CHOICES)
    configuracao = models.ForeignKeyPlus(ConfigPagamento, verbose_name='Configuração', related_name='pagamentos', on_delete=models.PROTECT)
    arquivo = models.ForeignKeyPlus(
        ArquivoPagamento, verbose_name='Arquivo de Pagamento', related_name='pagamentos', null=True, blank=True, on_delete=models.SET_NULL
    )
    linhas = models.ManyToManyField(LinhaPagamento, verbose_name='Linhas de Pagamento', related_name='pagamentos', blank=True)

    class Meta:
        verbose_name = 'Pagamento'
        verbose_name_plural = 'Pagamentos'

    def __str__(self):
        return f'Pagamento do {self.calculo.__str__()}'

    def get_absolute_url(self):
        return '/{}/{}/'.format(self._meta.label_lower.replace('.', '/'), self.id)

    def save(self):
        super().save()
        HistoricoPagamento.objects.create(pagamento=self, situacao=self.situacao, usuario=tl.get_user())


class HistoricoPagamento(ModelPlus):
    pagamento = models.ForeignKeyPlus(Pagamento, verbose_name='Pagamento', related_name='historicos', on_delete=models.CASCADE)
    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_PAGAMENTO_CHOICES)
    data = models.DateTimeFieldPlus('Data', auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário', on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Histórico de Pagamento'
        verbose_name_plural = 'Históricos de Pagamento'
