"""Matriz de acesso das telas de submissão do projeto — por papel e por objeto.

Toda tela de edição do projeto passa por ``tem_permissao`` (``projetos/views.py:2671``): só o
coordenador, o auxiliar ou o gerente sistêmico. A permissão de grupo
(``pode_interagir_com_projeto``) é larga — Servidor, Aluno, Prestador de Serviço, Usuário
Externo a têm —, então a checagem de OBJETO é a que protege. Este arquivo mede as duas:

* por papel, na edição do projeto;
* por objeto, o padrão de #17488 (acesso checado contra o pai da URL, filho buscado só pelo id):
  cada rota de filho (meta, atividade, desembolso, caracterização, anexo, participação) aberta
  pelo coordenador de OUTRO projeto tem de dar 403 com o filho intacto — é o controle positivo
  que mostra que essas views derivam o projeto do próprio filho. A ``memoria_calculo`` não
  deriva: recebe o item em ``?edit_id``/``?del_id`` e confia no projeto da URL (``xfail``).
"""

from urllib.parse import urlencode

import pytest

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import outra_uo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAR_PROJETO = '/projetos/editar_projeto/{}/'
IMPRIMIR_PROJETO = '/projetos/imprimir_projeto/{}/'
MEMORIA_CALCULO = '/projetos/memoria_calculo/{}/'
EXCLUIR_DESEMBOLSOS = '/projetos/excluir_desembolsos/{}/'

# Rota -> atributo do ``projeto_alheio`` cujo id vai na URL.
ROTAS_DO_ALHEIO = {
    EDITAR_PROJETO: 'projeto',
    '/projetos/adicionar_meta/{}/': 'projeto',
    MEMORIA_CALCULO: 'projeto',
    '/projetos/adicionar_desembolso/{}/': 'projeto',
    EXCLUIR_DESEMBOLSOS: 'projeto',
    '/projetos/adicionar_caracterizacao_beneficiario/{}/': 'projeto',
    '/projetos/adicionar_anexo_diverso_projeto/{}/': 'projeto',
    '/projetos/concluir_planejamento/{}/': 'projeto',
    '/projetos/alterar_coordenador/{}/': 'projeto',
    '/projetos/indicar_auxiliar_projeto/{}/': 'projeto',
    '/projetos/editar_meta/{}/': 'meta',
    '/projetos/remover_meta/{}/': 'meta',
    '/projetos/adicionar_etapa/{}/': 'meta',
    '/projetos/clonar_etapa/{}/': 'meta',
    '/projetos/editar_etapa/{}/': 'etapa',
    '/projetos/editar_equipe_etapa/{}/': 'etapa',
    '/projetos/remover_etapa/{}/': 'etapa',
    '/projetos/editar_desembolso/{}/': 'desembolso',
    '/projetos/remover_desembolso/{}/': 'desembolso',
    '/projetos/editar_caracterizacao_beneficiario/{}/': 'caracterizacao',
    '/projetos/remover_caracterizacao_beneficiario/{}/': 'caracterizacao',
    '/projetos/upload_outro_anexo/{}/': 'anexo',
    '/projetos/excluir_outro_anexo/{}/': 'anexo',
    '/projetos/adicionar_anexo_do_projeto/{}/': 'participacao',
}


@pytest.mark.parametrize(
    ('papel', 'status'),
    [
        ('coordenador_projeto', 200),
        # `tem_permissao` aceita o gerente sistêmico (`pode_gerenciar_edital`) em qualquer projeto.
        ('gerente', 200),
        ('coordenador_extensao', 403),
        ('avaliador', 403),
        ('aluno', 403),
    ],
)
def test_edicao_do_projeto_por_papel(logado_projetos, projeto_novo, papel, status):
    projeto = projeto_novo()
    assert Tela(logado_projetos(papel)).buscar(EDITAR_PROJETO.format(projeto.pk)).status == status


def test_coordenador_nao_alcanca_os_filhos_de_projeto_alheio(logado_projetos, projeto_alheio):
    """Cada rota, com o id do objeto do OUTRO projeto, responde 403 — e nada é apagado pelas remoções por GET."""
    tela = Tela(logado_projetos('coordenador_projeto'))

    respostas = {rota: tela.buscar(rota.format(getattr(projeto_alheio, alvo).pk)).status for rota, alvo in ROTAS_DO_ALHEIO.items()}

    assert respostas == dict.fromkeys(ROTAS_DO_ALHEIO, 403), (
        f'rotas que não barraram o estranho: { {r: s for r, s in respostas.items() if s != 403} }'
    )
    for alvo in ('meta', 'etapa', 'item', 'desembolso', 'caracterizacao', 'anexo'):
        objeto = getattr(projeto_alheio, alvo)
        assert type(objeto).objects.filter(pk=objeto.pk).exists(), f'{alvo} do projeto alheio foi apagado por uma rota que respondeu 403'


def test_coordenador_nao_remove_memoria_de_calculo_alheia(logado_projetos, projeto_novo, projeto_alheio):
    from projetos.models import ItemMemoriaCalculo

    proprio = projeto_novo()
    item = projeto_alheio.item

    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(f'{MEMORIA_CALCULO.format(proprio.pk)}?del_id={item.pk}')
    assert ItemMemoriaCalculo.objects.filter(pk=item.pk, projeto=projeto_alheio.projeto).exists(), 'apagou o item de projeto alheio'
    # 403 ou 404: a correção natural é buscar o item DENTRO do projeto (`get_object_or_404(..., projeto=projeto)`).
    assert resposta.status in (403, 404), f'respondeu {resposta.status} a um pedido para remover item de projeto alheio'


def test_coordenador_nao_toma_memoria_de_calculo_alheia(logado_projetos, projeto_novo, projeto_alheio):
    from projetos.models import ItemMemoriaCalculo

    proprio = projeto_novo()
    item = projeto_alheio.item
    rota = f'{MEMORIA_CALCULO.format(proprio.pk)}?edit_id={item.pk}'
    tela = Tela(logado_projetos('coordenador_projeto'))

    if tela.buscar(rota).status == 200:  # o defeito: a edição do item alheio abre, preenchida
        tela.ir(rota).preencher('Quantidade', 'texto', '9').clicar_botao('Salvar')
        tela.esperar()
    agora = ItemMemoriaCalculo.objects.filter(pk=item.pk).values('projeto', 'qtd').first()
    assert agora == {'projeto': projeto_alheio.projeto.pk, 'qtd': item.qtd}, (
        f'o item de projeto alheio foi alterado pela edição da memória de cálculo: {agora} (o da URL é o projeto {proprio.pk})'
    )


def test_termo_de_desligamento_nao_exibe_participante_alheio(logado_projetos, projeto_novo, projeto_alheio):
    """#17494: ``?termo_desligamento`` com a participação de OUTRO projeto não pode abrir a tela com os dados dela."""
    proprio = projeto_novo()
    rota = f'/projetos/adicionar_anexo_diverso_projeto/{proprio.pk}/?termo_desligamento={projeto_alheio.participacao.pk}'
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(rota)
    assert resposta.status == 404, f'respondeu {resposta.status} com a participação de projeto alheio'


def test_aluno_de_fora_nao_imprime_o_projeto(logado_projetos, projeto_alheio):
    resposta = Tela(logado_projetos('aluno')).buscar(f'{IMPRIMIR_PROJETO.format(projeto_alheio.projeto.pk)}?html=1')
    assert resposta.status in (302, 403), f'o aluno que não é da equipe imprimiu o projeto (status {resposta.status})'


def test_lista_do_admin_so_oferece_imprimir_a_quem_pode(logado_projetos, projeto_novo):
    """#17544: o Visualizador de Projetos do Campus lista os projetos de todos os campi, mas só imprime os do próprio.

    O projeto da reitoria aparece na lista e responde 403 na impressão: a coluna "Opções" não pode levar a ele.
    O do próprio campus é o controle positivo: mesmo papel, mesma tela, o botão continua lá.
    """
    from projetos.models import Projeto

    do_campus = projeto_novo()
    da_reitoria = projeto_novo()
    Projeto.objects.filter(pk=da_reitoria.pk).update(uo=outra_uo())
    tela = Tela(logado_projetos('visualizador_campus'))

    def botoes_imprimir(projeto: Projeto) -> int:
        tela.ir(f'/admin/projetos/projeto/?{urlencode({"tab": "tab_any_data", "q": projeto.titulo})}').ver_texto(projeto.titulo)
        return tela.loc(f'//a[@href="{IMPRIMIR_PROJETO.format(projeto.pk)}"]').count()

    assert tela.buscar(IMPRIMIR_PROJETO.format(da_reitoria.pk)).status == 403
    assert botoes_imprimir(da_reitoria) == 0, 'a lista oferece "Imprimir" de projeto que responde 403'
    assert botoes_imprimir(do_campus) == 1, 'a lista deixou de oferecer "Imprimir" do projeto do próprio campus'


def test_remocao_em_lote_por_get_nao_quebra(logado_projetos, projeto_novo):
    projeto = projeto_novo()
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(EXCLUIR_DESEMBOLSOS.format(projeto.pk))
    assert resposta.status < 500, f'GET na remoção em lote devolveu {resposta.status}'
