from professor_sv.models import SolicitacaoEmprestimoVaga, Grupo, Vaga, Configuracao, Contrato
from django.db.models import Q


def get_pendencias(user):
    lista_pendencias = []

    # Solicitações de emprestimo de vaga que devo analisar
    solicitacoes_emprestimo_aprovacao_pendente = SolicitacaoEmprestimoVaga.get_solicitacoes_emprestimo_aprovacao_pendente(user.get_relacionamento())
    if solicitacoes_emprestimo_aprovacao_pendente:
        pend_dict = {}
        pend_dict['msg'] = 'Solicitação(ões) de empréstimo de vaga de Professor Substituto/Visitante'
        pend_dict['subtitulo'] = 'pendente de análise'
        pend_dict['url'] = '/professor_sv/aprovar_solicitacao_emprestimo/'
        pend_dict['qtd'] = solicitacoes_emprestimo_aprovacao_pendente.count()
        lista_pendencias.append(pend_dict)

    config = Configuracao.get_configuracao()
    if config:
        # Existem emprestimos de vaga que devo saber
        # - notifica quem emprestou e quem pegou emprestado
        grupos_pode_gerenciar = Grupo.get_grupos_user_pode_cadastrar_contrato(user)

        # Obtem a qtd de dias de expiracao
        qtd_dias_expira_vaga = config.qtd_dias_alertar_expiracao_emprestimo_vaga
        qtd_dias_alerta_contrato = config.qtd_dias_alertar_expiracao_contrato

        # Alerta sobre emprestimo de vaga
        vagas_emprestimos_a_vencer = Vaga.get_vagas_emprestimos_a_vencer(qtd_dias_expira_vaga)
        vagas_emprestimos_a_vencer = vagas_emprestimos_a_vencer.filter(
            Q(grupo_dono__in=grupos_pode_gerenciar) | Q(grupo_tomador__in=grupos_pode_gerenciar)
        )
        if vagas_emprestimos_a_vencer.exists():
            pend_dict = {}
            pend_dict['msg'] = 'Empréstimos de vaga de Professor Substituto/Visitante'
            pend_dict['subtitulo'] = f'a expirar em {qtd_dias_expira_vaga} dias'
            pend_dict['url'] = f'/admin/professor_sv/vaga/?vex={qtd_dias_expira_vaga}'
            pend_dict['qtd'] = vagas_emprestimos_a_vencer.count()
            lista_pendencias.append(pend_dict)

        # Alerta sobre contrato
        contratos_proximos_a_expirar = Contrato.get_proximos_a_expirar(qtd_dias_alerta_contrato)
        contratos_proximos_a_expirar = contratos_proximos_a_expirar.filter(
            Q(vaga__grupo_dono__in=grupos_pode_gerenciar) | Q(vaga__grupo_tomador__in=grupos_pode_gerenciar)
        )
        if contratos_proximos_a_expirar.exists():
            pend_dict = {}
            pend_dict['msg'] = 'Contratos de Professor Substituto/Visitante'
            pend_dict['subtitulo'] = f'a expirar em {qtd_dias_alerta_contrato} dias'
            pend_dict['url'] = f'/admin/professor_sv/contrato/?cex={qtd_dias_alerta_contrato}'
            pend_dict['qtd'] = contratos_proximos_a_expirar.count()
            lista_pendencias.append(pend_dict)

    return lista_pendencias
