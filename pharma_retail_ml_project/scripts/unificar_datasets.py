"""Une las salidas REALES del generador farmacéutico usando pandas.
   Producto principal: 1 fila por (mes, medicamento). Los eventos detallados
   se exportan POR SEPARADO, ya que repetir métricas mensuales en cada evento
   provocaría sumas duplicadas. Ninguna cifra es una venta nacional observada.
   Uso: python scripts/unificar_datasets.py 
   --input-dir data/raw --output-dir data/processed
   Dependencia: pandas>=2.2.
"""


from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import pandas as pd

REQUIRED = (
    "products_catalog.csv",
    "pharma_retail_sales.csv",
    "pharma_monthly_sales.csv",
    "calibration_parameters.csv",
    "data_quality_report.csv",
    "generation_manifest.json",
)

# Columnas mínimas que deben existir en cada archivo (fallan rápido y claro).
REQUIRED_COLUMNS = {
    "products_catalog.csv": ["product_id", "sale_category"],
    "pharma_retail_sales.csv": ["transaction_id", "product_id", "month",
                                "sampled_units", "modeled_units_contribution"],
    "pharma_monthly_sales.csv": ["month", "product_id", "year",
                                 "sample_records", "sampled_units",
                                 "modeled_units_month", "coverage_factor",
                                 "is_partial_month"],
    "calibration_parameters.csv": ["product_id", "year", "annual_multiplier",
                                   "calibration_level", "source_url",
                                   "source_metric", "coverage", "notes"],
    "data_quality_report.csv": ["month", "test", "status"],
}


def check_columns(df: pd.DataFrame, source: str, columns: list[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{source}: faltan columnas requeridas {missing}. "
                         f"Columnas presentes: {list(df.columns)}")


def unique_key(df: pd.DataFrame, columns: list[str], source: str) -> None:
    if df[columns].isna().any().any():
        raise ValueError(f"{source}: claves nulas: {columns}")
    if df.duplicated(columns).any():
        example = df.loc[df.duplicated(columns, keep=False), columns].head(3)
        raise ValueError(f"{source}: clave duplicada {columns}\n{example}")


def merge_1_1(left: pd.DataFrame, right: pd.DataFrame, keys: list[str], source: str) -> pd.DataFrame:
    result = left.merge(right, how="left", on=keys, validate="one_to_one", indicator=True)
    if not result["_merge"].eq("both").all():
        missing = result.loc[result["_merge"] != "both", keys].head(5)
        raise ValueError(f"Faltan claves al unir {source}:\n{missing}")
    return result.drop(columns="_merge")


def build(input_dir: Path, output_dir: Path) -> dict:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    missing = [f for f in REQUIRED if not (input_dir / f).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Faltan archivos en {input_dir}: {', '.join(missing)}. "
            "Ejecuta primero el generador con --output-dir data/raw"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Lectura de CSV con tipos explícitos ---------------------------------
    catalog = pd.read_csv(input_dir / "products_catalog.csv", dtype={"product_id": "string"})
    monthly = pd.read_csv(input_dir / "pharma_monthly_sales.csv",
                          dtype={"product_id": "string", "month": "string"})
    events = pd.read_csv(input_dir / "pharma_retail_sales.csv",
                         dtype={"transaction_id": "string", "product_id": "string", "month": "string"})
    calibration = pd.read_csv(input_dir / "calibration_parameters.csv",
                              dtype={"product_id": "string"})
    qa = pd.read_csv(input_dir / "data_quality_report.csv", dtype={"month": "string"})
    with (input_dir / "generation_manifest.json").open(encoding="utf-8") as fp:
        manifest = json.load(fp)

    # --- Validación de esquema ----------------------------------------------
    for name, cols in REQUIRED_COLUMNS.items():
        frame = {
            "products_catalog.csv": catalog,
            "pharma_retail_sales.csv": events,
            "pharma_monthly_sales.csv": monthly,
            "calibration_parameters.csv": calibration,
            "data_quality_report.csv": qa,
        }[name]
        check_columns(frame, name, cols)

    # --- Normalización de fechas y años -------------------------------------
    for frame in (monthly, events, qa):
        frame["month"] = pd.to_datetime(frame["month"], format="%Y-%m", errors="raise")
    monthly["year"] = pd.to_numeric(monthly["year"], errors="raise").astype("int64")
    calibration["year"] = pd.to_numeric(calibration["year"], errors="raise").astype("int64")

    if not (monthly["month"].dt.year == monthly["year"]).all():
        raise ValueError("monthly.year contradice a monthly.month")

    for frame, name in ((catalog, "catalog"), (monthly, "monthly"),
                        (events, "events"), (calibration, "calibration")):
        if frame.empty:
            raise ValueError(f"Archivo {name} vacío")

    # --- Validaciones de granularidad ---------------------------------------
    unique_key(catalog, ["product_id"], "products_catalog")
    unique_key(monthly, ["month", "product_id"], "pharma_monthly_sales")
    unique_key(calibration, ["product_id", "year"], "calibration_parameters")
    unique_key(events, ["transaction_id"], "pharma_retail_sales")

    if len(catalog) != 62 or catalog["sale_category"].value_counts().to_dict() != {
        "OTC": 30, "RX": 30, "CONTROLLED": 2
    }:
        raise ValueError("Catálogo no corresponde a los 62 productos acordados")

    # --- Agregar eventos a granularidad producto-mes ------------------------
    ev_totals = (events.groupby(["month", "product_id"], as_index=False)
                 .agg(events_count=("transaction_id", "size"),
                      sample_units_from_events=("sampled_units", "sum"),
                      contributions_from_events=("modeled_units_contribution", "sum")))
    unique_key(ev_totals, ["month", "product_id"], "event aggregates")

    if len(ev_totals) != len(monthly):
        raise ValueError("La cobertura producto-mes de eventos difiere de la tabla mensual")

    full = merge_1_1(monthly, ev_totals, ["month", "product_id"], "eventos agregados")

    if not full["sample_records"].eq(full["events_count"]).all():
        raise ValueError("sample_records no coincide con el número de eventos por producto-mes")
    if not full["sampled_units"].eq(full["sample_units_from_events"]).all():
        raise ValueError("sampled_units mensual no concuerda con eventos")
    if not ((full["contributions_from_events"] - full["modeled_units_month"]).abs() < 1e-5).all():
        raise ValueError("Contribuciones ponderadas no cuadran con modeled_units_month")

    # --- Merge con catálogo (conservando sale_category y therapeutic_group) --
    # ORIGINAL: se eliminaba sale_category y luego se comparaba.
    # FIX: conservamos ambas columnas del catálogo y comparamos con sufijo.
    catalog_for_merge = catalog.copy()
    # Renombramos para detectar colisiones con monthly, si las hubiera.
    overlap = set(catalog_for_merge.columns) & set(full.columns) - {"product_id"}
    rename_map = {c: f"{c}_catalog" for c in overlap}
    if rename_map:
        catalog_for_merge = catalog_for_merge.rename(columns=rename_map)

    full = full.merge(catalog_for_merge, how="left", on="product_id",
                      validate="many_to_one", indicator=True)
    if not full["_merge"].eq("both").all():
        raise ValueError("Hay product_id que no aparecen en el catálogo")
    full.drop(columns="_merge", inplace=True)

    # Verificar coherencia de sale_category (viene del catálogo; si monthly
    # también la traía, comparar).
    if "sale_category" in catalog.columns:
        cat_check = catalog.set_index("product_id")["sale_category"]
        if "sale_category" in monthly.columns:
            if not full["sale_category"].eq(
                full["product_id"].map(cat_check)
            ).all():
                raise ValueError("Inconsistencia de categoría entre monthly y catálogo")

    # --- Merge con calibración anual por producto ---------------------------
    cal = calibration.rename(columns={
        "annual_multiplier": "evidence_annual_multiplier",
        "calibration_level": "evidence_calibration_level",
        "source_url": "evidence_source_url",
        "source_metric": "evidence_source_metric",
        "coverage": "evidence_coverage",
        "notes": "evidence_notes",
    })
    full = full.merge(cal, how="left", on=["product_id", "year"],
                      validate="many_to_one", indicator=True)
    if not full["_merge"].eq("both").all():
        raise ValueError("Faltan parámetros de calibración por producto-año")
    full.drop(columns="_merge", inplace=True)

    if "category_annual_multiplier" in full.columns:
        if not ((full["category_annual_multiplier"] -
                 full["evidence_annual_multiplier"]).abs() < 1e-9).all():
            raise ValueError("Multiplicadores de monthly y calibración anual difieren")
    # Comparaba full["calibration_level"] que fue renombrada.
    # solo comparar si monthly trae la columna original.
    if "calibration_level" in monthly.columns:
        if not full["calibration_level"].eq(
            full["evidence_calibration_level"]
        ).all():
            raise ValueError("Niveles de calibración incompatibles")

    # --- Merge con QA resumido por mes --------------------------------------
    qa_summary = (qa.groupby("month", as_index=False)
                  .agg(qa_tests=("test", "size"),
                       qa_all_pass=("status", lambda s: s.eq("PASS").all())))
    failed = qa.loc[qa["status"].ne("PASS")].groupby("month")["test"].agg("; ".join)
    qa_summary["qa_failed_tests"] = qa_summary["month"].map(failed).fillna("")

    full = full.merge(qa_summary, how="left", on="month",
                      validate="many_to_one", indicator=True)
    if not full["_merge"].eq("both").all() or not full["qa_all_pass"].all():
        raise ValueError("QA faltante o alguna validación del generador no superada")
    full.drop(columns="_merge", inplace=True)

    # --- Auditoría contra el manifest ---------------------------------------
    manifest_monthly = pd.json_normalize(manifest.get("monthly_summary", []))
    if manifest_monthly.empty:
        raise ValueError("El manifest no contiene monthly_summary")
    manifest_monthly["month"] = pd.to_datetime(
        manifest_monthly["month"], format="%Y-%m", errors="raise"
    )
    unique_key(manifest_monthly, ["month"], "manifest.monthly_summary")

    for column in ("sample_rows", "modeled_units", "partial"):
        if column not in manifest_monthly.columns:
            raise ValueError(f"Falta monthly_summary.{column}")

    computed = full.groupby("month", as_index=False).agg(
        check_sample_rows=("sample_records", "sum"),
        check_modeled_units=("modeled_units_month", "sum"),
        check_partial=("is_partial_month", "max"),
    )
    audit = merge_1_1(computed, manifest_monthly, ["month"], "resumen mensual del JSON")

    if not (audit["sample_rows"] == audit["check_sample_rows"]).all():
        raise ValueError("monthly_summary.sample_rows no coincide con monthly")
    if not (audit["modeled_units"] == audit["check_modeled_units"]).all():
        raise ValueError("monthly_summary.modeled_units no coincide con monthly")
    if not (audit["partial"].astype(int) == audit["check_partial"].astype(int)).all():
        raise ValueError("Bandera parcial del manifest no coincide")

    if manifest["total_products"] != len(catalog) or \
       manifest["number_of_months"] != full["month"].nunique():
        raise ValueError("Conteos declarados en JSON no coinciden con los datos")
    if len(full) != len(catalog) * full["month"].nunique():
        raise ValueError("Faltan producto-meses en la cuadrícula de 62 productos")
    if manifest["total_sample_rows"] != len(events):
        raise ValueError("El JSON contiene un total de eventos distinto")
    if manifest["total_synthetic_modeled_units"] != int(full["modeled_units_month"].sum()):
        raise ValueError("Total modelado del JSON no coincide")

    # --- Adjuntar propiedades escalares del manifest ------------------------
    mapping = {
        "generator_version": "run_generator_version",
        "period_start": "run_period_start",
        "period_end": "run_period_end",
        "base_units_per_product_month": "run_base_units_per_product_month",
        "base_records_per_month": "run_base_records_per_month",
        "monthly_variation_pct": "run_monthly_variation_pct",
        "synthetic_monthly_product_noise_sd": "run_synthetic_monthly_product_noise_sd",
        "seed": "run_seed",
        "national_representativeness": "run_national_representativeness",
        "market_estimate": "run_market_estimate",
        "row_definition": "run_row_definition",
        "unit_definition": "run_unit_definition",
    }
    for src, dst in mapping.items():
        full[dst] = manifest.get(src)

    full["modeled_units_full_month_equivalent"] = (
        full["modeled_units_month"] / full["coverage_factor"]
    )
    full["year"] = full["month"].dt.year
    full["month_number"] = full["month"].dt.month
    full["quarter"] = full["month"].dt.quarter
    full["year_month"] = full["month"].dt.strftime("%Y-%m")
    full["data_nature"] = "SYNTHETIC_NONREPRESENTATIVE"

    # --- Dataset 1: tabla mensual (una fila por producto-mes) ---------------
    full = full.sort_values(["month", "product_id"]).reset_index(drop=True)
    full.to_csv(output_dir / "dataset_unificado_mensual.csv",
                index=False, encoding="utf-8-sig")

    # --- Dataset 2: eventos enriquecidos (sin columnas aditivas mensuales) --
    detail_cols = [
        "month", "product_id", "product_name", "active_ingredient", "strength",
        "dosage_form", "therapeutic_group", "evidence_annual_multiplier",
        "evidence_calibration_level", "evidence_source_url", "run_seed",
    ]
    # validar que existan todas las columnas antes de seleccionar.
    missing_detail = [c for c in detail_cols if c not in full.columns]
    if missing_detail:
        raise ValueError(
            f"No se pueden construir las columnas de detalle: faltan {missing_detail}. "
            "Revisa que products_catalog.csv incluya product_name, "
            "active_ingredient, strength, dosage_form, therapeutic_group."
        )
    detail_metadata = full[detail_cols].copy()

    detail = events.merge(detail_metadata, how="left", on=["month", "product_id"],
                          validate="many_to_one", indicator=True)
    if not detail["_merge"].eq("both").all():
        raise ValueError("Faltan claves para enriquecer eventos")
    detail.drop(columns="_merge", inplace=True)
    detail.to_csv(output_dir / "dataset_transaccional_enriquecido.csv",
                  index=False, encoding="utf-8-sig")

    # --- Copia del manifest (evitar SameFileError) --------------------------
    src_manifest = (input_dir / "generation_manifest.json").resolve()
    dst_manifest = (output_dir / "metadata_manifest.json").resolve()
    if src_manifest != dst_manifest:
        shutil.copyfile(src_manifest, dst_manifest)

    audit.to_csv(output_dir / "auditoria_manifest_mensual.csv",
                 index=False, encoding="utf-8-sig")

    stats = {
        "products": int(len(catalog)),
        "months": int(full["month"].nunique()),
        "product_month_rows": int(len(full)),
        "sample_event_rows": int(len(detail)),
        "modeled_abstract_product_units": int(full["modeled_units_month"].sum()),
        "all_qa_pass": bool(full["qa_all_pass"].all()),
        "units_are_actual_national_sales": False,
    }
    (output_dir / "resumen_validaciones.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unificación y validación con pandas, sin duplicar medidas"
    )
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    results = build(args.input_dir, args.output_dir)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("Archivo principal:", (args.output_dir / "dataset_unificado_mensual.csv").resolve())
    print("Detalle separado:", (args.output_dir / "dataset_transaccional_enriquecido.csv").resolve())

if __name__ == "__main__":
    main()
