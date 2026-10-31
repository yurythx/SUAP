"""Fábricas ORM dos objetos que o smoke de rota precisa e a cadeia 01→14 não cria.

O ``edu`` tem 36 famílias de tela e as ``.feature`` do behave cobriam ~10 delas. As outras
existem em ``edu/urls.py`` mas endereçam models que nenhum passo do seed instancia — minicurso,
NAPNE, ENEM, censo, auditoria, material de aula, atividade complementar. Sem uma linha em cada
um desses models, a rota só pode dar 404, e 404 num smoke não distingue "tela quebrada" de
"não havia o que abrir".

Três regras que este módulo respeita, e que a próxima família a ser acrescentada também deve:

1. **Idempotente.** A suíte roda com ``--reuse-db`` e sem flush. Toda escrita passa por
   ``get_or_create`` com chave natural estável, e ``montar()`` é guardado por sentinela.
2. **Fora da cadeia.** Nada aqui altera objeto de que ``test_01``→``test_14`` dependem. Onde
   isso é inevitável (``ConfiguracaoPedidoMatricula``, que o ``test_07`` também usa), o objeto
   é criado com descrição própria e **janela de datas que não colide** com a da renovação —
   ``AddCursoConfiguracaoPedidoMatriculaForm.clean`` recusa duas configurações com datas
   sobrepostas para o mesmo curso, e essa recusa apareceria dentro do popup do ``test_07``.
3. **Mínimo.** Cada fábrica cria o objeto no estado mais simples que faz a tela abrir, não um
   cenário de negócio. Quem quer afirmar regra de negócio escreve fluxo, não smoke.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edu.models import Aluno

# Ano/período em que a cadeia inteira vive (ver `conftest.DATA_BASE`).
ANO = 2019
DATA = date(2019, 3, 10)

# Chaves naturais dos objetos criados aqui. Ficam nomeadas porque são o contrato com
# `alvos_rotas.py`: é por elas que os marcadores encontram o objeto certo, e não por "o
# primeiro que aparecer" — que mudaria a cada execução.
MINICURSO = 'Minicurso E2E Rotas'
TURMA_MINICURSO = 'Turma E2E Rotas'
APOIO_ESPECIALIZADO = 'Apoio E2E Rotas'
AUDITORIA = '3'  # AuditoriaEnsino.TIPO_RECEITA_FEDERAL
MATERIAL_AULA = 'Material E2E Rotas'
CONFIG_CREDITOS = 'Créditos Especiais E2E Rotas'
CONFIG_PEDIDO = 'Pedido de Matrícula E2E Rotas'
LABORATORIO = 'Laboratório E2E Rotas'
REGISTRO_EDUCACENSO = 'E2E-ROTAS'
# Códigos de geração do ENEM: chave natural das solicitações/registros E a chave pela qual
# as rotas os endereçam. `alvos_rotas` repete os mesmos literais.
CODIGO_SOLICITACAO_ENEM = 'e2erotas-solic'
CODIGO_CERTIFICADO_ENEM = 'e2erotas-cert'
# `SolicitacaoCertificadoENEM.get_registro_aluno_inep` casa configuração + CPF: os dois
# lados precisam do MESMO cpf, senão `imprimir_certificado_enem_pdf` estoura ao ler
# `data_nascimento` de None (`edu/views/enem.py:248`).
CPF_ENEM = '380.334.974-59'


def montar() -> None:
    """Roda todas as fábricas. Sem sentinela global, de propósito.

    Cada escrita já é ``get_or_create`` com chave natural, então repetir é barato e inócuo.
    Uma sentinela global seria pior que inútil: bastaria a PRIMEIRA fábrica ter gravado numa
    execução interrompida para todas as seguintes serem puladas para sempre — foi o que
    aconteceu na primeira versão deste módulo, e o sintoma foi 38 models vazios com o seed
    "concluído".
    """
    for fabrica in (
        # As duas primeiras são o que antes só a tela dos fluxos criava; as seguintes dependem delas.
        criar_aluno_smoke,
        criar_enade,
        criar_minicurso,
        criar_napne,
        criar_enem,
        criar_censos,
        criar_auditoria,
        criar_materiais_e_diario,
        criar_atividades,
        criar_procedimentos,
        criar_eventos,
        criar_projeto_final,
        criar_internacionalizacao,
        criar_diarios_especiais,
        criar_polos,
        criar_diplomas,
        criar_estagio_docente,
        criar_praticas_descartaveis,
        criar_plano_oferta,
        criar_cursos,
        criar_procedimentos_lote5,
        criar_aluno_descartavel,
        criar_diario_descartavel,
        criar_nada_consta,
    ):
        fabrica()


# O smoke NÃO pendura seus objetos no aluno da cadeia (20191101010001): abono de faltas,
# atividade complementar e acolhimento mudam as abas do prontuário, e `test_08_aluno` afirma
# exatamente essas abas. O aluno do smoke é próprio (``criar_aluno_smoke``) e é endereçado pelo
# CPF, não pela matrícula: o número sai de `SequencialMatricula` e depende de quantos alunos a
# sessão já criou no prefixo 2019/1/10101 — a UI e as fixtures de `test_04_matricula` criam
# dois a cada execução, e rodando só as rotas eles não existem.
CPF_ALUNO_SMOKE = '529.982.247-25'
# Convocação ENADE criada por `criar_enade` quando nenhuma existe (mesma descrição de `test_14`).
DESCRICAO_CONVOCACAO_ENADE = 'Licenciaturas - Portaria Normativa No 8, de 26 de Março de 2019'


def _aluno() -> Aluno:
    from edu.models import Aluno

    return Aluno.objects.get(pessoa_fisica__cpf=CPF_ALUNO_SMOKE)


def criar_aluno_smoke() -> None:
    """Aluno dono dos objetos do smoke, matriculado na turma 2019.1 do curso 10101.

    Na turma, e não só no curso, porque ``matricula_diario_smoke`` e o estágio docente precisam
    de ``MatriculaDiario``. São os passos de ``test_04_matricula.aluno_sem_turma``. Guardado por
    CPF, e ``seed.cadastrar_aluno`` não usa ``get_or_create``.
    """
    from comum.models import Ano
    from edu.models import Aluno, Cidade, FormaIngresso, MatriculaPeriodo, Turma
    from edu.tests.e2e import seed
    from rh.models import PessoaFisica

    if Aluno.objects.filter(pessoa_fisica__cpf=CPF_ALUNO_SMOKE).exists():
        return
    pessoa, _ = PessoaFisica.objects.get_or_create(
        cpf=CPF_ALUNO_SMOKE,
        defaults={'nome_registro': 'Aluno E2E Rotas Smoke', 'nome': 'Aluno E2E Rotas Smoke', 'sexo': 'M', 'nascimento_data': date(1990, 10, 10)},
    )
    ano = Ano.objects.get(ano=ANO)
    turma = Turma.objects.get(ano_letivo=ano, periodo_letivo=1, curso_campus__codigo='10101')
    ingresso = FormaIngresso.objects.get(descricao='Ampla Concorrência')
    aluno = seed.cadastrar_aluno(pessoa, Cidade.objects.get(nome='Natal'), ano, ingresso, turma.curso_campus, turma.matriz)
    seed.matricular_aluno(aluno, ano, turma.curso_campus, turma.matriz)
    turma.matricular_alunos(MatriculaPeriodo.objects.filter(aluno=aluno))


def criar_enade() -> None:
    """Licenciatura, ATPA e convocação ENADE com um registro — alvos de ``test_16``/``23``/``25``.

    Na execução completa quem cria tudo isso é a tela de ``test_12``→``test_14``, que roda antes
    deste seed (ordem de arquivo), e aqui vira no-op: ``seed.step_cadastro_curso_licenciatura`` é
    ``get_or_create`` pelas mesmas chaves naturais que a tela grava (a ATPA inclusive), e a
    convocação é guardada por existência. Rodando só as rotas, é daqui que eles vêm — o mesmo
    idioma de ``edu/tests/doc/test_11_enade.py``. Se este seed subisse antes do ``test_12``, a
    tela não quebraria: ``base_credito`` apaga a licenciatura e a ATPA, e
    ``test_14_enade.convocacoes_limpas`` apaga a convocação, antes de os cadastros rodarem.
    """
    from edu.models import Aluno, ConvocacaoENADE, ModalidadeConvocacaoENADE, RegistroConvocacaoENADE, SituacaoMatricula
    from edu.tests.e2e import seed

    curso = seed.step_cadastro_curso_licenciatura(None)
    if ConvocacaoENADE.objects.exists():
        return
    convocacao = ConvocacaoENADE.objects.create(
        descricao=DESCRICAO_CONVOCACAO_ENADE,
        tipo_convocacao=ConvocacaoENADE.AVALIACAO_TEORICA,
        ano_letivo=_ano(),
        data_inscricao_ingressantes=date(2019, 4, 1),
        data_inscricao=date(2019, 4, 1),
    )
    convocacao.modalidades_convocadas.add(curso.modalidade)
    convocacao.areas_cursos_formacao_superior.add(curso.area_curso_formacao_superior)
    convocacao.situacoes_convocadas.add(*SituacaoMatricula.objects.filter(descricao='Matriculado'))
    convocacao.cursos.add(curso)
    ModalidadeConvocacaoENADE.objects.create(convocacao_enade=convocacao, modalidade=curso.modalidade, data_prova=date(2019, 4, 2))
    RegistroConvocacaoENADE.objects.create(
        convocacao_enade=convocacao,
        aluno=Aluno.objects.get(pessoa_fisica__cpf=seed.CPF_ALUNA_LICENCIATURA),
        tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE,
    )


def _campus():
    from rh.models import UnidadeOrganizacional

    return UnidadeOrganizacional.objects.suap().get(sigla='CEN')


def _ano():
    from comum.models import Ano

    return Ano.objects.get(ano=ANO)


def criar_minicurso() -> None:
    """Minicurso com turma, participante, professor e monitor — 13 rotas de ``mini_cursos``."""
    from edu.models import CursoCampus, Minicurso, MonitorMinicurso, ParticipanteTurmaMinicurso, Professor, ProfessorMinicurso, TurmaMinicurso

    modelo = CursoCampus.objects.get(codigo='10101')
    minicurso, _ = Minicurso.objects.get_or_create(
        descricao=MINICURSO,
        defaults={
            'descricao_historico': MINICURSO,
            'codigo': 'E2EMC01',
            'ch_total': 20,
            'tipo_hora_aula': 60,
            # `declaracaodocencia_pdf` (edu/views/professores.py:524) lê
            # `minicurso.modalidade.descricao` e `minicurso.diretoria.setor.sigla` sem guarda:
            # minicurso sem os dois derruba a declaração de docência de QUALQUER professor
            # que tenha dado minicurso. Espelhar o curso da cadeia é o mínimo coerente.
            'modalidade': modelo.modalidade,
            'diretoria': modelo.diretoria,
        },
    )
    turma, _ = TurmaMinicurso.objects.get_or_create(
        descricao=TURMA_MINICURSO,
        minicurso=minicurso,
        defaults={'ano_letivo': _ano(), 'periodo_letivo': 1, 'data_inicio': DATA, 'data_fim': date(2019, 6, 30)},
    )
    aluno = _aluno()
    ParticipanteTurmaMinicurso.objects.get_or_create(aluno=aluno, turma=turma)
    professor = Professor.objects.order_by('id').first()
    # `carga_horaria` explícita: `ProfessorMinicurso.save` (`edu/models/turmas.py:695`)
    # calcula a semanal a partir dela e estoura TypeError se vier nula.
    ProfessorMinicurso.objects.get_or_create(professor=professor, turma_minicurso=turma, defaults={'carga_horaria': 20})
    MonitorMinicurso.objects.get_or_create(aluno=aluno, turma_minicurso=turma)


# CPF do profissional de apoio do NAPNE (um `PrestadorServico`). Fixo porque o `save` do
# prestador troca a matrícula pelos dígitos do CPF: com o CPF da sequência da factory, a segunda
# sessão (`--reuse-db`) não reencontraria o prestador e colidiria na matrícula.
CPF_PRESTADOR_NAPNE = '186.215.460-00'


def criar_napne() -> None:
    """Acolhimento com anexo e profissional de apoio — 12 rotas de ``napne``."""
    from comum.tests.factories import PrestadorServicoFactory
    from edu.models import Acolhimento, AcolhimentoAnexo, ApoioEspecializado, ProfissionalApoioEspecializado
    from rh.models import Setor

    acolhimento, _ = Acolhimento.objects.get_or_create(
        aluno=_aluno(), defaults={'data_acolhimento': DATA, 'relatorio': 'Acolhimento criado pelo smoke de rota.'}
    )
    AcolhimentoAnexo.objects.get_or_create(acolhimento=acolhimento, defaults={'descricao': 'Anexo E2E Rotas'})
    apoio, _ = ApoioEspecializado.objects.get_or_create(nome=APOIO_ESPECIALIZADO)
    # Prestador próprio (#17486): antes era o primeiro do banco, um dos do seed legado do behave.
    prestador = PrestadorServicoFactory(
        matricula=re.sub(r'\D', '', CPF_PRESTADOR_NAPNE),
        setor=Setor.objects.suap_ativos().get(sigla='DIAC/CEN'),
        pessoa_fisica__nome='Profissional Napne E2E',
        pessoa_fisica__cpf=CPF_PRESTADOR_NAPNE,
    )
    ProfissionalApoioEspecializado.objects.get_or_create(acolhimento=acolhimento, apoio_especializado=apoio, profissional=prestador)


def criar_enem() -> None:
    """Configuração, solicitação e registro de emissão do certificado ENEM — 15 rotas."""
    from edu.models import ConfiguracaoCertificadoENEM, RegistroAlunoINEP, RegistroEmissaoCertificadoENEM, SolicitacaoCertificadoENEM

    configuracao, _ = ConfiguracaoCertificadoENEM.objects.get_or_create(
        ano=_ano(),
        defaults={
            'data_primeira_prova': date(2019, 11, 3),
            'pontuacao_necessaria_areas_conhecimento': 450,
            'pontuacao_necessaria_redacao': 500,
            'numero_portaria': 'Portaria E2E Rotas',
        },
    )
    # `update_or_create`: se o CPF mudar, a linha antiga tem de acompanhar — foi trocá-lo uma
    # vez, com a linha já gravada, para o certificado deixar de encontrar o registro do INEP.
    RegistroAlunoINEP.objects.update_or_create(
        configuracao_certificado_enem=configuracao,
        numero_inscricao='190000000001',
        defaults={
            'nome': 'Candidata E2E Rotas',
            'nome_mae': 'Maria E2E Rotas',
            'rg': '1234567',
            'cpf': CPF_ENEM,
            'data_nascimento': date(1995, 5, 20),
            'nota_cn': 500,
            'nota_ch': 500,
            'nota_lc': 500,
            'nota_mt': 500,
            'nota_redacao': 600,
        },
    )
    # A chave natural é o CÓDIGO, não o CPF: são as rotas
    # `comprovante_solicitacao_certificado_enem` e `gerar_certificado_enem` que endereçam por
    # ele, com `.get(...)`. Chavear por outro campo permitiu, num banco reusado, nascer uma
    # segunda linha com o mesmo código — e as duas telas passaram a devolver 500 por
    # `MultipleObjectsReturned`. A chave da fábrica tem de ser a que a rota usa.
    solicitacao, _ = SolicitacaoCertificadoENEM.objects.get_or_create(
        codigo_geracao_solicitacao=CODIGO_SOLICITACAO_ENEM,
        defaults={
            'cpf': CPF_ENEM,
            'configuracao_certificado_enem': configuracao,
            'nome': 'Candidata E2E Rotas',
            'email': 'candidata.rotas@ifrn.edu.br',
            'tipo_certificado': 1,
            'uo': _campus(),
        },
    )
    RegistroEmissaoCertificadoENEM.objects.get_or_create(
        codigo_geracao_certificado=CODIGO_CERTIFICADO_ENEM,
        defaults={
            'solicitacao': solicitacao,
            'livro': 1,
            'folha': 1,
            'numero_registro': 1,
            'data_expedicao': DATA,
            'via': 1,
        },
    )


ARQUIVO_CENSUP = 'e2e_rotas_censup.csv'


def _arquivo_censup() -> str:
    """Cria em ``MEDIA_ROOT`` o arquivo que ``JustificativaCensup.save`` abre e lê.

    Não é um upload de verdade: ``JustificativaCensup.save`` percorre as linhas e ignora a que
    começa com ``LINHA`` (o cabeçalho), então um arquivo só com o cabeçalho faz o objeto ser
    gravado sem gerar resposta nenhuma — que é o que se quer, porque a resposta é criada
    logo abaixo, com dados controlados. Sem o arquivo, o ``save`` estoura ``FileNotFoundError``.
    """
    import os

    from django.conf import settings

    caminho = os.path.join(settings.MEDIA_ROOT, ARQUIVO_CENSUP)
    if not os.path.exists(caminho):
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        with open(caminho, 'w', encoding='utf-8') as arquivo:
            arquivo.write('LINHA|IDENTIFICACAO|A|B|MENSAGEM\n')
    return ARQUIVO_CENSUP


def criar_censos() -> None:
    """Educacenso (registro, questão, resposta), CENSUP e laboratório — 16 rotas de ``censos``."""
    from comum.models import Vinculo
    from edu.models import (
        AberturaExtemporanea,
        ExecucaoPlanoLaboratorio,
        JustificativaCensup,
        Laboratorio,
        QuestaoEducacenso,
        RegistroEducacenso,
        RespostaEducacenso,
        RespostaJustificativaCensup,
    )
    from comum.models import Sala

    registro, _ = RegistroEducacenso.objects.get_or_create(
        ano_censo=_ano(), numero_registro=REGISTRO_EDUCACENSO, defaults={'privado': False, 'data_limite': date(2019, 12, 31)}
    )
    questao, _ = QuestaoEducacenso.objects.get_or_create(
        registro=registro,
        numero_campo=1,
        defaults={'nome_campo': 'Campo E2E Rotas', 'tipo_resposta': 'T', 'tipo_obrigatoriedade': 'O'},
    )
    RespostaEducacenso.objects.get_or_create(questao=questao, campus=_campus())

    justificativa, _ = JustificativaCensup.objects.get_or_create(ano_letivo=_ano(), defaults={'arquivo': _arquivo_censup()})
    RespostaJustificativaCensup.objects.get_or_create(
        justificativa_censup=justificativa,
        aluno=_aluno(),
        defaults={'mensagem': 'Resposta do smoke de rota.', 'opcoes': '1-Sim;2-Não', 'resposta': 1},
    )
    AberturaExtemporanea.objects.get_or_create(
        solicitante=Vinculo.objects.get(user__username='100001'),
        defaults={'qtd_alunos': 1, 'justificativa': 'Abertura criada pelo smoke de rota.', 'campi': ''},
    )
    # Sala PRÓPRIA, nunca `Sala.objects.first()`: criar um `Laboratorio` sobre uma sala a tira
    # do campo "sala" de `DefinirLocalAulaForm` (`edu/forms/diarios.py:561` filtra
    # `laboratorio__isnull=True`) e a joga para o campo "laboratório". Como o seed da cadeia tem
    # UMA única sala ("Sala 101"), sequestrá-la fazia `test_03_turmas::test_configura_diario`
    # falhar em toda execução após a primeira — a opção simplesmente sumia do autocomplete.
    predio = Sala.objects.order_by('id').values_list('predio', flat=True).first()
    if predio:
        sala, _ = Sala.objects.get_or_create(nome='Sala E2E Rotas', defaults={'predio_id': predio})
        laboratorio, _ = Laboratorio.objects.get_or_create(nome=LABORATORIO, defaults={'sala': sala})
        ExecucaoPlanoLaboratorio.objects.get_or_create(ano=_ano(), laboratorio=laboratorio)


def criar_auditoria() -> None:
    """Auditoria de ensino com um registro, e os quatro tipos de ``Log`` — 14 rotas."""
    from edu.models import AuditoriaEnsino, Log, RegistroAuditoriaEnsino

    auditoria, _ = AuditoriaEnsino.objects.get_or_create(tipo_auditoria=AUDITORIA, campus=_campus())
    RegistroAuditoriaEnsino.objects.get_or_create(auditoria_ensino=auditoria, defaults={'registro': '20191101010001;730.378.660-04'})
    Log.objects.get_or_create(
        descricao='Log do smoke de rota',
        defaults={'tipo': 1, 'app': 'edu', 'modelo': 'aluno', 'nome_modelo': 'Aluno', 'ref': _aluno().pk},
    )


def criar_materiais_e_diario() -> None:
    """Material de aula, observação, suspensão, ocorrência, tópico e trabalho — 15 rotas."""
    from comum.models import User

    from edu.models import (
        AbonoFaltas,
        Diario,
        EquivalenciaComponente,
        MaterialAula,
        MaterialDiario,
        ObservacaoDiario,
        OcorrenciaDiario,
        Professor,
        ProfessorDiario,
        TopicoDiscussao,
        Trabalho,
    )

    professor = Professor.objects.order_by('id').first()
    professor_diario = ProfessorDiario.objects.order_by('id').first()
    diario = professor_diario.diario if professor_diario else Diario.objects.order_by('id').first()
    usuario = User.objects.get(username='100001')

    material, _ = MaterialAula.objects.get_or_create(professor=professor, descricao=MATERIAL_AULA)
    if professor_diario:
        MaterialDiario.objects.get_or_create(material_aula=material, professor_diario=professor_diario)
        OcorrenciaDiario.objects.get_or_create(professor_diario=professor_diario, data=DATA, defaults={'descricao': 'Ocorrência do smoke de rota.'})
    ObservacaoDiario.objects.get_or_create(diario=diario, usuario=usuario, defaults={'observacao': 'Observação do smoke de rota.', 'data': DATA})
    TopicoDiscussao.objects.get_or_create(
        diario=diario, etapa=1, user=usuario, defaults={'titulo': 'Tópico E2E Rotas', 'descricao': 'Tópico do smoke de rota.'}
    )
    Trabalho.objects.get_or_create(diario=diario, etapa=1, defaults={'titulo': 'Trabalho E2E Rotas', 'descricao': 'Trabalho do smoke de rota.'})
    AbonoFaltas.objects.get_or_create(
        aluno=_aluno(), defaults={'data_inicio': DATA, 'data_fim': DATA, 'quantidade_dias': 1, 'data_solicitacao': DATA}
    )
    EquivalenciaComponente.objects.get_or_create(simples=True, defaults={'ativa': True})


def criar_atividades() -> None:
    """Atividade complementar/aprofundamento, prática profissional e extensão — 17 rotas."""
    from edu.models import (
        AtividadeAprofundamento,
        AtividadeComplementar,
        AtividadeCurricularExtensao,
        AtividadeCurricularExtensaoExtra,
        AtividadePraticaProfissional,
        ConfiguracaoAtividadeComplementar,
        ConfiguracaoCreditosEspeciais,
        HorarioAtividadeExtra,
        HorarioAula,
        ItemConfiguracaoCreditosEspeciais,
        MatriculaPeriodo,
        ModalidadePraticaProfissional,
        TipoAtividadeAprofundamento,
        TipoAtividadeComplementar,
        TipoAtividadeCurricularExtensaoExtra,
    )

    matricula_periodo = MatriculaPeriodo.objects.filter(aluno=_aluno()).order_by('id').first()
    comuns = {'ano_letivo': _ano(), 'periodo_letivo': 1, 'data_atividade': DATA, 'carga_horaria': 10}

    # Tipo e configuração de AACC vêm, na execução completa, da fixture de `test_08_aluno`; rodando
    # só as rotas não existem. Reusa o primeiro que houver (na execução completa nada muda) e só
    # cria quando falta — sem isto o `if tipo_ac:` antigo pulava calado e o alvo sumia.
    tipo_ac = TipoAtividadeComplementar.objects.order_by('id').first() or TipoAtividadeComplementar.objects.create(
        descricao='Tipo Complementar E2E Rotas'
    )
    if not ConfiguracaoAtividadeComplementar.objects.exists():
        ConfiguracaoAtividadeComplementar.objects.create(descricao='Configuração AACC E2E Rotas')
    AtividadeComplementar.objects.get_or_create(tipo=tipo_ac, descricao='Atividade Complementar E2E Rotas', defaults={**comuns, 'aluno': _aluno()})
    # Os dois tipos abaixo vêm do `initial_data` em produção; no banco de teste
    # (`--no-migrations`) não existem, então a fábrica cria o seu.
    tipo_aa, _ = TipoAtividadeAprofundamento.objects.get_or_create(descricao='Tipo Aprofundamento E2E Rotas')
    if tipo_aa:
        AtividadeAprofundamento.objects.get_or_create(
            tipo=tipo_aa, descricao='Atividade Aprofundamento E2E Rotas', defaults={**comuns, 'aluno': _aluno()}
        )

    configuracao, _ = ConfiguracaoCreditosEspeciais.objects.get_or_create(
        descricao=CONFIG_CREDITOS, defaults={'quantidade_maxima_creditos_especiais': 10}
    )
    ItemConfiguracaoCreditosEspeciais.objects.get_or_create(
        configuracao=configuracao, atividade_academica='Atividade E2E Rotas', defaults={'equivalencia_creditos': 1}
    )

    if matricula_periodo:
        AtividadeCurricularExtensao.objects.get_or_create(
            matricula_periodo=matricula_periodo, descricao='Extensão E2E Rotas', defaults={'carga_horaria': 10}
        )
        tipo_extra, _ = TipoAtividadeCurricularExtensaoExtra.objects.get_or_create(descricao='Tipo Extensão Extra E2E Rotas')
        if tipo_extra:
            AtividadeCurricularExtensaoExtra.objects.get_or_create(
                matricula_periodo=matricula_periodo,
                descricao='Extensão Extra E2E Rotas',
                defaults={'tipo_atividade': tipo_extra, 'carga_horaria': 10},
            )
        modalidade = ModalidadePraticaProfissional.objects.order_by('id').first()
        if modalidade:
            AtividadePraticaProfissional.objects.get_or_create(
                matricula_periodo=matricula_periodo, descricao='Prática E2E Rotas', defaults={'modalidade_pratica_profissional': modalidade}
            )
        horario_aula = HorarioAula.objects.order_by('id').first()
        if horario_aula:
            HorarioAtividadeExtra.objects.get_or_create(
                matricula_periodo=matricula_periodo,
                descricao_atividade='Atividade Extra E2E Rotas',
                defaults={'horario_aula': horario_aula, 'dia_semana': 2},
            )


def criar_procedimentos() -> None:
    """Configuração de pedido de matrícula própria e requerimentos — rotas de ``procedimentos``.

    A configuração leva descrição e **janela de datas próprias** (dezembro/2019): a do
    ``test_07`` é 21/07/2019, e ``AddCursoConfiguracaoPedidoMatriculaForm.clean`` recusa duas
    configurações com datas sobrepostas para o mesmo curso.
    """
    from edu.models import ConfiguracaoPedidoMatricula, CursoCampus, Diretoria, MatriculaPeriodo, PedidoMatricula

    configuracao, criada = ConfiguracaoPedidoMatricula.objects.get_or_create(
        descricao=CONFIG_PEDIDO,
        defaults={'ano_letivo': _ano(), 'periodo_letivo': 2, 'data_inicio': date(2019, 12, 1), 'data_fim': date(2019, 12, 2)},
    )
    if criada:
        configuracao.diretorias.add(Diretoria.objects.get(setor__sigla='DIAC/CEN'))
        configuracao.cursos.add(CursoCampus.objects.get(codigo='10101'))
    matricula_periodo = MatriculaPeriodo.objects.filter(aluno=_aluno()).order_by('id').first()
    if matricula_periodo:
        PedidoMatricula.objects.get_or_create(matricula_periodo=matricula_periodo, configuracao_pedido_matricula=configuracao)


# --- lote 3: famílias de 9-10 rotas -------------------------------------------------------

EVENTO = 'Evento E2E Rotas'
COLACAO = 'Colação E2E Rotas'
POLO = 'Polo E2E Rotas'
PRE_MATRICULA = 'Pré-Matrícula Internacional E2E Rotas'


def _vinculo():
    """Vínculo de um servidor que só existe para o smoke (`seed.SERVIDORES_ROTAS`).

    Nunca o do professor nem o do administrador da cadeia: participante de evento, tutor e
    coordenador de polo aparecem em listagens que `test_01`→`test_14` inspecionam.
    """
    from comum.models import Vinculo

    return Vinculo.objects.get(user__username='100010')


def _matricula_periodo():
    from edu.models import MatriculaPeriodo

    return MatriculaPeriodo.objects.filter(aluno=_aluno()).order_by('id').first()


def _diretoria():
    from edu.models import Diretoria

    return Diretoria.objects.get(setor__sigla='DIAC/CEN')


def criar_eventos() -> None:
    """Evento com participante e colação de grau — 10 rotas de ``eventos``."""
    from edu.models import ColacaoGrau, Evento, ParticipanteEvento

    evento, _ = Evento.objects.get_or_create(descricao=EVENTO, defaults={'tipo': Evento.TIPO_EVENTO_PALESTRA, 'uo': _campus(), 'data': DATA})
    ParticipanteEvento.objects.get_or_create(evento=evento, participante=_vinculo(), defaults={'tipo_participacao': ParticipanteEvento.PARTICIPANTE})
    ColacaoGrau.objects.get_or_create(
        descricao=COLACAO,
        defaults={'diretoria': _diretoria(), 'ano_letivo': _ano(), 'periodo_letivo': 1, 'data_colacao': date(2019, 12, 20)},
    )


def criar_projeto_final() -> None:
    """Projeto final com ata eletrônica assinada — 8 rotas de ``projeto_final``."""
    from edu.models import AssinaturaAtaEletronica, AtaEletronica, Professor, ProjetoFinal

    projeto, _ = ProjetoFinal.objects.get_or_create(
        matricula_periodo=_matricula_periodo(),
        defaults={
            'titulo': 'Projeto Final E2E Rotas',
            'resumo': 'Resumo do projeto criado pelo smoke de rota.',
            'tipo': 'Monografia',
            # Sem orientador, `adicionar_projeto_final` e a declaração de participação
            # estouram: as duas telas leem o vínculo do orientador sem guarda.
            'orientador': Professor.objects.order_by('id').first(),
        },
    )
    ata, _ = AtaEletronica.objects.get_or_create(projeto_final=projeto, defaults={'consideracoes': 'Considerações do smoke de rota.'})
    AssinaturaAtaEletronica.objects.get_or_create(ata=ata, defaults={'vinculo': _vinculo()})


def criar_internacionalizacao() -> None:
    """Pré-matrícula internacional — 3 das 10 rotas de ``internacionalizacao``.

    ``InscricaoAlunoEstrangeiro`` fica de fora: são 24 campos obrigatórios, dois deles
    ``FileField`` de passaporte e declaração de vínculo. As 6 rotas que dependem dela seguem
    descobertas — dívida declarada, não dispensa.
    """
    from edu.models import MatrizCurso, PreMatriculaInternacional

    PreMatriculaInternacional.objects.get_or_create(
        descricao=PRE_MATRICULA,
        defaults={
            'ano_letivo': _ano(),
            'periodo_letivo': 1,
            'diretoria': _diretoria(),
            'matriz_curso': MatrizCurso.objects.order_by('id').first(),
            'qtd_vagas': 5,
            'data_inicio_inscricoes': DATA,
            'data_termino_inscricoes': date(2019, 4, 30),
            'data_limite_correcao_inscricoes': date(2019, 5, 15),
        },
    )


def criar_diarios_especiais() -> None:
    """Diário especial com um encontro — 9 rotas de ``diarios_especiais``."""
    from edu.models import Componente, DiarioEspecial, Encontro, HorarioCampus

    diario_especial, _ = DiarioEspecial.objects.get_or_create(
        ano_letivo=_ano(),
        periodo_letivo=1,
        componente=Componente.objects.order_by('id').first(),
        defaults={'horario_campus': HorarioCampus.objects.order_by('id').first(), 'diretoria': _diretoria()},
    )
    Encontro.objects.get_or_create(diario_especial=diario_especial, data=DATA, defaults={'conteudo': 'Encontro criado pelo smoke de rota.'})


def criar_polos() -> None:
    """Polo EAD com coordenador e tutor — 7 das 9 rotas de ``polos``.

    ``meu_polo`` fica de fora: resolve o polo pelo vínculo de quem está logado, e amarrar um
    servidor da cadeia a um polo mudaria o menu dele.
    """
    from edu.models import CoordenadorPolo, Polo, TutorPolo

    polo, _ = Polo.objects.get_or_create(sigla='E2ERT', defaults={'descricao': POLO})
    CoordenadorPolo.objects.get_or_create(polo=polo, vinculo=_vinculo())
    TutorPolo.objects.get_or_create(polo=polo, vinculo=_vinculo())


def criar_diplomas() -> None:
    """Registro de emissão de diploma — 5 rotas de ``diplomas``.

    ``AssinaturaDigital`` (exige `Papel`, `hmac` e chave pública de certificado real) e
    ``AssinaturaEletronica`` (exige o PDF assinado do diploma) ficam de fora: as rotas de
    status de assinatura e de XML seguem descobertas.
    """
    from edu.models import RegistroEmissaoDiploma

    RegistroEmissaoDiploma.objects.get_or_create(aluno=_aluno(), defaults={'via': 1})


def criar_estagio_docente() -> None:
    """Estágio docente com uma visita — 9 rotas de ``estagio_docente``."""
    from comum.models import Vinculo
    from edu.models import EstagioDocente, MatriculaDiario, Professor, VisitaEstagioDocente

    matricula_diario = MatriculaDiario.objects.filter(matricula_periodo__aluno=_aluno()).order_by('id').first()
    # As telas de visita e de avaliação exigem que o logado SEJA o orientador
    # (`edu/views/estagio_docente.py:32`), e `enviar_portfolio` compara
    # `data_final_envio_portfolio` com hoje sem guarda de nulo (linha 69). O orientador é o
    # servidor 100016, que existe só para o smoke e já nasce no grupo Professor.
    orientador, _ = Professor.objects.get_or_create(vinculo=Vinculo.objects.get(user__username='100016'))
    estagio, _ = EstagioDocente.objects.get_or_create(
        matricula_diario=matricula_diario,
        defaults={'professor_orientador': orientador, 'data_final_envio_portfolio': date(2019, 12, 31)},
    )
    VisitaEstagioDocente.objects.get_or_create(estagio_docente=estagio, data_visita=DATA, defaults={'desenvolvendo_atividades_previstas': True})


# --- lote 4: objetos descartáveis das rotas de ação ---------------------------------------
#
# Rota que grava no GET precisa de objeto PRÓPRIO, e um por ação: as cinco transições de
# `AtividadePraticaProfissional` mudam o estado da mesma entidade, então compartilhar uma
# linha faria o resultado depender da ordem em que o pytest resolve os grupos.
ACOES_PRATICA = ('iniciar', 'deferir', 'indeferir', 'desconsiderar', 'reconsiderar')


def criar_praticas_descartaveis() -> None:
    """Uma ``AtividadePraticaProfissional`` por ação de estado, endereçada pela descrição."""
    from edu.models import AtividadePraticaProfissional, ModalidadePraticaProfissional

    matricula_periodo = _matricula_periodo()
    modalidade = ModalidadePraticaProfissional.objects.order_by('id').first()
    if not (matricula_periodo and modalidade):
        return
    for acao in ACOES_PRATICA:
        AtividadePraticaProfissional.objects.get_or_create(
            descricao=f'Prática E2E Rotas {acao}',
            defaults={'matricula_periodo': matricula_periodo, 'modalidade_pratica_profissional': modalidade},
        )


# --- lote 5: plano de oferta, cursos, auditoria e procedimentos ---------------------------

CENARIO = 'Cenário de Oferta E2E Rotas'
CERTIFICACAO_PARCIAL = 'Certificação Parcial E2E Rotas'
REQUERIMENTO = 'Requerimento E2E Rotas'


def criar_plano_oferta() -> None:
    """Cenário de oferta com simulações e previsão de alunos — 8 rotas de ``plano_oferta``."""
    from edu.models import CenarioOferta, Matriz, PrevisaoQuantidadeAlunos, Professor, SimulacaoAfastamento, SimulacaoContratacao

    cenario, _ = CenarioOferta.objects.get_or_create(uo=_campus(), ano_letivo=_ano(), periodo_letivo=1, defaults={'descricao': CENARIO})
    SimulacaoAfastamento.objects.get_or_create(
        cenario=cenario,
        professor=Professor.objects.order_by('id').first(),
        defaults={'ano_inicio': _ano(), 'periodo_inicio': 1, 'tipo_substituicao': 1},
    )
    SimulacaoContratacao.objects.get_or_create(cenario=cenario, defaults={'ano_inicio': _ano(), 'periodo_inicio': 1, 'tipo_contratacao': 1})
    # Destravada pela correção de `edu/models/plano_oferta.py:312` (`super()` sem argumentos).
    # `matriz` é obrigatória na prática: os dois forms da tela leem
    # `self.instance.matriz.qtd_periodos_letivos` sem guarda (edu/forms/plano_oferta.py:17,28).
    PrevisaoQuantidadeAlunos.objects.get_or_create(cenario=cenario, defaults={'matriz': Matriz.objects.order_by('id').first()})


def criar_cursos() -> None:
    """Ato regulatório, certificação parcial e tramitação e-MEC — 7 rotas de ``cursos``."""
    from edu.models import AtoRegulatorioCurso, ConfiguracaoCertificacaoParcial, CursoCampus, Matriz, Modalidade, TramitacaoProcessoEMEC

    curso = CursoCampus.objects.get(codigo='10101')
    AtoRegulatorioCurso.objects.get_or_create(curso=curso, tipo='1', defaults={'data': DATA})
    TramitacaoProcessoEMEC.objects.get_or_create(
        curso=curso,
        numero_processo='E2E-ROTAS-001',
        defaults={'tipo_processo': '1', 'data_cadastro': DATA, 'data_protocolo': DATA},
    )
    ConfiguracaoCertificacaoParcial.objects.get_or_create(
        descricao=CERTIFICACAO_PARCIAL,
        defaults={
            'matriz': Matriz.objects.order_by('id').first(),
            'modalidade_certificacao': Modalidade.objects.order_by('id').first(),
            'titulacao_masculino': 'Técnico',
            'titulacao_feminino': 'Técnica',
        },
    )


def criar_procedimentos_lote5() -> None:
    """Medida, premiação, requerimento e aproveitamentos — 13 rotas de ``procedimentos``.

    Tudo pendurado no aluno do smoke (``CPF_ALUNO_SMOKE``): medida disciplinar e premiação
    aparecem no prontuário, que ``test_08_aluno`` inspeciona no aluno da cadeia.
    """
    from edu.models import (
        AbonoFaltas,
        AproveitamentoComponente,
        AproveitamentoEstudo,
        CertificacaoConhecimento,
        ComponenteCurricular,
        CreditoEspecial,
        ItemConfiguracaoAvaliacao,
        ItemConfiguracaoCreditosEspeciais,
        MedidaDisciplinar,
        Premiacao,
        Requerimento,
        RequerimentoAproveitamentoEstudo,
        SolicitacaoReposicaoAtividade,
        TipoMedidaDisciplinar,
        TipoPremiacao,
    )

    aluno, matricula_periodo = _aluno(), _matricula_periodo()
    componente = ComponenteCurricular.objects.order_by('id').first()

    tipo_medida, _ = TipoMedidaDisciplinar.objects.get_or_create(descricao='Medida E2E Rotas')
    MedidaDisciplinar.objects.get_or_create(aluno=aluno, tipo=tipo_medida, defaults={'data_inicio': DATA})
    tipo_premio, _ = TipoPremiacao.objects.get_or_create(descricao='Premiação E2E Rotas')
    Premiacao.objects.get_or_create(aluno=aluno, tipo=tipo_premio, defaults={'data': DATA})

    # `edu.Requerimento` é do aluno (`aluno`/`tipo`/`data`) — não confundir com o
    # `processo_eletronico.Requerimento`, que tem interessado e tipo de processo.
    Requerimento.objects.get_or_create(aluno=aluno, tipo=1, defaults={'data': DATA})
    RequerimentoAproveitamentoEstudo.objects.get_or_create(aluno=aluno, tipo=1, defaults={'data': DATA})

    if matricula_periodo and componente:
        AproveitamentoEstudo.objects.get_or_create(
            matricula_periodo=matricula_periodo, componente_curricular=componente, defaults={'data': DATA, 'nota': 70}
        )
        CertificacaoConhecimento.objects.get_or_create(
            matricula_periodo=matricula_periodo, componente_curricular=componente, defaults={'data': DATA, 'nota': 70}
        )
        AproveitamentoComponente.objects.get_or_create(matricula_periodo=matricula_periodo, componente_curricular=componente)
        item_credito = ItemConfiguracaoCreditosEspeciais.objects.order_by('id').first()
        if item_credito:
            CreditoEspecial.objects.get_or_create(matricula_periodo=matricula_periodo, item_configuracao_creditos_especiais=item_credito)

    abono = AbonoFaltas.objects.filter(aluno=aluno).order_by('id').first()
    item_avaliacao = ItemConfiguracaoAvaliacao.objects.order_by('id').first()
    if abono and item_avaliacao:
        SolicitacaoReposicaoAtividade.objects.get_or_create(abono_faltas=abono, item_configuracao_avaliacao=item_avaliacao)


# --- lote 9: aluno e registro ENADE descartáveis ------------------------------------------
#
# `evadir_aluno` e `remover_situacao_enade` mudam o estado do objeto no GET, de forma que
# nada desfaz. Precisam de aluno próprio: evadir o da cadeia quebraria de `test_05` em diante.
ALUNO_EVASAO_CPF = '159.215.213-96'


def criar_aluno_descartavel() -> None:
    """Aluno de sacrifício, matriculado, para as ações que mudam a situação dele.

    Reusa ``seed.cadastrar_aluno``/``seed.matricular_aluno`` em vez de reimplementar: são os
    mesmos passos que a cadeia usa, e replicá-los aqui deixaria duas verdades sobre "o que é
    um aluno matriculado".
    """
    from comum.models import Ano
    from edu.models import Aluno, ConvocacaoENADE, CursoCampus, FormaIngresso, Matriz, RegistroConvocacaoENADE
    from rh.models import PessoaFisica

    from edu.tests.e2e import seed

    if not Aluno.objects.filter(pessoa_fisica__cpf=ALUNO_EVASAO_CPF).exists():
        pessoa, _ = PessoaFisica.objects.get_or_create(
            cpf=ALUNO_EVASAO_CPF, defaults={'nome_registro': 'Aluna E2E Rotas Evasao', 'nome': 'Aluna E2E Rotas Evasao'}
        )
        curso = CursoCampus.objects.get(codigo='10101')
        aluno = seed.cadastrar_aluno(
            pessoa,
            _aluno().cidade,
            Ano.objects.get(ano=ANO),
            FormaIngresso.objects.order_by('id').first(),
            curso,
            Matriz.objects.order_by('id').first(),
        )
        seed.matricular_aluno(aluno, Ano.objects.get(ano=ANO), curso, aluno.matriz)

    # `remover_situacao_enade` apaga a situação lançada; sobre o registro da cadeia isso
    # desfaria o que `test_14_enade` acabou de afirmar.
    # Sem `if convocacao:`: `criar_enade` roda antes e garante uma, e um registro pulado calado
    # só apareceria depois, como alvo ausente no `test_25`.
    aluno = Aluno.objects.get(pessoa_fisica__cpf=ALUNO_EVASAO_CPF)
    RegistroConvocacaoENADE.objects.get_or_create(aluno=aluno, convocacao_enade=ConvocacaoENADE.objects.order_by('id').first())


# --- lote 10: diário descartável ----------------------------------------------------------
#
# As ações de diário (dividir, replicar, gerar configurações, transferir posse, suspender)
# gravam no GET. Um diário só para elas remove a razão que as mantinha dispensadas.
#
# A turma nasce por `Turma.gerar_turmas`, o mesmo caminho do seed 008 e da produção —
# construir `Turma`/`Diario` a mão falha com `NoneType.pk` porque o `save()` do diário depende
# de estado que só o gerador monta. Duas armadilhas medidas na assinatura:
# `gerar_turmas` tem 13 posicionais (os três últimos sem default), e `componentes` não pode vir
# fatiado — `edu/models/turmas.py:309` faz `componentes.filter(...) | componentes.filter(...)`.
#
# Duas restrições do alvo, ambas para não escrever na cadeia:
# 1. `ano_letivo=2018`: três `.get()` da cadeia buscam turma por ano+período+curso sem filtrar
#    `periodo_matriz` (`test_04_matricula.py:41`, `test_06_encerramento.py:32`,
#    `test_03_turmas.py:72`); turma nova em 2019.1 no curso 10101 os quebraria.
# 2. `local_aula` PREENCHIDO logo após a geração: os diários nascem sem local e, nesse estado,
#    entram em `edu/forms/turmas.py:105` (`local_aula__isnull=True`), que é o queryset da tela
#    usada por `test_03_turmas::test_configura_diario`.
ANO_DESCARTAVEL = 2018


def criar_diario_descartavel() -> None:
    """Turma 2018 + diários de sacrifício para as ações que gravam no GET — 7 rotas."""
    from comum.models import Ano, Sala
    from edu.models import (
        CalendarioAcademico,
        ComponenteCurricular,
        CursoCampus,
        Diario,
        HorarioCampus,
        JustificativaSuspensaoDiario,
        SuspensaoDiario,
        Turma,
        Turno,
    )

    ano, _ = Ano.objects.get_or_create(ano=ANO_DESCARTAVEL)
    if not Turma.objects.filter(ano_letivo=ano).exists():
        curso = CursoCampus.objects.get(codigo='10101')
        matriz = curso.matrizes.first()
        Turma.gerar_turmas(
            ano,
            1,
            {1: Turno.objects.order_by('id').first()},
            {1: 5},
            {1: 1},
            curso,
            matriz,
            HorarioCampus.objects.order_by('id').first(),
            CalendarioAcademico.objects.order_by('id').first(),
            # `exclude(POS.0001)`: `test_05_periodo.py:43` faz
            # `Diario.objects.get(componente_curricular__componente__sigla='POS.0001',
            # turma__curso_campus__codigo='10101', turma__periodo_letivo=1)` — **sem filtrar
            # ano**. Isolar a turma em 2018 não basta: o `.get()` alcança qualquer ano, e
            # `replicar_diario` ainda multiplica as cópias. O componente é que precisa diferir.
            ComponenteCurricular.objects.filter(matriz=matriz, periodo_letivo=1).exclude(componente__sigla='POS.0001'),
            False,
            None,
            True,
        )

    diarios = Diario.objects.filter(turma__ano_letivo=ano).order_by('id')
    sala = Sala.objects.filter(nome='Sala E2E Rotas').first() or Sala.objects.order_by('id').first()
    diarios.filter(local_aula__isnull=True).update(local_aula=sala)

    # `JustificativaSuspensaoDiario` vem do `initial_data`, que o banco de teste não carrega,
    # e a FK é NOT NULL com default=8.
    justificativa, _ = JustificativaSuspensaoDiario.objects.get_or_create(descricao='Suspensão E2E Rotas', defaults={'codigo_pedemeia': 99})
    SuspensaoDiario.objects.get_or_create(diario=diarios.first(), defaults={'inicio': DATA, 'justificativa': justificativa})


# --- lote 12: nada consta ------------------------------------------------------------------
#
# Família inteira fora da cadeia: nenhum `.get()` de `seed.py`/`test_0*`/`test_1[0-4]*` consulta
# `NadaConsta`, `ConfiguracaoNadaConsta` nem `TipoNadaConsta` — grepado antes de escrever. O
# registro fica no aluno do smoke, não no da cadeia, porque aparece na aba "Nada Consta" do
# prontuário que `test_08_aluno` inspeciona.
CONFIG_NADA_CONSTA = 'Nada Consta E2E Rotas'


def criar_nada_consta() -> None:
    """Configuração e registro de nada consta — 4 rotas de ``nada_consta``."""
    from edu.models import ConfiguracaoNadaConsta, NadaConsta, TipoNadaConsta

    ConfiguracaoNadaConsta.objects.get_or_create(descricao=CONFIG_NADA_CONSTA, defaults={'uo': _campus()})
    tipo, _ = TipoNadaConsta.objects.get_or_create(descricao='Tipo E2E Rotas')
    NadaConsta.objects.get_or_create(tipo=tipo, aluno=_aluno())
