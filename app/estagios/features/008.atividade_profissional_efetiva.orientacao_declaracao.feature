# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros de Orientação e da Declaração de Realização de Atividade Profissional Efetiva pelo Aluno
    No final desse teste o estado da Atividade Profissional Efetiva passará de "Em Andamento" para
    "Aptas para Conclusão".

  @do_document
  Cenário: O professor orientador cadastra uma Orientação da Atividade Profissional Efetiva
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102003" e senha "abcd"
    E clico no link "Orientações de Estágios e Afins"
    E olho para o quadro "Orientações de Atividade Profissional Efetiva"
    E olho a linha "Aluno"
    E clico no ícone de exibição
    Então vejo a página "Atividade Profissional Efetiva do(a) aluno(a) Aluno Estágio (20191101011021)"
    Quando clico na aba "Orientações"
    E clico no botão "Registrar/Agendar Orientação"
    E olho para o popup
    Então vejo os seguintes campos no formulário
      | Campo                               | Tipo     |
      | Data da Orientação                  | Data     |
      | Meio/Modalidade Utilizada           | Texto    |
      | Hora de Início                      | Texto    |
      | Local                               | Texto    |
      | Descrição do Conteúdo da Orientação | TextArea |
    Quando preencho o formulário com os dados
      | Campo                               | Tipo     | Valor                                               |
      | Meio/Modalidade Utilizada           | Texto    | reunião                                             |
      | Hora de Início                      | Texto    | 15:00                                               |
      | Local                               | Texto    | Sala C10                                            |
      | Descrição do Conteúdo da Orientação | TextArea | Tirar dúvidas e orietações relacionadas ao estágio. |
      | Data da Orientação                  | Data     | 20/08/2018                                          |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Registro/Agendamento de orientação adicionado com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O aprendiz cadastra o relatório do módulo
    Dado acesso a página "/"
    Quando realizo o login com o usuário "20191101011021" e senha "abcd"
    E clico no link "Relatório Final do Aluno Ainda Não Enviado"
    E clico na aba "Declaração de Realização de Atividade Profissional Efetiva – Aluno"
    Então vejo o quadro "Declaração de Realização de Atividade Profissional Efetiva – Aluno"
    Quando clico no botão "Enviar Declaração de Realização de Atividade Profissional Efetiva"
    E olho para o popup
    Quando preencho o formulário com os dados
      | Campo                                                                          | Tipo     | Valor                         |
      | Sobre as Atividades                                                            | Lista    | Realizadas                    |
      | Comentários sobre o desenvolvimento das atividades                             | TextArea | Tudo certo com as atividades. |
      | Realizou atividades não previstas no plano de atividades? Informe e justifique | TextArea | Não.                          |
      | Área de Formação                                                               | Lista    | Sim                           |
      | Contribuição                                                                   | Lista    | Sim                           |
      | Aplicação do Conhecimento                                                      | Lista    | Sim                           |
      | Conceito                                                                       | Lista    | Excelente                     |
      | Data da Declaração de Realização de Atividade Profissional Efetiva             | Data     | 20/01/2019                    |
      | Declaração de Realização de Atividade Profissional Efetiva                     | Arquivo  | Arquivo.pdf                   |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Declaração de realização de atividade profissional efetiva registrada com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O coordenador de estágio verifica nova situação da atividade profissional efetiva
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Ensino::Atividade Profissional Efetiva"
    E clico na aba "Aptas para Conclusão"
    E olho para a listagem
    Então vejo a linha "Aluno"
