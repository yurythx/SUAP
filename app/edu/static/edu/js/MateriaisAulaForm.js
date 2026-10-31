jQuery(document).ready(function () {
	var quantidade = jQuery('#id_quantidade_0');
	var quantidade2 = jQuery('#id_quantidade_1');
	var quantidade3 = jQuery('#id_quantidade_2');
	var quantidade4 = jQuery('#id_quantidade_3');
	var quantidade5 = jQuery('#id_quantidade_4');
	
	var quantidade2_wiget = jQuery('#id_descricao2').parent().parent().parent()
	var quantidade3_wiget = jQuery('#id_descricao3').parent().parent().parent()
	var quantidade4_wiget = jQuery('#id_descricao4').parent().parent().parent()
	var quantidade5_wiget = jQuery('#id_descricao5').parent().parent().parent()
	quantidade2_wiget.hide()
	quantidade3_wiget.hide()
	quantidade4_wiget.hide()
	quantidade5_wiget.hide()
	
    var upload = jQuery('#id_tipo1_0');
    var url = jQuery('#id_tipo1_1');
    var upload2 = jQuery('#id_tipo2_0');
    var url2 = jQuery('#id_tipo2_1');
    var upload3 = jQuery('#id_tipo3_0');
    var url3 = jQuery('#id_tipo3_1');
    var upload4 = jQuery('#id_tipo4_0');
    var url4 = jQuery('#id_tipo4_1');
    var upload5 = jQuery('#id_tipo5_0');
    var url5 = jQuery('#id_tipo5_1');

    var upload_wiget = jQuery('#id_arquivo1').parent().parent();
    upload_wiget.hide();
    var url_wiget = jQuery('#id_url1').parent().parent();
    url_wiget.hide();
    var upload_wiget2 = jQuery('#id_arquivo2').parent().parent();
    upload_wiget2.hide();
    var url_wiget2 = jQuery('#id_url2').parent().parent();
    url_wiget2.hide();
    var upload_wiget3 = jQuery('#id_arquivo3').parent().parent();
    upload_wiget3.hide();
    var url_wiget3 = jQuery('#id_url3').parent().parent();
    url_wiget3.hide();
    var upload_wiget4 = jQuery('#id_arquivo4').parent().parent();
    upload_wiget4.hide();
    var url_wiget4 = jQuery('#id_url4').parent().parent();
    url_wiget4.hide();
    var upload_wiget5 = jQuery('#id_arquivo5').parent().parent();
    upload_wiget5.hide();
    var url_wiget5 = jQuery('#id_url5').parent().parent();
    url_wiget5.hide();

    function configureVisibility() {
        if (upload.is(":checked")) {
            upload_wiget.show();
            url_wiget.hide();
        } else {
            upload_wiget.hide();
            url_wiget.show();
        }
        
        if (upload2.is(":checked")) {
            upload_wiget2.show();
            url_wiget2.hide();
        } else {
            upload_wiget2.hide();
            url_wiget2.show();
        }
        
        if (upload3.is(":checked")) {
            upload_wiget3.show();
            url_wiget3.hide();
        } else {
            upload_wiget3.hide();
            url_wiget3.show();
        }
        
        if (upload4.is(":checked")) {
            upload_wiget4.show();
            url_wiget4.hide();
        } else {
            upload_wiget4.hide();
            url_wiget4.show();
        }
        
        if (upload5.is(":checked")) {
            upload_wiget5.show();
            url_wiget5.hide();
        } else {
            upload_wiget5.hide();
            url_wiget5.show();
        }
        
        if (quantidade2.is(":checked")) {
        	quantidade2_wiget.show()
        }
        else if (quantidade3.is(":checked")) {
        	quantidade2_wiget.show()
        	quantidade3_wiget.show()
        }
        else if (quantidade4.is(":checked")) {
        	quantidade2_wiget.show()
        	quantidade3_wiget.show()
        	quantidade4_wiget.show()
        }
        else if (quantidade5.is(":checked")) {
        	quantidade2_wiget.show()
        	quantidade3_wiget.show()
        	quantidade4_wiget.show()
        	quantidade5_wiget.show()
        }
        
    }
    
    quantidade.on('click', function () {
    	quantidade2_wiget.hide()
    	quantidade3_wiget.hide()
    	quantidade4_wiget.hide()
    	quantidade5_wiget.hide()
    });
    quantidade2.on('click', function () {
    	quantidade2_wiget.show()
    	quantidade3_wiget.hide()
    	quantidade4_wiget.hide()
    	quantidade5_wiget.hide()
    });
    quantidade3.on('click', function () {
    	quantidade2_wiget.show()
    	quantidade3_wiget.show()
    	quantidade4_wiget.hide()
    	quantidade5_wiget.hide()
    });
    quantidade4.on('click', function () {
    	quantidade2_wiget.show()
    	quantidade3_wiget.show()
    	quantidade4_wiget.show()
    	quantidade5_wiget.hide()
    });
    quantidade5.on('click', function () {
    	quantidade2_wiget.show()
    	quantidade3_wiget.show()
    	quantidade4_wiget.show()
    	quantidade5_wiget.show()
    });

    upload.on('click', function () {
        configureVisibility();
    });

    url.on('click', function () {
        configureVisibility();
    });
    
    upload2.on('click', function () {
        configureVisibility();
    });

    url2.on('click', function () {
        configureVisibility();
    });
    
    upload3.on('click', function () {
        configureVisibility();
    });

    url3.on('click', function () {
        configureVisibility();
    });
    
    upload4.on('click', function () {
        configureVisibility();
    });

    url4.on('click', function () {
        configureVisibility();
    });
    
    upload5.on('click', function () {
        configureVisibility();
    });

    url5.on('click', function () {
        configureVisibility();
    });

    configureVisibility();

});