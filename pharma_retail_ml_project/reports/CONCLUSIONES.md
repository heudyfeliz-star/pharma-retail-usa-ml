# Conclusiones del estudio — Pharmaceutical Retail Sales USA (2019–2026)

> **Naturaleza del estudio:** ejercicio académico de ingeniería de datos y analítica sobre una muestra sintética no probabilística. Los valores no son ventas nacionales observadas, pacientes, dosis, tabletas ni dólares. No permiten atribución causal a COVID-19.

## 1. Pregunta de investigación

¿Cómo varía la demanda modelada de 62 formulaciones farmacéuticas a lo largo del período enero de 2019–19 de octubre de 2026, y cómo se distribuyen esas variaciones entre categorías OTC, RX y CONTROLLED?

La investigación es descriptiva. La comparación temporal permite estudiar el comportamiento del generador, no estimar el mercado farmacéutico estadounidense.

## 2. Datos y alcance

- 62 productos: 30 OTC, 30 RX y 2 CONTROLLED Schedule II.
- 94 meses: enero de 2019 a octubre de 2026.
- Referencia artificial: 5,850 unidades abstractas por producto y mes completo de 2019.
- Granularidad analítica: una fila por `product_id` y `month`.
- Octubre de 2026 está cubierto hasta el día 19 (19/31 = 0.612903).
- Ejecución reproducida con semilla 42 y parámetros predeterminados del generador.

La ejecución predeterminada generó **575,028 eventos de muestra** y **33,639,168 unidades abstractas modeladas**. Los eventos son observaciones sintéticas; las unidades modeladas son un objetivo independiente y no deben confundirse ni sumarse entre sí.

## 3. Hallazgos descriptivos por fase

Para comparar meses parciales y completos se utilizó `modeled_units_month / coverage_factor`, denominado equivalente de mes completo. En octubre de 2026 esta operación normaliza aritméticamente los 19 días cubiertos; no convierte el mes parcial en una observación real de 31 días.

| Fase | Período | Meses | CONTROLLED: media | RX: media | OTC: media |
|---|---|---:|---:|---:|---:|
| Línea base | Ene–dic 2019 | 12 | 5,873.21 | 5,859.28 | 5,849.24 |
| Fase descriptiva COVID-19 | Mar 2020–may 2023 | 39 | 5,225.62 | 5,745.12 | 5,842.78 |
| Fase posterior descriptiva | Jun 2023–oct 2026 | 41 | 4,683.79 | 5,843.92 | 5,837.57 |

Variación porcentual frente a la línea base de 2019:

| Categoría | Mar 2020–may 2023 | Jun 2023–oct 2026 |
|---|---:|---:|
| CONTROLLED | -11.03% | -20.25% |
| RX | -1.95% | -0.26% |
| OTC | -0.11% | -0.20% |

**Interpretación:** la trayectoria CONTROLLED incorpora por diseño el proxy anual agregado de dispensación de opioides; cinco productos RX incorporan un proxy de antibióticos ambulatorios en los años calibrados. El resto mantiene un multiplicador neutro y ruido sintético. Los porcentajes son resultados del simulador, no cambios medidos en ventas nacionales ni efectos de la emergencia.

Enero y febrero de 2020 se excluyeron de estas tres fases para respetar los límites establecidos: línea base 2019, marzo 2020–mayo 2023 y junio 2023 en adelante.

## 4. Variación por medicamento

En la comparación de años completos 2019 y 2020, los cinco antibióticos calibrados presentan las mayores reducciones sintéticas:

| Producto | Variación 2020 vs. 2019 |
|---|---:|
| Doxycycline generic | -24.22% |
| Amoxicillin generic | -21.84% |
| Macrobid | -21.81% |
| Zithromax | -21.70% |
| Cefdinir generic | -17.56% |

La tabla `variacion_anual_por_producto_vs_2019.csv` contiene las variaciones de cada medicamento para todos los años completos disponibles (2019–2025). La tabla `variacion_por_producto_fases.csv` contiene la comparación de cada producto por fase.

No debe construirse un ranking de medicamentos más vendidos: todos parten de la misma referencia artificial de 5,850 unidades por mes completo de 2019. Una diferencia entre medicamentos no es evidencia de participación de mercado.

## 5. Origen de las variaciones: calibración y ruido

La ejecución contiene 5,828 combinaciones producto-mes distribuidas así:

- 5,400 `SYNTHETIC_NEUTRAL_NO_PRODUCT_EVIDENCE`.
- 384 `DOCUMENTED_CATEGORY_PROXY`.
- 44 `CARRY_FORWARD_CATEGORY_PROXY_SYNTHETIC`.

El generador combina, de forma simplificada:

`unidades modeladas ≈ referencia × multiplicador anual de categoría × ruido mensual sintético × cobertura`.

El multiplicador de categoría aporta las tendencias impuestas por los proxies disponibles. El ruido mensual es una variación aleatoria sintética por producto y mes. Los valores neutrales de 1.0 no significan que el medicamento haya mantenido ventas reales estables: son un supuesto de simulación.

Los proxies son de categoría y no una medición específica por producto. Para 2025–2026, el proxy de opioides se arrastra como supuesto sintético, no como dato observado de esos años.

## 6. Calidad e integridad

- 62 productos × 94 meses = 5,828 filas producto-mes.
- Claves únicas verificadas: `product_id`; `(month, product_id)`; `(product_id, year)`; `transaction_id`.
- La suma de `modeled_units_contribution` por producto-mes concilia con `modeled_units_month`.
- `sample_records` coincide con el número de eventos por producto-mes.
- El manifiesto JSON concilia con los totales calculados.
- Las cinco pruebas automatizadas de `tests/test_integridad.py` fueron aprobadas.
- Los nulos en campos de fuente/calibración o atributos regulatorios no aplicables deben interpretarse según el diccionario y la categoría; no se deben rellenar automáticamente con datos inventados.

## 7. Sensibilidad al tamaño de muestra

Con semilla 42, cambiar `--base-records-per-month` de 6,200 (predeterminado) a 200 produjo:

| Parámetro | Predeterminado | Prueba reducida |
|---|---:|---:|
| Eventos de muestra | 575,028 | 18,552 |
| Unidades modeladas | 33,639,168 | 33,639,168 |

La serie de `modeled_units_month` fue idéntica en ambas ejecuciones. El parámetro modifica el número de eventos sintéticos y la estabilidad descriptiva de la muestra, no el volumen modelado que se pretende estudiar.

## 8. Limitaciones

1. Muestra sintética, no probabilística y sin representatividad nacional.
2. Unidad abstracta, sin conversión válida a dosis, envases, pacientes o dinero.
3. Referencia base igual para todos los productos: no permite comparar ventas relativas.
4. Proxies agregados de categoría no prueban una tendencia individual por medicamento.
5. La asignación anual uniforme a todos los meses no modela estacionalidad documentada.
6. El ruido mensual es generado por el programa y no representa shocks históricos observados.
7. Las fechas de comercialización, correspondencia NDC y estado regulatorio individual no han sido validados definitivamente.
8. Octubre de 2026 es parcial y no se debe comparar su total crudo con un mes completo.
9. Las diferencias temporales no demuestran causalidad ni impacto de COVID-19.

## 9. Próximos pasos

- Contrastar cada producto con NDC y fechas de comercialización verificadas.
- Incorporar calibraciones por producto y año sólo cuando exista fuente trazable y métrica compatible.
- Obtener series observadas y comparables antes de formular afirmaciones sobre el mercado real.
- Para ML opcional, definir una tarea sintética explícita, crear variables con información disponible hasta cada fecha, usar validación cronológica y reportar el desempeño sólo sobre datos sintéticos.

## 10. Evidencia generada

- `figures/01_tendencias_por_categoria.png`
- `figures/02_cambios_por_producto_2020.png`
- `figures/03_niveles_calibracion.png`
- `figures/indicadores_por_anio_categoria.csv`
- `figures/variaciones_2020_vs_2019.csv`
- `figures/comparacion_fases_categoria.csv`
- `figures/variacion_por_producto_fases.csv`
- `figures/variacion_anual_por_producto_vs_2019.csv`
- `figures/descomposicion_calibracion_ruido.csv`
- `quality/perfil_archivos.csv`

**Conclusión general:** el repositorio permite reproducir un flujo de generación, validación, unificación y exploración temporal con controles de integridad explícitos. Su valor académico está en la ingeniería reproducible y en interpretar responsablemente una simulación, no en medir el mercado farmacéutico de Estados Unidos.
