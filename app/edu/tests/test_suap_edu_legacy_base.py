import datetime

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command

from comum.models import Ano, Configuracao, Municipio, Predio, PrestadorServico, Raca, Sala, User, UsuarioGrupo, UsuarioGrupoSetor, Vinculo
from djtools.templatetags.filters import format_
from djtools.utils import is_ldap_enabled, somar_dias
from edu import q_academico
from edu.forms import AtividadeComplementarForm
from edu.models import (
    AbonoFaltas,
    Aluno,
    AreaCapes,
    AreaCurso,
    AtividadeComplementar,
    AtividadePolo,
    Aula,
    CalendarioAcademico,
    Cartorio,
    Cidade,
    Componente,
    ComponenteCurricular,
    ConfiguracaoAtividadeComplementar,
    ConfiguracaoAvaliacao,
    ConfiguracaoCertificadoENEM,
    ConfiguracaoLivro,
    ConfiguracaoPedidoMatricula,
    Convenio,
    ConvocacaoENADE,
    Credenciamento,
    CursoCampus,
    CursoFormacaoSuperior,
    Diario,
    Diretoria,
    Disciplina,
    EixoTecnologico,
    EquivalenciaComponenteQAcademico,
    Estado,
    EstruturaCurso,
    FormaIngresso,
    HistoricoRelatorio,
    HorarioAula,
    HorarioAulaDiario,
    HorarioCampus,
    InstituicaoEnsinoSuperior,
    ItemConfiguracaoAtividadeComplementar,
    ItemConfiguracaoAvaliacao,
    JustificativaDispensaENADE,
    LinhaPesquisa,
    MaterialAula,
    MaterialDiario,
    MatriculaDiario,
    MatriculaPeriodo,
    Matriz,
    MatrizCurso,
    Mensagem,
    Modalidade,
    MotivoAusenciaEscolar,
    NaturezaParticipacao,
    NivelEnsino,
    Nucleo,
    NucleoCentralEstruturante,
    PedidoMatricula,
    Polo,
    ProcedimentoMatricula,
    Professor,
    ProfessorDiario,
    ProjetoFinal,
    RegistroConvocacaoENADE,
    RegistroEmissaoCertificadoENEM,
    RegistroEmissaoDiploma,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    SolicitacaoCertificadoENEM,
    SolicitacaoRelancamentoEtapa,
    SolicitacaoUsuario,
    TipoAtividadeComplementar,
    TipoComponente,
    TipoProfessorDiario,
    Turma,
    Turno,
)
from edu.models.cadastros_gerais import AreaCursoFormacaoSuperior, Pais
from freezegun import freeze_time
from processo_seletivo.models import Candidato, CandidatoVaga, Edital, Lista, OfertaVagaCurso, WebService
from protocolo.models import Processo
from rh.enums import Nacionalidade

q_academico.DAO = q_academico.MockDAO


@pytest.mark.django_db
class EduTestCase:
    SALVAR_NOVA_PLANILHA = True
    ANUAL = '1'
    SEMESTRAL = '2'
    LIVRE = '3'
    CENARIOS = frozenset({'fic', 'pos', 'matricula_online', 'graduacao'})

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @pytest.fixture(autouse=True)
    def _auto_setup(self, atores_edu):
        self.initial_data = {}
        for nome, valor in vars(atores_edu).items():
            setattr(self, nome, valor)

        self.servidor_a.get_user().groups.add(Group.objects.get(name='Administrador Acadêmico'))

        self.servidor_c.get_user().groups.add(Group.objects.get(name='Diretor de Avaliação e Regulação do Ensino'))

        self.servidor_d.get_user().groups.add(Group.objects.get(name='Operador ENADE'))

        self.ano_2013 = Ano.objects.get_or_create(ano=2013)[0]
        self.ano_2014 = Ano.objects.get_or_create(ano=2014)[0]
        self.ano_atual = Ano.objects.get_or_create(ano=datetime.datetime.now().year)[0]

        Configuracao.objects.get_or_create(app='ldap_backend', chave='dominio_institucional', valor='ifrn.edu.br', descricao='...')
        Configuracao.objects.get_or_create(app='ldap_backend', chave='dominio_academico', valor='academico.ifrn.edu.br', descricao='...')
        Configuracao.objects.get_or_create(app='ldap_backend', chave='dominio_google_classroom', valor='escolar.ifrn.edu.br', descricao='...')

        Configuracao.objects.get_or_create(app='edu', chave='ano_letivo_atual', valor='2013')
        Configuracao.objects.get_or_create(app='edu', chave='periodo_letivo_atual', valor='2')
        Configuracao.objects.get_or_create(app='edu', chave='professor_externo_ocupacao_padrao', valor=str(self.ocupacao_professor_externo.id))
        Configuracao.objects.get_or_create(app='edu', chave='professor_externo_dias_vencimento_contrato', valor='720')

        # CADASTROS BÁSICOS
        pais = Pais.objects.get_or_create(nome='Brasil')[0]
        estado = Estado.objects.get_or_create(nome='Rio Grande do Norte', id=24)[0]
        cidade = Cidade.objects.get_or_create(nome='Natal', estado_id=estado.pk, cep_inicial='', cep_final='', codigo='2401403', pais_id=pais.pk)[0]
        Cartorio.objects.get_or_create(nome='Natal', cidade_id=cidade.pk, serventia='')
        predio = Predio.objects.get_or_create(nome='Prédio Padrão', uo=self.servidor_b.setor.uo, ativo=True)[0]
        Sala.objects.get_or_create(nome='Sala Padrão', ativa=True, predio=predio)

        self.raca = Raca.objects.get_or_create(descricao='Parda', codigo_censup='3', codigo_siape=4, inativo_siape=False)[0]

        self.carga_inicial()

    def logout(self):
        self.client.get('/comum/logout/')
        self.client.user = None

    def assert_no_validation_errors(self, response, url=None, data=None, content=None):
        errors = []
        erro_note = ''
        for line in response.content.decode().split('\n'):
            if line.find('"errorlist"') > 0:
                errors.append(line[line.find('<li') + 4 : line.find('</li')])
            elif line.find(' errornote ') > 0 or erro_note:
                index_inicial = line.find('<p')
                index_final = line.find('</p>')
                if index_final > 0 and index_inicial < index_final:
                    erro_note += line[index_inicial:index_final]
                    break
                elif index_final > 0 and (index_inicial < 0 or index_inicial > index_final):
                    erro_note += line[: index_final + 4]
                    break
                elif index_inicial > 0 > index_final:
                    erro_note += line[index_inicial:]
                elif index_inicial < 0 and index_final < 0 and erro_note:
                    erro_note += line[:]
        if erro_note:
            errors.append(erro_note)
        if errors:
            file = open('/tmp/testcase.html', 'w')
            file.write(response.content.decode())
            file.close()
            raise Exception('Erros apresentados no form:\n' + ('\n'.join(errors)) + f'\n{url}\n{data}\n{content}')
        return True

    def tearDown(self):
        if settings.SUAP_TESTS['SALVAR_CENARIO']:
            self.salvar_planilha(EduTestCase.SALVAR_NOVA_PLANILHA)
            if EduTestCase.SALVAR_NOVA_PLANILHA:
                EduTestCase.SALVAR_NOVA_PLANILHA = False

    def carga_inicial(self):
        """
        Cria os cadastros prévios necessários para a dinâmica da aplicação EDU, isto é, realiza os
        cadastros das macro atividades "Realizar Cadastros Gerais", "Vincular Usuários às Diretórias",
        "Configurar Horários dos Campi" e "Cadastrar Cursos".
        """

        # CADASTROS GERAIS
        self.acessar_como_administrador()
        area = self.cadastrar_area_curso('Educação')
        diretoria_academica = self.cadastrar_diretoria(self.servidor_b.setor.pk)
        eixo = EixoTecnologico.objects.get_or_create(descricao='Ambiente e Saúde', codigo_inep='1')[0]
        area_capes = self.cadastrar_area_capes('Ciências Exatas e da Terra')
        natureza_participacao = self.cadastrar_natureza_participacao('Presencial')
        self.cadastrar_credenciamento(natureza_participacao.pk)
        self.cadastrar_motivo_ausencia_escolar('Doença')
        nucleo = self.cadastrar_nucleo('Articulador')
        self.cadastrar_tipo_professor_diario('Principal')
        self.cadastrar_disciplina_professor('Matemática')
        self.cadastrar_nucleo_central_estruturante('Biologia')
        turno = self.retornar(Turno, chaves={'descricao': 'Matutino'})

        # CADASTROS GERAIS FIC
        self.cadastrar_convenio('PRONATEC')
        self.cadastrar_forma_ingresso('Matrícula Direta')
        tipo_componente_fic = self.cadastrar_tipos_componente('FIC')

        # CADASTROS GERAIS PÓS
        self.cadastrar_tipo_atividade_complementar('Mesa Redonda')
        self.cadastrar_tipo_atividade_complementar('Palestra')

        # CADASTROS GERAIS PÓS - processo seletivo
        self.cadastrar_linha_pesquisa()
        self.cadastrar_forma_ingresso('Processo Seletivo')
        tipo_componente_pos = self.cadastrar_tipos_componente('POS')
        self.cadastrar_tipo_professor_diario('Principal')

        # CADASTROS GERAIS PÓS - integração Q-Acadêmico
        self.cadastrar_forma_ingresso('Integração Q-Acadêmico')

        # CADASTROS EAD
        self.cadastrar_polo()

        # VINCULAÇÃO DOS USUÁRIOS E CADASTRO DOS HORÁRIOS DAS AULAS
        self.vincular_usuario_a_diretoria('Secretário Acadêmico')
        self.configurar_horario_campus('Horário Padrão', turno, self.servidor_b.setor, ('07:00-08:00', '08:00-09:00', '10:00-11:00'))

        _cenarios = self.CENARIOS
        # O curso de graduação reusa a matriz/estrutura de pós-crédito construídas no bloco de
        # matrícula online; por isso CENARIOS={'graduacao'} também dispara o bloco matrícula online.
        _build_matricula = bool(_cenarios & {'matricula_online', 'graduacao'})
        if 'fic' in _cenarios:
            # CADASTRO DO CURSO FIC
            estrutura_fic = self.cadastrar_estrutura_curso(
                descricao='PRONATEC / FICs 75%', tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_FIC, limite_reprovacao='0', qtd_minima_disciplinas='0'
            )
            componente_fic = self.cadastrar_componente_curricular(
                tipo_componente_fic,
                descricao='Administração da propriedade rural',
                descricao_historico='Administração da propriedade rural',
                tipo=tipo_componente_fic.pk,
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.FUNDAMENTAL,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='10',
            )
            matriz_fic = self.cadastrar_matriz(
                descricao='FIC em Agricultor Familiar [PRONATEC]',
                ano_criacao=self.ano_2013.pk,
                nivel_ensino=NivelEnsino.FUNDAMENTAL,
                natureza_participacao=natureza_participacao.pk,
                qtd_periodos_letivos='1',
                estrutura=estrutura_fic.pk,
                ch_componentes_obrigatorios='150',
                ch_componentes_tcc='0',
                ch_componentes_extensao='0',
                ch_componentes_com_extensao='0',
            )
            self.replicar_matriz()
            self.vincular_componente(
                matriz_fic, componente_fic, periodo_letivo='1', tipo='1', qtd_avaliacoes='1', nucleo=nucleo.pk, ch_presencial='10', ch_pratica='0'
            )
            data = {
                'descricao': 'FIC+ Agricultor Familiar [PRONATEC]',
                'descricao_historico': 'Agricultor Familiar',
                'ano_letivo': self.ano_2013.pk,
                'periodo_letivo': '1',
                'data_inicio': '17/06/2013',
                'data_fim': '',
                'ativo': 'on',
                'codigo': '0981',
                'turno': turno.pk,
                'modalidade': Modalidade.FIC,
                'area': area.pk,
                'eixo': eixo.pk,
                'area_capes': area_capes.pk,
                'estrutura': estrutura_fic.pk,
                'periodicidade': CursoCampus.PERIODICIDADE_LIVRE,
                'diretoria': diretoria_academica.pk,
                'emite_diploma': True,
                'titulo_certificado_masculino': 'Agricultor',
                'titulo_certificado_feminino': 'Agricultora',
                'quantidade_vagas': '10',
            }
            curso_fic = self.cadastrar_curso(data)
            self.replicar_curso()
            self.vincular_matriz_curso(matriz_fic, curso_fic)

        if 'pos' in _cenarios:
            # CADASTRO DO CURSO PÓS
            estrutura_pos = self.cadastrar_estrutura_curso(
                descricao='PÓS-GRADUAÇAO (SERIADO)',
                tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO,
                limite_reprovacao='2',
                qtd_minima_disciplinas='3',
            )
            componente_pos_a = self.cadastrar_componente_curricular(
                tipo_componente_pos,
                descricao='Administração da propriedade rural',
                descricao_historico='Administração da propriedade rural',
                tipo=tipo_componente_pos.pk,
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='10',
            )
            componente_pos_b = self.cadastrar_componente_curricular(
                tipo_componente_pos,
                descricao='Ambulatório de dependência química',
                descricao_historico='Ambulatório de dependência química',
                tipo=tipo_componente_pos.pk,
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='10',
            )
            componente_pos_c = self.cadastrar_componente_curricular(
                tipo_componente_pos,
                descricao='Projeto Final',
                descricao_historico='projeto final',
                tipo=tipo_componente_pos.pk,
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='10',
            )

            matriz_pos = self.cadastrar_matriz(
                descricao='Mestrado em Agricultor Familiar',
                ano_criacao=self.ano_2013.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                natureza_participacao=natureza_participacao.pk,
                qtd_periodos_letivos='3',
                estrutura=estrutura_pos.pk,
                ch_componentes_obrigatorios='20',
                ch_componentes_tcc='10',
                ch_componentes_extensao='0',
                ch_componentes_com_extensao='0',
            )
            self.vincular_componente(
                matriz_pos, componente_pos_a, periodo_letivo='1', tipo='1', qtd_avaliacoes='1', nucleo=nucleo.pk, ch_presencial='10', ch_pratica='0'
            )
            self.vincular_componente(
                matriz_pos, componente_pos_b, periodo_letivo='2', tipo='1', qtd_avaliacoes='1', nucleo=nucleo.pk, ch_presencial='10', ch_pratica='0'
            )
            self.vincular_componente(
                matriz_pos, componente_pos_c, periodo_letivo='3', tipo='4', qtd_avaliacoes='1', nucleo=nucleo.pk, ch_presencial='10', ch_pratica='0'
            )
            data = {
                'descricao': 'Mestrado em Agricultor Familiar',
                'descricao_historico': 'Agricultor Familiar',
                'ano_letivo': self.ano_2013.pk,
                'periodo_letivo': '1',
                'data_inicio': '17/06/2013',
                'data_fim': '',
                'ativo': 'on',
                'codigo': '0989',
                'turno': turno.pk,
                'modalidade': Modalidade.MESTRADO,
                'area': area.pk,
                'eixo': eixo.pk,
                'area_capes': area_capes.pk,
                'estrutura': estrutura_pos.pk,
                'periodicidade': CursoCampus.PERIODICIDADE_SEMESTRAL,
                'diretoria': diretoria_academica.pk,
                'emite_diploma': True,
                'titulo_certificado_masculino': 'Mestre',
                'titulo_certificado_feminino': 'Mestra',
                'quantidade_vagas': '10',
            }
            curso_pos = self.cadastrar_curso(data)
            self.vincular_matriz_curso(matriz_pos, curso_pos)

        if _build_matricula:
            # CADASTRO CURSOS PARA MATRÍCULA ONLINE
            estrutura_pos_seriado = self.cadastrar_estrutura_curso(
                descricao='PÓS-GRADUAÇAO SERIADO',
                ativo=True,
                tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO,
                limite_reprovacao='1',
                criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
                media_aprovacao_sem_prova_final='70',
                media_evitar_reprovacao_direta='50',
                media_aprovacao_avaliacao_final='70',
                percentual_frequencia='75',
                ira=EstruturaCurso.IRA_ARITMETICA_NOTAS_FINAIS,
                qtd_periodos_conclusao=0,
                qtd_max_reprovacoes_periodo=0,
                qtd_max_reprovacoes_disciplina=0,
                percentual_max_aproveitamento=0,
                numero_max_certificacoes=0,
                media_certificacao_conhecimento=0,
            )

            estrutura_pos_credito = self.cadastrar_estrutura_curso(
                descricao='PÓS-GRADUAÇAO CRÉDITO',
                ativo=True,
                tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_CREDITO,
                qtd_minima_disciplinas='1',
                numero_disciplinas_superior_periodo='1',
                qtd_max_periodos_subsequentes='1',
                numero_max_cancelamento_disciplina='1',
                criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
                media_aprovacao_sem_prova_final='70',
                media_evitar_reprovacao_direta='50',
                media_aprovacao_avaliacao_final='70',
                percentual_frequencia='75',
                ira=EstruturaCurso.IRA_ARITMETICA_NOTAS_FINAIS,
                qtd_periodos_conclusao=0,
                qtd_max_reprovacoes_periodo=0,
                qtd_max_reprovacoes_disciplina=0,
                percentual_max_aproveitamento=0,
                numero_max_certificacoes=0,
                media_certificacao_conhecimento=0,
            )

            componente_pos_a1 = self.cadastrar_componente_curricular(
                tipo_componente_pos,
                descricao='A1',
                descricao_historico='A1',
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='4',
            )

            componente_pos_a2 = self.cadastrar_componente_curricular(
                tipo_componente_pos,
                descricao='A2',
                descricao_historico='A2',
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='4',
            )

            componente_pos_b1 = self.cadastrar_componente_curricular(
                tipo_componente_pos,
                descricao='B1',
                descricao_historico='B1',
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='4',
            )

            componente_pos_b2 = self.cadastrar_componente_curricular(
                tipo_componente_pos,
                descricao='B2',
                descricao_historico='B2',
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='4',
            )

            componente_pos_op1 = self.cadastrar_componente_curricular(
                tipo_componente_pos,
                descricao='OP1',
                descricao_historico='OP1',
                diretoria=diretoria_academica.pk,
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                ch_hora_relogio='10',
                ch_hora_aula='10',
                ch_qtd_creditos='4',
            )

            matriz_pos_optativa_credito = self.cadastrar_matriz(
                descricao='Mestrado',
                ano_criacao=self.ano_2013.pk,
                periodo_criacao='1',
                data_inicio='11/06/2013',
                data_fim='',
                ativo='on',
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                natureza_participacao=natureza_participacao.pk,
                qtd_periodos_letivos='2',
                estrutura=estrutura_pos_credito.pk,
                ch_componentes_obrigatorios='40',
                ch_componentes_optativos='10',
                ch_componentes_eletivos='10',
                ch_seminarios='0',
                ch_componentes_tcc='10',
                ch_pratica_profissional='0',
                ch_atividades_complementares='0',
                ch_componentes_extensao='0',
                ch_componentes_com_extensao='0',
            )

            self.vincular_componente(
                matriz_pos_optativa_credito,
                componente_pos_a1,
                periodo_letivo='1',
                tipo='1',
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )
            self.vincular_componente(
                matriz_pos_optativa_credito,
                componente_pos_a2,
                periodo_letivo='1',
                tipo='1',
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )
            self.vincular_componente(
                matriz_pos_optativa_credito,
                componente_pos_b1,
                periodo_letivo='2',
                tipo='1',
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )
            self.vincular_componente(
                matriz_pos_optativa_credito,
                componente_pos_b2,
                periodo_letivo='2',
                tipo='1',
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )
            self.vincular_componente(
                matriz_pos_optativa_credito,
                componente_pos_op1,
                tipo='1',
                optativo=True,
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )

            matriz_pos_optativa_seriado = self.cadastrar_matriz(
                descricao='Mestrado',
                ano_criacao=self.ano_2013.pk,
                periodo_criacao='1',
                data_inicio='11/06/2013',
                data_fim='',
                ativo='on',
                nivel_ensino=NivelEnsino.POS_GRADUACAO,
                natureza_participacao=natureza_participacao.pk,
                qtd_periodos_letivos='2',
                estrutura=estrutura_pos_seriado.pk,
                ch_componentes_obrigatorios='40',
                ch_componentes_optativos='10',
                ch_componentes_eletivos='10',
                ch_seminarios='0',
                ch_componentes_tcc='10',
                ch_pratica_profissional='0',
                ch_atividades_complementares='0',
                ch_componentes_extensao='0',
                ch_componentes_com_extensao='0',
            )

            self.vincular_componente(
                matriz_pos_optativa_seriado,
                componente_pos_a1,
                periodo_letivo='1',
                tipo='1',
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )
            self.vincular_componente(
                matriz_pos_optativa_seriado,
                componente_pos_a2,
                periodo_letivo='1',
                tipo='1',
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )
            self.vincular_componente(
                matriz_pos_optativa_seriado,
                componente_pos_b1,
                periodo_letivo='2',
                tipo='1',
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )
            self.vincular_componente(
                matriz_pos_optativa_seriado,
                componente_pos_b2,
                periodo_letivo='2',
                tipo='1',
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )
            self.vincular_componente(
                matriz_pos_optativa_seriado,
                componente_pos_op1,
                tipo='1',
                optativo=True,
                qtd_avaliacoes='1',
                nucleo=nucleo.pk,
                ch_presencial='10',
                ch_pratica='0',
            )

            data = {
                'descricao': 'Mestrado Seriado',
                'descricao_historico': 'Mestrado Seriado',
                'ano_letivo': self.ano_2013.pk,
                'periodo_letivo': '1',
                'data_inicio': '17/06/2013',
                'data_fim': '',
                'ativo': 'on',
                'codigo': '9999',
                'turno': turno.pk,
                'modalidade': Modalidade.MESTRADO,
                'area': area.pk,
                'eixo': eixo.pk,
                'area_capes': area_capes.pk,
                'estrutura': estrutura_pos_seriado.pk,
                'periodicidade': CursoCampus.PERIODICIDADE_SEMESTRAL,
                'diretoria': diretoria_academica.pk,
                'emite_diploma': True,
                'titulo_certificado_masculino': 'Mestre',
                'titulo_certificado_feminino': 'Mestra',
                'quantidade_vagas': '10',
            }
            curso_pos_seriado = self.cadastrar_curso(data)
            self.vincular_matriz_curso(matriz_pos_optativa_seriado, curso_pos_seriado)

            data = {
                'descricao': 'Mestrado Crédito',
                'descricao_historico': 'Mestrado Crédito',
                'ano_letivo': self.ano_2013.pk,
                'periodo_letivo': '1',
                'data_inicio': '17/06/2013',
                'data_fim': '',
                'ativo': 'on',
                'codigo': '8888',
                'turno': turno.pk,
                'modalidade': Modalidade.MESTRADO,
                'area': area.pk,
                'eixo': eixo.pk,
                'area_capes': area_capes.pk,
                'estrutura': estrutura_pos_credito.pk,
                'periodicidade': CursoCampus.PERIODICIDADE_SEMESTRAL,
                'diretoria': diretoria_academica.pk,
                'emite_diploma': True,
                'titulo_certificado_masculino': 'Mestre',
                'titulo_certificado_feminino': 'Mestra',
                'quantidade_vagas': '10',
            }
            curso_pos_credito = self.cadastrar_curso(data)
            self.vincular_matriz_curso(matriz_pos_optativa_credito, curso_pos_credito)

        if 'graduacao' in _cenarios:
            # CURSO GRADUACAO

            area_curso_formacao_superior, _ = AreaCursoFormacaoSuperior.objects.update_or_create(
                codigo_cine='0111C012',
                defaults={
                    'cine': 'Ciência da educação - Bacharelado',
                    'codigo_area_geral': '01',
                    'area_geral': 'Educação',
                    'codigo_area_especifica': '011',
                    'area_especifica': 'Educação',
                    'codigo_area_detalhada': '0111',
                    'area_detalhada': 'Ciência da educação',
                },
            )
            data = {
                'descricao': 'Ciência da educação',
                'descricao_historico': 'Ciência da educação',
                'ano_letivo': self.ano_2013.pk,
                'periodo_letivo': '1',
                'data_inicio': '17/06/2013',
                'data_fim': '',
                'ativo': 'on',
                'codigo': '8887',
                'turno': turno.pk,
                'modalidade': Modalidade.LICENCIATURA,
                'area_curso_formacao_superior': area_curso_formacao_superior.pk,
                'area': area.pk,
                # eixo=eixo.pk,
                # area_capes=area_capes.pk,
                'estrutura': estrutura_pos_credito.pk,
                'periodicidade': CursoCampus.PERIODICIDADE_SEMESTRAL,
                'diretoria': diretoria_academica.pk,
                'emite_diploma': True,
                'exige_enade': True,
                'titulo_certificado_masculino': 'Licenciado',
                'titulo_certificado_feminino': 'Licenciada',
                'quantidade_vagas': '10',
            }
            curso_graduacao = self.cadastrar_curso(data)
            self.vincular_matriz_curso(matriz_pos_optativa_credito, curso_graduacao)

        # cadastrando professor servidor
        self.cadastrar_professor_servidor()
        self.acessar_como_professor()

    def recarregar(self, objeto):
        return objeto.__class__.objects.get(pk=objeto.pk)

    def retornar(self, cls, qtd=1, chaves=None):
        if chaves is None:
            chaves = {}
        if self.initial_data.get(cls.__name__):
            return self.initial_data[cls.__name__]
        if chaves:
            return cls.objects.get(**chaves)
        if qtd == 1:
            return cls.objects.latest('id')
        else:
            return cls.objects.all().order_by('-id')[0:qtd]

    def salvar_planilha(self, novo=False):
        from os import path

        import pandas as pd
        from django.apps import apps

        FILE_PATH = '/tmp/planilha.xlsx'

        if path.exists(FILE_PATH) and not novo:
            # Load existing excel file
            with pd.ExcelFile(FILE_PATH) as xls:
                # Create a dictionary of dataframes
                dfs = {sheet_name: xls.parse(sheet_name) for sheet_name in xls.sheet_names}
        else:
            dfs = {}

        # Prepare data for the new sheet
        data = []

        app = apps.get_app_config('edu')
        for model in apps.get_models(app):
            m2m = []
            fields = []
            for field in model._meta.many_to_many:
                m2m.append(field.name)
            for field in model._meta.fields:
                fields.append(field.name)

            model_rows = []
            model_columns = []
            for o in model.objects.all():
                row = []
                for field_name in fields:
                    if field_name not in m2m and 'documento' not in field_name:
                        v = hasattr(o, field_name) and getattr(o, field_name) or None
                        if not model_rows:
                            model_columns.append(field_name)
                        row.append(str(format_(v)))
                model_rows.append(row)

            if model_rows and not model.__name__.startswith('Log') and not model.__name__.startswith('Registro'):
                # Add model name as a header row (simulated by adding it to data)
                # In pandas, we usually write to separate sheets or just append data.
                # Given the original logic was writing everything to one sheet named after the test class,
                # but iterating over models and writing them sequentially in the same sheet.

                # Original logic:
                # sheet.write(count, 0, model.__name__)
                # count += 1
                # write headers
                # count += 1
                # write rows
                # count += 2

                data.append([model.__name__] + [''] * (len(model_columns) - 1 if model_columns else 0))
                data.append(model_columns)
                data.extend(model_rows)
                data.append([])  # Empty row
                data.append([])  # Empty row

        # Create DataFrame for the new sheet
        # Since the data has varying columns, we can't easily create a structured DF.
        # But we can create a DF of objects/strings.
        new_df = pd.DataFrame(data)

        dfs[self.__class__.__name__] = new_df

        # Save all sheets
        with pd.ExcelWriter(FILE_PATH) as writer:
            for sheet_name, df in dfs.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

    def to_html(self, response):
        with open('/tmp/testcase.html', 'w+b') as f:
            f.write(response.content)

    def cadastrar(self, cls, data):
        """Cria um cadastro auxiliar via ORM (em vez de 3 requisições ao admin).

        Estes são dados de apoio do cenário (não o alvo dos testes); criá-los
        diretamente — `create()` ainda dispara `save()`/sinais — torna a
        `carga_inicial` muito mais rápida sem alterar o estado resultante.
        """
        qs = cls.objects.filter(descricao=data['descricao'])
        if qs:
            return qs[0]
        return self._orm_create(cls, data)

    def _orm_create(self, cls, data, manager='objects'):
        """Cria `cls` por ORM a partir de um dict no formato dos forms do admin.

        Converte os valores como o admin faria — FK por pk vira `<campo>_id`,
        datas `dd/mm/aaaa` viram `date`, checkbox `'on'` vira `True` — ignora as
        chaves de management dos formsets e aplica M2M após o create. `create()`
        ainda dispara `save()`/sinais, então o estado resultante é equivalente ao
        do POST, sem o custo das requisições ao admin.
        """
        m2m = {}
        kwargs = {}
        for campo, valor in data.items():
            if '_set-' in campo or campo.endswith(('-TOTAL_FORMS', '-INITIAL_FORMS', '-MAX_NUM_FORMS')):
                continue  # management form de formset — sem filhos a criar aqui
            try:
                field = cls._meta.get_field(campo)
            except Exception:
                continue
            tipo = field.get_internal_type()
            if field.many_to_many:
                m2m[campo] = valor
            elif field.is_relation and valor not in (None, '') and not hasattr(valor, 'pk'):
                kwargs[field.attname] = valor  # FK por pk -> attname (ex.: uo_id)
            elif tipo in ('DateField', 'DateTimeField') and isinstance(valor, str):
                kwargs[campo] = datetime.datetime.strptime(valor, '%d/%m/%Y') if valor else None
            elif tipo == 'BooleanField':
                kwargs[campo] = True if valor == 'on' else valor
            elif valor == '':
                kwargs[campo] = '' if not field.null else None
            elif isinstance(valor, str):
                # coage a string para o tipo do campo, como o form do admin faria ('10' -> 10).
                try:
                    kwargs[campo] = field.to_python(valor)
                except Exception:
                    kwargs[campo] = valor
            else:
                kwargs[campo] = valor
        obj = getattr(cls, manager).create(**kwargs)
        for campo, valores in m2m.items():
            if valores in (None, ''):
                continue
            if not isinstance(valores, (list, tuple, set)):
                valores = [valores]  # admin aceita valor único para M2M; o ORM exige iterável
            getattr(obj, campo).set(valores)
        return obj

    def _login_if_needed(self, username):
        current_user = getattr(self.client, 'user', None)
        if getattr(current_user, 'username', None) == username:
            return
        if current_user is not None:
            self.logout()
        successful = self.client.login(username=username, password='123')
        assert successful is True

    def acessar_como_administrador(self):
        self._login_if_needed(self.servidor_a.get_user().username)

    def acessar_como_secretario(self):
        self._login_if_needed(self.servidor_b.get_user().username)

    def acessar_como_regulador_avaliador(self):
        self._login_if_needed(self.servidor_c.get_user().username)

    def acessar_como_operador_enade(self):
        self._login_if_needed(self.servidor_d.get_user().username)

    def acessar_como_professor(self):
        professor = self.retornar(Professor)
        self._login_if_needed(professor.vinculo.user.username)

    def acessar_como_aluno(self):
        aluno = self.retornar(Aluno)
        self._login_if_needed(aluno.matricula)

    def cadastrar_area_curso(self, descricao):
        return self.cadastrar(AreaCurso, {'descricao': descricao})

    def cadastrar_disciplina_professor(self, descricao):
        return self.cadastrar(Disciplina, {'descricao': descricao})

    def cadastrar_nucleo_central_estruturante(self, descricao):
        return self.cadastrar(NucleoCentralEstruturante, {'descricao': descricao})

    def atualizar_configuracao_avaliacao(self, configuracao_avaliacao, forma_calculo, itens, divisor=None):
        url = f'/admin/edu/configuracaoavaliacao/{configuracao_avaliacao.pk}/change/'
        response = self.client.get(url, follow=True)
        assert 'Editar ' in response.content.decode()
        count = ConfiguracaoAvaliacao.objects.all().count()
        data = {
            'forma_calculo': forma_calculo,
            'itemconfiguracaoavaliacao_set-TOTAL_FORMS': len(itens),
            'itemconfiguracaoavaliacao_set-INITIAL_FORMS': configuracao_avaliacao.itemconfiguracaoavaliacao_set.count(),
            'itemconfiguracaoavaliacao_set-MAX_NUM_FORMS': '1000',
        }

        if divisor:
            data.update({'divisor': divisor})
        else:
            data.update({'divisor': ''})

        i = 0
        for item in itens:
            item_qs = configuracao_avaliacao.itemconfiguracaoavaliacao_set.all()
            item_avaliacao = item_qs.count() > i and item_qs[i] or None
            s = f'itemconfiguracaoavaliacao_set-{i:d}-id'
            data[s] = item_avaliacao and item_avaliacao.pk or ''
            s = f'itemconfiguracaoavaliacao_set-{i:d}-tipo'
            data[s] = item.get('tipo')
            s = f'itemconfiguracaoavaliacao_set-{i:d}-sigla'
            data[s] = item.get('sigla')
            s = f'itemconfiguracaoavaliacao_set-{i:d}-descricao'
            data[s] = item.get('sigla')
            s = f'itemconfiguracaoavaliacao_set-{i:d}-nota_maxima'
            data[s] = item.get('nota_maxima')
            if item.get('peso'):
                s = f'itemconfiguracaoavaliacao_set-{i}-peso'
                data[s] = item.get('peso')
            i += 1

        response = self.client.post(url, data, follow=True)
        assert ConfiguracaoAvaliacao.objects.all().count() == count
        return self.retornar(ConfiguracaoAvaliacao)

    def cadastrar_diretoria(self, setor=None):
        if not setor:
            setor = self.servidor_b.setor.pk
        data = {
            'setor': setor,
            'tipo': 1,
            'titulo_autoridade_maxima_masculino': 'Reitor',
            'titulo_autoridade_maxima_feminino': 'Reitora',
            'titulo_autoridade_uo_masculino': 'Diretor Geral',
            'titulo_autoridade_uo_feminino': 'Diretora Geral',
            'titulo_autoridade_diretoria_masculino': 'Diretor Acadêmico',
            'titulo_autoridade_diretoria_feminino': 'Diretora Acadêmica',
        }
        return self._orm_create(Diretoria, data)

    def cadastrar_area_capes(self, descricao):
        return self.cadastrar(AreaCapes, {'descricao': descricao})

    def cadastrar_forma_ingresso(self, descricao):
        return self.cadastrar(FormaIngresso, {'descricao': descricao, 'ativo': True})

    def cadastrar_convenio(self, descricao):
        return self.cadastrar(Convenio, {'descricao': descricao})

    def cadastrar_natureza_participacao(self, descricao):
        return self.cadastrar(NaturezaParticipacao, {'descricao': descricao})

    def cadastrar_credenciamento(self, natureza_participacao_id):
        data = {
            'tipo': Credenciamento.CREDECIAMENTO,
            'natureza_participacao': natureza_participacao_id,
            'tipo_ato': 'Portaria',
            'numero_ato': '123',
            'data_ato': '01/01/2020',
            'numero_publicacao': '456',
            'data_publicacao': '02/01/2020',
            'veiculo_publicacao': 'DOU',
            'secao_publicacao': '1',
            'pagina_publicacao': '10',
        }
        return self._orm_create(Credenciamento, data)

    def cadastrar_motivo_ausencia_escolar(self, descricao):
        return self.cadastrar(MotivoAusenciaEscolar, {'descricao': descricao, 'ativo': True, 'possui_previsao_normativa': True})

    def cadastrar_nucleo(self, descricao):
        return self.cadastrar(Nucleo, {'descricao': descricao})

    def cadastrar_linha_pesquisa(self):
        return self.cadastrar(LinhaPesquisa, {'descricao': 'Educação'})

    def cadastrar_tipo_professor_diario(self, descricao):
        return self.cadastrar(TipoProfessorDiario, {'descricao': descricao})

    def cadastrar_tipo_atividade_complementar(self, descricao):
        return self.cadastrar(TipoAtividadeComplementar, {'descricao': descricao, 'modalidades': [Modalidade.MESTRADO, Modalidade.FIC]})

    def cadastrar_tipos_componente(self, descricao):
        return self._orm_create(TipoComponente, {'descricao': descricao})

    def vincular_usuario_a_diretoria(self, nome):
        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=Group.objects.get(name=nome), user=self.servidor_b.get_user())[0]
        UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=self.servidor_b.setor)

    def configurar_horario_campus(self, descricao, turno, setor, lista_horarios):
        qs = HorarioCampus.locals.filter(descricao=descricao)
        if qs:
            return qs[0]
        horario_campus = HorarioCampus.objects.create(descricao=descricao, uo_id=setor.uo_id, ativo=True)
        for i, h in enumerate(lista_horarios):
            HorarioAula.objects.create(
                horario_campus=horario_campus,
                numero=i + 1,
                turno=turno,
                inicio=h[0:5],
                termino=h[6:11],
            )
        assert horario_campus.horarioaula_set.count() == 3
        return horario_campus

    def cadastrar_calendario_academico(self, ano=None, periodo=None, tipo=CalendarioAcademico.TIPO_TEMPORARIO, **params):
        if not ano:
            ano = self.ano_2013
        if not periodo:
            periodo = '1'

        url = '/admin/edu/calendarioacademico/add/'
        response = self.client.get(url)
        assert 'Adicionar Calendário Acadêmico' in response.content.decode()
        assert response.status_code == 200
        count = CalendarioAcademico.locals.all().count()
        init = {
            'descricao': 'Calendário 1',
            'tipo': tipo,
            'uo': self.servidor_b.setor.uo_id,
            'ano_letivo': ano.pk,
            'periodo_letivo': periodo,
            'data_inicio': f'01/01/{ano.ano}',
            'data_fim': f'31/07/{ano.ano}',
            'data_fechamento_periodo': f'31/07/{ano.ano}',
            'qtd_etapas': '1',
            'data_inicio_etapa_1': f'01/01/{ano.ano}',
            'data_fim_etapa_1': f'31/07/{ano.ano}',
        }
        init.update(params)
        response = self.client.post(url, init)
        self.assert_no_validation_errors(response)
        assert CalendarioAcademico.locals.all().count() == count + 1

        # acessando calendário academico
        calendario_academico = self.retornar(CalendarioAcademico)
        url = f'/edu/calendarioacademico/{calendario_academico.id}/'
        response = self.client.get(url)
        assert calendario_academico.descricao in response.content.decode()
        assert response.status_code == 200

        return self.retornar(CalendarioAcademico)

    def gerar_turmas_diarios(self, ano=None, periodo=None, periodo_matriz=None, optativas=False, qtd_turmas=1):
        if not ano:
            ano = self.ano_2013
        if not periodo:
            periodo = 1
        if not periodo_matriz:
            periodo_matriz = 1

        # acessando a página de geração de turmas
        url = '/edu/gerar_turmas/'
        response = self.client.get(url)
        assert 'Gerar Turmas' in response.content.decode()
        assert response.status_code == 200
        numero_turmas_antes = Turma.objects.all().count()
        matriz_curso = self.retornar(MatrizCurso)
        turno = self.retornar(Turno, chaves={'descricao': 'Matutino'})
        horario_campus = self.retornar(HorarioCampus)
        calendario_academico = self.retornar(CalendarioAcademico)

        # executando o primeiro passo do wizard
        data = {'ano_letivo': ano.pk, 'periodo_letivo': periodo, 'matriz_curso': matriz_curso.pk, 'tipo_componente': optativas and '0' or '1'}
        self.client.get(url, data)

        # executando o segundo passo do wizard
        data.update(
            {
                'qtd_periodo_1': periodo_matriz == 1 and qtd_turmas or 0,
                'turno_periodo_1': turno.pk,
                'vagas_periodo_1': '0',
                'qtd_periodo_2': periodo_matriz == 2 and qtd_turmas or 0,
                'turno_periodo_2': turno.pk,
                'vagas_periodo_2': '0',
                'qtd_periodo_3': periodo_matriz == 3 and qtd_turmas or 0,
                'turno_periodo_3': turno.pk,
                'vagas_periodo_3': '0',
            }
        )
        response = self.client.get(url, data)
        self.assert_no_validation_errors(response)

        # executando o terceiro passo do wizard
        qs_componentes = matriz_curso.matriz.componentecurricular_set.filter(optativo=optativas)
        if not optativas:
            qs_componentes = qs_componentes.filter(periodo_letivo=periodo_matriz)
        componentes = tuple(qs_componentes.values_list('id', flat=True))

        data.update({'horario_campus': horario_campus.pk, 'calendario_academico': calendario_academico.pk, 'componentes': componentes})
        response = self.client.get(url, data)
        self.assert_no_validation_errors(response)

        # executando o quarto e último passo do wizard
        data.update({'confirmacao': 'on'})
        response = self.client.get(url, data, follow=True)
        self.assert_no_validation_errors(response)

        if not optativas:
            numero_turmas_depois = Turma.objects.all().count()
            assert numero_turmas_depois == numero_turmas_antes + 1

        # acessando o admin de turmas
        url = '/admin/edu/turma/'
        response = self.client.get(url)
        assert matriz_curso.curso_campus.descricao_historico in response.content.decode()
        assert response.status_code == 200

        return Turma.objects.all()

    def replicar_matriz(self):
        # replicando a matriz
        matriz = self.retornar(Matriz)
        url = f'/edu/matriz/{matriz.pk}/replicar/'
        self.client.get(url, follow=True)
        data = {'descricao': f'{matriz.descricao} [REPLICADO]'}
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert f'{matriz.descricao} [REPLICADO]' in response.content.decode()
        assert response.status_code == 200
        matriz_replicada = self.retornar(Matriz)
        assert matriz.componentecurricular_set.count() == matriz_replicada.componentecurricular_set.count()
        # deletando a matriz replicada
        matriz_replicada.delete()

    def replicar_curso(self):
        # replicando curso
        curso = self.retornar(CursoCampus)
        url = f'/edu/cursocampus/{curso.pk}/replicar/'
        self.client.get(url, follow=True)
        data = {'diretoria': self.retornar(Diretoria).pk, 'codigo': '01404'}
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Curso replicado com sucesso.' in response.content.decode()
        assert response.status_code == 200
        curso_replicado = self.retornar(CursoCampus)
        assert curso.matrizcurso_set.count() == curso_replicado.matrizcurso_set.count()
        # deletando o curso replicado
        curso_replicado.delete()

    def vincular_matriz_curso(self, matriz=None, curso=None):
        # vinculando uma matriz ao curso
        if not matriz:
            matriz = self.retornar(Matriz)
        if not curso:
            curso = self.retornar(CursoCampus)
        url = f'/edu/cursocampus/{curso.pk}/'
        response = self.client.get(url)
        assert curso.descricao in response.content.decode()
        assert response.status_code == 200
        url = f'/edu/adicionar_matriz_curso/{curso.pk}/'
        response = self.client.get(url)
        assert 'Adicionar Matriz' in response.content.decode()
        assert response.status_code == 200
        count = curso.matrizcurso_set.count()
        data = {'curso_campus': curso.pk, 'matriz': matriz.pk}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert curso.matrizcurso_set.count() == count + 1
        matrizcurso = self.retornar(MatrizCurso)
        self.cadastrar_autorizacao_reconhecimento(matrizcurso)
        return matrizcurso

    def cadastrar_autorizacao_reconhecimento(self, matrizcurso):
        curso = matrizcurso.curso_campus

        url = f'/edu/cursocampus/{curso.pk}/adicionar_atoregulatorio/'
        response = self.client.get(url)
        documento = open('edu/fixtures/test_projeto_final.pdf', 'r+b')
        tipo = '10' if matrizcurso.curso_campus.modalidade_id in [Modalidade.MESTRADO, Modalidade.DOUTORADO] else '1'
        data = {
            'tipo': tipo,
            'tipo_cadastro': '2',
            'arquivo_documento': documento,
            'tipo_documento': 'Lei Federal',
            'data': '10/10/2010',
            'numero': '123',
            'orgao': 'PROEN',
            'numero_publicacao': '123',
            'data_publicacao': '10/10/2010',
            'veiculo_publicacao': 'DOU',
            'secao_publicacao': '1',
            'pagina_publicacao': '10',
        }
        response = self.client.post(url, data)
        documento.close()
        self.assert_no_validation_errors(response)

        response = self.client.get(url)
        documento = open('edu/fixtures/test_projeto_final.pdf', 'r+b')
        data = {
            'tipo': '3',
            'tipo_cadastro': '2',
            'arquivo_documento': documento,
            'tipo_documento': 'Lei Federal',
            'data': '10/10/2010',
            'numero': '123',
            'validade': '10/10/2100',
            'orgao': 'PROEN',
            'numero_publicacao': '123',
            'data_publicacao': '10/10/2010',
            'pagina_publicacao': '123',
            'secao_publicacao': '1',
            'veiculo_publicacao': 'DOU',
        }
        response = self.client.post(url, data)
        documento.close()
        self.assert_no_validation_errors(response)

    def transferir_posse_etapa(self):
        self.transferir_posse_etapa_registro_escolar()
        self.transferir_posse_etapa_professor()

    def transferir_posse_etapa_registro_escolar(self):
        diario = self.retornar(Diario)
        # tranferindo a posse do diário do professor para o registro escolar
        url = f'/edu/transferir_posse_diario/{diario.pk}/{1}/{Diario.POSSE_REGISTRO_ESCOLAR}/'
        self.client.get(url)
        url = f'/edu/diario/{diario.pk}/?tab=notas_faltas'
        response = self.client.get(url)
        assert 'Posse transferida com sucesso.' in response.content.decode()

    def transferir_posse_etapa_professor(self):
        diario = self.retornar(Diario)
        # tranferindo a posse do diário de volta para o professor
        url = f'/edu/transferir_posse_diario/{diario.pk}/{1}/{Diario.POSSE_PROFESSOR}/'
        self.client.get(url)
        url = f'/edu/diario/{diario.pk}/?tab=notas_faltas'
        response = self.client.get(url)
        assert 'Posse transferida com sucesso.' in response.content.decode()

    def cadastrar_professor_servidor(self):
        professor = Professor.objects.get_or_create(vinculo=self.servidor_c.get_user().get_vinculo())[0]
        Group.objects.get(name='Professor').user_set.add(professor.vinculo.user)
        return professor

    def cadastrar_professor_nao_servidor(self):
        # acessando a página de listagem de professores e procurando o botão de cadastro
        url = '/admin/edu/professor/?tab=tab_nao_servidor'
        response = self.client.get(url)
        assert 'Adicionar Professor Prestador de Serviço' in response.content.decode()
        # acessando a página de cadastro de professor externo
        url = '/edu/cadastrar_professor_nao_servidor/'
        response = self.client.get(url)
        assert 'Adicionar Professor Prestador de Serviço' in response.content.decode()
        # cadastrando um professor externo
        numero_pretadores_antes = PrestadorServico.objects.count()
        url = '/edu/cadastrar_professor_nao_servidor/'
        naturalidade = self.retornar(Municipio)
        curso_superior = CursoFormacaoSuperior.objects.get_or_create(area='Outros', codigo='123', descricao='curso superior', grau='Licenciatura')[0]
        instituicao_ensino_superior = InstituicaoEnsinoSuperior.objects.get_or_create(
            nome='IFRN', codigo='123', tipo='Pública', dependencia_administrativa=1
        )[0]
        data = {
            'nome': 'João Pereira da Silva',
            'cpf': '477.863.089-03',
            'passaporte': '',
            'sexo': 'M',
            'nacionalidade': Nacionalidade.BRASILEIRO_NATO,
            'email': 'joao@silva.com.br',
            'uo': self.servidor_b.setor.uo_id,
            'naturalidade': naturalidade.id,
            'ano_inicio_curso_superior': 2000,
            'ano_conclusao_curso_superior': 2004,
            'curso_superior': curso_superior.id,
            'instituicao_ensino_superior': instituicao_ensino_superior.id,
            'titulacao': 'Graduado',
            'tipo': 2,
        }
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        numero_pretadores_depois = PrestadorServico.objects.count()
        assert 'Professor cadastrado com sucesso.' in response.content.decode()
        assert numero_pretadores_depois == numero_pretadores_antes + 1

        # acessando o professor
        professor = self.retornar(Professor)
        url = f'/edu/professor/{professor.id}/'
        response = self.client.get(url)
        assert professor.vinculo.pessoa.nome in response.content.decode()
        assert response.status_code == 200

    def configurar_diario(self, diario=None):
        if not diario:
            diario = self.retornar(Diario)
        # acessando diarios
        url = '/admin/edu/diario/'
        response = self.client.get(url)
        assert str(diario.componente_curricular) in response.content.decode()
        assert response.status_code == 200

        # acessando a página de visualização de diário na aba "Dados gerais"
        url = f'/edu/diario/{diario.pk}/'
        response = self.client.get(url)
        assert f'Diário ({diario.pk}) - {diario.componente_curricular.componente.sigla}' in response.content.decode()
        assert response.status_code == 200
        # localizando o link de acesso à página de definição de sala de aula
        url = f'/edu/definir_local_aula_diario/{diario.pk}/'
        assert url in response.content.decode()
        # acessando a página de definição de sala de aula
        response = self.client.get(url)
        assert 'Definir Local de Aula' in response.content.decode()
        assert response.status_code == 200
        assert diario.local_aula is None
        data = {'sala': self.retornar(Sala).pk}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        diario = self.recarregar(diario)
        assert diario.local_aula is not None
        # voltando para a página de detalhamento de diário na aba padrão
        url = f'/edu/diario/{diario.pk}/'
        response = self.client.get(url)
        # localizando o link de acesso à página de e definição de horário
        url = f'/edu/definir_horario_aula_diario/{diario.pk}/'
        assert url in response.content.decode()
        # acessando a página de definição de horário
        response = self.client.get(url)
        assert 'Definir Horário de Aula' in response.content.decode()
        assert response.status_code == 200
        assert diario.horarioauladiario_set.count() == 0
        horario_campus = diario.horario_campus
        horarios_aulas = horario_campus.horarioaula_set.all().order_by('-id')

        data = {'horario': [f'{horarios_aulas[0].pk};{1}', f'{horarios_aulas[1].pk};{1}', f'{horarios_aulas[2].pk};{1}']}
        response = self.client.post(f'/edu/definir_horario_aula_diario/{diario.pk}/', data, follow=True)
        assert 'Horário definido com sucesso' in response.content.decode()
        assert response.status_code == 200

        assert diario.get_horario_aulas() == '2M123'
        # voltando para a página de detalhamento de diário na aba padrão
        url = f'/edu/diario/{diario.pk}/'
        response = self.client.get(url)
        # localizando o link de acesso à página de definição de professor
        url = f'/edu/adicionar_professor_diario/{diario.pk}/'
        assert url in response.content.decode()
        # acessando a página de inclusão de professor
        tipo_professor_diario = self.retornar(TipoProfessorDiario)
        professor = self.retornar(Professor)
        response = self.client.get(url)
        assert 'Adicionar Professor' in response.content.decode()
        assert response.status_code == 200
        assert diario.professordiario_set.count() == 0
        # definindo professor no diário
        data = {
            'diario': diario.pk,
            'vinculo': professor.vinculo.pk,
            'tipo': tipo_professor_diario.pk,
            'data_inicio_etapa_1': diario.calendario_academico.data_inicio_etapa_1.strftime('%d/%m/%Y'),
            'data_fim_etapa_1': diario.calendario_academico.data_fim_etapa_1.strftime('%d/%m/%Y'),
            'data_inicio_etapa_final': diario.calendario_academico.data_fim_etapa_1.strftime('%d/%m/%Y'),
            'data_fim_etapa_final': diario.calendario_academico.data_fechamento_periodo.strftime('%d/%m/%Y'),
            'percentual_ch': 100,
            'ativo': True,
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert diario.professordiario_set.count() == 1
        return diario

    def visualizar_locais_horario_aulas_professor(self):
        # acessando a pagina de locais e horários de aula
        url = '/edu/locais_aula_professor/'
        response = self.client.get(url)
        assert 'Locais e Horários de Aula' in response.content.decode()
        assert response.status_code == 200

    def efetuar_matricula_institucional(
        self,
        cpf='047.704.024-14',
        nome='Carlos Breno Pereira Silva',
        data_nascimento='27/08/1984',
        responsavel='Maria Eliete da Silva Pereira',
        nome_mae='Maria Eliete da Silva Pereira',
        logradouro='Av. João XXIII',
        numero='708',
        bairro='Santos Reis',
        cep='59141-030',
        curso=None,
    ):
        numero_alunos_antes = Aluno.objects.all().count()
        numero_vinculos_antes = Vinculo.objects.all().count()
        # acessando a página de realização de matrícula
        qs = CandidatoVaga.objects.all()
        if qs.exists():
            url = f'/edu/efetuar_matricula/{qs[0].pk}/'
            linha_pesquisa = self.retornar(LinhaPesquisa)
        else:
            url = '/edu/efetuar_matricula/'
            linha_pesquisa = None
        response = self.client.get(url)
        assert 'Matrícula Institucional' in response.content.decode()
        assert response.status_code == 200
        cidade = Cidade.objects.get(codigo=2401403)
        cartorio = self.retornar(Cartorio)
        # executando o primeiro passo do wizard
        data = {'nacionalidade': Aluno.TIPO_NACIONALIDADE_CHOICES[0][0], 'cpf': cpf}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        # executando o segundo passo do wizard
        data.update(
            nome=nome,
            sexo='M',
            data_nascimento=data_nascimento,
            estado_civil=Aluno.ESTADO_CIVIL_CHOICES[0][0],
            responsavel=responsavel,
            nome_mae=nome_mae,
            parentesco_responsavel=Aluno.PARENTESCO_CHOICES[0][0],
            cpf_responsavel='263.458.470-97',
            logradouro=logradouro,
            numero=numero,
            bairro=bairro,
            cep=cep,
            cidade=cidade.pk,
            tipo_zona_residencial=Aluno.TIPO_ZONA_RESIDENCIAL_CHOICES[0][0],
        )
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        # executando o terceiro passo do wizard
        data.update(
            aluno_pne='Não',
            email_pessoal='carlos.silva@agmail.com',
            tipo_sanguineo=Aluno.TIPO_SANGUINEO_CHOICES[0][0],
            naturalidade=cidade.pk,
            raca=self.raca.pk,
            nivel_ensino_anterior=NivelEnsino.objects.get(pk=NivelEnsino.MEDIO).pk,
            ano_conclusao_estudo_anterior=self.ano_2013.pk,
            tipo_instituicao_origem=Aluno.TIPO_INSTITUICAO_ORIGEM_CHOICES[0][0],
        )
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        # executando o quarto passo do wizard
        data.update(tipo_certidao=Aluno.TIPO_CERTIDAO_CHOICES[0][0], cartorio=cartorio.pk)
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        # executando o quinto passo do wizard
        turno = self.retornar(Turno, chaves={'descricao': 'Matutino'})
        forma_ingresso = self.retornar(FormaIngresso)
        if curso:
            matriz_curso = self.retornar(MatrizCurso, chaves={'curso_campus_id': curso.id})
        else:
            matriz_curso = self.retornar(MatrizCurso)
        convenio = self.retornar(Convenio)

        data.update(
            foto='',
            ano_letivo=self.ano_2013.pk,
            periodo_letivo=Aluno.PERIODO_LETIVO_CHOICES[0][0],
            turno=turno.pk,
            forma_ingresso=forma_ingresso.pk,
            cota_sistec=Aluno.COTA_SISTEC_CHOICES[0][0],
            cota_mec=Aluno.COTA_MEC_CHOICES[0][0],
            data_conclusao_intercambio='',
            matriz_curso=matriz_curso.pk,
            linha_pesquisa=linha_pesquisa and linha_pesquisa.pk or '',
            numero_pasta=3880,
            polo='',
            possui_convenio=True,
            possui_orientador=False,
            convenio=convenio.pk,
        )
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)

        numero_alunos_depois = Aluno.objects.all().count()
        numero_vinculos_depois = Vinculo.objects.all().count()
        assert numero_alunos_depois == numero_alunos_antes + 1
        assert numero_vinculos_depois == numero_vinculos_antes + 1
        aluno = self.retornar(Aluno)

        # acessando o admin de alunos
        url = '/admin/edu/aluno/'
        response = self.client.get(url)
        assert aluno.pessoa_fisica.nome in response.content.decode()
        assert response.status_code == 200

        # alterando a senha do usuário do aluno para que ele possa acessar o suap
        user = User.objects.get(username=aluno.matricula)
        user.set_password('123')
        user.save()
        return aluno

    def cancelar_matricula(self):
        aluno = self.retornar(Aluno)
        numero_aluno_antes = Aluno.objects.count()
        url = f'/comum/excluir/edu/aluno/{aluno.pk}/'
        self.client.get(url, follow=True)
        data = {'senha': '123'}
        response = self.client.post(url, data, follow=True)
        numero_aluno_depois = Aluno.objects.count()
        self.assert_no_validation_errors(response)
        assert 'Registro(s) excluído(s) com sucesso.' in response.content.decode()
        assert numero_aluno_depois == numero_aluno_antes - 1

    def emitir_relatorio_alunos(self):
        aluno = self.retornar(Aluno)
        # selecionando um aluno do formulário de listagem de alunos
        parameters = f'aluno={aluno.pk}&periodo_letivo=0&situacao_diario=0&periodo_ingresso=0&forma_ingresso=&formatacao=simples&quantidade_itens=25&ordenacao=Nome&agrupamento=Campus'
        url = '/edu/relatorio/?' + parameters
        response = self.client.get(url, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Carlos Breno Pereira Silva' in response.content.decode()
        # imprimindo os alunos selecionados
        response = self.client.get(url + '&imprimir=1&html=1', follow=True)
        self.assert_no_validation_errors(response)
        assert 'Carlos Breno Pereira Silva' in response.content.decode()
        # gerando o xls dos alunos selecionados
        response = self.client.get(url + '&xls=1', follow=True)
        self.assert_no_validation_errors(response)
        # salvando o relatorio
        before = HistoricoRelatorio.objects.count()
        data = {'descricao': 'Relatório #1'}
        response = self.client.post('/edu/salvar_relatorio/1/{}/'.format(parameters.encode('utf-8').hex()), data, follow=True)
        self.assert_no_validation_errors(response)
        after = HistoricoRelatorio.objects.count()
        assert before + 1 == after
        assert 'Consulta salva com sucesso.' in response.content.decode()
        historico_relatorio = self.retornar(HistoricoRelatorio)
        # visualizando relatorio salvo
        response = self.client.get(historico_relatorio.get_url())
        self.assert_no_validation_errors(response)
        assert 'Carlos Breno Pereira Silva' in response.content.decode()
        # apagando o relatorio salvo
        before = HistoricoRelatorio.objects.count()
        url = f'/comum/excluir/edu/historicorelatorio/{historico_relatorio.pk}/'
        response = self.client.get(url)
        data = {'senha': '123'}
        response = self.client.post(url, data, follow=True)
        assert 'Registro(s) excluído(s) com sucesso.' in response.content.decode()
        assert response.status_code == 200
        after = HistoricoRelatorio.objects.count()
        assert before == after + 1

    def emitir_relatorio_diarios(self):
        ano_letivo = self.ano_2013
        # selecionando um ano ao formulário de listagem de diário
        parameters = f'ano_letivo_inicio={ano_letivo.pk}&ano_letivo_fim={ano_letivo.pk}&periodo_letivo_inicio=1&periodo_letivo_fim=2&etapa=1&ordenacao=Nome&agrupamento=Campus'
        url = '/edu/relatorio_diario/?' + parameters
        response = self.client.get(url, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Ano Letivo' in response.content.decode()
        # imprimindo os diários selecionados
        response = self.client.get(url + '&imprimir=1&html=1', follow=True)
        self.assert_no_validation_errors(response)
        # gerando o xls dos diários selecionados
        response = self.client.get(url + '&xls=1', follow=True)
        self.assert_no_validation_errors(response)
        # salvando o relatorio
        before = HistoricoRelatorio.objects.count()
        data = {'descricao': 'Relatório #1'}
        response = self.client.post('/edu/salvar_relatorio/2/{}/'.format(parameters.encode('utf-8').hex()), data, follow=True)
        self.assert_no_validation_errors(response)
        after = HistoricoRelatorio.objects.count()
        assert before + 1 == after
        assert 'Consulta salva com sucesso.' in response.content.decode()
        historico_relatorio = self.retornar(HistoricoRelatorio)
        # visualizando relatorio salvo
        response = self.client.get(historico_relatorio.get_url())
        self.assert_no_validation_errors(response)
        assert 'FIC.0001 - Administração da propriedade rural' in response.content.decode()
        # apagando o relatorio salvo
        before = HistoricoRelatorio.objects.count()
        url = f'/comum/excluir/edu/historicorelatorio/{historico_relatorio.pk}/'
        data = {'senha': '123'}
        response = self.client.post(url, data, follow=True)
        assert 'Registro(s) excluído(s) com sucesso.' in response.content.decode()
        assert response.status_code == 200
        after = HistoricoRelatorio.objects.count()
        assert before == after + 1

    def emitir_relatorio_professores(self):
        # O nome esperado sai do próprio servidor da fixture; antes era o literal
        # 'Servidor 3', que só existia porque o `suap_data` batizava assim o `servidor_c`.
        nome_professor = self.servidor_c.pessoa_fisica.nome
        # selecionando um professor do formulário de listagem de professores
        parameters = 'categoria=Todos&ano_letivo=&periodo_letivo=&tipo_professor=&uo=&setor_lotacao=&setor_suap=&disciplina_ingresso=&jornada_trabalho=&regime=Todos&nce=&ordenacao=Nome&exibicao=vinculo.setor.uo&exibicao=disciplina'
        url = '/edu/relatorio_professor/?' + parameters
        response = self.client.get(url, follow=True)
        self.assert_no_validation_errors(response)
        assert nome_professor in response.content.decode()
        # imprimindo os professores selecionados
        response = self.client.get(url + '&imprimir=1&html=1', follow=True)
        self.assert_no_validation_errors(response)
        assert nome_professor in response.content.decode()
        # gerando o xls dos professores selecionados
        response = self.client.get(url + '&xls=1', follow=True)
        self.assert_no_validation_errors(response)
        # salvando o relatorio
        before = HistoricoRelatorio.objects.count()
        data = {'descricao': 'Relatório #1'}
        response = self.client.post('/edu/salvar_relatorio/3/{}/'.format(parameters.encode('utf-8').hex()), data, follow=True)
        self.assert_no_validation_errors(response)
        after = HistoricoRelatorio.objects.count()
        assert before + 1 == after
        assert 'Consulta salva com sucesso.' in response.content.decode()
        historico_relatorio = self.retornar(HistoricoRelatorio)
        # visualizando relatorio salvo
        response = self.client.get(historico_relatorio.get_url())
        self.assert_no_validation_errors(response)
        assert nome_professor in response.content.decode()
        # apagando o relatorio salvo
        before = HistoricoRelatorio.objects.count()
        url = f'/comum/excluir/edu/historicorelatorio/{historico_relatorio.pk}/'
        data = {'senha': '123'}
        response = self.client.post(url, data, follow=True)
        assert 'Registro(s) excluído(s) com sucesso.' in response.content.decode()
        assert response.status_code == 200
        after = HistoricoRelatorio.objects.count()
        assert before == after + 1

    def emitir_relatorio_faltas(self, codigo_turma, contendo=None):
        # selecionando uma turma
        turma = Turma.objects.get(codigo=codigo_turma)
        uo_id = turma.curso_campus.diretoria.setor.uo_id
        parameters = (
            f'uo={uo_id}&turma={codigo_turma}&turma={turma.pk}&diario=&diario=&aluno=&aluno=&situacao_periodo=&intervalo_inicio=&intervalo_fim='
        )
        url = '/edu/relatorio_faltas/?' + parameters
        response = self.client.get(url)
        self.assert_no_validation_errors(response)

        if contendo:
            assert contendo in response.content.decode()

    def relatorio_periodos_abertos(self, ano, contem, contendo):
        url = f'/edu/relatorio_periodos_abertos/?ano_selecionado={ano}'
        response = self.client.get(url)
        assert 'Relatório de Alunos com Períodos Não-Fechados' in response.content.decode()

        if contem:
            assert contendo in response.content.decode()
        else:
            assert contendo not in response.content.decode()

    def emitir_relatorio_ead(self):
        url = '/edu/relatorio_ead/'
        response = self.client.get(url)
        assert 'Total de Alunos por Polo e Nível de Ensino' in response.content.decode()

    def relatorio_estatisticas(self):
        # acessando estatísticas
        url = '/edu/estatistica/'
        response = self.client.get(url)
        assert 'Estatísticas' in response.content.decode()

        # acessando as estatísticas dos alunos matriculados a partir do ano de 2013
        url = f'/edu/estatistica/?tab=listagem&situacao_matricula_periodo=SITUACAO_MATRICULADO&periodicidade=por_ano_letivo&apartir_do_ano={self.ano_2013.pk}'
        response = self.client.get(url)
        assert self.retornar(Aluno).pessoa_fisica.nome in response.content.decode()

    def imprimir_comprovante_matricula(self):
        aluno = self.retornar(Aluno)
        # acessando o comprovante de matricula
        url = f'/edu/comprovante_matricula_pdf/{aluno.id}/?html=1'
        response = self.client.get(url, follow=True)
        assert 'COMPROVANTE DE MATRÍCULA' in response.content.decode()

    def visualizar_dados_pessoais_e_academicos(
        self, ja_selecionou_email=False, com_boletim=True, com_historico=True, com_atividades_complementares=False, com_procedimento_academico=False
    ):
        aluno = self.retornar(Aluno)
        response = self.client.get('/comum/index/minhas_pendencias/')
        assert 'Responda ao questionário de Caracterização Socioeconômica.' in response.content.decode()
        # self.assertContains(response, 'Calendário Acadêmico')
        # acessando os dados pessoais do aluno
        url = aluno.get_absolute_url()
        response = self.client.get(url)
        assert 'Dados gerais' in response.content.decode()
        # acessando os dados acadêmicos do aluno
        response = self.client.get('{}{}'.format(url, '?tab=dados_pessoais'))
        assert 'Dados gerais' in response.content.decode()
        # acessando o boletim
        if com_boletim:
            response = self.client.get('{}{}'.format(url, '?tab=boletim'))
            assert 'Gráfico de Desempenho por Etapa' in response.content.decode()
        # acessando o histórico
        if com_historico:
            response = self.client.get('{}{}'.format(url, '?tab=historico'))
            assert 'Componentes Curriculares' in response.content.decode()
        # acessando os projetos finais
        response = self.client.get('{}{}'.format(url, '?tab=projeto'))
        if aluno.matriz:
            if aluno.matriz.exige_tcc:
                if not aluno.get_projetos_finais().exists():
                    assert 'Não há trabalho de conclusão de curso para esse aluno' in response.content.decode()
                else:
                    projeto_final = self.retornar(ProjetoFinal)
                    assert projeto_final.titulo in response.content.decode()
            # acessando os requisitos de conclusão
            response = self.client.get('{}{}'.format(url, '?tab=requisitos'))
            assert 'Disciplinas obrigatórias' in response.content.decode()
        if not com_atividades_complementares and aluno.matriz.ch_atividades_complementares:
            # acessando as atividades complementares
            response = self.client.get('{}{}'.format(url, '?tab=acc'))
            assert 'Nenhuma atividade complementar cadastrada até o momento' in response.content.decode()

    def visualizar_botao_email_academico(self, ja_selecionou_email=False):
        response = self.client.get('/comum/index/meus_avisos/')
        if is_ldap_enabled():
            assert 'Escolha seu email Acadêmico' in response.content.decode()

    def atualizar_endereco(self):
        aluno = self.retornar(Aluno)
        # atualizando endereço do aluno
        url = f'/edu/atualizar_meus_dados_pessoais/{aluno.matricula}/'
        response = self.client.get(url)
        cidade = Cidade.objects.get(codigo=2401403)
        assert 'Atualização de Dados Pessoais' in response.content.decode()

        data = {
            'email_secundario': 'a@a.com',
            'logradouro': 'RUA LAGOA DOS PATOS',
            'numero': '100',
            'complemento': 'APTO 101',
            'bairro': 'LAGOA NOVA',
            'cep': '59300-000',
            'cidade': cidade.pk,
            'utiliza_transporte_escolar_publico': 'Não',
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        aluno = self.recarregar(aluno)
        assert aluno.logradouro == 'RUA LAGOA DOS PATOS'

    def definir_email_institucional(self):
        if not is_ldap_enabled():
            return
        self.retornar(Aluno)
        response = self.client.get('/comum/index/meus_avisos/')
        # escolhendo o email institucional
        assert 'Escolha seu email Acadêmico' in response.content.decode()
        url = '/ldap_backend/escolher_email/academico/'
        response = self.client.get('/ldap_backend/escolher_email/academico/')
        assert 'Escolha seu E-mail Acadêmico' in response.content.decode()
        assert response.status_code == 200
        data = {'email': 'carlos.silva@academico.ifrn.edu.br'}
        response = self.client.post(url, data, follow=True)
        assert (
            'O email &quot;{}&quot; foi definido com sucesso e estará disponível para uso em 3 horas.'.format(data['email'])
            in response.content.decode()
        )
        assert response.status_code == 200

    def visualizar_locais_horario_aulas_aluno(self):
        # acessando a pagina de locais e horários de aula
        aluno = self.retornar(Aluno)
        url = f'{aluno.get_absolute_url()}?tab=locais_aula_aluno'
        response = self.client.get(url)
        assert 'Locais e horários de aula/atividades' in response.content.decode()
        assert response.status_code == 200

    def lancar_aulas_faltas_professor(self, ano=None):
        if not ano:
            ano = self.ano_2013

        matricula_diario = self.retornar(MatriculaDiario)
        professor_diario = self.retornar(ProfessorDiario)
        # verificando a existência do link de acesso à página de visualização de etapa
        url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
        response = self.client.get(url)
        assert 'Etapa 1' in response.content.decode()
        assert response.status_code == 200
        # verificando a existência do link de acesso à página de cadastro de aula
        url = f'/edu/adicionar_aula_diario/{matricula_diario.diario.pk}/1/'
        # self.assertContains(response, url)
        # acessando a página de cadastro de aula
        self.client.get(url)
        # registrando uma aula para atingir 80% da carga horária necessária (8 de 10)

        assert matricula_diario.diario.get_horas_aulas_etapa_1() == 0
        data = {
            'professor_diario': professor_diario.pk,
            'etapa': '1',
            'quantidade': '8',
            'tipo': 1,
            'data': f'01/{matricula_diario.data_matricula.month}/{ano.ano}',
            'conteudo': 'Aula 01.',
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        matricula_diario = self.retornar(MatriculaDiario)
        assert not matricula_diario.is_carga_horaria_diario_fechada()
        assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Cursando'
        assert matricula_diario.get_situacao_nota()['rotulo'] == 'Cursando'
        if matricula_diario.diario.pode_ser_entregue_sem_nota():
            assert matricula_diario.get_situacao_diario()['rotulo'] == 'Pendente'
            assert matricula_diario.pode_fechar_periodo_letivo()
        else:
            assert matricula_diario.get_situacao_diario()['rotulo'] == 'Cursando'
            assert not matricula_diario.pode_fechar_periodo_letivo()
        assert matricula_diario.get_situacao_registrada_diario()['rotulo'] == 'Cursando'
        assert matricula_diario.is_cursando()
        assert not matricula_diario.realizou_todas_avaliacoes_regulares()
        assert not matricula_diario.realizou_todas_avaliacoes()
        assert not matricula_diario.is_aprovado_sem_prova_final()
        assert not matricula_diario.realizou_avaliacao_final()
        assert not matricula_diario.is_em_prova_final()
        assert not matricula_diario.is_aprovado_em_prova_final()
        assert not matricula_diario.is_aprovado_por_nota()
        assert matricula_diario.is_aprovado_por_frequencia()
        assert not matricula_diario.is_aprovado()
        assert matricula_diario.get_media_disciplina() is None
        assert matricula_diario.get_media_final_disciplina() is None
        assert matricula_diario.get_numero_faltas_primeira_etapa() == 0
        assert matricula_diario.get_percentual_carga_horaria_frequentada() == 100
        # lançando mais uma aula para atingir de 100% necessário para fechar o diário
        data = {
            'professor_diario': professor_diario.pk,
            'etapa': '1',
            'quantidade': '2',
            'tipo': 1,
            'data': f'02/{matricula_diario.data_matricula.month}/{ano.ano}',
            'conteudo': 'Aula 02.',
        }
        self.client.post(url, data)
        # verificando algumas condições acerca da carga horária
        temp = Diario.locals.get(pk=matricula_diario.diario.pk)
        assert temp.get_horas_aulas_etapa_1() == 10
        assert temp.get_percentual_carga_horaria_cumprida() == 100
        matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario.pk)
        assert matricula_diario.is_carga_horaria_diario_fechada()
        assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Aprovado'
        # voltando para a página de listagem de diários
        url = '/edu/meus_diarios/'
        self.client.get(url)
        # acessando a página de visualização de diário na aba "Chamada"
        url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/?tab=notas'
        response = self.client.get(url)
        # lançando uma falta
        aula_ = matricula_diario.diario.professordiario_set.all()[0].aula_set.all()[0]
        url_ = f'/edu/registrar_chamada_ajax/{matricula_diario.pk}/{aula_.pk}/1/'
        assert 'O salvamento das notas é realizado' in response.content.decode()
        assert response.status_code == 200
        response_ = self.client.get(url_)
        assert '1' in response_.content.decode()
        assert response_.status_code == 200

    def abonar_falta(self):
        matricula_diario = self.retornar(MatriculaDiario)
        motivo = self.retornar(MotivoAusenciaEscolar)
        aluno = matricula_diario.matricula_periodo.aluno

        # acessando a página para cadastrar abono de faltas
        url = '/admin/edu/abonofaltas/add/'
        response = self.client.get(url)
        # verificando se estou na página de cadastro de abono de faltas
        assert 'Adicionar Justificativa de Falta' in response.content.decode()
        assert response.status_code == 200

        # guardando quantidade de faltas e abonos ANTES do cadastro de um abono
        qtd_faltas_diario_antes = matricula_diario.falta_set.all().count()
        qtd_faltas_periodo_antes = matricula_diario.matricula_periodo.get_total_faltas()
        qtd_faltas_abonadas_antes = matricula_diario.falta_set.filter(abono_faltas__isnull=False).all().count()
        anexo = open('edu/fixtures/test_projeto_final.pdf', 'r+b')
        data = {
            'aluno': aluno.pk,
            'responsavel_abono': self.servidor_a.get_user().pk,
            'data_inicio': '01/01/2013',
            'quantidade_dias': 1,
            'justificativa': '.',
            'motivo_ausencia_escolar': motivo.id,
            'anexo': anexo,
            'diario': matricula_diario.diario.pk,
        }
        response = self.client.post(url, data, follow=True)
        anexo.close()
        self.assert_no_validation_errors(response)
        abonofalta = self.retornar(AbonoFaltas)
        url = f'/edu/avaliar_abono_faltas/{abonofalta.pk}/'
        response = self.client.post(url, {'deferido': True}, follow=True)
        self.assert_no_validation_errors(response)
        # guardando quantidade de faltas e abonos DEPOIS do cadastro de um abono
        qtd_faltas_diario_depois = matricula_diario.falta_set.all().count()
        qtd_faltas_abonadas_depois = matricula_diario.falta_set.filter(abono_faltas__isnull=False).all().count()
        qtd_faltas_periodo_depois = matricula_diario.matricula_periodo.get_total_faltas()

        # regras para verificar situação das faltas e abonos depois de um cadastro de abono
        assert qtd_faltas_diario_antes == qtd_faltas_diario_depois
        assert qtd_faltas_periodo_depois == qtd_faltas_periodo_antes - 1
        assert qtd_faltas_abonadas_depois == qtd_faltas_abonadas_antes + 1

        # acessando a tela de visualização do abono de faltas
        ultimo_abono_faltas_cadastrado = self.retornar(AbonoFaltas)
        url = f'/edu/abonofaltas/{ultimo_abono_faltas_cadastrado.pk}/'
        response = self.client.get(url)
        # verificando se estou na página de visualização de abono de faltas
        assert (
            f'ustificativa de falta: {ultimo_abono_faltas_cadastrado.aluno.pessoa_fisica.nome_usual} ({ultimo_abono_faltas_cadastrado.aluno.matricula})'
            in response.content.decode()
        )
        assert response.status_code == 200

        # guardando quantidade de faltas e abonos ANTES da exclusão de um abono
        qtd_faltas_diario_antes_exclusao = qtd_faltas_diario_depois
        qtd_faltas_abonadas_antes_exclusao = qtd_faltas_abonadas_depois
        qtd_faltas_periodo_antes_exclusao = qtd_faltas_periodo_depois

        # excluindo um abono faltas
        url = f'/comum/excluir/edu/abonofaltas/{ultimo_abono_faltas_cadastrado.pk}/'
        data = {'senha': '123'}
        response = self.client.post(url, data, follow=True)
        assert 'Registro(s) excluído(s) com sucesso.' in response.content.decode()
        assert response.status_code == 200

        # guardando quantidade de faltas e abonos DEPOIS DA EXCLUSÃO de um abono
        qtd_faltas_diario_depois_exclusao = matricula_diario.falta_set.all().count()
        qtd_faltas_abonadas_depois_exclusao = matricula_diario.falta_set.filter(abono_faltas__isnull=False).all().count()
        qtd_faltas_periodo_depois_exclusao = matricula_diario.matricula_periodo.get_total_faltas()

        # regras para verificar situação das faltas e abonos DEPOIS DA EXCLUSÃO de abono
        assert qtd_faltas_diario_antes_exclusao == qtd_faltas_diario_depois_exclusao
        assert qtd_faltas_periodo_depois_exclusao == qtd_faltas_periodo_antes_exclusao + 1
        assert qtd_faltas_abonadas_depois_exclusao == qtd_faltas_abonadas_antes_exclusao - 1

    def acompanhar_aulas(self):
        matricula_diario = self.retornar(MatriculaDiario)
        # acessando salas virtuais
        url = '/edu/disciplinas/'
        response = self.client.get(url)
        assert 'disciplinas' in response.content.decode()
        # acessando uma sala virtual
        url = f'/edu/disciplina/{matricula_diario.diario.id}/'
        response = self.client.get(url, follow=True)
        assert 'Dados do diário' in response.content.decode()
        assert 'Professores' in response.content.decode()
        assert 'Local de Aula' in response.content.decode()
        assert 'Horário de Aula' in response.content.decode()
        assert 'Calendário' in response.content.decode()
        # acessando os participantes da sala virtual
        response = self.client.get('{}{}'.format(url, '?tab=participantes'))
        assert 'Carlos Breno Pereira Silva' in response.content.decode()

    def visualizar_materiais_didaticos(self):
        matricula_diario = self.retornar(MatriculaDiario)
        # acessando salas virtuais
        url = '/edu/disciplinas/'
        response = self.client.get(url)
        assert 'disciplinas' in response.content.decode()
        # acessando uma sala virtual
        url = f'/edu/disciplina/{matricula_diario.diario.id}/'
        # acessando os materiais de aula
        response = self.client.get('{}{}'.format(url, '?tab=materiais'))
        assert 'Material 01' in response.content.decode()

    def cadastrar_material_didatico(self):
        # cadastrando um material
        url = '/admin/edu/materialaula/'
        response = self.client.get(url)
        assert 'Nenhum Material de Aula encontrado.' in response.content.decode()
        assert response.status_code == 200
        url = '/admin/edu/materialaula/add/'
        count = MaterialAula.objects.all().count()
        data = {'tipo': 1, 'descricao': 'Material 01', 'url': 'http://google.com.br'}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert MaterialAula.objects.all().count() == count + 1
        url = '/admin/edu/materialaula/'
        response = self.client.get(url)
        assert 'Material 01' in response.content.decode()
        assert response.status_code == 200

    def vincular_material_didatico(self):
        diario = self.retornar(Diario)
        # verificando a existência do link de acesso à página de diários na página principal
        url = '/edu/meus_diarios/'
        quadro = 'UFJPRkVTU09SRVM='  # 'PROFESSORES' em base64
        response = self.client.get(f'/comum/index/meu_quadro/{quadro}/')
        assert url in response.content.decode()
        assert response.status_code == 200
        # acessando a página de diários
        self.client.get(f'{url}2013/')
        # acessando pagina dos materiais de aulas do diario
        professor_diario = diario.professordiario_set.all()[0]
        url_ = f'/edu/materiais_diario/{professor_diario.pk}/1/'
        response_ = self.client.get(url_)
        assert 'Materiais de Aula do Diário' in response_.content.decode()
        assert response_.status_code == 200
        # vincular material de aula a diário
        material_aula = MaterialAula.objects.filter(professor=professor_diario.professor)[0]
        count_ = MaterialDiario.objects.filter(professor_diario=professor_diario).count()
        data_ = {'materiais_aula': [material_aula.pk]}
        response_ = self.client.post(url_, data_)
        self.assert_no_validation_errors(response_)
        assert MaterialDiario.objects.filter(professor_diario=professor_diario).count() == count_ + 1
        response_ = self.client.get(url_)
        assert 'Material vinculado com sucesso' in response_.content.decode()
        assert response_.status_code == 200

    def lancar_notas_professor(self, nota=80, etapa=1, descricao_componente=None):
        matricula_diario = None
        if descricao_componente:
            matricula_diario = MatriculaDiario.objects.get(diario__componente_curricular__componente__descricao=descricao_componente)
        else:
            matricula_diario = self.retornar(MatriculaDiario)

            # acessando a página de visualização de diário na aba "Avaliações"
        url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/?tab=notas'
        self.client.get(url)

        if etapa == 1:
            nota_avaliacao = matricula_diario.get_notas_etapa_1()[0]
            if not nota:
                # lançando uma nota vazia
                url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
                self.client.get(url)
                data = {'lancamento_nota': 1, f'{1};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}': ''}
                assert matricula_diario.nota_1 is not None
                response = self.client.post(url, data)
                matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario.pk)
                self.assert_no_validation_errors(response)
                assert matricula_diario.nota_1 is None
                assert matricula_diario.is_carga_horaria_diario_fechada()
                assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_nota()['rotulo'] == 'Cursando'
                assert matricula_diario.get_situacao_diario()['rotulo'] == 'Cursando'
                assert matricula_diario.get_situacao_registrada_diario()['rotulo'] == 'Cursando'
                assert not matricula_diario.pode_fechar_periodo_letivo()
                assert matricula_diario.is_cursando()
                assert not matricula_diario.realizou_todas_avaliacoes_regulares()
                assert not matricula_diario.realizou_todas_avaliacoes()
                assert not matricula_diario.is_aprovado_sem_prova_final()
                assert not matricula_diario.realizou_avaliacao_final()
                assert not matricula_diario.is_em_prova_final()
                assert not matricula_diario.is_aprovado_em_prova_final()
                assert not matricula_diario.is_aprovado_por_nota()
                assert matricula_diario.is_aprovado_por_frequencia()
                assert not matricula_diario.is_aprovado()
                assert matricula_diario.get_media_disciplina() is None
                assert matricula_diario.get_media_final_disciplina() is None

            elif nota < matricula_diario.diario.turma.matriz.estrutura.media_evitar_reprovacao_direta:
                # lançando uma nota para aprovar o aluno reprovar direto
                data = {'lancamento_nota': 1, f'{1};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}': nota}  # 20
                assert matricula_diario.nota_1 is None
                response = self.client.post(url, data)
                matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario.pk)
                self.assert_no_validation_errors(response)
                assert matricula_diario.is_carga_horaria_diario_fechada()
                assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_nota()['rotulo'] == 'Reprovado'
                assert matricula_diario.get_situacao_diario()['rotulo'] == 'Reprovado'
                assert matricula_diario.get_situacao_registrada_diario()['rotulo'] == 'Cursando'
                assert matricula_diario.pode_fechar_periodo_letivo()
                assert matricula_diario.is_cursando()
                assert matricula_diario.realizou_todas_avaliacoes_regulares()
                assert matricula_diario.realizou_todas_avaliacoes()
                assert not matricula_diario.is_aprovado_sem_prova_final()
                assert not matricula_diario.realizou_avaliacao_final()
                assert not matricula_diario.is_em_prova_final()
                assert not matricula_diario.is_aprovado_em_prova_final()
                assert not matricula_diario.is_aprovado_por_nota()
                assert matricula_diario.is_aprovado_por_frequencia()
                assert not matricula_diario.is_aprovado()
                assert matricula_diario.get_media_disciplina() == nota
                assert matricula_diario.get_media_final_disciplina() == nota

            elif nota >= matricula_diario.diario.turma.matriz.estrutura.media_aprovacao_sem_prova_final:
                # lançando uma nota para aprovar o aluno direto
                url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
                self.client.get(url)
                data = {'lancamento_nota': 1, f'{1};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}': nota}
                response = self.client.post(url, data)
                matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario.pk)
                assert matricula_diario.is_carga_horaria_diario_fechada()
                assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_nota()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_diario()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_registrada_diario()['rotulo'] == 'Cursando'
                assert matricula_diario.pode_fechar_periodo_letivo()
                assert matricula_diario.is_cursando()
                assert matricula_diario.realizou_todas_avaliacoes_regulares()
                assert matricula_diario.realizou_todas_avaliacoes()
                assert matricula_diario.is_aprovado_sem_prova_final()
                assert not matricula_diario.realizou_avaliacao_final()
                assert not matricula_diario.is_em_prova_final()
                assert not matricula_diario.is_aprovado_em_prova_final()
                assert matricula_diario.is_aprovado_por_nota()
                assert matricula_diario.is_aprovado_por_frequencia()
                assert matricula_diario.is_aprovado()
                assert matricula_diario.get_media_disciplina() == nota
                assert matricula_diario.get_media_final_disciplina() == nota

            elif (
                nota >= matricula_diario.diario.turma.matriz.estrutura.media_evitar_reprovacao_direta
                and nota < matricula_diario.diario.turma.matriz.estrutura.media_aprovacao_sem_prova_final
            ):
                # lançando uma nota para levar o aluno para prova final
                url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
                self.client.get(url)
                data = {'lancamento_nota': 1, f'{1};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}': nota}  # 50
                response = self.client.post(url, data)
                matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario.pk)
                self.assert_no_validation_errors(response)
                assert matricula_diario.is_carga_horaria_diario_fechada()
                assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_nota()['rotulo'] == 'Prova Final'
                assert matricula_diario.get_situacao_diario()['rotulo'] == 'Prova Final'
                assert matricula_diario.get_situacao_registrada_diario()['rotulo'] == 'Cursando'
                assert not matricula_diario.pode_fechar_periodo_letivo()
                assert matricula_diario.is_cursando()
                assert matricula_diario.realizou_todas_avaliacoes_regulares()
                assert not matricula_diario.realizou_todas_avaliacoes()
                assert not matricula_diario.is_aprovado_sem_prova_final()
                assert not matricula_diario.realizou_avaliacao_final()
                assert matricula_diario.is_em_prova_final()
                assert not matricula_diario.is_aprovado_em_prova_final()
                assert not matricula_diario.is_aprovado_por_nota()
                assert matricula_diario.is_aprovado_por_frequencia()
                assert not matricula_diario.is_aprovado()
                assert matricula_diario.get_media_disciplina() == nota
                assert matricula_diario.get_media_final_disciplina() is None

        elif etapa == 5:
            nota_avaliacao = matricula_diario.get_notas_etapa_5()[0]
            if not nota:
                # Retirando a nota da avaliação final
                url = f'/edu/meu_diario/{matricula_diario.diario.pk}/5/'
                self.client.get(url)
                data = {'lancamento_nota': 1, f'{5};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}': ''}
                self.client.post(url, data)
                matricula_diario = self.recarregar(matricula_diario)
                assert matricula_diario.nota_final is None

            elif nota >= matricula_diario.diario.turma.matriz.estrutura.media_aprovacao_avaliacao_final:
                # lançando uma nota para aprovar o aluno na avaliação final
                url = f'/edu/meu_diario/{matricula_diario.diario.pk}/5/'
                self.client.get(url)
                data = {'lancamento_nota': 1, f'{5};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}': nota}  # 80
                response = self.client.post(url, data)
                matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario.pk)
                self.assert_no_validation_errors(response)
                assert matricula_diario.nota_1 is not None
                assert matricula_diario.is_carga_horaria_diario_fechada()
                assert matricula_diario.get_situacao_frequencia()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_nota()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_diario()['rotulo'] == 'Aprovado'
                assert matricula_diario.get_situacao_registrada_diario()['rotulo'] == 'Cursando'
                assert matricula_diario.pode_fechar_periodo_letivo()
                assert matricula_diario.is_cursando()
                assert matricula_diario.realizou_todas_avaliacoes_regulares()
                assert matricula_diario.realizou_todas_avaliacoes()
                assert not matricula_diario.is_aprovado_sem_prova_final()
                assert matricula_diario.realizou_avaliacao_final()
                assert matricula_diario.is_em_prova_final()
                assert matricula_diario.is_aprovado_em_prova_final()
                assert matricula_diario.is_aprovado_por_nota()
                assert matricula_diario.is_aprovado_por_frequencia()
                assert matricula_diario.is_aprovado()
                assert matricula_diario.get_media_disciplina() == matricula_diario.nota_1
                assert matricula_diario.get_media_final_disciplina() == nota
                # Voltando a nota para aprovar o aluno direto
                response = self.client.post(url, data)
                self.assert_no_validation_errors(response)
                matricula_diario = self.recarregar(matricula_diario)
                assert matricula_diario.nota_1 is not None
                assert matricula_diario.nota_final is not None
            else:
                # TODO Reprovado na prova final
                pass

        # visualizando a mensagem de registro de notas
        url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
        response = self.client.get(url)
        assert 'Etapa 1' in response.content.decode()
        assert response.status_code == 200
        assert 'Notas registradas com sucesso' in response.content.decode()

    def alterar_configuracao_avaliacao(self):
        matricula_diario = self.retornar(MatriculaDiario)
        nota_avaliacao = matricula_diario.get_notas_etapa_1()[0]

        # acessando meu diário
        url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
        response = self.client.get(url)
        assert 'Etapa 1' in response.content.decode()
        assert response.status_code == 200

        for k, v in ConfiguracaoAvaliacao.FORMA_CALCULO_CHOICES:
            nota_final = None

            itens = [
                {'tipo': ItemConfiguracaoAvaliacao.TIPO_PROVA, 'sigla': 'T1', 'nota_maxima': 100},
                {'tipo': ItemConfiguracaoAvaliacao.TIPO_PROVA, 'sigla': 'T2', 'nota_maxima': 100},
            ]
            if v == 'Média Aritmética':
                nota1 = 60
                nota2 = 100
                nota_final = 80
                divisor = None
            elif v == 'Soma Simples':
                itens[0].update({'nota_maxima': 50})
                itens[1].update({'nota_maxima': 50})
                nota1 = 40
                nota2 = 50
                nota_final = 90
                divisor = None
            elif v == 'Média Ponderada':
                peso1 = 65
                peso2 = 35
                itens[1].update({'peso': peso1})
                itens[0].update({'peso': peso2})
                nota1 = 80
                nota2 = 60
                divisor = None
                nota_final = ((nota1 * peso1) + (nota2 * peso2)) / (peso1 + peso2)
            elif v == 'Soma com Divisor Informado':
                nota1 = 70
                nota2 = 80
                divisor = 2
                nota_final = 75
            elif v == 'Maior Nota':
                nota1 = 73
                nota2 = 72
                nota_final = 73
                divisor = None

            if nota_final:
                # removendo as notas lançadas anteriormente
                url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
                response = self.client.get(url)
                notas_avaliacao = matricula_diario.get_notas_etapa_1()
                data = {'lancamento_nota': 1}
                for nota_avaliacao in notas_avaliacao:
                    data[f'{1};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}'] = ('',)
                response = self.client.post(url, data)

                # atualizando a configuração avaliação
                configuracao_avaliacao_antes = ConfiguracaoAvaliacao.objects.all().count()
                self.atualizar_configuracao_avaliacao(
                    nota_avaliacao.item_configuracao_avaliacao.configuracao_avaliacao, forma_calculo=k, itens=itens, divisor=divisor
                )

                configuracao_avaliacao_depois = ConfiguracaoAvaliacao.objects.all().count()
                assert configuracao_avaliacao_depois == configuracao_avaliacao_antes

                matricula_diario = self.retornar(MatriculaDiario)
                assert matricula_diario.nota_1 is None

                url = f'/edu/meu_diario/{matricula_diario.diario.pk}/1/'
                response = self.client.get(url)
                notas_avaliacao = matricula_diario.get_notas_etapa_1()
                data = {
                    'lancamento_nota': 1,
                    f'{1};{matricula_diario.pk};{notas_avaliacao[0].item_configuracao_avaliacao.pk}': nota1,
                    f'{1};{matricula_diario.pk};{notas_avaliacao[1].item_configuracao_avaliacao.pk}': nota2,
                }
                response = self.client.post(url, data)

                self.assert_no_validation_errors(response)

                matricula_diario = self.retornar(MatriculaDiario)
                # TODO parou de funcionar no django 1.9 com sqlite
                # self.assertEqual(matricula_diario.nota_1, nota_final)

    def imprimir_diario(self):
        diario = self.retornar(Diario)
        # acessando a página de impressão de boletim do diário
        url = f'/edu/emitir_boletins_pdf/{diario.pk}/?html=1'
        response = self.client.get(url)
        assert 'BOLETIM DE NOTAS DO DIÁRIO' in response.content.decode()
        assert response.status_code == 200
        # acessando a página de impressão da relação de alunos
        url = f'/edu/relacao_alunos_pdf/{diario.pk}/?html=1'
        response = self.client.get(url)
        assert 'RELAÇÃO DE ALUNOS' in response.content.decode()
        assert response.status_code == 200
        # acessando a página de impressão de diário para a etapa 1
        url = f'/edu/diario_pdf/{diario.pk}/1/?html=1'
        response = self.client.get(url)
        assert 'REGISTRO DE ATIVIDADES' in response.content.decode()
        assert response.status_code == 200

    def visualizar_boletim_individual(self):
        aluno = self.retornar(Aluno)
        # acessando o boletim
        url = f'/edu/emitir_boletim_pdf/{aluno.get_ultima_matricula_periodo().id}/?html=1'
        response = self.client.get(url)
        assert 'BOLETIM DE NOTAS INDIVIDUAL' in response.content.decode()

    def entregar_etapa(self, etapa=1):
        matricula_diario = self.retornar(MatriculaDiario)
        # entregando a etapa
        url = f'/edu/entregar_etapa/{matricula_diario.diario.pk}/{etapa}/'
        data = {'zerar_notas': False}
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Etapa entregue com sucesso.' in response.content.decode()
        matricula_diario = self.recarregar(matricula_diario)
        assert getattr(matricula_diario.diario, f'posse_etapa_{etapa}') == Diario.POSSE_REGISTRO_ESCOLAR

    def lancar_notas_secretario(self, nota='', etapa=1):
        matricula_diario = self.retornar(MatriculaDiario)
        nota_avaliacao = matricula_diario.get_notas_etapa_1()[0]
        # acessando a página de visualização de diário na aba "Lançamento de Notas/Faltas"
        url = f'/edu/diario/{matricula_diario.diario.pk}/?tab=notas_faltas'
        data = {'lancamento_nota': 1, f'{etapa};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}': nota}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)

    def alterar_aulas_faltas_notas(self):
        matricula_diario = self.retornar(MatriculaDiario)
        nota_avaliacao = matricula_diario.get_notas_etapa_1()[0]
        # acessando a página de visualização de diário na aba "Lançamento de Notas/Faltas"
        url = f'/edu/diario/{matricula_diario.diario.pk}/?tab=notas_faltas'
        response = self.client.get(url)
        assert (
            f'Diário ({matricula_diario.diario.pk}) - {matricula_diario.diario.componente_curricular.componente.sigla}' in response.content.decode()
        )
        assert response.status_code == 200
        # tranferindo a posse do diário do professor para o registro escolar
        url = f'/edu/transferir_posse_diario/{matricula_diario.diario.pk}/{1}/{Diario.POSSE_REGISTRO_ESCOLAR}/'
        self.client.get(url)
        url = f'/edu/diario/{matricula_diario.diario.pk}/?tab=notas_faltas'
        response = self.client.get(url)
        assert 'Posse transferida com sucesso.' in response.content.decode()
        # acessando a página de listagem de aulas cadastradas para a etapa 1
        url = f'/edu/registrar_chamada/{matricula_diario.diario.pk}/1/'
        assert url in response.content.decode()
        self.client.get(url)
        # acessando a página de cadastro de aula
        aula = self.retornar(Aula)
        url = f'/edu/adicionar_aula_diario/{matricula_diario.diario.pk}/1/{aula.pk}/'
        self.client.get(url)
        # atualizando uma aula
        data = {
            'professor_diario': aula.professor_diario.pk,
            'etapa': '1',
            'tipo': 1,
            'quantidade': aula.quantidade,
            'data': '01/01/2013',
            'conteudo': aula.conteudo,
        }
        assert matricula_diario.diario.get_horas_aulas_etapa_1() == 10
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        temp = Diario.locals.get(pk=matricula_diario.diario.pk)
        assert temp.get_horas_aulas_etapa_1() == 10

        # acessando a página de visualização de diário na aba "Lançamento de Notas/Faltas"
        url = f'/edu/diario/{matricula_diario.diario.pk}/?tab=notas_faltas'
        self.client.get(url)
        # lançando a mesma nota definida pelo professor para a etapa 1
        data = {'lancamento_nota': 1, f'{1};{matricula_diario.pk};{nota_avaliacao.item_configuracao_avaliacao.pk}': matricula_diario.nota_1}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario.pk)
        assert matricula_diario.nota_1 is not None

    def solicitar_relancamento_etapa(self):
        self.retornar(MatriculaDiario)
        professor_diario = self.retornar(ProfessorDiario)
        # solicitando relançamento da etapa 1
        numero_solicitacao_antes = SolicitacaoUsuario.objects.count()
        numero_solicitacao_relancamento_antes = SolicitacaoRelancamentoEtapa.objects.count()
        url = f'/edu/solicitar_relancamento_etapa/{professor_diario.pk}/1/'
        data = {'motivo': 'Motivo de Teste.'}
        self.client.post(url, data)
        numero_solicitacao_depois = SolicitacaoUsuario.objects.count()
        numero_solicitacao_relancamento_depois = SolicitacaoRelancamentoEtapa.objects.count()
        assert numero_solicitacao_relancamento_depois == numero_solicitacao_relancamento_antes + 1
        assert numero_solicitacao_depois == numero_solicitacao_antes + 1
        assert SolicitacaoRelancamentoEtapa.objects.order_by('-id').all()[0].solicitante.username == professor_diario.professor.vinculo.user.username

    def indeferir_solicitacao_relancamento_etapa(self):
        # indeferindo a solicitacao de relançamento de etapa
        url = '/admin/edu/solicitacaousuario/'
        self.client.get(url)
        solicitacao = self.retornar(SolicitacaoRelancamentoEtapa)
        url = f'/edu/rejeitar_solicitacao/{solicitacao.pk}/'
        self.client.get(url)
        data = {'razao_indeferimento': 'Fora de prazo.'}
        self.client.post(url, data)
        solicitacao = self.recarregar(solicitacao)
        assert solicitacao.avaliador.username == self.servidor_b.matricula
        assert not solicitacao.atendida

    def deferir_solicitacao_relancamento_etapa(self):
        # deferindo a solicitação
        solicitacao = self.retornar(SolicitacaoRelancamentoEtapa)
        url = f'/edu/solicitacaousuario/{solicitacao.pk}/?atender=1'
        response = self.client.get(url)
        self.assert_no_validation_errors(response)
        solicitacao = self.recarregar(solicitacao)
        assert solicitacao.avaliador.username == self.servidor_b.matricula
        assert solicitacao.atendida

    def fechar_periodo(self, forcar_fechamento, situacao_matricula, situacao_matricula_periodo, situacao_diario, componentes_situacoes=None):
        matricula_diario = self.retornar(MatriculaDiario)
        # acessando a página de fechamento de período letivo
        url = '/edu/fechar_periodo_letivo/'
        self.client.get(url)
        data = {
            'ano_letivo': matricula_diario.matricula_periodo.ano_letivo.pk,
            'periodo_letivo': matricula_diario.matricula_periodo.periodo_letivo,
            'tipo': 'MATRICULA',
            'aluno': matricula_diario.matricula_periodo.aluno.pk,
        }
        response = self.client.get(url, data)
        self.assert_no_validation_errors(response)
        assert matricula_diario.matricula_periodo.aluno.matricula in response.content.decode()
        if forcar_fechamento:
            data.update({'confirmado': 'on', 'forcar_fechamento': 'on'})
        else:
            data.update({'confirmado': 'on'})
        response = self.client.get(url, data, follow=True)
        self.assert_no_validation_errors(response)
        matricula_diario = self.recarregar(matricula_diario)
        assert matricula_diario.matricula_periodo.aluno.situacao.pk == situacao_matricula
        assert matricula_diario.matricula_periodo.situacao.pk == situacao_matricula_periodo

        assert '100' in response.content.decode()

        if componentes_situacoes:
            for componente, situacao in list(componentes_situacoes.items()):
                matricula_diario = MatriculaDiario.objects.get(diario__componente_curricular__componente__descricao=componente)
                assert matricula_diario.situacao == situacao
        else:
            assert matricula_diario.situacao == situacao_diario

        return response

    def abrir_periodo(self):
        matricula_diario = self.retornar(MatriculaDiario)
        # Reabrindo o período
        # acessando a página de reabertura de período letivo
        url = '/edu/abrir_periodo_letivo/'
        self.client.get(url)
        data = {
            'ano_letivo': matricula_diario.matricula_periodo.ano_letivo.pk,
            'periodo_letivo': matricula_diario.matricula_periodo.periodo_letivo,
            'tipo': 'MATRICULA',
            'aluno': matricula_diario.matricula_periodo.aluno.pk,
        }
        response = self.client.get(url, data)
        self.assert_no_validation_errors(response)
        # self.assertContains(response, matricula_diario.matricula_periodo.aluno.matricula)
        # abrindo período letivo
        data.update({'confirmado': 'on'})
        response = self.client.get(url, data, follow=True)
        matricula_diario = self.recarregar(matricula_diario)
        self.assert_no_validation_errors(response)
        # self.assertContains(response, u'100%')

        url = '{}?continue=1'.format(response.request['PATH_INFO'])
        response = self.client.get(url, follow=True)
        self.assert_no_validation_errors(response)
        assert matricula_diario.matricula_periodo.aluno.situacao.pk == SituacaoMatricula.MATRICULADO

    def configurar_livro(self):
        aluno = self.retornar(Aluno)
        data = {
            'descricao': 'Livro 1',
            'uo': aluno.curso_campus.diretoria.setor.uo.id,
            'modalidades': [aluno.curso_campus.modalidade.id],
            'numero_livro': 1,
            'folhas_por_livro': 1,
            'numero_folha': 1,
            'numero_registro': 1,
        }
        return self.cadastrar(ConfiguracaoLivro, data)

    def cadastrar_processo(self):
        aluno = self.retornar(Aluno)
        # Cadastrando processo e configuracao de livro
        data = {
            'vinculo_cadastro': self.servidor_a.get_vinculo(),
            'uo': aluno.curso_campus.diretoria.setor.uo,
            'setor_origem': aluno.curso_campus.diretoria.setor,
            'numero_processo': '23057.003498.2009-59',
            'assunto': 'Processo',
            'tipo': 1,
            'palavras_chave': 'Processo',
        }
        Processo.objects.get_or_create(**data)

    def emitir_diploma(self):
        # Emitir diploma
        aluno = self.retornar(Aluno)
        processo = self.retornar(Processo)
        # Acessando a tela de emissão de diploma
        url = '/edu/emitir_diploma/'
        response = self.client.get(url)
        self.assert_no_validation_errors(response)
        assert 'Seleção do Aluno' in response.content.decode()
        # Primeiro passo do wizard - Selecionando o aluno concluido
        data = {'aluno': aluno.pk}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert 'Dados da Emissão' in response.content.decode()
        # Segundo passo do wizard - Selecionando o processo e emitindo o diploma
        data.update(processo=processo.pk, numero_formulario='12', numero_pasta='23', autenticacao_sistec='XXXXXX')
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Registro de emissão de diploma cadastrado com sucesso' in response.content.decode()

        self.acessar_como_administrador()
        # acessando admin de registro de emissao de diplomas
        url = '/admin/edu/registroemissaodiploma/'
        response = self.client.get(url)
        assert aluno.pessoa_fisica.nome in response.content.decode()
        assert response.status_code == 200
        self.acessar_como_secretario()

        registro_emissao = self.retornar(RegistroEmissaoDiploma)
        url = f'/edu/registroemissaodiploma/{registro_emissao.id}/?registrar=1'
        response = self.client.get(url, follow=True)
        assert 'Diploma registrado com sucesso' in response.content.decode()

    def emitir_diploma_lote(self):
        # Emitir diploma

        # selecionando uma turma
        turma = self.retornar(Turma)
        url = '/edu/emitir_diplomas/'
        # Acessando a tela de emissão de diploma
        response = self.client.get(url)
        self.assert_no_validation_errors(response)
        assert 'Seleção da Turma' in response.content.decode()
        # Primeiro passo do wizard - Selecionando a turma
        data = {'turma': turma.pk}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        # verificando se existe alunos para a turma selecionada
        assert 'Seleção dos Alunos' in response.content.decode()

        matricula_periodo = turma.matriculaperiodo_set.all()[0]

        processo = self.retornar(Processo)
        # Segundo passo do wizard - Selecionando o aluno concluido
        data.update(alunos=(matricula_periodo.aluno.pk,))
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert 'Dados da Emissão' in response.content.decode()

        # Terceiro passo do wizard - Selecionando o processo e emitindo o diploma
        data.update(processo=processo.pk, numero_formulario='12', prefixo='PASTA', numero_pasta='23')
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'Registros de emissão de diploma cadastrados com sucesso.' in response.content.decode()

        registro_emissao = self.retornar(RegistroEmissaoDiploma)
        url = f'/edu/registroemissaodiploma/{registro_emissao.id}/?registrar=1'
        response = self.client.get(url, follow=True)
        assert 'Diploma registrado com sucesso' in response.content.decode()

    def imprimir_registro_emissao_diploma(self):
        # Acessando o registro de emissão de diplomas
        registro_emissao = self.retornar(RegistroEmissaoDiploma)
        url = f'/edu/registroemissaodiploma/{registro_emissao.id}/'
        response = self.client.get(url)
        self.assert_no_validation_errors(response)
        assert 'Cancelar' in response.content.decode()
        assert registro_emissao.cancelado is False
        # Cancelando emissão do diploma
        url = f'/edu/cancelar_registroemissaodiploma/{registro_emissao.id}/'
        data = {'motivo_cancelamento': 'Erro de emissão'}
        response = self.client.post(url, data, follow=True)
        registro_emissao = RegistroEmissaoDiploma.objects.get(id=registro_emissao.id)
        self.assert_no_validation_errors(response)
        assert 'Registro de emissão de diploma cancelado com sucesso.' in response.content.decode()
        assert registro_emissao.cancelado is True

    def visualizar_historico(self, final=False):
        # acessando o histórico
        aluno = self.retornar(Aluno)
        if final:
            url = f'/edu/emitir_historico_final_pdf/{aluno.id}/?html=1'
        else:
            url = f'/edu/emitir_historico_parcial_pdf/{aluno.id}/?html=1'
        response = self.client.get(url)
        assert 'HISTÓRICO ESCOLAR' in response.content.decode()

    def procedimento_matricula(self, situacao_desejada):
        aluno = self.retornar(Aluno)
        opcoes = None
        url = None

        if situacao_desejada == SituacaoMatricula.CANCELAMENTO_COMPULSORIO:
            opcoes = '20;23;7'
            url = '/edu/realizar_cancelamento_matricula/{}/'
        elif situacao_desejada == SituacaoMatricula.CANCELADO:
            opcoes = '10;4;7'
            url = '/edu/realizar_cancelamento_matricula/{}/'
        elif situacao_desejada == SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO:
            opcoes = '97;97;7'
            url = '/edu/realizar_cancelamento_matricula/{}/'
        elif situacao_desejada == SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE:
            opcoes = '98;98;7'
            url = '/edu/realizar_cancelamento_matricula/{}/'
        elif situacao_desejada == SituacaoMatricula.EVASAO:
            opcoes = '9;15;7'
            url = '/edu/realizar_cancelamento_matricula/{}/'
        elif situacao_desejada == SituacaoMatricula.JUBILADO:
            opcoes = '3;14;7'
            url = '/edu/realizar_cancelamento_matricula/{}/'
        elif situacao_desejada == SituacaoMatricula.INTERCAMBIO:
            opcoes = '17;24;6'
            url = '/edu/realizar_trancamento_matricula/{}/'
        elif situacao_desejada == SituacaoMatricula.TRANCADO:
            opcoes = '2;3;6'
            url = '/edu/realizar_trancamento_matricula/{}/'
        elif situacao_desejada == SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE:
            opcoes = '99;99;6'
            url = '/edu/realizar_trancamento_matricula/{}/'

        url = url.format(aluno.get_ultima_matricula_periodo().id)

        # acessando o formulário
        response = self.client.get(url)
        assert 'ar Matrícula' in response.content.decode()
        assert response.status_code == 200

        # realizando o procedimento
        processo = self.retornar(Processo)
        data = {'processo': processo.pk, 'data': '31/05/2014', 'opcoes': opcoes, 'motivo': '.'}
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)

        # verificando se realmente funcionou
        aluno = self.recarregar(aluno)
        assert situacao_desejada == aluno.situacao.id

    def desfazer_ultimo_procedimento_matricula(self):
        aluno = self.retornar(Aluno)
        procedimento_matricula = self.retornar(ProcedimentoMatricula)

        url = f'{aluno.get_absolute_url()}?tab=procedimentos&procedimento_id={procedimento_matricula.pk}'
        response = self.client.get(url, follow=True)
        assert 'Procedimento desfeito com sucesso!' in response.content.decode()
        assert response.status_code == 200

        # testando se situação voltou
        aluno = self.recarregar(aluno)
        assert procedimento_matricula.situacao_matricula_anterior == aluno.situacao

    def pc_reintegracao(self, ano_letivo, periodo_letivo):
        # acessando o form de reintegração
        aluno = self.retornar(Aluno)
        ultimo_procedimento = self.retornar(ProcedimentoMatricula)
        situacao_anterior = ultimo_procedimento.situacao_matricula_anterior.id
        url = f'/edu/reintegrar_aluno/{aluno.get_ultima_matricula_periodo().pk}/'
        response = self.client.get(url)
        assert 'Reintegrar Aluno' in response.content.decode()
        assert response.status_code == 200

        # realizando a reintegração
        processo = self.retornar(Processo)
        data = {
            'processo': processo.pk,
            'data': '01/06/2014',
            'motivo': 'Foi solicitado pelo aluno.',
            'ano_letivo': ano_letivo.id,
            'periodo_letivo': periodo_letivo,
        }
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        # verificando se realmente reintegrou o aluno
        aluno = self.recarregar(aluno)
        assert situacao_anterior == aluno.situacao.id

    def cadastrar_polo(self, **params):
        """
        Cria um polo com valores padrões caso não seja passado parâmetro
        """

        init = {
            'descricao': 'Polo Padrão',
            'sigla': 'PP',
            'cidade': self.retornar(Cidade).pk,
            'estrutura_disponivel': 'Básica',
            'logradouro': 'Rua Qualquer',
            'numero': '70',
            'complemento': '',
            'bairro': 'Tirol',
            'cep': '58071100',
            'do_municipio': False,
            'diretoria': self.retornar(Diretoria).pk,
            'telefone_principal': '8422222222',
            'telefone_secundario': '8432333333',
        }
        init.update(params)
        return self._orm_create(Polo, init)

    def acessar_polo(self):
        polo = self.retornar(Polo)
        url = f'/edu/polo/{polo.id}/'
        response = self.client.get(url)
        assert polo.descricao in response.content.decode()
        assert response.status_code == 200

    def cadastrar_atividade_polo(self, **params):
        """
        Cria uma atividade do polo com valores padrões caso não seja passado parâmetro
        """

        url = '/admin/edu/atividadepolo/add/'
        response = self.client.get(url)
        assert 'Adicionar Atividade do Polo' in response.content.decode()
        assert response.status_code == 200
        count = AtividadePolo.objects.all().count()
        init = {
            'polo': self.retornar(Polo).id,
            'nome': 'Atividade 1',
            'descricao': 'Faça uma atividade valendo nota.',
            'sala': self.retornar(Sala).id,
            'data_inicio': '11/06/2013',
            'data_fim': '12/06/2013',
        }

        init.update(params)
        response = self.client.post(url, init)
        self.assert_no_validation_errors(response)
        assert AtividadePolo.objects.all().count() == count + 1
        return AtividadePolo.objects.all().order_by('-id')[0]

    def cadastrar_estrutura_curso(self, **params):
        """
        Cria uma estrutura de curso com valores padrões caso não seja passado parâmetro
        """

        init = {
            'descricao': 'PRONATEC / FICs 75%',
            'tipo_avaliacao': EstruturaCurso.TIPO_AVALIACAO_FIC,
            'limite_reprovacao': '0',
            'qtd_minima_disciplinas': '0',
            'criterio_avaliacao': EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
            'media_aprovacao_sem_prova_final': '70',
            'media_evitar_reprovacao_direta': '50',
            'media_aprovacao_avaliacao_final': '70',
            'percentual_frequencia': '75',
            'ira': EstruturaCurso.IRA_ARITMETICA_NOTAS_FINAIS,
            'numero_disciplinas_superior_periodo': '2',
            'qtd_periodos_conclusao': 0,
            'qtd_max_reprovacoes_periodo': 0,
            'qtd_max_reprovacoes_disciplina': 0,
            'percentual_max_aproveitamento': 0,
            'numero_max_certificacoes': 0,
            'media_certificacao_conhecimento': 0,
            'fator_acrescimo_periodo_letivo': 1,
            'calculo_media_final': 2,
        }
        init.update(params)
        return self._orm_create(EstruturaCurso, init)

    def cadastrar_matriz(self, **params):
        """
        cria uma matriz curricular com valores padrões caso não seja passado o parâmetro
        """
        nivel_ensino_pk = params.get('nivel_ensino')
        if not nivel_ensino_pk:
            nivel_ensino_pk = self.retornar(NivelEnsino).pk
        natureza_participacao_pk = params.get('natureza_participacao')
        if not natureza_participacao_pk:
            natureza_participacao_pk = self.retornar(NaturezaParticipacao).pk
        init = {
            'descricao': 'Mestrado em Agricultor Familiar',
            'ano_criacao': self.ano_2013.pk,
            'periodo_criacao': '1',
            'data_inicio': '11/06/2013',
            'data_fim': '',
            'ativo': 'on',
            'nivel_ensino': nivel_ensino_pk,
            'natureza_participacao': natureza_participacao_pk,
            'qtd_periodos_letivos': '3',
            'ch_componentes_obrigatorios': '20',
            'ch_componentes_optativos': '0',
            'ch_componentes_eletivos': '0',
            'ch_seminarios': '0',
            'ch_componentes_tcc': '10',
            'ch_pratica_profissional': '0',
            'ch_atividades_complementares': '0',
            'ch_atividades_aprofundamento': '0',
            'ch_atividades_extensao': '0',
            'ch_pratica_como_componente': '0',
            'ch_visita_tecnica': '0',
            'ch_componentes_extensao': '0',
            'ch_componentes_com_extensao': '0',
        }
        init.update(params)
        return self._orm_create(Matriz, init)

    def cadastrar_componente_curricular(self, tipo_componente, **params):
        diretoria_pk = params.get('diretoria')
        nivel_ensino_pk = params.get('nivel_ensino')
        if not diretoria_pk:
            diretoria_pk = self.retornar(Diretoria).pk
        if not nivel_ensino_pk:
            nivel_ensino_pk = self.retornar(NivelEnsino).pk
        init = {
            'descricao': 'Administração da propriedade rural',
            'descricao_historico': 'Administração da propriedade rural',
            'abreviatura': 'ADMPR',
            'tipo': tipo_componente.pk,
            'diretoria': diretoria_pk,
            'nivel_ensino': nivel_ensino_pk,
            'ch_hora_relogio': '10',
            'ch_hora_aula': '10',
            'ch_qtd_creditos': '10',
        }
        init.update(params)
        return self._orm_create(Componente, init)

    def vincular_componente(self, matriz, componente, **params):
        nucleo_pk = params.get('nucleo')
        if not nucleo_pk:
            nucleo_pk = self.retornar(Nucleo)
        # vinculando Componente A à matriz no primeiro periodo
        url = f'/edu/matriz/{matriz.pk}/vincular_componente/'
        response = self.client.get(url)
        assert 'Vincular Componente de Matriz' in response.content.decode()
        assert response.status_code == 200
        count = matriz.componentecurricular_set.count()
        init = {
            'matriz': matriz.pk,
            'componente': componente.pk,
            'tipo': '1',
            'qtd_avaliacoes': '1',
            'nucleo': nucleo_pk,
            'ch_presencial': '10',
            'ch_pratica': '0',
            'ch_extensao': '0',
            'percentual_maximo_ead': '0',
            'qtd_aulas_ead': '0',
            'ch_pcc': 0,
            'ch_visita_tecnica': 0,
        }
        init.update(params)
        response = self.client.post(url, init)
        self.assert_no_validation_errors(response)
        assert matriz.componentecurricular_set.count() == count + 1

    def cadastrar_curso(self, data):
        # acessando a página de cadastro de curso
        url = '/admin/edu/cursocampus/add/'
        response = self.client.get(url)
        assert 'Adicionar Curso' in response.content.decode()
        assert response.status_code == 200
        count = CursoCampus.locals.all().count()
        response = self.client.post(url, data)
        self.assert_no_validation_errors(response)
        assert CursoCampus.locals.all().count() == count + 1

        return self.retornar(CursoCampus)

    def definindo_horario_diario(self, dias_semana=None, descricao_componente=None):
        if dias_semana is None:
            dias_semana = []
        diario = None
        if descricao_componente:
            diario = Diario.objects.filter(componente_curricular__componente__descricao=descricao_componente).order_by('-id')[0]
        else:
            diario = self.retornar(Diario)

        url = f'/edu/diario/{diario.pk}/'
        response = self.client.get(url)
        # localizando o link de acesso à página de e definição de horário
        url = f'/edu/definir_horario_aula_diario/{diario.pk}/'
        assert url in response.content.decode()
        # acessando a página de definição de horário
        response = self.client.get(url)
        assert 'Definir Horário de Aula' in response.content.decode()
        assert response.status_code == 200
        assert diario.horarioauladiario_set.filter(dia_semana__in=dias_semana).count() == 0
        horario_campus = diario.horario_campus
        horarios_aulas = horario_campus.horarioaula_set.all().order_by('-id')

        horarios = []
        # mantendo os horarios salvos previamente
        for horario_aula_diario in diario.horarioauladiario_set.all():
            horarios.append(f'{horario_aula_diario.horario_aula.pk};{horario_aula_diario.dia_semana}')
        # add horarios nos dias_semana passado
        for dia_semana in dias_semana:
            for i in range(3):
                horarios.append(f'{horarios_aulas[i].pk};{dia_semana}')

        data = {'horario': horarios}

        response = self.client.post(f'/edu/definir_horario_aula_diario/{diario.pk}/', data, follow=True)
        assert 'Horário definido com sucesso' in response.content.decode()
        assert response.status_code == 200

        for dia_semana in dias_semana:
            dia_semana += 1
            assert f'{dia_semana}M123' in diario.get_horario_aulas()

    def enviar_mensagem(self):
        # acessando url para envio de mensagem
        url = '/edu/enviar_mensagem/'
        response = self.client.get(url)
        assert 'Nova Mensagem' in response.content.decode()
        assert response.status_code == 200

        # contando mensagens enviadas
        numero_mensagens_antes = Mensagem.objects.count()

        # selecionando uma turma para envio de mensagem
        turma = self.retornar(Turma)
        aluno = self.retornar(Aluno)
        data = {'alunos': aluno.pk, 'turma': turma.pk, 'forma_envio': 1}
        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)

        assert aluno.matricula in response.content.decode()
        data.update({'assunto': 'Assunto da menssagem', 'conteudo': 'Conteúdo da mensagem', 'confirmacao': 'on'})

        response = self.client.post(url, data, follow=True)
        self.assert_no_validation_errors(response)
        assert 'enviadas com sucesso' in response.content.decode()

        # verificando a mensagem foi persistida
        numero_mensagens_depois = Mensagem.objects.count()
        assert numero_mensagens_depois == numero_mensagens_antes + 1

        # acessando a caixa de saida
        url = '/admin/edu/mensagemsaida/'
        response = self.client.get(url)
        assert 'Assunto da menssagem' in response.content.decode()
        assert response.status_code == 200

    def caixa_entrada_aluno(self):
        # acessando url
        url = '/comum/index/minhas_pendencias/'
        response = self.client.get(url)
        assert 'Mensagem' in response.content.decode()
        assert response.status_code == 200
        assert 'não lida' in response.content.decode()
        assert response.status_code == 200

        # acessando caixa de entrada como aluno
        url = '/admin/edu/mensagementrada/'
        response = self.client.get(url)
        assert 'Mensagens Recebidas' in response.content.decode()
        assert response.status_code == 200

        # acessando uma mensagem
        mensagem = self.retornar(Mensagem)
        url = f'/edu/mensagem/{mensagem.pk}/'
        response = self.client.get(url)
        assert 'Assunto da menssagem' in response.content.decode()
        assert response.status_code == 200
