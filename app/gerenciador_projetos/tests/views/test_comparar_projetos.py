"""Comparação de projetos: seleção pela listagem, visibilidade e as visões."""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from comum.models import User
from gerenciador_projetos.models import Projeto
from gerenciador_projetos.enums import VisibilidadeProjeto
from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory
from rh.tests.factories import ServidorFactory

# O Monitor de Projetos só enxerga projetos públicos fora da própria equipe.
PUBLICO = VisibilidadeProjeto.PUBLICO


def _usuario(*grupos: str) -> User:
    usuario = ServidorFactory().get_user()
    for nome in grupos:
        usuario.groups.add(Group.objects.get(name=nome))
    return usuario


def _url(nome: str, *projetos: Projeto, extra: str = '') -> str:
    return reverse(nome) + '?' + '&'.join(f'projeto={p.pk}' for p in projetos) + extra


class TestCompararProjetos:
    def test_monitor_compara_projetos_alheios(self, client):
        a, b = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO), ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO)
        client.force_login(_usuario('Monitor de Projetos'))

        resposta = client.get(_url('comparar_projetos', a, b))

        assert [i.projeto for i in resposta.context['indicadores']] == sorted([a, b], key=lambda p: p.titulo)

    def test_descarta_projeto_privado_alheio_e_id_invalido(self, client):
        meu = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO)
        alheio = ProjetoFactory(criado_por=self.user_admin)
        client.force_login(_usuario('Monitor de Projetos'))

        resposta = client.get(_url('comparar_projetos', meu, alheio, extra='&projeto=abc&projeto=999999&projeto=²'))

        assert [i.projeto for i in resposta.context['indicadores']] == [meu]

    def test_sem_projeto_visivel_mostra_aviso(self, client):
        alheio = ProjetoFactory(criado_por=self.user_admin)
        client.force_login(_usuario('Monitor de Projetos'))

        resposta = client.get(_url('comparar_projetos', alheio))

        assert resposta.status_code == 200
        assert resposta.context['indicadores'] == []

    def test_painel_nao_faz_query_por_projeto(self, client, django_assert_max_num_queries):
        client.force_login(_usuario('Monitor de Projetos'))

        def com_gerente() -> Projeto:
            projeto = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO)
            projeto.gerentes.add(ServidorFactory().get_user())
            return projeto

        um = [com_gerente()]
        # Cache de processo do User: a factory já o aquece, o que esconderia uma query por gerente.
        User.VINCULOS.clear()
        User.PESSOAS_FISICAS.clear()
        with CaptureQueriesContext(connection) as base:
            client.get(_url('comparar_projetos', *um))
        varios = um + [com_gerente() for _ in range(3)]
        User.VINCULOS.clear()
        User.PESSOAS_FISICAS.clear()

        with django_assert_max_num_queries(len(base)):
            client.get(_url('comparar_projetos', *varios))

    def test_comparacao_e_so_do_monitor(self, client):
        projeto = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO)
        gerente = _usuario('Gerente de Projeto')
        projeto.gerentes.add(gerente)
        client.force_login(gerente)

        listagem = client.get('/admin/gerenciador_projetos/projeto/?tab=tab_any_data')
        acao = client.post('/admin/gerenciador_projetos/projeto/?tab=tab_any_data', {'action': 'comparar_projetos', '_selected_action': [projeto.pk]})

        assert 'comparar_projetos' not in listagem.content.decode()
        assert not (acao.status_code == 302 and acao.url.startswith(reverse('comparar_projetos')))
        for nome in ('comparar_projetos', 'comparar_projetos_graficos', 'comparar_projetos_gantt', 'comparar_projetos_calendario'):
            assert client.get(_url(nome, projeto)).status_code == 403, nome

    def test_acao_do_admin_leva_a_comparacao(self, client):
        a, b = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO), ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO)
        client.force_login(_usuario('Monitor de Projetos'))

        resposta = client.post(
            '/admin/gerenciador_projetos/projeto/?tab=tab_any_data', {'action': 'comparar_projetos', '_selected_action': [a.pk, b.pk]}
        )

        assert resposta.status_code == 302
        assert resposta.url.startswith(reverse('comparar_projetos'))
        assert {f'projeto={a.pk}', f'projeto={b.pk}'} <= set(resposta.url.split('?')[1].split('&'))

    def test_as_quatro_visoes_abrem(self, client):
        projeto = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO, data_conclusao_estimada=date(2026, 12, 1))
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, data_inicio=date(2026, 10, 1), data_conclusao_estimada=date.today())
        client.force_login(_usuario('Monitor de Projetos'))

        for nome in ('comparar_projetos', 'comparar_projetos_graficos', 'comparar_projetos_gantt', 'comparar_projetos_calendario'):
            resposta = client.get(_url(nome, projeto))
            assert resposta.status_code == 200, nome
            assert projeto.titulo in resposta.content.decode(), nome

    def test_titulo_com_script_nao_fecha_a_tag_nos_graficos(self, client):
        projeto = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO, titulo='</script><img src=x onerror=alert(1)>')
        client.force_login(_usuario('Monitor de Projetos'))

        resposta = client.get(_url('comparar_projetos_graficos', projeto))

        assert '</script><img' not in resposta.content.decode()

    def test_filtro_do_calendario_ignora_projeto_invalido_na_url(self, client):
        projeto = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO)
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, titulo='Entrega X', data_conclusao_estimada=date(2026, 11, 10))
        client.force_login(_usuario('Monitor de Projetos'))

        resposta = client.get(_url('comparar_projetos_calendario', projeto, extra='&projeto=999999&data_inicio=01/11/2026&data_fim=30/11/2026'))

        assert 'Entrega X' in resposta.content.decode()

    def test_selecao_mostra_so_os_projetos_escolhidos(self, client):
        escolhido, outro = (
            ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO),
            ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO),
        )
        client.force_login(_usuario('Monitor de Projetos'))

        html = client.get(_url('comparar_projetos', escolhido)).content.decode()

        assert outro.titulo not in html

    def test_pagina_de_graficos_carrega_o_highcharts(self, client):
        projeto = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO)
        client.force_login(_usuario('Monitor de Projetos'))

        html = client.get(_url('comparar_projetos_graficos', projeto)).content.decode()

        assert 'graficos/highcharts.js' in html
