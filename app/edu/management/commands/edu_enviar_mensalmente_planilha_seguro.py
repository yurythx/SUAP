from datetime import date, datetime, timedelta

import pandas as pd
from django.conf import settings

from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus
from djtools.templatetags.filters import format_
from djtools.utils import adicionar_mes, human_str, send_mail
from edu.models import AulaCampo, ConfiguracaoSeguro


# Ao fim de cada mês (último dia do mês) o sistema deverá fazer um planilhão e enviar para os e-mails cadastrados
# agrupados em um único arquivo com abas e cada aba deverá agrupar os embarques coincidentes e seus respectivos alunos
# e servidores.
class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        mes_desejado = None

        if args:
            if int(args[0]) > 1 and int(args[0]) <= 12:
                mes_desejado = int(args[0])
            else:
                self.stdout.write('O parâmetro foi rejeitado. Executando o comando considerando o mês atual.')

        qs_configuracoes_seguro = ConfiguracaoSeguro.objects.filter(ativa=True)

        if mes_desejado:
            primeiro_dia_mes = date(datetime.today().year, mes_desejado, 1)
            ultimo_dia_mes = adicionar_mes(date(datetime.today().year, mes_desejado, 1), 1) - timedelta(days=1)
        else:
            primeiro_dia_mes = date(datetime.today().year, datetime.today().month, 1)
            ultimo_dia_mes = adicionar_mes(date(datetime.today().year, datetime.today().month, 1), 1) - timedelta(days=1)

        for configuracao_seguro in qs_configuracoes_seguro:
            aulas_campo_mes = configuracao_seguro.aulacampo_set.filter(
                situacao=AulaCampo.SITUACAO_REALIZADA, data_partida__range=(primeiro_dia_mes, ultimo_dia_mes)
            ).order_by('data_partida')
            datas_aulas_campo = aulas_campo_mes.values_list('data_partida', 'data_chegada').distinct()

            if aulas_campo_mes.exists():
                subject = '[SUAP] Planilha de Participantes - Aula de Campo - {} a {}'.format(
                    primeiro_dia_mes.strftime('%d/%m'), ultimo_dia_mes.strftime('%d/%m')
                )
                body = """
                    Seguem em anexo as planilhas referentes às aulas de campo.
                """
                from_email = settings.DEFAULT_FROM_EMAIL
                to = configuracao_seguro.email_disparo_planilha.split(',')

                # Criando a planilha
                instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
                filename = '/tmp/{}_RelatorioMensal_{}_{}.xlsx'.format(instituicao, datetime.today().strftime('%Y'), primeiro_dia_mes.strftime('%m'))

                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    # Percorrendo as datas e gerando as abas das planilhas com dias de chegada e partida iguais
                    for data_partida, data_chegada in datas_aulas_campo:
                        aulas_campo_dia = aulas_campo_mes.filter(data_partida=data_partida, data_chegada=data_chegada)

                        # Nomeando a aba a partir da data de partida e chegada
                        if data_partida == data_chegada:
                            sheet_name = data_partida.strftime('%d_%m_%Y')
                        else:
                            sheet_name = '{}_a_{}'.format(data_partida.strftime('%d_%m_%Y'), data_chegada.strftime('%d_%m_%Y'))

                        rows_agrupada = []
                        count = 0

                        for aula_campo in aulas_campo_dia:
                            # Inserindo os Responsáveis
                            for responsavel in aula_campo.responsaveis.all():
                                count += 1
                                row = [
                                    count,
                                    format_(responsavel.matricula),
                                    format_(responsavel.cpf),
                                    format_(responsavel.nome),
                                    format_(responsavel.nascimento_data),
                                    format_(responsavel.sexo),
                                    format_('Servidor'),
                                ]
                                row.append(aula_campo.roteiro)
                                rows_agrupada.append(row)

                            # Inserindo os Alunos
                            for aluno in aula_campo.alunos.all():
                                count += 1
                                row = [
                                    count,
                                    format_(aluno.matricula),
                                    format_(aluno.pessoa_fisica.cpf),
                                    format_(aluno.pessoa_fisica.nome),
                                    format_(aluno.pessoa_fisica.nascimento_data),
                                    format_(aluno.pessoa_fisica.sexo),
                                    format_('Aluno'),
                                ]
                                row.append(aula_campo.roteiro)
                                rows_agrupada.append(row)

                        # Apply human_str formatting
                        formatted_rows = []
                        for row in rows_agrupada:
                            formatted_rows.append([human_str(i, encoding='utf-8', blank='-') for i in row])

                        df = pd.DataFrame(formatted_rows, columns=['#', 'Matrícula', 'CPF', 'Nome', 'Data de Nascimento', 'Sexo', 'Tipo', 'Roteiro'])
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

                # Salvando e Anexando a planilha
                files = [filename]

                # Enviando o email para a seguradora
                send_mail(subject, body, from_email, to, files=files)
