"""P2 품질 게이트 — 정밀평가의 절차 이행을 기계적으로 점검하는지 검증."""
from greenwashing.verification import _evaluation_quality_warnings


def _claim(cid, *, risk=None, verdict=None, precedents=None, verification=True):
    ev = {"risk_final": risk, "precedents": precedents if precedents is not None else [{"cite": "공정위 2024구사0058"}]}
    if verification:
        ev["verification"] = {"verdict": verdict} if verdict else {"verdict": "미확인"}
    return {"claim_id": cid, "evaluation": ev}


def test_high_risk_without_web_verification_warns():
    w = _evaluation_quality_warnings([_claim("C1", risk="높음", verification=False)])
    assert any("실증·검증" in x and "C1" in x for x in w)


def test_missing_precedent_warns():
    w = _evaluation_quality_warnings([_claim("C2", risk="중간", precedents=[])])
    assert any("심결례 없음" in x and "C2" in x for x in w)


def test_verdict_risk_mismatch_warns():
    # '반증'인데 위험 '중간' — 근거 없이 낮춘 경우(영풍 1차의 3-10 사례)
    w = _evaluation_quality_warnings([_claim("C3", risk="중간", verdict="반증")])
    assert any("판정 '반증'" in x and "C3" in x for x in w)


def test_verdict_risk_consistent_is_quiet():
    w = _evaluation_quality_warnings([_claim("C4", risk="높음", verdict="반증")])
    assert not any("판정" in x for x in w)


def test_precedent_overreuse_warns():
    # 같은 심결례를 4건에 복붙 → 템플릿 반죽 경고(기준 3건 초과)
    claims = [_claim(f"C{i}", risk="중간", verdict="과장") for i in range(4)]
    w = _evaluation_quality_warnings(claims)
    assert any("반복 인용" in x for x in w)


def test_precedent_within_limit_is_quiet():
    claims = [_claim(f"C{i}", risk="중간", verdict="과장") for i in range(3)]
    assert not any("반복 인용" in x for x in _evaluation_quality_warnings(claims))


def test_unevaluated_claims_produce_no_quality_noise():
    assert _evaluation_quality_warnings([{"claim_id": "C9"}]) == []
