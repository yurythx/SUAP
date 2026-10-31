from django.contrib.auth.models import Group
from django.http import HttpResponse

from comum.models import Ocupacao
from djtools import forms
from edu.models import (
    Aluno,
    HistoricoImportacao,
    ProjetoFinal,
    Requerimento,
)
from rh.models import Setor


class ConfiguracaoForm(forms.FormPlus):
    # 1. Identificação Institucional e Atos Regulatórios
    credenciamento = forms.CharFieldPlus(
        label='Ato de credenciamento',
        required=False,
        widget=forms.Textarea(),
        help_text='Registro de credenciamento da instituição de ensino superior, constando número, data, seção e página de publicação no DOU.',
    )
    recredenciamento = forms.CharFieldPlus(
        label='Ato de recredenciamento',
        required=False,
        widget=forms.Textarea(),
        help_text='Registro de recredenciamento da instituição de ensino superior, constando número, data, seção e página de publicação no DOU.',
    )
    codigo_mec = forms.CharField(
        label='Código MEC',
        required=False,
        help_text='Código de identificação da instituição junto ao Ministério da Educação (e-MEC).',
    )
    setor_proreitor_ensino = forms.ModelChoiceFieldPlus(
        Setor.objects,
        label='Setor da Pró-Reitoria de Ensino',
        required=False,
        help_text='Setor institucional correspondente à Pró-Reitoria de Ensino (PROEN).',
    )

    # 2. Calendário Acadêmico e Parâmetros Gerais
    ano_letivo_atual = forms.IntegerField(
        label='Ano letivo atual',
        required=False,
        help_text='Ano letivo corrente utilizado como padrão para consultas e operações acadêmicas.',
    )
    periodo_letivo_atual = forms.ChoiceField(
        label='Período letivo atual',
        choices=Aluno.PERIODO_LETIVO_CHOICES,
        required=False,
        help_text='Período letivo corrente padrão para as operações acadêmicas (ex.: 1 ou 2).',
    )
    tipo_ata_projeto_final = forms.ChoiceField(
        label='Tipo de ata de projeto final',
        choices=ProjetoFinal.TIPO_ATA_CHOICES,
        help_text='Modelo padrão de ata gerado nas bancas de avaliação de projeto final ou TCC.',
    )
    inicio_confirmacao_frequencia = forms.DateFieldPlus(
        label='Início da confirmação de frequência',
        required=False,
        help_text='Data a partir da qual os professores deverão confirmar o registro de frequência das aulas ministradas.',
    )
    sigla_setor_seacs = forms.CharField(
        label='Sigla do setor das secretarias acadêmicas',
        initial='SEAC',
        help_text='Sigla padrão utilizada para identificar os setores de secretaria acadêmica nos campi (ex.: SEAC).',
    )
    caminho_arquivo_cracha = forms.CharField(
        label='Caminho do modelo de crachá',
        required=False,
        initial='edu/static/edu/img/cracha-aluno.png',
        help_text='Caminho relativo do arquivo de imagem do modelo de crachá de estudante (ex.: edu/static/edu/img/cracha-aluno.png).',
    )

    # 3. Regras Acadêmicas e Permissões
    exige_naturalidade_estrangeiro = forms.BooleanField(
        label='Exigir naturalidade de estudante estrangeiro',
        required=False,
        help_text='Marque esta opção para tornar obrigatório o preenchimento da naturalidade no cadastro de estudantes estrangeiros.',
    )
    nota_atitudinal = forms.BooleanField(
        label='Habilitar cálculo por nota atitudinal',
        required=False,
        help_text='Marque esta opção para aplicar exclusivamente a forma de cálculo "Média Atitudinal" nos cursos de nível médio.',
    )
    mostrar_diarios_reserva_sala = forms.BooleanField(
        label='Exibir diários no agendamento de salas',
        required=False,
        help_text='Marque esta opção para exibir, no agendamento de reserva de sala, os horários de aula dos diários vinculados à sala.',
    )
    reservar_sala_no_diario = forms.BooleanField(
        label='Permitir reserva de salas pelo diário',
        required=False,
        help_text='Marque esta opção para permitir a reserva de salas diretamente pelo diário, conforme os horários e locais de aula configurados.',
    )
    dispensa_enape_em_lote = forms.BooleanField(
        label='Permitir dispensa do ENADE em lote',
        required=False,
        help_text='Marque esta opção para habilitar a funcionalidade de dispensa em lote do ENADE para estudantes.',
    )
    editar_matriz_alunos_concluidos = forms.BooleanField(
        label='Permitir edição de matrizes curriculares com alunos já concluídos',
        required=False,
        help_text='Marque esta opção apenas temporariamente para viabilizar correções pontuais em matrizes que possuam estudantes já concluintes ou formados.',
    )
    pode_cadastrar_procedimento_matricula = forms.BooleanField(
        label='Permitir inclusão de procedimentos de matrícula para estudantes',
        required=False,
        help_text='Marque esta opção para habilitar o cadastro de registros de procedimentos de matrícula para os estudantes.',
    )
    permite_gerar_turma_polo = forms.BooleanField(
        label='Permitir geração de turmas por polo',
        required=False,
        help_text='Marque esta opção para habilitar a geração de turmas vinculadas a polos de educação a distância (EaD).',
    )
    permite_insclusao_registros_historico = forms.BooleanField(
        label='Permitir inclusão de registros no histórico escolar do aluno',
        required=False,
        help_text='Marque esta opção para permitir a inserção de novos registros na aba de histórico dos estudantes.',
    )
    permite_edicao_registros_historico = forms.BooleanField(
        label='Permitir edição de registros no histórico escolar do aluno',
        required=False,
        help_text='Marque esta opção para permitir a alteração de registros existentes na aba de histórico dos estudantes.',
    )
    permite_editar_parcialmente_alunos_migrados = forms.BooleanField(
        label='Permitir edição parcial de alunos migrados',
        required=False,
        help_text='Marque esta opção para permitir a edição de dados de alunos migrados sem exigir o preenchimento de todos os campos obrigatórios do formulário.',
    )
    permite_medio_adicionar_atividade_complementar = forms.BooleanField(
        label='Permitir registro de atividades complementares no ensino médio',
        required=False,
        help_text='Marque esta opção para permitir o registro de atividades complementares por estudantes de ensino médio. Se desmarcada, a funcionalidade restringe-se ao nível superior.',
    )
    permite_requerer_quebra_requisito_aumento_ch = forms.BooleanField(
        label='Permitir solicitação de matrícula com quebra de pré-requisito ou ampliação de carga horária',
        required=False,
        help_text='Marque esta opção para disponibilizar, na renovação de matrícula, a solicitação de quebra de pré-requisito ou ampliação de carga horária pelo estudante.',
    )
    tipos_requerimentos_abertos_pelos_alunos = forms.CharField(
        label='Tipos de requerimento disponíveis para abertura pelos estudantes',
        required=False,
        initial='8, 17, 20, 21',
        help_text='Informe os identificadores dos tipos de requerimento separados por vírgula (ex.: 8, 17, 20, 21). Opções disponíveis:<br>{}'.format(
            ', '.join([f'{pk} - {descricao}' for pk, descricao in Requerimento.TIPO_CHOICES])
        ),
    )
    relatorio_inconsistencia_descentralizado = forms.BooleanField(
        label='Permitir acesso descentralizado ao relatório de inconsistências',
        required=False,
        help_text='Marque esta opção para permitir que as secretarias acadêmicas dos campi acessem o relatório de inconsistências e executem correções.',
    )
    habilita_atividade_curricular_extensao_extra = forms.BooleanField(
        label='Permitir cadastro de atividades curriculares de extensão complementares',
        required=False,
        help_text='Marque esta opção para permitir a criação e a vinculação de atividades curriculares de extensão extras ao estudante.',
    )

    # 4. Regulação de Cursos e Prazos
    prazo_suspensao_curso = forms.IntegerField(
        label='Prazo máximo de suspensão de curso (dias)',
        required=False,
        help_text='Informe a quantidade máxima de dias que um curso pode permanecer suspenso após a publicação do ato de suspensão.',
    )
    notificacao_suspensao_curso = forms.IntegerField(
        label='Prazo para notificação de curso suspenso (dias)',
        required=False,
        help_text='Informe o prazo (em dias) para iniciar a notificação de curso suspenso que não possua ato de extinção ou processo de extinção instaurado.',
    )

    # 5. Corpo Docente e Professores Externos
    professor_externo_ocupacao_padrao = forms.ModelChoiceFieldPlus(
        queryset=Ocupacao.objects,
        label='Ocupação padrão de professor externo',
        required=False,
        help_text='Selecione a ocupação padrão que será associada ao cadastro de professores externos.',
    )
    professor_externo_dias_vencimento_contrato = forms.IntegerField(
        label='Prazo de vigência de contrato de professor externo (dias)',
        required=False,
        initial=720,
        help_text='Informe o prazo padrão (em dias) para a vigência do contrato de professor externo a partir da data de início.',
    )
    prefixo_pagina_docentes_portal = forms.CharField(
        label='Prefixo da página de docentes no portal institucional',
        required=False,
        help_text='Informe o prefixo utilizado na composição da URL pública dos docentes no portal institucional (ex.: "docente/").',
    )

    # 6. Emissão e Assinatura de Diplomas
    solicita_assinatura_diploma_cra = forms.BooleanField(
        label='Incluir Coordenador de Registros Acadêmicos na assinatura de diplomas',
        required=False,
        help_text='Marque esta opção para incluir o Coordenador de Registros Acadêmicos (CRA) nas solicitações de assinatura de diploma com certificado ICP-Edu.',
    )
    solicita_assinatura_diploma_da = forms.BooleanField(
        label='Incluir Diretor Acadêmico na assinatura de diplomas',
        required=False,
        help_text='Marque esta opção para incluir o Diretor Acadêmico nas solicitações de assinatura de diploma dos cursos de Formação Inicial e Continuada (FIC).',
    )

    # 7. Relações Internacionais e Pré-matrícula de Estrangeiros
    url_manual_prematricula_internacional = forms.CharField(
        label='URL do manual de pré-matrícula internacional [PT]',
        required=False,
        help_text='Informe a URL da página em português com as instruções de pré-matrícula de estudantes internacionais no SUAP.',
    )
    url_manual_prematricula_internacional_en = forms.CharField(
        label='URL do manual de pré-matrícula internacional [EN]',
        required=False,
        help_text='Informe a URL da página em inglês com as instruções de pré-matrícula de estudantes internacionais no SUAP.',
    )
    url_manual_prematricula_internacional_es = forms.CharField(
        label='URL do manual de pré-matrícula internacional [ES]',
        required=False,
        help_text='Informe a URL da página em espanhol com as instruções de pré-matrícula de estudantes internacionais no SUAP.',
    )

    # 8. Integrações com Sistemas Externos
    # 8.1 RAP (Registro de Aprendizagem Profissional)
    rap_client_id = forms.CharField(
        label='RAP - Identificador do cliente (Client ID)',
        required=False,
        help_text='Identificador de cliente fornecido para autenticação OAuth2 junto à API do RAP.',
    )
    rap_api_url = forms.CharField(
        label='RAP - URL da API',
        required=False,
        help_text='Endereço base do serviço web da API do RAP (ex.: https://api.rap.mec.gov.br).',
    )
    rap_api_user = forms.CharField(
        label='RAP - Usuário da API',
        required=False,
        help_text='Nome de usuário para autenticação na API do RAP.',
    )
    rap_api_password = forms.CharField(
        label='RAP - Senha da API',
        required=False,
        help_text='Senha de acesso vinculada ao usuário da API do RAP.',
    )

    # 8.2 Siabi (Sistema de Bibliotecas)
    siabi_nome_banco = forms.CharField(
        label='Siabi - Nome da base de dados',
        required=False,
        initial='SIABI_BIN',
        help_text='Nome da base de dados do Siabi para consultas de acervo e empréstimos.',
    )
    siabi_usuario_banco = forms.CharField(
        label='Siabi - Usuário da base de dados',
        required=False,
        help_text='Usuário com permissão de leitura na base de dados do Siabi.',
    )
    siabi_senha_banco = forms.CharField(
        label='Siabi - Senha da base de dados',
        required=False,
        help_text='Senha de acesso ao banco de dados do Siabi.',
    )
    siabi_endereco_banco = forms.CharField(
        label='Siabi - Endereço (host) da base de dados',
        required=False,
        help_text='Endereço de rede (IP ou hostname) do servidor do Siabi.',
    )

    # 8.3 Q-Acadêmico (Migração de Dados Legados)
    academico_nome_sistema = forms.CharField(
        label='Q-Acadêmico - Nome do sistema de origem',
        required=False,
        initial='Q-Acadêmico',
        help_text='Nome identificador do sistema acadêmico legado de onde os registros foram migrados (padrão: "Q-Acadêmico").',
    )
    academico_nome_banco_padrao = forms.CharField(
        label='Q-Acadêmico - Nome da base de dados padrão',
        required=False,
        initial='SISTEMA_ACADEMICO',
        help_text='Nome da base de dados relacional do Q-Acadêmico utilizada na migração.',
    )
    academico_nome_banco_binarios = forms.CharField(
        label='Q-Acadêmico - Nome da base de dados de fotos e anexos',
        required=False,
        initial='SISTEMA_ACADEMICO_BINARIOS',
        help_text='Nome da base de dados de arquivos binários (fotos de estudantes e documentos escaneados).',
    )
    academico_usuario_banco = forms.CharField(
        label='Q-Acadêmico - Usuário da base de dados',
        required=False,
        help_text='Usuário com permissão de leitura na base do Q-Acadêmico.',
    )
    academico_senha_banco = forms.CharField(
        label='Q-Acadêmico - Senha da base de dados',
        required=False,
        help_text='Senha de acesso ao banco de dados do Q-Acadêmico.',
    )
    academico_endereco_banco = forms.CharField(
        label='Q-Acadêmico - Endereço (host) da base de dados',
        required=False,
        help_text='Endereço de rede (IP ou hostname) do servidor de banco do Q-Acadêmico.',
    )

    # 8.4 Pé-de-Meia (Programa do MEC)
    usuario_pedemeia = forms.CharField(
        label='Pé-de-Meia - Usuário da API',
        required=False,
        help_text='Identificador ou usuário de autenticação junto à API do programa Pé-de-Meia (MEC).',
    )
    senha_pedemeia = forms.CharField(
        label='Pé-de-Meia - Senha da API',
        required=False,
        help_text='Senha de autenticação junto à API do programa Pé-de-Meia.',
    )
    url_pedemeia = forms.CharField(
        label='Pé-de-Meia - URL da API',
        required=False,
        help_text='Endereço base do endpoint do programa Pé-de-Meia para envio de dados acadêmicos.',
    )

    utilizar_api_icpedu = forms.BooleanField(
        label='Utilizar API ICP EDU',
        required=False,
        help_text='Marque essa opção caso deseje que as assinaturas ICP EDU seja realizada via API ao invés da utilização de arquivos .PFX.',
    )


class RedirectForm(forms.FormPlus):
    def get_url(self):
        pass

    def processar(self):
        return HttpResponse(f'<script>parent.close_fancybox_noreload();parent.document.location.href="{self.get_url()}"</script>')


class HistoricoImportacaoForm(forms.ModelFormPlus):
    id = forms.CharField(label='Identificador', widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = HistoricoImportacao
        fields = ['id']


def grupos():
    DIRETOR_GERAL = Group.objects.get_or_create(name='Diretor Geral')[0]
    DIRETOR = Group.objects.get_or_create(name='Diretor Acadêmico')[0]
    COORDENADOR = Group.objects.get_or_create(name='Coordenador de Curso')[0]
    SECRETARIO = Group.objects.get_or_create(name='Secretário Acadêmico')[0]
    PEDAGOGO = Group.objects.get_or_create(name='Pedagogo')[0]
    ESTAGIARIO = Group.objects.get_or_create(name='Estagiário')[0]
    AGENDADOR_AULA_CAMPO = Group.objects.get_or_create(name='Agendador de Aula de Campo EDU')[0]
    TUTOR_POLO = Group.objects.get_or_create(name='Tutor de Polo EAD')[0]
    COORDENADOR_POLO = Group.objects.get_or_create(name='Coordenador de Polo EAD')[0]
    COORDENADOR_POLO_SISTEMICO = Group.objects.get_or_create(name='Coordenador de Polo EAD Sistêmico')[0]
    COORDENADOR_REGISTROS_ACADEMICOS = Group.objects.get_or_create(name='Coordenador de Registros Acadêmicos')[0]
    COORDENADOR_ESTAGIO_DOCENTE = Group.objects.get_or_create(name='Coordenador de Estágio Docente')[0]
    COORDENADOR_MODALIDADE = Group.objects.get_or_create(name='Coordenador de Modalidade Acadêmica')[0]
    COORDENADOR_DESPORTO = Group.objects.get_or_create(name='Coordenador de Desporto')[0]
    ORGANIZADOR_FORMATURA = Group.objects.get_or_create(name='Organizador de Formatura')[0]
    BIBLIOTECARIO = Group.objects.get_or_create(name='Bibliotecário')[0]
    INTERESSADO_ETEP = Group.objects.get_or_create(name='Interessado ETEP')[0]
    return locals()
