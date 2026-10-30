# Guía de desarrollo punto por punto — Pharmaceutical Retail Sales USA

## Propósito y regla de interpretación

Este proyecto académico reproduce un flujo de generación sintética, perfilado, control de calidad, ETL, análisis exploratorio y publicación. El conjunto no es una muestra probabilística ni una medición de ventas de Estados Unidos. `modeled_units_month` representa unidades comerciales abstractas modeladas; no son tabletas, dosis, pacientes ni dólares.

El diseño confirmado es: 62 productos (30 OTC, 30 RX y 2 CONTROLLED Schedule II), 94 meses (enero de 2019–19 de octubre de 2026) y referencia artificial de 5,850 unidades por producto-mes completo de 2019.

---

## Fase 1 — Preparación del repositorio

### 1.1 Descomprimir y abrir

1. Descomprime `proyecto_pharma_retail_ml_python.zip`.
2. Abre la carpeta `pharma_retail_ml_project` en Visual Studio Code.
3. Abre una terminal integrada y confirma que estás en la raíz del proyecto: allí deben estar `README.md`, `requirements.txt`, `scripts/`, `tests/`, `data/` y `reports/`.

### 1.2 Verificar Python y Git

Windows PowerShell:

```powershell
python --version
git --version
```

Se requiere Python 3.10 o superior y Git. Si `python` no funciona en Windows, prueba `py --version` y utiliza `py` en los comandos siguientes.

### 1.3 Crear y activar entorno virtual

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, utiliza la política aprobada por tu organización o activa el entorno desde CMD:

```bat
.venv\Scripts\activate.bat
```

### 1.4 Instalar dependencias

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Las dependencias del proyecto base son pandas y matplotlib. No instales bibliotecas de ML hasta definir y aprobar la extensión de la fase 7.

### 1.5 Generar los datos

```powershell
python scripts/generador_ventas_farmaceuticas_usa.py --output-dir data/raw
```

Se esperan seis CSV y un JSON:
- `products_catalog.csv`
- `pharma_retail_sales.csv`
- `pharma_monthly_sales.csv`
- `calibration_parameters.csv`
- `data_quality_report.csv`
- `calibration_overrides_template.csv`
- `generation_manifest.json`

**Importante sobre el tamaño de muestra:** el valor predeterminado de `--base-records-per-month` es 6,200 y en la ejecución reproducida produjo 575,028 eventos. El ejemplo de 18,552 eventos corresponde a ejecutar con `--base-records-per-month 200`. Ambos escenarios mantienen las mismas unidades modeladas cuando se conserva la semilla y los demás parámetros:

```powershell
python scripts/generador_ventas_farmaceuticas_usa.py --output-dir data/raw_200 --base-records-per-month 200
```

La aceptación de fase 1 consiste en verificar los seis CSV, el manifiesto y que este declare 62 productos y 94 meses. La plantilla de overrides debe estar vacía hasta que se agreguen calibraciones verificadas.

---

## Fase 2 — Inventario y calidad de datos

### 2.1 Perfilado de las seis tablas

Se incorporó `scripts/perfil_calidad.py`. Ejecuta:

```powershell
python scripts/perfil_calidad.py --input-dir data/raw --output-dir reports/quality
```

El script muestra `head()`, `info()`, `describe()` y nulos de cada CSV, y produce `reports/quality/perfil_archivos.csv`.

Qué revisar:
- `rows`: cantidad de registros.
- `columns`: cantidad de columnas.
- `null_cells`: cantidad de celdas nulas.
- `duplicate_full_rows`: filas totalmente duplicadas.
- Nulos: investigar su significado; no rellenarlos automáticamente.
- La plantilla `calibration_overrides_template.csv` debe tener cero filas de datos: es una plantilla, no una fuente de observaciones.

### 2.2 Reglas de unicidad

| Archivo | Clave esperada | Motivo |
|---|---|---|
| `products_catalog.csv` | `product_id` | Un registro por producto |
| `pharma_monthly_sales.csv` | `month`, `product_id` | Un registro por producto y mes |
| `calibration_parameters.csv` | `product_id`, `year` | Un parámetro anual por producto |
| `pharma_retail_sales.csv` | `transaction_id` | Identificador único del evento |

El script falla con excepción si encuentra duplicados en estas claves.

### 2.3 Conciliaciones

- Agrupar eventos por `month` y `product_id`; el conteo debe coincidir con `sample_records`.
- Sumar `modeled_units_contribution` por producto-mes; debe coincidir con `modeled_units_month`, con tolerancia numérica.
- El catálogo debe contener 62 productos y las categorías deben ser 30 OTC, 30 RX y 2 CONTROLLED.

La fase 3 vuelve a aplicar estas reglas durante la unificación. No se debe continuar si aparece una discrepancia.

---

## Fase 3 — ETL y unificación

### 3.1 Ejecutar

```powershell
python scripts/unificar_datasets.py --input-dir data/raw --output-dir data/processed
```

### 3.2 Qué hace el ETL

1. Lee las seis tablas y el manifiesto JSON.
2. Convierte `month` a fecha.
3. Valida las claves antes de unir.
4. Agrega eventos a producto-mes para evitar que una unión uno-a-muchos replique medidas mensuales.
5. Une el catálogo por `product_id` con validación muchos-a-uno.
6. Une calibraciones por `product_id` y `year`, nunca sólo por año.
7. Resume el QA por mes y comprueba que todas las pruebas estén aprobadas.
8. Concilia el manifiesto con las tablas.
9. Conserva el JSON íntegro como `metadata_manifest.json`.

### 3.3 Archivos de salida

| Archivo | Granularidad | Uso |
|---|---|---|
| `dataset_unificado_mensual.csv` | Producto-mes | Dataset principal para EDA |
| `dataset_transaccional_enriquecido.csv` | Evento sintético | Trazabilidad del muestreo |
| `auditoria_manifest_mensual.csv` | Mes | Conciliación con JSON |
| `resumen_validaciones.json` | Ejecución | Resultado resumido de QA |
| `metadata_manifest.json` | Manifiesto | Parámetros, fuentes y limitaciones originales |

**Por qué no sumar el dataset transaccional enriquecido:** las unidades mensuales ya existen en la tabla mensual. Si se copian a cada evento y después se suman, se duplican o multiplican. Las contribuciones de evento son una distribución matemática del total modelado, no ventas adicionales.

### 3.4 Aceptación

Debe obtenerse:
- 62 productos.
- 94 meses.
- 5,828 filas producto-mes (62 × 94).
- Todas las validaciones QA aprobadas.
- Conciliación con el manifiesto.

---

## Fase 4 — Análisis exploratorio (EDA)

### 4.1 Crear los gráficos originales

```powershell
python scripts/visualizar_resultados.py --input data/processed/dataset_unificado_mensual.csv --output-dir reports/figures
```

Produce:
1. Tendencia temporal por categoría.
2. Quince cambios sintéticos más pronunciados por producto entre 2019 y 2020.
3. Distribución de niveles de calibración.
4. Indicadores anuales por categoría y CSV de variaciones 2020 vs. 2019.

### 4.2 Analizar las tres fases solicitadas

Se incorporó `scripts/analisis_fases.py`:

```powershell
python scripts/analisis_fases.py --input data/processed/dataset_unificado_mensual.csv --output-dir reports/figures
```

Períodos:
- Línea base: enero–diciembre de 2019 (12 meses).
- Fase descriptiva COVID-19: marzo de 2020–mayo de 2023 (39 meses).
- Fase posterior descriptiva: junio de 2023–octubre de 2026 (41 meses de calendario; octubre de 2026 es parcial).

Enero y febrero de 2020 se excluyen de esas tres comparaciones porque no pertenecen a los intervalos definidos en el mandato.

Para comparar meses completos y parciales, el script utiliza:

`full_month_equivalent = modeled_units_month / coverage_factor`

Este indicador permite comparar escalas mensuales dentro de la simulación. Para octubre de 2026 es una normalización aritmética de los 19 días cubiertos, no una observación de los 31 días ni una predicción. Nunca compares su total crudo con el de un mes completo.

### 4.3 Salidas analíticas adicionales

- `comparacion_fases_categoria.csv`: media por producto-mes y categoría en cada fase.
- `variacion_por_producto_fases.csv`: cambio por medicamento frente a 2019.
- `variacion_anual_por_producto_vs_2019.csv`: variación anual por medicamento, usando años completos 2019–2025.
- `descomposicion_calibracion_ruido.csv`: resumen de multiplicador anual, ruido sintético y nivel de calibración.

### 4.4 Cómo contestar las preguntas del mandato

**¿Qué productos presentan mayor cambio porcentual?**  
Ordena `variacion_anual_por_producto_vs_2019.csv` por valor absoluto de `change_pct_vs_2019`, pero explica que el ranking es de variaciones simuladas, no de ventas. Para el corte 2020 vs. 2019, los cinco antibióticos calibrados muestran las mayores reducciones de la ejecución reproducida.

**¿Qué grupos tienen trayectorias distintas?**  
Compara `comparacion_fases_categoria.csv`. CONTROLLED desciende más porque utiliza un proxy agregado de opioides. RX contiene cinco antibióticos calibrados. OTC conserva un multiplicador anual neutro y presenta principalmente ruido sintético.

**¿Cuánto procede de calibración y cuánto del ruido?**  
Examina `category_annual_multiplier`, `synthetic_monthly_noise_multiplier` y `calibration_level`. No presentes una descomposición estadística causal: son componentes explícitos del mecanismo del generador. La calibración documentada es de categoría, no específica por cada medicamento.

**¿Qué observaciones tienen fuente documental?**  
Las etiquetas `DOCUMENTED_CATEGORY_PROXY` y `CARRY_FORWARD_CATEGORY_PROXY_SYNTHETIC` identifican proxies y arrastres. Revisa `evidence_source_url`, `evidence_source_metric`, `evidence_coverage` y `evidence_notes`. La existencia de una URL no convierte el proxy en una serie nacional por producto.

**¿Cómo afecta el tamaño de muestra?**  
Compara dos ejecuciones con igual semilla, una predeterminada y otra con 200 registros base por mes. Cambia el número de eventos, pero el volumen mensual modelado permanece idéntico. El tamaño de muestra afecta la cantidad de registros y la estabilidad de resúmenes de eventos, no la demanda modelada definida por el generador.

**¿Por qué no es medición nacional ni causalidad?**  
No existe diseño probabilístico ni probabilidad de inclusión empírica; el volumen base es artificial; los proxies son agregados; el ruido se genera por código y no existe grupo contrafactual observado. Por tanto, no se puede inferir cuota de mercado, consumo real ni efecto causal de COVID-19.

---

## Fase 5 — Comunicación de resultados

El informe actualizado está en `reports/CONCLUSIONES.md`. Incluye:
1. Pregunta de investigación.
2. Alcance y limitaciones.
3. Diccionario conceptual de unidades y granularidad.
4. Comparación de las tres fases.
5. Variaciones por medicamento.
6. Distribución de niveles de calibración.
7. Conciliaciones y pruebas.
8. Sensibilidad al tamaño de muestra.
9. Limitaciones y próximos pasos.

Antes de entregar:
- Comprueba que los gráficos y CSV corresponden a la misma ejecución y semilla.
- Incluye período exacto, unidad, granularidad y denominador en cada gráfico.
- Separa explícitamente observaciones de la simulación de hechos respaldados por fuentes externas.
- No uses expresiones como “las ventas de Estados Unidos aumentaron/disminuyeron” para describir estos resultados.

---

## Fase 6 — Publicación y documentación GitHub

### 6.1 Revisar `.gitignore`

Deben excluirse `.venv/`, `__pycache__/`, `.env`, `data/raw/` y `data/processed/`. No publiques secretos, tokens ni archivos sensibles. Publica código, documentación, pruebas, conclusiones y gráficos ligeros.

### 6.2 Crear repositorio remoto

1. En GitHub crea un repositorio vacío llamado `pharma-retail-usa-ml`.
2. No marques README, `.gitignore` ni License si ya existen localmente.
3. Desde la raíz del proyecto:

```bash


git remote remove origin
git remote add origin https://github.com/heudyfeliz-star/pharma-retail-usa-ml.git
git remote -v
git push -u origin main

### git init
### git add .
### git status
### git commit -m "Initial commit: synthetic pharma ETL and EDA"
### git branch -M main
### git remote add origin https://github.com/heudyfeliz-star/pharma-retail-usa-ml.git
### git push -u origin main
```

### 6.3 Actualizar cambios

```bash
git status
git add .
git commit -m "Add phase analysis and data quality profile"
git push
```

### 6.4 Prueba de reproducibilidad

Una persona que clone el repositorio debe poder instalar dependencias, generar datos, ejecutar el ETL, crear gráficos y ejecutar pruebas. Los datos brutos/procesados se regeneran localmente; no es necesario versionar los CSV grandes.

---

## Fase 7 — Extensión opcional de Machine Learning

Esta fase se ejecuta después de aprobar las fases 1–6. No se debe entrenar un modelo sólo para añadir ML al título.

### 7.1 Elegir una pregunta concreta

Opciones coherentes con este dataset:
- Pronóstico de `modeled_units_month` para un producto o categoría.
- Agrupación de trayectorias de productos.
- Detección de cambios en la serie sintética.

### 7.2 Evitar fuga temporal

Para cada fecha de predicción, todas las variables deben estar disponibles antes de esa fecha. Ejemplos de features:
- `lag_1`, `lag_2`, `lag_3`, `lag_6`, `lag_12`.
- Medias móviles calculadas con `shift(1)` antes de aplicar rolling.
- Mes, trimestre y variables de calendario conocidas.
- Categoría y variables de calibración, sólo si serían conocidas al momento de pronosticar.

No usar datos futuros, valores del objetivo contemporáneo ni agregados calculados sobre todo el período.

### 7.3 Validación

- Ordenar cronológicamente.
- Entrenar con períodos iniciales y validar en períodos posteriores.
- Aplicar backtesting de origen rodante si hay suficientes meses.
- Prohibido `train_test_split(shuffle=True)` para pronóstico.
- Comparar contra baseline ingenuo (último valor) y estacional (`lag_12`).

### 7.4 Métricas y comunicación

Reportar MAE, RMSE y, cuando el denominador lo permita, MAPE o sMAPE. Presentar resultados como desempeño sobre datos sintéticos. Un buen score no demuestra que el modelo generalice al mercado real estadounidense.

---

## Checklist final de aceptación

- [ ] Entorno virtual y dependencias instalados.
- [ ] Seis CSV y `generation_manifest.json` generados.
- [ ] Perfilado de las seis tablas guardado.
- [ ] Claves únicas y conciliaciones aprobadas.
- [ ] ETL produce 5,828 filas producto-mes y 94 meses.
- [ ] JSON conciliado con las tablas.
- [ ] Gráficos originales y análisis por fases generados.
- [ ] Variaciones anuales por producto calculadas contra 2019.
- [ ] Informe de conclusiones actualizado y verificable.
- [ ] Cinco pruebas automatizadas aprobadas.
- [ ] GitHub publicado sin datos grandes ni secretos.
- [ ] Cualquier extensión ML usa partición cronológica y reconoce la naturaleza sintética.
