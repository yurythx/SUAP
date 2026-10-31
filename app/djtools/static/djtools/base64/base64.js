base64_encode = function ( str ) {
    return window.btoa(unescape(encodeURIComponent( str )));
}

base64_decode = function ( str ) {
    return decodeURIComponent(escape(window.atob( str )));
}
