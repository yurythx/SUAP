# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Encerramento de uma Aprendizagem
    No final desse teste o estado da aprendizagem estará "Concluída".

  @do_document
  Cenário: O coordenador de estágio cadastra o encerramento da aprendizagem
    Dado acesso a página "/"
    Quando realizo o login com o usuário "102002" e senha "abcd"
    E acesso o menu "Extensão::Estágio e Afins::Aprendizagens"
    E olho para a listagem
    E olho a linha "Aluno"
    Quando clico no ícone de exibição
    Então vejo a página "Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando clico na aba "Dados do Encerramento"
    E clico no botão "Registrar Encerramento"
    Então vejo a página "Encerrar aprendizagem - Aprendizagem do aluno Aluno Estágio (20191101011021) na concedente Banco do Brasil (00000000000191)"
    Quando preencho o formulário com os dados
      | Campo                       | Tipo     | Valor                                    |
      | Encerramento por            | Lista    | Conclusão                                |
      | Motivo do Encerramento      | Lista    | Término do contrato.                     |
      | Observações                 | Textarea | Aprendizagem correu conforme o esperado. |
      | Data do Encerramento        | Data     | 30/06/2018                               |
      | Carga-Horária Prática Final | Texto    |                                      200 |
      | Comprovante de Encerramento | Arquivo  | Comprovante.pdf                          |
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Aprendizagem encerrada com sucesso."
    Quando acesso o menu "Extensão::Estágio e Afins::Aprendizagens"
    Quando clico na aba "Concluídos"
    E olho para a listagem
    Então vejo a linha "Aluno"
