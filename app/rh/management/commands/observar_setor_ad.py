import datetime

import ldap
from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_ldap_conf
from suap import nomenclatura


class Command(BaseCommandPlus):
    def print_list(self, list):
        for lista in list:
            self.stdout.write(lista)

    def exibir_dados_setor_unificado(self, su_setores):
        self.stdout.write(' - Setores INATIVOS no Suap...')
        if not su_setores['inativos']:
            self.stdout.write('   - Nenhum')
        else:
            for s in su_setores['inativos']:
                self.stdout.write(f'   - Sigla: {s.sigla}   {nomenclatura.campus}: {s.uo}   Id: {s.id}')

        self.stdout.write(' - Setores ATIVOS no Suap...')
        if not su_setores['ativos']:
            self.stdout.write('   - Nenhum')
        else:
            for s in su_setores['ativos']:
                self.stdout.write(f'   - Sigla: {s.sigla}   {nomenclatura.campus}: {s.uo}   Id: {s.id}')

    def handle(self, *args, **options):
        title = 'RH - Observar Setores no AD (Active Directory)'
        self.stdout.write('\n')
        self.stdout.write('- ' * len(title))
        self.stdout.write(title)
        self.stdout.write('- ' * len(title))

        self.stdout.write(
            'O objetivo deste command eh simplesmente varrer os setores "suap", verificar se ha o cadastro do respectivo\n'
            'setor no AD e se esse cadastro esta consistente ou se ha alguma problema. Obs: Toda a operacao eh somente\n'
            'leitura. Nada ha escrita no AD ou no SUAP!'
        )

        self.stdout.write('\n')
        self.stdout.write('\n')
        self.stdout.write('Inicio do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.stdout.write('\n')

        ldapconf = get_ldap_conf()
        if not ldapconf:
            raise Exception('Nao foi encontrada nenhuma configuracao de AD no banco de dados do SUAP.')

        ad_url = ldapconf.uri
        ad_user = ldapconf.who
        ad_pass = ldapconf.cred
        base_address = ldapconf.base
        atts_to_read = ['*']

        self.stdout.write(f'Dados do AD: \n - {ad_url}\n - {ad_user}\n - {ad_pass}\n - {base_address}')
        self.stdout.write('Tentando conexao com o AD...')
        connect = ldap.initialize(ad_url)
        connect.set_option(ldap.OPT_NETWORK_TIMEOUT, 60.0)
        connect.set_option(ldap.OPT_TIMEOUT, 60.0)
        connect.set_option(ldap.OPT_REFERRALS, 0)
        connect.simple_bind_s(who=ad_user, cred=ad_pass)
        self.stdout.write('Conexao realizada com sucesso!')
        self.stdout.write('\n')

        Setor = apps.get_model('rh', 'Setor')
        setores = Setor.objects.suap().all().order_by('uo__sigla', 'sigla')

        # "setores_unificados" eh um dicionario de dicionarios, que tem como chave a sigla do setor. Seu objetivo eh
        # agrupar todas as Uos do SUAP que possuam a mesma sigla, visando facilitar posteriormente a busca no AD e a
        # analise que busca alguma inconsistencia no AD.
        setores_unificados = {}
        for setor in setores:
            setor_unificado = setores_unificados.get(setor.sigla)
            if not setor_unificado:
                setor_unificado = {}
                setor_unificado['inativos'] = []
                setor_unificado['inativos_id'] = []
                setor_unificado['ativos'] = []
                setor_unificado['ativos_id'] = []

            if setor.excluido:
                setor_unificado['inativos'].append(setor)
                setor_unificado['inativos_id'].append(setor.id)
            else:
                setor_unificado['ativos'].append(setor)
                setor_unificado['ativos_id'].append(setor.id)

            setores_unificados[setor.sigla] = setor_unificado

        # Uma vez que os setores do SUAP com a mesma sigla foram unificados...
        for su_sigla, su_setores in list(setores_unificados.items()):
            self.stdout.write(f'Carregando dados do setor de sigla "{su_sigla}" no AD...')
            # O ajuste abaixo na sigla do setor eh necessario porque no SUAP o cadastro geralmente inclue uma '/' para
            # separar a sigla do setor da sigla do campus, so que no AD ao inves da '/' usas-se '-'.
            search_param = 'OU={}'.format(su_sigla.replace('/', '-'))
            ad_rows = connect.search_s(base_address, ldap.SCOPE_SUBTREE, search_param, atts_to_read)

            msg_erro = ''
            # Se não há registro no AD...
            if not ad_rows:
                if su_setores['ativos_id']:
                    msg_erro += 'PROBLEMA: O setor nao existe no AD mas esta como ativo no SUAP.\n'
            # Caso contrário...
            else:
                for ad_row in ad_rows:
                    # dn eh a chave primaria do objeto no AD.
                    # dn = ad_row[0]
                    data = ad_row[1]
                    setor_id_ad = int(data.get('adminDescription', [-1])[0])

                    if setor_id_ad in su_setores['inativos_id']:
                        msg_erro += 'PROBLEMA: O setor do AD estah como INATIVO no SUAP.\n'
                    elif setor_id_ad not in su_setores['ativos_id']:
                        msg_erro += 'PROBLEMA: O setor do AD nao estah como ATIVO no SUAP.\n'

                    if len(su_setores['ativos_id']) > 1:
                        msg_erro = 'PROBLEMA: O setor do AD tem mais de uma UO ATIVA no SUAP.\n'

            # Se ha algum erro, ele será exibido.
            if msg_erro:
                self.stderr.write(msg_erro)
                self.exibir_dados_setor_unificado(su_setores)

                # Se o setor existe no AD, seus atributos tambem serao exibidos.
                if ad_rows:
                    self.stderr.write(' - Setor no AD...')
                    for key, value in list(data.items()):
                        self.stderr.write(f'   - {key}: {value}')
            else:
                self.stdout.write('OK - O cadastro do setor no AD esta correto.')

            self.stdout.write('\n')

        self.stdout.write('Processamento concluido com sucesso.')
        self.stdout.write('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
