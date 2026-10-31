from corsheaders.signals import check_request_enabled


def cors_allow_api_to_everyone(sender, request, **kwargs):
    return request.path.startswith('/api/') or request.path.startswith('/o/')


check_request_enabled.connect(cors_allow_api_to_everyone)
