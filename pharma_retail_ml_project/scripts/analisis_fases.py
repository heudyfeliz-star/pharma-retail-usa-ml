#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analisis por fases temporales para la muestra farmacéutica sintética.

Uso:
python scripts/analisis_fases.py \
  --input data/processed/dataset_unificado_mensual.csv \
  --output-dir reports/figures

Las comparaciones son descriptivas de la simulación, no inferencia causal.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

BASELINE = "Baseline 2019"
COVID = "Fase descriptiva COVID-19 (mar-2020 a may-2023)"
POST = "Fase posterior descriptiva (jun-2023 a oct-2026)"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path("data/processed/dataset_unificado_mensual.csv"))
    p.add_argument("--output-dir", type=Path, default=Path("reports/figures"))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input, parse_dates=["month"])
    required = {
        "month", "product_id", "product_name", "sale_category",
        "modeled_units_month", "coverage_factor", "reference_units_full_month",
        "category_annual_multiplier", "synthetic_monthly_noise_multiplier",
        "calibration_level", "is_partial_month"
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {sorted(missing)}")
    if df.duplicated(["month", "product_id"]).any():
        raise ValueError("Hay claves producto-mes duplicadas")
    if (df["coverage_factor"] <= 0).any():
        raise ValueError("coverage_factor debe ser positivo")

    # Equivalente de mes completo: ajuste de cobertura únicamente para comparar
    # la escala mensual; octubre de 2026 sigue siendo un mes parcial observado.
    df["full_month_equivalent"] = df["modeled_units_month"] / df["coverage_factor"]
    df["phase"] = np.select(
        [
            df["month"].between("2019-01-01", "2019-12-01"),
            df["month"].between("2020-03-01", "2023-05-01"),
            df["month"].between("2023-06-01", "2026-10-01"),
        ],
        [BASELINE, COVID, POST],
        default="Transición excluida (ene-feb 2020)"
    )

    selected = df[df["phase"] != "Transición excluida (ene-feb 2020)"].copy()
    phase_cat = (selected.groupby(["phase", "sale_category"], as_index=False)
        .agg(mean_units_per_product_month=("full_month_equivalent", "mean"),
             products=("product_id", "nunique"),
             months=("month", "nunique"),
             product_month_rows=("product_id", "size"),
             calibration_proxy_mean=("category_annual_multiplier", "mean"),
             synthetic_noise_mean=("synthetic_monthly_noise_multiplier", "mean")))
    baseline = (phase_cat[phase_cat["phase"] == BASELINE]
                .set_index("sale_category")["mean_units_per_product_month"])
    phase_cat["change_pct_vs_2019"] = phase_cat.apply(
        lambda r: (r["mean_units_per_product_month"] / baseline[r["sale_category"]] - 1) * 100,
        axis=1)
    phase_cat.to_csv(args.output_dir / "comparacion_fases_categoria.csv",
                     index=False, encoding="utf-8-sig")

    by_product = (selected.groupby(
        ["product_id", "product_name", "sale_category", "phase"], as_index=False)
        .agg(mean_units_per_product_month=("full_month_equivalent", "mean"),
             months=("month", "nunique")))
    wide = by_product.pivot(
        index=["product_id", "product_name", "sale_category"],
        columns="phase", values="mean_units_per_product_month").reset_index()
    for phase, out_col in [(COVID, "change_pct_covid_vs_2019"),
                           (POST, "change_pct_post_vs_2019")]:
        wide[out_col] = (wide[phase] / wide[BASELINE] - 1) * 100
    wide.to_csv(args.output_dir / "variacion_por_producto_fases.csv",
                index=False, encoding="utf-8-sig")

    # Variación anual por medicamento contra 2019; sólo años completos.
    complete = df[(df["month"].dt.year <= 2025) & (df["is_partial_month"] == 0)]
    annual = (complete.groupby(["product_id", "product_name", "sale_category", "year"], as_index=False)
        .agg(mean_units_per_product_month=("full_month_equivalent", "mean"),
             months=("month", "nunique")))
    annual = annual[annual["months"] == 12].copy()
    base = (annual[annual["year"] == 2019]
            [["product_id", "mean_units_per_product_month"]]
            .rename(columns={"mean_units_per_product_month": "baseline_2019"}))
    annual = annual.merge(base, on="product_id", how="left", validate="many_to_one")
    annual["change_pct_vs_2019"] = (
        annual["mean_units_per_product_month"] / annual["baseline_2019"] - 1) * 100
    annual.to_csv(args.output_dir / "variacion_anual_por_producto_vs_2019.csv",
                  index=False, encoding="utf-8-sig")

    # La descomposición se reporta como diseño del generador, no como causalidad:
    # valor aproximado = base * multiplicador de categoría * ruido * cobertura.
    decomposition = (df.groupby(["year", "sale_category", "calibration_level"], as_index=False)
        .agg(rows=("product_id", "size"),
             mean_category_multiplier=("category_annual_multiplier", "mean"),
             mean_synthetic_noise=("synthetic_monthly_noise_multiplier", "mean"),
             mean_full_month_equivalent=("full_month_equivalent", "mean")))
    decomposition.to_csv(args.output_dir / "descomposicion_calibracion_ruido.csv",
                         index=False, encoding="utf-8-sig")

    # Comprobación interna de invariancia de volumen modelado respecto al tamaño
    # de muestra: el generador usa RNG estable independiente para conteo y demanda.
    print("Fases y comparaciones creadas.")
    print(phase_cat.to_string(index=False))
    print("\nAdvertencia: la equivalencia mensual parcial es una normalización aritmética,")
    print("no una observación del mes completo ni una predicción.")
    print("Los cambios describen el simulador y no prueban efectos COVID-19.")


if __name__ == "__main__":
    main()
