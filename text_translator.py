import aiohttp
import requests

TRANSLATOR_URL = "https://model-nmt.aidmtlabs.com/api/texts/translation"


def translate(text, src, tgt):
    headers = {"Content-Type": "application/json"}
    data = {"text": text, "from_lang": src, "to_lang": tgt}

    try:
        session = requests.Session()
        response = session.post(
            TRANSLATOR_URL,
            headers=headers,
            json=data,
        )

        print(f"{response.text}")

        return response.json()['result']['result']
    except Exception as e:
        print(f"번역 요청에서 에러가 발생하였습니다 : {e}")
        return ""

# ======================== 구글번역
# import unicodedata
# import requests
# import re
# import html
#
# def remove_control_characters(s):
#     return "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
#
# async def translate(text, src, tgt) :
#     locale_dict = {"zh": "zh-CN", "zh-cn" : "zh-CN"}
#     tgt = tgt if locale_dict.get(tgt) is None else locale_dict.get(tgt)
#
#     session = requests.Session()
#     response = session.get(
#         "http://translate.google.com/m",
#         params={"tl": tgt, "sl": src, "q": text},
#         headers={
#             "User-Agent": "Mozilla/4.0 (compatible;MSIE 6.0;Windows NT 5.1;SV1;.NET CLR 1.1.4322;.NET CLR 2.0.50727;.NET CLR 3.0.04506.30)"  # noqa: E501
#         },
#     )
#
#     re_result = re.findall(r'(?s)class="(?:t0|result-container)">(.*?)<', response.text)
#     if response.status_code == 400:
#         result = "IRREPARABLE TRANSLATION ERROR"
#     else:
#         response.raise_for_status()
#
#         # 번역 에러나서 추가
#         try:
#             result = html.unescape(re_result[0])
#         except:
#             return "[google translator error]"
#     return remove_control_characters(result)
