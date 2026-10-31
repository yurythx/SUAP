from contextlib import ExitStack
from datetime import date
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError

from rh.deduplicacao.entrada import DocumentoDeOutraPessoa, Politica, verificar_documento
from rh.models import DeduplicacaoPessoa, PessoaFisica
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db
CPF = '529.982.247-25'


def test_cria_quando_documento_nao_existe() -> None:
    pessoa, criada = PessoaFisica.objects.obter_ou_criar({'cpf': '52998224725', 'nome': 'Ana Souza'}, Politica.CAUTELOSA)

    assert criada
    assert pessoa.documento_identificador == CPF


def test_exige_documento() -> None:
    with pytest.raises(ValidationError):
        PessoaFisica.objects.obter_ou_criar({'nome': 'Sem Documento'}, Politica.CAUTELOSA)


def test_pessoa_nova_com_pais_sem_iso_e_recusada() -> None:
    from comum.models import Pais

    sem_iso = Pais.objects.create(codigo='005', nome='ALEMANHA ORIENTAL')
    mensagem = 'País sem código ISO 3166-1 alfa-3; peça ao administrador para preencher em Países.'

    with pytest.raises(ValidationError, match=mensagem):
        verificar_documento(passaporte='AB123456', pais=sem_iso)
    with pytest.raises(ValidationError, match=mensagem):
        PessoaFisica.objects.obter_ou_criar({'passaporte': 'AB123456', 'pais_origem': sem_iso, 'nome': 'Hans'}, Politica.CAUTELOSA)


def test_reusa_pessoa_com_cpf_em_outro_formato() -> None:
    existente = PessoaFisicaFactory(cpf=CPF)

    pessoa, criada = PessoaFisica.objects.obter_ou_criar({'cpf': '52998224725', 'nome': 'Ana Souza'}, Politica.CAUTELOSA)

    assert not criada
    assert pessoa.pk == existente.pk


def test_cautelosa_recusa_nascimento_divergente() -> None:
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))

    with pytest.raises(DocumentoDeOutraPessoa):
        PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nascimento_data': date(1991, 1, 1)}, Politica.CAUTELOSA)


def test_cautelosa_sobrescreve_sem_apagar() -> None:
    existente = PessoaFisicaFactory(cpf=CPF, nome_mae='Maria', nome_pai='José')

    pessoa, _ = PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nome_mae': 'Maria Silva', 'nome_pai': ''}, Politica.CAUTELOSA)

    pessoa.refresh_from_db()
    assert pessoa.pk == existente.pk
    assert pessoa.nome_mae == 'Maria Silva'
    assert pessoa.nome_pai == 'José'


def test_autoritativa_sobrescreve_e_registra_divergencia() -> None:
    existente = PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))

    PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nascimento_data': date(1991, 1, 1)}, Politica.AUTORITATIVA)

    existente.refresh_from_db()
    assert existente.nascimento_data == date(1991, 1, 1)
    assert DeduplicacaoPessoa.objects.filter(pf_id=existente.pk, acao=DeduplicacaoPessoa.DIVERGENCIA_ENTRADA, aplicado_em__isnull=False).exists()


def test_preencher_so_completa_vazios() -> None:
    existente = PessoaFisicaFactory(cpf=CPF, nome_mae='Maria', nome_pai=None)

    PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nome_mae': 'Outra', 'nome_pai': 'José'}, Politica.PREENCHER)

    existente.refresh_from_db()
    assert existente.nome_mae == 'Maria'
    assert existente.nome_pai == 'José'


def test_com_duplicata_legada_usa_a_de_maior_prioridade(sem_unicidade_pessoa: None) -> None:
    PessoaFisicaFactory(cpf=CPF)
    mais_nova = PessoaFisicaFactory(cpf=CPF)

    pessoa, _ = PessoaFisica.objects.obter_ou_criar({'cpf': CPF}, Politica.PREENCHER)

    assert pessoa.pk == mais_nova.pk


def test_passaporte_vale_com_pais() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    chile = Pais.objects.create(codigo='158', nome='CHILE', iso_alfa3='CHL')
    existente = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)

    mesma, criada_mesma = PessoaFisica.objects.obter_ou_criar({'passaporte': 'ab123456', 'pais_origem': argentina}, Politica.PREENCHER)
    outra, criada_outra = PessoaFisica.objects.obter_ou_criar({'passaporte': 'AB123456', 'pais_origem': chile, 'nome': 'Outra'}, Politica.PREENCHER)

    assert (mesma.pk, criada_mesma) == (existente.pk, False)
    assert criada_outra
    assert outra.documento_identificador == 'CHL-AB123456'
    with pytest.raises(ValidationError):
        PessoaFisica.objects.obter_ou_criar({'passaporte': 'ZZ999999', 'nome': 'Sem País'}, Politica.PREENCHER)


def test_verificar_documento_nao_escreve_e_recusa_divergencia() -> None:
    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    total = PessoaFisica.objects.count()

    with pytest.raises(DocumentoDeOutraPessoa):
        verificar_documento(cpf=CPF, nascimento_data='1991-01-01')
    verificar_documento(cpf=CPF, nascimento_data=date(1990, 1, 1))
    verificar_documento(cpf='390.533.447-05', nascimento_data=date(1991, 1, 1))

    assert PessoaFisica.objects.count() == total


def test_pessoa_externa_nova_reusa_pf_e_nao_sobrescreve() -> None:
    from rh.models import PessoaExterna

    existente = PessoaFisicaFactory(cpf=CPF, nome_mae='Maria')

    # a edição da externa depois de criada é dos testes de PF exclusiva/compartilhada abaixo
    externa = PessoaExterna(cpf=CPF, nome='Ana Souza', nome_mae='Antiga')
    externa.save()

    existente.refresh_from_db()
    assert externa.pessoa_fisica_id == existente.pk
    assert existente.nome_mae == 'Maria'


def test_pessoa_externa_recusa_cpf_de_pessoa_com_outro_nascimento() -> None:
    from rh.models import PessoaExterna

    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    totais = (PessoaFisica.objects.count(), PessoaExterna.objects.count())

    with pytest.raises(DocumentoDeOutraPessoa):
        PessoaExterna(cpf=CPF, nome='Ana Souza', nascimento_data=date(1991, 1, 1)).save()

    assert (PessoaFisica.objects.count(), PessoaExterna.objects.count()) == totais


def test_prestador_novo_nao_apaga_dados_da_pessoa_existente_com_vazios_da_api() -> None:
    from comum.models import APIExterna, PrestadorServico

    existente = PessoaFisicaFactory(cpf=CPF, nome_mae='Maria', nascimento_data=date(1990, 1, 1))
    # fronteira externa: o gateway da API de pessoa física do governo
    api = Mock(ativo=True)
    api.get_service.return_value.get_dados_pessoais.return_value = (
        True,
        [{'CPF': '52998224725', 'Nome': 'ANA SOUZA', 'NomeMae': '', 'NomePai': None, 'Sexo': 3, 'DataNascimento': 'invalida'}],
    )

    with patch.object(APIExterna, 'PESSOAFISICA', api), patch('comum.models.sync_ldap_user'), patch('comum.models.sync_ldap_setor'):
        retorno = PrestadorServico.update_or_create({'pessoa_fisica': {'cpf': CPF, 'nome_registro': 'Ana Souza'}, 'ativo': True}, enviar_email=False)

    existente.refresh_from_db()
    assert retorno['prestador_created']
    assert retorno['pessoa_fisica'].pk == existente.pk
    assert (existente.nome_mae, existente.nascimento_data) == ('Maria', date(1990, 1, 1))
    assert existente.nome_registro == 'ANA SOUZA'


def _sem_fronteiras_externas() -> ExitStack:
    """API de pessoa física do governo desligada e LDAP mudo: as fronteiras externas do cadastro de prestador."""
    from comum.models import APIExterna

    pilha = ExitStack()
    pilha.enter_context(patch.object(APIExterna, 'PESSOAFISICA', Mock(ativo=False)))
    pilha.enter_context(patch('comum.models.sync_ldap_user'))
    pilha.enter_context(patch('comum.models.sync_ldap_setor'))
    return pilha


def test_prestador_novo_nao_sobrescreve_endereco_da_pessoa_existente() -> None:
    from comum.models import PessoaEndereco, PrestadorServico

    existente = PessoaFisicaFactory(cpf=CPF)
    PessoaEndereco.objects.create(pessoa=existente, logradouro='Rua A', numero='10')

    with _sem_fronteiras_externas():
        PrestadorServico.update_or_create(
            {'pessoa_fisica': {'cpf': CPF, 'nome_registro': 'Ana Souza'}, 'ativo': True, 'endereco': {'logradouro': '', 'numero': '99'}},
            enviar_email=False,
        )

    endereco = PessoaEndereco.objects.get(pessoa=existente)
    assert (endereco.logradouro, endereco.numero) == ('Rua A', '10')


def test_prestador_editando_o_proprio_cadastro_atualiza_o_contato() -> None:
    from comum.models import PessoaEndereco, PrestadorServico
    from comum.tests.factories import PrestadorServicoFactory

    prestador = PrestadorServicoFactory(matricula='52998224725', pessoa_fisica__cpf=CPF)
    PessoaEndereco.objects.create(pessoa=prestador.pessoa_fisica, logradouro='Rua A', numero='10', complemento='Apto 1')

    with _sem_fronteiras_externas():
        PrestadorServico.update_or_create(
            {'pessoa_fisica': {'cpf': CPF}, 'ativo': True, 'endereco': {'logradouro': 'Rua B', 'complemento': ''}}, enviar_email=False
        )

    endereco = PessoaEndereco.objects.get(pessoa=prestador.pessoa_fisica)
    assert (endereco.logradouro, endereco.numero, endereco.complemento) == ('Rua B', '10', 'Apto 1')


def test_prestador_corrige_o_proprio_nascimento_com_auditoria() -> None:
    from comum.models import PrestadorServico
    from comum.tests.factories import PrestadorServicoFactory

    prestador = PrestadorServicoFactory(matricula='52998224725', pessoa_fisica__cpf=CPF, pessoa_fisica__nascimento_data=date(1990, 1, 1))

    with _sem_fronteiras_externas():
        PrestadorServico.update_or_create({'pessoa_fisica': {'cpf': CPF, 'nascimento_data': date(1991, 1, 1)}, 'ativo': True}, enviar_email=False)

    pessoa = PessoaFisica.objects.get(pk=prestador.pessoa_fisica_id)
    assert pessoa.nascimento_data == date(1991, 1, 1)
    assert DeduplicacaoPessoa.objects.filter(pf_id=pessoa.pk, acao=DeduplicacaoPessoa.DIVERGENCIA_ENTRADA).exists()


def test_edicao_da_externa_alcanca_a_pf_exclusiva() -> None:
    from rh.models import PessoaExterna

    externa = PessoaExterna(cpf=CPF, nome='Ana Souza', nome_mae='Maria')
    externa.save()
    externa.nome_mae = 'Maria Souza'
    externa.save()

    assert PessoaFisica.objects.get(pk=externa.pessoa_fisica_id).nome_mae == 'Maria Souza'


def test_edicao_da_externa_nao_toca_a_pf_compartilhada() -> None:
    from comum.tests.factories import PrestadorServicoFactory
    from rh.models import PessoaExterna

    externa = PessoaExterna(cpf=CPF, nome='Ana Souza', nome_mae='Maria')
    externa.save()
    PrestadorServicoFactory(matricula='52998224725', pessoa_fisica=externa.pessoa_fisica)
    externa.nome_mae = 'Maria Souza'
    externa.save()

    assert PessoaFisica.objects.get(pk=externa.pessoa_fisica_id).nome_mae == 'Maria'


def test_filtros_de_passaporte_em_branco_nao_casam_quem_nao_tem_passaporte() -> None:
    from rh.deduplicacao.entrada import filtro_par_passaporte

    PessoaFisicaFactory(cpf=CPF)

    assert not PessoaFisica.objects.filter(filtro_par_passaporte('   ', None)).exists()


def test_par_de_passaporte_nao_casa_pessoa_sem_pais() -> None:
    from comum.models import Pais
    from rh.deduplicacao.entrada import filtro_par_passaporte

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    legado = PessoaFisicaFactory(cpf=CPF, passaporte='AB123456')

    assert not PessoaFisica.objects.filter(filtro_par_passaporte('ab123456', argentina)).exists()
    PessoaFisica.objects.filter(pk=legado.pk).update(pais_origem=argentina)
    assert PessoaFisica.objects.filter(filtro_par_passaporte('ab123456', argentina)).get() == legado


def test_par_de_passaporte_casa_pelo_iso_do_pais() -> None:
    from comum.models import Pais
    from rh.deduplicacao.entrada import filtro_par_passaporte

    suica = Pais.objects.create(codigo='150', nome='SUICA', iso_alfa3='CHE')
    suica_236 = Pais.objects.create(codigo='236', nome='SUICA', iso_alfa3='CHE')
    dona = PessoaFisicaFactory(cpf=None, passaporte='X1234567', pais_origem=suica)

    assert PessoaFisica.objects.filter(filtro_par_passaporte('x1234567', suica_236)).get() == dona
    assert PessoaFisica.objects.filter(filtro_par_passaporte('x1234567', suica_236.pk)).get() == dona


def test_cpf_novo_com_passaporte_de_quem_tem_outro_cpf_e_recusado() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    outra = PessoaFisicaFactory(cpf='390.533.447-05', passaporte='AB123456', pais_origem=argentina)
    dados = {'cpf': CPF, 'passaporte': 'AB123456', 'pais_origem': argentina, 'nome': 'Ana Souza'}

    for politica in Politica:
        with pytest.raises(DocumentoDeOutraPessoa, match='Passaporte já pertence a outra pessoa'):
            PessoaFisica.objects.obter_ou_criar(dados, politica)
    with pytest.raises(DocumentoDeOutraPessoa, match='Passaporte já pertence a outra pessoa'):
        verificar_documento(cpf=CPF, passaporte='ab123456', pais=argentina)

    outra.refresh_from_db()
    assert outra.cpf == '390.533.447-05'
    assert not PessoaFisica.objects.filter(cpf=CPF).exists()


def test_estrangeiro_so_com_passaporte_que_ganhou_cpf_e_reusado() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    so_passaporte = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)

    pessoa, criada = PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'passaporte': 'AB123456', 'pais_origem': argentina}, Politica.CAUTELOSA)

    assert (pessoa.pk, criada) == (so_passaporte.pk, False)
    so_passaporte.refresh_from_db()
    assert so_passaporte.cpf == CPF


def test_cpf_invalido_e_recusado_e_nao_casa_com_o_legado() -> None:
    legado = PessoaFisicaFactory(nascimento_data=date(1990, 1, 1))
    PessoaFisica.objects.filter(pk=legado.pk).update(cpf='111.111.111-11', documento_identificador='111.111.111-11')
    total = PessoaFisica.objects.count()

    for politica in Politica:
        with pytest.raises(ValidationError):
            PessoaFisica.objects.obter_ou_criar({'cpf': '111.111.111-11', 'nome': 'Outra Pessoa'}, politica)
    # não casa: a pessoa com outro nascimento não é recusada como "documento de outra pessoa"
    verificar_documento(cpf='111.111.111-11', nascimento_data=date(1991, 1, 1))

    legado.refresh_from_db()
    assert legado.nome != 'Outra Pessoa'
    assert PessoaFisica.objects.count() == total


def test_passaporte_invalido_e_recusado_sem_cpf_e_descartado_com_cpf() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    legado = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    PessoaFisica.objects.filter(pk=legado.pk).update(passaporte='AAAAAA', documento_identificador='ARG-AAAAAA')

    with pytest.raises(ValidationError):
        PessoaFisica.objects.obter_ou_criar({'passaporte': 'AAAAAA', 'pais_origem': argentina, 'nome': 'Outra'}, Politica.PREENCHER)
    # com CPF válido o passaporte inválido não é gravado: a higiene o anularia e a próxima entrada o regravaria
    pessoa, criada = PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'passaporte': 'AAAAAA', 'pais_origem': argentina}, Politica.CAUTELOSA)

    pessoa.refresh_from_db()
    assert criada
    assert pessoa.passaporte is None


def _advisory_locks_da_sessao() -> int:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()")
        return cursor.fetchone()[0]


def test_lock_do_documento_e_liberado_a_cada_chamada_mesmo_em_transacao_longa() -> None:
    from django.db import DatabaseError, transaction

    from rh.tests.factories import cpf_valido

    PessoaFisicaFactory(cpf=CPF, nascimento_data=date(1990, 1, 1))
    with transaction.atomic():  # o import de milhares de pessoas numa transação só (ex.: credores do SIAFI)
        for n in range(5):
            PessoaFisica.objects.obter_ou_criar({'cpf': cpf_valido(950 + n), 'nome': f'Importada {n}'}, Politica.PREENCHER)
        with pytest.raises(DocumentoDeOutraPessoa):
            PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nascimento_data': date(1991, 1, 1)}, Politica.CAUTELOSA)
        with pytest.raises(DatabaseError):  # erro de banco no meio (valor maior que a coluna): o unlock ainda roda
            PessoaFisica.objects.obter_ou_criar({'cpf': cpf_valido(960), 'nome': 'Longo', 'nome_mae': 'x' * 101}, Politica.PREENCHER)

        assert _advisory_locks_da_sessao() == 0
        assert PessoaFisica.objects.filter(nome__startswith='Importada ').count() == 5


def test_externa_nao_salva_cpf_diferente_do_da_pf() -> None:
    from rh.models import PessoaExterna

    externa = PessoaExterna(cpf=CPF, nome='Ana Souza', nome_mae='Maria')
    externa.save()
    externa.cpf, externa.nome_mae = '390.533.447-05', 'Maria Souza'

    # quem salva sem o formulário também não deixa a externa com um CPF e a PF com outro
    with pytest.raises(ValidationError):
        externa.save()

    externa.refresh_from_db()
    pessoa = PessoaFisica.objects.get(pk=externa.pessoa_fisica_id)
    assert (externa.cpf, pessoa.cpf, pessoa.nome_mae) == (CPF, CPF, 'Maria')


def test_externa_legada_com_cpf_divergente_salva_sem_trocar_o_cpf() -> None:
    from rh.models import PessoaExterna

    externa = PessoaExterna(cpf=CPF, nome='Ana Souza', nome_mae='Maria')
    externa.save()
    PessoaExterna.objects.filter(pk=externa.pk).update(cpf='390.533.447-05')  # legado: já divergia da PF antes da guarda
    externa = PessoaExterna.objects.get(pk=externa.pk)
    externa.nome_mae = 'Maria Souza'

    externa.save()  # sem mexer no CPF, a legada continua salvável

    externa.cpf = '111.444.777-35'
    with pytest.raises(ValidationError):  # trocar o CPF continua recusado
        externa.save()
    externa.refresh_from_db()
    pessoa = PessoaFisica.objects.get(pk=externa.pessoa_fisica_id)
    assert (externa.cpf, pessoa.cpf, pessoa.nome_mae) == ('390.533.447-05', CPF, 'Maria Souza')


def test_falha_ao_travar_a_segunda_chave_nao_deixa_lock_na_sessao() -> None:
    from django.db import OperationalError, connection, transaction

    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    with connection.cursor() as cursor:
        cursor.execute('SELECT hashtext(%s) < hashtext(%s)', [CPF, 'ARG-AB123456'])
        assert cursor.fetchone()[0], 'premissa: a chave do passaporte é a 2ª travada (pela string e pelo hash)'
    outra = connection.copy()
    try:
        with outra.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_lock(hashtext(%s))', ['ARG-AB123456'])
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '300ms'")
            with pytest.raises(OperationalError):
                PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'passaporte': 'AB123456', 'pais_origem': argentina}, Politica.CAUTELOSA)

            assert _advisory_locks_da_sessao() == 0
    finally:
        with outra.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock_all()')
        outra.close()


def test_conexao_quebrada_nao_encobre_o_erro_original() -> None:
    from django.db import OperationalError, connection

    from rh.deduplicacao import entrada

    with (
        patch.object(entrada, '_obter_ou_criar_travado', side_effect=OperationalError('conexão caiu')),
        patch.object(connection, 'savepoint_rollback', side_effect=OperationalError('sem conexão')),
        pytest.raises(OperationalError, match='conexão caiu'),
    ):
        PessoaFisica.objects.obter_ou_criar({'cpf': CPF}, Politica.PREENCHER)
    # a transação real está íntegra (só o rollback foi simulado): limpa o lock que o backend "morto" soltaria
    connection.needs_rollback = False
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_unlock_all()')


def test_cpf_com_dono_e_passaporte_de_pessoa_sem_cpf_e_recusado() -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    dona_do_cpf = PessoaFisicaFactory(cpf=CPF, passaporte=None)
    dona_do_par = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    dados = {'cpf': CPF, 'passaporte': 'AB123456', 'pais_origem': argentina, 'nome': 'Ana Souza'}

    with pytest.raises(DocumentoDeOutraPessoa, match='Passaporte já pertence a outra pessoa'):
        PessoaFisica.objects.obter_ou_criar(dados, Politica.CAUTELOSA)
    with pytest.raises(DocumentoDeOutraPessoa, match='Passaporte já pertence a outra pessoa'):
        verificar_documento(cpf=CPF, passaporte='ab123456', pais=argentina)

    dona_do_cpf.refresh_from_db()
    dona_do_par.refresh_from_db()
    assert (dona_do_cpf.passaporte, dona_do_cpf.pais_origem_id) == (None, None)
    assert (dona_do_par.cpf, dona_do_par.documento_identificador) == (None, 'ARG-AB123456')


def test_politica_nao_regrava_documento_invalido() -> None:
    from rh.deduplicacao.entrada import aplicar_politica

    anulada = PessoaFisicaFactory()  # a higiene anulou o CPF inválido dela
    PessoaFisica.objects.filter(pk=anulada.pk).update(cpf=None, documento_identificador=f'INVALIDO-{anulada.pk}-11111111111')
    anulada.refresh_from_db()
    aplicar_politica(anulada, {'cpf': '111.111.111-11', 'nome_mae': 'Maria Nova'}, Politica.AUTORITATIVA, preservar_documento=True)
    anulada.save()
    servidor = PessoaFisicaFactory(cpf=CPF, passaporte=None)
    aplicar_politica(servidor, {'cpf': '111.111.111-11', 'passaporte': 'AAAAAA', 'nome_mae': 'Maria Nova'}, Politica.AUTORITATIVA)
    servidor.save()

    anulada.refresh_from_db()
    servidor.refresh_from_db()
    assert (anulada.cpf, anulada.documento_identificador, anulada.nome_mae) == (None, f'INVALIDO-{anulada.pk}-11111111111', 'Maria Nova')
    assert (servidor.cpf, servidor.passaporte, servidor.nome_mae) == (CPF, None, 'Maria Nova')


def test_externa_nova_com_a_pf_ja_definida_salva_sem_cpf() -> None:
    from rh.models import PessoaExterna

    pessoa = PessoaFisicaFactory(cpf=CPF)
    externa = PessoaExterna(pessoa_fisica=pessoa, nome='Ana Souza')  # como os commands que criam a externa da PF existente

    externa.save()

    assert PessoaExterna.objects.get(pk=externa.pk).pessoa_fisica_id == pessoa.pk


def _em_conflito(pessoa: PessoaFisica) -> PessoaFisica:
    """Como o ``aplicar`` deixa a PF cujo documento ficou com outra: sem CPF/passaporte e com o sintético."""
    PessoaFisica.objects.filter(pk=pessoa.pk).update(
        cpf=None, passaporte=None, pais_origem=None, documento_identificador=f'CONFLITO-{pessoa.pk}-ARG-AB123456'
    )
    pessoa.refresh_from_db()
    return pessoa


def test_siape_nao_grava_cpf_de_outra_pessoa_e_audita() -> None:
    from rh.deduplicacao.entrada import aplicar_politica

    sobrevivente = PessoaFisicaFactory(cpf=CPF)
    conflito = _em_conflito(PessoaFisicaFactory(nome_mae='Maria'))

    aplicar_politica(conflito, {'cpf': '52998224725', 'nome_mae': 'Maria Nova'}, Politica.AUTORITATIVA)
    conflito.save()

    conflito.refresh_from_db()
    assert (conflito.cpf, conflito.documento_identificador, conflito.nome_mae) == (None, f'CONFLITO-{conflito.pk}-ARG-AB123456', 'Maria Nova')
    linha = DeduplicacaoPessoa.objects.get(pf_id=conflito.pk)
    assert (linha.acao, linha.campo, linha.valor_original, linha.motivo, linha.aplicado_em is not None) == (
        DeduplicacaoPessoa.DIVERGENCIA_ENTRADA,
        'cpf',
        CPF,
        f'documento informado pela fonte pertence à PF {sobrevivente.pk}; não aplicado',
        True,
    )


@pytest.mark.parametrize(
    ('politica', 'preservar_documento'),
    [(Politica.PREENCHER, False), (Politica.CAUTELOSA, False), (Politica.AUTORITATIVA, True)],
)
def test_demais_politicas_recusam_cpf_de_outra_pessoa(politica: Politica, preservar_documento: bool) -> None:
    from rh.deduplicacao.entrada import aplicar_politica

    PessoaFisicaFactory(cpf=CPF)
    conflito = _em_conflito(PessoaFisicaFactory(nome_mae=None))

    with pytest.raises(DocumentoDeOutraPessoa):
        aplicar_politica(conflito, {'cpf': CPF, 'nome_mae': 'Maria Nova'}, politica, preservar_documento=preservar_documento)

    assert (conflito.cpf, conflito.nome_mae) == (None, None)
    assert not DeduplicacaoPessoa.objects.filter(pf_id=conflito.pk).exists()


@pytest.mark.parametrize(
    ('politica', 'preservar_documento'),
    [(Politica.PREENCHER, False), (Politica.CAUTELOSA, False), (Politica.AUTORITATIVA, True)],
)
def test_demais_politicas_recusam_par_de_passaporte_de_outra_pessoa(politica: Politica, preservar_documento: bool) -> None:
    from comum.models import Pais
    from rh.deduplicacao.entrada import PassaporteDeOutraPessoa, aplicar_politica

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    conflito = _em_conflito(PessoaFisicaFactory())

    with pytest.raises(PassaporteDeOutraPessoa):
        aplicar_politica(conflito, {'passaporte': 'ab123456', 'pais_origem': argentina}, politica, preservar_documento=preservar_documento)


@pytest.mark.parametrize(
    ('politica', 'preservar_documento'),
    [(Politica.PREENCHER, False), (Politica.CAUTELOSA, False), (Politica.AUTORITATIVA, True)],
)
def test_par_de_passaporte_de_outra_pessoa_no_outro_codigo_do_mesmo_iso_e_recusado(politica: Politica, preservar_documento: bool) -> None:
    from comum.models import Pais
    from rh.deduplicacao.entrada import PassaporteDeOutraPessoa, aplicar_politica

    suica = Pais.objects.create(codigo='150', nome='SUICA', iso_alfa3='CHE')
    suica_236 = Pais.objects.create(codigo='236', nome='SUICA', iso_alfa3='CHE')
    PessoaFisicaFactory(cpf=None, passaporte='X1234567', pais_origem=suica)
    conflito = _em_conflito(PessoaFisicaFactory())

    with pytest.raises(PassaporteDeOutraPessoa):
        aplicar_politica(conflito, {'passaporte': 'x1234567', 'pais_origem': suica_236}, politica, preservar_documento=preservar_documento)


def test_siape_nao_grava_par_de_outra_pessoa_no_outro_codigo_do_mesmo_iso_e_audita() -> None:
    from comum.models import Pais
    from rh.deduplicacao.entrada import aplicar_politica

    suica = Pais.objects.create(codigo='150', nome='SUICA', iso_alfa3='CHE')
    suica_236 = Pais.objects.create(codigo='236', nome='SUICA', iso_alfa3='CHE')
    dona = PessoaFisicaFactory(cpf=None, passaporte='X1234567', pais_origem=suica)
    conflito = _em_conflito(PessoaFisicaFactory())

    aplicar_politica(conflito, {'passaporte': 'x1234567', 'pais_origem_id': suica_236.pk}, Politica.AUTORITATIVA)
    conflito.save()

    conflito.refresh_from_db()
    assert (conflito.passaporte, conflito.pais_origem_id) == (None, None)
    assert (
        DeduplicacaoPessoa.objects.get(pf_id=conflito.pk, campo='passaporte').motivo
        == f'documento informado pela fonte pertence à PF {dona.pk}; não aplicado'
    )


def test_siape_nao_grava_par_de_passaporte_de_outra_pessoa_e_audita() -> None:
    from comum.models import Pais
    from rh.deduplicacao.entrada import aplicar_politica

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    dona = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina)
    conflito = _em_conflito(PessoaFisicaFactory(nome_mae='Maria'))

    aplicar_politica(conflito, {'passaporte': 'ab123456', 'pais_origem_id': argentina.pk, 'nome_mae': 'Maria Nova'}, Politica.AUTORITATIVA)
    conflito.save()

    conflito.refresh_from_db()
    assert (conflito.passaporte, conflito.pais_origem_id, conflito.nome_mae) == (None, None, 'Maria Nova')
    linha = DeduplicacaoPessoa.objects.get(pf_id=conflito.pk)
    assert (linha.acao, linha.campo, linha.valor_original, linha.motivo) == (
        DeduplicacaoPessoa.DIVERGENCIA_ENTRADA,
        'passaporte',
        'AB123456',
        f'documento informado pela fonte pertence à PF {dona.pk}; não aplicado',
    )


def test_siape_com_o_mesmo_cpf_da_duplicata_legada_nao_audita(sem_unicidade_pessoa: None) -> None:
    PessoaFisicaFactory(cpf=CPF)
    PessoaFisicaFactory(cpf='52998224725')

    PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'nome_mae': 'Maria Nova'}, Politica.AUTORITATIVA)

    assert not DeduplicacaoPessoa.objects.exists()


@pytest.mark.parametrize('politica', [Politica.CAUTELOSA, Politica.AUTORITATIVA])
def test_par_de_passaporte_da_duplicata_legada_com_o_mesmo_cpf_nao_e_de_outra_pessoa(sem_unicidade_pessoa: None, politica: Politica) -> None:
    from comum.models import Pais

    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    PessoaFisicaFactory(cpf='52998224725', passaporte='AB123456', pais_origem=argentina)
    principal = PessoaFisicaFactory(cpf=CPF, passaporte=None)

    pessoa, _ = PessoaFisica.objects.obter_ou_criar({'cpf': CPF, 'passaporte': 'AB123456', 'pais_origem': argentina}, politica)

    pessoa.refresh_from_db()
    assert (pessoa.pk, pessoa.passaporte, pessoa.pais_origem_id) == (principal.pk, 'AB123456', argentina.pk)
    assert not DeduplicacaoPessoa.objects.exists()
