import datetime
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpRequest
from django.shortcuts import reverse
from django.template.defaultfilters import pluralize

from comum.models import Configuracao, User, UsuarioGrupoSetor, Vinculo
from djtools import documentos, layout
from djtools.utils import (
    rtr,
)
from edu.forms import BuscaAlunoForm, BuscaCalendarioForm, BuscaDiarioForm, BuscaMatrizForm
from edu.models import (
    AberturaExtemporanea,
    AbonoFaltas,
    Acolhimento,
    AlteracaoRespostaJustificativaCensup,
    Aluno,
    AssinaturaAtaEletronica,
    AtividadeAprofundamento,
    AtividadeComplementar,
    AtividadeCurricularExtensao,
    AtividadePraticaProfissional,
    AtoRegulatorioCurso,
    AuditoriaEnsino,
    Aula,
    CalendarioAcademico,
    CursoCampus,
    Diario,
    Diretoria,
    EstagioDocente,
    MatriculaDiario,
    Mensagem,
    Modalidade,
    NadaConsta,
    NivelEnsino,
    ParticipanteEvento,
    PedidoMatriculaDiario,
    PeriodoLetivoAtual,
    PlanoEnsino,
    Professor,
    ProfessorDiario,
    ProjetoFinal,
    Requerimento,
    RequerimentoAproveitamentoEstudo,
    RespostaEducacenso,
    RespostaJustificativaCensup,
    SituacaoMatricula,
    SolicitacaoAproveitamentoEstudo,
    SolicitacaoAssinaturaEletronica,
    SolicitacaoCertificadoENEM,
    Trabalho,
    Turma,
)
from edu.models.nada_consta import ItemConfiguracaoNadaConsta
from rh.models import Situacao


def _eh_docente_ativo(vinculo: Vinculo) -> bool:
    if not vinculo.eh_servidor():
        return False

    servidor = vinculo.relacionamento
    return bool(servidor.ativo and servidor.eh_docente and servidor.situacao and servidor.situacao.codigo in Situacao.SITUACOES_ATIVOS)


@documentos.emissao_documentos()
def emissao_documentos(request, data):
    participacoes = None
    professor = None
    alunos = None
    vinculo = request.user.get_vinculo()
    if vinculo:
        participacoes = ParticipanteEvento.objects.filter(participante__id=vinculo.id)
        professor = Professor.objects.filter(vinculo_id=vinculo.id).first()
        alunos = Aluno.objects.filter(pessoa_fisica_id=vinculo.pessoa.id)
    for participacao in participacoes:
        data.append(
            (
                'Ensino',
                'Palestras e Eventos',
                'Comprovante de Participação',
                participacao.evento,
                f'/edu/imprimir_certificado_participacao_evento/{participacao.pk}/',
            )
        )

    if professor:
        projetos_presididos, projetos_examinados = professor.get_participacoes_em_bancas()
        for projeto in projetos_presididos:
            data.append(
                (
                    'Ensino',
                    'Defesa de TCC / Projeto Final',
                    'Comprovante de Participação',
                    projeto,
                    f'/edu/declaracao_participacao_projeto_final_pdf/{projeto.pk}/presidente/',
                )
            )
        for projeto in projetos_examinados:
            data.append(
                (
                    'Ensino',
                    'Defesa de TCC / Projeto Final',
                    'Comprovante de Participação',
                    projeto,
                    f'/edu/declaracao_participacao_projeto_final_pdf/{projeto.pk}/{projeto.get_tipo_examinador(vinculo)}/',
                )
            )
    for aluno in alunos:
        for descricao, url in aluno.get_urls_documentos():
            data.append(('Ensino', 'Documentos Acadêmicos', aluno.curso_campus.descricao, descricao, url))


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []
    if PlanoEnsino.objects.exists():
        servicos_anonimos.append({'categoria': 'Ensino', 'url': '/edu/planoensino_public/', 'icone': 'file', 'titulo': 'Planos de Ensino'})
    servicos_anonimos.append({'categoria': 'Acessos', 'url': '/edu/acesso_responsavel/', 'icone': 'passport', 'titulo': 'Acesso do responsável'})
    servicos_anonimos.append(
        {'categoria': 'Ferramentas', 'url': '/comum/autenticar_documento/', 'icone': 'lock', 'titulo': 'Verificação de autenticação de documento'}
    )
    servicos_anonimos.append(
        {'categoria': 'Ensino', 'url': '/comum/validar_assinatura/', 'icone': 'lock', 'titulo': 'Validação de assinatura digital'}
    )
    servicos_anonimos.append(
        {'categoria': 'Ensino', 'url': '/edu/autenticar_certificado_minicurso/', 'icone': 'lock', 'titulo': 'Certificados de Minicursos'}
    )
    servicos_anonimos.append(
        {'categoria': 'Ensino', 'url': '/edu/solicitar_certificado_enem/', 'icone': 'certificate', 'titulo': 'Certificação ENEM'}
    )
    servicos_anonimos.append(
        {'categoria': 'Ensino', 'url': '/edu/registroemissaodiploma_public/', 'icone': 'certificate', 'titulo': 'Registro de diplomas'}
    )

    return servicos_anonimos


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Lista pendências acadêmicas atribuídas ao usuário logado.

    Reúne avisos para o aluno (logradouro, declaração CPC/SAES, matrícula
    online, renovação automática, frequência, plano individual de estudos,
    questionários de inscrição e procuração) e para o servidor (requerimentos
    para apreciar/encaminhar/responder, segundo o perfil).

    Args:
        request: requisição HTTP usada para identificar o usuário e seu vínculo.

    Returns:
        list[dict]: pendências em formato de cartão; lista vazia quando não há nenhuma.
    """
    pendencias = []
    usuario = request.user
    if usuario.eh_aluno:
        aluno = usuario.get_relacionamento()
        if not aluno.logradouro:
            pendencias.append({'url': f'/edu/atualizar_meus_dados_pessoais/{aluno.matricula}/', 'titulo': 'Atualize seus Dados Pessoais'})

        if not aluno.eh_menor_idade and not aluno.solicitacaoautorizacaousoimagem_set.exists():
            pendencias.append({'url': f'/edu/aluno/{aluno.matricula}/', 'titulo': 'Responda a solicitação de autorização de uso de imagem'})

        qtd_mensagens = (
            Mensagem.objects.filter(destinatarios=usuario.pk)
            .exclude(remetente=usuario)
            .exclude(registroexclusao__destinatario__pk=usuario.pk)
            .exclude(registroleitura__destinatario__pk=usuario.pk)
            .distinct()
        ).count()
        if qtd_mensagens:
            pendencias.append(
                {
                    'titulo': f'Mensage{pluralize(qtd_mensagens, "m,ns")}',
                    'subtitulo': f'não lida{pluralize(qtd_mensagens)}',
                    'qtd': qtd_mensagens,
                    'url': '/admin/edu/mensagementrada/?tab=tab_nao_lidas',
                }
            )

        qtd_trabalhos = (
            Trabalho.objects.filter(
                diario__matriculadiario__matricula_periodo__aluno=aluno, diario__matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO
            )
            .exclude(entregatrabalho__isnull=False)
            .exclude(data_limite_entrega__lt=datetime.date.today())
            .distinct()
        ).count()
        if qtd_trabalhos:
            pendencias.append(
                {
                    'titulo': f'Trabalho{pluralize(qtd_trabalhos)}',
                    'subtitulo': 'sem entrega',
                    'qtd': qtd_trabalhos,
                    'url': '/admin/edu/trabalho/',
                }
            )

        qtd_requerimentos = Requerimento.objects.filter(aluno=aluno, situacao='Em Andamento').count()
        if qtd_requerimentos:
            pendencias.append(
                {
                    'titulo': f'Requerimento{pluralize(qtd_requerimentos)}',
                    'subtitulo': 'em andamento',
                    'qtd': qtd_requerimentos,
                    'url': f'/edu/aluno/{aluno.matricula}/?tab=requerimentos',
                }
            )

    else:
        vinculo = usuario.get_vinculo()

        inicio_confirmacao_frequencia = Configuracao.get_valor_por_chave('edu', 'inicio_confirmacao_frequencia')
        if inicio_confirmacao_frequencia:
            inicio_confirmacao_frequencia = datetime.datetime.strptime(inicio_confirmacao_frequencia, '%Y-%m-%d')
            ids = set(
                Aula.objects.filter(
                    professor_diario__professor__vinculo=vinculo,
                    registro_frequencia_confirmado=False,
                    data__gte=inicio_confirmacao_frequencia,
                )
                .exclude(data__gte=datetime.datetime.today())
                .values_list('professor_diario__diario', flat=True)
            )
            qtd = len(ids)
            if qtd:
                param = '_'.join([str(pk) for pk in ids])
                pendencias.append(
                    {
                        'url': f'/edu/meus_diarios/{param}',
                        'titulo': f'Você possui <strong>{qtd}</strong> diário{pluralize(qtd)} aguardando confirmação de presença.',
                    }
                )

        assinaturas_eletronicas_pendentes = (
            SolicitacaoAssinaturaEletronica.objects.filter(data_assinatura__isnull=True, vinculo=vinculo)
            .filter(assinatura_eletronica__data_revogacao__isnull=True)
            .count()
        )
        if assinaturas_eletronicas_pendentes:
            pendencias.append(
                {
                    'titulo': f'Diploma{pluralize(assinaturas_eletronicas_pendentes)}',
                    'subtitulo': 'aguardando assinatura',
                    'qtd': assinaturas_eletronicas_pendentes,
                    'url': '/admin/edu/assinaturaeletronica/?tab=tab_pendentes_usuario',
                }
            )

        assinaturas_eletronicas_ata_pendentes = AssinaturaAtaEletronica.objects.filter(data__isnull=True, vinculo_id=vinculo.id).count()
        if assinaturas_eletronicas_ata_pendentes:
            pendencias.append(
                {
                    'titulo': f'Ata{pluralize(assinaturas_eletronicas_ata_pendentes)} de Projeto Final',
                    'subtitulo': 'aguardando assinatura',
                    'qtd': assinaturas_eletronicas_ata_pendentes,
                    'url': '/admin/edu/ataeletronica/?tab=tab_pendentes',
                }
            )

        qtd = AuditoriaEnsino.objects.filter(data_resolucao_auditoria__isnull=True, atendente=vinculo).count()
        if qtd:
            pendencias.append(
                {
                    'titulo': f'Auditoria{pluralize(qtd)} do Ensino',
                    'subtitulo': 'aguardando resolução',
                    'qtd': qtd,
                    'url': f'/admin/edu/auditoriaensino/?atendente={vinculo.id}&tab=tab_em_atendimento',
                }
            )

        qtd_equivalencias_nao_avalidas = vinculo.avaliadorequivalenciacomponente_set.filter(aprovada__isnull=True).count()
        if qtd_equivalencias_nao_avalidas:
            pendencias.append(
                {
                    'titulo': 'Equivalência de componente',
                    'subtitulo': 'aguardando minha avaliação',
                    'qtd': qtd_equivalencias_nao_avalidas,
                    'url': '/admin/edu/equivalenciacomponente/?tab=tab_aguardando_minha_avaliacao',
                }
            )

        nadaconsta = NadaConsta.objects.sob_responsabilidade(usuario).filter(quitado__isnull=True, data_solicitacao__isnull=False).count()
        if nadaconsta:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(nadaconsta, "ão,ões")} de Nada Consta',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': nadaconsta,
                    'url': '/admin/edu/nadaconsta/?tab=tab_aguardando_minha_avaliacao',
                }
            )

    return pendencias


def _pendencias_reposicao_atividade(user: User) -> list[dict[str, object]]:
    # Sem o escopo ``locals``: o filtro por ``user`` já restringe aos alunos dos diários do professor (#17795).
    qtd = AbonoFaltas.locals.aguardando_reposicao_atividade(queryset=AbonoFaltas.objects.all(), user=user).values('pk').count()
    if not qtd:
        return []
    return [
        {
            'titulo': 'Justificativa de falta',
            'subtitulo': 'Aguardando agendamento de reposição de atividade',
            'qtd': qtd,
            'url': '/admin/edu/abonofaltas/?tab=tab_aguardando_reposicao_minha_atividade',
        }
    ]


@layout.atribuidos_a_mim()
def pendencias_requerimento(request: HttpRequest) -> list[dict[str, object]]:
    """Lista pendências de requerimentos acadêmicos por papel do usuário.

    Para ``Avaliador de Requerimento`` mostra aproveitamentos de estudo
    aguardando avaliação; para ``Coordenador de Curso`` consolida em uma
    única consulta as contagens de aproveitamentos aguardando aceite,
    deferimento ou ambos.

    Args:
        request: requisição HTTP usada para obter o vínculo e os grupos do usuário.

    Returns:
        list[dict]: cartões com ``titulo``, ``subtitulo``, ``qtd`` e ``url``;
        lista vazia se nenhuma das contagens for positiva ou o usuário não
        tiver os papéis verificados.
    """
    pendencias = []
    vinculo = request.user.get_vinculo()
    if request.user.has_group_cached('Avaliador de Requerimento', ignore_groups_if_superuser=False):
        qs = SolicitacaoAproveitamentoEstudo.objects.filter(avaliador__vinculo=vinculo, parecer__isnull=True)
        qtd = qs.count()
        if qtd:
            pendencias.append(
                {
                    'titulo': 'Requerimento de Aproveitamento de Estudo',
                    'subtitulo': 'Aguardando Minha Avaliação',
                    'qtd': qtd,
                    'url': '/admin/edu/requerimento/?tab=tab_aguardando_minha_avaliacao',
                }
            )
    if request.user.has_group_cached('Coordenador de Curso', ignore_groups_if_superuser=False):
        qs_base = RequerimentoAproveitamentoEstudo.objects.filter(
            Q(aluno__curso_campus__coordenador=vinculo) | Q(aluno__curso_campus__coordenador_2=vinculo),
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
        )
        contagens = qs_base.aggregate(
            encaminhar=Count('id', filter=Q(atendente__isnull=True), distinct=True),
            em_avaliacao=Count('id', filter=Q(atendente__isnull=False), distinct=True),
            reencaminhar=Count(
                'id',
                filter=Q(atendente__isnull=False, solicitacaoaproveitamentoestudo__parecer__apto=False),
                distinct=True,
            ),
        )
        if contagens['encaminhar']:
            pendencias.append(
                {
                    'titulo': 'Requerimento de Aproveitamento de Estudo',
                    'subtitulo': 'Aguardando Encaminhamento',
                    'qtd': contagens['encaminhar'],
                    'url': '/admin/edu/requerimento/?tab=tab_encaminhar',
                }
            )
        if contagens['em_avaliacao']:
            pendencias.append(
                {
                    'titulo': 'Requerimento de Aproveitamento de Estudo',
                    'subtitulo': 'Aguardando Avaliação',
                    'qtd': contagens['em_avaliacao'],
                    'url': '/admin/edu/requerimento/?tab=tab_em_avaliacao',
                }
            )
        if contagens['reencaminhar']:
            pendencias.append(
                {
                    'titulo': 'Requerimento de Aproveitamento de Estudo',
                    'subtitulo': 'Aguardando Reencaminhamento',
                    'qtd': contagens['reencaminhar'],
                    'url': '/admin/edu/requerimento/?tab=tab_reencaminhar',
                }
            )

    if request.user.has_group_cached('Professor', ignore_groups_if_superuser=False):
        pendencias.extend(_pendencias_reposicao_atividade(request.user))

    if request.user.has_group_cached('Secretário Acadêmico', ignore_groups_if_superuser=False):
        pks = AbonoFaltas.locals.filter(responsavel_abono__isnull=True).values_list('pk', flat=True)
        qtd = pks.count()
        if qtd:
            pendencias.append(
                {
                    'titulo': 'Justificativa de Falta',
                    'subtitulo': 'Aguardando Avaliação',
                    'qtd': qtd,
                    'url': '/admin/edu/abonofaltas/?tab=tab_aguardando_avaliacao',
                }
            )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    hoje = datetime.date.today()

    if not request.user.eh_aluno:
        setor_user = request.user.get_vinculo().setor

        # Certificado ENEM
        if request.user.has_group_cached('Certificador ENEM', ignore_groups_if_superuser=False):
            qtd_solicitacoes_pendentes = SolicitacaoCertificadoENEM.objects.filter(
                configuracao_certificado_enem__in=request.user.get_vinculo().configuracaocertificadoenem_set.all(),
                data_avaliacao__isnull=True,
            ).count()
            if qtd_solicitacoes_pendentes:
                pendencias.append(
                    {
                        'titulo': f'Solicitaç{pluralize(qtd_solicitacoes_pendentes, "ão,ões")} de Certificado{pluralize(qtd_solicitacoes_pendentes)} ENEM',
                        'subtitulo': 'a avaliar',
                        'qtd': qtd_solicitacoes_pendentes,
                        'url': '/admin/edu/solicitacaocertificadoenem/?tab=tab_pendentes',
                    }
                )

        if setor_user:
            if request.user.has_perm('edu.view_registroeducacenso', ignore_superuser=True):
                ids_registros_educacenso_pendentes = set(
                    RespostaEducacenso.objects.filter(
                        campus_id=setor_user.uo_id,
                        questao__registro__privado=False,
                        situacao__in=[RespostaEducacenso.SITUACAO_AGUARDANDO, RespostaEducacenso.SITUACAO_EDICAO],
                    ).values_list('questao__registro_id', flat=True)
                )
                if len(ids_registros_educacenso_pendentes) > 0:
                    pendencias.append(
                        {
                            'titulo': 'Questionário do Educacenso',
                            'subtitulo': 'aguardando preenchimento',
                            'qtd': len(ids_registros_educacenso_pendentes),
                            'url': f'/admin/edu/registroeducacenso/?id__in={",".join(map(str, ids_registros_educacenso_pendentes))}',
                        }
                    )

            if (
                request.user.has_group_cached('Diretor Acadêmico', ignore_groups_if_superuser=False)
                and CursoCampus.objects.filter(plano_ensino=True).exists()
            ):
                planos_ensino = PlanoEnsino.objects.filter(
                    data_aprovacao__isnull=False,
                    data_homologacao__isnull=True,
                    diario__turma__curso_campus__diretoria__setor__uo_id=setor_user.uo_id,
                ).count()
                if planos_ensino:
                    pendencias.append(
                        {
                            'titulo': f'Plano{pluralize(planos_ensino)} de Ensino',
                            'subtitulo': 'a homologar',
                            'qtd': planos_ensino,
                            'url': '/admin/edu/planoensino/?tab=tab_aguardando_homologacao',
                        }
                    )

            if request.user.has_perm('edu.view_configuracaonadaconsta', ignore_superuser=True):
                qtd_itens = ItemConfiguracaoNadaConsta.objects.filter(
                    setores_responsaveis__isnull=True, servidores_responsaveis__isnull=True, configuracao__uo_id=setor_user.uo_id
                ).count()
                if qtd_itens:
                    pendencias.append(
                        {
                            'titulo': f'Ite{pluralize(qtd_itens, "m,ns")} de Nada Consta',
                            'subtitulo': 'a informar responsável pelo atendimento',
                            'qtd': qtd_itens,
                            'url': '/admin/edu/configuracaonadaconsta/',
                        }
                    )

            setores_secretario = list(
                UsuarioGrupoSetor.objects.filter(usuario_grupo__user=request.user, usuario_grupo__group__name='Secretário Acadêmico').values_list(
                    'setor_id', flat=True
                )
            )
            if setores_secretario:
                # notifica somente secretários de diretoria do tipo Acadêmica
                campus_ids = list(
                    Diretoria.objects.filter(setor_id__in=setores_secretario, tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA)
                    .values_list('setor__uo_id', flat=True)
                    .distinct()
                )
                if campus_ids:
                    contagens_auditoria = (
                        AuditoriaEnsino.objects.filter(data_ciencia_atendente__isnull=True, geracao_finalizada=True, campus_id__in=campus_ids)
                        .exclude(tipo_auditoria=AuditoriaEnsino.TIPO_ALUNO_SEM_SISTEC)
                        .values('campus_id')
                        .annotate(qtd=Count('id'))
                    )
                    for contagem in contagens_auditoria:
                        qtd = contagem['qtd']
                        if qtd:
                            pendencias.append(
                                {
                                    'titulo': f'Auditoria{pluralize(qtd)} do ensino',
                                    'subtitulo': 'a iniciar atendimento',
                                    'qtd': qtd,
                                    'url': f'/admin/edu/auditoriaensino/?campus={setor_user.uo_id}&tab=tab_gerada',
                                }
                            )

                contagens_abertura = (
                    AberturaExtemporanea.objects.filter(
                        situacao=AberturaExtemporanea.INICIADA, diretoria__setor_id__in=setores_secretario, diretoria__isnull=False
                    )
                    .values('diretoria_id')
                    .annotate(qtd=Count('id'))
                )
                if contagens_abertura:
                    diretorias_por_id = {d.id: d for d in Diretoria.objects.filter(id__in=[c['diretoria_id'] for c in contagens_abertura])}
                    for contagem in contagens_abertura:
                        qtd = contagem['qtd']
                        diretoria = diretorias_por_id.get(contagem['diretoria_id'])
                        if qtd and diretoria:
                            pendencias.append(
                                {
                                    'titulo': f'Abertura{pluralize(qtd)} Extemporânea{pluralize(qtd)}',
                                    'subtitulo': f'em andamento para a {diretoria}',
                                    'qtd': qtd,
                                    'url': f'/admin/edu/aberturaextemporanea/?diretoria={diretoria.pk}&tab=tab_iniciada',
                                }
                            )
                qtd = AberturaExtemporanea.objects.filter(situacao=AberturaExtemporanea.INICIADA, diretoria__isnull=True).count()
                if qtd:
                    pendencias.append(
                        {
                            'titulo': f'Abertura{pluralize(qtd)} Extemporânea{pluralize(qtd)}',
                            'subtitulo': 'em andamento',
                            'qtd': qtd,
                            'url': '/admin/edu/aberturaextemporanea/?tab=tab_iniciada',
                        }
                    )

        if request.user.has_perm('comum.is_reitor', ignore_superuser=True):
            qtd = AberturaExtemporanea.objects.filter(situacao=AberturaExtemporanea.SOLICITADA).count()
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Abertura{pluralize(qtd)} Extemporânea{pluralize(qtd)}',
                        'subtitulo': 'a deferir',
                        'qtd': qtd,
                        'url': '/admin/edu/aberturaextemporanea/?tab=tab_solicitada',
                    }
                )

        if request.user.has_perm('comum.is_procurador_institucional', ignore_superuser=True):
            qtd = (
                CursoCampus.objects.filter(mesmo_curso__isnull=True, em_extincao=True, extinto=False, matrizes__isnull=False)
                .exclude(aluno__situacao__in=SituacaoMatricula.SITUACOES_CURSANDO)
                .exclude(modalidade_id=Modalidade.FIC_MENOS)
                .distinct()
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)} em extinção',
                        'subtitulo': 'a finalizar ato de extinção',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?em_extincao__exact=1&extinto__exact=0&tab=sem_alunos',
                    }
                )

            qtd = (
                CursoCampus.objects.filter(mesmo_curso__isnull=True, ativo=False, em_extincao=False, extinto=False, matrizes__isnull=False)
                .exclude(modalidade_id=Modalidade.FIC_MENOS)
                .distinct()
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)} inativo{pluralize(qtd)}',
                        'subtitulo': 'a emitir ato de extinção',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?ativo__exact=0&em_extincao__exact=0&extinto__exact=0&tab=com_matriz',
                    }
                )

            qtd = (
                CursoCampus.objects.filter(
                    mesmo_curso__isnull=True,
                    tramitacaoprocessoemec__isnull=True,
                    data_solicitacao_reconhecimento__lt=hoje,
                    modalidade__in=AtoRegulatorioCurso.MODALIDADE_EXIGE_RECONHECIMENTO,
                    matrizes__isnull=False,
                )
                .exclude(atoregulatoriocurso__tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO)
                .distinct()
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar tramitação de processo e-MEC',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_processo_emec',
                    }
                )

            qtd = (
                CursoCampus.objects.filter(mesmo_curso__isnull=True, tramitacaoprocessoemec__isnull=False, matrizes__isnull=False)
                .exclude(atoregulatoriocurso__tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO)
                .distinct()
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a emitir ato de reconhecimento',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_reconhecimento',
                    }
                )

            qtd = (
                CursoCampus.objects.filter(mesmo_curso__isnull=True, matrizes__isnull=False)
                .exclude(atoregulatoriocurso__tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO)
                .exclude(modalidade_id__in=[Modalidade.MESTRADO, Modalidade.DOUTORADO, Modalidade.FIC_MENOS])
                .distinct()
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a emitir ato de autorização',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_autorizacao',
                    }
                )

            qtd = (
                CursoCampus.objects.filter(
                    mesmo_curso__isnull=True, matrizes__isnull=False, modalidade_id__in=[Modalidade.MESTRADO, Modalidade.DOUTORADO]
                )
                .exclude(atoregulatoriocurso__tipo=AtoRegulatorioCurso.TIPO_CRIACAO_CURSO)
                .distinct()
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a emitir ato de criação',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_criacao',
                    }
                )

            qtd = CursoCampus.objects.filter(quantidade_vagas__isnull=True, matrizes__isnull=False).distinct().count()
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar quantidade de vagas anuais autorizadas',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=vagas_pendentes',
                    }
                )

            qtd = (
                CursoCampus.objects.filter(data_funcionamento__isnull=True, matrizes__isnull=False)
                .exclude(modalidade_id=Modalidade.FIC_MENOS)
                .distinct()
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar data de início do funcionamento',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_data_funcionamento',
                    }
                )

        if request.user.has_perm('edu.add_areacursoformacaosuperior', ignore_superuser=True):
            qs = (
                CursoCampus.objects.filter(area_curso_formacao_superior__isnull=True, modalidade__nivel_ensino_id=NivelEnsino.GRADUACAO)
                .values_list('id', flat=True)
                .distinct()
            )
            qtd = qs.count()
            if qtd:
                ids = ','.join(str(id) for id in qs)
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar área do curso de formação superior',
                        'qtd': qtd,
                        'url': f'/admin/edu/cursocampus/?id__in={ids}',
                    }
                )

        if request.user.has_perm('edu.add_atoregulatoriocurso', ignore_superuser=True):
            qs = (
                CursoCampus.objects.filter(atoregulatoriocurso__ad_referendum=True, atoregulatoriocurso__ato_homologador__isnull=True)
                .values_list('id', flat=True)
                .distinct()
            )
            qtd = qs.count()
            if qtd:
                ids = ','.join(str(id) for id in qs)
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar ato regulatório de homologação',
                        'qtd': qtd,
                        'url': f'/admin/edu/cursocampus/?id__in={ids}',
                    }
                )

            qtd = (
                CursoCampus.locals.filter(modalidade_id__in=[Modalidade.ESPECIALIZACAO], codigo_emec='', ativo=True)
                .exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar código e-MEC',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_emec',
                    }
                )

        if request.user.has_perm('comum.is_administrador_academico', ignore_superuser=True):
            qtd = AberturaExtemporanea.objects.filter(situacao=AberturaExtemporanea.DEFERIDA).count()
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Abertura{pluralize(qtd)} Extemporânea{pluralize(qtd)}',
                        'subtitulo': 'a registrar no SISTEC',
                        'qtd': qtd,
                        'url': '/admin/edu/aberturaextemporanea/?tab=tab_deferida',
                    }
                )

            qtd = AuditoriaEnsino.objects.filter(tipo_auditoria=AuditoriaEnsino.TIPO_SISTEC, geracao_finalizada=False).count()
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Auditoria{pluralize(qtd)} de Ensino solicitada{pluralize(qtd)}',
                        'subtitulo': 'a responder',
                        'qtd': qtd,
                        'url': '/admin/edu/auditoriaensino/?tab=tab_solicitada',
                    }
                )

            qtd = AuditoriaEnsino.objects.filter(
                data_ciencia_atendente__isnull=True, geracao_finalizada=True, tipo_auditoria=AuditoriaEnsino.TIPO_ALUNO_SEM_SISTEC
            ).count()
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Auditoria{pluralize(qtd)} do ensino',
                        'subtitulo': 'a iniciar atendimento',
                        'qtd': qtd,
                        'url': '/admin/edu/auditoriaensino/?tipo_auditoria__exact=9&tab=tab_gerada',
                    }
                )

            qtd = (
                CursoCampus.locals.filter(modalidade__nivel_ensino_id=NivelEnsino.GRADUACAO, codigo_censup='', ativo=True)
                .exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar código CENSUP',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_censup',
                    }
                )

            qtd = (
                CursoCampus.locals.filter(codigo_sistec='', ativo=True)
                .exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
                .exclude(modalidade_id=Modalidade.FIC_MENOS)
                .exclude(aluno__isnull=True)
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar código SISTEC',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_sistec',
                    }
                )
            qs = (
                CursoCampus.locals.filter(codigo_educacenso__isnull=True, ativo=True)
                .exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
                .exclude(modalidade_id=Modalidade.FIC_MENOS)
            )
            qs = qs.filter(modalidade__nivel_ensino_id=NivelEnsino.MEDIO) | qs.filter(modalidade_id=Modalidade.PROEJA_FIC_FUNDAMENTAL)
            qtd = qs.distinct().count()
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)}',
                        'subtitulo': 'a informar código EDUCACENSO',
                        'qtd': qtd,
                        'url': '/admin/edu/cursocampus/?tab=sem_educacenso',
                    }
                )

            qtd = (
                CursoCampus.locals.filter(ch_total__gte=CursoCampus.CARGA_HORARIA_BASE_MINICURSO, codigo_sistec='', ativo=True)
                .exclude(diretoria__tipo=Diretoria.TIPO_PRONATEC)
                .exclude(aluno__isnull=True)
                .count()
            )
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Curso{pluralize(qtd)} FIC-',
                        'subtitulo': 'a informar código SISTEC',
                        'qtd': qtd,
                        'url': '/admin/edu/minicurso/?tab=sem_sistec',
                    }
                )

        qtd_dias = Configuracao.get_valor_por_chave('edu', 'notificacao_suspensao_curso')
        if qtd_dias and request.user.has_perm('edu.recebe_notificao_curso_suspenso', ignore_superuser=True):
            qs = CursoCampus.objects.filter(suspenso=True, em_extincao=False, extinto=False).values_list('id', flat=True).distinct()
            if qs.count():
                data_corte = hoje - timedelta(days=int(qtd_dias))
                qs_ato = (
                    AtoRegulatorioCurso.objects.filter(curso_id__in=qs, tipo=AtoRegulatorioCurso.TIPO_SUSPENSAO, data__lt=data_corte)
                    .distinct()
                    .values_list('curso_id', flat=True)
                )
                qtd = qs_ato.count()
                if qtd:
                    ids = ','.join(str(id) for id in qs_ato)
                    pendencias.append(
                        {
                            'titulo': f'Curso{pluralize(qtd)}',
                            'subtitulo': f'suspenso{pluralize(qtd)} a mais de {qtd_dias} dias',
                            'qtd': qtd,
                            'url': f'/admin/edu/cursocampus/?id__in={ids}',
                        }
                    )

        if request.user.has_perm('edu.view_respostajustificativacensup', ignore_superuser=True):
            qtd = RespostaJustificativaCensup.objects.filter(resposta__isnull=True).count()
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Justificativa{pluralize(qtd)} CENSUP',
                        'subtitulo': 'a responder',
                        'qtd': qtd,
                        'url': '/admin/edu/respostajustificativacensup/?tab=tab_sem_resposta',
                    }
                )

        if request.user.has_perm('edu.add_justificativacensup', ignore_superuser=True):
            qtd = AlteracaoRespostaJustificativaCensup.objects.filter(deferido__isnull=True).count()
            if qtd:
                pendencias.append(
                    {
                        'titulo': f'Solicitaç{pluralize(qtd, "ão,ões")} de alteração de resposta CENSUP',
                        'subtitulo': 'a responder',
                        'qtd': qtd,
                        'url': '/admin/edu/alteracaorespostajustificativacensup/?deferido__exact=0',
                    }
                )

        if request.user.has_perm('edu.change_professor', ignore_superuser=True):
            ano_atual = datetime.date.today().year
            qs = (
                Professor.objects.filter(
                    professordiario__diario__turma__curso_campus__modalidade__nivel_ensino_id=NivelEnsino.MEDIO,
                    professordiario__diario__ano_letivo__ano=ano_atual,
                )
                .exclude(
                    curso_superior__ativo=True,
                )
                .values_list('id', flat=True)
                .distinct()
            )
            if not request.user.has_group_cached(Professor.GRUPOS_ACESSO_SISTEMICO):
                uos_id = (
                    UsuarioGrupoSetor.objects.filter(usuario_grupo__user=request.user, usuario_grupo__group__permissions__codename='change_professor')
                    .exclude(usuario_grupo__group__name__in=Professor.GRUPOS_ACESSO_SISTEMICO)
                    .values_list('setor__uo_id', flat=True)
                    .distinct()
                )
                qs = qs.filter(vinculo__setor__uo_id__in=uos_id)

            qtd = qs.count()
            if qtd:
                ids = ','.join(str(id) for id in qs)
                pendencias.append(
                    {
                        'titulo': f'Professor{pluralize(qtd, "es")}',
                        'subtitulo': 'a informar curso superior',
                        'qtd': qtd,
                        'url': f'/admin/edu/professor/?id__in={ids}',
                    }
                )

        eh_coordenador_napne = request.user.has_group_cached('Coordenador do Napne', ignore_groups_if_superuser=False)
        eh_coordenador_sistemico_napne = request.user.has_group_cached('Coordenador sistêmico do Napne', ignore_groups_if_superuser=False)

        if eh_coordenador_napne or eh_coordenador_sistemico_napne:
            # Alerta com a quantidade de acolhimentos no campus aguardando entrevistas.
            # Ex: 13 acolhimentos aguardando entrevista
            acolhidos = Acolhimento.objects.all().select_related('aluno')
            uo = Acolhimento.get_uo_if_grupo_restrito(request.user)
            if uo:
                acolhidos = acolhidos.filter(aluno__curso_campus__diretoria__setor__uo=uo)
            sem_entrevista = acolhidos.filter(entrevista__isnull=True)
            if sem_entrevista.exists():
                qtd = sem_entrevista.count()
                url = reverse('napne_listar_acolhimentos') + '?tab=sem_entrevista'
                pendencias.append(
                    {
                        'titulo': f'Acolhimento{pluralize(qtd)}',
                        'subtitulo': 'aguardando entrevista',
                        'qtd': qtd,
                        'url': url,
                    }
                )

    return pendencias


def _get_infos_edu_configurador(request: HttpRequest) -> list[dict[str, object]]:
    infos: list[dict[str, object]] = []
    if request.user.has_group_cached('edu Configurador', ignore_groups_if_superuser=False):
        if Configuracao.get_valor_por_chave('edu', 'editar_matriz_alunos_concluidos'):
            infos.append(
                {
                    'url': '/comum/configuracao/edu/',
                    'titulo': 'A opção "<strong>Permitir edição de matrizes curriculares com alunos já concluídos</strong>" está ativa. Verifique se é necessário mantê-la assim.',
                }
            )
        if Configuracao.get_valor_por_chave('edu', 'pode_cadastrar_procedimento_matricula'):
            infos.append(
                {
                    'url': '/comum/configuracao/edu/',
                    'titulo': 'A opção "<strong>Permitir inclusão de procedimentos de matrícula para estudantes</strong>" está ativa. Verifique se é necessário mantê-la assim.',
                }
            )
        if Configuracao.get_valor_por_chave('edu', 'permite_insclusao_registros_historico'):
            infos.append(
                {
                    'url': '/comum/configuracao/edu/',
                    'titulo': 'A opção "<strong>Permitir inclusão de registros no histórico escolar do aluno</strong>" está ativa. Verifique se é necessário mantê-la assim.',
                }
            )
        if Configuracao.get_valor_por_chave('edu', 'permite_edicao_registros_historico'):
            infos.append(
                {
                    'url': '/comum/configuracao/edu/',
                    'titulo': 'A opção "<strong>Permitir edição de registros no histórico escolar do aluno</strong>" está ativa. Verifique se é necessário mantê-la assim.',
                }
            )

        if not Configuracao.get_valor_por_chave('edu', 'codigo_mec'):
            infos.append(
                {
                    'url': '/comum/configuracao/edu/',
                    'titulo': 'A opção "<strong>Código MEC</strong>" não foi informada.',
                }
            )
    return infos


def _get_infos_aluno(request: HttpRequest) -> list[dict[str, object]]:
    infos: list[dict[str, object]] = []
    aluno = request.user.get_relacionamento()
    if aluno.eh_menor_idade and not aluno.solicitacaoautorizacaousoimagem_set.exists():
        infos.append(
            {
                'url': f'/edu/aluno/{aluno.matricula}/',
                'titulo': 'Solicite ao seu responsável acessar o SUAP e responder a solicitação de autorização de uso de imagem.',
            }
        )
    if not aluno.pessoa_fisica.nome_usual:
        infos.append(
            {
                'url': f'/edu/atualizar_meus_dados_pessoais/{aluno.matricula}',
                'titulo': 'Você ainda não possui um nome usual no sistema. Edite o seus dados pessoais.',
            }
        )

    # ofertas de estágio
    if aluno.get_ofertas_pratica_profissional().exists():
        infos.append(
            {
                'url': '/estagios/ofertas_pratica_profissional/',
                'titulo': 'Há oportunidades de prática profissional (Estágio/ Aprendizagem) disponíveis para seu curso.',
            }
        )

    if aluno.situacao_id in [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO]:
        for pesquisa in aluno.pesquisas_egresso():
            infos.append(
                {
                    'url': f'/egressos/responder_pesquisa_egressos/atualizacao_cadastral/{pesquisa.pk}/',
                    'titulo': '<strong>Responda Pesquisa de Acompanhamento de Ex-Aluno</strong>',
                }
            )
    return infos


def _get_infos_docente(request: HttpRequest) -> list[dict[str, object]]:
    vinculo = request.user.get_vinculo()
    if not vinculo:
        return []

    # Verificar se professor tem configuração do portal configurada
    if not _eh_docente_ativo(vinculo):
        return []

    professor = vinculo.professor_set.select_related('config_dados_docentes').first()
    if not professor:
        return []

    # Usa hasattr para evitar query adicional se config_dados_docentes não existir
    tem_config_valida = hasattr(professor, 'config_dados_docentes') and professor.config_dados_docentes.modo_exibicao
    if not tem_config_valida:
        return [
            {
                'url': reverse('editar_dados_portal', args=(professor.pk,)),
                'titulo': 'Configure seus dados no portal institucional',
                'icone': 'cog',
            }
        ]
    return []


@layout.info()
def index_infos(request: HttpRequest) -> list[dict[str, object]]:
    infos = _get_infos_edu_configurador(request)

    if request.user.eh_aluno:
        infos.extend(_get_infos_aluno(request))
    else:
        infos.extend(_get_infos_docente(request))

    return infos


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []

    if request.user.eh_aluno:
        aluno = request.user.get_relacionamento()

        # matrícula online
        if aluno.pode_matricula_online():
            inscricoes.append(
                {
                    'url': aluno.get_url_matricula_online(),
                    'titulo': 'Faça sua <strong>matrícula</strong> online.',
                    'prazo': aluno.get_configuracao_pedido_matricula_ativa().data_fim,
                }
            )

    return inscricoes


@layout.quadro('Faça sua matrícula online', icone='users', session_cache=24 * 3600)
def index_quadros_banners_alunos(quadro, request):
    if request.user.eh_aluno:
        aluno = request.user.get_relacionamento()

        # matrícula online
        if aluno.pode_matricula_online():
            quadro.add_item(
                layout.ItemImagem(
                    titulo='Faça sua matrícula online.', path='/static/edu/img/index-banner-aluno.png', url=aluno.get_url_matricula_online()
                )
            )
    return quadro


@layout.quadro('Ensino', icone='pencil-alt')
def index_quadros(quadro, request):
    if request.user.eh_aluno:
        aluno = request.user.get_relacionamento()

        qtd_projetos_finais = ProjetoFinal.objects.filter(
            data_defesa__gte=datetime.datetime.today(), matricula_periodo__aluno__curso_campus=aluno.curso_campus
        ).count()
        if qtd_projetos_finais:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Defesas de TCC', subtitulo='Agendadas para o meu curso', qtd=qtd_projetos_finais, url='/edu/visualizar_agenda_defesas/'
                )
            )

        qtd_pedidos_renovacao_pendente = PedidoMatriculaDiario.objects.filter(
            pedido_matricula__matricula_periodo__aluno=aluno, data_processamento__isnull=True
        ).count()
        if qtd_pedidos_renovacao_pendente:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Renovação de Matrícula',
                    subtitulo='Pendentes',
                    qtd=qtd_pedidos_renovacao_pendente,
                    url=f'{aluno.get_absolute_url()}?tab=pedidos',
                )
            )

        if aluno.curso_campus.is_licenciatura():
            qtd_portfolios_pendentes = (
                EstagioDocente.objects.filter(matricula_diario__matricula_periodo__aluno=aluno)
                .exclude(portfolio__isnull=True)
                .exclude(situacao__in=[EstagioDocente.SITUACAO_ENCERRADO, EstagioDocente.SITUACAO_NAO_CONCLUIDO, EstagioDocente.SITUACAO_MUDANCA])
            ).count()
            if qtd_portfolios_pendentes:
                quadro.add_item(
                    layout.ItemContador(
                        titulo='Portfólios de Estágio Docente',
                        subtitulo='Pendentes',
                        qtd=qtd_portfolios_pendentes,
                        url=f'{aluno.get_absolute_url()}?tab=estagios',
                    )
                )
        qtd_estagios_com_avaliacao_pendente = aluno.get_estagios_com_avaliacao_pendente().count()
        if qtd_estagios_com_avaliacao_pendente:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Estágios',
                    subtitulo='Com Avaliação Pendente',
                    qtd=qtd_estagios_com_avaliacao_pendente,
                    url=f'{aluno.get_absolute_url()}?tab=estagios',
                )
            )

        estagio_com_rel_atividades_pendente = aluno.get_estagio_com_rel_atividades_pendente().first()
        if estagio_com_rel_atividades_pendente:
            quadro.add_item(
                layout.ItemContador(
                    titulo='Estágios',
                    subtitulo='Rel. Atividades Pendentes',
                    qtd=estagio_com_rel_atividades_pendente.get_qtd_pendente_relatorios_estagiario,
                    url=f'/estagios/pratica_profissional/{estagio_com_rel_atividades_pendente.pk}/?tab=relatorios',
                )
            )

        if (
            aluno.get_aprendizagem_com_rel_atividades_pendente()
            and aluno.get_aprendizagem_com_rel_atividades_pendente().qtd_relatorios_aprendiz_pendentes > 0
        ):
            quadro.add_item(
                layout.ItemContador(
                    titulo='Aprendizagem',
                    subtitulo='Rel. Atividades Pendentes',
                    qtd=aluno.get_aprendizagem_com_rel_atividades_pendente().qtd_relatorios_aprendiz_pendentes,
                    url=f'{aluno.get_absolute_url()}?tab=estagios',
                )
            )
        atividade_relatorio_pendente = aluno.get_atividade_profissional_efetiva_pendente_relatorio().first()
        orientacoes = aluno.get_atividade_profissional_efetiva_reunioes_de_orientacao()
        if atividade_relatorio_pendente or orientacoes.exists():
            subtitulo = ''
            if atividade_relatorio_pendente:
                subtitulo = 'Relatório Final do Aluno Ainda Não Enviado'
                tab = 'relatorios'
                pk = atividade_relatorio_pendente.pk
            if orientacoes.exists():
                if subtitulo:
                    subtitulo = subtitulo + f' / {orientacoes.count()} Orientação(ões) marcada(s)'
                else:
                    subtitulo = f'{orientacoes.count()} orientação(ões) marcada(s)'
                tab = 'reunioes'
                pk = orientacoes[0].atividade_profissional_efetiva.pk

            quadro.add_item(
                layout.ItemContador(
                    titulo='Atividade Profissional Efetiva',
                    subtitulo=subtitulo,
                    qtd=1,
                    url=f'/estagios/atividade_profissional_efetiva/{pk}/?tab={tab}',
                )
            )

        quadro.add_itens(
            [
                layout.ItemAcessoRapido(titulo='Agenda de avaliações', icone='calendar-alt', url='/edu/calendario_avaliacao/'),
                layout.ItemAcessoRapido(titulo='Locais e horários de aula', icone='search', url=f'{aluno.get_absolute_url()}?tab=locais_aula_aluno'),
                layout.ItemAcessoRapido(titulo='Meus dados', icone='user', url=aluno.get_absolute_url()),
                layout.ItemAcessoRapido(titulo='Meus requerimentos', icone='search', url=f'{aluno.get_absolute_url()}?tab=requerimentos'),
                layout.ItemAcessoRapido(titulo='Minhas disciplinas', icone='search', url='/edu/disciplinas/'),
                layout.ItemAcessoRapido(titulo='Minhas justificativas de falta', icone='search', url=f'{aluno.get_absolute_url()}?tab=abono_falta'),
            ]
        )

        if aluno.polo:
            quadro.add_item(layout.ItemAcessoRapido(titulo=f'Polo {aluno.polo.descricao}', url='/edu/meu_polo/'))

    return quadro


@layout.quadro('Professores', icone='graduation-cap')
def index_quadros_professores(quadro, request):
    vinculo = request.user.get_vinculo()
    if not vinculo:
        return quadro
    professor = vinculo.professor_set.first()
    if professor:
        professores_diario = professor.professordiario_set.filter(ativo=True).order_by('diario')
        if professores_diario.exists():
            hoje = datetime.datetime.now()
            inicio = hoje - timedelta(days=7)
            diarios = Diario.objects.filter(
                id__in=professores_diario.values_list('diario', flat=True), calendario_academico__data_inicio_etapa_1__lt=inicio
            )
            diarios = diarios.exclude(
                posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR,
                posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR,
                posse_etapa_3=Diario.POSSE_REGISTRO_ESCOLAR,
                posse_etapa_4=Diario.POSSE_REGISTRO_ESCOLAR,
            )
            pk_diarios = []
            pk_diarios_pendentes = []
            for diario in diarios:
                if diario.matriculadiario_set.exists():
                    aulas = diario.get_aulas().filter(data__range=(inicio, hoje))
                    if not aulas.exists():
                        pk_diarios.append(str(diario.pk))

                fimetapa = hoje - timedelta(days=7)
                if (
                    diario.matriculadiario_set.filter(
                        diario__professordiario__data_fim_etapa_1__lt=fimetapa, diario__posse_etapa_1=Diario.POSSE_PROFESSOR
                    ).exists()
                    or diario.matriculadiario_set.filter(
                        diario__professordiario__data_fim_etapa_2__lt=fimetapa, diario__posse_etapa_2=Diario.POSSE_PROFESSOR
                    ).exists()
                    or diario.matriculadiario_set.filter(
                        diario__professordiario__data_fim_etapa_3__lt=fimetapa, diario__posse_etapa_3=Diario.POSSE_PROFESSOR
                    ).exists()
                    or diario.matriculadiario_set.filter(
                        diario__professordiario__data_fim_etapa_4__lt=fimetapa, diario__posse_etapa_4=Diario.POSSE_PROFESSOR
                    ).exists()
                    or diario.matriculadiario_set.filter(
                        diario__professordiario__data_fim_etapa_final__lt=fimetapa, diario__posse_etapa_5=Diario.POSSE_PROFESSOR
                    ).exists()
                ):
                    pk_diarios_pendentes.append(str(diario.pk))

            if pk_diarios:
                quadro.add_item(
                    layout.ItemContador(
                        titulo=len(pk_diarios) == 1 and 'Diário' or 'Diários',
                        subtitulo='Sem registro há 8 dias',
                        qtd=len(pk_diarios),
                        url=('/edu/meus_diarios/{}'.format('_'.join(pk_diarios))),
                    )
                )
            if pk_diarios_pendentes:
                quadro.add_item(
                    layout.ItemContador(
                        titulo=len(pk_diarios_pendentes) == 1 and 'Diário' or 'Diários',
                        subtitulo='Não Entregues',
                        qtd=len(pk_diarios_pendentes),
                        url=('/edu/meus_diarios/{}'.format('_'.join(pk_diarios_pendentes))),
                    )
                )
                Requerimento.objects.filter()

            qtd_requerimentos = Requerimento.objects.filter(
                situacao='Em Andamento', tipo=Requerimento.REALIZACAO_PROVA, diario__professordiario__professor__vinculo__user=request.user
            ).count()
            if qtd_requerimentos:
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Requerimento{pluralize(qtd_requerimentos)}',
                        subtitulo='Em andamento',
                        qtd=qtd_requerimentos,
                        url='/admin/edu/requerimento/?tab=tab_em_andamento',
                    )
                )

        quadro.add_itens(
            [
                layout.ItemAcessoRapido(titulo='Meus Diários', url='/edu/meus_diarios/'),
                layout.ItemAcessoRapido(titulo='Materiais de Aula', icone='book', url='/admin/edu/materialaula/'),
                layout.ItemAcessoRapido(titulo='Agenda de Avaliações', icone='calendar-alt', url='/edu/calendario_avaliacao/'),
                layout.ItemAcessoRapido(titulo='Participações em Bancas de Projeto Final', url=f'/edu/professor/{professor.pk:d}/?tab=banca'),
                layout.ItemAcessoRapido(titulo='Orientação de Projeto Final', url=f'/edu/professor/{professor.pk:d}/?tab=projetofinal'),
                layout.ItemAcessoRapido(titulo='Meus Dados', url=f'/edu/professor/{professor.pk:d}/'),
                layout.ItemAcessoRapido(titulo='Locais e Horários de Aula', url='/edu/locais_aula_professor/'),
            ]
        )

        qtd_orientacoes_estagio = professor.get_qtd_orientacoes_estagio()
        qtd_estagios_nao_visitados = professor.get_qtd_estagios_nao_visitados()
        if qtd_orientacoes_estagio:
            quadro.add_itens(
                [
                    layout.ItemContador(
                        titulo='Orientações de Estágios e Afins',
                        subtitulo=f'{qtd_estagios_nao_visitados} com visitas pendentes' if qtd_estagios_nao_visitados else '',
                        qtd=qtd_orientacoes_estagio,
                        url=f'/edu/professor/{professor.pk}/?tab=estagios',
                    )
                ]
            )

        if request.user.eh_docente:
            quadro.add_item(
                layout.ItemAcessoRapido(titulo='Plano Individual de Trabalho', url=f'/edu/professor/{professor.pk:d}/?tab=planoatividades')
            )

        if CursoCampus.objects.filter(plano_ensino=True).exists():
            qs = PlanoEnsino.objects.filter(diario__professordiario__professor__vinculo=request.user.get_vinculo(), data_submissao__isnull=True)
            if qs.exists():
                quadro.add_itens(
                    [
                        layout.ItemContador(
                            titulo='Planos de Ensino',
                            subtitulo='Aguardando Submissão',
                            qtd=qs.count(),
                            url='/admin/edu/planoensino/?tab=tab_aguardando_minha_subissao',
                        )
                    ]
                )
            quadro.add_item(layout.ItemAcessoRapido(titulo='Planos de Ensino', url='/admin/edu/planoensino/'))

    return quadro


@layout.quadro('Coordenação de Curso - Pendências', icone='graduation-cap', session_cache=5 * 60)
def index_quadros_coordenadores_diretoria(quadro, request):
    if request.user.has_group_cached('Coordenador de Curso', ignore_groups_if_superuser=False):
        vinculo = request.user.get_vinculo()
        cursos_id = CursoCampus.objects.filter(Q(coordenador=vinculo) | Q(coordenador_2=vinculo)).values_list('id', flat=True)
        periodos = (
            Turma.objects.filter(curso_campus_id__in=cursos_id, calendario_academico__data_fim__gte=datetime.date.today())
            .values('ano_letivo__ano', 'periodo_letivo')
            .annotate(qtd=Count('pk'))
            .order_by('ano_letivo__ano', 'periodo_letivo')
        )
        diretorias = Diretoria.objects.filter(cursocampus__in=cursos_id).distinct()
        for item in periodos:
            if item['qtd']:
                ano = item['ano_letivo__ano']
                periodo = item['periodo_letivo']
                for diretoria in diretorias:
                    for pendencia in diretoria.get_pendencias(ano, periodo, request.user, True):
                        subtexto = pendencia.get('subtexto', '')
                        quadro.add_itens(
                            [
                                layout.ItemContador(
                                    titulo=pendencia['nome'],
                                    subtitulo=f'{subtexto} na {diretoria}',
                                    qtd=pendencia['quantidade'],
                                    url=pendencia['url'],
                                )
                            ]
                        )
    return quadro


def get_qtd_turmas_periodos(quadro, qs_turma, curso, filter_condition, period_type_description):
    """
    Adiciona contadores de turmas ao quadro para períodos específicos,
    otimizando a contagem para evitar N+1 queries.

    Args:
        quadro: O objeto quadro para adicionar os itens.
        qs_turma: QuerySet base de turmas.
        curso: O objeto CursoCampus.
        filter_condition: Uma condição Q para filtrar os períodos.
        period_type_description: Descrição do tipo de período (ex: 'vigente', 'a iniciar').
    """
    period_counts = (
        qs_turma.filter(filter_condition)
        .values('ano_letivo_id', 'ano_letivo__ano', 'periodo_letivo')
        .annotate(qtd=Count('pk'))
        .order_by('ano_letivo__ano', 'periodo_letivo')
    )

    for item in period_counts:
        qtd = item['qtd']
        if qtd:
            ano_id = item['ano_letivo_id']
            ano = item['ano_letivo__ano']
            periodo = item['periodo_letivo']

            plural_suffix = pluralize(qtd)

            # Constrói o subtítulo com base na descrição do tipo de período
            if period_type_description == 'vigente':
                subtitulo = f'vigente{plural_suffix} em {ano}.{periodo} do curso {curso.descricao_historico}'
            elif period_type_description == 'a iniciar':
                subtitulo = f'a iniciar em {ano}.{periodo} do curso {curso.descricao_historico}'
            else:
                # Fallback para outros tipos, se necessário
                subtitulo = f'{period_type_description}{plural_suffix} em {ano}.{periodo} do curso {curso.descricao_historico}'

            quadro.add_itens(
                [
                    layout.ItemContador(
                        titulo=f'Turma{plural_suffix}',
                        subtitulo=subtitulo,
                        qtd=qtd,
                        url=f'/admin/edu/turma/?curso_campus={curso.id}&ano_letivo__id__exact={ano_id}&periodo_letivo__exact={periodo}',
                    )
                ]
            )


@layout.quadro('Coordenação de Curso', icone='graduation-cap', session_cache=5 * 60)
def index_quadros_coordenadores_curso(quadro, request):
    if request.user.has_group_cached('Coordenador de Curso', ignore_groups_if_superuser=False):
        vinculo = request.user.get_vinculo()
        qs_cursos = CursoCampus.objects.filter(Q(coordenador=vinculo) | Q(coordenador_2=vinculo)).distinct()

        for curso in qs_cursos:
            # - Alunos com AACC pendentes de aprovação;
            qtd_aacc_pendente = AtividadeComplementar.locals.pendentes().filter(aluno__curso_campus_id=curso.pk).count()
            if qtd_aacc_pendente:
                quadro.add_itens(
                    [
                        layout.ItemContador(
                            titulo='AACC',
                            subtitulo=f'pendentes de aprovação do curso {curso.descricao_historico}',
                            qtd=qtd_aacc_pendente,
                            url=f'/admin/edu/atividadecomplementar/?deferida__isnull=True&aluno__curso_campus={curso.pk}',
                        )
                    ]
                )

            # - Alunos com ATPA pendentes de aprovação;
            qtd_atp_pendente = AtividadeAprofundamento.locals.filter(deferida__isnull=True, aluno__curso_campus_id=curso.pk).count()
            if qtd_atp_pendente:
                quadro.add_itens(
                    [
                        layout.ItemContador(
                            titulo='ATP',
                            subtitulo=f'pendentes de aprovação do curso {curso.descricao_historico}',
                            qtd=qtd_atp_pendente,
                            url=f'/admin/edu/atividadeaprofundamento/?deferida__isnull=True&aluno__curso_campus={curso.pk}',
                        )
                    ]
                )

            # - Diários não entregues;
            qtd_diarios = (
                Diario.locals.get_queryset()
                .filter(turma__curso_campus_id=curso.pk)
                .exclude(professordiario__professor__vinculo__user_id=request.user.pk)
                .nao_entregues()
                .count()
            )
            if qtd_diarios:
                quadro.add_itens(
                    [
                        layout.ItemContador(
                            titulo=f'Diário{pluralize(qtd_diarios)}',
                            subtitulo=f'não entregues do curso {curso.descricao_historico}',
                            qtd=qtd_diarios,
                            url=f'/admin/edu/diario/?turma__curso_campus={curso.pk}&tab=tab_nao_entregues',
                        )
                    ]
                )

            qs_turma = Turma.objects.filter(curso_campus_id=curso.pk)

            # - Turmas com fechamento pendente;
            qtd_turmas_pendentes = qs_turma.pendentes().count()
            if qtd_turmas_pendentes:
                quadro.add_itens(
                    [
                        layout.ItemContador(
                            titulo=f'Turma{pluralize(qtd_turmas_pendentes)}',
                            subtitulo=f'pendente{pluralize(qtd_turmas_pendentes)} do curso {curso.descricao_historico}',
                            qtd=qtd_turmas_pendentes,
                            url=f'/admin/edu/turma/?curso_campus={curso.id}&tab=tab_pendentes',
                        )
                    ]
                )

            hoje = datetime.date.today()
            # - Turmas em andamento
            get_qtd_turmas_periodos(
                quadro, qs_turma, curso, Q(calendario_academico__data_inicio__lte=hoje, calendario_academico__data_fim__gte=hoje), 'vigente'
            )

            # Turmas a iniciar;
            get_qtd_turmas_periodos(quadro, qs_turma, curso, Q(calendario_academico__data_inicio__gt=hoje), 'a iniciar')

            # - Alunos sem turma; PENDENCIAS DE TODOS PERIODOS
            for ano, periodo in Aluno.get_periodos_alunos_sem_turma(request.user, curso.id):
                qtd_alunos_sem_turma = Aluno.get_alunos_sem_turma(request.user, ano, periodo, curso.id).count()
                if qtd_alunos_sem_turma:
                    quadro.add_itens(
                        [
                            layout.ItemContador(
                                titulo=f'Aluno{pluralize(qtd_alunos_sem_turma)}',
                                subtitulo=f'sem turma em {ano}.{periodo} do curso {curso.descricao_historico}',
                                qtd=qtd_alunos_sem_turma,
                                url=f'/edu/alunos_sem_turma_curso/{ano}/{periodo}/{curso.id}/',
                            )
                        ]
                    )
            # - Atividades curriculares de extensão não avaliadas
            qtd_atividades = AtividadeCurricularExtensao.objects.filter(
                matricula_periodo__aluno__curso_campus_id=curso.id, concluida=True, aprovada__isnull=True
            ).count()
            if qtd_atividades:
                quadro.add_itens(
                    [
                        layout.ItemContador(
                            titulo='Atividade Curricular de Extensão',
                            subtitulo=f'não avaliada do curso {curso.descricao_historico}',
                            qtd=qtd_atividades,
                            url=f'/admin/edu/atividadecurricularextensao/?matricula_periodo__aluno__curso_campus={curso.id}&tab=tab_aguardando_avaliacao',
                        )
                    ]
                )
            qtd_requerimentos = (
                Requerimento.objects.filter(
                    aluno__curso_campus_id=curso.id,
                    situacao='Em Andamento',
                    tipo__in=[Requerimento.MATRICULA_DISCIPLINA, Requerimento.REALIZACAO_PROVA],
                )
                .exclude(situacao='Arquivado')
                .count()
            )
            if qtd_requerimentos:
                quadro.add_item(
                    layout.ItemContador(
                        titulo=f'Requerimento{pluralize(qtd_requerimentos)}',
                        subtitulo=f'Em andamento do curso {curso.descricao_historico}',
                        qtd=qtd_requerimentos,
                        url=f'/admin/edu/requerimento/?aluno__curso_campus={curso.id}&tab=tab_em_andamento',
                    )
                )

        if CursoCampus.objects.filter(plano_ensino=True, coordenador=request.user.get_vinculo()).exists():
            qs = PlanoEnsino.objects.filter(coordenador_curso=request.user.get_vinculo(), data_submissao__isnull=False, data_aprovacao__isnull=True)
            if qs.exists():
                quadro.add_itens(
                    [
                        layout.ItemContador(
                            titulo='Planos de Ensino',
                            subtitulo='Aguardando Aprovação',
                            qtd=qs.count(),
                            url='/admin/edu/planoensino/?tab=tab_aguardando_minha_aprovacao',
                        )
                    ]
                )
            quadro.add_item(layout.ItemAcessoRapido(titulo='Planos de Ensino', url='/admin/edu/planoensino/'))

        for pendencia in AtividadePraticaProfissional.get_pendencias_coordenador(request.user):
            subtexto = pendencia.get('subtexto', '')
            quadro.add_itens(
                [
                    layout.ItemContador(
                        titulo=pendencia['nome'],
                        subtitulo=subtexto,
                        qtd=pendencia['quantidade'],
                        url=pendencia['url'],
                    )
                ]
            )

        return quadro


@layout.quadro('Serviços Microsoft', icone='windows fab', pode_esconder=True, session_cache=24 * 3600)
def index_quadros_microsoft(quadro, request):
    if request.user.eh_aluno:
        aluno = request.user.get_relacionamento()
        if aluno.email_academico:
            quadro.add_itens(
                [
                    layout.ItemAcessoRapido(titulo='E-mail Institucional', icone='envelope', url='/microsoft/redirecionar_aluno/office365/'),
                    layout.ItemAcessoRapido(
                        titulo='Microsoft Azure',
                        icone='windows fab',
                        url='https://portal.azure.com/?Microsoft_Azure_Education_correlationId=43de9837-5309-4b65-9503-02d577da29c4#blade/Microsoft_Azure_Education/EducationMenuBlade/software',
                    ),
                ]
            )
        quadro.add_item(layout.ItemAcessoRapido(titulo='Portal Office 365', icone='windows fab', url='https://portal.office.com'))

    return quadro


@layout.quadro('Calendário Acadêmico', icone='calendar-alt', pode_esconder=True, session_cache=24 * 3600)
def index_quadros_calendario_academico(quadro, request):
    if request.user.eh_aluno:
        aluno = request.user.get_relacionamento()
        ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
        if ultima_matricula_periodo:
            calendario_academico = ultima_matricula_periodo.get_calendario_academico()
            if calendario_academico:
                quadro.add_itens(
                    [
                        layout.ItemCalendario(calendario=calendario_academico.mensal()),
                        layout.ItemAcessoRapido(titulo='Calendário Completo', url=f'/edu/calendarioacademico/{calendario_academico.pk:d}/'),
                    ]
                )

    return quadro


@layout.quadro('Calendários Acadêmicos', icone='calendar-alt', pode_esconder=True, session_cache=24 * 3600)
def index_quadros_calendarios_academicos(quadro, request):
    professor = Professor.objects.filter(vinculo__user=request.user).first()
    if professor:
        periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request, professor)
        professores_diario = ProfessorDiario.objects.filter(professor__vinculo__user=request.user, ativo=True).order_by('diario')
        professores_diario_anual = professores_diario.filter(
            diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, diario__ano_letivo__ano=periodo_letivo_atual.ano
        )

        # excluindo os diários semestrais em cursos anuais
        if periodo_letivo_atual.periodo == 1:
            professores_diario_anual = professores_diario_anual.exclude(diario__segundo_semestre=True)
        else:
            professores_diario_anual = professores_diario_anual.exclude(
                diario__segundo_semestre=False, diario__componente_curricular__qtd_avaliacoes=2
            )

        professores_diario_semestral = professores_diario.filter(
            diario__turma__curso_campus__periodicidade__in=[CursoCampus.PERIODICIDADE_SEMESTRAL, CursoCampus.PERIODICIDADE_LIVRE],
            diario__ano_letivo__ano=periodo_letivo_atual.ano,
            diario__periodo_letivo=periodo_letivo_atual.periodo,
        )
        professores_diario = (professores_diario_anual | professores_diario_semestral).order_by('diario__turma__curso_campus')
        pks_calendarios = (
            professores_diario.order_by('diario__calendario_academico').values_list('diario__calendario_academico', flat=True).distinct()
        )
        qs_calendarios_academicos = CalendarioAcademico.objects.filter(pk__in=pks_calendarios)

        diarios_especiais = professor.diarioespecial_set.filter(ano_letivo__ano=periodo_letivo_atual.ano, periodo_letivo=periodo_letivo_atual.periodo)
        qtd_diarios = professores_diario.count() + diarios_especiais.count()
        if qtd_diarios and qs_calendarios_academicos:
            legenda = """
            <div class="legenda">
                <p>Legenda:</p>
                <ul>
                    <li class="hoje">Hoje</li>
                    <li class="success">1ª Etapa</li>
                    <li class="info">2ª Etapa</li>
                    <li class="warning">3ª Etapa</li>
                    <li class="danger">4ª Etapa</li>
                    <li class="conflito">Fechamento do Período</li>
                </ul>
            </div>
            """
            for calendario_academico in qs_calendarios_academicos:
                quadro.add_item(
                    layout.ItemCalendario(
                        titulo=calendario_academico.descricao,
                        url=f'/edu/calendarioacademico/{calendario_academico.pk:d}/',
                        calendario=calendario_academico.mensal(),
                        legenda=legenda,
                    ),
                )

    return quadro


@rtr()
@login_required()
def redirecionar_aluno(request):
    title = 'Selecione o Aluno'
    form = BuscaAlunoForm(request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@login_required()
def redirecionar_diario(request):
    title = 'Selecione o Diário'
    form = BuscaDiarioForm(request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@login_required()
def redirecionar_matriz(request):
    title = 'Selecione a Matriz'
    form = BuscaMatrizForm(request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@login_required()
def redirecionar_calendario(request):
    title = 'Selecione o Calendário Acadêmico'
    form = BuscaCalendarioForm(request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()
