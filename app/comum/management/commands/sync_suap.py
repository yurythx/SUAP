from django.apps.registry import apps
from django.conf import settings
from django.core.management import call_command

from djtools.management.commands import BaseCommandPlus

Configuracao = apps.get_model('comum', 'Configuracao')


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        commands = []

        # Adiciona os comandas básicos ------------------------------
        # ** CORE **

        # === RH ===
        commands.append('importar_siape')

        ############################################################################################################
        # Se for o primeiro dia do mês roda uma importação completa do historico de afastamentos e ferias do servidor
        ############################################################################################################

        # tem casos onde o instituto/órgão pode querer manter apenas uma função SIAPE ativa
        # nesses casos, o suap irá manter a função mais nova ativa e irá setar uma data fim para todas as outras funções em aberto
        # como é um caso muito particular, foi criada essa configuração para executar ou não essa funcionalidade
        deixa_apenas_uma_funcao_siape_ativa = Configuracao.get_valor_por_chave('rh', 'deixa_apenas_uma_funcao_siape_ativa')
        if deixa_apenas_uma_funcao_siape_ativa:
            commands.append('organizar_data_fim_historico_funcao')
        # -------------------------------------------------------------------------------------------------------------------------

        # commands.append('atualizar_prazos_exercicio_externo')
        commands.append('organizar_historico_setor_siape')
        commands.append('organizar_data_fim_historico_setor')
        commands.append('importar_contracheques')
        commands.append('importar_arquivos_scdp')
        # commands.append('importar_funcao_servidor')
        commands.append('atualizar_pessoa_fisica_sub_instances')
        commands.append('atualizar_setor_prestador')
        commands.append('deletar_log_emails_antigos')

        # === Comum ===
        commands.append('sync_emails')
        commands.append('limpar_index_layout')
        commands.append('clearsessions_suap')
        commands.append('clean_tasks')
        commands.append('remover_permissao_usuarios')
        commands.append('indeferir_solicitacoes_reserva_sala')
        commands.append('zip_fotos_funcionarios')
        installed_apps = settings.INSTALLED_APPS
        # === Demais aplicações ===
        if 'ae' in installed_apps:
            commands.append('gerar_bolsas_ae')
            commands.append('gerar_bolsas_ae_pesquisa')
            commands.append('gera_faltas_alimentacao')
            commands.append('ofertabolsa_ae_verificar_disponibilidade')
            commands.append('gera_solicitacoes_comprovantes_mensais')

            if 'edu' in installed_apps:
                commands.append('edu_inativar_participacao_ae')

        if 'edu' in installed_apps:
            commands.append('edu_importar_dados')
            commands.append('edu_importar_digitais')
            commands.append('edu_importar_fotos')
            commands.append('edu_importar_professores')
            commands.append('edu_checar_nada_consta')
            commands.append('edu_fechar_periodo')
            commands.append('edu_notificar_pendencias_secretarios')
            commands.append('edu_processar_pedidos_matricula')
            commands.append('edu_zip_fotos_alunos')
            commands.append('edu_apagar_usuarios_minicursos')
            commands.append('edu_gerar_auditoria_ensino')

        if 'processo_seletivo' in installed_apps:
            commands.append('processo_seletivo_enviar_notificacoes_matricula')

        if 'plan_estrategico' in installed_apps:
            commands.append('plan_estrategico_coletar_variaveis_edu')
            commands.append('plan_estrategico_coletar_variaveis_gestao')
            commands.append('plan_estrategico_coletar_variaveis_extensao')
            commands.append('plan_estrategico_coletar_variaveis_gestao_pessoas')
            commands.append('plan_estrategico_coletar_variaveis_pesquisa')
            commands.append('plan_estrategico_coletar_variaveis_pesquisa_rede')
            commands.append('plan_estrategico_coletar_variaveis_tesouro_gerencial')
            commands.append('plan_estrategico_coletar_variaveis_pos_periodo')
            commands.append('plan_estrategico_coletar_variaveis_extensao_rede')
            commands.append('plan_estrategico_totalizar_indicadores')
            commands.append('notifica_preenchimento_variaveis')
            commands.append('plan_estrategico_atualizar_valores_indicadores')
            commands.append('plan_estrategico_atualizar_valores_trimestrais')

        if 'clipping' in installed_apps:
            commands.append('clipping_importar')

        if 'gerenciador_projetos' in installed_apps:
            commands.append('gp_tarefas_recorrentes')

        if 'materiais' in installed_apps:
            commands.append('inativar_cotacao')

        if 'rsc' in installed_apps:
            commands.append('checa_datas_processos_rsc')

        if 'projetos' in installed_apps:
            commands.append('notifica_atrasos_projetos')

        if 'pesquisa' in installed_apps:
            commands.append('normaliza_pontuacoes_editais_pesquisa')
            commands.append('notifica_atrasos_projetos_pesquisa')
            commands.append('gerencia_prazos_indicacoes_avaliadores')
            commands.append('notificar_atraso_parecer_obra')
            commands.append('importar_rpi')
            commands.append('importar_rpi_software')

        if 'documento_eletronico' in installed_apps:
            commands.append('delete_revisions_documento_eletronico')

        if 'processo_eletronico' in installed_apps:
            commands.append('processo_eletronico_atualizar_status_geral_processo')
            commands.append('processo_eletronico_gerar_numeros')
            commands.append('processo_eletronico_atualizar_permissoes')
            if Configuracao.get_valor_por_chave('processo_eletronico', 'prazo_recebimento_processo'):
                commands.append('processo_eletronico_checar_prazos_recebimento')

        if 'protocolo' in installed_apps and Configuracao.get_valor_por_chave('protocolo', 'habilitar_importacao_sei'):
            commands.append('importar_sei')

        if 'eleicao' in installed_apps:
            commands.append('atualizar_publico_eleicoes_em_andamento')

        if 'enquete' in installed_apps:
            commands.append('atualizar_publico_enquete_em_andamento')

        if 'eventos' in installed_apps:
            commands.append('finalizar_eventos')
            commands.append('eventos_processar_avaliacoes')

        if 'integracao_wifi' in installed_apps:
            commands.append('revogar_autorizacoes_dispositivos')

        if 'gestao' in installed_apps:
            commands.append('processar_variaveis')

        if 'licenca_capacitacao' in installed_apps:
            commands.append('processar_quantitativo_lic_capacitacao')

        if 'catalogo_provedor_servico' in installed_apps:
            commands.append('expirar_solicitacoes_incompletas')
            commands.append('enviar_email_aguardando_correcao')

        if 'cnpq' in installed_apps:
            commands.append('atualizar_datas_do_servidor')

        if 'erros' in installed_apps:
            commands.append('popular_links_gitlab')

        if 'saude' in installed_apps:
            commands.append('notificar_passaportes_invalidos')
            commands.append('encerra_avaliacoes_biomedicas_inativas')

        if 'demandas' in installed_apps:
            commands.append('remover_ambientes_homolog_expirados')

        if 'contratos' in installed_apps:
            commands.append('notificar_contratos_sem_garantia_vinculada')
            commands.append('notificar_contratos_a_expirar')
            commands.append('notificar_fiscalizacao_contratos')

        if 'patrimonio' in installed_apps:
            commands.append('patrimonio_depreciar_inventarios')

        if 'demandas_externas' in installed_apps:
            commands.append('notifica_demandas_com_pendencias')

        if 'pgd' in installed_apps:
            commands.append('sincronizar_permissoes_comissao_pgd')

        if 'pgd2' in installed_apps:
            commands.append('sincronizar_permissoes_comissao_pgd2')
            commands.append('enviar_dados_api_pgd2')
            commands.append('notifica_pgd2')

        if 'centralservicos' in installed_apps:
            commands.append('centralservicos_notificacoes_diarias')

        if 'progressao_docente' in installed_apps:
            commands.append('docentes_a_progredir')
            commands.append('alerta_emails_avaliacoes')

        if 'progressoes' in installed_apps:
            commands.append(
                (
                    'servidores_a_progredir',
                    '-s',
                )
            )
            commands.append('alertar_responsaveis_processos')

        if 'pafc' in installed_apps:
            commands.append('pafc_sincronizar')
            commands.append('pafc_notificar_pendencia_revisao_tecnica')

        if 'ppc' in installed_apps:
            commands.append('ppc_sincronizar')

        for command in commands:
            tipo = type(command)
            if tipo is str:
                call_command(command, interactive=False, raise_exception=False, verbosity=0)
            elif tipo is tuple:
                call_command(command[0], command[1], interactive=False, raise_exception=False, verbosity=0)
