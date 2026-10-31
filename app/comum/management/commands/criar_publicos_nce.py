"""
Criando o banco de dados suap_dev baseado nos dados iniciais dos testes do Suap.
"""

from comum.models import Publico
from edu.models.cadastros_gerais import Modalidade
from djtools.management.commands import BaseCommandPlus

NCES_EDUCACAO = [
    'LIC.0831',  # Fundamentos da Educação I
    'LIC.0832',  # Fundamentos da Educação II
    'LIC.0945',  # Psicologia da Aprendizagem
    'LIC.0842',  # Didática
    'LIC.0051',  # Organização e Gestão da Educação Brasileira
    'LIC.0598',  # Organização e Gestão da Educação Brasileira
    'LIC.0017',  # Organização e Gestão da Educação Brasileira
    'LIC.0369',  # Educação Inclusiva
    'LIC.0021',  # Educação Inclusiva
    'LIC.0847',  # Mídias Educacionais
    'LIC.0881',  # Mídias Educacionais
    'LIC.0022',  # Mídias Educacionais
    'LIC.0853',  # Libras
    'LIC.0551',  # Libras
    'LIC.0023',  # Libras
    'LIC.0076',  # Libras
    'LIC.1003',  # Libras
    'LIC.0370',  # Libras I
    'LIC.1255',  # Fundamentos da Educação a Distância e Ambientação Virtual
    'LIC.1171',  # Didática Geral
    'LIC.1002',  # Didática Geral
    'LIC.0012',  # Fundamentos Históricos e Filosóficos da Educação
    'LIC.1170',  # Psicologia do Desenvolvimento da Aprendizagem
    'LIC.1174',  # Didática para a Educação Profissional e Tecnológica
    'LIC.0013',  # Fundamentos Sociopolíticos e Econômicos da Educação
    'LIC.0014',  # Fundamentos e Bases da Educação Profissional e Tecnológica
    'LIC.0988',  # Didática na educação profissional e tecnológica
    'LIC.0987',  # Fundamentos Históricos e Filosóficos da Educação e do Trabalho
    'LIC.0986',  # Mídias e Ferramentas Tecnológicas na Educação a Distância
    'LIC.0989',  # Metodologias e Estratégias de Ensino
    'LIC.1004',  # Organização e Gestão da Educação
    'LIC.1000',  # Processos educativos e de gestão: instituições escolares, comunitárias, assistenciais e do mundo do trabalho
    'LIC.1001',  # Educação de Jovens e Adultos
    'LIC.0992',  # Educação especial na perspectiva inclusiva
    'LIC.0991',  # Educação Profissional
    'LIC.0993',  # Organização Curricular e Currículo Integrado na EPT
    'LIC.0869',  # Concepções e Práticas da Educação de Jovens e Adultos
    'LIC.0924',  # Concepções e Práticas da Educação de Jovens e Adultos
    'LIC.0092',  # Teoria e Organização Curricular
    'LIC.1137',  # Teoria e Organização Curricular
    'LIC.0090',  # LIBRAS II
    'LIC.1317',  # LIBRAS II
    'LIC.0867',  # Educação para o Desenvolvimento Sustentável
    'LIC.0419',  # Formação de Professores e Trabalho Docente
    'LIC.0866',  # Fundamentos da Educação à Distância
    'LIC.0923',  # Concepções e Práticas de Avaliação da Aprendizagem
    'LIC.0925',  # Educação em Direitos Humanos
    'LIC.1142',  # Educação em Direitos Humanos
    'LIC.0926',  # Educação para a Diversidade
    'LIC.0927',  # Ética da Docência
    'LIC.1141',  # Ética da Docência
    'LIC.0931',  # Fundamentos da Educação Profissional Técnica e Tecnológica
    'LIC.0928',  # Filosofia da Educação
    'LIC.1140',  # Concepções e Práticas na Avaliação
    'LIC.1139',  # Concepções e Práticas na EJA
    'LIC.1316',  # Docência na Educação a Distância
    'LIC.0091',  # Fundamentos da Educação de Jovens e Adultos
    'LIC.0399',  # Metodologia do Ensino à Distância
]


def create_json_publico_nce_educacao(siglas, nome_nce):
    filtro_avancado = (
        f'Q(vinculos__professor__professordiario__diario__componente_curricular__componente__sigla__in={siglas}) '
        f'& Q(vinculos__professor__professordiario__diario__ano_letivo__ano__in=[2024,2025], '
        f'vinculos__professor__professordiario__diario__periodo_letivo__in=[1, 2])'
    )

    _publico, _ = Publico.objects.update_or_create(
        nome=f'{nome_nce}',
        defaults={
            'modelo_base': 'Servidor',
            'qs_filter': 'docentes_permanentes, sem_afastamento_hoje',
            'manager_base': 'objects',
            'filtro_avancado': filtro_avancado,
        },
    )
    # print(f'{nome_nce} - {publico.get_queryset().count()} docentes')


NCES_ENSINO_MEDIO = [
    'Matemática',
    'Física',
    'Química',
    'Biologia',
    'História',
    'Geografia',
    'Português',
    'Inglês',
    'Educação Física',
    'Arte',
    'Espanhol',
    'Filosofia',
    'Sociologia',
]


def create_json_publico_nce_nivel_medio(descricao_grupo_atuacao, modalidades, nome_nce):
    nucleos = ['Estruturante']
    area_atuacao = [descricao_grupo_atuacao]
    if descricao_grupo_atuacao == 'Espanhol':
        area_atuacao.append('Francês')
    elif descricao_grupo_atuacao == 'Português':
        area_atuacao = ['Língua Portuguesa e Literatura']

    filtro_avancado = (
        f'Q(vinculos__professor__professordiario__diario__turma__curso_campus__modalidade__in={modalidades}) '
        f'& Q(vinculos__professor__professordiario__diario__componente_curricular__nucleo__descricao__in={nucleos}) '
        f'& Q(vinculos__professor__professordiario__diario__componente_curricular__componente__grupo_atuacao__descricao__in={area_atuacao}) '
        f'& Q(vinculos__professor__professordiario__diario__ano_letivo__ano__in=[2024,2025], '
        f'vinculos__professor__professordiario__diario__periodo_letivo__in=[1, 2])'
    )
    nome_publico = f'{nome_nce} - {descricao_grupo_atuacao}'
    _publico, _ = Publico.objects.update_or_create(
        nome=nome_publico,
        defaults={
            'modelo_base': 'Servidor',
            'qs_filter': 'docentes_permanentes, sem_afastamento_hoje',
            'manager_base': 'objects',
            'filtro_avancado': filtro_avancado,
        },
    )
    # print(f'{nome_publico} - {publico.get_queryset().count()} docentes')


LICENCIATURAS = [
    'Licenciatura em Biologia',
    'Licenciatura em Educação do Campo, com área de aprofundamento em Matemática',  #'Licenciatura em Educação do Campo - Matemática',
    'Licenciatura em Educação do Campo, com área de aprofundamento em Ciências Humanas e Sociais',  #'Licenciatura em Educação do Campo - Ciências Humanas e Sociais',
    'Licenciatura em Física',
    'Licenciatura em Formação Pedagógica para a Educação Básica, Profissional e Tecnológica',  # Licenciatura em Formação Pedagógica para a Educação Básica, Profissional e Tecnológica
    'Licenciatura em Formação Pedagógica para Graduados não Licenciados (em Rede)',  #'Licenciatura em Formação Pedagógica para Graduados não Licenciados',
    'Licenciatura em Geografia',
    'Licenciatura em Informática',
    'Licenciatura em Espanhol',  # Licenciatura em Letras-Espanhol
    'Licenciatura em Letras Português/Espanhol',  #'Licenciatura em Letras Português/Espanhol',
    'Licenciatura em Matemática',
    'Licenciatura em Química',
]


def create_json_publico_nce_licenciatura(licenciatura, nome_nce):
    # Definição dos núcleos padrão
    nucleos = {'Eixo Didático-Pedagógico e Epistemológico', 'Eixo Específico'}

    # Adiciona "Específico" caso a licenciatura seja uma das listadas
    if licenciatura in {
        'Licenciatura em Educação do Campo, com área de aprofundamento em Matemática',
        'Licenciatura em Educação do Campo, com área de aprofundamento em Ciências Humanas e Sociais',
    }:
        nucleos.add('Específico')

    # Definição do filtro avançado
    filtro_avancado = f"Q(vinculos__professor__professordiario__diario__turma__curso_campus__descricao_historico='{licenciatura}') "

    if licenciatura != 'Licenciatura em Formação Pedagógica para Graduados não Licenciados (em Rede)':
        filtro_avancado += f'& Q(vinculos__professor__professordiario__diario__componente_curricular__nucleo__descricao__in={list(nucleos)}) '

    filtro_avancado += (
        '& Q(vinculos__professor__professordiario__diario__ano_letivo__ano__in=[2024,2025], '
        'vinculos__professor__professordiario__diario__periodo_letivo__in=[1, 2])'
    )

    # Definição do nome do público
    nome_publico = f'{nome_nce} - {licenciatura}'

    # Criando ou atualizando o registro no banco
    Publico.objects.update_or_create(
        nome=nome_publico,
        defaults={
            'modelo_base': 'Servidor',
            'qs_filter': 'docentes_permanentes, sem_afastamento_hoje',
            'manager_base': 'objects',
            'filtro_avancado': filtro_avancado,
        },
    )

    # print(f'{nome_publico} - {publico.get_queryset().count()} docentes')


NUCLEOS_TECNOLOGICOS_NUCLEO_ESPECIFICO_CIENTIFICO_E_TECNOLOGICO_UT_ESTRUTURANTE = [
    'Específico',
    'Científico e Tecnológico (Unidade Tecnológica)',
    'Estruturante',
]
CURSOS_TECNOLOGICOS_NUCLEO_ESPECIFICO_CIENTIFICO_E_TECNOLOGICO_UT_ESTRUTURANTE = [
    'Engenharia Civil',
]

NUCLEOS_FORMACAO_ESPECIFICA_PROFISSIONALIZANTE = ['Formação Específica', 'Profissionalizante']
CURSOS_FORMACAO_ESPECIFICA_PROFISSIONALIZANTE = [
    'Engenharia de Energia',
]

NUCLEOS_CIENTIFICO_TECNOLOGICO_UE_UP = ['Científico e Tecnológico (Unidade Específica)', 'Científico e Tecnológico (Unidade Profissionalizante)']
CURSOS_CIENTIFICO_TECNOLOGICO_UE_UP = [
    'Engenharia de Produção',
]

NUCLEOS_ESPECIFICO_PROFISSIONALIZANTE = ['Específico', 'Profissionalizante']
CURSOS_ESPECIFICO_PROFISSIONALIZANTE = [
    'Engenharia Sanitária e Ambiental',
]

NUCLEOS_TECNOLOGICOS_NUCLEO_ESPECIFICO_CIENTIFICO_E_TECNOLOGICO_UT = [
    'Específico',
    'Científico e Tecnológico (Unidade Tecnológica)',
]
CURSOS_TECNOLOGICOS_NUCLEO_ESPECIFICO_CIENTIFICO_E_TECNOLOGICO_UT = [
    'Tecnologia em Gestão Ambiental',
    'Tecnologia em Sistemas para Internet',
]
NUCLEOS_CIENTIFICO_E_TECNOLOGICO_UT = [
    'Científico e Tecnológico (Unidade Tecnológica)',
]
CURSOS_CIENTIFICO_E_TECNOLOGICO_UT = [
    'Tecnologia em Design de Moda',
    'Tecnologia em Gestão do Turismo',
    'Tecnologia em Gestão Pública',
    'Tecnologia em Marketing',
    'Tecnologia em Processos Químicos',
    'Tecnologia em Produção Cultural',
    'Tecnologia em Agroecologia',
    'Tecnologia em Agroindústria',
    'Tecnologia em Alimentos',
]

NUCLEOS_ESPECIFICOS = ['Específico', 'Científico e Tecnológico (Unidade Tecnológica)']
CURSOS_ESPECIFICOS = [
    'Tecnologia em Energias Renováveis',
]
NUCLEOS_TECNOLOGICOS_CIENTIFICO_TECNOLOGICO_UT = ['Tecnológico', 'Científico e Tecnológico (Unidade Tecnológica)']
CURSOS_TECNOLOGICOS_CIENTIFICO_TECNOLOGICO_UT = [
    'Tecnologia em Logística',
]

NUCLEOS_TECNOLOGICOS = [
    'Tecnológico',
]
CURSOS_TECNOLOGICOS = [
    'Técnico de Nível Médio em Administração',
    'Técnico de Nível Médio em Alimentos',
    'Técnico de Nível Médio em Agropecuária',
    'Técnico de Nível Médio em Apicultura',
    'Técnico de Nível Médio em Agroecologia',
    'Técnico de Nível Médio em Petróleo e Gás',
    'Técnico de Nível Médio em Comércio',
    'Técnico de Nível Médio em Controle Ambiental',
    'Técnico de Nível Médio em Meio Ambiente',
    'Técnico de Nível Médio em Multimídia',
    'Técnico de Nível Médio em Eletromecânica',
    'Técnico de Nível Médio em Mecatrônica',
    'Técnico de Nível Médio em Eletrônica',
    'Técnico de Nível Médio em Eletrotécnica',
    'Técnico de Nível Médio em Equipamentos Biomédicos',
    'Técnico de Nível Médio em Edificações',
    'Técnico de Nível Médio em Estradas',
    'Técnico de Nível Médio em Saneamento',
    'Técnico de Nível Médio em Eventos',
    'Técnico de Nível Médio em Guia de Turismo',
    'Técnico de Nível Médio em Geologia',
    'Técnico de Nível Médio em Mineração',
    'Técnico de Nível Médio em Informática',
    'Técnico de Nível Médio em Informática para Internet',
    'Tecnologia em Análise e Desenvolvimento de Sistemas',
    'Técnico de nível Médio em Instrumento Musical',
    'Técnico de Nível Médio em Lazer',
    'Tecnologia em Gestão Desportiva e de Lazer',
    'Técnico de Nível Médio em Logística',
    'Técnico de Nível Médio em Manutenção e Suporte em Informática',
    'Técnico de Nível Médio em Mecânica',
    'Técnico de Nível Médio em Refrigeração e Climatização',
    'Técnico de Nível Médio em Programação de Jogos Digitais',
    'Técnico de Nível Médio em Química',
    'Técnico de Nível Médio em Recursos Pesqueiros',
    'Técnico de Nível Médio em Redes de Computadores',
    'Tecnologia em Redes de Computadores',
    'Técnico de Nível Médio em Segurança do Trabalho',
    'Técnico de Nível Médio em Têxtil',
    'Técnico de Nível Médio em Vestuário',
    'Tecnologia em Comércio Exterior',
    'Técnico de Nível Médio em Design Gráfico',
    'Técnico de Nível Médio em Secretaria Escolar',
]


def create_json_publico_nce_tecnologico(curso, nucleos, nome_nce):
    filtro_avancado = (
        f"Q(vinculos__professor__professordiario__diario__turma__curso_campus__descricao_historico='{curso}') "
        f'& Q(vinculos__professor__professordiario__diario__componente_curricular__nucleo__descricao__in={nucleos}) '
        f'& Q(vinculos__professor__professordiario__diario__ano_letivo__ano__in=[2024,2025], '
        f'vinculos__professor__professordiario__diario__periodo_letivo__in=[1, 2])'
    )

    nome_publico = f'{nome_nce} - {curso}'
    _publico, _ = Publico.objects.update_or_create(
        nome=nome_publico,
        defaults={
            'modelo_base': 'Servidor',
            'qs_filter': 'docentes_permanentes, sem_afastamento_hoje',
            'manager_base': 'objects',
            'filtro_avancado': filtro_avancado,
        },
    )
    # print(f'{nome_publico} - {publico.get_queryset().count()} docentes')


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # Criar o publico do NCE Educação
        create_json_publico_nce_educacao(NCES_EDUCACAO, 'NCE de Educação')
        # Criar o publico do NCE Ensino Médio
        for nce in NCES_ENSINO_MEDIO:
            create_json_publico_nce_nivel_medio(
                nce, [Modalidade.INTEGRADO, Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA], 'NCE Ensino Médio'
            )

        # NCE de formação de docentes - Licenciaturas
        for licenciatura in LICENCIATURAS:
            create_json_publico_nce_licenciatura(
                licenciatura,
                'NCE de Formação de Docentes',
            )
        # NCE Tecnológicos Engenharia
        nome_nce = 'NCE Tecnológicos'
        for curso in CURSOS_TECNOLOGICOS_NUCLEO_ESPECIFICO_CIENTIFICO_E_TECNOLOGICO_UT_ESTRUTURANTE:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_TECNOLOGICOS_NUCLEO_ESPECIFICO_CIENTIFICO_E_TECNOLOGICO_UT_ESTRUTURANTE,
                nome_nce,
            )
        for curso in CURSOS_FORMACAO_ESPECIFICA_PROFISSIONALIZANTE:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_FORMACAO_ESPECIFICA_PROFISSIONALIZANTE,
                nome_nce,
            )
        for curso in CURSOS_CIENTIFICO_TECNOLOGICO_UE_UP:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_CIENTIFICO_TECNOLOGICO_UE_UP,
                nome_nce,
            )
        for curso in CURSOS_ESPECIFICO_PROFISSIONALIZANTE:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_ESPECIFICO_PROFISSIONALIZANTE,
                nome_nce,
            )
        for curso in CURSOS_TECNOLOGICOS_NUCLEO_ESPECIFICO_CIENTIFICO_E_TECNOLOGICO_UT:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_TECNOLOGICOS_NUCLEO_ESPECIFICO_CIENTIFICO_E_TECNOLOGICO_UT,
                nome_nce,
            )
        for curso in CURSOS_CIENTIFICO_E_TECNOLOGICO_UT:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_CIENTIFICO_E_TECNOLOGICO_UT,
                nome_nce,
            )
        for curso in CURSOS_ESPECIFICOS:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_ESPECIFICOS,
                nome_nce,
            )
        for curso in CURSOS_TECNOLOGICOS_CIENTIFICO_TECNOLOGICO_UT:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_TECNOLOGICOS_CIENTIFICO_TECNOLOGICO_UT,
                nome_nce,
            )
        for curso in CURSOS_TECNOLOGICOS:
            create_json_publico_nce_tecnologico(
                curso,
                NUCLEOS_TECNOLOGICOS,
                nome_nce,
            )
