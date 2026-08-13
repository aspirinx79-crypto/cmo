"""캡처 여러 장을 한 번의 호출로 판독한다.

애드로그와 오픈업이 같은 일을 한다 — 장수·용량을 재고, 파일을 그림으로
바꾸고, 한 번에 보내고, 받은 글자를 파서에 넘긴다. 다른 건 프롬프트와
파서뿐이다. 두 벌로 두면 한쪽 상한만 고치고 잊는 날이 온다.

**한 번의 호출로 보낸다.** 오픈업은 성별 비율과 연령대가 다른 장에 걸쳐
있고, 애드로그는 조회수와 순위가 다른 화면에 있다. 같이 봐야 앞뒤가 맞는다.
"""
from collections.abc import Callable

from .read_doc import MAX_BYTES, MODEL, TOO_BIG, ask_model, render_pages

MAX_CAPTURES = 6

TOO_MANY = f"캡처는 {MAX_CAPTURES}장까지 넣을 수 있습니다."
NO_FILE = "파일을 한 개 이상 넣으십시오."


def read_many(files: list[tuple[bytes, str]], prompt: str,
              parse: Callable[[str], dict], api_key: str,
              model: str = MODEL) -> dict:
    """`[(바이트, 파일명)]` 을 판독해 dict 를 낸다. 아무것도 저장하지 않는다.

    용량은 **합계로** 본다. 한 장씩은 작아도 여섯 장을 더하면 넘는다.
    """
    if not files:
        raise ValueError(NO_FILE)
    if len(files) > MAX_CAPTURES:
        raise ValueError(TOO_MANY)
    if sum(len(data) for data, _ in files) > MAX_BYTES:
        raise ValueError(TOO_BIG)

    images = []
    for data, filename in files:
        images.extend(render_pages(data, filename))

    return parse(ask_model(images, prompt, api_key, model))
