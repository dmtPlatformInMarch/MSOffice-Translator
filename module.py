import re

def only_allowed_chars(text):
    # 허용 문자: 숫자, _, -, *, %, 공백
    pattern = r'^[0-9_\-\*\% ]+$'
    return bool(re.match(pattern, text))