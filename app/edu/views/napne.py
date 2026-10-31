import datetime

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, reverse

from comum.models import PrestadorServico
from djtools.utils import (
    httprr,
    permission_required,
    rtr,
)
from edu.forms.napne import (
    AcolhimentoForm,
    AcompanhamentoForm,
    AnexoAcolhimentoForm,
    AtualizarNeesAlunoForm,
    EntrevistaForm,
    FiltroAcolhimentoForm,
    FiltroCampusForm,
    ProfissionalApoioEspecializadoForm,
)
from edu.models import Aluno, Entrevista, MatriculaDiario
from edu.models.napne import (
    Acolhimento,
    AcolhimentoAnexo,
    ApoioEspecializado,
    ProfissionalApoioEspecializado,
)


@rtr('napne/listar_acolhimentos.html')
@permission_required('edu.view_acolhimento')
def listar_acolhimentos(request):
    title = 'Acolhimentos de alunos do Napne'

    def filtrar_acolhidos_por_form(acolhidos, form):
        """Aplica filtros do formulário ao queryset de acolhidos."""
        campos = {
            'sexo': 'aluno__pessoa_fisica__sexo',
            'genero': 'aluno__pessoa_fisica__genero',
            'raca': 'aluno__vinculos__raca',
            'deficiencias': 'aluno__deficiencias__in',
            'outras_nees': 'aluno__outras_nees__in',
            'curso': 'aluno__curso_campus',
            'campus': 'aluno__curso_campus__diretoria__setor__uo',
        }
        texto = form.cleaned_data.get('texto')
        if texto:
            acolhidos = acolhidos.filter(Q(aluno__matricula__icontains=texto) | Q(aluno__pessoa_fisica__nome__icontains=texto))
        for campo, filtro in campos.items():
            valor = form.cleaned_data.get(campo)
            if valor:
                acolhidos = acolhidos.filter(**{filtro: valor})
        return acolhidos

    eh_coordenador_napne = request.user.has_group_cached('Coordenador do Napne')
    eh_coordenador_sistemico_napne = request.user.has_group_cached('Coordenador sistêmico do Napne', ignore_groups_if_superuser=False)
    eh_apoio_especializado_napne = request.user.has_group_cached('Apoio especializado do Napne', ignore_groups_if_superuser=False)
    eh_membro_etep = request.user.has_group_cached('Membro ETEP', ignore_groups_if_superuser=False)
    eh_professor = request.user.has_group_cached('Professor', ignore_groups_if_superuser=False)

    uo = Acolhimento.get_uo_if_grupo_restrito(request.user)
    acolhidos = Acolhimento.objects.all().select_related('aluno')
    if uo:
        acolhidos = acolhidos.filter(aluno__curso_campus__diretoria__setor__uo=uo)
    if eh_professor and not any([eh_coordenador_napne, eh_coordenador_sistemico_napne, eh_apoio_especializado_napne, eh_membro_etep]):
        # Se é professor não é coordenador ou apoio especializado,
        # filtra todos os acolhidos do professor
        vinculo = request.user.get_vinculo()
        alunos_id = (
            MatriculaDiario.objects.filter(diario__professordiario__professor__vinculo=vinculo)
            .values_list('matricula_periodo__aluno_id', flat=True)
            .distinct()
        )
        acolhidos = acolhidos.filter(aluno__id__in=alunos_id)

    formFilter = FiltroAcolhimentoForm(request.POST or None, uo=uo)
    if formFilter.is_valid():
        acolhidos = filtrar_acolhidos_por_form(acolhidos, formFilter)

    acolhidos = acolhidos.order_by('aluno__pessoa_fisica__nome')

    def get_profissionais_apoio_especializado(request, acolhidos):
        """Retorna o queryset de profissionais de apoio especializado conforme o usuário."""
        if eh_apoio_especializado_napne:
            pessoa_fisica = request.user.get_profile()
            qs = ProfissionalApoioEspecializado.objects.filter(
                profissional__pessoa_fisica=pessoa_fisica,
                situacao=ProfissionalApoioEspecializado.ATIVO,
            ).select_related('acolhimento__aluno')
            acolhidos_filtrados = acolhidos.filter(id__in=qs.values_list('acolhimento_id', flat=True)).select_related('aluno')
        else:
            qs = ProfissionalApoioEspecializado.objects.filter(
                acolhimento__in=acolhidos,
                situacao=ProfissionalApoioEspecializado.ATIVO,
            )
            acolhidos_filtrados = acolhidos
        return qs, acolhidos_filtrados

    profissional_apoio_especializado_qs, acolhidos = get_profissionais_apoio_especializado(request, acolhidos)

    sem_entrevista = acolhidos.filter(entrevista__isnull=True)
    sem_apoio_especializado = (
        acolhidos.filter(entrevista__isnull=False)
        .filter(entrevista__parecer=Entrevista.PRECISA_APOIO)
        .exclude(profissionalapoioespecializado__isnull=False)
    ).distinct()
    sem_acompanhamento = (
        profissional_apoio_especializado_qs.exclude(acompanhamentos__isnull=False)
        .select_related('acolhimento__aluno', 'profissional')
        .distinct()
        .order_by('acolhimento__aluno__pessoa_fisica__nome')
    )
    em_acompanhamento = acolhidos.filter(profissionalapoioespecializado__acompanhamentos__isnull=False).distinct()
    return locals()


@rtr()
@permission_required('edu.add_acolhimento')
def adicionar_acolhimento(request, aluno_id=None):
    title = 'Adicionar acolhimento'
    aluno = None
    if aluno_id:
        aluno = get_object_or_404(Aluno, id=aluno_id)

    uo = Acolhimento.get_uo_if_grupo_restrito(request.user)
    form = AcolhimentoForm(request.POST or None, aluno=aluno, uo=uo)
    if request.method == 'POST' and form.is_valid():
        form.save()
        url = reverse('napne_visualizar_acolhimento', args=[form.instance.id])
        return httprr(url, 'Acolhimento adicionado com sucesso!')

    return locals()


@rtr()
@permission_required('edu.change_acolhimento')
def editar_acolhimento(request, acolhimento_id):
    title = 'Editar acolhimento'
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)
    form = AcolhimentoForm(request.POST or None, instance=acolhimento)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Acolhimento alterado.')

    return locals()


@rtr('napne/visualizar_acolhimento.html')
@permission_required('edu.view_acolhimento')
def visualizar_acolhimento(request, acolhimento_id):
    title = 'Visualizar acolhimento'
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)
    pessoa_fisica = request.user.get_profile()
    apoios_acolhimento = ProfissionalApoioEspecializado.objects.filter(
        acolhimento=acolhimento,
        profissional__pessoa_fisica=pessoa_fisica,
        situacao=ProfissionalApoioEspecializado.ATIVO,
    )
    acompanhamentos_sem_profissional = acolhimento.acompanhamentos.filter(profissional_apoio_especializado__isnull=True).order_by(
        'cadastrado_por', 'cadastrado_em'
    )
    total_acompanhamentos = acolhimento.acompanhamentos.count()
    profissionais_apoio_especializado = acolhimento.profissionalapoioespecializado_set.all().order_by('profissional__pessoa_fisica__nome')
    return locals()


@rtr()
@permission_required('edu.change_acolhimento')
def atualizar_nees_aluno(request, acolhimento_id):
    title = 'Atualizar NEEs do aluno'
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)

    # Verificar se o usuário tem permissão (Coordenador do Napne ou Coordenador sistêmico do Napne)
    eh_coordenador_napne = request.user.has_group_cached('Coordenador do Napne')
    eh_coordenador_sistemico_napne = request.user.has_group_cached('Coordenador sistêmico do Napne', ignore_groups_if_superuser=False)

    if not (eh_coordenador_napne or eh_coordenador_sistemico_napne):
        return httprr('..', 'Você não tem permissão para atualizar as NEEs do aluno.', tag='error')

    aluno = acolhimento.aluno
    form = AtualizarNeesAlunoForm(request.POST or None, instance=aluno)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'NEEs do aluno atualizadas com sucesso.')

    return locals()


@rtr()
@permission_required('edu.add_acolhimentoanexo')
def adicionar_anexo(request, acolhimento_id):
    title = 'Adicionar anexo'
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)
    form = AnexoAcolhimentoForm(request.POST or None, request.FILES or None, acolhimento=acolhimento, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Anexo adicionado.')

    return locals()


@rtr()
@permission_required('edu.delete_acolhimentoanexo')
def remover_anexo(request, acolhimento_id, anexo_id):
    title = 'Remover anexo'
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)
    anexo = get_object_or_404(AcolhimentoAnexo, id=anexo_id, acolhimento=acolhimento)
    if request.method == 'POST':
        anexo.delete()
        return httprr(reverse('napne_visualizar_acolhimento', args=[acolhimento.id]) + '?tab=anexos', 'Anexo removido com sucesso.')

    return locals()


@rtr('napne/visualizar_demandas.html')
@permission_required('edu.view_acolhimento')
def visualizar_demandas(request):
    """
    Lista todos os alunos com necessidade educacional específica do campus,
    com situação de matrícula ativa na instituição,
    e ainda não tiveram acolhimento
    """
    title = 'Visualizar demandas do Napne'
    uo = Acolhimento.get_uo_if_grupo_restrito(request.user)
    alunos_sem_acolhimento = []
    if uo:
        # Se tem uo, filtra diretamente pelo uo, sem exibir o form
        alunos_sem_acolhimento = Acolhimento.get_alunos_sem_acolhimento(uo)
    else:
        form = FiltroCampusForm(request.GET or None)
        if form.is_valid():
            campus = form.cleaned_data.get('campus')
            alunos_sem_acolhimento = Acolhimento.get_alunos_sem_acolhimento(campus)

    return locals()


@rtr()
@permission_required('edu.add_entrevista')
def adicionar_entrevista(request, acolhimento_id):
    title = 'Adicionar entrevista'
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)
    form = EntrevistaForm(request.POST or None, acolhimento=acolhimento)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Entrevista adicionada com sucesso.')

    return locals()


@rtr()
@permission_required('edu.add_profissionalapoioespecializado')
def adicionar_profissional_apoio_especializado(request, acolhimento_id):
    title = 'Definir profissional de apoio especializado'
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)
    profissional_id = None
    if request.method == 'POST':
        profissional_id = request.POST.get('profissional')
    form = ProfissionalApoioEspecializadoForm(request.POST or None, acolhimento=acolhimento, profissional_id=profissional_id)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Apoio especializado definido com sucesso.')

    return locals()


# Não é necessário nenhum decorador para GET requests sem CSRF
@permission_required('edu.view_profissionalapoioespecializado')
def listar_profissionais_json(request, acolhimento_id, apoio_id, uo_id):
    """
    View que retorna profissionais (PrestadorServico) que possuem a ocupação informada
    e que estejam ativos (data_fim >= hoje).
    Retorna um JSON com a lista de profissionais."""
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)
    apoio_especializado = get_object_or_404(ApoioEspecializado, id=apoio_id)
    hoje = datetime.date.today()
    profissionais_qs = (
        PrestadorServico.objects.filter(
            ocupacaoprestador__ocupacao_id__in=apoio_especializado.ocupacoes.values_list('id', flat=True),
            ocupacaoprestador__data_inicio__lte=hoje,
            ocupacaoprestador__data_fim__gte=hoje,
            setor__uo=uo_id,
        )
        .exclude(
            profissionalapoioespecializado__acolhimento=acolhimento,
            profissionalapoioespecializado__situacao=ProfissionalApoioEspecializado.ATIVO,
        )
        .distinct()
        .order_by('pessoa_fisica__nome')
        .values('id', 'pessoa_fisica__nome')
    )
    profissionais = [{'id': p['id'], 'nome': p['pessoa_fisica__nome']} for p in profissionais_qs]
    return JsonResponse({'profissionais': profissionais})


@rtr('napne/listar_profissionais.html')
@permission_required('edu.view_apoioespecializado')
def listar_profissionais(request, apoio_id):
    apoio_especializado = get_object_or_404(ApoioEspecializado, id=apoio_id)
    title = apoio_especializado.nome
    hoje = datetime.date.today()
    profissionais = PrestadorServico.objects.filter(
        ocupacaoprestador__ocupacao_id__in=apoio_especializado.ocupacoes.values_list('id', flat=True),
        ocupacaoprestador__data_inicio__lte=hoje,
        ocupacaoprestador__data_fim__gte=hoje,
    ).distinct()
    return locals()


@rtr()
@permission_required('edu.add_acompanhamento')
def adicionar_acompanhamento(request, acolhimento_id, profissional_apoio_especializado_id=None):
    title = 'Adicionar acompanhamento'
    acolhimento = get_object_or_404(Acolhimento, id=acolhimento_id)
    if profissional_apoio_especializado_id is not None:
        profissional_apoio_especializado = get_object_or_404(ProfissionalApoioEspecializado, id=profissional_apoio_especializado_id)
        user_vinculo = getattr(request.user.get_vinculo(), 'id', None)
        profissional_vinculo = getattr(getattr(profissional_apoio_especializado.profissional.get_vinculo(), 'id', None), '__int__', lambda: None)()
        if user_vinculo is None or profissional_vinculo is None or user_vinculo != profissional_vinculo:
            return httprr('..', 'Você não tem permissão para adicionar acompanhamento para este acolhimento.', tag='error')
    else:
        eh_coordenador_napne = request.user.has_group_cached('Coordenador do Napne')
        eh_coordenador_sistemico_napne = request.user.has_group_cached('Coordenador sistêmico do Napne', ignore_groups_if_superuser=False)
        if not (eh_coordenador_napne or eh_coordenador_sistemico_napne):
            return httprr('..', 'Você não tem permissão para adicionar acompanhamento.', tag='error')
        profissional_apoio_especializado = None
    form = AcompanhamentoForm(request.POST or None, acolhimento=acolhimento, profissional_apoio_especializado=profissional_apoio_especializado)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Acompanhamento adicionado com sucesso.')

    return locals()
