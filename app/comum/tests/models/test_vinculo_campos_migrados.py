from comum.models import Vinculo


def test_vinculo_tem_os_campos_migrados():
    # email_notificacao NÃO está aqui: virou property derivada (institucional do papel, senão email_pessoal).
    nomes = {campo.name for campo in Vinculo._meta.get_fields()}
    esperados = {
        'email_pessoal',
        'setores_adicionais',
        'sistema_origem',
        'foto',
        'raca',
        'povo_indigena',
        'deficiencia',
    }
    assert esperados <= nomes


def test_vinculo_email_notificacao_e_property_derivada():
    assert isinstance(Vinculo.email_notificacao, property)


# NOTA: o teste `test_backfill_copia_campos_de_pessoa_e_pessoafisica` foi retirado na fatia S1
# da migração de call-sites (RemoveField de raca/povo_indigena/deficiencia/sistema_origem/
# setores_adicionais em rh/0102). Ele exercitava `comum/0115_backfill_campos_vinculo` chamando
# a função contra o registry REAL, setando esses campos em Pessoa/PessoaFisica. Com os campos
# removidos dos modelos atuais, a função (que lê `pessoa.sistema_origem`, `pf.raca_id`, ...) não
# roda mais contra o registry atual, e o setup do teste não consegue mais atribuí-los.
# Sob `--no-migrations` (pytest do SUAP) não há estado histórico para testar a migration de forma
# adequada. A migration é one-time, roda no deploy contra modelos históricos (onde os campos ainda
# existem) e foi validada quando escrita (S0). Não se edita migration aplicada → regressão ~nula.
