from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from comum.utils import get_uo

# Create your views here.
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse, group_required, httprr, permission_required, rtr
from edu.models import Aluno, SituacaoMatricula
from egressos import tasks as egressos_tasks
from egressos.forms import (
    AtualizacaoCadastralForm,
    CategoriaForm,
    ClonarPesquisaForm,
    CopiarOpcaoForm,
    OpcaoForm,
    PerguntaForm,
    PublicarPesquisaForm,
    ResponderBlocoForm,
)
from egressos.models import Categoria, Opcao, Pergunta, Pesquisa, Resposta


def tem_permissao(request, pesquisa):
    if not request.user.has_perm('egressos.eh_gestor_egressos_sistemico') and get_uo(request.user) not in pesquisa.uo.all():
        raise PermissionDenied


@rtr()
@permission_required('egressos.view_pesquisa')
def pesquisa(request, pk):
    obj = get_object_or_404(Pesquisa, pk=pk)
    title = obj
    tem_permissao(request, obj)

    return locals()


@rtr()
@permission_required('egressos.add_categoria')
def cadastrar_categoria(request, pk, categoria_pk=None):
    pesquisa = get_object_or_404(Pesquisa, pk=pk)
    tem_permissao(request, pesquisa)
    title = 'Cadastro de Categoria'
    if categoria_pk:
        obj = get_object_or_404(Categoria, pk=categoria_pk)
    form = CategoriaForm(request=request, instance=categoria_pk and obj or Categoria(pesquisa=pesquisa), data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Categoria registrada com sucesso.')

    return locals()


@rtr()
@permission_required('egressos.add_pergunta')
def cadastrar_pergunta(request, pk, pergunta_pk=None):
    pesquisa = get_object_or_404(Pesquisa, pk=pk)
    tem_permissao(request, pesquisa)
    title = 'Cadastro de Pergunta'
    if pergunta_pk:
        obj = get_object_or_404(Pergunta, pk=pergunta_pk)
    form = PerguntaForm(request=request, instance=pergunta_pk and obj or Pergunta(pesquisa=pesquisa), data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Pergunta registrada com sucesso.')

    return locals()


@rtr()
@permission_required('egressos.add_opcao')
def cadastrar_opcao(request, pk, opcao_pk=None):
    pergunta = get_object_or_404(Pergunta, pk=pk)
    tem_permissao(request, pergunta.pesquisa)
    title = 'Cadastro de Opção de Pergunta'
    if opcao_pk:
        obj = get_object_or_404(Opcao, pk=opcao_pk)
    form = OpcaoForm(request=request, instance=opcao_pk and obj or Opcao(pergunta=pergunta), data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Opção de pergunta registrada com sucesso.')

    return locals()


@rtr()
@permission_required('egressos.add_opcao')
def copiar_opcoes(request, pk):
    obj = get_object_or_404(Pergunta, pk=pk)
    tem_permissao(request, obj.pesquisa)
    title = 'Copiar Opções de Resposta de uma pergunta anterior'
    form = CopiarOpcaoForm(request=request, pergunta_destino=obj, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if form.processar():
            return httprr('..', 'Opções de resposta copiadas com sucesso.')
        else:
            return httprr('..', 'Falha ao copiar.')

    return locals()


@rtr()
@group_required('Aluno')
def atualizacao_cadastral(request, pk):
    obj = get_object_or_404(Pesquisa, pk=pk)
    if not obj.esta_em_periodo_de_resposta():
        raise PermissionDenied
    aluno = get_object_or_404(Aluno, matricula=request.user.username, situacao__id__in=[SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO])
    title = 'Atualização Cadastral do Egresso'
    form = AtualizacaoCadastralForm(request=request, instance=aluno, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        bloco1 = Categoria.objects.get(pesquisa=obj, ordem=1)
        return httprr(f'/egressos/responder_pesquisa_egressos/bloco/{obj.pk}/{bloco1.pk}/', 'Atualização cadastral realizada com sucesso.')
    return locals()


@rtr()
@group_required('Aluno')
def responder_bloco(request, pk, pk_categoria):
    obj = get_object_or_404(Pesquisa, pk=pk)
    if not obj.esta_em_periodo_de_resposta():
        raise PermissionDenied
    aluno = get_object_or_404(Aluno, matricula=request.user.username, situacao__id__in=[SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO])
    categoria = get_object_or_404(Categoria, pk=pk_categoria)
    title = f'Responder bloco: {categoria}'
    form = ResponderBlocoForm(request=request, categoria=categoria, data=request.POST or None)
    ultimo_bloco = obj.get_ultimo_bloco()
    if request.method == 'POST' and form.is_valid():
        if form.save():
            if obj.get_ultimo_bloco().pk == categoria.pk:
                return httprr(
                    '/', 'Obrigado por responder esta pesquisa. Você pode ver suas respostas no menu Egressos -> Pesquisas de Egresso Respondidas.'
                )
            else:
                proximo_bloco = obj.get_proximo_bloco(aluno=aluno, bloco_atual=categoria)
                return httprr(
                    f'/egressos/responder_pesquisa_egressos/bloco/{obj.pk}/{proximo_bloco.pk}/',
                    f'Bloco <strong>{categoria.titulo}</strong> respondido com sucesso.',
                )
        else:
            return httprr('..', 'Falha.')

    return locals()


@rtr()
@permission_required('egressos.add_pesquisa')
def publicar_pesquisa(request, pk):
    obj = get_object_or_404(Pesquisa, pk=pk)
    tem_permissao(request, obj)
    title = f'Publicar Pesquisa: {obj.titulo}'
    form = PublicarPesquisaForm(request=request, instance=obj, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr(f'/egressos/pesquisa/{obj.pk}/', 'A pesquisa foi publicada e foram enviados os convites para os alunos alvo.')
    return locals()


@rtr()
@permission_required('egressos.add_pesquisa')
def gerar_planilha_alunos_alvo(request, pk):
    obj = get_object_or_404(Pesquisa, pk=pk)
    tem_permissao(request, obj)
    total = obj.get_alunos_alvo().count()
    if total > 65536:
        return httprr(
            f'/egressos/pesquisa/{obj.pk}/',
            'Esta pesquisa inclui mais de 65.536 alunos, o que excede o número máximo de linhas de uma planilha Excel.',
            tag='error',
        )
    return egressos_tasks.relatorio_planilha_alunos_alvo_xls(obj)


@rtr()
@group_required('Aluno')
def pesquisas_respondidas(request):
    title = 'Pesquisas Respondidas'
    pesquisas = Pesquisa.objects.filter(pergunta__resposta__aluno__matricula=request.user.username).distinct()
    for pesquisa in pesquisas:
        pesquisa.bloco1 = Categoria.objects.get(pesquisa=pesquisa, ordem=1)
    return locals()


@rtr()
@permission_required('egressos.add_pesquisa')
def reenviar_convites_alunos_nao_respondentes(request, pk):
    obj = get_object_or_404(Pesquisa, pk=pk)
    tem_permissao(request, obj)
    obj.reenviar_convites_alunos_nao_respondentes()
    return httprr('..', 'Convites reenviados.')


@rtr()
@permission_required('egressos.add_pesquisa')
def clonar_pesquisa(request, pk):
    obj = get_object_or_404(Pesquisa, pk=pk)
    tem_permissao(request, obj)
    title = f'Clonar Pesquisa: {obj}'
    form = ClonarPesquisaForm(
        request=request, titulo=f'[Clonada]{obj.titulo}', descricao=f'[Clonada]{obj.descricao}', pesquisa=obj, data=request.POST or None
    )
    if request.method == 'POST' and form.is_valid():
        pesquisa_clonada = form.processar()
        return httprr(f'/egressos/pesquisa/{pesquisa_clonada.pk}/', 'Pesquisa clonada com sucesso.')
    return locals()


@rtr()
@group_required('Aluno')
def ver_respostas_pesquisa(request, pk):
    obj = get_object_or_404(Pesquisa, pk=pk)
    title = f'Ver respostas da pesquisa: {obj}'
    respostas = Resposta.objects.filter(aluno__matricula=request.user.username, pergunta__pesquisa=obj).order_by('pergunta__categoria__ordem')
    return locals()


@rtr()
@permission_required('egressos.view_pesquisa')
def exportar_respostas(request, pk):
    obj = get_object_or_404(Pesquisa, pk=pk)
    tem_permissao(request, obj)
    primeiras_colunas = ['#', 'Matrícula', 'Nome', 'Curso', 'Diretoria', 'Campus', 'Situação', 'E-mail']
    perguntas = []
    for pergunta in obj.pergunta_set.all():
        perguntas.append(format_(pergunta.conteudo))
    rows = [primeiras_colunas + perguntas]

    alunos_respondentes = Aluno.objects.filter(id__in=Resposta.objects.filter(pergunta__pesquisa=obj).values_list('aluno__id', flat=True).distinct())
    count = 0
    for aluno in alunos_respondentes:
        count += 1
        row = [
            count,
            format_(aluno.matricula),
            format_(aluno.pessoa_fisica.nome),
            format_(aluno.curso_campus),
            format_(aluno.curso_campus.diretoria),
            format_(aluno.curso_campus.diretoria.setor.uo),
            format_(aluno.situacao),
            format_(aluno.email_notificacao),
        ]
        for pergunta in obj.pergunta_set.all():
            resposta_da_pergunta = Resposta.objects.filter(aluno=aluno, pergunta=pergunta)
            if resposta_da_pergunta.exists():
                if pergunta.eh_objetiva():
                    if resposta_da_pergunta[0].resposta_subjetiva:
                        row.append(format_(f'{format_(resposta_da_pergunta[0].opcoes.all())} {resposta_da_pergunta[0].resposta_subjetiva}'))
                    else:
                        row.append(format_(resposta_da_pergunta[0].opcoes))
                else:
                    row.append(format_(resposta_da_pergunta[0].resposta_subjetiva))
            else:
                row.append('')
        rows.append(row)
    return XlsResponse(rows, encoding='UTF-8')
