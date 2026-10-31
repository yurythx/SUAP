var faces_dentes = {};
var situacoes_clinicas = {};

permitir_clique = true;

var color_item = "white";
var color_item_selecionado = "#347b3e";
var color_item_clicado = "#75ad0a";
var color_default = '#222'

jQuery(document).ready(function(){
    initOdontograma();
});

function esconder_submit_ficha_odontologica(){
    document.getElementsByName("fichaclinicaodontologia_form")[1].style.display = 'None';
}

function submeter_ficha_odontologica(){
    document.getElementsByName("fichaclinicaodontologia_form")[1].click();
}

function carregar_categorias(){
    var categorias_data = document.getElementsByName("situacao_clinica_object");
    var id, cor;
    for (var i=0; i<categorias_data.length; i++) {
        situacao_clinica = categorias_data[i].value;
        id = situacao_clinica.substring(0, situacao_clinica.indexOf("/"));
        cor = situacao_clinica.substring(situacao_clinica.indexOf("/") + 1);
        situacoes_clinicas[id] = cor;
    }
    selecao = document.getElementById("id_situacao_clinica");
    if (selecao) {
        color_item_clicado = "white";

        selecao.onchange = function(){
            if (selecao.value=="")
                color_item_clicado = "white";
            else{
                descricao = situacoes_clinicas[selecao.value];
                color_item_clicado = descricao.substring(2, 10);
                switch(color_item_clicado) {
                    case "black":
                        color_item_clicado = "#444";
                        break;
                    case "blue":
                        color_item_clicado = "#31708f";
                        break;
                    case "grey":
                        color_item_clicado = "#999";
                        break;
                    case "orange":
                        color_item_clicado = "#e98b39";
                        break;
                    case "red":
                        color_item_clicado = "#e74c3c";
                        break;
                    case "yellow":
                        color_item_clicado = "#f1c40f";
                        break;
                }
            }
        }
    }
}

function initOdontograma(){
    if (!jQuery("#odontograma").hasClass("visualizacao")) {
        jQuery("polygon").hover(function(){
            var ID = jQuery(this).attr("id");
            var fill = jQuery(this).attr("fill");
            var situacao = jQuery(this).attr("situacao");
            if (ID.length>5) {
                if (fill==color_item) {
                    jQuery(this).attr("fill", color_item_selecionado);
                }
                if (document.getElementById("arcada") && document.getElementById("n_dente") && document.getElementById("face")){
                    if (ID[0]=="A"){
                        jQuery("#arcada").html("Adulto");
                    } else {
                        jQuery("#arcada").html("Infantil");
                    }
                    if (situacao){
                        jQuery("#sit_clinica").html(situacao);
                    } else {
                        jQuery("#sit_clinica").html('');
                    }

                    if (ID[2]=="V"){
                        document.getElementById("face").innerHTML = "Vestibular";
                    } else if (ID[2]=="P") {
                        document.getElementById("face").innerHTML = "Lingual/Palatal";
                    } else if (ID[2]=="M") {
                        document.getElementById("face").innerHTML = "Mesial";
                    } else if (ID[2]=="D") {
                        document.getElementById("face").innerHTML = "Distal";
                    } else if (ID[2]=="O") {
                        document.getElementById("face").innerHTML = "Oclusal/Incisal";
                    } else if (ID[2]=="C") {
                        document.getElementById("face").innerHTML = "Área Cervical";
                    } else {
                        document.getElementById("face").innerHTML = "Raiz do Dente";
                    }
                    document.getElementById("n_dente").innerHTML = ID.substring(4);
                }
            } else {
                jQuery(this).attr("fill", color_item_selecionado);
                if (document.getElementById("arcada") && document.getElementById("n_dente") && document.getElementById("face")){
                    if (ID[0]=="A"){
                        document.getElementById("arcada").innerHTML = "Adulto";
                    } else {
                        document.getElementById("arcada").innerHTML = "Infantil";
                    }
                    document.getElementById("n_dente").innerHTML = ID.substring(2);
                    document.getElementById("face").innerHTML = "Todas";
                }
            }
        }, function() {
            var ID = jQuery(this).attr("id");
            var fill = jQuery(this).attr("fill");
            if (fill == color_item_selecionado) {
                if (ID.length>5) jQuery(this).attr("fill", color_item); else jQuery(this).attr("fill", color_item_selecionado);
            }
        });

        jQuery("polygon, text").click(function(){
            //obj pode ser uma face ou o dente inteiro, vai depender do tamanho da string que representa seu ID
            var id = jQuery(this).attr("id");
            var situacao;

            if (document.getElementById("id_situacao_clinica")){
                if  (!document.getElementById("id_situacao_clinica").value){
                    alert("Selecione uma Situação Clínica.");
                }
                if (document.getElementById("id_situacao_clinica")) {
                    situacao = document.getElementById("id_situacao_clinica").value;
                }
            } else {
                situacao = 1;
            }

            if (id.charAt(id.length-1)!="V" && permitir_clique) { // esta condição impede a ação do click em polígonos de visualização e durante a realização de uma consulta
                if (id.length > 5){ // É uma face
                    // só permite implante na raíz do dente
                    if (situacao == 24 && id[2]!="R"){
                        alert('O implante só pode ser registrado na raíz do dente.');
                        return
                    }
                    if (situacao == 25){
                        alert('A permanência prolongada do decíduo deve ser registrada apenas no número do dente decíduo.');
                        return
                    }
                    var fill = jQuery(this).attr("fill");
                    if (fill == color_item_selecionado || fill == color_item) {
                        jQuery(this).attr("fill", color_item_clicado);
                        faces_dentes[id]=situacao;
                    } else {
                        jQuery(this).attr("fill", color_item);
                        faces_dentes[id]=0;
                    }
                } else { // É o dente inteiro
                    // só permite implante na raíz do dente
                    if (situacao == 24){
                        alert('Não é permitido registrar implante no dente inteiro.');
                        return
                    }
                    if (situacao == 25 && id[0]!="I"){
                        alert('A permanência prolongada do decíduo deve ser registrada apenas no número do dente decíduo.');
                        return
                    }
                    var faceV = jQuery("polygon#" + id.substring(0,2) + "V_" + id.substring(2));
                    var faceV_fill = faceV.attr("fill");
                    var faceV_id = faceV.attr("id");
                    var faceP = jQuery("polygon#" + id.substring(0,2) + "P_" + id.substring(2));
                    var faceP_fill = faceP.attr("fill");
                    var faceP_id = faceP.attr("id");
                    var faceM = jQuery("polygon#" + id.substring(0,2) + "M_" + id.substring(2));
                    var faceM_fill = faceM.attr("fill");
                    var faceM_id = faceM.attr("id");
                    var faceD = jQuery("polygon#" + id.substring(0,2) + "D_" + id.substring(2));
                    var faceD_fill = faceD.attr("fill");
                    var faceD_id = faceD.attr("id");
                    var faceO = jQuery("polygon#" + id.substring(0,2) + "O_" + id.substring(2));
                    var faceO_fill = faceO.attr("fill");
                    var faceO_id = faceO.attr("id");

                    if (faceV_fill==color_item && faceP_fill==color_item && faceM_fill==color_item && faceD_fill==color_item && faceO_fill==color_item){
                        faceV.attr("fill", color_item_clicado);
                        faces_dentes[faceV_id]=situacao;
                        faceP.attr("fill", color_item_clicado);
                        faces_dentes[faceP_id]=situacao;
                        faceM.attr("fill", color_item_clicado);
                        faces_dentes[faceM_id]=situacao;
                        faceD.attr("fill", color_item_clicado);
                        faces_dentes[faceD_id]=situacao;
                        faceO.attr("fill", color_item_clicado);
                        faces_dentes[faceO_id]=situacao;
                    } else {
                        faceV.attr("fill", color_item);
                        faces_dentes[faceV_id]=0;
                        faceP.attr("fill", color_item);
                        faces_dentes[faceP_id]=0;
                        faceM.attr("fill", color_item);
                        faces_dentes[faceM_id]=0;
                        faceD.attr("fill", color_item);
                        faces_dentes[faceD_id]=0;
                        faceO.attr("fill", color_item);
                        faces_dentes[faceO_id]=0;
                    }
                }
                if (document.getElementById("id_faces_marcadas")!=null){
                    jQuery("#id_faces_marcadas").val(faces_selecionadas(1)); //O paramentro 1 indica que se trata do odontograma de marcação.
                } else {
                    jQuery("#id_faces").val(faces_selecionadas(2)); //O paramentro 2 indica que se trata do odontograma fixo.
                }
            }
        });
    }
}

function faces_selecionadas(odontograma){
    var key, faces="";
    if (odontograma == 1){ //Odontograma de marcação
        for (key in faces_dentes){
            if (faces_dentes[key]!=0 && faces_dentes[key]!="") faces+=key+"-";
        }
    }else{ //Odontograma fixo
        for (key in faces_dentes){
            if (faces_dentes[key]!=0 && faces_dentes[key]!="") faces+=key+"_"+faces_dentes[key]+"-";
        }
    }
    return faces;
}

function restaurar_odontograma(){
	faces = document.getElementById("faces_alteradas").value;
	var lista = [];
	while(faces.length > 1){
        lista[lista.length] = faces.substring(0, faces.indexOf("-"));
        faces = faces.substring(faces.indexOf("-")+1, faces.length);
    }
    for (i=0; i<lista.length; i++){
    	situacao = lista[i].substring(7);

    	id_face = lista[i].substring(0, 6);
    	faces_dentes[id_face]=situacao;
    	face = document.getElementById(id_face);
    	descricao = situacoes_clinicas[situacao]
    	preenchimento = descricao.substring(0, descricao.indexOf("-"));
    	cor = descricao.substring(descricao.indexOf("-")+1, descricao.length);
    	const text = document.querySelector('input[name="situacao_clinica_object"][value="'+situacao+'/'+descricao+'"]').parentNode.textContent.trim();
    	switch(cor) {
            case "black":
                cor = "#444";
                break;
            case "blue":
                cor = "#31708f";
                break;
            case "grey":
                cor = "#999";
                break;
            case "orange":
                cor = "#e98b39";
                break;
            case "red":
                cor = "#e74c3c";
                break;
            case "yellow":
                cor = "#f1c40f";
                break;
        }
        jQuery(face).attr("fill", cor);
        jQuery(face).attr("situacao", text);
        jQuery(document.getElementById(id_face+"V")).attr("fill", cor);// Marcação no odontograma de visualização
        jQuery(document.getElementById(id_face+"V")).attr("situacao", text);// Marcação no odontograma de visualização
	}
}

function desenhar_odontograma(local){
    odontograma = "<div style='text-align:center' class='hasSVG'>";
    odontograma += "<svg version='1.1' width='620px' height='330px'>";
    odontograma += "<g transform='scale(1.5)'>";

    /* Arcada de adulto */
    for (i=0; i<8; i++){
        odontograma += "<g transform='translate("+(0+i*25)+",20)'>";
        odontograma += "<polygon id='A_R_1"+(8-i)+"' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_C_1"+(8-i)+"' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_V_1"+(8-i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_P_1"+(8-i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_M_1"+(8-i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_D_1"+(8-i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_O_1"+(8-i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<text id='A_1"+(8-i)+"' x='4' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>1"+(8-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",20)'>";
        odontograma += "<polygon id='A_R_2"+(i+1)+"' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_C_2"+(i+1)+"' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_V_2"+(i+1)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_P_2"+(i+1)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_D_2"+(i+1)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_M_2"+(i+1)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_O_2"+(i+1)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<text id='A_2"+(i+1)+"' x='4' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>2"+(i+1)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(0+i*25)+",180)'>";
        odontograma += "<polygon id='A_P_4"+(8-i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_V_4"+(8-i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_M_4"+(8-i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_D_4"+(8-i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_O_4"+(8-i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_C_4"+(8-i)+"' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_R_4"+(8-i)+"' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<text  id='A_4"+(8-i)+"' x='4' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>4"+(8-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",180)'>";
        odontograma += "<polygon id='A_P_3"+(i+1)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_V_3"+(i+1)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_D_3"+(i+1)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_M_3"+(i+1)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_O_3"+(i+1)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_C_3"+(i+1)+"' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='A_R_3"+(i+1)+"' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<text id='A_3"+(i+1)+"' x='4' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>3"+(i+1)+"</text>";
        odontograma += "</g>";
    }
    /* Arcada infantil */
    for (i=0; i<5; i++){
        odontograma += "<g transform='translate("+(75+i*25)+",75)'>";
        odontograma += "<polygon id='I_R_"+(55-i)+"' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_C_"+(55-i)+"' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_V_"+(55-i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_P_"+(55-i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_M_"+(55-i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_D_"+(55-i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_O_"+(55-i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<text id='I_"+(55-i)+"' x='5' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(55-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",75)'>";
        odontograma += "<polygon id='I_R_"+(61+i)+"' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_C_"+(61+i)+"' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_V_"+(61+i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_P_"+(61+i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_D_"+(61+i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_M_"+(61+i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_O_"+(61+i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<text id='I_"+(61+i)+"' x='5' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(61+i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(75+i*25)+",125)'>";
        odontograma += "<polygon id='I_P_"+(85-i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_V_"+(85-i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_M_"+(85-i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_D_"+(85-i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_O_"+(85-i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_C_"+(85-i)+"' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_R_"+(85-i)+"' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<text id='I_"+(85-i)+"' x='5' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(85-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",125)'>";
        odontograma += "<polygon id='I_P_"+(71+i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_V_"+(71+i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_D_"+(71+i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_M_"+(71+i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_O_"+(71+i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_C_"+(71+i)+"' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<polygon id='I_R_"+(71+i)+"' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5' style='cursor:pointer'></polygon>";
        odontograma += "<text id='I_"+(71+i)+"' x='5' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(71+i)+"</text>";
        odontograma += "</g>";
    }

    odontograma += "</g></svg></div>";
    document.getElementById("odontograma_fixo").innerHTML = odontograma;
}

function desenhar_odontograma_marcacao(){
    odontograma = "<div style='text-align:center' class='hasSVG'>";
    odontograma += "<svg version='1.1' width='620px' height='330px'>";
    odontograma += "<g transform='scale(1.5)'>";

    /* Arcada de adulto */
    for (i=0; i<8; i++){
        odontograma += "<g transform='translate("+(0+i*25)+",20)'>";
        odontograma += "<polygon id='A_R_1"+(8-i)+"' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_C_1"+(8-i)+"' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_V_1"+(8-i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_P_1"+(8-i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_M_1"+(8-i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_D_1"+(8-i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_O_1"+(8-i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='A_1"+(8-i)+"' x='4' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>1"+(8-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",20)'>";
        odontograma += "<polygon id='A_R_2"+(i+1)+"' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_C_2"+(i+1)+"' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_V_2"+(i+1)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_P_2"+(i+1)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_D_2"+(i+1)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_M_2"+(i+1)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_O_2"+(i+1)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='A_2"+(i+1)+"' x='4' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>2"+(i+1)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(0+i*25)+",180)'>";
        odontograma += "<polygon id='A_P_4"+(8-i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_V_4"+(8-i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_M_4"+(8-i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_D_4"+(8-i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_O_4"+(8-i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_C_4"+(8-i)+"' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_R_4"+(8-i)+"' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text  id='A_4"+(8-i)+"' x='4' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>4"+(8-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",180)'>";
        odontograma += "<polygon id='A_P_3"+(i+1)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_V_3"+(i+1)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_D_3"+(i+1)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_M_3"+(i+1)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_O_3"+(i+1)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_C_3"+(i+1)+"' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_R_3"+(i+1)+"' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='A_3"+(i+1)+"' x='4' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>3"+(i+1)+"</text>";
        odontograma += "</g>";
    }
    /* Arcada infantil */
    for (i=0; i<5; i++){
        odontograma += "<g transform='translate("+(75+i*25)+",75)'>";
        odontograma += "<polygon id='I_R_"+(55-i)+"' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_C_"+(55-i)+"' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_V_"+(55-i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_P_"+(55-i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_M_"+(55-i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_D_"+(55-i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_O_"+(55-i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='I_"+(55-i)+"' x='5' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(55-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",75)'>";
        odontograma += "<polygon id='I_R_"+(61+i)+"' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_C_"+(61+i)+"' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_V_"+(61+i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_P_"+(61+i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_D_"+(61+i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_M_"+(61+i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_O_"+(61+i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='I_"+(61+i)+"' x='5' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(61+i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(75+i*25)+",125)'>";
        odontograma += "<polygon id='I_P_"+(85-i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_V_"+(85-i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_M_"+(85-i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_D_"+(85-i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_O_"+(85-i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_C_"+(85-i)+"' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_R_"+(85-i)+"' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='I_"+(85-i)+"' x='5' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(85-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",125)'>";
        odontograma += "<polygon id='I_P_"+(71+i)+"' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_V_"+(71+i)+"' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_D_"+(71+i)+"' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_M_"+(71+i)+"' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_O_"+(71+i)+"' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_C_"+(71+i)+"' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_R_"+(71+i)+"' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='I_"+(71+i)+"' x='5' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(71+i)+"</text>";
        odontograma += "</g>";
    }
    odontograma += "</g></svg></div>";
    document.getElementById("odontograma_dinamico").innerHTML = odontograma;
}

function desenhar_odontograma_visualizacao(){
    odontograma = "<div style='text-align:center' class='hasSVG'>";
    odontograma += "<svg version='1.1' width='620px' height='330px'>";
    odontograma += "<g transform='scale(1.5)'>";

    /* Arcada de adulto */
    for (i=0; i<8; i++){
        odontograma += "<g transform='translate("+(0+i*25)+",20)'>";
        odontograma += "<polygon id='A_R_1"+(8-i)+"V' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_C_1"+(8-i)+"V' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_V_1"+(8-i)+"V' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_P_1"+(8-i)+"V' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_M_1"+(8-i)+"V' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_D_1"+(8-i)+"V' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_O_1"+(8-i)+"V' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='A_1"+(8-i)+"V' x='4' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>1"+(8-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",20)'>";
        odontograma += "<polygon id='A_R_2"+(i+1)+"V' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_C_2"+(i+1)+"V' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_V_2"+(i+1)+"V' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_P_2"+(i+1)+"V' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_D_2"+(i+1)+"V' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_M_2"+(i+1)+"V' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_O_2"+(i+1)+"V' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='A_2"+(i+1)+"V' x='4' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>2"+(i+1)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(0+i*25)+",180)'>";
        odontograma += "<polygon id='A_P_4"+(8-i)+"V' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_V_4"+(8-i)+"V' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_M_4"+(8-i)+"V' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_D_4"+(8-i)+"V' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_O_4"+(8-i)+"V' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_C_4"+(8-i)+"V' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_R_4"+(8-i)+"V' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text  id='A_4"+(8-i)+"V' x='4' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>4"+(8-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",180)'>";
        odontograma += "<polygon id='A_P_3"+(i+1)+"V' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_V_3"+(i+1)+"V' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_D_3"+(i+1)+"V' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_M_3"+(i+1)+"V' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_O_3"+(i+1)+"V' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_C_3"+(i+1)+"V' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='A_R_3"+(i+1)+"V' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='A_3"+(i+1)+"V' x='4' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>3"+(i+1)+"</text>";
        odontograma += "</g>";
    }
    /* Arcada infantil */
    for (i=0; i<5; i++){
        odontograma += "<g transform='translate("+(75+i*25)+",75)'>";
        odontograma += "<polygon id='I_R_"+(55-i)+"V' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_C_"+(55-i)+"V' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_V_"+(55-i)+"V' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_P_"+(55-i)+"V' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_M_"+(55-i)+"V' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_D_"+(55-i)+"V' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_O_"+(55-i)+"V' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='I_"+(55-i)+"V' x='5' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(55-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",75)'>";
        odontograma += "<polygon id='I_R_"+(61+i)+"V' points='5,-9 15,-9 10,-18' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_C_"+(61+i)+"V' points='5,-7 15,-7 20,-2 0,-2' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_V_"+(61+i)+"V' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_P_"+(61+i)+"V' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_D_"+(61+i)+"V' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_M_"+(61+i)+"V' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_O_"+(61+i)+"V' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='I_"+(61+i)+"V' x='5' y='30' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(61+i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(75+i*25)+",125)'>";
        odontograma += "<polygon id='I_P_"+(85-i)+"V' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_V_"+(85-i)+"V' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_M_"+(85-i)+"V' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_D_"+(85-i)+"V' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_O_"+(85-i)+"V' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_C_"+(85-i)+"V' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_R_"+(85-i)+"V' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='I_"+(85-i)+"V' x='5' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(85-i)+"</text>";
        odontograma += "</g>";
        odontograma += "<g transform='translate("+(210+i*25)+",125)'>";
        odontograma += "<polygon id='I_P_"+(71+i)+"V' points='0,0 20,0 15,5 5,5' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_V_"+(71+i)+"V' points='5,15 15,15 20,20 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_D_"+(71+i)+"V' points='15,5 20,0 20,20 15,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_M_"+(71+i)+"V' points='0,0 5,5 5,15 0,20' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_O_"+(71+i)+"V' points='5,5 15,5 15,15 5,15' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_C_"+(71+i)+"V' points='0,22 20,22 15,27 5,27' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<polygon id='I_R_"+(71+i)+"V' points='15,29 5,29 10,38' fill='white' situacao='' stroke='" + color_default + "' stroke-width='0.5'></polygon>";
        odontograma += "<text id='I_"+(71+i)+"V' x='5' y='-3' fill='" + color_default + "' stroke='" + color_default + "' stroke-width='0.1'>"+(71+i)+"</text>";
        odontograma += "</g>";
    }
    odontograma += "</g></svg></div>";
    document.getElementById("odontogramaSVG").innerHTML = odontograma;
}
