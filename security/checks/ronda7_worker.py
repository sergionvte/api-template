"""Arranca el worker del laboratorio con las tareas de `ronda7_lab_tasks` registradas.

    cd $LAB_DIR/app-copy && PYTHONPATH=$PWD:<repo>/security/checks \
      DATABASE_URL=sqlite+aiosqlite:///$LAB_DIR/lab.db ENVIRONMENT=production ... \
      python <repo>/security/checks/ronda7_worker.py
"""

import ronda7_lab_tasks  # noqa: F401  (registra lab7.*)
from app.tasks.worker import main

if __name__ == "__main__":
    main()
