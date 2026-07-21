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

**설계 원칙: 추출도 판단도 정규식이 하지 않는다. 둘 다 이 세션의 Claude가 한다.**
정규식은 어휘 없는 위험 문장("1~2급수 수질 유지")을 놓치고 목차·거버넌스 잡음을 올린다(영풍 실측).
CLI의 역할은 결정론적 검증(원문 앵커·해시·병합·문서생성)뿐이다.

```
① 통독 추출 (이 스킬)      → 세션이 보고서 전문을 읽고 주장 추출 → 1-claims.json
   + 앵커 검증 (CLI)       → assess가 인용문 실재를 PDF 대조(할루시네이션 게이트) → 1-worklist.md
② 정밀 법적 평가 (이 스킬) → 관문 쟁점·사건 서사 + 주장별 포섭·심결례·웹검증 → 2-evaluation.json
③ 문서 생성·게이트 (CLI)  → 병합 → 보고서(서사→관문→주장별) → 승인 → 고발장
```

## 실행 절차

전제: 프로젝트 루트로 이동(`cd <repo-경로>`). 사건 폴더에 `context.yaml`과 `input/`(검토대상),
있으면 `evidence/`(기업 실증자료)가 있어야 한다. 없으면 사용자에게 요청한다.

### ① 통독 추출 — 세션이 직접 한다
1. `input/`의 검토 대상(PDF)을 **전문 통독**한다(Read 도구, 분할 읽기). 표·이미지 캡션도 본다.
2. 환경 주장을 추출한다. **어휘가 아니라 실질**로 본다 — 다음을 반드시 포함:
   - 명시적 환경 표현(친환경·탄소중립·재활용 등)뿐 아니라 **환경성과를 함의하는 사실 주장**
     (수질 등급, 배출량 수치, "무방류", "검출한계 미만", 인증·수상, 생태계 서술)
   - CEO 메시지·하이라이트 페이지의 서사적 주장(가장 위험한 것이 여기 있는 경우가 많다)
   - 회사의 알려진 환경 이력(행정처분·소송·언론)과 **상충할 가능성**이 있는 모든 진술
3. `output/1-claims.json`으로 저장한다:
```json
{"matter_id":"...","extracted_by":"Claude 세션(통독 추출)","extracted_at":"YYYY-MM-DD",
 "claims":[{"claim_id":"<회사약칭>-p05-water","page":5,"quote":"…원문 그대로(중략은 …)…",
   "subject_scope":"사업장 환경성과","claim_types":["포괄적 환경편익 주장"],
   "why_flagged":"사법확정 오염 이력과 상충 가능","narrative_axis":"수질 서사"}]}
```
   `quote`는 **원문 그대로**(요약 금지) — CLI가 PDF와 문자 대조한다. 지어낸 인용은 앵커에서 걸린다.
4. 앵커 검증·워크시트 생성:
```bash
python3 -m greenwashing assess <matter> --mode public --with-public-check
```
`--mode confidential`이면 외부 통신을 하지 않는다(기밀 사건). 실행 후 `1-worklist.md`에서
**앵커 ⚠️미확인 주장을 반드시 해소**(인용 수정 후 재실행)한다. corpus DB 오류가 나면 먼저
`python3 -m greenwashing corpus sync --jurisdiction KR`.
(1-claims.json이 없으면 CLI는 정규식 폴백으로 동작하나, 이 스킬에서는 항상 통독 추출을 한다.)

### ② 정밀 법적 평가 — 이 스킬의 핵심

**②-0. 관문 쟁점(gateway) — 주장별 반복 금지, 한 번 깊게.**
이 사건 전체의 선결문제인 **광고 해당성**(지속가능경영보고서·홈페이지가 표시광고법상 '광고'인가)을
korean-law MCP(판례·심결례)로 정면 검토해 `gateway.ad_applicability`에 쓴다(매체별 결론 포함).
광고성이 부정될 경우의 **대안 경로**(환경기술산업법 직접 적용·자본시장법 공시규제 등)를
요건·제재·실익으로 비교해 `gateway.alternative_routes`에 쓴다. 주장별 평가에서는 이 결론을 참조만 한다.

**②-1. 사건 서사(narratives) — 보고서의 뼈대.**
개별 주장을 잇는 **구조적 괴리 축 1~3개**를 세운다: 회사의 대외 서사 vs 웹검증으로 확인된 사실
(행정처분·판결·측정치). 각 축에 `claim_ids`를 매핑한다. 이것이 결론 요약과 고발장 '대상 행위'가 된다.

**②-2. 주장별 포섭** — `1-shortlist.json`의 각 주장에 대해 korean-law MCP로 근거를 확인하고 포섭한다.

- 법령 원문·현행성: `mcp__korean-law__search_law` → `mcp__korean-law__get_law_text`
  - 표시광고법(mst 확인) 제3조(부당 표시광고 금지), 제5조(실증책임)
  - 제품 환경성이면 「환경기술 및 환경산업 지원법」 환경성 표시·광고 조문 + 로컬 corpus의
    「환경성 표시·광고 관리제도에 관한 고시」
- 심결례·판례: **주장별로 로컬 의결서 아카이브를 시맨틱 검색**한다(300+ 통독 금지) —
  `python3 -m greenwashing corpus search-decisions "<주장 문구>" -k 5 [--action 고발]`.
  상위 3~5건의 PDF(`pdf` 경로)만 열어 실제 관련성을 확인한다. 보조로 `mcp__korean-law__search_decisions`
  (domain `ftc`·`precedent`)도 시도. **없거나 탄젠트면 지어내지 말 것** — 시맨틱 상위여도 사실 관련
  없으면 버린다. 관련 의결서를 찾으면 `precedents`에 사건번호·조치·의결일을 채우고, 없으면 `precedents: []`.
  최종 인용 전 변호사가 의결서 원문·확정 여부를 확인한다(자동 편입 금지).
  (사전 준비: `corpus fetch-decisions` → `corpus index-decisions`로 아카이브·인덱스 구축, LM Studio 임베딩 필요)

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
{"matter_id":"...","evaluated_by":"...","evaluated_at":"YYYY-MM-DD",
 "gateway":{"ad_applicability":{"analysis":"...","media":[{"medium":"...","conclusion":"...","reason":"..."}],
    "precedents":[{"cite":"...","status":"...","holding":"..."}],"conclusion":"..."},
  "alternative_routes":[{"route":"...","requirements":"...","sanctions":"...","pros_cons":"..."}]},
 "narratives":[{"axis":"...","company_story":"...","confirmed_reality":"...","gap":"...",
    "legal_significance":"...","claim_ids":["..."]}],
 "claims":{
  "CLM-xxxx":{"applicability_final":"있음","risk_final":"높음",
    "provisions":[{"authority_id":"KR-FAIR-LABELING-ACT","cite":"제3조 제1항 제2호","label":"기만"}],
    "precedents":[{"cite":"...","status":"확정","holding":"...","url":"..."}],
    "assessment":"포섭·판단","misleading":"오인가능성",
    "verification":{"verdict":"부합/과장/불일치/반증/미확인","summary":"...",
      "sources":[{"title":"...","publisher":"...","url":"...","finding":"...","stance":"확인/반증/중립"}]},
    "confirm_needed":["..."]}}}
```
`risk_final`은 웹 검증 결과를 반영해 확정한다. `claim_id`는 1-claims.json과 일치해야 병합된다
(불일치는 assess가 경고). 주장별 `assessment`에서 관문 쟁점·공통 법리를 반복하지 말고 **그 주장 고유의
쟁점만** 쓴다. 같은 심결례를 3건 이상 주장에 복붙 인용하지 않는다 — 주장별로 `corpus search-decisions`를
실호출해 차별화된 후보를 찾고, 없으면 비워 둔다. `evaluated_by`는 세션 초안임을 명시, 최종 확정은 변호사.

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
