# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro Gerais da ETEP

  Cenário: Adicionando os usuários necessários para os testes ETEP
    Dado os seguintes usuários
      | Nome            | Matrícula      | Setor | Lotação | Email                   | CPF            | Senha | Grupo                |
      | Membro ETEP     |         111123 | CZN   | CZN     | membro_etep@ifrn.edu.br | 951.272.780-30 | abcd  | Membro ETEP          |
      | Admin ETEP      |         111124 | CZN   | CZN     | admin_etep@ifrn.edu.br  | 627.251.080-20 | abcd  | etep Administrador   |
      | Secretario Acad |         111125 | CZN   | CZN     | sec_acad@ifrn.edu.br    | 443.280.800-40 | abcd  | Secretário Acadêmico |
      | Aluno ETEP      | 20131101011031 | CZN   | CZN     | aluno_etep@ifrn.edu.br  | 005.591.980-43 | abcd  | Aluno                |

  @do_document
  Cenário: Cadastro Gerais da ETEP
    Cadastro gerais da ETEP.
    Ação executada por um membro do grupo "etep Administrador". É responsável por cadastrar
    Tipo de Acompanhamento, Tipo de Atividade, Tipo de Documento e Tipo de Acompanhamento.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "111124" e senha "abcd"
    E acesso o menu "Ensino::ETEP::Cadastros::Tipos de Acompanhamento"
    Então vejo a página "Tipos de Acompanhamentos"
    E vejo o botão "Adicionar Tipo de Acompanhamento"
    Quando clico no botão "Adicionar Tipo de Acompanhamento"
    Então vejo a página "Adicionar Tipo de Acompanhamento"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo  |
      | Tipo      | Texto |
      | Descrição | Texto |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo  | Valor                                                                 |
      | Tipo      | Texto | Aprendizagem                                                          |
      | Descrição | Texto | Rendimento, dificuldade de aprendizagem, não realização de atividades |
    E clico no botão "Salvar"
    Quando acesso o menu "Ensino::ETEP::Cadastros::Tipos de Acompanhamento"
    Então vejo a página "Tipos de Acompanhamentos"
    E vejo o botão "Adicionar Tipo de Acompanhamento"
    Quando clico no botão "Adicionar Tipo de Acompanhamento"
    Então vejo a página "Adicionar Tipo de Acompanhamento"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo  |
      | Tipo      | Texto |
      | Descrição | Texto |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo  | Valor                                                                                                |
      | Tipo      | Texto | Comportamento                                                                                        |
      | Descrição | Texto | indisciplina, participação, uso de celular, conversas paralelas, dorme em sala de aula, desmotivação |
    E clico no botão "Salvar"
    Quando acesso o menu "Ensino::ETEP::Cadastros::Tipos de Atividade"
    Então vejo a página "Tipos de Atividade"
    E vejo o botão "Adicionar Tipo de Atividade"
    Quando clico no botão "Adicionar Tipo de Atividade"
    Então vejo a página "Adicionar Tipo de Atividade"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo  |
      | Tipo      | Texto |
      | Descrição | Texto |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo | Tipo  | Valor            |
      | Tipo  | Texto | Atividade diária |
    E clico no botão "Salvar"
    Quando acesso o menu "Ensino::ETEP::Cadastros::Tipos de Documento"
    Então vejo a página "Tipos de Documento"
    E vejo o botão "Adicionar Tipo de Documento"
    Quando clico no botão "Adicionar Tipo de Documento"
    Então vejo a página "Adicionar Tipo de Documento"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo  |
      | Tipo      | Texto |
      | Descrição | Texto |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo  | Valor              |
      | Tipo      | Texto | Planilhas          |
      | Descrição | Texto | (documentos excel) |
    E clico no botão "Salvar"
    Quando acesso o menu "Ensino::ETEP::Cadastros::Tipos de Encaminhamento"
    Então vejo a página "Tipo de Encaminhamentos"
    E vejo o botão "Adicionar Tipo de Encaminhamento"
    Quando clico no botão "Adicionar Tipo de Encaminhamento"
    Então vejo a página "Adicionar Tipo de Encaminhamento"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo  |
      | Tipo      | Texto |
      | Descrição | Texto |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo  | Valor                  |
      | Tipo      | Texto | Atendimento domiciliar |
      | Descrição | Texto | Atendimento domiciliar |
    E clico no botão "Salvar"
