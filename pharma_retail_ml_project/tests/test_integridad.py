"""Pruebas de aceptación. Ejecutar tras generar datos y unificar.
python -m unittest discover -s tests -v
"""
import json
import unittest
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


class IntegridadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(PROCESSED / "dataset_unificado_mensual.csv")
        cls.tx = pd.read_csv(PROCESSED / "dataset_transaccional_enriquecido.csv")
        cls.m = json.loads((PROCESSED / "metadata_manifest.json").read_text(encoding="utf-8"))

    def test_catalogo_y_periodos(self):
        self.assertEqual(self.df.product_id.nunique(), 62)
        self.assertEqual(self.df.year_month.nunique(), 94)
        self.assertEqual(len(self.df), 5828)

    def test_granularidad(self):
        self.assertFalse(self.df.duplicated(["month", "product_id"]).any())
        self.assertFalse(self.tx.transaction_id.duplicated().any())

    def test_reconciliacion(self):
        self.assertEqual(int(self.df.modeled_units_month.sum()), self.m["total_synthetic_modeled_units"])
        self.assertEqual(len(self.tx), self.m["total_sample_rows"])
        self.assertEqual(int(self.df.sample_records.sum()), len(self.tx))

    def test_regulaciones_y_calidad(self):
        categories = self.df.groupby("sale_category").product_id.nunique().to_dict()
        self.assertEqual(categories, {"OTC": 30, "RX": 30, "CONTROLLED": 2})
        self.assertTrue(self.df.qa_all_pass.all())

    def test_advertencia_naturaleza_sintetica(self):
        self.assertFalse(self.m["national_representativeness"])
        self.assertFalse(self.m["market_estimate"])
        self.assertEqual(self.df.data_nature.nunique(), 1)


if __name__ == "__main__":
    unittest.main()
