# 생성: 2026-10-23 11:20 (KST)
"""DB 주소 다듬기. 표준 라이브러리만 씀(GitHub Actions의 db_ping에서도 씀)."""
from urllib.parse import quote, unquote


def normalize_db_url(url: str) -> str:
    """비밀번호에 @ : / # 같은 글자가 있어도 연결되도록 비밀번호 부분만 URL 인코딩한다.
    마지막 @ 뒤를 호스트로 본다. 이미 %40처럼 바꿔 둔 비밀번호는 그대로 둔다."""
    url = url.strip()
    scheme, sep, rest = url.partition("://")
    if not sep or "@" not in rest:
        return url
    userinfo, host = rest.rsplit("@", 1)
    user, colon, password = userinfo.partition(":")
    if not colon:
        return url
    return f"{scheme}://{user}:{quote(unquote(password), safe='')}@{host}"
