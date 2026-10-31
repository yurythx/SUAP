import uuid
from dataclasses import dataclass
from datetime import datetime

import pytest
from django.apps import apps

from comum.pytest_fixtures import api_auth_mocks
from rh.tests.factories import ServidorFactory

CategoriaMaterialPermanente = apps.get_model('patrimonio', 'CategoriaMaterialPermanente')
Entrada = apps.get_model('almoxarifado', 'Entrada')
EntradaPermanente = apps.get_model('patrimonio', 'EntradaPermanente')
EntradaTipo = apps.get_model('almoxarifado', 'EntradaTipo')
Group = apps.get_model('auth', 'Group')
InventarioStatus = apps.get_model('patrimonio', 'InventarioStatus')
MaterialTipo = apps.get_model('almoxarifado', 'MaterialTipo')
MovimentoPatrim = apps.get_model('patrimonio', 'MovimentoPatrim')
MovimentoPatrimTipo = apps.get_model('patrimonio', 'MovimentoPatrimTipo')
PlanoContas = apps.get_model('patrimonio', 'PlanoContas')
Servidor = apps.get_model('rh', 'Servidor')
UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')


@dataclass
class PatrimonioContext:
    """Cenário mínimo de uma entrada de material permanente com itens e inventários."""

    client: object
    servidor: object
    servidor_outro_campus: object
    campus: object
    outro_campus: object
    categoria: object
    entrada: object
    item_a: object
    item_b: object

    def login(self, servidor, *grupos):
        for nome in grupos:
            grupo, _ = Group.objects.get_or_create(name=nome)
            servidor.get_user().groups.add(grupo)
        self.client.logout()
        self.client.force_login(servidor.get_user())

    def criar_entrada(self, uo=None, quantidades=(2, 3)):
        entrada = Entrada.objects.create(
            data=datetime.now(),
            uo=uo or self.campus,
            tipo_entrada=EntradaTipo.objects.get(nome='doacao'),
            tipo_material=MaterialTipo.PERMANENTE(),
        )
        itens = [
            EntradaPermanente.objects.create(
                entrada=entrada, categoria=self.categoria, descricao=f'Item {indice} {uuid.uuid4().hex[:6]}', qtd=qtd, valor='100.00'
            )
            for indice, qtd in enumerate(quantidades, start=1)
        ]
        return entrada, itens

    def transferir_inventarios(self, item):
        """
        Simula um item já movimentado.

        A transferência é o cenário que o estorno (``can_delete``) recusa e que o
        cancelamento precisa aceitar, removendo a movimentação junto.
        """
        for inventario in item.inventario_set.all():
            MovimentoPatrim.objects.create(
                inventario=inventario,
                tipo=MovimentoPatrimTipo.TRANSFERENCIA(),
                vinculo=self.servidor.get_vinculo(),
                data=datetime.now(),
            )

    def baixar_inventarios(self, item):
        item.inventario_set.update(status=InventarioStatus.BAIXADO())

    def cancelar(self, entrada, itens, justificativa='Nota fiscal cancelada pelo fornecedor.'):
        return self.client.post(
            f'/almoxarifado/entrada/{entrada.pk}/cancelar_itens/',
            {'itens': [item.pk for item in itens], 'justificativa': justificativa},
        )


def _garantir_tipo_material(nome):
    tipo = MaterialTipo.objects.filter(nome=nome).order_by('id').first()
    if tipo is None:
        tipo = MaterialTipo.objects.create(nome=nome)
    MaterialTipo.objects.filter(nome=nome).exclude(id=tipo.id).delete()
    return tipo


def _garantir_dados_de_referencia():
    for nome in ('pendente', 'ativo', 'baixado'):
        InventarioStatus.objects.get_or_create(nome=nome)
    for nome in ('pendência', 'transferência', 'baixa', 'estorno'):
        MovimentoPatrimTipo.objects.get_or_create(nome=nome)
    _garantir_tipo_material('consumo')
    _garantir_tipo_material('permanente')
    EntradaTipo.objects.update_or_create(id=1, defaults={'nome': 'compra'})
    EntradaTipo.objects.update_or_create(id=2, defaults={'nome': 'doacao'})
    EntradaTipo.objects.filter(nome='compra').exclude(id=1).delete()
    EntradaTipo.objects.filter(nome='doacao').exclude(id=2).delete()


@pytest.fixture
def dados_referencia(db):
    """Tabelas de referência do patrimônio (status, tipos de movimento, tipos de entrada).

    São consultadas por nome (``InventarioStatus.ATIVO()``, ``EntradaTipo.COMPRA()``), então
    qualquer teste que crie tombamento depende delas.
    """
    _garantir_dados_de_referencia()


@pytest.fixture
def patrimonio_context(client, db, sync_permissions, dados_referencia):

    # Um servidor por campus: o patrimônio é por unidade, e vários testes conferem o que
    # acontece quando origem e destino são campi diferentes.
    servidor = ServidorFactory()
    servidor_outro_campus = ServidorFactory()
    campus = servidor.setor.uo
    outro_campus = servidor_outro_campus.setor.uo

    sufixo = uuid.uuid4().hex[:8]
    codigo = next((str(i).zfill(2) for i in range(100) if not PlanoContas.objects.filter(codigo=str(i).zfill(2)).exists()), None)
    assert codigo is not None
    plano = PlanoContas.objects.create(codigo=codigo, descricao=f'Plano de Contas {sufixo}')
    categoria = CategoriaMaterialPermanente.objects.create(codigo=codigo, nome=f'Elemento de Despesa {sufixo}', plano_contas=plano)

    contexto = PatrimonioContext(
        client=client,
        servidor=servidor,
        servidor_outro_campus=servidor_outro_campus,
        campus=campus,
        outro_campus=outro_campus,
        categoria=categoria,
        entrada=None,
        item_a=None,
        item_b=None,
    )
    contexto.entrada, (contexto.item_a, contexto.item_b) = contexto.criar_entrada()
    return contexto
