import uuid
from dataclasses import dataclass

import pytest
from django.apps import apps

from comum.tests.factories import PrestadorServicoFactory
from rh.tests.factories import PessoaJuridicaFactory, ServidorFactory, SetorFactory

from almoxarifado.forms import EmpenhoForm
from almoxarifado.tests.factories import MovimentoAlmoxEntradaTipoFactory, MovimentoAlmoxSaidaTipoFactory

PlanoContasAlmox = apps.get_model('almoxarifado', 'PlanoContasAlmox')
CategoriaMaterialConsumo = apps.get_model('almoxarifado', 'CategoriaMaterialConsumo')
Empenho = apps.get_model('almoxarifado', 'Empenho')
EntradaTipo = apps.get_model('almoxarifado', 'EntradaTipo')
Group = apps.get_model('auth', 'Group')
MaterialConsumo = apps.get_model('almoxarifado', 'MaterialConsumo')
MaterialTipo = apps.get_model('almoxarifado', 'MaterialTipo')
MovimentoAlmoxEntradaTipo = apps.get_model('almoxarifado', 'MovimentoAlmoxEntradaTipo')
MovimentoAlmoxSaidaTipo = apps.get_model('almoxarifado', 'MovimentoAlmoxSaidaTipo')
Processo = apps.get_model('protocolo', 'Processo')
Servidor = apps.get_model('rh', 'Servidor')
UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')


@dataclass
class AlmoxContext:
    client: object
    servidor_a: object
    servidor_b: object
    pessoa_juridica: object
    prestador_1: object
    campus_a_suap: object
    campus_b_suap: object
    processo: object
    mat1: object
    mat2: object

    def login(self, servidor):
        self.client.logout()
        self.client.force_login(servidor.get_user())

    def criar_empenho(self, tipo_pessoa='juridica', usuario=None):
        self.login(usuario or self.servidor_a)
        numero_empenho = f'2026NE{uuid.uuid4().int % 1_000_000:06d}'
        payload = {
            'numero': numero_empenho,
            'processo': self.processo.pk,
            'tipo_material': MaterialTipo.CONSUMO().pk,
        }

        if tipo_pessoa == 'juridica':
            payload.update(
                {
                    'tipo_pessoa': EmpenhoForm.TIPO_PESSOA_JURIDICA,
                    # O campo do form é `Vinculo.objects.pessoas_juridicas()`, então o valor
                    # é o id do VÍNCULO, não o da PessoaJuridica — igual ao ramo da pessoa
                    # física logo abaixo. Com o `suap_data` os dois ids coincidiam por ordem
                    # de inserção e o teste passava por acaso.
                    'pessoa_juridica': self.pessoa_juridica.get_vinculo().id,
                }
            )
        else:
            payload.update(
                {
                    'tipo_pessoa': EmpenhoForm.TIPO_PESSOA_FISICA,
                    'pessoa_fisica': self.prestador_1.get_vinculo().id,
                }
            )

        response = self.client.post('/admin/almoxarifado/empenho/add/', payload)
        assert response.status_code in (200, 302)
        empenho = Empenho.objects.filter(numero=numero_empenho).order_by('-id').first()
        assert empenho is not None
        return empenho

    def adicionar_itens_ao_empenho(self, empenho, itens):
        for material, qtd_empenhada, valor in itens:
            self.client.post(
                f'/almoxarifado/empenho/{empenho.pk}/',
                {'material': material.pk, 'qtd_empenhada': str(qtd_empenhada), 'valor': valor},
            )

        return [empenho.get_itens().get(material=material) for material, _, _ in itens]

    def criar_empenho_consumo_com_dois_itens(self, tipo_pessoa='juridica', usuario=None):
        empenho = self.criar_empenho(tipo_pessoa=tipo_pessoa, usuario=usuario)
        item1, item2 = self.adicionar_itens_ao_empenho(
            empenho,
            [
                (self.mat1, 10, '10,00'),
                (self.mat2, 10, '20,00'),
            ],
        )
        return empenho, item1, item2

    def registrar_entrada_compra(self, empenho, itens_empenho, quantidades, numero_nota='001', usuario=None):
        self.login(usuario or self.servidor_a)
        self.client.post(
            '/almoxarifado/entrada_realizar/',
            {
                'data_entrada': '01/01/2012',
                'empenho_hidden': empenho.pk,
                # A view faz `Vinculo.objects.get(pk=...)` com este valor: é o id do VÍNCULO,
                # mesmo caso do campo `pessoa_juridica` do EmpenhoForm.
                'fornecedor_hidden': self.pessoa_juridica.get_vinculo().id,
                'numero_nota': numero_nota,
                'data_nota': '01/01/2012',
                'empenho_itens': [item.pk for item in itens_empenho],
                'qtds': quantidades,
            },
        )

    def preparar_cenario_estoque_em_dois_campi(self):
        empenho, item1, item2 = self.criar_empenho_consumo_com_dois_itens(tipo_pessoa='juridica', usuario=self.servidor_a)
        self.registrar_entrada_compra(empenho, [item1, item2], [5, 10], numero_nota='001', usuario=self.servidor_a)
        self.registrar_entrada_compra(empenho, [item1], [5], numero_nota='002', usuario=self.servidor_b)
        return empenho, item1, item2


def _garantir_tipo_material_unico(nome):
    tipo = MaterialTipo.objects.filter(nome=nome).order_by('id').first()
    if tipo is None:
        tipo = MaterialTipo.objects.create(nome=nome)
    MaterialTipo.objects.filter(nome=nome).exclude(id=tipo.id).delete()
    return tipo


SENHA = '123'


def _com_senha(servidor):
    """A remoção de empenho no admin exige a senha no POST (`{'senha': ...}`), não só o
    login — e o `ServidorFactory` não define senha alguma."""
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    return servidor


@pytest.fixture
def almox_context(client, db, sync_permissions):
    # Um servidor por campus: a entrada de material vai para a UO de QUEM registra, e os
    # testes de campi distintos conferem o estoque de cada uma separadamente.
    servidor_a = _com_senha(ServidorFactory())
    servidor_b = _com_senha(ServidorFactory())
    campus_a_suap = servidor_a.setor.uo
    campus_b_suap = servidor_b.setor.uo
    pessoa_juridica = PessoaJuridicaFactory()
    prestador_1 = PrestadorServicoFactory(setor=servidor_a.setor)

    grupo, _ = Group.objects.get_or_create(name='Coordenador de Almoxarifado')
    servidor_a.get_user().groups.add(grupo)
    servidor_b.get_user().groups.add(grupo)

    sufixo = uuid.uuid4().hex[:8]
    codigo = next((str(i).zfill(2) for i in range(100) if not PlanoContasAlmox.objects.filter(codigo=str(i).zfill(2)).exists()), None)
    assert codigo is not None
    plano = PlanoContasAlmox.objects.create(codigo=codigo, descricao=f'Plano Contas {sufixo}')
    categoria = CategoriaMaterialConsumo.objects.create(codigo=codigo, nome=f'Categoria {sufixo}', plano_contas=plano)

    mat1 = MaterialConsumo.objects.create(categoria=categoria, nome=f'Material para consumir {sufixo}')
    mat2 = MaterialConsumo.objects.create(categoria=categoria, nome=f'Mais material de consumo {sufixo}')

    processo = Processo.objects.create(
        vinculo_cadastro=servidor_a.get_vinculo(),
        assunto=f'Assunto {sufixo}',
        tipo=1,
        setor_origem=servidor_a.setor,
    )

    _garantir_tipo_material_unico('consumo')
    _garantir_tipo_material_unico('permanente')
    EntradaTipo.objects.update_or_create(id=1, defaults={'nome': 'compra'})
    EntradaTipo.objects.update_or_create(id=2, defaults={'nome': 'doacao'})
    EntradaTipo.objects.filter(nome='compra').exclude(id=1).delete()
    EntradaTipo.objects.filter(nome='doacao').exclude(id=2).delete()
    # Mesmas linhas de referência que a suíte e2e precisa; via factory para não haver duas
    # cópias da lista de nomes (ver almoxarifado/tests/factories.py).
    MovimentoAlmoxEntradaTipoFactory(nome='entrada')
    MovimentoAlmoxEntradaTipoFactory(nome='requisicao_uo_material')
    MovimentoAlmoxSaidaTipoFactory(nome='requisicao_user_material')
    MovimentoAlmoxSaidaTipoFactory(nome='requisicao_uo_material')

    return AlmoxContext(
        client=client,
        servidor_a=servidor_a,
        servidor_b=servidor_b,
        pessoa_juridica=pessoa_juridica,
        prestador_1=prestador_1,
        campus_a_suap=campus_a_suap,
        campus_b_suap=campus_b_suap,
        processo=processo,
        mat1=mat1,
        mat2=mat2,
    )
