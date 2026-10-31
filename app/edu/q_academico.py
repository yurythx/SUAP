import copy
import datetime
import logging
from decimal import Decimal
from sys import stdout

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import QuerySet
from django.db.models.aggregates import Max

from comum.models import Ano, Configuracao, UnidadeFederativa, User
from comum.utils import get_sigla_reitoria
from djtools.utils import cache_queryset, normalizar_nome_proprio
from edu.models import (
    Aluno,
    Cidade,
    Componente,
    ConfiguracaoLivro,
    CursoCampus,
    Diretoria,
    Estado,
    FormaIngresso,
    MatriculaDiario,
    MatriculaDiarioResumida,
    MatriculaPeriodo,
    Modalidade,
    OrgaoEmissorRg,
    RegistroEmissaoDiploma,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turno,
)
from edu.models.cursos import EquivalenciaComponenteQAcademico, Matriz
from edu.models.polos import Polo
from edu.models.utils import HistoricoImportacao
from rh.deduplicacao.entrada import Politica, aplicar_politica
from rh.models import PessoaFisica, UnidadeOrganizacional

logger = logging.getLogger(__name__)


class DAO:
    def __init__(self):
        self.ESTADOS = {
            'AC': 12,
            'AL': 27,
            'AM': 13,
            'AP': 16,
            'BA': 29,
            'CE': 23,
            'DF': 53,
            'ES': 32,
            'GO': 52,
            'MA': 21,
            'MG': 31,
            'MS': 50,
            'MT': 51,
            'PA': 15,
            'PB': 25,
            'PE': 26,
            'PI': 22,
            'PR': 41,
            'RJ': 33,
            'RN': 24,
            'RO': 11,
            'RR': 14,
            'RS': 43,
            'SC': 42,
            'SE': 28,
            'SP': 35,
            'TO': 17,
        }
        for key in self.ESTADOS:
            self.ESTADOS[key] = Estado.objects.get(pk=self.ESTADOS[key])
        self.connection = None

        self.SIGLAS_UF = UnidadeFederativa.objects.values_list('sigla', flat=True)
        self.dt_ultimo_historico_atualizacao = HistoricoImportacao.objects.aggregate(Max('data'))['data__max']

    def get_connection(self):
        """Conexão com SQL Server"""
        import pymssql

        db_host = Configuracao.get_valor_por_chave('edu', 'academico_endereco_banco')
        db_user = Configuracao.get_valor_por_chave('edu', 'academico_usuario_banco')
        db_password = Configuracao.get_valor_por_chave('edu', 'academico_senha_banco')
        db_name = Configuracao.get_valor_por_chave('edu', 'academico_nome_banco_padrao')

        return pymssql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            as_dict=True,
            tds_version='7.0',
        )

    def importar_cursos_campus(self, verbose=True):
        sql = """
                SELECT
                    c.cod_curso AS codigo,
                    c.desc_curso AS nome,
                    c.cod_curso_matricula AS cod_turma,
                    c.cod_instituicao AS instituicao,
                    c.cod_curso_habilitado AS curso_habilitado,
                    c.desc_historico AS descricao_historico,
                    c.autorizacao AS autorizacao,
                    c.reconhecimento AS reconhecimento,
                    (select top 1 m.n_periodos from matrizes_curriculares m where m.cod_curso = c.cod_curso order by cod_matriz_curricular desc) AS numero_periodos,
                    c.dt_inicio AS data_inicio,
                    c.exige_enade AS exige_enade
                FROM cursos c
                LEFT JOIN turnos t ON c.COD_TURNO = t.COD_TURNO
                ORDER BY c.desc_curso
        """
        cur = self.get_connection().cursor()
        cur.execute(sql)

        row = cur.fetchone()
        while row:
            curso_campus = {
                'codigo': row['codigo'],
                'cod_turma': row['cod_turma'],
                'nome': row['nome'],
                'instituicao': row['instituicao'],
                'curso_habilitado': row['curso_habilitado'],
                'numero_periodos': row['numero_periodos'],
                'descricao_historico': row['descricao_historico'],
                'autorizacao': row['autorizacao'],
                'reconhecimento': row['reconhecimento'],
                'data_inicio': row['data_inicio'],
                'exige_enade': row['exige_enade'],
            }

            qs = CursoCampus.objects.filter(codigo_academico=curso_campus['codigo'])

            modalidade = None

            if curso_campus['nome'].lower().find('aperfeiçoamento') == 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.APERFEICOAMENTO)
            elif curso_campus['nome'].lower().find('especialização') == 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.ESPECIALIZACAO)
            elif curso_campus['nome'].lower().find('proeja') >= 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.PROEJA_FIC_FUNDAMENTAL)
            elif curso_campus['nome'].lower().find('fic') == 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.FIC)
            elif curso_campus['nome'].lower().find('licenciatura') == 0 or curso_campus['nome'].lower().find('segunda') == 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.LICENCIATURA)
            elif curso_campus['nome'].lower().find('mestrado') == 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.MESTRADO)
            elif curso_campus['nome'].lower().find('tecnologia') == 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.TECNOLOGIA)
            elif curso_campus['nome'].lower().find('subsequente') >= 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.SUBSEQUENTE)
            elif curso_campus['nome'].lower().find('concomitante') >= 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.CONCOMITANTE)
            elif (
                curso_campus['nome'].lower().find('cnico') >= 0
                and curso_campus['nome'].lower().find('integrad') >= 0
                and curso_campus['nome'].lower().find('eja') >= 0
            ):
                modalidade = Modalidade.objects.get(pk=Modalidade.INTEGRADO_EJA)
            elif (
                curso_campus['nome'].lower().find('cnico') >= 0
                and curso_campus['nome'].lower().find('integrad') >= 0
                and curso_campus['nome'].lower().find('eja') == -1
            ):
                modalidade = Modalidade.objects.get(pk=Modalidade.INTEGRADO)
            elif curso_campus['nome'].lower().find('ensino') >= 0 and curso_campus['nome'].lower().find('médio') >= 0:
                modalidade = Modalidade.objects.get(pk=Modalidade.ENSINO_MEDIO)

            d = {
                'codigo_academico': curso_campus['codigo'],
                'descricao': curso_campus['nome'],
                'descricao_historico': curso_campus['descricao_historico'],
                'ativo': False,
                'codigo': curso_campus['cod_turma'],
                # resolucao_criacao=curso_campus['autorizacao'],
                # reconhecimento_texto=curso_campus['reconhecimento'],
                'data_inicio': curso_campus['data_inicio'],
                'exige_enade': curso_campus['exige_enade'],
            }
            # a modalidade pode ter sido informada no SUAP
            if modalidade is not None:
                d.update(modalidade=modalidade)

            if qs.exists():
                # cursos ativos não podem ser alterados
                if not qs[0].ativo:
                    qs.update(**d)
            else:
                CursoCampus.objects.create(**d)
            row = cur.fetchone()

        cur.close()
        if verbose:
            stdout.write('\rImportando cursos no campus: 100%\r\n')

    def importar_situacoes_matricula(self, verbose=True):
        sql = """
        SELECT valor,
            descricao AS nome
        FROM situacoes_tabelas
        WHERE nome_tabela = 'MATRICULAS'
          AND nome_coluna = 'SIT_MATRICULA'
        """
        cur = self.get_connection().cursor()
        cur.execute(sql)

        row = cur.fetchone()
        while row:
            situacao = {'codigo': row['valor'], 'nome': row['nome']}
            qs = SituacaoMatricula.objects.filter(codigo_academico=situacao['codigo']) | SituacaoMatricula.objects.filter(
                descricao=situacao['nome'], codigo_academico__isnull=True
            )
            d = {'codigo_academico': situacao['codigo'], 'descricao': situacao['nome']}
            if qs.exists():
                qs.update(**d)
            else:
                SituacaoMatricula.objects.create(**d)
            row = cur.fetchone()
        cur.close()
        if verbose:
            stdout.write('\rImportando situacoes de matricula: 100%\r\n')

    def importar_situacoes_matricula_periodo(self, verbose=True):
        sql = """
        SELECT valor,
            descricao AS nome
        FROM situacoes_tabelas
        WHERE nome_tabela = 'MATRICULAS_PERIODOS'
          AND nome_coluna = 'SIT_MATRICULA_PERIODO'
        """
        cur = self.get_connection().cursor()
        cur.execute(sql)

        row = cur.fetchone()
        while row:
            situacao = {'codigo': row['valor'], 'nome': row['nome']}
            qs = SituacaoMatriculaPeriodo.objects.filter(codigo_academico=situacao['codigo']) | SituacaoMatriculaPeriodo.objects.filter(
                descricao=situacao['nome'], codigo_academico__isnull=True
            )
            d = {'codigo_academico': situacao['codigo'], 'descricao': situacao['nome']}
            if qs.exists():
                qs.update(**d)
            else:
                SituacaoMatriculaPeriodo.objects.create(**d)
            row = cur.fetchone()

        cur.close()
        if verbose:
            stdout.write('\rImportando situacoes de matricula no periodo: 100%\r\n')

    def importar_polos_ead(self, verbose=True):
        sql = """
        SELECT
            COD_EAD_POLO as codigo_academico,
            DESC_EAD_POLO as descricao,
            SIGLA_POLO as sigla
        FROM ead_polos
        """
        cur = self.get_connection().cursor()
        cur.execute(sql)

        row = cur.fetchone()
        while row:
            codigo_academico = row['codigo_academico']
            qs = Polo.objects.filter(codigo_academico=codigo_academico)
            d = {'codigo_academico': codigo_academico, 'descricao': row['descricao'], 'sigla': row['sigla']}
            if qs.exists():
                qs.update(**d)
            else:
                Polo.objects.create(**d)
            row = cur.fetchone()
        cur.close()
        if verbose:
            stdout.write('\rImportando polos do EAD: 100%\r\n')

    def get_contador_aluno(self, prefixo_matricula=None):
        sql = """
            SELECT count(1) as c FROM matriculas m
            inner join alunos a on m.cod_aluno = a.cod_aluno
            inner join sincronizacao s on m.cod_matricula = s.cod_matricula
            """

        if prefixo_matricula:
            if prefixo_matricula != 'full':
                if "'" in prefixo_matricula:
                    sql += f' AND m.matricula IN ({prefixo_matricula})'
                else:
                    sql += " AND m.matricula LIKE '" + prefixo_matricula + "%'"
        else:
            sql += f" WHERE s.dt_atualizacao >= '{self.dt_ultimo_historico_atualizacao}' "

        cur = self.get_connection().cursor()
        cur.execute(sql)
        quantidade = cur.fetchone()['c']
        cur.close()
        return quantidade

    def alunos_existem(self, lista_matricula):
        if not lista_matricula:
            return []

        if isinstance(lista_matricula, str):
            lista_matricula = [lista_matricula]

        placeholders = ','.join(['?' for _ in lista_matricula])
        sql = f'SELECT v.matricula FROM vw_matriculas v WHERE v.matricula IN ({placeholders})'

        cur = self.get_connection().cursor()
        cur.execute(sql, lista_matricula)
        result = [row['matricula'] for row in cur.fetchall()]
        cur.close()
        return result

    def importar_alunos(self, prefixo_matricula: str | None = None, verbose: bool = True, forcar_importacao: bool = False) -> tuple[int, int]:
        sql = """
        SELECT
            a.cod_pessoa AS codigo_academico_pf,
            a.renda_per_capita AS renda_per_capita,
            a.mae_falecida as mae_falecida,
            a.pai_falecido as pai_falecido,
            p.endereco + ', ' + p.bairro+ ', ' +c.desc_cidade+ '/' +c.estado as endereco,
            p.nome_pessoa AS pf_nome,
            p.identidade_numero as pf_identidade_numero,
            p.estado_identidade as pf_identidade_estado,
            p.cod_orgao_expedidor as pf_identidade_orgao_expedidor,
            p.identidade_data as pf_identidade_data,
            p.cpf AS pf_cpf,
            p.email AS email_qacademico,
            p.sexo AS pf_sexo,
            p.dt_nascimento AS pf_nascimento_data,
            p.nome_pai AS pf_nome_pai,
            p.nome_mae AS pf_nome_mae,
            p.endereco as logradouro,
            p.numero as numero,
            p.complemento as complemento,
            p.cep as cep,
            p.tel_residencial as residencial,
            p.celular as celular,
            p.titulo_ele as titulo,
            p.secao_ele as secao,
            p.zona_ele as zona,
            p.data_titulo_ele as data_titulo,
            p.reservista as reservista,
            p.ano_reservista as ano_reservista,
            p.regiao_militar as regiao_reservista,
            p.csm as serie_reservista,
            p.n_termo_certidao_civil as numero_certidao,
            p.folha_certidao_civil as folha_certidao,
            p.livro_certidao_civil as livro_certidao,
            p.dt_emissao_certidao_civil as data_certidao,
            p.matricula_certidao_civil as matricula_certidao,
            p.cod_nacionalidade as nacionalidade,
            m.sit_matricula AS situacao_codigo,
            m.cod_curso AS curso_codigo,
            m.cod_matricula AS codigo_academico,
            m.matricula,
            m.dt_matricula AS data_matricula,
            m.__dt_conclusao_curso AS dt_conclusao_curso,
            m.dt_colacao_grau AS data_colacao_grau,
            m.periodo_atual AS periodo_atual,
            m.ano_letivo_ini AS ano_letivo_inicial,
            m.periodo_letivo_ini AS periodo_letivo_inicial,
            m.coeficiente_rendimento AS indice_rendimento,
            m.cod_ead_polo as codigo_polo,
            ano_let_prev_conclusao,
            t.DESC_TURNO AS turno,
            fi.DESC_FORMA_INGRESSO AS forma_ingresso,
            m.__DIPLOMA_DATA as data_diploma
        FROM matriculas m
        inner join alunos a on m.cod_aluno = a.cod_aluno
        inner join pessoas p on a.cod_pessoa = p.cod_pessoa
        inner join sincronizacao s on m.cod_matricula = s.cod_matricula
        left join cidades c on p.cod_cidade = c.cod_cidade
        left join TURNOS t on m.COD_TURNO = t.COD_TURNO
        left join FORMAS_INGRESSO fi on m.COD_FORMA_INGRESSO = fi.COD_FORMA_INGRESSO
        WHERE m.cod_matricula = (select top 1 cod_matricula from vw_matriculas v where v.matricula = m.matricula)
        """
        sql += self._filtro_importacao_alunos(prefixo_matricula)

        alunos_qtd = self.get_contador_aluno(prefixo_matricula=prefixo_matricula)

        cur = self.get_connection().cursor()
        cur.execute(sql)

        criados = 0
        atualizados = 0

        caches = {
            'cursos': cache_queryset(CursoCampus.objects.all(), 'codigo_academico'),
            'situacoes': cache_queryset(SituacaoMatricula.objects.all(), 'codigo_academico'),
            'anos': cache_queryset(Ano.objects.all(), 'ano'),
        }

        percentual = 0
        for contador, m in enumerate(cur.fetchall(), start=1):
            matricula = m['matricula']
            # ignorando alunos integralizados
            qs1 = Aluno.objects.filter(matricula=matricula, matriz__isnull=False)
            qs2 = Aluno.objects.filter(matricula=matricula, registroemissaodiploma__sistema='SUAP', registroemissaodiploma__cancelado=False)
            if (not qs1.exists() and not qs2.exists()) or forcar_importacao:
                criado = self._importar_aluno(m, caches)
                if criado is not None:
                    criados += criado
                    atualizados += not criado

            if verbose:
                percentual = self._exibir_progresso_alunos(contador, alunos_qtd, percentual)

        if verbose:
            stdout.write('\rImportando alunos: 100%\r\n')

        return criados, atualizados

    def _filtro_importacao_alunos(self, prefixo_matricula: str | None) -> str:
        if not prefixo_matricula:
            return f" AND s.dt_atualizacao >= '{self.dt_ultimo_historico_atualizacao}' "
        if prefixo_matricula == 'full':
            return ''
        if "'" in prefixo_matricula:
            return f' AND m.matricula IN ({prefixo_matricula})'
        return " AND m.matricula LIKE '" + prefixo_matricula + "%'"

    @staticmethod
    def _exibir_progresso_alunos(contador: int, alunos_qtd: int, percentual: str | int) -> str | int:
        percentual_atual = f'{contador / float(alunos_qtd) * 100:.0f}'
        if percentual_atual != percentual:
            stdout.write(f'Importando alunos: {percentual_atual}%%\r')
            stdout.flush()
        return percentual_atual

    @staticmethod
    def _localizar_aluno(codigo_academico: object, matricula: str) -> tuple[QuerySet, int | None, int | None]:
        """O aluno já importado (pelo código acadêmico ou pela matrícula) e a pessoa física dele."""
        aluno_qs = Aluno.objects.filter(codigo_academico=codigo_academico)
        if not aluno_qs.exists():
            aluno_qs = Aluno.objects.filter(matricula=matricula)
        if aluno_qs.exists():
            aluno_pf_id, aluno_id = aluno_qs.values_list('pessoa_fisica_id', 'id')[0]
            return aluno_qs, aluno_pf_id, aluno_id
        aluno_pf_id = PessoaFisica.objects.filter(vinculo__user__username=matricula).values_list('id', flat=True).first()
        return aluno_qs, aluno_pf_id, None

    def _salvar_pessoa_fisica_aluno(self, m: dict, aluno_pf_id: int | None) -> int | None:
        """Grava a pessoa física do aluno; None quando o documento é recusado (registrado no log)."""
        m['pf_identidade_estado'] = m['pf_identidade_estado'] or ''
        pf_args = {
            'nome': normalizar_nome_proprio(m['pf_nome']),
            'cpf': m['pf_cpf'] or '',
            'nascimento_data': m['pf_nascimento_data'],
            'sexo': m['pf_sexo'],
            'rg': m['pf_identidade_numero'],
            'rg_uf': m['pf_identidade_estado'].upper() in self.SIGLAS_UF and m['pf_identidade_estado'] or '',
            'rg_orgao': m['pf_identidade_orgao_expedidor'] == 'SSP' and OrgaoEmissorRg.objects.get(pk=10).nome or None,
            'rg_data': m['pf_identidade_data'],
        }
        try:
            if aluno_pf_id:
                # o próprio cadastro do aluno: o acadêmico é a fonte dele
                pessoa_fisica = PessoaFisica.objects.get(pk=aluno_pf_id)
                aplicar_politica(pessoa_fisica, pf_args, Politica.AUTORITATIVA, preservar_documento=True)
                pessoa_fisica.save()
                return aluno_pf_id
            return PessoaFisica.objects.obter_ou_criar(pf_args, Politica.CAUTELOSA)[0].id
        except ValidationError as erro:
            logger.warning(f'Aluno {m["matricula"]} não importado: {erro.messages}')
            return None

    def _dependencias_aluno(self, m: dict) -> dict:
        """Turno, forma de ingresso e polo do aluno (a forma de ingresso desconhecida é criada inativa)."""
        qs_turno = Turno.objects.filter(descricao=m['turno'])
        forma_ingresso = FormaIngresso.objects.filter(descricao=m['forma_ingresso']).first()
        if forma_ingresso is None:
            forma_ingresso = FormaIngresso.objects.create(descricao=m['forma_ingresso'], ativo=False)
        polo = m['codigo_polo'] and Polo.objects.filter(codigo_academico=m['codigo_polo']).first() or None
        return {'turno': qs_turno.first(), 'forma_ingresso': forma_ingresso, 'polo': polo}

    @staticmethod
    def _email_qacademico(m: dict) -> str:
        try:
            email_qacademico = m['email_qacademico'][:75]
            validate_email(email_qacademico)
        except ValidationError, TypeError:
            return ''
        return email_qacademico

    def _importar_aluno(self, m: dict, caches: dict) -> bool | None:
        """Cria (True) ou atualiza (False) o aluno da linha do acadêmico; None quando a pessoa física foi recusada."""
        aluno_qs, aluno_pf_id, aluno_id = self._localizar_aluno(m['codigo_academico'], m['matricula'])
        pf_id = self._salvar_pessoa_fisica_aluno(m, aluno_pf_id)
        if pf_id is None:
            return None

        aluno_args = {
            'pessoa_fisica': pf_id,
            'situacao': caches['situacoes'][str(m['situacao_codigo'])].id,
            'curso_campus': caches['cursos'][str(m['curso_codigo'])].id,
            'codigo_academico': m['codigo_academico'],
            'codigo_academico_pf': m['codigo_academico_pf'],
            'matricula': m['matricula'],
            'data_matricula': m['data_matricula'],
            'data_colacao_grau': m['data_colacao_grau'],
            'dt_conclusao_curso': m['dt_conclusao_curso'],
            'periodo_atual': m['periodo_atual'],
            'ano_letivo': caches['anos'][str(m['ano_letivo_inicial'])].id,
            'periodo_letivo': m['periodo_letivo_inicial'],
            'ira': m['indice_rendimento'],
            'ano_let_prev_conclusao': m['ano_let_prev_conclusao'],
            'renda_per_capita': m['renda_per_capita'],
            'numero_rg': m['pf_identidade_numero'],
            'uf_emissao_rg': self.ESTADOS.get(m['pf_identidade_estado']),
            'orgao_emissao_rg': m['pf_identidade_orgao_expedidor'] == 'SSP' and OrgaoEmissorRg.objects.get(pk=10) or None,
            'data_emissao_rg': m['pf_identidade_data'],
            'nome_mae': m['pf_nome_mae'],
            'nome_pai': m['pf_nome_pai'],
            'pai_falecido': m['pai_falecido'] or False,
            'mae_falecida': m['mae_falecida'] or False,
            'logradouro': m['logradouro'],
            'numero': m['numero'],
            'complemento': m['complemento'],
            'cep': m['cep'],
            'telefone_principal': m['celular'] or m['residencial'],
            'telefone_secundario': m['residencial'] or m['celular'],
            'numero_titulo_eleitor': m['titulo'],
            'zona_titulo_eleitor': m['zona'],
            'secao': m['secao'],
            'data_emissao_titulo_eleitor': m['data_titulo'],
            'numero_carteira_reservista': m['reservista'],
            'regiao_carteira_reservista': m['regiao_reservista'],
            'serie_carteira_reservista': m['serie_reservista'],
            'ano_carteira_reservista': m['ano_reservista'],
            'numero_certidao': m['numero_certidao'],
            'folha_certidao': m['folha_certidao'],
            'livro_certidao': m['livro_certidao'],
            'data_emissao_certidao': m['data_certidao'],
            'matricula_certidao': m['matricula_certidao'],
            'nacionalidade': m['nacionalidade'] == 'BR' and 'Brasileira' or '',
            'data_expedicao_diploma': m['data_diploma'],
            'alterado_em': datetime.datetime.now(),
        }
        aluno_args.update(self._dependencias_aluno(m), email_qacademico=self._email_qacademico(m))

        if aluno_pf_id and aluno_id:
            # Caso o aluno já tenha sido migrado para o Suap, sua situação não pode ser alterada localmente
            if aluno_args['situacao'] == SituacaoMatricula.TRANSFERIDO_SUAP:
                aluno_args.pop('situacao')
            aluno_qs.update(**aluno_args)
            return False

        aluno_args['situacao_id'] = aluno_args.pop('situacao')
        aluno_args['curso_campus_id'] = aluno_args.pop('curso_campus')
        aluno_args['ano_letivo_id'] = aluno_args.pop('ano_letivo')
        aluno_args['pessoa_fisica_id'] = aluno_args.pop('pessoa_fisica')
        novo_aluno = Aluno.objects.create(**aluno_args)
        novo_aluno.definir_ano_let_prev_conclusao()
        novo_aluno.save()
        return True

    def get_contador_matricula_periodo(self, prefixo_matricula=None):
        sql = """
            SELECT count(1) as c FROM matriculas_periodos mp
            inner join sincronizacao s on s.cod_matricula = mp.cod_matricula
            """

        if prefixo_matricula:
            if prefixo_matricula != 'full':
                if "'" in prefixo_matricula:
                    sql += f' inner join matriculas m on mp.cod_matricula = m.cod_matricula where m.matricula IN ({prefixo_matricula})'
                else:
                    sql += " inner join matriculas m on mp.cod_matricula = m.cod_matricula where m.matricula LIKE '" + prefixo_matricula + "%'"
        else:
            sql += f" where s.dt_atualizacao >= '{self.dt_ultimo_historico_atualizacao}' "

        cur = self.get_connection().cursor()
        cur.execute(sql)
        quantidade = cur.fetchone()['c']
        cur.close()
        return quantidade

    def importar_data_colacao_grau(self):
        sql = """
        SELECT matricula, dt_colacao_grau from matriculas where dt_colacao_grau is not null;
        """
        c1 = Aluno.objects.filter(data_colacao_grau__isnull=True).count()
        cur = self.get_connection().cursor()
        cur.execute(sql)
        for row in cur.fetchall():
            Aluno.objects.filter(matricula=row['matricula']).update(data_colacao_grau=row['dt_colacao_grau'])
        c2 = Aluno.objects.filter(data_colacao_grau__isnull=True).count()
        logger.info(f'{c1 - c2} alunos atualizados')
        cur.close()

    def importar_matriculas_periodo(self, prefixo_matricula=None, verbose=True, forcar_importacao=False):
        sql = """
        select
            m.matricula,
            mp.cod_matricula,
            mp.ano_let,
            mp.periodo_let,
            mp.periodo,
            mp.cod_turma,
            mp.sit_matricula_periodo,
            mp.concluiu,
            mp.nota,

            (select top 1 ma.COD_MATRICULA_ATIVIDADE from AC_MATRICULAS_ATIVIDADES ma
             inner join AC_ATIVIDADES a on (ma.COD_ATIVIDADE = a.COD_ATIVIDADE and
                                            a.ANO_LET = mp.ANO_LET and
                                            a.PERIODO_LET = mp.PERIODO_LET)
             where mp.COD_MATRICULA = ma.COD_MATRICULA) as cursou_atividade,

            (select top 1 mac.COD_ATIVIDADE_COMPLEMENTAR from MATRICULAS_ATIVIDADES_COMPLEMENTARES mac
             inner join ATIVIDADES_COMPLEMENTARES ac on (mac.COD_ATIVIDADE_COMPLEMENTAR = ac.COD_ATIVIDADE_COMPLEMENTAR and
                                                        ac.ANO_LET = mp.ANO_LET and
                                                        ac.PERIODO_LET = mp.PERIODO_LET)
             where mp.COD_MATRICULA = mac.COD_MATRICULA) as cursou_atividade_complementar

        from matriculas_periodos mp
        inner join sincronizacao s on s.cod_matricula = mp.cod_matricula
        inner join matriculas m on mp.cod_matricula = m.cod_matricula
        """

        if prefixo_matricula:
            if prefixo_matricula != 'full':
                if "'" in prefixo_matricula:
                    sql += f' where m.matricula IN ({prefixo_matricula})'
                else:
                    sql += " where m.matricula LIKE '" + prefixo_matricula + "%'"
            else:
                MatriculaPeriodo.objects.filter(aluno__matriz__isnull=True).update(excluida=True)
        else:
            sql += f" where s.dt_atualizacao >= '{self.dt_ultimo_historico_atualizacao}' "

        m_qtd = self.get_contador_matricula_periodo(prefixo_matricula=prefixo_matricula)

        cur = self.get_connection().cursor()
        cur.execute(sql)

        criados = 0
        atualizados = 0
        percentual = 0
        contador = 1

        cache_situacoes_matriculas_periodo = cache_queryset(SituacaoMatriculaPeriodo.objects.all(), 'codigo_academico')
        cache_anos = cache_queryset(Ano.objects.all(), 'ano')

        if prefixo_matricula == 'full':
            MatriculaPeriodo.objects.filter(aluno__curso_campus__ativo=False, aluno__matriz__isnull=True).update(excluida=True)

        for row in cur.fetchall():
            # ignorando alunos integralizados
            if not Aluno.objects.filter(matricula=row['matricula'], matriz__isnull=False).exists() or forcar_importacao:
                cod_turma = row['cod_turma'] and row['cod_turma'] or ''

                d = {
                    'codigo_academico': row['cod_matricula'],
                    'ano_letivo': row['ano_let'],
                    'periodo_letivo': row['periodo_let'],
                    'periodo_matriz': row['periodo'],
                    'situacao': row['sit_matricula_periodo'],
                    'codigo_turma_qacademico': cod_turma,
                    'concluiu': row['concluiu'],
                    'nota': row['nota'],
                    'cursou_atividade': row['cursou_atividade'],
                    'cursou_atividade_complementar': row['cursou_atividade_complementar'],
                }

                try:
                    qs = MatriculaPeriodo.objects.filter(
                        aluno__codigo_academico=d['codigo_academico'], periodo_letivo=d['periodo_letivo'], ano_letivo=cache_anos[str(d['ano_letivo'])]
                    )
                except Exception as e:
                    logger.info((f'Funcao importar_matriculas_periodo: Aluno {d}', e))
                    continue

                if qs:
                    m = qs[0]
                    atualizados += 1
                else:
                    try:
                        m = MatriculaPeriodo()
                        m.aluno = Aluno.objects.get(codigo_academico=d['codigo_academico'])
                        criados += 1
                    except Exception as e:
                        logger.info((f'Funcao importar_matriculas_periodo: Aluno {d}', e))
                        continue

                m.ano_letivo = cache_anos[str(d['ano_letivo'])]
                m.periodo_letivo = d['periodo_letivo']
                m.periodo_matriz = d['periodo_matriz'] and d['periodo_matriz'] or 0

                # A situação da matrícula no periodo só pode ser alterada caso o aluno nao tenha sido migrado para o suap naquele período
                situacao_matricula_periodo = cache_situacoes_matriculas_periodo[str(d['situacao'])]
                if situacao_matricula_periodo.pk != SituacaoMatriculaPeriodo.TRANSFERIDO_SUAP:
                    m.situacao = situacao_matricula_periodo

                m.nota = d['nota'] and Decimal(str(d['nota'])) or Decimal(0)
                m.excluida = False
                m.gerada_suap = False
                m.codigo_turma_qacademico = d['codigo_turma_qacademico']
                m.cursou_acc_qacademico = bool(d['cursou_atividade'] or d['cursou_atividade_complementar'])

                if settings.NOTA_DECIMAL and settings.CASA_DECIMAL == 1:
                    m.nota *= 10
                elif settings.NOTA_DECIMAL and settings.CASA_DECIMAL == 2:
                    m.nota *= 100

                m.save()

                if verbose:
                    percentual_atual = f'{contador / float(m_qtd) * 100:.0f}'
                    if percentual_atual != percentual:
                        percentual = percentual_atual
                        stdout.write(f'Importando matriculas em periodo: {percentual}%%\r')
                        stdout.flush()
                contador += 1

        if verbose:
            stdout.write('\rImportando alunos: 100%\r\n')

        cur.close()
        return criados, atualizados

    def atualizar_historico(self):
        from django.db import connection

        sql = """
            insert into edu_historicosituacaomatricula (aluno_id, situacao_id, data)
            select a.id as aluno_id, a.situacao_id, NOW() as data from edu_aluno a where a.situacao_id <> coalesce((select situacao_id from edu_historicosituacaomatricula h where aluno_id = a.id order by data desc limit 1), -1);

            insert into edu_historicosituacaomatriculaperiodo (matricula_periodo_id, situacao_id, data)
            select mp.id as matricula_periodo_id, mp.situacao_id, NOW() as data from edu_matriculaperiodo mp where mp.situacao_id <> coalesce((select situacao_id from edu_historicosituacaomatriculaperiodo h where matricula_periodo_id = mp.id order by data desc limit 1), -1);
        """
        cur = connection.cursor()
        cur.execute(sql)
        connection._commit()

    def atualizar_username(self):
        pass

    # funcao utilizada na integralização
    def importar_historico_resumo(self, matriculas, matriz_id, ano_letivo, periodo_letivo, validacao=True, ignorar_ultimo_periodo=False, task=None):
        matriculas = copy.copy(matriculas)
        matriculas_str = ''
        for matricula_str in matriculas:
            matriculas_str += f"'{matricula_str}',"
        matriculas_str = matriculas_str[:-1]
        matriz = Matriz.objects.get(pk=matriz_id)

        DISCIPLINAS_SEM_NOTA = ['Seminário de Integração Acadêmica', 'Orientação Educacional']

        SITUACOES_PERIODOS_ABERTOS = [
            SituacaoMatriculaPeriodo.EM_ABERTO,
            SituacaoMatriculaPeriodo.MATRICULADO,
            SituacaoMatriculaPeriodo.TRANSFERIDO_SUAP,
        ]

        MAPA_SITUACAO_DIARIO = {}
        MAPA_SITUACAO_DIARIO[1] = MatriculaDiario.SITUACAO_CURSANDO  # Cursando (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[2] = MatriculaDiario.SITUACAO_CURSANDO  # Recuperacao (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[3] = MatriculaDiario.SITUACAO_CURSANDO  # Prova Final (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[4] = MatriculaDiario.SITUACAO_APROVADO  # Aprovado
        MAPA_SITUACAO_DIARIO[5] = MatriculaDiario.SITUACAO_REPROVADO  # Reprovado
        MAPA_SITUACAO_DIARIO[6] = MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA  # Rep. Falta
        MAPA_SITUACAO_DIARIO[7] = MatriculaDiario.SITUACAO_CANCELADO  # Cancelado
        MAPA_SITUACAO_DIARIO[8] = MatriculaDiario.SITUACAO_PROVA_FINAL  # Prova Final Frequencia (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[9] = MatriculaDiario.SITUACAO_DISPENSADO  # Dispensado
        MAPA_SITUACAO_DIARIO[10] = MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO  # Aproveit. Disciplina (Manter o termo do Suap)
        MAPA_SITUACAO_DIARIO[11] = MatriculaDiario.SITUACAO_TRANCADO  # Afastado
        MAPA_SITUACAO_DIARIO[12] = MatriculaDiario.SITUACAO_TRANCADO  # Trancado
        MAPA_SITUACAO_DIARIO[13] = MatriculaDiario.SITUACAO_CANCELADO  # Jubilado
        MAPA_SITUACAO_DIARIO[14] = MatriculaDiario.SITUACAO_CANCELADO  # Removida
        MAPA_SITUACAO_DIARIO[15] = MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO  # Aceler. Estudos (Manter o termo do Suap)
        MAPA_SITUACAO_DIARIO[16] = MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO  # Aprovado /Rep. no Modulo
        MAPA_SITUACAO_DIARIO[17] = MatriculaDiario.SITUACAO_CANCELADO  # Transferencia Curso
        MAPA_SITUACAO_DIARIO[18] = MatriculaDiario.SITUACAO_CANCELADO  # Transferencia de Turma
        MAPA_SITUACAO_DIARIO[19] = MatriculaDiario.SITUACAO_CANCELADO  # Transferencia Turno
        MAPA_SITUACAO_DIARIO[20] = MatriculaDiario.SITUACAO_CANCELADO  # Transferencia Externa
        MAPA_SITUACAO_DIARIO[22] = MatriculaDiario.SITUACAO_APROVADO  # Concluida
        MAPA_SITUACAO_DIARIO[23] = MatriculaDiario.SITUACAO_CURSANDO  # Recuperacao Frequencia (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[24] = MatriculaDiario.SITUACAO_PENDENTE  # Pendencia (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[25] = MatriculaDiario.SITUACAO_CURSANDO  # Em Andamento (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[26] = MatriculaDiario.SITUACAO_APROVADO  # Aprovado Modulo
        MAPA_SITUACAO_DIARIO[27] = MatriculaDiario.SITUACAO_REPROVADO  # Rep. Aceler. Estudos
        MAPA_SITUACAO_DIARIO[28] = MatriculaDiario.SITUACAO_TRANCADO  # Intercambio
        MAPA_SITUACAO_DIARIO[29] = MatriculaDiario.SITUACAO_CURSANDO  # Dep. nao cursada (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[30] = MatriculaDiario.SITUACAO_CURSANDO  # Certificado ENEM (Não-Integralizar)
        MAPA_SITUACAO_DIARIO[31] = MatriculaDiario.SITUACAO_CANCELADO  # Cancelamento Compulsorio

        MAPA_SITUACAO_INVALIDA = {}
        MAPA_SITUACAO_INVALIDA[1] = 'Cursando'
        MAPA_SITUACAO_INVALIDA[2] = 'Recuperação'
        MAPA_SITUACAO_INVALIDA[3] = 'Prova Final'
        MAPA_SITUACAO_INVALIDA[8] = 'Prova Final Frequência'
        MAPA_SITUACAO_INVALIDA[23] = 'Recuperação Frequência'
        MAPA_SITUACAO_INVALIDA[24] = 'Pendência'
        MAPA_SITUACAO_INVALIDA[25] = 'Em Andamento'
        MAPA_SITUACAO_INVALIDA[29] = 'Dep. não Cursda'
        MAPA_SITUACAO_INVALIDA[30] = 'Certificado ENEM'

        CACHE_COMPONENTES = {}

        if validacao:
            self.importar_alunos(matriculas_str, verbose=False, forcar_importacao=True)
            self.importar_matriculas_periodo(matriculas_str, verbose=False, forcar_importacao=True)

        semestral = (
            matriculas and Aluno.objects.get(matricula=matriculas[0]).curso_campus.periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL or False
        )
        if ignorar_ultimo_periodo:
            if semestral:
                where = f'and h.ano_let <> {ano_letivo.ano} and h.periodo_Let <> {periodo_letivo}'
            else:
                where = f'and h.ano_let < {ano_letivo.ano}'
        else:
            where = ''

        sql = f"""
            SELECT
                m.matricula as matricula,
                h.cod_matricula as cod_matricula,
                h.ano_let as ano_letivo,
                h.periodo_Let as periodo_letivo,
                h.sigla_disciplina as sigla,
                h.desc_disciplina as descricao,
                h.nota as nota,
                h.frequencia as frequencia,
                h.sit_matricula_pauta as situacao,
                h.cod_disciplina_pauta as cod_disciplina,
                h.carga_hor as carga_horaria,
                h.cod_professor as cod_professor,
                h.nome_pessoa_professor as nome_professor,
                h.desc_titularidade_professor as titularidade_professor,
                h.cod_pauta as cod_diario_pauta,
                h.conceito as conceito
            FROM dbo.vw_historico_3_0  h
            INNER JOIN dbo.matriculas m ON m.cod_matricula = h.cod_matricula
            WHERE m.matricula IN ({matriculas_str})
            and h.cod_pauta is not null
            {where}
            ORDER BY h.cod_matricula, h.ano_Let, h.periodo_let, h.desc_disciplina
        """

        cur = self.get_connection().cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        alunos = {}

        if task is None:
            iterator = rows
        else:
            iterator = task.iterate(rows)

        for row in iterator:
            codigo_academico = row['cod_matricula']
            sigla = row['sigla']
            ano_let = row['ano_letivo']
            periodo_let = row['periodo_letivo']
            descricao = row['descricao']
            carga_horaria = row['carga_horaria']
            cod_disciplina = row['cod_disciplina']
            situacao = row['situacao']
            frequencia = int(float(row['frequencia'] or 0))
            nota = None
            if row['nota'] != '' and row['nota'] is not None:
                if settings.NOTA_DECIMAL:
                    nota = int(str(row['nota']).replace(',', '').replace('.', ''))
                    if settings.CASA_DECIMAL == 2:
                        nota *= 10
                else:
                    nota = int(float(row['nota']))
            cod_professor = row['cod_professor']
            nome_professor = row['nome_professor']
            titularidade_professor = row['titularidade_professor']
            cod_diario_pauta = row['cod_diario_pauta']
            conceito = row['conceito']

            if codigo_academico in list(alunos.keys()):
                aluno = alunos[codigo_academico]
            else:
                aluno = Aluno.objects.get(codigo_academico=codigo_academico)
                aluno.erros = []
                aluno.registros = []
                alunos[codigo_academico] = aluno
                aluno.matriculas_periodo = {}
                # vamos remover a matrícula do aluno para ao final sabermos quais alunos não tiveram nenhum registro importado
                matriculas.remove(row['matricula'])

                # checando algumas condições sobre o aluno
                if validacao:
                    ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
                    if ignorar_ultimo_periodo:
                        matriculas_periodo = aluno.get_matriculas_periodo(ano_letivo, periodo_letivo)
                    else:
                        matriculas_periodo = aluno.get_matriculas_periodo()

                    for matricula_periodo in matriculas_periodo.filter(situacao__id__in=SITUACOES_PERIODOS_ABERTOS).exclude(
                        id=ultima_matricula_periodo.pk
                    ):
                        aluno.erros.append(
                            f'O período letivo <i>{matricula_periodo.ano_letivo.ano}/{matricula_periodo.periodo_letivo}</i> encontra-se aberto, ou seja, com a situação "<i>{matricula_periodo.situacao}</i>"'
                        )

                    if not ignorar_ultimo_periodo:
                        if ultima_matricula_periodo.ano_letivo.pk != ano_letivo.pk or (
                            semestral and ultima_matricula_periodo.periodo_letivo != periodo_letivo
                        ):
                            aluno.erros.append(
                                f'O período letivo da integralização (<i>{ano_letivo.ano}/{periodo_letivo}</i>) não coincide com o do último período da matrícula do aluno (<i>{ultima_matricula_periodo.ano_letivo.ano}/{ultima_matricula_periodo.periodo_letivo}</i>) '
                            )

                        if ultima_matricula_periodo.situacao.id not in SITUACOES_PERIODOS_ABERTOS:
                            aluno.erros.append(
                                f'A situação da matrícula no período {ultima_matricula_periodo.ano_letivo.ano}/{ultima_matricula_periodo.periodo_letivo} encontra-se fechada, ou seja, "<i>{ultima_matricula_periodo.situacao}</i>"'
                            )

                    if aluno.situacao.id not in [SituacaoMatricula.MATRICULADO, SituacaoMatricula.TRANSFERIDO_SUAP]:
                        aluno.erros.append(
                            f'O aluno não encontra-se com a situação "Matriculado" nem "Transferido Suap". A situação dele é "<i>{aluno.situacao}</i>"'
                        )

                        # regra a ser utilizada em breve, por isso encontra-se comentado
                        # if ultima_matricula_periodo.pedidomatricula_set.all():
                        #    aluno.erros.append(u'Já possui pedido de renovação de matrícula para o período de <i>{}/{}</i>'.format(ultima_matricula_periodo.ano_letivo.ano, ultima_matricula_periodo.periodo_letivo))

            # chechando algumas condições sobre as disciplinas
            if validacao:
                if situacao in list(MAPA_SITUACAO_INVALIDA.keys()):
                    aluno.erros.append(
                        'A disciplina "<i>{}</i>", cursada em {}.{}, encontra-se com a situação "<i>{}</i>".'.format(
                            row['descricao'], row['ano_letivo'], row['periodo_letivo'], MAPA_SITUACAO_INVALIDA[situacao]
                        )
                    )
                elif (
                    row['nota'] is None
                    and row['conceito'] is None
                    and (row['situacao'] not in [4, 6, 9, 16])
                    and descricao not in DISCIPLINAS_SEM_NOTA
                ):  # 4:Aprovado, 6:Rep. Falta, 9:Dispensado, 16:Aprovado/Reprovador Módulo
                    aluno.erros.append(
                        'A nota/conceito da disciplina "<i>{}</i>", cursada em {}.{}, não foi informada.'.format(
                            row['descricao'], row['ano_letivo'], row['periodo_letivo']
                        )
                    )
                elif row['cod_disciplina'] is None:
                    aluno.erros.append(
                        'O código da disciplina "<i>{}</i>", cursada em {}.{}, não foi definido.'.format(
                            row['descricao'], row['ano_letivo'], row['periodo_letivo']
                        )
                    )
                elif row['ano_letivo'] is None or row['periodo_letivo'] is None:
                    aluno.erros.append('O ano/período letivo em que a disciplina "<i>{}</i>" foi cursada não está definida.'.format(row['descricao']))
            else:
                if sigla not in CACHE_COMPONENTES:
                    qs_componente = Componente.objects.filter(sigla_qacademico=sigla)
                    CACHE_COMPONENTES[sigla] = qs_componente.exists() and qs_componente[0] or None

                # equivalencias
                qs_equivalencia_componente = EquivalenciaComponenteQAcademico.objects.filter(q_academico=row['cod_disciplina'])

                if qs_equivalencia_componente:
                    equivalencia_componente = qs_equivalencia_componente[0]
                else:
                    equivalencia_componente = EquivalenciaComponenteQAcademico()

                equivalencia_componente.q_academico = cod_disciplina
                equivalencia_componente.sigla = sigla
                equivalencia_componente.descricao = descricao
                equivalencia_componente.carga_horaria = carga_horaria
                if not equivalencia_componente.componente:
                    equivalencia_componente.componente = CACHE_COMPONENTES[sigla]
                equivalencia_componente.save()

                registro = {
                    'media_final_disciplina': nota,
                    'frequencia': frequencia,
                    'situacao': MAPA_SITUACAO_DIARIO[situacao],
                    'equivalencia_componente': equivalencia_componente,
                    'matricula_periodo': aluno.matriculaperiodo_set.get(ano_letivo__ano=ano_let, periodo_letivo=periodo_let),
                    'cod_professor': cod_professor,
                    'nome_professor': nome_professor,
                    'titularidade_professor': titularidade_professor,
                    'cod_diario_pauta': cod_diario_pauta,
                    'conceito': conceito,
                }

                aluno.registros.append(registro)

        cur.close()

        # retornando os erros caso de trate apenas de validação
        if validacao:
            erros = []
            for aluno in alunos.values():
                if aluno.erros:
                    erros.append((aluno, aluno.erros))
            return erros
        else:
            # adicionando os alunos os quais nenhum registro foi encontrado no a-acadêmico para que se efetive a integralização
            for matricula in matriculas:
                aluno = Aluno.objects.get(matricula=matricula)
                aluno.erros = []
                aluno.registros = []
                aluno.matriculas_periodo = {}
                alunos[aluno.codigo_academico] = aluno

            for aluno in alunos.values():
                ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()

                # setando situacao em_aberto na última matricula do período caso o aluno não esteja matriculado em nenhum diário (ocorre apenas na re-integralização do alunos após deferimento de pedido de matrícula)
                qs_matriculas_diario = MatriculaDiario.objects.filter(
                    situacao=MatriculaDiario.SITUACAO_CURSANDO, matricula_periodo=ultima_matricula_periodo
                )
                if ultima_matricula_periodo.situacao.id == SituacaoMatriculaPeriodo.MATRICULADO and not qs_matriculas_diario.exists():
                    ultima_matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)
                    ultima_matricula_periodo.save()

                # setando matriz do aluno
                if aluno.matriz is None:
                    aluno.matriz = matriz

                # atualizando o histórico do aluno
                for registro in aluno.registros:
                    qs = MatriculaDiarioResumida.objects.filter(
                        matricula_periodo=registro['matricula_periodo'], equivalencia_componente=registro['equivalencia_componente']
                    )
                    if qs.exists():
                        matricula_diario_resumida = qs[0]
                        matricula_diario_resumida.media_final_disciplina = registro['media_final_disciplina']
                        matricula_diario_resumida.frequencia = registro['frequencia']
                        matricula_diario_resumida.situacao = registro['situacao']
                        matricula_diario_resumida.codigo_professor = registro['cod_professor']
                        matricula_diario_resumida.nome_professor = registro['nome_professor']
                        matricula_diario_resumida.titularidade_professor = registro['titularidade_professor']
                        matricula_diario_resumida.codigo_diario_pauta = registro['cod_diario_pauta']
                        matricula_diario_resumida.conceito = registro['conceito']
                        matricula_diario_resumida.save()
                    else:
                        MatriculaDiarioResumida.objects.create(
                            matricula_periodo=registro['matricula_periodo'],
                            equivalencia_componente=registro['equivalencia_componente'],
                            media_final_disciplina=registro['media_final_disciplina'],
                            frequencia=registro['frequencia'],
                            situacao=registro['situacao'],
                            codigo_professor=registro['cod_professor'],
                            nome_professor=registro['nome_professor'],
                            codigo_diario_pauta=registro['cod_diario_pauta'],
                            conceito=registro['conceito'],
                        )
                # salvando o aluno

                aluno.data_integralizacao = datetime.datetime.now()
                aluno.ano_letivo_integralizacao = ultima_matricula_periodo.ano_letivo
                aluno.periodo_letivo_integralizacao = ultima_matricula_periodo.periodo_letivo
                aluno.atualizar_situacao('Migração do Aluno do Q-Acadêmico')

            if task:
                task.finalize('Integralização realizada com sucesso', f'/edu/integralizar_alunos/{matriz_id}/')

    def importar_livros(self):
        sql = """
        select
            l.COD_LIVRO_DIPLOMA as codigo_qacademico,
            l.DESC_LIVRO_DIPLOMA as descricao,
            l.LIVRO_ATUAL as numero_livro,
            l.QUANTIDADE_PAGINAS as folhas_por_livro,
            l.PAGINA_ATUAL as numero_folha,
            l.REGISTRO_ATUAL as numero_registro
        from dbo.DIP_LIVROS_DIPLOMAS l;
        """
        cur = self.get_connection().cursor()
        cur.execute(sql)
        for row in cur.fetchall():
            obj = ConfiguracaoLivro.objects.filter(codigo_qacademico=row['codigo_qacademico']).first()
            if not obj:
                obj = ConfiguracaoLivro()
                obj.codigo_qacademico = row['codigo_qacademico']
            obj.descricao = row['descricao']
            obj.numero_livro = row['numero_livro']
            obj.folhas_por_livro = row['folhas_por_livro']
            obj.numero_folha = row['numero_folha']
            obj.numero_registro = row['numero_registro']
            sigla = row['descricao'].split()[-1]
            obj.uo = UnidadeOrganizacional.objects.suap().filter(sigla=sigla.upper()).first() or UnidadeOrganizacional.objects.suap().get(
                sigla=get_sigla_reitoria()
            )
            obj.save()
        cur.close()

    def importar_registros_diploma(self, matricula=None):
        # RegistroEmissaoDiploma.objects.filter(codigo_qacademico__isnull=True).delete()
        sql1 = """
        select
            m.MATRICULA as matricula,
            d.COD_MATRICULA as codigo_qacademico,
            d.N_FORMULARIO as numero_formulario,
            d.N_LIVRO as livro,
            d.N_FOLHA as folha,
            d.N_REGISTRO as numero_registro,
            d.N_FORMULARIO as numero_formulario,
            d.DATA_EMISSAO as data_registro,
            d.DATA as data_expedicao,
            d.PASTA as pasta,
            d.via as via,
            d.PROCESSO as processo
        from dbo.DIP_FORMULARIOS_DIPLOMAS d
        inner join dbo.MATRICULAS m on d.COD_MATRICULA = m.COD_MATRICULA
        """
        if matricula:
            sql1 += f" AND m.MATRICULA = '{matricula}'"

        sql1 += ' order by d.DATA_EMISSAO desc'

        sql2 = """
        select
            m.MATRICULA as matricula,
            m.COD_MATRICULA as codigo_qacademico,
            __DIPLOMA_DATA as data_expedicao,
            __DIPLOMA_DATA_EMISSAO as data_registro,
            __DIPLOMA_N_FOLHA as folha,
            __DIPLOMA_N_LIVRO as livro,
            __DIPLOMA_N_REGISTRO as numero_registro,
            __DIPLOMA_PASTA as pasta,
            __DIPLOMA_PROCESSO as processo,
            __DIPLOMA_SERIE as numero_formulario,
            __DIPLOMA_VIA as via
            from MATRICULAS m
            where __DIPLOMA_DATA is not NULL
        """

        if matricula:
            sql2 += f" AND m.MATRICULA = '{matricula}'"

        i = 0
        conn = self.get_connection()
        conn2 = self.get_connection()
        for sql in (sql1, sql2):
            cur = conn.cursor()
            cur2 = conn2.cursor()
            cur.execute(sql)
            row = cur.fetchone()
            while row:
                i = i + 1
                if not i % 1000:
                    logger.info(i)
                aluno = Aluno.objects.filter(matricula=row['matricula']).first()
                if aluno:
                    obj = RegistroEmissaoDiploma.objects.filter(codigo_qacademico=row['codigo_qacademico'], via=row['via'] or 1).first()
                    if not obj:
                        obj = RegistroEmissaoDiploma()
                        obj.codigo_qacademico = row['codigo_qacademico']
                        obj.via = row['via'] or 1
                    obj.aluno = aluno
                    obj.sistema = 'Q-ACADÊMICO'
                    obj.livro = row['livro']
                    obj.folha = row['folha']
                    obj.configuracao_livro = (
                        ConfiguracaoLivro.objects.filter(uo=aluno.curso_campus.diretoria.setor.uo, codigo_qacademico__isnull=False)
                        .exclude(descricao='SICA')
                        .first()
                    )
                    obj.numero_registro = row['numero_registro']
                    obj.numero_formulario = row['numero_formulario']
                    obj.processo = None
                    obj.data_registro = row['data_expedicao'] or row['data_registro'] or None
                    obj.data_expedicao = row['data_expedicao'] or row['data_registro'] or None
                    obj.observacao = row['processo'] and 'Processo {}'.format(row['processo']) or ''
                    obj.pasta = row['pasta'] or ''
                    obj.emissor = None
                    obj.cancelado = False
                    obj.motivo_cancelamento = None
                    obj.data_cancelamento = None
                    matriz, ch_total, autorizacao, reconhecimento = self.get_dados_matriz(row['matricula'], cur2)
                    obj.matriz = matriz
                    obj.ch_total = ch_total
                    obj.autorizacao = autorizacao
                    obj.reconhecimento = reconhecimento
                    obj.save()
                row = cur.fetchone()
            cur.close()
            cur2.close()
        conn.close()
        conn2.close()

    def get_dados_matriz(self, matricula, cur):
        sql = f"""SELECT
            mc.COD_MATRIZ_CURRICULAR AS cod_matriz,
            mc.DESC_MATRIZ_CURRICULAR AS matriz,
            ch.Carga_Hor_Prevista as ch_total,
            c.AUTORIZACAO as autorizacao,
            c.RECONHECIMENTO as reconhecimento
            FROM MATRICULAS m
            JOIN VW_CARGA_HORARIA_ALUNOS ch ON  ch.Matricula  =  m.MATRICULA
            JOIN CURSOS c ON m.COD_CURSO = c.COD_CURSO
            JOIN MATRIZES_CURRICULARES mc ON m.COD_MATRIZ_CURRICULAR = mc.COD_MATRIZ_CURRICULAR
            WHERE m.MATRICULA =  '{matricula}'"""
        cur.execute(sql)
        row = cur.fetchone()
        matriz = '{} - {}'.format(row['cod_matriz'], row['matriz'])
        ch_total = row['ch_total']
        autorizacao = row['autorizacao']
        reconhecimento = row['reconhecimento']
        return matriz, ch_total, autorizacao, reconhecimento

    # funcao utilizada para obter o histórico de alunos concluídos que cursaram no SUAP

    def importar_historico_legado_resumo(self, aluno):
        SITUACAO_DIARIO = {
            1: 'Cursando',
            2: 'Recuperação',
            3: 'Prova Final',
            4: 'Aprovado',
            5: 'Reprovado',
            6: 'Rep. Falta',
            7: 'Cancelado',
            8: 'Prova Final Freqüência',
            9: 'Dispensado',
            10: 'Aproveit. Disciplina',
            11: 'Afastado',
            12: 'Trancado',
            13: 'Jubilado',
            14: 'Removida',
            15: 'Aceler. Estudos',
            16: 'Aprovado /Rep. no Módulo',
            17: 'Transferencia Curso',
            18: 'Transferência de Turma',
            19: 'Transferencia Turno',
            20: 'Transferencia Externa',
            22: 'Concluída',
            23: 'Recuperação Freqüência',
            24: 'Pendência',
            25: 'Em Andamento',
            26: 'Aprovado Módulo',
            27: 'Rep. Aceler. Estudos',
            28: 'Intercâmbio',
            29: 'Dep. não cursada',
            30: 'Certificado ENEM',
        }

        # Consultando as atividades complementares
        sql = f"""
            select ANO_LET as ano_letivo, PERIODO_LET as periodo_letivo,
            CAST(t3.CARGA_HORARIA AS INT) as is_curricular, t3.DESC_ATIVIDADE_COMPLEMENTAR as descricao from MATRICULAS m
            join MATRICULAS_ATIVIDADES_COMPLEMENTARES t2 on m.COD_MATRICULA = t2.cod_matricula
            join ATIVIDADES_COMPLEMENTARES t3 on t2.COD_ATIVIDADE_COMPLEMENTAR = t3.COD_ATIVIDADE_COMPLEMENTAR
            and  m.MATRICULA =  '{aluno.matricula}'
        """
        cur = self.get_connection().cursor()
        cur.execute(sql)
        accs = list(cur.fetchall())
        cur.close()

        # Extraindo o restante dos dados para o histórico
        sql = f"""
                SELECT
                            mc.COD_MATRIZ_CURRICULAR AS cod_matriz, mc.DESC_MATRIZ_CURRICULAR AS matriz,
                            ch.Carga_Hor_Obrigatoria_Cumprida as ch_obrigatoria_cumprida,
                            ch.Carga_Hor_Optativa_Cumprida as ch_optativa_cumprida,
                            ch.Carga_Hor_Complementar_Cumprida as ch_complementar_cumprida,
                            ch.Carga_Hor_Estagio_Cumprida as ch_estagio_cumprida,
                            ch.Carga_Hor_Projeto_Cumprida as ch_projeto_cumprida,
                            ch.Carga_Hor_Cumprida as ch_cumprida,
                            ch.Carga_Hor_Obrigatoria_Prevista as ch_obrigatoria_prevista,
                            ch.Carga_Hor_Optativa_Prevista as ch_optativa_prevista,
                            ch.Carga_Hor_Complementar_Prevista as ch_complementar_prevista,
                            ch.Carga_Hor_Estagio_Prevista as ch_estagio_prevista,
                            ch.Carga_Hor_Projeto_Prevista as ch_projeto_prevista,
                            ch.Carga_Hor_Prevista as ch_prevista,
                            c.MODALIDADE_ENSINO as ead,
                            c.AUTORIZACAO as autorizacao, c.RECONHECIMENTO as reconhecimento,
                            fi.DESC_FORMA_INGRESSO AS forma_ingresso, tc.MODULAR AS modular,
                            tc.PERIODIZADO AS seriado, tc.MODULAR_RN AS modular_rn,
                            tc.N_PERIODOS_ANO AS periodicidade, ci.DESC_CIDADE AS naturalidade,
                            ci.ESTADO as estado,
                            pf.TEMA as titulo_projeto,
                            ST_TIT.DESCRICAO as titulacao_orientador_projeto,
                            pppf.NOME_PESSOA as orientador_projeto,
                            vw_m.__DIPLOMA_N_LIVRO as livro,
                            vw_m.__DIPLOMA_N_FOLHA as folha,
                            vw_m.__DIPLOMA_N_REGISTRO as registro,
                            replace(convert(char(11),vw_m.__DIPLOMA_DATA,103),' ','/') as data_diploma,
                            replace(convert(char(11),pf.DT_APRESENTACAO,103),' ','/') as data_defesa,
                            pf.NOTA as nota_projeto,
                            pf.CARGA_HORARIA as ch_projeto,
                            st.DESCRICAO as tipo_projeto,
                            st2.DESCRICAO as situacao_projeto,
                            replace(convert(char(11),vw_m.DT_ULTIMO_ENADE,103),' ','/') as data_ultimo_enade,
                            vw_m.Desc_Sit_ENADE as situacao_enade,
                            ev.ANO_LET as ano_enade,
                            ev.DESC_VERSAO_ENADE as versao_enade,
                            replace(convert(char(11),ev.DT_PROVA,103),' ','/') as data_prova_enade,
                            st3.DESCRICAO as situacao_matricula_enade,
                            ej.DESC_JUSTIFICATIVA as justificativa_enade,
                            c.DESC_CURSO as curso,
                            vw_m.__DT_CONCLUSAO_CURSO AS data_conclusao_curso,
                            vw_m.DT_COLACAO_GRAU AS data_colacao_grau,
                            cg.ANO_LET AS ano_letivo_colacacao_grau,
                            cg.PERIODO_LET AS periodo_letivo_colacacao_grau
                FROM MATRICULAS m
                JOIN VW_MATRICULAS vw_m ON m.MATRICULA = vw_m.MATRICULA
                JOIN VW_CARGA_HORARIA_ALUNOS ch ON  ch.Matricula  =  vw_m.MATRICULA
                JOIN ALUNOS a ON m.COD_ALUNO = a.COD_ALUNO
                JOIN PESSOAS p ON a.COD_PESSOA = p.COD_PESSOA
                LEFT JOIN CIDADES ci ON p.COD_NATURALIDADE = ci.COD_CIDADE
                JOIN MATRIZES_CURRICULARES mc ON m.COD_MATRIZ_CURRICULAR = mc.COD_MATRIZ_CURRICULAR
                JOIN FORMAS_INGRESSO fi ON m.COD_FORMA_INGRESSO = fi.COD_FORMA_INGRESSO
                JOIN CURSOS c ON m.COD_CURSO = c.COD_CURSO
                JOIN TIPOS_CURSOS tc ON c.COD_TIPO_CURSO = tc.COD_TIPO_CURSO
                LEFT JOIN PROJETOS_FINAIS pf ON m.COD_MATRICULA = pf.COD_MATRICULA
                LEFT JOIN PROFESSORES ppf on pf.COD_PROFESSOR = ppf.COD_PROFESSOR
                LEFT JOIN SITUACOES_TABELAS ST_TIT ON ((ST_TIT.NOME_TABELA = 'PROFESSORES') AND (ST_TIT.NOME_COLUNA = 'TITULARIDADE') AND (ppf.TITULARIDADE = ST_TIT.VALOR))
                LEFT JOIN PESSOAS pppf on ppf.COD_PESSOA = pppf.COD_PESSOA
                LEFT JOIN SITUACOES_TABELAS st ON (st.NOME_TABELA = 'PROJETOS_FINAIS' and st.NOME_COLUNA = 'TIPO_PROJETO_FINAL' and st.VALOR = pf.TIPO_PROJETO_FINAL)
                LEFT JOIN SITUACOES_TABELAS st2 ON (st2.NOME_TABELA = 'PROJETOS_FINAIS' and st2.NOME_COLUNA = 'SIT_PROJETO_FINAL' and st2.VALOR = pf.SIT_PROJETO_FINAL)
                LEFT JOIN ENA_MATRICULAS_VERSOES_ENADE em ON m.COD_MATRICULA = em.COD_MATRICULA
                LEFT JOIN ENA_VERSOES_ENADE ev ON em.COD_VERSAO_ENADE = ev.COD_VERSAO_ENADE
                LEFT JOIN SITUACOES_TABELAS st3 ON (st3.NOME_TABELA = 'ENA_MATRICULAS_VERSOES_ENADE' and st3.NOME_COLUNA = 'SIT_MATRICULA_ENADE' and st3.VALOR = em.SIT_MATRICULA_ENADE)
                LEFT JOIN ENA_JUSTIFICATIVAS ej ON em.COD_JUSTIFICATIVA = ej.COD_JUSTIFICATIVA
                LEFT JOIN MATRICULAS_COLACOES_GRAU mcl ON mcl.COD_MATRICULA = m.COD_MATRICULA
                LEFT JOIN COLACOES_GRAU cg on mcl.COD_COLACAO_GRAU = cg.COD_COLACAO_GRAU
                WHERE m.MATRICULA =  '{aluno.matricula}'
        """

        cur = self.get_connection().cursor()
        cur.execute(sql)
        row = cur.fetchone()
        lista = []
        if row:
            regime = ''
            if row['modular_rn']:
                regime = 'Modular RN'
            elif row['modular']:
                regime = 'Modular'
            elif row['seriado']:
                regime = 'Seriado'
            else:
                regime = 'Crédito'

            periodicidade = ''
            if row['periodicidade'] == 1:
                periodicidade = 'Anual'
            elif row['periodicidade'] == 2:
                periodicidade = 'Semestral'
            elif row['periodicidade'] == 4:
                periodicidade = 'Trimestral'

            lista.append(
                {
                    'naturalidade': '{} - {}'.format(row['naturalidade'], row['estado']) if row['naturalidade'] and row['estado'] else '-',
                    'cod_matriz': row['cod_matriz'],
                    'matriz': '{} - {}'.format(row['cod_matriz'], row['matriz']),
                    'ch_obrigatoria_cumprida': row['ch_obrigatoria_cumprida'],
                    'ch_optativa_cumprida': row['ch_optativa_cumprida'],
                    'ch_complementar_cumprida': row['ch_complementar_cumprida'],
                    'ch_estagio_cumprida': row['ch_estagio_cumprida'],
                    'ch_projeto_cumprida': row['ch_projeto_cumprida'],
                    'ch_cumprida': row['ch_cumprida'],
                    'ch_obrigatoria_prevista': row['ch_obrigatoria_prevista'],
                    'ch_optativa_prevista': row['ch_optativa_prevista'],
                    'ch_complementar_prevista': row['ch_complementar_prevista'],
                    'ch_estagio_prevista': row['ch_estagio_prevista'],
                    'ch_projeto_prevista': row['ch_projeto_prevista'],
                    'ch_prevista': row['ch_prevista'],
                    'forma_ingresso': row['forma_ingresso'],
                    'ead': row['ead'],
                    'autorizacao': row['autorizacao'],
                    'reconhecimento': row['reconhecimento'],
                    'curso': row['curso'],
                    'data_conclusao_curso': row['data_conclusao_curso'],
                    'data_colacao_grau': row['data_colacao_grau'],
                    'ano_letivo_colacacao_grau': row['ano_letivo_colacacao_grau'],
                    'periodo_letivo_colacacao_grau': row['periodo_letivo_colacacao_grau'],
                    'regime': regime,
                    'periodicidade': periodicidade,
                    # 'diploma_livro': row['livro'],
                    # 'diploma_folha': row['folha'],
                    # 'diploma_registro': row['registro'],
                    # 'diploma_data': row['data_diploma'],
                    'projeto_tipo': row['tipo_projeto'],
                    'projeto_titulo': row['titulo_projeto'],
                    'projeto_titulacao_orientador': row['titulacao_orientador_projeto'],
                    'projeto_orientador': row['orientador_projeto'],
                    'projeto_data_defesa': row['data_defesa'],
                    'projeto_situacao': row['situacao_projeto'],
                    'projeto_nota': row['nota_projeto'] and row['nota_projeto'] or 0,
                    'projeto_ch': row['ch_projeto'] and int(row['ch_projeto']) or 0,
                    'enade_data_ultimo': row['data_ultimo_enade'],
                    'enade_situacao': row['situacao_enade'],
                    'enade_ano_letivo': row['ano_enade'],
                    'enade_versao': row['versao_enade'],
                    'enade_data_prova': row['data_prova_enade'],
                    'enade_situacao_matricula': row['situacao_matricula_enade'],
                    'enade_justificativa': row['justificativa_enade'],
                    'accs': accs,
                }
            )
            row = cur.fetchone()
        cur.close()

        # dados do diploma
        if lista:
            sql = f"""
            select
                m.MATRICULA as matricula,
                d.COD_MATRICULA as codigo_qacademico,
                d.N_FORMULARIO as numero_formulario,
                d.N_LIVRO as livro,
                d.N_FOLHA as folha,
                d.N_REGISTRO as numero_registro,
                d.N_FORMULARIO as numero_formulario,
                d.DATA_EMISSAO as data_expedicao,
                d.DATA as data_impressao,
                d.PASTA as pasta,
                d.via as via
            from dbo.DIP_FORMULARIOS_DIPLOMAS d
            inner join dbo.MATRICULAS m on d.COD_MATRICULA = m.COD_MATRICULA
            where m.MATRICULA = '{aluno.matricula}'
            order by via
            """

            cur = self.get_connection().cursor()
            cur.execute(sql)
            for row in cur.fetchall():
                if row['livro']:
                    lista[0]['diploma_livro'] = row['livro']
                if row['folha']:
                    lista[0]['diploma_folha'] = row['folha']
                if row['numero_registro']:
                    lista[0]['diploma_registro'] = row['numero_registro']
                if row['data_expedicao']:
                    lista[0]['diploma_data'] = row['data_expedicao'] and row['data_expedicao'].date or None
            cur.close()

        disciplinas_sem_professor = []
        lista_aux = []
        consultas = []

        # Identificando as disciplinas associadas
        disciplinas_associadas = {}
        professores_associados = {}
        if lista:
            sql = 'select COD_DISCIPLINA_CO as a, COD_DISCIPLINA as b from CO_REQUISITOS_DISCIPLINAS c where c.COD_MATRIZ_CURRICULAR = {} and c.IMPORTAR_RESULTADO = 1;'.format(
                lista[0]['cod_matriz']
            )
            cur = self.get_connection().cursor()
            cur.execute(sql)
            row = cur.fetchone()
            while row:
                disciplinas_associadas[row['a']] = row['b']
                professores_associados[row['b']] = {}
                row = cur.fetchone()

        # Extraindo discipĺinas do histórico
        sql1 = f"""
            SELECT
                    h.ANo_Let as ano_letivo, h.Periodo_Let as periodo_letivo,
                    h.N_Periodo as periodo, h.Sigla_Disciplina as sigla,
                    h.Desc_disciplina as descricao, h.Cod_turma as turma,
                    h.Carga_Hor as carga_horaria, h.Carga_Hor as carga_horaria_cumprida, h.Nota as nota,
                    h.Percentual_Presenca as frequencia, h.Sit_Matricula_Pauta as situacao, dmc.OPTATIVA as optativa,
                    h.Observacoes as observacao,
                    PR.nome_pessoa as nome_professor,
                    ST_TIT.descricao as titulacao_professor, h.cod_disciplina as cod_disciplina
            FROM dbo.VW_HISTORICO_ESCOLAR_FINAL h
            INNER JOIN dbo.MATRICULAS m ON m.COD_MATRICULA = h.Cod_Matricula
            LEFT JOIN dbo.DISCIPLINAS_MATRIZES_CURRICULARES dmc on dmc.COD_DISCIPLINA = h.Cod_Disciplina AND DMC.COD_MATRIZ_CURRICULAR = m.COD_MATRIZ_CURRICULAR and dmc.COD_HABILITACAO = m.COD_HABILITACAO

            INNER JOIN dbo.PAUTAS p on p.COD_PAUTA = h.Cod_Pauta
            LEFT JOIN (VW_PROFESSORES PR LEFT JOIN SITUACOES_TABELAS ST_TIT ON ((ST_TIT.NOME_TABELA = 'PROFESSORES') AND (ST_TIT.NOME_COLUNA = 'TITULARIDADE') AND (PR.TITULARIDADE = ST_TIT.VALOR))) ON (P.COD_PROFESSOR = PR.COD_PROFESSOR)

            WHERE m.MATRICULA = '{aluno.matricula}' and h.Sit_Matricula_Pauta is not NULL
            ORDER BY h.ANo_Let, h.Periodo_Let, h.N_Periodo, h.Desc_Disciplina, h.cod_disciplina
        """
        consultas.append((False, sql1))
        # prática profissional exceto estágios
        sql2 = f"""
        select distinct
            p.ANO_LET as ano_letivo, p.PERIODO_LET as periodo_letivo, dmc.N_Periodo as periodo,
            d.SIGLA_DISCIPLINA as sigla, d.DESC_DISCIPLINA as descricao,
            d.CARGA_HOR as carga_horaria, d.CARGA_HOR as carga_horaria_cumprida,
            mp.NOTA as nota, mp.FREQUENCIA_ORIGEM as frequencia,
            mp.SIT_MATRICULA_PAUTA as situacao, dmc.OPTATIVA as optativa,
            mp.Observacoes as observacao, d.TIPO_DISCIPLINA, p.cod_disciplina as cod_disciplina
        from MATRICULAS m
            join MATRICULAS_PAUTAS mp on m.COD_MATRICULA = mp.COD_MATRICULA
            join PAUTAS p on p.COD_PAUTA = mp.COD_PAUTA
            join DISCIPLINAS d on p.COD_DISCIPLINA = d.COD_DISCIPLINA
            INNER JOIN dbo.DISCIPLINAS_MATRIZES_CURRICULARES dmc on dmc.COD_DISCIPLINA = d.Cod_Disciplina AND DMC.COD_MATRIZ_CURRICULAR = m.COD_MATRIZ_CURRICULAR and dmc.COD_HABILITACAO = m.COD_HABILITACAO
        where dmc.CARGA_HOR_PRATICA_PROFISSIONAL is not null
            and mp.SIT_MATRICULA_PAUTA in (4, 9)
            and p.TIPO_PAUTA != 9
            and m.MATRICULA =  '{aluno.matricula}'
        """
        consultas.append((True, sql2))

        # prática profissional somente estágios
        sql3 = f"""
            select
                p.ANO_LET as ano_letivo, p.PERIODO_LET as periodo_letivo, dmc.N_Periodo as periodo,
                d.SIGLA_DISCIPLINA as sigla, d.DESC_DISCIPLINA as descricao,
                d.CARGA_HOR as carga_horaria, sum(e.CARGA_HORARIA) as carga_horaria_cumprida,
                mp.NOTA as nota, mp.FREQUENCIA_ORIGEM as frequencia,
                mp.SIT_MATRICULA_PAUTA as situacao, dmc.OPTATIVA as optativa,
                mp.Observacoes as observacao, d.TIPO_DISCIPLINA,
                p.cod_disciplina as cod_disciplina
            from MATRICULAS m
                join MATRICULAS_PAUTAS mp on m.COD_MATRICULA = mp.COD_MATRICULA
                join PAUTAS p on p.COD_PAUTA = mp.COD_PAUTA
                join DISCIPLINAS d on p.COD_DISCIPLINA = d.COD_DISCIPLINA
                join ESTAGIOS e on e.COD_MATRICULA = m.COD_MATRICULA
                INNER JOIN dbo.DISCIPLINAS_MATRIZES_CURRICULARES dmc on dmc.COD_DISCIPLINA = d.Cod_Disciplina AND DMC.COD_MATRIZ_CURRICULAR = m.COD_MATRIZ_CURRICULAR and dmc.COD_HABILITACAO = m.COD_HABILITACAO
            where dmc.CARGA_HOR_PRATICA_PROFISSIONAL is not null
                and mp.SIT_MATRICULA_PAUTA in (4, 9)
                and m.MATRICULA =  '{aluno.matricula}'
                and p.TIPO_PAUTA = 9
                and e.COD_PAUTA = p.COD_PAUTA
            group by p.ANO_LET, p.PERIODO_LET, dmc.N_Periodo, d.SIGLA_DISCIPLINA, d.DESC_DISCIPLINA, d.CARGA_HOR,
            mp.NOTA, mp.FREQUENCIA_ORIGEM, mp.SIT_MATRICULA_PAUTA, dmc.OPTATIVA, mp.Observacoes, d.TIPO_DISCIPLINA, p.cod_disciplina
        """
        consultas.append((True, sql3))
        for is_pratica_profissional, sql in consultas:
            cur = self.get_connection().cursor()
            cur.execute(sql)
            row = cur.fetchone()
            while row:
                titulacao_professor = row.get('titulacao_professor') or ''
                if 'Mestre' in titulacao_professor:
                    titulacao_professor = 'Mestre(a)'
                elif 'Graduado' in titulacao_professor:
                    titulacao_professor = 'Graduado(a)'

                nota = row['nota']
                if settings.NOTA_DECIMAL and settings.CASA_DECIMAL == 1:
                    nota *= 10
                elif settings.NOTA_DECIMAL and settings.CASA_DECIMAL == 2:
                    nota *= 100
                param = {
                    'ano_periodo_letivo': '{}/{}'.format(row['ano_letivo'], row['periodo_letivo']),
                    'periodo': row['periodo'],
                    'sigla': row['sigla'],
                    'descricao': row['descricao'].upper(),
                    'turma': row.get('turma'),
                    'carga_horaria': int(row['carga_horaria'] or 0),
                    'carga_horaria_cumprida': int(row['carga_horaria_cumprida'] or 0),
                    'nota': nota,
                    'optativa': row['optativa'],
                    'frequencia': round(row['frequencia'] or 0),
                    'situacao': SITUACAO_DIARIO[row['situacao'] or 1],
                    'is_pratica_profissional': is_pratica_profissional,
                    'observacao': row['observacao'],
                    'nome_professor': row.get('nome_professor'),
                    'titulacao_professor': titulacao_professor,
                    'cod_disciplina': row.get('cod_disciplina'),
                }
                if row['periodo']:
                    lista.append(param)
                else:
                    lista_aux.append(param)
                if row.get('nome_professor') is None:
                    disciplinas_sem_professor.append(param)
                if row.get('cod_disciplina') in professores_associados:
                    professores_associados[row.get('cod_disciplina')].update(
                        nome_professor=row.get('nome_professor'), titulacao_professor=titulacao_professor
                    )
                row = cur.fetchone()
            cur.close()
        # definindo o nome/titulação do professor das disciplinas associadas (co-requisitos que importa resultado no Q-Acadêmico)
        for param in disciplinas_sem_professor:
            param.update(professores_associados.get(disciplinas_associadas.get(param['cod_disciplina']), {}))
        lista.extend(lista_aux)
        return lista

    def cadastrar_situacoes_integralizado_fase_escolar(self, verbose=True):
        sql = """
        insert into SITUACOES_TABELAS (NOME_TABELA, NOME_COLUNA, VALOR, DESCRICAO, VALOR_CHAR, ATIVO, CONSTANTE_SITUACOES_TABELAS)
        values ('MATRICULAS', 'SIT_MATRICULA', 101, 'Integralizado Fase Escolar', '101', 1, 'MATRICULAS.SIT_MATRICULA.101.101');

        insert into SITUACOES_TABELAS (NOME_TABELA, NOME_COLUNA, VALOR, DESCRICAO, VALOR_CHAR, ATIVO, CONSTANTE_SITUACOES_TABELAS)
        values ('MATRICULAS_PERIODOS', 'SIT_MATRICULA_PERIODO', 101, 'Integralizado Fase Escolar', '101', 1, 'MATRICULAS_PERIODOS.SIT_MATRICULA_PERIODO.101.101');

        """
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

    def atualizar_situacao_aluno_integralizado_fase_escolar(self, matricula_periodo):
        conn = self.get_connection()
        cur = conn.cursor()
        matricula = matricula_periodo.aluno.matricula
        ano = matricula_periodo.ano_letivo.ano
        periodo = matricula_periodo.periodo_letivo
        sql = f"""
            SELECT count(*) as n FROM MATRICULAS_PERIODOS where cod_matricula = (
                select cod_matricula from MATRICULAS WHERE MATRICULA = '{matricula}'
            ) and ano_let = {ano} and periodo_let = {periodo};
        """
        cur.execute(sql)
        row = cur.fetchone()
        if row['n'] == 0:
            sql = f"""
                UPDATE MATRICULAS set sit_matricula = 101 where MATRICULA = '{matricula}';
                INSERT INTO MATRICULAS_PERIODOS (cod_matricula, ano_let, periodo_let, sit_matricula_periodo)
                    VALUES ((select cod_matricula from MATRICULAS WHERE MATRICULA = '{matricula}'), {ano}, {periodo}, 101);
            """
        else:
            sql = f"""
                UPDATE MATRICULAS set sit_matricula = 101 where MATRICULA = '{matricula}';
                UPDATE MATRICULAS_PERIODOS set sit_matricula_periodo = 101 where cod_matricula = (
                    select cod_matricula from MATRICULAS WHERE MATRICULA = '{matricula}'
                ) and ano_let = {ano} and periodo_let = {periodo};
            """
        cur.execute(sql)
        conn.commit()

    def atualizar_situacoes_alunos_integralizados_qacademico(self):
        conn = self.get_connection()

        qs_alunos_integralizados = Aluno.objects.filter(data_integralizacao__isnull=False, codigo_academico__isnull=False)
        if qs_alunos_integralizados:
            for aluno in qs_alunos_integralizados:
                # Atualizando as situacoes das matriculas periodos no qacademico para 100 - Transferido SUAP
                sql = f"""
                  UPDATE MATRICULAS_PERIODOS set SIT_MATRICULA_PERIODO = 100
                  WHERE COD_MATRICULA = {aluno.codigo_academico} and ANO_LET = {aluno.ano_letivo_integralizacao.ano} and PERIODO_LET = {aluno.periodo_letivo_integralizacao}
                """

                cur = conn.cursor()
                cur.execute(sql)
                conn.commit()

            # Atualizando a situacao dos alunos no qacademico para 100 - Transferido SUAP
            cods_matricula = ','.join([f'{codigo}' for codigo in qs_alunos_integralizados.values_list('codigo_academico', flat=True)])
            if cods_matricula:
                sql = f"""
                  UPDATE MATRICULAS set SIT_MATRICULA = 100
                  WHERE COD_MATRICULA in ({cods_matricula})
                """

                cur = conn.cursor()
                cur.execute(sql)
                conn.commit()

    def desfazer_situacao_alunos_integralizados_qacademico(self, matricula):
        conn = self.get_connection()
        aluno = Aluno.objects.get(matricula=matricula)
        # Atualizando a situacao dos alunos no qacademico para 0 - Matriculado
        sql = f"""
          UPDATE MATRICULAS set SIT_MATRICULA = 0 WHERE COD_MATRICULA = '{aluno.codigo_academico}' AND SIT_MATRICULA = 100;
        """

        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        cur.close()

        # Atualizando as situacoes das matriculas periodos no qacademico para 1 - Matriculado
        if aluno.ano_letivo_integralizacao:
            sql = f"""
                UPDATE MATRICULAS_PERIODOS set SIT_MATRICULA_PERIODO = 1
                WHERE COD_MATRICULA = {aluno.codigo_academico} and ANO_LET = {aluno.ano_letivo_integralizacao.ano} and PERIODO_LET = {aluno.periodo_letivo_integralizacao}
            """

            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            cur.close()

    def is_curso_EAD(self, aluno):
        ead = False
        sql = f"""
                SELECT c.MODALIDADE_ENSINO AS ead
                FROM MATRICULAS m
                JOIN CURSOS c ON m.COD_CURSO = c.COD_CURSO
                WHERE m.MATRICULA = '{aluno.matricula}';
            """
        cur = self.get_connection().cursor()
        cur.execute(sql)
        row = cur.fetchone()
        if row:
            ead = row['ead']
            row = cur.fetchone()
        cur.close()
        return ead


# classe utlizada nos testes da importação e integralização de alunos
class MockDAO:
    def importar_cursos_campus(self, verbose: bool = True) -> None:
        diretoria = Diretoria.objects.all().order_by('-id')[0]
        data = {
            'codigo_academico': '1234',
            'descricao': 'Curso Importado',
            'descricao_historico': 'Curso Importado',
            'ativo': False,
            'codigo': '-{}'.format('1234'),
            'modalidade_id': Modalidade.MESTRADO,
            'data_inicio': None,
            'exige_enade': False,
            'periodicidade': CursoCampus.PERIODICIDADE_SEMESTRAL,
            'diretoria': diretoria,
        }
        CursoCampus.objects.get_or_create(**data)

    def importar_situacoes_matricula(self, verbose=True):
        pass

    def importar_situacoes_matricula_periodo(self, verbose=True):
        pass

    def importar_polos_ead(self, verbose=True):
        pass

    def importar_alunos(self, prefixo_matricula: str | None = None, verbose: bool = True) -> tuple[int, int]:
        # Cadastrando a pessoa física do aluno importado
        matricula = '270636252864'

        pf_args = {
            'nome': 'Carlos Breno Pereira Silva',
            'cpf': '876.028.295-90',
            'nascimento_data': '1969-03-04',
            'sexo': 'F',
        }
        pf_id = PessoaFisica.objects.obter_ou_criar(pf_args, Politica.CAUTELOSA)[0]
        curso_campus = CursoCampus.objects.all().order_by('-id')[0]
        forma_ingresso = FormaIngresso.objects.all().order_by('-id')[0]
        turno = Turno.objects.get(id=Turno.MATUTINO)
        estado = Estado.objects.get_or_create(nome='Rio Grande do Norte')[0]
        Cidade.objects.get_or_create(nome='', estado_id=estado.pk, cep_inicial='', cep_final='')
        ano_letivo = Ano.objects.get(ano='2013')

        # Cadastrando o aluno importado
        aluno_args = {
            'pessoa_fisica': pf_id,
            'situacao': SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO),
            'curso_campus': curso_campus,
            'codigo_academico': '4033',
            'matricula': matricula,
            'data_matricula': '2010-03-01',
            'dt_conclusao_curso': '2013-06-01',
            'periodo_atual': '2',
            'ano_letivo': ano_letivo,
            'periodo_letivo': '1',
            'ira': 8.3,
            'ano_let_prev_conclusao': '2013',
            'renda_per_capita': '15000',
            'numero_rg': '51274033',
            'uf_emissao_rg': estado,
            'turno': turno,
            'forma_ingresso': forma_ingresso,
            'nome_mae': 'Maria Martins Almeida',
            'nome_pai': 'João Martins Almeida',
            'pai_falecido': False,
            'mae_falecida': False,
            'logradouro': 'Estrada do Koyama',
            'numero': '635',
            'complemento': None,
            'cep': '08633-210',
            'telefone_principal': '2248-5127',
            'telefone_secundario': '5127-5127',
            'email_qacademico': 'CarolinaMartinsAlmeida@rhyta.com',
        }
        aluno = Aluno.objects.get_or_create(**aluno_args)[0]
        aluno.definir_ano_let_prev_conclusao()
        aluno.save()
        return (1, 0)

    def importar_matriculas_periodo(self, prefixo_matricula=None, verbose=True):
        ano_letivo = Ano.objects.get(ano='2013')
        aluno = Aluno.objects.all().order_by('-id')[0]
        m = MatriculaPeriodo()
        m.aluno = aluno
        m.ano_letivo = ano_letivo
        m.periodo_letivo = '1'
        m.periodo_matriz = '1'
        m.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.APROVADO)
        m.save()

        m = MatriculaPeriodo()
        m.aluno = aluno
        m.ano_letivo = ano_letivo
        m.periodo_letivo = '2'
        m.periodo_matriz = '2'
        m.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)
        m.save()

        return (2, 0)

    def atualizar_historico(self):
        pass

    def atualizar_username(self):
        aluno = Aluno.objects.all().order_by('-id')[0]
        user = User.objects.get(username=aluno.matricula)
        user.set_password('123')
        user.save()

    def importar_historico_resumo(self, matriculas, matriz_id, ano_letivo, periodo_letivo, validacao=True, ignorar_ultimo_periodo=False, task=None):
        if validacao:
            return []
        aluno = Aluno.objects.get(matricula=matriculas[0])
        matricula_periodo_atual = aluno.matriculaperiodo_set.all().order_by('id')[0]

        # equivalencias
        equivalencia_componente = EquivalenciaComponenteQAcademico()
        equivalencia_componente.q_academico = 123
        equivalencia_componente.sigla = 'XXX.0001'
        equivalencia_componente.descricao = 'Administração da propriedade rural'
        equivalencia_componente.carga_horaria = 10
        equivalencia_componente.save()

        # setando situacao em_aberto na última matricula do período
        if matricula_periodo_atual.situacao.id == SituacaoMatriculaPeriodo.MATRICULADO and not matricula_periodo_atual.matriculadiario_set.exists():
            matricula_periodo_atual.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)
            matricula_periodo_atual.save()

        # setando matriz no aluno
        if not aluno.matriz:
            aluno.matriz = Matriz.objects.get(pk=matriz_id)
            aluno.save()

        MatriculaDiarioResumida.objects.get_or_create(
            matricula_periodo=matricula_periodo_atual,
            equivalencia_componente=equivalencia_componente,
            media_final_disciplina=9.5,
            frequencia=95,
            situacao=MatriculaDiario.SITUACAO_APROVADO,
            codigo_turma='Teste',
        )

        aluno.data_integralizacao = datetime.datetime.now()
        aluno.atualizar_situacao('Migração do Aluno do Q-Acadêmico')

        return []

    def atualizar_situacoes_alunos_integralizados_qacademico(self):
        pass
