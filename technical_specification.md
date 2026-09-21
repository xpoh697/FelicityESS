# Техническое задание (ТЗ): Home Assistant интеграция Felicity ESS

## 1. Введение и назначение
Разработка кастомной интеграции для Home Assistant (совместимой со стандартами HACS) для мониторинга батарей и инверторов Felicity Solar (Felicity ESS) на основе реверс-инжиниринга официального Android-приложения Fsolar (версия 4.0.9, пакет `com.felicity.solar`).

## 2. Результаты реверс-инжиниринга приложения Fsolar

### 2.1. Сетевая архитектура и эндпоинты
- **Базовый URL API:** `https://shine-api.felicitysolar.com`
- **Резервные / тестовые узлы:** `https://pre-api.felicitysolar.com`, `http://op-api-test.felicitysolar.com:8080`
- **Протокол:** HTTPS REST API, формат запросов и ответов `application/json; charset=utf-8`

### 2.2. Заголовки запросов (HTTP Headers)
Все запросы к API формируются со следующими обязательными заголовками:
- `source`: `"ANDROID"`
- `version`: `"4.0.9"`
- `lang`: `"ru"` или `"en"`
- `Content-Type`: `"application/json; charset=utf-8"`
- `token`: `<токен авторизации>` (после успешного входа)

### 2.3. Аутентификация и шифрование пароля
- **Эндпоинт авторизации:** `POST /app/base/userlogin`
- **Шифрование пароля:** Пароль перед отправкой шифруется по алгоритму RSA/ECB/PKCS1Padding и кодируется в Base64.
- **Публичный ключ RSA (2048 бит):**
```
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnAJE68pjWZmtSg6ZJs9FZugJXC6bBSluTW6mJttOLOaljrdErVnM5DNN+YFzpB9pAysTErjY1bnSVuEwQSwptnqUji7Ch2qMj2n+0eCp8p6vtSh7/tFr2ul8nDRtkoswLANAIwtUk/G85ipMpmY1W642LImnEJmGkkddlbjbjxJTZWR5hc/d9cPWb+AR77LxFFrMik3c+44v1kQlIPFP6EjIbOvt/Lv7fHWD9JI/YzN4y1gK7C/VQdNGuikQyNg+5W3rg9ecYf9I5uLAQwY/hxeI3lbNsErebqKe2EbJ8AwcNIC0lDBz53Sq0ML89QapEuy3fB+upuctxLULVDCbNwIDAQAB
```
- **Тело запроса авторизации:**
```json
{
  "userName": "user@example.com",
  "password": "<RSA_BASE64_ENCRYPTED_PASSWORD>",
  "version": "1.0",
  "registrationId": ""
}
```
- **Ответ авторизации:** Объект `UserEntity` со свойствами:
  - `token`: строка токена (передается в заголовке `token` во все последующие вызовы).
  - `id`: идентификатор пользователя (User ID).
  - `nodeList`: список доступных узлов API.

### 2.4. Получение списка станций (Plants)
- **Эндпоинт:** `POST /app/plant/list_plant`
- **Тело запроса:** `{"pageNum": 1, "pageSize": 50}`
- **Ответ:** Список объектов `PlantRootEntity`:
  - `plantId`: ID электростанции
  - `plantName`: Название электростанции
  - `status`: Статус (online/offline)
  - Сводные мощности: `pvPower`, `feedPower`, `loadPower`
  - Суточные счетчики: `todayBatteryCharging`, `todayBatteryDischarge`, `todayPv`, `todayLoad`, `todayFeedKwh`
  - Общие счетчики: `totalCharge`, `totalDischarge`, `totalPvOutputKwh`, `totalLoadConsumptionKwh`

### 2.5. Получение списка устройств станции (Devices)
- **Эндпоинт:** `POST /app/device/list_device`
- **Тело запроса:** `{"plantId": "<PLANT_ID>", "pageNum": 1, "pageSize": 50, "deviceType": "ALL"}`
- **Ответ:** Список объектов `DeviceBaseEntity`:
  - `deviceSn`: Серийный номер устройства
  - `deviceModel`: Модель (например, `LPBR48250`, `FLS-xxx`)
  - `deviceType`: Тип устройства (`BP` — батарейный блок, `HY` — гибридный инвертор, `IV` — инвертор)
  - `status`: Статус связи (онлайн / офлайн)
  - `emsSoc`: Заряд батареи (SOC %)
  - `emsSoh`: Здоровье батареи (SOH %)
  - `emsCapacity`: Емкость батареи (Ah / kWh)
  - `emsVoltage`: Напряжение батареи (V)
  - `emsCurrent`: Ток батареи (A)
  - `emsPower`: Мощность батареи (W)
  - `bmsPower`: Мощность BMS
  - `bmslccurr`: Лимит тока заряда BMS (A)
  - `bmsldcurr`: Лимит тока разряда BMS (A)
  - `ebatCharToday`: Заряжено сегодня (kWh)
  - `ebatDisCharToday`: Разряжено сегодня (kWh)
  - `pvPower`, `pvTotalPower`: Мощность генерации солнечных панелей (W)
  - `wifiSignal`: Уровень сигнала WiFi/коллектора
  - `firmwareVersion`: Версия прошивки
  - `controlVersion`, `displayVersion`, `moduleVersion`

### 2.6. Детальные данные батареи и ячеек (Telemetry)
- **Эндпоинты:**
  - `POST /app/plant/plantDetails_Battery` с телом `{"id": "<PLANT_ID>"}`
  - `GET /app/storageRealtimeData/pv_power_storage_realtimeData`
- **Параметры ячеек и BMS (согласно спецификации протокола `protocol_realtime` ключ 48/112):**
  - Напряжения ячеек: `cellVolt1` ... `cellVolt16` (В)
  - Температуры ячеек: `cellTemp1` ... `cellTemp4` (°C)
  - Экстремумы: `maxVoltage2bms`, `minVoltage2bms`, `maxVoltageNum2bms`, `minVoltageNum2bms`
  - Температуры экстремумы: `tempMax`, `tempMin`, `maxCellTempNum`, `minBattTempNum`
  - Лимиты напряжений: `BMSLCVolt` (Charge Voltage Limit), `BMSLDVolt` (Discharge Voltage Limit)
  - Статус BMS: `bmsState`

## 3. Требования к архитектуре интеграции Home Assistant

### 3.1. Структура интеграции
```
custom_components/felicity_ess/
├── __init__.py
├── manifest.json
├── hacs.json (в корне репозитория)
├── const.py
├── config_flow.py
├── coordinator.py
├── api.py
├── sensor.py
├── binary_sensor.py
├── brand/
│   ├── icon.png (1024x1024)
│   └── logo.png (1024x1024)
├── translations/
│   ├── en.json
│   └── ru.json
└── strings.json
```

### 3.2. Компоненты интеграции
1. **`api.py`**:
   - Асинхронный клиент на базе `aiohttp`
   - Шифрование пароля по RSA/PKCS1v15 через библиотеку `cryptography`
   - Автоматический повторный вход при истечении срока действия токена (HTTP 401 / ApiCode 3001)
   - Методы: `login()`, `get_plants()`, `get_devices()`, `get_battery_details()`, `get_realtime_data()`
2. **`coordinator.py` (`DataUpdateCoordinator`)**:
   - Периодический опрос данных (настраиваемый интервал, по умолчанию 30 секунд)
   - Объединение данных по станции, устройствам и батареям в единый кэш
   - Надежная обработка разрывов связи и таймаутов
3. **`config_flow.py`**:
   - Графическая настройка через UI Home Assistant (email/username, password, выбор станции)
   - Валидация учетных данных перед сохранением
   - Поддержка Options Flow (интервал опроса 15-300 сек)
4. **Сенсоры (`sensor.py`, `binary_sensor.py`)**:
   - Батарея: SOC (%), SOH (%), Емкость (Ah/kWh), Напряжение (V), Ток (A), Мощность (W), Заряд за сегодня (kWh), Разряд за сегодня (kWh)
   - BMS: Статус, Лимиты тока заряда/разряда (A), Лимиты напряжений (V), Cell Voltages 1..16 (V), Cell Temps 1..4 (°C), Мин/Макс напряжения и номера ячеек
   - Инвертор / Сеть / PV: Солнечная мощность (W), Напряжения/токи стрингов, Мощность сети, Потребление дома
   - Бинарные сенсоры: Статус онлайн/офлайн, Ошибки BMS, Сигнал тревоги

### 3.3. Брендинг и HACS совместимость
- Иконка и логотип (`icon.png`, `logo.png` 1024x1024) в формате, принятом в Home Assistant Brands / HACS, с фирменным логотипом Felicity Solar (оранжевый круг с градиентом и стилизованной белой строчной буквой "f").
- Файл `hacs.json` с метаданными.
- Репозиторий GitHub: `https://github.com/xpoh697/FelicityESS`.
