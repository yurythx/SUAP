import copy
import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.template import Context, Template
from django.utils.safestring import mark_safe

from comum.models import Ano, Configuracao, UsuarioGrupo, UsuarioGrupoSetor, Vinculo
from comum.utils import get_sigla_reitoria
from djtools.db import models, transaction
from djtools.templatetags.filters import format_datetime
from djtools.utils import retira_acentos, send_notification
from djtools.utils.masks import mask_number
from djtools.utils.response import substituir_marcadores
from edu.models import (
    Componente,
    ComponenteCurricular,
    ComponenteCurricularCertificacaoParcial,
    ConfiguracaoCertificacaoParcial,
    CursoCampus,
    Diretoria,
    LogModel,
    Matriz,
    MatrizCurso,
    Modalidade,
    ModalidadePraticaProfissional,
    NivelEnsino,
    TipoComponente,
)
from ppc.utils import processar_bibliografia
from rh.models import Servidor, Setor


class Diretriz(LogModel):
    descricao = models.CharFieldPlus('Descrição')
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', null=False, blank=False)
    estrutura_curso = models.ForeignKeyPlus('edu.EstruturaCurso', verbose_name='Estrutura de curso', null=False, blank=False)
    tipo_oferta = models.ForeignKeyPlus('edu.Modalidade', verbose_name='Tipo de oferta', null=False, blank=False)
    modalidade = models.ForeignKeyPlus('edu.NaturezaParticipacao', verbose_name='Modalidade', null=False, blank=False)
    arquivo = models.FileFieldPlus(
        'Arquivo',
        upload_to='ppc/diretrizes/',
        null=False,
        blank=False,
        filetypes=[
            'pdf',
        ],
    )

    qtd_min_periodos = models.PositiveIntegerFieldPlus('Quantidade mínima de períodos', null=True, blank=False, min_value=1)
    qtd_max_periodos = models.PositiveIntegerFieldPlus('Quantidade máxima de períodos', null=True, blank=False, min_value=1)

    qtd_min_disciplina_semestre = models.PositiveIntegerFieldPlus('Quantidade mínima de disciplinas no semestre', null=True, blank=True)
    qtd_max_disciplina_semestre = models.PositiveIntegerFieldPlus('Quantidade máxima de disciplinas no semestre', null=True, blank=True)

    ch_semanal_min_semestre = models.PositiveIntegerFieldPlus('Carga horária semanal mínima no semestre', null=True, blank=True)
    ch_semanal_max_semestre = models.PositiveIntegerFieldPlus('Carga horária semanal máxima no semestre', null=True, blank=True)

    ch_min_curso = models.PositiveIntegerFieldPlus('CH mínima do curso', null=False, blank=False, min_value=1)
    ch_max_curso = models.PositiveIntegerFieldPlus('CH máxima do curso', null=False, blank=False, min_value=1)

    ch_min_cc_obrigatorio = models.PositiveIntegerFieldPlus('CH mínima de componentes obrigatórios', null=False, blank=False)
    ch_max_cc_obrigatorio = models.PositiveIntegerFieldPlus('CH máxima de componentes obrigatórios', null=False, blank=False)

    ch_min_cc_optativo = models.PositiveIntegerFieldPlus('CH mínima de componentes optativos', null=False, blank=False)
    ch_max_cc_optativo = models.PositiveIntegerFieldPlus('CH máxima de componentes optativos', null=False, blank=False)

    ch_min_cc_eletivo = models.PositiveIntegerFieldPlus('CH mínima de componentes eletivos', null=False, blank=False)
    ch_max_cc_eletivo = models.PositiveIntegerFieldPlus('CH máxima de componentes eletivos', null=False, blank=False)

    ch_min_pratica = models.PositiveIntegerFieldPlus('CH mínima de prática profissional', null=False, blank=False)
    ch_max_pratica = models.PositiveIntegerFieldPlus('CH máxima de prática profissional', null=False, blank=False)

    ch_min_ac = models.PositiveIntegerFieldPlus('CH mínima de atividade complementar', null=False, blank=False)
    ch_max_ac = models.PositiveIntegerFieldPlus('CH máxima de atividade complementar', null=False, blank=False)

    ch_min_atpa = models.PositiveIntegerFieldPlus('CH mínima de atividade teórico-prática de aprofundamento', null=False, blank=False)
    ch_max_atpa = models.PositiveIntegerFieldPlus('CH máxima de atividade teórico-prática de aprofundamento', null=False, blank=False)

    ch_min_cc_regular = models.PositiveIntegerFieldPlus('CH mínima de componentes do tipo regular', null=False, blank=False, default=0)
    ch_max_cc_regular = models.PositiveIntegerFieldPlus('CH máxima de componentes do tipo regular', null=False, blank=False, default=0)

    ch_min_cc_extensao = models.PositiveIntegerFieldPlus('CH mínima de componentes do tipo atividade de extensão', null=False, blank=False, default=0)
    ch_max_cc_extensao = models.PositiveIntegerFieldPlus('CH máxima de componentes do tipo atividade de extensão', null=False, blank=False, default=0)

    ch_min_cc_tcc = models.PositiveIntegerFieldPlus('CH mínima de componentes do tipo TCC', null=False, blank=False)
    ch_max_cc_tcc = models.PositiveIntegerFieldPlus('CH máxima de componentes do tipo TCC', null=False, blank=False)

    percentual_min_ead = models.PositiveIntegerFieldPlus('Percentual mínimo de CH EAD', null=False, blank=False, default=0)
    percentual_max_ead = models.PositiveIntegerFieldPlus('Percentual máximo de CH EAD', null=False, blank=False, default=0)

    exige_tcc = models.BooleanField('Exige TCC', default=False)
    exige_colacao_grau = models.BooleanField('Exige colação de grau', default=False)
    exige_enade = models.BooleanField('Exige ENADE', default=False)
    exige_etapa_unica = models.BooleanField(
        'Exige etapa única', default=False, help_text='Exige que os planos de disciplinas contenham apenas uma etapa.'
    )
    emite_certificacao_parcial = models.BooleanField(
        verbose_name='Emite certificação intermediária',
        default=False,
        help_text='Habilita a emissão de certificação intermediária/parcial na matriz.',
    )
    certificado_parcial_acumulavel = models.BooleanField(
        verbose_name='Certificado intermediário acumulável com diploma de conclusão de curso',
        default=False,
        help_text='Permite a emissão de certificado intermediário e diploma de conclusão de curso. Se esta opção for desmarcada o aluno não poderá acumular ambos documentos.',
    )

    equivalencia_hr_ha = models.DecimalFieldPlus(
        'Equivalência h/r e h/a',
        null=False,
        blank=False,
        help_text='Estabelece o cálculo de equivalência da hora/aula em relação à hora/relógio dos componentes. Valor informado será dividido pela quantidade de horas do componente. Exemplo: 0,75',
    )
    equivalencia_hr_credito = models.DecimalFieldPlus(
        'Equivalência h/r e crédito',
        null=False,
        blank=False,
        help_text='Estabelece o cálculo de equivalência da quantidade de crédito em relação à hora/relógio dos componentes. Valor informado será dividido pela quantidade de horas do componente. Exemplo: 20',
    )

    permite_plano_nao_aprovado = models.BooleanField(
        verbose_name='Permite a inclusão de planos de disciplina não aprovados na matriz curricular',
        default=False,
        help_text='Se habilitada, permite a vinculação de planos de disciplina criados por outros PPCs antes da aprovação. Caso essa opção esteja desabilitada, apenas os planos criados pelas comissões do PPC poderão ser vinculados.',
    )

    class Meta:
        verbose_name = 'Diretriz'
        verbose_name_plural = 'Diretrizes'

    def __str__(self):
        return f'{self.descricao} ({self.ano})'

    def get_absolute_url(self):
        return f'/ppc/diretriz/{self.id}/'

    def clean(self):
        if self.percentual_max_ead > 100:
            raise ValidationError('O percentual máximo de CH EAD não pode ser maior do que 100.')
        if not Diretriz.is_diretriz_unica(self):
            raise ValidationError('Já existe uma diretriz para o ano, tipo de oferta e modalidade informados.')
        if self.possui_ppc_revisado():
            raise ValidationError('Esta diretriz não pode ser modificada pois existe PPC em fase de aprovação ou aprovado.')

        if self.qtd_min_periodos and self.qtd_max_periodos and self.qtd_min_periodos > self.qtd_max_periodos:
            raise ValidationError('A quantidade mínima de períodos não pode ser maior do que a quantidade máxima de períodos.')
        if (
            self.qtd_min_disciplina_semestre
            and self.qtd_max_disciplina_semestre
            and self.qtd_min_disciplina_semestre > self.qtd_max_disciplina_semestre
        ):
            raise ValidationError(
                'A quantidade mínima de disciplinas no semestre não pode ser maior do que a quantidade máxima de disciplinas no semestre.'
            )
        if self.ch_semanal_min_semestre and self.ch_semanal_max_semestre and self.ch_semanal_min_semestre > self.ch_semanal_max_semestre:
            raise ValidationError('A carga horária semanal mínima no semestre não pode ser maior do que a carga horária semanal máxima no semestre.')

        if self.certificado_parcial_acumulavel and not self.emite_certificacao_parcial:
            raise ValidationError(
                'A opção "Certificado intermediária acumulável com diploma de conclusão de curso" só pode ser selecionada se a opção "Emite certificação intermediária" estiver ativada.'
            )
        return super().clean()

    def can_change(self, user):
        return self.is_administrador(user) and not self.possui_ppc_revisado()

    def can_delete(self, user):
        return self.is_administrador(user) and not self.possui_ppc()

    def is_administrador(self, user):
        return user.has_perm('ppc.add_diretriz') or AdministradorTipoOferta.is_administrador(user, self.tipo_oferta_id)

    @staticmethod
    def is_diretriz_unica(obj):
        qs = Diretriz.objects.filter(ano_id=obj.ano_id, tipo_oferta_id=obj.tipo_oferta_id, modalidade_id=obj.modalidade_id)
        if obj.id:
            qs = qs.exclude(id=obj.id)
        return not qs.exists()

    def possui_ppc(self):
        return ProjetoPedagogicoCurso.objects.filter(diretriz_id=self.id).exists()

    def possui_ppc_revisado(self):
        return (
            ProjetoPedagogicoCurso.objects.filter(diretriz_id=self.id)
            .exclude(situacao__in=[ProjetoPedagogicoCurso.INICIADO, ProjetoPedagogicoCurso.EM_ELABORACAO, ProjetoPedagogicoCurso.EM_REVISAO])
            .exists()
        )

    def possui_exigencia_eixo(self):
        ids = self.nucleodiretriz_set.values_list('id', flat=True)
        return EixoTecnologicoDiretriz.objects.filter(nucleo_diretriz_id__in=ids).exists()

    def possui_modalidadepraticaprofissional(self):
        return self.ch_min_pratica > 0 or self.ch_max_pratica > 0

    def possui_ch_ead(self):
        return self.percentual_min_ead + self.percentual_max_ead > 0

    @transaction.atomic
    def replicar(self, descricao, ano, estrutura_curso, tipo_oferta, modalidade, arquivo):
        replicado = copy.copy(self)
        replicado.id = None
        replicado.descricao = descricao
        replicado.ano = ano
        replicado.estrutura_curso = estrutura_curso
        replicado.tipo_oferta = tipo_oferta
        replicado.modalidade = modalidade
        replicado.arquivo = arquivo
        replicado.save()

        for nucleo in self.nucleodiretriz_set.all():
            nucleo_replicado = copy.copy(nucleo)
            nucleo_replicado.id = None
            nucleo_replicado.diretriz = replicado
            nucleo_replicado.save()

        for periodo in self.periododiretriz_set.all():
            periodo_replicado = copy.copy(periodo)
            periodo_replicado.id = None
            periodo_replicado.diretriz = replicado
            periodo_replicado.save()

        for componente in self.componenteexigidodiretriz_set.all():
            componente_replicado = copy.copy(componente)
            componente_replicado.id = None
            componente_replicado.diretriz = replicado
            componente_replicado.save()

        return replicado

    def get_ch_max_plano_disciplina(self):
        return (self.ch_max_cc_obrigatorio or 0) + (self.ch_max_cc_optativo or 0) + (self.ch_max_cc_eletivo or 0) + (self.ch_max_cc_tcc or 0)


class NucleoDiretriz(LogModel):
    SEARCH_FIELDS = [
        'nucleo__descricao',
    ]

    diretriz = models.ForeignKeyPlus('ppc.Diretriz', verbose_name='Diretriz', null=False, blank=False)
    nucleo = models.ForeignKeyPlus('edu.Nucleo', verbose_name='Núcleo', null=False, blank=False)
    exige_eixo_tecnologico = models.BooleanField(
        'Exige eixo tecnológico', default=False, help_text='Habilita a vinculação de eixo tecnológico na configuração de núcleo da diretriz.'
    )
    ch_min_pd = models.PositiveIntegerFieldPlus('CH mínima de planos de disciplina', null=False, blank=False)
    ch_max_pd = models.PositiveIntegerFieldPlus('CH máxima de planos de disciplina', null=False, blank=False)
    permite_criacao_plano_disciplina = models.BooleanField('Permite criação de plano de disciplina pela comissão de elaboração do PPC', default=False)
    ch_min_pratica = models.PositiveIntegerFieldPlus('CH mínima de prática profissional', null=False, blank=False)
    ch_max_pratica = models.PositiveIntegerFieldPlus('CH máxima de prática profissional', null=False, blank=False)
    modalidade_pratica_obrigatoria = models.BooleanField(
        'Possui modalidade de prática profissional obrigatória',
        default=False,
        help_text='Habilita o cadastro de modalidades de prática profissional que serão obrigatórias nos PPCs vinculados a esta diretriz.',
    )

    class Meta:
        verbose_name = 'Núcleo da Diretriz'
        verbose_name_plural = 'Núcleos das Diretrizes'
        ordering = ('nucleo__descricao',)

    def __str__(self):
        return f'Núcleo {self.nucleo.descricao} - Diretriz {self.diretriz.descricao}'

    def clean(self):
        if self.id and not self.exige_eixo_tecnologico and self.eixotecnologicodiretriz_set.exists():
            raise ValidationError('Exclua os eixos tecnológicos deste núcleo antes de desmarcar a opção Exige eixo tecnológico.')

        if self.id and not self.modalidade_pratica_obrigatoria and self.modalidadepraticaprofissionaldiretriz_set.exists():
            raise ValidationError(
                'Exclua as modalidades de prática profissional deste núcleo antes de desmarcar a opção Possui modalidade de prática profissional obrigatória.'
            )

        ch_max_pd = self.diretriz.get_ch_max_plano_disciplina()
        ch_min_pd_cadastrada = sum(
            self.diretriz.nucleodiretriz_set.exclude(exige_eixo_tecnologico=True).exclude(id=self.id).values_list('ch_min_pd', flat=True)
        )
        if not self.exige_eixo_tecnologico:
            ch_min_pd_cadastrada += self.ch_min_pd or 0

        for nd in self.diretriz.nucleodiretriz_set.filter(exige_eixo_tecnologico=True):
            eixo = nd.eixotecnologicodiretriz_set.order_by('-ch_min_pd').first()
            ch_min_pd_cadastrada += eixo and eixo.ch_min_pd or 0

        if ch_min_pd_cadastrada > ch_max_pd:
            raise ValidationError(
                f'A soma das cargas horárias mínimas para planos de disciplinas nos núcleos ({ch_min_pd_cadastrada}h) excede à carga horária máxima definida na diretriz ({ch_max_pd}h).'
            )

        ch_max_pratica = self.diretriz.ch_max_pratica
        ch_min_pratica_cadastrada = sum(self.diretriz.nucleodiretriz_set.exclude(id=self.id).values_list('ch_min_pratica', flat=True)) + (
            self.ch_min_pratica or 0
        )

        if ch_min_pratica_cadastrada > ch_max_pratica:
            raise ValidationError(
                f'A soma das cargas horárias mínimas para prática profissional nos núcleos ({ch_min_pratica_cadastrada}h) excede à carga horária máxima definida na diretriz ({ch_max_pratica}h).'
            )

        if self.modalidade_pratica_obrigatoria and self.ch_min_pratica < 1:
            raise ValidationError(
                'A carga horária mínima de prática profissional não pode ser menor do que 1 se o campo Possui modalidade de prática profissional obrigatória estiver marcado.'
            )

        return super().clean()

    def save(self, *args, **kwargs):
        if self.exige_eixo_tecnologico:
            self.ch_min_pd = 0
            self.ch_max_pd = 0
        return super().save(*args, **kwargs)

    def can_delete(self, user=None):
        result = False
        if user and self.diretriz.is_administrador(user):
            if not PlanoDisciplinaPPC.objects.filter(
                matriz_ppc__ppc__diretriz_id=self.diretriz_id, plano_disciplina__nucleo_id=self.nucleo_id
            ).exists():
                result = not ModalidadePraticaProfissionalPPC.objects.filter(
                    matriz_ppc__ppc__diretriz_id=self.diretriz_id, nucleo_id=self.nucleo_id
                ).exists()
        return result

    def get_ch_pd_exigida(self):
        if self.exige_eixo_tecnologico:
            return '-'
        if self.ch_min_pd == self.ch_max_pd:
            return f'{self.ch_min_pd}h'
        return f'{self.ch_min_pd}h a {self.ch_max_pd}h'

    def get_ch_pratica_exigida(self):
        if self.ch_min_pratica == self.ch_max_pratica:
            return f'{self.ch_min_pratica}h'
        return f'{self.ch_min_pratica}h a {self.ch_max_pratica}h'

    def get_ch_min_pd(self, eixo_tecnologico_id=None):
        result = self.ch_min_pd
        if eixo_tecnologico_id:
            eixo = EixoTecnologicoDiretriz.objects.filter(eixo_tecnologico_id=eixo_tecnologico_id, nucleo_diretriz_id=self.id).first()
            result = eixo and eixo.ch_min_pd or result
        return result

    def get_ch_max_pd(self, eixo_tecnologico_id=None):
        result = self.ch_max_pd
        if eixo_tecnologico_id:
            eixo = EixoTecnologicoDiretriz.objects.filter(eixo_tecnologico_id=eixo_tecnologico_id, nucleo_diretriz_id=self.id).first()
            result = eixo and eixo.ch_max_pd or result
        return result


class EixoTecnologicoDiretriz(LogModel):
    nucleo_diretriz = models.ForeignKeyPlus('ppc.NucleoDiretriz', verbose_name='Núcleo da diretriz', null=False, blank=False)
    eixo_tecnologico = models.ForeignKeyPlus('edu.EixoTecnologico', verbose_name='Eixo tecnológico', null=False, blank=False)

    ch_min_pd = models.PositiveIntegerFieldPlus('CH mínima de planos de disciplina', null=False, blank=False)
    ch_max_pd = models.PositiveIntegerFieldPlus('CH máxima de planos de disciplina', null=False, blank=False)

    class Meta:
        verbose_name = 'Eixo tecnológico da diretriz'
        verbose_name_plural = 'Eixos tecnológicos das diretrizes'
        ordering = ('eixo_tecnologico__descricao',)

    def clean(self):
        ch_max_pd = self.nucleo_diretriz.diretriz.get_ch_max_plano_disciplina()
        ch_exigida_nucleo = (
            sum(self.nucleo_diretriz.diretriz.nucleodiretriz_set.exclude(id=self.nucleo_diretriz_id).values_list('ch_min_pd', flat=True))
            + self.ch_min_pd
        )
        if ch_exigida_nucleo > ch_max_pd:
            raise ValidationError(
                f'A soma das cargas horárias mínimas dos núcleos ({ch_exigida_nucleo}h) excede à carga horária máxima definida na diretriz ({ch_max_pd}h).'
            )
        return super().clean()

    def get_ch_pd_exigida(self):
        if self.ch_min_pd == self.ch_max_pd:
            return f'{self.ch_min_pd}h'
        return f'{self.ch_min_pd}h a {self.ch_max_pd}h'


class ModalidadePraticaProfissionalDiretriz(LogModel):
    nucleo_diretriz = models.ForeignKeyPlus('ppc.NucleoDiretriz', verbose_name='Núcleo da diretriz', null=False, blank=False)
    modalidade_pratica_profissional = models.ForeignKeyPlus(
        'edu.ModalidadePraticaProfissional', verbose_name='Modalidade de prática profissional', null=False, blank=False
    )
    optativa = models.BooleanField('Optativa', default=False)
    periodo_inicial = models.PositiveIntegerFieldPlus('Período inicial', min_value=1, null=False, blank=False)
    periodo_final = models.PositiveIntegerFieldPlus('Período final', null=True, blank=True)
    ch_requerida = models.PositiveIntegerFieldPlus('Carga horária requerida', null=True, blank=True)

    class Meta:
        verbose_name = 'Modalidade de prática profissional da diretriz'
        verbose_name_plural = 'Modalidades de prática profissional das diretrizes'

    def clean(self):
        if not self.optativa and not self.ch_requerida:
            raise ValidationError('Informe a carga horária requerida quando a modalidade não for optativa.')
        if not self.optativa:
            ch_max_pratica = self.nucleo_diretriz.ch_max_pratica or 0
            ch_min_pratica_cadastrada = (
                sum(
                    self.nucleo_diretriz.modalidadepraticaprofissionaldiretriz_set.exclude(id=self.id)
                    .exclude(optativa=True)
                    .values_list('ch_requerida', flat=True)
                )
                + self.ch_requerida
            )

            if ch_min_pratica_cadastrada > ch_max_pratica:
                raise ValidationError(
                    f'A soma das cargas horárias para modalidades de prática profissional ({ch_min_pratica_cadastrada}h) excede à carga horária máxima definida neste núcleo ({ch_max_pratica}h).'
                )
        return super().clean()

    def get_periodo(self):
        result = self.periodo_inicial
        if self.periodo_final:
            result = f'{result} a {self.periodo_final}'
        return result


class PeriodoDiretriz(LogModel):
    diretriz = models.ForeignKeyPlus('ppc.Diretriz', verbose_name='Diretriz', null=False, blank=False)
    periodo = models.PositiveIntegerFieldPlus('Período', null=False, blank=False, min_value=1)
    ch_min_componente = models.PositiveIntegerFieldPlus('CH Mínima de Componentes no Período', null=False, blank=False)
    ch_max_componente = models.PositiveIntegerFieldPlus('CH Máxima de Componentes no Período', null=False, blank=False)

    class Meta:
        verbose_name = 'Período da Diretriz'
        verbose_name_plural = 'Períodos das Diretrizes'
        ordering = ('periodo',)

    def clean(self):
        if self.periodo and self.periodo > self.diretriz.qtd_max_periodos:
            raise ValidationError(f'A quantidade máxima de períodos da diretriz é {self.diretriz.qtd_max_periodos}')
        if PeriodoDiretriz.objects.filter(diretriz_id=self.diretriz.pk, periodo=self.periodo).exclude(id=self.pk).exists():
            raise ValidationError(f'O período {self.periodo} já está cadastrado nesta diretriz.')
        ch_max_curso = self.diretriz.ch_max_curso
        ch_exigida_periodo = sum(self.diretriz.periododiretriz_set.values_list('ch_min_componente', flat=True)) + (self.ch_min_componente or 0)
        if ch_exigida_periodo > ch_max_curso:
            raise ValidationError('A soma das cargas horárias mínimas dos períodos não pode ser maior que a CH máxima do curso.')
        if self.ch_min_componente > self.ch_max_componente:
            raise ValidationError('A carga horária mínima de disciplinas não pode ser maior que que a carga horária máxima de disciplinas.')

        return super().clean()

    def can_delete(self, user=None):
        return user and self.diretriz.is_administrador(user)

    def get_ch_exigida(self):
        if self.ch_min_componente == self.ch_max_componente:
            return f'{self.ch_min_componente}h'
        return f'{self.ch_min_componente}h a {self.ch_max_componente}h'


class ComponenteExigidoDiretriz(LogModel):
    diretriz = models.ForeignKeyPlus('ppc.Diretriz', verbose_name='Diretriz', null=False, blank=False)
    nome_componente = models.TextField(
        'Nome do Componente',
        null=False,
        blank=False,
        help_text='separe os nomes de componente por ; caso seja obrigatório pelo menos um dos componentes.',
    )
    ch_min_componente = models.PositiveIntegerFieldPlus(
        'CH Mínima do Componente', null=False, blank=False, help_text='Informe a carga horária mínima do componente em hora/relógio.'
    )
    periodo_oferta = models.CharFieldPlus(
        'Período de Oferta', null=False, blank=True, help_text='separe por ; caso seja permitido a mobilidade do período de oferta do componente.'
    )

    class Meta:
        verbose_name = 'Componente Exigido da Diretriz'
        verbose_name_plural = 'Componentes Exigidos das Diretrizes'

    def can_delete(self, user=None):
        return user and self.diretriz.is_administrador(user)

    def get_ch_exigida(self):
        return f'{self.ch_min_componente}h'


class ModeloPPC(LogModel):
    descricao = models.CharFieldPlus('Descrição')
    data_criacao = models.DateFieldPlus('Data de Criação', auto_now_add=True)
    tipo_oferta = models.ForeignKeyPlus('edu.Modalidade', verbose_name='Tipo de Oferta', null=False, blank=False)
    modalidade = models.ForeignKeyPlus('edu.NaturezaParticipacao', verbose_name='Modalidade', null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=False)
    permite_sobrescrever_ppc = models.BooleanField(
        'Permitir inclusão de seções e conteúdos',
        default=False,
        help_text='Ao habilitar esta opção os conteúdos de todos os PPCs vinculados serão sobrescristos.',
    )

    class Meta:
        verbose_name = 'Modelo de PPC'
        verbose_name_plural = 'Modelos de PPCs'

    def get_absolute_url(self):
        return f'/ppc/modeloppc/{self.id}/'

    def clean(self):
        if (
            self.modalidade_id
            and self.tipo_oferta_id
            and ModeloPPC.objects.filter(ativo=True, tipo_oferta_id=self.tipo_oferta_id, modalidade_id=self.modalidade_id)
            .exclude(id=self.pk)
            .exists()
        ):
            raise ValidationError('Já existe um modelo de PPC ativo para este tipo de oferta e modalidade.')
        return super().clean()

    def can_change(self, user=None):
        return not self.ativo and self.is_administrador(user)

    def is_administrador(self, user):
        return user and (user.has_perm('ppc.add_modeloppc') or AdministradorTipoOferta.is_administrador(user, self.tipo_oferta_id))

    def pode_ativar(self, user):
        return self.is_administrador(user) and not self.ativo and self.secao_set.exists() and not self.possui_secao_sem_conteudo()

    def pode_sobrescrever_conteudo_ppc(self, user):
        return not self.permite_sobrescrever_ppc and self.pode_ativar(user)

    def pode_adicionar_secao(self, user):
        return self.can_change(user) and (not self.possui_ppc() or self.permite_sobrescrever_ppc)

    def pode_editar_secao(self, user):
        return self.can_change(user) and not self.possui_ppc_revisado()

    def pode_inativar(self, user):
        return self.ativo and self.is_administrador(user)

    def possui_ppc(self):
        return ProjetoPedagogicoCurso.objects.filter(modelo_ppc_id=self.id).exists()

    def possui_ppc_revisado(self):
        return (
            ProjetoPedagogicoCurso.objects.filter(modelo_ppc_id=self.id)
            .exclude(situacao__in=[ProjetoPedagogicoCurso.INICIADO, ProjetoPedagogicoCurso.EM_ELABORACAO, ProjetoPedagogicoCurso.EM_REVISAO])
            .exists()
        )

    def possui_secao_sem_conteudo(self):
        return self.secao_set.filter(conteudo__isnull=True).exists()

    @transaction.atomic
    def ativar(self):
        self.ativo = True
        if self.permite_sobrescrever_ppc:
            self.permite_sobrescrever_ppc = False
            self.sobrescrever_conteudos_ppc()
        self.save()

    def sobrescrever_conteudos_ppc(self):
        ppc_ids_to_overwrite = ProjetoPedagogicoCurso.objects.filter(
            modelo_ppc_id=self.pk,
            situacao__in=[ProjetoPedagogicoCurso.INICIADO, ProjetoPedagogicoCurso.EM_ELABORACAO, ProjetoPedagogicoCurso.EM_REVISAO],
        ).values_list('id', flat=True)

        if ppc_ids_to_overwrite:
            # Excluir todos os ConteudoPPC de uma vez
            ConteudoPPC.objects.filter(ppc_id__in=ppc_ids_to_overwrite).delete()

            new_conteudos_ppc = []
            model_conteudos = Conteudo.objects.filter(secao__modelo_ppc_id=self.pk)

            for ppc_id in ppc_ids_to_overwrite:
                for conteudo in model_conteudos:
                    item = ConteudoPPC(
                        conteudo_modelo=conteudo,
                        ppc_id=ppc_id,
                        texto=conteudo.texto or '',
                        situacao=ConteudoPPC.EM_EDICAO if conteudo.editavel else ConteudoPPC.HOMOLOGADO,
                    )
                    new_conteudos_ppc.append(item)

                # Inserir todos os novos ConteudoPPC de uma vez
            ConteudoPPC.objects.bulk_create(new_conteudos_ppc)

    def inativar(self):
        self.ativo = False
        self.save()

    def habilitar_sobrescrita_ppc(self):
        self.permite_sobrescrever_ppc = True
        self.save()

    @transaction.atomic
    def replicar(self, descricao, tipo_oferta, modalidade):
        replicado = ModeloPPC()
        replicado.descricao = descricao
        replicado.tipo_oferta = tipo_oferta
        replicado.modalidade = modalidade
        replicado.save()

        for secao in self.secao_set.all():
            secao_replicada = copy.copy(secao)
            secao_replicada.id = None
            secao_replicada.modelo_ppc = replicado
            secao_replicada.save()
            for conteudo in secao.conteudo_set.all():
                conteudo_replicado = copy.copy(conteudo)
                conteudo_replicado.id = None
                conteudo_replicado.secao = secao_replicada
                conteudo_replicado.save()

        return replicado


class Secao(LogModel):
    titulo = models.CharFieldPlus('Título')
    ordem_exibicao = models.PositiveIntegerFieldPlus('Ordem de Exibição', default=1, min_value=1)
    modelo_ppc = models.ForeignKeyPlus('ppc.ModeloPPC', verbose_name='Modelo de PPC', null=False, blank=False)
    subsecao = models.BooleanField(
        'É subseção',
        default=False,
        help_text='Marque esta opção caso este item deva ser exibido como uma subseção da primeira seção imediatamente acima não marcada como subseção.',
    )

    class Meta:
        verbose_name = 'Seção'
        verbose_name_plural = 'Seções'
        ordering = [
            'ordem_exibicao',
        ]

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        Secao.recalcular_ordem(self)
        return result

    def delete(self, *args, **kwargs):
        Secao.recalcular_ordem(self, delete=True)
        return super().delete(*args, **kwargs)

    @staticmethod
    @transaction.atomic
    def recalcular_ordem(secao, delete=False):
        secoes = Secao.objects.filter(modelo_ppc_id=secao.modelo_ppc_id)
        if delete:
            for seq, item in enumerate(secoes.exclude(id=secao.pk), start=1):
                if item.ordem_exibicao != seq:
                    Secao.objects.filter(id=item.id).update(ordem_exibicao=seq)
        else:
            atualizacao_ordem_exibicao = secao.ordem_exibicao
            if atualizacao_ordem_exibicao < 1:
                atualizacao_ordem_exibicao = 1
            elif atualizacao_ordem_exibicao > secoes.count():
                atualizacao_ordem_exibicao = secoes.count()
            nova_ordem = list(secoes.exclude(id=secao.id))
            nova_ordem.insert(atualizacao_ordem_exibicao - 1, secao)
            for seq, item in enumerate(nova_ordem, start=1):
                if item.ordem_exibicao != seq:
                    Secao.objects.filter(id=item.id).update(ordem_exibicao=seq)

    def can_delete(self, user):
        return user.has_perm('ppc.delete_secao') and self.modelo_ppc.pode_adicionar_secao(user)


class Conteudo(LogModel):
    secao = models.ForeignKeyPlus('ppc.Secao', verbose_name='Seção', null=False, blank=False)
    texto = models.TextField('Texto', null=True, blank=True)
    ordem_exibicao = models.PositiveIntegerField('Ordem de Exibição', null=False, blank=False)
    editavel = models.BooleanField('Editável', default=True)
    orientacao_preenchimento = models.TextField(
        'Orientação de Preenchimento',
        null=True,
        blank=True,
        help_text='Orientação de como o usuário deve preencher esse conteúdo na elaboração do PPC.',
    )

    class Meta:
        verbose_name = 'Conteúdo'
        verbose_name_plural = 'Conteúdos'
        ordering = [
            'secao__ordem_exibicao',
            'ordem_exibicao',
        ]

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        Conteudo.recalcular_ordem(self)
        return result

    def delete(self, *args, **kwargs):
        Conteudo.recalcular_ordem(self, delete=True)
        return super().delete(*args, **kwargs)

    def get_texto(self):
        if self.editavel and not self.texto:
            texto = '[Preenchido no PPC]'
        else:
            texto = self.texto
        return texto

    def get_texto_preview(self):
        dicionario = {
            'nome_curso': '[NOME DO CURSO]',
            'nome_diploma_historico': '[NOME DO CURSO NO DIPLOMA E HISTÓRICO]',
            'eixo_tecnologico': '[NOME DO EIXO TECNOLÓGICO]',
            'quadro_matriz': '[QUADRO DA MATRIZ CURRICULAR DO CURSO]',
            'quadro_requisitos': '[QUADRO DE PRÉ E CO REQUISITOS]',
            'quadro_optativas': '[QUADRO DAS DISCIPLINAS OPTATIVAS]',
            'quebra_de_pagina': Template('<div class="page-break"></div>').render(Context()),
            'ch_curso': '[CH DO CURSO]',
            'ch_matriz': '[CH DAS DISCIPLINAS]',
            'ch_pratica': '[CH DA PRÁTICA PROFISSIONAL]',
        }
        return substituir_marcadores(str(self.texto), dicionario)

    @staticmethod
    @transaction.atomic
    def recalcular_ordem(conteudo, delete=False):
        conteudos = Conteudo.objects.filter(secao_id=conteudo.secao_id)
        if delete:
            for seq, item in enumerate(conteudos.exclude(id=conteudo.pk), start=1):
                if item.ordem_exibicao != seq:
                    Conteudo.objects.filter(id=item.id).update(ordem_exibicao=seq)
        else:
            atualizacao_ordem_exibicao = conteudo.ordem_exibicao
            if atualizacao_ordem_exibicao < 1:
                atualizacao_ordem_exibicao = 1
            elif atualizacao_ordem_exibicao > conteudos.count():
                atualizacao_ordem_exibicao = conteudos.count()
            nova_ordem = list(conteudos.exclude(id=conteudo.id))
            nova_ordem.insert(atualizacao_ordem_exibicao - 1, conteudo)
            for seq, item in enumerate(nova_ordem, start=1):
                if item.ordem_exibicao != seq:
                    Conteudo.objects.filter(id=item.id).update(ordem_exibicao=seq)

    @transaction.atomic
    def tornar_editavel(self):
        self.editavel = True
        self.save()
        for conteudoppc in self.conteudoppc_set.filter(ppc__situacao__in=[ProjetoPedagogicoCurso.INICIADO, ProjetoPedagogicoCurso.EM_ELABORACAO]):
            conteudoppc.situacao = ConteudoPPC.EM_EDICAO
            conteudoppc.save()

    @transaction.atomic
    def tornar_nao_editavel(self):
        self.editavel = False
        self.save()
        for conteudoppc in self.conteudoppc_set.exclude(situacao=ConteudoPPC.HOMOLOGADO):
            conteudoppc.situacao = ConteudoPPC.HOMOLOGADO
            conteudoppc.texto = self.texto
            conteudoppc.save()

    @transaction.atomic
    def atualizar_texto(self, novo_texto):
        self.texto = novo_texto
        self.save()

        if self.editavel:
            for conteudoppc in self.conteudoppc_set.exclude(situacao=ConteudoPPC.HOMOLOGADO):
                conteudoppc.texto = novo_texto
                conteudoppc.save()
        else:
            for conteudoppc in self.conteudoppc_set.filter(
                ppc__situacao__in=[ProjetoPedagogicoCurso.INICIADO, ProjetoPedagogicoCurso.EM_ELABORACAO, ProjetoPedagogicoCurso.EM_REVISAO]
            ):
                conteudoppc.texto = novo_texto
                conteudoppc.save()

    def can_delete(self, user):
        return user.has_perm('ppc.delete_conteudo') and self.secao.modelo_ppc.pode_adicionar_secao(user)

    def pode_tornar_editavel(self, user):
        return not self.editavel and self.secao.modelo_ppc.can_change(user)

    def pode_tornar_nao_editavel(self, user):
        return self.editavel and self.secao.modelo_ppc.can_change(user) and not self.secao.modelo_ppc.possui_ppc_revisado()

    def pode_editar_texto(self, user):
        if self.secao.modelo_ppc.can_change(user):
            if self.editavel:
                return True
            else:
                return (
                    not ProjetoPedagogicoCurso.objects.filter(modelo_ppc_id=self.secao.modelo_ppc_id)
                    .exclude(situacao__in=[ProjetoPedagogicoCurso.INICIADO, ProjetoPedagogicoCurso.EM_ELABORACAO, ProjetoPedagogicoCurso.EM_REVISAO])
                    .exists()
                )

        return False


class SolicitacaoPPC(LogModel):
    DOCUMENTO_NAO_EXISTE = 'Documento não existe!'

    SOLICITADA = '1'
    EMISSAO_ATA = '2'
    INDICACAO_ELABORADORES = '3'
    EM_ANALISE = '4'
    EMISSAO_PORTARIA = '5'
    FINALIZADA = '6'
    REJEITADA = '7'
    SUSPENSA = '8'
    SITUACAO_CHOICES = [
        [SOLICITADA, 'Solicitada'],
        [EMISSAO_ATA, 'Em emissão de ata'],
        [INDICACAO_ELABORADORES, 'Em indicação de elaboradores'],
        [EM_ANALISE, 'Em análise'],
        [EMISSAO_PORTARIA, 'Em emissão de portaria'],
        [FINALIZADA, 'Finalizada'],
        [REJEITADA, 'Reprovada'],
        [SUSPENSA, 'Suspensa'],
    ]

    TIPO_CRIACAO = '1'
    TIPO_ADEQUACAO = '2'
    TIPO_CHOICES = [
        [TIPO_CRIACAO, 'Criação'],
        [TIPO_ADEQUACAO, 'Adequação'],
    ]

    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=SITUACAO_CHOICES, default=SOLICITADA)

    solicitante = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Solicitante', null=False, blank=False, related_name='solicitacaoppc_solicitante_set'
    )
    setor_solicitacao = models.ForeignKeyPlus(
        'rh.Setor', verbose_name='Setor do solicitante', null=False, blank=False, related_name='solicitacaoppc_setor_solicitante_set'
    )
    data_solicitacao = models.DateFieldPlus('Data de solicitação', auto_now_add=True)
    tipo_solicitacao = models.CharFieldPlus(verbose_name='Tipo de solicitação', null=False, blank=False, choices=TIPO_CHOICES, default=TIPO_CRIACAO)

    justificativa = models.TextField('Justificativa', null=False, blank=False)
    tipo_oferta = models.ForeignKeyPlus('edu.Modalidade', verbose_name='Tipo de oferta', null=False, blank=False)
    modalidade = models.ForeignKeyPlus('edu.NaturezaParticipacao', verbose_name='Modalidade', null=False, blank=False)
    eixo_tecnologico = models.ForeignKeyPlus(
        'edu.EixoTecnologico',
        verbose_name='Eixo tecnológico',
        null=True,
        blank=True,
        help_text='Preenchimento obrigatório para criação de PPC de curso de nível médio.',
    )
    ppc_adequacao = models.ForeignKeyPlus(
        'ppc.ProjetoPedagogicoCurso', verbose_name='PPC para adequação', null=True, blank=True, help_text='Informe o PPC que será adequado.'
    )
    nome_curso = models.CharFieldPlus('Nome do curso', null=True, blank=True, help_text='Sugira o nome do curso a ser criado no novo PPC.')

    criador_ata = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Criador da ata', null=True, blank=True, related_name='solicitacaoppc_criador_ata_set'
    )
    data_criacao_ata = models.DateFieldPlus('Data de criação da ata', null=True, blank=True)
    id_ata = models.PositiveIntegerFieldPlus(verbose_name='ID ata', null=True, blank=True, help_text='Identificador do documento Ata do Colegiado.')

    criador_portaria = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Criador da Portaria', null=True, blank=True, related_name='solicitacaoppc_criador_portaria_set'
    )
    data_criacao_portaria = models.DateFieldPlus('Data de criação da portaria', null=True, blank=True)
    id_portaria = models.PositiveIntegerFieldPlus(
        verbose_name='ID portaria', null=True, blank=True, help_text='Identificador do documento Portaria de Elaboração do PPC.'
    )

    motivo_rejeicao = models.TextField('Motivo da rejeição', null=True, blank=False)
    justificativa_correcao = models.TextField('Justificativa da correção', null=True, blank=False)

    convenio = models.ForeignKeyPlus('edu.Convenio', verbose_name='Convênio', null=True, blank=True)
    id_processo_convenio = models.PositiveIntegerFieldPlus(
        verbose_name='ID processo convênio', null=True, blank=True, help_text='Identificador do processo de Convênio.'
    )

    setor_avaliacao = models.ForeignKeyPlus(
        'rh.Setor',
        verbose_name='Setor de avaliação de comissão de elaboração',
        null=True,
        blank=False,
        related_name='solicitacaoppc_setor_avaliacao_set',
    )

    class Meta:
        verbose_name = 'Solicitação de PPC'
        verbose_name_plural = 'Solicitações de PPCs'

    def get_absolute_url(self):
        return f'/ppc/solicitacaoppc/{self.pk}/'

    def __str__(self):
        return self.ppc_adequacao and self.ppc_adequacao.nome_curso or self.nome_curso

    def clean(self):
        if self.situacao == SolicitacaoPPC.REJEITADA and not self.motivo_rejeicao:
            raise ValidationError('Informe a justificativa da rejeição da solicitação de PPC.')
        if self.ppc_adequacao is None and self.is_adequacao():
            raise ValidationError('Informe o PPC para adequação.')
        if not self.nome_curso and self.is_criacao():
            raise ValidationError('Informe o nome do novo curso.')
        if not getattr(self, 'tipo_oferta', None):
            raise ValidationError('Informe o tipo de oferta.')
        if self.tipo_oferta.nivel_ensino_id == NivelEnsino.MEDIO and self.eixo_tecnologico is None:
            raise ValidationError(f'O campo Eixo tecnológico é de preenchimento obrigatório para o tipo de oferta {self.tipo_oferta}.')
        return super().clean()

    def can_delete(self, user):
        return (self.situacao == SolicitacaoPPC.SOLICITADA and self.is_solicitante(user)) or (
            user.has_perm('comum.is_administrador_academico') and self.id_portaria is None
        )

    def is_criacao(self):
        return self.tipo_solicitacao == SolicitacaoPPC.TIPO_CRIACAO

    def is_adequacao(self):
        return self.tipo_solicitacao == SolicitacaoPPC.TIPO_ADEQUACAO

    def is_solicitante(self, user):
        return self.solicitante == user.get_relacionamento()

    def is_avaliador_indicacao(self, user):
        if self.situacao == SolicitacaoPPC.EM_ANALISE:
            diretoria = Diretoria.objects.filter(setor=self.setor_avaliacao).first()
            if diretoria:
                return UsuarioGrupo.objects.filter(
                    user=user, group__name__in=['Diretor Geral', 'Diretor Acadêmico'], setores=self.setor_avaliacao
                ).exists()
            else:
                return self.setor_avaliacao == user.get_vinculo().setor
        return False

    def exige_ata_colegiado(self):
        return self.tipo_oferta_id == Modalidade.FIC_MENOS

    def pode_editar(self, user):
        return self.is_solicitante(user) and self.situacao == SolicitacaoPPC.SOLICITADA

    def pode_avaliar_elaboradores(self, user):
        return self.situacao == SolicitacaoPPC.EM_ANALISE and self.is_avaliador_indicacao(user)

    def pode_solicitar_ata(self, user):
        return self.is_solicitante(user) and self.exige_ata_colegiado() and self.situacao == SolicitacaoPPC.SOLICITADA

    def pode_solicitar_portaria(self, user):
        return (
            self.pode_avaliar_elaboradores(user)
            and self.indicacaoelaboradorppc_set.all().count() > 0
            and not self.indicacaoelaboradorppc_set.filter(deferido=None).exists()
            and self.indicacaoelaboradorppc_set.filter(deferido=True, funcao=ElaboradorPPC.FUNCAO_COORDENADOR).exists()
        )

    def pode_emitir_ata(self, user):
        if self.situacao == SolicitacaoPPC.EMISSAO_ATA and self.id_ata is None:
            if self.setor_solicitacao.uo.eh_reitoria:
                return user.has_perm('comum.is_diretor_academico_sistemico') or user.has_perm('comum.is_reitor')
            else:
                diretoria = Diretoria.objects.filter(setor__uo_id=self.setor_solicitacao.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ENSINO).first()
                if diretoria:
                    return UsuarioGrupo.objects.filter(user=user, group__name__in=['Diretor Geral'], setores=diretoria.setor).exists()
                else:
                    diretoria = Diretoria.objects.filter(setor__uo_id=self.setor_solicitacao.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).first()
                    return UsuarioGrupo.objects.filter(
                        user=user, group__name__in=['Diretor Geral', 'Diretor Acadêmico'], setores=self.setor_solicitacao
                    ).exists()
        return False

    def pode_emitir_portaria(self, user, ignore_id=False):
        if self.situacao == SolicitacaoPPC.EMISSAO_PORTARIA and (ignore_id or self.id_portaria is None):
            if self.setor_avaliacao.uo.eh_reitoria:
                return user.has_perm('comum.is_diretor_academico_sistemico') or user.has_perm('comum.is_reitor')
            else:
                diretoria = Diretoria.objects.filter(setor__uo_id=self.setor_avaliacao.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ENSINO).first()
                if diretoria:
                    return UsuarioGrupo.objects.filter(user=user, group__name='Diretor Geral', setores=diretoria.setor).exists()
                else:
                    diretoria = Diretoria.objects.filter(setor__uo_id=self.setor_avaliacao.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).first()
                    return UsuarioGrupo.objects.filter(user=user, group__name='Diretor Geral', setores=self.setor_avaliacao).exists()
        return False

    def pode_devolver_analise(self, user):
        result = False
        if self.pode_emitir_portaria(user, True):
            result = True
            if self.id_portaria:
                documento = self.get_portaria()
                if documento and documento != SolicitacaoPPC.DOCUMENTO_NAO_EXISTE and (documento.estah_finalizado or documento.estah_assinado):
                    result = False
        return result

    def pode_iniciar_ppc(self):
        return self.situacao == SolicitacaoPPC.FINALIZADA and self.get_ppc() is None

    def pode_indicar_elaborador(self, user):
        if self.is_solicitante(user):
            if self.exige_ata_colegiado():
                return self.situacao == SolicitacaoPPC.INDICACAO_ELABORADORES
            else:
                return self.situacao == SolicitacaoPPC.SOLICITADA
        return False

    def pode_solicitar_avaliacao_elaboradores(self, user):
        result = self.is_solicitante(user)
        if result:
            if self.exige_ata_colegiado():
                result = self.situacao == SolicitacaoPPC.INDICACAO_ELABORADORES
            else:
                result = self.situacao == SolicitacaoPPC.SOLICITADA

        if result and self.tipo_oferta_id == Modalidade.FIC_MENOS:
            result = self.indicacaoelaboradorppc_set.exists()
        return result

    def pode_editar_setor_avaliacao_elaboradores(self, user):
        return (
            self.tipo_oferta_id == Modalidade.FIC_MENOS
            and self.situacao == SolicitacaoPPC.EM_ANALISE
            and (self.is_solicitante(user) or self.is_avaliador_indicacao(user))
            and not self.indicacaoelaboradorppc_set.filter(deferido__isnull=False).exists()
        )

    def get_situacoes(self):
        situacoes = None
        if self.situacao != SolicitacaoPPC.REJEITADA:
            situacoes = copy.copy(SolicitacaoPPC.SITUACAO_CHOICES)
            situacoes.remove([SolicitacaoPPC.REJEITADA, 'Reprovada'])
            if not self.exige_ata_colegiado():
                situacoes.remove([SolicitacaoPPC.EMISSAO_ATA, 'Em emissão de ata'])
                situacoes.remove([SolicitacaoPPC.INDICACAO_ELABORADORES, 'Em indicação de elaboradores'])

        return situacoes

    def get_ppc(self):
        return self.projetopedagogicocurso_set.first()

    def get_situacao_ppc(self):
        if self.situacao == SolicitacaoPPC.REJEITADA:
            result = '-'
        elif self.situacao == SolicitacaoPPC.FINALIZADA:
            ppc = self.get_ppc()
            result = ppc and ppc.get_situacao_display() or 'Parâmetros inválidos'
        else:
            result = 'Aguardando finalização da solicitação'
        return result

    def get_setor_emissao_portaria(self):
        if self.setor_avaliacao.uo.eh_reitoria:
            setor = Setor.objects.suap_ativos().filter(sigla=get_sigla_reitoria()).first()
        else:
            diretoria = Diretoria.objects.filter(setor__uo_id=self.setor_avaliacao.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ENSINO).first()
            if diretoria is None:
                diretoria = Diretoria.objects.filter(setor__uo_id=self.setor_avaliacao.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).first()
            setor = diretoria.setor
        return setor

    def get_setor_emissao_ata(self):
        if self.setor_solicitacao.uo.eh_reitoria:
            setor = Setor.objects.suap_ativos().filter(sigla=get_sigla_reitoria()).first()
        else:
            diretoria = Diretoria.objects.filter(setor__uo_id=self.setor_solicitacao.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ENSINO).first()
            if diretoria is None:
                diretoria = Diretoria.objects.filter(setor__uo_id=self.setor_solicitacao.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).first()
            setor = diretoria.setor
        return setor

    @staticmethod
    def get_solicitacoes_emissao_ata_pendente(queryset, servidor=None):
        qs = queryset.filter(situacao=SolicitacaoPPC.EMISSAO_ATA, id_ata__isnull=True)
        if servidor:
            user = servidor.get_vinculo().user
            pode_reitoria = user.has_perm('comum.is_diretor_academico_sistemico') or user.has_perm('comum.is_reitor')
            diretorias_ensino_por_uo = {
                d.setor.uo_id: d for d in Diretoria.objects.filter(tipo=Diretoria.TIPO_DIRETORIA_ENSINO).select_related('setor')
            }
            diretorias_acad_por_uo = {
                d.setor.uo_id: d for d in Diretoria.objects.filter(tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).select_related('setor')
            }
            setores_dg = set(
                UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user, usuario_grupo__group__name='Diretor Geral').values_list(
                    'setor_id', flat=True
                )
            )
            ids = []
            for q in qs.select_related('setor_solicitacao__uo'):
                if q.setor_solicitacao.uo.eh_reitoria:
                    if pode_reitoria:
                        ids.append(q.id)
                else:
                    diretoria = diretorias_ensino_por_uo.get(q.setor_solicitacao.uo_id)
                    if diretoria:
                        if diretoria.setor_id in setores_dg:
                            ids.append(q.id)
                    else:
                        # preserva busca por diretoria acadêmica do original (variável não usada no if abaixo)
                        diretorias_acad_por_uo.get(q.setor_solicitacao.uo_id)
                        if q.setor_solicitacao_id in setores_dg:
                            ids.append(q.id)
            qs = qs.filter(id__in=ids)
        return qs.distinct()

    @staticmethod
    def get_solicitacoes_finalizacao_ata_pendente(queryset, servidor=None):
        qs = queryset.filter(situacao=SolicitacaoPPC.EMISSAO_ATA, id_ata__isnull=False)
        if servidor:
            qs = qs.filter(criador_ata=servidor)

        return qs.distinct()

    @staticmethod
    def get_solicitacoes_envio_analise_pendente(queryset, servidor=None):
        qs1 = queryset.filter(situacao=SolicitacaoPPC.SOLICITADA).exclude(tipo_oferta_id=Modalidade.FIC_MENOS)
        qs2 = queryset.filter(
            situacao=SolicitacaoPPC.INDICACAO_ELABORADORES, tipo_oferta_id=Modalidade.FIC_MENOS, indicacaoelaboradorppc__isnull=False
        )
        qs = qs1 | qs2
        if servidor:
            qs = qs.filter(solicitante=servidor)
        return qs.distinct()

    @staticmethod
    def get_solicitacoes_indicacao_pendente(queryset, servidor=None):
        qs = queryset.filter(indicacaoelaboradorppc__isnull=True)
        if servidor:
            qs = qs.filter(solicitante=servidor)
        qs = qs.filter(situacao=SolicitacaoPPC.INDICACAO_ELABORADORES, tipo_oferta_id=Modalidade.FIC_MENOS) | qs.filter(
            situacao=SolicitacaoPPC.SOLICITADA
        ).exclude(tipo_oferta_id=Modalidade.FIC_MENOS)
        return qs.distinct()

    @staticmethod
    def get_solicitacoes_analise_pendente(queryset, servidor=None):
        # TODO: verificar como incluir no qs solicitações que não tem coordenador adicionado.
        qs = queryset.filter(situacao=SolicitacaoPPC.EM_ANALISE)
        qs = qs.filter(indicacaoelaboradorppc__deferido__isnull=True) | qs.filter(indicacaoelaboradorppc__isnull=True)
        if servidor:
            setores_com_diretoria = set(Diretoria.objects.values_list('setor_id', flat=True))
            setores_dg_acad = set(
                UsuarioGrupoSetor.objects.filter(
                    usuario_grupo__user__username=servidor.matricula,
                    usuario_grupo__group__name__in=['Diretor Geral', 'Diretor Acadêmico'],
                ).values_list('setor_id', flat=True)
            )
            setor_vinculo_servidor = servidor.get_vinculo().setor
            ids = []
            for q in qs.distinct().select_related('setor_avaliacao'):
                if q.setor_avaliacao_id in setores_com_diretoria:
                    if q.setor_avaliacao_id in setores_dg_acad:
                        ids.append(q.id)
                else:
                    if q.setor_avaliacao == setor_vinculo_servidor:
                        ids.append(q.id)
            qs = qs.filter(id__in=ids)

        return qs.distinct()

    @staticmethod
    def get_solicitacoes_solicitacao_portaria_pendente(queryset, servidor=None):
        qs = queryset.filter(
            situacao=SolicitacaoPPC.EM_ANALISE, indicacaoelaboradorppc__isnull=False, indicacaoelaboradorppc__funcao=ElaboradorPPC.FUNCAO_COORDENADOR
        ).exclude(indicacaoelaboradorppc__deferido__isnull=True)
        if servidor:
            setores_com_diretoria = set(Diretoria.objects.values_list('setor_id', flat=True))
            setores_dg_acad = set(
                UsuarioGrupoSetor.objects.filter(
                    usuario_grupo__user__username=servidor.matricula,
                    usuario_grupo__group__name__in=['Diretor Geral', 'Diretor Acadêmico'],
                ).values_list('setor_id', flat=True)
            )
            setor_vinculo_servidor = servidor.get_vinculo().setor
            ids = []
            for q in qs.select_related('setor_avaliacao'):
                if q.setor_avaliacao_id in setores_com_diretoria:
                    if q.setor_avaliacao_id in setores_dg_acad:
                        ids.append(q.id)
                else:
                    if q.setor_avaliacao == setor_vinculo_servidor:
                        ids.append(q.id)
            qs = qs.filter(id__in=ids)

        return qs.distinct()

    @staticmethod
    def get_solicitacoes_emissao_portaria_pendente(queryset, servidor=None):
        qs = queryset.filter(situacao=SolicitacaoPPC.EMISSAO_PORTARIA, id_portaria=None)
        if servidor:
            user = servidor.get_vinculo().user
            pode_reitoria = user.has_perm('comum.is_diretor_academico_sistemico') or user.has_perm('comum.is_reitor')
            diretorias_ensino_por_uo = {
                d.setor.uo_id: d for d in Diretoria.objects.filter(tipo=Diretoria.TIPO_DIRETORIA_ENSINO).select_related('setor')
            }
            diretorias_acad_por_uo = {
                d.setor.uo_id: d for d in Diretoria.objects.filter(tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).select_related('setor')
            }
            setores_dg = set(
                UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user, usuario_grupo__group__name='Diretor Geral').values_list(
                    'setor_id', flat=True
                )
            )
            ids = []
            for q in qs.select_related('setor_avaliacao__uo'):
                if q.setor_avaliacao.uo.eh_reitoria:
                    if pode_reitoria:
                        ids.append(q.id)
                else:
                    diretoria = diretorias_ensino_por_uo.get(q.setor_avaliacao.uo_id)
                    if diretoria:
                        if diretoria.setor_id in setores_dg:
                            ids.append(q.id)
                    else:
                        # preserva busca por diretoria acadêmica do original (variável não usada no if abaixo)
                        diretorias_acad_por_uo.get(q.setor_avaliacao.uo_id)
                        if q.setor_avaliacao_id in setores_dg:
                            ids.append(q.id)

            qs = qs.filter(id__in=ids)

        return qs.distinct()

    @staticmethod
    def get_solicitacoes_finalizacao_portaria_pendente(queryset, servidor=None):
        qs = queryset.filter(situacao=SolicitacaoPPC.EMISSAO_PORTARIA, id_portaria__isnull=False)
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoStatus, DocumentoTexto

            ids_portarias = qs.values_list('id_portaria', flat=True)
            ids_portarias_finalizadas = DocumentoTexto.objects.filter(id__in=ids_portarias, status=DocumentoStatus.STATUS_FINALIZADO).values_list(
                'id', flat=True
            )
            qs = qs.exclude(id_portaria__in=ids_portarias_finalizadas)
        if servidor:
            qs = qs.filter(criador_portaria=servidor)

        return qs.distinct()

    @staticmethod
    def get_solicitacoes_geracao_ppc_pendente(queryset):
        qs = queryset.filter(situacao=SolicitacaoPPC.EMISSAO_PORTARIA)
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoStatus, DocumentoTexto

            ids_portarias = qs.values_list('id_portaria', flat=True)
            ids_portarias_finalizadas = DocumentoTexto.objects.filter(id__in=ids_portarias, status=DocumentoStatus.STATUS_FINALIZADO).values_list(
                'id', flat=True
            )
            qs = qs.filter(id_portaria__in=ids_portarias_finalizadas)
        return qs.distinct()

    def notificar(
        self,
        mensagem,
        notificar_solicitante=False,
        notificar_emissor_ata=False,
        notificar_emissor_portaria=False,
        notificar_colegiado=False,
        notificar_avaliador=False,
        notificar_elaboradores=False,
    ):
        vinculo_ids = set()
        if notificar_colegiado:
            vinculo_ids.update(self.membrocolegiado_set.values_list('servidor__vinculos', flat=True))

        if notificar_avaliador and self.setor_avaliacao:
            vinculo_ids.update(self._vinculos_gestor_setor(self.setor_avaliacao))

        if notificar_emissor_ata:
            vinculo_ids.update(self._vinculos_emissor(self.setor_solicitacao))

        if notificar_emissor_portaria:
            vinculo_ids.update(self._vinculos_emissor(self.setor_avaliacao))

        if notificar_elaboradores:
            vinculo_ids.update(self.indicacaoelaboradorppc_set.filter(deferido=True).values_list('vinculo_id', flat=True))

        destinatarios = set(Vinculo.objects.filter(id__in=vinculo_ids)) if vinculo_ids else set()
        if notificar_solicitante:
            destinatarios.add(self.solicitante.get_vinculo())

        if not destinatarios:
            return

        url = f'{settings.SITE_URL}{self.get_absolute_url()}'
        titulo = '[SUAP] PPC: Atualização de solicitação de PPC'
        corpo = f"""<h1>Atualização de solicitação de PPC</h1>
            <p>{mensagem}</p>
            <p class="more-info">Para mais informações, acesse: <a href="{url}">{url}</a></p>"""
        send_notification(titulo, corpo, settings.DEFAULT_FROM_EMAIL, destinatarios)

    def _vinculos_gestor_setor(self, setor):
        diretoria = Diretoria.objects.filter(setor=setor).first()
        if diretoria:
            return UsuarioGrupo.objects.filter(group__name__in=['Diretor Geral', 'Diretor Acadêmico'], setores=setor).values_list(
                'user__vinculo', flat=True
            )
        return Servidor.objects.ativos().filter(setor=setor).values_list('vinculos', flat=True)

    def _vinculos_emissor(self, setor):
        if setor.uo.eh_reitoria:
            return UsuarioGrupo.objects.filter(group__name__in=['Diretor Acadêmico Sistêmico', 'Reitor']).values_list('user__vinculo', flat=True)

        diretoria_ensino = Diretoria.objects.filter(setor__uo_id=setor.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ENSINO).first()
        if diretoria_ensino:
            return UsuarioGrupo.objects.filter(group__name='Diretor Geral', setores=diretoria_ensino.setor).values_list('user__vinculo', flat=True)

        diretoria_academica = Diretoria.objects.filter(setor__uo_id=setor.uo_id, tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA).first()
        if diretoria_academica:
            return UsuarioGrupo.objects.filter(group__name__in=['Diretor Geral', 'Diretor Acadêmico'], setores=diretoria_academica.setor).values_list(
                'user__vinculo', flat=True
            )
        return []

    @transaction.atomic
    def enviar_analise(self, user, setor=None):
        if self.setor_avaliacao is None:
            if setor is None:
                raise ValidationError('Setor de avaliação da comissão de elaboração não foi informado.')
            else:
                self.setor_avaliacao = setor
        if self.pode_solicitar_avaliacao_elaboradores(user) or self.pode_editar_setor_avaliacao_elaboradores(user):
            self.situacao = SolicitacaoPPC.EM_ANALISE
            self.justificativa_correcao = None
            self.save()
            MovimentacaoSolicitacaoPPC.registrar_movimentacao(user, self)
            self.notificar(f'A solicitação de PPC {self} foi enviada para análise.', notificar_avaliador=True)

    @transaction.atomic
    def devolver_analise(self, user):
        if self.pode_devolver_analise(user):
            self.situacao = SolicitacaoPPC.EM_ANALISE
            self.justificativa_correcao = None
            self.save()
            MovimentacaoSolicitacaoPPC.registrar_movimentacao(user, self)
            self.notificar(f'A solicitação de PPC {self} foi devolvida para análise.', notificar_avaliador=True)

    @transaction.atomic
    def solicitar_ata(self, user):
        if self.pode_solicitar_ata(user):
            self.situacao = SolicitacaoPPC.EMISSAO_ATA
            self.save()
            MovimentacaoSolicitacaoPPC.registrar_movimentacao(user, self)
            self.notificar(f'Foi solicitada a emissão de ata da solicitação de PPC {self}.', notificar_emissor_ata=True)

    @transaction.atomic
    def solicitar_portaria(self, user):
        if self.pode_solicitar_portaria(user):
            self.situacao = SolicitacaoPPC.EMISSAO_PORTARIA
            self.save()
            MovimentacaoSolicitacaoPPC.registrar_movimentacao(user, self)
            self.notificar(
                f'Foi solicitada a emissão de portaria de elaboração de PPC da solicitação de PPC {self}',
                notificar_emissor_portaria=True,
                notificar_solicitante=True,
                notificar_elaboradores=True,
            )

    @transaction.atomic
    def devolver(self, user):
        if self.pode_avaliar_elaboradores(user) or self.pode_emitir_portaria(user):
            self.situacao = SolicitacaoPPC.SOLICITADA
            self.save()
            MovimentacaoSolicitacaoPPC.registrar_movimentacao(user, self)
            self.notificar(
                f'A solicitação de PPC {self} foi devolvida com a justificativa: {self.justificativa_correcao}.', notificar_solicitante=True
            )

    @transaction.atomic
    def rejeitar(self, user):
        if self.pode_emitir_portaria(user):
            self.situacao = SolicitacaoPPC.REJEITADA
            self.save()
            MovimentacaoSolicitacaoPPC.registrar_movimentacao(user, self)
            self.notificar(f'A solicitação de PPC {self} foi reprovada com a justificativa: {self.motivo_rejeicao}.', notificar_solicitante=True)

    @transaction.atomic
    def iniciar_ppc(self):
        modelo = ModeloPPC.objects.filter(tipo_oferta_id=self.tipo_oferta.id, modalidade_id=self.modalidade.id, ativo=True).first()
        if modelo is None:
            self.situacao = SolicitacaoPPC.EMISSAO_PORTARIA
            raise ValidationError('Não existe modelo de PPC ativo para esta solicitação.')

        diretriz = Diretriz.objects.filter(tipo_oferta_id=self.tipo_oferta.id, modalidade_id=self.modalidade_id).order_by('-ano__ano').first()
        if diretriz is None:
            self.situacao = SolicitacaoPPC.EMISSAO_PORTARIA
            raise ValidationError('Não existe diretriz de PPC para esta solicitação.')

        if diretriz.possui_exigencia_eixo():
            if not EixoTecnologicoDiretriz.objects.filter(
                nucleo_diretriz__diretriz_id=diretriz.pk, eixo_tecnologico_id=self.eixo_tecnologico_id
            ).exists():
                raise ValidationError('O eixo tecnológico desta solicitação não existe na diretriz de PPC para esta solicitação.')

        ppc = ProjetoPedagogicoCurso()
        ppc.modelo_ppc = modelo
        ppc.diretriz = diretriz
        ppc.nome_curso = self.nome_curso or self.ppc_adequacao.nome_curso
        ppc.titulo_certificado_masculino = self.ppc_adequacao.titulo_certificado_masculino if self.ppc_adequacao else None
        ppc.titulo_certificado_feminino = self.ppc_adequacao.titulo_certificado_feminino if self.ppc_adequacao else None
        ppc.situacao = ProjetoPedagogicoCurso.INICIADO
        ppc.solicitacao = self
        ppc.ch_curso = diretriz.ch_min_curso
        ppc.ch_pratica = diretriz.ch_min_pratica
        ppc.ch_cc_obrigatorio = diretriz.ch_min_cc_obrigatorio
        ppc.ch_cc_optativo = diretriz.ch_min_cc_optativo
        ppc.ch_cc_eletivo = diretriz.ch_min_cc_eletivo
        ppc.ch_cc_regular = diretriz.ch_min_cc_regular
        ppc.ch_cc_extensao = diretriz.ch_min_cc_extensao
        ppc.ch_cc_tcc = diretriz.ch_min_cc_tcc
        ppc.ch_ac = diretriz.ch_min_ac
        ppc.ch_atpa = diretriz.ch_min_atpa
        ppc.save()

        matrizppc = MatrizPPC.objects.create(ppc=ppc, nome=ppc.nome_curso)
        # Diretriz não possui prática profissional
        if not diretriz.possui_modalidadepraticaprofissional():
            matrizppc.situacao_modalidadepraticaprofissional = MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_APROVADA
            matrizppc.save()

        MovimentacaoPPC.registrar_movimentacao(None, ppc)

        for conteudo in Conteudo.objects.filter(secao__modelo_ppc_id=modelo.pk):
            item = ConteudoPPC()
            item.conteudo_modelo = conteudo
            item.ppc = ppc
            item.texto = conteudo.texto or ''
            item.situacao = ConteudoPPC.EM_EDICAO if conteudo.editavel else ConteudoPPC.HOMOLOGADO
            item.save()

        for indicacao in self.indicacaoelaboradorppc_set.filter(deferido=True):
            elaborador = ElaboradorPPC()
            elaborador.vinculo = indicacao.vinculo
            elaborador.funcao = indicacao.funcao
            elaborador.permissao = (
                indicacao.funcao == ElaboradorPPC.FUNCAO_COORDENADOR and ElaboradorPPC.PERMISSAO_EDICAO or ElaboradorPPC.PERMISSAO_LEITURA
            )
            elaborador.ppc = ppc
            elaborador.data_inicial = datetime.date.today()
            elaborador.save()

        for item in ModalidadePraticaProfissionalDiretriz.objects.filter(
            nucleo_diretriz__diretriz_id=diretriz.pk, nucleo_diretriz__modalidade_pratica_obrigatoria=True
        ):
            modalidade = ModalidadePraticaProfissionalPPC()
            modalidade.matriz_ppc = matrizppc
            modalidade.modalidade_pratica_profissional = item.modalidade_pratica_profissional
            modalidade.optativa = item.optativa
            modalidade.periodo_inicial = item.periodo_inicial
            modalidade.periodo_final = item.periodo_final
            modalidade.ch_requerida = item.ch_requerida
            modalidade.nucleo = item.nucleo_diretriz.nucleo
            modalidade.exigido_diretriz = True
            modalidade.save()

        if ppc.elaboradorppc_set.exists():
            ppc.situacao = ProjetoPedagogicoCurso.EM_ELABORACAO
            ppc.save()
            MovimentacaoPPC.registrar_movimentacao(None, ppc)
            ppc.notificar(
                f'O PPC {ppc} foi criado com sucesso e está disponível para elaboração.', notificar_solicitante=True, notificar_elaboradores=True
            )
        else:
            ppc.notificar(f'O PPC {ppc} foi criado com sucesso e está aguardando a início da fase de elaboração.', notificar_solicitante=True)

    @transaction.atomic
    def emitir_ata(self, user):
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import (
                CompartilhamentoDocumentoPessoa,
                Documento,
                DocumentoTexto,
                EstagioProcessamentoVariavel,
                ModeloDocumento,
            )
            from documento_eletronico.utils import get_variaveis

            nome_modelo = Configuracao.get_valor_por_chave('ppc', 'nome_modelo_ata') or 'Ata simples'
            modelo = ModeloDocumento.objects.get(nome=nome_modelo)
            variaveis = get_variaveis(
                documento_identificador='',
                estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
                usuario=user,
                setor_dono=self.get_setor_emissao_ata(),
            )
            documento = DocumentoTexto.adicionar_documento_texto(
                usuario=user,
                modelo=modelo,
                assunto='Ata de Avaliação de Solicitação de PPC',
                nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
                variaveis=variaveis,
                setor_dono=self.get_setor_emissao_ata(),
            )

            documento.save()

            if self.solicitante != user.get_relacionamento():
                compartilhamento = CompartilhamentoDocumentoPessoa()
                compartilhamento.usuario_criacao = user
                compartilhamento.documento = documento
                compartilhamento.vinculo_permitido = self.solicitante.get_vinculo()
                compartilhamento.save()

            for avaliador in self.membrocolegiado_set.all():
                compartilhamento = CompartilhamentoDocumentoPessoa()
                compartilhamento.usuario_criacao = user
                compartilhamento.documento = documento
                compartilhamento.vinculo_permitido = avaliador.servidor.get_vinculo()
                compartilhamento.save()

            self.id_ata = documento.id
            self.criador_ata = user.get_relacionamento()
            self.data_criacao_ata = datetime.datetime.now()
            self.save()

            self.notificar(f'A ata do colegiado da solicitação de PPC {self} foi gerada.', notificar_solicitante=True, notificar_colegiado=True)

    @transaction.atomic
    def emitir_portaria(self, user):
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import Documento, DocumentoTexto, EstagioProcessamentoVariavel, ModeloDocumento
            from documento_eletronico.utils import get_variaveis

            nome_modelo = Configuracao.get_valor_por_chave('ppc', 'nome_modelo_portaria') or 'Portaria Simples'
            try:
                modelo = ModeloDocumento.objects.get(nome=nome_modelo)
            except ModeloDocumento.DoesNotExist:
                raise ValidationError(
                    f'O modelo de portaria "{nome_modelo}" não foi encontrado. Entre em contato com o Administrador de PPC para correção da configuração.'
                )
            variaveis = get_variaveis(
                documento_identificador='',
                estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
                usuario=user,
                setor_dono=self.get_setor_emissao_portaria(),
            )
            documento = DocumentoTexto.adicionar_documento_texto(
                usuario=user,
                modelo=modelo,
                assunto='Portaria de Autorização de Solicitação de PPC',
                nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
                variaveis=variaveis,
                setor_dono=self.get_setor_emissao_portaria(),
            )

            documento.save()

            self.id_portaria = documento.id
            self.criador_portaria = user.get_relacionamento()
            self.data_criacao_portaria = datetime.datetime.now()
            self.save()

            self.notificar(
                f'A portaria de elaboração do PPC da solicitação de PPC {self} foi gerada.', notificar_solicitante=True, notificar_elaboradores=True
            )

    @transaction.atomic
    def atualizar_situacao(self, documento=None):
        if documento == SolicitacaoPPC.DOCUMENTO_NAO_EXISTE:
            pass
        elif documento:
            if documento.estah_finalizado:
                if self.situacao == SolicitacaoPPC.EMISSAO_ATA and self.id_ata == documento.id:
                    self.situacao = SolicitacaoPPC.INDICACAO_ELABORADORES
                    self.save()
                    MovimentacaoSolicitacaoPPC.registrar_movimentacao(None, self)
                    self.notificar(
                        f'A ata do colegiado da solicitação de PPC {self} foi finalizada.', notificar_solicitante=True, notificar_colegiado=True
                    )
                elif self.situacao == SolicitacaoPPC.EMISSAO_PORTARIA and self.id_portaria == documento.id:
                    self.situacao = SolicitacaoPPC.FINALIZADA
                    self.save()
                    MovimentacaoSolicitacaoPPC.registrar_movimentacao(None, self)
        else:
            if self.situacao == SolicitacaoPPC.EMISSAO_ATA and self.id_ata:
                documento = self.get_ata()
                if documento == SolicitacaoPPC.DOCUMENTO_NAO_EXISTE:
                    self.id_ata = None
                    self.save()
                elif documento and documento.estah_finalizado:
                    self.situacao = SolicitacaoPPC.INDICACAO_ELABORADORES
                    self.save()
                    MovimentacaoSolicitacaoPPC.registrar_movimentacao(None, self)
                    self.notificar(
                        f'A ata do colegiado da solicitação de PPC {self} foi finalizada.', notificar_solicitante=True, notificar_colegiado=True
                    )

            elif self.situacao == SolicitacaoPPC.EMISSAO_PORTARIA and self.id_portaria:
                documento = self.get_portaria()
                if documento == SolicitacaoPPC.DOCUMENTO_NAO_EXISTE:
                    self.id_portaria = None
                    self.save()
                elif documento and documento.estah_finalizado:
                    self.situacao = SolicitacaoPPC.FINALIZADA
                    self.save()
                    MovimentacaoSolicitacaoPPC.registrar_movimentacao(None, self)

        if self.pode_iniciar_ppc():
            self.iniciar_ppc()
            self.notificar(
                f'A portaria de elaboração do PPC da solicitação de PPC {self} foi finalizada.',
                notificar_solicitante=True,
                notificar_elaboradores=True,
            )
        return self

    def get_ata(self):
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoTexto

            try:
                return self.id_ata and DocumentoTexto.objects.get(id=self.id_ata)
            except DocumentoTexto.DoesNotExist:
                return SolicitacaoPPC.DOCUMENTO_NAO_EXISTE
        return None

    def get_portaria(self):
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoTexto

            try:
                return self.id_portaria and DocumentoTexto.objects.get(id=self.id_portaria)
            except DocumentoTexto.DoesNotExist:
                return SolicitacaoPPC.DOCUMENTO_NAO_EXISTE
        return None

    def get_processo_convenio(self):
        if 'processo_eletronico' in settings.INSTALLED_APPS:
            from processo_eletronico.models import Processo

            return self.id_processo_convenio and Processo.objects.get(id=self.id_processo_convenio)
        return None

    def get_nome_curso(self):
        return self.ppc_adequacao and self.ppc_adequacao.nome_curso or self.nome_curso


class MembroColegiado(LogModel):
    solicitacao = models.ForeignKeyPlus('ppc.SolicitacaoPPC', verbose_name='Solicitação de PPC', null=False, blank=False)
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', null=False, blank=False)

    class Meta:
        verbose_name = 'Membro de colegiado'
        verbose_name_plural = 'Membros de colegiados'

    def can_delete(self, user):
        return self.solicitacao.pode_emitir_ata(user) or self.solicitacao.pode_solicitar_ata(user)


class ProjetoPedagogicoCurso(LogModel):
    DOCUMENTO_NAO_EXISTE = 'Documento não existe!'

    INICIADO = '1'
    EM_ELABORACAO = '2'
    EM_REVISAO = '3'
    ANALISE_PROREITORIA = '4'
    ANALISE_CAMARA = '5'
    ANALISE_CONSEPEX = '6'
    ANALISE_CONSUP = '7'
    APROVADO = '8'
    FINALIZADO = '9'
    REJEITADO = '10'
    SITUACAO_CHOICES = [
        [INICIADO, 'Iniciado'],
        [EM_ELABORACAO, 'Em elaboração'],
        [EM_REVISAO, 'Em revisão'],
        [ANALISE_PROREITORIA, 'Em análise da Pró-Reitoria'],
        [ANALISE_CAMARA, 'Em análise da Câmara'],
        [ANALISE_CONSEPEX, 'Em análise do CONSEPEX'],
        [ANALISE_CONSUP, 'Em análise do CONSUP'],
        [APROVADO, 'Aprovado'],
        [FINALIZADO, 'Finalizado'],
        [REJEITADO, 'Reprovado'],
    ]

    TIPO_TRAMITACAO_CRIACAO = 1
    TIPO_TRAMITACAO_ADEQUACAO = 2
    TIPO_TRAMITACAO_CHOICES = [
        [TIPO_TRAMITACAO_CRIACAO, 'Criação'],
        [TIPO_TRAMITACAO_ADEQUACAO, 'Adequação'],
    ]

    DECISAO_APROVAR = '1'
    DECISAO_APROVAR_RESSALVA = '2'
    DECISAO_SOLICITAR_CORRECAO = '3'
    DECISAO_REJEITAR = '4'

    DECISAO_CHOICES = [
        [DECISAO_APROVAR, 'Aprovar'],
        [DECISAO_APROVAR_RESSALVA, 'Aprovar com ressalva'],
        [DECISAO_SOLICITAR_CORRECAO, 'Solicitar correção'],
        [DECISAO_REJEITAR, 'Reprovar'],
    ]

    DECISAO_INFO_CHOICES = [
        [DECISAO_APROVAR, 'O PPC avançará para a próxima etapa.'],
        [DECISAO_APROVAR_RESSALVA, 'O PPC retornará para a etapa de revisão e após conclusão da revisão NÃO voltará para está etapa.'],
        [DECISAO_SOLICITAR_CORRECAO, 'O PPC retornará para a etapa de revisão e após conclusão da revisão voltará para análise desta etapa.'],
        [DECISAO_REJEITAR, 'O PPC será finalizado com a situação Reprovado.'],
    ]

    nome_curso = models.CharFieldPlus('Nome do curso', null=False, blank=False, help_text='Nome do curso visualizado no SUAP')
    nome_diploma_historico = models.CharFieldPlus(
        'Nome no diploma e histórico', null=True, blank=True, help_text='Nome do curso que deverá aparecer no diploma e histórico'
    )
    titulo_certificado_masculino = models.CharFieldPlus(
        'Título do certificado de conclusão - Masculino',
        blank=True,
        null=True,
        help_text='Título conferido aos concluintes do sexo masculino que constará no certificado/diploma',
    )
    titulo_certificado_feminino = models.CharFieldPlus(
        'Título do certificado de conclusão - Feminino',
        blank=True,
        null=True,
        help_text='Título conferido aos concluintes do sexo feminino que constará no certificado/diploma',
    )

    modelo_ppc = models.ForeignKeyPlus('ppc.ModeloPPC', verbose_name='Modelo de PPC', null=False, blank=False)
    diretriz = models.ForeignKeyPlus('ppc.Diretriz', verbose_name='Diretriz', null=False, blank=False)
    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=SITUACAO_CHOICES, default=INICIADO)
    vigente = models.BooleanField('Vigente', default=False)
    solicitacao = models.ForeignKeyPlus('ppc.SolicitacaoPPC', verbose_name='Solicitacao de PPC', null=False, blank=False)

    codigo_censup = models.CharFieldPlus('Código CENSUP', null=True, blank=True)
    codigo_educacenso = models.CharFieldPlus('Código EDUCACENSO', null=True, blank=True)
    codigo_emec = models.CharFieldPlus('Código e-MEC', null=True, blank=True)
    codigo_sistec = models.CharFieldPlus(
        'Código SISTEC',
        null=True,
        blank=True,
        help_text='Separar por ";" sem espaço caso exista mais de um código cadastrado no SISTEC para esse curso. Ex: 00001;00002',
    )
    area_concentracao = models.ForeignKeyPlus('edu.AreaConcentracao', verbose_name='Área de Concentração', null=True, blank=True)
    programa = models.CharFieldPlus('Programa', blank=True, null=True)
    formacao_de_professores = models.BooleanField(
        'Formação de Professores', help_text='Marque essa opção caso se trate de um curso de formação de professores', default=False
    )
    periodicidade = models.PositiveIntegerField('Periodicidade', choices=CursoCampus.PERIODICIDADE_CHOICES, null=True, blank=False)

    # CH PPC
    ch_curso = models.PositiveIntegerFieldPlus('CH do Curso', null=True, blank=False, min_value=1)
    ch_cc_obrigatorio = models.PositiveIntegerFieldPlus('CH de componentes obrigatórios', blank=False, default=0)
    ch_cc_optativo = models.PositiveIntegerFieldPlus('CH de componentes optativos', blank=False, default=0)
    ch_cc_eletivo = models.PositiveIntegerFieldPlus('CH de componentes eletivos', blank=False, default=0)
    ch_pratica = models.PositiveIntegerFieldPlus('CH de prática profissional', blank=False, default=0)
    ch_ac = models.PositiveIntegerFieldPlus('CH de atividade complementar', blank=False, default=0)
    ch_atpa = models.PositiveIntegerFieldPlus('CH de atividade teórico-prática de aprofundamento', blank=False, default=0)

    ch_cc_regular = models.PositiveIntegerFieldPlus('CH de componentes do tipo regular', blank=False, default=0)
    ch_cc_extensao = models.PositiveIntegerFieldPlus('CH de componentes do tipo atividade de extensão', blank=False, default=0)
    ch_cc_tcc = models.PositiveIntegerFieldPlus('CH de componentes do tipo TCC', blank=False, default=0)

    # revisao
    tipo_tramitacao = models.PositiveIntegerField('Tipo de tramitação', choices=TIPO_TRAMITACAO_CHOICES, null=True, blank=False)
    resolucao_criacao = models.CharFieldPlus(
        'Resolução de aprovação',
        null=True,
        blank=True,
        help_text='Obrigatório informar a resolução de aprovação caso o tipo de tramitação deste PPC seja Adequação.',
    )
    url_resolucao_criacao = models.URLField(
        'Link da resolução criação', blank=True, null=True, help_text='Caso exista, informe o link para visualização do documento da resolução.'
    )

    # proreitoria
    proreitoria = models.ForeignKeyPlus(
        'ppc.ProReitoria',
        verbose_name='Pró-Reitoria',
        null=True,
        blank=False,
        help_text='Informe a Pró-Reitoria que irá continuar a análise deste PPC.',
    )
    rejeitado_proreitoria = models.BooleanField(
        'Reprovado', default=False, help_text='Marque esta opção para reprovar o PPC. Ele será reprovado após finalização do parecer emitido.'
    )
    ad_referendum = models.BooleanField('Ad Referendum', default=False, help_text='Sugere que a tramitação nos conselhos seja Ad Referendum.')
    pular_camara = models.BooleanField(
        'Avançar para CONSEPEX',
        default=False,
        help_text='Caso esta opção seja marcada, o sistema irá pular a análise da câmara e avançará diretamente para a análise do CONSEPEX.',
    )

    # camara
    camara = models.ForeignKeyPlus(
        'ppc.Camara', verbose_name='Câmara', null=True, blank=True, help_text='Informe a Câmara que irá continuar a análise deste PPC.'
    )
    data_convocacao_camara = models.DateFieldPlus('Data da reunião', null=True, blank=True)
    decisao_camara = models.CharFieldPlus(verbose_name='Decisão', null=True, blank=False, choices=DECISAO_CHOICES)
    camara_inexistente = models.BooleanField(
        'Câmara não instituída',
        default=False,
        help_text='Marque esta opção caso a Câmara não esteja formada no momento da análise deste PPC.',
    )

    # consepex
    data_convocacao_consepex = models.DateFieldPlus('Data da reunião', null=True, blank=True)
    decisao_consepex = models.CharFieldPlus(verbose_name='Decisão', null=True, blank=False, choices=DECISAO_CHOICES)
    consepex_inexistente = models.BooleanField(
        'CONSEPEX não instituído',
        default=False,
        help_text='Marque esta opção caso o CONSEPEX da instituição não esteja formado no momento da análise deste PPC.',
    )

    # consup
    data_convocacao_consup = models.DateFieldPlus('Data da reunião', null=True, blank=False)
    decisao_consup = models.CharFieldPlus(verbose_name='Decisão', null=True, blank=False, choices=DECISAO_CHOICES)

    data_aprovacao = models.DateFieldPlus(
        'Data da aprovação',
        null=True,
        blank=True,
        help_text='Corresponde à data da aprovação no CONSEPEX para PPC de adequação ou à data de aprovação no CONSUP para PPC de criação.',
    )
    reitor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Reitor', null=True, blank=False, related_name='ppc_reitor_set')
    proen = models.ForeignKeyPlus('rh.Servidor', verbose_name='Pró-Reitor de Ensino', null=True, blank=False, related_name='ppc_proen_set')
    proex = models.ForeignKeyPlus('rh.Servidor', verbose_name='Pró-Reitor de Extensão', null=True, blank=False, related_name='ppc_proex_set')
    propi = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Pró-Reitor de Pesquisa e Inovação', null=True, blank=False, related_name='ppc_propi_set'
    )

    # curso e matriz
    identificador_ppc = models.CharFieldPlus(
        'Identificador do PPC', null=True, blank=True, help_text='O código identificador do PPC será utilizado na composição do código de curso.'
    )
    cod_outros_cursos = models.CharFieldPlus(
        '',
        null=True,
        blank=True,
    )

    # bibliografia
    bibliografia_html = models.TextField('Bibliografia', null=True, blank=True)

    class Meta:
        verbose_name = 'Projeto pedagógico de curso'
        verbose_name_plural = 'Projetos pedagógicos de curso'

    def __str__(self):
        return f'{self.nome_curso}'

    def get_absolute_url(self, extra=None):
        url = f'/ppc/projetopedagogicocurso/{self.id}/'
        if extra:
            url = f'{url}?{extra}'
        return url

    def clean(self):
        if self.ch_curso < self.diretriz.ch_min_curso or self.ch_curso > self.diretriz.ch_max_curso:
            raise ValidationError(
                f'A carga horária do curso ({self.ch_curso}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_curso}h a {self.diretriz.ch_max_curso}h).'
            )
        if self.ch_pratica < self.diretriz.ch_min_pratica or self.ch_pratica > self.diretriz.ch_max_pratica:
            raise ValidationError(
                f'A carga horária da prática profissional ({self.ch_pratica}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_pratica}h a {self.diretriz.ch_max_pratica}h).'
            )
        if self.ch_cc_obrigatorio < self.diretriz.ch_min_cc_obrigatorio or self.ch_cc_obrigatorio > self.diretriz.ch_max_cc_obrigatorio:
            raise ValidationError(
                f'A carga horária dos componentes curriculares obrigatórios ({self.ch_cc_obrigatorio}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_cc_obrigatorio}h a {self.diretriz.ch_max_cc_obrigatorio}h).'
            )
        if self.ch_cc_optativo < self.diretriz.ch_min_cc_optativo or self.ch_cc_optativo > self.diretriz.ch_max_cc_optativo:
            raise ValidationError(
                f'A carga horária dos componentes curriculares optativos ({self.ch_cc_optativo}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_cc_optativo}h a {self.diretriz.ch_max_cc_optativo}h).'
            )
        if self.ch_cc_eletivo < self.diretriz.ch_min_cc_eletivo or self.ch_cc_eletivo > self.diretriz.ch_max_cc_eletivo:
            raise ValidationError(
                f'A carga horária dos componentes curriculares eletivos ({self.ch_cc_eletivo}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_cc_eletivo}h a {self.diretriz.ch_max_cc_eletivo}h).'
            )
        if self.ch_cc_regular is None:
            self.ch_cc_regular = 0
        if self.ch_cc_regular < self.diretriz.ch_min_cc_regular or self.ch_cc_regular > self.diretriz.ch_max_cc_regular:
            raise ValidationError(
                f'A carga horária para componentes do tipo regular ({self.ch_cc_regular}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_cc_regular}h a {self.diretriz.ch_max_cc_regular}h).'
            )
        if self.ch_cc_extensao is None:
            self.ch_cc_extensao = 0
        if self.ch_cc_extensao < self.diretriz.ch_min_cc_extensao or self.ch_cc_extensao > self.diretriz.ch_max_cc_extensao:
            raise ValidationError(
                f'A carga horária para componentes do tipo atividade de extensão ({self.ch_cc_extensao}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_cc_extensao}h a {self.diretriz.ch_max_cc_extensao}h).'
            )
        if self.ch_cc_tcc is None:
            self.ch_cc_tcc = 0
        if self.ch_cc_tcc < self.diretriz.ch_min_cc_tcc or self.ch_cc_tcc > self.diretriz.ch_max_cc_tcc:
            raise ValidationError(
                f'A carga horária para componentes do tipo TCC ({self.ch_cc_tcc}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_cc_tcc}h a {self.diretriz.ch_max_cc_tcc}h).'
            )
        if self.ch_ac < self.diretriz.ch_min_ac or self.ch_ac > self.diretriz.ch_max_ac:
            raise ValidationError(
                f'A carga horária de atividade complementar ({self.ch_ac}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_ac}h a {self.diretriz.ch_max_ac}h).'
            )
        if self.ch_atpa < self.diretriz.ch_min_atpa or self.ch_atpa > self.diretriz.ch_max_atpa:
            raise ValidationError(
                f'A carga horária de atividade teórico-prática de aprofundamento ({self.ch_cc_tcc}h) está divergente da carga horária definida na diretriz ({self.diretriz.ch_min_atpa}h a {self.diretriz.ch_max_atpa}h).'
            )
        if self.get_ch_exigida_matriz() != self.ch_cc_tcc + self.ch_cc_extensao + self.ch_cc_regular:
            raise ValidationError(
                f'A soma da carga horária dos componentes curriculares dos tipos TCC ({self.ch_cc_tcc}h), extensão ({self.ch_cc_extensao}h) e regular ({self.ch_cc_regular}h) está divergente da carga horária de componentes exigidos na matriz curricular ({self.get_ch_exigida_matriz()}h).'
            )
        ch_atividades = self.get_ch_exigida_matriz() + self.get_ch_exigida_atividades() + self.ch_cc_eletivo
        if self.ch_curso != ch_atividades:
            raise ValidationError(
                f'A carga horária do curso ({self.ch_curso}h) está divergente da soma carga horária das atividades e componentes deste PPC ({ch_atividades}h).'
            )
        if self.diretriz.exige_etapa_unica and self.is_curso_anual():
            raise ValidationError(
                'Este PPC não pode ter periodicidade anual, pois a diretriz exige que os planos de disciplina sejam de apenas uma etapa.'
            )
        return super().clean()

    def get_pendencias(self):
        result = []
        grupos = []

        # INÍCIO DADOS DO CURSO ###

        if self.periodicidade is None:
            result.append(['A periodicidade deste PPC não foi definida.', f'/admin/ppc/projetopedagogicocurso/{self.id}/change/'])

        if self.situacao == ProjetoPedagogicoCurso.APROVADO:
            # definir sufixo que fará parte do código do curso
            if self.identificador_ppc is None:
                result.append(['O código identificador do PPC não foi informado.', f'/admin/ppc/projetopedagogicocurso/{self.pk}/change/'])

        if result:
            grupos.append(['Pendências nos dados do curso', result])
            result = []

        # FIM DADOS DO CURSO ###

        # INÍCIO EQUIPE ###

        # comissão cadastrada
        if not self.elaboradorppc_set.exists():
            result.append(['A comissão de elaboração não foi cadastrada.', 'elaboracao#abas'])

        # revisores cadastrados
        if not self.revisorppc_set.exists():
            result.append(['A equipe de revisão não foi cadastrada.', 'equipe#abas'])

        if result:
            grupos.append(['Pendências da equipe', result])
            result = []

        # FIM EQUIPE ###

        # INÍCIO CONTEUDO ###

        if self.is_em_elaboracao():
            # todos os conteudos de PPC preenchidos
            for i in self.conteudoppc_set.filter(situacao__in=[ConteudoPPC.EM_EDICAO, ConteudoPPC.ENVIADO_CORRECAO]):
                result.append(
                    [
                        f'Existe conteúdo na seção {i.conteudo_modelo.secao.titulo} que não foi enviado para revisão.',
                        f'conteudo#id_secao_{i.conteudo_modelo.secao_id}',
                    ]
                )

        if self.situacao == ProjetoPedagogicoCurso.EM_REVISAO:
            # todos os conteudos de PPC revisados
            qs = self.conteudoppc_set.exclude(situacao__in=[ConteudoPPC.HOMOLOGADO, ConteudoPPC.ENVIADO_CORRECAO])
            for i in qs:
                result.append(
                    [
                        f'Existe conteúdo na seção {i.conteudo_modelo.secao.titulo} que não foi homologado.',
                        f'conteudo#id_secao_{i.conteudo_modelo.secao_id}',
                    ]
                )

        if result:
            grupos.append(['Pendências do conteúdo', result])
            result = []

        # FIM CONTEUDO ###

        # INÍCIO MATRIZES E PRATICA PROFISSIONAL ###
        for matriz_ppc in self.matrizppc_set.all():
            if matriz_ppc.get_pendencias(check_fast=True):
                result.append(
                    [
                        f'Existem pendências na matriz "{matriz_ppc.nome}".',
                        f'{matriz_ppc.get_absolute_url()}?tab=pendencias',
                    ]
                )
        if result:
            grupos.append(['Pendências das matrizes', result])
            result = []

        # FIM MATRIZES E PRATICA PROFISSIONAL ###

        # INÍCIO REITORIA ###

        if self.possui_pendencia_reitoria() and self.situacao != ProjetoPedagogicoCurso.EM_ELABORACAO:
            result.append(['Os dados de Reitor e Pró-Reitores não foram informados.', 'reitoria#abas'])

        if result:
            grupos.append(['Pendências da reitoria', result])
            result = []
        # FIM REITORIA ###

        # INICIO PROREITORIA ###
        if self.proreitoria:
            if self.situacao == ProjetoPedagogicoCurso.ANALISE_PROREITORIA:
                if self.tipo_tramitacao is None:
                    result.append([f'O tipo de tramitação do PPC não foi informada pela {self.proreitoria}.', 'proreitoria#abas'])

            if result:
                grupos.append([f'Pendências da {self.proreitoria}', result])
                result = []
        else:
            if not ProReitoria.objects.filter(ativo=True, tipos_oferta__id=self.diretriz.tipo_oferta_id).exists():
                result.append([f'Não existe pró-reitoria ativa associada ao tipo de oferta {self.get_tipo_oferta()}.', '/admin/ppc/proreitoria/'])

            if result:
                grupos.append(['Pendências da Pró-Reitoria', result])
                result = []
        # FIM PROREITORIA ###

        # INICIO CAMARA ###
        if self.camara is None:
            if not Camara.objects.filter(ativo=True, tipos_oferta__id=self.diretriz.tipo_oferta_id).exists():
                result.append([f'Não existe câmara ativa para o tipo de oferta {self.get_tipo_oferta()}.', '/admin/ppc/camara/'])

            if result:
                grupos.append(['Pendências da Câmara', result])
                result = []
        # FIM CAMARA ###

        return grupos

    def get_criticals(self, user):
        critical = []
        if self.situacao == ProjetoPedagogicoCurso.REJEITADO:
            critical.append(['Este PPC foi reprovado.', False])

        if self.situacao == ProjetoPedagogicoCurso.ANALISE_PROREITORIA:
            if self.proreitoria is None:
                critical.append(['Nenhuma Pró-Reitoria foi associada a este PPC.', False])
            elif self.rejeitado_proreitoria:
                critical.append([f'Este PPC será reprovado após finalização do parecer da {self.proreitoria}.', False])

        if self.situacao == ProjetoPedagogicoCurso.ANALISE_CAMARA:
            if self.decisao_camara == ProjetoPedagogicoCurso.DECISAO_REJEITAR:
                critical.append([f'Este PPC será reprovado após finalização do parecer da {self.camara}.', False])
        return critical

    def get_alerts(self, user):
        alertas = []
        if self.situacao == ProjetoPedagogicoCurso.ANALISE_CAMARA and self.data_convocacao_camara is None and not self.camara_inexistente:
            alertas.append([f'Aguardando a definição dos dados da {self.camara}.', False])

        elif self.situacao == ProjetoPedagogicoCurso.ANALISE_CONSEPEX and self.data_convocacao_consepex is None and not self.consepex_inexistente:
            alertas.append(['Aguardando a definição dos dados do CONSEPEX.', False])

        elif self.situacao == ProjetoPedagogicoCurso.ANALISE_CONSUP and self.data_convocacao_consup is None:
            alertas.append(['Aguardando a definição da data de reunião do CONSUP.', False])

        for documento in self.get_documentos_para_emissao(user):
            alertas.append([f'Aguardando emissão de {documento}.', False])

        for documento in self.documentoppc_set.filter(situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO):
            alertas.append([f'Aguardando finalização do documento {documento.get_documento()}.', 'documentos#abas'])

        return alertas

    def get_infos(self, user):
        infos = []

        if self.situacao == ProjetoPedagogicoCurso.EM_REVISAO:
            if self.decisao_camara in [ProjetoPedagogicoCurso.DECISAO_SOLICITAR_CORRECAO, ProjetoPedagogicoCurso.DECISAO_APROVAR_RESSALVA]:
                infos.append([f'A {self.camara} emitiu parecer indicando ajustes no PPC.', 'documentos#abas'])

        elif self.situacao == ProjetoPedagogicoCurso.ANALISE_CAMARA:
            if self.data_convocacao_camara and self.data_convocacao_camara > datetime.date.today():
                infos.append([f'A reunião da {self.camara} ocorrerá em {format_datetime(self.data_convocacao_camara)}.', 'camara#abas'])

        if self.decisao_consepex is None and self.data_convocacao_consepex and self.data_convocacao_consepex > datetime.date.today():
            infos.append([f'A reunião do CONSEPEX ocorrerá em {format_datetime(self.data_convocacao_consepex)}.', 'consepex#abas'])

        if (
            self.decisao_consup is None
            and self.data_convocacao_consup
            and self.data_convocacao_consup > datetime.date.today()
            and self.possui_aprovacao_consup()
        ):
            infos.append([f'A reunião do CONSUP ocorrerá em {format_datetime(self.data_convocacao_consup)}.', 'consup#abas'])

        if self.situacao in [
            ProjetoPedagogicoCurso.ANALISE_PROREITORIA,
            ProjetoPedagogicoCurso.ANALISE_CAMARA,
            ProjetoPedagogicoCurso.ANALISE_CONSEPEX,
            ProjetoPedagogicoCurso.ANALISE_CONSUP,
        ]:
            if self.ad_referendum:
                infos.append([f'Foi indicado pela {self.proreitoria} a tramitação Ad Referendum deste PPC.', False])

        qs_deliberacao = self.documentoppc_set.filter(tipo_documento=DocumentoPPC.DELIBERACAO)
        if qs_deliberacao.filter(ad_referendum=True).exists() and not qs_deliberacao.filter(ad_referendum=False).exists():
            infos.append(['Foi emitida uma deliberação de aprovação Ad Referendum.', 'documentos#abas'])

        if self.possui_aprovacao_consup():
            qs_resolucao = self.documentoppc_set.filter(tipo_documento=DocumentoPPC.RESOLUCAO)
            if qs_resolucao.filter(ad_referendum=True).exists() and not qs_resolucao.filter(ad_referendum=False).exists():
                infos.append(['Foi emitida uma resolução de aprovação Ad Referendum.', 'documentos#abas'])

        if self.is_em_elaboracao() and (
            self.conteudoppc_set.filter(situacao=ConteudoPPC.AGUARDANDO_REVISAO).exists()
            or self.matrizppc_set.filter(situacao_matriz=MatrizPPC.MATRIZ_AGUARDANDO_REVISAO).exists()
            or self.matrizppc_set.filter(situacao_modalidadepraticaprofissional=MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_REVISAO).exists()
        ):
            infos.append(['A revisão deste PPC só poderá ser iniciada após o envio de todos os conteúdos e matrizes para análise.', False])

        return infos

    def get_alerts_matriz(self):
        alertas = []

        planos_ppc = self.get_planos_disciplina()

        for matriz in self.matrizppc_set.all():
            ids = matriz.planodisciplinappc_set.values_list('plano_disciplina_id', flat=True)
            for pd_ppc in planos_ppc.exclude(id__in=ids):
                alertas.append(f'O plano de disciplina {pd_ppc} não foi vinculado à matriz {matriz.nome}.')
        return alertas

    def get_documentos_aprovadores(self):
        """
        Retorna uma tupla com os documentos que aprovaram o PPC, no formato (<documento ad referendum>, <documento final>).
        """
        tipo_documento_aprovador = DocumentoPPC.RESOLUCAO if self.possui_aprovacao_consup() else DocumentoPPC.DELIBERACAO

        documentos_aprovadores = self.documentoppc_set.order_by('-data_emissao').filter(
            tipo_documento=tipo_documento_aprovador,
            situacao_documento=DocumentoPPC.DOCUMENTO_FINALIZADO,
            decisao__in=[ProjetoPedagogicoCurso.DECISAO_APROVAR, ProjetoPedagogicoCurso.DECISAO_APROVAR_RESSALVA],
        )
        doc_ad_referendum = documentos_aprovadores.filter(ad_referendum=True).first()
        doc_final = documentos_aprovadores.filter(ad_referendum=False).first()

        return doc_ad_referendum, doc_final

    def get_texto_aprovacoes(self):
        doc_ad_referendum, doc_final = self.get_documentos_aprovadores()

        descricao_aprovador = 'xxx'
        if doc_final:
            doc = doc_final.get_documento()
            data_aprovacao = self.data_convocacao_consup if self.possui_aprovacao_consup() else self.data_convocacao_consepex
            descricao_aprovador = f'{doc} de {data_aprovacao.strftime("%d/%m/%Y")}'

        descricao_aprovador_ad_referendum = ''
        if doc_ad_referendum:
            doc = doc_ad_referendum.get_documento()
            descricao_aprovador_ad_referendum = (
                f'{doc} de {doc.get_data_finalizacao().strftime("%d/%m/%Y")} Ad Referendum, homologada pela {descricao_aprovador}'
            )

        if self.is_tramite_criacao():
            aprovacao = descricao_aprovador_ad_referendum or descricao_aprovador
            adequacao = ''
        else:
            aprovacao = self.resolucao_criacao or 'xxx'
            adequacao = descricao_aprovador_ad_referendum or descricao_aprovador

        return f'Projeto Pedagógico de Curso aprovado pela {aprovacao}{f" e adequado pela {adequacao}" if adequacao else ""}.'

    # modalidade do edu
    def get_tipo_oferta(self):
        return self.diretriz.tipo_oferta

    # natureza de participação do edu
    def get_modalidade(self):
        return self.modelo_ppc.modalidade

    def get_ch_exigida_matriz(self):
        soma = 0
        if self.ch_cc_obrigatorio:
            soma += self.ch_cc_obrigatorio
        if self.ch_cc_optativo:
            soma += self.ch_cc_optativo
        return soma

    def get_ch_exigida_atividades(self):
        soma = 0
        if self.ch_pratica:
            soma += self.ch_pratica
        if self.ch_ac:
            soma += self.ch_ac
        if self.ch_atpa:
            soma += self.ch_atpa
        return soma

    def get_ch_exigida_pratica(self, nucleo_id=None):
        qtd = self.get_nucleos_pratica().count()
        if qtd > 1 and nucleo_id:
            return NucleoDiretriz.objects.get(id=nucleo_id).ch_min_pratica
        elif qtd == 1:
            return self.ch_pratica
        else:
            return 0

    def get_nome_nucleo(self, nucleo_diretriz):
        result = nucleo_diretriz.nucleo.descricao
        if nucleo_diretriz.exige_eixo_tecnologico:
            eixo = EixoTecnologicoDiretriz.objects.filter(
                eixo_tecnologico_id=self.solicitacao.eixo_tecnologico_id, nucleo_diretriz_id=nucleo_diretriz.id
            ).first()
            if eixo:
                result = f'{result} ({eixo.eixo_tecnologico.descricao})'
        return result

    def get_ch_pd_exigida(self, nucleo_diretriz):
        if nucleo_diretriz.exige_eixo_tecnologico:
            eixo = EixoTecnologicoDiretriz.objects.filter(
                eixo_tecnologico_id=self.solicitacao.eixo_tecnologico_id, nucleo_diretriz_id=nucleo_diretriz.id
            ).first()
            result = eixo and eixo.get_ch_pd_exigida() or '0'
        else:
            result = nucleo_diretriz.get_ch_pd_exigida()
        return result

    def get_ch_min_pd_exigida(self, nucleo_diretriz):
        if nucleo_diretriz.exige_eixo_tecnologico:
            eixo = EixoTecnologicoDiretriz.objects.filter(
                eixo_tecnologico_id=self.solicitacao.eixo_tecnologico_id, nucleo_diretriz_id=nucleo_diretriz.id
            ).first()
            result = eixo and eixo.ch_min_pd or 0
        else:
            result = nucleo_diretriz.ch_min_pd
        return result

    def get_situacao_conteudo(self):
        result = 'Homologado'
        if self.conteudoppc_set.filter(situacao=ConteudoPPC.EM_EDICAO).exists():
            result = 'Em edição'
        elif self.conteudoppc_set.filter(situacao=ConteudoPPC.AGUARDANDO_REVISAO).exists():
            result = 'Aguardando revisão'
        elif self.conteudoppc_set.filter(situacao=ConteudoPPC.EM_REVISAO).exists():
            result = 'Em revisão'
        elif self.conteudoppc_set.filter(situacao=ConteudoPPC.ENVIADO_CORRECAO).exists():
            result = 'Aguardando correção'
        return result

    def get_secoes_conteudo(self):
        return self.modelo_ppc.secao_set.all().only('id', 'titulo', 'subsecao')

    def get_conteudos_por_secao(self, secao_id):
        return self.conteudoppc_set.filter(conteudo_modelo__secao_id=secao_id)

    def get_portarias(self):
        ids = [self.solicitacao.id_portaria]
        ids_atualizacoes = AtualizacaoComissaoElaboracao.objects.filter(ppc_id=self.id).values_list('id_portaria', flat=True)
        if ids_atualizacoes:
            ids.extend(ids_atualizacoes)
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoTexto

            try:
                return DocumentoTexto.objects.filter(id__in=ids)
            except DocumentoTexto.DoesNotExist:
                return []
        return []

    def get_atualizacao_comissao(self):
        return self.atualizacaocomissaoelaboracao_set.filter(concluida=False).first()

    def get_nucleos_matriz(self):
        return self.diretriz.nucleodiretriz_set.filter(Q(ch_min_pd__gt=0) | Q(exige_eixo_tecnologico=True))

    def get_nucleos_pratica(self):
        return self.diretriz.nucleodiretriz_set.filter(Q(ch_min_pratica__gt=0) | Q(ch_max_pratica__gt=0))

    def get_marcadores_dinamicos(self):
        result = []
        for nd in self.get_nucleos_matriz():
            descricao = nd.nucleo.descricao
            marcador = f'disciplinas_{descricao.replace(" ", "_")}'.lower()
            result.append([retira_acentos(marcador), descricao])
        return result

    def get_pafcs(self):
        result = []
        if 'pafc' in settings.INSTALLED_APPS:
            from pafc.models import PAFC

            return PAFC.objects.filter(ppc_id=self.id)
        return result

    def get_setor_conselhos(self):
        setor_id = Configuracao.get_valor_por_chave('ppc', 'setor_secretaria_conselhos')
        return Setor.objects.suap_ativos().get(id=setor_id)

    def get_documentos_para_emissao(self, user):
        documentos = []
        if self.pode_emitir_parecer_revisao(user) or self.pode_emitir_parecer_camara(user):
            documentos.append('Parecer')

        if self.pode_emitir_despacho_proreitoria(user) or self.pode_emitir_despacho_camara(user) or self.pode_emitir_despacho_consepex(user):
            documentos.append('Despacho')

        deliberacao_regular, deliberacao_ad_referendum, deliberacao_homologacao = self.pode_emitir_deliberacao(user)
        if deliberacao_regular:
            documentos.append('Deliberação')
        if deliberacao_ad_referendum:
            documentos.append('Deliberação Ad Referendum')
        if deliberacao_homologacao:
            documentos.append('Deliberação de homologação')

        resolucao_regular, resolucao_ad_referendum, resolucao_homologacao = self.pode_emitir_resolucao(user)
        if resolucao_regular:
            documentos.append('Resolução')
        if resolucao_ad_referendum:
            documentos.append('Resolução Ad Referendum')
        if resolucao_homologacao:
            documentos.append('Resolução de homologação')

        return documentos

    def get_planos_disciplina(self):
        return PlanoDisciplina.objects.filter(planodisciplinappc__matriz_ppc__ppc_id=self.id).distinct()

    def pode_adicionar_revisor(self, user):
        return (
            user.has_perm('comum.is_administrador_academico')
            or user.has_perm('comum.is_administrador_de_ppc')
            or AdministradorTipoOferta.objects.filter(tipo_oferta_id=self.diretriz.tipo_oferta_id, servidores__matricula=user.username).exists()
        )

    def pode_assumir_revisao(self, user):
        if self.pode_revisar(user):
            return self.conteudoppc_set.filter(situacao=ConteudoPPC.AGUARDANDO_REVISAO).exists()
        return False

    def pode_revisar(self, user):
        return self.situacao == ProjetoPedagogicoCurso.EM_REVISAO and self.is_revisor(user)

    def pode_atualizar_comissao_elaboracao(self, user):
        return user.has_perm('comum.is_administrador_de_ppc') and self.is_comissao_em_atualizacao()

    def pode_adicionar_portaria_elaboracao(self, user):
        return user.has_perm('comum.is_administrador_de_ppc') and not self.is_comissao_em_atualizacao()

    def pode_enviar_elaboracao(self, user):
        return self.situacao == ProjetoPedagogicoCurso.INICIADO and self.is_coordenador_elaboracao(user) and self.elaboradorppc_set.exists()

    def pode_elaborar(self, user):
        return self.is_em_elaboracao() and ElaboradorPPC.is_membro(user, self.id, permissao=ElaboradorPPC.PERMISSAO_EDICAO)

    def pode_informar_reitoria(self, user):
        return self.situacao == ProjetoPedagogicoCurso.EM_REVISAO and self.is_revisor(user)

    def pode_convocar_camara(self, user):
        if self.situacao != ProjetoPedagogicoCurso.ANALISE_CAMARA:
            return False
        if (
            self.camara_inexistente
            and self.documentoppc_set.filter(tipo_documento=DocumentoPPC.DESPACHO, situacao_ppc=ProjetoPedagogicoCurso.ANALISE_CAMARA).exists()
        ):
            return False
        return self.decisao_camara is None and self.is_secretario_camara(user)

    def pode_convocar_consepex(self, user):
        if ProjetoPedagogicoCurso.is_secretario_conselho(user) and self.decisao_consepex is None:
            if (
                self.consepex_inexistente
                and self.documentoppc_set.filter(tipo_documento=DocumentoPPC.DESPACHO, situacao_ppc=ProjetoPedagogicoCurso.ANALISE_CONSEPEX).exists()
            ):
                return False
            if (
                self.situacao == ProjetoPedagogicoCurso.ANALISE_CONSEPEX
                or self.ad_referendum
                and self.documentoppc_set.filter(
                    ad_referendum=True, tipo_documento=DocumentoPPC.DELIBERACAO, situacao_documento=DocumentoPPC.DOCUMENTO_FINALIZADO
                ).exists()
            ):
                return True
        return False

    def pode_convocar_consup(self, user):
        result = False
        if self.possui_aprovacao_consup() and ProjetoPedagogicoCurso.is_secretario_conselho(user) and self.decisao_consup is None:
            if (
                self.situacao == ProjetoPedagogicoCurso.ANALISE_CONSUP
                or self.ad_referendum
                and self.documentoppc_set.filter(
                    ad_referendum=True, tipo_documento=DocumentoPPC.RESOLUCAO, situacao_documento=DocumentoPPC.DOCUMENTO_FINALIZADO
                ).exists()
            ):
                result = True
        return result

    def pode_emitir_documento(self, user, documento):
        documentos = self.get_documentos_para_emissao(user)
        return documento in documentos

    def pode_emitir_parecer_revisao(self, user):
        return (
            self.pode_revisar(user)
            and not self.conteudoppc_set.exclude(situacao=ConteudoPPC.HOMOLOGADO).exists()
            and not self.possui_matrizppc_sem_aprovacao()
            and not self.possui_modalidadepraticaprofissional_sem_aprovacao()
            and not self.get_pendencias()
            and not DocumentoPPC.objects.filter(
                ppc_id=self.id, situacao_ppc=ProjetoPedagogicoCurso.EM_REVISAO, situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO
            ).exists()
        )

    def pode_emitir_despacho_proreitoria(self, user):
        if self.situacao == ProjetoPedagogicoCurso.ANALISE_PROREITORIA:
            eh_chefe_setor = user.eh_servidor and user.get_relacionamento().id in self.proreitoria.setor.historico_funcao().values_list(
                'servidor_id', flat=True
            )
            if (
                eh_chefe_setor
                and not self.documentoppc_set.filter(
                    situacao_ppc=ProjetoPedagogicoCurso.ANALISE_PROREITORIA, situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO
                ).exists()
            ):
                return not self.get_pendencias()
        return False

    def pode_emitir_parecer_camara(self, user):
        if self.camara_inexistente:
            return False
        if self.situacao != ProjetoPedagogicoCurso.ANALISE_CAMARA:
            return False

        return (
            self.data_convocacao_camara
            and datetime.date.today() >= self.data_convocacao_camara
            and (self.is_coordenador_camara(user) or self.is_secretario_camara(user))
            and not self.documentoppc_set.filter(
                situacao_ppc=ProjetoPedagogicoCurso.ANALISE_CAMARA, situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO
            ).exists()
        )

    def pode_emitir_despacho_camara(self, user):
        if not self.camara_inexistente:
            return False
        if self.situacao != ProjetoPedagogicoCurso.ANALISE_CAMARA:
            return False
        doc_criado = self.documentoppc_set.filter(
            situacao_ppc=ProjetoPedagogicoCurso.ANALISE_CAMARA,
            tipo_documento=DocumentoPPC.DESPACHO,
            situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO,
        ).exists()
        return not doc_criado and (self.is_coordenador_camara(user) or self.is_secretario_camara(user))

    def pode_emitir_deliberacao(self, user):
        if self.consepex_inexistente:
            return False, False, False

        pode_regular = False
        pode_ad_referendum = False
        pode_homologacao = False

        if ProjetoPedagogicoCurso.is_presidente_conselho(user) or ProjetoPedagogicoCurso.is_secretario_conselho(user):
            qs = self.documentoppc_set.filter(tipo_documento=DocumentoPPC.DELIBERACAO)
            reuniao_realizada = self.data_convocacao_consepex and datetime.date.today() >= self.data_convocacao_consepex
            if self.situacao == ProjetoPedagogicoCurso.ANALISE_CONSEPEX:
                pode_regular = (
                    reuniao_realizada
                    and self.decisao_consepex is None
                    and not qs.filter(ad_referendum=True, situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO).exists()
                )
                pode_ad_referendum = self.ad_referendum and self.decisao_consepex is None and not qs.filter(ad_referendum=True).exists()
            else:
                pode_homologacao = (
                    self.ad_referendum and reuniao_realizada and self.decisao_consepex is None and qs.filter(ad_referendum=True).exists()
                )

        return pode_regular, pode_ad_referendum, pode_homologacao

    def pode_emitir_resolucao(self, user):
        pode_regular = False
        pode_ad_referendum = False
        pode_homologacao = False

        if self.possui_aprovacao_consup() and (
            ProjetoPedagogicoCurso.is_presidente_conselho(user) or ProjetoPedagogicoCurso.is_secretario_conselho(user)
        ):
            qs = self.documentoppc_set.filter(tipo_documento=DocumentoPPC.RESOLUCAO)
            reuniao_realizada = self.data_convocacao_consup and datetime.date.today() >= self.data_convocacao_consup
            if self.situacao == ProjetoPedagogicoCurso.ANALISE_CONSUP:
                pode_regular = reuniao_realizada and self.decisao_consup is None
                pode_ad_referendum = self.ad_referendum and self.decisao_consup is None and not qs.filter(ad_referendum=True).exists()
            else:
                pode_homologacao = self.ad_referendum and reuniao_realizada and self.decisao_consup is None and qs.filter(ad_referendum=True).exists()

        return pode_regular, pode_ad_referendum, pode_homologacao

    def pode_emitir_despacho_consepex(self, user):
        if self.consepex_inexistente and self.situacao == ProjetoPedagogicoCurso.ANALISE_CONSEPEX:
            doc_criado = self.documentoppc_set.filter(
                situacao_ppc=ProjetoPedagogicoCurso.ANALISE_CONSEPEX,
                tipo_documento=DocumentoPPC.DESPACHO,
                situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO,
            ).exists()
            return not doc_criado and (ProjetoPedagogicoCurso.is_presidente_conselho(user) or ProjetoPedagogicoCurso.is_secretario_conselho(user))

    def pode_finalizar(self, user):
        # PPC deve estar aprovado
        if self.situacao != ProjetoPedagogicoCurso.APROVADO:
            return False
        # usuário deve ser o o administrador acadêmico
        if not user.has_perm('comum.is_administrador_academico'):
            return False
        # todas as matrizes do PPC devem ser geradas no EDU
        if self.matrizppc_set.filter(matriz__isnull=True).exists():
            return False
        # deliberação do consepex deve existir se ele tiver instituído.
        if (
            self.consepex_inexistente
            or self.documentoppc_set.filter(
                ad_referendum=False, tipo_documento=DocumentoPPC.DELIBERACAO, situacao_documento=DocumentoPPC.DOCUMENTO_FINALIZADO
            ).exists()
        ):
            # exige resolução se for criação ou consepex não tiver instituído
            if self.is_tramite_criacao() or self.consepex_inexistente:
                return self.documentoppc_set.filter(
                    ad_referendum=False, tipo_documento=DocumentoPPC.RESOLUCAO, situacao_documento=DocumentoPPC.DOCUMENTO_FINALIZADO
                ).exists()
            return True
        return False

    def pode_gerar_matrizes(self, user):
        result = False
        if (
            not self.rejeitado_proreitoria
            and self.situacao != ProjetoPedagogicoCurso.REJEITADO
            and user.has_perm('comum.is_administrador_academico')
            and self.matrizppc_set.filter(matriz__isnull=True).exists()
        ):
            if self.situacao == ProjetoPedagogicoCurso.APROVADO:
                result = True
            elif Configuracao.get_valor_por_chave('ppc', 'permite_gerar_curso_matriz'):
                result = not self.possui_matrizppc_sem_aprovacao() and not self.possui_modalidadepraticaprofissional_sem_aprovacao()
        return result

    def pode_alterar_modeloppc(self, user):
        modelo = self.modelo_ppc
        if self.is_em_elaboracao() and modelo.can_change(user):
            return ModeloPPC.objects.filter(tipo_oferta_id=modelo.tipo_oferta_id, modalidade_id=modelo.modalidade_id, ativo=True).exists()
        return False

    def possui_matrizppc_sem_aprovacao(self):
        return self.matrizppc_set.exclude(situacao_matriz=MatrizPPC.MATRIZ_APROVADA).exists()

    def possui_matrizppc_pendente_elaboracao(self):
        return self.matrizppc_set.filter(situacao_matriz__in=[MatrizPPC.MATRIZ_EM_ELABORACAO, MatrizPPC.MATRIZ_AGUARDANDO_CORRECAO]).exists()

    def possui_matrizppc_pendente_revisao(self):
        return self.matrizppc_set.filter(situacao_matriz__in=[MatrizPPC.MATRIZ_EM_REVISAO, MatrizPPC.MATRIZ_AGUARDANDO_REVISAO]).exists()

    def possui_modalidadepraticaprofissional_sem_aprovacao(self):
        return self.matrizppc_set.exclude(situacao_modalidadepraticaprofissional=MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_APROVADA).exists()

    def possui_modalidadepraticaprofissional_pendente_elaboracao(self):
        return self.matrizppc_set.filter(
            situacao_modalidadepraticaprofissional__in=[
                MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO,
                MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_CORRECAO,
            ]
        ).exists()

    def possui_modalidadepraticaprofissional_pendente_revisao(self):
        return self.matrizppc_set.filter(
            situacao_modalidadepraticaprofissional__in=[
                MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_REVISAO,
                MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_REVISAO,
            ]
        ).exists()

    def possui_pendencia_reitoria(self):
        return self.reitor is None or self.proen is None or self.proex is None or self.propi is None

    def possui_conteudo_para_edicao(self):
        return self.conteudoppc_set.filter(situacao__in=[ConteudoPPC.EM_EDICAO, ConteudoPPC.ENVIADO_CORRECAO]).exists()

    def possui_conteudo_para_revisao(self):
        return self.conteudoppc_set.filter(situacao__in=[ConteudoPPC.AGUARDANDO_REVISAO, ConteudoPPC.EM_REVISAO]).exists()

    def possui_pendencia_elaboracao(self):
        return (
            self.possui_conteudo_para_edicao()
            or self.possui_matrizppc_pendente_elaboracao()
            or self.possui_modalidadepraticaprofissional_pendente_elaboracao()
        )

    def possui_pendencia_revisao(self):
        return (
            self.possui_conteudo_para_revisao()
            or self.possui_matrizppc_pendente_revisao()
            or self.possui_modalidadepraticaprofissional_pendente_revisao()
        )

    def possui_coordenador_comissao_elaboracao(self):
        return ElaboradorPPC.objects.filter(funcao=ElaboradorPPC.FUNCAO_COORDENADOR, ppc_id=self.id).count() == 1

    def is_curso_anual(self):
        return self.periodicidade == CursoCampus.PERIODICIDADE_ANUAL

    def is_curso_semestral(self):
        return self.periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL

    def is_coordenador_elaboracao(self, user):
        return ElaboradorPPC.is_membro(user, self.id, ElaboradorPPC.FUNCAO_COORDENADOR)

    def is_revisor(self, user):
        if user.eh_servidor:
            return self.revisorppc_set.filter(servidor=user.get_relacionamento()).exists()
        return False

    def is_secretario_camara(self, user):
        return self.camara and self.camara.secretario and self.camara.secretario.matricula == user.username

    def is_coordenador_camara(self, user):
        return self.camara and self.camara.coordenador and self.camara.coordenador.matricula == user.username

    @staticmethod
    def is_presidente_conselho(user):
        diretoria = Diretoria.objects.filter(tipo=Diretoria.TIPO_SISTEMICA).first()
        return diretoria and UsuarioGrupo.objects.filter(user=user, group__name='Reitor', setores=diretoria.setor).exists()

    @staticmethod
    def is_secretario_conselho(user):
        setor_id = Configuracao.get_valor_por_chave('ppc', 'setor_secretaria_conselhos')
        return setor_id and user.get_vinculo().setor_id == int(setor_id) or False

    def is_tramite_criacao(self):
        return self.tipo_tramitacao and self.tipo_tramitacao == ProjetoPedagogicoCurso.TIPO_TRAMITACAO_CRIACAO

    def is_tramite_adequacao(self):
        return self.tipo_tramitacao and self.tipo_tramitacao == ProjetoPedagogicoCurso.TIPO_TRAMITACAO_ADEQUACAO

    def is_comissao_em_atualizacao(self):
        return self.atualizacaocomissaoelaboracao_set.filter(concluida=False).exists()

    def is_finalizado(self):
        return self.situacao == ProjetoPedagogicoCurso.FINALIZADO

    def is_em_elaboracao(self):
        return self.situacao == ProjetoPedagogicoCurso.EM_ELABORACAO

    def possui_aprovacao_consup(self):
        return self.is_tramite_criacao() or self.consepex_inexistente

    def can_change(self, user=None):
        return self.matrizppc_set.filter(matriz__isnull=True).exists() and (self.pode_elaborar(user) or self.pode_revisar(user))

    @transaction.atomic()
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.ch_cc_optativo > 0:
            for matriz in self.matrizppc_set.all().only('id', 'quantidade_periodos'):
                if not ConfiguracaoOptativasMatrizPPC.objects.filter(matriz_ppc_id=matriz.id).exists():
                    for periodo in matriz.get_periodos():
                        config = ConfiguracaoOptativasMatrizPPC()
                        config.matriz_ppc_id = matriz.id
                        config.periodo = periodo
                        config.save()
        elif ConfiguracaoOptativasMatrizPPC.objects.filter(matriz_ppc__ppc_id=self.id).exists():
            ConfiguracaoOptativasMatrizPPC.objects.filter(matriz_ppc__ppc_id=self.id).delete()

    def notificar(self, mensagem, notificar_solicitante=False, notificar_elaboradores=False, notificar_revisores=False):
        destinatarios = set()
        if notificar_solicitante:
            destinatarios.add(self.solicitacao.solicitante.get_vinculo())

        if notificar_elaboradores:
            vinculos = self.elaboradorppc_set.all().values_list('vinculo_id', flat=True)
            destinatarios.update(Vinculo.objects.filter(id__in=vinculos))

        if destinatarios:
            url = f'{settings.SITE_URL}{self.get_absolute_url()}'
            titulo = '[SUAP] PPC: Atualização de PPC'
            corpo = f"""<h1>Atualização de PPC</h1>
                <p>{mensagem}</p>
                <p class="more-info">Para mais informações, acesse: <a href="{url}">{url}</a></p>"""
            send_notification(titulo, corpo, settings.DEFAULT_FROM_EMAIL, destinatarios)

    def enviar_para_elaboracao(self, user):
        self.situacao = ProjetoPedagogicoCurso.EM_ELABORACAO
        self.save()
        MovimentacaoPPC.registrar_movimentacao(user, self)

    @transaction.atomic
    def atualizar_situacao(self, user=None):
        if self.is_em_elaboracao() and not self.possui_pendencia_elaboracao():
            self.bibliografia_html = processar_bibliografia(self)
            self.situacao = ProjetoPedagogicoCurso.EM_REVISAO
            self.save()
            self.matrizppc_set.filter(situacao_matriz=MatrizPPC.MATRIZ_AGUARDANDO_REVISAO).update(situacao_matriz=MatrizPPC.MATRIZ_EM_REVISAO)
            self.matrizppc_set.filter(situacao_modalidadepraticaprofissional=MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_REVISAO).update(
                situacao_modalidadepraticaprofissional=MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_REVISAO
            )
            MovimentacaoPPC.registrar_movimentacao(user, self)

        elif self.situacao == ProjetoPedagogicoCurso.EM_REVISAO and self.possui_pendencia_elaboracao() and not self.possui_pendencia_revisao():
            self.situacao = ProjetoPedagogicoCurso.EM_ELABORACAO
            self.save()
            self.matrizppc_set.filter(situacao_matriz=MatrizPPC.MATRIZ_AGUARDANDO_CORRECAO).update(situacao_matriz=MatrizPPC.MATRIZ_EM_ELABORACAO)
            self.matrizppc_set.filter(situacao_modalidadepraticaprofissional=MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_CORRECAO).update(
                situacao_modalidadepraticaprofissional=MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO
            )
            self.conteudoppc_set.filter(situacao=ConteudoPPC.ENVIADO_CORRECAO).update(situacao=ConteudoPPC.EM_EDICAO)
            MovimentacaoPPC.registrar_movimentacao(user, self)

        return self

    @transaction.atomic
    def finalizar(self, user):
        self.situacao = ProjetoPedagogicoCurso.FINALIZADO
        self.vigente = True
        self.save()
        MovimentacaoPPC.registrar_movimentacao(user, self)

    @transaction.atomic
    def gerar_matrizes(self, user, vincular_curso, cod_outros_cursos, diretorias):
        self.save()
        for matrizppc in self.matrizppc_set.all():
            matrizppc.gerar_matriz(user, vincular_curso, cod_outros_cursos, diretorias)

    @transaction.atomic
    def alterar_modeloppc(self):
        modelo = (
            ModeloPPC.objects.filter(tipo_oferta_id=self.modelo_ppc.tipo_oferta_id, modalidade_id=self.modelo_ppc.modalidade_id, ativo=True)
            .exclude(id=self.modelo_ppc_id)
            .only('id')
            .first()
        )
        if modelo is None:
            raise ValidationError('Não existe modelo de PPC ativo para esta modalidade e tipo de oferta.')

        self.conteudoppc_set.all().delete()
        self.modelo_ppc_id = modelo.id
        self.save()

        novos_conteudos_ppc = []
        for conteudo in Conteudo.objects.filter(secao__modelo_ppc_id=modelo.id).only('id', 'texto', 'editavel'):
            item = ConteudoPPC()
            item.conteudo_modelo_id = conteudo.id
            item.ppc_id = self.id
            item.texto = conteudo.texto or ''
            item.situacao = ConteudoPPC.EM_EDICAO if conteudo.editavel else ConteudoPPC.HOMOLOGADO
            novos_conteudos_ppc.append(item)

        if novos_conteudos_ppc:
            ConteudoPPC.objects.bulk_create(novos_conteudos_ppc)
        else:
            raise ValidationError('Não foram encontrados conteúdos para o modelo de PPC ativo desta modalidade e tipo de oferta.')


class MatrizPPC(LogModel):
    MATRIZ_EM_ELABORACAO = '1'
    MATRIZ_AGUARDANDO_REVISAO = '2'
    MATRIZ_EM_REVISAO = '3'
    MATRIZ_AGUARDANDO_CORRECAO = '4'
    MATRIZ_APROVADA = '5'
    SITUACAO_MATRIZ_CHOICES = [
        [MATRIZ_EM_ELABORACAO, 'Em edição'],
        [MATRIZ_AGUARDANDO_REVISAO, 'Edição concluída'],
        [MATRIZ_EM_REVISAO, 'Em revisão'],
        [MATRIZ_AGUARDANDO_CORRECAO, 'Solicitado correção'],
        [MATRIZ_APROVADA, 'Homologada'],
    ]

    MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO = '1'
    MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_REVISAO = '2'
    MODALIDADEPRATICAPROFISSIONAL_EM_REVISAO = '3'
    MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_CORRECAO = '4'
    MODALIDADEPRATICAPROFISSIONAL_APROVADA = '5'
    SITUACAO_MODALIDADEPRATICAPROFISSIONAL_CHOICES = [
        [MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO, 'Em edição'],
        [MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_REVISAO, 'Edição concluída'],
        [MODALIDADEPRATICAPROFISSIONAL_EM_REVISAO, 'Em revisão'],
        [MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_CORRECAO, 'Solicitado correção'],
        [MODALIDADEPRATICAPROFISSIONAL_APROVADA, 'Homologada'],
    ]

    nome = models.CharFieldPlus(verbose_name='Nome', null=False, blank=False)
    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='PPC', null=False, blank=False)

    quantidade_periodos = models.PositiveIntegerFieldPlus('Quantidade de períodos', null=True, blank=False, min_value=1)
    turno = models.ForeignKeyPlus('edu.Turno', verbose_name='Turno', null=True, blank=False)

    situacao_matriz = models.CharFieldPlus(
        verbose_name='Situação da matriz curricular', null=False, blank=False, choices=SITUACAO_MATRIZ_CHOICES, default=MATRIZ_EM_ELABORACAO
    )
    justificativa_matriz = models.TextField(
        'justificativa', null=True, blank=False, help_text='Indique as correções que devem ser realizadas na matriz curricular.'
    )

    situacao_modalidadepraticaprofissional = models.CharFieldPlus(
        verbose_name='Situação das modalidades de prática profissional',
        null=False,
        blank=False,
        choices=SITUACAO_MODALIDADEPRATICAPROFISSIONAL_CHOICES,
        default=MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO,
    )
    justificativa_modalidadepraticaprofissional = models.TextField(
        'justificativa',
        null=True,
        blank=False,
        help_text='Indique as correções que devem ser realizadas nas modalidades de prática profissional do PPC.',
    )

    matriz = models.ForeignKeyPlus('edu.Matriz', verbose_name='Matriz', null=True, blank=False)
    cursos = models.ManyToManyFieldPlus('edu.CursoCampus', verbose_name='Cursos', blank=True)

    class Meta:
        verbose_name = 'Matriz de PPC'
        verbose_name_plural = 'Matrizes de PPC'

    def __str__(self):
        return f'{self.nome} (PPC {self.ppc_id})'

    def clean(self):
        if self.quantidade_periodos:
            if self.quantidade_periodos > self.ppc.diretriz.qtd_max_periodos or self.quantidade_periodos < self.ppc.diretriz.qtd_min_periodos:
                raise ValidationError(
                    f'O número de períodos da matriz deve estar entre {self.ppc.diretriz.qtd_min_periodos} e {self.ppc.diretriz.qtd_max_periodos}.'
                )
            if (
                MatrizPPC.objects.filter(ppc_id=self.ppc_id, quantidade_periodos=self.quantidade_periodos, turno=self.turno)
                .exclude(id=self.id)
                .exists()
            ):
                raise ValidationError('Já existe uma matriz cadastrada para este PPC com a mesma quantidade de períodos e turno.')

        super().clean()

    @transaction.atomic
    def delete(self, *args, **kwargs):
        self.planodisciplinappc_set.all().delete()
        super().delete(*args, **kwargs)

    def can_change(self, user):
        return not self.possui_matriz_gerada() and self.ppc.pode_elaborar(user)

    def can_delete(self, user):
        return self.can_change(user)

    def get_absolute_url(self, extra=None):
        url = f'/ppc/matrizppc/{self.id}/'
        if extra:
            url = f'{url}?{extra}'
        return url

    def get_pendencias(self, check_fast=False):
        result = []
        grupos = []
        # INÍCIO MATRIZ CURRICULAR ###

        # matriz sem turno
        if self.turno is None:
            if check_fast:
                return True
            result.append(['O turno da matriz curricular não foi informado.', f'/ppc/matrizppc/{self.id}/editar/'])

        # configuração de optativas
        if self.ppc.ch_cc_optativo > 0:
            if not self.get_configuracao_optativas().exists():
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária de componentes optativos foi definida no PPC ({self.ppc.ch_cc_optativo}h), mas não há configuração de disciplinas optativas para esta matriz.',
                        'matriz#abas',
                    ]
                )
            ch_exigida = self.get_ch_total_optativo_periodo()
            if ch_exigida != self.ppc.ch_cc_optativo:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A soma da carga horária exigida de disciplinas optativas nos períodos ({ch_exigida}h) não corresponde à carga horária informada no PPC ({self.ppc.ch_cc_optativo}h).',
                        'optativas#abas',
                    ]
                )
            for config in self.get_configuracao_optativas().filter(ch_exigida__gt=0):
                planos_no_periodo = self.planodisciplinappc_set.filter(
                    periodo_oferta=config.periodo, optativo=True, plano_disciplina__nucleo_id=config.nucleo_diretriz.nucleo_id
                )
                ch_total = planos_no_periodo.aggregate(total=Sum('ch_teorica'))['total'] or 0
                ch_total += planos_no_periodo.aggregate(total=Sum('ch_extensao'))['total'] or 0
                # se existir pelo menos uma optativa no período, validar se cumpre CH exigida
                if ch_total > 0 and ch_total < config.ch_exigida:
                    if check_fast:
                        return True
                    result.append(
                        [
                            f'A carga horária total das disciplinas optativas no {config.periodo}° período ({ch_total}h) é inferior à carga horária mínima configurada para este período ({config.ch_exigida}h).',
                            'matriz#abas',
                        ]
                    )

        # planos de disciplinas aprovada
        for plano in self.planodisciplinappc_set.exclude(plano_disciplina__situacao=PlanoDisciplina.APROVADO):
            if check_fast:
                return True
            result.append([f'O plano de disciplina {plano.plano_disciplina} precisa ser aprovado.', plano.plano_disciplina.get_absolute_url()])

        # planos de disciplinas aprovada
        if self.ppc.situacao in [ProjetoPedagogicoCurso.EM_ELABORACAO, ProjetoPedagogicoCurso.EM_REVISAO]:
            for plano in self.planodisciplinappc_set.filter(plano_disciplina__situacao=PlanoDisciplina.APROVADO, plano_disciplina__ativo=False):
                if check_fast:
                    return True
                result.append(
                    [f'O plano de disciplina {plano.plano_disciplina} foi inativado.', f'matriz#id_nucleo_{plano.plano_disciplina.nucleo_id}']
                )

        # planos com período 0
        if self.planodisciplinappc_set.filter(periodo_oferta=0).exists():
            if check_fast:
                return True
            result.append(
                [
                    'Há planos de disciplina cujo período de oferta está informado com valor zero.',
                    f'/ppc/matrizppc/{self.id}/?tab=matriz',
                ]
            )

        # planos sem periodo oferta
        for plano in self.planodisciplinappc_set.filter(periodo_oferta__isnull=True, optativo=False):
            if check_fast:
                return True
            result.append(
                [
                    f'Período de oferta não informado para o plano de disciplina {plano.plano_disciplina}.',
                    f'/admin/ppc/planodisciplinappc/{plano.id}/change/',
                ]
            )

        # somatório da ch de extensão e teórica diferente da ch da disciplina
        for plano in (
            self.planodisciplinappc_set.select_related('plano_disciplina').only('ch_teorica', 'ch_extensao', 'plano_disciplina__ch_disciplina').all()
        ):
            ch_total = (plano.ch_teorica or 0) + (plano.ch_extensao or 0)
            if plano.plano_disciplina.ch_disciplina == ch_total:
                continue
            if check_fast:
                return True
            result.append(
                [
                    f'O somatório da carga horária teórica ({plano.ch_teorica}h) e de extensão ({plano.ch_extensao}h) do plano de disciplina {plano.plano_disciplina} está diferente da carga horária total da disciplina ({plano.plano_disciplina.ch_disciplina}h).',
                    f'/admin/ppc/planodisciplinappc/{plano.id}/change/',
                ]
            )
        # Componentes exigidos na diretriz
        mapa_planos = {}
        for pd in self.get_planos_disciplinappc():
            mapa_planos[pd.plano_disciplina.nome_disciplina] = [pd.plano_disciplina.ch_disciplina, pd.periodo_oferta]
        for componente in self.ppc.diretriz.componenteexigidodiretriz_set.all():
            nomes = componente.nome_componente.split(';')
            tem_disciplina = False
            for nome in nomes:
                if not tem_disciplina and nome in mapa_planos:
                    tem_disciplina = True
                    if componente.ch_min_componente and componente.ch_min_componente > mapa_planos[nome][0]:
                        if check_fast:
                            return True
                        result.append(
                            [f'A carga horária informada no plano de disciplina {nome} não atende aos requisitos da diretriz.', 'matriz#abas']
                        )
                    if componente.periodo_oferta:
                        periodos = componente.periodo_oferta.split(';')
                        if str(mapa_planos[nome][1]) not in periodos:
                            if check_fast:
                                return True
                            result.append(
                                [
                                    f'O período de oferta informado no plano de disciplina {nome} não atende aos requisitos da diretriz.',
                                    'matriz#abas',
                                ]
                            )
            if not tem_disciplina:
                n = ' ou '.join(nomes)
                m = ' ou '.join(componente.periodo_oferta.split(';'))
                if check_fast:
                    return True
                result.append([f'Não foi encontrado um plano de disciplina para {n} no {m}° período.', 'matriz#abas'])

        # ch exigida por componente do tipo regular
        if self.ppc.ch_cc_regular:
            ch_total = (
                self.get_planos_disciplinappc()
                .filter(tipo=PlanoDisciplinaPPC.TIPO_REGULAR, optativo=False)
                .aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total']
                or 0
            )
            ch_total += self.get_ch_informada_matriz_optativo()
            if self.ppc.ch_cc_regular != ch_total:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária total de componentes do tipo regular ({ch_total}h) não corresponde à carga horária exigida no PPC ({self.ppc.ch_cc_regular}h).',
                        'matriz#abas',
                    ]
                )

        # ch exigida por componente do tipo atividade de extensão
        if self.ppc.ch_cc_extensao:
            ch_total = self.get_ch_extensionista_tipo_atividade_extensao()
            if self.ppc.ch_cc_extensao != ch_total:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária total de componentes do tipo atividade de extensão ({ch_total}h) não corresponde à carga horária exigida no PPC ({self.ppc.ch_cc_extensao}h).',
                        'matriz#abas',
                    ]
                )

        # ch exigida por componente do tipo TCC
        if self.ppc.ch_cc_tcc:
            ch_total = (
                self.planodisciplinappc_set.filter(tipo=PlanoDisciplinaPPC.TIPO_TRABALHO_CONCLUSAO_CURSO).aggregate(total=Sum('ch_teorica'))['total']
                or 0
            )
            ch_total += (
                self.planodisciplinappc_set.filter(tipo=PlanoDisciplinaPPC.TIPO_TRABALHO_CONCLUSAO_CURSO).aggregate(total=Sum('ch_extensao'))['total']
                or 0
            )
            if self.ppc.ch_cc_tcc != ch_total:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária total de componentes do tipo TCC ({ch_total}h) não corresponde à carga horária exigida no PPC ({self.ppc.ch_cc_tcc}h).',
                        'matriz#abas',
                    ]
                )

        # ch exigida nos periodos
        for periodo in self.ppc.diretriz.periododiretriz_set.all():
            ch_informada = sum(
                self.planodisciplinappc_set.filter(periodo_oferta=periodo.periodo).values_list('plano_disciplina__ch_disciplina', flat=True)
            )
            if periodo.ch_min_componente > ch_informada:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária informada para o {periodo.periodo}° período ({ch_informada}h) está inferior ao exigido na diretriz ({periodo.ch_min_componente}h).',
                        'matriz#abas',
                    ]
                )
            if periodo.ch_max_componente < ch_informada:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária informada para o {periodo.periodo}° período ({ch_informada}h) está acima do permitido pela diretriz ({periodo.ch_max_componente}h).',
                        'matriz#abas',
                    ]
                )

        # ch exigida nos núcleos
        min_ch_nucleos = 0
        for nd in self.ppc.diretriz.nucleodiretriz_set.exclude(exige_eixo_tecnologico=True):
            min_ch_nucleos += nd.ch_min_pd
            ch_informada = self.get_ch_informada_matriz(nd.nucleo_id)
            if nd.ch_min_pd > ch_informada:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária informada no núcleo {nd.nucleo.descricao} ({ch_informada}h) está inferior ao exigido na diretriz ({nd.ch_min_pd}h).',
                        f'matriz#id_nucleo_{nd.nucleo_id}',
                    ]
                )
            if nd.ch_max_pd < ch_informada:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária informada no núcleo {nd.nucleo.descricao} ({ch_informada}h) está acima do permitido pela diretriz ({nd.ch_max_pd}h).',
                        f'matriz#id_nucleo_{nd.nucleo_id}',
                    ]
                )
        for nd in self.ppc.diretriz.nucleodiretriz_set.filter(exige_eixo_tecnologico=True):
            ch_informada = self.get_ch_informada_matriz(nd.nucleo_id)
            ch_min = nd.get_ch_min_pd(self.ppc.solicitacao.eixo_tecnologico_id)
            min_ch_nucleos += ch_min
            if ch_min > ch_informada:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária informada no núcleo {nd.nucleo.descricao} ({ch_informada}h) está inferior ao exigido na diretriz ({ch_min}h).',
                        f'matriz#id_nucleo_{nd.nucleo_id}',
                    ]
                )
            ch_max = nd.get_ch_max_pd(self.ppc.solicitacao.eixo_tecnologico_id)
            if ch_max < ch_informada:
                if check_fast:
                    return True
                result.append(
                    [
                        f'A carga horária informada no núcleo {nd.nucleo.descricao} ({ch_informada}h) está acima do permitido pela diretriz ({ch_max}h).',
                        f'matriz#id_nucleo_{nd.nucleo_id}',
                    ]
                )

        # ch para planos de disciplinas dos nucleos superior à CH de componentes do PPC
        ch_ppc = self.ppc.get_ch_exigida_matriz()
        if min_ch_nucleos > ch_ppc:
            if check_fast:
                return True
            result.append(
                [
                    f'A carga horária de componentes (obrigatórios, optativos, eletivos e TCC) definido neste PPC ({ch_ppc}h) está inferior à carga horária mínima de planos de disciplina exigido nos núcleos ({min_ch_nucleos}h) da diretriz.',
                    'curso#abas',
                ]
            )

        # quantidade de disciplinas por semestre
        if self.ppc.diretriz.qtd_min_disciplina_semestre or self.ppc.diretriz.qtd_max_disciplina_semestre:
            for i in self.get_periodos():
                if self.ppc.is_curso_anual():
                    for semestre in [1, 2]:
                        qtd = self.get_qtd_disciplinas_por_periodo(i, semestre)
                        if self.ppc.diretriz.qtd_min_disciplina_semestre and self.ppc.diretriz.qtd_min_disciplina_semestre > qtd:
                            if check_fast:
                                return True
                            result.append(
                                [
                                    f'A quantidade de disciplinas inseridas no {semestre}° semestre do {i}° período da matriz ({qtd}) está menor do que a quantidade mínima exigida na diretriz ({self.ppc.diretriz.qtd_min_disciplina_semestre}).',
                                    'matriz#abas',
                                ]
                            )
                        if self.ppc.diretriz.qtd_max_disciplina_semestre and qtd > self.ppc.diretriz.qtd_max_disciplina_semestre:
                            if check_fast:
                                return True
                            result.append(
                                [
                                    f'A quantidade de disciplinas inseridas no {semestre}° semestre do {i}° período da matriz ({qtd}) está maior do que a quantidade máxima exigida na diretriz ({self.ppc.diretriz.qtd_max_disciplina_semestre}).',
                                    'matriz#abas',
                                ]
                            )
                else:
                    qtd = self.get_qtd_disciplinas_por_periodo(i)
                    if self.ppc.diretriz.qtd_min_disciplina_semestre and self.ppc.diretriz.qtd_min_disciplina_semestre > qtd:
                        if check_fast:
                            return True
                        result.append(
                            [
                                f'A quantidade de disciplinas inseridas no {i}° período da matriz ({qtd}) está menor do que a quantidade mínima exigida na diretriz ({self.ppc.diretriz.qtd_min_disciplina_semestre}).',
                                'matriz#abas',
                            ]
                        )
                    if self.ppc.diretriz.qtd_max_disciplina_semestre and qtd > self.ppc.diretriz.qtd_max_disciplina_semestre:
                        if check_fast:
                            return True
                        result.append(
                            [
                                f'A quantidade de disciplinas inseridas no {i}° período da matriz ({qtd}) está maior do que a quantidade máxima exigida na diretriz ({self.ppc.diretriz.qtd_max_disciplina_semestre}).',
                                'matriz#abas',
                            ]
                        )

        # carga horaria semanal por semestre
        if self.ppc.diretriz.ch_semanal_min_semestre or self.ppc.diretriz.ch_semanal_max_semestre:
            for i in self.get_periodos():
                if self.ppc.is_curso_anual():
                    for semestre in [1, 2]:
                        ch = self.get_total_creditos_por_planos_disciplinappc(None, i, semestre)
                        if self.ppc.diretriz.ch_semanal_min_semestre and self.ppc.diretriz.ch_semanal_min_semestre > ch:
                            if check_fast:
                                return True
                            result.append(
                                [
                                    f'A carga horária semanal do {semestre}° semestre do {i}° período da matriz ({ch}) está menor do que a carga horária mínima exigida na diretriz ({self.ppc.diretriz.ch_semanal_min_semestre}).',
                                    'matriz#abas',
                                ]
                            )
                        if self.ppc.diretriz.ch_semanal_max_semestre and ch > self.ppc.diretriz.ch_semanal_max_semestre:
                            if check_fast:
                                return True
                            result.append(
                                [
                                    f'A carga horária semanal do {semestre}° semestre do {i}° período da matriz ({ch}) está maior do que a carga horária máxima exigida na diretriz ({self.ppc.diretriz.ch_semanal_max_semestre}).',
                                    'matriz#abas',
                                ]
                            )
                else:
                    ch = self.get_total_creditos_por_planos_disciplinappc(None, i, None)
                    if self.ppc.diretriz.ch_semanal_min_semestre and self.ppc.diretriz.ch_semanal_min_semestre > ch:
                        if check_fast:
                            return True
                        result.append(
                            [
                                f'A carga horária semanal do {i}° período da matriz ({ch}) está menor do que a carga horária mínima exigida na diretriz ({self.ppc.diretriz.ch_semanal_min_semestre}).',
                                'matriz#abas',
                            ]
                        )
                    if self.ppc.diretriz.ch_semanal_max_semestre and ch > self.ppc.diretriz.ch_semanal_max_semestre:
                        if check_fast:
                            return True
                        result.append(
                            [
                                f'A carga horária semanal do {i}° período da matriz ({ch}) está maior do que a carga horária máxima exigida na diretriz ({self.ppc.diretriz.ch_semanal_max_semestre}).',
                                'matriz#abas',
                            ]
                        )

        # % EAD
        if self.turno and not self.turno.is_ead() and self.ppc.diretriz.possui_ch_ead():
            curso = self.get_percentual_ead_total()
            if self.ppc.diretriz.percentual_min_ead:
                diretriz_min = Decimal(round(self.ppc.diretriz.percentual_min_ead, 2)).quantize(Decimal('0.01'))
                if curso < diretriz_min:
                    if check_fast:
                        return True
                    result.append(
                        [f'O percentual mínimo de CH EAD definido na diretriz ({diretriz_min}%) não foi alcançado ({curso}%).', 'matriz#abas']
                    )

            if self.ppc.diretriz.percentual_max_ead:
                diretriz_max = Decimal(round(self.ppc.diretriz.percentual_max_ead, 2)).quantize(Decimal('0.01'))
                if curso > diretriz_max:
                    if check_fast:
                        return True
                    result.append(
                        [f'O percentual máximo de CH EAD definido na diretriz ({diretriz_max}%) foi ultrapassado ({curso}%).', 'matriz#abas']
                    )

        # certificação intermediária
        ids_planos_matriz = self.planodisciplinappc_set.values_list('plano_disciplina_id', flat=True)
        qs_planos_certificacao = PlanoDisciplinaCertificacaoParcial.objects.filter(certificacao_parcial__ppc_id=self.ppc_id).exclude(
            plano_disciplina_id__in=ids_planos_matriz
        )
        if qs_planos_certificacao.exists():
            if check_fast:
                return True
            for plano in qs_planos_certificacao:
                result.append(
                    [
                        f'O plano de disciplina {plano.plano_disciplina} vinculado à certificação intemediária {plano.certificacao_parcial.descricao} não existe nesta matriz.',
                        'matriz#abas',
                    ]
                )

        # situação da matriz
        if self.ppc.situacao == ProjetoPedagogicoCurso.EM_ELABORACAO:
            # matriz enviada para revisão
            if self.situacao_matriz == MatrizPPC.MATRIZ_EM_ELABORACAO:
                if check_fast:
                    return True
                result.append(['A matriz curricular não foi enviada para revisão.', 'matriz#abas'])

        if self.ppc.situacao == ProjetoPedagogicoCurso.EM_REVISAO:
            # matriz aprovada
            if self.situacao_matriz != MatrizPPC.MATRIZ_APROVADA:
                if check_fast:
                    return True
                result.append(['A matriz curricular não foi aprovada', 'matriz#abas'])

        if result:
            grupos.append(['Pendências da matriz curricular', result])
            result = []

        # FIM MATRIZ CURRICULAR ###

        # INICIO PRATICA PROFISSIONAL ###

        if self.ppc.situacao == ProjetoPedagogicoCurso.EM_ELABORACAO:
            # prática enviada para revisão
            if self.situacao_modalidadepraticaprofissional == MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO:
                if check_fast:
                    return True
                result.append(['A prática profissional não foi enviada para revisão.', 'pratica#abas'])

        if self.ppc.situacao == ProjetoPedagogicoCurso.EM_REVISAO:
            # prática aprovada
            if self.situacao_modalidadepraticaprofissional != MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_APROVADA:
                if check_fast:
                    return True
                result.append(['A prática profissional não foi aprovada.', 'pratica#abas'])

        if result:
            grupos.append(['Pendências da prática profissional', result])
            result = []

        # FIM PRATICA PROFISSIONAL ###
        return grupos

    def get_periodos(self):
        periodos = []
        if self.quantidade_periodos:
            periodos = range(1, self.quantidade_periodos + 1)
        return periodos

    def get_ch_componentes_com_extensao(self):
        return (
            self.get_planos_disciplinappc().exclude(tipo=PlanoDisciplinaPPC.TIPO_ATIVIDADE_EXTENSAO).aggregate(total=Sum('ch_extensao'))['total'] or 0
        )

    def get_ch_total_extensao(self):
        # componentes do tipo Atividade de extensão + ch de extensão em componentes do tipo Regular
        return self.ppc.ch_cc_extensao + self.get_ch_componentes_com_extensao()

    def get_ch_total_optativo_periodo(self):
        return self.get_configuracao_optativas().aggregate(total=Sum('ch_exigida'))['total'] or 0

    def get_ch_vinculada_optativo_sem_periodo(self):
        return (
            PlanoDisciplinaPPC.objects.filter(matriz_ppc_id=self.id, periodo_oferta__isnull=True, optativo=True).aggregate(
                total=Sum('plano_disciplina__ch_disciplina')
            )['total']
            or 0
        )

    def get_ch_informada_matriz(self, nucleo_id=None):
        return self.get_ch_informada_matriz_obrigatorio(nucleo_id) + self.get_ch_informada_matriz_optativo(nucleo_id)

    def get_ch_informada_matriz_obrigatorio(self, nucleo_id=None):
        qs = self.get_planos_disciplinappc(nucleo_id)
        return qs.exclude(optativo=True).aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0

    def get_ch_informada_matriz_optativo(self, nucleo_id=None):
        ch_exigida = self.ppc.ch_cc_optativo
        if nucleo_id:
            ch_exigida = self.get_configuracao_optativas(nucleo_id).aggregate(total=Sum('ch_exigida'))['total'] or 0
        return min(self.get_ch_vinculada_matriz_optativo(nucleo_id), ch_exigida)

    def get_ch_vinculada_matriz_optativo(self, nucleo_id=None):
        qs = self.get_planos_disciplinappc(nucleo_id).filter(optativo=True)
        return qs.aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0

    def get_ch_informada_optativas_matriz(self, nucleo_id=None):
        qs_optativo = self.planodisciplinappc_set.filter(optativo=True)
        if nucleo_id:
            qs_optativo = qs_optativo.filter(plano_disciplina__nucleo_id=nucleo_id)
        return qs_optativo.aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0

    def get_ch_semanal(self, nucleo_id=None):
        return self.get_ch_informada_matriz(nucleo_id) / self.ppc.diretriz.equivalencia_hr_credito

    def get_ch_teorica(self, nucleo_id=None):
        qs = self.get_planos_disciplinappc(nucleo_id).exclude(optativo=True)
        return qs.aggregate(total=Sum('ch_teorica'))['total'] or 0

    def get_ch_teorica_optativo(self, nucleo_id=None):
        qs = self.get_planos_disciplinappc(nucleo_id).filter(optativo=True)
        return qs.aggregate(total=Sum('ch_teorica'))['total'] or 0

    def get_ch_extensionista_tipo_atividade_extensao(self):
        return (
            self.get_planos_disciplinappc()
            .filter(tipo=PlanoDisciplinaPPC.TIPO_ATIVIDADE_EXTENSAO)
            .aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total']
            or 0
        )

    def get_ch_extensionista_tipo_regular(self):
        return self.get_planos_disciplinappc().filter(tipo=PlanoDisciplinaPPC.TIPO_REGULAR).aggregate(total=Sum('ch_extensao'))['total'] or 0

    def get_ch_extensionista_total(self):
        return self.get_ch_extensionista_tipo_atividade_extensao() + self.get_ch_extensionista_tipo_regular()

    def get_ch_extensao(self, nucleo_id=None):
        qs = self.get_planos_disciplinappc(nucleo_id).exclude(optativo=True)
        return qs.aggregate(total=Sum('ch_extensao'))['total'] or 0

    def get_ch_extensao_optativo(self, nucleo_id=None):
        qs = self.get_planos_disciplinappc(nucleo_id).filter(optativo=True)
        return qs.aggregate(total=Sum('ch_extensao'))['total'] or 0

    def get_ch_total_por_periodo(self, periodo):
        qs = self.planodisciplinappc_set.filter(periodo_oferta=periodo)
        return qs.aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0

    def get_ch_teorica_por_periodo(self, periodo):
        qs = self.planodisciplinappc_set.filter(periodo_oferta=periodo)
        return qs.aggregate(total=Sum('ch_teorica'))['total'] or 0

    def get_ch_extensao_por_periodo(self, periodo):
        qs = self.planodisciplinappc_set.filter(periodo_oferta=periodo)
        return qs.aggregate(total=Sum('ch_extensao'))['total'] or 0

    def get_ch_total_optativo_por_tipo(self, tipo):
        qs = self.planodisciplinappc_set.filter(tipo=tipo, optativo=True)
        return qs.aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0

    def get_ch_total_optativo_contabilizado_por_tipo(self, tipo):
        return min(self.get_ch_total_optativo_por_tipo(tipo), self.ppc.ch_cc_optativo)

    def get_ch_total_obrigatorio_por_tipo(self, tipo):
        qs = self.planodisciplinappc_set.filter(tipo=tipo, optativo=False)
        return qs.aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0

    def get_planos_vinculados_sem_periodo(self):
        return PlanoDisciplinaPPC.objects.filter(matriz_ppc_id=self.id, periodo_oferta__isnull=True, optativo=True).count()

    def get_qtd_componentes(self, nucleo_id=None):
        qs = self.get_planos_disciplinappc(nucleo_id)
        return qs.count()

    def get_qtd_componentes_obrigatorio(self, nucleo_id=None):
        return self.get_planos_disciplinappc(nucleo_id).exclude(optativo=True).count()

    def get_qtd_componentes_optativo(self, nucleo_id=None):
        return self.get_planos_disciplinappc(nucleo_id).filter(optativo=True).count()

    def get_ch_informada_pratica(self, nucleo_id=None):
        qs = self.get_modalidades_praticaprofissionalppc(nucleo_id).filter(ch_requerida__gt=0)
        return sum(qs.values_list('ch_requerida', flat=True))

    def get_modalidades_praticaprofissionalppc(self, nucleo_id=None):
        qs = self.modalidadepraticaprofissionalppc_set.all()
        if nucleo_id:
            qs = qs.filter(nucleo_id=nucleo_id)
        return qs.order_by('periodo_inicial')

    def get_modalidades_praticaprofissionalppc_projeto_integrador(self):
        return self.get_modalidades_praticaprofissionalppc().filter(
            ch_requerida__isnull=False, modalidade_pratica_profissional_id__in=ModalidadePraticaProfissional.get_ids_modalidades_projeto_integrador()
        )

    def get_percentual_ch_informada_matriz(self):
        ch_exigida_matriz = self.ppc.get_ch_exigida_matriz()
        if ch_exigida_matriz == 0:
            return 100
        return round(self.get_ch_informada_matriz() / ch_exigida_matriz * 100)

    def get_qtd_disciplinas_por_periodo(self, periodo, semestre=None):
        qs = self.planodisciplinappc_set.filter(periodo_oferta=periodo, optativo=False, plano_disciplinappc_associado_id__isnull=True)
        if self.ppc.is_curso_anual() and semestre:
            segundo_semestre = semestre == 2
            qs = qs.filter(quantidade_etapas=4) | qs.filter(quantidade_etapas=2).exclude(segundo_semestre=segundo_semestre)
        return qs.count()

    def get_planos_disciplinappc(self, nucleo_id=None):
        qs = self.planodisciplinappc_set.all()
        if nucleo_id:
            qs = qs.filter(plano_disciplina__nucleo_id=nucleo_id)
        return qs

    def get_planos_disciplinappc_quadro(self, nucleo_id):
        qs = self.get_planos_disciplinappc(nucleo_id)
        if self.ppc.ch_cc_optativo:
            qs = qs.exclude(optativo=True)
        return qs

    def get_planos_disciplinappc_optativos(self, nucleo_id):
        return self.get_planos_disciplinappc(nucleo_id).filter(optativo=True)

    def get_configuracao_optativas(self, nucleo_id=None):
        qs = self.configuracaooptativasmatrizppc_set.all()
        if nucleo_id:
            qs = qs.filter(nucleo_diretriz__nucleo_id=nucleo_id, ch_exigida__gt=0)
        return qs

    def get_total_ch_hora_aula_por_planos_disciplinappc(self, nucleo_id=None):
        ch_hora_aula = 0
        qs = self.get_planos_disciplinappc(nucleo_id)
        if self.ppc.ch_cc_optativo > 0:
            for optativa in self.get_configuracao_optativas(nucleo_id):
                ch_hora_aula += optativa.get_hora_aula()
            qs = qs.exclude(optativo=True)
        for item in qs:
            ch_hora_aula += item.get_hora_aula()
        return ch_hora_aula

    def get_total_ch_hora_relogio_por_planos_disciplinappc(self, nucleo_id=None):
        result = 0
        qs = self.get_planos_disciplinappc(nucleo_id)
        if self.ppc.ch_cc_optativo > 0:
            result = qs.exclude(optativo=True).aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0
            result += self.get_configuracao_optativas(nucleo_id).aggregate(total=Sum('ch_exigida'))['total'] or 0
        else:
            result = qs.aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0
        return result

    def get_total_ch_ead_por_planos_disciplinappc(self, nucleo_id=None):
        total = 0
        for q in (
            self.get_planos_disciplinappc_quadro(nucleo_id)
            .select_related('matriz_ppc__ppc__diretriz')
            .only('qtd_aulas_ead', 'matriz_ppc__ppc__diretriz__equivalencia_hr_ha')
        ):
            total += q.get_hora_relogio_ead()
        return total

    def get_percentual_ead_total(self):
        ch_ead = self.get_total_ch_ead_por_planos_disciplinappc()
        ch_curso = self.ppc.get_ch_exigida_matriz()
        return Decimal(ch_ead / ch_curso * 100).quantize(Decimal('0.01'))

    def get_total_ch_ead_sincrona_por_planos_disciplinappc(self, nucleo_id=None):
        total = 0
        for q in (
            self.get_planos_disciplinappc_quadro(nucleo_id)
            .select_related('matriz_ppc__ppc__diretriz')
            .only('qtd_aulas_sincronas_ead', 'matriz_ppc__ppc__diretriz__equivalencia_hr_ha')
        ):
            total += q.get_hora_relogio_ead()
        return total

    def get_percentual_ead_sincrona_total(self):
        ch_ead = self.get_total_ch_ead_sincrona_por_planos_disciplinappc()
        ch_curso = self.ppc.get_ch_exigida_matriz()
        return Decimal(ch_ead / ch_curso * 100).quantize(Decimal('0.01'))

    def get_total_ch_ead_assincrona_por_planos_disciplinappc(self, nucleo_id=None):
        total = 0
        for q in (
            self.get_planos_disciplinappc_quadro(nucleo_id)
            .select_related('matriz_ppc__ppc__diretriz')
            .only('qtd_aulas_assincronas_ead', 'matriz_ppc__ppc__diretriz__equivalencia_hr_ha')
        ):
            total += q.get_hora_relogio_ead()
        return total

    def get_percentual_ead_assincrona_total(self):
        ch_ead = self.get_total_ch_ead_assincrona_por_planos_disciplinappc()
        ch_curso = self.ppc.get_ch_exigida_matriz()
        return Decimal(ch_ead / ch_curso * 100).quantize(Decimal('0.01'))

    def get_info_hora_relogio_ead_total(self):
        return f'{mask_number(self.get_percentual_ead_total())}h | {mask_number(self.get_percentual_ead_sincrona_total())}h síncrono e {mask_number(self.get_percentual_ead_assincrona_total())}h assíncrona'

    def get_total_creditos_por_planos_disciplinappc(self, nucleo_id=None, periodo=None, semestre=None):
        qtd_creditos = 0
        qs = self.get_planos_disciplinappc_quadro(nucleo_id).filter(periodo_oferta=periodo)
        for item in qs:
            if semestre and self.ppc.is_curso_anual():
                if semestre == 1:
                    qtd_creditos += item.get_qtd_aulas_1s() or 0
                else:
                    qtd_creditos += item.get_qtd_aulas_2s() or 0
            else:
                qtd_creditos += item.get_qtd_creditos()
        if self.ppc.ch_cc_optativo:
            for optativa in self.get_configuracao_optativas(nucleo_id).filter(periodo=periodo, ch_exigida__gt=0):
                qtd_creditos += optativa.get_qtd_creditos()
        return qtd_creditos

    def get_praticaprofissional_estagio(self):
        return (
            self.get_modalidades_praticaprofissionalppc()
            .filter(modalidade_pratica_profissional_id=ModalidadePraticaProfissional.MODALIDADE_PRATICA_ESTAGIO)
            .first()
            if self.ppc.ch_pratica
            else None
        )

    def get_ch_projeto_integrador(self):
        return self.get_modalidades_praticaprofissionalppc_projeto_integrador().aggregate(total=Sum('ch_requerida'))['total'] or 0

    def get_planos_disciplinas_com_associacao(self):
        return (
            self.get_planos_disciplinappc()
            .filter(plano_disciplinappc_associado_id__isnull=False)
            .select_related('plano_disciplinappc_associado', 'plano_disciplina__nucleo')
        )

    def pode_vincular_curso(self, user):
        result = False
        if user.has_perm('comum.is_administrador_academico') and self.matriz and self.ppc.is_tramite_adequacao():
            if self.ppc.situacao == ProjetoPedagogicoCurso.APROVADO:
                result = True
            elif Configuracao.get_valor_por_chave('ppc', 'permite_gerar_curso_matriz'):
                result = (
                    self.situacao_matriz == MatrizPPC.MATRIZ_APROVADA
                    and self.situacao_modalidadepraticaprofissional == MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_APROVADA
                )
        return result

    def pode_concluir_matriz(self, user):
        ch_total_informada = self.get_ch_informada_matriz() == self.ppc.get_ch_exigida_matriz()
        planos_concluidos = True
        if not Configuracao.get_valor_por_chave('ppc', 'permite_revisao_planodisciplina_em_elaboracao'):
            planos_concluidos = not self.planodisciplinappc_set.exclude(plano_disciplina__situacao=PlanoDisciplina.APROVADO).exists()
        return ch_total_informada and self.situacao_matriz == MatrizPPC.MATRIZ_EM_ELABORACAO and self.ppc.pode_elaborar(user) and planos_concluidos

    def pode_gerar_curso(self, user):
        result = False
        if user.has_perm('comum.is_administrador_academico') and self.matriz and self.ppc.is_tramite_criacao():
            if self.ppc.situacao == ProjetoPedagogicoCurso.APROVADO:
                result = True
            elif Configuracao.get_valor_por_chave('ppc', 'permite_gerar_curso_matriz'):
                result = (
                    self.situacao_matriz == MatrizPPC.MATRIZ_APROVADA
                    and self.situacao_modalidadepraticaprofissional == MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_APROVADA
                )
        return result

    def pode_desfazer_aprovacao_matriz(self, user):
        return self.situacao_matriz == MatrizPPC.MATRIZ_APROVADA and self.ppc.pode_revisar(user) and not self.possui_matriz_gerada()

    def pode_elaborar_matriz(self, user):
        return self.ppc.pode_elaborar(user) and self.situacao_matriz == MatrizPPC.MATRIZ_EM_ELABORACAO and self.ppc.periodicidade

    def pode_concluir_modalidadepraticaprofissional(self, user):
        return (
            self.situacao_modalidadepraticaprofissional == MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO
            and self.ppc.pode_elaborar(user)
            and self.get_modalidades_praticaprofissionalppc().exists()
        )

    def pode_revisar_modalidadepraticaprofissional(self, user):
        return self.situacao_modalidadepraticaprofissional in [
            MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_REVISAO,
            MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_REVISAO,
        ] and self.ppc.pode_revisar(user)

    def pode_desfazer_aprovacao_modalidadepraticaprofissional(self, user):
        return (
            self.situacao_modalidadepraticaprofissional == MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_APROVADA
            and self.ppc.pode_revisar(user)
            and not self.possui_matriz_gerada()
        )

    def possui_matriz_gerada(self):
        return self.matriz is not None

    def possui_ch_ead(self):
        return self.get_planos_disciplinappc().filter(qtd_aulas_ead__gt=0).exists()

    @transaction.atomic()
    def save(self, *args, **kwargs):
        replicado = kwargs.pop('replicado', False)
        super().save(*args, **kwargs)
        if not replicado and self.ppc.ch_cc_optativo > 0 and not ConfiguracaoOptativasMatrizPPC.objects.filter(matriz_ppc_id=self.id).exists():
            for periodo in self.get_periodos():
                ConfiguracaoOptativasMatrizPPC.objects.get_or_create(matriz_ppc=self, periodo=periodo)

    @transaction.atomic()
    def replicar(self):
        replicado = copy.copy(self)
        replicado.id = None
        replicado.save(replicado=True)

        dict_pre = {}
        dict_co = {}
        dict_associado = {}
        for plano in self.get_planos_disciplinappc():
            plano_replicado = copy.copy(plano)
            plano_replicado.id = None
            plano_replicado.matriz_ppc = replicado
            plano_replicado.save()

            dict_pre[plano_replicado] = plano.pre_requisitos.all().values_list('plano_disciplina_id')
            dict_co[plano_replicado] = plano.co_requisitos.all().values_list('plano_disciplina_id')
            plano_replicado.pre_requisitos.clear()
            plano_replicado.co_requisitos.clear()
            if plano.plano_disciplinappc_associado:
                dict_associado[plano_replicado] = plano.plano_disciplinappc_associado.plano_disciplina_id

        for item, values in dict_pre.items():
            requisitos = replicado.get_planos_disciplinappc().filter(plano_disciplina_id__in=values)
            item.pre_requisitos.set(requisitos)

        for item, values in dict_co.items():
            requisitos = replicado.get_planos_disciplinappc().filter(plano_disciplina_id__in=values)
            item.co_requisitos.set(requisitos)

        for item, value in dict_associado.items():
            associado = replicado.get_planos_disciplinappc().filter(plano_disciplina_id=value).only('id').first()
            if associado:
                item.plano_disciplinappc_associado_id = associado.id
                item.save(update_fields=['plano_disciplinappc_associado_id'])

        for config in self.get_configuracao_optativas().all():
            config_replicado = copy.copy(config)
            config_replicado.id = None
            config_replicado.pk = None
            config_replicado.matriz_ppc = replicado
            config_replicado.save()

        for pratica in self.get_modalidades_praticaprofissionalppc():
            pratica_replicada = copy.copy(pratica)
            pratica_replicada.id = None
            pratica_replicada.matriz_ppc = replicado
            pratica_replicada.save()

        return replicado

    def retomar_matrizcurricular(self):
        self.situacao_matriz = MatrizPPC.MATRIZ_EM_ELABORACAO
        self.justificativa_matriz = None
        self.save()

    def desfazer_aprovacao_matrizcurricular(self):
        self.situacao_matriz = MatrizPPC.MATRIZ_EM_REVISAO
        self.save()

    def concluir_matrizcurricular(self):
        self.situacao_matriz = MatrizPPC.MATRIZ_AGUARDANDO_REVISAO
        self.justificativa_matriz = None
        self.save()

    def aprovar_matrizcurricular(self):
        self.situacao_matriz = MatrizPPC.MATRIZ_APROVADA
        self.save()

    def devolver_matrizcurricular(self):
        self.situacao_matriz = MatrizPPC.MATRIZ_AGUARDANDO_CORRECAO
        self.save()

    def concluir_modalidadepraticaprofissional(self):
        self.situacao_modalidadepraticaprofissional = MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_REVISAO
        self.justificativa_modalidadepraticaprofissional = None
        self.save()

    def aprovar_modalidadepraticaprofissional(self):
        self.situacao_modalidadepraticaprofissional = MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_APROVADA
        self.save()

    def devolver_modalidadepraticaprofissional(self):
        self.situacao_modalidadepraticaprofissional = MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_AGUARDANDO_CORRECAO
        self.save()

    def retomar_modalidadepraticaprofissional(self):
        self.situacao_modalidadepraticaprofissional = MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_ELABORACAO
        self.justificativa_modalidadepraticaprofissional = None
        self.save()

    def desfazer_aprovacao_modalidadepraticaprofissional(self):
        self.situacao_modalidadepraticaprofissional = MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_EM_REVISAO
        self.save()

    def criar_matrizcurso(self, curso):
        if MatrizCurso.objects.filter(curso_campus=curso, matriz=self.matriz).exists():
            return
        mc = MatrizCurso()
        mc.curso_campus = curso
        mc.matriz = self.matriz
        # TODO: ver dados de autorização e reconhecimento
        mc.save()

    def vincular_matriz_curso(self):
        cursos = []
        id_vinculados = self.cursos.values_list('id', flat=True)
        for curso in CursoCampus.objects.filter(codigo__endswith=self.ppc.identificador_ppc, ativo=True).exclude(id__in=id_vinculados).distinct():
            # ignora os 2 primeiros caracteres referentes ao id do campus
            if curso.codigo[2:] == self.ppc.identificador_ppc:
                self.criar_matrizcurso(curso)
                cursos.append(curso)

        return cursos

    def criar_curso(self, diretoria):
        cod_campus = diretoria.setor.uo.codigo_interno
        cod_campus = len(cod_campus) == 1 and f'0{cod_campus}' or cod_campus
        codigo_curso = f'{cod_campus}{self.ppc.identificador_ppc}'
        curso = CursoCampus.objects.filter(codigo=codigo_curso).first()
        if curso is None:
            curso = CursoCampus()

            curso.descricao = self.ppc.nome_curso
            curso.descricao_historico = self.ppc.nome_diploma_historico
            curso.codigo_censup = self.ppc.codigo_censup or ''
            curso.codigo_emec = self.ppc.codigo_emec or ''
            curso.codigo_sistec = self.ppc.codigo_sistec or ''
            curso.codigo_educacenso = self.ppc.codigo_educacenso
            curso.ciencia_sem_fronteira = False  # add campo se necessário
            curso.formacao_de_professores = self.ppc.formacao_de_professores
            curso.ano_letivo = self.matriz.ano_criacao
            curso.periodo_letivo = self.matriz.periodo_criacao
            curso.data_inicio = self.matriz.data_inicio
            curso.data_fim = None
            curso.ativo = True
            curso.codigo = codigo_curso
            curso.modalidade_id = self.ppc.diretriz.tipo_oferta_id
            curso.plano_ensino = False  # criar campo se necessário
            curso.area = None  # criar campo se necessário
            curso.eixo_id = self.ppc.solicitacao.eixo_tecnologico_id
            curso.area_capes = None  # criar campo se necessário
            curso.periodicidade = self.ppc.periodicidade
            curso.exige_enade = self.ppc.diretriz.exige_enade
            curso.exige_colacao_grau = self.ppc.diretriz.exige_colacao_grau
            curso.assinatura_digital = False  # criar campo se necessário
            curso.emite_diploma = False  # criar campo se necessário
            curso.assinatura_eletronica = False  # criar campo se necessário
            curso.area_concentracao = self.ppc.area_concentracao
            curso.programa = self.ppc.programa or ''
            curso.diretoria_id = diretoria.id
            curso.extensao = False  # criar campo se necessário
            curso.coordenador = None
            curso.numero_portaria_coordenador = None
            curso.coordenador_2 = None
            curso.numero_portaria_coordenador_2 = None
            curso.resolucao_criacao = None
            curso.titulo_certificado_masculino = self.ppc.titulo_certificado_masculino
            curso.titulo_certificado_feminino = self.ppc.titulo_certificado_feminino
            curso.fator_esforco_curso = 1  # criar campo se necessário
            curso.save()

        self.criar_matrizcurso(curso)
        return curso

    @transaction.atomic
    def gerar_matriz(self, user, vincular_curso, cod_outros_cursos, diretorias):
        self.save()

        data = self.ppc.data_aprovacao or datetime.date.today()
        criou_matriz = False

        if not self.possui_matriz_gerada():
            criou_matriz = True

            # Matriz
            matriz = Matriz()
            matriz.descricao = f'{self.nome} ({self.turno.descricao})'
            matriz.ano_criacao = Ano.objects.get(ano=data.year)
            matriz.periodo_criacao = data.month > 6 and 2 or 1
            matriz.data_inicio = data
            matriz.ativo = True
            matriz.data_fim = None
            matriz.qtd_periodos_letivos = self.quantidade_periodos
            matriz.nivel_ensino_id = self.ppc.diretriz.tipo_oferta.nivel_ensino_id
            matriz.natureza_participacao_id = self.ppc.modelo_ppc.modalidade_id
            matriz.estrutura_id = self.ppc.diretriz.estrutura_curso_id
            matriz.ch_componentes_obrigatorios = self.ppc.ch_cc_obrigatorio - self.ppc.ch_cc_extensao
            matriz.ch_componentes_optativos = self.ppc.ch_cc_optativo
            matriz.ch_componentes_eletivos = self.ppc.ch_cc_eletivo
            matriz.ch_seminarios = 0
            matriz.ch_pratica_profissional = 0
            matriz.ch_atividades_complementares = self.ppc.ch_ac
            matriz.ch_atividades_aprofundamento = self.ppc.ch_atpa
            matriz.ch_atividades_extensao = self.get_ch_total_extensao()
            matriz.ch_componentes_com_extensao = self.get_ch_componentes_com_extensao()
            matriz.ch_componentes_extensao = self.ppc.ch_cc_extensao
            matriz.ch_componentes_tcc = self.ppc.ch_cc_tcc
            matriz.ch_pratica_como_componente = 0
            matriz.ch_visita_tecnica = 0
            matriz.exige_tcc = self.ppc.diretriz.exige_tcc
            matriz.observacao = f'Matriz gerada pelo sistema. PPC: {self.ppc}.'
            matriz.ch_projeto_integrador = self.get_ch_projeto_integrador()

            praticaprofissional_estagio = self.get_praticaprofissional_estagio()
            if praticaprofissional_estagio:
                matriz.exige_estagio = not praticaprofissional_estagio.optativa
                matriz.ch_minima_estagio = praticaprofissional_estagio.ch_requerida
                matriz.periodo_minimo_estagio_obrigatorio = (
                    praticaprofissional_estagio.periodo_inicial if not praticaprofissional_estagio.optativa else None
                )
                matriz.periodo_minimo_estagio_nao_obrigatorio = (
                    praticaprofissional_estagio.periodo_inicial if praticaprofissional_estagio.optativa else None
                )

            matriz.requer_vinculacao_extensao_diarios = matriz.ch_atividades_extensao > 0
            if self.ppc.diretriz.emite_certificacao_parcial and self.ppc.certificacaoparcial_set.exists():
                matriz.emite_certificacao_parcial = True
                matriz.certificado_parcial_acumulavel = self.ppc.diretriz.certificado_parcial_acumulavel
            matriz.save()

            self.matriz = matriz
            self.save()

            componentes_gerados = []
            dict_pre_requisitos = {}
            dict_co_requisitos = {}
            dict_associado_requisitos = {}
            dict_associado_projetointegrador = {}
            for pd in self.get_planos_disciplinappc().select_related(
                'plano_disciplina', 'plano_disciplinappc_associado', 'plano_disciplina__componente'
            ):
                componente = pd.plano_disciplina.componente
                if componente is None:
                    # Componente
                    componente = Componente()
                    componente.descricao = pd.plano_disciplina.nome_disciplina
                    componente.descricao_historico = pd.plano_disciplina.nome_disciplina
                    componente.tipo = pd.plano_disciplina.get_tipo_componente()
                    componente.diretoria = Diretoria.objects.filter(tipo=Diretoria.TIPO_SISTEMICA).first()
                    componente.nivel_ensino_id = pd.plano_disciplina.tipo_oferta.nivel_ensino_id
                    componente.ativo = True
                    componente.ch_hora_relogio = pd.plano_disciplina.ch_disciplina
                    componente.ch_hora_aula = pd.get_hora_aula()
                    componente.ch_qtd_creditos = pd.get_qtd_creditos()
                    componente.observacao = f'{pd.plano_disciplina_id}'
                    componente.sigla_qacademico = None
                    componente.abreviatura = None
                    componente.grupo_atuacao = None
                    componente.save()
                    pd.plano_disciplina.componente = componente
                    pd.plano_disciplina.save()
                    componentes_gerados.append(componente)
                else:
                    if componente.ch_hora_aula != pd.get_hora_aula() or componente.ch_qtd_creditos != pd.get_qtd_creditos():
                        raise ValidationError(
                            f'O plano de disciplina {pd} não pode ser utilizado na geração de matriz deste PPC em razão de apresentar divergência no cálculo de hora aula e quantidade de créditos do componente vinculado ao plano de disciplina.'
                        )

                # Componente Curricular
                cc = ComponenteCurricular()
                cc.matriz = matriz
                cc.componente = componente
                cc.classificacao_complementar = None
                cc.periodo_letivo = pd.periodo_oferta
                cc.tipo = pd.tipo
                cc.optativo = pd.optativo
                cc.is_seminario_estagio_docente = False  # criar campo quando for necessário
                cc.tipo_estagio_docente = None  # criar campo quando for necessário
                cc.tipo_modulo = None  # criar campo quando for necessário
                cc.qtd_avaliacoes = pd.quantidade_etapas
                cc.nucleo = pd.plano_disciplina.nucleo
                cc.ch_presencial = pd.ch_extensao if pd.tipo == PlanoDisciplinaPPC.TIPO_ATIVIDADE_EXTENSAO else pd.ch_teorica
                cc.ch_pratica = 0
                cc.ch_extensao = 0 if pd.tipo == PlanoDisciplinaPPC.TIPO_ATIVIDADE_EXTENSAO else pd.ch_extensao
                cc.ch_pcc = 0
                cc.ch_visita_tecnica = 0
                cc.qtd_aulas_ead = pd.qtd_aulas_ead
                cc.avaliacao_por_conceito = False
                cc.is_dinamico = False
                cc.componente_curricular_associado = None
                cc.segundo_semestre = pd.segundo_semestre
                cc.pode_fechar_pendencia = False
                cc.ementa = pd.plano_disciplina.ementa
                cc.ch_semanal_1s = pd.get_qtd_aulas_1s()
                cc.ch_semanal_2s = pd.get_qtd_aulas_2s()
                if matriz.ch_projeto_integrador and pd.modalidade_projetointegrador_id:
                    cc.ch_projeto_integrador = pd.get_ch_projeto_integrador()
                    cc.modalidade_pratica_profissional_projeto_integrador_id = pd.modalidade_projetointegrador_id
                    dict_associado_projetointegrador[cc] = pd.planos_associados_projetointegrador.values_list('plano_disciplina', flat=True)
                cc.save()

                pre_reqs = pd.pre_requisitos.values_list('plano_disciplina', flat=True)
                if pre_reqs:
                    dict_pre_requisitos[cc] = list(pre_reqs)

                co_reqs = pd.co_requisitos.values_list('plano_disciplina', flat=True)
                if co_reqs:
                    dict_co_requisitos[cc] = list(co_reqs)

                if pd.plano_disciplinappc_associado_id:
                    dict_associado_requisitos[cc] = pd.plano_disciplinappc_associado.plano_disciplina_id

            for cc, values in dict_pre_requisitos.items():
                cc.pre_requisitos.set(cc.matriz.componentecurricular_set.filter(componente__planodisciplina__in=values))

            for cc, values in dict_co_requisitos.items():
                cc.co_requisitos.set(cc.matriz.componentecurricular_set.filter(componente__planodisciplina__in=values))

            for cc, values in dict_associado_projetointegrador.items():
                cc.componentes_associados_projeto_integrador.set(cc.matriz.componentecurricular_set.filter(componente__planodisciplina__in=values))

            for cc, value in dict_associado_requisitos.items():
                cc.componente_curricular_associado = cc.matriz.componentecurricular_set.get(componente__planodisciplina=value)
                cc.save()

            if matriz.emite_certificacao_parcial:
                for cp_ppc in self.ppc.certificacaoparcial_set.all():
                    ccp = ConfiguracaoCertificacaoParcial()
                    ccp.matriz = matriz
                    ccp.descricao = cp_ppc.descricao
                    ccp.modalidade_certificacao = cp_ppc.modalidade_certificacao
                    ccp.titulacao_masculino = cp_ppc.titulacao_masculino
                    ccp.titulacao_feminino = cp_ppc.titulacao_feminino
                    ccp.ch_componentes_optativos = cp_ppc.ch_componentes_optativos
                    ccp.save()
                    for plano in cp_ppc.planodisciplinacertificacaoparcial_set.all():
                        componente = ComponenteCurricularCertificacaoParcial()
                        componente.componente_curricular_id = (
                            matriz.componentecurricular_set.filter(componente_id=plano.plano_disciplina.componente_id).only('id').first().id
                        )
                        componente.configuracao_certificacao_parcial = ccp
                        componente.save()

        cursos = []
        if self.ppc.is_tramite_adequacao():
            if vincular_curso:
                cursos = self.vincular_matriz_curso()
            if cod_outros_cursos:
                for cod in cod_outros_cursos.split(';'):
                    curso = CursoCampus.objects.filter(codigo=cod).first()
                    if curso and not self.cursos.filter(id=curso.id).exists():
                        self.criar_matrizcurso(curso)
                        cursos.append(curso)

        elif diretorias and self.ppc.is_tramite_criacao():
            for diretoria in diretorias:
                cursos.append(self.criar_curso(diretoria))

        for curso in cursos:
            self.cursos.add(curso)

        if criou_matriz:
            for _componente in componentes_gerados:
                MovimentacaoPlanoDisciplina(user, pd.plano_disciplina, 'Componente gerado')

            MovimentacaoPPC.registrar_movimentacao(user, self.ppc, f'Matriz {self.matriz} gerada')

        for curso in cursos:
            if self.ppc.is_tramite_criacao():
                MovimentacaoPPC.registrar_movimentacao(user, self.ppc, f'Curso {curso} gerado')
            MovimentacaoPPC.registrar_movimentacao(user, self.ppc, f'Matriz {self.matriz} vinculada ao curso {curso}')

    @transaction.atomic
    def remover_matrizcurso(self, user, matrizcurso, curso, remove_curso=False):
        if matrizcurso:
            curso = matrizcurso.curso_campus
            matrizcurso.delete()

        self.cursos.remove(curso)
        msg = f'Curso {curso} desvinculado da matriz.'

        if remove_curso:
            msg = f'Curso {curso} excluído.'
            curso.delete()
        MovimentacaoPPC.registrar_movimentacao(user, self.ppc, msg)


class ConfiguracaoOptativasMatrizPPC(LogModel):
    matriz_ppc = models.ForeignKeyPlus('ppc.MatrizPPC', verbose_name='Matriz do PPC', null=False, blank=False)
    periodo = models.PositiveIntegerFieldPlus('Período', null=False, blank=False)
    ch_exigida = models.PositiveIntegerFieldPlus('Carga horária exigida', null=False, blank=False, default=0)
    nucleo_diretriz = models.ForeignKeyPlus('ppc.NucleoDiretriz', verbose_name='Núcleo da diretriz', null=True, blank=False)

    class Meta:
        verbose_name = 'Configuração de optativas da matriz'
        verbose_name_plural = 'Configurações de optativas das matrizes'
        unique_together = ('matriz_ppc', 'periodo', 'nucleo_diretriz')
        ordering = ['periodo']

    def clean(self):
        # garantir unique_together quando nucleo_diretriz for None
        if (
            self.nucleo_diretriz_id is None
            and ConfiguracaoOptativasMatrizPPC.objects.filter(matriz_ppc_id=self.matriz_ppc_id, periodo=self.periodo).exists()
        ):
            raise ValidationError(f'Já existe uma configuração para o período {self.periodo}.')

        if (
            self.nucleo_diretriz_id
            and ConfiguracaoOptativasMatrizPPC.objects.filter(matriz_ppc_id=self.matriz_ppc_id, periodo=self.periodo, nucleo_diretriz_id__isnull=True)
            .exclude(id=self.id)
            .exists()
        ):
            raise ValidationError(
                f'Já existe uma configuração para o período {self.periodo}. Atualize o núcleo da diretriz na configuração existente.'
            )

        super().clean()

    def get_ch_vinculada(self):
        qs = PlanoDisciplinaPPC.objects.filter(matriz_ppc_id=self.matriz_ppc_id, periodo_oferta=self.periodo, optativo=True)
        if self.nucleo_diretriz_id:
            qs = qs.filter(plano_disciplina__nucleo_id=self.nucleo_diretriz.nucleo_id)
        return qs.aggregate(total=Sum('plano_disciplina__ch_disciplina'))['total'] or 0

    def get_planos_vinculados(self):
        qs = PlanoDisciplinaPPC.objects.filter(matriz_ppc_id=self.matriz_ppc_id, periodo_oferta=self.periodo, optativo=True)
        if self.nucleo_diretriz_id:
            qs = qs.filter(plano_disciplina__nucleo_id=self.nucleo_diretriz.nucleo_id)
        return qs.count()

    def get_qtd_creditos(self):
        return int(self.ch_exigida / self.matriz_ppc.ppc.diretriz.equivalencia_hr_credito)

    def get_hora_aula(self):
        return int(self.ch_exigida / self.matriz_ppc.ppc.diretriz.equivalencia_hr_ha)


class DocumentoPPC(LogModel):
    PARECER = '1'
    DELIBERACAO = '2'
    RESOLUCAO = '3'
    DESPACHO = '4'
    TIPO_DOCUMENTO_CHOICES = [
        [PARECER, 'Parecer'],
        [DELIBERACAO, 'Deliberação'],
        [RESOLUCAO, 'Resolução'],
        [DESPACHO, 'Despacho'],
    ]

    DOCUMENTO_CRIADO = '1'
    DOCUMENTO_FINALIZADO = '2'
    DOCUMENTO_INVALIDO = '3'

    SITUACAO_DOCUMENTO_CHOICES = [
        [DOCUMENTO_CRIADO, 'Criado'],
        [DOCUMENTO_FINALIZADO, 'Finalizado'],
        [DOCUMENTO_INVALIDO, 'Inválido'],
    ]

    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='PPC', null=False, blank=False)
    situacao_ppc = models.CharFieldPlus(
        verbose_name='Situação do PPC',
        null=False,
        blank=False,
        choices=ProjetoPedagogicoCurso.SITUACAO_CHOICES,
        help_text='Situação do PPC na emissão do documento.',
    )
    situacao_documento = models.CharFieldPlus(
        verbose_name='Situação do documento', null=False, blank=False, choices=SITUACAO_DOCUMENTO_CHOICES, default=DOCUMENTO_CRIADO
    )
    tipo_documento = models.CharFieldPlus(verbose_name='Tipo de documento', null=False, blank=False, choices=TIPO_DOCUMENTO_CHOICES)
    ad_referendum = models.BooleanField('Ad Referendum', default=False)
    rejeicao = models.BooleanField('Rejeição do PPC', default=False)
    id_documento = models.PositiveIntegerFieldPlus(
        verbose_name='Identificador', null=True, blank=True, help_text='Código de identificação do documento.'
    )
    emissor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Emissor', null=False, blank=False)
    data_emissao = models.DateTimeFieldPlus('Data da emissão', null=False, blank=False)
    decisao = models.CharFieldPlus(verbose_name='Decisão', null=True, blank=True, choices=ProjetoPedagogicoCurso.DECISAO_CHOICES)

    class Meta:
        verbose_name = 'Documento de PPC'
        verbose_name_plural = 'Documentos de PPC'

    def can_delete(self, user):
        return user.has_perm('comum.is_administrador_de_ppc') and self.is_documento_invalido() and self.situacao_ppc == self.ppc.situacao

    def is_documento_invalido(self):
        if self.situacao_documento == DocumentoPPC.DOCUMENTO_INVALIDO:
            return True
        doc = self.get_documento()
        return doc == ProjetoPedagogicoCurso.DOCUMENTO_NAO_EXISTE or doc.estah_cancelado

    def pode_vincular_documento(self, user):
        return (
            user.has_perm('comum.is_administrador_de_ppc')
            and self.situacao_ppc != self.ppc.situacao
            and self.is_documento_invalido()
            and not DocumentoPPC.objects.filter(ppc_id=self.ppc_id, situacao_ppc=self.situacao_ppc, tipo_documento=self.tipo_documento)
            .exclude(situacao_documento=DocumentoPPC.DOCUMENTO_INVALIDO)
            .exists()
        )

    def get_documento(self):
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoTexto

            try:
                return DocumentoTexto.objects.get(id=self.id_documento)
            except DocumentoTexto.DoesNotExist:
                return ProjetoPedagogicoCurso.DOCUMENTO_NAO_EXISTE
        return ProjetoPedagogicoCurso.DOCUMENTO_NAO_EXISTE

    @transaction.atomic
    @staticmethod
    def emitir_documento(ppc, user, documento, setor=None, documento_eletronico=None):
        ad_referendum = False
        rejeicao = False
        decisao = None

        if documento == 'Parecer':
            if ppc.situacao == ProjetoPedagogicoCurso.EM_REVISAO:
                nome_modelo = Configuracao.get_valor_por_chave('ppc', 'nome_modelo_parecer_revisao') or 'Parecer simples'
                tipo = DocumentoPPC.PARECER
            elif ppc.situacao == ProjetoPedagogicoCurso.ANALISE_CAMARA:
                nome_modelo = Configuracao.get_valor_por_chave('ppc', 'nome_modelo_parecer_camara') or 'Parecer simples'
                tipo = DocumentoPPC.PARECER
                rejeicao = decisao == ProjetoPedagogicoCurso.DECISAO_REJEITAR
                decisao = ppc.decisao_camara
        elif 'Deliberação' in documento:
            nome_modelo = Configuracao.get_valor_por_chave('ppc', 'nome_modelo_deliberacao') or 'Deliberação CONSEPEX - Submissão ao Consup'
            tipo = DocumentoPPC.DELIBERACAO
            if documento == 'Deliberação Ad Referendum':
                decisao = ProjetoPedagogicoCurso.DECISAO_APROVAR
                ad_referendum = True
            else:
                decisao = ppc.decisao_consepex
                rejeicao = decisao == ProjetoPedagogicoCurso.DECISAO_REJEITAR
        elif 'Resolução' in documento:
            nome_modelo = Configuracao.get_valor_por_chave('ppc', 'nome_modelo_resolucao') or 'Resolução simples'
            tipo = DocumentoPPC.RESOLUCAO
            if documento == 'Resolução Ad Referendum':
                decisao = ProjetoPedagogicoCurso.DECISAO_APROVAR
                ad_referendum = True
            else:
                decisao = ppc.decisao_consup
                rejeicao = decisao == ProjetoPedagogicoCurso.DECISAO_REJEITAR
        elif documento == 'Despacho':
            nome_modelo = Configuracao.get_valor_por_chave('ppc', 'nome_modelo_despacho') or 'Despacho Simples'
            tipo = DocumentoPPC.DESPACHO
            if ppc.situacao == ProjetoPedagogicoCurso.ANALISE_PROREITORIA:
                rejeicao = ppc.rejeitado_proreitoria
        else:
            raise ValidationError(f'A situação {ppc.get_situacao_display()} não permite emissão de documentos.')

        doc = DocumentoPPC()
        doc.ppc_id = ppc.id
        doc.situacao_ppc = ppc.situacao
        doc.tipo_documento = tipo
        doc.ad_referendum = ad_referendum
        doc.rejeicao = rejeicao
        doc.decisao = decisao

        if documento_eletronico:
            doc.id_documento = documento_eletronico.id
            doc.emissor = documento_eletronico.usuario_criacao.get_relacionamento()
            doc.data_emissao = documento_eletronico.data_criacao
        else:
            setor_dono = setor or user.get_vinculo().setor

            if 'documento_eletronico' in settings.INSTALLED_APPS:
                from documento_eletronico.models import Documento, DocumentoTexto, EstagioProcessamentoVariavel, ModeloDocumento
                from documento_eletronico.utils import get_variaveis

                modelo = ModeloDocumento.objects.get(nome=nome_modelo)
                variaveis = get_variaveis(
                    documento_identificador='',
                    estagio_processamento_variavel=EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
                    usuario=user,
                    setor_dono=setor_dono,
                )
                documento = DocumentoTexto.adicionar_documento_texto(
                    usuario=user,
                    modelo=modelo,
                    assunto=documento,
                    nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
                    variaveis=variaveis,
                    setor_dono=setor_dono,
                )

                documento.save()
                doc.id_documento = documento.id
                doc.emissor = user.get_relacionamento()
                doc.data_emissao = datetime.datetime.now()

        doc.save()

    @transaction.atomic
    @staticmethod
    def atualizar_situacao(ppc):
        # checar documentos criados na etapa atual
        qs = ppc.documentoppc_set.filter(situacao_ppc=ppc.situacao, situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO)
        for docPPC in qs:
            documento = docPPC.get_documento()
            if documento == ProjetoPedagogicoCurso.DOCUMENTO_NAO_EXISTE or documento.estah_cancelado:
                docPPC.situacao_documento = DocumentoPPC.DOCUMENTO_INVALIDO
                docPPC.save()
            elif documento.estah_finalizado:
                docPPC.situacao_documento = DocumentoPPC.DOCUMENTO_FINALIZADO
                docPPC.save()
                if docPPC.situacao_ppc == ProjetoPedagogicoCurso.EM_REVISAO:
                    if ppc.proreitoria is None:
                        raise ValidationError('Nenhuma Pró-Reitoria foi associada para analisar este PPC.')
                    if ppc.decisao_consup == ProjetoPedagogicoCurso.DECISAO_APROVAR_RESSALVA:
                        ppc.situacao = ProjetoPedagogicoCurso.APROVADO
                        ppc.data_aprovacao = datetime.date.today()
                    elif ppc.decisao_consup == ProjetoPedagogicoCurso.DECISAO_SOLICITAR_CORRECAO:
                        ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CONSUP
                        ppc.decisao_consup = None
                        ppc.data_convocacao_consup = None
                    elif ppc.decisao_consepex == ProjetoPedagogicoCurso.DECISAO_APROVAR_RESSALVA:
                        if ppc.is_tramite_criacao():
                            ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CONSUP
                        else:
                            ppc.situacao = ProjetoPedagogicoCurso.APROVADO
                            ppc.data_aprovacao = datetime.date.today()
                    elif ppc.decisao_consepex == ProjetoPedagogicoCurso.DECISAO_SOLICITAR_CORRECAO:
                        ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CONSEPEX
                        ppc.decisao_consepex = None
                        ppc.data_convocacao_consepex = None
                        ppc.consepex_inexistente = False
                    elif ppc.decisao_camara == ProjetoPedagogicoCurso.DECISAO_APROVAR_RESSALVA:
                        ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CONSEPEX
                    elif ppc.decisao_camara == ProjetoPedagogicoCurso.DECISAO_SOLICITAR_CORRECAO:
                        ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CAMARA
                        ppc.decisao_camara = None
                        ppc.data_convocacao_camara = None
                        ppc.camara_inexistente = False
                    else:
                        ppc.situacao = ProjetoPedagogicoCurso.ANALISE_PROREITORIA
                    ppc.save()
                    MovimentacaoPPC.registrar_movimentacao(None, ppc)
                    # TODO: notificar

                elif docPPC.situacao_ppc == ProjetoPedagogicoCurso.ANALISE_PROREITORIA:
                    if ppc.rejeitado_proreitoria:
                        ppc.situacao = ProjetoPedagogicoCurso.REJEITADO
                        ppc.camara = None
                    else:
                        if ppc.camara is None:
                            raise ValidationError('Nenhuma Pró-Reitoria foi associada para analisar este PPC.')
                        if ppc.ad_referendum and ppc.pular_camara:
                            ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CONSEPEX
                        else:
                            ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CAMARA
                    ppc.save()
                    MovimentacaoPPC.registrar_movimentacao(None, ppc)
                    # TODO: notificar

                elif docPPC.situacao_ppc == ProjetoPedagogicoCurso.ANALISE_CAMARA:
                    if docPPC.decisao == ProjetoPedagogicoCurso.DECISAO_APROVAR or ppc.camara_inexistente:
                        ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CONSEPEX
                    elif docPPC.decisao in [ProjetoPedagogicoCurso.DECISAO_APROVAR_RESSALVA, ProjetoPedagogicoCurso.DECISAO_SOLICITAR_CORRECAO]:
                        ppc.situacao = ProjetoPedagogicoCurso.EM_REVISAO
                    elif docPPC.decisao == ProjetoPedagogicoCurso.DECISAO_REJEITAR:
                        ppc.situacao = ProjetoPedagogicoCurso.REJEITADO
                    ppc.save()
                    MovimentacaoPPC.registrar_movimentacao(None, ppc)
                    # TODO: notificar

                elif docPPC.situacao_ppc == ProjetoPedagogicoCurso.ANALISE_CONSEPEX:
                    if ppc.consepex_inexistente:
                        ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CONSUP
                    if docPPC.decisao == ProjetoPedagogicoCurso.DECISAO_APROVAR:
                        if ppc.is_tramite_criacao():
                            ppc.situacao = ProjetoPedagogicoCurso.ANALISE_CONSUP
                        else:
                            ppc.situacao = ProjetoPedagogicoCurso.APROVADO
                            ppc.data_aprovacao = datetime.date.today()
                    elif docPPC.decisao in [ProjetoPedagogicoCurso.DECISAO_APROVAR_RESSALVA, ProjetoPedagogicoCurso.DECISAO_SOLICITAR_CORRECAO]:
                        ppc.situacao = ProjetoPedagogicoCurso.EM_REVISAO
                    elif docPPC.decisao == ProjetoPedagogicoCurso.DECISAO_REJEITAR:
                        ppc.situacao = ProjetoPedagogicoCurso.REJEITADO
                    ppc.save()
                    MovimentacaoPPC.registrar_movimentacao(None, ppc)
                    # TODO: notificar

                elif docPPC.situacao_ppc == ProjetoPedagogicoCurso.ANALISE_CONSUP:
                    if docPPC.decisao == ProjetoPedagogicoCurso.DECISAO_APROVAR:
                        ppc.situacao = ProjetoPedagogicoCurso.APROVADO
                        ppc.data_aprovacao = datetime.date.today()
                    elif docPPC.decisao in [ProjetoPedagogicoCurso.DECISAO_APROVAR_RESSALVA, ProjetoPedagogicoCurso.DECISAO_SOLICITAR_CORRECAO]:
                        ppc.situacao = ProjetoPedagogicoCurso.EM_REVISAO
                    elif docPPC.decisao == ProjetoPedagogicoCurso.DECISAO_REJEITAR:
                        ppc.situacao = ProjetoPedagogicoCurso.REJEITADO

                    ppc.save()
                    MovimentacaoPPC.registrar_movimentacao(None, ppc)
                    # TODO: notificar

        # checar documentos de outras etapas
        qs = ppc.documentoppc_set.exclude(situacao_ppc=ppc.situacao).exclude(situacao_documento=DocumentoPPC.DOCUMENTO_INVALIDO)
        for docPPC in qs:
            documento = docPPC.get_documento()
            if documento == ProjetoPedagogicoCurso.DOCUMENTO_NAO_EXISTE or documento.estah_cancelado:
                docPPC.situacao_documento = DocumentoPPC.DOCUMENTO_INVALIDO
                docPPC.save()


class ElaboradorPPC(LogModel):
    FUNCAO_COORDENADOR = '1'
    FUNCAO_MEMBRO = '2'
    FUNCAO_CHOICES = [
        [FUNCAO_COORDENADOR, 'Coordenador'],
        [FUNCAO_MEMBRO, 'Membro'],
    ]

    PERMISSAO_LEITURA = '1'
    PERMISSAO_EDICAO = '2'
    PERMISSAO_CHOICES = [
        [PERMISSAO_LEITURA, 'Leitura'],
        [PERMISSAO_EDICAO, 'Edição'],
    ]

    servidor = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Servidor', null=True, blank=False
    )  # TODO: issue17120 remover após migração de dados
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Elaborador', null=True, blank=False)
    funcao = models.CharFieldPlus(verbose_name='Função', null=False, blank=False, choices=FUNCAO_CHOICES)
    permissao = models.CharFieldPlus(verbose_name='Permissão', null=False, blank=False, choices=PERMISSAO_CHOICES, default='1')
    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='PPC', null=True, blank=True)
    data_inicial = models.DateFieldPlus('Data Início', null=False, blank=False)

    class Meta:
        verbose_name = 'Elaborador de PPC'
        verbose_name_plural = 'Elaboradores de PPC'

    def clean(self):
        if (
            self.funcao == ElaboradorPPC.FUNCAO_COORDENADOR
            and ElaboradorPPC.objects.filter(funcao=ElaboradorPPC.FUNCAO_COORDENADOR, ppc_id=self.ppc_id).exclude(id=self.id).exists()
        ):
            raise ValidationError('Já existe um membro na função de coordenação.')
        if ElaboradorPPC.objects.filter(vinculo_id=self.vinculo_id, ppc_id=self.ppc_id).exclude(id=self.id).exists():
            raise ValidationError('O membro indicado já foi adicionado a esta comissão.')
        if (
            self.id
            and self.funcao != ElaboradorPPC.FUNCAO_COORDENADOR
            and not ElaboradorPPC.objects.filter(funcao=ElaboradorPPC.FUNCAO_COORDENADOR, ppc_id=self.ppc_id).exclude(id=self.id).exists()
        ):
            raise ValidationError('A comissão não pode ficar sem um membro coordenador.')
        super().clean()

    @transaction.atomic
    def adicionar_elaborador(self, ppc_id):
        self.ppc_id = ppc_id
        self.save()
        HistoricoElaboradorPPC.registrar(self, HistoricoElaboradorPPC.ACAO_CADASTRO)

    @transaction.atomic
    def remover(self):
        HistoricoElaboradorPPC.registrar(self, HistoricoElaboradorPPC.ACAO_EXCLUSAO)
        self.delete()

    @staticmethod
    def is_membro(user, ppc_id, funcao=None, permissao=None):
        qs = ElaboradorPPC.objects.filter(ppc_id=ppc_id, vinculo_id=user.get_vinculo().id)
        if funcao:
            qs = qs.filter(funcao=funcao)
        if permissao:
            qs = qs.filter(permissao=permissao)
        return qs.exists()


class ColaboradorPPC(LogModel):
    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='PPC', null=True, blank=True)
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Colaborador de PPC'
        verbose_name_plural = 'Colaboradores de PPC'

    def clean(self):
        if ColaboradorPPC.objects.filter(servidor_id=self.servidor_id, ppc_id=self.ppc_id).exclude(id=self.id).exists():
            raise ValidationError('Este servidor já é um colaborador deste PPC.')
        super().clean()

    @staticmethod
    def is_colaborador(user, ppc_id):
        if user.eh_servidor:
            return ColaboradorPPC.objects.filter(ppc_id=ppc_id, servidor=user.get_relacionamento(), ativo=True).exists()
        return False


class IndicacaoElaboradorPPC(LogModel):
    REPRESENTACAO_DOCENTE = '1'
    REPRESENTACAO_COORDENACAO = '2'
    REPRESENTACAO_ETEP = '3'
    REPRESENTACAO_TECNICO = '4'

    REPRESENTACAO_CHOICES = [
        [REPRESENTACAO_DOCENTE, 'Docente'],
        [REPRESENTACAO_COORDENACAO, 'Coordenação de Curso'],
        [REPRESENTACAO_ETEP, 'ETEP'],
        [REPRESENTACAO_TECNICO, 'Técnico'],
    ]

    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', null=True, blank=False)  # TODO: issue17120 remover após migração
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Indicado', null=True, blank=False)
    solicitacao = models.ForeignKeyPlus('ppc.SolicitacaoPPC', verbose_name='Solicitação de PPC', null=True, blank=True)
    funcao = models.CharFieldPlus(
        verbose_name='Função', null=False, blank=False, choices=ElaboradorPPC.FUNCAO_CHOICES, default=ElaboradorPPC.FUNCAO_MEMBRO
    )
    representacao = models.CharFieldPlus(verbose_name='Representação', null=True, blank=False, choices=REPRESENTACAO_CHOICES)
    deferido = models.BooleanField('Deferido', null=True)
    avaliador = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Servidor', null=True, blank=True, related_name='indicacaoelaboradorppc_avaliador_set'
    )
    justificativa_rejeicao = models.TextField('Justificativa da rejeição', null=True, blank=False)

    class Meta:
        verbose_name = 'Indicação de Elaborador de PPC'
        verbose_name_plural = 'Indicações de Elaboradores de PPC'
        ordering = ['funcao', 'vinculo__pessoa__nome']

    def aprovar(self, user):
        self.deferido = True
        self.avaliador = user.get_relacionamento()
        self.save()

    def negar(self, user):
        self.deferido = False
        self.avaliador = user.get_relacionamento()
        self.save()


class AtualizacaoComissaoElaboracao(LogModel):
    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='PPC', null=True, blank=True)
    id_portaria = models.PositiveIntegerFieldPlus(
        verbose_name='ID portaria', null=True, blank=True, help_text='Identificador do documento Portaria de Elaboração do PPC.'
    )
    concluida = models.BooleanField(
        'Atualização concluída', default=False, help_text='Indica se foi concluída a atualização dos membros da comissão no cadastro do PPC. '
    )
    data = models.DateTimeFieldPlus('Data', auto_now=True)

    class Meta:
        verbose_name = 'Atualização da Comissão de Elaboração'
        verbose_name_plural = 'Atualizações das Comissões de Elaboração'
        ordering = ['-data']

    def get_portaria(self):
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoTexto

            try:
                return self.id_portaria and DocumentoTexto.objects.get(id=self.id_portaria)
            except DocumentoTexto.DoesNotExist:
                return SolicitacaoPPC.DOCUMENTO_NAO_EXISTE
        return None


class HistoricoElaboradorPPC(LogModel):
    ACAO_CADASTRO = '1'
    ACAO_EDICAO = '2'
    ACAO_EXCLUSAO = '3'
    ACAO_CHOICES = [
        [ACAO_CADASTRO, 'Adicionado'],
        [ACAO_EDICAO, 'Atualizado'],
        [ACAO_EXCLUSAO, 'Removido'],
    ]

    atualizacao_comissao = models.ForeignKeyPlus(
        'ppc.AtualizacaoComissaoElaboracao', verbose_name='Atualização da Comissão de Elaboração', null=False, blank=False
    )
    acao = models.CharFieldPlus(verbose_name='Ação', null=False, blank=False, choices=ACAO_CHOICES)
    servidor = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Servidor', null=True, blank=False
    )  # TODO: issue17120 remover após migração de dados
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Elaborador', null=True, blank=False)
    funcao = models.CharFieldPlus(verbose_name='Função', null=False, blank=False, choices=ElaboradorPPC.FUNCAO_CHOICES)
    permissao = models.CharFieldPlus(verbose_name='Permissão', null=False, blank=False, choices=ElaboradorPPC.PERMISSAO_CHOICES)
    data_inicial = models.DateFieldPlus('Data Início', null=False, blank=False)
    data_final = models.DateFieldPlus('Data Final', null=True, blank=True)

    class Meta:
        verbose_name = 'Histórico de Elaborador de PPC'
        verbose_name_plural = 'Históricos de Elaboradores de PPC'

    @staticmethod
    def registrar(elaborador, acao):
        h = HistoricoElaboradorPPC()
        h.atualizacao_comissao = elaborador.ppc.get_atualizacao_comissao()
        h.acao = acao
        h.vinculo = elaborador.vinculo
        h.funcao = elaborador.funcao
        h.permissao = elaborador.permissao
        h.data_inicial = elaborador.data_inicial
        if acao == HistoricoElaboradorPPC.ACAO_EXCLUSAO:
            h.data_final = datetime.date.today()
        h.save()


class RevisorPPC(LogModel):
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', null=False, blank=False)
    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='PPC', null=True, blank=True)
    data_inicial = models.DateFieldPlus('Data Início', null=False, blank=False)
    data_final = models.DateFieldPlus('Data Final', null=True, blank=True)
    papel = models.CharFieldPlus('Papel', null=False, blank=False, default='Revisor')

    class Meta:
        verbose_name = 'Revisor de PPC'
        verbose_name_plural = 'Revisores de PPC'

    def can_delete(self, user=None):
        return self.ppc.pode_adicionar_revisor(user)


class ConteudoPPC(LogModel):
    EM_EDICAO = '1'
    AGUARDANDO_REVISAO = '2'
    EM_REVISAO = '3'
    ENVIADO_CORRECAO = '4'
    HOMOLOGADO = '5'

    SITUACAO_CHOICES = [
        [EM_EDICAO, 'Em edição'],
        [AGUARDANDO_REVISAO, 'Edição concluída'],
        [EM_REVISAO, 'Em revisão'],
        [ENVIADO_CORRECAO, 'Solicitado correção'],
        [HOMOLOGADO, 'Homologado'],
    ]

    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='PPC', null=False, blank=False)
    conteudo_modelo = models.ForeignKeyPlus('ppc.Conteudo', verbose_name='Conteúdo', null=False, blank=False)
    texto = models.TextField('Texto', null=True, blank=True)
    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=SITUACAO_CHOICES, default=EM_EDICAO)
    revisor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Revisor', null=True, blank=True)
    parecer_revisor = models.TextField('Parecer do Revisor', null=True, blank=False)

    class Meta:
        verbose_name = 'Conteúdo de PPC'
        verbose_name_plural = 'Conteúdos de PPC'
        ordering = ['conteudo_modelo__secao__ordem_exibicao', 'conteudo_modelo__ordem_exibicao']

    def __str__(self):
        return f'Item #{self.conteudo_modelo.ordem_exibicao} ({self.conteudo_modelo.secao.titulo})'

    def pode_editar(self, user):
        # TODO: remover permissão temporaria da DIPED editar conteudo após sinalização deles
        original = (
            self.situacao == ConteudoPPC.EM_EDICAO
            and self.ppc.situacao == ProjetoPedagogicoCurso.EM_ELABORACAO
            and self.conteudo_modelo.editavel
            and ElaboradorPPC.is_membro(user, self.ppc_id, permissao=ElaboradorPPC.PERMISSAO_EDICAO)
        )
        return original or (
            self.situacao != ConteudoPPC.HOMOLOGADO and self.conteudo_modelo.editavel and user.has_perm('comum.is_administrador_de_ppc')
        )

    def pode_revisar(self, user):
        return (
            self.situacao == ConteudoPPC.EM_REVISAO
            and self.ppc.situacao == ProjetoPedagogicoCurso.EM_REVISAO
            and self.conteudo_modelo.editavel
            and self.revisor == user.get_relacionamento()
        )

    def pode_retomar_edicao(self, user):
        if self.ppc.pode_elaborar(user):
            return self.situacao == ConteudoPPC.AGUARDANDO_REVISAO
        return False

    def pode_assumir_revisao(self, user):
        if user.eh_servidor:
            return (
                self.situacao in [ConteudoPPC.AGUARDANDO_REVISAO, ConteudoPPC.EM_REVISAO]
                and self.ppc.situacao == ProjetoPedagogicoCurso.EM_REVISAO
                and self.conteudo_modelo.editavel
                and RevisorPPC.objects.filter(servidor=user.get_relacionamento(), ppc_id=self.ppc_id).exists()
            )
        return False

    def pode_desfazer_homologacao(self, user):
        if user.eh_servidor:
            return (
                self.situacao == ConteudoPPC.HOMOLOGADO
                and self.ppc.situacao == ProjetoPedagogicoCurso.EM_REVISAO
                and self.conteudo_modelo.editavel
                and RevisorPPC.objects.filter(servidor=user.get_relacionamento(), ppc_id=self.ppc_id).exists()
            )
        return False

    def desfazer_homologacao(self, user):
        self.situacao = ConteudoPPC.EM_REVISAO
        self.revisor = user.get_relacionamento()
        self.save()

    def retomar_edicao(self, user):
        self.situacao = ConteudoPPC.EM_EDICAO
        self.save()

    def assumir_revisao(self, user):
        self.situacao = ConteudoPPC.EM_REVISAO
        self.revisor = user.get_relacionamento()
        self.save()

    def enviar_para_revisao(self, user):
        self.situacao = ConteudoPPC.AGUARDANDO_REVISAO
        self.parecer_revisor = None
        self.save()

    def enviar_para_correcao(self, user):
        self.situacao = ConteudoPPC.ENVIADO_CORRECAO
        self.save()

    def homologar(self, user):
        self.situacao = ConteudoPPC.HOMOLOGADO
        self.revisor = user.get_relacionamento()
        self.save()

    def get_planos_disciplinas_html(self, nucleo):
        with open('ppc/templates/planodisciplina_pdf.html') as file:
            planosdisciplinasppc_html = file.read()
        template = Template(planosdisciplinasppc_html)
        qs = (
            PlanoDisciplinaPPC.objects.filter(plano_disciplina__nucleo__descricao=nucleo, matriz_ppc__ppc_id=self.ppc_id)
            .values_list('plano_disciplina_id', flat=True)
            .distinct()
        )
        ids_regular = qs.filter(qtd_aulas_ead=0)
        ids_ead = qs.exclude(qtd_aulas_ead=0)

        dicionario = {
            'planosdisciplinas_regular': PlanoDisciplina.objects.filter(id__in=ids_regular).order_by('nome_disciplina'),
            'planosdisciplinas_ead': PlanoDisciplina.objects.filter(id__in=ids_ead).order_by('nome_disciplina'),
            'nome_curso': self.ppc.nome_curso,
        }
        return template.render(Context(dicionario))

    def get_quadro_matriz_html(self):
        with open('ppc/templates/quadro_matriz.html') as file:
            quadro_matriz_html = file.read()
        template = Template(quadro_matriz_html)
        nucleos_matriz = self.ppc.get_nucleos_matriz().select_related('nucleo').only('nucleo__descricao', 'nucleo_id')
        nucleos_pratica = self.ppc.get_nucleos_pratica().select_related('nucleo').only('nucleo__descricao', 'nucleo_id')
        dicionario = {
            'projeto': self.ppc,
            'matrizes': self.ppc.matrizppc_set.defer('ppc', 'turno', 'matriz', 'cursos').all(),
            'nucleos_matriz': nucleos_matriz,
            'nucleos_pratica': nucleos_pratica,
            'semestres': [1, 2],
        }
        return template.render(Context(dicionario))

    def get_quadro_requisitos_html(self):
        with open('ppc/templates/quadro_requisitos.html') as file:
            quadro_html = file.read()
        template = Template(quadro_html)
        dicionario = {
            'projeto': self.ppc,
            'matrizes': self.ppc.matrizppc_set.prefetch_related('planodisciplinappc_set').only('nome').all(),
        }
        return template.render(Context(dicionario))

    def get_quadro_optativas_html(self):
        with open('ppc/templates/quadro_optativas.html') as file:
            quadro_html = file.read()
        template = Template(quadro_html)
        nucleos_matriz = self.ppc.get_nucleos_matriz().select_related('nucleo').only('nucleo__descricao', 'nucleo_id')
        nucleos_pratica = self.ppc.get_nucleos_pratica().select_related('nucleo').only('nucleo__descricao', 'nucleo_id')
        dicionario = {
            'projeto': self.ppc,
            'matrizes': self.ppc.matrizppc_set.defer('ppc', 'turno', 'matriz', 'cursos').all(),
            'nucleos_matriz': nucleos_matriz,
            'nucleos_pratica': nucleos_pratica,
            'semestres': [1, 2],
        }
        return template.render(Context(dicionario))

    def get_certificacao_intermediaria_html(self):
        with open('ppc/templates/certificacao_intermediaria.html') as file:
            certificacao_intermediaria_html = file.read()
        template = Template(certificacao_intermediaria_html)
        dicionario = {
            'projeto': self.ppc,
        }
        return template.render(Context(dicionario))

    def quebra_de_pagina_html(self):
        return Template('<div class="page-break"></div>').render(Context())

    def get_texto(self):
        texto = str(self.texto)
        dicionario = {}
        if 'nome_curso' in texto:
            dicionario['nome_curso'] = self.ppc.nome_curso
        if 'nome_diploma_historico' in texto:
            dicionario['nome_diploma_historico'] = self.ppc.nome_diploma_historico
        if 'eixo_tecnologico' in texto:
            dicionario['eixo_tecnologico'] = self.ppc.solicitacao.eixo_tecnologico or ''
        if 'quadro_matriz' in texto:
            dicionario['quadro_matriz'] = self.get_quadro_matriz_html()
        if 'quadro_requisitos' in texto:
            dicionario['quadro_requisitos'] = self.get_quadro_requisitos_html()
        if 'quadro_optativas' in texto:
            dicionario['quadro_optativas'] = self.get_quadro_optativas_html()
        if 'quebra_de_pagina' in texto:
            dicionario['quebra_de_pagina'] = self.quebra_de_pagina_html()
        if 'ch_curso' in texto:
            dicionario['ch_curso'] = self.ppc.ch_curso
        if 'ch_matriz' in texto:
            dicionario['ch_matriz'] = self.ppc.get_ch_exigida_matriz()
        if 'ch_pratica' in texto:
            dicionario['ch_pratica'] = self.ppc.ch_pratica
        if 'certificacao_intermediaria' in texto:
            dicionario['certificacao_intermediaria'] = self.get_certificacao_intermediaria_html()
        if 'bibliografia' in texto:
            dicionario['bibliografia'] = mark_safe(self.ppc.bibliografia_html) or ''

        for marcador, descricao in self.ppc.get_marcadores_dinamicos():
            if marcador in texto:
                dicionario[marcador] = self.get_planos_disciplinas_html(descricao)

        return substituir_marcadores(texto, dicionario)


class ComentarioConteudoPPC(LogModel):
    conteudo_ppc = models.ForeignKeyPlus('ppc.ConteudoPPC', verbose_name='Conteúdo PPC', null=False, blank=False)
    texto = models.TextField(verbose_name='Texto', null=False, blank=False)
    revisor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Revisor', null=False, blank=False)

    def __str__(self):
        return f'{self.texto} ({self.revisor.nome_usual})'


class MovimentacaoSolicitacaoPPC(LogModel):
    solicitacao = models.ForeignKeyPlus('ppc.SolicitacaoPPC', verbose_name='Solicitação de PPC', null=False, blank=False)
    data = models.DateTimeFieldPlus('Data', auto_now=True)
    usuario = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Usuário', null=True, blank=False)
    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=SolicitacaoPPC.SITUACAO_CHOICES)
    acao = models.CharFieldPlus(verbose_name='Ação', null=True, blank=True, max_length=510)

    class Meta:
        verbose_name = 'Movimentação de Solicitação de PPC'
        verbose_name_plural = 'Movimentações de Solicitações de PPC'
        ordering = ['id']

    @staticmethod
    def registrar_movimentacao(user, solicitacao, acao=None):
        registro = MovimentacaoSolicitacaoPPC()
        registro.solicitacao = solicitacao
        registro.usuario = user and user.get_vinculo()
        registro.situacao = solicitacao.situacao
        registro.acao = acao
        registro.save()


class MovimentacaoPPC(LogModel):
    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='Projeto pedagógico de curso', null=False, blank=False)
    data = models.DateTimeFieldPlus('Data', auto_now=True)
    usuario = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Usuário', null=True, blank=False)
    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=ProjetoPedagogicoCurso.SITUACAO_CHOICES)
    acao = models.TextField(verbose_name='Ação', null=True, blank=True)

    class Meta:
        verbose_name = 'Movimentação de PPC'
        verbose_name_plural = 'Movimentações de PPC'
        ordering = ['id']

    @staticmethod
    def registrar_movimentacao(user, ppc, acao=None):
        registro = MovimentacaoPPC()
        registro.ppc = ppc
        registro.usuario = user and user.get_vinculo()
        registro.situacao = ppc.situacao
        registro.acao = acao
        registro.save()


class ModeloPlanoDisciplina(LogModel):
    descricao = models.CharFieldPlus('Descrição')
    orientacoes = models.TextField('Orientações de preenchimento', blank=True, null=True)
    data_criacao = models.DateFieldPlus('Data de criação', auto_now_add=True)
    nivel_ensino = models.ForeignKeyPlus('edu.NivelEnsino', verbose_name='Nível de ensino', null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=False)
    permite_secoes_ead = models.BooleanField(
        'Permite seções EAD',
        default=False,
        help_text='Se habilitado, permite que os planos de disciplina incluam seções distintas para as versões com e sem EAD.',
    )
    permite_versao_ead_plano_aprovado = models.BooleanField(
        'Permite criação de versão EAD de plano aprovado',
        default=False,
        help_text='Se habilitado, permite que seja criado a versão EAD de um plano de disciplina que já foi aprovado.',
    )

    class Meta:
        verbose_name = 'Modelo de plano de disciplina'
        verbose_name_plural = 'Modelos de plano de disciplina'

    def get_absolute_url(self):
        return f'/ppc/modeloplanodisciplina/{self.id}/'

    def can_delete(self, user=None):
        return user.has_perm('ppc.delete_modeloplanodisciplina') and not PlanoDisciplina.objects.filter(modelo_plano_disciplina_id=self.id).exists()

    def clean(self):
        if self.ativo and ModeloPlanoDisciplina.objects.filter(ativo=True, nivel_ensino_id=self.nivel_ensino_id).exclude(id=self.pk).exists():
            raise ValidationError('Já existe um modelo de plano de disciplina ativo para este nível de ensino.')
        if self.ativo and not self.modelosecaoplanodisciplina_set.exists():
            raise ValidationError('É necessário criar pelo menos uma seção antes de ativar o modelo de plano de disciplina.')
        if self.id and self.planodisciplina_set.exists() and self.nivel_ensino_id != ModeloPlanoDisciplina.objects.get(id=self.id).nivel_ensino_id:
            raise ValidationError('O nível de ensino não pode ser modificado, pois existem planos de disciplina já vinculados a este modelo.')

        return super().clean()

    def pode_adicionar_secao(self, user):
        return user.has_perm('ppc.add_modeloplanodisciplina') and not PlanoDisciplina.objects.filter(modelo_plano_disciplina_id=self.id).exists()

    @transaction.atomic
    def replicar(self, descricao, nivel_ensino):
        replicado = ModeloPlanoDisciplina()
        replicado.descricao = descricao
        replicado.nivel_ensino = nivel_ensino
        replicado.save()

        for secao in self.modelosecaoplanodisciplina_set.all():
            secao_replicada = copy.copy(secao)
            secao_replicada.id = None
            secao_replicada.modelo_plano_disciplina = replicado
            secao_replicada.save()

        return replicado


class ModeloSecaoPlanoDisciplina(LogModel):
    titulo = models.CharFieldPlus('Título')
    ordem_exibicao = models.PositiveIntegerFieldPlus('Ordem de Exibição', default=1, min_value=1)
    modelo_plano_disciplina = models.ForeignKeyPlus(
        'ppc.ModeloPlanoDisciplina', verbose_name='Modelo de plano de disciplina', null=False, blank=False
    )

    class Meta:
        verbose_name = 'Seção de plano de disciplina'
        verbose_name_plural = 'Seções de planos de disciplinas'
        ordering = [
            'ordem_exibicao',
        ]

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        ModeloSecaoPlanoDisciplina.recalcular_ordem(self)
        return result

    def delete(self, *args, **kwargs):
        ModeloSecaoPlanoDisciplina.recalcular_ordem(self, delete=True)
        return super().delete(*args, **kwargs)

    @staticmethod
    @transaction.atomic
    def recalcular_ordem(secao, delete=False):
        secoes = ModeloSecaoPlanoDisciplina.objects.filter(modelo_plano_disciplina_id=secao.modelo_plano_disciplina_id)
        if delete:
            for seq, item in enumerate(secoes.exclude(id=secao.pk), start=1):
                if item.ordem_exibicao != seq:
                    ModeloSecaoPlanoDisciplina.objects.filter(id=item.id).update(ordem_exibicao=seq)
        else:
            atualizacao_ordem_exibicao = secao.ordem_exibicao
            if atualizacao_ordem_exibicao < 1:
                atualizacao_ordem_exibicao = 1
            elif atualizacao_ordem_exibicao > secoes.count():
                atualizacao_ordem_exibicao = secoes.count()
            nova_ordem = list(secoes.exclude(id=secao.id))
            nova_ordem.insert(atualizacao_ordem_exibicao - 1, secao)
            for seq, item in enumerate(nova_ordem, start=1):
                if item.ordem_exibicao != seq:
                    ModeloSecaoPlanoDisciplina.objects.filter(id=item.id).update(ordem_exibicao=seq)


class PlanoDisciplina(LogModel):
    SEARCH_FIELDS = ['nome_disciplina', 'id']

    ELABORACAO = '1'
    AGUARDANDO_ANALISE = '2'
    EM_ANALISE = '3'
    APROVADO = '4'
    REJEITADO = '5'
    SITUACAO_CHOICES = [
        [ELABORACAO, 'Em elaboração'],
        [AGUARDANDO_ANALISE, 'Aguardando revisão'],
        [EM_ANALISE, 'Em revisão'],
        [APROVADO, 'Aprovado'],
        [REJEITADO, 'Reprovado'],
    ]

    PERIODICIDADE_ANUAL = 1
    PERIODICIDADE_SEMESTRAL = 2
    PERIODICIDADE_CHOICES = [[PERIODICIDADE_ANUAL, 'Anual'], [PERIODICIDADE_SEMESTRAL, 'Semestral']]

    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=SITUACAO_CHOICES, default=ELABORACAO)
    nome_disciplina = models.CharFieldPlus('Nome da disciplina', null=False, blank=False)
    ch_disciplina = models.PositiveIntegerFieldPlus('Carga horária da disciplina', null=False, blank=False, min_value=1)
    desconsiderar_qtd_credito = models.BooleanField(
        'Desconsiderar créditos',
        default=False,
        help_text='Marque esta opção caso a quantidade de créditos contabilizada para este plano de disciplina deva ser igual a 0 (zero).',
    )
    ementa = models.TextField('Ementa', null=False, blank=False)
    modelo_plano_disciplina = models.ForeignKeyPlus(
        'ppc.ModeloPlanoDisciplina', verbose_name='Modelo de plano de disciplina', null=False, blank=False
    )
    diretriz = models.ForeignKeyPlus('ppc.Diretriz', verbose_name='Diretriz', null=True, blank=False)
    tipo_oferta = models.ForeignKeyPlus('edu.Modalidade', verbose_name='Tipo de oferta', null=False, blank=False)
    nucleo = models.ForeignKeyPlus('edu.Nucleo', verbose_name='Núcleo', null=False, blank=False)
    periodicidade = models.PositiveIntegerField('Periodicidade', choices=PERIODICIDADE_CHOICES, null=True, blank=True)
    comissao_ptdem = models.ForeignKeyPlus('ppc.ComissaoPTDEM', verbose_name='Comissão de plano de disciplina', null=True, blank=True)
    avaliador = models.ForeignKeyPlus('rh.Servidor', null=True, blank=True, verbose_name='Revisor')
    ativo = models.BooleanField('Ativo', default=True)
    justificativa = models.TextField('Justificativa', null=True, blank=False)
    topico_especifico = models.BooleanField(
        'Tópico específico',
        default=False,
        help_text='Marcar esta opção permite que os cursos modifiquem o conteúdo deste plano de disciplina no âmbito de seus POMCs.',
    )

    componente = models.ForeignKeyPlus(
        'edu.Componente', verbose_name='Componente', null=True, blank=True, help_text='Componente gerado a partir do plano de disciplina.'
    )

    plano_origem = models.ForeignKeyPlus('ppc.PlanoDisciplina', verbose_name='Plano de Disciplina de Origem', null=True, blank=True)

    ppc_criacao = models.ForeignKeyPlus(
        'ppc.ProjetoPedagogicoCurso',
        verbose_name='PPC de criação',
        related_name='planos_disciplina_criados',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text='Indica o PPC no qual este plano de disciplina foi originado, se aplicável.',
    )

    class Meta:
        verbose_name = 'Plano de disciplina'
        verbose_name_plural = 'Planos de disciplinas'

    def __str__(self):
        return f'{self.id} - {self.nome_disciplina} {self.ch_disciplina}h'

    @transaction.atomic()
    def save(self, *args, **kwargs):
        if self.tipo_oferta_id is None:
            self.tipo_oferta = self.diretriz.tipo_oferta

        if self.modelo_plano_disciplina_id is None:
            try:
                modelo_plano_disciplina = ModeloPlanoDisciplina.objects.get(nivel_ensino_id=self.tipo_oferta.nivel_ensino_id, ativo=True)
            except Exception:
                raise ValidationError(f'Não foi encontrado um modelo de plano de disciplina para o nível de ensino {self.tipo_oferta.nivel_ensino}.')
            self.modelo_plano_disciplina = modelo_plano_disciplina

        replicado = kwargs.pop('replicado', False)

        result = super().save(*args, **kwargs)

        if not replicado:
            if not self.secaoplanodisciplina_set.exists():
                for modelo in modelo_plano_disciplina.modelosecaoplanodisciplina_set.all():
                    secao = SecaoPlanoDisciplina()
                    secao.plano_disciplina = self
                    secao.modelo_secao_plano_disciplina = modelo
                    secao.save()

            if self.situacao == PlanoDisciplina.ELABORACAO and self.periodicidade in [
                PlanoDisciplina.PERIODICIDADE_ANUAL,
                PlanoDisciplina.PERIODICIDADE_SEMESTRAL,
            ]:
                for plano_ppc in PlanoDisciplinaPPC.objects.filter(plano_disciplina_id=self.id):
                    if plano_ppc.matriz_ppc.ppc.is_curso_anual():
                        if self.periodicidade == PlanoDisciplina.PERIODICIDADE_ANUAL:
                            plano_ppc.quantidade_etapas = 4
                            plano_ppc.segundo_semestre = False
                            plano_ppc.save()
                        elif self.periodicidade == PlanoDisciplina.PERIODICIDADE_SEMESTRAL:
                            plano_ppc.quantidade_etapas = 2
                            plano_ppc.save()

        return result

    def clean(self):
        if self.ch_disciplina is None:
            raise ValidationError('A carga horária da disciplina é obrigatória.')

        super().clean()

    @transaction.atomic()
    def vincular_planodisciplinappc(self, matriz_ppc, user):
        if self.diretriz is None:
            self.diretriz_id = matriz_ppc.ppc.diretriz_id
        if self.pk is None and self.comissao_ptdem is None:
            self.ppc_criacao_id = matriz_ppc.ppc_id
        self.save()
        plano = PlanoDisciplinaPPC()
        plano.plano_disciplina = self
        plano.matriz_ppc = matriz_ppc
        if self.periodicidade == PlanoDisciplina.PERIODICIDADE_ANUAL and matriz_ppc.ppc.is_curso_anual():
            plano.quantidade_etapas = 4
        elif self.periodicidade == PlanoDisciplina.PERIODICIDADE_SEMESTRAL and matriz_ppc.ppc.is_curso_anual():
            plano.quantidade_etapas = 2
        plano.ch_teorica = self.ch_disciplina
        plano.clean()
        plano.save()
        MovimentacaoPlanoDisciplina.registrar_movimentacao(user, self)
        return plano

    def notificar(self, mensagem, notificar_elaboradores, notificar_avaliadores):
        destinatarios = set()
        if notificar_elaboradores:
            for elaborador in ElaboradorPPC.objects.filter(ppc__matrizppc__planodisciplinappc__plano_disciplina_id=self.pk):
                destinatarios.add(elaborador.vinculo)
            if self.comissao_ptdem:
                for servidor in ComissaoPTDEM.objects.get(id=self.comissao_ptdem_id).servidores.all():
                    destinatarios.add(servidor.get_vinculo())

        if notificar_avaliadores:
            setor_id = Configuracao.get_valor_por_chave('ppc', 'setor_revisao_plano_disciplina')
            if setor_id:
                vinculos = list(Vinculo.objects.filter(setor_id=setor_id, ativo=True))
                destinatarios.update(vinculos)
            for revisor in RevisorPlanoDisciplina.objects.filter(ativo=True):
                destinatarios.add(revisor.servidor.get_vinculo())

        if destinatarios:
            url = f'{settings.SITE_URL}{self.get_absolute_url()}'
            titulo = '[SUAP] PPC: Atualização de plano de disciplina'
            corpo = f"""<h1>Atualização de plano de disciplina</h1>
                <p>{mensagem}</p>
                <p class="more-info">Para mais informações, acesse: <a href="{url}">{url}</a></p>"""
            send_notification(titulo, corpo, settings.DEFAULT_FROM_EMAIL, destinatarios)

    def aprovar(self, user):
        self.situacao = PlanoDisciplina.APROVADO
        self.avaliador = user.get_relacionamento()
        self.save()
        MovimentacaoPlanoDisciplina.registrar_movimentacao(user, self)
        self.notificar(f'O plano de disciplina {self} foi aprovado.', notificar_elaboradores=True, notificar_avaliadores=False)

    def desaprovar(self, user):
        self.situacao = PlanoDisciplina.EM_ANALISE
        self.avaliador = user.get_relacionamento()
        self.save()
        MovimentacaoPlanoDisciplina.registrar_movimentacao(user, self)
        self.notificar(f'A aprovação do plano de disciplina {self} foi desfeita.', notificar_elaboradores=True, notificar_avaliadores=False)

    @transaction.atomic()
    def rejeitar(self, user):
        self.situacao = PlanoDisciplina.REJEITADO
        self.avaliador = user.get_relacionamento()
        self.ativo = False
        self.save()
        MovimentacaoPlanoDisciplina.registrar_movimentacao(user, self)
        if self.possui_revisao_pendente():
            for revisao in self.revisaoplanodisciplina_set.filter(resolvido=False):
                revisao.atualizar_resolvida(user.get_vinculo())
                ComentarioRevisaoPlanoDisciplina.adicionar(revisao, user.get_vinculo(), 'rejeitou este plano de disciplina', automatico=True)
        self.notificar(f'O plano de disciplina {self} foi reprovado.', notificar_elaboradores=True, notificar_avaliadores=False)

    def enviar_analise(self, user):
        self.situacao = PlanoDisciplina.AGUARDANDO_ANALISE
        self.save()
        MovimentacaoPlanoDisciplina.registrar_movimentacao(user, self)
        self.notificar(f'O plano de disciplina {self} foi enviado para análise.', notificar_elaboradores=True, notificar_avaliadores=True)

    def analisar(self, user):
        self.situacao = PlanoDisciplina.EM_ANALISE
        self.avaliador = user.get_relacionamento()
        self.save()
        MovimentacaoPlanoDisciplina.registrar_movimentacao(user, self)
        self.notificar(f'Foi iniciada a análise do plano de disciplina {self}.', notificar_elaboradores=True, notificar_avaliadores=False)

    def enviar_elaboracao(self, user):
        self.situacao = PlanoDisciplina.ELABORACAO
        self.avaliador = user.get_relacionamento()
        self.save()
        MovimentacaoPlanoDisciplina.registrar_movimentacao(user, self)
        self.notificar(f'O plano de disciplina {self} foi devolvido para elaboração', notificar_elaboradores=True, notificar_avaliadores=False)

    def inativar(self):
        self.ativo = False
        self.save()
        self.notificar(f'O plano de disciplina {self} foi inativado.', notificar_elaboradores=True, notificar_avaliadores=False)

    def reativar(self):
        self.ativo = True
        self.save()
        self.notificar(f'O plano de disciplina {self} foi reativado.', notificar_elaboradores=True, notificar_avaliadores=False)

    @transaction.atomic()
    def replicar(self):
        replicado = copy.copy(self)
        replicado.id = None
        replicado.pk = None
        replicado.ativo = True
        replicado.nome_disciplina = f'{self.nome_disciplina} [REPLICADO]'
        replicado.situacao = PlanoDisciplina.ELABORACAO
        replicado.avaliador = None
        replicado.save(replicado=True)

        for secao in self.secaoplanodisciplina_set.all():
            secao_replicada = copy.copy(secao)
            secao_replicada.id = None
            secao_replicada.plano_disciplina = replicado
            secao_replicada.save()

        return replicado

    @transaction.atomic()
    def duplicar(self, tipo_oferta, diretriz):
        duplicado = copy.copy(self)
        duplicado.id = None
        duplicado.pk = None
        duplicado.plano_origem_id = self.id
        duplicado.tipo_oferta = tipo_oferta
        duplicado.diretriz = diretriz
        duplicado.save(replicado=True)

        for secao in self.secaoplanodisciplina_set.all():
            secao_duplicada = copy.copy(secao)
            secao_duplicada.id = None
            secao_duplicada.plano_disciplina = duplicado
            secao_duplicada.save()

        return duplicado

    @transaction.atomic()
    def criar_versao_ead(self):
        if self.situacao == PlanoDisciplina.APROVADO:
            self.situacao = PlanoDisciplina.EM_ANALISE
            self.save()
        for secao in self.get_secoes():
            secao_ead = copy.copy(secao)
            secao_ead.id = None
            secao_ead.versao_ead = True
            secao_ead.save()

    @transaction.atomic()
    def excluir_versao_ead(self):
        self.get_secoes_ead().delete()

    @staticmethod
    def remover_formatacao(html):
        import re

        h_tag = r'<h[^>]*>(.*?)</h[^>]*>'

        def substitui_h_tag(match):
            tag_content = match.group(1)
            return f'<strong>{tag_content}</strong>'

        html_substituido = re.sub(h_tag, substitui_h_tag, html)

        estilos = r'style="[^"]*"'
        html = re.sub(estilos, '', html_substituido)

        data_font = r'data-font="[^"]*"'
        html = re.sub(data_font, '', html)

        paragrafo_vazio = r'<p>(&nbsp;|\s)*</p>'
        html = re.sub(paragrafo_vazio, '', html)

        multiplos_espacos = r'(&nbsp;)+'
        html = re.sub(multiplos_espacos, '', html)

        return html

    def get_absolute_url(self):
        return f'/ppc/planodisciplina/{self.id}/'

    def get_tipo_componente(self):
        if self.tipo_oferta_id == Modalidade.INTEGRADO:
            return TipoComponente.objects.get(descricao='TIN')
        if self.tipo_oferta_id in [Modalidade.LICENCIATURA, Modalidade.LICENCIATURA_DUPLA_HABILITACAO]:
            return TipoComponente.objects.get(descricao='LIC')
        if self.tipo_oferta_id == Modalidade.ENGENHARIA:
            return TipoComponente.objects.get(descricao='ENG')
        if self.tipo_oferta_id in [Modalidade.FIC, Modalidade.FIC_MENOS, Modalidade.PROEJA_FIC_FUNDAMENTAL]:
            return TipoComponente.objects.get(descricao='FIC')
        if self.tipo_oferta_id in [Modalidade.MESTRADO, Modalidade.ESPECIALIZACAO, Modalidade.APERFEICOAMENTO, Modalidade.DOUTORADO]:
            return TipoComponente.objects.get(descricao='POS')
        if self.tipo_oferta_id in [Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA]:
            return TipoComponente.objects.get(descricao='EJA')
        if self.tipo_oferta_id == Modalidade.SUBSEQUENTE:
            return TipoComponente.objects.get(descricao='TSUB')
        if self.tipo_oferta_id == Modalidade.TECNOLOGIA:
            return TipoComponente.objects.get(descricao='TEC')
        raise ValidationError('Tipo de componente não definido.')

    @staticmethod
    def get_meus_planos(vinculo, queryset):
        comissoes_ppc = ElaboradorPPC.objects.filter(vinculo_id=vinculo.id).values_list('ppc_id', flat=True)
        qs = queryset.filter(comissao_ptdem__isnull=True, planodisciplinappc__matriz_ppc__ppc_id__in=comissoes_ppc)
        if vinculo.eh_servidor():
            comissoes_pd = ComissaoPTDEM.objects.filter(servidores=vinculo.relacionamento)
            qs = qs | queryset.filter(comissao_ptdem__in=comissoes_pd)
        return qs.distinct()

    def get_secoes(self):
        return self.secaoplanodisciplina_set.filter(versao_ead=False).order_by('modelo_secao_plano_disciplina__ordem_exibicao')

    def get_secoes_ead(self):
        return self.secaoplanodisciplina_set.filter(versao_ead=True).order_by('modelo_secao_plano_disciplina__ordem_exibicao')

    def get_secoes_impressao(self, versao_ead=False):
        if versao_ead and self.possui_versao_ead():
            return self.get_secoes_ead()
        return self.get_secoes()

    def get_secoes_impressao_ead(self):
        return self.get_secoes_impressao(True)

    def pode_comentar(self, user):
        eh_comissao = ComissaoPTDEM.objects.filter(servidores__matricula=user.username, id=self.comissao_ptdem_id).exists()
        eh_avaliador = PlanoDisciplina.is_avaliador(user)

        return eh_comissao or self.is_elaborador(user) or eh_avaliador

    def can_change(self, user):
        if self.situacao == PlanoDisciplina.ELABORACAO:
            if self.comissao_ptdem:
                # membro da comissão do Plano de Disciplina
                return ComissaoPTDEM.objects.filter(servidores__matricula=user.username, id=self.comissao_ptdem_id).exists()
            else:
                # membro da comissão de elaboração do PPC
                if self.ppc_criacao_id:
                    return ElaboradorPPC.is_membro(user, self.ppc_criacao_id, permissao=ElaboradorPPC.PERMISSAO_EDICAO)
        elif self.situacao == PlanoDisciplina.EM_ANALISE:
            return self.is_avaliador(user)
        return False

    def can_delete(self, user):
        if user.has_perm('ppc.delete_planodisciplina') and self.situacao == PlanoDisciplina.ELABORACAO:
            if self.planodisciplinappc_set.exists():
                return self.is_avaliador(user)
            else:
                return self.can_change(user) or self.is_avaliador(user)
        return False

    @staticmethod
    def is_avaliador(user):
        setor_id = Configuracao.get_valor_por_chave('ppc', 'setor_revisao_plano_disciplina')
        result = setor_id and user.get_vinculo() and user.get_vinculo().setor_id == int(setor_id) or False
        if not result:
            result = RevisorPlanoDisciplina.objects.filter(servidor__matricula=user.get_relacionamento().matricula).exists()
        return result

    def is_elaborador(self, user):
        plano = self.planodisciplinappc_set.first()
        return plano and ElaboradorPPC.is_membro(user, plano.matriz_ppc.ppc_id, permissao=ElaboradorPPC.PERMISSAO_EDICAO)

    def is_elaboracao(self):
        return self.situacao == PlanoDisciplina.ELABORACAO

    def is_aprovado(self):
        return self.situacao == PlanoDisciplina.APROVADO

    def pode_vincular_ppc(self):
        if self.situacao == PlanoDisciplina.REJEITADO:
            return False
        if self.comissao_ptdem:
            return True
        return self.situacao == PlanoDisciplina.APROVADO or self.diretriz.permite_plano_nao_aprovado

    def pode_enviar_analise(self, user):
        return (
            self.situacao == PlanoDisciplina.ELABORACAO
            and self.can_change(user)
            and not self.secaoplanodisciplina_set.filter(texto='').exists()
            and self.ementa
            and not self.possui_revisao_pendente()
        )

    def pode_analisar(self, user):
        return self.situacao == PlanoDisciplina.AGUARDANDO_ANALISE and PlanoDisciplina.is_avaliador(user)

    def pode_cadastrar_revisao(self, user):
        return self.estah_em_analise() and PlanoDisciplina.is_avaliador(user)

    def pode_devolver(self, user):
        """
        Verifica se o usuário pode devolver uma revisão que esteja em análise retornando para elaboração, caso exista revisoes pendentes
        """
        return self.pode_cadastrar_revisao(user) and self.possui_revisao_pendente()

    def pode_aprovar(self, user):
        return self.pode_cadastrar_revisao(user) and not self.possui_revisao_pendente()

    def pode_desaprovar(self, user):
        return self.pode_inativar(user) and not self.planodisciplinappc_set.filter(matriz_ppc__situacao_matriz=MatrizPPC.MATRIZ_APROVADA).exists()

    def pode_inativar(self, user):
        return self.ativo and self.situacao == PlanoDisciplina.APROVADO and PlanoDisciplina.is_avaliador(user)

    def pode_reativar(self, user):
        return not self.ativo and self.situacao == PlanoDisciplina.APROVADO and PlanoDisciplina.is_avaliador(user)

    def pode_replicar(self, user):
        return ComissaoPTDEM.objects.filter(servidores__matricula=user.username, id=self.comissao_ptdem_id).exists()

    def pode_duplicar(self, user):
        if not self.is_aprovado():
            return False
        if self.comissao_ptdem_id:
            return ComissaoPTDEM.objects.filter(servidores__matricula=user.username, id=self.comissao_ptdem_id).exists()
        if self.ppc_criacao_id:
            return ElaboradorPPC.is_membro(user, self.ppc_criacao_id, permissao=ElaboradorPPC.PERMISSAO_EDICAO)
        return False

    def pode_criar_versao_ead(self, user):
        if not self.modelo_plano_disciplina.permite_secoes_ead:
            return False
        if self.is_aprovado():
            return self.modelo_plano_disciplina.permite_versao_ead_plano_aprovado and self.is_avaliador(user) and not self.possui_versao_ead()
        if self.situacao in [PlanoDisciplina.ELABORACAO, PlanoDisciplina.EM_ANALISE]:
            return self.can_change(user) and not self.possui_versao_ead()
        return False

    def pode_excluir_versao_ead(self, user):
        if not self.possui_versao_ead():
            return False
        if self.situacao == PlanoDisciplina.APROVADO:
            return (
                self.modelo_plano_disciplina.permite_versao_ead_plano_aprovado
                and self.is_avaliador(user)
                and not self.planodisciplinappc_set.filter(matriz_ppc__situacao_matriz=MatrizPPC.MATRIZ_APROVADA, qtd_aulas_ead__gt=0).exists()
            )
        if self.situacao in [PlanoDisciplina.ELABORACAO, PlanoDisciplina.EM_ANALISE]:
            return self.can_change(user)

        return False

    def pode_remover_ppc_vinculado(self, user):
        return not self.ativo and PlanoDisciplina.is_avaliador(user)

    def possui_versao_ead(self):
        return self.secaoplanodisciplina_set.filter(versao_ead=True).exists()

    def possui_revisao_pendente(self):
        return self.revisaoplanodisciplina_set.filter(resolvido=False).exists()

    def estah_rejeitado(self):
        return self.situacao == PlanoDisciplina.REJEITADO

    def estah_em_analise(self):
        return self.situacao == PlanoDisciplina.EM_ANALISE


class RevisaoPlanoDisciplina(LogModel):
    USUARIO_ELABORADOR = 1
    USUARIO_REVISOR = 2

    TIPO_USUARIO_CHOICES = ((USUARIO_ELABORADOR, 'Revisor'), (USUARIO_REVISOR, 'Elaborador'))

    plano_disciplina = models.ForeignKeyPlus('ppc.PlanoDisciplina', verbose_name='Plano de Disciplina', null=False, blank=False)
    texto = models.TextField(verbose_name='Texto', null=False, blank=False)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Servidor', null=False)
    data_criacao = models.DateTimeFieldPlus(auto_now_add=True)
    resolvido = models.BooleanField('Resolvido', default=False)
    numero_revisao = models.PositiveIntegerFieldPlus('Número da revisão', null=False, blank=False, min_value=1)

    class Meta:
        verbose_name = 'Revisão do plano de disciplina'
        verbose_name_plural = 'Revisões dos planos de disciplinas'

    def pode_marcar_resolvido(self, user):
        return self.plano_disciplina.pode_comentar(user)

    def atualizar_resolvida(self, vinculo):
        pode_resolver = (
            self.plano_disciplina.is_elaboracao()
            or self.plano_disciplina.estah_rejeitado()
            or (self.plano_disciplina.estah_em_analise() and self.plano_disciplina.is_avaliador(vinculo.user))
        )
        if not self.pode_marcar_resolvido(vinculo.user) or not pode_resolver:
            raise ValidationError(f'O usuário {vinculo.user} não pode resolver ou o plano não está em uma das fases: Elaboração ou Em Análise.')
        self.resolvido = True
        self.save()
        texto_comentario = 'resolveu esta revisão.'
        ComentarioRevisaoPlanoDisciplina.adicionar(self, vinculo, texto_comentario, automatico=True)

    def retornar_para_nao_resovida(self, vinculo):
        self.resolvido = False
        self.save()
        texto_comentario = 'reabriu esta revisão.'
        ComentarioRevisaoPlanoDisciplina.adicionar(self, vinculo, texto_comentario, automatico=True)

    def get_comentarios(self):
        return self.comentariorevisaoplanodisciplina_set.all().order_by('-data_criacao')

    def collapsed_comments(self):
        return self.resolvido and 'collapsed' or ''


class ComentarioRevisaoPlanoDisciplina(LogModel):
    revisao = models.ForeignKeyPlus('ppc.RevisaoPlanoDisciplina', verbose_name='Revisão do Plano de Disciplina', null=False, blank=False)
    texto = models.TextField(verbose_name='Texto', null=False, blank=False)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Servidor', null=False)
    data_criacao = models.DateTimeFieldPlus(auto_now_add=True)
    ativo = models.BooleanField('Ativo', default=True)
    automatico = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Comentário do plano de disciplina'
        verbose_name_plural = 'Comentários nos planos de disciplinas'

    @classmethod
    def adicionar(cls, revisao, vinculo, texto, automatico=False):
        cls.objects.create(revisao=revisao, vinculo=vinculo, texto=texto, automatico=automatico)

    def pode_desconsiderar_comentario(self, vinculo):
        return self.ativo and vinculo == self.vinculo

    def desconsiderar_comentario(self):
        self.ativo = False
        self.save()

    def pode_remover_comentario(self, user):
        ultimo_comentario_da_revisao = ComentarioRevisaoPlanoDisciplina.objects.filter(revisao=self.revisao).order_by('data_criacao').last()
        eh_ultimo_comentario = self == ultimo_comentario_da_revisao
        return eh_ultimo_comentario and (user == self.vinculo.user)

    def remover_comentario(self, user):
        self.delete()
        ComentarioRevisaoPlanoDisciplina.adicionar(self.revisao, self.vinculo, 'excluiu um comentário', automatico=True)
        mensagem = f'O último comentário da revisão #{self.revisao.numero_revisao} foi excluído pelo {user}.'
        self.revisao.plano_disciplina.notificar(mensagem=mensagem, notificar_elaboradores=True, notificar_avaliadores=True)


class SecaoPlanoDisciplina(LogModel):
    plano_disciplina = models.ForeignKeyPlus('ppc.PlanoDisciplina', verbose_name='Plano de disciplina', null=False, blank=True)
    modelo_secao_plano_disciplina = models.ForeignKeyPlus(
        'ppc.ModeloSecaoPlanoDisciplina', verbose_name='Modelo de seção da plano de disciplina', null=False, blank=False
    )
    texto = models.TextField('Texto', default='', blank=False)
    versao_ead = models.BooleanField('Versão EAD', default=False)

    class Meta:
        verbose_name = 'Seção de plano de disciplina'
        verbose_name_plural = 'Seções de planos de disciplinas'
        ordering = [
            'modelo_secao_plano_disciplina__ordem_exibicao',
        ]

    def get_titulo(self):
        return self.modelo_secao_plano_disciplina.titulo

    def get_ordem_exibicao(self):
        return self.modelo_secao_plano_disciplina.ordem_exibicao


class MovimentacaoPlanoDisciplina(LogModel):
    plano_disciplina = models.ForeignKeyPlus('ppc.PlanoDisciplina', verbose_name='Plano de disciplina', null=False, blank=False)
    data = models.DateTimeFieldPlus('Data', auto_now=True)
    usuario = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Usuário', null=True, blank=False)
    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=PlanoDisciplina.SITUACAO_CHOICES)
    acao = models.CharFieldPlus(verbose_name='Ação', null=True, blank=True)

    class Meta:
        verbose_name = 'Movimentação de PPC'
        verbose_name_plural = 'Movimentações de PPC'

    @staticmethod
    def registrar_movimentacao(user, plano_disciplina, acao=None):
        registro = MovimentacaoPlanoDisciplina()
        registro.plano_disciplina = plano_disciplina
        registro.usuario = user and user.get_vinculo()
        registro.situacao = plano_disciplina.situacao
        registro.acao = acao
        registro.save()


class RevisorPlanoDisciplina(LogModel):
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Revisor de plano de disciplina'
        verbose_name_plural = 'Revisores de plano de disciplina'

    def clean(self):
        if RevisorPlanoDisciplina.objects.filter(servidor_id=self.servidor_id).exclude(id=self.id).exists():
            raise ValidationError('Este servidor já está cadastrado como um revisor de plano de disciplina.')
        super().clean()


class PlanoDisciplinaPPC(LogModel):
    SEARCH_FIELDS = ['plano_disciplina__nome_disciplina', 'plano_disciplina__id']

    TIPO_REGULAR = 1
    TIPO_TRABALHO_CONCLUSAO_CURSO = 4
    TIPO_ATIVIDADE_EXTENSAO = 5
    TIPO_CHOICES = [
        [TIPO_REGULAR, 'Regular'],
        [TIPO_TRABALHO_CONCLUSAO_CURSO, 'Trabalho de Conclusão de Curso'],
        [TIPO_ATIVIDADE_EXTENSAO, 'Atividade de Extensão'],
    ]

    matriz_ppc = models.ForeignKeyPlus('ppc.MatrizPPC', verbose_name='Matriz do PPC', null=True, blank=False)
    plano_disciplina = models.ForeignKeyPlus('ppc.PlanoDisciplina', verbose_name='Plano de disciplina', null=False, blank=False)
    plano_disciplinappc_associado = models.ForeignKeyPlus(
        'ppc.PlanoDisciplinaPPC',
        verbose_name='Plano de disciplina associado',
        related_name='planodisciplinappcassociado_set',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text='Informe, se houver, o plano de disciplina associado. A carga horária desse plano não será contabilizada para o docente da disciplina principal.',
    )

    # dados para componente curricular
    periodo_oferta = models.PositiveIntegerField('Período de oferta', null=True, blank=True)
    optativo = models.BooleanField('Optativo', default=False)
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, null=True)
    quantidade_etapas = models.PositiveIntegerField('Quantidade de etapas', choices=ComponenteCurricular.QTD_AVALIACOES_CHOICES, null=True)
    ch_teorica = models.PositiveIntegerField('Teórica', help_text='Carga horária em hora/relógio', default=0)
    ch_extensao = models.PositiveIntegerField('Extensão', help_text='Carga horária em hora/relógio', default=0)
    segundo_semestre = models.BooleanField(
        'Segundo semestre',
        default=False,
        help_text='Marque essa opção caso a disciplina seja configurada com 2 etapas e seja ofertada no segundo semestre de um curso anual.',
    )

    qtd_aulas_1s = models.PositiveIntegerField(
        'Quantidade de aulas semanais no 1° semestre',
        help_text='Informe a quantidade de aulas semanais do 1° semestre caso a quantidade de aulas do 1° semestre seja diferente da quantidade de aulas do 2° semestre.',
        null=True,
        blank=True,
    )
    qtd_aulas_ead = models.PositiveIntegerFieldPlus('Quantidade de horas/aulas EAD', default=0)
    qtd_aulas_sincronas_ead = models.PositiveIntegerFieldPlus('Quantidade de horas/aulas síncronas EAD', default=0)
    qtd_aulas_assincronas_ead = models.PositiveIntegerFieldPlus('Quantidade de horas/aulas assíncrona EAD', default=0)

    pode_fechar_pendencia = models.BooleanField('Pode fechar com pendência', default=False)

    pre_requisitos = models.ManyToManyFieldPlus(
        'ppc.PlanoDisciplinaPPC', verbose_name='Pré-requisitos', related_name='planodisciplinappc_prerequisitos_set', blank=True
    )
    co_requisitos = models.ManyToManyFieldPlus(
        'ppc.PlanoDisciplinaPPC', verbose_name='Co-requisitos', related_name='planodisciplinappc_corequisitos_set', blank=True
    )

    justificativa_correcao = models.TextField('Justificativa', null=True, blank=False)

    # projeto integrador
    modalidade_projetointegrador = models.ForeignKeyPlus(
        'edu.ModalidadePraticaProfissional',
        verbose_name='Modalidade de prática profissional',
        null=True,
        blank=True,
        help_text='Informe a modalidade de projeto integrador a ser associada a este plano de disciplina.',
    )
    planos_associados_projetointegrador = models.ManyToManyFieldPlus(
        'ppc.PlanoDisciplinaPPC', verbose_name='Planos associados', related_name='planos_associados_projetointegrador_set', blank=True
    )

    class Meta:
        verbose_name = 'Plano de disciplina de curso'
        verbose_name_plural = 'Planos de disciplinas de cursos'
        ordering = ('periodo_oferta', 'segundo_semestre', 'optativo')

    def __str__(self):
        periodo = self.periodo_oferta and f' ({self.periodo_oferta}° período)' or ''
        return f'{self.plano_disciplina}{periodo} - {self.matriz_ppc}'

    def clean(self):
        # Matriz precisa ter quantidade de períodos informada
        if self.matriz_ppc.quantidade_periodos is None:
            raise ValidationError('Informe a quantidade de períodos da matriz antes de iniciar o cadastro do plano de disciplina.')

        if not hasattr(self, 'plano_disciplina'):
            raise ValidationError('O plano de disciplina não foi vinculado.')
        if self.ch_teorica + self.ch_extensao != self.plano_disciplina.ch_disciplina:
            raise ValidationError(f'A soma das cargas horárias teórica e de extensão deve ser igual a {self.plano_disciplina.ch_disciplina}.')

        # EAD
        if self.qtd_aulas_ead > 0:
            if not self.matriz_ppc.ppc.diretriz.possui_ch_ead():
                raise ValidationError('A diretriz deste plano de disciplina não permite carga horária EAD.')
            hr_ead = self.get_hora_relogio_ead()
            if hr_ead > self.plano_disciplina.ch_disciplina:
                raise ValidationError(
                    f'A quantidade de horas/aulas EAD em hora-relógio ({hr_ead}h) não pode ser maior do que a carga horária do plano de disciplina ({self.plano_disciplina.ch_disciplina}h).'
                )

        nucleo_id = self.plano_disciplina.nucleo_id

        # verifica se permite optativa no período
        if self.optativo and self.periodo_oferta and self.matriz_ppc.ppc.ch_cc_optativo > 0:
            if not self.matriz_ppc.get_configuracao_optativas(nucleo_id).filter(periodo=self.periodo_oferta).exists():
                raise ValidationError(
                    f'O período de oferta deste plano de disciplina ({self.periodo_oferta}° período) não permite a inclusão de disciplinas optativas para este núcleo.'
                )

        try:
            nd = NucleoDiretriz.objects.get(nucleo_id=nucleo_id, diretriz_id=self.matriz_ppc.ppc.diretriz_id)
        except NucleoDiretriz.DoesNotExist:
            raise ValidationError(f'O núcleo deste plano de disciplina ("{self.plano_disciplina.nucleo}") não pertence à diretriz deste PPC.')
        ch_planos = self.matriz_ppc.get_ch_informada_matriz(nucleo_id)
        if not self.id and not self.optativo:
            ch_planos += self.plano_disciplina.ch_disciplina
        ch_max = nd.get_ch_max_pd(self.matriz_ppc.ppc.solicitacao.eixo_tecnologico_id)
        if ch_planos > ch_max:
            raise ValidationError(
                f'A inclusão deste plano de disciplina excede a carga horária total definida na diretriz para este núcleo ({ch_max}h).'
            )
        # quantidade de créditos precisa ser inteiro
        if self.is_qtd_creditos_decimal():
            raise ValidationError(
                f'Este plano de disciplina gera uma quantidade de créditos incompatível com a diretriz deste PPC. A CH deve ser múltiplo de {self.matriz_ppc.ppc.diretriz.equivalencia_hr_credito}.'
            )

        # ch hora aula precisa ser inteiro
        if self.is_ch_hora_aula_decimal():
            raise ValidationError('Este plano de disciplina gera uma carga horária de aula incompatível com a diretriz deste PPC.')

        # configuração de diretriz do componente gerado pelo plano de disciplina diferente da diretriz atual
        if self.plano_disciplina.componente and (
            self.get_hora_aula() != self.plano_disciplina.componente.ch_hora_aula
            or self.get_qtd_creditos() != self.plano_disciplina.componente.ch_qtd_creditos
        ):
            raise ValidationError(
                'Este plano de disciplina possui componente gerado com configuração de hora aula ou quantidade de créditos diferentes da diretriz deste PPC.'
            )

        # curso anual com plano anual tem 4 etapas
        configuracao_anual = self.plano_disciplina.periodicidade == PlanoDisciplina.PERIODICIDADE_ANUAL and self.matriz_ppc.ppc.is_curso_anual()
        if configuracao_anual and self.quantidade_etapas != 4:
            raise ValidationError('Este plano de disciplina exige que a quantidade de etapas seja igual a 4.')

        # curso anual ou semestral com plano semestral tem 2 etapas
        configuracao_semestral = (
            self.plano_disciplina.periodicidade == PlanoDisciplina.PERIODICIDADE_SEMESTRAL and self.matriz_ppc.ppc.is_curso_anual()
        )
        if configuracao_semestral and self.quantidade_etapas != 2:
            raise ValidationError('Este plano de disciplina exige que a quantidade de etapas seja igual a 2.')

        # curso semestral não pode ter mais de 2 etapas
        if self.matriz_ppc.ppc.is_curso_semestral() and self.quantidade_etapas and self.quantidade_etapas > 2:
            raise ValidationError('A quantidade de etapas deste plano de disciplina não pode ser maior do que 2.')

        if self.periodo_oferta == 0:
            raise ValidationError('O período de oferta não pode ser zero.')

        # periodo do plano não pode exceder quantidade de perídos da diretriz
        if self.periodo_oferta and self.periodo_oferta > self.matriz_ppc.quantidade_periodos:
            raise ValidationError(f'O período de oferta deste plano não pode ser maior que {self.matriz_ppc.quantidade_periodos}.')

        if self.segundo_semestre and not self.matriz_ppc.ppc.is_curso_anual():
            raise ValidationError(
                'A periodicidade do PPC desta matriz não permite que este plano de disciplina seja configurado como segundo semestre.'
            )

        if self.quantidade_etapas == 4:
            # plano de disciplina semestral não pode ter 4 etapas
            if self.segundo_semestre:
                raise ValidationError('O plano de disciplina com 4 etapas não pode ser configurado como segundo semestre.')

            # quantidade de aulas no semestre não pode ser maior que a quantidade total de créditos no período.
            if self.qtd_aulas_1s and self.qtd_aulas_1s > self.get_qtd_creditos() - 1:
                raise ValidationError(f'A quantidade de aulas semanais no 1° semestre não pode exceder {self.get_qtd_creditos() - 1} aulas.')

            if self.qtd_aulas_1s == 0:
                raise ValidationError('A quantidade de aulas semanais no 1° semestre não pode ser inferior a 1 aula.')

        # apenas plano de 4 etapas pode ter configuração de aulas no 1° semestre
        if self.quantidade_etapas != 4 and self.qtd_aulas_1s:
            raise ValidationError(
                f'A quantidade de etapas deste plano de disciplina ({self.quantidade_etapas}) não permite o preenchimento da quantidade de aulas no 1° semestre.'
            )

        # obrigatório precisa ter período informado
        if self.id and not self.optativo and not self.periodo_oferta:
            raise ValidationError('O período de oferta precisa ser informado para plano de disciplina que não é optativo.')

        if self.optativo and self.ch_extensao > 0:
            raise ValidationError('Um plano de disciplina optativo não pode ter carga horária de extensão.')

        if self.tipo == PlanoDisciplinaPPC.TIPO_ATIVIDADE_EXTENSAO and self.ch_teorica > 0:
            raise ValidationError('Para disciplinas do tipo Atividade de Extensão, toda a carga horária deve ser informada no campo Extensão.')

        if self.tipo == PlanoDisciplinaPPC.TIPO_TRABALHO_CONCLUSAO_CURSO and self.ch_extensao > 0:
            raise ValidationError('Disciplinas do tipo TCC não devem ter carga horária de Extensão informada.')

        if self.tipo == PlanoDisciplinaPPC.TIPO_REGULAR and self.ch_teorica == 0:
            raise ValidationError('Disciplinas do tipo Regular não devem ter carga horária teórica igual a zero.')

        # plano associado
        if self.plano_disciplinappc_associado:
            if self.plano_disciplinappc_associado.periodo_oferta != self.periodo_oferta:
                raise ValidationError(f'O plano de disciplina associado não pode ter período de oferta diferente do plano {self}.')
            if self.plano_disciplinappc_associado_id == self.id:
                raise ValidationError('O plano de disciplina associado não pode ser associado a ele mesmo.')
            if PlanoDisciplinaPPC.objects.filter(plano_disciplinappc_associado_id=self.plano_disciplinappc_associado_id).exclude(id=self.id).exists():
                raise ValidationError('O plano de disciplina associado informado já está associado a outro plano.')
            if plano := self.get_plano_disciplinappc_principal():
                raise ValidationError(
                    f'Este plano de disciplina não pode ter um plano de disciplina associado pois ele já é associado em outro plano ({plano.plano_disciplina}).'
                )

        # projeto integrador:
        if self.modalidade_projetointegrador_id:
            modalidade = (
                self.matriz_ppc.get_modalidades_praticaprofissionalppc_projeto_integrador()
                .filter(modalidade_pratica_profissional_id=self.modalidade_projetointegrador_id)
                .first()
            )
            if modalidade is None:
                raise ValidationError(
                    'A modalidade de prática profissional informada não está entre as modalidades de projeto integrador configuradas para esta matriz.'
                )
            if self.periodo_oferta is None or self.periodo_oferta < modalidade.periodo_inicial:
                raise ValidationError(
                    f'A modalidade de prática profissional informada exige que o período de oferta deste plano de disciplina seja maior ou igual a {modalidade.periodo_inicial}.'
                )
            if modalidade.periodo_final and self.periodo_oferta > modalidade.periodo_final:
                raise ValidationError(
                    f'A modalidade de prática profissional informada exige que o período de oferta deste plano de disciplina seja menor ou igual a {modalidade.periodo_final}.'
                )
            if (
                self.matriz_ppc.get_planos_disciplinappc()
                .filter(modalidade_projetointegrador_id=self.modalidade_projetointegrador_id)
                .exclude(id=self.id)
                .exists()
            ):
                raise ValidationError('A modalidade de prática profissional informada foi associada a outro plano de diciplina desta matriz.')
            if self.pk and self.planos_associados_projetointegrador.filter(pk=self.pk).exists():
                raise ValidationError(
                    'O plano de disciplina não pode ser associado a si mesmo como plano de disciplina associado do projeto integrador.'
                )

        return super().clean()

    def delete(self, *args, **kwargs):
        if (
            self.plano_disciplina.is_elaboracao()
            and self.plano_disciplina.ppc_criacao_id == self.matriz_ppc.ppc_id
            and not PlanoDisciplinaPPC.objects.filter(plano_disciplina_id=self.plano_disciplina_id).exclude(id=self.id).exists()
        ):
            self.plano_disciplina.delete()
        super().delete(*args, **kwargs)

    def can_change(self, user):
        return (
            self.matriz_ppc.ppc.situacao == ProjetoPedagogicoCurso.EM_ELABORACAO
            and self.matriz_ppc.situacao_matriz == MatrizPPC.MATRIZ_EM_ELABORACAO
            and ElaboradorPPC.is_membro(user, self.matriz_ppc.ppc_id, permissao=ElaboradorPPC.PERMISSAO_EDICAO)
        )

    def can_delete(self, user):
        if not user.has_perm('ppc.delete_planodisciplinappc'):
            return False
        if not self.can_change(user):
            return False
        return not PlanoDisciplinaPPC.objects.filter(plano_disciplinappc_associado_id=self.id).exists()

    def get_absolute_url(self):
        return f'/ppc/planodisciplinappc/{self.pk}/visualizar/'

    def get_natureza_disciplina_status(self):
        status_class = 'info'
        texto = 'Obrigatório'
        if self.optativo:
            status_class = 'alert'
            texto = 'Optativo'

        return mark_safe(f'<span class="status status-{status_class}">{texto}</span>')

    def get_qtd_creditos(self):
        if self.plano_disciplina.desconsiderar_qtd_credito:
            return 0
        return int(self.plano_disciplina.ch_disciplina / self.matriz_ppc.ppc.diretriz.equivalencia_hr_credito)

    def get_hora_aula(self):
        return int(self.plano_disciplina.ch_disciplina / self.matriz_ppc.ppc.diretriz.equivalencia_hr_ha)

    def get_hora_relogio(self):
        return self.plano_disciplina.ch_disciplina

    def get_hora_relogio_ead(self):
        return Decimal(self.qtd_aulas_ead * self.matriz_ppc.ppc.diretriz.equivalencia_hr_ha).quantize(Decimal('0.01'))

    def get_hora_relogio_ead_sincrona(self):
        return Decimal(self.qtd_aulas_sincronas_ead * self.matriz_ppc.ppc.diretriz.equivalencia_hr_ha).quantize(Decimal('0.01'))

    def get_hora_relogio_ead_assincrona(self):
        return Decimal(self.qtd_aulas_assincronas_ead * self.matriz_ppc.ppc.diretriz.equivalencia_hr_ha).quantize(Decimal('0.01'))

    def get_info_hora_relogio_ead(self):
        return f'{mask_number(self.get_hora_relogio_ead())}h ({mask_number(self.get_percentual_ead())}%) | {mask_number(self.get_hora_relogio_ead_sincrona())}h síncrono e {mask_number(self.get_hora_relogio_ead_assincrona())}h assíncrona'

    def get_percentual_ead(self):
        return Decimal(self.get_hora_relogio_ead() / self.plano_disciplina.ch_disciplina * 100).quantize(Decimal('0.01'))

    def get_qtd_aulas_1s(self):
        if self.plano_disciplina.desconsiderar_qtd_credito:
            return 0
        result = None
        if self.matriz_ppc.ppc.is_curso_anual():
            creditos = self.get_qtd_creditos()
            if self.quantidade_etapas == 4:
                if self.qtd_aulas_1s:
                    result = self.qtd_aulas_1s
                else:
                    if creditos % 2 == 0:
                        result = int(creditos / 2)
                    else:
                        result = int(creditos / 2) + 1
            elif self.quantidade_etapas == 2:
                result = self.segundo_semestre is False and creditos or None
        else:
            # cursos semestrais e livres
            result = self.get_qtd_creditos()
        return result

    def get_qtd_aulas_2s(self):
        if self.plano_disciplina.desconsiderar_qtd_credito:
            return 0
        result = None
        if self.matriz_ppc.ppc.is_curso_anual():
            creditos = self.get_qtd_creditos()
            if self.quantidade_etapas == 4 and self.qtd_aulas_1s:
                result = creditos - self.qtd_aulas_1s
            elif self.quantidade_etapas == 2:
                result = self.segundo_semestre and creditos or None
            else:
                result = int(creditos / 2)
        else:
            # cursos semestrais e livres
            result = 0

        return result

    def get_secoes_plano_disciplina_impressao(self):
        versao_ead = self.qtd_aulas_ead > 0
        return self.plano_disciplina.get_secoes_impressao(versao_ead)

    def get_periodicidade(self):
        periodicidade = '-'
        if self.quantidade_etapas == 4:
            periodicidade = 'Anual'
        elif self.quantidade_etapas == 2:
            periodicidade = 'Semestral'
        return periodicidade

    def get_plano_disciplinappc_principal(self):
        if self.id is None:
            return None
        return (
            PlanoDisciplinaPPC.objects.filter(plano_disciplinappc_associado_id=self.id)
            .select_related('plano_disciplina')
            .only('id', 'plano_disciplina__id', 'plano_disciplina__nome_disciplina', 'plano_disciplina__ch_disciplina')
            .first()
        )

    def get_ch_projeto_integrador(self):
        if self.modalidade_projetointegrador_id is None:
            return None
        result = (
            self.matriz_ppc.get_modalidades_praticaprofissionalppc_projeto_integrador()
            .filter(modalidade_pratica_profissional_id=self.modalidade_projetointegrador_id)
            .first()
            .only('ch_requerida')
            .first()
        )
        return result.ch_requerida if result else None

    def get_versoes_em_pomcs(self):
        result = []
        if 'pafc' in settings.INSTALLED_APPS and self.plano_disciplina.topico_especifico:
            for curso in self.matriz_ppc.cursos.all():
                if curso.ultimo_pafc_com_pomc:
                    id_componente = self.plano_disciplina.componente_id
                    id_matriz = self.matriz_ppc.matriz_id
                    plano_disciplina_pomc = curso.ultimo_pafc_com_pomc.get_plano_disciplina_pomc(id_componente, id_matriz)
                    if plano_disciplina_pomc:
                        nome_do_campus = plano_disciplina_pomc.plano_disciplina_modificado.pafc.get_nome_campus_normalizado()
                        result.append(
                            {
                                'id': plano_disciplina_pomc.id,
                                'descricao': f'Versão do {nome_do_campus}',
                            }
                        )
        return result

    def is_qtd_creditos_decimal(self):
        if self.plano_disciplina.desconsiderar_qtd_credito:
            return False
        result = Decimal(round(self.plano_disciplina.ch_disciplina / self.matriz_ppc.ppc.diretriz.equivalencia_hr_credito, 2)).quantize(
            Decimal('0.01')
        )
        return str(result).split('.')[1] != '00'

    def is_ch_hora_aula_decimal(self):
        if self.plano_disciplina.desconsiderar_qtd_credito:
            return False
        result = Decimal(round(self.plano_disciplina.ch_disciplina / self.matriz_ppc.ppc.diretriz.equivalencia_hr_ha, 2)).quantize(Decimal('0.01'))
        return str(result).split('.')[1] != '00'


class ModalidadePraticaProfissionalPPC(LogModel):
    SEARCH_FIELDS = [
        'modalidade_pratica_profissional',
    ]

    matriz_ppc = models.ForeignKeyPlus('ppc.MatrizPPC', verbose_name='Matriz de PPC', null=True, blank=False)

    modalidade_pratica_profissional = models.ForeignKeyPlus(
        'edu.ModalidadePraticaProfissional', verbose_name='Modalidade de prática profissional', null=False, blank=False
    )
    optativa = models.BooleanField('Optativa', default=False)
    periodo_inicial = models.PositiveIntegerFieldPlus('Período inicial', min_value=1, null=False, blank=False)
    periodo_final = models.PositiveIntegerFieldPlus('Período final', null=True, blank=True)
    ch_requerida = models.PositiveIntegerFieldPlus('Carga horária requerida', null=True, blank=True)
    nucleo = models.ForeignKeyPlus('edu.Nucleo', verbose_name='Núcleo', null=False, blank=False)
    exigido_diretriz = models.BooleanField('Exigido pela diretriz', default=False)

    class Meta:
        verbose_name = 'Modalidade de prática profissional do PPC'
        verbose_name_plural = 'Modalidades de prática profissional dos PPCs'

    def __str__(self):
        return f'{self.modalidade_pratica_profissional.nome} (período {self.get_periodo()})'

    def clean(self):
        if not self.optativa and self.ch_requerida:
            nd = NucleoDiretriz.objects.filter(nucleo_id=self.nucleo_id, diretriz_id=self.matriz_ppc.ppc.diretriz_id).first()
            ch_max_pratica = nd and nd.ch_max_pratica or 0
            ch_min_pratica_cadastrada = (
                sum(
                    self.matriz_ppc.get_modalidades_praticaprofissionalppc()
                    .exclude(id=self.id)
                    .exclude(optativa=True)
                    .exclude(ch_requerida__isnull=True)
                    .values_list('ch_requerida', flat=True)
                )
                + self.ch_requerida
            )

            if ch_min_pratica_cadastrada > ch_max_pratica:
                raise ValidationError(
                    f'A soma das cargas horárias para prática profissional ({ch_min_pratica_cadastrada}h) excede à carga horária máxima definida neste núcleo ({ch_max_pratica}h).'
                )

        if (
            self.matriz_ppc.get_modalidades_praticaprofissionalppc()
            .filter(modalidade_pratica_profissional_id=self.modalidade_pratica_profissional_id)
            .exclude(id=self.id)
            .exists()
        ):
            raise ValidationError('Esta modalidade já está associada a esta matriz.')
        return super().clean()

    def get_periodo(self):
        result = '-'
        if self.periodo_final is None:
            result = f'{self.periodo_inicial} a {self.matriz_ppc.quantidade_periodos}'
        elif self.periodo_final == self.periodo_inicial:
            result = self.periodo_inicial
        else:
            result = f'{self.periodo_inicial} a {self.periodo_final}'
        return result


class ComissaoPTDEM(LogModel):
    nome = models.CharFieldPlus('Nome', null=False, blank=False)
    servidores = models.ManyToManyFieldPlus('rh.Servidor', verbose_name='Servidores', blank=True)
    nucleos = models.ManyToManyFieldPlus('edu.Nucleo', verbose_name='Núcleos', blank=True)

    class Meta:
        verbose_name = 'Comissão de planos de disciplinas'
        verbose_name_plural = 'Comissões de planos de disciplinas'

    def get_absolute_url(self):
        return f'/ppc/comissaoptdem/{self.id}/'


class AdministradorTipoOferta(LogModel):
    tipo_oferta = models.ForeignKeyPlus('edu.Modalidade', verbose_name='Tipo de oferta', null=False, blank=False)
    servidores = models.ManyToManyFieldPlus('rh.Servidor', verbose_name='Servidores', blank=True)

    class Meta:
        verbose_name = 'Administrador de tipo de oferta'
        verbose_name_plural = 'Administradores de tipo de oferta'

    def __str__(self):
        return f'Administradores de {self.tipo_oferta}'

    def get_absolute_url(self):
        return f'/ppc/administradortipooferta/{self.id}/'

    @staticmethod
    def is_administrador(user, tipo_oferta_id=None):
        qs = AdministradorTipoOferta.objects.filter(servidores__matricula=user.username)
        if tipo_oferta_id:
            qs = qs.filter(tipo_oferta_id=tipo_oferta_id)
        return qs.exists()


class Camara(LogModel):
    SEARCH_FIELDS = [
        'nome',
    ]

    nome = models.CharFieldPlus('Nome', null=False, blank=False, default='Câmara de ')
    ativo = models.BooleanField('Ativo', default=True)
    tipos_oferta = models.ManyToManyFieldPlus('edu.Modalidade', verbose_name='Tipos de oferta', blank=True)
    coordenador = models.ForeignKeyPlus('rh.Servidor', verbose_name='Coordenador', null=False, blank=False, related_name='camara_coordenador_set')
    secretario = models.ForeignKeyPlus('rh.Servidor', verbose_name='Secretário', null=False, blank=False, related_name='camara_secretario_set')

    class Meta:
        verbose_name = 'Câmara'
        verbose_name_plural = 'Câmaras'

    def __str__(self):
        return self.nome


class ProReitoria(LogModel):
    SEARCH_FIELDS = ['setor__nome', 'setor__sigla']

    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor', null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=True)
    tipos_oferta = models.ManyToManyFieldPlus('edu.Modalidade', verbose_name='Tipos de oferta', blank=True)

    class Meta:
        verbose_name = 'Pró-Reitoria'
        verbose_name_plural = 'Pró-Reitorias'

    def __str__(self):
        return f'{self.setor.nome} ({self.setor.sigla})'


class CertificacaoParcial(LogModel):
    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', null=False, blank=False)
    descricao = models.CharFieldPlus('Descrição', blank=False, null=False)
    modalidade_certificacao = models.ForeignKeyPlus('edu.Modalidade')
    titulacao_masculino = models.CharFieldPlus('Titulação (masculino)', blank=False, null=False)
    titulacao_feminino = models.CharFieldPlus('Titulação (feminino)', blank=False, null=False)
    ch_componentes_optativos = models.PositiveIntegerField(
        'CH de componentes optativos',
        help_text='Carga horária em Hora-Relógio. Informar 0 caso esta configuração não contenha componentes optativos.',
        default=0,
        blank=False,
        null=False,
    )

    class Meta:
        verbose_name = 'Certificação intermediária'
        verbose_name_plural = 'Certificações intermediárias'

    def get_carga_horaria_total(self):
        result = self.ch_componentes_optativos or 0
        result += sum(self.planodisciplinacertificacaoparcial_set.all().values_list('plano_disciplina__ch_disciplina', flat=True))
        return result


class PlanoDisciplinaCertificacaoParcial(LogModel):
    certificacao_parcial = models.ForeignKeyPlus('ppc.CertificacaoParcial', verbose_name='Certificação intermediária', blank=False, null=False)
    plano_disciplina = models.ForeignKeyPlus('ppc.PlanoDisciplina', verbose_name='Plano de disciplina', blank=False, null=False)

    class Meta:
        verbose_name = 'Plano de disciplina de certificação intermediária'
        verbose_name_plural = 'Planos de disciplinas de certificações intermediárias'

    def get_planodisciplinappc(self, matriz_id):
        return PlanoDisciplinaPPC.objects.filter(plano_disciplina_id=self.plano_disciplina_id, matriz_ppc__id=matriz_id).first()
