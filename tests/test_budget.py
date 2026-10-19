import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

from budget_app.cli import main
from budget_app.models import AppError
from budget_app.service import BudgetService
from budget_app.storage import JsonlStore


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = JsonlStore(self.root / 'data')
        self.service = BudgetService(self.store)

    def add(self, date='2026-10-19', kind='expense', category='food', amount=100):
        return self.service.add(date=date, type=kind, category=category,
                                amount=amount, memo='점심', tags=['meal'])

    def test_initial_files(self):
        for name in ['transactions', 'categories', 'budgets']:
            self.assertTrue((self.root / 'data' / f'{name}.jsonl').exists())
        self.assertIn('food', self.service.categories())

    def test_crud_and_categories(self):
        tx = self.add()
        self.assertEqual(self.service.find(tx.id).amount, 100)
        with self.assertRaises(AppError):
            self.service.remove_category('food')
        self.service.update(tx.id, amount=200)
        self.assertEqual(self.service.find(tx.id).amount, 200)
        self.service.delete(tx.id)
        with self.assertRaises(AppError):
            self.service.find(tx.id)
        self.service.add_category('coffee')
        self.service.remove_category('coffee')

    def test_search_latest_and_budget(self):
        self.add(date='2026-10-01', amount=100)
        self.add(date='2026-10-19', amount=200)
        self.add(date='2026-09-01', kind='income', category='salary', amount=1000)
        result = list(self.service.sorted_filtered(month='2026-10', tag='meal'))
        self.assertEqual([tx.amount for tx in result], [200, 100])
        self.assertEqual(self.service.recent(1)[0].amount, 200)
        self.service.set_budget('2026-10', 250)
        report = self.service.summary('2026-10', 3)
        self.assertEqual((report['income'], report['expense'], report['balance']), (0, 300, -300))
        self.assertEqual(report['budget'], 250)

    def test_csv_import_export_and_invalid_rollback(self):
        self.add()
        output = self.root / 'export.csv'
        self.assertEqual(self.service.export_csv(output, month='2026-10'), 1)
        self.assertEqual(self.service.import_csv(output), (1, 0))
        self.assertEqual(len(list(self.store.iter_transactions())), 2)
        bad = self.root / 'bad.csv'
        bad.write_text('date,type,category,amount\n2026-10-01,expense,food,10\n'
                       '2026-10-02,expense,UNKNOWN,11\n', encoding='utf-8')
        with self.assertRaises(AppError):
            self.service.import_csv(bad)
        self.assertEqual(len(list(self.store.iter_transactions())), 2)

    def test_cli_error_exit_code(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            code = main(['--data-dir', str(self.root / 'data'), 'delete', '--id', 'NOT-FOUND'])
        self.assertEqual(code, 1)
        self.assertIn('없는 거래', out.getvalue())


if __name__ == '__main__':
    unittest.main()
