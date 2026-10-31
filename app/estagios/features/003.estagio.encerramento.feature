# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Encerramento de um Estágio
    No final desse teste o estado do estágio estará "Concluído".

  @do_document
  Cenário: O coordenador de estágio cadastra o encerramento do estágio
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Extensão::Estágio e Afins::Estágios"
    E olho para a listagem
    E olho a linha "Aluno"
    Quando clico no ícone de exibição
    Então vejo a página "Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando clico na aba "Dados do Encerramento"
    E clico no botão "Registrar Encerramento"
    Então vejo a página "Encerrar Estágio - Estágio de Aluno Estágio (20191101011021) em Banco do Brasil (00000000000191) (Pessoa Jurídica)"
    Quando preencho o formulário com os dados
      | Campo                                   | Tipo     | Valor                                                    |
      | Encerramento por                        | Lista    | Conclusão                                                |
      | Motivação do Desligamento/ Encerramento | Lista    | Por término do período previsto no Termo de Compromisso. |
      | Data do Encerramento                    | Data     | 30/09/2018                                               |
      | C.H. Final                              | Texto    |                                                      200 |
      | Termo de Realização de Estágio          | Arquivo  | Termo.pdf                                                |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Estágio encerrado com sucesso."
    Quando acesso o menu "Extensão::Estágio e Afins::Estágios"
    Quando clico na aba "Encerrados"
    #Então nao vejo mensagem de alerta "Nenhum Estágio encontrado."
