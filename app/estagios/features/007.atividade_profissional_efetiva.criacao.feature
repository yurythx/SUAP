# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de uma Atividade Profissional Efetiva
    Essa funcionalidade cadastra uma Atividade Profissional Efetiva. No final
    desse teste o estado da estará "Em Andamento".

  @do_document
  Cenário: O coordenador de estágio cria uma nova atividade profissional efetiva
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Ensino::Atividade Profissional Efetiva"
    Então vejo a página "Atividades Profissionais Efetivas"
    #E vejo mensagem de alerta "Nenhum Atividade Profissional Efetiva encontrado."
    Quando clico no botão "Adicionar Atividade Profissional Efetiva"
    Então vejo a página "Adicionar Atividade Profissional Efetiva"
    E vejo os seguintes campos no formulário
      | Campo                                     | Tipo         |
      | Aluno                                     | Autocomplete |
      | Instituição de Realização da Atividade    | Texto        |
      | Razão Social                              | Texto        |
      | Orientador                                | Autocomplete |
      | Tipo desta Atividade Profissional Efetiva | Lista        |
      | Descrição de Outro Tipo                   | Texto        |
      | Situação da Atividade                     | Lista        |
    Quando preencho o formulário com os dados
      | Campo                                     | Tipo         | Valor                    |
      | Aluno                                     | Autocomplete | 20191101011021           |
      | Instituição de Realização da Atividade    | Texto        | Empresa                  |
      | Razão Social                              | Texto        | Empresa s.a.             |
      | Orientador                                | Autocomplete |                   102003 |
      | Tipo desta Atividade Profissional Efetiva | Lista        | Emprego, Cargo ou Função |
      | Descrição de Outro Tipo                   | Texto        |                          |
      | Situação da Atividade                     | Lista        | Em Andamento             |
      | Data de Início                            | Data         | 01/01/2018               |
      | Data Prevista para Encerramento           | Data         | 31/12/2018               |
      | Carga Horária Semanal                     | Texto        |                       40 |
      | Documentação Comprobatória                | Arquivo      | documentacao.pdf         |
      | Plano de Atividades                       | Arquivo      | plano_atividades.pdf     |
      | Atividades Planejadas                     | Textarea     | atividade 1, 2, 3        |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
    Quando acesso o menu "Sair"

  Esquema do Cenário: Verifica a visualização da Atividade Profissional Efetiva pelo <Papel>
    Dado acesso a página "/"
    Quando realizo o login com o usuário "<Papel>" e senha "abcd"
    E acesso o menu "Ensino::Atividade Profissional Efetiva"
    Então vejo a página "Atividades Profissionais Efetivas"
    #E nao vejo mensagem de alerta "Nenhum Atividade Profissional Efetiva encontrado."
    Quando acesso o menu "Sair"

    Exemplos:
      | Papel  |
      | 102001 |
      | 102002 |

  @do_document
  Cenário: O coordenador de Executa Notificações de Pendências de Todas as Atividades Profissionais Efetivas
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Ensino::Atividade Profissional Efetiva"
    Então vejo a página "Atividades Profissionais Efetivas"
    Quando clico no botão "Enviar Notificações de Pendências"
    Então vejo mensagem de sucesso "Foram enviados e-mails referentes às atividades profissionais efetivas com pendências."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: O coordenador de Executa Notificação de Pendências de uma Atividade Profissional Efetiva em Particular
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Ensino::Atividade Profissional Efetiva"
    E olho para a listagem
    E olho a linha "Aluno"
    Quando clico no ícone de exibição
    Então vejo a página "Atividade Profissional Efetiva do(a) aluno(a) Aluno Estágio (20191101011021)"
    Quando clico na aba "Notificações"
    Quando clico no botão "Enviar Notificações"
    Então vejo mensagem de sucesso "Notificações da Atividade Profissional Efetiva do(a) aluno(a) Aluno Estágio (20191101011021) enviadas com sucesso."
