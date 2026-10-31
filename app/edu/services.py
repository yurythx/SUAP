import logging

from djtools.utils import normalizar_nome_proprio
from edu.models import (
    Aluno,
    ComponenteCurricular,
    CursoCampus,
    Diario,
)
from edu.models.diarios import ProfessorDiario
from edu.models.polos import Polo
from edu.models.turmas import ProfessorMinicurso, Turma
from rh.models import UnidadeOrganizacional

VERBOSE_NAMES = {
    'rg': 'RG',
    'uf': 'UF',
    'cep': 'CEP',
    'cpf': 'CPF',
    'inep': 'Código INEP',
    'nome': 'Nome',
    'bairro': 'Bairro',
    'genero': 'Gênero',
    'numero': 'Número',
    'racaCor': 'Raça/Cor',
    'serieAno': 'Série/Ano',
    'municipio': 'Município',
    'numeroNIS': 'NIS',
    'logradouro': 'Logradouro',
    'instituicao': 'Instituição',
    'orgaoEmisor': 'Orgão Emissor',
    'situacaoMat': 'Situação da Matrícula',
    'cpfResponsavel': 'CPF do Responsável',
    'dataNascimento': 'Data de Nascimento',
    'tipoDeficiencia': 'Tipo de Deficiência',
    'dataFimOuAprovacao': 'Data Fim da Matrícula',
    'nomeMaeEstudante': 'Nome da Mãe',
    'dataInicioMatricula': 'Data de Início da Matrícula',
    'numeroNISResponsavel': 'NIS do Responsável',
    'matriculaAteDoisMesesDoInicio': 'Matriculado até 2 Meses',
    'situacaoMatricula': 'Situação da Matrícula',
}

logger = logging.getLogger(__name__)


def serialize(obj, add_id=False):
    dados = {}
    if obj and add_id:
        dados.update(id=obj.id)
    if isinstance(obj, UnidadeOrganizacional):
        dados['descricao'] = obj.nome
        dados['sigla'] = obj.sigla
    elif isinstance(obj, ComponenteCurricular):
        dados['descricao'] = obj.componente.descricao
        dados['descricao_historico'] = obj.componente.descricao_historico
        dados['sigla'] = obj.componente.sigla
        dados['periodo'] = obj.periodo_letivo
        dados['tipo'] = obj.tipo
        dados['optativo'] = obj.optativo
        dados['qtd_avaliacoes'] = obj.qtd_avaliacoes
    elif isinstance(obj, Polo):
        dados['descricao'] = obj.descricao
    elif isinstance(obj, Aluno):
        dados.update(
            matricula=obj.matricula or '',
            nome=normalizar_nome_proprio(obj.pessoa_fisica.nome) or '',
            email=obj.email_notificacao or '',
            email_secundario=obj.email_pessoal or '',
            situacao=obj.situacao.ativo and 'ativo' or 'inativo',
            polo={'id': obj.polo.id, 'descricao': obj.polo.descricao} if obj.polo_id else {},
        )
    elif isinstance(obj, ProfessorDiario):
        dados.update(
            nome=normalizar_nome_proprio(obj.professor.vinculo.pessoa.nome) or '',
            email=obj.professor.vinculo.email_notificacao or '',
            email_secundario=obj.professor.vinculo.email_pessoal or '',
            tipo=obj.tipo.descricao,
            login=obj.professor.vinculo.user.username,
            status=obj.professor.vinculo.user.is_active and 'ativo' or 'inativo',
        )
    elif isinstance(obj, ProfessorMinicurso):
        dados.update(
            nome=normalizar_nome_proprio(obj.professor.vinculo.pessoa.nome) or '',
            email=obj.professor.vinculo.email_notificacao or '',
            email_secundario=obj.professor.vinculo.email_pessoal or '',
            tipo=obj.tipo.descricao if obj.tipo else '',
            login=obj.professor.vinculo.user.username,
            status=obj.professor.vinculo.user.is_active and 'ativo' or 'inativo',
        )
    elif isinstance(obj, Diario):
        componente = obj.componente_curricular.componente
        dados.update(
            situacao=obj.get_situacao_display() or '',
            descricao=componente.descricao or '',
            descricao_historico=componente.descricao_historico or '',
            sigla=componente.sigla or '',
            tipo='regular',
        )
    elif isinstance(obj, Turma):
        dados.update(codigo=obj.codigo or '')
    elif isinstance(obj, CursoCampus):
        dados.update(
            codigo=obj.codigo or '',
            nome=obj.descricao_historico or '',
            descricao=obj.descricao or '',
            autoinstrucional=obj.autoinstrucional,
            titulo_certificado_masculino=obj.titulo_certificado_masculino,
            titulo_certificado_feminino=obj.titulo_certificado_feminino,
            ch_total=obj.ch_total or 0,
            conteudo=[{'descricao': descricao, 'ch': ch} for descricao, ch in obj.conteudominicurso_set.values_list('descricao', 'ch')]
            if obj.ch_aula
            else [],
            modalidade={
                'id': obj.modalidade.id,
                'descricao': obj.modalidade.descricao,
                'nivel_ensino': {
                    'id': obj.modalidade.nivel_ensino.id,
                    'descricao': obj.modalidade.nivel_ensino.descricao,
                },
            },
        )
    return dados
