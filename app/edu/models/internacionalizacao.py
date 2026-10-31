from __future__ import annotations

import tempfile
from datetime import datetime, date
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.files.base import ContentFile
from djtools.db import models
from edu.models import (
    Aluno,
    Pais,
    Cidade,
    SituacaoMatricula,
    SequencialMatricula,
    AlunoArquivo,
    TipoAlunoArquivo,
    SituacaoMatriculaPeriodo,
    MatriculaPeriodo,
)
from rh.models import PessoaFisica, ArquivoUnico
from rh.enums import Nacionalidade
from comum.models import PrestadorServico, JustificativaUsuarioExterno, Configuracao, Vinculo
from rh.deduplicacao.documentos import formatar_passaporte
from rh.deduplicacao.entrada import Politica, aplicar_politica, filtro_par_passaporte
from rh.deduplicacao.paises import pais_por_nome
from djtools.utils import send_mail
from django.conf import settings
from djtools.storages import get_overwrite_storage
from djtools.thumbs import ImageWithThumbsField

if TYPE_CHECKING:
    import pandas as pd

    from comum.models import Pais as ComumPais
    from convenios.models import Convenio
    from edu.models import FormaIngresso, Polo, Turno


class TipoInstituicaoEstrangeira(models.ModelPlus):
    nome = models.CharField(verbose_name='Nome')

    class Meta:
        verbose_name = 'Tipo de Instituição Estrangeira'
        verbose_name_plural = 'Tipos de Instituição Estrangeira'

    def __str__(self):
        return self.nome


class PreMatriculaInternacional(models.ModelPlus):
    descricao = models.CharField(verbose_name='Descrição')
    ano_letivo = models.ForeignKeyPlus('comum.ano', verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.IntegerField(verbose_name='Período Letivo', choices=[[1, 1], [2, 2]])
    diretoria = models.ForeignKeyPlus('edu.diretoria', verbose_name='Diretoria', on_delete=models.CASCADE)
    matriz_curso = models.ForeignKeyPlus('edu.matrizcurso', verbose_name='Matriz/Curso', on_delete=models.CASCADE)
    qtd_vagas = models.IntegerField(verbose_name='Quantidade de Vagas')
    data_inicio_inscricoes = models.DateField(verbose_name='Início das Inscrições')
    data_termino_inscricoes = models.DateField(verbose_name='Término das Inscrições')
    data_limite_correcao_inscricoes = models.DateField(verbose_name='Limite para Correção das Inscrições')

    class Meta:
        verbose_name = 'Pré-matrícula Internacional'
        verbose_name_plural = 'Pré-matrícula Internacional'

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/edu/pre_matricula_internacional/{self.pk}/'

    def is_em_periodo_inscricao(self):
        hoje = date.today()
        return self.data_inicio_inscricoes <= hoje <= self.data_termino_inscricoes

    def is_em_periodo_correcao(self):
        hoje = date.today()
        return self.data_termino_inscricoes <= hoje <= self.data_limite_correcao_inscricoes

    def terminou_periodo_correcao(self):
        hoje = date.today()
        return self.data_limite_correcao_inscricoes <= hoje

    def get_total_convocados(self):
        return self.planilhaconvocacao_set.values_list('vinculos', flat=True).count()

    def get_total_inscritos(self):
        return self.inscricaoalunoestrangeiro_set.values_list('vinculo', flat=True).count()

    def get_percentual_inscritos(self):
        total = self.get_total_convocados()
        if total:
            return int(self.get_total_inscritos() * 100.0 / total)
        return 0

    def get_inscricoes_deferidas(self):
        return self.inscricaoalunoestrangeiro_set.filter(situacao=InscricaoAlunoEstrangeiro.SITUACAO_DEFERIDA)

    def get_total_avaliados(self):
        return (
            self.inscricaoalunoestrangeiro_set.filter(
                situacao__in=[InscricaoAlunoEstrangeiro.SITUACAO_DEFERIDA, InscricaoAlunoEstrangeiro.SITUACAO_INDEFERIDA]
            )
            .values_list('vinculo', flat=True)
            .count()
        )

    def get_percentual_avaliados(self):
        total = self.get_total_inscritos()
        if total:
            return int(self.get_total_avaliados() * 100.0 / total)
        return 0

    def possui_inscricao_pendente_matricula(self):
        return self.get_inscricoes_deferidas().filter(aluno__isnull=True).exists()


COLUNAS_PLANILHA_CONVOCACAO = {'PASSAPORTE', 'NOME_COMPLETO', 'DATA_NASCIMENTO', 'SEXO', 'EMAIL', 'PAIS', 'CIDADE_NASCIMENTO', 'CIDADE_RESIDENCIA'}


def _validar_planilha_convocacao(df: pd.DataFrame) -> dict:
    """Recusa (ValueError) a planilha inválida antes de qualquer gravação; retorna o comum.Pais de cada valor da coluna PAIS."""
    import pandas as pd

    # Garante que as colunas esperadas existem
    if not COLUNAS_PLANILHA_CONVOCACAO.issubset(df.columns):
        raise ValueError(f'A planilha deve conter as colunas {COLUNAS_PLANILHA_CONVOCACAO}')

    # Garante que todas as colunas da planilha tenham valores em texto
    for coluna in df.columns:
        valores_nao_texto = df[coluna].dropna().map(lambda valor: not isinstance(valor, str))
        if valores_nao_texto.any():
            raise ValueError(f'A coluna "{coluna}" deve conter apenas valores do tipo texto.')

    for indice, linha in df.iterrows():
        for coluna in ('PASSAPORTE', 'PAIS', 'DATA_NASCIMENTO'):
            if pd.isna(linha.get(coluna)) or not str(linha.get(coluna)).strip():
                raise ValueError(f'A coluna "{coluna}" contém valor vazio na linha {indice + 2}.')
        valor_data = linha.get('DATA_NASCIMENTO')
        try:
            datetime.strptime(str(valor_data).strip(), '%d/%m/%Y')
        except ValueError as exc:
            raise ValueError(f'A coluna "DATA_NASCIMENTO" deve estar no formato "dd/mm/aaaa" na linha {indice + 2}.') from exc

    return _paises_origem(df)


def _paises_origem(df: pd.DataFrame) -> dict:
    # a pessoa usa comum.Pais (as cidades, edu.Pais); a conversão é só pelo nome, nunca pelo código
    paises_origem = {nome: pais_por_nome(nome) for nome in df['PAIS'].unique()}
    sem_correspondencia = [str(nome) for nome, pais in paises_origem.items() if pais is None]
    if sem_correspondencia:
        raise ValueError(f'A coluna "PAIS" contém país sem correspondência no cadastro de países do SUAP: {", ".join(sem_correspondencia)}.')
    return paises_origem


def _cadastrar_cidades_planilha(df: pd.DataFrame) -> None:
    paises = {}
    for linha in df[list(COLUNAS_PLANILHA_CONVOCACAO)].to_dict(orient='records'):
        paises.setdefault(linha['PAIS'], set()).update((linha['CIDADE_NASCIMENTO'], linha['CIDADE_RESIDENCIA']))

    for nome_pais, nomes_cidades in paises.items():
        pais = Pais.objects.filter(nome__iexact=nome_pais).first()
        if pais:
            for nome_cidade in nomes_cidades:
                nome_cidade_suap = f'{nome_cidade} - {pais.nome}'
                if not Cidade.objects.filter(pais=pais, nome__icontains=nome_cidade).exists():
                    Cidade.objects.create(pais=pais, nome=nome_cidade_suap)


def _prestador_do_convocado(
    passaporte: str | None, pais_origem: ComumPais, justificativa_cadastro: JustificativaUsuarioExterno | None
) -> PrestadorServico | None:
    """O prestador do convocado pelo par passaporte+país; sem ele, o legado do mesmo passaporte ainda sem país.

    Passaporte só identifica com o país; sem passaporte, o filtro não casa ninguém (nunca "passaporte IS NULL").
    O legado sem país (a higiene só infere o país de aluno) é reusado e ganha o país pela planilha, mantendo o login
    dele (só o número). Mais de um legado: ambíguo, recusa.
    """
    convocados = PrestadorServico.objects.filter(justificativa_cadastro=justificativa_cadastro)
    prestador_servico = convocados.filter(filtro_par_passaporte(passaporte, pais_origem, 'pessoa_fisica__')).first()
    if prestador_servico is not None or not passaporte:
        return prestador_servico
    # ponytail: iexact não tira espaços do valor gravado; casa o legado depois que o aplicar do deduplicar_pessoas normalizou os passaportes
    legados = list(convocados.filter(pessoa_fisica__passaporte__iexact=passaporte, pessoa_fisica__pais_origem__isnull=True)[:2])
    if len(legados) > 1:
        raise ValueError(f'Passaporte {passaporte}: mais de um usuário sem país de origem tem este passaporte; corrija o cadastro antes.')
    return legados[0] if legados else None


def _importar_convocado(linha: dict, pais_origem: ComumPais, justificativa_cadastro: JustificativaUsuarioExterno | None) -> Vinculo:
    """Cadastra (ou atualiza) a pessoa e o prestador de serviço do convocado e retorna o vínculo dele."""
    passaporte = formatar_passaporte(str(linha['PASSAPORTE']))
    prestador_servico = _prestador_do_convocado(passaporte, pais_origem, justificativa_cadastro)
    dados = {
        'passaporte': passaporte,
        'pais_origem': pais_origem,
        'nome': linha['NOME_COMPLETO'].strip(),
        'nacionalidade': Nacionalidade.ESTRANGEIRO,
        'sexo': linha['SEXO'].strip(),
        'nascimento_data': datetime.strptime(linha['DATA_NASCIMENTO'], '%d/%m/%Y'),
    }
    try:
        if prestador_servico is None:
            pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(dados, Politica.CAUTELOSA)
            prestador_servico = PrestadorServico.objects.create(
                pessoa_fisica=pessoa_fisica, justificativa_cadastro=JustificativaUsuarioExterno.objects.first(), ativo=True
            )
        else:
            # o próprio cadastro do convocado: a planilha é a fonte dele
            aplicar_politica(prestador_servico.pessoa_fisica, dados, Politica.AUTORITATIVA, preservar_documento=True)
            prestador_servico.pessoa_fisica.save()
    except ValidationError as erro:
        raise ValueError(f'Passaporte {passaporte}: {" ".join(erro.messages)}') from erro
    if not prestador_servico.ativo:
        prestador_servico.ativo = True
        prestador_servico.save()
    vinculo = prestador_servico.vinculos.first()
    vinculo.email_pessoal = str(linha['EMAIL']).strip()
    vinculo.save()
    return vinculo


class PlanilhaConvocacao(models.ModelPlus):
    pre_matricula = models.ForeignKey(PreMatriculaInternacional, verbose_name='Pré-Matrícula', on_delete=models.CASCADE)
    data_publicacao = models.DateFieldPlus(verbose_name='Data da Publicação')
    arquivo = models.FileFieldPlus(
        verbose_name='Arquivo',
        upload_to='planilha_selecionados',
        help_text='Planilha contendo as colunas PASSAPORTE, DATA_NASCIMENTO, NOME_COMPLETO, SEXO, EMAIL',
    )

    vinculos = models.ManyToManyField('comum.vinculo', verbose_name='Vínculos')

    class Meta:
        verbose_name = 'Planilha de Convocação'
        verbose_name_plural = 'Planilhas de Convocação'

    def __str__(self):
        return f'Planilha {self.id}'

    def processar(self) -> list:
        """Processa a planilha de convocação e retorna os vínculos encontrados.

        Returns:
            list: lista de vínculos processados.
        """
        df = self._ler_planilha()
        paises_origem = _validar_planilha_convocacao(df)
        _cadastrar_cidades_planilha(df)

        vinculos = []
        justificativa_cadastro = JustificativaUsuarioExterno.objects.first()
        for linha in df[list(COLUNAS_PLANILHA_CONVOCACAO)].to_dict(orient='records'):
            with transaction.atomic():
                vinculo = _importar_convocado(linha, paises_origem[linha['PAIS']], justificativa_cadastro)
                if not self.vinculos.filter(pk=vinculo.id).exists():
                    vinculos.append(vinculo)
                    self.vinculos.add(vinculo)
        return vinculos

    def _ler_planilha(self) -> pd.DataFrame:
        import pandas as pd

        with tempfile.NamedTemporaryFile(delete=False, suffix=self.arquivo.name.split('.')[-1]) as temp_file:
            temp_file.write(self.arquivo.file.read())
            temp_file_path = temp_file.name
        if temp_file_path.lower().endswith('csv'):
            return pd.read_csv(temp_file_path)
        return pd.read_excel(temp_file_path)

    def enviar_emails(self, vinculos):
        assunto = '[SUAP] Pré-matrícula / Pre-registration / Preinscripción'
        url = Configuracao.get_valor_por_chave('edu', 'url_manual_prematricula_internacional')
        url_es = Configuracao.get_valor_por_chave('edu', 'url_manual_prematricula_internacional_es')
        url_en = Configuracao.get_valor_por_chave('edu', 'url_manual_prematricula_internacional_en')
        curso = self.pre_matricula.matriz_curso.curso_campus.descricao_historico
        pt = f'Solicitamos a realização de sua pré-matrícula no curso "{curso}". Para obter mais detalhes, acesse: {url} .'
        en = f'We request that you complete your pre-registration for the course "{curso}". For more details, please visit: {url_en} .'
        es = f'Le solicitamos complete su preinscripción para el curso "{curso}". Para más detalles, visite: {url_es} .'
        mensagem = f'Olá! / Hello! / ¡Hola!\n\n{pt}\n\n{en}\n\n{es}\n\n\nObrigado! / Thank you! / ¡Gracias!'
        for vinculo in vinculos:
            para = vinculo.email_notificacao
            send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [para])


class InscricaoAlunoEstrangeiro(models.ModelPlus):
    SITUACAO_SOLICITADA = 1
    SITUACAO_AGUARDANDO_CORRECAO = 2
    SITUACAO_DEFERIDA = 3
    SITUACAO_INDEFERIDA = 4

    SITUACAO_CHOICES = [
        (SITUACAO_SOLICITADA, 'Aguardando Avaliação'),
        (SITUACAO_AGUARDANDO_CORRECAO, 'Aguardando Correção'),
        (SITUACAO_DEFERIDA, 'Deferida'),
        (SITUACAO_INDEFERIDA, 'Indeferida'),
    ]
    pre_matricula = models.ForeignKey(PreMatriculaInternacional, verbose_name='Pré-Matrícula', on_delete=models.CASCADE)
    # 1. Dados Pessoais/ Personal Data / Datos Personales
    # 1.1 Nome(s) / Nombre(s) / Given name(s):
    # 1.2. Sobrenome(s) / Apellido(s) / Family name(s) / Surname(s):
    # 1.3. Data de Nascimento / Fecha de Nacimiento / Date of Birth (dd/mm/aaaa):
    vinculo = models.ForeignKeyPlus('comum.vinculo', verbose_name='Vínculo', on_delete=models.CASCADE)
    foto = ImageWithThumbsField(
        storage=get_overwrite_storage(),
        use_id_for_name=True,
        upload_to='inscricao_estrangeiros',
        sizes=((75, 100), (150, 200)),
        null=True,
        blank=True,
    )
    # 1.4. Nacionalidade / Nacionalidad / Nationality:
    nacionalidade = models.CharFieldPlus(
        max_length=255, verbose_name='Nacionalidade', null=True, choices=Aluno.TIPO_NACIONALIDADE_CHOICES, help_text='Nacionalidad / Nationality'
    )
    pais_origem = models.ForeignKeyPlus('edu.Pais', verbose_name='País de Origem', help_text='País / Country')
    naturalidade = models.ForeignKeyPlus(
        'edu.Cidade',
        verbose_name='Naturalidade',
        null=True,
        blank=True,
        help_text='Lugar onde nasceu / Lugar de nacimiento / Place of birth',
        related_name='cidades_naturalidade',
    )
    # 1.5. Número do Passaporte / Número de Pasaporte / Passport Number:
    numero_passaporte = models.CharFieldPlus(max_length=50, verbose_name='Nº do Passaporte', default='')
    # 1.6. Data de Emissão do Passaporte / Fecha de Emisión del Pasaporte / Passport Date of Issue (dd/mm/aaaa):
    data_passaporte = models.DateFieldPlus(
        verbose_name='Data de Emissão do Passaporte', help_text='Fecha de Emisión del Pasaporte / Passport Date of Issue (dd/mm/aaaa)'
    )
    # 1.7. Raça / Etnia / Raza / Etnia / Race / Ethnicity: (marque uma opção / marque una opción / select one option):
    raca = models.ForeignKeyPlus('comum.Raca', verbose_name='Raça/Etnia', on_delete=models.CASCADE, help_text='Raza/Etnia / Race/Ethnicity')
    # 1.8. Em caso de indígena ou quilombola, informe a qual comunidade quilombola ou povo/tribo indígena pertence.
    # En caso de ser indígena o quilombola, indique a qué comunidad quilombola o pueblo/tribu indígena pertenece.
    # If Indigenous or Quilombola, please state which Quilombola community or Indigenous people/tribe you belong to:
    povo_indigena = models.ForeignKeyPlus(
        'comum.PovoIndigena',
        verbose_name='Comunicade Indígena/Quilombola',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text='Comunidad quilombola o pueblo/tribu indígena / Quilombola community or indigenous people/tribe',
    )
    # 1.9. Gênero / Género / Gender:

    # 1.10. Estado Civil / Estado Civil / Marital Status:
    estado_civil = models.ForeignKeyPlus(
        'comum.EstadoCivil', verbose_name='Estado Civil', on_delete=models.CASCADE, help_text='Estado Civil / Marital Status'
    )
    # 2. Deficiências, Transtornos e Superdotação / Disabilities, Disorders and Giftedness / Discapacidades, Trastornos y Superdotación

    # 2.1. Possui alguma deficiência, transtorno e/ou superdotação?
    # ¿Presenta alguna discapacidad, trastorno y/o superdotación?
    # Do you have any disability, disorder and/or giftedness?
    # 2.2. Deficiência (especificar) / Discapacidad (especificar) / Disability (specify):
    # 2.3. Transtorno (especificar) / Trastorno (especificar) / Disorder (specify):
    # 2.4. Superdotação / Altas Habilidades (especificar) / Superdotación / Altas Capacidades (especificar) / Giftedness / High Ability (specify):

    deficiencias = models.ManyToManyFieldPlus('edu.Deficiencia', verbose_name='Deficiências', blank=True, help_text='Discapacidades / Disabilities')
    outras_nees = models.ManyToManyFieldPlus(
        'edu.TipoNEE',
        verbose_name='Outros tipos de NEEs',
        blank=True,
        help_text='Otras necesidades educativas especiales / Other special educational needs',
    )

    # 3. Vínculo Acadêmico com a Universidade / Academic Affiliation with the University / Vinculación Académica con la Universidad

    # 3.1. Tipo de Vínculo com a Universidade / Tipo de Vinculación con la Universidad / Type of Affiliation with the University:
    # (ex.: graduação, pós-graduação, intercâmbio, aluno especial / licenciatura, maestría, intercambio, aluno especial / undergraduate, graduate, exchange, visiting student)
    tipo_vinculo_universitario = models.CharField(
        verbose_name='Tipo de Vínculo com a Universidade',
        help_text='Tipo de Vinculación con la Universidad / Type of Affiliation with the University',
        choices=[
            ('graduacao', 'Graduação / licenciatura / undergraduate'),
            ('pos_graduacao', 'Pós-graduação / maestría / graduate'),
            ('intercambio', 'Intercâmbio / intercambio / exchange'),
            ('aluno_especial', 'Aluno especial / visiting student'),
        ],
    )
    # 3.2. Nível de Ensino / Nivel de Estudios / Level of Education:
    # (ex.: graduação, mestrado, doutorado, curso técnico / licenciatura, maestría, doctorado / undergraduate, master's, PhD, technical course)
    nivel_ensino = models.CharField(
        verbose_name='Nível de Ensino',
        help_text='Nivel de Estudios / Level of Education',
        choices=[
            ('graduacao', 'Graduação / licenciatura / undergraduate'),
            ('mestrado', "Mestrado / maestría / master's"),
            ('doutorado', 'Doutorado / doctorado / PhD'),
            ('curso_tecnico', 'Curso técnico / technical course'),
        ],
    )

    # 3.3. Tipo de Instituição / Tipo de Institución / Type of Institution:
    tipo_instituicao = models.ForeignKeyPlus(
        TipoInstituicaoEstrangeira,
        verbose_name='Tipo de Instituição',
        on_delete=models.CASCADE,
        help_text='Tipo de Institución / Type of Institution',
    )
    # 3.4. Universidade (de origem ou de vínculo) / Universidad (de origen o de vinculación) / University (home or partner institution):
    universidade = models.CharFieldPlus(
        verbose_name='Universidade (de origem ou de vínculo)',
        help_text='Universidad (de origen o de vinculación) / University (home or partner institution)',
    )
    # 4. Dados de Filiação / Parent/Guardian Information / Datos de Filiación

    # 4.1. Nome(s) da Mãe / Nombre(s) de la Madre / Mother's Given Name(s):
    nome_mae = models.CharFieldPlus(max_length=255, verbose_name='Nome(s) da Mãe', help_text="Nombre(s) de la Madre / Mother's Given Name(s)")

    # 4.2. Sobrenome(s) da Mãe / Apellido(s) de la Madre / Mother's Family Name(s):
    sobrenome_mae = models.CharFieldPlus(
        max_length=255, verbose_name='Sobrenome(s) da Mãe', help_text="Apellido(s) de la Madre / Mother's Family Name(s)"
    )

    # 4.3. Estado Civil da Mãe / Estado Civil de la Madre / Mother's Marital Status:
    estado_civil_mae = models.CharFieldPlus(
        verbose_name='Estado Civil da Mãe', choices=Aluno.ESTADO_CIVIL_CHOICES, help_text="Estado Civil de la Madre / Mother's Marital Status"
    )

    # 4.4. Nome(s) do Pai / Nombre(s) del Padre / Father's Given Name(s):
    nome_pai = models.CharFieldPlus(max_length=255, verbose_name='Nome(s) do Pai', help_text="Nombre(s) del Padre / Father's Given Name(s)")

    # 4.5. Sobrenome(s) do Pai / Apellido(s) del Padre / Father's Family Name(s):
    sobrenome_pai = models.CharFieldPlus(
        max_length=255, verbose_name='Sobrenome(s) do Pai', help_text="Apellido(s) del Padre / Father's Family Name(s)"
    )

    # 4.6. Estado Civil do Pai / Estado Civil del Padre / Father's Marital Status:
    estado_civil_pai = models.CharFieldPlus(
        verbose_name='Estado Civil do Pai', choices=Aluno.ESTADO_CIVIL_CHOICES, help_text="Estado Civil del Padre / Father's Marital Status"
    )

    # 5. Endereço Residencial / Residential Address / Dirección de Residencia

    # 5.1. Rua / Avenida / Calle / Avenida / Street / Avenue:
    logradouro = models.CharFieldPlus(max_length=255, verbose_name='Rua / Avenida', help_text=' Calle/Avenida / Street/Avenue')

    # 5.2. Número / Número / Number:
    numero = models.CharFieldPlus(max_length=255, verbose_name='Número', null=True)

    # 5.3. Complemento (apartamento, bloco, andar, etc.) / Complemento de Dirección / Address Complement (apartment, floor, etc.):
    complemento = models.CharFieldPlus(
        max_length=255,
        verbose_name='Complemento',
        null=True,
        blank=True,
        help_text='Complemento de Dirección / Address Complement (apartment, floor, etc.)',
    )

    # 5.4. Bairro / Barrio / District / Neighborhood:
    bairro = models.CharFieldPlus(max_length=255, verbose_name='Bairro', help_text='Barrio / District/Neighborhood')

    # 5.5. Cidade / Ciudad / City:
    cidade = models.ForeignKeyPlus('edu.Cidade', verbose_name='Cidade', help_text='Ciudad / City')

    # 5.6. País / País / Country:
    pais = models.ForeignKeyPlus('edu.Pais', verbose_name='País', help_text='País / Country', related_name='r1')

    # 5.7. CEP / Código Postal / Postal Code:
    cep = models.CharFieldPlus(max_length=255, verbose_name='CEP', help_text='Código Postal / Postal Code')

    # 6. Contatos / Contact Information / Datos de Contacto

    # 6.1. E-mail / Correo Electrónico / Email Address:
    email_secundario = models.EmailField(blank=True, verbose_name='E-mail', help_text='Correo Electrónico / Email Address')

    # 6.2. Telefone (com código do país e da cidade) / Teléfono (con código de país y ciudad) / Phone Number (with Country and Area Code):
    telefone = models.CharField(
        verbose_name='Telefone', help_text='Teléfono (con código de país y ciudad) / Phone Number (with Country and Area Code)'
    )

    # 7. Anexos de Documentação de Matrícula / Enrollment Documentation Attachments / Anexos de Documentación de Matrícula

    # 7.1. Passaporte completo (todas as páginas relevantes, em um único arquivo) / Pasaporte completo (todas las páginas relevantes, en un solo archivo) / Full passport (all relevant pages, in a single file):
    arquivo_passaporte = models.FileField(
        verbose_name='Passaporte completo',
        upload_to='internacionalizacao',
        help_text='Pasaporte completo (todas las páginas relevantes, en un solo archivo) / Full passport (all relevant pages, in a single file)',
    )
    # 7.2. Declaração de vínculo com a universidade parceira / Declaración de vinculación con la universidad socia / Declaration of affiliation with partner university:
    declaracao_vinculo = models.FileField(
        verbose_name='Declaração de vínculo com a universidade',
        upload_to='internacionalizacao',
        help_text='Declaración de vinculación con la universidad socia / Declaration of affiliation with partner university',
    )

    # 7.3. Anexo 1 (documentação adicional) / Anexo 1 (documentación adicional) / Attachment 1 (additional document):
    documento_adicional_1 = models.FileField(
        verbose_name='Anexo 1',
        upload_to='internacionalizacao',
        help_text='Anexo 1 (documentación adicional) / Attachment 1 (additional document)',
        null=True,
        blank=True,
    )

    # 7.4. Anexo 2 (documentação adicional) / Anexo 2 (documentación adicional) / Attachment 2 (additional document):
    documento_adicional_2 = models.FileField(
        verbose_name='Anexo 2',
        upload_to='internacionalizacao',
        help_text='Anexo 2 (documentación adicional) / Attachment 2 (additional document)',
        null=True,
        blank=True,
    )

    # 7.5. Anexo 3 (documentação adicional) / Anexo 3 (documentación adicional) / Attachment 3 (additional document):
    documento_adicional_3 = models.FileField(
        verbose_name='Anexo 3',
        upload_to='internacionalizacao',
        help_text='Anexo 3 (documentación adicional) / Attachment 3 (additional document)',
        null=True,
        blank=True,
    )

    # 7.6. Anexo 4 (documentação adicional) / Anexo 4 (documentación adicional) / Attachment 4 (additional document):
    documento_adicional_4 = models.FileField(
        verbose_name='Anexo 4',
        upload_to='internacionalizacao',
        help_text='Anexo 4 (documentación adicional) / Attachment 4 (additional document)',
        null=True,
        blank=True,
    )

    # 7.7. Anexo 5 (documentação adicional) / Anexo 5 (documentación adicional) / Attachment 5 (additional document):
    documento_adicional_5 = models.FileField(
        verbose_name='Anexo 5',
        upload_to='internacionalizacao',
        help_text='Anexo 5 (documentación adicional) / Attachment 5 (additional document)',
        null=True,
        blank=True,
    )

    situacao = models.IntegerField(verbose_name='Situação', choices=SITUACAO_CHOICES, default=1)
    avaliador = models.ForeignKeyPlus('comum.vinculo', verbose_name='Avaliador', on_delete=models.CASCADE, related_name='r1', null=True)
    data_avaliacao = models.DateTimeField(verbose_name='Data/Hora da Avaliação', null=True)
    observacao_avaliacao = models.TextField(verbose_name='Observação da Avaliação', null=True)

    aluno = models.ForeignKey(Aluno, verbose_name='Aluno', on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name = 'Pré-matricula de Aluno Estrangeiro'
        verbose_name_plural = 'Pré-matriculas de Aluno Estrangeiro'

    def get_absolute_url(self):
        return f'/edu/inscricao_aluno_estrangeiro/{self.pk}/'

    def get_solicitacoes_correcao_pendente(self):
        return self.solicitacaocorrecaoinscricaoalunoestrangeiro_set.filter(observacao_correcao__isnull=True)

    def get_observacao_solicitacao_correcao(self):
        return self.get_solicitacoes_correcao_pendente().values_list('observacao_solicitacao', flat=True).order_by('id').last()

    def __str__(self):
        return f'Inscrição - {self.vinculo.pessoa.nome} ({self.numero_passaporte})'

    def is_em_correcao(self):
        return self.situacao == InscricaoAlunoEstrangeiro.SITUACAO_AGUARDANDO_CORRECAO

    def is_avaliada(self):
        return self.situacao in (InscricaoAlunoEstrangeiro.SITUACAO_DEFERIDA, InscricaoAlunoEstrangeiro.SITUACAO_INDEFERIDA)

    def cancelar_avaliacao(self):
        self.data_avaliacao = None
        self.avaliador = None
        self.situacao = InscricaoAlunoEstrangeiro.SITUACAO_SOLICITADA
        self.observacao_avaliacao = None
        self.save()

    def get_foto_150x200_url(self):
        return self.foto and self.foto.url_150x200 or '/static/comum/img/default.jpg'

    def gerar_matricula(
        self,
        turno: Turno,
        polo: Polo | None,
        forma_ingresso: FormaIngresso,
        convenio_internacional: Convenio | None,
        possui_convenio: bool,
        convenio: Convenio | None,
        numero_pasta: str,
        observacao_matricula: str,
    ) -> None:
        if self.aluno is None:
            pessoa_fisica = self.vinculo.pessoa.pessoafisica
            prefixo = f'{self.pre_matricula.ano_letivo}{self.pre_matricula.periodo_letivo}{self.pre_matricula.matriz_curso.curso_campus.codigo}'
            matricula = SequencialMatricula.proximo_numero(prefixo)
            aluno = Aluno.objects.create(
                pessoa_fisica=pessoa_fisica,
                matricula=matricula,
                nacionalidade=self.nacionalidade,
                passaporte=self.numero_passaporte,
                estrangeiro_sem_passaporte=False,
                estado_civil=self.estado_civil,
                logradouro=self.logradouro,
                numero=self.numero,
                complemento=self.complemento,
                bairro=self.bairro,
                cep=self.cep,
                cidade=self.cidade,
                tipo_zona_residencial=None,
                nome_pai=f'{self.nome_pai} {self.sobrenome_pai}',
                estado_civil_pai=self.estado_civil_pai,
                pai_falecido=False,
                nome_mae=f'{self.nome_mae} {self.sobrenome_mae}',
                estado_civil_mae=self.estado_civil_mae,
                mae_falecida=False,
                responsavel=None,
                email_responsavel=None,
                parentesco_responsavel=None,
                cpf_responsavel=None,
                telefone_principal=self.telefone,
                telefone_secundario=None,
                telefone_adicional_1=None,
                telefone_adicional_2=None,
                tipo_sanguineo=None,
                pais_origem=self.pais,
                naturalidade=self.naturalidade,
                nivel_ensino_anterior=None,
                tipo_instituicao_origem=None,
                nome_instituicao_anterior=None,
                ano_conclusao_estudo_anterior=None,
                numero_rg=None,
                uf_emissao_rg=None,
                orgao_emissao_rg=None,
                data_emissao_rg=None,
                numero_titulo_eleitor=None,
                zona_titulo_eleitor=None,
                secao=None,
                data_emissao_titulo_eleitor=None,
                uf_emissao_titulo_eleitor=None,
                numero_carteira_reservista=None,
                regiao_carteira_reservista=None,
                serie_carteira_reservista=None,
                estado_emissao_carteira_reservista=None,
                ano_carteira_reservista=None,
                tipo_certidao=None,
                cartorio=None,
                numero_certidao=None,
                folha_certidao=None,
                livro_certidao=None,
                data_emissao_certidao=None,
                matricula_certidao=None,
                ano_letivo=self.pre_matricula.ano_letivo,
                periodo_letivo=self.pre_matricula.periodo_letivo,
                turno=turno,
                polo=polo,
                forma_ingresso=forma_ingresso,
                convenio_internacional=convenio_internacional,
                cota_sistec=None,
                cota_mec=None,
                possui_convenio=possui_convenio,
                convenio=convenio,
                matriz=self.pre_matricula.matriz_curso.matriz,
                curso_campus=self.pre_matricula.matriz_curso.curso_campus,
                numero_pasta=numero_pasta,
                observacao_matricula=observacao_matricula,
                situacao_id=SituacaoMatricula.MATRICULADO,
                periodo_atual=1,
            )
            v = aluno.get_vinculo()
            if v:
                v.raca = self.raca
                v.povo_indigena = self.povo_indigena
                v.save(update_fields=['raca', 'povo_indigena'])
            (aluno.deficiencias.set(self.deficiencias.all()),)
            (aluno.outras_nees.set(self.outras_nees.all()),)
            self.aluno = aluno
            self.save()
            MatriculaPeriodo.objects.create(
                aluno=aluno, ano_letivo=aluno.ano_letivo, periodo_letivo=aluno.periodo_letivo, situacao_id=SituacaoMatriculaPeriodo.EM_ABERTO
            )
            self.cadastrar_documento_pasta_aluno('Passaporte', self.arquivo_passaporte)
            aluno.refresh_from_db()
            if self.foto:
                aluno.foto.save(f'{aluno.pk}.jpg', ContentFile(self.foto.read()))
                aluno.save()
            self.enviar_email_matricula()

    def enviar_email_matricula(self):
        url = f'{settings.SITE_URL}'
        curso = self.pre_matricula.matriz_curso.curso_campus.descricao_historico
        assunto = '[SUAP] Matrícula Realizada / Registration Completed / Registro completado'
        pt = f'Sua matrícula no curso "{curso}" foi realizada. Para mais detalhes, visite: {url} .'
        en = f'Your enrollment in course "{curso}"has been completed. For more details, please access: {url} .'
        es = f'Su inscripción en el curso "{curso}" se ha completado. Para más detalles, visite {url} .'
        mensagem = f'Olá! / Hello! / ¡Hola!\n\n{pt}\n\n{en}\n\n{es}\n\n\nObrigado! / Thank you! / ¡Gracias!'
        para = self.vinculo.email_notificacao
        send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [para])

    def cadastrar_documento_pasta_aluno(self, nome, arquivo):
        if not AlunoArquivo.objects.filter(aluno=self.aluno, nome_exibicao=nome).exists():
            agora = datetime.now()
            arquivo_unico = ArquivoUnico.get_or_create_from_file_bytes(arquivo.read(), 'application/pdf', arquivo.name.split('/')[-1], agora)[0]
            arquivo_aluno = AlunoArquivo()
            arquivo_aluno.tipo_origem_cadastro = AlunoArquivo.TIPO_ORIGEM_CADASTRO_MATRICULA_ONLINE
            arquivo_aluno.tipo = TipoAlunoArquivo.objects.get(nome=TipoAlunoArquivo.PASSAPORTE)
            arquivo_aluno.aluno = self.aluno
            arquivo_aluno.arquivo_unico = arquivo_unico
            arquivo_aluno.nome_original = arquivo.name.split('/')[-1]
            arquivo_aluno.nome_exibicao = nome
            arquivo_aluno.descricao = nome
            arquivo_aluno.validado = True
            arquivo_aluno.data_hora_upload = agora
            arquivo_aluno.data_hora_criacao_registro = agora
            arquivo_aluno.data_validacao = self.data_avaliacao
            arquivo_aluno.responsavel_validacao = self.avaliador.get_user()
            arquivo_aluno.save()

    def enviar_email_avaliacao(self):
        url = f'{settings.SITE_URL}{self.get_absolute_url()}'
        para = self.vinculo.email_notificacao
        if self.situacao == InscricaoAlunoEstrangeiro.SITUACAO_DEFERIDA:
            assunto = '[SUAP] Pré-matrícula Aprovada / Pre-registration Approved / Preinscripción Aprobada'
            pt = 'Sua solicitação de pré-matrícula foi aprovada. Sua matrícula será realizada em breve.'
            en = 'Your pre-registration request has been approved. Your registration will be completed soon.'
            es = 'Su solicitud de preinscripción ha sido aprobada. Su registro se completará pronto.'
            mensagem = f'Olá! / Hello! / ¡Hola!\n\n{pt}\n\n{en}\n\n{es}\n\n\nObrigado! / Thank you! / ¡Gracias!'
            send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [para])
        elif self.situacao == InscricaoAlunoEstrangeiro.SITUACAO_INDEFERIDA:
            assunto = '[SUAP] Pré-matrícula Recusada / Pre-registration Refused / Preinscripción Rechazado'
            pt = f'Sua solicitação de pré-matrícula não foi aprovada. Para mais detalhes, acesse "{url}".'
            en = f'Your pre-registration request has not been approved. For more details, please access "{url}".'
            es = f'Su solicitud de preinscripción no ha sido aprobada. Para más detalles, acceda "{url}".'
            mensagem = f'Olá! / Hello! / ¡Hola!\n\n{pt}\n\n{en}\n\n{es}\n\n\nObrigado! / Thank you! / ¡Gracias!'
            send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [para])


class SolicitacaoCorrecaoInscricaoAlunoEstrangeiro(models.ModelPlus):
    inscricao = models.ForeignKey(InscricaoAlunoEstrangeiro, verbose_name='Inscrição', on_delete=models.CASCADE)
    solicitante = models.ForeignKeyPlus('comum.vinculo', verbose_name='Solicitante', on_delete=models.CASCADE)
    data_hora_solicitacao = models.DateTimeField(verbose_name='Data/Hora da Solicitação')
    observacao_solicitacao = models.TextField(verbose_name='Observação da Solicitação')
    data_hora_correcao = models.DateTimeField(verbose_name='Data/Hora da Correção', null=True)
    observacao_correcao = models.TextField(verbose_name='Observação da Correção', null=True)

    class Meta:
        verbose_name = 'Solicitação de Correção de Pré-matricula'
        verbose_name_plural = 'Solicitações de Correção de Pré-matricula'

    def __str__(self):
        return f'Solicitação {self.pk}'

    def get_absolute_url(self):
        return f'/edu/inscricao_aluno_estrangeiro/{self.inscricao.pk}/'

    def enviar_email_solicitacao_correcao(self):
        url = f'{settings.SITE_URL}{self.get_absolute_url()}'
        assunto = '[SUAP] Correção de dados / Data Correction Request / Corrección de datos'
        pt = f'Solicitamos que corrija alguns dados relacionados a sua pré-matricula. Para mais detalhes, acesse {url}.'
        en = f'We request that you correct some information related to your pre-registration. For more details, please access {url}.'
        es = f'Le solicitamos que corrija algunos datos relacionados con su preinscripción. Para más detalles, acceda {url}.'
        mensagem = f'Olá! / Hello! / ¡Hola!\n\n{pt}\n\n{en}\n\n{es}\n\n\nObrigado! / Thank you! / ¡Gracias!'
        para = self.inscricao.vinculo.email_notificacao
        send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [para])

    def enviar_email_correcao(self):
        url = f'{settings.SITE_URL}{self.get_absolute_url()}'
        assunto = '[SUAP] Solicitação de Correção de Dados Atendida'
        mensagem = f'Por favor, acesse {url}?tab=avaliacao, para mais detalhes.'
        para = self.solicitante.email_notificacao
        send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [para])
