# Funções sem iteração com a aplicação (página) ------------------------------------------------------------------------
from behave import given
from django.apps import apps

from processo_eletronico.models import TipoProcesso
from tesouro_gerencial.models import (
    AcaoGoverno,
    ClassificacaoInstitucional,
    DocumentoEmpenho,
    DocumentoEmpenhoItem,
    EsferaOrcamentaria,
    FonteRecurso,
    NaturezaDespesa,
    PlanoInterno,
    ProgramaTrabalhoResumido,
    SubElementoNaturezaDespesa,
    UnidadeGestora,
)


@given('os cadastros básicos do módulo contratos')
def step_cadastros_do_modulo_demandas(context):
    from rh.models import PessoaJuridica, Servidor

    Processo = apps.get_model('processo_eletronico', 'processo')
    PessoaJuridica.objects.get_or_create(cnpj='45.006.424/0001-00', defaults={'nome': 'Pessoa Jurídica'})[0]
    servidor_fiscal = Servidor.objects.get(matricula='996622')
    gerente_contratos = Servidor.objects.get(matricula='996623')
    # Cadastra um processo do Protocolo
    tipo = TipoProcesso.objects.first()
    processo = Processo.objects.create(
        assunto='Assunto do Contrato',
        tipo_processo=tipo,
        setor_criacao=servidor_fiscal.setor,
        nivel_acesso=1,
        usuario_gerador=servidor_fiscal.get_user(),
        modificado_por=servidor_fiscal.get_user(),
    )
    processo.interessados.add(servidor_fiscal.vinculos.first())
    processo.interessados.add(gerente_contratos.vinculos.first())
    processo.save()

    documento = DocumentoEmpenho()
    documento.numero = '2020NE000001'
    documento.tipo = DocumentoEmpenho.TIPO_NE
    documento.data_emissao = '2020-01-01'
    documento.acao_governo = AcaoGoverno.objects.create(codigo='2994', nome='ASSISTENCIA AOS ESTUDANTES DAS INSTITUICOES FEDERAIS DE EDUC')
    documento.emitente_ug = UnidadeGestora.objects.create(codigo='152808', nome='CAMPUS SAO PAULO DO POTENGI')
    documento.esfera_orcamentaria = EsferaOrcamentaria.objects.create(codigo='1', nome='ORCAMENTO FISCAL')
    documento.fonte_recurso = FonteRecurso.objects.create(codigo='0100000000', nome='RECURSOS ORDINARIOS')
    documento.plano_interno = PlanoInterno.objects.create(codigo='L2994P23AEN', nome='AUXILIO FINANCEIRO DE ASSISTENCIA ESTUDANTIL')
    documento.ptres = ProgramaTrabalhoResumido.objects.create(codigo='108939')
    documento.responsavel_ug = documento.emitente_ug
    documento.unidade_orcamentaria = ClassificacaoInstitucional.objects.create(codigo='26435', nome='INST.FED.DE EDUC.,CIENC.E TEC.DO RN')
    documento.save()

    natureza_despesa = NaturezaDespesa.objects.create(codigo='339018', nome='AUXILIO FINANCEIRO A ESTUDANTES')
    subitem = SubElementoNaturezaDespesa.objects.create(
        codigo='3390181', codigo_subelemento='1', natureza_despesa=natureza_despesa, nome='INDENIZACOES'
    )
    documento_item = DocumentoEmpenhoItem()
    documento_item.documento_empenho = documento
    documento_item.subitem = subitem
    documento_item.valor = '100000.00'
    documento_item.save()
