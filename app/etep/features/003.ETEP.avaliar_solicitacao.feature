# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Avaliar Solicitação de Acompanhamento

  @do_document
  Cenário: Avaliar Solicitação de Acompanhamento
    Ação executada pelo membro dos grupos Membro ETEP, Administrador Acadêmico ou etep Administrador.
    Responsável pela avaliação (deferimento ou indeferimento) das solicitações de acompanhamento.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "111124" e senha "abcd"
    E acesso o menu "Ensino::ETEP::Solicitações"
    Então vejo a página "Solicitações de Acompanhamento"
    Quando clico no ícone de exibição
    Então vejo a página "Solicitação de Acompanhamento"
    Quando clico no botão "Deferir/Acompanhar"
    Então vejo mensagem de sucesso "Solicitação deferida com sucesso."
