"""Business rules, stream sorting and import/export."""
import csv
import heapq
import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .models import (AppError, Transaction, check_date, check_month,
                     parse_tags, positive_int)
from .storage import JsonlStore

CSV_COLUMNS = ['date', 'type', 'category', 'amount', 'memo', 'tags']


class BudgetService:
    def __init__(self, store: JsonlStore):
        self.store = store

    def validate_transaction(self, tx: Transaction) -> Transaction:
        tx.validate()
        if tx.category not in self.store.get_categories():
            raise AppError(f"등록되지 않은 카테고리: {tx.category}. category add로 등록하세요.")
        return tx

    def add(self, **fields) -> Transaction:
        tx = self.validate_transaction(Transaction(id='TX-' + uuid4().hex[:12].upper(), **fields))
        self.store.append(tx)
        return tx

    def categories(self) -> list[str]:
        return self.store.get_categories()

    def add_category(self, name: str) -> None:
        name = name.strip()
        if not name or ',' in name or '\n' in name:
            raise AppError('카테고리명은 비어 있거나 쉼표/줄바꿈을 포함할 수 없습니다.')
        values = self.categories()
        if name in values:
            raise AppError('이미 존재하는 카테고리입니다.')
        self.store.set_categories(values + [name])

    def remove_category(self, name: str) -> None:
        values = self.categories()
        if name not in values:
            raise AppError('없는 카테고리입니다. category list로 확인하세요.')
        if any(tx.category == name for tx in self.store.iter_transactions()):
            raise AppError('사용 중인 카테고리는 삭제할 수 없습니다. 거래를 먼저 수정/삭제하세요.')
        self.store.set_categories([item for item in values if item != name])

    def find(self, txid: str) -> Transaction:
        for tx in self.store.iter_transactions():
            if tx.id == txid:
                return tx
        raise AppError(f'없는 거래 id: {txid}. list로 확인하세요.')

    def update(self, txid: str, **changes) -> None:
        original = self.find(txid)
        fields = original.to_dict()
        fields.update(changes)
        replacement = self.validate_transaction(Transaction(**fields))
        self.store.rewrite_transactions(lambda tx: replacement if tx.id == txid else tx)

    def delete(self, txid: str) -> None:
        self.find(txid)
        self.store.rewrite_transactions(lambda tx: None if tx.id == txid else tx)

    @staticmethod
    def matches(tx: Transaction, *, start: str | None = None, end: str | None = None,
                month: str | None = None, category: str | None = None,
                kind: str | None = None, q: str | None = None, tag: str | None = None) -> bool:
        return (not start or tx.date >= start) and (not end or tx.date <= end) and \
            (not month or tx.date.startswith(month + '-')) and \
            (not category or tx.category == category) and \
            (not kind or tx.type == kind) and \
            (not q or q.casefold() in tx.memo.casefold()) and \
            (not tag or tag in tx.tags)

    def iter_filtered(self, **filters) -> Iterator[Transaction]:
        for tx in self.store.iter_transactions():
            if self.matches(tx, **filters):
                yield tx

    def recent(self, limit: int, **filters) -> list[Transaction]:
        """Keep only N best rows in memory; newest date then id."""
        return heapq.nlargest(limit, self.iter_filtered(**filters), key=lambda t: (t.date, t.id))

    def sorted_filtered(self, **filters) -> Iterator[Transaction]:
        """External merge-sort: never hold all matching transactions in RAM."""
        chunk_size = 500
        with tempfile.TemporaryDirectory(prefix='budget-sort-') as folder:
            files: list[Path] = []
            chunk: list[Transaction] = []

            def save_chunk() -> None:
                chunk.sort(key=lambda t: (t.date, t.id), reverse=True)
                path = Path(folder) / f'{len(files)}.jsonl'
                with path.open('w', encoding='utf-8') as out:
                    for tx in chunk:
                        out.write(json.dumps(tx.to_dict(), ensure_ascii=False) + '\n')
                files.append(path)
                chunk.clear()

            for tx in self.iter_filtered(**filters):
                chunk.append(tx)
                if len(chunk) >= chunk_size:
                    save_chunk()
            if chunk:
                save_chunk()

            def rows(path: Path) -> Iterator[tuple[tuple[int, str], Transaction]]:
                for obj in JsonlStore.read_objects(path):
                    tx = Transaction(**obj)
                    yield ((-int(tx.date.replace('-', '')), ''.join(chr(0x10ffff - ord(c)) for c in tx.id)), tx)

            streams = [rows(path) for path in files]
            for _, tx in heapq.merge(*streams, key=lambda pair: pair[0]):
                yield tx

    def summary(self, month: str, top: int) -> dict:
        check_month(month)
        income = expense = count = 0
        groups: dict[str, int] = defaultdict(int)
        for tx in self.iter_filtered(month=month):
            count += 1
            if tx.type == 'income':
                income += tx.amount
            else:
                expense += tx.amount
                groups[tx.category] += tx.amount
        budget = self.store.get_budgets().get(month)
        return {'count': count, 'income': income, 'expense': expense,
                'balance': income - expense, 'budget': budget,
                'top': sorted(groups.items(), key=lambda x: (-x[1], x[0]))[:top]}

    def set_budget(self, month: str, amount: int) -> None:
        check_month(month)
        budgets = self.store.get_budgets()
        budgets[month] = positive_int(amount)
        self.store.set_budgets(budgets)

    def import_csv(self, source: Path) -> tuple[int, int]:
        """Validate whole CSV before writing any rows. Duplicates are imported again."""
        if not source.is_file():
            raise AppError(f'CSV 파일이 없습니다: {source}')
        with tempfile.TemporaryFile(mode='w+t', encoding='utf-8') as spool:
            count = 0
            try:
                with source.open('r', encoding='utf-8-sig', newline='') as file:
                    reader = csv.DictReader(file)
                    if not reader.fieldnames or not all(c in reader.fieldnames for c in CSV_COLUMNS[:4]):
                        raise AppError('CSV 헤더에 date,type,category,amount가 필요합니다.')
                    for line, row in enumerate(reader, 2):
                        try:
                            if None in row:
                                raise AppError('열 수가 맞지 않습니다.')
                            tx = self.validate_transaction(Transaction(
                                id='TX-' + uuid4().hex[:12].upper(),
                                date=row['date'], type=row['type'], category=row['category'],
                                amount=positive_int(row['amount']),
                                memo=row.get('memo') or '', tags=parse_tags(row.get('tags') or '')))
                        except (AppError, TypeError) as exc:
                            raise AppError(f'CSV {line}행 오류: {exc}') from exc
                        spool.write(json.dumps(tx.to_dict(), ensure_ascii=False) + '\n')
                        count += 1
            except UnicodeError as exc:
                raise AppError('CSV는 UTF-8로 저장하세요.') from exc
            spool.seek(0)
            def combined():
                for tx in self.store.iter_transactions():
                    yield tx.to_dict()
                for line in spool:
                    yield json.loads(line)
            self.store.atomic_write(self.store.transactions, combined())
        return count, 0

    def export_csv(self, target: Path, **filters) -> int:
        # Write to temporary file first to avoid leaving a partially exported CSV.
        target.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        temp = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='',
                    dir=target.parent, delete=False) as file:
                temp = Path(file.name)
                writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                for tx in self.sorted_filtered(**filters):
                    writer.writerow({'date': tx.date, 'type': tx.type, 'category': tx.category,
                                     'amount': tx.amount, 'memo': tx.memo, 'tags': ','.join(tx.tags)})
                    count += 1
            temp.replace(target)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        return count
