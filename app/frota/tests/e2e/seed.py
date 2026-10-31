"""Replay ORM do substrato que o behave do FROTA montava antes de agir (removido no modo 2).

As `.feature` foram a fonte dos nomes, tipos, papéis e datas — aqui só se reproduz o que elas
montavam, sem a obrigação de cobrir os cenários 1:1. Mesmo desenho do replay do `pesquisa`:
idempotente, porque a suíte e2e não dá flush e o CI usa `--reuse-db`.

O que o behave criava no passo ``Dado os dados básicos para frota``
(``frota/features/steps/given.py``) é o que as telas de cadastro exigem: a marca/modelo/cor do
veículo (app ``estacionamento``), o grupo e o status da viatura, e o patrimônio ``PATRIMONIO`` (via
``almoxarifado`` → ``patrimonio``), que o autocomplete de viatura oferece.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from django.apps.registry import apps

if TYPE_CHECKING:
    from rh.models import Servidor


# A tabela ``os seguintes usuários`` da feature 001. ``grupo`` é o papel, e o apelido em
# ``PAPEIS`` (do conftest) aponta para cá.
PAPEIS: dict[str, dict[str, str]] = {
    '107001': {'nome': 'Coord Frota Sistêmico', 'grupo': 'Coordenador de Frota Sistêmico'},
    '107002': {'nome': 'Coord Frota Campus', 'grupo': 'Coordenador de Frota'},
    '107003': {'nome': 'Agendador Frota', 'grupo': 'Agendador de Frota'},
    '107004': {'nome': 'Passageiro Frota', 'grupo': 'Servidor'},
    '107005': {'nome': 'Motorista Frota', 'grupo': 'Servidor'},
}

# Número do bem da viatura, abaixo dos que os outros módulos usam: o job de doc roda vários
# módulos num banco só, o `pesquisa` semeia o 123455 e o `patrimonio` numera os seguintes por
# `max + 1` — com o 123456 de antes, o `get_or_create` herdava o bem do patrimonio, de outro
# campus, e a viatura sumia das telas do coordenador do CZN.
PATRIMONIO = 107100


def _obter(modelo: str, nome: str):
    return apps.get_model(modelo, nome)


def criar_servidor(matricula: str) -> Servidor:
    """Servidor de ``PAPEIS`` com o grupo da feature, lotado no campus CZN."""
    from djtools.e2e_fixtures import campus, servidor_com_login

    dados = PAPEIS[matricula]
    return servidor_com_login(matricula, campus('CZN'), grupos=[dados['grupo']], staff=True, pessoa_fisica__nome=dados['nome'])


def dados_basicos() -> None:
    """Replay de ``os dados básicos para frota``, idempotente."""
    from frota.models import ViaturaGrupo, ViaturaStatus

    VeiculoMarca = _obter('estacionamento', 'VeiculoMarca')
    VeiculoTipo = _obter('estacionamento', 'VeiculoTipo')
    VeiculoEspecie = _obter('estacionamento', 'VeiculoEspecie')
    VeiculoTipoEspecie = _obter('estacionamento', 'VeiculoTipoEspecie')
    VeiculoModelo = _obter('estacionamento', 'VeiculoModelo')
    VeiculoCor = _obter('estacionamento', 'VeiculoCor')
    VeiculoCombustivel = _obter('estacionamento', 'VeiculoCombustivel')
    Municipio = _obter('comum', 'Municipio')
    InventarioStatus = _obter('patrimonio', 'InventarioStatus')
    Inventario = _obter('patrimonio', 'Inventario')
    Entrada = _obter('almoxarifado', 'Entrada')
    EntradaTipo = _obter('almoxarifado', 'EntradaTipo')
    MaterialTipo = _obter('almoxarifado', 'MaterialTipo')
    CategoriaMaterialPermanente = _obter('patrimonio', 'CategoriaMaterialPermanente')
    EntradaPermanente = _obter('patrimonio', 'EntradaPermanente')

    from djtools.e2e_fixtures import campus
    from rh.models import UnidadeOrganizacional

    marca = VeiculoMarca.objects.get_or_create(nome='Ford')[0]
    tipo = VeiculoTipo.objects.get_or_create(descricao='Utilitário')[0]
    especie = VeiculoEspecie.objects.get_or_create(descricao='Comum')[0]
    tipo_especie = VeiculoTipoEspecie.objects.get_or_create(tipo=tipo, especie=especie)[0]
    VeiculoModelo.objects.get_or_create(nome='Ranger', marca=marca, tipo_especie=tipo_especie)
    VeiculoCor.objects.get_or_create(nome='Branca')
    Municipio.objects.get_or_create(nome='Natal', uf='RN')
    ViaturaGrupo.objects.get_or_create(codigo='123', nome='Carro de Passeio', descricao='Carro para transporte de passageiro')
    ViaturaStatus.objects.get_or_create(descricao='Ativa')
    VeiculoCombustivel.objects.get_or_create(nome='Gasolina')

    status = InventarioStatus.objects.get_or_create(nome='Status')[0]
    uo = UnidadeOrganizacional.objects.suap().get(setor=campus('CZN'))
    entrada = Entrada.objects.get_or_create(data=datetime.now(), uo=uo, tipo_entrada=EntradaTipo.DOACAO(), tipo_material=MaterialTipo.PERMANENTE())[0]
    categoria = CategoriaMaterialPermanente.objects.get_or_create(codigo='0', nome='nome')[0]
    entrada_permanente = EntradaPermanente.objects.get_or_create(
        entrada=entrada, categoria=categoria, descricao='descrição', qtd=1, valor=Decimal(10)
    )[0]
    Inventario.objects.get_or_create(numero=PATRIMONIO, defaults={'status': status, 'entrada_permanente': entrada_permanente, 'campo_busca': '0'})


def limpar_execucao_anterior() -> None:
    """Apaga a cadeia da execução anterior — a suíte não dá flush e o CI usa `--reuse-db`.

    As entidades de fluxo (viatura, motorista, agendamento, viagem) são criadas com valores
    fixos das `.feature`; a segunda execução esbarraria na unicidade (ex.: motorista temporário
    com `(vinculo_pessoa, portaria)`). O seed de base não cria nenhuma delas, então `all()` é
    seguro — deleta-se em ordem, do filho ao pai.
    """
    from frota.models import MotoristaTemporario, Viagem, ViagemAgendamento, Viatura

    Viagem.objects.all().delete()
    ViagemAgendamento.objects.all().delete()
    MotoristaTemporario.objects.all().delete()
    Viatura.objects.all().delete()


def montar() -> None:
    """Substrato completo: cadastros básicos e os cinco papéis da feature."""
    limpar_execucao_anterior()
    dados_basicos()
    for matricula in PAPEIS:
        criar_servidor(matricula)


__all__ = ['PAPEIS', 'dados_basicos', 'montar']
