# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Responder Questionário de Acúmulo de Cargo

  @do_document
  Cenário: Responder Questionário de Acúmulo de Cargo
    Ação executada pelo membro do grupo Servidor.

    Dado acesso a página "/"
    Quando a data do sistema for "12/07/2020"
    Quando realizo o login com o usuário "100148" e senha "abcd"
    E clico no link "Preencha o Termo de Acúmulo de Cargos 2020."
    Então vejo a página "Adicionar Declaração de Acumulação de Cargos"
    E vejo os seguintes campos no formulário
      | Campo                                                                                                                                                                                                                                                         | Tipo     |
      | Não possuo qualquer outro vínculo ativo com a administração pública direta ou indireta nas esferas federal, estadual, distrital ou municipal, nem percebo proventos de aposentadoria, reforma ou pensão de nenhum órgão ou entidade da administração pública. | checkbox |
      | NÃO exerço qualquer atuação gerencial em atividade mercantil                                                                                                                                                                                                  | checkbox |
      | NÃO exerço comércio                                                                                                                                                                                                                                           | checkbox |
      | NÃO exerço qualquer atividade remunerada privada                                                                                                                                                                                                              | checkbox |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                                                                                                                                                                                                                                                         | Tipo     | Valor  |
      | Não possuo qualquer outro vínculo ativo com a administração pública direta ou indireta nas esferas federal, estadual, distrital ou municipal, nem percebo proventos de aposentadoria, reforma ou pensão de nenhum órgão ou entidade da administração pública. | checkbox | marcar |
      | NÃO exerço qualquer atuação gerencial em atividade mercantil                                                                                                                                                                                                  | checkbox | marcar |
      | NÃO exerço comércio                                                                                                                                                                                                                                           | checkbox | marcar |
      | NÃO exerço qualquer atividade remunerada privada                                                                                                                                                                                                              | checkbox | marcar |
    E clico no botão "Salvar"
