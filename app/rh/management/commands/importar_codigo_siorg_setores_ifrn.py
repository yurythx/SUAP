import datetime
from collections import Counter

from suds.client import Client

from djtools.management.commands import BaseCommandPlus
from rh.models import Setor


class Command(BaseCommandPlus):
    def print_list(self, list):
        for lista in list:
            self.stdout.write(str(lista))

    def handle(self, *args, **options):
        title = 'RH - Importação do Código SIORG dos Setores do IFRN'
        self.stdout.write('\n')
        self.stdout.write('- ' * len(title))
        self.stdout.write(title)
        self.stdout.write('- ' * len(title))

        self.stdout.write(
            'ATENÇÃO: Por conta de diferenças cadastrais entre os setores retornados pelo SIORG e os setores '
            'cadastrados no SUAP do IFRN, este command tem que ser avaliado antes de ser executado. Em tese ele irá '
            'atender vários outros órgãos, contudo caberá ao responsável pelo órgão fazer essa avaliação e implementar '
            'possíveis ajustes, atentendo assim as suas necessidades. Caso deseje, você pode executar apenas "SIMULAR" '
            'o processamento, sem que qualquer dado seja alterado no banco de dados.'
        )

        self.stdout.write('\n')
        executar_command = input('Informe o que deseja fazer? (SIMULAR/EXECUTAR/ABORTAR) ').strip().upper()

        executar_simulacao = executar_command == 'SIMULAR'
        executar_pra_valer = executar_command == 'EXECUTAR'
        if not executar_simulacao and not executar_pra_valer:
            self.stdout.write('\n')
            self.stdout.write('Processamento abortado.')
            return

        self.stdout.write('\n')
        self.stdout.write('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.stdout.write('\n')

        # Documentação do Novo Web Service SIORG Versão 1.1
        # http://www.dainf.ct.utfpr.edu.br/~caio/ws/
        # https://siorg.planejamento.gov.br/siorg-cidadao-webapp/pages/listar_orgaos_estruturas/listar_orgaos_estruturas.jsf#bxResultado
        url_service = 'http://estruturaorganizacional.dados.gov.br/ConsultarEstruturaWSImpl?wsdl'
        metodo = 'consultarEstruturaOrganizacionalCompleta'

        # https://softwarepublico.gov.br/archives/thread/sei-negocio/duvida-codigo-siorg-na-composicao-do-nup
        cliente_ws = None
        try:
            self.stdout.write('\n')
            self.stdout.write(f'Tentando consumir o webservice "{url_service}" oferecido pelo Governo Federal...')

            cliente_ws = Client(url_service)
            cliente_ws.options.location = url_service.split('?', maxsplit=1)[0]
            # list_of_methods = [method for method in client.wsdl.services[0].ports[0].methods]
            # for m in list_of_methods:
            #     print m

            self.stdout.write('Webservice carregado com sucesso.')
        except Exception as e:
            self.stdout.write(f'Erro ao consumir o webservices. Detalhes: {e}')
            return

        self.stdout.write('\n')

        # O parâmetro "codigoUnidade" é o código siorg. No caso do IFRN o código é o 439.
        # http://estruturaorganizacional.dados.gov.br/doc/orgao-entidade.xml
        # http://estruturaorganizacional.dados.gov.br/doc/unidade-organizacional/439
        # https://www.governoeletronico.gov.br/eixos-de-atuacao/governo/novo-siorg/documentos-e-arquivos/SIORG-NovoSiorg-v1.1-WebServices.pdf
        codigo_unidade_ifrn = 439

        self.stdout.write(f'Consumindo o método {metodo}...')
        self.stdout.write(f'Carregando a estrutura organizacional do IFRN (código {codigo_unidade_ifrn}) segundo o Governo Federal...')
        self.stdout.write(
            'Atenção: Cada órgão tem um código identificador junto ao Governo Federal. Para saber qual é o código '
            'da sua entidade, faça o seguinte: \n'
            '1 - Acesse http://estruturaorganizacional.dados.gov.br/doc/orgao-entidade.xml; \n'
            '2 - Faça uma busca textual pela sigla da sua entidade. Ex: IFRN, IFPB, IFPE; \n'
            '3 - Procure o atributo <codigoOrgaoEntidade>. Nele existirá uma URL com um número ao final. Esse número '
            'é o código da sua entidade.'
        )

        retorno_ws = cliente_ws.service.consultarEstruturaOrganizacionalCompleta(codigoUnidade=codigo_unidade_ifrn)
        log_sucesso_setores_codigo_siorg_mantido = []
        log_sucesso_setores_codigo_siorg_atualizado = []
        log_erro = []

        siglas_setores_governo_federal = []
        for u in retorno_ws.unidades:
            codigo_siorg = u.codigoUnidade
            sigla = u.sigla.replace('-', '/').lstrip()
            nome = u.nome.lstrip()

            siglas_setores_governo_federal.append(sigla)

            # Tentativa 1 - Pela sigla...
            # Somente os setores que tem funcionarios serão atualizados. Isso evita o problema dos setores duplicados,
            # que apresentam o mesma sigla, contudo um tem funcionários e o outro não. O que tem funcionários é o correto,
            # o que não tem será, em tese, excluído futuramente.
            suap_setor = Setor.objects.filter(sigla=sigla).exclude(funcionarios__isnull=True)

            # Tentativa 2 - Pela sigla do campus e pelo nome do setor...
            # Alguns setores do SUAP estão com a sigla diferente da sigla retornada pelo webservices, mas tem o mesmo nome.
            #
            # Exemplo:
            # WebServices >>> Coordenação de Pesquisa e Inovação (CPI/ZN - Código Siorg: 106960)
            # Suap >>> Coordenação de Pesquisa e Inovação (COPEIN/ZN)
            if not suap_setor.exists() and len(sigla.split('/')) > 1:
                sigla_campus = sigla.split('/')[-1]
                # print sigla_campus, nome
                suap_setor = Setor.objects.filter(uo__sigla=sigla_campus, nome=nome).exclude(funcionarios__isnull=True)

            if suap_setor.exists():
                if suap_setor.count() > 1:
                    log_erro.append(
                        f'{nome} ({sigla} - Código Siorg: {codigo_siorg}); Importação não realizada. Existem {suap_setor.count()} usando a mesma sigla.'
                    )
                else:
                    suap_setor = suap_setor[0]

                    if suap_setor.codigo_siorg:
                        if sigla == suap_setor.sigla:
                            log_sucesso_setores_codigo_siorg_mantido.append(f'{nome} ({sigla} - Código Siorg: {codigo_siorg})')
                        else:
                            log_sucesso_setores_codigo_siorg_mantido.append(
                                f'{nome} ({sigla} - Código Siorg: {codigo_siorg}); Sigla do Setor no SUAP: {suap_setor.sigla}'
                            )
                    else:
                        suap_setor.codigo_siorg = codigo_siorg
                        if executar_pra_valer:
                            suap_setor.save()

                        if sigla == suap_setor.sigla:
                            log_sucesso_setores_codigo_siorg_atualizado.append(f'{nome} ({sigla} - Código Siorg: {codigo_siorg})')
                        else:
                            log_sucesso_setores_codigo_siorg_atualizado.append(
                                f'{nome} ({sigla} - Código Siorg: {codigo_siorg}); Sigla do Setor no SUAP: {suap_setor.sigla}'
                            )

            else:
                log_erro.append(f'{nome} ({sigla} - Código Siorg: {codigo_siorg}); Setor não localizado no SUAP.')

        counter_siglas_setores_governo_federal = Counter(siglas_setores_governo_federal)
        log_alerta_setores_com_mesma_sigla_segundo_governo_federal = []
        for k, v in list(counter_siglas_setores_governo_federal.items()):
            if v > 1:
                log_alerta_setores_com_mesma_sigla_segundo_governo_federal.append(
                    f'O setor de sigla "{k}" possui {v} registro(s) na base de dados do Governo Federal.'
                )

        if len(log_alerta_setores_com_mesma_sigla_segundo_governo_federal) > 0:
            self.stdout.write('\n')
            self.stdout.write(
                f'ATENÇÃO: As unidades listadas abaixo, num total de {len(log_alerta_setores_com_mesma_sigla_segundo_governo_federal)} registro(s), apresentam a mesma sigla na '
                'base de dados do Governo Federal. Possivelmente são de campis diferentes, por isso se faz necessário '
                'averiguar caso a caso para definir o código SIORG correto no SUAP!'
            )
            self.print_list(log_alerta_setores_com_mesma_sigla_segundo_governo_federal)

        titulo_log_sucesso_setores_codigo_siorg_mantido = (
            f'Unidades Que Já Possuíam Código Siorg Definidos no SUAP: {len(log_sucesso_setores_codigo_siorg_mantido)} registro(s)'
        )
        self.stdout.write('\n')
        self.stdout.write('- ' * len(titulo_log_sucesso_setores_codigo_siorg_mantido))
        self.stdout.write(titulo_log_sucesso_setores_codigo_siorg_mantido)
        self.stdout.write('- ' * len(titulo_log_sucesso_setores_codigo_siorg_mantido))
        self.print_list(log_sucesso_setores_codigo_siorg_mantido)

        titulo_log_sucesso_setores_codigo_siorg_atualizado = (
            f'Unidades Que Tiveram o Código Siorg Atualizado com Sucesso no SUAP: {len(log_sucesso_setores_codigo_siorg_atualizado)} registro(s)'
        )
        self.stdout.write('\n')
        self.stdout.write('- ' * len(titulo_log_sucesso_setores_codigo_siorg_atualizado))
        self.stdout.write(titulo_log_sucesso_setores_codigo_siorg_atualizado)
        self.stdout.write('- ' * len(titulo_log_sucesso_setores_codigo_siorg_atualizado))
        self.print_list(log_sucesso_setores_codigo_siorg_atualizado)

        titulo_log_erro = f'Unidades Não Atualizadas Pois Não Existem Registros Equivalente no SUAP: {len(log_erro)} registro(s)'
        self.stdout.write('\n')
        self.stdout.write('- ' * len(titulo_log_erro))
        self.stdout.write(titulo_log_erro)
        self.stdout.write('- ' * len(titulo_log_erro))
        self.print_list(log_erro)

        self.stdout.write('\n')
        self.stdout.write('Processamento concluído com sucesso.')
        if not executar_pra_valer:
            self.stdout.write(
                'OBS: Este processamento foi apenas uma SIMULAÇÃO. Nada foi gravado no banco de dados. Para executar '
                'algo em definitivo, realize novamente o processamento e escolha a opção "EXECUTAR".'
            )

        self.stdout.write('\n')
        self.stdout.write('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
