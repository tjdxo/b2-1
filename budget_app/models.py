"""Data model and input validation."""
from dataclasses import asdict, dataclass, field
from datetime import date


class AppError(Exception):
    """User-correctable application error."""


def check_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise AppError("날짜는 YYYY-MM-DD 형식이어야 합니다. 예: 2026-10-19") from exc
    return value


def check_month(value: str) -> str:
    try:
        if len(value) != 7 or date.fromisoformat(value + '-01').strftime('%Y-%m') != value:
            raise ValueError
    except ValueError as exc:
        raise AppError("월은 YYYY-MM 형식이어야 합니다. 예: 2026-10") from exc
    return value


def positive_int(value: object) -> int:
    try:
        if isinstance(value, bool) or str(value).strip() != str(int(str(value).strip())):
            raise ValueError
        number = int(str(value).strip())
    except (ValueError, TypeError) as exc:
        raise AppError("금액은 양의 정수여야 합니다. 예: 15000") from exc
    if number <= 0:
        raise AppError("금액은 0보다 커야 합니다.")
    return number


def nonnegative_int(value: object) -> int:
    try:
        number = int(str(value))
    except (ValueError, TypeError) as exc:
        raise AppError("0 이상의 정수를 입력하세요.") from exc
    if number < 0:
        raise AppError("0 이상의 정수를 입력하세요.")
    return number


def parse_tags(value: str) -> list[str]:
    return list(dict.fromkeys(tag.strip() for tag in value.split(',') if tag.strip()))


@dataclass
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ''
    tags: list[str] = field(default_factory=list)

    def validate(self) -> None:
        check_date(self.date)
        if self.type not in {'income', 'expense'}:
            raise AppError("타입은 income 또는 expense여야 합니다.")
        self.amount = positive_int(self.amount)
        if not isinstance(self.category, str) or not self.category.strip():
            raise AppError("카테고리를 입력하세요.")
        if not isinstance(self.tags, list) or not all(isinstance(t, str) for t in self.tags):
            raise AppError("태그는 문자열 목록이어야 합니다.")

    def to_dict(self) -> dict:
        return asdict(self)
