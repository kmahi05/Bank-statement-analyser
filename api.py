"""Optional HTTP endpoint.

    pip install -r requirements-api.txt
    uvicorn api:app --reload
    curl -F "file=@data/statement_A.csv" http://127.0.0.1:8000/analyze
"""
from fastapi import FastAPI, File, HTTPException, UploadFile

from analyzer.parser import StatementError
from analyzer.report import analyse

app = FastAPI(title="Bank Statement Analyzer")


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="file must be UTF-8 CSV text")
    try:
        return analyse(text)
    except StatementError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
