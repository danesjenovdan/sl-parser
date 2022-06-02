import requests
from requests.auth import HTTPBasicAuth
from parlaparser import settings

auth = HTTPBasicAuth(settings.API_AUTH[0], settings.API_AUTH[1])
ids = {}
for gov, i in ids.values():
    files = {'image': open(f'{gov}.png', 'rb')}
    requests.post(f'{settings.API_URL}/people/{i}/upload_image/', files=files, auth=auth)
