"""Exportação de projetos para planilha: respeita quem vê o quê e traz os indicadores do painel."""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import Group
from django.http import HttpResponse
from openpyxl import load_workbook

from comum.models import User
from djtools.models import Task
from gerenciador_projetos.enums import SituacaoTarefa, VisibilidadeProjeto
from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory
from rh.tests.factories import ServidorFactory

LISTAGEM = '/admin/gerenciador_projetos/projeto/?tab=tab_any_data'

# O Monitor de Projetos só enxerga projetos públicos fora da própria equipe.
PUBLICO = VisibilidadeProjeto.PUBLICO


def _usuario(*grupos: str) -> User:
    usuario = ServidorFactory().get_user()
    for nome in grupos:
        usuario.groups.add(Group.objects.get(name=nome))
    return usuario


def _planilha(resposta: HttpResponse) -> dict[str, dict[str, object]]:
    """Linhas da planilha gerada pela tarefa, indexadas pelo título do projeto."""
    uuid = resposta['Location'].rstrip('/').rsplit('/', 1)[-1]
    linhas = list(load_workbook(Task.objects.get(uuid=uuid).file).active.iter_rows(values_only=True))
    cabecalho = linhas[0]
    return {linha[0]: dict(zip(cabecalho, linha, strict=True)) for linha in linhas[1:]}


class TestExportarProjetos:
    def test_equipe_exporta_so_os_proprios_projetos(self, client):
        meu, alheio = (
            ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO),
            ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO),
        )
        usuario = _usuario('Interessado do Projeto')
        meu.interessados.add(usuario)
        client.force_login(usuario)

        planilha = _planilha(client.get(f'{LISTAGEM}&export_to_xls=1'))

        assert set(planilha) == {meu.titulo}
        assert alheio.titulo not in planilha

    def test_monitor_exporta_os_publicos_com_indicadores(self, client):
        projeto = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO, data_conclusao_estimada=date(2020, 1, 1))
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, data_conclusao_estimada=date(2020, 1, 1))
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, situacao=SituacaoTarefa.CONCLUIDA)
        outro = ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO)
        privado = ProjetoFactory(criado_por=self.user_admin)
        client.force_login(_usuario('Monitor de Projetos'))

        planilha = _planilha(client.get(f'{LISTAGEM}&export_to_xls=1'))

        assert {projeto.titulo, outro.titulo} <= set(planilha)
        assert privado.titulo not in planilha
        linha = planilha[projeto.titulo]
        # O XlsResponse do djtools grava toda célula como texto (human_str), como nas demais exportações.
        assert (linha['Evolução (%)'], linha['Abertas'], linha['Concluídas'], linha['Atrasadas']) == ('50', '1', '1', '1')
        assert linha['Prazo'] == 'Atrasado'

    def test_acao_exporta_so_os_selecionados(self, client):
        escolhido, outro = (
            ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO),
            ProjetoFactory(criado_por=self.user_admin, visibilidade=PUBLICO),
        )
        client.force_login(_usuario('Monitor de Projetos'))

        resposta = client.post(LISTAGEM, {'action': 'exportar_projetos', '_selected_action': [escolhido.pk]})

        assert set(_planilha(resposta)) == {escolhido.titulo}
        assert outro.titulo not in _planilha(resposta)
