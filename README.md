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

### 1. Активировать виртуальное окружение

```bash
source venv/bin/activate
```

### 2. Запустить сервер

```bash
uvicorn app.main:app --reload
```

### 3. Открыть Swagger

```text
http://127.0.0.1:8000/docs
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
      "changed_by": "system",
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
  "message": "Digital proof package generated successfully",
  "proof_type": "BuildTrack Digital Proof",
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
