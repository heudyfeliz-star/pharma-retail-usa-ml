#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EDA y gráficos de la MUESTRA SINTÉTICA (no de ventas nacionales observadas).
Uso: python scripts/visualizar_resultados.py --input data/processed/dataset_unificado_mensual.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/processed/dataset_unificado_mensual.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.input, parse_dates=["month"])
    needed = {"month", "year", "product_id", "product_name", "sale_category", "modeled_units_month", "coverage_factor", "calibration_level"}
    if not needed.issubset(df.columns):
        raise ValueError(f"Faltan columnas: {sorted(needed-set(df.columns))}")
    if df.duplicated(["month", "product_id"]).any():
        raise ValueError("El dataset analítico tiene producto-meses repetidos")
    df["equivalente_mes_completo"] = df["modeled_units_month"] / df["coverage_factor"]
    df["mes_parcial"] = df["coverage_factor"] < 1

    # 1: evolución de demanda simulada por grupo, como promedio POR PRODUCTO.
    # No son ventas nacionales; cada producto parte de una referencia artificial igual.
    trend = (df.groupby(["month", "sale_category"], as_index=False)
             .agg(media_producto=("equivalente_mes_completo", "mean")))
    plt.figure(figsize=(12, 5))
    for cat, sub in trend.groupby("sale_category"):
        sub = sub.sort_values("month")
        plt.plot(sub["month"], sub["media_producto"], label=cat, linewidth=1.5)
    plt.axvline(pd.Timestamp("2020-03-01"), linestyle="--", linewidth=1, label="Marzo 2020")
    plt.axvline(pd.Timestamp("2023-06-01"), linestyle=":", linewidth=1, label="Junio 2023")
    plt.title("Volumen sintético: unidades medias por producto-mes")
    plt.xlabel("Mes")
    plt.ylabel("Unidades abstractas modeladas por producto (mes completo equivalente)")
    plt.legend()
    plt.grid(alpha=.2)
    plt.tight_layout()
    plt.savefig(args.output_dir / "01_tendencias_por_categoria.png", dpi=150)
    plt.close()

    # 2: diferencias 2019 -> 2020, producto por producto; años completos.
    means = (df.loc[df["year"].isin([2019, 2020]) & ~df["mes_parcial"]]
             .groupby(["product_id", "product_name", "year"])["modeled_units_month"]
             .mean().unstack("year"))
    means = means.dropna(subset=[2019, 2020]).copy()
    means["cambio_pct_2020_vs_2019"] = (means[2020] / means[2019] - 1) * 100
    ranking = means.reindex(means["cambio_pct_2020_vs_2019"].abs().sort_values(ascending=False).index).head(15)
    plt.figure(figsize=(10, 7))
    labels = [f"{pid} — {name}" for pid, name in ranking.index]
    plt.barh(labels[::-1], ranking["cambio_pct_2020_vs_2019"].to_numpy()[::-1])
    plt.axvline(0, linewidth=.8)
    plt.title("15 cambios sintéticos más pronunciados: promedio 2020 vs. 2019")
    plt.xlabel("Variación porcentual de unidades modeladas")
    plt.tight_layout()
    plt.savefig(args.output_dir / "02_cambios_por_producto_2020.png", dpi=150)
    plt.close()

    # 3: nivel de respaldo de las observaciones.
    quality = df["calibration_level"].value_counts().sort_values()
    plt.figure(figsize=(10, 5))
    plt.barh(quality.index, quality.values)
    plt.title("Composición de observaciones según evidencia de calibración")
    plt.xlabel("Cantidad de combinaciones producto-mes")
    plt.tight_layout()
    plt.savefig(args.output_dir / "03_niveles_calibracion.png", dpi=150)
    plt.close()

    # Indicadores comparables: medias mensuales por medicamento, no totales por año.
    metrics = (df.groupby(["year", "sale_category"], as_index=False)
               .agg(media_unidades_producto_mes=("equivalente_mes_completo", "mean"),
                    productos=("product_id", "nunique"),
                    meses=("month", "nunique"),
                    meses_parciales=("mes_parcial", "sum")))
    metrics.to_csv(args.output_dir / "indicadores_por_anio_categoria.csv", index=False, encoding="utf-8-sig")
    changes = means.reset_index()[["product_id", "product_name", "cambio_pct_2020_vs_2019"]]
    changes.to_csv(args.output_dir / "variaciones_2020_vs_2019.csv", index=False, encoding="utf-8-sig")
    print("Gráficos y tablas creados en:", args.output_dir.resolve())
    print("ADVERTENCIA: series sintéticas; diferencias 2020-2019 no prueban impacto causal de COVID-19")


if __name__ == "__main__":
    main()
