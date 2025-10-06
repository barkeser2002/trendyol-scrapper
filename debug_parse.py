import re
import json

data = open('sample.html', encoding='utf-8').read()
pattern = r'window\["__envoy_flash-sales-banner__PROPS"\]=(.*?);'
match = re.search(pattern, data, re.DOTALL)
if match:
    text = match.group(1)
    parsed = json.loads(text)
    print(parsed.keys())
    print(parsed['product'].keys())
    print(parsed['product']['category'])
    merchant_listing = parsed.get('merchantListing', {})
    print(merchant_listing.keys())
    base_merchant = merchant_listing.get('merchant', {})
    print('Base merchant', base_merchant)
    other_merchants = merchant_listing.get('otherMerchants', [])
    print('Other merchants count', len(other_merchants))
    if other_merchants:
        print('Sample other merchant keys', other_merchants[0].keys())
else:
    print('Pattern not found')
