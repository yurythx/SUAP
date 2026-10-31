from datetime import date

from django.db import transaction
from django.db.models import Count, F, IntegerField, Min, Q
from django.db.models.functions import Cast, ExtractYear
from django.template.defaultfilters import date as _date

from comum.models import Configuracao
from comum.models import Vinculo as VinculoPessoa
from djtools import forms
from djtools.db import models
from djtools.utils import running_tests
from rh.models import Servidor


class AreaAvaliacao(models.ModelPlus):
    nome = models.CharField('Nome', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Área de Avaliação da Qualis'
        verbose_name_plural = 'Áreas de Avaliações da Qualis'

    def __str__(self):
        return self.nome


class PeriodicoRevista(models.ModelPlus):
    SEARCH_FIELDS = ['issn', 'nome']

    issn = models.CharField('ISSN', max_length=8, unique=True)
    nome = models.CharField('Nome', max_length=255, db_index=True)

    class Meta:
        verbose_name = 'Periódico'
        verbose_name_plural = 'Periódicos'

    def __str__(self):
        return f'{self.issn} - {self.nome}'


class ClassificacaoPeriodico(models.ModelPlus):
    TIPO_ESTRATO = (
        ('A1', 'A1'),
        ('A2', 'A2'),
        ('A3', 'A3'),
        ('A4', 'A4'),
        ('B1', 'B1'),
        ('B2', 'B2'),
        ('B3', 'B3'),
        ('B4', 'B4'),
        ('B5', 'B5'),
        ('C', 'C'),
    )
    periodico = models.ForeignKeyPlus('cnpq.PeriodicoRevista', related_name='estratos_qualis', on_delete=models.CASCADE, verbose_name='Periódico')
    estrato = models.CharField('Classificação', max_length=2, choices=TIPO_ESTRATO)
    area_avaliacao = models.ForeignKeyPlus('cnpq.AreaAvaliacao', on_delete=models.CASCADE, verbose_name='Área de Avaliação')
    data_processamento = models.DateFieldPlus('Data do Processamento', auto_now=True)

    class Meta:
        verbose_name = 'Classificação de Periódico'
        verbose_name_plural = 'Classificações de Periódicos'

    def __str__(self):
        return f'{self.periodico} - {self.estrato} - {self.area_avaliacao}'


class GrupoPesquisa(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'descricao', 'instituicao']
    codigo = models.CharField('Código', max_length=16, unique=True)
    descricao = models.CharField('Descrição', max_length=255, db_index=True)
    instituicao = models.CharField('Instituição', max_length=60)

    class Meta:
        verbose_name = 'Grupo de Pesquisa'
        verbose_name_plural = 'Grupos de Pesquisa'

    def __str__(self):
        return str(self.descricao)


class CurriculoVittaeLattes(models.ModelPlus):
    sistema_origem_xml = models.TextField()
    numero_identificador = models.TextField()
    datahora_atualizacao = models.DateTimeField(null=True)
    dado_geral = models.OneToOneField('cnpq.DadoGeral', null=True, on_delete=models.CASCADE)
    dado_complementar = models.OneToOneField('cnpq.DadoComplementar', null=True, on_delete=models.CASCADE)
    vinculo = models.OneToOneField('comum.Vinculo', related_name='vinculo_curriculo_lattes', on_delete=models.CASCADE, null=True)
    grupos_pesquisa = models.ManyToManyFieldPlus('cnpq.GrupoPesquisa', verbose_name='Grupos de Pesquisa')
    data_extracao = models.DateTimeFieldPlus('Data da Última Extração', null=True)
    data_inicio_exercicio = models.DateField('Data de Início do Exercício na Instituição', null=True)
    data_fim_exercicio = models.DateField('Data de Fim do Exercício na Instituição', null=True)
    ano_inicio_exercicio = models.IntegerField('Ano de Início do Exercício na Instituição', null=True)
    ano_fim_exercicio = models.IntegerField('Ano de Fim do Exercício na Instituição', null=True)
    data_importacao_grupos_pesquisa = models.DateTimeField(null=True)

    class History:
        disabled = False

    class Meta:
        permissions = (
            ('pode_ver_relatorios', 'Pode ver os relatórios'),
            ('pode_ver_producao_servidor', 'Pode ver a produção por servidor'),
            ('pode_cadastrar_periodicos', 'Pode cadastrar periódicos'),
            ('pode_importar_planilha_periodicos', 'Pode importar planilha de periódicos'),
        )

    @transaction.atomic
    def delete(self):
        producoes_bibliograficas = self.producoes_bibliograficas.all()
        for producao in producoes_bibliograficas:
            producao.delete()

        producoes_tecnicas = self.producoes_tecnicas.all()
        for producao in producoes_tecnicas:
            producao.delete()

        outras_producoes = self.outras_producoes.all()
        for producao in outras_producoes:
            producao.delete()
        try:
            self.dado_complementar.delete()
        except Exception:
            pass
        try:
            self.dado_geral.delete()
        except Exception:
            pass

        super().delete()

    # RECUPERA AS FORMAÇÕES ACADÊMICAS
    def get_formacoes_doutor(self):
        return self.dado_geral.formacoes_academicas_titulacoes.order_by('-ano_conclusao').filter(tipo='DOUTORADO', status_curso='CONCLUIDO')

    def get_formacoes_mestrado(self):
        return self.dado_geral.formacoes_academicas_titulacoes.order_by('-ano_conclusao').filter(
            tipo__in=['MESTRADO', 'MESTRADO-PROFISSIONALIZANTE'], status_curso='CONCLUIDO'
        )

    def get_formacoes_especializacao(self):
        return self.dado_geral.formacoes_academicas_titulacoes.order_by('-ano_conclusao').filter(tipo='ESPECIALIZACAO', status_curso='CONCLUIDO')

    # RECUPERA AS PRODUCOES BIBLIOGRAFIAS
    def get_artigos(self):
        return Artigo.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_artigos_completos(self):
        return Artigo.objects.filter(natureza=Artigo.NATUREZA_COMPLETO).order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_artigos_resumos(self):
        return Artigo.objects.filter(natureza=Artigo.NATUREZA_RESUMO).order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_artigos_nao_informados(self):
        return Artigo.objects.filter(natureza=Artigo.NATUREZA_NAO_INFORMADO).order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_trabalhos_eventos(self):
        return TrabalhoEvento.objects.filter(curriculo=self).order_by('-ano', 'sequencia')

    def get_trabalhos_eventos_completos(self):
        return TrabalhoEvento.objects.filter(curriculo=self, natureza=TrabalhoEvento.NATUREZA_COMPLETO).order_by('-ano', 'sequencia')

    def get_trabalhos_eventos_resumos_expandidos(self):
        return TrabalhoEvento.objects.filter(natureza=TrabalhoEvento.NATUREZA_RESUMO_EXPANDIDO).order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_trabalhos_eventos_resumos(self):
        return TrabalhoEvento.objects.filter(natureza=TrabalhoEvento.NATUREZA_RESUMO).order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_livros(self):
        return Livro.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_capitulos(self):
        return Capitulo.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_textos_jornal_revista(self):
        return TextoJonalRevista.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_prefacios_posfacios(self):
        return PrefacioPosfacio.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_partituras(self):
        return Partitura.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_traducoes(self):
        return Traducao.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_outras_producoes(self):
        return OutraProducaoBibliografica.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    # RECUPERA AS PATENTES E REGISTROS
    def get_patentes_e_registros(self):
        qs1 = ProducaoTecnica.objects.order_by('-ano').filter(software__registros_patentes__isnull=False, curriculo=self)
        qs2 = ProducaoTecnica.objects.order_by('-ano').filter(produtotecnologico__registros_patentes__isnull=False, curriculo=self)
        qs3 = ProducaoTecnica.objects.order_by('-ano').filter(processotecnica__registros_patentes__isnull=False, curriculo=self)
        qs4 = ProducaoTecnica.objects.order_by('-ano').filter(marca__registros_patentes__isnull=False, curriculo=self)
        qs5 = ProducaoTecnica.objects.order_by('-ano').filter(patente__registros_patentes__isnull=False, curriculo=self)
        qs6 = ProducaoTecnica.objects.order_by('-ano').filter(desenhoindustrial__registros_patentes__isnull=False, curriculo=self)

        return qs1 | qs2 | qs3 | qs4 | qs5 | qs6

    def get_patentes(self):
        return ProducaoTecnica.objects.order_by('-ano').filter(patente__registros_patentes__isnull=False, curriculo=self)

    def get_softwares_patentes(self):
        return ProducaoTecnica.objects.order_by('-ano').filter(software__registros_patentes__isnull=False, curriculo=self)

    def get_outros_registros(self):
        qs2 = ProducaoTecnica.objects.order_by('-ano').filter(produtotecnologico__registros_patentes__isnull=False, curriculo=self)
        qs3 = ProducaoTecnica.objects.order_by('-ano').filter(processotecnica__registros_patentes__isnull=False, curriculo=self)
        qs4 = ProducaoTecnica.objects.order_by('-ano').filter(marca__registros_patentes__isnull=False, curriculo=self)
        qs6 = ProducaoTecnica.objects.order_by('-ano').filter(desenhoindustrial__registros_patentes__isnull=False, curriculo=self)

        return qs2 | qs3 | qs4 | qs6

    # RECUPERA AS PRODUCOES TECNICAS
    def get_todas_producoes_tecnicas(self):
        return ProducaoTecnica.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_softwares(self):
        return Software.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_produtos_tecnologicos(self):
        return ProdutoTecnologico.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_processos_tecnicas(self):
        return ProcessoTecnica.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_trabalhos_tecnicos(self):
        return TrabalhoTecnico.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_apresentacoes_trabalhos(self):
        return ApresentacaoTrabalho.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_cartas_mapas_similares(self):
        return CartaMapaSimilar.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_cursos_curta_duracao_ministrados(self):
        return CursoCurtaDuracaoMinistrado.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    """
    #Desenvolvimento de Material Didativo Instrucional
    """

    def get_desenvolvimento_materiais_didaticos_instrucionais(self):
        return DesMatDidativoInstrucional.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_editoracoes(self):
        return Editoracao.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_manutencao_obras_artisticas(self):
        return ManutencaoObraArtistica.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_maquetes(self):
        return Maquete.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_organizacoes_eventos(self):
        return OrganizacaoEventos.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_outras_producoes_tecnicas(self):
        return OutraProducaoTecnica.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_programas_radio_tv(self):
        return ProgramaRadioTV.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    def get_relatorios_pesquisa(self):
        return RelatorioPesquisa.objects.order_by('-ano', 'sequencia').filter(curriculo=self)

    # RECUPERA AS ORIENTACOES CONCLUIDAS
    def get_orientacoes_mestrado(self):
        return OrientacaoConcluida.objects.filter(tipo='ORIENTACOES-CONCLUIDAS-PARA-MESTRADO', curriculo=self).order_by('-ano', 'sequencia')

    def get_orientacoes_doutorado(self):
        return OrientacaoConcluida.objects.filter(tipo='ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO', curriculo=self).order_by('-ano', 'sequencia')

    def get_orientacoes_posdoutorado(self):
        return OrientacaoConcluida.objects.filter(tipo='ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO', curriculo=self).order_by('-ano', 'sequencia')

    def get_orientacoes_aperfeicoamento_especializacao(self):
        return OrientacaoConcluida.objects.filter(tipo='MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO', curriculo=self).order_by(
            '-ano', 'sequencia'
        )

    def get_orientacoes_graduacao(self):
        return OrientacaoConcluida.objects.filter(tipo='TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO', curriculo=self).order_by('-ano', 'sequencia')

    def get_orientacoes_iniciacao_cientifica(self):
        return OrientacaoConcluida.objects.filter(tipo='INICIACAO_CIENTIFICA', curriculo=self).order_by('-ano', 'sequencia')

    def get_outras_orientacoes(self):
        return OrientacaoConcluida.objects.filter(tipo='ORIENTACAO-DE-OUTRA-NATUREZA', curriculo=self).order_by('-ano', 'sequencia')

    def get_projeto_pesquisa(self, nome_instituicao=None):
        qs = (
            ProjetoPesquisa.objects.filter(participacao_projeto__atuacao_profissional__dado_geral__curriculovittaelattes=self)
            .filter(natureza='PESQUISA')
            .order_by('-ano_inicio')
        )
        if nome_instituicao is not None:
            qs = qs.filter(participacao_projeto__atuacao_profissional__nome_instituicao=nome_instituicao)
        return qs

    def get_projeto_pesquisa_como_coordenador(self, nome_instituicao=None):
        qs = self.get_projeto_pesquisa()
        if nome_instituicao is not None:
            qs = qs.filter(participacao_projeto__atuacao_profissional__nome_instituicao__iexact=nome_instituicao)
        ids = (
            qs.filter(
                integrantes_projeto__flag_responsavel=True,
                integrantes_projeto__nome_completo=F('participacao_projeto__atuacao_profissional__dado_geral__nome_completo'),
            )
            .values_list('id', flat=True)
            .distinct()
        )
        qs = qs.filter(id__in=ids)
        return qs

    def get_projeto_pesquisa_como_membro(self, nome_instituicao=None):
        qs = self.get_projeto_pesquisa()
        if nome_instituicao is not None:
            qs = qs.filter(participacao_projeto__atuacao_profissional__nome_instituicao__iexact=nome_instituicao)
        ids = (
            qs.filter(
                integrantes_projeto__flag_responsavel=False,
                integrantes_projeto__nome_completo=F('participacao_projeto__atuacao_profissional__dado_geral__nome_completo'),
            )
            .values_list('id', flat=True)
            .distinct()
        )
        qs = qs.filter(id__in=ids)
        return qs

    def get_projeto_extensao(self):
        return (
            ProjetoPesquisa.objects.filter(participacao_projeto__atuacao_profissional__dado_geral__curriculovittaelattes=self)
            .filter(natureza='EXTENSAO')
            .order_by('-ano_inicio')
        )

    def get_projeto_desenvolvimento(self, nome_instituicao=None):
        qs = (
            ProjetoPesquisa.objects.filter(participacao_projeto__atuacao_profissional__dado_geral__curriculovittaelattes=self)
            .filter(natureza='DESENVOLVIMENTO')
            .order_by('-ano_inicio')
        )
        if nome_instituicao is not None:
            qs = qs.filter(participacao_projeto__atuacao_profissional__nome_instituicao=nome_instituicao)
        return qs

    def get_projeto_desenvolvimento_como_coordenador(self, nome_instituicao=None):
        qs = self.get_projeto_desenvolvimento(nome_instituicao=nome_instituicao)
        ids = (
            qs.filter(
                integrantes_projeto__flag_responsavel=True,
                integrantes_projeto__nome_completo=F('participacao_projeto__atuacao_profissional__dado_geral__nome_completo'),
            )
            .values_list('id', flat=True)
            .distinct()
        )
        qs = qs.filter(id__in=ids)
        return qs

    def get_projeto_desenvolvimento_como_membro(self, nome_instituicao=None):
        qs = self.get_projeto_desenvolvimento(nome_instituicao=nome_instituicao)
        ids = (
            qs.filter(
                integrantes_projeto__flag_responsavel=False,
                integrantes_projeto__nome_completo=F('participacao_projeto__atuacao_profissional__dado_geral__nome_completo'),
            )
            .values_list('id', flat=True)
            .distinct()
        )
        qs = qs.filter(id__in=ids)
        return qs

    def get_participacao_em_banca_trabalho_conclusao(self):
        return ParticipacaoBancaTrabalhoConclusao.objects.filter(dado_complementar__curriculovittaelattes=self).order_by('natureza', '-ano', 'titulo')

    def get_participacao_em_banca_graduacao(self):
        return ParticipacaoBancaTrabalhoConclusao.objects.filter(dado_complementar__curriculovittaelattes=self).filter(
            tipo='PARTICIPACAO-EM-BANCA-DE-GRADUACAO'
        )

    def get_participacao_em_banca_especializacao(self):
        return ParticipacaoBancaTrabalhoConclusao.objects.filter(dado_complementar__curriculovittaelattes=self).filter(
            tipo='PARTICIPACAO-EM-BANCA-DE-APERFEICOAMENTO-ESPECIALIZACAO'
        )

    def get_participacao_em_banca_mestrado(self):
        return ParticipacaoBancaTrabalhoConclusao.objects.filter(dado_complementar__curriculovittaelattes=self).filter(
            tipo='PARTICIPACAO-EM-BANCA-DE-MESTRADO'
        )

    def get_participacao_em_banca_doutorado(self):
        return ParticipacaoBancaTrabalhoConclusao.objects.filter(dado_complementar__curriculovittaelattes=self).filter(
            tipo='PARTICIPACAO-EM-BANCA-DE-DOUTORADO'
        )

    def get_participacao_em_banca_comissoes_julgadoras(self):
        return ParticipacaoBancaJulgadora.objects.filter(dado_complementar__curriculovittaelattes=self).order_by('natureza', '-ano', 'titulo')

    def get_premios_e_titulos(self):
        return PremioTitulo.objects.filter(dado_geral__curriculovittaelattes=self).order_by('-ano_premiacao', 'nome_premio_titulo')

    def get_vinculos(self):
        return Vinculo.objects.filter(atuacao_profissional__dado_geral__curriculovittaelattes=self).order_by('outro_vinculo_informado', '-ano_inicio')

    def get_revisor_periodicos(self):
        # TODO: dados-gerais - atuacoes-profissionais - atuacao-profissional - vinculos (OUTRO-VINCULO-INFORMADO:Revisor de periódico)
        return (
            Vinculo.objects.filter(atuacao_profissional__dado_geral__curriculovittaelattes=self)
            .filter(outro_vinculo_informado='Revisor de periódico')
            .order_by('-ano_inicio')
        )

    def get_membro_corpo_editorial_de_periodicos(self):
        # TODO: dados-gerais - atuacoes-profissionais - atuacao-profissional - vinculos (OUTRO-VINCULO-INFORMADO:Membro de corpo editorial)
        return (
            Vinculo.objects.filter(atuacao_profissional__dado_geral__curriculovittaelattes=self)
            .filter(outro_vinculo_informado='Membro de corpo editorial')
            .order_by('-ano_inicio')
        )


################
# DADOS GERAIS #
################
class DadoGeral(models.ModelPlus):
    nome_completo = models.TextField()
    nome_citacao = models.TextField()
    nacionalidade = models.TextField()
    cpf = models.TextField()
    numero_passaporte = models.TextField()
    pais_nascimento = models.TextField()
    uf_nascimento = models.TextField()
    cidade_nascimento = models.TextField()
    data_nascimento = models.DateField(null=True)
    sexo = models.TextField()
    numero_identidade = models.TextField()
    orgao_emissor = models.TextField()
    uf_orgao_emissor = models.TextField()
    data_emissao = models.DateField(null=True)
    nome_pai = models.TextField()
    nome_mae = models.TextField()
    permissao_divulgacao = models.TextField()
    nome_arquivo_foto = models.TextField()
    texto_resumo = models.TextField()
    outras_informacoes_relevantes = models.TextField()

    endereco_preferencial = models.OneToOneField('cnpq.Endereco', null=True, related_name='endereco_preferencial', on_delete=models.CASCADE)
    endereco_profissional = models.OneToOneField('cnpq.Endereco', null=True, related_name='endereco_profissional', on_delete=models.CASCADE)
    endereco_residencial = models.OneToOneField('cnpq.Endereco', null=True, related_name='endereco_residencial', on_delete=models.CASCADE)

    def delete(self, *args, **kwargs):
        formacoes_academicas_titulacoes = self.formacoes_academicas_titulacoes.all()
        for formacao in formacoes_academicas_titulacoes:
            formacao.delete()

        return super(self.__class__, self).delete(*args, **kwargs)


class Endereco(models.ModelPlus):
    pais = models.TextField()
    uf = models.TextField()
    cep = models.TextField()
    cidade = models.TextField()
    bairro = models.TextField()
    ddd = models.TextField()
    telefone = models.TextField()
    ramal = models.TextField()
    fax = models.TextField()
    caixa_postal = models.TextField()
    email = models.TextField()
    home_page = models.TextField()
    logradouro = models.TextField()
    codigo_instituicao_empresa = models.TextField()
    nome_instituicao_empresa = models.TextField()
    codigo_orgao = models.TextField()
    nome_orgao = models.TextField()
    codigo_unidade = models.TextField()
    nome_unidade = models.TextField()


class FormacaoAcademicaTitulacao(models.ModelPlus):
    tipo_choices = {
        'GRADUACAO': 'Graduação',
        'ESPECIALIZACAO': 'Especialização',
        'MESTRADO': 'Mestrado',
        'DOUTORADO': 'Doutorado',
        'POS-DOUTORADO': 'Pós-Doutorado',
        'LIVRE-DOCENCIA': 'Livre Docência',
        'CURSO-TECNICO-PROFISSIONALIZANTE': 'Curso Técnico/Profissionalizante',
        'MESTRADO-PROFISSIONALIZANTE': 'Mestrado Profissionalizante',
        'ENSINO-FUNDAMENTAL-PRIMEIRO-GRAU': 'Ensino Fundamental (1º grau)',
        'ENSINO-MEDIO-SEGUNDO-GRAU': 'Ensino Médio (2º grau)',
        'RESIDENCIA-MEDICA': 'Residência Médica',
        'APERFEICOAMENTO': 'Aperfeicoamento',
    }

    status_choices = {'EM_ANDAMENTO': 'Em andamento', 'CONCLUIDO': 'Concluído', 'INCOMPLETO': 'Incompleto'}

    dado_geral = models.ForeignKeyPlus('cnpq.DadoGeral', related_name='formacoes_academicas_titulacoes', on_delete=models.CASCADE)
    tipo = models.TextField()
    sequencia_formacao = models.TextField()
    nivel = models.TextField()
    codigo_instituicao = models.TextField()
    nome_instituicao = models.TextField()
    status_curso = models.TextField()
    ano_inicio = models.TextField()
    ano_conclusao = models.TextField()
    ano_obtencao = models.TextField()
    titulo_trabalho_conclusao = models.TextField()
    codigo_orgao = models.TextField()
    nome_orgao = models.TextField()
    codigo_curso = models.TextField()
    nome_curso = models.TextField()
    flag_bolsa = models.BooleanField(null=True)
    codigo_agencia_financiadora = models.TextField()
    nome_agencia_financiadora = models.TextField()
    nome_orientador = models.TextField()
    codigo_area_curso = models.TextField()
    numero_id_orientador = models.TextField()
    codigo_curso_capes = models.TextField()
    carga_horaria = models.TextField()
    numero_registro = models.TextField()
    tipo_doutorado = models.TextField()
    status_estagio = models.TextField()
    codigo_instituicao_dout = models.TextField()
    nome_instituicao_dout = models.TextField()
    codigo_instituicao_outra_dout = models.TextField()
    nome_instituicao_outra_dout = models.TextField()
    nome_orientador_dout = models.TextField()
    palavras_chave = models.ManyToManyField('cnpq.PalavraChave')
    areas_conhecimento = models.ManyToManyField('cnpq.AreaConhecimento')
    setores_atividade = models.ManyToManyField('cnpq.SetorAtividade')

    def delete(self):
        palavras_chave = self.palavras_chave.all()
        for palavra in palavras_chave:
            palavra.delete()

        areas_conhecimento = self.areas_conhecimento.all()
        for area in areas_conhecimento:
            area.delete()

        setores_atividade = self.setores_atividade.all()
        for setor in setores_atividade:
            setor.delete()

        super().delete()

    def get_tipo(self):
        return self.tipo_choices[self.tipo]

    def get_status_curso(self):
        return (self.status_curso and self.status_choices[self.status_curso]) or ''

    def __str__(self):
        retorno = f'{self.get_tipo()}'
        if self.nome_curso:
            retorno += f' em {self.nome_curso}'

        if self.nome_instituicao:
            retorno += f'<br/> {self.nome_instituicao}.'
            if self.nome_orgao:
                retorno += f' {self.nome_orgao}'

        if self.titulo_trabalho_conclusao:
            retorno += f'<br/>Título: {self.titulo_trabalho_conclusao}.'
            if self.ano_obtencao:
                retorno += f'Ano de Obtenção: {self.ano_obtencao}'

        if self.nome_orientador:
            retorno += f'<br/>Orientador: {self.nome_orientador}.'

        if self.flag_bolsa == 'SIM':
            retorno += f'<br/>Bolsista do(a): {self.nome_agencia_financiadora}.'

        if self.palavras_chave.exists():
            retorno += '<br/>Palavras-chave: '
            for p in self.palavras_chave.all():
                retorno += f'{p.palavra}; '

        if self.areas_conhecimento.exists():
            retorno += '<br/>Palavras-chave: '
            for a in self.areas_conhecimento.all():
                retorno += f'{a.get_nome_grande_area()} / {a.nome_area} / {a.nome_sub_area} / {a.nome_especializacao}; '

        if self.setores_atividade.exists():
            retorno += '<br/>Setores de atividade: '
            for s in self.setores_atividade.all():
                retorno += f'{s.setor}; '

        return retorno


class PalavraChave(models.ModelPlus):
    ordem = models.TextField()
    palavra = models.TextField()

    def __str__(self):
        return self.palavra


class AreaConhecimento(models.ModelPlus):
    grande_area_choices = {
        'OUTROS': 'Outra',
        'LINGUISTICA_LETRAS_E_ARTES': 'Linguística, Letras e Artes',
        'CIENCIAS_HUMANAS': 'Ciências Humanas',
        'CIENCIAS_SOCIAIS_APLICADAS': 'Ciências Sociais Aplicadas',
        'CIENCIAS_AGRARIAS': 'Ciências Agrárias',
        'CIENCIAS_DA_SAUDE': 'Ciências da Saúde',
        'ENGENHARIAS': 'Engenharias',
        'CIENCIAS_BIOLOGICAS': 'Ciências Biológicas',
        'CIENCIAS_EXATAS_E_DA_TERRA': 'Ciências Exatas e da Terra',
    }
    ordem = models.TextField()
    nome_grande_area = models.TextField()
    nome_area = models.TextField()
    nome_sub_area = models.TextField()
    nome_especializacao = models.TextField()

    def get_nome_grande_area(self):
        return self.grande_area_choices[self.nome_grande_area]

    @classmethod
    def get_descricao_grande_area(cls, nome_grande_area):
        if nome_grande_area in cls.grande_area_choices:
            return cls.grande_area_choices[nome_grande_area]

        return nome_grande_area

    def __str__(self):
        return f'{self.nome_grande_area} - {self.nome_area} - {self.nome_sub_area} - {self.nome_especializacao}'


class SetorAtividade(models.ModelPlus):
    ordem = models.TextField()
    setor = models.TextField()

    def __str__(self):
        return self.setor


class AtuacaoProfissional(models.ModelPlus):
    dado_geral = models.ForeignKeyPlus('cnpq.DadoGeral', related_name='atuacoes_profissionais', on_delete=models.CASCADE)
    nome_instituicao = models.TextField()
    sequencia_atividade = models.TextField()


class AreaAtuacao(models.ModelPlus):
    dado_geral = models.ForeignKeyPlus('cnpq.DadoGeral', related_name='areas_atuacoes', on_delete=models.CASCADE)
    sequencia_area_atuacao = models.TextField()
    nome_grande_area_conhecimento = models.TextField()
    nome_area_conhecimento = models.TextField()
    nome_sub_area_conhecimento = models.TextField()
    nome_especialidade_conhecimento = models.TextField()

    class Meta:
        ordering = ['sequencia_area_atuacao']

    def __str__(self):
        especialidade = ''
        if self.nome_especialidade_conhecimento:
            especialidade = f' / Especialidade: {self.nome_especialidade_conhecimento}'
        return f'Grande área: {self.nome_grande_area_conhecimento} / Área: {self.nome_area_conhecimento} / Subárea: {self.nome_sub_area_conhecimento}{especialidade}.'


class ParticipacaoProjeto(models.ModelPlus):
    atuacao_profissional = models.ForeignKeyPlus('cnpq.AtuacaoProfissional', related_name='participacoes_projetos', on_delete=models.CASCADE)
    sequencia = models.TextField()
    periodo = models.TextField()
    mes_inicio = models.TextField()
    ano_inicio = models.TextField()
    mes_fim = models.TextField()
    ano_fim = models.TextField()
    nome_orgao = models.TextField()
    nome_unidade = models.TextField()


class ProjetoPesquisa(models.ModelPlus):
    participacao_projeto = models.ForeignKeyPlus('cnpq.ParticipacaoProjeto', related_name='projetos_pesquisa', on_delete=models.CASCADE)
    sequencia = models.TextField()
    ano_inicio = models.TextField()
    ano_fim = models.TextField()
    nome = models.TextField()
    situacao = models.TextField()
    natureza = models.TextField()
    descricao = models.TextField()

    def index(self):
        ano_fim = self.ano_fim or 'Atual'
        return f'{self.ano_inicio} - {ano_fim}'

    def __str__(self):
        return f'<strong>{self.nome}</strong><br/><br/><strong>Descrição:</strong> {self.descricao}'


class IntegranteProjeto(models.ModelPlus):
    projeto_pesquisa = models.ForeignKeyPlus('cnpq.ProjetoPesquisa', related_name='integrantes_projeto', on_delete=models.CASCADE)
    nome_completo = models.TextField()
    nome_citacao = models.TextField()
    ordem_integracao = models.TextField()
    flag_responsavel = models.BooleanField(null=True)


class FinanciadorProjeto(models.ModelPlus):
    projeto_pesquisa = models.ForeignKeyPlus('cnpq.ProjetoPesquisa', related_name='financiadores_projeto', on_delete=models.CASCADE)
    sequencia = models.TextField()
    nome_instituicao = models.TextField()
    natureza = models.TextField()


class Vinculo(models.ModelPlus):
    tipo_vinculo_choices = {
        'SERVIDOR_PUBLICO_OU_CELETISTA': 'Servidor público ou celetista',
        'SERVIDOR_PUBLICO': 'Servidor público',
        'CELETISTA': 'Celetista',
        'PROFESSOR_VISITANTE': 'Professor visitante',
        'COLABORADOR': 'Colaborador',
        'BOLSISTA_RECEM_DOUTOR': 'Bolsista recem doutor',
        'OUTRO': 'Outros',
        'LIVRE': 'Livre',
    }
    tipo_enquadramento_choice = {'PROFESSOR_TITULAR': 'Professor titular', 'OUTRO': 'Outros', 'LIVRE': 'Livre'}

    atuacao_profissional = models.ForeignKeyPlus('cnpq.AtuacaoProfissional', related_name='vinculos', on_delete=models.CASCADE)
    sequencia_historico = models.TextField()
    tipo_vinculo = models.TextField()
    enquadramento_funcional = models.TextField()
    carga_horaria = models.TextField()
    flag_dedicacao_exclusiva = models.BooleanField(null=True)
    mes_inicio = models.TextField()
    ano_inicio = models.TextField()
    mes_fim = models.TextField()
    ano_fim = models.TextField()
    outras_informacoes = models.TextField()
    flag_vinculo_empregaticio = models.BooleanField(null=True)
    outro_vinculo_informado = models.TextField()
    outro_enquadramento_funcional_informado = models.TextField()

    def __str__(self):
        mes_ano_fim = f'{self.mes_fim}/{self.ano_fim}'
        if mes_ano_fim == '/':
            mes_ano_fim = ' Atual'
        return '{}/{} - {}. {}. {}{}'.format(
            self.mes_inicio,
            self.ano_inicio,
            mes_ano_fim,
            self.atuacao_profissional.nome_instituicao,
            ' ' if self.tipo_vinculo == 'LIVRE' else f'{self.tipo_vinculo_choices[self.tipo_vinculo]}. ',
            self.outro_enquadramento_funcional_informado,
        )

    def get_tipo_vinculo(self):
        return self.tipo_vinculo_choices[self.tipo_vinculo]

    def get_tipo_enquadramento_funcional(self):
        return self.tipo_enquadramento_choice[self.enquadramento_funcional]


"""
class AtividadeProfissional(models.Model):
    atuacao_profissional = models.ForeignKeyPlus("cnpq.AtuacaoProfissional", related_name="atividades_profissionais", on_delete=models.CASCADE)
    tipo = models.TextField()
    sequencia_funcao_atividade = models.TextField()
    flag_periodo = models.TextField()#(ANTERIOR/ATUAL)
    mes_inicio = models.TextField()
    ano_inicio = models.TextField()
    mes_fim = models.TextField()
    ano_fim = models.TextField()
    codigo_orgao = models.TextField()
    nome_orgao = models.TextField()
    codigo_unidade = models.TextField()
    nome_unidade = models.TextField()
    codigo_curso = models.TextField()
    nome_curso = models.TextField()
    formato_cargo_funcao = models.TextField()
    cargo_funcao = models.TextField()
    tipo_ensino = models.TextField()
    atividade_realizada = models.TextField()
    especificacao = models.TextField()

class Disciplina(models.Model):
    atividade_profissional = models.ForeignKeyPlus("cnpq.AtividadeProfissional", related_name="disciplinas", on_delete=models.CASCADE)
    sequencia_especificacao = models.TextField()
    texto = models.TextField()

class LinhaPesquisa(models.Model):
    atividade_profissional = models.ForeignKeyPlus("cnpq.AtividadeProfissional", related_name="linhas_pesquisa", on_delete=models.CASCADE)
    sequencia = models.TextField()
    titulo = models.TextField()
    flag_ativa = models.BooleanField(null=True)
    objetivos = models.TextField()

class Treinamento(models.Model):
    atividade_profissional = models.ForeignKeyPlus("cnpq.AtividadeProfissional", related_name="treinamentos", on_delete=models.CASCADE)
    sequencia_especificacao = models.TextField()
    texto = models.TextField()

class ProducaoProjeto(models.Model):
    projeto_pesquisa = models.ForeignKeyPlus("cnpq.ProjetoPesquisa", related_name="producoes_projeto", on_delete=models.CASCADE)
    sequencia = models.TextField()
    titulo = models.TextField()
    tipo = models.TextField()

class OrientacaoProjeto(models.Model):
    projeto_pesquisa = models.ForeignKeyPlus("cnpq.ProjetoPesquisa", related_name="orientacoes_projeto", on_delete=models.CASCADE)
    sequencia = models.TextField()
    titulo = models.TextField()
    tipo = models.TextField()

"""


class Idioma(models.ModelPlus):
    dado_geral = models.ForeignKeyPlus('cnpq.DadoGeral', related_name='idiomas', on_delete=models.CASCADE)
    idioma = models.TextField()
    descricao = models.TextField()
    proficiencia_leitura = models.TextField()
    proficiencia_fala = models.TextField()
    proficiencia_escrita = models.TextField()
    proficiencia_compreensao = models.TextField()


class PremioTitulo(models.ModelPlus):
    dado_geral = models.ForeignKeyPlus('cnpq.DadoGeral', related_name='premios_titulos', on_delete=models.CASCADE)
    nome_premio_titulo = models.TextField()
    nome_entidade_promotora = models.TextField()
    ano_premiacao = models.TextField()
    nome_do_premio_ou_titulo_ingles = models.TextField()

    def __str__(self):
        return f'{self.ano_premiacao}. {self.nome_premio_titulo}. {self.nome_entidade_promotora}.'


##########################
# PRODUCAO BIBLIOGRAFICA #
##########################
class ProducaoBibliografica(models.ModelPlus):
    meio_divulgacao_choices = {
        'IMPRESSO': 'Impresso',
        'MEIO_MAGNETICO': 'Meio Magnético',
        'MEIO_DIGITAL': 'Meio Digital',
        'FILME': 'Filme',
        'HIPERTEXTO': 'Hipertexto',
        'OUTRO': 'Outro',
        'VARIOS': 'Vários',
        'NAO_INFORMADO': 'Não Informado',
    }

    tipo_pub_choices = {
        'TRABALHO-EM-EVENTOS': 'Trabalhos em Eventos',
        'ARTIGO-PUBLICADO': 'Artigos Completos Publicados em Periódicos',
        'LIVRO-PUBLICADO-OU-ORGANIZADO': 'Livros Publicados/Organizados ou Edições',
        'CAPITULO-DE-LIVRO-PUBLICADO': 'Capítulos de livros publicados',
        'TEXTO-EM-JORNAL-OU-REVISTA': 'Textos em jornais de notícias/revistas',
        'OUTRA-PRODUCAO-BIBLIOGRAFICA': 'Outras Produções Bibliográficas',
        'PREFACIO-POSFACIO': 'Prefácios ou Posfácios',
        'PARTITURA-MUSICAL': 'Partituras',
        'TRADUCAO': 'Traduções',
        'ARTIGO-ACEITO-PARA-PUBLICACAO': 'Artigos Aceitos para Publicação',
    }

    curriculo = models.ForeignKeyPlus('cnpq.CurriculoVittaeLattes', related_name='producoes_bibliograficas', on_delete=models.CASCADE)
    sequencia = models.TextField()
    natureza = models.TextField()
    titulo = models.TextField()
    ano = models.IntegerField(null=True)
    pais = models.TextField()
    meio_divulgacao = models.TextField()
    idioma = models.TextField()
    home_page = models.TextField()
    flag_relevancia = models.BooleanField(null=True)
    doi = models.TextField()
    tipo_pub = models.TextField()
    autores = models.ManyToManyField('cnpq.Autor')
    palavras_chave = models.ManyToManyField('cnpq.PalavraChave')
    areas_conhecimento = models.ManyToManyField('cnpq.AreaConhecimento')
    setores_atividade = models.ManyToManyField('cnpq.SetorAtividade')
    informacao_adicional = models.OneToOneField('cnpq.InformacaoAdicinal', null=True, on_delete=models.CASCADE)

    def delete(self):
        autores = self.autores.all()
        for autor in autores:
            autor.delete()

        palavras_chave = self.palavras_chave.all()
        for palavra in palavras_chave:
            palavra.delete()

        areas_conhecimento = self.areas_conhecimento.all()
        for area in areas_conhecimento:
            area.delete()

        setores_atividade = self.setores_atividade.all()
        for setor in setores_atividade:
            setor.delete()

        try:
            self.informacao_adicional.delete()
        except Exception:
            pass

        super().delete()

    def __str__(self):
        return str(self.get_subinstance())

    def get_autores_titulo_unicode(self):
        autores = []
        if self.get_autores():
            for autor in self.get_autores():
                autores.append(autor.nome_citacao)
            return '{} . {}. '.format(' ; '.join(autores), self.titulo)
        return '{} . {}. '.format('Não Informado', self.titulo)

    def get_subinstance(self):
        if hasattr(self, 'artigo'):
            return self.artigo
        elif hasattr(self, 'capitulo'):
            return self.capitulo
        elif hasattr(self, 'livro'):
            return self.livro
        elif hasattr(self, 'textojonalrevista'):
            return self.textojonalrevista
        elif hasattr(self, 'prefacioposfacio'):
            return self.prefacioposfacio
        elif hasattr(self, 'partitura'):
            return self.partitura
        elif hasattr(self, 'trabalhoevento'):
            return self.trabalhoevento
        elif hasattr(self, 'traducao'):
            return self.traducao
        elif hasattr(self, 'outraproducaobibliografica'):
            return self.outraproducaobibliografica

        return None

    def get_relevancia_doi(self):
        retorno = ''
        if self.flag_relevancia:
            retorno += '<img src="http://buscatextual.cnpq.br/buscatextual/images/curriculo/ico_relevante.gif">'
        if self.doi:
            retorno += (
                '<a style="background: url(\'http://buscatextual.cnpq.br/buscatextual/images/v2/ico_doi.gif\') no-repeat scroll 0 0 transparent;display: inline-block;height: 11px;width: 26px;margin-right: 5px;" target="_blank" href="http://dx.doi.org/'
                + self.doi
                + '" tabindex="230"></a>'
            )
        return retorno

    def get_autores(self):
        return self.autores.order_by('ordem')

    def get_meio_divulgacao(self):
        return self.meio_divulgacao_choices[self.meio_divulgacao]

    def get_ano(self):
        return self.ano

    def get_tipo(self):
        return self.tipo_pub_choices[self.tipo_pub] or 'Não informado'

    def get_autores_unicos(self):
        ids = ProducaoBibliografica.objects.filter(titulo=self.titulo, curriculo__vinculo__isnull=False).values_list('curriculo__vinculo', flat=True)
        return VinculoPessoa.objects.filter(id__in=ids)

    @classmethod
    def filtrar(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        from edu.models import Aluno
        from pesquisa.models import CursoProgramaPos, DocenteProgramaPos

        queryset = cls.objects.all()
        if tipo:
            queryset = queryset.filter(tipo_pub=tipo)

        if categoria:
            if categoria == 'aluno':
                queryset = queryset.filter(curriculo__vinculo__tipo_relacionamento__model=categoria)
            else:
                queryset = queryset.filter(
                    curriculo__vinculo__id_relacionamento__in=Servidor.objects.filter(
                        cargo_emprego__grupo_cargo_emprego__categoria=categoria
                    ).values_list('id', flat=True)
                )

        if ano_ini:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(ano=None)
            else:
                queryset = queryset.filter(ano__gte=ano_ini)

        if ano_fim:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(ano=None)
            else:
                queryset = queryset.filter(ano__lte=ano_fim)

        if natureza_evento:
            queryset = queryset.filter(natureza=natureza_evento)

        if qualis_capes:
            queryset = queryset.filter(
                id__in=Artigo.objects.annotate(estrato=Min('periodico__estratos_qualis__estrato'))
                .filter(estrato=qualis_capes)
                .values_list('id', flat=True)
            )
        if not running_tests():
            ids_dos_codigos_unicos = [indice['id'] for indice in queryset.values('id', 'titulo').distinct('titulo')]
            queryset = queryset.filter(id__in=ids_dos_codigos_unicos).order_by('ano')
        else:
            queryset = queryset.order_by('ano')

        if classificacao_evento:
            queryset = queryset.filter(id__in=TrabalhoEvento.objects.filter(classificacao_evento=classificacao_evento).values_list('id', flat=True))
        if servidor:
            queryset = queryset.filter(curriculo__vinculo=servidor.get_vinculo())

        if grupo_pesquisa:
            queryset = queryset.filter(curriculo__grupos_pesquisa=grupo_pesquisa)

        if apenas_no_exercicio:
            queryset = queryset.filter(curriculo__ano_inicio_exercicio__isnull=False).exclude(ano__lt=F('curriculo__ano_inicio_exercicio'))
            queryset = queryset.filter(curriculo__ano_fim_exercicio__isnull=False).exclude(
                ano__gt=F('curriculo__ano_fim_exercicio')
            ) | queryset.filter(curriculo__ano_fim_exercicio__isnull=True)

        if aluno:
            queryset = queryset.filter(curriculo__vinculo=aluno.get_vinculo())

        if campus:
            queryset_alunos = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Aluno.objects.filter(curso_campus__diretoria__setor__uo=campus).values_list('id', flat=True)
            )
            queryset = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Servidor.objects.filter(setor__uo=campus).values_list('id', flat=True)
            )
            queryset = (queryset_alunos | queryset).distinct()

        if programa_posgraduacao:
            ids_cursos_campus = CursoProgramaPos.objects.filter(programa=programa_posgraduacao).values_list('curso__id', flat=True)
            queryset_alunos = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Aluno.objects.filter(curso_campus__in=ids_cursos_campus).values_list('id', flat=True)
            )
            queryset = queryset.filter(
                curriculo__vinculo__id__in=DocenteProgramaPos.objects.filter(programa=programa_posgraduacao).values_list(
                    'docente__vinculo__id', flat=True
                )
            )
            queryset = (queryset_alunos | queryset).distinct()

        return queryset

    @classmethod
    def get_anos_qtd(cls, tipo=None, categoria=None, campus=None, ano_ini=None, ano_fim=None):
        queryset = cls.filtrar(tipo, categoria, campus, ano_ini, ano_fim)
        return queryset.values_list('ano').annotate(qtd=Count('id')).order_by('ano')

    @classmethod
    def get_tipo_qtd(
        cls,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        queryset = cls.filtrar(
            None,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        return queryset.values_list('tipo_pub').annotate(qtd=Count('id')).order_by()  # Remoção de order_by por ano do método filtrar

    @classmethod
    def get_ano_tipo_qtd(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        grupo_pesquisa=None,
        apenas_no_exercicio=None,
    ):
        queryset = cls.filtrar(
            tipo,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            natureza_evento,
            classificacao_evento,
            qualis_capes,
            servidor,
            grupo_pesquisa,
            apenas_no_exercicio,
        )
        return queryset.values('ano', 'tipo_pub').annotate(qtd=Count('titulo', distinct=True)).order_by('ano')


class TrabalhoEvento(ProducaoBibliografica):
    NATUREZA_COMPLETO = 'COMPLETO'
    NATUREZA_RESUMO = 'RESUMO'
    NATUREZA_RESUMO_EXPANDIDO = 'RESUMO_EXPANDIDO'
    natureza_choices = {NATUREZA_COMPLETO: 'Completo', NATUREZA_RESUMO: 'Resumo', NATUREZA_RESUMO_EXPANDIDO: 'Resumo Expandido'}

    classificacao_evento_choices = {
        'INTERNACIONAL': 'Internacional',
        'NACIONAL': 'Nacional',
        'REGIONAL': 'Regional',
        'LOCAL': 'Local',
        'NAO_INFORMADO': 'Não Informado',
    }
    classificacao_evento = models.TextField()
    nome_evento = models.TextField()
    cidade_evento = models.TextField()
    ano_realizacao = models.TextField()
    titulo_anais_proceeding = models.TextField()
    volume = models.TextField()
    fasciculo = models.TextField()
    serie = models.TextField()
    pagina_inicial = models.TextField()
    pagina_final = models.TextField()
    isbn = models.TextField()
    nome_editora = models.TextField()
    cidade_editora = models.TextField()

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.nome_evento:
            retorno += f'In: {self.nome_evento}, '
        if self.ano_realizacao:
            retorno += f'{self.ano_realizacao}, '
        if self.cidade_evento:
            retorno += f'{self.cidade_evento}. '
        if self.titulo_anais_proceeding:
            retorno += f'{self.titulo_anais_proceeding}. '
        if self.cidade_editora:
            retorno += f'{self.cidade_editora}: {self.nome_editora}, {self.ano}. '
        if self.volume:
            retorno += f'v. {self.volume}. '
        if self.pagina_inicial and self.pagina_final:
            retorno += f'p. {self.pagina_inicial}-{self.pagina_final}. '
        if self.classificacao_evento:
            retorno += f' ({self.classificacao_evento}). '
        return retorno

    def get_natureza(self):
        return self.natureza_choices[self.natureza]

    def get_classificacao_evento(self):
        return self.classificacao_evento_choices[self.classificacao_evento]


class Artigo(ProducaoBibliografica):
    NATUREZA_COMPLETO = 'COMPLETO'
    NATUREZA_RESUMO = 'RESUMO'
    NATUREZA_NAO_INFORMADO = 'NAO_INFORMADO'
    natureza_choices = {NATUREZA_COMPLETO: 'Completo', NATUREZA_RESUMO: 'Resumo', NATUREZA_NAO_INFORMADO: 'Não Informado'}
    tipo_choices = {'ARTIGOS-PUBLICADOS': 'Artigo Publicado', 'ARTIGOS-ACEITOS-PARA-PUBLICACAO': 'Artigo Aceito'}
    titulo_periodico_revista = models.TextField()
    tipo = models.TextField()  # publicado ou aceito
    issn = models.TextField()
    volume = models.TextField()
    fasciculo = models.TextField()
    serie = models.TextField()
    pagina_inicial = models.TextField()
    pagina_final = models.TextField()
    local_publicacao = models.TextField()
    periodico = models.ForeignKeyPlus('cnpq.PeriodicoRevista', null=True, on_delete=models.CASCADE)

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.titulo_periodico_revista:
            retorno += f'{self.titulo_periodico_revista}, '
        if self.local_publicacao:
            retorno += f'{self.local_publicacao}, '
        if self.volume:
            retorno += f'v. {self.volume}, '
        if self.pagina_inicial:
            retorno += f'p. {self.pagina_inicial}'
            if self.pagina_final:
                retorno += f'-{self.pagina_final}, '
        if self.ano:
            retorno += f'{self.ano}. '
        if self.periodico and self.periodico.estratos_qualis.exists():
            retorno += ' (Maior Qualis: {} - {}) '.format(
                self.periodico.estratos_qualis.all().order_by('estrato')[0].estrato,
                self.periodico.estratos_qualis.all().order_by('estrato')[0].area_avaliacao,
            )
        return retorno

    def get_natureza(self):
        return self.natureza_choices[self.natureza]

    def get_tipo(self):
        return self.tipo_choices[self.tipo]


class Livro(ProducaoBibliografica):
    tipo_choices = {
        'LIVRO_PUBLICADO': 'Livro Publicado',
        'LIVRO_ORGANIZADO_OU_EDICAO': 'Livro Organizado ou Edição',
        'NAO_INFORMADO': 'Não Informado',
    }
    natureza_choices = {
        'COLETANEA': 'Coletânea',
        'TEXTO_INTEGRAL': 'Texto Integral',
        'VERBETE': 'Verbete',
        'ANAIS': 'Anais',
        'CATALOGO': 'Catálogo',
        'ENCICLOPEDIA': 'Enciclopédia',
        'LIVRO': 'Livro',
        'OUTRA': 'Outra',
        'PERIODICO': 'Periódico',
        'NAO_INFORMADO': 'Não Informado',
    }
    tipo = models.TextField()
    numero_volumes = models.TextField()
    numero_paginas = models.TextField()
    isbn = models.TextField()
    numero_edicao_revisao = models.TextField()
    numero_serie = models.TextField()
    cidade_editora = models.TextField()
    nome_editora = models.TextField()

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.numero_edicao_revisao:
            retorno += f'{self.numero_edicao_revisao}. ed. '
        if self.cidade_editora and self.nome_editora and self.ano:
            retorno += f'{self.cidade_editora}: {self.nome_editora}, {self.ano}. '
        if self.numero_volumes:
            retorno += f'v. {self.numero_volumes}. '
        if self.numero_paginas:
            retorno += f'{self.numero_paginas}p .'
        return retorno

    def get_natureza(self):
        return self.natureza_choices[self.natureza]

    def get_tipo(self):
        return self.tipo_choices[self.tipo]


class Capitulo(ProducaoBibliografica):
    tipo = models.TextField()
    titulo_livro = models.TextField()
    numero_volumes = models.TextField()
    pagina_inicial = models.TextField()
    pagina_final = models.TextField()
    isbn = models.TextField()
    organizadores = models.TextField()
    numero_edicao_revisao = models.TextField()
    numero_serie = models.TextField()
    cidade_editora = models.TextField()
    nome_editora = models.TextField()

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.organizadores:
            retorno += f'In: {self.organizadores}. '
        if self.titulo_livro:
            retorno += f'(Org.). {self.titulo_livro}. '
        if self.numero_edicao_revisao:
            retorno += f'{self.numero_edicao_revisao}ed. '
        if self.cidade_editora and self.cidade_editora and self.ano:
            retorno += f'{self.cidade_editora}: {self.nome_editora}, {self.ano}. '
        if self.numero_volumes:
            retorno += f'v. {self.numero_volumes}. '
        if self.pagina_inicial and self.pagina_final:
            retorno += f'p. {self.pagina_inicial}-{self.pagina_final}. '
        return retorno


class TextoJonalRevista(ProducaoBibliografica):
    natureza_choices = {'JORNAL_DE_NOTICIAS': 'Jornal de Notícias', 'REVISTA_MAGAZINE': 'Revista/Magazine', 'NAO_INFORMADO': 'Não Informado'}
    titulo_jonal_revista = models.TextField()
    issn = models.TextField()
    data_publicacao = models.DateField(null=True)
    volume = models.TextField()
    pagina_inicial = models.TextField()
    pagina_final = models.TextField()
    local_publicacao = models.TextField()

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.titulo_jonal_revista:
            retorno += '{}, {}, {}. '.format(
                self.titulo_jonal_revista, self.local_publicacao, _date(self.data_publicacao, 'd b. Y')
            )  # formato de data 01 abr. 2009
        return retorno

    def get_natureza(self):
        return self.natureza_choices[self.natureza]


class PrefacioPosfacio(ProducaoBibliografica):
    tipo_choices = {'PREFACIO': 'Prefácio', 'POSFACIO': 'Posfácio', 'APRESENTACAO': 'Apresentação', 'INTRODUCAO': 'Introdução'}
    natureza_choices = {'LIVRO': 'Livro', 'OUTRA': 'Outra', 'REVISTAS_OU_PERIODICOS': 'Revistras/Periódicos', 'NAO_INFORMADO': 'Não Informado'}
    tipo = models.TextField()
    nome_autor_publicacao = models.TextField()
    titulo_publicacao = models.TextField()
    issn_isbn = models.TextField()
    numero_edicao_revisao = models.TextField()
    volume = models.TextField()
    serie = models.TextField()
    fasciculo = models.TextField()
    editora_prefacio_posfacio = models.TextField()
    cidade_editora = models.TextField()

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.cidade_editora:
            retorno += f'{self.cidade_editora}, {self.ano}. '
        return retorno

    def get_tipo(self):
        return self.tipo_choices[self.tipo]

    def get_natureza(self):
        return self.natureza_choices[self.natureza]


class Partitura(ProducaoBibliografica):
    natureza_choices = {'CANTO': 'Canto', 'CORAL': 'Coral', 'ORQUESTRA': 'Orquestra', 'OUTRO': 'Outro', 'NAO_INFORMADO': 'Não Informado'}
    formacao_instrumental = models.TextField()
    editora = models.TextField()
    cidade_editora = models.TextField()
    numero_paginas = models.TextField()
    numero_catalogo = models.TextField()

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.ano:
            retorno += f'{self.ano}. '
        return retorno

    def get_natureza(self):
        return self.natureza_choices[self.natureza]


class Traducao(ProducaoBibliografica):
    natureza_choices = {'ARTIGO': 'Artigo', 'LIVRO': 'Livro', 'OUTRO': 'Outro', 'NAO_INFORMADO': 'Não Informado'}
    nome_autor_traduzido = models.TextField()
    titulo_obra_original = models.TextField()
    issn_isbn = models.TextField()
    idioma_obra_original = models.TextField()
    editora_traducao = models.TextField()
    cidade_editora = models.TextField()
    numero_paginas = models.TextField()
    numero_edicao_revisao = models.TextField()
    volume = models.TextField()
    fasciculo = models.TextField()
    serie = models.TextField()

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.ano:
            retorno += f'{self.editora_traducao}, {self.ano}. '
        return retorno

    def get_natureza(self):
        return self.natureza_choices[self.natureza]


class OutraProducaoBibliografica(ProducaoBibliografica):
    editora = models.TextField()
    cidade_editora = models.TextField()
    numero_paginas = models.TextField()
    issn_isbn = models.TextField()

    def __str__(self):
        retorno = self.get_autores_titulo_unicode()
        if self.ano:
            retorno += f'{self.ano}. '
        if self.natureza:
            retorno += f'({self.natureza}). '
        return retorno


class Autor(models.ModelPlus):
    nome_completo = models.TextField()
    nome_citacao = models.TextField()
    ordem = models.TextField()
    cpf = models.TextField()

    def __str__(self):
        return self.nome_citacao


class InformacaoAdicinal(models.ModelPlus):
    descricao = models.TextField()

    def __str__(self):
        return self.descricao


#########################
#   PRODUCAO TECNICA    #
#########################
class ProducaoTecnica(models.ModelPlus):
    tipo_pub_choices = {
        'SOFTWARE': 'Softwares',
        'PRODUTO-TECNOLOGICO': 'Produtos Tecnológicos ',
        'PROCESSOS-OU-TECNICAS': 'Processos ou Técnicas',
        'TRABALHO-TECNICO': 'Trabalhos Técnicos',
        'APRESENTACAO-DE-TRABALHO': 'Apresentações de Trabalho',
        'CARTA-MAPA-OU-SIMILAR': 'Cartas, Mapas ou Similares',
        'CURSO-DE-CURTA-DURACAO-MINISTRADO': 'Cursos de Curta Duração Ministrados',
        'DESENVOLVIMENTO-DE-MATERIAL-DIDATICO-OU-INSTRUCIONAL': 'Desenvolvimento de Materiais Didáticos ou Instrucionais',
        'EDITORACAO': 'Editorações',
        'MANUTENCAO-DE-OBRA-ARTISTICA': 'Manutenção em Obras Artísticas',
        'MAQUETE': 'Maquetes',
        'ORGANIZACAO-DE-EVENTO': 'Organização de Eventos',
        'OUTRA-PRODUCAO-TECNICA': 'Outras Produções Técnicas',
        'PROGRAMA-DE-RADIO-OU-TV': 'Programas de Rádio ou TV',
        'RELATORIO-DE-PESQUISA': 'Relatórios de Pesquisa',
        'PATENTE': 'Patentes',
        'MARCA': 'Marca',
        'DESENHO-INDUSTRIAL': 'Desenho Insdustrial',
    }

    curriculo = models.ForeignKeyPlus('cnpq.CurriculoVittaeLattes', related_name='producoes_tecnicas', on_delete=models.CASCADE)
    sequencia = models.TextField()
    titulo = models.TextField()
    ano = models.TextField()
    pais = models.TextField()
    idioma = models.TextField()
    flag_relevancia = models.BooleanField(null=True)
    doi = models.TextField()
    tipo_pub = models.TextField()
    autores = models.ManyToManyField('cnpq.Autor')
    palavras_chave = models.ManyToManyField('cnpq.PalavraChave')
    areas_conhecimento = models.ManyToManyField('cnpq.AreaConhecimento')
    setores_atividade = models.ManyToManyField('cnpq.SetorAtividade')
    informacao_adicional = models.OneToOneField('cnpq.InformacaoAdicinal', null=True, on_delete=models.CASCADE)

    def delete(self):
        autores = self.autores.all()
        for autor in autores:
            autor.delete()

        palavras_chave = self.palavras_chave.all()
        for palavra in palavras_chave:
            palavra.delete()

        areas_conhecimento = self.areas_conhecimento.all()
        for area in areas_conhecimento:
            area.delete()

        setores_atividade = self.setores_atividade.all()
        for setor in setores_atividade:
            setor.delete()

        if self.informacao_adicional:
            self.informacao_adicional.delete()

        super().delete()

    def __str__(self):
        retorno = ''
        for autor in self.get_autores():
            retorno += autor.nome_citacao + '; '
        retorno += self.titulo + '. ' + self.ano + '.'
        return retorno

    def get_relevancia_doi(self):
        retorno = ''
        if self.flag_relevancia:
            retorno += '<img src="http://buscatextual.cnpq.br/buscatextual/images/curriculo/ico_relevante.gif">'
        if self.doi:
            retorno += (
                '<a style="background: url(\'http://buscatextual.cnpq.br/buscatextual/images/v2/ico_doi.gif\') no-repeat scroll 0 0 transparent;display: inline-block;height: 11px;width: 26px;margin-right: 5px;" target="_blank" href="http://dx.doi.org/'
                + self.doi
                + '" tabindex="230"></a>'
            )
        return retorno

    def get_autores(self):
        return self.autores.order_by('ordem')

    def get_ano(self):
        return self.ano

    def get_tipo(self):
        return self.tipo_pub_choices[self.tipo_pub] or 'Não informado'

    def get_autores_unicos(self):
        ids = ProducaoTecnica.objects.filter(titulo=self.titulo, curriculo__vinculo__isnull=False).values_list('curriculo__vinculo', flat=True)
        return VinculoPessoa.objects.filter(id__in=ids)

    @classmethod
    def filtrar(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        from edu.models import Aluno
        from pesquisa.models import CursoProgramaPos, DocenteProgramaPos

        queryset = cls.objects.all()
        if tipo:
            queryset = queryset.filter(tipo_pub=tipo)

        if categoria:
            if categoria == 'aluno':
                queryset = queryset.filter(curriculo__vinculo__tipo_relacionamento__model=categoria)
            else:
                queryset = queryset.filter(
                    curriculo__vinculo__id_relacionamento__in=Servidor.objects.filter(
                        cargo_emprego__grupo_cargo_emprego__categoria=categoria
                    ).values_list('id', flat=True)
                )

        if ano_ini:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(ano=None)
            else:
                queryset = queryset.filter(ano__gte=ano_ini)

        if ano_fim:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(ano=None)
            else:
                queryset = queryset.filter(ano__lte=ano_fim)

        if servidor:
            queryset = queryset.filter(curriculo__vinculo=servidor.get_vinculo())

        if grupo_pesquisa:
            queryset = queryset.filter(curriculo__grupos_pesquisa=grupo_pesquisa)

        if apenas_no_exercicio:
            queryset = (
                queryset.filter(curriculo__ano_inicio_exercicio__isnull=False)
                .annotate(ano_inteiro=Cast('ano', IntegerField()))
                .exclude(ano_inteiro__lt=F('curriculo__ano_inicio_exercicio'))
            )
            queryset = queryset.filter(curriculo__ano_fim_exercicio__isnull=False).annotate(ano_inteiro=Cast('ano', IntegerField())).exclude(
                ano_inteiro__gt=F('curriculo__ano_fim_exercicio')
            ) | queryset.filter(curriculo__ano_fim_exercicio__isnull=True)

        if aluno:
            queryset = queryset.filter(curriculo__vinculo=aluno.get_vinculo())

        if campus:
            queryset_alunos = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Aluno.objects.filter(curso_campus__diretoria__setor__uo=campus).values_list('id', flat=True)
            )
            queryset = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Servidor.objects.filter(setor__uo=campus).values_list('id', flat=True)
            )
            queryset = (queryset_alunos | queryset).distinct()

        if programa_posgraduacao:
            ids_cursos_campus = CursoProgramaPos.objects.filter(programa=programa_posgraduacao).values_list('curso__id', flat=True)
            queryset_alunos = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Aluno.objects.filter(curso_campus__in=ids_cursos_campus).values_list('id', flat=True)
            )
            queryset = queryset.filter(
                curriculo__vinculo__id__in=DocenteProgramaPos.objects.filter(programa=programa_posgraduacao).values_list(
                    'docente__vinculo__id', flat=True
                )
            )
            queryset = (queryset_alunos | queryset).distinct()

        if not running_tests():
            ids_dos_codigos_unicos = [indice['id'] for indice in queryset.values('id', 'titulo').distinct('titulo')]
            return queryset.filter(id__in=ids_dos_codigos_unicos).order_by('ano')
        else:
            return queryset.order_by('ano')

    @classmethod
    def get_anos_qtd(cls, tipo=None, categoria=None, campus=None, ano_ini=None, ano_fim=None):
        queryset = cls.filtrar(tipo, categoria, campus, ano_ini, ano_fim)
        return queryset.values_list('ano').annotate(qtd=Count('id')).order_by('ano')

    @classmethod
    def get_tipo_qtd(
        cls,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        queryset = cls.filtrar(
            None,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )

        return queryset.values_list('tipo_pub').annotate(qtd=Count('id')).order_by()  # Remoção de order_by por ano do método filtrar

    @classmethod
    def get_ano_tipo_qtd(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        grupo_pesquisa=None,
        apenas_no_exercicio=None,
    ):
        queryset = cls.filtrar(
            tipo,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            natureza_evento,
            classificacao_evento,
            qualis_capes,
            servidor,
            grupo_pesquisa,
            apenas_no_exercicio,
        )

        return queryset.values('ano', 'tipo_pub').annotate(qtd=Count('titulo', distinct=True)).order_by('ano')


class Software(ProducaoTecnica):
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    finalidade = models.TextField()
    plataforma = models.TextField()
    ambiente = models.TextField()
    disponibilidade = models.TextField()
    instituicao_financiadora = models.TextField()
    registros_patentes = models.ManyToManyField('cnpq.RegistroPatente')

    @transaction.atomic
    def delete(self):
        registros_patentes = self.registros_patentes.all()
        for patente in registros_patentes:
            patente.delete()

        self.producaotecnica_ptr.delete()


class ProdutoTecnologico(ProducaoTecnica):
    tipo_produto = models.TextField()
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    finalidade = models.TextField()
    disponibilidade = models.TextField()
    cidade_produto = models.TextField()
    instituicao_financiadora = models.TextField()
    registros_patentes = models.ManyToManyField('cnpq.RegistroPatente')

    @transaction.atomic
    def delete(self):
        registros_patentes = self.registros_patentes.all()
        for patente in registros_patentes:
            patente.delete()

        self.producaotecnica_ptr.delete()


class ProcessoTecnica(ProducaoTecnica):
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    finalidade = models.TextField()
    disponibilidade = models.TextField()
    instituicao_financiadora = models.TextField()
    cidade_processo = models.TextField()
    registros_patentes = models.ManyToManyField('cnpq.RegistroPatente')

    @transaction.atomic
    def delete(self):
        registros_patentes = self.registros_patentes.all()
        for patente in registros_patentes:
            patente.delete()

        self.producaotecnica_ptr.delete()


class Patente(ProducaoTecnica):
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    flag_potencial_inovacao = models.TextField()
    finalidade = models.TextField()
    instituicao_financiadora = models.TextField()
    categoria = models.TextField()
    registros_patentes = models.ManyToManyField('cnpq.RegistroPatente')

    @transaction.atomic
    def delete(self):
        registros_patentes = self.registros_patentes.all()
        for patente in registros_patentes:
            patente.delete()

        self.producaotecnica_ptr.delete()


class Marca(ProducaoTecnica):
    flag_potencial_inovacao = models.TextField()
    finalidade = models.TextField()
    natureza = models.TextField()
    registros_patentes = models.ManyToManyField('cnpq.RegistroPatente')

    @transaction.atomic
    def delete(self):
        registros_patentes = self.registros_patentes.all()
        for patente in registros_patentes:
            patente.delete()

        self.producaotecnica_ptr.delete()


class DesenhoIndustrial(ProducaoTecnica):
    flag_potencial_inovacao = models.TextField()
    finalidade = models.TextField()
    instituicao_financiadora = models.TextField()
    registros_patentes = models.ManyToManyField('cnpq.RegistroPatente')

    @transaction.atomic
    def delete(self):
        registros_patentes = self.registros_patentes.all()
        for patente in registros_patentes:
            patente.delete()

        self.producaotecnica_ptr.delete()


class TrabalhoTecnico(ProducaoTecnica):
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    finalidade = models.TextField()
    duracao_meses = models.TextField()
    numero_paginas = models.TextField()
    disponibilidade = models.TextField()
    instituicao_financiadora = models.TextField()
    cidade_trabalho = models.TextField()


class ApresentacaoTrabalho(ProducaoTecnica):
    natureza = models.TextField()
    nome_evento = models.TextField()
    instituicao_promotora = models.TextField()
    local_apresentacao = models.TextField()
    cidade_apresentacao = models.TextField()


class CartaMapaSimilar(ProducaoTecnica):
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page_trabalho = models.TextField()
    tema = models.TextField()
    tecnica_utilizada = models.TextField()
    finalidade = models.TextField()
    area_representada = models.TextField()
    instituicao_financiadora = models.TextField()


class CursoCurtaDuracaoMinistrado(ProducaoTecnica):
    nivel_curso = models.TextField()
    meio_divulgacao = models.TextField()
    home_page_trabalho = models.TextField()
    participacao_autores = models.TextField()
    instituicao_promotora_curso = models.TextField()
    local_curso = models.TextField()
    cidade = models.TextField()
    duracao = models.TextField()
    unidade = models.TextField()


# class DesenvolvimentoMaterialDidativoInstrucional(ProducaoTecnica):
class DesMatDidativoInstrucional(ProducaoTecnica):
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page_trabalho = models.TextField()
    finalidade = models.TextField()

    class Meta:
        db_table = 'desmatdidativoinstrucional'


class Editoracao(ProducaoTecnica):
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    numero_paginas = models.TextField()
    instituicao_promotora = models.TextField()
    editora = models.TextField()
    cidade = models.TextField()


class ManutencaoObraArtistica(ProducaoTecnica):
    tipo = models.TextField()
    natureza = models.TextField()
    nome_obra = models.TextField()
    autor_obra = models.TextField()
    ano_obra = models.TextField()
    arcevo = models.TextField()
    local = models.TextField()
    cidade = models.TextField()


class Maquete(ProducaoTecnica):
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    finalidade = models.TextField()
    objetivo_representador = models.TextField()
    material_utilizado = models.TextField()
    instituicao_financiadora = models.TextField()


class OrganizacaoEventos(ProducaoTecnica):
    tipo = models.TextField()
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    instituicao_promotora = models.TextField()
    duracao_semanas = models.TextField()
    flag_evento_itinerante = models.BooleanField(null=True)
    flag_catalogo = models.TextField()
    local = models.TextField()
    cidade = models.TextField()


class OutraProducaoTecnica(ProducaoTecnica):
    natureza = models.TextField()
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    finalidade = models.TextField()
    instituicao_promotora = models.TextField()
    local = models.TextField()
    cidade = models.TextField()


class ProgramaRadioTV(ProducaoTecnica):
    natureza = models.TextField()
    emissora = models.TextField()
    tema = models.TextField()
    data_apresentacao = models.DateField(null=True)
    duracao_minutos = models.TextField()
    cidade = models.TextField()


class RelatorioPesquisa(ProducaoTecnica):
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    nome_projeto = models.TextField()
    numero_paginas = models.TextField()
    disponibilidade = models.TextField()
    instituicao_financiadora = models.TextField()


class RegistroPatente(models.ModelPlus):
    tipo_choices = {
        'SOFTWARE': 'Software',
        'PRODUTO-TECNOLOGICO': 'Produtos Tecnológicos',
        'PROCESSOS-OU-TECNICAS': 'Processos ou Técnicas',
        'PATENTE': 'Patente',
        'MARCA': 'Marca',
        'DESENHO-INDUSTRIAL': 'Desenho Insdustrial',
    }

    # Relação do tipo de publicação com o relacionamento
    tipo_relacao_choices = {
        'SOFTWARE': 'software',
        'PRODUTO-TECNOLOGICO': 'produtotecnologico',
        'PROCESSOS-OU-TECNICAS': 'processotecnica',
        'PATENTE': 'patente',
        'MARCA': 'marca',
        'DESENHO-INDUSTRIAL': 'desenhoindustrial',
    }

    curriculo = models.ForeignKeyPlus(
        'cnpq.CurriculoVittaeLattes', related_name='patentes_registros', default=None, null=True, on_delete=models.CASCADE
    )
    tipo = models.TextField()
    codigo = models.TextField()
    titulo = models.TextField()
    data_pedido_deposito = models.DateField(null=True)
    data_pedido_exame = models.DateField(null=True)
    data_concessao = models.DateField(null=True)

    def __str__(self):
        data_pedido_deposito = self.data_pedido_deposito or ''
        if self.data_pedido_deposito:
            data_pedido_deposito = self.data_pedido_deposito.strftime('%d/%m/%Y')
        return f'Registros ou Patente: {self.get_tipo()}. Número do registro: {self.codigo}, data de registro: {data_pedido_deposito}, título: "{self.titulo}"'

    def get_tipo(self):
        for label, relacao in list(self.tipo_relacao_choices.items()):
            if getattr(self, relacao + '_set').exists():
                return self.tipo_choices[label]

        return 'Não informado'

    def get_ano(self):
        return self.data_pedido_deposito and self.data_pedido_deposito.year or None

    def get_autores_unicos(self):
        ids = RegistroPatente.objects.filter(codigo=self.codigo, curriculo__vinculo__isnull=False).values_list('curriculo__vinculo', flat=True)
        return VinculoPessoa.objects.filter(id__in=ids)

    @classmethod
    def filtrar(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        from edu.models import Aluno
        from pesquisa.models import CursoProgramaPos, DocenteProgramaPos

        queryset = cls.objects.all()
        if tipo and cls.tipo_relacao_choices.get(tipo):
            relacionamento = cls.tipo_relacao_choices[tipo]
            filter = {relacionamento + '__isnull': False}
            queryset = queryset.filter(**filter)

        if categoria:
            if categoria == 'aluno':
                queryset = queryset.filter(curriculo__vinculo__tipo_relacionamento__model=categoria)
            else:
                queryset = queryset.filter(
                    curriculo__vinculo__id_relacionamento__in=Servidor.objects.filter(
                        cargo_emprego__grupo_cargo_emprego__categoria=categoria
                    ).values_list('id', flat=True)
                )

        if ano_ini:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(data_pedido_deposito=None)
            else:
                queryset = queryset.filter(data_pedido_deposito__gte=date(int(ano_ini), 0o1, 0o1))
        if ano_fim:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(data_pedido_deposito=None)
            else:
                queryset = queryset.filter(data_pedido_deposito__lte=date(int(ano_fim), 12, 31))
        if servidor:
            queryset = queryset.filter(curriculo__vinculo=servidor.get_vinculo())

        if grupo_pesquisa:
            queryset = queryset.filter(curriculo__grupos_pesquisa=grupo_pesquisa)

        if apenas_no_exercicio:
            queryset = (
                queryset.filter(curriculo__ano_inicio_exercicio__isnull=False)
                .annotate(ano_inteiro=Cast(ExtractYear('data_pedido_deposito'), IntegerField()))
                .exclude(ano_inteiro__lt=F('curriculo__ano_inicio_exercicio'))
            )
            queryset = queryset.filter(curriculo__ano_fim_exercicio__isnull=False).annotate(
                ano_inteiro=Cast(ExtractYear('data_pedido_deposito'), IntegerField())
            ).exclude(ano_inteiro__gt=F('curriculo__ano_fim_exercicio')) | queryset.filter(curriculo__ano_fim_exercicio__isnull=True)

        if aluno:
            queryset = queryset.filter(curriculo__vinculo=aluno.get_vinculo())

        if campus:
            queryset_alunos = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Aluno.objects.filter(curso_campus__diretoria__setor__uo=campus).values_list('id', flat=True)
            )
            queryset = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Servidor.objects.filter(setor__uo=campus).values_list('id', flat=True)
            )
            queryset = (queryset_alunos | queryset).distinct()

        if programa_posgraduacao:
            ids_cursos_campus = CursoProgramaPos.objects.filter(programa=programa_posgraduacao).values_list('curso__id', flat=True)
            queryset_alunos = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Aluno.objects.filter(curso_campus__in=ids_cursos_campus).values_list('id', flat=True)
            )
            queryset = queryset.filter(
                curriculo__vinculo__id__in=DocenteProgramaPos.objects.filter(programa=programa_posgraduacao).values_list(
                    'docente__vinculo__id', flat=True
                )
            )
            queryset = (queryset_alunos | queryset).distinct()

        if not running_tests():
            ids_dos_codigos_unicos = [indice['id'] for indice in queryset.values('id', 'codigo').distinct('codigo')]
            return queryset.filter(id__in=ids_dos_codigos_unicos).order_by('data_pedido_deposito')
        else:
            return queryset.order_by('data_pedido_deposito')

    @classmethod
    def get_anos_qtd(cls, tipo=None, categoria=None, campus=None, ano_ini=None, ano_fim=None):
        queryset = cls.filtrar(tipo, categoria, campus, ano_ini, ano_fim)
        return (
            queryset.extra(select={'ano': "COALESCE(EXTRACT(YEAR FROM data_pedido_deposito)::INT::TEXT, '')"})
            .values_list('ano')
            .annotate(qtd=Count('id'))
            .order_by('ano')
        )

    @classmethod
    def get_tipo_qtd(
        cls,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        retorno = []
        queryset = cls.filtrar(
            None,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        for key, value in list(cls.tipo_relacao_choices.items()):
            filter = {value + '__isnull': False}
            qtd = queryset.filter(**filter).count()
            dado = [key, qtd]
            retorno.append(dado)

        return retorno

    @classmethod
    def get_ano_tipo_qtd(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        grupo_pesquisa=None,
        apenas_no_exercicio=None,
    ):
        retorno = []
        queryset = cls.filtrar(
            tipo,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            natureza_evento,
            classificacao_evento,
            qualis_capes,
            servidor,
            grupo_pesquisa,
            apenas_no_exercicio,
        )
        for key, value in list(cls.tipo_relacao_choices.items()):
            filter = {value + '__isnull': False}
            temp_queryset = queryset.filter(**filter)
            temp_queryset = (
                temp_queryset.extra(select={'ano': "COALESCE(EXTRACT(YEAR FROM data_pedido_deposito)::INT::TEXT, '')"})
                .values('ano')
                .annotate(qtd=Count('codigo', distinct=True))
                .order_by('ano')
            )
            if not temp_queryset:
                dado = {'ano': 0, 'qtd': 0, 'tipo_pub': key}
                retorno.append(dado)

            for dado in temp_queryset:
                if not dado['ano']:
                    dado['ano'] = 'Não informado'
                dado['tipo_pub'] = key
                retorno.append(dado)

        return retorno


######################################
#    OUTRA PRODUCAO BIBLIOGRAFICA    #
######################################
class OutraProducao(models.ModelPlus):
    tipo_choices = {
        'PRODUCAO-ARTISTICA-CULTURAL': 'Produções Artísticas-Culturais',
        'ORIENTACOES-CONCLUIDAS': 'Orientações Concluídas',
        'DEMAIS-TRABALHOS': 'Demais Trabalhos',
    }

    curriculo = models.ForeignKeyPlus('cnpq.CurriculoVittaeLattes', related_name='outras_producoes', on_delete=models.CASCADE)
    sequencia = models.TextField()
    natureza = models.TextField()
    titulo = models.TextField()
    ano = models.TextField()
    pais = models.TextField()
    flag_relevancia = models.BooleanField(null=True)
    doi = models.TextField()
    tipo = models.TextField()

    autores = models.ManyToManyField('cnpq.Autor')
    palavras_chave = models.ManyToManyField('cnpq.PalavraChave')
    areas_conhecimento = models.ManyToManyField('cnpq.AreaConhecimento')
    setores_atividade = models.ManyToManyField('cnpq.SetorAtividade')
    informacao_adicional = models.OneToOneField('cnpq.InformacaoAdicinal', null=True, on_delete=models.CASCADE)

    def delete(self):
        autores = self.autores.all()
        for autor in autores:
            autor.delete()

        palavras_chave = self.palavras_chave.all()
        for palavra in palavras_chave:
            palavra.delete()

        areas_conhecimento = self.areas_conhecimento.all()
        for area in areas_conhecimento:
            area.delete()

        setores_atividade = self.setores_atividade.all()
        for setor in setores_atividade:
            setor.delete()

        if self.informacao_adicional:
            self.informacao_adicional.delete()

        super().delete()


class OrientacaoConcluida(OutraProducao):
    tipo_choices = {
        'ORIENTACOES-CONCLUIDAS-PARA-MESTRADO': 'Orientações de Mestrado',
        'ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO': 'Orientações de Doutorado',
        'ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO': 'Orientações de Pós-Doutorado',
        'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 'Orientações de Aperfeiçoamento/Especialização',
        'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 'Orientações de Graduação',
        'INICIACAO_CIENTIFICA': 'Orientações de Iniciação Científica',
        'ORIENTACAO-DE-OUTRA-NATUREZA': 'Outras Orientações',
    }

    tipo_mestrado_choices = {'ACADEMICO': 'Acadêmico', 'PROFISSIONALIZANTE': 'Profissionalizante'}

    natureza_choices = {
        'MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO': 'Orientações de Aperfeiçoamento/Especialização',
        'TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO': 'Orientações de Graduação',
        'INICIACAO_CIENTIFICA': 'Orientações de Iniciação Científica',
        'OUTRAS-ORIENTACOES-CONCLUIDAS': 'Outras Orientações',
    }

    tipo_orientacao = models.TextField()
    tipo_mestrado = models.TextField()
    idioma = models.TextField()
    home_page = models.TextField()
    nome_orientando = models.TextField()
    nome_instituicao = models.TextField()
    nome_orgao = models.TextField()
    nome_curso = models.TextField()
    flag_bolsa = models.BooleanField(null=True)
    nome_agencia_financiadora = models.TextField()
    numero_paginas = models.TextField()

    def __str__(self):
        tipo = self.tipo_choices[self.tipo]
        return f'{self.nome_orientando}. {self.titulo}. Início: {self.ano}. {tipo} (em {self.nome_curso}) - {self.nome_instituicao}.'

    def get_autores_unicos(self):
        ids = OrientacaoConcluida.objects.filter(id=self.id, curriculo__vinculo__isnull=False).values_list('curriculo__vinculo', flat=True)
        return VinculoPessoa.objects.filter(id__in=ids)

    def get_ano(self):
        return self.ano

    def get_tipo(self):
        return self.tipo_choices[self.tipo] or 'Não informado'

    @classmethod
    def filtrar(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        from edu.models import Aluno
        from pesquisa.models import CursoProgramaPos, DocenteProgramaPos

        queryset = cls.objects.all()
        if tipo:
            queryset = queryset.filter(tipo_pub=tipo)

        if categoria:
            if categoria == 'aluno':
                queryset = queryset.filter(curriculo__vinculo__tipo_relacionamento__model=categoria)
            else:
                queryset = queryset.filter(
                    curriculo__vinculo__id_relacionamento__in=Servidor.objects.filter(
                        cargo_emprego__grupo_cargo_emprego__categoria=categoria
                    ).values_list('id', flat=True)
                )

        if ano_ini:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(ano=None)
            else:
                queryset = queryset.filter(ano__gte=ano_ini)

        if ano_fim:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(ano=None)
            else:
                queryset = queryset.filter(ano__lte=ano_fim)
        if servidor:
            queryset = queryset.filter(curriculo__vinculo=servidor.get_vinculo())
        if grupo_pesquisa:
            queryset = queryset.filter(curriculo__grupos_pesquisa=grupo_pesquisa)

        if apenas_no_exercicio:
            queryset = (
                queryset.filter(curriculo__ano_inicio_exercicio__isnull=False)
                .annotate(ano_inteiro=Cast('ano', IntegerField()))
                .exclude(ano_inteiro__lt=F('curriculo__ano_inicio_exercicio'))
            )
            queryset = queryset.filter(curriculo__ano_fim_exercicio__isnull=False).annotate(ano_inteiro=Cast('ano', IntegerField())).exclude(
                ano_inteiro__gt=F('curriculo__ano_fim_exercicio')
            ) | queryset.filter(curriculo__ano_fim_exercicio__isnull=True)

        if aluno:
            queryset = queryset.filter(curriculo__vinculo=aluno.get_vinculo())

        if campus:
            queryset_alunos = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Aluno.objects.filter(curso_campus__diretoria__setor__uo=campus).values_list('id', flat=True)
            )
            queryset = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Servidor.objects.filter(setor__uo=campus).values_list('id', flat=True)
            )
            queryset = (queryset_alunos | queryset).distinct()

        if programa_posgraduacao:
            ids_cursos_campus = CursoProgramaPos.objects.filter(programa=programa_posgraduacao).values_list('curso__id', flat=True)
            queryset_alunos = queryset.filter(
                curriculo__vinculo__id_relacionamento__in=Aluno.objects.filter(curso_campus__in=ids_cursos_campus).values_list('id', flat=True)
            )
            queryset = queryset.filter(
                curriculo__vinculo__id__in=DocenteProgramaPos.objects.filter(programa=programa_posgraduacao).values_list(
                    'docente__vinculo__id', flat=True
                )
            )
            queryset = (queryset_alunos | queryset).distinct()
        return queryset.order_by('ano')

    @classmethod
    def get_anos_qtd(cls, tipo=None, categoria=None, campus=None, ano_ini=None, ano_fim=None):
        queryset = cls.filtrar(tipo, categoria, campus, ano_ini, ano_fim)
        return queryset.values_list('ano').annotate(qtd=Count('id')).order_by('ano')

    @classmethod
    def get_tipo_qtd(
        cls,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        queryset = cls.filtrar(
            None,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        return queryset.values_list('tipo').annotate(qtd=Count('id')).order_by()  # Remoção de order_by por ano do método filtrar

    @classmethod
    def get_ano_tipo_qtd(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        grupo_pesquisa=None,
        apenas_no_exercicio=None,
    ):
        queryset = cls.filtrar(
            tipo,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            natureza_evento,
            classificacao_evento,
            qualis_capes,
            servidor,
            grupo_pesquisa,
            apenas_no_exercicio,
        )
        return queryset.values('ano', 'tipo').annotate(qtd=Count('id')).order_by('ano')


##############################
#    DADOS COMPLEMENTARES    #
##############################
class DadoComplementar(models.ModelPlus):
    def get_orientacoes_em_andamento_mestrado(self):
        return self.orientacoes_andamento.filter(tipo='ORIENTACAO-EM-ANDAMENTO-DE-MESTRADO').order_by('-ano', 'sequencia')

    def get_orientacoes_em_andamento_doutorado(self):
        return self.orientacoes_andamento.filter(tipo='ORIENTACAO-EM-ANDAMENTO-DE-DOUTORADO').order_by('-ano', 'sequencia')

    def get_orientacoes_posdoutorado(self):
        return self.orientacoes_andamento.filter(tipo='ORIENTACAO-EM-ANDAMENTO-DE-POS-DOUTORADO').order_by('-ano', 'sequencia')

    def get_orientacoes_em_andamento_aperfeicoamento_especializacao(self):
        return self.orientacoes_andamento.filter(tipo='ORIENTACAO-EM-ANDAMENTO-DE-APERFEICOAMENTO-ESPECIALIZACAO').order_by('-ano', 'sequencia')

    def get_orientacoes_em_andamento_graduacao(self):
        return self.orientacoes_andamento.filter(tipo='ORIENTACAO-EM-ANDAMENTO-DE-GRADUACAO').order_by('-ano', 'sequencia')

    def get_orientacoes_em_andamento_iniciacao_cientifica(self):
        return self.orientacoes_andamento.filter(tipo='ORIENTACAO-EM-ANDAMENTO-DE-INICIACAO-CIENTIFICA').order_by('-ano', 'sequencia')

    def get_orientacoes_em_andamento_outras(self):
        return self.orientacoes_andamento.filter(tipo='OUTRAS-ORIENTACOES-EM-ANDAMENTO').order_by('-ano', 'sequencia')

    def get_participacao_como_conferencista(self):
        return self.participacoes_evento_congresso.filter(tipo_participacao='Conferencista').order_by('-ano', 'sequencia')

    def participou_evento_congresso(self):
        return self.participacoes_evento_congresso.all()

    def get_participacao_congresso(self):
        return self.participacoes_evento_congresso.filter(natureza='Congresso').order_by('-ano', 'sequencia')

    def get_participacao_encontro(self):
        return self.participacoes_evento_congresso.filter(natureza='Encontro').order_by('-ano', 'sequencia')

    def get_participacao_seminario(self):
        return self.participacoes_evento_congresso.filter(natureza='Seminário').order_by('-ano', 'sequencia')

    def get_participacao_oficina(self):
        return self.participacoes_evento_congresso.filter(natureza='Oficina').order_by('-ano', 'sequencia')

    def get_outras_participacoes(self):
        return self.participacoes_evento_congresso.filter(natureza='Outra').order_by('-ano', 'sequencia')

    @transaction.atomic
    def delete(self):
        if hasattr(self, 'orientacaoandamento'):
            orientacaoandamento = self.orientacaoandamento

            palavras_chave = orientacaoandamento.palavras_chave.all()
            for palavra in palavras_chave:
                palavra.delete()
            areas_conhecimento = orientacaoandamento.areas_conhecimento.all()
            for area in areas_conhecimento:
                area.delete()
            setores_atividade = orientacaoandamento.setores_atividade.all()
            for setor in setores_atividade:
                setor.delete()
            if orientacaoandamento.informacao_adicional:
                orientacaoandamento.informacao_adicional.delete()

        super().delete()


class OrientacaoAndamento(models.ModelPlus):
    tipo_choices = {
        'ORIENTACAO-EM-ANDAMENTO-DE-MESTRADO': 'Orientações de Mestrado',
        'ORIENTACAO-EM-ANDAMENTO-DE-DOUTORADO': 'Orientações de Doutorado',
        'ORIENTACAO-EM-ANDAMENTO-DE-POS-DOUTORADO': 'Orientações de Pós-Doutorado',
        'ORIENTACAO-EM-ANDAMENTO-DE-APERFEICOAMENTO-ESPECIALIZACAO': 'Orientações de Aperfeiçoamento/Especialização',
        'ORIENTACAO-EM-ANDAMENTO-DE-GRADUACAO': 'Orientações de Graduação',
        'ORIENTACAO-EM-ANDAMENTO-DE-INICIACAO-CIENTIFICA': 'Orientações de Iniciação Científica',
        'OUTRAS-ORIENTACOES-EM-ANDAMENTO': 'Outras Orientações',
    }

    dado_complementar = models.ForeignKeyPlus('cnpq.DadoComplementar', related_name='orientacoes_andamento', on_delete=models.CASCADE)
    tipo = models.TextField()
    sequencia = models.TextField()
    natureza = models.TextField()
    titulo = models.TextField()
    ano = models.TextField()
    pais = models.TextField()
    idioma = models.TextField()
    home_page = models.TextField()
    doi = models.TextField()
    tipo_orientacao = models.TextField()
    nome_orientando = models.TextField()
    nome_instituicao = models.TextField()
    nome_orgao = models.TextField()
    nome_curso = models.TextField()
    flag_bolsa = models.BooleanField(null=True)
    nome_agencia_financiadora = models.TextField()

    palavras_chave = models.ManyToManyField('cnpq.PalavraChave')
    areas_conhecimento = models.ManyToManyField('cnpq.AreaConhecimento')
    setores_atividade = models.ManyToManyField('cnpq.SetorAtividade')
    informacao_adicional = models.OneToOneField('cnpq.InformacaoAdicinal', null=True, on_delete=models.CASCADE)

    @transaction.atomic
    def delete(self):
        palavras_chave = self.palavras_chave.all()
        for palavra in palavras_chave:
            palavra.delete()

        areas_conhecimento = self.areas_conhecimento.all()
        for area in areas_conhecimento:
            area.delete()

        setores_atividade = self.setores_atividade.all()
        for setor in setores_atividade:
            setor.delete()

        if self.informacao_adicional:
            self.informacao_adicional.delete()

        self.dadocomplementar_ptr.delete()

    def __str__(self):
        return f'{self.nome_orientando}. {self.titulo}. Início: {self.ano}. {self.natureza} (em {self.nome_curso}) - {self.nome_instituicao}.'

    def get_ano(self):
        return self.ano

    def get_tipo(self):
        return self.tipo_choices[self.tipo] or 'Não informado'

    def get_autores_unicos(self):
        ids = OrientacaoAndamento.objects.filter(id=self.id, dado_complementar__curriculovittaelattes__vinculo__isnull=False).values_list(
            'dado_complementar__curriculovittaelattes__vinculo', flat=True
        )
        return VinculoPessoa.objects.filter(id__in=ids)

    @classmethod
    def filtrar(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        from edu.models import Aluno
        from pesquisa.models import CursoProgramaPos, DocenteProgramaPos

        queryset = cls.objects.all()
        if tipo:
            queryset = queryset.filter(tipo_pub=tipo)

        if categoria:
            if categoria == 'aluno':
                queryset = queryset.filter(dado_complementar__curriculovittaelattes__vinculo__tipo_relacionamento__model=categoria)
            else:
                queryset = queryset.filter(
                    dado_complementar__curriculovittaelattes__vinculo__id_relacionamento__in=Servidor.objects.filter(
                        cargo_emprego__grupo_cargo_emprego__categoria=categoria
                    ).values_list('id', flat=True)
                )

        if ano_ini:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(ano=None)
            else:
                queryset = queryset.filter(ano__gte=ano_ini)

        if ano_fim:
            if ano_ini == 'Não informado':
                queryset = queryset.filter(ano=None)
            else:
                queryset = queryset.filter(ano__lte=ano_fim)
        if servidor:
            queryset = queryset.filter(dado_complementar__curriculovittaelattes__vinculo=servidor.get_vinculo())
        if grupo_pesquisa:
            queryset = queryset.filter(dado_complementar__curriculovittaelattes__grupos_pesquisa=grupo_pesquisa)

        if apenas_no_exercicio:
            queryset = (
                queryset.filter(dado_complementar__curriculovittaelattes__ano_inicio_exercicio__isnull=False)
                .annotate(ano_inteiro=Cast('ano', IntegerField()))
                .exclude(ano_inteiro__lt=F('dado_complementar__curriculovittaelattes__ano_inicio_exercicio'))
            )
            queryset = queryset.filter(dado_complementar__curriculovittaelattes__ano_fim_exercicio__isnull=False).annotate(
                ano_inteiro=Cast('ano', IntegerField())
            ).exclude(ano_inteiro__gt=F('dado_complementar__curriculovittaelattes__ano_fim_exercicio')) | queryset.filter(
                dado_complementar__curriculovittaelattes__ano_fim_exercicio__isnull=True
            )

        if aluno:
            queryset = queryset.filter(dado_complementar__curriculovittaelattes__vinculo=aluno.get_vinculo())

        if campus:
            queryset_alunos = queryset.filter(
                dado_complementar__curriculovittaelattes__vinculo__id__in=Aluno.objects.filter(curso_campus__diretoria__setor__uo=campus).values_list(
                    'pessoa_fisica__vinculo__id', flat=True
                )
            )
            queryset = queryset.filter(
                dado_complementar__curriculovittaelattes__vinculo__id__in=Servidor.objects.filter(setor__uo=campus).values_list('id', flat=True)
            )
            queryset = (queryset_alunos | queryset).distinct()

        if programa_posgraduacao:
            ids_cursos_campus = CursoProgramaPos.objects.filter(programa=programa_posgraduacao).values_list('curso__id', flat=True)
            queryset_alunos = queryset.filter(
                dado_complementar__curriculovittaelattes__vinculo__id__in=Aluno.objects.filter(curso_campus__in=ids_cursos_campus).values_list(
                    'pessoa_fisica__vinculo__id', flat=True
                )
            )
            queryset = queryset.filter(
                dado_complementar__curriculovittaelattes__vinculo__id__in=DocenteProgramaPos.objects.filter(
                    programa=programa_posgraduacao
                ).values_list('docente__vinculo__id', flat=True)
            )
            queryset = (queryset_alunos | queryset).distinct()

        return queryset.order_by('ano')

    @classmethod
    def get_anos_qtd(cls, tipo=None, categoria=None, campus=None, ano_ini=None, ano_fim=None):
        queryset = cls.filtrar(tipo, categoria, campus, ano_ini, ano_fim)
        return queryset.values_list('ano').annotate(qtd=Count('id')).order_by('ano')

    @classmethod
    def get_tipo_qtd(
        cls,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        servidor=None,
        aluno=None,
        grupo_pesquisa=None,
        programa_posgraduacao=None,
        apenas_no_exercicio=None,
    ):
        queryset = cls.filtrar(
            None,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            servidor=servidor,
            aluno=aluno,
            grupo_pesquisa=grupo_pesquisa,
            programa_posgraduacao=programa_posgraduacao,
            apenas_no_exercicio=apenas_no_exercicio,
        )
        return queryset.values_list('tipo').annotate(qtd=Count('id')).order_by()  # Remoção de order_by por ano do método filtrar

    @classmethod
    def get_ano_tipo_qtd(
        cls,
        tipo=None,
        categoria=None,
        campus=None,
        ano_ini=None,
        ano_fim=None,
        natureza_evento=None,
        classificacao_evento=None,
        qualis_capes=None,
        servidor=None,
        grupo_pesquisa=None,
        apenas_no_exercicio=None,
    ):
        queryset = cls.filtrar(
            tipo,
            categoria,
            campus,
            ano_ini,
            ano_fim,
            natureza_evento,
            classificacao_evento,
            qualis_capes,
            servidor,
            grupo_pesquisa,
            apenas_no_exercicio,
        )
        return queryset.values('ano', 'tipo').annotate(qtd=Count('id')).order_by('ano')


class ParticipanteBanca(models.ModelPlus):
    nome_completo = models.TextField()
    nome_citacao = models.TextField()
    ordem = models.TextField()
    cpf = models.TextField()

    def __str__(self):
        return self.nome_completo


class ParticipacaoBancaTrabalhoConclusao(models.ModelPlus):
    tipo_choices = {
        'PARTICIPACAO-EM-BANCA-DE-MESTRADO': 'Participação em Banca de Mestrado',
        'PARTICIPACAO-EM-BANCA-DE-DOUTORADO': 'Participação em Banca de Doutorado',
        'PARTICIPACAO-EM-BANCA-DE-EXAME-QUALIFICACAO': 'Participação em Banca de Exame de Qualificação',
        'PARTICIPACAO-EM-BANCA-DE-APERFEICOAMENTO-ESPECIALIZACAO': 'Participação em Banca de Aperfeiçoamento/Especialização',
        'PARTICIPACAO-EM-BANCA-DE-GRADUACAO': 'Participação em Banca de Graduação',
        'OUTRAS-PARTICIPACOES-EM-BANCA': 'Outras Participações em Banca',
    }

    dado_complementar = models.ForeignKeyPlus(
        'cnpq.DadoComplementar', related_name='participacoes_banca_trabalho_conclusao', on_delete=models.CASCADE
    )
    tipo = models.TextField()
    sequencia = models.TextField()
    natureza = models.TextField()
    tipo_mestrado = models.TextField()
    titulo = models.TextField()
    ano = models.TextField()
    pais = models.TextField()
    idioma = models.TextField()
    home_page = models.TextField()
    doi = models.TextField()
    titulo_ingles = models.TextField()
    nome_candidato = models.TextField()
    nome_instituicao = models.TextField()
    nome_orgao = models.TextField()
    nome_curso = models.TextField()
    nome_curso_ingles = models.TextField()

    participantes = models.ManyToManyField('cnpq.ParticipanteBanca')
    palavras_chave = models.ManyToManyField('cnpq.PalavraChave')
    areas_conhecimento = models.ManyToManyField('cnpq.AreaConhecimento')
    setores_atividade = models.ManyToManyField('cnpq.SetorAtividade')
    informacao_adicional = models.OneToOneField('cnpq.InformacaoAdicinal', null=True, on_delete=models.CASCADE)

    @transaction.atomic
    def delete(self):
        participantes = self.participantes.all()
        for participante in participantes:
            participante.delete()

        palavras_chave = self.palavras_chave.all()
        for palavra in palavras_chave:
            palavra.delete()

        areas_conhecimento = self.areas_conhecimento.all()
        for area in areas_conhecimento:
            area.delete()

        setores_atividade = self.setores_atividade.all()
        for setor in setores_atividade:
            setor.delete()

        if self.informacao_adicional:
            self.informacao_adicional.delete()

        self.dadocomplementar_ptr.delete()

    def get_participantes(self):
        return self.participantes.order_by('ordem')

    def __str__(self):
        retorno = ''
        for participante in self.get_participantes():
            retorno += participante.nome_citacao + '; '

        retorno += f'. Participação em banca de {self.nome_candidato}. '
        retorno += f'{self.titulo}. {self.ano}.'
        return retorno


class ParticipacaoBancaJulgadora(models.ModelPlus):
    tipo_choices = {
        'BANCA-JULGADORA-PARA-PROFESSOR-TITULAR': 'Participação em Banca julgada para professor títular',
        'BANCA-JULGADORA-PARA-CONCURSO-PUBLICO': 'Participação em Banca julgada para concurso público',
        'BANCA-JULGADORA-PARA-LIVRE-DOCENCIA': 'Participação em Banca julgada para livre docência',
        'BANCA-JULGADORA-PARA-AVALIACAO-CURSOS': 'Participação em Banca julgada para avaliação de cursos',
        'OUTRAS-BANCAS-JULGADORAS': 'Outras Participações em Bancas julgadoras',
    }

    dado_complementar = models.ForeignKeyPlus('cnpq.DadoComplementar', related_name='participacoes_banca_julgadora', on_delete=models.CASCADE)
    tipo = models.TextField()
    sequencia = models.TextField()

    natureza = models.TextField()
    titulo = models.TextField()
    ano = models.TextField()
    pais = models.TextField()
    idioma = models.TextField()
    home_page = models.TextField()
    doi = models.TextField()
    titulo_ingles = models.TextField()

    codigo_instituicao = models.TextField()
    nome_instituicao = models.TextField()

    participantes = models.ManyToManyField('cnpq.ParticipanteBanca')
    palavras_chave = models.ManyToManyField('cnpq.PalavraChave')
    areas_conhecimento = models.ManyToManyField('cnpq.AreaConhecimento')
    setores_atividade = models.ManyToManyField('cnpq.SetorAtividade')
    informacao_adicional = models.OneToOneField('cnpq.InformacaoAdicinal', null=True, on_delete=models.CASCADE)

    @transaction.atomic
    def delete(self):
        participantes = self.participantes.all()
        for participante in participantes:
            participante.delete()

        palavras_chave = self.palavras_chave.all()
        for palavra in palavras_chave:
            palavra.delete()

        areas_conhecimento = self.areas_conhecimento.all()
        for area in areas_conhecimento:
            area.delete()

        setores_atividade = self.setores_atividade.all()
        for setor in setores_atividade:
            setor.delete()

        if self.informacao_adicional:
            self.informacao_adicional.delete()

        self.dadocomplementar_ptr.delete()

    def get_participantes(self):
        return self.participantes.order_by('ordem')

    def __str__(self):
        retorno = ''
        for participante in self.get_participantes():
            retorno += participante.nome_citacao + '; '

        retorno += f'{self.titulo}. {self.ano}. {self.nome_instituicao}'
        return retorno


class ParticipanteEventoCongresso(models.ModelPlus):
    nome_completo = models.TextField()
    nome_citacao = models.TextField()
    ordem = models.TextField()

    def __str__(self):
        return self.nome_completo


class ParticipacaoEventoCongresso(models.ModelPlus):
    dado_complementar = models.ForeignKeyPlus('cnpq.DadoComplementar', related_name='participacoes_evento_congresso', on_delete=models.CASCADE)
    tipo = models.TextField()
    sequencia = models.TextField()

    natureza = models.TextField()
    titulo = models.TextField()
    ano = models.TextField()
    pais = models.TextField()
    idioma = models.TextField()
    meio_divulgacao = models.TextField()
    home_page = models.TextField()
    flag_relevancia = models.TextField()
    tipo_participacao = models.TextField()
    forma_participacao = models.TextField()
    doi = models.TextField()
    titulo_ingles = models.TextField()
    flag_divulgacao_cientifica = models.TextField()

    nome_evento = models.TextField()
    local_evento = models.TextField()
    cidade_evento = models.TextField()
    nome_evento_ingles = models.TextField(null=True)
    codigo_instituicao = models.TextField()
    nome_instituicao = models.TextField()

    participantes = models.ManyToManyField('cnpq.ParticipanteEventoCongresso')

    @transaction.atomic
    def delete(self):
        participantes = self.participantes.all()
        for participante in participantes:
            participante.delete()

        self.dadocomplementar_ptr.delete()

    def get_participantes(self):
        return self.participantes.order_by('ordem')

    def __str__(self):
        retorno = ''
        for participante in self.get_participantes():
            retorno += participante.nome_citacao + '; '

        retorno += f'{self.titulo}. {self.ano}. {self.nome_instituicao}'
        return retorno

    def get_titulo_evento(self):
        if self.titulo and self.nome_evento:
            return f'{self.titulo}/{self.nome_evento}'
        elif not self.nome_evento:
            return self.titulo
        elif not self.titulo:
            return self.nome_evento
        return '-'


class Parametro(models.ModelPlus):
    codigo = models.CharField('Código', max_length=10)
    descricao = models.CharField('Descrição', max_length=150)
    grupo = models.CharField('Grupo', max_length=150)

    class Meta:
        verbose_name = 'Critério'
        verbose_name_plural = 'Critérios'

    def __str__(self):
        return f'{self.descricao}'

    @classmethod
    def get_numero_producao_academica(self, servidor, ano_inicial, maior_ano=None, parametro=None):
        nome_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
        sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        criterios_avaliacao = {}
        if not parametro:
            for par in Parametro.objects.all():
                criterios_avaliacao[par.codigo] = [0, f'{par.codigo} - {par.descricao}']
        else:
            criterios_avaliacao[parametro.codigo] = [0, f'{parametro.codigo} - {parametro.descricao}']
        curriculo = None
        if hasattr(servidor.get_vinculo(), 'vinculo_curriculo_lattes'):
            curriculo = servidor.get_vinculo().vinculo_curriculo_lattes
        else:
            return criterios_avaliacao
        ano_final = maior_ano or date.today().year
        # Títulos decorrentes da atividade didática #
        if '1.01' in criterios_avaliacao:  # 1.1 - Orientação de IC no IFRN
            criterios_avaliacao['1.01'][0] = (
                curriculo.get_orientacoes_iniciacao_cientifica()
                .filter(ano__range=[ano_inicial, ano_final])
                .filter(Q(nome_instituicao__iexact=nome_instituicao) | Q(nome_instituicao__iexact=sigla_instituicao))
                .count()
            )
            criterios_avaliacao['1.01'][0] += (
                curriculo.dado_complementar.get_orientacoes_em_andamento_iniciacao_cientifica()
                .filter(ano__range=[ano_inicial, ano_final])
                .filter(Q(nome_instituicao__iexact=nome_instituicao) | Q(nome_instituicao__iexact=sigla_instituicao))
                .count()
            )
        if '1.02' in criterios_avaliacao:  # 1.2 Orientação de Monografia Graduação ou Especialização
            criterios_avaliacao['1.02'][0] = curriculo.get_orientacoes_graduacao().filter(ano__range=[ano_inicial, ano_final]).count()
            criterios_avaliacao['1.02'][0] += (
                curriculo.get_orientacoes_aperfeicoamento_especializacao().filter(ano__range=[ano_inicial, ano_final]).count()
            )
            criterios_avaliacao['1.02'][0] += (
                curriculo.dado_complementar.get_orientacoes_em_andamento_aperfeicoamento_especializacao()
                .filter(ano__range=[ano_inicial, ano_final])
                .count()
            )
            criterios_avaliacao['1.02'][0] += (
                curriculo.dado_complementar.get_orientacoes_em_andamento_graduacao().filter(ano__range=[ano_inicial, ano_final]).count()
            )
        if '1.03' in criterios_avaliacao:  # Orientação concluída de outra natureza, como: TCC de curso técnico e prática profissional
            criterios_avaliacao['1.03'][0] = curriculo.get_outras_orientacoes().filter(ano__range=[ano_inicial, ano_final]).count()
        if '1.04' in criterios_avaliacao:  # 1.3 Orientação de Dissertações de Mestrado
            criterios_avaliacao['1.04'][0] = curriculo.get_orientacoes_mestrado().filter(ano__range=[ano_inicial, ano_final]).count()
            criterios_avaliacao['1.04'][0] += (
                curriculo.dado_complementar.get_orientacoes_em_andamento_mestrado().filter(ano__range=[ano_inicial, ano_final]).count()
            )
        if '1.05' in criterios_avaliacao:  # 1.4 Orientações de Teses de Doutorado
            criterios_avaliacao['1.05'][0] = curriculo.get_orientacoes_doutorado().filter(ano__range=[ano_inicial, ano_final]).count()
            criterios_avaliacao['1.05'][0] += (
                curriculo.dado_complementar.get_orientacoes_em_andamento_doutorado().filter(ano__range=[ano_inicial, ano_final]).count()
            )
        if '1.06' in criterios_avaliacao:  # 1.5 Projetos de Pesquisa Concluídos no IFRN
            criterios_avaliacao['1.06'][0] = (
                curriculo.get_projeto_pesquisa_como_coordenador(nome_instituicao=nome_instituicao)
                .filter(situacao='CONCLUIDO')
                .filter(ano_fim__range=[ano_inicial, ano_final])
                .count()
            )
            # criterios_avaliacao['1.6] += curriculo.get_projeto_extensao().filter(ano_inicio__gte=ano_inicial).count()
            criterios_avaliacao['1.06'][0] += (
                curriculo.get_projeto_desenvolvimento_como_coordenador(nome_instituicao=nome_instituicao)
                .filter(situacao='CONCLUIDO')
                .filter(ano_fim__range=[ano_inicial, ano_final])
                .count()
            )
        if '1.07' in criterios_avaliacao:  # 1.7 - Participação em Banca de Graduação ou Especialização
            criterios_avaliacao['1.07'][0] = curriculo.get_participacao_em_banca_graduacao().filter(ano__range=[ano_inicial, ano_final]).count()
            criterios_avaliacao['1.07'][0] += curriculo.get_participacao_em_banca_especializacao().filter(ano__range=[ano_inicial, ano_final]).count()
        if '1.08' in criterios_avaliacao:  # 1.8 - Participação em Banca de Mestrado
            criterios_avaliacao['1.08'][0] = curriculo.get_participacao_em_banca_mestrado().filter(ano__range=[ano_inicial, ano_final]).count()
        if '1.09' in criterios_avaliacao:  # 1.9 - Participação em Banca de Doutorado
            criterios_avaliacao['1.09'][0] = curriculo.get_participacao_em_banca_doutorado().filter(ano__range=[ano_inicial, ano_final]).count()
        if '1.10' in criterios_avaliacao:  # 1.10. - Participação em bancas de comissões julgadoras
            criterios_avaliacao['1.10'][0] = (
                curriculo.get_participacao_em_banca_comissoes_julgadoras().filter(ano__range=[ano_inicial, ano_final]).count()
            )
        if '1.11' in criterios_avaliacao:  # 1.11. - Projetos de Pesquisa Concluídos na Instituição como membro
            criterios_avaliacao['1.11'][0] = (
                curriculo.get_projeto_pesquisa_como_membro(nome_instituicao=nome_instituicao)
                .filter(situacao='CONCLUIDO')
                .filter(ano_fim__range=[ano_inicial, ano_final])
                .count()
            )
            # criterios_avaliacao['1.6] += curriculo.get_projeto_extensao().filter(ano_inicio__gte=ano_inicial).count()
            criterios_avaliacao['1.11'][0] += (
                curriculo.get_projeto_desenvolvimento_como_membro(nome_instituicao=nome_instituicao)
                .filter(situacao='CONCLUIDO')
                .filter(ano_fim__range=[ano_inicial, ano_final])
                .count()
            )
        from django.conf import settings

        if '1.12' in criterios_avaliacao:  # 1.12. - Orientação de TCCs de curso técnico
            criterios_avaliacao['1.12'][0] = 0
            if 'edu' in settings.INSTALLED_APPS:
                from edu.models import Modalidade, ProjetoFinal

                criterios_avaliacao['1.12'][0] = (
                    ProjetoFinal.objects.filter(
                        orientador__vinculo=servidor.get_vinculo(),
                        matricula_periodo__aluno__curso_campus__modalidade__in=(
                            Modalidade.INTEGRADO,
                            Modalidade.INTEGRADO_EJA,
                            Modalidade.FIC_INTEGRADO_EJA,
                            Modalidade.SUBSEQUENTE,
                        ),
                    )
                    .filter(matricula_periodo__ano_letivo__ano__range=[ano_inicial, ano_final])
                    .count()
                )

        if '1.13' in criterios_avaliacao:  # 1.13. - Orientação de prática profissional
            criterios_avaliacao['1.13'][0] = 0
            if 'estagios' in settings.INSTALLED_APPS:
                from estagios.models import PraticaProfissional

                criterios_avaliacao['1.13'][0] = (
                    PraticaProfissional.objects.filter(orientador__vinculo=servidor.get_vinculo())
                    .filter(data_inicio__year__range=[ano_inicial, ano_final])
                    .count()
                )

        if '1.14' in criterios_avaliacao:  # 1.14. - Avaliações de Projetos de Pesquisa no SUAP
            criterios_avaliacao['1.14'][0] = 0
            if 'pesquisa' in settings.INSTALLED_APPS:
                from pesquisa.models import Avaliacao, ItemAvaliacao

                avaliacoes_realizadas = Avaliacao.objects.filter(vinculo=servidor.get_vinculo(), data__year__range=[ano_inicial, ano_final]).count()
                recursos_avaliados = ItemAvaliacao.objects.filter(
                    recurso_avaliado_por=servidor.get_vinculo(), recurso_avaliado_em__year__range=[ano_inicial, ano_final]
                ).count()
                total_avaliacoes = avaliacoes_realizadas + recursos_avaliados
                criterios_avaliacao['1.14'][0] = total_avaliacoes
        if '1.15' in criterios_avaliacao:  # 1.15 - Orientação de IC em outra instituição
            criterios_avaliacao['1.15'][0] = (
                curriculo.get_orientacoes_iniciacao_cientifica()
                .filter(ano__range=[ano_inicial, ano_final])
                .exclude(Q(nome_instituicao__iexact=nome_instituicao) | Q(nome_instituicao__iexact=sigla_instituicao))
                .count()
            )
            criterios_avaliacao['1.15'][0] += (
                curriculo.dado_complementar.get_orientacoes_em_andamento_iniciacao_cientifica()
                .filter(ano__range=[ano_inicial, ano_final])
                .exclude(Q(nome_instituicao__iexact=nome_instituicao) | Q(nome_instituicao__iexact=sigla_instituicao))
                .count()
            )
        if '1.16' in criterios_avaliacao:  # 1.16 Projetos de Pesquisa Concluídos em outra instituição
            criterios_avaliacao['1.16'][0] = (
                curriculo.get_projeto_pesquisa_como_coordenador()
                .filter(situacao='CONCLUIDO')
                .filter(ano_fim__range=[ano_inicial, ano_final])
                .exclude(participacao_projeto__atuacao_profissional__nome_instituicao=nome_instituicao)
                .count()
            )
            criterios_avaliacao['1.16'][0] += (
                curriculo.get_projeto_desenvolvimento_como_coordenador()
                .filter(situacao='CONCLUIDO')
                .filter(ano_fim__range=[ano_inicial, ano_final])
                .exclude(participacao_projeto__atuacao_profissional__nome_instituicao=nome_instituicao)
                .count()
            )
        if '1.17' in criterios_avaliacao:  # 1.17. - Projetos de Pesquisa Concluídos em outra Instituição como membro
            criterios_avaliacao['1.17'][0] = (
                curriculo.get_projeto_pesquisa_como_membro()
                .filter(situacao='CONCLUIDO')
                .filter(ano_fim__range=[ano_inicial, ano_final])
                .exclude(participacao_projeto__atuacao_profissional__nome_instituicao=nome_instituicao)
                .count()
            )
            criterios_avaliacao['1.17'][0] += (
                curriculo.get_projeto_desenvolvimento_como_membro()
                .filter(situacao='CONCLUIDO')
                .filter(ano_fim__range=[ano_inicial, ano_final])
                .exclude(participacao_projeto__atuacao_profissional__nome_instituicao=nome_instituicao)
                .count()
            )

        # Títulos decorrentes de atividades científicas e tecnológicas #
        if '2.01' in criterios_avaliacao:  # 2.1 - Publicação de livro com ISBN
            criterios_avaliacao['2.01'][0] = curriculo.get_livros().filter(ano__range=[ano_inicial, ano_final]).count()
        if '2.02' in criterios_avaliacao:  # 2.2 - Publicação de capítulo de livro com ISBN
            criterios_avaliacao['2.02'][0] = curriculo.get_capitulos().filter(ano__range=[ano_inicial, ano_final]).count()
        if '2.03' in criterios_avaliacao:  # 2.3 - Publicação em revistas e periódicos (Qualis A1 e A2)
            criterios_avaliacao['2.03'][0] = (
                curriculo.get_artigos()
                .annotate(estrato=Min('periodico__estratos_qualis__estrato'))
                .filter(ano__range=[ano_inicial, ano_final], estrato__in=['A1', 'A2'])
                .count()
            )
        if '2.04' in criterios_avaliacao:  # 2.4 - Publicação em revistas e periódicos (Qualis A3 e A4)
            criterios_avaliacao['2.04'][0] = (
                curriculo.get_artigos()
                .annotate(estrato=Min('periodico__estratos_qualis__estrato'))
                .filter(ano__range=[ano_inicial, ano_final], estrato__in=['A3', 'A4'])
                .count()
            )
        if '2.05' in criterios_avaliacao:  # 2.5 - Publicação em revistas e periódicos (Qualis B1 e B2)
            criterios_avaliacao['2.05'][0] = (
                curriculo.get_artigos()
                .annotate(estrato=Min('periodico__estratos_qualis__estrato'))
                .filter(ano__range=[ano_inicial, ano_final], estrato__in=['B1', 'B2'])
                .count()
            )
        if '2.06' in criterios_avaliacao:  # 2.6 - Publicação em revistas e periódicos (Qualis entre B3 e B4)
            criterios_avaliacao['2.06'][0] = (
                curriculo.get_artigos()
                .annotate(estrato=Min('periodico__estratos_qualis__estrato'))
                .filter(ano__range=[ano_inicial, ano_final], estrato__in=['B3', 'B4'])
                .count()
            )
        if '2.07' in criterios_avaliacao:  # 2.7 - Publicação em revistas e periódicos (Qualis C)
            criterios_avaliacao['2.07'][0] = (
                curriculo.get_artigos()
                .annotate(estrato=Min('periodico__estratos_qualis__estrato'))
                .filter(ano__range=[ano_inicial, ano_final], estrato__in='C')
                .count()
            )
        if '2.08' in criterios_avaliacao:  # 2.8 - Participação como conferencista
            criterios_avaliacao['2.08'][0] = (
                curriculo.dado_complementar.get_participacao_como_conferencista().filter(ano__range=[ano_inicial, ano_final]).count()
            )
        if '2.09' in criterios_avaliacao:  # 2.9 - Trabalho completo publicado em anais internacionais
            criterios_avaliacao['2.09'][0] = (
                curriculo.get_trabalhos_eventos_completos().filter(ano__range=[ano_inicial, ano_final], classificacao_evento='INTERNACIONAL').count()
            )
        if '2.10' in criterios_avaliacao:  # 2.10 - Trabalho completo publicado em anais nacionais, todos, exceto os internacionais
            criterios_avaliacao['2.10'][0] = (
                curriculo.get_trabalhos_eventos_completos().filter(ano__range=[ano_inicial, ano_final], classificacao_evento='NACIONAL').count()
            )
        if '2.11' in criterios_avaliacao:  # 2.11 - **Trabalhos publicado em anais de eventos de Regionais ou Locais ou Não Informados**
            criterios_avaliacao['2.11'][0] = (
                curriculo.get_trabalhos_eventos_completos()
                .filter(ano__range=[ano_inicial, ano_final], classificacao_evento__in=['REGIONAL', 'LOCAL', 'NAO_INFORMADO'])
                .count()
            )
        if '2.12' in criterios_avaliacao:  # 2.12 - Produção de trabalhos técnicos:
            criterios_avaliacao['2.12'][0] = curriculo.get_todas_producoes_tecnicas().filter(ano__range=[ano_inicial, ano_final]).count()
        if '2.13' in criterios_avaliacao:  # 2.13 - Registro de Propriedade Industrial no INPI
            criterios_avaliacao['2.13'][0] = curriculo.get_patentes_e_registros().filter(ano__range=[ano_inicial, ano_final]).count()
        if '2.14' in criterios_avaliacao:  # 2.14 - Membro de corpo editorial de periódicos
            criterios_avaliacao['2.14'][0] = (
                curriculo.get_membro_corpo_editorial_de_periodicos()
                .filter(
                    Q(ano_inicio__gte=ano_inicial)
                    | (Q(ano_inicio__lte=ano_inicial) & (Q(ano_fim__isnull=True) | Q(ano_fim__exact='')))
                    | Q(ano_fim__range=[ano_inicial, ano_final])
                )
                .count()
            )

        if '2.15' in criterios_avaliacao:  # 2.15 - Revisor de periódicos
            criterios_avaliacao['2.15'][0] = (
                curriculo.get_revisor_periodicos()
                .filter(
                    Q(ano_inicio__gte=ano_inicial)
                    | (Q(ano_inicio__lte=ano_inicial) & (Q(ano_fim__isnull=True) | Q(ano_fim__exact='')))
                    | Q(ano_fim__range=[ano_inicial, ano_final])
                )
                .count()
            )
        if '2.16' in criterios_avaliacao:  # 2.16 - Premiações
            criterios_avaliacao['2.16'][0] = curriculo.get_premios_e_titulos().filter(ano_premiacao__range=[ano_inicial, ano_final]).count()

        if '2.17' in criterios_avaliacao:  # 2.17 - Registro de Patente no INPI
            criterios_avaliacao['2.17'][0] = curriculo.get_patentes().filter(ano__range=[ano_inicial, ano_final]).count()

        if '2.18' in criterios_avaliacao:  # 2.18 - Registro de Software no INPI
            criterios_avaliacao['2.18'][0] = curriculo.get_softwares_patentes().filter(ano__range=[ano_inicial, ano_final]).count()

        if '2.19' in criterios_avaliacao:  # 2.19 - Demais registros de Propriedade Industrial no INPI
            criterios_avaliacao['2.19'][0] = curriculo.get_outros_registros().filter(ano__range=[ano_inicial, ano_final]).count()

        if '2.20' in criterios_avaliacao:  # 2.20 - Publicação em revistas e periódicos sem Qualis
            criterios_avaliacao['2.20'][0] = (
                curriculo.get_artigos()
                .annotate(estrato=Min('periodico__estratos_qualis__estrato'))
                .filter(ano__range=[ano_inicial, ano_final], estrato=None)
                .count()
            )
        if '2.21' in criterios_avaliacao:  # 2.21 - Resumo publicado em anais internacionais
            criterios_avaliacao['2.21'][0] = (
                curriculo.get_trabalhos_eventos_resumos().filter(ano__range=[ano_inicial, ano_final], classificacao_evento='INTERNACIONAL').count()
            )
            criterios_avaliacao['2.21'][0] += (
                curriculo.get_trabalhos_eventos_resumos_expandidos()
                .filter(ano__range=[ano_inicial, ano_final], classificacao_evento='INTERNACIONAL')
                .count()
            )
        if '2.22' in criterios_avaliacao:  # 2.22 - Resumo publicado em anais nacionais, todos, exceto os internacionais
            criterios_avaliacao['2.22'][0] = (
                curriculo.get_trabalhos_eventos_resumos().filter(ano__range=[ano_inicial, ano_final], classificacao_evento='NACIONAL').count()
            )
            criterios_avaliacao['2.22'][0] += (
                curriculo.get_trabalhos_eventos_resumos_expandidos()
                .filter(ano__range=[ano_inicial, ano_final], classificacao_evento='NACIONAL')
                .count()
            )
        if '2.23' in criterios_avaliacao:  # 2.23 - Resumo publicado em anais de eventos de Regionais ou Locais ou Não Informados
            criterios_avaliacao['2.23'][0] = (
                curriculo.get_trabalhos_eventos_resumos()
                .filter(ano__range=[ano_inicial, ano_final], classificacao_evento__in=['REGIONAL', 'LOCAL', 'NAO_INFORMADO'])
                .count()
            )
            criterios_avaliacao['2.23'][0] += (
                curriculo.get_trabalhos_eventos_resumos_expandidos()
                .filter(ano__range=[ano_inicial, ano_final], classificacao_evento__in=['REGIONAL', 'LOCAL', 'NAO_INFORMADO'])
                .count()
            )
        # Títulos decorrentes de atividades acadêmicas #
        if '3.01' in criterios_avaliacao and curriculo.get_formacoes_doutor().filter(ano_conclusao__isnull=False).exists():  # 3.1 Doutor
            criterios_avaliacao['3.01'][0] = curriculo.get_formacoes_doutor().filter(ano_conclusao__isnull=False).count()
        elif '3.02' in criterios_avaliacao and curriculo.get_formacoes_mestrado().filter(ano_conclusao__isnull=False).exists():  # 3.2 Mestre
            criterios_avaliacao['3.02'][0] = curriculo.get_formacoes_mestrado().filter(ano_conclusao__isnull=False).count()
        elif '3.03' in criterios_avaliacao:  # 3.3 Especialista ou em processo de capacitação para mestre
            criterios_avaliacao['3.03'][0] = curriculo.get_formacoes_especializacao().filter(ano_conclusao__isnull=False).count()

        return criterios_avaliacao

    def get_form_field(self, initial):
        return forms.DecimalField(label=f'{self.codigo} - {self.descricao}', initial=initial or 0)
