import ldap
import tqdm

from comum.exceptions import LoginException
from djtools.management.commands import BaseCommandPlus
from ldap_backend.models import LdapConf


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument(
            '--base-dn',
            action='store',
            dest='base_dn',
            default='',
            type=str,
            help='Informe o DN base para a busca.',
        )
        parser.add_argument(
            '--excluir',
            action='store_true',
            help='Informe se deseja excluir grupos e OUs vazios.',
        )
        parser.add_argument(
            '--no-groups',
            action='store_true',
            dest='no_groups',
            default=False,
            help='Informe se não deseja buscar grupos vazios.',
        )
        parser.add_argument(
            '--no-ous',
            action='store_true',
            dest='no_ous',
            default=False,
            help='Informe se não deseja buscar OUs vazias.',
        )

    def buscar_grupos_vazios(self, conf, base_dn):
        """
        Busca por grupos que não possuem membros.
        Procura por objectClass 'groupOfNames' ou 'posixGroup' sem o atributo 'member'.
        """
        # Filtro para encontrar grupos que não possuem o atributo 'member' ou 'memberUid'
        # Isso indica que o grupo está vazio.
        search_filter = '(&(objectClass=group)(!(member=*))(!(memberUid=*)))'
        try:
            self.stdout.write(' Procurando por grupos vazios...')
            # A busca é feita em toda a sub-árvore a partir do base_dn
            results = conf.search_objects(base=base_dn, filterstr=search_filter, attrlist=['dn'])
            # Retornamos apenas a lista de DNs (Distinguished Names)
            grupos_vazios = [obj['dn'] for obj in results]
            grupos_vazios = sorted(grupos_vazios, key=lambda key: key.split(',')[::-1], reverse=True)
            return grupos_vazios
        except ldap.NO_SUCH_OBJECT, LoginException:
            self.stderr.write(f"Opa! A base de busca '{base_dn}' não foi encontrada ao procurar grupos.")
            return []
        except ldap.LDAPError as e:
            self.stderr.write(f'Um erro de LDAP aconteceu ao buscar grupos: {e}')
            return []

    def buscar_ous_vazias(self, conf, base_dn):
        """
        Busca por Unidades Organizacionais (OUs) que não contêm nenhum objeto filho.
        """
        ous_vazias = []
        search_filter_ou = '(objectClass=organizationalUnit)'
        conn = conf.bind()

        try:
            self.stdout.write(' Procurando por todas as Unidades Organizacionais (OUs)...')
            # Primeiro, encontramos todas as OUs
            all_ous = conf.search_objects(base=base_dn, filterstr=search_filter_ou, attrlist=['dn'])

            self.stdout.write(f' Encontrei {len(all_ous)} OUs. Agora vou verificar uma por uma se estão vazias...')

            for ou in tqdm.tqdm(all_ous):
                # Para cada OU encontrada, fazemos uma nova busca dentro dela.
                # O escopo é ONELEVEL, para procurar apenas por filhos diretos.
                # Se essa busca não retornar nada, a OU está vazia!
                ou_dn = ou['dn']
                try:
                    lc = ldap.controls.SimplePagedResultsControl(True, size=1, cookie='')
                    children = conn.search_ext_s(
                        ou_dn,
                        ldap.SCOPE_ONELEVEL,
                        '(objectClass=*)',
                        ['dn'],
                        sizelimit=1,
                        serverctrls=[lc],
                    )
                    if not children:
                        ous_vazias.append(ou_dn)
                except ldap.LDAPError as e:
                    self.stderr.write(f"  -> Não consegui verificar a OU '{ou_dn}'. Erro: {e}")
            ous_vazias = sorted(ous_vazias, key=lambda key: key.split(',')[::-1], reverse=True)
            return ous_vazias
        except ldap.NO_SUCH_OBJECT, LoginException:
            # Isso não deve acontecer se a conexão funcionou, mas é bom previnir
            self.stderr.write(f"Opa! A base de busca '{base_dn}' não foi encontrada ao procurar OUs.")
            return []
        except ldap.LDAPError as e:
            self.stderr.write(f'Um erro de LDAP aconteceu ao buscar OUs: {e}')
            return []

    def excluir(self, conf, dns):
        """
        Exclui um objeto LDAP pelo seu DN.
        """
        conn = conf.bind()
        try:
            # Ordenar por número de componentes (vírgulas), do mais profundo para o menos profundo
            dn_para_processar = sorted(dns, key=lambda dn: dn.count(','), reverse=True)

            self.stdout.write('\n!!!!!!!!!!!!! MODO DE EXCLUSÃO ATIVADO !!!!!!!!!!!!!')
            self.stdout.write(' Os seguintes itens serão EXCLUÍDOS PERMANENTEMENTE:\n')
            for dn in dn_para_processar:
                self.stdout.write(f'  - {dn}')

            confirmacao = 'não'
            confirmacao = input("\n Você tem CERTEZA ABSOLUTA que deseja excluir esses itens? (digite 'sim' para confirmar): ")

            if confirmacao.lower() == 'sim':
                self.stdout.write('\n Ok, começando a exclusão...')
                sucesso = 0
                falha = 0
                for dn in dn_para_processar:
                    try:
                        conn.delete_s(dn)
                        self.stdout.write(f"  [SUCESSO] O objeto '{dn}' foi excluído.")
                        sucesso += 1
                    except ldap.LDAPError as e:
                        self.stderr.write(f"  [FALHA] Não foi possível excluir '{dn}'. Erro: {e}")
                        falha += 1
                self.stdout.write(f'\n Limpeza finalizada! {sucesso} objeto(s) excluído(s), {falha} falha(s).')
            else:
                self.stderr.write('\n Exclusão cancelada. Nenhum objeto foi alterado.')

        except ldap.INVALID_CREDENTIALS:
            self.stderr.write('\n Oh não! As credenciais estão erradas. Verifique o DN e a senha, por favor. :(')
        except ldap.LDAPError as e:
            self.stderr.write(f'\n Aconteceu um erro inesperado de LDAP: {e}')
        except Exception as e:
            self.stderr.write(f'\n Um erro geral aconteceu: {e}')
        finally:
            # É super importante sempre fechar a conexão no final!
            if conn:
                conn.unbind_s()

    def handle(self, *args, **options):
        conf = LdapConf.get_active()
        base_dn = options.get('base_dn', conf.base)
        excluir = options.get('excluir', False)
        no_groups = options.get('no_groups', False)
        no_ous = options.get('no_ous', False)
        self.stdout.write('\n !!!!!!!!!!!!! ATENÇÃO !!!!!!!!!!!!!')
        self.stdout.write(
            ' Este comando não irá excluir todos os grupos e OUs vazios, pois uma OU que contêm outras OUs não será considerada vazia, mesmo que todas as OUs filhas não tenha nenhum objeto.'
        )
        self.stdout.write(' Ele irá apenas excluir grupos e OUs que não possuem nenhum objeto filho, ou seja, que estão completamente vazias.')
        self.stdout.write(' Para garantir que você excluiu todos os OUs e grupos vazios, execute este comando diversas vezes.')
        self.stdout.write(
            ' Use com cautela! Este comando pode excluir grupos e OUs que você não queria excluir, então é importante verificar os resultados antes de confirmar a exclusão.'
        )

        if no_groups and no_ous:
            self.stdout.write('\n Nenhuma busca será realizada, pois ambas as opções --no-groups e --no-ous estão ativas.')
            return

        self.stdout.write(f'\n Iniciando limpeza LDAP na base DN: {base_dn}')

        if no_groups:
            grupos_vazios = []
        else:
            self.stdout.write('\n Iniciando a busca por grupos vazios...')
            grupos_vazios = self.buscar_grupos_vazios(conf, base_dn)

        if no_ous:
            ous_vazias = []
        else:
            self.stdout.write('\n Iniciando a busca por OUs vazias...')
            ous_vazias = self.buscar_ous_vazias(conf, base_dn)

        if not ous_vazias and not grupos_vazios:
            self.stdout.write('\n Nenhum grupo ou OU vazia encontrada. Nada a fazer!')
            return
        self.stdout.write(f'\n Encontrei {len(ous_vazias)} OUs vazias e {len(grupos_vazios)} grupos vazios.')
        if not excluir:
            self.stdout.write(' Listando todos os itens encontrados:\n')
            if ous_vazias:
                self.stdout.write(' OUs vazias:')
                for ou in ous_vazias:
                    self.stdout.write(f'  - {ou}')
            if grupos_vazios:
                self.stdout.write('\n Grupos vazios:')
                for grupo in grupos_vazios:
                    self.stdout.write(f'  - {grupo}')
        if excluir:
            self.stdout.write('\n Iniciando o processo de exclusão...')
            self.excluir(conf, ous_vazias + grupos_vazios)
