jQuery(document).ready(function () {
    var upload = jQuery('#id_tipo_0');
    var url = jQuery('#id_tipo_1');

    var upload_wiget = jQuery('#id_arquivo').parent().parent();
    upload_wiget.hide();

    var url_wiget = jQuery('#id_url').parent().parent();
    url_wiget.hide();

    function configureVisibility() {
        if (upload.is(":checked")) {
            upload_wiget.show();
            url_wiget.hide();
        } else {
            upload_wiget.hide();
            url_wiget.show();
        }
    }

    upload.on('click', function () {
        configureVisibility();
    });

    url.on('click', function () {
        configureVisibility();
    });

    configureVisibility();

});