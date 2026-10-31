# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Fiscalizar Contratos
   A fiscalização do contrato consiste em  anotar todas as ocorrências relacionadas à execução do contrato e quando
   necessário, deverá informar ao gestor, as faltas e os defeitos observados, na execução do contrato, seja na prestação
   do serviço ou na entregue dos bens.


  Cenário: Efetuar login no sistema
    Quando a data do sistema for "10/01/2020"
    E realizo o login com o usuário "996622" e senha "abcd"


  @do_document
  Cenário: Efetuar Medição das Parcelas
     """
    O objetivo da Medição de contrato se deve justamente para apurar a realização do contrato. A medição é um processo
    de verificação e fiscalização da realização de um serviço ou recebimento/entrega de um material. É neste momento que
    os saldos dos contratos serão atualizados com as quantidades já medidas.

    """

    Quando acesso o menu "Administração::Contratos::Contratos"
    E clico no ícone de exibição
    """
    Procure o contrato que você vai gerenciar o cronograma e clique o icone da lupa.
    """
    Então vejo a página "01/2020"
    """
    Verifique sempre se esse é o contrato que você quer gerenciar.
    """
    Quando clico na aba "Cronograma"
    E clico no botão "Efetuar Medição"
    E olho para o popup
    E preencho o formulário com os dados
      | Campo              | Tipo         | Valor         |
      | Nº do Documento    | Texto        | 0999299345123 |
      | Arquivo da Medição | Arquivo Real | Arquivo.pdf   |
      | Processo           | Autocomplete | 2020          |
      | Nota de Empenho    | Autocomplete | 2020          |
      | Valor              | Texto        | 50.000,00     |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Medição realizada com sucesso."
