"""Alvos dos modelos de URL usados pelo smoke de rota (``test_15``→``test_18``).

Os testes escrevem a rota como literal com marcador — ``'/edu/diario/{diario}/'`` — e este
módulo diz o que cada marcador vale. Duas razões para o marcador existir:

* o gate do modo 2 (``bin/scripts/paridade_e2e.py edu --rotas``) casa a rota declarada em
  ``edu/urls.py`` contra as strings literais iniciadas por ``/`` nos ``test_*.py``, trocando
  ``<int:pk>`` por ``[^/]+``. ``{diario}`` não tem barra, então o literal casa — e continua
  legível como a rota que é;
* nenhum pk mágico entra no teste. Todo alvo sai por consulta do que a cadeia 01→14 já criou;
  se o objeto não existir, ``_pk`` falha dizendo qual model faltou, em vez de o smoke bater
  num 404 e parecer bug de view.

Cada alvo é uma **função**, não um valor: a resolução é preguiçosa (ver ``conftest._Alvos``).
Resolver tudo de uma vez amarraria todo grupo de rotas ao estado de todos os models — e há
model do edu que só tem linha depois de um degrau específico do seed, ou que a própria suíte
apaga no caminho (``ConfiguracaoPedidoMatricula`` nasce da funcionalidade 008, é removida no
teardown de ``test_07`` e apagada de novo por ``_normalizar_execucao_anterior``).

Nada aqui **cria** dado: quem cria é ``edu/tests/e2e/seed.py`` e os módulos 01→14. Rota cujo
objeto o seed não produz não vira marcador — ou é dispensada em ``ROTAS_DISPENSADAS``, com o
motivo, ou fica de fora e é reportada como família descoberta.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Aluno do seed (``edu/tests/e2e/conftest.py:MATRICULA_ALUNO_SEED``), usado nas rotas que
# endereçam o aluno por matrícula (``<str:matricula>``) e não por pk.
MATRICULA_ALUNO = '20191101010001'

# Código do curso da cadeia principal (``Especialização em Educação Profissional``).
CODIGO_CURSO = '10101'

# Etapa/ano/período do calendário do seed. Não são pk: são coordenadas do período letivo
# 2019.1 em que toda a cadeia vive, e escrevê-las como marcador deixa isso explícito.
ETAPA = 1
ANO = 2019
PERIODO = 1


def resolvedores() -> dict[str, Callable[[Callable[..., int]], Any]]:
    """``marcador -> função que devolve o valor``, consultando o banco já semeado.

    A função recebe ``conftest._pk``, que devolve o menor ``id`` que casa os filtros ou falha
    com o nome do model. Injetado em vez de importado para o conftest ser o único lugar que
    decide o que fazer quando o alvo não existe.
    """
    from django.contrib.auth.models import Group

    from comum.models import UsuarioGrupo
    from edu.tests.e2e import seed_rotas
    from edu.models import (
        AberturaExtemporanea,
        AbonoFaltas,
        Acolhimento,
        AcolhimentoAnexo,
        Aluno,
        ApoioEspecializado,
        AproveitamentoComponente,
        AproveitamentoEstudo,
        AtaEletronica,
        AtividadeAprofundamento,
        AtividadeComplementar,
        AtividadeCurricularExtensao,
        AtividadeCurricularExtensaoExtra,
        AtividadePraticaProfissional,
        AtoRegulatorioCurso,
        AuditoriaEnsino,
        Aula,
        CalendarioAcademico,
        CenarioOferta,
        CertificacaoConhecimento,
        ColacaoGrau,
        Componente,
        ComponenteCurricular,
        ConfiguracaoAtividadeAprofundamento,
        ConfiguracaoAtividadeComplementar,
        ConfiguracaoAvaliacao,
        ConfiguracaoCertificacaoParcial,
        ConfiguracaoCertificadoENEM,
        ConfiguracaoCreditosEspeciais,
        ConfiguracaoNadaConsta,
        ConfiguracaoPedidoMatricula,
        ConvocacaoENADE,
        CoordenadorPolo,
        CreditoEspecial,
        CursoCampus,
        Diario,
        DiarioEspecial,
        Diretoria,
        Encontro,
        EquivalenciaComponente,
        EstagioDocente,
        EstruturaCurso,
        Evento,
        ExecucaoPlanoLaboratorio,
        HorarioCampus,
        ItemConfiguracaoAvaliacao,
        ItemConfiguracaoCreditosEspeciais,
        JustificativaCensup,
        Laboratorio,
        Log,
        MaterialAula,
        MaterialDiario,
        MatriculaDiario,
        MatriculaPeriodo,
        Matriz,
        MatrizCurso,
        MedidaDisciplinar,
        Minicurso,
        ModalidadeConvocacaoENADE,
        ModalidadePraticaProfissional,
        MonitorMinicurso,
        NadaConsta,
        ObservacaoDiario,
        OcorrenciaDiario,
        ParticipanteEvento,
        ParticipanteTurmaMinicurso,
        PedidoMatricula,
        PlanoEnsino,
        Polo,
        PreMatriculaInternacional,
        Premiacao,
        PrevisaoQuantidadeAlunos,
        Professor,
        ProfessorDiario,
        ProfessorMinicurso,
        ProfissionalApoioEspecializado,
        ProjetoFinal,
        QuestaoEducacenso,
        RegistroAlunoINEP,
        RegistroAuditoriaEnsino,
        RegistroConvocacaoENADE,
        RegistroEducacenso,
        RegistroEmissaoCertificadoENEM,
        RegistroEmissaoDiploma,
        Requerimento,
        RequerimentoAproveitamentoEstudo,
        RespostaEducacenso,
        RespostaJustificativaCensup,
        SimulacaoAfastamento,
        SimulacaoContratacao,
        SolicitacaoCertificadoENEM,
        SolicitacaoReposicaoAtividade,
        SuspensaoDiario,
        TipoComponente,
        TopicoDiscussao,
        Trabalho,
        TramitacaoProcessoEMEC,
        Turma,
        TurmaMinicurso,
        TutorPolo,
        VisitaEstagioDocente,
    )

    return {
        'aluno': lambda pk: pk(Aluno, matricula=MATRICULA_ALUNO),
        'matricula': lambda pk: MATRICULA_ALUNO,
        'aula': lambda pk: pk(Aula),
        'calendario_academico': lambda pk: pk(CalendarioAcademico),
        'componente': lambda pk: pk(Componente),
        'componente_curricular': lambda pk: pk(ComponenteCurricular),
        'configuracao_atividade_aprofundamento': lambda pk: pk(ConfiguracaoAtividadeAprofundamento),
        'configuracao_atividade_complementar': lambda pk: pk(ConfiguracaoAtividadeComplementar),
        # `diario__isnull=False` porque a tela é alcançada a partir de um diário e a view lê
        # `obj.diario` sem guarda (``edu/views/diarios.py:945``): a configuração órfã que o
        # `initial_data` deixa no banco faz a rota devolver 500. Ver o relatório da entrega.
        'configuracao_avaliacao': lambda pk: pk(ConfiguracaoAvaliacao, diario__isnull=False),
        'convocacao_enade': lambda pk: pk(ConvocacaoENADE),
        'curso_campus': lambda pk: pk(CursoCampus, codigo=CODIGO_CURSO),
        'diario': lambda pk: pk(Diario),
        'diretoria': lambda pk: pk(Diretoria, setor__sigla='DIAC/CEN'),
        'estrutura_curso': lambda pk: pk(EstruturaCurso),
        # `grupo` (django.contrib.auth.Group) é o papel em si; `usuario_grupo`
        # (comum.UsuarioGrupo) é o vínculo de um usuário a ele. As rotas usam os dois.
        'grupo': lambda pk: pk(Group, name='Coordenador de Curso'),
        'usuario_grupo': lambda pk: pk(UsuarioGrupo, group__name='Coordenador de Curso'),
        'horario_campus': lambda pk: pk(HorarioCampus),
        'item_configuracao_avaliacao': lambda pk: pk(ItemConfiguracaoAvaliacao),
        'matricula_diario': lambda pk: pk(MatriculaDiario),
        'matricula_periodo': lambda pk: pk(MatriculaPeriodo, aluno__matricula=MATRICULA_ALUNO),
        'matriz': lambda pk: pk(Matriz),
        'matriz_curso': lambda pk: pk(MatrizCurso),
        'modalidade_convocacao_enade': lambda pk: pk(ModalidadeConvocacaoENADE),
        'plano_ensino': lambda pk: pk(PlanoEnsino),
        'professor': lambda pk: pk(Professor),
        'professor_diario': lambda pk: pk(ProfessorDiario),
        'registro_convocacao_enade': lambda pk: pk(RegistroConvocacaoENADE),
        'tipo_componente': lambda pk: pk(TipoComponente),
        'turma': lambda pk: pk(Turma),
        'etapa': lambda pk: ETAPA,
        'ano': lambda pk: ANO,
        'periodo': lambda pk: PERIODO,
        # Sinalizadores das rotas que carregam um booleano/índice no caminho (``<int:publicar>``,
        # ``<int:renovacao_matricula>``). Não são pk; ficam nomeados para não parecerem um.
        # -- objetos criados por `edu/tests/e2e/seed_rotas.py` (famílias fora da cadeia 01→14).
        # Onde há chave natural declarada lá, ela é usada aqui: é o contrato entre os dois.
        'abertura_extemporanea': lambda pk: pk(AberturaExtemporanea),
        'abono_faltas': lambda pk: pk(AbonoFaltas),
        'acolhimento': lambda pk: pk(Acolhimento),
        'acolhimento_anexo': lambda pk: pk(AcolhimentoAnexo),
        'apoio_especializado': lambda pk: pk(ApoioEspecializado),
        'atividade_aprofundamento': lambda pk: pk(AtividadeAprofundamento),
        'atividade_complementar': lambda pk: pk(AtividadeComplementar),
        'atividade_curricular_extensao': lambda pk: pk(AtividadeCurricularExtensao),
        'atividade_curricular_extensao_extra': lambda pk: pk(AtividadeCurricularExtensaoExtra),
        'atividade_pratica_profissional': lambda pk: pk(AtividadePraticaProfissional),
        'auditoria_ensino': lambda pk: pk(AuditoriaEnsino),
        'configuracao_certificado_enem': lambda pk: pk(ConfiguracaoCertificadoENEM),
        'configuracao_creditos_especiais': lambda pk: pk(ConfiguracaoCreditosEspeciais),
        'configuracao_pedido_matricula': lambda pk: pk(ConfiguracaoPedidoMatricula, descricao=seed_rotas.CONFIG_PEDIDO),
        'equivalencia_componente': lambda pk: pk(EquivalenciaComponente),
        'execucao_plano_laboratorio': lambda pk: pk(ExecucaoPlanoLaboratorio),
        'item_configuracao_creditos_especiais': lambda pk: pk(ItemConfiguracaoCreditosEspeciais),
        'justificativa_censup': lambda pk: pk(JustificativaCensup),
        'laboratorio': lambda pk: pk(Laboratorio),
        'log': lambda pk: pk(Log),
        'material_aula': lambda pk: pk(MaterialAula),
        'material_diario': lambda pk: pk(MaterialDiario),
        'minicurso': lambda pk: pk(Minicurso, descricao=seed_rotas.MINICURSO),
        'monitor_minicurso': lambda pk: pk(MonitorMinicurso),
        'observacao_diario': lambda pk: pk(ObservacaoDiario),
        'ocorrencia_diario': lambda pk: pk(OcorrenciaDiario),
        'participante_turma_minicurso': lambda pk: pk(ParticipanteTurmaMinicurso),
        'pedido_matricula': lambda pk: pk(PedidoMatricula),
        'professor_minicurso': lambda pk: pk(ProfessorMinicurso),
        'profissional_apoio_especializado': lambda pk: pk(ProfissionalApoioEspecializado),
        'questao_educacenso': lambda pk: pk(QuestaoEducacenso),
        'registro_aluno_inep': lambda pk: pk(RegistroAlunoINEP),
        'registro_auditoria_ensino': lambda pk: pk(RegistroAuditoriaEnsino),
        'registro_educacenso': lambda pk: pk(RegistroEducacenso),
        'registro_emissao_certificado_enem': lambda pk: pk(RegistroEmissaoCertificadoENEM),
        'resposta_educacenso': lambda pk: pk(RespostaEducacenso),
        'resposta_justificativa_censup': lambda pk: pk(RespostaJustificativaCensup),
        'solicitacao_certificado_enem': lambda pk: pk(SolicitacaoCertificadoENEM),
        'topico_discussao': lambda pk: pk(TopicoDiscussao),
        'trabalho': lambda pk: pk(Trabalho),
        'turma_minicurso': lambda pk: pk(TurmaMinicurso, descricao=seed_rotas.TURMA_MINICURSO),
        # Códigos de geração do ENEM: as rotas os recebem no caminho como `<str:codigo...>`,
        # e são chave natural declarada em `seed_rotas.criar_enem`, não pk.
        # `<str:campus>` de `responder_questionarioeducacenso_campus` é a SIGLA da UO.
        'sigla_campus': lambda pk: 'CEN',
        'codigo_solicitacao_enem': lambda pk: seed_rotas.CODIGO_SOLICITACAO_ENEM,
        'codigo_certificado_enem': lambda pk: seed_rotas.CODIGO_CERTIFICADO_ENEM,
        # -- lote 3: famílias de 9-10 rotas (`seed_rotas.criar_eventos` e seguintes).
        'ata_eletronica': lambda pk: pk(AtaEletronica),
        'colacao_grau': lambda pk: pk(ColacaoGrau, descricao=seed_rotas.COLACAO),
        'coordenador_polo': lambda pk: pk(CoordenadorPolo),
        'diario_especial': lambda pk: pk(DiarioEspecial),
        'encontro': lambda pk: pk(Encontro),
        'estagio_docente': lambda pk: pk(EstagioDocente),
        'evento': lambda pk: pk(Evento, descricao=seed_rotas.EVENTO),
        'participante_evento': lambda pk: pk(ParticipanteEvento),
        'polo': lambda pk: pk(Polo, sigla='E2ERT'),
        'pre_matricula_internacional': lambda pk: pk(PreMatriculaInternacional, descricao=seed_rotas.PRE_MATRICULA),
        'projeto_final': lambda pk: pk(ProjetoFinal),
        'registro_emissao_diploma': lambda pk: pk(RegistroEmissaoDiploma),
        'tutor_polo': lambda pk: pk(TutorPolo),
        'visita_estagio_docente': lambda pk: pk(VisitaEstagioDocente),
        # O aluno DO SMOKE (`seed_rotas.CPF_ALUNO_SMOKE`), não o da cadeia: é dele o projeto
        # final e o estágio docente, e é ele que as rotas com `<int:aluno_pk>` precisam.
        'aluno_smoke': lambda pk: pk(Aluno, pessoa_fisica__cpf=seed_rotas.CPF_ALUNO_SMOKE),
        # Login dele: a matrícula é sequencial, então sai do banco e não de `conftest.PAPEIS`.
        'matricula_aluno_smoke': lambda pk: Aluno.objects.get(pk=pk(Aluno, pessoa_fisica__cpf=seed_rotas.CPF_ALUNO_SMOKE)).matricula,
        # Palavras de domínio destas rotas, lidas do próprio código da view.
        'tipo_participante_evento': lambda pk: 'Participante',  # edu/models/eventos.py:ParticipanteEvento.PARTICIPANTE
        'participante_declaracao': lambda pk: 'orientador',  # edu/views/projeto_final.py:250
        # -- lote 4: uma atividade prática por ação de estado (`seed_rotas.ACOES_PRATICA`).
        'pratica_iniciar': lambda pk: pk(AtividadePraticaProfissional, descricao='Prática E2E Rotas iniciar'),
        'pratica_deferir': lambda pk: pk(AtividadePraticaProfissional, descricao='Prática E2E Rotas deferir'),
        'pratica_indeferir': lambda pk: pk(AtividadePraticaProfissional, descricao='Prática E2E Rotas indeferir'),
        'pratica_desconsiderar': lambda pk: pk(AtividadePraticaProfissional, descricao='Prática E2E Rotas desconsiderar'),
        'pratica_reconsiderar': lambda pk: pk(AtividadePraticaProfissional, descricao='Prática E2E Rotas reconsiderar'),
        # `<str:acao>` de `/edu/auditoria/<pk>/<acao>/`: a view compara com esta palavra.
        'acao_auditoria': lambda pk: 'iniciar',
        # Matrícula-diário DO ALUNO DO SMOKE: as rotas de cancelar/desfazer gravam nela.
        'matricula_diario_smoke': lambda pk: pk(MatriculaDiario, matricula_periodo__aluno__pessoa_fisica__cpf=seed_rotas.CPF_ALUNO_SMOKE),
        # Querystring de `exportar_xls_aluno`, montada pela listagem de turmas.
        'turma_da_cadeia': lambda pk: pk(Turma),
        # -- lote 5: plano de oferta, cursos e procedimentos.
        'aproveitamento_componente': lambda pk: pk(AproveitamentoComponente),
        'aproveitamento_estudo': lambda pk: pk(AproveitamentoEstudo),
        'ato_regulatorio_curso': lambda pk: pk(AtoRegulatorioCurso),
        'cenario_oferta': lambda pk: pk(CenarioOferta),
        'certificacao_conhecimento': lambda pk: pk(CertificacaoConhecimento),
        'configuracao_certificacao_parcial': lambda pk: pk(ConfiguracaoCertificacaoParcial, descricao=seed_rotas.CERTIFICACAO_PARCIAL),
        'credito_especial': lambda pk: pk(CreditoEspecial),
        'medida_disciplinar': lambda pk: pk(MedidaDisciplinar),
        'premiacao': lambda pk: pk(Premiacao),
        'requerimento': lambda pk: pk(Requerimento),
        'requerimento_aproveitamento_estudo': lambda pk: pk(RequerimentoAproveitamentoEstudo),
        'simulacao_afastamento': lambda pk: pk(SimulacaoAfastamento),
        'simulacao_contratacao': lambda pk: pk(SimulacaoContratacao),
        'solicitacao_reposicao_atividade': lambda pk: pk(SolicitacaoReposicaoAtividade),
        'tramitacao_processo_emec': lambda pk: pk(TramitacaoProcessoEMEC),
        # -- lote 6
        'previsao_quantidade_alunos': lambda pk: pk(PrevisaoQuantidadeAlunos),
        # `<str:tipo>` de `imprimir_historico`: a view compara com 'parcial'/'final'
        # (`edu/views/historicos.py`).
        'tipo_historico': lambda pk: 'parcial',
        # `<str:origem>` de `identificar_candidato`: rótulo livre, a view não o consulta.
        'origem_candidato': lambda pk: 'sistemico',
        # -- lote 11: segmentos que são palavra de domínio, lidos do próprio código.
        # `IndicadoresForm.INDICADORES` é um dict indexado direto pela view
        # (`edu/views/relatorios.py:422`): chave errada é KeyError, não 404.
        'indicador': lambda pk: '01_TAXA_RETENCAO',
        # `uo`/`modalidades` chegam como lista separada por `_` (linhas 424-425).
        'uo_sigla': lambda pk: '3',
        'modalidades_ids': lambda pk: '1',
        # `salvar_relatorio` só repassa `tipo` ao form e `query_string` ao `processar`.
        'query_relatorio': lambda pk: 'ano_letivo=2019',
        # -- lote 9: objetos de sacrifício das ações que gravam no GET.
        'aluno_evasao': lambda pk: pk(Aluno, pessoa_fisica__cpf=seed_rotas.ALUNO_EVASAO_CPF),
        'registro_enade_descartavel': lambda pk: pk(RegistroConvocacaoENADE, aluno__pessoa_fisica__cpf=seed_rotas.ALUNO_EVASAO_CPF),
        # -- lote 10: diário de sacrifício (turma de 2018, fora do alcance da cadeia).
        'diario_descartavel': lambda pk: pk(Diario, turma__ano_letivo__ano=seed_rotas.ANO_DESCARTAVEL),
        'suspensao_diario': lambda pk: pk(SuspensaoDiario),
        # -- lote 12: nada consta (família inteira fora da cadeia).
        'nada_consta': lambda pk: pk(NadaConsta),
        'configuracao_nada_consta': lambda pk: pk(ConfiguracaoNadaConsta, descricao=seed_rotas.CONFIG_NADA_CONSTA),
        'zero': lambda pk: 0,
        'um': lambda pk: 1,
        # Rotas cujo segmento é uma **palavra de domínio**, não um id. O valor sai do `if` que
        # a própria view faz sobre o parâmetro; escrever um pk aqui passaria pelo `else` e o
        # teste estaria exercitando o caminho errado com um literal enganoso.
        'tipo_requisito': lambda pk: 'disciplinas_regulares_obrigatorias',  # edu/views/alunos.py:1126
        'tipo_ch': lambda pk: 'pendente',  # edu/views/alunos.py:1128
        'tipo_extensao': lambda pk: 'componentes',  # edu/views/alunos.py:1179
        'tipo_estagio': lambda pk: 'estagios',  # edu/views/estagio_docente.py:161
        'tipo_transferencia': lambda pk: 'Intercampus',  # edu/forms/procedimentos.py:895
        'tipo_disciplinas': lambda pk: 'pendente',  # edu/views/relatorios.py:232
        'exibir': lambda pk: 'cursando',  # edu/views/cursos.py:593
        'modalidade_pratica': lambda pk: pk(ModalidadePraticaProfissional),
        # `<int:polo_pk>` das telas de diário: sem polo é 0, não um pk de outro model. O nome
        # é `sem_polo` e não `polo` de propósito — `{polo}` seria lido como "um Polo".
        'sem_polo': lambda pk: 0,
    }
