import zipfile
from datetime import datetime

import pandas as pd
from django.conf import settings

from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus
from djtools.templatetags.filters import format_
from djtools.utils import human_str, send_mail
from edu.models import AulaCampo, ConfiguracaoSeguro


# A cada dia às 1h o sistema deverá enviar a (s) planilha (s) de cada embarque separadas para os e-mails cadastrados.
class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs_configuracoes_seguro = ConfiguracaoSeguro.objects.filter(ativa=True, data_fim_contrato__gte=datetime.today())

        for configuracao_seguro in qs_configuracoes_seguro:
            aulas_campo_para_hoje = configuracao_seguro.aulacampo_set.filter(situacao=AulaCampo.SITUACAO_AGENDADA, data_partida=datetime.today())
            aula_campo_count = 0

            if aulas_campo_para_hoje.exists():
                subject = '[SUAP] Planilha de Participantes - Aula de Campo - {}'.format(datetime.today().strftime('%d/%m/%y'))
                body = """
                    Seguem em anexo as planilhas referentes às aulas de campo.
                """
                from_email = settings.DEFAULT_FROM_EMAIL
                to = configuracao_seguro.email_disparo_planilha.split(',')
                instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
                zip_filename = '/tmp/{}_Seguro_Aula_Campo_{}_{}_{}.zip'.format(
                    instituicao, datetime.today().strftime('%d'), datetime.today().strftime('%m'), datetime.today().strftime('%Y')
                )
                arquivo_zip = zipfile.ZipFile(zip_filename, mode='w')

                # Processando as aulas e gerando as planilhas
                for aula_campo in aulas_campo_para_hoje:
                    aula_campo_count += 1
                    self.stdout.write(
                        f'Gerando a planilha para a aula de campo "{aula_campo}" - {aula_campo.data_partida.strftime("%d%m%y")} a {aula_campo.data_chegada.strftime("%d%m%y")}.\n'
                    )

                    rows = []

                    # Inserindo os Responsáveis
                    count = 0

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
                        rows.append(row)

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
                        rows.append(row)

                    # Gerando e Anexando o arquivo.
                    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
                    filename = '/tmp/{}_aula_campo_{}_{}_{}.xlsx'.format(
                        instituicao, aula_campo.data_partida.strftime('%d%m%Y'), aula_campo.data_chegada.strftime('%d%m%Y'), aula_campo_count
                    )

                    formatted_rows = []
                    for row in rows:
                        formatted_rows.append([human_str(i, encoding='utf-8', blank='-') for i in row])

                    df = pd.DataFrame(formatted_rows, columns=['#', 'Matrícula', 'CPF', 'Nome', 'Data de Nascimento', 'Sexo', 'Tipo', 'Roteiro'])
                    df.to_excel(filename, sheet_name='planilha1', index=False)

                    arquivo_zip.write(filename)

                    # Alterando o status da aula de campo para REALIZADA
                    aula_campo.situacao = AulaCampo.SITUACAO_REALIZADA
                    aula_campo.save()

                # Enviando o email para a seguradora
                arquivo_zip.close()
                files = [zip_filename]
                send_mail(subject, body, from_email, to, files=files)
