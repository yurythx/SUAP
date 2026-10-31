"""Migração de inventários por planilha: conferência do arquivo e escrita da cadeia patrimonial."""

import io

import pytest
from django.apps import apps
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from djtools.storages.utils import get_temp_storage
from patrimonio import migrador

Empenho = apps.get_model('almoxarifado', 'Empenho')
Entrada = apps.get_model('almoxarifado', 'Entrada')
EntradaTipo = apps.get_model('almoxarifado', 'EntradaTipo')
EmpenhoPermanente = apps.get_model('patrimonio', 'EmpenhoPermanente')
EntradaPermanente = apps.get_model('patrimonio', 'EntradaPermanente')
Inventario = apps.get_model('patrimonio', 'Inventario')
InventarioStatus = apps.get_model('patrimonio', 'InventarioStatus')
MovimentoPatrim = apps.get_model('patrimonio', 'MovimentoPatrim')
MovimentoPatrimTipo = apps.get_model('patrimonio', 'MovimentoPatrimTipo')
InventarioRotulo = apps.get_model('patrimonio', 'InventarioRotulo')
PessoaExterna = apps.get_model('rh', 'PessoaExterna')
PessoaFisica = apps.get_model('rh', 'PessoaFisica')
PessoaJuridica = apps.get_model('rh', 'PessoaJuridica')
Processo = apps.get_model('protocolo', 'Processo')
Requisicao = apps.get_model('patrimonio', 'Requisicao')
RequisicaoItem = apps.get_model('patrimonio', 'RequisicaoItem')
User = apps.get_model('comum', 'User')

pytestmark = pytest.mark.django_db

CNPJ = '11.222.333/0001-81'
OUTRO_CNPJ = '44.555.666/0001-81'
CPF = '111.444.777-35'
GRUPO_MIGRADOR = 'Migrador de Patrimônio'


def planilha(linhas, colunas=None):
    """Monta um CSV em memória no layout do migrador."""
    colunas = colunas or [coluna.nome for coluna in migrador.COLUNAS]
    conteudo = [';'.join(colunas)]
    conteudo += [';'.join(str(linha.get(coluna, '')) for coluna in colunas) for linha in linhas]
    arquivo = io.BytesIO('\n'.join(conteudo).encode('utf-8'))
    arquivo.name = 'migracao.csv'
    return arquivo


@pytest.fixture
def cenario(patrimonio_context):
    """Atalhos do cenário: quem migra, para onde, com qual elemento de despesa e em que sala."""
    contexto = patrimonio_context
    contexto.sala_nome = 'Sala do Migrador'
    contexto.processo = Processo.objects.create(
        vinculo_cadastro=contexto.servidor.get_vinculo(),
        assunto='Migração do acervo patrimonial',
        tipo=1,
        setor_origem=contexto.servidor.setor,
    )
    contexto.linha_base = {
        'campus_sigla': contexto.campus.sigla,
        'empenho_numero': '2024NE800123',
        'fornecedor_documento': CNPJ,
        'fornecedor_nome': 'MOVEIS BRASIL LTDA',
        'nota_fiscal_numero': '4567',
        'nota_fiscal_data': '15/03/2024',
        'entrada_data': '20/03/2024',
        'elemento_despesa_codigo': contexto.categoria.codigo,
        'descricao': 'Cadeira giratória',
        'valor': '389,90',
        'estado_conservacao': 'bom',
    }
    return contexto


def migrar(cenario, linhas):
    """Executa a migração das `linhas` e devolve o resumo produzido."""
    conferencia = migrador.conferir(planilha(linhas))
    assert conferencia.valida, [str(erro) for erro in conferencia.erros]
    return migrador.executar(conferencia, cenario.servidor.get_user())


def migrados(resumo):
    """
    Só os inventários criados por esta migração.

    O cenário de teste já nasce com uma entrada e cinco inventários, então contar tudo o que
    está na base misturaria os dois.
    """
    return Inventario.objects.filter(entrada_permanente__entrada__in=resumo['entradas_criadas'])


def itens_migrados(resumo):
    return EntradaPermanente.objects.filter(entrada__in=resumo['entradas_criadas'])


# ---------------------------------------------------------------------------
# Conferência
# ---------------------------------------------------------------------------


def test_confere_planilha_valida_sem_erros(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    assert conferencia.valida
    assert conferencia.total_bens == 1
    assert conferencia.total_pendentes == 1


def test_recusa_planilha_sem_coluna_obrigatoria(cenario):
    colunas = [coluna.nome for coluna in migrador.COLUNAS if coluna.nome != 'valor']

    with pytest.raises(ValidationError, match='Valor Unitário'):
        migrador.conferir(planilha([cenario.linha_base], colunas=colunas))


def test_coluna_de_empenho_continua_obrigatoria_no_cabecalho(cenario):
    """A célula pode ficar vazia (doação), mas a coluna precisa estar na planilha."""
    colunas = [coluna.nome for coluna in migrador.COLUNAS if coluna.nome != 'empenho_numero']

    with pytest.raises(ValidationError, match='Nº do Empenho'):
        migrador.conferir(planilha([cenario.linha_base], colunas=colunas))


def test_aceita_linha_sem_numero_de_empenho(cenario):
    """Sem empenho a linha não é recusada: ela migra como doação."""
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'empenho_numero': ''}]))

    assert conferencia.valida
    assert conferencia.linhas[0].eh_doacao


def test_recusa_linha_sem_empenho_e_sem_fornecedor(cenario):
    """Sem empenho e sem fornecedor não sobra nada que diga de onde o bem veio."""
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'empenho_numero': '', 'fornecedor_documento': ''}]))

    assert not conferencia.valida
    assert [erro.coluna for erro in conferencia.erros] == ['fornecedor_documento']


def test_conferencia_separa_compras_de_doacoes(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base, cenario.linha_base | {'empenho_numero': ''}]))

    assert conferencia.total_bens == 2
    assert conferencia.total_compras == 1
    assert conferencia.total_doacoes == 1
    assert conferencia.total_empenhos == 1


def test_aponta_a_linha_do_campus_inexistente(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'campus_sigla': 'INEXISTENTE'}]))

    assert not conferencia.valida
    assert conferencia.erros[0].linha == 2
    assert 'INEXISTENTE' in conferencia.erros[0].mensagem


def test_aponta_elemento_de_despesa_nao_cadastrado(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'elemento_despesa_codigo': '999999'}]))

    assert [erro.coluna for erro in conferencia.erros] == ['elemento_despesa_codigo']


def test_aponta_documento_de_fornecedor_invalido(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'fornecedor_documento': '11.111.111/1111-11'}]))

    assert [erro.coluna for erro in conferencia.erros] == ['fornecedor_documento']


def test_aceita_fornecedor_pessoa_fisica_nao_cadastrada(cenario):
    """Pessoa física ausente da base não bloqueia: a migração a cadastra."""
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'fornecedor_documento': CPF}]))

    assert conferencia.valida, [str(erro) for erro in conferencia.erros]


def test_aponta_responsavel_inexistente(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'responsavel_matricula': '99999999'}]))

    assert [erro.coluna for erro in conferencia.erros] == ['responsavel_matricula']


def test_aponta_valor_invalido(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'valor': 'muito caro'}]))

    assert [erro.coluna for erro in conferencia.erros] == ['valor']


def test_aponta_estado_de_conservacao_invalido(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'estado_conservacao': 'quebrado'}]))

    assert [erro.coluna for erro in conferencia.erros] == ['estado_conservacao']


def test_ignora_linhas_em_branco(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base, {}, cenario.linha_base]))

    assert conferencia.total_bens == 2


def test_le_valor_com_e_sem_separador_de_milhar(cenario):
    conferencia = migrador.conferir(
        planilha([cenario.linha_base | {'valor': '1.234,56'}, cenario.linha_base | {'valor': '1234.56', 'descricao': 'Mesa'}])
    )

    assert [str(linha.valor) for linha in conferencia.linhas] == ['1234.56', '1234.56']


# ---------------------------------------------------------------------------
# Execução: a cadeia patrimonial
# ---------------------------------------------------------------------------


def test_cria_a_cadeia_completa_do_empenho_ao_inventario(cenario):
    migrar(cenario, [cenario.linha_base])

    empenho = Empenho.objects.get(numero='2024NE800123', uo=cenario.campus)
    item_empenho = EmpenhoPermanente.objects.get(empenho=empenho)
    item_entrada = EntradaPermanente.objects.get(empenho_permanente=item_empenho)
    inventario = Inventario.objects.get(entrada_permanente=item_entrada)

    assert item_entrada.entrada.tipo_entrada == EntradaTipo.COMPRA()
    assert item_empenho.qtd_adquirida == 1
    assert inventario.valor == item_entrada.valor
    assert inventario.cargas_contabeis.count() == 1
    assert inventario.carga_contabil.campus == cenario.campus


def test_gera_movimento_de_pendencia_para_todo_bem(cenario):
    resumo = migrar(cenario, [cenario.linha_base])

    inventario = migrados(resumo).get()
    assert MovimentoPatrim.objects.filter(inventario=inventario, tipo=MovimentoPatrimTipo.PENDENCIA()).exists()


def test_bem_sem_responsavel_fica_pendente_e_sem_requisicao(cenario):
    resumo = migrar(cenario, [cenario.linha_base])

    inventario = migrados(resumo).get()
    assert inventario.status == InventarioStatus.PENDENTE()
    assert inventario.responsavel_vinculo is None
    assert not RequisicaoItem.objects.filter(inventario=inventario).exists()
    assert not Requisicao.objects.exists()


def test_bem_com_responsavel_entra_ativo_com_a_carga_efetivada(cenario):
    resumo = migrar(cenario, [cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula}])

    inventario = migrados(resumo).get()
    assert inventario.status == InventarioStatus.ATIVO()
    assert inventario.responsavel_vinculo == cenario.servidor.get_vinculo()
    assert MovimentoPatrim.objects.filter(inventario=inventario, tipo=MovimentoPatrimTipo.TRANSFERENCIA()).exists()


def test_requisicao_de_carga_nasce_deferida(cenario):
    migrar(cenario, [cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula}])

    requisicao = Requisicao.objects.get()
    assert requisicao.status == Requisicao.STATUS_DEFERIDA
    # Primeira carga: o bem não saiu de ninguém.
    assert requisicao.vinculo_origem is None
    assert requisicao.vinculo_destino == cenario.servidor.get_vinculo()
    assert requisicao.itens.get().situacao == RequisicaoItem.APROVADO


def test_migracao_nao_dispara_email_para_os_responsaveis(cenario):
    mail.outbox = []

    migrar(cenario, [cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula}])

    assert mail.outbox == []


def test_guarda_o_tombo_antigo_na_observacao(cenario):
    resumo = migrar(cenario, [cenario.linha_base | {'observação': 'Tombo antigo: 004521'}])

    assert migrados(resumo).get().observacao == 'Tombo antigo: 004521'


def test_sala_da_planilha_vira_rotulo_e_o_campo_sala_fica_vazio(cenario):
    """
    A localização do sistema antigo entra como rótulo, não como sala.

    O campo Sala aponta para o cadastro de salas do SUAP; preenchê-lo com o texto do sistema
    antigo exigiria um casamento que não existe. Como rótulo o dado entra inteiro e o bem fica
    localizável pela busca, com o campo Sala livre para o cadastro correto.
    """
    resumo = migrar(cenario, [cenario.linha_base | {'sala_nome': 'Sala 12'}])

    inventario = migrados(resumo).get()
    assert inventario.sala is None
    assert [rotulo.nome for rotulo in inventario.rotulos.all()] == ['Sala 12']


def test_rotulo_novo_nasce_no_campus_da_linha(cenario):
    """O campus é o da linha, não o de quem migrou: `get_uo` não vale no worker nem em migração multicampi."""
    migrar(cenario, [cenario.linha_base | {'sala_nome': 'Sala 12'}])

    rotulo = InventarioRotulo.objects.get(nome='Sala 12')
    assert rotulo.unidade_organizacional == cenario.campus
    assert 'Migração de inventários por planilha' in rotulo.descricao


def test_mesma_sala_em_varias_linhas_cria_um_unico_rotulo(cenario):
    """Sem cache do que acabou de ser criado, cada linha criaria um rótulo repetido."""
    linhas = [cenario.linha_base | {'sala_nome': 'Sala 12', 'descricao': f'Bem {indice}'} for indice in range(5)]

    resumo = migrar(cenario, linhas)

    assert InventarioRotulo.objects.filter(nome='Sala 12', unidade_organizacional=cenario.campus).count() == 1
    assert all(inventario.rotulos.count() == 1 for inventario in migrados(resumo))


def test_rotulo_existente_e_reaproveitado_na_gravacao(cenario):
    ja_existe = InventarioRotulo.objects.create(nome='Sala  12', unidade_organizacional=cenario.campus)

    resumo = migrar(cenario, [cenario.linha_base | {'sala_nome': 'Sala 12'}])

    assert InventarioRotulo.objects.filter(unidade_organizacional=cenario.campus).count() == 1
    assert migrados(resumo).get().rotulos.get() == ja_existe


def test_tombo_novo_e_gerado_pelo_suap_em_sequencia(cenario):
    """O número do inventário é do SUAP; a planilha não o informa."""
    resumo = migrar(cenario, [cenario.linha_base, cenario.linha_base])

    numeros = sorted(migrados(resumo).values_list('numero', flat=True))
    assert numeros[1] == numeros[0] + 1


def test_agrupa_bens_identicos_em_um_unico_item_de_entrada(cenario):
    """Três cadeiras iguais do mesmo empenho viram um item de quantidade 3, não três itens."""
    resumo = migrar(cenario, [cenario.linha_base] * 3)

    item = EntradaPermanente.objects.get(descricao='Cadeira giratória')
    assert item.qtd == 3
    assert item.inventario_set.count() == 3
    assert resumo['itens'] == 1
    assert resumo['bens'] == 3


def test_separa_itens_quando_a_descricao_ou_o_valor_diferem(cenario):
    resumo = migrar(cenario, [cenario.linha_base, cenario.linha_base | {'descricao': 'Mesa'}, cenario.linha_base | {'valor': '500,00'}])

    assert itens_migrados(resumo).count() == 3
    assert len(resumo['entradas_criadas']) == 1


def test_reaproveita_o_empenho_que_ja_existe_no_campus(cenario):
    primeira = migrar(cenario, [cenario.linha_base])
    segunda = migrar(cenario, [cenario.linha_base | {'descricao': 'Armário', 'nota_fiscal_numero': '8888'}])

    assert Empenho.objects.filter(numero='2024NE800123', uo=cenario.campus).count() == 1
    assert primeira['entradas_criadas'] != segunda['entradas_criadas']


def test_cria_o_fornecedor_pessoa_juridica_quando_o_cnpj_e_novo(cenario):
    resumo = migrar(cenario, [cenario.linha_base])

    entrada = Entrada.objects.get(pk=resumo['entradas_criadas'][0])
    assert entrada.vinculo_fornecedor is not None
    assert PessoaJuridica.objects.filter(matricula='11222333000181').exists()


def test_cria_o_fornecedor_pessoa_fisica_como_pessoa_externa_quando_o_cpf_e_novo(cenario):
    """A pessoa física sozinha não tem vínculo; é a pessoa externa que dá ao empenho o fornecedor."""
    resumo = migrar(cenario, [cenario.linha_base | {'fornecedor_documento': CPF, 'fornecedor_nome': 'JOAO DA SILVA'}])

    pessoa = PessoaFisica.objects.get(cpf=CPF)
    externa = PessoaExterna.objects.get(cpf=CPF)
    assert pessoa.nome == 'JOAO DA SILVA'
    assert externa.pessoa_fisica_id == pessoa.pk
    entrada = Entrada.objects.get(pk=resumo['entradas_criadas'][0])
    assert entrada.vinculo_fornecedor == externa.get_vinculo()


def test_o_fornecedor_pessoa_fisica_criado_nao_ganha_acesso_ao_suap(cenario):
    """Migrar patrimônio não distribui login: pessoa externa nasce com vínculo inativo e sem conta."""
    migrar(cenario, [cenario.linha_base | {'fornecedor_documento': CPF, 'fornecedor_nome': 'JOAO DA SILVA'}])

    externa = PessoaExterna.objects.get(cpf=CPF)
    assert externa.get_vinculo().ativo is False
    assert externa.get_vinculo().user is None
    assert not User.objects.filter(username='11144477735').exists()


def test_reaproveita_o_fornecedor_pessoa_fisica_ja_cadastrado(cenario):
    """CPF já na base não vira pessoa nova, mesmo com nome diferente na planilha."""
    pessoa = PessoaFisica.objects.create(nome='JOAO DA SILVA SOBRINHO', cpf=CPF)

    migrar(cenario, [cenario.linha_base | {'fornecedor_documento': CPF, 'fornecedor_nome': 'JOAO DA SILVA'}])

    assert PessoaFisica.objects.filter(cpf=CPF).count() == 1
    assert PessoaFisica.objects.get(pk=pessoa.pk).nome == 'JOAO DA SILVA SOBRINHO'


def test_da_vinculo_ao_fornecedor_pessoa_fisica_que_ja_existia_sem_papel(cenario):
    """Pessoa na base sem papel nenhum não tem vínculo; sem criá-lo o empenho ficaria sem fornecedor."""
    pessoa = PessoaFisica.objects.create(nome='JOAO DA SILVA', cpf=CPF)

    resumo = migrar(cenario, [cenario.linha_base | {'fornecedor_documento': CPF, 'fornecedor_nome': 'JOAO DA SILVA'}])

    entrada = Entrada.objects.get(pk=resumo['entradas_criadas'][0])
    assert entrada.vinculo_fornecedor is not None
    assert entrada.vinculo_fornecedor.pessoa_id == pessoa.pk


@pytest.mark.usefixtures('sem_unicidade_pessoa')
def test_escolhe_sempre_a_mesma_pessoa_fisica_quando_o_cpf_esta_duplicado(cenario):
    """
    Base legada, antes da deduplicação (Release 1), ainda pode ter CPF repetido. Sem ordenação explícita vale o Meta.ordering de Pessoa ('nome'),
    que empata entre homônimos e muda de vencedor a cada renomeação: a conferência mostraria uma
    pessoa e a gravação penduraria o bem na outra. Vence a mais antiga.

    Daí o nome da duplicata vir antes no alfabeto — é o que faz o teste reprovar sem a ordenação.
    """
    antiga = PessoaFisica.objects.create(nome='JOAO DA SILVA', cpf=CPF)
    PessoaFisica.objects.create(nome='ANTONIO DA SILVA', cpf=CPF)

    conferencia = migrador.conferir(planilha([cenario.linha_base | {'fornecedor_documento': CPF, 'fornecedor_nome': 'JOAO DA SILVA'}]))
    resumo = migrar(cenario, [cenario.linha_base | {'fornecedor_documento': CPF, 'fornecedor_nome': 'JOAO DA SILVA'}])

    entrada = Entrada.objects.get(pk=resumo['entradas_criadas'][0])
    assert entrada.vinculo_fornecedor.pessoa_id == antiga.pk
    assert [cadastro.descricao for cadastro in conferencia.cadastros if cadastro.tipo == 'Fornecedor (PF)'] == [antiga.nome]


def test_anexar_pessoa_externa_nao_apaga_os_dados_de_quem_ja_estava_na_base(cenario):
    """
    PessoaExterna.save() empurra o próprio __dict__ para dentro da PessoaFisica.

    Sem espelhar antes, anexá-la a alguém que já existe zeraria RG, nome da mãe e nascimento.
    """
    pessoa = PessoaFisica.objects.create(nome='JOAO DA SILVA', cpf=CPF, rg='1234567', nome_mae='MARIA DA SILVA', nascimento_data='1980-05-04')

    migrar(cenario, [cenario.linha_base | {'fornecedor_documento': CPF, 'fornecedor_nome': 'OUTRO NOME'}])

    pessoa.refresh_from_db()
    assert pessoa.nome == 'JOAO DA SILVA'
    assert pessoa.rg == '1234567'
    assert pessoa.nome_mae == 'MARIA DA SILVA'
    assert str(pessoa.nascimento_data) == '1980-05-04'


def test_reaproveita_o_vinculo_do_fornecedor_que_ja_e_servidor(cenario):
    """Fornecedor que já tem papel entra com o vínculo que tem, sem virar pessoa externa também."""
    servidor = cenario.servidor
    documento = servidor.pessoa_fisica.cpf

    resumo = migrar(cenario, [cenario.linha_base | {'fornecedor_documento': documento, 'fornecedor_nome': servidor.pessoa_fisica.nome}])

    entrada = Entrada.objects.get(pk=resumo['entradas_criadas'][0])
    assert entrada.vinculo_fornecedor == servidor.get_vinculo()
    assert not PessoaExterna.objects.filter(pessoa_fisica=servidor.pessoa_fisica).exists()


def test_uma_requisicao_por_responsavel(cenario):
    resumo = migrar(
        cenario,
        [
            cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula},
            cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula},
            cenario.linha_base,
        ],
    )

    requisicao = Requisicao.objects.get()
    assert requisicao.itens.count() == 2
    assert migrados(resumo).filter(status=InventarioStatus.PENDENTE()).count() == 1


def test_resumo_reporta_o_que_foi_criado(cenario):
    resumo = migrar(cenario, [cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula}, cenario.linha_base])

    assert resumo['bens'] == 2
    assert resumo['com_responsavel'] == 1
    assert resumo['pendentes'] == 1
    assert resumo['requisicoes'] == 1
    assert len(resumo['entradas_criadas']) == 1


# ---------------------------------------------------------------------------
# Doação: a linha sem número de empenho
# ---------------------------------------------------------------------------


def test_linha_sem_empenho_entra_como_doacao_sem_item_empenhado(cenario):
    resumo = migrar(cenario, [cenario.linha_base | {'empenho_numero': ''}])

    item_entrada = itens_migrados(resumo).get()
    assert item_entrada.entrada.tipo_entrada == EntradaTipo.DOACAO()
    assert item_entrada.empenho_permanente is None
    assert not Empenho.objects.filter(uo=cenario.campus).exists()
    assert not EmpenhoPermanente.objects.exists()


def test_doacao_preserva_o_fornecedor_da_planilha(cenario):
    """O doador é o fornecedor informado: documento e nome entram como vieram."""
    resumo = migrar(cenario, [cenario.linha_base | {'empenho_numero': ''}])

    entrada = itens_migrados(resumo).get().entrada
    fornecedor = PessoaJuridica.objects.get(matricula='11222333000181')
    assert entrada.vinculo_fornecedor == fornecedor.get_vinculo()
    assert fornecedor.nome == 'MOVEIS BRASIL LTDA'


def test_doacao_tomba_o_bem_com_carga_contabil_no_campus_da_entrada(cenario):
    """Sem empenho a UO da carga contábil sai da entrada — é o que `Inventario.save()` faz."""
    resumo = migrar(cenario, [cenario.linha_base | {'empenho_numero': ''}])

    inventario = migrados(resumo).get()
    assert inventario.status == InventarioStatus.PENDENTE()
    assert inventario.carga_contabil.campus == cenario.campus
    assert MovimentoPatrim.objects.filter(inventario=inventario, tipo=MovimentoPatrimTipo.PENDENCIA()).exists()


def test_bem_doado_com_responsavel_recebe_carga_como_qualquer_outro(cenario):
    resumo = migrar(cenario, [cenario.linha_base | {'empenho_numero': '', 'responsavel_matricula': cenario.servidor.matricula}])

    inventario = migrados(resumo).get()
    assert inventario.status == InventarioStatus.ATIVO()
    assert inventario.responsavel_vinculo == cenario.servidor.get_vinculo()


def test_compra_e_doacao_na_mesma_planilha_geram_entradas_separadas(cenario):
    resumo = migrar(cenario, [cenario.linha_base, cenario.linha_base | {'empenho_numero': ''}])

    entradas = Entrada.objects.filter(pk__in=resumo['entradas_criadas'])
    assert {entrada.tipo_entrada for entrada in entradas} == {EntradaTipo.COMPRA(), EntradaTipo.DOACAO()}
    assert resumo['doacoes'] == 1
    assert resumo['compras'] == 1


def test_doacoes_de_doadores_diferentes_nao_caem_na_mesma_entrada(cenario):
    """Sem empenho e sem nota fiscal, é o fornecedor que separa uma doação da outra."""
    doacao = cenario.linha_base | {'empenho_numero': '', 'nota_fiscal_numero': '', 'nota_fiscal_data': ''}

    resumo = migrar(cenario, [doacao, doacao | {'fornecedor_documento': CPF, 'fornecedor_nome': 'JOSE DOADOR'}])

    entradas = Entrada.objects.filter(pk__in=resumo['entradas_criadas'])
    assert entradas.count() == 2
    assert len({entrada.vinculo_fornecedor_id for entrada in entradas}) == 2


def test_doacoes_do_mesmo_doador_no_mesmo_dia_ficam_na_mesma_entrada(cenario):
    doacao = cenario.linha_base | {'empenho_numero': '', 'nota_fiscal_numero': '', 'nota_fiscal_data': ''}

    resumo = migrar(cenario, [doacao, doacao | {'descricao': 'Armário doado'}])

    assert len(resumo['entradas_criadas']) == 1
    assert itens_migrados(resumo).count() == 2


# ---------------------------------------------------------------------------
# Planilha modelo
# ---------------------------------------------------------------------------


def test_planilha_modelo_e_lida_pelo_proprio_migrador():
    """O modelo oferecido ao usuário precisa passar pela conferência do migrador."""
    arquivo = io.BytesIO(migrador.gerar_planilha_modelo())
    arquivo.name = 'modelo.xlsx'

    planilha_lida = migrador.ler_planilha(arquivo)

    assert list(planilha_lida.columns) == [coluna.nome for coluna in migrador.COLUNAS]
    assert len(planilha_lida) == len(migrador.EXEMPLOS_MODELO)


# ---------------------------------------------------------------------------
# Assistente (tela única)
# ---------------------------------------------------------------------------


def habilitar_migrador(cenario):
    """
    Loga o servidor no perfil que dá acesso ao migrador.

    Usa o grupo de verdade, criado pelo `permissions.yaml`, e não a permissão solta: assim os
    testes de tela também provam que o perfil está corretamente configurado.
    """
    usuario = cenario.servidor.get_user()
    usuario.groups.add(Group.objects.get(name=GRUPO_MIGRADOR))
    cenario.client.logout()
    cenario.client.force_login(User.objects.get(pk=usuario.pk))


def postar(cenario, linhas, ajax=True, **extra):
    """Posta a planilha na tela de migração. Sem `confirmar`, é só conferência."""
    dados = {
        'arquivo': SimpleUploadedFile('migracao.csv', planilha(linhas).getvalue(), content_type='text/csv'),
        'processo': cenario.processo.pk,
    }
    dados.update(extra)
    cabecalhos = {'headers': {'x-requested-with': 'XMLHttpRequest'}} if ajax else {}
    return cenario.client.post('/patrimonio/migracao/', dados, **cabecalhos)


def enviar(cenario, linhas, **extra):
    """Primeiro passo: confere a planilha, que é o que a tela faz sem recarregar a página."""
    return postar(cenario, linhas, **extra)


def confirmar(cenario, linhas, **extra):
    """
    Segundo passo: reenvia a mesma planilha, agora com o `confirmar`.

    É a submissão que o botão de importar dispara — a tela não guarda nada entre um passo e
    outro, então o arquivo tem que viajar de novo.
    """
    enviar(cenario, linhas)
    return postar(cenario, linhas, ajax=False, confirmar='1', **extra)


def arquivos_no_storage_temporario():
    """Tudo o que existe no storage temporário, onde a migração não pode deixar rastro."""
    storage = get_temp_storage()
    try:
        pastas, arquivos = storage.listdir('')
    except FileNotFoundError, NotImplementedError:
        return set()
    return set(arquivos) | set(pastas)


def test_tela_sem_permissao_e_negada(cenario):
    cenario.client.logout()
    cenario.client.force_login(cenario.servidor.get_user())

    assert cenario.client.get('/patrimonio/migracao/').status_code in (302, 403)


def test_tela_mostra_as_colunas_esperadas(cenario):
    habilitar_migrador(cenario)

    resposta = cenario.client.get('/patrimonio/migracao/')

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert 'responsavel_matricula' in conteudo
    assert 'pendente' in conteudo


def test_planilha_modelo_e_baixavel(cenario):
    habilitar_migrador(cenario)

    resposta = cenario.client.get('/patrimonio/migracao/modelo/')

    assert resposta.status_code == 200
    assert 'modelo-migracao-inventarios.xlsx' in resposta['Content-Disposition']


def test_envio_lista_os_erros_da_planilha(cenario):
    habilitar_migrador(cenario)

    resposta = enviar(cenario, [cenario.linha_base | {'campus_sigla': 'INEXISTENTE'}])

    assert resposta.status_code == 200
    assert 'INEXISTENTE' in resposta.content.decode()


def test_envio_confere_sem_gravar_nada(cenario):
    """O primeiro envio é só conferência: nenhuma escrita no banco."""
    habilitar_migrador(cenario)

    resposta = enviar(cenario, [cenario.linha_base])

    conteudo = resposta.content.decode()
    assert 'Nenhum erro encontrado' in conteudo
    assert 'Confirmar e importar' in conteudo
    assert not Empenho.objects.filter(numero='2024NE800123').exists()


def test_confirmacao_importa_a_cadeia_inteira(cenario):
    habilitar_migrador(cenario)
    linhas = [
        cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula, 'observação': 'Tombo antigo: 004521'},
        cenario.linha_base,
    ]

    resposta = confirmar(cenario, linhas)

    assert resposta.status_code == 302
    assert Empenho.objects.filter(numero='2024NE800123', uo=cenario.campus).exists()
    entrada = Entrada.objects.filter(numero_nota_fiscal='4567').get()
    inventarios = Inventario.objects.filter(entrada_permanente__entrada=entrada)
    assert inventarios.count() == 2
    assert inventarios.filter(status=InventarioStatus.ATIVO(), observacao='Tombo antigo: 004521').count() == 1
    assert inventarios.filter(status=InventarioStatus.PENDENTE(), responsavel_vinculo=None).count() == 1
    assert Requisicao.objects.get().status == Requisicao.STATUS_DEFERIDA


def test_conferencia_sem_erro_libera_o_botao_de_importar(cenario):
    """O botão de importar é o resultado da conferência: ele só existe quando a planilha passou."""
    habilitar_migrador(cenario)

    conteudo = enviar(cenario, [cenario.linha_base]).content.decode()

    assert 'name="confirmar"' in conteudo


def test_envio_sem_processo_e_recusado(cenario):
    """O processo é obrigatório: é ele que fica registrado como a autorização da migração."""
    habilitar_migrador(cenario)
    arquivo = SimpleUploadedFile('migracao.csv', planilha([cenario.linha_base]).getvalue(), content_type='text/csv')

    resposta = cenario.client.post('/patrimonio/migracao/', {'arquivo': arquivo}, headers={'x-requested-with': 'XMLHttpRequest'})

    conteudo = resposta.content.decode()
    assert 'obrigatório' in conteudo
    assert 'name="confirmar"' not in conteudo


def test_processo_informado_fica_nos_empenhos_e_entradas(cenario):
    habilitar_migrador(cenario)

    confirmar(cenario, [cenario.linha_base])

    assert Empenho.objects.get(numero='2024NE800123', uo=cenario.campus).processo == cenario.processo
    assert Entrada.objects.get(numero_nota_fiscal='4567').processo == cenario.processo


def test_conferencia_com_erro_nao_libera_o_botao_de_importar(cenario):
    """Com erro não há o que importar: a tela mostra o problema e espera outra planilha."""
    habilitar_migrador(cenario)

    conteudo = enviar(cenario, [cenario.linha_base | {'campus_sigla': 'INEXISTENTE'}]).content.decode()

    assert 'Erros por coluna' in conteudo
    assert 'name="confirmar"' not in conteudo


def test_confirmacao_de_planilha_com_erro_nao_importa(cenario):
    """A tela não é a dona da garantia: confirmar uma planilha com erro tem que ser barrado aqui."""
    habilitar_migrador(cenario)

    resposta = postar(cenario, [cenario.linha_base | {'campus_sigla': 'INEXISTENTE'}], ajax=False, confirmar='1')

    assert resposta.status_code == 302
    assert not Empenho.objects.filter(numero='2024NE800123').exists()


def test_confirmacao_sem_planilha_nao_importa(cenario):
    """Confirmar é o reenvio do arquivo: sem arquivo não há o que importar."""
    habilitar_migrador(cenario)

    resposta = cenario.client.post('/patrimonio/migracao/', {'confirmar': '1'})

    assert resposta.status_code == 200
    assert not Empenho.objects.filter(numero='2024NE800123').exists()


def test_migracao_nao_guarda_a_planilha_em_lugar_nenhum(cenario):
    """
    Nem entre os passos: a planilha fica no navegador e volta com a confirmação.

    Compara o storage temporário antes e depois de percorrer os dois passos — o teste não depende
    de ele estar vazio, só de a migração não acrescentar nada a ele. A sessão é conferida junto
    porque guardar o arquivo lá seria a outra forma óbvia de dispensar o reenvio.
    """
    habilitar_migrador(cenario)
    antes = arquivos_no_storage_temporario()

    enviar(cenario, [cenario.linha_base])
    durante = arquivos_no_storage_temporario()
    confirmar(cenario, [cenario.linha_base])

    assert durante == antes
    assert arquivos_no_storage_temporario() == antes
    # keys(): SessionBase não tem __iter__, e iterar a sessão direto cai no protocolo de sequência antigo.
    chaves_da_sessao = list(cenario.client.session.keys())
    assert not [chave for chave in chaves_da_sessao if 'migracao' in chave or 'patrimonio' in chave]


def test_conteudo_da_planilha_sobrevive_ao_transporte_ate_a_task(cenario):
    """Os bytes vão e voltam pelo serializador do `@task`; a leitura tem que continuar idêntica."""
    from djtools.utils import serialization

    original = planilha([cenario.linha_base]).getvalue()

    recuperado = serialization.deserialize(serialization.serialize(original))

    assert recuperado == original
    assert migrador.conferir(migrador.como_arquivo(recuperado, 'migracao.csv')).valida


def test_migracao_nao_depende_da_thread_local_para_saber_quem_migra(cenario, monkeypatch):
    """
    A task roda fora da thread da requisição, onde `tl.get_user()` está vazio.

    Simula isso zerando o usuário do thread-local assim que a task começa — exatamente o que a
    thread do worker enxerga, já que ela só recebe o `request`. O operador tem que continuar
    saindo da própria Task, senão a carga estoura no meio da gravação.
    """
    from djtools.middleware import threadlocals as tl

    habilitar_migrador(cenario)
    conferir_original = migrador.conferir

    def conferir_como_no_worker(arquivo):
        tl.context.user = None
        return conferir_original(arquivo)

    monkeypatch.setattr(migrador, 'conferir', conferir_como_no_worker)

    resposta = confirmar(cenario, [cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula}])

    assert resposta.status_code == 302
    assert Requisicao.objects.get().requisitante == cenario.servidor.get_vinculo()


def test_execucao_sem_usuario_e_recusada(cenario):
    """Sem operador não há autor para os movimentos: erro claro em vez de estouro na gravação."""
    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    with pytest.raises(ValidationError, match='usuário'):
        migrador.executar(conferencia, None)


def test_importa_sem_teto_de_linhas(cenario):
    """Sem limite: o que sustenta acervos grandes é a execução em segundo plano."""
    habilitar_migrador(cenario)
    linhas = [cenario.linha_base | {'descricao': f'Bem {indice}'} for indice in range(250)]

    confirmar(cenario, linhas)

    assert Inventario.objects.filter(entrada_permanente__entrada__numero_nota_fiscal='4567').count() == 250


# ---------------------------------------------------------------------------
# Levantamento dos cadastros prévios
# ---------------------------------------------------------------------------


def cadastros_do_tipo(conferencia, tipo):
    return [cadastro for cadastro in conferencia.cadastros if cadastro.tipo.startswith(tipo)]


def test_levanta_todos_os_cadastros_referenciados(cenario):
    conferencia = migrador.conferir(
        planilha([cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula, 'sala_nome': cenario.sala_nome}])
    )

    tipos = {cadastro.tipo for cadastro in conferencia.cadastros}
    assert {'Campus', 'Elemento de Despesa', 'Empenho', 'Fornecedor (PJ)', 'Responsável', 'Rótulo'} <= tipos


def test_marca_empenho_inexistente_como_a_criar(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    empenho = cadastros_do_tipo(conferencia, 'Empenho')[0]
    assert empenho.situacao == migrador.SERA_CRIADO
    assert empenho.identificacao == '2024NE800123'


def test_reconhece_empenho_que_ja_existe(cenario):
    """A segunda planilha do mesmo empenho precisa avisar que vai acrescentar itens ao existente."""
    migrar(cenario, [cenario.linha_base])

    conferencia = migrador.conferir(planilha([cenario.linha_base | {'descricao': 'Armário'}]))

    empenho = cadastros_do_tipo(conferencia, 'Empenho')[0]
    assert empenho.situacao == migrador.EXISTENTE
    assert '1 item' in empenho.descricao
    assert 'acrescentar itens' in empenho.detalhe


def test_bloqueia_empenho_que_colide_com_um_de_consumo(cenario):
    """`Empenho` é único por campus + número: colidir com um de consumo corromperia o empenho."""
    Empenho.objects.create(
        uo=cenario.campus,
        numero='2024NE800123',
        tipo_material=apps.get_model('almoxarifado', 'MaterialTipo').CONSUMO(),
    )

    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    assert not conferencia.valida
    assert any('corromperia' in erro.mensagem for erro in conferencia.erros)


def test_avisa_quando_o_empenho_existente_tem_outro_fornecedor(cenario):
    """Divergência de fornecedor não bloqueia, mas precisa aparecer."""
    outro = PessoaJuridica.objects.create(cnpj='33.000.167/0001-01', nome='OUTRA EMPRESA', nome_registro='OUTRA EMPRESA')
    Empenho.objects.create(
        uo=cenario.campus,
        numero='2024NE800123',
        tipo_material=apps.get_model('almoxarifado', 'MaterialTipo').PERMANENTE(),
        vinculo_fornecedor=outro.get_vinculo(),
    )

    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    empenho = cadastros_do_tipo(conferencia, 'Empenho')[0]
    assert conferencia.valida
    assert empenho.situacao == migrador.ATENCAO
    assert 'outro fornecedor' in empenho.detalhe


def test_avisa_elemento_de_despesa_sem_plano_de_contas(cenario):
    """Sem plano de contas o bem some dos relatórios contábeis e quebra a baixa."""
    cenario.categoria.plano_contas = None
    cenario.categoria.save()

    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    elemento = cadastros_do_tipo(conferencia, 'Elemento de Despesa')[0]
    assert elemento.situacao == migrador.ATENCAO
    assert 'sem plano de contas' in elemento.detalhe


def test_avisa_elemento_de_despesa_omitido(cenario):
    cenario.categoria.omitir = True
    cenario.categoria.save()

    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    assert 'omitido' in cadastros_do_tipo(conferencia, 'Elemento de Despesa')[0].detalhe


def test_marca_fornecedor_novo_como_a_criar(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    fornecedor = cadastros_do_tipo(conferencia, 'Fornecedor')[0]
    assert fornecedor.situacao == migrador.SERA_CRIADO
    assert '11222333000181' in fornecedor.identificacao


def test_avisa_que_o_fornecedor_pessoa_fisica_novo_vira_pessoa_externa(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'fornecedor_documento': CPF}]))

    fornecedor = cadastros_do_tipo(conferencia, 'Fornecedor')[0]
    assert fornecedor.situacao == migrador.SERA_CRIADO
    assert 'pessoa externa' in fornecedor.detalhe


def test_reconhece_fornecedor_ja_cadastrado(cenario):
    PessoaJuridica.objects.create(cnpj=CNPJ, nome='MOVEIS BRASIL LTDA', nome_registro='MOVEIS BRASIL LTDA')

    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    assert cadastros_do_tipo(conferencia, 'Fornecedor')[0].situacao == migrador.EXISTENTE


def test_avisa_quando_o_nome_do_fornecedor_diverge_do_cadastro(cenario):
    PessoaJuridica.objects.create(cnpj=CNPJ, nome='RAZAO SOCIAL DIFERENTE', nome_registro='RAZAO SOCIAL DIFERENTE')

    conferencia = migrador.conferir(planilha([cenario.linha_base]))

    fornecedor = cadastros_do_tipo(conferencia, 'Fornecedor')[0]
    assert fornecedor.situacao == migrador.ATENCAO
    assert 'o cadastro do SUAP prevalece' in fornecedor.detalhe


def test_avisa_responsavel_inativo(cenario):
    cenario.servidor.ativo = False
    cenario.servidor.save()

    conferencia = migrador.conferir(planilha([cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula}]))

    responsavel = cadastros_do_tipo(conferencia, 'Responsável')[0]
    assert responsavel.situacao == migrador.ATENCAO
    assert 'inativo' in responsavel.detalhe


def test_sala_da_planilha_vira_rotulo_novo(cenario):
    """O nome do sistema antigo não precisa existir como sala no SUAP: vira rótulo."""
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'sala_nome': 'Sala que nunca foi cadastrada'}]))

    assert conferencia.valida
    rotulo = cadastros_do_tipo(conferencia, 'Rótulo')[0]
    assert rotulo.identificacao == 'Sala que nunca foi cadastrada'
    assert rotulo.situacao == migrador.SERA_CRIADO


def test_reaproveita_o_rotulo_que_ja_existe_no_campus(cenario):
    InventarioRotulo.objects.create(nome='Sala do Migrador', unidade_organizacional=cenario.campus)

    conferencia = migrador.conferir(planilha([cenario.linha_base | {'sala_nome': 'Sala do Migrador'}]))

    assert cadastros_do_tipo(conferencia, 'Rótulo')[0].situacao == migrador.EXISTENTE


@pytest.mark.parametrize(
    ('cadastrado', 'planilhado'),
    [
        (' GESEG - SALA DE GINASTICA', 'GESEG - SALA DE GINASTICA'),
        ('Sala  de  Aula 12', 'Sala de Aula 12'),
        ('LABORATÓRIO DE FÍSICA', 'LABORATORIO DE FISICA'),
        ('LABORATORIO DE FISICA', 'Laboratório de Física'),
    ],
)
def test_acha_rotulo_cadastrado_com_nome_sujo(cenario, cadastrado, planilhado):
    """Nome de rótulo é texto livre: espaço sobrando e acento inconsistente criariam um duplicado."""
    InventarioRotulo.objects.create(nome=cadastrado, unidade_organizacional=cenario.campus)

    conferencia = migrador.conferir(planilha([cenario.linha_base | {'sala_nome': planilhado}]))

    assert cadastros_do_tipo(conferencia, 'Rótulo')[0].situacao == migrador.EXISTENTE


def test_rotulo_e_por_campus(cenario):
    """Rótulo de outro campus não serve: o cadastro é por unidade organizacional."""
    InventarioRotulo.objects.create(nome='Sala do Migrador', unidade_organizacional=cenario.outro_campus)

    conferencia = migrador.conferir(planilha([cenario.linha_base | {'sala_nome': 'Sala do Migrador'}]))

    assert cadastros_do_tipo(conferencia, 'Rótulo')[0].situacao == migrador.SERA_CRIADO


def test_bem_sem_sala_na_planilha_nao_ganha_rotulo(cenario):
    """A coluna é opcional: sem ela o bem entra sem rótulo nenhum."""
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'sala_nome': ''}]))

    assert conferencia.valida
    assert conferencia.linhas[0].rotulo_nome == ''
    assert not cadastros_do_tipo(conferencia, 'Rótulo')


def test_nota_fiscal_que_ja_deu_entrada_passa_com_aviso(cenario):
    """
    Nota repetida não barra a migração, mas é o sinal mais confiável de reimportação acidental:
    vira aviso, e o cadastro traz o link para a entrada existente, que o operador confere antes
    de confirmar.
    """
    migrar(cenario, [cenario.linha_base])

    conferencia = migrador.conferir(planilha([cenario.linha_base | {'descricao': 'Armário'}]))

    assert conferencia.valida, [str(erro) for erro in conferencia.erros]
    assert [aviso.coluna for aviso in conferencia.avisos] == ['nota_fiscal_numero']
    assert 'bens serão duplicados' in conferencia.avisos[0].mensagem

    nota = cadastros_do_tipo(conferencia, 'Nota Fiscal')
    assert len(nota) == 1
    assert nota[0].situacao == migrador.ATENCAO
    assert nota[0].url


def test_nota_fiscal_nova_no_mesmo_empenho_nao_avisa(cenario):
    """O aviso é da nota, não do empenho: o lote seguinte da mesma compra entra sem ressalva."""
    migrar(cenario, [cenario.linha_base])

    conferencia = migrador.conferir(planilha([cenario.linha_base | {'nota_fiscal_numero': '9999', 'descricao': 'Armário'}]))

    assert conferencia.valida, [str(erro) for erro in conferencia.erros]
    assert not conferencia.avisos
    assert not cadastros_do_tipo(conferencia, 'Nota Fiscal')


def test_doacao_reimportada_nao_avisa(cenario):
    """
    Limite conhecido: doação não tem nota fiscal, então o aviso de reimportação não a alcança.

    O teste existe para o limite ficar explícito — se um dia a migração ganhar registro próprio,
    é este comportamento que muda.
    """
    doacao = cenario.linha_base | {'empenho_numero': '', 'nota_fiscal_numero': '', 'nota_fiscal_data': ''}
    migrar(cenario, [doacao])

    conferencia = migrador.conferir(planilha([doacao]))

    assert conferencia.valida
    assert not cadastros_do_tipo(conferencia, 'Nota Fiscal')


def test_conta_quantas_linhas_usam_cada_cadastro(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base] * 3))

    assert cadastros_do_tipo(conferencia, 'Elemento de Despesa')[0].linhas == 3


def test_conferencia_exibe_os_cadastros_na_tela(cenario):
    habilitar_migrador(cenario)

    resposta = enviar(cenario, [cenario.linha_base])

    conteudo = resposta.content.decode()
    assert 'Cadastros verificados' in conteudo
    assert 'Serão criados' in conteudo
    assert 'Já cadastrados' in conteudo


def test_cadastros_sao_contados_por_tipo(cenario):
    """A lista item a item cresce com a planilha; a contagem por tipo, não."""
    linhas = [cenario.linha_base | {'descricao': f'Bem {indice}'} for indice in range(30)]

    conferencia = migrador.conferir(planilha(linhas))

    por_tipo = {resumo.tipo: resumo for resumo in conferencia.cadastros_por_tipo}
    assert por_tipo['Campus'].total == 1
    assert por_tipo['Campus'].existentes == 1
    assert por_tipo['Fornecedor (PJ)'].a_criar == 1
    assert sum(resumo.total for resumo in conferencia.cadastros_por_tipo) == len(conferencia.cadastros)


def test_erros_sao_resumidos_por_coluna(cenario):
    """Trinta linhas com o mesmo defeito viram uma linha de tela, não trinta."""
    linhas = [cenario.linha_base | {'campus_sigla': 'INEXISTENTE'} for _ in range(30)]

    conferencia = migrador.conferir(planilha(linhas))

    assert len(conferencia.erros) == 30
    assert [(resumo.coluna, resumo.total) for resumo in conferencia.erros_por_coluna] == [('campus_sigla', 30)]
    assert conferencia.erros_por_coluna[0].exemplos == ['Linha 2: ' + conferencia.erros[0].mensagem]


def test_resumo_de_erros_traz_problemas_diferentes_como_exemplo(cenario):
    """O exemplo só ensina algo se for outro problema — repetir a mesma mensagem é ruído."""
    linhas = [
        cenario.linha_base | {'campus_sigla': 'INEXISTENTE'},
        cenario.linha_base | {'campus_sigla': 'INEXISTENTE'},
        cenario.linha_base | {'campus_sigla': 'OUTRO_QUE_NAO_EXISTE'},
    ]

    conferencia = migrador.conferir(planilha(linhas))

    exemplos = conferencia.erros_por_coluna[0].exemplos
    assert len(exemplos) == 2
    assert 'Linha 2' in exemplos[0]
    assert 'Linha 4' in exemplos[1]


def test_tela_de_conferencia_nao_cresce_com_a_planilha(cenario):
    """O tamanho da conferência é o da tela, não o do acervo: nenhum bem é listado, só contado."""
    habilitar_migrador(cenario)
    linhas = [cenario.linha_base | {'descricao': f'Bem {indice}'} for indice in range(200)]

    conteudo = enviar(cenario, linhas).content.decode()

    assert 'Bem 0' not in conteudo
    assert 'Bem 199' not in conteudo
    assert '<dd>200</dd>' in conteudo


# ---------------------------------------------------------------------------
# Marca de origem, no lugar de um registro de migração
# ---------------------------------------------------------------------------


def test_empenho_criado_guarda_a_marca_de_origem(cenario):
    """Sem modelo de migração, é a observação do empenho que registra de onde vieram os bens."""
    migrar(cenario, [cenario.linha_base])

    empenho = Empenho.objects.get(numero='2024NE800123', uo=cenario.campus)
    assert empenho.observacao == migrador.marcador_de_origem()
    assert 'Migração de inventários por planilha' in empenho.observacao


def test_requisicao_de_carga_guarda_a_marca_de_origem(cenario):
    migrar(cenario, [cenario.linha_base | {'responsavel_matricula': cenario.servidor.matricula}])

    assert Requisicao.objects.get().descricao == migrador.marcador_de_origem()


def test_marca_de_origem_nao_depende_de_registro_algum(cenario):
    """Auto-contida: traz a data, já que não há id de migração a citar."""
    from datetime import date

    assert f'{date.today():%d/%m/%Y}' in migrador.marcador_de_origem()


# ---------------------------------------------------------------------------
# Fornecedor divergente dentro do mesmo empenho
# ---------------------------------------------------------------------------


def test_recusa_empenho_com_dois_fornecedores_na_planilha(cenario):
    """
    Um empenho tem um fornecedor só; sem esta guarda a migração gravaria o da primeira linha.

    Nem `chave_entrada` nem `chave_empenho` levam o fornecedor na compra, então as duas linhas
    cairiam na mesma Entrada e no mesmo Empenho, e a divergência sumiria.
    """
    conferencia = migrador.conferir(
        planilha(
            [
                cenario.linha_base,
                cenario.linha_base | {'fornecedor_documento': OUTRO_CNPJ, 'fornecedor_nome': 'OUTRA EMPRESA LTDA'},
            ]
        )
    )

    assert not conferencia.valida
    assert [erro.coluna for erro in conferencia.erros] == ['fornecedor_documento']
    assert 'fornecedores diferentes' in conferencia.erros[0].mensagem


def test_aponta_a_linha_que_destoa_e_nao_a_primeira_do_grupo(cenario):
    """A ocorrência é ancorada na linha que o usuário precisa abrir para corrigir."""
    conferencia = migrador.conferir(
        planilha(
            [
                cenario.linha_base,
                cenario.linha_base,
                cenario.linha_base | {'fornecedor_documento': OUTRO_CNPJ},
            ]
        )
    )

    # +2 porque a planilha tem cabeçalho e o usuário conta a partir de 1: a terceira linha é a 4.
    assert [erro.linha for erro in conferencia.erros] == [4]


def test_aceita_fornecedores_diferentes_em_empenhos_diferentes(cenario):
    """A guarda é por empenho: dois empenhos com fornecedores distintos é o caso normal."""
    conferencia = migrador.conferir(
        planilha(
            [
                cenario.linha_base,
                cenario.linha_base | {'empenho_numero': '2024NE800999', 'fornecedor_documento': OUTRO_CNPJ},
            ]
        )
    )

    assert conferencia.valida, [str(erro) for erro in conferencia.erros]


def test_doacao_com_doadores_diferentes_continua_valida(cenario):
    """Doação não tem empenho, e `chave_entrada` já separa as entradas pelo documento do doador."""
    doacao = cenario.linha_base | {'empenho_numero': '', 'nota_fiscal_numero': '', 'nota_fiscal_data': ''}
    conferencia = migrador.conferir(planilha([doacao, doacao | {'fornecedor_documento': OUTRO_CNPJ}]))

    assert conferencia.valida, [str(erro) for erro in conferencia.erros]


# ---------------------------------------------------------------------------
# Limites de tamanho dos campos de destino
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('coluna', 'app', 'modelo', 'campo'),
    [
        ('empenho_numero', 'almoxarifado', 'Empenho', 'numero'),
        ('nota_fiscal_numero', 'almoxarifado', 'Entrada', 'numero_nota_fiscal'),
        ('fornecedor_nome', 'rh', 'PessoaExterna', 'nome'),
        ('numero_serie', 'patrimonio', 'Inventario', 'numero_serie'),
        ('sala_nome', 'patrimonio', 'InventarioRotulo', 'nome'),
    ],
)
def test_limite_declarado_bate_com_o_campo_de_destino(coluna, app, modelo, campo):
    """Se o campo do SUAP mudar de tamanho, é este teste que avisa que a planilha ficou para trás."""
    assert migrador.COLUNAS_POR_NOME[coluna].limite == apps.get_model(app, modelo)._meta.get_field(campo).max_length


@pytest.mark.parametrize(
    ('coluna', 'tamanho'),
    [
        ('empenho_numero', 14),
        ('nota_fiscal_numero', 25),
        ('fornecedor_nome', 200),
        ('numero_serie', 50),
        ('sala_nome', 100),
    ],
)
def test_recusa_celula_maior_que_o_campo(cenario, coluna, tamanho):
    """
    Antes isto passava na conferência e estourava DataError no meio da task, sem dizer qual linha.

    Recusar em vez de truncar é deliberado: número de empenho ou de nota cortado no meio vira um
    registro errado que ninguém percebe.
    """
    conferencia = migrador.conferir(planilha([cenario.linha_base | {coluna: 'X' * (tamanho + 1)}]))

    assert not conferencia.valida
    assert [erro.coluna for erro in conferencia.erros] == [coluna]
    assert f'o limite é {tamanho}' in conferencia.erros[0].mensagem


@pytest.mark.parametrize(
    ('coluna', 'tamanho'),
    [
        ('empenho_numero', 14),
        ('nota_fiscal_numero', 25),
        ('fornecedor_nome', 200),
        ('numero_serie', 50),
        ('sala_nome', 100),
    ],
)
def test_aceita_celula_exatamente_no_limite(cenario, coluna, tamanho):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {coluna: 'X' * tamanho}]))

    assert conferencia.valida, [str(erro) for erro in conferencia.erros]


def test_recusa_valor_que_estoura_o_campo(cenario):
    """`EntradaPermanente.valor` é numeric(15, 6): o décimo dígito inteiro estoura no banco."""
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'valor': '1000000000,00'}]))

    assert not conferencia.valida
    assert [erro.coluna for erro in conferencia.erros] == ['valor']
    assert 'grande demais' in conferencia.erros[0].mensagem


def test_aceita_valor_no_maior_valor_que_cabe(cenario):
    conferencia = migrador.conferir(planilha([cenario.linha_base | {'valor': '999999999,99'}]))

    assert conferencia.valida, [str(erro) for erro in conferencia.erros]


def test_modelo_publica_o_limite_na_aba_de_instrucoes(cenario):
    """O usuário precisa saber do limite antes de montar a planilha, não depois de conferir."""
    assert migrador.COLUNAS_POR_NOME['empenho_numero'].instrucao.endswith('Até 14 caracteres.')
    assert 'caracteres' not in migrador.COLUNAS_POR_NOME['descricao'].instrucao
