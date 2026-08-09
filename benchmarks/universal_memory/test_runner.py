import tempfile, unittest
from pathlib import Path
from runner import BudgetedConsolidation, LamfBaseline, relevance_metrics


class ContractTests(unittest.TestCase):
    def test_relevance_counts_consolidated_provenance(self):
        result = [{"source_ids":["a", "b"]}]
        self.assertEqual(relevance_metrics(result, {"a", "b"}, 5), (1.0, 1.0, 1.0, 1.0))

    def test_adapter_names_are_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(LamfBaseline(Path(tmp)/"a").name, "lamf-baseline")
            self.assertEqual(BudgetedConsolidation(Path(tmp)/"b").name,
                             "budgeted-consolidation-v1")

if __name__ == "__main__": unittest.main()
