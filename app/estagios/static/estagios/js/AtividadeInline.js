jQuery(document).ready(function(){
    $("h2").last()[0].insertAdjacentHTML(
        'afterend',
        '<div class="container px-2">' +
            '<p class="alert alert-info">' +
                'Inserir cada uma das atividades que será desenvolvida pelo estagiário. ' +
                'Esta relação de atividades será utilizada para a elaboração dos relatórios de atividades de estágio do supervisor e do estagiário.' +
            '</p>' +
            '<p class="alert alert-warning">' +
                'É <strong>obrigatório</strong> informar pelo menos uma atividade.' +
            '</p>' +
        '</div>'
    );
});
