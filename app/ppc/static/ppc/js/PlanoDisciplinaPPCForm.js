function atualizarHelpText() {
    var qtdAulasEad = $('#id_qtd_aulas_ead').val();
    var equivalencia = $('#id_info_ead').val();
    var chDisciplina = $('#id_ch_disciplina').val();

    var hr_ead = qtdAulasEad * equivalencia
    var percentual = 0;
    if (chDisciplina){
        percentual = (hr_ead / chDisciplina) * 100;
    }

    if (percentual == 'Infinity' || isNaN(percentual)){
        var helpText = `Equivale a ${hr_ead} horas.`;
    }else{
        var helpText = `Equivale a ${hr_ead} horas, correspondendo a ${percentual}% da carga horária total da disciplina.`;
    }
    
    $('#id_qtd_aulas_ead').next('.help').text(helpText);
    
}

function esconderProjetoIntegrador() {
    var modalidadeProjetoIntegrador = $('#id_modalidade_projetointegrador');
    if (modalidadeProjetoIntegrador.is(':hidden')){
        modalidadeProjetoIntegrador.closest('fieldset').hide();
    }
}

jQuery(function () {

    $('#id_qtd_aulas_ead').on('keyup', function(){
        atualizarHelpText();
    });

    $('#id_qtd_aulas_ead').on('input', function(){
        atualizarHelpText();
    });

    esconderProjetoIntegrador();

    // Initial call to set the help text on page load
    atualizarHelpText();
});
