# 유지보수 및 최신화 운영절차

기준일: 2026-07-05

## 1. 주기

| 주기 | 자동 작업 | 사람 검토 |
|---|---|---|
| 매주 토요일 08:30 | 국내 핵심 규범 원문 재수집·본문 해시 비교, 국가법령정보센터 판례 검색식 실행 | 변경 규범과 신규 판례 후보 확인 |
| 매월 1일 09:30 | 공정위·기후에너지환경부·국가법령정보센터 검색결과 링크 집합 비교 | 신규 처분·보도자료의 사건번호·처분내용·불복 여부 확인 |
| 사건 제출 24시간 전 | `pre_filing` 전체 감시와 corpus audit, 사건 verify | 세션에서 korean-law MCP로 (a)인용 법령 현행 시행 여부, (b)인용 심결례·판례 확정·변경 여부, (c)사건 당시 시행법과 현행법 차이를 재확인하고 9-verification-log에 반영 |
| 분기 첫 주 | coverage registry 및 검색식 검토 | 누락 기관·검색어·기간 보완, 외국법 proposal/시행 상태 확인 |

## 2. 실행 명령

```bash
python3 -m greenwashing corpus monitor --cadence weekly
python3 -m greenwashing corpus monitor --cadence monthly
python3 -m greenwashing corpus monitor --cadence pre_filing
python3 -m greenwashing corpus candidates --status pending_human_review
python3 -m greenwashing corpus candidate-review KR-PREC-000000 --status excluded --notes "환경주장과 무관"
python3 -m greenwashing corpus audit --stale-days 7
```

결과는 `corpus/updates/`에 JSON과 Markdown으로 저장된다. 판례 원문 후보는 `corpus/research-queue/KR/cases/`에 보존된다.

## 3. 변경 판정

- 법령·행정규칙: 현행 `version_id`, 시행일, 정규화 본문 SHA-256을 비교한다.
- 공식 스냅숏: 내려받은 원파일 SHA-256을 별도로 보존한다. 국가법령정보센터가 같은 본문을 새 PDF로 렌더링하면 원파일 해시는 달라질 수 있으므로 법적 내용 변경은 본문 해시로 판단한다.
- 판례: 국가법령정보센터 통합검색의 고정 검색식 결과에서 `precSeq`를 수집한다.
- 공정위·환경부: 저장 검색결과의 상세페이지 링크 집합을 해시하여 신규·삭제 결과를 탐지한다.
- 오류·차단: 수집 실패는 정상 결과로 간주하지 않고 `source_watches.status=error:*` 및 감사 경고로 남긴다.

## 4. 판례·처분 승격 규칙

자동 수집 결과의 기본 상태는 `pending_human_review`이다. 다음을 모두 확인하기 전에는 `case_records`에 편입하지 않는다.

1. 공식 원문과 사건번호·의결번호
2. 기관·법원, 결정일·선고일, 절차단계
3. 확정 여부와 상급심·불복·후속 처분
4. 실제 환경주장 문구, 적용 법조문, 판단, 제재·구제
5. 동일 사건 중복 여부
6. 원문 URL·검색일·스냅숏 해시

검토 결과는 `approved_for_import`, `excluded`, `duplicate`, `needs_update` 중 하나로 기록한다. `approved_for_import`도 자동 승격되지 않으며, 구조화된 검증 JSON을 별도로 가져온다.

**실측 한계(2026-07-05):** 법제처 API(korean-law MCP)의 `ftc`(공정위 결정문)·`precedent` 도메인은
환경성 표시·광고(그린워싱) 심결례·판례를 거의 반환하지 않았다. korean-law MCP는 법령 조문 원문
확인·현행성 검증에는 신뢰도가 높으나(표시광고법 제3조·제5조, 환경기술산업법 제16조의10 확인 완료),
심결례 검증은 별도 경로가 필요하다.

### 후속 과제 — 심결례·판례 검증 경로 (미착수)

현재 `2-evaluation.json`의 `precedents`는 비어 있고 `confirm_needed`에 "심결례 보강 필요"로 남긴다.
다음 중 하나로 채운다. 착수 전까지 제출 문서는 심결례 인용 없이 조문 근거만으로 작성한다.

1. **공정위 사건검색 DB화** — https://case.ftc.go.kr/ocp/co/ltfr.do 의 의결서를 수집·구조화해
   `import-json`으로 편입. Open API가 개방되면 자동화 대상.
2. **사내 판례·심결례 DB** — 사내망에서 접근 가능한 판례·심결례로 검증.
   기밀·망분리 정책상 로컬/사내에서 수행하고 결과만 구조화 JSON으로 반입.

두 경로 모두 자동 편입 금지 — §4 승격 규칙(사람 확인 후 `import-json`)을 따른다.

## 5. 공개자료 교차확인 유지보수

- 회사 홈페이지는 `context.yaml`의 `company_homepage`에서 같은 도메인 내 환경·지속가능성 관련 링크를 최대 2단계로 수집한다.
- 언론은 회사명과 주요 주장유형을 조합한 Google News RSS 검색을 사용한다.
- 기사 검색 결과는 원문이 아니라 포인터일 수 있으므로 `search_pointer_only`로 표시한다.
- 반복 보도·회사 보도자료 전재는 독립 실증으로 취급하지 않는다.
- 기사 삭제·내용 변경에 대비해 검색일, 제목, 게시일, URL, 로컬 텍스트와 해시를 보존한다.
- 중요한 상충 신호는 원기사·정정보도·후속기사까지 사람이 확인한다.

## 6. 자동 실행 설치

샘플 launchd 파일은 `ops/`에 있다. 경로를 확인한 뒤 사용자가 직접 설치한다.

```bash
mkdir -p .gw/logs
cp ops/com.greenwashing.weekly.plist ~/Library/LaunchAgents/
cp ops/com.greenwashing.monthly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.greenwashing.weekly.plist
launchctl load ~/Library/LaunchAgents/com.greenwashing.monthly.plist
```

자동 작업은 외부 제출·발송이나 법률판단 덮어쓰기를 하지 않는다. 종료코드 2는 검토할 변경이나 coverage 공백이 있다는 뜻이며 로그를 확인해야 한다.

