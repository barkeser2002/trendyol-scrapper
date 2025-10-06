import re
import json

with open('sample.html', encoding='utf-8') as f:
    data = f.read()

pattern = 'window["__envoy_flash-sales-banner__PROPS"]='
index = data.find(pattern)
if index == -1:
    raise SystemExit('Pattern not found')
start = index + len(pattern)
end = data.find('</script>', start)
text = data[start:end].strip()
print(text[:80])
parsed = json.loads(text)
print(parsed.keys())
print(parsed['product']['category'])
print('product keys:', parsed['product'].keys())
print('contains merchantListing?', 'merchantListing' in parsed['product'])
config = parsed.get('config', {})
print('config keys:', list(config.keys()))
merchant_listing = parsed['product'].get('merchantListing')
print('merchant_listing is None?', merchant_listing is None)
if merchant_listing:
    print('merchant_listing keys:', merchant_listing.keys())
    merchant = merchant_listing.get('merchant', {})
    print('merchant keys:', merchant.keys())
    print('merchant:', merchant)
    print('other count:', len(merchant_listing.get('otherMerchants', [])))
    winner = merchant_listing.get('winnerVariant')
    if winner:
        print('winner variant keys:', winner.keys())
        print('winner price:', winner.get('price'))
    others = merchant_listing.get('otherMerchants', [])
    if others:
        print('other keys sample:', others[0].keys())
        print('sample other merchant:', others[0])
