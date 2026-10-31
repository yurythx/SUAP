# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Encerramento de uma Atividade Profissional Efetiva
    No final desse teste o estado da atividade profissional efetiva estará "Concluída".

  @do_document
  Cenário: O coordenador de estágio cadastra o encerramento da atividade profissional efetiva
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Ensino::Atividade Profissional Efetiva"
    E olho para a listagem
    E olho a linha "Aluno"
    Quando clico no ícone de exibição
    Então vejo a página "Atividade Profissional Efetiva do(a) aluno(a) Aluno Estágio (20191101011021)"
    Quando clico na aba "Dados do Encerramento"
    E clico no botão "Registrar Encerramento"
    E olho para o popup
    Então vejo os seguintes campos no formulário
      | Campo                  | Tipo     |
      | Data de Encerramento   | Data     |
      | Carga Horária Cumprida | Texto    |
      | Observações            | Textarea |
    Quando preencho o formulário com os dados
      | Campo                  | Tipo     | Valor            |
      | Carga Horária Cumprida | Texto    |              200 |
      | Observações            | Textarea | Correu tudo bem. |
      | Data de Encerramento   | Data     | 31/12/2018       |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Atividade Profissional Efetiva encerrada com sucesso."
    Quando acesso o menu "Ensino::Atividade Profissional Efetiva"
    Quando clico na aba "Concluídas"
    E olho para a listagem
    Então vejo a linha "Aluno"
