"""Fluxo: o ciclo de vida do prestador de serviço / usuário externo, e a ficha do pensionista.

Prestador de serviço é como o SUAP representa quem trabalha na instituição **sem** ser servidor:
terceirizado, bolsista, colaborador de convênio, pensionista. É a porta pela qual gente de fora
ganha usuário, vínculo e papel — e, com eles, acesso a processo eletrônico, assinatura de
documento e crachá. Quem cuida disso é a Gestão de Pessoas; quem liga e desliga a conta é a TI.

O ciclo tem cinco atos, e as oito rotas deste arquivo são eles:

1. **vincular a ocupação** (``ocupacao_prestador``) — é ela que faz o prestador existir de fato:
   ``OcupacaoPrestador.save`` cria o ``rh.Papel``, e a view reativa o ``User`` e marca
   ``pessoa_fisica.eh_prestador`` (``comum/views.py:3143-3150``);
2. **acompanhar** (``prestador_servico``) — a ficha, que é onde a ocupação aparece;
3. **encerrar** (``encerrar_ocupacao_prestador``) — mão única, e com confirmação por senha;
4. **a conta**: criar o papel de usuário externo, ativar e inativar;
5. **o pensionista** (``pensionista``), que é um prestador com matrícula de benefício.

A regressão que o arquivo pega é a do **efeito colateral**, não a da tela: as três ações da conta
(criar papel, ativar, inativar) respondem a mesma mensagem de sucesso e o mesmo redirect
**independentemente** do que aconteceu no banco — ``ativar_usuario_externo`` nem tem ``@rtr()``,
de modo que o caminho de falha devolveria um ``dict`` em vez de resposta. Por isso, aqui, quem
decide o teste é sempre a asserção no ORM.

Nenhum destes fluxos toca um papel de ``PAPEIS``: eles gravam em ``PessoaFisica``, ``Vinculo``,
``User`` e ``rh.Papel``, que são o substrato de todo o SUAP. O prestador nasce e morre no teste.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from comum.tests.e2e.conftest import EMPRESA_DO_SEED, OCUPACAO_DO_SEED
from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
FICHA_DO_PRESTADOR = '/comum/prestador_servico/{pk}/'
VINCULAR_OCUPACAO = '/comum/ocupacao_prestador/{pk}/'
ENCERRAR_OCUPACAO = '/comum/encerrar_ocupacao_prestador/{pk}/'
ALTERAR_FOTO = '/comum/alterar_foto_prestador/{pk}/'
CRIAR_PAPEL_EXTERNO = '/comum/criar_papel_usuario_externo/{pk}/'
ATIVAR_EXTERNO = '/comum/usuario_externo/ativar/{pk}/'
INATIVAR_EXTERNO = '/comum/usuario_externo/inativar/{pk}/'
FICHA_DO_PENSIONISTA = '/comum/pensionista/{matricula}/'

LISTAGEM_DE_PRESTADORES = '/admin/comum/prestadorservico/'


def test_vincular_ocupacao_cria_o_papel_e_publica_na_ficha(logado_comum, prestador_e2e):
    """Vincular a ocupação e conferir que ela apareceu na ficha — as duas rotas num teste só.

    Encadeadas porque a segunda só tem sentido depois da primeira: a ficha do prestador sem
    ocupação nenhuma é uma página vazia, e afirmar que ela abre não afirmaria nada sobre o
    vínculo. Este é o ato que faz o prestador existir para o resto do SUAP.

    A asserção mais importante não está na tela: ``OcupacaoPrestador.save`` cria um ``rh.Papel``
    do tipo ocupação (``comum/models.py:2392-2404``), e é esse papel — não a linha da ocupação —
    que o processo eletrônico e a assinatura digital consultam para saber quem a pessoa é. Uma
    regressão que gravasse a ocupação sem o papel deixaria a tela perfeita e o usuário externo
    incapaz de assinar qualquer coisa.

    ``OcupacaoPrestadorForm.processar`` engole exceção (``comum/forms.py:968-969``,
    ``capture_exception``) e a view responde "Ocupação vinculada com sucesso." de qualquer jeito;
    é por isso que a mensagem aqui é a primeira metade, nunca a prova.
    """
    from comum.models import OcupacaoPrestador
    from rh.models import Papel

    inicio = date.today() - timedelta(days=7)
    fim = date.today() + timedelta(days=365)

    tela = Tela(logado_comum('gestor_pessoal_sistemico')).ir(VINCULAR_OCUPACAO.format(pk=prestador_e2e.pk))
    tela.ver_titulo(f'Vincular Ocupação do Prestador {prestador_e2e}')
    tela.preencher_formulario(
        [
            ('Ocupação', 'autocomplete', OCUPACAO_DO_SEED),
            ('Pessoa Jurídica', 'autocomplete', EMPRESA_DO_SEED),
            ('Data de início', 'data', inicio.strftime('%d/%m/%Y')),
            ('Data fim', 'data', fim.strftime('%d/%m/%Y')),
            ('Setor suap', 'autocomplete', prestador_e2e.setor.sigla),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Ocupação vinculada com sucesso.')

    ocupacao = OcupacaoPrestador.objects.filter(prestador=prestador_e2e).first()
    assert ocupacao, 'a UI disse que vinculou, mas não gravou a ocupação'
    assert ocupacao.data_fim == fim, f'a ocupação foi gravada com data fim {ocupacao.data_fim}, e não a informada'
    assert Papel.objects.filter(vinculo=prestador_e2e.get_vinculo(), tipo_papel=Papel.TIPO_PAPEL_OCUPACAO).exists(), (
        'a ocupação foi gravada sem criar o papel — o usuário externo existe na tela e não existe para o processo eletrônico'
    )

    prestador_e2e.refresh_from_db()
    assert prestador_e2e.ativo, 'vincular ocupação vigente tinha de deixar o prestador ativo'

    tela.ir(FICHA_DO_PRESTADOR.format(pk=prestador_e2e.pk))
    tela.ver_titulo(str(prestador_e2e))
    tela.ver_texto(str(ocupacao.ocupacao))


def test_encerrar_ocupacao_recua_a_data_fim_para_ontem(logado_comum, ocupacao_ativa):
    """Encerrar é uma transição de mão única, confirmada por senha.

    A regra, que só o ORM revela: encerrar **não** apaga a ocupação nem grava "encerrada" — recua
    ``data_fim`` para ontem (``comum/views.py:3193``), porque o histórico do vínculo precisa
    continuar existindo para os documentos já assinados sob ele. Afirmar só a mensagem deixaria
    passar uma regressão que gravasse hoje (a ocupação continuaria vigente) ou que apagasse a
    linha (os documentos assinados perderiam o papel).

    A senha é a do usuário logado de verdade: ``PasswordField.clean`` autentica contra o request
    do threadlocal (``djtools/forms/fields/password.py:40-45``), e não há como burlá-la —
    é a confirmação que separa encerrar por engano de encerrar de propósito.
    """
    from comum.models import OcupacaoPrestador

    tela = Tela(logado_comum('gestor_pessoal_sistemico')).ir(ENCERRAR_OCUPACAO.format(pk=ocupacao_ativa.pk))
    tela.ver_texto('Ao encerrar a ocupação do prestador a data fim da ocupação será alterada para a data de ontem.')

    tela.preencher('Senha para confirmação', 'senha', SENHA_E2E)
    tela.clicar_botao('Enviar')
    tela.sucesso('Ocupação encerrada com sucesso.')

    encerrada = OcupacaoPrestador.objects.get(pk=ocupacao_ativa.pk)
    assert encerrada.data_fim == date.today() - timedelta(days=1), f'a UI disse que encerrou, mas a data fim ficou em {encerrada.data_fim}'
    assert not encerrada.eh_ativa(), 'a ocupação continuou ativa depois de encerrada'


def test_alterar_foto_do_usuario_externo(logado_comum, prestador_e2e):
    """A foto do usuário externo é gravada no ``Vinculo``, não na ``PessoaFisica``.

    Detalhe não óbvio e que é justamente o que o teste protege: ``AtualizarFotoPessoaFisicaForm``
    tem "PessoaFisica" no nome e salva em ``self.vinculo.foto`` (``comum/forms.py:2402``). Quem
    exibe a foto no crachá e na barra do SUAP lê do vínculo — uma regressão que a movesse para a
    pessoa física deixaria a tela dizendo "Foto atualizada com sucesso." e o crachá sem foto.

    ``processar`` devolve **texto** em vez de levantar quando falta permissão
    (``comum/forms.py:2406``), e a view usa esse texto como mensagem de sucesso: sem a asserção no
    vínculo, um "Permissão Negada." apareceria como banner verde.
    """
    tela = Tela(logado_comum('gestor_pessoal_sistemico')).ir(ALTERAR_FOTO.format(pk=prestador_e2e.pk))
    tela.ver_titulo(f'Alterar Foto do Usuário Externo {prestador_e2e}')

    tela.preencher('Arquivo', 'arquivo', 'foto.jpg')
    tela.clicar_botao('Enviar')
    tela.sucesso('Foto atualizada com sucesso.')

    vinculo = prestador_e2e.get_vinculo()
    vinculo.refresh_from_db()
    assert vinculo.foto, 'a UI disse que atualizou a foto, mas o vínculo continuou sem nenhuma'


def test_criar_papel_de_usuario_externo(logado_comum, prestador_e2e):
    """Criar o papel de usuário externo — a rota que transforma um cadastro em uma conta utilizável.

    A view responde a mesma coisa (``httprr`` para a listagem, banner verde) tenha ou não criado
    o papel: o ``if`` que separa os dois desfechos escolhe entre redirecionar e devolver
    ``locals()`` (``comum/views.py:4413-4417``), e o segundo caminho renderizaria um template que
    não existe. Quer dizer: em produção este fluxo só tem um desfecho visível. A asserção é o
    ``rh.Papel`` sem ``data_fim``, que é o que ``tem_papel_ativo_usuario_externo`` consulta.
    """
    from rh.models import Papel

    tela = Tela(logado_comum('gestor_pessoal_sistemico')).ir(CRIAR_PAPEL_EXTERNO.format(pk=prestador_e2e.pk))

    tela.sucesso('Papel de Usuário Externo Criado com Sucesso.')
    assert tela.pagina.url.endswith(LISTAGEM_DE_PRESTADORES), f'a ação não voltou para a listagem de prestadores: {tela.pagina.url}'
    assert Papel.objects.filter(vinculo=prestador_e2e.get_vinculo(), tipo_papel=Papel.TIPO_PAPEL_USUARIOEXTERNO, data_fim__isnull=True).exists(), (
        'a UI disse que criou o papel de usuário externo, mas ele não existe'
    )


def test_ciclo_de_ativacao_da_conta_do_usuario_externo(logado_comum, prestador_e2e):
    """Inativar e reativar a conta — as duas rotas num teste, porque uma desfaz a outra.

    Encadeadas de propósito (regra 1 da receita): ativar um prestador que já está ativo não prova
    nada, então o teste primeiro **inativa** e só então reativa. É também o que descreve a
    operação real: a TI desliga a conta quando o contrato termina e religa quando ele é renovado.

    As duas rotas são guardadas por ``@group_required('Coordenador de TI sistêmico')``, que checa
    o **nome do grupo** e não a permissão — nenhum papel da Gestão de Pessoas as alcança, por mais
    permissões de prestador que tenha. É por isso que existe o papel ``gestor_ti``.

    ``PrestadorServico.ativo`` e ``User.is_active`` andam juntos (``comum/models.py:2269-2277``) e
    é o segundo que decide se a pessoa consegue entrar; afirmar só o primeiro deixaria passar
    exatamente a regressão que deixa um contrato encerrado com login funcionando.
    """
    from comum.models import PrestadorServico

    tela = Tela(logado_comum('gestor_ti')).ir(INATIVAR_EXTERNO.format(pk=prestador_e2e.pk))
    tela.sucesso('Usuário Externo Desativado com Sucesso.')

    inativo = PrestadorServico.objects.get(pk=prestador_e2e.pk)
    assert not inativo.ativo, 'a UI disse que desativou, mas o prestador continuou ativo'
    assert not inativo.get_vinculo().user.is_active, 'o prestador foi desativado mas o usuário continuou podendo entrar no SUAP'

    tela.ir(ATIVAR_EXTERNO.format(pk=prestador_e2e.pk))
    tela.sucesso('Usuário Externo Ativado com Sucesso.')

    ativo = PrestadorServico.objects.get(pk=prestador_e2e.pk)
    assert ativo.ativo, 'a UI disse que ativou, mas o prestador continuou inativo'
    assert ativo.get_vinculo().user.is_active, 'o prestador foi ativado mas o usuário continuou sem poder entrar'


def test_ficha_do_pensionista(logado_comum, pensionista_e2e):
    """A ficha do pensionista, alcançada pela matrícula do benefício e não pelo id.

    ``Pensionista`` é um ``OneToOne`` com ``PrestadorServico``, e a rota o busca por
    ``matricula`` (``comum/urls.py:89``) — é a matrícula do benefício, o número que o pensionista
    conhece e informa no atendimento. A tela é governada por ``comum.view_pensionista``, uma
    permissão que praticamente só a Gestão de Pessoas sistêmica e a auditoria têm, porque o que
    ela mostra são dados de benefício previdenciário.
    """
    tela = Tela(logado_comum('gestor_pessoal_sistemico')).ir(FICHA_DO_PENSIONISTA.format(matricula=pensionista_e2e.matricula))

    tela.ver_titulo(str(pensionista_e2e))
    tela.ver_texto(pensionista_e2e.usuario_externo.pessoa_fisica.nome)


@pytest.mark.parametrize(
    'rota',
    [FICHA_DO_PRESTADOR, VINCULAR_OCUPACAO, ALTERAR_FOTO, CRIAR_PAPEL_EXTERNO],
    ids=['ficha', 'vincular-ocupacao', 'alterar-foto', 'criar-papel'],
)
def test_telas_de_prestador_barram_quem_nao_gerencia_pessoal(logado_comum, prestador_e2e, rota):
    """Matriz de acesso MEDIDA no navegador: ``solicitante`` não alcança nenhuma das quatro.

    Permissão se verifica por status HTTP, nunca por texto: as quatro telas diferem no que
    exigem (``view_prestadorservico`` na ficha, ``change_prestadorservico`` nas outras três) mas
    todas convergem para 403, e é esse o contrato. Vale a pena afirmá-lo porque um ``@rtr()`` sem
    o ``@permission_required`` acima dele é uma linha apagada por engano — e a tela de ocupação
    grava vínculo e papel de gente de fora.
    """
    resposta = Tela(logado_comum('solicitante')).buscar(rota.format(pk=prestador_e2e.pk))

    assert resposta.status == 403, f'{rota} respondeu HTTP {resposta.status} para quem não gerencia prestador de serviço'
