"""Cancelamento de itens de uma entrada de material permanente pela Coordenação de Patrimônio."""

import pytest
from django.apps import apps

Entrada = apps.get_model('almoxarifado', 'Entrada')
Inventario = apps.get_model('patrimonio', 'Inventario')
InventarioCargaContabil = apps.get_model('patrimonio', 'InventarioCargaContabil')
ItemEntradaCancelado = apps.get_model('patrimonio', 'ItemEntradaCancelado')
MovimentoPatrim = apps.get_model('patrimonio', 'MovimentoPatrim')

pytestmark = pytest.mark.django_db

COORDENADOR = 'Coordenador de Patrimônio'
COORDENADOR_SISTEMICO = 'Coordenador de Patrimônio Sistêmico'


def test_botao_remover_itens_visivel_para_coordenador_de_patrimonio(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{patrimonio_context.entrada.pk}/')

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert 'Remover Itens' in conteudo
    assert f'/almoxarifado/entrada/{patrimonio_context.entrada.pk}/cancelar_itens/' in conteudo


def test_botao_remover_itens_oculto_para_quem_nao_e_coordenador_de_patrimonio(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, 'Coordenador de Almoxarifado')

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{patrimonio_context.entrada.pk}/')

    assert resposta.status_code == 200
    assert f'/almoxarifado/entrada/{patrimonio_context.entrada.pk}/cancelar_itens/' not in resposta.content.decode()


def test_usuario_sem_grupo_nao_acessa_a_tela_de_remocao(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, 'Coordenador de Almoxarifado')

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{patrimonio_context.entrada.pk}/cancelar_itens/')

    assert resposta.status_code == 403


def test_coordenador_de_outro_campus_nao_remove_itens(patrimonio_context):
    entrada_outro_campus, _ = patrimonio_context.criar_entrada(uo=patrimonio_context.outro_campus)
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{entrada_outro_campus.pk}/cancelar_itens/')

    assert resposta.status_code == 403


def test_coordenador_sistemico_remove_itens_de_outro_campus(patrimonio_context):
    entrada_outro_campus, itens = patrimonio_context.criar_entrada(uo=patrimonio_context.outro_campus)
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR_SISTEMICO)

    patrimonio_context.cancelar(entrada_outro_campus, [itens[0]])

    assert not entrada_outro_campus.entradapermanente_set.filter(pk=itens[0].pk).exists()


def test_remove_apenas_os_itens_marcados(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada, item_a, item_b = patrimonio_context.entrada, patrimonio_context.item_a, patrimonio_context.item_b

    resposta = patrimonio_context.cancelar(entrada, [item_a], justificativa='Item devolvido ao fornecedor.')

    assert resposta.status_code == 302
    assert not entrada.entradapermanente_set.filter(pk=item_a.pk).exists()
    assert entrada.entradapermanente_set.filter(pk=item_b.pk).exists()


def test_remove_inventarios_e_movimentacao_dos_itens_marcados(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada, item_a, item_b = patrimonio_context.entrada, patrimonio_context.item_a, patrimonio_context.item_b
    inventarios_removidos = list(item_a.inventario_set.values_list('pk', flat=True))
    inventarios_mantidos = list(item_b.inventario_set.values_list('pk', flat=True))
    assert inventarios_removidos
    assert inventarios_mantidos

    patrimonio_context.cancelar(entrada, [item_a])

    assert not Inventario.objects.filter(pk__in=inventarios_removidos).exists()
    assert not InventarioCargaContabil.objects.filter(inventario_id__in=inventarios_removidos).exists()
    assert not MovimentoPatrim.objects.filter(inventario_id__in=inventarios_removidos).exists()
    assert Inventario.objects.filter(pk__in=inventarios_mantidos).count() == len(inventarios_mantidos)


def test_remove_item_ja_transferido_junto_com_sua_movimentacao(patrimonio_context):
    """O estorno recusa item movimentado; o cancelamento o aceita e remove a movimentação."""
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada, item_a = patrimonio_context.entrada, patrimonio_context.item_a
    patrimonio_context.transferir_inventarios(item_a)
    inventarios = list(item_a.inventario_set.values_list('pk', flat=True))
    assert MovimentoPatrim.objects.filter(inventario_id__in=inventarios).exists()
    assert not item_a.can_delete()

    resposta = patrimonio_context.cancelar(entrada, [item_a])

    assert resposta.status_code == 302
    assert not entrada.entradapermanente_set.filter(pk=item_a.pk).exists()
    assert not Inventario.objects.filter(pk__in=inventarios).exists()
    assert not MovimentoPatrim.objects.filter(inventario_id__in=inventarios).exists()


def test_registra_auditoria_vinculada_a_entrada(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada, item_a = patrimonio_context.entrada, patrimonio_context.item_a
    numeros = sorted(item_a.inventario_set.values_list('numero', flat=True))

    patrimonio_context.cancelar(entrada, [item_a], justificativa='Nota fiscal cancelada.')

    registro = ItemEntradaCancelado.objects.get(entrada=entrada)
    assert registro.descricao == item_a.descricao
    assert registro.qtd == item_a.qtd
    assert registro.justificativa == 'Nota fiscal cancelada.'
    assert registro.cancelado_por == patrimonio_context.servidor.get_user()
    assert registro.numeros_inventario == ', '.join(str(numero) for numero in numeros)


def test_entrada_e_auditoria_sobrevivem_a_remocao_de_todos_os_itens(patrimonio_context):
    """A entrada precisa continuar existindo — é nela que a aba 'Itens Removidos' vive."""
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada = patrimonio_context.entrada

    patrimonio_context.cancelar(entrada, [patrimonio_context.item_a, patrimonio_context.item_b])

    entrada.refresh_from_db()
    assert not entrada.entradapermanente_set.exists()
    assert ItemEntradaCancelado.objects.filter(entrada=entrada).count() == 2


def test_botao_remover_itens_oculto_quando_todos_os_itens_ja_foram_removidos(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada = patrimonio_context.entrada
    patrimonio_context.cancelar(entrada, [patrimonio_context.item_a, patrimonio_context.item_b])

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{entrada.pk}/')

    assert resposta.status_code == 200
    assert f'/almoxarifado/entrada/{entrada.pk}/cancelar_itens/' not in resposta.content.decode()


def test_botao_remover_itens_oculto_quando_so_restam_itens_bloqueados(patrimonio_context):
    """Sem nenhum item marcável, a tela de remoção não teria o que oferecer."""
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada = patrimonio_context.entrada
    patrimonio_context.baixar_inventarios(patrimonio_context.item_a)
    patrimonio_context.baixar_inventarios(patrimonio_context.item_b)

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{entrada.pk}/')

    assert resposta.status_code == 200
    assert f'/almoxarifado/entrada/{entrada.pk}/cancelar_itens/' not in resposta.content.decode()


def test_tela_de_remocao_bloqueada_quando_nao_ha_item_removivel(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada = patrimonio_context.entrada
    patrimonio_context.cancelar(entrada, [patrimonio_context.item_a, patrimonio_context.item_b])

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{entrada.pk}/cancelar_itens/')

    assert resposta.status_code == 403


def test_entrada_com_itens_removidos_nao_pode_ser_excluida(patrimonio_context):
    """Excluir a entrada apagaria o registro auditável da remoção."""
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR, 'Coordenador de Almoxarifado')
    entrada = patrimonio_context.entrada
    patrimonio_context.cancelar(entrada, [patrimonio_context.item_a, patrimonio_context.item_b])

    entrada.refresh_from_db()
    assert not entrada.can_delete()

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{entrada.pk}/remover/')

    assert resposta.status_code == 302
    assert Entrada.objects.filter(pk=entrada.pk).exists()
    assert ItemEntradaCancelado.objects.filter(entrada=entrada).count() == 2


def test_botao_remover_entrada_oculto_quando_ha_itens_removidos(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR, 'Coordenador de Almoxarifado')
    entrada = patrimonio_context.entrada
    patrimonio_context.cancelar(entrada, [patrimonio_context.item_a, patrimonio_context.item_b])

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{entrada.pk}/')

    assert f'/almoxarifado/entrada/{entrada.pk}/remover/' not in resposta.content.decode()


def test_estorno_do_ultimo_item_preserva_entrada_com_historico(patrimonio_context):
    """O estorno descarta a entrada esvaziada, salvo quando ela guarda itens removidos."""
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada, item_a, item_b = patrimonio_context.entrada, patrimonio_context.item_a, patrimonio_context.item_b
    patrimonio_context.cancelar(entrada, [item_a])

    item_b.delete()

    assert Entrada.objects.filter(pk=entrada.pk).exists()
    assert ItemEntradaCancelado.objects.filter(entrada=entrada).count() == 1


def test_aba_itens_removidos_ausente_quando_nada_foi_removido(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{patrimonio_context.entrada.pk}/')

    conteudo = resposta.content.decode()
    assert 'Itens Removidos' not in conteudo
    assert 'itens_removidos' not in conteudo


def test_aba_itens_removidos_exibe_os_registros(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada, item_a = patrimonio_context.entrada, patrimonio_context.item_a
    patrimonio_context.cancelar(entrada, [item_a], justificativa='Duplicidade de lançamento.')

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{entrada.pk}/')

    conteudo = resposta.content.decode()
    assert 'Itens Removidos' in conteudo
    assert 'Duplicidade de lançamento.' in conteudo
    assert item_a.descricao in conteudo


def test_item_com_inventario_baixado_e_bloqueado(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada, item_a = patrimonio_context.entrada, patrimonio_context.item_a
    patrimonio_context.baixar_inventarios(item_a)

    resposta = patrimonio_context.cancelar(entrada, [item_a])

    assert resposta.status_code == 200
    assert entrada.entradapermanente_set.filter(pk=item_a.pk).exists()
    assert not ItemEntradaCancelado.objects.filter(entrada=entrada).exists()


def test_justificativa_e_obrigatoria(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada, item_a = patrimonio_context.entrada, patrimonio_context.item_a

    resposta = patrimonio_context.cancelar(entrada, [item_a], justificativa='')

    assert resposta.status_code == 200
    assert entrada.entradapermanente_set.filter(pk=item_a.pk).exists()
    assert not ItemEntradaCancelado.objects.exists()


def test_selecao_vazia_nao_remove_nada(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR)
    entrada = patrimonio_context.entrada

    resposta = patrimonio_context.cancelar(entrada, [])

    assert resposta.status_code == 200
    assert entrada.entradapermanente_set.count() == 2
    assert not ItemEntradaCancelado.objects.exists()


def test_nao_remove_item_de_outra_entrada(patrimonio_context):
    """O queryset do formulário é restrito à entrada da URL, barrando POST manipulado."""
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR_SISTEMICO)
    outra_entrada, itens_da_outra = patrimonio_context.criar_entrada()

    resposta = patrimonio_context.cancelar(patrimonio_context.entrada, [itens_da_outra[0]])

    assert resposta.status_code == 200
    assert outra_entrada.entradapermanente_set.filter(pk=itens_da_outra[0].pk).exists()
    assert not ItemEntradaCancelado.objects.exists()


def test_entrada_de_consumo_nao_aceita_remocao_de_itens(patrimonio_context):
    from django.apps import apps as django_apps

    MaterialTipo = django_apps.get_model('almoxarifado', 'MaterialTipo')
    patrimonio_context.login(patrimonio_context.servidor, COORDENADOR_SISTEMICO)
    entrada = patrimonio_context.entrada
    entrada.tipo_material = MaterialTipo.CONSUMO()
    entrada.save()

    resposta = patrimonio_context.client.get(f'/almoxarifado/entrada/{entrada.pk}/cancelar_itens/')

    assert resposta.status_code == 403
