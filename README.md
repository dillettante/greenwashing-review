# Greenwashing Counsel

> **이 문서 하나로 전체를 이해하고, 수정·보완·개선의 기준점으로 삼는다.**
> 기준일 2026-07-05
> 관련: [PLAN.md](PLAN.md)(로드맵) · [EVALUATION-SOP.md](EVALUATION-SOP.md)(② 절차) · [MAINTENANCE.md](MAINTENANCE.md)(최신화) · [INSTALL.md](INSTALL.md)(오프라인·zip 배포)

지속가능경영보고서·광고·홍보자료를 입력하면 환경 주장을 추출·평가하고, **변호사 승인 하에** 공정위 신고서·환경부 조사요청서·수사기관 고발장 **초안**을 만드는 로컬 도구다. 한국법(표시광고법·환경기술산업법)만 직접 판단근거로 쓰고, 미국·EU·영국은 비교법적 보강으로 분리한다.

**핵심 철학 — 법적 판단은 정규식이 하지 않는다.** 정규식(Python CLI)은 기계적 잡일(추출·트리아지·문서생성)만 하고, 실제 법적 판단(조문 포섭·오인가능성·심결례·웹 검증)은 **Claude 세션이 korean-law MCP와 웹 리서치로** 수행한다. 이 분리가 전체 설계의 뼈대다.

---

## 1. 3계층 플로우

```
┌─ ① 추출·트리아지 (CLI, 정규식) ────────────────────────────────┐
│  PDF/DOCX/PPTX/HTML/이미지 → 텍스트·해시·페이지                    │
│  환경 주장 추출 → 8요소·100점 기계 위험점수 → shortlist(최대 20건)  │
│  산출: 1-shortlist.json, 1-worklist.md, 1-assessment.json          │
└──────────────────────────────┬─────────────────────────────────┘
                               │  (기계 트리아지는 법적 판단이 아님)
┌─ ② 정밀 법적 평가 (Claude 세션 + korean-law MCP + 웹) ──────────┐
│  shortlist 각 주장에 대해:                                        │
│   · 표시광고법 제3조 제1항 몇 호 / 환경기술산업법 제16조의10 포섭    │
│   · 공정위 심결례·판례 확인(없으면 지어내지 않음)                    │
│   · 오인가능성(대법원 전체적 인상 기준) 서술                        │
│   · ★웹 검증: 회사 주장 지표·인증의 실재·범위·반증 확인(위험 확정 전) │
│  산출: 2-evaluation.json  ← ①과 ③을 잇는 유일한 접점               │
└──────────────────────────────┬─────────────────────────────────┘
                               │
┌─ ③ 문서 생성·게이트 (CLI) ─────────────────────────────────────┐
│  2-evaluation.json 병합 → 3-legal-review-report.md + 3-*.xlsx/.md  │
│  변호사 승인(approve) → 4-filing-*-draft.md → verify(무결성)        │
└─────────────────────────────────────────────────────────────────┘
```

**①③은 무인 CLI, ②만 세션 작업이다.** ②는 `/greenwashing-review` 스킬 또는 [EVALUATION-SOP.md](EVALUATION-SOP.md) 절차로 수행한다. `2-evaluation.json`이 없으면 보고서는 `[미평가]`로 정직하게 표시한다(숨기지 않음).

```bash
python3 -m greenwashing assess matters/<사건> --mode public --with-public-check   # ①
#   → (세션) 1-shortlist.json을 korean-law MCP·웹으로 평가 → output/2-evaluation.json  # ②
python3 -m greenwashing assess matters/<사건> --mode public                       # ③ 병합
python3 -m greenwashing verify   <matter_id>
python3 -m greenwashing approve  <matter_id> --reviewer "홍길동" --scope all        # 변호사 승인
python3 -m greenwashing draft    <matter_id> --route all                           # 고발장 초안
```

---

## 2. 설치

Python 3.11+ 와 `python-docx`, `openpyxl`, `pypdf`, `python-pptx`(모두 `pyproject.toml`에 명시). Node·Codex 의존성은 없다.

```bash
pip install python-docx openpyxl pypdf python-pptx   # 또는: pip install -e .
python3 -m greenwashing corpus sync --jurisdiction KR       # 국내 법령 DB 최초 구축(네트워크)
python3 -m greenwashing assess examples/sample-matter --mode public   # 가상 예제로 동작 확인
```

`examples/sample-matter/`는 실제 기업과 무관한 가상 자료다. korean-law MCP는 이 repo에 포함되지 않으므로,
② 정밀평가를 쓰려면 각자 Claude Code에 korean-law MCP를 별도로 연결한다([INSTALL.md](INSTALL.md)).

제3자(다른 변호사·팀)에게 배포하는 방법은 [INSTALL.md](INSTALL.md) 참조.

---

## 3. 사건 폴더

```text
matters/<사건>/
  context.yaml           사건 메타
  input/                 검토대상(지속가능보고서·광고·홍보자료)
  evidence/              기업 실증자료·공개 반증자료(선택)
  public-evidence/       홈페이지·언론 스냅숏(--with-public-check가 생성)
  output/                산출물(단계 번호 프리픽스, §4)
```

`context.yaml`(1단계 key/value):
```yaml
matter_id: example-fy2025
company: 예시 주식회사
product: 동·은 제품 등
published_date: 2025-06-01
medium: 지속가능경영보고서
audience: 투자자·거래처·일반
complainant: 홍길동
respondent_details: "[확인 필요] 주소·대표자"
company_homepage: https://www.example.com/
public_urls: []
```

---

## 4. 산출물 — 단계 번호로 최종본과 전단계 구분

파일명 프리픽스가 파이프라인 단계를 나타낸다. Finder에서 정렬하면 진행 순서대로 보인다.

| 프리픽스 | 의미 | 파일 |
|---|---|---|
| `1-` | **전단계**(기계 트리아지) | `1-assessment.json`, `1-shortlist.json`, `1-worklist.md`, `1-corroboration.md/.json` |
| `2-` | **정밀평가**(세션 작성) | `2-evaluation.json` |
| `3-` | **★ 최종 결과물** | `3-legal-review-report.md`(메인 보고서), `3-claims-review.xlsx`(117행 작업본)/`.md`(요약), `3-evidence-list.xlsx`/`.md` |
| `4-` | **★★ 제출문서**(승인 후) | `4-filing-kftc-draft.md`, `4-filing-environment-draft.md`, `4-filing-criminal-draft.md` |
| `9-` | 검증 로그 | `9-verification-log.md/.json` |
| (없음) | 제어·메타 | `attorney-approval.json`, `test-summary.md` |

- **`3-`이 붙으면 최종 심사 산출물, `4-`는 승인 후 제출문서.** `1-`·`2-`는 그 전단계다.
- 서술형은 `.md`(후속 가공), 117행 검토표는 `.xlsx`(정렬·색상 작업본)를 원칙으로 한다.
- 보고서 내부 텍스트는 한국어(house style), 파일명만 영문·번호.

---

## 5. 핵심 접점 — `2-evaluation.json`

①과 ③을 잇는 유일한 인터페이스. 세션(②)이 이 파일을 만들면 `assess` 재실행 시 `cli._attach_evaluation`이 주장별로 병합해 보고서·고발장에 렌더한다. 스키마(상세 [EVALUATION-SOP.md](EVALUATION-SOP.md) §2):

```json
{ "matter_id": "...", "evaluated_by": "...(세션 초안 명시)", "evaluated_at": "YYYY-MM-DD",
  "claims": { "CLM-xxxx": {
    "applicability_final": "있음|불확실|없음",
    "risk_final": "매우 높음|높음|중간|낮음",
    "provisions": [{"authority_id":"KR-FAIR-LABELING-ACT","cite":"제3조 제1항 제2호","label":"기만"}],
    "precedents": [{"cite":"...","status":"확정","holding":"...","url":"..."}],
    "assessment": "포섭·판단",  "misleading": "오인가능성",
    "verification": {"verdict":"부합/과장/불일치/반증/미확인","summary":"...",
      "sources":[{"title":"...","publisher":"...","url":"...","finding":"...","stance":"확인/반증/중립"}]},
    "confirm_needed": ["..."]
  } } }
```

`claim_id`는 `1-shortlist.json`과 일치해야 병합된다. 필드는 모두 선택적(채운 것만 렌더). **`risk_final`은 웹 검증 결과를 반영해 확정한다.**

---

## 6. 명령어 레퍼런스

```
corpus sync --jurisdiction KR      국내 공식 원문 수집·조문 DB 갱신(네트워크)
corpus audit [--stale-days N]      coverage·효력·최신성·무결성 감사(공백 시 exit 2)
corpus import-json <path>          사람이 검증한 규범·심결례·판례 편입
corpus monitor --cadence X         weekly/monthly/pre_filing 변경 감시
corpus candidates [--status S]     판례·처분 검증 대기열 조회
corpus candidate-review <id> ...   후보 상태 기록
corpus fetch-decisions [--keyword 본문어] [--title 사건명어] [--violation-type 0609*] [--since YYYY-MM-DD]
                                   공정위 의결서 자동 수집(case.ftc.go.kr, 토큰 불요·증분). 인자 없으면 그린워싱 기본세트
                                   (부당한 표시광고 위반 0609* + 본문 환경·탄소·그린 등). raw·index는 corpus/raw/KR/cases/(gitignore)
assess <matter> --mode public|confidential [--with-public-check]   ①추출·③병합
corroborate <matter>               홈페이지·언론 교차확인
approve <matter_id> --reviewer ... --scope all|kftc|environment|criminal
draft   <matter_id> --route all|kftc|environment|criminal          승인 후 초안
verify  <matter_id>                무결성 검증(exit 2 = 검토 필요)
```

`assess`는 네트워크를 쓰지 않고 로컬 DB만 조회한다(단 `--with-public-check`는 공개자료 수집). `corpus sync`만 공식 원문을 내려받는다. `corpus audit` exit 2는 오류가 아니라 조사 공백을 알리는 품질 게이트다.

---

## 7. 법령 DB (corpus)

- **단일 원본은 국가법령정보센터 공식 원문.** `corpus sync`가 원문을 조문 단위로 파싱하고 시행일·원문/본문/조문 SHA-256과 함께 저장한다.
- 규범 6개 · 조문 240개: 표시광고법·시행령, 환경기술산업법·시행령, 「환경성 표시·광고 관리제도에 관한 고시」, 「환경 관련 표시·광고에 관한 심사지침」.
- `.gw/state.sqlite3` = 런타임 조회 DB, `corpus/verified` = 검증 원본, `corpus/raw` = 증거 스냅숏.
- **assess는 필수 조문 DB가 없으면 중단**한다(법률근거 게이트).
- **심결례·판례 DB는 아직 비어 있다.** 법제처 API가 그린워싱 사례를 거의 반환하지 않으므로 공정위 사건검색(case.ftc.go.kr)·사내 판례·심결례 DB에서 사람이 수집해 `import-json`으로 편입한다(후속 과제, [MAINTENANCE.md](MAINTENANCE.md)).

---

## 8. 스킬 — `/greenwashing-review`

**배포용 스킬 파일은 단 하나: `skills/greenwashing-review/SKILL.md`.**

- 설치: `~/.claude/skills/greenwashing-review` → 이 repo의 `skills/greenwashing-review`를 가리키는 **심링크**.
  - `ln -s "$(pwd)/skills/greenwashing-review" ~/.claude/skills/greenwashing-review`
- 스킬은 자체 완결이 아니라 프로젝트에 의존한다: (a) Python CLI(`python3 -m greenwashing`), (b) 절차 문서 [EVALUATION-SOP.md](EVALUATION-SOP.md). SKILL.md는 ②단계(포섭·심결례·웹검증)를 어떻게 수행하는지 규정한다.
- 트리거: "그린워싱 검토", "지속가능보고서 평가", "환경 표시·광고 검토", 환경성 주장 고발장 요청 등.

---

## 9. 유지보수 ([MAINTENANCE.md](MAINTENANCE.md))

매주(원문 해시 비교·판례 검색) · 매월(공정위·환경부·법령센터 검색결과 비교) · 제출 전(`pre_filing` 재검증) · 분기(coverage·외국법). 판례·처분은 자동 편입 금지 — 사람 확인 후 `import-json`. `scripts/run_maintenance.sh`·`ops/*.plist` 참고.

---

## 10. 안전 경계

- `draft`(고발장·신고서)는 변호사 승인(`approve`) 없이 실행 불가. 승인 후 `1-assessment.json`이 바뀌면 재승인 필요.
- **제출·발송 기능 없음.** 위험점수는 우선순위 도구일 뿐 위법성·고의·형사책임의 결론이 아니다.
- `confidential` 모드는 외부 통신 안 함. ②에서 사건 내부 문구를 MCP·웹에 넣지 않는다(주장 유형·법령만 질의).
- 존재하지 않는 조문·사건번호·심결례를 생성하지 않는다. 불확실은 `[확인 필요]`. 동명·유사기업 혼동 주의(동일·유사 상호의 다른 기업).
- 인용 법령·판례의 현행 시행·확정 여부는 제출 전 변호사가 재확인한다.

---

## 11. 파일 트리 · 모듈 맵

```
Greenwashing/
├─ README.md              ← 이 문서(단일 기준점)
├─ PLAN.md                로드맵·진행상황·완료기준
├─ EVALUATION-SOP.md      ② 정밀평가 절차·2-evaluation.json 스키마
├─ MAINTENANCE.md         DB 최신화 주기·심결례 후속과제
├─ INSTALL.md             제3자 배포·설치
├─ pyproject.toml         의존성
├─ greenwashing/          ── Python 패키지(~2,800 LOC) ──
│  ├─ cli.py              (427) 명령 파서·오케스트레이션·evaluation 병합·shortlist 출력
│  ├─ analysis.py         (343) ①핵심: 주장 추출·패턴분류·8요소 점수·shortlist 선별
│  ├─ markdown_docs.py    (283) ③보고서·요약표·고발장 .md 생성(웹검증 블록 렌더)
│  ├─ corroboration.py    (269) 공개자료(홈페이지·언론) 교차확인
│  ├─ database.py         (267) SQLite: 규범·조문·버전·해시·사건
│  ├─ korean_corpus.py    (228) 국가법령정보센터 원문 수집·조문 파싱
│  ├─ maintenance.py      (221) 주간/월간/제출전 변경 감시·판례 후보 큐
│  ├─ workbooks.py        (191) ③검토표·증거목록 .xlsx(openpyxl)
│  ├─ extractors.py       (139) PDF/DOCX/PPTX/HTML/이미지 OCR 추출
│  ├─ verification.py     (118) 산출물·인용·승인 무결성(verify)
│  ├─ models.py           (103) 데이터클래스
│  ├─ context.py          (64)  context.yaml 파서
│  ├─ approval.py         (41)  변호사 승인 해시 게이트
│  └─ data/               규범 출처 목록(kr_official_sources.json 등)
├─ corpus/{raw,verified}/ 법령 원문 스냅숏·파싱 JSON
├─ .gw/state.sqlite3      런타임 DB
├─ matters/<사건>/        사건 작업공간
├─ skills/greenwashing-review/SKILL.md   배포용 스킬
├─ scripts/ · ops/        유지보수 스크립트·launchd
└─ tests/                 회귀 테스트(11건)
```

---

## 12. 개선할 때 어디를 건드리나 (기준점)

| 바꾸고 싶은 것 | 손댈 곳 |
|---|---|
| 주장 추출·패턴·기계 점수 | `analysis.py` |
| shortlist 선별 기준 | `analysis.py:select_shortlist` |
| ② 평가 절차·웹검증·스키마 | `EVALUATION-SOP.md` + `skills/greenwashing-review/SKILL.md` |
| evaluation 병합·shortlist 출력 | `cli.py:_attach_evaluation`, `_write_shortlist` |
| 보고서·고발장 .md 서식 | `markdown_docs.py` |
| 검토표·증거목록 .xlsx 서식 | `workbooks.py` |
| 산출물 파일명·번호 규칙 | `cli.py`(assess/draft) + `verification.py`(REQUIRED·glob) + `workbooks.py` |
| 법령 수집·조문 파싱 | `korean_corpus.py`, `data/kr_official_sources.json` |
| 무결성 검증 규칙 | `verification.py` |
| 공개자료 교차확인 | `corroboration.py` |

---

## 13. 알려진 한계·후속 과제

1. **심결례·판례 DB 미구축** — case.ftc.go.kr DB화 또는 Open API 대기, 사내 판례·심결례 DB 활용. (최우선)
2. **추출 오탐** — 정책·목차 나열 blob, 수치표가 주장으로 잡힘(②에서 `없음` 필터로 걸러지나 ① 정확도 개선 여지).
3. **이미지·색상·인증마크** — OCR 문언까지만. 도안·색상 의미는 사람이 원본 확인.
4. **미국·EU·영국 DB** — 비교법 규범 원문·사례의 버전 DB 전환 미완.
5. **정답 세트 검증** — 실제 자료 3~5건으로 추출 재현율 95%·고위험 누락 0 측정 미완.

---

## 14. 검증

```bash
python3 -m unittest discover -s tests -v
```

---

## 15. 면책 (Disclaimer)

이 소프트웨어는 변호사의 그린워싱(환경 표시·광고) 검토를 **보조**하는 도구다. 산출물(위험점수·법률검토보고서·
신고서/고발장 초안 등)은 **법률자문이 아니며**, 기계적 산출물에 불과하다. 반드시 자격 있는 변호사의 검토·확정을
거쳐야 하고, 인용 법령·판례의 현행성·정확성은 제출 전 사람이 재확인해야 한다. 저작자는 이 도구의 사용 또는
산출물로 인한 어떠한 결과에 대해서도 보증·책임을 지지 않는다(아래 라이선스의 무보증·책임제한 조항 참조).

## 16. 라이선스

[Apache License 2.0](LICENSE) — Copyright 2026 dillettante. 자세한 조건은 `LICENSE`와 `NOTICE` 참조.
