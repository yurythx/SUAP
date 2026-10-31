## 3.8.20 (2023-12-29)

### changed (3 changes)

- [[saude] Na agenda de atendimentos, exibe apenas hora de início se o usuário for aluno](cosinf/suap@9dc575df85442c29a40ad81b44c53b1c84ddb23f) ([merge request](cosinf/suap!13909))
- [[tesouro_gerencial] Importação das Notas de Dotação](cosinf/suap@dfc676999efe5654a7aef0e38d56549647297537) ([merge request](cosinf/suap!13903))
- [[projetos] Otimização da tela de projeto. Resolves #10934](cosinf/suap@49818fc5e939fc7f649d62062da6d8b8b9b4a954) ([merge request](cosinf/suap!13904))
- [[edu] Correção/ajuste na funcionalidade de importação de alunos via CSV para o SUAP](cosinf/suap@f09205fe611b77f9824f10b6080d6f908341837e) ([merge request](cosinf/suap!13908))

### fixed (2 changes)

- [Ajuste na exibição de Dados do Recebedor na Requisição de Movimentação](cosinf/suap@029de37ab6e82a2f6b348a4441b89df7393c33ff) ([merge request](cosinf/suap!13907))
- [[ppc] Resolve erro ao rejeitar plano de disciplina](cosinf/suap@e2f847b1afccffcaa2959a6325a33313e14754cf) ([merge request](cosinf/suap!13906))

## 3.8.19 (2023-12-27)

### changed (5 changes)

- [[ppc] ajustes na edição e exclusão de plano de disciplina](cosinf/suap@26872ab8fe8087282c91db0fa73beb1846dfdbee) ([merge request](cosinf/suap!13902))
- [[saude] Exibir no prontuário os registros de vacinas de prontuários anteriores. resolves #10929](cosinf/suap@52f56cdd09c43b6e2877407807b57139163d1aa7) ([merge request](cosinf/suap!13901))
- [[pesquisa] Otimiza tela do projeto. resolves #10922](cosinf/suap@a0a33ec950916b585d803a96f13476beb1b5995a) ([merge request](cosinf/suap!13897))
- [[projetos] Vinculação dos projetos aos NEPP. Demanda 1729](cosinf/suap@3bc8701a232ec56fb4aaab5b7acfc69ffef4b25a) ([merge request](cosinf/suap!13895))
- [[ppc] Edição de modelo de conteúdo](cosinf/suap@6a8ce09bf38504dbaf213d0f1cc8b00928dba31a) ([merge request](cosinf/suap!13892))

### fixed (5 changes)

- [[plan_estrategico] Correção botão de realocação no plano original](cosinf/suap@51499cf587a1eb98e168c303e5aeac98db6e82a2) ([merge request](cosinf/suap!13900))
- [[edu] adiciona validações na importação de nota do moodle](cosinf/suap@c5f0d08dd9471926fe3a5f1d7f68ed34b844dd4c) ([merge request](cosinf/suap!13893))
- [[edu] Correção na funcionalidade de importação de alunos via CSV para o SUAP.](cosinf/suap@6ab7c2807099dd025f0568b1048bb5a9cd5e606a) ([merge request](cosinf/suap!13896))
- [[ppc] corrige erro ao acessar modelo de ppc que não existe](cosinf/suap@eca6dd08212195204197abe25d2769484ef9eea3) ([merge request](cosinf/suap!13899))
- [[plan_estrategico] Aumento de tamanho de caracteres do titulo da atividade.](cosinf/suap@3e393dcf9081e4011dcd0ae85d57e9c01a84f9a6) ([merge request](cosinf/suap!13898))

## 3.8.18 (2023-12-23)

### fixed (4 changes)

- [[comum] Erro ao tentar trocar de senha sem colocar o cpf ou passaporte](cosinf/suap@ec30edfff8ad78926c38f67894601ab2f6af456f) ([merge request](cosinf/suap!13890))
- [[comum] Corrigindo a exibição das salas disponíveis na tela de solicitações de reserva de sala.](cosinf/suap@4f2e8b8954464f381941b3f1d6827f56a02c3edc) ([merge request](cosinf/suap!13887))
- [[ae] Refatorando a tela de imprimir lista diária do módulo ae para ser processada no celery.](cosinf/suap@862d6a320069ab140abc220ca5e487e8aa500581) ([merge request](cosinf/suap!13884))
- [[comum] Adiciona verificação para quando o certificado cadastrado é inválido.](cosinf/suap@b39ea401f6954a7cc026603a4df76be438409cc5) ([merge request](cosinf/suap!13882))

### changed (4 changes)

- [[pesquisa] Novo fluxo de recursos e Ajustes diversos. Demandas 1723 e 1724](cosinf/suap@7cd6e3bd29bc6a6f1a01435ee5c87aae4b934bcc) ([merge request](cosinf/suap!13880))
- [[projetos] Adição em lote de alunos na equipe do projeto. Demanda 1691](cosinf/suap@c889d8f50f1b79d32b13c06084b99b29d8d3effb) ([merge request](cosinf/suap!13875))
- [[projetos] Torna configurável carga horária máxima dos servidores no projeto. resolves #10915](cosinf/suap@d1d363ed972a64e710507fcc56e866796ae57d32) ([merge request](cosinf/suap!13889))
- [[edu] Ajustes finais da implementação para possibilitar o lançamento da...](cosinf/suap@764bc29c736139ad083bf7e56f9abd5a226bb8e0) ([merge request](cosinf/suap!13885))

### removed (1 change)

- [[ppc] Impedido temporariamente o cadastro de Câmaras.](cosinf/suap@2b770ea1b23b44f771ef3a6727b9b4e056b8bc84) ([merge request](cosinf/suap!13886))

### added (1 change)

- [[ppc] habilita o revisor desfazer homologação de conteúdo do PPC](cosinf/suap@56f03030679ce57d53e0dcea1c6afda10a2702fa) ([merge request](cosinf/suap!13883))

## 3.8.17 (2023-12-20)

### fixed (10 changes)

- [[ae] Correção ao solicitar alteração dos dias de alimentação. resolves #10900](cosinf/suap@5e659bbae05e25be6e42de1d5ac159735598782f) ([merge request](cosinf/suap!13881))
- [[ae] Adicionando cache no processamento de folhas de pagamento](cosinf/suap@757efd200afcc2fea7050841c79c31989cc4e5d7) ([merge request](cosinf/suap!13876))
- [[projetos] Verifica se é email institucional ao cadastrar avaliador externo. resolves #10898](cosinf/suap@127c73be0c5f23a63105718dd4b163867de85f87) ([merge request](cosinf/suap!13879))
- [[ldap_backend] Corrige a sincronização de usuários sem setor](cosinf/suap@e6c424dea9827fd4e67989798ebb89c018bb666b) ([merge request](cosinf/suap!13878))
- [[edu] Corrige a exibição da previa de modelos de diplomas](cosinf/suap@c4d01599b5f10994b65323e164708984cbe439d2) ([merge request](cosinf/suap!13874))
- [[documento_eletronico] Corrigindo as permissões de reprocessamento de...](cosinf/suap@c4d06076fd54a04770a58aa7b9774a1c6ff02152) ([merge request](cosinf/suap!13872))
- [[comum] Corrigindo a exibição do logo de background da tela de login](cosinf/suap@cf97a28d84cebca47750685b0399981bd26dbebe) ([merge request](cosinf/suap!13871))
- [[estagios] Corrige a função de permissão de visualização de aprendizagem.](cosinf/suap@65856168f0de2c0082995eee912047d10f4e4b95) ([merge request](cosinf/suap!13867))
- [[documento_eletronico]  Adicionando botão de reprocessar interessados de documentos eletrônicos](cosinf/suap@b5c416804fa0c11e6d4e034c1ac7b83dce1d244a) ([merge request](cosinf/suap!13868))
- [[saude] corrige initial_data da saude](cosinf/suap@84a8ea01689a385271314105ff3e69b96ca28675) ([merge request](cosinf/suap!13865))

### changed (3 changes)

- [[edu] Possibilitando o lançamento da terceira nota em cursos anuais com três etapas](cosinf/suap@1901beca8f1830d20402964a521c4a3f03afca06) ([merge request](cosinf/suap!13877))
- [[ppc] Melhoria no fluxo de edição da periodicidade do plano de disciplina](cosinf/suap@e499f66b9abaa51b0436ad9a04c24fdc3a2fd568) ([merge request](cosinf/suap!13873))
- [[ppc] ajustes de usabilidade](cosinf/suap@533cbc04e5d90b223bf1b6284419be242c06b82c) ([merge request](cosinf/suap!13869))

### added (3 changes)

- [[ppc] melhoria na exibição de colunas da matriz no PPC e ajustes na aba...](cosinf/suap@e4a986a512b39992a4dc489a08cb772ece7a540e) ([merge request](cosinf/suap!13870))
- [[ppc] Adiciona cadastro de colaborador de PPC](cosinf/suap@18d9b0b386c290d9feb39fc7d6e3ec266bcb1960) ([merge request](cosinf/suap!13866))
- [[avaliacao_cursos] adiciona exportação XLS de respostas de avaliação de curso](cosinf/suap@934bb6981cfd1941154af910a9616f4f893b6c5e) ([merge request](cosinf/suap!13863))

## 3.8.16 (2023-12-17)

### added (1 change)

- [[ppc] adiciona fluxo de aprovação por conselhos e revisão de plano de disciplina com comentários](cosinf/suap@c728be5ea1fe6e1de88d11ffeffd2796a17c5cbd) ([merge request](cosinf/suap!13855))

### changed (2 changes)

- [[eventos] Incluir alerta na página interna de Eventos sobre carga horária dos certificados](cosinf/suap@01c1a58fc7f3603a3a15a5f85e0261c264f5f8d2) ([merge request](cosinf/suap!13840))
- [[edu] Possibilitando a criação de calendários acadêmicos anuais com três etapas.](cosinf/suap@175bbc62ddea2755fd308a406a1f165390142deb) ([merge request](cosinf/suap!13853))

### fixed (4 changes)

- [[rh] Adiciona a importação de servidor via WS pelo celery.](cosinf/suap@724735457eeb13bba25fd3f12021730df70bd46a) ([merge request](cosinf/suap!13854))
- [[processo_eletronico] Adicionando validação ao tentar deferir despacho de processo](cosinf/suap@bc426b3d46423071a6969205f8fc9ab97d26c4c3) ([merge request](cosinf/suap!13851))
- [[ppc] corrige erros no plano de disciplina](cosinf/suap@0ccb12e7ce1914628c5586da8f0209dcca00378b) ([merge request](cosinf/suap!13850))
- [[eventos] Corrigindo o clean de comparação de datas de atividades de eventos](cosinf/suap@774a2c5940ea4a7db3cde187510dc570f761dbf6) ([merge request](cosinf/suap!13848))

## 3.8.15 (2023-12-14)

### fixed (3 changes)

- [[central_servicos] Corrige as ações da base de conhecimento quando o admin é aberto num popup](cosinf/suap@a76343c164452df4675fb69252834fc62204fc75) ([merge request](cosinf/suap!13847))
- [[ldap_backend] Corrigindo a recuperação de senha](cosinf/suap@98e3f1a0d737eb3eb8343310b4c8125b03639f54) ([merge request](cosinf/suap!13846))
- [[djtools] Corrige a exportação de XLS quando um simplelistfilter é selecionado.](cosinf/suap@b8e62c4cc2c529dbc9f9c5557c5fc467c3c74105) ([merge request](cosinf/suap!13845))

### changed (2 changes)

- [[ppc] Melhorias e padronização do template padrão de geração de PDF.](cosinf/suap@c38e4fd0e82974ca0e21324dad6e74bf63a0e52a) ([merge request](cosinf/suap!13843))
- [[clipping] Converte a tarefa de importar noticias do clipping para o celery.](cosinf/suap@f0f65aded727d2c6e6ecc5e6412c506d0b819685) ([merge request](cosinf/suap!13844))

## 3.8.14 (2023-12-13)

### fixed (11 changes)

- [[rh] Corrige o save do servidor para alterar os vinculos das chaves corretamente.](cosinf/suap@3852e711adf25e94a8b2a2d55bf9186e14d13957) ([merge request](cosinf/suap!13841))
- [[pgd] Corrigindo cálculo de carga horária distribuida pelo semestre no RIT](cosinf/suap@e7a88b28bd26a9b90b6dceecaa4fd377060e96b5) ([merge request](cosinf/suap!13839))
- [[documento_eletronico] Adiciona um retorno padrão para a função pode_ser_excluido](cosinf/suap@10f421434a9bd39a48938aad634c6a61b1066d59) ([merge request](cosinf/suap!13838))
- [[edu] corrige exibição errada de mensagem no diário do professor](cosinf/suap@943ca0ad3e00b3b3f9deb89985ec4f921489fd16) ([merge request](cosinf/suap!13837))
- [[eventos] Corrigindo verificação se o participante de um evento é convidado.](cosinf/suap@b8dd5342bb8acd2ef00b902fec58bc62bfa1a3bd) ([merge request](cosinf/suap!13832))
- [[ppc] Corrigindo o search_fields do plano disciplina do PCC](cosinf/suap@74019edc699aa819a85e800f612d2f15cbf9b0a5) ([merge request](cosinf/suap!13831))
- [[ldap_backend] Substitui as referências a pessoa física na função ldap_actions...](cosinf/suap@b3bc2f3eab7a2798dee0741a2c7ba7e633377c4e) ([merge request](cosinf/suap!13830))
- [[almoxarifado] Adicionando validação no nome do material de consumo](cosinf/suap@66064e06736db1e236141a4d83cccbf310d50578) ([merge request](cosinf/suap!13829))
- [[edu] Correção de bug detectado pelo IFPR quando a opção de remanejamento de...](cosinf/suap@e36674a5b5596505f2fde730fb5fe13827ec34e6) ([merge request](cosinf/suap!13828))
- [[edu] corrige erro ao vincular coordenador de curso na diretoria acadêmica](cosinf/suap@f8626855d5da0eca74f10d16cf988a9e90bd98c6) ([merge request](cosinf/suap!13827))
- [[ppc] corrige erros de validação do plano de disciplina](cosinf/suap@a4843c6f3b47ef0fe26c88c8e8323a66a0081f72) ([merge request](cosinf/suap!13825))

### added (2 changes)

- [[ppc] Gerar PDF do plano de disciplina e altera search_fields](cosinf/suap@22768a5d6fcf089f95edc7705b05b0ab71ab7a82) ([merge request](cosinf/suap!13821))
- [[eventos] Demanda 1184 - Área pública](cosinf/suap@bd1a0a68c59908feca3d65c3444a03f2c631ed2b) ([merge request](cosinf/suap!13824))

### changed (1 change)

- [[pesquisa] Permite usuário externo gerenciar dados da Incubadora. Chamado 335826](cosinf/suap@233e171948c132fe68e5c887a05afcd42f78f513) ([merge request](cosinf/suap!13835))

## 3.8.13 (2023-12-09)

### added (2 changes)

- [[ppc] Adiciona atualização de portaria de elaboração e aba de documentos](cosinf/suap@a6919740f73fca7a5a29d4abb1e11fb950264c88) ([merge request](cosinf/suap!13819))
- [[edu] Importação do histórico do aluno no formato CSV via interface web.](cosinf/suap@baa6b5217d5ee0abda3e19359e3bf92b66595f82) ([merge request](cosinf/suap!13820))

### changed (2 changes)

- [[pesquisa] Cadastro de Termo de Compromisso em vários idiomas. Demanda 1587](cosinf/suap@870adc838b649b9d0502ded00f4fde628b9940b3) ([merge request](cosinf/suap!13816))
- [[projetos] Remove o botão 'visualizar gasto' da tela do projeto de extensão](cosinf/suap@1f8f810cc26d044c4cf00a5bd84611565ba80eb6) ([merge request](cosinf/suap!13814))
- [[processo_seletivo] Possibilidade de remanejar vaga para a lista geral / ampla...](cosinf/suap@60aea69fa4b0dd8989d55797cc0fa0ed0ccd2b9b) ([merge request](cosinf/suap!13815))

### fixed (3 changes)

- [[documento_eletronico] Corrige função pode_alterar_nivel_acesso do Documento Texto](cosinf/suap@9f305a682dbc170389a4c842a0091666ee8bae3a) ([merge request](cosinf/suap!13818))
- [[edu] corrige erro na geração de auditoria de alunos com dados da receita federal](cosinf/suap@4acf14bccce3f1e66135c35c94dfdaddd3ab5b55) ([merge request](cosinf/suap!13817))
- [[edu] corrige erro na verificação se aluno de curso FIC foi aprovado em todas as disciplinas](cosinf/suap@df0fc505d6c1548f525f00bb7aa9209a5abbee5c) ([merge request](cosinf/suap!13813))
## 3.8.12 (2023-12-05)

### added (1 change)

- [[ppc] [demanda 1615] Adiciona funcionalidades no PPC](cosinf/suap@795f6d0a18b6141c09e8d9a21546d844f79b174d) ([merge request](cosinf/suap!13812))

### changed (1 change)

- [[edu, estagio] - Utilizando a data de conclusão de estágio também para a...](cosinf/suap@3ec01e072f6f22478e58b119198c6f0dc44e2aa9) ([merge request](cosinf/suap!13786))

### fixed (5 changes)

- [[edu] corrige erro na geração automática de auditoria de ensino](cosinf/suap@742d344a5c0689b6b11d70f1ae19e11edd6b0289) ([merge request](cosinf/suap!13810))
- [[ppc] corrige erro no filtro do admin de Administrador de tipo de oferta](cosinf/suap@162e98ba53fe9bc620a0a1e18a86cd12eb5f8969) ([merge request](cosinf/suap!13811))
- [[comum] Correções para layout de formulários.](cosinf/suap@c857176ecde26a7b40110be0517ced263ac2f3e1) ([merge request](cosinf/suap!13809))
- [[documento_eletronico] Permite que solicitações de compartilhamento documento...](cosinf/suap@f1ed95dfc88ab2c98866db1216f70ebbc7c4f0f2) ([merge request](cosinf/suap!13801))
- [[api] Corrige bug ao enviar json inválido para obter um token jwt via api](cosinf/suap@2fbe4917dc771c543ae449932cd88feac9ede520) ([merge request](cosinf/suap!13808))

## 3.8.11 (2023-12-03)

### added (1 change)

- [[ppc] demanda 1615 - adição de funcionalidades](cosinf/suap@f4375329f7b366d3b45ead0a43f0483af8f0929d) ([merge request](cosinf/suap!13806))

### changed (1 change)

- [[edu, processo_seletivo] Consulta dos dados pessoais dos candidatos importados em arquivo CSV](cosinf/suap@8bd6ac53ba66c09fee4fa429b76d3678c388a635) ([merge request](cosinf/suap!13807))

## 3.8.10 (2023-12-03)

### changed (1 change)

- [[processo_seletivo] Desfazendo alteração realizada no MR anterior por...](cosinf/suap@e99a765ba9169bb58f92748767e426a112f9c2be) ([merge request](cosinf/suap!13805))

## 3.8.9 (2023-12-01)

### fixed (16 changes)

- [[comum] Salva responsável pelo cancelamento da solicitação de reserva de sala. resolves #10750](cosinf/suap@e0c065e4d24b0368ae8a7bde1657401437745570) ([merge request](cosinf/suap!13780))
- [[saude] Corrige erro de var too long ao unificar plano de tratamento. resolves #10669](cosinf/suap@4a786a583327a326e431c9d3cebb04c9bcc4c9f3) ([merge request](cosinf/suap!13775))
- [[processo_eletronico] Adiciona uma verificação de exceção ao tentar verificar...](cosinf/suap@3de630d6bfc663d47a3948581ecdde718d07f066) ([merge request](cosinf/suap!13803))
- [[labvirtual] Conserta urlname para a view de remover membro](cosinf/suap@1d2449c2190042364aed305c0ccee9d2b2205dd2) ([merge request](cosinf/suap!13802))
- [[plan_estrategico] Corrige os searchfields do plano interno](cosinf/suap@569decf6370b54c6a0e3321c5784f1b5580dd8f0) ([merge request](cosinf/suap!13800))
- [[processo_eletronico] Corrige a verificação se o processo possui ultimo...](cosinf/suap@2615bf16f01362a859d4a26981edefea88db5bcc) ([merge request](cosinf/suap!13799))
- [[patrimonio] Adicionando tamanho máximo para observação de baixa de patrimonio](cosinf/suap@7b143f0f3c2cdcba4d3faaf8b9b683c23700332a) ([merge request](cosinf/suap!13798))
- [[eventos] Corrige a exibição do calendário de eventos quando o usuário não...](cosinf/suap@4f4f2686702ee5f88856e108bd53ffd88af5be91) ([merge request](cosinf/suap!13797))
- [[centralservicos, processo_eletronico] Corrige a geração de processos a partir...](cosinf/suap@2d80dd5b04010cf67b91ce71cd4ef840b8f7800b) ([merge request](cosinf/suap!13794))
- [[edu] Separa o processamento das variaveis do cenário de ofertas](cosinf/suap@262a2b431edc2b86d4a0a47e94f0d63e1cbe6b6c) ([merge request](cosinf/suap!13792))
- [[plan_estrategico] O campo vinculo_permitido pode apontar para um vínculo sem user](cosinf/suap@7f751ad72b64846e542114f8b75a780df4fc8cc7) ([merge request](cosinf/suap!13789))
- [[chaves] Corrige a geração do zip do terminal de chaves quando nenhum prédio é...](cosinf/suap@e92ac0232975345024e5b69075d5f64af26c6498) ([merge request](cosinf/suap!13787))
- [[ppc] retira captura de exceção no sentry da sincronização automatica](cosinf/suap@52bb253387eedf61691575a824c04ec6c5d30144) ([merge request](cosinf/suap!13783))
- [[djtools] Corrige o comando bin/ci/daemon.py para encontrar todos os membros do grupo cosinf-devops](cosinf/suap@540da9ca33f8072f9de39b9bc7f76fe0492c1460) ([merge request](cosinf/suap!13784))
- [[edu] corrige erro na verificação se diploma pode ser emitido para aluno](cosinf/suap@d99379fdc2dd6ba5b200906ea64ef5994c0b90bc) ([merge request](cosinf/suap!13782))
- [[estagios] Corrige validação do cadastro de estágio](cosinf/suap@24b60f76c4d6bf3f1a9897fbeecc41dc815fd830) ([merge request](cosinf/suap!13781))

### added (4 changes)

- [[comum] Integração com APIs de Consulta a informações básicas do CadUnico e PcD](cosinf/suap@c8f72416ff68cfd082e9ab250e15c32be973ff3c) ([merge request](cosinf/suap!13793))
- [[ae] Relatório de Alunos atendidos em Programas de Auxílios Emergenciais. Demanda 1106](cosinf/suap@d7505dca46e8995514bb38759433b85d21c63ca3) ([merge request](cosinf/suap!13795))
- [[contratos] Demanda 1563: Melhoria gestão de mão de obra contratos](cosinf/suap@e993fbc61d003895638afd4e3d4e3236b75316d6) ([merge request](cosinf/suap!13788))
- [[edu, processo_seletivo] Adiciona importação de Aluno e Editais utilizando arquivos CSV e XML](cosinf/suap@90c5bc4293fe241ac5414a1413685d3e4c7ab22f) ([merge request](cosinf/suap!13778))

### changed (2 changes)

- [[saude] Ajusta permissões do initial_data da saúde. resolves #10808](cosinf/suap@5697d80fc99364ae725e2d65880a546ecc5221bd) ([merge request](cosinf/suap!13791))
- [[edu] Melhorias na tela de listagem de alunos](cosinf/suap@dd99c6ee37fbbc384427d6cf5994598fce3a4f27) ([merge request](cosinf/suap!13785))

## 3.8.8 (2023-11-29)

### fixed (4 changes)

- [[ppc] corrige erro de envio repetido de notificação de finalização de portaria...](cosinf/suap@1ec00c0091c1713586c2c16f190a71eaebf655db) ([merge request](cosinf/suap!13779))
- [[processo_eletronico] atualizando pacote do pypdf para a versão mais recente e...](cosinf/suap@7aab30c26b088fc551fd62a0a61b13330fe2bd4e) ([merge request](cosinf/suap!13773))
- [[lic_capacitacao] Forçando a quebra de palavras grandes na lista de ações da licença capacitação](cosinf/suap@b1c3e47dd111248c0f6a86b6febafa13b81247dd) ([merge request](cosinf/suap!13776))
- [[lic_capacitacao] Forçando a quebra de palavras grandes na lista de ações](cosinf/suap@0ee64b535525ef02a3c2b5c75774e7fc10f4d7d5) ([merge request](cosinf/suap!13774))

### changed (1 change)

- [[ae] Ajusta mensagem de erro ao solicitar refeição. resolves #10788](cosinf/suap@c60c66a0811d3ba36fea5681eede676c2d5d4d30) ([merge request](cosinf/suap!13777))

### added (1 change)

- [[plan_estrategico] Movimentação de Crédito e Requisição de Dotação provisória](cosinf/suap@8eeb9d3104715fc57d3a535bb990a7a15e5e0d67) ([merge request](cosinf/suap!13772))

## 3.8.7 (2023-11-28)

### fixed (2 changes)

- [[documento_eletronico] Correção em registro de erro ao tentar excluir um documento com associação](cosinf/suap@f42979d0837172e25c696c25a766176abf4d26d6) ([merge request](cosinf/suap!13771))
- [[ppc] corrige erro quando documento eletrônico vinculado à solicitação de ppc é excluído](cosinf/suap@f8da9273198d2b015fee771b8f4bbe9a260f3ee7) ([merge request](cosinf/suap!13770))

### changed (1 change)

- [[pesquisa] Importa tabela de despachos do INPI. resolves #10760](cosinf/suap@63cb2ab66e01d9bcca8ad386e673018b654c19be) ([merge request](cosinf/suap!13768))
- [[tesouro_gerencial] Configurar importação do tesouro para executar de hora em hora](cosinf/suap@a01487607ae66c1de7bb3aea62ad8597ffdc4b4c) ([merge request](cosinf/suap!13769))

## 3.8.6 (2023-11-27)

### fixed (5 changes)

- [[ppc] corrige erro na verificação de permissão para emissão de portaria na solicitação de PPC.](cosinf/suap@447b1e42e55991f7ed0953432c587173c517b685) ([merge request](cosinf/suap!13767))
- [[documento_eletronico] Removendo um self extra na mensagem de erro durante a...](cosinf/suap@10dc2da16bd54fa2c1e767a9d8896412ee4fa79d) ([merge request](cosinf/suap!13766))
- [[patrimonio] O modelo CategoriaMaterialPermanente pode ter o campo plano_contas](cosinf/suap@b6ecf4292f3901f88b0e8a694150d76f31f8b6cf) ([merge request](cosinf/suap!13763))
- [[plan_estrategico] Admin pode ver todas as atividades](cosinf/suap@2c4d0332b2d303cd84cc08a391e22494910a0568) ([merge request](cosinf/suap!13764))
- [[edu] atualizando campos para vinculo do diretor geral no histórico do aluno](cosinf/suap@1845ef4dfe3377ed8c4e7b67b5a0a6bc86c93c46) ([merge request](cosinf/suap!13762))

### added (1 change)

- [[documento_eletronico] Adiciona testes do documento eletrônico](cosinf/suap@590b0e991a5fbc922015b7934c3b18c7b8b0d91f) ([merge request](cosinf/suap!13765))

## 3.8.5 (2023-11-24)

### fixed (6 changes)

- [[documento_eletronico] Alteração em alerta de documentos não finalizados do usuário](cosinf/suap@9bcaf276636279617f09d8dccba52d026b14406c) ([merge request](cosinf/suap!13755))
- [[plan_estrategico] Plano interno e origem de recurso obrigatório no cadastro de atividade](cosinf/suap@995a6f0f49fcc35ef1526e043c6e837722cc4fa0) ([merge request](cosinf/suap!13757))
- [[edu] Impede nova emissão de registro de diploma](cosinf/suap@c2a315a919631839f6e339688b656e577200ae53) ([merge request](cosinf/suap!13760))
- [[projetos] Corrige geração de bolsa no AE. Resolves #10755](cosinf/suap@144c89d8a5decfd586b80d21540922007bc5a566) ([merge request](cosinf/suap!13758))
- [[comum] Correções de formulários relativos à atualização da versão do Django](cosinf/suap@0462796c6a119a775804ef95f1c2308bfe5f212b) ([merge request](cosinf/suap!13756))
- [[pesquisa] Corrige link para arquivo de diagramação da obra. Resolves #10749](cosinf/suap@417656309812bacb2cb32c8c39dae90a612c89db) ([merge request](cosinf/suap!13752))

### added (1 change)

- [[ppc] Demanda 1615 - adiciona representação no cadastro de indicação da comissão de elaboração](cosinf/suap@ac0f02762b9e38b0f0f666707596e054e012dc4d) ([merge request](cosinf/suap!13759))

### changed (1 change)

- [[djtools] Substituindo referências de SpanField para ReadOnlyField](cosinf/suap@512b91202673005f1afc4d02be0fe06894ab0e45) ([merge request](cosinf/suap!13753))

## 3.8.4 (2023-11-23)

### fixed (3 changes)

- [[edu] corrige erro na verificação de validade de certificado digital ICP EDU](cosinf/suap@50369312fdd4ce729d845365747c27c0c0f9fd64) ([merge request](cosinf/suap!13751))
- [Resolve: o inserir uma matrícula no documento entre parênteses não está sendo...](cosinf/suap@52d292168b4c484bc6ba798a52eecb23259c1ee2) ([merge request](cosinf/suap!13750))
- [[ae] Corrige definição de data de término de ParticipacaoBolsa. Resolves #10705](cosinf/suap@12cd6dd6f1ca571429e339d6cc4c9b62f83f103c) ([merge request](cosinf/suap!13747))

### changed (1 change)

- [[ppc] demanda1615 - adiciona formatação na cópia de dados da comissão para documento portaria](cosinf/suap@bd10231deb7233f8d5a032d739afce574c0ad863) ([merge request](cosinf/suap!13749))

### added (2 changes)

- [[rh] melhorias no cadastro de funções](cosinf/suap@0de00c5336f172c761972e5ed91071b4b083e74a) ([merge request](cosinf/suap!13672))
- [[ppc] demanda 1615 - adição de notificações e alertas](cosinf/suap@0a7883ffb03e30aa276b4a1461e9774a2ea2f4aa) ([merge request](cosinf/suap!13748))

## 3.8.3 (2023-11-22)

### fixed (4 changes)

- [[estagios] Corrige os fieldsets dos formulários do admin do django](cosinf/suap@8a40260660e7d2c32794286ecb01630d71bc0ff0) ([merge request](cosinf/suap!13744))
- [[estagios] Corrige resolução de permissões relativas a operações com Visitas de Orientador](cosinf/suap@330a660c0201adab03dd446fbe54f0b3efaeff8f) ([merge request](cosinf/suap!13746))
- [[plan_estrategico] Aprimorar o cadastro de atividades, limitando-o a origem de...](cosinf/suap@3959de4c07230267c50191796cad2c4782e67559) ([merge request](cosinf/suap!13745))
- [[processo_seletivo] Corrige a geração de xls da inscrição de fiscais em processos seletivos.](cosinf/suap@845266d67824335519a1c9ed4121dae8c8f173c4) ([merge request](cosinf/suap!13743))

## 3.8.2 (2023-11-20)

### fixed (4 changes)

- [[processo_eletronico] revertendo versão do pypdf2](cosinf/suap@a20911173f4e09046d7a49274ec82b5aebac715a) ([merge request](cosinf/suap!13742))
- [[comum] Corrige o dump e data de expiração de certificados digitais](cosinf/suap@324977575dd744edcbe630250b76cc01727b17fc) ([merge request](cosinf/suap!13740))
- [[comum] Corrige a exibição do CPF para prestadores sem número de CPF](cosinf/suap@7103e2aefb49b443822e2478fd7d3fc6ea21a683) ([merge request](cosinf/suap!13738))
- [[rh] Adiciona verificação do atributo ação no método POST ao tentar salvar processo de afastamento.](cosinf/suap@67b86f1c823e70162c75917faba8e2ca7367d2ca) ([merge request](cosinf/suap!13739))

## 3.8.1 (2023-11-19)

### fixed (4 changes)

- [[djtools] Corrige os testes para funcionarem com o novo navegador do chrome](cosinf/suap@3318fccd2d5d263dcdc19361637258088140ec2d) ([merge request](cosinf/suap!13737))
- [[comum] Corrige a instalação do chrome no gitlab-ci](cosinf/suap@ba1afbb73ee1690e46a2f82dacb2827a82303d69) ([merge request](cosinf/suap!13736))
- [[djtools, documento_eletronico] Corrigindo queryset de assinatura de documento texto](cosinf/suap@e09fe8669f0eee931802b3ddf2d99105fbff4f6f) ([merge request](cosinf/suap!13735))
- [[edu, saude, estagios] substituindo referencias erradas para funcionarios](cosinf/suap@7176101226d6b63dc1e56bf4ce1833b70a925064) ([merge request](cosinf/suap!13734))

## 3.8.0 (2023-11-19)

### changed (1 change)

- [[edu, rh] Migra os relacionamentos de Funcionario para Vinculo](cosinf/suap@08638a8e2187c18ed4b164483da2094c5bad9d57) ([merge request](cosinf/suap!13717))

### security (1 change)

- [[djtools] Django 4.2](cosinf/suap@2c320cf6b061e90e0abb9086e3c4c3024c9ceaa5) ([merge request](cosinf/suap!13731))

## 3.7.4 (2023-11-17)

### added (1 change)

- [[centralservicos] Adiciona funcionalidade de criar processo a partir de chamado](cosinf/suap@5b5a29fee49e8563983b9f7a165e115badd4945c) ([merge request](cosinf/suap!13450))

### changed (1 change)

- [[contratos] Demanda 1655: Pequenos ajustes no módulo de Contratos](cosinf/suap@0791ee8c6b873a8f8e19e340894b6267a32dbe60) ([merge request](cosinf/suap!13715))

## 3.7.3 (2023-11-16)

### fixed (1 change)

- [[ae] Considerar as datas liberadas recorrentes ao solicitar refeição. resolves #10700](cosinf/suap@279a2710172f8e59a618f13cdaed8891481dca4d) ([merge request](cosinf/suap!13729))

### added (1 change)

- [[ppc] adiciona periodicidade no plano de disciplina](cosinf/suap@e2a51dbc131f2450b342d1bf4eb2c16d19f88091) ([merge request](cosinf/suap!13728))

## 3.7.2 (2023-11-14)

### added (1 change)

- [[ppc] demanda1615 - melhorias](cosinf/suap@0ad4366051567c1fb87e7e35fbd26d29a0e70eb6) ([merge request](cosinf/suap!13726))

### changed (1 change)

- [[ae] Impedir solicitação de refeição se o dia atual é uma Data Liberada. resolves #10691](cosinf/suap@fbbcd6e10590c5557ab9a4ae952fc5b575bd63fc) ([merge request](cosinf/suap!13727))

### fixed (2 changes)

- [[portaria] correção de bug que impedia editar um usuário externo](cosinf/suap@3ddc786e827b000d445831669cfcf5c18f10a0a8) ([merge request](cosinf/suap!13720))
- [[comum] Correções do layout de formulários em diversas telas.](cosinf/suap@5532803518b150d1f430265a572e357c7853145d) ([merge request](cosinf/suap!13723))

## 3.7.1 (2023-11-14)

### added (1 change)

- [[pesquisa] Comando para importar os despachos das patentes da RPI. Demanda 1503](cosinf/suap@452016c872ca70bee3d462322881a06c98210f26) ([merge request](cosinf/suap!13721))

### changed (1 change)

- [[tesouro_gerencial] melhoria nos admins](cosinf/suap@2d8b13d5cd3c70f5dc882a1fad145850b5a890f8) ([merge request](cosinf/suap!13718))

### fixed (3 changes)

- [[plan_estrategico] adicionando login required para algumas views](cosinf/suap@93232bf90742457e8a592ac51f486119542819df) ([merge request](cosinf/suap!13716))
- [[eventos] Correção do comportamento no filtro de calendário dos eventos](cosinf/suap@2ffabad451679c3389d2707e3caa8f99a8fa67e1) ([merge request](cosinf/suap!13714))
- [[comum] Corrige o comando de remoção automática de permissões de usuários](cosinf/suap@ad7e2425813de853320f17b6dfb90dce4baa63ea) ([merge request](cosinf/suap!13712))

## 3.7.0 (2023-11-12)

### added (1 change)

- [[ppc] demanda 1615 - adição de funcionalidades e validações](cosinf/suap@f516c2bfccc1e27f2195b22a850bf73a2426a202) ([merge request](cosinf/suap!13710))

### fixed (1 change)

- [[chaves, pesquisa, plan_estrategico, contratos, rh] Atualiza referências de...](cosinf/suap@42be54cab09eb97d3d4c1e20647191cec62cdc29) ([merge request](cosinf/suap!13695))

## 3.6.26 (2023-11-12)

### fixed (3 changes)

- [[plan_estrategico] Permitir ajuste de objetivo estratégico quando o...](cosinf/suap@745e3a5896ee242df4a2ab9a96d1cfd272f28711) ([merge request](cosinf/suap!13709))
- [[edu] corrige erro na verificação de pendencias do aluno no fechamento de período](cosinf/suap@8fa5dc3dee2c3bbc38b810da72dc70ffc32ef191) ([merge request](cosinf/suap!13707))
- [[ae] Corrige erro ao solicitar almoço na quinta-feira. Resolves #10674](cosinf/suap@d0d53731a5d4f1db380f963375b727bc0f31b357) ([merge request](cosinf/suap!13706))

### changed (2 changes)

- [[edu] Implementação da demanda 1634 referente a permissão de gerenciamento dos...](cosinf/suap@42a24492a57a284bc649cd8bf016bb23069170bf) ([merge request](cosinf/suap!13708))
- [[projetos] Acesso ao botão 'visualizar comprovante' na aba de Desembolso. Demanda 1604](cosinf/suap@98ef8d182635252600a8c68d2753e238fefcc5e0) ([merge request](cosinf/suap!13705))

## 3.6.25 (2023-11-09)

### fixed (2 changes)

- [[edu] Corrige a geração de registros de impressão de diplomas](cosinf/suap@369a499283f5e659016715e6182674f5fe24597f) ([merge request](cosinf/suap!13704))
- [[comum] correção no bug de visualização de solicitação de reserva de sala de evento único](cosinf/suap@dfdb26feaa3eb218e3efd2bc600e381650dd447c) ([merge request](cosinf/suap!13703))

## 3.6.24 (2023-11-09)

### fixed (7 changes)

- [[eventos]  Variável configuracoes_minimas não está sendo carregada na tela de participantes](cosinf/suap@1d881a74b8840a1c1ade5a959481ba4ce4d45291) ([merge request](cosinf/suap!13702))
- [[auth_backends] Adiciona tratamento para obter o nível de confiabilidade caso...](cosinf/suap@dbb6df5fed80186dee0be895e5bd1bf2f87db338) ([merge request](cosinf/suap!13701))
- [[materiais] Corrige geração do XLS de materiais. resolves #10646](cosinf/suap@4ae2912fa03a4b4d9ac36d7c2d4b5048560ad1b2) ([merge request](cosinf/suap!13698))
- [[eventos] Adiciona validações no método clean ao tentar realizar login de avaliador.](cosinf/suap@a6524be6710e43262fcc857f7ba40d43fefef434) ([merge request](cosinf/suap!13700))
- [[eventos] Corrige a edição de eventos por usuários que não possuem nenhum setor associado](cosinf/suap@f7693f451f15805496eff86fa7303902a2af9661) ([merge request](cosinf/suap!13699))
- [[edu] Correção de bug na emissão de diploma de alunos com prática...](cosinf/suap@8a42597a720ebc2921baac5cbe2ac3e86e559a1a) ([merge request](cosinf/suap!13696))
- [[edu] Erro na referência da empresa de uma pratica profissional na hora de...](cosinf/suap@faa4105f7390791b47342d991571474f7a5044d8) ([merge request](cosinf/suap!13692))

### changed (4 changes)

- [[projetos] Adiciona coluna do CNPJ no XLS de visitas técnicas. resolves #10656 #10657](cosinf/suap@b1b80b3e36adb83d3a0907ce814a4a01edb05cff) ([merge request](cosinf/suap!13697))
- [[edu] Demanda 1071 - definição do público alvo da renovação](cosinf/suap@642100fe9d3895c67a8c25258118bd82abbc1ff1) ([merge request](cosinf/suap!13690))
- [[eventos] Alterando forma como a permissão é verificada na view informar_atividades()](cosinf/suap@4acce2f3836df80fa867bd3d238864cd2cc27c2b) ([merge request](cosinf/suap!13694))
- [[conectagov_pen] - Atualização da API do barramento (TramitaGov) para a versão 3](cosinf/suap@f0ed413e6a01455b29dd9326b2334de856e7c319) ([merge request](cosinf/suap!13693))

## 3.6.23 (2023-11-06)

### added (1 change)

- [[edu] versão inicial do e-PPC](cosinf/suap@a3c4d057b33faf764e974c9afbe6cf128a4fa810) ([merge request](cosinf/suap!13691))

### fixed (2 changes)

- [[estagios] Corrige a exportação para XLS das aprendizagens. resolves #10617](cosinf/suap@5eff4efca844d50b39b8a644a13352ff1f43b48e) ([merge request](cosinf/suap!13688))
- [[processo_eletronico] Erro ao Realizar "solicitação de documento" no SUAP,...](cosinf/suap@3dfad177b9576b4ff5b6db8c21e19bcf9efa5f17) ([merge request](cosinf/suap!13687))

## 3.6.22 (2023-11-01)

### changed (2 changes)

- [[eventos] Ajuste tamanho da etiqueta](cosinf/suap@7b126564ebb92b8786394de9f1eb117d4b64a47f) ([merge request](cosinf/suap!13686))
- [[ae] Verifica se a data agendada para desbloqueio da participação é posterior...](cosinf/suap@24777f95b6c23b8ae186bd00239d87f0caa1eb04) ([merge request](cosinf/suap!13685))

### fixed (3 changes)

- [[edu] Envio do trace de erro para o Sentry quando ocorre uma exceção na emissão de diploma.](cosinf/suap@8a5cd5c2d7d6ccbaa2812fd8dbdb6079dc631a41) ([merge request](cosinf/suap!13683))
- [[eventos] Removendo validação do passaporte](cosinf/suap@7413030e882a1774b32c8034917c5eed3baa6826) ([merge request](cosinf/suap!13684))
- [[calculos_pagamentos] corrige bug quando módulo não está configurado](cosinf/suap@42abebbcb3a1fdf007348d03f13c1d1bee9c241f) ([merge request](cosinf/suap!13678))

## 3.6.21 (2023-10-31)

### changed (2 changes)

- [Melhorias de usabilidade para telas públicas de Eventos.](cosinf/suap@419030298a4ddd2b849d6e06d0d9813a7714c04d) ([merge request](cosinf/suap!13675))
- [[plan_estrategico] Excluir plano interno quando não está vinculado ao Plano de atividade](cosinf/suap@b4d36c276c6407416e23d6a80d894f4262a4683b) ([merge request](cosinf/suap!13676))

### fixed (8 changes)

- [[ae] Melhorias de performance ao baixar as solicitações de refeição](cosinf/suap@8f08b9c45fc1e6f26a0e97be1ecdcc164ccf8f3c) ([merge request](cosinf/suap!13682))
- [[edu] Correção de bug que impede validação de documento emitido mais de uma...](cosinf/suap@8c0a30416f37972e68f6e186af2f5e8a6e283acf) ([merge request](cosinf/suap!13681))
- [[edu] Correção de bug que exibia o alerta de nada consta pendentes para usuários externos.](cosinf/suap@5458363c6c117f406f7e5e9ac4aac4c03574da2f) ([merge request](cosinf/suap!13677))
- [[edu] Correção de bug que impede que Administradores alterem/excluam situação...](cosinf/suap@b1dad38fa2480a4956302fdaec7c40062ce6a518) ([merge request](cosinf/suap!13679))
- [[eventos] confirmação do evento quando cadastra participante e confirmação...](cosinf/suap@d87aaec48fec16ab0a9c38b81e60173918658d1c) ([merge request](cosinf/suap!13670))
- [[djtools] força salvar a task antes de mandar executar no celery](cosinf/suap@36247e460d72b9b21d26be8f66e56eaa7facf257) ([merge request](cosinf/suap!13680))
- [[suap] thema aurora messages de erro](cosinf/suap@02bf62fe31bebc958d6c43664ff9537298d19448) ([merge request](cosinf/suap!13671))
- [[plan_estrategico] Corrige da busca de Ação orçamentária no cadastro de plano interno](cosinf/suap@0e613744ca45d201b076b31d9a9279bf6345f893) ([merge request](cosinf/suap!13674))

### added (1 change)

- [[plan_estrategico] Permissão para o Administrador do Planejamento Estratégico...](cosinf/suap@4aa97ddfb015975f2801931c447673955220c1d9) ([merge request](cosinf/suap!13673))

## 3.6.20 (2023-10-29)

### fixed (1 change)

- [[estagios] Remove referencias de modelos para Pessoa Física](cosinf/suap@76f1b156fe1a58db1f4a8de8637685ae8ffc3430) ([merge request](cosinf/suap!13667))

## 3.6.19 (2023-10-29)

### added (1 change)

- [[edu] adicionando avaliação por conceito](cosinf/suap@ebd6b90a1ee19dc9b82221475f258a1393f6f2a2) ([merge request](cosinf/suap!13666))

### fixed (1 change)

- [[saude] Corrige bug que impede usuário de ver seus agendamentos de atendimento para outros campi](cosinf/suap@b0b6573df2a9361bb3827689aafe73ad08035d45) ([merge request](cosinf/suap!13665))

## 3.6.18 (2023-10-28)

### added (2 changes)

- [[edu] Implantação da versão inicial do módulo de oferta](cosinf/suap@b7f777df00387d1f80d2d62456e4982358d0c5a6) ([merge request](cosinf/suap!13571))
- [[eventos] Demanda 1663: Ajustes para fluxo de submissões e inscrições em Eventos](cosinf/suap@5c151de5528cf0241ae4d47a150149b100aa02be) ([merge request](cosinf/suap!13618))

### fixed (3 changes)

- [Closes #10557](cosinf/suap@6aa5466f404b70e91ae1d77a5c99390cc5fb1fbd) ([merge request](cosinf/suap!13663))
- [[ae] Desfazendo mudanças na tela de baixar configurações do refeitorio](cosinf/suap@3447799a95287ecb4d69d380ec3b9c3aceab6b28) ([merge request](cosinf/suap!13662))
- [[eventos] Resolvendo erro reportado que oculta filtros ao não encontrar resultados da pesquisa](cosinf/suap@d5dfb19a23119d23b065572b914c4afad0a52729) ([merge request](cosinf/suap!13660))

### changed (2 changes)

- [[comum] Remoção de Herança de Pessoa Física em Dependente, Pensionista e Responsável Legal](cosinf/suap@24227faee0aacff0f305b40b7bbfbd2498916f03) ([merge request](cosinf/suap!13442))
- [[ae] Gerenciamento da oferta de auxílios eventuais. Demanda 1651](cosinf/suap@e94a928563f1c6a409dea5496430e7701c70593a) ([merge request](cosinf/suap!13402))

## 3.6.17 (2023-10-27)

### fixed (4 changes)

- [[edu] Correção de bug que está impedindo o envio do diploma digital de alunos do Q-Acadêmico](cosinf/suap@2765bd81a3514b6afeb200727d0e0debf639aa65) ([merge request](cosinf/suap!13658))
- [[eleicao] Melhoria de performance na tela de exibição de público](cosinf/suap@78ee6d1c53480214115f6b4daf07c755a8837980) ([merge request](cosinf/suap!13655))
- [[djtools] Movendo views do djtools para o arquivo views.py](cosinf/suap@4b02d897798cc600d3bd49878a1e2c2fe7159875) ([merge request](cosinf/suap!13654))
- [[comum] Correção de posicionamentos de elementos de formulários.](cosinf/suap@98978223cde0788849b3deb03b8fc00b6d3951cd) ([merge request](cosinf/suap!13652))

### changed (3 changes)

- [[djtools] Aumento de Max_results em RenderableSelectMultiple](cosinf/suap@f108adc111c0942c822eede37733a10d1c494375) ([merge request](cosinf/suap!13657))
- [[remanejamento] Alteração da nomenclatura “Remanejamento” para "Remoção...](cosinf/suap@b5c8a46a3f5f680f93b15aa29ab1845dd02bdd7e) ([merge request](cosinf/suap!13653))
- [[enquetes] Melhorias na tela de visualização de publico de enquetes](cosinf/suap@118a5f5165f05be1696349592c2c2fed88cb7c9b) ([merge request](cosinf/suap!13656))

## 3.6.16 (2023-10-26)

### fixed (1 change)

- [[eventos] Corrigindo bug que estava atualizando os inscritos nos eventos](cosinf/suap@5bb6807360e4ae09531d69e5b4b2f265ecd5f8fe) ([merge request](cosinf/suap!13651))

## 3.6.15 (2023-10-26)

### fixed (9 changes)

- [[documento_eletronico] Corrigindo as referencias do solicitante nas...](cosinf/suap@a145061de5b0613783fadc717db1a62f4fa58b77) ([merge request](cosinf/suap!13650))
- [[processo_eletronico] Desabilitando a remoção de assinaturas durante o merge de pdfs](cosinf/suap@fb2b74246904baca1f4d5b8a60e9871f3f18adbd) ([merge request](cosinf/suap!13649))
- [[edu] Correção de bug que impede a clonagem de alunos para realização de transferência interna](cosinf/suap@54b499a2f98e3b4e9dc6ede2f295a045cbfc0447) ([merge request](cosinf/suap!13648))
- [[processo_eletronico] Corrige a verificação de possuir solicitacoes pendentes...](cosinf/suap@3202b7e07f1aea541c34fa9dfbff2150dc5151b7) ([merge request](cosinf/suap!13646))
- [[ae] Filtra os agendamentos de refeição para os terminais baixarem apenas os...](cosinf/suap@b690538b118e20d3ee4a6fc7c56751bf1a329de6) ([merge request](cosinf/suap!13644))
- [[comum] Corrige o método get_vinculo do user quando não existe nenhum vinculo associado.](cosinf/suap@bdefee8ee3daee1368692b5f7afed84f0e356440) ([merge request](cosinf/suap!13641))
- [[processo_eletronico] Corrige o campo de senha dos formulários de autenticação...](cosinf/suap@49cf54f358bdc136d925b59a03098cb3b6250183) ([merge request](cosinf/suap!13643))
- [[comum] Corrige o admin do user após o vínculo virar onetoonefield.](cosinf/suap@84ebad48221f47b143334cb13a1159a94508783e) ([merge request](cosinf/suap!13642))
- [[processo eletrônico] Correção de bugs detectados pelo CFMV quando a opção de...](cosinf/suap@b572e445e0d1ac2249c0ad53487f839156d6c1db) ([merge request](cosinf/suap!13638))

### added (3 changes)

- [[processo_eletronico] Adicionando possibilidade de escolha de nivel de acesso...](cosinf/suap@15b3e36517bc853b5a4ce9507b15a9c7999ab4be) ([merge request](cosinf/suap!13647))
- [[edu] Adição no campo "percentual_afatamento" no modelo utilizado para...](cosinf/suap@e2b1348c09d88e35bda200ad8a782764e55b3356) ([merge request](cosinf/suap!13645))
- [[eventos] Demanda 1686: Relatório de avaliadores sem avaliações](cosinf/suap@cb759adf44b6f6b931b2fcde8500956806864b2a) ([merge request](cosinf/suap!13639))

## 3.6.14 (2023-10-24)

### added (1 change)

- [[calculos_pagamentos] - Demanda 727 - Calculos e pagamentos](cosinf/suap@a0183d27891b32889036c3fb42944236b7c831a2) ([merge request](cosinf/suap!13637))

### fixed (8 changes)

- [[comum] Tornando o user do vinculo único](cosinf/suap@d6a4489afd737c3cfc50bd4c7b85db3d30d47d34) ([merge request](cosinf/suap!13629))
- [[pesquisa, djtools] Adiciona autocomplete no autocadastro de parecerista de...](cosinf/suap@0e0986cdaaf5070573c846d82c951393f342846c) ([merge request](cosinf/suap!13635))
- [[pgd] Corrige a filtragem das temáticas para buscar os administradores pelo...](cosinf/suap@2b157e2d13193747ea7104dc1ef20be500886538) ([merge request](cosinf/suap!13634))
- [[almoxarifado] Correção da posição do componente BRDateRangeWidget.](cosinf/suap@0e6b7e044b9e0794d5d3a07c1cbe785dfd59d848) ([merge request](cosinf/suap!13631))
- [[documento_eletronico] Corrige a filtragem de documentos por tipos quando o tipo é inválido](cosinf/suap@215a073ad7fa936d9247bf4a05898ab192db37b8) ([merge request](cosinf/suap!13633))
- [[processo_eletronico] Remove o null=True do...](cosinf/suap@86d2d25411fee44e47efa7457db459524368d664) ([merge request](cosinf/suap!13632))
- [[avaliacao_integrada] Remove as respostas com valor negativo dos dados brutos no calculo da moda](cosinf/suap@161d1a9f593f20616717c1a9d815eae0a6b9aa4f) ([merge request](cosinf/suap!13630))
- [[comum] Adicionando comando que revincula usuários](cosinf/suap@bf0b0befaf6d2cbc586d17b8736ad45ccd44f1ac) ([merge request](cosinf/suap!13625))

### changed (1 change)

- [[ponto] ajuste em compensação de horários de docentes](cosinf/suap@1db7d38ede72fc207e640c86a33d07615fb212df) ([merge request](cosinf/suap!13628))

## 3.6.13 (2023-10-23)

### changed (3 changes)

- [[progressoes] Ajustes nas permissões de acesso ao relatório de servidores a progredir.](cosinf/suap@1d9f9467b13ae3c67b0c047d6fd9a99885a76de9) ([merge request](cosinf/suap!13626))
- [[eventos]  Demanda 1663: Ajustes para fluxo de submissões e inscrições em Eventos](cosinf/suap@607a7b9ea622bfc1dd840097c642af9f58510c0b) ([merge request](cosinf/suap!13627))
- [[avaliacao_integrada] Melhorias para o questionário de avaliação integrada](cosinf/suap@31e85134c3ffb19114cdd54b6c78d5145ce94a9e) ([merge request](cosinf/suap!13569))

### added (1 change)

- [[pesquisa]  Cadastro de Propriedade Intelectual e Transferência de Tecnologia](cosinf/suap@3d62d195043c45eb7ada9274c372f6c1bea21b8f) ([merge request](cosinf/suap!13622))

### fixed (3 changes)

- [[edu] Correção de bug no cálculo da carga horária cumprida das atividades curriculares de extensão](cosinf/suap@070af7a01c08ffa62d84e5f3a876913bb20948aa) ([merge request](cosinf/suap!13623))
- [[comum] Correção do posicionamento do componente selector.](cosinf/suap@b0c4dd4cd13d20fa8d39e8379637a64e4c3f7146) ([merge request](cosinf/suap!13624))
- [Permitir administrador do modulo de remanejamento ver todas as inscrições e edital](cosinf/suap@b13dfba95ed37d9a9ae06744206d235aa507437e) ([merge request](cosinf/suap!13621))

## 3.6.12 (2023-10-20)

### fixed (18 changes)

- [[djtools] Adiciona um comando para apagar pastas velhas de suapdevs que não existem mais](cosinf/suap@95d8e17e9914cc577cb1ea86b2a8247d2c869a50) ([merge request](cosinf/suap!13620))
- [[ae] Correção das solicitações de refeições por alunos.](cosinf/suap@d957e00f41436d9c83aaa82365a108507f380dc0) ([merge request](cosinf/suap!13617))
- [[ponto] Corrige o calculo do trabalho não permitido no fds](cosinf/suap@4d00634ebd1f51f2a8bc4ab702101d5cde2163c9) ([merge request](cosinf/suap!13616))
- [[edu] adiciona mais opções de módulos no componente curricular](cosinf/suap@b2b5a54807fddfecd3109238b7166bf94f9a68eb) ([merge request](cosinf/suap!13614))
- [[progressões] Resolução do bug que exibe servidores "excluídos" na tela de...](cosinf/suap@99e6cb2a83d2318760f065e5cecfa353f49a241a) ([merge request](cosinf/suap!13613))
- [[pesquisa] Cria o admin de Propriedade Intelectual](cosinf/suap@d305d62f3f5a4342828c6039b5f8868aa71442fe) ([merge request](cosinf/suap!13612))
- [[estagios] Corrige a serialização da exportação de dados cnap dos estágios](cosinf/suap@6fbb155f63b07d44505357db495bfa27b35fc021) ([merge request](cosinf/suap!13611))
- [[pgd] Corrige a validação de datas nos formulários do pgd](cosinf/suap@6d25619df620778d06144b12267bed96c26dd952) ([merge request](cosinf/suap!13610))
- [[ponto] correção de bug na edição de dias escolhidos em compensações específicas](cosinf/suap@f3b3e07eb3223d9ebb1eea9513309b4f7978119b) ([merge request](cosinf/suap!13609))
- [[labfisico] Correção na funcionalidade de finalizar as conecções ativas no módulo labfisico](cosinf/suap@1e5568370cd4ea9c78a7c1e5cfb9e1600eaaa25f) ([merge request](cosinf/suap!13608))
- [[eventos] Correção de bug no relatório de eventos](cosinf/suap@b2d9363ca68ab9697d88c68c2fb5cd0a52f340e0) ([merge request](cosinf/suap!13606))
- [[patrimonio] Correção da exibição da tabela de marcar Inventários em requisição de patrimônio.](cosinf/suap@66f205c054e3104f8a41b5eebc77ba5cc980ba13) ([merge request](cosinf/suap!13604))
- [[comum] Adiciona tratamento para erro de conexão com o acesso govbr durante o login.](cosinf/suap@f467f32e3dd64d3f283e338a0e597616d9598adc) ([merge request](cosinf/suap!13603))
- [[edu][djtools] Corrige a edição de coordenador de curso e remove referencias...](cosinf/suap@2a17115068cc88b8f6fe4999f6c8e356d2fd8318) ([merge request](cosinf/suap!13602))
- [[projetos_ensino] Corrige a listagem de email de coordenadores](cosinf/suap@f9b6ecd8f318bba37abe5e6bdeb376da44a763ac) ([merge request](cosinf/suap!13601))
- [[comum] Correção da exibição do componente de avaliação por estrelas em formulários.](cosinf/suap@f8b806b4af4fc401e31a0d53d26abbd58314ea4f) ([merge request](cosinf/suap!13600))
- [[contratos] Adicionando rtr para views que não retornam um response por padrão](cosinf/suap@294f022f81b9776973d74bc016ca0adf16b2c83c) ([merge request](cosinf/suap!13599))
- [[comum] Evitando que o comando limpar_usuarios_orfaos apaguem usuarios com is_staff=True](cosinf/suap@b15df5af8e8a55f66fcef8315b27e2a0d6de654e) ([merge request](cosinf/suap!13598))

### changed (2 changes)

- [[processo seletivo] Exibindo apenas servidores do setor quando a configuração que permite...](cosinf/suap@7759a7861721211b4ccf7ee538707d3da00f5206) ([merge request](cosinf/suap!13605))
- [[djtools] Torna opcional os parametros de modelo no comando restore.](cosinf/suap@109941f5b4bae6eeaf1717df569697e1114a8827) ([merge request](cosinf/suap!13597))

## 3.6.11 (2023-10-17)

### fixed (16 changes)

- [[portaria] Corrige o formato da data de expiração de acesso wifi para iso](cosinf/suap@0fac2e7a0cc85f3a6db7e6dadc0c46bf6db257ad) ([merge request](cosinf/suap!13596))
- [[edu] Corrigindo problema na emissão de diploma](cosinf/suap@a83f1b88cae77b7bccdfe48cb4c4f8f1a7747ba4) ([merge request](cosinf/suap!13595))
- [[rsc] Correção na rotina de criação do processo eletrônico ao enviar processo...](cosinf/suap@fb528fd0a32a8849b0d246e1d1b433faadec64c9) ([merge request](cosinf/suap!13594))
- [[djtools] corrige erro na exibição dos links de edição e visualização da listagem do ModelAdminPlus](cosinf/suap@d6c02840b126e5913b13f5f0b974249781228c96) ([merge request](cosinf/suap!13593))
- [[comum] Correção da exibição de tabelas dentro de formulários para...](cosinf/suap@11022ff8b394f03f1f44143c9b7eb08cb479cd4f) ([merge request](cosinf/suap!13592))
- [[djtools] Remove tag após ser enviada para o gitlab](cosinf/suap@b475d9ac5d275dc4736cba562a2a796a604cd201) ([merge request](cosinf/suap!13591))
- [[processo_eletronico] Remove view depreciada de impressão de processos](cosinf/suap@3be513fe10f976c65f598fd6d69640f864def02a) ([merge request](cosinf/suap!13590))
- [[patrimonio] Exibir todas as requisições de transferência que o inventário está incluído](cosinf/suap@78c81a2548c0c5e668c45403837fed9b8b1cbf9e) ([merge request](cosinf/suap!13588))
- [[ponto] Adiciona verificação se relacionamento é um servidor antes de calcular opções de recesso](cosinf/suap@ead60fb6f9ac288dccfa4939b69b81ee30cfcd84) ([merge request](cosinf/suap!13589))
- [[comum] ajustes no comando de exclusão de usuários orfãos](cosinf/suap@617147f40aba85a29d9b753d2df1f643e31f7b10) ([merge request](cosinf/suap!13587))
- [[tesouro_gerencial] Correção na importação](cosinf/suap@d4743d2b3dfabce7f0f374d889dab31944197754) ([merge request](cosinf/suap!13585))
- [[comum] Correção na exibição dos campos de Password e Data/Hora.](cosinf/suap@65d3d1909775d7d6b45c2765145bbac669e8223c) ([merge request](cosinf/suap!13586))
- [[ae] Remoção de contadores do AE para auditores](cosinf/suap@b8fca790c1475d2ac2bd55ed810ed260b1403b33) ([merge request](cosinf/suap!13580))
- [[processo eletronico] Sistema está exigindo o campo compartilhamento com pessoas sempre](cosinf/suap@f347b5ec5c729c7fc6fb11a1421430590fb027c4) ([merge request](cosinf/suap!13582))
- [[lab fisico] consertando remocao de grupo](cosinf/suap@d66e3b4fe682772b5a34be4d0b8efa7748f50e79) ([merge request](cosinf/suap!13584))
- [[comum] Correção da exibição de informações extras de Textareas nos temas Aurora e GovBR.](cosinf/suap@cd523d6a281ca1d43c2d0a0914af411727f83d55) ([merge request](cosinf/suap!13581))

### changed (1 change)

- [[edu] Atualização do RAP para a versão 0.22.4](cosinf/suap@d4c109a0419e603b079c477581d297eb914b67a3) ([merge request](cosinf/suap!13583))

## 3.6.10 (2023-10-16)

### fixed (7 changes)

- [[eventos] Adiciona validação de código na busca de submissões de eventos.](cosinf/suap@afe5ac800b0db6e9fa3b3b88d7df0c5cd872e652) ([merge request](cosinf/suap!13579))
- [[avaliacao_integrada] Adicionando verificação de respondente ao tentar montar...](cosinf/suap@691a612f34b25c15320add77e6eff27c9d0b6b5c) ([merge request](cosinf/suap!13578))
- [[protocolo] Adicionando verificação de existencia de setor ao tentar exibir quadro](cosinf/suap@ce8588219c2448caba43da38ced956512b806db4) ([merge request](cosinf/suap!13577))
- [[ponto] Corrige loop infinito quando a data de entrada é maior que a data atual](cosinf/suap@004cdd20d0f8c08b374b09ae48cf5d5d132af318) ([merge request](cosinf/suap!13576))
- [[djtools] Adiciona parametro para permitir esconder o botão de marcar todos nos checkboxes.](cosinf/suap@b03f8de92a408237f91ee37256f88b724e18ce91) ([merge request](cosinf/suap!13574))
- [[processo_eletronico] Arrumando o redirect para enviar o usuário para o processo.](cosinf/suap@3acb9e90cbe8e4422b5ee3d83f04f700f5e08d56) ([merge request](cosinf/suap!13573))
- [[pesquisa] Verifica anuência da chefia em projetos de editais simplificados. Resolves #10489](cosinf/suap@41702c32bef7e415c0d2cc1fef8c0f5508f205a4) ([merge request](cosinf/suap!13570))

### added (1 change)

- [[demandas] Adicionando botão para atualizar o pipeline do ambiente de homologação](cosinf/suap@3e459342afdeee89a3475477c190ae11018b14db) ([merge request](cosinf/suap!13575))

### changed (3 changes)

- [[comum] Adicionando comando para apagar usuários que provavelmente são lixo](cosinf/suap@9244e047da52fcb74f02d561201b3fe14e45213c) ([merge request](cosinf/suap!13572))
- [Ajustes de responsividade de formulários.](cosinf/suap@27fdc434be01d829be9e01572dbccef6c5a22eb3) ([merge request](cosinf/suap!13568))
- [[comum] Refactoring no layout dos forms](cosinf/suap@ed5010f4c75d089662c1d9b6ec934f7ae86c4af2) ([merge request](cosinf/suap!13559))

## 3.6.9 (2023-10-11)

### changed (2 changes)

- [[progressoes] Ajustes na listagem do relatório de servidores a progredir. Closes #10487](cosinf/suap@d19c6d00c1489da52ecea4651ac2608bae95e42c) ([merge request](cosinf/suap!13567))
- [[ponto] compensação e frequências: melhoria no desempenho das consultas](cosinf/suap@ce3973ecd6a8e563b5100aa6df466f3f024b52cd) ([merge request](cosinf/suap!13453))

### fixed (5 changes)

- [[comum] Corrige a seleção de vinculo quando o usuário logado via govbr não tem um cpf associado.](cosinf/suap@e509c7451072f37e47564af2205469582a9671a9) ([merge request](cosinf/suap!13566))
- [[ae] Corrige o código da atualização de documento de inscrição. Resolves #10455](cosinf/suap@1d3c90401dfe976bd32ec780d5dfe8e98f9e9550) ([merge request](cosinf/suap!13565))
- [[eventos] Adiciona validação ao tentar salvar uma resposta de inscrição](cosinf/suap@b26d42dda0be72b47e81e77081d3cafc8414a7e6) ([merge request](cosinf/suap!13564))
- [[processo_eletronico] Corrige erro ao inserir um id de setor inválido para a caixa de processos](cosinf/suap@91dddd020e944251ce61863613ca9da0b6805825) ([merge request](cosinf/suap!13563))
- [[eventos] Corrige a remoção de opções de resposta de um evento.](cosinf/suap@bd349c691183707057b21e553234d167df319a91) ([merge request](cosinf/suap!13562))

### added (1 change)

- [[edu] Importação das notas do Moodle para o SUAP.](cosinf/suap@2bbf3950dd2d45a812f108f0bf74e1d43fd5d486) ([merge request](cosinf/suap!13561))

## 3.6.8 (2023-10-10)

### fixed (6 changes)

- [[comum] Adicionando clean para obrigar todas as pessoas físicas a terem pelo...](cosinf/suap@a8f913a27753df5ee0a6109dbe987ae16e1e3c50) ([merge request](cosinf/suap!13560))
- [[patrimonio] Corrige a geração do PDF de termo de transferência quando a...](cosinf/suap@4472dbd4cfa87262b698dbf9fdf2db4da0a38194) ([merge request](cosinf/suap!13558))
- [[djtools] Adiciona timeout para request de obtenção de dados de usuário na api do govbr](cosinf/suap@a7a1cdeb2916e14c852d63d970cef7a99ceb264b) ([merge request](cosinf/suap!13557))
- [[djtools] Move diversas configurações do settings_sample para o settings_base](cosinf/suap@477b43ec9b1531e2cf8c38225235c9a0b9c8bf87) ([merge request](cosinf/suap!13545))
- [[temp_rh2] Corrige index de inscrições para servidor sem setor. Resolves #10270](cosinf/suap@15122dd3e7dcc3ecdeee94bff1ba0f6450b9c200) ([merge request](cosinf/suap!13554))
- [[djtools] Impede a geração de usuários com Username igual ao CPF para servidores logados via GovBR](cosinf/suap@03d8213fe466a762ba733ba76ec181625511061e) ([merge request](cosinf/suap!13555))

### added (1 change)

- [[eventos] Adicionar filtro por Perfil do Participante na Aba de Participantes...](cosinf/suap@15b30ab99395bf44d71e3cca2d27e466ed56b11c) ([merge request](cosinf/suap!13556))

## 3.6.7 (2023-10-10)

### added (3 changes)

- [[edu] Dispensa em lote ENAPE](cosinf/suap@ea0f63ea28e9bf12484111db914b8c0831f01ad2) ([merge request](cosinf/suap!13551))
- [[projetos] Adiciona Relatório financeiro de extensão](cosinf/suap@30c6d619989ab1657a2e95d1314f1c30a6765d9e) ([merge request](cosinf/suap!13550))
- [[edu] Permitindo a liberação de pedido de matrícula em disciplina extra-curricular...](cosinf/suap@0a7401027d73afde75540d9fac8223df74ef0cd7) ([merge request](cosinf/suap!13543))

### fixed (6 changes)

- [[estágios] Corrige validação do período do aluno no cadastro de estágio](cosinf/suap@5ddaec69015510cfb7efb8953e1f5e3fb0aed49c) ([merge request](cosinf/suap!13553))
- [[cursos] Corrige erro na tela de informar cadastro de folha. Resolves #10371](cosinf/suap@dcaaacee22854a76898cbc827a7b305924264396) ([merge request](cosinf/suap!13549))
- [[djtools] Corrige a geração de documentação automatizada do suap](cosinf/suap@b12a986d7621b67c7f90d498f6fdda62bb9b4c32) ([merge request](cosinf/suap!13548))
- [[processo_eletronico] Correção de bug que não trata exceção ao obter ultimo...](cosinf/suap@b0ee4fde679b2baf2272c3440bbc10216e464886) ([merge request](cosinf/suap!13544))
- [[portaria] Correção de bug que permitia o cadastro de visitante duplicados (módulo da...](cosinf/suap@544d28640a93faa300f01019d94814ab18106974) ([merge request](cosinf/suap!13541))
- [[comum] - Alteração para realizar logout no SSO do Gov.BR](cosinf/suap@ea920cbe9b9559e91fba7772f7d7fc3d12521e64) ([merge request](cosinf/suap!13539))

### changed (3 changes)

- [[pesquisa] Ajustes nos cadastros dos laboratórios multiusuários. Demanda 1683](cosinf/suap@ce3f9e1d27b3eeb318d98cded6a949b7b986a12d) ([merge request](cosinf/suap!13530))
- [[projetos] Melhorias no cadastro dos Núcleos de Extensão e Prática...](cosinf/suap@4ecb64a5ca3dffd32ad0f98f2e7f58d0c7a87b0f) ([merge request](cosinf/suap!13547))
- [[estagios] Melhorias no registro de visita de professor orientador de estágio...](cosinf/suap@b9570bd589a7b8d1751ba0da73bc7343ec241a41) ([merge request](cosinf/suap!13546))

## 3.6.6 (2023-10-06)

### changed (9 changes)

- [Adicionando chaves no modelo de documento de diploma para viabilizar a emissão...](cosinf/suap@d9ba0df61045244742604a416844882266bde8d7) ([merge request](cosinf/suap!13540))
- [[djtools] Substitui todos os CheckboxSelectMultiple por CheckboxSelectMultiplePlus](cosinf/suap@309879e8e5cbb6cc421ffd0a92bf5f84485343d1) ([merge request](cosinf/suap!13537))
- [[plan_estrategico] Ajuste na exibição Objetivos estratégicos](cosinf/suap@c85122572ddfae99269268b7695b55523235a055) ([merge request](cosinf/suap!13536))
- [[processo_eletronico] melhoria performance tela processo](cosinf/suap@77c82fec6f993272be9e03e31c8a3cd5a76d9263) ([merge request](cosinf/suap!13523))
- [[pgd] melhorias usabilidade chefe do setor](cosinf/suap@9d929abd9d6d77776ac9c8592553fe2bee1643c6) ([merge request](cosinf/suap!13534))
- [[ae] Ordena os registros por data na tela de justificar falta. resolves #10450](cosinf/suap@3e1e8266e8241c871960e6f8fcc3795a4aa56471) ([merge request](cosinf/suap!13535))
- [[eventos] Melhoria performance tela eventos](cosinf/suap@2114f3b5641c5cff61c084503c31ad8ce7497f1f) ([merge request](cosinf/suap!13529))
- [[ae] Filtro para desdobramento específico na lista de alunos. Demanda 691](cosinf/suap@89b1025c964a24c9dee5993bccf68c43799ac790) ([merge request](cosinf/suap!13526))
- [Ajustes e correções de layout e usabilidade para telas de vários módulos.](cosinf/suap@5b2b4310559d0f108c716049109477b189b58d10) ([merge request](cosinf/suap!13507))

### fixed (5 changes)

- [[eventos] Resolvendo bug da média calculada de forma incorreta e consulta de Trabalho Pendentes](cosinf/suap@1d63b35b104fbd034722db242cea2512bfb993d5) ([merge request](cosinf/suap!13538))
- [[edu] Remove uma tabela do edu que não está mais sendo usada](cosinf/suap@95ef01dc41aeda45d3228fe162674c65343c343a) ([merge request](cosinf/suap!13533))
- [[eventos] Corrige a validação de submissão quando nenhum avaliador é escolhido.](cosinf/suap@a243b75ba7511783e9c71f243f555c7d97ab940d) ([merge request](cosinf/suap!13531))
- [Correção da exibição das mensagens de erros em formulários em vários Temas](cosinf/suap@e6d7116ee8aed67f445d6cf8f38e51011000a15b) ([merge request](cosinf/suap!13532))
- [[processo_eletronico] Corrige a solicitação de compartilhamento de documentos digitalizados.](cosinf/suap@9716e5fb245e7f3730293c084e69705668c981ae) ([merge request](cosinf/suap!13527))

## 3.6.5 (2023-10-05)

### added (1 change)

- [[plan_estrategico] Adição do PTREs e Ação no Plano interno](cosinf/suap@b2fd7b7a731aa579d2cb1711a14f27f10c9c003b) ([merge request](cosinf/suap!13525))

### changed (2 changes)

- [[djtools] Oculta informações de IP, usuário e nome de banco de dados que são...](cosinf/suap@232b918dcd89845fc88f8d8d1184fd8464738a1a) ([merge request](cosinf/suap!13524))
- [[edu] Importação dos dados pessoais detalhados dos alunos do PROITEC.](cosinf/suap@5843218bd86c6f1591a75773fd0641e009d34b41) ([merge request](cosinf/suap!13520))

### fixed (5 changes)

- [[centralservicos] Adiciona tratamento de erros de transação para a avaliação...](cosinf/suap@88205b4dc6d8244446b8d98f9d838d8fe63460e3) ([merge request](cosinf/suap!13521))
- [[api] Adicionando verificação de necessidade de alteração de senha ao tentar gerar token jwt](cosinf/suap@95d2e4f26130121bd12f92f2692fd19ade670e65) ([merge request](cosinf/suap!13522))
- [[ponto] Corrige a lista de chefes das Opções de Recesso para armazenar o validador corretamente](cosinf/suap@cfd1939e145286f2606afb3e6ad993b24b52763a) ([merge request](cosinf/suap!13519))
- [[catalogo_digital] Troca as exceções tratadas por erros de validação ao tentar...](cosinf/suap@5a1cb52fd6786b8feb60e65cd8a66d1b790e6e71) ([merge request](cosinf/suap!13518))
- [[eventos] Corrigindo url de redirect de verificação de permissão de avaliador em eventos.](cosinf/suap@a294ee0ac0c61422934a3fb1b304bbe967b35711) ([merge request](cosinf/suap!13517))

## 3.6.4 (2023-10-04)

### fixed (7 changes)

- [[processo_eletronico] - Corrige erro de visualização dos compartilhamentos dos...](cosinf/suap@5b54300c0f5d61f243e5429f39b55407cbd7c51e) ([merge request](cosinf/suap!13514))
- [[ae] Correções na tela de solicitar refeição. Resolves #10415](cosinf/suap@116844f94ab3c75850a394201a081d5a51c23874) ([merge request](cosinf/suap!13515))
- [[demandas] Vinculando issue de demanda no gitlab ao usuário que clicou no botão de criar Issue](cosinf/suap@d4b86cc9b05a5e2b3a2f8b3f3d4559ddd27a7b35) ([merge request](cosinf/suap!13513))
- [[djtools] Adiciona um parâmetro para exibir ou não o campo de segundos no TimeWidget do suap](cosinf/suap@cf7c6222e92b5ac3fc3dd8eb5421ddaec5be96d4) ([merge request](cosinf/suap!13511))
- [[edu] corrige erro ao tentar excluir aluno](cosinf/suap@058237c6b1055ea0d2d09fc50d3a5adac3a13700) ([merge request](cosinf/suap!13510))
- [[etep] corrige erro na notificação de membros etep no acompanhamento de aluno](cosinf/suap@dd3a3c1009b55ce7b72162326a1c1da722f980f6) ([merge request](cosinf/suap!13509))
- [[LAB Virtual] O campo Name não suporte o operator OR](cosinf/suap@f8906240fcfa28345fd75802ad13b286b6555a3a) ([merge request](cosinf/suap!13508))

### changed (2 changes)

- [[ae] Cria campo de resposta ao aluno ao emitir parecer da inscrição. Demanda 1531](cosinf/suap@326eb875155199b3f7c7ab7767bac9da521a703d) ([merge request](cosinf/suap!13516))
- [[djtools] Remove o pdfunite do suap](cosinf/suap@72a579c291df93797a2228a463204ba329c8a313) ([merge request](cosinf/suap!13512))

## 3.6.3 (2023-09-29)

### changed (4 changes)

- [[ae] Solicitação e validação de comprovação do uso de auxílio eventual. Resolves #10031](cosinf/suap@c6f50172a7a451dfdf3271f1d99fb1d7048492a2) ([merge request](cosinf/suap!13505))
- [[catalogo_provedor_servidor]  Atualiza o serviço de "Matrícula em Curso de...](cosinf/suap@4b5da8e57282388cee2890a136ea4f4d8a4566a7) ([merge request](cosinf/suap!13504))
- [[projetos] Permitir adicionar termo de adesão durante execução do projeto. Resolves #10383](cosinf/suap@1d71411576df2994c42b1c3860a114dbdb8154d1) ([merge request](cosinf/suap!13494))
- [[djtools] Removendo libreoffice da imagem docker do suap](cosinf/suap@eca4238f8ce4069b899b829cc04da78b17176974) ([merge request](cosinf/suap!13485))

### added (3 changes)

- [[plan_estrategico] Adiciona funcionalidade para Macroprocesso e processo...](cosinf/suap@ed637c2a432054c778e4410c86cf45f2f6f06153) ([merge request](cosinf/suap!13506))
- [[contratos] Adiciona informações de empenhos no relatório de exportação de...](cosinf/suap@75ba07c51df14ccf0adafdb97886b6e447282852) ([merge request](cosinf/suap!13491))
- [[eventos] Demanda 1584: Melhorias para cadastro de Evento](cosinf/suap@8355c6293bbfdb2ff96f08113c54e5d1586cf3e7) ([merge request](cosinf/suap!13481))

### fixed (17 changes)

- [[djtools] Adicionando patch tags para cada deploy realizado do suap](cosinf/suap@832642063098c0cd76069ebf616832f70c92cd22) ([merge request](cosinf/suap!13495))
- [[djtools] Ignora erro no sentry caso seja problema de conexão com o conectagov](cosinf/suap@ff4005efd285f521fe8698d347bbb1212176763a) ([merge request](cosinf/suap!13503))
- [[centralservicos] Adiciona tratamento para evitar a quebra da tela de...](cosinf/suap@2fed9e1120e8d4e2e2792cf16d9cdab95397a286) ([merge request](cosinf/suap!13502))
- [[eventos] Adiciona verificação ao tentar adicionar um tipo de participante ao evento](cosinf/suap@0ab378c2ad21000aa433012a8b9bf0f92fe896d5) ([merge request](cosinf/suap!13501))
- [[processo_eletronico] - Permitir prestador de servico poder ter poder de chefe...](cosinf/suap@7803a513c2916c265ed3e132aae5ca77dabeabb3) ([merge request](cosinf/suap!13500))
- [[djtools] Corrige problema de conexão entre o django-health-check e o redis](cosinf/suap@bb392d67d9015724d639aa695448dd3cfd23c3bf) ([merge request](cosinf/suap!13499))
- [[pgd] Adiciona verificação de adesão existente ao tentar criar um PIT](cosinf/suap@ec53c23630746b5b98065ad0a7db98dda3a30a77) ([merge request](cosinf/suap!13496))
- [[professor_titular] Corrige problema ao tentar acompanhar avaliação](cosinf/suap@9e094fb7e72d2fc565c1f4a50727a436c9741da4) ([merge request](cosinf/suap!13498))
- [[eventos] Adicionando verificação de usuário autenticado ao verificar se ele...](cosinf/suap@a49439d1b7dc4d7ce7559df65a26fa55cfc6e856) ([merge request](cosinf/suap!13497))
- [[eventos] Correção na internacionalização do módulo de eventos](cosinf/suap@24eb25a471cd02661684de82d79ec35a35be0f10) ([merge request](cosinf/suap!13493))
- [[projetos_ensino] Corrige funcionalidade de gerenciar monitor do projeto. resolves #10369](cosinf/suap@f5cdd219d8af2f99fe88c48f9d5a70e8df7729db) ([merge request](cosinf/suap!13489))
- [[LAB VIRTUAL] Correção na rotina de adicionar um membro](cosinf/suap@4ad87d1a1dd11fb5670473649d7fff553258996a) ([merge request](cosinf/suap!13490))
- [[djtools] Removendo referências para o ifrn no arquivo .gitlab-ci.yml](cosinf/suap@6d1eb1b0482a0456a53d081046f88a362f56b14b) ([merge request](cosinf/suap!13488))
- [[encceja] corrigi erro na contagem de enccejas não cancelados](cosinf/suap@7f0b6db9f4a6c02bf923db23d5daf5060110a58f) ([merge request](cosinf/suap!13487))
- [[djtools] Melhorando mensagem de PDF inválido durante upload de arquivos](cosinf/suap@577ed105e3a5be80a33f4c348b5c5250bf60d124) ([merge request](cosinf/suap!13486))
- [[edu] corrige erro ao aproveitar disciplina de aluno cursando diário do componente em outra matriz](cosinf/suap@21f8c8a50700b7fc85e0ce0c33a82beff744245e) ([merge request](cosinf/suap!13484))
- [[Comum]: Campo nome não existe no modelo Pensionista:](cosinf/suap@6b559a90fce9cb66aee2a3771b0aba4418301df9) ([merge request](cosinf/suap!13483))

## 3.6.2 (2023-09-24)

### fixed (16 changes)

- [[LAB VIRTUAL] Rename](cosinf/suap@b3b5b35aedf3bb721fc4bdc8fef9a0a22dfefff4) ([merge request](cosinf/suap!13479))
- [[edu] Removendo strings de conexão do settings_sample para o siabi e q-academico](cosinf/suap@e2e0f9d541081477dffa963caba43e043d81b66f) ([merge request](cosinf/suap!13475))
- [[processo_eletronico] -  Corrige bug que impedia visualizacao e impressao de processos](cosinf/suap@ed2b5c8ee5b4c9b3b27fe1c0c9790ae264922e3c) ([merge request](cosinf/suap!13478))
- [[projetos_ensino] Corrige parâmetro pra url de resultado final.](cosinf/suap@a84a57893029de15a886ab5a48a001826d153365) ([merge request](cosinf/suap!13476))
- [[estágios] campo justificativa não existe. O certo é justificativas](cosinf/suap@bb6d98f4db27cd3bb180a60ed7c66879eb39e153) ([merge request](cosinf/suap!13474))
- [[api] Correção de bug que impedia a exclusão de aplicações OAuth2](cosinf/suap@fa195b230dec99bc94875c3bccd953064a0a1693) ([merge request](cosinf/suap!13473))
- [[edu] Corrige a emissão de histórico final para alunos integralizados no ensino médio](cosinf/suap@016ef3c7322b27a81fe9e891be7c736e6a77c797) ([merge request](cosinf/suap!13471))
- [[processo_eletronico] Remove assinatura de documentos texto mergeados com outros arquivos.](cosinf/suap@c9a5f453e7e7626f089d1e5a8ba30470c30a6dbb) ([merge request](cosinf/suap!13468))
- [[djtools] - Corrige erro user_info estrangeiro](cosinf/suap@25e09393cefc7e365405f34e21922c29e92f48f7) ([merge request](cosinf/suap!13470))
- [[processo_eletronico] O campo pessoa_fisica não existe mais no AtribuirProcessoForm.](cosinf/suap@a6261710e8238244f6a0d34a882b8107141be042) ([merge request](cosinf/suap!13469))
- [[edu] Tratando a exceção quando ocorre algum erro na sincronização dos diários...](cosinf/suap@37510e6c44115a38abcc4d0da6c72bc7bd1a1827) ([merge request](cosinf/suap!13466))
- [[djtools] Add Função merge_pdf_files_qpdf para merge de arquivos PDF como opção...](cosinf/suap@fd1b38a317f57c9035bc7e6d15cfa43f924d8d1d) ([merge request](cosinf/suap!13460))
- [[projetos] exibe nome do avaliador da solicitação de cancelamento do projeto](cosinf/suap@b20e0e3bfbfaaba26e1263e337c27d54e36d6a3e) ([merge request](cosinf/suap!13461))
- [[documento_eletronico] Busca na consulta pública dos documentos não levava em...](cosinf/suap@afe07dd20a4590e11ecd82c12e932f70b5155a83) ([merge request](cosinf/suap!13457))
- [[documento-eletronico] Correção de bug na migração da pessoa única do documento eletronico](cosinf/suap@dc93a4d60f568aba908ff565b25cf6a0d7277f4d) ([merge request](cosinf/suap!13459))
- [[projetos_ensino] Corrige geração do resultado do edital](cosinf/suap@93234a952e8ec1b8bb4597c13e405218dceeebe2) ([merge request](cosinf/suap!13456))

### changed (1 change)

- [[ae] Melhoria nas informações da Tabela de disponibilidade. Demanda 1631](cosinf/suap@81c2fcde91b1cf03714d3e6c390cb4743243b3cb) ([merge request](cosinf/suap!13477))
- [[comum] Remoção de Herança em Dependente, Pensionista e Responsável Legal](cosinf/suap@24227faee0aacff0f305b40b7bbfbd2498916f03) ([merge request](cosinf/suap!13442))
- [[ae] Gerenciamento da oferta de auxílios eventuais. Demanda 1651](cosinf/suap@e94a928563f1c6a409dea5496430e7701c70593a) ([merge request](cosinf/suap!13402))

### added (8 changes)

- [[VDI] adicionando suporte para n servidores](cosinf/suap@c703df3b6f1efff15741d5f99f044c89371f757d) ([merge request](cosinf/suap!13472))
- [[contratos] Integração com a API do Comprasgov.br para importar informações no...](cosinf/suap@9a0d9495b6f3b157e8f4d1f8f09bfa73e0ce6c8e) ([merge request](cosinf/suap!13464))
- [[eventos] Demanda 1664: Critérios de avaliação de trabalhos de eventos](cosinf/suap@c7c8b6624db2c29f132ac515d6c0fafd8e52c3f1) ([merge request](cosinf/suap!13462))
- [[processos/documentos eletronicos] Melhorias processo documento eletrônico](cosinf/suap@0daab74004025f32b5a64acea0dfeea8c03ebbc1) ([merge request](cosinf/suap!13446))
- [[pesquisa] Cálculo de indicadores de pesquisa aplicada e alunos de ações...](cosinf/suap@6135ec809691a001db065e8560b45d1e5aa80367) ([merge request](cosinf/suap!13465))
- [[eventos] Demanda 1665: Impressão de Etiqueta com dados do Participante](cosinf/suap@a3317f15206eb97bb87f5b8af433d279f31f0755) ([merge request](cosinf/suap!13463))
- [[djtools] Ignorando devcontainer](cosinf/suap@7bc133b0bfd2f272409331e5f6475b0a021b1dfa) ([merge request](cosinf/suap!13458))
- [[estagio] Implantar a assinatura digital nos registros de visita do orientador](cosinf/suap@eb5994b19a60d7b753685ac6ddb9197ba9f20272) ([merge request](cosinf/suap!13355))

## 3.6.1 (2023-09-20)

### fixed (45 changes)

- [[processos_eletronicos] Corrige notificação de processos encaminhados](cosinf/suap@1b5c8ef277af86f6b8bfc9b873b89328baa245ba) ([merge request](cosinf/suap!13454))
- [[comum] Correção no cadastro de Usuários Externos](cosinf/suap@f69eb0730c48ccf105eeefab67e7c26179d029d9) ([merge request](cosinf/suap!13455))
- [[pesquisa] Permite editar dados do membro da obra. Resolves #10332](cosinf/suap@78c5afec14a13c09c351138866488964b8946761) ([merge request](cosinf/suap!13452))
- [[processo-seletivo] Correção de bug que impede a visualização de vagas extras...](cosinf/suap@496799e601f2ba91e944d221afa12dde84d5a02e) ([merge request](cosinf/suap!13437))
- [[documentos_eletronicos] Corrige auto vinculação de interessados nos documentos eletrônicos](cosinf/suap@147dab97ec6134aefb1768c848d87d6f01242f05) ([merge request](cosinf/suap!13445))
- [[eventos] Corrigindo url ao notificar avaliador de trabalho](cosinf/suap@a8f3170b1126b76a04bbcbf7cc7793e5b815a206) ([merge request](cosinf/suap!13444))
- [[eventos] Corrigindo erros no modulo de eventos e corrigindo permissões de acesso](cosinf/suap@fe510779a473b5d527c4cef701983a4b1d2443d2) ([merge request](cosinf/suap!13443))
- [[comum] Salva o perfil do Prestador de Serviço. item da #10305](cosinf/suap@23cefb6820874209e8f0f3d00352f893c4514902) ([merge request](cosinf/suap!13441))
- [[comum] Corrige exibição da data de avaliação da reserva de sala. resolves #10281](cosinf/suap@8a81aaefa95ec56bfd4ea88e9460bf913e75bb3d) ([merge request](cosinf/suap!13440))
- [[edu] retira exibição de botão remover aluno em turma de minicurso para...](cosinf/suap@c40be9c0dd2367d173d6f959298eae8f7e822496) ([merge request](cosinf/suap!13439))
- [[Processo Eletrônico] Adicionando comando para migrar todas as referencias de...](cosinf/suap@4d55e857d8ad3feed46682c325785f46554f9a99) ([merge request](cosinf/suap!13435))
- [[eleicao] Corrige erro ao calcular percentual de votos brancos e nulos. Resolves #10300](cosinf/suap@cbc5f55371e0867e02616c3ac3504aa8f2eafe20) ([merge request](cosinf/suap!13433))
- [[edu] lista apenas alunos do campus do usuário no abono de falta](cosinf/suap@26e8fb1f204f391ca8f22d2f7dc83eb7e15424c3) ([merge request](cosinf/suap!13431))
- [[edu] corrige erro ao editar estágio docente](cosinf/suap@56e25e882c6869f1154fbe2dd33bcb3cdecf0b14) ([merge request](cosinf/suap!13432))
- [[documento_eletronico] Corrige erro ao solicitar assinatura com anexação a processo](cosinf/suap@22f1c73b45b4b0bc3bba4cb8bdbb4f46f824e92e) ([merge request](cosinf/suap!13425))
- [[pesquisa] Corrige verificação de número máximo de alunos no projeto. resolves #10260](cosinf/suap@add68d65de279d840a79d2e89588f98d337f08b5) ([merge request](cosinf/suap!13420))
- [[djtools] Adiciona tratamento quando uma imagem da documentação do suap não é encontrada.](cosinf/suap@98406a975b38daf932215c2c859f4bc37356e27a) ([merge request](cosinf/suap!13419))
- [[documento_eletronico] Remove logging de falhas de notificação do govbr, pois...](cosinf/suap@6e19e36bf346ad68d3ca855ed8783162a3f9d932) ([merge request](cosinf/suap!13418))
- [[centralservicos] Corrige a listagem de campus disponíveis para abertura de...](cosinf/suap@e405fca99dca186ae49910cf9ba81168795de240) ([merge request](cosinf/suap!13417))
- [[processo_eletronico] Corrige a listagem de tramites de funcionário para filtrar por vínculos.](cosinf/suap@3c8a38655a3fca34f1a9b291f4c4cec7178d6acc) ([merge request](cosinf/suap!13416))
- [[erros] Exibição de componente HTML na aba "Notas Internas" vazia](cosinf/suap@38ea1e5e2809543ea423dd3feee88f151c279326) ([merge request](cosinf/suap!13413))
- [[contratos] Corrige bug ao atualizar medição de contrato](cosinf/suap@fa60eb7e620f4dac180b5c881cbc13d67e588a01) ([merge request](cosinf/suap!13415))
- [[projetos_ensino] Corrige erro na tela de indicar avaliadores.](cosinf/suap@1d89c89b8ffcc6f72b289589e11613b787198e62) ([merge request](cosinf/suap!13411))
- [[edu] verifica validade máxima na homologação de documento da pasta documental](cosinf/suap@78c6cd12687600e8a69642a5e8d1f3ac9d912092) ([merge request](cosinf/suap!13407))
- [[processo_eletronico] Corrige format_user pra vínculo quando é pessoa externa](cosinf/suap@f36bce0e23aa8ccc87b3a7eca1598d7e970b6c7e) ([merge request](cosinf/suap!13406))
- [[edu] corrige erro na geração de auditoria sistec](cosinf/suap@e9649fa2cbfe43b25af2a700cd8564dd8cf5453c) ([merge request](cosinf/suap!13405))
- [[Processo Eletronico ]Ajustes na rotina de finalizar requirimento](cosinf/suap@f8dbfd3a10fd5e8f681a03c66a7aac07d493c0b2) ([merge request](cosinf/suap!13401))
- [[edu] Removendo annotate desnecessário de queryset das estatísticas](cosinf/suap@331d15b46a6cbcf6760fadadb34d10141a0f4689) ([merge request](cosinf/suap!13400))
- [[processo_eletronico] Corrige a edição de processos com tramite](cosinf/suap@e943b733b0d03df8c487dd0c621968ec0f02579b) ([merge request](cosinf/suap!13392))
- [[processo_eletronico] Corrige a busca textual por distribuição de tramites](cosinf/suap@e18275dd2ee5e3b2c57adcf8c764303ed2f7acdf) ([merge request](cosinf/suap!13398))
- [[processo_seletivo] Verificando se o parse do XML é válido ao tentar validar importação de edital](cosinf/suap@72164ed472cd3d90c1f394d07a89ac1e52a8f707) ([merge request](cosinf/suap!13396))
- [[progressao] Corrige erro gerar processo eletrônico nas progressões](cosinf/suap@bf82e42564de7b4b1fa15fc21e63ce193cd0307b) ([merge request](cosinf/suap!13393))
- [[processo_eletronico] Corrige busca por texto na caixa de processos. resolves #10222](cosinf/suap@f95ec9110bc155f9b041903a2fb21ced6e81e0d0) ([merge request](cosinf/suap!13390))
- [[pesquisa] Resolve erro ao atribuir servidor à programa de pós. resolves #10223 #10226](cosinf/suap@a1f7736810980dd401cf0c6cb40ff6128f5929a5) ([merge request](cosinf/suap!13391))
- [[djtools] Adicionando container do min.IO ao ambiente de desenvolvimento do suap](cosinf/suap@46780de43a9ae205a4592977472f6cfa708609d5) ([merge request](cosinf/suap!13388))
- [[edu] remove alunos sem matriz e de minicurso sem matrícula das auditorias de ensino](cosinf/suap@c58435ddb4df88702927c6c517c0e74558ee13b5) ([merge request](cosinf/suap!13387))
- [[ae] Corrige verificação de oferta quando aluno solicita refeição na...](cosinf/suap@bafbd2defe84248093e6d453c393def2f333f53e) ([merge request](cosinf/suap!13383))
- [[processo_eletronico] - add hiperlink listagem vinculos processo eletronico, correcao de erros](cosinf/suap@2762e05983b699abf04339a80b347c675cd80c74) ([merge request](cosinf/suap!13385))
- [[processo_eletronico] - Permite que o chefe ou pessoas com poder de chefe...](cosinf/suap@df5857132217dc8adee55bced363475e6b4fe790) ([merge request](cosinf/suap!13384))
- [[processo_eletronico] Corrige erro que impedia abrir aba de documentos e...](cosinf/suap@6a79d27324c14b6266730dd16bf79c5778c87d88) ([merge request](cosinf/suap!13380))
- [[processo_eletronico] Corrige erro que impedia filtra na caixa de processo por...](cosinf/suap@954d4bec1d0631ea3b0b2fc5505994a18f5258ce) ([merge request](cosinf/suap!13382))
- [[Processo Eletrônio] Removendo referencias aos campos remetente_pessoa e destinario_pessoa](cosinf/suap@a5d3fa778b72508d8091aa25a559cf429493d0ce) ([merge request](cosinf/suap!13378))
- [[processo_eletronico] Removendo referência a tabela pessoa em TramiteDistribuicaoForm](cosinf/suap@864f7b16713cd32952184a7648d821922a41c2ad) ([merge request](cosinf/suap!13381))
- [[processo_eletronico] Migrando filtro do form FiltroCaixaEntradaSaidaForm para Vínculo](cosinf/suap@cac62dcbfed7bb3914e25c7d73e1d1fb0446bb7f) ([merge request](cosinf/suap!13379))
- [[processo_eletronico] O método get_email deve retornar uma string](cosinf/suap@a528b3ec31cff016782f8ac9e8c82caa8d028c1e) ([merge request](cosinf/suap!13377))

### added (7 changes)

- [[eventos] Demanda 1585: Melhoras no processo de Inscrição para Eventos](cosinf/suap@aafce5924006462a097c650b432b2a0a35924225) ([merge request](cosinf/suap!13451))
- [[estágios] Melhora cadastro de aprendizagens e cria exportação de dados seguindo requisitos do CNAP](cosinf/suap@babc4652266b2c1f3447ddece961c01f12a6ffb9) ([merge request](cosinf/suap!13447))
- [[Laboratórios Virtuais] Implementação alpha do VDI](cosinf/suap@d31053140eecb887bbe24c07a379de627528a2b3) ([merge request](cosinf/suap!13430))
- [Demanda 1609: Criação de rotinas para Agenda de Fiscalização](cosinf/suap@fb8413f57db76968a6296dcd33c774cd3786363c) ([merge request](cosinf/suap!13429))
- [[eventos] melhorando clean link video](cosinf/suap@06127eb064289164911e7469f021f9ae1d32b096) ([merge request](cosinf/suap!13422))
- [[pesquisa] Cria módulo das incubadoras tecnológicas. Demanda 1507](cosinf/suap@d0d3f291fddd903b99c644c0fd2140b8124eb0cf) ([merge request](cosinf/suap!13409))
- [[ponto] opção de compensação específica do tipo impositiva: tela de feedback...](cosinf/suap@a45ca6b6e978bb42ef254f735a927d7ac508387b) ([merge request](cosinf/suap!13386))

### changed (15 changes)

- [[projetos] Verifica se critério de avaliação do edital pode ser excluído. resolves #10314](cosinf/suap@d5dfac94f85b66518f4c7da606383192241b09ca) ([merge request](cosinf/suap!13438))
- [[projetos] Permite o cadastro de mais de um termo de adesão. Demanda 1513](cosinf/suap@7462b50041ee0bf90d482a68ca8b6eba3fb2c100) ([merge request](cosinf/suap!13428))
- [[comum] Alteração informativo complexidade de senha](cosinf/suap@58b92f3d20d40e3ae62d0f8bd2ece5bb4d428a22) ([merge request](cosinf/suap!13426))
- [[projetos] Gerente sistêmico deve ver alerta de projeto externo pendente de...](cosinf/suap@566d17d33ff724166f977b8dde91e9cff0ef77fe) ([merge request](cosinf/suap!13424))
- [[ae] Retira restrição de solicitações de refeições em dias liberados. demanda 1565](cosinf/suap@3b746d995c822714d0c5fa90d97727a7ac4b1ca5) ([merge request](cosinf/suap!13423))
- [[djtools] Substituindo PasswordInput por PasswordField](cosinf/suap@266f4c787a52340b69d9437a2e3d2c63d28ed53a) ([merge request](cosinf/suap!13412))
- [[rsc] Ajuste no tempo de aceite e avaliação](cosinf/suap@cbc817e274abc900bd75853bf2bb70911e890c99) ([merge request](cosinf/suap!13414))
- [Melhorias de usabilidade gerais para diversos módulos](cosinf/suap@c5107eed5fbf656cbb3fd5dfe972545e02cfe90e) ([merge request](cosinf/suap!13408))
- [[pesquisa] Migra PessoaFisica do modelo ReconhecimentoDiploma. resolves #10214](cosinf/suap@58657111ebad42d639841028d76c014216140cb8) ([merge request](cosinf/suap!13389))
- [[processo_seletivo] Tornando o processamento de matrículas PROITEC assíncrono...](cosinf/suap@535332761ee52fe32c53118907e84fcf6da51e49) ([merge request](cosinf/suap!13399))
- [[processo_seletivo] Adicionando as informações se o candidato foi...](cosinf/suap@90eba98445e2db65fdacda13c107e8750aebd55f) ([merge request](cosinf/suap!13394))
- [[estagios] Transfere notificações de estágio para o crontab](cosinf/suap@003588488ed94e69f03eebfa5cfe5426ee2194dc) ([merge request](cosinf/suap!13395))
- [Alterar Modelagem módulo de Estágios de pessoa_fisica para Vínculo](cosinf/suap@982a23c5bab5c20a0bf97242e52c5f187b570902) ([merge request](cosinf/suap!12228))
- [[RSC] Migração de PF para Vínculo](cosinf/suap@5f878dab7e3afc23d7e9b709da131d7f6321f66c) ([merge request](cosinf/suap!13374))
- [[processo_eletronico] Migração das referências de Pessoa Física para Vinculo...](cosinf/suap@83539f9af70f6aa40d6215a2b5dc8f9dbdd65b6a) ([merge request](cosinf/suap!13019))
- [[Processo Eletronico] Refatoração do código](cosinf/suap@010c31b3daf753bfee89327d17537298d7aabeac) ([merge request](cosinf/suap!13404))

## 3.6.0 (2023-09-02)

### fixed (34 changes)

- [[temp_rh2] Correção ao tentar localizar inscrição inexistente. Resolves #10177](cosinf/suap@afd1656b62bdfb7bc9d5a4c6b8d3d661aff5b753) ([merge request](cosinf/suap!13372))
- [[eventos] Corrige erro ao cadastrar evento sem informar data da atividade. resolves #10097](cosinf/suap@ba78dd794253e23e639d748f2ad3059653d5d51c) ([merge request](cosinf/suap!13368))
- [[projeto_ensino] Correções nos testes do behave do módulo projetos de ensino,...](cosinf/suap@a49c280b325cb56b5ecd16d6e241b709eea6010b) ([merge request](cosinf/suap!13366))
- [[djtools] Corrige a geração da documentação automatizada dos testes do behave](cosinf/suap@96d52753115f5b68587bd6d78731e48d8b447cab) ([merge request](cosinf/suap!13365))
- [[edu] corrige erro no abono de falta de aluno](cosinf/suap@16692f7c642577423dc8dcfac846488575dbe400) ([merge request](cosinf/suap!13364))
- [[edu] impede edição de período letivo de aluno sem matriz](cosinf/suap@56ab8cc469b6d45ad994335931b54309cff483b1) ([merge request](cosinf/suap!13363))
- [[edu] corrige erro na geração de auditoria do tipo matrícula em modalidade](cosinf/suap@355956739bf40c9114f87307d4fcedd6be5038e3) ([merge request](cosinf/suap!13362))
- [[erros] corrige erro ao gerar issue no gitlab](cosinf/suap@dbc93c44a8f3581a771763be340acbf0c45d4145) ([merge request](cosinf/suap!13360))
- [[edu] corrige erro ao deferir abertura extemporanea de diretoria sistêmica](cosinf/suap@ad07ea579a038242acaa4d65781c053326d5834f) ([merge request](cosinf/suap!13358))
- [[edu] Remove a coluna pessoa_fisica_remover_id da tabela edu_professor](cosinf/suap@373704d90af7fd519a1ffffcbf001db71ff7f517) ([merge request](cosinf/suap!13357))
- [[documento_eletronico] Solicitação de assinatura com anexação a processo](cosinf/suap@ea34fa714aa590243cfcd11b11adeddb1c021e5f) ([merge request](cosinf/suap!13356))
- [[edu] Sinalização da utilização de arquivos da pasta documental do aluno nos...](cosinf/suap@3b33a08e9a7ad625041b7a153990c30e1cd1215e) ([merge request](cosinf/suap!13354))
- [[bug] Ajustes para impressão de gráficos HighCharts](cosinf/suap@5bac5a113c37a7b1fed6a0e67d0506c766538b69) ([merge request](cosinf/suap!13353))
- [[comum] Separando a documentação gerada pelos testes do behave por módulo](cosinf/suap@c7479540e4134a21f38682bae0314ffeaa751e28) ([merge request](cosinf/suap!13350))
- [[edu] corrige erro na geração de auditoria sistec](cosinf/suap@29066f2bcd1766ecbb42ea2100c1aaf10ababceb) ([merge request](cosinf/suap!13349))
- [[comum] Erro ao utilizar foto do govbr](cosinf/suap@38fe069a170b7961ad0e1350cf60f527f023edfb) ([merge request](cosinf/suap!13343))
- [[projetos_ensino] Corrige erro ao buscar projetos pelo nome do coordenador e...](cosinf/suap@ea7fc1b64bb5771d2162d622148486f945bfcf2c) ([merge request](cosinf/suap!13345))
- [[djtool] Erro em busca com mais de 10 termos no admin](cosinf/suap@2cfda5884391f05b5567d09cc6bc6c1c7296971f) ([merge request](cosinf/suap!13346))
- [[edu] Correige aprovação da atividade de extensão relacionada a diário quando...](cosinf/suap@68a732845c0b3e13aea2a60da70916e40baa899e) ([merge request](cosinf/suap!13342))
- [[documento_eletronico] Erro ao excluir um documento rascunho que está...](cosinf/suap@55811259761a62f8e6b3319a7ecd7a2995db34e1) ([merge request](cosinf/suap!13341))
- [[temp_rh2] Erro ao exportar inscrições de Competições Desportivas](cosinf/suap@4d8a0e8fe753a98888bfafd1061adfc100282c90) ([merge request](cosinf/suap!13340))
- [[edu] corrige erro ao cadastrar professor prestador de serviço](cosinf/suap@8783e9df33f50e36607c1a5b6de56222f288a5b8) ([merge request](cosinf/suap!13344))
- [[edu] Corrigindo comando de importar professores.](cosinf/suap@c4dd5abac21d0eaf4b0238d49657304bf2b6df53) ([merge request](cosinf/suap!13337))
- [[edu] Evitando a geração de atividades curriculares de extensão indevidas](cosinf/suap@af883c139789eada558e54f8ed82339a55cf1df0) ([merge request](cosinf/suap!13336))
- [[djtools] Verificando se o socialauth tem foto ao tentar salva-la no suap.](cosinf/suap@af6e88f180a057332091aadecf328f0be5f4714c) ([merge request](cosinf/suap!13334))
- [[comum]: Corrige erro ao criar solicitação de atualização de foto utilizando foto do gov.br](cosinf/suap@17fe8ca754aab48b5f63769c70a7c7947b59702c) ([merge request](cosinf/suap!13328))
- [[djtools] Diminuindo o tempo de detecção de duplo clique para apenas um segundo.](cosinf/suap@537bf95ed76abfe6355955d7237df1204d603d1c) ([merge request](cosinf/suap!13329))
- [[patrimonio] Transfere o deferimento de inventarios do patrimonio para o celery](cosinf/suap@0541bda52836d766bb14fdf921a1893fb1ee2212) ([merge request](cosinf/suap!13327))
- [[edu] corrige erro ao verificar se usuário pode editar orientador de aluno de pós](cosinf/suap@92da3f7eb68e12b725def6d4a2b6de5e94799d84) ([merge request](cosinf/suap!13323))
- [[djtools] Corrige os parametros da função print_ para aceitar mais de um parâmetro.](cosinf/suap@c2922c591c643324441bc4735b8aedaec358df2e) ([merge request](cosinf/suap!13325))
- [[edu] registra a operação que chamou o método atualizar_situacao em aluno](cosinf/suap@5479a7ebd4ba70cacdb657510f4df4ad41a9af4e) ([merge request](cosinf/suap!13322))
- [[pgd] correção de bug ao adicionar solicitação de atividade](cosinf/suap@b9f4987f3b84e1cee2d4d8e084df7e970c17ad17) ([merge request](cosinf/suap!13321))
- [[edu] corrige erro na data de corte da auditoria SISTEC](cosinf/suap@f7a9a3d6d667ed590dcd268b3fae93aeacfdf72c) ([merge request](cosinf/suap!13320))
- [[edu] Removendo referências da pessoa física para o módulo do edu](cosinf/suap@e767d377980a42200135c766c8c7e833a11fc86f) ([merge request](cosinf/suap!13304))

### changed (8 changes)

- [[pesquisa] resolves #10185](cosinf/suap@93b861f753f32328fa64eb845a0e276a976181c7) ([merge request](cosinf/suap!13367))
- [[pesquisa] Alteração no menu.yaml do módulo pesquisa](cosinf/suap@a15711e310ae085cb30e0d77fd9208274a2a646b) ([merge request](cosinf/suap!13361))
- [[edu] Permite a exclusão do aproveitamento automático de disciplinas de...](cosinf/suap@497428207cdaddd9c75aa0ca482496c784e3e880) ([merge request](cosinf/suap!13359))
- [[ae] Avisa na tela quando não há auxílio eventual disponível para solicitação. resolves #10167](cosinf/suap@de1bc5ff66a8ab90664c5a9bf4fb41d8c596172f) ([merge request](cosinf/suap!13352))
- [[projetos_ensino] Permite envio de projeto sem caracterizar beneficiário. resolves #10166](cosinf/suap@ad5e8738937f2fb5dd1a434b692bddece9476bb2) ([merge request](cosinf/suap!13351))
- [[edu] Ajuste no cadastro de previsão de quantitativo de alunos após análise de Anna Katharina](cosinf/suap@d37686a5be7ca5fc76d4473cc2c51fe9e8a6b3c4) ([merge request](cosinf/suap!13339))
- [[projetos] Permite não cadastrar comprovação quando a atividade não foi atendida. resolves #10144](cosinf/suap@2afa7439b57db91af52643de7321aea8bf204685) ([merge request](cosinf/suap!13333))
- [[ae] Permissão de acesso aos relatórios de Caracterização Econômica para...](cosinf/suap@7028f4f85637c897b83afee213786769ee00c1d3) ([merge request](cosinf/suap!13332))

### added (5 changes)

- [[erros] Adiciona a possibilidade de o usuário no status aguardando feedback poder fechar o erro](cosinf/suap@5800e379dc640b4cd51b403bd5bf10566ebd3264) ([merge request](cosinf/suap!13348))
- [[comum] Adicionar criação e deferimento de sugestão de melhorias em minhas ações](cosinf/suap@ba81a06cd6f939109fe186145ab17f3bcc5d557f) ([merge request](cosinf/suap!13338))
- [[patrimônio] adição de tipo baixa](cosinf/suap@4559730895e1be32989248b6040427065dd3aa7a) ([merge request](cosinf/suap!13335))
- [[plan_estrategico] Demonstrativo Execução orçamentária](cosinf/suap@05626ab0960cd717dacba52278140f187a9cb7b4) ([merge request](cosinf/suap!13326))
- [[projetos_ensino] Configuração no edital para permitir que alunos de graduação...](cosinf/suap@a5c365293d40d36bd4cd98cbda3d05308ebb2c56) ([merge request](cosinf/suap!13305))

## 3.5.5 (2023-08-26)

### fixed (61 changes)

- [[tesouro_gerencial] Correção na importação dos relatórios](cosinf/suap@26498ddacae84e53a5e0bd42097ae736d234f5c5) ([merge request](cosinf/suap!13317))
- [[edu] Correção que impede a conclusão de assinatura de diploma digital de...](cosinf/suap@7360d51d1dc15c956bacfb12b007a6f8bb7ec4de) ([merge request](cosinf/suap!13316))
- [[demandas] Corrige validação para suspender demanda.](cosinf/suap@61ffb0f1c5b03d32a04b06f8ed83ef5ae1cce5ad) ([merge request](cosinf/suap!13318))
- [[pgd] Ajusta acesso das comissões a relatórios do PGD](cosinf/suap@4dbce26d9391cbde2e9689331e639d1321290d93) ([merge request](cosinf/suap!13311))
- [[ldap_backend] Removendo capture_exception dos comandos de sincronização do ldap](cosinf/suap@1400ebb9c0f879a756a0a01f5c19474b3584616e) ([merge request](cosinf/suap!13315))
- [[djtools] Remove prints em tasks e models](cosinf/suap@5a3133e36df41ef1167539e44c48094171041cf1) ([merge request](cosinf/suap!13314))
- [[ponto] Movendo para celery a geração de relatório xls de frequencias do setor](cosinf/suap@bc9b507d138324ec0173cbf6fca1038ce8a182ec) ([merge request](cosinf/suap!13313))
- [[ponto] melhora no desempenho em compensações específicas](cosinf/suap@f828efebc47fec41e9b8e1e91d8aa29d0e899643) ([merge request](cosinf/suap!13309))
- [[ae] Corrige campo de confirmar assinatura de termo de compromisso com senha. resolves #10102](cosinf/suap@7cb2fb2b49376e40fd06c76e2d3c4b5f56866e2d) ([merge request](cosinf/suap!13307))
- [[ponto] Convertendo relatório de frequencia por cargo emprego em uma tarefa...](cosinf/suap@160d7ab8a62eff546fbffda63c0d40fc7e7d77de) ([merge request](cosinf/suap!13301))
- [[comum] Corrigindo erro de herança dos formulários de configuração do suap...](cosinf/suap@92d2a6f8b8804a62c1b768df478fff7e850ce19c) ([merge request](cosinf/suap!13303))
- [[djtools] Problema no Verbose name do list_filter no admin](cosinf/suap@587c5dac285d8b81d9d36b12e150b4fbe0845094) ([merge request](cosinf/suap!13302))
- [[comum] Corrigindo adição de usuario externo](cosinf/suap@8191caccc9985ad60e69761db1d627e58495de05) ([merge request](cosinf/suap!13294))
- [[erros] permite que usuário se adicione e remova interesse de erros em situação final](cosinf/suap@a17bfacb348902774228b4ba5b41f6c37cf482ca) ([merge request](cosinf/suap!13296))
- [[projetos_ensino] impede prestador de serviço submeter projeto de ensino. Resolves #10085 #10086](cosinf/suap@00d222252ecb62a1560bd841260562b81c3501f4) ([merge request](cosinf/suap!13291))
- [[edu] ajuste no tratamento de erro no processamento de pedido de renovação de matrícula](cosinf/suap@15ebb3a6b99bc551f7b2a900917e48c2ee620e6d) ([merge request](cosinf/suap!13289))
- [[pesquisa] remove alertas na tela inicial de projetos cancelados/inativados. resolves #10059](cosinf/suap@3c82b6b2629f6d1df92677df1bcaea7d104625dd) ([merge request](cosinf/suap!13290))
- [[ponto] trata erro de acesso com vínculo de aluno no relatório de ponto](cosinf/suap@38d7ed3f232e6a2cf9f2136d361f0c01e879deea) ([merge request](cosinf/suap!13286))
- [Corrige bug que impedia edição do superusuario nos criterios de avaliação de editais de pesquisa](cosinf/suap@99aa9083e0ab1c902cdb2254404c9651737ae84b) ([merge request](cosinf/suap!13288))
- [[ponto] Corrigindo erro função tem_funcoes_no_periodo](cosinf/suap@9e20a6b69877c9bc21b6fc83fd2bc64aa2683dfc) ([merge request](cosinf/suap!13285))
- [[cursos] corrige erro na ativação de detalhamento de atividades de curso](cosinf/suap@634b303ff57e32e6abec89a83deaf4c59f5c23ba) ([merge request](cosinf/suap!13282))
- [Correção do layout da general-box](cosinf/suap@ff971234a44bc0b107950d9c4c31b90a2414ba60) ([merge request](cosinf/suap!13283))
- [[projetos] corrige erro na verificação se usuário pode submeter novo projeto](cosinf/suap@75b0edd201bb2943a60fa076006aba9768fa96d0) ([merge request](cosinf/suap!13280))
- [[edu] Permitindo que diretores acadêmicos informem o percentual de particação dos...](cosinf/suap@9800ccc36a43033fe1941f26e8315da3437f57d7) ([merge request](cosinf/suap!13279))
- [[edu] trata erro no pedido de renovação de matrícula](cosinf/suap@81ab195f69c9c30505d1ed66565fbfd71002751a) ([merge request](cosinf/suap!13276))
- [[eventos] Corrige bug na validação da data de atividade de evento e torna o campo fim do...](cosinf/suap@8a7597171585246d435b678dff94334616351dcb) ([merge request](cosinf/suap!13270))
- [[pgd] Correção de bug no cadastro de atividade no PDG](cosinf/suap@410abe26386002aa9258d4f8fbcf9ccf08ae0c90) ([merge request](cosinf/suap!13269))
- [[eventos] - Eventos issue 10034](cosinf/suap@a6c57802ce9e53175402a29939afdd3edd556c6c) ([merge request](cosinf/suap!13273))
- [[edu] Correção em layout de relatório de declaração de docência de professor](cosinf/suap@7c21df8f12a6ceaf44ce03ed1bff52ffe90afb71) ([merge request](cosinf/suap!13268))
- [[progressoes] Correção do cálculo de tempo final do interstício de progressão](cosinf/suap@e6b6287c6620668b14a7831a32f3ac9a4112e9e8) ([merge request](cosinf/suap!13274))
- [Corrige visualização tela de configuração por superusuario](cosinf/suap@2d429302d6627f4d6793fc5e0042e03ba5c356f9) ([merge request](cosinf/suap!13264))
- [[pesquisa] Correção de bug na emissão de declaração de participação em projeto de pesquisa](cosinf/suap@4f843aa7e271a2a66d743a50c2c9e49247e73b3d) ([merge request](cosinf/suap!13266))
- [[djtools] Permitindo o filtro mesmo com uma string no id](cosinf/suap@6163613c4cd6733b5eaee502d1d8783bc108f53b) ([merge request](cosinf/suap!13231))
- [[edu] corrige erro ao exibir Monitoramento de Fechamento de Período](cosinf/suap@f49a1fa539dcc9a3d352abd80105fccf9cac1ad7) ([merge request](cosinf/suap!13263))
- [[ponto] Controle de horas: correção "total_exigido_final" para um dado período](cosinf/suap@2d4bd5896e0894fc24724469b9e9406008e2683a) ([merge request](cosinf/suap!13255))
- [[projetos] correção ao listar projetos de extensão para usuário sem UO associada](cosinf/suap@562a48116fde7031391ebcf7b3d3904ef4eafe3c) ([merge request](cosinf/suap!13253))
- [[documento_eletronico] - Trata erro visualizacao documento digitalizado anexo simples](cosinf/suap@0dacbfb38e9466404cbd936e4ee89090128d1ff5) ([merge request](cosinf/suap!13250))
- [[ponto] - Corrige cadastro de débido externo](cosinf/suap@2f27078059087c08c526211cf14228f7240d7d65) ([merge request](cosinf/suap!13249))
- [Correção de bug na importação de edital quando a tag "aprovado-heteroidentificacao" vez vazia](cosinf/suap@7dc1a766305581f54af4c272233d8e37846891d0) ([merge request](cosinf/suap!13247))
- [[edu] corrige erro na exibição de diários não entregues](cosinf/suap@a057e31967e29e5f1b5e78b1de428a45a3fb053a) ([merge request](cosinf/suap!13246))
- [[progressoes] Ajustes diversos no módulo de progressões](cosinf/suap@98aa83148d27b0d7c61dd841bbc77e1bf89be6d3) ([merge request](cosinf/suap!13243))
- [[pgd] Correção no cálculo da carga horária não distribuida](cosinf/suap@1181407dec01fdf7f52bc5731ecb356e4e350f6f) ([merge request](cosinf/suap!13232))
- [[edu] Correção da aprovação e reprovação em lote](cosinf/suap@8b6c0c81d70c464eb3db3956211cc2849372b607) ([merge request](cosinf/suap!13233))
- [[djtool] Correção do valor do DateRangeListFilter ao alterar ou zerar ele num formulário](cosinf/suap@2aeac1081e4b835984b44fc186ea546190f3772d) ([merge request](cosinf/suap!13234))
- [[edu] corrige erro no filtro de diretoria quando usuário é None](cosinf/suap@fc6eb366a8a1fe86e6eccbb21c148083eef4c9c3) ([merge request](cosinf/suap!13237))
- [[edu] corrige erro no manager com filtro por diretoria](cosinf/suap@10be5581ca3d90b90e20b6f53c4ea02436a2a288) ([merge request](cosinf/suap!13236))
- [[tesouro_gerencial] Ajuste no comando de importação para processar usando...](cosinf/suap@edecc0ca43c2f00bbaa4bfb8e877a0000a131a57) ([merge request](cosinf/suap!13229))
- [[comum] Corrigindo o login de Prestador de Serviço sem Usuário Externo](cosinf/suap@831417a2698e58a4831e013f3ec644a63535f147) ([merge request](cosinf/suap!13223))
- [[documento_eletronico] Corrige bug de edição de documentos por prestadores](cosinf/suap@7732a0ce0cb541fbc3adbdc5df34b6ef57d6df37) ([merge request](cosinf/suap!13227))
- [[edu] corrige erro na verificação de pendência em estágio de aluno](cosinf/suap@2e37ec81fab232eb1794e142bd686a7f52dff274) ([merge request](cosinf/suap!13226))
- [[processo_eletronico] Corrige rotina de remover permissao em processo](cosinf/suap@90a2f7457f228e761268bc037b3b0eebadb24d2d) ([merge request](cosinf/suap!13222))
- [[comum] Mostrando o cronograma da folha para perfil de RH no dashboard, Closes #9973](cosinf/suap@6cecd43a1c2e9f64f30d7af8453528362eb8afbf) ([merge request](cosinf/suap!13218))
- [[erros] corrige erro no comentário automático de erro](cosinf/suap@7821d9680e24b7c6d57da2c2d6a78e6cf05a1923) ([merge request](cosinf/suap!13219))
- [[plan_estrategico] Buscar pelo código da ação ano](cosinf/suap@5239962e50a2eaa58118bf30bf1a5459b1389607) ([merge request](cosinf/suap!13213))
- [[progressoes] Correção do cálculo da data final.](cosinf/suap@6e1fad61720574b4559ac1482ad067203990ef37) ([merge request](cosinf/suap!13217))
- [[edu] corrige verificação de permissão para usuários de diretoria do tipo sistêmica](cosinf/suap@0b356f98819b7275254b5d43a13c578baf8b52dc) ([merge request](cosinf/suap!13214))
- [[ae] Ajusta verificação da oferta alimentação quando solicita refeição na...](cosinf/suap@6234da2d88a10dba18e44af9b7e4e0abbb8247c3) ([merge request](cosinf/suap!13211))
- [[rh] Ajustes na macro completa do extrator](cosinf/suap@9c1eceae16f7bd66240896b7be2a04971d3220b1) ([merge request](cosinf/suap!13209))
- [[plan_estrategico] Visualização de Classificação Institucional em dados orçamentários](cosinf/suap@1d624b6f1263157bebe83a26c07dd910df990f96) ([merge request](cosinf/suap!13208))
- [[comum] Corrige impedimento de agendar sala para o mesmo dia. resolves #9967](cosinf/suap@95fc81a9a04d1d93a9b94914bf0b85f8f157cc97) ([merge request](cosinf/suap!13207))
- [[rh] Ajustes no filtro de aniversariantes](cosinf/suap@d99b4a55042547c82fad66446a21c06cd68dc793) ([merge request](cosinf/suap!13206))

### changed (21 changes)

- [[pgd] Melhorias de usabilidade no pgd](cosinf/suap@5e820add4e5c33ae0eb95724c6b78dd70e67a4d6) ([merge request](cosinf/suap!13312))
- [[convenios] Faz pequenos ajustes no Admin de convênios](cosinf/suap@20e0e361f96b421a7fcb9aa5373218d0717716b2) ([merge request](cosinf/suap!13306))
- [[edu] Inclusão da foto do aluno no endpoint referente ao usuário autenticado na API do SUAP](cosinf/suap@2a1e6017b759dbcd12192c7ff2b546ea991c0600) ([merge request](cosinf/suap!13299))
- [[comum] Trocar o ajax do index do suap para carregar os quadros por coluna](cosinf/suap@ae5b5b8214db8e00b11da03959372de7be837003) ([merge request](cosinf/suap!13298))
- [[processo_seletivo] Permitir que usuários do grupo "Operador de Editais de...](cosinf/suap@e6c09a75c1fd8cada5bab53642f3f91831a1f8f3) ([merge request](cosinf/suap!13293))
- [[egressos] Permite que coordenadores de egressos e estágios visualizem dados pessoais de alunos](cosinf/suap@594538baa86a2aaab1b8b0dbdf9fba9c76a1c01d) ([merge request](cosinf/suap!13295))
- [[eventos] Criação de telas públicas separadas para inscrições, submissões e avaliações](cosinf/suap@d4d2eb5fe672ccef97bf7b685f8ed4b93bb0686d) ([merge request](cosinf/suap!13278))
- [Ajustes de usabilidade e correções de layout.](cosinf/suap@85b2cfe053b56ef942b3a9425033dfa8481dbc75) ([merge request](cosinf/suap!13277))
- [[documento_eletronico] Aposentado pode agora cadastrar documentos pessoais no documento eletronico](cosinf/suap@de454b3886d72a289f350596b827d32d15536c49) ([merge request](cosinf/suap!13238))
- [[contratos] - Ao gerar os termos do contrato força o compartilhamento do documento](cosinf/suap@fc6e1d9f56592066cf34993f81ea44fddb24fc16) ([merge request](cosinf/suap!13245))
- [[pesquisa] Permite submissão de projetos de pesquisa por alunos de Pós. Demanda 1479](cosinf/suap@6766af33b233cb15379219eb48a3a89c5329bba5) ([merge request](cosinf/suap!13240))
- [[projetos] Libera consulta aos projetos de extensão para todos os usuários. Demanda 1605](cosinf/suap@b030322b1d8b8ac05f67c9485199f39454b51bfa) ([merge request](cosinf/suap!13225))
- [[edu] Melhorias na sincronização do diário com o Moodle (inclusão da situação do...](cosinf/suap@13c682fcc80800c8905887fb506c89d3c4241e4a) ([merge request](cosinf/suap!13242))
- [[edu] Melhoria no relatório de quantitativo de alunos (Demanda 1610)](cosinf/suap@a51eefc66c31200bf5f4276a2769c1d4ba578bdb) ([merge request](cosinf/suap!13230))
- [[djtools] Retirando mensagem bad request nos testes](cosinf/suap@a059e96b050bc87d7acc94fcaa7201139efd75a2) ([merge request](cosinf/suap!13228))
- [[edu] Inclusão do campo "grupo_atuacao" no cadastro de Componente no módulo do ensino](cosinf/suap@02989d128b9677e614950adf9218be22b76c513d) ([merge request](cosinf/suap!13224))
- [[documento_eletronico] Alteração na vinculação automatica de interessado](cosinf/suap@53767fa4fb0ea3e6dddce12afcd7b217b8b2b452) ([merge request](cosinf/suap!13221))
- [[pgd] Ajusta formulários de pesquisa do RIT](cosinf/suap@c7d3e5acaf20cec504de7b94f957adf2aa3e63fe) ([merge request](cosinf/suap!13212))
- [[pesquisa] Ajustes no módulo da editora solicitados na demanda 1567](cosinf/suap@8eecbd0477d9fd363c69444f424fa8d2c4282364) ([merge request](cosinf/suap!13194))
- [[contrato] Adição de filtros na tela publica de contratos](cosinf/suap@d3563c08275e554c442f3215d2759eaf6a5f2370) ([merge request](cosinf/suap!13215))
- [[avaliacao_integrada] Ajustes no módulo avaliacao_integrada para atender as demandas AAI 2023.1](cosinf/suap@2855c03fcb2bb219490d93d9f8e374f1a8323d14) ([merge request](cosinf/suap!13196))

### added (8 changes)

- [[edu] Implementação do cadastro de previsão de quantidade de alunos necessário...](cosinf/suap@0e74660e5a8cf34229f3e2d5f26a640341f00b46) ([merge request](cosinf/suap!13310))
- [[pesquisa] Gestão dos Programas de Pós-Graduação Strictu Sensu](cosinf/suap@a0928c11f19aaa7ffc0d42ba8b81632874edd7db) ([merge request](cosinf/suap!13254))
- [[edu] Provendo feedback para usuário na sincronização dos diários com o Moodle](cosinf/suap@ef38c9438abbebdfde2116ce6cfeb856ead11d80) ([merge request](cosinf/suap!13275))
- [edu - Edu chamado Possibilitando a sincronização de toda a turma com o Moodle.](cosinf/suap@26d0566cad65015da741e849aacc0942737cc1fe) ([merge request](cosinf/suap!13261))
- [[djtools] limita a quantidade de termos pesquisado no campo search do admin](cosinf/suap@194e364638cd0e4a77a328b17d6e30461f3994cf) ([merge request](cosinf/suap!13259))
- [[centralservicos] Adicionar alertas de bases de conhecimento que precisam de correção ou supervisão](cosinf/suap@bac6efd11da0cfdcd3d320a8a8a44367ac56f5fb) ([merge request](cosinf/suap!13248))
- [[eventos] Demanda 1586: Submissões de Trabalhos para Eventos](cosinf/suap@c3ba8ea5840fee6e9b6a34a4954990ac025cb98a) ([merge request](cosinf/suap!13251))
- [[edu] demanda 1482 - Justificativas CENSUP](cosinf/suap@88f61c6c998e3d46fe140d7b19deb6c41c47476d) ([merge request](cosinf/suap!13205))
- [[edu] Implementação do cadastro de afastamento de sala de aula (continuação da...](cosinf/suap@b33a1c3f673db3d84565c116ec6efef3a098e742) ([merge request](cosinf/suap!13287))

## 3.5.4 (2023-07-31)

### changed (3 changes)

- [[documento_eletronico] Melhoria usabilidade assinatura](cosinf/suap@6741d89dd0bc2090c94168ede10e5efe3164a27d) ([merge request](cosinf/suap!13202))
- [[pgd] Melhoria de usabilidade para tela do Meu PGD.](cosinf/suap@ec45a27d0930690d3b84ef8954399dd8a981185f) ([merge request](cosinf/suap!13201))
- [[edu] ajustes no módulo de auditorias de ensino](cosinf/suap@aa8b455c011c74a9b8da5eeab5ebc2edad06537c) ([merge request](cosinf/suap!13181))

### fixed (19 changes)

- [[djtools][edu] corrige o comando clean_pyc e a migração de dados 0138 do edu](cosinf/suap@8d960fcd457dcc453637432d620c26c48485a31b) ([merge request](cosinf/suap!13204))
- [[edu] desfaz ajuste no educacenso](cosinf/suap@b0b774e61666e1871162e5f803aaa43b890a577f) ([merge request](cosinf/suap!13199))
- [[docker] Adicionando mais espaço de memória RAM para o container de banco de...](cosinf/suap@32ef5b8255fec87fec86c9ab8b7568e86bd8e832) ([merge request](cosinf/suap!13200))
- [[comum] Impede solicitar reserva de sala para data passada. resolves #9910](cosinf/suap@e4f26f7faf52055af37c24b2eef0b60c23dc6097) ([merge request](cosinf/suap!13198))
- [[djtools] Desvincula o request e o user do threadlocals ao finalizar uma task do celery](cosinf/suap@2fd600d68985cabf701881927ae75bad91adc5f2) ([merge request](cosinf/suap!13188))
- [[djtools] Refatorando get_app_context para evitar exceptions de origin não encontrado](cosinf/suap@c901b9b0218f3b4962a2ea93c040603396e31396) ([merge request](cosinf/suap!13192))
- [[edu] corrige erro na emissão de certificado de conclusão de módulo](cosinf/suap@c0ed3ad37e3fa9c735569172a0cf429f389d3293) ([merge request](cosinf/suap!13191))
- [[pdi] Mudança nome da app PDI para Contibuição do PDI](cosinf/suap@c399d39a82ebc3117f64da29b06509aa6f74e16a) ([merge request](cosinf/suap!13189))
- [[demandas] Verificando o status de ambiente de homologação antes de ser automaticamente destruido](cosinf/suap@fd84387a98a556fc7bf968f4839c786c4eb5c8f1) ([merge request](cosinf/suap!13190))
- [[comum] Ajuste no command ativar_usuarios_externos.py para não inativar ...](cosinf/suap@edd19fcb46082e5e39ce46fad635c17ee15c0c71) ([merge request](cosinf/suap!13182))
- [[patrimonio] Permite atualizar carga contabil](cosinf/suap@271787b2f2721031b15d3666e682e192fbcd3b80) ([merge request](cosinf/suap!13187))
- [[catalogo_provedor_servico] Adiciona verificação de id do candidato vaga ao...](cosinf/suap@e543e9ed7052f5cabef17a4bd69684631f0cccf4) ([merge request](cosinf/suap!13184))
- [[edu] corrige erro de validação no cadastro de sábado letivo](cosinf/suap@7d9c12a5296e173ac20f3e89e3b0749ef41ebb62) ([merge request](cosinf/suap!13183))
- [[patrimonio] Exibir no detalhamento do inventário apenas requisições aprovadas](cosinf/suap@9d67aaa25f739c6d4879b41066267ddd1950a549) ([merge request](cosinf/suap!13175))
- [[pgd] Ajusta cálculo da CH prevista](cosinf/suap@0237c1719325ab6eebc8216aa399f644f04a80e9) ([merge request](cosinf/suap!13174))
- [[comum] Corrige queryset do campo de setor ao adicionar ocupação do prestador. resolves #9815](cosinf/suap@0be27e22df422eebd7909b1fb3e049bd02a8b094) ([merge request](cosinf/suap!13171))
- [[patrimonio] Acesso a todas as requisições de transferências](cosinf/suap@d5ab8e492a6f123a51379d2cbe7943bbe321299e) ([merge request](cosinf/suap!13172))
- [[enquete] Corrige o tipo de setor do publico para o caso de funcionarios e prestadores de serviço.](cosinf/suap@9d25bdf55fe59bdbdcae86a3964714969fef51a6) ([merge request](cosinf/suap!13170))
- [[edu] Migrando edu.RegistroEmissaoDiploma e edu.ParticipanteEvento para utilizar Vinculo](cosinf/suap@553fe04ca8131c414a4178bda31ec797db1d895a) ([merge request](cosinf/suap!13142))

### added (5 changes)

- [[rh] Implementação do filtro de setor na listagem de aniversariantes. Closes #9948](cosinf/suap@ccab16eb8b17a52dc818104c30f8d9bb04d6b2d4) ([merge request](cosinf/suap!13197))
- [[pgd] Adicionando Formulário de dados na entrega e avaliação do RIT](cosinf/suap@c78aba5ad23b4b8c21a8a969b105c3366973fb9d) ([merge request](cosinf/suap!13154))
- [[pesquisa] Notifica os membros do grupo 'Integrante da Editora' sempre que uma...](cosinf/suap@2b4ca33ded84ac098c7249744d2220208760316b) ([merge request](cosinf/suap!13185))
- [[eleicao] Permite voto branco e nulo nas eleições](cosinf/suap@0b20233e548c07ebc38c823f60fe0fca949f40f0) ([merge request](cosinf/suap!13180))
- [[processo_eletronico] Adicionando um aviso para o caso do solicitado não adicionar nenhum documento](cosinf/suap@3b6eebfd2324197bc5d9681b7ba76a613fe5fb91) ([merge request](cosinf/suap!13173))

## 3.5.3 (2023-07-24)

### fixed (27 changes)

- [[rsc] Verifica se o usuário está autenticado, antes de verificar se é dono.](cosinf/suap@b6d63994811ad9a8f7f472e32a937e701e663cdd) ([merge request](cosinf/suap!13169))
- [[djtools] Reinicia o container do nginx ao rodar o comando index.sh no ambiente de homologação](cosinf/suap@9153d250c86a345350fc93fb09d75f51325daf1b) ([merge request](cosinf/suap!13168))
- [[edu] Correção de bug que não exibe o nome do membro da banca de TCC com assinatura](cosinf/suap@3fcc44ea8245d572bb4f9058beed0dbc63967bca) ([merge request](cosinf/suap!13165))
- [[edu] corrige erro ao certificar/aproveitar disciplina](cosinf/suap@a1c142897082c9bfe45b4ea04faa642f1c18af0e) ([merge request](cosinf/suap!13162))
- [[edu] Corrigindo a exibição do nome do membro da banca de TCC com assinatura](cosinf/suap@eba2a1164b5655abd5f86a11d12858509d4f13ee) ([merge request](cosinf/suap!13163))
- [[pgd] Adicionando verificação se o form de aprovação de tarefas RIT existe.](cosinf/suap@1745d0276ad5ec74b0ce862cd91ef6497b1671dc) ([merge request](cosinf/suap!13164))
- [[edu] corrige erro na geração de ata eletrônica](cosinf/suap@853b4f7904194a4bcf05060cfee13c69593c42e1) ([merge request](cosinf/suap!13161))
- [[edu] corrige contabilização da CH da curricularização de extensão de diários...](cosinf/suap@3df686397e668495e66ec58d717988615d85f4aa) ([merge request](cosinf/suap!13160))
- [[edu] Corrige o histórico para alunos que não possuem data de conclusão de...](cosinf/suap@33384c5fe8c82f13cc8b48a7cca2cfb579c24d45) ([merge request](cosinf/suap!13157))
- [[edu] corrige erro ao gerar declaração de coorientação em projeto final](cosinf/suap@4d8394efdfef33f033572b20492fcd2bfdf4c905) ([merge request](cosinf/suap!13156))
- [[comum] Desabilita a edição de CPFs, Passaportes e nacionalidade de usuários externos.](cosinf/suap@135353644095574694a11e90061c23bfb988bc1a) ([merge request](cosinf/suap!13153))
- [[edu] corrige erros na anonimização de dados do aluno](cosinf/suap@d1cb83602bdc18bd1c2e52d8ca5eb140f9e7249a) ([merge request](cosinf/suap!13152))
- [[djtools] Ajuste na configuração do redis do healthcheck](cosinf/suap@b261cb2177cce7a42c7ce0b08daa4aa8fe98d3ec) ([merge request](cosinf/suap!13155))
- [[orcamento] Correção Busca Nota de Empenho](cosinf/suap@9ea00c5fab5208522fe8c34947940bbd6c99b7da) ([merge request](cosinf/suap!13147))
- [[saude] correção na ordenação dos itens do plano de tratamento de um atendimento odontológico](cosinf/suap@e5fea7a0b510a4fde9966739b23fa42da00f54a8) ([merge request](cosinf/suap!13127))
- [[progressoes] Retirando botão de assinar após assinatura na tela de assinaturas](cosinf/suap@de06cf6bc53da93ad2d3af12fd8f9e9d931e1ca2) ([merge request](cosinf/suap!13148))
- [[edu] Correção de bug relacionado aos dados de reconhecimento de curso de...](cosinf/suap@6a3871d54037c55c4c2e5176ce063cced1528a2f) ([merge request](cosinf/suap!13143))
- [[comum] Correções de layout e usabilidade](cosinf/suap@2d986a7353134f72fee37cfb1ebe8fb780186c2a) ([merge request](cosinf/suap!13146))
- [[edu] Verifica se o PDF do diploma é válido antes de assinar](cosinf/suap@263df68b9a296c54be569273d17615dcf18d5c82) ([merge request](cosinf/suap!13145))
- [[edu] corrige erro no envio por email de mensagem do comunicador](cosinf/suap@0deff1852602df1c35e5b1ab5bf1da145bd5c8ce) ([merge request](cosinf/suap!13144))
- [[edu] corrige erro na exibição de dados anonimizados para coordenador de curso](cosinf/suap@5c012fb1ad9763a530fa8f1ea8560dfa05649f37) ([merge request](cosinf/suap!13140))
- [[edu] Correção de bug referente a emissão de diploma digital de alunos do Q-Acadêmico](cosinf/suap@972578e3a55fcf24e814cd70ff2e2a7b2719d1ac) ([merge request](cosinf/suap!13136))
- [[comum] Correção da legenda do calendário administrativo](cosinf/suap@cb88884b9db85aaa6667dbcac1384b0278c3ff21) ([merge request](cosinf/suap!13134))
- [[edu] corrige erro na verificação de modalidade de curso importado do qacademico](cosinf/suap@7789b717a504bf2c204bc4415146e9c536fa1c7b) ([merge request](cosinf/suap!13132))
- [[edu] adiciona sanitização na descrição dos tipos de atividade complementar](cosinf/suap@d98797a3e9fbecbaede2a3836ca64e2491418d48) ([merge request](cosinf/suap!13131))
- [[edu] Adiciona filtros para exibir apenas horários de professores que o aluno...](cosinf/suap@5345fc86f50d572d3b050ffda15aa1f86d472cc9) ([merge request](cosinf/suap!13129))
- [[gestao] Adicionando verificação de usuário autenticado ao tentar recuperar o período de referência](cosinf/suap@c20c1fe3ddbea6c88a61ffdd193c971fa6235164) ([merge request](cosinf/suap!13130))

### changed (7 changes)

- [[erros] ajusta fluxo de alteração de labels em issues de erro no gitlab](cosinf/suap@57440e3db13bc3874a18e06618a0251ef400d6fd) ([merge request](cosinf/suap!13167))
- [[edu] Ajuste na implementação do cadastro de sábado letivo após observações...](cosinf/suap@432729c741a4f255b4fb70a65b629e414cc55031) ([merge request](cosinf/suap!13158))
- [Ajustes no módulo de avaliação integrada para incluir helptext no questionário de avaliação](cosinf/suap@f130ed12d4d80c192285d36720576dde03b36bed) ([merge request](cosinf/suap!13159))
- [[edu] Melhorias na matrícula de alunos estrangeiros.](cosinf/suap@c55becf0e55ce4735c5c754de0de5207b094cafa) ([merge request](cosinf/suap!13141))
- [[estagios] exibe para o aluno o botão de adicionar relatório apenas quando houver período aberto](cosinf/suap@5efa202a285bb8e0d3cf5706401de0577a7e1f5b) ([merge request](cosinf/suap!13137))
- [[edu] Melhorias no calendário acadêmico para possibilitar o cadastro de...](cosinf/suap@1a682acba6e6a0bd784050da7bfd99c87395d8ee) ([merge request](cosinf/suap!13135))
- [[saude] Altera alguns aspectos dos registros de atividades administrativas e...](cosinf/suap@de84b5a03383bcecafc1c87ed9e00879703e572e) ([merge request](cosinf/suap!13104))

### added (4 changes)

- [[ae] Exibe dados de inscrição e caracterização do aluno ao adicionar...](cosinf/suap@4aabdd85402c6537bd70a28427f1be291a74140f) ([merge request](cosinf/suap!13166))
- [[pgd] Corrige os cálculos de horas considerando o saldo externo e a...](cosinf/suap@b8796c41313bd02457b6240807414567ba26155c) ([merge request](cosinf/suap!13138))
- [[projetos_ensino] Implantação do módulo para gerenciamento de projetos de ensino](cosinf/suap@33235d0e2cc65a27727092742152afdd1493dd54) ([merge request](cosinf/suap!13149))
- [[edu] permite o cadastro de CH de extensão em Matrícula Diário Resumida](cosinf/suap@80b932cc3c9c0a12b2b2d1d500e518c4ff256907) ([merge request](cosinf/suap!13150))

## 3.5.2 (2023-07-17)

### added (4 changes)

- [[rh] Adiciona na tela do servidor o tempo no serviço público](cosinf/suap@0a34786df19be89cbb883a3d5ed4ed025b8a6f99) ([merge request](cosinf/suap!13125))
- [[edu] Ajuste na matrícula vínculo para impedir que o aluno fique com tal...](cosinf/suap@da5d6e6fde8b15084e0b241c15d50763a0dc3b5f) ([merge request](cosinf/suap!13124))
- [[ponto] Controle de horas / totais de um período: acrescentando o total de débito externo lançado](cosinf/suap@aefe0d64bc683582e007aedb425d8621b41d30fa) ([merge request](cosinf/suap!13112))
- [[edu] Monitoramento/previsão de força de trabalho no ensino](cosinf/suap@082f5b95b68f5fd2756285b8d1a38828d82e249a) ([merge request](cosinf/suap!13107))

### fixed (22 changes)

- [[processo_eletronico] Corrige assinatura em solicitação de assinatura com tramitação de processo](cosinf/suap@7cee552b8a8f969af7afaf3d463e2a7b914f5d48) ([merge request](cosinf/suap!13126))
- [[edu] Adicionando grupos na listagem de alunos](cosinf/suap@9f810f1950e1ef30e3f01b80c27de997ea844964) ([merge request](cosinf/suap!13123))
- [[comum] Corrige a edição do usuário externo.](cosinf/suap@bc71a3b9739646488429edf82f301abcd4902bab) ([merge request](cosinf/suap!13120))
- [[ae] corrige erro ao invalidar comprovante de participação](cosinf/suap@bb98f647b118564c576467e0ad44799ddac82f41) ([merge request](cosinf/suap!13122))
- [[progressoes] Corrigindo a verificação se usuário é do RH no processo de avaliação de servidor.](cosinf/suap@caf7d9439228d0d95c3eb48d2fd3b34c3a11c7b9) ([merge request](cosinf/suap!13118))
- [[ae] Altera nomenclatura do admin e do menu de Histórico de Suspensões](cosinf/suap@7b87ef4ff48a4f56cd4f2c0eba296e896ee73921) ([merge request](cosinf/suap!13121))
- [[cursos] Adiciona verificação de usuário logado ao tentar adicionar horas trabalhadas](cosinf/suap@a6914b1eca6c6e0d5f0581d4b0835eee5c52f7d5) ([merge request](cosinf/suap!13119))
- [[plan_estrategico] Ajuste na exibição dos indicadores para campus que não tem variável associada](cosinf/suap@7f74e0727866d74785edca73ce500fb5491fed86) ([merge request](cosinf/suap!13114))
- [[portaria] Adicionando verificação de acesso ao tentar cadastrar chave wifi](cosinf/suap@3686a74eeca453f131ce4fb83a242b32463353e6) ([merge request](cosinf/suap!13117))
- [[edu] Corrige a verificação de idade no get_ext_combo_template do aluno](cosinf/suap@1d1017996aafd063f4fc2b423cd8dcd4ee3b5c7d) ([merge request](cosinf/suap!13116))
- [[djtools] Adiciona uma view de healthcheck](cosinf/suap@75d58274d67d519005996b75e561de115eebae04) ([merge request](cosinf/suap!13115))
- [[cursos] chamado 301100: desativar o detalhamento das horas no caso de...](cosinf/suap@169699851330a92f0ef9054dd9cb8c160938d2e4) ([merge request](cosinf/suap!13113))
- [[eventos] Define campo data da atividade como obrigatório](cosinf/suap@2eb97b516bb4e726877e6d504278f5bdc7f24e1e) ([merge request](cosinf/suap!13111))
- [[djtools] Serializa todo o dicionário a ser enviado para o serviço de impressão de pdfs](cosinf/suap@c2bcff2c761bb663cf0168e4d81b81c100b8ec18) ([merge request](cosinf/suap!13108))
- [[ae] Seleciona corretamente as participações que devem ser consideradas ao solicitar comprovantes](cosinf/suap@188e7502c4108827555c2ecbc33fe71fc530849e) ([merge request](cosinf/suap!13105))
- [[documento_eletronico] Correção da solicitação de compartilhamento de documento digitalizado](cosinf/suap@08e3884be7eceeec52e5b4776134d8cc1c63b823) ([merge request](cosinf/suap!13103))
- [[pgd] Corrige a edição de Auxiliares de Planos de Trabalho Setoriais](cosinf/suap@6bd1af8fedab61b0da089920660db91eedf27c5f) ([merge request](cosinf/suap!13102))
- [[plan_estrategico] Correção form do plano concluído](cosinf/suap@9cbdd3a6793916037dfd5a4b485c4f6316b29173) ([merge request](cosinf/suap!13101))
- [[djtools] Corrige o envio de notificações com objetos associados com descrição...](cosinf/suap@e98bb80d40b46c2adeeff1b5a09701454c00fe98) ([merge request](cosinf/suap!13100))
- [[plan_estrategico] Ajuste Filtro de unidade Organizacional no farol de desempenho](cosinf/suap@75cd0e765b9d296e0d6a71212fe14ba36eca4a4b) ([merge request](cosinf/suap!13099))
- [[ae] Corrige erro do botão de ativar/desativar edital não aparecer. resolves #9807 #8991](cosinf/suap@635b1c352dc2166e843e7535555fa9740c09063b) ([merge request](cosinf/suap!13096))
- [[pesquisa] Impede que ColaboradorExterno participante de projeto seja deletado pelo admin](cosinf/suap@6e4d150fc19941355d238c149921682ae8a8b6c0) ([merge request](cosinf/suap!13094))

### changed (4 changes)

- [[documento_eletronico] Impede assinatura balizadora por aluno e libera nas demais assinaturas](cosinf/suap@a2e9d5f95031ad54720706b302a543289a704425) ([merge request](cosinf/suap!13110))
- [[comum] Exibindo apenas certificados com data de validade virgente no momento da...](cosinf/suap@224d5f1d0b6adc6d74180d603981733821497e28) ([merge request](cosinf/suap!13109))
- [[avaliacao_integrada] Inclusão de atributos cadastrado_em e cadastrado_por nos...](cosinf/suap@30e51a56b1f88d446e0ee2556d5f6a4d959317fa) ([merge request](cosinf/suap!13106))
- [[edu] Adicionando grupo Membro ETEP na listagem completa de alunos](cosinf/suap@95c70558b486f423ec4084772ae4f82ac8eef582) ([merge request](cosinf/suap!13098))

### removed (1 change)

- [[djtools] Removendo a parte de produção do projeto do suap](cosinf/suap@3714326a952fd0aab0536e0f814aa1587dd0ee13) ([merge request](cosinf/suap!13095))

## 3.5.1 (2023-07-10)

### fixed (22 changes)

- [[comum] Corrige erro de Prestador de Serviço inativo após adicionar ocupação.](cosinf/suap@e0c4d6235027b7eec7a132653cae0188975343ca) ([merge request](cosinf/suap!13092))
- [[pesquisa] Valida tamanho máximo do campo 'passaporte' no cadastro de...](cosinf/suap@09c1743bcffbc5938b8509666d06fbe3e3a8c790) ([merge request](cosinf/suap!13090))
- [[cursos] Permitindo que o usuário possa preencher um detalhamento de atividade...](cosinf/suap@d5377f6903d8009e94b129dade408975c7afc1e2) ([merge request](cosinf/suap!13091))
- [[edu] Corrige erro envio de mensagem edu](cosinf/suap@81a54ce029bac200c77e3bd7b68bcc8192100603) ([merge request](cosinf/suap!13086))
- [[eventos] Corrige o upload de modelos de certificados de eventos](cosinf/suap@ebcdc7779d68318029510c327d1bd7f9db7d16e1) ([merge request](cosinf/suap!13089))
- [[plan_estrategico] Correção método pode_avaliar do modelo RequisicaoRealocacao](cosinf/suap@1f768fbe9ae5d3b50a3f95d7f427f199213d2d0c) ([merge request](cosinf/suap!13088))
- [[edu] corrige erro de validação no cadastro de aula quando % mínimo de aula EAD habilitado](cosinf/suap@f63df4cd8fc0f0c1111a054d72083deb21427c9d) ([merge request](cosinf/suap!13085))
- [[comum] Adicionando verificação de CPF válido ao tentar cadastrar um usuário externo.](cosinf/suap@9deb9c04fe14b17190c16eb6b3c678e86f3f17c0) ([merge request](cosinf/suap!13084))
- [[djtools] Corrigindo MultipleModelChoiceFieldPlus para tratar escolhas vazias.](cosinf/suap@cb84cc4cadbfd7c3582c458fb74a92f8c2799408) ([merge request](cosinf/suap!13083))
- [[processo_eletronico] Adicionando verificação de existencia de codigo de...](cosinf/suap@389fc5836ad580015fa9cb58ea7f7c672b4adb7d) ([merge request](cosinf/suap!13082))
- [[edu] Adiciona verificação de estrutura na matriz do curso ao tentar...](cosinf/suap@781dbb8c7695b9de19bd07569a977d856823b2cc) ([merge request](cosinf/suap!13081))
- [[pgd] Corrige a listagem do admin de AtividadeSolicitacoes](cosinf/suap@21da3fa58eebeb255cfe9019840df2d768ee1b7c) ([merge request](cosinf/suap!13080))
- [[processo_seletivo] Corrige bug da importação da heteroidentificação](cosinf/suap@e64dd097713ca6392ee2e9bdd2da9eb5b1d7d82e) ([merge request](cosinf/suap!13079))
- [[ae] Corrige verificação se aluno já é participante. Resolves #9773](cosinf/suap@2be782ebebf55e61288c9b61cb9d2136a3df8427) ([merge request](cosinf/suap!13078))
- [[docker] Adicionando um volume para a pasta /tmp no container de impressão de pdf](cosinf/suap@20bcc737ca1c9412c77dd9681b592d45b22fc9a3) ([merge request](cosinf/suap!13075))
- [[ae] Corrige erro ao checar ofertas semanais durante solicitação de refeição. resolves #9764](cosinf/suap@0e0392fde3d69a2e813abad58bd5889dee5a747a) ([merge request](cosinf/suap!13074))
- [[ae]  Salva data informada pelo assistente social ao efetuar inscrição. resolves #9737](cosinf/suap@697ccf14f72cf8b9f95335b306beb9348f2ac2a1) ([merge request](cosinf/suap!13072))
- [[contracheques] Correção da tabela de retribuição de titulação. Closes #7147](cosinf/suap@a556f1c646f50114cc2fbde0775315113b92a110) ([merge request](cosinf/suap!13073))
- [[saude] Corrige a previsualização de documento de prontuário quando nenhum tipo é informado](cosinf/suap@8fff7bde28a58a74ac85f35dfe14a571ba05a23f) ([merge request](cosinf/suap!13067))
- [[documento_eletronico] Corrigindo problema ao gerenciar compartilhamento de setores](cosinf/suap@7379cf9f19ccdaaf5284c4123738131c8eb10902) ([merge request](cosinf/suap!13071))
- [[comum] Corrigindo problema ao selecionar vínculo ao tentar realizar login via govbr](cosinf/suap@40d259fc1179a00bb1eaed7dd4ec74c28517d948) ([merge request](cosinf/suap!13069))
- [[edu] Corrige a replicação do calendário acadêmico quando a descrição é muito longa.](cosinf/suap@b1c168e86f90f5c9081b37eef561aade67c3823b) ([merge request](cosinf/suap!13068))

### changed (3 changes)

- [[projetos] Permite o cadastro de mais de um registro de gasto para um desembolso. Demanda 1588](cosinf/suap@e0ba20322f2c104cf37383993e0fb3b0859de116) ([merge request](cosinf/suap!13093))
- [[avaliacao_integrada] sustentação evolutiva para atender a demanda da autoavaliação 2023.1](cosinf/suap@02aa63e6a3309ef66215a7454c2228da2dd1f406) ([merge request](cosinf/suap!13087))
- [[edu] Adicionando regras de anonimização na listagem de alunos](cosinf/suap@ff461ae006120001d2dd72909e37e695183d81c8) ([merge request](cosinf/suap!13070))

## 3.5.0 (2023-07-02)

### fixed (19 changes)

- [[edu] Adicionando tipo no método buscar_componentes_por_abreviaturas_e_siglas...](cosinf/suap@3e241087f290f625bc67e0626605b227c5eafb6f) ([merge request](cosinf/suap!13065))
- [[saude] corrige visualização erro documento prontuário](cosinf/suap@f7842530c3f6cd353875b0c0a2b45f29f253cff9) ([merge request](cosinf/suap!13063))
- [[processo_seletivo] Adicionando verificação de existencia do webservice ao...](cosinf/suap@a3d00404a9e89f375d99c05af8687c13b35db758) ([merge request](cosinf/suap!13061))
- [[progressoes] Corrige assinatura da avaliação de progressão quando o usuário...](cosinf/suap@d163f53ae72ec630c7d78130d24525b3ca862d34) ([merge request](cosinf/suap!13062))
- [[encceja] Correção de erro ao imprimir certificado do encceja](cosinf/suap@cccea06f199594f8941c113318dcf74c648098ae) ([merge request](cosinf/suap!13060))
- [[edu] corrige erro na busca de naturalidade na consulta aos dados da receita federal](cosinf/suap@7d05783a62e8a615231420705026e0a359d77f01) ([merge request](cosinf/suap!13058))
- [[patrimonio] Ao deferir requisição mudar a sala apenas dos itens aprovados](cosinf/suap@9bcb0ea61497071835c77f7ad555895e4dc3994d) ([merge request](cosinf/suap!13056))
- [[pesquisa, projetos] Corrigindo permissão de emissão de declaração de participação.](cosinf/suap@8acfc7bfa8632f31f00a6e89a9865a1718e8007e) ([merge request](cosinf/suap!13055))
- [[professor_titular] Correção dos processos de professor titular com situação...](cosinf/suap@43501addf3be897e0366f74f333b9c14b1659624) ([merge request](cosinf/suap!13051))
- [[plan_estrategico] Correção nos comandos para verificar se existe a variável para a uo cadastrada](cosinf/suap@e7275528ceb740d377389c3e06f8aaead21ba465) ([merge request](cosinf/suap!13050))
- [[documento_eletronico] corrigindo rotina de tem_identificador_definitivo para...](cosinf/suap@2a0006e7c3641a496a0a608902dd65851df7e2b7) ([merge request](cosinf/suap!13047))
- [[cursos] correção de bug em pesquisa de cota anual do servidor](cosinf/suap@5d49d7db66b9d81403eac8ff7838398813fd4f78) ([merge request](cosinf/suap!13046))
- [[edu] corrige erro ao gerar relatório de professores](cosinf/suap@a20de9ee7811384693b016c2608dd350afba5b9f) ([merge request](cosinf/suap!13044))
- [[edu] corrige erro na verificação se matrícula em diário pode ser cancelada](cosinf/suap@eee893729a31e72a3f0887bf3fea192c69ebe16b) ([merge request](cosinf/suap!13042))
- [[documento_eletronico] - Corrige visualização das portarias](cosinf/suap@5710bbac32bcb50d11b5a1197c3ba69b9f8911b0) ([merge request](cosinf/suap!13033))
- [[ae] Corrige bug de totalizadores no relatorio semanal de refeitorio](cosinf/suap@ed9ae20bc814ad2e70d6526794c987bd5f4db020) ([merge request](cosinf/suap!13039))
- [[contratos] Adicionando try except pass em migration que só são importantes para SUAP/IFRN](cosinf/suap@ea325e07c5e161b037cbdb07af6857b7a99bef54) ([merge request](cosinf/suap!13038))
- [[edu] ajustes no tratamento de dados na exportação do educacenso](cosinf/suap@fdc08549b7d35450cc5e758d6fda875adc93db0f) ([merge request](cosinf/suap!13036))
- [[edu] corrige erro ao gerar histórico final de aluno com ensino médio integralizado](cosinf/suap@e26e60017894f4442caec28c556e7e72ef43d2fc) ([merge request](cosinf/suap!13032))

### changed (9 changes)

- [[progressao] Ajuste no tempo que permite criação do processo. Closes #9748](cosinf/suap@94b763737ad19d9474df400fb0851734c4cabb85) ([merge request](cosinf/suap!13064))
- [[estagios] Adiciona na listagem de Estágios a coluna "Situação do Convênio"...](cosinf/suap@f9dfe8731da19890a01b695ee0da8761c30b8c88) ([merge request](cosinf/suap!13059))
- [[edu] Remodela a planilha de importação de componentes para matriz](cosinf/suap@4adca25324b27548d7b441508ed74351c331879d) ([merge request](cosinf/suap!13057))
- [[cursos] revisão na ativação do ciclo de preenchimento das horas trabalhadas](cosinf/suap@98b67b33dfe914bac40085b5fb66a5f7f3f0b532) ([merge request](cosinf/suap!13053))
- [[plan_estrategico] Visualização para todos os usuários do Plano de Atividades](cosinf/suap@f82b3128b99cb51becabc97b2b32bc3051861914) ([merge request](cosinf/suap!13045))
- [[comum] Redirecianando para a tela do job ao criar/atualizar ambiente de homologação...](cosinf/suap@b98d8ff3b787850fe1189f67e360ad32f4fe269d) ([merge request](cosinf/suap!13040))
- [[pgd] Realiza a migração de Pessoa Física para vínculo no PGD](cosinf/suap@5954012eb5ddc6a84c2b64ae7cd53cb363d7d591) ([merge request](cosinf/suap!13041))
- [[cursos] Ajuste em templates](cosinf/suap@dae36d10765edecb4d71a8d604ae7f51f5c67126) ([merge request](cosinf/suap!13037))
- [[cursos] ajuste na notificação após detalhamento das horas](cosinf/suap@252715c7050dfd34cc65f099eb6d2aaa910133e9) ([merge request](cosinf/suap!13035))

### other (1 change)

- [[djtools] Exibindo descrição amigável quando uma opção inválida é escolhida no campo de...](cosinf/suap@f62870e582d7cca129cb24b11f985d807e0275ed) ([merge request](cosinf/suap!13054))

### added (9 changes)

- [[documento_eletronico] Trigger para evitar registros duplicados](cosinf/suap@65613493eecb93028967c7d2b68e08f7ed25d8f3) ([merge request](cosinf/suap!13012))
- [[estagios] Acesso aos Dados Pessoais dos Alunos ao Coordenador de Estágio.](cosinf/suap@c74f0045e9334c49196c753c95c11374f851ab0b) ([merge request](cosinf/suap!13052))
- [[edu] Correção de bug na contabilização da carga horária de créditos especiais para...](cosinf/suap@676f7869ca076bd855a3deea9a97b657dfe10a37) ([merge request](cosinf/suap!13049))
- [[documento_eletronico] Adicionando checagem para impedir documento com...](cosinf/suap@6b7c507827043f179f97407112db7cb3574ba2f7) ([merge request](cosinf/suap!13003))
- [[patrimônio] Exclusão de Item de Conferência de Sala](cosinf/suap@b16c8e250efa1446f85d5e99d0b7f5fe230f9e4d) ([merge request](cosinf/suap!13043))
- [[ae] não permitir demandar refeições em dias sem ofertas](cosinf/suap@9332346ed2292a4f109afc9817491cf311d5de94) ([merge request](cosinf/suap!13011))
- [[eventos, clipping, enquete] Inclusão da descrição nos grupos da comunicação social.](cosinf/suap@2181ecc0df29df1fc773cae01248eafd62ca720b) ([merge request](cosinf/suap!13031))
- [[eventos] Enviar email de solicitação de presença para participantes](cosinf/suap@774370f841dc4900916ab5978f9eafe1893cd2d5) ([merge request](cosinf/suap!13034))
- [[gerenciador_projetos] Melhorias para a interação com as tarefas no Módulo de...](cosinf/suap@97bc6ec51783ab8bc3a74115b12c673834125285) ([merge request](cosinf/suap!13029))

## 3.4.1 (2023-06-26)

### fixed (37 changes)

- [[api] Adicionando permissão para que o próprio usuário possa excluir sua própria aplicação.](cosinf/suap@e32c2a1e4875c5039cc77b94960e468d06546a0c) ([merge request](cosinf/suap!13030))
- [[comum] Correção de bug na conversão de arquivo .docx para .pdf](cosinf/suap@4209d3ba171d786cf9c065bfe0c369f63f318565) ([merge request](cosinf/suap!13021))
- [[djtools] Adicionando verificação de existência de cpf antes de tentar validar](cosinf/suap@0a3ca98d36fe253990f7f18541ed0a968974c205) ([merge request](cosinf/suap!13026))
- [[docker] Adiciona pasta de volume ao instanciar container do projeto...](cosinf/suap@9b837daed91b1bf91403e34fa7477e1ca17bf671) ([merge request](cosinf/suap!13028))
- [[projetos] Corrige a verificação se o usuário é técnico ao editar um projeto de extensão](cosinf/suap@d21d11605b025e8f7ed387e7614d904b120ff5f5) ([merge request](cosinf/suap!13025))
- [[catalogo_provedor_servico] Tratando identificador inválido de função serializada](cosinf/suap@73179cf8ce8f48a7b918cbaaa18dc5e2604c0636) ([merge request](cosinf/suap!13027))
- [[ae] Corrige a remoção de documento texto antigo durante a assinatura de termo...](cosinf/suap@28f476a5f2ab2989c3850b3080711002d3b35891) ([merge request](cosinf/suap!13024))
- [[plan_estrategico] verificação da variavel associada ao campus.](cosinf/suap@4ca571b61de95fedb52c5e6016ec31dc335e278f) ([merge request](cosinf/suap!13023))
- [[eventos] Correção do erro 9648 referente a erro na impressão de certificados...](cosinf/suap@52d2c37da720251a1a77b9f6e633f0903ae59540) ([merge request](cosinf/suap!13020))
- [[documento_eletronico] Corrigindo o SEARCH_FIELDS do Documento Digitalizado...](cosinf/suap@c3b27e64dc7386fbbb65bd86653d1a9c64639895) ([merge request](cosinf/suap!13017))
- [[catalogo_provedor_servico] Adicionando validação ao receber solicitação de protocolar documento](cosinf/suap@1550c75ab73a5e8ad6b81c882e04342a2521946e) ([merge request](cosinf/suap!13015))
- [[documento_eletronico] Corrigindo rejeição de solicitação de assinatura para utilizar vínculo.](cosinf/suap@12b47b7ffd05128446413ad7378af522a4a1d883) ([merge request](cosinf/suap!13016))
- [[edu] correções no tratamento de dados da exportação do educancenso (1° etapa)](cosinf/suap@a057d0383ef23150deec7c0cec575dacee27f027) ([merge request](cosinf/suap!13013))
- [[pesquisa] Adiciona validações ao tentar adicionar um novo material ao laboratório de pesquisa.](cosinf/suap@63d057845a9beb34b3649ddcfb935d8d3ee91ca8) ([merge request](cosinf/suap!13014))
- [[plan_estrategico] Corrige o comando que importa as variaveis do planejamento estratégico.](cosinf/suap@f9fd9162dde5d68c01988034ac51e1cc0d56ea20) ([merge request](cosinf/suap!13010))
- [[documento_eletronico]  Corrige a aba de documentos e processos de alunos sem usuário associado](cosinf/suap@941b6277061104682f0e7de4899a817843b8770d) ([merge request](cosinf/suap!13009))
- [[edu] Adiciona tratamento de somente alunos com matriz ou de minicurso e...](cosinf/suap@abbafc390d897923a9e59cf4a8f1d1d5d2370bf8) ([merge request](cosinf/suap!13007))
- [[documento_eletronico] Corrige a solicitacao de assinaturas para pessoas que...](cosinf/suap@e2df8406c51a9e612e4363ed99d7f289c1b140a1) ([merge request](cosinf/suap!13006))
- [[erros] Correção na visualização das respostas frequentes na página de visualização de erro](cosinf/suap@8c0a0a01f32fab23f89fe9dd68ac77c75210a9c5) ([merge request](cosinf/suap!13004))
- [[ldap_backend] Adiciona uma verificação de matriz existente para atualizar as...](cosinf/suap@e74555673dbbc6fc35a48a9bae0b1895d9f443af) ([merge request](cosinf/suap!13001))
- [[documento_eletronico] Removendo referência para pessoa fisica na view finalizar documento](cosinf/suap@903fb66a932d6da910bfa4caecffd0ccb961a2c8) ([merge request](cosinf/suap!13002))
- [[comum] Escondendo noticias marcadas como lidas ao tentar renderizar um quadro cacheado.](cosinf/suap@f7c996510577882ad4dd8a20c594e72537e7a36f) ([merge request](cosinf/suap!12999))
- [[edu] corrige erros no abono de falta](cosinf/suap@a20a8fb2fe2161e56d77f1df2de69b5c9028a968) ([merge request](cosinf/suap!12998))
- [[documento_eletronico] Solicitação de Assinatura Com Anexação a Processo Só...](cosinf/suap@3fb9a2a12a5a9f9e73889ca1f39d741dc66f2b38) ([merge request](cosinf/suap!12995))
- [[documento_eletronico] - Corrige tela meus documentos emitidos](cosinf/suap@80ab001f52145812c7f6ecfebdf87d90ca1a7007) ([merge request](cosinf/suap!12994))
- [[documento_eletronico] Corrige visualização dos documentos relacionados ao cpf](cosinf/suap@f39cfde5155a37b88797d6181a692cdd668da4e4) ([merge request](cosinf/suap!12993))
- [[documento_eletronico] Correção de bug impedia criar documento pessoal](cosinf/suap@3c6ef58d8dd92d659830cf9296501f83e65a3ee8) ([merge request](cosinf/suap!12992))
- [[edu] corrige erro na exportação dos registros 10, 30 e 50 do educacenso](cosinf/suap@4fa0d15dff8f938389d7bb1aff95d34c8a78361c) ([merge request](cosinf/suap!12988))
- [[api] Correção no retorno do endpoint que exibe os números do SUAP](cosinf/suap@bfb0b87c4adf65f8d025f9fcb9fbc1117adeba10) ([merge request](cosinf/suap!12984))
- [[erros] - Corrige erro ao gerar comentario em issue gitlab](cosinf/suap@5769b149ea9105997b5d9c28b9d94f35571d76f7) ([merge request](cosinf/suap!12985))
- [[documento_eletronico][processo eletronico] Corrigindo tela minhas ações](cosinf/suap@194bddf6737834020dc89f34027393627ef5b4fb) ([merge request](cosinf/suap!12983))
- [[documento_eletronico] Corrige o registro de ações realizadas em documentos digitalizados](cosinf/suap@45b8a9271fa76f639b7814e49be84f5bf531c28e) ([merge request](cosinf/suap!12982))
- [[documento_eletronico] Corrige a emissão de documentos do AE](cosinf/suap@36dd02b237f305ed07360aa525b246db90eea9cb) ([merge request](cosinf/suap!12980))
- [[documento_eletronico] Atualiza o comando...](cosinf/suap@ef1d5a78a4ce20c4b5155aa08b657574628c6f83) ([merge request](cosinf/suap!12978))
- [[documento_eletronico] Bug em finalizar documento](cosinf/suap@07c2678c2b4f0cf0ae40644842f0f082e57f9c0b) ([merge request](cosinf/suap!12977))
- [[documento_eletronico] Atualizando referencia para vinculos em emissão de documentos](cosinf/suap@267b4ce8d8395a0f5ec3abb08a45595d67f86bad) ([merge request](cosinf/suap!12979))
- [[documento_eletronico] Corrige a adição de documento digitalizado pessoal pelo aluno](cosinf/suap@0ce4f2b5381a3f56b90bc0aec852de38b927956a) ([merge request](cosinf/suap!12981))

### added (6 changes)

- [[comum] Alterações em regras de cadastro de usuário externo](cosinf/suap@8780a1e04bfe6f1517a10706c9fffae77611467b) ([merge request](cosinf/suap!13018))
- [[edu] Adicionando o número de série e o código EMEC do curso no modelo de documento para diploma](cosinf/suap@5db535050fbf4d7b1b0a4e8377afedaf8eec3c73) ([merge request](cosinf/suap!13005))
- [[edu] Criação de comando para retirar todos os caracteres inválidos da descrição dos componentes](cosinf/suap@898b2bf73ce79419e05de153346c1d039c889b19) ([merge request](cosinf/suap!13000))
- [[erros] Cadastro de Respostas padrão para Erros](cosinf/suap@510bbd01b8e0100c0cbc6cf82fb72b541c5fb395) ([merge request](cosinf/suap!12986))
- [[docker] Adiciona deploy de suap-pdf ao gitlab-ci](cosinf/suap@d22db6915d0ab4a12ebfddf94a0e632874711126) ([merge request](cosinf/suap!12990))
- [[docker] Adiciona o container de impressão de pdfs usando libreoffice ao docker-compose](cosinf/suap@f64c58c142e387af71cbfee8bc5d873e22b614e8) ([merge request](cosinf/suap!12987))

### changed (3 changes)

- [[erros] Melhorias de usabilidade para formulário de Adicionar Interação em Erro](cosinf/suap@05e6ba579abadc39c04ec044a5df61b4c01bfb66) ([merge request](cosinf/suap!13008))
- [[edu] Atualização da versão do RAP para aversão 0.22.1.](cosinf/suap@d7d7ed5630974df694e70e57d2a81368516c17f8) ([merge request](cosinf/suap!12997))
- [[projetos ] Adicionar filtro "Tem interesse no fomento para custeio" nos projetos de extensão](cosinf/suap@e938a386db3928b404d6d5220b8a3b1d44e75e2a) ([merge request](cosinf/suap!12991))

## 3.4.0 (2023-06-18)

### fixed (2 changes)

- [[documento_eletronico] Se a tabelas forem vazias, pule a checagem da migração...](cosinf/suap@d3817c0fe22895a74c67729833c4ffdd691f11c3) ([merge request](cosinf/suap!12976))
- [[ae] Corrige erro quando não passava parâmetro tela de impressão lista diária de refeição](cosinf/suap@f8c8966a57f2d65723b5e1138505bf0384bb02a1) ([merge request](cosinf/suap!12970))

### changed (3 changes)

- [[contratos] Correções para adição de Contrato: inclusão de novos campos e...](cosinf/suap@54db027f70c8ee86ae741eea16f584e98173ac2a) ([merge request](cosinf/suap!12975))
- [[documento_eletronico] Ajustes na flag de migration do documento eletrônico](cosinf/suap@53f24df32d1c548ee46b4d94274304b349fca23b) ([merge request](cosinf/suap!12974))
- [[documento_eletronico] Migração Documento Eletrônico de PF para Vínculo](cosinf/suap@ed6c610d2d5771f37bb5fd745ae3683604d798a3) ([merge request](cosinf/suap!12972))

### added (1 change)

- [[plan_estrategico] Permitir cadastro de Códigos UG e UGR nas unidades gestoras](cosinf/suap@96ab0d2a91aa6e7c46f80508c08e111ee380d069) ([merge request](cosinf/suap!12971))

## 3.3.2 (2023-06-18)

### fixed (16 changes)

- [[edu] Correção de bug no cadastro de aula quando a configuração...](cosinf/suap@bb91638135a3075ce83a3210fd993fc8fa4a4ad2) ([merge request](cosinf/suap!12969))
- [[edu] Correção de bug na assinatura de diplomas de curso técnico em decorrência da...](cosinf/suap@12e547bde23b048f9e2145ca51a7cc38ae608920) ([merge request](cosinf/suap!12967))
- [[edu] Correção de bug na assinatura de diplomas de curso técnico em decorrência da...](cosinf/suap@fd838efe8d9dc7f8d10c9636c886f2131d33d6a9) ([merge request](cosinf/suap!12962))
- [[edu] corrige erro ao enviar dados do diploma para assinatura via api suap-pdf](cosinf/suap@08a594f199d193d52bd2117ca77faffd7c10b1e4) ([merge request](cosinf/suap!12965))
- [[licenca_capacitacao] Corrige exibição de dados na impressão do pedido do servidor](cosinf/suap@8f1b56936454cadd09fbecd30f10ef7aaf9686e6) ([merge request](cosinf/suap!12961))
- [[edu] melhora tratamento de erro na consulta de dados do aluno na api da receita federal](cosinf/suap@ecbbc4b49d6ea9fa8ef7ca7db5189835ede86bc1) ([merge request](cosinf/suap!12958))
- [[processo_eletronico] Correção de bug reportado pelo CFVM referente a...](cosinf/suap@6379724e53d2f0dba086a18f4b0db27cb42cf1de) ([merge request](cosinf/suap!12960))
- [[ae] Ajuste na mensagem de verificação de alunos ativos nos atendimentos.](cosinf/suap@233181453bd658ba6ade2ceec3cf28c69dee6816) ([merge request](cosinf/suap!12959))
- [[eleicao] - Adicionando validação nas datas homologação eleições](cosinf/suap@5c3f109089152a95fb774cdab2a31e7940cfa95f) ([merge request](cosinf/suap!12956))
- [[comum] corrige erro no login de usuário](cosinf/suap@d94883d28374fa26234e1450be73e961f12d89bc) ([merge request](cosinf/suap!12954))
- [[edu] Corrige erro ao gerar carômetros de alunos](cosinf/suap@fa9ba7647c3955ae8c709c1ee15510eee3e85326) ([merge request](cosinf/suap!12948))
- [[cursos][djtools] Melhorias nas notificacoes de horas trabalhadas de cursos e...](cosinf/suap@eaabc5be2d5de90ce001efe588097084acd263ab) ([merge request](cosinf/suap!12951))
- [[processo_eletronico] Correção busca por numeração em tela de adicionar documento ao processo](cosinf/suap@891e3a9afb25bb06d6488ec68d9c9e539dcacbb6) ([merge request](cosinf/suap!12943))
- [[documento_eletronico] Corrige função de visualização de documento eletronico](cosinf/suap@28106b0116eebd12b0fb211e853de121eec9d01d) ([merge request](cosinf/suap!12942))
- [[djtools] Corrige a execução de querys SQL sem gerar nenhum resultado](cosinf/suap@e2fadde7fc8574560b1c9ee6993ada9a022b4563) ([merge request](cosinf/suap!12939))
- [[edu] trata data inválida na atualização de código educacenso](cosinf/suap@94f7d17e6fa0139fd2d75ab71e5f584acf5babdd) ([merge request](cosinf/suap!12937))

### changed (11 changes)

- [[ae] Padronização e correção de alertas da página inicial para alunos...](cosinf/suap@2016bb80641bf8b33980a108ac504d40fdf0faa2) ([merge request](cosinf/suap!12966))
- [[edu] retira acesso a edição de abertura extemporânea](cosinf/suap@4f691d2717cf79027fbc54ec2fd46a0387d1ff81) ([merge request](cosinf/suap!12963))
- [[cursos] Correção do layout de botão de Deferir e Indeferir horas de Participante](cosinf/suap@629c35211dee5b6d66784224eda6f72db74c8b40) ([merge request](cosinf/suap!12957))
- [[erros] Exibe erros atuais abertos ao Reportar Erro](cosinf/suap@54f0fcbc98c468232331962c314afc036bc03105) ([merge request](cosinf/suap!12955))
- [[cursos] Ajustes de usabilidade na tela de visualização dos dados de Participante](cosinf/suap@db3b37559172e9fdd30aa2fc6a324774685ffd8c) ([merge request](cosinf/suap!12953))
- [[almoxarifado]  Alertas de empenho com 15 dias de prazo por campus](cosinf/suap@96e495fe53f2f8a0ff908a8f35fcbaaa87775087) ([merge request](cosinf/suap!12950))
- [[comum] Melhoria na tela pública para exibição da validação de assinatura digital](cosinf/suap@3f1229311cece5db5a7e376ac3a97f999adbd739) ([merge request](cosinf/suap!12949))
- [[licenca_capacitacao] Imprimir pedido de licença capacitação com dados dos...](cosinf/suap@6e033c7110458ea3c9c47f7f099161d48a18658c) ([merge request](cosinf/suap!12946))
- [[centralservicos] Impedimento de atribuição de chamados a atendentes de férias ou afastados](cosinf/suap@fc26bd1b1f57e7765032b68c8db947e7041cb1a9) ([merge request](cosinf/suap!12945))
- [[ae] Melhoria performance relatorio semanal refeição](cosinf/suap@39a7bdda9d0e34a7719b1f3b1601d26e5058e3c3) ([merge request](cosinf/suap!12941))
- [[djtools] Alteração nos templates de Merge Requests](cosinf/suap@1aa2a69ad18d49b791ce6453c7b812804bf9d32e) ([merge request](cosinf/suap!12938))

### added (4 changes)

- [[erros] Adição de mensagem de alerta ao Adicionar Anexo informando que a...](cosinf/suap@cc26fbc8213458aea8d4d7d3b1d594bf4b0ca9a4) ([merge request](cosinf/suap!12952))
- [[projetos] Registro de atividade curricular de extensão para alunos participantes do projeto](cosinf/suap@465fb15177a5a980f5908ab0bc214218ab53e27f) ([merge request](cosinf/suap!12947))
- [[djtools] Libreoffice](cosinf/suap@8dd8940cb4520a2d378dd9a393697b0fd8433a95) ([merge request](cosinf/suap!12940))
- [[edu] adiciona cópia de respostas no clone de questionário educacenso](cosinf/suap@45e0318765dadcfa182a163f4fca681120e5db1f) ([merge request](cosinf/suap!12936))

### performance (1 change)

- [[comum][edu] Remoção de dependências desnecessárias](cosinf/suap@1fd52d57895ad851a7217be36d01d1bb069a2dd3) ([merge request](cosinf/suap!12944))

## 3.3.1 (2023-06-12)

### added (4 changes)

- [[api] Adiciona o grupo Gerente Sistêmico de API para controlar todas as...](cosinf/suap@c9555c4ccfcd0ef1695978c6594634cfc11de305) ([merge request](cosinf/suap!12935))
- [[licenca_capacitacao]Permite que a gestão de Licença Capacitação veja os pedidos - mesmo os não submetidos](cosinf/suap@a7a1a96cdc32d8e78b3af628a80ca60270ee6eb4) ([merge request](cosinf/suap!12931))
- [[contratos] adicionando informações de valores pagos, liquidados, RAP e Saldo...](cosinf/suap@c1845b636ccd0f9981b02cc4b7b657622b44ef0a) ([merge request](cosinf/suap!12922))
- [[djtools] Adicionando pipelines de versionamento](cosinf/suap@fa37ab5aed20f208ffb199d56dba15683ce8e873) ([merge request](cosinf/suap!12919))

### fixed (13 changes)

- [[edu] Melhorias no fluxo de geração de auditorias do ensino](cosinf/suap@3ea80a14a002669ec694271a1ae969eb5a83fdd7) ([merge request](cosinf/suap!12933))
- [[plan_estrategico] Corrigindo exibição de atividades de movimentações de...](cosinf/suap@b77c3559739f9ec4bb912da0d8c51bb6ab5254f0) ([merge request](cosinf/suap!12932))
- [[ponto]Compensação: correção nome do script ponto-util-v2.js](cosinf/suap@e024cbd501e9634fe6442581c96cd8943ee43b6f) ([merge request](cosinf/suap!12929))
- [[estagios] Corrige validação do período corrente do aluno no cadastro de estágio](cosinf/suap@fa3e2ee9abfa863193b34ef97ec79081d9d833d3) ([merge request](cosinf/suap!12912))
- [[edu] corrige erro ao gerar auditoria sistec](cosinf/suap@b348075a3623e3ac9515d2c0d2822406daed6802) ([merge request](cosinf/suap!12928))
- [[djtools] Substituindo projeto scripts pelo suap-ansible no deploy do suap.](cosinf/suap@feaeccb27887510953b05de2f5ac6a1079c9ce0b) ([merge request](cosinf/suap!12927))
- [[edu] exibe necessidades educacionais específicas em dados pessoais de aluno](cosinf/suap@0da660937854b3daa9a3589a236ef8fd11fbc53b) ([merge request](cosinf/suap!12923))
- [[edu] Verifica a existência de configuração de caminho de arquivo de crachá de alunos](cosinf/suap@6db09b0745043a646a6225de9ac5252d10d84caf) ([merge request](cosinf/suap!12926))
- [[djtools] Simplificando a criação de tags do suap usando a API do gitlab](cosinf/suap@cc29abef4460b125fd3ebe39fa1738ae0bc7a024) ([merge request](cosinf/suap!12925))
- [[djtools] Substituindo os templates de merge request por templates mais significativos.](cosinf/suap@d4327517d8eca5f6b0b458dbc4a0bbeff74abacf) ([merge request](cosinf/suap!12924))
- [[edu] ignora letras maiúsculas e minúsculas auditoria de dados da receita federal](cosinf/suap@ffa73c842bcdf194c4f2dfb5b434c7cef9f8eff2) ([merge request](cosinf/suap!12921))
- [[edu] corrige erro ao recuperar dados da receita federal](cosinf/suap@71e0781216e7e6e8702f35e4c5b3fb24cf5efe47) ([merge request](cosinf/suap!12920))
- [[edu] ajuste no abono de faltas em lote](cosinf/suap@d38d32926a65a08909a02a05ed9138e25e76d167) ([merge request](cosinf/suap!12917))

### changed (1 change)

- [[djtools] Melhoria na geração de bancos de dados vazios do suap](cosinf/suap@f9547b5c91af0c5df0ab04ff5db0893e2069163d) ([merge request](cosinf/suap!12934))

## 3.3.0 (2023-06-05)

No changes.
