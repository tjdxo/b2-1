"""JSONL persistence. Transaction reading is lazy; writes use temp+replace."""
import json
import os
import tempfile
from pathlib import Path
from typing import Callable, Iterator

from .models import AppError, Transaction, check_month, positive_int

class JsonlStore:
    
    def __init__(self, data_dir: Path):
        self.root = data_dir
        self.root.mkdir(parents=True, exist_ok=True)

        self.transactions = self.root / "transactions.jsonl"
        self.categories = self.root / "categories.jsonl"
        self.budgets = self.root / "budgets.jsonl"

        # 최초 실행인지 확인
        first_run = not self.categories.exists()

        for path in (self.transactions, self.categories, self.budgets):
            path.touch(exist_ok=True)

        # 최초 실행일 때만 기본 카테고리 생성
        if first_run:
            default_categories = [
                "food", "transport", "rent", "salary", "etc"
            ]
            self.set_categories(default_categories)

    @staticmethod
    def read_objects(path: Path) -> Iterator[dict]:
        try:
            with path.open('r', encoding='utf-8') as stream:
                for number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        if not isinstance(obj, dict):
                            raise ValueError('객체가 아닙니다')
                    except (ValueError, json.JSONDecodeError) as exc:
                        raise AppError(f'{path.name} {number}행이 손상되었습니다. 파일을 확인하세요.') from exc
                    yield obj
        except UnicodeError as exc:
            raise AppError(f'{path.name} 파일 인코딩을 UTF-8로 확인하세요.') from exc

    def iter_transactions(self) -> Iterator[Transaction]:
        for obj in self.read_objects(self.transactions):
            try:
                tx = Transaction(**obj)
                tx.validate()
                yield tx
            except (TypeError, AppError) as exc:
                raise AppError('transactions.jsonl의 거래 데이터가 올바르지 않습니다.') from exc

    def append(self, tx: Transaction) -> None:
        with self.transactions.open('a', encoding='utf-8', newline='\n') as file:
            file.write(json.dumps(tx.to_dict(), ensure_ascii=False) + '\n')
            file.flush()
            os.fsync(file.fileno())

    @staticmethod
    def atomic_write(path: Path, objects) -> None:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8',
                    newline='\n', dir=path.parent, prefix='.tmp-', delete=False) as file:
                tmp_path = Path(file.name)
                for obj in objects:
                    file.write(json.dumps(obj, ensure_ascii=False) + '\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def rewrite_transactions(self, transform: Callable[[Transaction], Transaction | None]) -> None:
        def converted():
            for tx in self.iter_transactions():
                new = transform(tx)
                if new is not None:
                    yield new.to_dict()
        self.atomic_write(self.transactions, converted())

    def get_categories(self) -> list[str]:
        categories = []

        for number, obj in enumerate(self.read_objects(self.categories), 1):
            name = obj.get('name')

            if not isinstance(name, str) or not name.strip():
                raise AppError(
                    f'categories.jsonl {number}번째 데이터가 올바르지 않습니다. '
                    'name 항목을 확인하세요.'
                )

            categories.append(name)

        return categories
    def set_categories(self, names: list[str]) -> None:
        self.atomic_write(self.categories, ({'name': name} for name in names))

    
    def get_budgets(self) -> dict[str, int]:
        budgets = {}

        for number, obj in enumerate(self.read_objects(self.budgets), 1):
            try:
                month = obj['month']
                amount = obj['amount']

                # 기존 models.py 검증 함수 재사용
                check_month(month)
                amount = positive_int(amount)

            except (KeyError, TypeError, AppError) as exc:
                raise AppError(
                    f'budgets.jsonl {number}번째 데이터가 올바르지 않습니다. '
                    'month(YYYY-MM)와 amount(양의 정수)를 확인하세요.'
                ) from exc

            budgets[month] = amount

        return budgets

    def set_budgets(self, budgets: dict[str, int]) -> None:
        self.atomic_write(self.budgets,
            ({'month': month, 'amount': value} for month, value in sorted(budgets.items())))
