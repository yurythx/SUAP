"""Fluxo: os cadastros de apoio e a comunicação da Extensão — NEPP, comunicador, comissão de avaliação e retificação do edital.

* **NEPP** (Núcleo de Extensão e Prática Profissional) — qualquer servidor consulta a lista e a
  ficha; quem coordena o núcleo (ou o gerente) mantém a equipe e as fotos.
* **Comunicador** — o gerente escreve aos coordenadores de extensão (assistente de dois passos,
  envio por ``@task``) e relê a mensagem enviada.
* **Comissão de avaliação** — do admin da comissão, os membros (popup) e a lista de e-mails.
* **Retificação do edital** — o arquivo de retificação sai do histórico do edital.

As sondas: quem não coordena o núcleo não mexe na equipe nem nas fotos (as remoções gravam por
GET: o objeto tem de continuar lá); o comunicador e a comissão são do gerente; e a retificação só
sai por quem acessa o edital.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import PAPEIS, PREFIXO, clicar_em, comissao, vinculo

if TYPE_CHECKING:
    from projetos.models import NucleoExtensao

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTA_NEPP = '/projetos/lista_nepp/'
VISUALIZAR_NEPP = '/projetos/visualizar_nepp/{}/'
CADASTRAR_MEMBRO = '/projetos/cadastrar_membro_nepp/{}/'
EXCLUIR_MEMBRO = '/projetos/excluir_membro_nepp/{}/'
CADASTRAR_FOTO = '/projetos/cadastrar_foto_nepp/{}/'
EXCLUIR_FOTO = '/projetos/excluir_foto_nepp/{}/'
MENSAGENS = '/admin/projetos/comunicador/'
NOVA_MENSAGEM = '/projetos/nova_mensagem/'
VER_MENSAGEM = '/projetos/ver_detalhes_mensagem/{}/'
COMISSOES = '/admin/projetos/comissaoedital/'
MEMBROS_DA_COMISSAO = '/projetos/ver_membros_comissao/{}/'
EMAILS_DA_COMISSAO = '/projetos/lista_emails_comissao/{}/'
EDITAL = '/projetos/edital/{}/'
REMOVER_RETIFICACAO = '/projetos/remover_arquivo_retificacao/{}/'


# ---------------------------------------------------------------------------------- NEPP


@pytest.fixture
def nepp(projetos_seed) -> Iterator[NucleoExtensao]:
    """Núcleo do CZN coordenado pelo ``coordenador_projeto`` (um servidor sem papel na Extensão); apagado no fim.

    Não é filho de edital: a cascata dos editais temporários não o leva, e a lista mostra todo
    núcleo ativo — daí o nome com ``uuid``.
    """
    from projetos.tests.factories import NucleoExtensaoFactory

    nucleo = NucleoExtensaoFactory(nome=f'{PREFIXO} NEPP {uuid4().hex[:8]}', uo=projetos_seed.uo, coordenador=vinculo('coordenador_projeto'))
    yield nucleo
    nucleo.delete()


def test_servidor_consulta_a_lista_e_a_ficha_do_nepp(logado_projetos, nepp):
    """Menu "NEPP" → filtro por campus → "Visualizar": a ficha abre sem as ações de quem coordena."""
    tela = Tela(logado_projetos('avaliador')).ir(LISTA_NEPP).ver_titulo('Núcleos de Extensão e Prática Profissional - NEPP')

    tela.preencher('Campus', 'lista', 'CZN').clicar_botao('Enviar')
    tela.esperar().ver_texto(nepp.nome)
    clicar_em(tela, VISUALIZAR_NEPP.format(nepp.pk))
    tela.ver_texto(nepp.nome).ver_texto(nepp.area_atuacao).ver_texto('Nenhum membro da equipe cadastrado.')
    expect(tela.loc(f'//a[@href="{CADASTRAR_MEMBRO.format(nepp.pk)}"]')).to_have_count(0)  # a presença: `clicar_em` no teste abaixo


def test_coordenador_do_nepp_mantem_a_equipe(logado_projetos, nepp):
    """Aba "Equipe": "Adicionar Membro" (servidor pelo autocomplete) e o ícone de excluir (confirm, grava por GET)."""
    from projetos.models import MembroNEPP

    tela = Tela(logado_projetos('coordenador_projeto')).ir(VISUALIZAR_NEPP.format(nepp.pk))

    tela.clicar_aba('Equipe')
    clicar_em(tela, CADASTRAR_MEMBRO.format(nepp.pk))
    tela.preencher('Membro', 'autocomplete', PAPEIS['segundo_avaliador'], 'Segundo Avaliador E2E').clicar_botao('Salvar')
    tela.esperar().sucesso('Membro da equipe cadastrado com sucesso.')
    membro = MembroNEPP.objects.filter(nepp=nepp, membro=vinculo('segundo_avaliador')).first()
    assert membro is not None, 'a UI disse que cadastrou, mas o membro não persistiu'

    tela.clicar_aba('Equipe')
    clicar_em(tela, EXCLUIR_MEMBRO.format(membro.pk))  # `.icon-delete`: o `logado` aceita o confirm
    tela.esperar().sucesso('Membro excluído com sucesso.')
    assert not MembroNEPP.objects.filter(pk=membro.pk).exists(), 'a UI disse que excluiu, mas o membro continua'


def test_coordenador_do_nepp_mantem_as_fotos(logado_projetos, nepp):
    """Aba "Fotos": "Adicionar Foto" (descrição e imagem) e "Remover" (confirm, grava por GET)."""
    from projetos.models import FotoNEPP

    descricao = f'Oficina de compostagem {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(VISUALIZAR_NEPP.format(nepp.pk))

    tela.clicar_aba('Fotos')
    clicar_em(tela, CADASTRAR_FOTO.format(nepp.pk))
    tela.preencher_formulario([('Descrição', 'texto', descricao), ('Imagem', 'arquivo', 'foto.png')]).clicar_botao('Salvar')
    tela.esperar().sucesso('Foto cadastrada com sucesso.')
    foto = FotoNEPP.objects.filter(nepp=nepp, descricao=descricao).first()
    assert foto is not None, 'a UI disse que cadastrou, mas a foto não persistiu'

    tela.clicar_aba('Fotos')
    clicar_em(tela, EXCLUIR_FOTO.format(foto.pk))  # `.btn.danger`: o `logado` aceita o confirm
    tela.esperar().sucesso('Foto excluída com sucesso.')
    assert not FotoNEPP.objects.filter(pk=foto.pk).exists(), 'a UI disse que excluiu, mas a foto continua'


def test_quem_nao_coordena_o_nepp_nao_mexe_nele(logado_projetos, nepp):
    """Servidor alheio ao núcleo: as quatro rotas de manutenção dão 403 e nada é apagado; o gerente abre o cadastro de membro."""
    from projetos.tests.factories import FotoNEPPFactory, MembroNEPPFactory

    membro, foto = MembroNEPPFactory(nepp=nepp, membro=vinculo('avaliador')), FotoNEPPFactory(nepp=nepp)
    rotas = [CADASTRAR_MEMBRO.format(nepp.pk), EXCLUIR_MEMBRO.format(membro.pk), CADASTRAR_FOTO.format(nepp.pk), EXCLUIR_FOTO.format(foto.pk)]
    tela = Tela(logado_projetos('outro_coordenador'))

    respostas = {rota: tela.buscar(rota).status for rota in rotas}
    assert respostas == dict.fromkeys(rotas, 403), f'rotas que não barraram quem não coordena: { {r: s for r, s in respostas.items() if s != 403} }'
    assert (type(membro).objects.filter(pk=membro.pk).exists(), type(foto).objects.filter(pk=foto.pk).exists()) == (True, True)
    assert Tela(logado_projetos('gerente')).buscar(CADASTRAR_MEMBRO.format(nepp.pk)).status == 200


# ---------------------------------------------------------------------------- comunicador


@pytest.fixture
def mensagens_do_teste() -> Iterator[str]:
    """Prefixo dos títulos das mensagens que o teste cria (pela tela ou pela factory); apagadas no fim."""
    from projetos.models import Comunicador

    prefixo = f'{PREFIXO} mensagem {uuid4().hex[:8]}'
    yield prefixo
    Comunicador.objects.filter(titulo__startswith=prefixo).delete()


def test_gerente_escreve_aos_coordenadores_de_extensao(logado_projetos, mensagens_do_teste):
    """ "Mensagens" → "Nova mensagem": destinatários "Coordenadores de extensão" (já marcados no passo 2), título e conteúdo; depois, a mensagem enviada."""
    from projetos.models import Comunicador

    titulo = f'{mensagens_do_teste} prazo do relatório'
    tela = Tela(logado_projetos('gerente')).ir(MENSAGENS)

    clicar_em(tela, NOVA_MENSAGEM)
    tela.ver_titulo('Nova mensagem').preencher('Tipo de destinatários', 'lista', 'Coordenadores de extensão').clicar_botao('Continuar')
    tela.esperar().preencher_formulario([('Título', 'texto', titulo), ('Conteúdo', 'texto rico', 'O prazo do relatorio final termina sexta')])
    tela.clicar_botao('Finalizar')
    tela.esperar().ver_texto('Mensagem enviada com sucesso.')
    mensagem = Comunicador.objects.filter(titulo=titulo).first()
    assert mensagem is not None, 'a UI disse que enviou, mas a mensagem não foi registrada'
    assert 'Coordenador Extensão E2E' in mensagem.destinatarios, (
        f'o Coordenador de Extensão não está entre os destinatários: {mensagem.destinatarios}'
    )

    tela.ir(MENSAGENS)
    clicar_em(tela, VER_MENSAGEM.format(mensagem.pk))
    tela.ver_titulo(f'Mensagem enviada - {titulo}').ver_texto('O prazo do relatorio final termina sexta').ver_texto('Coordenador Extensão E2E')


def test_comunicador_e_do_gerente(logado_projetos, mensagens_do_teste):
    """``view_comunicador``: o Coordenador de Extensão não escreve nem lê as mensagens."""
    from projetos.tests.factories import ComunicadorFactory

    mensagem = ComunicadorFactory(titulo=f'{mensagens_do_teste} aviso', cadastrado_por=vinculo('gerente'))
    tela = Tela(logado_projetos('coordenador_extensao'))
    assert (tela.buscar(NOVA_MENSAGEM).status, tela.buscar(VER_MENSAGEM.format(mensagem.pk)).status) == (403, 403)


# --------------------------------------------------------------------- comissão de avaliação


def test_gerente_ve_membros_e_emails_da_comissao(logado_projetos, edital_novo, email_pessoal_de):
    """Admin da comissão (filtrado pelo edital): "Ver Membros" (popup de leitura) e "Lista de Emails dos Membros"."""
    from projetos.models import ComissaoEdital

    edital = edital_novo()
    comissao(edital, 'avaliador', 'segundo_avaliador')
    membro = ComissaoEdital.objects.get(edital=edital)
    email = email_pessoal_de('avaliador')
    tela = Tela(logado_projetos('gerente')).ir(f'{COMISSOES}?edital__id__in={edital.pk}')

    clicar_em(tela, MEMBROS_DA_COMISSAO.format(membro.pk))  # popup sem form: `popup_em` travaria (armadilha 77)
    tela.popup().ver_texto('Avaliador Extensão E2E').ver_texto('Segundo Avaliador E2E')

    tela.ir(f'{COMISSOES}?edital__id__in={edital.pk}')
    clicar_em(tela, EMAILS_DA_COMISSAO.format(membro.pk))
    tela.ver_texto('Todos os membros - 2').ver_texto(email)


def test_comissao_e_do_gerente(logado_projetos, edital_novo):
    from projetos.models import ComissaoEdital

    edital = edital_novo()
    comissao(edital, 'avaliador')
    pk = ComissaoEdital.objects.get(edital=edital).pk
    tela = Tela(logado_projetos('coordenador_extensao'))
    assert (tela.buscar(MEMBROS_DA_COMISSAO.format(pk)).status, tela.buscar(EMAILS_DA_COMISSAO.format(pk)).status) == (403, 403)


# ------------------------------------------------------------------ retificação do edital


def test_gerente_remove_a_retificacao_do_edital(logado_projetos, edital_novo):
    """ "Histórico de Retificações" do edital: o ícone de excluir (confirm, grava por GET) tira o arquivo."""
    from projetos.models import EditalArquivo
    from projetos.tests.factories import EditalArquivoFactory

    edital = edital_novo()
    arquivo = EditalArquivoFactory(edital=edital)
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.ver_texto('Histórico de Retificações')
    clicar_em(tela, REMOVER_RETIFICACAO.format(arquivo.pk))
    tela.esperar().sucesso('Retificação removida com sucesso.')
    assert not EditalArquivo.objects.filter(pk=arquivo.pk).exists(), 'a UI disse que removeu, mas a retificação continua'


def test_retificacao_de_edital_sem_acesso_nao_sai(logado_projetos, edital_de_outro_campus):
    """O Coordenador de Extensão sem acesso ao edital (``tem_permissao_acesso_edital``) recebe 403 — e o arquivo fica."""
    from projetos.models import EditalArquivo
    from projetos.tests.factories import EditalArquivoFactory

    arquivo = EditalArquivoFactory(edital=edital_de_outro_campus)
    assert Tela(logado_projetos('coordenador_extensao')).buscar(REMOVER_RETIFICACAO.format(arquivo.pk)).status == 403
    assert EditalArquivo.objects.filter(pk=arquivo.pk).exists(), 'uma rota que respondeu 403 removeu a retificação'
