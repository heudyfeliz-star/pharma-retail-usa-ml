#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Perfilado y controles de integridad de los archivos generados.

Ejecutar después del generador:
python scripts/perfil_calidad.py --input-dir data/raw --output-dir reports/quality
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

FILES = [
    "products_catalog.csv", "pharma_retail_sales.csv", "pharma_monthly_sales.csv",
    "calibration_parameters.csv", "data_quality_report.csv",
    "calibration_overrides_template.csv"
]


def require_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    duplicated = int(df.duplicated(keys).sum())
    if duplicated:
        raise ValueError(f"{label}: {duplicated} claves duplicadas en {keys}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--output-dir", type=Path, default=Path("reports/quality"))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    profiles = []
    tables = {}
    for filename in FILES:
        path = args.input_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"No existe archivo requerido: {path}")
        df = pd.read_csv(path)
        tables[filename] = df
        profiles.append({
            "file": filename, "rows": len(df), "columns": len(df.columns),
            "null_cells": int(df.isna().sum().sum()),
            "columns_with_nulls": int(df.isna().any().sum()),
            "duplicate_full_rows": int(df.duplicated().sum()),
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 3)
        })
        print(f"\n===== {filename} =====")
        print("HEAD\n", df.head().to_string(index=False))
        print("\nINFO")
        df.info()
        print("\nDESCRIBE\n", df.describe(include="all").transpose().to_string())
        print("\nNULOS\n", df.isna().sum().to_string())

    catalog = tables["products_catalog.csv"]
    monthly = tables["pharma_monthly_sales.csv"]
    events = tables["pharma_retail_sales.csv"]
    calibration = tables["calibration_parameters.csv"]
    require_unique(catalog, ["product_id"], "catálogo")
    require_unique(monthly, ["month", "product_id"], "ventas mensuales")
    require_unique(calibration, ["product_id", "year"], "calibraciones")
    require_unique(events, ["transaction_id"], "eventos")

    if len(catalog) != 62:
        raise ValueError(f"Se esperaban 62 productos; encontrados {len(catalog)}")
    if catalog["sale_category"].value_counts().to_dict() != {
        "OTC": 30, "RX": 30, "CONTROLLED": 2
    }:
        raise ValueError("Distribución de categorías distinta a 30 OTC, 30 RX, 2 CONTROLLED")

    event_counts = events.groupby(["month", "product_id"]).size()
    monthly_counts = monthly.set_index(["month", "product_id"])["sample_records"]
    if not event_counts.sort_index().equals(monthly_counts.sort_index().rename("sample_records")):
        raise ValueError("sample_records no coincide con cantidad de eventos")
    contributions = events.groupby(["month", "product_id"])["modeled_units_contribution"].sum()
    targets = monthly.set_index(["month", "product_id"])["modeled_units_month"]
    delta = (contributions - targets).abs()
    if delta.max() > 1e-5:
        raise ValueError(f"Contribuciones no concilian; diferencia máxima={delta.max()}")

    pd.DataFrame(profiles).to_csv(args.output_dir / "perfil_archivos.csv",
                                  index=False, encoding="utf-8-sig")
    print("\nPERFIL RESUMIDO")
    print(pd.DataFrame(profiles).to_string(index=False))
    print("\nPASS: unicidad, integridad referencial y conciliación de eventos/unidades.")
    print("La muestra y las unidades son sintéticas; no representan ventas nacionales.")


if __name__ == "__main__":
    main()
