# PPG Health App - Backend API

FastAPI backend for PPG (Photoplethysmography) health monitoring application.

## Features

- Real-time PPG data processing
- Quality Control (QC) feedback system
- Heart Rate (HR) and HRV analysis
- APG (Acceleration Photoplethysmography) analysis
- User authentication (Email, Kakao, Google)
- PostgreSQL database with SQLAlchemy ORM

## Tech Stack

- **Framework**: FastAPI 0.109.0
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy 2.0
- **Authentication**: JWT + OAuth2 (Kakao, Google)
- **Data Processing**: NumPy, SciPy, Pandas

## Setup Instructions

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your actual configuration
```

### 4. Set Up PostgreSQL Database

```bash
# Install PostgreSQL (macOS)
brew install postgresql@16
brew services start postgresql@16

# Create database
psql postgres
CREATE DATABASE ppghealth;
CREATE USER ppguser WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE ppghealth TO ppguser;
\q
```

### 5. Run Database Migrations

```bash
alembic upgrade head
```

### 6. Start the Server

```bash
# Development mode (with auto-reload)
uvicorn main:app --reload

# Or use Python directly
python main.py
```

The API will be available at:
- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc

## API Endpoints

### Health Check
- `GET /api/v1/health` - Server health status

### Measurements (Coming Soon)
- `POST /api/v1/measurements/start` - Start measurement
- `POST /api/v1/measurements/qc/data` - Submit QC data
- `GET /api/v1/measurements/qc/latest/{measurement_id}` - Get latest QC
- `POST /api/v1/measurements/complete` - Complete measurement
- `POST /api/v1/measurements/analyze` - Analyze measurement

### Authentication (Coming Soon)
- `POST /api/v1/auth/signup` - Email signup
- `POST /api/v1/auth/login` - Email login
- `GET /api/v1/auth/me` - Get current user
- `GET /api/v1/auth/kakao` - Kakao OAuth
- `GET /api/v1/auth/google` - Google OAuth

## Project Structure

```
ppg-backend/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── .gitignore
├── README.md
└── app/
    ├── __init__.py
    ├── api/
    │   ├── __init__.py
    │   └── routes/
    │       ├── __init__.py
    │       ├── health.py       # Health check
    │       ├── measurements.py # Measurement endpoints
    │       ├── auth.py         # Authentication
    │       └── analysis.py     # Analysis endpoints
    ├── core/
    │   ├── __init__.py
    │   ├── config.py          # App configuration
    │   └── security.py        # JWT & password hashing
    ├── db/
    │   ├── __init__.py
    │   ├── database.py        # DB connection
    │   ├── models/            # SQLAlchemy models
    │   │   ├── __init__.py
    │   │   ├── user.py
    │   │   ├── measurement.py
    │   │   └── ...
    │   └── schemas/           # Pydantic schemas
    │       ├── __init__.py
    │       └── ...
    ├── services/
    │   ├── __init__.py
    │   ├── qc_service.py      # Quality control
    │   ├── analysis_service.py # HR, HRV, APG analysis
    │   └── oauth.py           # OAuth integrations
    └── utils/
        ├── __init__.py
        └── signal_processing.py # DSP functions
```

## Development

### Run Tests

```bash
pytest
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Code Quality

```bash
# Format code
black app/

# Lint
flake8 app/

# Type checking
mypy app/
```

## Architecture

### Data Flow

1. **Mobile App** sends PPG data (300Hz, 24-byte packets)
2. **QC Pipeline** validates data quality (2-second windows)
3. **Analysis Pipeline** processes data (10-second windows)
4. **Results** sent back to mobile app

### Window Strategy

- **QC**: 2-second windows, 2-second hop (30 windows/minute)
- **Analysis**: 10-second windows, 10-second hop (6 windows/minute)
- **No overlap** - optimized for Oracle Free Tier

### Performance

- **Computation**: 540K operations total (270K QC + 270K analysis)
- **Processing Time**: 0.5-0.9 seconds on ARM (Oracle Free Tier)
- **Concurrent Users**: 15-20 users supported

## License

MIT
