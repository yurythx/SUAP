$(function () {

    const $modoExibicao = $('#id_modo_exibicao');
    const $detalhes = $('.detalhes');
    const $termos = $('.termos-responsabilidade');

    const $redesSociais = $(
        '#id_instagram_url,' +
        '#id_facebook_url,' +
        '#id_youtube_url,' +
        '#id_linkedin_url,' +
        '#id_spotify_url'
    );

    function limparRedesSociais() {
        $redesSociais.val('');
    }

    function exibeCamposExtras(modoExibicao) {
        const isMinima = modoExibicao === 'MINIMA';

        $detalhes.toggle(!isMinima);
        $termos.toggle(!isMinima);

        if (isMinima) {
            limparRedesSociais();
        }
    }

    // Estado inicial
    exibeCamposExtras($modoExibicao.val());

    // Alteração do modo de exibição
    $modoExibicao.on('change', function () {
        exibeCamposExtras(this.value);
    });

    // Antes do envio do formulário
    $('form').on('submit', function () {
        if ($modoExibicao.val() === 'MINIMA') {
            limparRedesSociais();
        }
    });

});
