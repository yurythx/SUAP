from datetime import datetime

from django.core.exceptions import ValidationError

from comum.models import APIExterna
from edu.importador import Modalidade
from edu.models import Aluno, Aula, Deficiencia, Diario, TipoNEE


class AlunoPeDeMeiaSerializer:
    """
    Serializer para representação de objeto da classe Aluno para estrutura JSON definida pela API do programa Pé de Meia
    disponível em: http://nees.pages.ufal.br/frequencia-escolar/api-cmde-spec/
    """

    def __init__(self, aluno: Aluno, is_update=False):
        """
        :param aluno: Aluno instance
        :param is_update: Indica se será realizada uma atualização do aluno (HTTP Patch) e retorna somente os atributos atualizaveis conforme
        """
        self.aluno = aluno
        self.is_update = is_update

    def get_json(self):
        try:
            json_retorno = {
                'cpf': self.aluno.pessoa_fisica.cpf.replace('.', '').replace('-', '') if self.aluno.pessoa_fisica.cpf else '',
                'numeroNIS': self.aluno.nis if self.aluno.nis and self.aluno.nis != '0' else None,
                'nome': self.aluno.pessoa_fisica.nome_registro,
                'email': self.aluno.email_notificacao,
                'telefone': (self.aluno.telefone_principal or '').replace(' ', '').replace('-', '').replace('(', '').replace(')', ''),
                'dataNascimento': self.aluno.pessoa_fisica.nascimento_data.strftime('%Y-%m-%d'),
                'matriculaRede': self.aluno.matricula,
                'instituicao': self._get_CodInstituicao(),
                'inep': self.aluno.curso_campus.diretoria.setor.uo.codigo_inep,
                'dataInicioMatricula': self.aluno.data_matricula.strftime('%Y-%m-%d'),
                'dataFimOuAprovacao': self.aluno.dt_conclusao_curso.strftime('%Y-%m-%d') if self.aluno.dt_conclusao_curso else '',
                'serieAno': 62
                if self.aluno.curso_campus.modalidade_id == Modalidade.INTEGRADO_EJA.value
                else {1: 30, 2: 31, 3: 32, 4: 33}[self.aluno.periodo_atual],
                'racaCor': {7: 0, 3: 1, 2: 2, 1: 3, 4: 4, 5: 5, None: 0}[self.aluno.raca.pk if self.aluno.raca else None],
                'logradouro': self.aluno.logradouro.replace(';', ' - ').replace(',', ' - ') if self.aluno.logradouro else '',
                'bairro': self.aluno.bairro or '',
                'numero': self.aluno.numero[0:6] if self.aluno.numero else '00',
                'cep': self.aluno.cep.replace('.', '').replace('-', '') if self.aluno.cep else '',
                'municipio': self.aluno.cidade.codigo if self.aluno.cidade else None,
                'uf': self.aluno.cidade.estado.id if self.aluno.cidade_id else None,
                'genero': {'M': 1, 'F': 2, None: 0}[self.aluno.pessoa_fisica.sexo],
                'cpfResponsavel': self.aluno.cpf_responsavel.replace('.', '').replace('-', '') if self.aluno.cpf_responsavel else None,
                'nomeMaeEstudante': self.aluno.nome_mae,
                'numeroNISResponsavel': '',
                'rg': self.aluno.numero_rg or '',
                'orgaoEmissor': self.aluno.orgao_emissao_rg.nome[0:10] if self.aluno.orgao_emissao_rg_id else '',
                'situacaoMatricula': self._get_situacaoMat(),
                'tipoDeficiencia': self._get_tipoDeficiencia(self.aluno.id),
                'matriculaAteDoisMesesDoInicio': self._get_matriculaAteDoisMesesdoInicio(),
                'dataInicioPeriodoLetivo': self._get_data_inicio_periodo_letivo().strftime('%Y-%m-%d')
                if self._get_data_inicio_periodo_letivo()
                else None,
                'formaOrganizacaoTurma': 2 if self.aluno.curso_campus.modalidade_id == Modalidade.INTEGRADO_EJA else 1,
                'turmaOrganizacaoQuantidadeTotal': self.aluno.matriz.qtd_periodos_letivos,
                'estudanteEjaAnoPeriodo': self.get_percentual_estudante_eja_ano_periodo(),
            }

            if self.is_update:
                # Estes atributos não são aceitam atualização pela API
                del json_retorno['cpf']
                del json_retorno['instituicao']
                del json_retorno['inep']
                del json_retorno['dataInicioMatricula']
                del json_retorno['dataFimOuAprovacao']
                del json_retorno['serieAno']
                del json_retorno['situacaoMatricula']
                del json_retorno['matriculaAteDoisMesesDoInicio']

            return json_retorno
        except Exception as e:
            raise ValidationError(f'[API_PE_DE_MEIA] Erro ao serializar aluno com matrícula {self.aluno.matricula} em JSON - Detalhes: {e}')

    def _get_tipoDeficiencia(self, aluno_id):
        """
        Códigos possíveis:
        0: Não informado
        1: Não possui
        2: Cegueira
        3: Deficiência auditiva
        4: Deficiência física
        5: Deficiência intelectual
        6: Surdez
        7: Surdocegueira
        8: Deficiência múltipla
        9: Transtorno do Espectro autista
        10: Altas habilidades/superdotação
        """
        mapeamento_deficiencia = {
            1: '2',  # Baixa visão => Cegueira
            2: '2',  # Visão monocular => Cegueira
            3: '2',  # Cegueira => Cegueira
            4: '3',  # Deficiência auditiva => Deficiência auditiva
            5: '4',  # Deficiência física => Deficiência física
            6: '5',  # Deficiência intelectual => Deficiência intelectual
            7: '6',  # Surdez => Surdez
            8: '7',  # Surdocegueira => Surdocegueira
            9: '9',  # Transtorno de Espectro Autista (TEA) => Transtorno do Espectro autista
        }
        tipos_deficiencia = set()

        try:
            deficiencias = set(Deficiencia.objects.filter(aluno=aluno_id).values_list('classificacao_educacenso', flat=True))
            for d in deficiencias:
                if d in mapeamento_deficiencia:
                    tipos_deficiencia.add(mapeamento_deficiencia[d])

            if TipoNEE.objects.filter(aluno=aluno_id, classificacao_educacenso=TipoNEE.ALTAS_HABILIDADES).exists():
                tipos_deficiencia.add('10')

        except Exception as e:
            raise ValidationError(
                f'[API_PE_DE_MEIA] Erro ao obter atributo tipoDeficiencia do aluno com matrícula {self.aluno.matricula} - Detalhes: {e}'
            )

        return tipos_deficiencia or {'1'}

    def _get_situacaoMat(self):
        if self.aluno.situacao.ativo:
            return 1
        return 0

    def _get_data_inicio_periodo_letivo(self):
        if not hasattr(self, '_data_inicio_periodo_letivo'):
            ano = datetime.now().year
            self._data_inicio_periodo_letivo = (
                Diario.objects.filter(ano_letivo__ano=ano, matriculadiario__matricula_periodo__aluno=self.aluno)
                .order_by('calendario_academico__data_inicio')
                .values_list('calendario_academico__data_inicio', flat=True)
                .first()
            )
        return self._data_inicio_periodo_letivo

    def _get_matriculaAteDoisMesesdoInicio(self):
        """
        Informar se o estudante realizou a matricula em ate dois meses do início do período letivo
        Valores possíveis: boolean
        """
        ano = datetime.now().year
        data_inicio_periodo_letivo = self._get_data_inicio_periodo_letivo()
        data_matricula_periodo = (
            Aula.objects.filter(
                registro_frequencia_confirmado=True,
                professor_diario__diario__ano_letivo__ano=ano,
                professor_diario__diario__matriculadiario__matricula_periodo__aluno=self.aluno,
            )
            .order_by('data')
            .values_list('data', flat=True)
            .first()
        )
        if data_matricula_periodo and data_inicio_periodo_letivo and (data_matricula_periodo >= data_inicio_periodo_letivo):
            if (data_matricula_periodo - data_inicio_periodo_letivo).days <= 60:
                return True
        return False

    def _get_CodInstituicao(self):
        try:
            api_externa_pedemeia = APIExterna.PEDEMEIA
            if api_externa_pedemeia.ativo:
                api_service = api_externa_pedemeia.get_service()
                sucesso, lista_unidades = api_service.obter_unidades_ensino()
                if sucesso and self.aluno.curso_campus.diretoria.setor.uo.codigo_inep:
                    unidade_encontrada = next(
                        (unidade for unidade in lista_unidades if unidade['inep'] == self.aluno.curso_campus.diretoria.setor.uo.codigo_inep), None
                    )
                    if unidade_encontrada:
                        co_instituicao = unidade_encontrada['id']
                        # print(f'INEP {self.aluno.curso_campus.diretoria.setor.uo.codigo_inep} - CO_INSTITUICAO {co_instituicao}')
                        return co_instituicao
        except Exception as e:
            raise ValidationError(
                f'[API_PE_DE_MEIA] Erro ao obter código da instituição do aluno com matrícula {self.aluno.matricula} - Detalhes: {e}'
            )

    def get_percentual_estudante_eja_ano_periodo(self):
        if self.aluno.percentual_ch_cumprida:
            if self.aluno.percentual_ch_cumprida > 60:
                return 3
            elif self.aluno.percentual_ch_cumprida > 30:
                return 2
        return 1
