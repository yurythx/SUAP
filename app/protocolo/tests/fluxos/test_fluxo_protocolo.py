"""Testes de fluxo do Protocolo.

Cobrem a tramitação de um processo (encaminhar, receber, gerar capa), as regras
de quem pode editá-lo e o cálculo de atraso — sempre a partir do estado mínimo
montado pelas fixtures (`conftest.py`), que constroem só o que cada teste usa.
"""

from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import Group

from protocolo.models import Configuracao, Processo, Tramite
from protocolo.tests.conftest import SENHA, _servidor_logavel
from rh.tests.factories import ServidorFactory


@pytest.mark.django_db(databases='__all__')
class TestFluxoProtocolo:
    # --- Tramitação --------------------------------------------------------

    def test_encaminhar_primeiro_tramite(self, cadastrador, processo, setor_c):
        """O cadastrador encaminha o processo pela primeira vez, criando o trâmite."""
        # o form recusa setor sem ninguém lotado (`Setor.get_setores_vazios()`).
        ServidorFactory(setor=setor_c)
        url = f'/protocolo/processo_encaminhar_primeiro_tramite/{processo.pk}/interno/'
        dados = {'processo': processo.pk, 'observacao_encaminhamento': '', 'orgao_interno_recebimento': setor_c.pk}

        cadastrador.post(url, dados)

        assert Tramite.objects.filter(processo=processo).count() == 1
        tramite = processo.get_ultimo_tramite()
        assert tramite.orgao_interno_encaminhamento == tramite.vinculo_encaminhamento.setor

    def test_receber_processo(self, suap_client, servidor_cadastrador, processo, criar_tramite):
        """O servidor do setor de destino recebe o trâmite que lhe foi encaminhado."""
        destinatario = _servidor_logavel()
        criar_tramite(processo, encaminha_de=servidor_cadastrador.setor, recebe_em=destinatario.setor)

        destinatario.get_user().groups.add(Group.objects.get(name='Cadastrador de processos'))
        suap_client.login(username=destinatario.get_user().username, password=SENHA)
        tramite = processo.get_ultimo_tramite()

        suap_client.post(f'/protocolo/processo_receber/{tramite.pk}/')

        tramite = processo.get_ultimo_tramite()
        assert tramite.vinculo_recebimento.setor == tramite.orgao_interno_recebimento

    def test_gerar_capa(self, cadastrador, processo, criar_tramite, setor_a, setor_c):
        """A capa de um processo já tramitado é renderizada com sucesso."""
        criar_tramite(processo, encaminha_de=setor_a, recebe_em=setor_c)

        resposta = cadastrador.get(f'/protocolo/capa_processo/{processo.pk}/')

        assert resposta.status_code == 200

    # --- Regras de edição --------------------------------------------------

    def test_edita_processo_sem_tramite_completo_com_qualquer_permissao(self, processo, editor_em_tramite, editor_sem_tramite_completo):
        """Processo sem trâmite completo pode ser editado por ambas as permissões."""
        assert processo.pode_editar_processo(editor_em_tramite)
        assert processo.pode_editar_processo(editor_sem_tramite_completo)

    def test_processo_com_tramite_completo_so_edita_com_permissao_em_tramite(
        self, processo, criar_tramite, setor_b, setor_c, editor_em_tramite, editor_sem_tramite_completo
    ):
        criar_tramite(
            processo,
            encaminha_de=setor_c,
            recebe_em=setor_b,
            data_recebimento=datetime.today(),
        )

        assert processo.pode_editar_processo(editor_em_tramite)
        assert not processo.pode_editar_processo(editor_sem_tramite_completo)

    def test_processo_finalizado_nao_pode_ser_editado(self, processo, editor_em_tramite, editor_sem_tramite_completo):
        processo.status = Processo.STATUS_FINALIZADO
        processo.save()

        assert not processo.pode_editar_processo(editor_em_tramite)
        assert not processo.pode_editar_processo(editor_sem_tramite_completo)

    # --- Numeração ---------------------------------------------------------

    def test_numero_processo_tem_digito_verificador_valido(self, processo):
        numero = processo.numero_processo[:-3].replace('.', '')
        dv = processo.numero_processo[-2:]

        assert dv == _calcula_digito_verificador(numero)

    # --- Atraso ------------------------------------------------------------

    def test_processo_sem_tramite_nao_esta_atrasado(self, processo):
        assert not processo.is_atrasado()

    def test_tramite_recente_nao_esta_atrasado(self, processo, criar_tramite, setor_a, setor_b):
        """Encaminhado agora, dentro do limite configurado, não conta como atraso."""
        Configuracao.objects.create(app='protocolo', chave='tempo_tramite_mesmo_campus', valor=12)
        criar_tramite(processo, encaminha_de=setor_a, recebe_em=setor_b)

        assert not processo.is_atrasado()

    def test_tramite_antigo_esta_atrasado(self, processo, criar_tramite, setor_a, setor_b):
        """Encaminhado ontem, acima do limite de 12h, conta como atraso."""
        Configuracao.objects.create(app='protocolo', chave='tempo_tramite_mesmo_campus', valor=12)
        criar_tramite(
            processo,
            encaminha_de=setor_a,
            recebe_em=setor_b,
            data_encaminhamento=datetime.now() - timedelta(days=1),
        )

        assert processo.is_atrasado()


def _calcula_digito_verificador(numero):
    soma_1 = sum(int(numero[::-1][x - 2]) * x for x in range(16, 1, -1))
    dv1 = (11 - (soma_1 % 11)) % 10
    numero2 = numero + str(dv1)
    soma_2 = sum(int(numero2[::-1][x - 2]) * x for x in range(17, 1, -1))
    dv2 = (11 - (soma_2 % 11)) % 10
    return f'{dv1}{dv2}'
