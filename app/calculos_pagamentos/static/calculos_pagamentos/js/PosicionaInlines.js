
jQuery(document).ready(function(){
    // IFMA/Tássio: Coloca campos inlines após/antes da div dos campos especificados
    // Pega período (e portaria) e posiciona
    var periodos = $('.js-inline-admin-formset.inline-group');
    if ($('div.form-row.field-campus.field-motivo_substituicao').length > 0) {
        periodos.insertAfter($('div.form-row.field-campus.field-motivo_substituicao'));
    }
    else {
        periodos.insertBefore(document.getElementsByClassName('form-row field-observacoes')[0].parentElement);
    }
    // Posiciona corretamente as portarias
    var portarias = jQuery("#portariafisica_set-group");
    portarias.insertBefore(document.getElementsByClassName('form-row field-servidor')[0].parentElement);

    // Reformata estilo do titulo dos Períodos de Substituição
    $('#periodosubstituicao_set-group h2').last().replaceWith('<h6><b>Períodos de Substituição</b></h6>');
});
