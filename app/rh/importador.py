import datetime as data
import logging
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

import tqdm
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from sentry_sdk import capture_exception

from comum.management.commands.preencher_iso_paises import ISO_ALFA3_POR_CODIGO_SIAPE
from djtools.utils import (
    cache_queryset,
    format_telefone,
    mask_cpf,
    normalizar_nome_proprio,
    running_tests,
    strptime_date_or_default,
    strptime_or_default,
)
from rh.utils import extrai_matricula

log = logging.getLogger(__name__)

ContentType = apps.get_model('contenttypes.ContentType')
Configuracao = apps.get_model('comum', 'configuracao')
EstadoCivil = apps.get_model('comum', 'estadocivil')
Log = apps.get_model('comum', 'log')
Pais = apps.get_model('comum', 'pais')
Municipio = apps.get_model('comum', 'municipio')
PessoaEndereco = apps.get_model('comum', 'pessoaendereco')
PessoaTelefone = apps.get_model('comum', 'pessoatelefone')
Ano = apps.get_model('comum', 'ano')
Raca = apps.get_model('comum', 'raca')

if 'edu' in settings.INSTALLED_APPS:
    Cidade = apps.get_model('edu', 'cidade')
    Estado = apps.get_model('edu', 'estado')

Atividade = apps.get_model('rh', 'atividade')
Afastamento = apps.get_model('rh', 'afastamentosiape')
Banco = apps.get_model('rh', 'banco')
CargoClasse = apps.get_model('rh', 'cargoclasse')
CargoEmprego = apps.get_model('rh', 'cargoemprego')
CargoEmpregoPendente = apps.get_model('rh', 'cargoempregopendente')
DiplomaLegal = apps.get_model('rh', 'diplomalegal')
Funcao = apps.get_model('rh', 'funcao')
GrupoCargoEmprego = apps.get_model('rh', 'grupocargoemprego')
GrupoOcorrencia = apps.get_model('rh', 'grupoocorrencia')
JornadaTrabalho = apps.get_model('rh', 'jornadatrabalho')
NivelEscolaridade = apps.get_model('rh', 'nivelescolaridade')
Ocorrencia = apps.get_model('rh', 'ocorrencia')
PessoaFisica = apps.get_model('rh', 'pessoafisica')
RegimeJuridico = apps.get_model('rh', 'regimejuridico')
Servidor = apps.get_model('rh', 'servidor')
ServidorOcorrencia = apps.get_model('rh', 'servidorocorrencia')
ServidorReativacaoTemporaria = apps.get_model('rh', 'servidorreativacaotemporaria')
ServidorAfastamento = apps.get_model('rh', 'servidorafastamento')
Setor = apps.get_model('rh', 'setor')
Situacao = apps.get_model('rh', 'situacao')
SubgrupoOcorrencia = apps.get_model('rh', 'subgrupoocorrencia')
Titulacao = apps.get_model('rh', 'titulacao')
Deficiencia = apps.get_model('rh', 'deficiencia')
if 'contracheques' in settings.INSTALLED_APPS:
    Rubrica = apps.get_model('contracheques', 'rubrica', None)

if 'ferias' in settings.INSTALLED_APPS:
    Ferias = apps.get_model('ferias', 'ferias')
    InterrupcaoFerias = apps.get_model('ferias', 'interrupcaoferias')

ServidorFuncaoHistorico = apps.get_model('rh', 'servidorfuncaohistorico')
ServidorSetorHistorico = apps.get_model('rh', 'servidorsetorhistorico')

Pessoa = apps.get_model('rh', 'pessoa')
ServidorSetorLotacaoHistorico = apps.get_model('rh', 'servidorsetorlotacaohistorico')

PCA = apps.get_model('rh', 'pca')
PosicionamentoPCA = apps.get_model('rh', 'posicionamentopca')
JornadaTrabalhoPCA = apps.get_model('rh', 'jornadatrabalhopca')
FormaProvimentoVacancia = apps.get_model('rh', 'formaprovimentovacancia')
RegimeJuridicoPCA = apps.get_model('rh', 'regimejuridicopca')
ExcecaoDado = apps.get_model('rh', 'ExcecaoDado')
Vinculo = apps.get_model('comum', 'Vinculo')
TipoExtracao = __import__('rh.enums', fromlist=['TipoExtracao']).TipoExtracao


class ImportadorSIAPE:
    def __init__(self) -> None:
        #
        # carregando campos de exceção de atualização do extrator
        excecoes_atualizacao = {}
        for i in ExcecaoDado.objects.filter(tipo_extracao=TipoExtracao.TIPO_EXTRATOR_SIAPE):
            if i.servidor.matricula not in excecoes_atualizacao:
                excecoes_atualizacao[i.servidor.matricula] = list(i.campos.values_list('campo', flat=True))
        self.excecoes_atualizacao = excecoes_atualizacao
        #
        # codigos de cargo do SIAPE sem correspondente no SUAP, acumulados ao longo de toda a
        # execucao: o layout de servidores pode vir quebrado em varios arquivos
        self.cargos_emprego_pendentes = {}

    def _decrescimo_data(self, data, dias):
        if data:
            return data - relativedelta(days=dias)
        return None

    def _get_map_layout_functions(self):
        layouts = {
            'atividades': self.importar_atividades,
            'afastamentos': self.importar_afastamentos,
            'bancos': self.importar_bancos,
            'grupo_cargo_emprego': self.importar_grupo_cargo_emprego,
            'cargo_emprego': self.importar_cargo_emprego,
            'cargo_classe': self.importar_cargo_classe,
            'diploma_legal': self.importar_diploma_legal,
            'funcoes': self.importar_funcoes,
            'jornada_trabalho': self.importar_jornada_trabalho,
            'pais': self.importar_pais,
            'nivel_escolaridade': self.importar_nivel_escolaridade,
            'regime_juridico': self.importar_regime_juridico,
            'rubrica': self.importar_rubrica,
            'situacao_servidor': self.importar_situacao_servidor,
            'uo': self.importar_uo,
            'estado_civil': self.importar_estado_civil,
            'grupo_ocorrencia': self.importar_grupo_ocorrencia,
            'ocorrencia': self.importar_ocorrencia,
            'titulacoes': self.importar_titulacoes,
            'servidor1': self.importar_servidor1,
            'servidor2': self.importar_servidor2,
            'servidor3': self.importar_servidor3,
            'servidor4': self.importar_servidor4,
            'servidor5': self.importar_servidor5,
            'email_telefone_servidor': self.importar_telefone_email_servidor,
            'servidorafastamentos': self.importar_servidor_afastamentos,
            'historico_ferias': self.importar_historico_ferias,
            'ferias': self.importar_ferias,
            'historico_afastamento': self.importar_historico_afastamento,
            'historico_funcao': self.importar_historico_funcao,
            'historico_setor_siape': self.importar_historico_setor_siape,
            'servidor_matriculas': self.importar_servidor_matriculas,
            'pca': self.importar_pca,
            'posicionamento_pca': self.importar_posicionamento_pca,
        }
        return layouts

    def importar_afastamentos(self, itens):
        for i in itens:
            # foi percebido que alguns tipos de afastamentos estão vindo sem a valor de IT-TP-AFASTAMENTO ou com valores que não são inteiros
            # não é possível cadastrar no suap um afastamento nessas condições
            # TODO estudar o motivo ^^^^^^
            try:
                if i['IT-TP-AFASTAMENTO'] and i['IT-TP-AFASTAMENTO'].isdigit():
                    codigo = i['IT-CO-AFASTAMENTO']

                    kwargs = {
                        'nome': i['IT-NO-AFASTAMENTO'].strip(),
                        'sigla': i['IT-SG-AFASTAMENTO'].strip(),
                        'tipo': i['IT-TP-AFASTAMENTO'].strip(),
                        'interrompe_pagamento': i['IT-IN-EXCLUI-PAGAMENTO'] == 'S',
                        'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1',
                    }
                    Afastamento.objects.update_or_create(codigo=codigo, defaults=kwargs)
                else:
                    log.info(
                        f'>>> ERRO DE REGISTRO: não foi possível inserir o dicionário {i}, pois o campo IT-TP-AFASTAMENTO não está no padrão aceitável.'
                    )
            except Exception as ex:
                capture_exception(ex)
                log.info(f'>>> ERRO: {ex}')
                continue

    # Esse metodo importa do arquivo Atividades do SIAPE para o SUAP... em algum momento de alguma extracao foi usado a funcao strip no IT-CO-ATIVIDADE
    #    causando duplicacao em registros na tabela.
    #    Essa entidade nao tem sobrescrita no metodo .save()

    def importar_atividades(self, itens):
        for i in itens:
            codigo = i['IT-CO-ATIVIDADE']
            kwargs = {'nome': i['IT-NO-ATIVIDADE'].strip(), 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'}
            Atividade.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_bancos(self, itens):
        for i in itens:
            codigo = i['IT-CO-BANCO']
            kwargs = {'nome': i['IT-NO-BANCO'].strip(), 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1', 'sigla': i['IT-SG-BANCO'].strip()}
            Banco.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_grupo_cargo_emprego(self, itens):
        for i in itens:
            codigo = i['IT-CO-GRUPO-CARGO-EMPREGO']
            kwargs = {
                'nome': i['IT-NO-GRUPO-CARGO-EMPREGO'].strip(),
                'sigla': i['IT-SG-GRUPO-CARGO-EMPREGO'].strip(),
                'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1',
            }
            if 'MAG' in i['IT-NO-GRUPO-CARGO-EMPREGO'].strip():
                kwargs['categoria'] = 'docente'

            GrupoCargoEmprego.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_cargo_emprego(self, itens):
        grupo_cargo_emprego_cache = cache_queryset(GrupoCargoEmprego.objects.all(), 'codigo', 'id')
        for i in itens:
            codigo = i['GR-IDEN-CARGO-EMPREGO']
            kwargs = {
                'grupo_cargo_emprego_id': grupo_cargo_emprego_cache[i['GR-IDEN-CARGO-EMPREGO'][:3]],
                'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1',
                'nome': i['IT-NO-CARGO-EMPREGO'].strip(),
                'sigla_escolaridade': i['IT-SG-ESCOLARIDADE'].strip(),
                # o registro passa a ser confirmado pelo SIAPE; cargos cadastrados à mão nascem
                # com cargo_siape=False e são reconciliados aqui, sem duplicar (a chave é o código)
                'cargo_siape': True,
            }
            CargoEmprego.objects.update_or_create(codigo=codigo, defaults=kwargs)

        # a tabela de cargos chegou: as pendências desses códigos deixam de existir.
        # Em lote — um DELETE por cargo custaria milhares de queries por importação.
        CargoEmpregoPendente.objects.filter(codigo__in=[i['GR-IDEN-CARGO-EMPREGO'] for i in itens]).delete()

    def importar_cargo_classe(self, itens):
        for i in itens:
            codigo = i['IT-CO-CLASSE']
            kwargs = {'nome': i['IT-NO-CLASSE'].strip(), 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'}
            CargoClasse.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_diploma_legal(self, itens):
        for i in itens:
            codigo = i['IT-CO-DIPLOMA-LEGAL']
            kwargs = {
                'nome': i['IT-NO-DIPLOMA-LEGAL'].strip(),
                'sigla': i['IT-SG-DIPLOMA-LEGAL'].strip(),
                'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1',
            }
            DiplomaLegal.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_funcoes(self, itens):
        for i in itens:
            codigo = i['IT-SG-FUNCAO'].strip()
            kwargs = {'nome': i['IT-NO-FUNCAO'].strip(), 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'}
            Funcao.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_jornada_trabalho(self, itens):
        for i in itens:
            codigo = i['IT-CO-JORNADA-TRABALHO']
            kwargs = {'nome': i['IT-NO-JORNADA-TRABALHO'].strip(), 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'}
            JornadaTrabalho.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_nivel_escolaridade(self, itens):
        for i in itens:
            codigo = i['IT-CO-NIVEL-ESCOLARIDADE']
            kwargs = {'nome': i['IT-NO-NIVEL-ESCOLARIDADE'].strip(), 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'}
            NivelEscolaridade.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_pais(self, itens: Iterable[dict[str, str]]) -> None:
        for i in itens:
            codigo = i['IT-CO-PAIS']
            kwargs = {
                'nome': i['IT-NO-PAIS'].strip(),
                'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1',
                'equiparado': i['IT-IN-PAIS-EQUIPARADO'] == 'S',
            }
            # o alfa-3 só no país criado: o que já existe não muda, a correção manual no admin vale
            Pais.objects.update_or_create(
                codigo=codigo, defaults=kwargs, create_defaults={**kwargs, 'iso_alfa3': ISO_ALFA3_POR_CODIGO_SIAPE.get(codigo, '')}
            )

    def importar_regime_juridico(self, itens):
        for i in itens:
            sigla = i['IT-SG-REGIME-JURIDICO']
            kwargs = {'nome': i['IT-NO-REGIME-JURIDICO'].strip(), 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'}
            RegimeJuridico.objects.update_or_create(sigla=sigla, defaults=kwargs)

    def importar_rubrica(self, itens):
        if 'contracheques' in settings.INSTALLED_APPS:
            for i in itens:
                codigo = i['IT-CO-RUBRICA']
                kwargs = {'nome': i['IT-NO-RUBRICA'].strip(), 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'}
                Rubrica.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_estado_civil(self, itens):
        for i in itens:
            codigo_siape = i['IT-CO-ESTADO-CIVIL']
            kwargs = {'nome': i['IT-NO-ESTADO-CIVIL'], 'ativo': i['IT-IN-STATUS-REGISTRO-TABELA'] == '0'}
            EstadoCivil.objects.update_or_create(codigo_siape=codigo_siape, defaults=kwargs)

    def importar_grupo_ocorrencia(self, itens):
        for i in itens:
            codigo = i['IT-CO-GRUPO-OCORRENCIA']
            kwargs = {'nome': i['IT-NO-GRUPO-OCORRENCIA'], 'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'}
            GrupoOcorrencia.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_ocorrencia(self, itens):
        grupo_ocorrencia_cache = cache_queryset(GrupoOcorrencia.objects.all(), 'codigo', 'id')
        for i in itens:
            codigo = i['GR-IDEN-OCORRENCIA']
            kwargs = {
                'nome': i['IT-NO-OCORRENCIA'],
                'grupo_ocorrencia': GrupoOcorrencia(pk=grupo_ocorrencia_cache[i['GR-IDEN-OCORRENCIA'][0:2]]),
                'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1',
                'interrompe_pagamento': i['IT-IN-OCORRENCIA-EXCL-PGTO'] == 'S',
            }
            Ocorrencia.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_situacao_servidor(self, itens):
        for i in itens:
            codigo = i['IT-CO-SITUACAO-SERVIDOR']
            kwargs = {
                'nome': i['IT-NO-SITUACAO-SERVIDOR'].strip(),
                'nome_siape': i['IT-NO-SITUACAO-SERVIDOR'].strip(),
                'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1',
            }
            Situacao.objects.update_or_create(codigo=codigo, defaults=kwargs)

    def importar_uo(self, itens):
        espelhar_setor = False
        # Se for a primeira vez em que o setor vai ser cria uma arvore de setores SUAP identica a arvore SIAPE.
        # Pressupõe-se que o usuario deseja árvores idênticas apenas para uma primeira importação. A partir dai, ele
        # começa a trabalhar na árvore SUAP editando-a independentemente. Poupa trabalho no cadastro de setores.
        if settings.TIPO_ARVORE_SETORES == 'SUAP' and Setor.objects.suap().all().count() == 0:
            espelhar_setor = True

        # ajustes de setores dentro da reitoria (corrigindo o problema de setores que estão diretamente ligados ao orgão cod. 000999999)
        ajustar_setores_na_reitoria = Configuracao.get_valor_por_chave('rh', 'ajustar_setores_na_reitoria')

        # Primeiro salve os setores.
        for i in itens:
            codigo = i['GR-IDENTIFICACAO-UORG'][-9:]
            sigla = i['IT-SG-UNIDADE-ORGANIZACIONAL'].strip()
            #
            _valor_cod_siorg = i['IT-CO-UORG-SIORG'].strip()
            codigo_siorg = _valor_cod_siorg.lstrip('0') if _valor_cod_siorg and _valor_cod_siorg != '0000000000' else ''
            #
            kwargs = {
                'excluido': i['IT-IN-STATUS-REGISTRO-TABELA'] == '1',
                'nome': i['IT-NO-UNIDADE-ORGANIZACIONAL'].strip(),
                'codigo_siorg': codigo_siorg,
            }
            kwargs_siape = kwargs
            kwargs_siape['sigla'] = sigla
            Setor.objects.siape().update_or_create(codigo=codigo, defaults=kwargs_siape)
            if espelhar_setor:
                Setor.objects.suap_ativos().update_or_create(sigla=sigla, defaults=kwargs)

        # Depois inclua os vinculos separadamente para nao correr os risco de fazer
        # referencia a um setor que ainda nao existe
        for i in itens:
            excluido = i['IT-IN-STATUS-REGISTRO-TABELA'] == '1'
            if not excluido:
                codigo = i['GR-IDENTIFICACAO-UORG'][-9:]
                nome = i['IT-NO-UNIDADE-ORGANIZACIONAL'].strip()
                sigla = i['IT-SG-UNIDADE-ORGANIZACIONAL'].strip()
                setor = Setor.objects.siape().get(codigo=codigo, nome=nome, sigla=sigla)

                if espelhar_setor:
                    setor_espelhado = Setor.objects.suap().get(nome=nome, sigla=sigla)

                vinculo = i['IT-CO-UORG-VINCULACAO'].strip()[-9:]

                # correção da mudança de árvore de setor ocasionado pela migração do siorg
                if ajustar_setores_na_reitoria:
                    sigla_re = Configuracao.get_valor_por_chave('comum', 'reitoria_sigla')
                    codigo_uorg = Configuracao.get_valor_por_chave('rh', 'codigo_uorg_vinculacao') or '000000001'
                    if vinculo == codigo_uorg and sigla != sigla_re:
                        s = Setor.objects.siape().get(sigla=sigla_re)
                        # ajustando o vinculo de todos os setores, alterando o vinculo de 1 para o vinculo da reitoria
                        vinculo = s.codigo

                if vinculo == '000999999' or int(vinculo) == 0:
                    superior = None
                    if espelhar_setor:
                        superior_espelhado = None
                else:
                    superior = Setor.objects.siape().get(codigo=vinculo)
                    pai_do_superior = superior.superior
                    if espelhar_setor:
                        if pai_do_superior:
                            superior_espelhado = Setor.objects.suap().get(sigla=superior.sigla, superior__sigla=pai_do_superior.sigla)
                        else:
                            superior_espelhado = Setor.objects.suap().get(sigla=superior.sigla)

                setor.superior = superior
                setor.save()
                if espelhar_setor:
                    setor_espelhado.superior = superior_espelhado
                    setor_espelhado.save()

    def calc_caches(self, servidores=True, force_recache=False):
        if force_recache or running_tests():
            force_recache = True

        if force_recache or servidores or not hasattr(self, 'servidores_cache'):
            self.servidores_cache = cache_queryset(Servidor.objects.all(), 'matricula', 'id')

        if force_recache or (not hasattr(self, 'has_cache') or not self.has_cache):
            self.has_cache = True
            self.estado_civil_cache = cache_queryset(EstadoCivil.objects.all(), 'codigo_siape', 'id')
            self.regime_juridico_cache = cache_queryset(RegimeJuridico.objects.all(), 'sigla', 'id')
            self.nivel_escolaridade_cache = cache_queryset(NivelEscolaridade.objects.all(), 'codigo', 'id')
            self.jornada_de_trabalho_cache = cache_queryset(JornadaTrabalho.objects.all(), 'codigo', 'id')
            self.atividades_cache = cache_queryset(Atividade.objects.all(), 'codigo', 'id')
            self.funcoes_cache = cache_queryset(Funcao.objects.all(), 'codigo', 'id')
            self.bancos_cache = cache_queryset(Banco.objects.all(), 'codigo', 'id')
            self.situacoes_cache = cache_queryset(Situacao.objects.all(), 'codigo', 'id')
            self.pais_cache = cache_queryset(Pais.objects.all(), 'codigo', 'id')
            self.setores_cache = cache_queryset(Setor.objects.siape().all(), 'codigo', 'id')
            self.grupo_cargo_emprego_cache = cache_queryset(GrupoCargoEmprego.objects.all(), 'codigo', 'id')
            self.cargo_emprego_cache = cache_queryset(CargoEmprego.objects.all(), 'codigo', 'id')
            self.cargo_classe_cache = cache_queryset(CargoClasse.objects.all(), 'codigo', 'id')
            self.grupo_ocorrencia_cache = cache_queryset(GrupoOcorrencia.objects.all(), 'codigo', 'id')
            self.ocorrencia_cache = cache_queryset(Ocorrencia.objects.all(), 'codigo', 'id')
            self.diploma_legal_cache = cache_queryset(DiplomaLegal.objects.all(), 'codigo', 'id')
            self.titulacao_cache = cache_queryset(Titulacao.objects.all(), 'codigo', 'id')
            self.raca_cache = cache_queryset(Raca.objects.all(), 'codigo_siape', 'id')
            self.deficiencia_cache = cache_queryset(Deficiencia.objects.all(), 'codigo', 'id')
            self.afastamentos_cache = cache_queryset(Afastamento.objects.all(), 'codigo', 'id')

    # INICIAR IMPORTACAO SERVIDOR 1
    def importar_servidor1(self, itens: Iterable[dict], registrar_pendentes: bool = True) -> None:
        self.calc_caches()
        for i in tqdm.tqdm(itens):
            self._importar_registro_servidor1(i)

        # o motor por lotes soma os acumuladores de todos os lotes e grava uma vez no fim do layout
        if registrar_pendentes:
            self._registrar_cargos_emprego_pendentes()

    def _importar_registro_servidor1(self, i: dict) -> None:
        matricula = nome_servidor = ''
        try:
            matricula = extrai_matricula(i['GR-MATRICULA'])
            nome_servidor = normalizar_nome_proprio(i['IT-NO-SERVIDOR'])
            servidor = Servidor.update_or_create(self._args_servidor1(i, matricula, nome_servidor))['servidor']
            v = servidor.get_vinculo()
            if v:
                v.sistema_origem = 'SIAPE'
                v.save(update_fields=['sistema_origem'])
            self._atualizar_ocorrencia_exclusao(servidor, i)
            # self._atualizar_ocorrencia_afastamento(servidor, i)
            self._atualizar_ocorrencia_inatividade(servidor, i)

        except Exception as ex:
            capture_exception(ex)
            log.warning(f'Erro ao processar dados: [{matricula}] {nome_servidor}: \n Error: {ex} \n Array: {i}')

    def _args_servidor1(self, i: dict, matricula: str, nome_servidor: str) -> dict:
        args = {
            'matricula': matricula,
            'situacao_id': self.situacoes_cache[i['IT-CO-SITUACAO-SERVIDOR']],
            'pessoa_fisica': self._pessoa_fisica_servidor1(i, nome_servidor),
            'data_exclusao_instituidor': strptime_or_default(i['IT-DA-EXCLUSAO-INSTITUIDOR'], '%Y%m%d'),
        }

        if i['IT-SG-REGIME-JURIDICO'].strip():
            args['regime_juridico_id'] = self.regime_juridico_cache.get(i['IT-SG-REGIME-JURIDICO'], None)

        # Equivalente ao metodo atualizar lotação
        if int(i['IT-CO-UORG-LOTACAO-SERVIDOR']):
            args['setor_lotacao_id'] = self.setores_cache.get(i['IT-CO-UORG-LOTACAO-SERVIDOR'], None)
            args['setor_lotacao_data_ocupacao'] = strptime_or_default(i['IT-DA-LOTACAO'], '%Y%m%d')
        else:
            args['setor_lotacao'] = None
            args['setor_lotacao_data_ocupacao'] = None

        # Equivalente ao atualizar cargo emprego
        if int(i['IT-CO-GRUPO-CARGO-EMPREGO']):
            args.update(self._cargo_emprego_servidor1(i))

        args['nivel_padrao'] = self._nivel_padrao_servidor1(i)
        return args

    def _pessoa_fisica_servidor1(self, i: dict, nome_servidor: str) -> dict:
        pessoa_fisica = {
            'cpf': mask_cpf(i['IT-NU-CPF']),
            'nome': nome_servidor,
            'nome_registro': nome_servidor,
            'nome_mae': normalizar_nome_proprio(i['IT-NO-MAE']),
            'pis_pasep': i['IT-NU-PIS-PASEP'],
            'pagto_agencia': i['IT-CO-AGENCIA-BANCARIA-PGTO-SERV'],
            'pagto_ccor': i['IT-NU-CCOR-PGTO-SERVIDOR'],
        }

        if int(i['IT-CO-ESTADO-CIVIL']):
            pessoa_fisica['estado_civil_id'] = self.estado_civil_cache.get(i['IT-CO-ESTADO-CIVIL'], None)

        if i['IT-CO-BANCO-PGTO-SERVIDOR'] and int(i['IT-CO-BANCO-PGTO-SERVIDOR']):
            pessoa_fisica['pagto_banco_id'] = self.bancos_cache.get(i['IT-CO-BANCO-PGTO-SERVIDOR'], None)

        if i['IT-CO-NACIONALIDADE'] and int(i['IT-CO-NACIONALIDADE']):
            pessoa_fisica['nacionalidade'] = int(i['IT-CO-NACIONALIDADE'])

        # Preenche o país de origem
        if i['IT-CO-PAIS'] and int(i['IT-CO-PAIS']):
            pessoa_fisica['pais_origem_id'] = self.pais_cache.get(i['IT-CO-PAIS'], None)
        return pessoa_fisica

    def _cargo_emprego_servidor1(self, i: dict) -> dict:
        codigo_cargo_siape = i['IT-CO-GRUPO-CARGO-EMPREGO'] + i['IT-CO-CARGO-EMPREGO']
        cargo_emprego_id = self.cargo_emprego_cache.get(codigo_cargo_siape, None)
        if not cargo_emprego_id:
            self._contabilizar_cargo_emprego_pendente(codigo_cargo_siape, i['IT-CO-GRUPO-CARGO-EMPREGO'])
        return {
            'cargo_emprego_id': cargo_emprego_id,
            'cargo_classe_id': self.cargo_classe_cache.get(i['IT-CO-CLASSE'], None),
            'cargo_emprego_data_ocupacao': strptime_or_default(i['IT-DA-OCUPACAO-CARGO-EMPREGO'], '%Y%m%d'),
            'cargo_emprego_data_saida': strptime_or_default(i['IT-DA-SAIDA-CARGO-EMPREGO'], '%Y%m%d'),
        }

    @staticmethod
    def _nivel_padrao_servidor1(i: dict) -> str:
        valor = i['IT-CO-PADRAO'] if i['IT-CO-PADRAO'].isdigit() else i['IT-CO-NIVEL']
        try:
            valor = int(valor)
        except Exception:
            pass
        return str(valor)

    def _contabilizar_cargo_emprego_pendente(self, codigo_cargo: str, codigo_grupo: str) -> None:
        """Acumula em memória um código de cargo do SIAPE que não existe no SUAP.

        A gravação é adiada para não sofrer um UPDATE por servidor; quando acontece depende de
        quem chama `importar_servidor1`. Via `run()` (serial, uma instância por arquivo), é ao
        fim de cada chamada — uma vez por arquivo. No motor paralelo por lotes
        (`ExecucaoPorLotes`), cada lote roda numa instância própria com `registrar_pendentes=False`
        e nunca grava sozinho: os acumuladores de todos os lotes do layout são somados
        (`PendenciasDeCargo`) e gravados uma única vez, ao fim do layout.

        Args:
            codigo_cargo: Código do cargo no SIAPE (3 dígitos do grupo + 3 do cargo).
            codigo_grupo: Código do grupo de cargo emprego no SIAPE.
        """
        pendencia = self.cargos_emprego_pendentes.setdefault(codigo_cargo, {'grupo_codigo': codigo_grupo, 'qtd_servidores': 0})
        pendencia['qtd_servidores'] += 1

    def _registrar_cargos_emprego_pendentes(self) -> None:
        """Grava as pendências acumuladas na instância, uma linha por código de cargo.

        Via `run()` (serial), a instância é uma por arquivo e o método é chamado ao fim de cada
        `importar_servidor1`: o layout pode vir quebrado em vários arquivos e cada gravação
        regrava o total já visto pela instância até ali. No motor paralelo por lotes, cada lote
        roda na sua própria instância e nunca chama este método (`registrar_pendentes=False`);
        quem chama é `PendenciasDeCargo.registrar`, uma única vez ao fim do layout, numa
        instância à parte que recebeu a soma dos acumuladores de todos os lotes.

        Serve de roteiro para a Gestão de Pessoas: cadastrando o cargo com o mesmo código, a
        extração seguinte religa os servidores automaticamente.
        """
        for codigo, dados in self.cargos_emprego_pendentes.items():
            CargoEmpregoPendente.objects.update_or_create(codigo=codigo, defaults=dados)

    def _atualizar_ocorrencia_inatividade(self, servidor, item):
        if int(item['IT-CO-GRUPO-OCOR-INATIVIDADE']):
            kwargs = {
                'diploma_legal_data': strptime_or_default(item['IT-DA-PUBL-DIPL-INATIVIDADE'], '%Y%m%d'),
                'diploma_legal_num': item['IT-NU-DIPL-INATIVIDADE'],
            }
            if int(item['IT-CO-DIPL-INATIVIDADE']):
                kwargs['diploma_legal_id'] = self.diploma_legal_cache[item['IT-CO-DIPL-INATIVIDADE']]
            else:
                kwargs['diploma_legal_id'] = None

            ocorrencia_id = self.ocorrencia_cache[item['IT-CO-GRUPO-OCOR-INATIVIDADE'] + item['IT-CO-OCOR-INATIVIDADE']]
            data = strptime_or_default(item['IT-DA-OCOR-INATIVIDADE-SERV'], '%Y%m%d')

            ok = False
            try:
                ServidorOcorrencia.objects.update_or_create(servidor=servidor, ocorrencia_id=ocorrencia_id, data=data, defaults=kwargs)
                ok = True
            except MultipleObjectsReturned:
                ServidorOcorrencia.objects.filter(servidor=servidor, ocorrencia_id=ocorrencia_id, data=data).delete()
                ok = False
            if not ok:
                ServidorOcorrencia.objects.update_or_create(servidor=servidor, ocorrencia_id=ocorrencia_id, data=data, defaults=kwargs)

    def _atualizar_ocorrencia_exclusao(self, servidor, item):
        """Atualiza a ocorrência de exclusão
        Retorna uma tupla de  (servidorocorrencia, novo) onde novo é um boolean
        especificando se servidorocorrencia foi criado
        Se houver uma ocorrencia de exclusao por falta de recadastramento, mas não vier uma exclusão em item,
        o servidor será reativado. Isso é comum para os casos em que um aposentado volta a fazer o recadastrado.
        """

        def excluir_servidor(servidor, item):
            subgrupo = SubgrupoOcorrencia.objects.get_or_create(descricao='EXCLUSAO')[0]
            kwargs = {
                'diploma_legal_data': strptime_or_default(item['IT-DA-PUBL-DIPL-EXCLUSAO'], '%Y%m%d'),
                'diploma_legal_num': item['IT-NU-DIPL-EXCLUSAO'],
            }

            kwargs['diploma_legal_id'] = self.diploma_legal_cache.get(item['IT-CO-DIPL-EXCLUSAO'], None)
            ocorrencia_id = self.ocorrencia_cache[item['IT-CO-GRUPO-OCOR-EXCLUSAO'] + item['IT-CO-OCOR-EXCLUSAO']]
            data = strptime_or_default(item['IT-DA-OCOR-EXCLUSAO-SERV'], '%Y%m%d')

            try:
                ServidorOcorrencia.objects.update_or_create(
                    servidor=servidor, ocorrencia_id=ocorrencia_id, data=data, subgrupo=subgrupo, defaults=kwargs
                )
                ok = True
            except MultipleObjectsReturned:
                ServidorOcorrencia.objects.update_or_create(servidor=servidor, ocorrencia_id=ocorrencia_id, data=data, subgrupo=subgrupo).delete()
                ok = False
            if not ok:
                ServidorOcorrencia.objects.update_or_create(
                    servidor=servidor, ocorrencia_id=ocorrencia_id, data=data, subgrupo=subgrupo, defaults=kwargs
                )

            tipo_relacionamento_servidor = ContentType.objects.get(app_label='rh', model='servidor')
            Servidor.objects.filter(id=servidor.id).update(ativo=False)
            Vinculo.objects.filter(user=servidor.get_user(), tipo_relacionamento=tipo_relacionamento_servidor).update(ativo=False)

            historico_setores_servidor = ServidorSetorHistorico.objects.filter(servidor=servidor).order_by('-data_inicio_no_setor')
            if historico_setores_servidor.exists():
                setor_mais_atual = historico_setores_servidor[0]
                if not setor_mais_atual.data_fim_no_setor:
                    setor_mais_atual.data_fim_no_setor = data
                    setor_mais_atual.save()

        def reativar_servidor(servidor, item):
            ServidorOcorrencia.objects.filter(servidor=servidor, ocorrencia__nome__unaccent__icontains='falta recadastramento').delete()
            #            Na regra que nos foi passado pelo RH antes um servidor que foi excluido, salvo por falta de recadastramento, nao voltava a ativa com mesma matricula.
            #            Porem foi visto que existem casos de servidores excluidos q voltaram a ativa com mesma matricula
            #            ServidorOcorrencia.objects.filter(servidor=servidor, ocorrencia__grupo_ocorrencia__nome=u'EXCLUSAO').delete()
            Servidor.objects.filter(id=servidor.id).update(ativo=True)

        cod_grupo_ocorrencia_exclusao = int(item['IT-CO-GRUPO-OCOR-EXCLUSAO'])
        # verificando se existe um código de grupo de ocorrência de exclusão e checa se o código não é 0 (zero). Caso o código não seja zero, ou seja
        # existe um código valido de exclusão, chama-se a definição para excluir o servidor no suap.
        if cod_grupo_ocorrencia_exclusao != 0:
            excluir_servidor(servidor, item)

        # verificando se o código de grupo de ocorrência de exclusão é igual a zero e checa se o servidor está como excluído no suap. Caso positivo,
        # reativa o servidor.
        if cod_grupo_ocorrencia_exclusao == 0 and servidor.ativo is False:
            reativar_servidor(servidor, item)

    def _atualizar_ocorrencia_afastamento(self, servidor, item):
        if int(item['IT-CO-GRUPO-OCOR-AFASTAMENTO']):
            kwargs = {
                'data_termino': strptime_or_default(item['IT-DA-TERMINO-OCOR-AFASTAMENTO'], '%Y%m%d'),
                'diploma_legal_data': strptime_or_default(item['IT-DA-PUBL-DIPL-AFASTAMENTO'], '%Y%m%d'),
                'diploma_legal_num': item['IT-NU-DIPL-AFASTAMENTO'],
            }
            data_inicio = strptime_or_default(item['IT-DA-INICIO-OCOR-AFASTAMENTO'], '%Y%m%d')
            if data_inicio > datetime.today():
                return
            kwargs['diploma_legal_id'] = self.diploma_legal_cache.get(item['IT-CO-DIPL-AFASTAMENTO'], None)
            ocorrencia_id = self.ocorrencia_cache[item['IT-CO-GRUPO-OCOR-AFASTAMENTO'] + item['IT-CO-OCOR-AFASTAMENTO']]

            ok = False
            try:
                ServidorOcorrencia.objects.update_or_create(servidor=servidor, ocorrencia_id=ocorrencia_id, data=data_inicio, defaults=kwargs)
                ok = True
            except MultipleObjectsReturned:
                ServidorOcorrencia.objects.filter(servidor=servidor, ocorrencia_id=ocorrencia_id, data=data_inicio).delete()
                ok = False

            if not ok:
                ServidorOcorrencia.objects.update_or_create(servidor=servidor, ocorrencia_id=ocorrencia_id, data=data_inicio, defaults=kwargs)

    def importar_servidor2(self, itens):
        self.calc_caches(servidores=True)
        for i in tqdm.tqdm(itens):
            try:
                servidor_id = self.servidores_cache[extrai_matricula(i['GR-MATRICULA'])]
            except Exception:
                continue
            args = {
                'pk': servidor_id,
                'pessoa_fisica': {
                    'nascimento_data': strptime_or_default(i['IT-DA-NASCIMENTO'], '%Y%m%d'),
                    'sexo': i['IT-CO-SEXO'],
                    'qtde_depend_ir': int(i['IT-QT-DEPENDENTE-IR']),
                    'ctps_numero': i['IT-NU-CARTEIRA-TRABALHO'],
                    'ctps_serie': i['IT-NU-SERIE-CARTEIRA-TRABALHO'],
                    'ctps_uf': i['IT-SG-UF-CTRA-SERVIDOR'].strip(),
                    'ctps_data_prim_emprego': strptime_or_default(i['IT-DA-PRIMEIRO-EMPREGO'], '%Y%m%d'),
                },
                'data_cadastro_siape': strptime_or_default(i['IT-DA-CADASTRAMENTO-SERVIDOR'], '%Y%m%d'),
            }
            if int(i['IT-CO-NIVEL-ESCOLARIDADE']):
                args['nivel_escolaridade_id'] = self.nivel_escolaridade_cache.get(i['IT-CO-NIVEL-ESCOLARIDADE'], None)
            if int(i['IT-CO-JORNADA-TRABALHO']):
                args['jornada_trabalho_id'] = self.jornada_de_trabalho_cache.get(i['IT-CO-JORNADA-TRABALHO'], None)

            # TODO verificar onde adicionar essa informação. ver se pode ser colocada em outros servidores (1,3,4 ou 5)

            # num_processo_aposentadoria = i['IT-NU-PROCESSO-APOSENTADORIA'].strip()
            # if num_processo_aposentadoria.strip('0'):
            #     args['num_processo_aposentadoria'] = num_processo_aposentadoria.lstrip('0')
            # else:
            #     args['num_processo_aposentadoria'] = ''
            # numerador_prop_aposentadoria = int(i['IT-NU-NUMERADOR-PROP'])
            # if numerador_prop_aposentadoria:
            #     args['numerador_prop_aposentadoria'] = numerador_prop_aposentadoria
            # denominador_prop_aposentadoria = i['IT-NU-DENOMINADOR-PROP']
            # if denominador_prop_aposentadoria:
            #     args['denominador_prop_aposentadoria'] = denominador_prop_aposentadoria

            """
            No extrator do SIAPE, a coluna IT-DA-INGRESSO-NOVA-FUNCAO e IT-DA-INGRESSO-FUNCAO sempre vem preenchindo com a data de inicio na função ou nova função,
            ou com zeros quando o servidor nunca teve uma função.
            """
            # nova função
            if int(i['IT-DA-INGRESSO-NOVA-FUNCAO']) > int(i['IT-DA-INGRESSO-FUNCAO']):
                sg_nova_funcao = i['IT-SG-NOVA-FUNCAO'].strip()
                if sg_nova_funcao not in self.funcoes_cache:
                    log.warning(
                        f'Nova função {sg_nova_funcao} do servidor de matrícula {extrai_matricula(i["GR-MATRICULA"])} não encontrada na cache. Verifique se a função existe e se o código está correto.'
                    )
                    continue
                funcao_id = self.funcoes_cache[sg_nova_funcao]
                args['funcao_id'] = funcao_id

                args['funcao_codigo'] = nivel = i['IT-CO-NIVEL-NOVA-FUNCAO'].lstrip('0')
                args['funcao_opcao'] = i['IT-IN-OPCAO-FUNCAO'] == 'S'
                args['funcao_data_ocupacao'] = data_inicio_funcao = strptime_or_default(i['IT-DA-INGRESSO-NOVA-FUNCAO'], '%Y%m%d')
                args['funcao_data_saida'] = data_fim_funcao = self._decrescimo_data(strptime_or_default(i['IT-DA-SAIDA-NOVA-FUNCAO'], '%Y%m%d'), 1)

                args['setor_funcao_id'] = None
                setor_funcao_id = None
                if int(i['IT-CO-UORG-NOVA-FUNCAO']):
                    co_uorg_nova_funcao = i['IT-CO-UORG-NOVA-FUNCAO']
                    if co_uorg_nova_funcao not in self.setores_cache:
                        log.warning(
                            f'Setor {co_uorg_nova_funcao} da nova função do servidor de matrícula {extrai_matricula(i["GR-MATRICULA"])} não encontrado na cache.'
                        )
                    else:
                        args['setor_funcao_id'] = setor_funcao_id = self.setores_cache[co_uorg_nova_funcao]

                args['funcao_atividade_id'] = None
                if int(i['IT-CO-ATIVIDADE-NOVA-FUNCAO']):
                    args['funcao_atividade_id'] = atividade_funcao_id = self.atividades_cache[i['IT-CO-ATIVIDADE-NOVA-FUNCAO']]

                # salvando
                if funcao_id and data_inicio_funcao and setor_funcao_id:
                    args_historicofuncao = {
                        'servidor_id': servidor_id,
                        'data_inicio_funcao': data_inicio_funcao,
                        'nivel': nivel,
                        'data_fim_funcao': data_fim_funcao,
                        'funcao_id': funcao_id,
                        'setor_id': setor_funcao_id,
                        'atividade_id': atividade_funcao_id,
                    }
                    ServidorFuncaoHistorico.objects.update_or_create(
                        servidor__pk=servidor_id, data_inicio_funcao=data_inicio_funcao, defaults=args_historicofuncao
                    )

            # função
            elif int(i['IT-DA-INGRESSO-NOVA-FUNCAO']) < int(i['IT-DA-INGRESSO-FUNCAO']):
                sg_funcao = i['IT-SG-FUNCAO'].strip()
                if sg_funcao not in self.funcoes_cache:
                    log.warning(
                        f'Função {sg_funcao} do servidor de matrícula {extrai_matricula(i["GR-MATRICULA"])} não encontrada na cache. Verifique se a função existe e se o código está correto.'
                    )
                    continue
                if not int(i['IT-DA-SAIDA-FUNCAO']):
                    args['funcao_id'] = funcao_id = self.funcoes_cache[sg_funcao]
                    args['funcao_codigo'] = nivel = i['IT-CO-NIVEL-FUNCAO'].lstrip('0')
                    args['funcao_opcao'] = i['IT-IN-OPCAO-FUNCAO'] == 'S'
                    args['funcao_data_ocupacao'] = data_inicio_funcao = strptime_or_default(i['IT-DA-INGRESSO-FUNCAO'], '%Y%m%d')
                    args['funcao_data_saida'] = data_fim_funcao = self._decrescimo_data(strptime_or_default(i['IT-DA-SAIDA-FUNCAO'], '%Y%m%d'), 1)

                    args['setor_funcao_id'] = None
                    setor_funcao_id = None
                    if int(i['IT-CO-UORG-FUNCAO']):
                        co_uorg_funcao = i['IT-CO-UORG-FUNCAO']
                        if co_uorg_funcao not in self.setores_cache:
                            log.warning(
                                f'Setor {co_uorg_funcao} da função do servidor de matrícula {extrai_matricula(i["GR-MATRICULA"])} não encontrado na cache.'
                            )
                        else:
                            args['setor_funcao_id'] = setor_funcao_id = self.setores_cache[co_uorg_funcao]
                    args['funcao_atividade_id'] = None
                    if int(i['IT-CO-ATIVIDADE-FUNCAO']):
                        args['funcao_atividade_id'] = atividade_funcao_id = self.atividades_cache[i['IT-CO-ATIVIDADE-FUNCAO']]
                else:
                    args['funcao_id'] = args['funcao_codigo'] = args['funcao_opcao'] = args['funcao_data_ocupacao'] = args[
                        'funcao_data_saida'
                    ] = args['setor_funcao_id'] = args['funcao_atividade_id'] = None

                    funcao_id = self.funcoes_cache[sg_funcao]
                    nivel = i['IT-CO-NIVEL-FUNCAO'].lstrip('0')
                    data_inicio_funcao = strptime_or_default(i['IT-DA-INGRESSO-FUNCAO'], '%Y%m%d')
                    data_fim_funcao = self._decrescimo_data(strptime_or_default(i['IT-DA-SAIDA-FUNCAO'], '%Y%m%d'), 1)
                    atividade_funcao_id = None
                    if int(i['IT-CO-ATIVIDADE-FUNCAO']):
                        atividade_funcao_id = self.atividades_cache[i['IT-CO-ATIVIDADE-FUNCAO']]
                    setor_funcao_id = None
                    if int(i['IT-CO-UORG-FUNCAO']):
                        co_uorg_funcao = i['IT-CO-UORG-FUNCAO']
                        if co_uorg_funcao not in self.setores_cache:
                            log.warning(
                                f'Setor {co_uorg_funcao} da função do servidor de matrícula {extrai_matricula(i["GR-MATRICULA"])} não encontrado na cache.'
                            )
                        else:
                            setor_funcao_id = self.setores_cache[co_uorg_funcao]

                # salvando
                if funcao_id and data_inicio_funcao and setor_funcao_id:
                    args_historicofuncao = {
                        'servidor_id': servidor_id,
                        'data_inicio_funcao': data_inicio_funcao,
                        'nivel': nivel,
                        'data_fim_funcao': data_fim_funcao,
                        'funcao_id': funcao_id,
                        'setor_id': setor_funcao_id,
                        'atividade_id': atividade_funcao_id,
                    }
                    ServidorFuncaoHistorico.objects.update_or_create(
                        servidor__pk=servidor_id, data_inicio_funcao=data_inicio_funcao, defaults=args_historicofuncao
                    )

            Servidor.update_or_create(args)
            self._atualizar_ingresso_orgao(servidor_id, i)
            self._atualizar_ingresso_servico_publico(servidor_id, i)

    def _atualizar_ingresso_orgao(self, servidor_id, item):
        if int(item['IT-CO-GRUPO-OCOR-INGR-ORGAO']):
            kwargs = {
                'diploma_legal_data': strptime_or_default(item['IT-DA-PUBL-DIPL-INGR-ORGAO'], '%Y%m%d'),
                'diploma_legal_num': item['IT-NU-DIPL-INGR-ORGAO'].strip(),
            }
            kwargs['diploma_legal_id'] = self.diploma_legal_cache.get(item['IT-CO-DIPL-INGR-ORGAO'], None)

            ocorrencia_id = self.ocorrencia_cache[item['IT-CO-GRUPO-OCOR-INGR-ORGAO'] + item['IT-CO-OCOR-INGR-ORGAO']]
            subgrupo = SubgrupoOcorrencia.get_or_create(descricao='INCLUSAO NO ORGAO')[0]
            data = strptime_or_default(item['IT-DA-OCOR-INGR-ORGAO-SERV'], '%Y%m%d')

            ok = False
            try:
                ServidorOcorrencia.objects.update_or_create(
                    servidor_id=servidor_id, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data, defaults=kwargs
                )
                ok = True
            except MultipleObjectsReturned:
                ServidorOcorrencia.objects.filter(servidor_id=servidor_id, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data).delete()
                ok = False

            if not ok:
                ServidorOcorrencia.objects.update_or_create(
                    servidor_id=servidor_id, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data, defaults=kwargs
                )

    def _atualizar_ingresso_servico_publico(self, servidor_id, item):
        if int(item['IT-CO-GRUPO-OCOR-INGR-SPUB']):
            kwargs = {
                'diploma_legal_data': strptime_or_default(item['IT-DA-PUBL-DIPL-INGR-SPUB'], '%Y%m%d'),
                'diploma_legal_num': item['IT-NU-DIPL-INGR-SPUB'].strip(),
            }
            kwargs['diploma_legal_id'] = self.diploma_legal_cache.get(item['IT-CO-DIPL-INGR-SPUB'], None)

            ocorrencia_id = self.ocorrencia_cache[item['IT-CO-GRUPO-OCOR-INGR-SPUB'] + item['IT-CO-OCOR-INGR-SPUB']]
            subgrupo = SubgrupoOcorrencia.get_or_create(descricao='INCLUSAO NO SERVICO PUBLICO')[0]
            data = strptime_or_default(item['IT-DA-OCOR-INGR-SPUB-SERV'], '%Y%m%d')

            ok = False
            try:
                ServidorOcorrencia.objects.update_or_create(
                    servidor_id=servidor_id, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data, defaults=kwargs
                )
                ok = True
            except MultipleObjectsReturned:
                ServidorOcorrencia.objects.filter(servidor_id=servidor_id, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data).delete()
                ok = False

            if not ok:
                ServidorOcorrencia.objects.update_or_create(
                    servidor_id=servidor_id, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data, defaults=kwargs
                )

    def _atualizar_ingresso_servico_publico_posse(self, servidor, item):
        if int(item['IT-CO-GRUPO-OCOR-INGR-SPUB-POSSE']):
            kwargs = {
                'diploma_legal_data': strptime_or_default(item['IT-DA-PUBL-DIPL-INGR-SPUB-POSSE'], '%Y%m%d'),
                'diploma_legal_num': item['IT-NU-DIPL-INGR-SPUB-POSSE'].strip(),
            }
            if int(item['IT-CO-DIPL-INGR-SPUB-POSSE']):
                kwargs['diploma_legal'] = self.diploma_legal_cache[item['IT-CO-DIPL-INGR-SPUB-POSSE']]
            else:
                kwargs['diploma_legal'] = None

            ocorrencia_id = self.ocorrencia_cache[item['IT-CO-GRUPO-OCOR-INGR-SPUB-POSSE'] + item['IT-CO-OCOR-INGR-SPUB-POSSE']]
            subgrupo, _created = SubgrupoOcorrencia.get_or_create(descricao='POSSE NO SERVICO PUBLICO')
            data = strptime_or_default(item['IT-DA-OCOR-INGR-SPUB-POSSE'], '%Y%m%d')

            ok = False
            try:
                ServidorOcorrencia.objects.update_or_create(
                    servidor=servidor, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data, defaults=kwargs
                )
                ok = True
            except MultipleObjectsReturned:
                ServidorOcorrencia.objects.filter(servidor=servidor, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data).delete()
                ok = False

            if not ok:
                ServidorOcorrencia.objects.update_or_create(
                    servidor=servidor, ocorrencia_id=ocorrencia_id, subgrupo=subgrupo, data=data, defaults=kwargs
                )

    def importar_servidor3(self, itens: Iterable[dict]) -> None:
        self.calc_caches(servidores=True)
        for i in tqdm.tqdm(itens):
            try:
                servidor_id = self.servidores_cache[extrai_matricula(i['GR-MATRICULA'])]
            except Exception:
                continue
            kwargs = {
                'pk': servidor_id,
                'matricula_anterior': extrai_matricula(i['IT-NU-MATRICULA-ANTERIOR']),
                'pessoa_fisica': {
                    # Dados do RG
                    'rg': i['IT-CO-REGISTRO-GERAL'].strip(),
                    'rg_orgao': i['IT-SG-ORGAO-EXPEDIDOR-IDEN'].strip(),
                    'rg_data': strptime_or_default(i['IT-DA-EXPEDICAO-IDEN'], '%Y%m%d'),
                    'rg_uf': i['IT-SG-UF-IDEN'],
                    'data_obito': strptime_or_default(i['IT-DA-OBITO'], '%Y%m%d'),
                    # TODO: O Titulo Eleitoral no arquivo do SIAPE tem 13 caracteres,
                    # mas modelamos com 12,
                    # como o primeiro do arquivo é sempre ZERO, deixamos assim mesmo.
                    'titulo_numero': i['IT-NU-TITULO-ELEITOR'][1:],
                },
                'opera_raio_x': bool(int(i['IT-IN-OPERADOR-RAIOX'])),
                'codigo_vaga': i['IT-CO-VAGA'],
            }

            id_setor_exercicio = i['IT-CO-UORG-EXERCICIO-SERV']

            # corrigindo setor de exercicio (não pode ser o raiz)
            nao_permitir_servidor_na_raiz = Configuracao.get_valor_por_chave('rh', 'nao_permitir_servidor_na_raiz')
            if nao_permitir_servidor_na_raiz:
                codigo_uorg = Configuracao.get_valor_por_chave('rh', 'codigo_uorg_vinculacao') or '000000001'
                if id_setor_exercicio == codigo_uorg:
                    sigla_re = Configuracao.get_valor_por_chave('comum', 'reitoria_sigla')
                    setor_exercicio = Setor.objects.siape().get(sigla=sigla_re)
                    id_setor_exercicio = setor_exercicio.codigo

            kwargs['setor_exercicio_id'] = self.setores_cache.get(id_setor_exercicio, None)
            # Só código conhecido altera a titulação: o SIAPE manda 00 também para servidor cuja
            # titulação o webservice (atualizar_servidor_completo_ws) grava toda noite, e um código
            # ainda fora da tabela (servidor3 importado sem o layout titulacoes) também a apagaria.
            titulacao_id = self.titulacao_cache.get(i['IT-CO-TITULACAO-FORMACAO-RH'])
            if titulacao_id:
                kwargs['titulacao_id'] = titulacao_id

            Servidor.update_or_create(kwargs)

    @staticmethod
    def municipio_do_endereco(item: dict) -> Municipio | None:
        """Município do endereço de um registro do layout servidor4 (criado se ainda não existir).

        Público porque o motor por lotes o chama antes de dividir o layout, para que lotes
        concorrentes não disputem a criação do mesmo município (`Municipio.get_or_create` não
        trata a violação de unicidade de `identificacao`).
        """
        # TODO: Quando migrar todos os arquivos de CIDADE, ESTADO e PAIS do edu rever esse if
        if 'edu' in settings.INSTALLED_APPS:
            estado = Estado.get_estado_por_sigla(item['IT-SG-UF-SERV-DISPONIVEL'])
            if not Cidade.objects.filter(nome=item['IT-NO-MUNICIPIO'], estado=estado).exists():
                return None
        return Municipio.get_or_create(item['IT-NO-MUNICIPIO'], item['IT-SG-UF-SERV-DISPONIVEL'])[0]

    def _atualizar_endereco(self, servidor_id: int, item: dict) -> None:
        servidor = Servidor.objects.get(pk=servidor_id)
        PessoaEndereco.objects.filter(pessoa__id=servidor.pessoa_fisica.id).delete()
        municipio = self.municipio_do_endereco(item)
        PessoaEndereco.objects.get_or_create(
            pessoa_id=servidor.pessoa_fisica.id,
            logradouro=item['IT-NO-LOGRADOURO'],
            numero=item['IT-NU-ENDERECO'],
            complemento=item['IT-NU-COMPLEMENTO-ENDERECO'],
            bairro=item['IT-NO-BAIRRO'],
            municipio=municipio,
            cep=item['IT-CO-CEP'],
        )

    def importar_servidor4(self, itens):
        self.calc_caches(servidores=True)
        for i in tqdm.tqdm(itens):
            try:
                servidor_id = self.servidores_cache[extrai_matricula(i['GR-MATRICULA-SERV-DISPONIVEL'])]
                # email_siape = i['IT-ED-CORREIO-ELETRONICO'].strip().lower()
                # try:
                #     validate_email(email_siape)
                # except ValidationError:
                #     email_siape = ''

                kwargs = {
                    'pk': servidor_id,
                    'pessoa_fisica': {
                        'grupo_sanguineo': i['IT-SG-GRUPO-SANGUINEO'].strip(),
                        'fator_rh': i['IT-SG-FATOR-RH'].strip(),
                    },
                    # email_siape = email_siape,
                    'alterado_em': datetime.now(),
                }

                kwargs['pessoa_fisica']['raca_id'] = self.raca_cache.get(str(int(i['IT-CO-COR-ORIGEM-ETNICA'])), None)
                kwargs['pessoa_fisica']['deficiencia_id'] = self.deficiencia_cache.get(
                    i['IT-CO-GRUPO-DEFICIENCIA-FISICA'] + i['IT-CO-DEFICIENCIA-FISICA'], None
                )

                Servidor.update_or_create(kwargs)
                self._atualizar_endereco(servidor_id, i)
            except Exception as ex:
                capture_exception(ex)
                log.warning(f'Erro ao importar servidor 4 - Error: {ex}\nArray: {i}')

    def importar_servidor5(self, itens):
        #        def _incluir_fax(pessoa_cpf, item):
        #            ddd = item['ED-FAX-RH'][:5].strip('0')
        #            numero = item['ED-FAX-RH'][5:].strip()
        #            if numero:
        #                pessoas=Pessoa.objects.filter(id__in=PessoaFisica.objects.filter(cpf=pessoa_cpf).values_list('id'))
        #                for pessoa in pessoas:
        #                    telefone_formatado = format_telefone(ddd, numero)
        #                    telefone = PessoaTelefone(pessoa=pessoa, numero = telefone_formatado)
        #                    telefone.save()
        for i in tqdm.tqdm(itens):
            try:
                pessoa_cpf = mask_cpf(i['NU-CPF-RH'])
            except KeyError:
                continue

            args = {
                'nome_pai': normalizar_nome_proprio(i['NO-PAI-RH'].strip()),
                'nascimento_municipio': Municipio.get_or_create(i['NO-MUNICIPIO-NASCIMENTO-RH'].strip(), i['SG-UF-NASCIMENTO-RH'])[0],
                'titulo_uf': i['SG-UF-TITULO-ELEITOR-RH'],
                'titulo_zona': i['NU-ZONA-ELEITORAL-RH'].strip(),
                'titulo_secao': i['NU-SECAO-ELEITORAL-RH'].strip(),
                'titulo_data_emissao': strptime_or_default(i['DA-EMISSAO-TITULO-ELEITOR-RH'], '%Y%m%d'),
                'cnh_carteira': i['NU-CART-MOTORISTA-RH'].strip(),
                'cnh_registro': i['NU-REGISTRO-CART-MOTORISTA-RH'].strip(),
                'cnh_categoria': i['IN-CATEGORIA-CART-MOTORISTA-RH'].strip(),
                'cnh_uf': i['SG-UF-CART-MOTORISTA-RH'].strip(),
                'cnh_emissao': strptime_or_default(i['DA-EXPEDICAO-CART-MOTORISTA-RH'], '%Y%m%d'),
                'cnh_validade': strptime_or_default(i['DA-VALIDADE-CART-MOTORISTA-RH'], '%Y%m%d'),
            }
            PessoaFisica.objects.filter(cpf=pessoa_cpf).update(**args)
            identificacao_unica_siape = i['CO-IDENT-UNICA-SIAPE-RH']
            #            servidor_id=servidores_cache[extrai_matricula(identificacao_unica_siape[:8])]
            Servidor.objects.filter(pessoa_fisica__cpf=pessoa_cpf).update(identificacao_unica_siape=identificacao_unica_siape)
            #            _incluir_fax(pessoa_cpf, i)

    def _atualizar_telefone(self, servidor_id, item):
        servidor = Servidor.objects.get(pk=servidor_id)
        PessoaTelefone.objects.filter(pessoa=servidor.pessoa_fisica).delete()
        fone_numero = item['IT-NU-TELEFONE'].strip()
        fone_ddd = item['IT-NU-DDD-TELEFONE'].strip()
        if fone_numero:
            telefone_formatado = format_telefone(fone_ddd, fone_numero)
            telefone = PessoaTelefone(pessoa=servidor.pessoa_fisica, numero=telefone_formatado)
            telefone.save()
        fone_numero_movel = item['IT-NU-TELEFONE-MOVEL'].strip()
        fone_ddd_movel = item['IT-NU-DDD-TELEFONE-MOVEL'].strip()
        if fone_numero_movel:
            telefone_formatado_movel = format_telefone(fone_ddd_movel, fone_numero_movel)
            telefone_movel = PessoaTelefone(pessoa=servidor.pessoa_fisica, numero=telefone_formatado_movel)
            telefone_movel.save()

    def importar_telefone_email_servidor(self, itens):
        self.calc_caches(servidores=True)
        for i in itens:
            # tratando matrículas com zeros a esquerda
            matricula_raw = i['GR-MATRICULA-SERV-DISPONIVEL'][5:]
            matricula_normalizada = str(int(matricula_raw))
            servidor_id = self.servidores_cache.get(matricula_normalizada)
            if not servidor_id:
                continue
            # criando o dicionário para ir adicionando as informações na medida que elas vão aparecendo
            kwargs = {}
            # verificando o campo de email institucional
            # email_institucional = i.get('IT-ED-EMAIL-INSTITUCIONAL')
            # if email_institucional:
            #     # ensure we only mark as institutional when the email belongs to an institutional domain
            #     email_institucional = email_institucional.strip().lower()
            #     if Configuracao.eh_email_institucional(email_institucional):
            #         kwargs['email_institucional'] = email_institucional
            #     else:
            #         email_institucional = None

            #
            # APENAS O EMAIL INSTITUCIONAL ESTÁ DISPONÍVEL NO EXTRATOR NO MOMENTO (15/07/2024)
            #

            # o campo IT-ED-CORREIO-ELETRONICO não pode ser email institucional
            # email_secundario = i.get("IT-ED-CORREIO-ELETRONICO")
            # if email_secundario and not Configuracao.eh_email_institucional(email_secundario):
            #     kwargs["email_secundario"] = email_secundario.lower()
            # atualizando o servidor
            Servidor.objects.filter(id=servidor_id).update(**kwargs)
            # atualiza telefones
            # self._atualizar_telefone(servidor_id, i)

    def importar_historico_afastamento(self, itens):
        self.calc_caches(True)
        for i in itens:
            servidor_id = self.servidores_cache[extrai_matricula(i['GR-MATRICULA-ANO-MES'])]
            self._atualizar_ocorrencia_afastamento(servidor_id, i)

    def importar_historico_funcao(self, itens):
        self.calc_caches(True)
        for i in itens:
            funcao_id = self.funcoes_cache.get(i['IT-SG-FUNCAO'].strip(), None)
            data_fim = self._decrescimo_data(strptime_or_default(i['IT-DA-SAIDA-FUNCAO'], '%Y%m%d'), 1)
            setor_id = self.setores_cache.get(i['IT-CO-UORG-FUNCAO'][-9:], None)
            if funcao_id and data_fim and setor_id:
                servidor_id = self.servidores_cache[extrai_matricula(i['GR-MATRICULA-ANO-MES'])]
                data_inicio = strptime_or_default(i['IT-DA-INGRESSO-FUNCAO'], '%Y%m%d')
                atividade_id = self.atividades_cache.get(i['IT-CO-ATIVIDADE-FUNCAO'], None)
                kwargs = {
                    'servidor_id': servidor_id,
                    'data_inicio_funcao': data_inicio,
                    'nivel': i['IT-CO-NIVEL-FUNCAO'].lstrip('0'),
                    'data_fim_funcao': data_fim,
                }
                kwargs['funcao_id'] = funcao_id
                kwargs['setor_id'] = setor_id
                kwargs['atividade_id'] = atividade_id
                check_funcao_historico = ServidorFuncaoHistorico.objects.filter(servidor_id=servidor_id, data_inicio_funcao=data_inicio).first()
                if check_funcao_historico is not None and not check_funcao_historico.atualiza_pelo_extrator:
                    continue
                ServidorFuncaoHistorico.objects.update_or_create(servidor_id=servidor_id, data_inicio_funcao=data_inicio, defaults=kwargs)

    def importar_historico_setor_siape(self, itens):
        if ServidorSetorLotacaoHistorico:
            self.calc_caches(True)
            for i in itens:
                servidor_id = self.servidores_cache.get(extrai_matricula(i['GR-MATRICULA-ANO-MES']))
                setor_lotacao_id = self.setores_cache.get(i['IT-CO-UORG-LOTACAO-SERVIDOR'].strip())
                setor_exercicio_id = self.setores_cache.get(i['IT-CO-UORG-EXERCICIO-SERV'].strip())
                data_inicio_setor_lotacao = strptime_or_default(i['IT-DA-LOTACAO'], '%Y%m%d')
                hora_atualizacao_siape = strptime_or_default(i['IT-DA-TRANSACAO'] + i['IT-HO-TRANSACAO'], '%Y%m%d%H%M%S')
                if servidor_id and setor_lotacao_id and setor_exercicio_id and data_inicio_setor_lotacao and hora_atualizacao_siape:
                    kwargs = {
                        'servidor_id': servidor_id,
                        'data_inicio_setor_lotacao': data_inicio_setor_lotacao,
                        'setor_lotacao_id': setor_lotacao_id,
                        'setor_exercicio_id': setor_exercicio_id,
                        'hora_atualizacao_siape': hora_atualizacao_siape,
                        'data_fim_setor_lotacao': None,
                    }
                    servidor_lotacao = ServidorSetorLotacaoHistorico.objects.filter(
                        servidor_id=servidor_id, data_inicio_setor_lotacao=data_inicio_setor_lotacao
                    )
                    if servidor_lotacao.exists():
                        servidor_lotacao.filter(hora_atualizacao_siape__lt=hora_atualizacao_siape).update(**kwargs)
                    else:
                        ServidorSetorLotacaoHistorico.objects.create(**kwargs)

    def importar_historico_ferias(self, itens):
        if Ferias:
            self.calc_caches(True)
            for i in itens:
                # a matricula vem junto com o ano de exercicio da ferias
                matricula = i['GR-MATR-EXERCICIO-FERIAS-HIST'][:12]
                servidor_id = self.servidores_cache[extrai_matricula(matricula)]
                ano = Ano.objects.get_or_create(ano=int(i['GR-MATR-EXERCICIO-FERIAS-HIST'][12:16]))[0]
                quitacao = int(i['IT-IN-QUITACAO-FERIAS'])
                ferias = Ferias.objects.filter(servidor_id=servidor_id, ano=ano).first()
                if ferias:
                    if not ferias.atualiza_pelo_extrator:
                        continue

                    if not ferias.quitacao or ferias.quitacao <= quitacao:
                        ferias.quitacao = quitacao
                        if int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(1)']):
                            ferias.gratificacao_natalina = 1
                        elif int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(2)']):
                            ferias.gratificacao_natalina = 2
                        elif int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(3)']):
                            ferias.gratificacao_natalina = 3
                        else:
                            ferias.gratificacao_natalina = 0
                        count = 0
                        indice_setenta_porcento = 0
                        if int(i['IT-IN-ADIANTAMENTO-FERIAS(1)']):
                            indice_setenta_porcento += 1
                            count += 1
                        if int(i['IT-IN-ADIANTAMENTO-FERIAS(2)']):
                            count += 1
                            indice_setenta_porcento += 2
                        if int(i['IT-IN-ADIANTAMENTO-FERIAS(3)']):
                            count += 1
                            indice_setenta_porcento += 3
                        if count > 1:
                            indice_setenta_porcento += 1
                        ferias.setenta_porcento = indice_setenta_porcento

                        ferias.data_inicio_periodo1 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(1)'], '%Y%m%d')
                        qtd_dias_periodo1 = int(i['IT-QT-DIAS-FERIAS(1)']) - 1
                        ferias.data_inicio_periodo2 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(2)'], '%Y%m%d')
                        qtd_dias_periodo2 = int(i['IT-QT-DIAS-FERIAS(2)']) - 1
                        ferias.data_inicio_periodo3 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(3)'], '%Y%m%d')
                        qtd_dias_periodo3 = int(i['IT-QT-DIAS-FERIAS(3)']) - 1

                        data_interrupcao_periodo1 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(1)'], '%Y%m%d')
                        data_interrupcao_periodo2 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(2)'], '%Y%m%d')
                        data_interrupcao_periodo3 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(3)'], '%Y%m%d')
                        data_inicio_continuacao_periodo1 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(1)'], '%Y%m%d')
                        qtd_dias_continuacao_periodo1 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(1)']) - 1
                        data_inicio_continuacao_periodo2 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(2)'], '%Y%m%d')
                        qtd_dias_continuacao_periodo2 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(2)']) - 1
                        data_inicio_continuacao_periodo3 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(3)'], '%Y%m%d')
                        qtd_dias_continuacao_periodo3 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(3)']) - 1
                        if ferias.data_inicio_periodo1:
                            ferias.data_fim_periodo1 = ferias.data_inicio_periodo1 + data.timedelta(days=qtd_dias_periodo1)
                            if data_interrupcao_periodo1:
                                interrupcao = InterrupcaoFerias()
                                interrupcao, created = InterrupcaoFerias.objects.get_or_create(
                                    ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo1
                                )
                                interrupcao.data_fim_continuacao_periodo = data_inicio_continuacao_periodo1 + data.timedelta(
                                    days=qtd_dias_continuacao_periodo1
                                )
                                interrupcao.data_inicio_continuacao_periodo = data_inicio_continuacao_periodo1
                                interrupcao.save()
                                if created:
                                    if ferias.data_inicio_periodo1 <= data_interrupcao_periodo1 < ferias.data_fim_periodo1:
                                        ferias.data_fim_periodo1 = data_interrupcao_periodo1 - data.timedelta(days=1)
                                    else:
                                        interrupcoes = InterrupcaoFerias.objects.filter(ferias=ferias)
                                        for interr in interrupcoes:
                                            if (
                                                interr.data_inicio_continuacao_periodo
                                                <= data_interrupcao_periodo1
                                                < interr.data_fim_continuacao_periodo
                                            ):
                                                interr.data_fim_continuacao_periodo = data_interrupcao_periodo1 - data.timedelta(days=1)
                                                interr.save()

                        if ferias.data_inicio_periodo2:
                            ferias.data_fim_periodo2 = ferias.data_inicio_periodo2 + data.timedelta(days=qtd_dias_periodo2)
                            if data_interrupcao_periodo2:
                                interrupcao = InterrupcaoFerias()
                                interrupcao, created = InterrupcaoFerias.objects.get_or_create(
                                    ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo2
                                )
                                interrupcao.data_fim_continuacao_periodo = data_inicio_continuacao_periodo2 + data.timedelta(
                                    days=qtd_dias_continuacao_periodo2
                                )
                                interrupcao.data_inicio_continuacao_periodo = data_inicio_continuacao_periodo2
                                interrupcao.save()
                                if created:
                                    if ferias.data_inicio_periodo2 <= data_interrupcao_periodo2 < ferias.data_fim_periodo2:
                                        ferias.data_fim_periodo2 = data_interrupcao_periodo2 - data.timedelta(days=1)
                                    else:
                                        interrupcoes = InterrupcaoFerias.objects.filter(ferias=ferias)
                                        for interr in interrupcoes:
                                            if (
                                                interr.data_inicio_continuacao_periodo
                                                <= data_interrupcao_periodo2
                                                < interr.data_fim_continuacao_periodo
                                            ):
                                                interr.data_fim_continuacao_periodo = data_interrupcao_periodo2 - data.timedelta(days=1)
                                                interr.save()
                        else:
                            ferias.data_fim_periodo2 = None

                        if ferias.data_inicio_periodo3:
                            ferias.data_fim_periodo3 = ferias.data_inicio_periodo3 + data.timedelta(days=qtd_dias_periodo3)
                            if data_interrupcao_periodo3:
                                interrupcao = InterrupcaoFerias()
                                interrupcao, created = InterrupcaoFerias.objects.get_or_create(
                                    ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo3
                                )
                                interrupcao.data_fim_continuacao_periodo = data_inicio_continuacao_periodo3 + data.timedelta(
                                    days=qtd_dias_continuacao_periodo3
                                )
                                interrupcao.data_inicio_continuacao_periodo = data_inicio_continuacao_periodo3
                                interrupcao.save()
                                if created:
                                    if ferias.data_inicio_periodo3 <= data_interrupcao_periodo3 < ferias.data_fim_periodo3:
                                        ferias.data_fim_periodo3 = data_interrupcao_periodo3 - data.timedelta(days=1)
                                    else:
                                        interrupcoes = InterrupcaoFerias.objects.filter(ferias=ferias)
                                        for interr in interrupcoes:
                                            if (
                                                interr.data_inicio_continuacao_periodo
                                                <= data_interrupcao_periodo3
                                                < interr.data_fim_continuacao_periodo
                                            ):
                                                interr.data_fim_continuacao_periodo = data_interrupcao_periodo3 - data.timedelta(days=1)
                                                interr.save()
                        else:
                            ferias.data_fim_periodo3 = None

                    ferias.cadastrado = True
                    ferias.save()
                else:
                    ferias = Ferias()
                    ferias.quitacao = quitacao
                    data_inicio_periodo1 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(1)'], '%Y%m%d')
                    data_inicio_periodo2 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(2)'], '%Y%m%d')
                    data_inicio_periodo3 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(3)'], '%Y%m%d')
                    kwargs = {
                        'data_inicio_periodo1': data_inicio_periodo1,
                        'data_inicio_periodo2': data_inicio_periodo2,
                        'data_inicio_periodo3': data_inicio_periodo2,
                        'cadastrado': True,
                    }
                    if int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(1)']):
                        kwargs['gratificacao_natalina'] = 1
                    elif int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(2)']):
                        kwargs['gratificacao_natalina'] = 2
                    elif int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(3)']):
                        kwargs['gratificacao_natalina'] = 3
                    else:
                        kwargs['gratificacao_natalina'] = 0
                    count = 0
                    indice_setenta_porcento = 0
                    if int(i['IT-IN-ADIANTAMENTO-FERIAS(1)']):
                        indice_setenta_porcento += 1
                        count += 1
                    if int(i['IT-IN-ADIANTAMENTO-FERIAS(2)']):
                        count += 1
                        indice_setenta_porcento += 2
                    if int(i['IT-IN-ADIANTAMENTO-FERIAS(3)']):
                        count += 1
                        indice_setenta_porcento += 3
                    if count > 1:
                        indice_setenta_porcento += 1

                    kwargs['setenta_porcento'] = indice_setenta_porcento

                    qtd_dias_periodo1 = int(i['IT-QT-DIAS-FERIAS(1)']) - 1
                    qtd_dias_periodo2 = int(i['IT-QT-DIAS-FERIAS(2)']) - 1
                    qtd_dias_periodo3 = int(i['IT-QT-DIAS-FERIAS(3)']) - 1

                    kwargs['data_fim_periodo1'] = data_inicio_periodo1 + data.timedelta(days=qtd_dias_periodo1)
                    data_interrupcao_periodo1 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(1)'], '%Y%m%d')
                    data_interrupcao_periodo2 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(2)'], '%Y%m%d')
                    data_interrupcao_periodo3 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(3)'], '%Y%m%d')
                    data_inicio_continuacao_periodo1 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(1)'], '%Y%m%d')
                    qtd_dias_continuacao_periodo1 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(1)']) - 1
                    data_inicio_continuacao_periodo2 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(2)'], '%Y%m%d')
                    qtd_dias_continuacao_periodo2 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(2)']) - 1
                    data_inicio_continuacao_periodo3 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(3)'], '%Y%m%d')
                    qtd_dias_continuacao_periodo3 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(3)']) - 1
                    if data_inicio_periodo2:
                        kwargs['data_fim_periodo2'] = data_inicio_periodo2 + data.timedelta(days=qtd_dias_periodo2)
                    if data_inicio_periodo3:
                        kwargs['data_fim_periodo3'] = data_inicio_periodo3 + data.timedelta(days=qtd_dias_periodo3)

                    ferias = Ferias.objects.update_or_create(servidor_id=servidor_id, ano=ano, defaults=kwargs)[0]
                    atualizar_dados_ferias = {}
                    if data_interrupcao_periodo1:
                        kwargs_interrupcao = {
                            'data_fim_continuacao_periodo': data_inicio_continuacao_periodo1 + data.timedelta(days=qtd_dias_continuacao_periodo1),
                            'data_inicio_continuacao_periodo': data_inicio_continuacao_periodo1,
                        }
                        InterrupcaoFerias.objects.update_or_create(
                            ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo1, defaults=kwargs_interrupcao
                        )
                        if ferias.data_inicio_periodo1 <= data_interrupcao_periodo1 < ferias.data_fim_periodo1:
                            atualizar_dados_ferias['data_fim_periodo1'] = data_interrupcao_periodo1 - data.timedelta(days=1)

                    if data_interrupcao_periodo2:
                        kwargs_interrupcao = {
                            'data_fim_continuacao_periodo': data_inicio_continuacao_periodo2 + data.timedelta(days=qtd_dias_continuacao_periodo2),
                            'data_inicio_continuacao_periodo': data_inicio_continuacao_periodo2,
                        }
                        InterrupcaoFerias.objects.update_or_create(
                            ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo2, defaults=kwargs_interrupcao
                        )
                        if ferias.data_inicio_periodo2 <= data_interrupcao_periodo2 < ferias.data_fim_periodo2:
                            atualizar_dados_ferias['data_fim_periodo2'] = data_interrupcao_periodo2 - data.timedelta(days=1)

                    if data_interrupcao_periodo3:
                        kwargs_interrupcao = {
                            'data_fim_continuacao_periodo': data_inicio_continuacao_periodo3 + data.timedelta(days=qtd_dias_continuacao_periodo3),
                            'data_inicio_continuacao_periodo': data_inicio_continuacao_periodo3,
                        }
                        InterrupcaoFerias.objects.update_or_create(
                            ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo3, defaults=kwargs_interrupcao
                        )
                        if ferias.data_inicio_periodo3 <= data_interrupcao_periodo3 < ferias.data_fim_periodo3:
                            atualizar_dados_ferias['data_fim_periodo3'] = data_interrupcao_periodo3 - data.timedelta(days=1)

                    if atualizar_dados_ferias:
                        Ferias.objects.filter(pk=ferias.pk).update(**atualizar_dados_ferias)

    def importar_ferias(self, itens):
        if Ferias:
            for i in itens:
                matricula = i['GR-MATRICULA-EXERCICIO-FERIAS'][:12]  # a matricula vem junto com o ano de exercicio da ferias
                try:
                    servidor = Servidor.objects.get(matricula=extrai_matricula(matricula))
                except Exception as ex:
                    log.info(f'>>> ERRO: {ex}  [{matricula}]')
                    continue
                ano = Ano.objects.get_or_create(ano=int(i['GR-MATRICULA-EXERCICIO-FERIAS'][12:16]))[0]
                quitacao = int(i['IT-IN-QUITACAO-FERIAS'])
                ferias = Ferias.objects.filter(servidor=servidor, ano=ano).first()
                if ferias:
                    if ferias.atualiza_pelo_extrator and (not ferias.quitacao or ferias.quitacao <= quitacao):
                        ferias.quitacao = quitacao

                        if int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(1)']):
                            ferias.gratificacao_natalina = 1
                        elif int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(2)']):
                            ferias.gratificacao_natalina = 2
                        elif int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(3)']):
                            ferias.gratificacao_natalina = 3
                        else:
                            ferias.gratificacao_natalina = 0
                        count = 0
                        indice_setenta_porcento = 0
                        if int(i['IT-IN-ADIANTAMENTO-FERIAS(1)']):
                            indice_setenta_porcento += 1
                            count += 1
                        if int(i['IT-IN-ADIANTAMENTO-FERIAS(2)']):
                            count += 1
                            indice_setenta_porcento += 2
                        if int(i['IT-IN-ADIANTAMENTO-FERIAS(3)']):
                            count += 1
                            indice_setenta_porcento += 3
                        if count > 1:
                            indice_setenta_porcento += 1
                        ferias.setenta_porcento = indice_setenta_porcento

                        ferias.data_inicio_periodo1 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(1)'], '%Y%m%d')
                        qtd_dias_periodo1 = int(i['IT-QT-DIAS-FERIAS(1)']) - 1
                        ferias.data_inicio_periodo2 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(2)'], '%Y%m%d')
                        qtd_dias_periodo2 = int(i['IT-QT-DIAS-FERIAS(2)']) - 1
                        ferias.data_inicio_periodo3 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(3)'], '%Y%m%d')
                        qtd_dias_periodo3 = int(i['IT-QT-DIAS-FERIAS(3)']) - 1

                        data_interrupcao_periodo1 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(1)'], '%Y%m%d')
                        data_interrupcao_periodo2 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(2)'], '%Y%m%d')
                        data_interrupcao_periodo3 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(3)'], '%Y%m%d')
                        data_inicio_continuacao_periodo1 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(1)'], '%Y%m%d')
                        qtd_dias_continuacao_periodo1 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(1)']) - 1
                        data_inicio_continuacao_periodo2 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(2)'], '%Y%m%d')
                        qtd_dias_continuacao_periodo2 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(2)']) - 1
                        data_inicio_continuacao_periodo3 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(3)'], '%Y%m%d')
                        qtd_dias_continuacao_periodo3 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(3)']) - 1
                        if ferias.data_inicio_periodo1:
                            ferias.data_fim_periodo1 = ferias.data_inicio_periodo1 + data.timedelta(days=qtd_dias_periodo1)
                            if data_interrupcao_periodo1:
                                interrupcao = InterrupcaoFerias()
                                interrupcao, created = InterrupcaoFerias.objects.get_or_create(
                                    ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo1
                                )
                                interrupcao.data_fim_continuacao_periodo = data_inicio_continuacao_periodo1 + data.timedelta(
                                    days=qtd_dias_continuacao_periodo1
                                )
                                interrupcao.data_inicio_continuacao_periodo = data_inicio_continuacao_periodo1
                                interrupcao.save()
                                if created:
                                    if ferias.data_inicio_periodo1 <= data_interrupcao_periodo1 < ferias.data_fim_periodo1:
                                        ferias.data_fim_periodo1 = data_interrupcao_periodo1 - data.timedelta(days=1)
                                    else:
                                        interrupcoes = InterrupcaoFerias.objects.filter(ferias=ferias)
                                        for interr in interrupcoes:
                                            if (
                                                interr.data_inicio_continuacao_periodo
                                                <= data_interrupcao_periodo1
                                                < interr.data_fim_continuacao_periodo
                                            ):
                                                interr.data_fim_continuacao_periodo = data_interrupcao_periodo1 - data.timedelta(days=1)
                                                interr.save()

                        if ferias.data_inicio_periodo2:
                            ferias.data_fim_periodo2 = ferias.data_inicio_periodo2 + data.timedelta(days=qtd_dias_periodo2)
                            if data_interrupcao_periodo2:
                                interrupcao = InterrupcaoFerias()
                                interrupcao, created = InterrupcaoFerias.objects.get_or_create(
                                    ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo2
                                )
                                interrupcao.data_fim_continuacao_periodo = data_inicio_continuacao_periodo2 + data.timedelta(
                                    days=qtd_dias_continuacao_periodo2
                                )
                                interrupcao.data_inicio_continuacao_periodo = data_inicio_continuacao_periodo2
                                interrupcao.save()
                                if created:
                                    if ferias.data_inicio_periodo2 <= data_interrupcao_periodo2 < ferias.data_fim_periodo2:
                                        ferias.data_fim_periodo2 = data_interrupcao_periodo2 - data.timedelta(days=1)
                                    else:
                                        interrupcoes = InterrupcaoFerias.objects.filter(ferias=ferias)
                                        for interr in interrupcoes:
                                            if (
                                                interr.data_inicio_continuacao_periodo
                                                <= data_interrupcao_periodo2
                                                < interr.data_fim_continuacao_periodo
                                            ):
                                                interr.data_fim_continuacao_periodo = data_interrupcao_periodo2 - data.timedelta(days=1)
                                                interr.save()
                        else:
                            ferias.data_fim_periodo2 = None

                        if ferias.data_inicio_periodo3:
                            ferias.data_fim_periodo3 = ferias.data_inicio_periodo3 + data.timedelta(days=qtd_dias_periodo3)
                            if data_interrupcao_periodo3:
                                interrupcao = InterrupcaoFerias()
                                interrupcao, created = InterrupcaoFerias.objects.get_or_create(
                                    ferias=ferias, data_interrupcao_periodo=data_interrupcao_periodo3
                                )
                                interrupcao.data_fim_continuacao_periodo = data_inicio_continuacao_periodo3 + data.timedelta(
                                    days=qtd_dias_continuacao_periodo3
                                )
                                interrupcao.data_inicio_continuacao_periodo = data_inicio_continuacao_periodo3
                                interrupcao.save()
                                if created:
                                    if ferias.data_inicio_periodo3 <= data_interrupcao_periodo3 < ferias.data_fim_periodo3:
                                        ferias.data_fim_periodo3 = data_interrupcao_periodo3 - data.timedelta(days=1)
                                    else:
                                        interrupcoes = InterrupcaoFerias.objects.filter(ferias=ferias)
                                        for interr in interrupcoes:
                                            if (
                                                interr.data_inicio_continuacao_periodo
                                                <= data_interrupcao_periodo3
                                                < interr.data_fim_continuacao_periodo
                                            ):
                                                interr.data_fim_continuacao_periodo = data_interrupcao_periodo3 - data.timedelta(days=1)
                                                interr.save()
                        else:
                            ferias.data_fim_periodo3 = None

                    ferias.cadastrado = True
                    ferias.save()
                else:
                    ferias = Ferias()
                    ferias.servidor = servidor
                    ferias.ano = ano
                    ferias.quitacao = quitacao
                    if int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(1)']):
                        ferias.gratificacao_natalina = 1
                    elif int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(2)']):
                        ferias.gratificacao_natalina = 2
                    elif int(i['IT-IN-ADIANTAMENTO-GRAT-NATALINA(3)']):
                        ferias.gratificacao_natalina = 3
                    else:
                        ferias.gratificacao_natalina = 0
                    count = 0
                    indice_setenta_porcento = 0
                    if int(i['IT-IN-ADIANTAMENTO-FERIAS(1)']):
                        indice_setenta_porcento += 1
                        count += 1
                    if int(i['IT-IN-ADIANTAMENTO-FERIAS(2)']):
                        count += 1
                        indice_setenta_porcento += 2
                    if int(i['IT-IN-ADIANTAMENTO-FERIAS(3)']):
                        count += 1
                        indice_setenta_porcento += 3
                    if count > 1:
                        indice_setenta_porcento += 1
                    ferias.setenta_porcento = indice_setenta_porcento
                    ferias.data_inicio_periodo1 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(1)'], '%Y%m%d')
                    qtd_dias_periodo1 = int(i['IT-QT-DIAS-FERIAS(1)']) - 1
                    ferias.data_inicio_periodo2 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(2)'], '%Y%m%d')
                    qtd_dias_periodo2 = int(i['IT-QT-DIAS-FERIAS(2)']) - 1
                    ferias.data_inicio_periodo3 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS(3)'], '%Y%m%d')
                    qtd_dias_periodo3 = int(i['IT-QT-DIAS-FERIAS(3)']) - 1
                    ferias.data_fim_periodo1 = ferias.data_inicio_periodo1 + data.timedelta(days=qtd_dias_periodo1)
                    data_interrupcao_periodo1 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(1)'], '%Y%m%d')
                    data_interrupcao_periodo2 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(2)'], '%Y%m%d')
                    data_interrupcao_periodo3 = strptime_date_or_default(i['IT-DA-INTERRUPCAO-FERIAS(3)'], '%Y%m%d')
                    data_inicio_continuacao_periodo1 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(1)'], '%Y%m%d')
                    qtd_dias_continuacao_periodo1 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(1)']) - 1
                    data_inicio_continuacao_periodo2 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(2)'], '%Y%m%d')
                    qtd_dias_continuacao_periodo2 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(2)']) - 1
                    data_inicio_continuacao_periodo3 = strptime_date_or_default(i['IT-DA-INICIO-FERIAS-INTERROMPIDA(3)'], '%Y%m%d')
                    qtd_dias_continuacao_periodo3 = int(i['IT-QT-DIA-FERIAS-INTERROMPIDA(3)']) - 1
                    if ferias.data_inicio_periodo2:
                        ferias.data_fim_periodo2 = ferias.data_inicio_periodo2 + data.timedelta(days=qtd_dias_periodo2)
                    if ferias.data_inicio_periodo3:
                        ferias.data_fim_periodo3 = ferias.data_inicio_periodo3 + data.timedelta(days=qtd_dias_periodo3)
                    ferias.cadastrado = True
                    ferias.save()
                    if data_interrupcao_periodo1:
                        interrupcao = InterrupcaoFerias.objects.create(
                            ferias=ferias,
                            data_interrupcao_periodo=data_interrupcao_periodo1,
                            data_fim_continuacao_periodo=data_inicio_continuacao_periodo1 + data.timedelta(days=qtd_dias_continuacao_periodo1),
                            data_inicio_continuacao_periodo=data_inicio_continuacao_periodo1,
                        )
                        if ferias.data_inicio_periodo1 <= data_interrupcao_periodo1 < ferias.data_fim_periodo1:
                            ferias.data_fim_periodo1 = data_interrupcao_periodo1 - data.timedelta(days=1)
                            ferias.save()

                    if data_interrupcao_periodo2:
                        interrupcao = InterrupcaoFerias.objects.get_or_create(
                            ferias=ferias,
                            data_interrupcao_periodo=data_interrupcao_periodo2,
                            data_fim_continuacao_periodo=data_inicio_continuacao_periodo2 + data.timedelta(days=qtd_dias_continuacao_periodo2),
                            data_inicio_continuacao_periodo=data_inicio_continuacao_periodo2,
                        )
                        if ferias.data_inicio_periodo2 <= data_interrupcao_periodo2 < ferias.data_fim_periodo2:
                            ferias.data_fim_periodo2 = data_interrupcao_periodo2 - data.timedelta(days=1)
                            ferias.save()
                    if data_interrupcao_periodo3:
                        interrupcao = InterrupcaoFerias.objects.get_or_create(
                            ferias=ferias,
                            data_interrupcao_periodo=data_interrupcao_periodo3,
                            data_fim_continuacao_periodo=data_inicio_continuacao_periodo3 + data.timedelta(days=qtd_dias_continuacao_periodo3),
                            data_inicio_continuacao_periodo=data_inicio_continuacao_periodo3,
                        )
                        if ferias.data_inicio_periodo3 <= data_interrupcao_periodo3 < ferias.data_fim_periodo3:
                            ferias.data_fim_periodo3 = data_interrupcao_periodo3 - data.timedelta(days=1)
                            ferias.save()

    def importar_titulacoes(self, itens):
        for i in itens:
            codigo = i['CO-TITULACAO']
            titulacao = Titulacao.objects.get_or_create(codigo=codigo)[0]
            titulacao.nome = i['NO-TITULACAO'].strip()
            titulacao.save()

    def importar_servidor_matriculas(self, itens):
        self.calc_caches(True)
        for i in itens:
            matricula_crh = i['CO-CRH-MATRICULA']
            matricula_sipe = i['NU-MATRICULA-SIPE-RH']
            matricula = extrai_matricula(i['GR-MATRICULA-SIAPE-RH'])
            servidor_id = self.servidores_cache.get(matricula)
            if matricula_crh and matricula_sipe and servidor_id:
                Servidor.objects.filter(id=servidor_id).update(matricula_crh=matricula_crh, matricula_sipe=matricula_sipe)

    def _atualizar_regime_juridico_pca(self, pca, registro, numero_registro):
        #
        # checagem exceção de atualização para regime jurídico pca por servidor
        atualiza = True
        matricula = pca.servidor.matricula
        if matricula in self.excecoes_atualizacao:
            for _campo in self.excecoes_atualizacao[matricula]:
                # NO CASO DOS REGIMES JURÍDICOS, NÃO É POSSÍVEL DEIXAR DE CADASTRAR APENAS UM CAMPO, POIS TODOS NÃO NOT NULL
                # NESTE CASO, VAMOS IGNORAR POR COMPLETO AS ALTERAÇÕES QUANDO ACHAR QUALQUER CAMPO REFERENTE
                # del registro[campo] # TODO: cuidado com campos not null
                atualiza = False

        if atualiza:
            # preenchendo/atualizando args para atualizar/cadastrar os registros
            regime_juridico = RegimeJuridico.objects.filter(codigo_regime=registro[f'CO-REGIME-JURIDICO-PCA({numero_registro})']).first()
            dados_pca = {
                'pca': pca,
                'regime_juridico': regime_juridico,
                'codigo_regime_juridico_pca': registro[f'CO-REGIME-JURIDICO-PCA({numero_registro})'],
            }
            # data de início do regime jurídico
            data_ini = f'DA-INI-REGIME-JURIDICO-PCA({numero_registro})'
            if data_ini in registro:
                data_inicio_regime_juridico_pca = strptime_or_default(registro[data_ini], '%Y%m%d')
                dados_pca.update({'data_inicio_regime_juridico_pca': data_inicio_regime_juridico_pca})
            # data de fim do regime jurídico
            data_fim = f'DA-FIM-REGIME-JURIDICO-PCA({numero_registro})'
            if data_fim in registro:
                data_fim_regime_juridico_pca = strptime_or_default(registro[data_fim], '%Y%m%d')
                dados_pca.update({'data_fim_regime_juridico_pca': data_fim_regime_juridico_pca})
            # fator do regime jurídico
            fator = f'VA-FATOR-TEMPO-REGIME-PCA({numero_registro})'
            if fator in registro:
                valor_fator_tempo_regime_juridico_pca = Decimal(registro[fator][:-4] + '.' + registro[fator][-4:])
                dados_pca.update(
                    {
                        'valor_fator_tempo_regime_juridico_pca': valor_fator_tempo_regime_juridico_pca,
                    }
                )

            RegimeJuridicoPCA.objects.get_or_create(**dados_pca)

    def _atualizar_jornada_trabalho_pca(self, pca, registro, numero_registro):
        data_inicio_jornada_trabalho_pca = strptime_or_default(registro[f'DA-INI-JORNADA-TRABALHO-PCA({numero_registro})'], '%Y%m%d')
        data_fim_jornada_trabalho_pca = strptime_or_default(registro[f'DA-FIM-JORNADA-TRABALHO-PCA({numero_registro})'], '%Y%m%d')
        JornadaTrabalhoPCA.objects.get_or_create(
            pca=pca,
            qtde_jornada_trabalho_pca=registro[f'QT-JORNADA-TRABALHO-PCA({numero_registro})'],
            data_inicio_jornada_trabalho_pca=data_inicio_jornada_trabalho_pca,
            data_fim_jornada_trabalho_pca=data_fim_jornada_trabalho_pca,
        )

    def importar_pca(self, itens):
        """
        itens = [
            {CH-PCA: '?', CO-CRH-PCA: '?', ...},
            {CH-PCA: '?', CO-CRH-PCA: '?', ...},
            {CH-PCA: '?', CO-CRH-PCA: '?', ...},
            {CH-PCA: '?', CO-CRH-PCA: '?', ...},
        ]
        """
        if PCA:
            for registro in itens:
                try:
                    codigo_pca = registro['CH-PCA']
                    servidor_matricula_crh = registro['CO-CRH-PCA']
                    servidor_vaga_pca = registro['CO-VAGA-SIAPE-PCA']
                    cargo_pca = CargoEmprego.objects.get(codigo=registro['CH-CARGO-PCA'])
                    if Servidor.objects.filter(matricula_crh=servidor_matricula_crh, matricula_sipe=codigo_pca[:-3]).exists():
                        servidor = Servidor.objects.filter(matricula_crh=servidor_matricula_crh, matricula_sipe=codigo_pca[:-3]).latest('pk')
                        forma_entrada_pca = None
                        if int(registro['CO-FORMA-ENTRADA-PCA']):
                            forma_entrada_pca = FormaProvimentoVacancia.get_or_create(fill_attr='descricao', codigo=registro['CO-FORMA-ENTRADA-PCA'])[
                                0
                            ]

                        forma_vacancia_pca = None
                        if int(registro['CO-FORMA-VACANCIA-PCA']):
                            forma_vacancia_pca = FormaProvimentoVacancia.get_or_create(
                                fill_attr='descricao', codigo=registro['CO-FORMA-VACANCIA-PCA']
                            )[0]

                        kwargs = {
                            'codigo_pca': codigo_pca,
                            'servidor': servidor,
                            'servidor_matricula_crh': servidor_matricula_crh,
                            'servidor_vaga_pca': servidor_vaga_pca,
                            'cargo_pca': cargo_pca,
                            'forma_entrada_pca': forma_entrada_pca,
                            'data_entrada_pca': strptime_or_default(registro['DA-ENTRADA-PCA'], '%Y%m%d'),
                            'texto_entrada_pca': registro['TX-ENTRADA-PCA(1)'].strip(),
                            'forma_vacancia_pca': forma_vacancia_pca,
                            'data_vacancia_pca': strptime_or_default(registro['DA-VACANCIA-PCA'], '%Y%m%d'),
                            'texto_vacancia_pca': registro['TX-VACANCIA-PCA(1)'].strip(),
                        }
                        pca = PCA.objects.update_or_create(codigo_pca=codigo_pca, defaults=kwargs)[0]

                        # regime juridico PCA
                        pca.regimejuridicopca_set.all().delete()
                        if int(registro['CO-REGIME-JURIDICO-PCA(1)']):
                            self._atualizar_regime_juridico_pca(pca, registro, 1)
                        if int(registro['CO-REGIME-JURIDICO-PCA(2)']):
                            self._atualizar_regime_juridico_pca(pca, registro, 2)
                        if int(registro['CO-REGIME-JURIDICO-PCA(3)']):
                            self._atualizar_regime_juridico_pca(pca, registro, 3)
                        if int(registro['CO-REGIME-JURIDICO-PCA(4)']):
                            self._atualizar_regime_juridico_pca(pca, registro, 4)
                        if int(registro['CO-REGIME-JURIDICO-PCA(5)']):
                            self._atualizar_regime_juridico_pca(pca, registro, 5)
                        if int(registro['CO-REGIME-JURIDICO-PCA(6)']):
                            self._atualizar_regime_juridico_pca(pca, registro, 6)

                        # jornada de trabalho PCA
                        pca.jornadatrabalhopca_set.all().delete()
                        if int(registro['QT-JORNADA-TRABALHO-PCA(1)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 1)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(2)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 2)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(3)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 3)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(4)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 4)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(5)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 5)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(6)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 6)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(7)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 7)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(8)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 8)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(9)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 9)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(10)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 10)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(11)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 11)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(12)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 12)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(13)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 13)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(14)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 14)
                        if int(registro['QT-JORNADA-TRABALHO-PCA(15)']):
                            self._atualizar_jornada_trabalho_pca(pca, registro, 15)

                except Exception as ex:
                    capture_exception(ex)
                    log.info(f'>>> ERRO: {ex} \n>>> LINHA: {registro}')
                    continue

    def importar_posicionamento_pca(self, itens):
        """
        pca = models.ForeignKeyPlus('rh.PCA', null=False)
        codigo_pca_posicionamento = models.CharField(max_length=11) # CH-PCA-POSICIONAMENTO - é o mesmo dado de rh.PCA.codigo_pca
        codigo_posicionamento_pca = models.CharField(max_length=9, unique=True, null=False) # CH-POSICIONAMENTO-PCA

        forma_entrada = models.ForeignKeyPlus('rh.FormaProvimentoVacancia') # CO-FORMA-ENTRADA-POS-PCA
        data_inicio_posicionamento_pca = models.DateFieldPlus() # DA-INI-POSICIONAMENTO-PCA
        data_fim_posicionamento_pca = models.DateFieldPlus() # DA-FIM-POSICIONAMENTO-PCA
        """
        if PosicionamentoPCA:
            for registro in itens:
                codigo_pca = registro['CH-PCA-POSICIONAMENTO']
                codigo_posicionamento = registro['CH-POSICIONAMENTO-PCA']
                forma_entrada = FormaProvimentoVacancia.get_or_create(fill_attr='descricao', codigo=registro['CO-FORMA-ENTRADA-POS-PCA'])[0]
                data_inicio_posicionamento_pca = strptime_or_default(registro['DA-INI-POSICIONAMENTO-PCA'], '%Y%m%d')
                kwargs = {
                    'codigo_pca_posicionamento': codigo_pca,
                    'codigo_posicionamento_pca': codigo_posicionamento,
                    'forma_entrada': forma_entrada,
                    'data_inicio_posicionamento_pca': data_inicio_posicionamento_pca,
                    'data_fim_posicionamento_pca': strptime_or_default(registro['DA-FIM-POSICIONAMENTO-PCA'], '%Y%m%d'),
                }
                pca = PCA.objects.filter(codigo_pca=codigo_pca).first()
                if pca:
                    kwargs['pca'] = pca
                    PosicionamentoPCA.objects.update_or_create(
                        codigo_posicionamento_pca=codigo_posicionamento,
                        codigo_pca_posicionamento=codigo_pca,
                        forma_entrada=forma_entrada,
                        data_inicio_posicionamento_pca=data_inicio_posicionamento_pca,
                        defaults=kwargs,
                    )

    def importar_servidor_afastamentos(self, itens):
        self.calc_caches()
        for i in itens:
            servidor_id = self.servidores_cache.get(extrai_matricula(i['GR-MATRICULA']))
            afastamento_id = self.afastamentos_cache.get(i['IT-CO-AFASTAMENTO-SERV'])

            if not afastamento_id or not servidor_id:
                continue
            cancelado = int(i['IT-CO-MOTIVO-CANCELA-AFAST']) > 0 or strptime_or_default(i['IT-DA-CANCELA-AFASTAMENTO'], '%Y%m%d') is not None
            tem_efeito_financeiro = i['IT-IN-EFEITO-FINANCEIRO-SERV'] == 'S'
            data_inicio = strptime_or_default(i['IT-DA-INICIO-AFASTAMENTO-SERV'], '%Y%m%d')
            qtd_minutos = i['IT-QT-MINUTOS-AFASTAMENTO-SERV']
            kwargs = {
                'data_termino': strptime_or_default(i['IT-DA-TERMINO-AFASTAMENTO-SERV'], '%Y%m%d'),
                'tem_efeito_financeiro': tem_efeito_financeiro,
                'cancelado': cancelado,
                'qtd_minuto_afastamento': qtd_minutos,
            }
            ServidorAfastamento.objects.update_or_create(
                servidor_id=servidor_id, afastamento_id=afastamento_id, data_inicio=data_inicio, defaults=kwargs
            )

    def importar_emails(self, itens):
        log.info('importando emails')
