import pytest
from django.apps.registry import apps

Empenho = apps.get_model('almoxarifado', 'empenho')
EmpenhoConsumo = apps.get_model('almoxarifado', 'empenhoconsumo')


pytestmark = pytest.mark.django_db


def test_cadastra_empenho_pessoa_juridica_com_itens_pendentes(almox_context):
    quantidade_antes = Empenho.objects.count()

    empenho, item1, item2 = almox_context.criar_empenho_consumo_com_dois_itens(tipo_pessoa='juridica', usuario=almox_context.servidor_a)

    assert Empenho.objects.count() == quantidade_antes + 1
    assert empenho.get_itens().count() == 2
    assert len(EmpenhoConsumo.get_pendentes(empenho)) == 2
    assert item1.qtd_adquirida == 0
    assert item2.qtd_adquirida == 0


def test_cadastra_empenho_pessoa_fisica_com_itens_pendentes(almox_context):
    quantidade_antes = Empenho.objects.count()

    empenho, item1, item2 = almox_context.criar_empenho_consumo_com_dois_itens(tipo_pessoa='fisica', usuario=almox_context.servidor_a)

    assert Empenho.objects.count() == quantidade_antes + 1
    assert empenho.get_itens().count() == 2
    assert len(EmpenhoConsumo.get_pendentes(empenho)) == 2
    assert item1.qtd_adquirida == 0
    assert item2.qtd_adquirida == 0


def test_remocao_de_empenho_com_itens_movimentados_exibe_mensagem_em_vez_de_erro(almox_context):
    empenho, item1, _ = almox_context.criar_empenho_consumo_com_dois_itens(usuario=almox_context.servidor_a)
    EmpenhoConsumo.objects.filter(pk=item1.pk).update(qtd_adquirida=1)

    response = almox_context.client.post(f'/admin/almoxarifado/empenho/{empenho.pk}/delete/', {'senha': '123', 'post': 'yes'}, follow=True)

    assert response.redirect_chain[0] == (empenho.get_absolute_url(), 302)
    assert 'Impossível remover o empenho: os itens sofreram movimentações.' in response.content.decode()
    assert Empenho.objects.filter(pk=empenho.pk).exists()


def test_remocao_de_empenho_sem_movimentacao_pelo_coordenador(almox_context):
    empenho = almox_context.criar_empenho(usuario=almox_context.servidor_a)

    response = almox_context.client.post(f'/admin/almoxarifado/empenho/{empenho.pk}/delete/', {'senha': '123', 'post': 'yes'})

    assert response.status_code == 302
    assert response['Location'] == '/almoxarifado/empenhos/'
    assert not Empenho.objects.filter(pk=empenho.pk).exists()
