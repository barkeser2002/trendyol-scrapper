import re

with open('sample.html', encoding='utf-8') as f:
    data = f.read()

scripts = re.findall(r'window\["(.*?)"\]=(.*?);\s*</script>', data, re.DOTALL)
print('Total matched scripts:', len(scripts))
for name, content in scripts:
    if 'merchantListing' in content:
        print('Found script name:', name)
        print(content[:500])
        break
else:
    print('No merchantListing found')
