from django.apps import apps
from django.db import transaction
from django.db.models import ExpressionWrapper, F, IntegerField
from django.db.models.expressions import Func
from django.db.models.functions import Abs
from django.db.models.query_utils import Q

from djtools.management.commands import BaseCommandPlus
from processo_eletronico.models import gerar_assinatura_tramite_senha


class ExtractMilliseconds(Func):
    template = 'EXTRACT(MILLISECONDS FROM %(expressions)s)::INTEGER'
    output_field = IntegerField()


# Exemplo de linha de comando para executar este command diretamente e ao mesmo tempo salvar o log. Obs: Execute na raiz dos fontes do SUAP.
# touch processo_eletronico_corrigir_despachos_violados.log && python manage.py processo_eletronico_corrigir_despachos_violados --opcao_command=2 --executar_command=S > processo_eletronico_corrigir_despachos_violados.log & tail -f processo_eletronico_corrigir_despachos_violados.log
class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        # Adiciona argumentos nomeados
        parser.add_argument('--opcao_command', type=str, help='Opcao de Execucao')
        parser.add_argument('--executar_command', type=str, help='Autorizacao para Executar')

    @transaction.atomic()
    def handle(self, *args, **options):
        title = 'Processo Eletrônico - Command que corrige os despachos dos tramites que apresentam a mensagem "Esse despacho foi violado"'
        self.stdout.write('')
        self.stdout.write('- ' * len(title))
        self.stdout.write(title)
        self.stdout.write('- ' * len(title))

        self.stdout.write('Esse command tem dois cenarios para execucao. Qual cenario deseja executar?')
        self.stdout.write('1 - Despachos violados em processos que estavam apensados (bug corrigido em 2018, na issue 3109).')
        self.stdout.write(
            '2 - Processos que misteriosamente o despacho apareceu violado e o motivo aparente eh a remocao em cascata da entidade Assinatura (bug corrigido em 2023 na issue 9824).'
        )
        self.stdout.write(
            '3 - Processos que apareceram com despachos com conteúdo textual em branco (string vazia) e constando como despachos violados.'
        )

        self.stdout.write('')
        opcao = options.get('opcao_command') or input('Qual a opcao? 1, 2 ou 3? ')
        opcao = opcao.strip()
        self.stdout.write(f'Opcao escolhida: {opcao}')

        if opcao == '1':
            self._corrigir_despachos_violados_cenario_1(args, options)
        elif opcao == '2':
            self._corrigir_despachos_violados_cenario_2(args, options)
        elif opcao == '3':
            self._corrigir_despachos_violados_cenario_3(args, options)
        else:
            raise Exception('Opcao invalida. Rode o comando novamente e faca uma escolha valida.')

    def _corrigir_despachos_violados_cenario_1(self, args, options):
        self.stdout.write(
            '\n\nCenario exemplo: Suponhamos que temos dois processos, A e B, sendo que B esta apensado a A. Ao tentar tramitar '
            'A com um despacho simples, o sistema primeiramente fazia o tramite de B (Despacho #100), nao realizava a assinatura do '
            'despacho desse tramite, daí em seguida realizava o tramite de A (Despacho #101) e assinava o despacho do tramite de A. '
            'Como resultado disso, o despacho do tramite de B ficava sem assinatura e assim gerava o erro "Esse despacho foi '
            'violado" quando o usuario clicava em "Visualizar Processo". '
        )

        self.stdout.write('')
        self.stdout.write(
            'O objetivo deste command eh varrer todos os tramites com despacho violado, ou seja, sem a respecitivas assinaturas '
            'e criar as assinaturas, com base na assinatura do tramite "irmao" do processo apensado. Obs: Este command funciona '
            'independentemente da quantidade de processos unidos por apensamento.'
        )

        executar_command = options.get('executar_command') or input('Deseja continuar? (S/n) ').strip().upper() == 'S'
        if not executar_command:
            self.stdout.write('')
            self.stdout.write('Processamento abortado.')
            return

        Tramite = apps.get_model('processo_eletronico', 'Tramite')
        ApensamentoProcesso = apps.get_model('processo_eletronico', 'ApensamentoProcesso')
        Assinatura = apps.get_model('documento_eletronico', 'Assinatura')
        AssinaturaTramite = apps.get_model('processo_eletronico', 'AssinaturaTramite')

        tramites_com_despachos_violados = Tramite.objects.filter(Q(despacho_corpo__isnull=False) & ~Q(despacho_corpo='')).filter(
            assinaturatramite__isnull=True
        )

        if tramites_com_despachos_violados.count() > 0:
            self.stdout.write(f'Foram encontrados {tramites_com_despachos_violados.count()} tramites com despachos violados')
        else:
            self.stdout.write('Nenhum tramite com despacho violado encontrado.')

        tramites_irmaos = []
        msg_erro = []
        for t in tramites_com_despachos_violados:
            # for t in tramites_com_despachos_violados[1:2]:
            # processos_apensados_pks = t.processo.get_processos_apensados().values_list('id', flat=True)
            apensamentos = t.processo.apensamentoprocesso_set.values_list('apensamento', flat=True)
            processos_irmaos_apensados = (
                ApensamentoProcesso.objects.filter(apensamento__in=apensamentos).exclude(processo=t.processo).values_list('processo', flat=True)
            )

            # Tentando localizar o tramite irmao, ou seja, aquele que tem as mesmas características do tramite em questao
            # e que tem a assinatura criada.
            tramite_irmao_assinado = Tramite.objects.filter(
                # data_hora_encaminhamento = t.data_hora_encaminhamento,
                # data_hora_recebimento = t.data_hora_recebimento,
                # despacho_cabecalho = t.despacho_cabecalho,
                despacho_corpo=t.despacho_corpo,
                # despacho_rodape = t.despacho_rodape,
                remetente_setor=t.remetente_setor,
                remetente_vinculo=t.remetente_vinculo,
                destinatario_setor=t.destinatario_setor,
                destinatario_vinculo=t.destinatario_vinculo,
                # Fazendo a busca somente nos tramites dos processos irmaos envolvidos nos apensamentos.
                processo__in=processos_irmaos_apensados,
                # Buscando o tramite que tem a assinatura. Isso porque o bug em questao pode envolver "n" processos.
                # Ex: Num caso de um apensamento envolvendo 4 processos, 3 deles tiveram o despachos nao assinados.
                assinaturatramite__isnull=False,
            )
            # self.stdout.write t.processo
            # self.stdout.write t
            # self.stdout.write tramite_irmao_assinado
            # self.stdout.write

            qtd_tramite_irmao = tramite_irmao_assinado.count()
            if qtd_tramite_irmao == 1:
                tramites_irmaos.append({'tramite_nao_assinado': t, 'tramite_irmao_assinado': tramite_irmao_assinado.first()})
            else:
                msg_erro.append(f'Total de tramites irmaos para o tramite {t}: {qtd_tramite_irmao}.')

        if msg_erro:
            raise Exception('Ha tramites para os quais nao foi possível obter o tramite irmao. Detalhes:\n' + '\n'.join(msg_erro))

        if tramites_irmaos:
            self.stdout.write('Iniciando a geraçao das assinaturas para os tramites com "despachos violados" (sem assinatura)...')

            i = 0
            for ti in tramites_irmaos:
                i += 1

                tramite_nao_assinado = ti['tramite_nao_assinado']
                tramite_irmao_assinado = ti['tramite_irmao_assinado']

                self.stdout.write('')
                self.stdout.write('=' * 100)
                self.stdout.write(
                    f'{i}º - Tramite nao assinado: #{tramite_nao_assinado.id} (Processo {tramite_nao_assinado.processo} - id: {tramite_nao_assinado.processo.id})'
                )
                self.stdout.write('=' * 100)
                self.stdout.write(
                    f'Tramite irmao assinado: #{tramite_irmao_assinado.id} (Processo {tramite_irmao_assinado.processo} - id: {tramite_irmao_assinado.processo.id}), '
                )
                self.stdout.write(f'- Hash do conteúdo: {tramite_irmao_assinado.hash_conteudo}')
                self.stdout.write(f'- Hmac da assinatura: {tramite_irmao_assinado.assinaturatramite.assinatura.hmac}')

                assinatura_base_para_copia = tramite_irmao_assinado.assinaturatramite.assinatura

                # Criando a assinatura para o tramite nao assinado.
                assinatura = Assinatura()
                assinatura.pessoa = assinatura_base_para_copia.pessoa
                assinatura.papel = assinatura_base_para_copia.papel
                assinatura.nome_papel = assinatura_base_para_copia.nome_papel
                assinatura.hmac = gerar_assinatura_tramite_senha(tramite_nao_assinado, assinatura_base_para_copia.vinculo)
                assinatura.save()
                # Forçando que a assinatura fique com o mesmo valor da assinatura base, uma vez que o atributo  "data_assinatura"
                # esta com o "auto_now_add", ou seja, data automatica apenas no ato da inserçao.
                assinatura.data_assinatura = assinatura_base_para_copia.data_assinatura
                assinatura.save()

                assinatura_tramite = AssinaturaTramite()
                assinatura_tramite.tramite = tramite_nao_assinado
                assinatura_tramite.assinatura = assinatura
                assinatura_tramite.save()

                self.stdout.write('')
                self.stdout.write(f'Assinatura do tramite #{tramite_nao_assinado.id} gerada com sucesso!')
                self.stdout.write(f'- Hash do conteúdo: {tramite_nao_assinado.hash_conteudo}')
                self.stdout.write(f'- Hmac da assinatura: {tramite_nao_assinado.assinaturatramite.assinatura.hmac}')
        self.stdout.write('')
        self.stdout.write('FIM')

    def _corrigir_despachos_violados_cenario_2(self, args, options):
        self.stdout.write(
            '\n\nCenario exemplo: Processo apareceu "do nada" com despacho "violado", e nao ha aparente motivo que justifique isso. '
            'Nesse cenario, a suspeita que levantamentos eh que a Assinatura associada ao tramite foi possivelmente removida '
            'por alguma operacao "cascade" existente. Para evitar isso, foi feito um ajuste no modelo Assinatura para nao permitir'
            'a sua remocao via cascade quando o Vinculo (comum) ou Papel (rh) for removido (issue 9824).'
        )

        self.stdout.write('')
        self.stdout.write(
            'O objetivo deste command eh varrer todos os tramites com despachos violados, ou seja, sem a respectivas assinaturas e recriar '
            'as assinaturas, com base na seguinte estrategia: \n'
            'A - Com base no historico de papeis do servidor e na data do tramite com despacho "violado", tentamos achar os papéis que o '
            'mesmo usava na epoca. \n'
            'B - Apos isso, no processo em que encontra-se o despacho "violado", fazemos uma busca por todos os trâmites assinados pelo '
            'usuário com esses respectivos papeis. Se conseguimos identificar um registro, então esse tramite assinado sera usado como '
            'referencia para a reconstrucao da assinatura do tramite com despacho "violado". Caso seja identificado mais de um, ai '
            'buscamos o tramite mais recente para usar como referencia. \n'
            'C - Caso nao seja identificado nenhum tramite assinado no processo que contem o despacho "violado", refazemos a mesma '
            'busca realizada em (B) soh que sem considerar esse processo, ou seja, buscamos por todos os tramites assinados pelo usuario '
            'com esses respectivos papeis, independente do processo. \n'
            'D - Caso nao seja identificado nenhum tramite assinado com tais papeis, para ser usado como referencia, entao criamos uma '
            'nova assinatura usando o papel mais antigo vigente na epoca para o usuario. \n'
            'E - Por fim, a assinatura so nao vai ser recriada caso nao seja identificado nenhum papel vigente, na epoca, para o usuario '
            'em questao, algo que em tese nao eh esperado. \n'
        )

        executar_command = options.get('executar_command') or input('Deseja continuar? (S/n) ').strip().upper() == 'S'
        if not executar_command:
            self.stdout.write('')
            self.stdout.write('Processamento abortado.')
            return

        Tramite = apps.get_model('processo_eletronico', 'Tramite')
        Assinatura = apps.get_model('documento_eletronico', 'Assinatura')
        AssinaturaTramite = apps.get_model('processo_eletronico', 'AssinaturaTramite')
        Papel = apps.get_model('rh', 'Papel')

        tramites_com_despachos_violados = (
            Tramite.objects.select_related('processo')
            .filter(Q(despacho_corpo__isnull=False) & ~Q(despacho_corpo=''))
            .filter(assinaturatramite__isnull=True)
        )

        qtd_total_tramites_com_despachos_violados = tramites_com_despachos_violados.count()
        qtd_total_tramites_com_despachos_violados_corrigidos = 0
        qtd_total_tramites_com_despachos_violados_nao_corrigidos = 0

        self.stdout.write('')
        if qtd_total_tramites_com_despachos_violados > 0:
            self.stdout.write(f'Foram encontrados {qtd_total_tramites_com_despachos_violados} tramites com despachos violados.')
        else:
            self.stdout.write('Nenhum tramite com despacho violado encontrado.')
            self.stdout.write('-------------------------------------------------------------------------------------------------------')
            self.stdout.write('FIM DO PROCESSAMENTO')
            self.stdout.write('-------------------------------------------------------------------------------------------------------')
            return

        for tramite_despacho_violado in tramites_com_despachos_violados:
            self.stdout.write('\n\n')
            self.stdout.write('-------------------------------------------------------------------------------------------------------')
            self.stdout.write(f'Processo: {tramite_despacho_violado.processo} (id: {tramite_despacho_violado.processo.id})')
            self.stdout.write(f'Tipo do Processo: {tramite_despacho_violado.processo.tipo_processo}')
            self.stdout.write(f'Trâmite com despacho "violado" (sem assinatura): {tramite_despacho_violado.id}')
            self.stdout.write(f'- Data de Encaminhamento: {tramite_despacho_violado.data_hora_encaminhamento.strftime("%d/%m/%Y %H:%M:%S")})')
            self.stdout.write(f'- Remetente: {tramite_despacho_violado.remetente_vinculo}')
            self.stdout.write('-------------------------------------------------------------------------------------------------------')

            papeis_vigentes_na_epoca = (
                Papel.objects.filter(
                    vinculo=tramite_despacho_violado.remetente_vinculo, data_inicio__lte=tramite_despacho_violado.data_hora_encaminhamento.date()
                )
                .filter(Q(data_fim__gte=tramite_despacho_violado.data_hora_encaminhamento.date()) | Q(data_fim__isnull=True))
                .order_by('data_inicio')
            )

            if papeis_vigentes_na_epoca.exists():
                self.stdout.write('Papéis vigentes na epoca: ')
                for papel in papeis_vigentes_na_epoca:
                    self.stdout.write(f'- {papel} (id: {papel.id}, data_inicio: {papel.data_inicio.strftime("%d/%m/%Y %H:%M:%S")})')

                # Num primeiro momento, com base no trâmite com despacho "violado"(sem assinatura), buscamos por trâmites assinados pela mesma pessoa, no mesmo processo, e usando os seus papéis vigentes na época.
                tramites_com_papeis_da_epoca = Tramite.objects.filter(
                    processo=tramite_despacho_violado.processo,
                    # Obs: Como Papel eh individual de cada pessoa, ou seja, nao existem 2 papeis para uma mesma pessoa, o filtro por remetente_vinculo nem seria necessario, mas o faco para ficar mais garantido!
                    remetente_vinculo=tramite_despacho_violado.remetente_vinculo,
                    assinaturatramite__assinatura__papel__in=papeis_vigentes_na_epoca,
                ).order_by('-data_hora_encaminhamento')

                # Se não existem tais trâmites citados acima, fazemos uma busca sem considerar o processo que contem o trâmite sem assinatura (despacho "violado").
                if not tramites_com_papeis_da_epoca.exists():
                    tramites_com_papeis_da_epoca = Tramite.objects.filter(
                        remetente_vinculo=tramite_despacho_violado.remetente_vinculo,
                        assinaturatramite__assinatura__papel__in=papeis_vigentes_na_epoca,
                    ).order_by('-data_hora_encaminhamento')

                # Instanciando os objetos. Neste ponto ja temos informacoes suficientes para criar a assinatura.
                assinatura = Assinatura()
                assinatura_tramite = AssinaturaTramite()

                if tramites_com_papeis_da_epoca.exists():
                    tramite_com_data_mais_proxima = self._get_tramite_com_data_encaminhamento_mais_proxima(
                        tramites_com_papeis_da_epoca, tramite_despacho_violado.data_hora_encaminhamento
                    )
                    assinatura_base_para_copia = tramite_com_data_mais_proxima.assinaturatramite.assinatura
                    msg_processo = (
                        'mesmo processo que contem o despacho "violado"'
                        if tramite_despacho_violado.processo == tramite_com_data_mais_proxima.processo
                        else 'outro processo'
                    )
                    self.stdout.write(
                        f'\nCom base nos papeis vigentes na epoca, o tramite assinado com data mais proxima eh o {tramite_com_data_mais_proxima.id}, no processo {tramite_com_data_mais_proxima.processo} ({msg_processo}), de {tramite_com_data_mais_proxima.data_hora_encaminhamento.strftime("%d/%m/%Y %H:%M:%S")}, contendo o papel {assinatura_base_para_copia.papel} (id: {assinatura_base_para_copia.papel.id}).'
                    )
                    self.stdout.write('Sera esse o tramite e papel usados como base para recriar a assinatura do tramite com despacho "violado".')

                    # Criando a assinatura para o tramite nao assinado.
                    assinatura.vinculo = assinatura_base_para_copia.vinculo
                    assinatura.cpf = assinatura_base_para_copia.cpf
                    assinatura.nome_papel = assinatura_base_para_copia.nome_papel
                    assinatura.papel = assinatura_base_para_copia.papel
                    assinatura.hmac = gerar_assinatura_tramite_senha(tramite_despacho_violado, assinatura_base_para_copia.vinculo)
                    assinatura.save()
                    # Forçando que a assinatura fique com o mesmo valor da assinatura referencia, uma vez que o atributo  "data_assinatura"
                    # esta com o "auto_now_add", ou seja, data automatica apenas no ato da inserçao.
                    assinatura.data_assinatura = tramite_despacho_violado.data_hora_encaminhamento
                    assinatura.save()

                    assinatura_tramite.tramite = tramite_despacho_violado
                    assinatura_tramite.assinatura = assinatura
                    assinatura_tramite.save()
                else:
                    self.stdout.write('\nNao foram encontrados tramites para o remetente em questao com os papeis usados por ele na epoca.')
                    # Se houver soh um papel, naturalmente serah essa papel. Se nao for, serah o primeiro com base na "data_inicio".
                    papel_mais_antigo_vigente_na_epoca = papeis_vigentes_na_epoca.first()
                    self.stdout.write(
                        f'Neste caso entao vamos recriar a assinatura usando o papel mais antigo vigente na epoca (total de {papeis_vigentes_na_epoca.count()}), que no caso serah o papel {papel_mais_antigo_vigente_na_epoca} (id: {papel_mais_antigo_vigente_na_epoca.id}).'
                    )

                    # Criando a assinatura para o tramite nao assinado.
                    assinatura.vinculo = papel_mais_antigo_vigente_na_epoca.vinculo
                    assinatura.cpf = papel_mais_antigo_vigente_na_epoca.vinculo.pessoa.pessoafisica.cpf
                    assinatura.nome_papel = papel_mais_antigo_vigente_na_epoca.descricao
                    assinatura.papel = papel_mais_antigo_vigente_na_epoca
                    assinatura.hmac = gerar_assinatura_tramite_senha(tramite_despacho_violado, papel_mais_antigo_vigente_na_epoca.vinculo)
                    assinatura.save()
                    # Forçando que a assinatura fique com o mesmo valor da assinatura referencia, uma vez que o atributo  "data_assinatura"
                    # esta com o "auto_now_add", ou seja, data automatica apenas no ato da inserçao.
                    assinatura.data_assinatura = tramite_despacho_violado.data_hora_encaminhamento
                    assinatura.save()

                    assinatura_tramite.tramite = tramite_despacho_violado
                    assinatura_tramite.assinatura = assinatura
                    assinatura_tramite.save()

                self.stdout.write('')
                self.stdout.write(f'Assinatura do Tramite (id) #{tramite_despacho_violado.id} gerada com sucesso!')
                self.stdout.write(f'- Hash do conteudo: {tramite_despacho_violado.hash_conteudo}')
                self.stdout.write(f'- Data de encaminhamento: {tramite_despacho_violado.data_hora_encaminhamento.strftime("%d/%m/%Y %H:%M:%S")}')
                self.stdout.write(f'- Hmac da assinatura: {assinatura.hmac}')
                self.stdout.write(f'- Data da assinatura: {assinatura.data_assinatura.strftime("%d/%m/%Y %H:%M:%S")}')
                self.stdout.write(f'- Assinatura (id): {assinatura.id}')
                self.stdout.write(f'- AssinaturaTramite (id): {assinatura_tramite.id}')
                self.stdout.write(f'- Assinatura Válida? {assinatura_tramite.validar_tramite()}')
                if assinatura_tramite.validar_tramite():
                    qtd_total_tramites_com_despachos_violados_corrigidos += 1
                else:
                    qtd_total_tramites_com_despachos_violados_nao_corrigidos += 1

            else:
                # Registrar arquivo de log com tramites que nao poderam ser corrigidos.
                self.stdout.write(
                    f'Nao foram encontrados papeis vigentes para {tramite_despacho_violado.remetente_vinculo} na data de {tramite_despacho_violado.data_hora_encaminhamento} (data do tramite com despacho "violado").'
                )
                self.stdout.write('Neste caso a assinatura do tramite com despacho "violado" nao podera ser refeita.')
                qtd_total_tramites_com_despachos_violados_nao_corrigidos += 1

        self.stdout.write('\n\n')
        self.stdout.write('-------------------------------------------------------------------------------------------------------')
        self.stdout.write(f'Total de tramites com despachos "violados": {qtd_total_tramites_com_despachos_violados}')
        self.stdout.write(f'Total de tramites com despachos "violados" corrigidos: {qtd_total_tramites_com_despachos_violados_corrigidos}')
        self.stdout.write(f'Total de tramites com despachos "violados" nao corrigidos: {qtd_total_tramites_com_despachos_violados_nao_corrigidos}')
        self.stdout.write('-------------------------------------------------------------------------------------------------------')
        self.stdout.write('FIM DO PROCESSAMENTO')
        self.stdout.write('-------------------------------------------------------------------------------------------------------')

    def _corrigir_despachos_violados_cenario_3(self, args, options):
        self.stdout.write(
            '\n\nCenario exemplo: Processo apareceu com despacho com conteúdo textual em branco (string vazia) e constando como "violado".'
        )

        self.stdout.write('')
        self.stdout.write(
            'O objetivo deste command eh varrer todos os trâmites com despacho com conteúdo textual em branco (string vazia), constando como "violado" e '
            'criar as assinaturas, com base na seguinte estrategia: \n'
            'A - Com base no historico de papeis do servidor e na data do tramite com despacho "violado", tentamos achar os papéis que o '
            'mesmo usava na epoca. \n'
            'B - Apos isso, no processo em que encontra-se o despacho "violado", fazemos uma busca por todos os trâmites assinados pelo '
            'usuário com esses respectivos papeis. Se conseguimos identificar um registro, então esse tramite assinado sera usado como '
            'referencia para a reconstrucao da assinatura do tramite com despacho "violado". Caso seja identificado mais de um, ai '
            'buscamos o tramite mais recente para usar como referencia. \n'
            'C - Caso nao seja identificado nenhum tramite assinado no processo que contem o despacho "violado", refazemos a mesma '
            'busca realizada em (B) soh que sem considerar esse processo, ou seja, buscamos por todos os tramites assinados pelo usuario '
            'com esses respectivos papeis, independente do processo. \n'
            'D - Caso nao seja identificado nenhum tramite assinado com tais papeis, para ser usado como referencia, entao criamos uma '
            'nova assinatura usando o papel mais antigo vigente na epoca para o usuario. \n'
            'E - Por fim, a assinatura so nao vai ser recriada caso nao seja identificado nenhum papel vigente, na epoca, para o usuario '
            'em questao, algo que em tese nao eh esperado. \n'
        )

        executar_command = options.get('executar_command') or input('Deseja continuar? (S/n) ').strip().upper() == 'S'
        if not executar_command:
            self.stdout.write('')
            self.stdout.write('Processamento abortado.')
            return

        Tramite = apps.get_model('processo_eletronico', 'Tramite')
        Assinatura = apps.get_model('documento_eletronico', 'Assinatura')
        AssinaturaTramite = apps.get_model('processo_eletronico', 'AssinaturaTramite')
        Papel = apps.get_model('rh', 'Papel')

        tramites_com_despachos_violados = Tramite.objects.select_related('processo').filter(despacho_corpo='', assinaturatramite__isnull=True)

        qtd_total_tramites_com_despachos_violados = tramites_com_despachos_violados.count()
        qtd_total_tramites_com_despachos_violados_corrigidos = 0
        qtd_total_tramites_com_despachos_violados_nao_corrigidos = 0

        self.stdout.write('')
        if qtd_total_tramites_com_despachos_violados > 0:
            self.stdout.write(f'Foram encontrados {qtd_total_tramites_com_despachos_violados} tramites com despachos violados.')
        else:
            self.stdout.write('Nenhum tramite com despacho violado encontrado.')
            self.stdout.write('-------------------------------------------------------------------------------------------------------')
            self.stdout.write('FIM DO PROCESSAMENTO')
            self.stdout.write('-------------------------------------------------------------------------------------------------------')
            return

        for tramite_despacho_violado in tramites_com_despachos_violados:
            self.stdout.write('\n\n')
            self.stdout.write('-------------------------------------------------------------------------------------------------------')
            self.stdout.write(f'Processo: {tramite_despacho_violado.processo} (id: {tramite_despacho_violado.processo.id})')
            self.stdout.write(f'Tipo do Processo: {tramite_despacho_violado.processo.tipo_processo}')
            self.stdout.write(f'Trâmite com despacho "violado" (sem assinatura): {tramite_despacho_violado.id}')
            self.stdout.write(f'- Data de Encaminhamento: {tramite_despacho_violado.data_hora_encaminhamento.strftime("%d/%m/%Y %H:%M:%S")})')
            self.stdout.write(f'- Remetente: {tramite_despacho_violado.remetente_vinculo}')
            self.stdout.write('-------------------------------------------------------------------------------------------------------')

            papeis_vigentes_na_epoca = (
                Papel.objects.filter(
                    vinculo=tramite_despacho_violado.remetente_vinculo, data_inicio__lte=tramite_despacho_violado.data_hora_encaminhamento.date()
                )
                .filter(Q(data_fim__gte=tramite_despacho_violado.data_hora_encaminhamento.date()) | Q(data_fim__isnull=True))
                .order_by('data_inicio')
            )

            if papeis_vigentes_na_epoca.exists():
                self.stdout.write('Papéis vigentes na epoca: ')
                for papel in papeis_vigentes_na_epoca:
                    self.stdout.write(f'- {papel} (id: {papel.id}, data_inicio: {papel.data_inicio.strftime("%d/%m/%Y %H:%M:%S")})')

                # Num primeiro momento, com base no trâmite com despacho "violado"(sem assinatura), buscamos por trâmites assinados pela mesma pessoa, no mesmo processo, e usando os seus papéis vigentes na época.
                tramites_com_papeis_da_epoca = Tramite.objects.filter(
                    processo=tramite_despacho_violado.processo,
                    # Obs: Como Papel eh individual de cada pessoa, ou seja, nao existem 2 papeis para uma mesma pessoa, o filtro por remetente_vinculo nem seria necessario, mas o faco para ficar mais garantido!
                    remetente_vinculo=tramite_despacho_violado.remetente_vinculo,
                    assinaturatramite__assinatura__papel__in=papeis_vigentes_na_epoca,
                ).order_by('-data_hora_encaminhamento')

                # Se não existem tais trâmites citados acima, fazemos uma busca sem considerar o processo que contem o trâmite sem assinatura (despacho "violado").
                if not tramites_com_papeis_da_epoca.exists():
                    tramites_com_papeis_da_epoca = Tramite.objects.filter(
                        remetente_vinculo=tramite_despacho_violado.remetente_vinculo,
                        assinaturatramite__assinatura__papel__in=papeis_vigentes_na_epoca,
                    ).order_by('-data_hora_encaminhamento')

                # Instanciando os objetos. Neste ponto ja temos informacoes suficientes para criar a assinatura.
                assinatura = Assinatura()
                assinatura_tramite = AssinaturaTramite()

                if tramites_com_papeis_da_epoca.exists():
                    tramite_com_data_mais_proxima = self._get_tramite_com_data_encaminhamento_mais_proxima(
                        tramites_com_papeis_da_epoca, tramite_despacho_violado.data_hora_encaminhamento
                    )
                    assinatura_base_para_copia = tramite_com_data_mais_proxima.assinaturatramite.assinatura
                    msg_processo = (
                        'mesmo processo que contem o despacho "violado"'
                        if tramite_despacho_violado.processo == tramite_com_data_mais_proxima.processo
                        else 'outro processo'
                    )
                    self.stdout.write(
                        f'\nCom base nos papeis vigentes na epoca, o tramite assinado com data mais proxima eh o {tramite_com_data_mais_proxima.id}, no processo {tramite_com_data_mais_proxima.processo} ({msg_processo}), de {tramite_com_data_mais_proxima.data_hora_encaminhamento.strftime("%d/%m/%Y %H:%M:%S")}, contendo o papel {assinatura_base_para_copia.papel} (id: {assinatura_base_para_copia.papel.id}).'
                    )
                    self.stdout.write('Sera esse o tramite e papel usados como base para recriar a assinatura do tramite com despacho "violado".')

                    # Criando a assinatura para o tramite nao assinado.
                    assinatura.vinculo = assinatura_base_para_copia.vinculo
                    assinatura.cpf = assinatura_base_para_copia.cpf
                    assinatura.nome_papel = assinatura_base_para_copia.nome_papel
                    assinatura.papel = assinatura_base_para_copia.papel
                    assinatura.hmac = gerar_assinatura_tramite_senha(tramite_despacho_violado, assinatura_base_para_copia.vinculo)
                    assinatura.save()
                    # Forçando que a assinatura fique com o mesmo valor da assinatura referencia, uma vez que o atributo  "data_assinatura"
                    # esta com o "auto_now_add", ou seja, data automatica apenas no ato da inserçao.
                    assinatura.data_assinatura = tramite_despacho_violado.data_hora_encaminhamento
                    assinatura.save()

                    assinatura_tramite.tramite = tramite_despacho_violado
                    assinatura_tramite.assinatura = assinatura
                    assinatura_tramite.save()
                else:
                    self.stdout.write('\nNao foram encontrados tramites para o remetente em questao com os papeis usados por ele na epoca.')
                    # Se houver soh um papel, naturalmente serah essa papel. Se nao for, serah o primeiro com base na "data_inicio".
                    papel_mais_antigo_vigente_na_epoca = papeis_vigentes_na_epoca.first()
                    self.stdout.write(
                        f'Neste caso entao vamos recriar a assinatura usando o papel mais antigo vigente na epoca (total de {papeis_vigentes_na_epoca.count()}), que no caso serah o papel {papel_mais_antigo_vigente_na_epoca} (id: {papel_mais_antigo_vigente_na_epoca.id}).'
                    )

                    # Criando a assinatura para o tramite nao assinado.
                    assinatura.vinculo = papel_mais_antigo_vigente_na_epoca.vinculo
                    assinatura.cpf = papel_mais_antigo_vigente_na_epoca.vinculo.pessoa.pessoafisica.cpf
                    assinatura.nome_papel = papel_mais_antigo_vigente_na_epoca.descricao
                    assinatura.papel = papel_mais_antigo_vigente_na_epoca
                    assinatura.hmac = gerar_assinatura_tramite_senha(tramite_despacho_violado, papel_mais_antigo_vigente_na_epoca.vinculo)
                    assinatura.save()
                    # Forçando que a assinatura fique com o mesmo valor da assinatura referencia, uma vez que o atributo  "data_assinatura"
                    # esta com o "auto_now_add", ou seja, data automatica apenas no ato da inserçao.
                    assinatura.data_assinatura = tramite_despacho_violado.data_hora_encaminhamento
                    assinatura.save()

                    assinatura_tramite.tramite = tramite_despacho_violado
                    assinatura_tramite.assinatura = assinatura
                    assinatura_tramite.save()

                self.stdout.write('')
                self.stdout.write(f'Assinatura do Tramite (id) #{tramite_despacho_violado.id} gerada com sucesso!')
                self.stdout.write(f'- Hash do conteudo: {tramite_despacho_violado.hash_conteudo}')
                self.stdout.write(f'- Data de encaminhamento: {tramite_despacho_violado.data_hora_encaminhamento.strftime("%d/%m/%Y %H:%M:%S")}')
                self.stdout.write(f'- Hmac da assinatura: {assinatura.hmac}')
                self.stdout.write(f'- Data da assinatura: {assinatura.data_assinatura.strftime("%d/%m/%Y %H:%M:%S")}')
                self.stdout.write(f'- Assinatura (id): {assinatura.id}')
                self.stdout.write(f'- AssinaturaTramite (id): {assinatura_tramite.id}')
                self.stdout.write(f'- Assinatura Válida? {assinatura_tramite.validar_tramite()}')
                if assinatura_tramite.validar_tramite():
                    qtd_total_tramites_com_despachos_violados_corrigidos += 1
                else:
                    qtd_total_tramites_com_despachos_violados_nao_corrigidos += 1

            else:
                # Registrar arquivo de log com tramites que nao poderam ser corrigidos.
                self.stdout.write(
                    f'Nao foram encontrados papeis vigentes para {tramite_despacho_violado.remetente_vinculo} na data de {tramite_despacho_violado.data_hora_encaminhamento} (data do tramite com despacho "violado").'
                )
                self.stdout.write('Neste caso a assinatura do tramite com despacho "violado" nao podera ser refeita.')
                qtd_total_tramites_com_despachos_violados_nao_corrigidos += 1

        self.stdout.write('\n\n')
        self.stdout.write('-------------------------------------------------------------------------------------------------------')
        self.stdout.write(f'Total de tramites com despachos "violados": {qtd_total_tramites_com_despachos_violados}')
        self.stdout.write(f'Total de tramites com despachos "violados" corrigidos: {qtd_total_tramites_com_despachos_violados_corrigidos}')
        self.stdout.write(f'Total de tramites com despachos "violados" nao corrigidos: {qtd_total_tramites_com_despachos_violados_nao_corrigidos}')
        self.stdout.write('-------------------------------------------------------------------------------------------------------')
        self.stdout.write('FIM DO PROCESSAMENTO')
        self.stdout.write('-------------------------------------------------------------------------------------------------------')

    def _get_tramite_com_data_encaminhamento_mais_proxima(self, tramites_com_mesmos_papeis, data_hora_encaminhamento):
        if tramites_com_mesmos_papeis.count() == 1:
            return tramites_com_mesmos_papeis.first()

        # Calcule a diferença absoluta, em millesegundos, entre a data_hora_encaminhamento de cada trâmite e a data_hora_encaminhamento do trâmite com despacho "violado".
        tramites_com_mesmos_papeis = tramites_com_mesmos_papeis.annotate(
            data_hora_encaminhamento_diff=ExpressionWrapper(
                Abs(ExtractMilliseconds(F('data_hora_encaminhamento') - data_hora_encaminhamento)), output_field=IntegerField()
            )
        )
        # Obtenha o registro com a menor diferença (ou seja, a data_hora_encaminhamento mais próxima)
        tramite_mais_proximo = tramites_com_mesmos_papeis.order_by('data_hora_encaminhamento_diff').first()
        return tramite_mais_proximo
