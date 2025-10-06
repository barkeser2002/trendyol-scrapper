import re

data = open('sample.html', encoding='utf-8').read()
for match in re.finditer('window', data):
    snippet = data[match.start():match.start()+80]
    print(snippet)
    if '__envoy_flash-sales-banner__PROPS' in snippet:
        print('Found target snippet')
        break
