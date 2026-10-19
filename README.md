# 나만의 용돈 기입장

Python **3.10+**, 표준 라이브러리만 사용하는 콘솔 가계부입니다. 별도 설치(`pip install`)는 필요하지 않습니다. 보너스 과제는 구현 범위에서 제외했습니다.

## 실행 방법

압축을 해제한 프로젝트 루트(`pocket_budget/`)에서 실행합니다.

```bash
python -m budget_app --help
python -m budget_app add
python -m budget_app list --limit 10
```

저장 폴더 변경(전역 옵션은 **명령 앞**에 기입):

```bash
python -m budget_app --data-dir ./other_data list
```

명령 도움말: `python -m budget_app search --help` (모든 명령과 하위 명령에서 사용 가능)

## 설계와 폴더 구조

```text
pocket_budget/
├── README.md
├── .gitignore
├── budget_app/
│   ├── __init__.py      # 패키지 표시
│   ├── __main__.py      # python -m 진입점
│   ├── cli.py           # argparse, 사용자 입력, 출력, 예외 데코레이터
│   ├── models.py        # Transaction dataclass, 입력 검증, AppError
│   ├── storage.py       # JSONL 파일 입출력, 순차 읽기, 안전한 다시 쓰기
│   └── service.py       # 거래/카테고리/예산 규칙, 집계, CSV 변환
├── examples/
│   └── import_sample.csv
└── tests/
    └── test_budget.py
```

기본 저장 위치는 **프로젝트 실행 경로의 `./data/`**입니다. 첫 명령 실행 시 디렉터리 및 3개 파일이 자동 생성됩니다.

- `transactions.jsonl`: 한 행에 거래 JSON 객체 1개 (id, type, date, amount, category, memo, tags)
- `categories.jsonl`: 한 행에 `{"name":"food"}` 형태의 객체 1개. 최초 빈 파일이면 기본 `food, transport, rent, salary, etc` 생성
- `budgets.jsonl`: 한 행에 `{"month":"2026-10","amount":500000}` 형태의 객체 1개

JSONL은 UTF-8이고 데이터가 프로그램 종료 후에도 유지됩니다. `update/delete`는 임시 파일로 전체 재작성 후 교체하며, 이는 파일 저장 시 데이터 손실 위험을 줄이기 위한 **필수 데이터 안정성 구현**입니다. 별도의 백업 명령 등 보너스 기능은 없습니다.

## 주요 명령

```bash
python -m budget_app add
# 프롬프트에 날짜, 타입, 카테고리, 금액, 메모, 태그 순서대로 입력
python -m budget_app list --limit 3
python -m budget_app search --from 2026-10-01 --to 2026-10-31 --category food --type expense --q 점심 --tag meal
python -m budget_app summary --month 2026-10 --top 3
python -m budget_app budget set --month 2026-10 --amount 500000
python -m budget_app budget get --month 2026-10
python -m budget_app category add
python -m budget_app category list
python -m budget_app category remove --name rent
python -m budget_app update --id TX-실제ID
python -m budget_app delete --id TX-실제ID
python -m budget_app import --from examples/import_sample.csv
python -m budget_app export --out october.csv --month 2026-10
python -m budget_app export --out range.csv --from 2026-10-01 --to 2026-10-31
```

`update`는 **대화형 고정**입니다. ID만 옵션으로 지정하고 모든 값을 순서대로 확인합니다. Enter면 기존 필드 유지, 메모/태그에 `-`를 넣으면 내용 삭제입니다. `category remove`는 사용 중이면 차단합니다. 예산은 월 총 **지출**과 비교하며 초과 시 경고를 출력합니다. 거래 날짜가 같으면 거래 ID를 보조 정렬 기준으로 사용합니다. ID는 무작위 고유 값이라 번호 순서가 곧 입력 순서는 아닙니다.

## CSV import/export 스키마

UTF-8, **헤더 포함**, 표준 CSV(쉼표 구분)입니다.

| 열 | 필수 | 설명 |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | `income` 또는 `expense` |
| category | Y | 등록된 카테고리 |
| amount | Y | 0보다 큰 정수 |
| memo | N | 문자열(없으면 빈 값) |
| tags | N | 태그 여러 개는 쉼표 구분. CSV 안에서는 `"meal,school"`처럼 큰따옴표로 감싸기 |

CSV에는 ID가 없습니다. **import 때 새 ID를 발급**하므로 동일 파일을 재가져오면 중복 내역이 생길 수 있습니다. 가져오기 전 CSV 모든 행의 유효성을 검증하고 한 행이라도 잘못되면 전체 가져오기를 취소합니다. 올바른 행은 전부 추가하며 `skipped=0`입니다. export는 필터를 필수로 받습니다.

## 핵심 학습 개념

1. **모델** `Transaction`: `@dataclass`에 필드와 타입 힌트를 정의하고 `validate()`로 값을 검증합니다.
2. **저장소** `JsonlStore.iter_transactions()`: `yield`로 파일을 한 줄씩 읽어 전량 메모리에 적재하지 않습니다.
3. **서비스** `BudgetService`: 조회/검색/요약/예산 정책을 저장 로직과 분리합니다. `list`는 `heapq.nlargest`를 이용해 지정한 개수만 메모리에 유지하며, `search/export`는 최대 500건씩 임시 파일로 정렬해 합치는 외부 병합 정렬로 최신순 출력합니다.
4. **데코레이터** `@handle_errors`: CLI 실행 중 검증/파일 오류를 스택트레이스 대신 사용자 친화적 오류와 힌트로 바꾸며 실패시 종료 코드 1을 반환합니다.
5. **안전한 저장**: 수정/삭제 및 일괄 가져오기는 기존 파일을 바로 덮어쓰지 않고 임시 파일 생성 후 `os.replace`로 교체합니다. 단일 프로세스 사용을 가정하며 동시 다중 프로세스 쓰기 잠금은 제공하지 않습니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

빈 저장소, CRUD, 필터/정렬, 예산 집계, 잘못된 CSV, export/import, 명령어 오류 코드를 검증합니다.

---

## 평가표 대응 및 발표용 설명 (필수 미션)

이 절은 평가표의 **기능 확인 → 구조 설명 → 설계 판단** 순서로 작성했습니다. `PASS`는 제공된 코드와 기존 실행 로그/자동 테스트에 근거한 판단이며, 수동으로 아직 수행하지 않은 경우는 **추가 확인**으로 표시했습니다. 보너스 기능은 평가 대상에서 제외했습니다.

### 항목 1. 기능 동작과 데이터 안정성

| 평가 질문 | 판정 및 근거 | 확인 명령 / 방법 |
| --- | --- | --- |
| `add/list/search/summary/export/import/update/delete`가 요구사항대로 동작하는가? | **대체로 PASS.** `add/list/search/summary/import/export/update`는 수동 실행 로그로 확인했고, `delete`는 자동 테스트에서 성공. CLI에서 정상 삭제를 한 번 더 직접 확인하면 좋음. | `python -m unittest discover -s tests -v`; `python -m budget_app delete --id TX-실제ID` |
| 재실행해도 거래·카테고리·예산이 유지되는가? 파일 3개 이상인가? | **PASS(저장 구조 확인).** `transactions.jsonl`, `categories.jsonl`, `budgets.jsonl`의 3개 파일을 생성하고 읽기/쓰기를 수행함. 제공된 파일 내용에서 거래·카테고리·예산 저장도 확인됨. 재실행 직후 `list/category list/budget get`으로 최종 확인 가능. | `python -m budget_app list`; `python -m budget_app category list`; `python -m budget_app budget get --month 2026-10` |
| `category add/list/remove` 및 사용 중 카테고리 삭제 방지 | **PASS.** 등록·조회·미사용 카테고리 삭제는 수동 실행, 사용 중 삭제 차단은 자동 테스트에서 확인. | 거래가 있는 `food`에 `category remove --name food` 실행 시 차단 확인 |
| `budget set` 저장과 `summary` 사용률/초과 경고 | **PASS(일부 추가 확인).** 500,000원 설정 후 지출 55,000원에 11.0% 사용률 확인. `expense > budget`일 때 `[경고] 월 예산 초과!` 출력하는 코드가 있으며 초과 상황은 수동 재확인 권장. | `python -m budget_app budget set --month 2026-10 --amount 1000` 후 같은 달 `summary` |
| `import/export`의 UTF-8·헤더·컬럼 스키마 | **PASS.** `csv.DictReader/DictWriter` 사용, `date,type,category,amount,memo,tags` 헤더 기록. 내보낸 결과의 5개 행과 JSONL 거래 5개 일치. 가져오기는 UTF-8 및 UTF-8 BOM 입력을 허용함. | `python -m budget_app export --out october.csv --month 2026-10` |
| 잘못된 입력/파일 오류에 스택트레이스 대신 원인+힌트 출력 | **대체로 PASS.** `@handle_errors`가 `AppError`, `OSError`, `csv.Error`를 잡아 `[오류]`, `[힌트]` 출력. 잘못된 대화형 필드 값은 `prompt_fields()`가 오류 후 재입력 요청. 임의의 예상 밖 프로그래밍 오류까지 숨기는 것은 아님. | `python -m budget_app delete --id NOT-FOUND`; `python -m budget_app import --from missing.csv` |
| 오류 종료 코드가 0이 아닌가? | **PASS.** 데코레이터는 오류에서 `1`, 정상 동작에서 `0` 반환. 자동 테스트로 `main()`의 `1` 반환도 확인됨. | 아래 종료 코드 확인 예시 참고 |

종료 코드는 macOS/Linux 터미널에서 **바로 직전에 실행한 명령**의 결과를 `$?`로 확인할 수 있습니다.

```bash
python -m budget_app delete --id NOT-FOUND
echo $?  # 1 (오류)
python -m budget_app category list
echo $?  # 0 (정상)
```

**설명 예시:** “거래, 카테고리, 예산을 각각 JSONL 파일에 저장하고, 프로그램을 다시 실행해도 기존 파일을 읽기 때문에 데이터가 유지됩니다. 사용 중인 카테고리는 삭제하지 못하도록 막고, 잘못된 입력은 사용자에게 오류와 해결 힌트를 보여주도록 구현했습니다.”

### 항목 2. 모듈과 클래스 설계, 수정/삭제의 안전성

**Q. 코드를 어떻게 3개 이상 모듈로 나눴는가?**

- `models.py`: `Transaction` 데이터 구조와 날짜·금액 등의 유효성 검증
- `storage.py`: JSONL 읽기/추가/전체 재작성 등 파일 I/O
- `service.py`: 거래 CRUD, 검색, 요약, 예산, 카테고리 규칙, CSV 변환
- `cli.py`: `argparse` 명령 처리, `input()`과 출력, 공통 오류 처리
- `__main__.py`: `python -m budget_app` 실행 진입점

**답변:** “사용자 입력, 실제 업무 규칙, 파일 저장을 분리했습니다. 예를 들어 저장 위치가 바뀌어도 거래 계산 규칙을 고칠 필요가 없고, CLI 출력 방식을 바꿔도 저장 코드는 그대로 둘 수 있습니다.”

**Q. 두 개 이상의 클래스는 각각 무슨 책임을 맡는가?**

- `Transaction` (`@dataclass`): **거래 한 건**의 필드와 값 검증을 책임집니다. `id/type/date/amount/category/memo/tags`를 갖습니다.
- `JsonlStore`: 데이터를 **어떻게 파일에 저장하고 읽는지** 책임집니다. 조회용 제너레이터 및 파일 교체를 구현합니다.
- `BudgetService`: 데이터를 **어떤 규칙으로 처리할지** 책임집니다. 예를 들어 카테고리 존재 여부, 사용 중 삭제 방지, 월별 집계를 판단합니다.

**Q. `update/delete`를 어떻게 안전하게 처리했는가?**

1. `BudgetService.find()`로 요청한 ID가 존재하는지 먼저 확인합니다.
2. `JsonlStore.rewrite_transactions()`에서 기존 데이터를 한 줄씩 읽으며 대상 거래를 변경하거나 제외합니다.
3. 같은 디렉터리의 임시 파일에 결과를 쓰고 `flush()`/`os.fsync()` 후 `os.replace()`로 기존 파일을 교체합니다.
4. 따라서 **기존 파일을 읽는 도중 바로 덮어쓰지 않아**, 정상적인 파일 교체 전 단계에서 실패하면 원본이 보존되는 방식입니다. 다만 다중 프로세스 동시 쓰기나 완전한 데이터베이스 트랜잭션까지 보장하지는 않습니다.

**짧게 답하면:** “수정/삭제 때 원본 파일을 직접 편집하지 않고 임시 파일에 새 내용을 완성한 뒤 교체했습니다. 이 방식은 처리 중 오류로 원본이 일부만 덮어써지는 위험을 줄입니다.”

### 항목 3. 제너레이터·데코레이터·타입 힌트

**Q. `list/search`를 어떻게 제너레이터로 구현했고 왜 유리한가?**

`JsonlStore.read_objects()`가 JSONL을 한 줄씩 읽으며 `yield`로 객체를 내보내고, `iter_transactions()`가 이를 `Transaction`으로 바꿔 `yield`합니다. 서비스의 `iter_filtered()`는 조건을 만족하는 거래만 다시 `yield`합니다. 즉, 원본 파일 전체를 `list()`로 메모리에 올리지 않습니다.

- `list`: `heapq.nlargest(limit, ...)`로 최신 **N건만 메모리에 유지**합니다.
- `search`와 `export`: 500건 단위로 정렬한 임시 파일들을 `heapq.merge()`로 합쳐 최신순으로 순차 출력합니다. **단, 임시 디스크 공간과 파일 개수는 증가**합니다.

**답변:** “`yield`는 한 번에 모든 거래를 반환하지 않고 필요한 순간에 한 건씩 처리합니다. 따라서 파일이 커져도 전체 거래를 메모리에 올리지 않는 장점이 있습니다.”

**Q. 데코레이터는 무엇을 분리했는가?**

`cli.py`의 `@handle_errors`는 명령 실행 함수 `run()`을 감쌉니다. 공통적으로 발생하는 검증·파일·CSV 오류를 잡아 `[오류]`와 `[힌트]`를 출력하고 오류 종료 코드 `1`을 반환합니다. 각 명령마다 동일한 `try/except`를 반복하지 않아도 되므로 **명령의 본래 처리 과정이 잘 보입니다.** 실행 시간 측정 데코레이터는 구현하지 않았으며, **예외 처리 데코레이터 1개만으로 필수 요구조건을 충족**합니다.

**Q. 타입 힌트는 어떻게 적용했고 왜 도움이 되는가?**

예: `def iter_transactions(self) -> Iterator[Transaction]:`은 “호출자가 거래 객체를 하나씩 받을 수 있다”는 약속입니다. `def set_budget(self, month: str, amount: int) -> None:`은 매개변수와 반환 계약을 표현합니다. IDE의 자동완성과 정적 분석, 협업 시 함수 이해에 유리합니다. **타입 힌트 자체가 런타임 입력을 막지는 않으므로**, `positive_int()`, `check_date()`, `Transaction.validate()`로 실제 값을 별도로 검사합니다.

### 항목 4. 저장 형식, 대용량 확장, 잘못된 CSV

**Q. JSONL과 CSV의 장단점, JSONL을 선택한 이유는?**

| 비교 | JSONL (선택) | CSV |
| --- | --- | --- |
| 장점 | JSON 객체를 행 단위로 저장, `tags` 같은 목록 타입 표현이 자연스러움, 한 줄씩 순차 읽기 쉬움 | 엑셀·스프레드시트 호환성이 좋고 사람이 표 형태로 보기 쉬움 |
| 단점 | CSV보다 파일 크기가 커질 수 있고 엑셀로 바로 열기 불편함 | 목록 타입은 문자열로 인코딩해야 하고 쉼표·따옴표 이스케이프 처리가 필요함 |
| 이번 적용 | 내부 거래·카테고리·예산 3개 파일을 JSONL로 관리 | 사용자가 다른 프로그램과 교환할 때 `import/export`에 사용 |

**답변:** “내부에는 거래별 필드와 태그 목록을 저장해야 해서 JSONL을 선택했습니다. 파일을 한 줄씩 읽기 편하고, 다른 프로그램과의 호환성은 CSV 가져오기/내보내기로 확보했습니다.”

**Q. 10만 건으로 증가하면 병목은 어디이고 어떻게 개선할까?**

현재는 파일을 순차로 탐색하므로 `find/update/delete` 때 많은 행을 읽고, `update/delete/import`는 거래 파일을 다시 작성합니다. `summary`도 해당 월만 바로 찾아가는 인덱스가 없어 전체 거래를 검사합니다. `search`는 500건 단위 임시 정렬 파일을 만들기 때문에 **디스크 I/O와 임시 파일 개수**, 여러 파일 병합 과정에서의 파일 핸들 수가 병목이 될 수 있습니다. 특히 10만 건이면 임시 파일이 최대 약 **200개** 생성될 수 있습니다(모든 거래가 검색에 포함될 때).

개선 방향은 다음과 같습니다.

1. 파일 기반을 유지한다면 월별 파일로 분리하거나 ID/날짜 인덱스를 추가해 불필요한 순차 탐색을 줄입니다.
2. 검색 정렬은 한 번에 여는 임시 파일 수를 제한하는 **다단계 병합**으로 확장합니다.
3. 데이터가 계속 커지거나 동시 사용자가 생기면 **SQLite**의 인덱스·트랜잭션으로 이전하는 것을 고려합니다. SQLite는 현재 미션에서 구현한 기능이 아니라 **향후 개선안**입니다.

**Q. CSV에 깨진 행이 있으면 사용자 신뢰를 어떻게 지키는가?**

현재 `import_csv()`는 모든 CSV 행을 먼저 읽어 **날짜/타입/카테고리/금액 등 전체를 검증**하고, 새 거래를 임시 저장소(`TemporaryFile`)에 모읍니다. 행 하나라도 잘못되면 `CSV N행 오류: ...`를 보여주고 **기존 거래 파일에는 아무것도 반영하지 않습니다(전체 취소/롤백 정책)**. 전부 유효할 때만 기존 거래와 새 거래를 합쳐 임시 파일로 저장한 뒤 교체합니다. 그래서 부분적으로 잘못 들어간 데이터를 뒤늦게 정리할 필요가 없습니다.

- **현재 정책:** 부분 성공이 아니라 **전체 실패**, 정상 CSV에 대해서만 `imported=N, skipped=0` 표시
- **보완 가능:** 오류 행 번호와 사유를 별도 리포트 CSV로 저장해 수정 후 다시 가져오기 쉽게 할 수 있음. 이는 **향후 개선안**이며 현재 구현되어 있지 않음
- **주의:** 동일한 정상 CSV를 두 번 가져오면 새 ID로 다시 등록되므로 중복 가져오기는 별도로 주의해야 함

### 평가 전 최종 확인 명령

```bash
python -m unittest discover -s tests -v
python -m budget_app list --limit 3
python -m budget_app category list
python -m budget_app budget get --month 2026-10
python -m budget_app summary --month 2026-10 --top 3
python -m budget_app delete --id NOT-FOUND
echo $?
```

위의 실패 명령 뒤 `echo $?`가 `1`이면 오류 종료 코드가 확인된 것입니다. **실제 거래 삭제 테스트**는 `list`에서 확인한 진짜 ID로 수행하고 데이터 변경에 유의하세요.

### 테스트 데이터 초기화

기존 파일을 잃지 않으려면 프로젝트 루트에서 폴더 이름을 바꿔 백업합니다.

```bash
mv data "data_backup_$(date +%Y%m%d_%H%M%S)"
python -m budget_app category list
```

새 `data/` 및 기본 카테고리와 빈 거래/예산 파일이 생성됩니다. `october.csv`처럼 프로젝트 루트에 만든 CSV는 영향을 받지 않습니다. 현재 코드에서는 **카테고리 파일이 비어 있으면 기본 카테고리를 다시 생성**하므로, 모든 카테고리를 삭제해 비워 둔 경우에도 다음 실행에서 기본 카테고리가 생기는 점에 유의하세요.
