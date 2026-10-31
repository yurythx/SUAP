/**
 * @author dennel
 */

$(document).ready(function(){
	$("label[for=id_periodo_de_movimento_ini]").parent().parent().hide();
    $("label[for=id_periodo_de_movimento_fim]").parent().parent().hide();
	$("label[for=id_ano]").parent().parent().hide();
    
    if($("#id_tipo").val() == "recebimento"){
		$("label[for=id_periodo_de_movimento_ini]").parent().parent().show();
        $("label[for=id_periodo_de_movimento_fim]").parent().parent().show();
		$("label[for=id_ano]").parent().parent().hide();
	}
	else if($("#id_tipo").val() == "anual"){
		$("label[for=id_periodo_de_movimento_ini]").parent().parent().hide();
    	$("label[for=id_periodo_de_movimento_fim]").parent().parent().hide();
		$("label[for=id_ano]").parent().parent().show();
	}
	else{
		$("label[for=id_periodo_de_movimento_ini]").parent().parent().hide();
        $("label[for=id_periodo_de_movimento_fim]").parent().parent().hide();
		$("label[for=id_ano]").parent().parent().hide();
	}
    
	$("#id_tipo").change(function(){
		if($("#id_tipo").val() == "recebimento"){
			$("label[for=id_periodo_de_movimento_ini]").parent().parent().show();
            $("label[for=id_periodo_de_movimento_fim]").parent().parent().show();
			$("label[for=id_ano]").parent().parent().hide();
		}
		else if($("#id_tipo").val() == "anual"){
			$("label[for=id_periodo_de_movimento_ini]").parent().parent().hide();
			$("label[for=id_periodo_de_movimento_fim]").parent().parent().hide();
			$("label[for=id_ano]").parent().parent().show();
		}
		else{
			$("label[for=id_periodo_de_movimento_ini]").parent().parent().hide();
            $("label[for=id_periodo_de_movimento_fim]").parent().parent().hide();
			$("label[for=id_ano]").parent().parent().hide();
		}
	})
})
   