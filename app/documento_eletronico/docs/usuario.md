# Documentos Eletrônicos

Este guia explica as tarefas do módulo de Documentos Eletrônicos: preparação dos cadastros, criação e ciclo de vida dos documentos, assinaturas, compartilhamento, vínculos e níveis de acesso.

As telas e mensagens foram verificadas em ambiente de teste. Se uma ação não aparecer, o usuário precisa receber o perfil ou a permissão indicada na tarefa.

## Antes de começar

1. Cadastre os tipos de documento, tipos de vínculo, tipos de conferência, hipóteses legais e modelos necessários.
2. Defina as permissões do setor para leitura e operação dos documentos.
3. Tenha um documento em rascunho quando for editar, concluir ou assinar; documentos finalizados não voltam para edição.
4. Para níveis **Restrito** e **Sigiloso**, selecione uma hipótese legal válida e confirme a operação com sua senha.

## Perfis envolvidos

| Perfil | Tarefas deste guia |
| --- | --- |
| Gerente Sistêmico de Documento Eletrônico | Painel e cadastros; clonagem de tipo e documento; recebimento de assinatura; vínculo. |
| Chefe de Setor | Permissões do setor; criação, edição, conclusão, assinatura e finalização; alteração direta de acesso; autorização. |
| Servidor autorizado | Solicitação de assinatura ou de alteração de nível, conforme a permissão recebida. |

## Painel

O painel reúne documentos pessoais, favoritos, documentos compartilhados, vínculos, assinaturas e revisões pendentes.

![Painel de Documentos Eletrônicos](usuario/smoke-dashboard.webp)

## Cadastros básicos

### 1. Cadastrar uma classificação

**Quem pode:** Gerente Sistêmico de Documento Eletrônico.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Cadastros › Classificações.

1. Abra **Classificações**.
2. Clique em **Adicionar Classificação**.
3. Informe **Código**, **Descrição**, **Suficiente para classificar um processo?** e **Ativo**. Preencha os demais campos necessários, como fase, destinação e observações.
4. Clique em **Salvar**.

![Listagem de classificações](usuario/classificacao-lista.webp)

![Formulário de classificação](usuario/classificacao-formulario.webp)

**Resultado:** a classificação aparece na listagem.

![Classificação salva](usuario/classificacao-salvo.webp)

### 2. Cadastrar um tipo de documento interno

**Quem pode:** Gerente Sistêmico de Documento Eletrônico.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Cadastros › Tipos de Documentos Internos.

1. Abra **Tipos de Documentos Internos**.
2. Clique em **Adicionar Tipo de Documento Interno**.
3. Informe **Descrição**, **Sigla** e **Ativo**.
4. Se necessário, preencha **Cabecalho padrao** e **Rodape padrao**.
5. Clique em **Salvar**.

![Listagem de tipos internos](usuario/tipo-interno-lista.webp)

![Formulário de tipo interno](usuario/tipo-interno-formulario.webp)

**Resultado:** o novo tipo aparece na listagem e pode ser usado em documentos e modelos.

![Tipo interno salvo](usuario/tipo-interno-salvo.webp)

### 3. Clonar um tipo de documento interno

**Quem pode:** Gerente Sistêmico de Documento Eletrônico.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Cadastros › Tipos de Documentos Internos.

1. Abra **Tipos de Documentos Internos**.
2. Na linha do tipo que servirá de base, clique em **Clonar**.
3. Confira o tipo criado, ajuste **Descrição**, **Sigla**, cabeçalho, rodapé e demais opções.
4. Clique em **Salvar**.

**Resultado:** o sistema cria uma cópia com novo nome, preservando o cabeçalho e o rodapé do tipo original.

![Tipo interno clonado](usuario/tipo-interno-clonado.webp)

### 4. Cadastrar um tipo de documento externo

**Quem pode:** Gerente Sistêmico de Documento Eletrônico.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Cadastros › Tipos de Documentos Externos.

1. Abra **Tipos de Documentos Externos**.
2. Clique em **Adicionar Tipo de Documento Externo**.
3. Informe **Descrição**, **Sigla** e **Ativo**.
4. Clique em **Salvar**.

![Listagem de tipos externos](usuario/tipo-externo-lista.webp)

![Formulário de tipo externo](usuario/tipo-externo-formulario.webp)

**Resultado:** o tipo externo aparece na listagem.

![Tipo externo salvo](usuario/tipo-externo-salvo.webp)

### 5. Cadastrar um tipo de vínculo de documento

**Quem pode:** Gerente Sistêmico de Documento Eletrônico.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Cadastros › Tipos de Vínculos entre Documentos.

1. Abra **Tipos de Vínculos de Documentos**.
2. Clique em **Adicionar Tipo de Vínculo de Documento**.
3. Informe a **Descrição**, a **Descrição na Voz Ativa** e a **Descrição na Voz Passiva**.
4. Clique em **Salvar**.

![Listagem de tipos de vínculo](usuario/tipo-vinculo-lista.webp)

![Formulário de tipo de vínculo](usuario/tipo-vinculo-formulario.webp)

**Resultado:** o tipo fica disponível ao vincular documentos.

![Tipo de vínculo salvo](usuario/tipo-vinculo-salvo.webp)

### 6. Cadastrar um tipo de conferência

**Quem pode:** Gerente Sistêmico de Documento Eletrônico.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Cadastros › Tipos Conferência.

1. Abra **Tipos de Conferência**.
2. Clique em **Adicionar Tipo de Conferência**.
3. Informe a **Descrição**.
4. Clique em **Salvar**.

![Listagem de tipos de conferência](usuario/tipo-conferencia-lista.webp)

![Formulário de tipo de conferência](usuario/tipo-conferencia-formulario.webp)

**Resultado:** o tipo fica disponível para registrar como o documento externo foi conferido.

![Tipo de conferência salvo](usuario/tipo-conferencia-salvo.webp)

### 7. Cadastrar uma hipótese legal

**Quem pode:** Gerente Sistêmico de Documento Eletrônico.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Cadastros › Hipóteses Legais.

1. Abra **Hipóteses Legais**.
2. Clique em **Adicionar Hipótese Legal**.
3. Selecione o **Nível de Acesso** que a hipótese justifica.
4. Informe **Descrição** e **Base Legal**.
5. Clique em **Salvar**.

![Listagem de hipóteses legais](usuario/hipotese-legal-lista.webp)

![Formulário de hipótese legal](usuario/hipotese-legal-formulario.webp)

**Resultado:** a hipótese pode ser escolhida ao restringir o acesso de um documento.

![Hipótese legal salva](usuario/hipotese-legal-salvo.webp)

### 8. Cadastrar um modelo de documento

**Quem pode:** Gerente Sistêmico de Documento Eletrônico.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Cadastros › Modelos.

1. Abra **Modelos de Documentos**.
2. Clique em **Adicionar Modelo de Documento**.
3. Selecione o **Tipo do Documento** e informe a **Descrição**.
4. Marque os níveis permitidos: **Sigiloso?**, **Restrito?** e **Público?**.
5. Escolha o **Nível de Acesso Padrão** e marque **Ativo**.
6. Clique em **Salvar**.

![Listagem de modelos](usuario/modelo-lista.webp)

![Formulário de modelo](usuario/modelo-formulario.webp)

**Resultado:** o modelo é criado e pode receber corpo, variáveis e ajustes adicionais.

![Modelo criado](usuario/modelo-salvo.webp)

## Criar e tramitar documentos

### 9. Definir permissões de documento eletrônico

**Quem pode:** Chefe de Setor.

**Caminho:** Documentos/Processos › Permissões › aba **Documentos Eletrônicos**.

1. Abra **Permissões**.
2. Selecione a aba **Documentos Eletrônicos**.
3. No setor desejado, informe os servidores que podem **adicionar, operar e ler** documentos.
4. Informe os servidores que podem apenas **ler** documentos.
5. Também é possível conceder essas permissões a setores.
6. Clique em **Enviar**.

![Formulário de permissões](usuario/permissoes-formulario.webp)

**Resultado:** as permissões ficam registradas para o setor.

![Permissões salvas](usuario/permissoes-salvo.webp)

### 10. Cadastrar um documento eletrônico

**Quem pode:** servidor com permissão de criação no setor.

**Caminho:** Documentos/Processos › Documentos Eletrônicos › Documentos.

1. Abra **Documentos de Texto**.
2. Clique em **Adicionar Documento de Texto**.
3. Selecione o **Tipo do Documento**, o **Modelo**, o **Nível de Acesso** e o **Setor Dono**.
4. Informe o **Assunto**.
5. Confirme que está ciente das instruções gerais, quando o campo for exibido.
6. Clique em **Salvar**.

![Listagem de documentos](usuario/cadastrar-documento-lista.webp)

![Formulário de documento](usuario/cadastrar-documento-formulario.webp)

**Resultado:** o documento é criado como rascunho e sua tela de visualização é aberta.

![Documento cadastrado](usuario/cadastrar-documento-salvo.webp)

### 11. Editar o conteúdo do documento eletrônico

**Quem pode:** usuário com permissão de operação no documento em rascunho.

1. Na tela do documento, clique em **Editar**.
2. Escolha **Texto**.
3. Edite o corpo do documento.
4. Clique em **Salvar e Visualizar**.

![Documento antes da edição](usuario/editar-conteudo-documento.webp)

![Editor do documento](usuario/editar-conteudo-formulario.webp)

**Resultado:** o documento volta à tela de visualização e registra a edição.

![Documento após a edição](usuario/editar-conteudo-salvo.webp)

### 12. Concluir o documento eletrônico

**Quem pode:** usuário com permissão de operação no documento.

1. Abra um documento em rascunho.
2. Revise o conteúdo e os dados do documento.
3. Clique em **Concluir**.

![Documento em rascunho](usuario/concluir-documento-rascunho.webp)

**Resultado:** o rascunho passa a concluído e fica pronto para assinatura.

![Documento concluído](usuario/concluir-documento-concluido.webp)

### 13. Retornar o documento para rascunho

**Quem pode:** usuário com permissão de operação no documento concluído.

1. No documento concluído, clique em **Ações**.
2. Clique em **Retornar para rascunho**.
3. Faça as alterações necessárias.
4. Clique novamente em **Concluir**.

![Documento concluído antes do retorno](usuario/retornar-rascunho-concluido.webp)

![Documento retornado para rascunho](usuario/retornar-rascunho-rascunho.webp)

**Resultado:** o documento volta a concluído após a nova conclusão.

![Documento concluído novamente](usuario/retornar-rascunho-reconcluido.webp)

### 14. Assinar o documento eletrônico

**Quem pode:** signatário autorizado do documento concluído.

1. No documento concluído, clique em **Assinar**.
2. Clique em **Definir identificador**.
3. Selecione o **Perfil** de assinatura.
4. Informe sua **Senha**.
5. Clique em **Assinar Documento**.

![Documento pronto para assinatura](usuario/assinar-documento-concluido.webp)

![Formulário de assinatura](usuario/assinar-documento-formulario.webp)

**Resultado:** a assinatura é registrada no documento.

![Documento assinado](usuario/assinar-documento-assinado.webp)

### 15. Solicitar assinatura de outro servidor

**Quem pode:** usuário com permissão de operação no documento.

1. Abra o documento concluído e clique em **Solicitar**.
2. Escolha **Assinatura**.
3. Informe a **Pessoa** que deverá assinar.
4. Clique em **Enviar solicitações**.
5. O destinatário abre o documento, clica em **Assinar**, escolhe o perfil, informa a senha e clica em **Assinar Documento**.

![Documento com opção de solicitar assinatura](usuario/solicitar-assinatura-documento.webp)

![Formulário de solicitação](usuario/solicitar-assinatura-formulario.webp)

![Solicitação registrada](usuario/solicitar-assinatura-salvo.webp)

![Documento recebido pelo signatário](usuario/solicitar-assinatura-destinatario.webp)

![Assinatura do destinatário](usuario/solicitar-assinatura-assinatura-formulario.webp)

**Resultado:** a solicitação e a assinatura ficam visíveis no histórico do documento.

![Documento assinado pelo destinatário](usuario/solicitar-assinatura-assinado.webp)

### 16. Finalizar o documento eletrônico

**Quem pode:** usuário autorizado a finalizar o documento assinado.

1. Abra o documento que já possui a assinatura necessária.
2. Confira as assinaturas.
3. Clique em **Finalizar**.

![Documento assinado antes da finalização](usuario/finalizar-documento-assinado.webp)

**Resultado:** o documento fica finalizado e não pode mais ser editado.

![Documento finalizado](usuario/finalizar-documento-finalizado.webp)

### 17. Imprimir o documento eletrônico

**Quem pode:** usuário com acesso ao documento.

1. Abra o documento finalizado.
2. Clique em **Ações**.
3. Escolha **Imprimir (Retrato)** ou **Imprimir (Paisagem)**.
4. Na tela de impressão, confira a prévia e clique em **Continuar** ou **Imprimir**.

![Impressão em retrato](usuario/imprimir-documento-retrato.webp)

![Impressão em paisagem](usuario/imprimir-documento-paisagem.webp)

**Resultado:** o sistema prepara o PDF no formato escolhido.

### 18. Compartilhar um documento com outros setores

**Quem pode:** usuário com permissão de compartilhamento do documento.

1. Abra o documento.
2. Clique em **Compartilhar**.
3. Escolha os setores que podem **editar e ler** ou apenas **ler**.
4. Clique em **Enviar**.

![Formulário de compartilhamento](usuario/compartilhar-documento-formulario.webp)

**Resultado:** o compartilhamento é registrado e o setor passa a encontrar o documento conforme a permissão concedida.

![Compartilhamento registrado](usuario/compartilhar-documento-salvo.webp)

### 19. Clonar um documento eletrônico

**Quem pode:** usuário com acesso de clonagem ao documento.

1. Abra o documento que servirá de base.
2. Clique em **Ações** e depois em **Clonar**.
3. Ajuste o **Setor Dono** e informe um novo **Assunto**.
4. Revise tipo, modelo, classificações e nível de acesso.
5. Clique em **Salvar**.

![Formulário de clonagem](usuario/clonar-documento-formulario.webp)

**Resultado:** um novo documento é criado, inicialmente em rascunho.

![Documento clonado](usuario/clonar-documento-salvo.webp)

### 20. Vincular documentos eletrônicos

**Quem pode:** usuário com permissão de operação no documento base.

1. Conclua, assine e finalize o documento que será a base do vínculo.
2. Abra **Ações** e clique em **Vincular documento**.
3. Selecione o **Tipo de Vínculo**.
4. Escolha o **Documento Alvo**.
5. Clique em **Salvar**.

![Formulário de vínculo](usuario/vincular-documento-formulario.webp)

**Resultado:** o vínculo aparece no histórico e na visualização dos documentos relacionados.

![Vínculo registrado](usuario/vincular-documento-salvo.webp)

## Alterar nível de acesso

### 21. Alterar diretamente o nível de acesso

**Quem pode:** Chefe de Setor ou responsável com autorização direta.

1. Abra um documento finalizado.
2. Clique em **Nível de acesso**.
3. Clique em **Editar nível de acesso**.
4. Escolha o novo nível em **Para**.
5. Se o nível exigir justificativa, selecione a **Hipótese Legal**.
6. Informe a **Senha para confirmação**.
7. Clique em **Enviar**.

![Listagem para alteração de acesso](usuario/nivel-acesso-alteracao-lista.webp)

![Documento para alteração de acesso](usuario/nivel-acesso-alteracao-documento.webp)

![Formulário de alteração de acesso](usuario/nivel-acesso-alteracao-formulario.webp)

**Resultado:** o novo nível aparece no documento e a alteração fica registrada no histórico.

![Alteração de acesso concluída](usuario/nivel-acesso-alteracao-sucesso.webp)

### 22. Solicitar alteração de nível de acesso

**Quem pode:** servidor que pode visualizar o documento, mas não pode alterar diretamente seu nível.

1. Abra o documento finalizado.
2. Clique em **Nível de acesso**.
3. Clique em **Solicitar alteração de nível de acesso**.
4. Escolha o novo nível em **Para**.
5. Selecione a **Hipótese Legal** e informe a senha.
6. Clique em **Enviar**.

![Listagem da solicitação](usuario/nivel-acesso-solicitacao-lista.webp)

![Documento da solicitação](usuario/nivel-acesso-solicitacao-documento.webp)

![Formulário de solicitação de acesso](usuario/nivel-acesso-solicitacao-formulario.webp)

**Resultado:** a solicitação fica pendente para análise do responsável.

![Solicitação de acesso registrada](usuario/nivel-acesso-solicitacao-sucesso.webp)

### 23. Autorizar alteração de nível de acesso

**Quem pode:** Chefe de Setor ou responsável pela análise do documento.

1. Abra o documento com solicitação pendente.
2. Clique em **Nível de acesso**.
3. Clique em **Analisar/Visualizar solicitações de alteração de nível de acesso**.
4. Selecione a solicitação e clique em **Deferir**.
5. Marque **Confirmar**.
6. Informe a senha e clique em **Enviar**.

![Listagem para autorização](usuario/nivel-acesso-autorizacao-lista.webp)

![Documento para autorização](usuario/nivel-acesso-autorizacao-documento.webp)

![Solicitações pendentes](usuario/nivel-acesso-autorizacao-solicitacoes.webp)

![Formulário de autorização](usuario/nivel-acesso-autorizacao-formulario.webp)

**Resultado:** o nível de acesso é alterado e a autorização fica registrada no histórico.

![Autorização concluída](usuario/nivel-acesso-autorizacao-sucesso.webp)

## Situações comuns

- **Ação não aparece:** confirme o perfil, a função no setor e as permissões do documento.
- **Hipótese legal não aparece:** selecione primeiro um nível que exija justificativa; as opções são carregadas depois dessa escolha.
- **Documento não pode ser editado:** ele pode estar concluído, assinado ou finalizado. Retorne-o para rascunho quando essa ação estiver disponível.
- **Assinatura não aparece:** verifique se a solicitação foi enviada para a pessoa correta e se ela possui acesso ao documento.
