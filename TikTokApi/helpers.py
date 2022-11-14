import json
from urllib.parse import urlencode, parse_qsl, urlparse, parse_qs
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from base64 import b64encode, b64decode
from .exceptions import *

import re
import requests

XTTPARAMS_AES_PASSWORD_ENCRYPTION = 'webapp1.0+202106'

def extract_tag_contents(html):
    next_json = re.search(
        r"id=\"__NEXT_DATA__\"\s+type=\"application\/json\"\s*[^>]+>\s*(?P<next_data>[^<]+)",
        html,
    )
    if next_json:
        nonce_start = '<head nonce="'
        nonce_end = '">'
        nonce = html.split(nonce_start)[1].split(nonce_end)[0]
        j_raw = html.split(
            '<script id="__NEXT_DATA__" type="application/json" nonce="%s" crossorigin="anonymous">'
            % nonce
        )[1].split("</script>")[0]
        return j_raw
    else:
        sigi_json = re.search(
            r'>\s*window\[[\'"]SIGI_STATE[\'"]\]\s*=\s*(?P<sigi_state>{.+});', html
        )
        if sigi_json:
            return sigi_json.group(1)
        else:
            raise CaptchaException(0, None,
                "TikTok blocks this request displaying a Captcha \nTip: Consider using a proxy or a custom_verify_fp as method parameters"
            )


def extract_video_id_from_url(url, headers={}):
    url = requests.head(url=url, allow_redirects=True, headers=headers).url
    if "@" in url and "/video/" in url:
        return url.split("/video/")[1].split("?")[0]
    else:
        raise TypeError(
            "URL format not supported. Below is an example of a supported url.\n"
            "https://www.tiktok.com/@therock/video/6829267836783971589"
        )


def deep_get(dict, path):
    def _split_indexes(key):
        split_array_index = re.compile(r'[.\[\]]+')  # ['foo', '0']
        return filter(None, split_array_index.split(key))

    ends_with_index = re.compile(r'\[(.*?)\]$')  # foo[0]
    keylist = path.split('.')
    val = dict
    for key in keylist:
        try:
            if ends_with_index.search(key):
                for prop in _split_indexes(key):
                    if prop.isdigit():
                        val = val[int(prop)]
                    else:
                        val = val[prop]
            else:
                val = val[key]
        except (KeyError, IndexError, TypeError):
            return None

    return val


def parse_query(url):
    result = urlparse(url)
    query = result.query
    query_dict = parse_qs(query)
    query_dict = {k: v[0] for k, v in query_dict.items()}
    return query_dict


def process_browser_log_entry(entry):
    response = json.loads(entry['message'])['message']
    return response


def set_url(domain, _dict):
    path = urlencode(_dict)
    url = domain + '?%s' % path
    return url


def get_param_url(_dict):
    return urlencode(_dict)


def encrypt_tt_param_v1(text):
    password = XTTPARAMS_AES_PASSWORD_ENCRYPTION
    text = text + '&is_encryption=1'
    iv = password.encode()
    password = password.encode()
    msg = pad(text.encode(), AES.block_size)
    cipher = AES.new(password, AES.MODE_CBC, iv)
    cipher_text = cipher.encrypt(msg)
    out = b64encode(cipher_text).decode('utf-8')
    return out


def encrypt_tt_param_v2(r):
    s = urlencode(r, doseq=True, quote_via=lambda s, *_: s)
    key = XTTPARAMS_AES_PASSWORD_ENCRYPTION.encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, key)
    ct_bytes = cipher.encrypt(pad(s.encode("utf-8"), AES.block_size))
    return b64encode(ct_bytes).decode("utf-8")


def decrypt_tt_param_v2(s):
    key = XTTPARAMS_AES_PASSWORD_ENCRYPTION.encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, key)
    ct = b64decode(s)
    s = unpad(cipher.decrypt(ct), AES.block_size)
    return dict(parse_qsl(s.decode("utf-8"), keep_blank_values=True))
