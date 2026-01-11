You are a senior backend engineer.

You are given:
1) A clarified product spec
2) An architecture document

Your task:
Generate a complete, minimal but runnable backend codebase that implements the MVP.

## Hard requirements

- Use **Python + FastAPI**.
- Use **SQLModel** (or SQLAlchemy) with **SQLite by default**.
- Provide a clear way to switch to **Postgres** later via an environment variable `DB_URL`.
- Include authentication (**JWT** is fine).
- Implement **role-based access**:
  - employee
  - manager
  - admin
- Implement MVP endpoints (you can refine details based on the spec/architecture):
  - **Auth**
    - login (returns JWT)
  - **Employees**
    - clock in
    - clock out
    - view own hours (for a date range)
  - **Managers**
    - view team hours (for a date range)
  - **Admin**
    - manage users (create, list, deactivate)
    - assign employees to managers
  - **Reports**
    - export CSV of hours (for a date range, per employee / team)

- Include **requirements.txt**.
- Include a **README.md** with **exact commands to run** the backend.
- The project must be **runnable with a single command**:
  - `python run_backend.py`

## Canonical project layout (STRICT)

You MUST generate the backend as if it lives in a folder named `backend/` with the following layout:

```text
backend/
  app/
    __init__.py
    main.py          # defines: app = FastAPI(...)
    models.py
    schemas.py
    deps.py
    api/
      __init__.py
      routes.py      # all API routes included here
  requirements.txt
  run_backend.py
  check_backend.py
  README.md
  .env.example
