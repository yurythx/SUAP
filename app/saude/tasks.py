from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import QuerySet

from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse
from saude.models import HipoteseDiagnostica, IntervencaoEnfermagem, PercepcaoSaudeBucal, ProcessoSaudeDoenca

if TYPE_CHECKING:
    from django.http import HttpResponse

    from djtools.models import Task
    from saude.models import Atendimento, HabitosDeVida


@task('Exportar Antropometria para XLS')
def graficos_antropometria_to_xls(registros, task=None):
    colunas = []
    rows = []
    colunas.append('#')
    colunas.append('Nome')
    colunas.append('Matrícula')
    colunas.append('Curso')
    colunas.append('Turma')
    colunas.append('IMC')
    rows.append(colunas)

    contador = 1
    for registro in task.iterate(registros):
        row = [contador]
        aluno = registro.atendimento.aluno
        row.append(format_(aluno.pessoa_fisica.nome))

        row.append(format_(aluno.matricula))

        row.append(format_(aluno.curso_campus))
        turma = '-'
        if aluno.get_ultima_matricula_periodo():
            turma = aluno.get_ultima_matricula_periodo().get_codigo_turma()
        row.append(format_(turma))
        estatura_imc = Decimal((registro.estatura / 100.0) * (registro.estatura / 100.0))
        if estatura_imc:
            imc = Decimal(registro.peso) / estatura_imc
        else:
            imc = Decimal('0.0')
        row.append(format_(imc))
        rows.append(row)
        contador += 1

    return XlsResponse(rows, processo=task)


@task('Exportar Dados de Acuidade Visual para XLS')
def exportar_graficos_acuidade_visual_to_xls(registros: QuerySet, task: Task | None = None) -> HttpResponse | None:
    colunas = []
    rows = []
    colunas.append('#')
    colunas.append('Nome')
    colunas.append('Matrícula')
    colunas.append('Curso')
    colunas.append('Turma')
    colunas.append('Olho Esquerdo')
    colunas.append('Olho Direito')
    colunas.append('Com Correção')
    colunas.append('O teste será realizado com o estudante utilizando lentes corretivas')
    colunas.append('Já faz uso de lentes de correção')
    colunas.append('Detalhes do uso de lente')
    rows.append(colunas)

    contador = 1
    for registro in task.iterate(registros):
        row = [contador]
        aluno = registro.atendimento.aluno
        if aluno:
            row.append(format_(aluno.pessoa_fisica.nome))

            row.append(format_(aluno.matricula))

            row.append(format_(aluno.curso_campus))
            turma = '-'
            if aluno.get_ultima_matricula_periodo():
                turma = aluno.get_ultima_matricula_periodo().get_codigo_turma()
            row.append(format_(turma))

            row.append(registro.olho_esquerdo)
            row.append(registro.olho_direito)
            # Ficha nova (com `teste_com_lente`) não pergunta mais "Com correção": o default False não pode virar "Não".
            if registro.teste_com_lente is not None:
                correcao = None
            else:
                correcao = 'Sim' if registro.com_correcao else 'Não'
            row.append(correcao)
            row.append(registro.teste_com_lente)
            row.append(registro.usa_lente)
            row.append(registro.usa_lente_detalhes)
            rows.append(row)
            contador += 1

    return XlsResponse(rows, processo=task)


def _identificacao_do_paciente(atendimento: Atendimento) -> list | None:
    """Nome, matrícula, curso e turma de quem foi atendido; ``None`` quando o atendimento não tem paciente."""
    pessoa = atendimento.aluno or atendimento.servidor or atendimento.prestador_servico or atendimento.pessoa_externa
    if not pessoa:
        return None
    curso = turma = '-'
    if atendimento.aluno:
        curso = pessoa.curso_campus
        if pessoa.get_ultima_matricula_periodo():
            turma = pessoa.get_ultima_matricula_periodo().get_codigo_turma()
    return [format_(pessoa.pessoa_fisica.nome), format_(pessoa.matricula), format_(curso), format_(turma)]


def _respostas_saude_doenca(registro: ProcessoSaudeDoenca) -> list:
    """Respostas da ficha; sem alergia alimentar na ficha antiga, vale a da Nutrição e Alimentação do atendimento (Demanda 2301)."""
    alergia_alimentos, que_alimentos = registro.alergia_alimentos, registro.que_alimentos
    if not alergia_alimentos and (da_nutricao := registro.get_alergias_alimentos_nutricao()):
        alergia_alimentos, que_alimentos = True, da_nutricao
    return [
        registro.fez_cirurgia,
        registro.que_cirurgia,
        registro.tempo_cirurgia,
        registro.hemorragia,
        registro.tempo_hemorragia,
        alergia_alimentos,
        que_alimentos,
        registro.doencas_previas,
        registro.que_doencas_previas,
        registro.alergia_medicamentos,
        registro.que_medicamentos,
        registro.usa_medicamentos,
        registro.usa_que_medicamentos,
        registro.tem_plano_saude,
        registro.tem_plano_odontologico,
        registro.transtorno_psiquiatrico,
        registro.qual_transtorno_psiquiatrico,
        registro.psiquiatra,
        registro.duracao_psiquiatria,
        registro.tempo_psiquiatria,
        registro.lesoes_ortopedicas,
        registro.quais_lesoes_ortopedicas,
        ''.join(f'{doenca.nome}, ' for doenca in registro.doencas_cronicas.all()),
        registro.gestante,
        registro.problema_auditivo,
        registro.qual_problema,
    ]


@task('Exportar Dados de Saúde e Doenças para XLS')
def graficos_saude_doenca_to_xls(registros, task=None):
    ids_alunos = []
    ids_registros = []
    for registro in registros:
        if registro.atendimento.prontuario.vinculo_id not in ids_alunos:
            ids_registros.append(registro.id)
            ids_alunos.append(registro.atendimento.prontuario.vinculo_id)

    registros = registros.filter(id__in=ids_registros)
    colunas = []
    rows = []
    colunas.append('#')
    colunas.append('Nome')
    colunas.append('Matrícula')
    colunas.append('Curso')
    colunas.append('Turma')
    colunas.append('Já fez alguma cirurgia')
    colunas.append('Que cirurgia')
    colunas.append('Quanto tempo da cirurgia')
    colunas.append('Histórico de hemorragia')
    colunas.append('Há quanto tempo apresentou hemorragia')
    colunas.append('Alergia a alimentos')
    colunas.append('Quais alimentos')
    colunas.append('Doenças Prévias')
    colunas.append('Quais Doenças Prévias')
    colunas.append('Alergia a medicamentos')
    colunas.append('Quais medicamentos')
    colunas.append('Faz uso de medicamentos rotineiramente')
    colunas.append('Usa quais medicamentos')
    colunas.append('Tem Plano de Saúde')
    colunas.append('Tem Plano Odontológico')
    colunas.append('Já teve transtorno psiquiátrico?')
    colunas.append('Qual transtorno psiquiátrico?')
    colunas.append('Já passou por psiquiatra?')
    colunas.append('Tempo na psiquiatria')
    colunas.append('Há quanto tempo esteve no psiquiatra')
    colunas.append('Teve lesões ortopédicas')
    colunas.append('Quais lesões ortopédicas')
    colunas.append('Sofre de alguma doença crônica')
    colunas.append('Gestante')
    colunas.append('Problemas Auditivos')
    colunas.append('Qual problema auditivo')
    rows.append(colunas)
    contador = 1
    for registro in task.iterate(registros):
        identificacao = _identificacao_do_paciente(registro.atendimento)
        if identificacao:
            rows.append([contador, *identificacao, *_respostas_saude_doenca(registro)])
            contador += 1

    return XlsResponse(rows, processo=task)


def _respostas_habitos_de_vida(registro: HabitosDeVida) -> list:
    """Respostas da ficha de Hábitos de Vida: as colunas antigas e, no fim, as das perguntas da Demanda 2301."""
    return [
        registro.atividade_fisica,
        registro.qual_atividade,
        registro.frequencia_semanal,
        registro.duracao_atividade,
        registro.fuma,
        registro.frequencia_fumo,
        registro.usa_drogas,
        ''.join(f'{droga.nome}, ' for droga in registro.que_drogas.all()),
        registro.outras_drogas,
        registro.bebe,
        registro.frequencia_bebida,
        registro.dificuldade_dormir,
        registro.horas_sono,
        registro.refeicoes_por_dia,
        registro.vida_sexual_ativa,
        registro.metodo_contraceptivo,
        ''.join(f'{metodo.nome}, ' for metodo in registro.qual_metodo_contraceptivo.all()),
        registro.uso_internet,
        registro.tempo_uso_internet,
        registro.objetivo_uso_internet,
        registro.get_frequencia_uso_fumo_display(),
        registro.idade_fumo,
        registro.get_frequencia_uso_bebida_display(),
        registro.idade_bebida,
        registro.get_frequencia_uso_droga_display(),
        registro.idade_drogas,
        registro.get_refeicoes_por_dia(),
    ]


@task('Exportar Dados de Hábitos de Vida para XLS')
def graficos_habitos_vida_to_xls(registros, task=None):
    ids_alunos = []
    ids_registros = []
    for registro in registros:
        if registro.atendimento.prontuario.vinculo_id not in ids_alunos:
            ids_registros.append(registro.id)
            ids_alunos.append(registro.atendimento.prontuario.vinculo_id)

    registros = registros.filter(id__in=ids_registros)
    colunas = []
    rows = []
    colunas.append('#')
    colunas.append('Nome')
    colunas.append('Matrícula')
    colunas.append('Curso')
    colunas.append('Turma')
    colunas.append('Pratica atividade física')
    colunas.append('Qual atividade')
    colunas.append('Qual a frequência semanal')
    colunas.append('Duração da atividade física')
    colunas.append('Fuma')
    colunas.append('Número de cigarros por dia')
    colunas.append('Faz uso ou já usou drogas ilícitas')
    colunas.append('Quais drogas')
    colunas.append('Outras drogas')
    colunas.append('Ingere bebidas alcoólicas')
    colunas.append('Frequência mínima de ingestão de bebidas alcoólicas')
    colunas.append('Tem dificuldade para dormir')
    colunas.append('Horas de sono diárias')
    colunas.append('Quantas refeições faz por dia')
    colunas.append('Tem vida sexual ativa')
    colunas.append('Faz uso de algum método contraceptivo')
    colunas.append('Qual método contraceptivo')
    colunas.append('Faz uso da internet?')
    colunas.append('Qual o tempo de uso')
    colunas.append('Objetivo do uso')
    # Perguntas da Demanda 2301 (fichas novas), depois das colunas das fichas antigas.
    colunas.append('Fuma - frequência de uso')
    colunas.append('Fuma - idade em que experimentou')
    colunas.append('Bebidas alcoólicas - frequência de uso')
    colunas.append('Bebidas alcoólicas - idade em que experimentou')
    colunas.append('Drogas - frequência de uso')
    colunas.append('Drogas - idade em que experimentou')
    colunas.append('Quantas refeições faz por dia (Nutrição e Alimentação)')
    rows.append(colunas)
    contador = 1
    for registro in task.iterate(registros):
        identificacao = _identificacao_do_paciente(registro.atendimento)
        if identificacao:
            rows.append([contador, *identificacao, *_respostas_habitos_de_vida(registro)])
            contador += 1

    return XlsResponse(rows, processo=task)


@task('Exportar Dados de Desenvolvimento Pessoal para XLS')
def graficos_desenvolvimento_pessoal_to_xls(registros, task=None):
    colunas = []
    rows = []
    colunas.append('#')
    colunas.append('Nome')
    colunas.append('Matrícula')
    colunas.append('Curso')
    colunas.append('Turma')
    colunas.append('Tem Problema de Apredizado')
    colunas.append('Qual o Problema')
    colunas.append('Origem do Problema')
    rows.append(colunas)
    contador = 1
    for registro in task.iterate(registros):
        row = [contador]
        curso = '-'
        turma = '-'
        pessoa = registro.atendimento.aluno
        if not pessoa:
            pessoa = registro.atendimento.servidor
        if not pessoa:
            pessoa = registro.atendimento.prestador_servico
        if not pessoa:
            pessoa = registro.atendimento.pessoa_externa
        if pessoa:
            if registro.atendimento.aluno:
                curso = pessoa.curso_campus
                if pessoa.get_ultima_matricula_periodo():
                    turma = pessoa.get_ultima_matricula_periodo().get_codigo_turma()
            row.append(format_(pessoa.pessoa_fisica.nome))
            row.append(format_(pessoa.matricula))
            row.append(format_(curso))
            row.append(format_(turma))
            tem_problema = 'Não'
            qual_problema = '-'
            origem_problema = '-'
            if registro.problema_aprendizado:
                tem_problema = 'Sim'
                qual_problema = registro.qual_problema_aprendizado
                origem_problema = registro.origem_problema
            row.append(tem_problema)
            row.append(qual_problema)
            row.append(origem_problema)
            rows.append(row)
            contador += 1

    return XlsResponse(rows, processo=task)


@task('Exportar Dados de Exames Fisicos para XLS')
def graficos_exame_fisico_to_xls(registros, task=None):
    colunas = []
    rows = []
    colunas.append('#')
    colunas.append('Nome')
    colunas.append('Matrícula')
    colunas.append('Curso')
    colunas.append('Turma')
    colunas.append('Ectoscopia alterada')
    colunas.append('Alteração na ectoscopia')
    colunas.append('Aparelho cardiovascular alterado')
    colunas.append('Alteração no aparelho cardiovascular')
    colunas.append('Aparelho respiratório alterado')
    colunas.append('Alteração no aparelho respiratório')
    colunas.append('Abdome alterado')

    colunas.append('Alteração no abdome')
    colunas.append('Membros inferiores alterados')
    colunas.append('Alteração nos membros inferiores')
    colunas.append('Membros superiores alterados')
    colunas.append('Alteração nos membros superiores')
    colunas.append('Outros órgãos/sistemas alterados')
    colunas.append('Descrição das outras alterações')
    rows.append(colunas)

    contador = 1
    for registro in task.iterate(registros):
        row = [contador]
        curso = '-'
        turma = '-'
        pessoa = registro.atendimento.aluno
        if not pessoa:
            pessoa = registro.atendimento.servidor
        if not pessoa:
            pessoa = registro.atendimento.prestador_servico
        if not pessoa:
            pessoa = registro.atendimento.pessoa_externa
        if pessoa:
            if registro.atendimento.aluno:
                curso = pessoa.curso_campus
                if pessoa.get_ultima_matricula_periodo():
                    turma = pessoa.get_ultima_matricula_periodo().get_codigo_turma()
            row.append(format_(pessoa.pessoa_fisica.nome))
            row.append(format_(pessoa.matricula))
            row.append(format_(curso))
            row.append(format_(turma))
            row.append(registro.ectoscopia_alterada)
            row.append(registro.alteracao_ectoscopia)
            row.append(registro.acv_alterado)
            row.append(registro.alteracao_acv)
            row.append(registro.ar_alterado)
            row.append(registro.alteracao_ar)
            row.append(registro.abdome_alterado)
            row.append(registro.alteracao_abdome)
            row.append(registro.mmi_alterados)
            row.append(registro.alteracao_mmi)
            row.append(registro.mms_alterados)
            row.append(registro.alteracao_mms)
            row.append(registro.outras_alteracoes)
            row.append(registro.outras_alteracoes_descricao)

            rows.append(row)
            contador += 1

    return XlsResponse(rows, processo=task)


@task('Exportando Dados de Percepção de Saúde Buscal para XLS')
def graficos_percepcao_saude_bucal_to_xls(registros: QuerySet, task: Task | None = None) -> HttpResponse | None:
    colunas = []
    rows = []
    colunas.append('#')
    colunas.append('Nome')
    colunas.append('Matrícula')
    colunas.append('Curso')
    colunas.append('Turma')
    colunas.append('Quantas vezes usou fio dental na última semana?')
    colunas.append('Na última semana quantos dias consumiu doces, balas, bolos ou refrigerantes?')
    colunas.append('Usa prótese?')
    colunas.append('Usa aparelho ortodôntico?')
    colunas.append('Já foi a um dentista anteriormente')
    colunas.append('Quanto tempo faz que foi a última vez ao dentista')
    colunas.append(
        'Nos últimos 6 meses teve alguma dificuldade relacionada à boca, dente, prótese ou aparelho ortodôntico que lhe causou alguma dificuldade'
    )
    colunas.append('Grau de dificuldade em sorrir')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Grau de dificuldade em falar')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Grau de dificuldade em comer')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Grau de dificuldade em relacionar-se socialmente')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Grau de dificuldade em manter o humor habitual')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Grau de dificuldade em estudar')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Grau de dificuldade em trabalhar')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Grau de dificuldade em higienizar a boca')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Grau de dificuldade em dormir')
    colunas.append('Qual motivo você atribui como responsável?')
    colunas.append('Você usa fio dental?')
    colunas.append('Em quantos dias você usou o fio dental nos últimos 7 dias?')
    colunas.append(PercepcaoSaudeBucal._meta.get_field('qtd_por_dia_consome_acucar').verbose_name)
    colunas.append('Motivo da dificuldade em estudar ou trabalhar')
    colunas.append(PercepcaoSaudeBucal._meta.get_field('frequencia_escovacao').verbose_name)
    rows.append(colunas)

    contador = 1
    for registro in task.iterate(registros):
        row = [contador]
        curso = '-'
        turma = '-'
        pessoa = registro.atendimento.aluno
        if not pessoa:
            pessoa = registro.atendimento.servidor
        if not pessoa:
            pessoa = registro.atendimento.prestador_servico
        if not pessoa:
            pessoa = registro.atendimento.pessoa_externa
        if pessoa:
            if registro.atendimento.aluno:
                curso = pessoa.curso_campus
                if pessoa.get_ultima_matricula_periodo():
                    turma = pessoa.get_ultima_matricula_periodo().get_codigo_turma()
            row.append(format_(pessoa.pessoa_fisica.nome))
            row.append(format_(pessoa.matricula))
            row.append(format_(curso))
            row.append(format_(turma))
            row.append(registro.qtd_vezes_fio_dental_ultima_semana)
            row.append(registro.qtd_dias_consumiu_doce_ultima_semana)
            row.append(registro.usa_protese)
            row.append(registro.usa_aparelho_ortodontico)
            row.append(registro.foi_dentista_anteriormente)
            row.append(registro.tempo_ultima_vez_dentista)
            row.append(registro.dificuldades)
            row.append(registro.grau_dificuldade_sorrir)
            row.append(registro.motivo_dificuldade_sorrir)
            row.append(registro.grau_dificuldade_falar)
            row.append(registro.motivo_dificuldade_falar)
            row.append(registro.grau_dificuldade_comer)
            row.append(registro.motivo_dificuldade_comer)
            row.append(registro.grau_dificuldade_relacionar)
            row.append(registro.motivo_dificuldade_relacionar)
            row.append(registro.grau_dificuldade_manter_humor)
            row.append(registro.motivo_dificuldade_manter_humor)
            row.append(registro.grau_dificuldade_estudar)
            row.append(registro.motivo_dificuldade_estudar)
            row.append(registro.grau_dificuldade_trabalhar)
            row.append(registro.motivo_dificuldade_trabalhar)
            row.append(registro.grau_dificuldade_higienizar)
            row.append(registro.motivo_dificuldade_higienizar)
            row.append(registro.grau_dificuldade_dormir)
            row.append(registro.motivo_dificuldade_dormir)
            row.append(registro.usa_fio_dental)
            row.append(registro.qts_dias_fio_dental_ultima_semana)
            row.append(registro.qtd_por_dia_consome_acucar)
            row.append(registro.motivo_dificuldade_estudar_trabalhar)
            row.append(registro.get_frequencia_escovacao_display())
            rows.append(row)
            contador += 1

    return XlsResponse(rows, processo=task)


@task('Exportar Dados de Atendimentos Odontológicos para XLS')
def relatorios_atendimentos_odontologicos_to_xls(atendimentos, task=None):
    rows = [
        [
            '#',
            'Nome',
            'Sexo',
            'Idade',
            'CPO-D Médio',
            'Dentes Cariados',
            'Dentes Perdidos',
            'Dentes Restaurados',
            'S1',
            'S2',
            'S3',
            'S4',
            'S5',
            'S6',
            'S1-S3',
            'S4-S6',
            'S1-S6',
            'Lábios',
            'Lingua',
            'Assoalho',
            'Mucosa Jugal',
            'Palato Duro',
            'Palato Mole',
            'Rebordo',
            'Cadeia Ganglionar',
            'Tonsilas Palatinas',
            'Atm',
            'Oclusão',
        ]
    ]

    contador = 1

    for atendimento in task.iterate(atendimentos):
        total = c = p = o = '-'
        tem_odontograma = atendimento.get_odontograma()
        if tem_odontograma:
            total, c, p, o = tem_odontograma.get_indice_cpod()
        labios = '-'
        lingua = '-'
        assoalho = '-'
        mucosa_jugal = '-'
        palato_duro = '-'
        palato_mole = '-'
        rebordo = '-'
        cadeia_ganglionar = '-'
        tonsilas_palatinas = '-'
        atm = '-'
        oclusao = '-'

        if atendimento.get_alteracoes_estomatologicas():
            labios = atendimento.get_alteracoes_estomatologicas().labios
            lingua = atendimento.get_alteracoes_estomatologicas().lingua
            assoalho = atendimento.get_alteracoes_estomatologicas().assoalho
            mucosa_jugal = atendimento.get_alteracoes_estomatologicas().mucosa_jugal
            palato_duro = atendimento.get_alteracoes_estomatologicas().palato_duro
            palato_mole = atendimento.get_alteracoes_estomatologicas().palato_mole
            rebordo = atendimento.get_alteracoes_estomatologicas().rebordo
            cadeia_ganglionar = atendimento.get_alteracoes_estomatologicas().cadeia_ganglionar
            tonsilas_palatinas = atendimento.get_alteracoes_estomatologicas().tonsilas_palatinas
            atm = atendimento.get_alteracoes_estomatologicas().atm
            oclusao = atendimento.get_alteracoes_estomatologicas().oclusao

        row = [
            contador,
            format_(atendimento.prontuario.vinculo.pessoa.nome),
            format_(atendimento.prontuario.vinculo.pessoa.pessoafisica.sexo),
            format_(atendimento.prontuario.vinculo.pessoa.pessoafisica.idade),
            format_(total),
            format_(c),
            format_(p),
            format_(o),
            format_(atendimento.get_exames_periodontais_s1()),
            format_(atendimento.get_exames_periodontais_s2()),
            format_(atendimento.get_exames_periodontais_s3()),
            format_(atendimento.get_exames_periodontais_s4()),
            format_(atendimento.get_exames_periodontais_s5()),
            format_(atendimento.get_exames_periodontais_s6()),
            format_(atendimento.get_exames_periodontais_s1_s3()),
            format_(atendimento.get_exames_periodontais_s4_s6()),
            format_(atendimento.get_exames_periodontais_s1_s6()),
            format_(labios),
            format_(lingua),
            format_(assoalho),
            format_(mucosa_jugal),
            format_(palato_duro),
            format_(palato_mole),
            format_(rebordo),
            format_(cadeia_ganglionar),
            format_(tonsilas_palatinas),
            format_(atm),
            format_(oclusao),
        ]
        rows.append(row)
        contador += 1
    return XlsResponse(rows, processo=task)


def _cid10_por_capitulo(atendimento: Atendimento) -> str:
    """Hipóteses diagnósticas do atendimento contadas por capítulo da CID-10, só os capítulos com ocorrência."""
    from saude.views import CAPITULOS_CID10  # import tardio: views importa este módulo

    contagens = (
        (titulo, HipoteseDiagnostica.objects.filter(atendimento=atendimento, cid__codigo__gte=primeiro, cid__codigo__lte=ultimo).count())
        for titulo, primeiro, ultimo in CAPITULOS_CID10
    )
    return ', '.join(f'{titulo}: {qtd}' for titulo, qtd in contagens if qtd)


def _alergias_da_ficha_mais_recente(atendimento: Atendimento) -> str:
    """Alergias alimentares e medicamentosas da versão mais recente do saúde-doença do atendimento (#17629)."""
    processo = atendimento.get_processo_saude_doenca()
    if not processo:
        return ''
    return ', '.join(alergia for alergia in (processo.que_alimentos, processo.que_medicamentos) if alergia)


@task('Exportar Relatório de Atendimentos Médicos e Enfermagem para XLS')
def relatorio_atendimento_medico_enfermagem_to_xls(registros: QuerySet[Atendimento], task: Task | None = None) -> HttpResponse | None:
    colunas = []
    rows = []
    colunas.append('#')
    colunas.append('Nome')
    colunas.append('Matrícula')
    colunas.append('Curso')
    colunas.append('Turma')
    colunas.append('CID-10 por Capítulo')
    colunas.append('Intervenções de Enfermagem')
    colunas.append('Alergias Medicamentosas e Alimentares')
    rows.append(colunas)
    contador = 1
    for registro in task.iterate(registros):
        row = [contador]
        aluno = registro.aluno
        row.append(format_(aluno.pessoa_fisica.nome))

        row.append(format_(aluno.matricula))

        row.append(format_(aluno.curso_campus))
        turma = '-'
        if aluno.get_ultima_matricula_periodo():
            turma = aluno.get_ultima_matricula_periodo().get_codigo_turma()
        row.append(format_(turma))
        row.append(_cid10_por_capitulo(registro))
        lista_intervencao = []
        for item in IntervencaoEnfermagem.objects.filter(atendimento=registro):
            lista_intervencao.append(item.procedimento_enfermagem.denominacao)
        row.append(', '.join(lista_intervencao))
        row.append(_alergias_da_ficha_mais_recente(registro))
        rows.append(row)
        contador += 1

    return XlsResponse(rows, processo=task)


@task('Exportar Lista de Alunos para XLS')
def lista_alunos_to_xls(
    atendimentos: QuerySet[Atendimento],
    ver_nome: bool,
    ver_matricula: bool,
    ver_curso: bool,
    ver_turma: bool,
    ver_rg: bool,
    ver_cpf: bool,
    ver_alergia_alimentos: bool,
    ver_alergia_medicamentos: bool,
    task: Task | None = None,
) -> HttpResponse | None:
    colunas = [
        (ver_nome, 'Nome', lambda atendimento: atendimento.aluno.pessoa_fisica.nome),
        (ver_matricula, 'Matrícula', lambda atendimento: atendimento.aluno.matricula),
        (ver_curso, 'Curso', lambda atendimento: atendimento.aluno.curso_campus),
        (ver_turma, 'Turma', lambda atendimento: atendimento.aluno.get_ultima_turma_cursada()),
        (ver_rg, 'RG', lambda atendimento: atendimento.aluno.pessoa_fisica.rg),
        (ver_cpf, 'CPF', lambda atendimento: atendimento.aluno.pessoa_fisica.cpf.replace('.', '').replace('-', '')),
        (ver_alergia_alimentos, 'Alergia à Alimentos', lambda atendimento: atendimento.get_alergias_alimentos()),
        (ver_alergia_medicamentos, 'Alergia à Medicamentos', lambda atendimento: atendimento.get_processo_saude_doenca().que_medicamentos),
    ]
    visiveis = [(titulo, valor) for ver, titulo, valor in colunas if ver]
    rows = [['#', *(titulo for titulo, _ in visiveis)]]
    for contador, atendimento in enumerate(task.iterate(atendimentos), 1):
        rows.append([contador, *(format_(valor(atendimento)) for _, valor in visiveis)])

    return XlsResponse(rows, processo=task)
