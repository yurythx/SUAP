from types import SimpleNamespace

from ldap_backend.models import LdapConf


def test_orientacao_inativacao_estrangeiro_mantem_acesso_ao_suap() -> None:
    configuracao = LdapConf()
    aluno = SimpleNamespace(pessoa_fisica=SimpleNamespace(eh_estrangeiro=True))

    orientacao = configuracao._get_orientacao_acesso_inativado(aluno, 'Aluno(a)')

    assert 'acesso ao SUAP continuará disponível' in orientacao
    assert 'matrícula e senha do SUAP' in orientacao
