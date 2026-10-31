import datetime

from django.conf import settings
from django.db.models import Q
from django.utils.text import slugify

from comum.models import Configuracao, User, UsuarioGrupo, UsuarioGrupoSetor
from djtools.db import models
from djtools.storages import get_overwrite_storage
from djtools.thumbs import ImageWithThumbsField
from djtools.utils import tooltip_text
from edu.managers import (
    ProfessorAtivoManager,
    ProfessorNaoServidorManager,
    ProfessorQuery,
    ProfessorServidorDocenteManager,
    ProfessorServidorManager,
    ProfessorServidorTecnicoManager,
)
from edu.models.cadastros_gerais import CursoFormacaoSuperior, GrupoAtuacao, HorarioAulaDiario, HorarioCampus, Turno
from edu.models.estagio_docente import EstagioDocente
from edu.models.logs import LogModel
from edu.models.projeto_final import ProjetoFinal
from rh.models import PessoaFisica, Servidor

# Quem emite a declaração de vínculo docente de outro professor (``Professor.pode_emitir_declaracao_docencia``).
GRUPOS_DECLARACAO_DOCENCIA_SISTEMICOS = ['Administrador Acadêmico', 'Diretor Acadêmico Sistêmico', 'Diretor de Avaliação e Regulação do Ensino']
GRUPOS_DECLARACAO_DOCENCIA_CAMPUS = [
    'Diretor Acadêmico',
    'Diretor Geral',
    'Secretário Acadêmico',
    'Coordenador de Registros Acadêmicos',
    'Coordenador de Curso',
]


class Professor(LogModel):
    SEARCH_FIELDS = [
        'vinculo__pessoa__pessoafisica__search_fields_optimized',
    ]

    GRUPOS_ACESSO_SISTEMICO = ['Administrador Acadêmico', 'Diretor de Avaliação e Regulação do Ensino', 'Operador de Censo']

    # Managers
    objects = ProfessorQuery().as_manager()
    ativos = ProfessorAtivoManager()
    servidores_docentes = ProfessorServidorDocenteManager()
    servidores_tecnicos = ProfessorServidorTecnicoManager()
    nao_servidores = ProfessorNaoServidorManager()
    servidores = ProfessorServidorManager()
    # Fields
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vínculo', on_delete=models.CASCADE, null=False)

    disciplina = models.ForeignKeyPlus('edu.Disciplina', verbose_name='Disciplina de Ingresso', null=True, blank=True, on_delete=models.CASCADE)
    nce = models.ManyToManyFieldPlus('edu.NucleoCentralEstruturante', verbose_name='Núcleo Central Estruturante', blank=True)
    ch_sala_aula_semanal = models.IntegerField(
        verbose_name='CH Sala de Aula Semanal',
        null=True,
        blank=True,
        help_text='Quantidade mínima de horas que o professor deve atuar em sala de aula por semana.',
    )

    TIPO_FIC = 1
    TIPO_CURSO_REGULAR = 2
    TIPO_CHOICES = [
        [TIPO_FIC, 'FIC'],
        [TIPO_CURSO_REGULAR, 'Curso Regular'],
    ]

    TITULACAO_CHOICES = [
        ['Graduado', 'Graduado'],
        ['Graduada', 'Graduada'],
        ['Especialista', 'Especialista'],
        ['Mestre', 'Mestre'],
        ['Mestra', 'Mestra'],
        ['Doutor', 'Doutor'],
        ['Doutora', 'Doutora'],
        ['Pós-Doutor', 'Pós-Doutor'],
        ['Pós-Doutora', 'Pós-Doutora'],
    ]
    AREA_ULTIMA_TITULACAO_CHOICES = [
        ['99', 'Programas básicos'],
        ['01', 'Educação'],
        ['02', 'Artes e humanidades'],
        ['03', 'Ciências sociais, comunicação e informação'],
        ['04', 'Negócios, administração e direito'],
        ['05', 'Ciências naturais, matemática e estatística'],
        ['06', 'Computação e Tecnologias da Informação e Comunicação (TIC)'],
        ['07', 'Engenharia, produção e construção'],
        ['08', 'Agricultura, silvicultura, pesca e veterinária'],
        ['09', 'Saúde e bem-estar'],
        ['10', 'Serviços'],
    ]
    tipo = models.IntegerField('Tipo', choices=TIPO_CHOICES, blank=False, default=2)
    titulacao = models.CharFieldPlus('Titulação', choices=TITULACAO_CHOICES, null=True, blank=True)
    ultima_instituicao_de_titulacao = models.CharFieldPlus('Instituição onde recebeu a última titulação', null=True, blank=True)
    area_ultima_titulacao = models.CharFieldPlus('Área da Última Titulação', null=True, blank=True, choices=AREA_ULTIMA_TITULACAO_CHOICES)
    ano_ultima_titulacao = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano da Última Titulação', null=True, blank=True, on_delete=models.CASCADE)
    vinculo_professor_ead = models.ForeignKeyPlus(
        'edu.VinculoProfessorEAD', verbose_name='Vinculo do Professor com o EAD', null=True, blank=True, on_delete=models.CASCADE
    )

    ano_inicio_curso_superior = models.IntegerField('Ano de Início do Curso Superior', null=True, blank=True)
    ano_conclusao_curso_superior = models.IntegerField('Ano de Conclusão do Curso Superior', null=True, blank=True)
    possui_formacao_complementar = models.BooleanField('Possui formação/complementação pedagógica', default=False)
    codigo_curso_superior = models.CharFieldPlus('Código do Curso Superior', null=True, blank=True)
    curso_superior = models.ForeignKeyPlus(CursoFormacaoSuperior, verbose_name='Curso Superior', null=True, blank=True, on_delete=models.CASCADE)
    instituicao_ensino_superior = models.ForeignKeyPlus(
        'edu.InstituicaoEnsinoSuperior', verbose_name='Instituição de Ensino Superior', null=True, blank=True
    )

    foto = ImageWithThumbsField(
        storage=get_overwrite_storage(), use_id_for_name=True, upload_to='professores', sizes=((75, 100), (150, 200)), null=True, blank=True
    )

    cursos_lecionados = models.ManyToManyFieldPlus('edu.CursoCampus', verbose_name='Cursos Lecionados')
    codigo_sgp = models.IntegerField(null=True, db_index=True, blank=True)

    # Metadata
    class Meta:
        verbose_name = 'Professor'
        verbose_name_plural = 'Professores'
        ordering = ('vinculo__pessoa__nome',)
        permissions = (
            ('pode_ver_cpf_professor', 'Pode visualizar o CPF do professor'),
            ('eh_professor', 'É professor'),
        )

    EXT_COMBO_RELATED = {
        'select_related': ['vinculo', 'vinculo__pessoa', 'vinculo__pessoa__pessoafisica', 'vinculo__user'],
        'prefetch_related': [],
    }

    def __str__(self):
        return f'{self.get_nome()} ({self.get_matricula()})'

    def can_change(self, user):
        if user.has_perm('edu.change_professor'):
            if UsuarioGrupo.objects.filter(user=user, group__name__in=Professor.GRUPOS_ACESSO_SISTEMICO).exists():
                return True
            if (
                self.vinculo.setor
                and UsuarioGrupoSetor.objects.filter(
                    usuario_grupo__user=user, setor__uo_id=self.vinculo.setor.uo_id, usuario_grupo__group__permissions__codename='change_professor'
                ).exists()
            ):
                return True
        return False

    def pode_emitir_declaracao_docencia(self, user: User) -> bool:
        """Indica se ``user`` pode emitir a declaração de vínculo docente deste professor (documento autenticado com CPF).

        Podem o próprio professor, a gestão acadêmica (decisão na #17725) e o RH (como em
        ``UnidadeOrganizacional.can_change``). Administrador Acadêmico, Diretor Acadêmico Sistêmico, Diretor de
        Avaliação e Regulação do Ensino e ``rh.eh_rh_sistemico`` alcançam qualquer campus; Diretor Acadêmico, Diretor
        Geral, Secretário Acadêmico, Coordenador de Registros Acadêmicos, Coordenador de Curso e ``rh.eh_rh_campus``, só
        o campus do professor (o do setor SUAP do vínculo, dos dois lados).
        """
        if not user.is_authenticated:
            return False
        if self.vinculo.user_id == user.id:
            return True
        if user.has_group_cached(GRUPOS_DECLARACAO_DOCENCIA_SISTEMICOS) or user.has_perm('rh.eh_rh_sistemico'):
            return True
        vinculo_usuario = user.get_vinculo()
        uo_usuario = vinculo_usuario and vinculo_usuario.setor and vinculo_usuario.setor.uo_id
        if not uo_usuario or uo_usuario != (self.vinculo.setor and self.vinculo.setor.uo_id):
            return False
        return user.has_group_cached(GRUPOS_DECLARACAO_DOCENCIA_CAMPUS) or user.has_perm('rh.eh_rh_campus')

    def get_programas_pos_lato_sensu(self):
        return self.docenteprogramapos_set.filter(programa__nivel='lato_sensu')

    def get_programas_pos_stricto_sensu(self):
        return self.docenteprogramapos_set.filter(programa__nivel='stricto_sensu')

    def get_vinculo(self):
        return self.vinculo

    def get_materiais_aula_outros_vinculos(self):
        from edu.models.diarios import MaterialAula

        pessoa_fisica = PessoaFisica.objects.get(pk=self.vinculo.pessoa_id)
        descricoes = self.materialaula_set.values_list('descricao', flat=True)
        return (
            MaterialAula.objects.exclude(professor_id=self.pk)
            .filter(professor__vinculo__pessoa__pessoafisica__cpf=pessoa_fisica.cpf)
            .exclude(descricao__in=descricoes)
        )

    def requer_pit_no_periodo(self, ano, periodo):
        requer_pit = True
        data_inicio_exercicio_no_cargo = (
            Servidor.objects.filter(matricula=self.get_matricula()).values_list('data_inicio_exercicio_no_cargo', flat=True).first()
        )
        if data_inicio_exercicio_no_cargo:
            if periodo == 2:
                mes = 1
                ano += 1
            else:
                mes = 7
            if data_inicio_exercicio_no_cargo > datetime.date(ano, mes, 1):
                requer_pit = False
        return requer_pit

    def get_titulacao(self):
        titulacao = None
        if self.titulacao:
            titulacao = self.titulacao
        elif self.vinculo.eh_servidor():
            titulacao = self.vinculo.relacionamento.get_titulacao()
        return titulacao

    def get_qtd_alunos(self):
        from edu.models import MatriculaDiario

        return MatriculaDiario.objects.filter(diario__professordiario__professor=self, situacao=MatriculaDiario.SITUACAO_CURSANDO).count()

    def get_qtd_diarios(self):
        from edu.models import CursoCampus, Diario

        ano_letivo = getattr(self, 'ano_letivo_informado', None)
        periodo_letivo = getattr(self, 'periodo_letivo_informado', None)

        if ano_letivo and periodo_letivo:
            qs = Diario.objects.filter(professordiario__professor=self)
            qs1 = qs.filter(turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, ano_letivo=ano_letivo)
            qs2 = qs.filter(
                turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo
            )
            return qs1.count() + qs2.count()
        return None

    def get_ch_semanal(self):
        ano_letivo = getattr(self, 'ano_letivo_informado', None)
        periodo_letivo = getattr(self, 'periodo_letivo_informado', None)
        if ano_letivo and periodo_letivo:
            ch_semanal_efetiva = 0
            for professor_diario in self.get_vinculo_diarios(ano_letivo.ano, periodo_letivo, False, None, False):
                ch_diario = professor_diario.get_qtd_creditos_efetiva(periodo_letivo)
                componente = professor_diario.diario.componente_curricular.componente
                ch_semanal_efetiva += ch_diario * componente.get_ch_hora_relogio() / componente.get_ch_hora_aula() if componente.ch_hora_aula else 0
            return ch_semanal_efetiva
        return None

    def get_qtd_diarios_total(self):
        ano_letivo = getattr(self, 'ano_letivo_informado', None)
        periodo_letivo = getattr(self, 'periodo_letivo_informado', None)
        if ano_letivo and periodo_letivo:
            qs_diarios = self.get_vinculo_diarios(ano_letivo.ano, periodo_letivo, fic=False) | self.get_vinculo_diarios(
                ano_letivo.ano, periodo_letivo, fic=True
            )
            vinculos_turmas_minicurso = self.get_vinculos_minicurso(ano_letivo.ano, periodo_letivo)
            diarios_especiais = self.get_vinculos_diarios_especiais(ano_letivo.ano, periodo_letivo)
            return qs_diarios.count() + vinculos_turmas_minicurso.count() + diarios_especiais.count()
        return None

    def get_ch_total(self):
        ano_letivo = getattr(self, 'ano_letivo_informado', None)
        periodo_letivo = getattr(self, 'periodo_letivo_informado', None)
        if 'pit_rit_v2' in settings.INSTALLED_APPS:
            from pit_rit_v2.models import PlanoIndividualTrabalhoV2

            if ano_letivo and periodo_letivo and ano_letivo.ano >= PlanoIndividualTrabalhoV2.ANO_INICIO_APP:
                qs_relatorios = PlanoIndividualTrabalhoV2.objects.filter(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo, professor=self)
                if qs_relatorios.exists():
                    pit = qs_relatorios.first()
                    if pit:
                        return pit.get_ch_total_aulas()
        return None

    def get_ch_total_pit(self):
        ano_letivo = getattr(self, 'ano_letivo_informado', None)
        periodo_letivo = getattr(self, 'periodo_letivo_informado', None)
        if 'pit_rit_v2' in settings.INSTALLED_APPS:
            from pit_rit_v2.models import PlanoIndividualTrabalhoV2

            if ano_letivo and periodo_letivo and ano_letivo.ano >= PlanoIndividualTrabalhoV2.ANO_INICIO_APP:
                qs_relatorios = PlanoIndividualTrabalhoV2.objects.filter(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo, professor=self)
                if qs_relatorios.exists():
                    pit = qs_relatorios.first()
                    if pit:
                        return pit.get_ch_total_semanal()
        return None

    def is_servidor(self):
        return self.vinculo.eh_servidor()

    def get_matricula(self):
        if self.vinculo:
            return self.vinculo.user and self.vinculo.user.username or self.vinculo.relacionamento.pessoa_fisica.cpf
        return None

    def get_horarios_aula_por_horario_campus(self, ano, periodo):
        horarios_campi = HorarioCampus.objects.filter(diario__professordiario__professor=self, diario__ano_letivo__ano=ano).distinct()
        result = []
        for horario_campus in horarios_campi:
            horario_campus.turnos = self.get_horarios_aula_por_turno(ano, periodo, horario_campus)
            result.append(horario_campus)
        return result

    def get_horarios_aula_por_turno(self, ano, periodo, horario_campus=None):
        from edu.models.cursos import CursoCampus
        from edu.models.diarios import Diario

        dias_semana = HorarioAulaDiario.DIA_SEMANA_CHOICES
        if horario_campus:
            horarios_campus_ids = [horario_campus.pk]
        else:
            horarios_campus_ids = Diario.objects.filter(professordiario__professor=self, professordiario__ativo=True).values_list(
                'horario_campus__id', flat=True
            )
        turnos_ids = HorarioCampus.objects.filter(id__in=horarios_campus_ids).values_list('horarioaula__turno__id', flat=True)
        turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')
        for turno in turnos:
            turno.horarios_aula = []
            turno.dias_semana = dias_semana
            turno.vazio = True
            for horario_aula in turno.horarioaula_set.filter(horario_campus__id__in=horarios_campus_ids).order_by('-id').order_by('inicio'):
                horario_aula.dias_semana = []
                horario_aula.vazio = True
                for dia_semana in dias_semana:
                    numero = dia_semana[0]
                    nome = dia_semana[1]
                    marcado = False
                    sigla = ''

                    qs_horarios = HorarioAulaDiario.objects.filter(
                        diario__professordiario__professor=self,
                        diario__professordiario__ativo=True,
                        dia_semana=dia_semana[0],
                        horario_aula=horario_aula,
                        diario__ano_letivo__ano=ano,
                    )
                    qs_horarios_semestrais = qs_horarios.filter(diario__periodo_letivo=periodo).exclude(
                        diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL
                    )
                    qs_horarios_anuais = qs_horarios.filter(diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL)
                    # excluíndo os diários semestrais em cursos anuais
                    if periodo == 1:
                        qs_horarios_anuais = qs_horarios_anuais.exclude(diario__segundo_semestre=True)
                    else:
                        qs_horarios_anuais = qs_horarios_anuais.exclude(
                            diario__segundo_semestre=False, diario__componente_curricular__qtd_avaliacoes=2
                        )
                    qs = qs_horarios_semestrais | qs_horarios_anuais

                    if qs.exists():
                        marcado = True
                        turno.vazio = False
                        horario_aula.vazio = False
                        sigla = ''
                        for diario in Diario.objects.filter(id__in=qs.values_list('diario__id', flat=True)):
                            sigla += tooltip_text(
                                f'({diario.id})-{diario.componente_curricular.componente.sigla} ',
                                diario.componente_curricular.componente.descricao_historico,
                            )
                        horario_aula.dias_semana.append(
                            {'numero': numero, 'nome': nome, 'marcado': marcado, 'sigla': sigla, 'horarios_aula_diario': qs}
                        )
                    else:
                        horario_aula.dias_semana.append(
                            {'numero': numero, 'nome': nome, 'marcado': marcado, 'sigla': sigla, 'horarios_aula_diario': []}
                        )
                turno.horarios_aula.append(horario_aula)
        return turnos

    def get_uo(self):
        try:
            if not self.vinculo.ativo:
                return Servidor.objects.get(pessoa_fisica__id=self.vinculo.pessoa.id).setor_lotacao.uo.equivalente
            return self.vinculo.setor.uo
        except Exception:
            return None

    def get_disciplina(self):
        try:
            return self.disciplina
        except Exception:
            return None

    def get_nome(self):
        return self.vinculo and self.vinculo.pessoa.nome or None

    def get_sigla_diretoria(self):
        return self.professordiario_set.order_by('pk').values_list('diario__turma__curso_campus__diretoria__setor__sigla', flat=True).first()

    def get_nome_usual(self):
        return self.vinculo and self.vinculo.pessoa.nome_usual or None

    def get_foto_75x100_url(self):
        return (
            self.foto
            and self.foto.url_75x100
            or self.vinculo
            and self.vinculo.foto
            and self.vinculo.foto.url_75x100
            or '/static/comum/img/default.jpg'
        )

    def get_foto_75x100_url_publica(self):
        retorno = (
            self.foto
            and self.foto.get_url_publica('75x100')
            or self.vinculo
            and self.vinculo.foto
            and self.vinculo.foto.get_url_publica('75x100')
            or '/static/comum/img/default.jpg'
        )
        return f'{settings.SITE_URL}{retorno}'

    def get_foto_150x200_url(self):
        return (
            self.foto
            and self.foto.url_150x200
            or self.vinculo
            and self.vinculo.foto
            and self.vinculo.foto.url_150x200
            or '/static/comum/img/default.jpg'
        )

    def get_foto_150x200_url_publica(self):
        retorno = (
            self.foto
            and self.foto.get_url_publica('150x200')
            or self.vinculo
            and self.vinculo.foto
            and self.vinculo.foto.get_url_publica('150x200')
            or '/static/comum/img/default.jpg'
        )
        return f'{settings.SITE_URL}{retorno}'

    def get_absolute_url(self):
        return f'/edu/professor/{self.pk:d}/'

    def get_slug_from_email(self):
        vinculo = self.get_vinculo()
        if vinculo and vinculo.email_notificacao:
            email_prefix = vinculo.email_notificacao.split('@')[0]
            nome_com_hifen = email_prefix.replace('.', '-')
            return slugify(nome_com_hifen)
        return None

    def get_telefones(self):
        if self.vinculo.setor and self.vinculo.setor.setortelefone_set.exists():
            return self.vinculo.setor.setortelefone_set.values_list('numero', flat=True)
        return []

    def get_qtd_orientacoes_estagio(self):
        from estagios.models import Aprendizagem, AtividadeProfissionalEfetiva, PraticaProfissional

        return (
            EstagioDocente.objects.filter(professor_orientador__vinculo__id=self.vinculo.pk)
            .exclude(situacao__in=[EstagioDocente.SITUACAO_ENCERRADO, EstagioDocente.SITUACAO_NAO_CONCLUIDO])
            .count()
            + PraticaProfissional.objects.filter(orientador__vinculo__id=self.vinculo.pk)
            .exclude(status__in=[PraticaProfissional.STATUS_CONCLUIDO, PraticaProfissional.STATUS_RESCINDIDO])
            .count()
            + Aprendizagem.objects.filter(orientador__vinculo__id=self.vinculo.pk).exclude(data_encerramento__isnull=False).count()
            + self.atividadeprofissionalefetiva_set.exclude(
                situacao__in=[AtividadeProfissionalEfetiva.CONCLUIDA, AtividadeProfissionalEfetiva.NAO_CONCLUIDA]
            ).count()
        )

    def get_qtd_estagios_nao_visitados(self):
        return (
            EstagioDocente.objects.filter(professor_orientador__vinculo__id=self.vinculo.pk)
            .exclude(visitaestagiodocente__isnull=False)
            .exclude(situacao__in=[EstagioDocente.SITUACAO_MUDANCA, EstagioDocente.SITUACAO_NAO_CONCLUIDO, EstagioDocente.SITUACAO_NAO_CONCLUIDO])
            .count()
            + self.get_estagios_em_andamento().filter(pendente_visita=True).count()
            + self.get_aprendizagens_em_andamento()
            .exclude(
                Q(moduloaprendizagem__visitaaprendizagem__isnull=False) | Q(moduloaprendizagem__justificativavisitamoduloaprendizagem__isnull=False)
            )
            .distinct()
            .count()
        )

    def get_anos_com_orientacao_tcc(self):
        return self.orientador_set.values_list('matricula_periodo__ano_letivo__ano', flat=True).distinct()

    def get_anos_com_orientacao_estagios(self):
        estagios = self.praticaprofissional_set.order_by('-data_inicio')
        anos = set()
        for estagio in estagios:
            periodo = estagio.get_periodo_duracao()
            anos = anos | set(range(periodo[0].year, periodo[1].year + 1))
        return sorted(self.excluir_anos_maiores_que_ano_atual(anos), reverse=True)

    def get_anos_com_orientacao_aprendizagens(self):
        aprendizagens = self.aprendizagem_set.order_by('-moduloaprendizagem__inicio')
        anos = set()
        for aprendizagem in aprendizagens:
            periodo = aprendizagem.get_periodo_duracao()
            anos = anos | set(range(periodo[0].year, periodo[1].year + 1))
        return sorted(self.excluir_anos_maiores_que_ano_atual(anos), reverse=True)

    def get_anos_com_orientacao_estagios_docentes(self):
        estagios = self.estagiodocente_orientador_set.order_by('-data_inicio')
        anos = set()
        for estagio in estagios:
            periodo = estagio.get_periodo_duracao()
            if periodo[0] and periodo[1]:
                anos = anos | set(range(periodo[0].year, periodo[1].year + 1))
        return sorted(self.excluir_anos_maiores_que_ano_atual(anos), reverse=True)

    def get_anos_com_orientacao_atividades_profissionais_efetivas(self):
        atividades_profissionais_efetivas = self.atividadeprofissionalefetiva_set.order_by('-inicio')
        anos = set()
        for atividade_profissional_efetiva in atividades_profissionais_efetivas:
            periodo = atividade_profissional_efetiva.get_periodo_duracao()
            if periodo[0] and periodo[1]:
                anos = anos | set(range(periodo[0].year, periodo[1].year + 1))
        return sorted(self.excluir_anos_maiores_que_ano_atual(anos), reverse=True)

    def excluir_anos_maiores_que_ano_atual(self, anos):
        return [x for x in anos if x <= datetime.date.today().year]

    def get_anos_com_diarios(self):
        return self.professordiario_set.values_list('diario__ano_letivo__ano', flat=True).distinct()

    def get_estagios_em_andamento(self):
        from estagios.models import PraticaProfissional

        return self.praticaprofissional_set.exclude(status__in=[PraticaProfissional.STATUS_CONCLUIDO, PraticaProfissional.STATUS_RESCINDIDO])

    def get_estagios_encerrados(self):
        from estagios.models import PraticaProfissional

        return self.praticaprofissional_set.filter(status__in=[PraticaProfissional.STATUS_CONCLUIDO, PraticaProfissional.STATUS_RESCINDIDO])

    def get_aprendizagens_em_andamento(self):
        return self.aprendizagem_set.exclude(data_encerramento__isnull=False)

    def get_aprendizagens_encerradas(self):
        return self.aprendizagem_set.filter(data_encerramento__isnull=False)

    def get_participacoes_em_bancas(
        self, ano_letivo=None, periodo_letivo=None, tipo=None, data_inicio=None, data_fim=None, ordenar_por='resultado_data', tipo_ordenacao=''
    ):
        qs = ProjetoFinal.objects.all()
        if ano_letivo:
            qs = qs.filter(matricula_periodo__ano_letivo__ano=ano_letivo)
        if periodo_letivo:
            qs = qs.filter(matricula_periodo__periodo_letivo=periodo_letivo)
        if tipo:
            qs = qs.filter(tipo=tipo)
        if data_inicio:
            qs = qs.filter(resultado_data__gte=data_inicio)
        if data_fim:
            qs = qs.filter(resultado_data__lte=data_fim)
        ordenar_por = f'{tipo_ordenacao}{ordenar_por}'

        projetos_presididos = qs.filter(presidente=self).order_by(ordenar_por)
        projetos_examinados = qs.filter(
            models.Q(examinador_interno__pk=self.vinculo.pk)
            | models.Q(examinador_externo__pk=self.vinculo.pk)
            | models.Q(terceiro_examinador__pk=self.vinculo.pk)
        ).order_by(ordenar_por)

        return projetos_presididos, projetos_examinados

    def get_vinculo_diarios(self, ano_letivo, periodo_letivo, fic=None, ativo=None, financiamento_externo=None):
        from edu.models import CursoCampus, Modalidade

        professor_diarios = self.professordiario_set.filter(
            diario__ano_letivo__ano=ano_letivo, diario__periodo_letivo=periodo_letivo
        ) | self.professordiario_set.filter(
            diario__ano_letivo__ano=ano_letivo, diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL
        )

        if periodo_letivo == 2:
            professor_diarios = professor_diarios.exclude(
                diario__calendario_academico__qtd_etapas=4, diario__componente_curricular__qtd_avaliacoes=2, diario__segundo_semestre=False
            )
        else:
            professor_diarios = professor_diarios.exclude(
                diario__calendario_academico__qtd_etapas=4, diario__componente_curricular__qtd_avaliacoes=2, diario__segundo_semestre=True
            )

        if ativo is not None:
            professor_diarios = professor_diarios.filter(ativo=ativo)

        if financiamento_externo is not None:
            professor_diarios = professor_diarios.filter(financiamento_externo=financiamento_externo)

        if fic is not None:
            if fic:
                professor_diarios = professor_diarios.filter(diario__turma__curso_campus__modalidade=Modalidade.FIC)
            else:
                professor_diarios = professor_diarios.exclude(diario__turma__curso_campus__modalidade=Modalidade.FIC)

        return professor_diarios

    def get_vinculos_minicurso(self, ano_letivo, periodo_letivo):
        return self.professorminicurso_set.filter(turma_minicurso__ano_letivo__ano=ano_letivo, turma_minicurso__periodo_letivo=periodo_letivo)

    def get_vinculos_diarios_especiais(self, ano_letivo, periodo_letivo, is_cap=None):
        if is_cap is None:
            return self.diarioespecial_set.filter(ano_letivo__ano=ano_letivo, periodo_letivo=periodo_letivo)
        else:
            return self.diarioespecial_set.filter(ano_letivo__ano=ano_letivo, periodo_letivo=periodo_letivo, is_centro_aprendizagem=is_cap)


class ParticipacaoGrupoAtuacao(models.ModelPlus):
    professor = models.ForeignKey(Professor, verbose_name='Professor', on_delete=models.CASCADE)
    grupo_atuacao = models.ForeignKey(GrupoAtuacao, verbose_name='Grupo de Atuação', on_delete=models.CASCADE)
    percentual = models.IntegerField('Percentual')

    class Meta:
        verbose_name = 'Participação em Grupo de Atuação'
        verbose_name_plural = 'Participações em Grupo de Atuação'

    def __str__(self):
        return f'Participação do professor {self.professor} no grupo de atuação {self.grupo_atuacao}'


class ConfiguracaoDadosDocentes(models.Model):
    EXIBICAO_MINIMA = 'MINIMA'
    EXIBICAO_COMPLETA = 'COMPLETA'

    EXIBICAO_CHOICES = [
        (EXIBICAO_MINIMA, 'Exibir apenas meu nome, disciplina e campus'),
        (EXIBICAO_COMPLETA, 'Exibir meu nome, disciplina, campus, materiais de aula e outras informações configuradas por mim'),
    ]

    professor = models.OneToOneField('edu.Professor', on_delete=models.CASCADE, related_name='config_dados_docentes', verbose_name='Professor')

    modo_exibicao = models.CharField(
        max_length=20,
        choices=EXIBICAO_CHOICES,
        null=True,
        blank=True,
        verbose_name='Como você deseja que seus dados sejam exibidos no portal institucional?',
    )

    # Campos adicionais habilitados quando modo_exibicao = COMPLETA
    exibir_foto = models.BooleanField(default=False, verbose_name='Exibir foto?')
    exibir_email = models.BooleanField(default=False, verbose_name='Exibir e-mail institucional?')
    exibir_lattes = models.BooleanField(
        default=False,
        verbose_name='Exibir dados do Currículo Lattes?',
        help_text='Serão exibidos: biografia, formação acadêmica, grande área e área de atuação, ⁠grupos de pesquisa, ⁠publicações, ⁠produções bibliográficas, ⁠produções técnicas, ⁠projetos, ⁠prêmios e títulos, e ⁠link para currículo lattes completo.',
    )

    instagram_url = models.URLField(blank=True, null=True, verbose_name='Instagram')
    facebook_url = models.URLField(blank=True, null=True, verbose_name='Facebook')
    youtube_url = models.URLField(blank=True, null=True, verbose_name='YouTube')
    linkedin_url = models.URLField(blank=True, null=True, verbose_name='LinkedIn')
    spotify_url = models.URLField(blank=True, null=True, verbose_name='Spotify')

    # Termos de responsabilidade
    atesto_responsabilidade_autor = models.BooleanField(
        default=False,
        verbose_name='Atesto que sou o único responsável pela publicação dos dados pessoais não institucionais presentes na minha página.',
    )
    atesto_responsabilidade_terceiros = models.BooleanField(
        default=False, verbose_name='Atesto que não devo publicar dados pessoais de terceiros na minha página.'
    )
    atesto_responsabilidade_instituicao = models.BooleanField(
        default=False,
        verbose_name='Atesto que as informações publicadas na minha página têm relação direta e exclusiva com a minha atuação na instituição.',
    )

    datahora_publicacao = models.DateTimeField(
        auto_now=True, verbose_name='Data e hora do último salvamento para publicação no Portal Institucional.'
    )

    class Meta:
        verbose_name = 'Configuração de dados docentes para publicação'
        verbose_name_plural = 'Configurações de dados docentes para publicação'

    def __str__(self):
        return f'Configuração de dados docentes de {self.professor.get_nome_usual()}'

    @property
    def get_url_portal(self):
        slug = self.professor.get_slug_from_email()
        if not slug:
            return None
        prefixo_pagina_docentes_portal = Configuracao.get_valor_por_chave('edu', 'prefixo_pagina_docentes_portal')
        if not prefixo_pagina_docentes_portal:
            return None
        return f'{prefixo_pagina_docentes_portal}{slug}/'

    @property
    def is_exibicao_completa(self):
        return self.modo_exibicao == self.EXIBICAO_COMPLETA
