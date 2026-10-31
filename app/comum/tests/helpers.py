def debug(response):
    f = open('/tmp/testcase.html', 'w')
    f.write(response.content.decode())
    f.close()


def save_page(response):
    file = open('/tmp/testcase.html', 'w')
    file.write(response.content.decode())
    file.close()
