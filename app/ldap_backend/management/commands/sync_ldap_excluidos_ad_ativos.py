from djtools.management.commands import BaseCommandPlus
from ldap_backend.models import LdapConf
from django.db.models import Exists, OuterRef
from datetime import date
from comum.models import PrestadorServico, OcupacaoPrestador
from edu.models import Aluno
from rh.models import Servidor


class Command(BaseCommandPlus):
    """Comando para buscar usuários no LDAP que não possuam extensionAttribute10
    e executar o sync para cada usuário encontrado.
    """

    help = 'Sincroniza usuários do LDAP que estão inativos mas com ad ativo ainda.'

    def handle(self, *args, **options):
        conf = LdapConf.get_active()
        if not conf:
            self.stdout.write('Nenhuma configuração LDAP ativa encontrada.')
            return

        username_field = conf.filterstr_prefix.replace('=', '')
        # Filtra usuários ativos no AD (userAccountControl=512) e que não estejam configurados para expirar.
        # Considera tanto o sentinel de 'never expires' (9223372036854775807) quanto entradas sem accountExpires.
        filterstr = '(&(objectClass=user)(userAccountControl=512)(|(accountExpires=0)(accountExpires=9223372036854775807)))'

        try:
            ldap_users = conf.search_objects(filterstr=filterstr, attrlist=[username_field], use_paged_results=True, sizelimit=500000)
        except Exception as e:
            self.stdout.write(f'Erro ao buscar usuários no LDAP: {e}')
            return

        users = {user.get(username_field, [b''])[0].decode() for user in ldap_users}
        alunos_synced_errors = []
        alunos_synced = []
        for aluno in Aluno.objects.filter(situacao__ativo=False, matricula__in=users):
            try:
                conf.sync_user(aluno.matricula)
                alunos_synced.append(aluno.matricula)
            except Exception:
                self.stdout.write(f'Erro ao sincronizar usuário {aluno.matricula}. Verifique o log para mais detalhes.')
                alunos_synced_errors.append(aluno.matricula)
                continue

        self.stdout.write(f'{len(alunos_synced)} usuários(alunos) sincronizados.')
        self.stdout.write(f'{len(alunos_synced_errors)} usuários(alunos) com erro durante sincronização.')

        servidor_synced_errors = []
        servidor_synced = []
        for servidor in Servidor.objects.filter(ativo=False, matricula__in=users):
            try:
                conf.sync_user(servidor.matricula)
                servidor_synced.append(servidor.matricula)
            except Exception:
                self.stdout.write(f'Erro ao sincronizar usuário {servidor.matricula}. Verifique o log para mais detalhes.')
                servidor_synced_errors.append(servidor.matricula)
                continue

        self.stdout.write(f'{len(servidor_synced)} usuários(servidor) sincronizados.')
        self.stdout.write(f'{len(servidor_synced_errors)} usuários(servidor) com erro durante sincronização.')

        prestador_synced_errors = []
        prestador_synced = []
        hoje = date.today()
        prestador_qs = PrestadorServico.objects.filter(matricula__in=users).annotate(
            ocupacao_ativa=Exists(OcupacaoPrestador.objects.filter(prestador=OuterRef('pk'), data_inicio__lte=hoje, data_fim__gte=hoje))
        )
        for prestador in prestador_qs.filter(ocupacao_ativa=False):
            try:
                conf.sync_user(prestador.matricula)
                prestador_synced.append(prestador.matricula)
            except Exception:
                self.stdout.write(f'Erro ao sincronizar usuário {prestador.matricula}. Verifique o log para mais detalhes.')
                prestador_synced_errors.append(prestador.matricula)
                continue

        self.stdout.write(f'{len(prestador_synced)} usuários(prestador) sincronizados.')
        self.stdout.write(f'{len(prestador_synced_errors)} usuários(prestador) com erro durante sincronização.')
