from __future__ import annotations

from django.contrib.auth.models import Group

from comum.models import User, Vinculo
from rh.models import Papel, Setor


def eh_auditor(user):
    perfis = ['Auditor']
    return user.groups.filter(name__in=perfis).exists()


def eh_auditor_chefe(user):
    perfis = ['Auditor Sistêmico']
    return eh_auditor(user) and user.groups.filter(name__in=perfis).exists()


def eh_procurador(user):
    perfis = ['Procurador']
    return user.groups.filter(name__in=perfis).exists()


def get_setor_auditor_chefe():
    from comum.models import Configuracao

    pk = Configuracao.get_valor_por_chave('auditoria', 'setor_auditor_chefe')
    return Setor.objects.suap_ativos().filter(pk=pk).first() if pk else Setor.objects.suap_ativos().filter(sigla='AUDGE').first()


def get_papel_auditor_chefe():
    from comum.models import Configuracao

    pk = Configuracao.get_valor_por_chave('auditoria', 'papel_auditor_chefe')
    return Papel.objects.filter(pk=pk, data_fim__isnull=True).first()


def sou_chefe_auditoria_hoje(user: User) -> bool:
    setor = get_setor_auditor_chefe()
    return tenho_poder_de_chefe(user, setor) or eh_auditor_chefe(user)


def get_auditores_ativos():
    return Vinculo.objects.ativos().servidores().filter(user__groups=Group.objects.get(name='Auditor'), user__is_superuser=False)


def get_todos_chefes_setores(setores):
    vinculos = []
    for setor in setores:
        vinculos_setor = [servidor.get_vinculo() for servidor in setor.obter_chefes_hieraquicamente()]
        vinculos.extend(vinculos_setor)
    return vinculos


def tenho_poder_de_chefe(user: User, setor: Setor | None) -> bool:
    """Indica se o usuário chefia hoje o ``setor`` (ou um ascendente dele).

    Só servidor/prestador (``AbstractFuncionario``) responde a ``eh_chefe_do_setor_hoje``;
    aluno, usuário sem vínculo e demais relacionamentos nunca são chefes.
    """
    eh_chefe_do_setor_hoje = getattr(user.get_relacionamento(), 'eh_chefe_do_setor_hoje', None)
    return eh_chefe_do_setor_hoje is not None and setor is not None and eh_chefe_do_setor_hoje(setor)
