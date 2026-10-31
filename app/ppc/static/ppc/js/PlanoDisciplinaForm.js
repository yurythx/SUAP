function atualizarHelpText() {
    var equivalencia = $('#id_equivalencia_hr_ha').val();
    var chDisciplina = $('#id_ch_disciplina').val();
    
    var ha = chDisciplina / equivalencia
    if (isNaN(ha)){
        ha = 0;
    }
    var helpText2 = `Equivale a ${ha} horas/aulas.`;
    $('#id_ch_disciplina').next('.help').text(helpText2);
}

function atualizarInfoEad() {
    
    var diretrizId = $('[id^="diretriz_"]').val();
    if (diretrizId) {
        $.ajax({
            url: `/ppc/diretriz/${diretrizId}/equivalencia_hr_ha/`,
            method: 'GET',
            success: function (data) {
                $('#id_equivalencia_hr_ha').val(data.equivalencia_hr_ha);
                atualizarHelpText();
            }
        });
    }
}

jQuery(function () {
    
    $('#id_ch_disciplina').on('keyup', function(){
        atualizarHelpText();
    });

    $('#id_ch_disciplina').on('input', function(){
        atualizarHelpText();
    });

    var diretriz = $('[id^="diretriz_"]');

    diretriz.change(function () {
        atualizarInfoEad();
    });

    // Initial call to set the help text on page load
    atualizarHelpText();
});
