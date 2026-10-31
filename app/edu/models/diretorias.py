import datetime

from comum.models import Ano, UsuarioGrupo, UsuarioGrupoSetor, Vinculo, User
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.template.defaultfilters import pluralize
from djtools.db import models
from djtools.html.calendarios import Calendario
from djtools.utils import somar_dias
from edu.managers import DiretoriaManager, FiltroUnidadeOrganizacionalManager
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES, HorarioAulaDiario
from edu.models.diarios import Diario, ProfessorDiario
from edu.models.historico import MatriculaPeriodo
from edu.models.logs import LogModel
from edu.models.procedimentos import Requerimento
from edu.models.solicitacoes import SolicitacaoProrrogacaoEtapa, SolicitacaoRelancamentoEtapa
from edu.models.turmas import Turma
from rh.models import Servidor


class Diretoria(LogModel):
    SEARCH_FIELDS = ['setor__uo__sigla', 'setor__sigla']

    TIPO_DIRETORIA_ACADEMICA = 1
    TIPO_DIRETORIA_ENSINO = 2
    TIPO_SISTEMICA = 3
    TIPO_PRONATEC = 4
    TIPO_CHOICES = [
        [TIPO_DIRETORIA_ACADEMICA, 'Diretoria Acadêmica'],
        [TIPO_DIRETORIA_ENSINO, 'Diretoria de Ensino'],
        [TIPO_SISTEMICA, 'Sistêmica'],
        [TIPO_PRONATEC, 'PRONATEC'],
    ]

    setor = models.ForeignKeyPlus('rh.Setor')
    codigo_academico = models.IntegerField(null=True)
    diretor_geral = models.ForeignKeyPlus('comum.Vinculo', related_name='diretorgeral_set', null=True, blank=True)
    diretor_geral_exercicio = models.ForeignKeyPlus('comum.Vinculo', related_name='diretorgeralexercicio_set', null=True, blank=True)

    diretor_academico = models.ForeignKeyPlus('comum.Vinculo', related_name='diretoracademico_set', null=True, blank=True)
    diretor_academico_exercicio = models.ForeignKeyPlus('comum.Vinculo', related_name='diretoracademicoexercicio_set', null=True, blank=True)
    ead = models.BooleanField('Ensino a Distância?', default=False)
    tipo = models.PositiveIntegerField(verbose_name='Tipo', choices=TIPO_CHOICES, default=1)

    titulo_autoridade_maxima_masculino = models.CharFieldPlus(
        verbose_name='Autoridade Máxima (M)', default='Reitor', help_text='Título masculino da autoridade máxima'
    )
    titulo_autoridade_maxima_feminino = models.CharFieldPlus(
        verbose_name='Autoridade Máxima (F)', default='Reitora', help_text='Título feminino da autoridade máxima'
    )

    titulo_autoridade_uo_masculino = models.CharFieldPlus(
        verbose_name='Responsável pela Unidade (M)', default='Diretor Geral', help_text='Título masculino do responsável pela unidade'
    )
    titulo_autoridade_uo_feminino = models.CharFieldPlus(
        verbose_name='Responsável pela Unidade (F)', default='Diretora Geral', help_text='Título feminino da responsável pela unidade'
    )

    titulo_autoridade_diretoria_masculino = models.CharFieldPlus(
        verbose_name='Responsável pela Diretoria (M)', default='Diretor Acadêmico', help_text='Título masculino do responsável pela diretoria'
    )
    titulo_autoridade_diretoria_feminino = models.CharFieldPlus(
        verbose_name='Responsável pela Diretoria (F)', default='Diretora Acadêmica', help_text='Título feminino da responsável pela diretoria'
    )

    id_grupo_atendimento = models.IntegerField(verbose_name='ID do Grupo de Atendimento', null=True, blank=True)

    objects = models.Manager()
    locals = DiretoriaManager()

    class Meta:
        verbose_name = 'Diretoria Acadêmica'
        verbose_name_plural = 'Diretorias Acadêmicas'
        ordering = ('setor__uo__sigla',)

    def __str__(self):
        return self.setor.sigla

    def get_absolute_url(self):
        return f'/edu/diretoria/{self.pk:d}/'

    def get_diretores_academicos(self):
        ids = []
        qs = UsuarioGrupo.objects.filter(group__name='Diretor Acadêmico', setores=self.setor)
        if qs.exists():
            for usuario_grupo in qs:
                ids.append(usuario_grupo.user.get_vinculo().id)
        return Vinculo.objects.filter(id__in=ids)

    def get_diretores_de_ensino(self):
        ids = []
        setores = Diretoria.objects.filter(setor__uo=self.setor.uo, tipo=Diretoria.TIPO_DIRETORIA_ENSINO).values_list('setor', flat=True)
        if setores.exists():
            qs = UsuarioGrupo.objects.filter(group__name='Diretor Acadêmico', setores__in=setores)
            if qs.exists():
                for usuario_grupo in qs:
                    ids.append(usuario_grupo.user.get_vinculo().id)
        return Vinculo.objects.filter(id__in=ids)

    def get_diretores_gerais(self):
        ids = []
        qs = UsuarioGrupo.objects.filter(group__name='Diretor Geral', setores=self.setor)
        if qs.exists():
            for usuario_grupo in qs:
                ids.append(usuario_grupo.user.get_vinculo().id)
        return Vinculo.objects.filter(id__in=ids)

    def get_reitores(self):
        ids = []
        qs = UsuarioGrupo.objects.filter(group__name='Reitor', setores=self.setor)
        if qs.exists():
            for usuario_grupo in qs:
                ids.append(usuario_grupo.user.get_vinculo().relacionamento.id)
        return Servidor.objects.filter(id__in=ids)

    def get_pendencias(self, ano_letivo, periodo_letivo, user=None, somente_coordenacoes=False):
        from edu.models import RegistroEmissaoDiploma
        from edu.models.alunos import Aluno, ComponenteCurricular
        from edu.models.arquivos import AlunoArquivo

        pendencias = []
        ano = Ano.objects.get(ano=ano_letivo)
        hoje = datetime.datetime.today()

        if user and (somente_coordenacoes or user.groups.filter(name='Procurador Institucional').exists()):
            from edu.models.enade import ConvocacaoENADE, ModalidadeConvocacaoENADE, RegistroConvocacaoENADE

            qs_convocacao = ConvocacaoENADE.objects.filter(ano_letivo_id=ano.id, tipo_convocacao=ConvocacaoENADE.AVALIACAO_TEORICA).only('id')
            if qs_convocacao.exists():
                convocacao_id = qs_convocacao[0].id
                qtd_nao_integralizados_convocados = 0
                for modalidade in ModalidadeConvocacaoENADE.objects.filter(
                    convocacao_enade_id=convocacao_id, data_limite_integralizacao_concluinte__lt=hoje
                ).only('percentual_minimo_concluintes', 'modalidade_id'):
                    percentual_minimo_concluintes = modalidade.percentual_minimo_concluintes
                    qs_registro = RegistroConvocacaoENADE.objects.filter(
                        possivel_integralizado=True,
                        situacao__isnull=True,
                        convocacao_enade_id=convocacao_id,
                        aluno__curso_campus__diretoria_id=self.id,
                        aluno__curso_campus__modalidade_id=modalidade.modalidade_id,
                    )
                    if somente_coordenacoes:
                        qs_registro = qs_registro.filter(aluno__curso_campus__coordenador__user_id=user.id) | qs_registro.filter(
                            aluno__curso_campus__coordenador_2__user_id=user.id
                        )
                    for registro in qs_registro.distinct():
                        if registro.percentual_ch_cumprida < percentual_minimo_concluintes:
                            registro.percentual_ch_cumprida = registro.aluno.get_percentual_carga_horaria_cumprida()
                            if registro.percentual_ch_cumprida < percentual_minimo_concluintes:
                                qtd_nao_integralizados_convocados += 1
                            else:
                                registro.save()
                if qtd_nao_integralizados_convocados:
                    eh_cordenador = 1 if somente_coordenacoes else 0
                    pendencias.append(
                        {
                            'nome': f'Convocado{pluralize(qtd_nao_integralizados_convocados)} ENADE',
                            'quantidade': qtd_nao_integralizados_convocados,
                            'url': f'/edu/convocados_enade_irregular/{convocacao_id}/{self.id}/{eh_cordenador}/',
                            'subtexto': f'Não integralizado{pluralize(qtd_nao_integralizados_convocados)}',
                        }
                    )
        if user and user.groups.filter(name='Procurador Institucional').exists():
            return pendencias

        qs_diarios = Diario.objects.filter(turma__curso_campus__diretoria_id=self.pk, ano_letivo_id=ano.id, periodo_letivo=periodo_letivo)
        if somente_coordenacoes:
            qs_diarios = qs_diarios.filter(
                Q(turma__curso_campus__coordenador__user_id=user.id) | Q(turma__curso_campus__coordenador_2__user_id=user.id)
            )

        ids_diarios = set(qs_diarios.values_list('id', flat=True))

        qtd_diarios_com_alunos_pendentes = Diario.objects.pendentes().filter(id__in=ids_diarios).count()
        if qtd_diarios_com_alunos_pendentes:
            pendencias.append(
                {
                    'nome': 'Diários',
                    'quantidade': qtd_diarios_com_alunos_pendentes,
                    'subtexto': 'Com alunos com nota pendente após o prazo de fechamento',
                    'url': f'/admin/edu/diario/?tab=tab_notas_pendentes&ano_letivo__id__exact={ano.pk}&periodo_letivo__exact={periodo_letivo}&turma__curso_campus__diretoria__id__exact={self.pk}',
                }
            )

        qs_sem_professores = qs_diarios.exclude(professordiario__id__isnull=False)
        if periodo_letivo == 1:
            qs_sem_professores = qs_sem_professores.exclude(segundo_semestre=True)
        qs_solicitacoes_pendentes = (
            SolicitacaoRelancamentoEtapa.objects.filter(uo=self.setor.uo)
            .exclude(avaliador_id__isnull=False)
            .filter(professor_diario__diario__turma__curso_campus__diretoria_id=self.pk)
        )
        solicitacoes_prorrogacao_etapa = SolicitacaoProrrogacaoEtapa.locals.pendentes().filter(
            professor_diario__diario__turma__curso_campus__diretoria_id=self.pk
        )
        if somente_coordenacoes:
            qs_solicitacoes_pendentes = qs_solicitacoes_pendentes.filter(
                professor_diario__diario__turma__curso_campus__coordenador__user_id=user.id
            ) | qs_solicitacoes_pendentes.filter(professor_diario__diario__turma__curso_campus__coordenador_2__user_id=user.id)
            solicitacoes_prorrogacao_etapa = solicitacoes_prorrogacao_etapa.filter(
                professor_diario__diario__turma__curso_campus__coordenador__user_id=user.id
            ) | solicitacoes_prorrogacao_etapa.filter(professor_diario__diario__turma__curso_campus__coordenador_2__user_id=user.id)
        qs_professores_diario = ProfessorDiario.objects.filter(
            diario__turma__curso_campus__diretoria_id=self.pk,
            diario__calendario_academico__data_fechamento_periodo__lte=datetime.datetime.now(),
            diario__ano_letivo_id=ano.id,
            diario__periodo_letivo=periodo_letivo,
        )
        qs1 = (
            qs_professores_diario.exclude(
                diario__componente_curricular__qtd_avaliacoes__in=[0, 1], diario__posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR
            )
            .exclude(
                diario__componente_curricular__qtd_avaliacoes=2,
                diario__posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR,
                diario__posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR,
            )
            .exclude(
                diario__componente_curricular__qtd_avaliacoes=4,
                diario__posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR,
                diario__posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR,
                diario__posse_etapa_3=Diario.POSSE_REGISTRO_ESCOLAR,
                diario__posse_etapa_4=Diario.POSSE_REGISTRO_ESCOLAR,
            )
        )
        qs2 = qs_professores_diario.filter(diario__posse_etapa_5=Diario.POSSE_PROFESSOR)
        qs_professores_diario = (qs1 | qs2).distinct()
        if somente_coordenacoes:
            qs_professores_diario = qs_professores_diario.filter(
                diario__turma__curso_campus__coordenador__user_id=user.id
            ) | qs_professores_diario.filter(diario__turma__curso_campus__coordenador_2__user_id=user.id)
        qtd_diarios_sem_professores = qs_sem_professores.count()
        if qtd_diarios_sem_professores:
            pendencias.append(
                {
                    'nome': 'Diários',
                    'subtexto': 'Sem professores',
                    'quantidade': qtd_diarios_sem_professores,
                    'url': f'/admin/edu/diario/?ano_letivo__id__exact={ano.pk}&periodo_letivo__exact={periodo_letivo}&tab=tab_sem_professores&turma__curso_campus__diretoria__id__exact={self.pk}',
                }
            )

        # Diretoria EAD não possui verificação de diário sem local ou horário de aula
        if not self.ead:
            qs_sem_local_aula = qs_diarios.filter(local_aula_id__isnull=True, local_laboratorio_id__isnull=True)
            # plano de retomada de aulas em virtude da pandemia (COVID19)
            qs_sem_local_aula = qs_sem_local_aula.exclude(turma__pertence_ao_plano_retomada=True)
            qs_sem_local_aula = qs_sem_local_aula.exclude(
                componente_curricular__tipo__in=[
                    ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                    ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                    ComponenteCurricular.TIPO_SEMINARIO,
                ]
            )
            if periodo_letivo == 1:
                qs_sem_local_aula = qs_sem_local_aula.exclude(segundo_semestre=True)
            qtd_diarios_sem_local_aula = qs_sem_local_aula.count()
            if qtd_diarios_sem_local_aula:
                pendencias.append(
                    {
                        'nome': 'Diários',
                        'subtexto': 'Sem local de aula',
                        'quantidade': qtd_diarios_sem_local_aula,
                        'url': f'/admin/edu/diario/?ano_letivo__id__exact={ano.pk}&periodo_letivo__exact={periodo_letivo}&tab=tab_sem_local_aula&turma__curso_campus__diretoria__id__exact={self.pk}',
                    }
                )

            ids_diarios_com_horarios = set(HorarioAulaDiario.objects.filter(diario_id__in=ids_diarios).values_list('diario_id', flat=True))
            ids_diarios_sem_horarios = list(ids_diarios - ids_diarios_com_horarios)
            if ids_diarios_sem_horarios:
                qs_sem_horario_aula = qs_diarios.filter(id__in=ids_diarios_sem_horarios).exclude(
                    componente_curricular__tipo__in=[
                        ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                        ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                        ComponenteCurricular.TIPO_SEMINARIO,
                    ]
                )
                if periodo_letivo == 1:
                    qs_sem_horario_aula = qs_sem_horario_aula.exclude(segundo_semestre=True)
                qtd_diarios_sem_horario_aula = qs_sem_horario_aula.count()
                if qtd_diarios_sem_horario_aula:
                    pendencias.append(
                        {
                            'nome': 'Diários',
                            'subtexto': 'Sem horário de aula',
                            'quantidade': qtd_diarios_sem_horario_aula,
                            'url': f'/admin/edu/diario/?ano_letivo__id__exact={ano.pk}&periodo_letivo__exact={periodo_letivo}&tab=tab_sem_horario_aula&turma__curso_campus__diretoria__id__exact={self.pk}',
                        }
                    )

        qtd_solicitacoes = qs_solicitacoes_pendentes.count()
        if qtd_solicitacoes and (not user or user.has_perm('edu.view_solicitacaorelancamentoetapa')):
            pendencias.append(
                {
                    'nome': 'Solicitações de Relançamento de Etapa',
                    'quantidade': qtd_solicitacoes,
                    'url': f'/admin/edu/solicitacaorelancamentoetapa/?tab=tab_pendentes&professor_diario__diario__turma__curso_campus__diretoria__id__exact={self.pk}',
                    'subtexto': 'Não atendidas',
                }
            )

        qs_alunos_periodo_aberto = MatriculaPeriodo.objects.com_fechamento_pendente(ano_letivo=ano, periodo_letivo=periodo_letivo, diretorias=[self])
        qs_alunos_periodo_aberto = qs_alunos_periodo_aberto.filter(aluno__curso_campus__diretoria=self)
        if somente_coordenacoes:
            qs_alunos_periodo_aberto = qs_alunos_periodo_aberto.filter(
                aluno__curso_campus__coordenador__user_id=user.id
            ) | qs_alunos_periodo_aberto.filter(aluno__curso_campus__coordenador_2__user_id=user.id)
        qtd_alunos_periodo_aberto = qs_alunos_periodo_aberto.count()
        if qtd_alunos_periodo_aberto:
            pendencias.append(
                {
                    'nome': 'Alunos',
                    'quantidade': qtd_alunos_periodo_aberto,
                    'url': f'/edu/monitoramento_fechamento_periodo/?ano_letivo={ano.pk}&periodo_letivo={periodo_letivo}&agrupamento=Curso&diretorias={self.pk}&modalidades=',
                    'subtexto': 'Com período letivo não fechado após o prazo de fechamento',
                }
            )
        qs_turmas_pendentes = Turma.locals.pendentes().filter(ano_letivo_id=ano.id, periodo_letivo=periodo_letivo, curso_campus__diretoria_id=self.pk)
        if somente_coordenacoes:
            qs_turmas_pendentes = qs_turmas_pendentes.filter(curso_campus__coordenador__user_id=user.id) | qs_turmas_pendentes.filter(
                curso_campus__coordenador_2__user_id=user.id
            )
        qtd_turmas_pendentes = qs_turmas_pendentes.count()
        if qtd_turmas_pendentes:
            pendencias.append(
                {
                    'nome': 'Turmas',
                    'quantidade': qtd_turmas_pendentes,
                    'url': f'/admin/edu/turma/?ano_letivo__id__exact={ano.pk}&periodo_letivo__exact={periodo_letivo}&tab=tab_pendentes&curso_campus__diretoria__id__exact={self.pk}',
                    'subtexto': 'Com fechamento pendente após o prazo de fechamento',
                }
            )

        if user and user.has_perm('edu.efetuar_matricula'):
            cursos_id = (
                list(self.cursocampus_set.filter(Q(coordenador__user_id=user.id) | Q(coordenador_2__user_id=user.id)).values_list('id', flat=True))
                if somente_coordenacoes
                else None
            )
            qtd_alunos_concluidos_dados_incompletos = Aluno.get_alunos_concluidos_dados_incompletos(self.pk, cursos_id).count()
            if qtd_alunos_concluidos_dados_incompletos:
                url = f'/edu/alunos_dados_incompletos/{self.pk}/'
                if cursos_id:
                    cursos_id_str = '_'.join(map(str, cursos_id))
                    url = f'{url}{cursos_id_str}/'
                pendencias.append(
                    {
                        'nome': f'Aluno{pluralize(qtd_alunos_concluidos_dados_incompletos)} concluído{pluralize(qtd_alunos_concluidos_dados_incompletos)}',
                        'quantidade': qtd_alunos_concluidos_dados_incompletos,
                        'url': url,
                        'subtexto': 'Com dados incompletos',
                    }
                )
        qtd_solicitacoes_prorrogacao_etapa = solicitacoes_prorrogacao_etapa.count()
        if qtd_solicitacoes_prorrogacao_etapa:
            pendencias.append(
                {
                    'nome': 'Solicitações de prorrogação de etapa',
                    'quantidade': qtd_solicitacoes_prorrogacao_etapa,
                    'url': f'/admin/edu/solicitacaoprorrogacaoetapa/?tab=tab_pendentes&professor_diario__diario__turma__curso_campus__diretoria__id__exact={self.pk}',
                    'subtexto': 'Não atendidas',
                }
            )
        ingressantes_sem_turma = Aluno.get_ingressantes_sem_turma(ano, periodo_letivo).filter(curso_campus__diretoria_id=self.pk)
        if somente_coordenacoes:
            ingressantes_sem_turma = ingressantes_sem_turma.filter(curso_campus__coordenador__user_id=user.id) | ingressantes_sem_turma.filter(
                curso_campus__coordenador_2__user_id=user.id
            )
        qtd_ingressantes_sem_turma = ingressantes_sem_turma.count()
        if qtd_ingressantes_sem_turma:
            pendencias.append(
                {
                    'nome': 'Alunos Ingressantes',
                    'quantidade': qtd_ingressantes_sem_turma,
                    'url': f'/edu/acompanhamento_matricula_turma/?tab=alunos&ano_letivo={ano.pk}&periodo_letivo={periodo_letivo}&diretoria={self.pk}',
                    'subtexto': 'Sem turma',
                }
            )
        qtd_diarios_nao_entregues = qs_professores_diario.count()
        if qtd_diarios_nao_entregues:
            pendencias.append(
                {
                    'nome': 'Diários',
                    'quantidade': qtd_diarios_nao_entregues,
                    'url': f'/edu/monitoramento_entrega_diarios/?ano_letivo={ano.pk}&periodo_letivo={periodo_letivo}&agrupamento=Professor&diretorias={self.pk}&modalidades=',
                    'subtexto': 'Não-entregues após o prazo de fechamento do período',
                }
            )

        qs_registros_emissao = RegistroEmissaoDiploma.objects.filter(
            codigo_qacademico__isnull=True,
            cancelado=False,
            aluno__curso_campus__diretoria_id=self.pk,
        )

        if user and user.groups.filter(name='Coordenador de Registros Acadêmicos').exists():
            for situacao, descricao in RegistroEmissaoDiploma.SITUACAO_CHOICES:
                if descricao.startswith('Aguardando'):
                    qtd_registros_emissao_pendente = qs_registros_emissao.filter(situacao=situacao).count()
                    if qtd_registros_emissao_pendente:
                        pendencias.append(
                            {
                                'nome': 'Emissão de Diploma',
                                'url': f'/admin/edu/registroemissaodiploma/?aluno__curso_campus__diretoria__id__exact={self.pk}&situacao__exact={situacao}',
                                'quantidade': qtd_registros_emissao_pendente,
                                'subtexto': descricao,
                            }
                        )

        qs_requerimentos = (
            Requerimento.get_queryset(user)
            .filter(situacao__isnull=False)
            .exclude(situacao='Arquivado')
            .filter(aluno__curso_campus__diretoria_id=self.pk)
        )
        if somente_coordenacoes:
            qs_requerimentos = qs_requerimentos.filter(tipo=Requerimento.MATRICULA_DISCIPLINA)
            qs_requerimentos = qs_requerimentos.filter(aluno__curso_campus__coordenador__user_id=user.id) | qs_requerimentos.filter(
                aluno__curso_campus__coordenador_2__user_id=user.id
            )
        qtd_requerimentos = qs_requerimentos.distinct().count()
        if qtd_requerimentos:
            pendencias.append(
                {
                    'nome': 'Requerimentos de Aluno',
                    'quantidade': qtd_requerimentos,
                    'url': f'/admin/edu/requerimento/?tab=tab_em_andamento&aluno__curso_campus__diretoria={self.pk}',
                    'subtexto': 'Em Andamento',
                }
            )

        qs = AlunoArquivo.objects.filter(validado__isnull=True, aluno__curso_campus__diretoria=self)
        if somente_coordenacoes:
            qs = qs.filter(aluno__curso_campus__coordenador__user_id=user.id) | qs.filter(aluno__curso_campus__coordenador_2__user_id=user.id)
        if qs.exists():
            param = '?coordenador=1' if somente_coordenacoes else ''
            pendencias.append(
                {
                    'nome': 'Arquivos',
                    'quantidade': qs.count(),
                    'url': f'/edu/avaliacao_documentos/{self.pk}/{param}',
                    'subtexto': 'Aguardando avaliação',
                }
            )

        return pendencias

    def is_diretoria_sistemica(self):
        return self.tipo == Diretoria.TIPO_SISTEMICA

    def is_diretoria_ensino(self):
        return self.tipo == Diretoria.TIPO_DIRETORIA_ENSINO

    def remover_cra(self, usuariogrupo_id):
        usuario_grupo = UsuarioGrupo.objects.get(pk=usuariogrupo_id)
        UsuarioGrupoSetor.objects.filter(usuario_grupo=usuario_grupo, setor=self.setor).delete()
        servidor = usuario_grupo.user.get_vinculo().relacionamento
        CoordenadorRegistroAcademico.objects.filter(diretoria=self, servidor=servidor).update(ativo=False)
        if not CoordenadorRegistroAcademico.objects.filter(servidor=servidor, ativo=True).exists():
            usuario_grupo.delete()

    def get_termos_vinculacao_auxiliar_secretaria(self):
        return self.termovinculacaousuariodiretoria_set.filter(group__name='Auxiliar de Secretaria Acadêmica')

    def get_termos_vinculacao_estagiario_secretaria(self):
        return self.termovinculacaousuariodiretoria_set.filter(group__name='Estagiário')


class TermoVinculacaoUsuarioDiretoria(LogModel):
    responsavel = models.ForeignKeyPlus(Vinculo, on_delete=models.CASCADE)
    diretoria = models.ForeignKeyPlus(Diretoria, verbose_name='Diretoria')
    user = models.ForeignKeyPlus(User, on_delete=models.CASCADE)
    group = models.ForeignKeyPlus(Group, on_delete=models.CASCADE)
    data_hora_assinatura = models.DateTimeFieldPlus(verbose_name='Data/Hora')

    class Meta:
        verbose_name = 'Termo de Vinculação de Usuário a Diretoria'
        verbose_name_plural = 'Termos de Vinculação de Usuário a Diretoria'

    def __str__(self):
        return f'Termo {self.id}'


class CoordenadorRegistroAcademico(LogModel):
    diretoria = models.ForeignKeyPlus(Diretoria, verbose_name='Diretoria')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    numero_portaria = models.CharFieldPlus('Número da Portaria')
    eh_coordenador_registro = models.BooleanField('Coordenador de Registro Escolar?', default=False)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Responsável pela Emissão do Diploma'
        verbose_name_plural = 'Responsáveis pela Emissão do Diploma'

    def __str__(self):
        return f'{self.servidor}'

    def save(self, *args, **kwargs):
        from edu.forms import grupos

        super().save(*args, **kwargs)
        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR_REGISTROS_ACADEMICOS'], user=self.servidor.get_user())[0]
        UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=self.diretoria.setor)

    def delete(self, *args, **kwargs):
        from edu.forms import grupos

        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR_REGISTROS_ACADEMICOS'], user=self.servidor.get_user())[0]
        if CoordenadorRegistroAcademico.objects.filter(servidor=self.servidor).count() == 1:
            usuario_grupo.delete()
        UsuarioGrupoSetor.objects.filter(usuario_grupo=usuario_grupo, setor=self.diretoria.setor).delete()
        super().delete(*args, **kwargs)


class CoordenadorModalidade(LogModel):
    diretoria = models.ForeignKeyPlus(Diretoria, verbose_name='Diretoria')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    modalidades = models.ManyToManyFieldPlus('edu.Modalidade', verbose_name='Modalidades de Ensino', related_name='coordenadormodalidade_edu_set')

    class Meta:
        verbose_name = 'Coordenador de Modalidade'
        verbose_name_plural = 'Coordenadores de Modalidade'

    def __str__(self):
        return f'{self.servidor}'

    def save(self, *args, **kwargs):
        from edu.forms import grupos

        super().save(*args, **kwargs)
        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR_MODALIDADE'], user=self.servidor.get_user())[0]
        UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=self.diretoria.setor)

    def delete(self, *args, **kwargs):
        from edu.forms import grupos

        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR_MODALIDADE'], user=self.servidor.get_user())[0]
        UsuarioGrupoSetor.objects.filter(usuario_grupo=usuario_grupo, setor=self.diretoria.setor).delete()
        if CoordenadorModalidade.objects.filter(servidor=self.servidor).count() == 1:
            usuario_grupo.delete()
        super().delete(*args, **kwargs)


class CalendarioAcademico(LogModel):
    SEARCH_FIELDS = ['id', 'descricao', 'uo__sigla']

    TIPO_ANUAL = 1
    TIPO_SEMESTRAL = 2
    TIPO_TEMPORARIO = 3
    TIPO_CHOICES = [[TIPO_ANUAL, 'Anual'], [TIPO_SEMESTRAL, 'Semestral'], [TIPO_TEMPORARIO, 'Livre']]

    QTD_ETAPA_1 = 1
    QTD_ETAPA_2 = 2
    QTD_ETAPA_3 = 3
    QTD_ETAPA_4 = 4
    QTD_ETAPAS_CHOICES = [[QTD_ETAPA_1, 'Etapa Única'], [QTD_ETAPA_2, 'Duas Etapas'], [QTD_ETAPA_3, 'Três Etapas'], [QTD_ETAPA_4, 'Quatro Etapas']]

    # Managers
    objects = models.Manager()
    locals = FiltroUnidadeOrganizacionalManager('uo')

    # Dados gerais
    id = models.AutoField(verbose_name='Código', primary_key=True)
    descricao = models.CharFieldPlus(verbose_name='Descrição', width=500)
    tipo = models.PositiveIntegerField(verbose_name='Tipo', choices=TIPO_CHOICES)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', null=True, on_delete=models.CASCADE)
    diretoria = models.ForeignKeyPlus(Diretoria, verbose_name='Diretoria', null=True, blank=True, on_delete=models.CASCADE)
    ano_letivo = models.ForeignKeyPlus(
        'comum.Ano', verbose_name='Ano letivo', related_name='calendarios_por_ano_letivo_set', on_delete=models.CASCADE
    )
    periodo_letivo = models.PositiveIntegerField(verbose_name='Período letivo', choices=PERIODO_LETIVO_CHOICES)
    data_inicio = models.DateFieldPlus(verbose_name='Início das Aulas')
    data_fim = models.DateFieldPlus(verbose_name='Término das Aulas')
    data_fechamento_periodo = models.DateFieldPlus(
        verbose_name='Data de Fechamento do Período', help_text='Data limite para lançamento de notas/faltas pelos professores'
    )
    eh_calendario_referencia = models.BooleanField('Calendário de Referência?', default=False)

    # Dados das Etapas
    qtd_etapas = models.PositiveIntegerField(verbose_name='Quantidade de Etapas', choices=QTD_ETAPAS_CHOICES)

    data_inicio_etapa_1 = models.DateFieldPlus(verbose_name='Início', help_text='Data de início da primeira etapa')
    data_fim_etapa_1 = models.DateFieldPlus(verbose_name='Fim', help_text='Data de encerramento da primeira etapa')

    data_inicio_etapa_2 = models.DateFieldPlus(verbose_name='Início', help_text='Data de início da segunda etapa', null=True, blank=True)
    data_fim_etapa_2 = models.DateFieldPlus(verbose_name='Fim', help_text='Data de encerramento da segunda etapa', null=True, blank=True)

    data_inicio_etapa_3 = models.DateFieldPlus(verbose_name='Início', help_text='Data de início da terceira etapa', null=True, blank=True)
    data_fim_etapa_3 = models.DateFieldPlus(verbose_name='Fim', help_text='Data de encerramento da terceira etapa', null=True, blank=True)

    data_inicio_etapa_4 = models.DateFieldPlus(verbose_name='Início', help_text='Data de início da quarta etapa', null=True, blank=True)
    data_fim_etapa_4 = models.DateFieldPlus(verbose_name='Fim', help_text='Data de encerramento da quarta etapa', null=True, blank=True)

    data_inicio_trancamento = models.DateFieldPlus(verbose_name='Início do Trancamento', null=True, blank=True)
    data_fim_trancamento = models.DateFieldPlus(verbose_name='Encerramento do Trancamento', null=True, blank=True)

    data_inicio_certificacao = models.DateFieldPlus(verbose_name='Início da Cert. e Aproveitamento', null=True, blank=True)
    data_fim_certificacao = models.DateFieldPlus(verbose_name='Encerramento da Cert. e Aproveitamento', null=True, blank=True)

    data_inicio_trancamento2 = models.DateFieldPlus(verbose_name='Início do Trancamento', null=True, blank=True, help_text='Segundo semestre')
    data_fim_trancamento2 = models.DateFieldPlus(verbose_name='Encerramento do Trancamento', null=True, blank=True, help_text='Segundo semestre')

    data_inicio_certificacao2 = models.DateFieldPlus(
        verbose_name='Início da Cert. e Aproveitamento', null=True, blank=True, help_text='Segundo semestre'
    )
    data_fim_certificacao2 = models.DateFieldPlus(
        verbose_name='Encerramento da Cert. e Aproveitamento', null=True, blank=True, help_text='Segundo semestre'
    )

    data_inicio_prova_final = models.DateFieldPlus(verbose_name='Início da Prova Final', null=True, blank=True)
    data_fim_prova_final = models.DateFieldPlus(verbose_name='Encerramento da Prova Final', null=True, blank=True)

    data_inicio_espaco_pedagogico = models.DateFieldPlus(verbose_name='Início', null=True, blank=True)
    data_fim_espaco_pedagogico = models.DateFieldPlus(verbose_name='Fim', null=True, blank=True)

    class Meta:
        verbose_name = 'Calendário Acadêmico'
        verbose_name_plural = 'Calendários Acadêmicos'
        ordering = ('descricao',)

    def get_data_inicio_letivo(self):
        return self.data_inicio_espaco_pedagogico or self.data_inicio_etapa_1

    def get_data_fim_utlima_etapa(self):
        if self.data_fim_prova_final:
            return self.data_fim_prova_final
        data = (
            self.qtd_etapas == 1
            and self.data_fim_etapa_1
            or self.qtd_etapas == 2
            and self.data_fim_etapa_2
            or self.qtd_etapas == 3
            and self.data_fim_etapa_3
            or self.qtd_etapas == 4
            and self.data_fim_etapa_4
        )
        return somar_dias(data, 1)

    def get_absolute_url(self):
        return f'/edu/calendarioacademico/{self.pk}/'

    def __str__(self):
        return f'[{self.pk}] {self.descricao} - {self.uo.sigla}/{self.ano_letivo}.{self.periodo_letivo}'

    def mensal(self):
        return self.anual(full=False)

    def anual(self, full=True, etapas=True):
        cal = Calendario()
        cal.adicionar_tipo_evento('extra5', 'Sábado Letivo')
        for sabado_letivo in self.sabadoletivo_set.all():
            cal.adicionar_evento_calendario(sabado_letivo.sabado, sabado_letivo.sabado, str(sabado_letivo), 'extra5')
        cal.adicionar_tipo_evento('extra4', 'Data Comemorativa')
        for data_comemorativa in self.datacomemorativa_set.all():
            cal.adicionar_evento_calendario(data_comemorativa.inicio, data_comemorativa.fim, data_comemorativa.descricao, 'extra4')

        if etapas:
            data_inicio = self.data_inicio_etapa_1
            data_fim = self.data_fim_etapa_1
            descricao = '1ª Etapa'
            cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'extra')

            if self.qtd_etapas > 1:
                data_inicio = self.data_inicio_etapa_2
                data_fim = self.data_fim_etapa_2
                descricao = '2ª Etapa'
                cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'extra2')

            if self.qtd_etapas > 2:
                data_inicio = self.data_inicio_etapa_3
                data_fim = self.data_fim_etapa_3
                descricao = '3ª Etapa'
                cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'extra3')

            if self.qtd_etapas > 3:
                data_inicio = self.data_inicio_etapa_4
                data_fim = self.data_fim_etapa_4
                descricao = '4ª Etapa'
                cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'danger')

            if self.data_inicio_espaco_pedagogico and self.data_fim_espaco_pedagogico:
                data_inicio = self.data_inicio_espaco_pedagogico
                data_fim = self.data_fim_espaco_pedagogico
                descricao = 'Espaço Pedagógico'
                cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'success')

            if self.data_inicio_certificacao and self.data_fim_certificacao:
                data_inicio = self.data_inicio_certificacao
                data_fim = self.data_fim_certificacao
                descricao = 'Período para Cert. e Aproveitamento'
                cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'info')

            if self.data_inicio_trancamento and self.data_fim_trancamento:
                data_inicio = self.data_inicio_trancamento
                data_fim = self.data_fim_trancamento
                descricao = 'Período para Trancamento'
                cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'warning')

            if self.data_inicio_prova_final and self.data_fim_prova_final:
                data_inicio = self.data_inicio_prova_final
                data_fim = self.data_fim_prova_final
                descricao = 'Prova Final'
                cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'extra6')

            data_inicio = self.data_fechamento_periodo
            data_fim = self.data_fechamento_periodo
            descricao = 'Fechamento do Período'
            cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, 'extra7')

        if full:
            return cal.formato_periodo(
                self.data_inicio.month, self.data_inicio.year, self.data_fechamento_periodo.month, self.data_fechamento_periodo.year
            )
        else:
            hoje = datetime.datetime.today()

            return cal.formato_mes(hoje.year, hoje.month)

    def clean(self):
        msg = None
        try:
            if (self.data_inicio_espaco_pedagogico and self.data_fim_espaco_pedagogico is None) or (
                self.data_inicio_espaco_pedagogico is None and self.data_fim_espaco_pedagogico
            ):
                msg = ValidationError('Informe a data de início e fim do espaço pedagógico.')
            elif self.data_inicio_espaco_pedagogico and self.data_inicio_espaco_pedagogico > self.data_fim_espaco_pedagogico:
                msg = ValidationError('A data de início do espaço pedagógico não pode ser maior que a data de fim do espaço pedagógico.')
            elif self.data_fim_espaco_pedagogico and self.data_fim_espaco_pedagogico > self.data_inicio:
                msg = ValidationError('A data de fim do espaço pedagógico não pode ser maior que a data de início das aulas.')

            if self.data_inicio > self.data_fim:
                msg = ValidationError('A data de encerramento deve ser maior que a data de início.')
            if self.data_fim > self.data_fechamento_periodo:
                msg = ValidationError('A data de fechamento do período deve ser maior que a data de encerramento das aulas.')
            if self.data_inicio != self.data_inicio_etapa_1:
                msg = ValidationError('A data de início da primeira etapa deve ser igual a data de início das aulas.')
            if self.data_inicio_etapa_1 > self.data_fim_etapa_1:
                msg = ValidationError('A data de encerramento da primeira etapa deve ser superior da data de início da primeira etapa.')
            if self.qtd_etapas == CalendarioAcademico.QTD_ETAPA_2:
                if not self.data_inicio_etapa_2 or not self.data_fim_etapa_2:
                    msg = ValidationError('Preencha as datas de início e de fim da segunda etapa.')
            if self.qtd_etapas == CalendarioAcademico.QTD_ETAPA_3:
                if not self.data_inicio_etapa_2 or not self.data_fim_etapa_2:
                    msg = ValidationError('Preencha as datas de início e de fim da segunda etapa.')
                if not self.data_inicio_etapa_3 or not self.data_fim_etapa_3:
                    msg = ValidationError('Preencha as datas de início e de fim da terceira etapa.')
            if self.qtd_etapas == CalendarioAcademico.QTD_ETAPA_4:
                if not self.data_inicio_etapa_2 or not self.data_fim_etapa_2:
                    msg = ValidationError('Preencha as datas de início e de fim da segunda etapa.')
                if not self.data_inicio_etapa_3 or not self.data_fim_etapa_3:
                    msg = ValidationError('Preencha as datas de início e de fim da terceira etapa.')
                if not self.data_inicio_etapa_4 or not self.data_fim_etapa_4:
                    msg = ValidationError('Preencha as datas de início e de fim da quarta etapa.')
            if self.qtd_etapas == CalendarioAcademico.QTD_ETAPA_1:
                if self.data_fim != self.data_fim_etapa_1:
                    msg = ValidationError('A data de encerramento da primeira etapa deve ser igual a data de encerramento das aulas.')
            if self.qtd_etapas > CalendarioAcademico.QTD_ETAPA_1:
                if self.data_fim_etapa_1 > self.data_inicio_etapa_2:
                    msg = ValidationError('A data de início da segunda etapa deve ser superior a data de encerramento da primeira etapa.')
            if self.qtd_etapas > CalendarioAcademico.QTD_ETAPA_1:
                if self.data_inicio_etapa_2 > self.data_fim_etapa_2:
                    msg = ValidationError('A data de encerramento da segunda etapa deve ser superior a data de início da segunda etapa.')
            if self.qtd_etapas == CalendarioAcademico.QTD_ETAPA_2:
                if self.data_fim != self.data_fim_etapa_2:
                    msg = ValidationError('A data de encerramento da segunda etapa deve ser igual a data de encerramento das aulas.')
            if self.qtd_etapas == CalendarioAcademico.QTD_ETAPA_3:
                if self.data_fim != self.data_fim_etapa_3:
                    msg = ValidationError('A data de encerramento da terceira etapa deve ser igual a data de encerramento das aulas.')
            if self.qtd_etapas > CalendarioAcademico.QTD_ETAPA_2:
                if self.data_fim_etapa_2 > self.data_inicio_etapa_3:
                    msg = ValidationError('A data de início da terceira etapa deve ser superior a data de encerramento da segunda etapa.')
            if self.qtd_etapas > CalendarioAcademico.QTD_ETAPA_2:
                if self.data_inicio_etapa_3 > self.data_fim_etapa_3:
                    msg = ValidationError('A data de encerramento da terceira etapa deve ser superior a data de início da terceira etapa.')
            if self.qtd_etapas > CalendarioAcademico.QTD_ETAPA_3:
                if self.data_fim_etapa_3 > self.data_inicio_etapa_4:
                    msg = ValidationError('A data de início da quarta etapa deve ser superior a data de encerramento da terceira etapa.')
            if self.qtd_etapas > CalendarioAcademico.QTD_ETAPA_3:
                if self.data_inicio_etapa_4 > self.data_fim_etapa_4:
                    msg = ValidationError('A data de encerramento da quarta etapa deve ser superior a data de início da quarta etapa.')
            if self.qtd_etapas == CalendarioAcademico.QTD_ETAPA_4:
                if self.data_fim != self.data_fim_etapa_4:
                    msg = ValidationError('A data de encerramento da quarta etapa deve ser igual a data de encerramento das aulas.')
        except Exception:
            raise ValidationError('Preencha os campos obrigatórios.')
        if msg:
            raise msg

    def replicar(self, uos):
        ids = []
        modelo = self
        for uo in uos:
            if '[REPLICADO]' not in modelo.descricao:
                if len(modelo.descricao) > 240:
                    modelo.descricao = modelo.descricao[: 240 - 3] + '...'
                modelo.descricao = f'{modelo.descricao} [REPLICADO]'
            modelo.id = None
            modelo.uo = uo
            modelo.save()
            ids.append(str(modelo.id))
        return ids

    def save(self, *args, **kwargs):
        pk = self.pk
        deve_atualizar_data_posse = pk and self.deve_atualizar_data_posse()
        # selecionando professordiario que tenham o calendário acadêmico e alternando as datas das etapas
        super(self.__class__, self).save(*args, **kwargs)

        if deve_atualizar_data_posse:
            professores_diarios = ProfessorDiario.objects.filter(diario__calendario_academico=self)
            for professor_diario in professores_diarios:
                professor_diario.atualizar_data_posse()

        # definindo como calendário de referência do campus no respectivo ano caso atenda aos requisitos
        if pk is None and self.tipo == CalendarioAcademico.TIPO_ANUAL and not self.eh_calendario_referencia:
            if (
                not CalendarioAcademico.objects.filter(uo=self.uo, ano_letivo=self.ano_letivo, eh_calendario_referencia=True)
                .exclude(pk=self.pk)
                .exists()
            ):
                CalendarioAcademico.objects.filter(pk=self.pk).update(eh_calendario_referencia=True)

    def deve_atualizar_data_posse(self):
        attrs = (
            'data_inicio_etapa_1',
            'data_fim_etapa_1',
            'data_inicio_etapa_2',
            'data_fim_etapa_2',
            'data_inicio_etapa_3',
            'data_fim_etapa_3',
            'data_inicio_etapa_4',
            'data_fim_etapa_4',
            'data_inicio_prova_final',
            'data_fim_prova_final',
        )
        datas_salvas = list(CalendarioAcademico.objects.filter(pk=self.pk).values_list(*attrs).first())
        datas_atuais = [getattr(self, attr) for attr in attrs]
        return datas_salvas != datas_atuais


class SabadoLetivo(models.ModelPlus):
    calendario_academico = models.ForeignKey(CalendarioAcademico, verbose_name='Calendário Acadêmico', on_delete=models.CASCADE)
    data = models.DateFieldPlus(
        'Data de Referência',
        help_text='Informe a data a qual esse sábado corresponde caso se trate da reposição de um dia letivo. Caso se trate de um dia letivo extra, não é necessário preencher.',
        null=True,
        blank=True,
    )
    sabado = models.DateFieldPlus('Sábado Letivo', help_text='Informe o sábado no qual o dia letivo ocorrerá.')
    dia_semana = models.CharFieldPlus(
        'Dia da Semana', choices=[[x, x] for x in ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira']], null=True
    )

    class Meta:
        verbose_name = 'Sábado Letivo'
        verbose_name_plural = 'Sábados Letivos'

    def __str__(self):
        return 'Sábado letivo em "{}" correspondente a um "{}"'.format(self.sabado.strftime('%d/%m/%Y'), self.dia_semana)


class DataComemorativa(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')
    calendario_academico = models.ForeignKey(CalendarioAcademico, verbose_name='Calendário Acadêmico', on_delete=models.CASCADE)
    inicio = models.DateFieldPlus('Início')
    fim = models.DateFieldPlus('Fim')

    class Meta:
        verbose_name = 'Data Comemorativa'
        verbose_name_plural = 'Datas Comemorativas'
