import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from djtools.templatetags.filters import format_
from djtools.utils import (
    documento,
    group_required,
    httprr,
    permission_required,
    rtr,
)
from edu.forms import (
    AssociarEscolasForm,
    CadastrarEstagioDocenteConcomitanteForm,
    EncerrarEstagioDocenteForm,
    EncerrarEstagioDocenteNaoConcluidoForm,
    EnviarAvaliacaoEstagioDocenteForm,
    EnviarPortfolioEstagioDocenteForm,
    RegistrarMundancaEscolaEstagioDocenteForm,
    VisitaEstagioDocenteForm,
)
from edu.models import EstagioDocente, Professor, VisitaEstagioDocente
from estagios.models import Aprendizagem, AtividadeProfissionalEfetiva, PraticaProfissional


@rtr()
@group_required('Professor')
def cadastrar_visita_estagio_docente(request, pk, visita_pk=None):
    title = 'Registrar Visita do Professor'
    obj = get_object_or_404(EstagioDocente, pk=pk, professor_orientador__vinculo__user=request.user)
    instance = None
    if visita_pk:
        instance = get_object_or_404(VisitaEstagioDocente, pk=visita_pk)
    form = VisitaEstagioDocenteForm(estagio_docente=obj, data=request.POST or None, files=request.FILES or None, instance=instance)
    if form.is_valid():
        visita = form.save(False)
        visita.estagio_docente = obj
        visita.save()
        return httprr('..', 'Visita cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_estagiodocente')
def estagio_docente(request, pk):
    obj = get_object_or_404(EstagioDocente.locals, pk=pk)
    title = f'Estágio Docente - {obj.matricula_diario.diario.componente_curricular.componente.descricao}'
    return locals()


@rtr()
@permission_required('edu.change_estagiodocente')
def associar_escolas(request):
    form = AssociarEscolasForm(data=request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('/edu/associar_escolas/', 'Associação realizada com sucesso.')
    title = f'Estágio Docente - Associar Escola ({form.pendencias.count()} Pendências)'
    return locals()


@rtr()
@group_required('Aluno')
def enviar_portfolio_estagio_docente(request, pk):
    obj = get_object_or_404(EstagioDocente, pk=pk, matricula_diario__matricula_periodo__aluno__vinculos__user=request.user)
    title = 'Enviar o portfólio'
    if obj.data_final_envio_portfolio >= datetime.date.today() and obj.situacao != EstagioDocente.SITUACAO_ENCERRADO:
        title = 'Enviar o portfólio'
        form = EnviarPortfolioEstagioDocenteForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
        if form.is_valid():
            form.save()
            return httprr('..', 'Portfólio enviado com sucesso.')
    else:
        if obj.situacao == EstagioDocente.SITUACAO_ENCERRADO:
            title = 'O estágio docente já está encerrado.'
        else:
            title = f'Prazo para envio do portfólio encerrado. A data final foi: {format_(obj.data_final_envio_portfolio)}'
    return locals()


@rtr()
@group_required('Professor')
def enviar_avaliacao_estagio_docente(request, pk):
    obj = get_object_or_404(EstagioDocente, pk=pk, professor_orientador__vinculo__user=request.user)
    title = 'Enviar a avaliação'
    form = EnviarAvaliacaoEstagioDocenteForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Avaliação enviada com sucesso.')

    return locals()


@rtr()
@permission_required('edu.change_estagiodocente')
def encerrar_estagio_docente(request, pk):
    obj = get_object_or_404(EstagioDocente, pk=pk)
    title = f'Encerrar Estágio Docente de {obj.matricula_diario.matricula_periodo.aluno} por Conclusão'
    form = EncerrarEstagioDocenteForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Estágio docente concluído encerrado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_estagiodocente')
def encerrar_estagio_docente_nao_concluido(request, pk):
    obj = get_object_or_404(EstagioDocente, pk=pk)
    title = f'Encerrar Estágio Docente de {obj.matricula_diario.matricula_periodo.aluno} por Não Conclusão'
    form = EncerrarEstagioDocenteNaoConcluidoForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Estágio docente não concluído encerrado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_estagiodocente')
def cadastrar_estagio_docente_concomitante(request, pk):
    obj = get_object_or_404(EstagioDocente, pk=pk)
    title = f'Adicionar Estágio Docente Concomitante de {obj.matricula_diario.matricula_periodo.aluno}'
    form = CadastrarEstagioDocenteConcomitanteForm(estagio_docente=obj, request=request, data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        form.save()
        return httprr('..', 'Estágio docente concomitante adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_estagiodocente')
def mudanca_escola_estagio_docente(request, pk):
    obj = get_object_or_404(EstagioDocente, pk=pk)
    title = f'Registrar Mudança de Escola do Estágio Docente de {obj.matricula_diario.matricula_periodo.aluno}'
    form = RegistrarMundancaEscolaEstagioDocenteForm(request=request, data=request.POST or None, files=request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Estágio docente transferido de escola com sucesso.')
    return locals()


def _orientacoes(obj: Professor, tipo_estagio: str, ano: str) -> tuple[str, QuerySet, QuerySet, QuerySet, QuerySet]:
    """Rótulo do tipo e orientações do professor no ``ano`` (``'0'`` = todos): estágios docentes, estágios,
    aprendizagens e atividades profissionais efetivas, só a do ``tipo_estagio`` preenchida."""
    estagios_docente = EstagioDocente.objects.none()
    estagios = PraticaProfissional.objects.none()
    aprendizagens = Aprendizagem.objects.none()
    atividades_profissionais_efetivas = AtividadeProfissionalEfetiva.objects.none()
    is_todos_os_anos = ano == '0'
    if tipo_estagio == 'estagios':
        tipo_estagio = 'Estágio'
        if is_todos_os_anos:
            estagios = obj.praticaprofissional_set.all()
        else:
            estagios_concluidos = obj.praticaprofissional_set.exclude(data_fim__isnull=True)
            estagios_nao_concluidos = obj.praticaprofissional_set.exclude(data_fim__isnull=False)
            estagios = estagios_nao_concluidos.filter(data_inicio__year__lte=ano, data_prevista_fim__year__gte=ano) | estagios_concluidos.filter(
                data_inicio__year__lte=ano, data_fim__year__gte=ano
            )
            estagios = estagios.distinct()
    elif tipo_estagio == 'aprendizagens':
        tipo_estagio = 'Aprendizagem'
        if is_todos_os_anos:
            aprendizagens = obj.aprendizagem_set.all()
        else:
            aprendizagens_concluidas = obj.aprendizagem_set.filter(data_encerramento__isnull=True)
            aprendizagens_nao_concluidas = obj.aprendizagem_set.filter(data_encerramento__isnull=False)
            aprendizagens = aprendizagens_nao_concluidas.filter(
                moduloaprendizagem__inicio__year__lte=ano, moduloaprendizagem__fim__year__gte=ano
            ) | aprendizagens_concluidas.filter(moduloaprendizagem__inicio__year__lte=ano, moduloaprendizagem__fim__year__gte=ano)
            aprendizagens = aprendizagens.distinct()
    elif tipo_estagio == 'estagiosdocentes':
        tipo_estagio = 'Estágio Docente'
        if is_todos_os_anos:
            estagios_docente = obj.estagiodocente_orientador_set.all()
        else:
            estagios_docente = obj.estagiodocente_orientador_set.filter(data_inicio__year__lte=ano, data_fim__year__gte=ano)
    elif tipo_estagio == 'atividadesprofissionaisefetivas':
        tipo_estagio = 'Atividade Profissional Efetiva'
        if is_todos_os_anos:
            atividades_profissionais_efetivas = obj.atividadeprofissionalefetiva_set.all()
        else:
            atividades_profissionais_efetivas_concluidas = obj.atividadeprofissionalefetiva_set.exclude(encerramento__isnull=True)
            atividades_profissionais_efetivas_nao_concluidas = obj.atividadeprofissionalefetiva_set.exclude(encerramento__isnull=False)
            atividades_profissionais_efetivas = atividades_profissionais_efetivas_nao_concluidas.filter(
                inicio__year__lte=ano, data_prevista_encerramento__year__gte=ano
            ) | atividades_profissionais_efetivas_concluidas.filter(inicio__year__lte=ano, encerramento__year__gte=ano)
            atividades_profissionais_efetivas = atividades_profissionais_efetivas.distinct()

    return tipo_estagio, estagios_docente, estagios, aprendizagens, atividades_profissionais_efetivas


@login_required()
@documento('Declaração de Orientação', validade=30, modelo='edu.professor', exibe_emissor=True)
@rtr('emitir_declaracao_de_orientacao_pdf.html')
def emitir_declaracao_de_orientacao_pdf(request: HttpRequest, pk: int, tipo_estagio: str, ano: str) -> dict | HttpResponse:
    obj = get_object_or_404(Professor, pk=pk)
    if not obj.pode_emitir_declaracao_docencia(request.user):
        raise PermissionDenied
    nome_professor = obj.vinculo.pessoa.nome
    matricula_siape = obj.vinculo.relacionamento.matricula
    vinculo_usuario = request.user.get_vinculo()
    uo = vinculo_usuario.setor.uo if vinculo_usuario and vinculo_usuario.setor else None
    hoje = datetime.date.today()
    is_todos_os_anos = ano == '0'
    tipo_estagio, estagios_docente, estagios, aprendizagens, atividades_profissionais_efetivas = _orientacoes(obj, tipo_estagio, ano)

    if estagios_docente.exists() or estagios.exists() or aprendizagens.exists() or atividades_profissionais_efetivas.exists():
        return locals()
    else:
        return httprr(f'/edu/professor/{obj.pk}/?tab=estagios', 'Nenhuma orientação registrada para este ano/professor.', 'error')
