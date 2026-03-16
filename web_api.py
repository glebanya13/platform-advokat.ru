import os
from datetime import datetime
from typing import Optional

import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

PLATFORM_TO_LEGAL_NAME = {
    "yandex": "Яндекс Go",
    "wb": "Wildberries",
    "ozon": "Ozon",
    "sber": "Купер",
    "other": "Другое",
}

app = FastAPI(title="PlatformAdvokat Gemini API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    role: Optional[str] = None
    platform: Optional[str] = None
    problem: Optional[str] = None
    amount: Optional[float] = None
    details: Optional[str] = None
    full_name: Optional[str] = None
    account_id: Optional[str] = None
    incident_date: Optional[str] = None


class GenerateResponse(BaseModel):
    legal_text: str


def _platform_legal_name(code: str) -> str:
    return PLATFORM_TO_LEGAL_NAME.get(code, "Другое")


def _build_prompt(body: GenerateRequest) -> str:
    platform_name = _platform_legal_name((body.platform or "other").strip().lower())
    full_name = (body.full_name or "").strip() or "Заявитель"
    account_id = (body.account_id or "").strip() or "не указан"
    incident_date = (body.incident_date or "").strip() or datetime.now().strftime("%d.%m.%Y")
    problem = (body.problem or "").strip() or "Проблема не указана"
    description = (body.details or "").strip() or problem
    if body.amount:
        description += f" Сумма удержания/штрафа: {body.amount} руб."

    return f"""
Ты — профессиональный юрист, эксперт по закону 289-ФЗ «О платформенной экономике».

ТВОЯ ЗАДАЧА: Составить текст досудебной претензии.

ДАННЫЕ:
- ФИО заявителя: {full_name}
- Платформа: {platform_name}
- ID аккаунта: {account_id}
- Тип проблемы: {problem}
- Дата инцидента: {incident_date}
- Описание ситуации клиента: {description}

ТРЕБОВАНИЯ К ТЕКСТУ:
1. Преобразуй описание клиента в юридически грамотный текст
2. Обязательно сошлись на ФЗ-289: статьи 12, 14, 15
3. Укажи конкретные нарушенные права и сформулируй требование к платформе
4. Укажи срок рассмотрения (15 рабочих дней согласно ст. 15 ФЗ-289)
ТОН: Официальный, юридически грамотный. Без эмоций.
ФОРМАТ: Сплошной текст претензии, без разделения на разделы.

Начни текст с: \"Я, {full_name}, являюсь исполнителем на цифровой платформе {platform_name}...\"
""".strip()


@app.post("/api/generate-complaint", response_model=GenerateResponse)
async def generate_complaint(body: GenerateRequest):
    """Генерация текста претензии через Gemini."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Сервис не настроен: укажите GEMINI_API_KEY в переменных окружения",
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        prompt = _build_prompt(body)
        resp = await model.generate_content_async(prompt)
        legal_text = (resp.text or "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini error: {e}")

    if not (legal_text or "").strip():
        raise HTTPException(status_code=500, detail="Пустой ответ от сервиса")
    return GenerateResponse(legal_text=legal_text.strip())


@app.get("/health")
def health():
    return {"ok": True}
