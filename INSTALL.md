# 배포·설치 안내 (제3자용)

제3자(다른 변호사·팀)에게 이 도구를 **git 없이** 배포·설치하는 방법. 개요·사용법은 [README.md](README.md).

## 0. 무엇을 배포하나

배포 단위는 **프로젝트 폴더 전체**다. 스킬 파일(`SKILL.md`) 하나만으로는 동작하지 않는다 —
CLI(Python 패키지)·법령 DB·절차 문서가 함께 있어야 한다.

- 포함: `greenwashing/`(코드), `corpus/`(법령 원문·파싱), `.gw/state.sqlite3`(런타임 DB),
  `skills/`, 문서(`README`·`PLAN`·`EVALUATION-SOP`·`MAINTENANCE`), `tests/`
- **제외(기밀): `matters/`** — 실제 사건 폴더는 배포하지 않는다. 각자 로컬에서 생성한다.

## 1. 배포본 만들기 (배포자)

```bash
# 프로젝트 루트에서. 스탬프는 날짜 등으로.
scripts/package.sh 20260705
# → /tmp/greenwashing-counsel-20260705.zip  (matters/ 등 제외된 클린 zip)
```

전달 경로(택1): 이메일 첨부 · Google Drive·사내 파일서버 공유.
**기밀 사건이 들어간 `matters/`가 빠졌는지 zip을 열어 반드시 확인**한 뒤 전달한다.

## 2. 설치 (수신자)

### 2-1. 전제
- Python 3.11+
- Claude Code (로컬 CLI) — 스킬 실행용
- **korean-law MCP 서버** — 이 repo에 포함되지 않는다. 수신자의 Claude Code에 별도로 연결돼 있어야
  ②정밀평가(조문 포섭·심결례)가 동작한다. 미연결이면 ①③(추출·문서생성)은 되지만 ②는 수동이 된다.

### 2-2. 압축 해제·의존성
```bash
unzip greenwashing-counsel-20260705.zip -d ~/greenwashing-counsel
cd ~/greenwashing-counsel
pip install python-docx openpyxl pypdf python-pptx     # 또는: pip install -e .
```

### 2-3. 법령 DB
번들된 `.gw/state.sqlite3`로 바로 쓸 수 있다. 최신화하려면(권장):
```bash
python3 -m greenwashing corpus sync --jurisdiction KR   # 국가법령정보센터 원문 재수집(네트워크)
python3 -m greenwashing corpus audit                    # 상태 확인
```

### 2-4. 스킬 설치
프로젝트 안의 스킬을 `~/.claude/skills`에 연결한다(택1).
```bash
# 권장: 심링크(프로젝트 편집이 즉시 반영)
ln -s "$(pwd)/skills/greenwashing-review" ~/.claude/skills/greenwashing-review
# 또는: 복사(독립본)
cp -R skills/greenwashing-review ~/.claude/skills/greenwashing-review
```
설치 후 Claude Code에서 `/greenwashing-review`로 확인.

⚠️ 스킬 본문(`SKILL.md`)은 "프로젝트 루트"를 참조한다. 수신자는 자신이 클론·설치한 경로 기준으로
실행하면 되고, CLI(`python3 -m greenwashing`)는 프로젝트 루트에서 실행한다.

### 2-5. 설치 확인
```bash
python3 -m unittest discover -s tests          # 회귀 테스트 통과 확인
# 사건 폴더(matters/<사건>/)를 만들고 context.yaml·input/ 배치 후:
python3 -m greenwashing assess matters/<사건> --mode public
```

## 3. 업데이트

git을 쓰지 않으므로 새 zip을 받아 **코드·docs·corpus만 덮어쓰고**, 각자의 `matters/`와
`.gw/state.sqlite3`(직접 sync한 경우)는 보존한다. 스킬을 심링크로 설치했다면 프로젝트 갱신만으로 반영된다.

## 4. 대안 — Claude Code 플러그인/마켓플레이스

반복 배포·버전 관리가 필요하면 정식 **Claude Code 플러그인**으로 패키징하는 방법도 있다(이 repo를
플러그인 구조로 재구성 + 사내 마켓플레이스 등록). 현재는 zip 배포로 충분하며, 수요가 생기면 전환한다.

## 5. 기밀·안전 (필수)

- 배포본에 **실제 사건 자료를 넣지 않는다**(matters/ 제외 확인).
- 기밀 사건은 수신자도 `--mode confidential`로 처리하고, ②에서 사건 내부 문구를 외부(MCP·웹)에 넣지 않는다.
- 이 도구는 제출·발송 기능이 없고, 고발장은 변호사 승인 후에만 초안이 생성된다.
