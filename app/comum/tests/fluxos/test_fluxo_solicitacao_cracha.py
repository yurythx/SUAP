"""Fluxo: solicitação de crachá (``DocumentoControle``), do cadastro à exportação.

Percorre, em sequência e trocando de ator, a vida inteira de uma solicitação de crachá:

1. A Gestão de Pessoas cadastra a solicitação no admin sem escolher nome sugerido nem nome
   social — o crachá é recusado, porque é esse nome que vai impresso nele.
2. Escolhido o nome, a solicitação é gravada e o histórico nasce junto.
3. A segunda solicitação do mesmo tipo é recusada enquanto a primeira estiver pendente.
4. Quem não despacha documentos (um servidor comum) não consegue atendê-la.
5. O solicitante acompanha a própria solicitação — e não pode despachá-la.
6. A Gestão de Pessoas atende pela *action* do admin — a situação vira "Atendida" e o
   histórico ganha a linha do despacho.
7. O CSV de conferência da impressora (``/comum/gerar_cvs/``) traz a matrícula do solicitante.

Por que este fluxo e não outro: a suíte e2e do módulo já anda as telas de *despacho*
(atender/rejeitar/acompanhar), mas cria a solicitação por ``bulk_create`` — de propósito,
porque ``DocumentoControle.save`` exige um request no threadlocal. Resultado: o formulário de
cadastro (``DocumentoControleAdminFormFactory``), que é onde moram todas as regras de negócio
do crachá, nunca é executado. Aqui a solicitação nasce pelo HTTP, que é o único caminho em que
essas regras rodam.
"""

from __future__ import annotations

import csv
import datetime
import io

import pytest
from django.contrib.auth.models import Group

from comum.models import (
    ConfiguracaoImpressaoDocumento,
    DocumentoControle,
    DocumentoControleHistorico,
    DocumentoControleTipo,
    User,
)
from djtools.choices import SituacaoSolicitacaoDocumento
from djtools.utils.strings import gera_nomes
from rh.models import Situacao
from rh.tests.factories import ServidorFactory, SetorFactory, SituacaoFactory

ADMIN_ADD = '/admin/comum/documentocontrole/add/'
ADMIN_LISTA = '/admin/comum/documentocontrole/'
VER_SOLICITACAO = '/comum/ver_solicitacao_documento/{pk}/'
MARCAR_ATENDIDA = '/comum/marcar_solicitacao_atendida/{pk}/'
GERAR_CSV = '/comum/gerar_cvs/{pk}/'

GRUPO_GESTAO_PESSOAS = 'Coordenador de Gestão de Pessoas'


def _recarregar(user: User) -> User:
    """Relê o usuário do banco.

    ``User`` guarda as permissões num cache de instância (``_perm_cache``) e o SUAP mantém
    ainda um cache de grupos por processo: depois de mexer em ``groups`` a instância antiga
    continua respondendo o que valia antes, e a view devolve 403 sem motivo aparente.
    """
    recarregado = User.objects.get(pk=user.pk)
    recarregado.get_groups_cached(force=True)
    return recarregado


def _regularizar_cadastro(servidor) -> None:
    """Preenche foto, grupo sanguíneo e fator RH — o que o crachá exige do cadastro.

    Não apague por parecer inócuo: ``DocumentoBaseForm.clean`` recusa crachá e carteira
    funcional de quem não tem os três cadastrados (#17404).
    """
    pessoa_fisica = servidor.pessoa_fisica
    pessoa_fisica.grupo_sanguineo = 'O'
    pessoa_fisica.fator_rh = '+'
    pessoa_fisica.save()
    vinculo = servidor.get_vinculo()
    # Basta o nome do arquivo: o formulário só testa a verdade do campo, não lê a imagem.
    vinculo.foto = 'fotos/cracha.jpg'
    vinculo.save()


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
class TestFluxoSolicitacaoCracha:
    def test_cadastro_atendimento_e_exportacao_do_cracha(self, client) -> None:
        setor = SetorFactory(sigla='GP0')
        campus = setor.uo
        situacao_ativa = SituacaoFactory(codigo=Situacao.ATIVO_PERMANENTE)

        gestor = ServidorFactory(setor=setor)
        gestor_user = gestor.get_user()
        gestor_user.groups.add(Group.objects.get(name=GRUPO_GESTAO_PESSOAS))
        gestor_user = _recarregar(gestor_user)

        solicitante = ServidorFactory(setor=setor, situacao=situacao_ativa)
        vinculo_solicitante = solicitante.get_vinculo()

        tipo_cracha = DocumentoControleTipo.objects.create(identificador=DocumentoControleTipo.CRACHA, descricao='Crachá')
        tipo_cracha.abrangencia.add(situacao_ativa)
        configuracao = ConfiguracaoImpressaoDocumento.objects.create(uo=campus, local_impressao='Natal/RN')
        configuracao.relacao_impressao.add(campus)
        configuracao.tipos_documento.add(tipo_cracha)

        nome_sugerido = gera_nomes(solicitante.pessoa_fisica.nome)[0]
        dados = {
            'documento_tipo': tipo_cracha.pk,
            'solicitante_vinculo': vinculo_solicitante.pk,
            'nome_sugerido': nome_sugerido,
            'nome_social': '',
            'justificativa': 'Primeira via do crachá funcional.',
            'status_solicitacao': SituacaoSolicitacaoDocumento.NAO_ATENDIDA,
            'ativo': 'on',
        }

        _regularizar_cadastro(solicitante)
        client.force_login(gestor_user)

        # 1. Sem nome sugerido nem nome social não há o que imprimir: o formulário recusa.
        resposta = client.post(ADMIN_ADD, {**dados, 'nome_sugerido': ''})
        assert resposta.status_code == 200, 'o formulário deveria ser reexibido com os erros, não redirecionar'
        assert not DocumentoControle.objects.filter(solicitante_vinculo=vinculo_solicitante).exists(), (
            'gravou a solicitação de crachá sem nome sugerido nem nome social'
        )
        assert 'selecione um nome sugerido ou descreva um nome social' in resposta.content.decode()

        # 2. Com o nome escolhido, a solicitação nasce pendente e já com histórico.
        resposta = client.post(ADMIN_ADD, dados, follow=True)
        assert resposta.status_code == 200

        solicitacao = DocumentoControle.objects.get(solicitante_vinculo=vinculo_solicitante, documento_tipo=tipo_cracha)
        assert solicitacao.status_solicitacao == SituacaoSolicitacaoDocumento.NAO_ATENDIDA
        assert solicitacao.nome_sugerido == nome_sugerido
        assert (
            DocumentoControleHistorico.objects.filter(solicitacao=solicitacao, situacao_historico=SituacaoSolicitacaoDocumento.NAO_ATENDIDA).count()
            == 1
        ), 'a abertura da solicitação não gravou a linha inicial do histórico'

        # 3. Enquanto a primeira estiver pendente, a segunda do mesmo tipo é recusada.
        resposta = client.post(ADMIN_ADD, dados)
        assert resposta.status_code == 200
        assert 'já existe uma solicitação pendente' in resposta.content.decode()
        assert DocumentoControle.objects.filter(solicitante_vinculo=vinculo_solicitante, documento_tipo=tipo_cracha).count() == 1, (
            'aceitou uma segunda solicitação pendente do mesmo tipo de documento'
        )

        # 4. Quem não está na Gestão de Pessoas não consegue despachar a solicitação alheia.
        estranho = ServidorFactory(setor=SetorFactory(sigla='OUTRO'))
        client.force_login(_recarregar(estranho.get_user()))
        resposta = client.get(MARCAR_ATENDIDA.format(pk=solicitacao.pk))
        assert resposta.status_code in (302, 403), 'servidor sem `comum.change_documentocontrole` conseguiu atender'
        assert DocumentoControle.objects.get(pk=solicitacao.pk).status_solicitacao == SituacaoSolicitacaoDocumento.NAO_ATENDIDA, (
            'a solicitação mudou de situação para quem não despacha documentos'
        )

        # 5. O solicitante acompanha a própria solicitação.
        client.force_login(_recarregar(solicitante.get_user()))
        resposta = client.get(VER_SOLICITACAO.format(pk=solicitacao.pk))
        assert resposta.status_code == 200
        assert resposta.context['verificacao_propria'] is True
        assert resposta.context['pode_atender_solicitacao'] is False, 'o próprio solicitante não pode despachar a solicitação dele'

        # 6. A Gestão de Pessoas atende pela ação em lote do admin.
        client.force_login(gestor_user)
        resposta = client.post(
            ADMIN_LISTA,
            {'action': 'atender', '_selected_action': [str(solicitacao.pk)], 'index': '0'},
            follow=True,
        )
        assert resposta.status_code == 200
        solicitacao.refresh_from_db()
        assert solicitacao.status_solicitacao == SituacaoSolicitacaoDocumento.ATENDIDA, (
            'a ação "Atender" do admin não mudou a situação da solicitação'
        )
        assert DocumentoControleHistorico.objects.filter(
            solicitacao=solicitacao, situacao_historico=SituacaoSolicitacaoDocumento.ATENDIDA
        ).exists(), 'o atendimento não deixou rastro no histórico'

        # 7. O CSV de conferência da impressora lista o solicitante.
        resposta = client.get(GERAR_CSV.format(pk=tipo_cracha.pk))
        assert resposta.status_code == 200
        assert resposta['Content-Type'] == 'text/csv'
        linhas = list(csv.reader(io.StringIO(resposta.content.decode())))
        matriculas = [linha[2] for linha in linhas[1:]]
        assert solicitante.matricula in matriculas, 'a solicitação atendida não apareceu no CSV do tipo de documento'
        assert len(matriculas) == DocumentoControle.objects.filter(documento_tipo=tipo_cracha, ativo=True).count()

    def test_situacao_funcional_fora_da_abrangencia_nao_solicita_cracha(self, client) -> None:
        """Quem está numa situação funcional fora da abrangência do crachá não pode pedir um.

        A abrangência é o que amarra o documento à situação do servidor (aposentado e
        exonerado não recebem crachá). Sem ela o formulário de crachá sequer é montado: o
        usuário cai no formulário-base, que não tem solicitante e recusa o cadastro.
        """
        setor = SetorFactory(sigla='GP1')
        campus = setor.uo
        ativo_permanente = SituacaoFactory(codigo=Situacao.ATIVO_PERMANENTE)
        aposentado = SituacaoFactory(codigo='03', nome_siape='APOSENTADO')

        gestor = ServidorFactory(setor=setor, situacao=aposentado)
        gestor_user = gestor.get_user()
        gestor_user.groups.add(Group.objects.get(name=GRUPO_GESTAO_PESSOAS))
        gestor_user = _recarregar(gestor_user)
        _regularizar_cadastro(gestor)

        tipo_cracha = DocumentoControleTipo.objects.create(identificador=DocumentoControleTipo.CRACHA, descricao='Crachá')
        tipo_cracha.abrangencia.add(ativo_permanente)
        configuracao = ConfiguracaoImpressaoDocumento.objects.create(uo=campus, local_impressao='Natal/RN')
        configuracao.relacao_impressao.add(campus)
        configuracao.tipos_documento.add(tipo_cracha)

        client.force_login(gestor_user)
        resposta = client.post(
            ADMIN_ADD,
            {
                'documento_tipo': tipo_cracha.pk,
                'solicitante_vinculo': gestor.get_vinculo().pk,
                'nome_sugerido': gera_nomes(gestor.pessoa_fisica.nome)[0],
                'justificativa': 'Crachá para servidor aposentado.',
            },
        )

        assert resposta.status_code == 200
        assert not DocumentoControle.objects.filter(documento_tipo=tipo_cracha).exists(), (
            'gravou crachá para situação funcional fora da abrangência do documento'
        )
        assert 'Situação Funcional não está habilitada' in resposta.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_csv_do_tipo_de_documento_ignora_solicitacoes_inativas(client) -> None:
    """O CSV de conferência é a lista do que ainda vale: solicitação inativa não vai para lá.

    ``DocumentoControle.atender_solicitacao`` inativa os atendimentos anteriores do mesmo
    servidor para o mesmo documento — é assim que a segunda via não faz a impressora
    reimprimir a primeira.
    """
    setor = SetorFactory(sigla='GP2')
    gestor = ServidorFactory(setor=setor)
    gestor_user = gestor.get_user()
    gestor_user.groups.add(Group.objects.get(name=GRUPO_GESTAO_PESSOAS))
    gestor_user = _recarregar(gestor_user)

    tipo = DocumentoControleTipo.objects.create(identificador=DocumentoControleTipo.CRACHA, descricao='Crachá')
    vinculo = gestor.get_vinculo()
    DocumentoControle.objects.bulk_create(
        [
            DocumentoControle(
                documento_tipo=tipo,
                solicitante_vinculo=vinculo,
                justificativa='Via antiga',
                ativo=False,
                status_solicitacao=SituacaoSolicitacaoDocumento.ATENDIDA,
                data_solicitacao=datetime.datetime.now(),
            ),
            DocumentoControle(
                documento_tipo=tipo,
                solicitante_vinculo=vinculo,
                justificativa='Via corrente',
                ativo=True,
                status_solicitacao=SituacaoSolicitacaoDocumento.NAO_ATENDIDA,
                data_solicitacao=datetime.datetime.now(),
            ),
        ]
    )

    client.force_login(gestor_user)
    resposta = client.get(GERAR_CSV.format(pk=tipo.pk))

    linhas = list(csv.reader(io.StringIO(resposta.content.decode())))
    assert len(linhas) - 1 == DocumentoControle.objects.filter(documento_tipo=tipo, ativo=True).count()


def _sem_foto(servidor) -> None:
    vinculo = servidor.get_vinculo()
    vinculo.foto = None
    vinculo.save()


def _sem_grupo_sanguineo(servidor) -> None:
    servidor.pessoa_fisica.grupo_sanguineo = None
    servidor.pessoa_fisica.save()


def _sem_fator_rh(servidor) -> None:
    servidor.pessoa_fisica.fator_rh = ''
    servidor.pessoa_fisica.save()


def _preparar_solicitacao(identificador: str | None, sigla: str) -> tuple[User, object, DocumentoControleTipo]:
    """Monta gestor, solicitante com cadastro regular e o tipo de documento pedido, impresso no campus.

    O crachá existe sempre: ``DocumentoControleAdminFormFactory`` lê a abrangência dele para
    decidir qual formulário montar, qualquer que seja o documento pedido.
    """
    setor = SetorFactory(sigla=sigla)
    campus = setor.uo
    situacao_ativa = SituacaoFactory(codigo=Situacao.ATIVO_PERMANENTE)

    gestor = ServidorFactory(setor=setor)
    gestor_user = gestor.get_user()
    gestor_user.groups.add(Group.objects.get(name=GRUPO_GESTAO_PESSOAS))

    solicitante = ServidorFactory(setor=setor, situacao=situacao_ativa)
    _regularizar_cadastro(solicitante)

    tipo_cracha = DocumentoControleTipo.objects.create(identificador=DocumentoControleTipo.CRACHA, descricao='Crachá')
    tipo_cracha.abrangencia.add(situacao_ativa)
    tipo = tipo_cracha
    if identificador != DocumentoControleTipo.CRACHA:
        tipo = DocumentoControleTipo.objects.create(identificador=identificador, descricao='Outro documento')
        tipo.abrangencia.add(situacao_ativa)
    configuracao = ConfiguracaoImpressaoDocumento.objects.create(uo=campus, local_impressao='Natal/RN')
    configuracao.relacao_impressao.add(campus)
    configuracao.tipos_documento.add(tipo)
    return _recarregar(gestor_user), solicitante, tipo


def _solicitar(client, solicitante, tipo: DocumentoControleTipo):
    return client.post(
        ADMIN_ADD,
        {
            'documento_tipo': tipo.pk,
            'solicitante_vinculo': solicitante.get_vinculo().pk,
            'nome_sugerido': gera_nomes(solicitante.pessoa_fisica.nome)[0],
            'nome_social': '',
            'justificativa': 'Primeira via.',
            'status_solicitacao': SituacaoSolicitacaoDocumento.NAO_ATENDIDA,
            'ativo': 'on',
        },
        follow=True,
    )


DOCUMENTOS_COM_CADASTRO = [DocumentoControleTipo.CRACHA, DocumentoControleTipo.CARTEIRA_FUNCIONAL]


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
@pytest.mark.parametrize('identificador', DOCUMENTOS_COM_CADASTRO)
@pytest.mark.parametrize(
    ('desregularizar', 'pendencia'),
    [
        (_sem_foto, 'foto cadastrada'),
        (_sem_grupo_sanguineo, 'grupo sanguíneo cadastrado'),
        (_sem_fator_rh, 'fator RH cadastrado'),
    ],
)
def test_cracha_e_carteira_exigem_foto_grupo_sanguineo_e_fator_rh(client, identificador: str, desregularizar, pendencia: str) -> None:
    """Crachá e carteira funcional imprimem foto e tipo sanguíneo: sem eles no cadastro, a solicitação é recusada (#17404)."""
    gestor_user, solicitante, tipo = _preparar_solicitacao(identificador, 'GP3')
    desregularizar(solicitante)

    client.force_login(gestor_user)
    resposta = _solicitar(client, solicitante, tipo)

    assert resposta.status_code == 200
    assert not DocumentoControle.objects.filter(documento_tipo=tipo).exists(), f'gravou {identificador} de quem não tem {pendencia}'
    conteudo = resposta.content.decode()
    assert f'O solicitante não tem {pendencia}' in conteudo
    assert 'para atualizar o cadastro do solicitante' in conteudo, 'a recusa não diz onde regularizar o cadastro'


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
@pytest.mark.parametrize('identificador', DOCUMENTOS_COM_CADASTRO)
def test_cracha_e_carteira_com_cadastro_completo_sao_aceitos(client, identificador: str) -> None:
    gestor_user, solicitante, tipo = _preparar_solicitacao(identificador, 'GP4')

    client.force_login(gestor_user)
    _solicitar(client, solicitante, tipo)

    assert DocumentoControle.objects.filter(documento_tipo=tipo, solicitante_vinculo=solicitante.get_vinculo()).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_outro_tipo_de_documento_nao_exige_foto_nem_tipo_sanguineo(client) -> None:
    """A exigência é do crachá e da carteira funcional, que imprimem esses dados; outro documento não a herda."""
    gestor_user, solicitante, tipo = _preparar_solicitacao(None, 'GP5')
    _sem_foto(solicitante)
    _sem_grupo_sanguineo(solicitante)
    _sem_fator_rh(solicitante)

    client.force_login(gestor_user)
    _solicitar(client, solicitante, tipo)

    assert DocumentoControle.objects.filter(documento_tipo=tipo, solicitante_vinculo=solicitante.get_vinculo()).exists()
