"""Fluxo: cadastro e gestão do edital de extensão (feature 001).

O ciclo de vida do edital antes de receber projetos: cadastrar (pelo admin), autorizar ou
rejeitar, clonar, carregar o arquivo do edital e notificar os servidores do campus. A regra de
negócio que mais importa está na AUTORIZAÇÃO: edital cadastrado (ou clonado) por Coordenador de
Extensão nasce pendente (``autorizado=None``, ``EditalAdmin.save_model`` e ``Edital.clonar_edital``)
e só o Gerente Sistêmico o autoriza — pendente não aparece para submissão
(``Edital.objects.em_inscricao`` exige ``autorizado=True``).
"""

import datetime
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

GERENCIAR = '/admin/projetos/edital/'
CADASTRAR = '/admin/projetos/edital/add/'
EDITAL = '/projetos/edital/{}/'
AUTORIZAR = '/projetos/autorizar_edital/{}/{}/'
CLONAR = '/projetos/clonar_edital/{}/'
UPLOAD_EDITAL = '/projetos/upload_edital/{}/'
NOTIFICAR = '/projetos/notificar_servidores_edital/{}/'


def _data(dias: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=dias)).strftime('%d/%m/%Y')


@pytest.mark.parametrize(('papel', 'autorizado'), [('gerente', True), ('coordenador_extensao', None)])
def test_cadastro_do_edital(logado_projetos, editais_da_ui, papel, autorizado):
    """O mesmo formulário, dois papéis: o do coordenador de extensão nasce pendente de autorização."""
    from projetos.models import Edital
    from projetos.tests.e2e.conftest import vinculo

    titulo = f'E2E Extensão cadastro {uuid4().hex[:8]}'
    editais_da_ui.append(titulo)
    tela = Tela(logado_projetos(papel)).ir(CADASTRAR)
    tela.preencher_formulario(
        [
            ('Título', 'texto', titulo),
            ('Descrição', 'textarea', 'Descrição do Edital'),
            ('Tipo do Fomento', 'lista', 'Interno'),
            ('Tipo do Edital', 'lista', 'Extensão'),
            ('Forma de Seleção', 'lista', 'Campus'),
            ('Início das Inscrições', 'data', _data(0)),
            ('Fim das Inscrições', 'data', _data(10)),
            ('Início da Pré-Seleção', 'data', _data(11)),
            ('Início da Seleção', 'data', _data(15)),
            ('Fim da Seleção', 'data', _data(17)),
            ('Divulgação da Seleção', 'data', _data(18)),
            ('Valor Financiado por Projeto', 'texto', '10.000,00'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.esperar().sucesso('Edital cadastrado com sucesso.').ver_titulo(f'{titulo} - Edital de Extensão')
    edital = Edital.objects.filter(titulo=titulo).first()
    assert edital is not None, 'a UI disse que salvou, mas não persistiu'
    assert (edital.autorizado, edital.cadastrado_por) == (autorizado, vinculo(papel)), f'autorizado={edital.autorizado}'


@pytest.mark.parametrize(('botao', 'opcao', 'autorizado'), [('Autorizar', 1, True), ('Rejeitar', 2, False)])
def test_gerente_avalia_edital_pendente(logado_projetos, edital_novo, botao, opcao, autorizado):
    from projetos.models import Edital
    from projetos.tests.e2e.conftest import vinculo

    edital = edital_novo(autorizado=None, autorizado_em=None, cadastrado_por=vinculo('coordenador_extensao'))
    tela = Tela(logado_projetos('gerente')).ir(f'{GERENCIAR}?q={edital.titulo}')

    tela.linha(edital.titulo).ver_botao(botao)
    clicar_em(tela, AUTORIZAR.format(edital.pk, opcao))  # o `confirm` nativo é aceito pelo `logado`
    tela.sucesso('Edital avaliado com sucesso.')
    edital.refresh_from_db()
    assert (edital.autorizado, edital.autorizado_por) == (autorizado, vinculo('gerente')), 'a UI disse que avaliou, mas não persistiu'


def test_coordenador_clona_edital_e_o_clone_fica_pendente(logado_projetos, edital_novo, editais_da_ui):
    from projetos.models import Edital
    from projetos.tests.factories import EditalAnexoAuxiliarFactory

    original = edital_novo()
    anexo = EditalAnexoAuxiliarFactory(edital=original)
    titulo = f'E2E Extensão clone {uuid4().hex[:8]}'
    editais_da_ui.append(titulo)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(f'{GERENCIAR}?q={original.titulo}')

    clicar_em(tela, CLONAR.format(original.pk))
    tela.ver_titulo(f'Clonar Edital: {original}')
    tela.preencher_formulario([('Título', 'texto', titulo), ('Descrição', 'textarea', 'Edital clonado')]).clicar_botao('Enviar')

    tela.esperar().sucesso('Edital clonado com sucesso.').ver_titulo(f'{titulo} - Edital de Extensão')
    clone = Edital.objects.filter(titulo=titulo).first()
    assert clone is not None, 'a UI disse que clonou, mas não persistiu'
    assert clone.autorizado is None, 'clone feito por Coordenador de Extensão deveria nascer pendente de autorização'
    assert list(clone.editalanexoauxiliar_set.values_list('nome', flat=True)) == [anexo.nome], 'os anexos do edital não foram clonados'
    assert clone.ofertaprojeto_set.filter(uo=original.ofertaprojeto_set.get().uo).exists(), 'o plano de oferta não foi clonado'


def test_gerente_carrega_o_arquivo_do_edital(logado_projetos, edital_novo):
    from projetos.models import EditalArquivo
    from projetos.tests.e2e.conftest import vinculo

    edital = edital_novo()
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))
    tela.ver_texto('Aguardando submissão do arquivo')

    clicar_em(tela, UPLOAD_EDITAL.format(edital.pk))
    tela.ver_titulo('Adicionar Edital').preencher('Arquivo', 'arquivo', 'arquivo.pdf').clicar_botao('Enviar')

    tela.esperar().sucesso('Arquivo enviado com sucesso.').ver_texto('Histórico de Retificações')
    assert EditalArquivo.objects.filter(edital=edital, vinculo_autor=vinculo('gerente')).exists(), 'a UI disse que enviou, mas não persistiu'


def test_gerente_notifica_os_servidores_do_campus_ofertado(logado_projetos, edital_novo):
    """Notificação vai para os servidores ativos das UOs do plano de oferta (``tasks.notificar_servidores_edital``).

    Assíncrona por desenho; sob teste roda na request e a tela é a da tarefa (``/djtools/process/``).
    """
    from comum.models import RegistroNotificacao
    from projetos.tests.e2e.conftest import vinculo

    edital = edital_novo()
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    clicar_em(tela, NOTIFICAR.format(edital.pk))
    tela.ver_texto('Notificações enviadas com sucesso.')
    recebidas = RegistroNotificacao.objects.filter(vinculo=vinculo('coordenador_projeto'), notificacao__mensagem__contains=edital.titulo)
    assert recebidas.exists(), 'a tarefa terminou, mas o servidor do campus ofertado não foi notificado'


@pytest.mark.parametrize(
    ('rota', 'fase', 'campos'),
    [
        # Só edital pendente é avaliado; um já autorizado não volta a ser avaliado (nem rejeitado).
        (AUTORIZAR, 'inscricao', {'autorizado': True}),
        # Classificar só entre o início da seleção e a divulgação; notificar só em inscrição.
        ('/projetos/executar_rotina_classificacao_edital/{}/', 'divulgado', {}),
        (NOTIFICAR, 'divulgado', {}),
    ],
)
def test_acao_do_gerente_fora_do_estado_do_edital_e_negada(logado_projetos, edital_novo, rota, fase, campos):
    """As ações por GET do edital recusam (403) fora do estado que as permite — sem gravar nada."""
    from projetos.models import Edital
    from projetos.tests.e2e.conftest import janela

    edital = edital_novo(**janela(fase), **campos)
    antes = Edital.objects.filter(pk=edital.pk).values('autorizado', 'autorizado_por').get()

    # O `2` é a opção (rejeitar) de AUTORIZAR; as outras rotas têm um parâmetro só e `format` ignora o excedente.
    assert Tela(logado_projetos('gerente')).buscar(rota.format(edital.pk, 2)).status == 403
    assert Edital.objects.filter(pk=edital.pk).values('autorizado', 'autorizado_por').get() == antes, 'o 403 veio, mas o edital mudou'


def test_autorizacao_do_edital_so_com_opcao_valida(logado_projetos, edital_novo):
    """Opção fora de 1/2 dá 404 e o edital pendente não muda: nem decisão, nem autor, nem data (#17551)."""
    from projetos.models import Edital

    edital = edital_novo(autorizado=None)
    antes = Edital.objects.filter(pk=edital.pk).values('autorizado', 'autorizado_por', 'autorizado_em').get()

    assert Tela(logado_projetos('gerente')).buscar(AUTORIZAR.format(edital.pk, 3)).status == 404
    assert Edital.objects.filter(pk=edital.pk).values('autorizado', 'autorizado_por', 'autorizado_em').get() == antes
