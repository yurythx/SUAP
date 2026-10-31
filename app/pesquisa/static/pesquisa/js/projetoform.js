$(document).ready(function(){

	if ($('#id_precisa_cep').val() == 'True') {
            $('#id_num_protocolo_cep').parent().parent().show();
    } else {
        $('#id_num_protocolo_cep').parent().parent().hide();
	}

	if ($('#id_precisa_ceua').val() == 'True') {
            $('#id_num_protocolo_ceua').parent().parent().show();
    } else {
        $('#id_num_protocolo_ceua').parent().parent().hide();
	}

	if ($('#id_precisa_sisgen').val() == 'True') {
        $('#id_num_protocolo_sisgen').parent().parent().show();
        $(".atividades_sisgen").show();
    } else {
        $('#id_num_protocolo_sisgen').parent().parent().hide();
        $(".atividades_sisgen").hide();
	}
	if ($('#id_precisa_sisbio').val() == 'True') {
        $('#id_num_protocolo_sisbio').parent().parent().show();
        $(".atividades_sisbio").show();
    } else {
        $('#id_num_protocolo_sisbio').parent().parent().hide();
        $(".atividades_sisbio").hide();
	}

	if ($('#id_vinculado_laboratorio_multiusuario').val() == 'True') {
        $("select[name='laboratorio_multiusuario']").parent().parent().show();
    } else {
        $("select[name='laboratorio_multiusuario']").parent().parent().hide();
	}

    if ($('#id_tem_ods').val() == 'True') {
        $("select[name='objetivos_desenvolvimento_sustentavel']").parent().parent().show();
        $("select[name='subobjetivos_desenvolvimento_sustentavel']").parent().parent().show();
    } else {
        $("select[name='objetivos_desenvolvimento_sustentavel']").parent().parent().hide();
        $("select[name='subobjetivos_desenvolvimento_sustentavel']").parent().parent().hide();
	}

	exibir_esconder_campo();
	if (!window.location.href.includes("editar_projeto")){
	    carrega_subobjetivos();
	}
    $("select[name='precisa_cep']").on('change', function () {
        exibir_esconder_campo();
    });

    $("select[name='precisa_ceua']").on('change', function () {
        exibir_esconder_campo();
    });

    $("select[name='precisa_sisgen']").on('change', function () {
        exibir_esconder_campo();
    });

    $("select[name='precisa_sisbio']").on('change', function () {
        exibir_esconder_campo();
    });

    $("select[name='vinculado_laboratorio_multiusuario']").on('change', function () {
        exibir_esconder_campo();
    });

    $("select[name='tem_ods']").on('change', function () {
        exibir_esconder_campo();
        carrega_subobjetivos();
    });

    $("select[name='objetivos_desenvolvimento_sustentavel']").on('change', function () {
        carrega_subobjetivos();
    });

    function exibir_esconder_campo() {
       if ($('#id_precisa_cep').val() == 'True') {
            $('#id_num_protocolo_cep').parent().parent().show();
       } else {
            $('#id_num_protocolo_cep').val("");
            $('#id_num_protocolo_cep').parent().parent().hide();
       }

       if ($('#id_precisa_ceua').val() == 'True') {
            $('#id_num_protocolo_ceua').parent().parent().show();
       } else {
            $('#id_num_protocolo_ceua').val("");
            $('#id_num_protocolo_ceua').parent().parent().hide();
       }

       if ($('#id_precisa_sisgen').val() == 'True') {
            $('#id_num_protocolo_sisgen').parent().parent().show();
            $(".atividades_sisgen").show();

       } else {
            $('#id_num_protocolo_sisgen').val("");
            $('#id_num_protocolo_sisgen').parent().parent().hide();
            $("input[name='atividades_sisgen']:checkbox").prop('checked',false);
            $(".atividades_sisgen").hide();
       }
       if ($('#id_precisa_sisbio').val() == 'True') {
            $('#id_num_protocolo_sisbio').parent().parent().show();
            $(".atividades_sisbio").show();
       } else {
            $('#id_num_protocolo_sisbio').val("");
            $('#id_num_protocolo_sisbio').parent().parent().hide();
            $("input[name='atividades_sisbio']:checkbox").prop('checked',false);
            $(".atividades_sisbio").hide();
       }
       if ($('#id_vinculado_laboratorio_multiusuario').val() == 'True') {
            $("select[name='laboratorio_multiusuario']").parent().parent().show();
            $("select[name='laboratorio_multiusuario']").parent().parent().addClass("required");
            $("select[name='laboratorio_multiusuario']").parent().prop("required", true);
       } else {
            $("select[name='laboratorio_multiusuario']").val("").trigger("change");
            $("select[name='laboratorio_multiusuario']").parent().parent().removeClass("required");
            $("select[name='laboratorio_multiusuario']").parent().parent().hide();
            $("select[name='laboratorio_multiusuario']").parent().prop("required", false);
       }


       if ($('#id_tem_ods').val() == 'True') {
            $("select[name='objetivos_desenvolvimento_sustentavel']").parent().parent().show();
            $("select[name='objetivos_desenvolvimento_sustentavel']").parent().parent().addClass("required");
            $("select[name='objetivos_desenvolvimento_sustentavel']").parent().prop("required", true);
            $("select[name='subobjetivos_desenvolvimento_sustentavel']").parent().parent().show();
       } else {
            $("select[name='objetivos_desenvolvimento_sustentavel']").val("").trigger("change");
            $("select[name='objetivos_desenvolvimento_sustentavel']").parent().parent().hide();
            $("select[name='subobjetivos_desenvolvimento_sustentavel']").val("").trigger("change");
            $("select[name='subobjetivos_desenvolvimento_sustentavel']").parent().parent().hide();
       }
    }
    function carrega_subobjetivos() {
      var selectedValues = $("select[name='objetivos_desenvolvimento_sustentavel']").val();

      if (!selectedValues || selectedValues.length === 0) {
        $("select[name='subobjetivos_desenvolvimento_sustentavel']").empty();
        return;
      }

      $.ajax({
        url: '/comum/get_subojetivos_ods_onu/',
        data: { ids: selectedValues.join(',') },
        method: 'GET',
        success: function(response) {
          $("select[name='subobjetivos_desenvolvimento_sustentavel']").empty();
            response.results.forEach(function(option) {
                $("select[name='subobjetivos_desenvolvimento_sustentavel']").append('<option value="' + option.id + '">' + option.text + '</option>');
              });
            $("select[name='subobjetivos_desenvolvimento_sustentavel']").trigger('change');
        },
        error: function() {alert('deu erro'); }
      });
    }


});
