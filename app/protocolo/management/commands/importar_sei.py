# Implementação baseada em https://gitlab.ufr.edu.br/protic/suap/-/blob/master/ufr/management/commands/importar_sei.py
import json
import traceback
from pprint import pformat

import mysql.connector
import tqdm
from django.conf import settings
from django.db import IntegrityError, transaction
from mysql.connector import Error

from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus
from djtools.utils import mask_cpf
from protocolo.models import Processo
from rh.models import PessoaFisica, Setor


class Command(BaseCommandPlus):
    def check(self, *args, **kwargs):
        pass

    def check_migrations(self, *args, **kwargs):
        pass

    def add_arguments(self, parser):
        parser.add_argument('--continuar', action='store_true', help='Continua a partir do último processo importado')

    @transaction.atomic
    def handle(self, *args, **options):
        if not Configuracao.get_valor_por_chave('protocolo', 'habilitar_importacao_sei'):
            return
        try:
            conexao = mysql.connector.connect(
                host=Configuracao.get_valor_por_chave('protocolo', 'sei_endereco_banco'),
                user=Configuracao.get_valor_por_chave('protocolo', 'sei_usuario_banco'),
                password=Configuracao.get_valor_por_chave('protocolo', 'sei_senha_banco'),
                database=Configuracao.get_valor_por_chave('protocolo', 'sei_nome_banco'),
            )

            if conexao.is_connected():
                continuar = options.get('continuar')
                setores_sei = Configuracao.get_valor_por_chave('protocolo', 'setores_sei')
                if setores_sei:
                    configuracao = json.loads(setores_sei)
                else:
                    sql = """
                        select
                            DISTINCT(SUBSTRING_INDEX(u.sigla, ' ', 1)) AS sigla
                        from protocolo p
                            inner join unidade u on u.id_unidade = p.id_unidade_geradora
                    """
                    cursor = conexao.cursor(dictionary=True)
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    siglas = set()
                    for row in rows:
                        siglas.add(row['sigla'])
                    cursor.close()
                    setores_presententes = set(Setor.objects.suap_ativos().filter(sigla__in=siglas).values_list('sigla', flat=True))
                    setores_ausentes = siglas - setores_presententes
                    configuracao = {}
                    for k in setores_presententes:
                        configuracao[k] = k
                    for k in setores_ausentes:
                        configuracao[k] = ''
                    Configuracao.objects.create(
                        app='protocolo',
                        chave='setores_sei',
                        valor=json.dumps(configuracao),
                        descricao='JSON contendo o mapeamento dos setores do SEI com o SUAP para fins de importação de processos. Execute o comando "python manage.py importar_sei" para que esse campo nessa inicializado.',
                    )

                self.stdout.write('========== MAPEAMENTO DE SETORES ==========')
                self.stdout.write(pformat(configuracao))
                self.stdout.write('========== X ==========')
                mapear = []
                for k, v in configuracao.items():
                    if v == '':
                        mapear.append(k)
                if mapear:
                    setores = ', '.join(mapear)
                    self.stderr.write(
                        f'Os setores SEI "{setores}" não estão mapeados no SUAP. Acesse {settings.SITE_URL}/comum/configuracao/protocolo/ e defina os valores correspondentes, ou informe "null" ou remova as chaves do dicionário.'
                    )
                    return

                cursor = conexao.cursor(dictionary=True)
                id_ultimo_processo_sei_suap = 0

                sql = """
                    select p.id_protocolo as id_protocolo_sei,
                        u.id_unidade as id_unidade_geradora_sei,
                        p.dta_geracao as data_cadastro,
                        LPAD(c.cpf,11,0) as cpf,
                        us.nome as nome,
                        c.email as email,
                        p.protocolo_formatado as numero_processo,
                        (CASE
                            WHEN p.descricao IS NOT NULL THEN UPPER(REPLACE(p.descricao,"'"," "))
                            ELSE 'NAO INFORMADO'
                        END) as assunto,
                        p.sta_nivel_acesso_local as nivel_acesso,
                        CONCAT(u.sigla,' - ', u.descricao) as setor_origem,
                        SUBSTRING_INDEX(u.sigla, ' ',1) as setor_origem_sigla
                    from protocolo p
                    inner join unidade u on u.id_unidade = p.id_unidade_geradora
                    inner join usuario us on us.id_usuario = p.id_usuario_gerador
                    inner join contato c on us.id_contato = c.id_contato
                    """

                if continuar:
                    sqlmax_id_protocolo = 'SELECT MAX(id_protocolo) as ultimo FROM protocolo WHERE sta_protocolo = "P" and sta_estado = 0'
                    cursor.execute(sqlmax_id_protocolo)

                    row = cursor.fetchone()
                    id_ultimo_processo_sei = row['ultimo'] or 0

                    if id_ultimo_processo_sei >= id_ultimo_processo_sei_suap:
                        sql += f' where p.id_protocolo > {id_ultimo_processo_sei_suap} '
                    else:
                        sql += ' where TRUE '
                sql += ' and  p.sta_protocolo = "P" and p.sta_estado in (0,1) and cpf IS NOT NULL order by id_protocolo '

                cursor.execute(sql)
                records = cursor.fetchall()

                self.stdout.write(f'Total de Processos: {cursor.rowcount}')
                count = 0

                for row in tqdm.tqdm(records):
                    if not configuracao.get(row['setor_origem_sigla']):
                        continue
                    numero_processo = row['numero_processo']
                    pessoa_fisica = PessoaFisica.objects.filter(cpf=mask_cpf(row['cpf'])).first()
                    setor_origem = Setor.objects.suap_ativos().filter(sigla=row['setor_origem_sigla']).first()

                    if not pessoa_fisica:
                        self.stderr.write(f'Erro na importação do processo: {numero_processo}. Pessoa {row["cpf"]} não encontrada no SUAP.')
                    elif not setor_origem:
                        self.stderr.write(f'Erro na importação do processo: {numero_processo}. Setor {row["setor_origem"]} não encontrada no SUAP.')
                    else:
                        count += 1

                        uo = setor_origem.uo
                        vinculo = pessoa_fisica.get_vinculo()

                        self.stdout.write(f'{row["numero_processo"]}, {row["assunto"]}, uo: {uo}, setor: {setor_origem}, vinculo: {vinculo}')

                        numero_processo = row['numero_processo']
                        try:
                            Processo.objects.get_or_create(
                                numero_processo=numero_processo,
                                defaults={
                                    'data_cadastro': row['data_cadastro'],
                                    'interessado_nome': row['nome'],
                                    'interessado_documento': row['cpf'],
                                    'interessado_pf': False,
                                    'interessado_email': row['email'],
                                    'assunto': row['assunto'],
                                    'tipo': 1,
                                    'status': 1,
                                    'setor_origem_id': setor_origem.id,
                                    'uo_id': uo.id,
                                    'vinculo_cadastro_id': vinculo.id,
                                },
                            )
                        except IntegrityError:
                            self.stderr.write(f'Erro na importação do processo: {numero_processo}')

                conexao.close()
                cursor.close()

                self.stdout.write('\rImportando processos do SEI: 100%\r\n')
                self.stdout.write(f'Nº processos importados do SEI: {count}')
            else:
                self.stderr.write('Sem Conexão...')

        except AttributeError as e:
            traceback.print_exc()
            self.stderr.write(f'Erro de configuração do SEI: {e}')
        except Error as e:
            self.stderr.write(f'Erro ao conectar à base de dados do SEI: {e}')
