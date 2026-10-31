from __future__ import annotations

import datetime
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, adicionar_ao_filteredselect, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


# Só os cadastros que a doc referencia viram captura: a tarefa dos cadastros de apoio é
# listada, não documentada tela a tela (ver `docs/agents/PROTOTIPO-doc-usuario-eventos.md`),
# e capturar os 24 deixaria 20 WebP sem uso no destino.
SLUGS_CAPTURADOS = {'vacina', 'tipo-exame-laboratorial', 'orientacao-nutricional'}

# As 9 perguntas de alteração do exame físico são `ChoiceField` obrigatórios.
PERGUNTAS_EXAME_FISICO = [
    'Ectoscopia alterada?',
    'Aparelho cardiovascular alterado?',
    'Aparelho respiratório alterado?',
    'Abdome alterado?',
    'Membros inferiores alterados?',
    'Membros superiores alterados?',
    'Sistema neurológico alterado?',
    'Estado mental alterado?',
    'Outros órgãos/sistemas alterados?',
]


def _admin_cadastrar(tela: Tela, capturar, modelo: str, botao: str, dados: list[tuple[str, ...]], slug: str) -> None:
    tela.ir(f'/admin/saude/{modelo}/')
    tela.ver_botao(botao)
    if slug == 'vacina':
        capturar(tela.pagina, 'cadastros-apoio-listagem')
    tela.clicar_botao(botao)
    anotar_tela(f'cadastro-{slug}', tela)
    if slug in SLUGS_CAPTURADOS:
        capturar(tela.pagina, f'cadastro-{slug}')
    tela.preencher_formulario(dados)
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')


def test_tarefas_cadastros_planejamento_e_relatorios(logado_saude, capturar):
    sufixo = uuid4().hex[:7]
    tela = Tela(logado_saude('coordenador'))

    # Inventário: Buscar Atividades de Registros Administrativos.
    tela.ir('/admin/saude/atividaderegistroadministrativo/')
    tela.filtros().preencher('Texto', 'texto', 'Orientação individual')
    tela.filtros().clicar_botao('Filtrar')
    tela.ver_texto('Orientação individual')
    capturar(tela.pagina, 'atividade-registro-busca')

    # Inventário: Cadastrar e Buscar Registros Administrativos.
    tela.ir('/admin/saude/registroadministrativo/')
    tela.clicar_botao('Adicionar Registro Administrativo')
    anotar_tela('registro-administrativo-formulario', tela)
    tela.preencher_formulario(
        [
            ('Descrição', 'textarea', f'Registro administrativo de documentação {sufixo}'),
            ('Atividades', 'autocomplete multiplo', 'Orientação individual'),
        ]
    )
    capturar(tela.pagina, 'registro-administrativo-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    tela.filtros().preencher('Texto', 'texto', sufixo)
    tela.filtros().clicar_botao('Filtrar')
    tela.ver_texto(sufixo)
    capturar(tela.pagina, 'registro-administrativo-listagem')

    # Inventário: Cadastrar Atividade em Grupo.
    hoje = datetime.date.today()
    tela.ir('/admin/saude/atividadegrupo/')
    tela.clicar_botao('Adicionar Atividade em Grupo')
    anotar_tela('atividade-grupo-formulario', tela)
    tela.preencher_formulario(
        [
            ('Nome do Evento/Atividade', 'texto', f'Roda de conversa {sufixo}'),
            ('Tipo', 'autocomplete', 'Reunião'),
            ('Tema', 'texto', 'Promoção da saúde'),
            ('Campus', 'autocomplete', 'CZN', ''),
            ('Recurso Necessário', 'textarea', 'Sala e projetor'),
            ('Número de Participantes', 'número', '20'),
            ('Data de Início', 'data e hora', f'{(hoje + datetime.timedelta(days=10)).strftime("%d/%m/%Y")} 09:00'),
            ('Data de Término', 'data e hora', f'{(hoje + datetime.timedelta(days=10)).strftime("%d/%m/%Y")} 11:00'),
            ('Responsáveis', 'autocomplete multiplo', '111001'),
        ]
    )
    capturar(tela.pagina, 'atividade-grupo-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    capturar(tela.pagina, 'atividade-grupo-listagem')

    # Inventário: Cadastrar Metas e Adicionar Ação Independente.
    tela.ir('/admin/saude/metaacaoeducativa/')
    capturar(tela.pagina, 'metas-listagem')
    tela.clicar_botao('Adicionar Meta da Ação Educativa')
    anotar_tela('meta-formulario', tela)
    tela.preencher_formulario(
        [
            ('Ano de Referência', 'autocomplete', str(hoje.year)),
            ('Objetivos', 'autocomplete multiplo', 'Promover saúde'),
            ('Descrição', 'textarea', f'Meta educativa {sufixo}'),
            ('Tipo de Indicador', 'lista', 'Número de Ações'),
            ('Quantidade', 'número', '2'),
        ]
    )
    capturar(tela.pagina, 'meta-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.clicar_botao('Cadastrar Ação Independente')
    anotar_tela('acao-independente-formulario', tela)
    tela.preencher_formulario(
        [
            ('Nome do Evento/Atividade', 'texto', f'Ação independente {sufixo}'),
            ('Recurso Necessário', 'textarea', 'Material educativo'),
            ('Data de Início', 'data e hora', f'{(hoje + datetime.timedelta(days=20)).strftime("%d/%m/%Y")} 14:00'),
            ('Data de Término', 'data e hora', f'{(hoje + datetime.timedelta(days=20)).strftime("%d/%m/%Y")} 16:00'),
        ]
    )
    capturar(tela.pagina, 'acao-independente-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Ação cadastrada com sucesso.')

    # Inventário: Relatório dos Pacientes Bloqueados.
    tela.ir('/admin/saude/bloqueioatendimentosaude/')
    anotar_tela('pacientes-bloqueados', tela)
    capturar(tela.pagina, 'pacientes-bloqueados')
    tela.ver_texto('Aluno Saúde Documentação')


def test_cadastros_de_apoio_curados_no_inventario(logado_saude, capturar):
    sufixo = uuid4().hex[:7]
    tela = Tela(logado_saude('coordenador'))
    simples = [
        ('vacina', 'Adicionar Vacina', [('Nome', 'texto', f'Vacina doc {sufixo}'), ('Número de Doses', 'número', '2')], 'vacina'),
        ('doenca', 'Adicionar Doença', [('Nome', 'texto', f'Doença doc {sufixo}')], 'doenca'),
        ('droga', 'Adicionar Droga', [('Nome', 'texto', f'Droga doc {sufixo}')], 'droga'),
        ('metodocontraceptivo', 'Adicionar Método Contraceptivo', [('Nome', 'texto', f'Método doc {sufixo}')], 'metodo-contraceptivo'),
        ('dificuldadeoral', 'Adicionar Dificuldade Oral', [('Dificuldade Oral', 'texto', f'Dificuldade doc {sufixo}')], 'dificuldade-oral'),
        (
            'procedimentoenfermagem',
            'Adicionar Procedimento de Enfermagem',
            [('Denominação', 'texto', f'Procedimento enfermagem {sufixo}')],
            'procedimento-enfermagem',
        ),
        ('cid', 'Adicionar Doença', [('Código', 'texto', f'DOC{sufixo}'), ('Denominação', 'texto', f'CID documentação {sufixo}')], 'cid'),
        ('motivochegadapsicologia', 'Adicionar Motivo da Chegada', [('Descrição', 'texto', f'Motivo chegada {sufixo}')], 'motivo-chegada'),
        ('queixapsicologica', 'Adicionar Queixa', [('Descrição', 'texto', f'Queixa psicológica {sufixo}')], 'queixa-psicologica'),
        ('tipoatividadegrupo', 'Adicionar Tipo de Atividade em Grupo', [('Descrição', 'texto', f'Tipo atividade {sufixo}')], 'tipo-atividade-grupo'),
        (
            'categoriaexamelaboratorial',
            'Adicionar Categoria de Exame Laboratorial',
            [('Nome', 'texto', f'Categoria exame {sufixo}')],
            'categoria-exame',
        ),
        (
            'procedimentomultidisciplinar',
            'Adicionar Procedimento Multidisciplinar',
            [('Denominação', 'texto', f'Procedimento multidisciplinar {sufixo}')],
            'procedimento-multidisciplinar',
        ),
        ('anoreferenciaacaoeducativa', 'Adicionar Ano de Referência', [('Ano', 'texto', str(2100 + int(sufixo[0], 16)))], 'ano-referencia'),
        (
            'objetivoacaoeducativa',
            'Adicionar Objetivo da Ação Educativa',
            [('Descrição', 'texto', f'Objetivo educativo {sufixo}')],
            'objetivo-educativo',
        ),
        (
            'avaliacaogastrointestinal',
            'Adicionar Avaliação Gastrointestinal',
            [('Descrição', 'texto', f'Avaliação gastrointestinal {sufixo}')],
            'avaliacao-gastrointestinal',
        ),
        ('restricaoalimentar', 'Adicionar Restrição Alimentar', [('Descrição', 'texto', f'Restrição alimentar {sufixo}')], 'restricao-alimentar'),
        (
            'diagnosticonutricional',
            'Adicionar Diagnóstico Nutricional',
            [('Descrição', 'texto', f'Diagnóstico nutricional {sufixo}')],
            'diagnostico-nutricional',
        ),
        (
            'frequenciapraticaalimentar',
            'Adicionar Alimento/Bebida para Frequência de Prática Alimentar',
            [('Descrição', 'texto', f'Alimento {sufixo}'), ('Valor Recomendado', 'número', '3')],
            'frequencia-alimentar',
        ),
        (
            'perguntamarcadornutricao',
            'Adicionar Pergunta de Marcador Alimentar',
            [('Pergunta', 'texto', f'Pergunta alimentar {sufixo}'), ('Tipo de Resposta', 'lista', 'Única Escolha')],
            'pergunta-alimentar',
        ),
        ('motivoatendimentonutricao', 'Adicionar Motivo do Atendimento', [('Descrição', 'texto', f'Motivo nutricional {sufixo}')], 'motivo-nutricao'),
    ]
    for modelo, botao, dados, slug in simples:
        _admin_cadastrar(tela, capturar, modelo, botao, dados, slug)

    _admin_cadastrar(
        tela,
        capturar,
        'tipoexamelaboratorial',
        'Adicionar Tipo de Exame Laboratorial',
        [
            ('Categoria', 'autocomplete', 'Perfil Glicêmico'),
            ('Nome', 'texto', f'Exame laboratorial {sufixo}'),
            ('Unidade de Medida', 'texto', 'mg/dL'),
            ('Valores de Referência', 'texto rico', 'Valores conforme faixa etária.'),
        ],
        'tipo-exame-laboratorial',
    )
    _admin_cadastrar(
        tela,
        capturar,
        'orientacaonutricional',
        'Adicionar Orientação Nutricional',
        [('Título', 'texto', f'Orientação {sufixo}'), ('Descrição', 'texto rico', 'Orientação nutricional de documentação.')],
        'orientacao-nutricional',
    )
    _admin_cadastrar(
        tela,
        capturar,
        'receitanutricional',
        'Adicionar Receita',
        [('Título', 'texto', f'Receita {sufixo}'), ('Descrição', 'texto rico', 'Receita alimentar de documentação.')],
        'receita-nutricional',
    )
    _admin_cadastrar(
        tela,
        capturar,
        'opcaorespostamarcadornutricao',
        'Adicionar Opção de Resposta de Marcador Alimentar',
        [('Pergunta', 'autocomplete', f'Pergunta alimentar {sufixo}'), ('Opção de Resposta', 'texto', f'Resposta {sufixo}')],
        'opcao-resposta-alimentar',
    )


def _prontuario_do_aluno():
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    return aluno, Prontuario.get_prontuario(aluno.get_vinculo())


def test_buscar_prontuarios_e_abrir_atendimentos(logado_saude, capturar):
    from saude.models import Atendimento

    aluno, prontuario = _prontuario_do_aluno()
    Atendimento.objects.filter(prontuario=prontuario).delete()

    tela = Tela(logado_saude('coordenador')).ir('/saude/prontuarios/')
    tela.ver_item_de_menu('Atividades Estudantis::Saúde::Prontuários')
    tela.preencher_formulario([('Buscar por Nome, Matrícula ou CPF', 'texto', aluno.matricula), ('Vínculo', 'lista', 'Aluno')])
    capturar(tela.pagina, 'prontuarios-busca')
    tela.clicar_botao('Buscar')
    tela.ver_texto(aluno.matricula)
    capturar(tela.pagina, 'prontuarios-resultado-aluno')
    tela.cartao(aluno.matricula).clicar_botao('Prontuário')
    tela.esperar()
    anotar_tela('prontuario-aluno', tela)
    capturar(tela.pagina, 'prontuario-aluno')

    tela.ir('/saude/prontuarios/')
    tela.preencher_formulario([('Buscar por Nome, Matrícula ou CPF', 'texto', '111001'), ('Vínculo', 'lista', 'Servidor')])
    tela.clicar_botao('Buscar')
    tela.ver_texto('111001')
    capturar(tela.pagina, 'prontuarios-resultado-servidor')

    fluxos = [
        ('auxiliar_enfermagem', 'Adicionar Atendimento Médico/Enfermagem', 'Atendimento Médico/Enfermagem', 'atendimento-medico-enfermagem'),
        ('fisioterapeuta', 'Adicionar Atendimento de Fisioterapia', 'Atendimento de Fisioterapia', 'atendimento-fisioterapia'),
        ('nutricionista', 'Adicionar Atendimento Nutricional', 'Atendimento Nutricional', 'atendimento-nutricao'),
        ('psicologo', 'Adicionar Atendimento Psicológico', 'Atendimento Psicológico', 'atendimento-psicologia'),
        ('odontologo', 'Adicionar Atendimento Odontológico', 'Atendimento Odontológico', 'atendimento-odontologia'),
    ]
    for papel, botao, titulo, slug in fluxos:
        pagina = Tela(logado_saude(papel)).ir(f'/saude/prontuario/{prontuario.vinculo_id}/')
        pagina.ver_botao(botao)
        pagina.clicar_botao(botao)
        pagina.esperar()
        pagina.ver_titulo(titulo)
        anotar_tela(slug, pagina)
        capturar(pagina.pagina, slug)

    medico_enfermagem = Atendimento.objects.get(prontuario=prontuario, tipo=2)
    fisioterapia = Atendimento.objects.get(prontuario=prontuario, tipo=7)
    nutricao = Atendimento.objects.get(prontuario=prontuario, tipo=5)
    psicologia = Atendimento.objects.get(prontuario=prontuario, tipo=4)
    odontologia = Atendimento.objects.get(prontuario=prontuario, tipo=3)

    # Inventário: intervenção de enfermagem.
    enfermagem = Tela(logado_saude('tecnico_enfermagem')).ir(f'/saude/atendimento_medico_enfermagem/{medico_enfermagem.pk}/')
    enfermagem.clicar_aba('Motivo do Atendimento').clicar_botao('Adicionar Motivo')
    enfermagem.preencher('Motivo do Atendimento', 'textarea', 'Acolhimento e avaliação inicial.')
    capturar(enfermagem.pagina, 'atendimento-enfermagem-motivo')
    enfermagem.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    enfermagem.clicar_aba('Intervenção de Enfermagem').clicar_botao('Adicionar Intervenção')
    anotar_tela('intervencao-enfermagem-formulario', enfermagem)
    enfermagem.preencher_formulario(
        [('Procedimento', 'autocomplete multiplo', 'Outros'), ('Descrição', 'textarea', 'Orientação e acompanhamento de enfermagem.')]
    )
    capturar(enfermagem.pagina, 'intervencao-enfermagem-formulario')
    enfermagem.clicar_botao('Enviar').sucesso('Intervenção de enfermagem registrada com sucesso.')

    # Inventário: registro médico e fechamento do atendimento compartilhado.
    medico = Tela(logado_saude('medico')).ir(f'/saude/atendimento_medico_enfermagem/{medico_enfermagem.pk}/')
    medico.clicar_aba('Anamnese').clicar_botao('Adicionar Anamnese')
    medico.preencher('HDA', 'textarea', 'História clínica registrada durante a consulta.')
    capturar(medico.pagina, 'atendimento-medico-anamnese')
    medico.clicar_botao('Salvar').sucesso('Anamnese registrada com sucesso.')
    medico.clicar_aba('Hipótese Diagnóstica')
    medico.quadro('Conduta Médica').clicar_link('Adicionar')
    medico.preencher('Conduta', 'textarea', 'Conduta e orientações médicas.')
    capturar(medico.pagina, 'atendimento-medico-conduta')
    medico.clicar_botao('Salvar').sucesso('Conduta Médica registrada com sucesso.')
    _fechar_atendimento(medico, capturar, 'medico-enfermagem')

    # Inventário: atendimento de fisioterapia.
    fisio = Tela(logado_saude('fisioterapeuta')).ir(f'/saude/atendimento_fisioterapia/{fisioterapia.pk}/')
    fisio.clicar_aba('Anamnese').clicar_botao('Adicionar')
    fisio.preencher('Anamnese', 'textarea', 'Avaliação fisioterapêutica inicial.')
    capturar(fisio.pagina, 'fisioterapia-anamnese')
    fisio.clicar_botao('Salvar').sucesso('Anamnese registrada com sucesso.')
    _fechar_atendimento(fisio, capturar, 'fisioterapia')

    # Inventário: atendimento nutricional.
    nutricionista = Tela(logado_saude('nutricionista')).ir(f'/saude/atendimento_nutricional/{nutricao.pk}/')
    nutricionista.clicar_aba('Motivo do atendimento').clicar_botao('Adicionar')
    adicionar_ao_filteredselect(nutricionista.pagina, 'id_motivo_from', 'Outros')
    nutricionista.preencher('Observações', 'textarea', 'Avaliação nutricional inicial.')
    capturar(nutricionista.pagina, 'nutricao-motivo')
    nutricionista.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    nutricionista.clicar_aba('Conduta Nutricional')
    nutricionista.quadro('Conduta').clicar_link('Adicionar')
    nutricionista.preencher('Conduta', 'texto rico', 'Orientações alimentares individualizadas.')
    capturar(nutricionista.pagina, 'nutricao-conduta')
    nutricionista.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    _fechar_atendimento(nutricionista, capturar, 'nutricao')

    # Inventário: atendimento psicológico.
    psicologo = Tela(logado_saude('psicologo')).ir(f'/saude/atendimento_psicologico/{psicologia.pk}/')
    psicologo.clicar_aba('Informações sobre o atendimento').clicar_link('Registrar Data/Hora do Atendimento')
    psicologo.preencher('Data/hora do atendimento', 'data', datetime.date.today().strftime('%d/%m/%Y'))
    capturar(psicologo.pagina, 'psicologia-data-hora')
    psicologo.clicar_botao('Salvar').sucesso('Data/hora do atendimento registrada com sucesso.')
    psicologo.clicar_aba('Informações sobre o atendimento').clicar_botao('Adicionar')
    anotar_tela('psicologia-registro-formulario', psicologo)
    psicologo.preencher_formulario(
        [
            ('Motivo da Chegada', 'autocomplete', 'Demanda Espontânea'),
            ('Queixa principal', 'checkbox multiplo', 'Ansiedade'),
            ('Queixa identificada', 'checkbox multiplo', 'Ansiedade'),
            ('Intervenção / Encaminhamento', 'textarea', 'Acolhimento e orientação psicológica.'),
            ('Tipo de atendimento', 'autocomplete', 'Atendimento individual'),
        ]
    )
    capturar(psicologo.pagina, 'psicologia-registro-formulario')
    psicologo.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    _fechar_atendimento(psicologo, capturar, 'psicologia')

    # Inventário: atendimento odontológico.
    odonto = Tela(logado_saude('odontologo')).ir(f'/saude/atendimento_odontologico/{odontologia.pk}/')
    odonto.clicar_aba('Situação Clínica')
    odonto.quadro('Exame Periodontal').clicar_link('Adicionar')
    odonto.preencher('Ocorrência', 'lista', 'Sangramento')
    adicionar_ao_filteredselect(odonto.pagina, 'id_sextante_from', 'S1', 'S2')
    capturar(odonto.pagina, 'odontologia-exame-periodontal')
    odonto.clicar_botao('Salvar').sucesso('Exame periodontal registrado com sucesso.')
    odonto.clicar_link('Voltar ao Atendimento').esperar().clicar_aba('Situação Clínica')
    odonto.quadro('Exame Estomatológico').clicar_botao('Adicionar')
    anotar_tela('odontologia-exame-estomatologico', odonto)
    capturar(odonto.pagina, 'odontologia-exame-estomatologico')
    odonto.clicar_botao('Salvar').sucesso('Exame Estomatológico registrado com sucesso.')
    odonto.clicar_aba('Plano de Tratamento').clicar_link('Gerar Plano de Tratamento Automático')
    odonto.sucesso('Plano de Tratamento criado com sucesso.')
    _fechar_atendimento(odonto, capturar, 'odontologia')


def _fechar_atendimento(tela: Tela, capturar, slug: str) -> None:
    tela.clicar_link('Fechar')
    tela.preencher('Observação de Fechamento', 'textarea', 'Atendimento concluído.')
    capturar(tela.pagina, f'{slug}-fechamento')
    tela.clicar_botao('Salvar').sucesso('Atendimento fechado com sucesso.')


def test_agenda_criar_consultar_e_reservar(logado_saude, capturar):
    from saude.models import BloqueioAtendimentoSaude, HorarioAtendimento

    BloqueioAtendimentoSaude.objects.filter(vinculo_paciente__pessoa__pessoafisica__cpf='559.454.350-31').delete()
    HorarioAtendimento.objects.filter(cadastrado_por_vinculo__user__username='111001').delete()
    data = datetime.date.today() + datetime.timedelta(days=10)
    tela = Tela(logado_saude('coordenador')).ir('/saude/agenda_atendimentos/')
    tela.ver_item_de_menu('Atividades Estudantis::Saúde::Agenda de Atendimentos')
    tela.ver_titulo('Agenda de Atendimentos')
    capturar(tela.pagina, 'agenda-listagem')
    tela.clicar_botao('Adicionar Data de Atendimento')
    tela.ver_titulo('Adicionar Horário de Atendimento')
    anotar_tela('agenda-formulario', tela)
    tela.preencher_formulario(
        [
            ('Especialidade', 'lista', 'Avaliação de Saúde'),
            ('Data Inicial', 'data', data.strftime('%d/%m/%Y')),
            ('Horário de Início', 'hora', '08:00'),
            ('Horário de Término', 'hora', '10:00'),
            ('Duração de cada atendimento (em minutos)', 'número', '30'),
        ]
    )
    capturar(tela.pagina, 'agenda-formulario')
    tela.clicar_botao('Gerar Horários')
    tela.esperar()
    anotar_tela('agenda-confirmacao-horarios', tela)
    capturar(tela.pagina, 'agenda-confirmacao-horarios')
    tela.clicar_botao('Salvar')
    tela.sucesso('Horário(s) de atendimento(s) registrado(s) com sucesso.')

    tela.ir('/saude/agenda_atendimentos/')
    tela.preencher_formulario(
        [
            ('Especialidade', 'lista', 'Avaliação de Saúde'),
            ('Data Inicial', 'data', data.strftime('%d/%m/%Y')),
            ('Data Final', 'data', data.strftime('%d/%m/%Y')),
        ]
    )
    tela.clicar_botao('Enviar')
    assert HorarioAtendimento.objects.filter(data=data, cancelado=False).exists()
    capturar(tela.pagina, 'agenda-resultado')

    aluno = Tela(logado_saude('aluno')).ir('/saude/agenda_atendimentos/')
    aluno.preencher_formulario(
        [
            ('Especialidade', 'lista', 'Avaliação de Saúde'),
            ('Data Inicial', 'data', data.strftime('%d/%m/%Y')),
            ('Data Final', 'data', data.strftime('%d/%m/%Y')),
        ]
    )
    aluno.clicar_botao('Enviar')
    aluno.ver_botao('Agendar')
    capturar(aluno.pagina, 'agenda-aluno-disponivel')
    aluno.clicar_botao('Agendar')
    aluno.sucesso('Horário de atendimento agendado com sucesso.')
    capturar(aluno.pagina, 'agenda-aluno-reservado')


def test_avaliacao_de_saude_e_atendimento_multidisciplinar(logado_saude, capturar):
    from saude.models import Atendimento

    _, prontuario = _prontuario_do_aluno()
    Atendimento.objects.filter(prontuario=prontuario, tipo__in=(1, 6)).delete()

    # Inventário: Avaliação de Saúde — o botão só aparece no prontuário de aluno, e o
    # fechamento exige as fichas Sinais Vitais e Exame Físico (quadro "Regras para fechamento").
    tela = Tela(logado_saude('medico')).ir(f'/saude/prontuario/{prontuario.vinculo_id}/')
    tela.clicar_botao('Adicionar Avaliação de Saúde').sucesso('Avaliação biomédica gerada com sucesso.')
    tela.esperar()
    anotar_tela('avaliacao-saude', tela)
    capturar(tela.pagina, 'avaliacao-saude')

    tela.clicar_aba('Sinais Vitais').quadro('Sinais Vitais').clicar_botao('Adicionar')
    anotar_tela('avaliacao-saude-sinais-vitais', tela)
    capturar(tela.pagina, 'avaliacao-saude-sinais-vitais')
    tela.preencher_formulario(
        [
            ('Pressão Sistólica', 'número', '120'),
            ('Pressão Diastólica', 'número', '80'),
            ('Pulsação', 'número', '72'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Sinais Vitais registrados com sucesso.')

    tela.clicar_aba('Exame Físico').quadro('Exame Físico').clicar_botao('Adicionar')
    # O exame físico é um checklist: as 9 perguntas de alteração são obrigatórias.
    tela.preencher_formulario([(pergunta, 'lista', 'Não') for pergunta in PERGUNTAS_EXAME_FISICO])
    tela.clicar_botao('Salvar').sucesso('Exame Físico registrado com sucesso.')
    _fechar_atendimento(tela, capturar, 'avaliacao-saude')

    # Inventário: Atendimento Multidisciplinar — Médico, Odontólogo, Nutricionista ou Psicólogo.
    tela = Tela(logado_saude('medico')).ir(f'/saude/prontuario/{prontuario.vinculo_id}/')
    tela.clicar_botao('Adicionar Atendimento Multidisciplinar').sucesso('Atendimento Multidisciplinar gerado com sucesso.')
    tela.esperar()
    anotar_tela('atendimento-multidisciplinar', tela)
    capturar(tela.pagina, 'atendimento-multidisciplinar')

    tela.clicar_aba('Procedimentos').clicar_botao('Adicionar')
    anotar_tela('multidisciplinar-procedimento', tela)
    capturar(tela.pagina, 'multidisciplinar-procedimento')
    # O rótulo "Procedimentos:" fica fora do `div.selector` e o tipo `filteredselectmultiple`
    # da `Tela` não acha o campo pelo label; quem envia o valor é a caixa "Escolhido(S)".
    adicionar_ao_filteredselect(tela.pagina, 'id_procedimento_from', 'Outros')
    tela.preencher('Observação', 'textarea', 'Procedimento realizado em conjunto pelas especialidades.')
    tela.clicar_botao('Salvar').sucesso('Atendimento multidisciplinar registrado com sucesso.')
    _fechar_atendimento(tela, capturar, 'multidisciplinar')
