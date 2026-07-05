---
name: greenwashing-review
description: >
  한국법 중심 그린워싱 평가·고발 파이프라인. 지속가능경영보고서·광고·홍보자료의 환경 주장을
  추출·트리아지(CLI)하고, korean-law MCP로 표시광고법·환경법 조문에 포섭한 정밀 법적 평가를 수행해
  법률검토보고서와 공정위 신고서·환경부 조사요청서·수사기관 고발장 초안을 만든다.
  "그린워싱 검토", "지속가능보고서 평가", "환경 표시·광고 검토", "그린클레임 평가",
  "이 보고서 그린워싱 봐줘", 환경성 주장 고발장 요청 시 사용.
argument-hint: "[사건 폴더 경로 — 예: matters/example-fy2025]"
---

# /greenwashing-review

프로젝트 루트: 이 저장소를 클론·설치한 경로. 상세 절차는 프로젝트 루트 안의
`EVALUATION-SOP.md`, 구조는 `README.md`. 법률 정확성·할루시네이션 금지 원칙이 최우선.

**설계 원칙: 법적 판단은 정규식이 하지 않는다. 판단은 이 세션의 Claude가 korean-law MCP로 한다.**

```
① 추출·트리아지 (CLI)     → 1-shortlist.json + 기계 1차분류(참고, 법적 판단 아님)
② 정밀 법적 평가 (이 스킬) → korean-law MCP로 조·항·호 포섭·심결례·오인가능성 → 2-evaluation.json
③ 문서 생성·게이트 (CLI)  → 2-evaluation.json 병합 → 보고서 → 승인 → 고발장
```

## 실행 절차

전제: 프로젝트 루트로 이동(`cd <repo-경로>`). 사건 폴더에 `context.yaml`과 `input/`(검토대상),
있으면 `evidence/`(기업 실증자료)가 있어야 한다. 없으면 사용자에게 요청한다.

### ① 추출·트리아지
```bash
python3 -m greenwashing assess <matter> --mode public --with-public-check
```
`--mode confidential`이면 외부 통신을 하지 않는다(기밀 사건). 실행 후 `<matter>/output/1-shortlist.json`과
`1-worklist.md`를 읽는다. corpus DB 오류가 나면 먼저 `python3 -m greenwashing corpus sync --jurisdiction KR`.

### ② 정밀 법적 평가 — 이 스킬의 핵심
`1-shortlist.json`의 각 주장에 대해 korean-law MCP로 근거를 확인하고 포섭한다.

- 법령 원문·현행성: `mcp__korean-law__search_law` → `mcp__korean-law__get_law_text`
  - 표시광고법(mst 확인) 제3조(부당 표시광고 금지), 제5조(실증책임)
  - 제품 환경성이면 「환경기술 및 환경산업 지원법」 환경성 표시·광고 조문 + 로컬 corpus의
    「환경성 표시·광고 관리제도에 관한 고시」
- 심결례·판례: `mcp__korean-law__search_decisions` (domain `ftc`=공정위, `precedent`=판례).
  검색어는 **공백 AND**이므로 단일어부터 넓게(`친환경`→`친환경 표시`). 결과가 나오면
  `get_decision_text`로 확정 여부 확인. **없으면 지어내지 말 것** — 국내 그린워싱 심결례는
  법제처 API로 거의 안 잡힌다. `precedents: []`로 두고 `confirm_needed`에 "공정위 사건검색(ftc.go.kr)·
  사내 판례·심결례 DB로 심결례 보강 필요"를 남긴다.

각 주장을 다음으로 포섭한다:
- 표시광고법 제3조 제1항 **어느 호**인지 특정: 1호 거짓·과장 / 2호 기만 / 3호 부당비교 / 4호 비방
- **오인가능성**: 보통주의력 일반 소비자가 받는 전체적·궁극적 인상 기준(대법원 표시광고 판단기준)
- 확인 안 된 사실(게시주체·기간·고의·실증 존부)은 지어내지 말고 `confirm_needed`에
- 광고 해당성이 불명확하면 `applicability_final: "불확실"`, 광고가 아니면(정책 나열·목차 등) `"없음"`

**실증·검증(웹 리서치) — 위험 확정 전 필수.** 회사가 주장하는 환경성과·지표의 실재·범위·반증을
WebSearch/WebFetch(필요 시 `agent-reach` 스킬)로 확인한다. EVALUATION-SOP.md §1.5 참조.
- 인증·라벨은 실재·대상·범위·유효기간 확인. 실재하면 '허위'로 몰지 말고 프레이밍 과장으로 좁힌다.
- 대외 환경이미지와 상충하는 사실(오염 배출·행정처분·소송·NGO 비판)을 찾는다.
- 출처 신뢰도 구분(관보·환경부·법원·주요언론=신뢰 / 위키·블로그·의견기사=저신뢰 단서). 확인 안 되면 단정 금지.
- **동명·유사기업 혼동 주의**(예: 동일·유사 상호의 다른 기업). `verdict`: 부합/과장/불일치/반증/미확인.

결과를 `<matter>/output/2-evaluation.json`으로 저장한다. 스키마(EVALUATION-SOP.md §2):
```json
{"matter_id":"...","evaluated_by":"...","evaluated_at":"YYYY-MM-DD","claims":{
  "CLM-xxxx":{"applicability_final":"있음","risk_final":"높음",
    "provisions":[{"authority_id":"KR-FAIR-LABELING-ACT","cite":"제3조 제1항 제2호","label":"기만"}],
    "precedents":[{"cite":"...","status":"확정","holding":"...","url":"..."}],
    "assessment":"포섭·판단","misleading":"오인가능성",
    "verification":{"verdict":"부합/과장/불일치/반증/미확인","summary":"...",
      "sources":[{"title":"...","publisher":"...","url":"...","finding":"...","stance":"확인/반증/중립"}]},
    "confirm_needed":["..."]}}}
```
`risk_final`은 웹 검증 결과를 반영해 확정한다. `claim_id`는 shortlist와 일치해야 병합된다.
`evaluated_by`는 세션 초안임을 명시하고 최종 확정은 변호사.

산출물은 모두 `.md`(보고서·고발장·요약표) + `.xlsx`(117행 검토표·증거목록 작업본)로 생성된다.

### ③ 병합·문서·게이트
```bash
python3 -m greenwashing assess <matter> --mode public   # 2-evaluation.json 자동 병합
python3 -m greenwashing verify <matter_id>
# 변호사 승인 후에만:
python3 -m greenwashing approve <matter_id> --reviewer "홍길동" --scope all
python3 -m greenwashing draft   <matter_id> --route all
```
보고서에 `법적 평가(변호사·korean-law MCP)` 블록이 붙고, 미평가 주장은 `[미평가]`로 남는다.

## 안전 경계

- `draft`(고발장·신고서)는 변호사 승인(`approve`) 없이 실행하지 않는다.
- 제출·발송 기능 없음. 위험점수는 우선순위 도구이지 위법성 결론이 아니다.
- 기밀 사건은 `--mode confidential`, ②에서 사건 내부 문구를 MCP에 넣지 말고 주장 유형·법령만 질의.
- 인용 법령·판례는 제출 전 현행 시행·확정 여부를 세션에서 korean-law MCP로 재검증(`pre_filing`).
- 존재하지 않는 조문·사건번호·심결례를 생성하지 않는다. 불확실은 `[확인 필요]`.
