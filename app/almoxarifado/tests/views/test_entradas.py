from decimal import Decimal

import pytest
from django.apps.registry import apps

from djtools.templatetags.filters import format_money_almox

Empenho = apps.get_model('almoxarifado', 'empenho')
Entrada = apps.get_model('almoxarifado', 'entrada')


pytestmark = pytest.mark.django_db


def assert_movimento_zero(movimento):
    assert list(movimento.values()) == [0, 0]


def test_registra_entradas_de_compra_em_campi_distintos(almox_context):
    empenho, item1, item2 = almox_context.criar_empenho_consumo_com_dois_itens(tipo_pessoa='juridica', usuario=almox_context.servidor_a)
    assert almox_context.mat1.codigo == str(almox_context.mat1.id).zfill(6)
    assert almox_context.mat2.codigo == str(almox_context.mat2.id).zfill(6)

    almox_context.login(almox_context.servidor_a)
    pagina_entrada = almox_context.client.get('/almoxarifado/entrada_compra/')
    assert pagina_entrada.status_code == 200
    assert 'Efetuar Entrada de Compra' in pagina_entrada.content.decode()

    almox_context.registrar_entrada_compra(empenho, [item1, item2], [5, 10], numero_nota='001', usuario=almox_context.servidor_a)

    assert empenho.get_entradas().count() == 1
    itens_ordenados = empenho.empenhoconsumo_set.order_by('id')
    assert itens_ordenados[0].qtd_adquirida == 5
    assert itens_ordenados[1].qtd_adquirida == 10

    assert almox_context.mat1.get_estoque_atual() == 5
    entrada_mat1_campus_a = almox_context.mat1.entrada(uo_id=almox_context.campus_a_suap.pk)
    assert [entrada_mat1_campus_a['qtd'], entrada_mat1_campus_a['valor']] == [5, 5 * item1.valor]
    assert_movimento_zero(almox_context.mat1.entrada_transferencia(uo_id=almox_context.campus_a_suap.pk))
    assert_movimento_zero(almox_context.mat1.saida(uo_id=almox_context.campus_a_suap.pk))

    assert almox_context.mat2.get_estoque_atual() == 10
    entrada_mat2_campus_a = almox_context.mat2.entrada(uo_id=almox_context.campus_a_suap.pk)
    assert [entrada_mat2_campus_a['qtd'], entrada_mat2_campus_a['valor']] == [10, 10 * item2.valor]
    assert_movimento_zero(almox_context.mat2.entrada_transferencia(uo_id=almox_context.campus_a_suap.pk))
    assert_movimento_zero(almox_context.mat2.saida(uo_id=almox_context.campus_a_suap.pk))

    almox_context.login(almox_context.servidor_b)
    pagina_entrada = almox_context.client.get('/almoxarifado/entrada_compra/')
    assert pagina_entrada.status_code == 200
    assert 'Efetuar Entrada de Compra' in pagina_entrada.content.decode()

    almox_context.registrar_entrada_compra(empenho, [item1], [5], numero_nota='002', usuario=almox_context.servidor_b)

    assert empenho.get_entradas().count() == 2
    itens_ordenados = empenho.empenhoconsumo_set.order_by('id')
    assert itens_ordenados[0].qtd_adquirida == 10
    assert itens_ordenados[1].qtd_adquirida == 10

    assert almox_context.mat1.get_estoque_atual(uo=almox_context.campus_b_suap) == 5
    entrada_mat1_campus_b = almox_context.mat1.entrada(uo_id=almox_context.campus_b_suap.pk)
    assert [entrada_mat1_campus_b['qtd'], entrada_mat1_campus_b['valor']] == [5, 5 * item1.valor]
    assert_movimento_zero(almox_context.mat1.entrada_transferencia(uo_id=almox_context.campus_b_suap.pk))
    assert_movimento_zero(almox_context.mat1.saida(uo_id=almox_context.campus_b_suap.pk))

    assert almox_context.mat2.get_estoque_atual(uo=almox_context.campus_b_suap) == 0
    assert_movimento_zero(almox_context.mat2.entrada(uo_id=almox_context.campus_b_suap.pk))
    assert_movimento_zero(almox_context.mat2.entrada_transferencia(uo_id=almox_context.campus_b_suap.pk))
    assert_movimento_zero(almox_context.mat2.saida(uo_id=almox_context.campus_b_suap.pk))


def test_remove_entrada_do_empenho(almox_context):
    empenho, _, _ = almox_context.preparar_cenario_estoque_em_dois_campi()
    quantidade_antes = empenho.get_entradas().count()
    entrada = empenho.get_entradas().order_by('-id').first()
    assert entrada is not None

    pagina_detalhe = almox_context.client.get(f'/almoxarifado/entrada/{entrada.id}/')
    assert pagina_detalhe.status_code == 200
    assert f'/almoxarifado/entrada/{entrada.id}/remover/' in pagina_detalhe.content.decode()

    almox_context.client.get(f'/almoxarifado/entrada/{entrada.id}/remover/')

    assert empenho.get_entradas().count() == quantidade_antes - 1


def test_remove_itens_de_empenho_sem_entrada_remove_empenho_ao_final(almox_context):
    empenho, _, _ = almox_context.criar_empenho_consumo_com_dois_itens(tipo_pessoa='juridica', usuario=almox_context.servidor_a)
    quantidade_empenhos_antes = Empenho.objects.count()
    quantidade_itens_antes = empenho.get_itens().count()

    pagina_empenho = almox_context.client.get(f'/almoxarifado/empenho/{empenho.id}/')
    primeiro_item = empenho.empenhoconsumo_set.order_by('id')[0]
    assert pagina_empenho.status_code == 200
    assert f'/almoxarifado/empenhoconsumo/{primeiro_item.id}/remover/' in pagina_empenho.content.decode()

    almox_context.client.get(f'/almoxarifado/empenhoconsumo/{primeiro_item.id}/remover/')
    assert empenho.get_itens().count() == quantidade_itens_antes - 1

    item_restante = empenho.empenhoconsumo_set.order_by('id')[0]
    almox_context.client.get(f'/almoxarifado/empenhoconsumo/{item_restante.id}/remover/')
    assert Empenho.objects.count() == quantidade_empenhos_antes - 1


def test_remove_so_item_sem_entrada_quando_outro_item_tem_entrada(almox_context):
    empenho, item1, item2 = almox_context.criar_empenho_consumo_com_dois_itens(tipo_pessoa='juridica', usuario=almox_context.servidor_a)
    quantidade_empenhos_antes = Empenho.objects.count()
    quantidade_itens_antes = empenho.get_itens().count()
    quantidade_entradas_antes = empenho.get_entradas().count()

    pagina_entrada = almox_context.client.get('/almoxarifado/entrada_compra/')
    assert pagina_entrada.status_code == 200
    assert 'Efetuar Entrada de Compra' in pagina_entrada.content.decode()

    almox_context.registrar_entrada_compra(empenho, [item1], [5], numero_nota='001', usuario=almox_context.servidor_a)
    assert empenho.get_entradas().count() == quantidade_entradas_antes + 1

    pagina_empenho = almox_context.client.get(f'/almoxarifado/empenho/{empenho.id}/')
    assert pagina_empenho.status_code == 200
    assert f'/almoxarifado/empenhoconsumo/{item1.id}/remover/' not in pagina_empenho.content.decode()

    almox_context.client.get(f'/almoxarifado/empenhoconsumo/{item2.id}/remover/')
    assert empenho.get_itens().count() == quantidade_itens_antes - 1
    assert Empenho.objects.count() == quantidade_empenhos_antes

    entrada = empenho.get_entradas().order_by('-id').first()
    assert entrada is not None
    pagina_detalhe_entrada = almox_context.client.get(f'/almoxarifado/entrada/{entrada.id}/')
    assert pagina_detalhe_entrada.status_code == 200
    assert f'/almoxarifado/entrada/{entrada.id}/remover/' in pagina_detalhe_entrada.content.decode()

    almox_context.client.get(f'/almoxarifado/entrada/{entrada.id}/remover/')
    assert empenho.get_entradas().count() == quantidade_entradas_antes

    almox_context.client.get(f'/almoxarifado/empenhoconsumo/{item1.id}/remover/')
    assert Empenho.objects.count() == quantidade_empenhos_antes - 1


def test_total_do_resumo_por_elemento_de_despesa_usa_a_mesma_mascara_das_linhas(almox_context):
    empenho, item1, item2 = almox_context.criar_empenho_consumo_com_dois_itens(usuario=almox_context.servidor_a)
    almox_context.registrar_entrada_compra(empenho, [item1, item2], [5, 10], numero_nota='001', usuario=almox_context.servidor_a)

    entrada = empenho.get_entradas().order_by('-id').first()
    assert entrada is not None

    # `valor` tem 6 casas e `qtd` 5: o Decimal do produto carrega 11 casas.
    assert entrada.get_valor_total() == Decimal('250.00000000000')

    pagina = almox_context.client.get(f'/almoxarifado/entrada/{entrada.id}/')
    assert pagina.status_code == 200

    # O totalizador do resumo sai da view (`total`), enquanto as linhas já vêm formatadas
    # de `get_elem_despesa_entrada()`; a máscara tem que ser a mesma nos dois.
    assert format_money_almox(entrada.get_valor_total()) == '250,00'
    assert pagina.context['total'] == '250,00'
