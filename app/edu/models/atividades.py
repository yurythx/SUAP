from django.db import transaction
from django.db.models import Q
from django.db.models.aggregates import Sum
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils.safestring import mark_safe
from djtools.db import models
from djtools.utils import mask_ch_componente
from djtools.templatetags.tags.utils import icone
from edu.models.cadastros_gerais import Turno, SituacaoMatricula
from edu.models.cursos import ComponenteCurricular
from edu.models.logs import LogModel
from enum import Enum


class HorarioAtividadeExtra(LogModel):
    DIA_SEMANA_SEG = 1
    DIA_SEMANA_TER = 2
    DIA_SEMANA_QUA = 3
    DIA_SEMANA_QUI = 4
    DIA_SEMANA_SEX = 5
    DIA_SEMANA_SAB = 6
    DIA_SEMANA_DOM = 7
    DIA_SEMANA_CHOICES = [
        [DIA_SEMANA_SEG, 'Segunda'],
        [DIA_SEMANA_TER, 'Terça'],
        [DIA_SEMANA_QUA, 'Quarta'],
        [DIA_SEMANA_QUI, 'Quinta'],
        [DIA_SEMANA_SEX, 'Sexta'],
        [DIA_SEMANA_SAB, 'Sábado'],
        [DIA_SEMANA_DOM, 'Domingo'],
    ]

    ATIVIDADE_ESTUDO = 1
    ATIVIDADE_LAZER = 2

    TIPO_CHOICES = [[ATIVIDADE_ESTUDO, 'Atividade de Estudo'], [ATIVIDADE_LAZER, 'Atividade de Lazer']]

    tipo_atividade = models.PositiveIntegerField(choices=TIPO_CHOICES, default=ATIVIDADE_ESTUDO, verbose_name='Tipo de Atividade')
    descricao_atividade = models.CharFieldPlus('Descrição')
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo')
    horario_aula = models.ForeignKeyPlus('edu.HorarioAula', on_delete=models.CASCADE)
    dia_semana = models.PositiveIntegerField(choices=DIA_SEMANA_CHOICES)

    class Meta:
        verbose_name = 'Horário da Atividade Extra'
        verbose_name_plural = 'Horários das Atividades Extras'

    def get_aluno(self):
        return self.matricula_periodo.aluno

    def get_horario_aulas(self):
        output = []
        turnos_ids = self.matricula_periodo.horarioatividadeextra_set.all().values_list('horario_aula__turno', flat=True).distinct()
        for turno in Turno.objects.filter(id__in=turnos_ids):
            dias_semana = (
                self.matricula_periodo.horarioatividadeextra_set.filter(
                    horario_aula__turno=turno, tipo_atividade=self.tipo_atividade, descricao_atividade=self.descricao_atividade
                )
                .order_by('dia_semana')
                .values_list('dia_semana', flat=True)
                .distinct()
            )
            for dia_semana in dias_semana:
                if output:
                    output.append(' / ')
                numeros = []
                for numero in (
                    self.matricula_periodo.horarioatividadeextra_set.filter(
                        horario_aula__turno=turno,
                        dia_semana=dia_semana,
                        tipo_atividade=self.tipo_atividade,
                        descricao_atividade=self.descricao_atividade,
                    )
                    .values_list('horario_aula__numero', flat=True)
                    .distinct()
                ):
                    if numero not in numeros:
                        numeros.append(str(numero))
                numeros.sort()
                output.append('{}{}{}'.format(dia_semana + 1, turno.descricao[0], ''.join(numeros)))
        return ''.join(output)


class AtividadeCurricularExtensao(LogModel):
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo')
    descricao = models.CharFieldPlus('Descrição')
    carga_horaria = models.IntegerField(verbose_name='Carga horária')

    referencia = GenericForeignKey('tipo_referencia', 'id_referencia')
    tipo_referencia = models.ForeignKeyPlus(ContentType, verbose_name='Tipo da referência', on_delete=models.CASCADE, null=True)
    id_referencia = models.PositiveIntegerField(verbose_name='Referência', null=True)

    concluida = models.BooleanField(verbose_name='Concluída', default=False)
    aprovada = models.BooleanField(verbose_name='Aprovada', null=True)

    requer_distribuicao_ch = models.BooleanField(verbose_name='Atividade requer distribuição de carga horária', default=False)
    aacc = models.ForeignKeyPlus('edu.atividadecomplementar', verbose_name='AACC', null=True, on_delete=models.SET_NULL)
    atpa = models.ForeignKeyPlus('edu.atividadeaprofundamento', verbose_name='ATPA', null=True, on_delete=models.SET_NULL)
    carga_horaria_vinculada = models.IntegerField(verbose_name='Carga horária vinculada', default=0)

    substituida = models.ForeignKeyPlus(
        'edu.AtividadeCurricularExtensao',
        null=True,
        blank=True,
        verbose_name='Atividade substituída',
        help_text='Indica a nova atividade curricular de extensão que substituiu esta atividade.',
        on_delete=models.SET_NULL,
    )

    class Meta:
        verbose_name = 'Atividade Curricular de Extensão'
        verbose_name_plural = 'Atividades Curriculares de Extensão'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.matricula_periodo.aluno.atualizar_situacao('Atualização de atividade curricular de extensão')

    def is_extra(self):
        return bool(self.tipo_referencia and self.tipo_referencia.model == 'atividadecurricularextensaoextra')

    def is_distribuicao_automatica(self):
        return self.is_componente_tipo_extensao() or self.is_componente_com_extensao_aproveitado()

    def is_componente_tipo_extensao(self):
        if self.referencia is None:
            return False
        if self.tipo_referencia.model == 'registrohistorico':
            return self.matricula_periodo.aluno.matriz.componentecurricular_set.filter(
                componente_id=self.referencia.componente_id, tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO
            ).exists()
        cc = None
        if self.tipo_referencia.model in ['aproveitamentocomponente', 'aproveitamentoestudo', 'certificacaoconhecimento']:
            cc = self.referencia.componente_curricular
        elif self.tipo_referencia.model == 'matriculadiario':
            cc = self.referencia.diario.componente_curricular
            if cc.tipo != ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO and cc.componente_curricular_associado:
                cc = cc.componente_curricular_associado
        return cc.tipo == ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO if cc else False

    def is_componente_com_extensao_aproveitado(self):
        """
        Componentes com CH parcial de extensão na matriz que foram aproveitados, certificados ou migrados
        """
        if self.referencia is None:
            return False

        if self.tipo_referencia.model in ['aproveitamentocomponente', 'aproveitamentoestudo', 'certificacaoconhecimento']:
            return self.referencia.componente_curricular.tem_ch_extensao_exigida()

        if self.tipo_referencia.model == 'registrohistorico':
            componente_id = self.referencia.componente_id
            return self.matricula_periodo.aluno.matriz.componentecurricular_set.com_extensao().filter(componente_id=componente_id).exists()

        return False

    def is_diario_associado_extensao(self):
        result = False
        if self.tipo_referencia.model == 'matriculadiario' and self.referencia.diario.componente_curricular.componente_curricular_associado:
            result = self.referencia.diario.componente_curricular.componente_curricular_associado.tipo == ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO
        return result

    @staticmethod
    def registrar(aluno, modelo, pk, ch, descricao, concluida=False, aprovada=None, matricula_periodo=None):
        tipo_referencia = ContentType.objects.get_for_model(modelo)
        qs = AtividadeCurricularExtensao.objects.filter(tipo_referencia=tipo_referencia, id_referencia=pk)
        if ch:
            atividade = qs.first() or AtividadeCurricularExtensao(tipo_referencia=tipo_referencia, id_referencia=pk)
            atividade.matricula_periodo = (
                aluno.get_ultima_matricula_periodo(excluir_em_aberto=True) if matricula_periodo is None else matricula_periodo
            )
            atividade.requer_distribuicao_ch = (
                bool(aluno.matriz and aluno.matriz.requer_vinculacao_extensao_diarios) and not atividade.is_distribuicao_automatica()
            )
            atividade.carga_horaria = ch
            atividade.descricao = descricao
            atividade.concluida = concluida
            atividade.aprovada = True if aprovada is None and concluida and atividade.requer_distribuicao_ch else aprovada

            if not atividade.requer_distribuicao_ch:
                atividade.carga_horaria_vinculada = ch if atividade.aprovada else 0
            atividade.save()
            return atividade
        else:
            qs.delete()

    def get_carga_horaria(self):
        return mask_ch_componente(self.carga_horaria)

    def get_carga_horaria_vinculada(self):
        return mask_ch_componente(self.carga_horaria_vinculada)

    def get_ch_contabilizada(self):
        if not self.aprovada or self.substituida_id is not None:
            return 0
        if not self.requer_distribuicao_ch:
            return self.get_carga_horaria()
        else:
            soma = 0
            soma += self.aacc.carga_horaria if self.aacc and self.aacc.deferida else 0
            soma += self.atpa.carga_horaria if self.atpa and self.atpa.deferida else 0
            soma += self.vinculacaoatividadeextensao_set.filter(homologada=True).aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0
            return mask_ch_componente(soma)

    def get_percentual_ch_vinculada(self):
        return int(self.carga_horaria_vinculada * 100 / self.carga_horaria if self.carga_horaria else 0)

    def get_tipo(self):
        if not self.tipo_referencia:
            return 'Atividade'
        model_cls = self.tipo_referencia.model_class()
        result = model_cls._meta.verbose_name if model_cls else 'Atividade'
        if self.is_extra():
            atividade_extra = self.get_atividade_extra()
            if atividade_extra and atividade_extra.tipo_atividade:
                result = atividade_extra.tipo_atividade.descricao
        return result

    def get_atividade_extra(self):
        result = None
        if self.is_extra():
            result = AtividadeCurricularExtensaoExtra.objects.get(id=self.id_referencia)
        return result

    def get_ch_nao_vinculada(self):
        return self.get_carga_horaria() - self.get_carga_horaria_vinculada()

    def recalcular_carga_horaria_vinculada(self, commit: bool = True) -> int:
        if not self.requer_distribuicao_ch:
            total = self.carga_horaria if self.aprovada else 0
        else:
            total = 0
            if self.aacc_id and self.aacc:
                total += self.aacc.carga_horaria or 0
            if self.atpa_id and self.atpa:
                total += self.atpa.carga_horaria or 0
            soma_vinc = self.vinculacaoatividadeextensao_set.aggregate(total=Sum('carga_horaria'))['total'] or 0
            total += soma_vinc
            total = total * 100 if settings.COMPONENTE_CH_DECIMAL else total
        self.carga_horaria_vinculada = total
        if commit:
            self.save()
        return total

    def matriz_tem_extensao_aacc(self):
        matriz = self.matricula_periodo.aluno.matriz
        return bool(matriz and matriz.ch_atividades_complementares > 0 and matriz.get_ch_outras_atividades_extensao() > 0)

    def matriz_tem_extensao_atpa(self):
        matriz = self.matricula_periodo.aluno.matriz
        return bool(matriz and matriz.ch_atividades_aprofundamento > 0 and matriz.get_ch_outras_atividades_extensao() > 0)

    def pode_distribuir(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        aluno = self.matricula_periodo.aluno
        if getattr(user, 'username', None) == aluno.matricula:
            return True
        aluno_user = aluno.get_user()
        if aluno_user and aluno_user.id == user.id:
            return True
        from edu import perms

        return perms.realizar_procedimentos_academicos(user, aluno.curso_campus)


class TipoAtividadeCurricularExtensaoExtra(LogModel):
    # gerenciado pelo adm academico

    descricao = models.CharFieldPlus('Descrição', null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de atividade curricular de extensão extra'
        verbose_name_plural = 'Tipos de atividades curriculares de extensão extra'


class AtividadeCurricularExtensaoExtra(LogModel):
    # gerenciado pelo adm academico, secretario e coordenador

    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo', verbose_name='Matrícula em período', null=False, blank=False)
    descricao = models.CharFieldPlus('Descrição', null=False, blank=False)
    tipo_atividade = models.ForeignKeyPlus('edu.TipoAtividadeCurricularExtensaoExtra', verbose_name='Tipo de atividade', null=False, blank=False)
    carga_horaria = models.IntegerField(verbose_name='Carga horária', null=False, blank=False)
    documento = models.FileFieldPlus(
        'Anexo',
        upload_to='edu/atividade_curricular_extensao/',
        null=True,
        blank=True,
        check_mimetype=False,
        help_text='Neste campo você pode anexar um certificado ou comprovante.',
        filetypes=['pdf', 'png', 'jpg'],
        max_file_size=5242880,
    )

    class Meta:
        verbose_name = 'Atividade curricular de extensão extra'
        verbose_name_plural = 'Atividades curriculares de extensão extra'

    @transaction.atomic
    def delete(self, *args, **kwargs):
        aluno = self.matricula_periodo.aluno
        AtividadeCurricularExtensao.registrar(aluno, type(self), self.pk, 0, None)
        resultado = super().delete(*args, **kwargs)
        aluno.atualizar_situacao('Exclusão de atividade curricular de extensão extra')
        return resultado

    @transaction.atomic
    def processar(self):
        self.carga_horaria = self.carga_horaria * 100 if settings.COMPONENTE_CH_DECIMAL else self.carga_horaria
        self.save()
        AtividadeCurricularExtensao.registrar(
            self.matricula_periodo.aluno, type(self), self.pk, self.carga_horaria, self.descricao, True, True, self.matricula_periodo
        )

    def can_delete(self, user: object | None = None) -> bool:
        atividade = AtividadeCurricularExtensao.objects.filter(
            id_referencia=self.pk, tipo_referencia__model='atividadecurricularextensaoextra'
        ).first()
        if atividade is None:
            return True
        if atividade.atividadecurricularextensao_set.exists():
            return False
        if not atividade.requer_distribuicao_ch:
            return True
        return atividade.carga_horaria_vinculada == 0

    def get_carga_horaria(self):
        return mask_ch_componente(self.carga_horaria)


class ConfiguracaoIntegracaoPraticaProfissional(Enum):
    ESTAGIO = {'app_label': 'Estágios', 'app': 'estagios', 'model': 'praticaprofissional'}
    PROJETO_EXTENSAO = {'app_label': 'Projetos', 'app': 'projetos', 'model': 'participacao'}
    MINICURSO = {'app_label': 'Ensino', 'app': 'edu', 'model': 'participanteturmaminicurso'}
    PROJETO_INTEGRADOR = {'app_label': 'Ensino', 'app': 'edu', 'model': 'avaliacaoprojetointegrador'}

    def get_integracao(modalidade_pratica_profissional_id):
        if modalidade_pratica_profissional_id not in ConfiguracaoIntegracaoPraticaProfissional.list_modalidades_integradas():
            return None
        if modalidade_pratica_profissional_id in [
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_FIC_PRATICA,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_FIC_PESQUISA,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_FIC_EXTENSAO,
        ]:
            return ConfiguracaoIntegracaoPraticaProfissional.MINICURSO
        if modalidade_pratica_profissional_id == ModalidadePraticaProfissional.MODALIDADE_PRATICA_ESTAGIO:
            return ConfiguracaoIntegracaoPraticaProfissional.ESTAGIO
        if modalidade_pratica_profissional_id == ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_EXTENSAO:
            return ConfiguracaoIntegracaoPraticaProfissional.PROJETO_EXTENSAO
        if modalidade_pratica_profissional_id in ModalidadePraticaProfissional.get_ids_modalidades_projeto_integrador():
            return ConfiguracaoIntegracaoPraticaProfissional.PROJETO_INTEGRADOR
        return None

    def list_modalidades_integradas():
        return [
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_FIC_PRATICA,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_FIC_PESQUISA,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_FIC_EXTENSAO,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_ESTAGIO,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_EXTENSAO,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_INTEGRADOR_1,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_INTEGRADOR_2,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_INTEGRADOR_3,
        ]


class AtividadePraticaProfissional(LogModel):
    SOLICITADA = '1'
    EM_ANDAMENTO = '2'
    SEM_NOTA = '3'
    AGUARDANDO_REAVALIACAO = '4'
    CONCLUIDA = '5'
    DESCONSIDERADA = '6'
    INSUFICIENTE = '7'
    INDEFERIDA = '8'
    SITUACAO_CHOICES = [
        [SOLICITADA, 'Solicitada'],
        [EM_ANDAMENTO, 'Em andamento'],
        [CONCLUIDA, 'Concluída'],
        [DESCONSIDERADA, 'Desconsiderada'],
        [INDEFERIDA, 'Indeferida'],
        [INSUFICIENTE, 'Nota insuficiente'],
        [SEM_NOTA, 'Aguardando nota'],
        [AGUARDANDO_REAVALIACAO, 'Aguardando reavaliação'],
    ]

    descricao = models.CharFieldPlus('Descrição')
    situacao = models.CharFieldPlus(verbose_name='Situação', choices=SITUACAO_CHOICES, default=SOLICITADA)
    carga_horaria = models.IntegerField(verbose_name='Carga horária', null=True)
    nota = models.IntegerField(verbose_name='Nota', null=True)
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo', verbose_name='Período')
    modalidade_pratica_profissional = models.ForeignKeyPlus('edu.ModalidadePraticaProfissional', verbose_name='Modalidade de prática profissional')

    nota_editavel = models.BooleanField(
        'Nota editável', help_text='Permite a edição de nota em modalidades integradas com outros módulos do SUAP.', default=False
    )

    referencia = GenericForeignKey('tipo_referencia', 'id_referencia')
    tipo_referencia = models.ForeignKeyPlus(ContentType, verbose_name='Tipo da referência', on_delete=models.CASCADE, null=True)
    id_referencia = models.PositiveIntegerField(verbose_name='Referência', null=True)
    url_registro_referencia = models.CharFieldPlus(verbose_name='URL de registro da referência', null=True, blank=True)

    documento_inscricao = models.FileFieldPlus(
        'Comprovante de participação',
        upload_to='edu/atividade_pratica_profissional/',
        null=True,
        blank=True,
        check_mimetype=False,
        help_text='Informe um comprovante de inscrição ou participação da atividade.',
        filetypes=['pdf', 'png', 'jpg'],
        max_file_size=5 * settings.BYTES_SIZE_1MB,
    )

    documento_conclusao = models.FileFieldPlus(
        'Comprovante de conclusão',
        upload_to='edu/atividade_pratica_profissional/',
        null=True,
        blank=False,
        check_mimetype=False,
        help_text='Informe o certificado de conclusão da atividade de prática profissional.',
        filetypes=['pdf', 'png', 'jpg'],
        max_file_size=5 * settings.BYTES_SIZE_1MB,
    )

    class Meta:
        verbose_name = 'Atividade de prática profissional'
        verbose_name_plural = 'Atividades de prática profissional'
        ordering = ('situacao', 'matricula_periodo', 'modalidade_pratica_profissional_id')

    def iniciar(self):
        self.situacao = AtividadePraticaProfissional.EM_ANDAMENTO
        self.save()

    def deferir(self):
        self.situacao = AtividadePraticaProfissional.CONCLUIDA
        self.save()

    def indeferir(self):
        self.situacao = AtividadePraticaProfissional.INDEFERIDA
        self.save()

    def concluir(self):
        if self.carga_horaria is None:
            raise ValidationError('A carga horária cumprida nesta atividade não foi informada.')
        if self.nota is None:
            raise ValidationError('A nota obtida nesta atividade não foi informada.')

        self.situacao = (
            AtividadePraticaProfissional.INSUFICIENTE
            if self.nota < self.matricula_periodo.aluno.matriz.estrutura.media_aprovacao_sem_prova_final
            else AtividadePraticaProfissional.CONCLUIDA
        )
        self.save()

    @staticmethod
    def registrar_inicio(modalidade_pratica_profissional_id, id_referencia, modelo, matricula_periodo_id, url_registro_referencia, descricao=None):
        configuracao = ConfiguracaoIntegracaoPraticaProfissional.get_integracao(modalidade_pratica_profissional_id)

        if not configuracao:
            raise ValidationError('A integração para esta atividade de prática profissional não está configurada.')

        tipo_referencia = ContentType.objects.get_for_model(modelo)
        if tipo_referencia.id != ContentType.objects.get(app_label=configuracao.value['app'], model=configuracao.value['model']).id:
            raise ValidationError('A configuração da integração para esse tipo de atividade de prática profissional está incorreta.')

        if descricao is None:
            descricao = f'Atividade de prática profissional - {ModalidadePraticaProfissional.objects.get(id=modalidade_pratica_profissional_id).nome}'

        atividade = AtividadePraticaProfissional()
        atividade.descricao = descricao
        atividade.situacao = AtividadePraticaProfissional.EM_ANDAMENTO
        atividade.matricula_periodo_id = matricula_periodo_id
        atividade.modalidade_pratica_profissional_id = modalidade_pratica_profissional_id
        atividade.id_referencia = id_referencia
        atividade.tipo_referencia = tipo_referencia
        atividade.url_registro_referencia = url_registro_referencia
        atividade.save()
        return atividade

    @staticmethod
    def registrar_conclusao(atividade, carga_horaria, nota=None):
        if not atividade:
            raise ValidationError('Não existe atividade de prática profissional registrada para essa referência.')
        if carga_horaria is None:
            raise ValidationError('A carga horária cumprida nesta atividade não foi informada.')
        atividade.carga_horaria = carga_horaria
        atividade.nota = nota
        if nota is None:
            atividade.situacao = AtividadePraticaProfissional.SEM_NOTA
            atividade.nota_editavel = True
        else:
            atividade.situacao = (
                AtividadePraticaProfissional.INSUFICIENTE
                if atividade.nota < atividade.matricula_periodo.aluno.matriz.estrutura.media_aprovacao_sem_prova_final
                else AtividadePraticaProfissional.CONCLUIDA
            )

        atividade.save()

    @staticmethod
    def registrar_inicio_e_conclusao(
        modalidade_pratica_profissional_id,
        id_referencia,
        modelo,
        matricula_periodo_id,
        carga_horaria,
        url_registro_referencia,
        descricao=None,
        nota=None,
    ):
        atividade = AtividadePraticaProfissional.get(id_referencia, modelo)
        if atividade is None:
            atividade = AtividadePraticaProfissional.registrar_inicio(
                modalidade_pratica_profissional_id, id_referencia, modelo, matricula_periodo_id, url_registro_referencia, descricao
            )
        AtividadePraticaProfissional.registrar_conclusao(atividade, carga_horaria, nota)

    @staticmethod
    def get(id_referencia, modelo):
        tipo_referencia = ContentType.objects.get_for_model(modelo)
        return (
            AtividadePraticaProfissional.objects.filter(tipo_referencia=tipo_referencia, id_referencia=id_referencia)
            .only('id')
            .order_by('-id')
            .first()
        )

    @staticmethod
    def desfazer_conclusao(id_referencia, modelo):
        atividade = AtividadePraticaProfissional.get(id_referencia, modelo)
        if atividade and atividade.situacao in [
            AtividadePraticaProfissional.CONCLUIDA,
            AtividadePraticaProfissional.INSUFICIENTE,
            AtividadePraticaProfissional.SEM_NOTA,
        ]:
            if not atividade.is_aluno_cursando():
                raise ValidationError('A situação atual do aluno não permite desfazer a conclusão desta atividade de prática profissional.')
            atividade.situacao = AtividadePraticaProfissional.EM_ANDAMENTO
            atividade.carga_horaria = None
            atividade.nota = None
            atividade.save()

    @staticmethod
    def remover_registro(id_referencia, modelo):
        atividade = AtividadePraticaProfissional.get(id_referencia, modelo)
        if atividade:
            if atividade.situacao == AtividadePraticaProfissional.CONCLUIDA and not atividade.is_aluno_cursando():
                raise ValidationError('A situação atual do aluno não permite remover o registro desta atividade de prática profissional.')
            atividade.delete()

    def desconsiderar(self):
        self.situacao = AtividadePraticaProfissional.DESCONSIDERADA
        self.save()

    def reconsiderar(self):
        self.situacao = AtividadePraticaProfissional.CONCLUIDA
        self.save()

    def can_change(self, user):
        if self.modalidade_pratica_profissional.possui_integracao() and not self.nota_editavel:
            return False
        if not self.is_aluno_cursando():
            return False
        if self.situacao == AtividadePraticaProfissional.SOLICITADA:
            return self.is_proprio_aluno(user) or (user.has_perm('edu.change_atividadepraticaprofissional') and not user.has_perm('comum.is_aluno'))
        if self.situacao in [
            AtividadePraticaProfissional.EM_ANDAMENTO,
            AtividadePraticaProfissional.CONCLUIDA,
            AtividadePraticaProfissional.INSUFICIENTE,
        ]:
            return user.has_perm('edu.change_atividadepraticaprofissional') and not user.has_perm('comum.is_aluno')
        return False

    def can_delete(self, user):
        if self.modalidade_pratica_profissional.possui_integracao():
            return False
        if not self.is_aluno_cursando():
            return False
        if self.situacao == AtividadePraticaProfissional.SOLICITADA:
            return self.is_proprio_aluno(user)
        return user.has_perm('comum.is_administrador_academico')

    @staticmethod
    def pode_registrar(aluno, modalidade_pratica_profissional_id):
        if modalidade_pratica_profissional_id not in ConfiguracaoIntegracaoPraticaProfissional.list_modalidades_integradas():
            return False
        matrizppc = aluno.matriz.get_matrizppc() if aluno.matriz else None
        if matrizppc is None:
            return False
        if matrizppc.ppc.ch_pratica > 0:
            return (
                matrizppc.get_modalidades_praticaprofissionalppc()
                .filter(modalidade_pratica_profissional_id=modalidade_pratica_profissional_id)
                .exists()
            )
        return False

    def pode_iniciar(self, user):
        return self.situacao == AtividadePraticaProfissional.SOLICITADA and self.pode_alterar_situacao(user)

    def pode_concluir(self, user):
        return self.situacao == AtividadePraticaProfissional.EM_ANDAMENTO and self.pode_alterar_situacao(user)

    def pode_deferir(self, user):
        return self.situacao == AtividadePraticaProfissional.AGUARDANDO_REAVALIACAO and self.pode_alterar_situacao(user)

    def pode_indeferir(self, user):
        return self.situacao in [
            AtividadePraticaProfissional.SOLICITADA,
            AtividadePraticaProfissional.AGUARDANDO_REAVALIACAO,
        ] and self.pode_alterar_situacao(user)

    def pode_lancar_nota(self, user):
        return (
            user.has_perm('edu.change_atividadepraticaprofissional')
            and not user.has_perm('comum.is_aluno')
            and self.situacao == AtividadePraticaProfissional.SEM_NOTA
        )

    def pode_desconsiderar(self, user):
        return (
            user.has_perm('edu.change_atividadepraticaprofissional')
            and self.situacao == AtividadePraticaProfissional.CONCLUIDA
            and self.is_aluno_cursando()
        )

    def pode_reconsiderar(self, user):
        return (
            user.has_perm('edu.change_atividadepraticaprofissional')
            and self.situacao == AtividadePraticaProfissional.DESCONSIDERADA
            and self.is_aluno_cursando()
        )

    def pode_alterar_situacao(self, user):
        if user.has_perm('comum.is_aluno'):
            return False
        if self.modalidade_pratica_profissional.possui_integracao() and self.situacao != AtividadePraticaProfissional.AGUARDANDO_REAVALIACAO:
            return False
        if not self.is_aluno_cursando():
            return False
        if user.has_perm('edu.change_atividadepraticaprofissional'):
            curso = self.matricula_periodo.aluno.curso_campus
            if user.get_vinculo().id in [curso.coordenador_id, curso.coordenador_2_id]:
                return True
            return user.has_perm('comum.is_administrador_academico')
        return False

    def is_aluno_cursando(self):
        return self.matricula_periodo.aluno.situacao_id in SituacaoMatricula.SITUACOES_CURSANDO

    def is_proprio_aluno(self, user):
        return self.matricula_periodo.aluno.matricula == user.username

    def get_acoes(self, user, from_admin=False):
        html = []
        html.append('<ul class="action-bar">')
        if self.pode_iniciar(user):
            url = reverse('iniciar_atividadepraticaprofissional', args=[self.id])
            html.append(f'<li><a class="btn success" href="{url}">{icone("plus")} Iniciar </a></li>')

        if self.pode_concluir(user):
            url = reverse('concluir_atividadepraticaprofissional', args=[self.id])
            html.append(f'<li><a class="btn success popup" href="{url}">{icone("check")} Concluir </a></li>')

        if self.pode_lancar_nota(user):
            url = reverse('lancar_nota_atividadepraticaprofissional', args=[self.id])
            html.append(f'<li><a class="btn success popup" href="{url}">{icone("check-square")} Lançar nota </a></li>')

        if self.can_change(user):
            url = reverse('editar_atividadepraticaprofissional', args=[self.id])
            html.append(f'<li><a class="btn primary popup" href="{url}">{icone("edit")} Editar </a></li>')

        if self.pode_deferir(user):
            url = reverse('deferir_atividadepraticaprofissional', args=[self.id])
            html.append(f'<li><a class="btn success" href="{url}">{icone("check")} Deferir</a></li>')

        if self.pode_indeferir(user):
            url = reverse('indeferir_atividadepraticaprofissional', args=[self.id])
            html.append(f'<li><a class="btn danger" href="{url}">{icone("times")} Indeferir </a></li>')

        if self.can_delete(user):
            url = f'/comum/excluir/edu/atividadepraticaprofissional/{self.id}/'
            html.append(f'<li><a class="btn danger popup" href="{url}">{icone("trash")} Remover </a></li>')

        if self.pode_desconsiderar(user):
            url = reverse('desconsiderar_atividadepraticaprofissional', args=[self.id])
            html.append(
                f'<li><a class="btn danger" href="{url}" data-confirm="Você quer desconsiderar esta atividade no cálculo da média e da carga horária contabilizada?">{icone("undo")} Desconsiderar</a></li>'
            )

        if self.pode_reconsiderar(user):
            url = reverse('reconsiderar_atividadepraticaprofissional', args=[self.id])
            html.append(
                f'<li><a class="btn warning" href="{url}" data-confirm="Você quer incluir esta atividade no cálculo da média e da carga horária contabilizada?">{icone("redo")} Reconsiderar</a></li>'
            )

        if from_admin:
            html.append(
                f'<li><a class="btn default" href="{self.matricula_periodo.aluno.get_absolute_url()}?tab=atividades_pratica_profissional#{self.id}" title="Visualizar aluno">{icone("eye")} Visualizar aluno</a></li>'
            )

        if self.url_registro_referencia:
            html.append(f'<li><a class="btn default" href="{self.url_registro_referencia}">{icone("eye")} Visualizar registro</a></li>')

        if self.documento_inscricao:
            html.append(f'<li><a class="btn" href="{self.documento_inscricao.url}">{icone("download")} Comprovante de inscrição</a></li>')

        if self.documento_conclusao:
            html.append(f'<li><a class="btn" href="{self.documento_conclusao.url}">{icone("download")} Comprovante de conclusão</a></li>')

        html.append('</ul>')
        return mark_safe(''.join(html))

    @staticmethod
    def get_pendentes_avaliacao_coordenador(user, queryset=None):
        qs = AtividadePraticaProfissional.get_atividades_coordenador(user, queryset)
        return qs.filter(situacao=AtividadePraticaProfissional.SOLICITADA)

    @staticmethod
    def get_pendentes_reavaliacao_coordenador(user, queryset=None):
        qs = AtividadePraticaProfissional.get_atividades_coordenador(user, queryset)
        return qs.filter(situacao=AtividadePraticaProfissional.AGUARDANDO_REAVALIACAO)

    @staticmethod
    def get_pendentes_conclusao_coordenador(user, queryset=None):
        qs = AtividadePraticaProfissional.get_atividades_coordenador(user, queryset)
        return qs.filter(situacao=AtividadePraticaProfissional.EM_ANDAMENTO).exclude(
            modalidade_pratica_profissional__in=ConfiguracaoIntegracaoPraticaProfissional.list_modalidades_integradas()
        )

    @staticmethod
    def get_pendentes_nota_coordenador(user, queryset=None):
        qs = AtividadePraticaProfissional.get_atividades_coordenador(user, queryset)
        return qs.filter(situacao=AtividadePraticaProfissional.SEM_NOTA)

    @staticmethod
    def get_atividades_coordenador(user, queryset):
        if queryset is None:
            queryset = AtividadePraticaProfissional.objects.all()
        qs = queryset.filter(matricula_periodo__aluno__situacao__in=SituacaoMatricula.SITUACOES_CURSANDO).filter(
            Q(matricula_periodo__aluno__curso_campus__coordenador__user_id=user.id)
            | Q(matricula_periodo__aluno__curso_campus__coordenador_2__user_id=user.id)
        )

        return qs

    @staticmethod
    def get_pendencias_coordenador(user):
        pendencias = []
        qtd_pendentes_avaliacao = AtividadePraticaProfissional.get_pendentes_avaliacao_coordenador(user).count()
        if qtd_pendentes_avaliacao:
            pendencias.append(
                {
                    'nome': f'Atividade{pluralize(qtd_pendentes_avaliacao)} de prática profissional',
                    'quantidade': qtd_pendentes_avaliacao,
                    'url': '/admin/edu/atividadepraticaprofissional/?tab=tab_aguardando_minha_avaliacao',
                    'subtexto': 'Aguardando avaliação',
                }
            )
        qtd_pendentes_reavaliacao = AtividadePraticaProfissional.get_pendentes_reavaliacao_coordenador(user).count()
        if qtd_pendentes_reavaliacao:
            pendencias.append(
                {
                    'nome': f'Atividade{pluralize(qtd_pendentes_reavaliacao)} de prática profissional',
                    'quantidade': qtd_pendentes_reavaliacao,
                    'url': '/admin/edu/atividadepraticaprofissional/?tab=tab_aguardando_minha_reavaliacao',
                    'subtexto': 'Aguardando reavaliação',
                }
            )
        qtd_pendentes_conclusoes = AtividadePraticaProfissional.get_pendentes_conclusao_coordenador(user).count()
        if qtd_pendentes_conclusoes:
            pendencias.append(
                {
                    'nome': f'Atividade{pluralize(qtd_pendentes_conclusoes)} de prática profissional',
                    'quantidade': qtd_pendentes_conclusoes,
                    'url': '/admin/edu/atividadepraticaprofissional/?tab=tab_aguardando_minha_conclusao',
                    'subtexto': 'Aguardando conclusão',
                }
            )

        qtd_pendentes_nota = AtividadePraticaProfissional.get_pendentes_nota_coordenador(user).count()
        if qtd_pendentes_nota:
            pendencias.append(
                {
                    'nome': f'Atividade{pluralize(qtd_pendentes_nota)} de prática profissional',
                    'quantidade': qtd_pendentes_nota,
                    'url': '/admin/edu/atividadepraticaprofissional/?tab=tab_sem_nota',
                    'subtexto': 'Aguardando lançamento de nota',
                }
            )
        return pendencias

    @staticmethod
    def get_ids_atividades_contabilizadas(aluno, modalidade_pratica_profissional_id=None):
        cache_key = f'_ids_atividades_contabilizadas_cache_{modalidade_pratica_profissional_id}'
        if hasattr(aluno, cache_key):
            return getattr(aluno, cache_key)

        ids_contabilizadas = []
        # Verifica se aluno tem matriz
        matrizppc = aluno.matriz.get_matrizppc() if aluno.matriz_id else None
        if matrizppc is None:
            setattr(aluno, cache_key, ids_contabilizadas)
            return ids_contabilizadas

        # Cachear modalidades para evitar múltiplas queries
        modalidades_ppc = list(matrizppc.get_modalidades_praticaprofissionalppc().values('modalidade_pratica_profissional_id', 'ch_requerida'))
        if not modalidades_ppc:
            setattr(aluno, cache_key, ids_contabilizadas)
            return ids_contabilizadas

        # Determinar modalidades a processar
        if modalidade_pratica_profissional_id is None:
            modalidades_da_matriz = [m['modalidade_pratica_profissional_id'] for m in modalidades_ppc]
        else:
            modalidades_da_matriz = [modalidade_pratica_profissional_id]

        # Criar mapa de ch_requerida por modalidade para acesso O(1)
        ch_requerida_por_modalidade = {m['modalidade_pratica_profissional_id']: m['ch_requerida'] for m in modalidades_ppc}

        # Buscar apenas campos necessários, ordenado por nota descrescente
        atividades_dados = list(
            AtividadePraticaProfissional.objects.filter(
                matricula_periodo__aluno_id=aluno.id,
                nota__isnull=False,
                carga_horaria__isnull=False,
                situacao=AtividadePraticaProfissional.CONCLUIDA,
                modalidade_pratica_profissional_id__in=modalidades_da_matriz,
            )
            .values_list('id', 'carga_horaria', 'modalidade_pratica_profissional_id')
            .order_by('-nota')
        )

        if atividades_dados:
            # Separar atividades por tipo de ch_requerida
            atividades_sem_ch_requerida = []
            atividades_com_ch_requerida_por_modalidade = {}

            for atividade_id, carga_horaria, modalidade_id in atividades_dados:
                ch_requerida = ch_requerida_por_modalidade.get(modalidade_id)
                if ch_requerida is None or ch_requerida == 0:
                    atividades_sem_ch_requerida.append((atividade_id, carga_horaria))
                else:
                    if modalidade_id not in atividades_com_ch_requerida_por_modalidade:
                        atividades_com_ch_requerida_por_modalidade[modalidade_id] = []
                    atividades_com_ch_requerida_por_modalidade[modalidade_id].append((atividade_id, carga_horaria))

            # Calcular limite de ch para atividades sem ch_requerida
            total_ch_requerida = sum(m['ch_requerida'] or 0 for m in modalidades_ppc)
            ch_limite_ch_nao_requeridas = matrizppc.ppc.ch_pratica - total_ch_requerida

            # Processar atividades sem ch_requerida
            ch_acumulada = 0
            for atividade_id, carga_horaria in atividades_sem_ch_requerida:
                if ch_acumulada < ch_limite_ch_nao_requeridas:
                    ch_acumulada += carga_horaria
                    ids_contabilizadas.append(atividade_id)
                else:
                    break

            # Processar atividades com ch_requerida por modalidade
            for modalidade_id, atividades in atividades_com_ch_requerida_por_modalidade.items():
                ch_requerida = ch_requerida_por_modalidade[modalidade_id]
                ch_acumulada = 0
                for atividade_id, carga_horaria in atividades:
                    if ch_acumulada < ch_requerida:
                        ch_acumulada += carga_horaria
                        ids_contabilizadas.append(atividade_id)
                    else:
                        break

        setattr(aluno, cache_key, ids_contabilizadas)
        return ids_contabilizadas


class ModalidadePraticaProfissional(LogModel):
    SEARCH_FIELDS = [
        'nome',
    ]

    MODALIDADE_PRATICA_FIC_PRATICA = 1
    MODALIDADE_PRATICA_FIC_PESQUISA = 2
    MODALIDADE_PRATICA_FIC_EXTENSAO = 3
    MODALIDADE_PRATICA_PROJETO_INTEGRADOR_1 = 4
    MODALIDADE_PRATICA_PROJETO_INTEGRADOR_2 = 23
    MODALIDADE_PRATICA_PROJETO_INTEGRADOR_3 = 24
    MODALIDADE_PRATICA_ESTAGIO = 5
    MODALIDADE_PRATICA_PROJETO_PESQUISA = 9
    MODALIDADE_PRATICA_PROJETO_EXTENSAO = 10
    MODALIDADE_PRATICA_PROJETO_ENSINO = 11

    nome = models.CharFieldPlus('Nome', null=False, blank=False)
    descricao = models.TextField('Descrição', null=True, blank=True)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Modalidade de prática profissional'
        verbose_name_plural = 'Modalidades de prática profissional'

    def __str__(self):
        return self.nome

    def can_delete(self):
        return False

    def possui_integracao(self):
        from edu.models import ConfiguracaoIntegracaoPraticaProfissional

        return self.id in ConfiguracaoIntegracaoPraticaProfissional.list_modalidades_integradas()

    def get_nome_app_integracao(self):
        from edu.models import ConfiguracaoIntegracaoPraticaProfissional

        integracao = ConfiguracaoIntegracaoPraticaProfissional.get_integracao(self.id)
        return integracao.value['app_label'] if integracao else None

    @staticmethod
    def get_ids_modalidades_projeto_integrador():
        return [
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_INTEGRADOR_1,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_INTEGRADOR_2,
            ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_INTEGRADOR_3,
        ]
