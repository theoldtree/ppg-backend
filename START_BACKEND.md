# 백엔드 실행 가이드

## 1단계: 가상환경 활성화 및 의존성 설치

```bash
cd /Users/yujeongmu/Desktop/ppg-backend

# 가상환경 활성화
source venv/bin/activate

# numpy 설치 (QC 서비스에 필요)
pip install numpy scipy

# 또는 requirements.txt에서 모두 설치
pip install -r requirements.txt
```

## 2단계: 데이터베이스 확인

이미 SQLite 데이터베이스가 생성되어 있습니다 (test.db).

필요시 테이블 재생성:
```bash
python create_tables.py
```

## 3단계: 백엔드 서버 실행

```bash
# 방법 1: uvicorn 직접 실행 (권장)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 방법 2: python으로 실행
python main.py
```

서버가 실행되면:
- API 서버: http://localhost:8000
- API 문서: http://localhost:8000/docs
- 대체 문서: http://localhost:8000/redoc

## 4단계: 실행 확인

터미널에서:
```bash
curl http://localhost:8000/api/v1/health
```

예상 응답:
```json
{"status": "healthy"}
```

## 실행 중 로그 확인

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using StatReload
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

## 종료

`Ctrl + C` 를 눌러 서버를 종료합니다.

## 트러블슈팅

### ModuleNotFoundError: No module named 'numpy'
```bash
source venv/bin/activate
pip install numpy scipy
```

### Address already in use
```bash
# 8000 포트를 사용중인 프로세스 확인
lsof -i :8000

# 해당 프로세스 종료
kill -9 <PID>
```

### CORS 에러
- .env 파일에서 ALLOWED_ORIGINS 확인
- React Native 에뮬레이터의 경우 http://localhost:8081 추가 필요
