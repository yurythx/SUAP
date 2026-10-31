from ae.models import (
    BeneficioGovernoFederal,
    CompanhiaDomiciliar,
    ContribuinteRendaFamiliar,
    EstadoCivil,
    Idioma,
    MeioTransporte,
    NecessidadeEspecial,
    NivelEscolaridade,
    OfertaAlimentacao,
    OfertaPasse,
    RazaoAfastamentoEducacional,
    SituacaoTrabalho,
    TipoAreaResidencial,
    TipoEmprego,
    TipoImovelResidencial,
)
from rh.models import UnidadeOrganizacional

DEFICIENCIAS_CHOICES = ['Auditiva', 'Física', 'Mental', 'Múltiplas', 'Visual', 'Condutas Típicas', 'Superdotado/Altas habilidades']

NecessidadeEspecial.objects.all().delete()
for item in DEFICIENCIAS_CHOICES:
    obj = NecessidadeEspecial()
    obj.descricao = item
    obj.save()

ESTADO_CIVIL_CHOICES = ['Solteiro(a)', 'Casado(a)', 'União Estável', 'Divorciado(a)', 'Viúvo(a)']

EstadoCivil.objects.all().delete()
for item in ESTADO_CIVIL_CHOICES:
    obj = EstadoCivil()
    obj.descricao = item
    obj.save()

ESCOLARIDADE_CHOICES = [
    'Analfabeto',
    'Alfabetizado',
    'Ensino fundamental completo',
    'Ensino fundamental incompleto',
    'Ensino médio completo',
    'Ensino médio incompleto',
    'Ensino superior completo',
    'Ensino superior incompleto',
    'Pós-gradução completa',
    'Pós-graduação incompleta',
    'Não sei informar',
]

NivelEscolaridade.objects.all().delete()
for item in ESCOLARIDADE_CHOICES:
    obj = NivelEscolaridade()
    obj.descricao = item
    obj.save()

RAZAO_PARA_ESTUDAR_CHOICES = [
    'Necessidade de trabalhar para ajudar no sustento familiar',
    'Baixa condição financeira para se manter na escola',
    'Desinteresse pessoal',
    'Desvalorização da educação',
    'Outra razão',
]

RazaoAfastamentoEducacional.objects.all().delete()
for item in RAZAO_PARA_ESTUDAR_CHOICES:
    obj = RazaoAfastamentoEducacional()
    obj.descricao = item
    obj.save()

IDIOMAS_CHOICES = ['Inglês', 'Espanhol', 'Francês', 'Outro']

Idioma.objects.all().delete()
for item in IDIOMAS_CHOICES:
    obj = Idioma()
    obj.descricao = item
    obj.save()

SITUACAO_TRABALHO_CHOICES = [
    'Trabalha com vínculo empregatício',
    'Trabalha sem vínculo empregatício',
    'Desempregado(a)',
    'Nunca trabalhou',
    'Aposentado(a)',
]

SituacaoTrabalho.objects.all().delete()
for item in SITUACAO_TRABALHO_CHOICES:
    obj = SituacaoTrabalho()
    obj.descricao = item
    obj.save()

MEIO_TRANSPORTE_CHOICES = ['Bicicleta', 'Moto', 'Mototaxi', 'Automóvel', 'Transporte coletivo', 'Transporte cedido por prefeitura', 'A pé', 'Outro']

MeioTransporte.objects.all().delete()
for item in MEIO_TRANSPORTE_CHOICES:
    obj = MeioTransporte()
    obj.descricao = item
    obj.save()

CONTRIBUINTE_RENDA_FAMILIAR_CHOICES = ['Pai', 'Mãe', 'Próprio aluno', 'Cônjuge', 'Avô(ó)', 'Tio(a)', 'Irmão(ã)', 'Parentes', 'Outros']

ContribuinteRendaFamiliar.objects.all().delete()
for item in CONTRIBUINTE_RENDA_FAMILIAR_CHOICES:
    obj = ContribuinteRendaFamiliar()
    obj.descricao = item
    obj.save()

TIPO_EMPREGO_CHOICES = [
    'Serviço público',
    'Empresa privada',
    'Militar',
    'Aposentado ou pensionsita',
    'Autonomo',
    'Desempregado',
    'Não sei informar',
    'Outro',
]

TipoEmprego.objects.all().delete()
for item in TIPO_EMPREGO_CHOICES:
    obj = TipoEmprego()
    obj.descricao = item
    obj.save()

MORADIA_CHOICES = ['Pais', 'Parentes', 'Outros Estudante', 'Conjuge', 'Ninguém', 'Outro']

CompanhiaDomiciliar.objects.all().delete()
for item in MORADIA_CHOICES:
    obj = CompanhiaDomiciliar()
    obj.descricao = item
    obj.save()

TIPO_IMOVEL_CHOICES = ['Próprio', 'Financiado', 'Alugado', 'Cedido ou Emprestado', 'Herdado']

TipoImovelResidencial.objects.all().delete()
for item in TIPO_IMOVEL_CHOICES:
    obj = TipoImovelResidencial()
    obj.descricao = item
    obj.save()

TIPO_AREA_RESIDENCIAL_CHOICES = ['Urbano', 'Rural', 'Comunidade Indígena', 'Comunidade Quilombola']

TipoAreaResidencial.objects.all().delete()
for item in TIPO_AREA_RESIDENCIAL_CHOICES:
    obj = TipoAreaResidencial()
    obj.descricao = item
    obj.save()

BENEFICIO_GOVERNO_FEDERAL = ['Bolsa Família', 'Programa de Erradicação do Trabalho Infantil']

BeneficioGovernoFederal.objects.all().delete()
for item in BENEFICIO_GOVERNO_FEDERAL:
    obj = BeneficioGovernoFederal()
    obj.descricao = item
    obj.save()

OfertaAlimentacao.objects.all().delete()
OfertaPasse.objects.all().delete()
for uo in UnidadeOrganizacional.objects.suap().all():
    oferta = OfertaAlimentacao()
    oferta.campus = uo
    oferta.save()
    oferta = OfertaPasse()
    oferta.campus = uo
    oferta.save()

print('[OK]')
