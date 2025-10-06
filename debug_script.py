import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

url = 'https://www.trendyol.com/apple/iphone-13-128-gb-yildiz-isigi-cep-telefonu-apple-turkiye-garantili-p-150059024?boutiqueId=61&merchantId=275331'
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
driver.get(url)
html = driver.page_source
driver.quit()

scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
for script in scripts:
    if 'merchantListing' in script:
        print('FOUND SCRIPT:')
        print(script[:1000])
        break
else:
    print('No script found containing merchantListing')
