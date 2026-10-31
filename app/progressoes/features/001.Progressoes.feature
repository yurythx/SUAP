# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Fluxo principal da Avaliação de Desempenho
    Essa funcionalidade testa o fluxo principal da funcionalidade Avaliação de Desempenho.

  Cenário: Adiciona os usuarios necessarios para essa funcionalidade
    Dado os seguintes usuários
      | Nome               | Matrícula      | Setor | Lotação | Email                         | CPF            | Senha | Grupo                                       |
      | Coord_RH Sistemico | 9999100        | CZN   | CZN     | coordrhsistemico@ifrn.edu.br  | 619.993.140-85 | abcd  | Coordenador de Gestão de Pessoas Sistêmico  |
    E os cadastros básicos de progressões
    Quando a data do sistema for "02/08/2019"

  @do_document
  Cenário: Adicionar Processo
    Quando acesso a página "/"
    E realizo o login com o usuário "9999100" e senha "abcd"
    Quando acesso a página "/admin/progressoes/processoprogressao/"
    E clico no botão "Adicionar Processo"
    E clico no botão "Progressão"
    Quando preencho o formulário com os dados
      | Campo                      | Tipo         | Valor      |
      | Avaliado                   | Autocomplete | Servidor   |
      | Data Início da Contagem    | Data         | 01/08/2019 |
      | Padrão de Vencimento Atual | Autocomplete |          1 |
      | Padrão de Vencimento Novo  | Autocomplete |          2 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Processo de progressão cadastrado com sucesso."

  @do_document
  Cenário: Adicionar Período(s)
    Quando acesso a página "/admin/progressoes/processoprogressao/"
    E clico no ícone de exibição
    Quando clico no botão "Adicionar período"
    E olho para o popup
    E preencho o formulário com os dados
      | Campo               | Tipo         | Valor      |
      | Setor               | Autocomplete | A1         |
      | Data Inicial        | Data         | 01/08/2019 |
      | Data Final          | Data         | 31/07/2020 |
      | Modelo de Avaliação | Autocomplete | Teste      |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Período cadastrado com sucesso."

  @do_document
  Cenário: Adicionar Avaliador(es)
    Quando acesso a página "/admin/progressoes/processoprogressao/"
    E clico no ícone de exibição
    Quando clico no botão "Adicionar/Editar avaliadores"
    E olho para o popup
    E preencho o formulário com os dados
      | Campo | Tipo         | Valor    |
      | Chefe | Autocomplete | Coord_RH |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliadores cadastrados com sucesso."

  @do_document
  Cenário: Liberar Processo para Avaliação
    Quando acesso a página "/admin/progressoes/processoprogressao/"
    E clico no ícone de exibição
    Quando clico no botão "Liberar avaliações e Iniciar trâmite do processo"
    Entao vejo mensagem de sucesso "Avaliações liberadas com sucesso. Os avaliadores foram notificados."

  @do_document
  Cenário: Responder Avaliação Como Avaliador
    Quando acesso a página "/progressoes/minhas_avaliacoes/"
    Quando clico no ícone de exibição
    E preencho o formulário com os dados
      | Campo                                  | Tipo     | Valor |
      | Considerações/Comentários do Avaliador | Textarea | Teste |
      | Criterio 1                             | radio    |  10.0 |
      | Criterio 2                             | radio    |  10.0 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação salva. Se desejar, pode assiná-la agora."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: Responder Auto-Avaliação
    Quando acesso a página "/"
    E realizo o login com o usuário "1111111" e senha "abc"
    Quando acesso a página "/progressoes/minhas_avaliacoes/"
    Quando clico no ícone de exibição
    E preencho o formulário com os dados
      | Campo                                  | Tipo     | Valor |
      | Considerações/Comentários do Avaliador | Textarea | Teste |
      | Criterio 1                             | radio    |  10.0 |
      | Criterio 2                             | radio    |  10.0 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação salva. Se desejar, pode assiná-la agora."

  @do_document
  Cenário: Assinar Auto-Avaliação
    Quando acesso a página "/progressoes/minhas_avaliacoes/?tab=tab2"
    E clico no botão "Assinar processo"
    E preencho o formulário com os dados
      | Campo | Tipo  | Valor |
      | Senha | senha | abc   |
    E clico no botão de submit "Assinar"
    Então vejo mensagem de alerta "Nenhuma avaliação pendente de assinatura."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: Assinar Avaliação
    Quando acesso a página "/"
    E realizo o login com o usuário "9999100" e senha "abcd"
    Quando acesso a página "/progressoes/minhas_avaliacoes/?tab=tab2"
    Quando clico no botão "Assinar processo"
    E preencho o formulário com os dados
      | Campo | Tipo  | Valor |
      | Senha | senha | abcd  |
    E clico no botão de submit "Assinar"
    Então vejo mensagem de alerta "Nenhuma avaliação pendente de assinatura."

  @do_document
  Cenário: Finalizar Processo
    Quando acesso a página "/admin/progressoes/processoprogressao/?tab=tab_em_tramite"
    E clico no ícone de exibição
    Quando clico no botão "Finalizar processo"
    Então vejo mensagem de sucesso "O processo foi finalizado."
