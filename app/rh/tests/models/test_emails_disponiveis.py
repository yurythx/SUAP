import importlib
import itertools

import pytest
from django.contrib.auth.models import Group

from comum.models import Ano, Configuracao, EmailBlockList
from edu.models import Aluno, SituacaoMatricula
from rh.models import PessoaFisica, Servidor, Situacao
from rh.tests.factories import cpf_valido

# `rh.models.pessoa` é pacote e módulo ao mesmo tempo, o que quebra o monkeypatch por string.
modulo_pessoa_fisica = importlib.import_module('rh.models.pessoa.pessoa_fisica')

# Faixa própria, fora da do `ServidorFactory` (9000000+) e da do antigo `suap_data`
# (1111111-4444444): estes testes fixam a matrícula, então precisam de um espaço que
# ninguém mais ocupe. Colidir aqui dá IntegrityError na unique de `Servidor.matricula`.
_matriculas_servidor = itertools.count(7000001)
_matriculas_aluno = itertools.count(90262154510001)

DOMINIO_ACADEMICO = 'academico.ifrn.edu.br'
DOMINIO_INSTITUCIONAL = 'ifrn.edu.br'


class LdapConfVazio:
    """Stub de LdapConf sem nenhuma conta cadastrada."""

    def get_usernames_from_mail(self, email):
        return []

    def get_usernames_from_principalname(self, email):
        return []

    def get_usernames_from_email_academico(self, email):
        return []

    def get_usernames_from_email_google_classroom(self, email):
        return []


@pytest.fixture
def ldap_habilitado(monkeypatch):
    monkeypatch.setattr(modulo_pessoa_fisica, 'is_ldap_write_enabled', lambda: True)
    monkeypatch.setattr(modulo_pessoa_fisica, 'get_ldap_conf', LdapConfVazio)


@pytest.fixture
def grupos_do_signal(db):
    """`user_post_save` (comum) exige que estes grupos existam ao salvar um Servidor."""
    for nome in ('Aposentado', 'Servidor', 'Servidores Com Poder de Chefe'):
        Group.objects.get_or_create(name=nome)


@pytest.fixture
def dominios(db):
    Configuracao.objects.create(app='ldap_backend', chave='dominio_academico', valor=DOMINIO_ACADEMICO)
    Configuracao.objects.create(app='ldap_backend', chave='dominio_institucional', valor=DOMINIO_INSTITUCIONAL)
    Configuracao.clear_cache()
    yield
    Configuracao.clear_cache()


def _criar_servidor(nome, email_institucional=''):
    matricula = str(next(_matriculas_servidor))
    # Pessoa descartada de propósito: mantém pessoa_fisica.id != servidor.id, como em produção.
    PessoaFisica.objects.create(nome=f'Descartada {matricula}', cpf=cpf_valido(int(matricula) + 100_000_000))
    pessoa_fisica = PessoaFisica.objects.create(nome=nome, cpf=cpf_valido(int(matricula)))
    situacao, _ = Situacao.objects.get_or_create(codigo='01', defaults={'nome': 'Ativo'})
    Servidor.objects.create(
        pessoa_fisica=pessoa_fisica,
        matricula=matricula,
        matricula_crh=matricula,
        matricula_sipe=matricula,
        situacao=situacao,
        email_institucional=email_institucional,
    )
    return pessoa_fisica


def _criar_aluno(nome, email_academico=''):
    matricula = str(next(_matriculas_aluno))
    pessoa_fisica = PessoaFisica.objects.create(nome=nome, cpf=cpf_valido(int(matricula)))
    ano_letivo, _ = Ano.objects.get_or_create(ano=2026)
    situacao, _ = SituacaoMatricula.objects.get_or_create(id=SituacaoMatricula.MATRICULADO, defaults={'descricao': 'Matriculado'})
    Aluno.objects.create(
        pessoa_fisica=pessoa_fisica,
        matricula=matricula,
        ano_letivo=ano_letivo,
        periodo_letivo=1,
        situacao=situacao,
        email_academico=email_academico,
    )
    return pessoa_fisica


@pytest.mark.django_db
def test_nao_oferece_email_academico_de_aluno_para_servidora_com_institucional_de_mesmo_prefixo(dominios, grupos_do_signal, ldap_habilitado):
    """Caso real: o prefixo institucional da própria servidora pulava a checagem do email do aluno."""
    _criar_aluno('Vitoria Canuto de Alencar', f'vitoria.alencar@{DOMINIO_ACADEMICO}')
    pessoa_fisica = _criar_servidor('Vitoria Alencar Travassos', f'vitoria.alencar@{DOMINIO_INSTITUCIONAL}')

    emails = pessoa_fisica.get_emails_disponiveis(tipo='academico')

    assert f'vitoria.alencar@{DOMINIO_ACADEMICO}' not in emails
    assert f'vitoria.travassos@{DOMINIO_ACADEMICO}' in emails


@pytest.mark.django_db
def test_prefixo_ocupado_em_outro_dominio_nao_bloqueia(dominios, grupos_do_signal, ldap_habilitado):
    """A ocupação é por endereço completo: o mesmo prefixo pode existir em domínios diferentes."""
    _criar_aluno('Pedro Nunes Barros', f'pedro.nunes@{DOMINIO_ACADEMICO}')
    pessoa_fisica = _criar_servidor('Pedro Nunes Cabral')

    emails = pessoa_fisica.get_emails_disponiveis(tipo='institucional')

    assert f'pedro.nunes@{DOMINIO_INSTITUCIONAL}' in emails


@pytest.mark.django_db
def test_email_ocupado_em_outro_campo_do_mesmo_dominio_bloqueia(dominios, grupos_do_signal, ldap_habilitado):
    """O endereço ocupa independentemente do campo em que está gravado."""
    _criar_aluno('Rita Gomes Farias', f'rita.gomes@{DOMINIO_INSTITUCIONAL}')
    pessoa_fisica = _criar_servidor('Rita Gomes Teixeira')

    emails = pessoa_fisica.get_emails_disponiveis(tipo='institucional')

    assert f'rita.gomes@{DOMINIO_INSTITUCIONAL}' not in emails
    assert f'rita.teixeira@{DOMINIO_INSTITUCIONAL}' in emails


@pytest.mark.django_db
def test_nao_oferece_email_academico_ja_ocupado_mesmo_com_institucional_proprio(dominios, grupos_do_signal, ldap_habilitado):
    """Regressão: o prefixo institucional da própria pessoa não pode pular a checagem de ocupação."""
    pessoa_fisica = _criar_servidor('Vitoria Alencar Travassos', f'vitoria.alencar@{DOMINIO_INSTITUCIONAL}')
    EmailBlockList.objects.create(email=f'vitoria.alencar@{DOMINIO_ACADEMICO}')

    emails = pessoa_fisica.get_emails_disponiveis(tipo='academico')

    assert f'vitoria.alencar@{DOMINIO_ACADEMICO}' not in emails
    assert f'vitoria.travassos@{DOMINIO_ACADEMICO}' in emails


@pytest.mark.django_db
def test_oferece_email_academico_com_prefixo_institucional_de_outro_servidor(dominios, grupos_do_signal, ldap_habilitado):
    """O institucional de outra pessoa não reserva o acadêmico de mesmo prefixo."""
    _criar_servidor('Joao Silva Souza', f'joao.silva@{DOMINIO_INSTITUCIONAL}')
    pessoa_fisica = _criar_servidor('Joao Silva Pereira')

    emails = pessoa_fisica.get_emails_disponiveis(tipo='academico')

    assert f'joao.silva@{DOMINIO_ACADEMICO}' in emails


@pytest.mark.django_db
def test_institucional_oferece_as_mesmas_variantes_dos_demais_tipos(dominios, grupos_do_signal, ldap_habilitado):
    """As variantes abreviadas valem para os três tipos, não só para acadêmico e classroom."""
    pessoa_fisica = _criar_servidor('Ana Paula Ribeiro')

    emails = pessoa_fisica.get_emails_disponiveis(tipo='institucional')

    assert f'ana.ribeiro@{DOMINIO_INSTITUCIONAL}' in emails
    assert f'a.ribeiro@{DOMINIO_INSTITUCIONAL}' in emails
    assert f'ana.r@{DOMINIO_INSTITUCIONAL}' in emails


@pytest.mark.django_db
def test_oferece_email_academico_com_prefixo_do_proprio_institucional(dominios, grupos_do_signal, ldap_habilitado):
    pessoa_fisica = _criar_servidor('Maria Costa Lima', f'maria.costa@{DOMINIO_INSTITUCIONAL}')

    emails = pessoa_fisica.get_emails_disponiveis(tipo='academico')

    assert f'maria.costa@{DOMINIO_ACADEMICO}' in emails
