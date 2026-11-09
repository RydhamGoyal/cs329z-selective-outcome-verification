"""Validate the project's OpenRouter key without printing the credential or spending tokens."""
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from dotenv import dotenv_values

key=(dotenv_values(Path('.env')).get('OPENROUTER_API_KEY') or '').strip()
if not key:
    raise SystemExit('OPENROUTER_API_KEY is missing from this project .env')
request=Request('https://openrouter.ai/api/v1/key',headers={'Authorization':f'Bearer {key}'})
try:
    with urlopen(request,timeout=15) as response:
        data=json.load(response).get('data',{})
        print('authentication: OK')
        print('disabled:',data.get('disabled','not reported'))
        print('expires_at:',data.get('expires_at','not reported'))
        print('limit_remaining_usd:',data.get('limit_remaining','not reported'))
except HTTPError as exc:
    print('authentication: HTTP',exc.code)
except URLError as exc:
    print('network_error:',type(exc.reason).__name__)
