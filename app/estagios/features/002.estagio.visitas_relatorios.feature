# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros de visitas e relatórios semestrais

  pre-requisitos para o encerramento do estágio. No final
  desse teste o estado do estágio passará de "Em Andamento"
  para "Apto para Encerramento".

  @do_document
  Cenário: O professor orientador cadastra a Visita
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102004" e senha "abcd"
    Então vejo o quadro "Professores"
    Quando clico no link "Orientações de Estágios e Afins"
    E olho a linha "Aluno Estágio"
    E clico no ícone de exibição
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando clico na aba "Visitas do Orientador"
    E clico no botão "Adicionar Visita"
    Quando preencho o formulário com os dados
      | Campo                                          | Tipo     | Valor                       |
      | Data da Visita                                 | Data     | 15/08/2018                  |
      | Ambiente Adequado                              | Checkbox | Marcar                      |
      | Justificativa para Ambiente Inadequado         | TextArea |                             |
      | Desenvolvimento Atividades Previstas           | Checkbox | Marcar                      |
      | Desenvolvimento Atividades Fora da Competência | Checkbox | Desmarcar                   |
      | Desenvolvimento Atividades Não-Previstas       | Checkbox | Desmarcar                   |
      | Atividades Não-Previstas                       | TextArea |                             |
      | Apoiado pelo Supervisor                        | Checkbox | Marcar                      |
      | Direitos Respeitados                           | Checkbox | Marcar                      |
      | Especificar direitos não respeitados           | TextArea |                             |
      | Aprendizagem Satisfatória                      | Checkbox | Marcar                      |
      | Informações Adicionais                         | TextArea | Correu tudo bem no estágio. |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Visita adicionada com sucesso."
    Quando clico na aba "Visitas do Orientador"
    Então vejo o texto "Relatório da Visita realizada em 15/08/2018 ainda não assinado."
    E vejo o botão "Assinar o Relatório da Visita do dia 15/08/2018"
    Quando clico no botão "Assinar o Relatório da Visita do dia 15/08/2018"
    E olho para o popup
    Então vejo o texto "Assinar Relatório de Visita a Organização Concedente"
    Quando preencho o formulário com os dados
      | Campo                  | Tipo     | Valor  |
      | Senha para confirmação | senha    | abcd   |
    E clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."

  @do_document
  Cenário: O professor orientador cadastra um Agendamento de Orientação de Estágio
    Quando clico na aba "Atividades de Orientação"
    Então vejo o botão "Agendar Orientação"
    Quando clico no botão "Agendar Orientação"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor                                               |
      | Hora de Início                      | Texto    | 14:00                                               |
      | Local                               | Texto    | Sala C10                                            |
      | Descrição do Conteúdo da Orientação | TextArea | Tirar dúvidas e orietações relacionadas ao estágio. |
      | Data da Reunião de Orientação       | Data     | 16/08/2018                                          |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Agendamento de orientação adicionado com sucesso."
    Quando acesso o menu "Sair"

  Cenário: Os campos obrigatórios não são preenchidos no cadastro dos relatórios de atividades
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Extensão::Estágio e Afins::Estágios"
    E olho para a listagem
    E olho a linha "Aluno Estágio"
    Quando clico no ícone de exibição
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando clico na aba "Relatórios de Atividades – Estagiário"
    E clico no botão "Registrar Relatório"
    Então vejo a página "Submeter Relatório Semestral do Aluno"
    Quando clico no botão "Salvar"
    # O clean() de FormPlus/ModelFormPlus (djtools/forms/base.py) levanta ValidationError
    # assim que há erro de campo, abortando o clean() customizado de SubmeterRelatorioSemestralForm.
    # Por isso apenas o erro nativo de "Data do Relatório" é exibido; os erros de "Período" e
    # das atividades (adicionados após super().clean()) não chegam a ser renderizados.
    Então vejo os seguintes erros no formulário
      | Campo                     | Tipo     | Mensagem                     |
      | Data do Relatório         | Data     | Este campo é obrigatório.    |
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O estagiário cadastra o relatório semestral de atividades
    Dado acesso a página "/"
    Quando realizo o login com o usuário "20191101011021" e senha "abcd"
    E clico no link "Rel. Atividades Pendentes"
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    E vejo a aba "Relatórios de Atividades – Estagiário"
    Quando clico no botão "Registrar Relatório"
    Então vejo a página "Submeter Relatório Semestral do Aluno"
    Quando preencho o formulário com os dados
      | Campo                                                     | Tipo     | Valor                                 |
      | Período                                                   | Lista    | [01/07/2018 até 30/09/2018]           |
      | Data do Relatório                                         | Data     | 01/10/2018                            |
      | Atividade 1                                               | Lista    | Realizada                             |
      | Atividade 2                                               | Lista    | Realizada                             |
      | Atividade 3                                               | Lista    | Realizada                             |
      | Comentários sobre o desenvolvimento das atividades        | TextArea | Tudo certo com as atividades.         |
      | Realizou atividades não previstas no Plano de Atividades? | Checkbox | Marcar                                |
      | Em caso afirmativo, descreva as atividades                | TextArea | Atividades 4, 5, 6                    |
      | Em caso afirmativo, justifique                            | TextArea | Surgiram novas possibilidades.        |
      | Área de Formação                                          | Lista    | Sim                                   |
      | Contribuição do Estágio                                   | Lista    | Sim                                   |
      | Aplicação do Conhecimento                                 | Lista    | Sim                                   |
      | Conceito                                                  | Lista    | Excelente                             |
      | Comentários e Sugestões                                   | TextArea | Sugiro aconselhamentos ao estágiario. |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação registrada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O coordenador de estágio cadastra o relatório semestral de atividades do Supervisor
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Extensão::Estágio e Afins::Estágios"
    Quando clico na aba "Pendência de Relatório de Atividades do Supervisor"
    E olho para a listagem
    E olho a linha "Aluno"
    Quando clico no ícone de exibição
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando clico na aba "Relatórios de Atividades - Supervisor"
    E clico no botão "Registrar Relatório"
    Então vejo a página "Registro da Avaliação do Supervisor - Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando preencho o formulário com os dados
      | Campo                                                     | Tipo     | Valor                          |
      | Período                                                   | Lista    | [01/07/2018 até 30/09/2018]    |
      | Data do Relatório                                         | Data     | 01/10/2018                     |
      | Atividade 1                                               | Lista    | Realizada                      |
      | Atividade 2                                               | Lista    | Realizada                      |
      | Atividade 3                                               | Lista    | Realizada                      |
      | Comentários sobre o desenvolvimento das atividades        | TextArea | Tudo feito corretamente.       |
      | Realizou atividades não previstas no Plano de Atividades? | Checkbox | Desmarcar                      |
      | Nota do Estagiário                                        | Lista    |                             10 |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação do supervisor registrada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O professor orientador resolve as divergências nos relatórios
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102004" e senha "abcd"
    E clico no link "divergências pendentes de resolução"
    E olho a linha "Aluno Estágio"
    E clico no ícone de exibição
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando clico na aba "Relatórios de Atividades – Estagiário"
    Então vejo mensagem de erro "Atenção: Este relatório possui divergências com o relatório do supervisor. Verifique os campos em comum de ambos para garantir que eles possuam as mesmas informações."
    Quando clico no botão "Resolver divergências"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                  | Tipo     | Valor                    |
      | Escolha a versão       | Lista    | Usar versão do aluno     |
    E clico no botão "Confirmar escolhas"
    Então vejo mensagem de sucesso "Relatórios atualizados com sucesso."
    Quando olho para o quadro "Relatórios de Atividades – Estagiário"
    Então vejo o botão "Assinar 1º Relatório"
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O estagiário assina os relatórios semestrais de atividades
    Dado acesso a página "/"
    Quando realizo o login com o usuário "20191101011021" e senha "abcd"
    E clico no link "aguardando assinatura"
    Quando olho para o quadro "Registros de Estágios"
    Quando clico no ícone de exibição
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando clico na aba "Relatórios de Atividades – Estagiário"
    E clico no botão "Assinar 1º Relatório"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | abcd     |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando clico na aba "Relatórios de Atividades - Supervisor"
    E clico no botão "Assinar 1º Relatório"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | abcd     |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O professor orientador assina os relatórios de atividades
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102004" e senha "abcd"
    E clico no link "aguardando assinatura"
    E olho a linha "Aluno Estágio"
    E clico no ícone de exibição
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando clico na aba "Relatórios de Atividades – Estagiário"
    E clico no botão "Assinar 1º Relatório"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | abcd     |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando clico na aba "Relatórios de Atividades - Supervisor"
    E clico no botão "Assinar 1º Relatório"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | abcd     |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O supervisor assina os relatórios de atividades
    # Supervisor: Prestador 1 (50621364401)
    Dado acesso a página "/"
    Quando realizo o login com o usuário "50621364401" e senha "123"
    E clico no link "aguardando assinatura"
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando clico na aba "Relatórios de Atividades – Estagiário"
    Quando clico no botão "Assinar 1º Relatório"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | 123      |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando clico na aba "Relatórios de Atividades - Supervisor"
    Quando clico no botão "Assinar 1º Relatório"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | 123      |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O coordenador de estágio verifica estágios aptos para encerramento
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Extensão::Estágio e Afins::Estágios"
    Quando clico na aba "Apto para Encerramento"
    E olho para a listagem
    Então vejo a linha "Aluno Estágio"
    Quando acesso o menu "Sair"
