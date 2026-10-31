jQuery(function () {
    function configurarVisbilidade(){
        if($('#id_interno_1').prop("checked")){
            $('.form-row.instituicao').show();
            $('.form-row.historico_escolar').show();
            $('.form-row.comprovante_reconhecimento_curso').show();
        }
        if($('#id_interno_0').prop("checked")){
            $('.form-row.instituicao').hide();
            $('.form-row.historico_escolar').hide();
            $('.form-row.comprovante_reconhecimento_curso').hide();
        }
    }
    configurarVisbilidade();
    $('#id_interno_0, #id_interno_1').on("click", function(){
      configurarVisbilidade();  
    })
});
