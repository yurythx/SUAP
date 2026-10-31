import datetime
import json
import traceback
import zlib
from os.path import join
from uuid import uuid4

import sentry_sdk
import xmltodict
from bs4 import BeautifulSoup
from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.aggregates import Sum
from django.dispatch import Signal
from requests import RequestException

from comum.models import Ano, UsuarioGrupoSetor
from comum.utils import get_uo, tl
from djtools.db import models
from djtools.templatetags.filters import in_group
from djtools.utils import requests, send_mail, years_between
from edu.managers import FiltroDiretoriaManager, FiltroUnidadeOrganizacionalManager
from edu.models import Aluno, CursoCampus, LinhaPesquisa, LogModel, Matriz, MatrizCurso
from rh.models import Servidor, UnidadeOrganizacional

from . import importacao

ausencia_candidato_sinal = Signal()  # providing_args=["candidato_vaga_id"]
matricula_candidato_sinal = Signal()  # providing_args=["candidato_vaga_id"]
inaptidao_candidato_sinal = Signal()  # providing_args=["candidato_vaga_id"]


def parse_data_sgc(valor: str | None) -> datetime.date | None:
    if not valor:
        return None

    valor = valor.strip()[:10]
    for formato in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.datetime.strptime(valor, formato).date()
        except ValueError:
            continue
    return None


class PSFiltroDiretoriaManager(FiltroDiretoriaManager):
    def get_ids(self):
        user = tl.get_user()
        if user and user.groups.filter(name__in=['Operador de Editais de Ensino', 'Operador de Censo']).exists():
            return []
        return super().get_ids()


class Edital(LogModel):
    configuracao_migracao_vagas = models.ForeignKeyPlus(
        'processo_seletivo.ConfiguracaoMigracaoVaga',
        verbose_name='Configuração de Migração de Vagas',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    codigo = models.IntegerField('Código')
    descricao = models.CharFieldPlus('Descrição')
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE)
    semestre = models.IntegerField('Semestre')
    data_encerramento = models.DateField(verbose_name='Data de Encerramento', null=True, blank=True)

    # Novos atributos
    sisu = models.BooleanField('Sisu?', default=False)
    qtd_vagas = models.IntegerField('Quantidade de Vagas')
    qtd_inscricoes = models.IntegerField('Quantidade de Inscrições')
    qtd_inscricoes_confirmadas = models.IntegerField('Quantidade de Inscrições Confirmadas')

    detalhamento_por_campus = models.TextField('Detalhamento por Campus')
    """
    Abaixo temos um exemplo do valor presente dentro do atributo "detalhamento_por_campus". Para rotinar internas no
    SUAP, tomar com chave apenas o suap_unidade_organizacional_id. Essa chave é que indica para qual campus do SUAP deverá
    ser atribuído o detalhamento. Isso é necessário porque no SGC há campus que não usam o mesmo padrão de nomeclatura da
    sigla e também há campus que não existem no SUAP, como por exemplo os "Pólos", que são unidades EAD existesntes no
    SGC. Nesse caso específico, todos os valores deverão ser atribuídos ao campus EAD do SUAP.

    {"qtd_inscricoes": 125, "suap_unidade_organizacional_id": "14", "campus": "EaD", "qtd_inscricoes_confirmadas": 18, "qtd_vagas": 30}, {"qtd_inscricoes": 28, "suap_unidade_organizacional_id": "14", "campus": "Polo SC", "qtd_inscricoes_confirmadas": 6, "qtd_vagas": 30}]
    """

    remanescentes = models.BooleanField('Vagas Remanescentes?', default=False)
    matricula_no_polo = models.BooleanField('Matrícula no Polo?', default=False)
    webservice = models.ForeignKeyPlus(
        'processo_seletivo.WebService', verbose_name='WebService', null=True, blank=True, default=None, on_delete=models.CASCADE
    )

    matricula_online = models.BooleanField('Matrícula Online', default=False)
    permite_adicionar_vagas_extras = models.BooleanField('Permite Adicionar Vagas Extras', default=False)
    permite_adicionar_candidato_classificacao = models.BooleanField('Permite Adicionar Candidato à Classificação', default=False)

    arquivo_xml = models.FileField(verbose_name='Arquivo XML', upload_to='xmls', null=True, blank=True)

    objects = models.Manager()
    locals = PSFiltroDiretoriaManager('ofertavagacurso__curso_campus__diretoria')

    class Meta:
        verbose_name = 'Edital'
        verbose_name_plural = 'Editais'
        permissions = (
            ('pode_ausentar_candidatos', 'Pode Ausentar Candidatos'),
            ('pode_convocar', 'Pode convocar candidatos'),
            ('pode_liberar_periodos', 'Pode Liberar Periodos'),
            ('pode_matricular_proitec', 'Pode Matricular Alunos Proitec'),
        )

    def __str__(self):
        return f'{self.descricao}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def salvar_arquivo_xml(self, xml):
        self.arquivo_xml.save(f'{uuid4().hex}.xml', ContentFile(xml.encode()))

    def consultar_candidato(self, candidato_vaga):
        from xml.dom import minidom

        from comum.models import Raca
        from djtools.utils import normalizar_nome_proprio
        from edu.models import Cidade, Estado, OrgaoEmissorRg

        xml = self.webservice.candidato(self.codigo, candidato_vaga.candidato.inscricao, compactado=self.webservice.is_zipped)
        doc = minidom.parseString(xml.replace('&', ' e '))

        def getText(tag, normalizar=True):
            dados_pessoais = doc.getElementsByTagName('dados_pessoais')
            if dados_pessoais:
                if dados_pessoais[0].getElementsByTagName(tag):
                    nodelist = dados_pessoais[0].getElementsByTagName(tag)[0].childNodes
                    rc = []
                    for node in nodelist:
                        if node.nodeType == node.TEXT_NODE:
                            rc.append(node.data)
                    return normalizar and normalizar_nome_proprio(''.join(rc)) or ''.join(rc)
            return None

        def getTexto(tag, normalizar=True):
            return getText(tag, normalizar) or ''

        nascimento_municipio = getText('nascimento_municipio')
        nascimento_uf = Estado.get_estado_por_sigla(getText('nascimento_uf'))

        qs_naturalidade = Cidade.objects.filter(nome__unaccent__icontains=nascimento_municipio, estado=nascimento_uf)

        naturalidade = None
        if qs_naturalidade:
            naturalidade = qs_naturalidade[0]

        endereco_estado_obj = Estado.get_estado_por_sigla(getText('endereco_uf'))
        qs = Cidade.objects.filter(nome__unaccent__icontains=getText('endereco_municipio'), estado=endereco_estado_obj)

        if qs:
            cidade = qs[0]
        else:
            cidade = ''

        qs = OrgaoEmissorRg.objects.filter(nome__unaccent__icontains=getText('rg_orgao'))
        if qs:
            orgao = qs[0].id
        else:
            orgao = ''
        qs = Estado.get_estado_por_sigla(getText('rg_uf'))
        if qs:
            uf_emissao_rg_id = qs.id
        else:
            uf_emissao_rg_id = ''
        daga_emissao_rg = parse_data_sgc(getText('rg_data_emissao'))
        nascimento_data = parse_data_sgc(getText('nascimento_data'))

        nacionalidade = None
        nascimento_pais = getText('nascimento_pais')
        if nascimento_pais and nascimento_pais.upper() in ('BR', 'BRASIL'):
            nacionalidade = 'Brasileira'

        nome_mae = getTexto('mae_nome')
        nome_pai = getTexto('pai_nome')
        nome_responsavel = ''
        parentesco_responsavel = ''

        if nome_mae or nome_pai:
            """
            Presume nome do responsável a partir do nome da mãe
            ou do a pai informado
            """
            nome_responsavel = nome_mae or nome_pai
            parentesco_responsavel = 'Pai/Mãe'

        initial = {
            'nome': getTexto('nome'),
            'sexo': getText('sexo') or 'M',
            'estado_civil': getText('estado_civil') or 'Solteiro',
            'tipo_sanguineo': getText('tipo_sanguineo'),
            'raca': Raca.objects.filter(descricao=getText('etnia')).values_list('pk', flat=True).first(),
            'data_nascimento': nascimento_data,
            'nacionalidade': nacionalidade,
            'nome_mae': nome_mae,
            'nome_pai': nome_pai,
            'responsavel': nome_responsavel,
            'parentesco_responsavel': parentesco_responsavel,
            'logradouro': getTexto('endereco_logradouro'),
            'numero': getTexto('endereco_numero'),
            'complemento': getTexto('endereco_complemento'),
            'bairro': getTexto('endereco_bairro'),
            'cidade': cidade,
            'estado': endereco_estado_obj.pk,  # endereco_uf,
            'cep': getTexto('endereco_cep'),
            'telefone_principal': getTexto('telefone_residencial'),
            'telefone_secundario': getTexto('telefone_celular'),
            'email_pessoal': getTexto('email', False),
            'numero_rg': getTexto('rg_numero'),
            'uf_emissao_rg': uf_emissao_rg_id,
            'orgao_emissao_rg': orgao,
            'data_emissao_rg': daga_emissao_rg,
            'linha_pesquisa': candidato_vaga.oferta_vaga.oferta_vaga_curso.linha_pesquisa,
            'tipo_zona_residencial': getText('endereco_zona_residencial') == 'Urbana' and 1 or 0,
            'naturalidade': naturalidade,
        }
        return initial

    def get_pendencias(self):
        pendencias = []
        if self.lista_set.filter(forma_ingresso__isnull=True).exists():
            pendencias.append('As formas de ingresso de todas as listas ainda não foram definidas para este edital')
        if self.configuracao_migracao_vagas_id:
            if self.configuracao_migracao_vagas.is_sisu and not self.sisu:
                pendencias.append('Este edital não é SISU, mas uma configuração de migração de vagas SISU foi definida para ele')
            if self.sisu and not self.configuracao_migracao_vagas.is_sisu:
                pendencias.append('Este edital é SISU, mas uma configuração de migração de vagas que não é SISU foi definida para ele')
            precedencia_matricula = []
            for i in range(1, 16):
                rotulo_lista = getattr(self.configuracao_migracao_vagas, f'lista_{i}')
                if rotulo_lista:
                    precedencia_matricula.append(rotulo_lista.nome)
            for lista in self.lista_set.all():
                if lista.descricao not in precedencia_matricula:
                    pendencias.append(
                        f'A lista "{lista.descricao}" não consta na precedência de matrícula da configuração de migração de vagas definida para este edital'
                    )
                if (
                    lista.descricao not in ['AC', 'Geral']
                    and not self.configuracao_migracao_vagas.precedenciamigracao_set.filter(origem__nome=lista.descricao).exists()
                ):
                    pendencias.append(
                        f'A lista "{lista.descricao}" não consta na precedência de migração da configuração de migração de vagas definida para este edital'
                    )
        return pendencias

    def get_absolute_url(self):
        return f'/processo_seletivo/edital/{self.pk}/'

    def get_detalhamento_por_campus_sgc_agrupado_por_suap_unidade_organizacional_id(self, campus_id):
        campus = ''
        qtd_inscricoes_total = 0
        qtd_inscricoes_confirmadas_total = 0
        qtd_vagas_total = 0
        id_campus_localizado = False

        if self.detalhamento_por_campus:
            json_dict_list = json.loads(self.detalhamento_por_campus)
            for json_dict in json_dict_list:
                # Os campus do SGC (Sistema Gerenciador de Concursos) não necessariamente serão os mesmos do SUAP.
                # No caso, podem haver dois ou mais campus do SGC apontando para um mesmo campus do SUAP, ou seja,
                # usando o mesmo valor para o atributo "suap_unidade_organizacional_id".
                suap_unidade_organizacional_id = json_dict['suap_unidade_organizacional_id']
                if suap_unidade_organizacional_id and int(suap_unidade_organizacional_id) == campus_id:
                    id_campus_localizado = True
                    if campus:
                        campus += '; ' + json_dict['campus']
                    else:
                        campus += json_dict['campus']

                    qtd_inscricoes_total += json_dict['qtd_inscricoes'] or 0
                    qtd_inscricoes_confirmadas_total += json_dict['qtd_inscricoes_confirmadas'] or 0
                    qtd_vagas_total += json_dict['qtd_vagas'] or 0

            if id_campus_localizado:
                return {
                    'suap_unidade_organizacional_id': campus_id,
                    'campus': campus,
                    'qtd_inscricoes': qtd_inscricoes_total,
                    'qtd_inscricoes_confirmadas': qtd_inscricoes_confirmadas_total,
                    'qtd_vagas': qtd_vagas_total,
                }

        return None

    def em_periodo_avaliacao(self, campus=None):
        periodo_liberacao = EditalPeriodoLiberacao.objects.filter(edital=self)

        if campus is not None:
            periodo_liberacao = periodo_liberacao.filter(uo=campus)

        if not periodo_liberacao.exists():
            return False

        periodo_liberacao = periodo_liberacao.latest('id')

        if periodo_liberacao.data_fim_matricula and periodo_liberacao.data_limite_avaliacao:
            if periodo_liberacao.data_fim_matricula < datetime.datetime.now() <= periodo_liberacao.data_limite_avaliacao:
                return True
        return False

    def em_periodo_matricula(self, campus=None):
        now = datetime.datetime.now()
        periodo_liberacao = EditalPeriodoLiberacao.objects.filter(edital=self)

        if campus is not None:
            periodo_liberacao = periodo_liberacao.filter(uo=campus)

        if not periodo_liberacao.exists():
            return False

        periodo_liberacao = periodo_liberacao.latest('id')

        if periodo_liberacao.data_inicio_matricula is None or periodo_liberacao.data_fim_matricula is None:
            return False

        return periodo_liberacao.data_inicio_matricula <= now <= periodo_liberacao.data_fim_matricula

    def possui_curso_proitec(self):
        return self.get_ids_cursos_proitec().exists()

    def get_ids_cursos_proitec(self):
        return (
            OfertaVagaCurso.objects.filter(edital=self, curso_campus__matrizcurso__matriz__estrutura__proitec=True)
            .values_list('curso_campus__id', flat=True)
            .distinct()
        )

    def get_matrizes_pronatec(self):
        ids = MatrizCurso.objects.filter(curso_campus__id__in=self.get_ids_cursos_proitec()).values_list('matriz__id', flat=True)
        return Matriz.objects.filter(id__in=ids).distinct()

    def possui_aluno_matriculado(self):
        return Aluno.objects.filter(candidato_vaga__oferta_vaga__oferta_vaga_curso__edital=self).exists()

    def formas_ingresso_estao_configuradas(self):
        return not self.lista_set.filter(forma_ingresso__isnull=True).exists()

    def get_uos(self):
        pks_uos_edital = OfertaVagaCurso.locals.filter(edital=self).values_list('curso_campus__diretoria__setor__uo', flat=True)
        uos = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_edital)
        return uos

    def get_quantidade_vagas(self):
        return OfertaVaga.objects.filter(oferta_vaga_curso__edital=self).aggregate(Sum('qtd')).get('qtd__sum')

    def get_quantidade_vagas_ofertadas(self):
        return not self.remanescentes and self.get_quantidade_vagas() or 0

    def get_quantidade_candidatos(self):
        return self.candidato_set.count()

    def importar_caracterizacoes(self):
        xml = self.webservice and self.webservice.caracterizacoes(self.codigo)
        if xml:
            response = xmltodict.parse(xml)
            edital = response.get('edital')
            if edital.get('caracterizacoes'):
                # quando vem apenas uma caracterização a bilioteca não identifica como sendo uma lista
                if isinstance(edital.get('caracterizacoes').get('caracterizacao'), dict):
                    caracterizacao = edital.pop('caracterizacoes')
                    edital.update(caracterizacoes=[caracterizacao])
                Caracterizacao = apps.get_model('ae.Caracterizacao')
                return Caracterizacao.importar_caracterizacao(response)
        return 0, 0

    def expirar_candidatos_chamada(self, chamada):
        numero_processado = 0
        candidatos_vaga = CandidatoVaga.objects.filter(candidato__edital=self, convocacao=chamada)

        for candidato in candidatos_vaga:
            candidato.registrar_ausencia()
            numero_processado += 1

        return numero_processado

    def pode_ausentar(self, user, uo=None):
        if not user.has_perm('processo_seletivo.pode_ausentar_candidatos'):
            return False
        now = datetime.datetime.now()
        periodo_liberacao = EditalPeriodoLiberacao.objects.filter(edital=self, data_limite_avaliacao__lt=now)

        if uo:
            periodo_liberacao = periodo_liberacao.filter(uo=uo)

        if periodo_liberacao.exists():
            candidatos_vaga = CandidatoVaga.objects.filter(candidato__edital=self, convocacao__isnull=False).filter(
                Q(situacao__isnull=True) | Q(situacao=CandidatoVaga.AUSENTE)
            )
            if uo:
                candidatos_vaga = candidatos_vaga.filter(candidato__curso_campus__diretoria__setor__uo=uo)
            return candidatos_vaga.exists()

        return False

    def can_change(self, user):
        return in_group(user, ['Administrador Acadêmico', 'Operador de Editais de Ensino'])


class EditalPeriodoLiberacao(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional')
    usuario = models.ForeignKeyPlus('comum.User', null=True)
    data_inicio_matricula = models.DateTimeFieldPlus('Data de início das matrículas', null=True, blank=True)
    data_fim_matricula = models.DateTimeFieldPlus('Data de fim das matrículas', null=True, blank=True)
    data_limite_avaliacao = models.DateTimeFieldPlus('Data limite para avaliação', null=True, blank=True)

    introducao_notifiacao_matricula = models.TextField(
        verbose_name='Introdução da Notificação',
        null=True,
        blank=True,
        help_text='Texto que estará presente no corpo do e-mail que será enviado para o candidato.',
    )
    detalhamento_notifiacao_matricula = models.TextField(
        verbose_name='Detalhamento da Notificação',
        null=True,
        blank=True,
        help_text='Texto que será mostrado ao candidato após ele clicar no link para visualizar a mensagem detalhada.',
    )

    class Meta:
        verbose_name = 'Período de Liberação Matrícula'
        verbose_name_plural = 'Períodos de Liberação Matrícula'

    def get_detalhamento_notifiacao_matricula_html(self):
        if self.detalhamento_notifiacao_matricula:
            return self.detalhamento_notifiacao_matricula.replace('\n', '<br>')
        return None

    def get_notificacoes_matricula(self):
        return self.notificacaomatricula_set.order_by('candidato_vaga__oferta_vaga__oferta_vaga_curso__curso_campus', 'candidato_vaga')

    def enviar_notificacoes_matricula(self, candidato_vaga_id=None):
        total = 0
        qs = CandidatoVaga.objects.filter(
            candidato__edital=self.edital,
            oferta_vaga__oferta_vaga_curso__curso_campus__diretoria__setor__uo=self.uo,
            situacao=CandidatoVaga.MATRICULADO,
            candidato__email__isnull=False,
        )
        if candidato_vaga_id:
            qs = qs.filter(pk=candidato_vaga_id)
        else:
            qs = qs.filter(notificacaomatricula__isnull=True)
        assunto = 'SUAP - Notificação de Matrícula'
        values = qs.distinct().values_list(
            'pk', 'candidato__nome', 'aluno__vinculos__email_pessoal', 'oferta_vaga__oferta_vaga_curso__curso_campus__descricao_historico'
        )
        for pk, nome, email, curso in values:
            if email:
                notificacao = NotificacaoMatricula.objects.create(candidato_vaga_id=pk, periodo_liberacao=self, email=email)
                new_line = '\n'
                url = f'{settings.SITE_URL}/processo_seletivo/visualizar_notificacao_matricula/{notificacao.token}/'
                mensagem = f"""
                    Olá <b>{nome}</b>!
                    <br><br>
                    {self.introducao_notifiacao_matricula.replace(new_line, '<br>')}
                    <br><br>
                    Para obter mais detalhes sobre sua matrícula no curso <b>"{curso}"</b> e confirmar o recebimento desta notificação, acesse o link
                    <a href="{url}">{url}</a>.
                """
                send_mail(
                    assunto,
                    mensagem,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    html=None,
                )
                total += 1
        return total

    def __str__(self):
        return f'{self.uo}: {self.data_inicio_matricula}/{self.data_fim_matricula}'

    def save(self, *args, **kwargs):
        usuario = kwargs.pop('user', tl.get_user())
        anterior = None

        if self.pk is not None:
            anterior = EditalPeriodoLiberacao.objects.get(pk=self.pk)
        else:
            self.usuario = usuario

        super().save(*args, **kwargs)

        salvar_historico = False

        if anterior:  # Alteração de dados
            if self.data_inicio_matricula and anterior.data_inicio_matricula and self.data_inicio_matricula != anterior.data_inicio_matricula:
                salvar_historico = True
            else:
                if self.data_limite_avaliacao and anterior.data_limite_avaliacao and self.data_limite_avaliacao != anterior.data_limite_avaliacao:
                    salvar_historico = True

        if salvar_historico:
            periodo = EditalPeriodoLiberacaoHistorico()
            periodo.periodo_liberacao = self
            periodo.usuario = anterior.usuario
            periodo.data_inicio_matricula = anterior.data_inicio_matricula
            periodo.data_fim_matricula = anterior.data_fim_matricula
            periodo.data_limite_avaliacao = anterior.data_limite_avaliacao
            periodo.save()

    def pode_editar(self, user):
        return user.has_perm('processo_seletivo.add_edital') or (self.uo == get_uo(user) and user.has_perm('processo_seletivo.pode_liberar_periodos'))


class EditalPeriodoLiberacaoHistorico(models.ModelPlus):
    periodo_liberacao = models.ForeignKeyPlus(EditalPeriodoLiberacao)
    usuario = models.ForeignKeyPlus('comum.User', null=True)
    data_inicio_matricula = models.DateTimeFieldPlus('Data de início das matrículas', null=True, blank=True)
    data_fim_matricula = models.DateTimeFieldPlus('Data de fim das matrículas', null=True, blank=True)
    data_limite_avaliacao = models.DateTimeFieldPlus('Data limite para avaliação', null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = 'Histórico de Liberação de Matrícula'
        verbose_name_plural = 'Histórico de Liberações de Matrícula'


class Lista(LogModel):
    codigo = models.CharFieldPlus('Código')
    descricao = models.TextField('Descrição')
    forma_ingresso = models.ForeignKeyPlus('edu.FormaIngresso', verbose_name='Forma de Igresso', null=True, blank=True, on_delete=models.CASCADE)
    requer_avaliacao_banca = models.BooleanField(
        verbose_name='Requer Avaliação em Banca',
        null=True,
        blank=True,
        choices=[
            (None, '-----'),
            (True, 'Sim'),
            (False, 'Não'),
        ],
    )
    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', null=True, blank=False, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Lista'
        verbose_name_plural = 'Listas'
        ordering = ('descricao',)

    def __str__(self):
        return self.descricao


class OfertaVagaCurso(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital)
    curso_campus = models.ForeignKeyPlus(CursoCampus)
    linha_pesquisa = models.ForeignKeyPlus(LinhaPesquisa, null=True, on_delete=models.CASCADE)
    turno = models.ForeignKeyPlus('edu.Turno', verbose_name='Turno', null=True, on_delete=models.CASCADE)
    qtd_inscritos = models.IntegerField(verbose_name='Quantidade de Inscritos', default=0)
    campus_polo = models.CharFieldPlus(verbose_name='Campus/Polo', default='')

    objects = models.Manager()
    locals = PSFiltroDiretoriaManager('curso_campus__diretoria')

    class Meta:
        verbose_name = 'Oferta de Vaga em Curso'
        verbose_name_plural = 'Ofertas de Vagas em Curso'
        ordering = ('curso_campus',)

    def get_ofertas_vaga(self):
        ofertas_vaga = []
        if self.edital.configuracao_migracao_vagas_id:
            nomes_listas = self.edital.configuracao_migracao_vagas.get_nomes_listas_ordenadas_por_restricao()
            for nome_lista in nomes_listas:
                oferta_vaga = self.ofertavaga_set.filter(lista__descricao=nome_lista).first()
                if oferta_vaga:
                    ofertas_vaga.append(oferta_vaga)
        else:
            ofertas_vaga.extend(list(self.ofertavaga_set.all()))
        return ofertas_vaga

    def get_candidatos_aguardando_convocacao(self):
        return (
            CandidatoVaga.objects.filter(eliminado=False, convocacao__isnull=True, situacao__isnull=True, oferta_vaga__oferta_vaga_curso_id=self.pk)
            .values_list('candidato', flat=True)
            .distinct()
        )

    def is_processamento_encerrado(self):
        return not CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso_id=self.pk, situacao__isnull=True).exists()

    def get_total_vagas(self, incluir_vagas_extras=False):
        qtd = sum(self.ofertavaga_set.filter(qtd__isnull=False).values_list('qtd', flat=True))
        if incluir_vagas_extras:
            qtd += sum(CriacaoVagaRemanescente.objects.filter(oferta_vaga__oferta_vaga_curso=self, qtd__isnull=False).values_list('qtd', flat=True))
            qtd += self.ofertavaga_set.filter(vagas_recebidas_polos__isnull=False).values_list('vagas_recebidas_polos', flat=True).distinct().count()
        return qtd

    def get_total_inscritos(self):
        return (
            CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso_id=self.pk)
            .order_by('candidato')
            .values_list('candidato', flat=True)
            .distinct()
            .count()
        )

    def is_candidatos_sem_classificacao(self):
        return not CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso_id=self.pk).filter(classificacao__gt=0).exists()

    def get_total_matriculados(self):
        return CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso_id=self.pk, situacao=CandidatoVaga.MATRICULADO).count()

    def get_percentual_matriculados(self):
        total_vagas = self.get_total_vagas()
        total_matriculados = self.get_total_matriculados()
        return int(total_matriculados * 100 / total_vagas)

    def get_numero_ultima_chamada(self):
        qs = (
            CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso_id=self.pk, convocacao__isnull=False)
            .values_list('convocacao', flat=True)
            .order_by('-convocacao')
        )
        return qs.first() or 0

    def pode_convocar(self, user):
        result = user.has_perm('processo_seletivo.pode_convocar')
        if result and user.has_perm('comum.is_operador_de_censo'):
            result = (
                user.has_perm('comum.is_administrador_academico')
                or user.has_perm('comum.is_estagiario_academico_sistemico')
                or user.has_perm('comum.is_operador_de_editais_de_ensino')
            )
            if not result:
                groups_user = user.get_groups('processo_seletivo.pode_convocar').values_list('name', flat=True)
                result = UsuarioGrupoSetor.objects.filter(
                    setor__uo_id=self.curso_campus.diretoria.setor.uo_id, usuario_grupo__user=user, usuario_grupo__group__name__in=groups_user
                ).exists()
        return result

    def pode_cancelar_ultima_chamada(self):
        numero_ultima_chamada = self.get_numero_ultima_chamada()
        if numero_ultima_chamada > 1:
            qs = CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso_id=self.pk, convocacao=numero_ultima_chamada)
            return qs.exists() and not qs.filter(situacao__isnull=False).exists()
        return False

    @transaction.atomic()
    def cancelar_ultima_chamada(self):
        if self.pode_cancelar_ultima_chamada():
            numero_ultima_chamada = self.get_numero_ultima_chamada()
            CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso=self, convocacao=numero_ultima_chamada).update(convocacao=None, vaga=None)
            if numero_ultima_chamada > 1:
                numero_ultima_chamada -= 1
                qs_candidato_vaga = CandidatoVaga.objects.filter(
                    oferta_vaga__oferta_vaga_curso=self,
                    convocacao=numero_ultima_chamada,
                    vaga__isnull=True,
                    situacao__in=[CandidatoVaga.AUSENTE, CandidatoVaga.INAPTO],
                )
                for cv in qs_candidato_vaga:
                    vaga = Vaga.objects.filter(candidatovaga__isnull=True, oferta_vaga=cv.oferta_vaga).first()
                    cv.vaga = vaga
                    cv.save()

    def pode_realizar_nova_chamada(self):
        return not CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso_id=self.pk, convocacao__isnull=False, situacao__isnull=True).exists()

    def pode_migrar_vagas_na_primeira_chamada(self):
        return self.get_total_inscritos() <= self.get_total_vagas() and self.is_candidatos_sem_classificacao()

    def realizar_nova_chamada(self, importacao_edital=False):
        if importacao_edital and self.get_numero_ultima_chamada() == 1:
            numero_chamada = 1
        else:
            numero_chamada = self.get_numero_ultima_chamada() + 1
        migrar_vagas = numero_chamada > 1 or self.pode_migrar_vagas_na_primeira_chamada()
        return self.realizar_chamada(numero_chamada, migrar_vagas=migrar_vagas)

    @transaction.atomic()
    def realizar_chamada(self, numero_chamada, migrar_vagas=False):
        vagas = []
        convocados = []
        if numero_chamada == 1:
            ofertas_vaga = self.get_ofertas_vaga()
            for oferta_vaga in ofertas_vaga:
                convocados.extend(list(oferta_vaga.realizar_nova_chamada(numero_chamada)))

        if self.edital.configuracao_migracao_vagas_id:
            precedencias = self.edital.configuracao_migracao_vagas.get_precedencias(apenas_descricao=True)
        else:
            precedencias = [[lista.descricao, []] for lista in self.edital.lista_set.all()]
        if migrar_vagas:
            for origem, destinos in precedencias:
                oferta_vaga_origem = self.ofertavaga_set.filter(lista__descricao=origem).first()
                if oferta_vaga_origem:
                    convocados.extend(oferta_vaga_origem.realizar_nova_chamada(numero_chamada))
                    vagas = vagas + oferta_vaga_origem.get_vagas_disponiveis()
                    if vagas:
                        for destino in destinos:
                            while vagas:
                                oferta_vaga_destino = self.ofertavaga_set.filter(lista__descricao=destino).first()
                                if oferta_vaga_destino:
                                    vaga = vagas.pop()
                                    convocado = oferta_vaga_destino.convocar_proximo_candidato(vaga, numero_chamada)
                                    if convocado:
                                        convocados.append(convocado)
                                    else:
                                        vagas.append(vaga)
                                        break
                                else:
                                    break
        return convocados

    def get_numeros_chamadas(self):
        return list(range(1, self.get_numero_ultima_chamada() + 1))


class OfertaVaga(models.ModelPlus):
    oferta_vaga_curso = models.ForeignKeyPlus(OfertaVagaCurso, null=True)
    lista = models.ForeignKeyPlus(Lista, on_delete=models.CASCADE)
    qtd = models.IntegerField('Quantidade', null=True, default=0)
    qtd_semestre_1 = models.IntegerField('Quantidade 1º Semestre', null=True)
    qtd_semestre_2 = models.IntegerField('Quantidade 2º Semestre', null=True)
    vagas_recebidas_polos = models.ManyToManyField('processo_seletivo.Vaga', verbose_name='Vagas Recebidas de Polos')

    objects = models.Manager()
    locals = PSFiltroDiretoriaManager('oferta_vaga_curso__curso_campus__diretoria')

    class Meta:
        verbose_name = 'Oferta de Vaga'
        verbose_name_plural = 'Ofertas de Vagas'
        ordering = ('oferta_vaga_curso__curso_campus', 'lista__descricao')

    def __str__(self):
        return f'{self.oferta_vaga_curso.edital}, {self.oferta_vaga_curso.curso_campus.descricao_historico}, {self.lista.descricao}'

    def get_descricao_qtd_vagas(self):
        if self.qtd_semestre_1 or self.qtd_semestre_2:
            return f'{self.qtd_semestre_1 or 0}-{self.qtd_semestre_2 or 0}'
        return self.qtd

    def get_criacao_classificacao(self):
        return CriacaoClassificacao.objects.filter(candidato_vaga__oferta_vaga=self)

    def get_vagas_enviadas_polo(self):
        return self.vaga_set.filter(ofertavaga__isnull=False)

    def get_absolute_url(self):
        return f'/processo_seletivo/oferta_vaga/{self.pk}/'

    def get_candidatos_inaptos_ausentes(self):
        return self.candidatovaga_set.filter(convocacao__isnull=False, situacao__in=(CandidatoVaga.AUSENTE, CandidatoVaga.INAPTO))

    def get_candidatos_classificados(self):
        return self.candidatovaga_set.filter(eliminado=False)

    def get_candidatos_aprovados(self):
        return self.get_candidatos_classificados().filter(aprovado=True)

    def get_candidatos_convocados(self):
        return self.candidatovaga_set.filter(convocacao__isnull=False)

    def get_candidatos_convocados_aguardando_matricula(self):
        return self.candidatovaga_set.filter(convocacao__isnull=False, situacao__isnull=True)

    def get_candidatos_aguardando_convocacao(self):
        return self.candidatovaga_set.filter(eliminado=False, convocacao__isnull=True, situacao__isnull=True)

    def get_candidatos_matriculados(self):
        return self.candidatovaga_set.filter(situacao=CandidatoVaga.MATRICULADO)

    def vagas_pode_ser_migradas(self):
        is_sisu = self.oferta_vaga_curso.edital.configuracao_migracao_vagas and self.oferta_vaga_curso.edital.configuracao_migracao_vagas.is_sisu
        return (
            is_sisu
            or self.get_candidatos_matriculados().count() >= self.qtd
            or not self.get_candidatos_classificados().filter(situacao__isnull=True).exists()
        )

    def get_vagas_usadas_de_migracao(self):
        return Vaga.objects.filter(candidatovaga__oferta_vaga=self).exclude(oferta_vaga_id=self.pk)

    def get_info_vagas_usadas_de_migracao(self):
        lista = []
        for item in self.get_vagas_usadas_de_migracao().values('oferta_vaga__lista__descricao').annotate(dcount=Count('pk')):
            lista.append('{} : {}'.format(item['oferta_vaga__lista__descricao'], item['dcount']))
        return '\n'.join(lista)

    def get_vagas_usadas_em_migracao(self):
        return self.vaga_set.filter(candidatovaga__isnull=False).exclude(candidatovaga__oferta_vaga_id=self.pk)

    def get_info_vagas_usadas_em_migracao(self):
        lista = []
        for item in self.get_vagas_usadas_em_migracao().values('candidatovaga__oferta_vaga__lista__descricao').annotate(dcount=Count('pk')):
            lista.append('{} : {}'.format(item['candidatovaga__oferta_vaga__lista__descricao'], item['dcount']))
        return '\n'.join(lista)

    def get_vagas_ocupadas(self):
        return self.vaga_set.filter(candidatovaga__situacao=CandidatoVaga.MATRICULADO)

    def is_cota_etnica(self):
        return self.lista.forma_ingresso and self.lista.forma_ingresso.programa_vaga_etinico

    def is_cota_quilombola(self):
        return self.lista.forma_ingresso and self.lista.forma_ingresso.programa_vaga_quilombola

    def is_cota_baixa_renda(self):
        return self.lista.forma_ingresso and self.lista.forma_ingresso.programa_vaga_social

    def is_cota_escola_publica(self):
        return self.lista.forma_ingresso and self.lista.forma_ingresso.programa_vaga_escola_publica

    def is_cota_deficiencia(self):
        return self.lista.forma_ingresso and self.lista.forma_ingresso.programa_vaga_pessoa_deficiencia

    def is_lista_fechada(self):
        return not self.candidatovaga_set.filter(situacao__isnull=True).exists()

    def is_lista_aprovado_fechada(self):
        return not self.candidatovaga_set.filter(situacao__isnull=True, aprovado=True).exists()

    def get_percentual_matriculados(self):
        if self.qtd:
            percentual = int(self.get_candidatos_matriculados().count() * 100 / self.qtd)
            return percentual > 100 and 100 or percentual
        else:
            return 100

    def get_total_vagas_ocupadas(self):
        if self.oferta_vaga_curso.curso_campus.matrizcurso_set.filter(matriz__estrutura__proitec=True).exists():
            return self.get_candidatos_convocados().count()
        else:
            return self.vaga_set.filter(candidatovaga__situacao=CandidatoVaga.MATRICULADO).count()

    def get_percentual_ocupacao(self):
        total_vagas = self.qtd
        total_vagas_ocupadas = self.get_total_vagas_ocupadas()
        return total_vagas and int(total_vagas_ocupadas * 100 / total_vagas) or 0

    def get_candidatos_processados(self):
        return self.get_candidatos_convocados().filter(situacao__isnull=False)

    def get_percentual_convocados_matriculados(self):
        total_convocados = self.get_candidatos_convocados().count()
        total_convocados_processados = self.get_candidatos_processados().count()
        return total_convocados and int(total_convocados_processados * 100 / total_convocados) or 0

    def get_proximo_candidato_apto_convocacao(self, numero_chamada):
        qs = self.get_candidatos_classificados().filter(convocacao__isnull=True, situacao__isnull=True)
        if numero_chamada == 1:
            qs = qs.filter(aprovado=True)
        return qs.order_by('classificacao').first()

    def convocar_proximo_candidato(self, vaga, numero_chamada):
        CandidatoVaga.objects.filter(vaga=vaga).update(vaga=None)
        candidato_vaga = self.get_proximo_candidato_apto_convocacao(numero_chamada)
        if candidato_vaga:
            candidato_vaga.convocacao = numero_chamada
            candidato_vaga.vaga = vaga
            candidato_vaga.save()
            candidato_vaga.get_participacoes_em_outras_listas().update(situacao=CandidatoVaga.JA_CONVOCADO)
            return candidato_vaga
        return None

    def get_vagas_disponiveis(self):
        vagas = []
        situacoes = (
            CandidatoVaga.INAPTO,
            CandidatoVaga.AUSENTE,
            CandidatoVaga.MATRICULA_CANCELADA,
            CandidatoVaga.TRANSFERIDO,
            CandidatoVaga.JA_MATRICULADO,
            CandidatoVaga.EVADIDO,
            CandidatoVaga.JA_CONVOCADO,
        )
        for qs in self.vaga_set.filter(ofertavaga__isnull=True), self.vagas_recebidas_polos:
            vagas.extend(list(qs.filter(candidatovaga__isnull=True) | qs.filter(candidatovaga__situacao__in=situacoes)))
        return vagas

    def get_qtd_vagas_extras(self):
        return sum(self.criacaovagaremanescente_set.values_list('qtd', flat=True))

    def realizar_nova_chamada(self, numero_chamada):
        convocados = []
        if numero_chamada == 1 and not self.vaga_set.exists():
            for _i in range(self.qtd):
                Vaga.objects.create(oferta_vaga=self)
        for vaga in self.get_vagas_disponiveis():
            convocado = self.convocar_proximo_candidato(vaga, numero_chamada)
            if convocado:
                convocados.append(convocado)
        return convocados


class Vaga(models.ModelPlus):
    oferta_vaga = models.ForeignKeyPlus(OfertaVaga)

    class Meta:
        verbose_name = 'Vaga'
        verbose_name_plural = 'Vagas'

    def __str__(self):
        return self.oferta_vaga.lista.descricao


class Candidato(models.ModelPlus):
    APROVACAO_BANCA_CHOICES = [
        (None, 'Aguardando Avaliação'),
        (True, 'Aprovado'),
        (False, 'Reprovado'),
    ]

    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital')
    inscricao = models.CharField(max_length=255, verbose_name='Nº da Inscrição')
    cpf = models.CharField(max_length=250, verbose_name='CPF')
    nome = models.CharField(max_length=255, verbose_name='Nome')
    email = models.CharField(max_length=255, verbose_name='E-mail', null=True)
    telefone = models.CharField(max_length=255, verbose_name='Telefone', null=True)
    curso_campus = models.ForeignKeyPlus(CursoCampus, verbose_name='Curso', null=True)
    turno = models.ForeignKeyPlus('edu.Turno', verbose_name='Turno', null=True, on_delete=models.CASCADE)
    campus_polo = models.CharFieldPlus(verbose_name='Campus/Polo', default='')
    aprovado_heteroidentificacao = models.BooleanField(
        verbose_name='Aprovado em Banca de Heteroidentificação', null=True, blank=True, choices=APROVACAO_BANCA_CHOICES
    )
    aprovado_quilombola = models.BooleanField(verbose_name='Aprovado em Banca de Quilombola', null=True, blank=True, choices=APROVACAO_BANCA_CHOICES)
    aprovado_escola_publica = models.BooleanField(
        verbose_name='Aprovado em Banca de Escola Pública', null=True, blank=True, choices=APROVACAO_BANCA_CHOICES
    )
    aprovado_baixa_renda = models.BooleanField(
        verbose_name='Aprovado em Banca de Baixa Renda', null=True, blank=True, choices=APROVACAO_BANCA_CHOICES
    )
    aprovado_deficiencia = models.BooleanField(
        verbose_name='Aprovado em Banca de Deficientes', null=True, blank=True, choices=APROVACAO_BANCA_CHOICES
    )
    pontuacao = models.DecimalFieldPlus(verbose_name='Pontuação', null=True)

    objects = models.Manager()
    locals = FiltroUnidadeOrganizacionalManager('edital__ofertavaga__curso_campus__diretoria__setor__uo')

    class Meta:
        verbose_name_plural = 'Candidato'
        verbose_name = 'Candidatos'

    def __str__(self):
        return f'{self.inscricao} {self.nome} ({self.cpf})'

    def get_lista_candidato(self):
        return ', '.join(f'{candidatovaga.oferta_vaga.lista}' for candidatovaga in self.candidatovaga_set.all())

    get_lista_candidato.short_description = 'Lista'

    def get_absolute_url(self):
        return f'/processo_seletivo/candidato/{self.pk}/'

    @property
    def get_aprovado_heteroidentificacao_display(self):
        if self.aprovado_heteroidentificacao is not None:
            return 'Aprovado' if self.aprovado_heteroidentificacao else 'Reprovado'
        return 'Sem Avaliação'

    @property
    def get_aprovado_quilombola_display(self):
        if self.aprovado_quilombola is not None:
            return 'Aprovado' if self.aprovado_quilombola else 'Reprovado'
        return 'Sem Avaliação'

    @property
    def get_aprovado_baixa_renda_display(self):
        if self.aprovado_baixa_renda is not None:
            return 'Aprovado' if self.aprovado_baixa_renda else 'Reprovado'
        return 'Sem Avaliação'

    @property
    def get_aprovado_escola_publica_display(self):
        if self.aprovado_escola_publica is not None:
            return 'Aprovado' if self.aprovado_escola_publica else 'Reprovado'
        return 'Sem Avaliação'

    @property
    def get_aprovado_deficiencia_display(self):
        if self.aprovado_deficiencia is not None:
            return 'Aprovado' if self.aprovado_deficiencia else 'Reprovado'
        return 'Sem Avaliação'


class CandidatoVaga(models.ModelPlus):
    MATRICULADO = '1'
    AUSENTE = '2'
    INAPTO = '3'
    JA_MATRICULADO = '4'
    MATRICULA_CANCELADA = '5'
    EVADIDO = '6'
    JA_CONVOCADO = '7'
    TRANSFERIDO = '8'

    SITUACAO_CHOICES = [
        [MATRICULADO, 'Matriculado'],
        [AUSENTE, 'Ausente'],
        [INAPTO, 'Inapto'],
        [JA_MATRICULADO, 'Já Matriculado'],
        [MATRICULA_CANCELADA, 'Matrícula Cancelada'],
        [EVADIDO, 'Evadido'],
        [JA_CONVOCADO, 'Já Convocado'],
        [TRANSFERIDO, 'Transferido'],
    ]

    candidato = models.ForeignKeyPlus(Candidato, verbose_name='Candidato')
    oferta_vaga = models.ForeignKeyPlus(OfertaVaga, verbose_name='Oferta de Vaga')
    vaga = models.ForeignKeyPlus(Vaga, verbose_name='Vaga', null=True)
    classificacao = models.IntegerField('Classificação')
    classificacao_para_divulgacao = models.IntegerField('Classificação para Divulgação', null=True)
    aprovado = models.BooleanField('Aprovado', default=False)
    eliminado = models.BooleanField('Eliminado', default=False)

    situacao = models.CharFieldPlus('Situação', choices=SITUACAO_CHOICES, null=True)
    migracao = models.ForeignKeyPlus(OfertaVaga, verbose_name='Migração', null=True, related_name='migracao_set')

    convocacao = models.IntegerField(verbose_name='Chamada da Convocação', null=True)

    objects = models.Manager()
    locals = FiltroUnidadeOrganizacionalManager('oferta_vaga__curso_campus__diretoria__setor__uo')

    class Meta:
        verbose_name_plural = 'Vaga Concorrida'
        verbose_name = 'Vaga Concorrida'
        ordering = ('classificacao',)

    def __str__(self):
        if self.classificacao:
            classificacao = self.classificacao
            if self.classificacao_para_divulgacao:
                classificacao = self.classificacao_para_divulgacao
            return f'{self.oferta_vaga.lista} - {classificacao}º Lugar ({self.oferta_vaga.oferta_vaga_curso.curso_campus})'
        else:
            return f'{self.oferta_vaga.lista} - Classificação indefinida'

    def pode_realizar_acao(self):
        if self.situacao is None:
            if self.oferta_vaga.qtd_semestre_1 or self.oferta_vaga.qtd_semestre_2:
                ano_letivo, periodo_letivo = self.get_periodo_letivo_apto_matricula()
                return ano_letivo and periodo_letivo
            return True
        return False

    def get_periodo_letivo_apto_matricula(self):
        if not hasattr(self, 'periodo_letivo_apto_matricula'):
            if self.situacao:
                lista = self.aluno_set.values_list('ano_letivo__ano', 'periodo_letivo').first()
                if lista:
                    ano_letivo, periodo_letivo = lista
                else:
                    ano_letivo, periodo_letivo = None, None
            elif self.oferta_vaga.qtd_semestre_1 and self.oferta_vaga.qtd_semestre_2:
                qtd_alunos = self.oferta_vaga.candidatovaga_set.filter(aluno__situacao__ativo=True).count()
                if qtd_alunos >= self.oferta_vaga.qtd_semestre_1:
                    # todos os alunos do primeiro semestre já foram matriculados
                    if self.candidato.edital.semestre == 2:
                        ano_letivo, periodo_letivo = Ano.objects.get_or_create(ano=self.candidato.edital.ano.ano + 1)[0], 1
                    else:
                        ano_letivo, periodo_letivo = self.candidato.edital.ano, self.candidato.edital.semestre + 1
                else:
                    qtd_candidados_anteriores_pendentes = self.oferta_vaga.candidatovaga_set.filter(
                        situacao__isnull=True, classificacao__lt=self.classificacao
                    ).count()
                    # o canditato é do segundo semestre e deve esperar a ocupação das vagas do primeiro semestre
                    if qtd_alunos + qtd_candidados_anteriores_pendentes >= self.oferta_vaga.qtd_semestre_1:
                        ano_letivo, periodo_letivo = None, None
                    else:
                        # o candidato é do primeiro semestre ou ocupará uma vaga livre do primeiro semestre
                        ano_letivo, periodo_letivo = self.candidato.edital.ano, self.candidato.edital.semestre
            elif self.oferta_vaga.qtd_semestre_2:
                # a oferta de vaga é para o segundo semeste apenas
                if self.candidato.edital.semestre == 2:
                    ano_letivo, periodo_letivo = Ano.objects.get_or_create(ano=self.candidato.edital.ano.ano + 1)[0], 1
                else:
                    ano_letivo, periodo_letivo = self.candidato.edital.ano, self.candidato.edital.semestre + 1
            else:
                ano_letivo, periodo_letivo = self.candidato.edital.ano, self.candidato.edital.semestre
            self.periodo_letivo_apto_matricula = ano_letivo, periodo_letivo
        return self.periodo_letivo_apto_matricula

    @property
    def campus(self):
        return self.candidato.curso_campus.diretoria.setor.uo

    def is_matriculado(self):
        return Aluno.objects.filter(candidato_vaga__candidato=self.candidato, curso_campus=self.oferta_vaga.oferta_vaga_curso.curso_campus).exists()

    def get_aluno(self):
        return Aluno.objects.filter(candidato_vaga__candidato=self.candidato).first()

    def get_situacao_matricula(self):
        qs_aluno = Aluno.objects.filter(candidato_vaga=self)
        return qs_aluno.exists() and qs_aluno[0].situacao or ''

    def utilizou_vaga_migrada(self):
        return self.vaga_id and self.vaga.oferta_vaga != self.oferta_vaga

    def get_participacoes_em_outras_listas(self):
        return CandidatoVaga.objects.filter(candidato=self.candidato, oferta_vaga__oferta_vaga_curso=self.oferta_vaga.oferta_vaga_curso).exclude(
            pk=self.pk
        )

    def get_status(self):
        status = {'1': 'success', '2': 'alert', '3': 'error', '4': 'info', '5': 'fechado', '6': 'fechado', '7': 'info', None: 'info'}
        descricao = self.get_situacao_display()
        data_matricula = ''
        if self.situacao in (CandidatoVaga.JA_CONVOCADO, CandidatoVaga.JA_MATRICULADO):
            candidato_vaga = self.get_participacoes_em_outras_listas().exclude(situacao=self.situacao).first()
            if candidato_vaga:
                descricao = f'{descricao} - {candidato_vaga.oferta_vaga.lista}'
        if self.situacao == CandidatoVaga.MATRICULADO:
            data_matricula = Aluno.objects.filter(candidato_vaga__candidato=self.candidato).values_list('data_matricula', flat=True).first()
            data_matricula = data_matricula and data_matricula.strftime('%d/%m/%Y as %H:%M') or ''
        return descricao, status.get(self.situacao), data_matricula

    def registrar_matricula(self):
        self.situacao = CandidatoVaga.MATRICULADO
        self.save()
        self.get_participacoes_em_outras_listas().filter(situacao__isnull=True).update(situacao=CandidatoVaga.JA_MATRICULADO)
        matricula_candidato_sinal.send(sender=CandidatoVaga, candidato_vaga_id=self.pk)

    def registrar_ausencia(self):
        self.situacao = CandidatoVaga.AUSENTE
        self.save()
        qs = self.get_participacoes_em_outras_listas()
        qs.filter(situacao=CandidatoVaga.JA_CONVOCADO).update(situacao=None)
        qs = qs.filter(situacao__isnull=True)
        qs.update(situacao=CandidatoVaga.AUSENTE)
        ausencia_candidato_sinal.send(sender=CandidatoVaga, candidato_vaga_id=self.pk, desfazer=False)

    def registrar_inaptidao(
        self,
        devido_heteroidentificacao=False,
        devido_quilombola=False,
        devido_baixa_renda=False,
        devido_escola_publica=False,
        devido_deficiencia=False,
    ):
        self.situacao = CandidatoVaga.INAPTO
        self.save()
        qs = self.get_participacoes_em_outras_listas()
        qs.filter(situacao=CandidatoVaga.JA_CONVOCADO).update(situacao=None)
        qs = qs.filter(situacao__isnull=True)
        if devido_heteroidentificacao:
            if self.candidato.aprovado_heteroidentificacao is None:
                self.candidato.aprovado_heteroidentificacao = False
                self.candidato.save()
            qs = qs.filter(oferta_vaga__lista__forma_ingresso__programa_vaga_etinico=True)
        if devido_quilombola:
            if self.candidato.aprovado_quilombola is None:
                self.candidato.aprovado_quilombola = False
                self.candidato.save()
            qs = qs.filter(oferta_vaga__lista__forma_ingresso__programa_vaga_quilombola=True)
        if devido_baixa_renda:
            if self.candidato.aprovado_baixa_renda is None:
                self.candidato.aprovado_baixa_renda = False
                self.candidato.save()
            qs = qs.filter(oferta_vaga__lista__forma_ingresso__programa_vaga_social=True)
        if devido_escola_publica:
            if self.candidato.aprovado_escola_publica is None:
                self.candidato.aprovado_escola_publica = False
                self.candidato.save()
            qs = qs.filter(oferta_vaga__lista__forma_ingresso__programa_vaga_escola_publica=True)
        if devido_deficiencia:
            if self.candidato.aprovado_deficiencia is None:
                self.candidato.aprovado_deficiencia = False
                self.candidato.save()
            qs = qs.filter(oferta_vaga__lista__forma_ingresso__programa_vaga_pessoa_deficiencia=True)
        qs.update(situacao=CandidatoVaga.INAPTO)
        inaptidao_candidato_sinal.send(sender=CandidatoVaga, candidato_vaga_id=self.pk, desfazer=False)

    # Todo: Verificar com Agugusto - Método criado para permitir retornar as solicitações indeferidas do catalogo digital para o status EM_ANALISE
    def retornar_para_apto(self):
        if self.situacao == CandidatoVaga.MATRICULADO:
            matricula_candidato_sinal.send(sender=CandidatoVaga, candidato_vaga_id=self.pk, desfazer=True)
        if self.situacao == CandidatoVaga.AUSENTE:
            ausencia_candidato_sinal.send(sender=CandidatoVaga, candidato_vaga_id=self.pk, desfazer=True)
        if self.situacao == CandidatoVaga.INAPTO:
            inaptidao_candidato_sinal.send(sender=CandidatoVaga, candidato_vaga_id=self.pk, desfazer=True)
        self.situacao = None
        self.save()
        self.get_participacoes_em_outras_listas().update(situacao=CandidatoVaga.JA_CONVOCADO)

    def simular_matricula(self):
        aluno = Aluno.objects.filter(candidato_vaga__isnull=True, situacao_id=1)[0]
        aluno.candidato_vaga = self
        aluno.ano_letivo, aluno.periodo_letivo = self.get_periodo_letivo_apto_matricula()
        aluno.save()
        self.situacao = CandidatoVaga.MATRICULADO
        self.save()
        self.get_participacoes_em_outras_listas().filter(situacao__isnull=True).update(situacao=CandidatoVaga.JA_MATRICULADO)

    def desfazer_procedimento(self):
        if self.vaga is None and self.convocacao == self.oferta_vaga.oferta_vaga_curso.get_numero_ultima_chamada():
            vagas = self.oferta_vaga.get_vagas_disponiveis()
            self.vaga = vagas and vagas[0] or None
        for aluno in Aluno.objects.filter(candidato_vaga=self):
            if aluno.pode_ser_excluido():
                try:
                    aluno.delete()
                except Exception:
                    aluno.candidato_vaga = None
                    aluno.save()
            else:
                aluno.candidato_vaga = None
                aluno.save()
        for candidato_vaga in self.get_participacoes_em_outras_listas():
            candidato_vaga.situacao = None
            if candidato_vaga.convocacao and candidato_vaga.oferta_vaga.candidatovaga_set.filter(convocacao__gt=candidato_vaga.convocacao).exists():
                candidato_vaga.convocacao = None
            for aluno in Aluno.objects.filter(candidato_vaga=candidato_vaga):
                if aluno.pode_ser_excluido():
                    try:
                        aluno.delete()
                    except Exception:
                        aluno.candidato_vaga = None
                        aluno.save()
                else:
                    aluno.candidato_vaga = None
                    aluno.save()
            candidato_vaga.save()
        self.retornar_para_apto()

    def get_lista_matriculada(self):
        if self.situacao == CandidatoVaga.MATRICULADO:
            if self.migracao:
                return self.migracao.lista
            else:
                return self.oferta_vaga.lista
        elif self.situacao == CandidatoVaga.JA_MATRICULADO:
            return CandidatoVaga.objects.get(
                candidato=self.candidato, oferta_vaga__curso_campus=self.oferta_vaga.curso_campus, situacao=CandidatoVaga.MATRICULADO
            ).oferta_vaga.lista
        return None

    def get_outra_convocacao(self):
        qs = CandidatoVaga.objects.filter(candidato=self.candidato, oferta_vaga__curso_campus=self.oferta_vaga.curso_campus)
        if self.oferta_vaga.turno:
            qs = qs.filter(oferta_vaga__turno=self.oferta_vaga.turno)
        qs = qs.filter(convocacao__isnull=False).exclude(pk=self.pk)
        return qs.exists() and qs.first() or None

    def get_convocacao_em_lista_menos_restritiva(self):
        if self.oferta_vaga.edital.configuracao_migracao_vagas:
            rotulos_lista = []
            for i in range(1, 16):
                rotulo_lista = getattr(self.oferta_vaga.edital.configuracao_migracao_vagas, f'lista_{i}')
                if rotulo_lista:
                    if rotulo_lista.nome == self.oferta_vaga.lista.descricao:
                        break
                    else:
                        rotulos_lista.append(rotulo_lista)
                else:
                    break
            for rotulo_lista in rotulos_lista:
                qs_oferta_vaga = OfertaVaga.objects.filter(
                    edital=self.oferta_vaga.edital,
                    curso_campus=self.oferta_vaga.curso_campus,
                    turno=self.oferta_vaga.turno,
                    lista__descricao=rotulo_lista.nome,
                )
                if qs_oferta_vaga.exists():
                    oferta_vaga = qs_oferta_vaga[0]
                    for tmp in oferta_vaga.get_candidatos_atualmente_convocados():
                        if tmp.candidato == self.candidato:
                            return tmp
        return None

    @classmethod
    def matricula_online_disponibilidade(cls, cpf, campus=None, niveis_ensino=None):
        now = datetime.datetime.now()
        ret_value = []

        # Tratamento para editais em período de matrícula --------------------------------------------------------------
        periodos_liberacao = EditalPeriodoLiberacao.objects.filter(data_inicio_matricula__lte=now, data_fim_matricula__gte=now)

        if campus is not None:
            periodos_liberacao = periodos_liberacao.filter(uo=campus)

        for periodo_liberacao in periodos_liberacao:
            # Avaliar consulta com e sem exclude
            candidaturas_periodo_matricula = CandidatoVaga.objects.filter(candidato__edital=periodo_liberacao.edital)
            candidaturas_periodo_matricula = candidaturas_periodo_matricula.filter(
                candidato__cpf=cpf, convocacao__isnull=False, situacao__isnull=True
            )

            if niveis_ensino is not None:
                candidaturas_periodo_matricula = candidaturas_periodo_matricula.filter(
                    candidato__curso_campus__modalidade__nivel_ensino_id__in=niveis_ensino
                )

            for cand in candidaturas_periodo_matricula:
                if not cand.is_matriculado() and cand.campus == periodo_liberacao.uo:
                    ret_value.append(
                        {
                            'edital_codigo': cand.candidato.edital.codigo,
                            'edital_id': cand.candidato.edital.id,
                            'candidato_vaga_id': cand.pk,
                            'edital_descricao': cand.candidato.edital.descricao,
                            'modalidade_id': cand.candidato.curso_campus.modalidade.pk,
                            'em_periodo_matricula': True,
                        }
                    )

        # Tratamento para editais fora de período, mas, em período de correção  ----------------------------------------
        periodos_liberacao = EditalPeriodoLiberacao.objects.filter(data_fim_matricula__lt=now, data_limite_avaliacao__gte=now)

        if campus is not None:
            periodos_liberacao = periodos_liberacao.filter(uo=campus)

        for periodo_liberacao in periodos_liberacao:
            # Avaliar consulta com e sem exclude
            candidaturas_periodo_avaliacao = CandidatoVaga.objects.filter(candidato__edital=periodo_liberacao.edital)
            candidaturas_periodo_avaliacao = candidaturas_periodo_avaliacao.filter(
                candidato__cpf=cpf, convocacao__isnull=False, situacao__isnull=True
            )

            if niveis_ensino is not None:
                candidaturas_periodo_avaliacao = candidaturas_periodo_avaliacao.filter(
                    candidato__curso_campus__modalidade__nivel_ensino_id__in=niveis_ensino
                )

            for cand in candidaturas_periodo_avaliacao:
                if not cand.is_matriculado() and cand.campus == periodo_liberacao.uo:
                    ret_value.append(
                        {
                            'edital_codigo': cand.candidato.edital.codigo,
                            'edital_id': cand.candidato.edital.id,
                            'candidato_vaga_id': cand.pk,
                            'edital_descricao': cand.candidato.edital.descricao,
                            'modalidade_id': cand.candidato.curso_campus.modalidade.pk,
                            'em_periodo_matricula': False,
                        }
                    )

        return ret_value

    @classmethod
    def matricula_online_dados_candidato(cls, candidato_vaga_id):
        # Fechar no SGC V2 para testes
        candidato_vaga = CandidatoVaga.objects.get(pk=candidato_vaga_id)
        ws = candidato_vaga.candidato.edital.webservice

        try:
            ret_values = None

            msg_erro = 'Erro ao tentar obter dados do candidato junto ao webservices do SGC.'
            ret_values = ws.candidato(
                codigo_edital=candidato_vaga.candidato.edital.codigo, codigo_candidato=candidato_vaga.candidato.inscricao, compactado=ws.is_zipped
            )

            msg_erro = 'Erro ao processar resposta obtida do webservices do SGC.'
            soap = BeautifulSoup(ret_values, 'xml')
            # Adicionando dados das listas
            lista = soap.new_tag('lista')
            lista_codigo = soap.new_tag('codigo')
            lista_codigo.append(f'{candidato_vaga.oferta_vaga.lista.codigo}')
            lista_nome = soap.new_tag('nome')
            lista_nome.append(f'{candidato_vaga.oferta_vaga.lista.descricao}')
            # Configuração das listas
            lista_etinia = soap.new_tag('criterio_etnico')
            lista_pessoa_deficiencia = soap.new_tag('criterio_deficiencia')
            lista_escola_publica = soap.new_tag('criterio_escola_publica')
            lista_social = soap.new_tag('criterio_social')
            lista_outros = soap.new_tag('criterio_outros')

            if candidato_vaga.oferta_vaga.lista.forma_ingresso:
                lista_etinia.append(f'{candidato_vaga.oferta_vaga.lista.forma_ingresso.programa_vaga_etinico}')
                lista_pessoa_deficiencia.append(f'{candidato_vaga.oferta_vaga.lista.forma_ingresso.programa_vaga_pessoa_deficiencia}')
                lista_escola_publica.append(f'{candidato_vaga.oferta_vaga.lista.forma_ingresso.programa_vaga_escola_publica}')
                lista_social.append(f'{candidato_vaga.oferta_vaga.lista.forma_ingresso.programa_vaga_social}')
                lista_outros.append(f'{candidato_vaga.oferta_vaga.lista.forma_ingresso.programa_vaga_outros}')

            lista.append(lista_codigo)
            lista.append(lista_nome)
            lista.append(lista_etinia)
            lista.append(lista_pessoa_deficiencia)
            lista.append(lista_escola_publica)
            lista.append(lista_social)
            lista.append(lista_outros)

            soap.find('inscricao').append(lista)
            return str(soap.contents[0])
        except Exception as e:
            with sentry_sdk.push_scope() as scope:
                scope.set_extra('msg_erro', msg_erro)
                scope.set_extra('ret_values', ret_values)
                scope.set_extra('candidato_vaga_id', candidato_vaga.id)
                scope.set_extra('candidato_vaga.candidato.cpf', candidato_vaga.candidato.cpf)
                scope.set_extra('candidato_vaga.candidato.nome', candidato_vaga.candidato.nome)
                scope.set_extra('candidato_vaga.candidato.inscricao', candidato_vaga.candidato.inscricao)
                scope.set_extra('candidato_vaga.candidato.edital', candidato_vaga.candidato.edital)
                scope.set_extra('candidato_vaga.candidato.edital.codigo', candidato_vaga.candidato.edital.codigo)
                scope.set_extra('candidato_vaga.candidato.edital.webservice', candidato_vaga.candidato.edital.webservice)
                sentry_sdk.capture_exception(e)
            traceback.print_exc()
            raise Exception(msg_erro)

    def is_inconsistente(self):
        result = False
        if CandidatoVaga.objects.filter(
            id=self.id, convocacao__isnull=False, vaga__isnull=True, eliminado=False, situacao__isnull=True, oferta_vaga_id=self.oferta_vaga.id
        ).exists():
            result = len(self.oferta_vaga.get_vagas_disponiveis()) > 0
        return result

    def vincular_vaga(self):
        if self.is_inconsistente():
            vaga = self.oferta_vaga.get_vagas_disponiveis()[0]
            self.vaga = vaga
            self.save()

    def is_reprovado_banca(self):
        reprovado = False
        forma_ingresso = self.oferta_vaga.lista.forma_ingresso
        if forma_ingresso:
            if forma_ingresso.programa_vaga_etinico:
                reprovado = reprovado or self.candidato.aprovado_heteroidentificacao is False
            if forma_ingresso.programa_vaga_quilombola:
                reprovado = reprovado or self.candidato.aprovado_quilombola is False
            if forma_ingresso.programa_vaga_pessoa_deficiencia:
                reprovado = reprovado or self.candidato.aprovado_deficiencia is False
            if forma_ingresso.programa_vaga_escola_publica:
                reprovado = reprovado or self.candidato.aprovado_escola_publica is False
            if forma_ingresso.programa_vaga_social:
                reprovado = reprovado or self.candidato.aprovado_baixa_renda is False
        return reprovado

    def get_banca_avaliacao(self):
        lista = []
        tipo_banca = None
        situacao = None
        forma_ingresso = self.oferta_vaga.lista.forma_ingresso
        if forma_ingresso:
            if forma_ingresso.programa_vaga_etinico:
                tipo_banca = 'Heteroidentificação'
                situacao = self.candidato.get_aprovado_heteroidentificacao_display
                lista.append([tipo_banca, situacao, 'gray'])
            if forma_ingresso.programa_vaga_quilombola:
                tipo_banca = 'Quilombola'
                situacao = self.candidato.get_aprovado_quilombola_display
                lista.append([tipo_banca, situacao, 'gray'])
            if forma_ingresso.programa_vaga_pessoa_deficiencia:
                tipo_banca = 'Deficiência'
                situacao = self.candidato.get_aprovado_deficiencia_display
                lista.append([tipo_banca, situacao, 'gray'])
            if forma_ingresso.programa_vaga_escola_publica:
                tipo_banca = 'Escola Pública'
                situacao = self.candidato.get_aprovado_escola_publica_display
                lista.append([tipo_banca, situacao, 'gray'])
            if forma_ingresso.programa_vaga_social:
                tipo_banca = 'Baixa Renda'
                situacao = self.candidato.get_aprovado_baixa_renda_display
                lista.append([tipo_banca, situacao, 'gray'])
            for item in lista:
                if item[1] == 'Aprovado':
                    item[2] = 'green'
                elif item[1] == 'Reprovado':
                    item[2] = 'red'
        return lista


class NotificacaoMatricula(models.ModelPlus):
    token = models.CharFieldPlus(verbose_name='Token')
    periodo_liberacao = models.ForeignKeyPlus(EditalPeriodoLiberacao)
    candidato_vaga = models.ForeignKeyPlus(CandidatoVaga)
    data_envio = models.DateTimeFieldPlus('Data do Envio', auto_now_add=True)
    email = models.EmailField(verbose_name='E-mail', null=True, blank=True)
    data_leitura = models.DateTimeFieldPlus('Data da Leitura', null=True, blank=True)

    class Meta:
        verbose_name = 'Período de Liberação Matrícula'
        verbose_name_plural = 'Períodos de Liberação Matrícula'

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid4().hex
        super().save(*args, **kwargs)


class WebService(LogModel):
    descricao = models.CharFieldPlus('Descrição')
    url_editais = models.CharFieldPlus(
        'Url Editais', help_text='Endereço do webservice para listagem de editais. Ex: http://ingresso.ifrn.edu.br/ws/editais/'
    )
    url_edital = models.CharFieldPlus(
        'Url Edital',
        help_text='Endereço do webservice para importação de edital. Parâmetro: código do edital. Ex: http://ingresso.ifrn.edu.br/ws/edital/{}/',
    )
    url_candidato = models.CharFieldPlus(
        'Url Candidato',
        help_text='Endereço do webservice para importação de candidato. Parâmetros: código do edital e código do candidato. Ex: http://ingresso.ifrn.edu.br/ws/candidato/{}/{}/',
    )
    url_caracterizacoes = models.CharFieldPlus(
        'Url Caracterizações',
        help_text='Endereço do webservice para importação de todas as caracterizações socio-econômicas dos candidatos. Parâmetro: código do edital. Ex: http://ingresso.ifrn.edu.br/ws/caracterizacoes/{}/',
        null=True,
    )

    token = models.CharFieldPlus(
        'Token de Autorização', help_text='Token passado no cabeçalho da requisição (Authorization: XXXXX)', null=True, blank=True
    )
    is_zipped = models.BooleanField('É compactado', default=False)

    class Meta:
        verbose_name = 'Web Service'
        verbose_name_plural = 'Web Services'

    def _executar(self, url, zipped=True):
        headers = {'Authorization': 'Token {}'.format(self.token or '')}
        response = requests.get(url, headers=headers, timeout=settings.REQUESTS_TIMEOUT)

        try:
            response.raise_for_status()
        except RequestException as exc:
            try:
                body_preview = (response.text or '')[:500]
            except Exception:  # pragma: no cover
                body_preview = (response.content or b'')[:500].decode('utf-8', errors='replace')
            raise Exception(f'Erro HTTP {response.status_code} ao consultar {url}. Retorno: {body_preview}') from exc

        if self.is_zipped and zipped:
            try:
                return zlib.decompress(response.content).decode('utf-8')
            except zlib.error as exc:
                body_preview = (response.content or b'')[:200].decode('utf-8', errors='replace')
                raise Exception(f'Retorno compactado inválido ao consultar {url}. Início do retorno: {body_preview}') from exc

        if response.encoding == 'ISO-8859-1':
            return response.text.encode('ISO-8859-1').decode('utf-8')

        return response.text

    def editais(self):
        if self.url_editais.startswith('file://'):
            with open(join(settings.BASE_DIR, self.url_editais.replace('file://', ''))) as f:
                content = f.read()
            return content
        else:
            return self._executar(self.url_editais, False)

    def edital(self, codigo_edital):
        if self.url_edital.startswith('file://'):
            with open(join(settings.BASE_DIR, self.url_edital.replace('file://', ''))) as f:
                content = f.read()
            return content
        else:
            url = self.url_edital.format(codigo_edital)
            return self._executar(url)

    def edital_bruto(self, codigo_edital):
        """Consulta o endpoint do edital na variante /bruta/, usada por alguns serviços para expor
        informações completas (ex.: aprovações de bancas).
        """
        if self.url_edital.startswith('file://'):
            # Mantém o comportamento anterior quando usa arquivo local
            with open(join(settings.BASE_DIR, self.url_edital.replace('file://', ''))) as f:
                return f.read()

        url = self.url_edital.format(codigo_edital)
        if not url.endswith('/'):
            url = url + '/'
        if not url.endswith('/bruta/'):
            url = url + 'bruta/'

        try:
            return self._executar(url)
        except Exception:
            # Alguns serviços não expõem a variante /bruta/.
            return self.edital(codigo_edital)

    def candidato(self, codigo_edital, codigo_candidato, compactado=False):
        if self.url_candidato.startswith('file://'):
            with open(join(settings.BASE_DIR, self.url_candidato.replace('file://', '').format(codigo_edital, codigo_candidato))) as f:
                content = f.read()
            return content
        else:
            url = self.url_candidato.format(codigo_edital, codigo_candidato)
            return self._executar(url, zipped=compactado)

    def caracterizacoes(self, codigo_edital):
        if self.url_caracterizacoes and self.url_caracterizacoes.startswith('file://'):
            with open(join(settings.BASE_DIR, self.url_caracterizacoes.replace('file://', ''))) as f:
                content = f.read()
            return content
        else:
            url = self.url_caracterizacoes.format(codigo_edital)
            return self._executar(url, zipped=True)


class TipoEditalAdesao(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=255, unique=True, blank=False, null=False)

    class Meta:
        verbose_name = 'Tipo do Edital de Adesão'
        verbose_name_plural = 'Tipos de Edital de Adesão'

    def __str__(self):
        return f'{self.nome}'


class EditalAdesao(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255)
    descricao = models.TextField('Descrição', blank=True)
    tipo = models.ForeignKeyPlus(TipoEditalAdesao)
    ano_edital = models.PositiveIntegerField('Ano do Edital', help_text='Ano do Edital', null=True)
    numero_edital = models.PositiveIntegerField('Número do Edital', help_text='Numeração do Edital', null=True)

    data_inicio_adesao = models.DateTimeFieldPlus('Data de início da adesão', null=False, blank=False)
    data_limite_adesao = models.DateTimeFieldPlus(
        'Data limite para adesão', help_text='Data limite para adesão ao edital pelos campi', null=False, blank=False
    )
    criado_por = models.ForeignKeyPlus(
        'comum.User', related_name='edital_adesao_criado_por', null=False, blank=False, editable=False, on_delete=models.CASCADE
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Edital de Adesão'
        verbose_name_plural = 'Editais de Adesão'
        unique_together = ('nome', 'numero_edital', 'ano_edital')

    def __str__(self):
        return f'{self.nome} {self.numero_edital}/{self.ano_edital}'


class EditalAdesaoCampus(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255)
    edital_regulador = models.ForeignKeyPlus(EditalAdesao)
    numero_edital = models.PositiveIntegerField('Número do Edital', help_text='Numeração do Edital do campus', null=True)
    ano_edital = models.PositiveIntegerField('Ano do Edital', help_text='Ano do Edital do campus', null=True)
    data_inicio_inscricoes = models.DateTimeFieldPlus('Data da inscrição', null=False, blank=False)
    data_encerramento_inscricoes = models.DateTimeFieldPlus(
        'Data de encerramento', help_text='Data limite para encerramento das inscrições', null=False, blank=False
    )
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, related_name='edital_adesao_campus_campus', null=False, blank=False)
    responsavel = models.ForeignKeyPlus(
        'comum.User', related_name='edital_adesao_campus_responsavel_por', null=False, blank=False, editable=False, on_delete=models.CASCADE
    )
    idade_minima = models.BooleanField(default=False)
    data_aplicacao_prova = models.DateTimeFieldPlus(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('edital_regulador', 'campus')
        verbose_name = 'Edital de Adesão Campus'
        verbose_name_plural = 'Editais de Adesão Campus'
        permissions = (
            ('pode_ver_todos_editais', 'Pode ver todos os editais de adesão'),
            ('pode_ver_edital_campus', 'pode ver edital os editais de adesão do campus'),
        )

    def __str__(self):
        return f'{self.nome} {self.numero_edital}/{self.ano_edital}-{self.campus}'

    @classmethod
    def editais_abertos(cls, user):
        now = datetime.datetime.now()
        return EditalAdesaoCampus.objects.filter(data_inicio_inscricoes__lte=now, data_encerramento_inscricoes__gte=now, campus=get_uo(user))


class InscricaoFiscal(models.ModelPlus):
    TIPO_ALUNO = 'ALUNO'
    TIPO_SERVIDOR = 'SERVIDOR'
    TIPO_CHOICES = [[TIPO_ALUNO, 'Aluno'], [TIPO_SERVIDOR, 'Servidor']]

    TIPO_CONTA_CORRENTE = 'CORRENTE'
    TIPO_CONTA_POUPANCA = 'POUPANCA'
    TIPO_CONTA_CHOICES = [[TIPO_CONTA_CORRENTE, 'Conta Corrente'], [TIPO_CONTA_POUPANCA, 'Conta Poupança']]

    edital = models.ForeignKeyPlus(EditalAdesaoCampus)
    fiscal = models.ForeignKeyPlus('comum.Vinculo', related_name='%(app_label)s_%(class)s_fiscal', verbose_name='Fiscal', on_delete=models.CASCADE)

    tipo = models.CharField(verbose_name='Vínculo', max_length=50, choices=TIPO_CHOICES)
    matricula = models.CharField('Matrícula', max_length=50)
    telefones = models.CharField(max_length=255)
    banco = models.CharField(max_length=50, null=True)
    numero_agencia = models.CharField('Número da Agência', max_length=50, null=True)
    tipo_conta = models.CharField(max_length=50, verbose_name='Tipo da Conta', choices=TIPO_CONTA_CHOICES, null=True)
    numero_conta = models.CharField('Número da Conta', max_length=50, null=True)
    operacao = models.CharField('Operação', max_length=50, null=True, blank=True)
    pis_pasep = models.CharField('PIS/PASEP', max_length=20, null=True, blank=True)
    outros_processos = models.IntegerField('Já Participou de outros processos? Quantos?', help_text='Ex.: 0', default=0)
    aceito_termos = models.BooleanField(
        verbose_name='Termo de Compromisso',
        help_text='Declaro junto à Comissão do Concurso Público o meu interesse em trabalhar como fiscal, bem como a veracidade dos dados acima.',
        default=False,
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Inscrição para Fiscal'
        verbose_name_plural = 'Inscrições para Fiscal'

    def set_user(self, user):
        vinculo = user.get_vinculo()
        if vinculo.eh_servidor():
            self.tipo = self.TIPO_SERVIDOR
            self.matricula = vinculo.relacionamento.matricula
            self.fiscal = vinculo
            return True
        elif vinculo.eh_aluno():
            self.tipo = self.TIPO_ALUNO
            self.matricula = vinculo.relacionamento.matricula
            self.fiscal = vinculo
            return True
        return False

    def idade_no_dia_prova(self):
        if self.edital.idade_minima and self.edital.data_aplicacao_prova:
            pessoa_fisica = self.fiscal.pessoa.pessoafisica
            return years_between(pessoa_fisica.nascimento_data, self.edital.data_aplicacao_prova)
        return '-'

    @classmethod
    def pode_efetuar_inscricao(cls, user, edital):
        if datetime.datetime.now() > edital.data_encerramento_inscricoes:
            return False, 'o prazo de inscrições para o edital corrente expirou.'

        pessoa_fisica = user.get_profile()
        vinculo = user.get_vinculo()

        if InscricaoFiscal.objects.filter(fiscal__pessoa__pessoafisica__cpf=pessoa_fisica.cpf, edital=edital).exists():
            return False, f'o CPF {pessoa_fisica.cpf} já possui uma inscrição com {vinculo}.'

        if edital.campus != get_uo(user):
            return False, 'o edital não permite inscrições vínculadas ao seu campus.'

        matricula_valida = (
            Servidor.objects.efetivos().filter(pessoa_fisica__pk=pessoa_fisica.pk, ativo=True).exists()
            or Aluno.objects.filter(pessoa_fisica__pk=pessoa_fisica.pk, situacao__ativo=True).exists()
        )
        if not matricula_valida:
            return matricula_valida, 'matrícula inválida.'

        if edital.idade_minima and edital.data_aplicacao_prova:
            if pessoa_fisica.nascimento_data is None:
                return False, 'sua data de nascimento não foi cadastrada.'
            possui_idade_minima = years_between(pessoa_fisica.nascimento_data, edital.data_aplicacao_prova) >= 18
            if not possui_idade_minima:
                return False, 'você não preenche o requisito de idade mínima previsto no edital.'

        return True, 'Inscrição realizada com sucesso.'


class RotuloLista(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'descricao']
    nome = models.TextField(verbose_name='Nome')
    descricao = models.TextField(verbose_name='Descrição')

    class Meta:
        verbose_name = 'Rótulo de Lista'
        verbose_name_plural = 'Rótulos de Lista'

    def __str__(self):
        return self.nome


class ConfiguracaoMigracaoVaga(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    is_sisu = models.BooleanField(default=False, verbose_name='SISU?')
    listas = models.ManyToManyFieldPlus(RotuloLista, verbose_name='Listas')
    ativo = models.BooleanField(default=True)

    lista_1 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 1', null=True, blank=True, related_name='p1')
    lista_2 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 2', null=True, blank=True, related_name='p2')
    lista_3 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 3', null=True, blank=True, related_name='p3')
    lista_4 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 4', null=True, blank=True, related_name='p4')
    lista_5 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 5', null=True, blank=True, related_name='p5')
    lista_6 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 6', null=True, blank=True, related_name='p6')
    lista_7 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 7', null=True, blank=True, related_name='p7')
    lista_8 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 8', null=True, blank=True, related_name='p8')
    lista_9 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 9', null=True, blank=True, related_name='p9')
    lista_10 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 10', null=True, blank=True, related_name='p10')
    lista_11 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 11', null=True, blank=True, related_name='p11')
    lista_12 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 12', null=True, blank=True, related_name='p12')
    lista_13 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 13', null=True, blank=True, related_name='p13')
    lista_14 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 14', null=True, blank=True, related_name='p14')
    lista_15 = models.ForeignKeyPlus(RotuloLista, verbose_name='Prioridade 15', null=True, blank=True, related_name='p15')

    class Meta:
        verbose_name = 'Configuração de Migração de Vaga'
        verbose_name_plural = 'Configurações de Migração de Vagas'

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/processo_seletivo/configuracaomigracaovaga/{self.pk}/'

    def get_nomes_listas_ordenadas_por_restricao(self):
        nomes = []
        for i in range(1, 16):
            rotulo_lista = getattr(self, f'lista_{i}')
            if rotulo_lista:
                nomes.append(rotulo_lista.nome)
        return nomes

    def get_precedencias(self, apenas_descricao=False):
        precedencias = []
        qs = PrecedenciaMigracao.objects.filter(configuracao=self)
        for nome_lista in self.get_nomes_listas_ordenadas_por_restricao():
            origem = self.listas.filter(nome=nome_lista).first()
            destinos = []
            if origem:
                for rotulo_pk in qs.filter(origem=origem).values_list('destino', flat=True).order_by('precedencia'):
                    rotulo_lista = RotuloLista.objects.get(pk=rotulo_pk)
                    destinos.append(apenas_descricao and rotulo_lista.nome or rotulo_lista)
                precedencias.append((apenas_descricao and nome_lista or origem, destinos))
        return precedencias


class PrecedenciaMigracao(models.ModelPlus):
    configuracao = models.ForeignKeyPlus(ConfiguracaoMigracaoVaga, verbose_name='Configuração', on_delete=models.CASCADE)
    origem = models.ForeignKeyPlus(RotuloLista, verbose_name='Lista de Origem')
    destino = models.ForeignKeyPlus(RotuloLista, verbose_name='Lista de Destino', related_name='precedenciamigracao_set2')
    precedencia = models.IntegerField(verbose_name='Precedência')

    class Meta:
        verbose_name = 'Precedência'
        verbose_name_plural = 'Precedências'

    def __str__(self):
        return f'{self.origem} - {self.destino} - {self.precedencia}'


class CriacaoVagaRemanescente(models.ModelPlus):
    oferta_vaga = models.ForeignKeyPlus(OfertaVaga, verbose_name='Oferta de Vaga')
    qtd = models.IntegerField(verbose_name='Quantidade')
    responsavel = models.CurrentUserField(verbose_name='Responsável')
    data = models.DateTimeFieldPlus(verbose_name='Data', auto_now=True)
    justificativa = models.TextField(verbose_name='Justificativa')

    class Meta:
        verbose_name = 'Criação de Vaga Remanescente'
        verbose_name_plural = 'Criações de Vaga Remanescente'

    def __str__(self):
        return f'Criacao de Vaga Remanescente #{self.pk} - {self.oferta_vaga}'

    def save(self, *args, **kwargs):
        pk = self.pk
        super().save(*args, **kwargs)
        if pk is None:
            for _i in range(self.qtd):
                Vaga.objects.create(oferta_vaga=self.oferta_vaga)

    def corrigir_quantidade_vagas(self, qtd_ajustada):
        qtd_vagas_exclusao = self.qtd - qtd_ajustada
        if qtd_vagas_exclusao < 0:
            raise Exception('Para adiconar vagas realize uma nova criação de vagas remanescentes.')

        qs_vagas_disponiveis = Vaga.objects.filter(oferta_vaga_id=self.oferta_vaga.pk, candidatovaga__situacao__isnull=True).order_by(
            '-candidatovaga__classificacao'
        )
        qtd_vagas_disponiveis = qs_vagas_disponiveis.count()
        if qtd_vagas_exclusao > qtd_vagas_disponiveis:
            raise Exception(f'Não é possível excluir {qtd_vagas_exclusao} vaga(s). Há {qtd_vagas_disponiveis} vaga(s) disponíveis para exclusão.')

        for _i in range(qtd_vagas_exclusao):
            vaga = qs_vagas_disponiveis[0]
            CandidatoVaga.objects.filter(vaga=vaga).update(vaga=None, convocacao=None)
            vaga.delete()

        self.qtd = qtd_ajustada
        self.save()


class RegistroAjusteCriacaoVagaRemanescente(models.ModelPlus):
    criacao_vaga_remanescente = models.ForeignKeyPlus(CriacaoVagaRemanescente, verbose_name='Criação de Vaga Remanescente')
    qtd_ajustada = models.IntegerField(verbose_name='Quantidade Ajustada')
    responsavel = models.CurrentUserField(verbose_name='Responsável')
    data = models.DateTimeFieldPlus(verbose_name='Data', auto_now=True)
    justificativa = models.TextField(verbose_name='Justificativa')

    @transaction.atomic()
    def save(self, *args, **kwargs):
        self.criacao_vaga_remanescente.corrigir_quantidade_vagas(self.qtd_ajustada)
        super().save(*args, **kwargs)


class CriacaoClassificacao(models.ModelPlus):
    candidato_vaga = models.ForeignKeyPlus(CandidatoVaga, verbose_name='Oferta de Vaga')
    data = models.DateTimeFieldPlus(verbose_name='Data', auto_now_add=True)
    responsavel = models.CurrentUserField(verbose_name='Responsável')
    justificativa = models.TextField(verbose_name='Justificativa')

    def pode_ser_excluida(self):
        return self.candidato_vaga.situacao is None


class ImportacaoCSV(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital')
    arquivo_listas = models.FileFieldPlus(verbose_name='Arquivo de Listas', upload_to='processo_seletivo/importacao')
    arquivo_vagas = models.FileFieldPlus(verbose_name='Arquivo de Vagas', upload_to='processo_seletivo/importacao')
    arquivo_candidatos = models.FileFieldPlus(verbose_name='Arquivo de Candidatos', upload_to='processo_seletivo/importacao')
    arquivo_resultado = models.FileFieldPlus(verbose_name='Arquivo de Resultado', upload_to='processo_seletivo/importacao')
    arquivo_dados_pessoais = models.FileFieldPlus(verbose_name='Arquivo de Dados Pessoais', upload_to='processo_seletivo/importacao')

    def consultar_dados_candidato(self, candidato_vaga):
        from edu.models import Cidade, Estado, OrgaoEmissorRg

        dados = importacao.consultar_dados_candidato(candidato_vaga.candidato.cpf, open(self.arquivo_dados_pessoais.path, 'rb'))
        initial = (
            {
                'nome': dados['NOME'],
                'sexo': dados['GENERO'],
                'estado_civil': 'Solteiro',
                'tipo_sanguineo': None,
                'raca': None,
                'data_nascimento': parse_data_sgc(dados['DATA_NASCIMENTO']),
                'nacionalidade': 'Brasileira',
                'nome_mae': dados['NOME_MAE'],
                'nome_pai': dados['NOME_PAI'],
                'responsavel': dados['NOME_MAE'] or dados['NOME_PAI'],
                'parentesco_responsavel': 'Pai/Mãe',
                'logradouro': dados['LOGRADOURO'],
                'numero': dados['NUMERO'],
                'complemento': dados['COMPLEMENTO'],
                'bairro': dados['BAIRRO'],
                'cidade': Cidade.objects.filter(estado=Estado.get_estado_por_sigla(dados['UF_ENDERECO']), nome__exact=dados['MUNICIPIO_ENDERECO']),
                'estado': Estado.get_estado_por_sigla(dados['UF_ENDERECO']).pk,
                'cep': dados['CEP'],
                'telefone_principal': f'({dados["DDD_FONE1"]}) {dados["FONE1"]}' if dados['FONE1'] else '',
                'telefone_secundario': f'({dados["DDD_FONE2"]}) {dados["FONE2"]}' if dados['FONE2'] else '',
                'email_pessoal': dados['EMAIL'],
                'numero_rg': dados['RG'],
                'uf_emissao_rg': Estado.get_estado_por_sigla(dados['RG_UF']).pk,
                'orgao_emissao_rg': OrgaoEmissorRg.objects.get_or_create(nome=dados['RG_ORGAO_EMISSOR'])[0].id,
                'data_emissao_rg': parse_data_sgc(dados['RG_DATA_EMISSAO']),
                'linha_pesquisa': candidato_vaga.oferta_vaga.oferta_vaga_curso.linha_pesquisa,
                'tipo_zona_residencial': 1,
                'naturalidade': None,
            }
            if dados
            else {}
        )
        return initial
