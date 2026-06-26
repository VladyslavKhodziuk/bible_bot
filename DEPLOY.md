# Деплой и поддержка

Бот работает на **long-polling**, поэтому публичный IP / домен / порт / HTTPS
**не нужны** — достаточно исходящего интернета. Это обычный фоновый worker.

Состояние целиком в одном файле **`bot.db`** (SQLite). Единственное жёсткое
требование к хостингу: этот файл должен переживать рестарты/редеплои.

Сейчас деплоим на **Railway** (часть A). На будущее, при росте или желании
фиксированной цены — переезд на **Hetzner VPS** (часть B), инструкция сохранена.

---

# Часть A. Railway (текущий прод)

## A0. Pre-flight чек-лист

Сделай **до** деплоя:

- [ ] **Отдельный прод-бот в @BotFather**: `/newbot` → имя → username → токен.
      Нельзя переиспользовать токен dev-бота: два long-polling процесса с одним
      токеном дают **409 Conflict**.
- [ ] Записан `BOT_TOKEN` и свои admin `user_id` (`ADMIN_IDS`, узнать у
      @userinfobot).
- [ ] **Gemini API key**: https://aistudio.google.com/apikey → `GEMINI_API_KEY`.
- [ ] Код запушен в GitHub (`main`). Railway деплоит из репозитория.
- [ ] Аккаунт на Railway (вход через GitHub) + подключённый платёжный метод
      (Hobby-план — $5/мес).

## A1. Создание проекта

В Railway Dashboard:

1. **New Project** → **Deploy from GitHub repo** → выбрать `bible_bot`,
   ветку `main`. (Если репозитория нет в списке — «Configure GitHub App» и
   дать Railway доступ к нему.)
2. Railway соберёт по **Nixpacks** (Python определится по `requirements.txt`).
   Версия Python берётся из `.python-version` (3.12). Start-команда
   (`python main.py`) и restart-policy заданы в `railway.json` — трогать в UI
   не нужно.

> Первый билд **упадёт/закрашится** — это нормально: ещё нет переменных
> окружения (`BOT_TOKEN`/`GEMINI_API_KEY` обязательны, без них `config.py`
> бросает исключение). Доведём в A2–A3, потом передеплоим.

## A2. Volume для базы (КРИТИЧНО — иначе потеря данных)

ФС контейнера на Railway **эфемерная**: при каждом редеплое/рестарте она
обнуляется. Без Volume `bot.db` и `migrations_applied.txt` сотрутся — это
**потеря всех юзеров** и повторный прогон миграций.

1. Открыть сервис → вкладка **Variables** (env зададим в A3) и **Settings**.
2. В сервисе: **+ Volume** (или Settings → Volumes → New Volume).
   - **Mount path:** `/data`
   - Размер: дефолт (стартовать можно с 1 GB; легко увеличить позже).
3. В Variables добавить **`BOT_DATA_DIR=/data`** — код положит `bot.db`,
   WAL/SHM, `migrations_applied.txt` и `persistence_sentinel.json` в
   примонтированный Volume (см. `config.py` / `database.py`).

> ⚠️ **С 2026-06-26 (после инцидента) бот отказывается стартовать на Railway
> без `BOT_DATA_DIR`** — `config.py` бросает `ValueError`. Проверка идёт по
> авто-переменной `RAILWAY_ENVIRONMENT` (её Railway выставляет сам). Локально
> и на Hetzner поведение прежнее.
>
> Дополнительно при каждом старте `database.verify_persistence()` сверяется
> с `persistence_sentinel.json` (последнее число юзеров). Если было N>0,
> стало 0 — в админ-чат прилетает 🚨 алерт «БД пуста после рестарта — Volume
> отвалился?». Не игнорируй: **не пушь обновления, пока не починишь Volume**.

Проверка после старта (см. A5): в логах первой строкой `DATA_DIR=/data`.

## A3. Переменные окружения

Сервис → **Variables** → добавить (Raw editor удобнее для пачки):

```
# Обязательные
BOT_TOKEN=<токен прод-бота>
GEMINI_API_KEY=<ключ Gemini>
BOT_DATA_DIR=/data
TZ=Europe/Madrid

# Админы/поддержка
ADMIN_IDS=<твой tg id[,ещё]>
DEFAULT_TZ=Europe/Madrid

# Опционально — фидбек-группы (можно позже; пусто → фидбек в ЛС админам)
FEEDBACK_REVIEW_CHAT_ID=
FEEDBACK_BUG_CHAT_ID=
FEEDBACK_IDEA_CHAT_ID=

# Опционально — отчёты/аналитика (дефолты ок)
REPORT_CHAT_ID=
REPORT_TIME=22:00

# Опционально — донаты (кнопка рендерится только если переменная непуста)
DONATE_MONOBANK_URL=
DONATE_MONOBANK_CARD=
DONATE_REVOLUT_URL=
DONATE_PAYPAL_URL=
DONATE_CRYPTO_URL=
DONATE_BIZUM_PHONE=
```

Полный список и значения по умолчанию — в `.env.example` и `config.py`.

> **`TZ`** важна: дневной/месячный отчёты и cleanup сверяются с **локальным
> временем контейнера** (`scheduler.py` → `datetime.now()`), а оно по умолчанию
> UTC. Личные часовые пояса юзеров на это не влияют — они считаются отдельно.
> Если отчёт приходит не в то время — образ контейнера без системной tzdata;
> тогда задавай `REPORT_TIME` прямо в UTC.

## A4. Деплой

После A2–A3 — **Deploy** (кнопка Deploy / или пуш в `main` триггерит сам).
Дождаться зелёного статуса.

## A5. Проверка

- **Logs** сервиса должны показать:
  `База данных готова → Библии загружены → Планировщик запущен →
  Run polling for bot @<твой_прод_бот>`.
- В Telegram: `/start` прод-боту → должен ответить.
- **Metrics** (RAM/CPU) — записать фактический RAM (см. «Стоимость» ниже):
  это главный драйвер цены на Railway.

## A6. Выкатка обновлений

Railway деплоит автоматически на каждый пуш в `main`:

```bash
git push origin main
```

`drop_pending_updates=True` уже стоит в `main.py` — пара секунд простоя на
редеплое не приведёт к лавине накопившихся апдейтов. Зависимости
переустанавливаются автоматически, если менялся `requirements.txt`.

## A6.5. Что делать, если бот стартовал с пустой БД

Симптом: в админ-чат прилетел алерт «БД пуста после рестарта — Volume
отвалился?», или ты сам заметил, что `/start` ведёт себя как для нового
юзера. **Сначала диагностика, потом восстановление. Ничего не пушь в `main`
до починки** — иначе сотрётся и текущая (пусть пустая) БД.

**1. Где сейчас лежит БД** — Railway → сервис → **⋮ → Open Shell**:

```bash
echo "BOT_DATA_DIR=$BOT_DATA_DIR  RAILWAY_ENVIRONMENT=$RAILWAY_ENVIRONMENT"
ls -la /data 2>/dev/null && echo "/data ok" || echo "/data НЕТ"
find / -name "bot.db" -type f 2>/dev/null
cat /data/persistence_sentinel.json 2>/dev/null
```

**2. Settings → Volumes** — есть ли Volume и куда смонтирован? Есть ли
**отвязанные** Volumes (Railway хранит их отдельно после удаления сервиса)?

**3. Восстановление:**
- Если нашёлся отвязанный Volume со старой `bot.db` → Attach to `bible_bot`,
  Mount path `/data`, выставить `BOT_DATA_DIR=/data` в Variables.
- Если ничего нет → A2 заново (новый Volume + env var). Старые юзеры утеряны
  безвозвратно. Сразу после первого старта на проде проверь, что `/data/bot.db`
  и `/data/persistence_sentinel.json` появились — следующий редеплой уже будет
  безопасным.

**4. Бэкап.** Если есть локальный `bot-YYYY-MM-DD.db` (A8) — `railway ssh`
залить обратно в `/data/bot.db`, рестартнуть сервис.

## A7. Откат

Railway хранит историю деплоев: сервис → **Deployments** → у нужного
(прошлого рабочего) → **⋮ → Redeploy**. Volume с `bot.db` при этом
сохраняется. Для отката кода в репозитории — обычный `git revert` + пуш.

## A8. Бэкапы

Volume переживает редеплои, но **сам по себе это не бэкап** (потеря/сбой тома =
потеря базы). Снимай дамп наружу периодически (минимум раз в неделю):

```bash
# Установить Railway CLI один раз: npm i -g @railway/cli ; railway login
railway link                      # выбрать проект/сервис (один раз в папке)

# WAL-safe онлайн-дамп прямо на работающем сервисе и скачивание к себе:
railway ssh "sqlite3 /data/bot.db \".backup '/data/backup.db'\""
railway ssh "cat /data/backup.db" > "bot-$(date +%F).db"   # сохранить локально
```

(Если `railway ssh` недоступен на плане — альтернатива: периодический
GitHub Actions с `railway run`, либо переезд на Hetzner, где бэкапы — простой
cron + `scp`, см. часть B шаг 5.)

## A9. Мониторинг

| Что | Где |
|---|---|
| Алерты о сбоях бота | приходят в ЛС `ADMIN_IDS` автоматически |
| Daily / monthly report | `REPORT_CHAT_ID` или ЛС админам |
| RAM / CPU | Railway → сервис → **Metrics** |
| Логи / ошибки | Railway → сервис → **Logs** |
| Расход бюджета | Railway → **Usage** (следить, чтобы укладывался в $5) |

---

## Стоимость на Railway ($5 Hobby) — на сколько хватит

**Тариф Hobby — $5/мес, и в него уже включено $5 потребления ресурсов.**
Railway тарифицирует по факту, посекундно:

- RAM: **$10 / GB / мес**
- vCPU: **$20 / vCPU / мес**
- Volume: **$0.15 / GB / мес**
- Egress: **$0.05 / GB**

Для этого бота расход определяет **в основном RAM** (постоянный), а не число
юзеров. Замеренный футпринт: библейские данные (все 16 переводов грузятся в
память при старте) — **~120 MB**; вместе с aiogram/SQLAlchemy/google-genai и
рантаймом ожидаемо **~250–350 MB** на Linux.

Прикидка месячного счёта при ~300 MB RAM:

| Ресурс | Расход | $/мес |
|---|---|---|
| RAM | ~0.30 GB | ~$3.0 |
| vCPU | long-poll почти простаивает, ~0.01–0.03 vCPU | ~$0.2–0.6 |
| Volume | ~1 GB | ~$0.15 |
| Egress | текстовые сообщения, ~единицы GB | <$0.30 |
| **Итого** | | **≈ $3.5–4.5 → влезает в $5** ✅ |

**На сколько хватит / рост.** Стоимость почти не зависит от числа юзеров:
у текстового бота предельная цена на юзера микроскопическая — килобайты egress
и миллисекунды CPU на сообщение, пара КБ в SQLite на юзера. Поэтому **$5 хватит
практически на любой реалистичный рост — десятки тысяч активных юзеров** — пока
не растёт постоянный RAM. AI-пастырь Railway не нагружает (Gemini — внешний).

**Что может выбить из $5:**
- RAM уползёт к ~480 MB+ → одна память уже $4.8/мес, плюс CPU/egress = перерасход
  (доплата сверху, не отключение). После деплоя **сверь реальный RAM в Metrics**.
- Добавишь тяжёлую фичу (генерация картинок, большие кэши) или второй сервис
  (например, отдельный Postgres).

**Когда переезжать на Hetzner:** если перерасход на Railway стабильно превышает
~€4.5/мес, либо нужна предсказуемая фиксированная цена / больше RAM / несколько
сервисов. CX22 — €4.50/мес за 4 GB / 2 vCPU без метеринга (часть B).

---

# Часть B. Hetzner VPS (альтернатива / на будущее)

Прод-сетап: Hetzner Cloud VPS + Ubuntu 24.04 + systemd. Те же требования
(long-polling, исходящий интернет). Здесь `bot.db` лежит прямо в папке проекта
(`BOT_DATA_DIR` не нужен — дефолт «рядом с кодом» подходит).

## B0. Pre-flight

Как A0, плюс: **Hetzner аккаунт** + SSH-ключ в Hetzner Cloud Console.

## B1. Создание сервера

В Hetzner Cloud Console:

- **Project** → New project (`bible-bot`).
- **Add Server**:
  - Location: ближайший (Falkenstein/Nuremberg/Helsinki).
  - Image: **Ubuntu 24.04**.
  - Type: **CX22** (€4.50/мес, 2 vCPU / 4 GB RAM) — с запасом. CX11 снят.
  - Networking: IPv4 + IPv6.
  - SSH keys: выбрать свой.
  - Name: `bible-bot-prod`.
- Создать → запомнить **IPv4**.

## B2. Первичная настройка сервера

```bash
ssh root@<IP>
```

На сервере (под root):

```bash
apt update && apt upgrade -y
apt install -y python3.12 python3.12-venv python3-pip git sqlite3 ufw

# Файервол: наружу открыт только SSH
ufw allow OpenSSH
ufw enable

# Юзер для бота (без sudo)
useradd -m -s /bin/bash bible
mkdir -p /home/bible/.ssh
cp /root/.ssh/authorized_keys /home/bible/.ssh/
chown -R bible:bible /home/bible/.ssh
chmod 700 /home/bible/.ssh
chmod 600 /home/bible/.ssh/authorized_keys
```

Заходим уже юзером `bible`:

```bash
exit
ssh bible@<IP>
```

## B3. Клонирование и установка

Под `bible`:

```bash
cd ~
git clone https://github.com/VladyslavKhodziuk/bible_bot.git
cd bible_bot

python3.12 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env   # заполнить BOT_TOKEN, GEMINI_API_KEY, ADMIN_IDS, остальное по вкусу
chmod 600 .env
```

Быстрый тест (Ctrl+C через 5 сек): `./venv/bin/python main.py` — должно вывести
`База данных готова → Библии загружены → Планировщик запущен → Run polling…`.
`bot.db` создастся сам.

## B4. systemd-сервис

```bash
sudo cp ~/bible_bot/deploy/bible-bot.service /etc/systemd/system/bible-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now bible-bot
sudo systemctl status bible-bot
```

Логи: `journalctl -u bible-bot -f` (live), `-p err` (ошибки),
`--since "1 hour ago"`.

## B5. Бэкапы

```bash
mkdir -p ~/backups
chmod +x ~/bible_bot/deploy/backup.sh
~/bible_bot/deploy/backup.sh && ls -lh ~/backups/

# Cron: каждый день в 03:00
( crontab -l 2>/dev/null; echo "0 3 * * * /home/bible/bible_bot/deploy/backup.sh >> /home/bible/backups/backup.log 2>&1" ) | crontab -
```

Рекомендую копировать бэкапы наружу (Storage Box / rclone в S3 / scp на свою
машину) — минимум раз в неделю.

## B6. Обновления / откат

```bash
# Обновление
cd ~/bible_bot && git pull origin main
./venv/bin/pip install -r requirements.txt   # если менялись зависимости
sudo systemctl restart bible-bot

# Откат кода
git reset --hard <HASH> && sudo systemctl restart bible-bot

# Откат БД из бэкапа
sudo systemctl stop bible-bot
gunzip -c ~/backups/bot-2026-06-22_0300.db.gz > ~/bible_bot/bot.db
rm -f ~/bible_bot/bot.db-wal ~/bible_bot/bot.db-shm
sudo systemctl start bible-bot
```

## B7. Полезные команды

```bash
sudo systemctl status|restart|stop bible-bot
journalctl -u bible-bot -f
sqlite3 ~/bible_bot/bot.db "SELECT COUNT(*) FROM users;"
du -h ~/bible_bot/bot.db ; df -h / ; free -h
```

---

## FAQ

**Запустил dev-бота и прод одновременно — что будет?**
У них разные токены — оба работают независимо. Один токен дважды запускать
нельзя (409 Conflict).

**Можно мигрировать `bot.db` с dev на prod?**
Технически да, но не рекомендую: dev-база содержит тестовых юзеров и фейковую
статистику. Чище стартовать прод с пустой базой — `init_db()` создаст схему сам.

**Сломалась миграция?**
Миграции в `database.py::run_migrations()` идемпотентны, ключ пишется в
`migrations_applied.txt` (на Railway — в `/data`, на Hetzner — рядом с `bot.db`).
Если новая миграция упала: исправить блок, задеплоить, удалить её ключ из
`migrations_applied.txt`, рестарт.

**Перенос Railway → Hetzner.**
Останови приём на Railway (можно не останавливать — 409 разрулится), скачай
`bot.db` (A8), положи в `~/bible_bot/bot.db` на Hetzner, убери WAL/SHM, запусти
systemd-сервис. `BOT_DATA_DIR` на Hetzner не задавай (дефолт «рядом с кодом»).
