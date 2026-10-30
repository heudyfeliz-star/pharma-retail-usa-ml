# Mandato de proyecto — Pharmaceutical Retail Sales (USA, 2019–2026)

## Misión

Construir un proyecto de ingeniería y analítica reproducible en Python que describa las variaciones de **demanda modelada** y la distribución de 62 formulaciones farmacéuticas, antes, durante y después de la emergencia federal COVID-19. El proyecto es académico: su muestra sintética no mide ventas nacionales reales y no permite atribución causal.

## Alcance confirmado

- Mercado de referencia: retail nacional de Estados Unidos; **muestra sintética no probabilística**.
- 62 productos: 30 OTC, 30 RX, 2 CONTROLLED Schedule II.
- 5,850 unidades abstractas modeladas/mes/producto como punto de referencia, sujetas a variaciones.
- Enero 2019–19 octubre 2026; octubre es un mes **parcial**.
- Datos transaccionales simulados; una tabla agregada por producto y mes.
- Insumos generados por `generador_ventas_farmaceuticas_usa.py`; análisis con pandas/matplotlib.
- No introducir precios, pacientes, geografía estatal ni causa clínica no documentada.

## Fase 1 — Preparación del repositorio

**Entregable:** estructura de carpetas, dependencias y entorno.

1. Descargar el proyecto, descomprimirlo y abrir la carpeta en VS Code o terminal.
2. Instalar Python 3.10+ y Git.
3. Crear entorno virtual y activarlo (ver README para Windows/macOS/Linux).
4. Instalar `pip install -r requirements.txt`.
5. Ejecutar `python scripts/generador_ventas_farmaceuticas_usa.py --output-dir data/raw`.

**Aceptación:** existen seis archivos de datos + una plantilla de overrides en `data/raw`. Verificar también `generation_manifest.json`.

## Fase 2 — Inventario y calidad de datos

**Entregable:** pruebas documentadas de unicidad e integridad.

1. Inspeccionar `head()`, `info()`, `describe()` y cantidades de nulos en cada tabla con pandas.
2. Confirmar la clave `product_id` única en catálogo.
3. Confirmar `(month, product_id)` único en ventas mensuales.
4. Confirmar `(product_id, year)` único en calibraciones.
5. Confirmar `transaction_id` único en eventos.
6. Contrastar `sample_records` mensual con el número de eventos.
7. Verificar que la suma de `modeled_units_contribution` por producto-mes concuerda con `modeled_units_month`.

**Aceptación:** errores de duplicidad o discrepancias provocan fallo explícito, no una unión silenciosa.

## Fase 3 — ETL y unificación

**Entregable:** `dataset_unificado_mensual.csv`, `dataset_transaccional_enriquecido.csv` y auditoría.

1. Ejecutar `python scripts/unificar_datasets.py --input-dir data/raw --output-dir data/processed`.
2. Leer con pandas y convertir `month` a tipo datetime.
3. Agregar eventos a producto-mes; usar `merge(validate=...)` para evitar multiplicaciones.
4. Unir catálogo por producto y calibraciones por producto-año.
5. Resumir los resultados QA por mes; verificarlos antes de unir.
6. Leer JSON: validar totales y anexar metadatos escalares.
7. Conservar JSON completo en `metadata_manifest.json` y mantener la tabla de eventos por separado.

**Aceptación:** 5,828 filas de producto-mes; 94 meses; 62 productos; conciliación numérica con JSON. Ejecutar `python -m unittest discover -s tests -v` y exigir todas las pruebas aprobadas.

## Fase 4 — Análisis exploratorio

**Entregable:** tabla de indicadores, gráficos y observaciones descriptivas.

1. Generar visualizaciones con `python scripts/visualizar_resultados.py`.
2. Describir la serie temporal por categoría con promedio por producto-mes.
3. Calcular variación porcentual anual **por medicamento** respecto a 2019.
4. Identificar cuáles cambios proceden de proxies de categoría y cuáles de ruido sintético.
5. Comparar 2019, marzo 2020–mayo 2023 y junio 2023–octubre 2026, indicando la distinta duración de cada fase.
6. No comparar el total de 2026 con un año completo. Para comparaciones usar meses completos comunes o mensualidades equivalentes, explicitando el método.
7. Confirmar que cambiar `--base-records-per-month` modifica eventos muestreados, no la demanda modelada que se pretende estudiar.

**Preguntas de análisis:**

- ¿Qué productos presentan mayor cambio porcentual de su demanda modelada respecto a 2019?
- ¿Qué grupos exhiben distinta trayectoria durante la emergencia COVID-19?
- ¿Cuánto de la evolución resulta de la calibración anual por categoría y cuánto del ruido sintético?
- ¿Qué observaciones tienen una fuente documental? ¿Cuáles son hipótesis de simulación?
- ¿Cómo afecta el tamaño de muestra a la estabilidad de `sample_records` sin modificar el volumen modelado?
- ¿Por qué los resultados no son una medición nacional ni evidencia causal?

**Criterio metodológico:** en este generador, todos los productos parten de 5,850 unidades abstractas en un mes completo de 2019. Por eso no deben afirmarse rankings reales de los medicamentos más vendidos ni tasas de consumo de pacientes.

## Fase 5 — Comunicación de resultados

**Entregable:** `reports/CONCLUSIONES.md` redactado por el estudiante (propuesta de estructura al final).

El informe debe contener:

1. Objetivo e hipótesis descriptivas.
2. Fuentes y limitaciones de representatividad.
3. Diccionario de campos y explicación de 5,850 unidades por producto.
4. 3 gráficos con pies descriptivos y períodos exactos.
5. Al menos 5 observaciones numéricas verificables en las tablas generadas.
6. Distinción de *observación de la simulación* vs *hecho respaldado por fuentes externas*.
7. Limitaciones y mejoras futuras: más calibraciones por producto, precios verificados si fueran necesarios, series OTC validadas.

## Fase 6 — Publicación y documentación GitHub

**Entregable:** repositorio reproducible con código fuente, `README.md`, `requirements.txt`, `docs/` y `.gitignore`.

1. Crear una cuenta en https://github.com (si aún no existe).
2. Crear un repositorio vacío **sin** activar README, `.gitignore` ni License (ya existen archivos locales).
3. Desde la carpeta del proyecto:

   ```bash
   git init
   git add .
   git commit -m "Initial commit: synthetic pharma ETL and EDA"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/pharma-retail-usa-ml.git
   git push -u origin main
   ```

4. Autenticarse con el mecanismo que GitHub ofrezca (por ejemplo, Git Credential Manager o clave SSH). **No usar contraseña normal como autenticación Git por HTTPS ni colocar tokens en el código**.
5. Abrir el repositorio y verificar que aparecen `README.md`, `scripts/`, `requirements.txt`, `docs/` y `.gitignore`.
6. Para actualizar: `git status`, `git add .`, `git commit -m "Add analysis results"`, `git push`.
7. Nunca incluir archivos `.env`, contraseñas, secretos o datos sensibles; mantener `data/raw/` y `data/processed/` fuera de Git para evitar archivos grandes reproducibles; publicar gráficos PNG ligeros y conclusiones como evidencia de trabajo.

**Aceptación:** alguien puede clonar el repositorio, instalar dependencias y volver a generar/analisar los datos siguiendo README; los resultados reportados identifican explícitamente la naturaleza sintética.

## Fase 7 — Extensión para ML (opcional, posterior)

1. Formular una tarea específica (detección de cambio estructural, clustering de trayectorias o pronóstico sintético).
2. Crear features temporales usando solo información disponible hasta cada fecha de entrenamiento.
3. Utilizar particiones cronológicas; prohibido hacer `train_test_split(shuffle=True)` sobre series temporales para pronóstico.
4. Presentar resultados como desempeño en datos sintéticos; no prometer generalización nacional.

## Rúbrica sugerida

| Criterio | Peso |
| --- | ---: |
| Reproducibilidad | 20% |
| Integridad de claves y ausencia de doble conteo | 25% |
| Exploración y gráficos adecuados | 20% |
| Interpretación responsable del dato sintético | 20% |
| Documentación y GitHub | 15% |

## Plantilla para `reports/CONCLUSIONES.md`

```markdown
# Conclusiones del estudio

## Pregunta de investigación
[Definir]

## Hallazgo 1: evolución por categoría
[Figura, cifras, período y descripción de calibración]

## Hallazgo 2: variaciones por medicamento
[Producto, magnitud, período; distinguir tendencias documentadas de ruido sintético]

## Hallazgo 3: cobertura/calidad de la evidencia
[Distribución de calibration_level; implicaciones]

## Limitaciones
[Muestra sintética no representativa; unidades abstractas; no causalidad]

## Próximos pasos
[Nuevas series históricas, revisión FDA/NDC, contrastación externa]
```
