"""
Management command: auditar_grupo_rh_sistemico_crsc

Lista os membros (atuais ou passados) da CRSC-TAE que estão no grupo
"Coordenador de Gestão de Pessoas Sistêmico". Até 07/2026, o ``user_post_save``
adicionava indevidamente todo membro da comissão a esse grupo e nunca o removia —
este comando dá a visão para o RH decidir, caso a caso, de quem remover o grupo
(a remoção NÃO é automática, pois o usuário pode ser um RH sistêmico legítimo).

Uso:
    python manage.py auditar_grupo_rh_sistemico_crsc
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from rsc_tae.models import MembroComissaoRSCTae


class Command(BaseCommand):
    help = 'Lista membros da CRSC-TAE presentes no grupo "Coordenador de Gestão de Pessoas Sistêmico" (concessão possivelmente indevida).'

    def handle(self, *args, **options):
        grupo = Group.objects.filter(name='Coordenador de Gestão de Pessoas Sistêmico').first()
        if not grupo:
            self.stdout.write(self.style.WARNING('Grupo "Coordenador de Gestão de Pessoas Sistêmico" não existe neste ambiente.'))
            return

        membros = MembroComissaoRSCTae.objects.select_related('vinculo__pessoa', 'vinculo__user', 'comissao').order_by('vinculo__pessoa__nome')

        encontrados = 0
        for membro in membros:
            user = getattr(membro.vinculo, 'user', None)
            if not user or not user.groups.filter(pk=grupo.pk).exists():
                continue
            encontrados += 1
            situacao_membro = 'membro ATIVO' if membro.ativo else 'membro inativo'
            situacao_comissao = 'comissão ativa' if membro.comissao.ativa else 'comissão inativa'
            self.stdout.write(f'- {membro.vinculo} (user={user.username}) — {situacao_membro} / {situacao_comissao} [{membro.comissao}]')

        if not encontrados:
            self.stdout.write(self.style.SUCCESS('Nenhum membro da CRSC-TAE está no grupo de RH sistêmico.'))
            return
        self.stdout.write('')
        self.stdout.write(
            self.style.WARNING(f'{encontrados} usuário(s) listado(s). Avalie caso a caso e remova o grupo pelo admin de usuários quando indevido.')
        )
