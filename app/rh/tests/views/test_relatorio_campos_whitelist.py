import re

import pytest
from django.test import Client

import rh.tasks
from djtools.choices import filtrar_campos_validos
from djtools.utils import getattr_coalesce
from rh.models import Servidor
from rh.tests.factories import ServidorFactory


class TestFiltrarCamposValidos:
    """`?campos=` chega cru na querystring e é resolvido por getattr encadeado, com
    auto-chamada quando o resultado é callable. Sem whitelist, `?campos=delete` fazia a
    view executar `servidor.delete()` para cada linha do relatório."""

    @pytest.mark.parametrize('malicioso', ['delete', 'save', 'pessoa_fisica.delete', 'vinculos.all', '__class__'])
    def test_descarta_atributo_fora_da_whitelist(self, malicioso):
        assert filtrar_campos_validos([malicioso]) == []

    def test_preserva_a_ordem_escolhida(self):
        assert filtrar_campos_validos(['situacao', 'delete', 'raca']) == ['situacao', 'raca']


@pytest.fixture
def servidor_alvo(db, sync_permissions):
    """Um servidor ativo com nome — é o que a view precisa achar para resolver campos."""
    return ServidorFactory()


class TestContratoCheckboxQuerystring:
    """O filtro só é correto se aceitar tudo que a própria tela de busca oferece.

    Conferir contra a lista `campos` seria tautológico — é dela que `CAMPOS_VALIDOS` deriva.
    A checagem que vale é contra os `value=` realmente renderizados nos checkboxes.
    """

    def test_todo_checkbox_renderizado_sobrevive_ao_filtro(self, admin_user):
        client = Client()
        client.force_login(admin_user)
        html = client.get('/rh/servidor/buscar/').content.decode('utf-8')

        renderizados = re.findall(r'<input type="checkbox" name="campos" value="([^"]+)"', html)
        assert len(renderizados) > 50, f'a tela de busca renderizou só {len(renderizados)} checkboxes'
        assert filtrar_campos_validos(renderizados) == renderizados


@pytest.mark.usefixtures('servidor_alvo')
class TestTelaRelatorioNaoResolveCampoArbitrario:
    """Prova de ponta a ponta, pela view real, de que o campo malicioso nunca chega ao getattr."""

    def _servidor_alvo(self):
        return Servidor.objects.filter(ativo=True, pessoa_fisica__nome__isnull=False).exclude(pessoa_fisica__nome='').first()

    def test_campo_malicioso_nao_e_resolvido_mas_o_legitimo_e(self, admin_user, monkeypatch):
        servidor = self._servidor_alvo()
        assert servidor is not None, 'é preciso ao menos 1 servidor ativo com nome'

        resolvidos = []

        def espiao(obj, attribute, default=None):
            resolvidos.append(attribute)
            return getattr_coalesce(obj, attribute, default)

        monkeypatch.setattr(rh.tasks, 'getattr_coalesce', espiao)

        total_antes = Servidor.objects.count()
        client = Client()
        client.force_login(admin_user)
        # `nome` é o que liga o flag `filtrado`; sem ele a view aborta antes do relatório.
        client.get('/rh/servidor/buscar/', {'nome': servidor.pessoa_fisica.nome.split()[0], 'campos': ['situacao', 'delete']})

        # Controle positivo: sem isto o teste passaria mesmo que a requisição nunca
        # chegasse ao laço que resolve os campos.
        assert 'situacao' in resolvidos, 'a requisição não chegou à resolução de campos do relatório'
        assert 'delete' not in resolvidos
        assert Servidor.objects.count() == total_antes
