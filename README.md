# BuildTrack Backend

BuildTrack Backend - это backend-модуль системы цифрового строительного контроля.

Система предназначена для фиксации строительных объектов, этапов работ, загрузки файлов сканов, расчета контрольных SHA-256 хешей, ведения статусов проверки, хранения истории изменений и формирования цифрового результата проверки.

Основная цепочка работы:

```text
объект - этап - скан - SHA-256 хеш - статус проверки - история изменений - отчет - digital proof
```

## Назначение

Backend обеспечивает серверную логику для работы с данными строительного контроля:

- создание строительных объектов;
- создание этапов работ;
- загрузка файлов сканов;
- расчет SHA-256 хеша загруженного файла;
- привязка скана к объекту и этапу;
- фиксация статуса проверки;
- сохранение истории изменения статуса;
- формирование отчета по объекту;
- формирование digital proof package для цифровой фиксации результата проверки.

## Технологический стек

- Python
- FastAPI
- SQLite
- SQLAlchemy
- Pydantic
- Uvicorn
- SHA-256
- Swagger / OpenAPI

## Функциональность

### 1. Объекты строительства

Система позволяет создавать строительные объекты.

Пример объекта:

```json
{
  "name": "BuildTrack Object",
  "description": "Строительный объект"
}
```

### 2. Этапы работ

Система позволяет создавать этапы работ и привязывать их к строительному объекту.

Пример этапа:

```json
{
  "name": "Фундамент",
  "project_id": 1
}
```

### 3. Загрузка сканов

Backend принимает файл скана, сохраняет его в хранилище, рассчитывает SHA-256 хеш и сохраняет запись в базе данных.

Для каждого скана фиксируются:

- объект;
- этап;
- имя файла;
- путь к файлу;
- SHA-256 хеш;
- статус проверки;
- проверяющий;
- время проверки.

### 4. Статусы проверки

Поддерживаются следующие статусы:

```text
pending
valid
invalid
manual_review
```

Описание статусов:

```text
pending — скан загружен и ожидает проверки
valid — проверка пройдена успешно
invalid — обнаружено несоответствие
manual_review — требуется ручная проверка
```

### 5. История изменений

Система ведет audit trail по каждому скану.

Фиксируются:

- старый статус;
- новый статус;
- кто изменил статус;
- время изменения.

Пример изменения статуса:

```text
pending → valid
```

### 6. Отчет по объекту

Endpoint:

```http
GET /projects/{project_id}/report
```

Возвращает сводный отчет по строительному объекту:

- данные объекта;
- этапы работ;
- количество сканов;
- список сканов по этапам;
- последний SHA-256 хеш;
- последний статус;
- итоговый статус объекта;
- историю проверок.

### 7. Digital Proof

Endpoint:

```http
GET /projects/{project_id}/digital-proof
```

Формирует цифровой пакет результата проверки.

Пакет содержит:

- project_id;
- project_name;
- stage_id;
- stage_name;
- scan_id;
- file_name;
- file_path;
- file_hash;
- verification_status;
- checked_by;
- checked_at;
- proof_generated_at;
- algorithm;
- digital_proof_hash.

`digital_proof_hash` — это SHA-256 хеш от всего proof-пакета.

Он используется как контрольный цифровой отпечаток результата проверки.

## Запуск проекта

### 1. Создать и активировать виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Установить зависимости

```bash
python -m pip install -r requirements.txt
```

### 3. Применить миграции базы данных

```bash
alembic upgrade head
```

Параметры локальной среды можно задать через переменные из `.env.example`:

```text
BUILDTRACK_DATABASE_URL
BUILDTRACK_UPLOAD_DIR
BUILDTRACK_MAX_PDF_SIZE_BYTES
BUILDTRACK_JWT_SECRET
BUILDTRACK_ACCESS_TOKEN_EXPIRE_MINUTES
```

### 4. Запустить сервер

```bash
uvicorn app.main:app --reload
```

### 5. Открыть Swagger

```text
http://127.0.0.1:8000/docs
```

### Тесты

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Основные endpoints

### Объекты

```http
POST /projects/
GET /projects/
GET /projects/{project_id}
DELETE /projects/{project_id}
GET /projects/{project_id}/report
GET /projects/{project_id}/digital-proof
```

### Этапы

```http
POST /stages/
GET /stages/
GET /stages/{stage_id}
DELETE /stages/{stage_id}
```

### Сканы

```http
POST /scans/upload
GET /scans/
GET /scans/{scan_id}
PATCH /scans/{scan_id}/status
DELETE /scans/{scan_id}
GET /scans/{scan_id}/audit
```

### Нормативы

```http
POST /normatives/
GET /normatives/
GET /normatives/{normative_id}
PATCH /normatives/{normative_id}
DELETE /normatives/{normative_id}
POST /normatives/{normative_id}/versions
```

Норматив связывается с одним или несколькими этапами. Изменение текста требования,
кода документа или даты действия выполняется созданием новой версии через endpoint
`/normatives/{normative_id}/versions`. Предыдущие версии не удаляются и остаются
доступными для истории проверок.

### Пользователи и роли проекта

```http
POST /users
GET /users
GET /users/{user_id}
PATCH /users/{user_id}
DELETE /users/{user_id}
POST /projects/{project_id}/members
GET /projects/{project_id}/members
DELETE /projects/{project_id}/members/{membership_id}
POST /auth/bootstrap
POST /auth/login
GET /auth/me
PUT /auth/password
```

Роль хранится в членстве проекта, а не глобально у пользователя. Поэтому один
пользователь может выполнять разные роли в разных проектах. Временный MVP-набор:
`investor`, `project_manager`, `inspector`, `contractor`, `service_agent`.

В текущей матрице доступа `contractor` выполняет роль рабочего: видит только
назначенные ему задачи, может начать их и отправить на проверку. `project_manager`
выполняет роль прораба: создаёт и распределяет задачи, управляет их жизненным циклом
и принимает результат. `inspector` подтверждает или отклоняет работу, а `investor`
имеет доступ только на чтение. `service_agent` зарезервирован для будущих интеграций
и в задачах ограничен правилами назначенного исполнителя.

Перед первым использованием нужно один раз создать администратора через
`POST /auth/bootstrap`. После этого endpoint закрывается. В Swagger вход выполняется
через `POST /auth/login`, а полученный JWT вставляется в кнопку `Authorize`.
Смена пароля отзывает ранее выданные токены. Все бизнес-endpoints требуют Bearer JWT.

### Задачи

```http
POST /tasks/
GET /tasks/
GET /tasks/{task_id}
PATCH /tasks/{task_id}
PATCH /tasks/{task_id}/status
GET /tasks/{task_id}/audit
```

Жизненный цикл задачи основан на полном ТЗ:

```text
created -> active -> pending_verification -> verified
                                      \----> rejected -> active
created/active/rejected -> cancelled
```

Каждый переход сохраняется в append-only истории. Детальные временные решения по
ролям, проверкам и актам зафиксированы в `docs/provisional_mvp_defaults.md`.
Исполнитель не может открыть чужую задачу или самостоятельно перевести свою задачу
в `verified`. Подтверждение выполняет прораб или инспектор согласно их правам.

### Проектная документация

```http
POST /documents/upload
GET /documents/
GET /documents/{document_id}
GET /documents/{document_id}/download
GET /documents/{document_id}/versions
POST /documents/{document_id}/versions
DELETE /documents/{document_id}
```

Для MVP принимаются только PDF-файлы. Backend проверяет расширение, MIME-тип,
сигнатуру `%PDF-` и ограничение размера, сохраняет файл под случайным именем и
вычисляет SHA-256. Путь в БД хранится относительно каталога загрузок.

Новая версия получает тот же `series_key`, ссылается на предыдущую через
`supersedes_id`, а предыдущая версия становится неактивной. Файлы старых версий
сохраняются, чтобы будущая проверка и отчет всегда ссылались на точный снимок
документа. `DELETE` выполняет мягкую деактивацию и не уничтожает историю.

Максимальный размер PDF задается переменной
`BUILDTRACK_MAX_PDF_SIZE_BYTES` (по умолчанию 25 МиБ).

### Проверки и замечания

```http
POST /checks/
GET /checks/
GET /checks/{check_id}
GET /checks/{check_id}/report
GET /checks/{check_id}/report.pdf
PATCH /findings/{finding_id}
GET /findings/{finding_id}/audit
```

Проверка запускается для конкретной неизменяемой версии документа. В запись проверки
копируются SHA-256 документа и полные снимки всех активных нормативов выбранного
этапа. Поэтому последующее обновление нормативной базы не переписывает старый
результат.

Детерминированный движок извлекает текст PDF и поддерживает три типа правил:
`required_phrase`, `forbidden_phrase`, `manual_review`. Замечания содержат важность,
страницу, основание, рекомендацию, статус и append-only историю ручной проверки.
Использование учебного или не подтвержденного экспертом правила никогда не
даёт безусловный результат `valid`.

JSON-отчет доступен через `/report`, а готовый PDF для скачивания - через
`/report.pdf`.

### Технические акты

```http
POST /acts/
GET /acts/
GET /acts/{act_id}
PATCH /acts/{act_id}/status
GET /acts/{act_id}/audit
```

Акт хранит номер, версию, проект, этап, точную проверку и документ, участников и их
роли, снимок замечаний, verdict, хеш документа и хеш отчета. Жизненный цикл:

```text
draft -> ready -> approved
draft/ready/approved -> cancelled
ready -> draft
```

Акт приемки этапа нельзя перевести в `ready`, пока замечания ожидают рассмотрения.
Подтвердить подготовленный технический акт может прораб (`project_manager`) или
инспектор (`inspector`); автор и каждый переход сохраняются в истории.
Это техническая JSON-запись MVP, а не КС-2, квалифицированная электронная подпись или
юридический платежный триггер.

Полный проверочный сценарий описан в
`docs/backend_acceptance_checklist.md`. Пошаговая инструкция для проверки на
учебном PDF находится в `docs/backend_demo_ru.md`.

### Автоматическая подготовка приёмки

Полный локальный сценарий можно создать одной командой после применения миграций:

```bash
python scripts/seed_acceptance_scenario.py
```

Скрипт скрыто запросит один временный пароль и создаст проект, этап `Фундамент`,
четыре учётные записи с ролями, контрольные правила, PDF, завершённую проверку,
рассмотренные замечания, принятую задачу и утверждённый технический акт. Итоговые
идентификаторы сохраняются в `output/acceptance/scenario-summary.json`, PDF-отчёт -
в `output/pdf/buildtrack-otchet-priemka-fundament.pdf`, а локальный файл доступов -
в `output/acceptance/access.txt` с правами `600`. Готовая инструкция с точными ID
появится в `output/acceptance/how-to-check.txt`. Каталог `output/` не попадает в Git.

Для автоматического локального запуска без запроса пароля:

```bash
python scripts/seed_acceptance_scenario.py --generate-password
```

Повторный запуск с тем же именем проекта останавливается без создания дубля. Для
отдельного сценария можно передать `--project-name "Новое имя"`.

## Рабочий сценарий

### Шаг 1. Создать объект

Endpoint:

```http
POST /projects/
```

Пример тела запроса:

```json
{
  "name": "BuildTrack Object",
  "description": "Строительный объект"
}
```

### Шаг 2. Создать этап

Endpoint:

```http
POST /stages/
```

Пример тела запроса:

```json
{
  "name": "Фундамент",
  "project_id": 1
}
```

### Шаг 3. Загрузить скан

Endpoint:

```http
POST /scans/upload
```

Передаваемые данные:

```text
project_id = 1
stage_id = 1
file = scan.txt
```

После загрузки система сохраняет файл, рассчитывает SHA-256 хеш и создает запись скана со статусом `pending`.

### Шаг 4. Изменить статус проверки

Endpoint:

```http
PATCH /scans/{scan_id}/status
```

Пример тела запроса:

```json
{
  "status": "valid",
  "checked_by": "Технический надзор"
}
```

После изменения статуса система сохраняет запись в audit trail.

### Шаг 5. Получить отчет по объекту

Endpoint:

```http
GET /projects/1/report
```

Пример ответа:

```json
{
  "project": {
    "project_id": 1,
    "name": "BuildTrack Object",
    "description": "Строительный объект"
  },
  "summary": {
    "total_stages": 1,
    "total_scans": 1,
    "latest_scan_id": 1,
    "latest_hash": "55cdacd244c392bbf2c9fa367a3157be0afabb7ea0467a4baefb0fc38c0103cc",
    "latest_status": "valid",
    "final_object_status": "valid",
    "generated_at": "2026-05-25T21:33:31.666111"
  },
  "stages": [
    {
      "stage_id": 1,
      "stage_name": "Фундамент",
      "project_id": 1,
      "scans_count": 1,
      "scans": [
        {
          "scan_id": 1,
          "file_name": "scan.txt",
          "file_path": "uploads/scan.txt",
          "file_hash": "55cdacd244c392bbf2c9fa367a3157be0afabb7ea0467a4baefb0fc38c0103cc",
          "status": "valid",
          "checked_by": "Технический надзор",
          "checked_at": "2026-05-22T21:34:26.483843"
        }
      ]
    }
  ],
  "audit_trail": [
    {
      "audit_id": 2,
      "scan_id": 1,
      "old_status": "pending",
      "new_status": "valid",
      "changed_by": "Технический надзор",
      "changed_at": "2026-05-22T21:34:26.488569"
    },
    {
      "audit_id": 1,
      "scan_id": 1,
      "old_status": null,
      "new_status": "pending",
      "changed_by": "система",
      "changed_at": "2026-05-22T21:34:02.511803"
    }
  ]
}
```

### Шаг 6. Получить digital proof

Endpoint:

```http
GET /projects/1/digital-proof
```

Пример ответа:

```json
{
  "message": "Пакет проверки целостности успешно сформирован",
  "proof_type": "Цифровое доказательство BuildTrack",
  "proof_payload": {
    "project_id": 1,
    "project_name": "BuildTrack Object",
    "stage_id": 1,
    "stage_name": "Фундамент",
    "scan_id": 1,
    "file_name": "scan.txt",
    "file_path": "uploads/scan.txt",
    "file_hash": "55cdacd244c392bbf2c9fa367a3157be0afabb7ea0467a4baefb0fc38c0103cc",
    "verification_status": "valid",
    "checked_by": "Технический надзор",
    "checked_at": "2026-05-22T21:34:26.483843",
    "proof_generated_at": "2026-05-25T21:35:40.273562",
    "algorithm": "SHA-256"
  },
  "digital_proof_hash": "5c3d8fb61d99054b57994534631ca6733c1fff9708f4f3497a0643d58298c94e"
}
```

## Роль backend-модуля в системе BuildTrack

Backend-модуль отвечает за серверную часть цифрового строительного контроля:

```text
прием данных - хеширование - хранение - проверка - история - отчет - цифровая фиксация
```

Он обеспечивает основу для работы с объектами, этапами, сканами, статусами проверки и контрольными хешами.

## Направления дальнейшего развития

Дальнейшее развитие системы может включать:

- интеграцию с LiDAR-сканированием;
- обработку облаков точек;
- работу с BIM/IFC-моделями;
- автоматическое сравнение фактического скана с проектной моделью;
- расширенную систему отчетности;
- интеграцию с внешним контуром цифровой фиксации;
- web-интерфейс для просмотра объектов, этапов, сканов и статусов.
