"""Argparse CLI; interactive add/update/category add."""
import argparse
import functools
import sys
from pathlib import Path

from .models import AppError, check_date, check_month, parse_tags, positive_int
from .service import BudgetService
from .storage import JsonlStore


def handle_errors(func):
    """Decorator keeps exception-to-user-message conversion out of command logic."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> int:
        try:
            return func(*args, **kwargs)
        except (AppError, OSError, csv_error()) as exc:
            print(f'[오류] {exc}\n[힌트] 입력값, 경로 및 --help를 확인하세요.', file=sys.stderr)
            return 1
        except (EOFError, KeyboardInterrupt):
            print('\n[오류] 입력이 취소되었습니다.', file=sys.stderr)
            return 1
    return wrapper


def csv_error():
    import csv
    return csv.Error


def prompt(label: str, default: str | None = None) -> str:
    suffix = f' [{default}]' if default is not None else ''
    value = input(f'{label}{suffix}: ').strip()
    return value if value else (default if default is not None else '')


def prompt_fields(service: BudgetService, initial=None) -> dict:
    """For update, Enter preserves existing field; '-' clears memo/tags."""
    def get(key, title):
        old = initial.get(key) if initial else None
        if isinstance(old, list):
            old = ','.join(old)
        return prompt(title, str(old) if old is not None else None)

    while True:
        try:
            dt = check_date(get('date', '날짜(YYYY-MM-DD)'))
            kind = get('type', '타입(income/expense)')
            category = get('category', f'카테고리 {service.categories()}')
            amount = positive_int(get('amount', '금액(양수 정수)'))
            memo = get('memo', '메모(선택)')
            tags = get('tags', '태그(쉼표 구분)')
            fields = {'date': dt, 'type': kind, 'category': category, 'amount': amount,
                      'memo': '' if memo == '-' else memo,
                      'tags': parse_tags('' if tags == '-' else tags)}
            from .models import Transaction
            service.validate_transaction(Transaction('TEMP', **fields))
            return fields
        except AppError as exc:
            print(f'[오류] {exc}\n다시 입력해 주세요.')


def display(tx) -> None:
    print(f'{tx.id} | {tx.date} | {tx.type} | {tx.category} | '
          f'{tx.amount}원 | {tx.memo} | tags={",".join(tx.tags)}')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='python -m budget_app', description='JSONL 기반 콘솔 용돈 기입장')
    parser.add_argument('--data-dir', type=Path, default=Path('./data'), help='저장 폴더 (기본 ./data)')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('add', help='대화형 거래 추가')
    listing = commands.add_parser('list', help='최신순 거래 조회')
    listing.add_argument('--limit', type=int, default=10)
    search = commands.add_parser('search', help='조건 검색 (최신순)')
    search.add_argument('--from', dest='start')
    search.add_argument('--to', dest='end')
    search.add_argument('--category')
    search.add_argument('--type', dest='kind', choices=['income', 'expense'])
    search.add_argument('--q')
    search.add_argument('--tag')
    summary = commands.add_parser('summary', help='월별 수입/지출/예산')
    summary.add_argument('--month', required=True)
    summary.add_argument('--top', type=int, default=3)
    budget = commands.add_parser('budget', help='월 예산 관리')
    budget_sub = budget.add_subparsers(dest='action', required=True)
    budget_set = budget_sub.add_parser('set', help='예산 설정')
    budget_set.add_argument('--month', required=True)
    budget_set.add_argument('--amount', required=True)
    budget_get = budget_sub.add_parser('get', help='예산 조회')
    budget_get.add_argument('--month', required=True)
    category = commands.add_parser('category', help='카테고리 관리')
    category_sub = category.add_subparsers(dest='action', required=True)
    category_sub.add_parser('add', help='대화형 카테고리 추가')
    category_sub.add_parser('list', help='카테고리 조회')
    category_rm = category_sub.add_parser('remove', help='카테고리 삭제')
    category_rm.add_argument('--name', required=True)
    update = commands.add_parser('update', help='대화형 거래 수정 (Enter 유지)')
    update.add_argument('--id', required=True)
    delete = commands.add_parser('delete', help='거래 삭제')
    delete.add_argument('--id', required=True)
    importing = commands.add_parser('import', help='CSV 거래 일괄 등록')
    importing.add_argument('--from', dest='source', type=Path, required=True)
    exporting = commands.add_parser('export', help='조건부 CSV 내보내기')
    exporting.add_argument('--out', type=Path, required=True)
    exporting.add_argument('--month')
    exporting.add_argument('--from', dest='start')
    exporting.add_argument('--to', dest='end')
    return parser


def filters_from(args):
    start = getattr(args, 'start', None)
    end = getattr(args, 'end', None)
    month = getattr(args, 'month', None)
    if start:
        check_date(start)
    if end:
        check_date(end)
    if month:
        check_month(month)
    if start and end and start > end:
        raise AppError('--from 날짜가 --to보다 늦습니다.')
    return dict(start=start, end=end, month=month,
                **{key: getattr(args, key, None) for key in ('category', 'kind', 'q', 'tag')})


@handle_errors
def run(args: argparse.Namespace) -> int:
    service = BudgetService(JsonlStore(args.data_dir))
    cmd = args.command
    if cmd == 'add':
        print(f'등록 카테고리: {", ".join(service.categories())}')
        tx = service.add(**prompt_fields(service))
        print(f'[저장 완료] id={tx.id}')
    elif cmd == 'list':
        if args.limit <= 0:
            raise AppError('--limit은 1 이상이어야 합니다.')
        items = service.recent(args.limit)
        for tx in items:
            display(tx)
        if not items:
            print('데이터 없음')
    elif cmd == 'search':
        found = False
        for tx in service.sorted_filtered(**filters_from(args)):
            display(tx)
            found = True
        if not found:
            print('검색 결과 없음')
    elif cmd == 'summary':
        if args.top <= 0:
            raise AppError('--top은 1 이상이어야 합니다.')
        info = service.summary(args.month, args.top)
        if not info['count']:
            print('해당 월 거래 데이터 없음')
        print(f"총 수입: {info['income']}원\n총 지출: {info['expense']}원\n잔액: {info['balance']}원")
        if info['budget'] is not None:
            rate = info['expense'] / info['budget'] * 100
            print(f"예산: {info['budget']}원 (사용률 {rate:.1f}%)")
            if info['expense'] > info['budget']:
                print('[경고] 월 예산 초과!')
        print(f'지출 TOP {args.top}')
        for i, (name, amount) in enumerate(info['top'], 1):
            print(f'{i}) {name} {amount}원')
    elif cmd == 'budget':
        check_month(args.month)
        if args.action == 'set':
            service.set_budget(args.month, positive_int(args.amount))
            print(f'[저장 완료] {args.month} 예산 {args.amount}원')
        else:
            amount = service.store.get_budgets().get(args.month)
            print(f'{args.month} 예산: {amount}원' if amount is not None else '설정된 예산 없음')
    elif cmd == 'category':
        if args.action == 'add':
            name = prompt('카테고리명')
            service.add_category(name)
            print(f'[저장 완료] category={name}')
        elif args.action == 'list':
            for name in service.categories():
                print(f'- {name}')
        else:
            service.remove_category(args.name)
            print(f'[삭제 완료] category={args.name}')
    elif cmd == 'update':
        before = service.find(args.id)
        print('수정할 값을 입력하세요. Enter=기존 유지, 메모/태그 -=비우기')
        service.update(args.id, **prompt_fields(service, before.to_dict()))
        print(f'[수정 완료] id={args.id}')
    elif cmd == 'delete':
        service.delete(args.id)
        print(f'[삭제 완료] id={args.id}')
    elif cmd == 'import':
        imported, skipped = service.import_csv(args.source)
        print(f'[완료] imported={imported}, skipped={skipped}')
    elif cmd == 'export':
        if not (args.month or args.start or args.end):
            raise AppError('export에는 --month 또는 --from/--to 조건이 필요합니다.')
        total = service.export_csv(args.out, **filters_from(args))
        print(f'[완료] {args.out} ({total} records)')
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)
