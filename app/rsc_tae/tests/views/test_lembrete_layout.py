"""Testes do lembrete "Fique atento!" do RSC-TAE na tela inicial (``views/layout.py``).

O aviso tem três portas: data limite cadastrada, data ainda não vencida, e servidor sem processo
finalizado. Basta uma fechada para ele não aparecer.

A configuração não tem migração: a linha em ``comum.Configuracao`` nasce quando alguém salva o
formulário de Configurações do módulo (``rsc_tae.forms.ConfiguracaoForm``), cujo NOME de campo vira
a chave. Os testes gravam a linha direto, o que deixa o valor visível em cada caso.
"""

import datetime
from types import SimpleNamespace

import pytest

from comum.models import Configuracao
from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import Nivel, ProcessoRSCTae
from rsc_tae.views.layout import (
    _FORMATOS_DATA,
    CHAVE_DATA_LIMITE_LEMBRETE,
    avisos_do_servidor,
    data_limite_lembrete,
    index_servidor,
)


def _configurar(valor):
    """Grava o valor da configuração e limpa o cache de Configuracao (TTL de 10s por processo)."""
    Configuracao.objects.update_or_create(
        app='rsc_tae',
        chave=CHAVE_DATA_LIMITE_LEMBRETE,
        defaults={'valor': valor, 'descricao': 'Data limite do lembrete (teste)'},
    )
    Configuracao.clear_cache()


@pytest.mark.django_db(databases='__all__')
class TestDataLimiteLembrete:
    """Leitura e conversão do valor cadastrado."""

    ATORES = ('servidor_a', 'servidor_b')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _limpar(self):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_DATA_LIMITE_LEMBRETE).delete()
        Configuracao.clear_cache()

    def test_sem_configuracao_cadastrada_nao_ha_data(self):
        assert data_limite_lembrete() is None

    def test_configuracao_em_branco_nao_ha_data(self):
        _configurar('')

        assert data_limite_lembrete() is None

    def test_le_data_no_formato_iso(self):
        """ISO é o formato que ConfiguracaoFormBase.save() grava."""
        _configurar('2026-12-31')

        assert data_limite_lembrete() == datetime.date(2026, 12, 31)

    def test_nao_aceita_o_formato_brasileiro(self):
        """ISO é o ÚNICO formato suportado, e não por preciosismo.

        ``ConfiguracaoFormBase.__init__`` percorre todas as ``Configuracao`` e faz
        ``strptime(valor, '%Y-%m-%d')`` sem try/except em qualquer chave que seja ``DateField``.
        Um valor dd/mm/aaaa gravado aqui derrubaria a tela de Configurações inteira, de todos os
        apps. Aceitar o formato na leitura seria um convite a gravá-lo.
        """
        _configurar('31/12/2026')

        assert data_limite_lembrete() is None

    def test_ignora_espacos_em_volta(self):
        _configurar('  2026-12-31  ')

        assert data_limite_lembrete() == datetime.date(2026, 12, 31)

    @pytest.mark.parametrize('valor', ['em breve', '2026-02-31', '2026', '2026-12', 'aaaa-mm-dd'])
    def test_valor_invalido_equivale_a_sem_data(self, valor):
        """Exibir para sempre esconderia o erro de digitação; some, e o log denuncia."""
        _configurar(valor)

        assert data_limite_lembrete() is None

    def test_valor_invalido_gera_aviso_no_log(self, caplog):
        _configurar('em breve')

        with caplog.at_level('WARNING'):
            data_limite_lembrete()

        assert CHAVE_DATA_LIMITE_LEMBRETE in caplog.text


class TestConfiguracaoForm:
    """Liga a chave lida pelo layout ao campo do formulário de Configurações. Sem banco."""

    ATORES = ('servidor_a', 'servidor_b')

    def test_formulario_expoe_o_campo_com_o_nome_da_chave(self):
        """``ConfiguracaoFormBase.save()`` deriva a chave do NOME do campo: renomear troca a chave."""
        from rsc_tae.forms import ConfiguracaoForm

        assert CHAVE_DATA_LIMITE_LEMBRETE in ConfiguracaoForm.base_fields

    def test_campo_e_opcional(self):
        """Obrigatório impediria salvar as demais configurações do módulo sem definir a janela."""
        from rsc_tae.forms import ConfiguracaoForm

        assert ConfiguracaoForm.base_fields[CHAVE_DATA_LIMITE_LEMBRETE].required is False

    def test_campo_e_de_data(self):
        """O tipo importa: ConfiguracaoFormBase lê e grava DateField em ISO."""
        from django.forms import DateField

        from rsc_tae.forms import ConfiguracaoForm

        assert isinstance(ConfiguracaoForm.base_fields[CHAVE_DATA_LIMITE_LEMBRETE], DateField)

    def test_label_serve_como_descricao_da_configuracao(self):
        """O label é gravado como descrição da Configuracao, então precisa se explicar sozinho."""
        from rsc_tae.forms import ConfiguracaoForm

        assert 'Fique atento' in ConfiguracaoForm.base_fields[CHAVE_DATA_LIMITE_LEMBRETE].label

    def test_formato_gravado_pelo_formulario_e_lido_de_volta(self):
        """Fecha o ciclo: o que o save() grava (str(date), ISO) é o que data_limite_lembrete() aceita."""
        import datetime as dt

        assert dt.datetime.strptime(str(dt.date(2026, 12, 31)), _FORMATOS_DATA[0]).date() == dt.date(2026, 12, 31)


class BaseLembrete:
    """Cenário comum: TAE sem processo e uma data limite 30 dias à frente."""

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        _configurar((datetime.date.today() + datetime.timedelta(days=30)).strftime('%Y-%m-%d'))

    def _request(self, servidor=None, eh_tae=True):
        """Duplo do request: ``index_servidor`` só usa ``user.eh_tecnico_administrativo`` e ``get_vinculo``."""
        servidor = servidor or self.servidor_a
        vinculo = servidor.get_vinculo()
        user = SimpleNamespace(
            is_authenticated=True,
            eh_tecnico_administrativo=eh_tae,
            get_vinculo=lambda: vinculo,
        )
        return SimpleNamespace(user=user)

    def _processo(self, situacao):
        return ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=situacao,
        )


@pytest.mark.django_db(databases='__all__')
class TestLembreteDoServidor(BaseLembrete):
    """As três portas do aviso, pelo caminho real de ``avisos_do_servidor``."""

    ATORES = ('servidor_a', 'servidor_b')

    # ------------------------------------------------------------ aparece

    def test_aparece_dentro_do_prazo_para_tae_sem_processo(self):
        avisos = avisos_do_servidor(self._request())

        assert len(avisos) == 1
        assert 'Inicie seu processo' in avisos[0]['titulo']

    def test_aparece_no_ultimo_dia_do_prazo(self):
        """A data cadastrada é o último dia de exibição, não o primeiro dia de ausência."""
        _configurar(datetime.date.today().strftime('%Y-%m-%d'))

        assert len(avisos_do_servidor(self._request())) == 1

    def test_informa_ate_quando_o_lembrete_sera_exibido(self):
        limite = datetime.date.today() + datetime.timedelta(days=30)
        _configurar(limite.strftime('%Y-%m-%d'))

        aviso = avisos_do_servidor(self._request())[0]

        assert aviso['extra'] == f'Este lembrete deixará de ser exibido após o dia {limite.strftime("%d/%m/%Y")}.'

    def test_nao_usa_o_slot_prazo_do_componente(self):
        """O slot renderiza "Até <data>", que sozinho seria lido como prazo para requerer o RSC."""
        aviso = avisos_do_servidor(self._request())[0]

        assert 'prazo' not in aviso

    def test_muda_o_texto_para_quem_ja_tem_processo_em_andamento(self):
        self._processo(SituacaoProcesso.AGUARDANDO_CRSC)

        avisos = avisos_do_servidor(self._request())

        assert 'Acompanhe seu processo' in avisos[0]['titulo']

    # ------------------------------------------------------------ não aparece

    def test_nao_aparece_sem_data_cadastrada(self):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_DATA_LIMITE_LEMBRETE).delete()
        Configuracao.clear_cache()

        assert avisos_do_servidor(self._request()) == []

    def test_nao_aparece_depois_do_prazo(self):
        _configurar((datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y-%m-%d'))

        assert avisos_do_servidor(self._request()) == []

    @pytest.mark.parametrize('situacao', [SituacaoProcesso.DEFERIDO, SituacaoProcesso.INDEFERIDO])
    def test_nao_aparece_para_quem_tem_processo_finalizado(self, situacao):
        self._processo(situacao)

        assert avisos_do_servidor(self._request()) == []

    def test_processo_finalizado_esconde_mesmo_com_outro_em_andamento(self):
        """Regra literal pedida: qualquer finalizado no histórico encerra o lembrete."""
        self._processo(SituacaoProcesso.DEFERIDO)
        self._processo(SituacaoProcesso.AGUARDANDO_CRSC)

        assert avisos_do_servidor(self._request()) == []

    def test_processo_finalizado_de_outro_servidor_nao_interfere(self):
        ProcessoRSCTae.objects.create(
            vinculo=self.servidor_b.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=SituacaoProcesso.DEFERIDO,
        )

        assert len(avisos_do_servidor(self._request())) == 1

    def test_nao_aparece_para_quem_nao_e_tecnico_administrativo(self):
        assert avisos_do_servidor(self._request(eh_tae=False)) == []

    def test_a_view_registrada_no_sinal_devolve_o_mesmo_aviso(self):
        """Liga o wrapper do sinal à lógica: o decorador recebe (sender, request)."""
        avisos = index_servidor(None, self._request())

        assert 'Inicie seu processo' in avisos[0]['titulo']


@pytest.mark.django_db(databases='__all__')
class TestCicloCompletoDaConfiguracao:
    """Ponta a ponta: salvar pela tela de Configurações precisa alimentar o lembrete.

    É o teste que prova a integração inteira — descoberta pela factory, chave derivada do nome do
    campo, formato gravado e leitura de volta. Os demais testam as peças isoladas.
    """

    ATORES = ('servidor_a', 'servidor_b')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _limpar(self):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_DATA_LIMITE_LEMBRETE).delete()
        Configuracao.clear_cache()

    def _salvar(self, valor):
        from comum.forms import ConfiguracaoFormFactory

        form = ConfiguracaoFormFactory('rsc_tae')(data={CHAVE_DATA_LIMITE_LEMBRETE: valor})
        assert form.is_valid(), form.errors
        form.save()
        return form

    def test_salvar_na_tela_de_configuracoes_alimenta_o_lembrete(self):
        self._salvar('31/12/2026')

        assert data_limite_lembrete() == datetime.date(2026, 12, 31)

    def test_configuracao_nasce_ao_salvar_sem_precisar_de_migracao(self):
        assert not Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_DATA_LIMITE_LEMBRETE).exists()

        self._salvar('31/12/2026')

        config = Configuracao.objects.get(app='rsc_tae', chave=CHAVE_DATA_LIMITE_LEMBRETE)
        assert config.descricao == 'Data limite do lembrete "Fique atento!"'

    def test_limpar_o_campo_desliga_o_lembrete(self):
        self._salvar('31/12/2026')

        self._salvar('')

        assert data_limite_lembrete() is None


@pytest.mark.django_db(databases='__all__')
class TestRenderizacaoDoAviso(BaseLembrete):
    """O componente do Design System é quem transforma o dict em tela — e ele tem slots próprios.

    Sem este teste, trocar 'prazo' por qualquer outra chave passaria: o dict continuaria correto e
    a data simplesmente não apareceria para ninguém.
    """

    ATORES = ('servidor_a', 'servidor_b')

    def _renderizar(self):
        from django.template.loader import render_to_string

        return render_to_string(
            'djtools/templates/components/alertas.html',
            {
                'titulo': 'Fique atento!',
                'icone': 'exclamation-circle',
                'classe': 'caution',
                'objetos': avisos_do_servidor(self._request()),
            },
        )

    def test_a_frase_com_a_data_aparece_na_tela(self):
        limite = datetime.date.today() + datetime.timedelta(days=30)
        _configurar(limite.strftime('%Y-%m-%d'))

        html = self._renderizar()

        assert f'Este lembrete deixará de ser exibido após o dia {limite.strftime("%d/%m/%Y")}.' in html

    def test_sem_aviso_nao_renderiza_a_frase(self):
        Configuracao.objects.filter(app='rsc_tae', chave=CHAVE_DATA_LIMITE_LEMBRETE).delete()
        Configuracao.clear_cache()

        html = self._renderizar()

        assert 'deixará de ser exibido' not in html
