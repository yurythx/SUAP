"""Substrato que o Behave do Saúde montava antes dos fluxos de tela, agora por factories (#17486).

A carga reproduz os doze profissionais, o aluno-paciente, os cadastros gerais das quatro
features e o bloqueio futuro. Todas as operações são idempotentes porque os e2e não dão
flush e o CI reaproveita o banco entre execuções. ``cargo_saude`` e ``criar_aluno`` servem
também ao seed da doc de usuário (``saude/tests/doc/conftest.py``).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from django.contrib.auth.models import Group

from djtools.e2e_fixtures import SENHA_E2E, campus, servidor_com_login, setor

if TYPE_CHECKING:
    from edu.models import Aluno
    from rh.models import CargoEmprego, Servidor, Setor

MATRICULA_ALUNO = '20191101011111'
CPF_ALUNO = '559.454.350-31'
NOME_ALUNO = 'Aluno Saúde'

CAMPI = {'CEN': 'Campus Central', 'CZN': 'Campus Zona Norte'}

PAPEIS: dict[str, dict[str, str]] = {
    '111001': {'nome': 'CoordSaudeSistemico', 'grupo': 'Coordenador de Saúde Sistêmico', 'setor': 'CZN'},
    '111002': {'nome': 'Medico', 'grupo': 'Médico', 'setor': 'CZN'},
    '111003': {'nome': 'Odontologo', 'grupo': 'Odontólogo', 'setor': 'DIAC/CZN'},
    '111004': {'nome': 'Enfermeiro', 'grupo': 'Enfermeiro', 'setor': 'CEN'},
    '111005': {'nome': 'TecnicoEnfermagem', 'grupo': 'Técnico em Enfermagem', 'setor': 'DIAC/CEN'},
    '111006': {'nome': 'AuxiliarEnfermagem', 'grupo': 'Auxiliar de Enfermagem', 'setor': 'CZN'},
    '111007': {'nome': 'Fisioterapeuta', 'grupo': 'Fisioterapeuta', 'setor': 'CZN'},
    '111008': {'nome': 'Psicologo', 'grupo': 'Psicólogo', 'setor': 'DIAC/CZN'},
    '111009': {'nome': 'Nutricionista', 'grupo': 'Nutricionista', 'setor': 'DIAC/CZN'},
    '111010': {'nome': 'TecnicoSaudeBucal', 'grupo': 'Técnico em Saúde Bucal', 'setor': 'DIAC/CZN'},
    # Papéis que não são da assistência: o relatório de chefia e a verificação pública do
    # passaporte vacinal vivem em grupos próprios, fora do quadro clínico.
    '111011': {'nome': 'ChefeSetor', 'grupo': 'Chefe de Setor', 'setor': 'CZN'},
    '111012': {'nome': 'VerificadorPassaporte', 'grupo': 'Verificador de Passaporte Vacinal', 'setor': 'CZN'},
}

# Cargo de cada grupo clínico, como o ``step_seguintes_usuarios`` do behave dava: as fichas
# gravam a especialidade por ``Especialidades.CARGO_ESPECIALIDADE_GRUPO_ID[cargo.codigo]``,
# então profissional sem um destes cargos derruba o salvamento com ``KeyError``. Grupo fora
# daqui fica com o cargo padrão da factory.
CARGOS: dict[str, tuple[str, str, str]] = {
    'Médico': ('701047', 'MEDICO-AREA', 'NS'),
    'Odontólogo': ('701064', 'ODONTOLOGO - 40 HORAS', 'NS'),
    'Enfermeiro': ('701029', 'ENFERMEIRO-AREA', 'NS'),
    'Técnico em Enfermagem': ('701233', 'TECNICO EM ENFERMAGEM', 'NI'),
    'Auxiliar de Enfermagem': ('701411', 'AUXILIAR DE ENFERMAGEM', 'NI'),
    'Técnico em Saúde Bucal': ('701241', 'TECNICO EM HIGIENE DENTAL', 'NI'),
    'Fisioterapeuta': ('701038', 'FISIOTERAPEUTA', 'NI'),
    'Psicólogo': ('701060', 'PSICOLOGO-AREA', 'NI'),
    'Nutricionista': ('701055', 'NUTRICIONISTA-HABILITACAO', 'NI'),
}

ORIENTACOES = (
    ('Orientação A', 'Descrição orientação A'),
    ('Orientação B', 'Descrição orientação B'),
    ('Orientação C', 'Descrição orientação C'),
    ('Orientação D', 'Descrição orientação D'),
    ('Orientação E', 'Descrição orientação E'),
)
RECEITAS = (
    ('Receita A', 'Descrição receita A'),
    ('Receita B', 'Descrição receita B'),
    ('Receita C', 'Desfrição receita C'),
    ('Receita D', 'Descrição receita D'),
    ('Receita E', 'Descrição receita E'),
)
AVALIACOES_GASTROINTESTINAIS = (
    'Pirose',
    'Náuseas',
    'Vômitos',
    'Dores abdominais',
    'Distensão abdominal',
    'Meteorismo/Flatulência',
    'Obstipação intestina',
    'Diarreia aguda',
    'Intolerância à lactose',
    'Patologia (DRGE/Gastrite/Doença Inflamatória Instestinal)',
    'Outros',
)
RESTRICOES_ALIMENTARES = (
    'Leite e derivados',
    'Ovos',
    'Oleaginosas',
    'Soja',
    'Peixe',
    'Crustáceos',
    'Amendoim e nozes',
    'Glúten',
    'Chocolates',
    'Corantes',
    'Aditivos químicos',
    'Frutas',
    'Outros',
)
MOTIVOS_NUTRICAO = (
    'Perda de peso',
    'Ganho de peso',
    'Ganho de massa muscular',
    'Manutenção do peso',
    'Prática de atividade física',
    'Dislipidemias',
    'Doenças do Trato Gastrointestinal',
    'Intolerância Alimentar',
    'Alergia Alimentar',
    'Transtorno Alimentar',
    'Patologias',
    'Alimentação saudável',
    'Outros',
)
DIAGNOSTICOS_NUTRICIONAIS = (
    'Hipermetabolismo (necessidades energéticas aumentadas)',
    'Gasto energético aumentado',
    'Hipometabolismo (necessidades energéticas diminuídas)',
    'Ingestão insuficiente de energia',
    'Ingestão excessiva de energia',
    'Ingestão oral insuficiente de alimento/bebida',
    'Ingestão oral excessiva de alimento/bebida',
    'Ingestão excessiva de nutrição enteral/parenteral',
    'Ingestão inadequada de nutrição enteral/parenteral',
    'Ingestão insuficiente de líquidos',
    'Ingestão excessiva de líquidos',
    'Ingestão insuficiente de substâncias bioativas',
    'ingestão insuficiente de líquidos',
    'Ingestão excessiva de substâncias bioativas',
    'Ingestão excessiva de álcool',
    'Necessidades aumentadas de nutriente (especificar)',
    'Desnutrição calórico-proteica evidente',
    'Ingestão insuficiente de energia e proteína',
    'Necessidades diminuídas de nutriente (especificar)',
    'Desequilíbrio de nutrientes',
    'Ingestão insuficiente de lipídios',
    'Ingestão excessiva de lipídios',
    'Ingestão inapropriada de alimentos ricos em gordura (especificar)',
    'Ingestão insuficiente de proteínas',
    'Ingestão excessiva de proteínas',
    'Ingestão inapropriada de aminoácidos (especificar)',
    'Ingestão insuficiente de carboidratos',
    'Ingestão excessiva de carboidratos',
    'Ingestão inapropriada de tipos de carboidratos (especificar)',
    'Ingestão irregular de carboidratos',
    'Ingestão insuficiente em fibras',
    'Ingestão excessiva de fibras',
    'Ingestão insuficiente de vitaminas (especificar)',
    'Ingestão excessiva de vitaminas (especificar)',
    'Ingestão insuficiente de minerais (especificar)',
    'Ingestão excessiva de minerais (especificar)',
    'Dificuldade na deglutição',
    'Dificuldade na mastigação',
    'Dificuldade na amamentação',
    'Alteração na função GI',
    'Alteração na utilização de nutrientes',
    'Alteração nos valores laborais relacionados com a nutrição',
    'Interação fármaco-nutriente',
    'Baixo peso',
    'Perda de peso involuntária',
    'Sobrepeso/obesidade',
    'Ganho de peso involuntário',
    'Deficiência de conhecimento relacionado com os alimentos e a nutrição',
    'Atitudes/crenças perigosas quanto aos alimentos ou tópicos relacionados com a nutrição',
    'Despreparo para mudança na dieta/estilo de vida',
    'Deficiência no automonitoramento',
    'Distúrbio no padrão alimentar',
    'Aderência limitada às recomendações relacionadas com a nutrição',
    'Escolhas alimentares indesejáveis',
    'Inatividade física',
    'Excesso de exercício',
    'Incapacidade ou falta de desejo para conduzir o autocuidado',
    'Alteração da capacidade de preparar alimentos/refeições',
    'Qualidade de vida e nutrição deficientes',
    'Dificuldade na autoalimentação',
    'Ingestão de alimento não seguro',
    'Acesso limitado aos alimentos',
)
MOTIVOS_PSICOLOGIA = (
    'Demanda Espontânea',
    'Encaminhado pelo Plantão psicológico/COASS/DIGPE',
    'Encaminhado pelo Serviço de Saúde',
    'Encaminhado por Docente',
    'Encaminhado por ETEP',
    'Encaminhado por Familiares',
    'Encaminhado por Outro Aluno',
    'Encaminhado por outros servidores',
    'Encaminhado por Terceirizados',
    'Encaminhamento Externo',
)
QUEIXAS_PSICOLOGICAS = (
    'Ansiedade',
    'Autoestima/autoimagem',
    'Automutilação',
    'Conflito Interpessoal - família',
    'Conflito Interpessoal - professores/servidores',
    'Conflito Interpessoal - relacionamentos afetivos',
    'Conflito Interpessoal - turma',
    'Conflitos religiosos',
    'Desmotivação',
    'Dificuldade de aprendizagem/concentração',
    'Ideação suicida',
    'Ideias obsessivas',
    'Impulsividade',
    'Organização de horário de estudo',
    'Orientação Profissional',
    'Outros',
    'Perdas/luto',
    'Problemas com a homoafetividade',
    'Problemas com pais ou parentes',
    'Problemas no relacionamento/ comunicação com os pais/ familiares',
    'Queixas escolares (dificuldades com o conteúdo)',
    'Queixas Escolares - Dificuldades com o conteúdo',
    'Queixas Escolares - Dificuldades de Aprendizagem',
    'Queixas Escolares - Dificuldades de Concentração',
    'Queixas psicossomáticas',
    'Questões ligadas a sexualidade',
    'Questões sobre a adaptação à escola',
    'Sintomas depressivos',
    'Tensão pré-menstrual (TPM)',
    'Transtorno mental diagnosticado',
    'Uso de álcool ou outras drogas',
    'Vítima de violência / abuso',
)


def cargo_saude(grupo: str) -> dict[str, CargoEmprego]:
    """Kwargs de ``servidor_com_login`` com o cargo do grupo clínico (vazio fora de ``CARGOS``)."""
    from rh.tests.factories import CargoEmpregoFactory, GrupoCargoEmpregoFactory

    if grupo not in CARGOS:
        return {}
    codigo, nome, escolaridade = CARGOS[grupo]
    grupo_cargo = GrupoCargoEmpregoFactory(codigo='313', nome='Grupo Saude 1')
    return {'cargo_emprego': CargoEmpregoFactory(codigo=codigo, nome=nome, sigla_escolaridade=escolaridade, grupo_cargo_emprego=grupo_cargo)}


def setor_do_papel(sigla: str) -> Setor:
    """Campus (``CZN``) ou setor sob campus (``DIAC/CZN``) da árvore que o behave usava."""
    if '/' in sigla:
        sigla_campus = sigla.split('/')[1]
        return setor(sigla, campus(sigla_campus, CAMPI[sigla_campus]), 'Diretoria Acadêmica')
    return campus(sigla, CAMPI[sigla])


def criar_servidor(matricula: str) -> Servidor:
    """Cria ou recompõe um profissional com setor, cargo, senha e grupo da feature."""
    dados = PAPEIS[matricula]
    servidor = servidor_com_login(
        matricula,
        setor_do_papel(dados['setor']),
        staff=True,
        # O e-mail pessoal é o único endereço que o ``solicitar_autenticacao_2fa`` aceita. Sem ele,
        # `enviar_mensagem_aluno` — a única rota do Saúde protegida por 2FA — nunca chega ao formulário.
        email_pessoal=f'{dados["nome"].lower()}@pessoal.ifrn.edu.br',
        pessoa_fisica__nome=dados['nome'],
        **cargo_saude(dados['grupo']),
    )
    usuario = servidor.get_user()
    assert usuario is not None, f'o servidor {matricula} não possui usuário'
    usuario.groups.set([Group.objects.get(name=dados['grupo'])])
    return servidor


def criar_aluno(nome: str = NOME_ALUNO) -> Aluno:
    """Cria o aluno-paciente da feature com vínculo ativo no campus CZN (a doc passa outro ``nome``)."""
    from comum.models import Ano
    from edu.models import (
        Aluno,
        CursoCampus,
        Diretoria,
        MatriculaPeriodo,
        Modalidade,
        NivelEnsino,
        SituacaoMatricula,
        SituacaoMatriculaPeriodo,
        Turma,
        Turno,
    )
    from rh.models import PessoaFisica

    diac = setor_do_papel('DIAC/CZN')
    diretoria = Diretoria.objects.filter(setor=diac).first()
    if diretoria is None:
        diretoria = Diretoria.objects.create(setor=diac)

    modalidade, _ = Modalidade.objects.update_or_create(
        descricao='Técnico Integrado', defaults={'nivel_ensino': NivelEnsino.objects.get(pk=NivelEnsino.MEDIO)}
    )
    curso, _ = CursoCampus.objects.update_or_create(
        codigo='TECINFO-SAUDE-E2E',
        defaults={
            'descricao': 'Técnico em Informática - Saúde E2E',
            'diretoria': diretoria,
            'ativo': True,
            'modalidade': modalidade,
        },
    )

    pessoa, _ = PessoaFisica.objects.get_or_create(
        cpf=CPF_ALUNO,
        defaults={'nome': nome, 'nome_registro': nome, 'nascimento_data': date(2000, 1, 1), 'sexo': 'M'},
    )
    pessoa.nome = nome
    pessoa.nome_registro = nome
    pessoa.nascimento_data = date(2000, 1, 1)
    pessoa.sexo = 'M'
    pessoa.eh_aluno = True
    pessoa.save()

    aluno, _ = Aluno.objects.update_or_create(
        matricula=MATRICULA_ALUNO,
        defaults={
            'pessoa_fisica': pessoa,
            'ano_letivo': Ano.objects.get_or_create(ano='2019')[0],
            'periodo_letivo': 1,
            'periodo_atual': 1,
            'situacao': SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO),
            'ano_let_prev_conclusao': 2022,
            'curso_campus': curso,
        },
    )
    usuario = aluno.get_user()
    assert usuario is not None, 'o aluno sintético não possui usuário'
    usuario.set_password(SENHA_E2E)
    usuario.is_staff = True
    usuario.save()
    usuario.groups.set([Group.objects.get(name='Aluno')])

    # Turma e matrícula em período: a presença em atividade de grupo é registrada pelo aluno
    # matriculado na turma da atividade (`registrar_presenca_atividade_grupo`), e o formulário
    # de atividade só oferece as turmas que existem.
    ano = Ano.objects.get(ano='2019')
    turma = Turma.objects.filter(ano_letivo=ano, periodo_letivo=1, periodo_matriz=1, curso_campus=curso).first()
    if turma is None:
        turma = Turma.objects.create(ano_letivo=ano, periodo_letivo=1, periodo_matriz=1, turno=Turno.objects.first(), curso_campus=curso)
    MatriculaPeriodo.objects.update_or_create(
        aluno=aluno,
        ano_letivo=ano,
        periodo_letivo=1,
        defaults={'turma': turma, 'situacao': SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)},
    )
    return aluno


def _catalogos_nutricao_e_psicologia() -> None:
    """Catálogos de nutrição e psicologia das features (extraído para a complexidade ≤ 10)."""
    from saude.models import (
        AvaliacaoGastroIntestinal,
        DiagnosticoNutricional,
        MotivoAtendimentoNutricao,
        MotivoChegadaPsicologia,
        OrientacaoNutricional,
        QueixaPsicologica,
        ReceitaNutricional,
        RestricaoAlimentar,
    )

    for titulo, descricao in ORIENTACOES:
        OrientacaoNutricional.objects.update_or_create(titulo=titulo, defaults={'descricao': descricao})
    for titulo, descricao in RECEITAS:
        ReceitaNutricional.objects.update_or_create(titulo=titulo, defaults={'descricao': descricao})
    for descricao in AVALIACOES_GASTROINTESTINAIS:
        AvaliacaoGastroIntestinal.objects.get_or_create(descricao=descricao)
    for descricao in RESTRICOES_ALIMENTARES:
        RestricaoAlimentar.objects.get_or_create(descricao=descricao)
    for descricao in MOTIVOS_NUTRICAO:
        MotivoAtendimentoNutricao.objects.get_or_create(descricao=descricao)
    for descricao in DIAGNOSTICOS_NUTRICIONAIS:
        DiagnosticoNutricional.objects.get_or_create(descricao=descricao)
    for descricao in MOTIVOS_PSICOLOGIA:
        MotivoChegadaPsicologia.objects.get_or_create(descricao=descricao)
    for descricao in QUEIXAS_PSICOLOGICAS:
        QueixaPsicologica.objects.get_or_create(descricao=descricao)


def criar_campus_e_cadastros_gerais() -> None:
    """Reproduz os cadastros auxiliares informados nas features do Saúde."""
    from saude.models import (
        AnoReferenciaAcaoEducativa,
        CategoriaExameLaboratorial,
        Cid,
        FrequenciaPraticaAlimentar,
        GrupoAlimento,
        GrupoAtividade,
        ObjetivoAcaoEducativa,
        OpcaoRespostaMarcadorNutricao,
        PerguntaMarcadorNutricao,
        ProcedimentoEnfermagem,
        ProcedimentoFisioterapia,
        ProcedimentoMultidisciplinar,
        ProcedimentoOdontologia,
        TipoAtendimentoPsicologia,
        TipoAtividadeGrupo,
        TipoExameLaboratorial,
        TipoIntoleranciaAlimentar,
        TipoRefeicao,
        Vacina,
    )

    campus('CC', 'CCampus1')
    TipoAtividadeGrupo.objects.get_or_create(descricao='Reunião')
    AnoReferenciaAcaoEducativa.objects.get_or_create(ano='2019')
    ObjetivoAcaoEducativa.objects.get_or_create(descricao='Novo Objetivo de Ação Educativa')
    CategoriaExameLaboratorial.objects.get_or_create(nome='Perfil Glicêmico')

    # O formulário de marcadores monta um campo por pergunta ativa (e um por alimento da
    # frequência), então sem opção de resposta e sem alimento a tela não tem o que preencher.
    pergunta, _ = PerguntaMarcadorNutricao.objects.update_or_create(
        pergunta='Nova Pergunta', defaults={'tipo_resposta': PerguntaMarcadorNutricao.UNICA_ESCOLHA}
    )
    for valor in ('Sim', 'Não'):
        OpcaoRespostaMarcadorNutricao.objects.update_or_create(pergunta=pergunta, valor=valor)
    FrequenciaPraticaAlimentar.objects.update_or_create(descricao='Feijão', defaults={'valor_recomendado': 5})

    _catalogos_nutricao_e_psicologia()
    TipoAtendimentoPsicologia.objects.get_or_create(descricao='Atendimento aos pais')
    ProcedimentoEnfermagem.objects.get_or_create(denominacao='Outros')
    ProcedimentoOdontologia.objects.get_or_create(denominacao='Outros')

    # O formulário de Nutrição e Alimentação (aba da avaliação biomédica) pergunta as refeições
    # do dia, as alergias e as intolerâncias: sem estes catálogos os campos obrigatórios não
    # têm nenhuma opção para escolher. O CID é o mesmo caso na hipótese diagnóstica — o
    # `carga_saude_cid.sql` do app não é carregado por nenhum comando.
    for refeicao in ('Café da manhã', 'Almoço', 'Jantar'):
        TipoRefeicao.objects.get_or_create(descricao=refeicao)
    GrupoAlimento.objects.get_or_create(descricao='Leite e derivados')
    TipoIntoleranciaAlimentar.objects.get_or_create(descricao='Lactose')
    GrupoAtividade.objects.get_or_create(descricao='Assistir televisão')
    Cid.objects.update_or_create(codigo='A001', defaults={'denominacao': 'Colera devida a Vibrio cholerae 01', 'ativo': True})

    # Catálogos que as telas de fisioterapia, multidisciplinar, vacinação e exames exigem para
    # ter o que oferecer no formulário (o behave não os criava porque não chegava neles).
    for denominacao in ('Fisioterapia Respiratória', 'Cinesioterapia'):
        ProcedimentoFisioterapia.objects.get_or_create(denominacao=denominacao)
    ProcedimentoMultidisciplinar.objects.get_or_create(denominacao='Atendimento Multiprofissional')
    Vacina.objects.get_or_create(nome='Tríplice Viral', defaults={'doses': 2})
    categoria_exame, _ = CategoriaExameLaboratorial.objects.get_or_create(nome='Perfil Glicêmico')
    TipoExameLaboratorial.objects.get_or_create(
        categoria=categoria_exame,
        nome='Glicemia de jejum',
        defaults={'unidade': 'mg/dL', 'valor_referencia': '70 a 99 mg/dL'},
    )


def criar_chefia() -> None:
    """Liga o chefe de setor ao setor CZN, como o `relatorio_passaporte_vacinal_chefia` exige.

    O relatório procura o histórico de função de chefia do usuário (`Funcao.eh_funcao_chefia`)
    para descobrir de quais setores ele responde — sem esse vínculo de RH a tela não tem o que
    listar.
    """
    from rh.models import Servidor, ServidorFuncaoHistorico
    from rh.tests.factories import FuncaoChefiaFactory

    servidor = Servidor.objects.get(matricula='111011')
    setor_suap = setor_do_papel('CZN')
    ServidorFuncaoHistorico.objects.update_or_create(
        servidor=servidor,
        funcao=FuncaoChefiaFactory(),
        data_inicio_funcao='2018-01-01',
        defaults={'setor': setor_suap, 'setor_suap': setor_suap},
    )


def criar_bloqueio() -> None:
    """Cria o bloqueio futuro do paciente exatamente como o step legado."""
    from edu.models import Aluno
    from rh.models import Servidor
    from saude.models import BloqueioAtendimentoSaude

    aluno = Aluno.objects.get(matricula=MATRICULA_ALUNO)
    profissional = Servidor.objects.get(matricula='111001')
    BloqueioAtendimentoSaude.objects.get_or_create(
        vinculo_paciente=aluno.get_vinculo(),
        vinculo_profissional=profissional.get_vinculo(),
        data=datetime.strptime('01/29/2050', '%m/%d/%Y'),
    )


def limpar_execucao_anterior() -> None:
    """Remove a cadeia clínica fixa e a agenda deixadas por uma execução e2e anterior."""
    from saude.models import Atendimento, BloqueioAtendimentoSaude, HorarioAtendimento, Prontuario
    from edu.models import Turma

    prontuarios = Prontuario.objects.filter(vinculo__pessoa__pessoafisica__cpf=CPF_ALUNO)
    Atendimento.objects.filter(prontuario__in=prontuarios).delete()
    prontuarios.delete()

    # A agenda e os bloqueios são criados pelos próprios testes e não têm sentinela: sem
    # limpá-los, a segunda execução encontra o horário já reservado/cancelado e o paciente
    # já bloqueado, e as telas deixam de oferecer os botões que o teste clica.
    HorarioAtendimento.objects.filter(cadastrado_por_vinculo__user__username__in=PAPEIS).delete()
    BloqueioAtendimentoSaude.objects.filter(vinculo_profissional__user__username__in=PAPEIS).delete()

    # `Turma.save` reescreve `codigo` e `descricao`, então a turma do aluno não tem sentinela
    # natural: apagá-la e recriá-la é o que mantém uma só turma por execução.
    Turma.objects.filter(curso_campus__codigo='TECINFO-SAUDE-E2E').delete()


def montar() -> None:
    """Monta o substrato completo na ordem exigida pelos vínculos e pelo bloqueio."""
    limpar_execucao_anterior()
    criar_campus_e_cadastros_gerais()
    for matricula in PAPEIS:
        criar_servidor(matricula)
    criar_aluno()
    criar_chefia()
    criar_bloqueio()


__all__ = ['CPF_ALUNO', 'MATRICULA_ALUNO', 'NOME_ALUNO', 'PAPEIS', 'cargo_saude', 'criar_aluno', 'montar']
