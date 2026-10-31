
function check_item(checkbox, focus_element, toggle_enable_inputs) {
	/*
	 * Adiciona a classe highlight na TR pai do ``checkbox``.
	 * 
	 * Parâmetros:
	 * - checkbox (jQuery) elemento checkbox
	 * - focus_element (jQuery) elemento que terá o foco após checkar.
	 * - toggle_enable_inputs (boolean) alterna o atributo "disabled" dos inputs
	 *                                  da mesma TR do checkbox.
	 */
	focus_element = focus_element || null;
    toggle_enable_inputs = toggle_enable_inputs || false;
	if (checkbox.checked) {
		$(checkbox).parents("tr").addClass("highlight");
		if (toggle_enable_inputs) {
			$(checkbox).parents("tr").find(":input[type!=checkbox]").attr("disabled", false);
		}
		if (focus_element) {
			focus_element.focus();
		}
	}
	else {
		$(checkbox).parents("tr").removeClass("highlight");
		if (toggle_enable_inputs) {
			$(checkbox).parents("tr").find(":input[type!=checkbox]").attr("disabled", true);			
		}
	}
}

function mostrar_totais(args) {
    // usado em templates/empenho_itens.html
    /*
     * ``valores``: lista de valores (cada item deve ter atributo "value")
     * ``qtds``: lista de quantidades (cada item deve ter atributo "value")
     * ``alvos_parciais``
     * ``alvo_final``
    */
    // consumo e permanente guardam o valor unitário com 6 casas decimais
    var CASAS_DECIMAIS = 6;
    var FATOR = Math.pow(10, CASAS_DECIMAIS);
    var ZERO = (0).toFixed(CASAS_DECIMAIS).replace(".", ",");
    var valor_total = 0;
    for (var i = 0; i < args.valores.length; i++) {
        valor = $(args.valores.eq(i)).attr("value");
        qtd = $(args.qtds.eq(i)).val();
        if (valor == null || valor == "" || qtd == null || qtd == "") {
            if (args.alvos_parciais != null) {
                args.alvos_parciais.eq(i).html(ZERO);
            }
        } else {
            valor_parcial = (parseFloat(mask_only_numbers(valor)) / FATOR) * parseFloat(qtd);
            if (args.alvos_parciais != null) {
                args.alvos_parciais.eq(i).html(mask_money_almox(valor_parcial.toFixed(CASAS_DECIMAIS)) + "");
            }
            valor_total += valor_parcial;
        }
    }
    valor_final = mask_money_almox(valor_total.toFixed(CASAS_DECIMAIS)) + "";
    if (args.alvo_final != null) {
        args.alvo_final.attr("value", valor_final);
        args.alvo_final.html(valor_final);
    }
    return valor_final;

};

function marcar(elem) {
    /*
    Adiciona ou remove classe highlight no primeiro ancestral tr.
    */
    elem = $(elem);
    if (elem.attr("checked") == true) {
        elem.parents("tr:first").addClass("highlight");
    } else {
        elem.parents("tr:first").removeClass("highlight");
    }
}

setHighlight = function(elementId, checked) {
	if (checked) {
		$("#"+elementId).addClass("highlight");
	} else {
		$("#"+elementId).removeClass("highlight");
	}
};

/* ==========
   ALMOXARIFADO: Requisição
============= */

function atualizarValorTotalNovo() { //ATUALIZA O VALOR POR ITEM E O VALOR TOTAL NA ENTRADA
    var valorTotal = 0.00;
    var existeItemIncompleto = false;
    for (numero=0; numero <= numeroUltimoItem(); numero++) {
    if ( $("div#item_"+numero).length != 0 ){ //caso o item exista na relacao
        qtd = $("#qtd_"+numero).attr("value");
        valor = $("#preco_"+numero).attr("value");
        if (qtd == null || valor == null) {
            $("#total_"+numero).attr("value","0,00");
            $("span#valor_total").html("0,00");
            existeItemIncompleto = true;
        } else {
            valorItem = (parseFloat(somenteNumeros(valor))/100) * parseFloat(qtd);
            $("#total_"+numero).attr("value",mascara_dinheiro(valorItem.toFixed(2))+"");
            valorTotal += valorItem;
        }
    }
    }
    if (!existeItemIncompleto) {
        $("span#valor_total").html(mascara_dinheiro(valorTotal.toFixed(2))+"");
    }
}

checkQuantidade = function(id) {
    qtd = document.getElementById("qtd"+id);
    if (document.getElementById("cb"+id).checked) {     
        qtd.removeAttribute("disabled");
        qtd.focus()
    } else {
        qtd.setAttribute("disabled", "");
    }
};

removeItemMaterial = function(div_id){
	if (divItensNumeroItensNovo()>1) {
		$("div#Itens > fieldset > div#"+div_id).remove();
		atualizarValorTotalNovo();
	}
};

numeroUltimoItem = function(){
	if (divItensNumeroItensNovo()>0) {
		return parseInt( $("div#Itens > fieldset > div.form-row:last").attr("ordem") );
	}
	return 0	
};


divItensNumeroItens = function() { //retorna o número de itens do #div_itens
	return $("div#itens > table").length;
};

divItensNumeroItensNovo = function() { //retorna o número de itens do #div_Itens
	return $("div#Itens > fieldset > div.form-row").length;
};

function montar_itens() {
    // usado em almoxarifado/templates/form_requisicao_usuario_pedido.html
    $("div#itens table").remove();
	html = "<table id='table_item_0'><tr><td>Material:</td><td><input type='text' id='item_0' name='itens' class='input_text' /></td><td>Qtd:</td><td><input type='text' name='quantidades' class='input_text' size='5' maxlength='5' onkeypress='mascara(this, somenteNumeros)' /></td></tr></table>"
	$("div#itens").append(html)
	createAutoComplete("item_0", "/almoxarifado/buscar_material_consumo_estoque_uo/"+$("[name=uo_id]").attr("value")+"/");
};
