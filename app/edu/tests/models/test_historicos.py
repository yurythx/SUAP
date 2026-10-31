from djtools.forms.fields.number import NotaField
from edu.forms.historicos import AproveitamentoEstudoForm, CertificarConhecimentoForm
from edu.models.historico import AproveitamentoEstudo, CertificacaoConhecimento


def test_form_aproveitamento_usa_notafield_no_campo_nota():
    campo_nota = AproveitamentoEstudo._meta.get_field('nota')

    assert isinstance(campo_nota.formfield(), NotaField)


def test_form_aproveitamento_define_modelo_e_expoe_campo_nota():
    assert AproveitamentoEstudoForm._meta.model is AproveitamentoEstudo
    assert 'nota' in AproveitamentoEstudoForm._meta.fields


def test_form_aproveitamento_nao_tem_clean_nota_customizado():
    assert not hasattr(AproveitamentoEstudoForm, 'clean_nota')


def test_form_certificacao_usa_notafield_no_campo_nota():
    campo_nota = CertificacaoConhecimento._meta.get_field('nota')

    assert isinstance(campo_nota.formfield(), NotaField)


def test_form_certificacao_define_modelo_e_expoe_campo_nota():
    assert CertificarConhecimentoForm._meta.model is CertificacaoConhecimento
    assert 'nota' in CertificarConhecimentoForm._meta.fields
