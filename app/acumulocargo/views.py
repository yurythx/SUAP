from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from acumulocargo.models import DeclaracaoAcumulacaoCargo, PeriodoDeclaracaoAcumuloCargos
from djtools import layout
from djtools.utils import documento, group_required, httprr, rtr, permission_required


@layout.inscricao()
def index_inscricao(request):
    """Retorna pendências de Termo de Acúmulo de Cargos para o servidor logado.

    Verifica se existe período aberto para cadastro e, conforme o servidor já
    tenha ou não declaração no período, devolve link para edição ou criação.

    Args:
        request: requisição HTTP usada para identificar o usuário/servidor logado.

    Returns:
        list[dict]: pendências contendo ``url``, ``titulo`` e ``prazo`` quando aplicável;
        lista vazia caso o usuário não seja servidor elegível ou não haja período aberto.
    """
    pendencias = []

    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        if not servidor.eh_estagiario:
            periodo = PeriodoDeclaracaoAcumuloCargos.periodo_aberto_para_cadastro(servidor).first()
            if periodo:
                declaracao = DeclaracaoAcumulacaoCargo.objects.filter(periodo_declaracao_acumulo_cargo=periodo, servidor=servidor).first()
                if declaracao:
                    pendencias.append(
                        {
                            'url': f'/admin/acumulocargo/declaracaoacumulacaocargo/{declaracao.id}/change/',
                            'titulo': 'Você ainda pode editar o seu <strong>Termo de Acúmulo de Cargos</strong>.',
                            'prazo': periodo.data_fim,
                        }
                    )
                else:
                    pendencias.append(
                        {
                            'url': '/admin/acumulocargo/declaracaoacumulacaocargo/add/',
                            'titulo': f'Preencha o <strong>Termo de Acúmulo de Cargos {periodo.ano}</strong>.',
                            'prazo': periodo.data_fim,
                        }
                    )

    return pendencias


@rtr()
@permission_required('acumulocargo.pode_ver_declaracao')
def ver_declaracao(request, pk):
    declaracao = get_object_or_404(DeclaracaoAcumulacaoCargo, pk=pk)
    servidor = declaracao.servidor

    if not pode_ver_declaracao(request, declaracao):
        return httprr('/admin/acumulocargo/declaracaoacumulacaocargo/', 'Você não tem permissão para acessar esta declaração.', tag='error')

    title = f'{servidor} - Declaração de {declaracao.periodo_declaracao_acumulo_cargo.ano}'
    cargo_funcao = '{} {}'.format(servidor.cargo_emprego, servidor.funcao or '')

    """ Cargos acumuláveis """
    cargos_acumulaveis = declaracao.cargopublicoacumulavel_set.all()

    """ Tem Aposentadoria """
    aposentadorias = declaracao.temaposentadoria_set.all()

    """ Tem Pensão """
    pensoes = declaracao.tempensao_set.all()

    """ Tem Atuação Gerencial """
    atuacoes_gerenciais = declaracao.tematuacaogerencial_set.all()
    mostrar_atuacoes_gerenciais = True
    if atuacoes_gerenciais:
        atuacao = atuacoes_gerenciais[0]
        if atuacao.nao_exerco_atuacao_gerencial or atuacao.nao_exerco_comercio:
            mostrar_atuacoes_gerenciais = False

    """ Exerce Atividade Remunerada Privada """
    atividades_remuneradas = declaracao.exerceatividaderemuneradaprivada_set.all()
    mostrar_atividades_remuneradas = True
    if atividades_remuneradas:
        atividade = atividades_remuneradas[0]
        if atividade.nao_exerco_atividade_remunerada:
            mostrar_atividades_remuneradas = False

    return locals()


@documento(enumerar_paginas=False)
@rtr()
@login_required()
@group_required('Coordenador de Gestão de Pessoas Sistêmico')
def imprimir_declaracoes(request, pk):
    questionario = get_object_or_404(PeriodoDeclaracaoAcumuloCargos, pk=pk)
    declaracoes = DeclaracaoAcumulacaoCargo.objects.filter(periodo_declaracao_acumulo_cargo=questionario)
    return locals()


def pode_ver_declaracao(request, declaracao):
    return request.user.is_superuser or eh_rh(request) or eh_dono(request, declaracao)


def eh_dono(request, declaracao):
    return request.user.is_authenticated and declaracao.servidor_id == request.user.get_profile().id


def eh_rh(request):
    return request.user.has_perm('rh.change_servidor')
