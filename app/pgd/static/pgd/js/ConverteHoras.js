$(document).ready(function(){

    $('#id_tempo_planejado, #id_tempo_executado').on('change keyup paste', function(){
        let tempo = $(this).val().split(',');
        let hora = tempo[0];
        let minuto = parseInt(tempo[1] * 60 / 100);
        let horas = 0;
        if (!minuto) {
            horas = hora + 'h';
        } else {
            horas = hora + 'h ' + minuto + 'min';
        }
        $(this).next(".help").html("Corresponde a " + horas);
    });

});
