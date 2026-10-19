# 나만의 용돈 기입장 (필수 미션)

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
