"""Fixtures compartilhadas pelos testes de fluxo da Frota.

A ideia central é montar o *estado mínimo* de cada etapa do fluxo de viagem por
ORM (rápido e legível) e deixar para os testes apenas o exercício do endpoint
que representa a ação do usuário. Assim cada teste é independente: não há mais
um teste chamando o outro para reconstruir o cenário.

O ciclo de vida modelado é:

    cadastrar viatura/motorista  ->  solicitar agendamento
        ->  deferir agendamento (reserva viatura + motorista)
        ->  registrar saída  ->  registrar chegada
"""

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from rh.tests.factories import ServidorFactory
from django.contrib.auth.models import Group

from almoxarifado.models import Entrada, EntradaTipo, MaterialTipo
from comum.models import Municipio
from estacionamento.models import (
    VeiculoCombustivel,
    VeiculoCor,
    VeiculoEspecie,
    VeiculoMarca,
    VeiculoModelo,
    VeiculoTipo,
    VeiculoTipoEspecie,
)
from frota.models import MotoristaTemporario, Viagem, ViagemAgendamento, ViagemAgendamentoResposta, Viatura, ViaturaGrupo, ViaturaStatus
from patrimonio.models import CategoriaMaterialPermanente, EntradaPermanente, Inventario, InventarioStatus, MovimentoPatrimTipo

# Datas fixas no futuro para a viagem; o ano evita colisão com agendamentos "fora do prazo".
PROXIMO_ANO = datetime.datetime.now().year + 1
SAIDA = datetime.datetime(PROXIMO_ANO, 1, 1, 8, 0)
CHEGADA = datetime.datetime(PROXIMO_ANO, 1, 10, 18, 0)


@pytest.fixture
def coordenador(db, sync_permissions):
    """Servidor com acesso sistêmico à Frota — quem avalia e opera as viagens."""
    servidor = ServidorFactory()
    user = servidor.get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Frota Sistêmico'))
    return SimpleNamespace(servidor=servidor, user=user, vinculo=user.get_vinculo())


@pytest.fixture
def campus(coordenador):
    """Campus das viaturas e do patrimônio — o do coordenador, como no cenário original."""
    return coordenador.servidor.setor.uo


@pytest.fixture
def cliente(suap_client, coordenador):
    """Client autenticado como Coordenador de Frota."""
    suap_client.login(user=coordenador.user)
    return suap_client


@pytest.fixture
def catalogo(db):
    """Dados de referência de veículos: taxonomia, combustível, grupo e situações.

    São tabelas de domínio reaproveitadas por viaturas e viagens.
    """
    marca = VeiculoMarca.objects.get_or_create(nome='Ford')[0]
    tipo = VeiculoTipo.objects.get_or_create(descricao='Utilitário')[0]
    especie = VeiculoEspecie.objects.get_or_create(descricao='Comum')[0]
    tipo_especie = VeiculoTipoEspecie.objects.get_or_create(tipo=tipo, especie=especie)[0]
    return SimpleNamespace(
        modelo=VeiculoModelo.objects.get_or_create(nome='Ranger', marca=marca, tipo_especie=tipo_especie)[0],
        cor=VeiculoCor.objects.get_or_create(nome='Branca')[0],
        combustivel=VeiculoCombustivel.objects.get_or_create(nome='Gasolina')[0],
        grupo=ViaturaGrupo.objects.get_or_create(codigo='123', nome='Carro de Passeio', descricao='Transporte de passageiros')[0],
        municipio=Municipio.objects.get_or_create(nome='Natal', uf='RN', codigo='NAT')[0],
        # Situações exigidas pelos formulários de saída/chegada ao mudar o estado da viatura.
        status_ativa=ViaturaStatus.objects.get_or_create(descricao='Ativa')[0],
        status_disponivel=ViaturaStatus.objects.get_or_create(descricao='Disponível')[0],
        status_transito=ViaturaStatus.objects.get_or_create(descricao='Em Trânsito')[0],
    )


@pytest.fixture
def patrimonio(campus, catalogo):
    """Inventário patrimonial válido — só é exigido no cadastro de viatura via admin."""
    for nome in ('pendente', 'ativo', 'baixado'):
        InventarioStatus.objects.get_or_create(nome=nome)
    inventario_status = InventarioStatus.objects.get(nome='ativo')
    for nome in ('pendência', 'transferência', 'baixa', 'estorno'):
        MovimentoPatrimTipo.objects.get_or_create(nome=nome)

    # Tabelas de domínio consultadas pela cadeia de save() do patrimônio/inventário.
    EntradaTipo.objects.get_or_create(nome='compra')
    MaterialTipo.objects.get_or_create(nome='consumo')
    uo = campus
    entrada = Entrada.objects.get_or_create(
        data=datetime.datetime.now(),
        uo=uo,
        tipo_entrada=EntradaTipo.objects.get_or_create(nome='doacao')[0],
        tipo_material=MaterialTipo.objects.get_or_create(nome='permanente')[0],
    )[0]
    entrada_permanente = EntradaPermanente.objects.get_or_create(
        entrada=entrada,
        categoria=CategoriaMaterialPermanente.objects.get_or_create(codigo='0', nome='nome')[0],
        descricao='descrição',
        qtd=1,
        valor=Decimal(10),
    )[0]
    inventario = Inventario.objects.filter(entrada_permanente=entrada_permanente).first()
    if inventario is None:
        ultimo = Inventario.objects.order_by('-numero').first()
        inventario = Inventario.objects.create(
            numero=(ultimo.numero + 1) if ultimo else 1,
            status=inventario_status,
            entrada_permanente=entrada_permanente,
            campo_busca='0',
        )
    return inventario


@pytest.fixture
def viatura(campus, catalogo):
    """Viatura ativa pronta para ser escalada em uma viagem (sem patrimônio, que é opcional)."""
    viatura = Viatura.objects.create(
        modelo=catalogo.modelo,
        cor=catalogo.cor,
        ano_fabric=2020,
        placa_codigo_atual='MXY-0001',
        lotacao=10,
        odometro=1000,
        capacidade_tanque=150,
        grupo=catalogo.grupo,
        status=catalogo.status_disponivel,
        campus=campus,
        ativo=True,
    )
    viatura.combustiveis.add(catalogo.combustivel)
    return viatura


@pytest.fixture
def motorista(db, sync_permissions):
    """Vínculo habilitado como motorista temporário (portaria sem data limite = sempre válida)."""
    vinculo = ServidorFactory().get_user().get_vinculo()
    MotoristaTemporario.objects.create(
        vinculo_pessoa=vinculo,
        portaria='1',
        ano_portaria=2015,
        validade_inicial=datetime.date(2012, 2, 1),
        obs='Portaria de teste',
    )
    return vinculo


@pytest.fixture
def agendamento(coordenador):
    """Solicitação de viagem pendente de avaliação."""
    solicitante = coordenador.vinculo
    agendamento = ViagemAgendamento.objects.create(
        vinculo_solicitante=solicitante,
        objetivo='Apresentação dos módulos do SUAP',
        intinerario='Ida para Caicó por Currais Novos',
        data_saida=SAIDA,
        data_chegada=CHEGADA,
        local_saida='Saindo do CNAT',
        nome_responsavel='Nome do Responsável',
        telefone_responsavel='(84) 12346-7898',
    )
    agendamento.vinculos_passageiros.add(solicitante)
    return agendamento


@pytest.fixture
def agendamento_deferido(coordenador, agendamento, viatura, motorista):
    """Agendamento já deferido, com viatura e motorista reservados (pré-condição da saída)."""
    agendamento.status = 'Deferida'
    agendamento.save()
    resposta = ViagemAgendamentoResposta.objects.create(
        agendamento=agendamento,
        vinculo_responsavel=coordenador.vinculo,
        data=datetime.datetime.now(),
        viatura=viatura,
        obs='Deferido para teste',
    )
    resposta.motoristas.add(motorista)
    return SimpleNamespace(agendamento=agendamento, resposta=resposta, viatura=viatura, motorista=motorista)


@pytest.fixture
def viagem_iniciada(coordenador, agendamento_deferido):
    """Viagem com saída registrada e ainda sem chegada (pré-condição da chegada)."""
    cenario = agendamento_deferido
    viagem = Viagem.objects.create(
        agendamento_resposta=cenario.resposta,
        viatura=cenario.viatura,
        saida_odometro=1000,
        saida_data=SAIDA,
    )
    viagem.motoristas.add(cenario.motorista)
    viagem.vinculos_passageiros.add(coordenador.vinculo)
    return SimpleNamespace(viagem=viagem, **cenario.__dict__)
