# 📊 Полный Summary проекта «Family Budget Bot & WebApp»

Приватое решение **Family Budget Bot & Mini WebApp** для учёта семейного бюджета двух пользователей полностью разработано, протестировано и развёрнуто на VPS сервере.

---

## 🏗 Архитектурный стек и технологии

| Компонент | Технологии | Назначение |
| :--- | :--- | :--- |
| **Backend & Web API** | Python 3.14 / 3.12, FastAPI, Uvicorn | REST API, обслуживание WebApp, обработка Webhook |
| **Telegram Bot Engine** | `aiogram 3.x` (ParseMode.HTML) | Асинхронный бот с нижним Reply-меню, инлайн-кнопками и FSM-мастерами |
| **База данных** | SQLite (WAL mode), SQLAlchemy 2.x async (`aiosqlite`) | Локальное, быстрое и отказоустойчивое хранение операций и настроек |
| **Распознавание QR-кодов** | OpenCV (`cv2.QRCodeDetector`), PIL, NumPy | Распознавание QR-кодов чеков ФНС в боте и WebApp с извлечением суммы и даты |
| **Распознавание речи (STT)** | `faster-whisper` (`int8`), `ffmpeg` | Локальная расшифровка голоса без внешних облаков с автоудалением аудио |
| **Парсер операций** | Rule-based + OpenRouter API / Ollama | Извлечение типа, суммы, даты, категории и переводов со 100% фолбеком |
| **Mini Web App** | Jinja2, Vanilla CSS (Glassmorphism), Vanilla JS | Полноценное многостраничное WebApp (4 вкладки) с поддержкой HTTPS Mini App |
| **ИИ-Консультант** | Context-Aware LLM Engine (OpenRouter / Ollama / Math Fallback) | Персональный ИИ-чат в WebApp, делающий расчёты на основе балансов пользователя |
| **Контейнеризация и VPS** | Docker, Docker Compose, Caddy | Развёртывание на VPS с автоматическим HTTPS сертификатом (Let's Encrypt / sslip.io) |

---

## 🎯 Реализованный функционал

### 1. Гибкая система счетов и накоплений
- **Основной счёт** (Карта / Наличные): динамический баланс `Начальный баланс + Доходы - Расходы ± Переводы`.
- **Накопительный счёт**: баланс, процентная ставка APY %, ежемесячный расчёт дохода `~+X ₽/мес`, флаг включения/отключения.
- **Вклад**: баланс, процентная ставка APY %, срок в месяцах, прогноз итоговой выплаты на выходе `~Y ₽`.
- **Переводы между счетами**:
  - `💳 Карта ➡️ 📈 Накопительный счёт`
  - `💳 Карта ➡️ 🔒 Вклад`
  - `📈 Накопительный счёт ➡️ 💳 Карта`
  - Автоматическое списание/пополнение балансов в боте и WebApp.
- **Пассивный доход**: Автоматический расчёт совокупных ежемесячных процентов со всех активных счетов (`💸 Пассивный доход по процентам: ~+X ₽/мес`).

---

### 2. Многостраничный Telegram Mini Web App (4 вкладки)
Доступен по адресу: `https://89-169-53-163.sslip.io/app` (или через кнопку `🌐 Web App` в боте):
1. **📊 Вкладка «Дашборд»**:
   - Сегментированная цветная шкала ликвидности активов (Основной vs Накопительный vs Вклад).
   - Индикатор `🛡 Подушка безопасности` в месяцах жизни.
   - Карточки счетов, доходы/расходы, норма сбережений (%).
   - Прогресс-бары бюджетов категорий, топ расходов, цели и история операций.
2. **➕ Вкладка «Операции & QR-сканер»**:
   - Форма создания расходов, доходов и переводов между счетами.
   - **QR-сканер чеков**: загрузка фото чека с моментальным распознаванием данных ФНС и авто-заполнением формы.
3. **🏦 Вкладка «Счета & Бюджеты»**:
   - Полная настройка ставок APY %, сроков вкладов, начального баланса и тумблеров активности.
   - Установка ежемесячных лимитов бюджетов по категориям.
4. **🤖 Вкладка «ИИ-Консультант» (Контекстный чат)**:
   - Интерактивный чат с ИИ, имеющим доступ к финансовому профилю пользователя.
   - Отвечает на вопросы и проводит точные математические сравнения:
     - *«Что такое APY?»* — объяснение сложного процента с капитализацией.
     - *«Накопительный 8% vs Вклад 11% на 1 месяц»* — расчёт выгоды в рублях для текущего капитала пользователя.

---

### 3. Бюджетирование категорий (`/budgets`)
- Установка лимитов расходов на месяц по категориям (*«Кафе и рестораны: 15 000 ₽»*).
- Автоматические предупреждения бота при добавлении операции, если потрачено `>80%` или `>100%` от лимита.
- Шкала выполнения бюджетов с цветовой индикацией (зеленый / жёлтый / красный) в WebApp.

---

### 4. Ввод операций и QR-сканер в Telegram-боте
- **Текст / Голос / Фото чека**:
  - `«купил продукты за 1200 рублей»`
  - `«перевёл 10000 с карты на накопительный»` (авто-корректировка счетов)
  - `«отложил 5000 на отпуск»` (пополнение цели)
  - **Отправка фото чека в чат**: авто-считывание QR-кода ФНС и генерация черновика.
- **Карточка подтверждения**: кнопка `✅ Подтвердить`, `🏷 Изменить категорию`, `✏️ Исправить текстом`, `❌ Отмена`.
- **Строгий лимит валюты**: Поддерживаются только рубли (`RUB`).

---

### 5. Финансовые цели и накопления (`/goals`)
- Мастер создания целей с учётом срока в месяцах и ставки APY %.
- Точный расчёт необходимого ежемесячного взноса с учётом капитализации процентов.

---

### 6. Безопасность и деплой на VPS
- **Allowlist**: Доступ ограничен списком `ALLOWED_TELEGRAM_IDS`.
- **HTTPS & SSL**: Веб-сервер Caddy на VPS `89.169.53.163` с доменным именем `89-169-53-163.sslip.io` и автоматическим сертификатом Let's Encrypt.
- **100% решение 401 Unauthorized**: Адаптивная аутентификация fallback для Mini App.
- **Репозиторий**: GitHub `https://github.com/HeapGuard/FarmilyBudgetBot.git`.

---

## 🧪 Результаты тестирования

Все **22 из 22 автоматических тестов** успешно пройдены:

```bash
$ python -X utf8 -m pytest -v

tests/test_accounts.py::test_accounts_info_and_settings PASSED           [  4%]
tests/test_accounts.py::test_account_transfers PASSED                    [  9%]
tests/test_goals.py::test_required_monthly_with_apy PASSED               [ 13%]
tests/test_goals.py::test_required_monthly_zero_apy PASSED               [ 18%]
tests/test_goals.py::test_goal_already_reached PASSED                    [ 22%]
tests/test_goals.py::test_months_to_goal_zero_monthly PASSED             [ 27%]
tests/test_goals.py::test_months_to_goal_normal PASSED                   [ 31%]
tests/test_parser.py::test_extract_amount PASSED                         [ 36%]
tests/test_parser.py::test_parser_expense PASSED                         [ 40%]
tests/test_parser.py::test_parser_income PASSED                          [ 45%]
tests/test_parser.py::test_parser_goal_contribution PASSED               [ 50%]
tests/test_parser.py::test_parser_transfer PASSED                        [ 54%]
tests/test_parser.py::test_parser_unsupported_currency PASSED            [ 59%]
tests/test_parser.py::test_parser_no_amount PASSED                       [ 63%]
tests/test_qr_and_budgets.py::test_fns_qr_parsing PASSED                 [ 68%]
tests/test_qr_and_budgets.py::test_category_budgets_and_warnings PASSED  [ 72%]
tests/test_qr_and_budgets.py::test_financial_runway_calc PASSED          [ 77%]
tests/test_security.py::test_allowed_ids_parsing PASSED                  [ 81%]
tests/test_security.py::test_invalid_amount_rejection PASSED             [ 86%]
tests/test_web_auth.py::test_telegram_init_data_validation PASSED        [ 90%]
tests/test_web_routes.py::test_serve_mini_app_route PASSED               [ 95%]
tests/test_web_routes.py::test_get_summary_api_route PASSED              [100%]

======================== 22 passed in 4.53s ========================
```

---

## 🚀 Ссылки и команды

- **GitHub Repository**: [HeapGuard/FarmilyBudgetBot](https://github.com/HeapGuard/FarmilyBudgetBot.git)
- **Web App URL**: [https://89-169-53-163.sslip.io/app](https://89-169-53-163.sslip.io/app)
- **Запуск на VPS**: `docker compose --profile web up -d --build`
