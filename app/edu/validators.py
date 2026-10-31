from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models

from comum.models import Ano, Raca
from comum.validators import (
    extrair_ano,
    extrair_periodo_letivo,
    handle_error,
    validar_booleano,
    validar_data,
    validar_decimal,
    validar_formatacao_cpf,
    validar_inteiro,
    validar_modelo,
    validar_passaporte,
    validar_string,
)
from edu.models import (
    Aluno,
    AreaCapes,
    AreaConcentracao,
    AreaCurso,
    Cartorio,
    Cidade,
    Componente,
    ComponenteCurricular,
    Convenio,
    CursoCampus,
    Deficiencia,
    Diretoria,
    EixoTecnologico,
    Estado,
    EstruturaCurso,
    FormaIngresso,
    Habilitacao,
    LinhaPesquisa,
    Matriz,
    NaturezaParticipacao,
    NivelEnsino,
    Nucleo,
    OrgaoEmissorRg,
    Pais,
    Polo,
    SituacaoMatricula,
    TipoComponente,
    TipoNEE,
    Turno,
)
from edu.models.cadastros_gerais import SituacaoMatriculaPeriodo
from edu.models.historico import RegistroHistorico, MatriculaDiario


def validar_tipo_procedimento(valor, erros=None, raise_exception=False):
    """
    Valida se o valor é uma string contendo um dos valores permitidos para tipo de procedimento.

    :param valor: O valor do campo a ser validado.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :return: O valor validado, ou None se o valor não for válido e a exceção não for levantada.
    """
    valor = valor.strip() if isinstance(valor, str) and valor else valor

    valores_permitidos = [
        'Intercâmbio',
        'Trancamento Compulsório',
        'Trancamento Voluntário',
        'Cancelamento Compulsório',
        'Cancelamento Voluntário',
        'Cancelamento por Duplicidade',
        'Cancelamento por Desligamento',
        'Evasão',
        'Jubilamento',
        'Reintegração',
        'Transferência Intercâmpus',
        'Transferência de Curso',
        'Transferência Externa',
        'Matrícula Vínculo',
        'Integralização Fase Escolar',
    ]

    if valor in valores_permitidos:
        return valor
    else:
        erro = f'O campo tipo de procedimento requer um dos seguintes valores: {", ".join(valores_permitidos)}. "{valor}" foi informado.'
        return handle_error(erro, erros, raise_exception)


def validar_matrizes(linha, ignorar_obrigatorios=False):
    erros = []
    registro = {}
    try:
        ativo = validar_booleano(linha['Matriz.ativo'], 'Matriz.ativo', erros=erros)
        data_inicio = validar_data(linha['Matriz.data_inicio'], 'Matriz.data_inicio', erros=erros)
        data_fim = validar_data(linha['Matriz.data_fim'], 'Matriz.data_fim', erros=erros)
        ano_criacao = extrair_ano(data_inicio)
        periodo_criacao = extrair_periodo_letivo(data_inicio)
        matriz_id = validar_inteiro(linha.get('Matriz.id', '').strip(), 0, None, 'Matriz.id', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios)
        matriz_db = Matriz.objects.filter(id=matriz_id)
        if matriz_db.exists():
            matriz_db_estrutura_id = matriz_db.first().estrutura_id
        else:
            matriz_db_estrutura_id = None

        registro = {
            'ativo': ativo,
            'descricao': linha['Matriz.descricao'].strip(),
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'ano_criacao': ano_criacao,
            'periodo_criacao': periodo_criacao,
            'qtd_periodos_letivos': validar_inteiro(
                linha['Matriz.qtd_periodos_letivos'], 1, 13, 'Matriz.qtd_periodos_letivos', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'ch_componentes_obrigatorios': validar_inteiro(
                linha['Matriz.ch_componentes_obrigatorios'],
                0,
                None,
                'Matriz.ch_componentes_obrigatorios',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_componentes_optativos': validar_inteiro(
                linha['Matriz.ch_componentes_optativos'],
                0,
                None,
                'Matriz.ch_componentes_optativos',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_componentes_eletivos': validar_inteiro(
                linha['Matriz.ch_componentes_eletivos'],
                0,
                None,
                'Matriz.ch_componentes_eletivos',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_seminarios': validar_inteiro(
                linha['Matriz.ch_seminarios'], 0, None, 'Matriz.ch_seminarios', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'ch_pratica_profissional': validar_inteiro(
                linha['Matriz.ch_pratica_profissional'],
                0,
                None,
                'Matriz.ch_pratica_profissional',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_atividades_complementares': validar_inteiro(
                linha['Matriz.ch_atividades_complementares'],
                0,
                None,
                'Matriz.ch_atividades_complementares',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_atividades_aprofundamento': validar_inteiro(
                linha['Matriz.ch_atividades_aprofundamento'],
                0,
                None,
                'Matriz.ch_atividades_aprofundamento',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_componentes_extensao': validar_inteiro(
                linha['Matriz.ch_componentes_extensao'],
                0,
                None,
                'Matriz.ch_componentes_extensao',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_atividades_extensao': validar_inteiro(
                linha['Matriz.ch_atividades_extensao'],
                0,
                None,
                'Matriz.ch_atividades_extensao',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_componentes_com_extensao': validar_inteiro(
                linha['Matriz.ch_componentes_com_extensao'],
                0,
                None,
                'Matriz.ch_componentes_com_extensao',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_componentes_tcc': validar_inteiro(
                linha['Matriz.ch_componentes_tcc'], 0, None, 'Matriz.ch_componentes_tcc', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'ch_pratica_como_componente': validar_inteiro(
                linha['Matriz.ch_pratica_como_componente'],
                0,
                None,
                'Matriz.ch_pratica_como_componente',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ch_visita_tecnica': validar_inteiro(
                linha['Matriz.ch_visita_tecnica'], 0, None, 'Matriz.ch_visita_tecnica', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'exige_tcc': validar_booleano(linha['Matriz.exige_tcc'], 'Matriz.exige_tcc', erros=erros),
            'observacao': linha.get('Matriz.observacao', '').strip(),
            'exige_estagio': validar_booleano(linha['Matriz.exige_estagio'], 'Matriz.exige_estagio', erros=erros),
            'ch_minima_estagio': validar_inteiro(
                linha['Matriz.ch_minima_estagio'], 0, None, 'Matriz.ch_minima_estagio', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            )
            if linha.get('Matriz.exige_estagio').strip().lower() in ['1', 'true', 'sim']
            else None,
            'periodo_minimo_estagio_obrigatorio': validar_inteiro(
                linha['Matriz.periodo_minimo_estagio_obrigatorio'],
                1,
                10,
                'Matriz.periodo_minimo_estagio_obrigatorio',
                False,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'periodo_minimo_estagio_nao_obrigatorio': validar_inteiro(
                linha['Matriz.periodo_minimo_estagio_nao_obrigatorio'],
                1,
                10,
                'Matriz.periodo_minimo_estagio_nao_obrigatorio',
                False,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'estrutura_id': validar_modelo(linha.get('Matriz.id_estrutura', ''), EstruturaCurso, 'Matriz.id_estrutura', erros=erros)
            if linha.get('Matriz.id_estrutura') != '0'
            else matriz_db_estrutura_id,
            'nivel_ensino_id': validar_inteiro(
                linha.get('Matriz.nivel_ensino', '').strip(), 0, 4, 'Matriz.nivel_ensino_id', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'natureza_participacao_id': validar_modelo(
                linha.get('Matriz.natureza_participacao', '').strip(),
                NaturezaParticipacao,
                'Matriz.natureza_participacao',
                campo_modelo='descricao',
                forcar_criacao=True,
                erros=erros,
            ),
            'id': matriz_id,
            'requer_vinculacao_extensao_diarios': True,
        }

        if ativo and data_fim:
            erros.append('Matriz ativa não pode ter data fim.')

        if not ativo and data_fim is None:
            erros.append('Matriz inativa requer data fim.')

    except Exception as e:
        erros.append(str(e))

    return registro, erros


def validar_cursos(linha, ignorar_obrigatorios=False):
    erros = []
    registro = {}
    try:
        registro = {
            'codigo': validar_string(
                linha.get('CursoCampus.codigo', '').strip(),
                'CursoCampus.codigo',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'codigo_academico': validar_inteiro(
                linha.get('CursoCampus.codigo_academico', '').strip(),
                obrigatorio=True,
                nome_campo='CursoCampus.codigo_academico',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'descricao': validar_string(
                linha.get('CursoCampus.descricao', '').strip(),
                'CursoCampus.descricao',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'descricao_historico': validar_string(
                linha.get('CursoCampus.descricao', '').strip(),
                'CursoCampus.descricao',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'diretoria_id': validar_modelo(
                linha.get('CursoCampus.diretoria', '').strip(), Diretoria, 'CursoCampus.diretoria', campo_modelo='setor__sigla', erros=erros
            ),
            'codigo_censup': validar_string(
                linha.get('CursoCampus.codigo_censup', '').strip(), 'CursoCampus.codigo_censup', obrigatorio=False, erros=erros
            ),
            'codigo_emec': validar_string(
                linha.get('CursoCampus.codigo_emec', '').strip(), 'CursoCampus.codigo_emec', obrigatorio=False, erros=erros
            ),
            'codigo_sistec': validar_string(
                linha.get('CursoCampus.codigo_sistec', '').strip(), 'CursoCampus.codigo_sistec', obrigatorio=False, erros=erros
            ),
            'codigo_educacenso': validar_string(
                linha.get('CursoCampus.codigo_educacenso', '').strip(), 'CursoCampus.codigo_educacenso', obrigatorio=False, erros=erros
            ),
            'ciencia_sem_fronteira': validar_booleano(
                linha.get('CursoCampus.ciencia_sem_fronteira', ''), 'CursoCampus.ciencia_sem_fronteira', erros=erros
            )
            or False,
            'formacao_de_professores': validar_booleano(
                linha.get('CursoCampus.formacao_de_professores', ''), 'CursoCampus.formacao_de_professores', erros=erros
            )
            or False,
            'ano_letivo_id': validar_modelo(
                linha.get('CursoCampus.ano_letivo', '').strip(), Ano, 'CursoCampus.ano_letivo', campo_modelo='ano', erros=erros
            ),
            'periodo_letivo': validar_inteiro(
                linha.get('CursoCampus.periodo_letivo', '').strip(),
                0,
                None,
                'CursoCampus.periodo_letivo',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'data_inicio': validar_data(linha.get('CursoCampus.data_inicio', '').strip(), 'CursoCampus.data_inicio', erros=erros),
            'data_funcionamento': validar_data(
                linha.get('CursoCampus.data_funcionamento', '').strip(), 'CursoCampus.data_funcionamento', erros=erros
            ),
            'data_solicitacao_reconhecimento': validar_data(
                linha.get('CursoCampus.data_solicitacao_reconhecimento', '').strip(), 'CursoCampus.data_solicitacao_reconhecimento', erros=erros
            ),
            'data_limite_reconhecimento': validar_data(
                linha.get('CursoCampus.data_limite_reconhecimento', '').strip(), 'CursoCampus.data_limite_reconhecimento', erros=erros
            ),
            'data_fim': validar_data(linha.get('CursoCampus.data_fim', '').strip(), 'CursoCampus.data_fim', erros=erros),
            'ativo': validar_booleano(linha.get('CursoCampus.ativo', ''), 'CursoCampus.ativo', erros=erros),
            'suspenso': validar_booleano(linha.get('CursoCampus.suspenso', ''), 'CursoCampus.suspenso', erros=erros) or False,
            'em_extincao': validar_booleano(linha.get('CursoCampus.em_extincao', ''), 'CursoCampus.em_extincao', erros=erros) or False,
            'extinto': validar_booleano(linha.get('CursoCampus.extinto', ''), 'CursoCampus.extinto', erros=erros) or False,
            'modalidade_id': validar_inteiro(
                linha.get('CursoCampus.modalidade', '').strip(),
                2,
                21,
                'CursoCampus.modalidade',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'quantidade_vagas': validar_inteiro(
                linha.get('CursoCampus.quantidade_vagas', '').strip(),
                0,
                None,
                'CursoCampus.quantidade_vagas',
                obrigatorio=False,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'periodicidade': validar_inteiro(
                linha.get('CursoCampus.periodicidade', '').strip(),
                1,
                3,
                'CursoCampus.periodicidade',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'exige_enade': validar_booleano(linha.get('CursoCampus.exige_enade', ''), 'CursoCampus.exige_enade', erros=erros) or False,
            'exige_colacao_grau': validar_booleano(linha.get('CursoCampus.exige_colacao_grau', ''), 'CursoCampus.exige_colacao_grau', erros=erros)
            or False,
            'emite_diploma': validar_booleano(linha.get('CursoCampus.emite_diploma', ''), 'CursoCampus.emite_diploma', erros=erros) or False,
            'assinatura_digital': validar_booleano(linha.get('CursoCampus.assinatura_digital', ''), 'CursoCampus.assinatura_digital', erros=erros)
            or False,
            'assinatura_eletronica': validar_booleano(
                linha.get('CursoCampus.assinatura_eletronica', ''), 'CursoCampus.assinatura_eletronica', erros=erros
            )
            or False,
            'area_concentracao_id': validar_modelo(
                linha.get('CursoCampus.area_concentracao', '').strip(),
                AreaConcentracao,
                'CursoCampus.area_concentracao',
                campo_modelo='descricao',
                forcar_criacao=True,
                obrigatorio=False,
                erros=erros,
            ),
            'programa': validar_string(
                linha.get('CursoCampus.programa', '').strip(),
                'CursoCampus.programa',
                obrigatorio=False,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'extensao': validar_booleano(linha.get('CursoCampus.extensao', ''), 'CursoCampus.extensao', erros=erros) or False,
            'titulo_certificado_masculino': validar_string(
                linha.get('CursoCampus.titulo_certificado_masculino', '').strip(),
                'CursoCampus.titulo_certificado_masculino',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'titulo_certificado_feminino': validar_string(
                linha.get('CursoCampus.titulo_certificado_feminino', '').strip(),
                'CursoCampus.titulo_certificado_feminino',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'matrizes': linha.get('CursoCampus.matrizes', '').strip().split(',') if linha.get('CursoCampus.matrizes') else [],
        }

        # Validações condicionais para área, eixo e área_capes baseadas na modalidade
        modalidade_id = registro['modalidade_id']
        if modalidade_id not in [8, 9, 10, 11, 12, 13, 14, 16, 18]:
            registro['area_id'] = validar_modelo(
                linha.get('CursoCampus.area', '').strip(), AreaCurso, 'CursoCampus.area', campo_modelo='descricao', forcar_criacao=True, erros=erros
            )
        if modalidade_id in [8, 11, 12, 13, 14, 18]:
            registro['eixo_id'] = validar_modelo(
                linha.get('CursoCampus.eixo', '').strip(),
                EixoTecnologico,
                'CursoCampus.eixo',
                campo_modelo='descricao',
                forcar_criacao=True,
                erros=erros,
            )
        if modalidade_id in [9, 10, 16]:
            registro['area_capes_id'] = validar_modelo(
                linha.get('CursoCampus.area_capes', '').strip(),
                AreaCapes,
                'CursoCampus.area_capes',
                campo_modelo='descricao',
                forcar_criacao=True,
                erros=erros,
            )

        # Validação das matrizes
        for matriz_id in registro['matrizes']:
            try:
                Matriz.objects.get(id=matriz_id.strip())
            except Matriz.DoesNotExist:
                erros.append(f'Matriz com ID {matriz_id.strip()} não foi encontrada.')

    except Exception as e:
        erros.append(str(e))

    return registro, erros


def validar_componentes(linha, registros_temp, ignorar_obrigatorios=False):
    erros = []
    registro = {}
    try:
        registro = {
            'matriz_id': validar_modelo(linha.get('Matriz.id', '').strip(), Matriz, 'Matriz.id', erros=erros),
            'componente_sigla_legado': validar_string(
                linha.get('Componente.sigla_legado', '').strip(), 'Componente.sigla_legado', obrigatorio=False, erros=erros
            ),
            'componente_ativo': validar_booleano(linha.get('Componente.ativo', ''), 'Componente.ativo', erros=erros),
            'componente_descricao': validar_string(
                linha.get('Componente.descricao', '').strip(),
                'Componente.descricao',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componente_ch_hora_relogio': validar_inteiro(
                linha.get('Componente.ch_hora_relogio', ''),
                0,
                None,
                'Componente.ch_hora_relogio',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componente_ch_hora_aula': validar_inteiro(
                linha.get('Componente.ch_hora_aula', ''), 0, None, 'Componente.ch_hora_aula', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'componente_ch_qtd_creditos': validar_inteiro(
                linha.get('Componente.ch_qtd_creditos', ''),
                0,
                None,
                'Componente.ch_qtd_creditos',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componente_nivel_ensino_id': validar_inteiro(
                linha.get('Componente.nivel_ensino_id', '').strip(),
                0,
                4,
                'Componente.nivel_ensino_id',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componente_observacao': validar_string(
                linha.get('Componente.observacao', '').strip(), 'Componente.observacao', obrigatorio=False, erros=erros
            ),
            'componente_tipo_id': validar_modelo(
                linha.get('Componente.tipo', '').strip(),
                TipoComponente,
                'Componente.tipo',
                'descricao',
                forcar_criacao=True,
                erros=erros,
            ),
            'componente_abreviatura': validar_string(
                linha.get('Componente.abreviatura', '').strip(), 'Componente.abreviatura', obrigatorio=False, erros=erros
            ),
            'componentecurricular_optativo': validar_booleano(
                linha.get('ComponenteCurricular.optativo', ''), 'ComponenteCurricular.optativo', erros=erros
            ),
            'componentecurricular_tipo_id': validar_inteiro(
                linha.get('ComponenteCurricular.tipo', '').strip(),
                1,
                5,
                'ComponenteCurricular.tipo',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componentecurricular_qtd_avaliacoes': validar_inteiro(
                linha.get('ComponenteCurricular.qtd_avaliacoes', ''),
                0,
                4,
                'ComponenteCurricular.qtd_avaliacoes',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componentecurricular_nucleo_id': validar_modelo(
                linha.get('ComponenteCurricular.nucleo', '').strip(),
                Nucleo,
                'ComponenteCurricular.nucleo',
                'descricao',
                forcar_criacao=True,
                erros=erros,
            ),
            'componentecurricular_ch_presencial': validar_inteiro(
                linha.get('ComponenteCurricular.ch_presencial', 0),
                0,
                None,
                'ComponenteCurricular.ch_presencial',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componentecurricular_ch_pratica': validar_inteiro(
                linha.get('ComponenteCurricular.ch_pratica', 0),
                0,
                None,
                'ComponenteCurricular.ch_pratica',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componentecurricular_ch_extensao': validar_inteiro(
                linha.get('ComponenteCurricular.ch_extensao', 0),
                0,
                None,
                'ComponenteCurricular.ch_extensao',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componentecurricular_ch_pcc': validar_inteiro(
                linha.get('ComponenteCurricular.ch_pcc', 0),
                0,
                None,
                'ComponenteCurricular.ch_pcc',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'componentecurricular_avaliacao_por_conceito': validar_booleano(
                linha.get('ComponenteCurricular.avaliacao_por_conceito', ''), 'ComponenteCurricular.avaliacao_por_conceito', erros=erros
            ),
            'componentecurricular_segundo_semestre': validar_booleano(
                linha.get('ComponenteCurricular.segundo_semestre', ''), 'ComponenteCurricular.segundo_semestre', erros=erros
            ),
            'componentecurricular_pode_fechar_pendencia': validar_booleano(
                linha.get('ComponenteCurricular.pode_fechar_pendencia', ''), 'ComponenteCurricular.pode_fechar_pendencia', erros=erros
            ),
            'componentecurricular_ch_semanal_1s': validar_inteiro(
                linha.get('ComponenteCurricular.ch_semanal_1s', ''), 0, None, 'ComponenteCurricular.ch_semanal_1s', obrigatorio=False, erros=erros
            ),
            'componentecurricular_ch_semanal_2s': validar_inteiro(
                linha.get('ComponenteCurricular.ch_semanal_2s', ''), 0, None, 'ComponenteCurricular.ch_semanal_2s', obrigatorio=False, erros=erros
            ),
            'componentecurricular_pre_requisitos': linha.get('ComponenteCurricular.pre_requisitos', '').strip().split(',')
            if linha.get('ComponenteCurricular.pre_requisitos')
            else [],
            'componentecurricular_co_requisitos': linha.get('ComponenteCurricular.co_requisitos', '').strip().split(',')
            if linha.get('ComponenteCurricular.co_requisitos')
            else [],
            'componentecurricular_periodo': validar_inteiro(
                linha.get('ComponenteCurricular.periodo', ''), 0, None, 'ComponenteCurricular.periodo', obrigatorio=False, erros=erros
            ),
        }

        # Campo 'componentecurricular_periodo' só é validado se 'componentecurricular_optativo' for falso
        if registro['componentecurricular_optativo'] and registro['componentecurricular_periodo']:
            erros.append('Componentes optativos não devem possuir um período letivo.')
        if not registro['componentecurricular_optativo'] and not registro['componentecurricular_periodo']:
            erros.append('Componentes obrigatórios devem possuir um período letivo.')

        if registro['componente_ch_hora_relogio'] != (
            registro['componentecurricular_ch_presencial']
            + registro['componentecurricular_ch_pratica']
            + registro['componentecurricular_ch_extensao']
            + registro['componentecurricular_ch_pcc']
        ):
            erros.append(
                'A soma dos campos "componentecurricular.ch_presencial", "componentecurricular.ch_pratica", "componentecurricular.ch_extensao" e  "componentecurricular.ch_pcc"precisa ser igual ao valor do campo "componente.componente_ch_hora_relogio".'
            )

        matriz = Matriz.objects.get(pk=registro['matriz_id'])
        if (
            registro['componentecurricular_tipo_id'] == 1
            and matriz.ch_componentes_obrigatorios == 0
            and not registro['componentecurricular_optativo']
        ):
            erros.append(
                'Não é possível informar um componente obrigatório do tipo REGULAR, pois a matriz não tem carga horária (ch_componentes_obrigatorios) para este tipo.'
            )
        elif registro['componentecurricular_tipo_id'] == 2 and matriz.ch_seminarios == 0:
            erros.append('Não é possível informar um componente tipo SEMINÁRIO, pois a matriz não tem carga horária (ch_seminarios) para este tipo.')
        elif registro['componentecurricular_tipo_id'] == 3 and matriz.ch_pratica_profissional == 0:
            erros.append(
                'Não é possível informar um componente tipo PRÁTICA PROFISSIONAL, pois a matriz não tem carga horária (ch_pratica_profissional) para este tipo.'
            )
        elif registro['componentecurricular_tipo_id'] == 4 and matriz.ch_componentes_tcc == 0:
            erros.append('Não é possível informar um componente tipo TCC, pois a matriz não tem carga horária (ch_componentes_tcc) para este tipo.')
        elif registro['componentecurricular_tipo_id'] == 5 and matriz.ch_componentes_extensao == 0:
            erros.append(
                'Não é possível informar um componente tipo ATIVIDADE DE EXTENSÃO, pois a matriz não tem carga horária (ch_componentes_extensao) para este tipo.'
            )

        if registro['componentecurricular_pre_requisitos']:
            pre_req = {'componentecurricular_periodo': None}
            for sigla in registro['componentecurricular_pre_requisitos']:
                if sigla in registros_temp:
                    pre_req = registros_temp[sigla]
                else:
                    try:
                        componente_db = ComponenteCurricular.objects.get(componente__sigla_qacademico=sigla.strip(), matriz_id=registro['matriz_id'])
                        pre_req = {'componentecurricular_periodo': componente_db.periodo_letivo}
                    except ComponenteCurricular.DoesNotExist:
                        erros.append(f'Componente curricular não encontrado para o pré-requisito {sigla}.')
                    except ComponenteCurricular.MultipleObjectsReturned:
                        erros.append(f'Foram encontrados múltiplos componentes curriculares com a sigla {sigla} na matriz {registro["matriz_id"]}.')

                if registro['componentecurricular_periodo'] and pre_req['componentecurricular_periodo'] is None:
                    erros.append(f'Pré-requisito {sigla} não possui período de oferta e não pode ser requisito deste componente.')
                elif registro['componentecurricular_periodo'] and pre_req['componentecurricular_periodo'] >= registro['componentecurricular_periodo']:
                    erros.append(f'Pré-requisito {sigla} deve estar em um período anterior ao componente atual.')

        if registro['componentecurricular_co_requisitos']:
            co_req = {'componentecurricular_periodo': None}
            for sigla in registro['componentecurricular_co_requisitos']:
                if sigla in registros_temp:
                    co_req = registros_temp[sigla]
                else:
                    try:
                        componente_db = ComponenteCurricular.objects.get(componente__sigla_qacademico=sigla.strip(), matriz_id=registro['matriz_id'])
                        co_req = {'componentecurricular_periodo': componente_db.periodo_letivo}
                    except ComponenteCurricular.DoesNotExist:
                        erros.append(f'Componente curricular não encontrado para o co-requisito {sigla}.')
                    except ComponenteCurricular.MultipleObjectsReturned:
                        erros.append(f'Foram encontrados múltiplos componentes curriculares com a sigla {sigla} na matriz {registro["matriz_id"]}.')

                if registro['componentecurricular_periodo'] and co_req['componentecurricular_periodo'] is None:
                    erros.append(f'Co-requisito {sigla} não possui período de oferta e não pode ser requisito deste componente.')
                elif registro['componentecurricular_periodo'] and co_req['componentecurricular_periodo'] > registro['componentecurricular_periodo']:
                    erros.append(f'Co-requisito {sigla} deve estar no mesmo período ou em um anterior ao componente atual.')

    except Exception as e:
        erros.append(str(e))

    return registro, erros


def validar_lista_modelos(
    valor: str | None,
    modelo: type[models.Model],
    nome_campo: str,
    campo_modelo: str = 'id',
    erros: list[str] | None = None,
) -> list[int]:
    """
    Valida uma lista de identificadores separados por vírgula para um modelo Django.

    Se o campo estiver vazio ou nulo, retorna lista vazia.
    Se contiver tokens, valida a existência de cada um via validar_modelo.
    """
    if not valor or not valor.strip():
        return []

    ids: list[int] = []
    tokens = [x.strip() for x in valor.split(',') if x.strip()]
    for token in tokens:
        item_id = validar_modelo(
            token,
            modelo,
            nome_campo,
            campo_modelo=campo_modelo,
            obrigatorio=True,
            erros=erros,
        )
        if item_id is not None:
            ids.append(item_id)
    return ids


def validar_alunos(linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any], list[str]]:
    erros = []
    registro = {}
    try:
        possui_convenio = validar_booleano(linha.get('Aluno.possui_convenio', ''), nome_campo='Aluno.possui_convenio', erros=erros)
        dt_conclusao_curso = validar_data(linha.get('Aluno.dt_conclusao_curso', '').strip(), nome_campo='Aluno.dt_conclusao_curso', erros=erros)
        registro = {
            'codigo_academico': validar_inteiro(
                linha.get('Aluno.codigo_academico', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.codigo_academico',
                erros=erros,
                ignorar_obrigatorios=False,
            ),
            'matricula': validar_string(
                linha.get('Aluno.matricula', '').strip(), obrigatorio=True, nome_campo='Aluno.matricula', erros=erros, ignorar_obrigatorios=False
            ),
            'estado_civil': validar_string(
                linha.get('Aluno.estado_civil', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.estado_civil',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'logradouro': validar_string(
                linha.get('Aluno.logradouro', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.logradouro',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'numero': validar_string(
                linha.get('Aluno.numero', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.numero',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'complemento': validar_string(
                linha.get('Aluno.complemento', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.complemento',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'bairro': validar_string(
                linha.get('Aluno.bairro', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.bairro',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'cep': validar_string(
                linha.get('Aluno.cep', '').strip(), obrigatorio=False, nome_campo='Aluno.cep', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'cidade_id': validar_naturalidade(
                linha.get('Aluno.cidade', '').strip(), 'Aluno.cidade', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'tipo_zona_residencial': validar_string(
                linha.get('Aluno.tipo_zona_residencial', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.tipo_zona_residencial',
                erros=erros,
                max_len=1,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'logradouro_profissional': validar_string(
                linha.get('Aluno.logradouro_profissional', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.logradouro_profissional',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'numero_profissional': validar_string(
                linha.get('Aluno.numero_profissional', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.numero_profissional',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'complemento_profissional': validar_string(
                linha.get('Aluno.complemento_profissional', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.complemento_profissional',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'bairro_profissional': validar_string(
                linha.get('Aluno.bairro_profissional', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.bairro_profissional',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'cep_profissional': validar_string(
                linha.get('Aluno.cep_profissional', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.cep_profissional',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'cidade_profissional_id': validar_naturalidade(
                linha.get('Aluno.cidade_profissional', '').strip(), 'Aluno.cidade_profissional', obrigatorio=False, erros=erros
            ),
            'tipo_zona_residencial_profissional': validar_string(
                linha.get('Aluno.tipo_zona_residencial_profissional', '').strip(),
                obrigatorio=False,
                max_len=1,
                nome_campo='Aluno.tipo_zona_residencial_profissional',
                erros=erros,
            ),
            'telefone_profissional': validar_string(
                linha.get('Aluno.telefone_profissional', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.telefone_profissional',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'nome_pai': validar_string(
                linha.get('Aluno.nome_pai', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.nome_pai',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'estado_civil_pai': validar_string(
                linha.get('Aluno.estado_civil_pai', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.estado_civil_pai',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'pai_falecido': validar_booleano(linha.get('Aluno.pai_falecido', ''), nome_campo='Aluno.pai_falecido', erros=erros) or False,
            'nome_mae': validar_string(
                linha.get('Aluno.nome_mae', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.nome_mae',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'estado_civil_mae': validar_string(
                linha.get('Aluno.estado_civil_mae', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.estado_civil_mae',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'mae_falecida': validar_booleano(linha.get('Aluno.mae_falecida', ''), nome_campo='Aluno.mae_falecida', erros=erros) or False,
            'responsavel': validar_string(
                linha.get('Aluno.responsavel', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.responsavel',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'email_responsavel': validar_string(
                linha.get('Aluno.email_responsavel', '').strip(),
                obrigatorio=bool(linha.get('Aluno.responsavel')),
                nome_campo='Aluno.email_responsavel',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'parentesco_responsavel': validar_string(
                linha.get('Aluno.parentesco_responsavel', '').strip(),
                obrigatorio=bool(linha.get('Aluno.responsavel')),
                nome_campo='Aluno.parentesco_responsavel',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'cpf_responsavel': validar_string(
                linha.get('Aluno.cpf_responsavel', '').strip(),
                obrigatorio=bool(linha.get('Aluno.responsavel')),
                nome_campo='Aluno.cpf_responsavel',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'telefone_principal': validar_string(
                linha.get('Aluno.telefone_principal', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.telefone_principal',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'telefone_secundario': validar_string(
                linha.get('Aluno.telefone_secundario', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.telefone_secundario',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'telefone_adicional_1': validar_string(
                linha.get('Aluno.telefone_adicional_1', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.telefone_adicional_1',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'telefone_adicional_2': validar_string(
                linha.get('Aluno.telefone_adicional_2', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.telefone_adicional_2',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'facebook': validar_string(
                linha.get('Aluno.facebook', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.facebook',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'instagram': validar_string(
                linha.get('Aluno.instagram', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.instagram',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'twitter': validar_string(
                linha.get('Aluno.twitter', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.twitter',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'linkedin': validar_string(
                linha.get('Aluno.linkedin', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.linkedin',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'skype': validar_string(
                linha.get('Aluno.skype', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.skype',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'tipo_sanguineo': validar_string(
                linha.get('Aluno.tipo_sanguineo', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.tipo_sanguineo',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'nacionalidade': validar_string(
                linha.get('Aluno.nacionalidade', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.nacionalidade',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'passaporte': validar_passaporte(
                linha.get('Aluno.passaporte', '').strip(),
                obrigatorio=linha.get('Aluno.nacionalidade') == 'Estrangeira',
                nome_campo='Aluno.passaporte',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'pais_origem_id': validar_modelo(
                linha.get('Aluno.pais_origem', '').strip(),
                Pais,
                'Aluno.pais_origem',
                campo_modelo='sigla',
                obrigatorio=linha.get('Aluno.nacionalidade') == 'Estrangeira',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'naturalidade_id': validar_naturalidade(
                linha.get('Aluno.naturalidade', '').strip(),
                'Aluno.naturalidade',
                obrigatorio=linha.get('Aluno.nacionalidade') == 'Brasileira',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'deficiencias': validar_lista_modelos(linha.get('Aluno.deficiencias'), Deficiencia, 'Aluno.deficiencias', erros=erros),
            'outras_nees': validar_lista_modelos(linha.get('Aluno.outras_nees'), TipoNEE, 'Aluno.outras_nees', erros=erros),
            'nivel_ensino_anterior_id': validar_modelo(
                linha.get('Aluno.nivel_ensino_anterior', '').strip(), NivelEnsino, 'Aluno.nivel_ensino_anterior', obrigatorio=False, erros=erros
            ),
            'tipo_instituicao_origem': validar_string(
                linha.get('Aluno.tipo_instituicao_origem', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.tipo_instituicao_origem',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'nome_instituicao_anterior': validar_string(
                linha.get('Aluno.nome_instituicao_anterior', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.nome_instituicao_anterior',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ano_conclusao_estudo_anterior_id': validar_modelo(
                linha.get('Aluno.ano_conclusao_estudo_anterior', '').strip(),
                Ano,
                'Aluno.ano_conclusao_estudo_anterior',
                campo_modelo='ano',
                obrigatorio=False,
                erros=erros,
            ),
            'numero_rg': validar_string(
                linha.get('Aluno.numero_rg', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.numero_rg',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'uf_emissao_rg_id': validar_modelo(
                linha.get('Aluno.uf_emissao_rg', '').strip(), Estado, 'Aluno.uf_emissao_rg', obrigatorio=False, erros=erros
            ),
            'orgao_emissao_rg_id': validar_modelo(
                linha.get('Aluno.orgao_emissao_rg', '').strip(),
                OrgaoEmissorRg,
                'Aluno.orgao_emissao_rg',
                campo_modelo='nome',
                obrigatorio=False,
                erros=erros,
            ),
            'data_emissao_rg': validar_data(linha.get('Aluno.data_emissao_rg', '').strip(), nome_campo='Aluno.data_emissao_rg', erros=erros),
            'numero_titulo_eleitor': validar_string(
                linha.get('Aluno.numero_titulo_eleitor', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.numero_titulo_eleitor',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'zona_titulo_eleitor': validar_string(
                linha.get('Aluno.zona_titulo_eleitor', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.zona_titulo_eleitor',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'secao': validar_string(
                linha.get('Aluno.secao', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.secao',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'data_emissao_titulo_eleitor': validar_data(
                linha.get('Aluno.data_emissao_titulo_eleitor', '').strip(), nome_campo='Aluno.data_emissao_titulo_eleitor', erros=erros
            ),
            'uf_emissao_titulo_eleitor_id': validar_modelo(
                linha.get('Aluno.uf_emissao_titulo_eleitor', '').strip(), Estado, 'Aluno.uf_emissao_titulo_eleitor', obrigatorio=False, erros=erros
            ),
            'numero_carteira_reservista': validar_string(
                linha.get('Aluno.numero_carteira_reservista', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.numero_carteira_reservista',
                erros=erros,
            ),
            'regiao_carteira_reservista': validar_string(
                linha.get('Aluno.regiao_carteira_reservista', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.regiao_carteira_reservista',
                erros=erros,
            ),
            'serie_carteira_reservista': validar_string(
                linha.get('Aluno.serie_carteira_reservista', '').strip(), obrigatorio=False, nome_campo='Aluno.serie_carteira_reservista', erros=erros
            ),
            'estado_emissao_carteira_reservista_id': validar_modelo(
                linha.get('Aluno.estado_emissao_carteira_reservista', '').strip(),
                Estado,
                'Aluno.estado_emissao_carteira_reservista',
                campo_modelo='nome',
                obrigatorio=False,
                erros=erros,
            ),
            'ano_carteira_reservista': validar_inteiro(
                linha.get('Aluno.ano_carteira_reservista', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.ano_carteira_reservista',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'tipo_certidao': validar_string(
                linha.get('Aluno.tipo_certidao', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.tipo_certidao',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'cartorio_id': validar_modelo(
                linha.get('Aluno.cartorio', '').strip(), Cartorio, 'Aluno.cartorio', campo_modelo='nome', obrigatorio=False, erros=erros
            ),
            'numero_certidao': validar_string(
                linha.get('Aluno.numero_certidao', '').strip(), obrigatorio=False, nome_campo='Aluno.numero_certidao', erros=erros
            ),
            'folha_certidao': validar_string(
                linha.get('Aluno.folha_certidao', '').strip(), obrigatorio=False, nome_campo='Aluno.folha_certidao', erros=erros
            ),
            'livro_certidao': validar_string(
                linha.get('Aluno.livro_certidao', '').strip(), obrigatorio=False, nome_campo='Aluno.livro_certidao', erros=erros
            ),
            'data_emissao_certidao': validar_data(
                linha.get('Aluno.data_emissao_certidao', '').strip(), nome_campo='Aluno.data_emissao_certidao', erros=erros
            ),
            'matricula_certidao': validar_string(
                linha.get('Aluno.matricula_certidao', '').strip(), obrigatorio=False, nome_campo='Aluno.matricula_certidao', erros=erros
            ),
            'ano_letivo_id': validar_modelo(
                linha.get('Aluno.ano_letivo', '').strip(),
                Ano,
                'Aluno.ano_letivo',
                campo_modelo='ano',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'periodo_letivo': validar_inteiro(
                linha.get('Aluno.periodo_letivo', '').strip(),
                0,
                None,
                obrigatorio=True,
                nome_campo='Aluno.periodo_letivo',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'data_matricula': validar_data(linha.get('Aluno.data_matricula', '').strip(), nome_campo='Aluno.data_matricula', erros=erros),
            'turno_id': validar_modelo(
                linha.get('Aluno.turno', '').strip(), Turno, 'Aluno.turno', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'forma_ingresso_id': validar_modelo(
                linha.get('Aluno.forma_ingresso', '').strip(),
                FormaIngresso,
                'Aluno.forma_ingresso',
                campo_modelo='descricao',
                forcar_criacao=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'cota_sistec': validar_string(linha.get('Aluno.cota_sistec', '').strip(), obrigatorio=False, nome_campo='Aluno.cota_sistec', erros=erros),
            'cota_mec': validar_string(linha.get('Aluno.cota_mec', '').strip(), obrigatorio=False, nome_campo='Aluno.cota_mec', erros=erros),
            'possui_convenio': possui_convenio,
            'convenio_id': validar_modelo(
                linha.get('Aluno.convenio', '').strip(),
                Convenio,
                'Aluno.convenio',
                campo_modelo='descricao',
                obrigatorio=possui_convenio,
                forcar_criacao=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'data_conclusao_intercambio': validar_data(
                linha.get('Aluno.data_conclusao_intercambio', '').strip(), nome_campo='Aluno.data_conclusao_intercambio', erros=erros
            ),
            'curso_campus_id': validar_modelo(
                linha.get('Aluno.curso_campus', '').strip(), CursoCampus, 'Aluno.curso_campus', campo_modelo='codigo_academico', erros=erros
            ),
            'habilitacao_id': validar_modelo(
                linha.get('Aluno.habilitacao', '').strip(), Habilitacao, 'Aluno.habilitacao', campo_modelo='descricao', obrigatorio=False, erros=erros
            ),
            'matriz_id': validar_modelo(
                linha.get('Aluno.matriz', '').strip(), Matriz, 'Aluno.matriz', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'situacao_id': validar_modelo(
                linha.get('Aluno.situacao', '').strip(), SituacaoMatricula, 'Aluno.situacao', erros=erros, ignorar_obrigatorios=ignorar_obrigatorios
            ),
            'numero_pasta': validar_string(
                linha.get('Aluno.numero_pasta', '').strip(), obrigatorio=False, nome_campo='Aluno.numero_pasta', erros=erros
            ),
            'linha_pesquisa_id': validar_modelo(
                linha.get('Aluno.linha_pesquisa', '').strip(),
                LinhaPesquisa,
                'Aluno.linha_pesquisa',
                campo_modelo='descricao',
                obrigatorio=False,
                forcar_criacao=True,
                erros=erros,
            ),
            'aluno_especial': validar_booleano(linha.get('Aluno.aluno_especial', ''), nome_campo='Aluno.aluno_especial', erros=erros) or False,
            'dt_conclusao_curso': dt_conclusao_curso,
            'data_expedicao_diploma': validar_data(
                linha.get('Aluno.data_expedicao_diploma', '').strip(), nome_campo='Aluno.data_expedicao_diploma', erros=erros
            ),
            'data_colacao_grau': validar_data(linha.get('Aluno.data_colacao_grau', '').strip(), nome_campo='Aluno.data_colacao_grau', erros=erros),
            'renda_per_capita': validar_decimal(
                linha.get('Aluno.renda_per_capita', '').strip(), obrigatorio=False, nome_campo='Aluno.renda_per_capita', erros=erros
            ),
            'observacao_historico': validar_string(
                linha.get('Aluno.observacao_historico', '').strip(), obrigatorio=False, nome_campo='Aluno.observacao_historico', erros=erros
            ),
            'email_academico': validar_string(
                linha.get('Aluno.email_academico', '').strip(), obrigatorio=False, nome_campo='Aluno.email_academico', erros=erros
            ),
            'email_qacademico': validar_string(
                linha.get('Aluno.email_qacademico', '').strip(), obrigatorio=False, nome_campo='Aluno.email_qacademico', erros=erros
            ),
            'email_google_classroom': validar_string(
                linha.get('Aluno.email_google_classroom', '').strip(), obrigatorio=False, nome_campo='Aluno.email_google_classroom', erros=erros
            ),
            'poder_publico_responsavel_transporte': validar_string(
                linha.get('Aluno.poder_publico_responsavel_transporte', '').strip(),
                obrigatorio=False,
                nome_campo='Aluno.poder_publico_responsavel_transporte',
                erros=erros,
            ),
            'tipo_veiculo': validar_string(
                linha.get('Aluno.tipo_veiculo', '').strip(),
                obrigatorio=bool(linha.get('Aluno.poder_publico_responsavel_transporte')),
                nome_campo='Aluno.tipo_veiculo',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'ano_conclusao': dt_conclusao_curso.year if dt_conclusao_curso else None,
            'codigo_sistec': validar_string(linha.get('Aluno.codigo_sistec', '').strip(), 'Aluno.codigo_sistec', obrigatorio=False, erros=erros),
            'data_inicio_ciclo': validar_data(
                linha.get('Aluno.data_inicio_ciclo', '').strip(),
                nome_campo='Aluno.data_inicio_ciclo',
                erros=erros,
            ),
            'polo_id': validar_modelo(
                linha.get('Aluno.polo', '').strip(),
                Polo,
                'Aluno.polo',
                campo_modelo='sigla',
                obrigatorio=False,
                erros=erros,
            ),
        }

        pessoa_fisica_data = {
            'cpf': validar_formatacao_cpf(
                linha.get('Aluno.PessoaFisica.cpf', '').strip(),
                obrigatorio=linha.get('Aluno.nacionalidade') == 'Brasileira',
                nome_campo='Aluno.PessoaFisica.cpf',
                erros=erros,
            ),
            'nome_registro': validar_string(
                linha.get('Aluno.PessoaFisica.nome_registro', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.PessoaFisica.nome_registro',
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'nome_social': validar_string(
                linha.get('Aluno.PessoaFisica.nome_social', '').strip(), obrigatorio=False, nome_campo='Aluno.PessoaFisica.nome_social', erros=erros
            ),
            'sexo': validar_string(
                linha.get('Aluno.PessoaFisica.sexo', '').strip(),
                obrigatorio=True,
                nome_campo='Aluno.PessoaFisica.sexo',
                erros=erros,
                max_len=1,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'nascimento_data': validar_data(
                linha.get('Aluno.PessoaFisica.nascimento_data', '').strip(), nome_campo='Aluno.PessoaFisica.nascimento_data', erros=erros
            ),
            'raca_id': validar_modelo(
                linha.get('Aluno.PessoaFisica.raca', '').strip(), Raca, 'Aluno.PessoaFisica.raca', campo_modelo='codigo_siape', erros=erros
            ),
        }

        registro['PessoaFisica'] = pessoa_fisica_data

    except Exception as e:
        erros.append(str(e))

    return registro, erros


def validar_historico_aluno(linha, ignorar_obrigatorios=False):
    erros = []
    registro = {}

    try:
        matricula_periodo_data = {
            'ano_letivo_id': validar_modelo(
                linha.get('MatriculaPeriodo.ano_letivo', '').strip(), Ano, 'MatriculaPeriodo.ano_letivo', campo_modelo='ano', erros=erros
            ),
            'periodo_letivo': validar_inteiro(
                linha.get('MatriculaPeriodo.periodo_letivo', '').strip(), 0, None, nome_campo='MatriculaPeriodo.periodo_letivo', erros=erros
            ),
            'periodo_matriz': validar_inteiro(
                linha.get('MatriculaPeriodo.periodo_matriz', '').strip(),
                min_val=0,
                max_val=None,
                nome_campo='MatriculaPeriodo.periodo_matriz',
                obrigatorio=True,
                erros=erros,
                ignorar_obrigatorios=ignorar_obrigatorios,
            ),
            'situacao_id': validar_modelo(
                linha.get('MatriculaPeriodo.situacao', '').strip(), SituacaoMatriculaPeriodo, 'MatriculaPeriodo.situacao', erros=erros
            ),
            'codigo_turma_qacademico': validar_string(
                linha.get('MatriculaPeriodo.codigo_turma_qacademico', '').strip(),
                'MatriculaPeriodo.codigo_turma_qacademico',
                obrigatorio=False,
                erros=erros,
            ),
            'codigo_educacenso': validar_string(
                linha.get('MatriculaPeriodo.codigo_educacenso', '').strip(), 'MatriculaPeriodo.codigo_educacenso', obrigatorio=False, erros=erros
            ),
            'periodo_integralizado_ensino_medio': False,
        }

        registro_historico_data = {
            'componente_id': validar_modelo(
                linha.get('RegistroHistorico.componente', '').strip(),
                Componente,
                'RegistroHistorico.componente',
                campo_modelo='sigla_qacademico',
                erros=erros,
            ),
            'codigo_diario': validar_string(
                linha.get('RegistroHistorico.codigo_diario', '').strip(), 'RegistroHistorico.codigo_diario', obrigatorio=False, erros=erros
            ),
            'codigo_turma': validar_string(
                linha.get('RegistroHistorico.codigo_turma', '').strip(), 'RegistroHistorico.codigo_turma', obrigatorio=False, erros=erros
            ),
            'media_final_disciplina': validar_nota(
                linha.get('RegistroHistorico.media_final_disciplina', '').strip(), nome_campo='RegistroHistorico.media_final_disciplina', erros=erros
            ),
            'conceito': validar_string(
                linha.get('RegistroHistorico.conceito', '').strip(), 'RegistroHistorico.conceito', obrigatorio=False, erros=erros
            ),
            'frequencia': validar_inteiro(
                linha.get('RegistroHistorico.frequencia', '').strip(),
                min_val=0,
                max_val=100,
                nome_campo='RegistroHistorico.frequencia',
                obrigatorio=False,
                erros=erros,
            ),
            'situacao': validar_inteiro(
                linha.get('RegistroHistorico.situacao', '').strip(), min_val=0, max_val=None, nome_campo='RegistroHistorico.situacao', erros=erros
            ),
            'codigo_professor': validar_inteiro(
                linha.get('RegistroHistorico.codigo_professor', '').strip(),
                min_val=0,
                max_val=None,
                nome_campo='RegistroHistorico.codigo_professor',
                obrigatorio=False,
                erros=erros,
            ),
            'nome_professor': validar_string(
                linha.get('RegistroHistorico.nome_professor', '').strip(), 'RegistroHistorico.nome_professor', obrigatorio=False, erros=erros
            ),
            'titularidade_professor': validar_string(
                linha.get('RegistroHistorico.titularidade_professor', '').strip(),
                'RegistroHistorico.titularidade_professor',
                obrigatorio=False,
                erros=erros,
            ),
            'codigo_professor2': validar_inteiro(
                linha.get('RegistroHistorico.codigo_professor2', '').strip(),
                min_val=0,
                max_val=None,
                nome_campo='RegistroHistorico.codigo_professor2',
                obrigatorio=False,
                erros=erros,
            ),
            'nome_professor2': validar_string(
                linha.get('RegistroHistorico.nome_professor2', '').strip(), 'RegistroHistorico.nome_professor2', obrigatorio=False, erros=erros
            ),
            'titularidade_professor2': validar_string(
                linha.get('RegistroHistorico.titularidade_professor2', '').strip(),
                'RegistroHistorico.titularidade_professor2',
                obrigatorio=False,
                erros=erros,
            ),
            'outros_professores': validar_string(
                linha.get('RegistroHistorico.outros_professores', '').strip(),
                'RegistroHistorico.outros_professores',
                obrigatorio=False,
                erros=erros,
            ),
            'identificador_externo': validar_inteiro(
                linha.get('RegistroHistorico.identificador_externo', '').strip(),
                min_val=0,
                max_val=None,
                nome_campo='RegistroHistorico.identificador_externo',
                erros=erros,
            ),
        }

        outros_professores = registro_historico_data.get('outros_professores')
        if outros_professores:
            outros_professores = outros_professores.replace(',', ';')
            registro_historico_data['outros_professores'] = outros_professores
            erro = validar_outros_professores(outros_professores)
            if erro:
                erros.append(
                    f'O campo RegistroHistorico.outros_professores falhou na seguinte validação: {erro}. Foi informado {registro_historico_data.get("outros_professores")}.'
                )

        if registro_historico_data.get('situacao') not in [2, 3, 5, 6, 7, 8, 9, 10, 13, 11, 12, 23]:
            erros.append('O campo RegistroHistorico.situacao requer um dos seguintes valores: 2, 3, 5, 6, 7, 8, 9, 10, 13, 11, 12 ou 23.')

        if (
            not ignorar_obrigatorios
            and registro_historico_data.get('situacao')
            not in [
                MatriculaDiario.SITUACAO_TRANCADO,
                MatriculaDiario.SITUACAO_CANCELADO,
                MatriculaDiario.SITUACAO_DISPENSADO,
                MatriculaDiario.SITUACAO_PENDENTE,
                MatriculaDiario.SITUACAO_TRANSFERIDO,
            ]
            and registro_historico_data.get('media_final_disciplina') is None
            and not registro_historico_data.get('conceito')
        ):
            erros.append('É obrigatório o preenchimento de um dos campos: "media_final_disciplina" ou "conceito".')

        if (
            not ignorar_obrigatorios
            and registro_historico_data.get('situacao')
            not in [
                MatriculaDiario.SITUACAO_TRANCADO,
                MatriculaDiario.SITUACAO_CANCELADO,
                MatriculaDiario.SITUACAO_DISPENSADO,
                MatriculaDiario.SITUACAO_PENDENTE,
                MatriculaDiario.SITUACAO_TRANSFERIDO,
            ]
            and registro_historico_data.get('frequencia') is None
        ):
            erros.append('É obrigatório o preenchimento do campo "frequencia".')

        if registro_historico_data.get('media_final_disciplina') and registro_historico_data.get('conceito'):
            erros.append('Preencha apenas um dos campos: "media_final_disciplina" ou "conceito".')

        registro['aluno_id'] = validar_modelo(
            linha.get('Aluno.matricula', '').strip(), Aluno, 'Aluno.matricula', campo_modelo='matricula', erros=erros
        )

        registro['MatriculaPeriodo'] = matricula_periodo_data
        registro['RegistroHistorico'] = registro_historico_data

    except Exception as e:
        erros.append(str(e))

    return registro, erros


def validar_procedimento_matricula(linha):
    erros = []
    registro = {}

    try:
        matricula_periodo_data = {
            'ano_letivo_id': validar_modelo(
                linha.get('MatriculaPeriodo.ano_letivo', '').strip(), Ano, 'MatriculaPeriodo.ano_letivo', campo_modelo='ano', erros=erros
            ),
            'periodo_letivo': validar_inteiro(
                linha.get('MatriculaPeriodo.periodo_letivo', '').strip(), 0, None, nome_campo='MatriculaPeriodo.periodo_letivo', erros=erros
            ),
        }

        procedimento_matricula_data = {
            'tipo': validar_tipo_procedimento(linha.get('ProcedimentoMatricula.tipo', '').strip(), erros=erros),
            'motivo': validar_string(linha.get('ProcedimentoMatricula.motivo', '').strip(), 'ProcedimentoMatricula.motivo', erros=erros),
            'data': validar_data(linha.get('ProcedimentoMatricula.data', '').strip(), 'ProcedimentoMatricula.data', erros=erros),
            'identificador_externo': validar_inteiro(
                linha.get('ProcedimentoMatricula.identificador_externo', '').strip(),
                0,
                None,
                'ProcedimentoMatricula.identificador_externo',
                obrigatorio=False,
                erros=erros,
            ),
            'situacao_matricula_anterior_id': 1,
        }

        registro['aluno_id'] = validar_modelo(
            linha.get('Aluno.matricula', '').strip(), Aluno, 'Aluno.matricula', campo_modelo='matricula', erros=erros
        )
        registro['MatriculaPeriodo'] = matricula_periodo_data
        registro['ProcedimentoMatricula'] = procedimento_matricula_data

    except Exception as e:
        erros.append(str(e))

    return registro, erros


def validar_equivalencia(linha):
    erros = []
    registro = {}

    try:
        matricula_periodo_data = {
            'ano_letivo_id': validar_modelo(
                linha.get('MatriculaPeriodo.ano_letivo', '').strip(), Ano, 'MatriculaPeriodo.ano_letivo', campo_modelo='ano', erros=erros
            ),
            'periodo_letivo': validar_inteiro(
                linha.get('MatriculaPeriodo.periodo_letivo', '').strip(), nome_campo='MatriculaPeriodo.periodo_letivo', erros=erros
            ),
        }
        aluno_id = validar_modelo(linha.get('Aluno.matricula', '').strip(), Aluno, 'Aluno.matricula', campo_modelo='matricula', erros=erros)
        componente_id = validar_modelo(
            linha.get('AproveitamentoComponente.componente_curricular', '').strip(),
            Componente,
            'AproveitamentoComponente.componente_curricular',
            'sigla_qacademico',
            erros=erros,
        )
        matriz_id = Aluno.objects.filter(id=aluno_id).only('matriz_id').first().matriz_id

        if matriz_id is None:
            erros.append(f'O aluno {aluno_id} não foi vinculado a uma matriz.')

        cc = ComponenteCurricular.objects.filter(componente_id=componente_id, matriz_id=matriz_id).first()
        if cc is None:
            erros.append(
                f'O componente {linha.get("AproveitamentoComponente.componente_curricular", "").strip()} não foi vinculado à matriz {matriz_id}.'
            )

        registro['componente_currricular_id'] = cc.id
        registro['MatriculaPeriodo'] = matricula_periodo_data
        registro['aluno_id'] = aluno_id

        registro['registros_historico'] = []
        if linha.get('AproveitamentoComponente.registros_historico'):
            for identificador_externo in linha.get('AproveitamentoComponente.registros_historico', '').strip().split(','):
                try:
                    registro_historico = RegistroHistorico.objects.get(
                        matricula_periodo__aluno_id=aluno_id, identificador_externo=identificador_externo.strip()
                    )
                    registro['registros_historico'].append(registro_historico)

                except RegistroHistorico.DoesNotExist:
                    erros.append(f'Registro Histórico não encontrado para o identificador externo {identificador_externo}.')
                except RegistroHistorico.MultipleObjectsReturned:
                    erros.append(
                        f'Foram encontrados múltiplos registros históricos com o identificador externo {identificador_externo} na matrícula/período do aluno {aluno_id}.'
                    )
            if not registro['registros_historico']:
                erros.append(f'Nenhum registro histórico encontrado para os valores {linha.get("AproveitamentoComponente.registros_historico")}.')
        else:
            erros.append('O campo AproveitamentoComponente.registros_historico é obrigatório e não pode estar vazio.')

    except Exception as e:
        erros.append(str(e))

    return registro, erros


def validar_matricula(linha):
    erros = []
    registro = {}

    try:
        matricula = linha.get('Aluno.matricula', '').strip()
        registro['aluno_id'] = validar_modelo(matricula, Aluno, 'Aluno.matricula', campo_modelo='matricula', erros=erros)

        if Aluno.objects.filter(id=registro['aluno_id'], data_integralizacao__isnull=True).exists():
            erros.append(f'O aluno {matricula} não foi integralizado.')

        if Aluno.objects.filter(id=registro['aluno_id'], matriz__estrutura__isnull=True).exists():
            erros.append(f'A matriz do aluno {matricula} não possui estrutura de curso.')

    except Exception as e:
        erros.append(str(e))

    return registro, erros


def validar_naturalidade(valor, nome_campo, obrigatorio=True, erros=None, raise_exception=False, ignorar_obrigatorios=False):
    if obrigatorio and not ignorar_obrigatorios and not valor:
        erro = f'O campo {nome_campo} é obrigatório e não pode estar vazio.'
        return handle_error(erro, erros, raise_exception)
    elif not valor:
        return None

    result = None
    try:
        codigo = int(valor)
        result = Cidade.objects.filter(codigo=codigo).first()
    except ValueError:
        try:
            cidade, pais = valor.split('/')
            result = Cidade.objects.filter(nome=cidade, pais__sigla=pais).first()
        except Exception:
            erro = f'O campo {nome_campo} requer um valor válido. "{valor}" foi informado.'
            return handle_error(erro, erros, raise_exception)
    except Exception:
        erro = f'O campo {nome_campo} requer um valor válido. "{valor}" foi informado.'
        return handle_error(erro, erros, raise_exception)
    return result and result.id


def validar_nota(valor: str | float, nome_campo: str = '', erros: list[str] | None = None, raise_exception: bool = False) -> int | None:
    """
    Valida se o valor é um inteiro e opcionalmente se está dentro de um intervalo.

    :param valor: O valor do campo a ser validado.
    :param nome_campo: O nome do campo, utilizado para mensagens de erro.
    :param erros: Lista para acumular mensagens de erro.
    :param raise_exception: Se True, lança uma exceção imediatamente quando um erro é encontrado.
    :return: O valor inteiro validado ou None.
    """

    if isinstance(valor, float):
        if settings.NOTA_DECIMAL:
            valor = f'{valor:.2f}' if settings.CASA_DECIMAL == 2 else f'{valor:.1f}'
        else:
            erro = f'A nota informada no {nome_campo} deve ser um número inteiro. "{valor}" foi informado.'
            return handle_error(erro, erros, raise_exception)
    elif isinstance(valor, str):
        valor = valor.strip()
    else:
        valor = str(valor)

    if valor == '':
        return None
    min_val = 0
    max_val = 1000 if settings.NOTA_DECIMAL and settings.CASA_DECIMAL == 2 else 100
    if not settings.NOTA_DECIMAL and not valor.isdigit():
        erro = f'A nota informada no {nome_campo} deve ser um número inteiro. "{valor}" foi informado.'
        return handle_error(erro, erros, raise_exception)

    # O try cobre só a conversão: o ValueError de handle_error não pode ser recapturado (#17458).
    try:
        valor_int = int(valor.replace(',', '').replace('.', '')) if settings.NOTA_DECIMAL else int(valor)
    except ValueError:
        erro = f'Ocorreu um erro na conversão do campo {nome_campo}. "{valor}" foi informado.'
        return handle_error(erro, erros, raise_exception)

    if valor_int < min_val or valor_int > max_val:
        if settings.NOTA_DECIMAL:
            max_val = 10
        msg_complemento = f' com {settings.CASA_DECIMAL} casas decimais' if settings.NOTA_DECIMAL else ''
        erro = f'O campo {nome_campo} deve estar entre {min_val} e {max_val}{msg_complemento}. Valor informado: {valor} ({valor_int}).'
        return handle_error(erro, erros, raise_exception)
    return valor_int


def validar_outros_professores(valor):
    titulacoes_validas = {'Graduado', 'Graduada', 'Especialista', 'Mestre', 'Mestra', 'Doutor', 'Doutora', 'Pós-Doutor', 'Pós-Doutora'}

    # Divide por ; e remove espaços extras
    blocos = [bloco.strip() for bloco in valor.strip().split(';') if bloco.strip()]

    for bloco in blocos:
        if '|' not in bloco:
            return 'O Separador "|" não foi informado.'  # Falta separador
        nome, titulacao = map(str.strip, bloco.split('|', 1))

        # Verifica se nome e titulação estão preenchidos corretamente
        if not nome or not titulacao:
            return 'Nome ou titulação não informados corretamente.'
        if titulacao not in titulacoes_validas:
            return 'Titulação inválida. As opções válidas são: ' + ', '.join(titulacoes_validas)
    return ''
