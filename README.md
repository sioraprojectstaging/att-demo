# Siora One

Attendance, payroll and workforce management with face-recognition check-in.
One Django REST API serves both the **web app** (React) and the **mobile app**.

| Part | Folder | Hosted on | Vercel project |
|------|--------|-----------|----------------|
| Web app (admin dashboard) | `client/` | Vercel (static) | `siora-one` |
| API + Django admin | `backend/` | Vercel (Python function) | `siora-one-api` |
| Database | — | Neon Postgres (Vercel Marketplace) | connected to `siora-one-api` |
| Uploaded files (profile photos) | — | Vercel Blob | connected to `siora-one-api` |

## Tech stack

- **Backend:** Django 5.2, Django REST Framework, SimpleJWT, drf-spectacular (OpenAPI docs)
- **Face recognition:** InsightFace `buffalo_l` (detection + recognition models), ONNX Runtime, OpenCV
- **Frontend:** React 19, Vite, Tailwind CSS, Axios
- **Database:** PostgreSQL (Neon in production)

---

## Local development

**Prerequisites:** Python 3.12, Node.js 22, PostgreSQL.

### Backend

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then set DB_USER / DB_NAME for your local Postgres
createdb attendance_db_local
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

- API: http://127.0.0.1:8000/api/
- API docs: http://127.0.0.1:8000/api/docs/
- Django admin: http://127.0.0.1:8000/admin/

The first face check-in downloads the InsightFace model pack (~275 MB) into `~/.insightface`.

### Web app

```bash
cd client
npm install
npm run dev                 # http://localhost:5173
```

The web app calls `http://127.0.0.1:8000/api/` unless `VITE_API_URL` is set (see `client/.env.example`).

---

## Deploying to Vercel

Two Vercel projects deploy from this one repo.

### 1. API: `siora-one-api`

- **Root Directory:** `backend`. Vercel detects Django from `manage.py` and serves `core.wsgi.application`.
- **Storage:** connect a **Neon** database (sets `DATABASE_URL`) and a **public Blob** store (sets `BLOB_READ_WRITE_TOKEN`).
- **Environment variables:**

  | Name | Value |
  |------|-------|
  | `SECRET_KEY` | long random string (required; also needed at build time) |
  | `FRONTEND_URL` | `https://siora-one.vercel.app` |
  | `FACE_MODEL_BASE_URL` | public folder URL holding `det_10g.onnx` and `w600k_r50.onnx` (see below) |
  | `VERCEL_SUPPORT_LARGE_FUNCTIONS` | `1` (the face-recognition libraries exceed the 500 MB standard limit) |
  | `CORS_ALLOWED_ORIGIN_REGEXES` | optional, e.g. `^https://siora-one-[a-z0-9-]+\.vercel\.app$` for preview URLs |

- **Function memory:** set 4 GB under Settings → Functions (requires the Pro plan). Loading the face model needs more than the 2 GB default.
- **Face model files:** upload `det_10g.onnx` and `w600k_r50.onnx` from `~/.insightface/models/buffalo_l/` to a public location, e.g. the Blob store under `models/buffalo_l/`. Set `FACE_MODEL_BASE_URL` to that folder. On a cold start the API downloads them into `/tmp`, which takes a few seconds once per instance.
- **Migrations** are not run automatically. After a deploy that adds migrations:
  ```bash
  cd backend
  vercel link --project siora-one-api
  vercel env pull .env.local     # DATABASE_URL etc.; .env.local is gitignored
  python manage.py migrate
  python manage.py create_superadmin --email you@example.com --password '...'
  ```
- Static files (Django admin CSS) are collected and served by Vercel automatically.

### 2. Web app: `siora-one`

- **Root Directory:** `client`. Build settings come from `client/vercel.json`.
- **Environment variable:** `VITE_API_URL=https://siora-one-api.vercel.app/api/`

---

## For the mobile app

- **Base URL:** `https://siora-one-api.vercel.app/api/`
- **Interactive docs (Swagger):** `https://siora-one-api.vercel.app/api/docs/`
- **OpenAPI schema** (import into Postman or generate a client): `https://siora-one-api.vercel.app/api/schema/`
- **Health check:** `GET /api/health/` → `{"status": "ok", "database": "ok"}`

Trailing slashes are optional on every route, so `/api/me` and `/api/me/` both work.

### Authentication (JWT)

```http
POST /api/auth/login/
Content-Type: application/json

{"username": "...", "password": "..."}
```

The response is `{"access": "...", "refresh": "..."}`. Send `Authorization: Bearer <access>` on every request. The access token lasts 60 minutes. Exchange the refresh token (valid 30 days) for a new access token with `POST /api/auth/refresh/` and body `{"refresh": "..."}`.

### Key endpoints

| Method | Path | Auth | Body |
|--------|------|------|------|
| POST | `/api/employee/register/` | none | multipart: `name`, `contact`, `department`, `location` (location code), `email` (optional), `image` (face photo) |
| POST | `/api/attendance/mark/` | none | multipart: `image` (face photo), `type` = `IN` or `OUT` |
| GET | `/api/locations/` | none | list of locations (use `code` for registration) |
| GET | `/api/me/` | Bearer | current user's profile |
| GET | `/api/me/attendance/` | Bearer | current user's attendance |
| GET | `/api/me/payroll/` | Bearer | current user's payroll |

Image URLs in responses (e.g. `profile_picture`) are absolute `https://` URLs.

Errors come back as JSON with an `error` field and a 4xx/5xx status.

The first face request after a period of inactivity takes a few extra seconds while the model loads. Use a request timeout of at least 60 s on face endpoints.

---

## Notes

- The InsightFace pretrained models are licensed for non-commercial research use. Check the licence terms before using them in a paid product.
- Password reset doesn't send email yet. Outside DEBUG, `/api/auth/forgot-password/` never reveals the reset token, so an admin must reset passwords.
