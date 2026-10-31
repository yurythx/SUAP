# Glossário — Contratos

> Linguagem ubíqua do módulo: termos de domínio, siglas e entidades, com a
> definição usada **aqui** e onde cada conceito vive no código. Complementa o
> [README.md](README.md) e o [HLA.md](HLA.md).

## Termos de domínio

| Termo | Definição (neste módulo) | Onde no código |
|---|---|---|
| Contrato | Instrumento contratual administrativo já publicado, identificado por número no formato `99999/9999`. O módulo o acompanha da publicação ao encerramento; não trata da fase licitatória. | `models.py` (`Contrato`) |
| Contratada | Pessoa jurídica (ou física/prestador) com quem a instituição firmou o contrato. Modelada como `Vinculo`, o que permite CNPJ, CPF ou prestador de serviço. | `models.py` (`Contrato.vinculo_contratado`, `contratada`) |
| Campus gerenciador | Unidade responsável pela gestão do contrato. Define quem pode editá-lo quando a restrição por unidade está ligada. | `models.py` (`Contrato.campus_gerenciador`, `pode_gerenciar`) |
| Campi atendidos | Unidades beneficiadas pela execução do contrato; usadas para filtrar medições, fiscais, anexos e ocorrências por campus. | `models.py` (`Contrato.campi`) |
| Setores gerenciadores | Setores cujos servidores com perfil de operador/gestor podem gerenciar o contrato; refina a restrição por unidade. | `models.py` (`Contrato.setores_gerenciadores`, `pode_gerenciar`) |
| Base legal | Fundamento normativo do contrato; carrega a vigência e a prorrogação máximas (em meses) que limitam a data final, e o texto de conformidade usado nos documentos. | `models.py` (`BaseLegal`, `tempo_maximo_prorrogacao`) |
| Continuidade | Classificação do contrato quanto à sua natureza temporal: contínuo, por escopo/não continuado ou indeterminado. Contratos contínuos são os candidatos a aditivo de prazo. | `models.py` (`CONTINUIDADE_CHOICES`, `Contrato.eh_continuo`) |
| Natureza | Se o contrato representa despesa, receita, ambas ou nenhum impacto financeiro. Contratos com receita habilitam a aba de valores de concessão. | `models.py` (`NATUREZA_CHOICES`, `Contrato.possui_arrecadacao_receita`) |
| Dedicação exclusiva de mão de obra | Marca que o contrato aloca trabalhadores terceirizados exclusivamente à instituição; habilita as abas de mão de obra e conta vinculada e torna o grau de risco obrigatório. | `models.py` (`Contrato.mao_obra_exclusiva`), `forms.ContratoForm.clean` |
| Grau de risco | Classificação (1, 2 ou 3) da atividade da empresa; define qual percentual de submódulo 4.1 é aplicado no cálculo da conta vinculada. | `models.py` (`Contrato.grau_risco`, `ContaVinculadaCalculo.obter_percentuais_para_contrato`) |
| Termo aditivo | Alteração formal do contrato, classificada como de prazo, de valor, de fiscal e/ou de outros. Aditivo de prazo empurra a data de vencimento; de valor soma (majoração) ou subtrai (supressão) do valor total. | `models.py` (`Aditivo`, `Contrato.get_data_vencimento`, `get_valor_aditivado`) |
| Apostilamento | Registro de alteração que não exige termo aditivo (reajuste, repactuação, dotação orçamentária ou outros); também compõe o valor total do contrato. | `models.py` (`Apostilamento`, `Contrato.get_valor_apostilado`) |
| Fiscal de contrato | Servidor designado por portaria para acompanhar a execução. Ser fiscal *daquele* contrato é pré-requisito para medir, informar IMR e registrar ocorrências. | `models.py` (`Fiscal`), `utils.verificar_fiscal` |
| Fiscal gestor do contrato | Tipo de fiscal habilitado a conduzir o recebimento definitivo e gerar o Termo de Recebimento Definitivo. | `models.py` (`TipoFiscal.eh_gestor_contrato`, `Contrato.eh_gestor_contrato`) |
| Cronograma | Cronograma físico-financeiro do contrato, identificado por número (com NL e RC do SIAFI). Um contrato pode ter vários; vale o mais recente. | `models.py` (`Cronograma`, `Contrato.get_cronograma`) |
| Parcela | Fatia prevista do cronograma, com período e valor previstos. É a unidade que se mede; pode ser marcada como "sem medição". | `models.py` (`Parcela`) |
| Medição | Registro do que foi efetivamente executado em uma parcela em um período, com nota/documento fiscal, valor executado, ocorrências e providências. É a unidade de pagamento. | `models.py` (`Medicao`) |
| Medição elétrica | Extensão da medição para contratos de energia: consumo de ponta/fora de ponta, demanda contratada/medida e multa por ultrapassagem acima de 5%. | `models.py` (`MedicaoEletrica`) |
| Valor executado | Somatório dos valores das medições do contrato; base do percentual de execução. | `models.py` (`Contrato.get_valor_executado`, `get_percentual_executado`) |
| Valor total | Valor inicial do contrato acrescido de aditivos de valor e apostilamentos. | `models.py` (`Contrato.get_valor_total`) |
| Saldo do contrato | Valor total menos o executado (`saldo atual`) ou menos executado e previsto em parcelas não medidas (`saldo do contrato`). Limita parcelas e medições. | `models.py` (`Contrato.get_saldo_atual`, `get_saldo_contrato`) |
| Recebimento provisório | Primeira etapa do aceite: o fiscal emite o "Relatório Circunstanciado de Recebimento Provisório" como documento eletrônico. Considera-se emitido quando o documento está assinado ou finalizado. | `views.gerar_despacho_documentotexto`, `models.Medicao.recebimento_provisorio_emitido` |
| Recebimento definitivo | Segunda etapa: o gestor/gerente confere os documentos comprobatórios, aponta pendências e conclui o aceite, culminando no Termo Circunstanciado de Recebimento Definitivo. | `views.receber_definitivamente_medicao`, `gerar_termo_definitivo_documentotexto` |
| Documento comprobatório | Item de checklist que a contratada deve apresentar junto à medição (ex.: guias, folhas). Configurado por contrato, confirmado pelo fiscal e revisado pelo gestor (Recebido / Pendente / Não se aplica). | `models.py` (`TipoDocumentoComprobatorio`, `ContratoTipoDocumentoComprobatorio`, `MedicaoTipoDocumentoComprobatorio`) |
| Conta vinculada | Conta bancária do contrato onde ficam retidas as provisões trabalhistas dos terceirizados; movimentada por depósitos (retenções) e saques (liberações). | `models.py` (`ContaContrato`, `MovimentacaoContaContrato`) |
| Retenção / cálculo da conta vinculada | Memória de cálculo, por trabalhador, dos valores de 13º, férias + 1/3, multa do FGTS e submódulo 4.1 retidos em uma medição; admite ajuste manual ou isenção, sempre com justificativa. | `models.py` (`Medicao.calcular_conta_vinculada`, `ContaVinculadaCalculo`, `ContaVinculadaCalculoItem`) |
| Submódulo 4.1 | Parcela dos encargos previdenciários/trabalhistas cujo percentual varia com o grau de risco da empresa; um dos componentes da retenção. | `models.py` (`ContaVinculadaCalculo.PERCENTUAIS_PADRAO`) |
| Mão de obra | Trabalhador terceirizado alocado ao contrato, com função, CBO, jornada, escolaridade, salário bruto e custo mensal. Também chamado de "terceirizado" nos relatórios. | `models.py` (`MaoDeObra`), `tasks.relatorio_terceirizados_xls` |
| Verba salarial | Componente da remuneração do terceirizado (por tipo e vigência); somada, forma o valor total das verbas. | `models.py` (`VerbaSalarialMaoDeObra`, `MaoDeObra.valor_total_das_verbas`) |
| Ocorrência (do contrato) | Fato registrado durante a execução, com prazo de resolução e situação (pendente/resolvida); pode ser notificado por e-mail à contratada e aos fiscais. | `models.py` (`Ocorrencia`, `notificar`) |
| Ocorrência em mão de obra | Evento relativo ao trabalhador terceirizado (afastamento, substituição etc.), por tipo e vigência. | `models.py` (`OcorrenciaMaoDeObra`) |
| Garantia contratual | Garantia exigida da contratada (seguro-garantia, fiança, caução ou registro no SIAFI), com vigência, valor e anexo. | `models.py` (`Garantia`, `Contrato.exige_garantia_contratual`) |
| Penalidade | Sanção aplicada à contratada: advertência, multa ou suspensão, com o arquivo que a documenta. | `models.py` (`Penalidade`) |
| Agenda de fiscalização | Ação de fiscalização programada para uma data, opcionalmente derivada de uma pré-configuração e atribuída a fiscais específicos; ao ser executada, recebe data de execução e anexos. | `models.py` (`Agenda`, `PreConfiguracaoAgenda`, `AnexoAgenda`) |
| Pendência (do contrato) | Situação em que falta ao contrato arquivo digitalizado, publicação, anexo de publicação/aditivo, fiscal, cronograma ou parcelas. | `models.py` (`Contrato.get_pendencias`) |
| Valor de concessão / arrecadação de receita | Valor arrecadado periodicamente em contratos de natureza receita (ex.: cessão de espaço). | `models.py` (`ArrecadacaoReceita`) |
| Item de contrato | Material ou serviço contratado, com quantidade e valores unitário/total; pode ser importado do ComprasGov. | `models.py` (`ItemContrato`) |
| Visualizador sistêmico | Perfil que enxerga contratos de todas as unidades mesmo com a restrição por unidade ligada: superusuário, Auditor e Supervisor de Contratos. | `views.contrato`, `admin.ContratoAdmin.get_queryset` |
| Consulta pública | Listagem e ficha de contrato acessíveis sem autenticação, expostas como serviço anônimo do SUAP. | `views.listar_contratos`, `contrato_publico`, `servicos_anonimos` |

## Siglas e abreviações

| Sigla | Significado | Contexto |
|---|---|---|
| IMR | Instrumento de Medição de Resultado | Percentual de qualidade do serviço por campus/parcela, que pode ser vinculado a uma medição (`models.IMR`) |
| CBO | Classificação Brasileira de Ocupações | Campo `categoria` da mão de obra (`MaoDeObra.categoria`) |
| CCT | Convenção Coletiva de Trabalho | Campo `numero_cct` da mão de obra |
| FGTS | Fundo de Garantia do Tempo de Serviço | Componente do cálculo da conta vinculada (multa do FGTS) |
| SIAFI | Sistema Integrado de Administração Financeira do Governo Federal | Tipo de garantia "Registro Garantia no SIAFI" e campo `pa_siafi` |
| PA | Lançamento Patrimonial (SIAFI) | `Garantia.pa_siafi` |
| NL | Nota de Lançamento | `Cronograma.nl` |
| RC | Registro de Contrato | `Cronograma.rc` |
| NE | Nota de Empenho | `DocumentoBase.TIPO_NE`, filtro do relatório de empenhos |
| UG | Unidade Gestora | Código/nome da UG nos relatórios de terceirizados e empenhos (`campus_gerenciador.codigo_ug`, `empenho.emitente_ug`) |
| UASG | Unidade Administrativa de Serviços Gerais | Parte do formato do campo `pregao` (`XXXXX/YYYY (AAAAAA)`) |
| UO | Unidade Organizacional | Campus/unidade (`rh.UnidadeOrganizacional`), usada em filtros e permissões |
| SUSEP | Superintendência de Seguros Privados | Anexo de consulta da garantia (`Garantia.consulta_susep`) |
| ComprasGov | Portal de Contratos do Comprasnet (`contratos.comprasnet.gov.br`) | Importação de contratos e itens (`services.ApiContratosGovBRService`) |
| XLS | Planilha Excel | Formato de todas as exportações do módulo (`XlsResponse`) |
| TA | Termo Aditivo | Abreviação usada no relatório de situação dos contratos (`ultimo_ta_prazo`, `ultimo_ta_valor`) |

## Entidades ↔ termo de negócio

| Modelo (código) | Termo de negócio | Observação |
|---|---|---|
| `Aditivo` | Termo Aditivo | `verbose_name = 'Termo Aditivo'`; o `__str__` exibe "Nº Termo (de Prazo, de Valor…)" |
| `MaoDeObra` | Terceirizado / colaborador do contrato | Nos relatórios e no formulário aparece como "Terceirizado"; a aba da tela chama "Mão de Obra" |
| `ContaContrato` | Conta vinculada | `__str__` retorna "Conta Vinculada &lt;descrição&gt;"; o campo `descricao` guarda o **número** da conta |
| `MovimentacaoContaContrato` | Depósito / saque na conta vinculada | O booleano `deposito` distingue as duas operações; estornos são movimentações inversas |
| `ContaVinculadaCalculo` | Memória de cálculo da retenção | Não é lançamento contábil: o lançamento é a `MovimentacaoContaContrato` de depósito |
| `Medicao.despacho_documentotexto` | Relatório Circunstanciado de Recebimento Provisório | Nome técnico "despacho" é legado; o documento gerado tem outro nome |
| `Medicao.termo_definitivo_documentotexto` | Termo Circunstanciado de Recebimento Definitivo | — |
| `MedicaoTipoDocumentoComprobatorio.confirmacao_fiscal` | "Incluído no Processo?" | Rótulo do formulário difere do nome do campo |
| `MedicaoTipoDocumentoComprobatorio.recebido_gerente` | Revisão do gestor (Recebido / Pendente / Não se aplica) | `parecer_gerente` é rotulado "Descrição da Pendência" |
| `ArrecadacaoReceita` | Valor de Concessão | A aba da tela e as views usam "Valor de Concessão"; o campo `data` é rotulado "Data da Concessão" |
| `PublicacaoContrato` / `PublicacaoAditivo` | Publicação (no DOU/imprensa oficial) | Ambas têm `verbose_name = 'Publicação'`; a do aditivo é espelhada na do contrato |
| `AnexoContrato` | Documento relacionado | Aparece na aba "Documentos Relacionados" junto com os documentos eletrônicos vinculados |
| `DocumentoTextoContrato` | Vínculo documento eletrônico ↔ contrato | Remoção **lógica** (`data_hora_remocao`), não exclusão física |
| `DocumentoEmpenhoContrato` | Empenho do contrato | Tabela de ligação com `tesouro_gerencial.DocumentoEmpenho`; o `__str__` mostra "Empenho &lt;n&gt;" |
| `DocumentoEmpenhoContratoMedicao` | Consumo do empenho na medição | Registra quanto de cada nota de empenho foi usado na medição |
| `PreConfiguracaoAgenda` | Modelo de ação de fiscalização | Catálogo carregado por `importar_dados_contratos`; `gatilho` hoje só tem "mão de obra exclusiva" |
| `Contrato.pregao` | Número da licitação | `verbose_name = 'Número da Licitação'`, mas o nome do campo preserva o termo legado "pregão" |
| `Contrato.arquivo` vs. `Contrato.arquivo_contrato` | Arquivo digitalizado do contrato | Dois campos coexistem: `arquivo` (`comum.Arquivo`, usado nas pendências) e `arquivo_contrato` (`PrivateFileField`). ⚠️ REVISAR: qual é o canônico não está explícito no código |
| `TipoOcorrencia` / `TipoVerbaSalarial` | Tipos de eventos da mão de obra | Apesar do nome genérico, **só** se aplicam a `OcorrenciaMaoDeObra`/`VerbaSalarialMaoDeObra` — a `Ocorrencia` do contrato não tem tipo |

---
_Gerado/atualizado via subagent `documentador` em 2026-08-11._
