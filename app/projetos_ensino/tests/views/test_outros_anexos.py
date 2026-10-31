"""Caixa "Outros Anexos" da aba Anexos de `projeto.html`."""

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from projetos_ensino.models import ProjetoAnexo
from projetos_ensino.tests.conftest import _login, set_periodo_execucao


@pytest.mark.django_db(databases='__all__')
def test_gerente_so_ve_excluir_e_atualizar_anexo_quando_a_view_aceita(client, usuarios, projeto_aprovado):
    """Em projeto somente leitura as views recusam o anexo; a tela não oferece excluir nem "Atualizar Anexo" ao gerente (#17575).

    O projeto em execução é o controle positivo: prova que o cenário renderiza os links.
    """
    projeto = projeto_aprovado
    set_periodo_execucao(projeto.edital)
    anexo = ProjetoAnexo.objects.create(projeto=projeto, descricao='Anexo diverso', arquivo=SimpleUploadedFile('anexo.pdf', b'%PDF-1.4'))
    recusadas = [f'/projetos_ensino/excluir_outro_anexo/{anexo.pk}/', f'/projetos_ensino/upload_outro_anexo/{anexo.pk}/']
    adicionar = f'/projetos_ensino/adicionar_anexo_diverso_projeto/{projeto.pk}/'  # a view aceita o gerente: segue oferecido
    rotas = [*recusadas, adicionar]
    _login(client, usuarios.gerente)

    tela = client.get(f'/projetos_ensino/projeto/{projeto.pk}/?tab=anexos').content.decode()
    assert [rota for rota in rotas if f'href="{rota}"' in tela] == rotas

    projeto.data_finalizacao_conclusao = datetime.date.today()
    projeto.save()
    assert projeto.eh_somente_leitura()

    tela = client.get(f'/projetos_ensino/projeto/{projeto.pk}/?tab=anexos').content.decode()
    assert [rota for rota in rotas if f'href="{rota}"' in tela] == [adicionar]
    for rota in recusadas:
        resposta = client.get(rota, follow=True)
        assert ProjetoAnexo.objects.filter(pk=anexo.pk).exists()
        assert 'não pode ser' in resposta.content.decode(), rota
