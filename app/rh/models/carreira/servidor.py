import datetime
import logging
import operator
import tempfile
from collections import OrderedDict
from collections.abc import Iterable
from datetime import timedelta
from functools import cached_property, reduce
from typing import TYPE_CHECKING

import tqdm
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models import Case, Count, F, IntegerField, Sum, Value, When

from comum.types import ServidorCadastro, ServidorRetorno
from comum.utils import get_uo, get_uo_siape
from djtools.db import models
from djtools.db.models import Q, QuerySet
from djtools.templatetags.filters import in_group
from djtools.utils import cpf_valido, datas_entre, get_datetime_now, mask_cpf, mask_numbers, sync_ldap_setor, sync_ldap_user
from rh.deduplicacao.entrada import Politica, aplicar_politica
from rh.enums import TipoExtracao
from rh.utils import estah_no_pgd_hoje_pgd1_pgd2
from suap import nomenclatura

from ...managers import ServidorQueryset
from ..afastamento import AfastamentoSiape, ServidorAfastamento
from ..pcd import ExcecaoDado
from ..pessoa import AbstractFuncionario, PessoaFisica, PessoaInfoComplementar
from .carga_horaria import HorarioSemanal
from .funcao import Funcao
from .jornada import JornadaTrabalhoPCA
from .jornada_trabalho import JornadaTrabalho, JornadaTrabalhoPersonalizada
from .papel import Papel
from .provimento import FormaProvimentoVacancia
from .servidor_funcao import ServidorFuncaoHistorico
from .servidor_setor import ServidorSetorHistorico, ServidorSetorLotacaoHistorico
from .situacao import Situacao

if TYPE_CHECKING:
    # Imports só para tipagem (anotações); evitam import circular em runtime.
    from django.db.models import Prefetch

    from comum.models import Vinculo

    from ..organizacao import Setor

PRIVATE_ROOT_DIR = 'private-media/rh'
log = logging.getLogger(__name__)


def _prefetch_vinculos_servidor() -> Prefetch:
    from django.db.models import Prefetch

    from comum.models import Vinculo

    return Prefetch(
        'vinculos',
        queryset=Vinculo.objects.filter(tipo_relacionamento__model='servidor')
        .select_related('tipo_relacionamento')
        .prefetch_related('vinculo_curriculo_lattes'),
        to_attr='_vinculo_servidor_list',
    )


class Servidor(AbstractFuncionario):
    SEARCH_FIELDS = ['pessoa_fisica__search_fields_optimized', 'matricula']

    matricula_crh = models.CharField('Matrícula CRH', max_length=20, db_index=True)  # é o mesmo dado de rh.PCA.codigo_crh_pca
    matricula_sipe = models.CharField('Matrícula SIPE', max_length=20, db_index=True)
    matricula_anterior = models.CharField('Matrícula Anterior', max_length=20, null=True, blank=True)
    qtde_depend_ir = models.IntegerField(null=True, blank=True)
    nivel_padrao = models.CharField(max_length=4, null=True, blank=True)
    opera_raio_x = models.BooleanField(default=False)
    num_processo_aposentadoria = models.CharField(max_length=30, null=True, blank=True)
    numerador_prop_aposentadoria = models.CharField(max_length=20, null=True, blank=True)
    denominador_prop_aposentadoria = models.CharField(max_length=20, null=True, blank=True)
    data_cadastro_siape = models.DateField(null=True, blank=True)

    data_inicio_servico_publico = models.DateField(null=True, blank=True)
    data_inicio_exercicio_na_instituicao = models.DateField(null=True, blank=True)
    data_posse_na_instituicao = models.DateField(null=True, blank=True)
    data_posse_no_cargo = models.DateField(null=True, blank=True)
    data_inicio_exercicio_no_cargo = models.DateField(null=True, blank=True)

    data_fim_servico_na_instituicao = models.DateField(null=True, blank=True)

    # O campo excluido é definido pelo método rh.ServidorOcorrencia.save

    # email extraido do SIAPE
    email_siape = models.EmailField(blank=True, verbose_name='Email SIAPE')

    alterado_em = models.DateTimeField(auto_now=True)

    identificacao_unica_siape = models.CharField(max_length=20, null=True, blank=True, default='Novo')

    codigo_vaga = models.CharField(max_length=7, null=True, blank=True)  # é o mesmo dado de rh.PCA.codigo_vaga_siape_pca

    cargo_classe = models.ForeignKeyPlus('rh.CargoClasse', null=True, blank=True, on_delete=models.CASCADE)
    cargo_emprego = models.ForeignKeyPlus('rh.CargoEmprego', verbose_name='Cargo Emprego', null=True, blank=True, on_delete=models.CASCADE)
    cargo_emprego_area = models.ForeignKeyPlus(
        'rh.CargoEmpregoArea', verbose_name='Área do Cargo Emprego', null=True, blank=True, on_delete=models.CASCADE
    )

    cargo_emprego_data_ocupacao = models.DateField(null=True, blank=True)
    cargo_emprego_data_saida = models.DateField(null=True, blank=True)
    situacao = models.ForeignKeyPlus('rh.Situacao', null=False, verbose_name='Situação', on_delete=models.CASCADE)
    jornada_trabalho = models.ForeignKeyPlus('rh.JornadaTrabalho', null=True, blank=True, on_delete=models.CASCADE)
    # TODO: Verificar para poder retirar
    funcao = models.ForeignKeyPlus('rh.Funcao', null=True, blank=True, on_delete=models.CASCADE)
    funcao_atividade = models.ForeignKeyPlus('rh.Atividade', null=True, blank=True, on_delete=models.CASCADE)
    funcao_opcao = models.BooleanField(null=True)
    funcao_codigo = models.CharField(max_length=20, null=True, blank=True)
    funcao_data_ocupacao = models.DateField(null=True, blank=True)
    funcao_data_saida = models.DateField(null=True, blank=True)
    regime_juridico = models.ForeignKeyPlus('rh.RegimeJuridico', null=True, blank=True, on_delete=models.CASCADE)
    nivel_escolaridade = models.ForeignKeyPlus('rh.NivelEscolaridade', null=True, blank=True, on_delete=models.CASCADE)
    setor_lotacao_data_ocupacao = models.DateField(null=True)
    data_exclusao_instituidor = models.DateField(null=True, blank=True)
    titulacao = models.ForeignKeyPlus('rh.Titulacao', null=True, blank=True, on_delete=models.CASCADE)
    setor_exercicio = models.ForeignKeyPlus(
        'rh.Setor',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='servidores_exercicio',
        verbose_name='Setor de Exercício SIAPE',
    )
    areas_de_conhecimento = models.ManyToManyFieldPlus('rh.AreaConhecimento', blank=True)

    eh_docente = models.BooleanField(null=True)
    eh_tecnico_administrativo = models.BooleanField(null=True)

    data_ultima_atualizacao_webservice = models.DateTimeField(null=True, blank=True)
    # data base utilizada para progressões
    data_base_progressao = models.DateFieldPlus('Data Base para Progressões', null=True, blank=True)
    ## informação se participa do pgd e modalidade vindas do SIAPE
    participa_pgd = models.BooleanField('Participa do PGD', default=False)
    modalidade_pgd = models.ForeignKeyPlus('rh.ModalidadePgd', null=True, blank=True, on_delete=models.SET_NULL, verbose_name='Modalidade PGD')

    # Managers
    objects = ServidorQueryset.as_manager()

    vinculos = GenericRelation('comum.Vinculo', content_type_field='tipo_relacionamento', object_id_field='id_relacionamento')

    class Meta:
        db_table = 'servidor'
        verbose_name = 'Servidor'
        verbose_name_plural = 'Servidores'

        permissions = (
            ('pode_ver_relatorios_rh', 'Pode ver relatórios do RH'),
            ('chefe', 'Chefe'),
            ('gabinete', 'Gabinete'),
            ('auditor', 'Auditor'),
            ('eh_servidor', 'Servidor'),
            ('eh_rh_sistemico', 'RH Sistêmico'),
            ('eh_rh_campus', 'RH Campus'),
            ('cadastrador_rsc_simec', 'Cadastrador RSC/SIMEC'),
            ('pode_ver_cpf_servidor', 'Pode ver CPF'),
            ('pode_ver_dados_pessoais_servidor', 'Pode ver dados pessoais de servidores'),
            ('pode_ver_telefones_pessoais_servidor', 'Pode ver telefones pessoais de servidores'),
            ('pode_ver_endereco_servidor', 'Pode visualizar endereço de servidores'),
            ('pode_ver_dados_bancarios_servidor', 'Pode visualizar dados bancários de servidores'),
            ('pode_ver_dados_professor_servidor', 'Pode visualizar dados de professor de servidores'),
            ('pode_ver_ferias_servidor', 'Pode visualizar Férias dos servidores'),
            ('pode_ver_ocorrencias_afastamentos_servidor', 'Pode visualizar Ocorrências e Afastamentos dos Servidores'),
            ('pode_ver_historico_setores_servidor', 'Pode visualizar historico de setor dos Servidores'),
            ('pode_ver_historico_funcional_servidor', 'Pode visualizar historico funcional dos Servidores'),
            ('pode_ver_historico_funcao_servidor', 'Pode visualizar historico de funções dos Servidores'),
            ('pode_ver_arquivos_servidor', 'Pode visualizar arquivos dos Servidores'),
            ('pode_ver_contracheques_servidor', 'Pode visualizar contracheques dos Servidores'),
            ('pode_ver_viagens_servidor', 'Pode visualizar viagens dos Servidores'),
            ('pode_editar_cargo_emprego_externo', 'Pode editar cargo emprego de servidor fora do PCCTAE'),
            ('pode_ver_identificacao_unica_siape', 'Pode visualizar Identificação Única SIAPE'),
            ('pode_importar_servidor_ws', 'Pode importar servidor via Webservice'),
            ('pode_gerenciar_extracao_scdp', 'Pode gerenciar extração SCDP'),
            ('pode_gerenciar_extracao_siape', 'Pode gerenciar extração SIAPE'),
        )

    EXT_COMBO_RELATED = {
        'select_related': ['pessoa_fisica', 'setor', 'cargo_emprego', 'cargo_emprego__grupo_cargo_emprego', 'situacao'],
        'prefetch_related': [_prefetch_vinculos_servidor],
    }

    def __str__(self):
        return f'{self.pessoa_fisica_id and self.pessoa_fisica.nome or ""} ({self.matricula})'

    def get_vinculo(self) -> Vinculo | None:
        """Vínculo do servidor, lido do prefetch do autocomplete (``EXT_COMBO_RELATED``) quando houver (#17694)."""
        if hasattr(self, '_vinculo_servidor_list'):
            return next(iter(self._vinculo_servidor_list), None)
        return super().get_vinculo()

    def get_absolute_url(self):
        return f'/rh/servidor/{self.matricula}/'

    @staticmethod
    def _extrair_campos_do_vinculo(pessoa_fisica_dict: dict) -> dict:
        """Retira de ``pessoa_fisica_dict`` os campos que migraram para Vinculo e os devolve."""
        # Nota: sistema_origem não está aqui porque o importador SIAPE já o escreve
        # diretamente no vínculo (rh/importador.py); nenhum caller passa sistema_origem
        # via pessoa_fisica_dict, então não há risco de vazamento para PessoaFisica.
        vinculo_updates: dict = {}
        for campo in ('povo_indigena', 'raca', 'deficiencia'):
            if campo in pessoa_fisica_dict:
                vinculo_updates[campo] = pessoa_fisica_dict.pop(campo)
            campo_id = f'{campo}_id'
            if campo_id in pessoa_fisica_dict:
                vinculo_updates[campo_id] = pessoa_fisica_dict.pop(campo_id)
        # email_secundario/email migraram para Vinculo.email_pessoal: ambos alimentam o pessoal,
        # ficando o 1º não-institucional (regra do backfill 0115). email_notificacao virou property.
        email_secundario = pessoa_fisica_dict.pop('email_secundario', None)
        email_principal = pessoa_fisica_dict.pop('email', None)
        if email_secundario is not None or email_principal is not None:
            from comum.models import Configuracao

            candidatos = [e for e in (email_secundario, email_principal) if e and not Configuracao.eh_email_institucional(e)]
            vinculo_updates['email_pessoal'] = candidatos[0] if candidatos else ''
        return vinculo_updates

    @staticmethod
    def update_or_create(dados: ServidorCadastro) -> ServidorRetorno:
        pessoa_fisica_dict = dados['pessoa_fisica']
        if 'setores_adicionais' in pessoa_fisica_dict:
            setores_adicionais_alterados = True
            setores_adicionais = pessoa_fisica_dict.pop('setores_adicionais')
        else:
            setores_adicionais_alterados = False
            setores_adicionais = []
        vinculo_updates = Servidor._extrair_campos_do_vinculo(pessoa_fisica_dict)
        # foto migrou para Vinculo (S2.4b): intercepta para não vazar para PessoaFisica
        # ponytail: membership check distingue "ausente" (None default) de "limpar" (None explícito)
        foto_alterada = 'foto' in pessoa_fisica_dict
        foto_nova = pessoa_fisica_dict.pop('foto', None)
        servidor_pk = dados.get('pk', 0)
        if servidor_pk:
            servidor = Servidor.objects.filter(pk=servidor_pk).first()
        else:
            servidor = Servidor.objects.filter(matricula=dados['matricula']).first()
        if not servidor:
            pessoa_fisica, pessoa_fisica_created = PessoaFisica.objects.obter_ou_criar(pessoa_fisica_dict, Politica.AUTORITATIVA)
            dados['pessoa_fisica'] = pessoa_fisica
            servidor = Servidor.objects.create(**dados)
            servidor_created = True
        else:
            # SIAPE é a fonte mais confiável: sobrescreve tudo, exceto com valor nulo/vazio
            pessoa_fisica, pessoa_fisica_created = servidor.pessoa_fisica, False
            aplicar_politica(pessoa_fisica, pessoa_fisica_dict, Politica.AUTORITATIVA)
            pessoa_fisica.save()
            dados['pessoa_fisica'] = pessoa_fisica
            servidor, servidor_created = Servidor.objects.update_or_create(pk=servidor.pk, defaults=dados)

        v = servidor.get_vinculo()
        if v:
            if setores_adicionais_alterados:
                v.setores_adicionais.set(setores_adicionais)
            if vinculo_updates:
                for campo, valor in vinculo_updates.items():
                    setattr(v, campo, valor)
                v.save(update_fields=list(vinculo_updates.keys()))
            if foto_alterada:
                v.foto = foto_nova  # None limpa; File salva
                v.save(update_fields=['foto'])

        retorno: ServidorRetorno = {
            'servidor': servidor,
            'servidor_created': servidor_created,
            'pessoa_fisica': pessoa_fisica,
            'pessoa_fisica_created': pessoa_fisica_created,
        }
        return retorno

    def save(self, *args, **kwargs):
        from comum.models import User, Vinculo

        from .servidor_setor import ServidorSetorHistorico

        User.objects.get_or_create_user(self.matricula, self.pessoa_fisica.cpf)

        self.pessoa_fisica.eh_servidor = True

        eh_novo_registro = self.id is None

        def campus_siape_igual_campus_suap(setor_a, setor_b):
            return setor_a and setor_b and setor_b.uo and setor_b.uo.equivalente and setor_b.uo.equivalente == setor_a.uo

        # A restrição só será feita se o servidor tiver setor de exercício SIAPE
        # e não for estagiário.
        if self.setor_exercicio and not self.eh_estagiario:
            if settings.TIPO_ARVORE_SETORES == 'SUAP':
                if not campus_siape_igual_campus_suap(self.setor, self.setor_exercicio):
                    if self.setor and self.setor.uo:
                        from chaves.models import Chave

                        chaves = Chave.objects.filter(vinculos=self.get_vinculo(), sala__predio__uo=self.setor.uo)
                        for chave in chaves:
                            chave.vinculos.remove(self.get_vinculo())
                        self.setor = None

            else:
                self.setor = self.setor_exercicio

        # Seta se o servidor é tec. administrativo ou docente
        nao_tem_categoria = not self.eh_docente and not self.eh_tecnico_administrativo
        if nao_tem_categoria and self.cargo_emprego and self.cargo_emprego.grupo_cargo_emprego.categoria == 'docente':
            self.eh_docente = True

        if (
            nao_tem_categoria
            and not self.eh_tecnico_administrativo
            and self.cargo_emprego
            and self.cargo_emprego.grupo_cargo_emprego.categoria == 'tecnico_administrativo'
        ):
            self.eh_tecnico_administrativo = True

        if self.pk:
            servidor_anterior = Servidor.objects.get(pk=self.pk)
            historico_setores_servidor = ServidorSetorHistorico.objects.filter(servidor=self)
            if self.setor:
                if not historico_setores_servidor.exists():
                    #
                    # não tem histórico SUAP
                    if self.data_cadastro_siape:
                        ServidorSetorHistorico.objects.create(servidor=self, setor=self.setor, data_inicio_no_setor=self.data_cadastro_siape)
                    else:
                        ServidorSetorHistorico.objects.create(servidor=self, setor=self.setor, data_inicio_no_setor=datetime.date.today())
                else:
                    if servidor_anterior.setor != self.setor:
                        historico_setor_data_inicio_hoje = historico_setores_servidor.filter(data_inicio_no_setor=datetime.date.today())
                        if historico_setor_data_inicio_hoje.exists():
                            historico_atualizar = historico_setor_data_inicio_hoje[0]
                            historico_atualizar.setor = self.setor
                            historico_atualizar.save()
                        else:
                            """
                            o último histórico SUAP deve ser resolvido:
                                Se não há último histórico SIAPE:
                                    Cria-se um novo histórico SUAP:
                                        data inicial = hoje
                                        data final = nenhuma
                                Senão
                                    Se data inicial >= data inicial do último histórico SIAPE
                                        O último histórico SUAP já refere-se ao último histórico SIAPE.
                                        Atualiza o último histórico SUAP:
                                            setor = setor informado pelo RH
                                            data final = data final do último histórico SIAPE
                                    Senão (situação NORMAL)
                                        Conclui o último histórico SUAP:
                                            data final = data inicial do atual histórico SIAPE - 1 dia
                                        Cria-se um novo histórico SUAP:
                                            data inicial = data inicial do último histórico SIAPE
                                            data final = nenhuma
                            """
                            historico_siape = self.historico_setor_siape()
                            ultimo_historico_siape = None
                            if historico_siape.exists():
                                ultimo_historico_siape = historico_siape.order_by('-data_inicio_setor_lotacao')[0]
                            if not ultimo_historico_siape:
                                #
                                # cria novo histórico suap a partir de HOJE
                                ServidorSetorHistorico.objects.create(servidor=self, setor=self.setor, data_inicio_no_setor=datetime.date.today())
                            else:
                                ultimo_historico_suap = ServidorSetorHistorico.objects.filter(servidor=self).order_by('-data_inicio_no_setor')[0]
                                #
                                data_inicial_ultimo_historico_suap = ultimo_historico_suap.data_inicio_no_setor
                                data_inicial_ultimo_historico_siape = ultimo_historico_siape.data_inicio_setor_lotacao
                                data_final_ultimo_historico_siape = ultimo_historico_siape.data_fim_setor_lotacao
                                #
                                if data_inicial_ultimo_historico_suap >= data_inicial_ultimo_historico_siape:
                                    #
                                    # situação ANORMAL
                                    # atualiza o último histórico suap no dia
                                    ultimo_historico_suap.setor = self.setor
                                    ultimo_historico_suap.data_fim_no_setor = data_final_ultimo_historico_siape
                                    ultimo_historico_suap.save()
                                else:
                                    #
                                    # situação NORMAL
                                    # finaliza o último histórico suap no dia
                                    # anterior ao primeiro dia do último histórico siape
                                    ultimo_historico_suap.data_fim_no_setor = data_inicial_ultimo_historico_siape - datetime.timedelta(days=1)
                                    ultimo_historico_suap.save()
                                    #
                                    # cria novo histórico suap
                                    ServidorSetorHistorico.objects.create(
                                        servidor=self, setor=self.setor, data_inicio_no_setor=data_inicial_ultimo_historico_siape
                                    )
            self.pessoa_fisica.save()
            servidor = super().save(*args, **kwargs)
        else:
            self.pessoa_fisica.save()
            servidor = super().save(*args, **kwargs)
            if self.setor:
                if self.data_cadastro_siape:
                    ServidorSetorHistorico.objects.create(servidor=self, setor=self.setor, data_inicio_no_setor=self.data_cadastro_siape)
                else:
                    ServidorSetorHistorico.objects.create(servidor=self, setor=self.setor, data_inicio_no_setor=datetime.date.today())

        user = self.get_user()

        defaults = {
            'pessoa': self.pessoa_fisica.pessoa_ptr,
            'user': user,
            'setor': self.setor,
            'ativo': self.ativo,
        }
        tipo_relacionamento = ContentType.objects.get_for_model(self)
        Vinculo.objects.update_or_create(id_relacionamento=self.id, tipo_relacionamento=tipo_relacionamento, defaults=defaults)
        #
        cache.delete(f'servidor_tem_setor_middleware_{self.matricula}')
        user.save()
        if getattr(self, 'setor', None):
            sync_ldap_setor(self.setor)
        sync_ldap_user(self.matricula)

        if eh_novo_registro:
            user.enviar_email_boas_vindas()

        # Com isso toda vez que um servidor for salvo, ele terá o papel correto
        if self.eh_estagiario:
            self._definir_papel_do_estagiario()
        else:
            self._definir_papel_do_servidor()
        return servidor

    def get_foto_path(self):
        if self.foto and default_storage.exists(self.foto.name):
            tmp = tempfile.NamedTemporaryFile(delete=False)
            with self.foto.open('rb') as f:
                tmp.write(f.read())
            tmp.close()
            return tmp.name
        return self.get_foto_path_anonimo()

    def get_foto_path_anonimo(self):
        return f'{settings.BASE_DIR}/static/comum/img/default.jpg'

    def estah_afastado_ou_de_ferias_ateh(self, dia):
        retorno = []
        parcela = self.estah_de_ferias_ateh(dia)
        if parcela:
            retorno.append(f'Férias até {parcela.data_fim.strftime("%d/%m/%Y")}')

        afastamento = self.estah_afastado_ateh(dia)
        if afastamento:
            retorno.append(f'Afastado até {afastamento.data_termino.strftime("%d/%m/%Y")}')
        return ', '.join(retorno)

    def estah_de_ferias_ateh(self, dia):
        parcela = None
        if 'ferias' in settings.INSTALLED_APPS:
            from ferias.models import ParcelaFerias

            parcela = ParcelaFerias.objects.filter(ferias__servidor=self, data_inicio__lte=dia, data_fim__gte=dia).first()
        return parcela

    def estah_afastado_ateh(self, dia):
        afastamento = (
            ServidorAfastamento.objects.exclude_afastamentos_pgd()
            .filter(servidor=self, data_inicio__lte=dia, data_termino__gte=dia, cancelado=False)
            .first()
        )
        return afastamento

    def estah_em_recesso(self, dia):
        recesso = False
        if 'ponto' in settings.INSTALLED_APPS:
            from ponto.models import RecessoDiaEscolhido, RecessoOpcaoEscolhida

            recesso = RecessoDiaEscolhido.objects.filter(
                recesso_opcao_escolhida__funcionario=self,
                recesso_opcao_escolhida__validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
                dia__data=dia,
            ).exists()
        return recesso

    def get_titulacao(self):
        if self.titulacao:
            if self.pessoa_fisica.sexo == 'M':
                return self.titulacao.titulo_masculino or self.titulacao.nome
            else:
                return self.titulacao.titulo_feminino or self.titulacao.nome
        return None

    def setor_na_data(self, data, chefes_setor_lotacao=False):
        """
        Setor do Funcionário em uma determinada data.
        """
        if chefes_setor_lotacao:
            historico = ServidorSetorLotacaoHistorico.objects.filter(servidor=self).filter(
                Q(data_inicio_setor_lotacao__lte=data), Q(data_fim_setor_lotacao__gte=data) | Q(data_fim_setor_lotacao__isnull=True)
            )
            if historico.exists():
                return historico[0].setor_lotacao
            return self.setor_lotacao
        else:
            historico = ServidorSetorHistorico.objects.filter(servidor=self).filter(
                Q(data_inicio_no_setor__lte=data), Q(data_fim_no_setor__gte=data) | Q(data_fim_no_setor__isnull=True)
            )

            if historico.exists():
                return historico[0].setor
            return self.setor

    @classmethod
    def get_by_cpf_ou_matricula(cls, cpf_ou_matricula):
        if cpf_valido(cpf_ou_matricula):
            # Buscar por CPF
            res = cls.objects.filter(pessoa_fisica__cpf=mask_numbers(cpf_ou_matricula)) | cls.objects.filter(
                pessoa_fisica__cpf=mask_cpf(cpf_ou_matricula)
            )
            if not res:
                return None
            elif len(res) == 1:
                return res[0]
            elif len(res) > 1:
                # Existem pelo menos 2 pessoas físicas com o mesmo CPF,
                # provavelmente são servidores e apenas um está ativo.
                try:
                    return Servidor.objects.get(pk__in=res.values_list('pk', flat=True), ativo=True)
                except Servidor.DoesNotExist, Servidor.MultipleObjectsReturned:
                    return res.latest('id')
        else:
            # Buscar por matrícula
            try:
                return Servidor.objects.get(matricula=cpf_ou_matricula)
            except Servidor.DoesNotExist:
                return None

    # get_vinculo() herdado de AbstractRelacionamento (prefetch-friendly)

    def get_user(self):
        from comum.models import User

        return User.objects.filter(username=self.matricula).first()

    @staticmethod
    def quadro_referencia_administrativos():
        """Total por nível (A, B, C, D e E) e total geral por campus de lotação SIAPE considerando apenas
        ativos permanentes e cedidos.
        """
        Situacao = apps.get_model('rh', 'Situacao')
        quadro_tecnicos = (
            Servidor.objects.filter(
                ativo=True,
                eh_tecnico_administrativo=True,
                cargo_classe__codigo__in=('A', 'B', 'C', 'D', 'E'),
                vinculos__sistema_origem__exact='SIAPE',
                situacao__codigo__in=Situacao.SITUACOES_EFETIVOS,
            )
            .values('setor_lotacao__uo__id', 'setor_lotacao__uo__sigla', 'cargo_classe__codigo')
            .order_by('setor_lotacao__uo__sigla')
        )

        quadro_final = OrderedDict()
        for s in quadro_tecnicos:
            campus_id = s['setor_lotacao__uo__id']
            campus_sigla = s['setor_lotacao__uo__sigla']
            cargo_classe = s['cargo_classe__codigo']

            if campus_id not in quadro_final:
                quadro_final[campus_id] = {'sigla': campus_sigla, 'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'total': 0}

            quadro_final[campus_id][cargo_classe] += 1
            quadro_final[campus_id]['total'] += 1
        # ----
        return quadro_final

    @staticmethod
    def quadro_referencia_administrativos_novo():
        """Total por nível (A, B, C, D e E) e total geral por campus de lotação SIAPE considerando apenas
        ativos permanentes e cedidos.
        """
        Situacao = apps.get_model('rh', 'Situacao')
        quadro_final = (
            Servidor.objects.filter(
                ativo=True,
                eh_tecnico_administrativo=True,
                cargo_classe__codigo__in=('A', 'B', 'C', 'D', 'E'),
                situacao__codigo__in=Situacao.SITUACOES_EFETIVOS,
            )
            .values('setor_lotacao__uo__id', 'setor_lotacao__uo__sigla', 'cargo_classe__codigo')
            .annotate(total=Count('pk'))
            .annotate(
                sigla=F('setor_lotacao__uo__sigla'),
            )
            .values('setor_lotacao__uo__id', 'sigla')
            .annotate(
                A=Sum(Case(When(cargo_classe__codigo='A', then=Value(1)), default=Value(0), output_field=IntegerField())),
                B=Sum(Case(When(cargo_classe__codigo='B', then=Value(1)), default=Value(0), output_field=IntegerField())),
                C=Sum(Case(When(cargo_classe__codigo='C', then=Value(1)), default=Value(0), output_field=IntegerField())),
                D=Sum(Case(When(cargo_classe__codigo='D', then=Value(1)), default=Value(0), output_field=IntegerField())),
                E=Sum(Case(When(cargo_classe__codigo='E', then=Value(1)), default=Value(0), output_field=IntegerField())),
            )
            .annotate(total=F('A') + F('B') + F('C') + F('D') + F('E'))
            .order_by('setor_lotacao__uo__sigla')
        )

        return quadro_final

    @staticmethod
    def quadro_referencia_docentes():
        """Total de docentes por Jornada de Trabalho"""
        Situacao = apps.get_model('rh', 'Situacao')
        # ------
        quadro_docentes = (
            Servidor.objects.filter(
                ativo=True,
                eh_docente=True,
                situacao__codigo__in=Situacao.SITUACOES_EFETIVOS_E_TEMPORARIOS,
            )
            .values(
                'setor_lotacao__uo__id',
                'setor_lotacao__uo__sigla',
                'jornada_trabalho__codigo',
                'situacao__codigo',
                'jornada_trabalho__docente_peso',
            )
            .order_by('setor_lotacao__uo__sigla')
        )

        quadro_final = OrderedDict()
        quadro_total = {
            '20': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
            '40': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
            '99': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
            'TT': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
            'NA': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
        }

        for s in quadro_docentes:
            campus_id = s['setor_lotacao__uo__id']
            campus_sigla = s['setor_lotacao__uo__sigla'] or f'Sem {nomenclatura.campus}'
            jornada_codigo = s['jornada_trabalho__codigo'] or 'NA'
            situacao_codigo = s['situacao__codigo']
            jornada_peso = s['jornada_trabalho__docente_peso'] or 0

            if campus_id not in quadro_final:
                quadro_final[campus_id] = {
                    'sigla': campus_sigla,
                    '20': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
                    '40': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
                    '99': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
                    'TT': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
                    'NA': {'qtd_efetivos': 0, 'peso_efetivos': 0, 'qtd_temporarios': 0, 'peso_temporarios': 0},
                }

            descricao_vinculo = 'efetivos'
            if situacao_codigo not in Situacao.SITUACOES_EFETIVOS:
                descricao_vinculo = 'temporarios'
            quadro_final[campus_id][jornada_codigo]['qtd_' + descricao_vinculo] += 1
            quadro_final[campus_id][jornada_codigo]['peso_' + descricao_vinculo] += jornada_peso
            quadro_final[campus_id]['TT']['qtd_' + descricao_vinculo] += 1
            quadro_final[campus_id]['TT']['peso_' + descricao_vinculo] += jornada_peso

            quadro_total[jornada_codigo]['qtd_' + descricao_vinculo] += 1
            quadro_total[jornada_codigo]['peso_' + descricao_vinculo] += jornada_peso
            quadro_total['TT']['qtd_' + descricao_vinculo] += 1
            quadro_total['TT']['peso_' + descricao_vinculo] += jornada_peso
        # ------
        return (quadro_final, quadro_total)

    def pode_gerar_cracha(self) -> bool:
        DocumentoControleTipo = apps.get_model('comum', 'DocumentoControleTipo')
        try:
            cracha = DocumentoControleTipo.objects.get(identificador=DocumentoControleTipo.CRACHA)
            return bool(
                self.situacao
                and not self.pessoa_fisica.data_obito
                and all([self.pessoa_fisica.grupo_sanguineo, self.pessoa_fisica.fator_rh, self.pessoa_fisica.nome_usual, self.foto])
                and (self.situacao.codigo,) in cracha.abrangencia.values_list('codigo')
            )
        except DocumentoControleTipo.DoesNotExist, DocumentoControleTipo.MultipleObjectsReturned:
            # Tipo de documento não cadastrado (ou duplicado): não há abrangência para conferir.
            return False

    def pode_gerar_carteira_funcional(self) -> bool:
        """
        Define se pode ser gerada carteira funcional para o servidor em questão.
        Atualmente geramos carteira funcionais para Ativos Permamentes e Aposentados vivos
        """
        DocumentoControleTipo = apps.get_model('comum', 'DocumentoControleTipo')
        try:
            carteira = DocumentoControleTipo.objects.get(identificador=DocumentoControleTipo.CARTEIRA_FUNCIONAL)
            return bool(
                self.situacao
                and not self.pessoa_fisica.data_obito
                and all(
                    [
                        self.pessoa_fisica.nome,
                        self.pessoa_fisica.grupo_sanguineo,
                        self.pessoa_fisica.fator_rh,
                        self.pessoa_fisica.nome_mae,
                        self.pessoa_fisica.rg,
                        self.pessoa_fisica.rg_orgao,
                        self.pessoa_fisica.nascimento_municipio,
                        self.pessoa_fisica.cpf,
                        self.pessoa_fisica.nascimento_data,
                        self.foto,
                        self.cargo_emprego,
                    ]
                )
                and (self.situacao.codigo,) in carteira.abrangencia.values_list('codigo')
            )
        except DocumentoControleTipo.DoesNotExist, DocumentoControleTipo.MultipleObjectsReturned:
            # Tipo de documento não cadastrado (ou duplicado): não há abrangência para conferir.
            return False

    def get_ext_combo_template(self) -> str:
        out = [f'<dt class="visually-hidden">Nome</dt><dd class="title">{self.pessoa_fisica.nome} (Mat. {self.matricula})</dd>']
        if self.setor:
            out.append(f'<dt class="visually-hidden">Setor</dt><dd>{self.setor.get_caminho_as_html()}</dd>')
        if self.eh_estagiario:
            out.append('<dt class="visually-hidden">Vínculo</dt><dd>Estagiário</dd>')
        elif self.cargo_emprego:
            out.append(f'<dt class="visually-hidden">Cargo</dt><dd>{self.cargo_emprego}</dd>')
        template = """<div class="person">
            <div class="photo-circle">
                <img src="{}" alt="Foto de {}" />
            </div>
            <dl>{}</dl>
        </div>
        """.format(self.get_foto_75x100_url(), self.pessoa_fisica.nome, ''.join(out))
        return template

    def tem_acesso_servicos_microsoft(self):
        if self.cargo_emprego and not self.eh_aposentado:
            return '.edu.br' in self.email_institucional and (self.eh_docente or in_group(self.get_user(), 'Usuário do Microsoft Imagine'))

    @cached_property
    def setores_que_eh_chefe_hoje(self):
        from ..organizacao import Setor

        if self.setor:
            setores_id_que_eh_chefe_hoje = []
            hoje = get_datetime_now().date()
            historico_funcao = (
                self.historico_funcao(hoje, hoje)
                .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False)
                .select_related('setor_suap')
            )

            for funcao_setor in historico_funcao:
                for setor in funcao_setor.setor_suap.descendentes:
                    setores_id_que_eh_chefe_hoje.append(setor.id)
            if setores_id_que_eh_chefe_hoje:
                return Setor.objects.suap_ativos().filter(pk__in=setores_id_que_eh_chefe_hoje)

        return Setor.objects.suap_ativos().none()

    def eh_chefe_do_setor_periodo(self, setor, data_ini, data_fim):
        historico_funcao = self.historico_funcao(data_ini, data_fim).filter(
            funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False
        )
        if historico_funcao.exists():
            for funcao_setor in historico_funcao:
                if setor.id in funcao_setor.setor_suap.ids_descendentes:
                    return True
        return False

    def tem_funcoes_no_periodo(self, data_ini, data_fim):
        historico_funcao = self.historico_funcao(data_ini, data_fim).filter(
            funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False
        )
        return historico_funcao.exists()

    def get_setores_suap_no_periodo(self, data_inicio: datetime.date, data_fim: datetime.date | None = None) -> dict:
        setores_historico_por_dia: dict[datetime.date, ServidorSetorHistorico] = {}

        data_fim_periodo = data_fim or datetime.date.today()

        historico_setor = self.historico_setor_suap(data_inicio, data_fim)

        for historico in historico_setor.distinct():
            for dia in datas_entre(historico.data_inicio_no_setor, historico.data_fim_no_setor or data_fim_periodo):
                if data_inicio <= dia <= data_fim_periodo:
                    setores_historico_por_dia[dia] = historico

        return setores_historico_por_dia

    def get_funcoes_no_periodo(self, data_inicio: datetime.date, data_fim: datetime.date | None = None) -> dict:
        funcoes_historico_por_dia: dict[datetime.date, ServidorFuncaoHistorico] = {}

        data_fim_periodo = data_fim or datetime.date.today()

        historico_funcao = self.historico_funcao(data_inicio, data_fim).filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia())

        for historico in historico_funcao.distinct():
            for dia in datas_entre(historico.data_inicio_funcao, historico.data_fim_funcao or data_fim_periodo):
                if data_inicio <= dia <= data_fim_periodo:
                    funcoes_historico_por_dia[dia] = historico  # considera-se apenas uma função ao mesmo tempo

        return funcoes_historico_por_dia

    def get_chefes_no_periodo(
        self,
        data_inicio: datetime.date,
        data_fim: datetime.date | None = None,
        substituicao_chefia_eh_chefe=True,
        return_qs_historico_funcoes=False,
    ) -> dict[datetime.date, list[Servidor]] | models.QuerySet[ServidorFuncaoHistorico]:
        """Chefes dos setores do servidor em todos os dias do
        período informado.
        Um chefe não poderá ser chefe de si mesmo, exceto no caso de
        reitor. No caso de não ser o reitor, seu chefe estará em algum
        setor ascendente, até que seja o próprio reitor do período
        informado.
        Por padrão, as substituições de chefia tem força de chefia.
        Serão consideradas apenas as funções setadas como funções de chefia.
        Todos os dias do período informado terão uma lista de
        servidores, mesmo que vazia.
        """

        data_fim = data_fim or datetime.date.today()

        h_funcoes = (
            ServidorFuncaoHistorico.objects.select_related(
                'servidor',
                'funcao',
                'setor_suap',
            )
            .filter(
                data_inicio_funcao__lte=data_inicio,
            )
            .filter(models.Q(data_fim_funcao__gte=data_fim) | models.Q(data_fim_funcao__isnull=True))
            .annotate(
                funcao_eh_reitor=models.Case(
                    models.When(models.Q(funcao__codigo=Funcao.CODIGO_CD) & models.Q(nivel__in=('1', '0001')), then=models.Value(True)),
                    default=models.Value(False),
                    output_field=models.BooleanField(),
                )
            )
            .distinct()
        )

        # Sigla da função de substituição de chefia: um substituto NÃO conta como
        # "titular" do setor para fins de subir de nível na resolução da chefia.
        sigla_substituicao_chefia = Funcao.get_sigla_substituicao_chefia()

        if not substituicao_chefia_eh_chefe:
            h_funcoes = h_funcoes.exclude(
                # Exclui as substituições de chefia.
                funcao__codigo=sigla_substituicao_chefia
            )

        # Considera apenas as funções que são
        # setadas como funções de chefia.
        h_funcoes = h_funcoes.filter(funcao__eh_funcao_chefia=True)

        h_setores = (
            ServidorSetorHistorico.objects.select_related(
                'servidor',
                'setor',
                'setor__superior',
            )
            .filter(
                servidor=self,
                data_inicio_no_setor__lte=data_inicio,
            )
            .filter(models.Q(data_fim_no_setor__gte=data_fim) | models.Q(data_fim_no_setor__isnull=True))
        )

        # O servidor deve estar em algum setor para
        # que a busca da(s) chefia(s) seja possível.
        if h_setores.exists():
            h_funcoes_setores = self._resolver_chefias_nos_setores([h_setor.setor for h_setor in h_setores], h_funcoes, sigla_substituicao_chefia)
        else:
            h_funcoes_setores = ServidorFuncaoHistorico.objects.none()

        if return_qs_historico_funcoes:
            return h_funcoes_setores

        chefes_no_periodo: dict[datetime.date, list[Servidor]] = {}

        for dia in datas_entre(data_inicio, data_fim):
            if dia not in chefes_no_periodo:
                chefes_no_periodo[dia] = []

            h_funcoes_no_dia = h_funcoes_setores.filter(
                data_inicio_funcao__lte=dia,
            ).filter(models.Q(data_fim_funcao__gte=dia) | models.Q(data_fim_funcao__isnull=True))

            for h_funcao in h_funcoes_no_dia:
                chefe = h_funcao.servidor
                if chefe not in chefes_no_periodo[dia]:
                    chefes_no_periodo[dia].append(chefe)

        return chefes_no_periodo

    def _resolver_chefias_nos_setores(
        self,
        setores: Iterable[Setor],
        h_funcoes: models.QuerySet[ServidorFuncaoHistorico],
        sigla_substituicao_chefia: str | None,
    ) -> models.QuerySet[ServidorFuncaoHistorico]:
        """Resolve as funções de chefia que comandam o servidor a partir de ``setores``.

        Nos setores em que o próprio servidor é **titular** de chefia (função de
        chefia que não é substituição e não é reitor), seu chefe está no setor
        **superior** — os substitutos do próprio setor não chefiam o titular.
        Quando o servidor não é titular, a chefia é a do próprio setor. Sobe
        recursivamente até encontrar chefia ou, no limite, o reitor.
        """
        # Setores em que o próprio servidor é titular (exclui substituição e reitor).
        funcoes_titular_self = h_funcoes.filter(setor_suap__in=setores, servidor=self, funcao_eh_reitor=False)
        if sigla_substituicao_chefia:
            funcoes_titular_self = funcoes_titular_self.exclude(funcao__codigo=sigla_substituicao_chefia)
        setores_self_titular_ids = set(funcoes_titular_self.values_list('setor_suap_id', flat=True))

        # Onde o servidor é titular, troca o setor pelo seu superior.
        setores_efetivos = []
        for setor in setores:
            eh_titular_no_setor = setor.pk in setores_self_titular_ids
            if eh_titular_no_setor and setor.superior:
                setores_efetivos.append(setor.superior)
            elif not eh_titular_no_setor:
                setores_efetivos.append(setor)
            # titular sem setor superior: cai no fallback do reitor abaixo.

        h_funcoes_setores = h_funcoes.filter(setor_suap__in=setores_efetivos).exclude(
            # Exclui chefia de si mesmo se não for reitor.
            servidor=self,
            funcao_eh_reitor=False,
        )

        if not h_funcoes_setores.exists():
            # Chefe nos setores superiores; no limite será o reitor do período.
            setores_superiores = [setor.superior for setor in setores_efetivos if setor.superior]
            if setores_superiores:
                h_funcoes_setores = self._resolver_chefias_nos_setores(setores_superiores, h_funcoes, sigla_substituicao_chefia)
            else:
                h_funcoes_setores = h_funcoes.filter(funcao_eh_reitor=True)

        return h_funcoes_setores

    def get_dias_liberado_frequencia_periodo(self, data_ini, data_fim):
        from .servidor_funcao import ServidorFuncaoHistorico

        dias_liberado_frequencia = []

        qry_dias_liberado_frequencia = ServidorFuncaoHistorico.get_liberados_frequencia(self.historico_funcao(data_ini, data_fim))

        if qry_dias_liberado_frequencia.exists():
            for funcao_servidor in qry_dias_liberado_frequencia:
                if funcao_servidor.data_inicio_funcao < data_ini:
                    funcao_servidor.data_inicio_funcao = data_ini
                if not funcao_servidor.data_fim_funcao or funcao_servidor.data_fim_funcao > data_fim:
                    funcao_servidor.data_fim_funcao = data_fim
                dias_liberado_frequencia += datas_entre(funcao_servidor.data_inicio_funcao, funcao_servidor.data_fim_funcao)

        return dias_liberado_frequencia

    def chefes_imediatos(self):
        if self.setor:
            setor = self.setor

            if self.eh_chefe_do_setor_hoje(self.setor):
                if self.setor.superior:
                    setor = self.setor.superior

            while not setor.historico_funcao().exists() and setor.superior:
                setor = setor.superior

            return Servidor.objects.filter(pk__in=setor.historico_funcao().values_list('servidor_id', flat=True))
        return Servidor.objects.none()

    def eh_liberado_controle_frequencia(self):
        return ServidorFuncaoHistorico.get_liberados_frequencia(self.historico_funcao_ativa).exists()

    @property
    def disciplina_ingresso(self):
        if self.eh_docente and self.get_vinculo().professor_set.all().exists():
            return self.get_vinculo().professor_set.all()[0].disciplina
        return '-'

    @property
    def professor(self):
        if 'edu' in settings.INSTALLED_APPS:
            return self.get_vinculo().professor_set.first()
        else:
            return None

    @classmethod
    def get_sem_setor_suap(cls, do_meu_campus=False):
        servidores = cls.objects.vinculados().filter(setor__isnull=True).exclude(situacao__codigo=Situacao.APOSENTADOS)
        if do_meu_campus:
            meu_campus_siape = get_uo_siape()
            servidores = servidores.filter(setor_lotacao__uo=meu_campus_siape) | servidores.filter(setor_funcao__uo=meu_campus_siape)
        return servidores.order_by('pessoa_fisica__nome')

    @classmethod
    def get_sem_cargo(cls, do_meu_campus=False):
        situacoes = (Situacao.APOSENTADOS, *Situacao.situacoes_siape_estagiarios())
        servidores = cls.objects.vinculados().filter(cargo_emprego__isnull=True).exclude(situacao__codigo__in=situacoes)
        if do_meu_campus:
            servidores = servidores.filter(setor__uo=get_uo())
        return servidores.order_by('pessoa_fisica__nome')

    @staticmethod
    def get_servidores_com_cargafuncao(campus=None, funcao=None):
        servidores = Servidor.objects.filter(funcao__isnull=False, ativo=True)
        if campus:
            servidores = servidores.filter(setor__uo=campus)
        if funcao:
            servidores = servidores.filter(funcao=funcao)
        servidores = servidores.order_by('setor__uo__setor__sigla', 'pessoa_fisica__nome')
        return servidores

    @property
    def eh_aposentado(self):
        return self.situacao.codigo == Situacao.APOSENTADOS

    @property
    def eh_estagiario(self):
        return self.situacao.codigo in Situacao.situacoes_siape_estagiarios()

    @property
    def get_grupo_cargo_emprego(self):
        if self.cargo_emprego:
            return self.cargo_emprego.grupo_cargo_emprego
        return None

    @property
    def get_modelo_regime_trabalho(self):
        modelo_regime_trabalho = 'Presencial'
        if 'pgd2' in settings.INSTALLED_APPS:
            esta_em_pgd, adesao_pgd = estah_no_pgd_hoje_pgd1_pgd2(self)
            if esta_em_pgd and adesao_pgd:
                modelo_regime_trabalho = adesao_pgd.planoindividualtrabalho_set.order_by('-data_fim').last().get_regime_execucacao_display()
        return modelo_regime_trabalho

    @property
    def dependentes(self):
        Dependente = apps.get_model('comum', 'Dependente')
        return Dependente.objects.filter(servidor=self)

    @property
    def dependentes_ir(self):
        from datetime import date as _date

        from django.db.models import Q

        Dependente = apps.get_model('comum', 'Dependente')
        hoje = _date.today()
        return (
            Dependente.objects.filter(
                servidor=self,
                beneficiodependente__beneficio__codigo='03',
            )
            .filter(Q(beneficiodependente__data_termino__isnull=True) | Q(beneficiodependente__data_termino__gte=hoje))
            .distinct()
            .select_related('usuario_externo__pessoa_fisica', 'grau_parentesco')
        )

    @property
    def atividade(self):
        return self.funcao_atividade

    @property
    def funcao_display(self):
        return '{}{}'.format(self.funcao and self.funcao.codigo or '', self.funcao_codigo or '')

    @property
    def categoria(self):
        """
        Teoricamente pode retornar 3 strings:
            ['Técnico-administrativo', 'Docente', 'ESTAGIARIO']
        """
        if self.eh_docente:
            return 'docente'
        elif self.eh_tecnico_administrativo:
            return 'tecnico_administrativo'
        elif self.eh_estagiario:
            return 'estagiario'
        return 'indefinida'

    @property
    def categoria_display(self):
        """
        Teoricamente pode retornar 3 strings:
            ['Técnico-administrativo', 'Docente', 'ESTAGIARIO']
        """
        if self.eh_docente:
            return 'Docente'
        elif self.eh_tecnico_administrativo:
            return 'Técnico-administrativo'
        elif self.eh_estagiario:
            return 'Estagiário'
        return 'Indefinida'

    @property
    def ocorrencias(self):
        return self.servidorocorrencia_set.all()

    @property
    def ocorrencias_display(self):
        return '<br>'.join(
            [
                '{}: {} - {}'.format(so.ocorrencia.grupo_ocorrencia.nome, so.ocorrencia.nome, [so.data.strftime('%d/%m/%Y') if so else ''][0])
                for so in self.ocorrencias
            ]
        )

    @property
    def afastamentos(self):
        return self.servidorafastamento_set.filter(cancelado=False)

    @property
    def afastamentos_para_capacitacao_strictu_sensu(self):
        return self.afastamentos.filter(afastamento__codigo=AfastamentoSiape.AFASTAMENTO_STRICTU_SENSU)

    @property
    def afastamentos_para_capacitacao_strictu_sensu_hoje(self):
        hoje = get_datetime_now().date()
        return self.afastamentos.filter(afastamento__codigo=AfastamentoSiape.AFASTAMENTO_STRICTU_SENSU, data_inicio__lte=hoje, data_termino__gte=hoje)

    @property
    def tempo_afastado_para_capacitacao_strictu_sensu(self):
        tempo = datetime.timedelta(0)
        hoje = get_datetime_now().date()
        if self.afastamentos_para_capacitacao_strictu_sensu.exists():
            for afastamento in self.afastamentos_para_capacitacao_strictu_sensu:
                data_fim = afastamento.data_termino
                if afastamento.data_termino >= hoje:
                    data_fim = hoje
                tempo += data_fim - afastamento.data_inicio

        return tempo

    @property
    def ultimo_afastamento_para_capacitacao_strictu_sensu(self):
        if self.afastamentos_para_capacitacao_strictu_sensu.exists():
            return self.afastamentos_para_capacitacao_strictu_sensu.latest('data_termino')
        return None

    @property
    def dois_anos_apos_ultimo_afastamento_para_capacitacao_strictu_sensu(self):
        ultimo_afastamento = self.ultimo_afastamento_para_capacitacao_strictu_sensu
        if ultimo_afastamento:
            return ultimo_afastamento.data_termino + relativedelta(years=2)
        return None

    @property
    def afastamentos_para_capacitacao_3_meses(self):
        return self.afastamentos.filter(afastamento__codigo=AfastamentoSiape.LICENCA_CAPACITACAO_3_MESES)

    @property
    def ultimo_afastamento_para_capacitacao_3_meses(self):
        if self.afastamentos_para_capacitacao_3_meses.exists():
            return self.afastamentos_para_capacitacao_3_meses.latest('data_termino')
        return None

    @property
    def dois_anos_apos_ultimo_afastamento_para_capacitacao_3_meses(self):
        ultimo_afastamento = self.ultimo_afastamento_para_capacitacao_3_meses
        if ultimo_afastamento:
            return ultimo_afastamento.data_termino + relativedelta(years=2)
        return None

    @property
    def total_dias_afastado_interrompe_pagamento(self, data_inicio=None, data_fim=None):
        hoje = get_datetime_now().date()
        if not data_inicio:
            data_inicio = self.data_inicio_exercicio_no_cargo
        if not data_fim:
            data_fim = hoje
        afastamentos = self.afastamentos.filter(
            afastamento__interrompe_pagamento=True, data_inicio__gte=data_inicio, data_termino__lte=data_fim, cancelado=False
        )
        total_dias_afastamentos = datetime.timedelta(0)

        for afastamento in afastamentos:
            afastamento_data_fim = afastamento.data_termino
            afastamento_data_inicio = afastamento.data_inicio
            if afastamento_data_inicio < data_inicio:
                afastamento_data_inicio = data_inicio
            if afastamento_data_fim > data_fim:
                afastamento_data_fim = data_fim
            total_dias_afastamentos += (afastamento_data_fim - afastamento_data_inicio) + datetime.timedelta(1)

        # aplica os afastamentos ao tempo calculado, NÃO considerando o fator
        return total_dias_afastamentos

    """
    # Afastamentos que interrompem tempo de serviço no período
    """

    def dados_afastamentos_interrompem_tempo_servico(self, data_inicio, data_fim, ids_ignorar=None):
        if ids_ignorar is None:
            ids_ignorar = []
        if data_inicio is None or data_fim is None:
            return None
        #
        afastamentos_inicio_no_periodo_corrido = self.afastamentos.filter(
            afastamento__interrompe_tempo_servico=True, data_inicio__gte=data_inicio, data_inicio__lte=data_fim
        )
        #
        afastamentos_termino_no_periodo_corrido = self.afastamentos.filter(
            afastamento__interrompe_tempo_servico=True, data_termino__gte=data_inicio, data_termino__lte=data_fim
        )
        #
        afastamentos_considerados = afastamentos_inicio_no_periodo_corrido | afastamentos_termino_no_periodo_corrido
        #
        total_dias_afastado = 0
        id_afastamentos = []
        dados = {'afastamentos': []}
        for sa in afastamentos_considerados.exclude(id__in=ids_ignorar).distinct():
            if sa.data_termino:
                total = (sa.data_termino - sa.data_inicio).days + 1
                dados['afastamentos'].append(
                    {
                        'codigo': sa.afastamento.codigo,
                        'sigla': sa.afastamento.sigla,
                        'nome': sa.afastamento.nome,
                        'data_inicio': sa.data_inicio,
                        'data_termino': sa.data_termino,
                        'dias_afastamento': total,
                    }
                )
                id_afastamentos.append(sa.id)
                total_dias_afastado += total
        # se não tiver dias para retornar, retorna Nulo
        if total_dias_afastado == 0:
            return None
        #
        dados.update({'total_dias': total_dias_afastado, 'afastamentos_ids': id_afastamentos})
        #
        return dados

    """
    # Afastamentos que interferem no efetivo exercício após uma certa quantidade de dias
    # - isso significa que o servidor pode ter uma certa quantidade de dias desses afastamento e um determinado período, após isso, cada dia
    # extra será acrescido na data final de progressão
    """

    def dados_afastamentos_efetivo_exercicio_30_dias(self, data_inicio, data_fim, ids_ignorar=None):
        if ids_ignorar is None:
            ids_ignorar = []
        DIAS_EFETIVO_EXERCICIO = 30
        inicio = data_inicio
        fim = data_fim
        codigos_afastamento = self._get_afastamentos_efetivo_exercicio_qtd_dias(DIAS_EFETIVO_EXERCICIO)

        # só entra se o servidor em questão tiver afastamentos no período passado
        if codigos_afastamento:
            dados = {}
            observacoes_list = []
            ids_afastamentos = []
            pv_inicio = inicio - timedelta(days=365)
            pv_fim = inicio
            delta_periodo_completo = fim - pv_inicio  # para calcular o delta, vamos andar até o fim da data fim
            calc_pv_inicio = pv_inicio
            calc_pv_fim = pv_fim
            lista_dias_afetados = []

            # selecionando todos os afastamentos dentro do período de verificação (PV)
            qs_afastamentos = self.afastamentos.filter(
                data_termino__gte=pv_inicio, data_inicio__lte=fim, afastamento__codigo__in=codigos_afastamento, desconsiderar_regra_30_dias=False
            )

            list_afastamentos = []
            list_dias_afastamentos = []
            for afastamento in qs_afastamentos.exclude(id__in=ids_ignorar):
                ids_afastamentos.append(afastamento.id)
                dict_afastamento = {
                    'data_inicio': afastamento.data_inicio,
                    'data_termino': afastamento.data_termino,
                    'servidor_afastamento': afastamento,
                }
                d = (afastamento.data_termino - afastamento.data_inicio).days + 1
                for dia_afast in range(d):
                    list_dias_afastamentos.append(afastamento.data_inicio + datetime.timedelta(days=dia_afast))
                list_afastamentos.append(dict_afastamento)

            for num_dia in range(1, delta_periodo_completo.days + 1):  # não somar mais 1, fica só 364 dias :/
                dias = 0
                # verifica se o dia da vez tem um afastamento. em caso negativo, passa para o próximo
                check_dia = calc_pv_fim  # dia da vez
                #
                if check_dia in list_dias_afastamentos:
                    #
                    la = []
                    for i in list_afastamentos:
                        delta = 0
                        # verificando se os dias do afastamento será integral na contagem
                        if i.get('data_inicio') >= calc_pv_inicio and i.get('data_termino') <= calc_pv_fim:
                            delta = i.get('data_termino') - i.get('data_inicio')
                            dias += delta.days + 1
                            la.append(i.get('servidor_afastamento'))
                        else:
                            # afastamentos onde nem todos os dias serão contabilizados
                            if i.get('data_inicio') < calc_pv_inicio and i.get('data_termino') >= calc_pv_inicio:
                                delta = i.get('data_termino') - calc_pv_inicio
                                dias += delta.days + 1
                                la.append(i.get('servidor_afastamento'))
                            if i.get('data_termino') > calc_pv_fim and i.get('data_inicio') <= calc_pv_fim:
                                delta = calc_pv_fim - i.get('data_inicio')
                                dias += delta.days + 1
                                la.append(i.get('servidor_afastamento'))
                    #
                    if dias > 30:
                        dict_obs = {'data_afetada': check_dia, 'qtd_dias': dias, 'lista_afastamentos': la}
                        observacoes_list.append(dict_obs)
                        lista_dias_afetados.append(check_dia)
                # andando com o período de verificação
                calc_pv_inicio = pv_inicio + timedelta(days=num_dia)
                calc_pv_fim = pv_fim + timedelta(days=num_dia)
            dados.update(
                {
                    'afastamentos_ids': ids_afastamentos,
                    'observacoes': observacoes_list,
                }
            )
            return dados
        return None

    """
    # selecionando os afastamentos de acordo com a configuração encontrada com a quantidade de dias limites passado
    """

    def _get_afastamentos_efetivo_exercicio_qtd_dias(self, dias_limite):
        # selecionando a configuração dos afastamentos pela quantidade de dias limite
        AfastamentoSiapeEfetivoExercicio = apps.get_model('rh', 'AfastamentoSiapeEfetivoExercicio')
        config_afastamento = AfastamentoSiapeEfetivoExercicio.objects.filter(
            dias_efetivo_exercicio=dias_limite, situacao=AfastamentoSiapeEfetivoExercicio.SITUACAO_ATIVO
        )
        if config_afastamento.exists():
            config_afastamento = config_afastamento[0]
            lista_codigos_afastamento = []
            for a in config_afastamento.afastamentos.all():
                if a.codigo in self.afastamentos.values_list('afastamento__codigo', flat=True):
                    lista_codigos_afastamento.append(a.codigo)
            return lista_codigos_afastamento
        return []

    @property
    def ultima_progressao_merito_finalizada(self):
        ProcessoProgressao = apps.get_model('progressoes.ProcessoProgressao')
        _ultima_progressao = None
        try:
            _ultima_progressao = self.processoprogressao_set.filter(
                tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO,
                status=ProcessoProgressao.STATUS_FINALIZADO,
            ).latest('pk')
        except ProcessoProgressao.DoesNotExist:
            _ultima_progressao = None
        return _ultima_progressao

    @property
    def media_ultima_progressao(self):
        processo = self.ultima_progressao_merito_finalizada
        return processo.media_processo if processo else None

    @property
    def ultima_mudanca_posicionamento_pca(self):
        for pca in self.pca_set.all().exclude(servidor__cargo_emprego__grupo_cargo_emprego__categoria='docente'):
            try:
                posicionamento_referencia = pca.posicionamentopca_set.filter(eh_capacitacao=False).order_by('-data_inicio_posicionamento_pca').first()
                if posicionamento_referencia:
                    return posicionamento_referencia
            except Exception:
                continue  # vai para o próximo PCA

    def tem_divergencia_datas_progressao_pca(self):
        progressao = self.ultima_progressao_merito_finalizada
        pca = self.ultima_mudanca_posicionamento_pca

        if not progressao or not pca:
            return False

        data_conclusao = progressao.data_fim_contagem_progressao
        data_pca = pca.data_inicio_posicionamento_pca

        return data_conclusao not in {
            data_pca,
            data_pca - timedelta(days=1),
        }

    @property
    def afastamentos_display(self):
        return '<br/>'.join(
            [
                '{}: {} - {}'.format(
                    servidor_afastamento.afastamento.get_tipo_display(),
                    servidor_afastamento.afastamento.nome,
                    [servidor_afastamento.data_inicio.strftime('%d/%m/%Y') if servidor_afastamento else ''][0],
                )
                for servidor_afastamento in self.afastamentos
            ]
        )

    @property
    def data_previsao_estabilidade(self):
        if self.data_inicio_exercicio_no_cargo:
            data_previsao_estabilidade = self.data_inicio_exercicio_no_cargo + relativedelta(years=3)
            if self.total_dias_afastado_interrompe_pagamento:
                data_previsao_estabilidade = data_previsao_estabilidade + self.total_dias_afastado_interrompe_pagamento
            return data_previsao_estabilidade
        return None

    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # data_inicio_no_servico_publico
    @property
    def calcula_inicio_no_servico_publico(self):
        #
        # verificando se existe configuração de exceção
        campo_verificavel = 'data_inicio_servico_publico'
        _qs = ExcecaoDado.objects.filter(servidor=self, tipo_extracao=TipoExtracao.TIPO_SISTEMA, campos__campo=campo_verificavel)
        if _qs.exists():
            # se existir, retorna a informação que já está cadastrada para o servidor, mesmo que seja None
            return self.data_inicio_servico_publico
        #
        so = self.servidorocorrencia_set.filter(subgrupo__descricao__unaccent__icontains='INCLUSAO NO SERVICO PUBLICO').order_by('data')
        if so.exists():
            return so[0].data
        return None

    # data_posse_na_instituicao
    @property
    def calcula_posse_na_instituicao(self):
        # via PCA
        pca = self.pca_set.all().order_by('data_entrada_pca')
        if pca.exists():
            return pca[0].data_entrada_pca

        # via OCORRENCIA
        so = self.servidorocorrencia_set.filter(subgrupo__descricao='INCLUSAO NO ORGAO').order_by('data')
        if so.exists():
            return so[0].data
        return None

    #  data_inicio_exercicio_na_instituicao

    @property
    def calcula_inicio_exercicio_na_instituicao(self):  # início do exercício
        # via PCA
        pca = self.pca_set.all().order_by('data_entrada_pca')
        if pca.exists():
            return pca[0].inicio_exercicio_pca

        # via OCORRENCIA
        so = self.servidorocorrencia_set.filter(subgrupo__descricao='INCLUSAO NO ORGAO').order_by('data')
        if so.exists():
            return so[0].data
        return None

    # data_inicio_exercicio_no_cargo
    @property
    def calcula_inicio_exercicio_no_cargo(self):  # início do exercício no cargo
        #
        # verificando se existe configuração de exceção
        campo_verificavel = 'data_inicio_exercicio_no_cargo'
        _qs = ExcecaoDado.objects.filter(servidor=self, tipo_extracao=TipoExtracao.TIPO_SISTEMA, campos__campo=campo_verificavel)
        if _qs.exists():
            # se existir, retorna a informação que já está cadastrada para o servidor, mesmo que seja None
            return self.data_inicio_exercicio_no_cargo
        #
        # via PCA
        pcas = self.pca_set.filter(servidor_vaga_pca=self.codigo_vaga).order_by('-data_entrada_pca')
        if pcas.exists():
            return pcas[0].inicio_exercicio_pca

        # via OCORRENCIA
        so = self.servidorocorrencia_set.filter(subgrupo__descricao='INCLUSAO NO ORGAO').order_by('data')
        if so.exists():
            return so[0].data
        return None

    # data_posse_no_cargo

    @property
    def calcula_posse_no_cargo(self):  # posse no cargo
        #
        # verificando se existe configuração de exceção
        campo_verificavel = 'data_posse_no_cargo'
        _qs = ExcecaoDado.objects.filter(servidor=self, tipo_extracao=TipoExtracao.TIPO_SISTEMA, campos__campo=campo_verificavel)
        if _qs.exists():
            # se existir, retorna a informação que já está cadastrada para o servidor, mesmo que seja None
            return self.data_posse_no_cargo
        #
        # via PCA
        pcas = self.pca_set.filter(servidor_vaga_pca=self.codigo_vaga).order_by('-data_entrada_pca')
        if pcas.exists():
            return pcas[0].data_entrada_pca

        # via OCORRENCIA
        so = self.servidorocorrencia_set.filter(subgrupo__descricao='INCLUSAO NO ORGAO').order_by('data')
        if so.exists():
            return so[0].data
        return None

    # data_fim_servico_na_instituicao
    @property
    def calcula_fim_servico_na_instituicao(self):
        pca = self.pca_set.all().order_by('-data_entrada_pca')
        existe_pca = pca.exists()
        if existe_pca:
            pca = pca[0]
        ocorrencia_exclusao = self.servidorocorrencia_set.filter(subgrupo__descricao='EXCLUSAO').order_by('-data')
        existe_ocorrencia_exclusao = ocorrencia_exclusao.exists()
        if existe_ocorrencia_exclusao:
            ocorrencia_exclusao = ocorrencia_exclusao[0]

        referencia = 'pca'
        if existe_pca and existe_ocorrencia_exclusao:
            if pca.data_entrada_pca >= ocorrencia_exclusao.data or pca.forma_vacancia_pca:
                referencia = 'pca'
            else:
                referencia = 'ocorrencia'
        elif existe_pca:
            referencia = 'pca'
        else:
            referencia = 'ocorrencia'

        if referencia == 'pca':
            if pca.fim_exercicio_pca_or_None:
                return pca.fim_exercicio_pca_or_None

        elif referencia == 'ocorrencia':
            # via OCORRENCIA
            so_inclusao = (
                self.servidorocorrencia_set.filter(subgrupo__descricao__in=['INCLUSAO NO ORGAO', 'INCLUSAO NO SERVICO PUBLICO'])
                .exclude(ocorrencia__nome='REFORMA ADMINISTRATIVA')
                .order_by('-data')
            )
            so = self.servidorocorrencia_set.filter(subgrupo__descricao='EXCLUSAO').order_by('-data') or self.servidorocorrencia_set.filter(
                ocorrencia__grupo_ocorrencia__nome__unaccent__icontains='EXCLUSAO'
            ).order_by('-data')

            if so.exists() and so_inclusao.exists():
                if self.situacao.codigo in Situacao.situacoes_servidores_de_carreira():
                    if so_inclusao.latest('data').data <= so.latest('data').data:
                        return so[0].data
                else:
                    return so.latest('data').data
        return None

    @property
    def datas_ultimas_progressoes(self):
        datas = []
        for pca in self.pca_set.all():
            try:
                if hasattr(pca, 'prefetched_progressao'):
                    if pca.prefetched_progressao:
                        posicionamento = pca.prefetched_progressao[0]
                    else:
                        continue
                else:
                    # posicionamento mais atual (índice 0 com data em ordem decrescente)
                    posicionamento = pca.posicionamentopca_set.filter(forma_entrada__codigo=FormaProvimentoVacancia.CODIGO_PROGRESSAO).order_by(
                        '-data_inicio_posicionamento_pca'
                    )[0]
            except Exception:
                continue
            datas.append(posicionamento.data_inicio_posicionamento_pca)
        return datas

    @property
    def data_ultima_progressao(self):
        if self.datas_ultimas_progressoes:
            return self.datas_ultimas_progressoes[0]
        return None

    @property
    def aposentadoria(self):
        ServidorOcorrencia = apps.get_model('rh', 'ServidorOcorrencia')
        sos = ServidorOcorrencia.objects.filter(servidor=self, ocorrencia__grupo_ocorrencia__nome__unaccent__icontains='aposent')
        ocorrencias = []
        for so in sos:
            if so.diploma_legal:
                ocorrencias.append(
                    '{}: Diploma: {} - {} - {}, Tipo: {}, {}, Data: {}. '.format(
                        so.ocorrencia.codigo,
                        so.diploma_legal_num,
                        so.diploma_legal.sigla,
                        so.diploma_legal_data,
                        so.ocorrencia.nome,
                        so.ocorrencia.grupo_ocorrencia.nome,
                        so.data.strftime('%d/%m/%Y'),
                    )
                )
            else:
                ocorrencias.append(
                    '{}: Diploma: Não definido, Tipo: {}, {}, Data: {}. '.format(
                        so.ocorrencia.codigo, so.ocorrencia.nome, so.ocorrencia.grupo_ocorrencia.nome, so.data.strftime('%d/%m/%Y')
                    )
                )
        return ''.join(ocorrencias) or 'Sem ocorência de aposentadoria.'

    @property
    def data_aposentadoria(self):
        ServidorOcorrencia = apps.get_model('rh', 'ServidorOcorrencia')
        sos = ServidorOcorrencia.objects.filter(servidor=self, ocorrencia__grupo_ocorrencia__nome__unaccent__icontains='aposent')
        if sos.exists():
            return sos[0].data
        return None

    @property
    def data_aposentadoria_pca(self):
        qs_aposentadoria_pca = self.pca_set.filter(forma_vacancia_pca__descricao__unaccent__icontains='APOSENT').order_by('-data_vacancia_pca')
        if qs_aposentadoria_pca.exists():
            return qs_aposentadoria_pca[0].data_vacancia_pca
        return None

    @property
    def campus_lotacao_siape(self):
        if self.setor_lotacao:
            return self.setor_lotacao.uo
        return None

    @property
    def campus_exercicio_siape(self):
        if self.setor_exercicio:
            return self.setor_exercicio.uo
        return None

    @property
    def ferias(self):
        return ', '.join(self.get_ferias())  # string contendo as férias separadas por ','

    @property
    def ferias_lista(self):
        return self.get_ferias()  # lista contendo as férias

    @property
    def jornada_trabalho_servidor_pca(self):
        jornada = ''
        if self.pca_set.all().exists():
            pca = self.pca_set.all().latest('data_entrada_pca')
            if pca.jornadatrabalhopca_set.all().exists():
                jornada = pca.jornadatrabalhopca_set.all().latest('data_inicio_jornada_trabalho_pca').qtde_jornada_trabalho_pca
        return jornada

    @property
    def is_historico_setor_com_pendencias(self):
        historico_siape = self.historico_setor_siape()
        historico_suap = self.historico_setor_suap()
        #
        sem_setor_siape = not historico_siape.exists()
        sem_setor_suap = not historico_suap.exists() or self.setor is None
        #
        if historico_siape.exists() and historico_suap.exists():
            setor_siape = historico_siape.order_by('-data_inicio_setor_lotacao')[0].setor_exercicio
            setor_suap = historico_suap.order_by('-data_inicio_no_setor')[0].setor
            setor_historico_suap_com_campus_invalido = not (
                setor_suap and setor_siape and setor_siape.uo and setor_siape.uo.equivalente and setor_siape.uo.equivalente == setor_suap.uo
            )
        else:
            setor_historico_suap_com_campus_invalido = True
        #
        if historico_suap.exists():
            setor_atual_difere_do_setor_historico_suap = self.setor.id != historico_suap.order_by('-data_inicio_no_setor')[0].setor.id
        else:
            setor_atual_difere_do_setor_historico_suap = True
        #
        return sem_setor_siape or sem_setor_suap or setor_historico_suap_com_campus_invalido or setor_atual_difere_do_setor_historico_suap

    @property
    def papeis(self):
        return self.get_vinculo().papel_set.all()

    @property
    def papeis_ativos(self):
        hoje = get_datetime_now().date()
        papeis_datas_menores_hoje = self.get_vinculo().papel_set.filter(data_inicio__lte=hoje)
        return papeis_datas_menores_hoje.filter(data_fim__isnull=True) | papeis_datas_menores_hoje.filter(data_fim__gte=hoje)

    @property
    def esta_em_pgd(self):
        return estah_no_pgd_hoje_pgd1_pgd2(self)[0]

    def estah_horario_atendimento_pgd(self):
        em_horario_atendimento = False
        esta_em_pgd, adesao_pgd = estah_no_pgd_hoje_pgd1_pgd2(self)
        if esta_em_pgd:
            from pgd2.models import PlanoIndividualTrabalho, PlanoIndividualTrabalhoAtendimento

            dia = datetime.datetime.today()
            hora = dia.time()
            pits_da_adesao = PlanoIndividualTrabalho.objects.filter(adesao=adesao_pgd).exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
            horarios_atendimento_pgd = PlanoIndividualTrabalhoAtendimento.objects.filter(pit__in=pits_da_adesao, homologado=True, data=dia)
            em_horario_atendimento = horarios_atendimento_pgd.filter(hora_inicio__lte=hora, hora_final__gte=hora).exists()
        return em_horario_atendimento

    def eh_reitor(self, na_data=None):
        if not na_data:
            na_data = datetime.date.today()
        return self.historico_funcao(na_data, na_data).filter(funcao__codigo=Funcao.CODIGO_CD, nivel__in=('1', '0001')).exists()

    def tempo_no_servico_publico(self):
        if self.data_inicio_servico_publico:
            return (self.data_fim_servico_na_instituicao or datetime.date.today()) - self.data_inicio_servico_publico + datetime.timedelta(1)
        return None

    def tempo_servico_na_instituicao(self):
        if self.data_inicio_exercicio_na_instituicao:
            return (self.data_fim_servico_na_instituicao or datetime.date.today()) - self.data_inicio_exercicio_na_instituicao + datetime.timedelta(1)
        return None

    def tempo_servico_no_cargo(self, data_referencia=None):
        if not data_referencia:
            data_referencia = datetime.date.today()
        if data_referencia > datetime.date.today():
            data_referencia = datetime.date.today()
        if self.data_inicio_exercicio_no_cargo:
            if self.data_fim_servico_na_instituicao and data_referencia < self.data_fim_servico_na_instituicao:
                return data_referencia - self.data_inicio_exercicio_no_cargo
            return (self.data_fim_servico_na_instituicao or data_referencia) - self.data_inicio_exercicio_no_cargo + datetime.timedelta(1)
        return None

    def tempo_servico_na_instituicao_via_pca(self, ficto=False, data_referencia=None):
        # calcula o TEMPO REAL ou TEMPO FICTO
        # retorna um timedelta
        if not data_referencia:
            data_referencia = datetime.date.today()
        tempo_servico = datetime.timedelta(0)  # em timedelta
        # calcula o tempo ficto (considera o fator do regime juridico)
        for pca in self.pca_set.all():
            tempo_servico += pca.tempo_servico_pca(ficto, data_referencia)
        return tempo_servico

    def tempo_servico_no_cargo_via_pca(self, ficto=False, data_referencia=None):
        tempo_servico = datetime.timedelta(0)  # em timedelta
        if not data_referencia:
            data_referencia = datetime.date.today()
        for pca in self.pca_set.filter(servidor_vaga_pca=self.codigo_vaga):
            tempo_servico += pca.tempo_servico_pca(ficto, data_referencia)
        return tempo_servico

    def tempo_servico_interrompido(self, data_referencia=None):
        tempo_servico = datetime.timedelta(0)  # em timedelta
        if not data_referencia:
            data_referencia = datetime.date.today()
        for pca in self.pca_set.all():
            tempo_servico += pca.tempo_servico_interrompido_pca(data_referencia)
        return tempo_servico

    def get_ferias(self):
        """
        Modelo novo baseado em suap.ferias.models.Ferias.
        Modelo antigo baseado em suap.rh.models.ServidorOcorrencia
            Executar o script no banco: ServidorOcorrencia.objects.filter(ocorrencia__nome__unaccent__icontains='ferias').delete()
        """

        # Ano -> Períodos: dd/mm/aaaa até dd/mm/aaaa, dd/mm/aaaa até dd/mm/aaaa, dd/mm/aaaa até dd/mm/aaaa. Interrupções: 1ª dd/mm/aaaa - cont. dd/mm/aaaa até dd/mm/aaaa, ...
        servidor_ferias_lista = []
        if 'ferias' in settings.INSTALLED_APPS:
            servidor_ferias = self.ferias_set.all()
            # a lista que será retornada pela propriedade
            for ferias in servidor_ferias:
                servidor_ferias_str = f'{ferias.ano} -> Períodos: '

                if ferias.data_inicio_periodo1:
                    servidor_ferias_str += '{} até {}'.format(
                        ferias.data_inicio_periodo1.strftime('%d/%m/%Y'), ferias.data_fim_periodo1.strftime('%d/%m/%Y')
                    )
                if ferias.data_inicio_periodo2:
                    servidor_ferias_str += ', {} até {}'.format(
                        ferias.data_inicio_periodo2.strftime('%d/%m/%Y'), ferias.data_fim_periodo2.strftime('%d/%m/%Y')
                    )
                if ferias.data_inicio_periodo3:
                    servidor_ferias_str += ', {} até {}'.format(
                        ferias.data_inicio_periodo3.strftime('%d/%m/%Y'), ferias.data_fim_periodo3.strftime('%d/%m/%Y')
                    )
                servidor_ferias_str += '. '

                interrupcoes = ferias.interrupcaoferias_set.all()
                for idx, interrupcao in enumerate(interrupcoes):
                    if idx == 0:
                        servidor_ferias_str += 'Interrupções -> '
                    if idx > 0:
                        servidor_ferias_str += ', '
                    servidor_ferias_str += '{}ª {} - cont. {} até {}'.format(
                        idx + 1,
                        interrupcao.data_interrupcao_periodo and interrupcao.data_interrupcao_periodo.strftime('%d/%m/%Y') or '-',
                        interrupcao.data_inicio_continuacao_periodo and interrupcao.data_inicio_continuacao_periodo.strftime('%d/%m/%Y') or '-',
                        interrupcao.data_fim_continuacao_periodo and interrupcao.data_fim_continuacao_periodo.strftime('%d/%m/%Y') or '-',
                    )
                servidor_ferias_lista.append(servidor_ferias_str)
        return servidor_ferias_lista

    def get_matriculas_por_cpf(self):
        return Servidor.objects.filter(pessoa_fisica__cpf=self.pessoa_fisica.cpf).exclude(id=self.id)

    def jornada_trabalho_servidor(self, data=None):
        """
        Obtém a jornada de trabalho do servidor em certa data.

        Retorna uma instância de rh.JornadaTrabalho ou rh.JornadaTrabalhoPersonalizada.
        """

        if not data:
            data = datetime.date.today()

        jornada_funcao = self.get_jornadas_funcoes_dict(data_inicio=data, data_fim=data)[0].get(data)
        if jornada_funcao:
            return jornada_funcao

        jornada_setor = {}
        if self.cargo_emprego and self.cargo_emprego.grupo_cargo_emprego.categoria == 'tecnico_administrativo':
            jornada_setor = self.get_jornadas_por_setores_dict(data_inicio=data, data_fim=data).get(data)
        jornada_servidor = self.get_jornadas_servidor_dict(data_inicio=data, data_fim=data).get(data)

        jornada_funcionario = self.get_jornadas_por_funcionario_dict(data_inicio=data, data_fim=data).get(data)
        if jornada_funcionario:
            return jornada_funcionario

        if jornada_setor and jornada_servidor:
            return (
                jornada_setor if jornada_setor.get_jornada_trabalho_diaria() <= jornada_servidor.get_jornada_trabalho_diaria() else jornada_servidor
            )

        return jornada_setor or jornada_servidor

    # obtém a jornada de trabalho do servidor em um período
    # retorna um dicionario com os dias e as jornadas de trabalho
    def get_jornadas_servidor_dict(self, data_inicio, data_fim):
        jornadas_trabalho_servidor = {}

        if self.eh_estagiario:
            for dia in datas_entre(data_inicio, data_fim):
                jornadas_trabalho_servidor[dia] = self.jornada_trabalho
            return jornadas_trabalho_servidor

        jornadas_trabalhos_pca = JornadaTrabalhoPCA.objects.filter(pk__in=self.pca_set.all().values_list('jornadatrabalhopca', flat=True))

        jornadas_de_trabalho = {}  # {nome: instância, ...}

        for jornada in jornadas_trabalhos_pca:
            data_inicio_jornada = jornada.data_inicio_jornada_trabalho_pca
            data_fim_jornada = jornada.data_fim_jornada_trabalho_pca
            if data_inicio_jornada <= data_inicio:
                data_inicio_jornada = data_inicio
            if not data_fim_jornada or data_fim_jornada >= data_fim:
                data_fim_jornada = data_fim
            for dia in datas_entre(data_inicio_jornada, data_fim_jornada):
                if jornada.qtde_jornada_trabalho_pca == '99':
                    nome_jornada = 'DEDICACAO EXCLUSIVA'
                else:
                    nome_jornada = f'{jornada.qtde_jornada_trabalho_pca} HORAS SEMANAIS'

                jornadas_trabalho_servidor[dia] = JornadaTrabalho.get_jornada(nome_jornada)

                if nome_jornada not in jornadas_de_trabalho:
                    jornadas_de_trabalho[nome_jornada] = JornadaTrabalho.get_jornada(nome_jornada)

                jornadas_trabalho_servidor[dia] = jornadas_de_trabalho[nome_jornada]

        # procura ocorrências de jornada de trabalho em processos de ch reduzida
        # servidor_jornadas_via_ch_reduzida = HorarioSemanal.get_jornadas_servidor_horario(self, data_inicio, data_fim)
        # jornadas_trabalho_servidor.update(servidor_jornadas_via_ch_reduzida)
        return jornadas_trabalho_servidor

    def get_jornadas_extraordinarias_servidor_dict(self, data_inicio, data_fim):
        return HorarioSemanal.get_jornadas_servidor_horario(self, data_inicio, data_fim)

    # obtém a jornada de trabalho de um funcionario cadastradas pela chefia analisando o seu historico setor em um período
    # retorna um dicionario com os dias e as jornadas de trabalho
    def get_jornadas_por_funcionario_dict(self, data_inicio, data_fim):
        jornadas_funcionarios = {}
        historico_setor = self.historico_setor_suap(data_inicio, data_fim)
        if historico_setor.exists():
            for hist_setor in historico_setor:
                data_inicio_setor = hist_setor.data_inicio_no_setor
                data_fim_setor = hist_setor.data_fim_no_setor
                if data_inicio_setor <= data_inicio:
                    data_inicio_setor = data_inicio
                if not data_fim_setor or data_fim_setor >= data_fim:
                    data_fim_setor = data_fim

                jornada_trabalho_funcionario_no_setor = self.jornada_trabalho_por_periodo_dict(hist_setor.setor, data_inicio_setor, data_fim_setor)

                for dia in datas_entre(data_inicio_setor, data_fim_setor):
                    jornadas_funcionarios[dia] = jornada_trabalho_funcionario_no_setor.get(dia)
        return jornadas_funcionarios

    #
    # obtém a jornada de trabalho de um servidor analisando o seu historico setor em um período
    # retorna um dicionario com os dias e as jornadas de trabalho
    #
    def get_jornadas_por_setores_dict(self, data_inicio, data_fim):
        jornadas_setores = {}
        historico_setor = self.historico_setor_suap(data_inicio, data_fim).select_related('setor')
        for hist_setor in historico_setor:
            data_inicio_setor = hist_setor.data_inicio_no_setor
            data_fim_setor = hist_setor.data_fim_no_setor
            if data_inicio_setor <= data_inicio:
                data_inicio_setor = data_inicio
            if not data_fim_setor or data_fim_setor >= data_fim:
                data_fim_setor = data_fim

            jornada_trabalho_setor = hist_setor.setor.jornada_trabalho_por_periodo_dict(data_inicio_setor, data_fim_setor)
            for dia in datas_entre(data_inicio_setor, data_fim_setor):
                jornadas_setores[dia] = jornada_trabalho_setor.get(dia)
        return jornadas_setores

    def get_jornadas_funcoes_dict(self, data_inicio, data_fim, apenas_funcoes_de_chefia=True):
        from .servidor_funcao import ServidorFuncaoHistorico

        """
        Obtém a jornada de trabalho de um servidor analisando o seu historico de funcoes em um período

        Retorna uma tupla com 3 elementos:
            (1) os dias e suas jornadas de trabalho (None ou 1 jornada de trabalho por dia);
            (2) os dias e suas funções (0, 1 ou mais funções por dia);
            (3) a queryset de todas as funções envolvidas;

        Pode haver dias no período que não terá informações de jornadas de tabalhado relacionadas à função.

        Ao analisar cada dia, determina-se suas jornadas de função (pode envolver várias funções) e
        as funções relacionadas (nem todas as funções do período são aplicadas a um dia específico desse período).
        """

        if self.eh_estagiario:
            return {}, ServidorFuncaoHistorico.objects.none(), {}

        dias_jornadas = {}
        dias_funcoes = {}
        qs_funcoes = self.historico_funcao(data_inicio=data_inicio, data_fim=data_fim)

        if apenas_funcoes_de_chefia:
            qs_funcoes = qs_funcoes.filter(Q(funcao__codigo__in=Funcao.get_codigos_funcao_chefia()))

        jornada_quarenta_horas = JornadaTrabalho.get_jornada('40 HORAS SEMANAIS')

        for dia in datas_entre(data_inicio, data_fim):
            if dia not in dias_jornadas:
                dias_jornadas[dia] = None

            if dia not in dias_funcoes:
                dias_funcoes[dia] = []

            for funcao in qs_funcoes:
                if funcao.data_fim_funcao:
                    funcao_abranje_o_dia = funcao.data_inicio_funcao <= dia and funcao.data_fim_funcao >= dia
                else:
                    funcao_abranje_o_dia = funcao.data_inicio_funcao <= dia

                if funcao_abranje_o_dia:
                    funcao_ch_semanal = funcao.funcao.ch_semanal  # ch quaisquer informada manualmente no cadastro da função (se for o caso)

                    if funcao_ch_semanal:
                        jornada_funcao = JornadaTrabalhoPersonalizada(ch_semana=funcao_ch_semanal)
                    else:
                        jornada_funcao = jornada_quarenta_horas

                    dias_jornadas[dia] = (
                        jornada_funcao  # ATT: o dia recebe a jornada da última função processada aqui (e se já tiver jornada no dia?)
                    )
                    dias_funcoes[dia].append(funcao)

        # procura ocorrências de jornada de trabalho em processos de ch reduzida
        servidor_jornadas_via_ch_reduzida = HorarioSemanal.get_jornadas_servidor_horario(self, data_inicio, data_fim)
        dias_jornadas.update(servidor_jornadas_via_ch_reduzida)

        return dias_jornadas, dias_funcoes, qs_funcoes

    def get_jornadas_periodo_dict(self, data_inicio, data_fim) -> tuple[dict, dict, dict]:
        """
        Obtém a jornada de trabalho de um servidor em um período.

        Retorna 3 dicionários:
            - dias e jornadas
            - dias e motivos das jornadas (motivo = texto estático informativo)
            - dias e origens das jornadas (origem = texto estático informativo)
        """

        jornada_padrao = JornadaTrabalho.get_jornada('40 HORAS SEMANAIS')

        jornadas = {}
        motivos_jornadas = {}
        origens_jornadas = {}

        dias_jornadas_funcoes = {}
        dias_historico_funcoes = {}
        _historico_funcoes = ServidorFuncaoHistorico.objects.none()
        jornadas_setores = {}

        if self.eh_tecnico_administrativo:
            dias_jornadas_funcoes, dias_historico_funcoes, _historico_funcoes = self.get_jornadas_funcoes_dict(
                data_inicio, data_fim, apenas_funcoes_de_chefia=False
            )
            jornadas_setores = self.get_jornadas_por_setores_dict(data_inicio, data_fim)
        elif self.eh_docente:
            dias_jornadas_funcoes, dias_historico_funcoes, _historico_funcoes = self.get_jornadas_funcoes_dict(
                data_inicio, data_fim, apenas_funcoes_de_chefia=False
            )

        jornadas_servidor = self.get_jornadas_servidor_dict(data_inicio, data_fim)
        jornadas_extraordinarias = self.get_jornadas_extraordinarias_servidor_dict(data_inicio, data_fim)

        for dia in datas_entre(data_inicio, data_fim):
            if jornadas_extraordinarias.get(dia):
                jornadas[dia] = jornadas_extraordinarias.get(dia)
                motivos_jornadas[dia] = 'Carga horária Excepcional'
                origens_jornadas[dia] = 'Jornada do Servidor'

            elif dias_jornadas_funcoes.get(dia):
                jornadas[dia] = dias_jornadas_funcoes.get(dia)

                historico_funcoes_dia = dias_historico_funcoes.get(dia)
                historico_funcoes_dia_de_chefia = [h_funcao for h_funcao in historico_funcoes_dia if h_funcao.funcao.eh_funcao_chefia]

                if historico_funcoes_dia_de_chefia:
                    motivos_jornadas[dia] = 'Exerce Cargo de Chefia'
                    origens_jornadas[dia] = 'Jornada do Cargo/Função de Chefia'
                else:
                    motivos_jornadas[dia] = 'Exerce Função sem Chefia'
                    historico_funcoes_dia_com_ch_semanal_especifica = [
                        h_funcao for h_funcao in historico_funcoes_dia if h_funcao.funcao.ch_semanal is not None
                    ]

                    if historico_funcoes_dia_com_ch_semanal_especifica:
                        origens_jornadas[dia] = 'Jornada do Cargo/Função sem Chefia'
                    else:
                        origens_jornadas[dia] = 'Jornada do Servidor'

            elif jornadas_setores.get(dia) or jornadas_servidor.get(dia):
                if jornadas_setores.get(dia) and jornadas_servidor.get(dia):
                    if jornadas_setores.get(dia).get_jornada_trabalho_diaria() < jornadas_servidor.get(dia).get_jornada_trabalho_diaria():
                        jornadas[dia] = jornadas_setores.get(dia)
                        motivos_jornadas[dia] = 'CH Adequada do Setor'
                        origens_jornadas[dia] = 'Jornada do Setor'
                    else:
                        jornadas[dia] = jornadas_servidor.get(dia)
                        motivos_jornadas[dia] = 'CH padrão do servidor'
                        origens_jornadas[dia] = 'Jornada do Servidor'
                else:
                    jornadas[dia] = jornadas_setores.get(dia) or jornadas_servidor.get(dia)
                    motivos_jornadas[dia] = 'CH padrão do servidor' if not jornadas_setores.get(dia) else 'CH Adequada do Setor'
                    origens_jornadas[dia] = 'Jornada do Servidor' if not jornadas_setores.get(dia) else 'Jornada do Setor'

            else:
                jornadas[dia] = jornada_padrao
                motivos_jornadas[dia] = 'CH padrão do servidor'
                origens_jornadas[dia] = 'Jornada do Servidor'

        return jornadas, motivos_jornadas, origens_jornadas

    #
    # obtém uma lista do(s) setor(es) SUAP do servidor em certo período
    #
    def setor_suap_servidor_por_periodo(self, data_inicial=None, data_final=None):
        from .servidor_setor import ServidorSetorHistorico

        if (data_inicial is None) and (data_final is None):  # período informado?
            #
            # período não foi informado ... retorna o setor atual
            #
            return [self.setor]
        else:
            #
            # uma das datas pode ser nula
            #
            if data_inicial is None:
                data_inicial = data_final
            elif data_final is None:
                data_final = data_inicial

            #
            # nesse ponto, temos um período válido
            # obtém o(s) setor(es) no período
            #
            if data_inicial != data_final:
                qs_1 = ServidorSetorHistorico.objects.filter(
                    servidor=self,
                    data_inicio_no_setor__lte=data_inicial,
                    data_fim_no_setor__gte=data_inicial,
                    data_fim_no_setor__lte=data_final,
                )  # inicio fora e termino dentro do período (incluindo extremidades)

                qs_2 = ServidorSetorHistorico.objects.filter(
                    servidor=self,
                    data_inicio_no_setor__gt=data_inicial,
                    data_inicio_no_setor__lt=data_final,
                    data_fim_no_setor__lt=data_final,
                )  # inicio dentro e termino dentro do período (nao incluindo extremidades)

                qs_3 = ServidorSetorHistorico.objects.filter(
                    servidor=self, data_inicio_no_setor__lte=data_inicial, data_fim_no_setor__gte=data_final
                )  # inicio fora e termino fora do período (incluindo extremidades)

                qs_4 = ServidorSetorHistorico.objects.filter(
                    servidor=self, data_inicio_no_setor__lte=data_final, data_fim_no_setor__isnull=True
                )  # período com data final não definida

                historicos = (qs_1 | qs_2 | qs_3 | qs_4).distinct()
            else:
                qs_1 = ServidorSetorHistorico.objects.filter(
                    servidor=self, data_inicio_no_setor__lte=data_inicial, data_fim_no_setor__gte=data_final
                )  # data informada dentro do período

                qs_2 = ServidorSetorHistorico.objects.filter(
                    servidor=self, data_inicio_no_setor__lte=data_inicial, data_fim_no_setor__isnull=True
                )  # data inicial antes ou igual a data informada e data final não definida

                historicos = (qs_1 | qs_2).distinct()

            setores = []
            for historico in historicos.select_related('setor'):
                if historico.setor not in setores:
                    setores.append(historico.setor)

            return setores

    def jornada_trabalho_por_periodo_dict(self, setor, data_inicio, data_fim):
        from .carga_horaria import CargaHorariaReduzida

        jornadas = {}
        qs_1 = CargaHorariaReduzida.objects.filter(servidor=self, data_inicio__lte=data_fim, data_termino__gte=data_inicio)
        qs_2 = CargaHorariaReduzida.objects.filter(servidor=self, data_inicio__lte=data_fim, data_termino__isnull=True)
        qs = (qs_1 | qs_2).distinct()
        jornadas = {}
        for jornada_historico in qs:
            data_inicio_jornada = jornada_historico.data_inicio
            data_fim_jornada = jornada_historico.data_termino
            if data_inicio_jornada <= data_inicio:
                data_inicio_jornada = data_inicio
            if not data_fim_jornada or data_fim_jornada >= data_fim:
                data_fim_jornada = data_fim
            for dia in datas_entre(data_inicio_jornada, data_fim_jornada):
                jornadas[dia] = jornada_historico.nova_jornada

        return jornadas

    # verifica qual o setor do servidor em um dia específico
    def setor_suap_servidor_no_dia(self, dia):
        qs_setor = self.servidorsetorhistorico_set.filter(data_inicio_no_setor__lte=dia)
        if qs_setor.exists():
            # verificando data final no setor
            qs_setor = qs_setor.filter(data_fim_no_setor__gte=dia) | qs_setor.filter(data_fim_no_setor__isnull=True)
            if qs_setor.exists():
                return qs_setor[0].setor
        return None

    def historico_setor_suap(self, data_inicio=None, data_fim=None):
        if not data_inicio:
            data_inicio = self.calcula_inicio_exercicio_na_instituicao or datetime.date.today()
        if not data_fim:
            data_fim = datetime.date.today()
        #
        historico_setor = ServidorSetorHistorico.objects.filter(
            servidor=self, data_inicio_no_setor__lte=data_fim, data_fim_no_setor__gte=data_inicio
        ) | ServidorSetorHistorico.objects.filter(servidor=self, data_inicio_no_setor__lte=data_fim, data_fim_no_setor__isnull=True)
        return historico_setor

    def historico_setor_siape(self, data_inicio=None, data_fim=None):
        if not data_inicio:
            data_inicio = self.calcula_inicio_exercicio_na_instituicao or datetime.date.today()
        if not data_fim:
            data_fim = datetime.date.today()
        #
        historico_setor = ServidorSetorLotacaoHistorico.objects.filter(
            servidor=self, data_inicio_setor_lotacao__lte=data_fim, data_fim_setor_lotacao__gte=data_inicio
        ) | ServidorSetorLotacaoHistorico.objects.filter(servidor=self, data_inicio_setor_lotacao__lte=data_fim, data_fim_setor_lotacao__isnull=True)
        return historico_setor

    def historico_funcao(self, data_inicio=None, data_fim=None, queryset_base: QuerySet[ServidorFuncaoHistorico] = None):
        """
        Histórico de função do Servidor em um período
        procura a interseção entre período informado e os períodos das funções

        periodo         |--------------------------------|

        func_1   |--------------------------------------------|
        func_2              |--------------------------------------------|
        func_3   |------------------------------|
        func_4             |-----------------------|

        ATT: tratar a data_fim=None das funções.

        func_1_2_3_4 = func.data_inicial <= data_periodo_final and func.data_final >= data_periodo_inicial
        """
        if not data_inicio:
            data_inicio = self.data_inicio_exercicio_na_instituicao or datetime.date.today()
        if not data_fim:
            data_fim = datetime.date.today()

        qs_base = queryset_base or ServidorFuncaoHistorico.objects.select_related(
            'servidor',
            'funcao',
            'atividade',
            'setor',
            'setor_suap',
        ).filter(servidor=self)

        historico_funcao = qs_base.filter(
            Q(data_inicio_funcao__lte=data_fim, data_fim_funcao__gte=data_inicio) | Q(data_inicio_funcao__lte=data_fim, data_fim_funcao__isnull=True)
        )

        return historico_funcao.distinct()

    @cached_property
    def historico_funcao_ativa(self):
        from .servidor_funcao import ServidorFuncaoHistorico

        hoje = get_datetime_now().date()
        qs_filter = [Q(data_fim_funcao__gte=hoje), Q(data_fim_funcao__isnull=True)]
        return ServidorFuncaoHistorico.objects.filter(servidor=self, data_inicio_funcao__lte=hoje).filter(reduce(operator.or_, qs_filter))

    @staticmethod
    def importar_funcao_servidor(verbosity=3):
        servidores = Servidor.objects.filter(cargo_emprego__isnull=False, ativo=True)
        estagiarios = Servidor.objects.filter(situacao__codigo__in=Situacao.situacoes_siape_estagiarios(), ativo=True)
        if verbosity:
            servidores = tqdm.tqdm(servidores)
            estagiarios = tqdm.tqdm(estagiarios)
        for servidor in servidores:
            try:
                servidor._definir_papel_do_servidor()
            except Exception as e:
                if verbosity > 1:
                    log.warning(f'Erro ao definir papel do servidor {servidor.matricula}: {e}')

        for estagiario in estagiarios:
            try:
                estagiario._definir_papel_do_estagiario()
            except Exception as e:
                if verbosity > 1:
                    log.warning(f'Erro ao definir papel do estagiario {estagiario.matricula}: {e}')

    def _definir_papel_do_servidor(self):
        if Papel.objects.filter(papel_content_id__isnull=True).exists():
            raise Exception(
                'Existem registros de Papel sem CargoEmprego ou Funcao definidos. '
                'Execute o command "importar_funcao_servidor_atualizar_genericfk" para resolver '
                'o problema.'
            )

        data_inicio = self.cargo_emprego_data_ocupacao or self.data_inicio_exercicio_no_cargo or get_datetime_now()
        if data_inicio and self.cargo_emprego:
            kwargs = {
                'detalhamento': self.cargo_emprego.nome,
                'portaria': '',
                'data_fim': self.cargo_emprego_data_saida,
                'tipo_papel': Papel.TIPO_PAPEL_CARGO,
                'descricao': self.cargo_emprego.nome,
            }
            _papel_cargo, _criou = Papel.objects.update_or_create(
                vinculo=self.get_vinculo(),
                data_inicio=data_inicio,
                papel_content_type=ContentType.objects.get_for_model(self.cargo_emprego),
                papel_content_id=self.cargo_emprego.id,
                defaults=kwargs,
            )

        hoje = get_datetime_now().date()
        if self.historico_funcao(hoje, hoje).exists():
            for funcao in self.historico_funcao(hoje, hoje).all():
                funcao.save()

    def _definir_papel_do_estagiario(self):
        if Papel.objects.filter(papel_content_id__isnull=True).exists():
            raise Exception(
                'Existem registros de Papel sem CargoEmprego ou Funcao definidos. '
                'Execute o command "importar_funcao_servidor_atualizar_genericfk" para resolver '
                'o problema.'
            )

        kwargs = {
            'detalhamento': self.situacao.nome,
            'portaria': '',
            'data_fim': self.cargo_emprego_data_saida,
            'tipo_papel': Papel.TIPO_PAPEL_CARGO,
            'descricao': self.situacao.nome,
        }

        data_inicio = self.cargo_emprego_data_ocupacao or self.data_inicio_exercicio_no_cargo or self.data_inicio_exercicio_na_instituicao
        if data_inicio:
            _papel_cargo, _criou = Papel.objects.update_or_create(
                vinculo=self.get_vinculo(),
                data_inicio=data_inicio,
                papel_content_type=ContentType.objects.get_for_model(self.situacao),
                papel_content_id=self.situacao.id,
                defaults=kwargs,
            )

        hoje = get_datetime_now().date()
        if self.historico_funcao(hoje, hoje).exists():
            for funcao in self.historico_funcao(hoje, hoje).all():
                funcao.save()

    def qtd_horas_trabalhadas_gecc(self, ano):
        if 'cursos' in settings.INSTALLED_APPS:
            from cursos.enums import SituacaoCurso, SituacaoParticipante

            qtd_horas = (
                self.participante_set.filter(
                    curso__situacao__in=[
                        SituacaoCurso.FINALIZADO,
                        SituacaoCurso.INICIADO,
                        SituacaoCurso.AGUARDANDO_CADASTRO_EM_FOLHA,
                        SituacaoCurso.CADASTRADO_EM_FOLHA,
                    ],
                    curso__ano_pagamento=ano,
                )
                .exclude(situacao=SituacaoParticipante.NAO_LIBERADO)
                .aggregate(horas=Sum('horas_trabalhada'))
            )

            return qtd_horas.get('horas') or 0
        else:
            return 0

    def get_dados_receita_federal(self):
        from comum.models import APIExterna

        api = APIExterna.PESSOAFISICA
        dados_cidadao = []
        obj = PessoaInfoComplementar.get_instance(self.pessoa_fisica, api, force=False)
        if obj:
            dados_cidadao = obj.informacoes
        info_pessoafisica_rfb = dados_cidadao[0] if (len(dados_cidadao) > 0 and 'mensagem' not in dados_cidadao[0]) else None
        if info_pessoafisica_rfb:
            return {
                'NomeMunicipioNaturalidade': info_pessoafisica_rfb.get('NomeMunicipioNaturalidade', ''),
                'UFMunicipioNaturalidade': info_pessoafisica_rfb.get('UFMunicipioNaturalidade', ''),
                'CodigoMunicipioNaturalidade': info_pessoafisica_rfb.get('CodigoMunicipioNaturalidade', ''),
            }
        else:
            erro = dados_cidadao and dados_cidadao[0] or 'Ocorreu um erro na consulta dos dados do aluno'
            raise Exception(erro)

    def eh_chefe_do_setor_hoje(self, setor):
        historico_funcao = self.historico_funcao_ativa.filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False)
        if historico_funcao.exists():
            for funcao_setor in historico_funcao:
                if setor.id in funcao_setor.setor_suap.ids_descendentes:
                    return True
        return False

    def get_funcao(self):
        from comum.models import FuncaoCodigo

        if self.funcao and self.funcao_codigo:
            funcao = FuncaoCodigo.objects.filter(nome__unaccent__icontains=self.funcao.codigo).filter(nome__unaccent__icontains=self.funcao_codigo)
            if funcao.exists():
                return funcao[0]
        return None

    def ultimo_pca_progressao_merito(self):
        pca = self.pca_set
        if pca.exists():
            for pca_item in pca.all():
                posicionamento = pca_item.posicionamentopca_set.filter(eh_capacitacao=False)
                if posicionamento.exists():
                    for po in posicionamento.all():
                        if po.forma_entrada.codigo not in ['009', '128'] and po.data_fim_posicionamento_pca_or_None() is None:
                            return po
        return None

    @staticmethod
    def get_docente_sem_database(user, excluir_nivel_padrao=None):
        # apenas PROFESSOR ENS BASICO TECN TECNOLOGICO (CMEBT) - 707001
        if excluir_nivel_padrao is None:
            excluir_nivel_padrao = ['501']
        COD_CARGO_EMPREGO = '707001'
        docentes = Servidor.objects.docentes().ativos().filter(data_base_progressao__isnull=True, cargo_emprego__codigo=COD_CARGO_EMPREGO)
        if excluir_nivel_padrao:
            docentes = docentes.exclude(nivel_padrao__in=excluir_nivel_padrao)
        # se coordenador sistêmico ou super usuário
        if user.has_perm('comum.is_coordenador_de_gestao_de_pessoas_sistemico') or user.is_superuser:
            return docentes
        # se coordenador rh campus
        if user.has_perm('comum.is_coordenador_de_gestao_de_pessoas'):
            uo_usuario = get_uo(user)
            docentes = docentes.filter(setor__uo__id=uo_usuario.id)
            return docentes
        return Servidor.objects.none()

    def get_cargo_area(self):
        cargo_area = None
        if self.cargo_emprego_area:
            cargo_area = str(self.cargo_emprego_area)
        else:
            cargo_area = self.cargo_emprego.nome
        return cargo_area

    #
    # - regra dos 24 meses de afastamentos
    def dados_afastamentos_efetivo_exercicio_24_meses(self, contar_a_partir_de=None, ids_ignorar=None):
        from ..afastamento import ServidorAfastamento

        if ids_ignorar is None:
            ids_ignorar = []
        DIAS_EFETIVO_EXERCICIO = 730  # 730 dias referentes a 24 meses (365 * 2)
        codigos_afastamento = self._get_afastamentos_efetivo_exercicio_qtd_dias(DIAS_EFETIVO_EXERCICIO)
        #
        # checando o tipo do parâmetro passado
        if type(contar_a_partir_de) is datetime.datetime:
            contar_a_partir_de = datetime.date(contar_a_partir_de.year, contar_a_partir_de.month, contar_a_partir_de.day)
        soma = 0

        check_qs = ServidorAfastamento.objects.filter(servidor=self, afastamento__codigo__in=codigos_afastamento, id__in=ids_ignorar)
        for i in check_qs:
            soma += i.dias_incluindo_ultimo_dia()

        # só entra se o servidor em questão tiver afastamentos no período passado
        if codigos_afastamento:
            # identificando se os dias de afastamentos ultrapassam o limite
            dias = 0
            dict_info = {}
            qs_afasts = (
                ServidorAfastamento.objects.filter(servidor=self, afastamento__codigo__in=codigos_afastamento)
                .exclude(id__in=ids_ignorar)
                .order_by('data_inicio')
            )
            for i in qs_afasts:
                dias_diferenca = (i.data_termino - i.data_inicio).days + 1
                dict_info[i] = []
                for x in range(dias_diferenca):  # é necessário percorrer dia a dia dos afastamentos até identificar o dia que exrapola o limite
                    soma += 1
                    data = i.data_inicio + datetime.timedelta(days=x)
                    if (
                        contar_a_partir_de and contar_a_partir_de > data
                    ):  # normalmente, o parâmetro "contar_a_partir_de" é a data de início do período aquisitivo
                        continue
                    # se a soma for maior que os dias de exercício, iremos montar os dados
                    if soma > DIAS_EFETIVO_EXERCICIO:
                        dias += 1
                        dict_info[i].append({'soma_dias': soma, 'data': data, 'afastamento': i})
            dict_info.update({'total_dias': dias})
            return dict_info
        return None

    def get_indicacoes_como_avaliador_pesquisa(self):
        if 'pesquisa' in settings.INSTALLED_APPS:
            AvaliadorIndicado = apps.get_model('pesquisa', 'AvaliadorIndicado')
            Avaliacao = apps.get_model('pesquisa', 'Avaliacao')
            vinculo_avaliador = self.get_vinculo()
            return f'{AvaliadorIndicado.objects.filter(vinculo=vinculo_avaliador).count()} indicações, {Avaliacao.objects.filter(vinculo=vinculo_avaliador).count()} avaliações realizadas'
        return '-'

    @staticmethod
    def calcula_novo_padrao(nivel_padrao, eh_tae=False, eh_docente=False):
        try:
            # selecionando o nível e o padrão do servidor
            nivel = nivel_padrao[:1]
            padrao = nivel_padrao[1:3]
            # verificando se é tae
            if eh_tae:
                nivel_int = int(nivel)
                padrao_int = int(padrao)
                novo_padrao = (nivel_int - 1) + padrao_int
                return f'{novo_padrao:02}'
            # verificando se é docente
            if eh_docente:
                codigo = f'D{nivel}{padrao}'
                return Servidor._reenquadrar_docente(codigo)
        except Exception as ex:
            if settings.DEBUG:
                log.error(ex)
            return None
        #
        return None

    @staticmethod
    def _reenquadrar_docente(codigo):
        mapa_reenquadramento = {
            'D101': 'A1',
            'D102': 'A1',
            'D201': 'A1',
            'D202': 'A1',
            'D301': 'B1',
            'D302': 'B2',
            'D303': 'B3',
            'D304': 'B4',
            'D401': 'C1',
            'D402': 'C2',
            'D403': 'C3',
            'D404': 'C4',
            'D501': 'D1',
        }
        return mapa_reenquadramento.get(codigo, 'Código desconhecido')

    @property
    def nivel_docente(self):
        if self.cargo_classe:
            return self.cargo_classe.codigo + self.nivel_padrao
        return None

    # Método que devolve de forma fácil o nível de capacitacao (horizontal) do servidor
    def get_nivel_capacitacao(self):
        nivel = None
        if self.nivel_padrao:
            nivel = self.nivel_padrao[:1]
        return nivel

    def get_reativacao_temporaria_vigente(self, data_referencia=None):
        data_referencia = data_referencia or get_datetime_now().date()
        return (
            self.servidorreativacaotemporaria_set.filter(
                data_inicio__lte=data_referencia,
                data_fim__gte=data_referencia,
                situacao=ServidorReativacaoTemporaria.STATUS_AUTORIZADA,
            )
            .order_by('-data_fim', '-pk')
            .first()
        )

    def get_ocorrencias_exclusao(self):
        return self.servidorocorrencia_set.filter(subgrupo__descricao='EXCLUSAO').select_related('ocorrencia', 'subgrupo').order_by('-data', '-pk')

    def get_ocorrencias_inclusao(self):
        return (
            self.servidorocorrencia_set.filter(subgrupo__descricao__istartswith='INCLUSAO')
            .select_related('ocorrencia', 'subgrupo')
            .order_by('-data', '-pk')
        )

    def get_ocorrencia_exclusao_para_reativacao_permanente(self):
        ocorrencias_inclusao = self.get_ocorrencias_inclusao()
        for ocorrencia_exclusao in self.get_ocorrencias_exclusao():
            possui_inclusao_posterior = ocorrencias_inclusao.filter(data__gte=ocorrencia_exclusao.data).exists()
            if not possui_inclusao_posterior:
                return ocorrencia_exclusao
        return None

    def possui_reativacao_temporaria_vigente(self, data_referencia=None):
        return bool(self.get_reativacao_temporaria_vigente(data_referencia=data_referencia))

    @staticmethod
    def _ad_timestamp_to_datetime(valor):
        if not valor or valor in ('0', '9223372036854775807'):
            return None
        return datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=int(valor) / 10)

    def possui_janela_acesso_ldap_vigente(self, data_referencia=None):
        data_referencia = data_referencia or get_datetime_now()
        vinculo = self.get_vinculo()
        if not vinculo:
            return False
        ldap_user = vinculo.get_usuario_ldap(attrs=['accountExpires'])
        if not ldap_user:
            return False
        account_expires = ldap_user.get('accountExpires', [None])[0]
        if isinstance(account_expires, bytes):
            account_expires = account_expires.decode()
        data_expiracao = self._ad_timestamp_to_datetime(account_expires)
        return bool(data_expiracao and data_expiracao >= data_referencia)

    def acesso_ldap_liberado(self, data_referencia=None):
        return bool(self.ativo or self.possui_reativacao_temporaria_vigente(data_referencia=data_referencia))

    def acesso_suap_liberado(self, data_referencia=None):
        return bool(
            self.acesso_ldap_liberado(data_referencia=data_referencia) or self.possui_janela_acesso_ldap_vigente(data_referencia=data_referencia)
        )


class ServidorReativacaoTemporaria(models.ModelPlus):
    STATUS_SOLICITADA = 'solicitada'
    STATUS_AUTORIZADA = 'autorizada'
    STATUS_NEGADA = 'negada'
    STATUS_CHOICES = (
        (STATUS_SOLICITADA, 'Solicitada'),
        (STATUS_AUTORIZADA, 'Autorizada'),
        (STATUS_NEGADA, 'Não autorizada'),
    )

    servidor = models.ForeignKeyPlus(Servidor, verbose_name='Servidor')
    data_inicio = models.DateField(
        'Data de Início',
        null=False,
    )
    data_fim = models.DateField('Data de Fim', null=False)
    justificativa = models.TextField('Justificativa')
    cadastrado_por = models.ForeignKeyPlus(
        'comum.User',
        verbose_name='Cadastrado Por',
        related_name='reativacoes_temporarias_cadastradas',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', auto_now_add=True, null=True)
    situacao = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default=STATUS_SOLICITADA)
    autorizador = models.ForeignKeyPlus(
        'comum.User',
        verbose_name='Autorizador',
        related_name='reativacoes_temporarias_autorizadas',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    data_autorizacao = models.DateTimeFieldPlus('Data da Autorização', null=True, blank=True)

    class Meta:
        verbose_name = 'Reativação Temporária de Servidor'
        verbose_name_plural = 'Reativações Temporárias dos Servidores'
        ordering = ('-data_inicio', '-pk')

    def clean(self):
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            raise ValidationError({'data_fim': 'A data de fim deve ser maior ou igual à data de início.'})
        if self.data_inicio and self.data_fim and (self.data_fim - self.data_inicio).days > 90:
            raise ValidationError({'data_fim': 'A duração da reativação temporária não pode ultrapassar 90 dias.'})

    @property
    def vigente(self):
        data_referencia = get_datetime_now().date()
        return self.situacao == self.STATUS_AUTORIZADA and self.data_inicio <= data_referencia <= self.data_fim

    @property
    def encerrada(self):
        return self.situacao == self.STATUS_AUTORIZADA and self.data_fim < get_datetime_now().date()

    @property
    def pendente_avaliacao(self):
        return self.situacao == self.STATUS_SOLICITADA

    def autorizar(self, user):
        agora = get_datetime_now()
        self.situacao = self.STATUS_AUTORIZADA
        self.autorizador = user
        self.data_autorizacao = agora
        self.save(update_fields=['situacao', 'autorizador', 'data_autorizacao'])

    def negar(self, user):
        self.situacao = self.STATUS_NEGADA
        self.save(update_fields=['situacao'])

    def encerrar(self, user=None):
        hoje = get_datetime_now().date()
        data_fim = hoje - datetime.timedelta(days=1)
        if self.data_fim > data_fim:
            self.data_fim = data_fim
            self.save(update_fields=['data_fim'])

    def __str__(self):
        return f'Reativação Temporária de {self.servidor} - {self.get_situacao_display()}'


class ServidorReativacaoPermanente(models.ModelPlus):
    STATUS_SOLICITADA = 'solicitada'
    STATUS_AUTORIZADA = 'autorizada'
    STATUS_NEGADA = 'negada'
    STATUS_CHOICES = (
        (STATUS_SOLICITADA, 'Solicitada'),
        (STATUS_AUTORIZADA, 'Autorizada'),
        (STATUS_NEGADA, 'Não autorizada'),
    )

    servidor = models.ForeignKeyPlus(Servidor, verbose_name='Servidor', on_delete=models.CASCADE)
    justificativa = models.TextField('Justificativa')
    cadastrado_por = models.ForeignKeyPlus(
        'comum.User',
        verbose_name='Cadastrado Por',
        related_name='reativacoes_permanentes_cadastradas',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', auto_now_add=True, null=True)
    situacao = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default=STATUS_SOLICITADA)
    autorizador = models.ForeignKeyPlus(
        'comum.User',
        verbose_name='Autorizador',
        related_name='reativacoes_permanentes_autorizadas',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    data_autorizacao = models.DateTimeFieldPlus('Data da Autorização', null=True, blank=True)
    ocorrencia_removida = models.BooleanField('Ocorrência removida?', default=False)
    ocorrencia_codigo = models.CharField('Código da Ocorrência Removida', max_length=10, null=True, blank=True)
    ocorrencia_nome = models.CharField('Ocorrência Removida', max_length=255, null=True, blank=True)
    ocorrencia_data = models.DateField('Data da Ocorrência', null=True, blank=True)
    ocorrencia_data_termino = models.DateField('Data de Término da Ocorrência', null=True, blank=True)
    subgrupo_descricao = models.CharField('Subgrupo', max_length=255, null=True, blank=True)
    diploma_legal_num = models.CharField('Número do Diploma Legal', max_length=10, null=True, blank=True)
    diploma_legal_data = models.DateField('Data do Diploma Legal', null=True, blank=True)

    class Meta:
        verbose_name = 'Reativação Permanente de Servidor'
        verbose_name_plural = 'Reativações Permanentes dos Servidores'
        ordering = ('-data_cadastro', '-pk')

    @property
    def autorizada(self):
        return self.situacao == self.STATUS_AUTORIZADA

    @property
    def pendente_avaliacao(self):
        return self.situacao == self.STATUS_SOLICITADA

    def autorizar(self, user):
        agora = get_datetime_now()
        self.situacao = self.STATUS_AUTORIZADA
        self.autorizador = user
        self.data_autorizacao = agora
        self.save(update_fields=['situacao', 'autorizador', 'data_autorizacao'])

    def negar(self, user):
        self.situacao = self.STATUS_NEGADA
        self.save(update_fields=['situacao'])

    def __str__(self):
        return f'Reativação Permanente de {self.servidor} - {self.get_situacao_display()}'
