from django.db.models.aggregates import Sum

from comum.models import Ano
from djtools.db import models
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES


class PlanoEstudo(models.ModelPlus):
    PLANEJAMENTO = 'Planejamento'
    DISPENSA = 'Dispensa'

    tipo = models.CharFieldPlus(verbose_name='Tipo', choices=[[PLANEJAMENTO, PLANEJAMENTO], [DISPENSA, DISPENSA]])
    pedido_matricula = models.ForeignKeyPlus('edu.PedidoMatricula', verbose_name='Pedido de Matrícula')
    planejamento_concluido = models.BooleanField(verbose_name='Planejamento Concluído', null=True)
    homologado = models.BooleanField(verbose_name='Planejamento Homologado', null=True)
    data_homologacao = models.DateFieldPlus(verbose_name='Data de Homologação', null=True)
    observacao_homologacao = models.TextField(verbose_name='Observação da Homologação', blank=True)
    numero_ata_homologacao = models.CharFieldPlus(verbose_name='Nº da Ata de Homologação', null=True)
    descumprido = models.BooleanField(verbose_name='Descumprido', default=False)

    class Meta:
        verbose_name = 'Plano de Estudo'
        verbose_name_plural = 'Planos de Estudo'

    def __str__(self):
        return f'Plano de estudo #{self.id}'

    def get_absolute_url(self):
        return f'/edu/planoestudo/{self.pk}/'

    def get_resumo_ch(self):
        metadados = [
            (
                'ch_componentes_obrigatorios',
                'get_ch_componentes_regulares_obrigatorios_cumprida',
                'Componentes Regulares Obrigatórios',
            ),
            (
                'ch_componentes_optativos',
                'get_ch_componentes_regulares_optativos_cumprida',
                'Componentes Regulares Optativos',
            ),
            (
                'ch_componentes_eletivos',
                'get_ch_componentes_eletivos_cumprida',
                'Componentes Eletivos',
            ),
            (
                'ch_seminarios',
                'get_ch_componentes_seminario_cumprida',
                'Seminários',
            ),
            (
                'ch_pratica_profissional',
                'get_ch_componentes_pratica_profissional_cumprida',
                'Prática Profissional',
            ),
            (
                'ch_componentes_tcc',
                'get_ch_componentes_tcc_cumprida',
                'Trabalho de Conclusão de Curso',
            ),
        ]
        dados = []
        planejamento_concluido = True
        for atributo_ch_esperada, atributo_ch_cumprida, nome in metadados:
            aluno = self.pedido_matricula.matricula_periodo.aluno
            ch_esperada = getattr(aluno.matriz, atributo_ch_esperada)
            if ch_esperada:
                ch_cumprida = getattr(aluno, atributo_ch_cumprida)()
                ch_planejada = getattr(self, atributo_ch_cumprida[:-9])()
                ch_total = ch_cumprida + ch_planejada
                dados.append((nome, ch_esperada, ch_cumprida, ch_planejada, ch_total, ch_total >= ch_esperada))
                if ch_total < ch_esperada:
                    planejamento_concluido = False
        if planejamento_concluido and not self.planejamento_concluido:
            self.planejamento_concluido = planejamento_concluido
            self.save()
        if self.planejamento_concluido and not planejamento_concluido:
            self.planejamento_concluido = planejamento_concluido
            self.save()
        return dados

    def get_ch_componentes_regulares_obrigatorios(self):
        matriz = self.pedido_matricula.matricula_periodo.aluno.matriz
        return (
            self.itemplanoestudo_set.filter(componente_curricular__componente_id__in=matriz.get_ids_componentes_regulares_obrigatorios())
            .aggregate(Sum('componente_curricular__componente__ch_hora_relogio'))
            .get('componente_curricular__componente__ch_hora_relogio__sum')
            or 0
        )

    def get_ch_componentes_regulares_optativos(self):
        matriz = self.pedido_matricula.matricula_periodo.aluno.matriz
        return (
            self.itemplanoestudo_set.filter(componente_curricular__componente_id__in=matriz.get_ids_componentes_regulares_optativos())
            .aggregate(Sum('componente_curricular__componente__ch_hora_relogio'))
            .get('componente_curricular__componente__ch_hora_relogio__sum')
            or 0
        )

    def get_ch_componentes_eletivos(self):
        return 0

    def get_ch_componentes_seminario(self):
        matriz = self.pedido_matricula.matricula_periodo.aluno.matriz
        return (
            self.itemplanoestudo_set.filter(componente_curricular__componente_id__in=matriz.get_ids_componentes_seminario())
            .aggregate(Sum('componente_curricular__componente__ch_hora_relogio'))
            .get('componente_curricular__componente__ch_hora_relogio__sum')
            or 0
        )

    def get_ch_componentes_pratica_profissional(self):
        matriz = self.pedido_matricula.matricula_periodo.aluno.matriz
        return (
            self.itemplanoestudo_set.filter(componente_curricular__componente_id__in=matriz.get_ids_componentes_pratica_profissional())
            .aggregate(Sum('componente_curricular__componente__ch_hora_relogio'))
            .get('componente_curricular__componente__ch_hora_relogio__sum')
            or 0
        )

    def get_ch_componentes_tcc(self):
        matriz = self.pedido_matricula.matricula_periodo.aluno.matriz
        return (
            self.itemplanoestudo_set.filter(componente_curricular__componente_id__in=matriz.get_ids_componentes_tcc())
            .aggregate(Sum('componente_curricular__componente__ch_hora_relogio'))
            .get('componente_curricular__componente__ch_hora_relogio__sum')
            or 0
        )


class ItemPlanoEstudo(models.ModelPlus):
    plano_estudo = models.ForeignKeyPlus(PlanoEstudo, verbose_name='Plano de Estudo')
    componente_curricular = models.ForeignKeyPlus('edu.ComponenteCurricular', verbose_name='Componente Curricular')
    ano_letivo = models.ForeignKeyPlus(Ano, verbose_name='Ano Letivo')
    periodo_letivo = models.IntegerField(verbose_name='Período Letivo', choices=PERIODO_LETIVO_CHOICES)

    class Meta:
        verbose_name = 'Item do Plano de Estudo'
        verbose_name_plural = 'Itens de Plano de Estudo'

    def __str__(self):
        return f'Item de plano de estudo #{self.id}'
