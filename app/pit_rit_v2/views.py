import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from comum.models import Ano
from djtools import documentos, layout
from djtools.utils import documento, httprr, rtr
from edu.models import Professor
from pit_rit_v2.forms import (
    AprovarRelatorioForm,
    CriarPlanoIndividualTrabalhoForm,
    EntregarRelatorioForm,
    EnviarPlanoForm,
    ParecerForm,
    PlanoIndividualTrabalhoProfessorForm,
    ReabrirRelatorioForm,
    RelatorioIndividualTrabalhoProfessorForm,
)
from pit_rit_v2.models import PlanoIndividualTrabalhoV2


@documentos.emissao_documentos()
def emissao_documentos(request, data):
    for pit in PlanoIndividualTrabalhoV2.objects.filter(professor__vinculo__pessoa__id=request.user.get_vinculo().pessoa.id):
        data.append(
            (
                'Ensino',
                'PIT/RIT',
                'Planos Individuais de Trabalho',
                f'{pit.ano_letivo}/{pit.periodo_letivo}',
                f'/pit_rit_v2/plano_atividade_docente_pdf/{pit.pk}/',
            )
        )
        if pit.data_envio_relatorio:
            data.append(
                (
                    'Ensino',
                    'PIT/RIT',
                    'Relatórios Individuais de Trabalho',
                    f'{pit.ano_letivo}/{pit.periodo_letivo}',
                    f'/pit_rit_v2/relatorio_atividade_docente_pdf/{pit.pk}/',
                )
            )


@layout.info()
def index_info_a_mim(request):
    infos = []
    if request.user.eh_docente and request.user.has_group_cached('Professor'):
        pk = request.user.get_vinculo().professor_set.values_list('id', flat=True).first()
        for critico, mensagem in PlanoIndividualTrabalhoV2.check_pit_rit(request.user):
            if not critico and mensagem:
                tipo = 'Plano' if 'PIT' in mensagem else 'Relatório'
                infos.append({'url': f'/edu/professor/{pk}/?tab=planoatividades', 'titulo': f'{tipo} Individual de Trabalho: {mensagem}'})
    return infos


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    if request.user.eh_docente and request.user.has_group_cached('Professor'):
        pk = request.user.get_vinculo().professor_set.values_list('id', flat=True).first()
        for critico, mensagem in PlanoIndividualTrabalhoV2.check_pit_rit(request.user):
            if critico and mensagem:
                tipo = 'Plano' if 'PIT' in mensagem else 'Relatório'
                pendencias.append(
                    {
                        'titulo': f'{tipo} Individual de Trabalho',
                        'subtitulo': mensagem,
                        'qtd': 1,
                        'url': f'/edu/professor/{pk}/?tab=planoatividades',
                    }
                )

    if request.user.has_perm('pit_rit_v2.view_planoindividualtrabalhov2'):
        qtd_plano = PlanoIndividualTrabalhoV2.objects.filter(aprovado__isnull=True, avaliador__vinculos__user=request.user).count()
        if qtd_plano:
            pendencias.append(
                {
                    'titulo': f'Plano{pluralize(qtd_plano)} Individua{pluralize(qtd_plano, "l,is")} de Trabalho',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': qtd_plano,
                    'url': '/admin/pit_rit_v2/planoindividualtrabalhov2/?tab=tab_aguardando_avaliacao',
                }
            )

        qtd_relatorio = PlanoIndividualTrabalhoV2.objects.filter(
            aprovado=True, relatorio_aprovado__isnull=True, data_envio_relatorio__isnull=False, avaliador_relatorio__vinculos__user=request.user
        ).count()
        if qtd_relatorio:
            pendencias.append(
                {
                    'titulo': f'Relatório{pluralize(qtd_relatorio)} Individua{pluralize(qtd_relatorio, "l,is")} de Trabalho',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': qtd_relatorio,
                    'url': '/admin/pit_rit_v2/planoindividualtrabalhov2/?tab=tab_aguardando_avaliacao_relatorio',
                }
            )

        qtd_publicacao = PlanoIndividualTrabalhoV2.objects.filter(
            aprovado=True, relatorio_aprovado=True, publicado__isnull=True, responsavel_publicacao__vinculos__user=request.user
        ).count()
        if qtd_publicacao:
            pendencias.append(
                {
                    'titulo': f'Relatório{pluralize(qtd_publicacao)} Individua{pluralize(qtd_publicacao, "l,is")} de Trabalho',
                    'subtitulo': 'aguardando publicação',
                    'qtd': qtd_publicacao,
                    'url': '/admin/pit_rit_v2/planoindividualtrabalhov2/?tab=tab_aguardando_publicacao',
                }
            )

    return pendencias


@rtr()
def cadastrar_plano_individual_trabalho(request, pk, ano_letivo, periodo_letivo):
    professor = get_object_or_404(Professor, pk=pk)
    if request.user != professor.vinculo.user:
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    ano_letivo = get_object_or_404(Ano, ano=ano_letivo)
    qs = PlanoIndividualTrabalhoV2.objects.filter(professor=professor, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
    instance = qs.first() or PlanoIndividualTrabalhoV2.objects.create(professor=professor, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
    title = str(instance)
    initial = {}
    ch_aulas = instance.get_cargas_horarias()[1]
    if instance.ch_preparacao_manutencao_ensino == 0:
        initial = {'ch_preparacao_manutencao_ensino': ch_aulas}
        instance.ch_preparacao_manutencao_ensino = ch_aulas
    form = PlanoIndividualTrabalhoProfessorForm(data=request.POST or None, instance=instance, initial=initial)
    form.fields[
        'ch_preparacao_manutencao_ensino'
    ].help_text = f'Informe a carga horária que você utilizará para a preparação e manutenção das aulas com um limite de até {ch_aulas} hora(s), que corresponde a sua carga horária de regência no período.'
    if not settings.PERMITE_ALTERACAO_CH_PREPARACAO_AULAS_PIT:
        form.fields['ch_preparacao_manutencao_ensino'].widget.attrs.update(readonly='readonly')
        form.fields['ch_preparacao_manutencao_ensino'].help_text = ''
    form.fields['ch_preparacao_manutencao_ensino'].initial = ch_aulas
    if form.is_valid():
        form.save()
        return httprr('..', 'Plano individual de trabalho cadastrado/atualizado com sucesso.')
    return locals()


@rtr()
@login_required()
def preencher_relatorio_individual_trabalho(request, pk):
    title = 'Relatório Individual de Trabalho'
    obj = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    if not obj.pode_preencher_relatorio(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = RelatorioIndividualTrabalhoProfessorForm(data=request.POST or None, instance=obj, files=request.FILES or None)
    if form.is_valid():
        form.save()
        return httprr('..', 'Relatório individual de trabalho preenchido com sucesso.')
    return locals()


@rtr()
@login_required()
def enviar_plano(request, pk):
    title = 'Enviar Plano Individual de Trabalho'
    pit = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    if not pit.pode_enviar_plano(request.user) and not pit.pode_alterar_avaliador_plano(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = EnviarPlanoForm(data=request.POST or None, instance=pit)
    if form.is_valid():
        form.instance.data_envio = datetime.datetime.now()
        form.save()
        return httprr('..', 'Plano enviado com sucesso.')
    return locals()


@rtr()
@login_required()
def aprovar_plano(request, pk):
    title = 'Aprovar Plano'
    pit = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    if not pit.pode_avaliar_plano(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = ParecerForm(data=request.POST or None, request=request)
    if form.is_valid():
        pit.aprovar_plano(request.user, form.instance)
        return httprr('..', 'Plano aprovado com sucesso.')
    return locals()


@rtr()
@login_required()
def devolver_plano(request, pk):
    title = 'Devolver Plano'
    pit = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    if not pit.pode_avaliar_plano(request.user) and not pit.pode_desfazer_aprovacao_plano(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = ParecerForm(data=request.POST or None, request=request)
    if form.is_valid():
        pit.devolver_plano(request.user, form.instance)
        return httprr('..', 'Plano devolvido com sucesso.')
    return locals()


@rtr()
@login_required()
def entregar_relatorio(request, pk):
    pit = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    if not pit.pode_enviar_relatorio(request.user) and not pit.pode_alterar_avaliador_relatorio(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = EntregarRelatorioForm(data=request.POST or None, instance=pit)
    if form.is_valid():
        form.instance.data_envio_relatorio = datetime.datetime.now()
        form.save()
        return httprr('..', 'Plano enviado com sucesso.')
    return locals()


@rtr()
@login_required()
def aprovar_relatorio(request, pk):
    title = 'Aprovar Relatório'
    pit = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    if not pit.pode_avaliar_relatorio(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = AprovarRelatorioForm(data=request.POST or None, request=request)
    if form.is_valid():
        pit.aprovar_relatorio(request.user, form.instance, form.cleaned_data.get('responsavel_publicacao'))
        return httprr('..', 'Relatório aprovado com sucesso.')
    return locals()


@rtr()
@login_required()
def devolver_relatorio(request, pk):
    title = 'Devolver Relatório'
    pit = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    if not pit.pode_avaliar_relatorio(request.user) and not pit.pode_desfazer_aprovacao_relatorio(request.user):
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = ParecerForm(data=request.POST or None, request=request)
    if form.is_valid():
        pit.devolver_relatorio(request.user, form.instance)
        return httprr('..', 'Relatório devolvido com sucesso.')
    return locals()


@rtr()
@login_required()
def criar_plano(request, professor_id):
    title = 'Criar Plano Individual de Trabalho'
    professor = get_object_or_404(Professor, pk=professor_id)
    if professor.vinculo != request.user.get_vinculo():
        return httprr('/', 'Você não tem permissão para acessar essa página', tag='error')
    form = CriarPlanoIndividualTrabalhoForm(data=request.POST or None, request=request)
    if form.is_valid():
        obj = form.processar(professor_id)
        url = f'/edu/professor/{professor_id}/?tab=planoatividades&ano-periodo={obj.ano_letivo}.{obj.periodo_letivo}'
        return httprr(url, 'Ação realizada com sucesso.')
    return locals()


def relatorio_atividade_docente_pdf(request, pk):
    return plano_atividade_docente_pdf(request, pk, True)


@documento()
@rtr()
def plano_atividade_docente_pdf(request, pk, relatorio=False):
    title = relatorio and 'RELATÓRIO INDIVIDUAL DE TRABALHO' or 'PLANO INDIVIDUAL DE TRABALHO'
    pit = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    uo = (
        (pit.professor.vinculo.setor and pit.professor.vinculo.setor.uo)
        or (pit.professor.vinculo.relacionamento.setor_lotacao and pit.professor.vinculo.relacionamento.setor_lotacao.uo.equivalente)
        or None
    )
    if not pit.publicado and not request.user.is_authenticated:
        return HttpResponseRedirect('/accounts/login/')
    hoje = datetime.date.today()
    is_servidor = pit.professor.vinculo.eh_servidor()
    funcao_servidor = None
    url = None

    if is_servidor:
        data_inicio = None
        data_fim = None

        servidor = pit.professor.vinculo.relacionamento
        historico_funcoes = servidor.historico_funcao(data_inicio=data_inicio, data_fim=data_fim)
        funcao_servidor = historico_funcoes.last().funcao_display if historico_funcoes.exists() else None
        carga_horaria_servidor = servidor.jornada_trabalho.nome

    vinculos_diarios = pit.get_vinculo_diarios()
    vinculos_diarios_regulares = pit.get_vinculo_diarios(False)
    vinculos_diarios_fics = pit.get_vinculo_diarios(True)
    vinculos_turmas_minicurso = pit.get_vinculos_minicurso()
    diarios_especiais = pit.get_vinculos_diarios_especiais()

    (
        ch_semanal_aulas,
        ch_aulas,
        ch_semanal_diarios,
        ch_semanal_diarios_fic,
        ch_semanal_minicursos,
        ch_semanal_diarios_especiais,
        ch_preparacao_manutencao_ensino,
        ch_apoio_ensino,
        ch_programas_projetos_ensino,
        ch_orientacao_alunos,
        ch_reunioes,
        ch_pesquisa,
        ch_extensao,
        ch_gestao,
        ch_total,
    ) = pit.get_cargas_horarias()
    ch_ensino = ch_aulas + ch_preparacao_manutencao_ensino + ch_apoio_ensino + ch_programas_projetos_ensino + ch_orientacao_alunos + ch_reunioes
    ch_resumo = [
        (ch_aulas, 'AULAS'),
        (ch_preparacao_manutencao_ensino, 'PREPARAÇÃO E MANUTENÇÃO DO ENSINO'),
        (ch_apoio_ensino, 'APOIO AO ENSINO'),
        (ch_programas_projetos_ensino, 'PROGRAMAS OU PROJETOS DE ENSINO'),
        (ch_orientacao_alunos, 'ATENDIMENTO, ACOMPANHAMENTO, AVALIAÇÃO E ORIENTAÇÃO DE ALUNOS'),
        (ch_reunioes, 'REUNIÕES PEDAGÓGICAS, DE GRUPO E AFINS'),
        (ch_pesquisa, 'PESQUISA E INOVAÇÃO'),
        (ch_extensao, 'EXTENSÃO'),
        (ch_gestao, 'GESTÃO E REPRESENTAÇÃO INSTITUCIONAL'),
    ]

    return locals()


@rtr()
def reabrir_relatorio(request, pk):
    title = 'Reabrir Relatório'
    pit = get_object_or_404(PlanoIndividualTrabalhoV2, pk=pk)
    if not pit.pode_desfazer_publicacao_relatorio(request.user):
        return HttpResponseForbidden()
    form = ReabrirRelatorioForm(data=request.POST or None, request=request)
    if form.is_valid():
        response = relatorio_atividade_docente_pdf(request, pk)
        form.processar(pit, response.content)
        return httprr('..', 'Reabertura realizada com sucesso.')
    return locals()
