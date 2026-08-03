# 💰 Family Budget Bot & Telegram Mini Web App

Безопасное, готовое к продакшену приложение для учёта семейного бюджета двух пользователей на базе Telegram Bot и Telegram Mini Web App (Python 3.12, aiogram 3, FastAPI, SQLite, faster-whisper).

---

## 🚀 Возможности MVP

- **Учёт операций**: Доходы, расходы, переводы и пополнения целей текстом и голосовыми сообщениями.
- **Подтверждение перед сохранением**: Каждая операция отображается в виде интерактивной карточки для подтверждения или смены категории.
- **Локальное распознавание речи**: `faster-whisper` + `ffmpeg` без отправки голосовых в облако и с немедленным удалением аудиофайлов после распознавания.
- **Финансовые цели**: Точный расчёт будущей стоимости и требуемых ежемесячных взносов с учётом процентных ставок по вкладам (детерминированные математические формулы).
- **Персональные советы**: Автоматический 3–5 пунктный анализ привычек, норм сбережений и прироста категорий без галлюцинаций LLM.
- **Telegram Mini Web App**: Современное мобильное веб-приложение для мгновенного обзора баланса, сводки за месяц, прогресса целей и истории транзакций.
- **Поддержка слабых VPS**: Работает полностью автономно в режимах `rule_based` / `OpenRouter` / `Ollama`.
- **Безопасность**: Доступ строго по Allowlist `ALLOWED_TELEGRAM_IDS`, защита Telegram `initData` через HMAC-SHA256, отсутствие платежей и банковских паролей.

---

## 📂 Структура проекта

```
our-moneys/
├── app/
│   ├── main.py              # Точка входа (FastAPI + aiogram polling/webhook)
│   ├── config.py            # Настройки и валидация .env (pydantic-settings)
│   ├── database.py          # SQLAlchemy 2.x async SQLite (WAL mode)
│   ├── models/              # ORM модели и Pydantic схемы
│   ├── bot/                 # Aiogram 3 хэндлеры, клавиатуры и мидлварь доступа
│   ├── web/                 # FastAPI веб-эндпоинты, HMAC-авторизация и шаблоны Jinja2
│   └── services/            # Парсер, STT, калькулятор целей, советник, CSV экспорт
├── tests/                   # Модульные и интеграционные pytest тесты
├── Dockerfile               # Многоэтапный Dockerfile (Python 3.12 + ffmpeg)
├── docker-compose.yml       # Конфигурация сервисов (app, caddy, ollama)
├── Caddyfile.example        # Reverse proxy Caddy с авто-SSL
├── .env.example             # Пример конфигурации окружения
└── README.md
```

---

## 🛠 Настройка Telegram Bot & Mini App

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Создайте нового бота (`/newbot`) и скопируйте `BOT_TOKEN`.
3. Установите меню команд:
   ```
   start - Главное меню
   help - Справка
   add - Добавить операцию
   balance - Показать текущий баланс
   set_balance - Установить стартовый баланс
   report - Отчёт за текущий месяц
   goals - Список целей
   goal_new - Создать новую цель
   advice - Получить совет
   open_app - Открыть Mini Web App
   export - Выгрузить CSV
   privacy - Приватность
   delete_all - Сбросить все данные
   ```
4. Перейдите в `/newapp` или редактирование бота (`Edit Bot` -> `Web Apps`) и добавьте URL вашего Mini App: `https://your-domain.com/app`.

---

## ⚙️ Настройка двух пользователей (Allowlist)

Укажите Telegram ID обоих пользователей в переменной `ALLOWED_TELEGRAM_IDS` через запятую:

```env
ALLOWED_TELEGRAM_IDS=123456789,987654321
```

Узнать свой Telegram ID можно с помощью [@userinfobot](https://t.me/userinfobot).

---

## 💻 Локальный запуск (Development)

1. Клонируйте репозиторий и создайте `.env`:
   ```bash
   cp .env.example .env
   ```
2. Установите зависимости:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Или venv\Scripts\activate на Windows
   pip install -r requirements.txt
   ```
3. Убедитесь, что в системе установлен `ffmpeg` (для распознавания голоса).
4. Запустите тесты:
   ```bash
   pytest
   ```
5. Запустите приложение в режиме polling:
   ```bash
   python -m app.main
   ```
6. Веб-приложение будет доступно по адресу: `http://localhost:8000/app`.

---

## 🚢 Production запуск (Docker & Caddy)

1. Настройте `.env` файл на сервере:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   ALLOWED_TELEGRAM_IDS=123456789,987654321
   BASE_URL=https://budget.yourdomain.com
   MODE=webhook
   WEBHOOK_SECRET=your_super_secret_webhook_token
   SECRET_KEY=your_super_secret_hmac_key
   ```
2. Настройте `Caddyfile`:
   ```caddy
   budget.yourdomain.com {
       reverse_proxy app:8000
   }
   ```
3. Запустите Docker Compose:
   ```bash
   # Запуск только бота и веб-приложения с Caddy (для слабых VPS)
   docker compose --profile web up -d --build
   ```

---

## 🤖 Настройка LLM и Голоса (STT)

### Как выбрать LLM-провайдер:
- **`LLM_PROVIDER=rule_based`** (По умолчанию, идеально для VPS 1 CPU / 2GB RAM): 0% потребления лишних ресурсов, быстрый детерминированный парсинг и генерация советов.
- **`LLM_PROVIDER=openrouter`**: Облачные модели через OpenRouter API (например, `OPENROUTER_MODEL=qwen/qwen-2.5-7b-instruct`). Не нагружает ваш сервер.
- **`LLM_PROVIDER=ollama`**: Локальная нейросеть Ollama. Запускается командой `docker compose --profile web --profile llm up -d`.

### Как включить / выключить голосовой ввод (STT):
- **`STT_ENGINE=faster_whisper`**: Локальная расшифровка голоса через `faster-whisper` (модель `WHISPER_MODEL=Systran/faster-whisper-small` или `tiny`).
- **`STT_ENGINE=none`**: Отключает обработку голосовых сообщений для максимальной экономии ресурсов VPS.

---

## 💾 Резервное копирование SQLite

База данных хранится в локальном файле `./data/app.db` в режиме SQLite WAL.

Создать бэкап можно одной командой:
```bash
sqlite3 ./data/app.db ".backup ./data/app_backup_$(date +%F).db"
```

---

## 🔒 Безопасность и Приватность

- Все запросы от неавторизованных пользователей отклоняются.
- Пароли, банковские карты, номера счетов и SMS-коды не запрашиваются и не хранятся.
- Все суммы хранятся исключительно в рублевом эквиваленте (`RUB`).
- Любые операции добавляются только после подтверждения пользователем.
