# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros Básicos
  Cadastro das de Subtipos de contrato e Motivos de Conclusão.

  Cenário: Usuários da aplicação
    Quando a data do sistema for "10/01/2020"
    Dado os seguintes usuários
      | Nome                | Matrícula | Setor | Lotação | Email                        | CPF            | Senha | Grupo                                                  |
      | Fiscal de Contrato  | 996622    | CZN   | CZN     | fiscal_contrato@ifrn.edu.br  | 675.849.850-68 | abcd  | Fiscal de Contrato                                     |
      | Gerente de Contrato | 996623    | CZN   | CZN     | gerente_contrato@ifrn.edu.br | 347.374.140-00 | abcd  | Gerente de Contrato, Coordenador de Contrato Sistêmico |
    E os cadastros básicos do módulo contratos
    Quando acesso a página "/"
    E realizo o login com o usuário "996623" e senha "abcd"


  @do_document
  Cenário: SubTipos de Contratos
    Cadastro de Subtipos de contratos com o objetivo de agrupar
    Dado acesso a página "/"
    Quando acesso o menu "Administração::Contratos::Cadastros::Subtipos de Contratos"
    E clico no botão "Adicionar Subtipo de Contrato"
    E preencho o formulário com os dados
      | Campo            | Tipo         | Valor                                                                        |
      | Descrição        | Texto        | Serviço Continuado sem Dedicação Exclusiva de Mão de Obra - Energia Elétrica |
      | Tipo de Contrato | Autocomplete | Contrato                                                                     |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."


  @do_document
  Cenário: Motivos de Conclusão de Contratos
    Dado acesso a página "/"
    Quando acesso o menu "Administração::Contratos::Cadastros::Motivos de Conclusão de Contratos"
    E clico no botão "Adicionar Motivo de Conclusão de Contrato"
    E preencho o formulário com os dados
      | Campo     | Tipo  | Valor                          |
      | Descrição | Texto | Término da Vigência Contratual |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."


  @do_document
  Cenário: Base Legal
    Dado acesso a página "/"
    Quando acesso o menu "Administração::Contratos::Cadastros::Base Legal"
    E clico no botão "Adicionar Base Legal"
    E preencho o formulário com os dados
      | Campo     | Tipo  | Valor                          |
      | Título    | Texto | Base Legal 123                 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
