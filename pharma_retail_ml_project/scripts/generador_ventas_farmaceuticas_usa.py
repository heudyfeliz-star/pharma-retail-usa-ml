#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GENERADOR DE MUESTRA SINTETICA DE RETAIL FARMACEUTICO - ESTADOS UNIDOS
Periodo: enero 2019 a octubre 19 de 2026.

OBJETIVO
  Estudiar las variaciones de ventas / dispensaciones por medicamento y mes
  alrededor de la pandemia. NO son ventas observadas ni estimaciones oficiales
  del total del mercado de Estados Unidos.

DEPENDENCIAS
  Python 3.9+ (solo biblioteca estandar).

EJEMPLO
  python generador_ventas_farmaceuticas_usa.py --output-dir salidas
  python generador_ventas_farmaceuticas_usa.py --base-records-per-month 5000 --monthly-variation-pct 0.12
  python generador_ventas_farmaceuticas_usa.py --calibration-csv tendencias_verificadas.csv

CONCEPTOS
  BASE_UNITS_PER_PRODUCT_MONTH = 5850 es la referencia de unidades MODELANDAS
  para CADA producto en un mes completo de 2019, antes de fluctuaciones.
  Cada fila de pharma_retail_sales.csv es una OBSERVACION MUESTREADA sintetica
  de un producto en un mes, NO 1 venta nacional verificada. La columna
  modeled_units_contribution normaliza filas de ese producto/mes al total
  sintetico modelado (monthly_units_modeled).
  El numero de filas/mes se controla INDEPENDIENTEMENTE de esas unidades.
  Por ello cambiar filas/mes no cambia mecanicamente la demanda modelada.

CALIBRACION POR DEFECTO (LIMITADA Y TRANSPARENTE)
  1) Opioides (CTRL-001 y CTRL-002): cociente entre recetas anuales de opioides
     en general segun CDC/IQVIA, 2019-2024; PROXY DE CATEGORIA, NO una serie
     especifica para oxicodona ni morfina. 2025-2026: ultimo valor observado
     arrastrado, claramente marcado como supuesto sintético.
  2) Antibioticos seleccionados: variacion anual de dispensaciones
     ambulatorias totales en EE.UU. 2020 (-19.4%), 2021 (-15.4%), 2022
     (-5.5%) respecto a 2019; PROXY DE CATEGORIA, NO por cada ingrediente.
     2023-2026: factor neutral 1.0; NO extrapolacion documentada.
  3) Otros productos: factor neutral 1.0 (ausencia de calibracion), con
     ruido opcional etiquetado SINTETICO. NO se atribuyen cambios reales.
  4) Dentro de cada ano, factores anuales se asignan uniformemente a meses:
     NO se infiere estacionalidad mensual a partir de series anuales.
  5) Productos y nombres son una PRESELECCION de formulaciones existentes,
     no una verificacion automatica de NDC ni estado historico por fabricante.
     Antes del uso regulatorio, validar cada presentacion en FDA/DailyMed.

FUENTES
  CDC (IQVIA Xponent), series anuales: https://www.cdc.gov/overdose-prevention/data-research/facts-stats/us-dispensing-rate-maps.html
  Estudio antibioticos: https://pmc.ncbi.nlm.nih.gov/articles/PMC11526179/
  CMS Part D, alcance y limitaciones: https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-d-spending-by-drug
  FDA NDC (reconciliacion eventual): https://open.fda.gov/apis/drug/ndc/

IMPORTANTE
  La muestra no es representativa probabilistica nacional porque no
  conocemos fracciones ni probabilidades empiricas de inclusion. La
  normalizacion no es un peso muestral estimado del mercado real.
  La equivalencia "unidad vendida" es una UNIDAD COMERCIAL ABSTRACTA
  de cada producto, no miligramos, dosis, pastillas o pacientes.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_START = date(2019, 1, 1)
DEFAULT_END = date(2026, 10, 19)
DEFAULT_BASE_UNITS = 5850
DEFAULT_BASE_RECORDS = 6200  # observaciones de muestra/mes, no unidades modeladas
DEFAULT_MONTHLY_VARIATION = 0.12
DEFAULT_PRODUCT_NOISE_SD = 0.06  # ruido sintetico (distribucion lognormal)
DEFAULT_SEED = 42

CDC_URL = "https://www.cdc.gov/overdose-prevention/data-research/facts-stats/us-dispensing-rate-maps.html"
ANTIBIOTICS_URL = "https://pmc.ncbi.nlm.nih.gov/articles/PMC11526179/"
FDA_URL = "https://open.fda.gov/apis/drug/ndc/"
CMS_URL = "https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-d-spending-by-drug"

# Conteos de recetas dispensadas en farmacias minoristas (TODOS los opioides), CDC/IQVIA.
CDC_OPIOID_PRESCRIPTIONS = {
    2019: 153624095,
    2020: 143211932,
    2021: 139521926,
    2022: 131776213,
    2023: 125487979,
    2024: 120410433,
}
# Variaciones vs 2019 para conjunto de antibioticos ambulatorios; no por producto.
ANTIBIOTIC_MULTIPLIERS = {2019: 1.0, 2020: 0.806, 2021: 0.846, 2022: 0.945}
ANTIBIOTIC_IDS = {"RX-019", "RX-020", "RX-021", "RX-022", "RX-023"}

# (ID, nombre, principio(s) activo(s), concentracion, presentacion, familia)
# Ninguna fila representa otro producto que aparezca repetido en el catalogo.
PRODUCT_ROWS = [
    ("OTC-001", "Tylenol Extra Strength", "Acetaminophen", "500 mg", "tablet", "PAIN_FEVER"),
    ("OTC-002", "Advil", "Ibuprofen", "200 mg", "tablet", "PAIN_FEVER"),
    ("OTC-003", "Aleve", "Naproxen sodium", "220 mg", "tablet", "PAIN_FEVER"),
    ("OTC-004", "Aspirin generic", "Acetylsalicylic acid", "325 mg", "tablet", "PAIN_FEVER"),
    ("OTC-005", "Claritin", "Loratadine", "10 mg", "tablet", "ALLERGY"),
    ("OTC-006", "Zyrtec", "Cetirizine", "10 mg", "tablet", "ALLERGY"),
    ("OTC-007", "Allegra", "Fexofenadine", "180 mg", "tablet", "ALLERGY"),
    ("OTC-008", "Benadryl", "Diphenhydramine HCl", "25 mg", "tablet", "ALLERGY"),
    ("OTC-009", "Pepcid AC Maximum Strength", "Famotidine", "20 mg", "tablet", "GI"),
    ("OTC-010", "Prilosec OTC", "Omeprazole", "20 mg", "delayed-release tablet", "GI"),
    ("OTC-011", "Nexium 24HR", "Esomeprazole", "20 mg", "delayed-release capsule", "GI"),
    ("OTC-012", "Tums Extra Strength", "Calcium carbonate", "750 mg", "chewable tablet", "GI"),
    ("OTC-013", "Pepto-Bismol", "Bismuth subsalicylate", "262 mg", "chewable tablet", "GI"),
    ("OTC-014", "Imodium A-D", "Loperamide HCl", "2 mg", "caplet", "GI"),
    ("OTC-015", "Gas-X Extra Strength", "Simethicone", "125 mg", "softgel", "GI"),
    ("OTC-016", "MiraLAX", "Polyethylene glycol 3350", "17 g/dose", "powder", "GI"),
    ("OTC-017", "Dulcolax", "Bisacodyl", "5 mg", "delayed-release tablet", "GI"),
    ("OTC-018", "Colace", "Docusate sodium", "100 mg", "softgel", "GI"),
    ("OTC-019", "Senokot", "Sennosides", "8.6 mg", "tablet", "GI"),
    ("OTC-020", "Mucinex", "Guaifenesin", "600 mg", "extended-release tablet", "RESPIRATORY_OTC"),
    ("OTC-021", "Dextromethorphan generic", "Dextromethorphan HBr", "15 mg/5 mL", "oral solution", "RESPIRATORY_OTC"),
    ("OTC-022", "Dramamine Original", "Dimenhydrinate", "50 mg", "tablet", "MOTION_SICKNESS"),
    ("OTC-023", "Afrin Original", "Oxymetazoline HCl", "0.05%", "nasal spray", "RESPIRATORY_OTC"),
    ("OTC-024", "Flonase Allergy Relief", "Fluticasone propionate", "50 mcg/actuation", "nasal spray", "ALLERGY"),
    ("OTC-025", "Zaditor", "Ketotifen fumarate", "0.025%", "ophthalmic solution", "ALLERGY"),
    ("OTC-026", "Lotrimin AF", "Clotrimazole", "1%", "cream", "DERMATOLOGY"),
    ("OTC-027", "Lamisil AT", "Terbinafine HCl", "1%", "cream", "DERMATOLOGY"),
    ("OTC-028", "Cortizone-10", "Hydrocortisone", "1%", "cream", "DERMATOLOGY"),
    ("OTC-029", "Differin", "Adapalene", "0.1%", "gel", "DERMATOLOGY"),
    ("OTC-030", "Rogaine", "Minoxidil", "5%", "topical solution", "DERMATOLOGY"),
    ("RX-001", "Lipitor", "Atorvastatin", "20 mg", "tablet", "CARDIOVASCULAR"),
    ("RX-002", "Crestor", "Rosuvastatin", "10 mg", "tablet", "CARDIOVASCULAR"),
    ("RX-003", "Lisinopril generic", "Lisinopril", "10 mg", "tablet", "CARDIOVASCULAR"),
    ("RX-004", "Cozaar", "Losartan potassium", "50 mg", "tablet", "CARDIOVASCULAR"),
    ("RX-005", "Norvasc", "Amlodipine besylate", "5 mg", "tablet", "CARDIOVASCULAR"),
    ("RX-006", "Toprol-XL", "Metoprolol succinate", "50 mg", "extended-release tablet", "CARDIOVASCULAR"),
    ("RX-007", "Hydrochlorothiazide generic", "Hydrochlorothiazide", "25 mg", "tablet", "CARDIOVASCULAR"),
    ("RX-008", "Coreg", "Carvedilol", "12.5 mg", "tablet", "CARDIOVASCULAR"),
    ("RX-009", "Eliquis", "Apixaban", "5 mg", "tablet", "ANTICOAGULANT"),
    ("RX-010", "Xarelto", "Rivaroxaban", "20 mg", "tablet", "ANTICOAGULANT"),
    ("RX-011", "Metformin generic", "Metformin HCl", "500 mg", "tablet", "DIABETES"),
    ("RX-012", "Jardiance", "Empagliflozin", "10 mg", "tablet", "DIABETES"),
    ("RX-013", "Ozempic", "Semaglutide", "1 mg/dose", "prefilled injection pen", "DIABETES"),
    ("RX-014", "Synthroid", "Levothyroxine sodium", "50 mcg", "tablet", "ENDOCRINE"),
    ("RX-015", "Zoloft", "Sertraline HCl", "50 mg", "tablet", "PSYCHIATRY"),
    ("RX-016", "Lexapro", "Escitalopram", "10 mg", "tablet", "PSYCHIATRY"),
    ("RX-017", "Wellbutrin XL", "Bupropion HCl", "150 mg", "extended-release tablet", "PSYCHIATRY"),
    ("RX-018", "Prozac", "Fluoxetine HCl", "20 mg", "capsule", "PSYCHIATRY"),
    ("RX-019", "Amoxicillin generic", "Amoxicillin", "500 mg", "capsule", "ANTIBIOTIC"),
    ("RX-020", "Zithromax", "Azithromycin", "250 mg", "tablet", "ANTIBIOTIC"),
    ("RX-021", "Doxycycline generic", "Doxycycline", "100 mg", "tablet", "ANTIBIOTIC"),
    ("RX-022", "Cefdinir generic", "Cefdinir", "300 mg", "capsule", "ANTIBIOTIC"),
    ("RX-023", "Macrobid", "Nitrofurantoin", "100 mg", "capsule", "ANTIBIOTIC"),
    ("RX-024", "Ventolin HFA", "Albuterol sulfate", "90 mcg/actuation", "inhaler", "RESPIRATORY_RX"),
    ("RX-025", "Symbicort", "Budesonide + formoterol", "160/4.5 mcg/actuation", "inhaler", "RESPIRATORY_RX"),
    ("RX-026", "Singulair", "Montelukast", "10 mg", "tablet", "RESPIRATORY_RX"),
    ("RX-027", "Prednisone generic", "Prednisone", "20 mg", "tablet", "OTHER_RX"),
    ("RX-028", "Ondansetron generic ODT", "Ondansetron", "4 mg", "orally disintegrating tablet", "OTHER_RX"),
    ("RX-029", "Protonix", "Pantoprazole", "40 mg", "delayed-release tablet", "GI_RX"),
    ("RX-030", "Flomax", "Tamsulosin", "0.4 mg", "capsule", "UROLOGY"),
    ("CTRL-001", "Oxycodone HCl generic", "Oxycodone hydrochloride", "5 mg", "immediate-release tablet", "OPIOID_CONTROLLED"),
    ("CTRL-002", "Morphine sulfate generic", "Morphine sulfate", "15 mg", "immediate-release tablet", "OPIOID_CONTROLLED"),
]

PRODUCT_FIELDS = [
    "product_id", "product_name", "active_ingredient", "strength", "dosage_form",
    "therapeutic_group", "sale_category", "dea_schedule", "market", "catalog_verification",
    "regulatory_reference",
]


def category(pid: str) -> str:
    return "CONTROLLED" if pid.startswith("CTRL-") else "OTC" if pid.startswith("OTC-") else "RX"


def make_products() -> List[dict]:
    out = []
    for pid, name, ingredient, strength, form, group in PRODUCT_ROWS:
        cat = category(pid)
        out.append(dict(product_id=pid, product_name=name, active_ingredient=ingredient,
                        strength=strength, dosage_form=form, therapeutic_group=group,
                        sale_category=cat, dea_schedule="II" if cat == "CONTROLLED" else "",
                        market="United States", catalog_verification="CURATED_PRESELECTION_NOT_NDC_VERIFIED",
                        regulatory_reference=FDA_URL))
    return out


def validate_products(products: List[dict]) -> None:
    ids = [p["product_id"] for p in products]
    if len(ids) != len(set(ids)):
        raise ValueError("Identificadores repetidos en el catalogo")
    distribution = Counter(p["sale_category"] for p in products)
    if distribution != {"OTC": 30, "RX": 30, "CONTROLLED": 2}:
        raise ValueError(f"Composicion incorrecta: {distribution}")
    keys = [(p["active_ingredient"].casefold(), p["strength"].casefold(),
             p["dosage_form"].casefold()) for p in products]
    if len(keys) != len(set(keys)):
        raise ValueError("Misma formulacion aparece en mas de un producto")
    assert len(products) == 62
    assert all(p["dea_schedule"] == "II" for p in products if p["sale_category"] == "CONTROLLED")


def stable_rng(seed: int, *parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, (seed,) + parts)).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def iter_months(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        effective_start, effective_end = max(first, start), min(last, end)
        covered = (effective_end - effective_start).days + 1
        if covered > 0:
            yield first, covered, (last - first).days + 1
        month += 1
        if month == 13:
            month = 1
            year += 1


def phase(d: date) -> str:
    if d < date(2020, 3, 1):
        return "PRE_COVID"
    if d < date(2023, 6, 1):
        return "COVID_PUBLIC_HEALTH_EMERGENCY_PERIOD"
    return "POST_EMERGENCY"


def load_overrides(path: Path | None, valid_ids: set) -> Dict[Tuple[str, int], dict]:
    """Overrides OPCIONALES: factores ya normalizados respecto a ano base 2019.

    Columnas: product_id,year,multiplier,source_url,source_metric,coverage,notes
    No se aceptan factores sin URL y descripcion de la metrica.
    """
    results = {}
    if path is None:
        return results
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"product_id", "year", "multiplier", "source_url", "source_metric", "coverage"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV calibracion necesita columnas: {', '.join(sorted(required))}")
        for i, row in enumerate(reader, 2):
            pid = row["product_id"].strip()
            year = int(row["year"])
            factor = float(row["multiplier"])
            if pid not in valid_ids or year not in range(2019, 2027):
                raise ValueError(f"Producto/ano fuera de catalogo en fila {i}")
            if not (math.isfinite(factor) and factor > 0):
                raise ValueError(f"Multiplicador invalido en fila {i}")
            if not row["source_url"].strip().startswith("https://"):
                raise ValueError(f"Fuente HTTPS obligatoria en fila {i}")
            if not row["source_metric"].strip() or not row["coverage"].strip():
                raise ValueError(f"source_metric y coverage son obligatorios (fila {i})")
            key = (pid, year)
            if key in results:
                raise ValueError(f"Duplicada calibracion para {key}")
            results[key] = dict(multiplier=factor, status="USER_VERIFIED_PRODUCT_PROXY",
                                source_url=row["source_url"].strip(),
                                source_metric=row["source_metric"].strip(),
                                coverage=row["coverage"].strip(),
                                notes=row.get("notes", "").strip())
    return results


def built_in_calibration(product: dict, year: int) -> dict:
    pid = product["product_id"]
    if product["sale_category"] == "CONTROLLED":
        observed_year = min(year, 2024)
        ratio = CDC_OPIOID_PRESCRIPTIONS[observed_year] / CDC_OPIOID_PRESCRIPTIONS[2019]
        observed = year <= 2024
        return dict(multiplier=ratio,
                    status="DOCUMENTED_CATEGORY_PROXY" if observed else "CARRY_FORWARD_CATEGORY_PROXY_SYNTHETIC",
                    source_url=CDC_URL, source_metric="US annual retail opioid prescriptions, all opioids",
                    coverage="National retail pharmacies, all opioid products (not product-specific)",
                    notes="Annual index applied uniformly within year; 2025-2026 carry forward" if not observed
                          else "Annual category index assigned uniformly across months")
    if pid in ANTIBIOTIC_IDS and year in ANTIBIOTIC_MULTIPLIERS:
        return dict(multiplier=ANTIBIOTIC_MULTIPLIERS[year], status="DOCUMENTED_CATEGORY_PROXY",
                    source_url=ANTIBIOTICS_URL, source_metric="US outpatient antibiotic prescriptions annual change vs 2019",
                    coverage="All outpatient antibiotics; not specific to the named product or strength",
                    notes="Annual category index assigned uniformly across months")
    return dict(multiplier=1.0, status="SYNTHETIC_NEUTRAL_NO_PRODUCT_EVIDENCE", source_url="",
                source_metric="", coverage="No compatible public calibration loaded",
                notes="1.0 is an explicit neutral simulation assumption, not a measured trend")


def get_calibration(p: dict, year: int, overrides: dict) -> dict:
    return overrides.get((p["product_id"], year)) or built_in_calibration(p, year)


def rounded_count(x: float) -> int:
    """Redondeo tradicional no negativo, evitando redondeo a par de round()."""
    return max(0, int(math.floor(x + 0.5)))


def write_csv_header(path: Path, headers: list):
    f = path.open("w", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader()
    return f, w


def build_dataset(args: argparse.Namespace) -> dict:
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if start > end or start < date(2019, 1, 1) or end > date(2026, 10, 19):
        raise ValueError("Rango permitido: 2019-01-01 a 2026-10-19, con inicio <= final")
    if args.base_units_per_product_month < 1:
        raise ValueError("--base-units-per-product-month debe ser positivo")
    if args.base_records_per_month < 62:
        raise ValueError("--base-records-per-month debe ser al menos 62 para representar todos los productos")
    if not 0 <= args.monthly_variation_pct < 1:
        raise ValueError("--monthly-variation-pct debe ser >=0 y <1")
    if not 0 <= args.product_noise_sd <= 1:
        raise ValueError("--product-noise-sd debe estar entre 0 y 1")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    products = make_products()
    validate_products(products)
    overrides = load_overrides(Path(args.calibration_csv) if args.calibration_csv else None,
                               {p["product_id"] for p in products})

    catalog_file = out_dir / "products_catalog.csv"
    with catalog_file.open("w", newline="", encoding="utf-8") as fp:
        cw = csv.DictWriter(fp, fieldnames=PRODUCT_FIELDS)
        cw.writeheader()
        cw.writerows(products)

    tx_headers = ["transaction_id", "month", "product_id", "sale_category",
                  "sampled_units", "modeled_units_contribution", "pandemic_phase",
                  "calibration_level", "is_partial_month", "record_type"]
    monthly_headers = ["month", "year", "product_id", "sale_category", "therapeutic_group",
                       "reference_units_full_month", "category_annual_multiplier",
                       "synthetic_monthly_noise_multiplier", "covered_days", "days_in_month",
                       "coverage_factor", "modeled_units_month", "sample_records",
                       "sampled_units", "sampling_normalization_factor", "calibration_level",
                       "pandemic_phase", "is_partial_month"]
    calibration_headers = ["product_id", "year", "annual_multiplier", "calibration_level",
                           "source_url", "source_metric", "coverage", "notes"]
    qa_headers = ["month", "test", "status", "details"]

    tf, tw = write_csv_header(out_dir / "pharma_retail_sales.csv", tx_headers)
    mf, mw = write_csv_header(out_dir / "pharma_monthly_sales.csv", monthly_headers)
    cf, cw = write_csv_header(out_dir / "calibration_parameters.csv", calibration_headers)
    qf, qw = write_csv_header(out_dir / "data_quality_report.csv", qa_headers)
    cals = {}
    for p in products:
        for year in range(start.year, end.year + 1):
            cal = get_calibration(p, year, overrides)
            cals[(p["product_id"], year)] = cal
            cw.writerow(dict(product_id=p["product_id"], year=year,
                             annual_multiplier=f'{cal["multiplier"]:.12f}',
                             calibration_level=cal["status"], source_url=cal["source_url"],
                             source_metric=cal["source_metric"], coverage=cal["coverage"],
                             notes=cal["notes"]))
    cf.close()

    # Archivo vacio con esquema de parametros validados que el usuario puede alimentar.
    template = out_dir / "calibration_overrides_template.csv"
    with template.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["product_id", "year", "multiplier", "source_url",
                                "source_metric", "coverage", "notes"])

    total_records = 0
    total_units = 0
    total_months = 0
    by_status = Counter()
    months = []
    for month_date, covered_days, days_in_month in iter_months(start, end):
        month = month_date.strftime("%Y-%m")
        year = month_date.year
        effective_coverage = covered_days / days_in_month
        is_partial = int(covered_days < days_in_month)
        mrng = stable_rng(args.seed, month, "rowcount")
        # Fluctuaciones del TAMAÑO DE MUESTRA: no equivalen a cambios de mercado.
        monthly_fluctuation = mrng.uniform(-args.monthly_variation_pct,
                                           args.monthly_variation_pct)
        count_rows = max(62, rounded_count(args.base_records_per_month *
                                           (1 + monthly_fluctuation) * effective_coverage))

        targets = []
        for p in products:
            pid = p["product_id"]
            cal = cals[(pid, year)]
            nrng = stable_rng(args.seed, month, pid, "monthly_noise")
            # Fluctuacion sintetica centrada en factor 1; no es observacion historica.
            sd = args.product_noise_sd
            noise = math.exp(nrng.gauss(-sd * sd / 2.0, sd)) if sd else 1.0
            raw_target = args.base_units_per_product_month * cal["multiplier"] * noise * effective_coverage
            monthly_units = rounded_count(raw_target)
            targets.append(dict(product=p, cal=cal, noise=noise,
                                units=monthly_units, count=1))  # representacion de todos los productos
        # Estratificacion minima artificial: una fila por producto; resto muestreo ponderado.
        # Esta garantia evita ausencias de muestra confundidas con ausencia de ventas.
        weights = [max(x["units"], 0) for x in targets]
        if not any(weights):
            raise ValueError("Todas las unidades calculadas son cero; no se puede muestrear")
        draws = stable_rng(args.seed, month, "product_draws").choices(
            range(len(products)), weights=weights, k=count_rows - len(products))
        for j in draws:
            targets[j]["count"] += 1

        assigned_count = 0
        assigned_units = 0
        for item in targets:
            p, cal = item["product"], item["cal"]
            pid = p["product_id"]
            qty, n = item["units"], item["count"]
            # Normalizacion tecnica al volumen sintetico modelado, NO factor de expansion
            # de una encuesta probabilistica nacional.
            norm = qty / n
            mw.writerow(dict(month=month, year=year, product_id=pid,
                             sale_category=p["sale_category"],
                             therapeutic_group=p["therapeutic_group"],
                             reference_units_full_month=args.base_units_per_product_month,
                             category_annual_multiplier=f'{cal["multiplier"]:.12f}',
                             synthetic_monthly_noise_multiplier=f'{item["noise"]:.12f}',
                             covered_days=covered_days, days_in_month=days_in_month,
                             coverage_factor=f'{effective_coverage:.12f}',
                             modeled_units_month=qty, sample_records=n,
                             sampled_units=n,
                             sampling_normalization_factor=f'{norm:.12f}',
                             calibration_level=cal["status"], pandemic_phase=phase(month_date),
                             is_partial_month=is_partial))
            for k in range(n):
                tw.writerow(dict(transaction_id=f'SYN-{year}{month_date.month:02d}-{assigned_count + k + 1:07d}',
                                 month=month, product_id=pid,
                                 sale_category=p["sale_category"], sampled_units=1,
                                 modeled_units_contribution=f'{norm:.12f}',
                                 pandemic_phase=phase(month_date),
                                 calibration_level=cal["status"],
                                 is_partial_month=is_partial,
                                 record_type="SYNTHETIC_STRATIFIED_OBSERVATION"))
            assigned_count += n
            assigned_units += qty
            by_status[cal["status"]] += 1
        assert assigned_count == count_rows
        assert sum(x["count"] for x in targets) == count_rows
        assert sum(x["units"] for x in targets) == assigned_units
        qw.writerow(dict(month=month, test="COUNTS_AND_TOTALS", status="PASS",
                         details=f"sample_rows={assigned_count}; modeled_units={assigned_units}; products={len(targets)}"))
        total_records += assigned_count
        total_units += assigned_units
        total_months += 1
        months.append({"month": month, "sample_rows": assigned_count,
                       "modeled_units": assigned_units, "partial": bool(is_partial)})
    tf.close()
    mf.close()
    qf.close()

    manifest = {
        "dataset_name": "US synthetic retail pharmaceutical sample 2019-2026",
        "generator_version": "1.0.0",
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "number_of_months": total_months, "total_products": len(products),
        "product_groups": {"OTC": 30, "RX": 30, "CONTROLLED": 2},
        "base_units_per_product_month": args.base_units_per_product_month,
        "base_records_per_month": args.base_records_per_month,
        "monthly_variation_pct": args.monthly_variation_pct,
        "synthetic_monthly_product_noise_sd": args.product_noise_sd,
        "seed": args.seed, "override_rows": len(overrides),
        "total_sample_rows": total_records, "total_synthetic_modeled_units": total_units,
        "unit_definition": "Abstract commercial product unit; not tablets, doses, patients or dollars",
        "row_definition": "One synthetic, stratified product-month sample event, not a verified US retail sale",
        "modeled_units_contribution_definition": "Monthly modeled product units divided by that product-month's number of sample events",
        "sample_design": "Stratified synthetic convenience sample; >=1 observation per product and month",
        "national_representativeness": False,
        "market_estimate": False,
        "yearly_proxies_are_assigned_uniformly_to_months": True,
        "pandemic_dates_are_descriptive_not_causal": True,
        "prescription_dispensing_does_not_prove_ingestion": True,
        "october_2026_partial_period": True,
        "dates_are_month_only_no_fake_transaction_day": True,
        "regulatory_status": "Catalog preselection; individual product/NDC mapping not yet verified",
        "categories": {"OTC": "nonprescription", "RX": "prescription, nonopioid-controlled subgroup",
                       "CONTROLLED": "prescription opioid, DEA Schedule II"},
        "limitations": [
            "5850 is a synthetic model reference for each product, not an observed national market count",
            "Equal baseline product reference volumes are an artificial design choice, not actual relative market shares",
            "Category annual trends are category proxies, not evidence of product-specific sales or monthly effects",
            "Other products have neutral multiplier 1, with explicitly synthetic monthly noise",
            "2025-2026 opioid trend carried forward from 2024 solely as a documented assumption",
            "Individual product approval/marketing dates and NDCs have not been independently validated in this script",
            "Cannot infer COVID-19 causal effects from these synthetic data",
        ],
        "sources": {"opioid_category": CDC_URL, "antibiotic_category": ANTIBIOTICS_URL,
                    "cms_optional_background": CMS_URL, "fda_product_reconciliation": FDA_URL},
        "monthly_summary": months,
        "calibration_levels_count_product_months": dict(by_status),
        "outputs": ["products_catalog.csv", "pharma_retail_sales.csv", "pharma_monthly_sales.csv",
                    "calibration_parameters.csv", "data_quality_report.csv",
                    "calibration_overrides_template.csv", "generation_manifest.json"],
    }
    with (out_dir / "generation_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Genera ventas/dispensaciones farmaceuticas sinteticas (USA)")
    p.add_argument("--output-dir", default="pharma_usa_output")
    p.add_argument("--start-date", default=DEFAULT_START.isoformat())
    p.add_argument("--end-date", default=DEFAULT_END.isoformat())
    p.add_argument("--base-units-per-product-month", type=int, default=DEFAULT_BASE_UNITS,
                   help="5850 unidades modeladas como referencia por producto/mes completo")
    p.add_argument("--base-records-per-month", type=int, default=DEFAULT_BASE_RECORDS,
                   help="Numero base de filas de muestra mensual (independiente de unidades)")
    p.add_argument("--monthly-variation-pct", type=float, default=DEFAULT_MONTHLY_VARIATION,
                   help="Fluctuacion uniforme del NUMERO DE FILAS/mes, ej. 0.12")
    p.add_argument("--product-noise-sd", type=float, default=DEFAULT_PRODUCT_NOISE_SD,
                   help="Desviacion estandar del ruido lognormal SINTETICO por producto-mes")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--calibration-csv", default=None,
                   help="CSV OPCIONAL con evidencia verificada product_id,year,multiplier,source_url,source_metric,coverage,notes")
    return p


def main() -> None:
    p = make_parser()
    args = p.parse_args()
    try:
        manifest = build_dataset(args)
    except (ValueError, OSError) as e:
        p.error(str(e))
    print("Generacion completada")
    print("Directorio:", Path(args.output_dir).resolve())
    print("Productos:", manifest["total_products"])
    print("Meses:", manifest["number_of_months"])
    print("Filas de muestra:", format(manifest["total_sample_rows"], ","))
    print("Unidades sinteticas modeladas:", format(manifest["total_synthetic_modeled_units"], ","))
    print("IMPORTANTE: no son ventas nacionales observadas; ver generation_manifest.json")


if __name__ == "__main__":
    main()
