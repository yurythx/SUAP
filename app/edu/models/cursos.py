import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.aggregates import Count, Sum
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from djtools.utils import mask_ch_componente

from comum.models import Configuracao, Group, UsuarioGrupo, UsuarioGrupoSetor, User
from djtools.db import models
from djtools.utils import somar_dias
from edu.managers import (
    CursoCampusManager,
    FiltroDiretoriaManager,
    MatrizManager,
    MatrizCursoManager,
    MinicursoLocalsManager,
    MinicursoObjectsManager,
)
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES, GrupoAtuacao, Modalidade, SituacaoMatricula
from edu.models.diretorias import Diretoria
from edu.models.logs import LogModel
from rh.models import UnidadeOrganizacional
from djtools.middleware.threadlocals import get_ano_letivo


class Componente(LogModel):
    SEARCH_FIELDS = ['descricao', 'descricao_historico', 'sigla', 'sigla_qacademico', 'abreviatura']

    descricao = models.CharFieldPlus(verbose_name='Descrição', width=500)
    descricao_historico = models.CharFieldPlus(verbose_name='Descrição no Diploma e Histórico', width=500)
    tipo = models.ForeignKeyPlus('edu.TipoComponente', verbose_name='Tipo do Componente', on_delete=models.CASCADE)
    sigla = models.CharFieldPlus(max_length=255, unique=True)
    diretoria = models.ForeignKeyPlus('edu.Diretoria', on_delete=models.CASCADE)
    nivel_ensino = models.ForeignKeyPlus('edu.NivelEnsino', verbose_name='Nível de ensino', on_delete=models.CASCADE)
    ativo = models.BooleanField('Está ativo', default=True)

    ch_hora_relogio = models.PositiveIntegerField('Hora/relógio')
    ch_hora_aula = models.PositiveIntegerField('Hora/aula')
    ch_qtd_creditos = models.PositiveIntegerField('Qtd. de créditos')

    observacao = models.TextField('Observação', blank=True, default='')
    sigla_qacademico = models.CharFieldPlus('Sigla do Q-Acadêmico', null=True)
    abreviatura = models.CharFieldPlus('Abreviatura', max_length=10, null=True)

    grupo_atuacao = models.ForeignKey('edu.grupoatuacao', verbose_name='Grupo de Atuação', on_delete=models.CASCADE, null=True, blank=True)

    sequencial = models.PositiveIntegerField('Sequencial', null=True, blank=False)

    class Meta:
        verbose_name = 'Componente'
        verbose_name_plural = 'Componentes'
        ordering = ('descricao',)

    def __str__(self):
        return '{} - {} - {} [{} h/{} Aulas] {}'.format(
            self.sigla,
            self.descricao,
            str(self.nivel_ensino),
            self.get_ch_hora_relogio_str(),
            self.get_ch_hora_aula(),
            (self.observacao and '- {}'.format(self.observacao or '')),
        )

    @classmethod
    def get_ids_componentes_equivalentes(cls, componente_id, matriz_id):
        from edu.models.equivalencias import EquivalenciaComponente

        ids_componentes_equivalentes = []
        # disciplinas diretamente equivalentes
        ids_componentes_equivalentes.extend(
            EquivalenciaComponente.objects.filter(
                simples=True, ativa=True, aprovada=True, componentes=componente_id, equivalenciacomponentematriz__matriz_origem=matriz_id
            ).values_list('equivalentes', flat=True)
        )
        # disciplinas indiretamente equivalentes
        ids_componentes_equivalentes.extend(
            EquivalenciaComponente.objects.filter(
                simples=True,
                ativa=True,
                aprovada=True,
                equivalentes=componente_id,
                equivalenciacomponentematriz__matriz_destino=matriz_id,
            ).values_list('componentes', flat=True)
        )
        return ids_componentes_equivalentes

    def get_fator_conversao_hora_aula(self):
        return self.ch_hora_relogio and (Decimal(self.get_ch_hora_aula()) / Decimal(self.get_ch_hora_relogio())) or Decimal(0)

    def get_absolute_url(self):
        return f'/edu/componente/{self.pk:d}/'

    def clean(self):
        if hasattr(self, 'nivel_ensino'):
            qs = Componente.objects.filter(
                descricao=self.descricao,
                ch_hora_relogio=self.ch_hora_relogio,
                ch_hora_aula=self.ch_hora_aula,
                nivel_ensino=self.nivel_ensino,
                observacao=self.observacao,
            ).exclude(id=self.id)
            if qs.exists():
                raise ValidationError(
                    f'Já existe um componente ({qs[0].pk}) cadastrado com a mesma descrição, carga horária, nível de ensino e observação.'
                )
        if Componente.objects.filter(sigla__iexact=self.sigla).exclude(id=self.id).exists():
            raise ValidationError('A sigla do componente deve ser única.')

    def save(self, *args, **kwargs):
        alterou_tipo_componente = False
        if self.id:
            old = Componente.objects.get(id=self.id)
            if old.tipo_id != self.tipo_id:
                alterou_tipo_componente = True

            if self.sequencial is None and self.sigla:
                self.sequencial = int(self.sigla.split('.')[1])

        if (not self.id and not self.sigla) or alterou_tipo_componente:
            qs = Componente.objects.filter(tipo_id=self.tipo_id).exclude(id=self.id)
            if qs.exists():
                prefixo, sufixo = qs.order_by('-sequencial').first().sigla.split('.')
                sequencial = int(sufixo) + 1
                proxima_sigla = prefixo + '.' + str(sequencial).zfill(4)
                self.sigla = proxima_sigla
                self.sequencial = sequencial
            else:
                self.sigla = str(self.tipo) + '.0001'
                self.sequencial = 1

        super().save(*args, **kwargs)

    def get_planodisciplina(self):
        result = None
        if 'ppc' in settings.INSTALLED_APPS:
            from ppc.models import PlanoDisciplina

            result = PlanoDisciplina.objects.filter(componente_id=self.id).first()
        return result

    def get_ch_hora_relogio(self):
        return mask_ch_componente(self.ch_hora_relogio)

    def get_ch_hora_relogio_str(self):
        return str(self.get_ch_hora_relogio()).replace('.', ',')

    def get_ch_hora_aula(self):
        if settings.COMPONENTE_CH_DECIMAL:
            return round(self.ch_hora_aula / 100)
        return self.ch_hora_aula


class ComponenteCurricularQuerySet(models.QuerySet):
    def com_extensao(self):
        return self.filter(ComponenteCurricular.get_filtro_com_extensao())


class ComponenteCurricular(LogModel):
    SEARCH_FIELDS = ['componente__sigla', 'componente__descricao']

    objects = models.Manager.from_queryset(ComponenteCurricularQuerySet)()

    TIPO_REGULAR = 1
    TIPO_SEMINARIO = 2
    TIPO_PRATICA_PROFISSIONAL = 3
    TIPO_TRABALHO_CONCLUSAO_CURSO = 4
    TIPO_ATIVIDADE_EXTENSAO = 5
    TIPO_PRATICA_COMO_COMPONENTE = 6
    TIPO_VISITA_TECNICA = 7
    TIPO_EXTRA_CURRICULAR = 8
    TIPO_CHOICES = [
        [TIPO_REGULAR, 'Regular'],
        [TIPO_SEMINARIO, 'Seminário'],
        [TIPO_PRATICA_PROFISSIONAL, 'Prática Profissional'],
        [TIPO_TRABALHO_CONCLUSAO_CURSO, 'Trabalho de Conclusão de Curso'],
        [TIPO_ATIVIDADE_EXTENSAO, 'Atividade de Extensão'],
        [TIPO_PRATICA_COMO_COMPONENTE, 'Prática como Componente Curricular'],
    ]

    ESTAGIO_DOCENTE_1 = 1
    ESTAGIO_DOCENTE_2 = 2
    ESTAGIO_DOCENTE_3 = 3
    ESTAGIO_DOCENTE_4 = 4
    ESTAGIO_DOCENTE_MATRIZ_ANTERIOR = 5

    TIPO_ESTAGIO_DOCENTE_CHOICES = [
        [ESTAGIO_DOCENTE_1, 'Estágio Docente I'],
        [ESTAGIO_DOCENTE_2, 'Estágio Docente II'],
        [ESTAGIO_DOCENTE_3, 'Estágio Docente III'],
        [ESTAGIO_DOCENTE_4, 'Estágio Docente IV'],
        [ESTAGIO_DOCENTE_MATRIZ_ANTERIOR, 'Estágio Docente de Matriz Anterior'],
    ]

    MODULO_1 = 1
    MODULO_2 = 2
    MODULO_3 = 3
    MODULO_4 = 4
    MODULO_5 = 5
    MODULO_6 = 6
    MODULO_7 = 7
    MODULO_8 = 8
    MODULO_9 = 9
    MODULO_10 = 10
    MODULO_11 = 11
    MODULO_12 = 12

    TIPO_MODULO_CHOICES = [
        [MODULO_1, 'Módulo I'],
        [MODULO_2, 'Módulo II'],
        [MODULO_3, 'Módulo III'],
        [MODULO_4, 'Módulo IV'],
        [MODULO_5, 'Módulo V'],
        [MODULO_6, 'Módulo VI'],
        [MODULO_7, 'Módulo VII'],
        [MODULO_8, 'Módulo VIII'],
        [MODULO_9, 'Módulo IX'],
        [MODULO_10, 'Módulo X'],
        [MODULO_11, 'Módulo XI'],
        [MODULO_12, 'Módulo XII'],
    ]

    QTD_AVALIACOES_CHOICES = [[0, 'Zero'], [1, 'Uma'], [2, 'Duas'], [3, 'Três'], [4, 'Quatro']]

    # Dados gerais
    matriz = models.ForeignKeyPlus('edu.Matriz')
    componente = models.ForeignKeyPlus('edu.Componente')
    classificacao_complementar = models.ForeignKeyPlus(
        'edu.ClassificacaoComplementarComponenteCurricular', null=True, blank=True, verbose_name='Classificação Complementar'
    )
    periodo_letivo = models.PositiveIntegerField('Período', null=True, blank=True)
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES)
    optativo = models.BooleanField(default=False)
    is_seminario_estagio_docente = models.BooleanField(
        'É um Seminário de Estágio Docente? (Ou Estágio Docente de Matriz Anterior)',
        default=False,
        help_text='Marcar caso este componente curricular seja um seminário de estágio docente.',
    )
    tipo_estagio_docente = models.PositiveIntegerField('Tipo de Estágio Docente', choices=TIPO_ESTAGIO_DOCENTE_CHOICES, null=True, blank=True)
    tipo_modulo = models.PositiveIntegerField('Tipo de Módulo', choices=TIPO_MODULO_CHOICES, null=True, blank=True)
    qtd_avaliacoes = models.PositiveIntegerField('Qtd. Avaliações', choices=QTD_AVALIACOES_CHOICES)
    nucleo = models.ForeignKeyPlus('edu.Nucleo', verbose_name='Núcleo', on_delete=models.CASCADE)
    # Carga horária
    ch_presencial = models.PositiveIntegerField('Teórica', help_text='Hora-Relógio')
    ch_pratica = models.PositiveIntegerField('Prática', help_text='Hora-Relógio')
    ch_extensao = models.PositiveIntegerField('Extensão', help_text='Hora-Relógio', default=0)
    ch_pcc = models.PositiveIntegerField('Prática como Componente Curricular', help_text='Hora-Relógio', default=0)
    ch_visita_tecnica = models.PositiveIntegerField('Visita Técnica/Aula de Campo', help_text='Hora-Relógio', default=0)

    percentual_maximo_ead = models.PositiveIntegerField(
        '% Máximo EAD', help_text='Percentual máximo de aulas que o professor pode registrar na modalidade EAD.', default=0
    )
    qtd_aulas_ead = models.PositiveIntegerFieldPlus(
        'Quantidade de horas/aulas EAD', default=0, help_text='Quantidade de aulas na modalidade EAD que será exigida no registro do diário.'
    )

    # Pré requisitos
    pre_requisitos = models.ManyToManyFieldPlus('edu.ComponenteCurricular', related_name='prerequisitos_set', blank=True)
    # Co-requisitos
    co_requisitos = models.ManyToManyFieldPlus('edu.ComponenteCurricular', related_name='corequisitos_set', blank=True)

    avaliacao_por_conceito = models.BooleanField(
        'Avaliação por Conceito',
        default=False,
        help_text='Marque essa opção para exibir a representação conceitual da nota ao invés do valor numérico.',
    )
    is_dinamico = models.BooleanField(
        'Descrição Dinâmica',
        default=False,
        help_text='Marque essa opção caso deseje que a descrição do componente possa ser complementada no diário.',
    )

    componente_curricular_associado = models.ForeignKeyPlus('edu.ComponenteCurricular', related_name='associados_set', null=True, blank=True)
    segundo_semestre = models.BooleanField(
        'Segundo Semestre', default=False, help_text='Marque essa opção caso a disciplina seja ofertada no segundo semestre.'
    )

    pode_fechar_pendencia = models.BooleanField('Pode Fechar com Pendência', default=False)
    ementa = models.TextField('Ementa', blank=True, null=True, default='')

    # distribuição da quantidade de créditos do componente curricular anual no semestre
    ch_semanal_1s = models.PositiveIntegerField('CH semanal no 1° semestre', null=True, blank=True)
    ch_semanal_2s = models.PositiveIntegerField('CH semanal no 2° semestre', null=True, blank=True)

    ch_projeto_integrador = models.PositiveIntegerField('Carga horária', null=True, blank=True)
    modalidade_pratica_profissional_projeto_integrador = models.ForeignKeyPlus(
        'edu.ModalidadePraticaProfissional', verbose_name='Modalidade de prática profissional associada', null=True, blank=True
    )
    componentes_associados_projeto_integrador = models.ManyToManyFieldPlus(
        'edu.componentecurricular', verbose_name='Disciplinas associadas', related_name='associados_pi_set', blank=True
    )

    class Meta:
        ordering = ('matriz', 'periodo_letivo', 'componente__descricao', 'tipo', 'nucleo')
        unique_together = ('matriz', 'componente')
        verbose_name = 'Componente Curricular'
        verbose_name_plural = 'Componentes Curriculares'

    def __str__(self):
        return f'{self.componente!s} [Matriz {self.matriz.pk}]'

    def clean(self):
        from edu.models import EstruturaCurso, MatrizCurso

        if self.matriz.is_regime_modular() and not self.tipo_modulo:
            raise ValidationError('A estrutura de curso desta matriz exige que seja informado o tipo de módulo do componente curricular.')

        if (
            self.tipo == ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO
            and self.qtd_avaliacoes != 1
            and not self.matriz.permite_etapas_componente_tcc
        ):
            raise ValidationError('Componentes de TCC devem possuir 1 avaliação.')

        if self.qtd_avaliacoes and self.qtd_avaliacoes > 0:
            if MatrizCurso.locals.filter(
                matriz=self.matriz, matriz__estrutura__criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_FREQUENCIA
            ).exists():
                raise ValidationError(
                    'Componentes com avaliação não podem ser adicionados a matrizes já vinculadas a cursos cuja estrutura de avaliação seja por frequência.'
                )

        if hasattr(self, 'componente') and self.ch_presencial >= 0 and self.ch_pratica >= 0:
            if self.ch_presencial + self.ch_pratica + self.ch_extensao + self.ch_pcc + self.ch_visita_tecnica != self.componente.ch_hora_relogio:
                raise ValidationError(f'A soma das cargas horárias deve ser {self.componente.get_ch_hora_relogio()}')
        if self.periodo_letivo and self.periodo_letivo > self.matriz.qtd_periodos_letivos:
            raise ValidationError('O período letivo excede a quantidade de períodos da matriz.')

        if self.is_seminario_estagio_docente and not self.tipo_estagio_docente:
            raise ValidationError(
                {
                    'tipo_estagio_docente': 'Este componente curricular foi marcado como de Seminário de Estágio Docente, neste caso o preenchimento do Tipo de Estágio Docente é obrigatório.'
                }
            )

        if not self.is_seminario_estagio_docente and self.tipo_estagio_docente:
            raise ValidationError(
                {
                    'tipo_estagio_docente': 'Este componente curricular não foi marcado como de Seminário de Estágio Docente, neste caso não deve ser preenchido Tipo de Estágio Docente.'
                }
            )

    def get_professores(self, ano_letivo=None):
        from edu.models import Diario, Professor

        ano_letivo = ano_letivo or get_ano_letivo()
        pks = (
            Diario.objects.filter(componente_curricular=self, calendario_academico__ano_letivo=ano_letivo)
            .values_list('professordiario__professor', flat=True)
            .order_by('professordiario__professor')
            .distinct()
        )
        return Professor.objects.filter(pk__in=pks)

    def get_cursos(self, ano_letivo=None):
        ano_letivo = ano_letivo or get_ano_letivo()
        pks = (
            Matriz.objects.filter(turma__calendario_academico__ano_letivo=ano_letivo)
            .filter(pk=self.matriz_id)
            .values_list('matrizcurso__curso_campus_id', flat=True)
            .order_by('matrizcurso__curso_campus_id')
            .distinct()
        )
        return CursoCampus.objects.filter(pk__in=pks)

    def get_ch_presencial(self):
        return mask_ch_componente(self.ch_presencial)

    def get_ch_pratica(self):
        return mask_ch_componente(self.ch_pratica)

    def get_ch_extensao(self, incluir_associado: bool = False) -> int | Decimal:
        ch = self.ch_extensao or 0
        if incluir_associado:
            cc_associado = self.componente_curricular_associado
            if cc_associado and cc_associado.tipo != ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO:
                ch += cc_associado.ch_extensao or 0
        return mask_ch_componente(ch)

    def get_ch_extensao_exigida(self) -> int | Decimal:
        return self.get_ch_extensao(incluir_associado=True)

    def get_ch_extensao_a_registrar(self) -> int:
        ch = self.componente.ch_hora_relogio if self.tipo == ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO else (self.ch_extensao or 0)
        cc_associado = self.componente_curricular_associado
        if cc_associado:
            ch += (
                cc_associado.componente.ch_hora_relogio
                if cc_associado.tipo == ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO
                else (cc_associado.ch_extensao or 0)
            )
        return ch

    def tem_ch_extensao_exigida(self) -> bool:
        return self.get_ch_extensao_exigida() > 0 and self.tipo != self.TIPO_ATIVIDADE_EXTENSAO

    @classmethod
    def get_filtro_com_extensao(cls, prefix: str = '') -> Q:
        """Retorna o filtro Q para componentes com CH de extensão exigida (parcial).

        Exclui componentes que são 100% atividade de extensão e inclui componentes
        com ch_extensao > 0 própria ou no associado (desde que o associado não seja
        TIPO_ATIVIDADE_EXTENSAO).
        """
        p = f'{prefix}__' if prefix else ''
        return (
            Q(**{f'{p}ch_extensao__gt': 0})
            | (
                Q(**{f'{p}componente_curricular_associado__ch_extensao__gt': 0})
                & ~Q(**{f'{p}componente_curricular_associado__tipo': cls.TIPO_ATIVIDADE_EXTENSAO})
            )
        ) & ~Q(**{f'{p}tipo': cls.TIPO_ATIVIDADE_EXTENSAO})

    def get_ch_pcc(self):
        return mask_ch_componente(self.ch_pcc)

    def get_ch_visita_tecnica(self):
        return mask_ch_componente(self.ch_visita_tecnica)

    def get_carga_horaria_total(self):
        return self.get_ch_pratica() + self.get_ch_presencial()

    def get_ch_qtd_creditos_nucleo(self):
        return sum(
            ComponenteCurricular.objects.filter(matriz=self.matriz, nucleo=self.nucleo, periodo_letivo=self.periodo_letivo).values_list(
                'componente__ch_qtd_creditos', flat=True
            )
        )

    def is_projeto_final(self):
        return self.tipo == self.TIPO_TRABALHO_CONCLUSAO_CURSO or self.tipo == self.TIPO_PRATICA_PROFISSIONAL

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        self.matriz.verificar_inconsistencias()
        self.matriz.save()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

        self.matriz.verificar_inconsistencias()
        self.matriz.save()

    def can_delete(self, user):
        return user.has_perm('edu.delete_componentecurricular') and self.matriz.pode_ser_editada(user)

    def get_grupo_componente_historico(self, grupos_componentes):
        componentes = None
        if self.tipo == ComponenteCurricular.TIPO_REGULAR:
            componentes = grupos_componentes.get('Componentes Curriculares', [])
        elif self.tipo == ComponenteCurricular.TIPO_SEMINARIO:
            componentes = grupos_componentes.get('Seminários', [])
        elif self.tipo == ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL:
            componentes = grupos_componentes.get('Prática Profissional', [])
        elif self.tipo == ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO:
            componentes = grupos_componentes.get('Componentes Curriculares', [])
        elif self.tipo == ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO:
            componentes = grupos_componentes.get('Atividade de Extensão', [])
        elif self.tipo == ComponenteCurricular.TIPO_PRATICA_COMO_COMPONENTE:
            componentes = grupos_componentes.get('Prática como Componente Curricular', [])
        elif self.tipo == ComponenteCurricular.TIPO_VISITA_TECNICA:
            componentes = grupos_componentes.get('Visita Técnica / Aula da Campo', [])
        elif self.tipo == ComponenteCurricular.TIPO_EXTRA_CURRICULAR:
            componentes = grupos_componentes.get('Componentes Extracurriculares', [])
        return componentes

    def get_pre_requisitos(self, requisitos=None, recursivo=False):
        if requisitos is None:
            requisitos = []
        if len(requisitos) < 50:  # evitar loop infinito já que se trata de uma função recursiva
            for pre_requisito in self.pre_requisitos.all():
                if pre_requisito.componente.pk not in requisitos:
                    requisitos.append(pre_requisito.componente.pk)
                if recursivo:
                    pre_requisito.get_pre_requisitos(requisitos)
        return requisitos

    def get_corequisitos(self):
        requisitos = []
        for corequisito in self.co_requisitos.all():
            requisitos.append(corequisito.componente.pk)
        return requisitos

    def is_semestral(self):
        return self.qtd_avaliacoes == 2

    def get_periodo_letivo(self):
        return 0 if self.periodo_letivo is None else self.periodo_letivo

    def get_periodo_oferta(self) -> str:
        if self.periodo_letivo:
            return f'{self.periodo_letivo}º Período'
        if self.tipo_modulo:
            return str(self.get_modulo())
        if self.optativo:
            return 'Optativa'
        return 'Sem período'

    def get_modulo(self):
        result = '-'
        if self.tipo_modulo:
            result = RotuloModulo.objects.filter(matriz_id=self.matriz_id, tipo_modulo=self.tipo_modulo).first() or self.get_tipo_modulo_display()
        return result

    def get_ch_semanal(self, semestre):
        if semestre is None:
            return self.componente.ch_qtd_creditos if self.ch_semanal_1s is None else self.ch_semanal_1s
        elif semestre == 1:
            return self.ch_semanal_1s or 0
        return self.ch_semanal_2s or 0

    def get_plano_disciplina_ppc(self):
        result = None
        matrizppc = self.matriz.get_matrizppc()
        if matrizppc:
            result = matrizppc.planodisciplinappc_set.filter(plano_disciplina__componente_id=self.componente_id).first()
        return result

    def get_plano_disciplina_pomc(self, curso):
        result = None
        if curso and curso.ultimo_pafc_com_pomc:
            result = curso.ultimo_pafc_com_pomc.get_plano_disciplina_pomc(self.componente_id, self.matriz_id)
        return result

    def possui_ch_ead(self):
        return self.percentual_maximo_ead > 0 or self.qtd_aulas_ead > 0


class EstruturaCurso(LogModel):
    TIPO_AVALIACAO_CREDITO = 1
    TIPO_AVALIACAO_SERIADO = 2
    TIPO_AVALIACAO_FIC = 3
    TIPO_AVALIACAO_MODULAR = 4
    TIPO_AVALIACAO_CHOICES = [
        [TIPO_AVALIACAO_CREDITO, 'Crédito'],
        [TIPO_AVALIACAO_SERIADO, 'Seriado'],
        [TIPO_AVALIACAO_FIC, 'FIC'],
        [TIPO_AVALIACAO_MODULAR, 'Modular'],
    ]

    CRITERIO_AVALIACAO_NOTA = 1
    CRITERIO_AVALIACAO_FREQUENCIA = 2
    CRITERIO_AVALIACAO_CONCEITO = 3
    CRITERIO_AVALIACAO_CHOICES = [
        [CRITERIO_AVALIACAO_NOTA, 'Nota'],
        [CRITERIO_AVALIACAO_FREQUENCIA, 'Frequência'],
        [CRITERIO_AVALIACAO_CONCEITO, 'Conceito'],
    ]

    IRA_ARITMETICA_NOTAS_FINAIS = 1
    IRA_PONDERADA_POR_CH = 2
    IRA_CHOICES = [
        [IRA_ARITMETICA_NOTAS_FINAIS, 'Média aritmética das Notas Finais'],
        [IRA_PONDERADA_POR_CH, 'Média dos componentes pela carga horária dos componentes'],
    ]

    MEDIA_FINAL_ARITMETICA = 1
    MEDIA_FINAL_PONDERADA = 2
    MEDIA_FINAL_CHOICES = [
        [MEDIA_FINAL_ARITMETICA, 'Média aritmética das etapas'],
        [MEDIA_FINAL_PONDERADA, 'Média ponderada por pesos'],
    ]

    # Dados gerais
    id = models.AutoField('Código', primary_key=True)
    descricao = models.CharFieldPlus('Descrição', width=500)
    ativo = models.BooleanField('Está Ativa', default=True)

    # Aproveitamento de Disciplinas
    percentual_max_aproveitamento = models.PositiveIntegerField(
        'Percentual Máximo de Aproveitamento',
        help_text='Percentual (%) máximo de carga horária aproveitada/certificada em relação a carga horária das disciplinas na matriz. Informe 0 (zero) caso esse valor seja indeterminado.',
        null=True,
        blank=True,
        default=0,
    )
    formas_ingresso_ignoradas_aproveitamento = models.ManyToManyFieldPlus(
        'edu.FormaIngresso',
        verbose_name='Ignorar Formas de Ingresso',
        help_text='Formas de ingressos que não serão contabilizadas no cálculo de carga horária aproveitada.',
        blank=True,
    )
    permite_registro_mobilidade_academica = models.BooleanField(
        'Permite o Registro de Mobilidade Acadêmica',
        default=False,
        help_text='Permite o registro de componentes cursados em outras instituições/universidades no histórico de aluno (Mobilidade Acadêmica Nacional/Internacional).',
    )

    numero_max_certificacoes = models.PositiveIntegerField(
        'Número Máximo de Certificações por Período',
        help_text='Número máximo de certificação de conhecimento em disciplinas no mesmo período da matriz. Informe 0 (zero) caso esse valor seja indeterminado.',
        null=True,
        default=0,
    )
    media_certificacao_conhecimento = models.NotaField(
        'Média para Certificação',
        help_text='Média para certificação de conhecimento. Informe 0 (zero) para utilizar o mesmo valor informado na média para aprovação sem prova final.',
        null=True,
        default=0,
    )
    quantidade_max_creditos_aproveitamento = models.PositiveIntegerField(
        'Quantidade Máxima de Créditos para Aproveitamento',
        help_text='Quantidade máxima de créditos aproveitados/certificados. Informe 0 (zero) caso esse valor seja indeterminado.',
        null=True,
        blank=True,
        default=8,
    )

    # Critérios de Apuração de Resultados por Período
    # fic
    proitec = models.BooleanField('Proitec', help_text='Marque esta opção caso esta estrutura se destine a cursos Proitec.', default=False)
    tipo_avaliacao = models.PositiveIntegerField('Tipo de Avaliação', choices=TIPO_AVALIACAO_CHOICES)
    # seriado
    limite_reprovacao = models.PositiveIntegerField(
        'Número máximo de reprovações para aprovação por dependência',
        help_text='Quantidade máxima de reprovações em disciplinas no período que permite os alunos cursarem a próxima série.',
        null=True,
        blank=True,
    )
    reprova_todas_disciplinas = models.BooleanField(
        'Reprovação total',
        help_text='Marque esta opção para que o aluno reprovado no período ou módulo precise refazer todos os componentes curriculares, inclusive aqueles em que foi aprovado.',
        default=False,
    )

    # modular
    componente_sem_periodo = models.BooleanField(
        'Somente componentes sem período',
        help_text='Marque esta opção para que a matriz não permita componentes curriculares com período definido. Nesse caso, todos os componentes deverão ser optativos e sem vínculo a um período específico.',
        default=False,
    )

    # crédito
    qtd_minima_disciplinas = models.PositiveIntegerField(
        'Número mínimo de disciplinas por período',
        help_text='Quantidade mínima de matrículas em disciplinas por período letivo.',
        null=True,
        blank=True,
    )
    numero_disciplinas_superior_periodo = models.PositiveIntegerField(
        'Número máximo de disciplinas extras por período',
        help_text='Número máximo de matrículas em disciplinas a mais no período em relação ao número de disciplinas daquele período definido na matriz.',
        null=True,
        blank=True,
    )

    qtd_max_periodos_subsequentes = models.PositiveIntegerField(
        'Número máximo de períodos subsequentes para matrícula em disciplina',
        help_text='Quantidade máxima de períodos subsequentes ao período de referência na qual os alunos podem se matricular em disciplinas.',
        null=True,
        blank=True,
    )
    numero_max_cancelamento_disciplina = models.PositiveIntegerField(
        'Número máximo de cancelamentos de disciplinas',
        help_text='Número máximo de cancelamento de disciplinas ao longo do curso.',
        null=True,
        blank=True,
    )

    ch_minima_disciplinas = models.PositiveIntegerField(
        'Carga horária mínima por período',
        help_text='Carga horária mínima de matrícula em disciplinas por período letivo.',
        null=True,
        blank=True,
    )

    ch_maxima_disciplinas = models.PositiveIntegerField(
        'Carga horária máxima por período',
        help_text='Carga horária máxima de matrícula em disciplinas por período letivo.',
        null=True,
        blank=True,
    )

    # Critérios de Avaliação por Disciplinas
    criterio_avaliacao = models.PositiveIntegerField('Critério de Avaliação', choices=CRITERIO_AVALIACAO_CHOICES)
    media_aprovacao_sem_prova_final = models.NotaField('Média para passar sem prova final', null=True, blank=True)
    media_evitar_reprovacao_direta = models.NotaField('Média para não reprovar direto', null=True, blank=True)
    media_aprovacao_avaliacao_final = models.NotaField('Média para aprovação após avaliação final', null=True, blank=True)

    conceito_minimo_aprovacao = models.CharField('Conceito mínimo para aprovação', null=True, blank=True, max_length=1)

    # Critérios de Apuração de Frequência
    percentual_frequencia = models.PositiveIntegerField(
        'Percentual Mínimo de Frequência',
        help_text='Percentual (%) mínimo de frequência para que os alunos não reprovem no período ou na disciplina.',
        default=90,
    )
    reprovacao_por_falta_disciplina = models.BooleanField(
        'Reprovação por Disciplina',
        help_text='Marque essa opção caso o controle da frequência seja feita por disciplina e não por módulo/período/série.',
        default=False,
    )
    limitar_ch_por_tipo_aula = models.BooleanField(
        'Limitar carga horária por tipo de aula',
        help_text='Marque essa opção caso a carga horária de aulas definida na vinculação dos componentes às matrizes deva ser utilizada como limite na contabilização das cargas-horárias das aulas registradas no diário pelo professor.',
        default=False,
    )

    exibe_frequencia_global = models.BooleanField(
        'Exibir frequência global',
        default=False,
        help_text='Marque esta opção para exibir no histórico do aluno a frequência global do período letivo ao invés da frequência da disciplina.',
    )

    # Coeficiente de rendimento(IRA)
    ira = models.PositiveIntegerField('Forma de Cálculo (I.R.A)', choices=IRA_CHOICES, default=1)

    # Fechamento de período
    permite_fechamento_com_pendencia = models.BooleanField(
        'Permitir fechamento com pendência',
        default=False,
        help_text='Habilita a possibilidade de fechar o período letivo do aluno mesmo havendo pendências em algum diário.',
    )

    # Critérios de Jubilamento
    qtd_periodos_conclusao = models.PositiveIntegerField(
        'Número Máximo de Matrículas em Períodos',
        help_text='Quantidade máxima de matrículas em períodos letivos que os alunos podem se matricular até concluir o curso. Informe 0 (zero) caso esse valor seja indeterminado.',
        default=0,
    )
    fator_acrescimo_periodo_letivo = models.DecimalFieldPlus(
        'Fator de Acréscimo de Matrículas em Períodos',
        help_text='Fator (número decimal) que será multiplicado pela quantidade de período da matriz para calcular se o aluno terá tempo hábil para concluir o curso. Ex: 1,0 para cursos de graduação ou integrado EJA e 1,5 para os demais cursos. Informe 0 (zero) caso esse valor seja indeterminado.',
        default=0,
    )
    qtd_max_reprovacoes_periodo = models.PositiveIntegerField(
        'Número Máximo de Reprovações no Mesmo Período',
        help_text='Quantidade máxima de reprovações que os alunos podem ter no mesmo período da matriz. Informe 0 (zero) caso esse valor seja indeterminado.',
        null=True,
        default=0,
    )
    qtd_max_reprovacoes_disciplina = models.PositiveIntegerField(
        'Número Máximo de Reprovações na Mesma Disciplina',
        help_text='Qtd. máxima de reprovações que os alunos podem ter na mesma disciplina. Informe 0 (zero) caso esse valor seja indeterminado.',
        null=True,
        default=0,
    )

    # Critérios de trancamento voluntário
    qtd_trancamento_voluntario = models.PositiveIntegerField(
        'Número máximo de trancamentos voluntários',
        help_text='Quantidade máxima de trancamentos de forma voluntária que os alunos podem realizar durante todo o curso.',
        blank=True,
        null=True,
        default=2,
    )

    exige_periodo_ingresso_integralizado = models.BooleanField(
        'Exige integralização do período de ingresso',
        help_text='Marque essa opção para permitir o trancamento voluntário somente se o aluno tiver concluído todas as disciplinas do seu período de ingresso.',
        default=True,
    )

    # Comportamento do Diário
    pode_entregar_etapa_sem_aula = models.BooleanField(
        'Entregar etapa sem aula',
        default=False,
        help_text='Marque essa opção caso seja permitido a entrega de etapa de diário sem registro de aula lançado para a etapa.',
    )
    pode_lancar_nota_fora_do_prazo = models.BooleanField(
        'Lançar nota fora do prazo',
        default=False,
        help_text='Marque essa opção caso seja permitido que o professor de diário compartilhado lance nota em data diferente do período de posse da etapa pelo professor.',
    )
    pode_lancar_aula_fora_do_prazo = models.BooleanField(
        'Lançar Aula/Falta Fora do Prazo',
        default=False,
        help_text='Marque essa opção caso seja permitido que o professor registre aula e faltas em data diferente do período da etapa definida no calendário acadêmico.',
    )
    permite_recuperacao_etapa = models.BooleanField(
        'Permite recuperação por etapa',
        default=False,
        help_text='Marque essa opção caso seja permitido a realização de recuperação dentro da etapa para os alunos que não atingirem a média necessária para aprovação da etapa.',
    )
    calculo_media_final = models.PositiveIntegerField('Forma de cálculo da média final', choices=MEDIA_FINAL_CHOICES, default=MEDIA_FINAL_PONDERADA)

    plano_estudo = models.BooleanField(
        'Permite Plano de Estudo',
        help_text='Marque essa opção caso os alunos necessitem solicitar dispensa/planejamento de plano de estudo durante a renovação da matrícula caso tenham ultrapassado o tempo de conclusão mínimo do curso.',
        default=False,
    )

    # Critérios relacionados a matrícula
    numero_min_alunos_diario = models.IntegerField(
        'Número Mínimo de Alunos em Diários',
        null=True,
        blank=True,
        help_text='Preencha essa opção caso haja um limite mínimo do número de alunos que devem estar matriculados nos diários.',
    )
    numero_max_alunos_especiais = models.IntegerField(
        'Número Máximo de Alunos Especiais',
        null=True,
        blank=True,
        help_text='Preencha essa opção apenas caso seja necessário limitar o número de alunos especiais em cursos de pós-graduação.',
    )
    requer_declaracao_para_cancelamento_matricula = models.BooleanField(
        'Requer Declaração para Cancelamento de Matrícula',
        default=False,
        help_text='Marque essa opção caso seja necessário a apresentação de uma declaração reconhecida em cartório para a realização do cancelamento voluntário no curso.',
    )

    # Entrega de Etapa do Diário
    exige_plano_ensino_submetido = models.BooleanField(
        'Requer submissão de plano de ensino',
        default=False,
        help_text='Exige a submissão do plano de ensino para liberar a entrega das etapas do diário.',
    )

    class Meta:
        verbose_name = 'Estrutura de Curso'
        verbose_name_plural = 'Estruturas de Curso'

    def get_absolute_url(self):
        return f'/edu/estruturacurso/{self.pk:d}/'

    def clean(self):
        if self.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_SERIADO:
            if self.limite_reprovacao is None:
                raise ValidationError('O limite de reprovações deve ser informado.')
        if self.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_NOTA:
            if self.media_aprovacao_sem_prova_final is None:
                raise ValidationError('A média para passar sem prova final deve ser informada.')
            if self.media_evitar_reprovacao_direta is None:
                raise ValidationError('A média para não reprovar direto deve ser informada.')
            if self.media_aprovacao_avaliacao_final is None:
                raise ValidationError('A média para aprovação após avaliação final deve ser informada.')
        if self.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_FREQUENCIA and self.pk:
            if MatrizCurso.locals.filter(matriz__estrutura=self, matriz__componentecurricular__qtd_avaliacoes__gt=0).exists():
                raise ValidationError(
                    'Estruturas associadas a cursos já vinculados a matrizes contendo componentes com avaliações não podem ter como critério de avaliacão a frequência.'
                )
        if self.is_lancamento_conceito():
            if self.conceito_minimo_aprovacao is None:
                raise ValidationError('Informe o conceito mínimo para aprovação do aluno.')
            if self.conceito_minimo_aprovacao and not settings.REPRESENTACAO_CONCEITUAL:
                raise ValidationError(
                    'Configuração da representação conceitual não encontrada. Por favor, entre em contato com o setor de desenvolvimento do SUAP.'
                )
            if self.conceito_minimo_aprovacao and self.conceito_minimo_aprovacao not in settings.REPRESENTACAO_CONCEITUAL:
                raise ValidationError(f'O valor informado ({self.conceito_minimo_aprovacao}) como conceito mínimo para aprovação não é válido.')
        if not self.media_certificacao_conhecimento and not self.is_lancamento_conceito():
            self.media_certificacao_conhecimento = self.media_aprovacao_sem_prova_final

    def get_representacoesconceituais(self):
        return self.representacaoconceitual_set.all().order_by('descricao')

    def is_lancamento_conceito(self):
        return self.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_CONCEITO

    def get_nota_minima_aprovacao_conceito(self):
        if self.is_lancamento_conceito():
            return self.get_nota(self.conceito_minimo_aprovacao)
        else:
            # aluno de estrutura por nota matriculado em diário de estrutura por conceito
            return self.media_aprovacao_sem_prova_final

    def get_conceito(self, nota):
        if nota is None:
            return ''
        conceito = self.representacaoconceitual_set.filter(valor_minimo__lte=nota, valor_maximo__gte=nota).first()
        if conceito:
            return conceito.descricao
        else:
            return nota

    def get_nota(self, conceito):
        representacao = self.representacaoconceitual_set.filter(descricao=conceito).first()
        return representacao and representacao.valor_minimo

    def get_matrizes_ativas(self):
        return self.matriz_set.filter(data_fim__isnull=True)

    def get_matrizes_inativas(self):
        return self.matriz_set.filter(data_fim__isnull=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_lancamento_conceito():
            if not self.representacaoconceitual_set.exists():
                for chave in settings.REPRESENTACAO_CONCEITUAL:
                    representacao = RepresentacaoConceitual()
                    representacao.estrutura_curso = self
                    representacao.descricao = chave
                    representacao.valor_minimo = settings.REPRESENTACAO_CONCEITUAL[chave]
                    representacao.valor_maximo = settings.REPRESENTACAO_CONCEITUAL[chave]
                    representacao.save()

            nota = self.get_nota_minima_aprovacao_conceito()
            if self.media_certificacao_conhecimento != nota:
                # atribui nota de conceito mínimo para aprovação como média para certificação de conhecimento
                self.media_certificacao_conhecimento = nota
                self.save()


class Habilitacao(LogModel):
    descricao = models.CharFieldPlus('Descrição', width=500)

    class Meta:
        verbose_name = 'Habilitação'
        verbose_name_plural = 'Habilitações'

    def __str__(self):
        return self.descricao


class CursoCampus(LogModel):
    CARGA_HORARIA_BASE_MINICURSO = 20
    SEARCH_FIELDS = ['codigo', 'codigo_academico', 'descricao', 'descricao_historico']

    PERIODICIDADE_ANUAL = 1
    PERIODICIDADE_SEMESTRAL = 2
    PERIODICIDADE_LIVRE = 3
    PERIODICIDADE_CHOICES = [[PERIODICIDADE_ANUAL, 'Anual'], [PERIODICIDADE_SEMESTRAL, 'Semestral'], [PERIODICIDADE_LIVRE, 'Livre']]

    TIPO_INICIACAO_PRATICA_PROFISSIONAL = '1'
    TIPO_INICIACAO_PESQUISA = '2'
    TIPO_INICIACAO_EXTENSAO = '3'
    TIPO_INICIACAO_CHOICES = [
        [TIPO_INICIACAO_PESQUISA, 'Iniciação à Pesquisa'],
        [TIPO_INICIACAO_EXTENSAO, 'Iniciação à Extensão'],
        [TIPO_INICIACAO_PRATICA_PROFISSIONAL, 'Iniciação à Prática Profissional'],
    ]

    codigo_academico = models.IntegerField(verbose_name='Código no sistema legado', null=True)

    # Identificação
    id = models.AutoField(verbose_name='Código', primary_key=True)
    descricao = models.CharFieldPlus(verbose_name='Descrição', width=500)
    descricao_historico = models.CharFieldPlus(verbose_name='Descrição no Diploma e Histórico', width=500)
    codigo_censup = models.CharFieldPlus('Código CENSUP', default='', blank=True)
    codigo_emec = models.CharFieldPlus('Código e-MEC', default='', blank=True)
    codigo_sistec = models.CharFieldPlus(
        'Código SISTEC',
        default='',
        blank=True,
        help_text='Separar por ";" sem espaço caso exista mais de um código cadastrado no SISTEC para esse curso. Ex: 00001;00002',
    )
    codigo_educacenso = models.CharFieldPlus('Código EDUCACENSO', null=True, blank=True)
    ciencia_sem_fronteira = models.BooleanField(
        'Ciência sem Fronteiras', help_text='Prioritário para o programa Ciência sem Fronteiras?', default=False
    )
    formacao_de_professores = models.BooleanField(
        'Formação de Professores', help_text='Marque essa opção caso se trate de um curso de formação de professores', default=False
    )

    # Dados da funcionamento
    data_inicio = models.DateFieldPlus('Data de criação', null=True, help_text='Data de criação do curso.')
    data_funcionamento = models.DateFieldPlus('Data de funcionamento', null=True, blank=True, help_text='Data de início de funcionamento do curso.')
    ano_letivo = models.ForeignKeyPlus(
        'comum.Ano',
        verbose_name='Ano letivo',
        related_name='cursos_por_ano_letivo_set',
        null=True,
        on_delete=models.CASCADE,
        help_text='Ano letivo do início de funcionamento do curso.',
    )
    periodo_letivo = models.PositiveIntegerField(
        'Período letivo', null=True, choices=PERIODO_LETIVO_CHOICES, help_text='Período letivo do início de funcionamento do curso.'
    )
    ativo = models.BooleanField('Ativo', default=True)

    # Outros Dados
    data_fim = models.DateFieldPlus('Data de extinção', null=True, blank=True, help_text='Data de extinção do curso.')
    data_solicitacao_reconhecimento = models.DateFieldPlus('Data para solicitação de reconhecimento do curso', null=True, blank=True)
    data_limite_reconhecimento = models.DateFieldPlus('Data limite para solicitar reconhecimento do curso', null=True, blank=True)
    suspenso = models.BooleanField('Suspenso', default=False)
    em_extincao = models.BooleanField('Em extinção', default=False)
    extinto = models.BooleanField('Extinto', default=False)

    codigo = models.CharFieldPlus(verbose_name='Código', help_text='Código para composição de turmas e matrículas', unique=True)
    modalidade = models.ForeignKeyPlus('edu.Modalidade', null=True, verbose_name='Modalidade de Ensino', on_delete=models.CASCADE)
    plano_ensino = models.BooleanField(
        'Exige Plano de Ensino',
        help_text='Marque essa opção caso os professores necessitem informar o plano de ensino das disciplinas nos diários',
        default=False,
    )
    quantidade_vagas = models.PositiveIntegerField('Quantidade de vagas anuais autorizadas', null=True, blank=True)

    # cursos Licenciatura
    area = models.ForeignKeyPlus('edu.AreaCurso', null=True, verbose_name='Área de curso', blank=True, on_delete=models.CASCADE)
    coordenadores_estagio_docente = models.ManyToManyFieldPlus(
        'edu.Professor', verbose_name='Coordenadores de Estágio Docente', related_name='cursos_coordenacao_estagio_docente_set'
    )
    # cursos tecnológicos ou FIC
    eixo = models.ForeignKeyPlus('edu.EixoTecnologico', null=True, verbose_name='Eixo tecnológico', blank=True, on_delete=models.CASCADE)

    # cursos técnicos concomitantes e subsequentes
    curso_tecnico = models.ForeignKeyPlus('edu.CursoTecnico', null=True, verbose_name='Curso técnico', blank=True, on_delete=models.CASCADE)

    # cursos de pós-graduação
    area_capes = models.ForeignKeyPlus('edu.AreaCapes', null=True, verbose_name='Área Capes', blank=True, on_delete=models.CASCADE)

    area_curso_formacao_superior = models.ForeignKeyPlus(
        'edu.AreaCursoFormacaoSuperior', null=True, verbose_name='Área do curso de formação superior', blank=True, on_delete=models.CASCADE
    )

    exige_enade = models.BooleanField('Exige ENADE', default=False)
    justificativa_dispensa_ingressante = models.ForeignKeyPlus('edu.JustificativaDispensaEnade', null=True, blank=True)
    processamento_enade = models.BooleanField(
        'Processamento ENADE',
        default=True,
        help_text='Indica que este curso faz parte do processamento ENADE. Caso seja desmarcado, o curso não será considerado nas convocações do ENADE.',
    )

    periodicidade = models.PositiveIntegerField('Periodicidade', choices=PERIODICIDADE_CHOICES, null=True)
    exige_colacao_grau = models.BooleanField('Exige colação de grau', default=False)
    assinatura_digital = models.BooleanField('Certificado/Diploma Assinado via Certificado ICP-Brasil', default=False)
    emite_diploma = models.BooleanField('Certificado/Diploma Emitido pelo Campus', default=False)
    assinatura_eletronica = models.BooleanField('Certificado/Diploma Assinado via Certificado ICP-EDU', default=False)
    area_concentracao = models.ForeignKeyPlus(
        'edu.AreaConcentracao', verbose_name='Área de Concentração', null=True, blank=True, on_delete=models.CASCADE
    )
    programa = models.CharFieldPlus('Programa', blank=True, default='')
    diretoria = models.ForeignKeyPlus('edu.Diretoria', null=True, verbose_name='Diretoria', on_delete=models.CASCADE)
    extensao = models.BooleanField('Curso de Extensão?', default=False)
    coordenador = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True)
    numero_portaria_coordenador = models.CharFieldPlus(
        'Nº Portaria', null=True, blank=True, help_text='Número da portaria que nomeou o servidor como coordenador do curso.'
    )
    coordenador_2 = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Coordenador substituto', null=True, blank=True, related_name='cursocampus_vicecoordenador_set'
    )
    numero_portaria_coordenador_2 = models.CharFieldPlus(
        'Nº Portaria (coordenador substituto)',
        null=True,
        blank=True,
        help_text='Número da portaria que nomeou o servidor como coordenador substituto do curso.',
    )
    matrizes = models.ManyToManyFieldPlus('edu.Matriz', through='edu.MatrizCurso')
    mesmo_curso = models.ForeignKeyPlus(
        'edu.CursoCampus',
        verbose_name='Mesmo curso',
        null=True,
        blank=True,
        help_text='Indica que o curso possui outro cadastro no campus e bloqueia a edição de dados deste curso. Atenção! os dados deste curso serão sobrescritos pelos dados do curso indicado.',
    )

    # Titulo do certificado de conclusão
    titulo_certificado_masculino = models.CharFieldPlus('Masculino', blank=True, null=True)
    titulo_certificado_feminino = models.CharFieldPlus('Feminino', blank=True, null=True)

    # Atributo de Minicurso
    ppc = models.FileFieldPlus(upload_to='edu/ppc/', null=True, blank=True, verbose_name='PPC', default=None)
    ch_total = models.PositiveIntegerField('Carga Horária Total h/r', blank=True, null=True, default=None)
    ch_aula = models.PositiveIntegerField('Carga Horária Total h/a', blank=True, null=True, default=None)
    tipo_hora_aula = models.PositiveIntegerField('Tipo Hora Aula', blank=True, null=True, choices=settings.TIPO_HORA_AULA_CHOICES)
    resolucao_criacao = models.TextField('Documento de Criação', blank=True, null=True)

    fator_esforco_curso = models.DecimalField('Fator de Esforço de Curso (FEC)', blank=True, null=True, default=1, max_digits=4, decimal_places=2)

    autoinstrucional = models.BooleanField(verbose_name='Autoinstrucional', default=False)
    tipo_curso_autoinstrucional = models.CharFieldPlus(
        verbose_name='Tipo de curso autoinstrucional', null=True, blank=True, choices=TIPO_INICIACAO_CHOICES
    )

    objects = models.Manager()
    locals = CursoCampusManager()

    class Meta:
        verbose_name = 'Curso'
        verbose_name_plural = 'Cursos'
        ordering = ('-ativo',)
        app_label = 'edu'

    def __str__(self):
        codigo = self.codigo.replace('-', '')
        return '{} - {} ({})'.format(codigo, self.descricao, str(self.diretoria and self.diretoria.setor.uo.nome or '-'))

    def clean(self):
        if CursoCampus.objects.filter(codigo__iexact=self.codigo).exclude(id=self.id).exists():
            raise ValidationError('Já existe um curso com este mesmo código. O código do curso deve ser único.')
        if self.ativo and self.data_fim:
            raise ValidationError('Um curso ativo não pode ter data de fim')
        if self.is_minicurso():
            if not isinstance(self, Minicurso):
                if not self.pk:
                    raise ValidationError({'modalidade': 'A modalidade FIC- é exclusiva de Minicursos.'})
                if not self.ch_total or self.ch_total > 160:
                    raise ValidationError({'modalidade': 'Cursos regulares não podem ter a modalidade alterada para FIC-.'})
            if self.pk and self.matrizcurso_set.exists():
                raise ValidationError({'modalidade': 'Cursos da modalidade FIC- (Minicurso) não podem ter matrizes associadas.'})
        super().clean()

    def get_absolute_url(self) -> str:
        if self.is_minicurso():
            return f'/edu/minicurso/{self.pk}/'
        return f'/edu/cursocampus/{self.pk}/'

    def get_funcao_coordenador(self):
        if self.coordenador:
            return getattr(self.coordenador.relacionamento, 'funcao', None)
        return None

    def get_funcao_coordenador_2(self):
        if self.coordenador_2:
            return getattr(self.coordenador_2.relacionamento, 'funcao', None)
        return None

    def get_titulacao_coordenador(self):
        if self.coordenador:
            from edu.models import Professor

            professor = Professor.objects.filter(vinculo=self.coordenador).first()
            if professor:
                return professor.get_titulacao()
        return None

    def get_coordenadores_html(self, detalhado=True):
        html = []
        if self.coordenador:
            html.append('<dl>')
            html.append(f'<dt>Coordenador:</dt><dd>{self.coordenador}</dd>')
            if detalhado:
                html.append(f'<dt>Email:</dt><dd>{self.coordenador.email_notificacao}</dd>')
                if self.numero_portaria_coordenador:
                    html.append(f'<dt>Portaria:</dt><dd>{self.numero_portaria_coordenador}</dd>')
                funcao = self.get_funcao_coordenador()
                if funcao:
                    html.append(f'<dt>Função:</dt><dd>{funcao}</dd>')
            html.append('</dl>')
        if self.coordenador_2:
            if self.coordenador:
                html.append('<hr>')
            html.append('<dl>')
            html.append(f'<dt>Coordenador substituto:</dt><dd>{self.coordenador_2}</dd>')
            if detalhado:
                html.append(f'<dt>Email:</dt><dd>{self.coordenador_2.email_notificacao}</dd>')
                if self.numero_portaria_coordenador_2:
                    html.append(f'<dt>Portaria:</dt><dd>{self.numero_portaria_coordenador_2}</dd>')
                funcao = self.get_funcao_coordenador_2()
                if funcao:
                    html.append(f'<dt>Função:</dt><dd>{funcao}</dd>')
            html.append('</dl>')

        return mark_safe(''.join(html))

    def get_pafcs(self):
        result = []
        if 'pafc' in settings.INSTALLED_APPS:
            from pafc.models import PAFC

            result = PAFC.objects.filter(curso_id=self.pk, situacao=PAFC.FINALIZADO).order_by('data_aprovacao')
        return result

    @cached_property
    def ultimo_pafc_com_pomc(self):
        """Retorna o último PAFC que implementou POMC para o curso (ou None, se não houver)"""
        if 'pafc' in settings.INSTALLED_APPS:
            from pafc.models import PAFC

            return (
                self.pafc_set.filter(
                    Q(situacao=PAFC.FINALIZADO)
                    | Q(situacao=PAFC.APROVADO, curso_ja_ofertado_campus=False, curso__isnull=False)
                    | Q(situacao=PAFC.APROVADO, curso_ja_ofertado_campus=True, data_atualizacao_curso__isnull=False)
                )
                .filter(planos_disciplina_modificados__isnull=False)
                .order_by('-data_aprovacao')
                .first()
            )
        return None

    def get_matrizcurso(self, matriz_id):
        return MatrizCurso.objects.filter(curso_campus_id=self.id, matriz_id=matriz_id).first()

    def get_autorizacao(self):
        from edu.models.regulacao import AtoRegulatorioCurso

        qs = self.mesmo_curso and self.mesmo_curso.atoregulatoriocurso_set.all() or self.atoregulatoriocurso_set.all()
        if self.modalidade_id in [Modalidade.MESTRADO, Modalidade.DOUTORADO]:
            qs = qs.filter(tipo=AtoRegulatorioCurso.TIPO_CRIACAO_CURSO)
        else:
            qs = qs.filter(tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO)
        return qs.order_by('data').first()

    def get_adequacao(self):
        from edu.models.regulacao import AtoRegulatorioCurso

        qs = self.mesmo_curso and self.mesmo_curso.atoregulatoriocurso_set.all() or self.atoregulatoriocurso_set.all()
        return qs.filter(tipo=AtoRegulatorioCurso.TIPO_ADEQUACAO_PAFC).order_by('-data').first()

    def get_reconhecimento(self):
        from edu.models.regulacao import AtoRegulatorioCurso

        qs = self.mesmo_curso and self.mesmo_curso.atoregulatoriocurso_set.all() or self.atoregulatoriocurso_set.all()
        return qs.filter(tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO).order_by('data').first()

    def get_renovacao_reconhecimento(self):
        from edu.models.regulacao import AtoRegulatorioCurso

        qs = self.mesmo_curso and self.mesmo_curso.atoregulatoriocurso_set.all() or self.atoregulatoriocurso_set.all()
        return qs.filter(tipo=AtoRegulatorioCurso.TIPO_RENOVACAO).order_by('-data').first()

    def get_tramitacao_processo_emec(self):
        qs = self.mesmo_curso and self.mesmo_curso.tramitacaoprocessoemec_set.all() or self.tramitacaoprocessoemec_set.all()
        return qs.first()

    def processar_grupo_coordenadores(self):
        if self.coordenador:
            user = User.objects.get(id=self.coordenador.user_id)
            group = Group.objects.get(name='Coordenador de Curso')
            usuario_grupo = UsuarioGrupo.objects.get_or_create(user=user, group=group)[0]
            UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=self.diretoria.setor)
        if self.coordenador_2:
            user = User.objects.get(id=self.coordenador_2.user_id)
            group = Group.objects.get(name='Coordenador de Curso')
            usuario_grupo = UsuarioGrupo.objects.get_or_create(user=user, group=group)[0]
            UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=self.diretoria.setor)

    def replicar(self, diretoria, codigo='[REPLICADO]', coordenador=None, coordenador_2=None):
        matrizes = self.matrizes.all()
        self.id = None
        self.codigo_censup = ''
        self.codigo_emec = ''
        self.codigo_sistec = ''
        self.codigo_educacenso = None
        self.descricao = f'{self.descricao} [REPLICADO]'
        self.codigo = codigo
        self.diretoria = diretoria
        self.codigo_academico = None
        self.coordenador = coordenador
        self.coordenador_2 = coordenador_2
        self.clean()
        self.save()
        for matriz in matrizes:
            mc = MatrizCurso()
            mc.curso_campus = self
            mc.matriz = matriz
            mc.save()
        return self

    def save(self, *args, **kwargs):
        if self.is_minicurso():
            if not isinstance(self, Minicurso) and (not self.pk or not self.ch_total or self.ch_total > 160):
                raise ValidationError('A modalidade FIC- é exclusiva de Minicursos.')
            if self.pk and self.matrizcurso_set.exists():
                raise ValidationError('Cursos da modalidade FIC- (Minicurso) não podem ter matrizes associadas.')

        curso_campus = None
        if self.pk:
            curso_campus = CursoCampus.objects.get(pk=self.pk)

            if self.data_funcionamento and (self.data_solicitacao_reconhecimento is None or self.data_limite_reconhecimento is None):
                qtd_periodos_letivos = self.matrizcurso_set.order_by('matriz__data_inicio').values('matriz__qtd_periodos_letivos').first()
                metade_periodos = qtd_periodos_letivos and qtd_periodos_letivos['matriz__qtd_periodos_letivos'] / 2
                if metade_periodos:
                    if self.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
                        self.data_solicitacao_reconhecimento = somar_dias(self.data_funcionamento, metade_periodos * 365)
                        self.data_limite_reconhecimento = somar_dias(self.data_solicitacao_reconhecimento, metade_periodos * 365 // 2)
                    elif self.periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL:
                        self.data_solicitacao_reconhecimento = somar_dias(self.data_funcionamento, metade_periodos * 365 // 2)
                        self.data_limite_reconhecimento = somar_dias(self.data_solicitacao_reconhecimento, metade_periodos * 365 // 4)
        super().save(*args, **kwargs)

        if curso_campus:
            if curso_campus.coordenador_id and self.coordenador_id != curso_campus.coordenador_id:
                if (
                    not CursoCampus.objects.filter(Q(coordenador_id=curso_campus.coordenador_id) | Q(coordenador_2_id=curso_campus.coordenador_id))
                    .exclude(id=curso_campus.id)
                    .exists()
                ):
                    UsuarioGrupo.objects.filter(user=curso_campus.coordenador.user, group__name='Coordenador de Curso').delete()
            if curso_campus.coordenador_2_id and self.coordenador_2_id != curso_campus.coordenador_2_id:
                if (
                    not CursoCampus.objects.filter(
                        Q(coordenador_id=curso_campus.coordenador_2_id) | Q(coordenador_2_id=curso_campus.coordenador_2_id)
                    )
                    .exclude(id=curso_campus.id)
                    .exists()
                ):
                    UsuarioGrupo.objects.filter(user=curso_campus.coordenador_2.user, group__name='Coordenador de Curso').delete()

        for repetido in self.cursocampus_set.all():
            repetido.codigo_censup = self.codigo_censup
            repetido.codigo_emec = self.codigo_emec
            repetido.codigo_sistec = self.codigo_sistec
            repetido.codigo_educacenso = self.codigo_educacenso
            repetido.ciencia_sem_fronteira = self.ciencia_sem_fronteira
            repetido.formacao_de_professores = self.formacao_de_professores
            repetido.data_inicio = self.data_inicio
            repetido.data_funcionamento = self.data_funcionamento
            repetido.ano_letivo = self.ano_letivo
            repetido.periodo_letivo = self.periodo_letivo
            repetido.quantidade_vagas = self.quantidade_vagas
            repetido.ativo = self.ativo
            repetido.extinto = self.extinto
            repetido.em_extincao = self.em_extincao
            repetido.suspenso = self.suspenso
            repetido.area_id = self.area_id
            repetido.eixo_id = self.eixo_id
            repetido.area_capes_id = self.area_capes_id
            repetido.periodicidade = self.periodicidade

            if repetido.coordenador_id and self.coordenador_id != repetido.coordenador_id:
                UsuarioGrupo.objects.filter(user=repetido.coordenador.user, group__name='Coordenador de Curso').delete()
                repetido.coordenador_id = self.coordenador_id
                repetido.numero_portaria_coordenador = self.numero_portaria_coordenador

            if repetido.coordenador_2_id and self.coordenador_2_id != repetido.coordenador_2_id:
                UsuarioGrupo.objects.filter(user=repetido.coordenador_2.user, group__name='Coordenador de Curso').delete()
                repetido.coordenador_2_id = self.coordenador_2_id
                repetido.numero_portaria_coordenador_2 = self.numero_portaria_coordenador_2

            repetido.save()

    def is_anual(self):
        return self.periodicidade == CursoCampus.PERIODICIDADE_ANUAL

    def is_fic(self):
        return self.modalidade_id == Modalidade.FIC

    def is_minicurso(self) -> bool:
        return self.modalidade_id == Modalidade.FIC_MENOS

    def is_licenciatura(self):
        return self.modalidade_id in [Modalidade.LICENCIATURA, Modalidade.LICENCIATURA_DUPLA_HABILITACAO]

    def is_pos_graduacao(self):
        return self.modalidade_id in [Modalidade.MESTRADO, Modalidade.ESPECIALIZACAO, Modalidade.APERFEICOAMENTO, Modalidade.DOUTORADO]

    def is_coordenador(self, user):
        is_coordenador = self.coordenador and self.coordenador.user.username == user.username
        is_vice_coordenador = self.coordenador_2 and self.coordenador_2.user.username == user.username
        return is_coordenador or is_vice_coordenador

    def is_solicitacao_reconhecimento_pendente(self):
        hoje = datetime.date.today()
        return (
            self.is_reconhecimento_obrigatorio()
            and self.data_solicitacao_reconhecimento
            and self.data_solicitacao_reconhecimento <= hoje
            and self.data_limite_reconhecimento >= hoje
            and not self.possui_processoemec()
            and not self.possui_reconhecimento()
        )

    def is_solicitacao_reconhecimento_pendente_fora_do_prazo(self):
        hoje = datetime.date.today()
        return (
            self.is_reconhecimento_obrigatorio()
            and self.data_limite_reconhecimento
            and self.data_limite_reconhecimento < hoje
            and not self.possui_reconhecimento()
            and not self.possui_processoemec()
        )

    def is_autorizacao_pendente(self):
        from edu.models.regulacao import AtoRegulatorioCurso

        result = False
        if self.modalidade_id not in [Modalidade.MESTRADO, Modalidade.DOUTORADO]:
            result = not self.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO).exists()
        return result

    def is_criacao_pendente(self):
        from edu.models.regulacao import AtoRegulatorioCurso

        result = False
        if self.modalidade_id in [Modalidade.MESTRADO, Modalidade.DOUTORADO]:
            result = not self.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_CRIACAO_CURSO).exists()
        return result

    def is_reconhecimento_obrigatorio(self, incluir_pos=False):
        from edu.models.regulacao import AtoRegulatorioCurso

        result = self.modalidade_id in AtoRegulatorioCurso.MODALIDADE_EXIGE_RECONHECIMENTO
        if incluir_pos:
            result = result and self.modalidade_id in [Modalidade.MESTRADO, Modalidade.DOUTORADO]
        return result

    def possui_aluno_cursando(self):
        return self.aluno_set.filter(situacao__in=SituacaoMatricula.SITUACOES_CURSANDO).exists()

    def possui_reconhecimento(self):
        from edu.models.regulacao import AtoRegulatorioCurso

        return self.atoregulatoriocurso_set.filter(tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO).exists()

    def possui_processoemec(self):
        return self.tramitacaoprocessoemec_set.exists()

    def pode_ingressar_aluno(self):
        return self.ativo and not self.suspenso and not self.extinto and not self.em_extincao

    def pode_extinguir_curso(self):
        return self.em_extincao and not self.extinto and not self.possui_aluno_cursando()

    def pode_solicitar_reconhecimento(self, user):
        return (
            user.has_perm('edu.add_tramitacaoprocessoemec')
            and self.is_reconhecimento_obrigatorio()
            and not self.possui_processoemec()
            and not self.possui_reconhecimento()
        )

    def pode_emitir_diploma(self, return_message_error=False):
        erro = None
        if not (self.emite_diploma or self.assinatura_digital or self.assinatura_eletronica):
            erro = f'O curso {self} não está configurado para emissão de diploma.'

        if self.is_reconhecimento_obrigatorio(incluir_pos=True) and not self.possui_reconhecimento():
            if not self.possui_processoemec():
                erro = f'O curso {self} não possui ato regulatório de reconhecimento.'
            else:
                processo = self.tramitacaoprocessoemec_set.first()
                if processo.data_cadastro > self.data_limite_reconhecimento:
                    erro = f'O curso {self} não possui ato regulatório de reconhecimento e seu processo e-MEC de solicitação de reconhecimento foi iniciado após prazo limite para expedição de diploma.'
        pode_emitir_diploma = erro is None
        if return_message_error:
            return pode_emitir_diploma, erro
        else:
            return pode_emitir_diploma


class RepresentacaoConceitual(LogModel):
    estrutura_curso = models.ForeignKeyPlus('edu.EstruturaCurso')
    descricao = models.CharFieldPlus('Descrição')
    valor_minimo = models.NotaField('Valor Mínimo')
    valor_maximo = models.NotaField('Valor Máximo')

    class Meta:
        verbose_name = 'Representação Conceitual'
        verbose_name_plural = 'Representações Conceituais'


class EquivalenciaComponenteQAcademico(LogModel):
    q_academico = models.PositiveIntegerField('Código Q-Acadêmico')
    sigla = models.CharFieldPlus('Sigla')
    descricao = models.CharFieldPlus('Descrição', width=500)
    carga_horaria = models.PositiveIntegerField('Carga horária')
    componente = models.ForeignKeyPlus('edu.Componente', null=True)

    class Meta:
        verbose_name = 'Equivalência Q-Academico'
        verbose_name_plural = 'Equivalências Q-Academico'

    def __str__(self):
        return f'{self.sigla} - {self.descricao} ({self.carga_horaria}H)'


class Matriz(LogModel):
    SEARCH_FIELDS = ['id', 'descricao']

    objects = MatrizManager()
    locals = FiltroDiretoriaManager('matrizcurso__curso_campus__diretoria')

    # Dados gerais
    id = models.AutoField(verbose_name='Código', primary_key=True)
    descricao = models.CharFieldPlus(verbose_name='Descrição', width=500)
    ano_criacao = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Criação', on_delete=models.CASCADE)
    periodo_criacao = models.PositiveIntegerField('Período Criação', default=1, choices=PERIODO_LETIVO_CHOICES)
    ativo = models.BooleanField('Ativa', default=True)
    data_inicio = models.DateFieldPlus('Data de início')
    data_fim = models.DateFieldPlus('Data de fim', null=True, blank=True)
    ppp = models.FileFieldPlus(upload_to='edu/ppp/', null=True, blank=True, verbose_name='PPP')
    ppc = models.FileFieldPlus(upload_to='edu/ppc/', null=True, blank=True, verbose_name='PPC')
    qtd_periodos_letivos = models.PositiveIntegerField(verbose_name='Quantidade de Períodos Letivos', choices=[[x, x] for x in range(1, 13)])
    nivel_ensino = models.ForeignKeyPlus('edu.NivelEnsino', verbose_name='Nível de Ensino', null=True, on_delete=models.CASCADE)
    estrutura = models.ForeignKeyPlus('edu.EstruturaCurso', verbose_name='Estrutura de curso', null=True, on_delete=models.CASCADE)
    natureza_participacao = models.ForeignKeyPlus(
        'edu.NaturezaParticipacao', verbose_name='Natureza de participação', null=True, on_delete=models.CASCADE
    )

    # Carga horária
    ch_componentes_obrigatorios = models.PositiveIntegerField('Componentes obrigatórios', help_text='Hora-Relógio.')
    ch_componentes_optativos = models.PositiveIntegerField('Componentes optativos', help_text='Hora-Relógio.')
    ch_componentes_eletivos = models.PositiveIntegerField('Componentes eletivos', help_text='Hora-Relógio.')
    ch_seminarios = models.PositiveIntegerField('Seminários', help_text='Hora-Relógio.')
    ch_pratica_profissional = models.PositiveIntegerField('Prática Profissional', help_text='Hora-Relógio.')
    ch_atividades_complementares = models.PositiveIntegerField('Atividades complementares', help_text='Hora-Relógio.')
    ch_atividades_aprofundamento = models.PositiveIntegerField('Atividades Teórico-Práticas de Aprofundamento', help_text='Hora-Relógio.')
    ch_componentes_extensao = models.PositiveIntegerField(
        'Componentes de extensão', help_text='Hora-Relógio. Somente componentes integralmente de extensão (tipo Atividade de extensão).', default=0
    )
    ch_componentes_tcc = models.PositiveIntegerField('Trabalho de Conclusão de Curso', help_text='Hora-Relógio.')
    ch_pratica_como_componente = models.PositiveIntegerField('Prática como Componente Curricular', help_text='Hora-Relógio.')
    ch_visita_tecnica = models.PositiveIntegerField('Visita Técnica/Aula de Campo', help_text='Hora-Relógio.')

    ch_atividades_extensao = models.PositiveIntegerField('Carga horária total de atividades de extensão', help_text='Hora-Relógio.', default=0)
    ch_componentes_com_extensao = models.PositiveIntegerField(
        'Carga horária de extensão em outros componentes',
        help_text='Hora-Relógio. Componentes que possuem carga horária parcial destinada a atividades de extensão.',
        default=0,
    )

    # Projeto integrador
    ch_projeto_integrador = models.PositiveIntegerField('Carga horária', null=True, blank=True)

    # Componentes
    componentes = models.ManyToManyField('edu.Componente', through='edu.ComponenteCurricular')
    configuracao_atividade_academica = models.ForeignKeyPlus(
        'edu.ConfiguracaoAtividadeComplementar', null=True, blank=True, verbose_name='Configuração de AACC', on_delete=models.CASCADE
    )
    configuracao_atividade_aprofundamento = models.ForeignKeyPlus(
        'edu.ConfiguracaoAtividadeAprofundamento', null=True, blank=True, verbose_name='Configuração de ATPA', on_delete=models.CASCADE
    )
    configuracao_creditos_especiais = models.ForeignKeyPlus(
        'edu.ConfiguracaoCreditosEspeciais', null=True, blank=True, verbose_name='Configuração de Créditos Especiais', on_delete=models.CASCADE
    )
    # A matriz possui inconsistência?
    inconsistente = models.BooleanField(default=False)
    # Exige trabalho de conclusão de curso
    exige_tcc = models.BooleanField(
        'Exige TCC',
        help_text='Marque essa opção caso a apresentação de um trabalho de conclusão de curso seja um pré-requisito para a finalização do curso.',
        default=False,
    )
    permite_etapas_componente_tcc = models.BooleanField(
        'Permite componente de TCC com 2 ou mais etapas',
        default=False,
        help_text='Componentes do tipo TCC possuem apenas 1 etapa. Marque essa opção para permitir a vinculação de componentes de TCC com 2 ou mais etapas.',
    )

    observacao = models.TextField('Observação', null=True, blank=True)

    # Estágio
    exige_estagio = models.BooleanField(
        'Exige Estágio e Afins',
        help_text='Marque essa opção caso a realização de estágio seja um pré-requisito para a finalização do curso',
        default=False,
    )
    ch_minima_estagio = models.PositiveIntegerField('Carga Horária Mínima de Estágio e Afins', help_text='Hora', null=True, blank=True)
    periodo_minimo_estagio_obrigatorio = models.IntegerField(
        'Período Mínimo para Estágio Obrigatório',
        choices=[['', '------']] + [[x, x] for x in range(1, 11)],
        help_text='Período mínimo para realização do Estágio Obrigatório',
        null=True,
        blank=True,
    )
    periodo_minimo_estagio_nao_obrigatorio = models.IntegerField(
        'Período Mínimo para Estágio Não Obrigatório',
        choices=[['', '------']] + [[x, x] for x in range(1, 11)],
        help_text='Período mínimo para realização do Estágio Não Obrigatório',
        null=True,
        blank=True,
    )

    requer_vinculacao_extensao_diarios = models.BooleanField(
        verbose_name='Requer Vinculação de Atividade de Extensão a Diários/AACC/ATPA', default=False
    )

    # certificação parcial
    emite_certificacao_parcial = models.BooleanField(
        verbose_name='Emite certificação parcial', default=False, help_text='Habilita a emissão de certificação parcial na matriz.'
    )
    certificado_parcial_acumulavel = models.BooleanField(
        verbose_name='Certificado parcial acumulável com diploma de conclusão de curso',
        default=False,
        help_text='Permite a emissão de certificado parcial e diploma de conclusão de curso. Se esta opção for desmarcada o aluno não poderá acumular ambos documentos.',
    )

    class Meta:
        verbose_name = 'Matriz Curricular'
        verbose_name_plural = 'Matrizes Curriculares'
        ordering = ('descricao',)

    def __str__(self):
        ano_criacao = self.ano_criacao and f' - {self.ano_criacao.ano}' or ''
        periodos = f'{self.qtd_periodos_letivos} períodos' if self.qtd_periodos_letivos > 1 else '1 período'
        return f'{self.pk} - {self.descricao} - {periodos}{ano_criacao}'

    def clean(self):
        if self.ativo and self.data_fim:
            raise ValidationError('Uma matriz ativa não pode ter data de fim.')
        if not self.ativo and not self.data_fim:
            raise ValidationError('Uma matriz inativa deve ter data de fim')

    def save(self, *args, **kwargs):
        self.verificar_inconsistencias()
        super().save(*args, **kwargs)

    def replicar(self, descricao):
        componentes_curriculares = self.componentecurricular_set.all()
        list(componentes_curriculares)
        self.id = None
        self.descricao = descricao
        self.clean()
        self.save()

        for componente_curricular in componentes_curriculares:
            pre_requisitos = componente_curricular.pre_requisitos.all()
            co_requisitos = componente_curricular.co_requisitos.all()
            componente_curricular.id = None
            componente_curricular.matriz = self
            componente_curricular.save()
            for pre_requisito in pre_requisitos:
                componente_curricular.pre_requisitos.add(pre_requisito)
            for co_requisito in co_requisitos:
                componente_curricular.co_requisitos.add(co_requisito)

        return self

    def possui_projeto_integrador(self):
        return self.componentecurricular_set.filter(ch_projeto_integrador__gt=0).exists()

    def get_absolute_url(self):
        return f'/edu/matriz/{self.pk:d}/'

    def can_change(self, user):
        return user.has_perm('edu.change_matriz')

    def can_delete(self, user):
        return self.can_change(user) and self.get_matrizppc() is None

    def get_componentes_ancora_projeto_integrador(self):
        return self.componentecurricular_set.filter(ch_projeto_integrador__gt=0)

    def get_ch_projeto_integrador_definida(self, igorar_componente_curricular=None):
        qs = self.get_componentes_ancora_projeto_integrador()
        if igorar_componente_curricular:
            qs = qs.exclude(pk=igorar_componente_curricular.id)
        return sum(qs.values_list('ch_projeto_integrador', flat=True))

    def get_grupos_atuacao(self):
        return GrupoAtuacao.objects.filter(pk__in=self.componentecurricular_set.values_list('componente__grupo_atuacao', flat=True).distinct())

    def is_regime_modular(self):
        return self.estrutura and self.estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_MODULAR

    def pode_ser_editada(self, user=None):
        if settings.DEBUG:
            return True
        result = False
        if self.get_matrizppc() is None and self.can_change(user):
            result = Configuracao.get_valor_por_chave('edu', 'editar_matriz_alunos_concluidos') or not self.tem_aluno_concluido()
        return result

    def tem_aluno_concluido(self):
        return self.aluno_set.filter(situacao_id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO]).exists()

    def get_grade_curricular(self, curso_campus=None):
        result = {}
        for cc in self.componentecurricular_set.all():
            p = str(cc.periodo_letivo or 0)
            prerequisitos = []
            for prerequisito in cc.pre_requisitos.all():
                prerequisitos.append({'id': str(prerequisito.pk)})
            corequisitos = []
            for corequisito in cc.co_requisitos.all():
                corequisitos.append({'id': str(corequisito.pk)})
            componente = {
                'componente': cc.componente.descricao_historico.replace("'", ''),
                'id': str(cc.pk),
                'periodo': str(p),
                'tipo': str(cc.tipo),
                'prerequisitos': prerequisitos,
                'corequisitos': corequisitos,
                'ch_hora_relogio': cc.componente.get_ch_hora_relogio(),
                'sigla': cc.componente.sigla,
                'optativo': cc.optativo,
                'plano_disciplina_ppc': cc.get_plano_disciplina_ppc(),
                'plano_disciplina_pomc': cc.get_plano_disciplina_pomc(curso_campus),
            }
            if p not in result:
                result[p] = []
            result[p].append(componente)
        return result

    def get_ch_certificavel_aproveitavel(self):
        return self.ch_componentes_obrigatorios + self.ch_componentes_optativos + self.ch_componentes_eletivos + self.ch_seminarios

    def toJson(self):
        import json

        m = []
        for cc in self.componentecurricular_set.all():
            prerequisitos = []
            corequisitos = []
            for prerequisito in cc.pre_requisitos.all():
                prerequisitos.append({'id': str(prerequisito.pk)})
            for corequisito in cc.co_requisitos.all():
                corequisitos.append({'id': str(corequisito.pk)})

            m.append(
                {
                    'componente': cc.componente.descricao_historico.replace("'", ''),
                    'id': str(cc.pk),
                    'periodo': str(cc.periodo_letivo or 0),
                    'tipo': str(cc.tipo),
                    'prerequisitos': prerequisitos,
                    'corequisitos': corequisitos,
                    'ch_hora_relogio': str(cc.componente.get_ch_hora_relogio()),
                    'sigla': cc.componente.sigla,
                    'optativo': cc.optativo,
                }
            )
        return json.dumps({'matriz': m})

    def get_numero_colunas(self):
        qs = self.componentecurricular_set.filter(optativo=False).values_list('periodo_letivo', flat=True).order_by('-periodo_letivo')
        return qs and qs[0] or 0

    def get_numero_linhas(self):
        numero_linhas = 0
        for dicionarios in self.componentecurricular_set.values('periodo_letivo').annotate(Count('id')).order_by():
            count = dicionarios['id__count']
            if count >= numero_linhas:
                numero_linhas = count
        return numero_linhas

    def get_matrizppc(self):
        if 'ppc' not in settings.INSTALLED_APPS:
            return None
        from ppc.models import MatrizPPC

        return MatrizPPC.objects.filter(matriz_id=self.id).first()

    def get_ch_total(self):
        total = self.componentecurricular_set.aggregate(total=Sum('componente__ch_hora_relogio'))['total'] or 0
        return mask_ch_componente(total)

    def get_carga_horaria_total_prevista(self):
        result = (
            self.ch_componentes_obrigatorios
            + self.ch_componentes_optativos
            + self.ch_componentes_eletivos
            + self.ch_seminarios
            + self.ch_componentes_extensao  # outras CH de extensão já está somado em outros componentes ou ch de aacc/atpa
            + self.ch_componentes_tcc
            + self.ch_pratica_como_componente
            + self.ch_visita_tecnica
        )
        if not self.requer_vinculacao_extensao_diarios:
            result += self.get_ch_outras_atividades_extensao()

        if matrizppc := self.get_matrizppc():
            result += matrizppc.ppc.ch_pratica or 0
        else:
            result += self.ch_pratica_profissional
            result += self.ch_atividades_complementares
            result += self.ch_atividades_aprofundamento

        return result

    def get_carga_horaria_aula(self, ch=None):
        ch = ch or self.get_carga_horaria_total_prevista()
        cc = self.get_componentes_curriculares(apenas_obrigatorio=True).first()
        if cc:
            fator_conversao_hora_aula = cc.componente.get_fator_conversao_hora_aula()
            return round(ch * fator_conversao_hora_aula)
        return None

    def possui_componentes_obrigatorios(self):
        return self.ch_atividades_complementares > 0

    def possui_componentes_optativos(self):
        return self.ch_componentes_optativos > 0

    def possui_componentes_eletivos(self):
        return self.ch_componentes_eletivos > 0

    def requer_paticipacao_seminarios(self):
        return self.ch_seminarios > 0

    def exige_pratica_profissional(self):
        return self.ch_pratica_profissional > 0

    def exige_atividades_complementares(self):
        return self.ch_atividades_complementares > 0

    # COMPONENTES

    def get_ids_componentes(self, periodos=None, apenas_obrigatorio=False, apenas_optativas=False):
        if periodos is None:
            periodos = []
        if not hasattr(self, '_ids_componentes_cache'):
            self._ids_componentes_cache = {}
        cache_key = f'{"_".join(str(p) for p in periodos)}:{apenas_obrigatorio}:{apenas_optativas}'
        if cache_key in self._ids_componentes_cache:
            return self._ids_componentes_cache[cache_key]

        result = self.get_componentes_curriculares(periodos, apenas_obrigatorio, apenas_optativas).values_list('componente_id', flat=True)
        self._ids_componentes_cache[cache_key] = result
        return result

    def get_componentes(self, apenas_obrigatorio=False):
        return Componente.objects.filter(id__in=self.get_ids_componentes(apenas_obrigatorio=apenas_obrigatorio))

    def get_ids_componentes_regulares_obrigatorios(self):
        return self.get_componentes_curriculares_regulares_obrigatorios().values_list('componente_id', flat=True)

    def get_componentes_regulares_obrigatorios(self):
        return Componente.objects.filter(id__in=self.get_ids_componentes_regulares_obrigatorios())

    def get_ids_componentes_regulares_optativos(self):
        return self.get_componentes_curriculares_optativos().values_list('componente_id', flat=True)

    def get_componentes_regulares_optativos(self):
        return Componente.objects.filter(id__in=self.get_ids_componentes_regulares_optativos())

    def get_ids_componentes_seminario(self, apenas_obrigatorio=False):
        qs = self.get_componentes_curriculares_seminario()
        if apenas_obrigatorio:
            qs = qs.exclude(optativo=True)
        return qs.values_list('componente_id', flat=True)

    def get_componentes_seminario(self, apenas_obrigatorio=False):
        return Componente.objects.filter(id__in=self.get_ids_componentes_seminario(apenas_obrigatorio))

    def get_ids_componentes_pratica_como_componente(self, apenas_obrigatorio=False):
        qs = self.get_componentes_curriculares_pratica_como_componente()
        if apenas_obrigatorio:
            qs = qs.exclude(optativo=True)
        return qs.values_list('componente_id', flat=True)

    def get_componentes_pratica_como_componente(self, apenas_obrigatorio=False):
        return Componente.objects.filter(id__in=self.get_ids_componentes_pratica_como_componente(apenas_obrigatorio))

    def get_ids_componentes_visita_tecnica(self, apenas_obrigatorio=False):
        qs = self.get_componentes_curriculares_visita_tecnica()
        if apenas_obrigatorio:
            qs = qs.exclude(optativo=True)
        return qs.values_list('componente_id', flat=True)

    def get_componentes_visita_tecnica(self, apenas_obrigatorio=False):
        return Componente.objects.filter(id__in=self.get_ids_componentes_visita_tecnica(apenas_obrigatorio))

    def get_ids_componentes_pratica_profissional(self, apenas_obrigatorio=False):
        qs = self.get_componentes_curriculares_pratica_profissional()
        if apenas_obrigatorio:
            qs = qs.exclude(optativo=True)
        return qs.values_list('componente_id', flat=True)

    def get_componentes_pratica_profissional(self, apenas_obrigatorio=False):
        return Componente.objects.filter(id__in=self.get_ids_componentes_pratica_profissional(apenas_obrigatorio))

    def get_ids_componentes_tcc(self, apenas_obrigatorio=False):
        qs = self.get_componentes_curriculares_tcc()
        if apenas_obrigatorio:
            qs = qs.exclude(optativo=True)
        return qs.values_list('componente_id', flat=True)

    def get_componentes_tcc(self, apenas_obrigatorio=False):
        return Componente.objects.filter(id__in=self.get_ids_componentes_tcc(apenas_obrigatorio))

    # COMPONENTES CURRICULARES

    def get_componentes_curriculares(self, periodos=None, apenas_obrigatorio=False, apenas_optativas=False):
        if periodos is None:
            periodos = []
        qs = ComponenteCurricular.objects.filter(matriz_id=self.id)
        if periodos:
            if isinstance(periodos, list):
                qs = qs.filter(periodo_letivo__in=periodos)
            else:
                qs = qs.filter(periodo_letivo=periodos)
        if apenas_obrigatorio:
            qs = qs.exclude(optativo=True)

        if apenas_optativas:
            qs = qs.exclude(optativo=False)

        return qs

    def get_componentes_curriculares_regulares_obrigatorios(self):
        return self.get_componentes_curriculares(apenas_obrigatorio=True).filter(tipo=ComponenteCurricular.TIPO_REGULAR)

    def get_componentes_curriculares_optativos(self):
        return self.get_componentes_curriculares().filter(tipo=ComponenteCurricular.TIPO_REGULAR, optativo=True)

    def get_componentes_curriculares_seminario(self):
        return self.get_componentes_curriculares().filter(tipo=ComponenteCurricular.TIPO_SEMINARIO)

    def get_componentes_curriculares_pratica_profissional(self):
        return self.get_componentes_curriculares().filter(tipo=ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL)

    def get_componentes_curriculares_pratica_como_componente(self):
        return self.get_componentes_curriculares().filter(tipo=ComponenteCurricular.TIPO_PRATICA_COMO_COMPONENTE)

    def get_componentes_curriculares_visita_tecnica(self):
        return self.get_componentes_curriculares().filter(tipo=ComponenteCurricular.TIPO_VISITA_TECNICA)

    def get_componentes_curriculares_tcc(self):
        return self.get_componentes_curriculares().filter(tipo=ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO)

    # CARGA HORRÁRIA DOS COMPONENTES CURRICULARES

    def get_ch_componentes_obrigatorios(self, nucleo=None, relogio=True):
        componentes_regulares = self.get_componentes_curriculares_regulares_obrigatorios()
        if nucleo:
            componentes_regulares = componentes_regulares.filter(nucleo=nucleo).distinct()
        result = 0
        if relogio:
            result = componentes_regulares.aggregate(qtd=Sum('componente__ch_hora_relogio')).get('qtd') or 0
        else:
            result = componentes_regulares.aggregate(qtd=Sum('componente__ch_hora_aula')).get('qtd') or 0
        return mask_ch_componente(result)

    def get_ch_componentes_optativos(self, nucleo=None, relogio=True):
        componentes_optativos = self.get_componentes_curriculares_optativos()
        if nucleo:
            componentes_optativos = componentes_optativos.filter(nucleo=nucleo).distinct()
        result = 0
        if relogio:
            result = componentes_optativos.aggregate(qtd=Sum('componente__ch_hora_relogio')).get('qtd') or 0
        else:
            result = componentes_optativos.aggregate(qtd=Sum('componente__ch_hora_aula')).get('qtd') or 0
        return mask_ch_componente(result)

    def get_ch_componentes_seminario(self, nucleo=None, relogio=True):
        componentes_seminarios = self.get_componentes_curriculares_seminario()
        if nucleo:
            componentes_seminarios = componentes_seminarios.filter(nucleo=nucleo).distinct()
        result = 0
        if relogio:
            result = componentes_seminarios.aggregate(qtd=Sum('componente__ch_hora_relogio')).get('qtd') or 0
        else:
            result = componentes_seminarios.aggregate(qtd=Sum('componente__ch_hora_aula')).get('qtd') or 0
        return mask_ch_componente(result)

    def get_ch_componentes_pratica_profissional(self, nucleo=None, relogio=True):
        componentes_pratica_profissional = self.get_componentes_curriculares_pratica_profissional()
        if nucleo:
            componentes_pratica_profissional = componentes_pratica_profissional.filter(nucleo=nucleo).distinct()
        result = 0
        if relogio:
            result = componentes_pratica_profissional.aggregate(qtd=Sum('componente__ch_hora_relogio')).get('qtd') or 0
        else:
            result = componentes_pratica_profissional.aggregate(qtd=Sum('componente__ch_hora_aula')).get('qtd') or 0
        return mask_ch_componente(result)

    def get_ch_componentes_tcc(self):
        result = self.get_componentes_tcc().aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        return mask_ch_componente(result)

    def get_ch_componentes_atividade_extensao(self):
        result = (
            self.componentecurricular_set.filter(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO)
            .aggregate(Sum('componente__ch_hora_relogio'))
            .get('componente__ch_hora_relogio__sum')
            or 0
        )
        return mask_ch_componente(result)

    def get_ch_componentes_atividade_extensao_outros_componentes(self):
        return (
            self.componentecurricular_set.exclude(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO)
            .aggregate(Sum('ch_extensao'))
            .get('ch_extensao__sum')
            or 0
        )

    def get_ch_outras_atividades_extensao(self):
        return self.ch_atividades_extensao - self.ch_componentes_extensao - self.ch_componentes_com_extensao

    def get_ch_componentes_obrigatorios_faltando(self):
        return self.ch_componentes_obrigatorios - self.get_ch_componentes_obrigatorios()

    def get_ch_componentes_optativos_faltando(self):
        return self.ch_componentes_optativos - self.get_ch_componentes_optativos()

    def get_ch_componentes_seminario_faltando(self):
        return self.ch_seminarios - self.get_ch_componentes_seminario()

    def get_ch_componentes_pratica_profissional_faltando(self):
        return self.ch_pratica_profissional - self.get_ch_componentes_pratica_profissional()

    def get_ch_componentes_tcc_faltando(self):
        return self.ch_componentes_tcc - self.get_ch_componentes_tcc()

    def get_qtd_credito_componentes_obrigatorios(self, nucleo=None, periodo_letivo=None):
        componentes_obrigatorios = self.get_componentes_curriculares_regulares_obrigatorios()
        if nucleo:
            componentes_obrigatorios = componentes_obrigatorios.filter(nucleo=nucleo)
        if periodo_letivo:
            componentes_obrigatorios = componentes_obrigatorios.filter(periodo_letivo=periodo_letivo)
        return componentes_obrigatorios.aggregate(qtd=Sum('componente__ch_qtd_creditos')).get('qtd') or 0

    def get_qtd_credito_componentes_optativos(self, nucleo=None):
        componentes_optativos = self.get_componentes_curriculares_optativos()
        if nucleo:
            componentes_optativos = componentes_optativos.filter(nucleo=nucleo)
        return componentes_optativos.aggregate(qtd=Sum('componente__ch_qtd_creditos')).get('qtd') or 0

    def get_qtd_credito_componentes_seminarios(self, nucleo=None, periodo_letivo=None):
        componentes_seminarios = self.get_componentes_curriculares_seminario()
        if nucleo:
            componentes_seminarios = componentes_seminarios.filter(nucleo=nucleo)
        if periodo_letivo:
            componentes_seminarios = componentes_seminarios.filter(periodo_letivo=periodo_letivo)
        return componentes_seminarios.aggregate(qtd=Sum('componente__ch_qtd_creditos')).get('qtd') or 0

    def get_qtd_credito_componentes_pratica_profissional(self, nucleo=None, periodo_letivo=None):
        componentes_pratica_profissional = self.get_componentes_curriculares_pratica_profissional()
        if nucleo:
            componentes_pratica_profissional = componentes_pratica_profissional.filter(nucleo=nucleo)
        if periodo_letivo:
            componentes_pratica_profissional = componentes_pratica_profissional.filter(periodo_letivo=periodo_letivo)
        return componentes_pratica_profissional.aggregate(qtd=Sum('componente__ch_qtd_creditos')).get('qtd') or 0

    def is_ch_componentes_obrigatorios_faltando(self):
        return self.get_ch_componentes_obrigatorios_faltando() > 0

    def is_ch_componentes_obrigatorios_consistente(self):
        return self.get_ch_componentes_obrigatorios() == self.ch_componentes_obrigatorios

    def is_ch_componentes_optativos_faltando(self):
        return self.get_ch_componentes_optativos_faltando() > 0

    def is_ch_componentes_seminario_faltando(self):
        return self.get_ch_componentes_seminario_faltando() > 0

    def is_ch_componentes_pratica_profissional_faltando(self):
        return self.get_ch_componentes_pratica_profissional_faltando() > 0

    def is_ch_componentes_tcc_faltando(self):
        return self.get_ch_componentes_tcc_faltando() > 0

    def is_configuracao_atividade_academica_faltando(self):
        return self.ch_atividades_complementares > 0 and not self.configuracao_atividade_academica

    def is_ch_faltando(self):
        return (
            self.is_ch_componentes_obrigatorios_faltando()
            or self.is_ch_componentes_optativos_faltando()
            or self.is_ch_componentes_seminario_faltando()
            or self.is_ch_componentes_pratica_profissional_faltando()
            or self.is_ch_componentes_tcc_faltando()
            or self.is_configuracao_atividade_academica_faltando()
        )

    # CAMPUS COM CURSOS CONTENDO A MATRIZ

    def get_uos(self):
        ids = set(self.cursocampus_set.all().filter(ativo=True).values_list('diretoria__setor__uo__id', flat=True))
        return UnidadeOrganizacional.objects.suap().filter(id__in=ids)

    def get_diretorias(self):
        ids = set(self.cursocampus_set.all().filter(ativo=True).values_list('diretoria__id', flat=True))
        return Diretoria.objects.filter(id__in=ids)

    def is_configuracao_modular_invalida(self):
        return (
            self.is_regime_modular()
            and self.estrutura.componente_sem_periodo
            and self.componentecurricular_set.filter(periodo_letivo__isnull=False).exists()
        )

    def verificar_inconsistencias(self):
        retorno = False

        if self.is_ch_faltando() or not self.is_ch_componentes_obrigatorios_consistente() or self.is_configuracao_modular_invalida():
            self.inconsistente = True
        else:
            self.inconsistente = False

        return retorno


class MatrizCurso(LogModel):
    SEARCH_FIELDS = ['curso_campus__descricao', 'curso_campus__codigo', 'matriz__pk']
    # Manager
    objects = models.Manager()
    locals = MatrizCursoManager()

    # Fields
    curso_campus = models.ForeignKeyPlus('edu.CursoCampus', on_delete=models.CASCADE, verbose_name='Curso')
    matriz = models.ForeignKeyPlus('edu.Matriz', on_delete=models.CASCADE, verbose_name='Matriz')

    # Ato normativo
    resolucao_criacao = models.TextField('Documento de Criação', blank=True, null=True)  # sem uso
    resolucao_data = models.DateFieldPlus('Data de Criação', null=True, blank=True)  # sem uso
    # Ato de reconhecimento
    reconhecimento_texto = models.TextField('Descrição', blank=True, null=True)  # sem uso
    reconhecimento_data = models.DateFieldPlus('Data', null=True, blank=True)  # sem uso

    search = models.SearchField(attrs=['curso_campus', 'matriz'])

    class Meta:
        verbose_name = 'Vínculo de Matriz em Curso'
        verbose_name_plural = 'Vínculos de Matriz em Curso'
        unique_together = ('matriz', 'curso_campus')

    def get_ext_combo_template(self):
        return '<p>Matriz: {} </p><p>Curso: {}</p><p> Campus: {}</p>'.format(
            self.matriz, self.curso_campus.descricao, str(self.curso_campus.diretoria and self.curso_campus.diretoria.setor.uo.nome or '-')
        )

    def get_absolute_url(self):
        return f'/edu/cursocampus/{self.curso_campus.pk}/?tab=matrizes'

    def __str__(self):
        return 'Matriz: {} Curso: {} Campus: {}'.format(
            self.matriz, self.curso_campus.descricao, str(self.curso_campus.diretoria and self.curso_campus.diretoria.setor.uo.nome or '-')
        )

    def clean(self):
        if self.curso_campus_id and self.curso_campus.is_minicurso():
            raise ValidationError({'curso_campus': 'Cursos da modalidade FIC- (Minicurso) não podem possuir matriz curricular.'})
        if not hasattr(self, 'matriz'):
            raise ValidationError('Por favor selecione uma matriz.')
        if not self.matriz.estrutura:
            raise ValidationError('Não é possível adicionar matriz a este curso, pois o mesmo não possui Estrutura de Curso.')
        if self.matriz.estrutura.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_FREQUENCIA:
            for componente_curricular in self.matriz.componentecurricular_set.all():
                if componente_curricular.qtd_avaliacoes > 0:
                    raise ValidationError(
                        'Matrizes com componentes que requerem avaliações não podem ser vinculadas a cursos cuja estrutura de avaliação seja por frequência'
                    )

    def save(self, *args, **kwargs):
        if self.curso_campus_id and self.curso_campus.is_minicurso():
            raise ValidationError('Cursos da modalidade FIC- (Minicurso) não podem possuir matriz curricular.')
        super().save(*args, **kwargs)

    def pode_ser_excluida(self):
        from edu.models.alunos import Aluno

        return not Aluno.objects.filter(matriz=self.matriz, curso_campus=self.curso_campus).exists()

    def delete(self, *args, **kwargs):
        if self.pode_ser_excluida():
            super().delete(*args, **kwargs)
        else:
            raise Exception('A Matriz não pode ser removida, pois existem alunos nela matriculados.')

    def get_autorizacao(self):
        result = self.autorizacao_set.order_by('-data').first()
        if result is None:
            result = self.resolucao_criacao != '' and self.resolucao_criacao or None
        return result

    def get_reconhecimento(self):
        result = self.reconhecimento_set.order_by('-data').first()
        if result is None:
            result = self.reconhecimento_texto or None
        return result


class RotuloModulo(LogModel):
    matriz = models.ForeignKeyPlus('edu.Matriz', on_delete=models.CASCADE, verbose_name='Matriz')
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    tipo_modulo = models.PositiveIntegerField('Tipo de Módulo', choices=ComponenteCurricular.TIPO_MODULO_CHOICES)

    class Meta:
        verbose_name = 'Módulo'
        verbose_name_plural = 'Módulos'
        unique_together = ('matriz', 'tipo_modulo')

    def __str__(self):
        return f'{self.descricao} ({self.get_tipo_modulo_display()})'


class Autorizacao(models.ModelPlus):
    # dados da criação
    matriz_curso = models.ForeignKeyPlus(MatrizCurso, verbose_name='Matriz Curso', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus(
        verbose_name='Tipo',
        choices=[['Resolução', 'Resolução'], ['Portaria', 'Portaria'], ['Lei Federal', 'Lei Federal'], ['Deliberação', 'Deliberação']],
    )
    data = models.DateFieldPlus(verbose_name='Data')
    numero = models.CharFieldPlus(verbose_name='Número')
    adequacao = models.BooleanField(verbose_name='Adequação', default=False)

    # dados do funcionamento
    funcionamento_tipo = models.CharFieldPlus(
        verbose_name='Tipo',
        null=True,
        blank=True,
        choices=[['Resolução', 'Resolução'], ['Portaria', 'Portaria'], ['Lei Federal', 'Lei Federal'], ['Deliberação', 'Deliberação']],
    )
    funcionamento_data = models.DateFieldPlus(verbose_name='Data', null=True, blank=True)
    funcionamento_numero = models.CharFieldPlus(verbose_name='Número', null=True, blank=True)

    # dados da publicação
    numero_publicacao = models.CharFieldPlus(verbose_name='Número da Publicação', null=True, blank=True)
    data_publicacao = models.DateFieldPlus(verbose_name='Data da Publicação', null=True, blank=True)
    veiculo_publicacao = models.CharFieldPlus(verbose_name='Veículo da Publicação', choices=[['DOU', 'DOU']], null=True, blank=True)
    secao_publicacao = models.CharFieldPlus(verbose_name='Seção da Publicação', null=True, blank=True)
    pagina_publicacao = models.CharFieldPlus(verbose_name='Página da Publicação', null=True, blank=True)

    class Meta:
        verbose_name = 'Autorização'
        verbose_name_plural = 'Autorizações'

    def __str__(self):
        adequacao = self.adequacao and ' (Adequação)' or ''
        publicacao = (
            ' Publicado no DOU N° {}, seção {}, página {} em {}.'.format(
                self.numero_publicacao,
                self.secao_publicacao,
                self.pagina_publicacao,
                self.data_publicacao.strftime('%d/%m/%Y') if self.data_publicacao else '__/__/____',
            )
            if self.veiculo_publicacao
            else ''
        )
        funcionamento = ''
        if self.funcionamento_tipo:
            funcionamento = ' {} N° {} de {}.'.format(
                self.funcionamento_tipo,
                self.funcionamento_numero,
                self.funcionamento_data.strftime('%d/%m/%Y') if self.funcionamento_data else '__/__/____',
            )
        return '{} N° {} de {}.{}{}{}'.format(self.tipo, self.numero, self.data.strftime('%d/%m/%Y'), funcionamento, publicacao, adequacao)


class Reconhecimento(models.ModelPlus):
    # dados gerais
    matriz_curso = models.ForeignKeyPlus(MatrizCurso, verbose_name='Matriz Curso', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus(
        verbose_name='Tipo',
        choices=[['Resolução', 'Resolução'], ['Portaria', 'Portaria'], ['Lei Federal', 'Lei Federal'], ['Deliberação', 'Deliberação']],
    )
    data = models.DateFieldPlus(verbose_name='Data')
    numero = models.CharFieldPlus(verbose_name='Número')
    renovacao = models.BooleanField(verbose_name='Renovação', default=False)
    validade = models.DateFieldPlus(verbose_name='Validade', null=True, blank=False)

    # dados da publicação
    numero_publicao = models.CharFieldPlus(verbose_name='Número da Publicação', blank=True, null=True)
    data_publicacao = models.DateFieldPlus(verbose_name='Data da Publicação', blank=True, null=True)
    veiculo_publicacao = models.CharFieldPlus(verbose_name='Veículo da Publicação', choices=[['DOU', 'DOU']], null=True, blank=True)
    secao_publicao = models.CharFieldPlus(verbose_name='Seção da Publicação', blank=True, null=True)
    pagina_publicao = models.CharFieldPlus(verbose_name='Página da Publicação', blank=True, null=True)

    class Meta:
        verbose_name = 'Reconhecimento'
        verbose_name_plural = 'Reconhecimentos'

    def __str__(self):
        renovacao = self.renovacao and ' (Renovação)' or ''
        publicacao = (
            ' Publicado no DOU N° {}, seção {}, página {} em {}.'.format(
                self.numero_publicao,
                self.secao_publicao,
                self.pagina_publicao,
                self.data_publicacao.strftime('%d/%m/%Y') if self.data_publicacao else '__/__/____',
            )
            if self.veiculo_publicacao
            else ''
        )
        return '{} N° {} de {}.{}{}'.format(self.tipo, self.numero, self.data.strftime('%d/%m/%Y'), publicacao, renovacao)


class Minicurso(CursoCampus):
    objects = MinicursoObjectsManager()
    locals = MinicursoLocalsManager()

    class Meta:
        verbose_name = 'Curso FIC < 160h'
        verbose_name_plural = 'Cursos FIC < 160h'
        proxy = True

    def get_absolute_url(self):
        return f'/edu/minicurso/{self.pk:d}/'

    def clean(self):
        self.modalidade_id = Modalidade.FIC_MENOS
        if self.pk and self.matrizcurso_set.exists():
            raise ValidationError('Minicursos não podem possuir matriz curricular.')
        if not self.ch_total:
            raise ValidationError({'ch_total': 'Não é possível cadastrar um minicurso sem carga horária total.'})
        if self.ch_total > 160:
            raise ValidationError({'ch_total': 'Não é possível cadastrar uma carga horária total maior que 160 horas.'})
        if self.ch_total < 1:
            raise ValidationError({'ch_total': 'Não é possível cadastrar uma carga horária total menor que 1 hora.'})
        if not self.autoinstrucional and self.tipo_curso_autoinstrucional:
            raise ValidationError(
                {
                    'tipo_curso_autoinstrucional': 'O tipo de curso autoinstrucional deve ser vazio quando o curso não for marcado como autoinstrucional.'
                }
            )

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.modalidade_id = Modalidade.FIC_MENOS
        if self.pk and self.matrizcurso_set.exists():
            raise ValidationError('Minicursos não podem possuir matriz curricular.')

        if self.codigo == '' or self.codigo is None:
            minicursos_do_campus = Minicurso.objects.filter(diretoria__setor__uo=self.diretoria.setor.uo).order_by('-codigo')
            maior_codigo = minicursos_do_campus.exists() and minicursos_do_campus[0].codigo or 0
            if not maior_codigo:
                self.codigo = '0001'
            else:
                maior_codigo = str(int(maior_codigo.split('.')[0]) + 1).zfill(4)
                self.codigo = maior_codigo
            self.codigo = f'{self.codigo}.{self.diretoria.setor.uo}'

        self.ch_aula = int(self.ch_total * 60 / self.tipo_hora_aula)
        super().save(*args, **kwargs)

    def can_change(self, user=None):
        return Minicurso.locals.filter(pk=self.id).exists()

    def get_codigo(self):
        return self.codigo.split('.')[0]

    @transaction.atomic
    def clonar(self, diretorias):
        ids = []
        conteudos = list(self.conteudominicurso_set.all())
        minicurso = self
        for diretoria in diretorias:
            minicurso.pk = None
            minicurso.codigo = None
            minicurso.codigo_sistec = ''
            minicurso.diretoria = diretoria
            minicurso.modalidade_id = Modalidade.FIC_MENOS
            minicurso.save()
            ids.append(minicurso.id)
            for conteudo in conteudos:
                conteudo.pk = None
                conteudo.minicurso = minicurso
                conteudo.save()
        return ids

    get_codigo.admin_order_field = 'codigo'
    get_codigo.short_description = 'Código'


class ConteudoMinicurso(LogModel):
    descricao = models.CharFieldPlus('Descrição')
    ch = models.PositiveIntegerField('Carga Horária')
    minicurso = models.ForeignKeyPlus('edu.Minicurso', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Conteúdo'
        verbose_name_plural = 'Conteúdos'

    def __str__(self):
        return f'({self.pk}) Conteúdo'


class ConfiguracaoCertificacaoParcial(LogModel):
    SEARCH_FIELDS = ['descricao', 'matriz__id', 'matriz__descricao']

    matriz = models.ForeignKeyPlus('edu.Matriz')
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
        verbose_name = 'Configuração de certificação parcial'
        verbose_name_plural = 'Configurações de certificações parciais'

    def can_change(self, user):
        return (
            user.has_perm('edu.change_matriz')
            and not self.registroemissaodiploma_set.exists()
            and self.matriz.emite_certificacao_parcial
            and self.matriz.get_matrizppc() is None
        )

    def get_carga_horaria_total(self):
        result = self.ch_componentes_optativos or 0
        result += (
            self.componentecurricularcertificacaoparcial_set.aggregate(total=Sum('componente_curricular__componente__ch_hora_relogio'))['total'] or 0
        )
        return mask_ch_componente(result)

    def get_componentes(self):
        return self.componentecurricularcertificacaoparcial_set.all().order_by(
            'componente_curricular__tipo_modulo', 'componente_curricular__periodo_letivo'
        )


class ComponenteCurricularCertificacaoParcial(LogModel):
    configuracao_certificacao_parcial = models.ForeignKeyPlus(
        'edu.ConfiguracaoCertificacaoParcial', verbose_name='Configuração de certificação parcial', blank=False, null=False
    )
    componente_curricular = models.ForeignKeyPlus('edu.ComponenteCurricular', verbose_name='Componente curricular', blank=False, null=False)

    class Meta:
        verbose_name = 'Componente curricular de certificação parcial'
        verbose_name_plural = 'Componentes curriculares de certificações parciais'
