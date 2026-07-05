# 정밀 법적 평가 절차 (step ②) — korean-law MCP

기준일: 2026-07-05

이 문서는 **기계 트리아지(step ①, CLI)** 와 **문서 생성(step ③, CLI)** 사이의
**법적 판단(step ②)** 을 어떻게 수행하는지 고정한다. 정규식은 법적 판단을 하지 않는다.
판단은 변호사 + Claude 세션이 korean-law MCP로 수행하고 그 결과를 `2-evaluation.json`에 남긴다.

## 0. 전제

- `python3 -m greenwashing assess <matter> --mode public` 를 먼저 실행해 `output/1-shortlist.json`,
  `output/1-worklist.md` 가 생성돼 있어야 한다.
- 정밀평가 대상은 shortlist(광고성·중대성 상위, 최대 20건)뿐이다. 전량이 아니다.
- `confidential` 사건은 외부 전송이 금지되나 korean-law MCP는 공식 법령 조회이므로
  사건 내부자료를 프롬프트에 넣지 않는 범위에서 사용한다(주장 문구·유형만 질의).

## 1. 세션 절차

Claude 세션(로컬 Claude Code CLI)에서 다음을 수행한다.

1. `output/1-shortlist.json` 을 읽는다.
2. 각 주장에 대해 korean-law MCP로 **직접 근거와 사례**를 확인한다.
   - 법령 원문: `search_law` → `get_law_text` (표시광고법 제3조, 환경기술산업법 제16조의10 등)
   - 공정위 심결례: `search_decisions(domain="ftc", query=…)`
   - 판례: `search_decisions(domain="precedent", query=…)` → `get_decision_text`
   - 해석례 필요 시: `search_decisions(domain="interpretation", …)`
   - 검색어는 **공백 AND**로 처리되므로 넓게 시작해 좁힌다(예: `환경` → `친환경 표시`).
     국내 그린워싱 판례는 얇으므로 공정위 심결례·심사지침을 우선한다.
3. 각 주장을 **포섭**한다. 표시광고법 제3조 제1항의 어느 호인지 특정한다.
   - 1호 거짓·과장 / 2호 기만 / 3호 부당 비교 / 4호 비방
   - 제품 환경성이면 환경기술 및 환경산업 지원법상 환경성 표시·광고 기준(제16조의10 등)·
     「환경성 표시·광고 관리제도에 관한 고시」를 병행 검토한다.
4. **오인가능성**을 전체적 인상 기준으로 서술한다(대법원 표시광고 판단기준: 보통주의력을 가진
   일반 소비자가 받는 전체적·궁극적 인상).
5. **실증·검증 (웹 리서치)** — 위험을 확정하기 전에 회사가 주장하는 환경성과·지표의 실재·범위·반증을
   웹으로 확인한다(WebSearch/WebFetch, 필요 시 `agent-reach` 스킬). 이것이 품질의 핵심이다.
   - 인증·라벨은 **실재·대상·범위·유효기간**을 확인한다(예: SGS 100% PIR — 인증이 실재하는지, '원료'
     인증인지 '제품 전과정' 인증인지). 실재하면 '허위'로 몰지 말고, 프레이밍 과장 여부로 좁힌다.
   - 지표(친환경 매출·탄소감축·재생에너지 비중)는 외부 확인·반증, 독립 검증 여부를 찾는다.
   - 회사의 대외 환경이미지와 **상충하는 사실**(오염 배출·행정처분·소송·NGO 비판)을 찾는다.
   - **출처 신뢰도**를 구분한다. 관보·환경부·법원·주요 언론=신뢰, 블로그·위키·의견기사=저신뢰(단서로만).
   - **확인 안 되면 단정하지 않는다.** 동명·유사 상호 기업 혼동에 주의.
   - 판정(`verdict`)을 부합/과장/불일치/반증/미확인 중 하나로 내고, 근거 `sources`를 남긴다.
6. 확인되지 않은 사실(게시주체·기간·고의·실증자료 존부 등)은 지어내지 않고 `confirm_needed`에 남긴다.
7. 판례·심결례 인용 시 **확정 여부**를 확인한다(항소·상고 결과). 확인 불가 시 `status: "확인 필요"`.
8. 결과를 `output/2-evaluation.json` 으로 저장한다(아래 스키마).

## 2. `2-evaluation.json` 스키마

CLI(`_attach_evaluation`)가 이 형식을 읽어 보고서·고발장에 병합한다.

```json
{
  "matter_id": "example-fy2025",
  "evaluated_by": "홍길동",
  "evaluated_at": "2026-07-05",
  "claims": {
    "CLM-xxxxxxxxxx": {
      "applicability_final": "있음",
      "risk_final": "높음",
      "provisions": [
        {"authority_id": "KR-FAIR-LABELING-ACT", "cite": "제3조 제1항 제1호", "label": "거짓·과장의 표시·광고"}
      ],
      "precedents": [
        {"cite": "공정위 의결 제2023-000호", "status": "확정", "holding": "...", "url": "https://..."}
      ],
      "assessment": "재활용 원료 사용이라는 부분 속성을 제품 전과정의 친환경으로 확대한 것으로, ...",
      "misleading": "일반 소비자는 '친환경 제품'을 전과정 환경우수성으로 인식할 수 있어 ...",
      "verification": {
        "verdict": "부합(인증 실재)이나 표현 과장 소지",
        "summary": "SGS 100% 재활용 원료 인증은 신뢰 보도로 실재 확인. 다만 '원료' 인증을 '친환경 100%'로 확대.",
        "sources": [
          {"title": "예시 기업 동 제품 친환경 100% 글로벌 인증", "publisher": "서울경제", "date": "2024",
           "url": "https://...", "finding": "인증 실재하나 '재활용 원료'를 '친환경'으로 확대 표현", "stance": "확인"}
        ]
      },
      "confirm_needed": ["SGS 인증 범위·유효기간", "친환경 매출 산정기준"]
    }
  }
}
```

필드는 모두 선택적이다. 채운 것만 보고서에 렌더된다. `claim_id`는 shortlist의 것과 일치해야 한다.
`verification.verdict`는 부합/과장/불일치/반증/미확인, `sources[].stance`는 확인/반증/중립.
`risk_final`은 웹 검증 결과를 반영해 확정한다(반증 발견 시 상향, 완전 실증 시 오인성 판단에 반영).

## 3. 병합

```bash
# 2-evaluation.json 저장 후 재실행하면 보고서·검토표·고발장에 정밀평가가 결합된다.
python3 -m greenwashing assess <matter> --mode public
```

보고서 상단에 정밀평가 결합 여부가 표시되고, 각 주장에 `법적 평가` 블록이 붙는다.
정밀평가가 없는 주장은 `[미평가]`로 표시되어 숨겨지지 않는다.

## 4. 제출 전 (step ③ 이후)

`draft` 로 고발장·신고서 초안을 만들기 전 `pre_filing` 재검증을 세션에서 수행한다.
korean-law MCP로 (a) 인용 법령의 현행 시행 여부, (b) 인용 판례·심결례의 확정·변경 여부,
(c) 사건 당시 시행법과 현행법의 차이를 재확인하고 결과를 `9-verification-log`에 반영한다.
