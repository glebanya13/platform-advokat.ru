import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services import ai_service
from services.pdf_service import generate_complaint_pdf

PLATFORM_TO_LEGAL_NAME = {
    "yandex": "Яндекс Go",
    "wb": "Wildberries",
    "ozon": "Ozon",
    "sber": "Купер",
    "other": "Другое",
}

app = FastAPI(title="Платформенный Адвокат — Web API")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    role: str
    platform: str
    problem: str
    amount: Optional[float] = None
    details: Optional[str] = None
    full_name: Optional[str] = None
    account_id: Optional[str] = None
    incident_date: Optional[str] = None


class GenerateResponse(BaseModel):
    legal_text: str


class PdfRequest(BaseModel):
    legal_text: str
    platform: str
    full_name: str
    account_id: str
    incident_date: str


def _platform_legal_name(code: str) -> str:
    return PLATFORM_TO_LEGAL_NAME.get(code, "Другое")


@app.post("/api/generate-complaint", response_model=GenerateResponse)
async def generate_complaint(body: GenerateRequest):
    """Генерация текста претензии через Gemini."""
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        raise HTTPException(
            status_code=503,
            detail="Сервис не настроен: укажите GEMINI_API_KEY в переменных окружения",
        )
    platform_name = _platform_legal_name(body.platform)
    full_name = (body.full_name or "").strip() or "Заявитель"
    account_id = (body.account_id or "").strip() or "не указан"
    incident_date = (body.incident_date or "").strip() or datetime.now().strftime("%d.%m.%Y")
    description = (body.details or "").strip() or body.problem
    if body.amount:
        description += f" Сумма удержания/штрафа: {body.amount} руб."

    try:
        legal_text = await ai_service.generate_legal_text(
            platform_name=platform_name,
            issue_type=body.problem,
            description=description,
            full_name=full_name,
            account_id=account_id,
            incident_date=incident_date,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {e}")

    if not (legal_text or "").strip():
        raise HTTPException(status_code=500, detail="Пустой ответ от сервиса")
    return GenerateResponse(legal_text=legal_text.strip())


@app.post("/api/generate-pdf")
async def generate_pdf(body: PdfRequest):
    """Сформировать PDF по готовому тексту претензии и вернуть файл."""
    platform_name = _platform_legal_name(body.platform)
    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
    try:
        path = await generate_complaint_pdf(
            case_id=case_id,
            platform_name=platform_name,
            full_name=body.full_name.strip(),
            account_id=body.account_id.strip(),
            incident_date=body.incident_date.strip(),
            legal_text=body.legal_text,
        )
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=os.path.basename(path),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания PDF: {e}")


TEST_LEGAL_TEXT = """
Я, Тестовый Пользователь, являюсь исполнителем на цифровой платформе Яндекс Go (ID аккаунта: web-test).

10.03.2026 в отношении меня было принято решение: блокировка аккаунта без предварительного уведомления.

Считаю данное решение незаконным и нарушающим мои права, предусмотренные Федеральным законом от 13.07.2024 №289-ФЗ «О деятельности по организации комплексного обслуживания потребителей».

Согласно статье 12 указанного закона, платформа обязана обеспечивать прозрачность работы алгоритмов. Статья 14 ФЗ-289 устанавливает обязанность уведомлять исполнителя не менее чем за 24 часа до введения ограничений. Статья 15 ФЗ-289 гарантирует право на обжалование.

Требую: отменить решение, восстановить доступ, рассмотреть претензию в течение 15 рабочих дней.
"""


@app.get("/api/test-pdf")
async def test_pdf():
    """Скачать тестовый PDF (без вызова Gemini)."""
    platform_name = "Яндекс Go"
    case_id = f"TEST-{uuid.uuid4().hex[:6].upper()}"
    path = await generate_complaint_pdf(
        case_id=case_id,
        platform_name=platform_name,
        full_name="Тестовый Пользователь",
        account_id="web-test",
        incident_date=datetime.now().strftime("%d.%m.%Y"),
        legal_text=TEST_LEGAL_TEXT.strip(),
    )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"pretenziya_test_{case_id}.pdf",
    )


@app.get("/")
def index():
    """Главная страница сайта."""
    return FileResponse(os.path.join(SITE_DIR, "index.html"))


app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
