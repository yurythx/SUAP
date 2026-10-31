# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros de visitas e relatórios de uma aprendizagem
  pre-requisitos para encerramento da aprendizagem. No final desse teste o estado da aprendizagem passará de "Em Andamento" para "Apto para Conclusão".

  @do_document
  Cenário: O professor orientador cadastra a Visita do semestre
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102003" e senha "abcd"
    E clico no link "Orientações de Estágios e Afins"
    E olho a linha "Aluno Estágio"
    E clico no ícone de exibição
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Visitas do Orientador"
    E clico no botão "Registrar Visita"
    Quando preencho o formulário com os dados
      | Campo                                          | Tipo     | Valor                            |
      | Data da Visita                                 | Data     | 15/06/2018                       |
      | Ambiente Adequado                              | Checkbox | Marcar                           |
      | Justificativa para Ambiente Inadequado         | TextArea |                                  |
      | Desenvolvimento Atividades Previstas           | Checkbox | Marcar                           |
      | Desenvolvimento Atividades Fora da Competência | Checkbox | Desmarcar                        |
      | Desenvolvimento Atividades Não-Previstas       | Checkbox | Desmarcar                        |
      | Atividades Não-Previstas                       | TextArea |                                  |
      | Apoiado pelo Supervisor                        | Checkbox | Marcar                           |
      | Direitos Respeitados                           | Checkbox | Marcar                           |
      | Especificar direitos não respeitados           | TextArea |                                  |
      | Aprendizagem Satisfatória                      | Checkbox | Marcar                           |
      | Informações Adicionais                         | TextArea | Correu tudo bem na aprendizagem. |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Visita adicionada com sucesso."
    Quando clico na aba "Visitas do Orientador"
    Então vejo o texto "Relatório da Visita realizada em 15/06/2018 ainda não assinado."
    E vejo o botão "Assinar o Relatório da Visita do dia 15/06/2018"
    Quando clico no botão "Assinar o Relatório da Visita do dia 15/06/2018"
    E olho para o popup
    Então vejo o texto "Assinar Relatório de Visita a Organização Concedente"
    Quando preencho o formulário com os dados
      | Campo                  | Tipo     | Valor  |
      | Senha para confirmação | senha    | abcd   |
    E clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O professor orientador cadastra um Agendamento de Orientação da Aprendizagem
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102003" e senha "abcd"
    E clico no link "Orientações de Estágios e Afins"
    E olho a linha "Aluno Estágio"
    E clico no ícone de exibição
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Atividades de Orientação"
    E clico no botão "Agendar Orientação"
    E olho para o popup
    Então vejo os seguintes campos no formulário
      | Campo                               | Tipo     |
      | Data da Reunião de Orientação       | Data     |
      | Hora de Início                      | Texto    |
      | Local                               | Texto    |
      | Descrição do Conteúdo da Orientação | TextArea |
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor                                               |
      | Hora de Início                      | Texto    | 14:00                                               |
      | Local                               | Texto    | Sala C10                                            |
      | Descrição do Conteúdo da Orientação | TextArea | Tirar dúvidas e orietações relacionadas ao estágio. |
      | Data da Reunião de Orientação       | Data     | 01/06/2018                                          |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Agendamento de orientação adicionado com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O aprendiz cadastra seu relatório de atividades
    Dado acesso a página "/"
    Quando realizo o login com o usuário "20191101011021" e senha "abcd"
    E clico no link "Rel. Atividades Pendentes"
    Quando olho para o quadro "Registros de Aprendizagem"
    Quando clico no ícone de exibição
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Relatórios de Atividades – Aprendiz"
    Quando clico no botão "Registrar/Editar Relatório"
    Então vejo a página "Submeter Relatório do Semestre I (de 01/01/2018 até 30/06/2018) - Aprendiz"
    Quando preencho o formulário com os dados
      | Campo                                                                      | Tipo     | Valor                                           |
      | Sobre as Atividades                                                        | Lista    | Realizadas                                      |
      | Detalhe a realização das atividades                                        | TextArea | Tudo certo com as atividades.                   |
      | Realizou atividades não previstas no resumo do curso? Informe e justifique | TextArea | Não.                                            |
      | Área de Formação                                                           | Lista    | Sim                                             |
      | Contribuição da Aprendizagem                                               | Lista    | Sim                                             |
      | Aplicação do Conhecimento                                                  | Lista    | Sim                                             |
      | Conceito                                                                   | Lista    | Excelente                                       |
      | Comentários gerais sobre o desenvolvimento das atividades                  | TextArea | No geral, tudo certo com as atividades.         |
      | Comentários e Sugestões                                                    | TextArea | Sugiro alinhamento com a instituição de ensino. |
      | Data do Relatório                                                          | Data     | 15/01/2019                                      |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação registrada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O coordenador de estágio cadastra o relatório de atividades do empregado monitor
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Extensão::Estágio e Afins::Aprendizagens"
    E olho para a listagem
    E olho a linha "Aluno Estágio"
    Quando clico no ícone de exibição
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Relatórios de Atividades – Empregado Monitor"
    Quando clico no botão "Registrar/Editar Relatório"
    Então vejo a página "Submeter Relatório do Semestre I (de 01/01/2018 até 30/06/2018) - Empregado Monitor"
    Quando preencho o formulário com os dados
      | Campo                                                                      | Tipo     | Valor                                             |
      | Sobre as Atividades                                                        | Lista    | Realizadas                                        |
      | Detalhe a realização das atividades                                        | TextArea | Tudo certo com as atividades.                     |
      | Realizou atividades não previstas no resumo do curso? Informe e justifique | TextArea | Sim.                                              |
      | Nota do Aprendiz                                                           | Lista    |                                                10 |
      | Comentários e Sugestões                                                    | TextArea | Sugiro afiwebnamento com a instituição de ensino. |
      | Data do Relatório                                                          | Data     | 15/01/2019                                        |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação registrada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O professor orientador resolve as divergências nos relatórios
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102003" e senha "abcd"
    E clico no link "Orientações de Estágios e Afins"
    E olho a linha "Aluno Estágio"
    E clico no ícone de exibição
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Relatórios de Atividades – Aprendiz"
    E olho para a tabela
    Então vejo a linha "Possui informações conflitantes com relatório do monitor."
    Quando clico no botão "Resolver divergências"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                  | Tipo     | Valor                    |
      | Escolha a versão       | Lista    | Usar versão do aluno     |
    E clico no botão "Confirmar escolhas"
    Então vejo mensagem de sucesso "Relatórios atualizados com sucesso."
    Quando olho para a tabela
    Então vejo a linha "Assinaturas pendentes: Aprendiz, Empregado(a) Monitor(a) e Orientador(a)"
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O aprendiz assina os relatórios de atividades
    Dado acesso a página "/"
    Quando realizo o login com o usuário "20191101011021" e senha "abcd"
    E clico no link "aguardando assinatura"
    Quando olho para o quadro "Registros de Aprendizagem"
    Quando clico no ícone de exibição
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Relatórios de Atividades – Aprendiz"
    E clico no botão "Assinar"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | abcd     |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando clico na aba "Relatórios de Atividades – Empregado Monitor"
    E clico no botão "Assinar"
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
    Quando realizo o login com o usuário "102003" e senha "abcd"
    E clico no link "aguardando assinatura"
    E olho a linha "Aluno Estágio"
    E clico no ícone de exibição
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Relatórios de Atividades – Aprendiz"
    E clico no botão "Assinar"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | abcd     |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando clico na aba "Relatórios de Atividades – Empregado Monitor"
    E clico no botão "Assinar"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | abcd     |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O empregado monitor assina os relatórios de atividades
    Dado acesso a página "/"
    Quando realizo o login com o usuário "50621364401" e senha "123"
    E clico no link "aguardando assinatura"
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Relatórios de Atividades – Aprendiz"
    Quando clico no botão "Assinar"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | 123      |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando clico na aba "Relatórios de Atividades – Empregado Monitor"
    Quando clico no botão "Assinar"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor    |
      | Senha para confirmação              | senha    | 123      |
    Quando clico no botão "Assinar"
    Então vejo mensagem de sucesso "Assinatura eletrônica realizada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O coordenador de estágio verifica aprendizagens aptas para encerramento
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Extensão::Estágio e Afins::Aprendizagens"
    Quando clico na aba "Apto para Conclusão"
    E olho para a listagem
    Então vejo a linha "Aluno Estágio"
    Quando acesso o menu "Sair"
