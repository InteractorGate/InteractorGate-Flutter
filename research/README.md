# Herramientas offline de investigación

`evaluate_text.py` entrena y evalúa una copia experimental de la RNN y un bigrama
usando el checkout del backend. Requiere PyTorch en el entorno del investigador;
no se empaqueta PyTorch en la app ni se modifica el predictor desplegado.

```powershell
python research/evaluate_text.py --backend-root ../ig-django-backend --output research/runs/text_pilot
python research/manual_example.py research/runs/manual_example
```

`manual_example.py` crea datos ficticios y un oráculo aritmético para probar el
análisis de `sidecar/analyze_study.py`. No es una sesión con participantes ni
representa el esquema aleatorio real de E2. `runs/` queda excluido de Git.

Métodos, comandos instalables, limitaciones y resultados del piloto:
[ANALISIS_E1_E2.md](../docs/ANALISIS_E1_E2.md).
